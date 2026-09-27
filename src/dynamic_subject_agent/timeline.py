"""Canonical M0 Admission and atomic Publication boundary.

The deep TimelineEngine owns the only canonical writer Interface. Admission
and Publication are separate short transactions; cognition, domain adjudication,
and effect dispatch remain outside this module. M0 Publication accepts only a
complete, precomputed typed-NoOp commit plan.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import tempfile
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from pathlib import Path
from time import time_ns
from typing import Any
from uuid import UUID, uuid4

from dynamic_subject_agent.first_life import (
    FirstLifeInput, LifeRecord, LIFE_SYSTEM_INTENT, decode_life_record,
    initial_life_record, adjudicate_life, event_summary,
)

from dynamic_subject_agent.participant_goals import (
    PARTICIPANT_GOAL_FAILURE_CODES,
    POLICY_HASH as PARTICIPANT_GOAL_POLICY_HASH,
    POLICY_ID as PARTICIPANT_GOAL_POLICY_ID,
    POLICY_VERSION as PARTICIPANT_GOAL_POLICY_VERSION,
    ParticipantGoalCommitmentRecord,
)
from dynamic_subject_agent.situated_state import (
    POLICY_HASH as SITUATED_POLICY_HASH,
    POLICY_ID as SITUATED_POLICY_ID,
    POLICY_VERSION as SITUATED_POLICY_VERSION,
    POSTURES as SITUATED_POSTURES,
    SituatedStateRecord,
)
from dynamic_subject_agent.medium_state import (
    BASELINES as MEDIUM_BASELINES,
    POLICY_HASH as MEDIUM_POLICY_HASH,
    POLICY_ID as MEDIUM_POLICY_ID,
    POLICY_VERSION as MEDIUM_POLICY_VERSION,
    SIGNALS as MEDIUM_SIGNALS,
    MediumSignalRecord,
    MediumStateRecord,
)
from dynamic_subject_agent.temporal_grounding import TemporalAnchor


CONTRACT_VERSION = "M0-CONTRACT-1.0"
PERSISTENCE_VERSION = "M0-PERSISTENCE-1.0"
SCHEMA_VERSION = 1
ROOT_FORMAT = "dynamic-subject-m0-canonical"
ROOT_EPOCH = 1
ROOT_KIND = "test-fixture"
EXPERIMENTAL_ROOT_KIND = "experimental"
_ROOT_KINDS = frozenset({ROOT_KIND, EXPERIMENTAL_ROOT_KIND})
COMMAND_KIND = "contribute-utterance"
NORMALIZATION_VERSION = "subject-command-nfc-lf-v1"
TIMELINE_SCHEMA_FAMILY = "m0-canonical-timeline"
CONTROL_SCHEMA_FAMILY = "m0-canonical-control"
_IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9._~-]{16,256}$")
_RESERVED_TEST_PATH_SEGMENTS = frozenset({"legacy", "private", "retired"})
_HOST_TIMELINE_TOKEN = object()


_PUBLICATION_INTEGRITY_VERSION = "m0-publication-integrity-1"
_EMPTY_VERIFIED_PREFIX_DIGEST = hashlib.sha256(
    b"M0-EMPTY-VERIFIED-EPISTEMIC-PREFIX-1"
).hexdigest()
_EMPTY_REVISION_HEAD_DIGEST = hashlib.sha256(b"M0-EMPTY-REVISION-HEAD-1").hexdigest()


class OperationState(str, Enum):
    ADMITTED_PENDING = "admitted-pending"
    RUNNING = "running"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED_CLOSED = "failed-closed"


class OperationKind(str, Enum):
    SUBJECT = "subject"
    SYSTEM = "system"
    HOST = "host"


class AttemptState(str, Enum):
    PENDING = "pending"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    INTERRUPTED = "interrupted"
    FAILED_CLOSED = "failed-closed"


class DecisionStatus(str, Enum):
    ACCEPTED_AS_PROPOSED = "accepted-as-proposed"
    ACCEPTED_WITH_CONSTRAINTS = "accepted-with-constraints"
    REJECTED = "rejected"
    NO_OP = "no-op"
    FAILED_CLOSED = "failed-closed"


class LivingMemoryDecisionStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NO_OP = "no-op"
    FAILED_CLOSED = "failed-closed"


class EffectDispatchState(str, Enum):
    UNAVAILABLE = "unavailable"
    READY = 'ready'


class FaultPoint(str, Enum):
    BEFORE_PREPARED_CANCEL_COMMIT = 'before-prepared-cancel-commit'
    AFTER_PREPARED_CANCEL_COMMIT = 'after-prepared-cancel-commit'
    BEFORE_TRANSACTION = "before-transaction"
    AFTER_IDEMPOTENCY_CLAIM = "after-idempotency-claim"
    AFTER_OPERATION = "after-operation"
    BEFORE_COMMIT = "before-commit"
    AFTER_COMMIT = "after-commit"
    BEFORE_PLAN_CLAIM = "before-plan-claim"
    AFTER_PLAN_CLAIM = "after-plan-claim"
    BEFORE_PUBLICATION_TRANSACTION = "before-publication-transaction"
    AFTER_COMMIT_PLAN_RECEIPT = "after-commit-plan-receipt"
    AFTER_EXPERIENCE = "after-experience"
    AFTER_EPISTEMIC = "after-epistemic"
    AFTER_CANDIDATE_DECISIONS = "after-candidate-decisions"
    AFTER_DOMAIN_OUTCOMES = "after-domain-outcomes"
    AFTER_REVISION_SET = "after-revision-set"
    AFTER_EXPRESSION = "after-expression"
    AFTER_EFFECT_SET = "after-effect-set"
    AFTER_TIMELINE_OUTCOME = "after-timeline-outcome"
    AFTER_HEAD_ADVANCE = "after-head-advance"
    AFTER_ATTEMPT_TERMINAL = "after-attempt-terminal"
    BEFORE_PUBLICATION_COMMIT = "before-publication-commit"
    AFTER_PUBLICATION_COMMIT = "after-publication-commit"


class AdmissionProblem(Exception):
    """Base for typed Admission failures."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class PreAdmissionRejected(AdmissionProblem):
    """A command was rejected before an OperationRef could exist."""


class PayloadConflict(PreAdmissionRejected):
    """The idempotency key already names a different normalized command."""

    def __init__(self, existing_operation_ref: OperationRef) -> None:
        super().__init__(
            "payload-conflict",
            "the authority-scoped idempotency key names a different payload",
        )
        self.existing_operation_ref = existing_operation_ref


class AdmissionFailedClosed(AdmissionProblem):
    """Admission did not commit and the caller must not treat it as success."""


class AdmissionInterrupted(AdmissionProblem):
    """The Admission commit outcome could not be proven from canonical state."""


class PublicationProblem(Exception):
    """Base for typed failures after an OperationRef exists."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class CommitPlanRejected(PublicationProblem):
    """A CycleCommitPlan is incomplete or outside its frozen authority."""


class _PreparedShareDayExpired(CommitPlanRejected):
    def __init__(self):
        super().__init__('first-life-share-day-expired', 'The prepared share belongs to a different trusted civil day.')


class CommitPlanConflict(PublicationProblem):
    """An immutable plan or attempt identity already names different content."""


class StaleTimelineBasis(PublicationProblem):
    """The plan was built from a Timeline basis that is no longer current."""

    def __init__(
        self,
        expected_basis: TimelineBasis,
        observed_basis: TimelineBasis,
    ) -> None:
        super().__init__(
            "stale-timeline-basis",
            "the current Timeline head no longer matches the frozen plan basis",
        )
        self.expected_basis = expected_basis
        self.observed_basis = observed_basis


class PublicationFailedClosed(PublicationProblem):
    """Publication rolled back before a commit could become authoritative."""


class PublicationInterrupted(PublicationProblem):
    """The Publication commit outcome could not be proven from canonical state."""


def _canonical_uuid(value: str, field: str) -> str:
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError) as error:
        raise PreAdmissionRejected(
            "malformed-command",
            f"{field} must be a UUID",
        ) from error
    return str(parsed)


def _canonical_store_uuid(value: str, field: str) -> str:
    try:
        return str(UUID(value))
    except (AttributeError, TypeError, ValueError) as error:
        raise AdmissionFailedClosed(
            "store-identity-mismatch",
            f"{field} is not a canonical UUID",
        ) from error


def _normalize_text(value: str, field: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise PreAdmissionRejected(
            "malformed-command",
            f"{field} must be text",
        )
    normalized = unicodedata.normalize(
        "NFC",
        value.replace("\r\n", "\n").replace("\r", "\n"),
    )
    if not normalized.strip():
        raise PreAdmissionRejected(
            "malformed-command",
            f"{field} must not be blank",
        )
    if len(normalized) > maximum:
        raise PreAdmissionRejected(
            "malformed-command",
            f"{field} exceeds its M0 bound",
        )
    if "\x00" in normalized:
        raise PreAdmissionRejected(
            "malformed-command",
            f"{field} contains a null character",
        )
    return normalized


def _fingerprint_tuple(parts: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    digest.update(b"M0-SUBJECT-COMMAND-FINGERPRINT-1\x00")
    for part in parts:
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            field.name: _canonical_value(getattr(value, field.name))
            for field in fields(value)
            # The optional schema-3 extension must not change schema-1/2 bytes.
            if field.name != "life_record" or getattr(value, field.name) is not None
        }
    if isinstance(value, tuple):
        return [_canonical_value(item) for item in value]
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if value is None or isinstance(value, (bool, int, str)):
        return value
    raise CommitPlanRejected(
        "commit-plan-not-canonical",
        f"unsupported canonical value type: {type(value).__name__}",
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _publication_digest(kind: str, value: Any) -> bytes:
    payload = _canonical_json(value).encode("utf-8")
    digest = hashlib.sha256()
    for part in (
        _PUBLICATION_INTEGRITY_VERSION.encode("ascii"),
        kind.encode("ascii"),
        payload,
    ):
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)
    return digest.digest()


def _publication_uuid_bytes(value: str, field: str) -> bytes:
    try:
        return UUID(value).bytes
    except (AttributeError, TypeError, ValueError) as error:
        raise CommitPlanRejected(
            "commit-plan-invalid-identity",
            f"{field} must be a canonical UUID",
        ) from error


def _publication_digest_bytes(
    value: str | None,
    field: str,
) -> bytes | None:
    if value is None:
        return None
    try:
        result = bytes.fromhex(value)
    except (TypeError, ValueError) as error:
        raise CommitPlanRejected(
            "commit-plan-invalid-digest",
            f"{field} must be a SHA-256 hex digest",
        ) from error
    if len(result) != 32 or value != result.hex():
        raise CommitPlanRejected(
            "commit-plan-invalid-digest",
            f"{field} must be lowercase canonical SHA-256 hex",
        )
    return result


def _command_fingerprint(
    *,
    contract_version: str,
    kind: str,
    target_profile_id: str,
    target_timeline_id: str,
    declared_intent: str,
    utterance: str,
    language: str,
    provenance: str,
    normalization_version: str,
) -> str:
    return _fingerprint_tuple(
        (
            contract_version,
            kind,
            target_profile_id,
            target_timeline_id,
            declared_intent,
            utterance,
            language,
            provenance,
            normalization_version,
        )
    )


@dataclass(frozen=True)
class SubjectCommand:
    contract_version: str
    kind: str
    target_profile_id: str
    target_timeline_id: str
    declared_intent: str
    utterance: str
    language: str
    provenance: str
    normalization_version: str
    payload_fingerprint: str

    def __post_init__(self) -> None:
        if self.contract_version != CONTRACT_VERSION:
            raise PreAdmissionRejected(
                "unsupported-contract-version",
                "SubjectCommand contract version is not supported",
            )
        if self.kind != COMMAND_KIND:
            raise PreAdmissionRejected(
                "unsupported-command-kind",
                "M0 Admission accepts only ContributeUtterance",
            )
        if self.normalization_version != NORMALIZATION_VERSION:
            raise PreAdmissionRejected(
                "unsupported-normalization-version",
                "SubjectCommand normalization version is not supported",
            )
        expected_values = {
            "target_profile_id": _canonical_uuid(
                self.target_profile_id,
                "target_profile_id",
            ),
            "target_timeline_id": _canonical_uuid(
                self.target_timeline_id,
                "target_timeline_id",
            ),
            "declared_intent": _normalize_text(
                self.declared_intent,
                "declared_intent",
                maximum=128,
            ),
            "utterance": _normalize_text(
                self.utterance,
                "utterance",
                maximum=32_768,
            ),
            "language": _normalize_text(
                self.language,
                "language",
                maximum=32,
            ).lower(),
            "provenance": _normalize_text(
                self.provenance,
                "provenance",
                maximum=128,
            ),
        }
        for field, expected in expected_values.items():
            if getattr(self, field) != expected:
                raise PreAdmissionRejected(
                    "malformed-command",
                    f"{field} is not in canonical normalized form",
                )
        expected_fingerprint = _command_fingerprint(
            contract_version=self.contract_version,
            kind=self.kind,
            target_profile_id=self.target_profile_id,
            target_timeline_id=self.target_timeline_id,
            declared_intent=self.declared_intent,
            utterance=self.utterance,
            language=self.language,
            provenance=self.provenance,
            normalization_version=self.normalization_version,
        )
        if self.payload_fingerprint != expected_fingerprint:
            raise PreAdmissionRejected(
                "payload-fingerprint-mismatch",
                "SubjectCommand fingerprint does not match normalized content",
            )

    @classmethod
    def contribute_utterance(
        cls,
        *,
        target_profile_id: str,
        target_timeline_id: str,
        declared_intent: str,
        utterance: str,
        language: str,
        provenance: str,
    ) -> SubjectCommand:
        profile_id = _canonical_uuid(target_profile_id, "target_profile_id")
        timeline_id = _canonical_uuid(target_timeline_id, "target_timeline_id")
        intent = _normalize_text(declared_intent, "declared_intent", maximum=128)
        normalized_utterance = _normalize_text(
            utterance,
            "utterance",
            maximum=32_768,
        )
        normalized_language = _normalize_text(
            language,
            "language",
            maximum=32,
        ).lower()
        normalized_provenance = _normalize_text(
            provenance,
            "provenance",
            maximum=128,
        )
        fingerprint = _command_fingerprint(
            contract_version=CONTRACT_VERSION,
            kind=COMMAND_KIND,
            target_profile_id=profile_id,
            target_timeline_id=timeline_id,
            declared_intent=intent,
            utterance=normalized_utterance,
            language=normalized_language,
            provenance=normalized_provenance,
            normalization_version=NORMALIZATION_VERSION,
        )
        return cls(
            contract_version=CONTRACT_VERSION,
            kind=COMMAND_KIND,
            target_profile_id=profile_id,
            target_timeline_id=timeline_id,
            declared_intent=intent,
            utterance=normalized_utterance,
            language=normalized_language,
            provenance=normalized_provenance,
            normalization_version=NORMALIZATION_VERSION,
            payload_fingerprint=fingerprint,
        )

    @classmethod
    def from_dict(cls, source: Mapping[str, Any]) -> SubjectCommand:
        if source.get("contract_version") != CONTRACT_VERSION:
            raise PreAdmissionRejected(
                "unsupported-contract-version",
                "SubjectCommand contract version is not supported",
            )
        if source.get("kind") != COMMAND_KIND:
            raise PreAdmissionRejected(
                "unsupported-command-kind",
                "M0 Admission accepts only ContributeUtterance",
            )
        if source.get("normalization_version") != NORMALIZATION_VERSION:
            raise PreAdmissionRejected(
                "unsupported-normalization-version",
                "SubjectCommand normalization version is not supported",
            )
        command = cls.contribute_utterance(
            target_profile_id=str(source.get("target_profile_id", "")),
            target_timeline_id=str(source.get("target_timeline_id", "")),
            declared_intent=str(source.get("declared_intent", "")),
            utterance=str(source.get("utterance", "")),
            language=str(source.get("language", "")),
            provenance=str(source.get("provenance", "")),
        )
        supplied = source.get("payload_fingerprint")
        if supplied is not None and supplied != command.payload_fingerprint:
            raise PreAdmissionRejected(
                "payload-fingerprint-mismatch",
                "SubjectCommand fingerprint does not match normalized content",
            )
        return command

    def to_dict(self) -> dict[str, str]:
        return {
            "contract_version": self.contract_version,
            "kind": self.kind,
            "target_profile_id": self.target_profile_id,
            "target_timeline_id": self.target_timeline_id,
            "declared_intent": self.declared_intent,
            "utterance": self.utterance,
            "language": self.language,
            "provenance": self.provenance,
            "normalization_version": self.normalization_version,
            "payload_fingerprint": self.payload_fingerprint,
        }


@dataclass(frozen=True)
class FixtureAuthority:
    authority_scope_id: str
    profile_id: str
    timeline_id: str
    allowed_intents: tuple[str, ...]
    allowed_provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "authority_scope_id",
            _canonical_uuid(self.authority_scope_id, "authority_scope_id"),
        )
        object.__setattr__(
            self,
            "profile_id",
            _canonical_uuid(self.profile_id, "profile_id"),
        )
        object.__setattr__(
            self,
            "timeline_id",
            _canonical_uuid(self.timeline_id, "timeline_id"),
        )
        if not self.allowed_intents or not self.allowed_provenance:
            raise PreAdmissionRejected(
                "malformed-fixture-authority",
                "fixture authority must constrain intent and provenance",
            )
        object.__setattr__(
            self,
            "allowed_intents",
            tuple(
                _normalize_text(item, "allowed_intent", maximum=128)
                for item in self.allowed_intents
            ),
        )
        object.__setattr__(
            self,
            "allowed_provenance",
            tuple(
                _normalize_text(item, "allowed_provenance", maximum=128)
                for item in self.allowed_provenance
            ),
        )

    @classmethod
    def from_dict(cls, source: Mapping[str, Any]) -> FixtureAuthority:
        return cls(
            authority_scope_id=str(source.get("authority_scope_id", "")),
            profile_id=str(source.get("profile_id", "")),
            timeline_id=str(source.get("timeline_id", "")),
            allowed_intents=tuple(source.get("allowed_intents", ())),
            allowed_provenance=tuple(source.get("allowed_provenance", ())),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority_scope_id": self.authority_scope_id,
            "profile_id": self.profile_id,
            "timeline_id": self.timeline_id,
            "allowed_intents": list(self.allowed_intents),
            "allowed_provenance": list(self.allowed_provenance),
        }


@dataclass(frozen=True)
class _RuntimeBindingAuthority:
    """Private Timeline fencing token; ControlStore remains binding authority."""

    authority_scope_id: str
    profile_id: str
    timeline_id: str
    allowed_intents: tuple[str, ...]
    allowed_provenance: tuple[str, ...]
    binding_id: str
    binding_revision: int
    binding_epoch: int
    qualification_id: str
    qualification_revision: int
    provider_authority: str

    def __post_init__(self) -> None:
        for field in (
            "authority_scope_id",
            "profile_id",
            "timeline_id",
            "binding_id",
            "qualification_id",
        ):
            object.__setattr__(
                self, field, _canonical_uuid(getattr(self, field), field)
            )
        if self.binding_revision < 1 or self.binding_epoch < 1:
            raise PreAdmissionRejected(
                "binding-version-invalid",
                "binding revision and epoch must be positive",
            )
        if self.qualification_revision < 1:
            raise PreAdmissionRejected(
                "qualification-version-invalid",
                "qualification revision must be positive",
            )
        if not self.allowed_intents or not self.allowed_provenance:
            raise PreAdmissionRejected(
                "binding-capability-invalid",
                "runtime binding must constrain intent and provenance",
            )
        object.__setattr__(
            self,
            "allowed_intents",
            tuple(
                _normalize_text(item, "allowed_intent", maximum=128)
                for item in self.allowed_intents
            ),
        )
        object.__setattr__(
            self,
            "allowed_provenance",
            tuple(
                _normalize_text(item, "allowed_provenance", maximum=128)
                for item in self.allowed_provenance
            ),
        )
        object.__setattr__(
            self,
            "provider_authority",
            _normalize_text(
                self.provider_authority,
                "provider_authority",
                maximum=256,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority_kind": "published-qri-binding",
            "authority_scope_id": self.authority_scope_id,
            "profile_id": self.profile_id,
            "timeline_id": self.timeline_id,
            "allowed_intents": list(self.allowed_intents),
            "allowed_provenance": list(self.allowed_provenance),
            "binding_id": self.binding_id,
            "binding_revision": self.binding_revision,
            "binding_epoch": self.binding_epoch,
            "qualification_id": self.qualification_id,
            "qualification_revision": self.qualification_revision,
            "provider_authority": self.provider_authority,
        }


@dataclass(frozen=True)
class _AdmissionGateView:
    authority: FixtureAuthority | _RuntimeBindingAuthority
    gate_epoch: int
    state: str
    data_control_scope_id: str | None


@dataclass(frozen=True)
class CanonicalRootRef:
    root_path: str
    root_id: str
    control_store_id: str
    timeline_store_id: str
    timeline_id: str
    root_kind: str = ROOT_KIND

    def __post_init__(self) -> None:
        if not Path(self.root_path).is_absolute():
            raise AdmissionFailedClosed(
                "canonical-root-not-allowed",
                "canonical root reference must be absolute",
            )
        for field in (
            "root_id",
            "control_store_id",
            "timeline_store_id",
            "timeline_id",
        ):
            object.__setattr__(
                self,
                field,
                _canonical_store_uuid(getattr(self, field), field),
            )
        if self.root_kind not in _ROOT_KINDS:
            raise AdmissionFailedClosed(
                "canonical-root-kind-not-allowed",
                "canonical root kind must be test-fixture or experimental",
            )

    @property
    def root(self) -> Path:
        return Path(self.root_path)

    @property
    def control_database(self) -> Path:
        return self.root / "control" / "control.sqlite3"

    @property
    def timeline_database(self) -> Path:
        return self.root / "timelines" / self.timeline_id / "timeline.sqlite3"

    @classmethod
    def from_dict(cls, source: Mapping[str, Any]) -> CanonicalRootRef:
        root_path = str(source.get("root_path", ""))
        if not Path(root_path).is_absolute():
            raise AdmissionFailedClosed(
                "canonical-root-not-allowed",
                "canonical root reference must be absolute",
            )
        return cls(
            root_path=root_path,
            root_id=_canonical_store_uuid(str(source.get("root_id", "")), "root_id"),
            control_store_id=_canonical_store_uuid(
                str(source.get("control_store_id", "")),
                "control_store_id",
            ),
            timeline_store_id=_canonical_store_uuid(
                str(source.get("timeline_store_id", "")),
                "timeline_store_id",
            ),
            timeline_id=_canonical_store_uuid(
                str(source.get("timeline_id", "")),
                "timeline_id",
            ),
            root_kind=str(source.get("root_kind", ROOT_KIND)),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "root_path": self.root_path,
            "root_id": self.root_id,
            "control_store_id": self.control_store_id,
            "timeline_store_id": self.timeline_store_id,
            "timeline_id": self.timeline_id,
            "root_kind": self.root_kind,
        }


@dataclass(frozen=True)
class _ReservedTimelineIdentity:
    """Exact private store identities consumed by one confirmed Host activation."""

    root_id: str
    control_store_id: str
    timeline_store_id: str

    def __post_init__(self) -> None:
        for field in ("root_id", "control_store_id", "timeline_store_id"):
            object.__setattr__(
                self,
                field,
                _canonical_store_uuid(getattr(self, field), field),
            )

    def location(
        self,
        base: Path,
        *,
        timeline_id: str,
        root_kind: str,
    ) -> CanonicalRootRef:
        return CanonicalRootRef(
            root_path=str(base / "mature-runtime-m0" / "roots" / self.root_id),
            root_id=self.root_id,
            control_store_id=self.control_store_id,
            timeline_store_id=self.timeline_store_id,
            timeline_id=timeline_id,
            root_kind=root_kind,
        )

@dataclass(frozen=True)
class OperationRef:
    contract_version: str
    root_id: str
    timeline_store_id: str
    authority_scope_id: str
    operation_id: str
    operation_kind: OperationKind
    admitted_payload_fingerprint: str

    def __post_init__(self) -> None:
        try:
            kind = OperationKind(self.operation_kind)
        except ValueError as error:
            raise AdmissionFailedClosed(
                "operation-ref-kind-invalid",
                "OperationRef kind is not part of the closed operation union",
            ) from error
        object.__setattr__(self, "operation_kind", kind)


@dataclass(frozen=True)
class Admitted:
    operation_ref: OperationRef
    attempt_id: str
    replayed: bool
    recovered_after_commit: bool = False


@dataclass(frozen=True)
class AdmissionSnapshot:
    operation_ref: OperationRef
    operation_state: OperationState
    attempt_id: str
    attempt_state: AttemptState
    subject_event_id: str
    timeline_head_sequence: int
    timeline_basis: TimelineBasis
    admitted_at_us: int
    timeline_outcome_id: str | None = None


@dataclass(frozen=True)
class OperationFailure:
    """Canonical terminal fact for a pre-Publication cycle failure."""

    operation_ref: OperationRef
    attempt_id: str
    stage: str
    code: str
    detail: str
    recorded_at_us: int


@dataclass(frozen=True)
class TimelineBasis:
    head_sequence: int
    published_outcome_digest: str | None
    verified_prefix_digest: str
    revision_head_digest: str


@dataclass(frozen=True)
class ConversationOutcomeSummary:
    """Display facts derived from a verified turn, never from today's state."""
    living_memory_status: str
    living_memory_recalled_count: int
    memory_content: str | None
    knowledge_status: str | None
    knowledge_citation_ids: tuple[str, ...]
    relationship_status: str | None
    relationship_candidate_event: str | None
    participant_goal_commitment_status: str | None
    participant_goal_commitment_action: str | None
    participant_goal_commitment_selected_count: int
    situated_state_status: str | None
    situated_state_action: str | None
    situated_state_posture: str | None
    situated_state_reason_code: str | None
    medium_state_status: str | None
    medium_state_baseline: str | None
    medium_state_before_baseline: str | None
    medium_state_reason_code: str | None
    medium_state_signal: str | None
    memory_revision: bool | None = None
    preference_question: object | None = None
    memory_withdrawal_status: str | None = None

    @classmethod
    def from_outcome(cls, outcome: TimelineOutcome) -> ConversationOutcomeSummary:
        experience = outcome.experience_outcome
        state = outcome.subject_state_outcome
        return cls(
            living_memory_status=experience.living_memory_status.value,
            living_memory_recalled_count=len(experience.living_memory_recalled_ids),
            memory_content=experience.living_memory_content,
            knowledge_status=experience.knowledge_status,
            knowledge_citation_ids=experience.knowledge_citation_ids,
            relationship_status=outcome.relationship_outcome.relationship_status,
            relationship_candidate_event=outcome.relationship_outcome.relationship_candidate_event,
            participant_goal_commitment_status=experience.participant_goal_commitment_status,
            participant_goal_commitment_action=experience.participant_goal_commitment_action,
            participant_goal_commitment_selected_count=experience.participant_goal_commitment_selected_count,
            situated_state_status=state.situated_state_status,
            situated_state_action=state.situated_state_action,
            situated_state_posture=state.situated_state_posture,
            situated_state_reason_code=state.situated_state_reason_code,
            medium_state_status=state.medium_state_status,
            medium_state_baseline=state.medium_state_baseline,
            medium_state_before_baseline=state.medium_state_before_baseline,
            medium_state_reason_code=state.medium_state_reason_code,
            medium_state_signal=state.medium_state_signal,
            memory_revision=experience.memory_revision,
            preference_question=experience.preference_question,
            memory_withdrawal_status=experience.memory_withdrawal_status,
        )


@dataclass(frozen=True)
class ConversationTurnRecord:
    head_sequence: int
    user_text: str
    user_language: str
    assistant_text: str
    assistant_language: str
    published_at_us: int
    outcome_summary: ConversationOutcomeSummary | None = None


@dataclass(frozen=True)
class CandidateDecisionRecord:
    decision_id: str
    scope: str
    status: DecisionStatus
    reason: str
    rule_version: str
    actual_revision_ids: tuple[str, ...]


@dataclass(frozen=True)
class ExperienceRecord:
    experience_id: str
    summary: str
    experienced_at_us: int


@dataclass(frozen=True)
class EpistemicOutcome:
    epistemic_outcome_id: str
    status: DecisionStatus
    reason: str
    route_version: str
    verified_prefix_digest: str
    completed_stages: tuple[str, ...]


@dataclass(frozen=True)
class ExperienceDomainOutcome:
    outcome_id: str
    decision: CandidateDecisionRecord
    epistemic_outcome_id: str

    @property
    def memory_withdrawal_status(self) -> str | None:
        if self._text_fact('living_memory', 'action') != 'forget':
            return None
        return self.living_memory_status.value

    @property
    def memory_revision(self) -> bool | None:
        try:
            value = json.loads(self.decision.reason)
            if not isinstance(value, dict):
                return None
            memory = value.get('living_memory')
            if memory is None:
                if value.get('code') == 'preference.question':
                    return False if self.preference_question is not None and set(value) <= {'code', 'provenance', 'preference_question', 'knowledge', 'participant_goal_commitment'} else None
                code = value.get('code')
                if isinstance(code, str) and code in PARTICIPANT_GOAL_FAILURE_CODES:
                    goal = value.get('participant_goal_commitment')
                    return False if (
                        self.decision.rule_version == 'experience-1.0'
                        and set(value) <= {'code', 'provenance', 'participant_goal_commitment'}
                        and goal == {'status': 'failed-closed', 'action': 'noop', 'reason_code': code}
                    ) else None
                known_codes = {'experience.no-applicable-candidate', 'knowledge.accepted',
                    'knowledge.identity-invalid', 'knowledge.no-projected-candidates',
                    'knowledge.citation-not-projected', 'knowledge.citation-duplicated',
                    'knowledge-provider-failed', 'knowledge-provider-invalid-output',
                    'participant-goal.selected-for-reply'}
                return False if (isinstance(value.get('code'), str) and value['code'] in known_codes
                    and set(value) <= {'code', 'provenance', 'knowledge', 'participant_goal_commitment'}
                    and self.decision.rule_version in {'m0-domain-noop-1.0', 'experience-1.0'}) else None
            if not isinstance(memory, dict) or self.decision.rule_version != 'experience-1.0':
                return None
            if value.get('code') == 'living-memory.forgotten' and memory.get('status') == 'accepted':
                if set(memory) != {'status', 'action', 'target_memory_id', 'reason_code', 'source_user_message_id'} or memory['action'] != 'forget' or memory['reason_code'] != 'selected':
                    return None
                UUID(memory['target_memory_id'])
                UUID(memory['source_user_message_id'])
                return True
            if value.get('code') == 'living-memory.recalled' and memory.get('status') == 'no-op':
                if set(memory) != {'status', 'recalled_memory_ids'} or not isinstance(memory['recalled_memory_ids'], list):
                    return None
                for memory_id in memory['recalled_memory_ids']:
                    UUID(memory_id)
                return False
            required = {'status', 'memory_id', 'content', 'source_user_message_id', 'supersedes_memory_id', 'memory_kind'}
            if (value.get('code') != 'living-memory.accepted' or memory.get('status') != 'accepted'
                or not required <= set(memory) or not set(memory) <= required | {'temporal_anchor', 'preference_confirmation'}
                or not isinstance(memory['content'], str) or not memory['content'].strip()
                or memory['memory_kind'] not in {'durable', 'plan'}):
                return None
            if 'preference_confirmation' in memory:
                from dynamic_subject_agent.preference_clarification import valid_confirmation
                if not valid_confirmation(memory['preference_confirmation']) or memory['source_user_message_id'] != memory['preference_confirmation']['source_id']:
                    return None
            UUID(memory['memory_id'])
            UUID(memory['source_user_message_id'])
            previous = memory['supersedes_memory_id']
            if previous is None:
                return False
            UUID(previous)
            return True
        except (ValueError, TypeError, AttributeError):
            return None

    def _text_fact(self, capability: str, field: str) -> str | None:
        try:
            value = json.loads(self.decision.reason).get(capability, {}).get(field)
            return value if isinstance(value, str) else None
        except (AttributeError, TypeError, json.JSONDecodeError):
            return None

    @property
    def living_memory_content(self) -> str | None:
        if self.living_memory_status is not LivingMemoryDecisionStatus.ACCEPTED:
            return None
        return self._text_fact('living_memory', 'content')

    @property
    def preference_question(self):
        from dynamic_subject_agent.preference_clarification import PreferenceQuestion
        try:
            value = json.loads(self.decision.reason)
            return PreferenceQuestion.parse(value.get('preference_question')) if self.decision.rule_version == 'experience-1.0' and value.get('code') == 'preference.question' else None
        except (ValueError, TypeError, AttributeError):
            return None

    @property
    def living_memory_status(self) -> LivingMemoryDecisionStatus:
        try:
            reason = json.loads(self.decision.reason)
            memory = reason.get("living_memory", {})
            return LivingMemoryDecisionStatus(memory.get("status", "no-op"))
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            return LivingMemoryDecisionStatus.NO_OP

    @property
    def living_memory_recalled_ids(self) -> tuple[str, ...]:
        try:
            reason = json.loads(self.decision.reason)
            recalled = reason.get("living_memory", {}).get(
                "recalled_memory_ids",
                (),
            )
            return tuple(str(UUID(memory_id)) for memory_id in recalled)
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            return ()

    @property
    def knowledge_citation_ids(self) -> tuple[str, ...]:
        try:
            reason = json.loads(self.decision.reason)
            knowledge = reason.get("knowledge", {})
            if knowledge.get("status") != "accepted":
                return ()
            return tuple(
                str(entry_id) for entry_id in knowledge.get("cited_entry_ids", ())
            )
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            return ()

    @property
    def knowledge_status(self) -> str | None:
        try:
            value = json.loads(self.decision.reason).get("knowledge", {}).get("status")
            return (
                value
                if value in {"accepted", "rejected", "failed-closed"}
                else None
            )
        except (AttributeError, TypeError, json.JSONDecodeError):
            return None

    @property
    def participant_goal_commitment_status(self) -> str | None:
        try:
            value = json.loads(self.decision.reason).get(
                "participant_goal_commitment",
                {},
            ).get("status")
            return (
                value
                if value in {"accepted", "rejected", "no-update", "failed-closed"}
                else None
            )
        except (AttributeError, TypeError, json.JSONDecodeError):
            return None

    @property
    def participant_goal_commitment_action(self) -> str | None:
        try:
            value = json.loads(self.decision.reason).get(
                "participant_goal_commitment",
                {},
            ).get("action")
            return value if value in {"create", "revise", "transition", "noop"} else None
        except (AttributeError, TypeError, json.JSONDecodeError):
            return None

    @property
    def participant_goal_commitment_reason_code(self) -> str | None:
        try:
            value = json.loads(self.decision.reason).get(
                "participant_goal_commitment",
                {},
            ).get("reason_code")
            return value if isinstance(value, str) and value.strip() else None
        except (AttributeError, TypeError, json.JSONDecodeError):
            return None

    @property
    def participant_goal_commitment_selected_count(self) -> int:
        try:
            value = json.loads(self.decision.reason).get(
                "participant_goal_commitment",
                {},
            ).get("selected_count", 0)
            return value if isinstance(value, int) and 0 <= value <= 5 else 0
        except (AttributeError, TypeError, json.JSONDecodeError):
            return 0

    @property
    def participant_goal_commitment_terms(self) -> str | None:
        return self._text_fact('participant_goal_commitment', 'terms')

    @property
    def participant_goal_commitment_kind(self) -> str | None:
        value = self._text_fact('participant_goal_commitment', 'kind')
        return value if value in {'goal', 'commitment'} else None

    @property
    def participant_goal_commitment_next_status(self) -> str | None:
        value = self._text_fact('participant_goal_commitment', 'next_status')
        return value if isinstance(value, str) else None



@dataclass(frozen=True)
class RelationshipStanceInteraction:
    event: str
    evidence_quote: str
    source_user_message_id: str
    policy_version: str
    status: str
    head_sequence: int

@dataclass(frozen=True)
class LivingMemoryRecord:
    memory_id: str
    content: str
    source_user_message_id: str
    status: str
    supersedes_memory_id: str | None = None
    memory_kind: str = "durable"
    temporal_anchor: TemporalAnchor | None = None
    preference_additive: bool = False
    preference_confirmed: bool = False


@dataclass(frozen=True)
class SubjectCoreOutcome:
    outcome_id: str
    decision: CandidateDecisionRecord


@dataclass(frozen=True)
class DevelopmentOutcome:
    outcome_id: str
    decision: CandidateDecisionRecord


@dataclass(frozen=True)
class SubjectStateDomainOutcome:
    outcome_id: str
    decision: CandidateDecisionRecord
    subject_core: SubjectCoreOutcome
    development: DevelopmentOutcome

    @property
    def situated_state_status(self) -> str | None:
        try:
            value = json.loads(self.subject_core.decision.reason).get(
                "situated_state", {}
            ).get("status")
            return (
                value
                if value in {"accepted", "rejected", "no-update", "failed-closed"}
                else None
            )
        except (AttributeError, TypeError, json.JSONDecodeError):
            return None

    @property
    def situated_state_action(self) -> str | None:
        try:
            value = json.loads(self.subject_core.decision.reason).get(
                "situated_state", {}
            ).get("action")
            return value if value in {"set", "carry", "consume", "noop"} else None
        except (AttributeError, TypeError, json.JSONDecodeError):
            return None

    @property
    def situated_state_posture(self) -> str | None:
        try:
            value = json.loads(self.subject_core.decision.reason).get(
                "situated_state", {}
            ).get("posture")
            return value if value in SITUATED_POSTURES else None
        except (AttributeError, TypeError, json.JSONDecodeError):
            return None

    @property
    def medium_state_status(self) -> str | None:
        try:
            value = json.loads(self.subject_core.decision.reason).get(
                "medium_state", {}
            ).get("status")
            return (
                value
                if value in {"accepted", "rejected", "no-update", "failed-closed"}
                else None
            )
        except (AttributeError, TypeError, json.JSONDecodeError):
            return None

    @property
    def medium_state_baseline(self) -> str | None:
        try:
            value = json.loads(self.subject_core.decision.reason).get(
                "medium_state", {}
            ).get("after_baseline")
            return value if value in MEDIUM_BASELINES else None
        except (AttributeError, TypeError, json.JSONDecodeError):
            return None

    @property
    def situated_state_reason_code(self) -> str | None:
        try:
            value = json.loads(self.subject_core.decision.reason).get(
                "situated_state", {}
            ).get("reason_code")
            return value if isinstance(value, str) and value.strip() else None
        except (AttributeError, TypeError, json.JSONDecodeError):
            return None

    @property
    def medium_state_reason_code(self) -> str | None:
        try:
            value = json.loads(self.subject_core.decision.reason).get(
                "medium_state", {}
            ).get("reason_code")
            return value if isinstance(value, str) and value.strip() else None
        except (AttributeError, TypeError, json.JSONDecodeError):
            return None

    @property
    def medium_state_signal(self) -> str | None:
        try:
            value = json.loads(self.subject_core.decision.reason).get(
                "medium_state", {}
            ).get("signal")
            return value if value in {"concern", "encouragement", "settling"} else None
        except (AttributeError, TypeError, json.JSONDecodeError):
            return None

    @property
    def medium_state_before_baseline(self) -> str | None:
        try:
            value = json.loads(self.subject_core.decision.reason).get(
                "medium_state", {}
            ).get("before_baseline")
            return value if value in MEDIUM_BASELINES else None
        except (AttributeError, TypeError, json.JSONDecodeError):
            return None


@dataclass(frozen=True)
class AgencyDomainOutcome:
    outcome_id: str
    decision: CandidateDecisionRecord
    committed_effect_eligible: bool


@dataclass(frozen=True)
class RelationshipDomainOutcome:
    outcome_id: str
    decision: CandidateDecisionRecord
    relationship_target_id: str


    @property
    def relationship_event(self) -> str:
        try:
            reason = json.loads(self.decision.reason)
            relationship = reason.get("relationship", {})
            if relationship.get("status") != "accepted":
                return ""
            return str(relationship.get("event", ""))
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            return ""

    @property
    def relationship_status(self) -> str | None:
        try:
            value = json.loads(self.decision.reason).get("relationship", {}).get("status")
            return (
                value
                if value in {"accepted", "rejected", "no-update", "failed-closed"}
                else None
            )
        except (AttributeError, TypeError, json.JSONDecodeError):
            return None

    @property
    def relationship_candidate_event(self) -> str | None:
        try:
            value = json.loads(self.decision.reason).get("relationship", {}).get(
                "event"
            )
            return value if isinstance(value, str) and value.strip() else None
        except (AttributeError, TypeError, json.JSONDecodeError):
            return None

    @property
    def relationship_reason_code(self) -> str | None:
        try:
            value = json.loads(self.decision.reason).get("code")
            return value if isinstance(value, str) and value.strip() else None
        except (AttributeError, TypeError, json.JSONDecodeError):
            return None

@dataclass(frozen=True)
class RevisionSet:
    revision_set_id: str
    revision_ids: tuple[str, ...]


@dataclass(frozen=True)
class Expression:
    expression_id: str
    text: str
    language: str
    grounding_decision_ids: tuple[str, ...]


@dataclass(frozen=True)
class CommittedEffectSet:
    effect_set_id: str
    reference_ids: tuple[str, ...]
    dispatch_state: EffectDispatchState
    reason: str


@dataclass(frozen=True)
class CycleCommitPlan:
    plan_id: str
    cycle_plan_id: str
    operation_ref: OperationRef
    attempt_id: str
    subject_event_id: str
    profile_id: str
    timeline_id: str
    expected_basis: TimelineBasis
    experience: ExperienceRecord
    epistemic_outcome: EpistemicOutcome
    experience_outcome: ExperienceDomainOutcome
    subject_state_outcome: SubjectStateDomainOutcome
    agency_outcome: AgencyDomainOutcome
    relationship_outcome: RelationshipDomainOutcome
    revision_set: RevisionSet
    expression: Expression
    committed_effect_set: CommittedEffectSet
    life_record: LifeRecord | None = None

    def to_dict(self) -> dict[str, Any]:
        return _canonical_value(self)

    @classmethod
    def from_dict(cls, source: Mapping[str, Any]) -> CycleCommitPlan:
        def decision(value: Mapping[str, Any]) -> CandidateDecisionRecord:
            return CandidateDecisionRecord(
                decision_id=str(value["decision_id"]),
                scope=str(value["scope"]),
                status=DecisionStatus(str(value["status"])),
                reason=str(value["reason"]),
                rule_version=str(value["rule_version"]),
                actual_revision_ids=tuple(value["actual_revision_ids"]),
            )

        try:
            operation = source["operation_ref"]
            basis = source["expected_basis"]
            experience = source["experience"]
            epistemic = source["epistemic_outcome"]
            experience_outcome = source["experience_outcome"]
            subject_state = source["subject_state_outcome"]
            subject_core = subject_state["subject_core"]
            development = subject_state["development"]
            agency = source["agency_outcome"]
            relationship = source["relationship_outcome"]
            revision = source["revision_set"]
            expression = source["expression"]
            effects = source["committed_effect_set"]
            return cls(
                plan_id=str(source["plan_id"]),
                cycle_plan_id=str(source["cycle_plan_id"]),
                operation_ref=OperationRef(
                    contract_version=str(operation["contract_version"]),
                    root_id=str(operation["root_id"]),
                    timeline_store_id=str(operation["timeline_store_id"]),
                    authority_scope_id=str(operation["authority_scope_id"]),
                    operation_id=str(operation["operation_id"]),
                    operation_kind=OperationKind(str(operation["operation_kind"])),
                    admitted_payload_fingerprint=str(
                        operation["admitted_payload_fingerprint"]
                    ),
                ),
                attempt_id=str(source["attempt_id"]),
                subject_event_id=str(source["subject_event_id"]),
                profile_id=str(source["profile_id"]),
                timeline_id=str(source["timeline_id"]),
                expected_basis=TimelineBasis(
                    head_sequence=int(basis["head_sequence"]),
                    published_outcome_digest=(
                        None
                        if basis["published_outcome_digest"] is None
                        else str(basis["published_outcome_digest"])
                    ),
                    verified_prefix_digest=str(basis["verified_prefix_digest"]),
                    revision_head_digest=str(basis["revision_head_digest"]),
                ),
                experience=ExperienceRecord(
                    experience_id=str(experience["experience_id"]),
                    summary=str(experience["summary"]),
                    experienced_at_us=int(experience["experienced_at_us"]),
                ),
                epistemic_outcome=EpistemicOutcome(
                    epistemic_outcome_id=str(epistemic["epistemic_outcome_id"]),
                    status=DecisionStatus(str(epistemic["status"])),
                    reason=str(epistemic["reason"]),
                    route_version=str(epistemic["route_version"]),
                    verified_prefix_digest=str(epistemic["verified_prefix_digest"]),
                    completed_stages=tuple(epistemic["completed_stages"]),
                ),
                experience_outcome=ExperienceDomainOutcome(
                    outcome_id=str(experience_outcome["outcome_id"]),
                    decision=decision(experience_outcome["decision"]),
                    epistemic_outcome_id=str(
                        experience_outcome["epistemic_outcome_id"]
                    ),
                ),
                subject_state_outcome=SubjectStateDomainOutcome(
                    outcome_id=str(subject_state["outcome_id"]),
                    decision=decision(subject_state["decision"]),
                    subject_core=SubjectCoreOutcome(
                        outcome_id=str(subject_core["outcome_id"]),
                        decision=decision(subject_core["decision"]),
                    ),
                    development=DevelopmentOutcome(
                        outcome_id=str(development["outcome_id"]),
                        decision=decision(development["decision"]),
                    ),
                ),
                agency_outcome=AgencyDomainOutcome(
                    outcome_id=str(agency["outcome_id"]),
                    decision=decision(agency["decision"]),
                    committed_effect_eligible=bool(agency["committed_effect_eligible"]),
                ),
                relationship_outcome=RelationshipDomainOutcome(
                    outcome_id=str(relationship["outcome_id"]),
                    decision=decision(relationship["decision"]),
                    relationship_target_id=str(relationship["relationship_target_id"]),
                ),
                revision_set=RevisionSet(
                    revision_set_id=str(revision["revision_set_id"]),
                    revision_ids=tuple(revision["revision_ids"]),
                ),
                expression=Expression(
                    expression_id=str(expression["expression_id"]),
                    text=str(expression["text"]),
                    language=str(expression["language"]),
                    grounding_decision_ids=tuple(expression["grounding_decision_ids"]),
                ),
                committed_effect_set=CommittedEffectSet(
                    effect_set_id=str(effects["effect_set_id"]),
                    reference_ids=tuple(effects["reference_ids"]),
                    dispatch_state=EffectDispatchState(str(effects["dispatch_state"])),
                    reason=str(effects["reason"]),
                ),
                life_record=(decode_life_record(source["life_record"]) if source.get("life_record") is not None else None),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise CommitPlanRejected(
                "commit-plan-deserialization-failed",
                "serialized CycleCommitPlan is incomplete or invalid",
            ) from error


@dataclass(frozen=True)
class TimelineOutcome:
    outcome_id: str
    operation_ref: OperationRef
    attempt_id: str
    subject_event_id: str
    plan_id: str
    head_sequence: int
    previous_outcome_digest: str | None
    outcome_digest: str
    experience: ExperienceRecord
    epistemic_outcome: EpistemicOutcome
    experience_outcome: ExperienceDomainOutcome
    subject_state_outcome: SubjectStateDomainOutcome
    agency_outcome: AgencyDomainOutcome
    relationship_outcome: RelationshipDomainOutcome
    revision_set: RevisionSet
    expression: Expression
    committed_effect_set: CommittedEffectSet
    life_record: LifeRecord | None = None


@dataclass(frozen=True)
class Published:
    outcome: TimelineOutcome
    replayed: bool
    recovered_after_commit: bool = False

    @property
    def outcome_id(self) -> str:
        return self.outcome.outcome_id

    @property
    def head_sequence(self) -> int:
        return self.outcome.head_sequence


_FaultHook = Callable[[FaultPoint], None]


def _utc_microseconds() -> int:
    return time_ns() // 1_000


def _validate_idempotency_key(value: str) -> bytes:
    if not isinstance(value, str) or not _IDEMPOTENCY_PATTERN.fullmatch(value):
        raise PreAdmissionRejected(
            "malformed-idempotency-key",
            "idempotency key must be an opaque 16-256 character token",
        )
    return hashlib.sha256(value.encode("utf-8")).digest()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _nearest_existing_ancestor(path: Path) -> Path:
    candidate = path
    while not candidate.exists():
        if candidate.parent == candidate:
            break
        candidate = candidate.parent
    return candidate


def _is_linklike(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction is not None and is_junction())


def _has_linklike_component(path: Path, stop: Path) -> bool:
    candidate = path
    while True:
        if candidate.exists() and _is_linklike(candidate):
            return True
        if candidate == stop or candidate.parent == candidate:
            return False
        candidate = candidate.parent


def _experimental_base_shape_allowed(path: Path, temporary_root: Path) -> bool:
    if _is_relative_to(path, temporary_root):
        return True
    parent_parts = tuple(part.casefold() for part in path.parent.parts[-3:])
    return parent_parts == ("dynamicsubjectagent", "m0", "experiments")


def _reserved_artifact_activation_base_shape_allowed(path: Path) -> bool:
    parent_parts = tuple(part.casefold() for part in path.parent.parts[-3:])
    return parent_parts == (
        "dynamicsubjectagent",
        "post-m0",
        "artifact-activations",
    )


def _validate_experimental_host_base(host_root: Path) -> Path:
    requested = Path(host_root)
    if (
        not requested.is_absolute()
        or not requested.anchor
        or requested.anchor.startswith("\\\\")
        or any(marker in str(requested) for marker in "*?[]%${}")
    ):
        raise AdmissionFailedClosed(
            "canonical-root-not-allowed",
            "experimental Timeline base must be an exact absolute local path",
        )
    try:
        if str(UUID(requested.name)) != requested.name:
            raise ValueError
    except (ValueError, AttributeError):
        raise AdmissionFailedClosed(
            "canonical-root-not-allowed",
            "experimental Timeline base must name one Host identity",
        ) from None
    if (
        requested.parent.name != "host-roots"
        or requested.parent.parent.name != "mature-runtime-m0"
    ):
        raise AdmissionFailedClosed(
            "canonical-root-not-allowed",
            "experimental Timeline base is outside the Host layout",
        )
    experiment_base = requested.parents[2]
    try:
        if str(UUID(experiment_base.name)) != experiment_base.name:
            raise ValueError
        temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
        anchor = Path(requested.anchor).resolve(strict=True)
        resolved = requested.resolve(strict=True)
    except (OSError, ValueError, AttributeError) as error:
        raise AdmissionFailedClosed(
            "canonical-root-not-allowed",
            "experimental Timeline base identity cannot be verified",
        ) from error
    if (
        resolved != requested.resolve(strict=False)
        or not resolved.is_dir()
        or _has_linklike_component(requested, anchor)
        or not (
            _experimental_base_shape_allowed(experiment_base, temporary_root)
            or _reserved_artifact_activation_base_shape_allowed(experiment_base)
        )
        or any(
            part.casefold() in _RESERVED_TEST_PATH_SEGMENTS
            for part in resolved.parts
        )
    ):
        raise AdmissionFailedClosed(
            "canonical-root-not-allowed",
            "experimental Timeline base is outside dedicated authority",
        )
    return resolved


def _validate_runtime_base(test_base: Path, *, root_kind: str) -> Path:
    if root_kind == ROOT_KIND:
        return _validate_test_base(test_base)
    if root_kind == EXPERIMENTAL_ROOT_KIND:
        return _validate_experimental_host_base(test_base)
    raise AdmissionFailedClosed(
        "canonical-root-kind-not-allowed",
        "Timeline root kind is not recognized",
    )


def _validate_test_base(test_base: Path) -> Path:
    requested = Path(test_base)
    if not requested.is_absolute():
        raise AdmissionFailedClosed(
            "canonical-root-not-allowed",
            "test root authority must be an explicit absolute path",
        )
    temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
    ancestor = _nearest_existing_ancestor(requested)
    try:
        resolved_ancestor = ancestor.resolve(strict=True)
    except OSError as error:
        raise AdmissionFailedClosed(
            "canonical-root-not-allowed",
            "test root ancestor cannot be verified",
        ) from error
    if not _is_relative_to(resolved_ancestor, temporary_root):
        raise AdmissionFailedClosed(
            "canonical-root-not-allowed",
            "M0-A stores may only be created under the process temporary root",
        )

    prospective = requested.resolve(strict=False)
    if not _is_relative_to(prospective, temporary_root):
        raise AdmissionFailedClosed(
            "canonical-root-not-allowed",
            "requested test root escapes the process temporary root",
        )
    relative_requested = prospective.relative_to(temporary_root)
    if any(
        part.casefold() in _RESERVED_TEST_PATH_SEGMENTS
        for part in relative_requested.parts
    ):
        raise AdmissionFailedClosed(
            "canonical-root-not-allowed",
            "the requested test root contains a reserved path segment",
        )

    current = temporary_root
    for part in resolved_ancestor.relative_to(temporary_root).parts:
        current = current / part
        if current.is_symlink():
            raise AdmissionFailedClosed(
                "canonical-root-not-allowed",
                "test root ancestry must not contain symbolic links",
            )

    try:
        requested.mkdir(parents=True, exist_ok=True)
        resolved = requested.resolve(strict=True)
    except OSError as error:
        raise AdmissionFailedClosed(
            "canonical-root-not-allowed",
            "test root could not be prepared",
        ) from error
    if not _is_relative_to(resolved, temporary_root) or resolved.is_symlink():
        raise AdmissionFailedClosed(
            "canonical-root-not-allowed",
            "test root escaped the allowed temporary boundary",
        )
    return resolved


def _validate_existing_root(
    root: Path,
    expected_root_id: str,
    *,
    root_kind: str = ROOT_KIND,
) -> Path:
    if not root.is_absolute():
        raise AdmissionFailedClosed(
            "canonical-root-not-allowed",
            "canonical root must be absolute",
        )
    try:
        resolved = root.resolve(strict=True)
        temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
        anchor = Path(root.anchor).resolve(strict=True)
    except OSError as error:
        raise AdmissionFailedClosed(
            "canonical-root-not-allowed",
            "canonical root cannot be resolved",
        ) from error
    if root_kind not in _ROOT_KINDS:
        raise AdmissionFailedClosed(
            "canonical-root-kind-not-allowed",
            "canonical root kind is not recognized",
        )
    if root_kind == ROOT_KIND and not _is_relative_to(resolved, temporary_root):
        raise AdmissionFailedClosed(
            "canonical-root-not-allowed",
            "M0-A store is outside the temporary authority",
        )
    link_stop = temporary_root if root_kind == ROOT_KIND else anchor
    if _has_linklike_component(root, link_stop):
        raise AdmissionFailedClosed(
            "canonical-root-not-allowed",
            "canonical root must not traverse a link or junction",
        )
    if resolved.name != expected_root_id:
        raise AdmissionFailedClosed(
            "root-identity-mismatch",
            "root directory does not match root identity",
        )
    if resolved.parent.name != "roots" or resolved.parent.parent.name != (
        "mature-runtime-m0"
    ):
        raise AdmissionFailedClosed(
            "canonical-root-not-allowed",
            "canonical root layout is not recognized",
        )
    if root_kind == EXPERIMENTAL_ROOT_KIND:
        host_root = resolved.parents[2]
        _validate_experimental_host_base(host_root)
    for candidate in (
        resolved,
        resolved / "root.identity",
        resolved / "control" / "control.sqlite3",
    ):
        if _is_linklike(candidate):
            raise AdmissionFailedClosed(
                "canonical-root-not-allowed",
                "canonical root must not contain symbolic links",
            )
    return resolved


def _sqlite_uri(path: Path, mode: str) -> str:
    return f"{path.resolve().as_uri()}?mode={mode}"


def _connect_existing_writer(path: Path) -> sqlite3.Connection:
    if not path.is_file() or path.is_symlink() or path.stat().st_nlink != 1:
        raise AdmissionFailedClosed(
            "store-missing",
            "canonical SQLite store is missing or has a linked identity",
        )
    try:
        connection = sqlite3.connect(
            _sqlite_uri(path, "rw"),
            uri=True,
            autocommit=True,
            timeout=2.0,
            check_same_thread=True,
        )
        connection.execute("PRAGMA synchronous = EXTRA")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA secure_delete = ON")
        connection.execute("PRAGMA busy_timeout = 2000")
        return connection
    except sqlite3.Error as error:
        raise AdmissionFailedClosed(
            "store-open-failed",
            "canonical SQLite store could not be opened",
        ) from error


def _connect_new_writer(path: Path) -> sqlite3.Connection:
    if path.exists():
        raise AdmissionFailedClosed(
            "store-already-exists",
            "new canonical store path must not already exist",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        connection = sqlite3.connect(
            _sqlite_uri(path, "rwc"),
            uri=True,
            autocommit=True,
            timeout=2.0,
            check_same_thread=True,
        )
        journal_mode = connection.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
        connection.execute("PRAGMA synchronous = EXTRA")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA secure_delete = ON")
        connection.execute("PRAGMA busy_timeout = 2000")
        if str(journal_mode).lower() != "delete":
            raise AdmissionFailedClosed(
                "connection-profile-mismatch",
                "canonical store did not enter DELETE journal mode",
            )
        return connection
    except AdmissionFailedClosed:
        raise
    except sqlite3.Error as error:
        raise AdmissionFailedClosed(
            "store-create-failed",
            "canonical SQLite store could not be created",
        ) from error


def _verify_connection_profile(connection: sqlite3.Connection) -> None:
    journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
    synchronous = int(connection.execute("PRAGMA synchronous").fetchone()[0])
    foreign_keys = int(connection.execute("PRAGMA foreign_keys").fetchone()[0])
    secure_delete = int(connection.execute("PRAGMA secure_delete").fetchone()[0])
    if (
        journal_mode != "delete"
        or synchronous != 3
        or foreign_keys != 1
        or secure_delete != 1
    ):
        raise AdmissionFailedClosed(
            "connection-profile-mismatch",
            "canonical SQLite connection profile is not the frozen M0 profile",
        )


_STORE_MANIFEST_DDL = """
CREATE TABLE store_manifest (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    root_id TEXT NOT NULL,
    store_id TEXT NOT NULL UNIQUE,
    store_kind TEXT NOT NULL,
    schema_family TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    contract_version TEXT NOT NULL,
    persistence_version TEXT NOT NULL,
    root_epoch INTEGER NOT NULL,
    created_at_us INTEGER NOT NULL
)
"""

_CONTROL_DDL = (
    _STORE_MANIFEST_DDL,
    """
    CREATE TABLE root_record (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        root_id TEXT NOT NULL UNIQUE,
        lifecycle_state TEXT NOT NULL CHECK (lifecycle_state = 'ready')
    )
    """,
    """
    CREATE TABLE timeline_registration (
        timeline_id TEXT PRIMARY KEY,
        timeline_store_id TEXT NOT NULL UNIQUE,
        relative_database_path TEXT NOT NULL UNIQUE,
        registration_state TEXT NOT NULL CHECK (registration_state = 'ready')
    )
    """,
)

_TIMELINE_DDL = (
    _STORE_MANIFEST_DDL,
    """
    CREATE TABLE admission_gate (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        authority_kind TEXT NOT NULL CHECK (
            authority_kind IN ('m0-a-fixture', 'published-qri-binding')
        ),
        authority_scope_id TEXT NOT NULL,
        profile_id TEXT NOT NULL,
        timeline_id TEXT NOT NULL,
        allowed_intents_json TEXT NOT NULL,
        allowed_provenance_json TEXT NOT NULL,
        binding_id TEXT,
        binding_revision INTEGER CHECK (binding_revision >= 1),
        binding_epoch INTEGER CHECK (binding_epoch >= 1),
        qualification_id TEXT,
        qualification_revision INTEGER CHECK (qualification_revision >= 1),
        provider_authority TEXT,
        gate_epoch INTEGER NOT NULL CHECK (gate_epoch >= 1),
        gate_state TEXT NOT NULL CHECK (
            gate_state IN ('closed', 'open', 'draining', 'retired', 'clearing')
        ),
        data_control_scope_id TEXT,
        CHECK (
            (authority_kind = 'm0-a-fixture'
                AND binding_id IS NULL
                AND binding_revision IS NULL
                AND binding_epoch IS NULL
                AND qualification_id IS NULL
                AND qualification_revision IS NULL
                AND provider_authority IS NULL
                AND (
                    (gate_state = 'open' AND data_control_scope_id IS NULL)
                    OR (gate_state = 'clearing' AND data_control_scope_id IS NOT NULL)
                ))
            OR
            (authority_kind = 'published-qri-binding'
                AND binding_id IS NOT NULL
                AND binding_revision IS NOT NULL
                AND binding_epoch IS NOT NULL
                AND qualification_id IS NOT NULL
                AND qualification_revision IS NOT NULL
                AND provider_authority IS NOT NULL
                AND data_control_scope_id IS NULL
                AND gate_state IN ('closed', 'open', 'draining', 'retired'))
        )
    )
    """,
    """
    CREATE TABLE timeline_head (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        head_sequence INTEGER NOT NULL CHECK (head_sequence >= 0),
        published_outcome_digest BLOB
    )
    """,
    """
    CREATE TABLE idempotency_claim (
        authority_scope_id TEXT NOT NULL,
        key_digest BLOB NOT NULL CHECK (length(key_digest) = 32),
        payload_fingerprint BLOB NOT NULL
            CHECK (length(payload_fingerprint) = 32),
        operation_id BLOB NOT NULL UNIQUE
            CHECK (length(operation_id) = 16)
            REFERENCES subject_operation(operation_id)
                ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
        claimed_at_us INTEGER NOT NULL,
        PRIMARY KEY (authority_scope_id, key_digest)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE subject_operation (
        operation_id BLOB PRIMARY KEY CHECK (length(operation_id) = 16),
        authority_scope_id TEXT NOT NULL,
        operation_kind TEXT NOT NULL,
        contract_version TEXT NOT NULL,
        payload_fingerprint BLOB NOT NULL
            CHECK (length(payload_fingerprint) = 32),
        operation_state TEXT NOT NULL CHECK (operation_state = 'admitted-pending'),
        admitted_at_us INTEGER NOT NULL
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE subject_command (
        operation_id BLOB PRIMARY KEY
            REFERENCES subject_operation(operation_id) ON DELETE RESTRICT,
        command_kind TEXT NOT NULL,
        target_profile_id TEXT NOT NULL,
        target_timeline_id TEXT NOT NULL,
        declared_intent TEXT NOT NULL,
        utterance TEXT NOT NULL,
        language TEXT NOT NULL,
        provenance TEXT NOT NULL,
        normalization_version TEXT NOT NULL,
        payload_fingerprint BLOB NOT NULL
            CHECK (length(payload_fingerprint) = 32)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE subject_event (
        event_id BLOB PRIMARY KEY CHECK (length(event_id) = 16),
        operation_id BLOB NOT NULL UNIQUE
            REFERENCES subject_operation(operation_id) ON DELETE RESTRICT,
        event_kind TEXT NOT NULL CHECK (event_kind = 'command-admitted'),
        recorded_at_us INTEGER NOT NULL
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE experience_attempt (
        attempt_id BLOB PRIMARY KEY CHECK (length(attempt_id) = 16),
        operation_id BLOB NOT NULL UNIQUE
            REFERENCES subject_operation(operation_id) ON DELETE RESTRICT,
        attempt_ordinal INTEGER NOT NULL CHECK (attempt_ordinal = 1),
        attempt_state TEXT NOT NULL CHECK (attempt_state = 'pending'),
        created_at_us INTEGER NOT NULL,
        UNIQUE (operation_id, attempt_ordinal)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE operation_transition (
        operation_id BLOB NOT NULL
            REFERENCES subject_operation(operation_id) ON DELETE RESTRICT,
        transition_ordinal INTEGER NOT NULL CHECK (transition_ordinal = 1),
        from_state TEXT,
        to_state TEXT NOT NULL CHECK (to_state = 'admitted-pending'),
        recorded_at_us INTEGER NOT NULL,
        PRIMARY KEY (operation_id, transition_ordinal)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE attempt_cycle_basis (
        operation_id BLOB PRIMARY KEY
            REFERENCES subject_operation(operation_id) ON DELETE RESTRICT,
        attempt_id BLOB NOT NULL UNIQUE
            REFERENCES experience_attempt(attempt_id) ON DELETE RESTRICT,
        head_sequence INTEGER NOT NULL CHECK (head_sequence >= 0),
        published_outcome_digest BLOB
            CHECK (
                published_outcome_digest IS NULL
                OR length(published_outcome_digest) = 32
            ),
        verified_prefix_digest BLOB NOT NULL
            CHECK (length(verified_prefix_digest) = 32),
        revision_head_digest BLOB NOT NULL
            CHECK (length(revision_head_digest) = 32),
        frozen_at_us INTEGER NOT NULL
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE operation_failure (
        operation_id BLOB PRIMARY KEY
            REFERENCES subject_operation(operation_id) ON DELETE RESTRICT,
        attempt_id BLOB NOT NULL UNIQUE
            REFERENCES experience_attempt(attempt_id) ON DELETE RESTRICT,
        failure_stage TEXT NOT NULL,
        failure_code TEXT NOT NULL,
        failure_detail TEXT NOT NULL,
        recorded_at_us INTEGER NOT NULL
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE cycle_failure_transition (
        operation_id BLOB PRIMARY KEY
            REFERENCES subject_operation(operation_id) ON DELETE RESTRICT,
        transition_ordinal INTEGER NOT NULL CHECK (transition_ordinal = 2),
        from_state TEXT NOT NULL CHECK (from_state = 'admitted-pending'),
        to_state TEXT NOT NULL CHECK (to_state = 'failed-closed'),
        recorded_at_us INTEGER NOT NULL
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE timeline_integrity (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        verified_prefix_digest BLOB NOT NULL
            CHECK (length(verified_prefix_digest) = 32),
        revision_head_digest BLOB NOT NULL
            CHECK (length(revision_head_digest) = 32)
    )
    """,
    """
    CREATE TABLE commit_plan_identity_claim (
        plan_id BLOB PRIMARY KEY CHECK (length(plan_id) = 16),
        plan_digest BLOB NOT NULL CHECK (length(plan_digest) = 32),
        cycle_plan_id BLOB NOT NULL UNIQUE CHECK (length(cycle_plan_id) = 16),
        operation_id BLOB NOT NULL
            REFERENCES subject_operation(operation_id) ON DELETE RESTRICT,
        attempt_id BLOB NOT NULL UNIQUE
            REFERENCES experience_attempt(attempt_id) ON DELETE RESTRICT,
        subject_event_id BLOB NOT NULL
            REFERENCES subject_event(event_id) ON DELETE RESTRICT,
        expected_head_sequence INTEGER NOT NULL CHECK (expected_head_sequence >= 0),
        expected_head_outcome_digest BLOB
            CHECK (
                expected_head_outcome_digest IS NULL
                OR length(expected_head_outcome_digest) = 32
            ),
        expected_verified_prefix_digest BLOB NOT NULL
            CHECK (length(expected_verified_prefix_digest) = 32),
        expected_revision_head_digest BLOB NOT NULL
            CHECK (length(expected_revision_head_digest) = 32),
        claim_epoch INTEGER NOT NULL CHECK (claim_epoch = 1),
        claimed_at_us INTEGER NOT NULL
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE publication_conflict_fact (
        conflict_id BLOB PRIMARY KEY CHECK (length(conflict_id) = 16),
        plan_id BLOB NOT NULL
            REFERENCES commit_plan_identity_claim(plan_id) ON DELETE RESTRICT,
        operation_id BLOB NOT NULL
            REFERENCES subject_operation(operation_id) ON DELETE RESTRICT,
        expected_head_sequence INTEGER NOT NULL,
        observed_head_sequence INTEGER NOT NULL,
        conflict_code TEXT NOT NULL CHECK (conflict_code = 'stale-timeline-basis'),
        recorded_at_us INTEGER NOT NULL,
        UNIQUE (plan_id, observed_head_sequence, conflict_code)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE cycle_commit_plan_receipt (
        plan_id BLOB PRIMARY KEY
            REFERENCES commit_plan_identity_claim(plan_id) ON DELETE RESTRICT,
        plan_digest BLOB NOT NULL UNIQUE CHECK (length(plan_digest) = 32),
        cycle_plan_id BLOB NOT NULL UNIQUE CHECK (length(cycle_plan_id) = 16),
        operation_id BLOB NOT NULL UNIQUE
            REFERENCES subject_operation(operation_id) ON DELETE RESTRICT,
        attempt_id BLOB NOT NULL UNIQUE
            REFERENCES experience_attempt(attempt_id) ON DELETE RESTRICT,
        subject_event_id BLOB NOT NULL
            REFERENCES subject_event(event_id) ON DELETE RESTRICT,
        profile_id TEXT NOT NULL,
        timeline_id TEXT NOT NULL,
        expected_head_sequence INTEGER NOT NULL,
        expected_head_outcome_digest BLOB
            CHECK (
                expected_head_outcome_digest IS NULL
                OR length(expected_head_outcome_digest) = 32
            ),
        expected_verified_prefix_digest BLOB NOT NULL
            CHECK (length(expected_verified_prefix_digest) = 32),
        expected_revision_head_digest BLOB NOT NULL
            CHECK (length(expected_revision_head_digest) = 32),
        published_at_us INTEGER NOT NULL
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE experience_record (
        experience_id BLOB PRIMARY KEY CHECK (length(experience_id) = 16),
        plan_id BLOB NOT NULL UNIQUE
            REFERENCES cycle_commit_plan_receipt(plan_id) ON DELETE RESTRICT,
        summary TEXT NOT NULL,
        experienced_at_us INTEGER NOT NULL,
        record_digest BLOB NOT NULL UNIQUE CHECK (length(record_digest) = 32)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE epistemic_outcome (
        epistemic_outcome_id BLOB PRIMARY KEY
            CHECK (length(epistemic_outcome_id) = 16),
        plan_id BLOB NOT NULL UNIQUE
            REFERENCES cycle_commit_plan_receipt(plan_id) ON DELETE RESTRICT,
        status TEXT NOT NULL CHECK (status = 'no-op'),
        reason TEXT NOT NULL,
        route_version TEXT NOT NULL,
        verified_prefix_digest BLOB NOT NULL
            CHECK (length(verified_prefix_digest) = 32),
        completed_stages_json TEXT NOT NULL,
        outcome_digest BLOB NOT NULL UNIQUE CHECK (length(outcome_digest) = 32)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE candidate_decision_record (
        decision_id BLOB PRIMARY KEY CHECK (length(decision_id) = 16),
        plan_id BLOB NOT NULL
            REFERENCES cycle_commit_plan_receipt(plan_id) ON DELETE RESTRICT,
        scope TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status = 'no-op'),
        reason TEXT NOT NULL,
        rule_version TEXT NOT NULL,
        actual_revision_ids_json TEXT NOT NULL
            CHECK (actual_revision_ids_json = '[]'),
        decision_digest BLOB NOT NULL UNIQUE CHECK (length(decision_digest) = 32),
        UNIQUE (plan_id, scope)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE experience_domain_outcome (
        outcome_id BLOB PRIMARY KEY CHECK (length(outcome_id) = 16),
        plan_id BLOB NOT NULL UNIQUE
            REFERENCES cycle_commit_plan_receipt(plan_id) ON DELETE RESTRICT,
        decision_id BLOB NOT NULL UNIQUE
            REFERENCES candidate_decision_record(decision_id) ON DELETE RESTRICT,
        epistemic_outcome_id BLOB NOT NULL
            REFERENCES epistemic_outcome(epistemic_outcome_id) ON DELETE RESTRICT,
        outcome_digest BLOB NOT NULL UNIQUE CHECK (length(outcome_digest) = 32)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE subject_core_outcome (
        outcome_id BLOB PRIMARY KEY CHECK (length(outcome_id) = 16),
        plan_id BLOB NOT NULL UNIQUE
            REFERENCES cycle_commit_plan_receipt(plan_id) ON DELETE RESTRICT,
        decision_id BLOB NOT NULL UNIQUE
            REFERENCES candidate_decision_record(decision_id) ON DELETE RESTRICT,
        outcome_digest BLOB NOT NULL UNIQUE CHECK (length(outcome_digest) = 32)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE development_outcome (
        outcome_id BLOB PRIMARY KEY CHECK (length(outcome_id) = 16),
        plan_id BLOB NOT NULL UNIQUE
            REFERENCES cycle_commit_plan_receipt(plan_id) ON DELETE RESTRICT,
        decision_id BLOB NOT NULL UNIQUE
            REFERENCES candidate_decision_record(decision_id) ON DELETE RESTRICT,
        outcome_digest BLOB NOT NULL UNIQUE CHECK (length(outcome_digest) = 32)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE subject_state_domain_outcome (
        outcome_id BLOB PRIMARY KEY CHECK (length(outcome_id) = 16),
        plan_id BLOB NOT NULL UNIQUE
            REFERENCES cycle_commit_plan_receipt(plan_id) ON DELETE RESTRICT,
        decision_id BLOB NOT NULL UNIQUE
            REFERENCES candidate_decision_record(decision_id) ON DELETE RESTRICT,
        subject_core_outcome_id BLOB NOT NULL UNIQUE
            REFERENCES subject_core_outcome(outcome_id) ON DELETE RESTRICT,
        development_outcome_id BLOB NOT NULL UNIQUE
            REFERENCES development_outcome(outcome_id) ON DELETE RESTRICT,
        outcome_digest BLOB NOT NULL UNIQUE CHECK (length(outcome_digest) = 32)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE agency_domain_outcome (
        outcome_id BLOB PRIMARY KEY CHECK (length(outcome_id) = 16),
        plan_id BLOB NOT NULL UNIQUE
            REFERENCES cycle_commit_plan_receipt(plan_id) ON DELETE RESTRICT,
        decision_id BLOB NOT NULL UNIQUE
            REFERENCES candidate_decision_record(decision_id) ON DELETE RESTRICT,
        committed_effect_eligible INTEGER NOT NULL
            CHECK (committed_effect_eligible = 0),
        outcome_digest BLOB NOT NULL UNIQUE CHECK (length(outcome_digest) = 32)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE relationship_domain_outcome (
        outcome_id BLOB PRIMARY KEY CHECK (length(outcome_id) = 16),
        plan_id BLOB NOT NULL UNIQUE
            REFERENCES cycle_commit_plan_receipt(plan_id) ON DELETE RESTRICT,
        decision_id BLOB NOT NULL UNIQUE
            REFERENCES candidate_decision_record(decision_id) ON DELETE RESTRICT,
        relationship_target_id TEXT NOT NULL,
        outcome_digest BLOB NOT NULL UNIQUE CHECK (length(outcome_digest) = 32)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE domain_outcome_set (
        plan_id BLOB PRIMARY KEY
            REFERENCES cycle_commit_plan_receipt(plan_id) ON DELETE RESTRICT,
        experience_outcome_id BLOB NOT NULL UNIQUE
            REFERENCES experience_domain_outcome(outcome_id) ON DELETE RESTRICT,
        subject_state_outcome_id BLOB NOT NULL UNIQUE
            REFERENCES subject_state_domain_outcome(outcome_id) ON DELETE RESTRICT,
        agency_outcome_id BLOB NOT NULL UNIQUE
            REFERENCES agency_domain_outcome(outcome_id) ON DELETE RESTRICT,
        relationship_outcome_id BLOB NOT NULL UNIQUE
            REFERENCES relationship_domain_outcome(outcome_id) ON DELETE RESTRICT,
        set_digest BLOB NOT NULL UNIQUE CHECK (length(set_digest) = 32)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE revision_set (
        revision_set_id BLOB PRIMARY KEY CHECK (length(revision_set_id) = 16),
        plan_id BLOB NOT NULL UNIQUE
            REFERENCES cycle_commit_plan_receipt(plan_id) ON DELETE RESTRICT,
        revision_count INTEGER NOT NULL CHECK (revision_count = 0),
        revision_ids_json TEXT NOT NULL CHECK (revision_ids_json = '[]'),
        set_digest BLOB NOT NULL UNIQUE CHECK (length(set_digest) = 32)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE expression_record (
        expression_id BLOB PRIMARY KEY CHECK (length(expression_id) = 16),
        plan_id BLOB NOT NULL UNIQUE
            REFERENCES cycle_commit_plan_receipt(plan_id) ON DELETE RESTRICT,
        expression_text TEXT NOT NULL,
        language TEXT NOT NULL,
        grounding_decision_ids_json TEXT NOT NULL,
        expression_digest BLOB NOT NULL UNIQUE
            CHECK (length(expression_digest) = 32)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE committed_effect_set (
        effect_set_id BLOB PRIMARY KEY CHECK (length(effect_set_id) = 16),
        plan_id BLOB NOT NULL UNIQUE
            REFERENCES cycle_commit_plan_receipt(plan_id) ON DELETE RESTRICT,
        effect_count INTEGER NOT NULL CHECK (effect_count = 0),
        reference_ids_json TEXT NOT NULL CHECK (reference_ids_json = '[]'),
        dispatch_state TEXT NOT NULL CHECK (dispatch_state = 'unavailable'),
        reason TEXT NOT NULL,
        set_digest BLOB NOT NULL UNIQUE CHECK (length(set_digest) = 32)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE timeline_outcome (
        outcome_id BLOB PRIMARY KEY CHECK (length(outcome_id) = 16),
        operation_id BLOB NOT NULL UNIQUE
            REFERENCES subject_operation(operation_id) ON DELETE RESTRICT,
        attempt_id BLOB NOT NULL UNIQUE
            REFERENCES experience_attempt(attempt_id) ON DELETE RESTRICT,
        subject_event_id BLOB NOT NULL UNIQUE
            REFERENCES subject_event(event_id) ON DELETE RESTRICT,
        plan_id BLOB NOT NULL UNIQUE
            REFERENCES cycle_commit_plan_receipt(plan_id) ON DELETE RESTRICT,
        head_sequence INTEGER NOT NULL UNIQUE CHECK (head_sequence > 0),
        previous_outcome_digest BLOB
            CHECK (
                previous_outcome_digest IS NULL
                OR length(previous_outcome_digest) = 32
            ),
        outcome_digest BLOB NOT NULL UNIQUE CHECK (length(outcome_digest) = 32),
        experience_id BLOB NOT NULL UNIQUE
            REFERENCES experience_record(experience_id) ON DELETE RESTRICT,
        epistemic_outcome_id BLOB NOT NULL UNIQUE
            REFERENCES epistemic_outcome(epistemic_outcome_id) ON DELETE RESTRICT,
        experience_outcome_id BLOB NOT NULL UNIQUE
            REFERENCES experience_domain_outcome(outcome_id) ON DELETE RESTRICT,
        subject_state_outcome_id BLOB NOT NULL UNIQUE
            REFERENCES subject_state_domain_outcome(outcome_id) ON DELETE RESTRICT,
        agency_outcome_id BLOB NOT NULL UNIQUE
            REFERENCES agency_domain_outcome(outcome_id) ON DELETE RESTRICT,
        relationship_outcome_id BLOB NOT NULL UNIQUE
            REFERENCES relationship_domain_outcome(outcome_id) ON DELETE RESTRICT,
        revision_set_id BLOB NOT NULL UNIQUE
            REFERENCES revision_set(revision_set_id) ON DELETE RESTRICT,
        expression_id BLOB NOT NULL UNIQUE
            REFERENCES expression_record(expression_id) ON DELETE RESTRICT,
        effect_set_id BLOB NOT NULL UNIQUE
            REFERENCES committed_effect_set(effect_set_id) ON DELETE RESTRICT,
        published_at_us INTEGER NOT NULL
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE publication_receipt (
        plan_id BLOB PRIMARY KEY
            REFERENCES cycle_commit_plan_receipt(plan_id) ON DELETE RESTRICT,
        outcome_id BLOB NOT NULL UNIQUE
            REFERENCES timeline_outcome(outcome_id) ON DELETE RESTRICT,
        outcome_digest BLOB NOT NULL UNIQUE CHECK (length(outcome_digest) = 32),
        published_at_us INTEGER NOT NULL
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE operation_publication_state (
        operation_id BLOB PRIMARY KEY
            REFERENCES subject_operation(operation_id) ON DELETE RESTRICT,
        attempt_id BLOB NOT NULL UNIQUE
            REFERENCES experience_attempt(attempt_id) ON DELETE RESTRICT,
        operation_state TEXT NOT NULL
            CHECK (operation_state IN ('completed', 'interrupted')),
        attempt_state TEXT NOT NULL
            CHECK (attempt_state IN ('published', 'interrupted')),
        plan_id BLOB NOT NULL
            REFERENCES commit_plan_identity_claim(plan_id) ON DELETE RESTRICT,
        outcome_id BLOB UNIQUE
            REFERENCES timeline_outcome(outcome_id) ON DELETE RESTRICT,
        claim_epoch INTEGER NOT NULL CHECK (claim_epoch = 1),
        updated_at_us INTEGER NOT NULL,
        CHECK (
            (operation_state = 'completed'
                AND attempt_state = 'published'
                AND outcome_id IS NOT NULL)
            OR
            (operation_state = 'interrupted'
                AND attempt_state = 'interrupted'
                AND outcome_id IS NULL)
        )
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE publication_transition (
        operation_id BLOB PRIMARY KEY
            REFERENCES subject_operation(operation_id) ON DELETE RESTRICT,
        transition_ordinal INTEGER NOT NULL CHECK (transition_ordinal = 2),
        from_state TEXT NOT NULL CHECK (from_state = 'admitted-pending'),
        to_state TEXT NOT NULL CHECK (to_state IN ('completed', 'interrupted')),
        plan_id BLOB NOT NULL
            REFERENCES commit_plan_identity_claim(plan_id) ON DELETE RESTRICT,
        recorded_at_us INTEGER NOT NULL
    ) WITHOUT ROWID
    """,
)

_CONTROL_TABLES = frozenset({"root_record", "store_manifest", "timeline_registration"})
_EMPTY_EFFECT_HEAD = hashlib.sha256(b'text-effect-receipts-1').hexdigest()
_LIFE_DDL = (
    """CREATE TABLE system_input (
        operation_id BLOB PRIMARY KEY REFERENCES subject_operation(operation_id),
        input_json TEXT NOT NULL, payload_fingerprint BLOB NOT NULL
    ) STRICT""",
    """CREATE TABLE prepared_cycle_plan (
        plan_id BLOB PRIMARY KEY REFERENCES commit_plan_identity_claim(plan_id),
        operation_id BLOB NOT NULL UNIQUE REFERENCES subject_operation(operation_id),
        plan_json TEXT NOT NULL, plan_digest BLOB NOT NULL
    ) STRICT""",
    """CREATE TABLE life_record (
        plan_id BLOB PRIMARY KEY REFERENCES cycle_commit_plan_receipt(plan_id),
        record_json TEXT NOT NULL, record_digest BLOB NOT NULL
    ) STRICT""",
)

_EFFECT_DDL = (
    '''CREATE TABLE effect_receipt (
        ordinal INTEGER PRIMARY KEY CHECK (ordinal>0), effect_id TEXT NOT NULL UNIQUE,
        outcome_id BLOB NOT NULL UNIQUE REFERENCES timeline_outcome(outcome_id),
        head_sequence INTEGER NOT NULL UNIQUE CHECK (head_sequence>0),
        receipt_json TEXT NOT NULL, previous_digest TEXT NOT NULL, receipt_digest TEXT NOT NULL UNIQUE
    )''',
    '''CREATE TABLE effect_receipt_head (
        singleton INTEGER PRIMARY KEY CHECK (singleton=1), receipt_count INTEGER NOT NULL CHECK (receipt_count>=0),
        receipt_digest TEXT NOT NULL
    )''',
)
_TIMELINE_TABLES = frozenset(
    {
        "admission_gate",
        "agency_domain_outcome",
        "attempt_cycle_basis",
        "candidate_decision_record",
        "commit_plan_identity_claim",
        "cycle_failure_transition",
        "committed_effect_set",
        "cycle_commit_plan_receipt",
        "development_outcome",
        "domain_outcome_set",
        "epistemic_outcome",
        "experience_attempt",
        "experience_domain_outcome",
        "experience_record",
        "expression_record",
        "idempotency_claim",
        "operation_failure",
        "operation_publication_state",
        "operation_transition",
        "publication_conflict_fact",
        "publication_receipt",
        "publication_transition",
        "relationship_domain_outcome",
        "revision_set",
        "store_manifest",
        "subject_command",
        "subject_core_outcome",
        "subject_event",
        "subject_operation",
        "subject_state_domain_outcome",
        "timeline_head",
        "timeline_integrity",
        "timeline_outcome",
    }
)


def _begin(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")


def _commit(connection: sqlite3.Connection) -> None:
    connection.execute("COMMIT")


def _rollback_if_needed(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.execute("ROLLBACK")


def _insert_manifest(
    connection: sqlite3.Connection,
    *,
    root_id: str,
    store_id: str,
    store_kind: str,
    schema_family: str,
    created_at_us: int | None = None,
    schema_version: int = SCHEMA_VERSION,
) -> None:
    connection.execute(
        """
        INSERT INTO store_manifest (
            singleton,
            root_id,
            store_id,
            store_kind,
            schema_family,
            schema_version,
            contract_version,
            persistence_version,
            root_epoch,
            created_at_us
        ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            root_id,
            store_id,
            store_kind,
            schema_family,
            schema_version,
            CONTRACT_VERSION,
            PERSISTENCE_VERSION,
            ROOT_EPOCH,
            _utc_microseconds() if created_at_us is None else created_at_us,
        ),
    )


def _bootstrap_control(
    location: CanonicalRootRef,
    *,
    created_at_us: int | None = None,
) -> None:
    connection = _connect_new_writer(location.control_database)
    try:
        _begin(connection)
        for statement in _CONTROL_DDL:
            connection.execute(statement)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        _insert_manifest(
            connection,
            root_id=location.root_id,
            store_id=location.control_store_id,
            store_kind="control",
            schema_family=CONTROL_SCHEMA_FAMILY,
            created_at_us=created_at_us,
        )
        connection.execute(
            """
            INSERT INTO root_record (singleton, root_id, lifecycle_state)
            VALUES (1, ?, 'ready')
            """,
            (location.root_id,),
        )
        connection.execute(
            """
            INSERT INTO timeline_registration (
                timeline_id,
                timeline_store_id,
                relative_database_path,
                registration_state
            ) VALUES (?, ?, ?, 'ready')
            """,
            (
                location.timeline_id,
                location.timeline_store_id,
                f"timelines/{location.timeline_id}/timeline.sqlite3",
            ),
        )
        _commit(connection)
    except Exception:
        _rollback_if_needed(connection)
        raise
    finally:
        connection.close()


def _bootstrap_timeline(
    location: CanonicalRootRef,
    authority: FixtureAuthority | _RuntimeBindingAuthority,
    *,
    gate_state: str,
    created_at_us: int | None = None,
) -> None:
    connection = _connect_new_writer(location.timeline_database)
    try:
        _begin(connection)
        effects = 'confirmed-text-save-v1' in authority.allowed_intents
        life = LIFE_SYSTEM_INTENT in authority.allowed_intents
        if life and effects:
            raise AdmissionFailedClosed('life-effect-contract-conflict', 'life authority does not enable file effects')
        schema_version = 3 if life else 2 if effects else SCHEMA_VERSION
        for statement in _TIMELINE_DDL:
            if life:
                statement = statement.replace("CHECK (event_kind = 'command-admitted')", "CHECK (event_kind IN ('command-admitted','system-input-admitted'))")
            if effects:
                statement=statement.replace('CHECK (committed_effect_eligible = 0)', 'CHECK (committed_effect_eligible IN (0,1))')
                statement=statement.replace('CHECK (effect_count = 0)', 'CHECK (effect_count IN (0,1))')
                statement=statement.replace("CHECK (reference_ids_json = '[]')", '')
                statement=statement.replace("CHECK (dispatch_state = 'unavailable')", "CHECK (dispatch_state IN ('unavailable','ready'))")
            connection.execute(statement)
        if effects:
            for statement in _EFFECT_DDL:
                connection.execute(statement)
            connection.execute('INSERT INTO effect_receipt_head VALUES (1,0,?)', (_EMPTY_EFFECT_HEAD,))
        if life:
            for statement in _LIFE_DDL:
                connection.execute(statement)
        connection.execute(f"PRAGMA user_version = {schema_version}")
        _insert_manifest(
            connection,
            root_id=location.root_id,
            store_id=location.timeline_store_id,
            store_kind="timeline",
            schema_family=TIMELINE_SCHEMA_FAMILY,
            created_at_us=created_at_us,
            schema_version=schema_version,
        )
        connection.execute(
            """
            INSERT INTO admission_gate (
                singleton,
                authority_kind,
                authority_scope_id,
                profile_id,
                timeline_id,
                allowed_intents_json,
                allowed_provenance_json,
                binding_id,
                binding_revision,
                binding_epoch,
                qualification_id,
                qualification_revision,
                provider_authority,
                gate_epoch,
                gate_state,
                data_control_scope_id
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, NULL)
            """,
            (
                (
                    "m0-a-fixture"
                    if isinstance(authority, FixtureAuthority)
                    else "published-qri-binding"
                ),
                authority.authority_scope_id,
                authority.profile_id,
                authority.timeline_id,
                json.dumps(
                    authority.allowed_intents,
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
                json.dumps(
                    authority.allowed_provenance,
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
                (
                    None
                    if isinstance(authority, FixtureAuthority)
                    else authority.binding_id
                ),
                (
                    None
                    if isinstance(authority, FixtureAuthority)
                    else authority.binding_revision
                ),
                (
                    None
                    if isinstance(authority, FixtureAuthority)
                    else authority.binding_epoch
                ),
                (
                    None
                    if isinstance(authority, FixtureAuthority)
                    else authority.qualification_id
                ),
                (
                    None
                    if isinstance(authority, FixtureAuthority)
                    else authority.qualification_revision
                ),
                (
                    None
                    if isinstance(authority, FixtureAuthority)
                    else authority.provider_authority
                ),
                gate_state,
            ),
        )
        connection.execute(
            """
            INSERT INTO timeline_head (
                singleton,
                head_sequence,
                published_outcome_digest
            ) VALUES (1, 0, NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO timeline_integrity (
                singleton,
                verified_prefix_digest,
                revision_head_digest
            ) VALUES (1, ?, ?)
            """,
            (
                bytes.fromhex(_EMPTY_VERIFIED_PREFIX_DIGEST),
                bytes.fromhex(_EMPTY_REVISION_HEAD_DIGEST),
            ),
        )
        _commit(connection)
    except Exception:
        _rollback_if_needed(connection)
        raise
    finally:
        connection.close()


def _manifest_row(connection: sqlite3.Connection) -> sqlite3.Row:
    try:
        row = connection.execute(
            """
            SELECT
                root_id,
                store_id,
                store_kind,
                schema_family,
                schema_version,
                contract_version,
                persistence_version,
                root_epoch
            FROM store_manifest
            WHERE singleton = 1
            """
        ).fetchone()
    except sqlite3.Error as error:
        raise AdmissionFailedClosed(
            "store-identity-mismatch",
            "store manifest is absent or unreadable",
        ) from error
    if row is None:
        raise AdmissionFailedClosed(
            "store-identity-mismatch",
            "store manifest is absent",
        )
    return row


def _verify_manifest(
    connection: sqlite3.Connection,
    *,
    root_id: str,
    store_id: str,
    store_kind: str,
    schema_family: str,
) -> None:
    try:
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    except sqlite3.Error as error:
        raise AdmissionFailedClosed(
            "unsupported-schema-version",
            "schema version cannot be read",
        ) from error
    if user_version not in ((1,2,3) if store_kind=='timeline' else (SCHEMA_VERSION,)):
        raise AdmissionFailedClosed(
            "unsupported-schema-version",
            f"expected schema version {SCHEMA_VERSION}, found {user_version}",
        )
    row = _manifest_row(connection)
    if row[4] != user_version:
        raise AdmissionFailedClosed('unsupported-schema-version','schema version differs from the canonical manifest')
    expected = (
        root_id,
        store_id,
        store_kind,
        schema_family,
        user_version,
        CONTRACT_VERSION,
        PERSISTENCE_VERSION,
        ROOT_EPOCH,
    )
    if tuple(row) != expected:
        raise AdmissionFailedClosed(
            "store-identity-mismatch",
            "store manifest does not match the requested canonical authority",
        )


def _verify_store_integrity(
    connection: sqlite3.Connection,
    *,
    expected_tables: frozenset[str],
) -> None:
    if expected_tables == _TIMELINE_TABLES and connection.execute('PRAGMA user_version').fetchone()[0]==2:
        expected_tables=expected_tables | {'effect_receipt','effect_receipt_head'}
    elif expected_tables == _TIMELINE_TABLES and connection.execute('PRAGMA user_version').fetchone()[0]==3:
        expected_tables=expected_tables | {'system_input', 'prepared_cycle_plan', 'life_record'}
    try:
        tables = frozenset(
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_schema
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            )
        )
        quick_check = tuple(row[0] for row in connection.execute("PRAGMA quick_check"))
        foreign_key_violations = tuple(connection.execute("PRAGMA foreign_key_check"))
    except sqlite3.Error as error:
        raise AdmissionFailedClosed(
            "store-integrity-check-failed",
            "canonical store integrity could not be checked",
        ) from error
    if tables != expected_tables:
        raise AdmissionFailedClosed(
            "store-schema-mismatch",
            "canonical store table inventory does not match schema version 1",
        )
    if quick_check != ("ok",) or foreign_key_violations:
        raise AdmissionFailedClosed(
            "store-integrity-check-failed",
            "canonical store failed SQLite integrity checks",
        )


def _read_root_identity(
    root: Path,
    expected_root_id: str,
    expected_root_kind: str = ROOT_KIND,
) -> None:
    identity_path = root / "root.identity"
    if (
        not identity_path.is_file()
        or identity_path.is_symlink()
        or identity_path.stat().st_nlink != 1
    ):
        raise AdmissionFailedClosed(
            "root-identity-mismatch",
            "root identity is absent or linked",
        )
    try:
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AdmissionFailedClosed(
            "root-identity-mismatch",
            "root identity is unreadable",
        ) from error
    expected = {
        "format": ROOT_FORMAT,
        "root_epoch": ROOT_EPOCH,
        "root_id": expected_root_id,
        "root_kind": expected_root_kind,
    }
    if identity != expected:
        raise AdmissionFailedClosed(
            "root-identity-mismatch",
            "root identity does not match the canonical root reference",
        )


def _read_admission_gate(connection: sqlite3.Connection) -> _AdmissionGateView:
    try:
        row = connection.execute(
            """
            SELECT
                authority_kind,
                authority_scope_id,
                profile_id,
                timeline_id,
                allowed_intents_json,
                allowed_provenance_json,
                binding_id,
                binding_revision,
                binding_epoch,
                qualification_id,
                qualification_revision,
                provider_authority,
                gate_epoch,
                gate_state,
                data_control_scope_id
            FROM admission_gate
            WHERE singleton = 1
            """
        ).fetchone()
    except sqlite3.Error as error:
        raise AdmissionFailedClosed(
            "admission-gate-invalid",
            "fixture Admission gate is unreadable",
        ) from error
    if row is None or int(row[12]) < 1:
        raise AdmissionFailedClosed(
            "admission-gate-invalid",
            "Admission gate is incomplete",
        )
    try:
        intents = tuple(json.loads(row[4]))
        provenance = tuple(json.loads(row[5]))
    except (TypeError, json.JSONDecodeError) as error:
        raise AdmissionFailedClosed(
            "admission-gate-invalid",
            "Admission gate constraints are invalid",
        ) from error
    try:
        if str(row[0]) == "m0-a-fixture":
            authority: FixtureAuthority | _RuntimeBindingAuthority = FixtureAuthority(
                authority_scope_id=row[1],
                profile_id=row[2],
                timeline_id=row[3],
                allowed_intents=intents,
                allowed_provenance=provenance,
            )
        elif str(row[0]) == "published-qri-binding":
            authority = _RuntimeBindingAuthority(
                authority_scope_id=row[1],
                profile_id=row[2],
                timeline_id=row[3],
                allowed_intents=intents,
                allowed_provenance=provenance,
                binding_id=row[6],
                binding_revision=int(row[7]),
                binding_epoch=int(row[8]),
                qualification_id=row[9],
                qualification_revision=int(row[10]),
                provider_authority=row[11],
            )
        else:
            raise PreAdmissionRejected(
                "admission-authority-kind-invalid",
                "Admission gate authority kind is unsupported",
            )
    except PreAdmissionRejected as error:
        raise AdmissionFailedClosed(
            "admission-gate-invalid",
            "Admission gate identity is invalid",
        ) from error
    state = str(row[13])
    scope_id = None if row[14] is None else str(row[14])
    fixture_state_valid = isinstance(authority, FixtureAuthority) and (
        (state == "open" and scope_id is None)
        or (state == "clearing" and scope_id is not None)
    )
    runtime_state_valid = isinstance(authority, _RuntimeBindingAuthority) and (
        state in {"closed", "open", "draining", "retired"} and scope_id is None
    )
    if not fixture_state_valid and not runtime_state_valid:
        raise AdmissionFailedClosed(
            "admission-gate-invalid",
            "Admission gate lifecycle is invalid",
        )
    return _AdmissionGateView(
        authority=authority,
        gate_epoch=int(row[12]),
        state=state,
        data_control_scope_id=scope_id,
    )


def _read_fixture_gate(
    connection: sqlite3.Connection,
) -> tuple[FixtureAuthority, int, str, str | None]:
    gate = _read_admission_gate(connection)
    if not isinstance(gate.authority, FixtureAuthority):
        raise AdmissionFailedClosed(
            "fixture-authority-unavailable",
            "this Timeline is owned by a published QRI binding",
        )
    return (
        gate.authority,
        gate.gate_epoch,
        gate.state,
        gate.data_control_scope_id,
    )


def _read_fixture_authority(connection: sqlite3.Connection) -> FixtureAuthority:
    authority, _epoch, state, _scope_id = _read_fixture_gate(connection)
    if state != "open":
        raise AdmissionFailedClosed(
            "admission-unavailable",
            "fixture Admission gate is not open",
        )
    return authority


def _read_open_authority(
    connection: sqlite3.Connection,
) -> FixtureAuthority | _RuntimeBindingAuthority:
    gate = _read_admission_gate(connection)
    if gate.state != "open":
        raise AdmissionFailedClosed(
            "admission-unavailable",
            "Timeline Admission gate is not open",
        )
    return gate.authority


def _require_publication_gate(
    connection: sqlite3.Connection,
    expected_authority: FixtureAuthority | _RuntimeBindingAuthority,
) -> None:
    try:
        authority = _read_open_authority(connection)
    except AdmissionProblem as error:
        raise PublicationInterrupted(
            "governance-clearing",
            "Publication is fenced because Admission authority is unavailable",
        ) from error
    if authority != expected_authority:
        raise PublicationInterrupted(
            "governance-authority-mismatch",
            "Publication is fenced from a changed Admission authority",
        )


def _read_timeline_basis(connection: sqlite3.Connection) -> TimelineBasis:
    try:
        row = connection.execute(
            """
            SELECT
                head_sequence,
                published_outcome_digest,
                verified_prefix_digest,
                revision_head_digest
            FROM timeline_head
            CROSS JOIN timeline_integrity
            WHERE timeline_head.singleton = 1
              AND timeline_integrity.singleton = 1
            """
        ).fetchone()
    except sqlite3.Error as error:
        raise AdmissionFailedClosed(
            "timeline-head-unreadable",
            "canonical Timeline basis could not be read",
        ) from error
    if row is None:
        raise AdmissionFailedClosed(
            "timeline-head-missing",
            "canonical Timeline basis is absent",
        )
    return TimelineBasis(
        head_sequence=int(row[0]),
        published_outcome_digest=(None if row[1] is None else bytes(row[1]).hex()),
        verified_prefix_digest=bytes(row[2]).hex(),
        revision_head_digest=bytes(row[3]).hex(),
    )


def _basis_matches(left: TimelineBasis, right: TimelineBasis) -> bool:
    return left == right


class TimelineEngine:
    """The only M0-A writer boundary for Admission in one timeline store."""

    def __init__(
        self,
        location: CanonicalRootRef,
        authority: FixtureAuthority | _RuntimeBindingAuthority,
        writer: sqlite3.Connection,
        fault_hook: _FaultHook | None,
    ) -> None:
        self._location = location
        self._authority = authority
        self._writer = writer
        self._fault_hook = fault_hook
        self._closed = False

    @property
    def location(self) -> CanonicalRootRef:
        return self._location

    @classmethod
    def create_test(
        cls,
        test_base: Path,
        authority: FixtureAuthority,
    ) -> TimelineEngine:
        if not isinstance(authority, FixtureAuthority):
            raise TypeError("create_test requires FixtureAuthority")
        location = cls._create_root(test_base, authority, gate_state="open")
        return cls.open(location, expected_authority=authority)

    @classmethod
    def _create_bound(
        cls,
        test_base: Path,
        authority: _RuntimeBindingAuthority,
        *,
        root_kind: str,
        _host_token: object,
        _reserved_identity: _ReservedTimelineIdentity | None = None,
        _created_at_us: int | None = None,
    ) -> TimelineEngine:
        if _host_token is not _HOST_TIMELINE_TOKEN:
            raise AdmissionFailedClosed(
                "binding-authority-required",
                "only RuntimeHost can create a QRI-bound Timeline",
            )
        if not isinstance(authority, _RuntimeBindingAuthority):
            raise TypeError("bound Timeline requires binding authority")
        if _reserved_identity is not None and not isinstance(
            _reserved_identity,
            _ReservedTimelineIdentity,
        ):
            raise TypeError("reserved Timeline identity is invalid")
        if _reserved_identity is not None:
            base = _validate_runtime_base(Path(test_base), root_kind=root_kind)
            reserved_location = _reserved_identity.location(
                base,
                timeline_id=authority.timeline_id,
                root_kind=root_kind,
            )
            if reserved_location.root.exists():
                return cls.open(
                    reserved_location,
                    expected_authority=authority,
                    _host_token=_host_token,
                )
        location = cls._create_root(
            test_base,
            authority,
            gate_state="closed",
            root_kind=root_kind,
            _reserved_identity=_reserved_identity,
            _created_at_us=_created_at_us,
        )
        return cls.open(
            location,
            expected_authority=authority,
            _host_token=_host_token,
        )

    @staticmethod
    def _create_root(
        test_base: Path,
        authority: FixtureAuthority | _RuntimeBindingAuthority,
        *,
        gate_state: str,
        root_kind: str = ROOT_KIND,
        _reserved_identity: _ReservedTimelineIdentity | None = None,
        _created_at_us: int | None = None,
    ) -> CanonicalRootRef:
        base = _validate_runtime_base(Path(test_base), root_kind=root_kind)
        if _reserved_identity is None:
            root_id = str(uuid4())
            control_store_id = str(uuid4())
            timeline_store_id = str(uuid4())
        else:
            root_id = _reserved_identity.root_id
            control_store_id = _reserved_identity.control_store_id
            timeline_store_id = _reserved_identity.timeline_store_id
        root = base / "mature-runtime-m0" / "roots" / root_id
        root.parent.mkdir(parents=True, exist_ok=True)
        try:
            root.mkdir()
        except OSError as error:
            if root.exists():
                raise AdmissionFailedClosed(
                    "canonical-root-partial-or-foreign",
                    "reserved canonical root already exists but is not exact",
                ) from error
            raise AdmissionFailedClosed(
                "canonical-root-create-failed",
                "new canonical root could not be created",
            ) from error

        location = CanonicalRootRef(
            root_path=str(root),
            root_id=root_id,
            control_store_id=control_store_id,
            timeline_store_id=timeline_store_id,
            timeline_id=authority.timeline_id,
            root_kind=root_kind,
        )
        try:
            identity = {
                "format": ROOT_FORMAT,
                "root_epoch": ROOT_EPOCH,
                "root_id": root_id,
                "root_kind": root_kind,
            }
            with (root / "root.identity").open(
                "x",
                encoding="utf-8",
                newline="\n",
            ) as target:
                json.dump(
                    identity,
                    target,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                target.write("\n")
            _bootstrap_control(location, created_at_us=_created_at_us)
            _bootstrap_timeline(
                location,
                authority,
                gate_state=gate_state,
                created_at_us=_created_at_us,
            )
            return location
        except Exception as error:
            if isinstance(error, AdmissionProblem):
                raise
            raise AdmissionFailedClosed(
                "canonical-root-bootstrap-failed",
                "new canonical root could not be bootstrapped",
            ) from error

    @classmethod
    def open(
        cls,
        location: CanonicalRootRef,
        *,
        expected_authority: FixtureAuthority | _RuntimeBindingAuthority | None = None,
        _fault_hook: _FaultHook | None = None,
        _host_token: object | None = None,
    ) -> TimelineEngine:
        if not isinstance(location, CanonicalRootRef):
            raise AdmissionFailedClosed(
                "canonical-root-reference-invalid",
                "TimelineEngine.open requires a CanonicalRootRef",
            )
        root = _validate_existing_root(
            location.root,
            location.root_id,
            root_kind=location.root_kind,
        )
        _read_root_identity(root, location.root_id, location.root_kind)
        control = _connect_existing_writer(location.control_database)
        try:
            _verify_connection_profile(control)
            _verify_manifest(
                control,
                root_id=location.root_id,
                store_id=location.control_store_id,
                store_kind="control",
                schema_family=CONTROL_SCHEMA_FAMILY,
            )
            _verify_store_integrity(
                control,
                expected_tables=_CONTROL_TABLES,
            )
            try:
                registration = control.execute(
                    """
                    SELECT
                        timeline_store_id,
                        relative_database_path,
                        registration_state
                    FROM timeline_registration
                    WHERE timeline_id = ?
                    """,
                    (location.timeline_id,),
                ).fetchone()
            except sqlite3.Error as error:
                raise AdmissionFailedClosed(
                    "store-identity-mismatch",
                    "timeline registration is unreadable",
                ) from error
            expected_relative = f"timelines/{location.timeline_id}/timeline.sqlite3"
            if registration != (
                location.timeline_store_id,
                expected_relative,
                "ready",
            ):
                raise AdmissionFailedClosed(
                    "store-identity-mismatch",
                    "timeline registration does not match the root reference",
                )
        finally:
            control.close()

        writer = _connect_existing_writer(location.timeline_database)
        try:
            _verify_connection_profile(writer)
            _verify_manifest(
                writer,
                root_id=location.root_id,
                store_id=location.timeline_store_id,
                store_kind="timeline",
                schema_family=TIMELINE_SCHEMA_FAMILY,
            )
            _verify_store_integrity(
                writer,
                expected_tables=_TIMELINE_TABLES,
            )
            gate = _read_admission_gate(writer)
            authority = gate.authority
            if (writer.execute('PRAGMA user_version').fetchone()[0]==2) != ('confirmed-text-save-v1' in authority.allowed_intents):
                raise AdmissionFailedClosed('effect-contract-mismatch','Timeline version differs from effect authority')
            if (writer.execute('PRAGMA user_version').fetchone()[0]==3) != (LIFE_SYSTEM_INTENT in authority.allowed_intents):
                raise AdmissionFailedClosed('life-contract-mismatch', 'Timeline version differs from life authority')
            if authority.timeline_id != location.timeline_id:
                raise AdmissionFailedClosed(
                    "store-identity-mismatch",
                    "timeline authority does not match the root reference",
                )
            if expected_authority is not None and authority != expected_authority:
                raise AdmissionFailedClosed(
                    "authority-identity-mismatch",
                    "fixture authority does not match canonical state",
                )
            if isinstance(authority, _RuntimeBindingAuthority):
                if _host_token is not _HOST_TIMELINE_TOKEN:
                    raise AdmissionFailedClosed(
                        "binding-authority-required",
                        "QRI-bound Timeline can only be opened by RuntimeHost",
                    )
                if gate.state not in {"closed", "open", "draining", "retired"}:
                    raise AdmissionFailedClosed(
                        "binding-gate-unavailable",
                        "runtime binding gate is not recoverable",
                    )
            elif gate.state != "open":
                raise AdmissionFailedClosed(
                    "admission-unavailable",
                    "fixture Admission gate is not open",
                )
        except Exception:
            writer.close()
            raise
        return cls(location, authority, writer, _fault_hook)

    def close(self) -> None:
        if not self._closed:
            self._writer.close()
            self._closed = True

    def _require_open(self) -> None:
        if self._closed:
            raise AdmissionFailedClosed(
                "engine-closed",
                "TimelineEngine is closed",
            )

    def _hit(self, point: FaultPoint) -> None:
        if self._fault_hook is not None:
            self._fault_hook(point)

    def _require_runtime_host(self, token: object) -> _RuntimeBindingAuthority:
        if token is not _HOST_TIMELINE_TOKEN or not isinstance(
            self._authority,
            _RuntimeBindingAuthority,
        ):
            raise AdmissionFailedClosed(
                "binding-authority-required",
                "Timeline binding lifecycle is private to RuntimeHost",
            )
        return self._authority

    def _activate_binding_gate(self, *, _host_token: object) -> None:
        authority = self._require_runtime_host(_host_token)
        self._require_open()
        try:
            _begin(self._writer)
            gate = _read_admission_gate(self._writer)
            if gate.authority != authority or gate.state == "retired":
                raise AdmissionFailedClosed(
                    "binding-gate-mismatch",
                    "Timeline gate does not match the active binding",
                )
            if gate.state != "open":
                changed = self._writer.execute(
                    """
                    UPDATE admission_gate
                    SET gate_state = 'open'
                    WHERE singleton = 1
                      AND authority_kind = 'published-qri-binding'
                      AND binding_id = ?
                      AND binding_revision = ?
                      AND binding_epoch = ?
                      AND gate_state IN ('closed', 'draining')
                    """,
                    (
                        authority.binding_id,
                        authority.binding_revision,
                        authority.binding_epoch,
                    ),
                )
                if changed.rowcount != 1:
                    raise AdmissionFailedClosed(
                        "binding-gate-mismatch",
                        "Timeline gate could not be opened for this binding",
                    )
            _commit(self._writer)
        except Exception:
            _rollback_if_needed(self._writer)
            raise

    def _close_binding_gate(
        self,
        *,
        retire: bool,
        _host_token: object,
    ) -> None:
        authority = self._require_runtime_host(_host_token)
        self._require_open()
        target_state = "retired" if retire else "closed"
        try:
            _begin(self._writer)
            gate = _read_admission_gate(self._writer)
            if gate.authority != authority:
                raise AdmissionFailedClosed(
                    "binding-gate-mismatch",
                    "Timeline gate does not match the binding being closed",
                )
            if gate.state != target_state:
                if gate.state == "retired":
                    raise AdmissionFailedClosed(
                        "binding-retired",
                        "a retired Timeline gate cannot be reopened or reclosed",
                    )
                changed = self._writer.execute(
                    """
                    UPDATE admission_gate
                    SET gate_state = ?, gate_epoch = gate_epoch + 1
                    WHERE singleton = 1
                      AND authority_kind = 'published-qri-binding'
                      AND binding_id = ?
                      AND binding_revision = ?
                      AND binding_epoch = ?
                      AND gate_state IN ('open', 'closed', 'draining')
                    """,
                    (
                        target_state,
                        authority.binding_id,
                        authority.binding_revision,
                        authority.binding_epoch,
                    ),
                )
                if changed.rowcount != 1:
                    raise AdmissionFailedClosed(
                        "binding-gate-mismatch",
                        "Timeline gate could not be closed for this binding",
                    )
            _commit(self._writer)
        except Exception:
            _rollback_if_needed(self._writer)
            raise

    def _binding_health(
        self,
        *,
        _host_token: object,
    ) -> tuple[str, int, TimelineBasis, bool]:
        authority = self._require_runtime_host(_host_token)
        self._require_open()
        gate = _read_admission_gate(self._writer)
        if gate.authority != authority:
            raise AdmissionFailedClosed(
                "binding-gate-mismatch",
                "Timeline health does not match the expected binding",
            )
        basis = _read_timeline_basis(self._writer)
        event = self._writer.execute("SELECT 1 FROM subject_event LIMIT 1").fetchone()
        return gate.state, gate.gate_epoch, basis, event is not None

    def _query_command(self, operation_ref: OperationRef) -> SubjectCommand:
        self._require_open()
        if (
            operation_ref.root_id != self._location.root_id
            or operation_ref.timeline_store_id != self._location.timeline_store_id
            or operation_ref.authority_scope_id != self._authority.authority_scope_id
        ):
            raise PreAdmissionRejected(
                "operation-ref-authority-mismatch",
                "OperationRef does not belong to this Timeline authority",
            )
        if operation_ref.operation_kind is OperationKind.SYSTEM:
            self._require_life_authority()
            row = self._writer.execute(
                'SELECT input_json, payload_fingerprint FROM system_input WHERE operation_id=?',
                (UUID(operation_ref.operation_id).bytes,),
            ).fetchone()
            try:
                if row is None:
                    raise ValueError('missing system input')
                command = FirstLifeInput(**json.loads(row[0]))
                self._validate_first_life_input(command)
                if (_canonical_json(command) != row[0]
                    or bytes(row[1]).hex() != command.payload_fingerprint
                    or command.payload_fingerprint != operation_ref.admitted_payload_fingerprint
                    or self._writer.execute('SELECT 1 FROM subject_command WHERE operation_id=?',
                        (UUID(operation_ref.operation_id).bytes,)).fetchone() is not None):
                    raise ValueError('system input fingerprint differs')
                return command
            except (TypeError, ValueError, KeyError) as error:
                raise AdmissionFailedClosed('system-input-integrity-failed', 'canonical system input is invalid') from error
        row = self._writer.execute(
            """
            SELECT
                command_kind,
                target_profile_id,
                target_timeline_id,
                declared_intent,
                utterance,
                language,
                provenance,
                normalization_version,
                hex(payload_fingerprint)
            FROM subject_command
            WHERE operation_id = ?
            """,
            (UUID(operation_ref.operation_id).bytes,),
        ).fetchone()
        if row is None:
            raise PreAdmissionRejected(
                "operation-not-found",
                "OperationRef has no canonical SubjectCommand",
            )
        command = SubjectCommand.contribute_utterance(
            target_profile_id=str(row[1]),
            target_timeline_id=str(row[2]),
            declared_intent=str(row[3]),
            utterance=str(row[4]),
            language=str(row[5]),
            provenance=str(row[6]),
        )
        if (
            str(row[0]) != command.kind
            or str(row[7]) != command.normalization_version
            or str(row[8]).casefold() != command.payload_fingerprint
            or command.payload_fingerprint != operation_ref.admitted_payload_fingerprint
        ):
            raise AdmissionFailedClosed(
                "command-integrity-failed",
                "canonical SubjectCommand no longer matches its OperationRef",
            )
        return command

    def _require_life_authority(self):
        if LIFE_SYSTEM_INTENT not in self._authority.allowed_intents:
            raise PreAdmissionRejected('first-life-unavailable', 'this identity has no life authority')

    def _validate_first_life_input(self, command):
        from datetime import date
        self._require_life_authority()
        if type(command) is not FirstLifeInput:
            raise PreAdmissionRejected('typed-system-input-required', 'life requires an exact typed system input')
        if (command.target_profile_id != self._authority.profile_id
            or command.target_timeline_id != self._authority.timeline_id
            or command.input_kind not in ('advance', 'share', 'control')
            or command.trigger not in ('simulation', 'control', 'online')
            or not isinstance(command.request_digest, str)
            or re.fullmatch(r'[0-9a-f]{64}', command.request_digest) is None
            or any(value is not None and type(value) is not bool for value in (command.paused, command.sharing_enabled))
            or (command.input_kind != 'control' and (command.paused is not None or command.sharing_enabled is not None))
            or (command.input_kind == 'control' and command.paused is None and command.sharing_enabled is None)):
            raise PreAdmissionRejected('first-life-input-invalid', 'system input exceeds the closed life contract')
        try:
            # Revalidate the frozen dataclass, including target-event semantics.
            FirstLifeInput(**_canonical_value(command))
            if date.fromisoformat(command.civil_day).isoformat() != command.civil_day:
                raise ValueError('noncanonical civil day')
        except (TypeError, ValueError) as error:
            raise PreAdmissionRejected('first-life-day-invalid', 'system input needs a canonical civil day') from error

    def admit_first_life(self, command, *, idempotency_key, _reserved_operation_id=None):
        self._validate_first_life_input(command)
        key_digest = _validate_idempotency_key(idempotency_key)
        row = self._writer.execute('SELECT operation_id FROM idempotency_claim WHERE authority_scope_id=? AND key_digest=?',
            (self._authority.authority_scope_id, key_digest)).fetchone()
        if row is not None:
            admitted = self._admitted_for_operation(self._writer, bytes(row[0]), replayed=True)
            original = self._query_command(admitted.operation_ref)
            if type(original) is not FirstLifeInput or replace(command, civil_day=original.civil_day) != original:
                raise PayloadConflict(admitted.operation_ref)
            command = original
        return self.admit(command, idempotency_key=idempotency_key, _reserved_operation_id=_reserved_operation_id)

    def replay_first_life_request(self, request_id, request_digest):
        """Read an exact public-request receipt without Admission or execution."""
        self._require_open()
        self._require_life_authority()
        key_digest = _validate_idempotency_key(request_id)
        if not isinstance(request_digest, str) or re.fullmatch(r'[0-9a-f]{64}', request_digest) is None:
            raise PreAdmissionRejected('first-life-request-invalid', 'the public request digest must be exact')
        row = self._writer.execute('SELECT operation_id FROM idempotency_claim WHERE authority_scope_id=? AND key_digest=?',
            (self._authority.authority_scope_id, key_digest)).fetchone()
        if row is None:
            return None
        ref = self._admitted_for_operation(self._writer, bytes(row[0]), replayed=True).operation_ref
        command = self._query_command(ref)
        if type(command) is not FirstLifeInput or command.request_digest != request_digest:
            raise PayloadConflict(ref)
        return ref

    def pending_first_life_operations(self):
        """Discover this schema-3 binding's pending work without executing it."""
        self._require_open()
        self._require_life_authority()
        self._verified_publications()
        rows = self._writer.execute('SELECT operation_id FROM subject_operation ORDER BY admitted_at_us, operation_id').fetchall()
        pending = []
        for (operation_id,) in rows:
            ref = self._admitted_for_operation(self._writer, bytes(operation_id), replayed=True).operation_ref
            snapshot = self.query(ref)
            self._query_command(ref)
            self.prepared_plan(ref)
            if snapshot.operation_state is OperationState.ADMITTED_PENDING:
                pending.append(ref)
            elif snapshot.operation_state is OperationState.COMPLETED:
                self.query_outcome(ref)
            elif snapshot.operation_state is OperationState.FAILED_CLOSED:
                self.query_failure(ref)
            else:
                raise PublicationFailedClosed('first-life-recovery-unresolved', 'an operation has no supported terminal or pending recovery state')
        return tuple(pending)

    def _validate_authority(self, command: SubjectCommand) -> None:
        if type(command) is FirstLifeInput:
            self._validate_first_life_input(command)
            return
        if command.declared_intent == LIFE_SYSTEM_INTENT:
            raise PreAdmissionRejected('typed-system-input-required', 'a user utterance cannot impersonate a life input')
        if (
            command.target_profile_id != self._authority.profile_id
            or command.target_timeline_id != self._authority.timeline_id
        ):
            raise PreAdmissionRejected(
                "authority-mismatch",
                "command target is outside the fixture authority",
            )
        if command.declared_intent not in self._authority.allowed_intents:
            raise PreAdmissionRejected(
                "intent-unavailable",
                "declared intent is unavailable in the fixture authority",
            )
        if command.provenance not in self._authority.allowed_provenance:
            raise PreAdmissionRejected(
                "provenance-unqualified",
                "command provenance is unavailable in the fixture authority",
            )
        if (
            command.contract_version != CONTRACT_VERSION
            or command.kind != COMMAND_KIND
            or command.normalization_version != NORMALIZATION_VERSION
        ):
            raise PreAdmissionRejected(
                "unsupported-contract-version",
                "command contract or normalization version is unsupported",
            )
        expected_fingerprint = _command_fingerprint(
            contract_version=command.contract_version,
            kind=command.kind,
            target_profile_id=command.target_profile_id,
            target_timeline_id=command.target_timeline_id,
            declared_intent=command.declared_intent,
            utterance=command.utterance,
            language=command.language,
            provenance=command.provenance,
            normalization_version=command.normalization_version,
        )
        if command.payload_fingerprint != expected_fingerprint:
            raise PreAdmissionRejected(
                "payload-fingerprint-mismatch",
                "command payload fingerprint is invalid",
            )

    def admit(
        self,
        command: SubjectCommand,
        *,
        idempotency_key: str,
        _reserved_operation_id: str | None = None,
    ) -> Admitted:
        self._require_open()
        if not isinstance(command, SubjectCommand) and type(command) is not FirstLifeInput:
            raise PreAdmissionRejected(
                "malformed-command",
                "Admission requires a SubjectCommand",
            )
        self._validate_authority(command)
        key_digest = _validate_idempotency_key(idempotency_key)
        payload = bytes.fromhex(command.payload_fingerprint)
        reserved_operation_id = (
            _canonical_uuid(_reserved_operation_id, "reserved_operation_id")
            if _reserved_operation_id is not None
            else None
        )
        reserved_operation_bytes = (
            UUID(reserved_operation_id).bytes
            if reserved_operation_id is not None
            else None
        )

        commit_started = False
        try:
            self._hit(FaultPoint.BEFORE_TRANSACTION)
            _begin(self._writer)
            observed_authority = _read_open_authority(self._writer)
            if observed_authority != self._authority:
                raise AdmissionFailedClosed(
                    "authority-identity-mismatch",
                    "Admission authority changed before its transaction",
                )
            existing = self._writer.execute(
                """
                SELECT payload_fingerprint, operation_id
                FROM idempotency_claim
                WHERE authority_scope_id = ? AND key_digest = ?
                """,
                (self._authority.authority_scope_id, key_digest),
            ).fetchone()
            if existing is not None:
                admitted = self._admitted_for_operation(
                    self._writer,
                    bytes(existing[1]),
                    replayed=True,
                )
                _commit(self._writer)
                if (
                    reserved_operation_bytes is not None
                    and bytes(existing[1]) != reserved_operation_bytes
                ):
                    raise PreAdmissionRejected(
                        "operation-egress-reservation-conflict",
                        "idempotency claim does not match the reserved operation",
                    )
                if bytes(existing[0]) != payload:
                    raise PayloadConflict(admitted.operation_ref)
                return admitted

            if reserved_operation_bytes is not None:
                already_reserved = self._writer.execute(
                    "SELECT 1 FROM subject_operation WHERE operation_id = ?",
                    (reserved_operation_bytes,),
                ).fetchone()
                if already_reserved is not None:
                    raise PreAdmissionRejected(
                        "operation-egress-reservation-conflict",
                        "reserved operation is already owned by another admission",
                    )
            operation_id = reserved_operation_bytes or uuid4().bytes
            event_id = uuid4().bytes
            attempt_id = uuid4().bytes
            recorded_at = _utc_microseconds()
            self._writer.execute(
                """
                INSERT INTO idempotency_claim (
                    authority_scope_id,
                    key_digest,
                    payload_fingerprint,
                    operation_id,
                    claimed_at_us
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self._authority.authority_scope_id,
                    key_digest,
                    payload,
                    operation_id,
                    recorded_at,
                ),
            )
            self._hit(FaultPoint.AFTER_IDEMPOTENCY_CLAIM)
            self._writer.execute(
                """
                INSERT INTO subject_operation (
                    operation_id,
                    authority_scope_id,
                    operation_kind,
                    contract_version,
                    payload_fingerprint,
                    operation_state,
                    admitted_at_us
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    operation_id,
                    self._authority.authority_scope_id,
                    OperationKind.SYSTEM.value if type(command) is FirstLifeInput else OperationKind.SUBJECT.value,
                    command.contract_version,
                    payload,
                    OperationState.ADMITTED_PENDING.value,
                    recorded_at,
                ),
            )
            if type(command) is FirstLifeInput:
                self._writer.execute('INSERT INTO system_input VALUES (?,?,?)',
                    (operation_id, _canonical_json(command), payload))
            else:
                self._writer.execute(
                    """
                    INSERT INTO subject_command (
                    operation_id,
                    command_kind,
                    target_profile_id,
                    target_timeline_id,
                    declared_intent,
                    utterance,
                    language,
                    provenance,
                    normalization_version,
                    payload_fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    operation_id,
                    command.kind,
                    command.target_profile_id,
                    command.target_timeline_id,
                    command.declared_intent,
                    command.utterance,
                    command.language,
                    command.provenance,
                    command.normalization_version,
                    payload,
                    ),
                )
            self._hit(FaultPoint.AFTER_OPERATION)
            self._writer.execute(
                """
                INSERT INTO subject_event (
                    event_id,
                    operation_id,
                    event_kind,
                    recorded_at_us
                ) VALUES (?, ?, ?, ?)
                """,
                (event_id, operation_id, 'system-input-admitted' if type(command) is FirstLifeInput else 'command-admitted', recorded_at),
            )
            self._writer.execute(
                """
                INSERT INTO experience_attempt (
                    attempt_id,
                    operation_id,
                    attempt_ordinal,
                    attempt_state,
                    created_at_us
                ) VALUES (?, ?, 1, ?, ?)
                """,
                (
                    attempt_id,
                    operation_id,
                    AttemptState.PENDING.value,
                    recorded_at,
                ),
            )
            self._writer.execute(
                """
                INSERT INTO operation_transition (
                    operation_id,
                    transition_ordinal,
                    from_state,
                    to_state,
                    recorded_at_us
                ) VALUES (?, 1, NULL, ?, ?)
                """,
                (
                    operation_id,
                    OperationState.ADMITTED_PENDING.value,
                    recorded_at,
                ),
            )
            self._hit(FaultPoint.BEFORE_COMMIT)
            commit_started = True
            _commit(self._writer)
            admitted = self._admitted_for_operation(
                self._writer,
                operation_id,
                replayed=False,
            )
            try:
                self._hit(FaultPoint.AFTER_COMMIT)
            except Exception:
                return self._resolve_uncertain_commit(
                    key_digest,
                    payload,
                )
            return admitted
        except PayloadConflict:
            raise
        except AdmissionFailedClosed:
            if self._writer.in_transaction:
                _rollback_if_needed(self._writer)
            raise
        except Exception as error:
            if not commit_started:
                try:
                    _rollback_if_needed(self._writer)
                except sqlite3.Error:
                    self._replace_writer()
                raise AdmissionFailedClosed(
                    "admission-transaction-failed",
                    "Admission transaction rolled back before commit",
                ) from error
            return self._resolve_uncertain_commit(
                key_digest,
                payload,
                cause=error,
            )

    def _replace_writer(self) -> None:
        self._writer.close()
        replacement = _connect_existing_writer(self._location.timeline_database)
        try:
            _verify_connection_profile(replacement)
            _verify_manifest(
                replacement,
                root_id=self._location.root_id,
                store_id=self._location.timeline_store_id,
                store_kind="timeline",
                schema_family=TIMELINE_SCHEMA_FAMILY,
            )
            _verify_store_integrity(
                replacement,
                expected_tables=_TIMELINE_TABLES,
            )
        except Exception:
            replacement.close()
            self._closed = True
            raise
        self._writer = replacement

    def _resolve_uncertain_commit(
        self,
        key_digest: bytes,
        payload: bytes,
        *,
        cause: BaseException | None = None,
    ) -> Admitted:
        try:
            self._replace_writer()
            row = self._writer.execute(
                """
                SELECT payload_fingerprint, operation_id
                FROM idempotency_claim
                WHERE authority_scope_id = ? AND key_digest = ?
                """,
                (self._authority.authority_scope_id, key_digest),
            ).fetchone()
            if row is None:
                raise AdmissionInterrupted(
                    "commit-outcome-unknown",
                    "canonical state has no proof of the attempted commit",
                )
            admitted = self._admitted_for_operation(
                self._writer,
                bytes(row[1]),
                replayed=True,
                recovered_after_commit=True,
            )
            if bytes(row[0]) != payload:
                raise PayloadConflict(admitted.operation_ref)
            return admitted
        except (AdmissionInterrupted, PayloadConflict):
            raise
        except Exception as error:
            interrupted = AdmissionInterrupted(
                "commit-outcome-unknown",
                "canonical state could not prove the attempted commit",
            )
            if cause is not None:
                raise interrupted from cause
            raise interrupted from error

    def _admitted_for_operation(
        self,
        connection: sqlite3.Connection,
        operation_id: bytes,
        *,
        replayed: bool,
        recovered_after_commit: bool = False,
    ) -> Admitted:
        try:
            row = connection.execute(
                """
                SELECT
                    operation_id,
                    authority_scope_id,
                    operation_kind,
                    contract_version,
                    payload_fingerprint,
                    operation_state,
                    attempt_id,
                    attempt_state
                FROM subject_operation
                JOIN experience_attempt USING (operation_id)
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise AdmissionInterrupted(
                "admission-query-failed",
                "canonical pending Admission could not be read",
            ) from error
        if row is None:
            raise AdmissionInterrupted(
                "incomplete-admission",
                "idempotency claim does not resolve to a complete pending attempt",
            )
        if (
            row[5] != OperationState.ADMITTED_PENDING.value
            or row[7] != AttemptState.PENDING.value
        ):
            raise AdmissionInterrupted(
                "invalid-admission-state",
                "operation is not a recoverable pending Admission",
            )
        operation_ref = OperationRef(
            contract_version=row[3],
            root_id=self._location.root_id,
            timeline_store_id=self._location.timeline_store_id,
            authority_scope_id=row[1],
            operation_id=str(UUID(bytes=bytes(row[0]))),
            operation_kind=OperationKind(row[2]),
            admitted_payload_fingerprint=bytes(row[4]).hex(),
        )
        return Admitted(
            operation_ref=operation_ref,
            attempt_id=str(UUID(bytes=bytes(row[6]))),
            replayed=replayed,
            recovered_after_commit=recovered_after_commit,
        )

    def _validate_commit_plan(self, plan: CycleCommitPlan) -> None:
        if not isinstance(plan, CycleCommitPlan):
            raise CommitPlanRejected(
                "commit-plan-invalid",
                "Publication requires a complete CycleCommitPlan",
            )
        if plan.life_record is not None:
            self._require_life_authority()
            try:
                if type(plan.life_record) is not LifeRecord or decode_life_record(_canonical_value(plan.life_record)) != plan.life_record:
                    raise ValueError('life record must be typed')
            except (TypeError, ValueError, AttributeError, KeyError) as error:
                raise CommitPlanRejected('life-record-invalid', 'life record is outside the typed contract') from error
        expected_types = (
            (plan.operation_ref, OperationRef, "operation_ref"),
            (plan.expected_basis, TimelineBasis, "expected_basis"),
            (plan.experience, ExperienceRecord, "experience"),
            (plan.epistemic_outcome, EpistemicOutcome, "epistemic_outcome"),
            (
                plan.experience_outcome,
                ExperienceDomainOutcome,
                "experience_outcome",
            ),
            (
                plan.subject_state_outcome,
                SubjectStateDomainOutcome,
                "subject_state_outcome",
            ),
            (plan.agency_outcome, AgencyDomainOutcome, "agency_outcome"),
            (
                plan.relationship_outcome,
                RelationshipDomainOutcome,
                "relationship_outcome",
            ),
            (plan.revision_set, RevisionSet, "revision_set"),
            (plan.expression, Expression, "expression"),
            (
                plan.committed_effect_set,
                CommittedEffectSet,
                "committed_effect_set",
            ),
        )
        for value, expected_type, field in expected_types:
            if not isinstance(value, expected_type):
                raise CommitPlanRejected(
                    "commit-plan-incomplete",
                    f"{field} must be a typed {expected_type.__name__}",
                )

        if plan.operation_ref.operation_kind is OperationKind.SYSTEM and plan.life_record is None:
            raise CommitPlanRejected('life-record-required', 'system Publication requires an adjudicated life record')

        if (
            plan.operation_ref.contract_version != CONTRACT_VERSION
            or plan.operation_ref.root_id != self._location.root_id
            or plan.operation_ref.timeline_store_id != self._location.timeline_store_id
            or plan.operation_ref.authority_scope_id
            != self._authority.authority_scope_id
        ):
            raise CommitPlanRejected(
                "commit-plan-authority-mismatch",
                "OperationRef is outside this canonical Timeline authority",
            )
        if (
            plan.profile_id != self._authority.profile_id
            or plan.timeline_id != self._authority.timeline_id
            or plan.operation_ref.operation_kind not in (
                (OperationKind.SUBJECT, OperationKind.SYSTEM)
                if LIFE_SYSTEM_INTENT in self._authority.allowed_intents else (OperationKind.SUBJECT,)
            )
        ):
            raise CommitPlanRejected(
                "commit-plan-authority-mismatch",
                "plan Profile, Timeline, or operation kind is not authoritative",
            )

        identities = {
            "plan_id": plan.plan_id,
            "cycle_plan_id": plan.cycle_plan_id,
            "operation_id": plan.operation_ref.operation_id,
            "attempt_id": plan.attempt_id,
            "subject_event_id": plan.subject_event_id,
            "experience_id": plan.experience.experience_id,
            "epistemic_outcome_id": plan.epistemic_outcome.epistemic_outcome_id,
            "experience_outcome_id": plan.experience_outcome.outcome_id,
            "subject_state_outcome_id": plan.subject_state_outcome.outcome_id,
            "subject_core_outcome_id": (
                plan.subject_state_outcome.subject_core.outcome_id
            ),
            "development_outcome_id": (
                plan.subject_state_outcome.development.outcome_id
            ),
            "agency_outcome_id": plan.agency_outcome.outcome_id,
            "relationship_outcome_id": plan.relationship_outcome.outcome_id,
            "revision_set_id": plan.revision_set.revision_set_id,
            "expression_id": plan.expression.expression_id,
            "effect_set_id": plan.committed_effect_set.effect_set_id,
        }
        decisions = (
            plan.experience_outcome.decision,
            plan.subject_state_outcome.decision,
            plan.subject_state_outcome.subject_core.decision,
            plan.subject_state_outcome.development.decision,
            plan.agency_outcome.decision,
            plan.relationship_outcome.decision,
        )
        for index, decision in enumerate(decisions):
            if not isinstance(decision, CandidateDecisionRecord):
                raise CommitPlanRejected(
                    "commit-plan-incomplete",
                    "every typed DomainOutcome requires a CandidateDecisionRecord",
                )
            identities[f"decision_{index}"] = decision.decision_id
        for field, value in identities.items():
            _publication_uuid_bytes(value, field)
        record_identity_values = tuple(
            value
            for field, value in identities.items()
            if field not in {"operation_id", "attempt_id", "subject_event_id"}
        )
        if len(set(record_identity_values)) != len(record_identity_values):
            raise CommitPlanRejected(
                "commit-plan-identity-collision",
                "publication record identities must be distinct",
            )

        if plan.expected_basis.head_sequence < 0:
            raise CommitPlanRejected(
                "commit-plan-invalid-basis",
                "expected head sequence must be non-negative",
            )
        _publication_digest_bytes(
            plan.expected_basis.published_outcome_digest,
            "published_outcome_digest",
        )
        _publication_digest_bytes(
            plan.expected_basis.verified_prefix_digest,
            "verified_prefix_digest",
        )
        _publication_digest_bytes(
            plan.expected_basis.revision_head_digest,
            "revision_head_digest",
        )
        if (
            plan.epistemic_outcome.verified_prefix_digest
            != plan.expected_basis.verified_prefix_digest
        ):
            raise CommitPlanRejected(
                "commit-plan-epistemic-discontinuity",
                "M0 epistemic NoOp must preserve the verified prefix",
            )
        if plan.epistemic_outcome.completed_stages:
            raise CommitPlanRejected(
                "commit-plan-epistemic-invalid",
                "M0 epistemic NoOp cannot claim completed epistemic stages",
            )

        expected_scopes = (
            "experience",
            "subject-state",
            "subject-core",
            "development",
            "agency",
            "relationship",
        )
        if tuple(decision.scope for decision in decisions) != expected_scopes:
            raise CommitPlanRejected(
                "commit-plan-domain-set-invalid",
                "the six typed M0 decision scopes are incomplete or reordered",
            )
        if any(
            decision.status is not DecisionStatus.NO_OP
            or decision.actual_revision_ids
            or not decision.reason.strip()
            or not decision.rule_version.strip()
            for decision in decisions
        ):
            raise CommitPlanRejected(
                "commit-plan-domain-not-noop",
                "M0 07 accepts only reasoned typed NoOp decisions with no revisions",
            )
        domain_statuses = (
            plan.epistemic_outcome.status,
            plan.experience_outcome.decision.status,
            plan.subject_state_outcome.decision.status,
            plan.subject_state_outcome.subject_core.decision.status,
            plan.subject_state_outcome.development.decision.status,
            plan.agency_outcome.decision.status,
            plan.relationship_outcome.decision.status,
        )
        if any(status is not DecisionStatus.NO_OP for status in domain_statuses):
            raise CommitPlanRejected(
                "commit-plan-domain-not-noop",
                "M0 07 does not implement non-NoOp Domain authority",
            )
        if (
            plan.experience_outcome.epistemic_outcome_id
            != plan.epistemic_outcome.epistemic_outcome_id
        ):
            raise CommitPlanRejected(
                "commit-plan-lineage-invalid",
                "Experience outcome does not reference the plan epistemic outcome",
            )
        if (
            plan.relationship_outcome.relationship_target_id != plan.profile_id
        ):
            raise CommitPlanRejected(
                "commit-plan-domain-invalid",
                "M0 relationship target or Agency effect eligibility is invalid",
            )
        if plan.revision_set.revision_ids:
            raise CommitPlanRejected(
                "commit-plan-revisions-unavailable",
                "M0 07 accepts an explicit empty RevisionSet only",
            )
        from dynamic_subject_agent.text_artifacts import effect_from_reason
        effect = effect_from_reason(plan.agency_outcome.decision)
        expected_refs = (effect.effect_id,) if effect else ()
        if (plan.agency_outcome.committed_effect_eligible != bool(effect)
            or plan.committed_effect_set.reference_ids != expected_refs
            or plan.committed_effect_set.dispatch_state is not (EffectDispatchState.READY if effect else EffectDispatchState.UNAVAILABLE)
            or (effect and 'confirmed-text-save-v1' not in self._authority.allowed_intents)
            or not plan.committed_effect_set.reason.strip()):
            raise CommitPlanRejected(
                "commit-plan-effects-unavailable",
                "M0 committed effects must be explicit empty and unavailable",
            )

        decision_ids = tuple(decision.decision_id for decision in decisions)
        if len(plan.expression.grounding_decision_ids) != len(decision_ids) or set(
            plan.expression.grounding_decision_ids
        ) != set(decision_ids):
            raise CommitPlanRejected(
                "commit-plan-expression-grounding-invalid",
                "Expression must be grounded by every typed M0 decision exactly once",
            )
        text_fields = (
            ("experience.summary", plan.experience.summary),
            ("epistemic.reason", plan.epistemic_outcome.reason),
            ("epistemic.route_version", plan.epistemic_outcome.route_version),
            ("expression.text", plan.expression.text),
            ("expression.language", plan.expression.language),
        )
        for field, value in text_fields:
            if (
                not isinstance(value, str)
                or not value.strip()
                or unicodedata.normalize(
                    "NFC",
                    value.replace("\r\n", "\n").replace("\r", "\n"),
                )
                != value
                or "\x00" in value
            ):
                raise CommitPlanRejected(
                    "commit-plan-text-invalid",
                    f"{field} is not non-empty canonical text",
                )
        if (
            not isinstance(plan.experience.experienced_at_us, int)
            or plan.experience.experienced_at_us <= 0
        ):
            raise CommitPlanRejected(
                "commit-plan-experience-time-invalid",
                "Experience timestamp must be a positive UTC microsecond integer",
            )

    def _verified_publications(self):
        """Verify the global chain before any origin-specific projection."""
        rows = self._writer.execute('''SELECT outcome.head_sequence, outcome.published_at_us,
            operation.operation_id, operation.contract_version, operation.operation_kind,
            hex(operation.payload_fingerprint) FROM timeline_outcome outcome
            JOIN subject_operation operation USING(operation_id) ORDER BY outcome.head_sequence''').fetchall()
        basis = _read_timeline_basis(self._writer)
        if len(rows) != basis.head_sequence or [row[0] for row in rows] != list(range(1, basis.head_sequence + 1)):
            raise PublicationFailedClosed('timeline-chain-incomplete', 'global Publication chain is incomplete')
        previous = None
        result = []
        for row in rows:
            ref = OperationRef(str(row[3]), self._location.root_id, self._location.timeline_store_id,
                self._authority.authority_scope_id, str(UUID(bytes=bytes(row[2]))), OperationKind(row[4]), str(row[5]).lower())
            outcome = self.query_outcome(ref)
            command = self._query_command(ref)
            if (outcome.head_sequence != row[0] or outcome.previous_outcome_digest != previous
                or type(row[1]) is not int or row[1] <= 0
                or (type(command) is FirstLifeInput) != (ref.operation_kind is OperationKind.SYSTEM)):
                raise PublicationFailedClosed('timeline-chain-invalid', 'global Publication lineage is invalid')
            result.append((outcome, command, row[1]))
            previous = outcome.outcome_digest
        if previous != basis.published_outcome_digest:
            raise PublicationFailedClosed('timeline-head-invalid', 'global Publication head does not match its chain')
        return tuple(result)

    def _check_life_change(self, record, command, before, expression):
        """Python adjudication of the entire delta, also used during replay."""
        if record is None:
            if type(command) is FirstLifeInput:
                raise ValueError('system Publication has no life record')
            return
        if decode_life_record(_canonical_value(record)) != record:
            raise ValueError('invalid typed life record')
        old = before.record
        system = type(command) is FirstLifeInput
        expected_kind = command.input_kind if system else 'disclosure'
        if record.kind != expected_kind and not (expected_kind == 'share' and record.kind == 'share-declined'):
            raise ValueError('life record origin mismatch')
        if record.kind != 'advance':
            if ((record.phase, record.revision, record.plan, record.virtual_minutes)
                != (old.phase, old.revision, old.plan, old.virtual_minutes)
                or record.reason_code or record.differences or record.event_id or record.summary or record.simulated):
                raise ValueError('non-advance changed the creative state')
        if record.kind == 'control':
            if (record.paused != (old.paused if command.paused is None else command.paused)
                or record.sharing_enabled != (old.sharing_enabled if command.sharing_enabled is None else command.sharing_enabled)):
                raise ValueError('control result differs from explicit input')
        elif (record.paused, record.sharing_enabled) != (old.paused, old.sharing_enabled):
            raise ValueError('ordinary activity cannot modify controls')
        if record.kind == 'advance':
            if old.paused or before.technical_problem or record.virtual_minutes != old.virtual_minutes + 1:
                raise ValueError('life progression is paused or does not represent one step')
            action = {'drafted': 'start', 'revised': 'revise', 'kept': 'keep', 'rework': 'rework', 'deferred': 'defer'}.get(record.phase)
            value = dict(action=action, plan=_canonical_value(record.plan) if action in ('start','revise') else None,
                reason_code=record.reason_code)
            action, phase, selected, reason, differences = adjudicate_life(value, phase=old.phase, current_plan=old.plan)
            revision = old.revision + (1 if action in ('start', 'revise') else 0)
            if ((record.phase, record.plan, record.reason_code, record.differences, record.revision)
                != (phase, selected, reason, differences, revision)
                or record.summary != event_summary(action, revision, differences)
                or record.simulated != (command.trigger == 'simulation')
                or str(UUID(record.event_id)) != record.event_id
                or record.event_id in {event.event_id for event in before.events}):
                raise ValueError('life transition is not the exact adjudicated delta')
        if record.kind in ('share', 'share-declined'):
            target = record.disclosed_event_id if record.kind == 'share' else record.considered_event_id
            if (not before.has_dialogue or before.unanswered_share or not old.sharing_enabled
                or before.technical_problem or not before.events or target != before.events[-1].event_id
                or target != command.target_event_id
                or target in before.disclosed_event_ids or target in before.considered_event_ids):
                raise ValueError('event is not eligible for a new application share')
        if record.kind == 'share':
            if (str(UUID(record.share_id)) != record.share_id or record.share_id in {share.share_id for share in before.shares}
                or record.share_text != expression.text or expression.language != 'zh'):
                raise ValueError('share differs from its assistant expression')
        elif record.share_id or record.share_text:
            raise ValueError('non-share contains a proactive message')
        if record.kind == 'disclosure':
            if record.disclosed_event_id not in {event.event_id for event in before.events}:
                raise ValueError('chat disclosure is not tied to a committed event')
        elif record.kind != 'share' and record.disclosed_event_id:
            raise ValueError('non-disclosure has disclosure evidence')
        if record.kind != 'share-declined' and record.considered_event_id:
            raise ValueError('unexpected consideration evidence')

    def first_life_basis(self, *, expected_head=None):
        from dynamic_subject_agent.first_life import FirstLifeBasis, LifeEvent, LifeVersion, LifeShare
        self._require_life_authority()
        publications = self._verified_publications()
        if expected_head is not None and len(publications) != expected_head:
            raise PublicationFailedClosed('life-basis-changed', 'life projection is not the frozen global head')
        current = initial_life_record()
        events, versions, shares, disclosed, considered = [], [], [], set(), set()
        has_dialogue = False
        last_control_admitted = 0
        for outcome, command, _timestamp in publications:
            before = FirstLifeBasis(current, tuple(events), tuple(versions), tuple(shares), has_dialogue,
                any(not share.answered for share in shares), tuple(sorted(disclosed)), outcome.head_sequence - 1,
                tuple(sorted(considered)))
            record = outcome.life_record
            try:
                self._check_life_change(record, command, before, outcome.expression)
            except (TypeError, ValueError, KeyError, AttributeError) as error:
                raise PublicationFailedClosed('life-transition-invalid', 'canonical life delta cannot be verified') from error
            if type(command) is SubjectCommand:
                has_dialogue = True
                shares = [replace(share, answered=True) for share in shares]
            if record is None:
                continue
            current = record
            if record.kind == 'advance':
                action = {'drafted': 'start', 'revised': 'revise', 'kept': 'keep', 'rework': 'rework', 'deferred': 'defer'}[record.phase]
                events.append(LifeEvent(record.event_id, outcome.head_sequence, action,
                    record.summary, record.revision, record.reason_code, record.simulated))
                if record.differences:
                    versions.append(LifeVersion(record.revision, record.plan, record.reason_code,
                        record.differences, outcome.head_sequence))
            if record.kind == 'share':
                shares.append(LifeShare(record.share_id, outcome.head_sequence, record.disclosed_event_id,
                    record.revision, record.share_text, outcome.expression.language, False))
            if record.disclosed_event_id:
                disclosed.add(record.disclosed_event_id)
            if record.considered_event_id:
                considered.add(record.considered_event_id)
            if record.kind == 'control':
                last_control_admitted = self.query(outcome.operation_ref).admitted_at_us
        failures = self._writer.execute('''SELECT failure.operation_id, operation.admitted_at_us
            FROM operation_failure failure JOIN subject_operation operation USING(operation_id)
            WHERE operation.operation_kind='system' ORDER BY operation.admitted_at_us''').fetchall()
        technical_problem = ''
        for operation_id, admitted_at in failures:
            ref = self._admitted_for_operation(self._writer, bytes(operation_id), replayed=True).operation_ref
            failed_input = self._query_command(ref)
            failure = self.query_failure(ref)
            if failed_input.input_kind == 'share' and failure.code != 'first-life-share-not-attempted':
                considered.add(failed_input.target_event_id)
            if admitted_at > last_control_admitted:
                technical_problem = failure.code
        return FirstLifeBasis(current, tuple(events), tuple(versions), tuple(shares), has_dialogue,
            any(not share.answered for share in shares), tuple(sorted(disclosed)), len(publications),
            tuple(sorted(considered)), technical_problem)

    def list_first_life(self):
        from dynamic_subject_agent.first_life import FirstLifeQuery, LifeProject
        basis = self.first_life_basis()
        return FirstLifeQuery('available', LifeProject(self._authority.timeline_id, '绘画构图文字方案',
            basis.record.phase, basis.record.revision, basis.record.plan), basis.versions, basis.events, basis.shares,
            basis.technical_problem)

    def _validate_life_plan(self, plan):
        if LIFE_SYSTEM_INTENT not in self._authority.allowed_intents:
            return
        before = self.first_life_basis(expected_head=plan.expected_basis.head_sequence)
        try:
            self._check_life_change(plan.life_record, self._query_command(plan.operation_ref), before, plan.expression)
        except (TypeError, ValueError, KeyError, AttributeError) as error:
            raise CommitPlanRejected('life-transition-invalid', 'life plan differs from canonical preconditions') from error

    def _read_life_record(self, plan_id):
        if LIFE_SYSTEM_INTENT not in self._authority.allowed_intents:
            return None
        row = self._writer.execute('SELECT record_json, record_digest FROM life_record WHERE plan_id=?', (plan_id,)).fetchone()
        if row is None:
            return None
        try:
            record = decode_life_record(json.loads(row[0]))
            self._assert_record_digest('life-record', record, row[1])
            if _canonical_json(record) != row[0]:
                raise ValueError('noncanonical life record')
            return record
        except (TypeError, ValueError, KeyError, AttributeError) as error:
            raise PublicationFailedClosed('life-record-invalid', 'life record is not canonical') from error

    def _claim_commit_plan(
        self,
        plan: CycleCommitPlan,
        plan_digest: bytes,
    ) -> None:
        plan_id = _publication_uuid_bytes(plan.plan_id, "plan_id")
        attempt_id = _publication_uuid_bytes(plan.attempt_id, "attempt_id")
        operation_id = _publication_uuid_bytes(
            plan.operation_ref.operation_id,
            "operation_id",
        )
        cycle_plan_id = _publication_uuid_bytes(plan.cycle_plan_id, "cycle_plan_id")
        subject_event_id = _publication_uuid_bytes(
            plan.subject_event_id,
            "subject_event_id",
        )
        committed = False
        try:
            self._hit(FaultPoint.BEFORE_PLAN_CLAIM)
            _begin(self._writer)
            life = LIFE_SYSTEM_INTENT in self._authority.allowed_intents
            if life and self._writer.execute('SELECT 1 FROM operation_failure WHERE operation_id=?', (operation_id,)).fetchone():
                raise CommitPlanRejected('operation-already-terminal', 'cancelled preparation cannot be claimed or published')
            existing = self._writer.execute(
                """
                SELECT
                    plan_digest,
                    cycle_plan_id,
                    operation_id,
                    attempt_id,
                    subject_event_id,
                    expected_head_sequence,
                    expected_head_outcome_digest,
                    expected_verified_prefix_digest,
                    expected_revision_head_digest,
                    claim_epoch
                FROM commit_plan_identity_claim
                WHERE plan_id = ?
                """,
                (plan_id,),
            ).fetchone()
            expected = (
                plan_digest,
                cycle_plan_id,
                operation_id,
                attempt_id,
                subject_event_id,
                plan.expected_basis.head_sequence,
                _publication_digest_bytes(
                    plan.expected_basis.published_outcome_digest,
                    "published_outcome_digest",
                ),
                _publication_digest_bytes(
                    plan.expected_basis.verified_prefix_digest,
                    "verified_prefix_digest",
                ),
                _publication_digest_bytes(
                    plan.expected_basis.revision_head_digest,
                    "revision_head_digest",
                ),
                1,
            )
            if existing is not None:
                normalized_existing = (
                    bytes(existing[0]),
                    bytes(existing[1]),
                    bytes(existing[2]),
                    bytes(existing[3]),
                    bytes(existing[4]),
                    int(existing[5]),
                    None if existing[6] is None else bytes(existing[6]),
                    bytes(existing[7]),
                    bytes(existing[8]),
                    int(existing[9]),
                )
                if normalized_existing != expected:
                    _rollback_if_needed(self._writer)
                    raise CommitPlanConflict(
                        "commit-plan-identity-conflict",
                        "plan identity already names different immutable content",
                    )
                if life:
                    cached = self.prepared_plan(plan.operation_ref)
                    if cached != plan:
                        raise CommitPlanConflict('prepared-plan-conflict', 'immutable prepared plan differs from its claim')
                _commit(self._writer)
                committed = True
                self._hit(FaultPoint.AFTER_PLAN_CLAIM)
                return

            attempt_claim = self._writer.execute(
                """
                SELECT plan_id, plan_digest
                FROM commit_plan_identity_claim
                WHERE attempt_id = ?
                """,
                (attempt_id,),
            ).fetchone()
            if attempt_claim is not None:
                _rollback_if_needed(self._writer)
                raise CommitPlanConflict(
                    "attempt-plan-conflict",
                    "attempt identity already belongs to a different commit plan",
                )

            admitted = self._admitted_for_operation(
                self._writer,
                operation_id,
                replayed=True,
            )
            if (
                admitted.operation_ref != plan.operation_ref
                or admitted.attempt_id != plan.attempt_id
            ):
                _rollback_if_needed(self._writer)
                raise CommitPlanRejected(
                    "commit-plan-lineage-invalid",
                    "plan Operation or attempt does not match canonical Admission",
                )
            event = self._writer.execute(
                """
                SELECT event_id
                FROM subject_event
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
            if event is None or bytes(event[0]) != subject_event_id:
                _rollback_if_needed(self._writer)
                raise CommitPlanRejected(
                    "commit-plan-lineage-invalid",
                    "plan SubjectEvent does not match canonical Admission",
                )
            cycle_failure = self._writer.execute(
                """
                SELECT 1
                FROM operation_failure
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
            if cycle_failure is not None:
                _rollback_if_needed(self._writer)
                raise CommitPlanRejected(
                    "commit-plan-operation-failed",
                    "a failed-closed cycle cannot enter Publication",
                )

            if life:
                if plan.expected_basis != _read_timeline_basis(self._writer):
                    raise StaleTimelineBasis(plan.expected_basis, _read_timeline_basis(self._writer))
                self._validate_life_plan(plan)

            self._writer.execute(
                """
                INSERT INTO commit_plan_identity_claim (
                    plan_id,
                    plan_digest,
                    cycle_plan_id,
                    operation_id,
                    attempt_id,
                    subject_event_id,
                    expected_head_sequence,
                    expected_head_outcome_digest,
                    expected_verified_prefix_digest,
                    expected_revision_head_digest,
                    claim_epoch,
                    claimed_at_us
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (plan_id,) + expected[:-1] + (_utc_microseconds(),),
            )
            if life:
                self._writer.execute('INSERT INTO prepared_cycle_plan VALUES (?,?,?,?)',
                    (plan_id, operation_id, _canonical_json(plan), plan_digest))
            _commit(self._writer)
            committed = True
            self._hit(FaultPoint.AFTER_PLAN_CLAIM)
        except (CommitPlanRejected, CommitPlanConflict, StaleTimelineBasis):
            _rollback_if_needed(self._writer)
            raise
        except Exception as error:
            try:
                _rollback_if_needed(self._writer)
            except sqlite3.Error:
                self._replace_writer()
            if committed:
                raise PublicationInterrupted(
                    "plan-claim-response-unknown",
                    "plan identity is durable but the claim response was interrupted",
                ) from error
            raise PublicationFailedClosed(
                "plan-claim-failed",
                "commit-plan identity claim did not complete",
            ) from error

    def prepared_plan(self, operation_ref):
        if LIFE_SYSTEM_INTENT not in self._authority.allowed_intents:
            return None
        operation_id = _publication_uuid_bytes(operation_ref.operation_id, 'operation_id')
        row = self._writer.execute('''SELECT prepared.plan_id, prepared.plan_json, prepared.plan_digest,
            claim.plan_digest, claim.operation_id, claim.attempt_id, claim.subject_event_id,
            claim.expected_head_sequence, claim.expected_head_outcome_digest,
            claim.expected_verified_prefix_digest, claim.expected_revision_head_digest
            FROM prepared_cycle_plan prepared LEFT JOIN commit_plan_identity_claim claim USING(plan_id)
            WHERE prepared.operation_id=?''', (operation_id,)).fetchone()
        claim = self._writer.execute('SELECT 1 FROM commit_plan_identity_claim WHERE operation_id=?', (operation_id,)).fetchone()
        if row is None:
            if claim is not None:
                raise PublicationFailedClosed('prepared-plan-missing', 'durable claim has no complete prepared plan')
            return None
        try:
            plan = CycleCommitPlan.from_dict(json.loads(row[1]))
            self._validate_commit_plan(plan)
            digest = _publication_digest('cycle-commit-plan', plan)
            admitted = self._admitted_for_operation(self._writer, operation_id, replayed=True)
            basis = TimelineBasis(int(row[7]), None if row[8] is None else bytes(row[8]).hex(), bytes(row[9]).hex(), bytes(row[10]).hex())
            frozen = self._writer.execute('''SELECT attempt_id, head_sequence, published_outcome_digest,
                verified_prefix_digest, revision_head_digest FROM attempt_cycle_basis WHERE operation_id=?''', (operation_id,)).fetchone()
            event = self._writer.execute('SELECT event_id FROM subject_event WHERE operation_id=?', (operation_id,)).fetchone()
            expected_frozen = (UUID(plan.attempt_id).bytes, basis.head_sequence,
                None if basis.published_outcome_digest is None else bytes.fromhex(basis.published_outcome_digest),
                bytes.fromhex(basis.verified_prefix_digest), bytes.fromhex(basis.revision_head_digest))
            if (plan.operation_ref != operation_ref or admitted.operation_ref != operation_ref
                or plan.attempt_id != admitted.attempt_id or plan.expected_basis != basis
                or frozen != expected_frozen or event != (UUID(plan.subject_event_id).bytes,)
                or bytes(row[0]) != UUID(plan.plan_id).bytes or bytes(row[2]) != digest or bytes(row[3]) != digest
                or bytes(row[4]) != operation_id or bytes(row[5]) != UUID(plan.attempt_id).bytes
                or bytes(row[6]) != UUID(plan.subject_event_id).bytes or _canonical_json(plan) != row[1]):
                raise ValueError('prepared plan differs from immutable claim')
            self._query_command(operation_ref)
            return plan
        except (TypeError, ValueError, KeyError, AttributeError, CommitPlanRejected) as error:
            raise PublicationFailedClosed('prepared-plan-invalid', 'complete prepared plan cannot be verified') from error

    def _share_day_expired(self, operation_ref):
        if operation_ref.operation_kind is not OperationKind.SYSTEM:
            return False
        from dynamic_subject_agent.first_life import current_civil_day
        from datetime import date
        command = self._query_command(operation_ref)
        if command.input_kind != 'share':
            return False
        today = current_civil_day()
        if not isinstance(today, str) or date.fromisoformat(today).isoformat() != today:
            raise PublicationFailedClosed('first-life-clock-unverified', 'the trusted civil day is unavailable')
        return command.civil_day != today

    def cancel_prepared_if_stale(self, operation_ref):
        """Atomically terminate an obsolete schema-3 preparation, without publication."""
        self._require_life_authority()
        try:
            _begin(self._writer)
            plan = self.prepared_plan(operation_ref)
            snapshot = self.query(operation_ref)
            if snapshot.operation_state is not OperationState.ADMITTED_PENDING or plan is None:
                _commit(self._writer)
                return False
            current = _read_timeline_basis(self._writer)
            expired_share = self._share_day_expired(operation_ref)
            if current == plan.expected_basis and not expired_share:
                _commit(self._writer)
                return False
            # A corrupt/deleted/regressed chain must never count as cancellation evidence.
            self._verified_publications()
            if current != plan.expected_basis and current.head_sequence <= plan.expected_basis.head_sequence:
                raise PublicationFailedClosed('prepared-basis-invalid', 'changed basis is not a verified successor')
            prefix = self._writer.execute('SELECT outcome_digest FROM timeline_outcome WHERE head_sequence=?',
                (plan.expected_basis.head_sequence,)).fetchone()
            if (None if prefix is None else bytes(prefix[0]).hex()) != plan.expected_basis.published_outcome_digest:
                raise PublicationFailedClosed('prepared-prefix-invalid', 'preparation does not belong to the current chain')
            operation_id = UUID(operation_ref.operation_id).bytes
            if (self._writer.execute('SELECT 1 FROM publication_receipt WHERE plan_id=?', (UUID(plan.plan_id).bytes,)).fetchone()
                or self._writer.execute('SELECT 1 FROM cycle_commit_plan_receipt WHERE plan_id=?', (UUID(plan.plan_id).bytes,)).fetchone()
                or self._writer.execute('SELECT 1 FROM timeline_outcome WHERE operation_id=?', (operation_id,)).fetchone()
                or self._writer.execute('SELECT 1 FROM operation_publication_state WHERE operation_id=?', (operation_id,)).fetchone()):
                raise PublicationFailedClosed('prepared-terminal-conflict', 'prepared cancellation encountered publication evidence')
            code = 'first-life-share-day-expired' if expired_share else 'first-life-stale-preparation'
            detail = ('The prepared share was cancelled because its trusted publication day differs from its claim day.'
                if expired_share else 'The prepared operation was cancelled because its verified canonical basis changed.')
            recorded_at = _utc_microseconds()
            self._writer.execute('INSERT INTO operation_failure VALUES (?,?,?,?,?,?)',
                (operation_id, UUID(plan.attempt_id).bytes, 'publication', code, detail, recorded_at))
            self._writer.execute("INSERT INTO cycle_failure_transition VALUES (?,2,'admitted-pending','failed-closed',?)",
                (operation_id, recorded_at))
            self._hit(FaultPoint.BEFORE_PREPARED_CANCEL_COMMIT)
            _commit(self._writer)
            self._hit(FaultPoint.AFTER_PREPARED_CANCEL_COMMIT)
            return True
        except Exception:
            _rollback_if_needed(self._writer)
            raise

    def _record_stale_conflict(
        self,
        plan: CycleCommitPlan,
        observed_basis: TimelineBasis,
    ) -> None:
        operation_id = _publication_uuid_bytes(
            plan.operation_ref.operation_id,
            "operation_id",
        )
        attempt_id = _publication_uuid_bytes(plan.attempt_id, "attempt_id")
        plan_id = _publication_uuid_bytes(plan.plan_id, "plan_id")
        recorded_at = _utc_microseconds()
        try:
            _begin(self._writer)
            self._writer.execute(
                """
                INSERT OR IGNORE INTO publication_conflict_fact (
                    conflict_id,
                    plan_id,
                    operation_id,
                    expected_head_sequence,
                    observed_head_sequence,
                    conflict_code,
                    recorded_at_us
                ) VALUES (?, ?, ?, ?, ?, 'stale-timeline-basis', ?)
                """,
                (
                    uuid4().bytes,
                    plan_id,
                    operation_id,
                    plan.expected_basis.head_sequence,
                    observed_basis.head_sequence,
                    recorded_at,
                ),
            )
            self._writer.execute(
                """
                INSERT OR IGNORE INTO operation_publication_state (
                    operation_id,
                    attempt_id,
                    operation_state,
                    attempt_state,
                    plan_id,
                    outcome_id,
                    claim_epoch,
                    updated_at_us
                ) VALUES (?, ?, 'interrupted', 'interrupted', ?, NULL, 1, ?)
                """,
                (operation_id, attempt_id, plan_id, recorded_at),
            )
            self._writer.execute(
                """
                INSERT OR IGNORE INTO publication_transition (
                    operation_id,
                    transition_ordinal,
                    from_state,
                    to_state,
                    plan_id,
                    recorded_at_us
                ) VALUES (?, 2, 'admitted-pending', 'interrupted', ?, ?)
                """,
                (operation_id, plan_id, recorded_at),
            )
            _commit(self._writer)
        except Exception as error:
            _rollback_if_needed(self._writer)
            raise PublicationInterrupted(
                "publication-conflict-fact-interrupted",
                "stale basis was proven but its recovery fact was not durable",
            ) from error

    def _resolve_publication_commit(
        self,
        plan: CycleCommitPlan,
        plan_digest: bytes,
        *,
        cause: BaseException | None = None,
    ) -> Published:
        try:
            self._replace_writer()
            row = self._writer.execute(
                """
                SELECT
                    commit_plan_identity_claim.plan_digest,
                    publication_receipt.outcome_id
                FROM commit_plan_identity_claim
                LEFT JOIN publication_receipt USING (plan_id)
                WHERE plan_id = ?
                """,
                (_publication_uuid_bytes(plan.plan_id, "plan_id"),),
            ).fetchone()
            if row is None or bytes(row[0]) != plan_digest or row[1] is None:
                raise PublicationInterrupted(
                    "publication-commit-outcome-unknown",
                    "canonical state has no proof of the attempted Publication",
                )
            outcome = self.query_outcome(plan.operation_ref)
            if outcome.plan_id != plan.plan_id:
                raise PublicationInterrupted(
                    "publication-commit-outcome-unknown",
                    "canonical outcome does not match the immutable plan identity",
                )
            return Published(
                outcome=outcome,
                replayed=True,
                recovered_after_commit=True,
            )
        except PublicationInterrupted:
            raise
        except Exception as error:
            interrupted = PublicationInterrupted(
                "publication-commit-outcome-unknown",
                "canonical state could not prove the attempted Publication",
            )
            if cause is not None:
                raise interrupted from cause
            raise interrupted from error

    def _insert_commit_plan_receipt(
        self,
        plan: CycleCommitPlan,
        plan_digest: bytes,
        published_at: int,
    ) -> None:
        self._writer.execute(
            """
            INSERT INTO cycle_commit_plan_receipt (
                plan_id,
                plan_digest,
                cycle_plan_id,
                operation_id,
                attempt_id,
                subject_event_id,
                profile_id,
                timeline_id,
                expected_head_sequence,
                expected_head_outcome_digest,
                expected_verified_prefix_digest,
                expected_revision_head_digest,
                published_at_us
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _publication_uuid_bytes(plan.plan_id, "plan_id"),
                plan_digest,
                _publication_uuid_bytes(plan.cycle_plan_id, "cycle_plan_id"),
                _publication_uuid_bytes(
                    plan.operation_ref.operation_id,
                    "operation_id",
                ),
                _publication_uuid_bytes(plan.attempt_id, "attempt_id"),
                _publication_uuid_bytes(
                    plan.subject_event_id,
                    "subject_event_id",
                ),
                plan.profile_id,
                plan.timeline_id,
                plan.expected_basis.head_sequence,
                _publication_digest_bytes(
                    plan.expected_basis.published_outcome_digest,
                    "published_outcome_digest",
                ),
                _publication_digest_bytes(
                    plan.expected_basis.verified_prefix_digest,
                    "verified_prefix_digest",
                ),
                _publication_digest_bytes(
                    plan.expected_basis.revision_head_digest,
                    "revision_head_digest",
                ),
                published_at,
            ),
        )

    def _insert_experience_records(self, plan: CycleCommitPlan) -> None:
        plan_id = _publication_uuid_bytes(plan.plan_id, "plan_id")
        self._writer.execute(
            """
            INSERT INTO experience_record (
                experience_id,
                plan_id,
                summary,
                experienced_at_us,
                record_digest
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                _publication_uuid_bytes(
                    plan.experience.experience_id,
                    "experience_id",
                ),
                plan_id,
                plan.experience.summary,
                plan.experience.experienced_at_us,
                _publication_digest("experience-record", plan.experience),
            ),
        )
        self._hit(FaultPoint.AFTER_EXPERIENCE)
        self._writer.execute(
            """
            INSERT INTO epistemic_outcome (
                epistemic_outcome_id,
                plan_id,
                status,
                reason,
                route_version,
                verified_prefix_digest,
                completed_stages_json,
                outcome_digest
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _publication_uuid_bytes(
                    plan.epistemic_outcome.epistemic_outcome_id,
                    "epistemic_outcome_id",
                ),
                plan_id,
                plan.epistemic_outcome.status.value,
                plan.epistemic_outcome.reason,
                plan.epistemic_outcome.route_version,
                _publication_digest_bytes(
                    plan.epistemic_outcome.verified_prefix_digest,
                    "epistemic_verified_prefix_digest",
                ),
                _canonical_json(plan.epistemic_outcome.completed_stages),
                _publication_digest(
                    "epistemic-outcome",
                    plan.epistemic_outcome,
                ),
            ),
        )
        self._hit(FaultPoint.AFTER_EPISTEMIC)

    def _plan_decisions(
        self,
        plan: CycleCommitPlan,
    ) -> tuple[CandidateDecisionRecord, ...]:
        return (
            plan.experience_outcome.decision,
            plan.subject_state_outcome.decision,
            plan.subject_state_outcome.subject_core.decision,
            plan.subject_state_outcome.development.decision,
            plan.agency_outcome.decision,
            plan.relationship_outcome.decision,
        )

    def _insert_candidate_decisions(self, plan: CycleCommitPlan) -> None:
        plan_id = _publication_uuid_bytes(plan.plan_id, "plan_id")
        for decision in self._plan_decisions(plan):
            self._writer.execute(
                """
                INSERT INTO candidate_decision_record (
                    decision_id,
                    plan_id,
                    scope,
                    status,
                    reason,
                    rule_version,
                    actual_revision_ids_json,
                    decision_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _publication_uuid_bytes(
                        decision.decision_id,
                        "decision_id",
                    ),
                    plan_id,
                    decision.scope,
                    decision.status.value,
                    decision.reason,
                    decision.rule_version,
                    _canonical_json(decision.actual_revision_ids),
                    _publication_digest(
                        "candidate-decision-record",
                        decision,
                    ),
                ),
            )
        self._hit(FaultPoint.AFTER_CANDIDATE_DECISIONS)

    def _insert_experience_and_subject_state_outcomes(
        self,
        plan: CycleCommitPlan,
    ) -> None:
        plan_id = _publication_uuid_bytes(plan.plan_id, "plan_id")
        epistemic_id = _publication_uuid_bytes(
            plan.epistemic_outcome.epistemic_outcome_id,
            "epistemic_outcome_id",
        )
        self._writer.execute(
            """
            INSERT INTO experience_domain_outcome (
                outcome_id,
                plan_id,
                decision_id,
                epistemic_outcome_id,
                outcome_digest
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                _publication_uuid_bytes(
                    plan.experience_outcome.outcome_id,
                    "experience_outcome_id",
                ),
                plan_id,
                _publication_uuid_bytes(
                    plan.experience_outcome.decision.decision_id,
                    "experience_decision_id",
                ),
                epistemic_id,
                _publication_digest(
                    "experience-domain-outcome",
                    plan.experience_outcome,
                ),
            ),
        )
        subject_core_id = _publication_uuid_bytes(
            plan.subject_state_outcome.subject_core.outcome_id,
            "subject_core_outcome_id",
        )
        self._writer.execute(
            """
            INSERT INTO subject_core_outcome (
                outcome_id,
                plan_id,
                decision_id,
                outcome_digest
            ) VALUES (?, ?, ?, ?)
            """,
            (
                subject_core_id,
                plan_id,
                _publication_uuid_bytes(
                    plan.subject_state_outcome.subject_core.decision.decision_id,
                    "subject_core_decision_id",
                ),
                _publication_digest(
                    "subject-core-outcome",
                    plan.subject_state_outcome.subject_core,
                ),
            ),
        )
        development_id = _publication_uuid_bytes(
            plan.subject_state_outcome.development.outcome_id,
            "development_outcome_id",
        )
        self._writer.execute(
            """
            INSERT INTO development_outcome (
                outcome_id,
                plan_id,
                decision_id,
                outcome_digest
            ) VALUES (?, ?, ?, ?)
            """,
            (
                development_id,
                plan_id,
                _publication_uuid_bytes(
                    plan.subject_state_outcome.development.decision.decision_id,
                    "development_decision_id",
                ),
                _publication_digest(
                    "development-outcome",
                    plan.subject_state_outcome.development,
                ),
            ),
        )
        self._writer.execute(
            """
            INSERT INTO subject_state_domain_outcome (
                outcome_id,
                plan_id,
                decision_id,
                subject_core_outcome_id,
                development_outcome_id,
                outcome_digest
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _publication_uuid_bytes(
                    plan.subject_state_outcome.outcome_id,
                    "subject_state_outcome_id",
                ),
                plan_id,
                _publication_uuid_bytes(
                    plan.subject_state_outcome.decision.decision_id,
                    "subject_state_decision_id",
                ),
                subject_core_id,
                development_id,
                _publication_digest(
                    "subject-state-domain-outcome",
                    plan.subject_state_outcome,
                ),
            ),
        )

    def _insert_agency_relationship_and_domain_set(
        self,
        plan: CycleCommitPlan,
    ) -> None:
        plan_id = _publication_uuid_bytes(plan.plan_id, "plan_id")
        agency_id = _publication_uuid_bytes(
            plan.agency_outcome.outcome_id,
            "agency_outcome_id",
        )
        self._writer.execute(
            """
            INSERT INTO agency_domain_outcome (
                outcome_id,
                plan_id,
                decision_id,
                committed_effect_eligible,
                outcome_digest
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                agency_id,
                plan_id,
                _publication_uuid_bytes(
                    plan.agency_outcome.decision.decision_id,
                    "agency_decision_id",
                ),
                int(plan.agency_outcome.committed_effect_eligible),
                _publication_digest(
                    "agency-domain-outcome",
                    plan.agency_outcome,
                ),
            ),
        )
        relationship_id = _publication_uuid_bytes(
            plan.relationship_outcome.outcome_id,
            "relationship_outcome_id",
        )
        self._writer.execute(
            """
            INSERT INTO relationship_domain_outcome (
                outcome_id,
                plan_id,
                decision_id,
                relationship_target_id,
                outcome_digest
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                relationship_id,
                plan_id,
                _publication_uuid_bytes(
                    plan.relationship_outcome.decision.decision_id,
                    "relationship_decision_id",
                ),
                plan.relationship_outcome.relationship_target_id,
                _publication_digest(
                    "relationship-domain-outcome",
                    plan.relationship_outcome,
                ),
            ),
        )
        domain_outcomes = (
            plan.experience_outcome,
            plan.subject_state_outcome,
            plan.agency_outcome,
            plan.relationship_outcome,
        )
        self._writer.execute(
            """
            INSERT INTO domain_outcome_set (
                plan_id,
                experience_outcome_id,
                subject_state_outcome_id,
                agency_outcome_id,
                relationship_outcome_id,
                set_digest
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id,
                _publication_uuid_bytes(
                    plan.experience_outcome.outcome_id,
                    "experience_outcome_id",
                ),
                _publication_uuid_bytes(
                    plan.subject_state_outcome.outcome_id,
                    "subject_state_outcome_id",
                ),
                agency_id,
                relationship_id,
                _publication_digest("domain-outcome-set", domain_outcomes),
            ),
        )
        self._hit(FaultPoint.AFTER_DOMAIN_OUTCOMES)

    def _insert_revision_expression_and_effect_set(
        self,
        plan: CycleCommitPlan,
    ) -> None:
        plan_id = _publication_uuid_bytes(plan.plan_id, "plan_id")
        self._writer.execute(
            """
            INSERT INTO revision_set (
                revision_set_id,
                plan_id,
                revision_count,
                revision_ids_json,
                set_digest
            ) VALUES (?, ?, 0, ?, ?)
            """,
            (
                _publication_uuid_bytes(
                    plan.revision_set.revision_set_id,
                    "revision_set_id",
                ),
                plan_id,
                _canonical_json(plan.revision_set.revision_ids),
                _publication_digest("revision-set", plan.revision_set),
            ),
        )
        self._hit(FaultPoint.AFTER_REVISION_SET)
        self._writer.execute(
            """
            INSERT INTO expression_record (
                expression_id,
                plan_id,
                expression_text,
                language,
                grounding_decision_ids_json,
                expression_digest
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _publication_uuid_bytes(
                    plan.expression.expression_id,
                    "expression_id",
                ),
                plan_id,
                plan.expression.text,
                plan.expression.language,
                _canonical_json(plan.expression.grounding_decision_ids),
                _publication_digest("expression", plan.expression),
            ),
        )
        self._hit(FaultPoint.AFTER_EXPRESSION)
        self._writer.execute(
            """
            INSERT INTO committed_effect_set (
                effect_set_id,
                plan_id,
                effect_count,
                reference_ids_json,
                dispatch_state,
                reason,
                set_digest
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _publication_uuid_bytes(
                    plan.committed_effect_set.effect_set_id,
                    "effect_set_id",
                ),
                plan_id,
                len(plan.committed_effect_set.reference_ids),
                _canonical_json(plan.committed_effect_set.reference_ids),
                plan.committed_effect_set.dispatch_state.value,
                plan.committed_effect_set.reason,
                _publication_digest(
                    "committed-effect-set",
                    plan.committed_effect_set,
                ),
            ),
        )
        self._hit(FaultPoint.AFTER_EFFECT_SET)

    def _insert_outcome_and_advance_head(
        self,
        plan: CycleCommitPlan,
        plan_digest: bytes,
        observed_basis: TimelineBasis,
        published_at: int,
    ) -> None:
        operation_id = _publication_uuid_bytes(
            plan.operation_ref.operation_id,
            "operation_id",
        )
        attempt_id = _publication_uuid_bytes(plan.attempt_id, "attempt_id")
        subject_event_id = _publication_uuid_bytes(
            plan.subject_event_id,
            "subject_event_id",
        )
        plan_id = _publication_uuid_bytes(plan.plan_id, "plan_id")
        outcome_id = uuid4().bytes
        head_sequence = observed_basis.head_sequence + 1
        outcome_digest = _publication_digest(
            "timeline-outcome",
            {
                "outcome_id": str(UUID(bytes=outcome_id)),
                "operation_ref": plan.operation_ref,
                "attempt_id": plan.attempt_id,
                "subject_event_id": plan.subject_event_id,
                "plan_id": plan.plan_id,
                "plan_digest": plan_digest.hex(),
                "head_sequence": head_sequence,
                "previous_outcome_digest": (observed_basis.published_outcome_digest),
                "experience": plan.experience,
                "epistemic_outcome": plan.epistemic_outcome,
                "experience_outcome": plan.experience_outcome,
                "subject_state_outcome": plan.subject_state_outcome,
                "agency_outcome": plan.agency_outcome,
                "relationship_outcome": plan.relationship_outcome,
                "revision_set": plan.revision_set,
                "expression": plan.expression,
                "committed_effect_set": plan.committed_effect_set,
                **({'life_record': plan.life_record} if plan.life_record is not None else {}),
            },
        )
        self._writer.execute(
            """
            INSERT INTO timeline_outcome (
                outcome_id,
                operation_id,
                attempt_id,
                subject_event_id,
                plan_id,
                head_sequence,
                previous_outcome_digest,
                outcome_digest,
                experience_id,
                epistemic_outcome_id,
                experience_outcome_id,
                subject_state_outcome_id,
                agency_outcome_id,
                relationship_outcome_id,
                revision_set_id,
                expression_id,
                effect_set_id,
                published_at_us
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                outcome_id,
                operation_id,
                attempt_id,
                subject_event_id,
                plan_id,
                head_sequence,
                _publication_digest_bytes(
                    observed_basis.published_outcome_digest,
                    "previous_outcome_digest",
                ),
                outcome_digest,
                _publication_uuid_bytes(
                    plan.experience.experience_id,
                    "experience_id",
                ),
                _publication_uuid_bytes(
                    plan.epistemic_outcome.epistemic_outcome_id,
                    "epistemic_outcome_id",
                ),
                _publication_uuid_bytes(
                    plan.experience_outcome.outcome_id,
                    "experience_outcome_id",
                ),
                _publication_uuid_bytes(
                    plan.subject_state_outcome.outcome_id,
                    "subject_state_outcome_id",
                ),
                _publication_uuid_bytes(
                    plan.agency_outcome.outcome_id,
                    "agency_outcome_id",
                ),
                _publication_uuid_bytes(
                    plan.relationship_outcome.outcome_id,
                    "relationship_outcome_id",
                ),
                _publication_uuid_bytes(
                    plan.revision_set.revision_set_id,
                    "revision_set_id",
                ),
                _publication_uuid_bytes(
                    plan.expression.expression_id,
                    "expression_id",
                ),
                _publication_uuid_bytes(
                    plan.committed_effect_set.effect_set_id,
                    "effect_set_id",
                ),
                published_at,
            ),
        )
        self._writer.execute(
            """
            INSERT INTO publication_receipt (
                plan_id,
                outcome_id,
                outcome_digest,
                published_at_us
            ) VALUES (?, ?, ?, ?)
            """,
            (plan_id, outcome_id, outcome_digest, published_at),
        )
        self._hit(FaultPoint.AFTER_TIMELINE_OUTCOME)

        expected_head_digest = _publication_digest_bytes(
            observed_basis.published_outcome_digest,
            "expected_head_outcome_digest",
        )
        advanced = self._writer.execute(
            """
            UPDATE timeline_head
            SET head_sequence = ?, published_outcome_digest = ?
            WHERE singleton = 1
              AND head_sequence = ?
              AND (
                  (published_outcome_digest IS NULL AND ? IS NULL)
                  OR published_outcome_digest = ?
              )
            """,
            (
                head_sequence,
                outcome_digest,
                observed_basis.head_sequence,
                expected_head_digest,
                expected_head_digest,
            ),
        )
        integrity_advanced = self._writer.execute(
            """
            UPDATE timeline_integrity
            SET
                verified_prefix_digest = ?,
                revision_head_digest = ?
            WHERE singleton = 1
              AND verified_prefix_digest = ?
              AND revision_head_digest = ?
            """,
            (
                _publication_digest_bytes(
                    plan.epistemic_outcome.verified_prefix_digest,
                    "new_verified_prefix_digest",
                ),
                _publication_digest_bytes(
                    plan.expected_basis.revision_head_digest,
                    "new_revision_head_digest",
                ),
                _publication_digest_bytes(
                    observed_basis.verified_prefix_digest,
                    "expected_verified_prefix_digest",
                ),
                _publication_digest_bytes(
                    observed_basis.revision_head_digest,
                    "expected_revision_head_digest",
                ),
            ),
        )
        if advanced.rowcount != 1 or integrity_advanced.rowcount != 1:
            raise StaleTimelineBasis(
                plan.expected_basis,
                _read_timeline_basis(self._writer),
            )
        self._hit(FaultPoint.AFTER_HEAD_ADVANCE)
        self._writer.execute(
            """
            INSERT INTO operation_publication_state (
                operation_id,
                attempt_id,
                operation_state,
                attempt_state,
                plan_id,
                outcome_id,
                claim_epoch,
                updated_at_us
            ) VALUES (?, ?, 'completed', 'published', ?, ?, 1, ?)
            """,
            (
                operation_id,
                attempt_id,
                plan_id,
                outcome_id,
                published_at,
            ),
        )
        self._writer.execute(
            """
            INSERT INTO publication_transition (
                operation_id,
                transition_ordinal,
                from_state,
                to_state,
                plan_id,
                recorded_at_us
            ) VALUES (?, 2, 'admitted-pending', 'completed', ?, ?)
            """,
            (operation_id, plan_id, published_at),
        )
        self._hit(FaultPoint.AFTER_ATTEMPT_TERMINAL)

    def publish(self, plan: CycleCommitPlan) -> Published:
        self._require_open()
        self._validate_commit_plan(plan)
        _require_publication_gate(self._writer, self._authority)
        plan_digest = _publication_digest("cycle-commit-plan", plan)
        self._claim_commit_plan(plan, plan_digest)

        operation_id = _publication_uuid_bytes(
            plan.operation_ref.operation_id,
            "operation_id",
        )
        attempt_id = _publication_uuid_bytes(plan.attempt_id, "attempt_id")
        subject_event_id = _publication_uuid_bytes(
            plan.subject_event_id,
            "subject_event_id",
        )
        plan_id = _publication_uuid_bytes(plan.plan_id, "plan_id")
        commit_started = False
        try:
            self._hit(FaultPoint.BEFORE_PUBLICATION_TRANSACTION)
            _begin(self._writer)
            _require_publication_gate(self._writer, self._authority)
            if (LIFE_SYSTEM_INTENT in self._authority.allowed_intents
                and self._writer.execute('SELECT 1 FROM operation_failure WHERE operation_id=?', (operation_id,)).fetchone()):
                raise CommitPlanRejected('operation-already-terminal', 'cancelled preparation cannot publish')
            existing = self._writer.execute(
                """
                SELECT
                    cycle_commit_plan_receipt.plan_digest,
                    publication_receipt.outcome_id
                FROM cycle_commit_plan_receipt
                JOIN publication_receipt USING (plan_id)
                WHERE plan_id = ?
                """,
                (plan_id,),
            ).fetchone()
            if existing is not None:
                if bytes(existing[0]) != plan_digest:
                    raise CommitPlanConflict(
                        "commit-plan-identity-conflict",
                        "published plan identity has a different digest",
                    )
                _commit(self._writer)
                return Published(
                    outcome=self.query_outcome(plan.operation_ref),
                    replayed=True,
                )

            claimed = self._writer.execute(
                """
                SELECT
                    plan_digest,
                    operation_id,
                    attempt_id,
                    subject_event_id,
                    claim_epoch
                FROM commit_plan_identity_claim
                WHERE plan_id = ?
                """,
                (plan_id,),
            ).fetchone()
            if claimed is None or (
                bytes(claimed[0]),
                bytes(claimed[1]),
                bytes(claimed[2]),
                bytes(claimed[3]),
                int(claimed[4]),
            ) != (
                plan_digest,
                operation_id,
                attempt_id,
                subject_event_id,
                1,
            ):
                raise CommitPlanConflict(
                    "commit-plan-claim-mismatch",
                    "Publication is fenced from the immutable plan claim",
                )
            other_outcome = self._writer.execute(
                """
                SELECT plan_id
                FROM timeline_outcome
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
            if other_outcome is not None:
                raise CommitPlanConflict(
                    "operation-outcome-conflict",
                    "Operation already has a TimelineOutcome from another plan",
                )

            observed_basis = _read_timeline_basis(self._writer)
            if not _basis_matches(plan.expected_basis, observed_basis):
                raise StaleTimelineBasis(plan.expected_basis, observed_basis)
            admitted = self._admitted_for_operation(
                self._writer,
                operation_id,
                replayed=True,
            )
            if (
                admitted.operation_ref != plan.operation_ref
                or admitted.attempt_id != plan.attempt_id
            ):
                raise CommitPlanRejected(
                    "commit-plan-lineage-invalid",
                    "canonical Admission changed before Publication",
                )

            published_at = _utc_microseconds()
            self._validate_life_plan(plan)
            self._insert_commit_plan_receipt(
                plan,
                plan_digest,
                published_at,
            )
            self._hit(FaultPoint.AFTER_COMMIT_PLAN_RECEIPT)
            self._insert_experience_records(plan)
            self._insert_candidate_decisions(plan)
            self._insert_experience_and_subject_state_outcomes(plan)
            self._insert_agency_relationship_and_domain_set(plan)
            self._insert_revision_expression_and_effect_set(plan)
            if plan.life_record is not None:
                self._writer.execute('INSERT INTO life_record VALUES (?,?,?)',
                    (plan_id, _canonical_json(plan.life_record), _publication_digest('life-record', plan.life_record)))
            self._insert_outcome_and_advance_head(
                plan,
                plan_digest,
                observed_basis,
                published_at,
            )
            self._hit(FaultPoint.BEFORE_PUBLICATION_COMMIT)
            # The final authorization sample defines the publication accounting
            # day. Nothing that may wait on a fault hook precedes COMMIT after it.
            if LIFE_SYSTEM_INTENT in self._authority.allowed_intents and self._share_day_expired(plan.operation_ref):
                raise _PreparedShareDayExpired()
            commit_started = True
            _commit(self._writer)
            try:
                self._hit(FaultPoint.AFTER_PUBLICATION_COMMIT)
            except Exception as error:
                return self._resolve_publication_commit(
                    plan,
                    plan_digest,
                    cause=error,
                )
            return Published(
                outcome=self.query_outcome(plan.operation_ref),
                replayed=False,
            )
        except _PreparedShareDayExpired:
            _rollback_if_needed(self._writer)
            self.cancel_prepared_if_stale(plan.operation_ref)
            raise
        except StaleTimelineBasis as error:
            _rollback_if_needed(self._writer)
            if LIFE_SYSTEM_INTENT in self._authority.allowed_intents:
                self.cancel_prepared_if_stale(plan.operation_ref)
            else:
                self._record_stale_conflict(plan, error.observed_basis)
            raise
        except (
            CommitPlanRejected,
            CommitPlanConflict,
            PublicationInterrupted,
        ):
            _rollback_if_needed(self._writer)
            raise
        except Exception as error:
            if not commit_started:
                try:
                    _rollback_if_needed(self._writer)
                except sqlite3.Error:
                    self._replace_writer()
                raise PublicationFailedClosed(
                    "publication-transaction-failed",
                    "Publication rolled back before the atomic commit",
                ) from error
            return self._resolve_publication_commit(
                plan,
                plan_digest,
                cause=error,
            )

    def _assert_record_digest(
        self,
        kind: str,
        value: Any,
        stored_digest: Any,
    ) -> None:
        if bytes(stored_digest) != _publication_digest(kind, value):
            raise PublicationFailedClosed(
                "canonical-publication-integrity-mismatch",
                f"{kind} record digest does not match canonical content",
            )

    def _read_decision(self, decision_id: bytes) -> CandidateDecisionRecord:
        row = self._writer.execute(
            """
            SELECT
                scope,
                status,
                reason,
                rule_version,
                actual_revision_ids_json,
                decision_digest
            FROM candidate_decision_record
            WHERE decision_id = ?
            """,
            (decision_id,),
        ).fetchone()
        if row is None:
            raise PublicationFailedClosed(
                "canonical-publication-incomplete",
                "CandidateDecisionRecord is absent",
            )
        value = CandidateDecisionRecord(
            decision_id=str(UUID(bytes=decision_id)),
            scope=str(row[0]),
            status=DecisionStatus(str(row[1])),
            reason=str(row[2]),
            rule_version=str(row[3]),
            actual_revision_ids=tuple(json.loads(str(row[4]))),
        )
        self._assert_record_digest(
            "candidate-decision-record",
            value,
            row[5],
        )
        return value

    def _read_experience(self, experience_id: bytes) -> ExperienceRecord:
        row = self._writer.execute(
            """
            SELECT summary, experienced_at_us, record_digest
            FROM experience_record
            WHERE experience_id = ?
            """,
            (experience_id,),
        ).fetchone()
        if row is None:
            raise PublicationFailedClosed(
                "canonical-publication-incomplete",
                "ExperienceRecord is absent",
            )
        value = ExperienceRecord(
            experience_id=str(UUID(bytes=experience_id)),
            summary=str(row[0]),
            experienced_at_us=int(row[1]),
        )
        self._assert_record_digest("experience-record", value, row[2])
        return value

    def _read_epistemic(self, outcome_id: bytes) -> EpistemicOutcome:
        row = self._writer.execute(
            """
            SELECT
                status,
                reason,
                route_version,
                verified_prefix_digest,
                completed_stages_json,
                outcome_digest
            FROM epistemic_outcome
            WHERE epistemic_outcome_id = ?
            """,
            (outcome_id,),
        ).fetchone()
        if row is None:
            raise PublicationFailedClosed(
                "canonical-publication-incomplete",
                "EpistemicOutcome is absent",
            )
        value = EpistemicOutcome(
            epistemic_outcome_id=str(UUID(bytes=outcome_id)),
            status=DecisionStatus(str(row[0])),
            reason=str(row[1]),
            route_version=str(row[2]),
            verified_prefix_digest=bytes(row[3]).hex(),
            completed_stages=tuple(json.loads(str(row[4]))),
        )
        self._assert_record_digest("epistemic-outcome", value, row[5])
        return value

    def _read_experience_outcome(
        self,
        outcome_id: bytes,
    ) -> ExperienceDomainOutcome:
        row = self._writer.execute(
            """
            SELECT decision_id, epistemic_outcome_id, outcome_digest
            FROM experience_domain_outcome
            WHERE outcome_id = ?
            """,
            (outcome_id,),
        ).fetchone()
        if row is None:
            raise PublicationFailedClosed(
                "canonical-publication-incomplete",
                "ExperienceDomainOutcome is absent",
            )
        value = ExperienceDomainOutcome(
            outcome_id=str(UUID(bytes=outcome_id)),
            decision=self._read_decision(bytes(row[0])),
            epistemic_outcome_id=str(UUID(bytes=bytes(row[1]))),
        )
        self._assert_record_digest(
            "experience-domain-outcome",
            value,
            row[2],
        )
        return value

    def _read_subject_core(self, outcome_id: bytes) -> SubjectCoreOutcome:
        row = self._writer.execute(
            """
            SELECT decision_id, outcome_digest
            FROM subject_core_outcome
            WHERE outcome_id = ?
            """,
            (outcome_id,),
        ).fetchone()
        if row is None:
            raise PublicationFailedClosed(
                "canonical-publication-incomplete",
                "SubjectCoreOutcome is absent",
            )
        value = SubjectCoreOutcome(
            outcome_id=str(UUID(bytes=outcome_id)),
            decision=self._read_decision(bytes(row[0])),
        )
        self._assert_record_digest("subject-core-outcome", value, row[1])
        return value

    def _read_development(self, outcome_id: bytes) -> DevelopmentOutcome:
        row = self._writer.execute(
            """
            SELECT decision_id, outcome_digest
            FROM development_outcome
            WHERE outcome_id = ?
            """,
            (outcome_id,),
        ).fetchone()
        if row is None:
            raise PublicationFailedClosed(
                "canonical-publication-incomplete",
                "DevelopmentOutcome is absent",
            )
        value = DevelopmentOutcome(
            outcome_id=str(UUID(bytes=outcome_id)),
            decision=self._read_decision(bytes(row[0])),
        )
        self._assert_record_digest("development-outcome", value, row[1])
        return value

    def _read_subject_state_outcome(
        self,
        outcome_id: bytes,
    ) -> SubjectStateDomainOutcome:
        row = self._writer.execute(
            """
            SELECT
                decision_id,
                subject_core_outcome_id,
                development_outcome_id,
                outcome_digest
            FROM subject_state_domain_outcome
            WHERE outcome_id = ?
            """,
            (outcome_id,),
        ).fetchone()
        if row is None:
            raise PublicationFailedClosed(
                "canonical-publication-incomplete",
                "SubjectStateDomainOutcome is absent",
            )
        value = SubjectStateDomainOutcome(
            outcome_id=str(UUID(bytes=outcome_id)),
            decision=self._read_decision(bytes(row[0])),
            subject_core=self._read_subject_core(bytes(row[1])),
            development=self._read_development(bytes(row[2])),
        )
        self._assert_record_digest(
            "subject-state-domain-outcome",
            value,
            row[3],
        )
        return value

    def _read_agency_outcome(
        self,
        outcome_id: bytes,
    ) -> AgencyDomainOutcome:
        row = self._writer.execute(
            """
            SELECT
                decision_id,
                committed_effect_eligible,
                outcome_digest
            FROM agency_domain_outcome
            WHERE outcome_id = ?
            """,
            (outcome_id,),
        ).fetchone()
        if row is None:
            raise PublicationFailedClosed(
                "canonical-publication-incomplete",
                "AgencyDomainOutcome is absent",
            )
        value = AgencyDomainOutcome(
            outcome_id=str(UUID(bytes=outcome_id)),
            decision=self._read_decision(bytes(row[0])),
            committed_effect_eligible=bool(row[1]),
        )
        self._assert_record_digest(
            "agency-domain-outcome",
            value,
            row[2],
        )
        return value

    def _read_relationship_outcome(
        self,
        outcome_id: bytes,
    ) -> RelationshipDomainOutcome:
        row = self._writer.execute(
            """
            SELECT
                decision_id,
                relationship_target_id,
                outcome_digest
            FROM relationship_domain_outcome
            WHERE outcome_id = ?
            """,
            (outcome_id,),
        ).fetchone()
        if row is None:
            raise PublicationFailedClosed(
                "canonical-publication-incomplete",
                "RelationshipDomainOutcome is absent",
            )
        value = RelationshipDomainOutcome(
            outcome_id=str(UUID(bytes=outcome_id)),
            decision=self._read_decision(bytes(row[0])),
            relationship_target_id=str(row[1]),
        )
        self._assert_record_digest(
            "relationship-domain-outcome",
            value,
            row[2],
        )
        return value

    def _read_revision_set(self, set_id: bytes) -> RevisionSet:
        row = self._writer.execute(
            """
            SELECT revision_count, revision_ids_json, set_digest
            FROM revision_set
            WHERE revision_set_id = ?
            """,
            (set_id,),
        ).fetchone()
        if row is None or int(row[0]) != 0:
            raise PublicationFailedClosed(
                "canonical-publication-incomplete",
                "explicit empty RevisionSet is absent",
            )
        value = RevisionSet(
            revision_set_id=str(UUID(bytes=set_id)),
            revision_ids=tuple(json.loads(str(row[1]))),
        )
        self._assert_record_digest("revision-set", value, row[2])
        return value

    def _read_expression(self, expression_id: bytes) -> Expression:
        row = self._writer.execute(
            """
            SELECT
                expression_text,
                language,
                grounding_decision_ids_json,
                expression_digest
            FROM expression_record
            WHERE expression_id = ?
            """,
            (expression_id,),
        ).fetchone()
        if row is None:
            raise PublicationFailedClosed(
                "canonical-publication-incomplete",
                "Expression record is absent",
            )
        value = Expression(
            expression_id=str(UUID(bytes=expression_id)),
            text=str(row[0]),
            language=str(row[1]),
            grounding_decision_ids=tuple(json.loads(str(row[2]))),
        )
        self._assert_record_digest("expression", value, row[3])
        return value

    def _read_effect_set(self, set_id: bytes) -> CommittedEffectSet:
        row = self._writer.execute(
            """
            SELECT
                effect_count,
                reference_ids_json,
                dispatch_state,
                reason,
                set_digest
            FROM committed_effect_set
            WHERE effect_set_id = ?
            """,
            (set_id,),
        ).fetchone()
        if row is None or int(row[0]) not in (0,1):
            raise PublicationFailedClosed(
                "canonical-publication-incomplete",
                "explicit empty CommittedEffectSet is absent",
            )
        value = CommittedEffectSet(
            effect_set_id=str(UUID(bytes=set_id)),
            reference_ids=tuple(json.loads(str(row[1]))),
            dispatch_state=EffectDispatchState(str(row[2])),
            reason=str(row[3]),
        )
        if len(value.reference_ids)!=int(row[0]) or (value.reference_ids and 'confirmed-text-save-v1' not in self._authority.allowed_intents):
            raise PublicationFailedClosed('effect-reference-invalid','effect references differ from authority')
        self._assert_record_digest("committed-effect-set", value, row[4])
        return value

    def has_frozen_attempt(self, operation_ref):
        snapshot = self.query(operation_ref)
        row = self._writer.execute('SELECT attempt_id FROM attempt_cycle_basis WHERE operation_id=?',
            (UUID(operation_ref.operation_id).bytes,)).fetchone()
        if row is not None and bytes(row[0]) != UUID(snapshot.attempt_id).bytes:
            raise PublicationFailedClosed('attempt-basis-mismatch', 'frozen attempt differs from Admission')
        return row is not None

    def freeze_attempt_basis(
        self,
        operation_ref: OperationRef,
    ) -> TimelineBasis:
        """Freeze one attempt's first observed canonical Timeline basis."""

        self._require_open()
        snapshot = self.query(operation_ref)
        operation_id = _publication_uuid_bytes(
            operation_ref.operation_id,
            "operation_id",
        )
        attempt_id = _publication_uuid_bytes(
            snapshot.attempt_id,
            "attempt_id",
        )
        try:
            _begin(self._writer)
            row = self._writer.execute(
                """
                SELECT
                    attempt_id,
                    head_sequence,
                    published_outcome_digest,
                    verified_prefix_digest,
                    revision_head_digest
                FROM attempt_cycle_basis
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
            if row is None:
                basis = _read_timeline_basis(self._writer)
                self._writer.execute(
                    """
                    INSERT INTO attempt_cycle_basis (
                        operation_id,
                        attempt_id,
                        head_sequence,
                        published_outcome_digest,
                        verified_prefix_digest,
                        revision_head_digest,
                        frozen_at_us
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        operation_id,
                        attempt_id,
                        basis.head_sequence,
                        _publication_digest_bytes(
                            basis.published_outcome_digest,
                            "published_outcome_digest",
                        ),
                        _publication_digest_bytes(
                            basis.verified_prefix_digest,
                            "verified_prefix_digest",
                        ),
                        _publication_digest_bytes(
                            basis.revision_head_digest,
                            "revision_head_digest",
                        ),
                        _utc_microseconds(),
                    ),
                )
                _commit(self._writer)
                return basis
            if bytes(row[0]) != attempt_id:
                raise PublicationFailedClosed(
                    "attempt-cycle-basis-lineage-invalid",
                    "frozen cycle basis does not match the canonical attempt",
                )
            basis = TimelineBasis(
                head_sequence=int(row[1]),
                published_outcome_digest=(
                    None if row[2] is None else bytes(row[2]).hex()
                ),
                verified_prefix_digest=bytes(row[3]).hex(),
                revision_head_digest=bytes(row[4]).hex(),
            )
            _commit(self._writer)
            return basis
        except PublicationProblem:
            _rollback_if_needed(self._writer)
            raise
        except sqlite3.Error as error:
            _rollback_if_needed(self._writer)
            raise PublicationInterrupted(
                "attempt-cycle-basis-interrupted",
                "the frozen attempt basis could not be proven",
            ) from error

    def fail_operation(
        self,
        operation_ref: OperationRef,
        *,
        stage: str,
        code: str,
        detail: str,
    ) -> OperationFailure:
        """Atomically record one pre-Publication failed-closed terminal fact."""

        self._require_open()
        snapshot = self.query(operation_ref)
        values = {
            "stage": (stage, 64),
            "code": (code, 64),
            "detail": (detail, 512),
        }
        for field, (value, maximum) in values.items():
            if (
                not isinstance(value, str)
                or not value
                or len(value) > maximum
                or value
                != unicodedata.normalize(
                    "NFC",
                    value.replace("\r\n", "\n").replace("\r", "\n"),
                )
                or "\x00" in value
            ):
                raise PublicationFailedClosed(
                    "operation-failure-invalid",
                    f"{field} is not bounded canonical text",
                )
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", stage) or not re.fullmatch(
            r"[a-z][a-z0-9-]{0,63}",
            code,
        ):
            raise PublicationFailedClosed(
                "operation-failure-invalid",
                "failure stage and code must be stable lowercase identifiers",
            )

        if snapshot.operation_state is OperationState.FAILED_CLOSED:
            existing_failure = self.query_failure(operation_ref)
            if (
                existing_failure.stage,
                existing_failure.code,
                existing_failure.detail,
            ) != (stage, code, detail):
                raise PublicationFailedClosed(
                    "operation-failure-conflict",
                    "Operation already has a different terminal failure fact",
                )
            return existing_failure
        if snapshot.operation_state is not OperationState.ADMITTED_PENDING:
            raise PublicationFailedClosed(
                "operation-already-terminal",
                "only an admitted pending Operation can fail before Publication",
            )

        operation_id = _publication_uuid_bytes(
            operation_ref.operation_id,
            "operation_id",
        )
        attempt_id = _publication_uuid_bytes(
            snapshot.attempt_id,
            "attempt_id",
        )
        recorded_at = _utc_microseconds()
        try:
            _begin(self._writer)
            existing = self._writer.execute(
                """
                SELECT
                    attempt_id,
                    failure_stage,
                    failure_code,
                    failure_detail
                FROM operation_failure
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
            if existing is not None:
                normalized = (
                    bytes(existing[0]),
                    str(existing[1]),
                    str(existing[2]),
                    str(existing[3]),
                )
                if normalized != (attempt_id, stage, code, detail):
                    raise PublicationFailedClosed(
                        "operation-failure-conflict",
                        "Operation already has a different terminal failure fact",
                    )
                _commit(self._writer)
                return self.query_failure(operation_ref)

            admitted = self._admitted_for_operation(
                self._writer,
                operation_id,
                replayed=True,
            )
            if (
                admitted.operation_ref != operation_ref
                or admitted.attempt_id != snapshot.attempt_id
            ):
                raise PublicationFailedClosed(
                    "operation-failure-lineage-invalid",
                    "failure fact does not match canonical Admission",
                )
            claimed = self._writer.execute(
                """
                SELECT 1
                FROM commit_plan_identity_claim
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
            publication = self._writer.execute(
                """
                SELECT 1
                FROM operation_publication_state
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
            if claimed is not None or publication is not None:
                raise PublicationFailedClosed(
                    "operation-publication-already-started",
                    "a claimed or terminal Publication cannot become a cycle failure",
                )
            self._writer.execute(
                """
                INSERT INTO operation_failure (
                    operation_id,
                    attempt_id,
                    failure_stage,
                    failure_code,
                    failure_detail,
                    recorded_at_us
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    operation_id,
                    attempt_id,
                    stage,
                    code,
                    detail,
                    recorded_at,
                ),
            )
            self._writer.execute(
                """
                INSERT INTO cycle_failure_transition (
                    operation_id,
                    transition_ordinal,
                    from_state,
                    to_state,
                    recorded_at_us
                ) VALUES (?, 2, 'admitted-pending', 'failed-closed', ?)
                """,
                (operation_id, recorded_at),
            )
            _commit(self._writer)
        except PublicationProblem:
            _rollback_if_needed(self._writer)
            raise
        except sqlite3.Error as error:
            _rollback_if_needed(self._writer)
            raise PublicationInterrupted(
                "operation-failure-commit-interrupted",
                "canonical failure commit outcome could not be proven",
            ) from error
        return self.query_failure(operation_ref)

    def query_failure(self, operation_ref: OperationRef) -> OperationFailure:
        snapshot = self.query(operation_ref)
        if snapshot.operation_state is not OperationState.FAILED_CLOSED:
            raise PublicationInterrupted(
                "operation-failure-unavailable",
                "Operation has no canonical failed-closed fact",
            )
        try:
            operation_id = UUID(operation_ref.operation_id).bytes
            row = self._writer.execute(
                """
                SELECT
                    attempt_id,
                    failure_stage,
                    failure_code,
                    failure_detail,
                    recorded_at_us
                FROM operation_failure
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise PublicationFailedClosed(
                "operation-failure-unreadable",
                "canonical operation failure could not be read",
            ) from error
        if row is None or str(UUID(bytes=bytes(row[0]))) != snapshot.attempt_id:
            raise PublicationFailedClosed(
                "operation-failure-incomplete",
                "failed Operation has no matching canonical failure fact",
            )
        return OperationFailure(
            operation_ref=operation_ref,
            attempt_id=snapshot.attempt_id,
            stage=str(row[1]),
            code=str(row[2]),
            detail=str(row[3]),
            recorded_at_us=int(row[4]),
        )

    def query(self, operation_ref: OperationRef) -> AdmissionSnapshot:
        self._require_open()
        if not isinstance(operation_ref, OperationRef):
            raise AdmissionFailedClosed(
                "operation-ref-invalid",
                "query requires an OperationRef",
            )
        if (
            operation_ref.contract_version != CONTRACT_VERSION
            or operation_ref.root_id != self._location.root_id
            or operation_ref.timeline_store_id != self._location.timeline_store_id
            or operation_ref.authority_scope_id != self._authority.authority_scope_id
        ):
            raise AdmissionFailedClosed(
                "operation-ref-authority-mismatch",
                "OperationRef does not belong to this canonical authority",
            )
        try:
            operation_id = UUID(operation_ref.operation_id).bytes
        except (AttributeError, TypeError, ValueError) as error:
            raise AdmissionFailedClosed(
                "operation-ref-invalid",
                "OperationRef contains an invalid operation identity",
            ) from error
        admitted = self._admitted_for_operation(
            self._writer,
            operation_id,
            replayed=True,
        )
        if admitted.operation_ref != operation_ref:
            raise AdmissionFailedClosed(
                "operation-ref-content-mismatch",
                "OperationRef does not match canonical operation content",
            )
        try:
            event = self._writer.execute(
                """
                SELECT event.event_id, operation.admitted_at_us
                FROM subject_event AS event
                JOIN subject_operation AS operation
                  ON operation.operation_id = event.operation_id
                WHERE event.operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
            publication = self._writer.execute(
                """
                SELECT
                    attempt_id,
                    operation_state,
                    attempt_state,
                    outcome_id
                FROM operation_publication_state
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
            failure = self._writer.execute(
                """
                SELECT attempt_id
                FROM operation_failure
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
            basis = _read_timeline_basis(self._writer)
        except sqlite3.Error as error:
            raise AdmissionFailedClosed(
                "operation-follow-unreadable",
                "canonical operation follow state could not be read",
            ) from error
        if event is None:
            raise AdmissionFailedClosed(
                "operation-event-missing",
                "canonical SubjectEvent is absent",
            )
        admitted_at_us = int(event[1])
        if admitted_at_us <= 0:
            raise AdmissionFailedClosed(
                "operation-admission-time-invalid",
                "canonical Operation admission time is invalid",
            )
        operation_state = OperationState.ADMITTED_PENDING
        attempt_state = AttemptState.PENDING
        outcome_id: str | None = None
        if publication is not None and failure is not None:
            raise AdmissionFailedClosed(
                "operation-terminal-state-conflict",
                "Operation has both Publication and cycle-failure terminal facts",
            )
        if publication is not None:
            if str(UUID(bytes=bytes(publication[0]))) != admitted.attempt_id:
                raise AdmissionFailedClosed(
                    "operation-attempt-mismatch",
                    "Publication state does not match the admitted attempt",
                )
            try:
                operation_state = OperationState(str(publication[1]))
                attempt_state = AttemptState(str(publication[2]))
            except ValueError as error:
                raise AdmissionFailedClosed(
                    "operation-state-invalid",
                    "canonical Publication state is not recognized",
                ) from error
            if publication[3] is not None:
                outcome_id = str(UUID(bytes=bytes(publication[3])))
        elif failure is not None:
            if str(UUID(bytes=bytes(failure[0]))) != admitted.attempt_id:
                raise AdmissionFailedClosed(
                    "operation-attempt-mismatch",
                    "cycle failure does not match the admitted attempt",
                )
            operation_state = OperationState.FAILED_CLOSED
            attempt_state = AttemptState.FAILED_CLOSED
        return AdmissionSnapshot(
            operation_ref=admitted.operation_ref,
            operation_state=operation_state,
            attempt_id=admitted.attempt_id,
            attempt_state=attempt_state,
            subject_event_id=str(UUID(bytes=bytes(event[0]))),
            timeline_head_sequence=basis.head_sequence,
            timeline_basis=basis,
            admitted_at_us=admitted_at_us,
            timeline_outcome_id=outcome_id,
        )

    def list_living_memories(
        self,
        *,
        active_only: bool = False,
        limit: int = 20,
        through_sequence: int | None = None,
    ) -> tuple[LivingMemoryRecord, ...]:
        if not isinstance(active_only, bool):
            raise TypeError("active_only must be bool")
        if through_sequence is not None and (type(through_sequence) is not int or through_sequence < 0):
            raise ValueError('through_sequence must be a nonnegative head')
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("limit must be between 1 and 100")
        rows = self._writer.execute(
            """
            SELECT decision.decision_id
            FROM candidate_decision_record AS decision
            JOIN timeline_outcome AS outcome ON outcome.plan_id = decision.plan_id
            WHERE decision.scope = 'experience'
              AND (? IS NULL OR outcome.head_sequence <= ?)
            ORDER BY outcome.head_sequence ASC
            """, (through_sequence, through_sequence)
        ).fetchall()
        records: list[LivingMemoryRecord] = []
        positions: dict[str, int] = {}
        for row in rows:
            decision = self._read_decision(bytes(row[0]))
            try:
                reason = json.loads(decision.reason)
                memory = reason["living_memory"]
            except (KeyError, TypeError, json.JSONDecodeError):
                continue
            if memory.get("status") != LivingMemoryDecisionStatus.ACCEPTED.value:
                continue
            if memory.get('action') == 'forget':
                try:
                    if (set(memory) != {'status', 'action', 'target_memory_id', 'reason_code', 'source_user_message_id'}
                        or memory['reason_code'] != 'selected' or reason.get('code') != 'living-memory.forgotten'
                        or decision.rule_version != 'experience-1.0'):
                        raise ValueError('invalid withdrawal')
                    target = str(UUID(memory['target_memory_id']))
                    UUID(memory['source_user_message_id'])
                    position = positions[target]
                    if records[position].status != 'active':
                        raise ValueError('target is not active')
                except (KeyError, ValueError, TypeError, AttributeError):
                    raise PublicationFailedClosed('canonical-memory-withdrawal-invalid', 'withdrawal requires one active target') from None
                records[position] = replace(records[position], status='forgotten')
                continue
            try:
                raw_temporal_anchor = memory.get("temporal_anchor")
                temporal_anchor = (
                    None
                    if raw_temporal_anchor is None
                    else TemporalAnchor.from_dict(raw_temporal_anchor)
                )
                from dynamic_subject_agent.preference_clarification import valid_confirmation
                confirmation = memory.get('preference_confirmation')
                if confirmation is not None and (not valid_confirmation(confirmation) or confirmation['source_id'] != memory['source_user_message_id']):
                    raise ValueError('invalid preference confirmation')
                record = LivingMemoryRecord(
                    memory_id=str(UUID(str(memory["memory_id"]))),
                    content=str(memory["content"]),
                    source_user_message_id=str(
                        UUID(str(memory["source_user_message_id"]))
                    ),
                    status="active",
                    supersedes_memory_id=(
                        None
                        if memory.get("supersedes_memory_id") is None
                        else str(UUID(str(memory["supersedes_memory_id"])))
                    ),
                    memory_kind=str(memory.get("memory_kind", "durable")),
                    temporal_anchor=temporal_anchor,
                    preference_additive=confirmation is not None and confirmation['choice'] == 'supplement',
                    preference_confirmed=confirmation is not None,
                )
            except (KeyError, TypeError, ValueError):
                raise PublicationFailedClosed(
                    "canonical-living-memory-invalid",
                    "accepted Living Memory decision is malformed",
                )
            if record.supersedes_memory_id is not None:
                old_position = positions.get(record.supersedes_memory_id)
                if old_position is None or records[old_position].status != "active":
                    raise PublicationFailedClosed(
                        "canonical-living-memory-lineage-invalid",
                        "Living Memory supersession does not name an active record",
                    )
                records[old_position] = replace(
                    records[old_position],
                    status="superseded",
                )
            positions[record.memory_id] = len(records)
            records.append(record)
        selected = [
            record
            for record in reversed(records)
            if not active_only or record.status == "active"
        ]
        return tuple(selected[:limit])

    def list_participant_goal_commitments(
        self,
        *,
        active_only: bool = False,
        limit: int = 20,
    ) -> tuple[ParticipantGoalCommitmentRecord, ...]:
        if not isinstance(active_only, bool):
            raise TypeError("active_only must be bool")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("limit must be between 1 and 100")
        rows = self._writer.execute(
            """
            SELECT decision.decision_id, outcome.head_sequence
            FROM candidate_decision_record AS decision
            JOIN timeline_outcome AS outcome ON outcome.plan_id = decision.plan_id
            WHERE decision.scope = 'experience'
            ORDER BY outcome.head_sequence ASC
            """
        ).fetchall()
        records: list[ParticipantGoalCommitmentRecord] = []
        positions: dict[str, int] = {}
        for row in rows:
            decision = self._read_decision(bytes(row[0]))
            head_sequence = int(row[1])
            try:
                payload = json.loads(decision.reason)["participant_goal_commitment"]
            except (KeyError, TypeError, json.JSONDecodeError):
                continue
            if payload.get("status") != "accepted":
                continue
            try:
                action = str(payload["action"])
                source_id = str(UUID(str(payload["source_user_message_id"])))
                evidence_quote = str(payload["evidence_quote"])
                policy_id = str(payload["policy_id"])
                policy_version = int(payload["policy_version"])
                policy_hash = str(payload["policy_hash"])
                record_id = str(UUID(str(payload["record_id"])))
                target_id = (
                    None
                    if payload.get("target_record_id") is None
                    else str(UUID(str(payload["target_record_id"])))
                )
                raw_temporal_anchor = payload.get("temporal_anchor")
                temporal_anchor = (
                    None
                    if raw_temporal_anchor is None
                    else TemporalAnchor.from_dict(raw_temporal_anchor)
                )
            except (KeyError, TypeError, ValueError):
                raise PublicationFailedClosed(
                    "canonical-participant-goal-invalid",
                    "accepted participant goal decision is malformed",
                )
            if (
                policy_id != PARTICIPANT_GOAL_POLICY_ID
                or policy_version != PARTICIPANT_GOAL_POLICY_VERSION
                or policy_hash != PARTICIPANT_GOAL_POLICY_HASH
                or not evidence_quote
            ):
                raise PublicationFailedClosed(
                    "canonical-participant-goal-policy-invalid",
                    "participant goal policy identity or evidence is invalid",
                )
            if action in {"revise", "transition"}:
                target_position = positions.get(target_id or "")
                if (
                    target_position is None
                    or records[target_position].status != "active"
                ):
                    raise PublicationFailedClosed(
                        "canonical-participant-goal-lineage-invalid",
                        "participant goal change must name one active record",
                    )
            if action == "create":
                kind = str(payload["kind"])
                terms = str(payload["terms"])
                next_status = str(payload["next_status"])
                if (
                    target_id is not None
                    or kind not in {"goal", "commitment"}
                    or not terms
                    or next_status != "active"
                    or record_id in positions
                ):
                    raise PublicationFailedClosed(
                        "canonical-participant-goal-create-invalid",
                        "participant goal creation is invalid",
                    )
                record = ParticipantGoalCommitmentRecord(
                    record_id=record_id,
                    kind=kind,
                    terms=terms,
                    status="active",
                    source_user_message_id=source_id,
                    evidence_quote=evidence_quote,
                    created_head_sequence=head_sequence,
                    policy_id=policy_id,
                    policy_version=policy_version,
                    policy_hash=policy_hash,
                    temporal_anchor=temporal_anchor,
                )
                positions[record_id] = len(records)
                records.append(record)
            elif action == "revise":
                target_position = positions[target_id or ""]
                target = records[target_position]
                kind = str(payload["kind"])
                terms = str(payload["terms"])
                if (
                    record_id in positions
                    or kind != target.kind
                    or not terms
                    or payload.get("next_status") != "active"
                ):
                    raise PublicationFailedClosed(
                        "canonical-participant-goal-revision-invalid",
                        "participant goal revision is invalid",
                    )
                records[target_position] = replace(
                    target,
                    status="superseded",
                    status_changed_head_sequence=head_sequence,
                )
                record = ParticipantGoalCommitmentRecord(
                    record_id=record_id,
                    kind=kind,
                    terms=terms,
                    status="active",
                    source_user_message_id=source_id,
                    evidence_quote=evidence_quote,
                    created_head_sequence=head_sequence,
                    revision_of_record_id=target.record_id,
                    policy_id=policy_id,
                    policy_version=policy_version,
                    policy_hash=policy_hash,
                    temporal_anchor=temporal_anchor,
                )
                positions[record_id] = len(records)
                records.append(record)
            elif action == "transition":
                target_position = positions[target_id or ""]
                target = records[target_position]
                next_status = str(payload["next_status"])
                allowed = (
                    {"achieved", "abandoned"}
                    if target.kind == "goal"
                    else {"fulfilled", "released"}
                )
                if record_id != target.record_id or next_status not in allowed:
                    raise PublicationFailedClosed(
                        "canonical-participant-goal-transition-invalid",
                        "participant goal terminal transition is invalid",
                    )
                records[target_position] = replace(
                    target,
                    status=next_status,
                    status_changed_head_sequence=head_sequence,
                )
            else:
                raise PublicationFailedClosed(
                    "canonical-participant-goal-action-invalid",
                    "accepted participant goal action is not recognized",
                )
        selected = [
            record
            for record in reversed(records)
            if not active_only or record.status == "active"
        ]
        return tuple(selected[:limit])

    def list_situated_states(
        self,
        *,
        active_only: bool = False,
        limit: int = 20,
    ) -> tuple[SituatedStateRecord, ...]:
        if not isinstance(active_only, bool):
            raise TypeError("active_only must be bool")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("limit must be between 1 and 100")
        rows = self._writer.execute(
            """
            SELECT core.decision_id, outcome.head_sequence
            FROM subject_core_outcome AS core
            JOIN timeline_outcome AS outcome ON outcome.plan_id = core.plan_id
            ORDER BY outcome.head_sequence ASC
            """
        ).fetchall()
        records: list[SituatedStateRecord] = []
        positions: dict[str, int] = {}
        for row in rows:
            decision = self._read_decision(bytes(row[0]))
            head_sequence = int(row[1])
            try:
                payload = json.loads(decision.reason)["situated_state"]
            except (KeyError, TypeError, json.JSONDecodeError):
                continue
            action = payload.get("action")
            target_id = payload.get("target_state_id")
            if target_id is not None:
                try:
                    target_id = str(UUID(str(target_id)))
                except (TypeError, ValueError):
                    raise PublicationFailedClosed(
                        "canonical-situated-target-invalid",
                        "Situated target identity is malformed",
                    ) from None
            if action == "set" and payload.get("status") == "accepted":
                try:
                    state_id = str(UUID(str(payload["state_id"])))
                    source_id = str(UUID(str(payload["source_user_message_id"])))
                    posture = str(payload["posture"])
                    evidence = str(payload["evidence_quote"])
                    remaining = int(payload["remaining_turns"])
                    expires_at_us = int(payload["expires_at_us"])
                    policy_id = str(payload["policy_id"])
                    policy_version = int(payload["policy_version"])
                    policy_hash = str(payload["policy_hash"])
                except (KeyError, TypeError, ValueError):
                    raise PublicationFailedClosed(
                        "canonical-situated-set-invalid",
                        "Accepted Situated set is malformed",
                    ) from None
                if (
                    posture not in SITUATED_POSTURES
                    or not evidence
                    or remaining != 1
                    or expires_at_us <= 0
                    or policy_id != SITUATED_POLICY_ID
                    or policy_version != SITUATED_POLICY_VERSION
                    or policy_hash != SITUATED_POLICY_HASH
                    or state_id in positions
                ):
                    raise PublicationFailedClosed(
                        "canonical-situated-set-invalid",
                        "Accepted Situated set violates policy",
                    )
                if target_id is not None:
                    target_position = positions.get(target_id)
                    if (
                        target_position is None
                        or records[target_position].status != "active"
                    ):
                        raise PublicationFailedClosed(
                            "canonical-situated-replacement-invalid",
                            "Situated replacement must name the active record",
                        )
                    records[target_position] = replace(
                        records[target_position],
                        status="ended",
                        ended_head_sequence=head_sequence,
                        end_reason="replaced",
                    )
                elif any(record.status == "active" for record in records):
                    raise PublicationFailedClosed(
                        "canonical-situated-cardinality-invalid",
                        "Situated set would create a second active record",
                    )
                record = SituatedStateRecord(
                    state_id=state_id,
                    posture=posture,
                    source_user_message_id=source_id,
                    evidence_quote=evidence,
                    remaining_turns=remaining,
                    expires_at_us=expires_at_us,
                    created_head_sequence=head_sequence,
                    policy_id=policy_id,
                    policy_version=policy_version,
                    policy_hash=policy_hash,
                )
                positions[state_id] = len(records)
                records.append(record)
            elif action in {"carry", "consume"}:
                target_position = positions.get(target_id or "")
                if (
                    target_position is None
                    or records[target_position].status != "active"
                ):
                    raise PublicationFailedClosed(
                        "canonical-situated-consume-invalid",
                        "Situated carry/consume must name the active record",
                    )
                reason = "consumed" if action == "carry" else str(
                    payload.get("reason_code", "consumed")
                )
                records[target_position] = replace(
                    records[target_position],
                    remaining_turns=0,
                    status="ended",
                    ended_head_sequence=head_sequence,
                    end_reason=reason,
                )
            elif action == "noop":
                continue
            else:
                raise PublicationFailedClosed(
                    "canonical-situated-action-invalid",
                    "Situated action is not recognized",
                )
        selected = [
            record
            for record in reversed(records)
            if not active_only or record.status == "active"
        ]
        return tuple(selected[:limit])

    def current_medium_state(self) -> MediumStateRecord:
        rows = self._writer.execute(
            """
            SELECT core.decision_id, outcome.head_sequence
            FROM subject_core_outcome AS core
            JOIN timeline_outcome AS outcome ON outcome.plan_id = core.plan_id
            ORDER BY outcome.head_sequence ASC
            """
        ).fetchall()
        current = MediumStateRecord(None, "settled", 0, None)
        for row in rows:
            decision = self._read_decision(bytes(row[0]))
            try:
                payload = json.loads(decision.reason)["medium_state"]
            except (KeyError, TypeError, json.JSONDecodeError):
                continue
            if payload.get("action") != "transition" or payload.get("status") != "accepted":
                continue
            try:
                revision_id = str(UUID(str(payload["revision_id"])))
                before = str(payload["before_baseline"])
                after = str(payload["after_baseline"])
                base_version = int(payload["base_version"])
                resulting_version = int(payload["resulting_version"])
                entered = int(payload["entered_head_sequence"])
                policy_id = str(payload["policy_id"])
                policy_version = int(payload["policy_version"])
                policy_hash = str(payload["policy_hash"])
            except (KeyError, TypeError, ValueError):
                raise PublicationFailedClosed(
                    "canonical-medium-transition-invalid",
                    "Accepted Medium transition is malformed",
                ) from None
            if (
                before != current.baseline
                or base_version != current.version
                or after not in MEDIUM_BASELINES
                or resulting_version != base_version + 1
                or entered != int(row[1])
                or policy_id != MEDIUM_POLICY_ID
                or policy_version != MEDIUM_POLICY_VERSION
                or policy_hash != MEDIUM_POLICY_HASH
            ):
                raise PublicationFailedClosed(
                    "canonical-medium-lineage-invalid",
                    "Medium transition does not extend the current version",
                )
            current = MediumStateRecord(
                revision_id,
                after,
                resulting_version,
                entered,
                policy_id,
                policy_version,
                policy_hash,
            )
        return current

    def list_medium_signals(self, *, limit: int = 7) -> tuple[MediumSignalRecord, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        rows = self._writer.execute(
            """
            SELECT core.decision_id, outcome.head_sequence
            FROM subject_core_outcome AS core
            JOIN timeline_outcome AS outcome ON outcome.plan_id = core.plan_id
            ORDER BY outcome.head_sequence ASC
            """
        ).fetchall()
        signals: list[MediumSignalRecord] = []
        for row in rows:
            decision = self._read_decision(bytes(row[0]))
            try:
                payload = json.loads(decision.reason)["medium_state"]
            except (KeyError, TypeError, json.JSONDecodeError):
                continue
            if not payload.get("signal_eligible"):
                continue
            signal = payload.get("signal")
            evidence = payload.get("evidence_quote")
            if signal not in MEDIUM_SIGNALS or not isinstance(evidence, str) or not evidence:
                raise PublicationFailedClosed(
                    "canonical-medium-signal-invalid",
                    "Eligible Medium signal is malformed",
                )
            signals.append(MediumSignalRecord(int(row[1]), signal, evidence))
        return tuple(signals[-limit:])

    def list_relationship_interactions(
        self,
        *,
        limit: int = 20,
    ) -> tuple[RelationshipStanceInteraction, ...]:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("limit must be between 1 and 100")
        rows = self._writer.execute(
            """
            SELECT decision.decision_id, outcome.head_sequence
            FROM candidate_decision_record AS decision
            JOIN timeline_outcome AS outcome ON outcome.plan_id = decision.plan_id
            WHERE decision.scope = 'relationship'
            ORDER BY outcome.head_sequence ASC
            """
        ).fetchall()
        records: list[RelationshipStanceInteraction] = []
        for row in rows:
            decision = self._read_decision(bytes(row[0]))
            try:
                reason = json.loads(decision.reason)
                stance = reason["relationship"]
            except (KeyError, TypeError, json.JSONDecodeError):
                continue
            if stance.get("status") not in {"accepted", "rejected"}:
                continue
            try:
                records.append(
                    RelationshipStanceInteraction(
                        event=str(stance["event"]),
                        evidence_quote=str(stance.get("evidence_quote", "")),
                        source_user_message_id=str(
                            UUID(str(stance["source_user_message_id"]))
                        ),
                        policy_version=str(stance.get("policy_version", "")),
                        status=str(stance["status"]),
                        head_sequence=int(row[1]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                raise PublicationFailedClosed(
                    "canonical-relationship-invalid",
                    "relationship decision record is malformed",
                )
        return tuple(records[-limit:])

    def list_conversation_turns(
        self,
        *,
        limit: int = 20,
    ) -> tuple[ConversationTurnRecord, ...]:
        """Return recent completed user/expression pairs from canonical outcomes."""

        self._require_open()
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("limit must be between 1 and 100")
        if LIFE_SYSTEM_INTENT in self._authority.allowed_intents:
            turns = []
            for outcome, command, published_at in self._verified_publications():
                if type(command) is not SubjectCommand:
                    continue
                turns.append(ConversationTurnRecord(outcome.head_sequence, command.utterance,
                    command.language, outcome.expression.text, outcome.expression.language, published_at,
                    ConversationOutcomeSummary.from_outcome(outcome)))
            return tuple(turns[-limit:])
        rows = self._writer.execute(
            """
            SELECT
                outcome.head_sequence,
                outcome.published_at_us,
                outcome.operation_id,
                operation.contract_version,
                operation.operation_kind,
                hex(operation.payload_fingerprint)
            FROM timeline_outcome AS outcome
            JOIN subject_operation AS operation
              ON operation.operation_id = outcome.operation_id
            ORDER BY outcome.head_sequence ASC
            """
        ).fetchall()
        basis = _read_timeline_basis(self._writer)
        if len(rows) != basis.head_sequence:
            raise PublicationFailedClosed(
                "conversation-history-outcome-count-invalid",
                "recent TimelineOutcome suffix is incomplete",
            )
        expected_sequences = list(range(1, basis.head_sequence + 1))
        if [int(row[0]) for row in rows] != expected_sequences:
            raise PublicationFailedClosed(
                "conversation-history-head-invalid",
                "recent TimelineOutcome head sequence is incomplete",
            )
        records: list[ConversationTurnRecord] = []
        previous_outcome: TimelineOutcome | None = None
        for row in rows:
            operation_ref = OperationRef(
                contract_version=str(row[3]),
                root_id=self._location.root_id,
                timeline_store_id=self._location.timeline_store_id,
                authority_scope_id=self._authority.authority_scope_id,
                operation_id=str(UUID(bytes=bytes(row[2]))),
                operation_kind=OperationKind(str(row[4])),
                admitted_payload_fingerprint=str(row[5]).casefold(),
            )
            outcome = self.query_outcome(operation_ref)
            command = self._query_command(operation_ref)
            if outcome.head_sequence != int(row[0]):
                raise PublicationFailedClosed(
                    "conversation-history-outcome-invalid",
                    "canonical history outcome does not match its suffix position",
                )
            if (
                previous_outcome is not None
                and outcome.previous_outcome_digest
                != previous_outcome.outcome_digest
            ):
                raise PublicationFailedClosed(
                    "conversation-history-chain-invalid",
                    "canonical history outcome digest chain is broken",
                )
            published_at_us = int(row[1])
            if published_at_us < 1:
                raise PublicationFailedClosed(
                    "conversation-history-time-invalid",
                    "canonical history publication time is invalid",
                )
            records.append(
                ConversationTurnRecord(
                    head_sequence=int(row[0]),
                    user_text=('主体任务操作' if command.declared_intent in ('subject-task-v1','confirmed-text-save-v1') else command.utterance),
                    user_language=command.language,
                    assistant_text=outcome.expression.text,
                    assistant_language=outcome.expression.language,
                    published_at_us=published_at_us,
                    outcome_summary=(None if command.declared_intent in ('subject-task-v1','confirmed-text-save-v1') else ConversationOutcomeSummary.from_outcome(outcome)),
                )
            )
            previous_outcome = outcome
        if records and (
            previous_outcome is None
            or previous_outcome.head_sequence != basis.head_sequence
            or previous_outcome.outcome_digest != basis.published_outcome_digest
        ):
            raise PublicationFailedClosed(
                "conversation-history-head-digest-invalid",
                "canonical history suffix does not end at the Timeline head",
            )
        if not records and (
            basis.head_sequence != 0 or basis.published_outcome_digest is not None
        ):
            raise PublicationFailedClosed(
                "conversation-history-empty-head-invalid",
                "empty canonical history does not match the Timeline head",
            )
        return tuple(records[-limit:])

    def list_subject_tasks(self):
        return self._verified_subject_tasks()[0]

    def preview_text_artifact(self, task_id, revision):
        from dynamic_subject_agent.text_artifacts import make_preview
        if 'confirmed-text-save-v1' not in self._authority.allowed_intents:
            return None
        record=next((r for r in self.list_subject_tasks() if r.task_id==task_id and r.revision==revision),None)
        return make_preview(record,root_id=self._location.root_id,profile_id=self._authority.profile_id,
            timeline_id=self._authority.timeline_id,directory=self._location.root/'artifacts') if record else None

    def _effect_receipts(self):
        from dynamic_subject_agent.text_artifacts import FILE_RESULTS
        if 'confirmed-text-save-v1' not in self._authority.allowed_intents:
            return ()
        try:
            rows=self._writer.execute('SELECT ordinal,effect_id,outcome_id,head_sequence,receipt_json,previous_digest,receipt_digest FROM effect_receipt ORDER BY ordinal').fetchall()
            previous=_EMPTY_EFFECT_HEAD; receipts=[]; last_sequence=0
            for ordinal,row in enumerate(rows,1):
                value=json.loads(row[4])
                if (set(value)!={'effect_id','outcome_id','outcome_digest','head_sequence','result','content_digest','filename','ordinal','previous_digest'}
                    or value['result'] not in FILE_RESULTS or type(value['head_sequence']) is not int
                    or value['ordinal']!=ordinal or row[0]!=ordinal or value['effect_id']!=row[1]
                    or value['outcome_id']!=str(UUID(bytes=bytes(row[2]))) or value['head_sequence']!=row[3]
                    or row[3]<=last_sequence or value['previous_digest']!=previous or row[5]!=previous):
                    raise ValueError('invalid effect receipt lineage')
                digest=hashlib.sha256(_canonical_json(value).encode()).hexdigest()
                if row[6]!=digest:
                    raise ValueError('invalid effect receipt digest')
                previous=digest;last_sequence=row[3];receipts.append(value)
            if self._writer.execute('SELECT receipt_count,receipt_digest FROM effect_receipt_head WHERE singleton=1').fetchone()!=(len(rows),previous):
                raise ValueError('effect receipt head differs from records')
            return tuple(receipts)
        except (sqlite3.Error,ValueError,TypeError,KeyError):
            raise PublicationFailedClosed('effect-receipts-invalid','canonical effect receipts could not be verified') from None

    def _verified_subject_tasks(self):
        from dataclasses import asdict
        from dynamic_subject_agent.subject_tasks import TASK_INTENT, SubjectTaskCommand, SubjectTaskProposal, decide, validate_task_reason
        from dynamic_subject_agent.text_artifacts import TEXT_EFFECT_INTENT, TextSaveApproval, make_preview, approve, effect_from_reason
        # Verify the complete canonical chain, including non-task publications.
        self.list_conversation_turns(limit=1)
        receipts={r['head_sequence']:r for r in self._effect_receipts()}
        rows = self._writer.execute('''SELECT op.operation_id,op.contract_version,op.operation_kind,
            hex(op.payload_fingerprint),d.decision_id,o.head_sequence,o.outcome_id,o.outcome_digest FROM timeline_outcome AS o
            JOIN subject_operation AS op ON op.operation_id=o.operation_id
            JOIN candidate_decision_record AS d ON d.plan_id=o.plan_id AND d.scope='agency'
            ORDER BY o.head_sequence''').fetchall()
        records = {};pending=[]
        for row in rows:
            ref = OperationRef(str(row[1]),self._location.root_id,self._location.timeline_store_id,
                self._authority.authority_scope_id,str(UUID(bytes=bytes(row[0]))),OperationKind(str(row[2])),str(row[3]).lower())
            command = self._query_command(ref)
            decision = self._read_decision(bytes(row[4]))
            if decision.rule_version=='agency-text-effect-1.0':
                try:
                    if command.declared_intent!=TEXT_EFFECT_INTENT:
                        raise ValueError('effect without explicit approval')
                    reason=json.loads(decision.reason);effect=effect_from_reason(decision)
                    source=TextSaveApproval.from_json(command.utterance)
                    old=records.get(source.task_id)
                    preview=make_preview(old,root_id=self._location.root_id,profile_id=self._authority.profile_id,
                        timeline_id=self._authority.timeline_id,directory=self._location.root/'artifacts') if old and old.revision==source.revision else None
                    record,expected,reply=approve(source,tuple(records.values()),preview)
                    if effect!=expected or reason['subject_task']!=(asdict(record) if record else None) or reason['reply']!=reply or reason['approval']!=asdict(source):
                        raise ValueError('effect differs from canonical approval')
                    if record:
                        records[record.task_id]=record
                    receipt=receipts.pop(row[5],None)
                    if effect:
                        if receipt:
                            expected_receipt={'effect_id':effect.effect_id,'outcome_id':str(UUID(bytes=bytes(row[6]))),
                                'outcome_digest':bytes(row[7]).hex(),'head_sequence':row[5],
                                'content_digest':effect.content_digest,'filename':effect.filename}
                            if any(receipt[k]!=v for k,v in expected_receipt.items()):
                                raise ValueError('effect receipt does not match intent')
                            records[record.task_id]=replace(record,status='completed' if receipt['result']=='created' else 'failed',
                                revision=record.revision+1,reason='saved' if receipt['result']=='created' else 'file_failed')
                        elif row[5]!=len(rows):
                            raise ValueError('publication follows unresolved effect')
                        else:
                            pending.append((effect,ref))
                    elif receipt:
                        raise ValueError('receipt without effect')
                except (ValueError,TypeError,KeyError,AttributeError):
                    raise PublicationFailedClosed('text-effect-history-invalid','text effect could not be replayed') from None
                continue
            if decision.rule_version != 'agency-task-1.0':
                if command.declared_intent in (TASK_INTENT,TEXT_EFFECT_INTENT):
                    raise PublicationFailedClosed('task-history-invalid','task result has no task adjudication')
                continue
            try:
                if command.declared_intent != TASK_INTENT:
                    raise ValueError('task result without explicit task request')
                reason = json.loads(decision.reason)
                validate_task_reason(reason)
                source = SubjectTaskCommand.from_json(command.utterance)
                proposal = SubjectTaskProposal(**reason['proposal']) if reason['proposal'] else None
                record, reply = decide(source,proposal,tuple(records.values()),new_id=ref.operation_id)
                if reason['subject_task'] != (asdict(record) if record else None) or reason['reply'] != reply:
                    raise ValueError('task transition does not match canonical source')
                if record:
                    records[record.task_id] = record
            except (ValueError, TypeError, KeyError, AttributeError):
                raise PublicationFailedClosed('task-history-invalid','task transition could not be verified') from None
        if receipts:
            raise PublicationFailedClosed('orphan-effect-receipt','effect receipt has no matching intent')
        return tuple(records.values()),tuple(pending)

    def _pending_text_effects(self):
        return self._verified_subject_tasks()[1]

    def _append_effect_receipt(self, preview, operation_ref, result):
        from dynamic_subject_agent.text_artifacts import FILE_RESULTS
        if result not in FILE_RESULTS or (preview,operation_ref) not in self._pending_text_effects():
            raise PublicationFailedClosed('effect-receipt-source-invalid','receipt requires a verified pending effect')
        outcome=self.query_outcome(operation_ref)
        previous_rows=self._effect_receipts()
        previous=self._writer.execute('SELECT receipt_digest FROM effect_receipt_head WHERE singleton=1').fetchone()[0]
        value={'effect_id':preview.effect_id,'outcome_id':outcome.outcome_id,'outcome_digest':outcome.outcome_digest,
            'head_sequence':outcome.head_sequence,'result':result,'content_digest':preview.content_digest,
            'filename':preview.filename,'ordinal':len(previous_rows)+1,'previous_digest':previous}
        encoded=_canonical_json(value);digest=hashlib.sha256(encoded.encode()).hexdigest()
        try:
            _begin(self._writer)
            if self._writer.execute('SELECT receipt_count,receipt_digest FROM effect_receipt_head WHERE singleton=1').fetchone()!=(len(previous_rows),previous):
                raise PublicationFailedClosed('effect-receipt-conflict','receipt head changed')
            self._writer.execute('INSERT INTO effect_receipt VALUES (?,?,?,?,?,?,?)',(value['ordinal'],preview.effect_id,
                UUID(outcome.outcome_id).bytes,outcome.head_sequence,encoded,previous,digest))
            self._writer.execute('UPDATE effect_receipt_head SET receipt_count=?,receipt_digest=? WHERE singleton=1',(value['ordinal'],digest))
            _commit(self._writer)
        except Exception:
            _rollback_if_needed(self._writer)
            raise

    def withheld_memory_ids_before(self, operation_ref: OperationRef, *, expected_head: int) -> tuple[str, ...]:
        """Unpublished withdrawal intent restricts disclosure, never fakes state.

        Resolve at that operation's frozen prefix, not against a later renamed
        record. A subsequent local withdrawal can still use authoritative state.
        """
        from dynamic_subject_agent.memory_control import select_memory_withdrawal
        self.recent_dialogue_before(operation_ref, expected_head=expected_head)
        current = self.list_living_memories(limit=100)
        blocked: set[str] = set()
        rows = self._writer.execute('''SELECT op.operation_id, op.contract_version, op.operation_kind,
            hex(op.payload_fingerprint), basis.head_sequence FROM subject_operation op
            LEFT JOIN attempt_cycle_basis basis ON basis.operation_id=op.operation_id
            WHERE op.operation_id != ? AND NOT EXISTS (
                SELECT 1 FROM timeline_outcome outcome WHERE outcome.operation_id=op.operation_id)
        ''', (UUID(operation_ref.operation_id).bytes,)).fetchall()
        for row in rows:
            ref = OperationRef(str(row[1]), self._location.root_id, self._location.timeline_store_id,
                self._authority.authority_scope_id, str(UUID(bytes=bytes(row[0]))),
                OperationKind(str(row[2])), str(row[3]).casefold())
            command = self._query_command(ref)
            if type(command) is FirstLifeInput:
                continue
            message = command.utterance
            prior = self.list_living_memories(limit=100, through_sequence=int(row[4])) if row[4] is not None else current
            selection = select_memory_withdrawal(message, tuple(m for m in prior if m.status == 'active'))
            if selection is None or not selection.restricts_disclosure:
                continue
            if row[4] is None or len(prior) == 100 or len(current) == 100 or selection.target_memory_id is None:
                return tuple(m.memory_id for m in current if m.status == 'active')
            blocked.add(selection.target_memory_id)
        for _ in current:
            descendants = {m.memory_id for m in current if m.supersedes_memory_id in blocked}
            if descendants <= blocked:
                break
            blocked.update(descendants)
        return tuple(sorted(m.memory_id for m in current if m.status == 'active' and m.memory_id in blocked))

    def character_dialogue_before(self, operation_ref, *, expected_head, enabled):
        from dynamic_subject_agent.reviewed_character_chat import CharacterDialogueBasis
        from dynamic_subject_agent.recent_dialogue import select_recent_dialogue, is_dialogue_control
        if type(enabled) is not bool:
            raise PublicationFailedClosed("character-history-policy-invalid", "history preference must be explicit")
        if enabled:
            verified = self._verified_dialogue_prefix(operation_ref, expected_head=expected_head)
            if verified is None:
                return CharacterDialogueBasis("unavailable", problem_code="character-history-unresolved")
            records, cutoff = verified
            if is_dialogue_control(self._query_command(operation_ref).utterance):
                return CharacterDialogueBasis("restricted", bool(records), problem_code="character-history-restricted")
            selected = select_recent_dialogue(records, after_sequence=cutoff)
            if records and is_dialogue_control(records[-1].user_text):
                return CharacterDialogueBasis("restricted", True, problem_code="character-history-restricted")
            return CharacterDialogueBasis("available", bool(records), selected)
        # Closing disclosure still verifies the canonical basis and foreground;
        # it never substitutes an unverified empty history for a failed read.
        snapshot = self.query(operation_ref)
        if snapshot.timeline_basis is None or snapshot.timeline_basis.head_sequence != expected_head:
            raise PublicationFailedClosed("character-history-basis-invalid", "character foreground must match frozen Admission")
        records = self.list_conversation_turns(limit=2)
        if LIFE_SYSTEM_INTENT not in self._authority.allowed_intents and (records[-1].head_sequence if records else 0) != expected_head:
            raise PublicationFailedClosed("character-history-head-invalid", "character foreground is not current")
        return CharacterDialogueBasis("available", bool(records))

    def recent_dialogue_before(self, operation_ref: OperationRef, *, expected_head: int):
        """Read only the same identity's verified frozen prefix for this reply."""
        from dynamic_subject_agent.recent_dialogue import select_recent_dialogue
        verified = self._verified_dialogue_prefix(operation_ref, expected_head=expected_head)
        if verified is None:
            return ()
        records, cutoff = verified
        return select_recent_dialogue(records, after_sequence=cutoff)

    def _verified_dialogue_prefix(self, operation_ref: OperationRef, *, expected_head: int):
        from dynamic_subject_agent.recent_dialogue import is_dialogue_control

        snapshot = self.query(operation_ref)
        frozen_row = self._writer.execute('''SELECT attempt_id, head_sequence, published_outcome_digest,
            verified_prefix_digest, revision_head_digest FROM attempt_cycle_basis WHERE operation_id=?''',
            (UUID(operation_ref.operation_id).bytes,)).fetchone()
        if frozen_row is None or bytes(frozen_row[0]) != UUID(snapshot.attempt_id).bytes:
            raise PublicationFailedClosed('dialogue-attempt-unverified', 'dialogue requires the current frozen attempt')
        frozen = TimelineBasis(int(frozen_row[1]), None if frozen_row[2] is None else bytes(frozen_row[2]).hex(),
            bytes(frozen_row[3]).hex(), bytes(frozen_row[4]).hex())
        if (isinstance(expected_head, bool) or not isinstance(expected_head, int)
            or frozen.head_sequence != expected_head or frozen != snapshot.timeline_basis):
            raise PublicationFailedClosed('dialogue-basis-mismatch', 'dialogue does not match the frozen turn basis')
        records = self.list_conversation_turns(limit=2)
        if LIFE_SYSTEM_INTENT not in self._authority.allowed_intents and (records[-1].head_sequence if records else 0) != expected_head:
            raise PublicationFailedClosed('dialogue-head-mismatch', 'dialogue does not end at the frozen head')
        cutoff = 0
        unpublished = self._writer.execute('''
            SELECT op.operation_id, op.contract_version, op.operation_kind,
                   hex(op.payload_fingerprint), basis.head_sequence, failure.operation_id
            FROM subject_operation op
            LEFT JOIN attempt_cycle_basis basis ON basis.operation_id=op.operation_id
            LEFT JOIN operation_failure failure ON failure.operation_id=op.operation_id
            WHERE op.operation_id != ? AND NOT EXISTS (
                SELECT 1 FROM timeline_outcome outcome WHERE outcome.operation_id=op.operation_id)
        ''', (UUID(operation_ref.operation_id).bytes,)).fetchall()
        for row in unpublished:
            previous_ref = OperationRef(str(row[1]), self._location.root_id,
                self._location.timeline_store_id, self._authority.authority_scope_id,
                str(UUID(bytes=bytes(row[0]))), OperationKind(str(row[2])), str(row[3]).casefold())
            previous_command = self._query_command(previous_ref)
            if type(previous_command) is FirstLifeInput:
                continue
            # Pending/interrupted or unfrozen admissions have unresolved intent.
            if row[4] is None or row[5] is None:
                return None
            if is_dialogue_control(previous_command.utterance):
                return None
            cutoff = max(cutoff, int(row[4]))
        return records, cutoff

    def preference_question_before(self, operation_ref: OperationRef, *, expected_head: int):
        from dynamic_subject_agent.preference_clarification import PendingPreference
        from dynamic_subject_agent.recent_dialogue import is_dialogue_control
        # Reuse frozen-prefix, integrity, pending-admission and control checks.
        verified = self._verified_dialogue_prefix(operation_ref, expected_head=expected_head)
        if verified is None:
            return None
        turns, cutoff = verified
        if not turns or turns[-1].outcome_summary is None:
            return None
        turn = turns[-1]
        if turn.head_sequence <= cutoff or is_dialogue_control(turn.user_text) or turn.outcome_summary.memory_revision is not False or turn.outcome_summary.living_memory_status != 'no-op':
            return None
        question = turn.outcome_summary.preference_question
        if question is None or question.source_text != turn.user_text or question.prompt not in turn.assistant_text:
            return None
        snapshot = self.query(operation_ref)
        return PendingPreference(question, snapshot.timeline_basis.verified_prefix_digest)

    def query_outcome(self, operation_ref: OperationRef) -> TimelineOutcome:
        snapshot = self.query(operation_ref)
        if snapshot.operation_state is not OperationState.COMPLETED:
            raise PublicationInterrupted(
                "timeline-outcome-unavailable",
                "Operation has no committed TimelineOutcome",
            )
        try:
            operation_id = UUID(operation_ref.operation_id).bytes
            row = self._writer.execute(
                """
                SELECT
                    outcome_id,
                    attempt_id,
                    subject_event_id,
                    plan_id,
                    head_sequence,
                    previous_outcome_digest,
                    outcome_digest,
                    experience_id,
                    epistemic_outcome_id,
                    experience_outcome_id,
                    subject_state_outcome_id,
                    agency_outcome_id,
                    relationship_outcome_id,
                    revision_set_id,
                    expression_id,
                    effect_set_id
                FROM timeline_outcome
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
            if row is None:
                raise PublicationFailedClosed(
                    "canonical-publication-incomplete",
                    "completed Operation has no TimelineOutcome",
                )
            outcome_id = bytes(row[0])
            if snapshot.timeline_outcome_id != str(UUID(bytes=outcome_id)):
                raise PublicationFailedClosed(
                    "canonical-publication-integrity-mismatch",
                    "follow state and TimelineOutcome identity disagree",
                )

            plan_id = bytes(row[3])
            receipt = self._writer.execute(
                """
                SELECT
                    plan_digest,
                    cycle_plan_id,
                    attempt_id,
                    subject_event_id,
                    profile_id,
                    timeline_id,
                    expected_head_sequence,
                    expected_head_outcome_digest,
                    expected_verified_prefix_digest,
                    expected_revision_head_digest
                FROM cycle_commit_plan_receipt
                WHERE plan_id = ?
                """,
                (plan_id,),
            ).fetchone()
            if receipt is None:
                raise PublicationFailedClosed(
                    "canonical-publication-incomplete",
                    "CycleCommitPlanReceipt is absent",
                )

            experience = self._read_experience(bytes(row[7]))
            epistemic = self._read_epistemic(bytes(row[8]))
            experience_outcome = self._read_experience_outcome(bytes(row[9]))
            subject_state_outcome = self._read_subject_state_outcome(bytes(row[10]))
            agency_outcome = self._read_agency_outcome(bytes(row[11]))
            relationship_outcome = self._read_relationship_outcome(bytes(row[12]))
            revision_set = self._read_revision_set(bytes(row[13]))
            expression = self._read_expression(bytes(row[14]))
            effect_set = self._read_effect_set(bytes(row[15]))
            life_record = self._read_life_record(plan_id)

            domain_set = self._writer.execute(
                """
                SELECT
                    experience_outcome_id,
                    subject_state_outcome_id,
                    agency_outcome_id,
                    relationship_outcome_id,
                    set_digest
                FROM domain_outcome_set
                WHERE plan_id = ?
                """,
                (plan_id,),
            ).fetchone()
            expected_domain_ids = (
                bytes(row[9]),
                bytes(row[10]),
                bytes(row[11]),
                bytes(row[12]),
            )
            if (
                domain_set is None
                or tuple(bytes(domain_set[index]) for index in range(4))
                != expected_domain_ids
            ):
                raise PublicationFailedClosed(
                    "canonical-publication-incomplete",
                    "DomainOutcomeSet is absent or does not close all typed refs",
                )
            domain_values = (
                experience_outcome,
                subject_state_outcome,
                agency_outcome,
                relationship_outcome,
            )
            self._assert_record_digest(
                "domain-outcome-set",
                domain_values,
                domain_set[4],
            )

            expected_basis = TimelineBasis(
                head_sequence=int(receipt[6]),
                published_outcome_digest=(
                    None if receipt[7] is None else bytes(receipt[7]).hex()
                ),
                verified_prefix_digest=bytes(receipt[8]).hex(),
                revision_head_digest=bytes(receipt[9]).hex(),
            )
            plan = CycleCommitPlan(
                plan_id=str(UUID(bytes=plan_id)),
                cycle_plan_id=str(UUID(bytes=bytes(receipt[1]))),
                operation_ref=operation_ref,
                attempt_id=str(UUID(bytes=bytes(receipt[2]))),
                subject_event_id=str(UUID(bytes=bytes(receipt[3]))),
                profile_id=str(receipt[4]),
                timeline_id=str(receipt[5]),
                expected_basis=expected_basis,
                experience=experience,
                epistemic_outcome=epistemic,
                experience_outcome=experience_outcome,
                subject_state_outcome=subject_state_outcome,
                agency_outcome=agency_outcome,
                relationship_outcome=relationship_outcome,
                revision_set=revision_set,
                expression=expression,
                committed_effect_set=effect_set,
                life_record=life_record,
            )
            self._validate_commit_plan(plan)
            plan_digest = _publication_digest("cycle-commit-plan", plan)
            if plan_digest != bytes(receipt[0]):
                raise PublicationFailedClosed(
                    "canonical-publication-integrity-mismatch",
                    "CycleCommitPlanReceipt digest does not match composing records",
                )
            if LIFE_SYSTEM_INTENT in self._authority.allowed_intents and self.prepared_plan(operation_ref) != plan:
                raise PublicationFailedClosed('prepared-publication-mismatch', 'published plan differs from durable preparation')
            claim = self._writer.execute(
                """
                SELECT plan_digest
                FROM commit_plan_identity_claim
                WHERE plan_id = ?
                """,
                (plan_id,),
            ).fetchone()
            publication_receipt = self._writer.execute(
                """
                SELECT outcome_id, outcome_digest
                FROM publication_receipt
                WHERE plan_id = ?
                """,
                (plan_id,),
            ).fetchone()
            if (
                claim is None
                or bytes(claim[0]) != plan_digest
                or publication_receipt is None
                or bytes(publication_receipt[0]) != outcome_id
                or bytes(publication_receipt[1]) != bytes(row[6])
            ):
                raise PublicationFailedClosed(
                    "canonical-publication-integrity-mismatch",
                    "plan claim or PublicationReceipt does not match the outcome",
                )

            previous_digest = None if row[5] is None else bytes(row[5]).hex()
            expected_outcome_digest = _publication_digest(
                "timeline-outcome",
                {
                    "outcome_id": str(UUID(bytes=outcome_id)),
                    "operation_ref": operation_ref,
                    "attempt_id": plan.attempt_id,
                    "subject_event_id": plan.subject_event_id,
                    "plan_id": plan.plan_id,
                    "plan_digest": plan_digest.hex(),
                    "head_sequence": int(row[4]),
                    "previous_outcome_digest": previous_digest,
                    "experience": experience,
                    "epistemic_outcome": epistemic,
                    "experience_outcome": experience_outcome,
                    "subject_state_outcome": subject_state_outcome,
                    "agency_outcome": agency_outcome,
                    "relationship_outcome": relationship_outcome,
                    "revision_set": revision_set,
                    "expression": expression,
                    "committed_effect_set": effect_set,
                    **({'life_record': life_record} if life_record is not None else {}),
                },
            )
            if expected_outcome_digest != bytes(row[6]):
                raise PublicationFailedClosed(
                    "canonical-publication-integrity-mismatch",
                    "TimelineOutcome digest does not match composing records",
                )
            return TimelineOutcome(
                outcome_id=str(UUID(bytes=outcome_id)),
                operation_ref=operation_ref,
                attempt_id=plan.attempt_id,
                subject_event_id=plan.subject_event_id,
                plan_id=plan.plan_id,
                head_sequence=int(row[4]),
                previous_outcome_digest=previous_digest,
                outcome_digest=bytes(row[6]).hex(),
                experience=experience,
                epistemic_outcome=epistemic,
                experience_outcome=experience_outcome,
                subject_state_outcome=subject_state_outcome,
                agency_outcome=agency_outcome,
                relationship_outcome=relationship_outcome,
                revision_set=revision_set,
                expression=expression,
                committed_effect_set=effect_set,
                life_record=life_record,
            )
        except PublicationProblem:
            raise
        except (json.JSONDecodeError, sqlite3.Error, TypeError, ValueError) as error:
            raise PublicationFailedClosed(
                "canonical-publication-unreadable",
                "canonical TimelineOutcome projection could not be rebuilt",
            ) from error


def _data_control_export_snapshot(
    location: CanonicalRootRef,
    *,
    expected_authority: FixtureAuthority | _RuntimeBindingAuthority,
) -> dict[str, Any]:
    """Return a transactionally consistent typed Timeline view for export."""

    engine = TimelineEngine.open(
        location,
        expected_authority=expected_authority,
        _host_token=(
            _HOST_TIMELINE_TOKEN
            if isinstance(expected_authority, _RuntimeBindingAuthority)
            else None
        ),
    )
    transaction_open = False
    try:
        engine._writer.execute("BEGIN")
        transaction_open = True
        operation_rows = engine._writer.execute(
            """
            SELECT operation_id
            FROM subject_operation
            ORDER BY admitted_at_us, operation_id
            """
        ).fetchall()
        operations: list[dict[str, Any]] = []
        outcomes: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for operation_row in operation_rows:
            operation_id = bytes(operation_row[0])
            admitted = engine._admitted_for_operation(
                engine._writer,
                operation_id,
                replayed=True,
            )
            snapshot = engine.query(admitted.operation_ref)
            if admitted.operation_ref.operation_kind is OperationKind.SYSTEM:
                system_input = engine._query_command(admitted.operation_ref)
                operations.append({
                    "operation_ref": _canonical_value(admitted.operation_ref),
                    "admission_snapshot": _canonical_value(snapshot),
                    "system_input": _canonical_value(system_input),
                })
            else:
                command = engine._writer.execute(
                    """
                    SELECT
                        command_kind,
                        target_profile_id,
                        target_timeline_id,
                        declared_intent,
                        utterance,
                        language,
                        provenance,
                        normalization_version,
                        payload_fingerprint
                    FROM subject_command
                    WHERE operation_id = ?
                    """,
                    (operation_id,),
                ).fetchone()
                if command is None:
                    raise AdmissionFailedClosed(
                        "data-control-timeline-incomplete",
                        "canonical Operation has no admitted SubjectCommand",
                    )
                operations.append(
                    {
                        "operation_ref": _canonical_value(admitted.operation_ref),
                        "admission_snapshot": _canonical_value(snapshot),
                        "command": {
                            "contract_version": CONTRACT_VERSION,
                            "kind": str(command[0]),
                            "target_profile_id": str(command[1]),
                            "target_timeline_id": str(command[2]),
                            "declared_intent": str(command[3]),
                            "utterance": str(command[4]),
                            "language": str(command[5]),
                            "provenance": str(command[6]),
                            "normalization_version": str(command[7]),
                            "payload_fingerprint": bytes(command[8]).hex(),
                        },
                    }
                )
            if snapshot.operation_state is OperationState.COMPLETED:
                outcomes.append(
                    _canonical_value(engine.query_outcome(admitted.operation_ref))
                )
            elif snapshot.operation_state is OperationState.FAILED_CLOSED:
                failures.append(
                    _canonical_value(engine.query_failure(admitted.operation_ref))
                )
        basis = _read_timeline_basis(engine._writer)
        event_kinds = [
            str(row[0])
            for row in engine._writer.execute(
                "SELECT event_kind FROM subject_event ORDER BY recorded_at_us, event_id"
            ).fetchall()
        ]
        effect_export={}
        actual_schema=engine._writer.execute('PRAGMA user_version').fetchone()[0]
        if actual_schema==2:
            engine._verified_subject_tasks()
            effect_export={'effect_receipts':engine._effect_receipts(),
                'effect_receipt_head':engine._writer.execute('SELECT receipt_count,receipt_digest FROM effect_receipt_head WHERE singleton=1').fetchone()}
        engine._writer.execute("COMMIT")
        transaction_open = False
        return {
            "runtime_timeline": {
                "record_kind": "runtime-timeline",
                "schema_family": TIMELINE_SCHEMA_FAMILY,
                "schema_version": actual_schema,
                **effect_export,
                "contract_version": CONTRACT_VERSION,
                "persistence_version": PERSISTENCE_VERSION,
                "source_root": location.to_dict(),
                "authority": expected_authority.to_dict(),
                "head": _canonical_value(basis),
                "operations": operations,
                "operation_failures": failures,
                "subject_event_kinds": event_kinds,
            },
            "timeline_outcomes": {
                "record_kind": "timeline-outcomes",
                "contract_version": CONTRACT_VERSION,
                "outcomes": outcomes,
            },
        }
    finally:
        if transaction_open:
            engine._writer.execute("ROLLBACK")
        engine.close()


def _data_control_open_timeline_writer(
    location: CanonicalRootRef,
) -> sqlite3.Connection:
    root = _validate_existing_root(
        location.root,
        location.root_id,
        root_kind=location.root_kind,
    )
    _read_root_identity(root, location.root_id, location.root_kind)
    control = _connect_existing_writer(location.control_database)
    try:
        _verify_connection_profile(control)
        _verify_manifest(
            control,
            root_id=location.root_id,
            store_id=location.control_store_id,
            store_kind="control",
            schema_family=CONTROL_SCHEMA_FAMILY,
        )
        _verify_store_integrity(control, expected_tables=_CONTROL_TABLES)
        registration = control.execute(
            """
            SELECT timeline_store_id, relative_database_path, registration_state
            FROM timeline_registration
            WHERE timeline_id = ?
            """,
            (location.timeline_id,),
        ).fetchone()
        if registration != (
            location.timeline_store_id,
            f"timelines/{location.timeline_id}/timeline.sqlite3",
            "ready",
        ):
            raise AdmissionFailedClosed(
                "store-identity-mismatch",
                "Timeline registration changed before DataControl clear",
            )
    finally:
        control.close()
    writer = _connect_existing_writer(location.timeline_database)
    try:
        _verify_connection_profile(writer)
        _verify_manifest(
            writer,
            root_id=location.root_id,
            store_id=location.timeline_store_id,
            store_kind="timeline",
            schema_family=TIMELINE_SCHEMA_FAMILY,
        )
        _verify_store_integrity(writer, expected_tables=_TIMELINE_TABLES)
    except Exception:
        writer.close()
        raise
    return writer


def _data_control_begin_clear(
    location: CanonicalRootRef,
    *,
    scope_id: str,
    expected_authority: FixtureAuthority,
) -> int:
    """Atomically withdraw Admission and fence stale Publication."""

    try:
        canonical_scope = str(UUID(scope_id))
    except (AttributeError, TypeError, ValueError) as error:
        raise AdmissionFailedClosed(
            "data-control-scope-invalid",
            "DataControl scope identity is invalid",
        ) from error
    if canonical_scope != scope_id:
        raise AdmissionFailedClosed(
            "data-control-scope-invalid",
            "DataControl scope identity is not canonical",
        )
    writer = _data_control_open_timeline_writer(location)
    try:
        _begin(writer)
        authority, epoch, state, bound_scope = _read_fixture_gate(writer)
        if authority != expected_authority:
            raise AdmissionFailedClosed(
                "authority-identity-mismatch",
                "Timeline authority changed before DataControl clear",
            )
        if state == "open" and bound_scope is None:
            epoch += 1
            writer.execute(
                """
                UPDATE admission_gate
                SET gate_epoch = ?, gate_state = 'clearing',
                    data_control_scope_id = ?
                WHERE singleton = 1
                """,
                (epoch, canonical_scope),
            )
        elif state != "clearing" or bound_scope != canonical_scope:
            raise AdmissionFailedClosed(
                "data-control-scope-conflict",
                "Timeline gate is bound to a different governance operation",
            )
        _commit(writer)
        return epoch
    except Exception:
        _rollback_if_needed(writer)
        raise
    finally:
        writer.close()


def _data_control_verify_clear_target(
    location: CanonicalRootRef,
    *,
    scope_id: str,
    expected_authority: FixtureAuthority,
) -> dict[str, str]:
    """Recheck the exact clearing Timeline capsule immediately before deletion."""

    writer = _data_control_open_timeline_writer(location)
    try:
        authority, epoch, state, bound_scope = _read_fixture_gate(writer)
        if (
            authority != expected_authority
            or state != "clearing"
            or bound_scope != scope_id
            or epoch < 2
        ):
            raise AdmissionFailedClosed(
                "timeline-governance-mismatch",
                "Timeline capsule is not fenced by the selected clear scope",
            )
        return {
            "root_id": location.root_id,
            "control_store_id": location.control_store_id,
            "timeline_store_id": location.timeline_store_id,
            "timeline_id": location.timeline_id,
            "profile_id": authority.profile_id,
            "scope_id": bound_scope,
        }
    finally:
        writer.close()


__all__ = [
    "AdmissionFailedClosed",
    "AdmissionInterrupted",
    "AdmissionSnapshot",
    "Admitted",
    "AgencyDomainOutcome",
    "AttemptState",
    "CandidateDecisionRecord",
    "CanonicalRootRef",
    "CommitPlanConflict",
    "CommitPlanRejected",
    "CommittedEffectSet",
    "ConversationTurnRecord",
    "CycleCommitPlan",
    "DecisionStatus",
    "DevelopmentOutcome",
    "EffectDispatchState",
    "EpistemicOutcome",
    "ExperienceDomainOutcome",
    "ExperienceRecord",
    "Expression",
    "FaultPoint",
    "FixtureAuthority",
    "OperationFailure",
    "OperationRef",
    "OperationState",
    "PayloadConflict",
    "PreAdmissionRejected",
    "PublicationFailedClosed",
    "PublicationInterrupted",
    "PublicationProblem",
    "Published",
    "RelationshipDomainOutcome",
    "RevisionSet",
    "StaleTimelineBasis",
    "SubjectCommand",
    "SubjectCoreOutcome",
    "SubjectStateDomainOutcome",
    "TimelineBasis",
    "TimelineEngine",
    "TimelineOutcome",
]
