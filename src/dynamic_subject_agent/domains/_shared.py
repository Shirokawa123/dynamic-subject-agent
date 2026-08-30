"""Shared immutable facts for the four M0 Domain Interfaces.

This module owns validation and audit formatting only.  It has no persistence,
Timeline, orchestration, or cross-Domain dispatch authority.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from uuid import NAMESPACE_URL, UUID, uuid5

from dynamic_subject_agent.timeline import CandidateDecisionRecord, DecisionStatus


M0_DOMAIN_RULE_VERSION = "m0-domain-noop-1.0"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class DomainCapabilityState(str, Enum):
    """Capability state disclosed before a material Domain change is attempted."""

    UNAVAILABLE = "unavailable"
    AVAILABLE = "available"


@dataclass(frozen=True)
class ExperienceBasis:
    """The read-only minimum shared head for one Experience adjudication."""

    operation_id: str
    attempt_id: str
    subject_event_id: str
    experience_id: str
    profile_id: str
    timeline_id: str
    epistemic_outcome_id: str
    verified_prefix_digest: str
    source_provenance: str
    integrity_verified: bool


class DomainAdjudicationFailedClosed(Exception):
    """A Domain participated but could not prove a safe adjudication."""

    status = DecisionStatus.FAILED_CLOSED

    def __init__(self, domain: str, code: str, detail: str) -> None:
        super().__init__(f"{domain}:{code}: {detail}")
        self.domain = domain
        self.code = code
        self.detail = detail


class ExperienceImpactEnvelopeRejected(Exception):
    """The cross-module read-only envelope is incomplete or inconsistent."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def validate_basis(basis: object, *, domain: str) -> ExperienceBasis:
    if not isinstance(basis, ExperienceBasis):
        raise DomainAdjudicationFailedClosed(
            domain,
            "invalid-experience-basis",
            "adjudication requires a typed ExperienceBasis",
        )
    identities = {
        "operation_id": basis.operation_id,
        "attempt_id": basis.attempt_id,
        "subject_event_id": basis.subject_event_id,
        "experience_id": basis.experience_id,
        "profile_id": basis.profile_id,
        "timeline_id": basis.timeline_id,
        "epistemic_outcome_id": basis.epistemic_outcome_id,
    }
    try:
        for value in identities.values():
            UUID(value)
    except (AttributeError, TypeError, ValueError) as error:
        raise DomainAdjudicationFailedClosed(
            domain,
            "invalid-experience-lineage",
            "every ExperienceBasis identity must be a canonical UUID",
        ) from error
    if not basis.integrity_verified:
        raise DomainAdjudicationFailedClosed(
            domain,
            "experience-basis-unverified",
            "the Experience basis integrity was not verified",
        )
    if not _SHA256_PATTERN.fullmatch(basis.verified_prefix_digest):
        raise DomainAdjudicationFailedClosed(
            domain,
            "verified-prefix-invalid",
            "the verified epistemic prefix must be a SHA-256 digest",
        )
    if basis.source_provenance != "project-original":
        raise DomainAdjudicationFailedClosed(
            domain,
            "source-provenance-unqualified",
            "M0-A accepts only the qualified project-original fixture",
        )
    return basis


def stable_id(basis: ExperienceBasis, name: str) -> str:
    identity = ":".join(
        (
            "m0-08",
            basis.operation_id,
            basis.attempt_id,
            basis.experience_id,
            name,
        )
    )
    return str(uuid5(NAMESPACE_URL, identity))


def reason_payload(*, code: str, provenance: str) -> str:
    return json.dumps(
        {"code": code, "provenance": provenance},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def noop_decision(
    basis: ExperienceBasis,
    *,
    scope: str,
    reason_code: str,
) -> CandidateDecisionRecord:
    return CandidateDecisionRecord(
        decision_id=stable_id(basis, f"{scope}-decision"),
        scope=scope,
        status=DecisionStatus.NO_OP,
        reason=reason_payload(
            code=reason_code,
            provenance=basis.source_provenance,
        ),
        rule_version=M0_DOMAIN_RULE_VERSION,
        actual_revision_ids=(),
    )


def require_tuple(value: object, *, domain: str, field: str) -> tuple[object, ...]:
    if not isinstance(value, tuple):
        raise DomainAdjudicationFailedClosed(
            domain,
            "mutable-domain-input",
            f"{field} must be an immutable tuple",
        )
    return value
