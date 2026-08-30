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


@dataclass(frozen=True)
class ExperienceReadView:
    verified_prefix_digest: str
    memory_trace_refs: tuple[str, ...]
    active_memories: tuple[LivingMemoryRecord, ...] = ()


@dataclass(frozen=True)
class ExperienceAdjudicationRequest:
    basis: ExperienceBasis
    current_state: ExperienceReadView
    candidates: tuple[ExperienceChangeCandidate, ...]
    current_user_message: str = ""
    source_user_message_id: str = ""
    knowledge_candidates: tuple[KnowledgeEntry, ...] = ()


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
                candidate.memory_action is None and candidate.knowledge_citation_ids
            )
            if is_memory and is_knowledge:
                raise DomainAdjudicationFailedClosed(
                    "experience",
                    "mixed-kind-candidate",
                    "one candidate may not carry both memory and knowledge changes",
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
            else:
                raise DomainAdjudicationFailedClosed(
                    "experience",
                    "material-change-capability-unavailable",
                    "only Living Memory and knowledge citation changes are available",
                )
        if memory_candidate is None and knowledge_candidate is None:
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
        if memory_candidate is not None:
            memory_code, memory_payload = self._living_memory_fragment(
                basis,
                request,
                memory_candidate,
                tuple(active_memories),
            )
        knowledge_code: str | None = None
        knowledge_payload: dict[str, object] | None = None
        if knowledge_candidate is not None:
            knowledge_code, knowledge_payload = self._knowledge_fragment(
                basis,
                request,
                knowledge_candidate,
            )
        reason: dict[str, object] = {
            "code": memory_code or knowledge_code or "experience.accepted",
            "provenance": basis.source_provenance,
        }
        if memory_payload is not None:
            reason["living_memory"] = memory_payload
        if knowledge_payload is not None:
            reason["knowledge"] = knowledge_payload
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
        return (
            "living-memory.accepted",
            {
                "status": LivingMemoryDecisionStatus.ACCEPTED.value,
                "memory_id": candidate.candidate_id,
                "content": evidence,
                "source_user_message_id": request.source_user_message_id,
                "supersedes_memory_id": candidate.supersedes_memory_id,
                "memory_kind": candidate.memory_kind,
            },
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


__all__ = [
    "ExperienceAdjudicationRequest",
    "ExperienceChangeCandidate",
    "ExperienceDomain",
    "ExperienceReadView",
]
