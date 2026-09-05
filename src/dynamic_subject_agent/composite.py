"""Composite cognition: memory, knowledge, participant goals and stance.

Each sub-cognition keeps its own authorized provider projection and ModelGateway
task; no projection merging happens. A typed sub-cognition failure remains local.
Expression selection (Python-adjudicated): a proposed knowledge citation uses
the knowledge reply; otherwise the memory reply. The relationship sub-cognition
never speaks — it only contributes stance events.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from uuid import NAMESPACE_URL, uuid5

from dynamic_subject_agent.domains import CompleteDomainOutcomeSet, RelationshipChangeCandidate
from dynamic_subject_agent.knowledge_entries import (
    KnowledgeEntry,
    SEALED_KNOWLEDGE_ENTRIES,
    select_knowledge_candidates,
)
from dynamic_subject_agent.runtime import (
    CognitionEngine,
    CognitionFailedClosed,
    CognitionRuntimeView,
    CognitiveProposal,
    CyclePlan,
    ExperienceBasis,
    ExpressionCandidate,
)
from dynamic_subject_agent.relationship import RELATIONSHIP_POLICY_VERSION
from dynamic_subject_agent.participant_goal_cognition import (
    participant_record_query_kind, route_participant_goal_deterministically,
)
from dynamic_subject_agent.participant_goals import active_targets, participant_operation_requested
from dynamic_subject_agent.timeline import SubjectCommand
from dynamic_subject_agent.runtime_identity_reply import activity_boundary_reply
from dynamic_subject_agent.subject_time_continuity import (
    SubjectTimeStatus,
)

_COMPOSITE_ADAPTER_VERSION = "composite-cognition-1.0"
_NO_MEMORY_EXPRESSION = "（无记忆相关内容）"
_UNAVAILABLE_EXPRESSION = "抱歉，当前没有可用于回答这个问题的记忆或知识。"
_GENERAL_CONVERSATION_REPLY = (
    "可以。你可以从最近正在做的事、在意的问题，"
    "或者单纯想理清的一件事说起。"
)
_GENERAL_CONVERSATION_ENTRIES = frozenset(
    {
        "我们能聊些什么吗",
        "我们可以聊些什么",
        "你有什么希望和我聊的吗",
        "你想和我聊什么",
        "我们聊点什么",
    }
)
_CROSS_DOMAIN_UNAVAILABLE_MARKERS = (
    "没有相关信息",
    "没有这方面的信息",
    "没有记录",
    "目前没有",
    "不知道",
    "不清楚",
    "无法回答",
    "需要你告诉",
    "需要你提供",
)
_DIRECT_RELATIONSHIP_CLAIM_KINDS = {
    "我们现在已经是最好的朋友了吧": "best-friend",
    "我们已经是最好的朋友了吧": "best-friend",
    "我们现在是最好的朋友了吧": "best-friend",
    "我们是最好的朋友了吧": "best-friend",
    "我们现在已经是朋友了吧": "friend",
    "我们已经是朋友了吧": "friend",
    "我们现在是朋友了吧": "friend",
    "我们是朋友了吧": "friend",
    "我们的关系已经确定了吧": "defined",
    "我们的关系已经确定吗": "defined",
}
_DIRECT_RELATIONSHIP_CLAIM_REPLIES = {
    "best-friend": (
        "我还不会把我们直接定义成最好的朋友。"
        "关系要看我们之后怎样相处。"
    ),
    "friend": "我还不会直接替我们定义关系。关系要看我们之后怎样相处。",
    "defined": "我不会把我们的关系直接当成已经确定。还要看之后怎样相处。",
}


@dataclass(frozen=True)
class _DirectRelationshipClaim:
    kind: str
    clause: str


def _direct_relationship_claims(text: str) -> tuple[_DirectRelationshipClaim, ...]:
    claims: list[_DirectRelationshipClaim] = []
    for clause in re.split(r"[。！？!?；;\n]+", text):
        normalized = re.sub(r"\s+", "", clause).strip()
        kind = _DIRECT_RELATIONSHIP_CLAIM_KINDS.get(normalized)
        if kind is not None:
            claims.append(_DirectRelationshipClaim(kind, clause.strip()))
    return tuple(claims)


def _claim_reply(claims: tuple[_DirectRelationshipClaim, ...]) -> str:
    kind = (
        "best-friend"
        if any(claim.kind == "best-friend" for claim in claims)
        else claims[0].kind
    )
    return _DIRECT_RELATIONSHIP_CLAIM_REPLIES[kind]


def _evidence_overlaps_claim(
    evidence_quote: str,
    claims: tuple[_DirectRelationshipClaim, ...],
) -> bool:
    evidence = evidence_quote.strip().rstrip("。！？!?；;")
    return bool(
        evidence
        and any(
            evidence in claim.clause or claim.clause in evidence
            for claim in claims
        )
    )


def _is_general_conversation_entry(text: str) -> bool:
    normalized = re.sub(r"[\s。！？!?]+", "", text)
    return normalized in _GENERAL_CONVERSATION_ENTRIES


def _supported_clauses(text: str) -> str:
    clauses = re.findall(r"[^。！？!?]+[。！？!?]?", text)
    supported = [
        clause.strip()
        for clause in clauses
        if clause.strip()
        and not any(
            marker in clause for marker in _CROSS_DOMAIN_UNAVAILABLE_MARKERS
        )
    ]
    return "".join(supported)


def _merge_expression_text(base: str, addition: str, *, preserve_evidence: bool = False) -> str:
    if preserve_evidence:
        # Quoted source/memory text is opaque evidence, not free prose to prune
        # or approximately deduplicate. In particular, retain qualifications.
        return '\n\n'.join(dict.fromkeys(part for part in (base, addition) if part.strip()))
    supported_base = _supported_clauses(base)
    supported_addition = _supported_clauses(addition)
    if not supported_base and not supported_addition:
        return _UNAVAILABLE_EXPRESSION
    if not supported_base:
        return supported_addition
    if not supported_addition:
        return supported_base
    similarity = SequenceMatcher(
        None,
        supported_base,
        supported_addition,
    ).ratio()
    if similarity >= 0.75:
        return (
            supported_base
            if len(supported_base) >= len(supported_addition)
            else supported_addition
        )
    return f"{supported_base}\n\n{supported_addition}"


class ControlledCompositeCognition(CognitionEngine):
    """No-write cognition seam composing memory, knowledge and stance seams."""

    adapter_version = _COMPOSITE_ADAPTER_VERSION
    experimental = True
    test_only = True

    def __init__(
        self,
        *,
        memory_provider: object,
        knowledge_provider: object,
        relationship_provider: object,
        knowledge_entries: tuple[KnowledgeEntry, ...] = SEALED_KNOWLEDGE_ENTRIES,
        participant_goal_gateway: object | None = None,
        situated_gateway: object | None = None,
        medium_gateway: object | None = None,
    ) -> None:
        from dynamic_subject_agent.knowledge import ControlledKnowledgeCognition
        from dynamic_subject_agent.living_memory import (
            ControlledLivingMemoryCognition,
        )
        from dynamic_subject_agent.relationship import (
            ControlledRelationshipCognition,
        )

        self._memory = ControlledLivingMemoryCognition(
            provider=memory_provider,
        )
        if not isinstance(knowledge_entries, tuple) or any(
            not isinstance(entry, KnowledgeEntry) for entry in knowledge_entries
        ):
            raise TypeError("knowledge_entries must be sealed KnowledgeEntry values")
        self._knowledge_entries = knowledge_entries
        self._knowledge = ControlledKnowledgeCognition(
            provider=knowledge_provider,
            entries=knowledge_entries,
        )
        self._relationship = ControlledRelationshipCognition(
            provider=relationship_provider,
        )
        self._participant_goals = None
        if participant_goal_gateway is not None:
            from dynamic_subject_agent.participant_goal_cognition import (
                ControlledParticipantGoalCognition,
            )

            self._participant_goals = ControlledParticipantGoalCognition(
                gateway=participant_goal_gateway
            )
        self._situated = None
        if situated_gateway is not None:
            from dynamic_subject_agent.situated_cognition import (
                ControlledSituatedCognition,
            )

            self._situated = ControlledSituatedCognition(gateway=situated_gateway)
        self._medium = None
        if medium_gateway is not None:
            from dynamic_subject_agent.medium_cognition import ControlledMediumCognition

            self._medium = ControlledMediumCognition(gateway=medium_gateway)
        authorities = {
            self._memory.provider_authority,
            self._knowledge.provider_authority,
            self._relationship.provider_authority,
        }
        if self._participant_goals is not None:
            authorities.add(self._participant_goals.provider_authority)
        if self._situated is not None:
            authorities.add(self._situated.provider_authority)
        if self._medium is not None:
            authorities.add(self._medium.provider_authority)
        if len(authorities) != 1:
            raise TypeError(
                "composite providers must share one provider authority"
            )
        self.provider_authority = next(iter(authorities))
        self.test_only = all(
            bool(getattr(sub, "test_only", True))
            for sub in (
                self._memory,
                self._knowledge,
                self._relationship,
                self._participant_goals,
                self._situated,
                self._medium,
            )
            if sub is not None
        )

    def propose(
        self,
        *,
        plan: CyclePlan,
        context: CognitionRuntimeView,
        command,
        basis: ExperienceBasis,
    ) -> CognitiveProposal:
        subject_time = context.subject_time_result
        if subject_time.status is SubjectTimeStatus.FAILED_CLOSED:
            raise CognitionFailedClosed(
                "subject-time",
                subject_time.problem_code or "subject-time-failed-closed",
                "canonical Interaction Recency could not be safely derived",
            )
        if subject_time.status is SubjectTimeStatus.ANSWER:
            if subject_time.answer is None:
                raise CognitionFailedClosed(
                    "subject-time",
                    "subject-time-result-invalid",
                    "typed Subject Time answer is absent",
                )
            return self._bounded_noop_proposal(
                context=context,
                basis=basis,
                experience_summary="本轮以 canonical Subject Time 回答明确查询。",
                expression_candidate=ExpressionCandidate(
                    subject_time.answer.text,
                    command.language,
                ),
            )
        memory_proposal = self._propose_sub(self._memory, plan, context, command, basis)
        knowledge_hit = bool(
            select_knowledge_candidates(
                command.utterance,
                self._knowledge_entries,
            )
        )
        knowledge_proposal = (
            self._propose_sub(self._knowledge, plan, context, command, basis)
            if knowledge_hit
            else None
        )
        relationship_proposal = self._propose_sub(
            self._relationship,
            plan,
            context,
            command,
            basis,
        )
        participant_goal_proposal = (
            self._propose_sub(
                self._participant_goals,
                plan,
                context,
                command,
                basis,
            )
            if self._participant_goals is not None
            else None
        )
        situated_proposal = (
            self._propose_sub(
                self._situated,
                plan,
                context,
                command,
                basis,
            )
            if self._situated is not None
            else None
        )
        medium_proposal = (
            self._propose_sub(
                self._medium,
                plan,
                context,
                command,
                basis,
            )
            if self._medium is not None
            else None
        )

        experience_request = memory_proposal.impact_envelope.experience
        relationship_request = relationship_proposal.impact_envelope.relationship
        relationship_event = (
            relationship_request.candidates[0].event
            if relationship_request.candidates
            else ""
        )
        participant_goal_relevant = False
        participant_goal_expression_priority = False
        participant_goal_selection_priority = False
        participant_goal_mutation = False
        if participant_goal_proposal is not None:
            participant_request = participant_goal_proposal.impact_envelope.experience
            participant_goal_relevant = bool(
                participant_request.candidates
                or participant_request.selected_participant_goal_record_ids
            )
            participant_goal_expression_priority = (
                participant_request.participant_goal_expression_priority
            )
            participant_goal_mutation = bool(participant_request.candidates)
            participant_goal_selection_priority = bool(
                participant_record_query_kind(command.utterance) is not None
                and participant_goal_expression_priority
            )
            experience_request = replace(
                experience_request,
                current_state=replace(
                    experience_request.current_state,
                    participant_goal_commitments=(
                        participant_request.current_state.participant_goal_commitments
                    ),
                ),
                candidates=(
                    (() if participant_goal_selection_priority else experience_request.candidates)
                    + participant_request.candidates
                ),
                living_memory_failure_code=(
                    None
                    if participant_goal_selection_priority
                    else experience_request.living_memory_failure_code
                ),
                selected_participant_goal_record_ids=(
                    participant_request.selected_participant_goal_record_ids
                ),
                participant_goal_failure_code=(
                    participant_request.participant_goal_failure_code
                ),
                participant_goal_expression_priority=(
                    participant_goal_expression_priority
                ),
            )
        relationship_claims = _direct_relationship_claims(command.utterance)
        relationship_claimed = bool(relationship_claims)
        if relationship_event == "relationship_claim" and not relationship_claims:
            relationship_claims = (
                _DirectRelationshipClaim("defined", command.utterance.strip()),
            )
        relationship_claim_protected = bool(relationship_claims)
        if relationship_claimed and relationship_request.failure_code is None:
            relationship_request = replace(
                relationship_request,
                candidates=(
                    RelationshipChangeCandidate(
                        candidate_id=str(
                            uuid5(
                                NAMESPACE_URL,
                                "relationship-direct-claim:"
                                f"{basis.operation_id}",
                            )
                        ),
                        relationship_target_id=context.profile_id,
                        evidence_refs=(basis.operation_id,),
                        event="relationship_claim",
                        evidence_quote=relationship_claims[0].clause,
                        source_user_message_id=basis.operation_id,
                        policy_version=RELATIONSHIP_POLICY_VERSION,
                    ),
                ),
            )
            relationship_event = "relationship_claim"
        if relationship_claim_protected:
            experience_request = replace(
                experience_request,
                candidates=tuple(
                    candidate
                    for candidate in experience_request.candidates
                    if not (
                        candidate.memory_action is not None
                        and _evidence_overlaps_claim(
                            candidate.evidence_quote,
                            relationship_claims,
                        )
                    )
                ),
            )
            memory_proposal = replace(
                memory_proposal,
                experience_summary=(
                    "用户单方面声称关系；Python 保持关系与记忆均不变。"
                ),
                expression_candidate=ExpressionCandidate(
                    text=_claim_reply(relationship_claims),
                    language=memory_proposal.expression_candidate.language,
                ),
            )
        if knowledge_proposal is not None and not participant_goal_selection_priority:
            knowledge_request = knowledge_proposal.impact_envelope.experience
            experience_request = replace(
                experience_request,
                candidates=(
                    experience_request.candidates + knowledge_request.candidates
                ),
                knowledge_candidates=knowledge_request.knowledge_candidates,
                knowledge_failure_code=knowledge_request.knowledge_failure_code,
            )
        subject_state_request = (
            situated_proposal.impact_envelope.subject_state
            if situated_proposal is not None
            else memory_proposal.impact_envelope.subject_state
        )
        if medium_proposal is not None:
            medium_request = medium_proposal.impact_envelope.subject_state
            subject_state_request = replace(
                subject_state_request,
                current_state=replace(
                    subject_state_request.current_state,
                    medium_state=medium_request.current_state.medium_state,
                    medium_signals=medium_request.current_state.medium_signals,
                ),
                medium_candidates=medium_request.medium_candidates,
                medium_failure_code=medium_request.medium_failure_code,
                medium_expression_active=medium_request.medium_expression_active,
                medium_expression_priority=medium_request.medium_expression_priority,
                current_user_message=medium_request.current_user_message,
                source_user_message_id=medium_request.source_user_message_id,
                observed_at_us=medium_request.observed_at_us,
                current_head_sequence=medium_request.current_head_sequence,
            )
        envelope = replace(
            memory_proposal.impact_envelope,
            experience=experience_request,
            subject_state=subject_state_request,
            relationship=relationship_request,
        )

        knowledge_cited = bool(
            not participant_goal_selection_priority
            and knowledge_proposal is not None
            and any(
                candidate.knowledge_citation_ids
                for candidate in knowledge_proposal.impact_envelope.experience.candidates
            )
        )
        memory_recalled = any(
            candidate.recalled_memory_ids
            for candidate in experience_request.candidates
        ) and not participant_goal_selection_priority
        memory_changed = any(
            candidate.memory_action in {"create", "revise"}
            for candidate in experience_request.candidates
        ) and not participant_goal_selection_priority
        memory_relevant = memory_recalled or memory_changed
        if knowledge_cited and memory_relevant:
            memory_text = memory_proposal.expression_candidate.text
            if not memory_proposal.expression_candidate.is_creative:
                recalled_ids = {memory_id for candidate in experience_request.candidates for memory_id in candidate.recalled_memory_ids}
                facts = [f'你之前说的是：「{item.content}」' for item in context.active_memories if item.memory_id in recalled_ids]
                if memory_changed:
                    facts.append(f'你这次说的是：「{command.utterance}」' if len(command.utterance) <= 800
                        else '本轮记忆处理的结果会在说明中列出。')
                memory_text = '\n\n'.join(facts)
            expression = ExpressionCandidate(
                text=_merge_expression_text(
                    memory_text,
                    knowledge_proposal.expression_candidate.text,
                    preserve_evidence=True,
                ),
                language=memory_proposal.expression_candidate.language,
            )
        else:
            expression = (
                knowledge_proposal.expression_candidate
                if knowledge_cited
                else memory_proposal.expression_candidate
            )
        if participant_goal_relevant and participant_goal_proposal is not None:
            goal_text = _supported_clauses(
                participant_goal_proposal.expression_candidate.text
            )
            if knowledge_cited or memory_relevant:
                if not participant_goal_mutation:
                    expression = ExpressionCandidate(
                        text=(
                            _merge_expression_text(goal_text, expression.text, preserve_evidence=knowledge_cited)
                            if participant_goal_expression_priority
                            else _merge_expression_text(expression.text, goal_text, preserve_evidence=knowledge_cited)
                        ),
                        language=expression.language,
                    )
            else:
                expression = participant_goal_proposal.expression_candidate
        situated_active = bool(
            situated_proposal is not None
            and situated_proposal.impact_envelope.subject_state.situated_expression_active
        )
        situated_priority = bool(
            situated_proposal is not None
            and situated_proposal.impact_envelope.subject_state.situated_expression_priority
        )
        medium_active = bool(
            medium_proposal is not None
            and medium_proposal.impact_envelope.subject_state.medium_expression_active
        )
        medium_priority = bool(
            medium_proposal is not None
            and medium_proposal.impact_envelope.subject_state.medium_expression_priority
        )
        non_state_relevant = bool(
            knowledge_cited
            or memory_relevant
            or participant_goal_relevant
            or relationship_claim_protected
        )
        situated_should_speak = situated_active and (
            situated_priority or not non_state_relevant
        ) and not (medium_priority and not situated_priority)
        medium_should_speak = medium_active and (
            (medium_priority and not situated_priority)
            or (not non_state_relevant and not situated_should_speak)
        )
        if situated_should_speak and situated_proposal is not None:
            situated_text = _supported_clauses(
                situated_proposal.expression_candidate.text
            )
            if knowledge_cited or memory_relevant or participant_goal_relevant:
                expression = ExpressionCandidate(
                    text=_merge_expression_text(expression.text, situated_text, preserve_evidence=knowledge_cited),
                    language=expression.language,
                )
            else:
                expression = situated_proposal.expression_candidate
        if medium_should_speak and medium_proposal is not None:
            medium_text = _supported_clauses(medium_proposal.expression_candidate.text)
            if (
                knowledge_cited
                or memory_relevant
                or participant_goal_relevant
                or situated_should_speak
            ):
                expression = ExpressionCandidate(
                    text=_merge_expression_text(expression.text, medium_text, preserve_evidence=knowledge_cited),
                    language=expression.language,
                )
            else:
                expression = medium_proposal.expression_candidate
        if relationship_claim_protected:
            expression = ExpressionCandidate(
                text=_merge_expression_text(
                    _claim_reply(relationship_claims),
                    expression.text,
                    preserve_evidence=knowledge_cited,
                ),
                language=expression.language,
            )
        if expression.text == _NO_MEMORY_EXPRESSION:
            expression = ExpressionCandidate(
                text=(
                    _GENERAL_CONVERSATION_REPLY
                    if _is_general_conversation_entry(command.utterance)
                    else _UNAVAILABLE_EXPRESSION
                ),
                language=expression.language,
            )
        summary = (
            participant_goal_proposal.experience_summary
            if participant_goal_selection_priority
            and participant_goal_proposal is not None
            else (
                knowledge_proposal.experience_summary
                if knowledge_cited and knowledge_proposal.experience_summary.strip()
                else memory_proposal.experience_summary
            )
        ) or memory_proposal.expression_candidate.text
        return CognitiveProposal(
            adapter_version=self.adapter_version,
            experience_summary=summary,
            epistemic_outcome=memory_proposal.epistemic_outcome,
            impact_envelope=envelope,
            expression_candidate=expression,
        )

    def express(
        self, *, proposal: CognitiveProposal, context: CognitionRuntimeView,
        command: SubjectCommand, outcomes: CompleteDomainOutcomeSet,
    ) -> ExpressionCandidate:
        """Confirm goal operations only after the authoritative Domain decision."""
        if self._participant_goals is None:
            return self._grounded_primary(proposal, command)
        outcome = outcomes.experience
        status = outcome.participant_goal_commitment_status
        action = outcome.participant_goal_commitment_action
        requested = participant_operation_requested(command.utterance)
        text = None
        if status == 'failed-closed' and requested:
            text = '这次没能完成目标或承诺的处理，原有记录保持不变。'
        elif status == 'rejected' and requested:
            reason = outcome.participant_goal_commitment_reason_code
            text = {
                'unknown_target_ref': '没有找到要修改的已记录目标或承诺，这次没有更改。',
                'ambiguous_target_evidence': '还不能确定你要修改哪一条目标或承诺，这次没有更改。',
                'duplicate_active_record': '这项目标或承诺已经记录过了，没有重复保存。',
                'conflicting_operation_intent': '这条消息包含多个操作或撤回了保存意图，这次没有更改目标与承诺。请一次确认一项操作。',
            }.get(reason, '这次没有保存或修改目标与承诺，请明确说明要记录或修改的内容。')
        elif participant_record_query_kind(command.utterance) is not None:
            query = route_participant_goal_deterministically(
                command.utterance, targets=active_targets(context.participant_goal_commitments),
            )
            return ExpressionCandidate(query.reply_text, command.language)
        elif status == 'accepted':
            noun = '目标' if outcome.participant_goal_commitment_kind == 'goal' else '承诺'
            terms = outcome.participant_goal_commitment_terms
            if action in {'create', 'revise'} and terms:
                verb = '记录' if action == 'create' else '修改'
                text = f'已{verb}你的{noun}：「{terms}」。'
            elif action == 'transition':
                label = {'achieved': '已达成', 'abandoned': '已放弃',
                         'fulfilled': '已履行', 'released': '已解除'}.get(
                    outcome.participant_goal_commitment_next_status, '已更新',
                )
                text = f'已按你的说明，将这项{noun}标为“{label}”。'
        elif requested and status in {None, 'no-update'}:
            text = '这次没有新增或修改目标与承诺。请明确说明你的目标、承诺或要修改的记录。'
        if text is not None:
            if status != 'accepted' and outcome.living_memory_status.value == 'accepted':
                text += '你的这段话已作为记忆保留，但目标与承诺列表没有更新。'
            independent = []
            if outcome.knowledge_status == 'accepted':
                cited = set(outcome.knowledge_citation_ids)
                independent.extend(
                    f'根据条目《{entry.title}》：{entry.content}'
                    for entry in self._knowledge_entries if entry.entry_id in cited
                )
            if status == 'accepted' and outcome.living_memory_status.value == 'accepted':
                content = outcome.living_memory_content
                if isinstance(content, str) and not any(word in content for word in ('目标', '承诺')):
                    independent.append(f'我记下了：「{content}」。')
            claims = _direct_relationship_claims(command.utterance)
            if claims and outcomes.relationship.relationship_status == 'no-update':
                independent.append(_claim_reply(claims))
            text = '\n\n'.join((*independent, text))
            return ExpressionCandidate(text, command.language)
        return self._grounded_primary(proposal, command)

    @staticmethod
    def _grounded_primary(proposal: CognitiveProposal, command: SubjectCommand) -> ExpressionCandidate:
        activity = activity_boundary_reply(command.utterance)
        if activity is not None:
            return ExpressionCandidate(activity, command.language)
        return proposal.expression_candidate

    def _propose_sub(
        self,
        sub: CognitionEngine,
        plan: CyclePlan,
        context: CognitionRuntimeView,
        command,
        basis: ExperienceBasis,
    ) -> CognitiveProposal:
        try:
            return sub.propose(plan=plan, context=context, command=command, basis=basis)
        except CognitionFailedClosed:
            raise
        except Exception as error:
            raise CognitionFailedClosed(
                "provider",
                "composite-sub-cognition-failed",
                f"{type(sub).__name__} failed outside its bounded failure type",
            ) from error


__all__ = ["ControlledCompositeCognition"]
