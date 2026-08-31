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
        if not callable(getattr(provider, "analyze", None)):
            raise TypeError("provider must expose analyze(request)")
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
        if (
            task.kind is not ModelTaskKind.LIVING_MEMORY_ANALYSIS
            or not isinstance(task.payload, LivingMemoryProviderRequest)
        ):
            raise ModelGatewayFailure("living-memory-task-invalid")
        return ModelResult(task.kind, self._provider.analyze(task.payload))


class ControlledLivingMemoryCognition(CognitionEngine):
    """No-write cognition seam; only ExperienceDomain may accept a proposal."""

    adapter_version = "living-memory-cognition-1.0"
    provider_authority = M0_A_PROVIDER_AUTHORITY
    experimental = True
    test_only = True

    def __init__(self, *, provider: object) -> None:
        if not callable(getattr(provider, "analyze", None)):
            raise TypeError("provider must expose analyze(request)")
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
        reply_text = result.reply_text
        if historical_memory is not None:
            summary = "本轮通过 canonical Living Memory 修订链召回更正前记录。"
            reply_text = f"你更正前说的是：「{historical_memory.content}」"
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
        base = self._bounded_noop_proposal(
            context=context,
            basis=basis,
            experience_summary=summary,
            expression_candidate=ExpressionCandidate(
                text=reply_text,
                language=result.language,
            ),
        )
        experience_request = ExperienceAdjudicationRequest(
            basis=basis,
            current_state=ExperienceReadView(
                verified_prefix_digest=basis.verified_prefix_digest,
                memory_trace_refs=tuple(memory.memory_id for memory in active),
                active_memories=active,
            ),
            candidates=candidates,
            current_user_message=command.utterance,
            source_user_message_id=plan.operation_ref.operation_id,
        )
        return replace(
            base,
            impact_envelope=replace(
                base.impact_envelope,
                experience=experience_request,
            ),
        )

    def _failure(
        self,
        context: CognitionRuntimeView,
        command: SubjectCommand,
        basis: ExperienceBasis,
        active: tuple[LivingMemoryRecord, ...],
        code: str,
    ) -> CognitiveProposal:
        base = self._bounded_noop_proposal(
            context=context,
            basis=basis,
            experience_summary="Living Memory 本轮失败关闭。",
            expression_candidate=ExpressionCandidate(
                text="（无记忆相关内容）",
                language=command.language,
            ),
        )
        return replace(
            base,
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
]
