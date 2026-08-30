"""Read-only typed ExperienceImpactEnvelope for four Domain requests."""

from __future__ import annotations

from dataclasses import dataclass

from dynamic_subject_agent.domains._shared import (
    ExperienceBasis,
    ExperienceImpactEnvelopeRejected,
)
from dynamic_subject_agent.domains.agency import AgencyAdjudicationRequest
from dynamic_subject_agent.domains.experience import ExperienceAdjudicationRequest
from dynamic_subject_agent.domains.relationship import RelationshipAdjudicationRequest
from dynamic_subject_agent.domains.subject_state import SubjectStateAdjudicationRequest


@dataclass(frozen=True)
class ExperienceImpactEnvelope:
    """Bind four typed slices to one immutable ExperienceBasis."""

    experience: ExperienceAdjudicationRequest
    subject_state: SubjectStateAdjudicationRequest
    agency: AgencyAdjudicationRequest
    relationship: RelationshipAdjudicationRequest

    def __post_init__(self) -> None:
        expected_types = (
            (self.experience, ExperienceAdjudicationRequest, "experience"),
            (self.subject_state, SubjectStateAdjudicationRequest, "subject_state"),
            (self.agency, AgencyAdjudicationRequest, "agency"),
            (self.relationship, RelationshipAdjudicationRequest, "relationship"),
        )
        for value, expected_type, field in expected_types:
            if not isinstance(value, expected_type):
                raise ExperienceImpactEnvelopeRejected(
                    "wrong-domain-request",
                    f"{field} must be a typed {expected_type.__name__}",
                )
        bases = (
            self.experience.basis,
            self.subject_state.basis,
            self.agency.basis,
            self.relationship.basis,
        )
        if any(basis != bases[0] for basis in bases[1:]):
            raise ExperienceImpactEnvelopeRejected(
                "mixed-experience-basis",
                "all four Domain requests must share one exact ExperienceBasis",
            )

    @property
    def basis(self) -> ExperienceBasis:
        return self.experience.basis
