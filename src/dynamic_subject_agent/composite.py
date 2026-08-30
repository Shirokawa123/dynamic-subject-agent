"""Composite cognition: memory, knowledge, participant goals and stance.

Each sub-cognition keeps its own authorized provider projection; no projection
merging happens. Any sub-cognition failure fails the whole turn closed.
Expression selection (Python-adjudicated): a proposed knowledge citation uses
the knowledge reply; otherwise the memory reply. The relationship sub-cognition
never speaks — it only contributes stance events.
"""

from __future__ import annotations

import re
from dataclasses import replace

from dynamic_subject_agent.knowledge_entries import select_knowledge_candidates
from dynamic_subject_agent.runtime import (
    CognitionEngine,
    CognitionFailedClosed,
    CognitionRuntimeView,
    CognitiveProposal,
    CyclePlan,
    ExperienceBasis,
    ExpressionCandidate,
)

_COMPOSITE_ADAPTER_VERSION = "composite-cognition-1.0"
_NO_MEMORY_EXPRESSION = "（无记忆相关内容）"
_UNAVAILABLE_EXPRESSION = "抱歉，当前没有可用于回答这个问题的记忆或知识。"
_CROSS_DOMAIN_UNAVAILABLE_MARKERS = (
    "没有相关信息",
    "没有这方面的信息",
    "目前没有",
    "不知道",
    "不清楚",
    "无法回答",
    "需要你告诉",
    "需要你提供",
)


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
    return "".join(supported) or text


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
        participant_goal_gateway: object | None = None,
    ) -> None:
        from dynamic_subject_agent.knowledge import ControlledKnowledgeCognition
        from dynamic_subject_agent.living_memory import (
            ControlledLivingMemoryCognition,
        )
        from dynamic_subject_agent.relationship import (
            ControlledRelationshipCognition,
        )

        self._memory = ControlledLivingMemoryCognition(provider=memory_provider)
        self._knowledge = ControlledKnowledgeCognition(provider=knowledge_provider)
        self._relationship = ControlledRelationshipCognition(
            provider=relationship_provider
        )
        self._participant_goals = None
        if participant_goal_gateway is not None:
            from dynamic_subject_agent.participant_goal_cognition import (
                ControlledParticipantGoalCognition,
            )

            self._participant_goals = ControlledParticipantGoalCognition(
                gateway=participant_goal_gateway
            )
        authorities = {
            self._memory.provider_authority,
            self._knowledge.provider_authority,
            self._relationship.provider_authority,
        }
        if self._participant_goals is not None:
            authorities.add(self._participant_goals.provider_authority)
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
        memory_proposal = self._propose_sub(self._memory, plan, context, command, basis)
        knowledge_hit = bool(
            select_knowledge_candidates(command.utterance)
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

        experience_request = memory_proposal.impact_envelope.experience
        relationship_request = relationship_proposal.impact_envelope.relationship
        relationship_event = (
            relationship_request.candidates[0].event
            if relationship_request.candidates
            else ""
        )
        participant_goal_relevant = False
        participant_goal_expression_priority = False
        if participant_goal_proposal is not None:
            participant_request = participant_goal_proposal.impact_envelope.experience
            participant_goal_relevant = bool(
                participant_request.candidates
                or participant_request.selected_participant_goal_record_ids
            )
            participant_goal_expression_priority = (
                participant_request.participant_goal_expression_priority
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
                    experience_request.candidates + participant_request.candidates
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
        if relationship_event == "relationship_claim":
            experience_request = replace(
                experience_request,
                candidates=(),
                selected_participant_goal_record_ids=(),
                participant_goal_failure_code=None,
                participant_goal_expression_priority=False,
            )
            participant_goal_relevant = False
            participant_goal_expression_priority = False
            memory_proposal = replace(
                memory_proposal,
                experience_summary=(
                    "用户单方面声称关系；Python 保持关系与记忆均不变。"
                ),
                expression_candidate=ExpressionCandidate(
                    text=(
                        "我会根据我们之后真实发生的互动理解关系，"
                        "不会因为一句声称直接把关系写成既定事实。"
                    ),
                    language=memory_proposal.expression_candidate.language,
                ),
            )
        if knowledge_proposal is not None:
            knowledge_request = knowledge_proposal.impact_envelope.experience
            experience_request = replace(
                experience_request,
                candidates=(
                    experience_request.candidates + knowledge_request.candidates
                ),
                knowledge_candidates=knowledge_request.knowledge_candidates,
            )
        envelope = replace(
            memory_proposal.impact_envelope,
            experience=experience_request,
            relationship=relationship_proposal.impact_envelope.relationship,
        )

        knowledge_cited = bool(
            experience_request.candidates
            and experience_request.candidates[-1].knowledge_citation_ids
            and knowledge_proposal is not None
        )
        memory_recalled = any(
            candidate.recalled_memory_ids
            for candidate in experience_request.candidates
        )
        if knowledge_cited and memory_recalled:
            expression = ExpressionCandidate(
                text=(
                    f"{_supported_clauses(memory_proposal.expression_candidate.text)}\n\n"
                    f"{_supported_clauses(knowledge_proposal.expression_candidate.text)}"
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
            if participant_goal_expression_priority:
                expression = participant_goal_proposal.expression_candidate
            elif knowledge_cited or memory_recalled:
                expression = ExpressionCandidate(
                    text=f"{_supported_clauses(expression.text)}\n\n{goal_text}",
                    language=expression.language,
                )
            else:
                expression = participant_goal_proposal.expression_candidate
        if expression.text == _NO_MEMORY_EXPRESSION:
            expression = ExpressionCandidate(
                text=_UNAVAILABLE_EXPRESSION,
                language=expression.language,
            )
        summary = (
            knowledge_proposal.experience_summary
            if knowledge_cited and knowledge_proposal.experience_summary.strip()
            else memory_proposal.experience_summary
        ) or memory_proposal.expression_candidate.text
        return CognitiveProposal(
            adapter_version=self.adapter_version,
            experience_summary=summary,
            epistemic_outcome=memory_proposal.epistemic_outcome,
            impact_envelope=envelope,
            expression_candidate=expression,
        )

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
