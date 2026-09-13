"""Controlled Living Memory cognition using provider proposals and Python adjudication."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from uuid import NAMESPACE_URL, uuid5

from dynamic_subject_agent.domains import (
    ExperienceAdjudicationRequest,
    ExperienceChangeCandidate,
    ExperienceReadView,
)
from dynamic_subject_agent.runtime import (
    CognitionEngine,
    CognitionRuntimeView,
    CognitiveProposal,
    CyclePlan,
    ExperienceBasis,
    ExpressionCandidate,
    M0_A_PROVIDER_AUTHORITY,
)
from dynamic_subject_agent.timeline import LivingMemoryRecord, SubjectCommand
from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection
from dynamic_subject_agent.recent_dialogue import RecentDialogueTurn, is_dialogue_control, is_dialogue_continuation, is_previous_expression_rewrite, sentence_revision_index
from dynamic_subject_agent.runtime_identity_reply import activity_boundary_reply, contextual_reply, repeats_previous_expression, has_creative_sentence, has_supplied_sentence, MISSING_REVISION_REPLY, FAILED_REVISION_REPLY, CREATIVE_REPLY_PREFIX, explicit_creation_request
from dynamic_subject_agent.reminder_expression import reminder_request_kind, REMINDER_BOUNDARY
from dynamic_subject_agent.memory_answer_scope import is_memory_status_query, unsupported_inventory_claim, selected_memory_answer, exact_memory_status_answer, MEMORY_SCOPE_UNAVAILABLE, grounded_memory_answer
from dynamic_subject_agent.memory_control import MemoryWithdrawal, select_memory_withdrawal, memory_withdrawal_reply, is_memory_inventory_query, missing_name_answer
from dynamic_subject_agent.factual_boundary import unsourced_fact_reply
from dynamic_subject_agent.memory_subject import requested_memory_subject, select_subject_memories
from dynamic_subject_agent.memory_write_receipt import (
    explicit_memory_write_request, independent_memory_question, contains_memory_write_claim, memory_write_receipt, combine_memory_write_receipt,
)


ACTIVE_MEMORY_LIMIT = 20


class LivingMemoryAction(str, Enum):
    NONE = "none"
    CREATE = "create"
    REVISE = "revise"


@dataclass(frozen=True)
class LivingMemoryProviderMemory:
    memory_id: str
    content: str
    source_user_message_id: str


@dataclass(frozen=True)
class LivingMemoryProviderRequest:
    current_user_message: str
    active_memories: tuple[LivingMemoryProviderMemory, ...]


@dataclass(frozen=True)
class LivingMemoryReplyMemory:
    content: str


@dataclass(frozen=True)
class LivingMemoryReplyRequest:
    current_user_message: str
    selected_memories: tuple[LivingMemoryReplyMemory, ...]
    runtime_identity: RuntimeIdentityProjection
    recent_dialogue: tuple[RecentDialogueTurn, ...] = ()


@dataclass(frozen=True)
class LivingMemoryReplyResult:
    reply_text: str
    language: str
    reply_kind: str = 'conversation'

    @classmethod
    def from_mapping(cls, value: object) -> LivingMemoryReplyResult:
        if not isinstance(value, dict) or set(value) != {'reply_text', 'language', 'reply_kind'}:
            raise ValueError('memory-reply-fields-invalid')
        text, kind = value['reply_text'], value['reply_kind']
        if (value['language'] != 'zh' or kind not in {'conversation', 'creative', 'activity', 'memory'}
            or not isinstance(text, str) or (not text.strip() and kind != 'memory') or len(text) > 8_000):
            raise ValueError('memory-reply-shape-invalid')
        return cls(text, 'zh', kind)


MEMORY_KINDS = frozenset({"durable", "plan"})
_HISTORICAL_RECALL_MARKERS = (
    "一开始",
    "最初",
    "说错",
    "错误",
    "更正前",
    "改之前",
)
from dynamic_subject_agent.model_gateway import (
    ModelGateway,
    ModelGatewayFailure,
    ModelResult,
    ModelTask,
    ModelTaskKind,
    ProviderAdapter,
    ProviderCapabilities,
    StructuredOutputMode,
)
_EARLIEST_RECALL_MARKERS = ("一开始", "最初")


def _historical_memory_for_recalled_revision(
    message: str,
    *,
    recalled_memory_ids: tuple[str, ...],
    active_memories: tuple[LivingMemoryRecord, ...],
    memory_history: tuple[LivingMemoryRecord, ...],
) -> LivingMemoryRecord | None:
    if not any(marker in message for marker in _HISTORICAL_RECALL_MARKERS):
        return None
    if len(recalled_memory_ids) != 1:
        return None
    current = {
        memory.memory_id: memory for memory in active_memories
    }.get(recalled_memory_ids[0])
    if current is None or current.supersedes_memory_id is None:
        return None
    history = {memory.memory_id: memory for memory in memory_history}
    previous = history.get(current.supersedes_memory_id)
    if previous is None or previous.status != "superseded":
        return None
    if not any(marker in message for marker in _EARLIEST_RECALL_MARKERS):
        return previous
    visited = {current.memory_id}
    while previous.supersedes_memory_id is not None:
        if previous.memory_id in visited:
            return None
        visited.add(previous.memory_id)
        older = history.get(previous.supersedes_memory_id)
        if older is None or older.status != "superseded":
            break
        previous = older
    return previous


@dataclass(frozen=True)
class LivingMemoryProposal:
    action: LivingMemoryAction
    evidence_quote: str
    supersedes_memory_id: str | None = None
    recalled_memory_ids: tuple[str, ...] = ()
    memory_kind: str = "durable"


@dataclass(frozen=True)
class LivingMemoryProviderResult:
    proposal: LivingMemoryProposal
    experience_summary: str
    reply_text: str
    language: str


class LivingMemoryProviderAdapter(ProviderAdapter):
    def __init__(self, *, provider: object) -> None:
        self._split = callable(getattr(provider, "propose", None)) and callable(
            getattr(provider, "reply", None)
        )
        if not self._split and not callable(getattr(provider, "analyze", None)):
            raise TypeError("provider must expose propose/reply or analyze")
        provider_id = getattr(provider, "provider_authority", M0_A_PROVIDER_AUTHORITY)
        if not isinstance(provider_id, str) or not provider_id:
            raise TypeError("provider_authority must be a non-empty string")
        self._provider = provider
        self.capabilities = ProviderCapabilities(
            provider_id=provider_id,
            model_id=str(getattr(provider, "model_id", type(provider).__name__)),
            local=bool(getattr(provider, "local", False)),
            structured_output_modes=(StructuredOutputMode.JSON_OBJECT,),
        )

    def invoke(self, task: ModelTask) -> ModelResult:
        if task.kind is ModelTaskKind.LIVING_MEMORY_ANALYSIS and isinstance(
            task.payload,
            LivingMemoryProviderRequest,
        ):
            result = (
                self._provider.propose(task.payload)
                if self._split
                else self._provider.analyze(task.payload)
            )
            return ModelResult(task.kind, result)
        if (
            task.kind is ModelTaskKind.LIVING_MEMORY_REPLY
            and isinstance(task.payload, LivingMemoryReplyRequest)
            and self._split
        ):
            return ModelResult(task.kind, self._provider.reply(task.payload))
        raise ModelGatewayFailure("living-memory-task-invalid")


class ControlledLivingMemoryCognition(CognitionEngine):
    """No-write cognition seam; only ExperienceDomain may accept a proposal."""

    adapter_version = "living-memory-cognition-1.0"
    provider_authority = M0_A_PROVIDER_AUTHORITY
    experimental = True
    test_only = True

    def __init__(
        self,
        *,
        provider: object,
    ) -> None:
        split = callable(getattr(provider, "propose", None)) and callable(
            getattr(provider, "reply", None)
        )
        if not split and not callable(getattr(provider, "analyze", None)):
            raise TypeError("provider must expose propose/reply or analyze")
        provider_authority = getattr(
            provider,
            "provider_authority",
            M0_A_PROVIDER_AUTHORITY,
        )
        if not isinstance(provider_authority, str) or not provider_authority:
            raise TypeError("provider_authority must be a non-empty string")
        self.provider_authority = provider_authority
        self.test_only = bool(getattr(provider, "test_only", True))
        self._gateway = ModelGateway(LivingMemoryProviderAdapter(provider=provider))
        self._split = split

    @classmethod
    def for_profile(
        cls,
        profile: str,
        *,
        deepseek_transport: object | None = None,
        credential_ref: object | None = None,
    ) -> ControlledLivingMemoryCognition:
        if profile != "default":
            raise ValueError("Living Memory profile adapter is unavailable")
        from dynamic_subject_agent.deepseek import DeepSeekLivingMemoryProvider

        return cls(
            provider=DeepSeekLivingMemoryProvider(
                transport=deepseek_transport,
                credential_ref=credential_ref,
            )
        )

    def propose(
        self,
        *,
        plan: CyclePlan,
        context: CognitionRuntimeView,
        command: SubjectCommand,
        basis: ExperienceBasis,
    ) -> CognitiveProposal:
        active = tuple(context.active_memories[:ACTIVE_MEMORY_LIMIT])
        memory_subject = requested_memory_subject(command.utterance)
        control_active = tuple(m for m in context.living_memory_history if m.status == 'active') if context.living_memory_history else active
        withdrawal = select_memory_withdrawal(command.utterance, control_active)
        if withdrawal is not None and withdrawal.restricts_disclosure and not context.memory_control_complete:
            withdrawal = MemoryWithdrawal(None, 'inventory_incomplete')
        if withdrawal is not None:
            base = self._bounded_noop_proposal(context=context, basis=basis,
                experience_summary='本轮请求逻辑遗忘，结果以裁决为准。',
                expression_candidate=ExpressionCandidate('本轮记忆操作尚未确认。', command.language, dialogue_priority=True))
            return replace(base, impact_envelope=replace(base.impact_envelope,
                experience=ExperienceAdjudicationRequest(basis=basis,
                    current_state=ExperienceReadView(basis.verified_prefix_digest,
                        tuple(m.memory_id for m in control_active), control_active,
                        memory_control_complete=context.memory_control_complete), candidates=(),
                    current_user_message=command.utterance, source_user_message_id=basis.operation_id,
                    memory_withdrawal=withdrawal)))
        withheld = ()
        disclosure_unavailable = False
        if context.load_withheld_memory_ids is not None:
            try:
                withheld = context.load_withheld_memory_ids()
            except Exception:
                disclosure_unavailable = True
                withheld = tuple(m.memory_id for m in control_active)
            active = tuple(m for m in active if m.memory_id not in withheld)
        available = tuple(m for m in control_active if m.memory_id not in withheld)
        preference_inventory = tuple(m for m in context.canonical_memory_history if m.status == 'active' and m.memory_id not in withheld)
        from dynamic_subject_agent.scoped_preferences import route_preference
        from dynamic_subject_agent.preference_clarification import choice, resolve, make_question
        pending = None
        confirmation = choice(command.utterance) is not None
        if confirmation:
            try:
                pending = context.load_preference_question() if context.load_preference_question is not None else None
            except Exception:
                disclosure_unavailable = True
            preference = resolve(command.utterance, pending, preference_inventory,
                complete=context.memory_control_complete and not disclosure_unavailable and not withheld,
                profile_id=context.profile_id, timeline_id=context.timeline_id, now=basis.observed_at_us)
        else:
            preference = route_preference(command.utterance, context.canonical_memory_history,
                complete=context.memory_control_complete, readable=not disclosure_unavailable and not withheld)
        if preference is not None:
            question = (make_question(command.utterance, preference_inventory,
                complete=context.memory_control_complete and not disclosure_unavailable and not withheld,
                source_id=basis.operation_id, profile_id=context.profile_id, timeline_id=context.timeline_id, now=basis.observed_at_us)
                if preference.needs_choice else None)
            if preference.needs_choice and question is None:
                preference = replace(preference, reply='这次无法保留待确认问题，请直接写明完整场景、颜色及补充或更正意图。')
            base = self._bounded_noop_proposal(context=context, basis=basis,
                experience_summary='按当前明确场景处理偏好，写入以最终裁决为准。',
                expression_candidate=ExpressionCandidate(preference.reply, command.language, is_memory_answer=True, dialogue_priority=True))
            candidates = ()
            if preference.action in {'create', 'revise'}:
                candidates = (ExperienceChangeCandidate(candidate_id=str(uuid5(NAMESPACE_URL, 'scoped-preference:' + basis.operation_id)),
                    target_experience_id=basis.experience_id, evidence_refs=(basis.operation_id,),
                    memory_action=preference.action, evidence_quote=preference.evidence,
                    supersedes_memory_id=preference.target, memory_kind='durable'),)
            return replace(base, memory_write_requested=bool(candidates), impact_envelope=replace(base.impact_envelope,
                experience=ExperienceAdjudicationRequest(basis=basis,
                    current_state=ExperienceReadView(basis.verified_prefix_digest, tuple(m.memory_id for m in control_active), control_active,
                        memory_control_complete=context.memory_control_complete and not disclosure_unavailable and not withheld,
                        preference_memories=preference_inventory, pending_preference=pending),
                    candidates=candidates, current_user_message=command.utterance, source_user_message_id=basis.operation_id,
                    preference_question=question)))
        status_answer = exact_memory_status_answer(command.utterance, context.canonical_memory_history,
            complete=context.memory_control_complete, readable=not disclosure_unavailable and not withheld)
        if status_answer is not None:
            return self._bounded_noop_proposal(context=context, basis=basis,
                experience_summary='本轮本地核实明确原文的记录状态，不回显内容。',
                expression_candidate=ExpressionCandidate(status_answer, command.language, dialogue_priority=True))
        if context.memory_retrieval_unavailable and not is_memory_inventory_query(command.utterance):
            return self._failure(context, command, basis, active, 'living-memory-retrieval-unavailable')
        name_answer = missing_name_answer(command.utterance, active, complete=context.memory_control_complete)
        if is_memory_inventory_query(command.utterance) or name_answer is not None:
            text = name_answer or ('当前可用于召回的活跃记录：\n' + '\n'.join(f'「{m.content}」' for m in available)
                if available else '当前没有可用于召回的活跃记忆。')
            if disclosure_unavailable:
                text = '这次无法核实可用记忆清单，暂不返回记忆内容。'
            elif not context.memory_control_complete:
                text = '当前无法证明记忆清单完整，不能把局部结果当作全部记录。'
            elif withheld:
                text += '\n有未完成的遗忘请求，相关内容暂不用于回复；这不表示已成功停用。'
            return self._bounded_noop_proposal(context=context, basis=basis,
                experience_summary='本轮本地读取可用活跃记忆清单。',
                expression_candidate=ExpressionCandidate(text, command.language, dialogue_priority=True))
        if memory_subject is not None:
            active = select_subject_memories(active, memory_subject)
        request = LivingMemoryProviderRequest(
            current_user_message=command.utterance,
            active_memories=tuple(
                LivingMemoryProviderMemory(
                    memory_id=memory.memory_id,
                    content=memory.content,
                    source_user_message_id=memory.source_user_message_id,
                )
                for memory in active
            ),
        )
        try:
            result = self._gateway.execute(
                ModelTask(ModelTaskKind.LIVING_MEMORY_ANALYSIS, request)
            ).value
        except Exception as error:
            return self._failure(
                context,
                command,
                basis,
                active,
                "living-memory-provider-failed",
            )
        if (
            not isinstance(result, LivingMemoryProviderResult)
            or not isinstance(result.proposal, LivingMemoryProposal)
            or not isinstance(result.proposal.action, LivingMemoryAction)
            or result.language != command.language
            or not result.reply_text.strip()
            or result.proposal.memory_kind not in MEMORY_KINDS
            or memory_subject is not None and result.proposal.action is not LivingMemoryAction.NONE
        ):
            return self._failure(
                context,
                command,
                basis,
                active,
                "living-memory-provider-invalid-output",
            )
        summary = result.experience_summary.strip() or (
            f"召回 {len(result.proposal.recalled_memory_ids)} 条记忆。"
            if result.proposal.recalled_memory_ids
            else "本轮无记忆变化。"
        )
        active_ids = {memory.memory_id for memory in active}
        recalled_ids = result.proposal.recalled_memory_ids
        if (
            not isinstance(recalled_ids, tuple)
            or any(memory_id not in active_ids for memory_id in recalled_ids)
        ):
            return self._failure(
                context,
                command,
                basis,
                active,
                "living-memory-provider-invalid-output",
            )
        historical_memory = _historical_memory_for_recalled_revision(
            command.utterance,
            recalled_memory_ids=recalled_ids,
            active_memories=active,
            memory_history=context.living_memory_history,
        )
        reply_text = contextual_reply(result.reply_text, message=command.utterance)
        is_creative = False
        is_memory_answer = False
        recent_dialogue = ()
        refinement_used = False
        refined_kind = None
        expression_failure_used = False
        revision_index = sentence_revision_index(command.utterance)
        from dynamic_subject_agent.runtime_identity_reply import supplied_draft_candidates
        current_draft_present = bool(supplied_draft_candidates(command.utterance))
        revision_supplied = revision_index is not None and has_supplied_sentence(command.utterance, revision_index)
        revision_ready = False
        if self._split:
            if not isinstance(context.runtime_identity, RuntimeIdentityProjection):
                return self._failure(
                    context,
                    command,
                    basis,
                    active,
                    "living-memory-provider-invalid-output",
                )
            selected = tuple(
                LivingMemoryReplyMemory(memory.content)
                for memory in active
                if memory.memory_id in recalled_ids
            )[:5]
            recent_dialogue = ()
            if (context.load_recent_dialogue is not None
                and not current_draft_present
                and not withheld
                and not disclosure_unavailable
                and result.proposal.action is not LivingMemoryAction.REVISE
                and not is_dialogue_control(command.utterance)):
                try:
                    recent_dialogue = context.load_recent_dialogue()
                    if is_previous_expression_rewrite(command.utterance):
                        recent_dialogue = recent_dialogue[-1:]
                except Exception:
                    # Optional context failure cannot license history disclosure
                    # or cancel the independently obtained state proposal.
                    recent_dialogue = ()
            revision_ready = revision_supplied or bool(recent_dialogue and revision_index is not None
                and has_creative_sentence(recent_dialogue[-1].assistant_text, revision_index))
            try:
                reply_result = self._gateway.execute(
                    ModelTask(
                        ModelTaskKind.LIVING_MEMORY_REPLY,
                        LivingMemoryReplyRequest(
                            current_user_message=command.utterance,
                            selected_memories=selected,
                            runtime_identity=context.runtime_identity,
                            recent_dialogue=recent_dialogue,
                        ),
                    )
                ).value
            except Exception:
                reply_result = None
            if (
                isinstance(reply_result, LivingMemoryReplyResult)
                and isinstance(reply_result.reply_text, str)
                and (reply_result.reply_text.strip() or reply_result.reply_kind == 'memory')
                and reply_result.language == command.language
            ):
                if reply_result.reply_kind == 'memory':
                    is_memory_answer = result.proposal.action is LivingMemoryAction.NONE
                    guarded_reply = (grounded_memory_answer(tuple(m.content for m in selected),
                        available=not disclosure_unavailable and not withheld)
                        if is_memory_answer else '我收到了你这次的说明。')
                    activity = activity_boundary_reply(command.utterance)
                    if reminder_request_kind(command.utterance) is not None:
                        guarded_reply, is_memory_answer = REMINDER_BOUNDARY, False
                    elif activity is not None:
                        guarded_reply, is_memory_answer = activity, False
                    elif explicit_creation_request(command.utterance) or is_dialogue_continuation(command.utterance):
                        guarded_reply, is_memory_answer = None, False
                        reply_text = '这次没能给出符合你请求的回复，我不会用记忆记录代替当前创作。'
                        expression_failure_used = True
                else:
                    guarded_reply = contextual_reply(reply_result.reply_text,
                        message=command.utterance, reply_kind=reply_result.reply_kind,
                        continuation_allowed=revision_supplied or (bool(recent_dialogue) and is_dialogue_continuation(command.utterance)
                            and (revision_index is None or revision_ready)))
                if guarded_reply is not None and guarded_reply.startswith(CREATIVE_REPLY_PREFIX) and revision_index is not None and revision_ready:
                    from dynamic_subject_agent.runtime_identity_reply import complete_sentence_revision, supplied_draft_text
                    original = supplied_draft_text(command.utterance) if revision_supplied else recent_dialogue[-1].assistant_text
                    revised = complete_sentence_revision(guarded_reply, original, revision_index, source_is_history=not revision_supplied)
                    guarded_reply = (contextual_reply(revised, message=command.utterance, reply_kind='creative', continuation_allowed=True)
                                     if revised is not None else None)
                if (guarded_reply is not None and recent_dialogue and is_dialogue_continuation(command.utterance)
                    and repeats_previous_expression(guarded_reply, recent_dialogue[-1].assistant_text)):
                    guarded_reply = None
                if guarded_reply is not None:
                    reply_text = guarded_reply
                    refinement_used = True
                    refined_kind = reply_result.reply_kind
                    is_creative = reply_result.reply_kind == 'creative' and guarded_reply.startswith(CREATIVE_REPLY_PREFIX)
                elif reply_result.reply_kind == 'creative' and reply_text in {None, '（无记忆相关内容）'}:
                    # Rejected unsolicited creation is an expression mismatch,
                    # not evidence that the current message lacks information.
                    reply_text = '这次没能给出符合你请求的回复，我不会用擅自创作的内容代替。'
                    expression_failure_used = True
        if memory_subject is not None:
            # The complete local question owns the answer mode, independently
            # of optional refinement or the legacy analyze-only adapter.
            reply_text = grounded_memory_answer(tuple(m.content for m in active if m.memory_id in recalled_ids)[:5],
                available=not disclosure_unavailable and not withheld)
            is_memory_answer, is_creative = True, False
        if reply_text is None:
            reply_text = '这件事我还没有可靠的内容可以说。我们可以先从你现在想聊的部分说起。'
        if self._split and is_dialogue_continuation(command.utterance) and (not (recent_dialogue or revision_supplied) or not refinement_used):
            reply_text = ('这轮没有可以可靠使用的前文，请把要改的句子或意思再说一下。' if not recent_dialogue
                else '这次没有形成新的改写版本。请再说明希望怎样调整这句话。')
            is_creative = False
        if revision_index is not None and (not revision_ready or not refinement_used):
            reply_text = FAILED_REVISION_REPLY if revision_ready else MISSING_REVISION_REPLY
            is_creative = False
            expression_failure_used = True
        if historical_memory is not None:
            is_creative = False
            summary = "本轮通过 canonical Living Memory 修订链召回更正前记录。"
            reply_text = f"你更正前说的是：「{historical_memory.content}」"
        factual_boundary = unsourced_fact_reply(command.utterance)
        if factual_boundary is not None:
            reply_text = factual_boundary
            is_creative = False
            is_memory_answer = False
        memory_scope_checked = is_memory_status_query(command.utterance) or (not is_creative and unsupported_inventory_claim(reply_text))
        if memory_scope_checked:
            reply_text = selected_memory_answer(tuple(m.content for m in active if m.memory_id in recalled_ids)[:5],
                available=not disclosure_unavailable and not withheld)
            is_creative = False
        candidates: tuple[ExperienceChangeCandidate, ...] = ()
        if result.proposal.action in {
            LivingMemoryAction.CREATE,
            LivingMemoryAction.REVISE,
        } or recalled_ids:
            candidate_id = str(
                uuid5(
                    NAMESPACE_URL,
                    "living-memory:"
                    f"{basis.operation_id}:{result.proposal.action.value}:"
                    f"{result.proposal.evidence_quote}",
                )
            )
            candidates = (
                ExperienceChangeCandidate(
                    candidate_id=candidate_id,
                    target_experience_id=basis.experience_id,
                    evidence_refs=(basis.operation_id,),
                    memory_action=result.proposal.action.value,
                    evidence_quote=result.proposal.evidence_quote,
                    supersedes_memory_id=result.proposal.supersedes_memory_id,
                recalled_memory_ids=recalled_ids,
                memory_kind=result.proposal.memory_kind,
            ),
            )
        write_requested = (result.proposal.action in {LivingMemoryAction.CREATE, LivingMemoryAction.REVISE}
                           or explicit_memory_write_request(command.utterance)
                           or not is_creative and not recalled_ids and contains_memory_write_claim(reply_text))
        from dynamic_subject_agent.runtime_identity_reply import creation_failure_reply
        creation_requested = explicit_creation_request(command.utterance)
        if creation_requested and not is_creative:
            # Failure is independent of whether Memory proposed a write.
            # Existing factual/activity/reminder boundaries are kept alongside.
            failure = creation_failure_reply(command.utterance)
            if factual_boundary is None and reminder_request_kind(command.utterance) is None and activity_boundary_reply(command.utterance) is None:
                reply_text = failure
            elif failure not in reply_text:
                reply_text += '\n\n' + failure
        continuation = (ExpressionCandidate(reply_text, command.language, is_creative=is_creative, dialogue_priority=True)
                        if is_creative or creation_requested else None)
        if write_requested:
            if is_creative or factual_boundary is not None or reminder_request_kind(command.utterance) is not None or activity_boundary_reply(command.utterance) is not None:
                continuation = ExpressionCandidate(reply_text, command.language, is_creative=is_creative, dialogue_priority=True)
            elif explicit_creation_request(command.utterance) or is_dialogue_continuation(command.utterance):
                continuation = ExpressionCandidate(creation_failure_reply(command.utterance), command.language, dialogue_priority=True)
            elif independent_memory_question(command.utterance, result.proposal.evidence_quote):
                independent = ('这次还没能可靠地回答你另外的问题。' if contains_memory_write_claim(reply_text)
                               or self._split and (not refinement_used or refined_kind != 'conversation')
                               else '关于你的问题：\n' + reply_text)
                continuation = ExpressionCandidate(independent, command.language, dialogue_priority=True)
            reply_text = continuation.text if continuation is not None else ''
        base = self._bounded_noop_proposal(
            context=context,
            basis=basis,
            experience_summary=summary,
            expression_candidate=ExpressionCandidate(
                text=reply_text,
                language=result.language,
                is_creative=is_creative,
                is_memory_answer=is_memory_answer,
                dialogue_priority=write_requested or is_memory_answer or memory_scope_checked or reminder_request_kind(command.utterance) is not None or factual_boundary is not None or self._split and (is_dialogue_continuation(command.utterance)
                    or expression_failure_used or bool(recent_dialogue) and refinement_used),
            ),
        )
        experience_request = ExperienceAdjudicationRequest(
            basis=basis,
            current_state=ExperienceReadView(
                verified_prefix_digest=basis.verified_prefix_digest,
                memory_trace_refs=tuple(memory.memory_id for memory in active),
                active_memories=active,
                memory_control_complete=context.memory_control_complete and not disclosure_unavailable and not withheld,
                preference_memories=preference_inventory,
            ),
            candidates=candidates,
            current_user_message=command.utterance,
            source_user_message_id=plan.operation_ref.operation_id,
        )
        return replace(
            base,
            memory_write_requested=write_requested,
            memory_continuation=continuation,
            impact_envelope=replace(
                base.impact_envelope,
                experience=experience_request,
            ),
        )

    def express(self, *, proposal, context, command, outcomes):
        text = memory_withdrawal_reply(outcomes.experience.memory_withdrawal_status)
        if text is not None:
            return ExpressionCandidate(text, command.language)
        receipt = memory_write_receipt(outcomes.experience, requested=proposal.memory_write_requested)
        if receipt is not None:
            return ExpressionCandidate(combine_memory_write_receipt(receipt, proposal.expression_candidate.text), command.language)
        return proposal.expression_candidate

    def _failure(
        self,
        context: CognitionRuntimeView,
        command: SubjectCommand,
        basis: ExperienceBasis,
        active: tuple[LivingMemoryRecord, ...],
        code: str,
    ) -> CognitiveProposal:
        factual_boundary = unsourced_fact_reply(command.utterance)
        write_requested = explicit_memory_write_request(command.utterance)
        base = self._bounded_noop_proposal(
            context=context,
            basis=basis,
            experience_summary="Living Memory 本轮失败关闭。",
            expression_candidate=ExpressionCandidate(
                text=(MEMORY_SCOPE_UNAVAILABLE if is_memory_status_query(command.utterance) or requested_memory_subject(command.utterance) is not None else factual_boundary
                    or ('' if write_requested else '这次没能完成记忆检索，请稍后再试。' if code == 'living-memory-retrieval-unavailable' else "（无记忆相关内容）")),
                language=command.language,
                dialogue_priority=write_requested or is_memory_status_query(command.utterance) or requested_memory_subject(command.utterance) is not None or factual_boundary is not None,
            ),
        )
        return replace(
            base,
            memory_write_requested=explicit_memory_write_request(command.utterance),
            impact_envelope=replace(
                base.impact_envelope,
                experience=ExperienceAdjudicationRequest(
                    basis=basis,
                    current_state=ExperienceReadView(
                        verified_prefix_digest=basis.verified_prefix_digest,
                        memory_trace_refs=tuple(memory.memory_id for memory in active),
                        active_memories=active,
                    ),
                    candidates=(),
                    current_user_message=command.utterance,
                    source_user_message_id=basis.operation_id,
                    living_memory_failure_code=code,
                ),
            ),
        )


__all__ = [
    "ACTIVE_MEMORY_LIMIT",
    "MEMORY_KINDS",
    "ControlledLivingMemoryCognition",
    "LivingMemoryProviderAdapter",
    "LivingMemoryAction",
    "LivingMemoryProposal",
    "LivingMemoryProviderMemory",
    "LivingMemoryProviderRequest",
    "LivingMemoryProviderResult",
    "LivingMemoryReplyMemory",
    "LivingMemoryReplyRequest",
    "LivingMemoryReplyResult",
]
