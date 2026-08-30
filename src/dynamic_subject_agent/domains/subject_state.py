"""SubjectState Domain: distinct SubjectCore and Development adjudication."""

from __future__ import annotations

from dataclasses import dataclass

from dynamic_subject_agent.timeline import (
    DevelopmentOutcome,
    SubjectCoreOutcome,
    SubjectStateDomainOutcome,
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


@dataclass(frozen=True)
class SituatedEffectCandidate:
    candidate_id: str
    target_profile_id: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class DevelopmentChangeCandidate:
    candidate_id: str
    target_profile_id: str
    consolidation_eligibility_ref: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class SubjectStateReadView:
    subject_core_revision_refs: tuple[str, ...]
    development_revision_refs: tuple[str, ...]


@dataclass(frozen=True)
class SubjectStateAdjudicationRequest:
    basis: ExperienceBasis
    current_state: SubjectStateReadView
    situated_effect_candidates: tuple[SituatedEffectCandidate, ...]
    development_candidates: tuple[DevelopmentChangeCandidate, ...]


class SubjectStateDomain:
    """Adjudicate two state authorities without folding either result."""

    material_change_capability = DomainCapabilityState.UNAVAILABLE

    def adjudicate(
        self,
        request: SubjectStateAdjudicationRequest,
    ) -> SubjectStateDomainOutcome:
        if not isinstance(request, SubjectStateAdjudicationRequest):
            raise DomainAdjudicationFailedClosed(
                "subject-state",
                "wrong-domain-request",
                "SubjectStateDomain requires SubjectStateAdjudicationRequest",
            )
        basis = validate_basis(request.basis, domain="subject-state")
        if not isinstance(request.current_state, SubjectStateReadView):
            raise DomainAdjudicationFailedClosed(
                "subject-state",
                "invalid-read-view",
                "SubjectState current state must be a typed read-only view",
            )
        situated = require_tuple(
            request.situated_effect_candidates,
            domain="subject-state",
            field="situated_effect_candidates",
        )
        development = require_tuple(
            request.development_candidates,
            domain="subject-state",
            field="development_candidates",
        )
        for candidate in situated:
            if not isinstance(candidate, SituatedEffectCandidate):
                raise DomainAdjudicationFailedClosed(
                    "subject-state",
                    "wrong-domain-candidate",
                    "only SituatedEffectCandidate may enter SubjectCore",
                )
            if candidate.target_profile_id != basis.profile_id:
                raise DomainAdjudicationFailedClosed(
                    "subject-state",
                    "candidate-target-mismatch",
                    "SituatedEffectCandidate names a different Profile",
                )
        for candidate in development:
            if not isinstance(candidate, DevelopmentChangeCandidate):
                raise DomainAdjudicationFailedClosed(
                    "subject-state",
                    "wrong-domain-candidate",
                    "only DevelopmentChangeCandidate may enter Development",
                )
            if candidate.target_profile_id != basis.profile_id:
                raise DomainAdjudicationFailedClosed(
                    "subject-state",
                    "candidate-target-mismatch",
                    "Development candidate names a different Profile",
                )
        if situated or development:
            raise DomainAdjudicationFailedClosed(
                "subject-state",
                "material-change-capability-unavailable",
                "M0-A cannot safely adjudicate a SubjectState material change",
            )
        return SubjectStateDomainOutcome(
            outcome_id=stable_id(basis, "subject-state-outcome"),
            decision=noop_decision(
                basis,
                scope="subject-state",
                reason_code="subject-state.no-material-change",
            ),
            subject_core=SubjectCoreOutcome(
                outcome_id=stable_id(basis, "subject-core-outcome"),
                decision=noop_decision(
                    basis,
                    scope="subject-core",
                    reason_code=("subject-state.subject-core.no-applicable-candidate"),
                ),
            ),
            development=DevelopmentOutcome(
                outcome_id=stable_id(basis, "development-outcome"),
                decision=noop_decision(
                    basis,
                    scope="development",
                    reason_code=("subject-state.development.no-applicable-candidate"),
                ),
            ),
        )
