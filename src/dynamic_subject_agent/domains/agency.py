"""Agency Domain: intentions, projects, commitments, and action authority."""

from __future__ import annotations

from dataclasses import dataclass

from dynamic_subject_agent.timeline import AgencyDomainOutcome
from dynamic_subject_agent.domains._shared import (
    DomainAdjudicationFailedClosed,
    DomainCapabilityState,
    ExperienceBasis,
    noop_decision,
    require_tuple,
    stable_id,
    validate_basis,
)


@dataclass(frozen=True)
class AgencyChangeCandidate:
    candidate_id: str
    target_profile_id: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class AgencyReadView:
    intention_refs: tuple[str, ...]
    project_refs: tuple[str, ...]
    commitment_refs: tuple[str, ...]
    action_refs: tuple[str, ...]


@dataclass(frozen=True)
class AgencyAdjudicationRequest:
    basis: ExperienceBasis
    current_state: AgencyReadView
    candidates: tuple[AgencyChangeCandidate, ...]


class AgencyDomain:
    """Adjudicate Agency inputs without creating or dispatching effects."""

    material_change_capability = DomainCapabilityState.UNAVAILABLE

    def adjudicate(self, request: AgencyAdjudicationRequest) -> AgencyDomainOutcome:
        if not isinstance(request, AgencyAdjudicationRequest):
            raise DomainAdjudicationFailedClosed(
                "agency",
                "wrong-domain-request",
                "AgencyDomain requires AgencyAdjudicationRequest",
            )
        basis = validate_basis(request.basis, domain="agency")
        if not isinstance(request.current_state, AgencyReadView):
            raise DomainAdjudicationFailedClosed(
                "agency",
                "invalid-read-view",
                "Agency current state must be a typed read-only view",
            )
        candidates = require_tuple(
            request.candidates,
            domain="agency",
            field="candidates",
        )
        for candidate in candidates:
            if not isinstance(candidate, AgencyChangeCandidate):
                raise DomainAdjudicationFailedClosed(
                    "agency",
                    "wrong-domain-candidate",
                    "only AgencyChangeCandidate may enter AgencyDomain",
                )
            if candidate.target_profile_id != basis.profile_id:
                raise DomainAdjudicationFailedClosed(
                    "agency",
                    "candidate-target-mismatch",
                    "Agency candidate names a different Profile",
                )
        if candidates:
            raise DomainAdjudicationFailedClosed(
                "agency",
                "material-change-capability-unavailable",
                "M0-A cannot safely adjudicate an Agency material-change candidate",
            )
        return AgencyDomainOutcome(
            outcome_id=stable_id(basis, "agency-outcome"),
            decision=noop_decision(
                basis,
                scope="agency",
                reason_code="agency.no-applicable-candidate",
            ),
            committed_effect_eligible=False,
        )
