"""M0 Host authoring and immutable runtime-input qualification.

PolicyKernel owns deterministic qualification. SubjectStudio owns the only
ProfileStore writer and hides draft revision, seal, immutable artifact, and
qualification publication transactions behind one Host-authoring Interface.
Nothing in this module creates lived history or a timeline head.
"""

from __future__ import annotations
from dynamic_subject_agent.reviewed_character_definition import (
    REVIEWED_CHARACTER_AUTHORITY, REVIEWED_CHARACTER_PROOF, REVIEWED_KNOWLEDGE_QUALIFICATION,
    is_reviewed_source, reviewed_source_refs, reviewed_profile_id, validate_reviewed_envelope,
)

from dynamic_subject_agent.first_life import (LIFE_AUTHORITY, LIFE_DORMANT_AUTHORITY, first_life_definition, first_life_source_refs, is_first_life_source, life_profile_id)
from dynamic_subject_agent.reviewed_character_chat import CHAT_AUTHORITY, chat_contract, matches_chat_source_contract
from dynamic_subject_agent.original_whole_chat import WHOLE_AUTHORITY, matches_whole_source_contract, validate_whole_envelope

import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from time import time_ns
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from dynamic_subject_agent.source_authoring import (
    ArtifactProvenance,
    UnsealedGenesisArtifact,
    UnsealedKnowledgeArtifact,
    UnpublishedSubjectStudioArtifact,
)
from dynamic_subject_agent.source_character_authoring import (
    SourceFreezeMappingRequest,
    SourceFreezeMappingResponse,
    SourceFreezeMappingStatus,
    SourceFreezeMappingView,
    SourceDraftCommand,
    SourceDraftCommandKind,
    SourceDraftResponse,
    SourceDraftSaveRequest,
    SourceDraftStatus,
    SourceDraftView,
    prepare_source_draft_save,
    prepare_source_freeze_mapping,
    source_draft_candidates_from_json,
)
from dynamic_subject_agent.knowledge_entries import KnowledgeEntry


CONTRACT_VERSION = "M0-CONTRACT-1.0"
PERSISTENCE_VERSION = "M0-PERSISTENCE-1.0"
POLICY_VERSION = "m0-host-policy-1.0"
QUALIFICATION_VERSION = "m0-qualified-runtime-input-1.0"
SCHEMA_VERSION = 2
_LEGACY_SCHEMA_VERSION = 1
ROOT_FORMAT = "dynamic-subject-m0-canonical"
ROOT_EPOCH = 1
ROOT_KIND = "test-fixture"
EXPERIMENTAL_ROOT_KIND = "experimental"
PROFILE_SCHEMA_FAMILY = "m0-canonical-profile"
_PUBLICATION_KEY = re.compile(r"^[A-Za-z0-9._~-]{16,256}$")
_RESERVED_TEST_PATH_SEGMENTS = frozenset(
    {"backup", "backups", "legacy", "private", "retired", "sagiri"}
)
_PROVIDER_AUTHORITY = "fake-cognition:m0-a-cycle-1.0"
_DEEPSEEK_PROVIDER_AUTHORITY = "02081deb-96be-4f1c-8a17-9cc39f8daaac"
_DORMANT_ARTIFACT_PROVIDER_AUTHORITY = "dormant-artifact:no-cognition-1.0"
_LOCAL_FIRST_TEST_PROVIDER_AUTHORITY = (
    "local-first:deterministic-test-double-1.0"
)
_LOCAL_LLAMA_PROVIDER_AUTHORITY = "local-first:llama:qwen3-4b-q4-k-m-1.0"
_LOCAL_FIRST_PHASE1_IDEMPOTENCY_KEY = (
    "post-m0-04-local-first-command-test-0001"
)
_LOCAL_FIRST_PHASE1_CONFIRMED_BRIEF = (
    "仅确认这是 Phase 1 原创临时 fixture；不提供历史、Knowledge、Memory "
    "或任何外部来源。"
)
_LOCAL_FIRST_LOCAL_IDEMPOTENCY_KEY = "post-m0-04-local-llama-command-0001"
_LOCAL_FIRST_LOCAL_CONFIRMED_BRIEF = (
    "Avery 是成年虚构 zine 创作者，正在准备一本灯笼主题 zine。本次只处理"
    "当前这条命令与这份已确认简报，不读取历史、Memory 或任何外部来源。"
)
_QRI_PUBLICATION_TOKEN = object()
_CORRECTIVE_LOCAL_LLAMA_SUCCESSOR_AUTHORITY = object()
_EXPERIMENTAL_PREVIEW_TOKEN = object()
_CONFIRMED_EXPERIMENT_PREPARATION_TOKEN = object()
_CONFIRMED_ARTIFACT_ACTIVATION_TOKEN = object()
_POST_M0_03_PHASE_2_PREVIEW_SHA256 = (
    "1ff52a7cec70e8bbce128de1ed409d5f2bae7a01e41ecc3e9a1ee8a1d7fa1c57"
)
_POST_M0_03_PHASE_2_CONFIRMATION_SHA256 = (
    "6fca03228b1462e81ac4c94de4059ad842ead0249913c32ef553e5b2685010f2"
)


class PolicyDisposition(str, Enum):
    QUALIFIED = "qualified"
    DENIED = "denied"
    UNAVAILABLE = "unavailable"


class StudioFaultPoint(str, Enum):
    BEFORE_PUBLICATION_TRANSACTION = "before-publication-transaction"
    AFTER_QRI_INSERT = "after-qri-insert"
    BEFORE_PUBLICATION_COMMIT = "before-publication-commit"
    AFTER_PUBLICATION_COMMIT = "after-publication-commit"


class AcceptedArtifactActivationFaultPoint(str, Enum):
    AFTER_LOCK = "after-lock"
    AFTER_STUDIO_OPEN = "after-studio-open"
    AFTER_DRAFT_STAGE = "after-draft-stage"
    AFTER_GENESIS_FREEZE_ATTEMPT = "after-genesis-freeze-attempt"
    AFTER_KNOWLEDGE_FREEZE_ATTEMPT = "after-knowledge-freeze-attempt"
    AFTER_SEAL = "after-seal"
    AFTER_COMPATIBILITY_PROOF = "after-compatibility-proof"
    AFTER_QRI_PUBLICATION = "after-qri-publication"
    AFTER_COMPOSITION_HEALTH = "after-composition-health"
    BEFORE_VISIBILITY_COMMIT = "before-visibility-commit"


class StudioProblem(Exception):
    """Base for typed Host-authoring failures."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class StudioRejected(StudioProblem):
    """A deterministic policy or structure check rejected the request."""


class StudioConflict(StudioProblem):
    """An immutable identity already names different content."""


class StudioFailedClosed(StudioProblem):
    """A technical inability prevented a trustworthy decision."""


class StudioInterrupted(StudioProblem):
    """A publication attempt was interrupted and must be queried or retried."""


def _canonical_uuid(value: str, field: str) -> str:
    try:
        canonical = str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as error:
        raise StudioRejected("invalid-identity", f"{field} must be a UUID") from error
    if canonical != str(value):
        raise StudioRejected("invalid-identity", f"{field} must be canonical")
    return canonical


def _normalize_text(value: str, field: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise StudioRejected("invalid-text", f"{field} must be text")
    normalized = unicodedata.normalize("NFC", value).replace("\r\n", "\n")
    normalized = normalized.replace("\r", "\n").strip()
    if not normalized or len(normalized) > maximum or "\x00" in normalized:
        raise StudioRejected(
            "invalid-text",
            f"{field} must be non-empty and at most {maximum} characters",
        )
    return normalized


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_canonical_value(item) for item in value]
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_sha256(value: str, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.casefold() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise StudioRejected("invalid-digest", f"{field} must be canonical SHA-256")
    return value


def _local_first_interaction_basis_digest(
    *,
    profile_id: str,
    timeline_id: str,
    command_fingerprint: str,
    idempotency_key_digest: str,
    confirmed_brief_digest: str,
) -> str:
    return _digest(
        {
            "profile_id": _canonical_uuid(profile_id, "profile_id"),
            "timeline_id": _canonical_uuid(timeline_id, "timeline_id"),
            "command_fingerprint": _canonical_sha256(
                command_fingerprint,
                "command_fingerprint",
            ),
            "idempotency_key_digest": _canonical_sha256(
                idempotency_key_digest,
                "idempotency_key_digest",
            ),
            "confirmed_brief_digest": _canonical_sha256(
                confirmed_brief_digest,
                "confirmed_brief_digest",
            ),
        }
    )


def _local_first_successor_compatibility_digest(
    *,
    predecessor_qualification_id: str,
    predecessor_integrity_digest: str,
    predecessor_compatibility_proof: str,
    policy_decision_id: str,
    capability_manifest: CapabilityManifest,
    provider_authority: str,
    interaction_basis_digest: str,
) -> str:
    return _digest(
        {
            "predecessor_qualification_id": _canonical_uuid(
                predecessor_qualification_id,
                "predecessor_qualification_id",
            ),
            "predecessor_integrity_digest": _canonical_sha256(
                predecessor_integrity_digest,
                "predecessor_integrity_digest",
            ),
            "accepted_artifact_compatibility_proof": _canonical_sha256(
                predecessor_compatibility_proof,
                "predecessor_compatibility_proof",
            ),
            "policy_decision_id": _canonical_uuid(
                policy_decision_id,
                "policy_decision_id",
            ),
            "capability_manifest": capability_manifest.to_dict(),
            "provider_authority": provider_authority,
            "interaction_basis_digest": _canonical_sha256(
                interaction_basis_digest,
                "interaction_basis_digest",
            ),
        }
    )


def _local_first_phase1_test_interaction(
    *,
    predecessor_qualification_id: str,
    profile_id: str,
    successor_publication_key: str,
) -> tuple[Any, str, str]:
    """Derive the only Phase-1 command/brief plan without caller input."""

    from dynamic_subject_agent.timeline import SubjectCommand

    predecessor_id = _canonical_uuid(
        predecessor_qualification_id,
        "predecessor_qualification_id",
    )
    canonical_profile_id = _canonical_uuid(profile_id, "profile_id")
    if not isinstance(successor_publication_key, str) or not _PUBLICATION_KEY.fullmatch(
        successor_publication_key
    ):
        raise StudioRejected(
            "invalid-publication-key",
            "successor publication key is invalid",
        )
    timeline_id = str(
        uuid5(
            NAMESPACE_URL,
            "post-m0-04-phase1-timeline:"
            f"{predecessor_id}:{successor_publication_key}",
        )
    )
    command = SubjectCommand.contribute_utterance(
        target_profile_id=canonical_profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="请只根据这条当前命令说明本地测试通道是否工作。",
        language="zh-CN",
        provenance="project-original",
    )
    return (
        command,
        _LOCAL_FIRST_PHASE1_IDEMPOTENCY_KEY,
        _LOCAL_FIRST_PHASE1_CONFIRMED_BRIEF,
    )


def _local_first_phase3_local_interaction(
    *,
    predecessor_qualification_id: str,
    profile_id: str,
    successor_publication_key: str,
    _corrective_timeline_id: str | None = None,
) -> tuple[Any, str, str]:
    """Derive the only production local command/brief plan without caller input."""

    from dynamic_subject_agent.timeline import SubjectCommand

    predecessor_id = _canonical_uuid(
        predecessor_qualification_id,
        "predecessor_qualification_id",
    )
    canonical_profile_id = _canonical_uuid(profile_id, "profile_id")
    if not isinstance(successor_publication_key, str) or not _PUBLICATION_KEY.fullmatch(
        successor_publication_key
    ):
        raise StudioRejected(
            "invalid-publication-key",
            "successor publication key is invalid",
        )
    timeline_id = (
        str(uuid5(
            NAMESPACE_URL,
            "post-m0-04-local-llama-timeline:"
            f"{predecessor_id}:{successor_publication_key}",
        ))
        if _corrective_timeline_id is None
        else _canonical_uuid(_corrective_timeline_id, "corrective_timeline_id")
    )
    command = SubjectCommand.contribute_utterance(
        target_profile_id=canonical_profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="请根据这条当前命令与已确认简报，用中文简短说明本地模型通道是否工作。",
        language="zh-CN",
        provenance="project-original",
    )
    return (
        command,
        _LOCAL_FIRST_LOCAL_IDEMPOTENCY_KEY,
        _LOCAL_FIRST_LOCAL_CONFIRMED_BRIEF,
    )


def _utc_microseconds() -> int:
    return time_ns() // 1_000


@dataclass(frozen=True)
class SourceDeclaration:
    source_id: str
    origin_kind: str
    rights_confirmed: bool
    source_asset_refs: tuple[str, ...]
    uses_disallowed_inheritance: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _canonical_uuid(self.source_id, "source_id"))
        origin_kind = _normalize_text(self.origin_kind, "origin_kind", maximum=64)
        object.__setattr__(self, "origin_kind", origin_kind)
        if not isinstance(self.rights_confirmed, bool):
            raise StudioRejected(
                "invalid-source-declaration",
                "rights_confirmed must be explicit",
            )
        refs = tuple(
            _normalize_text(value, "source_asset_ref", maximum=256)
            for value in self.source_asset_refs
        )
        if len(set(refs)) != len(refs):
            raise StudioRejected(
                "invalid-source-declaration",
                "source asset references must be unique",
            )
        object.__setattr__(self, "source_asset_refs", refs)
        if not isinstance(self.uses_disallowed_inheritance, bool):
            raise StudioRejected(
                "invalid-source-declaration",
                "inheritance declaration must be explicit",
            )

    @classmethod
    def project_original(cls, *, rights_confirmed: bool) -> SourceDeclaration:
        return cls(
            source_id=str(uuid4()),
            origin_kind="project-original",
            rights_confirmed=rights_confirmed,
            source_asset_refs=(),
            uses_disallowed_inheritance=False,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "origin_kind": self.origin_kind,
            "rights_confirmed": self.rights_confirmed,
            "source_asset_refs": list(self.source_asset_refs),
            "uses_disallowed_inheritance": self.uses_disallowed_inheritance,
        }

    @classmethod
    def from_dict(cls, source: Mapping[str, Any]) -> SourceDeclaration:
        return cls(
            source_id=str(source.get("source_id", "")),
            origin_kind=str(source.get("origin_kind", "")),
            rights_confirmed=source.get("rights_confirmed"),
            source_asset_refs=tuple(source.get("source_asset_refs", ())),
            uses_disallowed_inheritance=source.get("uses_disallowed_inheritance"),
        )


@dataclass(frozen=True)
class ParticipantProfile:
    profile_id: str
    display_name: str
    identity_core: str
    source: SourceDeclaration
    profile_revision: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_id", _canonical_uuid(self.profile_id, "profile_id"))
        object.__setattr__(
            self,
            "display_name",
            _normalize_text(self.display_name, "display_name", maximum=128),
        )
        object.__setattr__(
            self,
            "identity_core",
            _normalize_text(self.identity_core, "identity_core", maximum=2_000),
        )
        if not isinstance(self.source, SourceDeclaration):
            raise StudioRejected(
                "invalid-profile",
                "ParticipantProfile requires a SourceDeclaration",
            )
        if self.profile_revision != 1:
            raise StudioRejected(
                "invalid-profile",
                "M0 ParticipantProfile revision must start at one",
            )

    @classmethod
    def original(
        cls,
        *,
        display_name: str,
        identity_core: str,
        source: SourceDeclaration,
    ) -> ParticipantProfile:
        return cls(
            profile_id=str(uuid4()),
            display_name=display_name,
            identity_core=identity_core,
            source=source,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "display_name": self.display_name,
            "identity_core": self.identity_core,
            "source": self.source.to_dict(),
            "profile_revision": self.profile_revision,
        }

    @classmethod
    def from_dict(cls, source: Mapping[str, Any]) -> ParticipantProfile:
        source_declaration = source.get("source")
        if not isinstance(source_declaration, Mapping):
            raise StudioFailedClosed("profile-corrupt", "profile source is missing")
        return cls(
            profile_id=str(source.get("profile_id", "")),
            display_name=str(source.get("display_name", "")),
            identity_core=str(source.get("identity_core", "")),
            source=SourceDeclaration.from_dict(source_declaration),
            profile_revision=int(source.get("profile_revision", 0)),
        )


@dataclass(frozen=True)
class GenesisPremise:
    subject_identity: str
    canon_start: str
    initial_relationship_premise: str
    source: SourceDeclaration

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "subject_identity",
            _normalize_text(self.subject_identity, "subject_identity", maximum=2_000),
        )
        object.__setattr__(
            self,
            "canon_start",
            _normalize_text(self.canon_start, "canon_start", maximum=4_000),
        )
        object.__setattr__(
            self,
            "initial_relationship_premise",
            _normalize_text(
                self.initial_relationship_premise,
                "initial_relationship_premise",
                maximum=2_000,
            ),
        )
        if not isinstance(self.source, SourceDeclaration):
            raise StudioRejected(
                "invalid-genesis-premise",
                "GenesisPremise requires a SourceDeclaration",
            )

    @classmethod
    def original_lantern_zine(cls) -> GenesisPremise:
        return cls(
            subject_identity=(
                "Rowan Vale is an adult fictional creator of handmade community zines."
            ),
            canon_start=(
                "Rowan and Avery are preparing an original night-lantern zine and are "
                "checking whether the issue can still reach Friday's print slot."
            ),
            initial_relationship_premise=(
                "Rowan and Avery are newly acquainted collaborators; no trust, promise, "
                "shared memory, or earned relationship state is established."
            ),
            source=SourceDeclaration.project_original(rights_confirmed=True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_identity": self.subject_identity,
            "canon_start": self.canon_start,
            "initial_relationship_premise": self.initial_relationship_premise,
            "source": self.source.to_dict(),
        }

    @classmethod
    def from_dict(cls, source: Mapping[str, Any]) -> GenesisPremise:
        source_declaration = source.get("source")
        if not isinstance(source_declaration, Mapping):
            raise StudioFailedClosed("draft-corrupt", "Genesis source is missing")
        return cls(
            subject_identity=str(source.get("subject_identity", "")),
            canon_start=str(source.get("canon_start", "")),
            initial_relationship_premise=str(
                source.get("initial_relationship_premise", "")
            ),
            source=SourceDeclaration.from_dict(source_declaration),
        )


@dataclass(frozen=True)
class CapabilityManifest:
    manifest_version: str
    included: tuple[str, ...]
    certified: tuple[str, ...]
    unavailable: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "manifest_version",
            _normalize_text(
                self.manifest_version,
                "manifest_version",
                maximum=128,
            ),
        )
        for field in ("included", "certified", "unavailable"):
            values = tuple(
                _normalize_text(value, field, maximum=128)
                for value in getattr(self, field)
            )
            if len(values) != len(set(values)):
                raise StudioRejected(
                    "invalid-capability-manifest",
                    f"{field} capabilities must be unique",
                )
            object.__setattr__(self, field, values)
        if set(self.included) & set(self.unavailable):
            raise StudioRejected(
                "invalid-capability-manifest",
                "a capability cannot be included and unavailable",
            )
        if not set(self.certified).issubset(self.included):
            raise StudioRejected(
                "invalid-capability-manifest",
                "certified capabilities must be included",
            )

    @classmethod
    def m0(cls) -> CapabilityManifest:
        return cls(
            manifest_version="m0-lantern-zine-capabilities-1.0",
            included=(
                "fake-cognition",
                "four-domain-typed-noop",
                "host-authoring",
            ),
            certified=(
                "fake-cognition",
                "four-domain-typed-noop",
                "host-authoring",
            ),
            unavailable=(
                "real-cognition",
                "real-provider",
                "network-access",
                "external-tools",
                "tts",
            ),
        )

    @classmethod
    def deepseek_v4_flash_experimental(cls) -> CapabilityManifest:
        """Return the one confirmed no-egress DeepSeek activation manifest."""

        return cls(
            manifest_version="post-m0-deepseek-v4-flash-experimental-1.0",
            included=(
                "controlled-real-cognition",
                "deepseek-v4-flash",
                "four-domain-typed-noop",
                "host-authoring",
                "credential-isolation",
                "no-legacy-private-fallback",
            ),
            certified=(
                "four-domain-typed-noop",
                "host-authoring",
                "credential-isolation",
                "no-legacy-private-fallback",
            ),
            unavailable=(
                "automatic-history-retrieval",
                "memory",
                "relationship-change",
                "non-noop-domain-change",
                "effect-dispatch",
                "external-tools",
                "tts",
                "unapproved-network-egress",
                "other-provider-fallback",
                "legacy-private-fallback",
            ),
        )

    @classmethod
    def accepted_artifact_dormant(cls) -> CapabilityManifest:
        return cls(
            manifest_version="post-m0-accepted-artifact-dormant-1.0",
            included=(
                "host-authoring",
                "accepted-artifact-snapshots",
                "four-domain-typed-noop",
            ),
            certified=(
                "host-authoring",
                "accepted-artifact-snapshots",
                "four-domain-typed-noop",
            ),
            unavailable=(
                "cognition",
                "provider",
                "network-access",
                "automatic-history-retrieval",
                "memory",
                "relationship-change",
                "non-noop-domain-change",
                "effect-dispatch",
                "external-tools",
                "tts",
                "legacy-private-fallback",
            ),
        )

    @classmethod
    def reviewed_character_dormant(cls) -> CapabilityManifest:
        return cls(manifest_version="reviewed-character-dormant-capabilities-1",
            included=("host-authoring", "sealed-reviewed-character-definition"),
            certified=("host-authoring", "sealed-reviewed-character-definition"),
            unavailable=("cognition", "provider", "network-access", "legacy-six-domain-cognition", "effect-dispatch"))

    @classmethod
    def reviewed_character_chat(cls):
        return cls(manifest_version="reviewed-character-chat-capabilities-1",
            included=("host-authoring", "sealed-reviewed-character-definition", "private-character-chat", "deepseek-two-stage-chat", "bounded-canonical-dialogue"),
            certified=("host-authoring", "sealed-reviewed-character-definition", "private-character-chat", "deepseek-two-stage-chat", "bounded-canonical-dialogue"),
            unavailable=("legacy-six-domain-cognition", "subject-tasks", "effect-dispatch", "life-events", "background-notifications"))

    @classmethod
    def original_whole_chat(cls):
        return cls(manifest_version="original-whole-chat-capabilities-s127-1",
            included=("host-authoring", "sealed-reviewed-character-definition", "private-character-chat", "original-single-stage-whole-reply", "bounded-canonical-dialogue"),
            certified=("host-authoring", "sealed-reviewed-character-definition", "private-character-chat", "original-single-stage-whole-reply", "bounded-canonical-dialogue"),
            unavailable=("legacy-six-domain-cognition", "subject-tasks", "effect-dispatch", "life-events", "background-notifications", "persona-rewrite", "relationship-writeback"))

    @classmethod
    def first_life_dormant(cls):
        return cls(manifest_version="first-life-dormant-capabilities-1",
            included=("host-authoring", "sealed-reviewed-character-definition", "typed-first-life-publication"),
            certified=("host-authoring", "sealed-reviewed-character-definition", "typed-first-life-publication"),
            unavailable=("provider", "network-access", "first-life-models", "legacy-six-domain-cognition", "effect-dispatch"))

    @classmethod
    def first_life_active(cls):
        return cls(manifest_version="first-life-active-capabilities-1",
            included=("host-authoring", "sealed-reviewed-character-definition", "typed-first-life-publication", "private-character-life-chat", "bounded-application-sharing"),
            certified=("host-authoring", "sealed-reviewed-character-definition", "typed-first-life-publication", "private-character-life-chat", "bounded-application-sharing"),
            unavailable=("legacy-six-domain-cognition", "subject-tasks", "effect-dispatch", "background-notifications", "offline-catchup"))

    @classmethod
    def _local_first_test_double(cls) -> CapabilityManifest:
        """Return the Phase-1-only local interaction test manifest.

        This manifest qualifies a deterministic in-process cognition double.  It
        does not claim that an operating-system model runner or network-deny
        boundary has been qualified.
        """

        return cls(
            manifest_version="post-m0-04-local-first-test-double-1.0",
            included=(
                "accepted-artifact-snapshots",
                "current-command-only",
                "deterministic-local-cognition-test-double",
                "four-domain-typed-noop",
                "host-authoring",
                "user-confirmed-context-brief-only",
            ),
            certified=(
                "accepted-artifact-snapshots",
                "current-command-only",
                "deterministic-local-cognition-test-double",
                "four-domain-typed-noop",
                "host-authoring",
                "user-confirmed-context-brief-only",
            ),
            unavailable=(
                "operating-system-local-model-runner",
                "automatic-history-retrieval",
                "memory",
                "relationship-change",
                "non-noop-domain-change",
                "effect-dispatch",
                "external-tools",
                "tts",
                "network-access",
                "cloud-provider-fallback",
                "legacy-private-fallback",
            ),
        )

    @classmethod
    def _local_llama_experimental(cls) -> CapabilityManifest:
        """Return the one qualified local llama.cpp activation manifest.

        This manifest claims an operating-system local model runner bound to
        one exact qualified model and loopback-only inference, with OS-level
        network-deny enforced as a separate execution gate.
        """

        return cls(
            manifest_version="post-m0-04-local-llama-qwen3-4b-q4-k-m-1.0",
            included=(
                "accepted-artifact-snapshots",
                "current-command-only",
                "operating-system-local-model-runner",
                "qwen3-4b-q4-k-m",
                "loopback-only-local-inference",
                "user-confirmed-context-brief-only",
                "four-domain-typed-noop",
                "host-authoring",
            ),
            certified=(
                "accepted-artifact-snapshots",
                "current-command-only",
                "operating-system-local-model-runner",
                "qwen3-4b-q4-k-m",
                "loopback-only-local-inference",
                "user-confirmed-context-brief-only",
                "four-domain-typed-noop",
                "host-authoring",
            ),
            unavailable=(
                "automatic-history-retrieval",
                "memory",
                "relationship-change",
                "non-noop-domain-change",
                "effect-dispatch",
                "external-tools",
                "tts",
                "network-access",
                "cloud-provider-fallback",
                "legacy-private-fallback",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_version": self.manifest_version,
            "included": list(self.included),
            "certified": list(self.certified),
            "unavailable": list(self.unavailable),
        }

    @classmethod
    def from_dict(cls, source: Mapping[str, Any]) -> CapabilityManifest:
        return cls(
            manifest_version=str(source.get("manifest_version", "")),
            included=tuple(source.get("included", ())),
            certified=tuple(source.get("certified", ())),
            unavailable=tuple(source.get("unavailable", ())),
        )


@dataclass(frozen=True)
class IsolationProof:
    root_id: str
    root_kind: str
    path_class: str
    provenance_class: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "root_id", _canonical_uuid(self.root_id, "root_id"))
        for field in ("root_kind", "path_class", "provenance_class"):
            object.__setattr__(
                self,
                field,
                _normalize_text(getattr(self, field), field, maximum=128),
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "root_id": self.root_id,
            "root_kind": self.root_kind,
            "path_class": self.path_class,
            "provenance_class": self.provenance_class,
        }


@dataclass(frozen=True)
class StudioRootRef:
    root_path: str
    root_id: str
    profile_store_id: str
    root_kind: str = ROOT_KIND

    def __post_init__(self) -> None:
        if not Path(self.root_path).is_absolute():
            raise StudioRejected(
                "canonical-root-not-allowed",
                "Studio root reference must be absolute",
            )
        object.__setattr__(self, "root_id", _canonical_uuid(self.root_id, "root_id"))
        object.__setattr__(
            self,
            "profile_store_id",
            _canonical_uuid(self.profile_store_id, "profile_store_id"),
        )
        if self.root_kind not in {ROOT_KIND, EXPERIMENTAL_ROOT_KIND}:
            raise StudioRejected(
                "root-kind-not-allowed",
                "Studio root kind must be test-fixture or experimental",
            )

    @property
    def root(self) -> Path:
        return Path(self.root_path)

    @property
    def profile_database(self) -> Path:
        return self.root / "profiles" / self.profile_store_id / "profile.sqlite3"

    def to_dict(self) -> dict[str, str]:
        return {
            "root_path": self.root_path,
            "root_id": self.root_id,
            "profile_store_id": self.profile_store_id,
            "root_kind": self.root_kind,
        }

    @classmethod
    def from_dict(cls, source: Mapping[str, Any]) -> StudioRootRef:
        return cls(
            root_path=str(source.get("root_path", "")),
            root_id=str(source.get("root_id", "")),
            profile_store_id=str(source.get("profile_store_id", "")),
            root_kind=str(source.get("root_kind", ROOT_KIND)),
        )


@dataclass(frozen=True)
class DraftView:
    draft_id: str
    branch_id: str
    profile_id: str
    revision: int
    content_fingerprint: str
    sealed_snapshot_id: str | None


@dataclass(frozen=True)
class GenesisPreview:
    draft_id: str
    branch_id: str
    profile_id: str
    revision: int
    freeze_basis_digest: str
    content_fingerprint: str
    premise: GenesisPremise
    authoritative: bool = False


@dataclass(frozen=True)
class KnowledgeDraftPreview:
    draft_id: str
    artifact_id: str
    revision: int
    freeze_basis_digest: str
    content_fingerprint: str
    member_count: int
    authoritative: bool = False


@dataclass(frozen=True)
class _DormantArtifactMapping:
    policy_version: str
    display_name: str
    identity_core: str
    subject_identity: str
    canon_start: str
    initial_relationship_premise: str
    mapping_digest: str

    def to_dict(self) -> dict[str, str]:
        return {
            "policy_version": self.policy_version,
            "display_name": self.display_name,
            "identity_core": self.identity_core,
            "subject_identity": self.subject_identity,
            "canon_start": self.canon_start,
            "initial_relationship_premise": self.initial_relationship_premise,
        }


@dataclass(frozen=True)
class AcceptedArtifactDraftBundle:
    artifact_id: str
    profile_id: str
    provenance_digest: str
    mapping_policy_version: str
    mapping_digest: str
    genesis: GenesisPreview
    knowledge: KnowledgeDraftPreview
    authoritative: bool = False


@dataclass(frozen=True)
class FreezeDecision:
    decision_id: str
    draft_id: str
    expected_revision: int
    freeze_basis_digest: str
    decided_by: str
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision_id",
            _canonical_uuid(self.decision_id, "freeze_decision_id"),
        )
        object.__setattr__(self, "draft_id", _canonical_uuid(self.draft_id, "draft_id"))
        if self.expected_revision < 1:
            raise StudioRejected(
                "invalid-freeze-decision",
                "expected revision must be positive",
            )
        if not re.fullmatch(r"[0-9a-f]{64}", self.freeze_basis_digest):
            raise StudioRejected(
                "invalid-freeze-decision",
                "freeze basis digest is invalid",
            )
        object.__setattr__(
            self,
            "decided_by",
            _normalize_text(self.decided_by, "decided_by", maximum=128),
        )
        object.__setattr__(
            self,
            "rationale",
            _normalize_text(self.rationale, "rationale", maximum=1_000),
        )

    @classmethod
    def for_preview(
        cls,
        preview: GenesisPreview,
        *,
        decided_by: str,
        rationale: str,
    ) -> FreezeDecision:
        if not isinstance(preview, GenesisPreview):
            raise TypeError("FreezeDecision requires a GenesisPreview")
        return cls(
            decision_id=str(uuid4()),
            draft_id=preview.draft_id,
            expected_revision=preview.revision,
            freeze_basis_digest=preview.freeze_basis_digest,
            decided_by=decided_by,
            rationale=rationale,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "draft_id": self.draft_id,
            "expected_revision": self.expected_revision,
            "freeze_basis_digest": self.freeze_basis_digest,
            "decided_by": self.decided_by,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, source: Mapping[str, Any]) -> FreezeDecision:
        return cls(
            decision_id=str(source.get("decision_id", "")),
            draft_id=str(source.get("draft_id", "")),
            expected_revision=int(source.get("expected_revision", 0)),
            freeze_basis_digest=str(source.get("freeze_basis_digest", "")),
            decided_by=str(source.get("decided_by", "")),
            rationale=str(source.get("rationale", "")),
        )


@dataclass(frozen=True)
class ScopedFreezeDecision:
    decision_id: str
    scope: str
    draft_id: str
    expected_revision: int
    freeze_basis_digest: str
    decided_by: str
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision_id",
            _canonical_uuid(self.decision_id, "freeze_decision_id"),
        )
        if self.scope not in {"genesis", "knowledge"}:
            raise StudioRejected(
                "invalid-freeze-decision",
                "artifact FreezeDecision scope must be Genesis or Knowledge",
            )
        object.__setattr__(
            self,
            "draft_id",
            _canonical_uuid(self.draft_id, "draft_id"),
        )
        if self.expected_revision < 1 or not re.fullmatch(
            r"[0-9a-f]{64}", self.freeze_basis_digest
        ):
            raise StudioRejected(
                "invalid-freeze-decision",
                "artifact FreezeDecision basis is invalid",
            )
        object.__setattr__(
            self,
            "decided_by",
            _normalize_text(self.decided_by, "decided_by", maximum=128),
        )
        object.__setattr__(
            self,
            "rationale",
            _normalize_text(self.rationale, "rationale", maximum=1_000),
        )

    @classmethod
    def for_genesis(
        cls,
        preview: GenesisPreview,
        *,
        decided_by: str,
        rationale: str,
    ) -> ScopedFreezeDecision:
        return cls(
            decision_id=str(uuid4()),
            scope="genesis",
            draft_id=preview.draft_id,
            expected_revision=preview.revision,
            freeze_basis_digest=preview.freeze_basis_digest,
            decided_by=decided_by,
            rationale=rationale,
        )

    @classmethod
    def for_knowledge(
        cls,
        preview: KnowledgeDraftPreview,
        *,
        decided_by: str,
        rationale: str,
    ) -> ScopedFreezeDecision:
        return cls(
            decision_id=str(uuid4()),
            scope="knowledge",
            draft_id=preview.draft_id,
            expected_revision=preview.revision,
            freeze_basis_digest=preview.freeze_basis_digest,
            decided_by=decided_by,
            rationale=rationale,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "scope": self.scope,
            "draft_id": self.draft_id,
            "expected_revision": self.expected_revision,
            "freeze_basis_digest": self.freeze_basis_digest,
            "decided_by": self.decided_by,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class AcceptedArtifactSnapshot:
    snapshot_id: str
    scope: str
    artifact_id: str
    draft_id: str
    freeze_decision_id: str
    freeze_attempt_id: str
    policy_decision_id: str
    freeze_basis_digest: str
    content_fingerprint: str
    provenance_digest: str
    member_count: int
    created_at_us: int


@dataclass(frozen=True)
class AcceptedArtifactSnapshotBundle:
    artifact_id: str
    profile_id: str
    genesis: AcceptedArtifactSnapshot
    knowledge: AcceptedArtifactSnapshot


@dataclass(frozen=True)
class SnapshotCompatibilityProof:
    proof_id: str
    artifact_id: str
    profile_id: str
    genesis_snapshot_id: str
    knowledge_snapshot_id: str
    policy_decision_id: str
    capability_manifest_version: str
    participant_identity_digest: str
    source_qualification_digest: str
    knowledge_membership_digest: str
    prerequisites_digest: str
    integrity_digest: str


@dataclass(frozen=True)
class DormantArtifactActivationReceipt:
    activation_id: str
    artifact_id: str
    plan_digest: str
    studio_location: StudioRootRef
    host_root_path: str
    host_root_id: str
    host_control_store_id: str
    profile_id: str
    genesis_draft_id: str
    knowledge_draft_id: str
    genesis_freeze_decision_id: str
    knowledge_freeze_decision_id: str
    genesis_freeze_attempt_id: str
    knowledge_freeze_attempt_id: str
    genesis_snapshot_id: str
    knowledge_snapshot_id: str
    compatibility_proof_id: str
    qualification_id: str
    qri_publication_key: str
    binding_id: str
    authority_scope_id: str
    timeline_id: str
    timeline_root_id: str
    timeline_control_store_id: str
    timeline_store_id: str
    timeline_head: int
    timeline_gate_epoch: int
    live_runtime_instance_lease_count: int
    authority_counts: Mapping[str, int]
    visible_at_us: int
    integrity_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "activation_id": self.activation_id,
            "artifact_id": self.artifact_id,
            "plan_digest": self.plan_digest,
            "studio_location": self.studio_location.to_dict(),
            "host_root_path": self.host_root_path,
            "host_root_id": self.host_root_id,
            "host_control_store_id": self.host_control_store_id,
            "profile_id": self.profile_id,
            "genesis_draft_id": self.genesis_draft_id,
            "knowledge_draft_id": self.knowledge_draft_id,
            "genesis_freeze_decision_id": self.genesis_freeze_decision_id,
            "knowledge_freeze_decision_id": self.knowledge_freeze_decision_id,
            "genesis_freeze_attempt_id": self.genesis_freeze_attempt_id,
            "knowledge_freeze_attempt_id": self.knowledge_freeze_attempt_id,
            "genesis_snapshot_id": self.genesis_snapshot_id,
            "knowledge_snapshot_id": self.knowledge_snapshot_id,
            "compatibility_proof_id": self.compatibility_proof_id,
            "qualification_id": self.qualification_id,
            "qri_publication_key": self.qri_publication_key,
            "binding_id": self.binding_id,
            "authority_scope_id": self.authority_scope_id,
            "timeline_id": self.timeline_id,
            "timeline_root_id": self.timeline_root_id,
            "timeline_control_store_id": self.timeline_control_store_id,
            "timeline_store_id": self.timeline_store_id,
            "timeline_head": self.timeline_head,
            "timeline_gate_epoch": self.timeline_gate_epoch,
            "live_runtime_instance_lease_count": self.live_runtime_instance_lease_count,
            "authority_counts": dict(self.authority_counts),
            "visible_at_us": self.visible_at_us,
            "integrity_digest": self.integrity_digest,
        }


@dataclass(frozen=True)
class _AcceptedArtifactTestActivationPlan:
    activation_id: str
    artifact_id: str
    bundle_base: Path
    studio_root_id: str
    profile_store_id: str
    profile_id: str
    genesis_freeze_decision_id: str
    knowledge_freeze_decision_id: str
    qri_publication_key: str
    qualification_id: str
    timeline_id: str
    host_root_id: str
    host_control_store_id: str
    binding_id: str
    authority_scope_id: str
    timeline_root_id: str
    timeline_control_store_id: str
    timeline_store_id: str
    policy_clock_us: int
    activation_time_us: int
    root_kind: str
    gate_parent: Path
    plan_digest: str


def _accepted_artifact_test_activation_plan(
    test_parent: Path,
    artifact_id: str,
) -> _AcceptedArtifactTestActivationPlan:
    parent = _validate_test_base(Path(test_parent))
    canonical_artifact_id = _canonical_uuid(artifact_id, "artifact_id")
    activation_id = str(
        uuid5(
            NAMESPACE_URL,
            f"post-m0-03-test-activation:{canonical_artifact_id}",
        )
    )
    bundle_base = parent / "post-m0-03-activation-bundles" / activation_id
    studio_root_id = str(uuid5(NAMESPACE_URL, f"{activation_id}:studio-root"))
    profile_store_id = str(uuid5(NAMESPACE_URL, f"{activation_id}:profile-store"))
    profile_id = str(
        uuid5(
            NAMESPACE_URL,
            f"accepted-artifact-profile:{studio_root_id}:{canonical_artifact_id}",
        )
    )
    qri_publication_key = f"post-m0-03-artifact-qri-{activation_id}"
    qualification_id = str(
        uuid5(
            NAMESPACE_URL,
            f"accepted-artifact-qri:{studio_root_id}:{qri_publication_key}",
        )
    )
    host_root_id = str(uuid5(NAMESPACE_URL, f"{activation_id}:host-root"))
    timeline_id = str(uuid5(NAMESPACE_URL, f"{activation_id}:timeline"))
    binding_id = str(
        uuid5(
            NAMESPACE_URL,
            f"m0-12-binding:{host_root_id}:{profile_id}:{timeline_id}:"
            f"{qualification_id}:1",
        )
    )
    values: dict[str, Any] = {
        "activation_id": activation_id,
        "artifact_id": canonical_artifact_id,
        "bundle_base": str(bundle_base),
        "studio_root_id": studio_root_id,
        "profile_store_id": profile_store_id,
        "profile_id": profile_id,
        "genesis_freeze_decision_id": str(
            uuid5(NAMESPACE_URL, f"{activation_id}:genesis-freeze-decision")
        ),
        "knowledge_freeze_decision_id": str(
            uuid5(NAMESPACE_URL, f"{activation_id}:knowledge-freeze-decision")
        ),
        "qri_publication_key": qri_publication_key,
        "qualification_id": qualification_id,
        "timeline_id": timeline_id,
        "host_root_id": host_root_id,
        "host_control_store_id": str(
            uuid5(NAMESPACE_URL, f"{activation_id}:host-control-store")
        ),
        "binding_id": binding_id,
        "authority_scope_id": str(
            uuid5(NAMESPACE_URL, f"m0-12-authority-scope:{binding_id}")
        ),
        "timeline_root_id": str(
            uuid5(NAMESPACE_URL, f"{activation_id}:timeline-root")
        ),
        "timeline_control_store_id": str(
            uuid5(NAMESPACE_URL, f"{activation_id}:timeline-control-store")
        ),
        "timeline_store_id": str(
            uuid5(NAMESPACE_URL, f"{activation_id}:timeline-store")
        ),
        "policy_clock_us": 2_000_000_000_000_000,
        "activation_time_us": 2_000_000_000_000_000,
        "root_kind": ROOT_KIND,
        "gate_parent": str(parent / "post-m0-03-activation-gates"),
    }
    constructor_values = dict(values)
    constructor_values["bundle_base"] = bundle_base
    constructor_values["gate_parent"] = Path(values["gate_parent"])
    return _AcceptedArtifactTestActivationPlan(
        **constructor_values,
        plan_digest=_digest(values),
    )


@dataclass(frozen=True)
class _AcceptedArtifactExperimentalActivationPlan:
    activation_id: str
    artifact_id: str
    bundle_base: Path
    studio_root_id: str
    profile_store_id: str
    profile_id: str
    genesis_freeze_decision_id: str
    knowledge_freeze_decision_id: str
    qri_publication_key: str
    qualification_id: str
    timeline_id: str
    host_root_id: str
    host_control_store_id: str
    binding_id: str
    authority_scope_id: str
    timeline_root_id: str
    timeline_control_store_id: str
    timeline_store_id: str
    policy_clock_us: int
    activation_time_us: int
    root_kind: str
    gate_parent: Path
    plan_digest: str


_AcceptedArtifactActivationPlan = (
    _AcceptedArtifactTestActivationPlan | _AcceptedArtifactExperimentalActivationPlan
)


def _accepted_artifact_experimental_test_plan(
    test_parent: Path,
    artifact: UnpublishedSubjectStudioArtifact,
) -> _AcceptedArtifactExperimentalActivationPlan:
    parent = _validate_test_base(Path(test_parent))
    activation_id = str(
        uuid5(
            NAMESPACE_URL,
            f"post-m0-03-experimental-test:{artifact.artifact_id}",
        )
    )
    bundle_base = parent / activation_id
    studio_root_id = str(uuid5(NAMESPACE_URL, f"{activation_id}:studio-root"))
    profile_store_id = str(uuid5(NAMESPACE_URL, f"{activation_id}:profile-store"))
    profile_id = str(
        uuid5(
            NAMESPACE_URL,
            f"accepted-artifact-profile:{studio_root_id}:{artifact.artifact_id}",
        )
    )
    qri_publication_key = f"post-m0-03-artifact-qri-{activation_id}"
    qualification_id = str(
        uuid5(
            NAMESPACE_URL,
            f"accepted-artifact-qri:{studio_root_id}:{qri_publication_key}",
        )
    )
    host_root_id = str(uuid5(NAMESPACE_URL, f"{activation_id}:host-root"))
    timeline_id = str(uuid5(NAMESPACE_URL, f"{activation_id}:timeline"))
    binding_id = str(
        uuid5(
            NAMESPACE_URL,
            f"m0-12-binding:{host_root_id}:{profile_id}:{timeline_id}:"
            f"{qualification_id}:1",
        )
    )
    authority_scope_id = str(
        uuid5(NAMESPACE_URL, f"m0-12-authority-scope:{binding_id}")
    )
    values: dict[str, Any] = {
        "activation_id": activation_id,
        "artifact_id": artifact.artifact_id,
        "bundle_base": str(bundle_base),
        "studio_root_id": studio_root_id,
        "profile_store_id": profile_store_id,
        "profile_id": profile_id,
        "genesis_freeze_decision_id": str(
            uuid5(NAMESPACE_URL, f"{activation_id}:genesis-freeze-decision")
        ),
        "knowledge_freeze_decision_id": str(
            uuid5(NAMESPACE_URL, f"{activation_id}:knowledge-freeze-decision")
        ),
        "qri_publication_key": qri_publication_key,
        "qualification_id": qualification_id,
        "timeline_id": timeline_id,
        "host_root_id": host_root_id,
        "host_control_store_id": str(
            uuid5(NAMESPACE_URL, f"{activation_id}:host-control-store")
        ),
        "binding_id": binding_id,
        "authority_scope_id": authority_scope_id,
        "timeline_root_id": str(
            uuid5(NAMESPACE_URL, f"{activation_id}:timeline-root")
        ),
        "timeline_control_store_id": str(
            uuid5(NAMESPACE_URL, f"{activation_id}:timeline-control-store")
        ),
        "timeline_store_id": str(
            uuid5(NAMESPACE_URL, f"{activation_id}:timeline-store")
        ),
        "policy_clock_us": 2_000_000_000_000_000,
        "activation_time_us": 2_000_000_000_000_000,
        "root_kind": EXPERIMENTAL_ROOT_KIND,
        "gate_parent": str(parent / "experimental-activation-gates"),
    }
    constructor = dict(values)
    constructor["bundle_base"] = bundle_base
    constructor["gate_parent"] = Path(values["gate_parent"])
    return _AcceptedArtifactExperimentalActivationPlan(
        **constructor,
        plan_digest=_digest(values),
    )


@dataclass(frozen=True)
class PolicyQuestion:
    question_digest: str
    profile_digest: str
    freeze_basis_digest: str
    capability_manifest: CapabilityManifest
    isolation_proof: IsolationProof
    profile_source: SourceDeclaration
    genesis_source: SourceDeclaration
    reviewed_chat_contract: dict | None = None


@dataclass(frozen=True, init=False)
class PolicyDecision:
    decision_id: str
    disposition: PolicyDisposition
    reason_codes: tuple[str, ...]
    policy_version: str
    question_digest: str
    issued_at_us: int
    valid_until_us: int
    capability_manifest: CapabilityManifest
    integrity_digest: str

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("PolicyDecision can only be issued by PolicyKernel")

    @classmethod
    def _issue(
        cls,
        *,
        decision_id: str,
        disposition: PolicyDisposition,
        reason_codes: tuple[str, ...],
        policy_version: str,
        question_digest: str,
        issued_at_us: int,
        valid_until_us: int,
        capability_manifest: CapabilityManifest,
        integrity_digest: str,
    ) -> PolicyDecision:
        instance = object.__new__(cls)
        for field, value in (
            ("decision_id", decision_id),
            ("disposition", disposition),
            ("reason_codes", reason_codes),
            ("policy_version", policy_version),
            ("question_digest", question_digest),
            ("issued_at_us", issued_at_us),
            ("valid_until_us", valid_until_us),
            ("capability_manifest", capability_manifest),
            ("integrity_digest", integrity_digest),
        ):
            object.__setattr__(instance, field, value)
        return instance

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "disposition": self.disposition.value,
            "reason_codes": list(self.reason_codes),
            "policy_version": self.policy_version,
            "question_digest": self.question_digest,
            "issued_at_us": self.issued_at_us,
            "valid_until_us": self.valid_until_us,
            "capability_manifest": self.capability_manifest.to_dict(),
            "integrity_digest": self.integrity_digest,
        }


@dataclass(frozen=True)
class PolicyRevalidation:
    disposition: PolicyDisposition
    reason_code: str


@dataclass(frozen=True)
class GenesisSnapshot:
    snapshot_id: str
    knowledge_snapshot_id: str
    profile_id: str
    branch_id: str
    draft_id: str
    freeze_decision_id: str
    policy_decision_id: str
    freeze_basis_digest: str
    content_fingerprint: str
    predecessor_snapshot_id: str | None
    lineage_relation: str
    lineage_reason: str
    premise: GenesisPremise
    knowledge_member_count: int
    created_at_us: int
    source_freeze_basis_digest: str | None = None
    reviewed_definition: dict[str, Any] | None = None
    first_life_contract: dict | None = None


@dataclass(frozen=True, init=False)
class QualifiedRuntimeInput:
    qualification_id: str
    qualification_revision: int
    profile_id: str
    genesis_branch_id: str
    genesis_snapshot_id: str
    knowledge_snapshot_id: str
    policy_decision_ids: tuple[str, ...]
    capabilities: CapabilityManifest
    isolation_proof: IsolationProof
    provider_authority: str
    compatibility_proof: str
    predecessor_qualification_id: str | None
    publication_key: str
    published_at_us: int
    integrity_digest: str
    reviewed_chat_contract: dict | None = None
    first_life_contract: dict | None = None

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "QualifiedRuntimeInput can only be created by SubjectStudio publication"
        )

    @classmethod
    def _published(
        cls,
        *,
        _authority: object,
        **values: Any,
    ) -> QualifiedRuntimeInput:
        if _authority is not _QRI_PUBLICATION_TOKEN:
            raise TypeError(
                "QualifiedRuntimeInput requires SubjectStudio publication authority"
            )
        instance = object.__new__(cls)
        for field, value in values.items():
            object.__setattr__(instance, field, value)
        return instance

    def to_dict(self) -> dict[str, Any]:
        value = {
            "qualification_id": self.qualification_id,
            "qualification_revision": self.qualification_revision,
            "profile_id": self.profile_id,
            "genesis_branch_id": self.genesis_branch_id,
            "genesis_snapshot_id": self.genesis_snapshot_id,
            "knowledge_snapshot_id": self.knowledge_snapshot_id,
            "policy_decision_ids": list(self.policy_decision_ids),
            "capabilities": self.capabilities.to_dict(),
            "isolation_proof": self.isolation_proof.to_dict(),
            "provider_authority": self.provider_authority,
            "compatibility_proof": self.compatibility_proof,
            "predecessor_qualification_id": self.predecessor_qualification_id,
            "publication_key": self.publication_key,
            "published_at_us": self.published_at_us,
            "integrity_digest": self.integrity_digest,
        }
        if self.reviewed_chat_contract is not None:
            value["reviewed_chat_contract"] = self.reviewed_chat_contract
        if self.first_life_contract is not None:
            value["first_life_contract"] = self.first_life_contract
        return value


class PolicyKernel:
    """Deterministically evaluates rights, isolation, and M0 capabilities."""

    def __init__(self, *, clock: Callable[[], int] | None = None) -> None:
        self._clock = clock or _utc_microseconds

    def decide(
        self,
        question: PolicyQuestion,
        *,
        validity_us: int = 5_000_000,
    ) -> PolicyDecision:
        if not isinstance(question, PolicyQuestion):
            raise TypeError("PolicyKernel.decide requires a PolicyQuestion")
        if validity_us < 1:
            raise StudioRejected(
                "invalid-policy-validity",
                "policy validity must be positive",
            )
        reasons: list[str] = []
        reviewed = (
            (question.capability_manifest == CapabilityManifest.reviewed_character_dormant()
             or (question.capability_manifest == CapabilityManifest.reviewed_character_chat()
                 and matches_chat_source_contract(question.profile_source, question.reviewed_chat_contract))
             or (question.capability_manifest == CapabilityManifest.original_whole_chat()
                 and matches_whole_source_contract(question.profile_source, question.reviewed_chat_contract)))
            and is_reviewed_source(question.profile_source) and question.profile_source == question.genesis_source
            and question.isolation_proof.provenance_class == REVIEWED_CHARACTER_PROOF
            and question.isolation_proof.path_class in ("local-private-experimental", "system-temporary-experimental")
        )
        first_life = (question.capability_manifest in (CapabilityManifest.first_life_dormant(), CapabilityManifest.first_life_active())
            and is_first_life_source(question.profile_source) and question.profile_source == question.genesis_source
            and question.isolation_proof.provenance_class == REVIEWED_CHARACTER_PROOF
            and question.isolation_proof.path_class in ("local-private-experimental", "system-temporary-experimental"))
        reviewed = reviewed or first_life
        for source in (question.profile_source, question.genesis_source):
            if source.origin_kind != "project-original" and not reviewed:
                reasons.append("source-origin-denied")
            if not source.rights_confirmed:
                reasons.append("rights-declaration-missing")
            if (source.source_asset_refs or source.uses_disallowed_inheritance) and not reviewed:
                reasons.append("source-isolation-denied")
        allowed_isolation = {
            (ROOT_KIND, "process-temporary"),
            (EXPERIMENTAL_ROOT_KIND, "system-temporary-experimental"),
            (EXPERIMENTAL_ROOT_KIND, "local-private-experimental"),
        }
        if (
            question.isolation_proof.root_kind,
            question.isolation_proof.path_class,
        ) not in allowed_isolation:
            reasons.append("path-isolation-denied")
        if reasons:
            disposition = PolicyDisposition.DENIED
        elif first_life:
            disposition = PolicyDisposition.QUALIFIED
            reasons.append("first-life-active-qualified" if question.capability_manifest == CapabilityManifest.first_life_active() else "first-life-dormant-qualified")
        elif reviewed:
            disposition = PolicyDisposition.QUALIFIED
            reasons.append("private-reviewed-character-dormant-qualified")
        elif question.capability_manifest == CapabilityManifest.m0():
            disposition = PolicyDisposition.QUALIFIED
            reasons.append("m0-original-host-input-qualified")
        elif (
            question.capability_manifest
            == CapabilityManifest.deepseek_v4_flash_experimental()
        ):
            disposition = PolicyDisposition.QUALIFIED
            reasons.append("post-m0-deepseek-host-input-qualified")
        elif (
            question.capability_manifest
            == CapabilityManifest.accepted_artifact_dormant()
        ):
            disposition = PolicyDisposition.QUALIFIED
            reasons.append("post-m0-accepted-artifact-dormant-qualified")
        elif (
            question.capability_manifest
            == CapabilityManifest._local_first_test_double()
        ):
            disposition = PolicyDisposition.QUALIFIED
            reasons.append("post-m0-04-local-test-double-qualified")
        elif (
            question.capability_manifest
            == CapabilityManifest._local_llama_experimental()
        ):
            disposition = PolicyDisposition.QUALIFIED
            reasons.append("post-m0-04-local-llama-qualified")
        else:
            disposition = PolicyDisposition.UNAVAILABLE
            reasons.append("required-capability-unavailable")

        issued_at_us = int(self._clock())
        valid_until_us = issued_at_us + validity_us
        identity_basis = {
            "question_digest": question.question_digest,
            "policy_version": POLICY_VERSION,
            "issued_at_us": issued_at_us,
            "valid_until_us": valid_until_us,
            "disposition": disposition.value,
            "reason_codes": sorted(set(reasons)),
        }
        decision_id = str(
            uuid5(NAMESPACE_URL, f"dynamic-subject-agent:policy:{_digest(identity_basis)}")
        )
        integrity_basis = {
            **identity_basis,
            "decision_id": decision_id,
            "capability_manifest": question.capability_manifest.to_dict(),
        }
        return PolicyDecision._issue(
            decision_id=decision_id,
            disposition=disposition,
            reason_codes=tuple(sorted(set(reasons))),
            policy_version=POLICY_VERSION,
            question_digest=question.question_digest,
            issued_at_us=issued_at_us,
            valid_until_us=valid_until_us,
            capability_manifest=question.capability_manifest,
            integrity_digest=_digest(integrity_basis),
        )


    def revalidate(
        self,
        decision: PolicyDecision,
        question: PolicyQuestion,
    ) -> PolicyRevalidation:
        if decision.policy_version != POLICY_VERSION:
            return PolicyRevalidation(PolicyDisposition.DENIED, "policy-version-stale")
        if decision.question_digest != question.question_digest:
            return PolicyRevalidation(PolicyDisposition.DENIED, "policy-basis-stale")
        if int(self._clock()) > decision.valid_until_us:
            return PolicyRevalidation(PolicyDisposition.DENIED, "policy-expired")
        if decision.disposition is not PolicyDisposition.QUALIFIED:
            return PolicyRevalidation(decision.disposition, decision.reason_codes[0])
        return PolicyRevalidation(PolicyDisposition.QUALIFIED, "policy-current")


def _issue_corrective_policy_decision(
    predecessor: PolicyDecision,
    *,
    issued_at_us: int,
    validity_us: int,
    _authority: object,
) -> PolicyDecision:
    """Re-issue a qualified local policy from its non-content commitment."""

    if _authority is not _CORRECTIVE_LOCAL_LLAMA_SUCCESSOR_AUTHORITY:
        raise TypeError("corrective PolicyDecision requires private authority")
    if (
        not isinstance(predecessor, PolicyDecision)
        or predecessor.disposition is not PolicyDisposition.QUALIFIED
        or predecessor.capability_manifest
        != CapabilityManifest._local_llama_experimental()
        or not re.fullmatch(r"[0-9a-f]{64}", predecessor.question_digest)
        or int(issued_at_us) < 1
        or int(validity_us) < 1
    ):
        raise StudioRejected(
            "corrective-policy-basis-mismatch",
            "corrective policy requires the exact qualified structural predecessor",
        )
    issued = int(issued_at_us)
    valid_until = issued + int(validity_us)
    reasons = ("post-m0-06-corrective-local-llama-qualified",)
    identity_basis = {
        "question_digest": predecessor.question_digest,
        "policy_version": POLICY_VERSION,
        "issued_at_us": issued,
        "valid_until_us": valid_until,
        "disposition": PolicyDisposition.QUALIFIED.value,
        "reason_codes": list(reasons),
    }
    decision_id = str(
        uuid5(NAMESPACE_URL, f"dynamic-subject-agent:policy:{_digest(identity_basis)}")
    )
    integrity_basis = {
        **identity_basis,
        "decision_id": decision_id,
        "capability_manifest": predecessor.capability_manifest.to_dict(),
    }
    return PolicyDecision._issue(
        decision_id=decision_id,
        disposition=PolicyDisposition.QUALIFIED,
        reason_codes=reasons,
        policy_version=POLICY_VERSION,
        question_digest=predecessor.question_digest,
        issued_at_us=issued,
        valid_until_us=valid_until,
        capability_manifest=predecessor.capability_manifest,
        integrity_digest=_digest(integrity_basis),
    )


_PROFILE_DDL = (
    """
    CREATE TABLE store_manifest (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        root_id TEXT NOT NULL,
        store_id TEXT NOT NULL,
        store_kind TEXT NOT NULL CHECK (store_kind = 'profile'),
        schema_family TEXT NOT NULL,
        schema_version INTEGER NOT NULL,
        contract_version TEXT NOT NULL,
        persistence_version TEXT NOT NULL,
        root_epoch INTEGER NOT NULL,
        created_at_us INTEGER NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE profile_governance (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        governance_epoch INTEGER NOT NULL CHECK (governance_epoch >= 1),
        governance_state TEXT NOT NULL CHECK (
            governance_state IN ('active', 'clearing')
        ),
        data_control_scope_id TEXT
    ) STRICT
    """,
    """
    CREATE TABLE participant_profile (
        profile_id TEXT PRIMARY KEY,
        profile_json TEXT NOT NULL,
        profile_digest TEXT NOT NULL CHECK (length(profile_digest) = 64),
        created_at_us INTEGER NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE genesis_branch (
        branch_id TEXT PRIMARY KEY,
        profile_id TEXT NOT NULL REFERENCES participant_profile(profile_id),
        predecessor_snapshot_id TEXT,
        lineage_relation TEXT NOT NULL,
        lineage_reason TEXT NOT NULL,
        created_at_us INTEGER NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE genesis_draft (
        draft_id TEXT PRIMARY KEY,
        branch_id TEXT NOT NULL UNIQUE REFERENCES genesis_branch(branch_id),
        profile_id TEXT NOT NULL REFERENCES participant_profile(profile_id),
        current_revision INTEGER NOT NULL CHECK (current_revision >= 1),
        sealed_snapshot_id TEXT,
        created_at_us INTEGER NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE genesis_draft_revision (
        draft_id TEXT NOT NULL REFERENCES genesis_draft(draft_id),
        revision INTEGER NOT NULL CHECK (revision >= 1),
        premise_json TEXT NOT NULL,
        content_digest TEXT NOT NULL CHECK (length(content_digest) = 64),
        created_at_us INTEGER NOT NULL,
        PRIMARY KEY (draft_id, revision)
    ) STRICT
    """,
    """
    CREATE TABLE policy_decision (
        decision_id TEXT PRIMARY KEY,
        decision_json TEXT NOT NULL,
        integrity_digest TEXT NOT NULL CHECK (length(integrity_digest) = 64),
        created_at_us INTEGER NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE genesis_snapshot (
        snapshot_id TEXT PRIMARY KEY,
        draft_id TEXT NOT NULL UNIQUE REFERENCES genesis_draft(draft_id),
        branch_id TEXT NOT NULL UNIQUE REFERENCES genesis_branch(branch_id),
        freeze_decision_id TEXT NOT NULL UNIQUE,
        freeze_basis_digest TEXT NOT NULL CHECK (length(freeze_basis_digest) = 64),
        snapshot_json TEXT NOT NULL,
        snapshot_digest TEXT NOT NULL CHECK (length(snapshot_digest) = 64),
        created_at_us INTEGER NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE knowledge_snapshot (
        knowledge_snapshot_id TEXT PRIMARY KEY,
        genesis_snapshot_id TEXT NOT NULL UNIQUE REFERENCES genesis_snapshot(snapshot_id),
        member_count INTEGER NOT NULL CHECK (member_count >= 0 AND member_count <= 6),
        qualification TEXT NOT NULL CHECK (
            qualification IN ('qualified-original-empty', 'qualified-source-freeze', 'qualified-reviewed-character-asset')
        ),
        snapshot_digest TEXT NOT NULL CHECK (length(snapshot_digest) = 64),
        created_at_us INTEGER NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE knowledge_snapshot_member (
        knowledge_snapshot_id TEXT NOT NULL REFERENCES knowledge_snapshot(knowledge_snapshot_id),
        ordinal INTEGER NOT NULL CHECK (ordinal >= 0 AND ordinal < 6),
        entry_id TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        source_ref TEXT NOT NULL,
        evidence_quote TEXT,
        member_digest TEXT NOT NULL CHECK (length(member_digest) = 64),
        PRIMARY KEY (knowledge_snapshot_id, ordinal),
        UNIQUE (knowledge_snapshot_id, entry_id)
    ) STRICT
    """,
    """
    CREATE TABLE qri_publication (
        qualification_id TEXT PRIMARY KEY,
        publication_key TEXT NOT NULL UNIQUE,
        publication_digest TEXT NOT NULL CHECK (length(publication_digest) = 64),
        qri_json TEXT NOT NULL,
        integrity_digest TEXT NOT NULL CHECK (length(integrity_digest) = 64),
        created_at_us INTEGER NOT NULL
    ) STRICT
    """,
)


_PROFILE_TABLES = frozenset(
    {
        "genesis_branch",
        "genesis_draft",
        "genesis_draft_revision",
        "genesis_snapshot",
        "knowledge_snapshot",
        "knowledge_snapshot_member",
        "participant_profile",
        "policy_decision",
        "profile_governance",
        "qri_publication",
        "store_manifest",
    }
)


_ARTIFACT_SIDECAR_DDL = (
    """
    CREATE TABLE sidecar_manifest (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        root_id TEXT NOT NULL,
        store_kind TEXT NOT NULL CHECK (store_kind = 'accepted-artifact-snapshots'),
        schema_version INTEGER NOT NULL CHECK (schema_version = 1),
        created_at_us INTEGER NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE accepted_artifact (
        artifact_id TEXT PRIMARY KEY,
        profile_id TEXT NOT NULL,
        genesis_draft_id TEXT NOT NULL UNIQUE,
        knowledge_draft_id TEXT NOT NULL UNIQUE,
        artifact_json TEXT NOT NULL,
        artifact_digest TEXT NOT NULL CHECK (length(artifact_digest) = 64),
        provenance_digest TEXT NOT NULL CHECK (length(provenance_digest) = 64),
        created_at_us INTEGER NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE knowledge_draft (
        draft_id TEXT PRIMARY KEY,
        artifact_id TEXT NOT NULL UNIQUE REFERENCES accepted_artifact(artifact_id),
        current_revision INTEGER NOT NULL CHECK (current_revision = 1),
        sealed_snapshot_id TEXT,
        created_at_us INTEGER NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE knowledge_draft_revision (
        draft_id TEXT NOT NULL REFERENCES knowledge_draft(draft_id),
        revision INTEGER NOT NULL CHECK (revision = 1),
        content_json TEXT NOT NULL,
        content_digest TEXT NOT NULL CHECK (length(content_digest) = 64),
        created_at_us INTEGER NOT NULL,
        PRIMARY KEY (draft_id, revision)
    ) STRICT
    """,
    """
    CREATE TABLE freeze_decision (
        decision_id TEXT PRIMARY KEY,
        artifact_id TEXT NOT NULL REFERENCES accepted_artifact(artifact_id),
        scope TEXT NOT NULL CHECK (scope IN ('genesis', 'knowledge')),
        draft_id TEXT NOT NULL UNIQUE,
        decision_json TEXT NOT NULL,
        decision_digest TEXT NOT NULL CHECK (length(decision_digest) = 64),
        created_at_us INTEGER NOT NULL,
        UNIQUE (artifact_id, scope)
    ) STRICT
    """,
    """
    CREATE TABLE freeze_attempt (
        attempt_id TEXT PRIMARY KEY,
        artifact_id TEXT NOT NULL REFERENCES accepted_artifact(artifact_id),
        scope TEXT NOT NULL CHECK (scope IN ('genesis', 'knowledge')),
        decision_id TEXT NOT NULL UNIQUE REFERENCES freeze_decision(decision_id),
        draft_id TEXT NOT NULL UNIQUE,
        freeze_basis_digest TEXT NOT NULL CHECK (length(freeze_basis_digest) = 64),
        result TEXT NOT NULL CHECK (result = 'sealed'),
        created_at_us INTEGER NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE sealed_snapshot (
        snapshot_id TEXT PRIMARY KEY,
        artifact_id TEXT NOT NULL REFERENCES accepted_artifact(artifact_id),
        scope TEXT NOT NULL CHECK (scope IN ('genesis', 'knowledge')),
        draft_id TEXT NOT NULL UNIQUE,
        freeze_decision_id TEXT NOT NULL UNIQUE,
        freeze_attempt_id TEXT NOT NULL UNIQUE REFERENCES freeze_attempt(attempt_id),
        snapshot_json TEXT NOT NULL,
        snapshot_digest TEXT NOT NULL CHECK (length(snapshot_digest) = 64),
        created_at_us INTEGER NOT NULL,
        UNIQUE (artifact_id, scope)
    ) STRICT
    """,
    """
    CREATE TABLE snapshot_compatibility_proof (
        proof_id TEXT PRIMARY KEY,
        artifact_id TEXT NOT NULL UNIQUE REFERENCES accepted_artifact(artifact_id),
        proof_json TEXT NOT NULL,
        integrity_digest TEXT NOT NULL CHECK (length(integrity_digest) = 64),
        created_at_us INTEGER NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE activation_receipt (
        activation_id TEXT PRIMARY KEY,
        artifact_id TEXT NOT NULL UNIQUE REFERENCES accepted_artifact(artifact_id),
        plan_digest TEXT NOT NULL CHECK (length(plan_digest) = 64),
        receipt_json TEXT NOT NULL,
        integrity_digest TEXT NOT NULL CHECK (length(integrity_digest) = 64),
        visible_at_us INTEGER NOT NULL
    ) STRICT
    """,
)

_ARTIFACT_SIDECAR_TABLES = frozenset(
    {
        "accepted_artifact",
        "activation_receipt",
        "freeze_decision",
        "freeze_attempt",
        "knowledge_draft",
        "knowledge_draft_revision",
        "sealed_snapshot",
        "snapshot_compatibility_proof",
        "sidecar_manifest",
    }
)

_PROFILE_TABLES_V1 = _PROFILE_TABLES - {"knowledge_snapshot_member"}


_SOURCE_DRAFT_DDL = (
    """
    CREATE TABLE draft_manifest (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        root_id TEXT NOT NULL,
        store_kind TEXT NOT NULL CHECK (store_kind = 'source-character-draft'),
        schema_version INTEGER NOT NULL CHECK (schema_version = 1),
        created_at_us INTEGER NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE source_draft (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        draft_id TEXT NOT NULL UNIQUE,
        source_title TEXT NOT NULL,
        source_text TEXT NOT NULL,
        source_digest TEXT NOT NULL CHECK (length(source_digest) = 64),
        candidate_basis_digest TEXT NOT NULL CHECK (length(candidate_basis_digest) = 64),
        current_revision INTEGER NOT NULL CHECK (current_revision >= 1),
        created_at_us INTEGER NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE source_draft_revision (
        draft_id TEXT NOT NULL,
        revision INTEGER NOT NULL CHECK (revision >= 1),
        candidates_json TEXT NOT NULL,
        selection_digest TEXT NOT NULL CHECK (length(selection_digest) = 64),
        request_digest TEXT NOT NULL UNIQUE CHECK (length(request_digest) = 64),
        created_at_us INTEGER NOT NULL,
        PRIMARY KEY (draft_id, revision),
        FOREIGN KEY (draft_id) REFERENCES source_draft(draft_id) ON DELETE CASCADE
    ) STRICT
    """,
)

_SOURCE_DRAFT_TABLES = frozenset(
    {"draft_manifest", "source_draft", "source_draft_revision"}
)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


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


def _nearest_existing_ancestor(path: Path) -> Path:
    candidate = path
    while not candidate.exists() and candidate.parent != candidate:
        candidate = candidate.parent
    return candidate


def _validate_test_base(test_base: Path) -> Path:
    requested = Path(test_base)
    if not requested.is_absolute():
        raise StudioRejected(
            "canonical-root-not-allowed",
            "test root authority must be an explicit absolute path",
        )
    temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
    if _has_linklike_component(requested, temporary_root):
        raise StudioRejected(
            "canonical-root-not-allowed",
            "test root authority must not traverse a link or junction",
        )
    ancestor = _nearest_existing_ancestor(requested)
    try:
        resolved_ancestor = ancestor.resolve(strict=True)
    except OSError as error:
        raise StudioRejected(
            "canonical-root-not-allowed",
            "test root ancestor cannot be verified",
        ) from error
    under_temporary = _is_relative_to(resolved_ancestor, temporary_root)
    if not under_temporary:
        raise StudioRejected(
            "canonical-root-not-allowed",
            "M0 Host test stores may only be created under the process temporary root",
        )
    prospective = requested.resolve(strict=False)
    if not _is_relative_to(prospective, temporary_root):
        raise StudioRejected(
            "canonical-root-not-allowed",
            "requested test root escapes the process temporary root",
        )
    relative = prospective.relative_to(temporary_root)
    if any(part.casefold() in _RESERVED_TEST_PATH_SEGMENTS for part in relative.parts):
        raise StudioRejected(
            "canonical-root-not-allowed",
            "requested test root contains a reserved path segment",
        )
    try:
        requested.mkdir(parents=True, exist_ok=True)
        resolved = requested.resolve(strict=True)
    except OSError as error:
        raise StudioRejected(
            "canonical-root-not-allowed",
            "test root could not be prepared",
        ) from error
    if not _is_relative_to(resolved, temporary_root) or _has_linklike_component(
        requested,
        temporary_root,
    ):
        raise StudioRejected(
            "canonical-root-not-allowed",
            "test root escaped the allowed temporary boundary",
        )
    return resolved


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


def _validate_experimental_base(experiment_base: Path) -> Path:
    requested = Path(experiment_base)
    if (
        not requested.is_absolute()
        or not requested.anchor
        or requested.anchor.startswith("\\\\")
        or any(marker in str(requested) for marker in "*?[]%${}")
    ):
        raise StudioRejected(
            "experimental-root-not-allowed",
            "experimental root must be an exact absolute local path",
        )
    try:
        if str(UUID(requested.name)) != requested.name:
            raise ValueError
    except (ValueError, AttributeError):
        raise StudioRejected(
            "experimental-root-not-allowed",
            "experimental root leaf must be a canonical UUID",
        ) from None
    if any(
        part.casefold() in _RESERVED_TEST_PATH_SEGMENTS
        for part in requested.parts
    ):
        raise StudioRejected(
            "experimental-root-not-allowed",
            "experimental root contains a protected path segment",
        )
    try:
        anchor = Path(requested.anchor).resolve(strict=True)
        temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
    except OSError as error:
        raise StudioRejected(
            "experimental-root-not-allowed",
            "experimental root authority could not be resolved",
        ) from error
    if _has_linklike_component(requested, anchor):
        raise StudioRejected(
            "experimental-root-not-allowed",
            "experimental root must not traverse a link or junction",
        )
    ancestor = _nearest_existing_ancestor(requested)
    try:
        resolved_ancestor = ancestor.resolve(strict=True)
        prospective = requested.resolve(strict=False)
    except OSError as error:
        raise StudioRejected(
            "experimental-root-not-allowed",
            "experimental root ancestor cannot be verified",
        ) from error
    if not _is_relative_to(resolved_ancestor, anchor) or not _is_relative_to(
        prospective,
        anchor,
    ):
        raise StudioRejected(
            "experimental-root-not-allowed",
            "experimental root escapes its local volume",
        )
    if not _experimental_base_shape_allowed(prospective, temporary_root):
        raise StudioRejected(
            "experimental-root-not-allowed",
            "non-temporary experimental roots require the dedicated local layout",
        )
    if requested.exists():
        if _is_linklike(requested) or not requested.is_dir():
            raise StudioRejected(
                "experimental-root-not-allowed",
                "experimental root must be a plain directory",
            )
        try:
            populated = next(requested.iterdir(), None) is not None
        except OSError as error:
            raise StudioRejected(
                "experimental-root-not-allowed",
                "experimental root could not be inspected",
            ) from error
        raise StudioRejected(
            (
                "experimental-root-not-empty"
                if populated
                else "experimental-root-already-exists"
            ),
            "experimental root must be newly and exclusively created",
        )
    try:
        requested.mkdir(parents=True, exist_ok=False)
        resolved = requested.resolve(strict=True)
    except OSError as error:
        raise StudioFailedClosed(
            "experimental-root-create-failed",
            "experimental root could not be exclusively created",
        ) from error
    if (
        resolved != prospective
        or _has_linklike_component(requested, anchor)
        or not _experimental_base_shape_allowed(resolved, temporary_root)
    ):
        raise StudioRejected(
            "experimental-root-not-allowed",
            "experimental root changed identity during creation",
        )
    return resolved


def _validate_reserved_artifact_activation_base(
    experiment_base: Path,
    *,
    create: bool,
) -> Path:
    """Validate the one reserved Post-M0 artifact-activation bundle layout."""

    requested = Path(experiment_base)
    if (
        not requested.is_absolute()
        or not requested.anchor
        or requested.anchor.startswith("\\\\")
        or any(marker in str(requested) for marker in "*?[]%${}")
    ):
        raise StudioRejected(
            "experimental-root-not-allowed",
            "artifact activation root must be an exact absolute local path",
        )
    try:
        if str(UUID(requested.name)) != requested.name:
            raise ValueError
        anchor = Path(requested.anchor).resolve(strict=True)
        temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
    except (OSError, ValueError, AttributeError) as error:
        raise StudioRejected(
            "experimental-root-not-allowed",
            "artifact activation root identity cannot be verified",
        ) from error
    prospective = requested.resolve(strict=False)
    dedicated_parent = tuple(
        part.casefold() for part in prospective.parent.parts[-3:]
    ) == ("dynamicsubjectagent", "post-m0", "artifact-activations")
    if (
        not (_is_relative_to(prospective, temporary_root) or dedicated_parent)
        or any(
            part.casefold() in _RESERVED_TEST_PATH_SEGMENTS
            for part in prospective.parts
        )
        or _has_linklike_component(requested, anchor)
    ):
        raise StudioRejected(
            "experimental-root-not-allowed",
            "artifact activation root is outside its dedicated local layout",
        )
    ancestor = _nearest_existing_ancestor(requested)
    try:
        if not _is_relative_to(ancestor.resolve(strict=True), anchor):
            raise OSError("ancestor escapes local volume")
        if create:
            requested.mkdir(parents=True, exist_ok=True)
        if not requested.exists():
            return prospective
        resolved = requested.resolve(strict=True)
    except OSError as error:
        raise StudioRejected(
            "experimental-root-not-allowed",
            "artifact activation root cannot be prepared or resolved",
        ) from error
    if (
        resolved != prospective
        or not requested.is_dir()
        or _is_linklike(requested)
        or _has_linklike_component(requested, anchor)
    ):
        raise StudioRejected(
            "experimental-root-not-allowed",
            "artifact activation root changed identity",
        )
    return resolved


def _validate_artifact_activation_gate_parent(path: Path) -> Path:
    requested = Path(path)
    if not requested.is_absolute() or any(
        marker in str(requested) for marker in "*?[]%${}"
    ):
        raise StudioRejected(
            "artifact-activation-gate-invalid",
            "activation gate root must be exact and absolute",
        )
    try:
        anchor = Path(requested.anchor).resolve(strict=True)
        temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
        prospective = requested.resolve(strict=False)
    except OSError as error:
        raise StudioRejected(
            "artifact-activation-gate-invalid",
            "activation gate root cannot be resolved",
        ) from error
    dedicated = tuple(part.casefold() for part in prospective.parts[-3:]) == (
        "dynamicsubjectagent",
        "post-m0",
        "artifact-activation-gates",
    )
    if (
        not (_is_relative_to(prospective, temporary_root) or dedicated)
        or _has_linklike_component(requested, anchor)
    ):
        raise StudioRejected(
            "artifact-activation-gate-invalid",
            "activation gate root is outside its dedicated local layout",
        )
    try:
        requested.mkdir(parents=True, exist_ok=True)
        resolved = requested.resolve(strict=True)
    except OSError as error:
        raise StudioRejected(
            "artifact-activation-gate-invalid",
            "activation gate root cannot be prepared",
        ) from error
    if resolved != prospective or _has_linklike_component(requested, anchor):
        raise StudioRejected(
            "artifact-activation-gate-invalid",
            "activation gate root changed identity",
        )
    return resolved


def _validate_existing_root(
    root: Path,
    expected_root_id: str,
    expected_root_kind: str = ROOT_KIND,
) -> Path:
    if not root.is_absolute():
        raise StudioRejected(
            "canonical-root-not-allowed",
            "Studio root must be absolute",
        )
    try:
        resolved = root.resolve(strict=True)
        temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
        anchor = Path(root.anchor).resolve(strict=True)
    except OSError as error:
        raise StudioRejected(
            "canonical-root-not-allowed",
            "Studio root cannot be resolved",
        ) from error
    if expected_root_kind not in {ROOT_KIND, EXPERIMENTAL_ROOT_KIND}:
        raise StudioRejected(
            "root-kind-not-allowed",
            "Studio root kind is not recognized",
        )
    link_stop = temporary_root if expected_root_kind == ROOT_KIND else anchor
    if _has_linklike_component(root, link_stop):
        raise StudioRejected(
            "canonical-root-not-allowed",
            "Studio root must not traverse a link or junction",
        )
    if expected_root_kind == ROOT_KIND and not _is_relative_to(
        resolved,
        temporary_root,
    ):
        raise StudioRejected(
            "canonical-root-not-allowed",
            "M0 Host store is outside temporary authority",
        )
    if resolved.name != expected_root_id or (
        resolved.parent.name != "roots"
        or resolved.parent.parent.name != "mature-runtime-m0"
    ):
        raise StudioRejected(
            "root-identity-mismatch",
            "Studio root layout does not match its identity",
        )
    if expected_root_kind == EXPERIMENTAL_ROOT_KIND:
        experiment_base = resolved.parent.parent.parent
        try:
            if str(UUID(experiment_base.name)) != experiment_base.name:
                raise ValueError
        except (ValueError, AttributeError):
            raise StudioRejected(
                "root-identity-mismatch",
                "experimental root does not have a canonical experiment identity",
            ) from None
        if (
            any(
                part.casefold() in _RESERVED_TEST_PATH_SEGMENTS
                for part in experiment_base.parts
            )
                or not (
                    _experimental_base_shape_allowed(
                        experiment_base,
                        temporary_root,
                    )
                    or _reserved_artifact_activation_base_shape_allowed(
                        experiment_base
                    )
                )
            ):
            raise StudioRejected(
                "canonical-root-not-allowed",
                "experimental Studio root is outside dedicated authority",
            )
    for candidate in (resolved, resolved / "root.identity"):
        if _is_linklike(candidate):
            raise StudioRejected(
                "canonical-root-not-allowed",
                "Studio root must not contain symbolic links",
            )
    return resolved


def _sqlite_uri(path: Path, mode: str) -> str:
    return f"{path.resolve().as_uri()}?mode={mode}"


def _connect_new(path: Path) -> sqlite3.Connection:
    if path.exists():
        raise StudioConflict("store-already-exists", "ProfileStore already exists")
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
        connection.row_factory = sqlite3.Row
        if str(journal_mode).lower() != "delete":
            raise StudioFailedClosed(
                "connection-profile-mismatch",
                "ProfileStore did not enter DELETE journal mode",
            )
        return connection
    except StudioProblem:
        raise
    except sqlite3.Error as error:
        raise StudioFailedClosed(
            "store-create-failed",
            "ProfileStore could not be created",
        ) from error


def _connect_existing(path: Path) -> sqlite3.Connection:
    if not path.is_file() or path.is_symlink() or path.stat().st_nlink != 1:
        raise StudioFailedClosed(
            "store-missing",
            "ProfileStore is missing or has a linked identity",
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
        connection.row_factory = sqlite3.Row
        return connection
    except sqlite3.Error as error:
        raise StudioFailedClosed(
            "store-open-failed",
            "ProfileStore could not be opened",
        ) from error


def _begin(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")


def _commit(connection: sqlite3.Connection) -> None:
    connection.execute("COMMIT")


def _rollback_if_needed(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.execute("ROLLBACK")


def _write_root_identity(location: StudioRootRef) -> None:
    identity = {
        "format": ROOT_FORMAT,
        "root_epoch": ROOT_EPOCH,
        "root_id": location.root_id,
        "root_kind": location.root_kind,
    }
    with (location.root / "root.identity").open(
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


def _read_root_identity(location: StudioRootRef) -> None:
    identity_path = location.root / "root.identity"
    if (
        not identity_path.is_file()
        or identity_path.is_symlink()
        or identity_path.stat().st_nlink != 1
    ):
        raise StudioFailedClosed(
            "root-identity-mismatch",
            "Studio root identity is absent or linked",
        )
    try:
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise StudioFailedClosed(
            "root-identity-mismatch",
            "Studio root identity is unreadable",
        ) from error
    expected = {
        "format": ROOT_FORMAT,
        "root_epoch": ROOT_EPOCH,
        "root_id": location.root_id,
        "root_kind": location.root_kind,
    }
    if identity != expected:
        raise StudioFailedClosed(
            "root-identity-mismatch",
            "Studio root identity does not match its reference",
        )


def _bootstrap_profile(location: StudioRootRef) -> None:
    connection = _connect_new(location.profile_database)
    try:
        _begin(connection)
        for statement in _PROFILE_DDL:
            connection.execute(statement)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
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
            ) VALUES (1, ?, ?, 'profile', ?, ?, ?, ?, ?, ?)
            """,
            (
                location.root_id,
                location.profile_store_id,
                PROFILE_SCHEMA_FAMILY,
                SCHEMA_VERSION,
                CONTRACT_VERSION,
                PERSISTENCE_VERSION,
                ROOT_EPOCH,
                _utc_microseconds(),
            ),
        )
        connection.execute(
            """
            INSERT INTO profile_governance VALUES (1, 1, 'active', NULL)
            """
        )
        _commit(connection)
    except Exception:
        _rollback_if_needed(connection)
        raise
    finally:
        connection.close()


def _verify_store(location: StudioRootRef, connection: sqlite3.Connection) -> None:
    journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
    synchronous = int(connection.execute("PRAGMA synchronous").fetchone()[0])
    foreign_keys = int(connection.execute("PRAGMA foreign_keys").fetchone()[0])
    secure_delete = int(connection.execute("PRAGMA secure_delete").fetchone()[0])
    if (journal_mode, synchronous, foreign_keys, secure_delete) != (
        "delete",
        3,
        1,
        1,
    ):
        raise StudioFailedClosed(
            "connection-profile-mismatch",
            "ProfileStore connection profile is invalid",
        )
    manifest = connection.execute(
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
    schema_version = None if manifest is None else int(manifest[4])
    user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if (
        manifest is None
        or tuple(manifest[:4])
        != (
            location.root_id,
            location.profile_store_id,
            "profile",
            PROFILE_SCHEMA_FAMILY,
        )
        or tuple(manifest[5:])
        != (CONTRACT_VERSION, PERSISTENCE_VERSION, ROOT_EPOCH)
        or schema_version not in {_LEGACY_SCHEMA_VERSION, SCHEMA_VERSION}
        or user_version != schema_version
    ):
        raise StudioFailedClosed(
            "store-identity-mismatch",
            "ProfileStore manifest does not match its reference",
        )
    table_rows = connection.execute(
        """
        SELECT name
        FROM sqlite_schema
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()
    expected_tables = (
        _PROFILE_TABLES
        if schema_version == SCHEMA_VERSION
        else _PROFILE_TABLES_V1
    )
    if {str(row[0]) for row in table_rows} != expected_tables:
        raise StudioFailedClosed(
            "schema-shape-mismatch",
            "ProfileStore schema does not match the M0 contract",
        )
    integrity = connection.execute("PRAGMA integrity_check").fetchone()
    foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    if integrity is None or str(integrity[0]).lower() != "ok" or foreign_key_errors:
        raise StudioFailedClosed(
            "store-integrity-failed",
            "ProfileStore integrity check failed",
        )


def _require_profile_active(connection: sqlite3.Connection) -> None:
    try:
        row = connection.execute(
            """
            SELECT governance_epoch, governance_state, data_control_scope_id
            FROM profile_governance
            WHERE singleton = 1
            """
        ).fetchone()
    except sqlite3.Error as error:
        raise StudioFailedClosed(
            "profile-governance-invalid",
            "Profile governance state is unreadable",
        ) from error
    if row is None or int(row[0]) < 1:
        raise StudioFailedClosed(
            "profile-governance-invalid",
            "Profile governance state is incomplete",
        )
    if str(row[1]) != "active" or row[2] is not None:
        raise StudioRejected(
            "governance-clearing",
            "Profile authority was withdrawn for active-copy clearing",
        )


_FaultHook = Callable[[StudioFaultPoint], None]


class SubjectStudio:
    """Deep Host-authoring Module for draft, seal, and QRI publication."""

    def __init__(
        self,
        location: StudioRootRef,
        writer: sqlite3.Connection,
        policy_kernel: PolicyKernel,
        fault_hook: _FaultHook | None,
        *,
        readonly: bool = False,
    ) -> None:
        self._location = location
        self._writer = writer
        self._policy_kernel = policy_kernel
        self._fault_hook = fault_hook
        self._readonly = bool(readonly)
        self._closed = False

    @property
    def location(self) -> StudioRootRef:
        return self._location

    @property
    def isolation_proof(self) -> IsolationProof:
        if self._location.root_kind == EXPERIMENTAL_ROOT_KIND:
            experiment_base = self._location.root.parents[2]
            temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
            path_class = (
                "system-temporary-experimental"
                if _is_relative_to(experiment_base.resolve(strict=True), temporary_root)
                else "local-private-experimental"
            )
        else:
            path_class = "process-temporary"
        return IsolationProof(
            root_id=self._location.root_id,
            root_kind=self._location.root_kind,
            path_class=path_class,
            provenance_class="project-original-only",
        )

    @classmethod
    def create(
        cls,
        local_product_base: Path,
        *,
        policy_kernel: PolicyKernel,
    ) -> SubjectStudio:
        """Create one production Studio under the dedicated local-product layout."""

        if not isinstance(policy_kernel, PolicyKernel):
            raise TypeError("SubjectStudio requires a PolicyKernel")
        base = _validate_experimental_base(Path(local_product_base))
        return cls._create_at_base(
            base,
            root_kind=EXPERIMENTAL_ROOT_KIND,
            policy_kernel=policy_kernel,
        )

    @classmethod
    def open_or_create_source_identity(
        cls,
        product_parent: Path,
        *,
        freeze_basis_digest: str,
        policy_kernel: PolicyKernel,
    ) -> tuple[SubjectStudio, Path]:
        """Open or create the deterministic Studio hidden behind one Freeze Basis."""

        basis = _canonical_sha256(freeze_basis_digest, "freeze_basis_digest")
        if not isinstance(policy_kernel, PolicyKernel):
            raise TypeError("SubjectStudio requires a PolicyKernel")
        experiment_id = str(
            uuid5(
                NAMESPACE_URL,
                "dynamic-subject-agent:source-experiment:" + basis,
            )
        )
        experiment_base = Path(product_parent) / experiment_id
        root_id = str(
            uuid5(NAMESPACE_URL, "dynamic-subject-agent:source-studio:" + basis)
        )
        profile_store_id = str(
            uuid5(NAMESPACE_URL, "dynamic-subject-agent:source-profile-store:" + basis)
        )
        location = StudioRootRef(
            root_path=str(
                experiment_base / "mature-runtime-m0" / "roots" / root_id
            ),
            root_id=root_id,
            profile_store_id=profile_store_id,
            root_kind=EXPERIMENTAL_ROOT_KIND,
        )
        if location.root.exists():
            return cls.open(location, policy_kernel=policy_kernel), experiment_base
        base = _validate_experimental_base(experiment_base)
        return (
            cls._create_at_base(
                base,
                root_kind=EXPERIMENTAL_ROOT_KIND,
                policy_kernel=policy_kernel,
                root_id=root_id,
                profile_store_id=profile_store_id,
            ),
            experiment_base,
        )

    @classmethod
    def create_test(
        cls,
        test_base: Path,
        *,
        policy_kernel: PolicyKernel,
    ) -> SubjectStudio:
        if not isinstance(policy_kernel, PolicyKernel):
            raise TypeError("SubjectStudio requires a PolicyKernel")
        base = _validate_test_base(Path(test_base))
        return cls._create_at_base(
            base,
            root_kind=ROOT_KIND,
            policy_kernel=policy_kernel,
        )

    @classmethod
    def _create_experimental(
        cls,
        experiment_base: Path,
        *,
        policy_kernel: PolicyKernel,
        _authority: object,
    ) -> SubjectStudio:
        if _authority is not _EXPERIMENTAL_PREVIEW_TOKEN:
            raise TypeError(
                "experimental Studio creation requires preview-runner authority"
            )
        if not isinstance(policy_kernel, PolicyKernel):
            raise TypeError("SubjectStudio requires a PolicyKernel")
        base = _validate_experimental_base(Path(experiment_base))
        return cls._create_at_base(
            base,
            root_kind=EXPERIMENTAL_ROOT_KIND,
            policy_kernel=policy_kernel,
        )

    @classmethod
    def _create_reserved_experimental(
        cls,
        experiment_base: Path,
        *,
        root_id: str,
        profile_store_id: str,
        policy_kernel: PolicyKernel,
        _authority: object,
    ) -> SubjectStudio:
        if _authority is not _CONFIRMED_EXPERIMENT_PREPARATION_TOKEN:
            raise TypeError(
                "reserved experimental creation requires preparation authority"
            )
        if not isinstance(policy_kernel, PolicyKernel):
            raise TypeError("SubjectStudio requires a PolicyKernel")
        base = _validate_experimental_base(Path(experiment_base))
        return cls._create_at_base(
            base,
            root_kind=EXPERIMENTAL_ROOT_KIND,
            policy_kernel=policy_kernel,
            root_id=root_id,
            profile_store_id=profile_store_id,
        )

    @classmethod
    def _create_at_base(
        cls,
        base: Path,
        *,
        root_kind: str,
        policy_kernel: PolicyKernel,
        root_id: str | None = None,
        profile_store_id: str | None = None,
    ) -> SubjectStudio:
        root_id = (
            str(uuid4())
            if root_id is None
            else _canonical_uuid(root_id, "root_id")
        )
        profile_store_id = (
            str(uuid4())
            if profile_store_id is None
            else _canonical_uuid(profile_store_id, "profile_store_id")
        )
        root = base / "mature-runtime-m0" / "roots" / root_id
        root.parent.mkdir(parents=True, exist_ok=True)
        try:
            root.mkdir()
        except OSError as error:
            raise StudioFailedClosed(
                "canonical-root-create-failed",
                "new Studio root could not be created",
            ) from error
        location = StudioRootRef(
            root_path=str(root),
            root_id=root_id,
            profile_store_id=profile_store_id,
            root_kind=root_kind,
        )
        try:
            _write_root_identity(location)
            _bootstrap_profile(location)
            return cls.open(location, policy_kernel=policy_kernel)
        except Exception as error:
            if root.exists() and _is_relative_to(root.resolve(), base):
                shutil.rmtree(root)
            if isinstance(error, StudioProblem):
                raise
            raise StudioFailedClosed(
                "canonical-root-bootstrap-failed",
                "new Studio root could not be bootstrapped",
            ) from error

    @classmethod
    def open(
        cls,
        location: StudioRootRef,
        *,
        policy_kernel: PolicyKernel,
        _fault_hook: _FaultHook | None = None,
    ) -> SubjectStudio:
        if not isinstance(location, StudioRootRef):
            raise TypeError("SubjectStudio.open requires a StudioRootRef")
        if not isinstance(policy_kernel, PolicyKernel):
            raise TypeError("SubjectStudio.open requires a PolicyKernel")
        _validate_existing_root(
            location.root,
            location.root_id,
            location.root_kind,
        )
        _read_root_identity(location)
        writer = _connect_existing(location.profile_database)
        try:
            _verify_store(location, writer)
            _require_profile_active(writer)
        except Exception:
            writer.close()
            raise
        return cls(location, writer, policy_kernel, _fault_hook)

    def close(self) -> None:
        if not self._closed:
            self._writer.close()
            self._closed = True

    def _require_open(self) -> None:
        if self._closed:
            raise StudioFailedClosed("studio-closed", "SubjectStudio is closed")

    def _require_authority(self) -> None:
        self._require_open()
        if self._readonly:
            raise StudioRejected(
                "studio-readonly",
                "read-only SubjectStudio cannot perform an authority write",
            )
        _validate_existing_root(
            self._location.root,
            self._location.root_id,
            self._location.root_kind,
        )
        _read_root_identity(self._location)
        _verify_store(self._location, self._writer)
        _require_profile_active(self._writer)

    def _hit(self, point: StudioFaultPoint) -> None:
        if self._fault_hook is not None:
            self._fault_hook(point)

    @property
    def _artifact_sidecar_database(self) -> Path:
        return (
            self._location.root
            / "accepted-artifact-snapshots"
            / "snapshot-authority.sqlite3"
        )

    def _open_artifact_sidecar(
        self,
        *,
        create: bool,
    ) -> sqlite3.Connection:
        database = self._artifact_sidecar_database
        if not database.exists() and not create:
            raise StudioRejected(
                "accepted-artifact-not-found",
                "accepted artifact snapshot authority does not exist",
            )
        root = self._location.root.resolve(strict=True)
        if _has_linklike_component(database.parent, root) or not _is_relative_to(
            database.resolve(strict=False),
            root,
        ):
            raise StudioRejected(
                "accepted-artifact-store-invalid",
                "accepted artifact snapshot authority escapes the Studio root",
            )
        if create:
            database.parent.mkdir(parents=False, exist_ok=True)
            if _has_linklike_component(database.parent, root) or not _is_relative_to(
                database.parent.resolve(strict=True),
                root,
            ):
                raise StudioRejected(
                    "accepted-artifact-store-invalid",
                    "accepted artifact snapshot authority changed path identity",
                )
        if database.exists() and (
            not database.is_file()
            or database.is_symlink()
            or database.stat().st_nlink != 1
        ):
            raise StudioFailedClosed(
                "accepted-artifact-store-invalid",
                "accepted artifact snapshot authority has an unsafe identity",
            )
        try:
            connection = sqlite3.connect(
                _sqlite_uri(
                    database,
                    "rwc" if create else ("ro" if self._readonly else "rw"),
                ),
                uri=True,
                autocommit=True,
                timeout=2.0,
                check_same_thread=True,
            )
            connection.execute("PRAGMA synchronous = EXTRA")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA secure_delete = ON")
            connection.execute("PRAGMA busy_timeout = 2000")
            if self._readonly:
                connection.execute("PRAGMA query_only = ON")
            connection.row_factory = sqlite3.Row
            if create:
                _begin(connection)
                for statement in _ARTIFACT_SIDECAR_DDL:
                    connection.execute(statement.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1))
                manifest = connection.execute(
                    "SELECT root_id FROM sidecar_manifest WHERE singleton = 1"
                ).fetchone()
                if manifest is None:
                    connection.execute(
                        """
                        INSERT INTO sidecar_manifest (
                            singleton, root_id, store_kind, schema_version, created_at_us
                        ) VALUES (1, ?, 'accepted-artifact-snapshots', 1, ?)
                        """,
                        (self._location.root_id, _utc_microseconds()),
                    )
                _commit(connection)
            table_rows = connection.execute(
                """
                SELECT name FROM sqlite_schema
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            ).fetchall()
            manifest = connection.execute(
                """
                SELECT root_id, store_kind, schema_version
                FROM sidecar_manifest WHERE singleton = 1
                """
            ).fetchone()
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
            if (
                {str(row[0]) for row in table_rows} != _ARTIFACT_SIDECAR_TABLES
                or manifest is None
                or tuple(manifest)
                != (self._location.root_id, "accepted-artifact-snapshots", 1)
                or integrity is None
                or str(integrity[0]).lower() != "ok"
                or foreign_key_errors
            ):
                raise StudioFailedClosed(
                    "accepted-artifact-store-invalid",
                    "accepted artifact snapshot authority failed verification",
                )
            return connection
        except StudioProblem:
            try:
                connection.close()
            except UnboundLocalError:
                pass
            raise
        except (OSError, sqlite3.Error) as error:
            try:
                connection.close()
            except UnboundLocalError:
                pass
            raise StudioFailedClosed(
                "accepted-artifact-store-unavailable",
                "accepted artifact snapshot authority is unavailable",
            ) from error

    @property
    def _source_draft_database(self) -> Path:
        return (
            self._location.root
            / "source-character-draft"
            / "draft-authority.sqlite3"
        )

    def _open_source_draft_sidecar(self, *, create: bool) -> sqlite3.Connection:
        database = self._source_draft_database
        if not database.exists() and not create:
            raise StudioRejected(
                "source-draft-not-found",
                "source character draft authority does not exist",
            )
        root = self._location.root.resolve(strict=True)
        if _has_linklike_component(database.parent, root) or not _is_relative_to(
            database.resolve(strict=False),
            root,
        ):
            raise StudioRejected(
                "source-draft-store-invalid",
                "source character draft authority escapes the Studio root",
            )
        if create:
            try:
                database.parent.mkdir(parents=False, exist_ok=True)
            except OSError as error:
                raise StudioFailedClosed(
                    "source-draft-store-unavailable",
                    "source character draft directory cannot be created",
                ) from error
            if _has_linklike_component(database.parent, root) or not _is_relative_to(
                database.parent.resolve(strict=True),
                root,
            ):
                raise StudioRejected(
                    "source-draft-store-invalid",
                    "source character draft authority changed path identity",
                )
        if database.exists() and (
            not database.is_file()
            or database.is_symlink()
            or database.stat().st_nlink != 1
        ):
            raise StudioFailedClosed(
                "source-draft-store-invalid",
                "source character draft authority has an unsafe identity",
            )
        try:
            connection = sqlite3.connect(
                _sqlite_uri(
                    database,
                    "rwc" if create else ("ro" if self._readonly else "rw"),
                ),
                uri=True,
                autocommit=True,
                timeout=2.0,
                check_same_thread=True,
            )
            connection.execute("PRAGMA synchronous = EXTRA")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA secure_delete = ON")
            connection.execute("PRAGMA busy_timeout = 2000")
            if self._readonly:
                connection.execute("PRAGMA query_only = ON")
            connection.row_factory = sqlite3.Row
            if create:
                _begin(connection)
                for statement in _SOURCE_DRAFT_DDL:
                    connection.execute(
                        statement.replace(
                            "CREATE TABLE",
                            "CREATE TABLE IF NOT EXISTS",
                            1,
                        )
                    )
                manifest = connection.execute(
                    "SELECT root_id FROM draft_manifest WHERE singleton = 1"
                ).fetchone()
                if manifest is None:
                    connection.execute(
                        """
                        INSERT INTO draft_manifest (
                            singleton, root_id, store_kind, schema_version, created_at_us
                        ) VALUES (1, ?, 'source-character-draft', 1, ?)
                        """,
                        (self._location.root_id, _utc_microseconds()),
                    )
                _commit(connection)
            table_rows = connection.execute(
                """
                SELECT name FROM sqlite_schema
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            ).fetchall()
            manifest = connection.execute(
                """
                SELECT root_id, store_kind, schema_version
                FROM draft_manifest WHERE singleton = 1
                """
            ).fetchone()
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            foreign_key_errors = connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            if (
                {str(row[0]) for row in table_rows} != _SOURCE_DRAFT_TABLES
                or manifest is None
                or tuple(manifest)
                != (self._location.root_id, "source-character-draft", 1)
                or integrity is None
                or str(integrity[0]).lower() != "ok"
                or foreign_key_errors
            ):
                raise StudioFailedClosed(
                    "source-draft-store-invalid",
                    "source character draft authority failed verification",
                )
            return connection
        except StudioProblem:
            try:
                connection.close()
            except UnboundLocalError:
                pass
            raise
        except (OSError, sqlite3.Error) as error:
            try:
                connection.close()
            except UnboundLocalError:
                pass
            raise StudioFailedClosed(
                "source-draft-store-unavailable",
                "source character draft authority is unavailable",
            ) from error

    def source_draft(self, command: object) -> SourceDraftResponse:
        self._require_open()
        if not isinstance(command, SourceDraftCommand):
            return SourceDraftResponse(
                SourceDraftStatus.REJECTED,
                problem_code="typed-source-draft-command-required",
            )
        try:
            if command.kind is SourceDraftCommandKind.QUERY:
                if command.save_request is not None or command.delete_confirmed:
                    return SourceDraftResponse(
                        SourceDraftStatus.REJECTED,
                        problem_code="source-draft-command-shape-invalid",
                    )
                return self._query_source_draft()
            if command.kind is SourceDraftCommandKind.SAVE:
                if command.delete_confirmed:
                    return SourceDraftResponse(
                        SourceDraftStatus.REJECTED,
                        problem_code="source-draft-command-shape-invalid",
                    )
                return self._save_source_draft(command.save_request)
            if command.kind is SourceDraftCommandKind.DELETE:
                if command.save_request is not None:
                    return SourceDraftResponse(
                        SourceDraftStatus.REJECTED,
                        problem_code="source-draft-command-shape-invalid",
                    )
                return self._delete_source_draft(
                    confirmed=command.delete_confirmed,
                )
            return SourceDraftResponse(
                SourceDraftStatus.REJECTED,
                problem_code="source-draft-command-kind-invalid",
            )
        except StudioConflict:
            return SourceDraftResponse(
                SourceDraftStatus.CONFLICT,
                problem_code="source-draft-revision-conflict",
            )
        except StudioProblem:
            return SourceDraftResponse(
                SourceDraftStatus.FAILED_CLOSED,
                problem_code="source-draft-store-failed-closed",
            )
        except Exception:
            return SourceDraftResponse(
                SourceDraftStatus.FAILED_CLOSED,
                problem_code="source-draft-store-failed-closed",
            )

    def preview_source_freeze_mapping(
        self,
        request: object,
    ) -> SourceFreezeMappingResponse:
        self._require_open()
        draft = self.source_draft(SourceDraftCommand.query())
        return self._validated_source_freeze_mapping(draft, request)

    def _validated_source_freeze_mapping(
        self,
        draft: SourceDraftResponse,
        request: object,
    ) -> SourceFreezeMappingResponse:
        if draft.status is SourceDraftStatus.ABSENT:
            return SourceFreezeMappingResponse(SourceFreezeMappingStatus.ABSENT)
        if draft.status is not SourceDraftStatus.AVAILABLE or draft.view is None:
            return SourceFreezeMappingResponse(
                SourceFreezeMappingStatus.FAILED_CLOSED,
                problem_code="source-freeze-draft-unavailable",
            )
        mapping = prepare_source_freeze_mapping(draft.view, request)
        if mapping.status is not SourceFreezeMappingStatus.AVAILABLE:
            return mapping
        assert mapping.view is not None
        try:
            source = SourceDeclaration.project_original(rights_confirmed=True)
            profile = ParticipantProfile(
                profile_id=mapping.view.profile.profile_id,
                display_name=mapping.view.profile.display_name,
                identity_core=mapping.view.profile.identity_core,
                source=source,
            )
            premise = GenesisPremise(
                subject_identity=mapping.view.genesis.subject_identity,
                canon_start=mapping.view.genesis.canon_start,
                initial_relationship_premise=(
                    mapping.view.genesis.initial_relationship_premise
                ),
                source=source,
            )
        except StudioProblem:
            return SourceFreezeMappingResponse(
                SourceFreezeMappingStatus.REJECTED,
                problem_code="source-freeze-studio-mapping-invalid",
            )
        if (
            profile.display_name != mapping.view.profile.display_name
            or profile.identity_core != mapping.view.profile.identity_core
            or premise.subject_identity != mapping.view.genesis.subject_identity
            or premise.canon_start != mapping.view.genesis.canon_start
            or premise.initial_relationship_premise
            != mapping.view.genesis.initial_relationship_premise
        ):
            return SourceFreezeMappingResponse(
                SourceFreezeMappingStatus.FAILED_CLOSED,
                problem_code="source-freeze-studio-normalization-changed",
            )
        return mapping

    def execute_locked_source_freeze(
        self,
        request: object,
        publisher: Callable[[SourceFreezeMappingView], Any],
    ) -> Any:
        """Hold the Source Draft revision stable through the irreversible publisher."""

        self._require_authority()
        if not callable(publisher):
            raise TypeError("publisher must be callable")
        if not self._source_draft_database.exists():
            return SourceFreezeMappingResponse(SourceFreezeMappingStatus.ABSENT)
        sidecar = self._open_source_draft_sidecar(create=False)
        try:
            _begin(sidecar)
            draft = self._query_source_draft(_sidecar=sidecar)
            mapping = self._validated_source_freeze_mapping(draft, request)
            if (
                mapping.status is not SourceFreezeMappingStatus.AVAILABLE
                or mapping.view is None
            ):
                _commit(sidecar)
                return mapping
            result = publisher(mapping.view)
            _commit(sidecar)
            return result
        except Exception:
            _rollback_if_needed(sidecar)
            raise
        finally:
            sidecar.close()

    def _query_source_draft(
        self,
        *,
        _sidecar: sqlite3.Connection | None = None,
    ) -> SourceDraftResponse:
        if not self._source_draft_database.exists():
            return SourceDraftResponse(SourceDraftStatus.ABSENT)
        sidecar = (
            self._open_source_draft_sidecar(create=False)
            if _sidecar is None
            else _sidecar
        )
        try:
            row = sidecar.execute(
                """
                SELECT
                    d.draft_id,
                    d.source_title,
                    d.source_text,
                    d.source_digest,
                    d.candidate_basis_digest,
                    d.current_revision,
                    r.candidates_json,
                    r.selection_digest,
                    r.request_digest
                FROM source_draft AS d
                JOIN source_draft_revision AS r
                  ON r.draft_id = d.draft_id
                 AND r.revision = d.current_revision
                WHERE d.singleton = 1
                """
            ).fetchone()
            revision_rows = sidecar.execute(
                """
                SELECT revision, candidates_json, selection_digest, request_digest
                FROM source_draft_revision
                WHERE draft_id = (SELECT draft_id FROM source_draft WHERE singleton = 1)
                ORDER BY revision
                """
            ).fetchall()
        finally:
            if _sidecar is None:
                sidecar.close()
        if row is None:
            return SourceDraftResponse(SourceDraftStatus.ABSENT)
        try:
            UUID(str(row[0]))
            candidates = source_draft_candidates_from_json(str(row[6]))
        except (TypeError, ValueError):
            raise StudioFailedClosed(
                "source-draft-corrupt",
                "source character draft payload is unreadable",
            ) from None
        prepared, problem = prepare_source_draft_save(
            SourceDraftSaveRequest(
                source_title=str(row[1]),
                source_text=str(row[2]),
                candidates=candidates,
                local_save_confirmed=True,
                base_revision=max(0, int(row[5]) - 1),
            )
        )
        if (
            problem is not None
            or prepared is None
            or prepared.source_digest != str(row[3])
            or prepared.candidate_basis_digest != str(row[4])
            or prepared.selection_digest != str(row[7])
            or prepared.request_digest != str(row[8])
        ):
            raise StudioFailedClosed(
                "source-draft-integrity-failed",
                "source character draft digest no longer matches its content",
            )
        if (
            len(revision_rows) != int(row[5])
            or [int(item[0]) for item in revision_rows]
            != list(range(1, int(row[5]) + 1))
        ):
            raise StudioFailedClosed(
                "source-draft-revision-chain-invalid",
                "source character draft revision chain is incomplete",
            )
        for revision_row in revision_rows:
            try:
                revision_candidates = source_draft_candidates_from_json(
                    str(revision_row[1])
                )
            except ValueError:
                raise StudioFailedClosed(
                    "source-draft-revision-corrupt",
                    "source character draft revision is unreadable",
                ) from None
            revision_prepared, revision_problem = prepare_source_draft_save(
                SourceDraftSaveRequest(
                    source_title=str(row[1]),
                    source_text=str(row[2]),
                    candidates=revision_candidates,
                    local_save_confirmed=True,
                    base_revision=max(0, int(revision_row[0]) - 1),
                )
            )
            if (
                revision_problem is not None
                or revision_prepared is None
                or revision_prepared.candidate_basis_digest != str(row[4])
                or revision_prepared.selection_digest != str(revision_row[2])
                or revision_prepared.request_digest != str(revision_row[3])
            ):
                raise StudioFailedClosed(
                    "source-draft-revision-integrity-failed",
                    "source character draft revision digest is invalid",
                )
        return SourceDraftResponse(
            SourceDraftStatus.AVAILABLE,
            view=SourceDraftView(
                source_title=prepared.source_title,
                source_digest=prepared.source_digest,
                revision=int(row[5]),
                candidates=prepared.candidates,
            ),
        )

    def _save_source_draft(self, request: object) -> SourceDraftResponse:
        self._require_authority()
        effective_request = request
        if not isinstance(request, SourceDraftSaveRequest):
            return SourceDraftResponse(
                SourceDraftStatus.REJECTED,
                problem_code="source-draft-save-request-invalid",
            )
        if request.local_save_confirmed is not True:
            return SourceDraftResponse(
                SourceDraftStatus.REJECTED,
                problem_code="source-draft-local-save-confirmation-required",
            )
        if (
            request.source_text is None
        ):
            if request.source_title is not None:
                return SourceDraftResponse(
                    SourceDraftStatus.REJECTED,
                    problem_code="source-draft-selection-update-invalid",
                )
            if not self._source_draft_database.exists():
                return SourceDraftResponse(
                    SourceDraftStatus.REJECTED,
                    problem_code="source-draft-selection-source-absent",
                )
            reader = self._open_source_draft_sidecar(create=False)
            try:
                source_row = reader.execute(
                    """
                    SELECT source_title, source_text
                    FROM source_draft WHERE singleton = 1
                    """
                ).fetchone()
            finally:
                reader.close()
            if source_row is None:
                return SourceDraftResponse(
                    SourceDraftStatus.REJECTED,
                    problem_code="source-draft-selection-source-absent",
                )
            effective_request = SourceDraftSaveRequest(
                source_title=str(source_row[0]),
                source_text=str(source_row[1]),
                candidates=request.candidates,
                local_save_confirmed=request.local_save_confirmed,
                base_revision=request.base_revision,
            )
        prepared, problem = prepare_source_draft_save(effective_request)
        if problem is not None or prepared is None:
            return SourceDraftResponse(
                SourceDraftStatus.REJECTED,
                problem_code=problem or "source-draft-save-invalid",
            )
        sidecar = self._open_source_draft_sidecar(create=True)
        replayed = False
        try:
            _begin(sidecar)
            current = sidecar.execute(
                """
                SELECT
                    d.draft_id,
                    d.source_title,
                    d.source_digest,
                    d.candidate_basis_digest,
                    d.current_revision,
                    r.request_digest
                FROM source_draft AS d
                JOIN source_draft_revision AS r
                  ON r.draft_id = d.draft_id
                 AND r.revision = d.current_revision
                WHERE d.singleton = 1
                """
            ).fetchone()
            if current is None:
                if prepared.base_revision != 0:
                    raise StudioConflict(
                        "source-draft-revision-conflict",
                        "source draft does not match requested base revision",
                    )
                draft_id = str(uuid4())
                revision = 1
                now_us = _utc_microseconds()
                sidecar.execute(
                    """
                    INSERT INTO source_draft (
                        singleton,
                        draft_id,
                        source_title,
                        source_text,
                        source_digest,
                        candidate_basis_digest,
                        current_revision,
                        created_at_us
                    ) VALUES (1, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        draft_id,
                        prepared.source_title,
                        prepared.source_text,
                        prepared.source_digest,
                        prepared.candidate_basis_digest,
                        now_us,
                    ),
                )
                sidecar.execute(
                    """
                    INSERT INTO source_draft_revision (
                        draft_id,
                        revision,
                        candidates_json,
                        selection_digest,
                        request_digest,
                        created_at_us
                    ) VALUES (?, 1, ?, ?, ?, ?)
                    """,
                    (
                        draft_id,
                        prepared.candidates_json,
                        prepared.selection_digest,
                        prepared.request_digest,
                        now_us,
                    ),
                )
            else:
                draft_id = str(current[0])
                revision = int(current[4])
                if prepared.request_digest == str(current[5]):
                    replayed = True
                else:
                    if prepared.base_revision != revision:
                        raise StudioConflict(
                            "source-draft-revision-conflict",
                            "source draft changed before this save",
                        )
                    if (
                        prepared.source_title != str(current[1])
                        or prepared.source_digest != str(current[2])
                        or prepared.candidate_basis_digest != str(current[3])
                    ):
                        _rollback_if_needed(sidecar)
                        return SourceDraftResponse(
                            SourceDraftStatus.CONFLICT,
                            problem_code="source-draft-basis-changed",
                        )
                    revision += 1
                    now_us = _utc_microseconds()
                    sidecar.execute(
                        """
                        INSERT INTO source_draft_revision (
                            draft_id,
                            revision,
                            candidates_json,
                            selection_digest,
                            request_digest,
                            created_at_us
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            draft_id,
                            revision,
                            prepared.candidates_json,
                            prepared.selection_digest,
                            prepared.request_digest,
                            now_us,
                        ),
                    )
                    updated = sidecar.execute(
                        """
                        UPDATE source_draft
                        SET current_revision = ?
                        WHERE singleton = 1 AND current_revision = ?
                        """,
                        (revision, prepared.base_revision),
                    )
                    if updated.rowcount != 1:
                        raise StudioConflict(
                            "source-draft-revision-conflict",
                            "source draft changed before publication",
                        )
            _commit(sidecar)
        except Exception:
            _rollback_if_needed(sidecar)
            raise
        finally:
            sidecar.close()
        return SourceDraftResponse(
            SourceDraftStatus.AVAILABLE,
            view=SourceDraftView(
                source_title=prepared.source_title,
                source_digest=prepared.source_digest,
                revision=revision,
                candidates=prepared.candidates,
            ),
            replayed=replayed,
        )

    def _delete_source_draft(self, *, confirmed: bool) -> SourceDraftResponse:
        if confirmed is not True:
            return SourceDraftResponse(
                SourceDraftStatus.REJECTED,
                problem_code="source-draft-delete-confirmation-required",
            )
        self._require_authority()
        if not self._source_draft_database.exists():
            return SourceDraftResponse(SourceDraftStatus.ABSENT)
        sidecar = self._open_source_draft_sidecar(create=False)
        try:
            _begin(sidecar)
            deleted = sidecar.execute(
                "DELETE FROM source_draft WHERE singleton = 1"
            ).rowcount
            _commit(sidecar)
        except Exception:
            _rollback_if_needed(sidecar)
            raise
        finally:
            sidecar.close()
        return SourceDraftResponse(
            SourceDraftStatus.DELETED if deleted else SourceDraftStatus.ABSENT
        )

    @staticmethod
    def _accepted_artifact_payload(
        artifact: UnpublishedSubjectStudioArtifact,
    ) -> dict[str, Any]:
        return {
            "artifact_id": artifact.artifact_id,
            "genesis": {
                "candidate_id": artifact.genesis.candidate_id,
                "authored_origin_document": artifact.genesis.authored_origin_document,
                "content_digest": artifact.genesis.content_digest,
            },
            "knowledge": {
                "candidate_id": artifact.knowledge.candidate_id,
                "source_documents": list(artifact.knowledge.source_documents),
                "content_digest": artifact.knowledge.content_digest,
            },
            "provenance": {
                "manifest_id": artifact.provenance.manifest_id,
                "manifest_digest": artifact.provenance.manifest_digest,
                "report_digest": artifact.provenance.report_digest,
                "subset_digest": artifact.provenance.subset_digest,
                "source_ids": list(artifact.provenance.source_ids),
                "source_hashes": list(artifact.provenance.source_hashes),
                "rights_basis": artifact.provenance.rights_basis,
                "declared_use": artifact.provenance.declared_use,
                "artifact_root": artifact.provenance.artifact_root,
            },
            "published": artifact.published,
            "unsealed": artifact.unsealed,
            "authority_counts": dict(artifact.authority_counts),
        }

    @staticmethod
    def _map_accepted_artifact_to_dormant_basis(
        document: str,
    ) -> _DormantArtifactMapping:
        """Map one accepted source without promoting its candidate body to canon."""

        if not isinstance(document, str):
            raise StudioRejected(
                "accepted-artifact-mapping-unavailable",
                "accepted artifact identity requires one UTF-8 text document",
            )
        names: list[str] = []
        for line in document.splitlines():
            stripped = line.strip()
            chinese = re.fullmatch(
                r"-\s*主体称呼为\s+([A-Za-z][A-Za-z0-9 .'-]{0,126})。",
                stripped,
            )
            if chinese is not None:
                names.append(chinese.group(1).strip())
        if not names:
            first_line = next(
                (line.strip() for line in document.splitlines() if line.strip()),
                "",
            )
            english = re.match(
                r"^([A-Z][A-Za-z0-9'-]*(?: [A-Z][A-Za-z0-9'-]*){0,3}) "
                r"is an adult fictional\b",
                first_line,
            )
            if english is not None:
                names.append(english.group(1))
        unique_names = tuple(dict.fromkeys(names))
        if len(unique_names) != 1:
            raise StudioRejected(
                "accepted-artifact-mapping-unavailable",
                "accepted artifact must contain one explicit stable fictional subject name",
            )
        display_name = _normalize_text(
            unique_names[0],
            "accepted_artifact_display_name",
            maximum=128,
        )
        identity_core = (
            f"{display_name} is the named fictional subject of a new isolated "
            "local-private profile. No legacy or private identity, history, memory, "
            "relationship, promise, or runtime authority is inherited."
        )
        canon_start = (
            "The accepted initial source is the sole authored origin. It establishes "
            f"only the subject name {display_name} inside a fictional-subject private "
            "experiment; no other source statement is promoted into Genesis canon."
        )
        relationship = (
            "No relationship, trust, promise, memory, or lived history is established."
        )
        unsigned = {
            "policy_version": "post-m0-03-minimal-dormant-mapping-1.0",
            "display_name": display_name,
            "identity_core": identity_core,
            "subject_identity": identity_core,
            "canon_start": canon_start,
            "initial_relationship_premise": relationship,
        }
        return _DormantArtifactMapping(
            **unsigned,
            mapping_digest=_digest(unsigned),
        )

    def _validate_accepted_artifact_test(
        self,
        artifact: UnpublishedSubjectStudioArtifact,
        *,
        _authority: object | None = None,
    ) -> tuple[dict[str, Any], str, str]:
        try:
            if not isinstance(artifact, UnpublishedSubjectStudioArtifact):
                raise TypeError("accepted artifact type is required")
            _canonical_uuid(artifact.artifact_id, "artifact_id")
            _canonical_uuid(artifact.genesis.candidate_id, "genesis_candidate_id")
            _canonical_uuid(artifact.knowledge.candidate_id, "knowledge_candidate_id")
            _canonical_uuid(artifact.provenance.manifest_id, "manifest_id")
            if artifact.published or not artifact.unsealed:
                raise ValueError("artifact is already authoritative")
            expected_count_keys = {
                "qualified_runtime_input",
                "runtime_binding",
                "runtime_timeline",
                "operation",
                "timeline_outcome",
                "effect",
                "physical_clear",
            }
            if set(artifact.authority_counts) != expected_count_keys or any(
                type(value) is not int or value != 0
                for value in artifact.authority_counts.values()
            ):
                raise ValueError("artifact already owns authority")
            digests = (
                artifact.genesis.content_digest,
                artifact.knowledge.content_digest,
                artifact.provenance.manifest_digest,
                artifact.provenance.report_digest,
                artifact.provenance.subset_digest,
                *artifact.provenance.source_hashes,
            )
            if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in digests):
                raise ValueError("artifact digest is malformed")
            if (
                len(artifact.knowledge.source_documents) != 1
                or len(artifact.provenance.source_ids) != 1
                or len(artifact.provenance.source_hashes) != 1
            ):
                raise ValueError("Phase 1 accepts one exact source member")
            document = artifact.genesis.authored_origin_document
            if artifact.knowledge.source_documents != (document,):
                raise ValueError("Genesis and Knowledge do not bind the same source")
            actual_digest = hashlib.sha256(document.encode("utf-8")).hexdigest()
            if (
                actual_digest != artifact.genesis.content_digest
                or actual_digest != artifact.knowledge.content_digest
                or artifact.provenance.source_hashes != (actual_digest,)
            ):
                raise ValueError("artifact content digest does not match")
            _normalize_text(document, "accepted_artifact_document", maximum=4_000)
            _normalize_text(
                artifact.provenance.rights_basis,
                "rights_basis",
                maximum=1_000,
            )
            _normalize_text(
                artifact.provenance.declared_use,
                "declared_use",
                maximum=1_000,
            )
            artifact_root = Path(artifact.provenance.artifact_root)
            temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
            if _authority is _CONFIRMED_ARTIFACT_ACTIVATION_TOKEN:
                if (
                    not artifact_root.is_absolute()
                    or not artifact_root.is_dir()
                    or _has_linklike_component(
                        artifact_root,
                        Path(artifact_root.anchor).resolve(strict=True),
                    )
                ):
                    raise ValueError("exact accepted artifact root is unsafe")
            elif (
                not artifact_root.is_absolute()
                or not _is_relative_to(
                    artifact_root.resolve(strict=False), temporary_root
                )
                or _has_linklike_component(artifact_root, temporary_root)
            ):
                raise ValueError("test artifact root is outside the temporary boundary")
            payload = self._accepted_artifact_payload(artifact)
            provenance_payload = payload["provenance"]
            return payload, _digest(payload), _digest(provenance_payload)
        except (StudioProblem, TypeError, ValueError, UnicodeError, OSError) as error:
            raise StudioRejected(
                "accepted-artifact-ineligible",
                "artifact fixture is not an exact unpublished and unsealed input",
            ) from error

    def _stage_accepted_artifact_test(
        self,
        artifact: UnpublishedSubjectStudioArtifact,
        *,
        _authority: object | None = None,
    ) -> AcceptedArtifactDraftBundle:
        """Stage one source-complete artifact under the temporary-root test seam."""

        self._require_authority()
        payload, artifact_digest, provenance_digest = (
            self._validate_accepted_artifact_test(
                artifact,
                _authority=_authority,
            )
        )
        sidecar = self._open_artifact_sidecar(create=True)
        try:
            existing = sidecar.execute(
                "SELECT artifact_digest FROM accepted_artifact WHERE artifact_id = ?",
                (artifact.artifact_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != artifact_digest:
                    raise StudioConflict(
                        "accepted-artifact-identity-conflict",
                        "artifact identity already names different content",
                    )
                return self.query_accepted_artifact_drafts(artifact.artifact_id)
        finally:
            sidecar.close()

        document = artifact.genesis.authored_origin_document
        mapping = self._map_accepted_artifact_to_dormant_basis(document)
        source = SourceDeclaration(
            source_id=artifact.provenance.source_ids[0],
            origin_kind="project-original",
            rights_confirmed=True,
            source_asset_refs=(),
            uses_disallowed_inheritance=False,
        )
        profile = ParticipantProfile(
            profile_id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"accepted-artifact-profile:{self._location.root_id}:{artifact.artifact_id}",
                )
            ),
            display_name=mapping.display_name,
            identity_core=mapping.identity_core,
            source=source,
        )
        premise = GenesisPremise(
            subject_identity=mapping.subject_identity,
            canon_start=mapping.canon_start,
            initial_relationship_premise=mapping.initial_relationship_premise,
            source=source,
        )
        branch_id = str(
            uuid5(
                NAMESPACE_URL,
                f"accepted-artifact-branch:{self._location.root_id}:{artifact.artifact_id}",
            )
        )
        profile_json = _canonical_json(profile.to_dict())
        profile_digest = _digest(profile.to_dict())
        premise_json = _canonical_json(premise.to_dict())
        premise_digest = _digest(premise.to_dict())
        knowledge_payload = {
            "artifact_id": artifact.artifact_id,
            "draft_id": artifact.knowledge.candidate_id,
            "revision": 1,
            "source_documents": list(artifact.knowledge.source_documents),
            "content_digest": artifact.knowledge.content_digest,
            "source_ids": list(artifact.provenance.source_ids),
            "source_hashes": list(artifact.provenance.source_hashes),
            "rights_basis": artifact.provenance.rights_basis,
            "declared_use": artifact.provenance.declared_use,
        }
        knowledge_digest = _digest(knowledge_payload)
        created_at_us = _utc_microseconds()
        try:
            _begin(self._writer)
            self._writer.execute(
                """
                INSERT OR IGNORE INTO participant_profile (
                    profile_id, profile_json, profile_digest, created_at_us
                ) VALUES (?, ?, ?, ?)
                """,
                (profile.profile_id, profile_json, profile_digest, created_at_us),
            )
            self._writer.execute(
                """
                INSERT OR IGNORE INTO genesis_branch (
                    branch_id, profile_id, predecessor_snapshot_id,
                    lineage_relation, lineage_reason, created_at_us
                ) VALUES (?, ?, NULL, 'first-publication',
                          'accepted unpublished artifact', ?)
                """,
                (branch_id, profile.profile_id, created_at_us),
            )
            self._writer.execute(
                """
                INSERT OR IGNORE INTO genesis_draft (
                    draft_id, branch_id, profile_id, current_revision,
                    sealed_snapshot_id, created_at_us
                ) VALUES (?, ?, ?, 1, NULL, ?)
                """,
                (
                    artifact.genesis.candidate_id,
                    branch_id,
                    profile.profile_id,
                    created_at_us,
                ),
            )
            self._writer.execute(
                """
                INSERT OR IGNORE INTO genesis_draft_revision (
                    draft_id, revision, premise_json, content_digest, created_at_us
                ) VALUES (?, 1, ?, ?, ?)
                """,
                (
                    artifact.genesis.candidate_id,
                    premise_json,
                    premise_digest,
                    created_at_us,
                ),
            )
            _commit(self._writer)
        except Exception:
            _rollback_if_needed(self._writer)
            raise
        recovered_genesis = self.preview(artifact.genesis.candidate_id)
        if (
            recovered_genesis.profile_id != profile.profile_id
            or recovered_genesis.branch_id != branch_id
            or recovered_genesis.revision != 1
            or recovered_genesis.premise != premise
        ):
            raise StudioConflict(
                "accepted-artifact-identity-conflict",
                "recovered Genesis draft differs from the accepted artifact",
            )
        sidecar = self._open_artifact_sidecar(create=True)
        try:
            _begin(sidecar)
            sidecar.execute(
                """
                INSERT INTO accepted_artifact (
                    artifact_id, profile_id, genesis_draft_id, knowledge_draft_id,
                    artifact_json, artifact_digest, provenance_digest, created_at_us
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.artifact_id,
                    profile.profile_id,
                    artifact.genesis.candidate_id,
                    artifact.knowledge.candidate_id,
                    _canonical_json(payload),
                    artifact_digest,
                    provenance_digest,
                    created_at_us,
                ),
            )
            sidecar.execute(
                """
                INSERT INTO knowledge_draft (
                    draft_id, artifact_id, current_revision,
                    sealed_snapshot_id, created_at_us
                ) VALUES (?, ?, 1, NULL, ?)
                """,
                (
                    artifact.knowledge.candidate_id,
                    artifact.artifact_id,
                    created_at_us,
                ),
            )
            sidecar.execute(
                """
                INSERT INTO knowledge_draft_revision (
                    draft_id, revision, content_json, content_digest, created_at_us
                ) VALUES (?, 1, ?, ?, ?)
                """,
                (
                    artifact.knowledge.candidate_id,
                    _canonical_json(knowledge_payload),
                    knowledge_digest,
                    created_at_us,
                ),
            )
            _commit(sidecar)
        except Exception:
            _rollback_if_needed(sidecar)
            raise
        finally:
            sidecar.close()
        return self.query_accepted_artifact_drafts(artifact.artifact_id)

    def query_accepted_artifact_drafts(
        self,
        artifact_id: str,
    ) -> AcceptedArtifactDraftBundle:
        self._require_open()
        canonical_artifact_id = _canonical_uuid(artifact_id, "artifact_id")
        sidecar = self._open_artifact_sidecar(create=False)
        try:
            row = sidecar.execute(
                """
                SELECT
                    a.artifact_json, a.artifact_digest, a.provenance_digest,
                    a.genesis_draft_id, a.knowledge_draft_id,
                    k.current_revision, k.sealed_snapshot_id,
                    r.content_json, r.content_digest
                FROM accepted_artifact AS a
                JOIN knowledge_draft AS k ON k.artifact_id = a.artifact_id
                JOIN knowledge_draft_revision AS r
                  ON r.draft_id = k.draft_id AND r.revision = k.current_revision
                WHERE a.artifact_id = ?
                """,
                (canonical_artifact_id,),
            ).fetchone()
        finally:
            sidecar.close()
        if row is None:
            raise StudioRejected(
                "accepted-artifact-not-found",
                "accepted artifact drafts do not exist",
            )
        try:
            artifact_payload = json.loads(str(row[0]))
            knowledge_payload = json.loads(str(row[7]))
        except json.JSONDecodeError as error:
            raise StudioFailedClosed(
                "accepted-artifact-corrupt",
                "accepted artifact draft payload is unreadable",
            ) from error
        if (
            _digest(artifact_payload) != str(row[1])
            or _digest(artifact_payload.get("provenance")) != str(row[2])
            or _digest(knowledge_payload) != str(row[8])
            or str(row[3]) != artifact_payload.get("genesis", {}).get("candidate_id")
            or str(row[4]) != artifact_payload.get("knowledge", {}).get("candidate_id")
        ):
            raise StudioFailedClosed(
                "accepted-artifact-integrity-failed",
                "accepted artifact draft identity or digest changed",
            )
        genesis = self.preview(str(row[3]))
        try:
            knowledge_documents = tuple(knowledge_payload["source_documents"])
            knowledge_document_digest = hashlib.sha256(
                knowledge_documents[0].encode("utf-8")
            ).hexdigest()
            authored_origin_document = artifact_payload["genesis"][
                "authored_origin_document"
            ]
            artifact_genesis_digest = artifact_payload["genesis"]["content_digest"]
            artifact_knowledge_digest = artifact_payload["knowledge"]["content_digest"]
            provenance_hashes = tuple(artifact_payload["provenance"]["source_hashes"])
        except (KeyError, IndexError, TypeError, AttributeError) as error:
            raise StudioFailedClosed(
                "accepted-artifact-integrity-failed",
                "accepted artifact source binding is incomplete",
            ) from error
        if (
            len(knowledge_documents) != 1
            or tuple(artifact_payload["knowledge"]["source_documents"])
            != knowledge_documents
            or authored_origin_document != knowledge_documents[0]
            or knowledge_payload.get("content_digest") != artifact_knowledge_digest
            or hashlib.sha256(authored_origin_document.encode("utf-8")).hexdigest()
            != artifact_genesis_digest
            or knowledge_document_digest != artifact_knowledge_digest
            or provenance_hashes
            != (artifact_genesis_digest,)
            or artifact_genesis_digest != artifact_knowledge_digest
        ):
            raise StudioFailedClosed(
                "accepted-artifact-integrity-failed",
                "artifact digests do not bind the persisted Genesis and Knowledge bodies",
            )
        mapping = self._map_accepted_artifact_to_dormant_basis(
            authored_origin_document
        )
        _profile_row, profile, persisted_premise, _profile_digest = self._draft_bundle(
            str(row[3])
        )
        if (
            profile.display_name != mapping.display_name
            or profile.identity_core != mapping.identity_core
            or persisted_premise.subject_identity != mapping.subject_identity
            or persisted_premise.canon_start != mapping.canon_start
            or persisted_premise.initial_relationship_premise
            != mapping.initial_relationship_premise
        ):
            raise StudioFailedClosed(
                "accepted-artifact-mapping-integrity-failed",
                "persisted Profile or Genesis exceeds the current minimal mapping",
            )
        genesis_basis = _digest(
            {
                "scope": "accepted-artifact-genesis",
                "artifact_id": canonical_artifact_id,
                "provenance_digest": str(row[2]),
                "studio_freeze_basis_digest": genesis.freeze_basis_digest,
            }
        )
        knowledge_basis = _digest(
            {
                "scope": "accepted-artifact-knowledge",
                "artifact_id": canonical_artifact_id,
                "provenance_digest": str(row[2]),
                "draft_id": str(row[4]),
                "revision": int(row[5]),
                "content_digest": str(row[8]),
            }
        )
        return AcceptedArtifactDraftBundle(
            artifact_id=canonical_artifact_id,
            profile_id=genesis.profile_id,
            provenance_digest=str(row[2]),
            mapping_policy_version=mapping.policy_version,
            mapping_digest=mapping.mapping_digest,
            genesis=GenesisPreview(
                draft_id=genesis.draft_id,
                branch_id=genesis.branch_id,
                profile_id=genesis.profile_id,
                revision=genesis.revision,
                freeze_basis_digest=genesis_basis,
                content_fingerprint=genesis.content_fingerprint,
                premise=genesis.premise,
            ),
            knowledge=KnowledgeDraftPreview(
                draft_id=str(row[4]),
                artifact_id=canonical_artifact_id,
                revision=int(row[5]),
                freeze_basis_digest=knowledge_basis,
                content_fingerprint=artifact_payload["knowledge"]["content_digest"],
                member_count=len(knowledge_payload["source_documents"]),
                authoritative=row[6] is not None,
            ),
        )

    def _accepted_artifact_policy_question(
        self,
        artifact_id: str,
        capabilities: CapabilityManifest,
    ) -> PolicyQuestion:
        if not isinstance(capabilities, CapabilityManifest):
            raise TypeError("artifact policy requires a CapabilityManifest")
        drafts = self.query_accepted_artifact_drafts(artifact_id)
        _row, profile, premise, profile_digest = self._draft_bundle(
            drafts.genesis.draft_id
        )
        isolation = self.isolation_proof
        combined_freeze_basis = _digest(
            {
                "contract_version": CONTRACT_VERSION,
                "artifact_id": drafts.artifact_id,
                "provenance_digest": drafts.provenance_digest,
                "genesis_freeze_basis_digest": drafts.genesis.freeze_basis_digest,
                "knowledge_freeze_basis_digest": drafts.knowledge.freeze_basis_digest,
            }
        )
        question_basis = {
            "contract_version": CONTRACT_VERSION,
            "profile_digest": profile_digest,
            "freeze_basis_digest": combined_freeze_basis,
            "capability_manifest": capabilities.to_dict(),
            "isolation_proof": isolation.to_dict(),
        }
        return PolicyQuestion(
            question_digest=_digest(question_basis),
            profile_digest=profile_digest,
            freeze_basis_digest=combined_freeze_basis,
            capability_manifest=capabilities,
            isolation_proof=isolation,
            profile_source=profile.source,
            genesis_source=premise.source,
        )

    def decide_accepted_artifact_policy(
        self,
        artifact_id: str,
        capabilities: CapabilityManifest,
        *,
        validity_us: int = 5_000_000,
    ) -> PolicyDecision:
        self._require_authority()
        question = self._accepted_artifact_policy_question(artifact_id, capabilities)
        decision = self._policy_kernel.decide(question, validity_us=validity_us)
        payload = decision.to_dict()
        try:
            _begin(self._writer)
            existing = self._writer.execute(
                "SELECT integrity_digest FROM policy_decision WHERE decision_id = ?",
                (decision.decision_id,),
            ).fetchone()
            if existing is None:
                self._writer.execute(
                    """
                    INSERT INTO policy_decision (
                        decision_id, decision_json, integrity_digest, created_at_us
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        decision.decision_id,
                        _canonical_json(payload),
                        decision.integrity_digest,
                        _utc_microseconds(),
                    ),
                )
            elif str(existing[0]) != decision.integrity_digest:
                raise StudioConflict(
                    "policy-identity-conflict",
                    "PolicyDecision identity already names different content",
                )
            _commit(self._writer)
        except Exception:
            _rollback_if_needed(self._writer)
            raise
        return decision

    @staticmethod
    def _artifact_snapshot_from_payload(
        payload: Mapping[str, Any],
    ) -> AcceptedArtifactSnapshot:
        return AcceptedArtifactSnapshot(
            snapshot_id=str(payload["snapshot_id"]),
            scope=str(payload["scope"]),
            artifact_id=str(payload["artifact_id"]),
            draft_id=str(payload["draft_id"]),
            freeze_decision_id=str(payload["freeze_decision_id"]),
            freeze_attempt_id=str(payload["freeze_attempt_id"]),
            policy_decision_id=str(payload["policy_decision_id"]),
            freeze_basis_digest=str(payload["freeze_basis_digest"]),
            content_fingerprint=str(payload["content_fingerprint"]),
            provenance_digest=str(payload["provenance_digest"]),
            member_count=int(payload["member_count"]),
            created_at_us=int(payload["created_at_us"]),
        )

    def _seal_accepted_artifact_test(
        self,
        artifact_id: str,
        *,
        genesis_decision: ScopedFreezeDecision,
        knowledge_decision: ScopedFreezeDecision,
        policy_decision_id: str,
        _attempt_hook: Callable[[str], None] | None = None,
        _created_at_us: int | None = None,
    ) -> AcceptedArtifactSnapshotBundle:
        self._require_authority()
        if not isinstance(genesis_decision, ScopedFreezeDecision) or not isinstance(
            knowledge_decision, ScopedFreezeDecision
        ):
            raise TypeError("artifact seal requires two scoped FreezeDecisions")
        drafts = self.query_accepted_artifact_drafts(artifact_id)
        expected = (
            (
                genesis_decision,
                "genesis",
                drafts.genesis.draft_id,
                drafts.genesis.revision,
                drafts.genesis.freeze_basis_digest,
            ),
            (
                knowledge_decision,
                "knowledge",
                drafts.knowledge.draft_id,
                drafts.knowledge.revision,
                drafts.knowledge.freeze_basis_digest,
            ),
        )
        if genesis_decision.decision_id == knowledge_decision.decision_id or any(
            decision.scope != scope
            or decision.draft_id != draft_id
            or decision.expected_revision != revision
            or decision.freeze_basis_digest != basis
            for decision, scope, draft_id, revision, basis in expected
        ):
            raise StudioRejected(
                "artifact-freeze-basis-mismatch",
                "Genesis and Knowledge each require their own current FreezeDecision",
            )
        policy = self._read_policy_decision(policy_decision_id)
        question = self._accepted_artifact_policy_question(
            drafts.artifact_id,
            policy.capability_manifest,
        )
        revalidation = self._policy_kernel.revalidate(policy, question)
        if (
            revalidation.disposition is not PolicyDisposition.QUALIFIED
            or policy.capability_manifest
            != CapabilityManifest.accepted_artifact_dormant()
        ):
            raise StudioRejected(
                revalidation.reason_code,
                "PolicyDecision does not authorize accepted artifact seal",
            )
        sidecar = self._open_artifact_sidecar(create=False)
        try:
            existing = sidecar.execute(
                """
                SELECT COUNT(*) FROM sealed_snapshot WHERE artifact_id = ?
                """,
                (drafts.artifact_id,),
            ).fetchone()
            if existing is not None and int(existing[0]) != 0:
                sealed = self.query_accepted_artifact_snapshots(drafts.artifact_id)
                if (
                    sealed.genesis.freeze_decision_id
                    != genesis_decision.decision_id
                    or sealed.knowledge.freeze_decision_id
                    != knowledge_decision.decision_id
                    or sealed.genesis.policy_decision_id != policy.decision_id
                    or sealed.knowledge.policy_decision_id != policy.decision_id
                ):
                    raise StudioConflict(
                        "artifact-seal-identity-conflict",
                        "artifact already has different immutable snapshots",
                    )
                return sealed
            artifact_row = sidecar.execute(
                """
                SELECT artifact_json FROM accepted_artifact WHERE artifact_id = ?
                """,
                (drafts.artifact_id,),
            ).fetchone()
            if artifact_row is None:
                raise StudioFailedClosed(
                    "accepted-artifact-integrity-failed",
                    "artifact disappeared before seal",
                )
            created_at_us = (
                _utc_microseconds()
                if _created_at_us is None
                else int(_created_at_us)
            )
            if created_at_us < 1:
                raise StudioRejected(
                    "artifact-activation-plan-mismatch",
                    "snapshot creation time must be positive",
                )
            snapshot_payloads: list[dict[str, Any]] = []
            for decision, scope, draft_id, _revision, basis in expected:
                attempt_id = str(
                    uuid5(
                        NAMESPACE_URL,
                        f"accepted-artifact-freeze-attempt:{self._location.root_id}:"
                        f"{drafts.artifact_id}:{scope}:{decision.decision_id}",
                    )
                )
                snapshot_id = str(
                    uuid5(
                        NAMESPACE_URL,
                        f"accepted-artifact-snapshot:{self._location.root_id}:"
                        f"{drafts.artifact_id}:{scope}:{decision.decision_id}",
                    )
                )
                content_fingerprint = (
                    drafts.genesis.content_fingerprint
                    if scope == "genesis"
                    else drafts.knowledge.content_fingerprint
                )
                snapshot_payloads.append(
                    {
                        "snapshot_id": snapshot_id,
                        "scope": scope,
                        "artifact_id": drafts.artifact_id,
                        "draft_id": draft_id,
                        "freeze_decision_id": decision.decision_id,
                        "freeze_attempt_id": attempt_id,
                        "policy_decision_id": policy.decision_id,
                        "freeze_basis_digest": basis,
                        "content_fingerprint": content_fingerprint,
                        "provenance_digest": drafts.provenance_digest,
                        "member_count": 0 if scope == "genesis" else drafts.knowledge.member_count,
                        "created_at_us": created_at_us,
                    }
                )
            _begin(sidecar)
            for decision, snapshot_payload in zip(
                (genesis_decision, knowledge_decision),
                snapshot_payloads,
                strict=True,
            ):
                decision_payload = decision.to_dict()
                sidecar.execute(
                    """
                    INSERT INTO freeze_decision (
                        decision_id, artifact_id, scope, draft_id,
                        decision_json, decision_digest, created_at_us
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        decision.decision_id,
                        drafts.artifact_id,
                        decision.scope,
                        decision.draft_id,
                        _canonical_json(decision_payload),
                        _digest(decision_payload),
                        created_at_us,
                    ),
                )
                sidecar.execute(
                    """
                    INSERT INTO freeze_attempt (
                        attempt_id, artifact_id, scope, decision_id, draft_id,
                        freeze_basis_digest, result, created_at_us
                    ) VALUES (?, ?, ?, ?, ?, ?, 'sealed', ?)
                    """,
                    (
                        snapshot_payload["freeze_attempt_id"],
                        drafts.artifact_id,
                        snapshot_payload["scope"],
                        decision.decision_id,
                        decision.draft_id,
                        decision.freeze_basis_digest,
                        created_at_us,
                    ),
                )
                if _attempt_hook is not None:
                    _attempt_hook(str(snapshot_payload["scope"]))
                sidecar.execute(
                    """
                    INSERT INTO sealed_snapshot (
                        snapshot_id, artifact_id, scope, draft_id,
                        freeze_decision_id, freeze_attempt_id,
                        snapshot_json, snapshot_digest, created_at_us
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_payload["snapshot_id"],
                        drafts.artifact_id,
                        snapshot_payload["scope"],
                        snapshot_payload["draft_id"],
                        snapshot_payload["freeze_decision_id"],
                        snapshot_payload["freeze_attempt_id"],
                        _canonical_json(snapshot_payload),
                        _digest(snapshot_payload),
                        created_at_us,
                    ),
                )
            sidecar.execute(
                """
                UPDATE knowledge_draft SET sealed_snapshot_id = ?
                WHERE draft_id = ? AND sealed_snapshot_id IS NULL
                """,
                (
                    snapshot_payloads[1]["snapshot_id"],
                    drafts.knowledge.draft_id,
                ),
            )
            _commit(sidecar)
        except Exception:
            _rollback_if_needed(sidecar)
            raise
        finally:
            sidecar.close()
        return self.query_accepted_artifact_snapshots(drafts.artifact_id)

    def query_accepted_artifact_snapshots(
        self,
        artifact_id: str,
    ) -> AcceptedArtifactSnapshotBundle:
        self._require_open()
        drafts = self.query_accepted_artifact_drafts(artifact_id)
        sidecar = self._open_artifact_sidecar(create=False)
        try:
            rows = sidecar.execute(
                """
                SELECT scope, snapshot_json, snapshot_digest
                FROM sealed_snapshot WHERE artifact_id = ? ORDER BY scope
                """,
                (drafts.artifact_id,),
            ).fetchall()
            decision_rows = sidecar.execute(
                """
                SELECT scope, decision_json, decision_digest
                FROM freeze_decision WHERE artifact_id = ? ORDER BY scope
                """,
                (drafts.artifact_id,),
            ).fetchall()
        finally:
            sidecar.close()
        if len(rows) != 2 or {str(row[0]) for row in rows} != {
            "genesis",
            "knowledge",
        }:
            raise StudioRejected(
                "accepted-artifact-snapshots-not-found",
                "both artifact snapshots are required",
            )
        if len(decision_rows) != 2 or {str(row[0]) for row in decision_rows} != {
            "genesis",
            "knowledge",
        }:
            raise StudioFailedClosed(
                "artifact-freeze-decision-integrity-failed",
                "both persisted scoped FreezeDecisions are required",
            )
        decisions: dict[str, Mapping[str, Any]] = {}
        for row in decision_rows:
            try:
                decision_payload = json.loads(str(row[1]))
            except json.JSONDecodeError as error:
                raise StudioFailedClosed(
                    "artifact-freeze-decision-integrity-failed",
                    "persisted FreezeDecision is unreadable",
                ) from error
            if (
                _digest(decision_payload) != str(row[2])
                or decision_payload.get("scope") != str(row[0])
            ):
                raise StudioFailedClosed(
                    "artifact-freeze-decision-integrity-failed",
                    "persisted FreezeDecision digest or scope changed",
                )
            decisions[str(row[0])] = decision_payload
        snapshots: dict[str, AcceptedArtifactSnapshot] = {}
        for row in rows:
            try:
                payload = json.loads(str(row[1]))
            except json.JSONDecodeError as error:
                raise StudioFailedClosed(
                    "accepted-artifact-snapshot-corrupt",
                    "artifact snapshot payload is unreadable",
                ) from error
            if _digest(payload) != str(row[2]) or payload.get("scope") != str(row[0]):
                raise StudioFailedClosed(
                    "accepted-artifact-snapshot-integrity-failed",
                    "artifact snapshot digest or scope changed",
                )
            snapshots[str(row[0])] = self._artifact_snapshot_from_payload(payload)
        for scope, snapshot in snapshots.items():
            decision = decisions[scope]
            expected_preview = drafts.genesis if scope == "genesis" else drafts.knowledge
            if (
                decision.get("decision_id") != snapshot.freeze_decision_id
                or decision.get("draft_id") != snapshot.draft_id
                or decision.get("draft_id") != expected_preview.draft_id
                or decision.get("expected_revision") != expected_preview.revision
                or decision.get("freeze_basis_digest")
                != snapshot.freeze_basis_digest
                or decision.get("freeze_basis_digest")
                != expected_preview.freeze_basis_digest
                or snapshot.content_fingerprint
                != expected_preview.content_fingerprint
            ):
                raise StudioFailedClosed(
                    "artifact-freeze-decision-integrity-failed",
                    "persisted FreezeDecision no longer binds its snapshot",
                )
        return AcceptedArtifactSnapshotBundle(
            artifact_id=drafts.artifact_id,
            profile_id=drafts.profile_id,
            genesis=snapshots["genesis"],
            knowledge=snapshots["knowledge"],
        )

    @staticmethod
    def _compatibility_proof_from_payload(
        payload: Mapping[str, Any],
    ) -> SnapshotCompatibilityProof:
        return SnapshotCompatibilityProof(
            proof_id=str(payload["proof_id"]),
            artifact_id=str(payload["artifact_id"]),
            profile_id=str(payload["profile_id"]),
            genesis_snapshot_id=str(payload["genesis_snapshot_id"]),
            knowledge_snapshot_id=str(payload["knowledge_snapshot_id"]),
            policy_decision_id=str(payload["policy_decision_id"]),
            capability_manifest_version=str(payload["capability_manifest_version"]),
            participant_identity_digest=str(payload["participant_identity_digest"]),
            source_qualification_digest=str(payload["source_qualification_digest"]),
            knowledge_membership_digest=str(payload["knowledge_membership_digest"]),
            prerequisites_digest=str(payload["prerequisites_digest"]),
            integrity_digest=str(payload["integrity_digest"]),
        )

    def _prove_accepted_artifact_compatibility_test(
        self,
        artifact_id: str,
        *,
        policy_decision_id: str,
    ) -> SnapshotCompatibilityProof:
        self._require_authority()
        drafts = self.query_accepted_artifact_drafts(artifact_id)
        snapshots = self.query_accepted_artifact_snapshots(artifact_id)
        policy = self._read_policy_decision(policy_decision_id)
        question = self._accepted_artifact_policy_question(
            artifact_id,
            policy.capability_manifest,
        )
        revalidation = self._policy_kernel.revalidate(policy, question)
        if (
            revalidation.disposition is not PolicyDisposition.QUALIFIED
            or policy.capability_manifest
            != CapabilityManifest.accepted_artifact_dormant()
        ):
            raise StudioRejected(
                "snapshot-compatibility-failed",
                "capability prerequisites are not qualified",
            )
        _row, profile, premise, _profile_digest = self._draft_bundle(
            drafts.genesis.draft_id
        )
        sidecar = self._open_artifact_sidecar(create=False)
        try:
            artifact_row = sidecar.execute(
                "SELECT artifact_json FROM accepted_artifact WHERE artifact_id = ?",
                (drafts.artifact_id,),
            ).fetchone()
        finally:
            sidecar.close()
        if artifact_row is None:
            raise StudioFailedClosed(
                "accepted-artifact-integrity-failed",
                "artifact disappeared before compatibility evaluation",
            )
        try:
            artifact_payload = json.loads(str(artifact_row[0]))
            provenance = artifact_payload["provenance"]
            source_documents = artifact_payload["knowledge"]["source_documents"]
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise StudioFailedClosed(
                "accepted-artifact-integrity-failed",
                "artifact is unreadable during compatibility evaluation",
            ) from error
        compatible = (
            profile.profile_id == drafts.profile_id
            and profile.identity_core == premise.subject_identity
            and profile.source.origin_kind == "project-original"
            and premise.source.origin_kind == "project-original"
            and profile.source.rights_confirmed
            and premise.source.rights_confirmed
            and bool(provenance["rights_basis"])
            and bool(provenance["declared_use"])
            and len(source_documents) == snapshots.knowledge.member_count == 1
            and snapshots.genesis.content_fingerprint
            == drafts.genesis.content_fingerprint
            and snapshots.knowledge.content_fingerprint
            == artifact_payload["knowledge"]["content_digest"]
            and snapshots.genesis.provenance_digest == drafts.provenance_digest
            and snapshots.knowledge.provenance_digest == drafts.provenance_digest
        )
        if not compatible:
            raise StudioRejected(
                "snapshot-compatibility-failed",
                "identity, origin, canon, rights, or Knowledge membership is incompatible",
            )
        participant_identity_digest = _digest(
            {
                "profile_id": profile.profile_id,
                "identity_core": profile.identity_core,
                "subject_identity": premise.subject_identity,
                "reality_scope": "fictional-subject-private-experiment",
                "canon_scope": "initial-source-only",
                "mapping_policy_version": drafts.mapping_policy_version,
                "mapping_digest": drafts.mapping_digest,
            }
        )
        source_qualification_digest = _digest(
            {
                "provenance_digest": drafts.provenance_digest,
                "source_ids": provenance["source_ids"],
                "source_hashes": provenance["source_hashes"],
                "rights_basis": provenance["rights_basis"],
                "declared_use": provenance["declared_use"],
            }
        )
        knowledge_membership_digest = _digest(
            {
                "knowledge_snapshot_id": snapshots.knowledge.snapshot_id,
                "member_count": snapshots.knowledge.member_count,
                "source_hashes": provenance["source_hashes"],
            }
        )
        prerequisites_digest = _digest(
            {
                "capabilities": policy.capability_manifest.to_dict(),
                "policy_decision_id": policy.decision_id,
                "genesis_snapshot_id": snapshots.genesis.snapshot_id,
                "knowledge_snapshot_id": snapshots.knowledge.snapshot_id,
            }
        )
        unsigned = {
            "artifact_id": drafts.artifact_id,
            "profile_id": drafts.profile_id,
            "genesis_snapshot_id": snapshots.genesis.snapshot_id,
            "knowledge_snapshot_id": snapshots.knowledge.snapshot_id,
            "policy_decision_id": policy.decision_id,
            "capability_manifest_version": policy.capability_manifest.manifest_version,
            "participant_identity_digest": participant_identity_digest,
            "source_qualification_digest": source_qualification_digest,
            "knowledge_membership_digest": knowledge_membership_digest,
            "prerequisites_digest": prerequisites_digest,
        }
        proof_id = str(
            uuid5(
                NAMESPACE_URL,
                f"snapshot-compatibility-proof:{self._location.root_id}:{_digest(unsigned)}",
            )
        )
        payload_without_integrity = {"proof_id": proof_id, **unsigned}
        payload = {
            **payload_without_integrity,
            "integrity_digest": _digest(payload_without_integrity),
        }
        sidecar = self._open_artifact_sidecar(create=False)
        try:
            _begin(sidecar)
            existing = sidecar.execute(
                """
                SELECT proof_json, integrity_digest
                FROM snapshot_compatibility_proof WHERE artifact_id = ?
                """,
                (drafts.artifact_id,),
            ).fetchone()
            if existing is None:
                sidecar.execute(
                    """
                    INSERT INTO snapshot_compatibility_proof (
                        proof_id, artifact_id, proof_json, integrity_digest, created_at_us
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        proof_id,
                        drafts.artifact_id,
                        _canonical_json(payload),
                        payload["integrity_digest"],
                        _utc_microseconds(),
                    ),
                )
            elif (
                str(existing[0]) != _canonical_json(payload)
                or str(existing[1]) != payload["integrity_digest"]
            ):
                raise StudioConflict(
                    "snapshot-compatibility-conflict",
                    "artifact already has a different compatibility proof",
                )
            _commit(sidecar)
        except Exception:
            _rollback_if_needed(sidecar)
            raise
        finally:
            sidecar.close()
        return self._compatibility_proof_from_payload(payload)

    def query_accepted_artifact_compatibility(
        self,
        artifact_id: str,
    ) -> SnapshotCompatibilityProof:
        self._require_open()
        canonical_artifact_id = _canonical_uuid(artifact_id, "artifact_id")
        sidecar = self._open_artifact_sidecar(create=False)
        try:
            row = sidecar.execute(
                """
                SELECT proof_json, integrity_digest
                FROM snapshot_compatibility_proof WHERE artifact_id = ?
                """,
                (canonical_artifact_id,),
            ).fetchone()
        finally:
            sidecar.close()
        if row is None:
            raise StudioRejected(
                "snapshot-compatibility-not-found",
                "accepted artifact has no compatibility proof",
            )
        try:
            payload = json.loads(str(row[0]))
        except json.JSONDecodeError as error:
            raise StudioFailedClosed(
                "snapshot-compatibility-corrupt",
                "compatibility proof is unreadable",
            ) from error
        unsigned = dict(payload)
        integrity_digest = str(unsigned.pop("integrity_digest", ""))
        if (
            payload.get("artifact_id") != canonical_artifact_id
            or _digest(unsigned) != integrity_digest
            or integrity_digest != str(row[1])
        ):
            raise StudioFailedClosed(
                "snapshot-compatibility-integrity-failed",
                "compatibility proof digest or artifact identity changed",
            )
        return self._compatibility_proof_from_payload(payload)

    def _publish_accepted_artifact_qri_test(
        self,
        artifact_id: str,
        *,
        policy_decision_id: str,
        compatibility_proof_id: str,
        publication_key: str,
        _published_at_us: int | None = None,
    ) -> QualifiedRuntimeInput:
        self._require_authority()
        if not isinstance(publication_key, str) or not _PUBLICATION_KEY.fullmatch(
            publication_key
        ):
            raise StudioRejected(
                "invalid-publication-key",
                "publication key must be a stable opaque identifier",
            )
        proof = self.query_accepted_artifact_compatibility(artifact_id)
        snapshots = self.query_accepted_artifact_snapshots(artifact_id)
        drafts = self.query_accepted_artifact_drafts(artifact_id)
        policy = self._read_policy_decision(policy_decision_id)
        question = self._accepted_artifact_policy_question(
            artifact_id,
            policy.capability_manifest,
        )
        if (
            proof.proof_id != _canonical_uuid(compatibility_proof_id, "proof_id")
            or proof.policy_decision_id != policy.decision_id
            or proof.genesis_snapshot_id != snapshots.genesis.snapshot_id
            or proof.knowledge_snapshot_id != snapshots.knowledge.snapshot_id
            or self._policy_kernel.revalidate(policy, question).disposition
            is not PolicyDisposition.QUALIFIED
            or policy.capability_manifest
            != CapabilityManifest.accepted_artifact_dormant()
        ):
            raise StudioRejected(
                "snapshot-compatibility-failed",
                "compatibility proof does not authorize this QRI publication",
            )
        qualification_id = str(
            uuid5(
                NAMESPACE_URL,
                f"accepted-artifact-qri:{self._location.root_id}:{publication_key}",
            )
        )
        published_at_us = (
            _utc_microseconds()
            if _published_at_us is None
            else int(_published_at_us)
        )
        if published_at_us < 1:
            raise StudioRejected(
                "artifact-activation-plan-mismatch",
                "QRI publication time must be positive",
            )
        branch_id = self.query_draft(drafts.genesis.draft_id).branch_id
        unsigned = {
            "qualification_id": qualification_id,
            "qualification_revision": 1,
            "profile_id": drafts.profile_id,
            "genesis_branch_id": branch_id,
            "genesis_snapshot_id": snapshots.genesis.snapshot_id,
            "knowledge_snapshot_id": snapshots.knowledge.snapshot_id,
            "policy_decision_ids": [policy.decision_id],
            "capabilities": policy.capability_manifest.to_dict(),
            "isolation_proof": self.isolation_proof.to_dict(),
            "provider_authority": _DORMANT_ARTIFACT_PROVIDER_AUTHORITY,
            "compatibility_proof": proof.integrity_digest,
            "predecessor_qualification_id": None,
            "publication_key": publication_key,
            "published_at_us": published_at_us,
        }
        payload = {**unsigned, "integrity_digest": _digest(unsigned)}
        publication_digest = _digest(
            {
                "artifact_id": drafts.artifact_id,
                "genesis_snapshot_id": snapshots.genesis.snapshot_id,
                "knowledge_snapshot_id": snapshots.knowledge.snapshot_id,
                "policy_decision_id": policy.decision_id,
                "compatibility_proof_id": proof.proof_id,
                "qri_integrity_digest": payload["integrity_digest"],
            }
        )
        try:
            _begin(self._writer)
            existing = self._writer.execute(
                """
                SELECT publication_digest, qri_json, integrity_digest
                FROM qri_publication WHERE publication_key = ?
                """,
                (publication_key,),
            ).fetchone()
            if existing is None:
                self._writer.execute(
                    """
                    INSERT INTO qri_publication (
                        qualification_id, publication_key, publication_digest,
                        qri_json, integrity_digest, created_at_us
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        qualification_id,
                        publication_key,
                        publication_digest,
                        _canonical_json(payload),
                        payload["integrity_digest"],
                        published_at_us,
                    ),
                )
                existing = self._writer.execute(
                    """
                    SELECT publication_digest, qri_json, integrity_digest
                    FROM qri_publication WHERE publication_key = ?
                    """,
                    (publication_key,),
                ).fetchone()
            elif str(existing[0]) != publication_digest:
                raise StudioConflict(
                    "publication-key-conflict",
                    "publication key already names a different qualification",
                )
            _commit(self._writer)
        except Exception:
            _rollback_if_needed(self._writer)
            raise
        if existing is None:
            raise StudioFailedClosed(
                "qri-publication-missing",
                "QRI disappeared during publication",
            )
        return self._read_qri_row(existing)

    def _publish_accepted_artifact_local_successor_qri_test(
        self,
        artifact_id: str,
        *,
        predecessor_qualification_id: str,
        policy_decision_id: str,
        publication_key: str,
        _published_at_us: int | None = None,
    ) -> QualifiedRuntimeInput:
        """Append the Phase-1 local-test successor of one canonical dormant QRI.

        The caller supplies stable identities, never provider selection or
        Profile/Genesis/Knowledge content.  This deep test seam re-reads every
        canonical predecessor and accepted-artifact basis before publishing.
        """

        self._require_authority()
        canonical_artifact_id = _canonical_uuid(artifact_id, "artifact_id")
        canonical_predecessor_id = _canonical_uuid(
            predecessor_qualification_id,
            "predecessor_qualification_id",
        )
        if not isinstance(publication_key, str) or not _PUBLICATION_KEY.fullmatch(
            publication_key
        ):
            raise StudioRejected(
                "invalid-publication-key",
                "publication key must be a stable opaque identifier",
            )

        predecessor_row = self._writer.execute(
            """
            SELECT publication_digest, qri_json, integrity_digest
            FROM qri_publication WHERE qualification_id = ?
            """,
            (canonical_predecessor_id,),
        ).fetchone()
        if predecessor_row is None:
            raise StudioRejected(
                "successor-predecessor-not-found",
                "canonical predecessor QRI does not exist",
            )
        predecessor = self._read_qri_row(predecessor_row)
        drafts = self.query_accepted_artifact_drafts(canonical_artifact_id)
        snapshots = self.query_accepted_artifact_snapshots(canonical_artifact_id)
        proof = self.query_accepted_artifact_compatibility(canonical_artifact_id)
        branch_id = self.query_draft(drafts.genesis.draft_id).branch_id

        if (
            predecessor.qualification_revision != 1
            or predecessor.predecessor_qualification_id is not None
            or predecessor.capabilities
            != CapabilityManifest.accepted_artifact_dormant()
            or predecessor.provider_authority
            != _DORMANT_ARTIFACT_PROVIDER_AUTHORITY
            or predecessor.profile_id != drafts.profile_id
            or predecessor.genesis_branch_id != branch_id
            or predecessor.genesis_snapshot_id != snapshots.genesis.snapshot_id
            or predecessor.knowledge_snapshot_id
            != snapshots.knowledge.snapshot_id
            or predecessor.isolation_proof != self.isolation_proof
            or predecessor.compatibility_proof != proof.integrity_digest
            or proof.genesis_snapshot_id != snapshots.genesis.snapshot_id
            or proof.knowledge_snapshot_id != snapshots.knowledge.snapshot_id
        ):
            raise StudioRejected(
                "successor-predecessor-lineage-mismatch",
                "predecessor is not the canonical dormant QRI for this artifact",
            )
        if len(predecessor.policy_decision_ids) != 1:
            raise StudioFailedClosed(
                "successor-predecessor-integrity-failed",
                "dormant predecessor must bind exactly one PolicyDecision",
            )
        expected_predecessor_publication_digest = _digest(
            {
                "artifact_id": drafts.artifact_id,
                "genesis_snapshot_id": snapshots.genesis.snapshot_id,
                "knowledge_snapshot_id": snapshots.knowledge.snapshot_id,
                "policy_decision_id": predecessor.policy_decision_ids[0],
                "compatibility_proof_id": proof.proof_id,
                "qri_integrity_digest": predecessor.integrity_digest,
            }
        )
        if str(predecessor_row[0]) != expected_predecessor_publication_digest:
            raise StudioFailedClosed(
                "successor-predecessor-integrity-failed",
                "dormant predecessor publication no longer binds the artifact proof",
            )

        policy = self._read_policy_decision(policy_decision_id)
        question = self._accepted_artifact_policy_question(
            canonical_artifact_id,
            policy.capability_manifest,
        )
        revalidation = self._policy_kernel.revalidate(policy, question)
        if (
            policy.decision_id in predecessor.policy_decision_ids
            or revalidation.disposition is not PolicyDisposition.QUALIFIED
            or policy.capability_manifest
            != CapabilityManifest._local_first_test_double()
        ):
            raise StudioRejected(
                "successor-policy-not-qualified",
                "a new qualified local-test PolicyDecision is required",
            )

        phase1_command, phase1_idempotency_key, phase1_confirmed_brief = (
            _local_first_phase1_test_interaction(
                predecessor_qualification_id=predecessor.qualification_id,
                profile_id=predecessor.profile_id,
                successor_publication_key=publication_key,
            )
        )
        interaction_basis_digest = _local_first_interaction_basis_digest(
            profile_id=predecessor.profile_id,
            timeline_id=phase1_command.target_timeline_id,
            command_fingerprint=phase1_command.payload_fingerprint,
            idempotency_key_digest=hashlib.sha256(
                phase1_idempotency_key.encode("utf-8")
            ).hexdigest(),
            confirmed_brief_digest=hashlib.sha256(
                phase1_confirmed_brief.encode("utf-8")
            ).hexdigest(),
        )

        qualification_id = str(
            uuid5(
                NAMESPACE_URL,
                (
                    "accepted-artifact-local-successor-qri:"
                    f"{self._location.root_id}:{publication_key}"
                ),
            )
        )
        published_at_us = (
            _utc_microseconds()
            if _published_at_us is None
            else int(_published_at_us)
        )
        if published_at_us < 1:
            raise StudioRejected(
                "local-successor-plan-mismatch",
                "QRI publication time must be positive",
            )
        compatibility_proof = _local_first_successor_compatibility_digest(
            predecessor_qualification_id=predecessor.qualification_id,
            predecessor_integrity_digest=predecessor.integrity_digest,
            predecessor_compatibility_proof=proof.integrity_digest,
            policy_decision_id=policy.decision_id,
            capability_manifest=policy.capability_manifest,
            provider_authority=_LOCAL_FIRST_TEST_PROVIDER_AUTHORITY,
            interaction_basis_digest=interaction_basis_digest,
        )
        unsigned = {
            "qualification_id": qualification_id,
            "qualification_revision": predecessor.qualification_revision + 1,
            "profile_id": predecessor.profile_id,
            "genesis_branch_id": predecessor.genesis_branch_id,
            "genesis_snapshot_id": predecessor.genesis_snapshot_id,
            "knowledge_snapshot_id": predecessor.knowledge_snapshot_id,
            "policy_decision_ids": [policy.decision_id],
            "capabilities": policy.capability_manifest.to_dict(),
            "isolation_proof": predecessor.isolation_proof.to_dict(),
            "provider_authority": _LOCAL_FIRST_TEST_PROVIDER_AUTHORITY,
            "compatibility_proof": compatibility_proof,
            "predecessor_qualification_id": predecessor.qualification_id,
            "publication_key": publication_key,
            "published_at_us": published_at_us,
        }
        payload = {**unsigned, "integrity_digest": _digest(unsigned)}
        publication_digest = _digest(
            {
                "artifact_id": drafts.artifact_id,
                "predecessor_qualification_id": predecessor.qualification_id,
                "predecessor_integrity_digest": predecessor.integrity_digest,
                "predecessor_publication_digest": str(predecessor_row[0]),
                "genesis_snapshot_id": snapshots.genesis.snapshot_id,
                "knowledge_snapshot_id": snapshots.knowledge.snapshot_id,
                "accepted_artifact_compatibility_proof": proof.integrity_digest,
                "policy_decision_id": policy.decision_id,
                "capability_manifest": policy.capability_manifest.to_dict(),
                "provider_authority": _LOCAL_FIRST_TEST_PROVIDER_AUTHORITY,
                "interaction_basis_digest": interaction_basis_digest,
                "successor_integrity_digest": payload["integrity_digest"],
            }
        )

        try:
            _begin(self._writer)
            for successor_row in self._writer.execute(
                """
                SELECT publication_digest, qri_json, integrity_digest
                FROM qri_publication
                """
            ).fetchall():
                published = self._read_qri_row(successor_row)
                if (
                    published.predecessor_qualification_id
                    == predecessor.qualification_id
                    and published.publication_key != publication_key
                ):
                    raise StudioConflict(
                        "successor-already-published",
                        "dormant predecessor already has a local successor",
                    )
            existing = self._writer.execute(
                """
                SELECT publication_digest, qri_json, integrity_digest
                FROM qri_publication WHERE publication_key = ?
                """,
                (publication_key,),
            ).fetchone()
            if existing is None:
                self._writer.execute(
                    """
                    INSERT INTO qri_publication (
                        qualification_id, publication_key, publication_digest,
                        qri_json, integrity_digest, created_at_us
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        qualification_id,
                        publication_key,
                        publication_digest,
                        _canonical_json(payload),
                        payload["integrity_digest"],
                        published_at_us,
                    ),
                )
                existing = self._writer.execute(
                    """
                    SELECT publication_digest, qri_json, integrity_digest
                    FROM qri_publication WHERE publication_key = ?
                    """,
                    (publication_key,),
                ).fetchone()
            elif str(existing[0]) != publication_digest:
                raise StudioConflict(
                    "publication-key-conflict",
                    "publication key already names a different qualification",
                )
            _commit(self._writer)
        except Exception:
            _rollback_if_needed(self._writer)
            raise
        if existing is None:
            raise StudioFailedClosed(
                "qri-publication-missing",
                "local successor QRI disappeared during publication",
            )
        return self._read_qri_row(existing)

    def _publish_accepted_artifact_local_llama_successor_qri(
        self,
        artifact_id: str,
        *,
        predecessor_qualification_id: str,
        policy_decision_id: str,
        publication_key: str,
        _published_at_us: int | None = None,
        _corrective_authority: object | None = None,
        _corrective_timeline_id: str | None = None,
        _corrective_preparation_digest: str | None = None,
        _corrective_policy: PolicyDecision | None = None,
        _corrective_predecessor_policy_id: str | None = None,
        _corrective_predecessor_policy_integrity_digest: str | None = None,
        _corrective_fault_hook: Callable[[str], None] | None = None,
    ) -> QualifiedRuntimeInput:
        """Append the production local-llama successor of one dormant QRI.

        The caller supplies stable identities, never provider selection or
        Profile/Genesis/Knowledge content.  This seam re-reads every canonical
        predecessor and accepted-artifact basis before publishing, and binds
        the one deterministic production command/brief plan.
        """

        self._require_authority()
        canonical_artifact_id = _canonical_uuid(artifact_id, "artifact_id")
        canonical_predecessor_id = _canonical_uuid(
            predecessor_qualification_id,
            "predecessor_qualification_id",
        )
        if not isinstance(publication_key, str) or not _PUBLICATION_KEY.fullmatch(
            publication_key
        ):
            raise StudioRejected(
                "invalid-publication-key",
                "publication key must be a stable opaque identifier",
            )

        corrective = (
            _corrective_authority is _CORRECTIVE_LOCAL_LLAMA_SUCCESSOR_AUTHORITY
        )
        if (_corrective_policy is not None or _corrective_fault_hook is not None) and not corrective:
            raise StudioRejected(
                "corrective-successor-authority-required",
                "corrective policy publication requires private authority",
            )

        predecessor_row = self._writer.execute(
            """
            SELECT publication_digest, qri_json, integrity_digest
            FROM qri_publication WHERE qualification_id = ?
            """,
            (canonical_predecessor_id,),
        ).fetchone()
        if predecessor_row is None:
            raise StudioRejected(
                "successor-predecessor-not-found",
                "canonical predecessor QRI does not exist",
            )
        predecessor = self._read_qri_row(predecessor_row)
        proof = self.query_accepted_artifact_compatibility(canonical_artifact_id)
        if corrective:
            # The corrective path is deliberately source-text-free.  Its
            # canonical predecessor and compatibility proof already commit to
            # the accepted artifact, Profile, Genesis and Knowledge identities.
            artifact_profile_row = self._open_artifact_sidecar(create=False)
            try:
                artifact_profile = artifact_profile_row.execute(
                    "SELECT profile_id FROM accepted_artifact WHERE artifact_id = ?",
                    (canonical_artifact_id,),
                ).fetchone()
            finally:
                artifact_profile_row.close()
            if artifact_profile is None:
                raise StudioRejected(
                    "accepted-artifact-not-found",
                    "corrective artifact identity does not exist",
                )
            profile_id = str(artifact_profile[0])
            genesis_snapshot_id = predecessor.genesis_snapshot_id
            knowledge_snapshot_id = predecessor.knowledge_snapshot_id
            branch_id = predecessor.genesis_branch_id
        else:
            drafts = self.query_accepted_artifact_drafts(canonical_artifact_id)
            snapshots = self.query_accepted_artifact_snapshots(canonical_artifact_id)
            branch_id = self.query_draft(drafts.genesis.draft_id).branch_id
            profile_id = drafts.profile_id
            genesis_snapshot_id = snapshots.genesis.snapshot_id
            knowledge_snapshot_id = snapshots.knowledge.snapshot_id

        if (
            predecessor.qualification_revision != 1
            or predecessor.predecessor_qualification_id is not None
            or predecessor.capabilities
            != CapabilityManifest.accepted_artifact_dormant()
            or predecessor.provider_authority
            != _DORMANT_ARTIFACT_PROVIDER_AUTHORITY
            or predecessor.profile_id != profile_id
            or predecessor.genesis_branch_id != branch_id
            or predecessor.genesis_snapshot_id != genesis_snapshot_id
            or predecessor.knowledge_snapshot_id != knowledge_snapshot_id
            or predecessor.isolation_proof != self.isolation_proof
            or predecessor.compatibility_proof != proof.integrity_digest
            or proof.genesis_snapshot_id != genesis_snapshot_id
            or proof.knowledge_snapshot_id != knowledge_snapshot_id
        ):
            raise StudioRejected(
                "successor-predecessor-lineage-mismatch",
                "predecessor is not the canonical dormant QRI for this artifact",
            )
        if len(predecessor.policy_decision_ids) != 1:
            raise StudioFailedClosed(
                "successor-predecessor-integrity-failed",
                "dormant predecessor must bind exactly one PolicyDecision",
            )
        expected_predecessor_publication_digest = _digest(
            {
                "artifact_id": canonical_artifact_id,
                "genesis_snapshot_id": genesis_snapshot_id,
                "knowledge_snapshot_id": knowledge_snapshot_id,
                "policy_decision_id": predecessor.policy_decision_ids[0],
                "compatibility_proof_id": proof.proof_id,
                "qri_integrity_digest": predecessor.integrity_digest,
            }
        )
        legacy_predecessor_publication_digest = _digest(
            {
                "artifact_id": canonical_artifact_id,
                "genesis_snapshot_id": genesis_snapshot_id,
                "knowledge_snapshot_id": knowledge_snapshot_id,
                "policy_decision_id": predecessor.policy_decision_ids[0],
                "compatibility_proof_id": proof.proof_id,
            }
        )
        if str(predecessor_row[0]) not in (
            expected_predecessor_publication_digest,
            legacy_predecessor_publication_digest,
        ):
            raise StudioFailedClosed(
                "successor-predecessor-integrity-failed",
                "dormant predecessor publication no longer binds the artifact proof",
            )

        if corrective:
            if not isinstance(_corrective_policy, PolicyDecision):
                raise StudioRejected(
                    "corrective-successor-plan-required",
                    "corrective publication must bind the complete PolicyDecision",
                )
            policy = _corrective_policy
            integrity_basis = {
                "question_digest": policy.question_digest,
                "policy_version": policy.policy_version,
                "issued_at_us": policy.issued_at_us,
                "valid_until_us": policy.valid_until_us,
                "disposition": policy.disposition.value,
                "reason_codes": list(policy.reason_codes),
                "decision_id": policy.decision_id,
                "capability_manifest": policy.capability_manifest.to_dict(),
            }
            nonconforming_policy_ids: set[str] = set()
            for row in self._writer.execute(
                "SELECT qri_json, publication_digest, integrity_digest FROM qri_publication"
            ).fetchall():
                candidate = self._read_qri_row((row[1], row[0], row[2]))
                if (
                    candidate.predecessor_qualification_id
                    == predecessor.qualification_id
                    and candidate.provider_authority == _LOCAL_LLAMA_PROVIDER_AUTHORITY
                    and candidate.qualification_revision
                    == predecessor.qualification_revision + 1
                ):
                    nonconforming_policy_ids.update(candidate.policy_decision_ids)
            if len(nonconforming_policy_ids) != 1:
                raise StudioRejected(
                    "corrective-policy-basis-mismatch",
                    "corrective policy requires the exact nonconforming predecessor",
                )
            nonconforming_policy = self._read_policy_decision(
                next(iter(nonconforming_policy_ids))
            )
            if (
                nonconforming_policy.decision_id
                != _canonical_uuid(
                    _corrective_predecessor_policy_id,
                    "corrective_predecessor_policy_id",
                )
                or nonconforming_policy.integrity_digest
                != _canonical_sha256(
                    _corrective_predecessor_policy_integrity_digest,
                    "corrective_predecessor_policy_integrity_digest",
                )
            ):
                raise StudioFailedClosed(
                    "corrective-policy-basis-mismatch",
                    "nonconforming PolicyDecision differs from the sealed plan",
                )
            policy_valid = (
                _digest(integrity_basis) == policy.integrity_digest
                and policy.decision_id == _canonical_uuid(policy_decision_id, "policy_decision_id")
                and policy.disposition is PolicyDisposition.QUALIFIED
                and policy.policy_version == POLICY_VERSION
                and policy.reason_codes
                == ("post-m0-06-corrective-local-llama-qualified",)
                and policy.question_digest == nonconforming_policy.question_digest
                and policy.valid_until_us >= policy.issued_at_us
            )
        else:
            policy = self._read_policy_decision(policy_decision_id)
            question = self._accepted_artifact_policy_question(
                canonical_artifact_id,
                policy.capability_manifest,
            )
            revalidation = self._policy_kernel.revalidate(policy, question)
            policy_valid = revalidation.disposition is PolicyDisposition.QUALIFIED
        if corrective and policy.decision_id in nonconforming_policy_ids:
            raise StudioRejected(
                "corrective-successor-policy-reused",
                "corrective publication requires a new PolicyDecision",
            )
        if (
            policy.decision_id in predecessor.policy_decision_ids
            or not policy_valid
            or policy.capability_manifest
            != CapabilityManifest._local_llama_experimental()
        ):
            raise StudioRejected(
                "successor-policy-not-qualified",
                "a new qualified local-llama PolicyDecision is required",
            )

        if _corrective_authority is not None and not corrective:
            raise StudioRejected(
                "corrective-successor-authority-required",
                "local-llama corrective publication requires private authority",
            )
        if _corrective_timeline_id is not None and not corrective:
            raise StudioRejected(
                "corrective-successor-authority-required",
                "only a corrective publication can retain the governed Timeline",
            )
        if corrective:
            if _corrective_timeline_id is None:
                raise StudioRejected(
                    "corrective-successor-plan-required",
                    "corrective publication must bind its governed Timeline",
                )
            corrective_preparation_digest = _canonical_sha256(
                _corrective_preparation_digest,
                "corrective_preparation_digest",
            )
        elif _corrective_preparation_digest is not None:
            raise StudioRejected(
                "corrective-successor-authority-required",
                "only a corrective publication can bind a preparation digest",
            )
        else:
            corrective_preparation_digest = None

        local_command, local_idempotency_key, local_confirmed_brief = (
            _local_first_phase3_local_interaction(
                predecessor_qualification_id=predecessor.qualification_id,
                profile_id=predecessor.profile_id,
                successor_publication_key=publication_key,
                _corrective_timeline_id=_corrective_timeline_id,
            )
        )
        interaction_basis_digest = _local_first_interaction_basis_digest(
            profile_id=predecessor.profile_id,
            timeline_id=local_command.target_timeline_id,
            command_fingerprint=local_command.payload_fingerprint,
            idempotency_key_digest=hashlib.sha256(
                local_idempotency_key.encode("utf-8")
            ).hexdigest(),
            confirmed_brief_digest=hashlib.sha256(
                local_confirmed_brief.encode("utf-8")
            ).hexdigest(),
        )

        qualification_id = str(
            uuid5(
                NAMESPACE_URL,
                (
                    "accepted-artifact-local-llama-successor-qri:"
                    f"{self._location.root_id}:{publication_key}"
                ),
            )
        )
        published_at_us = (
            _utc_microseconds()
            if _published_at_us is None
            else int(_published_at_us)
        )
        if published_at_us < 1:
            raise StudioRejected(
                "local-successor-plan-mismatch",
                "QRI publication time must be positive",
            )
        compatibility_proof = _local_first_successor_compatibility_digest(
            predecessor_qualification_id=predecessor.qualification_id,
            predecessor_integrity_digest=predecessor.integrity_digest,
            predecessor_compatibility_proof=proof.integrity_digest,
            policy_decision_id=policy.decision_id,
            capability_manifest=policy.capability_manifest,
            provider_authority=_LOCAL_LLAMA_PROVIDER_AUTHORITY,
            interaction_basis_digest=interaction_basis_digest,
        )
        unsigned = {
            "qualification_id": qualification_id,
            "qualification_revision": (
                predecessor.qualification_revision + (2 if corrective else 1)
            ),
            "profile_id": predecessor.profile_id,
            "genesis_branch_id": predecessor.genesis_branch_id,
            "genesis_snapshot_id": predecessor.genesis_snapshot_id,
            "knowledge_snapshot_id": predecessor.knowledge_snapshot_id,
            "policy_decision_ids": [policy.decision_id],
            "capabilities": policy.capability_manifest.to_dict(),
            "isolation_proof": predecessor.isolation_proof.to_dict(),
            "provider_authority": _LOCAL_LLAMA_PROVIDER_AUTHORITY,
            "compatibility_proof": compatibility_proof,
            "predecessor_qualification_id": predecessor.qualification_id,
            "publication_key": publication_key,
            "published_at_us": published_at_us,
        }
        payload = {**unsigned, "integrity_digest": _digest(unsigned)}
        publication_digest = _digest(
            {
                "artifact_id": canonical_artifact_id,
                "predecessor_qualification_id": predecessor.qualification_id,
                "predecessor_integrity_digest": predecessor.integrity_digest,
                "predecessor_publication_digest": str(predecessor_row[0]),
                "genesis_snapshot_id": genesis_snapshot_id,
                "knowledge_snapshot_id": knowledge_snapshot_id,
                "accepted_artifact_compatibility_proof": proof.integrity_digest,
                "policy_decision_id": policy.decision_id,
                "capability_manifest": policy.capability_manifest.to_dict(),
                "provider_authority": _LOCAL_LLAMA_PROVIDER_AUTHORITY,
                "interaction_basis_digest": interaction_basis_digest,
                **(
                    {
                        "corrective_preparation_digest": (
                            corrective_preparation_digest
                        )
                    }
                    if corrective
                    else {}
                ),
                "successor_integrity_digest": payload["integrity_digest"],
            }
        )

        try:
            _begin(self._writer)
            if corrective:
                existing_qri_before_policy = self._writer.execute(
                    "SELECT 1 FROM qri_publication WHERE publication_key = ?",
                    (publication_key,),
                ).fetchone()
                existing_policy = self._writer.execute(
                    "SELECT decision_json, integrity_digest FROM policy_decision WHERE decision_id = ?",
                    (policy.decision_id,),
                ).fetchone()
                policy_json = _canonical_json(policy.to_dict())
                if existing_policy is not None and existing_qri_before_policy is None:
                    raise StudioFailedClosed(
                        "corrective-policy-only-preimage",
                        "corrective PolicyDecision cannot pre-exist its QRI",
                    )
                if existing_policy is None:
                    self._writer.execute(
                        "INSERT INTO policy_decision (decision_id, decision_json, integrity_digest, created_at_us) VALUES (?, ?, ?, ?)",
                        (
                            policy.decision_id,
                            policy_json,
                            policy.integrity_digest,
                            policy.issued_at_us,
                        ),
                    )
                elif tuple(map(str, existing_policy)) != (
                    policy_json,
                    policy.integrity_digest,
                ):
                    raise StudioConflict(
                        "policy-identity-conflict",
                        "PolicyDecision identity already names different content",
                    )
                if _corrective_fault_hook is not None:
                    _corrective_fault_hook("after-policy-insert")
            matching_local_llama_successors = 0
            matching_local_llama_revisions: list[int] = []
            matching_local_llama_policy_ids: set[str] = set()
            for successor_row in self._writer.execute(
                """
                SELECT publication_digest, qri_json, integrity_digest
                FROM qri_publication
                """
            ).fetchall():
                published = self._read_qri_row(successor_row)
                if (
                    published.predecessor_qualification_id
                    == predecessor.qualification_id
                    and published.publication_key != publication_key
                ):
                    if (
                        published.provider_authority
                        == _LOCAL_LLAMA_PROVIDER_AUTHORITY
                    ):
                        matching_local_llama_successors += 1
                        matching_local_llama_revisions.append(
                            published.qualification_revision
                        )
                        matching_local_llama_policy_ids.update(
                            published.policy_decision_ids
                        )
                    else:
                        raise StudioConflict(
                            "successor-already-published",
                            "dormant predecessor already has a different successor",
                        )
            if matching_local_llama_successors and not (
                corrective and matching_local_llama_successors == 1
            ):
                raise StudioConflict(
                    "successor-already-published",
                    "dormant predecessor already has a local-llama successor",
                )
            if corrective and matching_local_llama_revisions != [
                predecessor.qualification_revision + 1
            ]:
                raise StudioConflict(
                    "corrective-successor-lineage-mismatch",
                    "corrective publication requires the one direct local successor",
                )
            if corrective and policy.decision_id in matching_local_llama_policy_ids:
                raise StudioRejected(
                    "corrective-successor-policy-reused",
                    "corrective publication requires a new PolicyDecision",
                )
            existing = self._writer.execute(
                """
                SELECT publication_digest, qri_json, integrity_digest,
                       qualification_id, created_at_us
                FROM qri_publication WHERE publication_key = ?
                """,
                (publication_key,),
            ).fetchone()
            if existing is None:
                self._writer.execute(
                    """
                    INSERT INTO qri_publication (
                        qualification_id, publication_key, publication_digest,
                        qri_json, integrity_digest, created_at_us
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        qualification_id,
                        publication_key,
                        publication_digest,
                        _canonical_json(payload),
                        payload["integrity_digest"],
                        published_at_us,
                    ),
                )
                existing = self._writer.execute(
                    """
                    SELECT publication_digest, qri_json, integrity_digest,
                           qualification_id, created_at_us
                    FROM qri_publication WHERE publication_key = ?
                    """,
                    (publication_key,),
                ).fetchone()
            elif (
                str(existing[0]) != publication_digest
                or str(existing[1]) != _canonical_json(payload)
                or str(existing[2]) != payload["integrity_digest"]
                or str(existing[3]) != qualification_id
                or int(existing[4]) != published_at_us
            ):
                raise StudioConflict(
                    "publication-key-conflict",
                    "publication key already names a different qualification",
                )
            _commit(self._writer)
        except Exception:
            _rollback_if_needed(self._writer)
            raise
        if existing is None:
            raise StudioFailedClosed(
                "qri-publication-missing",
                "local-llama successor QRI disappeared during publication",
            )
        return self._read_qri_row(existing[:3])

    def authority_counts(self) -> dict[str, int]:
        self._require_open()
        if not self._artifact_sidecar_database.exists():
            return {
                "accepted_artifact_draft": 0,
                "freeze_decision": 0,
                "freeze_attempt": 0,
                "sealed_genesis": 0,
                "sealed_knowledge": 0,
            }
        sidecar = self._open_artifact_sidecar(create=False)
        try:
            draft_count = int(
                sidecar.execute("SELECT COUNT(*) FROM accepted_artifact").fetchone()[0]
            )
            freeze_count = int(
                sidecar.execute("SELECT COUNT(*) FROM freeze_attempt").fetchone()[0]
            )
            decision_count = int(
                sidecar.execute("SELECT COUNT(*) FROM freeze_decision").fetchone()[0]
            )
            scope_counts = {
                str(row[0]): int(row[1])
                for row in sidecar.execute(
                    "SELECT scope, COUNT(*) FROM sealed_snapshot GROUP BY scope"
                ).fetchall()
            }
        finally:
            sidecar.close()
        return {
            "accepted_artifact_draft": draft_count,
            "freeze_decision": decision_count,
            "freeze_attempt": freeze_count,
            "sealed_genesis": scope_counts.get("genesis", 0),
            "sealed_knowledge": scope_counts.get("knowledge", 0),
        }

    @staticmethod
    def _read_artifact_activation_evidence(
        path: Path,
        *,
        expected_sha256: str,
        label: str,
    ) -> tuple[dict[str, Any], str]:
        record = Path(path)
        if not record.is_absolute():
            raise StudioRejected(
                "artifact-activation-evidence-invalid",
                f"{label} must use an explicit absolute path",
            )
        try:
            anchor = Path(record.anchor).resolve(strict=True)
            if (
                not record.is_file()
                or record.is_symlink()
                or record.stat().st_nlink != 1
                or _has_linklike_component(record, anchor)
            ):
                raise OSError("evidence is absent or linked")
            raw = record.read_bytes()
        except OSError as error:
            raise StudioRejected(
                "artifact-activation-evidence-invalid",
                f"{label} is absent, linked, or unreadable",
            ) from error
        actual_sha256 = hashlib.sha256(raw).hexdigest()
        if actual_sha256 != expected_sha256:
            raise StudioRejected(
                "artifact-activation-evidence-invalid",
                f"{label} does not match its frozen SHA-256",
            )
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise StudioRejected(
                "artifact-activation-evidence-invalid",
                f"{label} is not UTF-8 JSON",
            ) from error
        if not isinstance(payload, dict):
            raise StudioRejected(
                "artifact-activation-evidence-invalid",
                f"{label} must be one JSON object",
            )
        return payload, actual_sha256

    @staticmethod
    def _artifact_activation_production_source_binding() -> dict[str, Any]:
        """Bind the complete mature production Python distribution, not a hand list."""

        package_root = Path(__file__).resolve().parent
        anchor = Path(package_root.anchor).resolve(strict=True)
        source_paths = tuple(sorted(package_root.rglob("*.py")))
        if not source_paths:
            raise StudioFailedClosed(
                "artifact-activation-source-inventory-invalid",
                "mature production source inventory is empty",
            )
        production_sources: dict[str, str] = {}
        for source_path in source_paths:
            try:
                if (
                    not source_path.is_file()
                    or source_path.is_symlink()
                    or source_path.stat().st_nlink != 1
                    or _has_linklike_component(source_path, anchor)
                ):
                    raise OSError("production source is absent or linked")
                relative = source_path.relative_to(package_root).as_posix()
                production_sources[relative] = hashlib.sha256(
                    source_path.read_bytes()
                ).hexdigest()
            except (OSError, ValueError) as error:
                raise StudioFailedClosed(
                    "artifact-activation-source-inventory-invalid",
                    "mature production source inventory is unsafe or unreadable",
                ) from error
        return {
            "files": production_sources,
            "file_count": len(production_sources),
            "fingerprint": _digest(production_sources),
        }

    @classmethod
    def _classify_artifact_activation_target(
        cls,
        *,
        plan: _AcceptedArtifactExperimentalActivationPlan,
    ) -> str:
        """Accept only absent, exact same-plan staging, or exact visible state."""

        target = plan.bundle_base
        if not target.exists():
            return "absent"
        _validate_reserved_artifact_activation_base(target, create=False)
        m0 = Path("mature-runtime-m0")
        studio = m0 / "roots" / plan.studio_root_id
        profile = studio / "profiles" / plan.profile_store_id / "profile.sqlite3"
        sidecar = (
            studio
            / "accepted-artifact-snapshots"
            / "snapshot-authority.sqlite3"
        )
        host = m0 / "host-roots" / plan.host_root_id
        timeline_root = (
            host / "mature-runtime-m0" / "roots" / plan.timeline_root_id
        )
        timeline_database = (
            timeline_root / "timelines" / plan.timeline_id / "timeline.sqlite3"
        )
        control_databases = (
            profile,
            sidecar,
            host / "control" / "host.sqlite3",
            timeline_root / "control" / "control.sqlite3",
            timeline_database,
        )
        allowed_files = {
            studio / "root.identity",
            profile,
            sidecar,
            host / "root.identity",
            host / "control" / "host.sqlite3",
            timeline_root / "root.identity",
            timeline_root / "control" / "control.sqlite3",
            timeline_database,
        }
        allowed = {
            m0,
            m0 / "roots",
            studio,
            studio / "profiles",
            studio / "profiles" / plan.profile_store_id,
            studio / "accepted-artifact-snapshots",
            m0 / "host-roots",
            host,
            host / "control",
            host / "mature-runtime-m0",
            host / "mature-runtime-m0" / "roots",
            timeline_root,
            timeline_root / "control",
            timeline_root / "timelines",
            timeline_root / "timelines" / plan.timeline_id,
        } | allowed_files
        journal_files = {
            Path(f"{database.as_posix()}-journal")
            for database in control_databases
        }
        allowed_files.update(journal_files)
        allowed.update(journal_files)
        actual: set[Path] = set()
        try:
            for candidate in target.rglob("*"):
                relative = candidate.relative_to(target)
                actual.add(relative)
                if (
                    relative not in allowed
                    or _is_linklike(candidate)
                    or (
                        relative in allowed_files
                        and not candidate.is_file()
                    )
                    or (
                        relative not in allowed_files
                        and not candidate.is_dir()
                    )
                    or (
                        candidate.is_file()
                        and candidate.stat().st_nlink != 1
                    )
                ):
                    raise OSError("unexpected or linked recovery content")
        except (OSError, ValueError) as error:
            raise StudioRejected(
                "artifact-activation-recovery-mismatch",
                "existing activation target is not exact same-plan recovery state",
            ) from error
        empty_staging = {m0, m0 / "roots"}
        studio_root = target / studio
        if not studio_root.exists():
            if not actual.issubset(empty_staging):
                raise StudioRejected(
                    "artifact-activation-recovery-mismatch",
                    "pre-Studio recovery target contains unexpected state",
                )
            return "recoverable-same-plan"

        studio_location = StudioRootRef(
            root_path=str(studio_root),
            root_id=plan.studio_root_id,
            profile_store_id=plan.profile_store_id,
            root_kind=plan.root_kind,
        )
        opened = cls.open(studio_location, policy_kernel=PolicyKernel())
        try:
            try:
                sidecar_connection = opened._open_artifact_sidecar(create=False)
            except StudioProblem as error:
                if error.code != "accepted-artifact-not-found":
                    raise
                activation_ids: tuple[str, ...] = ()
            else:
                try:
                    activation_ids = tuple(
                        str(row[0])
                        for row in sidecar_connection.execute(
                            "SELECT activation_id FROM activation_receipt "
                            "ORDER BY activation_id"
                        ).fetchall()
                    )
                finally:
                    sidecar_connection.close()
        finally:
            opened.close()
        if activation_ids and activation_ids != (plan.activation_id,):
            raise StudioRejected(
                "artifact-activation-recovery-mismatch",
                "existing target contains a foreign activation receipt",
            )
        host_root = target / host
        if host_root.exists():
            from dynamic_subject_agent.host import (
                RuntimeHostRootRef,
                _read_root_identity as _read_host_root_identity,
                _validate_existing_root as _validate_host_root,
            )

            host_location = RuntimeHostRootRef(
                root_path=str(host_root),
                root_id=plan.host_root_id,
                control_store_id=plan.host_control_store_id,
                root_kind=plan.root_kind,
            )
            _validate_host_root(
                host_root,
                plan.host_root_id,
                root_kind=plan.root_kind,
                studio_location=studio_location,
            )
            _read_host_root_identity(host_location, studio_location)
        timeline_path = target / timeline_root
        if timeline_path.exists():
            if not host_root.exists():
                raise StudioRejected(
                    "artifact-activation-recovery-mismatch",
                    "Timeline recovery state has no matching Host root",
                )
            from dynamic_subject_agent.timeline import (
                _read_root_identity as _read_timeline_root_identity,
                _validate_existing_root as _validate_timeline_root,
            )

            _validate_timeline_root(
                timeline_path,
                plan.timeline_root_id,
                root_kind=plan.root_kind,
            )
            _read_timeline_root_identity(
                timeline_path,
                plan.timeline_root_id,
                plan.root_kind,
            )
        try:
            receipt = cls._query_accepted_artifact_activation_test(
                plan.bundle_base,
                plan.artifact_id,
                _plan=plan,
                _authority=_CONFIRMED_ARTIFACT_ACTIVATION_TOKEN,
            )
        except StudioRejected as error:
            if error.code != "artifact-activation-not-visible":
                raise
            return "recoverable-same-plan"
        if (
            receipt.activation_id != plan.activation_id
            or receipt.plan_digest != plan.plan_digest
        ):
            raise StudioRejected(
                "artifact-activation-recovery-mismatch",
                "visible authority differs from the frozen activation plan",
            )
        return "visible-same-plan"

    @classmethod
    def _load_exact_accepted_artifact_for_preview(
        cls,
        *,
        phase_2_preview: Mapping[str, Any],
    ) -> tuple[UnpublishedSubjectStudioArtifact, dict[str, Any]]:
        exact = phase_2_preview.get("exact_accepted_artifact")
        if not isinstance(exact, Mapping):
            raise StudioRejected(
                "artifact-activation-evidence-invalid",
                "Phase 2 preview has no exact accepted artifact",
            )
        root = Path(str(exact.get("artifact_root", "")))
        database = root / "offline-authoring.sqlite3"
        try:
            anchor = Path(root.anchor).resolve(strict=True)
            if (
                not root.is_absolute()
                or not root.is_dir()
                or _has_linklike_component(root, anchor)
                or {entry.name for entry in root.iterdir()}
                != {"offline-authoring.sqlite3"}
                or not database.is_file()
                or database.is_symlink()
                or database.stat().st_nlink != 1
                or _has_linklike_component(database, anchor)
            ):
                raise OSError("artifact root or database is unsafe")
            before = database.read_bytes()
            before_mtime = database.stat().st_mtime_ns
        except OSError as error:
            raise StudioRejected(
                "accepted-artifact-exact-root-invalid",
                "exact accepted artifact root is absent, linked, or not singular",
            ) from error
        database_sha256 = hashlib.sha256(before).hexdigest()
        if database_sha256 != exact.get("artifact_database_sha256"):
            raise StudioRejected(
                "accepted-artifact-exact-root-invalid",
                "exact artifact database digest changed",
            )
        try:
            connection = sqlite3.connect(
                _sqlite_uri(database, "ro"),
                uri=True,
                autocommit=True,
                timeout=2.0,
            )
            connection.execute("PRAGMA query_only = ON")
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            schema = connection.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type = 'table' ORDER BY name"
            ).fetchall()
            rows = connection.execute(
                "SELECT subset_digest, payload FROM artifact"
            ).fetchall()
        except sqlite3.Error as error:
            raise StudioRejected(
                "accepted-artifact-exact-root-invalid",
                "exact artifact database cannot be read safely",
            ) from error
        finally:
            try:
                connection.close()
            except UnboundLocalError:
                pass
        if (
            integrity != ("ok",)
            or schema
            != [
                (
                    "artifact",
                    "CREATE TABLE artifact "
                    "(subset_digest TEXT PRIMARY KEY, payload TEXT NOT NULL)",
                )
            ]
            or len(rows) != 1
        ):
            raise StudioRejected(
                "accepted-artifact-exact-root-invalid",
                "exact artifact store schema, integrity, or cardinality changed",
            )
        subset_digest, payload_json = rows[0]
        payload_sha256 = hashlib.sha256(
            str(payload_json).encode("utf-8")
        ).hexdigest()
        if (
            subset_digest != exact.get("subset_digest")
            or payload_sha256 != exact.get("artifact_payload_sha256")
        ):
            raise StudioRejected(
                "accepted-artifact-exact-root-invalid",
                "exact artifact row differs from the accepted payload",
            )
        try:
            payload = json.loads(str(payload_json))
            provenance_payload = payload["provenance"]
            genesis_payload = payload["genesis"]
            knowledge_payload = payload["knowledge"]
            provenance = ArtifactProvenance(
                manifest_id=str(provenance_payload["manifest_id"]),
                manifest_digest=str(provenance_payload["manifest_digest"]),
                report_digest=str(provenance_payload["report_digest"]),
                subset_digest=str(provenance_payload["subset_digest"]),
                source_ids=tuple(provenance_payload["source_ids"]),
                source_hashes=tuple(provenance_payload["source_hashes"]),
                rights_basis=str(provenance_payload["rights_basis"]),
                declared_use=str(provenance_payload["declared_use"]),
                artifact_root=str(provenance_payload["artifact_root"]),
            )
            artifact = UnpublishedSubjectStudioArtifact(
                artifact_id=str(payload["artifact_id"]),
                genesis=UnsealedGenesisArtifact(
                    candidate_id=str(genesis_payload["candidate_id"]),
                    authored_origin_document=str(
                        genesis_payload["authored_origin_document"]
                    ),
                    content_digest=str(genesis_payload["content_digest"]),
                ),
                knowledge=UnsealedKnowledgeArtifact(
                    candidate_id=str(knowledge_payload["candidate_id"]),
                    source_documents=tuple(knowledge_payload["source_documents"]),
                    content_digest=str(knowledge_payload["content_digest"]),
                ),
                provenance=provenance,
                published=payload["published"],
                unsealed=payload["unsealed"],
                authority_counts=dict(payload["authority_counts"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise StudioRejected(
                "accepted-artifact-exact-root-invalid",
                "exact artifact payload is structurally invalid",
            ) from error
        source_document = artifact.genesis.authored_origin_document
        source_sha256 = hashlib.sha256(source_document.encode("utf-8")).hexdigest()
        expected_zero_counts = {
            "qualified_runtime_input": 0,
            "runtime_binding": 0,
            "runtime_timeline": 0,
            "operation": 0,
            "timeline_outcome": 0,
            "effect": 0,
            "physical_clear": 0,
        }
        if (
            artifact.artifact_id != exact.get("artifact_id")
            or artifact.genesis.candidate_id != exact.get("genesis_draft_id")
            or artifact.knowledge.candidate_id != exact.get("knowledge_draft_id")
            or artifact.provenance.subset_digest != exact.get("subset_digest")
            or artifact.provenance.source_hashes != (exact.get("source_sha256"),)
            or source_sha256 != exact.get("source_sha256")
            or artifact.genesis.content_digest != source_sha256
            or artifact.knowledge.content_digest != source_sha256
            or artifact.knowledge.source_documents != (source_document,)
            or Path(artifact.provenance.artifact_root).resolve(strict=True)
            != root.resolve(strict=True)
            or not artifact.provenance.rights_basis.strip()
            or artifact.provenance.declared_use
            != "local-private-subjectstudio-authoring"
            or artifact.published
            or not artifact.unsealed
            or artifact.authority_counts != expected_zero_counts
        ):
            raise StudioRejected(
                "accepted-artifact-exact-root-invalid",
                "exact artifact identity, source, rights, use, or zero authority changed",
            )
        after = database.read_bytes()
        after_mtime = database.stat().st_mtime_ns
        if before != after or before_mtime != after_mtime:
            raise StudioFailedClosed(
                "accepted-artifact-readonly-violation",
                "exact artifact changed during the read-only verification",
            )
        return artifact, {
            "artifact_root": str(root),
            "database_path": str(database),
            "artifact_database_sha256": database_sha256,
            "artifact_payload_sha256": payload_sha256,
            "source_sha256": source_sha256,
            "document_utf8_bytes": len(source_document.encode("utf-8")),
            "database_mtime_ns_before": before_mtime,
            "database_mtime_ns_after": after_mtime,
            "sqlite_integrity_check": "ok",
            "table_count": 1,
            "row_count": 1,
        }

    @classmethod
    def _experimental_artifact_plan_from_phase_two(
        cls,
        *,
        phase_2_preview: Mapping[str, Any],
        artifact: UnpublishedSubjectStudioArtifact,
        input_facts: Mapping[str, Any],
        mapping: _DormantArtifactMapping,
    ) -> _AcceptedArtifactExperimentalActivationPlan:
        proposed = phase_2_preview.get("proposed_new_isolated_authority")
        if not isinstance(proposed, Mapping):
            raise StudioRejected(
                "artifact-activation-evidence-invalid",
                "Phase 2 preview has no proposed isolated authority",
            )
        activation_id = _canonical_uuid(
            str(proposed.get("experiment_id", "")),
            "activation_id",
        )
        bundle_base = Path(str(proposed.get("experiment_base", "")))
        _validate_reserved_artifact_activation_base(bundle_base, create=False)
        gate_parent = bundle_base.parent.parent / "artifact-activation-gates"
        activation_time_us = 1_786_233_600_000_000
        expected = {
            "studio_root_id": str(uuid5(NAMESPACE_URL, f"{activation_id}:studio-root")),
            "profile_store_id": str(
                uuid5(NAMESPACE_URL, f"{activation_id}:profile-store")
            ),
            "genesis_freeze_decision_id": str(
                uuid5(NAMESPACE_URL, f"{activation_id}:genesis-freeze-decision")
            ),
            "knowledge_freeze_decision_id": str(
                uuid5(NAMESPACE_URL, f"{activation_id}:knowledge-freeze-decision")
            ),
            "host_root_id": str(uuid5(NAMESPACE_URL, f"{activation_id}:host-root")),
            "host_control_store_id": str(
                uuid5(NAMESPACE_URL, f"{activation_id}:host-control-store")
            ),
            "timeline_id": str(uuid5(NAMESPACE_URL, f"{activation_id}:timeline")),
            "timeline_root_id": str(
                uuid5(NAMESPACE_URL, f"{activation_id}:timeline-root")
            ),
            "timeline_control_store_id": str(
                uuid5(NAMESPACE_URL, f"{activation_id}:timeline-control-store")
            ),
            "timeline_store_id": str(
                uuid5(NAMESPACE_URL, f"{activation_id}:timeline-store")
            ),
        }
        profile_id = str(
            uuid5(
                NAMESPACE_URL,
                "accepted-artifact-profile:"
                f"{expected['studio_root_id']}:{artifact.artifact_id}",
            )
        )
        qri_publication_key = f"post-m0-03-artifact-qri-{activation_id}"
        qualification_id = str(
            uuid5(
                NAMESPACE_URL,
                "accepted-artifact-qri:"
                f"{expected['studio_root_id']}:{qri_publication_key}",
            )
        )
        binding_id = str(
            uuid5(
                NAMESPACE_URL,
                "m0-12-binding:"
                f"{expected['host_root_id']}:{profile_id}:"
                f"{expected['timeline_id']}:{qualification_id}:1",
            )
        )
        authority_scope_id = str(
            uuid5(NAMESPACE_URL, f"m0-12-authority-scope:{binding_id}")
        )
        frozen = {
            **expected,
            "profile_id": profile_id,
            "qri_publication_key": qri_publication_key,
            "qualification_id": qualification_id,
            "binding_id": binding_id,
            "authority_scope_id": authority_scope_id,
        }
        if any(proposed.get(field) != value for field, value in frozen.items()):
            raise StudioRejected(
                "artifact-activation-plan-mismatch",
                "Phase 2 authority identities do not match their UUID5 derivation",
            )
        values: dict[str, Any] = {
            "activation_id": activation_id,
            "artifact_id": artifact.artifact_id,
            "bundle_base": str(bundle_base),
            **frozen,
            "policy_clock_us": activation_time_us,
            "activation_time_us": activation_time_us,
            "root_kind": EXPERIMENTAL_ROOT_KIND,
            "gate_parent": str(gate_parent),
            "phase_2_preview_sha256": _POST_M0_03_PHASE_2_PREVIEW_SHA256,
            "phase_2_confirmation_sha256": (
                _POST_M0_03_PHASE_2_CONFIRMATION_SHA256
            ),
            "artifact_database_sha256": input_facts[
                "artifact_database_sha256"
            ],
            "artifact_payload_sha256": input_facts["artifact_payload_sha256"],
            "source_sha256": input_facts["source_sha256"],
            "mapping_policy_version": mapping.policy_version,
            "mapping_digest": mapping.mapping_digest,
        }
        return _AcceptedArtifactExperimentalActivationPlan(
            activation_id=activation_id,
            artifact_id=artifact.artifact_id,
            bundle_base=bundle_base,
            studio_root_id=expected["studio_root_id"],
            profile_store_id=expected["profile_store_id"],
            profile_id=profile_id,
            genesis_freeze_decision_id=expected["genesis_freeze_decision_id"],
            knowledge_freeze_decision_id=expected[
                "knowledge_freeze_decision_id"
            ],
            qri_publication_key=qri_publication_key,
            qualification_id=qualification_id,
            timeline_id=expected["timeline_id"],
            host_root_id=expected["host_root_id"],
            host_control_store_id=expected["host_control_store_id"],
            binding_id=binding_id,
            authority_scope_id=authority_scope_id,
            timeline_root_id=expected["timeline_root_id"],
            timeline_control_store_id=expected["timeline_control_store_id"],
            timeline_store_id=expected["timeline_store_id"],
            policy_clock_us=activation_time_us,
            activation_time_us=activation_time_us,
            root_kind=EXPERIMENTAL_ROOT_KIND,
            gate_parent=gate_parent,
            plan_digest=_digest(values),
        )

    @classmethod
    def _prepare_exact_accepted_artifact_activation_preview(
        cls,
        *,
        phase_2_preview_record: Path,
        phase_2_confirmation_record: Path,
        _allow_matching_recovery_state: bool = False,
        _authority: object | None = None,
    ) -> dict[str, Any]:
        """Read exact accepted input and render the only Phase 4 plan, without writes."""

        phase_2, phase_2_sha256 = cls._read_artifact_activation_evidence(
            phase_2_preview_record,
            expected_sha256=_POST_M0_03_PHASE_2_PREVIEW_SHA256,
            label="Phase 2 activation-basis preview",
        )
        confirmation, confirmation_sha256 = cls._read_artifact_activation_evidence(
            phase_2_confirmation_record,
            expected_sha256=_POST_M0_03_PHASE_2_CONFIRMATION_SHA256,
            label="Phase 2 confirmation",
        )
        reference = confirmation.get("preview")
        if (
            phase_2.get("evidence_contract")
            != "POST-M0-03-HITL-PHASE-2-ACTIVATION-BASIS-PREVIEW-1.0"
            or confirmation.get("status")
            != "user-confirmed-phase-3-read-only-preview-only"
            or not isinstance(reference, Mapping)
            or reference.get("sha256") != phase_2_sha256
        ):
            raise StudioRejected(
                "artifact-activation-evidence-invalid",
                "Phase 2 preview and confirmation do not authorize Phase 3",
            )
        artifact, input_facts = cls._load_exact_accepted_artifact_for_preview(
            phase_2_preview=phase_2
        )
        mapping = cls._map_accepted_artifact_to_dormant_basis(
            artifact.genesis.authored_origin_document
        )
        plan = cls._experimental_artifact_plan_from_phase_two(
            phase_2_preview=phase_2,
            artifact=artifact,
            input_facts=input_facts,
            mapping=mapping,
        )
        source = SourceDeclaration(
            source_id=artifact.provenance.source_ids[0],
            origin_kind="project-original",
            rights_confirmed=True,
            source_asset_refs=(),
            uses_disallowed_inheritance=False,
        )
        profile = ParticipantProfile(
            profile_id=plan.profile_id,
            display_name=mapping.display_name,
            identity_core=mapping.identity_core,
            source=source,
        )
        premise = GenesisPremise(
            subject_identity=mapping.subject_identity,
            canon_start=mapping.canon_start,
            initial_relationship_premise=mapping.initial_relationship_premise,
            source=source,
        )
        branch_id = str(
            uuid5(
                NAMESPACE_URL,
                "accepted-artifact-branch:"
                f"{plan.studio_root_id}:{artifact.artifact_id}",
            )
        )
        proposed = phase_2["proposed_new_isolated_authority"]
        if branch_id != proposed.get("genesis_branch_id"):
            raise StudioRejected(
                "artifact-activation-plan-mismatch",
                "Phase 2 Genesis branch identity is not derivable",
            )
        profile_digest = _digest(profile.to_dict())
        premise_digest = _digest(premise.to_dict())
        provenance_payload = cls._accepted_artifact_payload(artifact)["provenance"]
        provenance_digest = _digest(provenance_payload)
        studio_genesis_basis = _digest(
            {
                "contract_version": CONTRACT_VERSION,
                "profile_id": plan.profile_id,
                "profile_digest": profile_digest,
                "draft_id": artifact.genesis.candidate_id,
                "branch_id": branch_id,
                "revision": 1,
                "content_digest": premise_digest,
                "predecessor_snapshot_id": None,
                "lineage_relation": "first-publication",
            }
        )
        genesis_freeze_basis = _digest(
            {
                "scope": "accepted-artifact-genesis",
                "artifact_id": artifact.artifact_id,
                "provenance_digest": provenance_digest,
                "studio_freeze_basis_digest": studio_genesis_basis,
            }
        )
        knowledge_payload = {
            "artifact_id": artifact.artifact_id,
            "draft_id": artifact.knowledge.candidate_id,
            "revision": 1,
            "source_documents": list(artifact.knowledge.source_documents),
            "content_digest": artifact.knowledge.content_digest,
            "source_ids": list(artifact.provenance.source_ids),
            "source_hashes": list(artifact.provenance.source_hashes),
            "rights_basis": artifact.provenance.rights_basis,
            "declared_use": artifact.provenance.declared_use,
        }
        knowledge_revision_digest = _digest(knowledge_payload)
        knowledge_freeze_basis = _digest(
            {
                "scope": "accepted-artifact-knowledge",
                "artifact_id": artifact.artifact_id,
                "provenance_digest": provenance_digest,
                "draft_id": artifact.knowledge.candidate_id,
                "revision": 1,
                "content_digest": knowledge_revision_digest,
            }
        )
        capabilities = CapabilityManifest.accepted_artifact_dormant()
        isolation = IsolationProof(
            root_id=plan.studio_root_id,
            root_kind=EXPERIMENTAL_ROOT_KIND,
            path_class="local-private-experimental",
            provenance_class="project-original-only",
        )
        combined_freeze_basis = _digest(
            {
                "contract_version": CONTRACT_VERSION,
                "artifact_id": artifact.artifact_id,
                "provenance_digest": provenance_digest,
                "genesis_freeze_basis_digest": genesis_freeze_basis,
                "knowledge_freeze_basis_digest": knowledge_freeze_basis,
            }
        )
        question_basis = {
            "contract_version": CONTRACT_VERSION,
            "profile_digest": profile_digest,
            "freeze_basis_digest": combined_freeze_basis,
            "capability_manifest": capabilities.to_dict(),
            "isolation_proof": isolation.to_dict(),
        }
        question = PolicyQuestion(
            question_digest=_digest(question_basis),
            profile_digest=profile_digest,
            freeze_basis_digest=combined_freeze_basis,
            capability_manifest=capabilities,
            isolation_proof=isolation,
            profile_source=source,
            genesis_source=source,
        )
        policy = PolicyKernel(clock=lambda: plan.policy_clock_us).decide(
            question,
            validity_us=10**18,
        )
        decisions = {
            "genesis": ScopedFreezeDecision(
                decision_id=plan.genesis_freeze_decision_id,
                scope="genesis",
                draft_id=artifact.genesis.candidate_id,
                expected_revision=1,
                freeze_basis_digest=genesis_freeze_basis,
                decided_by="post-m0-03-user-confirmed-local-activation",
                rationale="Freeze only the exact reviewed minimal Genesis mapping.",
            ),
            "knowledge": ScopedFreezeDecision(
                decision_id=plan.knowledge_freeze_decision_id,
                scope="knowledge",
                draft_id=artifact.knowledge.candidate_id,
                expected_revision=1,
                freeze_basis_digest=knowledge_freeze_basis,
                decided_by="post-m0-03-user-confirmed-local-activation",
                rationale="Freeze only the exact provenance-bound Knowledge member.",
            ),
        }
        snapshot_payloads: dict[str, dict[str, Any]] = {}
        for scope, decision in decisions.items():
            attempt_id = str(
                uuid5(
                    NAMESPACE_URL,
                    "accepted-artifact-freeze-attempt:"
                    f"{plan.studio_root_id}:{artifact.artifact_id}:"
                    f"{scope}:{decision.decision_id}",
                )
            )
            snapshot_id = str(
                uuid5(
                    NAMESPACE_URL,
                    "accepted-artifact-snapshot:"
                    f"{plan.studio_root_id}:{artifact.artifact_id}:"
                    f"{scope}:{decision.decision_id}",
                )
            )
            snapshot_payloads[scope] = {
                "snapshot_id": snapshot_id,
                "scope": scope,
                "artifact_id": artifact.artifact_id,
                "draft_id": decision.draft_id,
                "freeze_decision_id": decision.decision_id,
                "freeze_attempt_id": attempt_id,
                "policy_decision_id": policy.decision_id,
                "freeze_basis_digest": decision.freeze_basis_digest,
                "content_fingerprint": (
                    premise_digest
                    if scope == "genesis"
                    else artifact.knowledge.content_digest
                ),
                "provenance_digest": provenance_digest,
                "member_count": 0 if scope == "genesis" else 1,
                "created_at_us": plan.activation_time_us,
            }
        if (
            snapshot_payloads["genesis"]["freeze_attempt_id"]
            != proposed.get("genesis_freeze_attempt_id")
            or snapshot_payloads["knowledge"]["freeze_attempt_id"]
            != proposed.get("knowledge_freeze_attempt_id")
            or snapshot_payloads["genesis"]["snapshot_id"]
            != proposed.get("genesis_snapshot_id")
            or snapshot_payloads["knowledge"]["snapshot_id"]
            != proposed.get("knowledge_snapshot_id")
        ):
            raise StudioRejected(
                "artifact-activation-plan-mismatch",
                "Phase 2 snapshot identities are not derivable",
            )
        participant_identity_digest = _digest(
            {
                "profile_id": profile.profile_id,
                "identity_core": profile.identity_core,
                "subject_identity": premise.subject_identity,
                "reality_scope": "fictional-subject-private-experiment",
                "canon_scope": "initial-source-only",
                "mapping_policy_version": mapping.policy_version,
                "mapping_digest": mapping.mapping_digest,
            }
        )
        source_qualification_digest = _digest(
            {
                "provenance_digest": provenance_digest,
                "source_ids": list(artifact.provenance.source_ids),
                "source_hashes": list(artifact.provenance.source_hashes),
                "rights_basis": artifact.provenance.rights_basis,
                "declared_use": artifact.provenance.declared_use,
            }
        )
        knowledge_membership_digest = _digest(
            {
                "knowledge_snapshot_id": snapshot_payloads["knowledge"][
                    "snapshot_id"
                ],
                "member_count": 1,
                "source_hashes": list(artifact.provenance.source_hashes),
            }
        )
        prerequisites_digest = _digest(
            {
                "capabilities": capabilities.to_dict(),
                "policy_decision_id": policy.decision_id,
                "genesis_snapshot_id": snapshot_payloads["genesis"]["snapshot_id"],
                "knowledge_snapshot_id": snapshot_payloads["knowledge"][
                    "snapshot_id"
                ],
            }
        )
        proof_unsigned = {
            "artifact_id": artifact.artifact_id,
            "profile_id": profile.profile_id,
            "genesis_snapshot_id": snapshot_payloads["genesis"]["snapshot_id"],
            "knowledge_snapshot_id": snapshot_payloads["knowledge"]["snapshot_id"],
            "policy_decision_id": policy.decision_id,
            "capability_manifest_version": capabilities.manifest_version,
            "participant_identity_digest": participant_identity_digest,
            "source_qualification_digest": source_qualification_digest,
            "knowledge_membership_digest": knowledge_membership_digest,
            "prerequisites_digest": prerequisites_digest,
        }
        proof_id = str(
            uuid5(
                NAMESPACE_URL,
                "snapshot-compatibility-proof:"
                f"{plan.studio_root_id}:{_digest(proof_unsigned)}",
            )
        )
        proof_without_integrity = {"proof_id": proof_id, **proof_unsigned}
        proof = {
            **proof_without_integrity,
            "integrity_digest": _digest(proof_without_integrity),
        }
        qri_unsigned = {
            "qualification_id": plan.qualification_id,
            "qualification_revision": 1,
            "profile_id": profile.profile_id,
            "genesis_branch_id": branch_id,
            "genesis_snapshot_id": snapshot_payloads["genesis"]["snapshot_id"],
            "knowledge_snapshot_id": snapshot_payloads["knowledge"]["snapshot_id"],
            "policy_decision_ids": [policy.decision_id],
            "capabilities": capabilities.to_dict(),
            "isolation_proof": isolation.to_dict(),
            "provider_authority": _DORMANT_ARTIFACT_PROVIDER_AUTHORITY,
            "compatibility_proof": proof["integrity_digest"],
            "predecessor_qualification_id": None,
            "publication_key": plan.qri_publication_key,
            "published_at_us": plan.activation_time_us,
        }
        qri = {**qri_unsigned, "integrity_digest": _digest(qri_unsigned)}
        production_source_binding = (
            cls._artifact_activation_production_source_binding()
        )
        from dynamic_subject_agent.timeline import (
            _EMPTY_REVISION_HEAD_DIGEST,
            _EMPTY_VERIFIED_PREFIX_DIGEST,
        )

        target_state = cls._classify_artifact_activation_target(plan=plan)
        if target_state != "absent":
            if not (
                _allow_matching_recovery_state
                and _authority is _CONFIRMED_ARTIFACT_ACTIVATION_TOKEN
            ):
                raise StudioRejected(
                    "artifact-activation-target-not-new",
                    "exact new authority root is not absent before Phase 3 preview",
                )
        target_pre_state = "absent-or-same-plan-recoverable"
        return {
            "evidence_contract": (
                "POST-M0-03-HITL-PHASE-3-EXACT-EXECUTION-PREVIEW-1.0"
            ),
            "status": "awaiting-explicit-phase-4-confirmation",
            "generated_on": "2026-08-09",
            "phase_2_authorization": {
                "preview_sha256": phase_2_sha256,
                "confirmation_sha256": confirmation_sha256,
                "authorized_scope": "Phase 3 exact read-only verification and preview only",
            },
            "exact_input_verification": {
                **input_facts,
                "artifact_id": artifact.artifact_id,
                "genesis_draft_id": artifact.genesis.candidate_id,
                "knowledge_draft_id": artifact.knowledge.candidate_id,
                "manifest_id": artifact.provenance.manifest_id,
                "manifest_digest": artifact.provenance.manifest_digest,
                "report_digest": artifact.provenance.report_digest,
                "subset_digest": artifact.provenance.subset_digest,
                "source_ids": list(artifact.provenance.source_ids),
                "source_hashes": list(artifact.provenance.source_hashes),
                "rights_basis": artifact.provenance.rights_basis,
                "declared_use": artifact.provenance.declared_use,
                "published": artifact.published,
                "unsealed": artifact.unsealed,
                "authority_counts": dict(artifact.authority_counts),
                "read_only_database_unchanged": True,
            },
            "source_content_semantics": {
                "explicit_subject_name": mapping.display_name,
                "candidate_status_retained_in_knowledge": True,
                "contains_project_draft_unknowns_and_suggestions": True,
                "promoted_to_profile_or_genesis": ["explicit subject name only"],
                "not_promoted": [
                    "candidate or confirmation status text",
                    "Lantern Zine project facts",
                    "unknown information",
                    "suggested collaboration structure",
                    "rights or publication assumptions",
                ],
            },
            "mapping": {
                **mapping.to_dict(),
                "mapping_digest": mapping.mapping_digest,
                "knowledge_body_policy": (
                    "the exact accepted body remains one provenance-bound Knowledge member"
                ),
            },
            "exact_activation_plan": {
                "activation_id": plan.activation_id,
                "plan_digest": plan.plan_digest,
                "activation_time_us": plan.activation_time_us,
                "bundle_base": str(plan.bundle_base),
                "target_pre_state": target_pre_state,
                "studio_root_id": plan.studio_root_id,
                "profile_store_id": plan.profile_store_id,
                "profile_id": plan.profile_id,
                "genesis_branch_id": branch_id,
                "host_root_id": plan.host_root_id,
                "host_control_store_id": plan.host_control_store_id,
                "binding_id": plan.binding_id,
                "authority_scope_id": plan.authority_scope_id,
                "timeline_id": plan.timeline_id,
                "timeline_root_id": plan.timeline_root_id,
                "timeline_control_store_id": plan.timeline_control_store_id,
                "timeline_store_id": plan.timeline_store_id,
            },
            "proposed_profile": {
                **profile.to_dict(),
                "profile_digest": profile_digest,
            },
            "proposed_genesis": {
                "draft_id": artifact.genesis.candidate_id,
                "branch_id": branch_id,
                "revision": 1,
                "premise": premise.to_dict(),
                "premise_digest": premise_digest,
                "freeze_basis_digest": genesis_freeze_basis,
                "freeze_decision": decisions["genesis"].to_dict(),
                "snapshot": {
                    **snapshot_payloads["genesis"],
                    "snapshot_digest": _digest(snapshot_payloads["genesis"]),
                },
            },
            "proposed_knowledge": {
                "draft_id": artifact.knowledge.candidate_id,
                "revision": 1,
                "member_count": 1,
                "member_source_id": artifact.provenance.source_ids[0],
                "member_source_sha256": artifact.provenance.source_hashes[0],
                "revision_digest": knowledge_revision_digest,
                "freeze_basis_digest": knowledge_freeze_basis,
                "freeze_decision": decisions["knowledge"].to_dict(),
                "snapshot": {
                    **snapshot_payloads["knowledge"],
                    "snapshot_digest": _digest(snapshot_payloads["knowledge"]),
                },
                "rights_basis": artifact.provenance.rights_basis,
                "declared_use": artifact.provenance.declared_use,
            },
            "proposed_policy_decision": policy.to_dict(),
            "proposed_snapshot_compatibility_proof": proof,
            "proposed_qualified_runtime_input": qri,
            "proposed_binding_and_empty_timeline": {
                "binding_id": plan.binding_id,
                "binding_state": "active",
                "provider_authority": _DORMANT_ARTIFACT_PROVIDER_AUTHORITY,
                "timeline_id": plan.timeline_id,
                "timeline_head": 0,
                "final_admission_gate_state": "closed",
                "live_runtime_instance_lease_count": 0,
                "empty_verified_prefix_digest": _EMPTY_VERIFIED_PREFIX_DIGEST,
                "empty_revision_head_digest": _EMPTY_REVISION_HEAD_DIGEST,
            },
            "production_source_binding": {
                **production_source_binding,
            },
            "phase_4_exact_writes_if_later_confirmed": [
                "one new local-private experimental Studio/ProfileStore bundle",
                "one accepted-artifact snapshot sidecar with two scoped FreezeDecisions and FreezeAttempts",
                "one sealed GenesisSnapshot and one sealed KnowledgeSnapshot",
                "one compatibility proof and one published dormant QualifiedRuntimeInput",
                "one RuntimeHost root, one active binding and one closed head-0 Timeline",
                "one logical visibility receipt after the complete bundle passes read-only verification",
            ],
            "phase_4_failure_and_recovery": {
                "before_visibility_receipt": (
                    "query remains not-visible; retry must reuse the same identities and converge"
                ),
                "after_visibility_receipt": (
                    "the immutable dormant authority remains; it is not deleted or rewritten"
                ),
                "any_input_mapping_source_or_preview_change": (
                    "fail closed before the first new authority write and require a successor preview"
                ),
            },
            "target_post_state": {
                "profile": 1,
                "freeze_decision": 2,
                "freeze_attempt": 2,
                "sealed_genesis": 1,
                "sealed_knowledge": 1,
                "qualified_runtime_input": 1,
                "active_binding": 1,
                "empty_timeline": 1,
                "timeline_head": 0,
                "live_lease": 0,
                "operation": 0,
                "experience": 0,
                "timeline_outcome": 0,
                "effect": 0,
                "provider_network_credential": 0,
                "physical_clear": 0,
            },
            "confirmation_effect": (
                "Confirming this exact Phase 3 preview authorizes one local Phase 4 "
                "dormant activation at the exact new root, followed by immediate Host "
                "close and post-state HITL. It authorizes no command, provider, network, "
                "credential, retrieval, Memory, effect or clear."
            ),
            "confirmation_required": True,
        }

    @classmethod
    def _activate_exact_accepted_artifact_from_confirmation(
        cls,
        *,
        phase_2_preview_record: Path,
        phase_2_confirmation_record: Path,
        phase_3_preview_record: Path,
        phase_3_confirmation_record: Path,
        _fault_hook: Callable[[AcceptedArtifactActivationFaultPoint], None] | None = None,
        _host_fault_hook: Callable[[object], None] | None = None,
        _authority: object | None = None,
    ) -> DormantArtifactActivationReceipt:
        """Consume one exact confirmed execution preview; no caller supplies roots or IDs."""

        if _authority is not _CONFIRMED_ARTIFACT_ACTIVATION_TOKEN:
            raise StudioRejected(
                "artifact-activation-authority-required",
                "exact Phase 4 activation requires the private confirmed capability",
            )

        def read_unpinned(path: Path, label: str) -> tuple[dict[str, Any], str]:
            record = Path(path)
            if not record.is_absolute():
                raise StudioRejected(
                    "artifact-activation-evidence-invalid",
                    f"{label} must use an explicit absolute path",
                )
            try:
                anchor = Path(record.anchor).resolve(strict=True)
                if (
                    not record.is_file()
                    or record.is_symlink()
                    or record.stat().st_nlink != 1
                    or _has_linklike_component(record, anchor)
                ):
                    raise OSError("record is absent or linked")
                raw = record.read_bytes()
                payload = json.loads(raw.decode("utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise StudioRejected(
                    "artifact-activation-evidence-invalid",
                    f"{label} is absent, linked, or invalid",
                ) from error
            if not isinstance(payload, dict):
                raise StudioRejected(
                    "artifact-activation-evidence-invalid",
                    f"{label} must be one JSON object",
                )
            return payload, hashlib.sha256(raw).hexdigest()

        preview, preview_sha256 = read_unpinned(
            phase_3_preview_record,
            "Phase 3 exact execution preview",
        )
        confirmation, _confirmation_sha256 = read_unpinned(
            phase_3_confirmation_record,
            "Phase 3 activation confirmation",
        )
        reference = confirmation.get("preview")
        if (
            preview.get("evidence_contract")
            != "POST-M0-03-HITL-PHASE-3-EXACT-EXECUTION-PREVIEW-1.0"
            or preview.get("status") != "awaiting-explicit-phase-4-confirmation"
            or confirmation.get("status")
            != "user-confirmed-one-local-dormant-activation"
            or not isinstance(reference, Mapping)
            or reference.get("sha256") != preview_sha256
        ):
            raise StudioRejected(
                "artifact-activation-evidence-invalid",
                "Phase 3 preview has no exact Phase 4 user confirmation",
            )
        expected_preview = cls._prepare_exact_accepted_artifact_activation_preview(
            phase_2_preview_record=phase_2_preview_record,
            phase_2_confirmation_record=phase_2_confirmation_record,
            _allow_matching_recovery_state=True,
            _authority=_CONFIRMED_ARTIFACT_ACTIVATION_TOKEN,
        )
        if preview != expected_preview:
            raise StudioRejected(
                "artifact-activation-evidence-invalid",
                "Phase 3 preview differs from the exact current execution package",
            )
        phase_2, _phase_2_sha256 = cls._read_artifact_activation_evidence(
            phase_2_preview_record,
            expected_sha256=_POST_M0_03_PHASE_2_PREVIEW_SHA256,
            label="Phase 2 activation-basis preview",
        )
        artifact, input_facts = cls._load_exact_accepted_artifact_for_preview(
            phase_2_preview=phase_2
        )
        mapping = cls._map_accepted_artifact_to_dormant_basis(
            artifact.genesis.authored_origin_document
        )
        plan = cls._experimental_artifact_plan_from_phase_two(
            phase_2_preview=phase_2,
            artifact=artifact,
            input_facts=input_facts,
            mapping=mapping,
        )
        receipt = cls._activate_accepted_artifact_test(
            plan.bundle_base,
            artifact,
            _fault_hook=_fault_hook,
            _host_fault_hook=_host_fault_hook,
            _plan=plan,
            _authority=_CONFIRMED_ARTIFACT_ACTIVATION_TOKEN,
        )
        proposed = preview["exact_activation_plan"]
        proposed_genesis = preview["proposed_genesis"]["snapshot"]
        proposed_knowledge = preview["proposed_knowledge"]["snapshot"]
        proposed_proof = preview["proposed_snapshot_compatibility_proof"]
        if (
            receipt.activation_id != proposed["activation_id"]
            or receipt.plan_digest != proposed["plan_digest"]
            or receipt.genesis_snapshot_id != proposed_genesis["snapshot_id"]
            or receipt.knowledge_snapshot_id != proposed_knowledge["snapshot_id"]
            or receipt.compatibility_proof_id != proposed_proof["proof_id"]
            or receipt.timeline_head != 0
            or receipt.live_runtime_instance_lease_count != 0
        ):
            raise StudioFailedClosed(
                "artifact-activation-assembly-invalid",
                "visible activation differs from the user-confirmed exact preview",
            )
        return receipt

    @staticmethod
    def _activation_receipt_from_payload(
        payload: Mapping[str, Any],
    ) -> DormantArtifactActivationReceipt:
        try:
            return DormantArtifactActivationReceipt(
                activation_id=_canonical_uuid(str(payload["activation_id"]), "activation_id"),
                artifact_id=_canonical_uuid(str(payload["artifact_id"]), "artifact_id"),
                plan_digest=str(payload["plan_digest"]),
                studio_location=StudioRootRef.from_dict(payload["studio_location"]),
                host_root_path=str(payload["host_root_path"]),
                host_root_id=_canonical_uuid(str(payload["host_root_id"]), "host_root_id"),
                host_control_store_id=_canonical_uuid(
                    str(payload["host_control_store_id"]), "host_control_store_id"
                ),
                profile_id=_canonical_uuid(str(payload["profile_id"]), "profile_id"),
                genesis_draft_id=_canonical_uuid(
                    str(payload["genesis_draft_id"]), "genesis_draft_id"
                ),
                knowledge_draft_id=_canonical_uuid(
                    str(payload["knowledge_draft_id"]), "knowledge_draft_id"
                ),
                genesis_freeze_decision_id=_canonical_uuid(
                    str(payload["genesis_freeze_decision_id"]),
                    "genesis_freeze_decision_id",
                ),
                knowledge_freeze_decision_id=_canonical_uuid(
                    str(payload["knowledge_freeze_decision_id"]),
                    "knowledge_freeze_decision_id",
                ),
                genesis_freeze_attempt_id=_canonical_uuid(
                    str(payload["genesis_freeze_attempt_id"]),
                    "genesis_freeze_attempt_id",
                ),
                knowledge_freeze_attempt_id=_canonical_uuid(
                    str(payload["knowledge_freeze_attempt_id"]),
                    "knowledge_freeze_attempt_id",
                ),
                genesis_snapshot_id=_canonical_uuid(
                    str(payload["genesis_snapshot_id"]), "genesis_snapshot_id"
                ),
                knowledge_snapshot_id=_canonical_uuid(
                    str(payload["knowledge_snapshot_id"]), "knowledge_snapshot_id"
                ),
                compatibility_proof_id=_canonical_uuid(
                    str(payload["compatibility_proof_id"]), "compatibility_proof_id"
                ),
                qualification_id=_canonical_uuid(
                    str(payload["qualification_id"]), "qualification_id"
                ),
                qri_publication_key=str(payload["qri_publication_key"]),
                binding_id=_canonical_uuid(str(payload["binding_id"]), "binding_id"),
                authority_scope_id=_canonical_uuid(
                    str(payload["authority_scope_id"]), "authority_scope_id"
                ),
                timeline_id=_canonical_uuid(str(payload["timeline_id"]), "timeline_id"),
                timeline_root_id=_canonical_uuid(
                    str(payload["timeline_root_id"]), "timeline_root_id"
                ),
                timeline_control_store_id=_canonical_uuid(
                    str(payload["timeline_control_store_id"]),
                    "timeline_control_store_id",
                ),
                timeline_store_id=_canonical_uuid(
                    str(payload["timeline_store_id"]), "timeline_store_id"
                ),
                timeline_head=int(payload["timeline_head"]),
                timeline_gate_epoch=int(payload["timeline_gate_epoch"]),
                live_runtime_instance_lease_count=int(
                    payload["live_runtime_instance_lease_count"]
                ),
                authority_counts={
                    str(key): int(value)
                    for key, value in dict(payload["authority_counts"]).items()
                },
                visible_at_us=int(payload["visible_at_us"]),
                integrity_digest=str(payload["integrity_digest"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise StudioFailedClosed(
                "artifact-activation-receipt-corrupt",
                "dormant artifact activation receipt is unreadable",
            ) from error

    @classmethod
    def _query_accepted_artifact_activation_test(
        cls,
        test_parent: Path,
        artifact_id: str,
        *,
        _plan: _AcceptedArtifactActivationPlan | None = None,
        _authority: object | None = None,
    ) -> DormantArtifactActivationReceipt:
        """Read only the single logical visibility receipt and its bound stores."""

        if _plan is None:
            plan: _AcceptedArtifactActivationPlan = (
                _accepted_artifact_test_activation_plan(test_parent, artifact_id)
            )
        else:
            if (
                _authority is not _CONFIRMED_ARTIFACT_ACTIVATION_TOKEN
                or type(_plan) is not _AcceptedArtifactExperimentalActivationPlan
                or _plan.artifact_id != _canonical_uuid(artifact_id, "artifact_id")
            ):
                raise StudioRejected(
                    "artifact-activation-plan-mismatch",
                    "experimental activation query requires the frozen exact plan",
                )
            plan = _plan
        location = StudioRootRef(
            root_path=str(
                plan.bundle_base
                / "mature-runtime-m0"
                / "roots"
                / plan.studio_root_id
            ),
            root_id=plan.studio_root_id,
            profile_store_id=plan.profile_store_id,
            root_kind=plan.root_kind,
        )
        sidecar_path = (
            location.root
            / "accepted-artifact-snapshots"
            / "snapshot-authority.sqlite3"
        )
        if not location.root.exists() or not sidecar_path.exists():
            raise StudioRejected(
                "artifact-activation-not-visible",
                "dormant artifact activation has no committed visibility receipt",
            )
        _validate_existing_root(location.root, location.root_id, location.root_kind)
        _read_root_identity(location)

        def readonly(path: Path) -> sqlite3.Connection:
            if (
                not path.is_file()
                or path.is_symlink()
                or path.stat().st_nlink != 1
            ):
                raise StudioFailedClosed(
                    "artifact-activation-store-invalid",
                    "activation store is missing or linked",
                )
            connection = sqlite3.connect(
                _sqlite_uri(path, "ro"),
                uri=True,
                autocommit=True,
                timeout=2.0,
                check_same_thread=True,
            )
            connection.execute("PRAGMA synchronous = EXTRA")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA secure_delete = ON")
            connection.execute("PRAGMA query_only = ON")
            return connection

        profile = readonly(location.profile_database)
        sidecar = readonly(sidecar_path)
        try:
            _verify_store(location, profile)
            _require_profile_active(profile)
            row = sidecar.execute(
                """
                SELECT plan_digest, receipt_json, integrity_digest
                FROM activation_receipt WHERE activation_id = ? AND artifact_id = ?
                """,
                (plan.activation_id, plan.artifact_id),
            ).fetchone()
            if row is None:
                raise StudioRejected(
                    "artifact-activation-not-visible",
                    "dormant artifact activation has no committed visibility receipt",
                )
            try:
                payload = json.loads(str(row[1]))
            except json.JSONDecodeError as error:
                raise StudioFailedClosed(
                    "artifact-activation-receipt-corrupt",
                    "activation receipt JSON is unreadable",
                ) from error
            unsigned = dict(payload)
            integrity_digest = str(unsigned.pop("integrity_digest", ""))
            if (
                str(row[0]) != plan.plan_digest
                or str(row[2]) != integrity_digest
                or _digest(unsigned) != integrity_digest
            ):
                raise StudioFailedClosed(
                    "artifact-activation-receipt-corrupt",
                    "activation receipt digest or plan binding changed",
                )
            receipt = cls._activation_receipt_from_payload(payload)
            expected_plan_fields = {
                "activation_id": plan.activation_id,
                "artifact_id": plan.artifact_id,
                "plan_digest": plan.plan_digest,
                "studio_location": location,
                "host_root_id": plan.host_root_id,
                "host_control_store_id": plan.host_control_store_id,
                "profile_id": plan.profile_id,
                "genesis_freeze_decision_id": plan.genesis_freeze_decision_id,
                "knowledge_freeze_decision_id": plan.knowledge_freeze_decision_id,
                "qualification_id": plan.qualification_id,
                "qri_publication_key": plan.qri_publication_key,
                "binding_id": plan.binding_id,
                "authority_scope_id": plan.authority_scope_id,
                "timeline_id": plan.timeline_id,
                "timeline_root_id": plan.timeline_root_id,
                "timeline_control_store_id": plan.timeline_control_store_id,
                "timeline_store_id": plan.timeline_store_id,
            }
            if any(
                getattr(receipt, field) != expected
                for field, expected in expected_plan_fields.items()
            ):
                raise StudioFailedClosed(
                    "artifact-activation-receipt-corrupt",
                    "activation receipt differs from its deterministic plan",
                )
            readonly_studio = cls(
                location,
                profile,
                PolicyKernel(clock=lambda: plan.policy_clock_us),
                None,
                readonly=True,
            )
            drafts = readonly_studio.query_accepted_artifact_drafts(plan.artifact_id)
            snapshots = readonly_studio.query_accepted_artifact_snapshots(
                plan.artifact_id
            )
            proof = readonly_studio.query_accepted_artifact_compatibility(
                plan.artifact_id
            )
            qri = readonly_studio.query_qri(
                publication_key=plan.qri_publication_key
            )
            if (
                drafts.profile_id != receipt.profile_id
                or drafts.genesis.draft_id != receipt.genesis_draft_id
                or drafts.knowledge.draft_id != receipt.knowledge_draft_id
                or snapshots.genesis.snapshot_id != receipt.genesis_snapshot_id
                or snapshots.knowledge.snapshot_id != receipt.knowledge_snapshot_id
                or snapshots.genesis.freeze_attempt_id
                != receipt.genesis_freeze_attempt_id
                or snapshots.knowledge.freeze_attempt_id
                != receipt.knowledge_freeze_attempt_id
                or proof.proof_id != receipt.compatibility_proof_id
                or qri.qualification_id != receipt.qualification_id
            ):
                raise StudioFailedClosed(
                    "artifact-activation-incomplete",
                    "receipt no longer binds the exact authoring aggregates",
                )
            profile_manifest = profile.execute(
                "SELECT root_id, store_id FROM store_manifest WHERE singleton = 1"
            ).fetchone()
            if profile_manifest != (plan.studio_root_id, plan.profile_store_id):
                raise StudioFailedClosed(
                    "artifact-activation-store-invalid",
                    "ProfileStore identity differs from the activation receipt",
                )
            qri_row = profile.execute(
                """
                SELECT qri_json FROM qri_publication
                WHERE qualification_id = ? AND publication_key = ?
                """,
                (plan.qualification_id, plan.qri_publication_key),
            ).fetchone()
            if qri_row is None:
                raise StudioFailedClosed(
                    "artifact-activation-incomplete",
                    "activation receipt has no exact QRI",
                )
            qri_payload = json.loads(str(qri_row[0]))
            if (
                qri_payload.get("profile_id") != plan.profile_id
                or qri_payload.get("genesis_snapshot_id")
                != receipt.genesis_snapshot_id
                or qri_payload.get("knowledge_snapshot_id")
                != receipt.knowledge_snapshot_id
                or qri_payload.get("provider_authority")
                != _DORMANT_ARTIFACT_PROVIDER_AUTHORITY
            ):
                raise StudioFailedClosed(
                    "artifact-activation-incomplete",
                    "activation QRI differs from the visibility receipt",
                )
            observed_authoring_counts = {
                "profile": int(
                    profile.execute("SELECT COUNT(*) FROM participant_profile").fetchone()[0]
                ),
                "genesis_draft": int(
                    profile.execute("SELECT COUNT(*) FROM genesis_draft").fetchone()[0]
                ),
                "knowledge_draft": int(
                    sidecar.execute("SELECT COUNT(*) FROM knowledge_draft").fetchone()[0]
                ),
                "freeze_decision": int(
                    sidecar.execute("SELECT COUNT(*) FROM freeze_decision").fetchone()[0]
                ),
                "freeze_attempt": int(
                    sidecar.execute("SELECT COUNT(*) FROM freeze_attempt").fetchone()[0]
                ),
                "sealed_genesis": int(
                    sidecar.execute(
                        "SELECT COUNT(*) FROM sealed_snapshot WHERE scope = 'genesis'"
                    ).fetchone()[0]
                ),
                "sealed_knowledge": int(
                    sidecar.execute(
                        "SELECT COUNT(*) FROM sealed_snapshot WHERE scope = 'knowledge'"
                    ).fetchone()[0]
                ),
                "snapshot_compatibility_proof": int(
                    sidecar.execute(
                        "SELECT COUNT(*) FROM snapshot_compatibility_proof"
                    ).fetchone()[0]
                ),
                "qualified_runtime_input": int(
                    profile.execute("SELECT COUNT(*) FROM qri_publication").fetchone()[0]
                ),
            }
        finally:
            profile.close()
            sidecar.close()

        from dynamic_subject_agent.host import (
            RuntimeHostRootRef,
            _connect_readonly as _host_connect_readonly,
            _read_root_identity as _read_host_root_identity,
            _validate_existing_root as _validate_host_root,
            _verify_control as _verify_host_control,
        )

        host_location = RuntimeHostRootRef(
            root_path=receipt.host_root_path,
            root_id=receipt.host_root_id,
            control_store_id=receipt.host_control_store_id,
            root_kind=plan.root_kind,
        )
        _validate_host_root(
            host_location.root,
            host_location.root_id,
            root_kind=plan.root_kind,
            studio_location=location,
        )
        _read_host_root_identity(host_location, location)
        host = _host_connect_readonly(host_location.control_database)
        timeline_control: sqlite3.Connection | None = None
        timeline: sqlite3.Connection | None = None
        try:
            from dynamic_subject_agent.timeline import (
                CONTROL_SCHEMA_FAMILY as _TIMELINE_CONTROL_SCHEMA_FAMILY,
                TIMELINE_SCHEMA_FAMILY as _TIMELINE_SCHEMA_FAMILY,
                CanonicalRootRef,
                _CONTROL_TABLES as _TIMELINE_CONTROL_TABLES,
                _EMPTY_REVISION_HEAD_DIGEST,
                _EMPTY_VERIFIED_PREFIX_DIGEST,
                _TIMELINE_TABLES,
                _read_root_identity as _read_timeline_root_identity,
                _validate_existing_root as _validate_timeline_root,
                _verify_connection_profile as _verify_timeline_connection,
                _verify_manifest as _verify_timeline_manifest,
                _verify_store_integrity as _verify_timeline_store,
            )
            timeline_location = CanonicalRootRef(
                root_path=str(
                    host_location.root
                    / "mature-runtime-m0"
                    / "roots"
                    / receipt.timeline_root_id
                ),
                root_id=receipt.timeline_root_id,
                control_store_id=receipt.timeline_control_store_id,
                timeline_store_id=receipt.timeline_store_id,
                timeline_id=receipt.timeline_id,
                root_kind=plan.root_kind,
            )
            _validate_timeline_root(
                timeline_location.root,
                timeline_location.root_id,
                root_kind=plan.root_kind,
            )
            _read_timeline_root_identity(
                timeline_location.root,
                timeline_location.root_id,
                plan.root_kind,
            )
            timeline_control = readonly(timeline_location.control_database)
            timeline = readonly(timeline_location.timeline_database)
            _verify_host_control(host_location, location, host)
            _verify_timeline_connection(timeline_control)
            _verify_timeline_manifest(
                timeline_control,
                root_id=timeline_location.root_id,
                store_id=timeline_location.control_store_id,
                store_kind="control",
                schema_family=_TIMELINE_CONTROL_SCHEMA_FAMILY,
            )
            _verify_timeline_store(
                timeline_control,
                expected_tables=_TIMELINE_CONTROL_TABLES,
            )
            registration = timeline_control.execute(
                """
                SELECT timeline_store_id, relative_database_path, registration_state
                FROM timeline_registration WHERE timeline_id = ?
                """,
                (receipt.timeline_id,),
            ).fetchone()
            if registration != (
                receipt.timeline_store_id,
                f"timelines/{receipt.timeline_id}/timeline.sqlite3",
                "ready",
            ):
                raise StudioFailedClosed(
                    "artifact-activation-incomplete",
                    "Timeline registration differs from the visibility receipt",
                )
            _verify_timeline_connection(timeline)
            _verify_timeline_manifest(
                timeline,
                root_id=timeline_location.root_id,
                store_id=timeline_location.timeline_store_id,
                store_kind="timeline",
                schema_family=_TIMELINE_SCHEMA_FAMILY,
            )
            _verify_timeline_store(timeline, expected_tables=_TIMELINE_TABLES)
            gate_row = timeline.execute(
                """
                SELECT authority_kind, authority_scope_id, profile_id, timeline_id,
                       allowed_intents_json, allowed_provenance_json, binding_id,
                       binding_revision, binding_epoch, qualification_id,
                       qualification_revision, provider_authority, gate_epoch,
                       gate_state, data_control_scope_id
                FROM admission_gate WHERE singleton = 1
                """
            ).fetchone()
            if gate_row != (
                "published-qri-binding",
                receipt.authority_scope_id,
                receipt.profile_id,
                receipt.timeline_id,
                _canonical_json(["ask-collaborator-status"]),
                _canonical_json(["project-original"]),
                receipt.binding_id,
                1,
                1,
                receipt.qualification_id,
                qri.qualification_revision,
                _DORMANT_ARTIFACT_PROVIDER_AUTHORITY,
                receipt.timeline_gate_epoch,
                "closed",
                None,
            ):
                raise StudioFailedClosed(
                    "artifact-activation-incomplete",
                    "Timeline Admission gate differs from the dormant binding",
                )
            binding = host.execute(
                """
                SELECT binding_id, state, profile_id, timeline_id,
                       authority_scope_id, qualification_id,
                       qualification_revision, qri_publication_key,
                       qri_integrity_digest, genesis_snapshot_id,
                       knowledge_snapshot_id, policy_decision_ids_json,
                       capability_manifest_version, provider_authority,
                       runtime_kind, runtime_contract_version,
                       studio_root_id, studio_store_id, host_root_id,
                       host_control_store_id, timeline_root_json,
                       timeline_root_id, timeline_control_store_id,
                       timeline_store_id, first_subject_event_sealed
                FROM runtime_authority_binding
                WHERE binding_id = ?
                """,
                (receipt.binding_id,),
            ).fetchone()
            timeline_root_path = (
                host_location.root
                / "mature-runtime-m0"
                / "roots"
                / receipt.timeline_root_id
            )
            expected_binding = (
                receipt.binding_id,
                "active",
                receipt.profile_id,
                receipt.timeline_id,
                receipt.authority_scope_id,
                receipt.qualification_id,
                qri.qualification_revision,
                receipt.qri_publication_key,
                qri.integrity_digest,
                receipt.genesis_snapshot_id,
                receipt.knowledge_snapshot_id,
                _canonical_json(list(qri.policy_decision_ids)),
                qri.capabilities.manifest_version,
                _DORMANT_ARTIFACT_PROVIDER_AUTHORITY,
                "mature-canonical",
                "m0-a-cycle-1.0",
                receipt.studio_location.root_id,
                receipt.studio_location.profile_store_id,
                receipt.host_root_id,
                receipt.host_control_store_id,
                _canonical_json(
                    {
                        "root_path": str(timeline_root_path),
                        "root_id": receipt.timeline_root_id,
                        "control_store_id": receipt.timeline_control_store_id,
                        "timeline_store_id": receipt.timeline_store_id,
                        "timeline_id": receipt.timeline_id,
                        "root_kind": plan.root_kind,
                    }
                ),
                receipt.timeline_root_id,
                receipt.timeline_control_store_id,
                receipt.timeline_store_id,
                0,
            )
            active_leases = int(
                host.execute(
                    "SELECT COUNT(*) FROM runtime_instance_lease WHERE lease_state = 'active'"
                ).fetchone()[0]
            )
            head = int(
                timeline.execute(
                    "SELECT head_sequence FROM timeline_head WHERE singleton = 1"
                ).fetchone()[0]
            )
            integrity_row = timeline.execute(
                """
                SELECT verified_prefix_digest, revision_head_digest
                FROM timeline_integrity WHERE singleton = 1
                """
            ).fetchone()
            counts = {
                **observed_authoring_counts,
                "runtime_host_root": 1,
                "active_runtime_binding": int(
                    host.execute(
                        "SELECT COUNT(*) FROM runtime_authority_binding WHERE state = 'active'"
                    ).fetchone()[0]
                ),
                "runtime_timeline": 1,
                "operation": int(
                    timeline.execute("SELECT COUNT(*) FROM subject_operation").fetchone()[0]
                ),
                "experience": int(
                    timeline.execute("SELECT COUNT(*) FROM experience_record").fetchone()[0]
                ),
                "timeline_outcome": int(
                    timeline.execute("SELECT COUNT(*) FROM timeline_outcome").fetchone()[0]
                ),
                "effect": 0,
                "provider_call": 0,
                "network_egress": 0,
                "credential_access": 0,
                "physical_clear": 0,
            }
            if (
                binding != expected_binding
                or observed_authoring_counts
                != {
                    "profile": 1,
                    "genesis_draft": 1,
                    "knowledge_draft": 1,
                    "freeze_decision": 2,
                    "freeze_attempt": 2,
                    "sealed_genesis": 1,
                    "sealed_knowledge": 1,
                    "snapshot_compatibility_proof": 1,
                    "qualified_runtime_input": 1,
                }
                or head != 0
                or integrity_row
                != (
                    bytes.fromhex(_EMPTY_VERIFIED_PREFIX_DIGEST),
                    bytes.fromhex(_EMPTY_REVISION_HEAD_DIGEST),
                )
                or active_leases != 0
                or receipt.timeline_head != 0
                or receipt.live_runtime_instance_lease_count != 0
                or dict(receipt.authority_counts) != counts
                or any(
                    counts[key] != 0
                    for key in (
                        "operation",
                        "experience",
                        "timeline_outcome",
                        "effect",
                        "provider_call",
                        "network_egress",
                        "credential_access",
                        "physical_clear",
                    )
                )
            ):
                raise StudioFailedClosed(
                    "artifact-activation-incomplete",
                    "visible dormant authority is not the exact closed empty bundle",
                )
            return receipt
        except StudioProblem:
            raise
        except Exception as error:
            raise StudioFailedClosed(
                "artifact-activation-store-invalid",
                "visible dormant authority failed read-only verification",
            ) from error
        finally:
            if timeline is not None:
                timeline.close()
            if timeline_control is not None:
                timeline_control.close()
            host.close()

    @classmethod
    def _activate_accepted_artifact_test(
        cls,
        test_parent: Path,
        artifact: UnpublishedSubjectStudioArtifact,
        *,
        _fault_hook: Callable[[AcceptedArtifactActivationFaultPoint], None] | None = None,
        _host_fault_hook: Callable[[object], None] | None = None,
        _plan: _AcceptedArtifactActivationPlan | None = None,
        _authority: object | None = None,
    ) -> DormantArtifactActivationReceipt:
        """Build one complete dormant fixture, then atomically expose its receipt."""

        if not isinstance(artifact, UnpublishedSubjectStudioArtifact):
            raise TypeError("artifact activation requires an unpublished artifact fixture")
        if _plan is None:
            plan: _AcceptedArtifactActivationPlan = (
                _accepted_artifact_test_activation_plan(
                    test_parent,
                    artifact.artifact_id,
                )
            )
            exact_authority: object | None = None
        else:
            if (
                _authority is not _CONFIRMED_ARTIFACT_ACTIVATION_TOKEN
                or type(_plan) is not _AcceptedArtifactExperimentalActivationPlan
                or _plan.artifact_id != artifact.artifact_id
                or _plan.root_kind != EXPERIMENTAL_ROOT_KIND
            ):
                raise StudioRejected(
                    "artifact-activation-plan-mismatch",
                    "experimental activation requires the frozen exact plan",
                )
            plan = _plan
            exact_authority = _CONFIRMED_ARTIFACT_ACTIVATION_TOKEN
            cls._classify_artifact_activation_target(plan=plan)

        def hit(point: AcceptedArtifactActivationFaultPoint) -> None:
            if _fault_hook is not None:
                _fault_hook(point)

        gate_parent = (
            _validate_test_base(plan.gate_parent)
            if plan.root_kind == ROOT_KIND
            else _validate_artifact_activation_gate_parent(plan.gate_parent)
        )
        gate_path = gate_parent / f"{plan.activation_id}.sqlite3"
        if gate_path.exists() and (
            not gate_path.is_file()
            or gate_path.is_symlink()
            or gate_path.stat().st_nlink != 1
        ):
            raise StudioRejected(
                "artifact-activation-gate-invalid",
                "activation gate has an unsafe identity",
            )
        gate = sqlite3.connect(
            _sqlite_uri(gate_path, "rwc"),
            uri=True,
            autocommit=True,
            timeout=30.0,
            check_same_thread=True,
        )
        studio: SubjectStudio | None = None
        try:
            gate.execute(
                "CREATE TABLE IF NOT EXISTS activation_gate (singleton INTEGER PRIMARY KEY CHECK (singleton = 1)) STRICT"
            )
            gate.execute("BEGIN EXCLUSIVE")
            hit(AcceptedArtifactActivationFaultPoint.AFTER_LOCK)
            if plan.root_kind == EXPERIMENTAL_ROOT_KIND:
                cls._classify_artifact_activation_target(plan=plan)
            verified_bundle = (
                _validate_test_base(plan.bundle_base)
                if plan.root_kind == ROOT_KIND
                else _validate_reserved_artifact_activation_base(
                    plan.bundle_base,
                    create=True,
                )
            )
            if verified_bundle != plan.bundle_base.resolve(strict=True):
                raise StudioRejected(
                    "artifact-activation-plan-mismatch",
                    "activation bundle path changed identity",
                )
            location = StudioRootRef(
                root_path=str(
                    plan.bundle_base
                    / "mature-runtime-m0"
                    / "roots"
                    / plan.studio_root_id
                ),
                root_id=plan.studio_root_id,
                profile_store_id=plan.profile_store_id,
                root_kind=plan.root_kind,
            )
            kernel = PolicyKernel(clock=lambda: plan.policy_clock_us)
            if location.root.exists():
                studio = cls.open(location, policy_kernel=kernel)
            else:
                studio = cls._create_at_base(
                    plan.bundle_base,
                    root_kind=plan.root_kind,
                    policy_kernel=kernel,
                    root_id=plan.studio_root_id,
                    profile_store_id=plan.profile_store_id,
                )
            hit(AcceptedArtifactActivationFaultPoint.AFTER_STUDIO_OPEN)
            try:
                sidecar = studio._open_artifact_sidecar(create=False)
                try:
                    visible = sidecar.execute(
                        "SELECT 1 FROM activation_receipt WHERE activation_id = ?",
                        (plan.activation_id,),
                    ).fetchone()
                finally:
                    sidecar.close()
            except StudioProblem as error:
                if error.code != "accepted-artifact-not-found":
                    raise
                visible = None
            if visible is not None:
                _payload, candidate_digest, _provenance_digest = (
                    studio._validate_accepted_artifact_test(
                        artifact,
                        _authority=exact_authority,
                    )
                )
                sidecar = studio._open_artifact_sidecar(create=False)
                try:
                    persisted = sidecar.execute(
                        "SELECT artifact_digest FROM accepted_artifact WHERE artifact_id = ?",
                        (plan.artifact_id,),
                    ).fetchone()
                finally:
                    sidecar.close()
                if persisted is None or str(persisted[0]) != candidate_digest:
                    raise StudioConflict(
                        "accepted-artifact-identity-conflict",
                        "visible activation already binds different artifact content",
                    )
                studio.close()
                studio = None
                gate.execute("COMMIT")
                return cls._query_accepted_artifact_activation_test(
                    test_parent,
                    artifact.artifact_id,
                    _plan=(plan if plan.root_kind == EXPERIMENTAL_ROOT_KIND else None),
                    _authority=exact_authority,
                )

            drafts = studio._stage_accepted_artifact_test(
                artifact,
                _authority=exact_authority,
            )
            if drafts.profile_id != plan.profile_id:
                raise StudioFailedClosed(
                    "artifact-activation-plan-mismatch",
                    "staged Profile differs from the deterministic activation plan",
                )
            hit(AcceptedArtifactActivationFaultPoint.AFTER_DRAFT_STAGE)
            policy = studio.decide_accepted_artifact_policy(
                artifact.artifact_id,
                CapabilityManifest.accepted_artifact_dormant(),
                validity_us=10**18,
            )
            genesis_decision = ScopedFreezeDecision(
                decision_id=plan.genesis_freeze_decision_id,
                scope="genesis",
                draft_id=drafts.genesis.draft_id,
                expected_revision=drafts.genesis.revision,
                freeze_basis_digest=drafts.genesis.freeze_basis_digest,
                decided_by=(
                    "post-m0-03-temporary-root-tdd"
                    if plan.root_kind == ROOT_KIND
                    else "post-m0-03-user-confirmed-local-activation"
                ),
                rationale="Freeze only the exact reviewed minimal Genesis mapping.",
            )
            knowledge_decision = ScopedFreezeDecision(
                decision_id=plan.knowledge_freeze_decision_id,
                scope="knowledge",
                draft_id=drafts.knowledge.draft_id,
                expected_revision=drafts.knowledge.revision,
                freeze_basis_digest=drafts.knowledge.freeze_basis_digest,
                decided_by=(
                    "post-m0-03-temporary-root-tdd"
                    if plan.root_kind == ROOT_KIND
                    else "post-m0-03-user-confirmed-local-activation"
                ),
                rationale="Freeze only the exact provenance-bound Knowledge member.",
            )

            def attempt_hit(scope: str) -> None:
                hit(
                    AcceptedArtifactActivationFaultPoint.AFTER_GENESIS_FREEZE_ATTEMPT
                    if scope == "genesis"
                    else AcceptedArtifactActivationFaultPoint.AFTER_KNOWLEDGE_FREEZE_ATTEMPT
                )

            snapshots = studio._seal_accepted_artifact_test(
                artifact.artifact_id,
                genesis_decision=genesis_decision,
                knowledge_decision=knowledge_decision,
                policy_decision_id=policy.decision_id,
                _attempt_hook=attempt_hit,
                _created_at_us=plan.activation_time_us,
            )
            hit(AcceptedArtifactActivationFaultPoint.AFTER_SEAL)
            proof = studio._prove_accepted_artifact_compatibility_test(
                artifact.artifact_id,
                policy_decision_id=policy.decision_id,
            )
            hit(AcceptedArtifactActivationFaultPoint.AFTER_COMPATIBILITY_PROOF)
            qri = studio._publish_accepted_artifact_qri_test(
                artifact.artifact_id,
                policy_decision_id=policy.decision_id,
                compatibility_proof_id=proof.proof_id,
                publication_key=plan.qri_publication_key,
                _published_at_us=plan.activation_time_us,
            )
            if qri.qualification_id != plan.qualification_id:
                raise StudioFailedClosed(
                    "artifact-activation-plan-mismatch",
                    "published QRI differs from the deterministic activation plan",
                )
            hit(AcceptedArtifactActivationFaultPoint.AFTER_QRI_PUBLICATION)

            from dynamic_subject_agent.bootstrap import compose_application
            from dynamic_subject_agent.host import (
                RuntimeHostRootRef,
                _DormantArtifactActivationPlan,
                _DormantArtifactExperimentalActivationPlan,
            )
            from dynamic_subject_agent.runtime import _DormantArtifactCognition
            from dynamic_subject_agent.timeline import (
                _EMPTY_REVISION_HEAD_DIGEST,
                _EMPTY_VERIFIED_PREFIX_DIGEST,
                _ReservedTimelineIdentity,
            )

            host_location = RuntimeHostRootRef(
                root_path=str(
                    plan.bundle_base
                    / "mature-runtime-m0"
                    / "host-roots"
                    / plan.host_root_id
                ),
                root_id=plan.host_root_id,
                control_store_id=plan.host_control_store_id,
                root_kind=plan.root_kind,
            )
            host_plan_type = (
                _DormantArtifactActivationPlan
                if plan.root_kind == ROOT_KIND
                else _DormantArtifactExperimentalActivationPlan
            )
            host_plan = host_plan_type(
                provider_authority=_DORMANT_ARTIFACT_PROVIDER_AUTHORITY,
                profile_id=plan.profile_id,
                qualification_id=plan.qualification_id,
                qri_publication_key=plan.qri_publication_key,
                timeline_id=plan.timeline_id,
                host_root_id=plan.host_root_id,
                host_control_store_id=plan.host_control_store_id,
                binding_id=plan.binding_id,
                authority_scope_id=plan.authority_scope_id,
                timeline_identity=_ReservedTimelineIdentity(
                    root_id=plan.timeline_root_id,
                    control_store_id=plan.timeline_control_store_id,
                    timeline_store_id=plan.timeline_store_id,
                ),
            )
            composition = compose_application(
                m0_root=plan.bundle_base,
                studio_location=location,
                qualified_runtime_input=qri,
                timeline_id=plan.timeline_id,
                host_location=host_location if host_location.root.exists() else None,
                _cognition=_DormantArtifactCognition(),
                _activation_plan=host_plan,
                _host_fault_hook=_host_fault_hook,
            )
            try:
                binding = composition._host.query_binding(
                    profile_id=plan.profile_id,
                    timeline_id=plan.timeline_id,
                )
                health = composition._host.health(
                    profile_id=plan.profile_id,
                    timeline_id=plan.timeline_id,
                )
                if (
                    binding.binding_id != plan.binding_id
                    or binding.timeline_root.root_id != plan.timeline_root_id
                    or health.timeline_basis.head_sequence != 0
                    or health.first_subject_event_sealed
                ):
                    raise StudioFailedClosed(
                        "artifact-activation-assembly-invalid",
                        "dormant Runtime assembly differs from the activation plan",
                    )
                hit(AcceptedArtifactActivationFaultPoint.AFTER_COMPOSITION_HEALTH)
            finally:
                composition.close()

            host_reader = sqlite3.connect(
                _sqlite_uri(host_location.control_database, "ro"),
                uri=True,
                autocommit=True,
                timeout=2.0,
            )
            timeline_database = (
                host_location.root
                / "mature-runtime-m0"
                / "roots"
                / plan.timeline_root_id
                / "timelines"
                / plan.timeline_id
                / "timeline.sqlite3"
            )
            timeline_reader = sqlite3.connect(
                _sqlite_uri(timeline_database, "ro"),
                uri=True,
                autocommit=True,
                timeout=2.0,
            )
            try:
                active_binding_count = int(
                    host_reader.execute(
                        "SELECT COUNT(*) FROM runtime_authority_binding WHERE state = 'active'"
                    ).fetchone()[0]
                )
                active_lease_count = int(
                    host_reader.execute(
                        "SELECT COUNT(*) FROM runtime_instance_lease WHERE lease_state = 'active'"
                    ).fetchone()[0]
                )
                final_gate = timeline_reader.execute(
                    """
                    SELECT gate_epoch, gate_state FROM admission_gate WHERE singleton = 1
                    """
                ).fetchone()
                empty_state = timeline_reader.execute(
                    """
                    SELECT
                      (SELECT head_sequence FROM timeline_head WHERE singleton = 1),
                      (SELECT COUNT(*) FROM subject_operation),
                      (SELECT COUNT(*) FROM experience_record),
                      (SELECT COUNT(*) FROM timeline_outcome)
                    """
                ).fetchone()
                empty_integrity = timeline_reader.execute(
                    """
                    SELECT verified_prefix_digest, revision_head_digest
                    FROM timeline_integrity WHERE singleton = 1
                    """
                ).fetchone()
            finally:
                timeline_reader.close()
                host_reader.close()
            if (
                active_binding_count != 1
                or active_lease_count != 0
                or final_gate is None
                or str(final_gate[1]) != "closed"
                or empty_state != (0, 0, 0, 0)
                or empty_integrity
                != (
                    bytes.fromhex(_EMPTY_VERIFIED_PREFIX_DIGEST),
                    bytes.fromhex(_EMPTY_REVISION_HEAD_DIGEST),
                )
            ):
                raise StudioFailedClosed(
                    "artifact-activation-assembly-invalid",
                    "closed dormant assembly failed the pre-visibility check",
                )
            final_gate_epoch = int(final_gate[0])
            counts = {
                "profile": 1,
                "genesis_draft": 1,
                "knowledge_draft": 1,
                "freeze_decision": 2,
                "freeze_attempt": 2,
                "sealed_genesis": 1,
                "sealed_knowledge": 1,
                "snapshot_compatibility_proof": 1,
                "qualified_runtime_input": 1,
                "runtime_host_root": 1,
                "active_runtime_binding": 1,
                "runtime_timeline": 1,
                "operation": 0,
                "experience": 0,
                "timeline_outcome": 0,
                "effect": 0,
                "provider_call": 0,
                "network_egress": 0,
                "credential_access": 0,
                "physical_clear": 0,
            }
            visible_at_us = _utc_microseconds()
            unsigned = {
                "activation_id": plan.activation_id,
                "artifact_id": plan.artifact_id,
                "plan_digest": plan.plan_digest,
                "studio_location": location.to_dict(),
                "host_root_path": str(host_location.root),
                "host_root_id": plan.host_root_id,
                "host_control_store_id": plan.host_control_store_id,
                "profile_id": plan.profile_id,
                "genesis_draft_id": drafts.genesis.draft_id,
                "knowledge_draft_id": drafts.knowledge.draft_id,
                "genesis_freeze_decision_id": genesis_decision.decision_id,
                "knowledge_freeze_decision_id": knowledge_decision.decision_id,
                "genesis_freeze_attempt_id": snapshots.genesis.freeze_attempt_id,
                "knowledge_freeze_attempt_id": snapshots.knowledge.freeze_attempt_id,
                "genesis_snapshot_id": snapshots.genesis.snapshot_id,
                "knowledge_snapshot_id": snapshots.knowledge.snapshot_id,
                "compatibility_proof_id": proof.proof_id,
                "qualification_id": qri.qualification_id,
                "qri_publication_key": qri.publication_key,
                "binding_id": binding.binding_id,
                "authority_scope_id": binding.authority_scope_id,
                "timeline_id": binding.timeline_id,
                "timeline_root_id": binding.timeline_root.root_id,
                "timeline_control_store_id": binding.timeline_root.control_store_id,
                "timeline_store_id": binding.timeline_root.timeline_store_id,
                "timeline_head": 0,
                "timeline_gate_epoch": final_gate_epoch,
                "live_runtime_instance_lease_count": 0,
                "authority_counts": counts,
                "visible_at_us": visible_at_us,
            }
            payload = {**unsigned, "integrity_digest": _digest(unsigned)}
            hit(AcceptedArtifactActivationFaultPoint.BEFORE_VISIBILITY_COMMIT)
            sidecar = studio._open_artifact_sidecar(create=False)
            try:
                _begin(sidecar)
                sidecar.execute(
                    """
                    INSERT INTO activation_receipt (
                        activation_id, artifact_id, plan_digest,
                        receipt_json, integrity_digest, visible_at_us
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        plan.activation_id,
                        plan.artifact_id,
                        plan.plan_digest,
                        _canonical_json(payload),
                        payload["integrity_digest"],
                        visible_at_us,
                    ),
                )
                _commit(sidecar)
            except Exception:
                _rollback_if_needed(sidecar)
                raise
            finally:
                sidecar.close()
            studio.close()
            studio = None
            gate.execute("COMMIT")
        except Exception:
            if gate.in_transaction:
                gate.execute("ROLLBACK")
            raise
        finally:
            if studio is not None:
                studio.close()
            gate.close()
        return cls._query_accepted_artifact_activation_test(
            test_parent,
            artifact.artifact_id,
            _plan=(plan if plan.root_kind == EXPERIMENTAL_ROOT_KIND else None),
            _authority=exact_authority,
        )

    @classmethod
    def _activate_accepted_artifact_experimental_test(
        cls,
        test_parent: Path,
        artifact: UnpublishedSubjectStudioArtifact,
        *,
        _fault_hook: Callable[[AcceptedArtifactActivationFaultPoint], None] | None = None,
        _host_fault_hook: Callable[[object], None] | None = None,
    ) -> DormantArtifactActivationReceipt:
        """Exercise the production experimental-root branch using only temp fixtures."""

        plan = _accepted_artifact_experimental_test_plan(test_parent, artifact)
        return cls._activate_accepted_artifact_test(
            test_parent,
            artifact,
            _fault_hook=_fault_hook,
            _host_fault_hook=_host_fault_hook,
            _plan=plan,
            _authority=_CONFIRMED_ARTIFACT_ACTIVATION_TOKEN,
        )

    def create_draft(
        self,
        *,
        profile: ParticipantProfile,
        premise: GenesisPremise,
    ) -> DraftView:
        return self._create_draft_with_ids(
            profile=profile,
            premise=premise,
            draft_id=str(uuid4()),
            branch_id=str(uuid4()),
        )

    def ensure_source_identity_draft(
        self,
        *,
        profile: ParticipantProfile,
        premise: GenesisPremise,
        source_freeze_basis_digest: str,
    ) -> DraftView:
        """Idempotently stage the one Genesis draft derived from a source basis."""

        basis = _canonical_sha256(
            source_freeze_basis_digest,
            "source_freeze_basis_digest",
        )
        draft_id = str(
            uuid5(NAMESPACE_URL, "dynamic-subject-agent:source-draft:" + basis)
        )
        branch_id = str(
            uuid5(NAMESPACE_URL, "dynamic-subject-agent:source-branch:" + basis)
        )
        try:
            row, stored_profile, stored_premise, _profile_digest = self._draft_bundle(
                draft_id
            )
        except StudioRejected as error:
            if error.code != "draft-not-found":
                raise
            return self._create_draft_with_ids(
                profile=profile,
                premise=premise,
                draft_id=draft_id,
                branch_id=branch_id,
            )
        if (
            str(row[1]) != branch_id
            or stored_profile.to_dict() != profile.to_dict()
            or stored_premise.to_dict() != premise.to_dict()
        ):
            raise StudioConflict(
                "source-freeze-identity-conflict",
                "Freeze Basis already names different staged identity content",
            )
        return DraftView(
            draft_id=str(row[0]),
            branch_id=str(row[1]),
            profile_id=str(row[2]),
            revision=int(row[3]),
            content_fingerprint=str(row[10]),
            sealed_snapshot_id=None if row[4] is None else str(row[4]),
        )

    def _create_reserved_draft(
        self,
        *,
        profile: ParticipantProfile,
        premise: GenesisPremise,
        draft_id: str,
        branch_id: str,
        _authority: object,
    ) -> DraftView:
        if _authority is not _CONFIRMED_EXPERIMENT_PREPARATION_TOKEN:
            raise TypeError("reserved draft creation requires preparation authority")
        return self._create_draft_with_ids(
            profile=profile,
            premise=premise,
            draft_id=draft_id,
            branch_id=branch_id,
        )

    def _create_draft_with_ids(
        self,
        *,
        profile: ParticipantProfile,
        premise: GenesisPremise,
        draft_id: str,
        branch_id: str,
    ) -> DraftView:
        self._require_authority()
        if not isinstance(profile, ParticipantProfile):
            raise TypeError("create_draft requires a ParticipantProfile")
        if not isinstance(premise, GenesisPremise):
            raise TypeError("create_draft requires a GenesisPremise")
        draft_id = _canonical_uuid(draft_id, "draft_id")
        branch_id = _canonical_uuid(branch_id, "branch_id")
        profile_json = _canonical_json(profile.to_dict())
        profile_digest = _digest(profile.to_dict())
        premise_json = _canonical_json(premise.to_dict())
        content_digest = _digest(premise.to_dict())
        created_at_us = _utc_microseconds()
        try:
            _begin(self._writer)
            existing = self._writer.execute(
                "SELECT profile_digest FROM participant_profile WHERE profile_id = ?",
                (profile.profile_id,),
            ).fetchone()
            if existing is None:
                self._writer.execute(
                    """
                    INSERT INTO participant_profile (
                        profile_id, profile_json, profile_digest, created_at_us
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (profile.profile_id, profile_json, profile_digest, created_at_us),
                )
            elif str(existing[0]) != profile_digest:
                raise StudioConflict(
                    "profile-identity-conflict",
                    "ParticipantProfile identity already names different content",
                )
            self._writer.execute(
                """
                INSERT INTO genesis_branch (
                    branch_id,
                    profile_id,
                    predecessor_snapshot_id,
                    lineage_relation,
                    lineage_reason,
                    created_at_us
                ) VALUES (?, ?, NULL, 'first-publication', 'initial original branch', ?)
                """,
                (branch_id, profile.profile_id, created_at_us),
            )
            self._writer.execute(
                """
                INSERT INTO genesis_draft (
                    draft_id,
                    branch_id,
                    profile_id,
                    current_revision,
                    sealed_snapshot_id,
                    created_at_us
                ) VALUES (?, ?, ?, 1, NULL, ?)
                """,
                (draft_id, branch_id, profile.profile_id, created_at_us),
            )
            self._writer.execute(
                """
                INSERT INTO genesis_draft_revision (
                    draft_id,
                    revision,
                    premise_json,
                    content_digest,
                    created_at_us
                ) VALUES (?, 1, ?, ?, ?)
                """,
                (draft_id, premise_json, content_digest, created_at_us),
            )
            _commit(self._writer)
        except Exception:
            _rollback_if_needed(self._writer)
            raise
        return DraftView(
            draft_id=draft_id,
            branch_id=branch_id,
            profile_id=profile.profile_id,
            revision=1,
            content_fingerprint=content_digest,
            sealed_snapshot_id=None,
        )

    def revise_draft(
        self,
        draft_id: str,
        *,
        expected_revision: int,
        premise: GenesisPremise,
    ) -> DraftView:
        self._require_authority()
        canonical_draft_id = _canonical_uuid(draft_id, "draft_id")
        if not isinstance(expected_revision, int) or expected_revision < 1:
            raise StudioRejected(
                "invalid-draft-revision",
                "expected revision must be a positive integer",
            )
        if not isinstance(premise, GenesisPremise):
            raise TypeError("revise_draft requires a GenesisPremise")
        premise_json = _canonical_json(premise.to_dict())
        content_digest = _digest(premise.to_dict())
        created_at_us = _utc_microseconds()
        try:
            _begin(self._writer)
            current = self._writer.execute(
                """
                SELECT
                    branch_id,
                    profile_id,
                    current_revision,
                    sealed_snapshot_id
                FROM genesis_draft
                WHERE draft_id = ?
                """,
                (canonical_draft_id,),
            ).fetchone()
            if current is None:
                raise StudioRejected(
                    "draft-not-found",
                    "Genesis draft does not exist",
                )
            if current[3] is not None:
                raise StudioConflict(
                    "sealed-draft-immutable",
                    "sealed Genesis draft cannot be revised",
                )
            if int(current[2]) != expected_revision:
                raise StudioConflict(
                    "draft-revision-conflict",
                    "draft changed before this revision",
                )
            revision = expected_revision + 1
            self._writer.execute(
                """
                INSERT INTO genesis_draft_revision (
                    draft_id,
                    revision,
                    premise_json,
                    content_digest,
                    created_at_us
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    canonical_draft_id,
                    revision,
                    premise_json,
                    content_digest,
                    created_at_us,
                ),
            )
            self._writer.execute(
                """
                UPDATE genesis_draft
                SET current_revision = ?
                WHERE draft_id = ? AND current_revision = ?
                """,
                (revision, canonical_draft_id, expected_revision),
            )
            _commit(self._writer)
        except Exception:
            _rollback_if_needed(self._writer)
            raise
        return DraftView(
            draft_id=canonical_draft_id,
            branch_id=str(current[0]),
            profile_id=str(current[1]),
            revision=revision,
            content_fingerprint=content_digest,
            sealed_snapshot_id=None,
        )

    def create_successor(
        self,
        predecessor_snapshot_id: str,
        *,
        premise: GenesisPremise,
        correction_reason: str,
    ) -> DraftView:
        self._require_authority()
        if not isinstance(premise, GenesisPremise):
            raise TypeError("create_successor requires a GenesisPremise")
        reason = _normalize_text(
            correction_reason,
            "correction_reason",
            maximum=1_000,
        )
        predecessor = self.query_snapshot(predecessor_snapshot_id)
        draft_id = str(uuid4())
        branch_id = str(uuid4())
        premise_json = _canonical_json(premise.to_dict())
        content_digest = _digest(premise.to_dict())
        created_at_us = _utc_microseconds()
        try:
            _begin(self._writer)
            present = self._writer.execute(
                """
                SELECT profile_id
                FROM genesis_snapshot
                JOIN genesis_draft USING (draft_id)
                WHERE snapshot_id = ?
                """,
                (predecessor.snapshot_id,),
            ).fetchone()
            if present is None or str(present[0]) != predecessor.profile_id:
                raise StudioConflict(
                    "predecessor-snapshot-conflict",
                    "successor predecessor changed or is unavailable",
                )
            self._writer.execute(
                """
                INSERT INTO genesis_branch (
                    branch_id,
                    profile_id,
                    predecessor_snapshot_id,
                    lineage_relation,
                    lineage_reason,
                    created_at_us
                ) VALUES (?, ?, ?, 'successor', ?, ?)
                """,
                (
                    branch_id,
                    predecessor.profile_id,
                    predecessor.snapshot_id,
                    reason,
                    created_at_us,
                ),
            )
            self._writer.execute(
                """
                INSERT INTO genesis_draft (
                    draft_id,
                    branch_id,
                    profile_id,
                    current_revision,
                    sealed_snapshot_id,
                    created_at_us
                ) VALUES (?, ?, ?, 1, NULL, ?)
                """,
                (draft_id, branch_id, predecessor.profile_id, created_at_us),
            )
            self._writer.execute(
                """
                INSERT INTO genesis_draft_revision (
                    draft_id,
                    revision,
                    premise_json,
                    content_digest,
                    created_at_us
                ) VALUES (?, 1, ?, ?, ?)
                """,
                (draft_id, premise_json, content_digest, created_at_us),
            )
            _commit(self._writer)
        except Exception:
            _rollback_if_needed(self._writer)
            raise
        return DraftView(
            draft_id=draft_id,
            branch_id=branch_id,
            profile_id=predecessor.profile_id,
            revision=1,
            content_fingerprint=content_digest,
            sealed_snapshot_id=None,
        )

    def _draft_bundle(
        self,
        draft_id: str,
    ) -> tuple[sqlite3.Row, ParticipantProfile, GenesisPremise, str]:
        canonical_draft_id = _canonical_uuid(draft_id, "draft_id")
        row = self._writer.execute(
            """
            SELECT
                d.draft_id,
                d.branch_id,
                d.profile_id,
                d.current_revision,
                d.sealed_snapshot_id,
                b.predecessor_snapshot_id,
                b.lineage_relation,
                p.profile_json,
                p.profile_digest,
                r.premise_json,
                r.content_digest
            FROM genesis_draft AS d
            JOIN genesis_branch AS b ON b.branch_id = d.branch_id
            JOIN participant_profile AS p ON p.profile_id = d.profile_id
            JOIN genesis_draft_revision AS r
              ON r.draft_id = d.draft_id AND r.revision = d.current_revision
            WHERE d.draft_id = ?
            """,
            (canonical_draft_id,),
        ).fetchone()
        if row is None:
            raise StudioRejected("draft-not-found", "Genesis draft does not exist")
        try:
            profile_payload = json.loads(str(row[7]))
            premise_payload = json.loads(str(row[9]))
        except json.JSONDecodeError as error:
            raise StudioFailedClosed(
                "draft-corrupt",
                "stored draft payload is unreadable",
            ) from error
        profile = ParticipantProfile.from_dict(profile_payload)
        premise = GenesisPremise.from_dict(premise_payload)
        if _digest(profile.to_dict()) != str(row[8]) or (
            _digest(premise.to_dict()) != str(row[10])
        ):
            raise StudioFailedClosed(
                "draft-integrity-failed",
                "stored draft digest does not match its content",
            )
        return row, profile, premise, str(row[8])

    def query_draft(self, draft_id: str) -> DraftView:
        self._require_open()
        row, _profile, _premise, _profile_digest = self._draft_bundle(draft_id)
        return DraftView(
            draft_id=str(row[0]),
            branch_id=str(row[1]),
            profile_id=str(row[2]),
            revision=int(row[3]),
            content_fingerprint=str(row[10]),
            sealed_snapshot_id=(None if row[4] is None else str(row[4])),
        )

    def query_profile(self, profile_id: str) -> ParticipantProfile:
        self._require_open()
        canonical_id = _canonical_uuid(profile_id, "profile_id")
        row = self._writer.execute(
            """
            SELECT profile_json, profile_digest
            FROM participant_profile WHERE profile_id = ?
            """,
            (canonical_id,),
        ).fetchone()
        if row is None:
            raise StudioRejected("profile-not-found", "ParticipantProfile does not exist")
        try:
            payload = json.loads(str(row[0]))
            profile = ParticipantProfile.from_dict(payload)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise StudioFailedClosed(
                "profile-corrupt",
                "ParticipantProfile is unreadable",
            ) from error
        if profile.profile_id != canonical_id or _digest(payload) != str(row[1]):
            raise StudioFailedClosed(
                "profile-integrity-failed",
                "ParticipantProfile digest is invalid",
            )
        return profile

    def preview(self, draft_id: str) -> GenesisPreview:
        self._require_open()
        row, profile, premise, profile_digest = self._draft_bundle(draft_id)
        content_digest = str(row[10])
        basis = {
            "contract_version": CONTRACT_VERSION,
            "profile_id": profile.profile_id,
            "profile_digest": profile_digest,
            "draft_id": str(row[0]),
            "branch_id": str(row[1]),
            "revision": int(row[3]),
            "content_digest": content_digest,
            "predecessor_snapshot_id": row[5],
            "lineage_relation": str(row[6]),
        }
        return GenesisPreview(
            draft_id=str(row[0]),
            branch_id=str(row[1]),
            profile_id=profile.profile_id,
            revision=int(row[3]),
            freeze_basis_digest=_digest(basis),
            content_fingerprint=content_digest,
            premise=premise,
        )

    def _policy_question(
        self,
        draft_id: str,
        capabilities: CapabilityManifest,
        reviewed_chat_contract=None,
    ) -> PolicyQuestion:
        if not isinstance(capabilities, CapabilityManifest):
            raise TypeError("policy decision requires a CapabilityManifest")
        row, profile, premise, profile_digest = self._draft_bundle(draft_id)
        preview = self.preview(str(row[0]))
        isolation = self.isolation_proof
        if (is_reviewed_source(profile.source) or is_first_life_source(profile.source)) and profile.source == premise.source:
            isolation = IsolationProof(isolation.root_id, isolation.root_kind, isolation.path_class, REVIEWED_CHARACTER_PROOF)
        question_basis = {
            "contract_version": CONTRACT_VERSION,
            "profile_digest": profile_digest,
            "freeze_basis_digest": preview.freeze_basis_digest,
            "capability_manifest": capabilities.to_dict(),
            "isolation_proof": isolation.to_dict(),
        }
        if reviewed_chat_contract is not None:
            if capabilities == CapabilityManifest.original_whole_chat():
                if not is_reviewed_source(profile.source) or not matches_whole_source_contract(profile.source, reviewed_chat_contract):
                    raise StudioRejected("original-whole-contract-invalid", "whole contract requires the exact approved source")
                expected = reviewed_chat_contract
            elif capabilities == CapabilityManifest.reviewed_character_chat() and is_reviewed_source(profile.source):
                expected = chat_contract(dict(definition_basis=profile.source.source_asset_refs[0].split(":", 1)[1],
                    runtime_asset_sha=profile.source.source_asset_refs[1].split(":", 1)[1]),
                    reviewed_chat_contract["scope_digest"], reviewed_chat_contract["review_request_basis"])
            else:
                raise StudioRejected("reviewed-chat-contract-invalid", "chat contract requires exact reviewed source")
            if expected != reviewed_chat_contract: raise StudioRejected("reviewed-chat-contract-invalid", "chat scope or configuration changed")
            question_basis["reviewed_chat_contract"] = reviewed_chat_contract
        return PolicyQuestion(
            reviewed_chat_contract=reviewed_chat_contract,
            question_digest=_digest(question_basis),
            profile_digest=profile_digest,
            freeze_basis_digest=preview.freeze_basis_digest,
            capability_manifest=capabilities,
            isolation_proof=isolation,
            profile_source=profile.source,
            genesis_source=premise.source,
        )

    def decide_policy(
        self,
        draft_id: str,
        capabilities: CapabilityManifest,
        *,
        validity_us: int = 5_000_000,
        reviewed_chat_contract=None,
    ) -> PolicyDecision:
        self._require_authority()
        question = self._policy_question(draft_id, capabilities, reviewed_chat_contract)
        decision = self._policy_kernel.decide(question, validity_us=validity_us)
        payload = decision.to_dict()
        try:
            _begin(self._writer)
            existing = self._writer.execute(
                """
                SELECT integrity_digest
                FROM policy_decision
                WHERE decision_id = ?
                """,
                (decision.decision_id,),
            ).fetchone()
            if existing is None:
                self._writer.execute(
                    """
                    INSERT INTO policy_decision (
                        decision_id,
                        decision_json,
                        integrity_digest,
                        created_at_us
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        decision.decision_id,
                        _canonical_json(payload),
                        decision.integrity_digest,
                        _utc_microseconds(),
                    ),
                )
            elif str(existing[0]) != decision.integrity_digest:
                raise StudioConflict(
                    "policy-identity-conflict",
                    "PolicyDecision identity already names different content",
                )
            _commit(self._writer)
        except Exception:
            _rollback_if_needed(self._writer)
            raise
        return decision

    def _read_policy_decision(self, decision_id: str) -> PolicyDecision:
        canonical_id = _canonical_uuid(decision_id, "policy_decision_id")
        row = self._writer.execute(
            """
            SELECT decision_json, integrity_digest
            FROM policy_decision
            WHERE decision_id = ?
            """,
            (canonical_id,),
        ).fetchone()
        if row is None:
            raise StudioRejected(
                "policy-decision-not-found",
                "PolicyDecision does not exist",
            )
        try:
            payload = json.loads(str(row[0]))
            manifest = CapabilityManifest.from_dict(payload["capability_manifest"])
            decision = PolicyDecision._issue(
                decision_id=str(payload["decision_id"]),
                disposition=PolicyDisposition(str(payload["disposition"])),
                reason_codes=tuple(payload["reason_codes"]),
                policy_version=str(payload["policy_version"]),
                question_digest=str(payload["question_digest"]),
                issued_at_us=int(payload["issued_at_us"]),
                valid_until_us=int(payload["valid_until_us"]),
                capability_manifest=manifest,
                integrity_digest=str(payload["integrity_digest"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise StudioFailedClosed(
                "policy-decision-corrupt",
                "stored PolicyDecision is unreadable",
            ) from error
        integrity_basis = {
            "question_digest": decision.question_digest,
            "policy_version": decision.policy_version,
            "issued_at_us": decision.issued_at_us,
            "valid_until_us": decision.valid_until_us,
            "disposition": decision.disposition.value,
            "reason_codes": list(decision.reason_codes),
            "decision_id": decision.decision_id,
            "capability_manifest": decision.capability_manifest.to_dict(),
        }
        expected = _digest(integrity_basis)
        if expected != decision.integrity_digest or expected != str(row[1]):
            raise StudioFailedClosed(
                "policy-decision-integrity-failed",
                "stored PolicyDecision digest is invalid",
            )
        return decision

    def seal(
        self,
        draft_id: str,
        freeze: FreezeDecision,
        *,
        policy_decision_id: str,
        knowledge_entries: tuple[KnowledgeEntry, ...] = (),
        source_freeze_basis_digest: str | None = None,
        reviewed_definition: dict[str, Any] | None = None,
        first_life_contract: dict | None = None,
    ) -> GenesisSnapshot:
        self._require_authority()
        if not isinstance(freeze, FreezeDecision):
            raise TypeError("seal requires a FreezeDecision")
        if not isinstance(knowledge_entries, tuple) or any(
            not isinstance(entry, KnowledgeEntry) for entry in knowledge_entries
        ):
            raise TypeError("knowledge_entries must be sealed KnowledgeEntry values")
        if len(knowledge_entries) > 6 or len(
            {entry.entry_id for entry in knowledge_entries}
        ) != len(knowledge_entries):
            raise StudioRejected(
                "knowledge-members-invalid",
                "Knowledge snapshot accepts at most six unique members",
            )
        for entry in knowledge_entries:
            if (
                not entry.entry_id
                or len(entry.entry_id) > 64
                or not entry.title.strip()
                or len(entry.title) > 200
                or not entry.content.strip()
                or len(entry.content) > 4_000
                or not entry.source_ref.strip()
                or len(entry.source_ref) > 256
                or (
                    entry.evidence_quote is not None
                    and (
                        not entry.evidence_quote.strip()
                        or len(entry.evidence_quote) > 4_000
                    )
                )
            ):
                raise StudioRejected(
                    "knowledge-members-invalid",
                    "Knowledge snapshot member is invalid",
                )
        if source_freeze_basis_digest is not None:
            source_freeze_basis_digest = _canonical_sha256(
                source_freeze_basis_digest,
                "source_freeze_basis_digest",
            )
        if knowledge_entries and source_freeze_basis_digest is None:
            raise StudioRejected(
                "source-freeze-basis-required",
                "non-empty Knowledge snapshot requires exact source freeze provenance",
            )
        preview = self.preview(draft_id)
        if (
            freeze.draft_id != preview.draft_id
            or freeze.expected_revision != preview.revision
            or freeze.freeze_basis_digest != preview.freeze_basis_digest
        ):
            raise StudioConflict(
                "freeze-basis-conflict",
                "FreezeDecision does not match the current draft basis",
            )
        decision = self._read_policy_decision(policy_decision_id)
        question = self._policy_question(draft_id, decision.capability_manifest)
        revalidation = self._policy_kernel.revalidate(decision, question)
        if revalidation.disposition is not PolicyDisposition.QUALIFIED:
            raise StudioRejected(
                revalidation.reason_code,
                "PolicyDecision does not authorize seal",
            )
        row, profile, premise, _ = self._draft_bundle(draft_id)
        self._validate_reviewed_content(profile, premise, reviewed_definition, source_freeze_basis_digest, first_life_contract)
        if reviewed_definition is not None:
            reviewed_definition = json.loads(_canonical_json(reviewed_definition))
            if knowledge_entries or decision.capability_manifest != (CapabilityManifest.first_life_dormant() if first_life_contract is not None else CapabilityManifest.reviewed_character_dormant()):
                raise StudioRejected("reviewed-contract-invalid", "reviewed asset requires its dormant contract and empty legacy Knowledge")
        qualification = (REVIEWED_KNOWLEDGE_QUALIFICATION if reviewed_definition is not None else
                         "qualified-source-freeze" if knowledge_entries else "qualified-original-empty")
        snapshot_id = str(
            uuid5(
                NAMESPACE_URL,
                f"dynamic-subject-agent:genesis:{self._location.root_id}:"
                f"{freeze.decision_id}",
            )
        )
        knowledge_payload = [
            {
                "entry_id": entry.entry_id,
                "title": entry.title,
                "content": entry.content,
                "source_ref": entry.source_ref,
                "evidence_quote": entry.evidence_quote,
            }
            for entry in knowledge_entries
        ]
        knowledge_snapshot_id = str(
            uuid5(
                NAMESPACE_URL,
                "dynamic-subject-agent:knowledge:"
                f"{snapshot_id}:{_digest(knowledge_payload)}",
            )
        )
        created_at_us = _utc_microseconds()
        snapshot_payload = {
            "snapshot_id": snapshot_id,
            "knowledge_snapshot_id": knowledge_snapshot_id,
            "profile_id": profile.profile_id,
            "branch_id": str(row[1]),
            "draft_id": preview.draft_id,
            "freeze_decision_id": freeze.decision_id,
            "freeze_decision": freeze.to_dict(),
            "policy_decision_id": decision.decision_id,
            "freeze_basis_digest": preview.freeze_basis_digest,
            "content_fingerprint": preview.content_fingerprint,
            "predecessor_snapshot_id": row[5],
            "lineage_relation": str(row[6]),
            "lineage_reason": str(
                self._writer.execute(
                    "SELECT lineage_reason FROM genesis_branch WHERE branch_id = ?",
                    (str(row[1]),),
                ).fetchone()[0]
            ),
            "premise": premise.to_dict(),
            "knowledge_member_count": len(knowledge_entries),
            "source_freeze_basis_digest": source_freeze_basis_digest,
            "created_at_us": created_at_us,
        }
        if reviewed_definition is not None:
            snapshot_payload["reviewed_definition"] = reviewed_definition
        if first_life_contract is not None:
            snapshot_payload["first_life_contract"] = json.loads(_canonical_json(first_life_contract))
        snapshot_digest = _digest(snapshot_payload)
        knowledge_digest = _digest(
            {
                "knowledge_snapshot_id": knowledge_snapshot_id,
                "genesis_snapshot_id": snapshot_id,
                "member_count": len(knowledge_entries),
                "qualification": qualification,
                "members": knowledge_payload,
                "source_freeze_basis_digest": source_freeze_basis_digest,
            }
        )
        try:
            _begin(self._writer)
            existing = self._writer.execute(
                """
                SELECT
                    snapshot_id,
                    freeze_basis_digest,
                    snapshot_digest,
                    snapshot_json
                FROM genesis_snapshot
                WHERE freeze_decision_id = ?
                """,
                (freeze.decision_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != snapshot_id or str(existing[1]) != (
                    preview.freeze_basis_digest
                ):
                    raise StudioConflict(
                        "seal-identity-conflict",
                        "FreezeDecision identity already names different content",
                    )
                try:
                    existing_payload = json.loads(str(existing[3]))
                except json.JSONDecodeError as error:
                    raise StudioFailedClosed(
                        "snapshot-corrupt",
                        "stored GenesisSnapshot is unreadable",
                    ) from error
                if (existing_payload.get("freeze_decision") != freeze.to_dict()
                    or existing_payload.get("reviewed_definition") != reviewed_definition
                    or existing_payload.get("first_life_contract") != first_life_contract
                    or (reviewed_definition is not None and (
                        existing_payload.get("premise") != premise.to_dict()
                        or existing_payload.get("source_freeze_basis_digest") != source_freeze_basis_digest
                        or existing_payload.get("profile_id") != profile.profile_id))):
                    raise StudioConflict(
                        "seal-identity-conflict",
                        "FreezeDecision identity already names different content",
                    )
                if _digest(existing_payload) != str(existing[2]):
                    raise StudioFailedClosed(
                        "snapshot-integrity-failed",
                        "stored GenesisSnapshot digest is invalid",
                    )
                _commit(self._writer)
                return self.query_snapshot(snapshot_id)
            current = self._writer.execute(
                """
                SELECT current_revision, sealed_snapshot_id
                FROM genesis_draft
                WHERE draft_id = ?
                """,
                (preview.draft_id,),
            ).fetchone()
            if current is None or int(current[0]) != preview.revision:
                raise StudioConflict(
                    "freeze-basis-conflict",
                    "draft changed before seal",
                )
            if current[1] is not None:
                raise StudioConflict(
                    "branch-already-sealed",
                    "sealed Genesis cannot be overwritten",
                )
            self._writer.execute(
                """
                INSERT INTO genesis_snapshot (
                    snapshot_id,
                    draft_id,
                    branch_id,
                    freeze_decision_id,
                    freeze_basis_digest,
                    snapshot_json,
                    snapshot_digest,
                    created_at_us
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    preview.draft_id,
                    preview.branch_id,
                    freeze.decision_id,
                    preview.freeze_basis_digest,
                    _canonical_json(snapshot_payload),
                    snapshot_digest,
                    created_at_us,
                ),
            )
            self._writer.execute(
                """
                INSERT INTO knowledge_snapshot (
                    knowledge_snapshot_id,
                    genesis_snapshot_id,
                    member_count,
                    qualification,
                    snapshot_digest,
                    created_at_us
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    knowledge_snapshot_id,
                    snapshot_id,
                    len(knowledge_entries),
                    qualification,
                    knowledge_digest,
                    created_at_us,
                ),
            )
            for ordinal, entry in enumerate(knowledge_entries):
                member_payload = knowledge_payload[ordinal]
                self._writer.execute(
                    """
                    INSERT INTO knowledge_snapshot_member (
                        knowledge_snapshot_id, ordinal, entry_id, title, content,
                        source_ref, evidence_quote, member_digest
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        knowledge_snapshot_id,
                        ordinal,
                        entry.entry_id,
                        entry.title,
                        entry.content,
                        entry.source_ref,
                        entry.evidence_quote,
                        _digest(member_payload),
                    ),
                )
            self._writer.execute(
                """
                UPDATE genesis_draft
                SET sealed_snapshot_id = ?
                WHERE draft_id = ? AND sealed_snapshot_id IS NULL
                """,
                (snapshot_id, preview.draft_id),
            )
            _commit(self._writer)
        except Exception:
            _rollback_if_needed(self._writer)
            raise
        return self.query_snapshot(snapshot_id)

    @staticmethod
    def _validate_reviewed_content(profile, premise, envelope, basis, first_life_contract=None):
        if envelope is None:
            if profile.source.origin_kind == "reviewed-fiction-derived" or premise.source.origin_kind == "reviewed-fiction-derived":
                raise StudioFailedClosed("reviewed-definition-missing", "reviewed source requires a sealed complete definition")
            return
        try:
            validate_reviewed_envelope(envelope)
            pc, gc = envelope["profile_content"], envelope["genesis_content"]
            if first_life_contract is not None:
                expected = first_life_definition(envelope, first_life_contract["life_scope_digest"])
                source_ok = (expected == first_life_contract and is_first_life_source(profile.source)
                    and profile.source.source_asset_refs == first_life_source_refs(envelope, expected["life_scope_digest"])
                    and basis == expected["identity_basis"]
                    and profile.profile_id == life_profile_id(envelope["definition_basis"], expected["life_scope_digest"]))
            else:
                source_ok = (is_reviewed_source(profile.source)
                    and profile.source.source_asset_refs == reviewed_source_refs(envelope["definition_basis"], envelope["runtime_asset_sha"])
                    and basis == envelope["definition_basis"] and profile.profile_id == reviewed_profile_id(basis))
            if (not source_ok or profile.source != premise.source
                or profile.display_name != pc["display_name"] or profile.identity_core != pc["identity_core"]
                or premise.subject_identity != gc["subject_identity"] or premise.canon_start != gc["canon_start"]
                or premise.initial_relationship_premise != gc["initial_relationship_premise"]):
                raise ValueError("reviewed source content mismatch")
        except Exception as error:
            raise StudioFailedClosed("reviewed-definition-integrity-failed", "reviewed definition or source binding is invalid") from error

    def query_snapshot(self, snapshot_id: str) -> GenesisSnapshot:
        self._require_open()
        canonical_id = _canonical_uuid(snapshot_id, "snapshot_id")
        row = self._writer.execute(
            """
            SELECT s.snapshot_json, s.snapshot_digest, k.member_count,
                   k.qualification, k.snapshot_digest
            FROM genesis_snapshot AS s
            JOIN knowledge_snapshot AS k ON k.genesis_snapshot_id = s.snapshot_id
            WHERE s.snapshot_id = ?
            """,
            (canonical_id,),
        ).fetchone()
        if row is None:
            raise StudioRejected(
                "snapshot-not-found",
                "GenesisSnapshot does not exist",
            )
        try:
            payload = json.loads(str(row[0]))
            premise = GenesisPremise.from_dict(payload["premise"])
            freeze = FreezeDecision.from_dict(payload["freeze_decision"])
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise StudioFailedClosed(
                "snapshot-corrupt",
                "GenesisSnapshot is unreadable",
            ) from error
        member_count = int(row[2])
        members = self.knowledge_entries(str(payload["knowledge_snapshot_id"]))
        knowledge_payload = [
            {
                "entry_id": entry.entry_id,
                "title": entry.title,
                "content": entry.content,
                "source_ref": entry.source_ref,
                "evidence_quote": entry.evidence_quote,
            }
            for entry in members
        ]
        expected_knowledge_digest = _digest(
            {
                "knowledge_snapshot_id": str(payload["knowledge_snapshot_id"]),
                "genesis_snapshot_id": canonical_id,
                "member_count": member_count,
                "qualification": str(row[3]),
                "members": knowledge_payload,
                "source_freeze_basis_digest": payload.get(
                    "source_freeze_basis_digest"
                ),
            }
        )
        legacy_empty_digest = _digest(
            {
                "knowledge_snapshot_id": str(payload["knowledge_snapshot_id"]),
                "genesis_snapshot_id": canonical_id,
                "member_count": 0,
                "qualification": "qualified-original-empty",
            }
        )
        knowledge_digest_valid = str(row[4]) == expected_knowledge_digest or (
            member_count == 0
            and "source_freeze_basis_digest" not in payload
            and str(row[4]) == legacy_empty_digest
        )
        if (
            _digest(payload) != str(row[1])
            or member_count != int(payload["knowledge_member_count"])
            or member_count != len(members)
            or not knowledge_digest_valid
        ):
            raise StudioFailedClosed(
                "snapshot-integrity-failed",
                "GenesisSnapshot digest or KnowledgeSnapshot is invalid",
            )
        if (
            freeze.decision_id != str(payload["freeze_decision_id"])
            or freeze.draft_id != str(payload["draft_id"])
            or freeze.freeze_basis_digest != str(payload["freeze_basis_digest"])
        ):
            raise StudioFailedClosed(
                "snapshot-integrity-failed",
                "FreezeDecision provenance does not match GenesisSnapshot",
            )
        reviewed = payload.get("reviewed_definition")
        profile = self.query_profile(str(payload["profile_id"]))
        self._validate_reviewed_content(profile, premise, reviewed, payload.get("source_freeze_basis_digest"), payload.get("first_life_contract"))
        if reviewed is not None:
            current = self.preview(str(payload["draft_id"]))
            sealed_policy = self._read_policy_decision(str(payload["policy_decision_id"]))
            question = self._policy_question(str(payload["draft_id"]), sealed_policy.capability_manifest)
            if (canonical_id != payload["snapshot_id"] or current.profile_id != payload["profile_id"]
                or current.branch_id != payload["branch_id"]
                or current.freeze_basis_digest != payload["freeze_basis_digest"]
                or current.content_fingerprint != payload["content_fingerprint"]
                or sealed_policy.question_digest != question.question_digest
                or sealed_policy.capability_manifest != (CapabilityManifest.first_life_dormant() if payload.get("first_life_contract") is not None else CapabilityManifest.reviewed_character_dormant())
                or sealed_policy.disposition is not PolicyDisposition.QUALIFIED):
                raise StudioFailedClosed("reviewed-policy-binding-invalid", "sealed reviewed definition no longer matches its policy basis")
        if reviewed is not None and (member_count != 0 or str(row[3]) != REVIEWED_KNOWLEDGE_QUALIFICATION):
            raise StudioFailedClosed("reviewed-knowledge-qualification-invalid", "reviewed knowledge belongs to the sealed asset")
        if reviewed is None and str(row[3]) == REVIEWED_KNOWLEDGE_QUALIFICATION:
            raise StudioFailedClosed("reviewed-definition-missing", "reviewed qualification requires its asset")
        return GenesisSnapshot(
            snapshot_id=str(payload["snapshot_id"]),
            knowledge_snapshot_id=str(payload["knowledge_snapshot_id"]),
            profile_id=str(payload["profile_id"]),
            branch_id=str(payload["branch_id"]),
            draft_id=str(payload["draft_id"]),
            freeze_decision_id=str(payload["freeze_decision_id"]),
            policy_decision_id=str(payload["policy_decision_id"]),
            freeze_basis_digest=str(payload["freeze_basis_digest"]),
            content_fingerprint=str(payload["content_fingerprint"]),
            predecessor_snapshot_id=payload["predecessor_snapshot_id"],
            lineage_relation=str(payload["lineage_relation"]),
            lineage_reason=str(payload["lineage_reason"]),
            premise=premise,
            knowledge_member_count=int(payload["knowledge_member_count"]),
            created_at_us=int(payload["created_at_us"]),
            source_freeze_basis_digest=payload.get("source_freeze_basis_digest"),
            reviewed_definition=reviewed,
            first_life_contract=payload.get("first_life_contract"),
        )

    def knowledge_entries(
        self,
        knowledge_snapshot_id: str,
    ) -> tuple[KnowledgeEntry, ...]:
        self._require_open()
        canonical_id = _canonical_uuid(
            knowledge_snapshot_id,
            "knowledge_snapshot_id",
        )
        snapshot = self._writer.execute(
            """
            SELECT member_count FROM knowledge_snapshot
            WHERE knowledge_snapshot_id = ?
            """,
            (canonical_id,),
        ).fetchone()
        if snapshot is None:
            raise StudioRejected(
                "knowledge-snapshot-not-found",
                "KnowledgeSnapshot does not exist",
            )
        count = int(snapshot[0])
        if count == 0:
            return ()
        tables = {
            str(row[0])
            for row in self._writer.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
            ).fetchall()
        }
        if "knowledge_snapshot_member" not in tables:
            raise StudioFailedClosed(
                "knowledge-snapshot-integrity-failed",
                "non-empty KnowledgeSnapshot has no member authority",
            )
        rows = self._writer.execute(
            """
            SELECT ordinal, entry_id, title, content, source_ref,
                   evidence_quote, member_digest
            FROM knowledge_snapshot_member
            WHERE knowledge_snapshot_id = ?
            ORDER BY ordinal
            """,
            (canonical_id,),
        ).fetchall()
        if len(rows) != count or [int(row[0]) for row in rows] != list(range(count)):
            raise StudioFailedClosed(
                "knowledge-snapshot-integrity-failed",
                "KnowledgeSnapshot members are incomplete",
            )
        entries: list[KnowledgeEntry] = []
        for row in rows:
            payload = {
                "entry_id": str(row[1]),
                "title": str(row[2]),
                "content": str(row[3]),
                "source_ref": str(row[4]),
                "evidence_quote": None if row[5] is None else str(row[5]),
            }
            if _digest(payload) != str(row[6]):
                raise StudioFailedClosed(
                    "knowledge-snapshot-integrity-failed",
                    "KnowledgeSnapshot member digest is invalid",
                )
            entries.append(KnowledgeEntry(**payload))
        return tuple(entries)

    def _qri_from_payload(self, payload: Mapping[str, Any]) -> QualifiedRuntimeInput:
        capabilities_payload = payload.get("capabilities")
        isolation_payload = payload.get("isolation_proof")
        if not isinstance(capabilities_payload, Mapping) or not isinstance(
            isolation_payload, Mapping
        ):
            raise StudioFailedClosed("qri-corrupt", "QRI proof bundle is incomplete")
        isolation = IsolationProof(
            root_id=str(isolation_payload.get("root_id", "")),
            root_kind=str(isolation_payload.get("root_kind", "")),
            path_class=str(isolation_payload.get("path_class", "")),
            provenance_class=str(isolation_payload.get("provenance_class", "")),
        )
        return QualifiedRuntimeInput._published(
            _authority=_QRI_PUBLICATION_TOKEN,
            qualification_id=str(payload["qualification_id"]),
            qualification_revision=int(payload["qualification_revision"]),
            profile_id=str(payload["profile_id"]),
            genesis_branch_id=str(payload["genesis_branch_id"]),
            genesis_snapshot_id=str(payload["genesis_snapshot_id"]),
            knowledge_snapshot_id=str(payload["knowledge_snapshot_id"]),
            policy_decision_ids=tuple(payload["policy_decision_ids"]),
            capabilities=CapabilityManifest.from_dict(capabilities_payload),
            isolation_proof=isolation,
            provider_authority=str(payload["provider_authority"]),
            compatibility_proof=str(payload["compatibility_proof"]),
            predecessor_qualification_id=payload["predecessor_qualification_id"],
            publication_key=str(payload["publication_key"]),
            published_at_us=int(payload["published_at_us"]),
            integrity_digest=str(payload["integrity_digest"]),
            reviewed_chat_contract=payload.get("reviewed_chat_contract"),
            first_life_contract=payload.get("first_life_contract"),
        )

    def publish(
        self,
        snapshot_id: str,
        *,
        policy_decision_id: str,
        publication_key: str,
        predecessor_qualification_id: str | None = None,
        reviewed_chat_contract=None,
    ) -> QualifiedRuntimeInput:
        self._require_authority()
        if not isinstance(publication_key, str) or not _PUBLICATION_KEY.fullmatch(
            publication_key
        ):
            raise StudioRejected(
                "invalid-publication-key",
                "publication key must be a stable opaque identifier",
            )
        snapshot = self.query_snapshot(snapshot_id)
        decision = self._read_policy_decision(policy_decision_id)
        question = self._policy_question(
            snapshot.draft_id,
            decision.capability_manifest,
            reviewed_chat_contract,
        )
        if (
            snapshot.policy_decision_id != decision.decision_id
            and snapshot.source_freeze_basis_digest is None
        ):
            raise StudioRejected(
                "policy-snapshot-mismatch",
                "PolicyDecision did not seal this GenesisSnapshot",
            )
        if predecessor_qualification_id is not None:
            predecessor_qualification_id = _canonical_uuid(
                predecessor_qualification_id,
                "predecessor_qualification_id",
            )
        qualification_id = str(
            uuid5(
                NAMESPACE_URL,
                f"dynamic-subject-agent:qri:{self._location.root_id}:{publication_key}",
            )
        )
        compatibility_proof = _digest(
            {
                "contract_version": CONTRACT_VERSION,
                "profile_id": snapshot.profile_id,
                "genesis_snapshot_id": snapshot.snapshot_id,
                "knowledge_snapshot_id": snapshot.knowledge_snapshot_id,
                "policy_decision_id": decision.decision_id,
                "capability_manifest": decision.capability_manifest.to_dict(),
            }
        )
        publication_policy_decision_ids = (
            [decision.decision_id]
            if snapshot.policy_decision_id == decision.decision_id
            else [snapshot.policy_decision_id, decision.decision_id]
        )
        published_at_us = _utc_microseconds()
        payload_without_integrity = {
            "qualification_id": qualification_id,
            "qualification_revision": 1,
            "profile_id": snapshot.profile_id,
            "genesis_branch_id": snapshot.branch_id,
            "genesis_snapshot_id": snapshot.snapshot_id,
            "knowledge_snapshot_id": snapshot.knowledge_snapshot_id,
            "policy_decision_ids": publication_policy_decision_ids,
            "capabilities": decision.capability_manifest.to_dict(),
            "isolation_proof": question.isolation_proof.to_dict(),
            "provider_authority": (
                WHOLE_AUTHORITY
                if decision.capability_manifest == CapabilityManifest.original_whole_chat()
                else LIFE_AUTHORITY
                if decision.capability_manifest == CapabilityManifest.first_life_active()
                else LIFE_DORMANT_AUTHORITY
                if decision.capability_manifest == CapabilityManifest.first_life_dormant()
                else CHAT_AUTHORITY
                if decision.capability_manifest == CapabilityManifest.reviewed_character_chat()
                else REVIEWED_CHARACTER_AUTHORITY
                if decision.capability_manifest == CapabilityManifest.reviewed_character_dormant()
                else _PROVIDER_AUTHORITY
                if decision.capability_manifest == CapabilityManifest.m0()
                else _DEEPSEEK_PROVIDER_AUTHORITY
            ),
            "compatibility_proof": compatibility_proof,
            "predecessor_qualification_id": predecessor_qualification_id,
            "publication_key": publication_key,
            "published_at_us": published_at_us,
        }
        if snapshot.first_life_contract is not None:
            payload_without_integrity["first_life_contract"] = snapshot.first_life_contract
        if reviewed_chat_contract is not None:
            payload_without_integrity["reviewed_chat_contract"] = reviewed_chat_contract
        integrity_digest = _digest(payload_without_integrity)
        payload = {**payload_without_integrity, "integrity_digest": integrity_digest}
        publication_digest = _digest(
            {
                "snapshot_id": snapshot.snapshot_id,
                "policy_decision_id": decision.decision_id,
                "capabilities": decision.capability_manifest.to_dict(),
                "predecessor_qualification_id": predecessor_qualification_id,
            }
        )
        existing = self._writer.execute(
            """
            SELECT publication_digest, qri_json, integrity_digest
            FROM qri_publication
            WHERE publication_key = ?
            """,
            (publication_key,),
        ).fetchone()
        if existing is not None:
            if str(existing[0]) != publication_digest:
                raise StudioConflict(
                    "publication-key-conflict",
                    "publication key already names a different qualification",
                )
            return self._read_qri_row(existing)

        revalidation = self._policy_kernel.revalidate(decision, question)
        if revalidation.disposition is not PolicyDisposition.QUALIFIED:
            raise StudioRejected(
                revalidation.reason_code,
                "PolicyDecision does not authorize QRI publication",
            )

        commit_completed = False
        try:
            self._hit(StudioFaultPoint.BEFORE_PUBLICATION_TRANSACTION)
            _begin(self._writer)
            existing = self._writer.execute(
                """
                SELECT publication_digest, qri_json, integrity_digest
                FROM qri_publication
                WHERE publication_key = ?
                """,
                (publication_key,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != publication_digest:
                    raise StudioConflict(
                        "publication-key-conflict",
                        "publication key already names a different qualification",
                    )
                _commit(self._writer)
                return self._read_qri_row(existing)
            self._writer.execute(
                """
                INSERT INTO qri_publication (
                    qualification_id,
                    publication_key,
                    publication_digest,
                    qri_json,
                    integrity_digest,
                    created_at_us
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    qualification_id,
                    publication_key,
                    publication_digest,
                    _canonical_json(payload),
                    integrity_digest,
                    published_at_us,
                ),
            )
            self._hit(StudioFaultPoint.AFTER_QRI_INSERT)
            self._hit(StudioFaultPoint.BEFORE_PUBLICATION_COMMIT)
            _commit(self._writer)
            commit_completed = True
            self._hit(StudioFaultPoint.AFTER_PUBLICATION_COMMIT)
        except StudioConflict:
            _rollback_if_needed(self._writer)
            raise
        except Exception as error:
            _rollback_if_needed(self._writer)
            raise StudioInterrupted(
                (
                    "publication-response-unknown"
                    if commit_completed
                    else "publication-interrupted"
                ),
                "query or retry the same publication identity",
            ) from error
        return self.query_qri(publication_key=publication_key)

    def _read_qri_row(self, row: sqlite3.Row) -> QualifiedRuntimeInput:
        try:
            payload = json.loads(str(row[1]))
            qri = self._qri_from_payload(payload)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise StudioFailedClosed("qri-corrupt", "QRI is unreadable") from error
        payload_without_integrity = dict(payload)
        payload_without_integrity.pop("integrity_digest", None)
        expected = _digest(payload_without_integrity)
        if expected != qri.integrity_digest or expected != str(row[2]):
            raise StudioFailedClosed(
                "qri-integrity-failed",
                "QRI integrity digest is invalid",
            )
        snapshot_row = self._writer.execute("SELECT snapshot_json FROM genesis_snapshot WHERE snapshot_id = ?",
            (qri.genesis_snapshot_id,)).fetchone()
        try:
            snapshot_hint = json.loads(str(snapshot_row[0])) if snapshot_row is not None else {}
        except (TypeError, ValueError) as error:
            raise StudioFailedClosed("snapshot-corrupt", "published snapshot is unreadable") from error
        if ("first_life_contract" in snapshot_hint or qri.first_life_contract is not None
            or qri.provider_authority in (LIFE_AUTHORITY, LIFE_DORMANT_AUTHORITY)):
            return self._verify_first_life_qri(qri, self.query_snapshot(qri.genesis_snapshot_id))
        if qri.provider_authority == WHOLE_AUTHORITY or qri.capabilities == CapabilityManifest.original_whole_chat():
            return self._verify_original_whole_qri(qri, self.query_snapshot(qri.genesis_snapshot_id))
        reviewed_contract = ("reviewed_definition" in snapshot_hint
            or qri.provider_authority in (REVIEWED_CHARACTER_AUTHORITY, CHAT_AUTHORITY)
            or qri.publication_key.startswith("reviewed-character-")
            or self.query_profile(qri.profile_id).source.origin_kind == "reviewed-fiction-derived")
        snapshot = self.query_snapshot(qri.genesis_snapshot_id) if reviewed_contract else None
        active_chat = qri.provider_authority == CHAT_AUTHORITY
        expected_manifest = CapabilityManifest.reviewed_character_chat() if active_chat else CapabilityManifest.reviewed_character_dormant()
        if active_chat:
            try:
                if type(qri.reviewed_chat_contract) is not dict: raise ValueError("chat contract missing")
                expected_chat = chat_contract(snapshot.reviewed_definition, qri.reviewed_chat_contract["scope_digest"], qri.reviewed_chat_contract["review_request_basis"])
                if expected_chat != qri.reviewed_chat_contract: raise ValueError("chat scope changed")
                predecessor = self.query_qri(publication_key="reviewed-character-" + snapshot.reviewed_definition["definition_basis"])
                if (predecessor.provider_authority != REVIEWED_CHARACTER_AUTHORITY
                    or predecessor.genesis_snapshot_id != snapshot.snapshot_id
                    or qri.predecessor_qualification_id != predecessor.qualification_id):
                    raise ValueError("chat lineage changed")
            except Exception as error:
                raise StudioFailedClosed("reviewed-chat-contract-invalid", "chat scope or dormant predecessor is invalid") from error
        expected_key = ("reviewed-character-chat-" + snapshot.reviewed_definition["definition_basis"] + "-" + qri.reviewed_chat_contract["scope_digest"]
            if active_chat else "reviewed-character-" + snapshot.reviewed_definition["definition_basis"]) if snapshot is not None and snapshot.reviewed_definition is not None else ""
        if reviewed_contract and (
            snapshot.reviewed_definition is None
            or qri.provider_authority not in (REVIEWED_CHARACTER_AUTHORITY, CHAT_AUTHORITY)
            or qri.capabilities != expected_manifest
            or qri.isolation_proof != IsolationProof(self.isolation_proof.root_id, self.isolation_proof.root_kind,
                self.isolation_proof.path_class, REVIEWED_CHARACTER_PROOF)
            or snapshot.policy_decision_id not in qri.policy_decision_ids
            or qri.genesis_snapshot_id != snapshot.snapshot_id
            or qri.profile_id != snapshot.profile_id or qri.knowledge_snapshot_id != snapshot.knowledge_snapshot_id
            or qri.genesis_branch_id != snapshot.branch_id
            or qri.publication_key != expected_key
            or (not active_chat and qri.reviewed_chat_contract is not None)
        ):
            raise StudioFailedClosed("reviewed-qri-integrity-failed", "reviewed QRI does not match sealed definition")
        if snapshot is not None and snapshot.reviewed_definition is not None:
            for decision_id in qri.policy_decision_ids:
                decision = self._read_policy_decision(decision_id)
                sealing = decision_id == snapshot.policy_decision_id
                question = self._policy_question(snapshot.draft_id, decision.capability_manifest, None if sealing else qri.reviewed_chat_contract)
                if (decision.capability_manifest != (CapabilityManifest.reviewed_character_dormant() if sealing else expected_manifest)
                    or decision.question_digest != question.question_digest
                    or decision.disposition is not PolicyDisposition.QUALIFIED):
                    raise StudioFailedClosed("reviewed-qri-policy-invalid", "reviewed publication policy does not match source and asset")
            expected_compatibility = _digest(dict(contract_version=CONTRACT_VERSION,
                profile_id=snapshot.profile_id, genesis_snapshot_id=snapshot.snapshot_id,
                knowledge_snapshot_id=snapshot.knowledge_snapshot_id,
                policy_decision_id=qri.policy_decision_ids[-1], capability_manifest=qri.capabilities.to_dict()))
            if qri.compatibility_proof != expected_compatibility:
                raise StudioFailedClosed("reviewed-qri-policy-invalid", "reviewed publication compatibility proof is invalid")
        return qri

    def _verify_original_whole_qri(self, qri, snapshot):
        try:
            contract = qri.reviewed_chat_contract
            validate_whole_envelope(snapshot.reviewed_definition, contract)
            predecessor = self.query_qri(publication_key="reviewed-character-" + contract["definition_basis"])
            if (qri.provider_authority != WHOLE_AUTHORITY or qri.capabilities != CapabilityManifest.original_whole_chat()
                or qri.first_life_contract is not None or snapshot.first_life_contract is not None
                or qri.publication_key != "original-character-whole-" + contract["definition_basis"] + "-" + contract["scope_digest"]
                or predecessor.provider_authority != REVIEWED_CHARACTER_AUTHORITY
                or predecessor.genesis_snapshot_id != snapshot.snapshot_id
                or qri.predecessor_qualification_id != predecessor.qualification_id
                or qri.profile_id != snapshot.profile_id or qri.genesis_snapshot_id != snapshot.snapshot_id
                or qri.knowledge_snapshot_id != snapshot.knowledge_snapshot_id or qri.genesis_branch_id != snapshot.branch_id
                or qri.isolation_proof != predecessor.isolation_proof
                or qri.policy_decision_ids != (snapshot.policy_decision_id, qri.policy_decision_ids[-1])
                or qri.policy_decision_ids[-1] == snapshot.policy_decision_id):
                raise ValueError("whole qualification lineage invalid")
            for decision_id in qri.policy_decision_ids:
                decision = self._read_policy_decision(decision_id)
                sealing = decision_id == snapshot.policy_decision_id
                manifest = CapabilityManifest.reviewed_character_dormant() if sealing else CapabilityManifest.original_whole_chat()
                question = self._policy_question(snapshot.draft_id, manifest, None if sealing else contract)
                if (decision.capability_manifest != manifest or decision.question_digest != question.question_digest
                    or decision.disposition is not PolicyDisposition.QUALIFIED):
                    raise ValueError("whole policy invalid")
            expected = _digest(dict(contract_version=CONTRACT_VERSION, profile_id=snapshot.profile_id,
                genesis_snapshot_id=snapshot.snapshot_id, knowledge_snapshot_id=snapshot.knowledge_snapshot_id,
                policy_decision_id=qri.policy_decision_ids[-1], capability_manifest=qri.capabilities.to_dict()))
            if qri.compatibility_proof != expected:
                raise ValueError("whole compatibility invalid")
        except Exception as error:
            raise StudioFailedClosed("original-whole-qri-invalid", "whole qualification does not match the approved definition and purpose") from error
        return qri

    def _verify_first_life_qri(self, qri, snapshot):
        try:
            contract = snapshot.first_life_contract
            if contract is None or qri.first_life_contract != contract: raise ValueError("life definition missing")
            active = qri.provider_authority == LIFE_AUTHORITY
            manifest = CapabilityManifest.first_life_active() if active else CapabilityManifest.first_life_dormant()
            key = ("first-life-active-" if active else "first-life-dormant-") + contract["identity_basis"]
            if (qri.provider_authority not in (LIFE_AUTHORITY, LIFE_DORMANT_AUTHORITY) or qri.capabilities != manifest
                or qri.publication_key != key or qri.profile_id != snapshot.profile_id
                or qri.genesis_snapshot_id != snapshot.snapshot_id or qri.genesis_branch_id != snapshot.branch_id
                or qri.knowledge_snapshot_id != snapshot.knowledge_snapshot_id or qri.reviewed_chat_contract is not None
                or qri.isolation_proof != IsolationProof(self.isolation_proof.root_id, self.isolation_proof.root_kind,
                    self.isolation_proof.path_class, REVIEWED_CHARACTER_PROOF)
                or snapshot.policy_decision_id not in qri.policy_decision_ids): raise ValueError("life qualification mismatch")
            if active:
                predecessor = self.query_qri(publication_key="first-life-dormant-" + contract["identity_basis"])
                if qri.predecessor_qualification_id != predecessor.qualification_id: raise ValueError("life predecessor mismatch")
            for decision_id in qri.policy_decision_ids:
                decision = self._read_policy_decision(decision_id)
                expected_manifest = CapabilityManifest.first_life_dormant() if decision_id == snapshot.policy_decision_id else manifest
                question = self._policy_question(snapshot.draft_id, decision.capability_manifest)
                if (decision.capability_manifest != expected_manifest or decision.question_digest != question.question_digest
                    or decision.disposition is not PolicyDisposition.QUALIFIED): raise ValueError("life policy mismatch")
            compatibility = _digest(dict(contract_version=CONTRACT_VERSION, profile_id=snapshot.profile_id,
                genesis_snapshot_id=snapshot.snapshot_id, knowledge_snapshot_id=snapshot.knowledge_snapshot_id,
                policy_decision_id=qri.policy_decision_ids[-1], capability_manifest=qri.capabilities.to_dict()))
            if compatibility != qri.compatibility_proof: raise ValueError("life compatibility mismatch")
        except Exception as error:
            raise StudioFailedClosed("first-life-qualification-invalid", "life source, scope or qualification is invalid") from error
        return qri

    def query_qri(self, *, publication_key: str) -> QualifiedRuntimeInput:
        self._require_open()
        if not isinstance(publication_key, str):
            raise StudioRejected(
                "invalid-publication-key",
                "publication key must be text",
            )
        row = self._writer.execute(
            """
            SELECT publication_digest, qri_json, integrity_digest
            FROM qri_publication
            WHERE publication_key = ?
            """,
            (publication_key,),
        ).fetchone()
        if row is None:
            raise StudioRejected("qri-not-found", "QRI publication does not exist")
        return self._read_qri_row(row)

    def _query_qri_by_qualification_id(
        self, qualification_id: str
    ) -> QualifiedRuntimeInput:
        self._require_open()
        canonical_id = _canonical_uuid(qualification_id, "qualification_id")
        row = self._writer.execute(
            "SELECT publication_digest, qri_json, integrity_digest FROM qri_publication WHERE qualification_id = ?",
            (canonical_id,),
        ).fetchone()
        if row is None:
            raise StudioRejected("qri-not-found", "QRI publication does not exist")
        return self._read_qri_row(row)


def _data_control_export_snapshot(
    location: StudioRootRef,
    *,
    publication_key: str,
    expected_qualification_id: str,
    expected_profile_id: str,
) -> dict[str, Any]:
    """Return a verified typed publication view without exposing ProfileStore writes."""

    studio = SubjectStudio.open(location, policy_kernel=PolicyKernel())
    try:
        qri = studio.query_qri(publication_key=publication_key)
        if (
            qri.qualification_id != expected_qualification_id
            or qri.profile_id != expected_profile_id
            or qri.isolation_proof.root_id != location.root_id
        ):
            raise StudioFailedClosed(
                "data-control-authority-mismatch",
                "QRI identity does not match the selected DataControl scope",
            )
        snapshot = studio.query_snapshot(qri.genesis_snapshot_id)
        if (
            snapshot.profile_id != expected_profile_id
            or snapshot.snapshot_id != qri.genesis_snapshot_id
            or snapshot.knowledge_snapshot_id != qri.knowledge_snapshot_id
            or snapshot.policy_decision_id not in qri.policy_decision_ids
        ):
            raise StudioFailedClosed(
                "data-control-publication-mismatch",
                "sealed Profile, GenesisSnapshot, and QRI do not form one publication",
            )
        profile_row = studio._writer.execute(
            """
            SELECT profile_json, profile_digest
            FROM participant_profile
            WHERE profile_id = ?
            """,
            (expected_profile_id,),
        ).fetchone()
        snapshot_row = studio._writer.execute(
            """
            SELECT snapshot_json, snapshot_digest
            FROM genesis_snapshot
            WHERE snapshot_id = ?
            """,
            (snapshot.snapshot_id,),
        ).fetchone()
        knowledge_row = studio._writer.execute(
            """
            SELECT member_count, qualification, snapshot_digest
            FROM knowledge_snapshot
            WHERE knowledge_snapshot_id = ? AND genesis_snapshot_id = ?
            """,
            (snapshot.knowledge_snapshot_id, snapshot.snapshot_id),
        ).fetchone()
        if profile_row is None or snapshot_row is None or knowledge_row is None:
            raise StudioFailedClosed(
                "data-control-publication-incomplete",
                "selected Studio publication is incomplete",
            )
        profile_payload = json.loads(str(profile_row[0]))
        snapshot_payload = json.loads(str(snapshot_row[0]))
        profile = ParticipantProfile.from_dict(profile_payload)
        knowledge_entries = studio.knowledge_entries(
            snapshot.knowledge_snapshot_id
        )
        if (
            profile.profile_id != expected_profile_id
            or _digest(profile_payload) != str(profile_row[1])
            or _digest(snapshot_payload) != str(snapshot_row[1])
            or int(knowledge_row[0]) != len(knowledge_entries)
        ):
            raise StudioFailedClosed(
                "data-control-publication-integrity-failed",
                "selected Studio publication failed integrity verification",
            )
        policies = [
            studio._read_policy_decision(decision_id).to_dict()
            for decision_id in qri.policy_decision_ids
        ]
        schema_version = int(
            studio._writer.execute(
                "SELECT schema_version FROM store_manifest WHERE singleton = 1"
            ).fetchone()[0]
        )
        return {
            "record_kind": "profile-genesis-publication",
            "schema_family": PROFILE_SCHEMA_FAMILY,
            "schema_version": schema_version,
            "contract_version": CONTRACT_VERSION,
            "persistence_version": PERSISTENCE_VERSION,
            "source_root": location.to_dict(),
            "profile": profile.to_dict(),
            "genesis_snapshot": snapshot_payload,
            "knowledge_snapshot": {
                "knowledge_snapshot_id": snapshot.knowledge_snapshot_id,
                "genesis_snapshot_id": snapshot.snapshot_id,
                "member_count": int(knowledge_row[0]),
                "qualification": str(knowledge_row[1]),
                "snapshot_digest": str(knowledge_row[2]),
                **(
                    {
                        "members": [
                            {
                                "entry_id": entry.entry_id,
                                "title": entry.title,
                                "content": entry.content,
                                "source_ref": entry.source_ref,
                                "evidence_quote": entry.evidence_quote,
                            }
                            for entry in knowledge_entries
                        ]
                    }
                    if knowledge_entries
                    else {}
                ),
            },
            "policy_decisions": policies,
            "qualified_runtime_input": qri.to_dict(),
        }
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise StudioFailedClosed(
            "data-control-publication-corrupt",
            "selected Studio publication is unreadable",
        ) from error
    finally:
        studio.close()


def _data_control_begin_clear(
    location: StudioRootRef,
    *,
    scope_id: str,
    publication_key: str,
    expected_qualification_id: str,
    expected_profile_id: str,
) -> int:
    """Withdraw Studio authority and durably bind it to one clear scope."""

    canonical_scope = _canonical_uuid(scope_id, "data_control_scope_id")
    _data_control_export_snapshot(
        location,
        publication_key=publication_key,
        expected_qualification_id=expected_qualification_id,
        expected_profile_id=expected_profile_id,
    )
    _validate_existing_root(
        location.root,
        location.root_id,
        location.root_kind,
    )
    _read_root_identity(location)
    connection = _connect_existing(location.profile_database)
    try:
        _verify_store(location, connection)
        _begin(connection)
        row = connection.execute(
            """
            SELECT governance_epoch, governance_state, data_control_scope_id
            FROM profile_governance
            WHERE singleton = 1
            """
        ).fetchone()
        if row is None:
            raise StudioFailedClosed(
                "profile-governance-invalid",
                "Profile governance state is absent",
            )
        epoch = int(row[0])
        state = str(row[1])
        bound_scope = None if row[2] is None else str(row[2])
        if state == "active" and bound_scope is None:
            epoch += 1
            connection.execute(
                """
                UPDATE profile_governance
                SET governance_epoch = ?, governance_state = 'clearing',
                    data_control_scope_id = ?
                WHERE singleton = 1
                """,
                (epoch, canonical_scope),
            )
        elif state != "clearing" or bound_scope != canonical_scope:
            raise StudioRejected(
                "data-control-scope-conflict",
                "Profile authority is bound to a different governance operation",
            )
        _commit(connection)
        return epoch
    except Exception:
        _rollback_if_needed(connection)
        raise
    finally:
        connection.close()


def _data_control_verify_clear_target(
    location: StudioRootRef,
    *,
    scope_id: str,
    publication_key: str,
    expected_qualification_id: str,
    expected_profile_id: str,
) -> dict[str, str]:
    """Recheck the exact clearing Profile capsule immediately before deletion."""

    canonical_scope = _canonical_uuid(scope_id, "data_control_scope_id")
    _validate_existing_root(
        location.root,
        location.root_id,
        location.root_kind,
    )
    _read_root_identity(location)
    connection = _connect_existing(location.profile_database)
    try:
        _verify_store(location, connection)
        governance = connection.execute(
            """
            SELECT governance_state, data_control_scope_id
            FROM profile_governance
            WHERE singleton = 1
            """
        ).fetchone()
        qri = connection.execute(
            """
            SELECT qri_json, integrity_digest
            FROM qri_publication
            WHERE publication_key = ?
            """,
            (publication_key,),
        ).fetchone()
        if governance is None or tuple(governance) != ("clearing", canonical_scope):
            raise StudioFailedClosed(
                "profile-governance-mismatch",
                "Profile capsule is not fenced by the selected clear scope",
            )
        if qri is None:
            raise StudioFailedClosed(
                "data-control-publication-incomplete",
                "selected QRI is absent before Profile deletion",
            )
        payload = json.loads(str(qri[0]))
        unsigned = dict(payload)
        unsigned.pop("integrity_digest", None)
        if (
            str(payload.get("qualification_id")) != expected_qualification_id
            or str(payload.get("profile_id")) != expected_profile_id
            or _digest(unsigned) != str(qri[1])
            or str(payload.get("integrity_digest")) != str(qri[1])
        ):
            raise StudioFailedClosed(
                "data-control-publication-integrity-failed",
                "selected QRI identity changed before Profile deletion",
            )
        return {
            "root_id": location.root_id,
            "store_id": location.profile_store_id,
            "profile_id": expected_profile_id,
            "qualification_id": expected_qualification_id,
            "scope_id": canonical_scope,
        }
    except json.JSONDecodeError as error:
        raise StudioFailedClosed(
            "data-control-publication-corrupt",
            "selected QRI is unreadable before Profile deletion",
        ) from error
    finally:
        connection.close()


__all__ = [
    "AcceptedArtifactDraftBundle",
    "AcceptedArtifactSnapshot",
    "AcceptedArtifactSnapshotBundle",
    "CapabilityManifest",
    "DraftView",
    "FreezeDecision",
    "GenesisPremise",
    "GenesisPreview",
    "GenesisSnapshot",
    "IsolationProof",
    "KnowledgeDraftPreview",
    "ParticipantProfile",
    "PolicyDecision",
    "PolicyDisposition",
    "PolicyKernel",
    "PolicyQuestion",
    "PolicyRevalidation",
    "QualifiedRuntimeInput",
    "ScopedFreezeDecision",
    "SnapshotCompatibilityProof",
    "SourceDeclaration",
    "StudioConflict",
    "StudioFailedClosed",
    "StudioFaultPoint",
    "StudioInterrupted",
    "StudioProblem",
    "StudioRejected",
    "StudioRootRef",
    "SubjectStudio",
]
