"""Relationship Domain: target-specific, provenance-separated adjudication."""

from __future__ import annotations

from dataclasses import dataclass

import json
from uuid import UUID

from dynamic_subject_agent.timeline import (
    CandidateDecisionRecord,
    DecisionStatus,
    RelationshipDomainOutcome,
)
from dynamic_subject_agent.relationship_events import (
    ALL_RELATIONSHIP_EVENTS,
    NO_UPDATE_EVENTS,
    UPDATE_EVENTS,
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

_STABLE_POSITIVE_EVIDENCE_MARKERS = (
    "谢谢",
    "感谢",
    "准确",
    "记得",
    "帮助",
    "尊重",
    "信任",
    "放心",
    "做得好",
    "确认好了",
)
_BOUNDARY_RETROSPECTIVE_MARKERS = (
    "刚才",
    "之前",
    "上次",
    "这次你",
    "你已经",
    "你确实",
)
_BOUNDARY_RESPECT_OUTCOME_MARKERS = (
    "尊重",
    "听到我说",
    "停下",
    "没有继续",
    "照我说的",
)


@dataclass(frozen=True)
class RelationshipChangeCandidate:
    candidate_id: str
    relationship_target_id: str
    evidence_refs: tuple[str, ...]
    event: str = ""
    evidence_quote: str = ""
    source_user_message_id: str = ""
    policy_version: str = ""


@dataclass(frozen=True)
class RelationshipReadView:
    relationship_target_id: str
    subject_stance_revision_refs: tuple[str, ...]
    interaction_norm_revision_refs: tuple[str, ...]
    mutual_commitment_revision_refs: tuple[str, ...]
    narrative_revision_refs: tuple[str, ...]
    authored_origin_refs: tuple[str, ...]
    earned_evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class RelationshipAdjudicationRequest:
    basis: ExperienceBasis
    relationship_enabled: bool
    relationship_target_id: str
    current_state: RelationshipReadView
    candidates: tuple[RelationshipChangeCandidate, ...]
    failure_code: str | None = None


class RelationshipDomain:
    """Adjudicate one relationship without scores or cross-Domain authority."""

    material_change_capability = DomainCapabilityState.UNAVAILABLE

    def adjudicate(
        self,
        request: RelationshipAdjudicationRequest,
    ) -> RelationshipDomainOutcome:
        if not isinstance(request, RelationshipAdjudicationRequest):
            raise DomainAdjudicationFailedClosed(
                "relationship",
                "wrong-domain-request",
                "RelationshipDomain requires RelationshipAdjudicationRequest",
            )
        basis = validate_basis(request.basis, domain="relationship")
        if not isinstance(request.current_state, RelationshipReadView):
            raise DomainAdjudicationFailedClosed(
                "relationship",
                "invalid-read-view",
                "Relationship current state must be a typed read-only view",
            )
        if (
            request.relationship_target_id
            != request.current_state.relationship_target_id
            or request.relationship_target_id != basis.profile_id
        ):
            raise DomainAdjudicationFailedClosed(
                "relationship",
                "relationship-target-mismatch",
                "the request, read view, and Experience basis must name one target",
            )
        candidates = require_tuple(
            request.candidates,
            domain="relationship",
            field="candidates",
        )
        for candidate in candidates:
            if not isinstance(candidate, RelationshipChangeCandidate):
                raise DomainAdjudicationFailedClosed(
                    "relationship",
                    "wrong-domain-candidate",
                    "only RelationshipChangeCandidate may enter RelationshipDomain",
                )
            if candidate.relationship_target_id != request.relationship_target_id:
                raise DomainAdjudicationFailedClosed(
                    "relationship",
                    "candidate-target-mismatch",
                    "Relationship candidate names a different target",
                )
        failure = request.failure_code
        if failure is not None and (
            failure
            not in {
                "relationship-provider-failed",
                "relationship-provider-invalid-output",
            }
            or candidates
            or not request.relationship_enabled
        ):
            raise DomainAdjudicationFailedClosed(
                "relationship",
                "relationship-failure-invalid",
                "Relationship failure must be typed, enabled and carry no candidate",
            )
        if failure is not None:
            decision = CandidateDecisionRecord(
                decision_id=stable_id(basis, "relationship-decision"),
                scope="relationship",
                status=DecisionStatus.NO_OP,
                reason=json.dumps(
                    {
                        "code": failure,
                        "provenance": basis.source_provenance,
                        "relationship": {
                            "status": "failed-closed",
                            "event": "",
                            "evidence_quote": "",
                            "source_user_message_id": basis.operation_id,
                            "policy_version": "relationship-stance-v1",
                            "reason_code": failure,
                        },
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                rule_version="relationship-1.0",
                actual_revision_ids=(),
            )
            return RelationshipDomainOutcome(
                outcome_id=stable_id(basis, "relationship-outcome"),
                decision=decision,
                relationship_target_id=request.relationship_target_id,
            )
        if candidates:
            return self._adjudicate_stance_event(basis, candidates[0])
        reason_code = (
            "relationship.no-applicable-candidate"
            if request.relationship_enabled
            else "relationship.disabled-by-configuration"
        )
        return RelationshipDomainOutcome(
            outcome_id=stable_id(basis, "relationship-outcome"),
            decision=noop_decision(
                basis,
                scope="relationship",
                reason_code=reason_code,
            ),
            relationship_target_id=request.relationship_target_id,
        )

    def _adjudicate_stance_event(
        self,
        basis: ExperienceBasis,
        candidate: RelationshipChangeCandidate,
    ) -> RelationshipDomainOutcome:
        rejection_code: str | None = None
        try:
            UUID(candidate.candidate_id)
            UUID(candidate.source_user_message_id)
        except (AttributeError, TypeError, ValueError):
            rejection_code = "relationship.identity-invalid"
        if candidate.event not in ALL_RELATIONSHIP_EVENTS:
            rejection_code = "relationship.event-not-in-closed-set"
        if (
            candidate.event in UPDATE_EVENTS
            and (
                not isinstance(candidate.evidence_quote, str)
                or not candidate.evidence_quote.strip()
                or len(candidate.evidence_quote) > 500
            )
        ):
            rejection_code = "relationship.evidence-missing"
        if (
            candidate.event == "stable_positive_interaction"
            and not any(
                marker in candidate.evidence_quote
                for marker in _STABLE_POSITIVE_EVIDENCE_MARKERS
            )
        ):
            rejection_code = "relationship.stable-positive-evidence-insufficient"
        if candidate.event == "boundary_respected" and not (
            any(
                marker in candidate.evidence_quote
                for marker in _BOUNDARY_RETROSPECTIVE_MARKERS
            )
            and any(
                marker in candidate.evidence_quote
                for marker in _BOUNDARY_RESPECT_OUTCOME_MARKERS
            )
        ):
            rejection_code = "relationship.boundary-respected-evidence-insufficient"
        if not candidate.policy_version.strip():
            rejection_code = "relationship.policy-version-missing"
        if rejection_code is not None:
            return self._stance_outcome(basis, candidate, code=rejection_code)
        if candidate.event in NO_UPDATE_EVENTS:
            return self._stance_outcome(
                basis,
                candidate,
                code="relationship.stance-event-no-update",
            )
        return self._stance_outcome(
            basis,
            candidate,
            code="relationship.stance-event-accepted",
        )

    def _stance_outcome(
        self,
        basis: ExperienceBasis,
        candidate: RelationshipChangeCandidate,
        *,
        code: str,
    ) -> RelationshipDomainOutcome:
        accepted = code == "relationship.stance-event-accepted"
        status = "accepted" if accepted else (
            "no-update" if code == "relationship.stance-event-no-update" else "rejected"
        )
        payload: dict[str, object] = {
            "code": code,
            "provenance": basis.source_provenance,
            "relationship": {
                "status": status,
                "event": candidate.event,
                "evidence_quote": candidate.evidence_quote,
                "source_user_message_id": candidate.source_user_message_id,
                "policy_version": candidate.policy_version,
            },
        }
        decision = CandidateDecisionRecord(
            decision_id=stable_id(basis, "relationship-stance-decision"),
            scope="relationship",
            status=DecisionStatus.NO_OP,
            reason=json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            rule_version="relationship-stance-1.0",
            actual_revision_ids=(),
        )
        return RelationshipDomainOutcome(
            outcome_id=stable_id(basis, "relationship-outcome"),
            decision=decision,
            relationship_target_id=candidate.relationship_target_id,
        )
