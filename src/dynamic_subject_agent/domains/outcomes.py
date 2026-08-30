"""Order-independent validation of the four concrete DomainOutcome types."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass

from dynamic_subject_agent.timeline import (
    AgencyDomainOutcome,
    CandidateDecisionRecord,
    DecisionStatus,
    DevelopmentOutcome,
    ExperienceDomainOutcome,
    RelationshipDomainOutcome,
    SubjectCoreOutcome,
    SubjectStateDomainOutcome,
)


class DomainOutcomeSetRejected(Exception):
    """Four concrete outcomes could not form one complete typed set."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _validate_reasoned_noop(
    decision: object,
    *,
    expected_scope: str,
) -> CandidateDecisionRecord:
    if not isinstance(decision, CandidateDecisionRecord):
        raise DomainOutcomeSetRejected(
            "invalid-domain-decision",
            f"{expected_scope} requires a CandidateDecisionRecord",
        )
    if (
        decision.scope != expected_scope
        or decision.status is not DecisionStatus.NO_OP
        or decision.actual_revision_ids
        or not decision.rule_version.strip()
    ):
        raise DomainOutcomeSetRejected(
            "invalid-domain-noop",
            f"{expected_scope} must be a reasoned typed NoOp without revisions",
        )
    try:
        reason = json.loads(decision.reason)
    except (TypeError, json.JSONDecodeError) as error:
        raise DomainOutcomeSetRejected(
            "invalid-domain-reason",
            f"{expected_scope} reason must contain canonical code and provenance",
        ) from error
    if not isinstance(reason, dict):
        raise DomainOutcomeSetRejected(
            "invalid-domain-reason",
            f"{expected_scope} reason must be an object",
        )
    allowed_keys = {"code", "provenance"}
    if expected_scope == "experience" and "living_memory" in reason:
        allowed_keys.add("living_memory")
    if expected_scope == "experience" and "knowledge" in reason:
        allowed_keys.add("knowledge")
    if expected_scope == "relationship" and "relationship" in reason:
        allowed_keys.add("relationship")
    if (
        set(reason) != allowed_keys
        or not isinstance(reason["code"], str)
        or not reason["code"].strip()
        or not isinstance(reason["provenance"], str)
        or not reason["provenance"].strip()
    ):
        raise DomainOutcomeSetRejected(
            "invalid-domain-reason",
            f"{expected_scope} reason must contain canonical code and provenance",
        )
    if "living_memory" in reason:
        memory = reason["living_memory"]
        if (
            not isinstance(memory, dict)
            or memory.get("status") not in {"accepted", "rejected", "no-op"}
        ):
            raise DomainOutcomeSetRejected(
                "invalid-living-memory-reason",
                "Experience Living Memory reason requires a typed status",
            )
    if "knowledge" in reason:
        knowledge = reason["knowledge"]
        if (
            not isinstance(knowledge, dict)
            or knowledge.get("status") not in {"accepted", "rejected"}
            or not isinstance(knowledge.get("cited_entry_ids"), list)
        ):
            raise DomainOutcomeSetRejected(
                "invalid-knowledge-reason",
                "Experience knowledge reason requires a typed status and cited ids",
            )
    if "relationship" in reason:
        relationship = reason["relationship"]
        if (
            not isinstance(relationship, dict)
            or relationship.get("status") not in {"accepted", "rejected", "no-update"}
            or not isinstance(relationship.get("event"), str)
        ):
            raise DomainOutcomeSetRejected(
                "invalid-relationship-reason",
                "Relationship reason requires a typed status and event",
            )
    return decision


@dataclass(frozen=True)
class CompleteDomainOutcomeSet:
    """Exactly one result from each Domain, independent of completion order."""

    experience: ExperienceDomainOutcome
    subject_state: SubjectStateDomainOutcome
    agency: AgencyDomainOutcome
    relationship: RelationshipDomainOutcome

    def __post_init__(self) -> None:
        expected_types = (
            (self.experience, ExperienceDomainOutcome, "experience"),
            (self.subject_state, SubjectStateDomainOutcome, "subject_state"),
            (self.agency, AgencyDomainOutcome, "agency"),
            (self.relationship, RelationshipDomainOutcome, "relationship"),
        )
        for value, expected_type, field in expected_types:
            if type(value) is not expected_type:
                raise DomainOutcomeSetRejected(
                    "wrong-domain-outcome-type",
                    f"{field} must be a concrete {expected_type.__name__}",
                )
        self._validate()

    @classmethod
    def collect(cls, outcomes: Iterable[object]) -> CompleteDomainOutcomeSet:
        slots: dict[str, object] = {}
        for outcome in outcomes:
            if type(outcome) is ExperienceDomainOutcome:
                slot = "experience"
            elif type(outcome) is SubjectStateDomainOutcome:
                slot = "subject_state"
            elif type(outcome) is AgencyDomainOutcome:
                slot = "agency"
            elif type(outcome) is RelationshipDomainOutcome:
                slot = "relationship"
            else:
                raise DomainOutcomeSetRejected(
                    "wrong-domain-outcome-type",
                    "only the four concrete top-level DomainOutcome types are allowed",
                )
            if slot in slots:
                raise DomainOutcomeSetRejected(
                    "duplicate-domain-outcome",
                    f"the {slot} Domain produced more than one outcome",
                )
            slots[slot] = outcome
        missing = tuple(
            name
            for name in ("experience", "subject_state", "agency", "relationship")
            if name not in slots
        )
        if missing:
            raise DomainOutcomeSetRejected(
                "missing-domain-outcome",
                f"missing required Domain outcomes: {', '.join(missing)}",
            )
        return cls(
            experience=slots["experience"],  # type: ignore[arg-type]
            subject_state=slots["subject_state"],  # type: ignore[arg-type]
            agency=slots["agency"],  # type: ignore[arg-type]
            relationship=slots["relationship"],  # type: ignore[arg-type]
        )

    def _validate(self) -> None:
        if not isinstance(self.subject_state.subject_core, SubjectCoreOutcome):
            raise DomainOutcomeSetRejected(
                "missing-subject-core-outcome",
                "SubjectState requires a distinct SubjectCoreOutcome",
            )
        if not isinstance(self.subject_state.development, DevelopmentOutcome):
            raise DomainOutcomeSetRejected(
                "missing-development-outcome",
                "SubjectState requires a distinct DevelopmentOutcome",
            )
        decisions = (
            (self.experience.decision, "experience"),
            (self.subject_state.decision, "subject-state"),
            (self.subject_state.subject_core.decision, "subject-core"),
            (self.subject_state.development.decision, "development"),
            (self.agency.decision, "agency"),
            (self.relationship.decision, "relationship"),
        )
        for decision, scope in decisions:
            _validate_reasoned_noop(decision, expected_scope=scope)
        if self.agency.committed_effect_eligible:
            raise DomainOutcomeSetRejected(
                "agency-effect-ineligible",
                "M0-A Agency outcomes cannot authorize a committed effect",
            )
        if not self.experience.epistemic_outcome_id.strip():
            raise DomainOutcomeSetRejected(
                "experience-lineage-missing",
                "Experience outcome must reference its EpistemicOutcome",
            )
        if not self.relationship.relationship_target_id.strip():
            raise DomainOutcomeSetRejected(
                "relationship-target-missing",
                "Relationship outcome must retain its exact target",
            )
        identities = (
            self.experience.outcome_id,
            self.subject_state.outcome_id,
            self.subject_state.subject_core.outcome_id,
            self.subject_state.development.outcome_id,
            self.agency.outcome_id,
            self.relationship.outcome_id,
            *(decision.decision_id for decision, _ in decisions),
        )
        if len(set(identities)) != len(identities):
            raise DomainOutcomeSetRejected(
                "domain-outcome-identity-collision",
                "Domain outcome and decision identities must be distinct",
            )
