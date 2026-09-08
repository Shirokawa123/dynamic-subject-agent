"""Experience Domain: epistemic lineage, memory encoding and knowledge citation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

from dynamic_subject_agent.timeline import (
    CandidateDecisionRecord,
    DecisionStatus,
    ExperienceDomainOutcome,
    LivingMemoryDecisionStatus,
    LivingMemoryRecord,
)
from dynamic_subject_agent.domains._shared import (
    DomainAdjudicationFailedClosed,
    DomainCapabilityState,
    ExperienceBasis,
    noop_decision,
    require_tuple,
    stable_id,
    validate_basis,
)
from dynamic_subject_agent.knowledge_entries import KnowledgeEntry
from dynamic_subject_agent.participant_goals import (
    MAX_TERMS_CHARS,
    POLICY_HASH as PARTICIPANT_GOAL_POLICY_HASH,
    POLICY_ID as PARTICIPANT_GOAL_POLICY_ID,
    POLICY_VERSION as PARTICIPANT_GOAL_POLICY_VERSION,
    ParticipantGoalCommitmentCandidate,
    ParticipantGoalCommitmentEngine,
    ParticipantGoalCommitmentRecord,
    active_targets,
)
from dynamic_subject_agent.temporal_grounding import TemporalGrounding
from dynamic_subject_agent.memory_control import MemoryWithdrawal, select_memory_withdrawal


@dataclass(frozen=True)
class ExperienceChangeCandidate:
    candidate_id: str
    target_experience_id: str
    evidence_refs: tuple[str, ...]
    memory_action: str | None = None
    evidence_quote: str = ""
    supersedes_memory_id: str | None = None
    recalled_memory_ids: tuple[str, ...] = ()
    knowledge_citation_ids: tuple[str, ...] = ()
    memory_kind: str = "durable"
    participant_goal_candidate: ParticipantGoalCommitmentCandidate | None = None


@dataclass(frozen=True)
class ExperienceReadView:
    verified_prefix_digest: str
    memory_trace_refs: tuple[str, ...]
    active_memories: tuple[LivingMemoryRecord, ...] = ()
    participant_goal_commitments: tuple[ParticipantGoalCommitmentRecord, ...] = ()


@dataclass(frozen=True)
class ExperienceAdjudicationRequest:
    basis: ExperienceBasis
    current_state: ExperienceReadView
    candidates: tuple[ExperienceChangeCandidate, ...]
    current_user_message: str = ""
    source_user_message_id: str = ""
    knowledge_candidates: tuple[KnowledgeEntry, ...] = ()
    selected_participant_goal_record_ids: tuple[str, ...] = ()
    living_memory_failure_code: str | None = None
    knowledge_failure_code: str | None = None
    participant_goal_failure_code: str | None = None
    participant_goal_expression_priority: bool = False
    memory_withdrawal: MemoryWithdrawal | None = None


class ExperienceDomain:
    """Adjudicate the Experience-owned slice without acquiring write authority."""

    material_change_capability = DomainCapabilityState.AVAILABLE

    def adjudicate(
        self,
        request: ExperienceAdjudicationRequest,
    ) -> ExperienceDomainOutcome:
        if not isinstance(request, ExperienceAdjudicationRequest):
            raise DomainAdjudicationFailedClosed(
                "experience",
                "wrong-domain-request",
                "ExperienceDomain requires ExperienceAdjudicationRequest",
            )
        basis = validate_basis(request.basis, domain="experience")
        if not isinstance(request.current_state, ExperienceReadView):
            raise DomainAdjudicationFailedClosed(
                "experience",
                "invalid-read-view",
                "Experience current state must be a typed read-only view",
            )
        if request.current_state.verified_prefix_digest != basis.verified_prefix_digest:
            raise DomainAdjudicationFailedClosed(
                "experience",
                "verified-prefix-mismatch",
                "Experience read view does not match the shared verified prefix",
            )
        candidates = require_tuple(
            request.candidates,
            domain="experience",
            field="candidates",
        )
        memory_candidate: ExperienceChangeCandidate | None = None
        knowledge_candidate: ExperienceChangeCandidate | None = None
        participant_goal_candidate: ExperienceChangeCandidate | None = None
        for candidate in candidates:
            if not isinstance(candidate, ExperienceChangeCandidate):
                raise DomainAdjudicationFailedClosed(
                    "experience",
                    "wrong-domain-candidate",
                    "only ExperienceChangeCandidate may enter ExperienceDomain",
                )
            if candidate.target_experience_id != basis.experience_id:
                raise DomainAdjudicationFailedClosed(
                    "experience",
                    "candidate-target-mismatch",
                    "Experience candidate names a different Experience",
                )
            is_memory = candidate.memory_action is not None
            is_knowledge = (
                candidate.memory_action is None
                and bool(candidate.knowledge_citation_ids)
                and candidate.participant_goal_candidate is None
            )
            is_participant_goal = candidate.participant_goal_candidate is not None
            if sum(bool(value) for value in (is_memory, is_knowledge, is_participant_goal)) != 1:
                raise DomainAdjudicationFailedClosed(
                    "experience",
                    "mixed-kind-candidate",
                    "one candidate must carry exactly one Experience change kind",
                )
            if is_memory:
                if memory_candidate is not None:
                    raise DomainAdjudicationFailedClosed(
                        "experience",
                        "multiple-living-memory-candidates",
                        "one turn may propose at most one Living Memory change",
                    )
                memory_candidate = candidate
            elif is_knowledge:
                if knowledge_candidate is not None:
                    raise DomainAdjudicationFailedClosed(
                        "experience",
                        "multiple-knowledge-candidates",
                        "one turn may propose at most one knowledge citation",
                    )
                knowledge_candidate = candidate
            elif is_participant_goal:
                if participant_goal_candidate is not None:
                    raise DomainAdjudicationFailedClosed(
                        "experience",
                        "multiple-participant-goal-candidates",
                        "one turn may propose at most one participant goal change",
                    )
                participant_goal_candidate = candidate
            else:
                raise DomainAdjudicationFailedClosed(
                    "experience",
                    "material-change-capability-unavailable",
                    "only current Experience capabilities are available",
                )
        participant_records = require_tuple(
            request.current_state.participant_goal_commitments,
            domain="experience",
            field="participant_goal_commitments",
        )
        if any(
            not isinstance(record, ParticipantGoalCommitmentRecord)
            for record in participant_records
        ):
            raise DomainAdjudicationFailedClosed(
                "experience",
                "invalid-participant-goal-read-view",
                "participant goals must be typed records",
            )
        for record in participant_records:
            try:
                UUID(record.record_id)
                UUID(record.source_user_message_id)
            except (AttributeError, TypeError, ValueError):
                raise DomainAdjudicationFailedClosed(
                    "experience",
                    "participant-goal-read-identity-invalid",
                    "participant goal read records require canonical identities",
                ) from None
            if (
                record.kind not in {"goal", "commitment"}
                or record.status != "active"
                or not record.terms.strip()
                or len(record.terms) > MAX_TERMS_CHARS
                or record.policy_id != PARTICIPANT_GOAL_POLICY_ID
                or record.policy_version != PARTICIPANT_GOAL_POLICY_VERSION
                or record.policy_hash != PARTICIPANT_GOAL_POLICY_HASH
            ):
                raise DomainAdjudicationFailedClosed(
                    "experience",
                    "participant-goal-read-record-invalid",
                    "participant goal read records violate current policy",
                )
        selected_ids = require_tuple(
            request.selected_participant_goal_record_ids,
            domain="experience",
            field="selected_participant_goal_record_ids",
        )
        active_record_ids = {
            record.record_id for record in participant_records if record.status == "active"
        }
        if (
            len(selected_ids) > 5
            or len(set(selected_ids)) != len(selected_ids)
            or any(record_id not in active_record_ids for record_id in selected_ids)
        ):
            raise DomainAdjudicationFailedClosed(
                "experience",
                "participant-goal-selection-invalid",
                "reply selection must name at most five active records",
            )
        participant_goal_failure = request.participant_goal_failure_code
        living_memory_failure = request.living_memory_failure_code
        knowledge_failure = request.knowledge_failure_code
        if living_memory_failure is not None and (
            living_memory_failure
            not in {
                "living-memory-provider-failed",
                "living-memory-provider-invalid-output",
            }
            or memory_candidate is not None
        ):
            raise DomainAdjudicationFailedClosed(
                "experience",
                "living-memory-failure-invalid",
                "Living Memory failure must be typed and carry no memory candidate",
            )
        if knowledge_failure is not None and (
            knowledge_failure
            not in {
                "knowledge-provider-failed",
                "knowledge-provider-invalid-output",
            }
            or knowledge_candidate is not None
        ):
            raise DomainAdjudicationFailedClosed(
                "experience",
                "knowledge-failure-invalid",
                "Knowledge failure must be typed and carry no knowledge candidate",
            )
        if not isinstance(request.participant_goal_expression_priority, bool):
            raise DomainAdjudicationFailedClosed(
                "experience",
                "participant-goal-expression-priority-invalid",
                "participant goal expression priority must be bool",
            )
        if participant_goal_failure is not None and (
            not isinstance(participant_goal_failure, str)
            or participant_goal_failure
            not in {
                "participant-goal-classification-failed",
                "participant-goal-classification-invalid",
                "participant-goal-selection-invalid",
                "participant-goal-reply-failed",
                "participant-goal-reply-invalid",
            }
            or participant_goal_candidate is not None
            or selected_ids
        ):
            raise DomainAdjudicationFailedClosed(
                "experience",
                "participant-goal-failure-invalid",
                "participant goal failure must be typed and carry no candidate",
            )
        if (
            memory_candidate is None
            and request.memory_withdrawal is None
            and knowledge_candidate is None
            and participant_goal_candidate is None
            and living_memory_failure is None
            and knowledge_failure is None
            and participant_goal_failure is None
            and not selected_ids
        ):
            return ExperienceDomainOutcome(
                outcome_id=stable_id(basis, "experience-outcome"),
                decision=noop_decision(
                    basis,
                    scope="experience",
                    reason_code="experience.no-applicable-candidate",
                ),
                epistemic_outcome_id=basis.epistemic_outcome_id,
            )
        active_memories = require_tuple(
            request.current_state.active_memories,
            domain="experience",
            field="active_memories",
        )
        if any(
            not isinstance(memory, LivingMemoryRecord)
            or memory.status != "active"
            for memory in active_memories
        ):
            raise DomainAdjudicationFailedClosed(
                "experience",
                "invalid-living-memory-read-view",
                "Living Memory read view must contain active typed records",
            )
        memory_code: str | None = None
        memory_payload: dict[str, object] | None = None
        if request.memory_withdrawal is not None:
            if memory_candidate is not None or living_memory_failure is not None:
                raise DomainAdjudicationFailedClosed('experience', 'mixed-memory-control', 'withdrawal must be independent of memory proposals')
            selected = select_memory_withdrawal(request.current_user_message, tuple(active_memories))
            if (not isinstance(request.memory_withdrawal, MemoryWithdrawal)
                or selected != request.memory_withdrawal
                or request.source_user_message_id != basis.operation_id):
                raise DomainAdjudicationFailedClosed('experience', 'invalid-memory-control', 'withdrawal does not match the admitted command')
            accepted = selected.target_memory_id is not None
            if accepted:
                try:
                    UUID(selected.target_memory_id)
                except (ValueError, TypeError, AttributeError):
                    raise DomainAdjudicationFailedClosed('experience', 'invalid-memory-target', 'withdrawal target must be canonical') from None
            memory_code = 'living-memory.forgotten' if accepted else 'living-memory.withdrawal-rejected'
            memory_payload = {'status': 'accepted' if accepted else 'rejected', 'action': 'forget',
                'target_memory_id': selected.target_memory_id, 'reason_code': selected.reason_code,
                'source_user_message_id': request.source_user_message_id}
        elif memory_candidate is not None:
            memory_code, memory_payload = self._living_memory_fragment(
                basis,
                request,
                memory_candidate,
                tuple(active_memories),
            )
        elif living_memory_failure is not None:
            memory_code = living_memory_failure
            memory_payload = {
                "status": "failed-closed",
                "action": "noop",
                "reason_code": living_memory_failure,
                "recalled_memory_ids": [],
            }
        knowledge_code: str | None = None
        knowledge_payload: dict[str, object] | None = None
        if knowledge_candidate is not None:
            knowledge_code, knowledge_payload = self._knowledge_fragment(
                basis,
                request,
                knowledge_candidate,
            )
        elif knowledge_failure is not None:
            knowledge_code = knowledge_failure
            knowledge_payload = {
                "status": "failed-closed",
                "action": "noop",
                "reason_code": knowledge_failure,
                "cited_entry_ids": [],
            }
        participant_goal_code: str | None = None
        participant_goal_payload: dict[str, object] | None = None
        if participant_goal_candidate is not None:
            participant_goal_code, participant_goal_payload = (
                self._participant_goal_fragment(
                    basis,
                    request,
                    participant_goal_candidate,
                    tuple(participant_records),
                )
            )
        elif participant_goal_failure is not None:
            participant_goal_code = participant_goal_failure
            participant_goal_payload = {
                "status": "failed-closed",
                "action": "noop",
                "reason_code": participant_goal_failure,
            }
        elif selected_ids:
            participant_goal_code = "participant-goal.selected-for-reply"
            participant_goal_payload = {
                "status": "no-update",
                "action": "noop",
                "reason_code": "selected_for_reply",
                "selected_count": len(selected_ids),
            }
        reason: dict[str, object] = {
            "code": (
                memory_code
                or knowledge_code
                or participant_goal_code
                or "experience.accepted"
            ),
            "provenance": basis.source_provenance,
        }
        if memory_payload is not None:
            reason["living_memory"] = memory_payload
        if knowledge_payload is not None:
            reason["knowledge"] = knowledge_payload
        if participant_goal_payload is not None:
            reason["participant_goal_commitment"] = participant_goal_payload
        decision = CandidateDecisionRecord(
            decision_id=stable_id(basis, "experience-decision"),
            scope="experience",
            status=DecisionStatus.NO_OP,
            reason=json.dumps(
                reason,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            rule_version="experience-1.0",
            actual_revision_ids=(),
        )
        return ExperienceDomainOutcome(
            outcome_id=stable_id(basis, "experience-outcome"),
            decision=decision,
            epistemic_outcome_id=basis.epistemic_outcome_id,
        )

    def _living_memory_fragment(
        self,
        basis: ExperienceBasis,
        request: ExperienceAdjudicationRequest,
        candidate: ExperienceChangeCandidate,
        active_memories: tuple[LivingMemoryRecord, ...],
    ) -> tuple[str, dict[str, object] | None]:
        rejection_code: str | None = None
        try:
            UUID(candidate.candidate_id)
            UUID(request.source_user_message_id)
        except (AttributeError, TypeError, ValueError):
            rejection_code = "living-memory.identity-invalid"
        if request.source_user_message_id != basis.operation_id:
            rejection_code = "living-memory.source-mismatch"
        active_ids = {memory.memory_id for memory in active_memories}
        if any(
            memory_id not in active_ids
            for memory_id in candidate.recalled_memory_ids
        ):
            rejection_code = "living-memory.recall-not-active"
        if candidate.memory_action == "none":
            if rejection_code is not None:
                return (
                    rejection_code,
                    {
                        "status": LivingMemoryDecisionStatus.REJECTED.value,
                        "recalled_memory_ids": list(candidate.recalled_memory_ids),
                    },
                )
            return (
                "living-memory.recalled",
                {
                    "status": LivingMemoryDecisionStatus.NO_OP.value,
                    "recalled_memory_ids": list(candidate.recalled_memory_ids),
                },
            )
        evidence = candidate.evidence_quote
        if (
            not isinstance(evidence, str)
            or not evidence.strip()
            or len(evidence) > 500
            or evidence not in request.current_user_message
        ):
            rejection_code = "living-memory.evidence-not-verbatim"
        if candidate.memory_action == "create":
            if candidate.supersedes_memory_id is not None:
                rejection_code = "living-memory.create-cannot-supersede"
        elif candidate.memory_action == "revise":
            if candidate.supersedes_memory_id not in active_ids:
                rejection_code = "living-memory.supersedes-not-active"
        else:
            rejection_code = "living-memory.action-invalid"
        if rejection_code is not None:
            return (
                rejection_code,
                {
                    "status": LivingMemoryDecisionStatus.REJECTED.value,
                    "memory_id": candidate.candidate_id,
                },
            )
        if candidate.memory_kind not in {"durable", "plan"}:
            return (
                "living-memory.kind-invalid",
                {
                    "status": LivingMemoryDecisionStatus.REJECTED.value,
                    "memory_id": candidate.candidate_id,
                },
            )
        payload: dict[str, object] = {
            "status": LivingMemoryDecisionStatus.ACCEPTED.value,
            "memory_id": candidate.candidate_id,
            "content": evidence,
            "source_user_message_id": request.source_user_message_id,
            "supersedes_memory_id": candidate.supersedes_memory_id,
            "memory_kind": candidate.memory_kind,
        }
        if candidate.memory_kind == "plan":
            temporal_anchor = TemporalGrounding().anchor(
                request.current_user_message,
                observed_at_us=basis.observed_at_us,
            )
            if (
                temporal_anchor is not None
                and temporal_anchor.original_expression in evidence
            ):
                payload["temporal_anchor"] = temporal_anchor.to_dict()
        return (
            "living-memory.accepted",
            payload,
        )

    def _knowledge_fragment(
        self,
        basis: ExperienceBasis,
        request: ExperienceAdjudicationRequest,
        candidate: ExperienceChangeCandidate,
    ) -> tuple[str, dict[str, object] | None]:
        rejection_code: str | None = None
        try:
            UUID(candidate.candidate_id)
        except (AttributeError, TypeError, ValueError):
            rejection_code = "knowledge.identity-invalid"
        candidate_ids = {entry.entry_id for entry in request.knowledge_candidates}
        if not request.knowledge_candidates:
            rejection_code = "knowledge.no-projected-candidates"
        if any(
            entry_id not in candidate_ids
            for entry_id in candidate.knowledge_citation_ids
        ):
            rejection_code = "knowledge.citation-not-projected"
        if len(set(candidate.knowledge_citation_ids)) != len(
            candidate.knowledge_citation_ids
        ):
            rejection_code = "knowledge.citation-duplicated"
        if rejection_code is not None:
            return (
                rejection_code,
                {
                    "status": "rejected",
                    "cited_entry_ids": list(candidate.knowledge_citation_ids),
                },
            )
        return (
            "knowledge.accepted",
            {
                "status": "accepted",
                "cited_entry_ids": list(candidate.knowledge_citation_ids),
            },
        )

    def _participant_goal_fragment(
        self,
        basis: ExperienceBasis,
        request: ExperienceAdjudicationRequest,
        change: ExperienceChangeCandidate,
        records: tuple[ParticipantGoalCommitmentRecord, ...],
    ) -> tuple[str, dict[str, object]]:
        raw_candidate = change.participant_goal_candidate
        if raw_candidate is None:
            raise DomainAdjudicationFailedClosed(
                "experience",
                "participant-goal-candidate-absent",
                "participant goal change requires a typed candidate",
            )
        try:
            UUID(change.candidate_id)
            UUID(request.source_user_message_id)
        except (AttributeError, TypeError, ValueError):
            return (
                "participant-goal.identity-invalid",
                {"status": "rejected", "action": "noop", "reason_code": "identity_invalid"},
            )
        plan = ParticipantGoalCommitmentEngine().evaluate(
            source_user_message_id=request.source_user_message_id,
            message_text=request.current_user_message,
            current_records=active_targets(records),
            candidate=raw_candidate,
        )
        payload: dict[str, object] = {
            "status": plan.decision.replace("_", "-"),
            "action": plan.action,
            "reason_code": plan.reason_code,
            "kind": plan.kind,
            "terms": plan.terms,
            "next_status": plan.next_status,
            "source_user_message_id": plan.source_user_message_id,
            "evidence_quote": plan.evidence_quote,
            "target_record_id": plan.target_record_id,
            "policy_id": plan.policy_id,
            "policy_version": plan.policy_version,
            "policy_hash": plan.policy_hash,
        }
        if plan.decision == "accepted":
            if plan.action in {"create", "revise"}:
                temporal_anchor = TemporalGrounding().anchor(
                    request.current_user_message,
                    observed_at_us=basis.observed_at_us,
                )
                if (
                    temporal_anchor is not None
                    and plan.terms is not None
                    and temporal_anchor.original_expression in plan.terms
                ):
                    payload["temporal_anchor"] = temporal_anchor.to_dict()
            payload["record_id"] = (
                change.candidate_id
                if plan.action in {"create", "revise"}
                else plan.target_record_id
            )
            return "participant-goal.accepted", payload
        return f"participant-goal.{plan.reason_code}", payload


__all__ = [
    "ExperienceAdjudicationRequest",
    "ExperienceChangeCandidate",
    "ExperienceDomain",
    "ExperienceReadView",
]
