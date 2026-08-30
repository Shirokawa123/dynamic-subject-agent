"""Four explicit M0 Domain Interfaces and their immutable contracts."""

from dynamic_subject_agent.domains._shared import (
    DomainAdjudicationFailedClosed,
    DomainCapabilityState,
    ExperienceBasis,
    ExperienceImpactEnvelopeRejected,
    M0_DOMAIN_RULE_VERSION,
)
from dynamic_subject_agent.domains.agency import (
    AgencyAdjudicationRequest,
    AgencyChangeCandidate,
    AgencyDomain,
    AgencyReadView,
)
from dynamic_subject_agent.domains.envelope import ExperienceImpactEnvelope
from dynamic_subject_agent.domains.experience import (
    ExperienceAdjudicationRequest,
    ExperienceChangeCandidate,
    ExperienceDomain,
    ExperienceReadView,
)
from dynamic_subject_agent.domains.outcomes import (
    CompleteDomainOutcomeSet,
    DomainOutcomeSetRejected,
)
from dynamic_subject_agent.domains.relationship import (
    RelationshipAdjudicationRequest,
    RelationshipChangeCandidate,
    RelationshipDomain,
    RelationshipReadView,
)
from dynamic_subject_agent.domains.subject_state import (
    DevelopmentChangeCandidate,
    SituatedEffectCandidate,
    SubjectStateAdjudicationRequest,
    SubjectStateDomain,
    SubjectStateReadView,
)

__all__ = [
    "AgencyAdjudicationRequest",
    "AgencyChangeCandidate",
    "AgencyDomain",
    "AgencyReadView",
    "CompleteDomainOutcomeSet",
    "DevelopmentChangeCandidate",
    "DomainAdjudicationFailedClosed",
    "DomainCapabilityState",
    "DomainOutcomeSetRejected",
    "ExperienceAdjudicationRequest",
    "ExperienceBasis",
    "ExperienceChangeCandidate",
    "ExperienceDomain",
    "ExperienceImpactEnvelope",
    "ExperienceImpactEnvelopeRejected",
    "ExperienceReadView",
    "M0_DOMAIN_RULE_VERSION",
    "RelationshipAdjudicationRequest",
    "RelationshipChangeCandidate",
    "RelationshipDomain",
    "RelationshipReadView",
    "SituatedEffectCandidate",
    "SubjectStateAdjudicationRequest",
    "SubjectStateDomain",
    "SubjectStateReadView",
]
