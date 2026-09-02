"""M0 RuntimeAuthorityBinding and process-local RuntimeHost routing.

RuntimeHost is the private Host deep Module joining an immutable published QRI
to one whole Timeline binding and one process-local SubjectRuntime lane.  Its
ControlStore owns binding lifecycle; TimelineStore contains only the matching
Admission gate used for fencing.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
from pathlib import Path
from time import time_ns
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from dynamic_subject_agent.local_llama import (
    LocalLlamaCognition,
    _LocalLlamaProcessTransport,
    _LocalLlamaTransport,
)
from dynamic_subject_agent.runtime import (
    CognitionEngine,
    RuntimeFaultPoint,
    RuntimeResult,
    SubjectRuntime,
    _DeterministicLocalCognitionDouble,
    _HOST_RUNTIME_TOKEN,
    _LOCAL_LLAMA_COGNITION_TOKEN,
    _LOCAL_FIRST_TEST_COGNITION_TOKEN,
    _UserConfirmedContextBrief,
    _DormantArtifactCognition,
)
from dynamic_subject_agent.studio import (
    CapabilityManifest,
    IsolationProof,
    PolicyDecision,
    PolicyDisposition,
    PolicyKernel,
    QualifiedRuntimeInput,
    StudioRootRef,
    SubjectStudio,
    _DORMANT_ARTIFACT_PROVIDER_AUTHORITY,
    _DEEPSEEK_PROVIDER_AUTHORITY,
    _LOCAL_FIRST_TEST_PROVIDER_AUTHORITY,
    _LOCAL_LLAMA_PROVIDER_AUTHORITY,
    _CORRECTIVE_LOCAL_LLAMA_SUCCESSOR_AUTHORITY,
    _QRI_PUBLICATION_TOKEN,
    _digest as _studio_digest,
    _issue_corrective_policy_decision,
    _local_first_phase1_test_interaction,
    _local_first_phase3_local_interaction,
    _local_first_interaction_basis_digest,
    _local_first_successor_compatibility_digest,
    _read_root_identity as _read_studio_root_identity,
    _validate_existing_root as _validate_studio_existing_root,
    _verify_store as _verify_studio_store,
    StudioRejected,
)
from dynamic_subject_agent.timeline import (
    CONTROL_SCHEMA_FAMILY as TIMELINE_CONTROL_SCHEMA_FAMILY,
    TIMELINE_SCHEMA_FAMILY,
    CanonicalRootRef,
    ConversationTurnRecord,
    LivingMemoryRecord,
    RelationshipStanceInteraction,
    OperationRef,
    OperationState,
    SubjectCommand,
    TimelineBasis,
    TimelineEngine,
    _HOST_TIMELINE_TOKEN,
    _ReservedTimelineIdentity,
    _RuntimeBindingAuthority,
    _CONTROL_TABLES as _TIMELINE_CONTROL_TABLES,
    _TIMELINE_TABLES,
    _EMPTY_REVISION_HEAD_DIGEST,
    _EMPTY_VERIFIED_PREFIX_DIGEST,
    _read_root_identity as _read_timeline_root_identity,
    _validate_existing_root as _validate_timeline_existing_root,
    _verify_connection_profile as _verify_timeline_connection_profile,
    _verify_manifest as _verify_timeline_manifest,
    _verify_store_integrity as _verify_timeline_store_integrity,
    _read_admission_gate as _read_timeline_admission_gate,
    _read_timeline_basis,
)
from dynamic_subject_agent.participant_goals import ParticipantGoalCommitmentRecord
from dynamic_subject_agent.situated_state import SituatedStateRecord
from dynamic_subject_agent.medium_state import MediumSignalRecord, MediumStateRecord
from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection


CONTRACT_VERSION = "M0-CONTRACT-1.0"
PERSISTENCE_VERSION = "M0-PERSISTENCE-1.0"
HOST_SCHEMA_VERSION = 2
HOST_ROOT_FORMAT = "dynamic-subject-m0-runtime-host"
HOST_ROOT_EPOCH = 1
HOST_ROOT_KIND = "test-fixture"
EXPERIMENTAL_ROOT_KIND = "experimental"
_HOST_ROOT_KINDS = frozenset({HOST_ROOT_KIND, EXPERIMENTAL_ROOT_KIND})
HOST_SCHEMA_FAMILY = "m0-runtime-host-control"
RUNTIME_KIND = "mature-canonical"
RUNTIME_CONTRACT_VERSION = "m0-a-cycle-1.0"
PROVIDER_AUTHORITY = "fake-cognition:m0-a-cycle-1.0"
_SUPPORTED_PROVIDER_AUTHORITIES = frozenset(
    {
        PROVIDER_AUTHORITY,
        _DEEPSEEK_PROVIDER_AUTHORITY,
        _DORMANT_ARTIFACT_PROVIDER_AUTHORITY,
        _LOCAL_FIRST_TEST_PROVIDER_AUTHORITY,
        _LOCAL_LLAMA_PROVIDER_AUTHORITY,
    }
)
ALLOWED_INTENTS = ("ask-collaborator-status",)
ALLOWED_PROVENANCE = ("project-original",)
REQUIRED_CAPABILITIES = frozenset(
    {"fake-cognition", "four-domain-typed-noop", "host-authoring"}
)
FORBIDDEN_CAPABILITIES = frozenset(
    {"real-cognition", "real-provider", "network-access", "external-tools", "tts"}
)
_RESERVED_TEST_PATH_SEGMENTS = frozenset({"legacy", "private", "retired"})
_WILDCARD_OR_EXPANSION = frozenset("*?[]%${}")
_PROCESS_REGISTRY_LOCK = threading.RLock()
_PROCESS_REGISTRY: dict[str, str] = {}
_FORWARD_GOVERNANCE_SESSION_LOCK = threading.RLock()
_FORWARD_GOVERNANCE_SESSIONS: set[object] = set()
_COGNITION_ASSEMBLY_TOKEN = object()
_NORMAL_GOVERNANCE_ACTIVATION = object()
_TEST_HELD_GOVERNANCE_ACTIVATION = object()
_RETIRE_GOVERNANCE_TRANSITION = object()
_FORWARD_GOVERNANCE_INSTALL_AUTHORITY = object()
_CORRECTIVE_SUCCESSOR_PREPARATION_AUTHORITY = object()
_LOCAL_SERVING_AUTHORITY_TOKEN = object()
_POST_M0_05_PHASE2_RESULT_SHA256 = (
    "6c6d42154606e6702f3de949afce153e3a97c4282cf60da44994030682dc6056"
)
_BRANCH_NORMAL = "normal"
_BRANCH_NONCONFORMING = "nonconforming-experimental"
_BRANCH_ELIGIBLE = "eligible"
_BRANCH_HELD = "held"
_BRANCH_RETIRED = "retired"


def _qri_provider_contract_matches(qri: QualifiedRuntimeInput) -> bool:
    if qri.provider_authority == PROVIDER_AUTHORITY:
        return qri.capabilities == CapabilityManifest.m0()
    if qri.provider_authority == _DEEPSEEK_PROVIDER_AUTHORITY:
        return (
            qri.capabilities
            == CapabilityManifest.deepseek_v4_flash_experimental()
        )
    if qri.provider_authority == _DORMANT_ARTIFACT_PROVIDER_AUTHORITY:
        return qri.capabilities == CapabilityManifest.accepted_artifact_dormant()
    if qri.provider_authority == _LOCAL_FIRST_TEST_PROVIDER_AUTHORITY:
        return qri.capabilities == CapabilityManifest._local_first_test_double()
    if qri.provider_authority == _LOCAL_LLAMA_PROVIDER_AUTHORITY:
        return qri.capabilities == CapabilityManifest._local_llama_experimental()
    return False


def _cognition_contract_supported(cognition: object) -> bool:
    if not isinstance(cognition, CognitionEngine):
        return False
    if cognition.provider_authority == _DORMANT_ARTIFACT_PROVIDER_AUTHORITY:
        return type(cognition) is _DormantArtifactCognition
    if cognition.provider_authority == _LOCAL_FIRST_TEST_PROVIDER_AUTHORITY:
        return type(cognition) is _DeterministicLocalCognitionDouble
    if cognition.provider_authority == _LOCAL_LLAMA_PROVIDER_AUTHORITY:
        return type(cognition) is LocalLlamaCognition
    return cognition.provider_authority in _SUPPORTED_PROVIDER_AUTHORITIES


class BindingState(str, Enum):
    VALIDATED = "validated"
    ACTIVE = "active"
    REJECTED = "rejected"
    INVALIDATED = "invalidated"
    RETIRED = "retired"


class RuntimeHostFaultPoint(str, Enum):
    AFTER_TIMELINE_BUILD = "after-timeline-build"
    AFTER_ASSEMBLY_HEALTH = "after-assembly-health"
    AFTER_OLD_GATE_CLOSED = "after-old-gate-closed"
    AFTER_CONTROL_ACTIVATION = "after-control-activation"
    AFTER_TIMELINE_GATE_OPEN = "after-timeline-gate-open"
    AFTER_LANE_INSTALL = "after-lane-install"
    AFTER_RETIRE_GATE_CLOSED = "after-retire-gate-closed"


class _ForwardGovernanceFaultPoint(str, Enum):
    AFTER_LOCKED_PREFLIGHT = "after-locked-preflight"
    AFTER_V2_DELTA_DDL = "after-v2-delta-ddl"
    AFTER_MANIFEST_VERSION_UPDATE = "after-manifest-version-update"
    AFTER_INITIAL_GOVERNANCE_FACT = "after-initial-governance-fact"
    BEFORE_COMMIT = "before-commit"
    AFTER_COMMIT_BEFORE_RECEIPT = "after-commit-before-receipt"


class _CorrectiveSuccessorFaultPoint(str, Enum):
    AFTER_QRI_APPEND = "after-qri-append"
    AFTER_ROOT_COMMITMENT = "after-root-commitment"
    AFTER_TIMELINE_ROOT = "after-timeline-root"
    AFTER_LOCKED_PREFLIGHT = "after-locked-preflight"
    BEFORE_COMMIT = "before-commit"
    AFTER_COMMIT_BEFORE_RECEIPT = "after-commit-before-receipt"


class RuntimeHostProblem(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class RuntimeHostRejected(RuntimeHostProblem):
    """Input or lifecycle state is deterministically outside Host authority."""


class RuntimeHostConflict(RuntimeHostProblem):
    """A second owner, binding, runtime, or lease contended with the active lane."""


class RuntimeHostFailedClosed(RuntimeHostProblem):
    """The Host could not prove a safe build, identity, or recovery decision."""


class RuntimeHostInterrupted(RuntimeHostProblem):
    def __init__(
        self,
        fault_point: RuntimeHostFaultPoint,
        detail: str = "query canonical binding state and retry the same activation",
    ) -> None:
        super().__init__("runtime-host-interrupted", detail)
        self.fault_point = fault_point


@dataclass(frozen=True, init=False)
class _LocalFirstSubmissionAuthorization:
    authorization_id: str
    qualification_id: str
    qri_integrity_digest: str
    provider_authority: str
    profile_id: str
    timeline_id: str
    command_fingerprint: str
    idempotency_key_digest: str
    confirmed_brief_digest: str
    interaction_basis_digest: str
    plan_digest: str

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("local submission authorization is internally issued")

    @classmethod
    def _issue(
        cls,
        *,
        qri: QualifiedRuntimeInput,
        command: SubjectCommand,
        idempotency_key: str,
        confirmed_brief: _UserConfirmedContextBrief,
        _authority: object,
    ) -> _LocalFirstSubmissionAuthorization:
        if _authority is not _COGNITION_ASSEMBLY_TOKEN:
            raise TypeError("local submission authorization requires Host authority")
        if (
            type(qri) is not QualifiedRuntimeInput
            or (
                qri.provider_authority != _LOCAL_FIRST_TEST_PROVIDER_AUTHORITY
                and qri.provider_authority != _LOCAL_LLAMA_PROVIDER_AUTHORITY
            )
            or type(command) is not SubjectCommand
            or command.target_profile_id != qri.profile_id
            or not isinstance(idempotency_key, str)
            or not idempotency_key
            or len(idempotency_key) > 256
            or type(confirmed_brief) is not _UserConfirmedContextBrief
        ):
            raise RuntimeHostRejected(
                "local-interaction-plan-mismatch",
                "local submission plan is incomplete or targets another authority",
            )
        idempotency_digest = sha256(idempotency_key.encode("utf-8")).hexdigest()
        interaction_basis_digest = _local_first_interaction_basis_digest(
            profile_id=qri.profile_id,
            timeline_id=command.target_timeline_id,
            command_fingerprint=command.payload_fingerprint,
            idempotency_key_digest=idempotency_digest,
            confirmed_brief_digest=confirmed_brief.content_digest,
        )
        basis = {
            "qualification_id": qri.qualification_id,
            "qri_integrity_digest": qri.integrity_digest,
            "provider_authority": qri.provider_authority,
            "profile_id": qri.profile_id,
            "timeline_id": command.target_timeline_id,
            "command_fingerprint": command.payload_fingerprint,
            "idempotency_key_digest": idempotency_digest,
            "confirmed_brief_digest": confirmed_brief.content_digest,
            "interaction_basis_digest": interaction_basis_digest,
        }
        plan_digest = sha256(
            json.dumps(
                basis,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        instance = object.__new__(cls)
        values = {
            "authorization_id": str(
                uuid5(NAMESPACE_URL, f"post-m0-04-local-plan:{plan_digest}")
            ),
            **basis,
            "plan_digest": plan_digest,
        }
        for field, value in values.items():
            object.__setattr__(instance, field, value)
        return instance


    def matches(
        self,
        binding: RuntimeAuthorityBinding,
        command: SubjectCommand,
        idempotency_key: str,
    ) -> bool:
        return (
            type(binding) is RuntimeAuthorityBinding
            and type(command) is SubjectCommand
            and binding.qualification_id == self.qualification_id
            and binding.qri_integrity_digest == self.qri_integrity_digest
            and binding.profile_id == self.profile_id
            and binding.timeline_id == self.timeline_id
            and command.target_profile_id == self.profile_id
            and command.target_timeline_id == self.timeline_id
            and command.payload_fingerprint == self.command_fingerprint
            and isinstance(idempotency_key, str)
            and sha256(idempotency_key.encode("utf-8")).hexdigest()
            == self.idempotency_key_digest
        )


@dataclass(frozen=True, init=False)
class _LocalServingAuthorization:
    authorization_id: str
    entry_contract_sha256: str
    host_root_id: str
    host_control_store_id: str
    binding_id: str
    binding_revision: int
    binding_epoch: int
    profile_id: str
    timeline_id: str
    qualification_id: str
    qri_integrity_digest: str
    timeline_root_id: str
    timeline_control_store_id: str
    timeline_store_id: str
    preparation_record_sha256: str
    cognition_plan_digest: str
    plan_digest: str

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("local serving authorization is internally issued")

    @classmethod
    def _issue(
        cls,
        *,
        location: RuntimeHostRootRef,
        binding: RuntimeAuthorityBinding,
        qri: QualifiedRuntimeInput,
        entry_contract_sha256: str,
        preparation_record_sha256: str,
        cognition_plan_digest: str,
        _authority: object,
    ) -> _LocalServingAuthorization:
        if _authority is not _LOCAL_SERVING_AUTHORITY_TOKEN:
            raise TypeError("local serving authorization requires Host authority")
        if (
            type(location) is not RuntimeHostRootRef
            or type(binding) is not RuntimeAuthorityBinding
            or type(qri) is not QualifiedRuntimeInput
            or not isinstance(entry_contract_sha256, str)
            or len(entry_contract_sha256) != 64
            or any(character not in "0123456789abcdef" for character in entry_contract_sha256)
            or not isinstance(preparation_record_sha256, str)
            or len(preparation_record_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in preparation_record_sha256
            )
            or not isinstance(cognition_plan_digest, str)
            or len(cognition_plan_digest) != 64
            or any(
                character not in "0123456789abcdef"
                for character in cognition_plan_digest
            )
            or binding.state is not BindingState.ACTIVE
            or binding.profile_id != qri.profile_id
            or binding.qualification_id != qri.qualification_id
            or binding.qri_integrity_digest != qri.integrity_digest
        ):
            raise RuntimeHostRejected(
                "local-serving-authorization-mismatch",
                "serving authorization does not bind one exact prepared authority",
            )
        basis = {
            "entry_contract_sha256": entry_contract_sha256,
            "host_root_id": location.root_id,
            "host_control_store_id": location.control_store_id,
            "binding_id": binding.binding_id,
            "binding_revision": binding.binding_revision,
            "binding_epoch": binding.binding_epoch,
            "profile_id": binding.profile_id,
            "timeline_id": binding.timeline_id,
            "qualification_id": qri.qualification_id,
            "qri_integrity_digest": qri.integrity_digest,
            "timeline_root_id": binding.timeline_root.root_id,
            "timeline_control_store_id": binding.timeline_root.control_store_id,
            "timeline_store_id": binding.timeline_root.timeline_store_id,
            "preparation_record_sha256": preparation_record_sha256,
            "cognition_plan_digest": cognition_plan_digest,
        }
        plan_digest = sha256(
            json.dumps(basis, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()
        instance = object.__new__(cls)
        for field, value in {
            "authorization_id": str(
                uuid5(NAMESPACE_URL, f"post-m0-08-local-serving:{plan_digest}")
            ),
            **basis,
            "plan_digest": plan_digest,
        }.items():
            object.__setattr__(instance, field, value)
        return instance

    def matches(
        self,
        location: RuntimeHostRootRef,
        binding: RuntimeAuthorityBinding,
        qri: QualifiedRuntimeInput,
        cognition_plan_digest: str,
    ) -> bool:
        return (
            self._is_intrinsically_valid()
            and cognition_plan_digest == self.cognition_plan_digest
            and type(location) is RuntimeHostRootRef
            and type(binding) is RuntimeAuthorityBinding
            and type(qri) is QualifiedRuntimeInput
            and location.root_id == self.host_root_id
            and location.control_store_id == self.host_control_store_id
            and binding.binding_id == self.binding_id
            and binding.binding_revision == self.binding_revision
            and binding.binding_epoch == self.binding_epoch
            and binding.profile_id == self.profile_id == qri.profile_id
            and binding.timeline_id == self.timeline_id
            and binding.qualification_id == self.qualification_id == qri.qualification_id
            and binding.qri_integrity_digest
            == self.qri_integrity_digest
            == qri.integrity_digest
            and binding.timeline_root.root_id == self.timeline_root_id
            and binding.timeline_root.control_store_id
            == self.timeline_control_store_id
            and binding.timeline_root.timeline_store_id == self.timeline_store_id
        )

    def matches_binding(
        self,
        location: RuntimeHostRootRef,
        binding: RuntimeAuthorityBinding,
    ) -> bool:
        return (
            self._is_intrinsically_valid()
            and type(location) is RuntimeHostRootRef
            and type(binding) is RuntimeAuthorityBinding
            and location.root_id == self.host_root_id
            and location.control_store_id == self.host_control_store_id
            and binding.binding_id == self.binding_id
            and binding.binding_revision == self.binding_revision
            and binding.binding_epoch == self.binding_epoch
            and binding.profile_id == self.profile_id
            and binding.timeline_id == self.timeline_id
            and binding.qualification_id == self.qualification_id
            and binding.qri_integrity_digest == self.qri_integrity_digest
            and binding.timeline_root.root_id == self.timeline_root_id
            and binding.timeline_root.control_store_id
            == self.timeline_control_store_id
            and binding.timeline_root.timeline_store_id == self.timeline_store_id
        )

    def _is_intrinsically_valid(self) -> bool:
        basis = {
            "entry_contract_sha256": self.entry_contract_sha256,
            "host_root_id": self.host_root_id,
            "host_control_store_id": self.host_control_store_id,
            "binding_id": self.binding_id,
            "binding_revision": self.binding_revision,
            "binding_epoch": self.binding_epoch,
            "profile_id": self.profile_id,
            "timeline_id": self.timeline_id,
            "qualification_id": self.qualification_id,
            "qri_integrity_digest": self.qri_integrity_digest,
            "timeline_root_id": self.timeline_root_id,
            "timeline_control_store_id": self.timeline_control_store_id,
            "timeline_store_id": self.timeline_store_id,
            "preparation_record_sha256": self.preparation_record_sha256,
            "cognition_plan_digest": self.cognition_plan_digest,
        }
        expected_digest = sha256(
            json.dumps(basis, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()
        return (
            self.plan_digest == expected_digest
            and self.authorization_id
            == str(uuid5(NAMESPACE_URL, f"post-m0-08-local-serving:{expected_digest}"))
        )


@dataclass(frozen=True)
class _LocalFirstPhase1ExecutionTrace:
    plan_id: str
    process_graph_id: str
    provider_authority: str
    execution_mode: str
    runner_status: str
    os_network_deny_status: str
    process_launch_count: int
    network_attempt_count: int
    credential_read_count: int
    fallback_count: int


@dataclass(frozen=True)
class _CognitionAssemblySlot:
    qualification_id: str
    qri_integrity_digest: str
    provider_authority: str
    cognition: CognitionEngine

    @classmethod
    def _from_qri(
        cls,
        qri: QualifiedRuntimeInput,
        cognition: CognitionEngine,
    ) -> _CognitionAssemblySlot:
        if type(qri) is not QualifiedRuntimeInput:
            raise RuntimeHostRejected(
                "cognition-assembly-mismatch",
                "assembly slots require a SubjectStudio-published QRI",
            )
        if (
            not _qri_provider_contract_matches(qri)
            or not _cognition_contract_supported(cognition)
            or cognition.provider_authority != qri.provider_authority
        ):
            raise RuntimeHostRejected(
                "cognition-assembly-mismatch",
                "QRI and cognition do not form one exact supported slot",
            )
        return cls(
            qualification_id=qri.qualification_id,
            qri_integrity_digest=qri.integrity_digest,
            provider_authority=qri.provider_authority,
            cognition=cognition,
        )


class _CognitionAssembly:
    """Host-private exact QRI-to-Cognition selection boundary."""

    def __init__(
        self,
        *,
        single_cognition: CognitionEngine | None = None,
        slots: tuple[_CognitionAssemblySlot, ...] = (),
        submission_authorization: _LocalFirstSubmissionAuthorization | None = None,
        phase1_command: SubjectCommand | None = None,
        phase1_idempotency_key: str | None = None,
        phase1_confirmed_brief: str | None = None,
        _authority: object,
    ) -> None:
        if _authority is not _COGNITION_ASSEMBLY_TOKEN:
            raise TypeError("CognitionAssembly requires RuntimeHost authority")
        if (single_cognition is None) == (not slots):
            raise TypeError("CognitionAssembly requires either one adapter or slots")
        if (single_cognition is None) != (
            type(submission_authorization) is _LocalFirstSubmissionAuthorization
        ):
            raise TypeError(
                "transition assembly requires one exact submission authorization"
            )
        if single_cognition is None:
            if (
                type(phase1_command) is not SubjectCommand
                or not isinstance(phase1_idempotency_key, str)
                or not isinstance(phase1_confirmed_brief, str)
            ):
                raise TypeError("transition assembly requires its frozen Phase-1 plan")
        elif any(
            value is not None
            for value in (
                phase1_command,
                phase1_idempotency_key,
                phase1_confirmed_brief,
            )
        ):
            raise TypeError("single cognition cannot carry a local interaction plan")
        if single_cognition is not None and not _cognition_contract_supported(
            single_cognition
        ):
            raise TypeError("CognitionAssembly single adapter is unsupported")
        identities = {
            (
                slot.qualification_id,
                slot.qri_integrity_digest,
                slot.provider_authority,
            )
            for slot in slots
        }
        if slots and (len(slots) != len(identities) or len(slots) < 2):
            raise RuntimeHostRejected(
                "cognition-assembly-mismatch",
                "transition assembly slots must have unique exact identities",
            )
        self._single_cognition = single_cognition
        self._slots = slots
        self._submission_authorization = submission_authorization
        self._phase1_command = phase1_command
        self._phase1_idempotency_key = phase1_idempotency_key
        self._phase1_confirmed_brief = phase1_confirmed_brief
        self._phase1_trace = (
            None
            if submission_authorization is None
            else _LocalFirstPhase1ExecutionTrace(
                plan_id=submission_authorization.authorization_id,
                process_graph_id=str(
                    uuid5(
                        NAMESPACE_URL,
                        "post-m0-04-no-process-graph:"
                        f"{submission_authorization.plan_digest}",
                    )
                ),
                provider_authority=(
                    _LOCAL_LLAMA_PROVIDER_AUTHORITY
                    if submission_authorization.provider_authority
                    == _LOCAL_LLAMA_PROVIDER_AUTHORITY
                    else _LOCAL_FIRST_TEST_PROVIDER_AUTHORITY
                ),
                execution_mode=(
                    "exact-qualified-local-llama-runner"
                    if submission_authorization.provider_authority
                    == _LOCAL_LLAMA_PROVIDER_AUTHORITY
                    else "in-process-deterministic-test-double"
                ),
                runner_status=(
                    "qualified-b10331-cuda13.3-not-executed-in-assembly"
                    if submission_authorization.provider_authority
                    == _LOCAL_LLAMA_PROVIDER_AUTHORITY
                    else "not-selected-phase1"
                ),
                os_network_deny_status=(
                    "phase4-execution-gate-not-installed"
                    if submission_authorization.provider_authority
                    == _LOCAL_LLAMA_PROVIDER_AUTHORITY
                    else "not-qualified-no-process-launched"
                ),
                process_launch_count=0,
                network_attempt_count=0,
                credential_read_count=0,
                fallback_count=0,
            )
        )

    @classmethod
    def _single(cls, cognition: CognitionEngine) -> _CognitionAssembly:
        return cls(
            single_cognition=cognition,
            _authority=_COGNITION_ASSEMBLY_TOKEN,
        )

    @classmethod
    def _prepared_control_only(cls) -> _CognitionAssembly:
        """Create a non-serving placeholder after governance-only cold recovery."""

        instance = object.__new__(cls)
        instance._single_cognition = None
        instance._slots = ()
        instance._submission_authorization = None
        instance._phase1_command = None
        instance._phase1_idempotency_key = None
        instance._phase1_confirmed_brief = None
        instance._phase1_trace = None
        return instance

    @classmethod
    def _post_m0_04_test_transition(
        cls,
        predecessor: QualifiedRuntimeInput,
        successor: QualifiedRuntimeInput,
        *,
        _authority: object,
    ) -> _CognitionAssembly:
        if _authority is not _LOCAL_FIRST_TEST_COGNITION_TOKEN:
            raise TypeError("local transition assembly requires private authority")
        if (
            type(predecessor) is not QualifiedRuntimeInput
            or type(successor) is not QualifiedRuntimeInput
            or predecessor.capabilities
            != CapabilityManifest.accepted_artifact_dormant()
            or predecessor.provider_authority
            != _DORMANT_ARTIFACT_PROVIDER_AUTHORITY
            or successor.capabilities
            != CapabilityManifest._local_first_test_double()
            or successor.provider_authority
            != _LOCAL_FIRST_TEST_PROVIDER_AUTHORITY
            or successor.predecessor_qualification_id
            != predecessor.qualification_id
            or successor.qualification_revision
            != predecessor.qualification_revision + 1
            or successor.profile_id != predecessor.profile_id
            or successor.genesis_branch_id != predecessor.genesis_branch_id
            or successor.genesis_snapshot_id != predecessor.genesis_snapshot_id
            or successor.knowledge_snapshot_id != predecessor.knowledge_snapshot_id
            or successor.isolation_proof != predecessor.isolation_proof
        ):
            raise RuntimeHostRejected(
                "cognition-assembly-mismatch",
                "local transition is not the exact dormant successor lineage",
            )
        command, idempotency_key, confirmed_context_brief = (
            _local_first_phase1_test_interaction(
                predecessor_qualification_id=predecessor.qualification_id,
                profile_id=successor.profile_id,
                successor_publication_key=successor.publication_key,
            )
        )
        confirmed_brief = _UserConfirmedContextBrief._confirmed_for_test(
            confirmed_context_brief,
            _authority=_LOCAL_FIRST_TEST_COGNITION_TOKEN,
        )
        authorization = _LocalFirstSubmissionAuthorization._issue(
            qri=successor,
            command=command,
            idempotency_key=idempotency_key,
            confirmed_brief=confirmed_brief,
            _authority=_COGNITION_ASSEMBLY_TOKEN,
        )
        if len(successor.policy_decision_ids) != 1 or (
            successor.compatibility_proof
            != _local_first_successor_compatibility_digest(
                predecessor_qualification_id=predecessor.qualification_id,
                predecessor_integrity_digest=predecessor.integrity_digest,
                predecessor_compatibility_proof=predecessor.compatibility_proof,
                policy_decision_id=successor.policy_decision_ids[0],
                capability_manifest=successor.capabilities,
                provider_authority=successor.provider_authority,
                interaction_basis_digest=authorization.interaction_basis_digest,
            )
        ):
            raise RuntimeHostRejected(
                "local-interaction-plan-mismatch",
                "successor QRI does not bind this command, key, timeline, and brief",
            )
        dormant = _DormantArtifactCognition()
        local = _DeterministicLocalCognitionDouble._for_host_assembly(
            confirmed_brief=confirmed_brief,
            expected_command_fingerprint=authorization.command_fingerprint,
            _authority=_LOCAL_FIRST_TEST_COGNITION_TOKEN,
        )
        return cls(
            slots=(
                _CognitionAssemblySlot._from_qri(predecessor, dormant),
                _CognitionAssemblySlot._from_qri(successor, local),
            ),
            submission_authorization=authorization,
            phase1_command=command,
            phase1_idempotency_key=idempotency_key,
            phase1_confirmed_brief=confirmed_context_brief,
            _authority=_COGNITION_ASSEMBLY_TOKEN,
        )

    @classmethod
    def _post_m0_04_local_transition(
        cls,
        predecessor: QualifiedRuntimeInput,
        successor: QualifiedRuntimeInput,
        *,
        transport: _LocalLlamaTransport,
        corrective_timeline_id: str | None = None,
        _authority: object,
    ) -> _CognitionAssembly:
        if _authority is not _LOCAL_LLAMA_COGNITION_TOKEN:
            raise TypeError("local-llama transition assembly requires private authority")
        if (
            type(predecessor) is not QualifiedRuntimeInput
            or type(successor) is not QualifiedRuntimeInput
            or predecessor.capabilities
            != CapabilityManifest.accepted_artifact_dormant()
            or predecessor.provider_authority
            != _DORMANT_ARTIFACT_PROVIDER_AUTHORITY
            or successor.capabilities
            != CapabilityManifest._local_llama_experimental()
            or successor.provider_authority
            != _LOCAL_LLAMA_PROVIDER_AUTHORITY
            or successor.predecessor_qualification_id
            != predecessor.qualification_id
            or successor.qualification_revision
            != predecessor.qualification_revision
            + (2 if corrective_timeline_id is not None else 1)
            or successor.profile_id != predecessor.profile_id
            or successor.genesis_branch_id != predecessor.genesis_branch_id
            or successor.genesis_snapshot_id != predecessor.genesis_snapshot_id
            or successor.knowledge_snapshot_id != predecessor.knowledge_snapshot_id
            or successor.isolation_proof != predecessor.isolation_proof
        ):
            raise RuntimeHostRejected(
                "cognition-assembly-mismatch",
                "local-llama transition is not the exact qualified successor lineage",
            )
        command, idempotency_key, confirmed_context_brief = (
            _local_first_phase3_local_interaction(
                predecessor_qualification_id=predecessor.qualification_id,
                profile_id=successor.profile_id,
                successor_publication_key=successor.publication_key,
                _corrective_timeline_id=corrective_timeline_id,
            )
        )
        confirmed_brief = _UserConfirmedContextBrief._confirmed_for_local(
            confirmed_context_brief,
            _authority=_LOCAL_LLAMA_COGNITION_TOKEN,
        )
        authorization = _LocalFirstSubmissionAuthorization._issue(
            qri=successor,
            command=command,
            idempotency_key=idempotency_key,
            confirmed_brief=confirmed_brief,
            _authority=_COGNITION_ASSEMBLY_TOKEN,
        )
        if len(successor.policy_decision_ids) != 1 or (
            successor.compatibility_proof
            != _local_first_successor_compatibility_digest(
                predecessor_qualification_id=predecessor.qualification_id,
                predecessor_integrity_digest=predecessor.integrity_digest,
                predecessor_compatibility_proof=predecessor.compatibility_proof,
                policy_decision_id=successor.policy_decision_ids[0],
                capability_manifest=successor.capabilities,
                provider_authority=successor.provider_authority,
                interaction_basis_digest=authorization.interaction_basis_digest,
            )
        ):
            raise RuntimeHostRejected(
                "local-interaction-plan-mismatch",
                "successor QRI does not bind this command, key, timeline, and brief",
            )
        dormant = _DormantArtifactCognition()
        local = LocalLlamaCognition._for_host_assembly(
            confirmed_brief=confirmed_brief,
            expected_command_fingerprint=authorization.command_fingerprint,
            transport=transport,
            _authority=_LOCAL_LLAMA_COGNITION_TOKEN,
        )
        return cls(
            slots=(
                _CognitionAssemblySlot._from_qri(predecessor, dormant),
                _CognitionAssemblySlot._from_qri(successor, local),
            ),
            submission_authorization=authorization,
            phase1_command=command,
            phase1_idempotency_key=idempotency_key,
            phase1_confirmed_brief=confirmed_context_brief,
            _authority=_COGNITION_ASSEMBLY_TOKEN,
        )

    def accepts_bootstrap(self, cognition: CognitionEngine) -> bool:
        if not _cognition_contract_supported(cognition):
            return False
        if self._single_cognition is not None:
            return type(cognition) is type(self._single_cognition) and (
                cognition.provider_authority
                == self._single_cognition.provider_authority
            )
        return any(
            type(cognition) is type(slot.cognition)
            and cognition.provider_authority == slot.provider_authority
            for slot in self._slots
        )

    def single_provider_mismatch(self, qri: QualifiedRuntimeInput) -> bool:
        return self._single_cognition is not None and (
            self._single_cognition.provider_authority != qri.provider_authority
        )

    def submission_authorization(
        self,
        qri: QualifiedRuntimeInput,
        binding: RuntimeAuthorityBinding,
    ) -> _LocalFirstSubmissionAuthorization | None:
        authorization = self._submission_authorization
        if authorization is None:
            return None
        if (
            qri.qualification_id != authorization.qualification_id
            or qri.integrity_digest != authorization.qri_integrity_digest
            or binding.qualification_id != authorization.qualification_id
            or binding.qri_integrity_digest != authorization.qri_integrity_digest
            or binding.profile_id != authorization.profile_id
            or binding.timeline_id != authorization.timeline_id
        ):
            return None
        return authorization

    def phase1_execution_trace(self) -> _LocalFirstPhase1ExecutionTrace | None:
        return self._phase1_trace

    def phase1_submission_plan(
        self,
    ) -> tuple[SubjectCommand, str, str] | None:
        if self._phase1_command is None:
            return None
        assert self._phase1_idempotency_key is not None
        assert self._phase1_confirmed_brief is not None
        return (
            self._phase1_command,
            self._phase1_idempotency_key,
            self._phase1_confirmed_brief,
        )

    def _local_serving_plan_digest(
        self,
        qri: QualifiedRuntimeInput,
        binding: RuntimeAuthorityBinding,
    ) -> str:
        authorization = self.submission_authorization(qri, binding)
        cognition = self.select(qri)
        if authorization is None or type(cognition) is not LocalLlamaCognition:
            raise RuntimeHostRejected(
                "cognition-assembly-mismatch",
                "local serving requires one exact local llama assembly plan",
            )
        slots = [
            {
                "qualification_id": slot.qualification_id,
                "qri_integrity_digest": slot.qri_integrity_digest,
                "provider_authority": slot.provider_authority,
                "cognition_type": (
                    f"{type(slot.cognition).__module__}."
                    f"{type(slot.cognition).__qualname__}"
                ),
                "adapter_version": getattr(slot.cognition, "adapter_version", None),
            }
            for slot in self._slots
        ]
        basis = {
            "binding_id": binding.binding_id,
            "qualification_id": qri.qualification_id,
            "qri_integrity_digest": qri.integrity_digest,
            "submission_plan_digest": authorization.plan_digest,
            "cognition_plan_digest": cognition._serving_plan_digest(),
            "slots": slots,
        }
        return sha256(
            json.dumps(basis, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()

    def _preflight_local_serving_plan(
        self,
        qri: QualifiedRuntimeInput,
        binding: RuntimeAuthorityBinding,
    ) -> None:
        if self.submission_authorization(qri, binding) is None:
            raise RuntimeHostRejected(
                "cognition-assembly-mismatch",
                "local serving preflight requires its exact submission plan",
            )
        cognition = self.select(qri)
        if type(cognition) is not LocalLlamaCognition:
            raise RuntimeHostRejected(
                "cognition-assembly-mismatch",
                "local serving preflight requires the local llama adapter",
            )
        cognition._preflight_serving_plan()

    def select(self, qri: QualifiedRuntimeInput) -> CognitionEngine:
        if type(qri) is not QualifiedRuntimeInput or not _qri_provider_contract_matches(
            qri
        ):
            raise RuntimeHostRejected(
                "cognition-assembly-mismatch",
                "assembly selection requires an exact supported canonical QRI",
            )
        if self._single_cognition is not None:
            cognition = self._single_cognition
            if cognition.provider_authority == qri.provider_authority:
                return cognition
            raise RuntimeHostRejected(
                "cognition-assembly-mismatch",
                "single cognition does not match the canonical QRI",
            )
        matches = tuple(
            slot
            for slot in self._slots
            if (
                slot.qualification_id == qri.qualification_id
                and slot.qri_integrity_digest == qri.integrity_digest
                and slot.provider_authority == qri.provider_authority
            )
        )
        if len(matches) != 1:
            raise RuntimeHostRejected(
                "cognition-assembly-mismatch",
                "canonical QRI does not select exactly one cognition slot",
            )
        cognition = matches[0].cognition
        if (
            not _cognition_contract_supported(cognition)
            or cognition.provider_authority != qri.provider_authority
        ):
            raise RuntimeHostRejected(
                "cognition-assembly-mismatch",
                "selected cognition no longer matches its QRI slot",
            )
        if type(cognition) is _DeterministicLocalCognitionDouble:
            authorization = self._submission_authorization
            if authorization is None or not cognition._matches_phase1_plan(
                command_fingerprint=authorization.command_fingerprint,
                confirmed_brief_digest=authorization.confirmed_brief_digest,
            ):
                raise RuntimeHostRejected(
                    "local-interaction-plan-mismatch",
                    "local cognition no longer matches the QRI-bound Phase-1 plan",
                )
        if type(cognition) is LocalLlamaCognition:
            authorization = self._submission_authorization
            if authorization is None or not cognition._matches_phase1_plan(
                command_fingerprint=authorization.command_fingerprint,
                confirmed_brief_digest=authorization.confirmed_brief_digest,
            ):
                raise RuntimeHostRejected(
                    "local-interaction-plan-mismatch",
                    "local cognition no longer matches the QRI-bound Phase-1 plan",
                )
        return cognition


def _post_m0_04_test_cognition_assembly(
    predecessor: QualifiedRuntimeInput,
    successor: QualifiedRuntimeInput,
) -> _CognitionAssembly:
    """Build the Phase-1 transition assembly without accepting adapter input."""

    return _CognitionAssembly._post_m0_04_test_transition(
        predecessor,
        successor,
        _authority=_LOCAL_FIRST_TEST_COGNITION_TOKEN,
    )


def _post_m0_04_local_cognition_assembly(
    predecessor: QualifiedRuntimeInput,
    successor: QualifiedRuntimeInput,
) -> _CognitionAssembly:
    """Build the production local-llama transition assembly.

    The assembly binds the exact qualified runner transport; it launches no
    process here.  Execution requires the separate Phase-4 OS-level gate.
    """

    return _CognitionAssembly._post_m0_04_local_transition(
        predecessor,
        successor,
        transport=_LocalLlamaProcessTransport(
            _authority=_LOCAL_LLAMA_COGNITION_TOKEN,
        ),
        _authority=_LOCAL_LLAMA_COGNITION_TOKEN,
    )


def _post_m0_04_local_cognition_assembly_test(
    predecessor: QualifiedRuntimeInput,
    successor: QualifiedRuntimeInput,
    *,
    transport: _LocalLlamaTransport,
) -> _CognitionAssembly:
    """Build the production local-llama assembly with an injected transport.

    This deep TDD seam exists so temporary-root tests can exercise the full
    assembly without launching a model process.  It never runs in production
    composition.
    """

    return _CognitionAssembly._post_m0_04_local_transition(
        predecessor,
        successor,
        transport=transport,
        _authority=_LOCAL_LLAMA_COGNITION_TOKEN,
    )


def _post_m0_08_corrective_local_cognition_assembly_test(
    predecessor: QualifiedRuntimeInput,
    successor: QualifiedRuntimeInput,
    *,
    timeline_id: str,
    transport: _LocalLlamaTransport,
) -> _CognitionAssembly:
    """Build the Post-M0 08 corrective test assembly for one temporary root."""

    return _CognitionAssembly._post_m0_04_local_transition(
        predecessor,
        successor,
        transport=transport,
        corrective_timeline_id=timeline_id,
        _authority=_LOCAL_LLAMA_COGNITION_TOKEN,
    )


@dataclass(frozen=True)
class RuntimeHostRootRef:
    root_path: str
    root_id: str
    control_store_id: str
    root_kind: str = HOST_ROOT_KIND

    def __post_init__(self) -> None:
        if not Path(self.root_path).is_absolute():
            raise RuntimeHostRejected(
                "host-root-not-allowed",
                "RuntimeHost root reference must be absolute",
            )
        object.__setattr__(self, "root_id", _canonical_uuid(self.root_id, "root_id"))
        object.__setattr__(
            self,
            "control_store_id",
            _canonical_uuid(self.control_store_id, "control_store_id"),
        )
        if self.root_kind not in _HOST_ROOT_KINDS:
            raise RuntimeHostRejected(
                "host-root-kind-not-allowed",
                "RuntimeHost root kind must be test-fixture or experimental",
            )

    @property
    def root(self) -> Path:
        return Path(self.root_path)

    @property
    def control_database(self) -> Path:
        return self.root / "control" / "host.sqlite3"

    def to_dict(self) -> dict[str, str]:
        return {
            "root_path": self.root_path,
            "root_id": self.root_id,
            "control_store_id": self.control_store_id,
            "root_kind": self.root_kind,
        }

    @classmethod
    def from_dict(cls, source: Mapping[str, Any]) -> RuntimeHostRootRef:
        return cls(
            root_path=str(source.get("root_path", "")),
            root_id=str(source.get("root_id", "")),
            control_store_id=str(source.get("control_store_id", "")),
            root_kind=str(source.get("root_kind", HOST_ROOT_KIND)),
        )


@dataclass(frozen=True)
class _RuntimeActivationPlan:
    """Private exact identities for one digest-bound experimental activation."""

    provider_authority: str
    profile_id: str
    qualification_id: str
    qri_publication_key: str
    timeline_id: str
    host_root_id: str
    host_control_store_id: str
    binding_id: str
    authority_scope_id: str
    timeline_identity: _ReservedTimelineIdentity

    def __post_init__(self) -> None:
        for field in (
            "profile_id",
            "qualification_id",
            "timeline_id",
            "host_root_id",
            "host_control_store_id",
            "binding_id",
            "authority_scope_id",
        ):
            object.__setattr__(self, field, _canonical_uuid(getattr(self, field), field))
        if self.provider_authority != _DEEPSEEK_PROVIDER_AUTHORITY:
            raise RuntimeHostRejected(
                "activation-provider-mismatch",
                "reserved activation is limited to the confirmed DeepSeek authority",
            )
        if not isinstance(self.timeline_identity, _ReservedTimelineIdentity):
            raise TypeError("timeline_identity must be a reserved Timeline identity")


@dataclass(frozen=True)
class _DormantArtifactActivationPlan:
    """Private exact identities for one temporary dormant artifact activation."""

    provider_authority: str
    profile_id: str
    qualification_id: str
    qri_publication_key: str
    timeline_id: str
    host_root_id: str
    host_control_store_id: str
    binding_id: str
    authority_scope_id: str
    timeline_identity: _ReservedTimelineIdentity

    def __post_init__(self) -> None:
        for field in (
            "profile_id",
            "qualification_id",
            "timeline_id",
            "host_root_id",
            "host_control_store_id",
            "binding_id",
            "authority_scope_id",
        ):
            object.__setattr__(self, field, _canonical_uuid(getattr(self, field), field))
        if self.provider_authority != _DORMANT_ARTIFACT_PROVIDER_AUTHORITY:
            raise RuntimeHostRejected(
                "activation-provider-mismatch",
                "dormant artifact activation requires the no-cognition authority",
            )
        if not isinstance(self.timeline_identity, _ReservedTimelineIdentity):
            raise TypeError("timeline_identity must be a reserved Timeline identity")


@dataclass(frozen=True)
class _DormantArtifactExperimentalActivationPlan:
    """Private exact identities for one confirmed local dormant artifact activation."""

    provider_authority: str
    profile_id: str
    qualification_id: str
    qri_publication_key: str
    timeline_id: str
    host_root_id: str
    host_control_store_id: str
    binding_id: str
    authority_scope_id: str
    timeline_identity: _ReservedTimelineIdentity

    def __post_init__(self) -> None:
        for field in (
            "profile_id",
            "qualification_id",
            "timeline_id",
            "host_root_id",
            "host_control_store_id",
            "binding_id",
            "authority_scope_id",
        ):
            object.__setattr__(self, field, _canonical_uuid(getattr(self, field), field))
        if self.provider_authority != _DORMANT_ARTIFACT_PROVIDER_AUTHORITY:
            raise RuntimeHostRejected(
                "activation-provider-mismatch",
                "experimental dormant artifact activation requires no cognition",
            )
        if not isinstance(self.timeline_identity, _ReservedTimelineIdentity):
            raise TypeError("timeline_identity must be a reserved Timeline identity")


_HostActivationPlan = (
    _RuntimeActivationPlan
    | _DormantArtifactActivationPlan
    | _DormantArtifactExperimentalActivationPlan
)


@dataclass(frozen=True)
class RuntimeAuthorityBinding:
    binding_id: str
    binding_revision: int
    binding_epoch: int
    state: BindingState
    profile_id: str
    timeline_id: str
    authority_scope_id: str
    qualification_id: str
    qualification_revision: int
    qri_publication_key: str
    qri_integrity_digest: str
    genesis_snapshot_id: str
    knowledge_snapshot_id: str
    policy_decision_ids: tuple[str, ...]
    capability_manifest_version: str
    provider_authority: str
    runtime_kind: str
    runtime_contract_version: str
    studio_root_id: str
    studio_store_id: str
    host_root_id: str
    host_control_store_id: str
    timeline_root: CanonicalRootRef
    predecessor_binding_id: str | None
    first_subject_event_sealed: bool
    created_at_us: int
    activated_at_us: int | None
    retired_at_us: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "binding_revision": self.binding_revision,
            "binding_epoch": self.binding_epoch,
            "state": self.state.value,
            "profile_id": self.profile_id,
            "timeline_id": self.timeline_id,
            "authority_scope_id": self.authority_scope_id,
            "qualification_id": self.qualification_id,
            "qualification_revision": self.qualification_revision,
            "qri_publication_key": self.qri_publication_key,
            "qri_integrity_digest": self.qri_integrity_digest,
            "genesis_snapshot_id": self.genesis_snapshot_id,
            "knowledge_snapshot_id": self.knowledge_snapshot_id,
            "policy_decision_ids": list(self.policy_decision_ids),
            "capability_manifest_version": self.capability_manifest_version,
            "provider_authority": self.provider_authority,
            "runtime_kind": self.runtime_kind,
            "runtime_contract_version": self.runtime_contract_version,
            "studio_root_id": self.studio_root_id,
            "studio_store_id": self.studio_store_id,
            "host_root_id": self.host_root_id,
            "host_control_store_id": self.host_control_store_id,
            "timeline_root": self.timeline_root.to_dict(),
            "predecessor_binding_id": self.predecessor_binding_id,
            "first_subject_event_sealed": self.first_subject_event_sealed,
            "created_at_us": self.created_at_us,
            "activated_at_us": self.activated_at_us,
            "retired_at_us": self.retired_at_us,
        }

    @classmethod
    def from_dict(cls, source: Mapping[str, Any]) -> RuntimeAuthorityBinding:
        if not isinstance(source, Mapping):
            raise RuntimeHostFailedClosed(
                "binding-record-corrupt",
                "RuntimeAuthorityBinding requires a mapping",
            )
        try:
            timeline_root = CanonicalRootRef.from_dict(source["timeline_root"])
            return cls(
                binding_id=_canonical_uuid(str(source["binding_id"]), "binding_id"),
                binding_revision=int(source["binding_revision"]),
                binding_epoch=int(source["binding_epoch"]),
                state=BindingState(str(source["state"])),
                profile_id=_canonical_uuid(str(source["profile_id"]), "profile_id"),
                timeline_id=_canonical_uuid(str(source["timeline_id"]), "timeline_id"),
                authority_scope_id=_canonical_uuid(
                    str(source["authority_scope_id"]), "authority_scope_id"
                ),
                qualification_id=_canonical_uuid(
                    str(source["qualification_id"]), "qualification_id"
                ),
                qualification_revision=int(source["qualification_revision"]),
                qri_publication_key=str(source["qri_publication_key"]),
                qri_integrity_digest=str(source["qri_integrity_digest"]),
                genesis_snapshot_id=_canonical_uuid(
                    str(source["genesis_snapshot_id"]), "genesis_snapshot_id"
                ),
                knowledge_snapshot_id=_canonical_uuid(
                    str(source["knowledge_snapshot_id"]), "knowledge_snapshot_id"
                ),
                policy_decision_ids=tuple(source["policy_decision_ids"]),
                capability_manifest_version=str(source["capability_manifest_version"]),
                provider_authority=str(source["provider_authority"]),
                runtime_kind=str(source["runtime_kind"]),
                runtime_contract_version=str(source["runtime_contract_version"]),
                studio_root_id=_canonical_uuid(
                    str(source["studio_root_id"]), "studio_root_id"
                ),
                studio_store_id=_canonical_uuid(
                    str(source["studio_store_id"]), "studio_store_id"
                ),
                host_root_id=_canonical_uuid(
                    str(source["host_root_id"]), "host_root_id"
                ),
                host_control_store_id=_canonical_uuid(
                    str(source["host_control_store_id"]), "host_control_store_id"
                ),
                timeline_root=timeline_root,
                predecessor_binding_id=(
                    None
                    if source["predecessor_binding_id"] is None
                    else _canonical_uuid(
                        str(source["predecessor_binding_id"]),
                        "predecessor_binding_id",
                    )
                ),
                first_subject_event_sealed=bool(source["first_subject_event_sealed"]),
                created_at_us=int(source["created_at_us"]),
                activated_at_us=(
                    None
                    if source["activated_at_us"] is None
                    else int(source["activated_at_us"])
                ),
                retired_at_us=(
                    None
                    if source["retired_at_us"] is None
                    else int(source["retired_at_us"])
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeHostFailedClosed(
                "binding-record-corrupt",
                "RuntimeAuthorityBinding record is unreadable",
            ) from error


@dataclass(frozen=True, init=False)
class _ForwardGovernanceInstallPlan:
    """Exact private plan for one pre-open v1 containment installation."""

    installation_id: str
    plan_digest: str
    source_result_sha256: str
    location: RuntimeHostRootRef
    studio_location: StudioRootRef
    database_sha256_items: tuple[tuple[str, str], ...]
    root_identity_sha256_items: tuple[tuple[str, str], ...]
    lease_rows: tuple[tuple[str, int, str, int, str, int], ...]
    predecessor: RuntimeAuthorityBinding
    successor: RuntimeAuthorityBinding
    case_id: str
    fact_id: str
    fact_digest: str

    @property
    def database_sha256(self) -> dict[str, str]:
        return dict(self.database_sha256_items)

    @property
    def root_identity_sha256(self) -> dict[str, str]:
        return dict(self.root_identity_sha256_items)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("forward governance plan is internally issued")

    @classmethod
    def _issue(
        cls,
        *,
        source_result_sha256: str,
        location: RuntimeHostRootRef,
        studio_location: StudioRootRef,
        database_sha256: Mapping[str, str],
        root_identity_sha256: Mapping[str, str],
        lease_rows: tuple[tuple[str, int, str, int, str, int], ...],
        predecessor: RuntimeAuthorityBinding,
        successor: RuntimeAuthorityBinding,
        _authority: object,
    ) -> _ForwardGovernanceInstallPlan:
        if _authority is not _FORWARD_GOVERNANCE_INSTALL_AUTHORITY:
            raise TypeError("forward governance plan requires private authority")
        if type(location) is not RuntimeHostRootRef:
            raise TypeError("forward governance plan requires RuntimeHostRootRef")
        if type(studio_location) is not StudioRootRef:
            raise TypeError("forward governance plan requires StudioRootRef")
        if type(predecessor) is not RuntimeAuthorityBinding or type(
            successor
        ) is not RuntimeAuthorityBinding:
            raise TypeError("forward governance plan requires exact bindings")
        expected_database_names = {
            "profile_database",
            "host_database",
            "predecessor_control_database",
            "predecessor_timeline_database",
            "successor_control_database",
            "successor_timeline_database",
        }
        database_items = tuple(
            sorted((str(name), str(digest)) for name, digest in database_sha256.items())
        )
        if {name for name, _digest in database_items} != expected_database_names or any(
            not _is_sha256(digest) for _name, digest in database_items
        ):
            raise RuntimeHostRejected(
                "forward-governance-plan-invalid",
                "forward governance plan requires six canonical database digests",
            )
        identity_items = tuple(
            sorted(
                (str(name), str(digest))
                for name, digest in root_identity_sha256.items()
            )
        )
        if {
            name for name, _digest in identity_items
        } != {
            "studio_root_identity",
            "host_root_identity",
            "predecessor_root_identity",
            "successor_root_identity",
        } or any(not _is_sha256(digest) for _name, digest in identity_items):
            raise RuntimeHostRejected(
                "forward-governance-plan-invalid",
                "forward governance plan requires four canonical root identities",
            )
        if source_result_sha256 != _POST_M0_05_PHASE2_RESULT_SHA256:
            raise RuntimeHostRejected(
                "forward-governance-plan-invalid",
                "source result must be the exact passed Phase-2 Result-04",
            )
        try:
            canonical_lease_rows = tuple(
                sorted(
                    (
                        _canonical_uuid(str(binding_id), "binding_id"),
                        int(owner_pid),
                        str(owner_instance_id),
                        int(generation),
                        str(lease_state),
                        int(updated_at_us),
                    )
                    for (
                        binding_id,
                        owner_pid,
                        owner_instance_id,
                        generation,
                        lease_state,
                        updated_at_us,
                    ) in lease_rows
                )
            )
        except (TypeError, ValueError) as error:
            raise RuntimeHostRejected(
                "forward-governance-plan-invalid",
                "forward governance plan has invalid lease rows",
            ) from error
        if (
            {row[0] for row in canonical_lease_rows}
            != {predecessor.binding_id, successor.binding_id}
            or len(canonical_lease_rows) != 2
            or any(
                row[1] < 1
                or not row[2]
                or row[3] < 1
                or row[4] not in {"active", "draining", "closed"}
                or row[5] < 1
                for row in canonical_lease_rows
            )
        ):
            raise RuntimeHostRejected(
                "forward-governance-plan-invalid",
                "forward governance plan requires exactly two canonical lease rows",
            )
        if (
            predecessor.profile_id != successor.profile_id
            or predecessor.timeline_id == successor.timeline_id
            or predecessor.predecessor_binding_id is not None
            or successor.predecessor_binding_id is not None
            or successor.qualification_revision
            != predecessor.qualification_revision + 1
            or successor.genesis_snapshot_id != predecessor.genesis_snapshot_id
            or successor.knowledge_snapshot_id != predecessor.knowledge_snapshot_id
            or predecessor.state is not BindingState.ACTIVE
            or successor.state is not BindingState.ACTIVE
            or predecessor.host_root_id != location.root_id
            or successor.host_root_id != location.root_id
            or predecessor.host_control_store_id != location.control_store_id
            or successor.host_control_store_id != location.control_store_id
            or predecessor.studio_root_id != studio_location.root_id
            or successor.studio_root_id != studio_location.root_id
            or predecessor.studio_store_id != studio_location.profile_store_id
            or successor.studio_store_id != studio_location.profile_store_id
        ):
            raise RuntimeHostRejected(
                "forward-governance-plan-invalid",
                "containment plan does not describe one crossed active Host lineage",
            )
        case_id = str(
            uuid5(
                NAMESPACE_URL,
                f"post-m0-05-branch-governance:{location.root_id}:"
                f"{predecessor.profile_id}",
            )
        )
        members = (
            _branch_governance_member(
                predecessor,
                classification=_BRANCH_NORMAL,
                serving_disposition=_BRANCH_HELD,
            ),
            _branch_governance_member(
                successor,
                classification=_BRANCH_NONCONFORMING,
                serving_disposition=_BRANCH_HELD,
            ),
        )
        fact_digest = _branch_governance_fact_digest(
            case_id=case_id,
            host_root_id=location.root_id,
            host_control_store_id=location.control_store_id,
            sequence=1,
            previous_fact_digest=None,
            members=members,
        )
        fact_id = str(
            uuid5(
                NAMESPACE_URL,
                f"post-m0-05-branch-fact:{case_id}:1:{fact_digest}",
            )
        )
        body = {
            "format": "post-m0-05-forward-governance-v1-to-v2-1",
            "source_result_sha256": source_result_sha256,
            "location": location.to_dict(),
            "studio_location": studio_location.to_dict(),
            "database_sha256": dict(database_items),
            "root_identity_sha256": dict(identity_items),
            "lease_rows": [list(row) for row in canonical_lease_rows],
            "predecessor_binding": predecessor.to_dict(),
            "predecessor_classification": _BRANCH_NORMAL,
            "predecessor_serving_disposition": _BRANCH_HELD,
            "successor_binding": successor.to_dict(),
            "successor_classification": _BRANCH_NONCONFORMING,
            "successor_serving_disposition": _BRANCH_HELD,
            "case_id": case_id,
            "fact_id": fact_id,
            "fact_digest": fact_digest,
            "target": "quarantine-both-held",
        }
        plan_digest = sha256(_canonical_json(body).encode("utf-8")).hexdigest()
        installation_id = str(
            uuid5(NAMESPACE_URL, f"post-m0-05-forward-install:{plan_digest}")
        )
        instance = object.__new__(cls)
        for field, value in {
            "installation_id": installation_id,
            "plan_digest": plan_digest,
            "source_result_sha256": source_result_sha256,
            "location": location,
            "studio_location": studio_location,
            "database_sha256_items": database_items,
            "root_identity_sha256_items": identity_items,
            "lease_rows": canonical_lease_rows,
            "predecessor": predecessor,
            "successor": successor,
            "case_id": case_id,
            "fact_id": fact_id,
            "fact_digest": fact_digest,
        }.items():
            object.__setattr__(instance, field, value)
        return instance


@dataclass(frozen=True)
class _ForwardGovernanceInstallReceipt:
    installation_id: str
    status: str
    fact_id: str
    fact_digest: str
    host_database_sha256_before: str
    host_database_sha256_after: str
    non_host_databases_unchanged: bool


@dataclass(frozen=True, init=False)
class _CorrectiveSuccessorPreparationPlan:
    preparation_id: str
    plan_digest: str
    location: RuntimeHostRootRef
    studio_location: StudioRootRef
    artifact_id: str
    predecessor_qualification_id: str
    nonconforming_qualification_id: str
    nonconforming_policy_decision_id: str
    nonconforming_policy_integrity_digest: str
    target_timeline_id: str
    policy_decision_id: str
    policy_decision: PolicyDecision
    publication_key: str
    published_at_us: int
    predecessor_root_sha256_items: tuple[tuple[str, str], ...]
    nonconforming_root_sha256_items: tuple[tuple[str, str], ...]
    authority_preimage_sha256_items: tuple[tuple[str, str], ...]

    @property
    def predecessor_root_sha256(self) -> dict[str, str]:
        return dict(self.predecessor_root_sha256_items)

    @property
    def nonconforming_root_sha256(self) -> dict[str, str]:
        return dict(self.nonconforming_root_sha256_items)

    @property
    def authority_preimage_sha256(self) -> dict[str, str]:
        return dict(self.authority_preimage_sha256_items)

    @property
    def prepared_timeline_root(self) -> CanonicalRootRef:
        """Exact Host-issued fault target for temporary-root maintenance tests."""

        return _corrective_timeline_root_for_plan(self)

    @property
    def body(self) -> dict[str, object]:
        return {
            "format": "post-m0-06-corrective-successor-preparation-1",
            "location": self.location.to_dict(),
            "studio_location": self.studio_location.to_dict(),
            "artifact_id": self.artifact_id,
            "predecessor_qualification_id": self.predecessor_qualification_id,
            "nonconforming_qualification_id": self.nonconforming_qualification_id,
            "nonconforming_policy_decision_id": self.nonconforming_policy_decision_id,
            "nonconforming_policy_integrity_digest": self.nonconforming_policy_integrity_digest,
            "target_timeline_id": self.target_timeline_id,
            "policy_decision_id": self.policy_decision_id,
            "policy_decision": self.policy_decision.to_dict(),
            "publication_key": self.publication_key,
            "published_at_us": self.published_at_us,
            "predecessor_root_sha256": self.predecessor_root_sha256,
            "nonconforming_root_sha256": self.nonconforming_root_sha256,
            "authority_preimage_sha256": self.authority_preimage_sha256,
        }

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("corrective successor plan is internally issued")

    @classmethod
    def _issue(
        cls,
        *,
        location: RuntimeHostRootRef,
        studio_location: StudioRootRef,
        artifact_id: str,
        predecessor_qualification_id: str,
        nonconforming_qualification_id: str,
        nonconforming_policy_decision_id: str,
        nonconforming_policy_integrity_digest: str,
        target_timeline_id: str,
        policy_decision_id: str,
        policy_decision: PolicyDecision,
        publication_key: str,
        published_at_us: int,
        predecessor_root_sha256: Mapping[str, str],
        nonconforming_root_sha256: Mapping[str, str],
        authority_preimage_sha256: Mapping[str, str],
        _authority: object,
    ) -> _CorrectiveSuccessorPreparationPlan:
        if _authority is not _CORRECTIVE_SUCCESSOR_PREPARATION_AUTHORITY:
            raise TypeError("corrective successor plan requires private authority")
        if type(location) is not RuntimeHostRootRef or type(
            studio_location
        ) is not StudioRootRef:
            raise TypeError("corrective successor plan requires exact roots")
        expected_root_hash_names = {
            "root_identity",
            "control_database",
            "timeline_database",
        }

        def canonical_root_hashes(
            source: Mapping[str, str],
            field: str,
        ) -> tuple[tuple[str, str], ...]:
            if not isinstance(source, Mapping):
                raise RuntimeHostRejected(
                    "corrective-successor-plan-invalid",
                    f"{field} must bind the three source-root files",
                )
            items = tuple(
                sorted((str(name), str(digest)) for name, digest in source.items())
            )
            if (
                {name for name, _digest in items} != expected_root_hash_names
                or any(not _is_sha256(digest) for _name, digest in items)
            ):
                raise RuntimeHostRejected(
                    "corrective-successor-plan-invalid",
                    f"{field} must contain three canonical SHA-256 values",
                )
            return items

        predecessor_hash_items = canonical_root_hashes(
            predecessor_root_sha256,
            "predecessor_root_sha256",
        )
        nonconforming_hash_items = canonical_root_hashes(
            nonconforming_root_sha256,
            "nonconforming_root_sha256",
        )
        authority_hash_names = {
            "studio_root_identity",
            "studio_profile_database",
            "host_root_identity",
            "host_control_database",
        }
        authority_hash_items = tuple(
            sorted(
                (str(name), str(digest))
                for name, digest in authority_preimage_sha256.items()
            )
        )
        if (
            {name for name, _digest in authority_hash_items}
            != authority_hash_names
            or any(not _is_sha256(digest) for _name, digest in authority_hash_items)
        ):
            raise RuntimeHostRejected(
                "corrective-successor-plan-invalid",
                "authority preimage must bind Studio and Host identity/database bytes",
            )
        if not isinstance(policy_decision, PolicyDecision):
            raise RuntimeHostRejected(
                "corrective-successor-plan-invalid",
                "corrective successor plan must bind the complete PolicyDecision",
            )
        if policy_decision.decision_id != _canonical_uuid(
            policy_decision_id, "policy_decision_id"
        ):
            raise RuntimeHostRejected(
                "corrective-successor-plan-invalid",
                "corrective PolicyDecision identity does not match the plan",
            )
        policy_integrity_basis = {
            "question_digest": policy_decision.question_digest,
            "policy_version": policy_decision.policy_version,
            "issued_at_us": policy_decision.issued_at_us,
            "valid_until_us": policy_decision.valid_until_us,
            "disposition": policy_decision.disposition.value,
            "reason_codes": list(policy_decision.reason_codes),
            "decision_id": policy_decision.decision_id,
            "capability_manifest": policy_decision.capability_manifest.to_dict(),
        }
        if sha256(_canonical_json(policy_integrity_basis).encode("utf-8")).hexdigest() != policy_decision.integrity_digest:
            raise RuntimeHostRejected(
                "corrective-successor-plan-invalid",
                "corrective PolicyDecision integrity does not match its projection",
            )
        body = {
            "format": "post-m0-06-corrective-successor-preparation-1",
            "location": location.to_dict(),
            "studio_location": studio_location.to_dict(),
            "artifact_id": _canonical_uuid(artifact_id, "artifact_id"),
            "predecessor_qualification_id": _canonical_uuid(
                predecessor_qualification_id, "predecessor_qualification_id"
            ),
            "nonconforming_qualification_id": _canonical_uuid(
                nonconforming_qualification_id, "nonconforming_qualification_id"
            ),
            "nonconforming_policy_decision_id": _canonical_uuid(
                nonconforming_policy_decision_id,
                "nonconforming_policy_decision_id",
            ),
            "nonconforming_policy_integrity_digest": str(
                nonconforming_policy_integrity_digest
            ),
            "target_timeline_id": _canonical_uuid(
                target_timeline_id, "target_timeline_id"
            ),
            "policy_decision_id": _canonical_uuid(
                policy_decision_id, "policy_decision_id"
            ),
            "policy_decision": policy_decision.to_dict(),
            "publication_key": str(publication_key),
            "published_at_us": int(published_at_us),
            "predecessor_root_sha256": dict(predecessor_hash_items),
            "nonconforming_root_sha256": dict(nonconforming_hash_items),
            "authority_preimage_sha256": dict(authority_hash_items),
        }
        if (
            body["predecessor_qualification_id"]
            == body["nonconforming_qualification_id"]
            or not isinstance(publication_key, str)
            or not publication_key
            or int(published_at_us) < 1
            or not _is_sha256(body["nonconforming_policy_integrity_digest"])
        ):
            raise RuntimeHostRejected(
                "corrective-successor-plan-invalid",
                "corrective successor plan contains invalid or duplicate identities",
            )
        plan_digest = sha256(_canonical_json(body).encode("utf-8")).hexdigest()
        preparation_id = str(
            uuid5(NAMESPACE_URL, f"post-m0-06-corrective:{plan_digest}")
        )
        instance = object.__new__(cls)
        for field, value in {
            "preparation_id": preparation_id,
            "plan_digest": plan_digest,
            "location": location,
            "studio_location": studio_location,
            "artifact_id": body["artifact_id"],
            "predecessor_qualification_id": body[
                "predecessor_qualification_id"
            ],
            "nonconforming_qualification_id": body[
                "nonconforming_qualification_id"
            ],
            "nonconforming_policy_decision_id": body[
                "nonconforming_policy_decision_id"
            ],
            "nonconforming_policy_integrity_digest": body[
                "nonconforming_policy_integrity_digest"
            ],
            "target_timeline_id": body["target_timeline_id"],
            "policy_decision_id": body["policy_decision_id"],
            "policy_decision": policy_decision,
            "publication_key": body["publication_key"],
            "published_at_us": body["published_at_us"],
            "predecessor_root_sha256_items": predecessor_hash_items,
            "nonconforming_root_sha256_items": nonconforming_hash_items,
            "authority_preimage_sha256_items": authority_hash_items,
        }.items():
            object.__setattr__(instance, field, value)
        return instance


def _policy_decision_from_payload(payload: object) -> PolicyDecision:
    if not isinstance(payload, Mapping):
        raise RuntimeHostFailedClosed(
            "corrective-successor-root-commitment-mismatch",
            "corrective PolicyDecision projection is absent",
        )
    try:
        return PolicyDecision._issue(
            decision_id=str(payload["decision_id"]),
            disposition=PolicyDisposition(str(payload["disposition"])),
            reason_codes=tuple(str(value) for value in payload["reason_codes"]),
            policy_version=str(payload["policy_version"]),
            question_digest=str(payload["question_digest"]),
            issued_at_us=int(payload["issued_at_us"]),
            valid_until_us=int(payload["valid_until_us"]),
            capability_manifest=CapabilityManifest.from_dict(
                payload["capability_manifest"]
            ),
            integrity_digest=str(payload["integrity_digest"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeHostFailedClosed(
            "corrective-successor-root-commitment-mismatch",
            "corrective PolicyDecision projection is invalid",
        ) from error


def _verify_corrective_successor_plan(
    plan: _CorrectiveSuccessorPreparationPlan,
) -> None:
    if type(plan) is not _CorrectiveSuccessorPreparationPlan:
        raise TypeError("corrective successor preparation requires a sealed plan")
    expected = _CorrectiveSuccessorPreparationPlan._issue(
        location=plan.location,
        studio_location=plan.studio_location,
        artifact_id=plan.artifact_id,
        predecessor_qualification_id=plan.predecessor_qualification_id,
        nonconforming_qualification_id=plan.nonconforming_qualification_id,
        nonconforming_policy_decision_id=plan.nonconforming_policy_decision_id,
        nonconforming_policy_integrity_digest=(
            plan.nonconforming_policy_integrity_digest
        ),
        target_timeline_id=plan.target_timeline_id,
        policy_decision_id=plan.policy_decision_id,
        policy_decision=plan.policy_decision,
        publication_key=plan.publication_key,
        published_at_us=plan.published_at_us,
        predecessor_root_sha256=plan.predecessor_root_sha256,
        nonconforming_root_sha256=plan.nonconforming_root_sha256,
        authority_preimage_sha256=plan.authority_preimage_sha256,
        _authority=_CORRECTIVE_SUCCESSOR_PREPARATION_AUTHORITY,
    )
    if plan != expected:
        raise RuntimeHostFailedClosed(
            "corrective-successor-plan-mismatch",
            "corrective successor plan differs from its canonical reissuance",
        )


@dataclass(frozen=True)
class _CorrectiveSuccessorPreparationReceipt:
    preparation_id: str
    plan_digest: str
    status: str
    binding_id: str
    qualification_id: str
    fact_id: str
    fact_digest: str
    predecessor_root_hashes_unchanged: bool
    nonconforming_root_hashes_unchanged: bool
    all_leases_closed: bool
    new_timeline_root: CanonicalRootRef


@dataclass(frozen=True, init=False)
class _CorrectiveSuccessorRecoveryPlan:
    """Host-owned sealed recovery route around one corrective write plan."""

    plan: _CorrectiveSuccessorPreparationPlan
    nce_policy_decision_id: str
    nce_policy_integrity_digest: str
    source_text_free_evidence_digest: str
    activation_commitment_digest: str
    recovery_basis_digest: str
    _write_projection_json: str

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("corrective successor recovery plan is internally issued")

    @property
    def write_projection(self) -> dict[str, object]:
        return dict(json.loads(self._write_projection_json))

    @classmethod
    def _issue(
        cls,
        *,
        plan: _CorrectiveSuccessorPreparationPlan,
        nce_policy: PolicyDecision,
        source_text_free_evidence: Mapping[str, object],
        activation_commitment: Mapping[str, object],
        write_projection: Mapping[str, object],
        _authority: object,
    ) -> _CorrectiveSuccessorRecoveryPlan:
        if _authority is not _CORRECTIVE_SUCCESSOR_PREPARATION_AUTHORITY:
            raise TypeError("corrective successor recovery plan requires private authority")
        _verify_corrective_successor_plan(plan)
        if not isinstance(nce_policy, PolicyDecision):
            raise TypeError("corrective successor recovery plan requires PolicyDecision")
        source_digest = sha256(
            _canonical_json(dict(source_text_free_evidence)).encode("utf-8")
        ).hexdigest()
        activation_digest = sha256(
            _canonical_json(dict(activation_commitment)).encode("utf-8")
        ).hexdigest()
        recovery_basis = {
            "format": "post-m0-06-corrective-successor-recovery-1",
            "plan_digest": plan.plan_digest,
            "nce_policy_decision_id": nce_policy.decision_id,
            "nce_policy_integrity_digest": nce_policy.integrity_digest,
            "source_text_free_evidence_digest": source_digest,
            "activation_commitment_digest": activation_digest,
            "fresh_authority_preimage_required": True,
            "recovery_only": True,
        }
        recovery_basis_digest = sha256(
            _canonical_json(recovery_basis).encode("utf-8")
        ).hexdigest()
        projection = json.loads(_canonical_json(dict(write_projection)))
        projection["recovery_basis"] = {
            **recovery_basis,
            "recovery_basis_digest": recovery_basis_digest,
        }
        instance = object.__new__(cls)
        for field, value in {
            "plan": plan,
            "nce_policy_decision_id": nce_policy.decision_id,
            "nce_policy_integrity_digest": nce_policy.integrity_digest,
            "source_text_free_evidence_digest": source_digest,
            "activation_commitment_digest": activation_digest,
            "recovery_basis_digest": recovery_basis_digest,
            "_write_projection_json": _canonical_json(projection),
        }.items():
            object.__setattr__(instance, field, value)
        return instance


def _verify_corrective_successor_recovery_plan(
    recovery_plan: _CorrectiveSuccessorRecoveryPlan,
) -> None:
    if type(recovery_plan) is not _CorrectiveSuccessorRecoveryPlan:
        raise TypeError("corrective successor recovery requires a sealed recovery plan")
    _verify_corrective_successor_plan(recovery_plan.plan)
    projection = recovery_plan.write_projection
    recovery_basis = projection.get("recovery_basis")
    expected_basis = {
        "format": "post-m0-06-corrective-successor-recovery-1",
        "plan_digest": recovery_plan.plan.plan_digest,
        "nce_policy_decision_id": recovery_plan.nce_policy_decision_id,
        "nce_policy_integrity_digest": recovery_plan.nce_policy_integrity_digest,
        "source_text_free_evidence_digest": (
            recovery_plan.source_text_free_evidence_digest
        ),
        "activation_commitment_digest": recovery_plan.activation_commitment_digest,
        "fresh_authority_preimage_required": True,
        "recovery_only": True,
    }
    expected_digest = sha256(
        _canonical_json(expected_basis).encode("utf-8")
    ).hexdigest()
    if recovery_basis != {
        **expected_basis,
        "recovery_basis_digest": expected_digest,
    } or recovery_plan.recovery_basis_digest != expected_digest:
        raise RuntimeHostFailedClosed(
            "corrective-successor-recovery-plan-mismatch",
            "corrective successor recovery basis differs from its seal",
        )
    if (
        projection.get("plan_digest") != recovery_plan.plan.plan_digest
        or projection.get("preparation_id")
        != recovery_plan.plan.preparation_id
        or projection.get("policy_decision")
        != recovery_plan.plan.policy_decision.to_dict()
        or recovery_plan.plan.nonconforming_policy_decision_id
        != recovery_plan.nce_policy_decision_id
        or recovery_plan.plan.nonconforming_policy_integrity_digest
        != recovery_plan.nce_policy_integrity_digest
    ):
        raise RuntimeHostFailedClosed(
            "corrective-successor-recovery-plan-mismatch",
            "corrective successor recovery projection differs from its plan",
        )


def _corrective_timeline_is_canonical_empty(
    timeline: sqlite3.Connection,
    basis: TimelineBasis,
) -> bool:
    cycle_tables = tuple(
        sorted(
            _TIMELINE_TABLES
            - {
                "store_manifest",
                "admission_gate",
                "timeline_head",
                "timeline_integrity",
            }
        )
    )
    empty_counts = all(
        int(
            timeline.execute(
                f'SELECT count(*) FROM "{table}"'
            ).fetchone()[0]
        )
        == 0
        for table in cycle_tables
    )
    return (
        empty_counts
        and basis.head_sequence == 0
        and basis.published_outcome_digest is None
        and basis.verified_prefix_digest == _EMPTY_VERIFIED_PREFIX_DIGEST
        and basis.revision_head_digest == _EMPTY_REVISION_HEAD_DIGEST
    )


def _corrective_timeline_is_canonical_one_cycle(
    timeline: sqlite3.Connection,
    basis: TimelineBasis,
    binding: RuntimeAuthorityBinding,
) -> bool:
    expected_counts = {
        table: 1
        for table in (
            _TIMELINE_TABLES
            - {
                "store_manifest",
                "admission_gate",
                "timeline_head",
                "timeline_integrity",
                "candidate_decision_record",
                "cycle_failure_transition",
                "operation_failure",
                "publication_conflict_fact",
            }
        )
    }
    expected_counts.update(
        {
            "candidate_decision_record": 6,
            "cycle_failure_transition": 0,
            "operation_failure": 0,
            "publication_conflict_fact": 0,
        }
    )
    if any(
        int(
            timeline.execute(
                f'SELECT count(*) FROM "{table}"'
            ).fetchone()[0]
        )
        != expected
        for table, expected in sorted(expected_counts.items())
    ):
        return False
    operation = timeline.execute(
        "SELECT operation_id, authority_scope_id, operation_state "
        "FROM subject_operation"
    ).fetchone()
    event = timeline.execute(
        "SELECT event_id, operation_id, event_kind FROM subject_event"
    ).fetchone()
    attempt = timeline.execute(
        "SELECT attempt_id, operation_id, attempt_ordinal, attempt_state "
        "FROM experience_attempt"
    ).fetchone()
    plan = timeline.execute(
        "SELECT plan_id, operation_id, attempt_id, subject_event_id, "
        "expected_head_sequence, expected_head_outcome_digest, "
        "expected_verified_prefix_digest, expected_revision_head_digest "
        "FROM commit_plan_identity_claim"
    ).fetchone()
    receipt = timeline.execute(
        "SELECT plan_id, operation_id, attempt_id, subject_event_id, "
        "profile_id, timeline_id, expected_head_sequence, "
        "expected_head_outcome_digest, expected_verified_prefix_digest, "
        "expected_revision_head_digest FROM cycle_commit_plan_receipt"
    ).fetchone()
    outcome = timeline.execute(
        "SELECT outcome_id, operation_id, attempt_id, subject_event_id, plan_id, "
        "head_sequence, previous_outcome_digest, outcome_digest "
        "FROM timeline_outcome"
    ).fetchone()
    if None in {operation, event, attempt, plan, receipt, outcome}:
        return False
    operation_id = bytes(operation[0])
    event_id = bytes(event[0])
    attempt_id = bytes(attempt[0])
    plan_id = bytes(plan[0])
    outcome_id = bytes(outcome[0])
    outcome_digest = bytes(outcome[7])
    empty_verified = bytes.fromhex(_EMPTY_VERIFIED_PREFIX_DIGEST)
    empty_revision = bytes.fromhex(_EMPTY_REVISION_HEAD_DIGEST)
    command = timeline.execute(
        "SELECT operation_id, target_profile_id, target_timeline_id "
        "FROM subject_command"
    ).fetchone()
    transition = timeline.execute(
        "SELECT operation_id, transition_ordinal, from_state, to_state "
        "FROM operation_transition"
    ).fetchone()
    cycle_basis = timeline.execute(
        "SELECT operation_id, attempt_id, head_sequence, "
        "published_outcome_digest, verified_prefix_digest, "
        "revision_head_digest FROM attempt_cycle_basis"
    ).fetchone()
    publication = timeline.execute(
        "SELECT plan_id, outcome_id, outcome_digest FROM publication_receipt"
    ).fetchone()
    operation_state = timeline.execute(
        "SELECT operation_id, attempt_id, operation_state, attempt_state, "
        "plan_id, outcome_id FROM operation_publication_state"
    ).fetchone()
    publication_transition = timeline.execute(
        "SELECT operation_id, transition_ordinal, from_state, to_state, plan_id "
        "FROM publication_transition"
    ).fetchone()
    effect = timeline.execute(
        "SELECT effect_count, reference_ids_json, dispatch_state "
        "FROM committed_effect_set"
    ).fetchone()
    revision = timeline.execute(
        "SELECT revision_count, revision_ids_json FROM revision_set"
    ).fetchone()
    agency = timeline.execute(
        "SELECT committed_effect_eligible FROM agency_domain_outcome"
    ).fetchone()
    try:
        verifier = TimelineEngine(
            binding.timeline_root,
            _RuntimeBindingAuthority(
                authority_scope_id=binding.authority_scope_id,
                profile_id=binding.profile_id,
                timeline_id=binding.timeline_id,
                allowed_intents=ALLOWED_INTENTS,
                allowed_provenance=ALLOWED_PROVENANCE,
                binding_id=binding.binding_id,
                binding_revision=binding.binding_revision,
                binding_epoch=binding.binding_epoch,
                qualification_id=binding.qualification_id,
                qualification_revision=binding.qualification_revision,
                provider_authority=binding.provider_authority,
            ),
            timeline,
            None,
        )
        admitted = verifier._admitted_for_operation(
            timeline,
            operation_id,
            replayed=True,
        )
        command_value = verifier._query_command(admitted.operation_ref)
        verifier._validate_authority(command_value)
        idempotency_claim = timeline.execute(
            "SELECT authority_scope_id, payload_fingerprint, operation_id "
            "FROM idempotency_claim"
        ).fetchone()
        canonical_outcome = verifier.query_outcome(admitted.operation_ref)
        canonical_outcome_verified = (
            idempotency_claim
            == (
                binding.authority_scope_id,
                bytes.fromhex(command_value.payload_fingerprint),
                operation_id,
            )
            and basis.verified_prefix_digest
            == canonical_outcome.epistemic_outcome.verified_prefix_digest
            and basis.revision_head_digest == bytes(receipt[9]).hex()
        )
    except Exception:
        canonical_outcome_verified = False
    return (
        canonical_outcome_verified
        and basis.head_sequence == 1
        and basis.published_outcome_digest == outcome_digest.hex()
        and str(operation[1]) == binding.authority_scope_id
        and str(operation[2]) == "admitted-pending"
        and command
        == (operation_id, binding.profile_id, binding.timeline_id)
        and event == (event_id, operation_id, "command-admitted")
        and attempt == (attempt_id, operation_id, 1, "pending")
        and transition == (operation_id, 1, None, "admitted-pending")
        and cycle_basis
        == (
            operation_id,
            attempt_id,
            0,
            None,
            empty_verified,
            empty_revision,
        )
        and plan[1:4] == (operation_id, attempt_id, event_id)
        and int(plan[4]) == 0
        and plan[5] is None
        and bytes(plan[6]) == empty_verified
        and bytes(plan[7]) == empty_revision
        and receipt[0:4] == (plan_id, operation_id, attempt_id, event_id)
        and receipt[4:6] == (binding.profile_id, binding.timeline_id)
        and int(receipt[6]) == 0
        and receipt[7] is None
        and bytes(receipt[8]) == empty_verified
        and bytes(receipt[9]) == empty_revision
        and outcome[1:5] == (operation_id, attempt_id, event_id, plan_id)
        and int(outcome[5]) == 1
        and outcome[6] is None
        and publication == (plan_id, outcome_id, outcome_digest)
        and operation_state
        == (
            operation_id,
            attempt_id,
            "completed",
            "published",
            plan_id,
            outcome_id,
        )
        and publication_transition
        == (operation_id, 2, "admitted-pending", "completed", plan_id)
        and effect == (0, "[]", "unavailable")
        and revision == (0, "[]")
        and agency == (0,)
    )


def _corrective_timeline_state(
    binding: RuntimeAuthorityBinding,
) -> tuple[str, int, TimelineBasis, bool, dict[str, str], bool, bool]:
    root = binding.timeline_root
    try:
        _validate_timeline_existing_root(
            root.root,
            root.root_id,
            root_kind=root.root_kind,
        )
        _read_timeline_root_identity(root.root, root.root_id, root.root_kind)
        _verify_forward_governance_regular_paths(
            (
                root.root / "root.identity",
                root.control_database,
                root.timeline_database,
            )
        )
        control = _connect_readonly(root.control_database)
        timeline = _connect_readonly(root.timeline_database)
        try:
            for connection in (control, timeline):
                _verify_timeline_connection_profile(connection)
            _verify_timeline_manifest(
                control,
                root_id=root.root_id,
                store_id=root.control_store_id,
                store_kind="control",
                schema_family=TIMELINE_CONTROL_SCHEMA_FAMILY,
            )
            _verify_timeline_store_integrity(
                control,
                expected_tables=_TIMELINE_CONTROL_TABLES,
            )
            registration = control.execute(
                "SELECT timeline_store_id, relative_database_path, "
                "registration_state FROM timeline_registration WHERE timeline_id = ?",
                (root.timeline_id,),
            ).fetchone()
            if registration != (
                root.timeline_store_id,
                f"timelines/{root.timeline_id}/timeline.sqlite3",
                "ready",
            ):
                raise RuntimeHostFailedClosed(
                    "corrective-successor-timeline-invalid",
                    "corrective Timeline registration differs from its binding",
                )
            _verify_timeline_manifest(
                timeline,
                root_id=root.root_id,
                store_id=root.timeline_store_id,
                store_kind="timeline",
                schema_family=TIMELINE_SCHEMA_FAMILY,
            )
            _verify_timeline_store_integrity(
                timeline,
                expected_tables=_TIMELINE_TABLES,
            )
            gate = _read_timeline_admission_gate(timeline)
            authority = gate.authority
            if not isinstance(authority, _RuntimeBindingAuthority) or authority != (
                _RuntimeBindingAuthority(
                    authority_scope_id=binding.authority_scope_id,
                    profile_id=binding.profile_id,
                    timeline_id=binding.timeline_id,
                    allowed_intents=ALLOWED_INTENTS,
                    allowed_provenance=ALLOWED_PROVENANCE,
                    binding_id=binding.binding_id,
                    binding_revision=binding.binding_revision,
                    binding_epoch=binding.binding_epoch,
                    qualification_id=binding.qualification_id,
                    qualification_revision=binding.qualification_revision,
                    provider_authority=binding.provider_authority,
                )
            ):
                raise RuntimeHostFailedClosed(
                    "corrective-successor-timeline-invalid",
                    "corrective Timeline gate authority differs from its binding",
                )
            basis = _read_timeline_basis(timeline)
            has_event = timeline.execute(
                "SELECT 1 FROM subject_event LIMIT 1"
            ).fetchone() is not None
            is_canonical_empty = _corrective_timeline_is_canonical_empty(
                timeline,
                basis,
            )
            is_canonical_one_cycle = (
                _corrective_timeline_is_canonical_one_cycle(
                    timeline,
                    basis,
                    binding,
                )
            )
        finally:
            timeline.close()
            control.close()
    except RuntimeHostProblem:
        raise
    except Exception as error:
        raise RuntimeHostFailedClosed(
            "corrective-successor-timeline-invalid",
            "corrective Timeline root could not be verified",
        ) from error
    return (
        gate.state,
        gate.gate_epoch,
        basis,
        has_event,
        {
            "root_identity": _file_sha256(root.root / "root.identity"),
            "control_database": _file_sha256(root.control_database),
            "timeline_database": _file_sha256(root.timeline_database),
        },
        is_canonical_empty,
        is_canonical_one_cycle,
    )


def _corrective_root_hashes(binding: RuntimeAuthorityBinding) -> dict[str, str]:
    root = binding.timeline_root
    return {
        "root_identity": _file_sha256(root.root / "root.identity"),
        "control_database": _file_sha256(root.control_database),
        "timeline_database": _file_sha256(root.timeline_database),
    }


def _corrective_binding_id(
    plan: _CorrectiveSuccessorPreparationPlan,
    *,
    profile_id: str,
    qualification_id: str,
    binding_revision: int,
) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"m0-12-binding:{plan.location.root_id}:{profile_id}:"
            f"{plan.target_timeline_id}:{qualification_id}:{binding_revision}",
        )
    )


def _corrective_timeline_root_for_plan(
    plan: _CorrectiveSuccessorPreparationPlan,
) -> CanonicalRootRef:
    root_id = str(uuid5(NAMESPACE_URL, f"{plan.preparation_id}:timeline-root"))
    return CanonicalRootRef(
        root_path=str(
            plan.location.root / "mature-runtime-m0" / "roots" / root_id
        ),
        root_id=root_id,
        control_store_id=str(
            uuid5(NAMESPACE_URL, f"{plan.preparation_id}:timeline-control-store")
        ),
        timeline_store_id=str(
            uuid5(NAMESPACE_URL, f"{plan.preparation_id}:timeline-store")
        ),
        timeline_id=plan.target_timeline_id,
        root_kind=plan.location.root_kind,
    )


def _corrective_successor_write_projection(
    plan: _CorrectiveSuccessorPreparationPlan,
    *,
    profile_id: str,
    genesis_branch_id: str,
    genesis_snapshot_id: str,
    knowledge_snapshot_id: str,
    predecessor_policy_decision_id: str,
    predecessor_qri_integrity_digest: str,
    compatibility_proof_id: str,
    compatibility_proof_integrity_digest: str,
    predecessor_binding: RuntimeAuthorityBinding | Mapping[str, object],
    nonconforming_binding: RuntimeAuthorityBinding | Mapping[str, object],
    previous_fact_digest: str,
    _authority: object,
) -> dict[str, object]:
    """Issue the complete deterministic Phase-06 write projection."""

    if _authority is not _CORRECTIVE_SUCCESSOR_PREPARATION_AUTHORITY:
        raise TypeError("corrective write projection requires private authority")
    _verify_corrective_successor_plan(plan)
    if not isinstance(predecessor_binding, RuntimeAuthorityBinding):
        predecessor_binding = RuntimeAuthorityBinding.from_dict(predecessor_binding)
    if not isinstance(nonconforming_binding, RuntimeAuthorityBinding):
        nonconforming_binding = RuntimeAuthorityBinding.from_dict(
            nonconforming_binding
        )
    command, idempotency_key, confirmed_brief = _local_first_phase3_local_interaction(
        predecessor_qualification_id=plan.predecessor_qualification_id,
        profile_id=profile_id,
        successor_publication_key=plan.publication_key,
        _corrective_timeline_id=plan.target_timeline_id,
    )
    interaction_basis_digest = _local_first_interaction_basis_digest(
        profile_id=profile_id,
        timeline_id=plan.target_timeline_id,
        command_fingerprint=command.payload_fingerprint,
        idempotency_key_digest=sha256(idempotency_key.encode("utf-8")).hexdigest(),
        confirmed_brief_digest=sha256(confirmed_brief.encode("utf-8")).hexdigest(),
    )
    compatibility_proof = _local_first_successor_compatibility_digest(
        predecessor_qualification_id=plan.predecessor_qualification_id,
        predecessor_integrity_digest=predecessor_qri_integrity_digest,
        predecessor_compatibility_proof=compatibility_proof_integrity_digest,
        policy_decision_id=plan.policy_decision_id,
        capability_manifest=plan.policy_decision.capability_manifest,
        provider_authority=_LOCAL_LLAMA_PROVIDER_AUTHORITY,
        interaction_basis_digest=interaction_basis_digest,
    )
    qualification_id = str(
        uuid5(
            NAMESPACE_URL,
            "accepted-artifact-local-llama-successor-qri:"
            f"{plan.studio_location.root_id}:{plan.publication_key}",
        )
    )
    qri_unsigned = {
        "qualification_id": qualification_id,
        "qualification_revision": predecessor_binding.qualification_revision + 2,
        "profile_id": profile_id,
        "genesis_branch_id": genesis_branch_id,
        "genesis_snapshot_id": genesis_snapshot_id,
        "knowledge_snapshot_id": knowledge_snapshot_id,
        "policy_decision_ids": [plan.policy_decision_id],
        "capabilities": plan.policy_decision.capability_manifest.to_dict(),
        "isolation_proof": IsolationProof(
            root_id=plan.studio_location.root_id,
            root_kind=plan.studio_location.root_kind,
            path_class="local-private-experimental",
            provenance_class="project-original-only",
        ).to_dict(),
        "provider_authority": _LOCAL_LLAMA_PROVIDER_AUTHORITY,
        "compatibility_proof": compatibility_proof,
        "predecessor_qualification_id": plan.predecessor_qualification_id,
        "publication_key": plan.publication_key,
        "published_at_us": plan.published_at_us,
    }
    qri_payload = {**qri_unsigned, "integrity_digest": _studio_digest(qri_unsigned)}
    predecessor_publication_digest = _studio_digest(
        {
            "artifact_id": plan.artifact_id,
            "genesis_snapshot_id": genesis_snapshot_id,
            "knowledge_snapshot_id": knowledge_snapshot_id,
            "policy_decision_id": predecessor_policy_decision_id,
            "compatibility_proof_id": compatibility_proof_id,
            "qri_integrity_digest": predecessor_qri_integrity_digest,
        }
    )
    publication_digest = _studio_digest(
        {
            "artifact_id": plan.artifact_id,
            "predecessor_qualification_id": plan.predecessor_qualification_id,
            "predecessor_integrity_digest": predecessor_qri_integrity_digest,
            "predecessor_publication_digest": predecessor_publication_digest,
            "genesis_snapshot_id": genesis_snapshot_id,
            "knowledge_snapshot_id": knowledge_snapshot_id,
            "accepted_artifact_compatibility_proof": compatibility_proof_integrity_digest,
            "policy_decision_id": plan.policy_decision_id,
            "capability_manifest": plan.policy_decision.capability_manifest.to_dict(),
            "provider_authority": _LOCAL_LLAMA_PROVIDER_AUTHORITY,
            "interaction_basis_digest": interaction_basis_digest,
            "corrective_preparation_digest": plan.plan_digest,
            "successor_integrity_digest": qri_payload["integrity_digest"],
        }
    )
    revision = predecessor_binding.binding_revision + 1
    binding_id = _corrective_binding_id(
        plan,
        profile_id=profile_id,
        qualification_id=qualification_id,
        binding_revision=revision,
    )
    authority = _RuntimeBindingAuthority(
        authority_scope_id=str(uuid5(NAMESPACE_URL, f"m0-12-authority-scope:{binding_id}")),
        profile_id=profile_id,
        timeline_id=plan.target_timeline_id,
        allowed_intents=ALLOWED_INTENTS,
        allowed_provenance=ALLOWED_PROVENANCE,
        binding_id=binding_id,
        binding_revision=revision,
        binding_epoch=predecessor_binding.binding_epoch + 1,
        qualification_id=qualification_id,
        qualification_revision=int(qri_payload["qualification_revision"]),
        provider_authority=_LOCAL_LLAMA_PROVIDER_AUTHORITY,
    )
    root = plan.prepared_timeline_root
    root_hashes = _expected_corrective_root_hashes(plan, root, authority)
    qri = QualifiedRuntimeInput._published(
        _authority=_QRI_PUBLICATION_TOKEN,
        **{
            **qri_unsigned,
            "policy_decision_ids": (plan.policy_decision_id,),
            "capabilities": plan.policy_decision.capability_manifest,
            "isolation_proof": IsolationProof(**qri_unsigned["isolation_proof"]),
            "integrity_digest": qri_payload["integrity_digest"],
        },
    )
    members = [
        _branch_governance_member(
            replace(predecessor_binding, state=BindingState.RETIRED),
            classification=_BRANCH_NORMAL,
            serving_disposition=_BRANCH_RETIRED,
        ),
        _branch_governance_member(
            nonconforming_binding,
            classification=_BRANCH_NONCONFORMING,
            serving_disposition=_BRANCH_HELD,
        ),
        {
            "binding_id": binding_id,
            "binding_revision": revision,
            "binding_epoch": authority.binding_epoch,
            "profile_id": profile_id,
            "timeline_id": plan.target_timeline_id,
            "authority_scope_id": authority.authority_scope_id,
            "qualification_id": qualification_id,
            "qri_integrity_digest": qri_payload["integrity_digest"],
            "timeline_root_id": root.root_id,
            "timeline_control_store_id": root.control_store_id,
            "timeline_store_id": root.timeline_store_id,
            "classification": _BRANCH_NORMAL,
            "serving_disposition": _BRANCH_ELIGIBLE,
        },
    ]
    case_id = str(
        uuid5(
            NAMESPACE_URL,
            f"post-m0-05-branch-governance:{plan.location.root_id}:{profile_id}",
        )
    )
    corrective_preparation = _corrective_preparation_record_payload(
        plan, qri, root, root_hashes
    )
    fact_digest = _branch_governance_fact_digest(
        case_id=case_id,
        host_root_id=plan.location.root_id,
        host_control_store_id=plan.location.control_store_id,
        sequence=2,
        previous_fact_digest=previous_fact_digest,
        members=members,
        corrective_preparation=corrective_preparation,
    )
    fact_id = str(
        uuid5(NAMESPACE_URL, f"post-m0-05-branch-fact:{case_id}:2:{fact_digest}")
    )
    return {
        "preparation_id": plan.preparation_id,
        "plan_digest": plan.plan_digest,
        "published_at_us": plan.published_at_us,
        "publication_key": plan.publication_key,
        "target_timeline_id": plan.target_timeline_id,
        "policy_decision": plan.policy_decision.to_dict(),
        "qri": {
            **qri_payload,
            "interaction_basis_digest": interaction_basis_digest,
            "publication_digest": publication_digest,
        },
        "new_timeline_root": {
            **root.to_dict(),
            "sha256": root_hashes,
            "state": "closed",
            "head_sequence": 0,
            "canonical_empty": True,
        },
        "binding": {
            "binding_id": binding_id,
            "binding_revision": revision,
            "binding_epoch": authority.binding_epoch,
            "profile_id": profile_id,
            "timeline_id": plan.target_timeline_id,
            "authority_scope_id": authority.authority_scope_id,
            "qualification_id": qualification_id,
            "qualification_revision": int(qri_payload["qualification_revision"]),
            "qri_integrity_digest": qri_payload["integrity_digest"],
            "timeline_root_id": root.root_id,
            "timeline_control_store_id": root.control_store_id,
            "timeline_store_id": root.timeline_store_id,
            "state": "active",
            "predecessor_binding_id": predecessor_binding.binding_id,
            "first_subject_event_sealed": False,
            "lease_generation": 1,
            "lease_state": "closed",
        },
        "governance_sequence_2": {
            "case_id": case_id,
            "sequence": 2,
            "previous_fact_digest": previous_fact_digest,
            "fact_id": fact_id,
            "fact_digest": fact_digest,
            "members": sorted(members, key=lambda item: str(item["binding_id"])),
        },
    }


def _corrective_preparation_record_payload(
    plan: _CorrectiveSuccessorPreparationPlan,
    qri: QualifiedRuntimeInput,
    root: CanonicalRootRef,
    expected_root_hashes: Mapping[str, str],
) -> dict[str, object]:
    return {
        "format": "post-m0-06-corrective-root-preparation-2",
        "preparation_id": plan.preparation_id,
        "plan_digest": plan.plan_digest,
        "plan_body": plan.body,
        "qualification_id": qri.qualification_id,
        "qri_integrity_digest": qri.integrity_digest,
        "sqlite_runtime_version": sqlite3.sqlite_version,
        "timeline_root": root.to_dict(),
        "timeline_root_sha256": dict(expected_root_hashes),
    }


def _corrective_preparation_record_path(
    host: RuntimeHostRootRef,
    root: CanonicalRootRef,
) -> Path:
    return host.root / "corrective-preparations" / f"{root.root_id}.json"


def _expected_corrective_root_hashes(
    plan: _CorrectiveSuccessorPreparationPlan,
    root: CanonicalRootRef,
    authority: _RuntimeBindingAuthority,
) -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="post-m0-06-root-fingerprint-") as raw:
        temporary_base = Path(raw).resolve()
        engine = TimelineEngine._create_bound(
            temporary_base,
            authority,
            root_kind=HOST_ROOT_KIND,
            _host_token=_HOST_TIMELINE_TOKEN,
            _reserved_identity=_ReservedTimelineIdentity(
                root_id=root.root_id,
                control_store_id=root.control_store_id,
                timeline_store_id=root.timeline_store_id,
            ),
            _created_at_us=plan.published_at_us,
        )
        try:
            materialized = engine.location
            hashes = {
                "control_database": _file_sha256(materialized.control_database),
                "timeline_database": _file_sha256(materialized.timeline_database),
            }
        finally:
            engine.close()
    identity = _canonical_json(
        {
            "format": "dynamic-subject-m0-canonical",
            "root_epoch": 1,
            "root_id": root.root_id,
            "root_kind": root.root_kind,
        }
    ) + "\n"
    return {
        "root_identity": sha256(identity.encode("utf-8")).hexdigest(),
        **hashes,
    }


def _reject_corrective_root_transient_files(root: CanonicalRootRef) -> None:
    for database in (root.control_database, root.timeline_database):
        for suffix in ("-journal", "-wal", "-shm"):
            if Path(f"{database}{suffix}").exists():
                raise RuntimeHostFailedClosed(
                    "corrective-successor-root-commitment-mismatch",
                    "prepared corrective root contains transient SQLite state",
                )


def _write_corrective_preparation_record(
    plan: _CorrectiveSuccessorPreparationPlan,
    qri: QualifiedRuntimeInput,
    root: CanonicalRootRef,
    expected_root_hashes: Mapping[str, str],
) -> None:
    payload = _corrective_preparation_record_payload(
        plan, qri, root, expected_root_hashes
    )
    payload_json = _canonical_json(payload)
    wrapper = {
        "payload": payload,
        "record_digest": sha256(payload_json.encode("utf-8")).hexdigest(),
    }
    text = _canonical_json(wrapper) + "\n"
    path = _corrective_preparation_record_path(plan.location, root)
    directory = path.parent
    try:
        directory.mkdir(exist_ok=True)
        if directory.is_symlink() or directory.resolve(strict=True).parent != plan.location.root:
            raise RuntimeHostFailedClosed(
                "corrective-successor-root-commitment-mismatch",
                "Host-local corrective commitment directory is not exact",
            )
        with path.open("x", encoding="utf-8", newline="\n") as target:
            target.write(text)
    except FileExistsError:
        existing = _read_corrective_preparation_record(plan.location, root)
        if existing != payload:
            raise RuntimeHostFailedClosed(
                "corrective-successor-root-commitment-mismatch",
                "Host already binds this corrective root to another preparation",
            ) from None
    except OSError as error:
        raise RuntimeHostFailedClosed(
            "corrective-successor-root-commitment-mismatch",
            "Host-local corrective root commitment could not be sealed",
        ) from error


def _read_corrective_preparation_record(
    host: RuntimeHostRootRef,
    root: CanonicalRootRef,
) -> dict[str, object]:
    path = _corrective_preparation_record_path(host, root)
    if (
        _has_linklike_component(path.parent, host.root)
        or not path.is_file()
        or path.is_symlink()
        or path.stat().st_nlink != 1
    ):
        raise RuntimeHostFailedClosed(
            "corrective-successor-root-commitment-mismatch",
            "Host-local corrective root commitment is absent or linked",
        )
    try:
        text = path.read_text(encoding="utf-8")
        wrapper = json.loads(text)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeHostFailedClosed(
            "corrective-successor-root-commitment-mismatch",
            "corrective root preparation record is unreadable",
        ) from error
    if not isinstance(wrapper, dict) or not isinstance(wrapper.get("payload"), dict):
        raise RuntimeHostFailedClosed(
            "corrective-successor-root-commitment-mismatch",
            "corrective root preparation record is not canonical",
        )
    payload = wrapper["payload"]
    payload_json = _canonical_json(payload)
    if (
        text != _canonical_json(wrapper) + "\n"
        or wrapper.get("record_digest")
        != sha256(payload_json.encode("utf-8")).hexdigest()
    ):
        raise RuntimeHostFailedClosed(
            "corrective-successor-root-commitment-mismatch",
            "corrective root preparation record bytes are not canonical",
        )
    return payload


def _verify_corrective_preparation_record(
    host: RuntimeHostRootRef,
    root: CanonicalRootRef,
    *,
    qualification_id: str,
    qri_integrity_digest: str,
    authority: _RuntimeBindingAuthority,
    predecessor: RuntimeAuthorityBinding,
    nonconforming: RuntimeAuthorityBinding,
    expected_plan: _CorrectiveSuccessorPreparationPlan | None = None,
) -> dict[str, object]:
    payload = _read_corrective_preparation_record(host, root)
    plan_body = payload.get("plan_body")
    if not isinstance(plan_body, dict):
        raise RuntimeHostFailedClosed(
            "corrective-successor-root-commitment-mismatch",
            "corrective root preparation plan body is absent",
        )
    plan_digest = sha256(_canonical_json(plan_body).encode("utf-8")).hexdigest()
    preparation_id = str(
        uuid5(NAMESPACE_URL, f"post-m0-06-corrective:{plan_digest}")
    )
    expected_root_id = str(
        uuid5(NAMESPACE_URL, f"{preparation_id}:timeline-root")
    )
    expected_control_store_id = str(
        uuid5(NAMESPACE_URL, f"{preparation_id}:timeline-control-store")
    )
    expected_timeline_store_id = str(
        uuid5(NAMESPACE_URL, f"{preparation_id}:timeline-store")
    )
    current_root_hashes = {
        "root_identity": _file_sha256(root.root / "root.identity"),
        "control_database": _file_sha256(root.control_database),
        "timeline_database": _file_sha256(root.timeline_database),
    }
    _reject_corrective_root_transient_files(root)
    try:
        sealed_plan = (
            expected_plan
            if expected_plan is not None
            else _CorrectiveSuccessorPreparationPlan._issue(
                location=RuntimeHostRootRef.from_dict(plan_body["location"]),
                studio_location=StudioRootRef.from_dict(
                    plan_body["studio_location"]
                ),
                artifact_id=str(plan_body["artifact_id"]),
                predecessor_qualification_id=str(
                    plan_body["predecessor_qualification_id"]
                ),
                nonconforming_qualification_id=str(
                    plan_body["nonconforming_qualification_id"]
                ),
                nonconforming_policy_decision_id=str(
                    plan_body["nonconforming_policy_decision_id"]
                ),
                nonconforming_policy_integrity_digest=str(
                    plan_body["nonconforming_policy_integrity_digest"]
                ),
                target_timeline_id=str(plan_body["target_timeline_id"]),
                policy_decision_id=str(plan_body["policy_decision_id"]),
                policy_decision=_policy_decision_from_payload(
                    plan_body["policy_decision"]
                ),
                publication_key=str(plan_body["publication_key"]),
                published_at_us=int(plan_body["published_at_us"]),
                predecessor_root_sha256=plan_body["predecessor_root_sha256"],
                nonconforming_root_sha256=plan_body[
                    "nonconforming_root_sha256"
                ],
                authority_preimage_sha256=plan_body[
                    "authority_preimage_sha256"
                ],
                _authority=_CORRECTIVE_SUCCESSOR_PREPARATION_AUTHORITY,
            )
        )
        expected_root_hashes = _expected_corrective_root_hashes(
            sealed_plan,
            root,
            authority,
        )
    except (KeyError, TypeError, ValueError, RuntimeHostProblem) as error:
        raise RuntimeHostFailedClosed(
            "corrective-successor-root-commitment-mismatch",
            "corrective root preparation plan cannot be reconstructed",
        ) from error
    if (
        payload.get("format") != "post-m0-06-corrective-root-preparation-2"
        or payload.get("plan_digest") != plan_digest
        or payload.get("preparation_id") != preparation_id
        or payload.get("qualification_id") != qualification_id
        or payload.get("qri_integrity_digest") != qri_integrity_digest
        or payload.get("sqlite_runtime_version") != sqlite3.sqlite_version
        or payload.get("timeline_root") != root.to_dict()
        or payload.get("timeline_root_sha256") != expected_root_hashes
        or current_root_hashes != expected_root_hashes
        or root.root_id != expected_root_id
        or root.control_store_id != expected_control_store_id
        or root.timeline_store_id != expected_timeline_store_id
        or plan_body.get("predecessor_qualification_id")
        != predecessor.qualification_id
        or plan_body.get("nonconforming_qualification_id")
        != nonconforming.qualification_id
        or plan_body.get("target_timeline_id") != predecessor.timeline_id
        or plan_body.get("predecessor_root_sha256")
        != _corrective_root_hashes(predecessor)
        or plan_body.get("nonconforming_root_sha256")
        != _corrective_root_hashes(nonconforming)
        or (expected_plan is not None and plan_body != expected_plan.body)
    ):
        raise RuntimeHostFailedClosed(
            "corrective-successor-root-commitment-mismatch",
            "corrective root differs from its sealed preparation commitment",
        )
    return payload


@dataclass(frozen=True)
class RuntimeHealth:
    binding_id: str
    lane_id: str | None
    healthy: bool
    serving: bool
    gate_state: str
    gate_epoch: int
    timeline_basis: TimelineBasis
    first_subject_event_sealed: bool


@dataclass(frozen=True)
class RuntimeRoute:
    binding: RuntimeAuthorityBinding
    lane_id: str
    health: RuntimeHealth


@dataclass
class _Lane:
    binding: RuntimeAuthorityBinding
    binding_id: str
    lane_id: str
    worker: _RuntimeWorker
    lock: threading.Lock
    submission_authorization: _LocalFirstSubmissionAuthorization | None = None
    accepting: bool = True
    first_event_seen: bool = False


class _RuntimeWorker:
    """One thread owns one SubjectRuntime and its thread-affine SQLite writer."""

    def __init__(
        self,
        binding_id: str,
        factory: Callable[[], SubjectRuntime],
    ) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=f"m0-runtime-{binding_id[:8]}",
        )
        self._runtime: SubjectRuntime | None = None
        try:
            self._runtime = self._executor.submit(factory).result()
        except Exception:
            self._executor.shutdown(wait=True, cancel_futures=True)
            raise
        self._closed = False

    def call(self, method: str, /, *args: object, **kwargs: object) -> Any:
        if self._closed or self._runtime is None:
            raise RuntimeHostRejected(
                "runtime-worker-closed",
                "SubjectRuntime lane worker is closed",
            )

        def invoke() -> Any:
            runtime = self._runtime
            if runtime is None:
                raise RuntimeHostRejected(
                    "runtime-worker-closed",
                    "SubjectRuntime lane worker is closed",
                )
            return getattr(runtime, method)(*args, **kwargs)

        return self._executor.submit(invoke).result()

    @property
    def location(self) -> CanonicalRootRef:
        return self.call("__getattribute__", "location")

    def close(self) -> None:
        if self._closed:
            return
        try:
            self.call("close")
        finally:
            self._closed = True
            self._runtime = None
            self._executor.shutdown(wait=True, cancel_futures=True)


class RuntimeLease:
    """Typed, exclusive access to one SubjectRuntime authority lane."""

    def __init__(
        self,
        host: RuntimeHost,
        lane: _Lane,
        binding: RuntimeAuthorityBinding,
    ) -> None:
        self._host = host
        self._lane = lane
        self.binding = binding
        self.lane_id = lane.lane_id
        self._released = False

    def __enter__(self) -> RuntimeLease:
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()

    def _require_active(self) -> None:
        if self._released:
            raise RuntimeHostRejected("lease-released", "runtime lease is released")

    def _require_submission_authorized(
        self,
        command: SubjectCommand,
        idempotency_key: str,
    ) -> None:
        authorization = self._lane.submission_authorization
        if authorization is not None and not authorization.matches(
            self.binding,
            command,
            idempotency_key,
        ):
            raise RuntimeHostRejected(
                "local-interaction-plan-mismatch",
                "RuntimeLease accepts only the QRI-bound command and idempotency key",
            )

    def execute(
        self,
        command: SubjectCommand,
        *,
        idempotency_key: str,
    ) -> RuntimeResult:
        self._require_active()
        self._host._require_binding_permit(self.binding)
        self._require_submission_authorized(command, idempotency_key)
        try:
            return self._lane.worker.call(
                "execute",
                command,
                idempotency_key=idempotency_key,
            )
        finally:
            self._host._synchronize_subject_event_seal(self._lane)

    def admit(
        self,
        command: SubjectCommand,
        *,
        idempotency_key: str,
    ) -> RuntimeResult:
        """Commit canonical Admission while leaving execution independently observable."""

        self._require_active()
        self._host._require_binding_permit(self.binding)
        self._require_submission_authorized(command, idempotency_key)
        try:
            return self._lane.worker.call(
                "admit",
                command,
                idempotency_key=idempotency_key,
            )
        finally:
            self._host._synchronize_subject_event_seal(self._lane)

    def resume(self, operation_ref: OperationRef) -> RuntimeResult:
        self._require_active()
        self._host._require_binding_permit(self.binding)
        try:
            return self._lane.worker.call("resume", operation_ref)
        finally:
            self._host._synchronize_subject_event_seal(self._lane)

    def follow(
        self,
        operation_ref: OperationRef,
        *,
        timeout_seconds: float = 0.0,
    ) -> RuntimeResult:
        self._require_active()
        self._host._require_binding_permit(self.binding)
        return self._lane.worker.call(
            "follow",
            operation_ref,
            timeout_seconds=timeout_seconds,
        )

    def list_living_memories(
        self,
        *,
        active_only: bool = False,
        limit: int = 100,
    ) -> tuple[LivingMemoryRecord, ...]:
        self._require_active()
        self._host._require_binding_permit(self.binding)
        return self._lane.worker.call(
            "list_living_memories",
            active_only=active_only,
            limit=limit,
        )

    def list_conversation_turns(
        self,
        *,
        limit: int = 20,
    ) -> tuple[ConversationTurnRecord, ...]:
        self._require_active()
        self._host._require_binding_permit(self.binding)
        return self._lane.worker.call("list_conversation_turns", limit=limit)

    def list_relationship_interactions(
        self,
        *,
        limit: int = 100,
    ) -> tuple[RelationshipStanceInteraction, ...]:
        self._require_active()
        self._host._require_binding_permit(self.binding)
        return self._lane.worker.call(
            "list_relationship_interactions",
            limit=limit,
        )

    def list_participant_goal_commitments(
        self,
        *,
        active_only: bool = False,
        limit: int = 100,
    ) -> tuple[ParticipantGoalCommitmentRecord, ...]:
        self._require_active()
        self._host._require_binding_permit(self.binding)
        return self._lane.worker.call(
            "list_participant_goal_commitments",
            active_only=active_only,
            limit=limit,
        )

    def list_situated_states(
        self,
        *,
        active_only: bool = False,
        limit: int = 100,
    ) -> tuple[SituatedStateRecord, ...]:
        self._require_active()
        self._host._require_binding_permit(self.binding)
        return self._lane.worker.call(
            "list_situated_states",
            active_only=active_only,
            limit=limit,
        )

    def current_medium_state(self) -> MediumStateRecord:
        self._require_active()
        self._host._require_binding_permit(self.binding)
        return self._lane.worker.call("current_medium_state")

    def list_medium_signals(self, *, limit: int = 7) -> tuple[MediumSignalRecord, ...]:
        self._require_active()
        self._host._require_binding_permit(self.binding)
        return self._lane.worker.call("list_medium_signals", limit=limit)

    def release(self) -> None:
        if not self._released:
            self._released = True
            self._lane.lock.release()


class RuntimeHost:

    _relationship_enabled = False
    """Private Host Module owning bindings, assemblies, and process-local lanes."""

    def __init__(
        self,
        location: RuntimeHostRootRef,
        studio_location: StudioRootRef,
        writer: sqlite3.Connection,
        cognition_assembly: _CognitionAssembly,
        *,
        fault_hook: Callable[[RuntimeHostFaultPoint], None] | None,
        runtime_interrupt_at: RuntimeFaultPoint | None,
        runtime_fault_hook: Callable[[RuntimeFaultPoint, OperationRef], None] | None,
        instance_id: str,
        runtime_identity: RuntimeIdentityProjection | None,
    ) -> None:
        self._location = location
        self._studio_location = studio_location
        self._writer = writer
        self._cognition_assembly = cognition_assembly
        self._fault_hook = fault_hook
        self._runtime_interrupt_at = runtime_interrupt_at
        self._runtime_fault_hook = runtime_fault_hook
        self._instance_id = instance_id
        self._runtime_identity = runtime_identity
        self._lanes: dict[tuple[str, str], _Lane] = {}
        self._state_lock = threading.RLock()
        self._owner_thread_id = threading.get_ident()
        self._closed = False
        self._local_serving_authorization: _LocalServingAuthorization | None = None

    @property
    def location(self) -> RuntimeHostRootRef:
        return self._location

    @classmethod
    def create(
        cls,
        test_base: Path,
        *,
        studio_location: StudioRootRef,
        cognition: CognitionEngine,
        _cognition_assembly: _CognitionAssembly | None = None,
        _fault_hook: Callable[[RuntimeHostFaultPoint], None] | None = None,
        _runtime_interrupt_at: RuntimeFaultPoint | None = None,
        _runtime_fault_hook: (
            Callable[[RuntimeFaultPoint, OperationRef], None] | None
        ) = None,
        _activation_plan: _HostActivationPlan | None = None,
        relationship_enabled: bool = False,
        _runtime_identity: RuntimeIdentityProjection | None = None,
    ) -> RuntimeHost:
        if not isinstance(studio_location, StudioRootRef):
            raise TypeError("RuntimeHost requires StudioRootRef authority")
        if not _cognition_contract_supported(cognition):
            raise TypeError(
                "RuntimeHost requires a CognitionEngine matching QRI authority"
            )
        cognition_assembly = (
            _CognitionAssembly._single(cognition)
            if _cognition_assembly is None
            else _cognition_assembly
        )
        if type(cognition_assembly) is not _CognitionAssembly or not (
            cognition_assembly.accepts_bootstrap(cognition)
        ):
            raise RuntimeHostRejected(
                "cognition-assembly-mismatch",
                "private cognition assembly does not accept the bootstrap adapter",
            )
        if _activation_plan is not None:
            plan_kind_matches = (
                type(_activation_plan) is _RuntimeActivationPlan
                and studio_location.root_kind == EXPERIMENTAL_ROOT_KIND
            ) or (
                type(_activation_plan) is _DormantArtifactActivationPlan
                and studio_location.root_kind == HOST_ROOT_KIND
            ) or (
                type(_activation_plan) is _DormantArtifactExperimentalActivationPlan
                and studio_location.root_kind == EXPERIMENTAL_ROOT_KIND
            )
            if (
                not plan_kind_matches
                or cognition.provider_authority != _activation_plan.provider_authority
            ):
                raise RuntimeHostRejected(
                    "activation-plan-mismatch",
                    "reserved activation plan does not match the experimental Host",
                )
        base = _validate_runtime_base(Path(test_base), studio_location)
        root_id = (
            str(uuid4())
            if _activation_plan is None
            else _activation_plan.host_root_id
        )
        control_store_id = (
            str(uuid4())
            if _activation_plan is None
            else _activation_plan.host_control_store_id
        )
        root = base / "mature-runtime-m0" / "host-roots" / root_id
        root.parent.mkdir(parents=True, exist_ok=True)
        try:
            root.mkdir()
        except OSError as error:
            raise RuntimeHostFailedClosed(
                "host-root-create-failed",
                "new RuntimeHost root could not be created",
            ) from error
        location = RuntimeHostRootRef(
            root_path=str(root),
            root_id=root_id,
            control_store_id=control_store_id,
            root_kind=studio_location.root_kind,
        )
        try:
            _write_root_identity(location, studio_location)
            _bootstrap_control(location, studio_location)
            return cls.open(
                location,
                studio_location=studio_location,
                cognition=cognition,
                _cognition_assembly=cognition_assembly,
                _fault_hook=_fault_hook,
                _runtime_interrupt_at=_runtime_interrupt_at,
                _runtime_fault_hook=_runtime_fault_hook,
                relationship_enabled=relationship_enabled,
                _runtime_identity=_runtime_identity,
            )
        except Exception:
            if root.exists() and _is_relative_to(root.resolve(), base):
                shutil.rmtree(root)
            raise

    @classmethod
    def _install_forward_governance_v1_to_v2(
        cls,
        location: RuntimeHostRootRef,
        *,
        studio_location: StudioRootRef,
        plan: _ForwardGovernanceInstallPlan,
        _authority: object,
        _fault_hook: Callable[[_ForwardGovernanceFaultPoint], None] | None = None,
    ) -> _ForwardGovernanceInstallReceipt:
        if _authority is not _FORWARD_GOVERNANCE_INSTALL_AUTHORITY:
            raise TypeError("forward governance installation requires private authority")
        if type(location) is not RuntimeHostRootRef:
            raise TypeError("forward governance installation requires RuntimeHostRootRef")
        if type(studio_location) is not StudioRootRef:
            raise TypeError("forward governance installation requires StudioRootRef")
        if type(plan) is not _ForwardGovernanceInstallPlan:
            raise TypeError("forward governance installation requires an exact plan")
        _verify_forward_governance_plan(plan)
        if plan.location != location or plan.studio_location != studio_location:
            raise RuntimeHostRejected(
                "forward-governance-plan-mismatch",
                "forward governance plan does not bind the selected roots",
            )
        maintenance_id = str(uuid4())
        maintenance_session = object()
        _claim_process_registry(location.root_id, maintenance_id)
        with _FORWARD_GOVERNANCE_SESSION_LOCK:
            _FORWARD_GOVERNANCE_SESSIONS.add(maintenance_session)
        readers: tuple[sqlite3.Connection, ...] = ()
        try:
            paths = _forward_governance_database_paths(
                location,
                studio_location,
                plan.predecessor,
                plan.successor,
            )
            _verify_forward_governance_exact_roots(
                location=location,
                studio_location=studio_location,
                plan=plan,
            )
            _verify_forward_governance_paths(paths)
            _verify_forward_governance_nonhost_stores(
                studio_location=studio_location,
                plan=plan,
            )
            readers = _hold_forward_governance_source_snapshots(paths)
            return cls._install_forward_governance_v1_to_v2_locked(
                location,
                studio_location=studio_location,
                plan=plan,
                _authority=_authority,
                _maintenance_session=maintenance_session,
                _fault_hook=_fault_hook,
            )
        finally:
            for reader in readers:
                try:
                    reader.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                reader.close()
            with _FORWARD_GOVERNANCE_SESSION_LOCK:
                _FORWARD_GOVERNANCE_SESSIONS.discard(maintenance_session)
            _release_process_registry(location.root_id, maintenance_id)

    @classmethod
    def _install_forward_governance_v1_to_v2_locked(
        cls,
        location: RuntimeHostRootRef,
        *,
        studio_location: StudioRootRef,
        plan: _ForwardGovernanceInstallPlan,
        _authority: object,
        _maintenance_session: object | None = None,
        _fault_hook: Callable[[_ForwardGovernanceFaultPoint], None] | None = None,
    ) -> _ForwardGovernanceInstallReceipt:
        """Install the confirmed containment fact without opening a runtime lane."""

        if _authority is not _FORWARD_GOVERNANCE_INSTALL_AUTHORITY:
            raise TypeError("forward governance installation requires private authority")
        with _FORWARD_GOVERNANCE_SESSION_LOCK:
            maintenance_session_active = (
                _maintenance_session in _FORWARD_GOVERNANCE_SESSIONS
            )
        if not maintenance_session_active:
            raise TypeError(
                "forward governance locked installation requires active maintenance session"
            )
        if type(location) is not RuntimeHostRootRef or type(
            studio_location
        ) is not StudioRootRef:
            raise TypeError("forward governance installation requires exact roots")
        if type(plan) is not _ForwardGovernanceInstallPlan:
            raise TypeError("forward governance installation requires an exact plan")
        _verify_forward_governance_plan(plan)
        if plan.location != location or plan.studio_location != studio_location:
            raise RuntimeHostRejected(
                "forward-governance-plan-mismatch",
                "forward governance plan does not bind the selected roots",
            )
        _validate_existing_root(
            location.root,
            location.root_id,
            root_kind=location.root_kind,
            studio_location=studio_location,
        )
        _read_root_identity(location, studio_location)
        _verify_forward_governance_exact_roots(
            location=location,
            studio_location=studio_location,
            plan=plan,
        )
        paths = _forward_governance_database_paths(
            location,
            studio_location,
            plan.predecessor,
            plan.successor,
        )
        _verify_forward_governance_paths(paths)
        before = {name: _file_sha256(path) for name, path in paths.items()}
        expected_before = plan.database_sha256
        already_applied = _forward_governance_installed_receipt(
            location=location,
            studio_location=studio_location,
            plan=plan,
            paths=paths,
            before=before,
        )
        if already_applied is not None:
            return already_applied
        if before != expected_before:
            raise RuntimeHostFailedClosed(
                "forward-governance-preflight-mismatch",
                "database preimage differs from the confirmed installation plan",
            )
        writer = _connect_existing(location.control_database)
        try:
            try:
                _begin(writer)
            except sqlite3.OperationalError as error:
                raise RuntimeHostFailedClosed(
                    "forward-governance-host-writer-unavailable",
                    "the confirmed Host database was not writable for containment installation",
                ) from error
            if _file_sha256(location.control_database) != expected_before["host_database"]:
                raise RuntimeHostFailedClosed(
                    "forward-governance-preflight-mismatch",
                    "Host database changed before the locked preflight",
                )
            _verify_forward_governance_v1_preimage(
                writer,
                location=location,
                studio_location=studio_location,
                plan=plan,
            )
            if _fault_hook is not None:
                _fault_hook(_ForwardGovernanceFaultPoint.AFTER_LOCKED_PREFLIGHT)
            for statement in _CONTROL_V1_TO_V2_DDL:
                writer.execute(statement)
            if _fault_hook is not None:
                _fault_hook(_ForwardGovernanceFaultPoint.AFTER_V2_DELTA_DDL)
            changed = writer.execute(
                "UPDATE host_manifest SET schema_version = 2 "
                "WHERE singleton = 1 AND schema_version = 1"
            )
            if changed.rowcount != 1:
                raise RuntimeHostFailedClosed(
                    "forward-governance-schema-conflict",
                    "Host manifest did not have the confirmed v1 preimage",
                )
            writer.execute(f"PRAGMA user_version = {HOST_SCHEMA_VERSION}")
            if _fault_hook is not None:
                _fault_hook(_ForwardGovernanceFaultPoint.AFTER_MANIFEST_VERSION_UPDATE)
            created_at_us = _utc_microseconds()
            writer.execute(
                """
                INSERT INTO branch_governance_fact (
                    fact_id, case_id, host_root_id, host_control_store_id,
                    sequence, previous_fact_digest, fact_digest, created_at_us
                ) VALUES (?, ?, ?, ?, 1, NULL, ?, ?)
                """,
                (
                    plan.fact_id,
                    plan.case_id,
                    location.root_id,
                    location.control_store_id,
                    plan.fact_digest,
                    created_at_us,
                ),
            )
            members = (
                _branch_governance_member(
                    plan.predecessor,
                    classification=_BRANCH_NORMAL,
                    serving_disposition=_BRANCH_HELD,
                ),
                _branch_governance_member(
                    plan.successor,
                    classification=_BRANCH_NONCONFORMING,
                    serving_disposition=_BRANCH_HELD,
                ),
            )
            for member in members:
                writer.execute(
                    """
                    INSERT INTO branch_governance_member (
                        fact_id, binding_id, binding_revision, binding_epoch,
                        profile_id, timeline_id, authority_scope_id,
                        qualification_id, qri_integrity_digest, timeline_root_id,
                        timeline_control_store_id, timeline_store_id,
                        classification, serving_disposition
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (plan.fact_id, *member.values()),
                )
            if _fault_hook is not None:
                _fault_hook(_ForwardGovernanceFaultPoint.AFTER_INITIAL_GOVERNANCE_FACT)
                _fault_hook(_ForwardGovernanceFaultPoint.BEFORE_COMMIT)
            _commit(writer)
            if _fault_hook is not None:
                _fault_hook(_ForwardGovernanceFaultPoint.AFTER_COMMIT_BEFORE_RECEIPT)
        except sqlite3.IntegrityError as error:
            _rollback_if_needed(writer)
            raise RuntimeHostFailedClosed(
                "forward-governance-installation-conflict",
                "the containment installation conflicted with persisted state",
            ) from error
        except Exception:
            _rollback_if_needed(writer)
            raise
        finally:
            writer.close()
        _verify_forward_governance_exact_roots(
            location=location,
            studio_location=studio_location,
            plan=plan,
        )
        _verify_forward_governance_paths(paths)
        after = {name: _file_sha256(path) for name, path in paths.items()}
        non_host_unchanged = all(
            before[name] == after[name]
            for name in paths
            if name != "host_database"
        )
        if not non_host_unchanged:
            raise RuntimeHostFailedClosed(
                "forward-governance-postcondition-failed",
                "a non-Host canonical store changed during governance installation",
            )
        verified = _forward_governance_installed_receipt(
            location=location,
            studio_location=studio_location,
            plan=plan,
            paths=paths,
            before=after,
        )
        if verified is None:
            raise RuntimeHostFailedClosed(
                "forward-governance-postcondition-failed",
                "the committed governance state could not be verified",
            )
        return _ForwardGovernanceInstallReceipt(
            installation_id=plan.installation_id,
            status="applied",
            fact_id=plan.fact_id,
            fact_digest=plan.fact_digest,
            host_database_sha256_before=before["host_database"],
            host_database_sha256_after=after["host_database"],
            non_host_databases_unchanged=True,
        )

    @classmethod
    def _prepare_corrective_local_first_successor_recovery(
        cls,
        *,
        recovery_plan: _CorrectiveSuccessorRecoveryPlan,
        _authority: object,
        _fault_hook: (
            Callable[[_CorrectiveSuccessorFaultPoint], None] | None
        ) = None,
    ) -> _CorrectiveSuccessorPreparationReceipt:
        """Apply only a Host-issued, evidence-bound recovery plan."""

        if _authority is not _CORRECTIVE_SUCCESSOR_PREPARATION_AUTHORITY:
            raise TypeError("corrective successor recovery requires private authority")
        _verify_corrective_successor_recovery_plan(recovery_plan)
        return cls._prepare_corrective_local_first_successor(
            plan=recovery_plan.plan,
            _authority=_authority,
            _require_fresh_preimage=True,
            _fault_hook=_fault_hook,
        )

    @classmethod
    def _prepare_corrective_local_first_successor(
        cls,
        *,
        plan: _CorrectiveSuccessorPreparationPlan,
        _authority: object,
        _require_fresh_preimage: bool = False,
        _fault_hook: (
            Callable[[_CorrectiveSuccessorFaultPoint], None] | None
        ) = None,
    ) -> _CorrectiveSuccessorPreparationReceipt:
        """Prepare, but never serve, the one governed corrective successor."""

        if _authority is not _CORRECTIVE_SUCCESSOR_PREPARATION_AUTHORITY:
            raise TypeError("corrective successor preparation requires private authority")
        _verify_corrective_successor_plan(plan)
        if _fault_hook is not None and not callable(_fault_hook):
            raise TypeError("_fault_hook must be callable")
        location = plan.location
        studio_location = plan.studio_location
        artifact_id = plan.artifact_id
        predecessor_qualification_id = plan.predecessor_qualification_id
        nonconforming_qualification_id = plan.nonconforming_qualification_id
        target_timeline_id = plan.target_timeline_id
        policy_decision_id = plan.policy_decision_id
        publication_key = plan.publication_key
        _published_at_us = plan.published_at_us
        _validate_existing_root(
            location.root,
            location.root_id,
            root_kind=location.root_kind,
            studio_location=studio_location,
        )
        _read_root_identity(location, studio_location)
        authority_preimage_before = {
            "studio_root_identity": _file_sha256(
                studio_location.root / "root.identity"
            ),
            "studio_profile_database": _file_sha256(
                studio_location.profile_database
            ),
            "host_root_identity": _file_sha256(location.root / "root.identity"),
            "host_control_database": _file_sha256(location.control_database),
        }
        maintenance_id = str(
            uuid5(
                NAMESPACE_URL,
                f"post-m0-06-corrective-maintenance:{plan.preparation_id}",
            )
        )
        _claim_process_registry(location.root_id, maintenance_id)
        snapshot_readers: tuple[sqlite3.Connection, ...] = ()
        try:
            existing_qri: QualifiedRuntimeInput | None = None
            studio = SubjectStudio.open(
                studio_location,
                policy_kernel=PolicyKernel(clock=lambda: _published_at_us),
            )
            try:
                try:
                    existing_qri = studio.query_qri(publication_key=publication_key)
                except StudioRejected as error:
                    if error.code != "qri-not-found":
                        raise
            finally:
                studio.close()
            if _require_fresh_preimage and existing_qri is not None:
                raise RuntimeHostFailedClosed(
                    "corrective-successor-recovery-authorization-required",
                    "an existing corrective QRI requires a separately reviewed recovery Preview",
                )
            if _require_fresh_preimage and (
                plan.prepared_timeline_root.root.exists()
                or _corrective_preparation_record_path(
                    location,
                    plan.prepared_timeline_root,
                ).exists()
            ):
                raise RuntimeHostFailedClosed(
                    "corrective-successor-recovery-authorization-required",
                    "an existing corrective root or commitment requires a separately reviewed recovery Preview",
                )
            if (
                existing_qri is None
                and authority_preimage_before != plan.authority_preimage_sha256
            ):
                raise RuntimeHostFailedClosed(
                    "corrective-successor-preimage-mismatch",
                    "Studio or Host authority bytes differ from the sealed Phase 2 preimage",
                )
            writer = _connect_existing(location.control_database)
            try:
                _verify_control(location, studio_location, writer)
                verifier = object.__new__(cls)
                verifier._location = location
                verifier._studio_location = studio_location
                verifier._writer = writer
                predecessor_row = writer.execute(
                    f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
                    "WHERE qualification_id = ?",
                    (predecessor_qualification_id,),
                ).fetchone()
                nonconforming_row = writer.execute(
                    f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
                    "WHERE qualification_id = ?",
                    (nonconforming_qualification_id,),
                ).fetchone()
                if predecessor_row is None or nonconforming_row is None:
                    raise RuntimeHostFailedClosed(
                        "corrective-successor-preimage-mismatch",
                        "governed two-held preimage is incomplete",
                    )
                predecessor = verifier._binding_from_row(predecessor_row)
                nonconforming = verifier._binding_from_row(nonconforming_row)
                already_prepared = predecessor.state is BindingState.RETIRED
                if (
                    predecessor.state
                    not in {BindingState.ACTIVE, BindingState.RETIRED}
                    or nonconforming.state is not BindingState.ACTIVE
                    or predecessor.profile_id != nonconforming.profile_id
                    or predecessor.timeline_id != target_timeline_id
                    or nonconforming.timeline_id == target_timeline_id
                    or predecessor.predecessor_binding_id is not None
                    or nonconforming.predecessor_binding_id is not None
                    or predecessor.first_subject_event_sealed
                ):
                    raise RuntimeHostRejected(
                        "corrective-successor-preimage-mismatch",
                        "corrective preparation requires the exact two-held source",
                    )
                active_count = int(
                    writer.execute(
                        "SELECT count(*) FROM runtime_authority_binding "
                        "WHERE profile_id = ? AND state = 'active'",
                        (predecessor.profile_id,),
                    ).fetchone()[0]
                )
                if already_prepared:
                    candidate_rows = writer.execute(
                        f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
                        "WHERE profile_id = ? AND timeline_id = ? AND state = 'active'",
                        (predecessor.profile_id, predecessor.timeline_id),
                    ).fetchall()
                    if len(candidate_rows) != 1:
                        raise RuntimeHostFailedClosed(
                            "corrective-successor-recovery-mismatch",
                            "prepared successor is not the unique active Timeline binding",
                        )
                    prepared = verifier._binding_from_row(candidate_rows[0])
                    expected_binding_id = _corrective_binding_id(
                        plan,
                        profile_id=predecessor.profile_id,
                        qualification_id=(
                            existing_qri.qualification_id
                            if existing_qri is not None
                            else prepared.qualification_id
                        ),
                        binding_revision=predecessor.binding_revision + 1,
                    )
                    expected_timeline_root = _corrective_timeline_root_for_plan(plan)
                    if (
                        existing_qri is None
                        or prepared.binding_id != expected_binding_id
                        or prepared.qualification_id
                        != existing_qri.qualification_id
                        or prepared.predecessor_binding_id
                        != predecessor.binding_id
                        or prepared.timeline_root != expected_timeline_root
                        or not verifier._is_prepared_corrective_case(prepared)
                        or active_count != 2
                    ):
                        raise RuntimeHostFailedClosed(
                            "corrective-successor-recovery-mismatch",
                            "persisted successor does not match this exact plan",
                        )
                else:
                    try:
                        verifier._require_structural_binding_permit(predecessor)
                    except RuntimeHostRejected as error:
                        if error.code != "branch-serving-held":
                            raise
                    verifier._require_corrective_governance_preimage(
                        predecessor,
                        nonconforming,
                    )
                if not already_prepared and active_count != 2:
                    raise RuntimeHostRejected(
                        "corrective-successor-preimage-mismatch",
                        "corrective preparation accepts exactly two active held bindings",
                    )
                predecessor_root_hashes_before = plan.predecessor_root_sha256
                nonconforming_root_hashes_before = (
                    plan.nonconforming_root_sha256
                )
                if (
                    _corrective_root_hashes(predecessor)
                    != predecessor_root_hashes_before
                    or _corrective_root_hashes(nonconforming)
                    != nonconforming_root_hashes_before
                ):
                    raise RuntimeHostFailedClosed(
                        "corrective-successor-preimage-mismatch",
                        "source Timeline bytes differ from the sealed plan",
                    )
                predecessor_state = _corrective_timeline_state(predecessor)
                nonconforming_state = _corrective_timeline_state(nonconforming)
                lease_rows = writer.execute(
                    "SELECT binding_id, lease_state FROM runtime_instance_lease "
                    "WHERE binding_id IN (?, ?) ORDER BY binding_id",
                    (predecessor.binding_id, nonconforming.binding_id),
                ).fetchall()
                expected_history = (
                    predecessor_state[0] == "closed"
                    and predecessor_state[2].head_sequence == 0
                    and not predecessor_state[3]
                    and predecessor_state[5]
                    and nonconforming_state[0] == "closed"
                    and nonconforming_state[2].head_sequence == 1
                    and nonconforming_state[3]
                    and nonconforming_state[6]
                    and nonconforming.first_subject_event_sealed
                    and len(lease_rows) == 2
                    and all(str(row[1]) == "closed" for row in lease_rows)
                )
                if not expected_history:
                    raise RuntimeHostFailedClosed(
                        "corrective-successor-preimage-mismatch",
                        "corrective preparation requires exact closed head-0/head-1 history",
                    )
                governance_case_id = verifier._governance_case_id(
                    predecessor.profile_id
                )
                governance_facts_before = tuple(
                    tuple(row)
                    for row in writer.execute(
                        "SELECT * FROM branch_governance_fact "
                        "WHERE case_id = ? ORDER BY sequence",
                        (governance_case_id,),
                    ).fetchall()
                )
                governance_members_before = tuple(
                    tuple(row)
                    for row in writer.execute(
                        "SELECT member.* FROM branch_governance_member AS member "
                        "JOIN branch_governance_fact AS fact "
                        "ON fact.fact_id = member.fact_id "
                        "WHERE fact.case_id = ? "
                        "ORDER BY fact.sequence, member.binding_id",
                        (governance_case_id,),
                    ).fetchall()
                )
            finally:
                writer.close()

            source_timeline_paths = {
                "predecessor_control_database": (
                    predecessor.timeline_root.control_database
                ),
                "predecessor_timeline_database": (
                    predecessor.timeline_root.timeline_database
                ),
                "nonconforming_control_database": (
                    nonconforming.timeline_root.control_database
                ),
                "nonconforming_timeline_database": (
                    nonconforming.timeline_root.timeline_database
                ),
            }
            _verify_forward_governance_regular_paths(
                source_timeline_paths.values(), sqlite=True
            )
            snapshot_readers = _hold_forward_governance_source_snapshots(
                source_timeline_paths
            )
            if (
                _corrective_timeline_state(predecessor) != predecessor_state
                or _corrective_timeline_state(nonconforming)
                != nonconforming_state
                or _corrective_root_hashes(predecessor)
                != predecessor_root_hashes_before
                or _corrective_root_hashes(nonconforming)
                != nonconforming_root_hashes_before
            ):
                raise RuntimeHostConflict(
                    "corrective-successor-preimage-mismatch",
                    "a source Timeline changed before its read snapshot was fixed",
                )

            studio = SubjectStudio.open(
                studio_location,
                policy_kernel=PolicyKernel(clock=lambda: _published_at_us),
            )
            try:
                qri = studio._publish_accepted_artifact_local_llama_successor_qri(
                    artifact_id,
                    predecessor_qualification_id=predecessor_qualification_id,
                    policy_decision_id=policy_decision_id,
                    publication_key=publication_key,
                    _published_at_us=_published_at_us,
                    _corrective_authority=(
                        _CORRECTIVE_LOCAL_LLAMA_SUCCESSOR_AUTHORITY
                    ),
                    _corrective_timeline_id=target_timeline_id,
                    _corrective_preparation_digest=plan.plan_digest,
                    _corrective_policy=plan.policy_decision,
                    _corrective_predecessor_policy_id=(
                        plan.nonconforming_policy_decision_id
                    ),
                    _corrective_predecessor_policy_integrity_digest=(
                        plan.nonconforming_policy_integrity_digest
                    ),
                )
            finally:
                studio.close()
            if _fault_hook is not None:
                _fault_hook(_CorrectiveSuccessorFaultPoint.AFTER_QRI_APPEND)
            studio_snapshot_path = {
                "studio_profile_database": studio_location.profile_database,
            }
            _verify_forward_governance_regular_paths(
                studio_snapshot_path.values(), sqlite=True
            )
            snapshot_readers += _hold_forward_governance_source_snapshots(
                studio_snapshot_path
            )
            if (
                qri.profile_id != predecessor.profile_id
                or qri.predecessor_qualification_id != predecessor.qualification_id
                or qri.qualification_id == nonconforming.qualification_id
                or qri.provider_authority != _LOCAL_LLAMA_PROVIDER_AUTHORITY
            ):
                raise RuntimeHostFailedClosed(
                    "corrective-successor-qri-mismatch",
                    "published corrective QRI does not preserve its governed lineage",
                )
            binding_id = _corrective_binding_id(
                plan,
                profile_id=qri.profile_id,
                qualification_id=qri.qualification_id,
                binding_revision=predecessor.binding_revision + 1,
            )
            authority = _RuntimeBindingAuthority(
                authority_scope_id=str(
                    uuid5(NAMESPACE_URL, f"m0-12-authority-scope:{binding_id}")
                ),
                profile_id=qri.profile_id,
                timeline_id=target_timeline_id,
                allowed_intents=ALLOWED_INTENTS,
                allowed_provenance=ALLOWED_PROVENANCE,
                binding_id=binding_id,
                binding_revision=predecessor.binding_revision + 1,
                binding_epoch=predecessor.binding_epoch + 1,
                qualification_id=qri.qualification_id,
                qualification_revision=qri.qualification_revision,
                provider_authority=qri.provider_authority,
            )
            expected_timeline_root = _corrective_timeline_root_for_plan(plan)
            expected_timeline_root_hashes = _expected_corrective_root_hashes(
                plan,
                expected_timeline_root,
                authority,
            )
            _write_corrective_preparation_record(
                plan,
                qri,
                expected_timeline_root,
                expected_timeline_root_hashes,
            )
            if _fault_hook is not None:
                _fault_hook(
                    _CorrectiveSuccessorFaultPoint.AFTER_ROOT_COMMITMENT
                )
            timeline = TimelineEngine._create_bound(
                location.root,
                authority,
                root_kind=location.root_kind,
                _host_token=_HOST_TIMELINE_TOKEN,
                _reserved_identity=_ReservedTimelineIdentity(
                    root_id=expected_timeline_root.root_id,
                    control_store_id=expected_timeline_root.control_store_id,
                    timeline_store_id=expected_timeline_root.timeline_store_id,
                ),
                _created_at_us=plan.published_at_us,
            )
            try:
                gate_state, _epoch, basis, has_event = timeline._binding_health(
                    _host_token=_HOST_TIMELINE_TOKEN
                )
                if (
                    gate_state != "closed"
                    or has_event
                    or not _corrective_timeline_is_canonical_empty(
                        timeline._writer,
                        basis,
                    )
                ):
                    raise RuntimeHostFailedClosed(
                        "corrective-successor-timeline-invalid",
                        "prepared corrective Timeline is not closed and empty",
                    )
                timeline_root = timeline.location
            finally:
                timeline.close()
            _verify_corrective_preparation_record(
                location,
                timeline_root,
                qualification_id=qri.qualification_id,
                qri_integrity_digest=qri.integrity_digest,
                authority=authority,
                predecessor=predecessor,
                nonconforming=nonconforming,
                expected_plan=plan,
            )
            if _fault_hook is not None:
                _fault_hook(_CorrectiveSuccessorFaultPoint.AFTER_TIMELINE_ROOT)
            if timeline_root != expected_timeline_root:
                raise RuntimeHostFailedClosed(
                    "corrective-successor-timeline-invalid",
                    "prepared Timeline root is not the exact plan-derived identity",
                )
            prepared_timeline_paths = {
                "prepared_control_database": timeline_root.control_database,
                "prepared_timeline_database": timeline_root.timeline_database,
            }
            _verify_forward_governance_regular_paths(
                prepared_timeline_paths.values(), sqlite=True
            )
            snapshot_readers += _hold_forward_governance_source_snapshots(
                prepared_timeline_paths
            )
            writer = _connect_existing(location.control_database)
            try:
                _verify_control(location, studio_location, writer)
                verifier = object.__new__(cls)
                verifier._location = location
                verifier._studio_location = studio_location
                verifier._writer = writer
                existing = writer.execute(
                    f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
                    "WHERE binding_id = ?",
                    (binding_id,),
                ).fetchone()
                if existing is not None:
                    binding = verifier._binding_from_row(existing)
                    verifier._require_structural_binding_permit(binding)
                    if (
                        binding.timeline_root != expected_timeline_root
                        or not verifier._is_prepared_corrective_case(binding)
                    ):
                        raise RuntimeHostFailedClosed(
                            "corrective-successor-recovery-mismatch",
                            "existing corrective binding is not the exact prepared state",
                        )
                    fact_row = writer.execute(
                        "SELECT fact_id, fact_digest FROM branch_governance_fact "
                        "WHERE case_id = ? ORDER BY sequence DESC LIMIT 1",
                        (verifier._governance_case_id(binding.profile_id),),
                    ).fetchone()
                    if fact_row is None:
                        raise RuntimeHostFailedClosed(
                            "corrective-successor-recovery-mismatch",
                            "prepared successor has no governance fact",
                        )
                    _prepared_state = _corrective_timeline_state(binding)
                    lease_states = writer.execute(
                        "SELECT lease_state FROM runtime_instance_lease "
                        "WHERE binding_id IN (?, ?) ORDER BY binding_id",
                        (binding.binding_id, nonconforming.binding_id),
                    ).fetchall()
                    if (
                        _prepared_state[0] != "closed"
                        or _prepared_state[2].head_sequence != 0
                        or _prepared_state[3]
                        or not _prepared_state[5]
                        or len(lease_states) != 2
                        or any(str(row[0]) != "closed" for row in lease_states)
                    ):
                        raise RuntimeHostFailedClosed(
                            "corrective-successor-recovery-mismatch",
                            "prepared successor gate, head, or leases drifted",
                        )
                    return _CorrectiveSuccessorPreparationReceipt(
                        preparation_id=plan.preparation_id,
                        plan_digest=plan.plan_digest,
                        status="already-applied",
                        binding_id=binding.binding_id,
                        qualification_id=binding.qualification_id,
                        fact_id=str(fact_row[0]),
                        fact_digest=str(fact_row[1]),
                        predecessor_root_hashes_unchanged=(
                            _corrective_root_hashes(predecessor)
                            == predecessor_root_hashes_before
                        ),
                        nonconforming_root_hashes_unchanged=(
                            _corrective_root_hashes(nonconforming)
                            == nonconforming_root_hashes_before
                        ),
                        all_leases_closed=True,
                        new_timeline_root=binding.timeline_root,
                    )
                _begin(writer)
                _verify_control(location, studio_location, writer)
                locked_governance_facts = tuple(
                    tuple(row)
                    for row in writer.execute(
                        "SELECT * FROM branch_governance_fact "
                        "WHERE case_id = ? ORDER BY sequence",
                        (governance_case_id,),
                    ).fetchall()
                )
                locked_governance_members = tuple(
                    tuple(row)
                    for row in writer.execute(
                        "SELECT member.* FROM branch_governance_member AS member "
                        "JOIN branch_governance_fact AS fact "
                        "ON fact.fact_id = member.fact_id "
                        "WHERE fact.case_id = ? "
                        "ORDER BY fact.sequence, member.binding_id",
                        (governance_case_id,),
                    ).fetchall()
                )
                if (
                    locked_governance_facts != governance_facts_before
                    or locked_governance_members != governance_members_before
                ):
                    raise RuntimeHostConflict(
                        "corrective-successor-preimage-mismatch",
                        "governance ledger changed before the locked transition",
                    )
                locked_predecessor_row = writer.execute(
                    f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
                    "WHERE binding_id = ?",
                    (predecessor.binding_id,),
                ).fetchone()
                locked_nonconforming_row = writer.execute(
                    f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
                    "WHERE binding_id = ?",
                    (nonconforming.binding_id,),
                ).fetchone()
                if (
                    locked_predecessor_row is None
                    or locked_nonconforming_row is None
                    or verifier._binding_from_row(locked_predecessor_row) != predecessor
                    or verifier._binding_from_row(locked_nonconforming_row)
                    != nonconforming
                ):
                    raise RuntimeHostConflict(
                        "corrective-successor-preimage-mismatch",
                        "governed bindings changed before the locked transition",
                    )
                try:
                    verifier._require_structural_binding_permit(predecessor)
                except RuntimeHostRejected as error:
                    if error.code != "branch-serving-held":
                        raise
                locked_leases = writer.execute(
                    "SELECT binding_id, lease_state FROM runtime_instance_lease "
                    "WHERE binding_id IN (?, ?) ORDER BY binding_id",
                    (predecessor.binding_id, nonconforming.binding_id),
                ).fetchall()
                if len(locked_leases) != 2 or any(
                    str(row[1]) != "closed" for row in locked_leases
                ):
                    raise RuntimeHostConflict(
                        "corrective-successor-preimage-mismatch",
                        "a governed lease changed before the locked transition",
                    )
                if _fault_hook is not None:
                    _fault_hook(_CorrectiveSuccessorFaultPoint.AFTER_LOCKED_PREFLIGHT)
                now = plan.published_at_us
                writer.execute(
                    """
                    INSERT INTO runtime_authority_binding (
                        binding_id, binding_revision, binding_epoch, state,
                        profile_id, timeline_id, authority_scope_id,
                        qualification_id, qualification_revision,
                        qri_publication_key, qri_integrity_digest,
                        genesis_snapshot_id, knowledge_snapshot_id,
                        policy_decision_ids_json, capability_manifest_version,
                        provider_authority, runtime_kind, runtime_contract_version,
                        studio_root_id, studio_store_id, host_root_id,
                        host_control_store_id, timeline_root_json,
                        timeline_root_id, timeline_control_store_id,
                        timeline_store_id, predecessor_binding_id,
                        first_subject_event_sealed, created_at_us,
                        activated_at_us, retired_at_us
                    ) VALUES (?, ?, ?, 'validated', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, NULL, NULL)
                    """,
                    (
                        authority.binding_id, authority.binding_revision,
                        authority.binding_epoch, authority.profile_id,
                        authority.timeline_id, authority.authority_scope_id,
                        qri.qualification_id, qri.qualification_revision,
                        qri.publication_key, qri.integrity_digest,
                        qri.genesis_snapshot_id, qri.knowledge_snapshot_id,
                        _canonical_json(list(qri.policy_decision_ids)),
                        qri.capabilities.manifest_version, qri.provider_authority,
                        RUNTIME_KIND, RUNTIME_CONTRACT_VERSION,
                        studio_location.root_id, studio_location.profile_store_id,
                        location.root_id, location.control_store_id,
                        _canonical_json(timeline_root.to_dict()), timeline_root.root_id,
                        timeline_root.control_store_id, timeline_root.timeline_store_id,
                        predecessor.binding_id, now,
                    ),
                )
                retired = writer.execute(
                    """
                    UPDATE runtime_authority_binding
                    SET state = 'retired', retired_at_us = ?
                    WHERE binding_id = ? AND state = 'active'
                      AND first_subject_event_sealed = 0
                    """,
                    (now, predecessor.binding_id),
                )
                if retired.rowcount != 1:
                    raise RuntimeHostConflict(
                        "corrective-successor-preimage-mismatch",
                        "governed predecessor changed before corrective retirement",
                    )
                closed = writer.execute(
                    "UPDATE runtime_instance_lease SET lease_state = 'closed', "
                    "updated_at_us = ? WHERE binding_id = ? AND lease_state = 'closed'",
                    (now, predecessor.binding_id),
                )
                if closed.rowcount != 1:
                    raise RuntimeHostConflict(
                        "corrective-successor-preimage-mismatch",
                        "predecessor lease did not remain closed",
                    )
                activated = writer.execute(
                    "UPDATE runtime_authority_binding SET state = 'active', activated_at_us = ? "
                    "WHERE binding_id = ? AND state = 'validated'",
                    (now, authority.binding_id),
                )
                if activated.rowcount != 1:
                    raise RuntimeHostConflict(
                        "corrective-successor-activation-conflict",
                        "corrective binding was not uniquely activated",
                    )
                writer.execute(
                    """
                    INSERT INTO runtime_instance_lease (
                        binding_id, owner_pid, owner_instance_id, generation,
                        lease_state, updated_at_us
                    ) VALUES (?, ?, ?, 1, 'closed', ?)
                    """,
                    (authority.binding_id, 1, maintenance_id, now),
                )
                candidate_row = writer.execute(
                    f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
                    "WHERE binding_id = ?",
                    (authority.binding_id,),
                ).fetchone()
                if candidate_row is None:
                    raise RuntimeHostFailedClosed(
                        "binding-identity-mismatch",
                        "corrective binding disappeared before governance append",
                    )
                verifier._append_branch_governance_fact(
                    verifier._binding_from_row(candidate_row),
                    replaces=predecessor,
                    activation=_CORRECTIVE_SUCCESSOR_PREPARATION_AUTHORITY,
                    created_at_us=now,
                )
                fact_row = writer.execute(
                    "SELECT fact_id, fact_digest FROM branch_governance_fact "
                    "WHERE case_id = ? ORDER BY sequence DESC LIMIT 1",
                    (verifier._governance_case_id(qri.profile_id),),
                ).fetchone()
                if fact_row is None:
                    raise RuntimeHostFailedClosed(
                        "corrective-successor-postcondition-failed",
                        "corrective governance fact disappeared before commit",
                    )
                if _fault_hook is not None:
                    _fault_hook(_CorrectiveSuccessorFaultPoint.BEFORE_COMMIT)
                _commit(writer)
                if _fault_hook is not None:
                    _fault_hook(
                        _CorrectiveSuccessorFaultPoint.AFTER_COMMIT_BEFORE_RECEIPT
                    )
                candidate = verifier._binding_from_row(candidate_row)
                prepared_state = _corrective_timeline_state(candidate)
                final_leases = writer.execute(
                    "SELECT lease_state FROM runtime_instance_lease "
                    "WHERE binding_id IN (?, ?, ?) ORDER BY binding_id",
                    (
                        predecessor.binding_id,
                        nonconforming.binding_id,
                        candidate.binding_id,
                    ),
                ).fetchall()
                predecessor_unchanged = (
                    _corrective_root_hashes(predecessor)
                    == predecessor_root_hashes_before
                )
                nonconforming_unchanged = (
                    _corrective_root_hashes(nonconforming)
                    == nonconforming_root_hashes_before
                )
                all_leases_closed = len(final_leases) == 3 and all(
                    str(row[0]) == "closed" for row in final_leases
                )
                if (
                    not predecessor_unchanged
                    or not nonconforming_unchanged
                    or not all_leases_closed
                    or prepared_state[0] != "closed"
                    or prepared_state[2].head_sequence != 0
                    or prepared_state[3]
                    or not prepared_state[5]
                ):
                    raise RuntimeHostFailedClosed(
                        "corrective-successor-postcondition-failed",
                        "corrective successor postcondition did not verify",
                    )
                return _CorrectiveSuccessorPreparationReceipt(
                    preparation_id=plan.preparation_id,
                    plan_digest=plan.plan_digest,
                    status="applied",
                    binding_id=authority.binding_id,
                    qualification_id=qri.qualification_id,
                    fact_id=str(fact_row[0]),
                    fact_digest=str(fact_row[1]),
                    predecessor_root_hashes_unchanged=predecessor_unchanged,
                    nonconforming_root_hashes_unchanged=nonconforming_unchanged,
                    all_leases_closed=all_leases_closed,
                    new_timeline_root=timeline_root,
                )
            except Exception:
                _rollback_if_needed(writer)
                raise
            finally:
                writer.close()
        finally:
            for reader in snapshot_readers:
                try:
                    reader.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                reader.close()
            _release_process_registry(location.root_id, maintenance_id)

    def _require_prepared_corrective_case(
        self,
        bindings: tuple[RuntimeAuthorityBinding, ...],
    ) -> bool:
        profiles = {binding.profile_id for binding in bindings}
        prepared_profiles = {
            profile_id
            for profile_id in profiles
            if any(
                self._is_prepared_corrective_case(binding)
                for binding in bindings
                if binding.profile_id == profile_id
            )
        }
        if not prepared_profiles:
            return False
        if prepared_profiles != profiles or len(profiles) != 1:
            raise RuntimeHostFailedClosed(
                "branch-governance-transition-invalid",
                "a prepared corrective case cannot mask another active profile",
            )
        profile_bindings = tuple(
            binding
            for binding in bindings
            if binding.profile_id in prepared_profiles
        )
        if len(profile_bindings) != 2:
            raise RuntimeHostFailedClosed(
                "branch-governance-transition-invalid",
                "prepared corrective state requires exactly two active bindings",
            )
        prepared_binding = next(
            (
                binding
                for binding in profile_bindings
                if binding.predecessor_binding_id is not None
            ),
            None,
        )
        contained_binding = next(
            (
                binding
                for binding in profile_bindings
                if binding.predecessor_binding_id is None
            ),
            None,
        )
        if (
            prepared_binding is None
            or contained_binding is None
            or not contained_binding.first_subject_event_sealed
        ):
            raise RuntimeHostFailedClosed(
                "branch-governance-transition-invalid",
                "prepared corrective state has invalid active binding roles",
            )
        if prepared_binding.first_subject_event_sealed and (
            type(self._local_serving_authorization) is not _LocalServingAuthorization
            or not self._local_serving_authorization.matches_binding(
                self._location,
                prepared_binding,
            )
        ):
            raise RuntimeHostRejected(
                "branch-serving-authorization-required",
                "served corrective history requires its exact lifecycle authority",
            )
        for binding in profile_bindings:
            target, _members = self._require_structural_binding_permit(binding)
            if binding.predecessor_binding_id is None:
                if target["serving_disposition"] != _BRANCH_HELD:
                    raise RuntimeHostFailedClosed(
                        "branch-governance-transition-invalid",
                        "contained branch no longer has its held disposition",
                    )
            elif target["serving_disposition"] != _BRANCH_ELIGIBLE:
                raise RuntimeHostFailedClosed(
                    "branch-governance-transition-invalid",
                    "prepared successor is no longer the unique eligible member",
                )
            (
                state,
                _epoch,
                basis,
                has_event,
                _hashes,
                is_canonical_empty,
                is_canonical_one_cycle,
            ) = _corrective_timeline_state(binding)
            expected_head = 1 if binding.first_subject_event_sealed else 0
            if (
                state != "closed"
                or basis.head_sequence != expected_head
                or has_event != binding.first_subject_event_sealed
                or (
                    binding.predecessor_binding_id is not None
                    and not (
                        is_canonical_one_cycle
                        if binding.first_subject_event_sealed
                        else is_canonical_empty
                    )
                )
                or (
                    binding.predecessor_binding_id is None
                    and not is_canonical_one_cycle
                )
            ):
                raise RuntimeHostFailedClosed(
                    "corrective-successor-recovery-mismatch",
                    "prepared corrective Timeline health differs from its binding",
                )
            lease = self._writer.execute(
                "SELECT lease_state FROM runtime_instance_lease WHERE binding_id = ?",
                (binding.binding_id,),
            ).fetchone()
            if lease != ("closed",):
                raise RuntimeHostFailedClosed(
                    "corrective-successor-recovery-mismatch",
                    "prepared corrective binding does not have a closed lease",
                )
        predecessor_row = self._writer.execute(
            f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
            "WHERE binding_id = ?",
            (prepared_binding.predecessor_binding_id,),
        ).fetchone()
        if predecessor_row is None:
            raise RuntimeHostFailedClosed(
                "corrective-successor-recovery-mismatch",
                "prepared corrective predecessor is missing",
            )
        predecessor = self._binding_from_row(predecessor_row)
        if (
            predecessor.state is not BindingState.RETIRED
            or predecessor.profile_id != prepared_binding.profile_id
            or predecessor.timeline_id != prepared_binding.timeline_id
            or predecessor.first_subject_event_sealed
        ):
            raise RuntimeHostFailedClosed(
                "corrective-successor-recovery-mismatch",
                "prepared corrective predecessor identity or state drifted",
            )
        (
            state,
            _epoch,
            basis,
            has_event,
            _hashes,
            is_canonical_empty,
            _is_canonical_one_cycle,
        ) = _corrective_timeline_state(predecessor)
        predecessor_lease = self._writer.execute(
            "SELECT lease_state FROM runtime_instance_lease WHERE binding_id = ?",
            (predecessor.binding_id,),
        ).fetchone()
        if (
            state != "closed"
            or basis.head_sequence != 0
            or has_event
            or not is_canonical_empty
            or predecessor_lease != ("closed",)
        ):
            raise RuntimeHostFailedClosed(
                "corrective-successor-recovery-mismatch",
                "prepared corrective predecessor root or lease drifted",
            )
        return True

    @classmethod
    def _issue_corrective_successor_recovery_plan(
        cls,
        *,
        source_text_free_evidence: Mapping[str, object],
        activation_basis_evidence: Mapping[str, object],
        publication_key: str,
        published_at_us: int,
        policy_validity_us: int,
        _authority: object,
    ) -> _CorrectiveSuccessorRecoveryPlan:
        """Derive the entire recovery write plan from frozen structural evidence."""

        if (
            cls is not RuntimeHost
            or _authority is not _CORRECTIVE_SUCCESSOR_PREPARATION_AUTHORITY
        ):
            raise TypeError("corrective successor recovery planning requires private authority")
        if not isinstance(source_text_free_evidence, Mapping) or not isinstance(
            activation_basis_evidence, Mapping
        ):
            raise TypeError("corrective successor recovery planning requires mappings")
        evidence = dict(source_text_free_evidence)
        activation_basis = dict(activation_basis_evidence)
        commitment_source = activation_basis.get("activation_commitment")
        expected_activation_sources = {
            "post_m0_03_exit": {
                "path": (
                    ".scratch/mature-runtime-post-m0/POST-M0-03-EXIT-1.0.json"
                ),
                "sha256": (
                    "bb63520fee97907da2ec6e97dcb7d7262eb98138adeb146c13ea5db0173b2ad9"
                ),
            },
            "post_m0_03_exact_activation_preview_05": {
                "path": (
                    ".scratch/mature-runtime-post-m0/"
                    "POST-M0-03-HITL-PHASE-3-EXACT-EXECUTION-PREVIEW-05.json"
                ),
                "sha256": (
                    "40400c0491953016203c1c84b60c41e4880cbf48e37f30958c51e98bc6b6c6f1"
                ),
            },
            "phase_2_recovery_raw_09": {
                "path": (
                    ".scratch/mature-runtime-post-m0/POST-M0-06-PHASE-2-"
                    "SOURCE-TEXT-FREE-EXACT-STATE-RECOVERY-RAW-09.json"
                ),
                "sha256": (
                    "c50146c371108f0243173e6482090a398ff24c3e7fcc97040fbf72b41fb04d0a"
                ),
            },
            "phase_2_recovery_completion_09": {
                "path": (
                    ".scratch/mature-runtime-post-m0/POST-M0-06-PHASE-2-"
                    "SOURCE-TEXT-FREE-EXACT-STATE-RECOVERY-COMPLETION-09.json"
                ),
                "sha256": (
                    "9a1d5ba0af69e6ba0e743f85f2f753b5c8e89e7ea396594026b3f27cd213aaa5"
                ),
            },
        }
        if (
            activation_basis.get("status") != "frozen-source-text-free"
            or activation_basis.get("authority_access") != 0
            or activation_basis.get("authority_writes") != 0
            or activation_basis.get("sources") != expected_activation_sources
            or not isinstance(commitment_source, Mapping)
        ):
            raise RuntimeHostFailedClosed(
                "corrective-successor-evidence-invalid",
                "activation basis evidence is incomplete or not offline",
            )
        commitment = dict(commitment_source)
        expected_commitment_keys = {
            "artifact_id",
            "genesis_branch_id",
            "predecessor_policy_decision_id",
            "compatibility_proof_id",
            "compatibility_proof_integrity_digest",
        }
        if set(commitment) != expected_commitment_keys:
            raise RuntimeHostFailedClosed(
                "corrective-successor-evidence-invalid",
                "activation commitment has an unexpected shape",
            )
        for field in (
            "artifact_id",
            "genesis_branch_id",
            "predecessor_policy_decision_id",
            "compatibility_proof_id",
        ):
            commitment[field] = _canonical_uuid(str(commitment[field]), field)
        if not _is_sha256(str(commitment["compatibility_proof_integrity_digest"])):
            raise RuntimeHostFailedClosed(
                "corrective-successor-evidence-invalid",
                "activation commitment has an invalid proof digest",
            )
        if (
            evidence.get("passed") is not True
            or evidence.get("mismatches") != []
            or evidence.get("authority_writes") != 0
            or evidence.get("content_columns_read") != 0
            or evidence.get("runtime_host_or_model_starts") != 0
            or evidence.get("network_or_commands") != 0
        ):
            raise RuntimeHostFailedClosed(
                "corrective-successor-evidence-invalid",
                "Phase 2 structural evidence did not pass its zero-authority contract",
            )
        policy_rows = evidence.get("policy_decisions")
        if not isinstance(policy_rows, list) or len(policy_rows) != 1:
            raise RuntimeHostFailedClosed(
                "corrective-successor-evidence-invalid",
                "Phase 2 evidence must contain one NCE PolicyDecision",
            )
        policy_projection = policy_rows[0]
        if not isinstance(policy_projection, Mapping) or any(
            policy_projection.get(field) is not True
            for field in (
                "decision_id_matches_row",
                "integrity_valid",
                "production_verifier_valid",
                "nonconforming_binding_link_valid",
                "qri_policy_link_valid",
                "qri_integrity_prevalidated_by_consumed_phase3_failure",
            )
        ):
            raise RuntimeHostFailedClosed(
                "corrective-successor-evidence-invalid",
                "NCE PolicyDecision proof flags are incomplete",
            )
        nce_policy = _policy_decision_from_payload(policy_projection)
        if (
            nce_policy.disposition is not PolicyDisposition.QUALIFIED
            or nce_policy.capability_manifest
            != CapabilityManifest._local_llama_experimental()
        ):
            raise RuntimeHostFailedClosed(
                "corrective-successor-evidence-invalid",
                "NCE PolicyDecision is not the exact local llama capability",
            )
        profile = evidence.get("profile")
        host = evidence.get("host")
        files = evidence.get("files")
        root_identities = evidence.get("root_identities")
        if not all(
            isinstance(value, Mapping)
            for value in (profile, host, files, root_identities)
        ):
            raise RuntimeHostFailedClosed(
                "corrective-successor-evidence-invalid",
                "Phase 2 structural authority projection is incomplete",
            )
        host_manifest = host.get("manifest")
        profile_manifest = profile.get("manifest")
        predecessor_raw = host.get("predecessor")
        nonconforming_raw = host.get("successor")
        governance_facts = host.get("branch_governance_facts")
        if (
            not isinstance(host_manifest, (list, tuple))
            or len(host_manifest) != 9
            or not isinstance(profile_manifest, (list, tuple))
            or len(profile_manifest) != 8
            or not isinstance(predecessor_raw, Mapping)
            or not isinstance(nonconforming_raw, Mapping)
            or not isinstance(governance_facts, list)
            or len(governance_facts) != 1
            or not isinstance(governance_facts[0], (list, tuple))
            or len(governance_facts[0]) != 7
            or int(governance_facts[0][4]) != 1
            or governance_facts[0][5] is not None
            or not _is_sha256(str(governance_facts[0][6]))
        ):
            raise RuntimeHostFailedClosed(
                "corrective-successor-evidence-invalid",
                "Phase 2 Host/profile/governance projection is invalid",
            )

        def unchanged_digest(source: Mapping[str, object], name: str) -> str:
            item = source.get(name)
            if (
                not isinstance(item, Mapping)
                or item.get("unchanged") is not True
                or item.get("sha256_before") != item.get("sha256_after")
                or not _is_sha256(str(item.get("sha256_before", "")))
            ):
                raise RuntimeHostFailedClosed(
                    "corrective-successor-evidence-invalid",
                    f"{name} is not an unchanged exact-byte commitment",
                )
            return str(item["sha256_before"])

        def identity_root(name: str, expected_root_id: object) -> Path:
            item = root_identities.get(name)
            unchanged_digest(root_identities, name)
            if not isinstance(item, Mapping):
                raise RuntimeHostFailedClosed(
                    "corrective-successor-evidence-invalid",
                    f"{name} identity projection is absent",
                )
            path = Path(str(item.get("path", "")))
            if path.name != "root.identity" or path.parent.name != str(
                expected_root_id
            ):
                raise RuntimeHostFailedClosed(
                    "corrective-successor-evidence-invalid",
                    f"{name} identity path does not match its root id",
                )
            return path.parent

        host_root = identity_root("host", host_manifest[0])
        studio_root = identity_root("studio", profile_manifest[0])
        projected_root_kind = (
            HOST_ROOT_KIND
            if _is_relative_to(host_root, Path(tempfile.gettempdir()))
            else EXPERIMENTAL_ROOT_KIND
        )
        location = RuntimeHostRootRef(
            root_path=str(host_root),
            root_id=str(host_manifest[0]),
            control_store_id=str(host_manifest[1]),
            root_kind=projected_root_kind,
        )
        studio_location = StudioRootRef(
            root_path=str(studio_root),
            root_id=str(profile_manifest[0]),
            profile_store_id=str(profile_manifest[1]),
            root_kind=projected_root_kind,
        )
        if (
            host_manifest[2] != studio_location.root_id
            or host_manifest[3] != studio_location.profile_store_id
            or profile.get("profile_ids") != [predecessor_raw.get("profile_id")]
        ):
            raise RuntimeHostFailedClosed(
                "corrective-successor-evidence-invalid",
                "Host and Studio structural identities are not linked",
            )

        def evidence_binding(
            raw: Mapping[str, object],
            *,
            identity_name: str,
            policy_decision_id: str,
        ) -> RuntimeAuthorityBinding:
            root_path = identity_root(identity_name, raw.get("timeline_root_id"))
            return RuntimeAuthorityBinding.from_dict(
                {
                    **dict(raw),
                    "policy_decision_ids": [policy_decision_id],
                    "timeline_root": {
                        "root_path": str(root_path),
                        "root_id": raw["timeline_root_id"],
                        "control_store_id": raw["timeline_control_store_id"],
                        "timeline_store_id": raw["timeline_store_id"],
                        "timeline_id": raw["timeline_id"],
                        "root_kind": projected_root_kind,
                    },
                    "created_at_us": 1,
                    "activated_at_us": 1,
                    "retired_at_us": None,
                    "first_subject_event_sealed": bool(
                        raw["first_subject_event_sealed"]
                    ),
                }
            )

        predecessor = evidence_binding(
            predecessor_raw,
            identity_name="predecessor",
            policy_decision_id=str(commitment["predecessor_policy_decision_id"]),
        )
        nonconforming = evidence_binding(
            nonconforming_raw,
            identity_name="successor",
            policy_decision_id=nce_policy.decision_id,
        )
        qri_identity_rows = profile.get("qri_identities")
        if not isinstance(qri_identity_rows, list) or len(qri_identity_rows) != 2:
            raise RuntimeHostFailedClosed(
                "corrective-successor-evidence-invalid",
                "Phase 2 evidence does not contain the exact predecessor QRI pair",
            )
        qri_identities: dict[str, tuple[str, str]] = {}
        for row in qri_identity_rows:
            if not isinstance(row, Mapping) or set(row) != {
                "qualification_id",
                "publication_key",
                "integrity_digest",
            }:
                raise RuntimeHostFailedClosed(
                    "corrective-successor-evidence-invalid",
                    "Phase 2 evidence does not contain the exact predecessor QRI pair",
                )
            qualification_id = _canonical_uuid(
                str(row["qualification_id"]), "qualification_id"
            )
            if qualification_id in qri_identities or not _is_sha256(
                str(row["integrity_digest"])
            ):
                raise RuntimeHostFailedClosed(
                    "corrective-successor-evidence-invalid",
                    "Phase 2 evidence does not contain the exact predecessor QRI pair",
                )
            qri_identities[qualification_id] = (
                str(row["publication_key"]),
                str(row["integrity_digest"]),
            )
        expected_qri_identities = {
            predecessor.qualification_id: (
                predecessor.qri_publication_key,
                predecessor.qri_integrity_digest,
            ),
            nonconforming.qualification_id: (
                nonconforming.qri_publication_key,
                nonconforming.qri_integrity_digest,
            ),
        }
        if (
            predecessor.profile_id != nonconforming.profile_id
            or predecessor.timeline_id == nonconforming.timeline_id
            or predecessor.qualification_revision != 1
            or nonconforming.qualification_revision != 2
            or qri_identities != expected_qri_identities
        ):
            raise RuntimeHostFailedClosed(
                "corrective-successor-evidence-invalid",
                "the two held bindings are not the exact predecessor pair",
            )
        predecessor_root_sha256 = {
            "root_identity": unchanged_digest(root_identities, "predecessor"),
            "control_database": unchanged_digest(
                files, "predecessor_control_database"
            ),
            "timeline_database": unchanged_digest(
                files, "predecessor_timeline_database"
            ),
        }
        nonconforming_root_sha256 = {
            "root_identity": unchanged_digest(root_identities, "successor"),
            "control_database": unchanged_digest(
                files, "successor_control_database"
            ),
            "timeline_database": unchanged_digest(
                files, "successor_timeline_database"
            ),
        }
        authority_preimage_sha256 = {
            "studio_root_identity": unchanged_digest(root_identities, "studio"),
            "studio_profile_database": unchanged_digest(files, "profile_database"),
            "host_root_identity": unchanged_digest(root_identities, "host"),
            "host_control_database": unchanged_digest(files, "host_database"),
        }
        policy = _issue_corrective_policy_decision(
            nce_policy,
            issued_at_us=published_at_us,
            validity_us=policy_validity_us,
            _authority=_CORRECTIVE_LOCAL_LLAMA_SUCCESSOR_AUTHORITY,
        )
        plan = cls._issue_corrective_successor_preparation_plan(
            location=location,
            studio_location=studio_location,
            artifact_id=str(commitment["artifact_id"]),
            predecessor_qualification_id=predecessor.qualification_id,
            nonconforming_qualification_id=nonconforming.qualification_id,
            nonconforming_policy_decision_id=nce_policy.decision_id,
            nonconforming_policy_integrity_digest=nce_policy.integrity_digest,
            target_timeline_id=predecessor.timeline_id,
            policy_decision_id=policy.decision_id,
            policy_decision=policy,
            publication_key=publication_key,
            published_at_us=published_at_us,
            predecessor_root_sha256=predecessor_root_sha256,
            nonconforming_root_sha256=nonconforming_root_sha256,
            authority_preimage_sha256=authority_preimage_sha256,
            _authority=_authority,
        )
        projection = _corrective_successor_write_projection(
            plan,
            profile_id=predecessor.profile_id,
            genesis_branch_id=str(commitment["genesis_branch_id"]),
            genesis_snapshot_id=predecessor.genesis_snapshot_id,
            knowledge_snapshot_id=predecessor.knowledge_snapshot_id,
            predecessor_policy_decision_id=str(
                commitment["predecessor_policy_decision_id"]
            ),
            predecessor_qri_integrity_digest=predecessor.qri_integrity_digest,
            compatibility_proof_id=str(commitment["compatibility_proof_id"]),
            compatibility_proof_integrity_digest=str(
                commitment["compatibility_proof_integrity_digest"]
            ),
            predecessor_binding=predecessor,
            nonconforming_binding=nonconforming,
            previous_fact_digest=str(governance_facts[0][6]),
            _authority=_authority,
        )
        return _CorrectiveSuccessorRecoveryPlan._issue(
            plan=plan,
            nce_policy=nce_policy,
            source_text_free_evidence=evidence,
            activation_commitment=activation_basis,
            write_projection=projection,
            _authority=_authority,
        )

    @classmethod
    def _issue_corrective_successor_plan_and_projection(
        cls,
        *,
        location: Mapping[str, object],
        studio_location: Mapping[str, object],
        artifact_id: str,
        predecessor_qualification_id: str,
        nonconforming_qualification_id: str,
        nonconforming_policy_decision_id: str,
        nonconforming_policy_integrity_digest: str,
        nonconforming_policy_question_digest: str,
        target_timeline_id: str,
        publication_key: str,
        published_at_us: int,
        policy_validity_us: int,
        predecessor_root_sha256: Mapping[str, str],
        nonconforming_root_sha256: Mapping[str, str],
        authority_preimage_sha256: Mapping[str, str],
        profile_id: str,
        genesis_branch_id: str,
        genesis_snapshot_id: str,
        knowledge_snapshot_id: str,
        predecessor_policy_decision_id: str,
        predecessor_qri_integrity_digest: str,
        compatibility_proof_id: str,
        compatibility_proof_integrity_digest: str,
        source_text_free_evidence: Mapping[str, object],
        previous_fact_digest: str,
        _authority: object,
    ) -> tuple[_CorrectiveSuccessorPreparationPlan, dict[str, object]]:
        """Single frozen Host seam for Phase-06 planning and projection."""

        if cls is not RuntimeHost or _authority is not _CORRECTIVE_SUCCESSOR_PREPARATION_AUTHORITY:
            raise TypeError("corrective successor planning requires private authority")
        host_ref = RuntimeHostRootRef.from_dict(location)
        studio_ref = StudioRootRef.from_dict(studio_location)
        evidence_host = source_text_free_evidence.get("host")
        evidence_identities = source_text_free_evidence.get("root_identities")
        if (
            source_text_free_evidence.get("passed") is not True
            or source_text_free_evidence.get("mismatches") != []
            or not isinstance(evidence_host, Mapping)
            or not isinstance(evidence_identities, Mapping)
        ):
            raise RuntimeHostFailedClosed(
                "corrective-successor-evidence-invalid",
                "source-text-free Phase 2 evidence is incomplete or did not pass",
            )
        predecessor_evidence = evidence_host.get("predecessor")
        nonconforming_evidence = evidence_host.get("successor")
        predecessor_identity = evidence_identities.get("predecessor")
        nonconforming_identity = evidence_identities.get("successor")
        if not all(
            isinstance(value, Mapping)
            for value in (
                predecessor_evidence,
                nonconforming_evidence,
                predecessor_identity,
                nonconforming_identity,
            )
        ):
            raise RuntimeHostFailedClosed(
                "corrective-successor-evidence-invalid",
                "source-text-free Phase 2 binding projection is incomplete",
            )

        def evidence_binding(
            raw: Mapping[str, object],
            identity: Mapping[str, object],
            *,
            policy_decision_id: str,
            first_subject_event_sealed: bool,
        ) -> RuntimeAuthorityBinding:
            root_path = Path(str(identity.get("path", ""))).parent
            return RuntimeAuthorityBinding.from_dict(
                {
                    **dict(raw),
                    "policy_decision_ids": [policy_decision_id],
                    "timeline_root": {
                        "root_path": str(root_path),
                        "root_id": raw["timeline_root_id"],
                        "control_store_id": raw["timeline_control_store_id"],
                        "timeline_store_id": raw["timeline_store_id"],
                        "timeline_id": raw["timeline_id"],
                        "root_kind": host_ref.root_kind,
                    },
                    "created_at_us": 1,
                    "activated_at_us": 1,
                    "retired_at_us": None,
                    "first_subject_event_sealed": first_subject_event_sealed,
                }
            )

        predecessor_binding = evidence_binding(
            predecessor_evidence,
            predecessor_identity,
            policy_decision_id=predecessor_policy_decision_id,
            first_subject_event_sealed=False,
        )
        nonconforming_binding = evidence_binding(
            nonconforming_evidence,
            nonconforming_identity,
            policy_decision_id=nonconforming_policy_decision_id,
            first_subject_event_sealed=True,
        )
        predecessor_policy = PolicyDecision._issue(
            decision_id=nonconforming_policy_decision_id,
            disposition=PolicyDisposition.QUALIFIED,
            reason_codes=("local-llama-qualified",),
            policy_version="m0-host-policy-1.0",
            question_digest=nonconforming_policy_question_digest,
            issued_at_us=1,
            valid_until_us=2,
            capability_manifest=CapabilityManifest._local_llama_experimental(),
            integrity_digest=nonconforming_policy_integrity_digest,
        )
        policy = _issue_corrective_policy_decision(
            predecessor_policy,
            issued_at_us=published_at_us,
            validity_us=policy_validity_us,
            _authority=_CORRECTIVE_LOCAL_LLAMA_SUCCESSOR_AUTHORITY,
        )
        plan = cls._issue_corrective_successor_preparation_plan(
            location=host_ref,
            studio_location=studio_ref,
            artifact_id=artifact_id,
            predecessor_qualification_id=predecessor_qualification_id,
            nonconforming_qualification_id=nonconforming_qualification_id,
            nonconforming_policy_decision_id=nonconforming_policy_decision_id,
            nonconforming_policy_integrity_digest=nonconforming_policy_integrity_digest,
            target_timeline_id=target_timeline_id,
            policy_decision_id=policy.decision_id,
            policy_decision=policy,
            publication_key=publication_key,
            published_at_us=published_at_us,
            predecessor_root_sha256=predecessor_root_sha256,
            nonconforming_root_sha256=nonconforming_root_sha256,
            authority_preimage_sha256=authority_preimage_sha256,
            _authority=_authority,
        )
        projection = _corrective_successor_write_projection(
            plan,
            profile_id=profile_id,
            genesis_branch_id=genesis_branch_id,
            genesis_snapshot_id=genesis_snapshot_id,
            knowledge_snapshot_id=knowledge_snapshot_id,
            predecessor_policy_decision_id=predecessor_policy_decision_id,
            predecessor_qri_integrity_digest=predecessor_qri_integrity_digest,
            compatibility_proof_id=compatibility_proof_id,
            compatibility_proof_integrity_digest=compatibility_proof_integrity_digest,
            predecessor_binding=predecessor_binding,
            nonconforming_binding=nonconforming_binding,
            previous_fact_digest=previous_fact_digest,
            _authority=_authority,
        )
        return plan, projection

    @classmethod
    def _issue_corrective_successor_preparation_plan(
        cls,
        *,
        location: RuntimeHostRootRef,
        studio_location: StudioRootRef,
        artifact_id: str,
        predecessor_qualification_id: str,
        nonconforming_qualification_id: str,
        nonconforming_policy_decision_id: str | None = None,
        nonconforming_policy_integrity_digest: str | None = None,
        target_timeline_id: str,
        policy_decision_id: str | None = None,
        policy_decision: PolicyDecision | None = None,
        publication_key: str,
        published_at_us: int,
        predecessor_root_sha256: Mapping[str, str] | None = None,
        nonconforming_root_sha256: Mapping[str, str] | None = None,
        authority_preimage_sha256: Mapping[str, str] | None = None,
        _authority: object,
    ) -> _CorrectiveSuccessorPreparationPlan:
        if cls is not RuntimeHost:
            raise TypeError("corrective successor plan requires RuntimeHost")
        explicit_policy_id = policy_decision_id is not None
        if (
            policy_decision is None
            or nonconforming_policy_decision_id is None
            or nonconforming_policy_integrity_digest is None
        ):
            studio = SubjectStudio.open(
                studio_location,
                policy_kernel=PolicyKernel(clock=lambda: published_at_us),
            )
            try:
                nonconforming_qri = studio._query_qri_by_qualification_id(
                    nonconforming_qualification_id
                )
                if nonconforming_qri.qualification_id != nonconforming_qualification_id:
                    raise RuntimeHostFailedClosed(
                        "corrective-successor-preimage-mismatch",
                        "nonconforming QRI identity changed before plan issue",
                    )
                if len(nonconforming_qri.policy_decision_ids) != 1:
                    raise RuntimeHostFailedClosed(
                        "corrective-successor-preimage-mismatch",
                        "nonconforming QRI policy projection is not singular",
                    )
                predecessor_policy = studio._read_policy_decision(
                    nonconforming_qri.policy_decision_ids[0]
                )
                nonconforming_policy_decision_id = predecessor_policy.decision_id
                nonconforming_policy_integrity_digest = (
                    predecessor_policy.integrity_digest
                )
                if policy_decision_id is not None:
                    policy_decision = studio._read_policy_decision(
                        policy_decision_id
                    )
                else:
                    policy_decision = _issue_corrective_policy_decision(
                        predecessor_policy,
                        issued_at_us=published_at_us,
                        validity_us=60_000_000,
                        _authority=_CORRECTIVE_LOCAL_LLAMA_SUCCESSOR_AUTHORITY,
                    )
            finally:
                studio.close()
        elif not explicit_policy_id and policy_decision.reason_codes != (
            "post-m0-06-corrective-local-llama-qualified",
        ):
            policy_decision = _issue_corrective_policy_decision(
                policy_decision,
                issued_at_us=published_at_us,
                validity_us=max(
                    1,
                    policy_decision.valid_until_us - policy_decision.issued_at_us,
                ),
                _authority=_CORRECTIVE_LOCAL_LLAMA_SUCCESSOR_AUTHORITY,
            )
            policy_decision_id = policy_decision.decision_id
        if policy_decision_id is None:
            policy_decision_id = policy_decision.decision_id
        if predecessor_root_sha256 is None or nonconforming_root_sha256 is None:
            writer = _connect_existing(location.control_database)
            try:
                _verify_control(location, studio_location, writer)
                verifier = object.__new__(cls)
                verifier._location = location
                verifier._studio_location = studio_location
                verifier._writer = writer
                predecessor_row = writer.execute(
                    f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
                    "WHERE qualification_id = ?",
                    (predecessor_qualification_id,),
                ).fetchone()
                nonconforming_row = writer.execute(
                    f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
                    "WHERE qualification_id = ?",
                    (nonconforming_qualification_id,),
                ).fetchone()
                if predecessor_row is None or nonconforming_row is None:
                    raise RuntimeHostFailedClosed(
                        "corrective-successor-preimage-mismatch",
                        "corrective plan source bindings are absent",
                    )
                predecessor = verifier._binding_from_row(predecessor_row)
                nonconforming = verifier._binding_from_row(nonconforming_row)
                predecessor_root_sha256 = _corrective_root_hashes(predecessor)
                nonconforming_root_sha256 = _corrective_root_hashes(nonconforming)
            finally:
                writer.close()
        if authority_preimage_sha256 is None:
            authority_preimage_sha256 = {
                "studio_root_identity": _file_sha256(
                    studio_location.root / "root.identity"
                ),
                "studio_profile_database": _file_sha256(
                    studio_location.profile_database
                ),
                "host_root_identity": _file_sha256(
                    location.root / "root.identity"
                ),
                "host_control_database": _file_sha256(
                    location.control_database
                ),
            }
        return _CorrectiveSuccessorPreparationPlan._issue(
            location=location,
            studio_location=studio_location,
            artifact_id=artifact_id,
            predecessor_qualification_id=predecessor_qualification_id,
            nonconforming_qualification_id=nonconforming_qualification_id,
            nonconforming_policy_decision_id=nonconforming_policy_decision_id,
            nonconforming_policy_integrity_digest=(
                nonconforming_policy_integrity_digest
            ),
            target_timeline_id=target_timeline_id,
            policy_decision_id=policy_decision_id,
            policy_decision=policy_decision,
            publication_key=publication_key,
            published_at_us=published_at_us,
            predecessor_root_sha256=predecessor_root_sha256,
            nonconforming_root_sha256=nonconforming_root_sha256,
            authority_preimage_sha256=authority_preimage_sha256,
            _authority=_authority,
        )

    @classmethod
    def open(
        cls,
        location: RuntimeHostRootRef,
        *,
        studio_location: StudioRootRef,
        cognition: CognitionEngine | None,
        _cognition_assembly: _CognitionAssembly | None = None,
        _fault_hook: Callable[[RuntimeHostFaultPoint], None] | None = None,
        _runtime_interrupt_at: RuntimeFaultPoint | None = None,
        _runtime_fault_hook: (
            Callable[[RuntimeFaultPoint, OperationRef], None] | None
        ) = None,
        _local_serving_authorization: _LocalServingAuthorization | None = None,
        relationship_enabled: bool = False,
        _runtime_identity: RuntimeIdentityProjection | None = None,
    ) -> RuntimeHost:
        if not isinstance(location, RuntimeHostRootRef):
            raise TypeError("RuntimeHost.open requires RuntimeHostRootRef")
        if not isinstance(studio_location, StudioRootRef):
            raise TypeError("RuntimeHost.open requires StudioRootRef")
        if _fault_hook is not None and not callable(_fault_hook):
            raise TypeError("_fault_hook must be callable")
        if _runtime_interrupt_at is not None and not isinstance(
            _runtime_interrupt_at,
            RuntimeFaultPoint,
        ):
            raise TypeError("_runtime_interrupt_at must be RuntimeFaultPoint")
        if _runtime_fault_hook is not None and not callable(_runtime_fault_hook):
            raise TypeError("_runtime_fault_hook must be callable")
        if (
            _local_serving_authorization is not None
            and type(_local_serving_authorization) is not _LocalServingAuthorization
        ):
            raise TypeError("local serving authorization must be exact")
        _validate_existing_root(
            location.root,
            location.root_id,
            root_kind=location.root_kind,
            studio_location=studio_location,
        )
        _read_root_identity(location, studio_location)
        instance_id = str(uuid4())
        _claim_process_registry(location.root_id, instance_id)
        writer: sqlite3.Connection | None = None
        try:
            writer = _connect_existing(location.control_database)
            _verify_control(location, studio_location, writer)
            control_only_assembly = _CognitionAssembly._prepared_control_only()
            host = cls(
                location,
                studio_location,
                writer,
                control_only_assembly,
                fault_hook=_fault_hook,
                runtime_interrupt_at=_runtime_interrupt_at,
                runtime_fault_hook=_runtime_fault_hook,
                instance_id=instance_id,
                runtime_identity=_runtime_identity,
            )
            host._local_serving_authorization = _local_serving_authorization
            host._relationship_enabled = relationship_enabled
            active_rows = writer.execute(
                f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
                "WHERE state = 'active' ORDER BY profile_id, timeline_id"
            ).fetchall()
            active_bindings = tuple(
                host._binding_from_row(row) for row in active_rows
            )
            if host._require_prepared_corrective_case(active_bindings):
                if _local_serving_authorization is not None:
                    if not any(
                        _local_serving_authorization.matches_binding(
                            location,
                            binding,
                        )
                        for binding in active_bindings
                    ):
                        raise RuntimeHostRejected(
                            "branch-serving-authorization-required",
                            "prepared corrective eligibility is not lifecycle authority",
                        )
                    if cognition is None or not _cognition_contract_supported(cognition):
                        raise TypeError(
                            "authorized local serving requires matching CognitionEngine"
                        )
                    cognition_assembly = (
                        _CognitionAssembly._single(cognition)
                        if _cognition_assembly is None
                        else _cognition_assembly
                    )
                    if type(cognition_assembly) is not _CognitionAssembly or not (
                        cognition_assembly.accepts_bootstrap(cognition)
                    ):
                        raise RuntimeHostRejected(
                            "cognition-assembly-mismatch",
                            "private cognition assembly does not accept bootstrap adapter",
                        )
                    host._cognition_assembly = cognition_assembly
                return host
            if cognition is None or not _cognition_contract_supported(cognition):
                raise TypeError(
                    "RuntimeHost requires a CognitionEngine matching QRI authority"
                )
            cognition_assembly = (
                _CognitionAssembly._single(cognition)
                if _cognition_assembly is None
                else _cognition_assembly
            )
            if type(cognition_assembly) is not _CognitionAssembly or not (
                cognition_assembly.accepts_bootstrap(cognition)
            ):
                raise RuntimeHostRejected(
                    "cognition-assembly-mismatch",
                    "private cognition assembly does not accept the bootstrap adapter",
                )
            host._cognition_assembly = cognition_assembly
            host._recover_active_bindings()
            return host
        except Exception:
            if writer is not None:
                try:
                    writer.execute(
                        """
                        UPDATE runtime_instance_lease
                        SET lease_state = 'closed', updated_at_us = ?
                        WHERE owner_instance_id = ? AND lease_state = 'active'
                        """,
                        (_utc_microseconds(), instance_id),
                    )
                except sqlite3.Error:
                    _rollback_if_needed(writer)
                writer.close()
            _release_process_registry(location.root_id, instance_id)
            raise

    @classmethod
    def _issue_local_serving_authorization_test(
        cls,
        location: RuntimeHostRootRef,
        *,
        studio_location: StudioRootRef,
        qri: QualifiedRuntimeInput,
        timeline_id: str,
        entry_contract_sha256: str,
        cognition_assembly: _CognitionAssembly,
    ) -> _LocalServingAuthorization:
        """Issue a temporary-root serving authorization for Post-M0 08 TDD."""

        if location.root_kind != HOST_ROOT_KIND or studio_location.root_kind != HOST_ROOT_KIND:
            raise RuntimeHostRejected(
                "local-serving-authorization-unavailable",
                "test serving authorization accepts only temporary test roots",
            )
        timeline_id = _canonical_uuid(timeline_id, "timeline_id")
        studio = SubjectStudio.open(studio_location, policy_kernel=PolicyKernel())
        try:
            canonical = studio.query_qri(publication_key=qri.publication_key)
        finally:
            studio.close()
        if canonical != qri:
            raise RuntimeHostRejected(
                "local-serving-authorization-mismatch",
                "serving authorization requires the canonical published QRI",
            )
        host = cls.open(
            location,
            studio_location=studio_location,
            cognition=None,
        )
        try:
            binding = host.query_binding(
                profile_id=qri.profile_id,
                timeline_id=timeline_id,
            )
            if not host._is_prepared_corrective_case(binding):
                raise RuntimeHostRejected(
                    "local-serving-authorization-unavailable",
                    "only the exact prepared corrective successor may be authorized",
                )
            target, _members = host._require_structural_binding_permit(binding)
            if target["serving_disposition"] != _BRANCH_ELIGIBLE:
                raise RuntimeHostRejected(
                    "local-serving-authorization-unavailable",
                    "prepared successor is not the unique eligible member",
                )
            cognition_plan_digest = cognition_assembly._local_serving_plan_digest(
                qri,
                binding,
            )
            return _LocalServingAuthorization._issue(
                location=location,
                binding=binding,
                qri=qri,
                entry_contract_sha256=entry_contract_sha256,
                preparation_record_sha256=_file_sha256(
                    _corrective_preparation_record_path(
                        location,
                        binding.timeline_root,
                    )
                ),
                cognition_plan_digest=cognition_plan_digest,
                _authority=_LOCAL_SERVING_AUTHORITY_TOKEN,
            )
        finally:
            host.close()

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeHostRejected("host-closed", "RuntimeHost is closed")

    def _hit(self, point: RuntimeHostFaultPoint) -> None:
        if self._fault_hook is not None:
            try:
                self._fault_hook(point)
            except RuntimeHostProblem:
                raise
            except Exception as error:
                if point in {
                    RuntimeHostFaultPoint.AFTER_CONTROL_ACTIVATION,
                    RuntimeHostFaultPoint.AFTER_TIMELINE_GATE_OPEN,
                    RuntimeHostFaultPoint.AFTER_LANE_INSTALL,
                    RuntimeHostFaultPoint.AFTER_RETIRE_GATE_CLOSED,
                }:
                    raise RuntimeHostInterrupted(point) from error
                raise

    def _verify_published_qri(
        self,
        qri: QualifiedRuntimeInput,
    ) -> QualifiedRuntimeInput:
        if type(qri) is not QualifiedRuntimeInput:
            raise RuntimeHostRejected(
                "published-qri-required",
                "RuntimeHost accepts only a SubjectStudio-published QRI",
            )
        studio = SubjectStudio.open(
            self._studio_location,
            policy_kernel=PolicyKernel(),
        )
        try:
            canonical = studio.query_qri(publication_key=qri.publication_key)
        except Exception as error:
            raise RuntimeHostFailedClosed(
                "qri-publication-unavailable",
                "published QRI could not be verified from its ProfileStore",
            ) from error
        finally:
            studio.close()
        if canonical != qri:
            raise RuntimeHostRejected(
                "qri-identity-mismatch",
                "supplied QRI does not match its canonical publication",
            )
        if (
            canonical.qualification_revision < 1
            or canonical.isolation_proof.root_id != self._studio_location.root_id
            or not _qri_provider_contract_matches(canonical)
            or self._cognition_assembly.single_provider_mismatch(canonical)
        ):
            raise RuntimeHostRejected(
                "qri-authority-incompatible",
                "QRI proof bundle is incompatible with the M0 RuntimeHost",
            )
        self._cognition_assembly.select(canonical)
        return canonical

    def open_runtime(
        self,
        qri: QualifiedRuntimeInput,
        *,
        timeline_id: str,
        _activation_plan: _HostActivationPlan | None = None,
        _local_serving_authorization: _LocalServingAuthorization | None = None,
        _serving_cognition_assembly: _CognitionAssembly | None = None,
    ) -> RuntimeRoute:
        with self._state_lock:
            return self._open_runtime_locked(
                qri,
                timeline_id=timeline_id,
                _activation_plan=_activation_plan,
                _local_serving_authorization=_local_serving_authorization,
                _serving_cognition_assembly=_serving_cognition_assembly,
            )

    def _open_runtime_locked(
        self,
        qri: QualifiedRuntimeInput,
        *,
        timeline_id: str,
        _activation_plan: _HostActivationPlan | None,
        _local_serving_authorization: _LocalServingAuthorization | None,
        _serving_cognition_assembly: _CognitionAssembly | None,
    ) -> RuntimeRoute:
        self._require_open()
        timeline_id = _canonical_uuid(timeline_id, "timeline_id")
        local_serving_assembly: _CognitionAssembly | None = None
        if type(qri) is QualifiedRuntimeInput:
            prepared = self._select_active_binding(qri.profile_id, timeline_id)
            if prepared is not None and (
                prepared.qualification_id == qri.qualification_id
                and prepared.qri_integrity_digest == qri.integrity_digest
                and self._is_prepared_corrective_case(prepared)
            ):
                target, _members = self._require_structural_binding_permit(prepared)
                if target["serving_disposition"] == _BRANCH_HELD:
                    raise RuntimeHostRejected(
                        "branch-serving-held",
                        "contained nonconforming branch has no serving permit",
                    )
                if type(_serving_cognition_assembly) is not _CognitionAssembly:
                    raise RuntimeHostRejected(
                        "branch-serving-authorization-required",
                        "prepared corrective eligibility lacks a cognition plan",
                    )
                cognition_plan_digest = (
                    _serving_cognition_assembly._local_serving_plan_digest(
                        qri,
                        prepared,
                    )
                )
                if (
                    type(_local_serving_authorization)
                    is not _LocalServingAuthorization
                    or not _local_serving_authorization.matches(
                        self._location,
                        prepared,
                        qri,
                        cognition_plan_digest,
                    )
                    or _serving_cognition_assembly.submission_authorization(
                        qri,
                        prepared,
                    )
                    is None
                ):
                    raise RuntimeHostRejected(
                        "branch-serving-authorization-required",
                        "prepared corrective eligibility is not serving authority",
                    )
                local_serving_assembly = _serving_cognition_assembly
                self._cognition_assembly = _serving_cognition_assembly
                self._local_serving_authorization = _local_serving_authorization
        canonical = self._verify_published_qri(qri)
        self._require_governed_timeline_lineage(canonical, timeline_id=timeline_id)
        if local_serving_assembly is not None:
            try:
                local_serving_assembly._preflight_local_serving_plan(
                    canonical,
                    prepared,
                )
            except Exception as error:
                raise RuntimeHostFailedClosed(
                    "local-serving-plan-preflight-failed",
                    "local runner/model plan failed verification before gate open",
                ) from error
        if _activation_plan is not None:
            self._validate_activation_plan(
                canonical,
                timeline_id=timeline_id,
                plan=_activation_plan,
            )
        key = (canonical.profile_id, timeline_id)
        with self._state_lock:
            active = self._select_active_binding(*key)
            if active is not None:
                if (
                    active.qualification_id != canonical.qualification_id
                    or active.qri_integrity_digest != canonical.integrity_digest
                ):
                    return self._swap_before_first_event(active, canonical)
                if _activation_plan is not None and (
                    active.binding_id != _activation_plan.binding_id
                    or active.authority_scope_id
                    != _activation_plan.authority_scope_id
                    or active.timeline_root.root_id
                    != _activation_plan.timeline_identity.root_id
                    or active.timeline_root.control_store_id
                    != _activation_plan.timeline_identity.control_store_id
                    or active.timeline_root.timeline_store_id
                    != _activation_plan.timeline_identity.timeline_store_id
                ):
                    raise RuntimeHostRejected(
                        "activation-plan-mismatch",
                        "active lane differs from the reserved activation identities",
                    )
                lane = self._lanes.get(key)
                if lane is None or not lane.accepting:
                    lane = self._rebuild_lane(active, canonical)
                    if lane is None:
                        raise RuntimeHostRejected(
                            "binding-retired",
                            "Timeline gate completed retirement during recovery",
                        )
                return self._route(active, lane)
            return self._activate_first_binding(
                canonical,
                timeline_id,
                activation_plan=_activation_plan,
                _governance_activation=_NORMAL_GOVERNANCE_ACTIVATION,
            )

    def _require_local_serving_plan(
        self,
        qri: QualifiedRuntimeInput,
        binding: RuntimeAuthorityBinding,
        *,
        authorization: _LocalServingAuthorization,
        cognition_assembly: _CognitionAssembly,
    ) -> None:
        cognition_plan_digest = cognition_assembly._local_serving_plan_digest(
            qri,
            binding,
        )
        if not authorization.matches(
            self._location,
            binding,
            qri,
            cognition_plan_digest,
        ):
            raise RuntimeHostRejected(
                "branch-serving-authorization-required",
                "prepared corrective eligibility is not the exact cognition plan",
            )

    def _test_seed_nonconforming_held_branch(
        self,
        qri: QualifiedRuntimeInput,
        *,
        timeline_id: str,
        historical_command: SubjectCommand | None = None,
        historical_idempotency_key: str | None = None,
    ) -> None:
        """Temporary-root-only fixture seam for recovery fail-closed tests."""

        self._require_open()
        if self._location.root_kind != HOST_ROOT_KIND:
            raise RuntimeHostRejected(
                "test-governance-seed-not-allowed",
                "held branch fixtures are limited to fresh test RuntimeHost roots",
            )
        canonical = self._verify_published_qri(qri)
        timeline_id = _canonical_uuid(timeline_id, "timeline_id")
        predecessor_id = canonical.predecessor_qualification_id
        if predecessor_id is None:
            raise RuntimeHostRejected(
                "test-governance-seed-invalid",
                "held nonconforming fixture requires a successor QRI",
            )
        rows = self._writer.execute(
            f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
            "WHERE profile_id = ? AND qualification_id = ? AND state = 'active'",
            (canonical.profile_id, predecessor_id),
        ).fetchall()
        if not rows or all(
            self._binding_from_row(row).timeline_id == timeline_id for row in rows
        ):
            raise RuntimeHostRejected(
                "test-governance-seed-invalid",
                "held fixture must cross an active predecessor Timeline",
            )
        try:
            self._activate_first_binding(
                canonical,
                timeline_id,
                _governance_activation=_TEST_HELD_GOVERNANCE_ACTIVATION,
            )
        except RuntimeHostRejected as error:
            if error.code not in {
                "nonconforming-experimental-branch",
                "branch-serving-held",
            }:
                raise
            lane = self._lanes.pop((canonical.profile_id, timeline_id), None)
            if lane is None:
                raise RuntimeHostFailedClosed(
                    "test-governance-seed-incomplete",
                    "held fixture did not produce the expected closed lane",
                ) from error
            if (historical_command is None) != (
                historical_idempotency_key is None
            ):
                lane.worker.close()
                raise TypeError(
                    "historical held fixture requires both command and idempotency key"
                )
            if historical_command is not None:
                if type(historical_command) is not SubjectCommand:
                    lane.worker.close()
                    raise TypeError("historical held fixture requires SubjectCommand")
                lane.worker.call(
                    "_activate_binding_gate",
                    _host_token=_HOST_RUNTIME_TOKEN,
                )
                try:
                    result = lane.worker.call(
                        "execute",
                        historical_command,
                        idempotency_key=historical_idempotency_key,
                    )
                    if result.outcome is None:
                        raise RuntimeHostFailedClosed(
                            "test-governance-seed-incomplete",
                            "historical held fixture did not publish one canonical cycle",
                        )
                    self._writer.execute(
                        "UPDATE runtime_authority_binding "
                        "SET first_subject_event_sealed = 1 WHERE binding_id = ?",
                        (lane.binding_id,),
                    )
                finally:
                    lane.worker.call(
                        "_close_binding_gate",
                        retire=False,
                        _host_token=_HOST_RUNTIME_TOKEN,
                    )
            lane.accepting = False
            lane.worker.close()
            return
        raise RuntimeHostFailedClosed(
            "test-governance-seed-incomplete",
            "nonconforming fixture unexpectedly received a serving permit",
        )

    def _require_governed_timeline_lineage(
        self,
        qri: QualifiedRuntimeInput,
        *,
        timeline_id: str,
    ) -> None:
        reader = _connect_readonly(self._location.control_database)
        try:
            rows = reader.execute(
                f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
                "WHERE profile_id = ? AND state = 'active'",
                (qri.profile_id,),
            ).fetchall()
        finally:
            reader.close()
        active = tuple(self._binding_from_row(row) for row in rows)
        exact = tuple(
            binding
            for binding in active
            if binding.timeline_id == timeline_id
            and binding.qualification_id == qri.qualification_id
            and binding.qri_integrity_digest == qri.integrity_digest
        )
        if exact:
            if len(exact) != 1:
                raise RuntimeHostFailedClosed(
                    "branch-governance-tampered",
                    "more than one active binding claims one governed route",
                )
            self._require_binding_permit(exact[0])
            return
        predecessor_qualification_id = qri.predecessor_qualification_id
        if predecessor_qualification_id is None:
            if any(binding.timeline_id != timeline_id for binding in active):
                raise RuntimeHostRejected(
                    "branch-governance-forward-lineage-required",
                    "a second Timeline requires an explicit governed predecessor",
                )
            return
        predecessors = tuple(
            binding
            for binding in active
            if binding.qualification_id == predecessor_qualification_id
        )
        if any(binding.timeline_id != timeline_id for binding in predecessors):
            raise RuntimeHostRejected(
                "nonconforming-experimental-branch",
                "successor QRI crosses an existing predecessor Timeline without "
                "a forward branch disposition",
            )
        if not predecessors:
            raise RuntimeHostFailedClosed(
                "branch-governance-missing",
                "successor QRI has no governed active predecessor",
            )
        if len(predecessors) != 1:
            raise RuntimeHostFailedClosed(
                "branch-governance-tampered",
                "successor QRI resolves to more than one active predecessor",
            )
        self._require_binding_permit(predecessors[0])

    def _governance_case_id(self, profile_id: str) -> str:
        return str(
            uuid5(
                NAMESPACE_URL,
                f"post-m0-05-branch-governance:{self._location.root_id}:{profile_id}",
            )
        )

    def _append_branch_governance_fact(
        self,
        binding: RuntimeAuthorityBinding,
        *,
        replaces: RuntimeAuthorityBinding | None,
        activation: object,
        created_at_us: int,
    ) -> None:
        if activation is _NORMAL_GOVERNANCE_ACTIVATION:
            members = [
                *(
                    [
                        _branch_governance_member(
                            replaces,
                            classification=_BRANCH_NORMAL,
                            serving_disposition=_BRANCH_RETIRED,
                        )
                    ]
                    if replaces is not None
                    else []
                ),
                _branch_governance_member(
                    binding,
                    classification=_BRANCH_NORMAL,
                    serving_disposition=_BRANCH_ELIGIBLE,
                ),
            ]
        elif activation is _TEST_HELD_GOVERNANCE_ACTIVATION:
            rows = self._writer.execute(
                f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
                "WHERE profile_id = ? AND binding_id != ? AND state = 'active' "
                "ORDER BY binding_id",
                (binding.profile_id, binding.binding_id),
            ).fetchall()
            predecessors = tuple(self._binding_from_row(row) for row in rows)
            if not predecessors or all(
                predecessor.timeline_id == binding.timeline_id
                for predecessor in predecessors
            ):
                raise RuntimeHostRejected(
                    "test-governance-seed-invalid",
                    "held fixture does not contain a crossed active Timeline",
                )
            members = [
                *(
                    _branch_governance_member(
                        predecessor,
                        classification=_BRANCH_NORMAL,
                        serving_disposition=_BRANCH_HELD,
                    )
                    for predecessor in predecessors
                ),
                _branch_governance_member(
                    binding,
                    classification=_BRANCH_NONCONFORMING,
                    serving_disposition=_BRANCH_HELD,
                ),
            ]
        elif activation is _RETIRE_GOVERNANCE_TRANSITION:
            if replaces is not None:
                raise RuntimeHostFailedClosed(
                    "branch-governance-transition-invalid",
                    "retirement governance fact cannot replace another binding",
                )
            members = [
                _branch_governance_member(
                    binding,
                    classification=_BRANCH_NORMAL,
                    serving_disposition=_BRANCH_RETIRED,
                )
            ]
        elif activation is _CORRECTIVE_SUCCESSOR_PREPARATION_AUTHORITY:
            if replaces is None:
                raise RuntimeHostFailedClosed(
                    "corrective-successor-transition-invalid",
                    "corrective governance requires its retired predecessor",
                )
            rows = self._writer.execute(
                f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
                "WHERE profile_id = ? ORDER BY binding_id",
                (binding.profile_id,),
            ).fetchall()
            all_bindings = tuple(self._binding_from_row(row) for row in rows)
            contained = tuple(
                item
                for item in all_bindings
                if item.binding_id not in {binding.binding_id, replaces.binding_id}
            )
            self._require_corrective_governance_preimage(
                replaces,
                contained[0] if len(contained) == 1 else None,
            )
            if (
                len(all_bindings) != 3
                or len(contained) != 1
                or (
                    replaces.state is not BindingState.RETIRED
                    and not (
                        replaces.state is BindingState.ACTIVE
                        and replaces.binding_id == binding.predecessor_binding_id
                    )
                )
                or binding.state is not BindingState.ACTIVE
                or contained[0].state is not BindingState.ACTIVE
                or binding.predecessor_binding_id != replaces.binding_id
                or replaces.predecessor_binding_id is not None
                or contained[0].predecessor_binding_id is not None
                or binding.timeline_id != replaces.timeline_id
                or contained[0].timeline_id == replaces.timeline_id
                or binding.binding_revision != replaces.binding_revision + 1
            or binding.binding_epoch != replaces.binding_epoch + 1
            or binding.qualification_id == replaces.qualification_id
            or binding.qri_integrity_digest == replaces.qri_integrity_digest
            or binding.timeline_root == replaces.timeline_root
            ):
                raise RuntimeHostFailedClosed(
                    "corrective-successor-transition-invalid",
                    "corrective governance does not preserve the exact two-held lineage",
                )
            members = [
                _branch_governance_member(
                    replaces,
                    classification=_BRANCH_NORMAL,
                    serving_disposition=_BRANCH_RETIRED,
                ),
                _branch_governance_member(
                    contained[0],
                    classification=_BRANCH_NONCONFORMING,
                    serving_disposition=_BRANCH_HELD,
                ),
                _branch_governance_member(
                    binding,
                    classification=_BRANCH_NORMAL,
                    serving_disposition=_BRANCH_ELIGIBLE,
                ),
            ]
            corrective_preparation = _verify_corrective_preparation_record(
                self._location,
                binding.timeline_root,
                qualification_id=binding.qualification_id,
                qri_integrity_digest=binding.qri_integrity_digest,
                authority=self._authority_for_binding(binding),
                predecessor=replaces,
                nonconforming=contained[0],
            )
        else:
            raise RuntimeHostFailedClosed(
                "branch-governance-activation-invalid",
                "binding activation lacks the private governance authority",
            )
        case_id = self._governance_case_id(binding.profile_id)
        prior = self._writer.execute(
            """
            SELECT sequence, fact_digest FROM branch_governance_fact
            WHERE case_id = ? ORDER BY sequence DESC LIMIT 1
            """,
            (case_id,),
        ).fetchone()
        sequence = 1 if prior is None else int(prior[0]) + 1
        previous_fact_digest = None if prior is None else str(prior[1])
        fact_digest = _branch_governance_fact_digest(
            case_id=case_id,
            host_root_id=self._location.root_id,
            host_control_store_id=self._location.control_store_id,
            sequence=sequence,
            previous_fact_digest=previous_fact_digest,
            members=members,
            corrective_preparation=(
                corrective_preparation
                if activation is _CORRECTIVE_SUCCESSOR_PREPARATION_AUTHORITY
                else None
            ),
        )
        fact_id = str(
            uuid5(
                NAMESPACE_URL,
                f"post-m0-05-branch-fact:{case_id}:{sequence}:{fact_digest}",
            )
        )
        self._writer.execute(
            """
            INSERT INTO branch_governance_fact (
                fact_id, case_id, host_root_id, host_control_store_id,
                sequence, previous_fact_digest, fact_digest, created_at_us
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fact_id,
                case_id,
                self._location.root_id,
                self._location.control_store_id,
                sequence,
                previous_fact_digest,
                fact_digest,
                created_at_us,
            ),
        )
        for member in members:
            self._writer.execute(
                """
                INSERT INTO branch_governance_member (
                    fact_id, binding_id, binding_revision, binding_epoch,
                    profile_id, timeline_id, authority_scope_id, qualification_id,
                    qri_integrity_digest, timeline_root_id,
                    timeline_control_store_id, timeline_store_id, classification,
                    serving_disposition
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (fact_id, *member.values()),
            )

    def _require_corrective_governance_preimage(
        self,
        predecessor: RuntimeAuthorityBinding,
        nonconforming: RuntimeAuthorityBinding | None,
    ) -> None:
        """Require the one exact two-held fact before the corrective append."""

        if nonconforming is None:
            raise RuntimeHostFailedClosed(
                "corrective-successor-governance-preimage-mismatch",
                "corrective governance requires exactly two source bindings",
            )
        case_id = self._governance_case_id(predecessor.profile_id)
        facts = self._writer.execute(
            "SELECT fact_id, sequence, previous_fact_digest "
            "FROM branch_governance_fact WHERE case_id = ? ORDER BY sequence",
            (case_id,),
        ).fetchall()
        if (
            len(facts) != 1
            or int(facts[0][1]) != 1
            or facts[0][2] is not None
        ):
            raise RuntimeHostFailedClosed(
                "corrective-successor-governance-preimage-mismatch",
                "corrective governance must transition exact sequence 1 to sequence 2",
            )
        members = self._writer.execute(
            "SELECT binding_id, classification, serving_disposition "
            "FROM branch_governance_member WHERE fact_id = ? ORDER BY binding_id",
            (str(facts[0][0]),),
        ).fetchall()
        expected = sorted(
            (
                (predecessor.binding_id, _BRANCH_NORMAL, _BRANCH_HELD),
                (
                    nonconforming.binding_id,
                    _BRANCH_NONCONFORMING,
                    _BRANCH_HELD,
                ),
            )
        )
        if [tuple(str(value) for value in row) for row in members] != expected:
            raise RuntimeHostFailedClosed(
                "corrective-successor-governance-preimage-mismatch",
                "sequence 1 must contain the exact normal/nonconforming held pair",
            )

    def _require_binding_permit(self, binding: RuntimeAuthorityBinding) -> None:
        target, latest_members = self._require_structural_binding_permit(binding)
        if target["serving_disposition"] == _BRANCH_HELD:
            raise RuntimeHostRejected(
                "branch-serving-held",
                "held branch has no serving permit",
            )
        if target["serving_disposition"] == _BRANCH_RETIRED:
            raise RuntimeHostRejected(
                "branch-serving-retired",
                "retired branch has no serving permit",
            )
        eligible = sum(
            member["serving_disposition"] == _BRANCH_ELIGIBLE
            for member in latest_members
        )
        if eligible != 1:
            raise RuntimeHostFailedClosed(
                "branch-governance-dual-eligible",
                "latest serving fact must name exactly one eligible member",
            )
        derived_classification = self._derive_binding_branch_classification(binding)
        if target["classification"] != derived_classification:
            raise RuntimeHostFailedClosed(
                "branch-governance-classification-mismatch",
                "ledger classification differs from canonical QRI/binding lineage",
            )
        if derived_classification == _BRANCH_NONCONFORMING:
            raise RuntimeHostRejected(
                "nonconforming-experimental-branch",
                "canonical lineage identifies a nonconforming experimental branch",
            )

    def _require_structural_binding_permit(
        self,
        binding: RuntimeAuthorityBinding,
    ) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
        """Validate the Host ledger and reject held state before Studio assembly."""

        if (
            binding.host_root_id != self._location.root_id
            or binding.host_control_store_id != self._location.control_store_id
        ):
            raise RuntimeHostFailedClosed(
                "branch-governance-cross-root",
                "binding does not belong to this Host ControlStore",
            )
        case_id = self._governance_case_id(binding.profile_id)
        reader = _connect_readonly(self._location.control_database)
        try:
            facts = reader.execute(
                """
                SELECT fact_id, host_root_id, host_control_store_id, sequence,
                       previous_fact_digest, fact_digest
                FROM branch_governance_fact WHERE case_id = ? ORDER BY sequence
                """,
                (case_id,),
            ).fetchall()
            if not facts:
                raise RuntimeHostFailedClosed(
                    "branch-governance-missing",
                    "active binding has no branch-governance fact",
                )
            expected_sequence = 1
            previous_digest: str | None = None
            latest_members: tuple[dict[str, object], ...] = ()
            for fact in facts:
                fact_id = str(fact[0])
                if (
                    str(fact[1]) != self._location.root_id
                    or str(fact[2]) != self._location.control_store_id
                    or int(fact[3]) != expected_sequence
                    or (None if fact[4] is None else str(fact[4])) != previous_digest
                ):
                    raise RuntimeHostFailedClosed(
                        "branch-governance-cross-root",
                        "branch-governance fact has another root or broken sequence",
                    )
                member_rows = reader.execute(
                    """
                    SELECT binding_id, binding_revision, binding_epoch, profile_id,
                           timeline_id, authority_scope_id, qualification_id,
                           qri_integrity_digest, timeline_root_id,
                           timeline_control_store_id, timeline_store_id,
                           classification, serving_disposition
                    FROM branch_governance_member WHERE fact_id = ?
                    ORDER BY binding_id
                    """,
                    (fact_id,),
                ).fetchall()
                members = tuple(_branch_governance_member_from_row(row) for row in member_rows)
                corrective_preparation: Mapping[str, object] | None = None
                if expected_sequence == 2 and len(members) == 3:
                    retired_id = next(
                        (
                            str(member["binding_id"])
                            for member in members
                            if member["classification"] == _BRANCH_NORMAL
                            and member["serving_disposition"] == _BRANCH_RETIRED
                        ),
                        None,
                    )
                    contained_id = next(
                        (
                            str(member["binding_id"])
                            for member in members
                            if member["classification"] == _BRANCH_NONCONFORMING
                            and member["serving_disposition"] == _BRANCH_HELD
                        ),
                        None,
                    )
                    eligible_id = next(
                        (
                            str(member["binding_id"])
                            for member in members
                            if member["classification"] == _BRANCH_NORMAL
                            and member["serving_disposition"] == _BRANCH_ELIGIBLE
                        ),
                        None,
                    )
                    if None not in {retired_id, contained_id, eligible_id}:
                        role_rows = {
                            role_id: reader.execute(
                                f"SELECT {_BINDING_COLUMNS} "
                                "FROM runtime_authority_binding WHERE binding_id = ?",
                                (role_id,),
                            ).fetchone()
                            for role_id in (retired_id, contained_id, eligible_id)
                        }
                        if all(row is not None for row in role_rows.values()):
                            retired_binding = self._binding_from_row(
                                role_rows[retired_id]
                            )
                            contained_binding = self._binding_from_row(
                                role_rows[contained_id]
                            )
                            eligible_binding = self._binding_from_row(
                                role_rows[eligible_id]
                            )
                            authorization = getattr(
                                self,
                                "_local_serving_authorization",
                                None,
                            )
                            if (
                                type(authorization) is _LocalServingAuthorization
                                and authorization.matches_binding(
                                    self._location,
                                    eligible_binding,
                                )
                            ):
                                record_path = _corrective_preparation_record_path(
                                    self._location,
                                    eligible_binding.timeline_root,
                                )
                                if (
                                    _file_sha256(record_path)
                                    != authorization.preparation_record_sha256
                                ):
                                    raise RuntimeHostFailedClosed(
                                        "corrective-successor-root-commitment-mismatch",
                                        "serving authorization preparation record drifted",
                                    )
                                authorized_record = _read_corrective_preparation_record(
                                    self._location,
                                    eligible_binding.timeline_root,
                                )
                                authorized_body = authorized_record.get("plan_body")
                                if (
                                    authorized_record.get("qualification_id")
                                    != eligible_binding.qualification_id
                                    or authorized_record.get("qri_integrity_digest")
                                    != eligible_binding.qri_integrity_digest
                                    or authorized_record.get("timeline_root")
                                    != eligible_binding.timeline_root.to_dict()
                                    or not isinstance(authorized_body, dict)
                                    or authorized_body.get(
                                        "predecessor_root_sha256"
                                    )
                                    != _corrective_root_hashes(retired_binding)
                                    or authorized_body.get(
                                        "nonconforming_root_sha256"
                                    )
                                    != _corrective_root_hashes(contained_binding)
                                ):
                                    raise RuntimeHostFailedClosed(
                                        "corrective-successor-root-commitment-mismatch",
                                        "authorized serving lineage drifted",
                                    )
                                corrective_preparation = authorized_record
                            else:
                                corrective_preparation = (
                                    _verify_corrective_preparation_record(
                                        self._location,
                                        eligible_binding.timeline_root,
                                        qualification_id=(
                                            eligible_binding.qualification_id
                                        ),
                                        qri_integrity_digest=(
                                            eligible_binding.qri_integrity_digest
                                        ),
                                        authority=self._authority_for_binding(
                                            eligible_binding
                                        ),
                                        predecessor=retired_binding,
                                        nonconforming=contained_binding,
                                    )
                                )
                if not members or _branch_governance_fact_digest(
                    case_id=case_id,
                    host_root_id=self._location.root_id,
                    host_control_store_id=self._location.control_store_id,
                    sequence=expected_sequence,
                    previous_fact_digest=previous_digest,
                    members=members,
                    corrective_preparation=corrective_preparation,
                ) != str(fact[5]):
                    raise RuntimeHostFailedClosed(
                        "branch-governance-tampered",
                        "branch-governance fact digest does not verify",
                    )
                for member in members:
                    observed = reader.execute(
                        f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
                        "WHERE binding_id = ?",
                        (str(member["binding_id"]),),
                    ).fetchone()
                    if observed is None or not _branch_governance_member_matches(
                        member, self._binding_from_row(observed)
                    ):
                        raise RuntimeHostFailedClosed(
                            "binding-identity-mismatch",
                            "branch-governance member differs from its binding",
                        )
                    if (
                        str(member["profile_id"]) != binding.profile_id
                        or str(member["classification"]) not in {
                            _BRANCH_NORMAL,
                            _BRANCH_NONCONFORMING,
                        }
                        or str(member["serving_disposition"]) not in {
                            _BRANCH_ELIGIBLE,
                            _BRANCH_HELD,
                            _BRANCH_RETIRED,
                        }
                        or (
                            str(member["classification"]) == _BRANCH_NONCONFORMING
                            and str(member["serving_disposition"]) != _BRANCH_HELD
                        )
                    ):
                        raise RuntimeHostFailedClosed(
                            "branch-governance-tampered",
                            "branch-governance member has an invalid disposition",
                        )
                previous_digest = str(fact[5])
                expected_sequence += 1
                latest_members = members
        finally:
            reader.close()
        target = next(
            (member for member in latest_members if member["binding_id"] == binding.binding_id),
            None,
        )
        if target is None:
            raise RuntimeHostFailedClosed(
                "branch-governance-stale",
                "active binding is absent from the latest governance fact",
            )
        if any(
            member["classification"] == _BRANCH_NONCONFORMING
            for member in latest_members
        ):
            if self._is_prepared_corrective_case(binding):
                return target, latest_members
            if all(
                member["serving_disposition"] == _BRANCH_HELD
                for member in latest_members
            ):
                raise RuntimeHostRejected(
                    "branch-serving-held",
                    "contained nonconforming branch keeps every member held",
                )
            raise RuntimeHostRejected(
                "nonconforming-experimental-branch",
                "a nonconforming member quarantines the complete branch case",
            )
        return target, latest_members

    def _is_prepared_corrective_case(
        self,
        binding: RuntimeAuthorityBinding,
    ) -> bool:
        """Recognize only the complete two-held-to-corrective ledger topology."""

        reader = _connect_readonly(self._location.control_database)
        try:
            facts = reader.execute(
                "SELECT fact_id, sequence FROM branch_governance_fact "
                "WHERE case_id = ? ORDER BY sequence",
                (self._governance_case_id(binding.profile_id),),
            ).fetchall()
            members_by_sequence: dict[int, dict[str, tuple[str, str]]] = {}
            for fact_id, sequence in facts:
                rows = reader.execute(
                    "SELECT binding_id, classification, serving_disposition "
                    "FROM branch_governance_member WHERE fact_id = ?",
                    (str(fact_id),),
                ).fetchall()
                members_by_sequence[int(sequence)] = {
                    str(row[0]): (str(row[1]), str(row[2])) for row in rows
                }
            rows = reader.execute(
                f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
                "WHERE profile_id = ? ORDER BY binding_id",
                (binding.profile_id,),
            ).fetchall()
        finally:
            reader.close()
        if (
            len(facts) != 2
            or [int(fact[1]) for fact in facts] != [1, 2]
        ):
            return False
        first = members_by_sequence[1]
        second = members_by_sequence[2]
        if len(rows) != 3 or len(first) != 2 or len(second) != 3:
            return False
        predecessor_id = next(
            (
                item
                for item, disposition in first.items()
                if disposition == (_BRANCH_NORMAL, _BRANCH_HELD)
                and second.get(item) == (_BRANCH_NORMAL, _BRANCH_RETIRED)
            ),
            None,
        )
        nonconforming_id = next(
            (
                item
                for item, disposition in first.items()
                if disposition == (_BRANCH_NONCONFORMING, _BRANCH_HELD)
                and second.get(item) == (_BRANCH_NONCONFORMING, _BRANCH_HELD)
            ),
            None,
        )
        corrective_id = next(
            (
                item
                for item, disposition in second.items()
                if disposition == (_BRANCH_NORMAL, _BRANCH_ELIGIBLE)
                and item not in first
            ),
            None,
        )
        by_id = {str(row[0]): row for row in rows}
        if (
            predecessor_id is None
            or nonconforming_id is None
            or corrective_id is None
            or set(by_id) != {predecessor_id, nonconforming_id, corrective_id}
        ):
            return False
        predecessor_row = by_id[predecessor_id]
        nonconforming_row = by_id[nonconforming_id]
        corrective_row = by_id[corrective_id]
        return (
            str(predecessor_row[3]) == BindingState.RETIRED.value
            and str(nonconforming_row[3]) == BindingState.ACTIVE.value
            and str(corrective_row[3]) == BindingState.ACTIVE.value
            and predecessor_row[26] is None
            and nonconforming_row[26] is None
            and str(corrective_row[26]) == predecessor_id
            and str(corrective_row[5]) == str(predecessor_row[5])
            and str(nonconforming_row[5]) != str(predecessor_row[5])
            and int(corrective_row[1]) == int(predecessor_row[1]) + 1
            and int(corrective_row[2]) == int(predecessor_row[2]) + 1
            and str(corrective_row[23]) != str(predecessor_row[23])
            and str(corrective_row[24]) != str(predecessor_row[24])
            and str(corrective_row[25]) != str(predecessor_row[25])
        )

    def _derive_binding_branch_classification(
        self,
        binding: RuntimeAuthorityBinding,
    ) -> str:
        """Derive branch semantics from canonical Studio and binding facts.

        The ledger records a disposition, but it is not trusted to invent lineage.
        In particular, a recomputed ControlStore digest cannot turn a successor on
        another Timeline into a normal serving branch.
        """

        qri = self._qri_for_binding(binding)
        reader = _connect_readonly(self._location.control_database)
        try:
            rows = reader.execute(
                f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
                "WHERE profile_id = ? AND binding_id != ? ORDER BY created_at_us, binding_id",
                (binding.profile_id, binding.binding_id),
            ).fetchall()
        finally:
            reader.close()
        others = tuple(self._binding_from_row(row) for row in rows)
        predecessor_qualification_id = qri.predecessor_qualification_id
        if predecessor_qualification_id is None:
            if binding.predecessor_binding_id is not None:
                raise RuntimeHostFailedClosed(
                    "branch-governance-lineage-mismatch",
                    "root QRI binding unexpectedly names a predecessor binding",
                )
            for other in others:
                if other.timeline_id == binding.timeline_id:
                    continue
                other_qri = self._qri_for_binding(other)
                if other_qri.published_at_us <= qri.published_at_us:
                    return _BRANCH_NONCONFORMING
            return _BRANCH_NORMAL

        predecessors = tuple(
            other
            for other in others
            if other.qualification_id == predecessor_qualification_id
        )
        if not predecessors:
            raise RuntimeHostFailedClosed(
                "branch-governance-missing",
                "canonical successor QRI has no recorded predecessor binding",
            )
        if any(
            predecessor.timeline_id != binding.timeline_id
            for predecessor in predecessors
        ):
            return _BRANCH_NONCONFORMING
        if (
            len(predecessors) != 1
            or binding.predecessor_binding_id != predecessors[0].binding_id
        ):
            raise RuntimeHostFailedClosed(
                "branch-governance-lineage-mismatch",
                "successor binding does not uniquely name its same-Timeline predecessor",
            )
        return _BRANCH_NORMAL

    def _validate_activation_plan(
        self,
        qri: QualifiedRuntimeInput,
        *,
        timeline_id: str,
        plan: _HostActivationPlan,
    ) -> None:
        expected_binding_id = str(
            uuid5(
                NAMESPACE_URL,
                f"m0-12-binding:{plan.host_root_id}:{qri.profile_id}:"
                f"{timeline_id}:{qri.qualification_id}:1",
            )
        )
        expected_scope_id = str(
            uuid5(NAMESPACE_URL, f"m0-12-authority-scope:{expected_binding_id}")
        )
        plan_kind_matches = (
            type(plan) is _RuntimeActivationPlan
            and self._location.root_kind == EXPERIMENTAL_ROOT_KIND
        ) or (
            type(plan) is _DormantArtifactActivationPlan
            and self._location.root_kind == HOST_ROOT_KIND
        ) or (
            type(plan) is _DormantArtifactExperimentalActivationPlan
            and self._location.root_kind == EXPERIMENTAL_ROOT_KIND
        )
        if (
            not plan_kind_matches
            or self._location.root_id != plan.host_root_id
            or self._location.control_store_id != plan.host_control_store_id
            or qri.provider_authority != plan.provider_authority
            or qri.profile_id != plan.profile_id
            or qri.qualification_id != plan.qualification_id
            or qri.publication_key != plan.qri_publication_key
            or timeline_id != plan.timeline_id
            or plan.binding_id != expected_binding_id
            or plan.authority_scope_id != expected_scope_id
        ):
            raise RuntimeHostRejected(
                "activation-plan-mismatch",
                "QRI, Host, binding, or Timeline differs from the reserved plan",
            )

    def _activate_first_binding(
        self,
        qri: QualifiedRuntimeInput,
        timeline_id: str,
        *,
        activation_plan: _HostActivationPlan | None = None,
        _governance_activation: object,
    ) -> RuntimeRoute:
        cognition = self._cognition_assembly.select(qri)
        binding_id = (
            str(
                uuid5(
                    NAMESPACE_URL,
                    f"m0-12-binding:{self._location.root_id}:{qri.profile_id}:"
                    f"{timeline_id}:{qri.qualification_id}:1",
                )
            )
            if activation_plan is None
            else activation_plan.binding_id
        )
        authority = _RuntimeBindingAuthority(
            authority_scope_id=(
                str(uuid5(NAMESPACE_URL, f"m0-12-authority-scope:{binding_id}"))
                if activation_plan is None
                else activation_plan.authority_scope_id
            ),
            profile_id=qri.profile_id,
            timeline_id=timeline_id,
            allowed_intents=ALLOWED_INTENTS,
            allowed_provenance=ALLOWED_PROVENANCE,
            binding_id=binding_id,
            binding_revision=1,
            binding_epoch=1,
            qualification_id=qri.qualification_id,
            qualification_revision=qri.qualification_revision,
            provider_authority=qri.provider_authority,
        )
        worker: _RuntimeWorker | None = None
        try:
            worker = _RuntimeWorker(
                binding_id,
                lambda: SubjectRuntime._create_bound(
                    self._location.root,
                    authority=authority,
                    cognition=cognition,
                    experienced_at_us=qri.published_at_us,
                    runtime_identity=self._runtime_identity,
                    root_kind=self._location.root_kind,
                    relationship_enabled=self._relationship_enabled,
                    _host_token=_HOST_RUNTIME_TOKEN,
                    interrupt_at=self._runtime_interrupt_at,
                    fault_hook=self._runtime_fault_hook,
                    _reserved_timeline_identity=(
                        None
                        if activation_plan is None
                        else activation_plan.timeline_identity
                    ),
                ),
            )
            self._hit(RuntimeHostFaultPoint.AFTER_TIMELINE_BUILD)
            gate_state, _gate_epoch, basis, has_event = worker.call(
                "_binding_health",
                _host_token=_HOST_RUNTIME_TOKEN,
            )
            if gate_state != "closed" or basis.head_sequence != 0 or has_event:
                raise RuntimeHostFailedClosed(
                    "assembly-health-failed",
                    "candidate RuntimeAssembly is not a closed empty Timeline",
                )
            self._hit(RuntimeHostFaultPoint.AFTER_ASSEMBLY_HEALTH)
            self._insert_and_activate_binding(
                authority,
                qri,
                worker.location,
                _governance_activation=_governance_activation,
            )
            self._hit(RuntimeHostFaultPoint.AFTER_CONTROL_ACTIVATION)
            binding = self._require_active_binding(qri.profile_id, timeline_id)
            self._claim_instance(binding)
            worker.call(
                "_activate_binding_gate",
                _host_token=_HOST_RUNTIME_TOKEN,
            )
            self._hit(RuntimeHostFaultPoint.AFTER_TIMELINE_GATE_OPEN)
            lane = self._install_lane(binding, qri, worker)
            worker = None
            self._hit(RuntimeHostFaultPoint.AFTER_LANE_INSTALL)
            return self._route(binding, lane)
        except RuntimeHostProblem:
            if worker is not None:
                worker.close()
            raise
        except Exception as error:
            if worker is not None:
                worker.close()
            raise RuntimeHostFailedClosed(
                "runtime-build-failed",
                "candidate RuntimeAssembly failed before serving",
            ) from error

    def _swap_before_first_event(
        self,
        active: RuntimeAuthorityBinding,
        qri: QualifiedRuntimeInput,
    ) -> RuntimeRoute:
        successor_cognition = self._cognition_assembly.select(qri)
        key = (active.profile_id, active.timeline_id)
        old_lane = self._lanes.get(key)
        if old_lane is None:
            raise RuntimeHostFailedClosed(
                "runtime-lane-unavailable",
                "active binding has no lane to build-then-swap",
            )
        self._synchronize_subject_event_seal(old_lane)
        active = self._require_active_binding(*key)
        if active.first_subject_event_sealed:
            raise RuntimeHostConflict(
                "timeline-binding-sealed",
                "a Timeline with a SubjectEvent cannot be rebound",
            )
        if qri.predecessor_qualification_id != active.qualification_id:
            raise RuntimeHostRejected(
                "qualification-lineage-mismatch",
                "successor QRI must name the active qualification as predecessor",
            )
        revision = active.binding_revision + 1
        epoch = active.binding_epoch + 1
        binding_id = str(
            uuid5(
                NAMESPACE_URL,
                f"m0-12-binding:{self._location.root_id}:{qri.profile_id}:"
                f"{active.timeline_id}:{qri.qualification_id}:{revision}",
            )
        )
        authority = _RuntimeBindingAuthority(
            authority_scope_id=str(
                uuid5(NAMESPACE_URL, f"m0-12-authority-scope:{binding_id}")
            ),
            profile_id=qri.profile_id,
            timeline_id=active.timeline_id,
            allowed_intents=ALLOWED_INTENTS,
            allowed_provenance=ALLOWED_PROVENANCE,
            binding_id=binding_id,
            binding_revision=revision,
            binding_epoch=epoch,
            qualification_id=qri.qualification_id,
            qualification_revision=qri.qualification_revision,
            provider_authority=qri.provider_authority,
        )
        candidate: _RuntimeWorker | None = None
        old_lane_locked = False
        old_gate_closed = False
        control_swapped = False
        try:
            candidate = _RuntimeWorker(
                binding_id,
                lambda: SubjectRuntime._create_bound(
                    self._location.root,
                    authority=authority,
                    cognition=successor_cognition,
                    experienced_at_us=qri.published_at_us,
                    runtime_identity=self._runtime_identity,
                    root_kind=self._location.root_kind,
                    relationship_enabled=self._relationship_enabled,
                    _host_token=_HOST_RUNTIME_TOKEN,
                    interrupt_at=self._runtime_interrupt_at,
                    fault_hook=self._runtime_fault_hook,
                ),
            )
            self._hit(RuntimeHostFaultPoint.AFTER_TIMELINE_BUILD)
            gate_state, _gate_epoch, basis, has_event = candidate.call(
                "_binding_health",
                _host_token=_HOST_RUNTIME_TOKEN,
            )
            if gate_state != "closed" or basis.head_sequence != 0 or has_event:
                raise RuntimeHostFailedClosed(
                    "assembly-health-failed",
                    "successor RuntimeAssembly is not a closed empty Timeline",
                )
            self._hit(RuntimeHostFaultPoint.AFTER_ASSEMBLY_HEALTH)
            if not old_lane.lock.acquire(blocking=False):
                raise RuntimeHostConflict(
                    "runtime-lease-contended",
                    "active lane must drain before binding swap",
                )
            old_lane_locked = True
            old_lane.accepting = False
            old_lane.worker.call(
                "_close_binding_gate",
                retire=False,
                _host_token=_HOST_RUNTIME_TOKEN,
            )
            old_gate_closed = True
            self._hit(RuntimeHostFaultPoint.AFTER_OLD_GATE_CLOSED)
            self._insert_and_activate_binding(
                authority,
                qri,
                candidate.location,
                replaces=active,
                _governance_activation=_NORMAL_GOVERNANCE_ACTIVATION,
            )
            control_swapped = True
            self._hit(RuntimeHostFaultPoint.AFTER_CONTROL_ACTIVATION)
            binding = self._require_active_binding(*key)
            self._claim_instance(binding)
            candidate.call(
                "_activate_binding_gate",
                _host_token=_HOST_RUNTIME_TOKEN,
            )
            self._hit(RuntimeHostFaultPoint.AFTER_TIMELINE_GATE_OPEN)
            old_lane.worker.close()
            self._lanes.pop(key, None)
            lane = self._install_lane(binding, qri, candidate)
            candidate = None
            self._hit(RuntimeHostFaultPoint.AFTER_LANE_INSTALL)
            return self._route(binding, lane)
        except RuntimeHostProblem:
            if old_gate_closed and not control_swapped:
                old_lane.worker.call(
                    "_activate_binding_gate",
                    _host_token=_HOST_RUNTIME_TOKEN,
                )
                old_lane.accepting = True
            raise
        except Exception as error:
            if old_gate_closed and not control_swapped:
                old_lane.worker.call(
                    "_activate_binding_gate",
                    _host_token=_HOST_RUNTIME_TOKEN,
                )
                old_lane.accepting = True
            raise RuntimeHostFailedClosed(
                "runtime-build-failed",
                "successor RuntimeAssembly failed before serving",
            ) from error
        finally:
            if candidate is not None:
                candidate.close()
            if old_lane_locked:
                old_lane.lock.release()

    def _insert_and_activate_binding(
        self,
        authority: _RuntimeBindingAuthority,
        qri: QualifiedRuntimeInput,
        timeline_root: CanonicalRootRef,
        *,
        replaces: RuntimeAuthorityBinding | None = None,
        _governance_activation: object,
    ) -> None:
        now = _utc_microseconds()
        try:
            _begin(self._writer)
            self._writer.execute(
                """
                INSERT INTO runtime_authority_binding (
                    binding_id, binding_revision, binding_epoch, state,
                    profile_id, timeline_id, authority_scope_id,
                    qualification_id, qualification_revision,
                    qri_publication_key, qri_integrity_digest,
                    genesis_snapshot_id, knowledge_snapshot_id,
                    policy_decision_ids_json, capability_manifest_version,
                    provider_authority, runtime_kind, runtime_contract_version,
                    studio_root_id, studio_store_id, host_root_id,
                    host_control_store_id, timeline_root_json,
                    timeline_root_id, timeline_control_store_id,
                    timeline_store_id, predecessor_binding_id,
                    first_subject_event_sealed, created_at_us,
                    activated_at_us, retired_at_us
                ) VALUES (
                    ?, ?, ?, 'validated', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, NULL, NULL
                )
                """,
                (
                    authority.binding_id,
                    authority.binding_revision,
                    authority.binding_epoch,
                    authority.profile_id,
                    authority.timeline_id,
                    authority.authority_scope_id,
                    qri.qualification_id,
                    qri.qualification_revision,
                    qri.publication_key,
                    qri.integrity_digest,
                    qri.genesis_snapshot_id,
                    qri.knowledge_snapshot_id,
                    _canonical_json(list(qri.policy_decision_ids)),
                    qri.capabilities.manifest_version,
                    qri.provider_authority,
                    RUNTIME_KIND,
                    RUNTIME_CONTRACT_VERSION,
                    self._studio_location.root_id,
                    self._studio_location.profile_store_id,
                    self._location.root_id,
                    self._location.control_store_id,
                    _canonical_json(timeline_root.to_dict()),
                    timeline_root.root_id,
                    timeline_root.control_store_id,
                    timeline_root.timeline_store_id,
                    None if replaces is None else replaces.binding_id,
                    now,
                ),
            )
            if replaces is not None:
                retired = self._writer.execute(
                    """
                    UPDATE runtime_authority_binding
                    SET state = 'retired', retired_at_us = ?
                    WHERE binding_id = ?
                      AND state = 'active'
                      AND first_subject_event_sealed = 0
                    """,
                    (now, replaces.binding_id),
                )
                if retired.rowcount != 1:
                    raise RuntimeHostConflict(
                        "timeline-binding-sealed",
                        "active binding changed or crossed its first-event seal",
                    )
                self._writer.execute(
                    """
                    UPDATE runtime_instance_lease
                    SET lease_state = 'closed', updated_at_us = ?
                    WHERE binding_id = ?
                    """,
                    (now, replaces.binding_id),
                )
            changed = self._writer.execute(
                """
                UPDATE runtime_authority_binding
                SET state = 'active', activated_at_us = ?
                WHERE binding_id = ? AND state = 'validated'
                """,
                (now, authority.binding_id),
            )
            if changed.rowcount != 1:
                raise RuntimeHostConflict(
                    "binding-activation-conflict",
                    "candidate binding was not uniquely activated",
                )
            candidate_row = self._writer.execute(
                f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
                "WHERE binding_id = ?",
                (authority.binding_id,),
            ).fetchone()
            if candidate_row is None:
                raise RuntimeHostFailedClosed(
                    "binding-identity-mismatch",
                    "activated binding disappeared before governance append",
                )
            self._append_branch_governance_fact(
                self._binding_from_row(candidate_row),
                replaces=replaces,
                activation=_governance_activation,
                created_at_us=now,
            )
            _commit(self._writer)
        except sqlite3.IntegrityError as error:
            _rollback_if_needed(self._writer)
            raise RuntimeHostConflict(
                "binding-activation-conflict",
                "another active binding already owns this Profile/Timeline",
            ) from error
        except Exception:
            _rollback_if_needed(self._writer)
            raise

    def _binding_from_row(self, row: sqlite3.Row) -> RuntimeAuthorityBinding:
        try:
            timeline_root = CanonicalRootRef.from_dict(json.loads(str(row[22])))
            policy_ids = tuple(json.loads(str(row[13])))
            binding = RuntimeAuthorityBinding(
                binding_id=_canonical_uuid(str(row[0]), "binding_id"),
                binding_revision=int(row[1]),
                binding_epoch=int(row[2]),
                state=BindingState(str(row[3])),
                profile_id=_canonical_uuid(str(row[4]), "profile_id"),
                timeline_id=_canonical_uuid(str(row[5]), "timeline_id"),
                authority_scope_id=_canonical_uuid(str(row[6]), "authority_scope_id"),
                qualification_id=_canonical_uuid(str(row[7]), "qualification_id"),
                qualification_revision=int(row[8]),
                qri_publication_key=str(row[9]),
                qri_integrity_digest=str(row[10]),
                genesis_snapshot_id=_canonical_uuid(
                    str(row[11]), "genesis_snapshot_id"
                ),
                knowledge_snapshot_id=_canonical_uuid(
                    str(row[12]), "knowledge_snapshot_id"
                ),
                policy_decision_ids=policy_ids,
                capability_manifest_version=str(row[14]),
                provider_authority=str(row[15]),
                runtime_kind=str(row[16]),
                runtime_contract_version=str(row[17]),
                studio_root_id=_canonical_uuid(str(row[18]), "studio_root_id"),
                studio_store_id=_canonical_uuid(str(row[19]), "studio_store_id"),
                host_root_id=_canonical_uuid(str(row[20]), "host_root_id"),
                host_control_store_id=_canonical_uuid(
                    str(row[21]), "host_control_store_id"
                ),
                timeline_root=timeline_root,
                predecessor_binding_id=(
                    None
                    if row[26] is None
                    else _canonical_uuid(str(row[26]), "predecessor_binding_id")
                ),
                first_subject_event_sealed=bool(row[27]),
                created_at_us=int(row[28]),
                activated_at_us=None if row[29] is None else int(row[29]),
                retired_at_us=None if row[30] is None else int(row[30]),
            )
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            raise RuntimeHostFailedClosed(
                "binding-record-corrupt",
                "RuntimeAuthorityBinding record is unreadable",
            ) from error
        expected = (
            timeline_root.root_id,
            timeline_root.control_store_id,
            timeline_root.timeline_store_id,
        )
        if (
            expected != (str(row[23]), str(row[24]), str(row[25]))
            or binding.runtime_kind != RUNTIME_KIND
            or binding.provider_authority not in _SUPPORTED_PROVIDER_AUTHORITIES
            or binding.runtime_contract_version != RUNTIME_CONTRACT_VERSION
            or binding.studio_root_id != self._studio_location.root_id
            or binding.studio_store_id != self._studio_location.profile_store_id
            or binding.host_root_id != self._location.root_id
            or binding.host_control_store_id != self._location.control_store_id
        ):
            raise RuntimeHostFailedClosed(
                "binding-identity-mismatch",
                "binding store, scope, provider, or root identity is inconsistent",
            )
        return binding

    def _select_active_binding(
        self,
        profile_id: str,
        timeline_id: str,
    ) -> RuntimeAuthorityBinding | None:
        row = self._writer.execute(
            f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
            "WHERE profile_id = ? AND timeline_id = ? AND state = 'active'",
            (profile_id, timeline_id),
        ).fetchone()
        return None if row is None else self._binding_from_row(row)

    def _require_active_binding(
        self,
        profile_id: str,
        timeline_id: str,
    ) -> RuntimeAuthorityBinding:
        binding = self._select_active_binding(profile_id, timeline_id)
        if binding is None:
            raise RuntimeHostRejected(
                "binding-not-active",
                "Profile/Timeline has no active RuntimeAuthorityBinding",
            )
        return binding

    def _assert_lane_binding(
        self,
        binding: RuntimeAuthorityBinding,
        lane: _Lane,
    ) -> None:
        frozen = lane.binding
        if (
            binding.binding_id != frozen.binding_id
            or binding.binding_revision != frozen.binding_revision
            or binding.binding_epoch != frozen.binding_epoch
            or binding.authority_scope_id != frozen.authority_scope_id
            or binding.qualification_id != frozen.qualification_id
            or binding.qri_integrity_digest != frozen.qri_integrity_digest
            or binding.provider_authority != frozen.provider_authority
            or binding.timeline_root != frozen.timeline_root
            or binding.state is not BindingState.ACTIVE
        ):
            lane.accepting = False
            raise RuntimeHostFailedClosed(
                "binding-identity-mismatch",
                "ControlStore binding no longer matches the installed authority lane",
            )
        self._assert_instance_owner(binding.binding_id, lane)

    def _assert_instance_owner(self, binding_id: str, lane: _Lane) -> None:
        reader: sqlite3.Connection | None = None
        connection = self._writer
        if threading.get_ident() != self._owner_thread_id:
            reader = _connect_readonly(self._location.control_database)
            connection = reader
        try:
            row = connection.execute(
                """
                SELECT owner_pid, owner_instance_id, lease_state
                FROM runtime_instance_lease
                WHERE binding_id = ?
                """,
                (binding_id,),
            ).fetchone()
        finally:
            if reader is not None:
                reader.close()
        if row != (os.getpid(), self._instance_id, "active"):
            lane.accepting = False
            raise RuntimeHostFailedClosed(
                "runtime-instance-identity-mismatch",
                "installed lane no longer owns its process-local instance lease",
            )

    def _active_binding_for_lease(
        self,
        profile_id: str,
        timeline_id: str,
    ) -> RuntimeAuthorityBinding:
        if threading.get_ident() == self._owner_thread_id:
            return self._require_active_binding(profile_id, timeline_id)
        reader = _connect_readonly(self._location.control_database)
        try:
            row = reader.execute(
                f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
                "WHERE profile_id = ? AND timeline_id = ? AND state = 'active'",
                (profile_id, timeline_id),
            ).fetchone()
        finally:
            reader.close()
        if row is None:
            raise RuntimeHostRejected(
                "binding-not-active",
                "Profile/Timeline has no active RuntimeAuthorityBinding",
            )
        return self._binding_from_row(row)

    def _read_active_binding(
        self,
        profile_id: str,
        timeline_id: str,
    ) -> RuntimeAuthorityBinding | None:
        """Read the committed ControlStore fact without a writer snapshot."""

        reader = _connect_readonly(self._location.control_database)
        try:
            row = reader.execute(
                f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
                "WHERE profile_id = ? AND timeline_id = ? AND state = 'active'",
                (profile_id, timeline_id),
            ).fetchone()
        finally:
            reader.close()
        return None if row is None else self._binding_from_row(row)

    def query_binding(
        self,
        *,
        profile_id: str,
        timeline_id: str,
    ) -> RuntimeAuthorityBinding:
        self._require_open()
        profile_id = _canonical_uuid(profile_id, "profile_id")
        timeline_id = _canonical_uuid(timeline_id, "timeline_id")
        lane = self._lanes.get((profile_id, timeline_id))
        if lane is not None:
            self._synchronize_subject_event_seal(lane)
        active = self._read_active_binding(profile_id, timeline_id)
        if active is not None:
            if lane is not None:
                committed_swap_awaiting_lane_recovery = (
                    not lane.accepting
                    and active.predecessor_binding_id == lane.binding.binding_id
                    and active.binding_revision
                    == lane.binding.binding_revision + 1
                    and active.binding_epoch == lane.binding.binding_epoch + 1
                    and active.profile_id == lane.binding.profile_id
                    and active.timeline_id == lane.binding.timeline_id
                )
                if committed_swap_awaiting_lane_recovery:
                    predecessor_qri = self._qri_for_binding(lane.binding)
                    successor_qri = self._qri_for_binding(active)
                    if (
                        successor_qri.predecessor_qualification_id
                        != predecessor_qri.qualification_id
                        or successor_qri.profile_id != predecessor_qri.profile_id
                        or successor_qri.genesis_snapshot_id
                        != predecessor_qri.genesis_snapshot_id
                        or successor_qri.knowledge_snapshot_id
                        != predecessor_qri.knowledge_snapshot_id
                        or successor_qri.isolation_proof
                        != predecessor_qri.isolation_proof
                    ):
                        raise RuntimeHostFailedClosed(
                            "binding-identity-mismatch",
                            "committed successor does not match the stopped predecessor lane",
                        )
                else:
                    self._assert_lane_binding(active, lane)
            return active
        reader = _connect_readonly(self._location.control_database)
        try:
            row = reader.execute(
                f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
                "WHERE profile_id = ? AND timeline_id = ? "
                "ORDER BY binding_revision DESC LIMIT 1",
                (profile_id, timeline_id),
            ).fetchone()
        finally:
            reader.close()
        if row is None:
            raise RuntimeHostRejected(
                "binding-not-found",
                "Profile/Timeline has no RuntimeAuthorityBinding",
            )
        return self._binding_from_row(row)

    def _authority_for_binding(
        self,
        binding: RuntimeAuthorityBinding,
    ) -> _RuntimeBindingAuthority:
        return _RuntimeBindingAuthority(
            authority_scope_id=binding.authority_scope_id,
            profile_id=binding.profile_id,
            timeline_id=binding.timeline_id,
            allowed_intents=ALLOWED_INTENTS,
            allowed_provenance=ALLOWED_PROVENANCE,
            binding_id=binding.binding_id,
            binding_revision=binding.binding_revision,
            binding_epoch=binding.binding_epoch,
            qualification_id=binding.qualification_id,
            qualification_revision=binding.qualification_revision,
            provider_authority=binding.provider_authority,
        )

    def _qri_for_binding(
        self,
        binding: RuntimeAuthorityBinding,
    ) -> QualifiedRuntimeInput:
        studio = SubjectStudio.open(
            self._studio_location,
            policy_kernel=PolicyKernel(),
        )
        try:
            qri = studio.query_qri(publication_key=binding.qri_publication_key)
        except Exception as error:
            raise RuntimeHostFailedClosed(
                "qri-publication-unavailable",
                "active binding QRI could not be recovered",
            ) from error
        finally:
            studio.close()
        if (
            qri.qualification_id != binding.qualification_id
            or qri.qualification_revision != binding.qualification_revision
            or qri.integrity_digest != binding.qri_integrity_digest
            or qri.profile_id != binding.profile_id
            or qri.genesis_snapshot_id != binding.genesis_snapshot_id
            or qri.knowledge_snapshot_id != binding.knowledge_snapshot_id
            or qri.policy_decision_ids != binding.policy_decision_ids
            or qri.capabilities.manifest_version != binding.capability_manifest_version
            or qri.provider_authority != binding.provider_authority
        ):
            raise RuntimeHostFailedClosed(
                "binding-qri-mismatch",
                "active binding no longer matches its published QRI",
            )
        return qri

    def _rebuild_lane(
        self,
        binding: RuntimeAuthorityBinding,
        qri: QualifiedRuntimeInput,
    ) -> _Lane | None:
        self._require_binding_permit(binding)
        if self._verify_published_qri(qri) != qri:
            raise RuntimeHostFailedClosed(
                "binding-qri-mismatch",
                "binding QRI could not be revalidated",
            )
        cognition = self._cognition_assembly.select(qri)
        key = (binding.profile_id, binding.timeline_id)
        existing = self._lanes.get(key)
        if existing is not None:
            if existing.accepting:
                raise RuntimeHostConflict(
                    "second-runtime-owner",
                    "a SubjectRuntime already owns this authority lane",
                )
            existing.worker.close()
            self._lanes.pop(key, None)
        self._claim_instance(binding)
        worker = _RuntimeWorker(
            binding.binding_id,
            lambda: SubjectRuntime._open_bound(
                binding.timeline_root,
                authority=self._authority_for_binding(binding),
                cognition=cognition,
                experienced_at_us=qri.published_at_us,
                runtime_identity=self._runtime_identity,
                root_kind=self._location.root_kind,
                relationship_enabled=self._relationship_enabled,
                _host_token=_HOST_RUNTIME_TOKEN,
                interrupt_at=self._runtime_interrupt_at,
                fault_hook=self._runtime_fault_hook,
            ),
        )
        try:
            gate_state, _gate_epoch, _basis, has_event = worker.call(
                "_binding_health",
                _host_token=_HOST_RUNTIME_TOKEN,
            )
            if gate_state == "retired":
                self._finalize_retired_binding(binding, has_event=has_event)
                worker.close()
                worker = None
                return None
            worker.call(
                "_activate_binding_gate",
                _host_token=_HOST_RUNTIME_TOKEN,
            )
            lane = self._install_lane(binding, qri, worker)
            worker = None
            return lane
        finally:
            if worker is not None:
                worker.close()

    def _finalize_retired_binding(
        self,
        binding: RuntimeAuthorityBinding,
        *,
        has_event: bool,
    ) -> None:
        try:
            _begin(self._writer)
            retired_at_us = _utc_microseconds()
            changed = self._writer.execute(
                """
                UPDATE runtime_authority_binding
                SET state = 'retired',
                    first_subject_event_sealed = CASE
                        WHEN ? THEN 1 ELSE first_subject_event_sealed END,
                    retired_at_us = COALESCE(retired_at_us, ?)
                WHERE binding_id = ? AND state = 'active'
                """,
                (int(has_event), retired_at_us, binding.binding_id),
            )
            if changed.rowcount != 1:
                raise RuntimeHostConflict(
                    "binding-retire-conflict",
                    "retired Timeline gate did not match one active binding",
                )
            self._writer.execute(
                """
                UPDATE runtime_instance_lease
                SET lease_state = 'closed', updated_at_us = ?
                WHERE binding_id = ?
                """,
                (retired_at_us, binding.binding_id),
            )
            self._append_branch_governance_fact(
                binding,
                replaces=None,
                activation=_RETIRE_GOVERNANCE_TRANSITION,
                created_at_us=retired_at_us,
            )
            _commit(self._writer)
        except Exception:
            _rollback_if_needed(self._writer)
            raise

    def _install_lane(
        self,
        binding: RuntimeAuthorityBinding,
        qri: QualifiedRuntimeInput,
        worker: _RuntimeWorker,
    ) -> _Lane:
        key = (binding.profile_id, binding.timeline_id)
        existing = self._lanes.get(key)
        if existing is not None and existing.accepting:
            raise RuntimeHostConflict(
                "second-runtime-owner",
                "a SubjectRuntime already owns this authority lane",
            )
        submission_authorization = (
            self._cognition_assembly.submission_authorization(qri, binding)
        )
        if (
            qri.provider_authority
            in (
                _LOCAL_FIRST_TEST_PROVIDER_AUTHORITY,
                _LOCAL_LLAMA_PROVIDER_AUTHORITY,
            )
            and submission_authorization is None
        ):
            raise RuntimeHostRejected(
                "local-interaction-plan-mismatch",
                "local lane requires its exact QRI-bound submission authorization",
            )
        lane = _Lane(
            binding=binding,
            binding_id=binding.binding_id,
            lane_id=str(uuid5(NAMESPACE_URL, f"m0-12-lane:{binding.binding_id}")),
            worker=worker,
            lock=threading.Lock(),
            submission_authorization=submission_authorization,
        )
        self._lanes[key] = lane
        return lane

    def _claim_instance(self, binding: RuntimeAuthorityBinding) -> None:
        try:
            _begin(self._writer)
            row = self._writer.execute(
                """
                SELECT owner_pid, owner_instance_id, generation, lease_state
                FROM runtime_instance_lease
                WHERE binding_id = ?
                """,
                (binding.binding_id,),
            ).fetchone()
            generation = 1
            if row is not None:
                owner_pid = int(row[0])
                owner_instance_id = str(row[1])
                generation = int(row[2]) + 1
                if (
                    str(row[3]) == "active"
                    and owner_instance_id != self._instance_id
                    and _pid_is_alive(owner_pid)
                ):
                    raise RuntimeHostConflict(
                        "runtime-instance-lease-contended",
                        "another live process-local SubjectRuntime owns this binding",
                    )
            self._writer.execute(
                """
                INSERT INTO runtime_instance_lease (
                    binding_id, owner_pid, owner_instance_id, generation,
                    lease_state, updated_at_us
                ) VALUES (?, ?, ?, ?, 'active', ?)
                ON CONFLICT(binding_id) DO UPDATE SET
                    owner_pid = excluded.owner_pid,
                    owner_instance_id = excluded.owner_instance_id,
                    generation = excluded.generation,
                    lease_state = 'active',
                    updated_at_us = excluded.updated_at_us
                """,
                (
                    binding.binding_id,
                    os.getpid(),
                    self._instance_id,
                    generation,
                    _utc_microseconds(),
                ),
            )
            _commit(self._writer)
        except Exception:
            _rollback_if_needed(self._writer)
            raise

    def _recover_active_bindings(self) -> None:
        rows = self._writer.execute(
            f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
            "WHERE state = 'active' ORDER BY profile_id, timeline_id"
        ).fetchall()
        bindings = tuple(self._binding_from_row(row) for row in rows)
        if self._require_prepared_corrective_case(bindings):
            return
        for binding in bindings:
            target, _members = self._require_structural_binding_permit(binding)
            if target["serving_disposition"] == _BRANCH_HELD:
                raise RuntimeHostRejected(
                    "branch-serving-held",
                    "held branch has no serving permit",
                )
            if target["serving_disposition"] == _BRANCH_RETIRED:
                raise RuntimeHostRejected(
                    "branch-serving-retired",
                    "retired branch has no serving permit",
                )
        recoveries = tuple((binding, self._qri_for_binding(binding)) for binding in bindings)
        for binding, qri in recoveries:
            self._require_binding_permit(binding)
            self._require_governed_timeline_lineage(
                qri,
                timeline_id=binding.timeline_id,
            )
        for binding, qri in recoveries:
            lane = self._rebuild_lane(binding, qri)
            if lane is not None:
                self._synchronize_subject_event_seal(lane)

    def _synchronize_subject_event_seal(self, lane: _Lane) -> None:
        try:
            _state, _epoch, _basis, has_event = lane.worker.call(
                "_binding_health",
                _host_token=_HOST_RUNTIME_TOKEN,
            )
        except Exception:
            return
        if has_event:
            lane.first_event_seen = True
        if lane.first_event_seen and threading.get_ident() == self._owner_thread_id:
            committed = self._read_active_binding(
                lane.binding.profile_id,
                lane.binding.timeline_id,
            )
            if committed is None:
                lane.accepting = False
                raise RuntimeHostFailedClosed(
                    "binding-identity-mismatch",
                    "active binding disappeared while sealing its first event",
                )
            self._assert_lane_binding(committed, lane)
            self._writer.execute(
                """
                UPDATE runtime_authority_binding
                SET first_subject_event_sealed = 1
                WHERE binding_id = ? AND first_subject_event_sealed = 0
                """,
                (lane.binding_id,),
            )
            lane.binding = replace(
                lane.binding,
                first_subject_event_sealed=True,
            )

    def _route(
        self,
        binding: RuntimeAuthorityBinding,
        lane: _Lane,
    ) -> RuntimeRoute:
        self._require_binding_permit(binding)
        return RuntimeRoute(
            binding=self._require_active_binding(
                binding.profile_id,
                binding.timeline_id,
            ),
            lane_id=lane.lane_id,
            health=self.health(
                profile_id=binding.profile_id,
                timeline_id=binding.timeline_id,
            ),
        )

    def health(self, *, profile_id: str, timeline_id: str) -> RuntimeHealth:
        self._require_open()
        key = (
            _canonical_uuid(profile_id, "profile_id"),
            _canonical_uuid(timeline_id, "timeline_id"),
        )
        binding = self._read_active_binding(*key)
        if binding is None:
            raise RuntimeHostRejected(
                "binding-not-active",
                "Profile/Timeline has no active RuntimeAuthorityBinding",
            )
        self._require_binding_permit(binding)
        lane = self._lanes.get(key)
        if lane is None:
            raise RuntimeHostFailedClosed(
                "runtime-lane-unavailable",
                "active binding has no process-local SubjectRuntime lane",
            )
        self._assert_lane_binding(binding, lane)
        gate_state, gate_epoch, basis, has_event = lane.worker.call(
            "_binding_health",
            _host_token=_HOST_RUNTIME_TOKEN,
        )
        return RuntimeHealth(
            binding_id=binding.binding_id,
            lane_id=lane.lane_id,
            healthy=gate_state in {"closed", "open", "draining"},
            serving=lane.accepting and gate_state == "open",
            gate_state=gate_state,
            gate_epoch=gate_epoch,
            timeline_basis=basis,
            first_subject_event_sealed=has_event,
        )

    def _local_serving_health(
        self,
        *,
        profile_id: str,
        timeline_id: str,
        _authorization: _LocalServingAuthorization,
    ) -> RuntimeHealth:
        """Query an authorized local lane without turning eligibility into serving."""

        self._require_open()
        key = (
            _canonical_uuid(profile_id, "profile_id"),
            _canonical_uuid(timeline_id, "timeline_id"),
        )
        binding = self._require_active_binding(*key)
        if (
            type(_authorization) is not _LocalServingAuthorization
            or not _authorization.matches_binding(self._location, binding)
        ):
            raise RuntimeHostRejected(
                "branch-serving-authorization-required",
                "prepared corrective eligibility is not lifecycle query authority",
            )
        self._local_serving_authorization = _authorization
        target, _members = self._require_structural_binding_permit(binding)
        if target["serving_disposition"] != _BRANCH_ELIGIBLE:
            raise RuntimeHostRejected(
                "branch-serving-authorization-required",
                "only the unique eligible corrective member has lifecycle status",
            )
        lane = self._lanes.get(key)
        if lane is not None:
            return self.health(profile_id=key[0], timeline_id=key[1])
        gate_state, gate_epoch, basis, has_event, _hashes, _empty, _one = (
            _corrective_timeline_state(binding)
        )
        active_leases = self._writer.execute(
            "SELECT count(*) FROM runtime_instance_lease "
            "WHERE binding_id = ? AND lease_state = 'active'",
            (binding.binding_id,),
        ).fetchone()
        if gate_state != "closed" or active_leases != (0,):
            raise RuntimeHostFailedClosed(
                "local-serving-stopped-state-invalid",
                "stopped local serving still has an open gate or active lease",
            )
        return RuntimeHealth(
            binding_id=binding.binding_id,
            lane_id=None,
            healthy=True,
            serving=False,
            gate_state=gate_state,
            gate_epoch=gate_epoch,
            timeline_basis=basis,
            first_subject_event_sealed=has_event,
        )

    def _follow_local_serving(
        self,
        operation_ref: OperationRef,
        *,
        profile_id: str,
        timeline_id: str,
        _authorization: _LocalServingAuthorization,
    ) -> RuntimeResult:
        """Observe one terminal local operation without reopening serving."""

        with self._state_lock:
            health = self._local_serving_health(
                profile_id=profile_id,
                timeline_id=timeline_id,
                _authorization=_authorization,
            )
            if health.lane_id is not None:
                with self.lease(
                    profile_id=profile_id,
                    timeline_id=timeline_id,
                ) as lease:
                    return lease.follow(operation_ref)
            binding = self._require_active_binding(profile_id, timeline_id)
            qri = self._qri_for_binding(binding)
            cognition = self._cognition_assembly.select(qri)
            worker = _RuntimeWorker(
                binding.binding_id,
                lambda: SubjectRuntime._open_bound(
                    binding.timeline_root,
                    authority=self._authority_for_binding(binding),
                    cognition=cognition,
                    experienced_at_us=qri.published_at_us,
                    runtime_identity=self._runtime_identity,
                    root_kind=self._location.root_kind,
                    relationship_enabled=self._relationship_enabled,
                    _host_token=_HOST_RUNTIME_TOKEN,
                    interrupt_at=self._runtime_interrupt_at,
                    fault_hook=self._runtime_fault_hook,
                ),
            )
            try:
                result = worker.call("follow", operation_ref, timeout_seconds=0.0)
            finally:
                worker.close()
            if result.snapshot.operation_state not in {
                OperationState.COMPLETED,
                OperationState.FAILED_CLOSED,
                OperationState.INTERRUPTED,
            }:
                raise RuntimeHostRejected(
                    "operation-not-terminal-while-stopped",
                    "stopped local serving never resumes a pending operation",
                )
            return result

    def _stop_local_serving(
        self,
        *,
        profile_id: str,
        timeline_id: str,
        timeout_seconds: float,
        _authorization: _LocalServingAuthorization,
    ) -> RuntimeHealth:
        """Stop one exact local lane with a bounded lease-drain budget."""

        self._local_serving_health(
            profile_id=profile_id,
            timeline_id=timeline_id,
            _authorization=_authorization,
        )
        return self.drain(
            profile_id=profile_id,
            timeline_id=timeline_id,
            _timeout_seconds=timeout_seconds,
        )

    def lease(
        self,
        *,
        profile_id: str,
        timeline_id: str,
    ) -> RuntimeLease:
        self._require_open()
        key = (
            _canonical_uuid(profile_id, "profile_id"),
            _canonical_uuid(timeline_id, "timeline_id"),
        )
        lane = self._lanes.get(key)
        if lane is None:
            if threading.get_ident() == self._owner_thread_id:
                self._require_active_binding(*key)
            raise RuntimeHostRejected(
                "runtime-lane-unavailable",
                "active binding has no process-local runtime lane",
            )
        binding = self._active_binding_for_lease(*key)
        self._require_binding_permit(binding)
        self._assert_lane_binding(binding, lane)
        if not lane.accepting or lane.binding.state is not BindingState.ACTIVE:
            raise RuntimeHostRejected(
                "runtime-lane-unavailable",
                "active binding is not accepting a runtime lease",
            )
        if not lane.lock.acquire(blocking=False):
            raise RuntimeHostConflict(
                "runtime-lease-contended",
                "the Profile/Timeline authority lane is already leased",
            )
        return RuntimeLease(self, lane, binding)

    def drain(
        self,
        *,
        profile_id: str,
        timeline_id: str,
        _timeout_seconds: float | None = None,
    ) -> RuntimeHealth:
        self._require_open()
        if _timeout_seconds is not None and (
            isinstance(_timeout_seconds, bool)
            or not isinstance(_timeout_seconds, (int, float))
            or _timeout_seconds <= 0
            or _timeout_seconds > 30
        ):
            raise ValueError("runtime drain timeout must be in (0, 30]")
        key = (
            _canonical_uuid(profile_id, "profile_id"),
            _canonical_uuid(timeline_id, "timeline_id"),
        )
        with self._state_lock:
            binding = self._require_active_binding(*key)
            if self._is_prepared_corrective_case(binding):
                target, _members = self._require_structural_binding_permit(binding)
                if target["serving_disposition"] == _BRANCH_HELD:
                    raise RuntimeHostRejected(
                        "branch-serving-held",
                        "contained nonconforming branch has no lifecycle authority",
                    )
                authorization = self._local_serving_authorization
                if (
                    type(authorization) is not _LocalServingAuthorization
                    or not authorization.matches_binding(self._location, binding)
                ):
                    raise RuntimeHostRejected(
                        "branch-serving-authorization-required",
                        "prepared corrective eligibility is not lifecycle authority",
                    )
            self._require_binding_permit(binding)
            lane = self._lanes.get(key)
            if lane is None:
                raise RuntimeHostRejected(
                    "runtime-lane-unavailable",
                    "active binding has no lane to drain",
                )
            lane.accepting = False
            acquired = (
                lane.lock.acquire()
                if _timeout_seconds is None
                else lane.lock.acquire(timeout=float(_timeout_seconds))
            )
            if not acquired:
                raise RuntimeHostFailedClosed(
                    "runtime-drain-timeout",
                    "runtime lease did not drain within the bounded stop budget",
                )
            try:
                self._synchronize_subject_event_seal(lane)
                lane.worker.call(
                    "_close_binding_gate",
                    retire=False,
                    _host_token=_HOST_RUNTIME_TOKEN,
                )
                gate_state, gate_epoch, basis, has_event = lane.worker.call(
                    "_binding_health",
                    _host_token=_HOST_RUNTIME_TOKEN,
                )
                lane.worker.close()
                self._writer.execute(
                    """
                    UPDATE runtime_instance_lease
                    SET lease_state = 'closed', updated_at_us = ?
                    WHERE binding_id = ? AND owner_instance_id = ?
                    """,
                    (_utc_microseconds(), lane.binding_id, self._instance_id),
                )
                self._lanes.pop(key, None)
            finally:
                lane.lock.release()
            binding = self._require_active_binding(*key)
            return RuntimeHealth(
                binding_id=binding.binding_id,
                lane_id=lane.lane_id,
                healthy=gate_state == "closed",
                serving=False,
                gate_state=gate_state,
                gate_epoch=gate_epoch,
                timeline_basis=basis,
                first_subject_event_sealed=has_event,
            )

    def retire(
        self,
        *,
        profile_id: str,
        timeline_id: str,
    ) -> RuntimeAuthorityBinding:
        self._require_open()
        key = (
            _canonical_uuid(profile_id, "profile_id"),
            _canonical_uuid(timeline_id, "timeline_id"),
        )
        with self._state_lock:
            binding = self._require_active_binding(*key)
            if self._is_prepared_corrective_case(binding):
                target, _members = self._require_structural_binding_permit(binding)
                if target["serving_disposition"] == _BRANCH_HELD:
                    raise RuntimeHostRejected(
                        "branch-serving-held",
                        "contained nonconforming branch has no lifecycle authority",
                    )
                raise RuntimeHostRejected(
                    "branch-serving-authorization-required",
                    "prepared corrective eligibility is not lifecycle authority",
                )
            self._require_binding_permit(binding)
            lane = self._lanes.get(key)
            qri = self._qri_for_binding(binding)
            temporary_worker: _RuntimeWorker | None = None
            if lane is None:
                self._claim_instance(binding)
                cognition = self._cognition_assembly.select(qri)
                temporary_worker = _RuntimeWorker(
                    binding.binding_id,
                    lambda: SubjectRuntime._open_bound(
                        binding.timeline_root,
                        authority=self._authority_for_binding(binding),
                        cognition=cognition,
                        experienced_at_us=qri.published_at_us,
                        runtime_identity=self._runtime_identity,
                        root_kind=self._location.root_kind,
                        relationship_enabled=self._relationship_enabled,
                        _host_token=_HOST_RUNTIME_TOKEN,
                        interrupt_at=self._runtime_interrupt_at,
                        fault_hook=self._runtime_fault_hook,
                    ),
                )
                worker = temporary_worker
                lock = threading.Lock()
                lock.acquire()
            else:
                lane.accepting = False
                lane.lock.acquire()
                worker = lane.worker
                lock = lane.lock
            try:
                if lane is not None:
                    self._synchronize_subject_event_seal(lane)
                    binding = self._require_active_binding(*key)
                worker.call(
                    "_close_binding_gate",
                    retire=True,
                    _host_token=_HOST_RUNTIME_TOKEN,
                )
                self._hit(RuntimeHostFaultPoint.AFTER_RETIRE_GATE_CLOSED)
                try:
                    _begin(self._writer)
                    retired_at_us = _utc_microseconds()
                    changed = self._writer.execute(
                        """
                        UPDATE runtime_authority_binding
                        SET state = 'retired', retired_at_us = ?
                        WHERE binding_id = ? AND state = 'active'
                        """,
                        (retired_at_us, binding.binding_id),
                    )
                    if changed.rowcount != 1:
                        raise RuntimeHostConflict(
                            "binding-retire-conflict",
                            "active binding changed while it was retiring",
                        )
                    self._writer.execute(
                        """
                        UPDATE runtime_instance_lease
                        SET lease_state = 'closed', updated_at_us = ?
                        WHERE binding_id = ?
                        """,
                        (retired_at_us, binding.binding_id),
                    )
                    self._append_branch_governance_fact(
                        binding,
                        replaces=None,
                        activation=_RETIRE_GOVERNANCE_TRANSITION,
                        created_at_us=retired_at_us,
                    )
                    _commit(self._writer)
                except Exception:
                    _rollback_if_needed(self._writer)
                    raise
                worker.close()
                self._lanes.pop(key, None)
            finally:
                if temporary_worker is not None:
                    temporary_worker.close()
                lock.release()
            return self.query_binding(profile_id=key[0], timeline_id=key[1])

    def close(self) -> None:
        if self._closed:
            return
        first_error: Exception | None = None
        with self._state_lock:
            for key, lane in tuple(self._lanes.items()):
                lane.accepting = False
                lane.lock.acquire()
                try:
                    for action in (
                        lambda: self._synchronize_subject_event_seal(lane),
                        lambda: lane.worker.call(
                            "_close_binding_gate",
                            retire=False,
                            _host_token=_HOST_RUNTIME_TOKEN,
                        ),
                        lane.worker.close,
                        lambda: self._writer.execute(
                            """
                            UPDATE runtime_instance_lease
                            SET lease_state = 'closed', updated_at_us = ?
                            WHERE binding_id = ? AND owner_instance_id = ?
                            """,
                            (
                                _utc_microseconds(),
                                lane.binding_id,
                                self._instance_id,
                            ),
                        ),
                    ):
                        try:
                            action()
                        except Exception as error:
                            if first_error is None:
                                first_error = error
                finally:
                    lane.lock.release()
                self._lanes.pop(key, None)
            try:
                self._writer.execute(
                    """
                    UPDATE runtime_instance_lease
                    SET lease_state = 'closed', updated_at_us = ?
                    WHERE owner_instance_id = ? AND lease_state = 'active'
                    """,
                    (_utc_microseconds(), self._instance_id),
                )
            except Exception as error:
                if first_error is None:
                    first_error = error
            finally:
                self._writer.close()
                self._closed = True
                _release_process_registry(self._location.root_id, self._instance_id)
        if first_error is not None:
            raise first_error


_BINDING_COLUMNS = """
binding_id, binding_revision, binding_epoch, state,
profile_id, timeline_id, authority_scope_id,
qualification_id, qualification_revision, qri_publication_key,
qri_integrity_digest, genesis_snapshot_id, knowledge_snapshot_id,
policy_decision_ids_json, capability_manifest_version, provider_authority,
runtime_kind, runtime_contract_version, studio_root_id, studio_store_id,
host_root_id, host_control_store_id, timeline_root_json, timeline_root_id,
timeline_control_store_id, timeline_store_id, predecessor_binding_id,
first_subject_event_sealed, created_at_us, activated_at_us, retired_at_us
""".replace("\n", " ").strip()


_CONTROL_DDL = (
    """
    CREATE TABLE host_manifest (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        root_id TEXT NOT NULL UNIQUE,
        control_store_id TEXT NOT NULL UNIQUE,
        studio_root_id TEXT NOT NULL,
        studio_store_id TEXT NOT NULL,
        schema_family TEXT NOT NULL,
        schema_version INTEGER NOT NULL,
        contract_version TEXT NOT NULL,
        persistence_version TEXT NOT NULL,
        root_epoch INTEGER NOT NULL,
        created_at_us INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE runtime_authority_binding (
        binding_id TEXT PRIMARY KEY,
        binding_revision INTEGER NOT NULL CHECK (binding_revision >= 1),
        binding_epoch INTEGER NOT NULL CHECK (binding_epoch >= 1),
        state TEXT NOT NULL CHECK (
            state IN ('validated', 'active', 'rejected', 'invalidated', 'retired')
        ),
        profile_id TEXT NOT NULL,
        timeline_id TEXT NOT NULL,
        authority_scope_id TEXT NOT NULL UNIQUE,
        qualification_id TEXT NOT NULL,
        qualification_revision INTEGER NOT NULL CHECK (qualification_revision >= 1),
        qri_publication_key TEXT NOT NULL,
        qri_integrity_digest TEXT NOT NULL,
        genesis_snapshot_id TEXT NOT NULL,
        knowledge_snapshot_id TEXT NOT NULL,
        policy_decision_ids_json TEXT NOT NULL,
        capability_manifest_version TEXT NOT NULL,
        provider_authority TEXT NOT NULL,
        runtime_kind TEXT NOT NULL CHECK (runtime_kind = 'mature-canonical'),
        runtime_contract_version TEXT NOT NULL,
        studio_root_id TEXT NOT NULL,
        studio_store_id TEXT NOT NULL,
        host_root_id TEXT NOT NULL,
        host_control_store_id TEXT NOT NULL,
        timeline_root_json TEXT NOT NULL,
        timeline_root_id TEXT NOT NULL UNIQUE,
        timeline_control_store_id TEXT NOT NULL UNIQUE,
        timeline_store_id TEXT NOT NULL UNIQUE,
        predecessor_binding_id TEXT REFERENCES runtime_authority_binding(binding_id),
        first_subject_event_sealed INTEGER NOT NULL CHECK (
            first_subject_event_sealed IN (0, 1)
        ),
        created_at_us INTEGER NOT NULL,
        activated_at_us INTEGER,
        retired_at_us INTEGER,
        UNIQUE (profile_id, timeline_id, binding_revision),
        UNIQUE (profile_id, timeline_id, binding_epoch)
    )
    """,
    """
    CREATE UNIQUE INDEX one_active_binding_per_timeline
    ON runtime_authority_binding(profile_id, timeline_id)
    WHERE state = 'active'
    """,
    """
    CREATE TABLE runtime_instance_lease (
        binding_id TEXT PRIMARY KEY
            REFERENCES runtime_authority_binding(binding_id) ON DELETE RESTRICT,
        owner_pid INTEGER NOT NULL CHECK (owner_pid > 0),
        owner_instance_id TEXT NOT NULL,
        generation INTEGER NOT NULL CHECK (generation >= 1),
        lease_state TEXT NOT NULL CHECK (
            lease_state IN ('active', 'draining', 'closed')
        ),
        updated_at_us INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE branch_governance_fact (
        fact_id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL,
        host_root_id TEXT NOT NULL,
        host_control_store_id TEXT NOT NULL,
        sequence INTEGER NOT NULL CHECK (sequence >= 1),
        previous_fact_digest TEXT,
        fact_digest TEXT NOT NULL UNIQUE,
        created_at_us INTEGER NOT NULL,
        UNIQUE (case_id, sequence)
    )
    """,
    """
    CREATE TABLE branch_governance_member (
        fact_id TEXT NOT NULL
            REFERENCES branch_governance_fact(fact_id) ON DELETE RESTRICT,
        binding_id TEXT NOT NULL
            REFERENCES runtime_authority_binding(binding_id) ON DELETE RESTRICT,
        binding_revision INTEGER NOT NULL CHECK (binding_revision >= 1),
        binding_epoch INTEGER NOT NULL CHECK (binding_epoch >= 1),
        profile_id TEXT NOT NULL,
        timeline_id TEXT NOT NULL,
        authority_scope_id TEXT NOT NULL,
        qualification_id TEXT NOT NULL,
        qri_integrity_digest TEXT NOT NULL,
        timeline_root_id TEXT NOT NULL,
        timeline_control_store_id TEXT NOT NULL,
        timeline_store_id TEXT NOT NULL,
        classification TEXT NOT NULL CHECK (
            classification IN ('normal', 'nonconforming-experimental')
        ),
        serving_disposition TEXT NOT NULL CHECK (
            serving_disposition IN ('eligible', 'held', 'retired')
        ),
        PRIMARY KEY (fact_id, binding_id)
    )
    """,
    """
    CREATE TRIGGER branch_governance_fact_no_update
    BEFORE UPDATE ON branch_governance_fact
    BEGIN
        SELECT RAISE(ABORT, 'branch-governance-append-only');
    END
    """,
    """
    CREATE TRIGGER branch_governance_fact_no_delete
    BEFORE DELETE ON branch_governance_fact
    BEGIN
        SELECT RAISE(ABORT, 'branch-governance-append-only');
    END
    """,
    """
    CREATE TRIGGER branch_governance_member_no_update
    BEFORE UPDATE ON branch_governance_member
    BEGIN
        SELECT RAISE(ABORT, 'branch-governance-append-only');
    END
    """,
    """
    CREATE TRIGGER branch_governance_member_no_delete
    BEFORE DELETE ON branch_governance_member
    BEGIN
        SELECT RAISE(ABORT, 'branch-governance-append-only');
    END
    """,
)
_CONTROL_TABLES = frozenset(
    {
        "host_manifest",
        "runtime_authority_binding",
        "runtime_instance_lease",
        "branch_governance_fact",
        "branch_governance_member",
    }
)
_CONTROL_TRIGGERS = frozenset(
    {
        "branch_governance_fact_no_update",
        "branch_governance_fact_no_delete",
        "branch_governance_member_no_update",
        "branch_governance_member_no_delete",
    }
)
_CONTROL_V1_TABLES = frozenset(
    {"host_manifest", "runtime_authority_binding", "runtime_instance_lease"}
)
_CONTROL_V1_TO_V2_DDL = _CONTROL_DDL[4:]


def _canonical_uuid(value: str, field: str) -> str:
    try:
        canonical = str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as error:
        raise RuntimeHostRejected(
            "invalid-identity", f"{field} must be a UUID"
        ) from error
    if canonical != str(value):
        raise RuntimeHostRejected("invalid-identity", f"{field} must be canonical")
    return canonical


def _is_sha256(value: str) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        return bytes.fromhex(value).hex() == value
    except ValueError:
        return False


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _branch_governance_member(
    binding: RuntimeAuthorityBinding,
    *,
    classification: str,
    serving_disposition: str,
) -> dict[str, object]:
    return {
        "binding_id": binding.binding_id,
        "binding_revision": binding.binding_revision,
        "binding_epoch": binding.binding_epoch,
        "profile_id": binding.profile_id,
        "timeline_id": binding.timeline_id,
        "authority_scope_id": binding.authority_scope_id,
        "qualification_id": binding.qualification_id,
        "qri_integrity_digest": binding.qri_integrity_digest,
        "timeline_root_id": binding.timeline_root.root_id,
        "timeline_control_store_id": binding.timeline_root.control_store_id,
        "timeline_store_id": binding.timeline_root.timeline_store_id,
        "classification": classification,
        "serving_disposition": serving_disposition,
    }


def _branch_governance_member_from_row(
    row: sqlite3.Row,
) -> dict[str, object]:
    fields = (
        "binding_id",
        "binding_revision",
        "binding_epoch",
        "profile_id",
        "timeline_id",
        "authority_scope_id",
        "qualification_id",
        "qri_integrity_digest",
        "timeline_root_id",
        "timeline_control_store_id",
        "timeline_store_id",
        "classification",
        "serving_disposition",
    )
    return {
        field: int(value)
        if field in {"binding_revision", "binding_epoch"}
        else str(value)
        for field, value in zip(fields, row, strict=True)
    }


def _branch_governance_member_matches(
    member: Mapping[str, object],
    binding: RuntimeAuthorityBinding,
) -> bool:
    return all(
        member[field] == expected
        for field, expected in {
            "binding_id": binding.binding_id,
            "binding_revision": binding.binding_revision,
            "binding_epoch": binding.binding_epoch,
            "profile_id": binding.profile_id,
            "timeline_id": binding.timeline_id,
            "authority_scope_id": binding.authority_scope_id,
            "qualification_id": binding.qualification_id,
            "qri_integrity_digest": binding.qri_integrity_digest,
            "timeline_root_id": binding.timeline_root.root_id,
            "timeline_control_store_id": binding.timeline_root.control_store_id,
            "timeline_store_id": binding.timeline_root.timeline_store_id,
        }.items()
    )


def _branch_governance_fact_digest(
    *,
    case_id: str,
    host_root_id: str,
    host_control_store_id: str,
    sequence: int,
    previous_fact_digest: str | None,
    members: list[dict[str, object]] | tuple[dict[str, object], ...],
    corrective_preparation: Mapping[str, object] | None = None,
) -> str:
    payload = {
        "case_id": case_id,
        "host_root_id": host_root_id,
        "host_control_store_id": host_control_store_id,
        "sequence": sequence,
        "previous_fact_digest": previous_fact_digest,
        "members": sorted(members, key=lambda member: str(member["binding_id"])),
        **(
            {"corrective_preparation": corrective_preparation}
            if corrective_preparation is not None
            else {}
        ),
    }
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _utc_microseconds() -> int:
    return time_ns() // 1_000


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


def _validate_runtime_base(
    runtime_base: Path,
    studio_location: StudioRootRef,
) -> Path:
    if studio_location.root_kind == HOST_ROOT_KIND:
        return _validate_test_base(runtime_base)
    if studio_location.root_kind != EXPERIMENTAL_ROOT_KIND:
        raise RuntimeHostRejected(
            "host-root-kind-not-allowed",
            "RuntimeHost root kind is incompatible with Studio authority",
        )
    requested = Path(runtime_base)
    if not requested.is_absolute() or any(
        character in os.fspath(requested) for character in _WILDCARD_OR_EXPANSION
    ):
        raise RuntimeHostRejected(
            "host-root-not-allowed",
            "experimental RuntimeHost base must be exact and absolute",
        )
    studio = SubjectStudio.open(
        studio_location,
        policy_kernel=PolicyKernel(),
    )
    studio.close()
    try:
        expected = studio_location.root.parents[2].resolve(strict=True)
        resolved = requested.resolve(strict=True)
        anchor = Path(requested.anchor).resolve(strict=True)
    except OSError as error:
        raise RuntimeHostFailedClosed(
            "host-root-not-allowed",
            "experimental RuntimeHost base could not be verified",
        ) from error
    if (
        resolved != expected
        or _has_linklike_component(requested, anchor)
        or any(
            part.casefold() in _RESERVED_TEST_PATH_SEGMENTS for part in resolved.parts
        )
    ):
        raise RuntimeHostRejected(
            "host-root-not-allowed",
            "experimental RuntimeHost base differs from Studio authority",
        )
    return resolved


def _validate_test_base(test_base: Path) -> Path:
    requested = Path(test_base)
    if any(character in os.fspath(requested) for character in _WILDCARD_OR_EXPANSION):
        raise RuntimeHostRejected(
            "host-root-not-allowed",
            "RuntimeHost test root cannot contain wildcard or expansion syntax",
        )
    if not requested.is_absolute():
        raise RuntimeHostRejected(
            "host-root-not-allowed",
            "RuntimeHost test root must be explicit and absolute",
        )
    temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
    if _has_linklike_component(requested, temporary_root):
        raise RuntimeHostRejected(
            "host-root-not-allowed",
            "RuntimeHost test root must not traverse a link or junction",
        )
    ancestor = _nearest_existing_ancestor(requested)
    try:
        resolved_ancestor = ancestor.resolve(strict=True)
    except OSError as error:
        raise RuntimeHostFailedClosed(
            "host-root-not-allowed",
            "RuntimeHost test root ancestor could not be verified",
        ) from error
    if not _is_relative_to(resolved_ancestor, temporary_root):
        raise RuntimeHostRejected(
            "host-root-not-allowed",
            "RuntimeHost root is outside the fresh temporary authority",
        )
    prospective = requested.resolve(strict=False)
    if not _is_relative_to(prospective, temporary_root):
        raise RuntimeHostRejected(
            "host-root-not-allowed",
            "RuntimeHost root escapes the fresh temporary authority",
        )
    relative = prospective.relative_to(temporary_root)
    if any(part.casefold() in _RESERVED_TEST_PATH_SEGMENTS for part in relative.parts):
        raise RuntimeHostRejected(
            "host-root-not-allowed",
            "RuntimeHost root contains a reserved path segment",
        )
    try:
        requested.mkdir(parents=True, exist_ok=True)
        resolved = requested.resolve(strict=True)
    except OSError as error:
        raise RuntimeHostFailedClosed(
            "host-root-not-allowed",
            "RuntimeHost test root could not be prepared",
        ) from error
    if not _is_relative_to(resolved, temporary_root) or _has_linklike_component(
        requested, temporary_root
    ):
        raise RuntimeHostRejected(
            "host-root-not-allowed",
            "RuntimeHost root is outside the fresh temporary authority",
        )
    return resolved


def _validate_existing_root(
    root: Path,
    expected_root_id: str,
    *,
    root_kind: str = HOST_ROOT_KIND,
    studio_location: StudioRootRef | None = None,
) -> Path:
    if not root.is_absolute():
        raise RuntimeHostRejected(
            "host-root-not-allowed",
            "RuntimeHost root must be absolute",
        )
    if root_kind not in _HOST_ROOT_KINDS:
        raise RuntimeHostRejected(
            "host-root-kind-not-allowed",
            "RuntimeHost root kind is not recognized",
        )
    temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
    anchor = (
        temporary_root
        if root_kind == HOST_ROOT_KIND
        else Path(root.anchor).resolve(strict=True)
    )
    if _has_linklike_component(root, anchor):
        raise RuntimeHostRejected(
            "host-root-not-allowed",
            "RuntimeHost root must not traverse a link or junction",
        )
    try:
        resolved = root.resolve(strict=True)
    except OSError as error:
        raise RuntimeHostFailedClosed(
            "host-root-not-allowed",
            "RuntimeHost root cannot be resolved",
        ) from error
    if (
        (root_kind == HOST_ROOT_KIND and not _is_relative_to(resolved, temporary_root))
        or resolved.name != expected_root_id
        or resolved.parent.name != "host-roots"
        or resolved.parent.parent.name != "mature-runtime-m0"
    ):
        raise RuntimeHostRejected(
            "host-root-not-allowed",
            "RuntimeHost root layout or boundary is invalid",
        )
    if root_kind == EXPERIMENTAL_ROOT_KIND:
        if (
            studio_location is None
            or studio_location.root_kind != EXPERIMENTAL_ROOT_KIND
        ):
            raise RuntimeHostRejected(
                "host-root-not-allowed",
                "experimental Host requires experimental Studio authority",
            )
        try:
            studio_base = studio_location.root.parents[2].resolve(strict=True)
        except OSError as error:
            raise RuntimeHostFailedClosed(
                "host-root-not-allowed",
                "experimental Studio base could not be verified",
            ) from error
        if resolved.parents[2] != studio_base or any(
            part.casefold() in _RESERVED_TEST_PATH_SEGMENTS for part in resolved.parts
        ):
            raise RuntimeHostRejected(
                "host-root-not-allowed",
                "experimental Host is outside its Studio experiment",
            )
    for path in (resolved, resolved / "root.identity", resolved / "control"):
        if _is_linklike(path):
            raise RuntimeHostRejected(
                "host-root-not-allowed",
                "RuntimeHost root must not traverse a link or junction",
            )
    return resolved


def _write_root_identity(
    location: RuntimeHostRootRef,
    studio_location: StudioRootRef,
) -> None:
    if location.root_kind != studio_location.root_kind:
        raise RuntimeHostRejected(
            "host-root-kind-mismatch",
            "RuntimeHost and Studio root kinds must match",
        )
    identity = {
        "format": HOST_ROOT_FORMAT,
        "root_epoch": HOST_ROOT_EPOCH,
        "root_id": location.root_id,
        "root_kind": location.root_kind,
        "control_store_id": location.control_store_id,
        "studio_root_id": studio_location.root_id,
        "studio_store_id": studio_location.profile_store_id,
    }
    with (location.root / "root.identity").open(
        "x", encoding="utf-8", newline="\n"
    ) as target:
        json.dump(
            identity, target, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
        target.write("\n")


def _read_root_identity(
    location: RuntimeHostRootRef,
    studio_location: StudioRootRef,
) -> None:
    if location.root_kind != studio_location.root_kind:
        raise RuntimeHostRejected(
            "host-root-kind-mismatch",
            "RuntimeHost and Studio root kinds must match",
        )
    path = location.root / "root.identity"
    if not path.is_file() or path.is_symlink() or path.stat().st_nlink != 1:
        raise RuntimeHostFailedClosed(
            "host-root-identity-mismatch",
            "RuntimeHost root identity is missing or linked",
        )
    try:
        observed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeHostFailedClosed(
            "host-root-identity-mismatch",
            "RuntimeHost root identity is unreadable",
        ) from error
    expected = {
        "format": HOST_ROOT_FORMAT,
        "root_epoch": HOST_ROOT_EPOCH,
        "root_id": location.root_id,
        "root_kind": location.root_kind,
        "control_store_id": location.control_store_id,
        "studio_root_id": studio_location.root_id,
        "studio_store_id": studio_location.profile_store_id,
    }
    if observed != expected:
        raise RuntimeHostFailedClosed(
            "host-root-identity-mismatch",
            "RuntimeHost root identity does not match its reference",
        )


def _sqlite_uri(path: Path, mode: str) -> str:
    return f"{path.resolve().as_uri()}?mode={mode}"


def _connect_new(path: Path) -> sqlite3.Connection:
    if path.exists():
        raise RuntimeHostFailedClosed(
            "host-store-already-exists",
            "new RuntimeHost ControlStore must not already exist",
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
        mode = str(connection.execute("PRAGMA journal_mode = DELETE").fetchone()[0])
        connection.execute("PRAGMA synchronous = EXTRA")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA secure_delete = ON")
        connection.execute("PRAGMA busy_timeout = 2000")
        if mode.casefold() != "delete":
            raise RuntimeHostFailedClosed(
                "host-store-profile-mismatch",
                "RuntimeHost ControlStore did not enter DELETE journal mode",
            )
        return connection
    except RuntimeHostProblem:
        raise
    except sqlite3.Error as error:
        raise RuntimeHostFailedClosed(
            "host-store-create-failed",
            "RuntimeHost ControlStore could not be created",
        ) from error


def _connect_existing(path: Path) -> sqlite3.Connection:
    if not path.is_file() or path.is_symlink() or path.stat().st_nlink != 1:
        raise RuntimeHostFailedClosed(
            "host-store-missing",
            "RuntimeHost ControlStore is missing or linked",
        )
    try:
        connection = sqlite3.connect(
            _sqlite_uri(path, "rw"),
            uri=True,
            autocommit=True,
            timeout=2.0,
            check_same_thread=False,
        )
        connection.execute("PRAGMA synchronous = EXTRA")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA secure_delete = ON")
        connection.execute("PRAGMA busy_timeout = 2000")
        return connection
    except sqlite3.Error as error:
        raise RuntimeHostFailedClosed(
            "host-store-open-failed",
            "RuntimeHost ControlStore could not be opened",
        ) from error


def _connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file() or path.is_symlink() or path.stat().st_nlink != 1:
        raise RuntimeHostFailedClosed(
            "host-store-missing",
            "RuntimeHost ControlStore is missing or linked",
        )
    try:
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
        connection.execute("PRAGMA busy_timeout = 2000")
        return connection
    except sqlite3.Error as error:
        raise RuntimeHostFailedClosed(
            "host-store-open-failed",
            "RuntimeHost ControlStore could not be opened read-only",
        ) from error


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _forward_governance_database_paths(
    location: RuntimeHostRootRef,
    studio_location: StudioRootRef,
    predecessor: RuntimeAuthorityBinding,
    successor: RuntimeAuthorityBinding,
) -> dict[str, Path]:
    return {
        "profile_database": studio_location.profile_database,
        "host_database": location.control_database,
        "predecessor_control_database": predecessor.timeline_root.control_database,
        "predecessor_timeline_database": predecessor.timeline_root.timeline_database,
        "successor_control_database": successor.timeline_root.control_database,
        "successor_timeline_database": successor.timeline_root.timeline_database,
    }


def _forward_governance_root_identity_paths(
    location: RuntimeHostRootRef,
    studio_location: StudioRootRef,
    predecessor: RuntimeAuthorityBinding,
    successor: RuntimeAuthorityBinding,
) -> dict[str, Path]:
    return {
        "studio_root_identity": studio_location.root / "root.identity",
        "host_root_identity": location.root / "root.identity",
        "predecessor_root_identity": predecessor.timeline_root.root / "root.identity",
        "successor_root_identity": successor.timeline_root.root / "root.identity",
    }


def _verify_forward_governance_plan(plan: _ForwardGovernanceInstallPlan) -> None:
    """Reissue every derived field; the supplied object is never trusted alone."""

    expected = _ForwardGovernanceInstallPlan._issue(
        source_result_sha256=plan.source_result_sha256,
        location=plan.location,
        studio_location=plan.studio_location,
        database_sha256=plan.database_sha256,
        root_identity_sha256=plan.root_identity_sha256,
        lease_rows=plan.lease_rows,
        predecessor=plan.predecessor,
        successor=plan.successor,
        _authority=_FORWARD_GOVERNANCE_INSTALL_AUTHORITY,
    )
    if plan != expected:
        raise RuntimeHostFailedClosed(
            "forward-governance-plan-mismatch",
            "forward governance plan differs from its canonical reissuance",
        )


def _verify_forward_governance_exact_roots(
    *,
    location: RuntimeHostRootRef,
    studio_location: StudioRootRef,
    plan: _ForwardGovernanceInstallPlan,
) -> None:
    """Verify all four root identities before opening any canonical database."""

    _validate_existing_root(
        location.root,
        location.root_id,
        root_kind=location.root_kind,
        studio_location=studio_location,
    )
    _read_root_identity(location, studio_location)
    _validate_studio_existing_root(
        studio_location.root,
        studio_location.root_id,
        studio_location.root_kind,
    )
    _read_studio_root_identity(studio_location)
    for binding in (plan.predecessor, plan.successor):
        root = binding.timeline_root
        _validate_timeline_existing_root(
            root.root,
            root.root_id,
            root_kind=root.root_kind,
        )
        _read_timeline_root_identity(root.root, root.root_id, root.root_kind)
    identity_paths = _forward_governance_root_identity_paths(
        location,
        studio_location,
        plan.predecessor,
        plan.successor,
    )
    _verify_forward_governance_regular_paths(identity_paths.values())
    observed = {name: _file_sha256(path) for name, path in identity_paths.items()}
    if observed != plan.root_identity_sha256:
        raise RuntimeHostFailedClosed(
            "forward-governance-preflight-mismatch",
            "a canonical root identity differs from the confirmed plan",
        )


def _verify_forward_governance_nonhost_stores(
    *,
    studio_location: StudioRootRef,
    plan: _ForwardGovernanceInstallPlan,
) -> None:
    profile = _connect_readonly(studio_location.profile_database)
    try:
        _verify_studio_store(studio_location, profile)
    finally:
        profile.close()
    for binding in (plan.predecessor, plan.successor):
        root = binding.timeline_root
        control = _connect_readonly(root.control_database)
        timeline = _connect_readonly(root.timeline_database)
        try:
            for connection in (control, timeline):
                _verify_timeline_connection_profile(connection)
            _verify_timeline_manifest(
                control,
                root_id=root.root_id,
                store_id=root.control_store_id,
                store_kind="control",
                schema_family=TIMELINE_CONTROL_SCHEMA_FAMILY,
            )
            _verify_timeline_store_integrity(
                control,
                expected_tables=_TIMELINE_CONTROL_TABLES,
            )
            registration = control.execute(
                "SELECT timeline_store_id, relative_database_path, "
                "registration_state FROM timeline_registration WHERE timeline_id = ?",
                (root.timeline_id,),
            ).fetchone()
            if registration != (
                root.timeline_store_id,
                f"timelines/{root.timeline_id}/timeline.sqlite3",
                "ready",
            ):
                raise RuntimeHostFailedClosed(
                    "forward-governance-preflight-mismatch",
                    "Timeline registration differs from its confirmed root",
                )
            _verify_timeline_manifest(
                timeline,
                root_id=root.root_id,
                store_id=root.timeline_store_id,
                store_kind="timeline",
                schema_family=TIMELINE_SCHEMA_FAMILY,
            )
            _verify_timeline_store_integrity(
                timeline,
                expected_tables=_TIMELINE_TABLES,
            )
            gate = timeline.execute(
                "SELECT binding_id, binding_revision, binding_epoch, profile_id, "
                "timeline_id, authority_scope_id, qualification_id, "
                "qualification_revision, provider_authority, gate_state "
                "FROM admission_gate WHERE singleton = 1"
            ).fetchone()
            if gate is None or tuple(gate) != (
                binding.binding_id,
                binding.binding_revision,
                binding.binding_epoch,
                binding.profile_id,
                binding.timeline_id,
                binding.authority_scope_id,
                binding.qualification_id,
                binding.qualification_revision,
                binding.provider_authority,
                "closed",
            ):
                raise RuntimeHostFailedClosed(
                    "forward-governance-preflight-mismatch",
                    "Timeline gate differs from the confirmed closed binding",
                )
        finally:
            timeline.close()
            control.close()


def _hold_forward_governance_source_snapshots(
    paths: Mapping[str, Path],
) -> tuple[sqlite3.Connection, ...]:
    readers: list[sqlite3.Connection] = []
    try:
        for name, path in sorted(paths.items()):
            if name == "host_database":
                continue
            reader = _connect_readonly(path)
            reader.execute("BEGIN")
            reader.execute("SELECT count(*) FROM sqlite_schema").fetchone()
            readers.append(reader)
        return tuple(readers)
    except Exception:
        for reader in readers:
            try:
                reader.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            reader.close()
        raise


def _verify_forward_governance_paths(paths: Mapping[str, Path]) -> None:
    _verify_forward_governance_regular_paths(paths.values(), sqlite=True)


def _verify_forward_governance_regular_paths(
    paths: object,
    *,
    sqlite: bool = False,
) -> None:
    for path in paths:
        if (
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_nlink != 1
            or _has_linklike_component(path, Path(path.anchor).resolve(strict=True))
        ):
            raise RuntimeHostFailedClosed(
                "forward-governance-preflight-mismatch",
                "a confirmed database path is missing, linked, or not regular",
            )
        if sqlite:
            for suffix in ("-journal", "-wal", "-shm"):
                if path.with_name(path.name + suffix).exists():
                    raise RuntimeHostFailedClosed(
                        "forward-governance-preflight-mismatch",
                        "a confirmed database has an SQLite sidecar",
                    )


def _verify_forward_governance_v1_preimage(
    writer: sqlite3.Connection,
    *,
    location: RuntimeHostRootRef,
    studio_location: StudioRootRef,
    plan: _ForwardGovernanceInstallPlan,
) -> None:
    user_version = int(writer.execute("PRAGMA user_version").fetchone()[0])
    manifest = writer.execute(
        """
        SELECT root_id, control_store_id, studio_root_id, studio_store_id,
               schema_family, schema_version, contract_version,
               persistence_version, root_epoch
        FROM host_manifest WHERE singleton = 1
        """
    ).fetchone()
    tables = frozenset(
        str(row[0])
        for row in writer.execute(
            "SELECT name FROM sqlite_schema "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    )
    triggers = frozenset(
        str(row[0])
        for row in writer.execute("SELECT name FROM sqlite_schema WHERE type = 'trigger'")
    )
    expected_manifest = (
        location.root_id,
        location.control_store_id,
        studio_location.root_id,
        studio_location.profile_store_id,
        HOST_SCHEMA_FAMILY,
        1,
        CONTRACT_VERSION,
        PERSISTENCE_VERSION,
        HOST_ROOT_EPOCH,
    )
    if (
        user_version != 1
        or manifest != expected_manifest
        or tables != _CONTROL_V1_TABLES
        or triggers
    ):
        raise RuntimeHostFailedClosed(
            "forward-governance-schema-conflict",
            "Host ControlStore is not the confirmed clean schema-v1 preimage",
        )
    rows = writer.execute(
        f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
        "ORDER BY binding_id"
    ).fetchall()
    verifier = object.__new__(RuntimeHost)
    verifier._location = location
    verifier._studio_location = studio_location
    observed = tuple(RuntimeHost._binding_from_row(verifier, row) for row in rows)
    if observed != tuple(sorted((plan.predecessor, plan.successor), key=lambda item: item.binding_id)):
        raise RuntimeHostFailedClosed(
            "forward-governance-preflight-mismatch",
            "Host bindings differ from the confirmed containment plan",
        )
    leases = writer.execute(
        "SELECT binding_id, owner_pid, owner_instance_id, generation, "
        "lease_state, updated_at_us FROM runtime_instance_lease ORDER BY binding_id"
    ).fetchall()
    if (
        tuple(tuple(row) for row in leases) != plan.lease_rows
        or any(row[4] != "closed" for row in plan.lease_rows)
    ):
        raise RuntimeHostFailedClosed(
            "forward-governance-live-lease",
            "containment installation requires the exact two confirmed closed leases",
        )


def _forward_governance_installed_receipt(
    *,
    location: RuntimeHostRootRef,
    studio_location: StudioRootRef,
    plan: _ForwardGovernanceInstallPlan,
    paths: Mapping[str, Path],
    before: Mapping[str, str],
) -> _ForwardGovernanceInstallReceipt | None:
    reader = _connect_readonly(location.control_database)
    try:
        user_version = int(reader.execute("PRAGMA user_version").fetchone()[0])
        schema_version_row = reader.execute(
            "SELECT schema_version FROM host_manifest WHERE singleton = 1"
        ).fetchone()
        if user_version == 1 and schema_version_row == (1,):
            return None
        if user_version != HOST_SCHEMA_VERSION or schema_version_row != (
            HOST_SCHEMA_VERSION,
        ):
            raise RuntimeHostFailedClosed(
                "forward-governance-incomplete-or-unknown",
                "Host schema is neither the confirmed v1 preimage nor exact v2 result",
            )
        try:
            _verify_control(location, studio_location, reader)
        except RuntimeHostProblem as error:
            raise RuntimeHostFailedClosed(
                "forward-governance-incomplete-or-unknown",
                "existing v2 Host identity is not the exact installed result",
            ) from error
        tables = frozenset(
            str(row[0])
            for row in reader.execute(
                "SELECT name FROM sqlite_schema "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        )
        triggers = frozenset(
            str(row[0])
            for row in reader.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'trigger'"
                )
        )
        if tables != _CONTROL_TABLES or triggers != _CONTROL_TRIGGERS:
            raise RuntimeHostFailedClosed(
                "forward-governance-incomplete-or-unknown",
                "existing v2 schema is incomplete or has unknown objects",
            )
        fact = reader.execute(
            """
            SELECT fact_id, case_id, host_root_id, host_control_store_id,
                   sequence, previous_fact_digest, fact_digest
            FROM branch_governance_fact
            """
        ).fetchall()
        member_rows = reader.execute(
            """
            SELECT binding_id, binding_revision, binding_epoch, profile_id,
                   timeline_id, authority_scope_id, qualification_id,
                   qri_integrity_digest, timeline_root_id,
                   timeline_control_store_id, timeline_store_id,
                   classification, serving_disposition
            FROM branch_governance_member WHERE fact_id = ? ORDER BY binding_id
            """,
            (plan.fact_id,),
        ).fetchall()
        expected_members = sorted(
            (
                tuple(
                    _branch_governance_member(
                        plan.predecessor,
                        classification=_BRANCH_NORMAL,
                        serving_disposition=_BRANCH_HELD,
                    ).values()
                ),
                tuple(
                    _branch_governance_member(
                        plan.successor,
                        classification=_BRANCH_NONCONFORMING,
                        serving_disposition=_BRANCH_HELD,
                    ).values()
                ),
            )
        )
        exact_fact = [
            (
                plan.fact_id,
                plan.case_id,
                location.root_id,
                location.control_store_id,
                1,
                None,
                plan.fact_digest,
            )
        ]
        if (
            [tuple(row) for row in fact] != exact_fact
            or sorted(tuple(row) for row in member_rows) != expected_members
        ):
            raise RuntimeHostFailedClosed(
                "forward-governance-incomplete-or-unknown",
                "existing v2 governance state does not exactly match this plan",
            )
        verifier = object.__new__(RuntimeHost)
        verifier._location = location
        verifier._studio_location = studio_location
        rows = reader.execute(
            f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding ORDER BY binding_id"
        ).fetchall()
        observed = tuple(RuntimeHost._binding_from_row(verifier, row) for row in rows)
        if observed != tuple(
            sorted((plan.predecessor, plan.successor), key=lambda item: item.binding_id)
        ):
            raise RuntimeHostFailedClosed(
                "forward-governance-preflight-mismatch",
                "installed governance members no longer match their bindings",
            )
        lease_rows = tuple(
            tuple(row)
            for row in reader.execute(
                "SELECT binding_id, owner_pid, owner_instance_id, generation, "
                "lease_state, updated_at_us FROM runtime_instance_lease "
                "ORDER BY binding_id"
            ).fetchall()
        )
        if lease_rows != plan.lease_rows or any(
            row[4] != "closed" for row in lease_rows
        ):
            raise RuntimeHostFailedClosed(
                "forward-governance-incomplete-or-unknown",
                "installed containment leases differ from the confirmed closed state",
            )
    finally:
        reader.close()
    expected_non_host = plan.database_sha256
    if any(
        before[name] != expected_non_host[name]
        for name in paths
        if name != "host_database"
    ):
        raise RuntimeHostFailedClosed(
            "forward-governance-preflight-mismatch",
            "a non-Host database changed after containment installation",
        )
    return _ForwardGovernanceInstallReceipt(
        installation_id=plan.installation_id,
        status="already-applied",
        fact_id=plan.fact_id,
        fact_digest=plan.fact_digest,
        host_database_sha256_before=plan.database_sha256["host_database"],
        host_database_sha256_after=before["host_database"],
        non_host_databases_unchanged=True,
    )


def _data_control_verify_binding(
    location: RuntimeHostRootRef,
    studio_location: StudioRootRef,
    expected_binding: RuntimeAuthorityBinding,
) -> RuntimeAuthorityBinding:
    """Verify one binding through a query-only ControlStore connection."""

    if type(location) is not RuntimeHostRootRef:
        raise RuntimeHostRejected(
            "invalid-root-reference",
            "DataControl binding verification requires RuntimeHostRootRef",
        )
    if type(studio_location) is not StudioRootRef:
        raise RuntimeHostRejected(
            "invalid-studio-reference",
            "DataControl binding verification requires StudioRootRef",
        )
    if type(expected_binding) is not RuntimeAuthorityBinding:
        raise RuntimeHostRejected(
            "invalid-binding-reference",
            "DataControl binding verification requires RuntimeAuthorityBinding",
        )
    _validate_existing_root(
        location.root,
        location.root_id,
        root_kind=location.root_kind,
        studio_location=studio_location,
    )
    _read_root_identity(location, studio_location)
    reader = _connect_readonly(location.control_database)
    try:
        _verify_control(location, studio_location, reader)
        row = reader.execute(
            f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding "
            "WHERE binding_id = ?",
            (expected_binding.binding_id,),
        ).fetchone()
        if row is None:
            raise RuntimeHostRejected(
                "binding-not-found",
                "DataControl binding is absent from Host authority",
            )
        verifier = object.__new__(RuntimeHost)
        verifier._location = location
        verifier._studio_location = studio_location
        observed = RuntimeHost._binding_from_row(verifier, row)
        if observed != expected_binding:
            raise RuntimeHostFailedClosed(
                "binding-identity-mismatch",
                "DataControl binding reference differs from Host authority",
            )
        return observed
    finally:
        reader.close()


def _data_control_timeline_authority(
    binding: RuntimeAuthorityBinding,
) -> _RuntimeBindingAuthority:
    if type(binding) is not RuntimeAuthorityBinding:
        raise RuntimeHostRejected(
            "invalid-binding-reference",
            "Timeline export authority requires RuntimeAuthorityBinding",
        )
    return _RuntimeBindingAuthority(
        authority_scope_id=binding.authority_scope_id,
        profile_id=binding.profile_id,
        timeline_id=binding.timeline_id,
        allowed_intents=ALLOWED_INTENTS,
        allowed_provenance=ALLOWED_PROVENANCE,
        binding_id=binding.binding_id,
        binding_revision=binding.binding_revision,
        binding_epoch=binding.binding_epoch,
        qualification_id=binding.qualification_id,
        qualification_revision=binding.qualification_revision,
        provider_authority=binding.provider_authority,
    )


def _begin(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")


def _commit(connection: sqlite3.Connection) -> None:
    connection.execute("COMMIT")


def _rollback_if_needed(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.execute("ROLLBACK")


def _bootstrap_control(
    location: RuntimeHostRootRef,
    studio_location: StudioRootRef,
) -> None:
    connection = _connect_new(location.control_database)
    try:
        _begin(connection)
        for statement in _CONTROL_DDL:
            connection.execute(statement)
        connection.execute(f"PRAGMA user_version = {HOST_SCHEMA_VERSION}")
        connection.execute(
            """
            INSERT INTO host_manifest (
                singleton, root_id, control_store_id, studio_root_id,
                studio_store_id, schema_family, schema_version,
                contract_version, persistence_version, root_epoch, created_at_us
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                location.root_id,
                location.control_store_id,
                studio_location.root_id,
                studio_location.profile_store_id,
                HOST_SCHEMA_FAMILY,
                HOST_SCHEMA_VERSION,
                CONTRACT_VERSION,
                PERSISTENCE_VERSION,
                HOST_ROOT_EPOCH,
                _utc_microseconds(),
            ),
        )
        _commit(connection)
    except Exception:
        _rollback_if_needed(connection)
        raise
    finally:
        connection.close()


def _verify_control(
    location: RuntimeHostRootRef,
    studio_location: StudioRootRef,
    connection: sqlite3.Connection,
) -> None:
    try:
        mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).casefold()
        synchronous = int(connection.execute("PRAGMA synchronous").fetchone()[0])
        foreign_keys = int(connection.execute("PRAGMA foreign_keys").fetchone()[0])
        secure_delete = int(connection.execute("PRAGMA secure_delete").fetchone()[0])
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        tables = frozenset(
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        )
        triggers = frozenset(
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'trigger'"
            )
        )
        manifest = connection.execute(
            """
            SELECT root_id, control_store_id, studio_root_id, studio_store_id,
                   schema_family, schema_version, contract_version,
                   persistence_version, root_epoch
            FROM host_manifest WHERE singleton = 1
            """
        ).fetchone()
    except sqlite3.Error as error:
        raise RuntimeHostFailedClosed(
            "host-store-integrity-failed",
            "RuntimeHost ControlStore could not be verified",
        ) from error
    expected_manifest = (
        location.root_id,
        location.control_store_id,
        studio_location.root_id,
        studio_location.profile_store_id,
        HOST_SCHEMA_FAMILY,
        HOST_SCHEMA_VERSION,
        CONTRACT_VERSION,
        PERSISTENCE_VERSION,
        HOST_ROOT_EPOCH,
    )
    if user_version != HOST_SCHEMA_VERSION:
        raise RuntimeHostFailedClosed(
            "branch-governance-schema-required",
            "RuntimeHost ControlStore lacks the required branch-governance schema",
        )
    if (
        mode != "delete"
        or synchronous != 3
        or foreign_keys != 1
        or secure_delete != 1
        or integrity != "ok"
        or tables != _CONTROL_TABLES
        or triggers != _CONTROL_TRIGGERS
        or manifest != expected_manifest
    ):
        raise RuntimeHostFailedClosed(
            "host-store-identity-mismatch",
            "RuntimeHost ControlStore identity or connection profile is invalid",
        )


def _claim_process_registry(root_id: str, instance_id: str) -> None:
    with _PROCESS_REGISTRY_LOCK:
        if root_id in _PROCESS_REGISTRY:
            raise RuntimeHostConflict(
                "second-runtime-host",
                "another RuntimeHost already owns this process-local root",
            )
        _PROCESS_REGISTRY[root_id] = instance_id


def _release_process_registry(root_id: str, instance_id: str) -> None:
    with _PROCESS_REGISTRY_LOCK:
        if _PROCESS_REGISTRY.get(root_id) == instance_id:
            _PROCESS_REGISTRY.pop(root_id, None)


def _pid_is_alive(pid: int) -> bool:
    if pid == os.getpid():
        return True
    if sys.platform == "win32":
        return _windows_process_is_alive(pid)
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


def _windows_process_is_alive(pid: int) -> bool:
    import ctypes

    if not 0 < pid < 2**31:
        return False
    process_query_limited_information = 0x1000
    synchronize = 0x00100000
    still_active = 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(
        process_query_limited_information | synchronize, False, pid
    )
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


__all__ = [
    "BindingState",
    "RuntimeAuthorityBinding",
    "RuntimeHealth",
    "RuntimeHost",
    "RuntimeHostConflict",
    "RuntimeHostFailedClosed",
    "RuntimeHostFaultPoint",
    "RuntimeHostInterrupted",
    "RuntimeHostProblem",
    "RuntimeHostRejected",
    "RuntimeHostRootRef",
    "RuntimeLease",
    "RuntimeRoute",
]
