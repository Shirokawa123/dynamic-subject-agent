"""Private, no-egress activation Module for the confirmed DeepSeek lane.

The Module may assemble and verify an empty authority lane.  It deliberately
contains no provider Adapter, transport, credential resolver, submit, export,
or clear Interface.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID

from dynamic_subject_agent.bootstrap import compose_application
from dynamic_subject_agent.application import ApplicationOperationResponse
from dynamic_subject_agent.cognition import (
    CognitionProviderRequest,
    CredentialRef,
    OperationEgressApproval,
    OperationEgressReservation,
    ProviderFailure,
    ProviderFailureCode,
    UserConfirmedContextBrief,
)
from dynamic_subject_agent.cognition_experiment import (
    DEEPSEEK_CONTEXT_BRIEF_ID,
    DEEPSEEK_EXPERIMENT_ID,
    DEEPSEEK_GENESIS_DRAFT_ID,
    DEEPSEEK_PROFILE_ID,
    DEEPSEEK_PROFILE_STORE_ID,
    DEEPSEEK_ROOT_ID,
    DeepSeekExperimentDraftPreparer,
)
from dynamic_subject_agent.deepseek import (
    DEEPSEEK_CREDENTIAL_BACKEND_ID,
    DEEPSEEK_CREDENTIAL_KEY_ID,
    DEEPSEEK_MODEL,
    DEEPSEEK_PROVIDER_AUTHORITY_ID,
    ApprovedDeepSeekCognition,
    DeepSeekCognitionProvider,
    DeepSeekCredentialResolver,
    DeepSeekTransport,
    DeepSeekUrlLibTransport,
)
from dynamic_subject_agent.domains import ExperienceBasis
from dynamic_subject_agent.host import (
    RuntimeHostRootRef,
    RuntimeHostFaultPoint,
    _RuntimeActivationPlan,
)
from dynamic_subject_agent.runtime import (
    CognitionEngine,
    CognitionFailedClosed,
    CognitionRuntimeView,
    CognitiveProposal,
    CyclePlan,
)
from dynamic_subject_agent.studio import (
    CapabilityManifest,
    FreezeDecision,
    PolicyKernel,
    StudioProblem,
    StudioRootRef,
    SubjectStudio,
)
from dynamic_subject_agent.timeline import (
    PreAdmissionRejected,
    SubjectCommand,
    _ReservedTimelineIdentity,
)


_FREEZE_DECISION_ID = "0129db78-3fa9-4edc-b8d5-130a009a7bdd"
_GENESIS_SNAPSHOT_ID = "98055c5c-b7a1-50f7-aa73-65c28af3a92e"
_KNOWLEDGE_SNAPSHOT_ID = "c3f2eec8-c95c-580b-8bbf-671eb06452e0"
_QRI_PUBLICATION_KEY = "post-m0-01-deepseek-v4-flash-qri-1"
_QUALIFICATION_ID = "46d909b2-77cc-5c52-9a4c-8ebe1210b6bb"
_HOST_ROOT_ID = "8fdd2e2b-c37b-4848-9d9e-5a2f43969f04"
_HOST_CONTROL_STORE_ID = "58a25589-7d6a-4e74-af7b-eca7a79e0e1c"
_TIMELINE_ID = "b92fdc8f-3873-4ab5-b645-471f0efd4547"
_TIMELINE_ROOT_ID = "ca631751-ffb5-47d8-9f96-5ad9dead0c89"
_TIMELINE_CONTROL_STORE_ID = "33eb606e-43bc-4371-8ba8-3386736092e0"
_TIMELINE_STORE_ID = "eef45101-8a1d-4fbd-ad37-e0f40a191ecd"
_BINDING_ID = "f4f4a580-5417-5ebd-ac75-62a3a11e5ce1"
_AUTHORITY_SCOPE_ID = "43330d30-bc9d-525c-9f65-6d12c058a0f1"
_PHASE_FIVE_OPERATION_ID = "bcd3d22c-5e8b-4f2b-865d-f9e2a0a8af2c"
_PHASE_FIVE_APPROVAL_ID = "0c16b949-241e-53a4-a7c6-eed6ec19af15"
_PHASE_FIVE_IDEMPOTENCY_KEY = "post-m0-01-deepseek-phase-5-operation-0001"
_PHASE_SIX_OPERATION_ID = "0544c62c-cffb-4c4b-99c4-9c2e5f2155c4"
_PHASE_SIX_APPROVAL_ID = "9353ef49-b122-48f6-834b-9a39502e6180"
_PHASE_SIX_IDEMPOTENCY_KEY = "post-m0-01-deepseek-phase-6-operation-0001"
_PHASE_SIX_REQUEST_ID = "cc7d8dda-3b8d-4a36-8d3a-6c5b96e678b2"
_PHASE_FIVE_COMMAND = (
    "Avery，我们正在筹备 Lantern Zine。给出三条下一步的建议，说明一下你缺少哪些信息，我告诉你。"
)
_PHASE_FIVE_OUTBOUND_DIGEST = (
    "a4fce37501c1f2c90e964bd86ae3436d399a8c97ae09c9f79cf646ac6b7db8bd"
)
_PHASE_FIVE_PREVIEW_SHA256 = (
    "9f20d786da87f283f2df58d7b47501e18f1c02be971bc28abe3b688767fb4560"
)
_PHASE_FIVE_EXECUTOR_PREVIEW_SHA256 = (
    "550f0f0f9f3db4564b0bfd4d4b203719ec976ef94c66d87536ba01aa5b42c215"
)
_PHASE_SIX_PREDECESSOR_PREVIEW_SHA256 = (
    "08a678175e67e67aa98a45e0badf7bc166e511b4e1af833d20c18e7e5578ff61"
)
_PHASE_FOUR_ACTIVATION_SHA256 = (
    "8477780528b4835b370c3f2106be9477e083094d08adee6c73953aaa4ab7cd76"
)
_REQUIRED_SOURCE_NAMES = frozenset(
    {
        "_deepseek_activation.py",
        "bootstrap.py",
        "cognition.py",
        "cognition_experiment.py",
        "deepseek.py",
        "host.py",
        "runtime.py",
        "studio.py",
        "timeline.py",
    }
)


class DeepSeekRuntimeActivationRejected(Exception):
    """The confirmed empty-lane activation could not be proven safe."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class DeepSeekOperationExecutionRejected(Exception):
    """The one approved operation cannot safely enter the authority lane."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class _PhaseFiveOperationPlan:
    operation_id: str
    approval_id: str
    idempotency_key: str
    request_id: str
    binding_id: str
    profile_id: str
    timeline_id: str
    command: SubjectCommand
    outbound_digest: str
    experiment_base: Path | None = None


class _OneShotExactCredentialResolver(DeepSeekCredentialResolver):
    """Consumes one opaque, caller-supplied value with no configuration discovery."""

    def __init__(self, secret_supplier: Callable[[CredentialRef], str]) -> None:
        if not callable(secret_supplier):
            raise TypeError("credential supplier must be callable")
        self._secret_supplier = secret_supplier
        self._consumed = False

    def resolve(self, credential_ref: CredentialRef) -> str:
        if (
            self._consumed
            or credential_ref.backend_id != DEEPSEEK_CREDENTIAL_BACKEND_ID
            or credential_ref.key_id != DEEPSEEK_CREDENTIAL_KEY_ID
        ):
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        self._consumed = True
        supplier = self._secret_supplier
        self._secret_supplier = _credential_already_consumed
        secret = supplier(credential_ref)
        if not isinstance(secret, str) or not secret:
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        return secret


def _credential_already_consumed(credential_ref: CredentialRef) -> str:
    del credential_ref
    raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)


def _phase_five_command() -> SubjectCommand:
    return SubjectCommand.contribute_utterance(
        target_profile_id=DEEPSEEK_PROFILE_ID,
        target_timeline_id=_TIMELINE_ID,
        declared_intent="ask-collaborator-status",
        utterance=_PHASE_FIVE_COMMAND,
        language="zh-CN",
        provenance="project-original",
    )


def _phase_five_plan(*, outbound_digest: str = _PHASE_FIVE_OUTBOUND_DIGEST) -> _PhaseFiveOperationPlan:
    command = _phase_five_command()
    if not isinstance(outbound_digest, str) or len(outbound_digest) != 64:
        raise DeepSeekOperationExecutionRejected(
            "operation-approval-mismatch",
            "the approved outbound digest is malformed",
        )
    return _PhaseFiveOperationPlan(
        operation_id=_PHASE_FIVE_OPERATION_ID,
        approval_id=_PHASE_FIVE_APPROVAL_ID,
        idempotency_key=_PHASE_FIVE_IDEMPOTENCY_KEY,
        request_id="c41a5bf2-b2ad-57c0-85df-6e12fd549d01",
        binding_id=_BINDING_ID,
        profile_id=DEEPSEEK_PROFILE_ID,
        timeline_id=_TIMELINE_ID,
        command=command,
        outbound_digest=outbound_digest,
    )


def _phase_six_plan(*, outbound_digest: str = _PHASE_FIVE_OUTBOUND_DIGEST) -> _PhaseFiveOperationPlan:
    return _PhaseFiveOperationPlan(
        operation_id=_PHASE_SIX_OPERATION_ID,
        approval_id=_PHASE_SIX_APPROVAL_ID,
        idempotency_key=_PHASE_SIX_IDEMPOTENCY_KEY,
        request_id=_PHASE_SIX_REQUEST_ID,
        binding_id=_BINDING_ID,
        profile_id=DEEPSEEK_PROFILE_ID,
        timeline_id=_TIMELINE_ID,
        command=_phase_five_command(),
        outbound_digest=outbound_digest,
    )


def _operation_plan_for_phase(
    phase: str,
    *,
    outbound_digest: str = _PHASE_FIVE_OUTBOUND_DIGEST,
) -> _PhaseFiveOperationPlan:
    if phase == "p5":
        return _phase_five_plan(outbound_digest=outbound_digest)
    if phase == "p6":
        return _phase_six_plan(outbound_digest=outbound_digest)
    raise DeepSeekOperationExecutionRejected(
        "operation-phase-unavailable",
        "the executor only recognizes the reviewed P5 or P6 operation identity",
    )


def _approved_cognition(
    plan: _PhaseFiveOperationPlan,
    *,
    transport: DeepSeekTransport,
) -> ApprovedDeepSeekCognition:
    command = plan.command
    brief = UserConfirmedContextBrief.confirm(
        brief_id=DEEPSEEK_CONTEXT_BRIEF_ID,
        profile_id=plan.profile_id,
        timeline_id=plan.timeline_id,
        command_fingerprint=command.payload_fingerprint,
        language=command.language,
        confirmed_facts=(),
        acknowledged_unknowns=(),
    )
    request = CognitionProviderRequest(
        request_id=plan.request_id,
        request_digest="0" * 64,
        operation_id=plan.operation_id,
        profile_id=plan.profile_id,
        timeline_id=plan.timeline_id,
        provider="deepseek-official-api",
        model=DEEPSEEK_MODEL,
        current_command=command.utterance,
        language=command.language,
        brief_id=brief.brief_id,
        brief_digest=brief.integrity_digest,
        confirmed_facts=(),
        acknowledged_unknowns=(),
    )
    actual_digest = DeepSeekCognitionProvider.outbound_digest(request)
    if actual_digest != _PHASE_FIVE_OUTBOUND_DIGEST or actual_digest != plan.outbound_digest:
        raise DeepSeekOperationExecutionRejected(
            "operation-approval-mismatch",
            "the requested payload differs from the one confirmed operation",
        )
    approval = OperationEgressApproval.approve(
        approval_id=plan.approval_id,
        operation_id=plan.operation_id,
        outbound_digest=actual_digest,
        disclosure=DeepSeekCognitionProvider.terms_disclosure(),
    )
    provider = DeepSeekCognitionProvider(
        transport=transport,
        egress_approval=approval,
    )
    return ApprovedDeepSeekCognition(
        provider=provider,
        context_brief=brief,
        operation_reservation=OperationEgressReservation.reserve(
            operation_id=plan.operation_id,
            binding_id=plan.binding_id,
            profile_id=plan.profile_id,
            timeline_id=plan.timeline_id,
            command_fingerprint=command.payload_fingerprint,
            provider_authority=DEEPSEEK_PROVIDER_AUTHORITY_ID,
        ),
        credential_ref=CredentialRef.reference(
            backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
            key_id=DEEPSEEK_CREDENTIAL_KEY_ID,
        ),
    )


def _open_exact_operation_application(
    prepared: _PreparedAuthority,
    *,
    plan: _PhaseFiveOperationPlan,
    cognition: ApprovedDeepSeekCognition,
) -> tuple[object, _PhaseFiveOperationPlan]:
    studio = SubjectStudio.open(prepared.location, policy_kernel=PolicyKernel())
    try:
        qri = studio.query_qri(publication_key=_QRI_PUBLICATION_KEY)
    finally:
        studio.close()
    if (
        qri.profile_id != plan.profile_id
        or qri.provider_authority != DEEPSEEK_PROVIDER_AUTHORITY_ID
    ):
        raise DeepSeekOperationExecutionRejected(
            "operation-qri-identity-mismatch",
            "the exact operation does not match the published QRI",
        )
    composition = compose_application(
        m0_root=prepared.experiment_base,
        studio_location=prepared.location,
        qualified_runtime_input=qri,
        timeline_id=plan.timeline_id,
        host_location=_host_location(prepared.experiment_base),
        _cognition=cognition,
        _activation_plan=_activation_plan(),
    )
    binding = composition._host.query_binding(
        profile_id=plan.profile_id,
        timeline_id=plan.timeline_id,
    )
    if (
        binding.binding_id != plan.binding_id
        or binding.authority_scope_id != _AUTHORITY_SCOPE_ID
    ):
        composition.close()
        raise DeepSeekOperationExecutionRejected(
            "operation-binding-identity-mismatch",
            "the operation does not match the sole active binding",
        )
    return composition, plan


def _assert_phase_six_precondition(prepared: _PreparedAuthority) -> None:
    """Permit P6 only after P5's observed provider-unavailable terminal fact."""

    timeline_database = (
        _host_location(prepared.experiment_base).root
        / "mature-runtime-m0"
        / "roots"
        / _TIMELINE_ROOT_ID
        / "timelines"
        / _TIMELINE_ID
        / "timeline.sqlite3"
    )
    if (
        not timeline_database.is_file()
        or timeline_database.is_symlink()
        or timeline_database.stat().st_nlink != 1
    ):
        raise DeepSeekOperationExecutionRejected(
            "phase-six-precondition-unmet",
            "P6 cannot verify the exact Timeline store read-only",
        )
    try:
        reader = sqlite3.connect(
            f"file:{timeline_database.as_posix()}?mode=ro&immutable=1",
            uri=True,
        )
        reader.execute("PRAGMA query_only=ON")
        p5_failure = reader.execute(
            """
            SELECT failure_stage, failure_code
            FROM operation_failure
            WHERE operation_id = ?
            """,
            (UUID(_PHASE_FIVE_OPERATION_ID).bytes,),
        ).fetchone()
        p6_exists = reader.execute(
            "SELECT 1 FROM subject_operation WHERE operation_id = ?",
            (UUID(_PHASE_SIX_OPERATION_ID).bytes,),
        ).fetchone()
        outcome_count = reader.execute(
            "SELECT COUNT(*) FROM timeline_outcome"
        ).fetchone()[0]
        head = reader.execute(
            "SELECT head_sequence FROM timeline_head WHERE singleton = 1"
        ).fetchone()[0]
    except sqlite3.Error as error:
        raise DeepSeekOperationExecutionRejected(
            "phase-six-precondition-unmet",
            "P6 cannot read the exact Timeline precondition",
        ) from error
    finally:
        try:
            reader.close()
        except UnboundLocalError:
            pass
    if p5_failure != ("provider", "provider-unavailable"):
        raise DeepSeekOperationExecutionRejected(
            "phase-six-precondition-unmet",
            "P6 requires P5's exact provider-unavailable failure and an empty outcome prefix",
        )
    if p6_exists is not None:
        return
    if outcome_count != 0 or head != 0:
        raise DeepSeekOperationExecutionRejected(
            "phase-six-precondition-unmet",
            "a new P6 operation requires an empty outcome prefix",
        )


def _read_phase_five_evidence(
    path: Path,
    *,
    expected_digest: str | None,
) -> tuple[dict[str, Any], str]:
    if not isinstance(path, Path) or not path.is_absolute():
        raise DeepSeekOperationExecutionRejected(
            "operation-evidence-path-invalid",
            "operation evidence must be an explicit absolute Path",
        )
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_nlink != 1:
            raise OSError("evidence is absent or linked")
        raw = path.read_bytes()
    except OSError as error:
        raise DeepSeekOperationExecutionRejected(
            "operation-evidence-unreadable",
            "operation evidence is absent, linked, or unreadable",
        ) from error
    digest = hashlib.sha256(raw).hexdigest()
    if expected_digest is not None and digest != expected_digest:
        raise DeepSeekOperationExecutionRejected(
            "operation-evidence-digest-mismatch",
            "operation evidence does not match the confirmed immutable record",
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise DeepSeekOperationExecutionRejected(
            "operation-evidence-unreadable",
            "operation evidence is not valid UTF-8 JSON",
        ) from error
    if not isinstance(payload, dict):
        raise DeepSeekOperationExecutionRejected(
            "operation-evidence-semantics-invalid",
            "operation evidence must be a JSON object",
        )
    return payload, digest


def _phase_five_plan_from_evidence(
    *,
    preview_record: Path,
    confirmation_record: Path,
) -> _PhaseFiveOperationPlan:
    preview, preview_digest = _read_phase_five_evidence(
        preview_record,
        expected_digest=None,
    )
    try:
        if (
            not confirmation_record.is_file()
            or confirmation_record.is_symlink()
            or confirmation_record.stat().st_nlink != 1
        ):
            raise OSError("confirmation is absent or linked")
        confirmation = json.loads(confirmation_record.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DeepSeekOperationExecutionRejected(
            "operation-confirmation-unreadable",
            "operation confirmation is absent, linked, or unreadable",
        ) from error
    reservation = preview.get("canonical_operation_reservation")
    provider = preview.get("provider")
    outbound = preview.get("exact_outbound")
    supersedes = preview.get("supersedes")
    reference = confirmation.get("preview") if isinstance(confirmation, dict) else None
    contract = preview.get("evidence_contract")
    preview_lineage_valid = (
        contract == "POST-M0-01-HITL-PHASE-5-OPERATION-EGRESS-PREVIEW-02"
        and preview_digest == _PHASE_FIVE_PREVIEW_SHA256
    ) or (
        contract == "POST-M0-01-HITL-PHASE-5-OPERATION-EGRESS-PREVIEW-03"
        and isinstance(supersedes, dict)
        and supersedes.get("preview_sha256") == _PHASE_FIVE_PREVIEW_SHA256
    ) or (
        contract == "POST-M0-01-HITL-PHASE-5-OPERATION-EGRESS-PREVIEW-04"
        and isinstance(supersedes, dict)
        and supersedes.get("preview_sha256")
        == _PHASE_FIVE_EXECUTOR_PREVIEW_SHA256
    ) or (
        contract == "POST-M0-01-HITL-PHASE-6-OPERATION-EGRESS-PREVIEW-01"
        and isinstance(supersedes, dict)
        and supersedes.get("preview_sha256")
        == _PHASE_SIX_PREDECESSOR_PREVIEW_SHA256
    )
    expected_plan = (
        _phase_six_plan()
        if contract == "POST-M0-01-HITL-PHASE-6-OPERATION-EGRESS-PREVIEW-01"
        else _phase_five_plan()
    )
    if (
        not preview_lineage_valid
        or not isinstance(reservation, dict)
        or not isinstance(provider, dict)
        or not isinstance(outbound, dict)
        or not isinstance(reference, dict)
        or not isinstance(confirmation, dict)
        or not str(confirmation.get("status", "")).startswith("user-confirmed")
        or reference.get("sha256") != preview_digest
        or reference.get("operation_id") != expected_plan.operation_id
        or reference.get("outbound_digest") != _PHASE_FIVE_OUTBOUND_DIGEST
        or reservation.get("operation_id") != expected_plan.operation_id
        or reservation.get("binding_id") != expected_plan.binding_id
        or reservation.get("profile_id") != expected_plan.profile_id
        or reservation.get("timeline_id") != expected_plan.timeline_id
        or reservation.get("provider_authority_id") != DEEPSEEK_PROVIDER_AUTHORITY_ID
        or provider.get("model") != DEEPSEEK_MODEL
        or provider.get("timeout_seconds") != 30
        or provider.get("maximum_network_attempts") != 1
        or provider.get("retry") != "forbidden; timeout is typed delivery-ambiguous rather than a retry trigger"
        or outbound.get("sha256") != _PHASE_FIVE_OUTBOUND_DIGEST
    ):
        raise DeepSeekOperationExecutionRejected(
            "operation-evidence-semantics-invalid",
            "operation evidence does not bind the exact confirmed route",
        )
    runner_digest = preview.get("operation_executor_source_sha256")
    current_runner_digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if runner_digest != current_runner_digest:
        raise DeepSeekOperationExecutionRejected(
            "operation-executor-preview-required",
            "the reviewed executor source is not bound by a successor preview",
        )
    execution_authority = preview.get("exact_execution_authority")
    if not isinstance(execution_authority, dict):
        raise DeepSeekOperationExecutionRejected(
            "operation-executor-preview-required",
            "the executor authority path is not bound by a successor preview",
        )
    experiment_base = Path(str(execution_authority.get("experiment_base", "")))
    if (
        not experiment_base.is_absolute()
        or experiment_base.name != DEEPSEEK_EXPERIMENT_ID
        or execution_authority.get("activation_receipt_sha256")
        != _PHASE_FOUR_ACTIVATION_SHA256
        or execution_authority.get("profile_id") != DEEPSEEK_PROFILE_ID
        or execution_authority.get("binding_id") != _BINDING_ID
        or execution_authority.get("timeline_id") != _TIMELINE_ID
        or execution_authority.get("provider_authority_id")
        != DEEPSEEK_PROVIDER_AUTHORITY_ID
    ):
        raise DeepSeekOperationExecutionRejected(
            "operation-authority-identity-mismatch",
            "the executor preview does not bind the exact dormant authority",
        )
    plan = expected_plan
    return _PhaseFiveOperationPlan(
        operation_id=plan.operation_id,
        approval_id=plan.approval_id,
        idempotency_key=plan.idempotency_key,
        request_id=plan.request_id,
        binding_id=plan.binding_id,
        profile_id=plan.profile_id,
        timeline_id=plan.timeline_id,
        command=plan.command,
        outbound_digest=plan.outbound_digest,
        experiment_base=experiment_base,
    )


class DeepSeekOperationExecutor:
    """One private Interface: approved evidence to one Facade-routed operation."""

    def __new__(cls, *args: object, **kwargs: object) -> DeepSeekOperationExecutor:
        raise TypeError("DeepSeekOperationExecutor is not instantiable")

    @staticmethod
    def _execute_test(
        test_parent: Path,
        *,
        _transport: DeepSeekTransport,
        _outbound_digest: str = _PHASE_FIVE_OUTBOUND_DIGEST,
        _operation_phase: str = "p5",
    ) -> ApplicationOperationResponse:
        """Temporary-root seam; no credential resolver or network adapter is reachable."""

        prepared = _prepare_test_authority(test_parent)
        if not _host_location(prepared.experiment_base).root.exists():
            _activate(prepared)
        plan = _operation_plan_for_phase(
            _operation_phase,
            outbound_digest=_outbound_digest,
        )
        if _operation_phase == "p6":
            _assert_phase_six_precondition(prepared)
        cognition = _approved_cognition(plan, transport=_transport)
        composition, plan = _open_exact_operation_application(
            prepared,
            plan=plan,
            cognition=cognition,
        )
        try:
            submitted = composition.application.submit(
                plan.command,
                idempotency_key=plan.idempotency_key,
            )
            if submitted.operation_ref is None:
                return submitted
            return composition.application.wait(
                submitted.operation_ref,
                timeout_seconds=30.0,
            )
        finally:
            composition.close()

    @staticmethod
    def _credential_resolver_for_one_operation(
        *,
        _secret_supplier: Callable[[CredentialRef], str],
    ) -> DeepSeekCredentialResolver:
        """Create the only resolver accepted by this executor; no secret is read here."""

        return _OneShotExactCredentialResolver(_secret_supplier)

    @staticmethod
    def execute(
        *,
        preview_record: Path,
        confirmation_record: Path,
        credential_resolver: DeepSeekCredentialResolver,
    ) -> ApplicationOperationResponse:
        """Execute only source-bound, confirmed evidence through ApplicationFacade."""

        if type(credential_resolver) is not _OneShotExactCredentialResolver:
            raise DeepSeekOperationExecutionRejected(
                "credential-resolver-unavailable",
                "the operation requires the reviewed one-shot injected resolver",
            )
        plan = _phase_five_plan_from_evidence(
            preview_record=preview_record,
            confirmation_record=confirmation_record,
        )
        if plan.experiment_base is None:
            raise DeepSeekOperationExecutionRejected(
                "operation-executor-preview-required",
                "the executor has no source-bound authority path",
            )
        prepared = _existing_prepared(plan.experiment_base)
        if plan.operation_id == _PHASE_SIX_OPERATION_ID:
            _assert_phase_six_precondition(prepared)
        cognition = _approved_cognition(
            plan,
            transport=DeepSeekUrlLibTransport(credential_resolver=credential_resolver),
        )
        composition, plan = _open_exact_operation_application(
            prepared,
            plan=plan,
            cognition=cognition,
        )
        try:
            submitted = composition.application.submit(
                plan.command,
                idempotency_key=plan.idempotency_key,
            )
            if submitted.operation_ref is None:
                return submitted
            return composition.application.wait(
                submitted.operation_ref,
                timeout_seconds=30.0,
            )
        finally:
            composition.close()

@dataclass(frozen=True)
class DeepSeekRuntimeActivationReceipt:
    genesis_snapshot_id: str
    knowledge_snapshot_id: str
    qualification_id: str
    host_root_id: str
    host_control_store_id: str
    binding_id: str
    authority_scope_id: str
    timeline_id: str
    timeline_root_id: str
    timeline_control_store_id: str
    timeline_store_id: str
    timeline_head: int
    live_runtime_instance_lease_count: int
    authority_counts: Mapping[str, int]


@dataclass(frozen=True)
class _PreparedAuthority:
    experiment_base: Path
    location: StudioRootRef


class DormantDeepSeekCognition(CognitionEngine):
    """Buildable DeepSeek authority that cannot call a provider without a grant."""

    adapter_version = "post-m0-deepseek-dormant-activation-1.0"
    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    experimental = True
    test_only = False

    def preflight(
        self,
        *,
        context: CognitionRuntimeView,
        command: SubjectCommand,
    ) -> None:
        del context, command
        raise PreAdmissionRejected(
            "operation-egress-approval-required",
            "the dormant DeepSeek lane has no operation-bound egress approval",
        )

    def propose(
        self,
        *,
        plan: CyclePlan,
        context: CognitionRuntimeView,
        command: SubjectCommand,
        basis: ExperienceBasis,
    ) -> CognitiveProposal:
        del plan, context, command, basis
        raise CognitionFailedClosed(
            "provider",
            "operation-egress-approval-required",
            "the dormant DeepSeek lane cannot construct or call a provider",
        )


def _activation_plan() -> _RuntimeActivationPlan:
    return _RuntimeActivationPlan(
        provider_authority=DEEPSEEK_PROVIDER_AUTHORITY_ID,
        profile_id=DEEPSEEK_PROFILE_ID,
        qualification_id=_QUALIFICATION_ID,
        qri_publication_key=_QRI_PUBLICATION_KEY,
        timeline_id=_TIMELINE_ID,
        host_root_id=_HOST_ROOT_ID,
        host_control_store_id=_HOST_CONTROL_STORE_ID,
        binding_id=_BINDING_ID,
        authority_scope_id=_AUTHORITY_SCOPE_ID,
        timeline_identity=_ReservedTimelineIdentity(
            root_id=_TIMELINE_ROOT_ID,
            control_store_id=_TIMELINE_CONTROL_STORE_ID,
            timeline_store_id=_TIMELINE_STORE_ID,
        ),
    )


def _host_location(experiment_base: Path) -> RuntimeHostRootRef:
    return RuntimeHostRootRef(
        root_path=str(
            experiment_base
            / "mature-runtime-m0"
            / "host-roots"
            / _HOST_ROOT_ID
        ),
        root_id=_HOST_ROOT_ID,
        control_store_id=_HOST_CONTROL_STORE_ID,
        root_kind="experimental",
    )


def _existing_prepared(experiment_base: Path) -> _PreparedAuthority:
    location = StudioRootRef(
        root_path=str(
            experiment_base / "mature-runtime-m0" / "roots" / DEEPSEEK_ROOT_ID
        ),
        root_id=DEEPSEEK_ROOT_ID,
        profile_store_id=DEEPSEEK_PROFILE_STORE_ID,
        root_kind="experimental",
    )
    studio = SubjectStudio.open(location, policy_kernel=PolicyKernel())
    try:
        draft = studio.query_draft(DEEPSEEK_GENESIS_DRAFT_ID)
        if (
            draft.profile_id != DEEPSEEK_PROFILE_ID
            or draft.branch_id != "7257d111-ab7b-46d0-ae3c-7140d8c70c6f"
            or draft.revision != 1
        ):
            raise DeepSeekRuntimeActivationRejected(
                "activation-draft-identity-mismatch",
                "the experimental draft differs from the confirmed authority",
            )
    finally:
        studio.close()
    return _PreparedAuthority(experiment_base=experiment_base, location=location)


def _prepare_test_authority(test_parent: Path) -> _PreparedAuthority:
    if not isinstance(test_parent, Path) or not test_parent.is_absolute():
        raise TypeError("test_parent must be an explicit absolute Path")
    temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
    prospective = test_parent.resolve(strict=False)
    if not prospective.is_relative_to(temporary_root):
        raise DeepSeekRuntimeActivationRejected(
            "test-parent-not-temporary",
            "test activation is restricted to the system temporary root",
        )
    experiment_base = prospective / DEEPSEEK_EXPERIMENT_ID
    if not experiment_base.exists():
        prepared = DeepSeekExperimentDraftPreparer._prepare_test(prospective)
        return _PreparedAuthority(
            experiment_base=prepared.experiment_base,
            location=prepared.location,
        )
    return _existing_prepared(experiment_base)


def _seal_and_publish(prepared: _PreparedAuthority):
    studio = SubjectStudio.open(prepared.location, policy_kernel=PolicyKernel())
    try:
        try:
            qri = studio.query_qri(publication_key=_QRI_PUBLICATION_KEY)
        except StudioProblem as error:
            if error.code != "qri-not-found":
                raise
            try:
                snapshot = studio.query_snapshot(_GENESIS_SNAPSHOT_ID)
                policy_decision_id = snapshot.policy_decision_id
            except StudioProblem as snapshot_error:
                if snapshot_error.code != "snapshot-not-found":
                    raise
                preview = studio.preview(DEEPSEEK_GENESIS_DRAFT_ID)
                decision = studio.decide_policy(
                    DEEPSEEK_GENESIS_DRAFT_ID,
                    CapabilityManifest.deepseek_v4_flash_experimental(),
                )
                snapshot = studio.seal(
                    DEEPSEEK_GENESIS_DRAFT_ID,
                    FreezeDecision(
                        decision_id=_FREEZE_DECISION_ID,
                        draft_id=DEEPSEEK_GENESIS_DRAFT_ID,
                        expected_revision=1,
                        freeze_basis_digest=preview.freeze_basis_digest,
                        decided_by="post-m0-01-confirmed-activation",
                        rationale=(
                            "Seal only the confirmed isolated DeepSeek experiment."
                        ),
                    ),
                    policy_decision_id=decision.decision_id,
                )
                policy_decision_id = decision.decision_id
            qri = studio.publish(
                snapshot.snapshot_id,
                policy_decision_id=policy_decision_id,
                publication_key=_QRI_PUBLICATION_KEY,
            )
        if (
            qri.qualification_id != _QUALIFICATION_ID
            or qri.profile_id != DEEPSEEK_PROFILE_ID
            or qri.genesis_snapshot_id != _GENESIS_SNAPSHOT_ID
            or qri.knowledge_snapshot_id != _KNOWLEDGE_SNAPSHOT_ID
            or qri.provider_authority != DEEPSEEK_PROVIDER_AUTHORITY_ID
            or qri.capabilities
            != CapabilityManifest.deepseek_v4_flash_experimental()
        ):
            raise DeepSeekRuntimeActivationRejected(
                "activation-qri-identity-mismatch",
                "the published QRI differs from the confirmed activation plan",
            )
        return qri
    finally:
        studio.close()


def _readonly_counts(
    prepared: _PreparedAuthority,
    host_location: RuntimeHostRootRef,
) -> tuple[dict[str, int], int, int]:
    profile = sqlite3.connect(
        f"file:{prepared.location.profile_database.as_posix()}?mode=ro&immutable=1",
        uri=True,
    )
    host = sqlite3.connect(
        f"file:{host_location.control_database.as_posix()}?mode=ro&immutable=1",
        uri=True,
    )
    timeline_database = (
        Path(host_location.root_path)
        / "mature-runtime-m0"
        / "roots"
        / _TIMELINE_ROOT_ID
        / "timelines"
        / _TIMELINE_ID
        / "timeline.sqlite3"
    )
    timeline = sqlite3.connect(
        f"file:{timeline_database.as_posix()}?mode=ro&immutable=1",
        uri=True,
    )
    try:
        counts = {
            "profile": int(
                profile.execute("SELECT COUNT(*) FROM participant_profile").fetchone()[0]
            ),
            "genesis_draft": int(
                profile.execute("SELECT COUNT(*) FROM genesis_draft").fetchone()[0]
            ),
            "policy_decision": int(
                profile.execute("SELECT COUNT(*) FROM policy_decision").fetchone()[0]
            ),
            "sealed_genesis": int(
                profile.execute("SELECT COUNT(*) FROM genesis_snapshot").fetchone()[0]
            ),
            "empty_knowledge_snapshot": int(
                profile.execute("SELECT COUNT(*) FROM knowledge_snapshot").fetchone()[0]
            ),
            "qualified_runtime_input": int(
                profile.execute("SELECT COUNT(*) FROM qri_publication").fetchone()[0]
            ),
            "runtime_host_root": 1,
            "active_runtime_binding": int(
                host.execute(
                    "SELECT COUNT(*) FROM runtime_authority_binding "
                    "WHERE state = 'active'"
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
            "physical_clear": 0,
        }
        lease_count = int(
            host.execute(
                "SELECT COUNT(*) FROM runtime_instance_lease "
                "WHERE lease_state = 'active'"
            ).fetchone()[0]
        )
        head = int(
            timeline.execute(
                "SELECT head_sequence FROM timeline_head WHERE singleton = 1"
            ).fetchone()[0]
        )
        return counts, lease_count, head
    finally:
        profile.close()
        host.close()
        timeline.close()


def _activate(
    prepared: _PreparedAuthority,
    *,
    fault_hook: Callable[[RuntimeHostFaultPoint], None] | None = None,
) -> DeepSeekRuntimeActivationReceipt:
    qri = _seal_and_publish(prepared)
    plan = _activation_plan()
    host_location = _host_location(prepared.experiment_base)
    first_host_location = host_location if host_location.root.exists() else None
    composition = compose_application(
        m0_root=prepared.experiment_base,
        studio_location=prepared.location,
        qualified_runtime_input=qri,
        timeline_id=_TIMELINE_ID,
        host_location=first_host_location,
        _cognition=DormantDeepSeekCognition(),
        _activation_plan=plan,
        _host_fault_hook=fault_hook,
    )
    try:
        binding = composition._host.query_binding(
            profile_id=DEEPSEEK_PROFILE_ID,
            timeline_id=_TIMELINE_ID,
        )
        health = composition._host.health(
            profile_id=DEEPSEEK_PROFILE_ID,
            timeline_id=_TIMELINE_ID,
        )
        if health.timeline_basis.head_sequence != 0:
            raise DeepSeekRuntimeActivationRejected(
                "activation-timeline-not-empty",
                "the activated Timeline is not empty",
            )
    finally:
        composition.close()

    restarted = compose_application(
        m0_root=prepared.experiment_base,
        studio_location=prepared.location,
        qualified_runtime_input=qri,
        timeline_id=_TIMELINE_ID,
        host_location=host_location,
        _cognition=DormantDeepSeekCognition(),
        _activation_plan=plan,
    )
    try:
        recovered = restarted._host.query_binding(
            profile_id=DEEPSEEK_PROFILE_ID,
            timeline_id=_TIMELINE_ID,
        )
        recovered_health = restarted._host.health(
            profile_id=DEEPSEEK_PROFILE_ID,
            timeline_id=_TIMELINE_ID,
        )
        if recovered != binding or recovered_health.timeline_basis.head_sequence != 0:
            raise DeepSeekRuntimeActivationRejected(
                "activation-recovery-mismatch",
                "cold recovery did not return the same empty authority lane",
            )
    finally:
        restarted.close()

    counts, lease_count, head = _readonly_counts(prepared, host_location)
    return DeepSeekRuntimeActivationReceipt(
        genesis_snapshot_id=qri.genesis_snapshot_id,
        knowledge_snapshot_id=qri.knowledge_snapshot_id,
        qualification_id=qri.qualification_id,
        host_root_id=host_location.root_id,
        host_control_store_id=host_location.control_store_id,
        binding_id=binding.binding_id,
        authority_scope_id=binding.authority_scope_id,
        timeline_id=binding.timeline_id,
        timeline_root_id=binding.timeline_root.root_id,
        timeline_control_store_id=binding.timeline_root.control_store_id,
        timeline_store_id=binding.timeline_root.timeline_store_id,
        timeline_head=head,
        live_runtime_instance_lease_count=lease_count,
        authority_counts=MappingProxyType(counts),
    )


def _read_json_evidence(path: Path) -> tuple[dict[str, Any], str]:
    if not isinstance(path, Path) or not path.is_absolute():
        raise DeepSeekRuntimeActivationRejected(
            "activation-evidence-path-invalid",
            "activation evidence must use an explicit absolute Path",
        )
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_nlink != 1:
            raise OSError("evidence missing or linked")
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DeepSeekRuntimeActivationRejected(
            "activation-evidence-unreadable",
            "activation evidence is absent, linked, or invalid",
        ) from error
    if not isinstance(payload, dict):
        raise DeepSeekRuntimeActivationRejected(
            "activation-evidence-unreadable",
            "activation evidence must be a JSON object",
        )
    return payload, hashlib.sha256(raw).hexdigest()


def _source_hashes() -> dict[str, str]:
    package_root = Path(__file__).resolve().parent
    return {
        name: hashlib.sha256((package_root / name).read_bytes()).hexdigest()
        for name in sorted(_REQUIRED_SOURCE_NAMES)
    }


def _prepared_from_evidence(
    *,
    preview_record: Path,
    confirmation_record: Path,
) -> _PreparedAuthority:
    preview, preview_sha256 = _read_json_evidence(preview_record)
    confirmation, _confirmation_sha256 = _read_json_evidence(confirmation_record)
    reference = confirmation.get("preview")
    source_contract = preview.get("current_code_readiness")
    expected_sources = (
        source_contract.get("relevant_source_sha256")
        if isinstance(source_contract, dict)
        else None
    )
    authority = preview.get("exact_existing_experimental_authority")
    identities = preview.get("exact_reserved_activation_identities")
    if (
        preview.get("evidence_contract")
        != "POST-M0-01-HITL-PHASE-4-SEAL-RUNTIME-PREVIEW-1.0"
        or not isinstance(reference, dict)
        or reference.get("sha256") != preview_sha256
        or reference.get("preview_plan_id") != preview.get("preview_plan_id")
        or confirmation.get("status") != "confirmed-with-source-hash-condition"
        or not isinstance(authority, dict)
        or not isinstance(identities, dict)
        or authority.get("experiment_id") != DEEPSEEK_EXPERIMENT_ID
        or authority.get("studio_root_id") != DEEPSEEK_ROOT_ID
        or authority.get("profile_store_id") != DEEPSEEK_PROFILE_STORE_ID
        or authority.get("profile_id") != DEEPSEEK_PROFILE_ID
        or identities.get("freeze_decision_id") != _FREEZE_DECISION_ID
        or identities.get("genesis_snapshot_id") != _GENESIS_SNAPSHOT_ID
        or identities.get("empty_knowledge_snapshot_id")
        != _KNOWLEDGE_SNAPSHOT_ID
        or identities.get("qualification_id") != _QUALIFICATION_ID
        or identities.get("provider_authority_id")
        != DEEPSEEK_PROVIDER_AUTHORITY_ID
        or identities.get("host_root_id") != _HOST_ROOT_ID
        or identities.get("host_control_store_id") != _HOST_CONTROL_STORE_ID
        or identities.get("binding_id") != _BINDING_ID
        or identities.get("authority_scope_id") != _AUTHORITY_SCOPE_ID
        or identities.get("timeline_id") != _TIMELINE_ID
        or identities.get("timeline_root_id") != _TIMELINE_ROOT_ID
        or identities.get("timeline_control_store_id")
        != _TIMELINE_CONTROL_STORE_ID
        or identities.get("timeline_store_id") != _TIMELINE_STORE_ID
    ):
        raise DeepSeekRuntimeActivationRejected(
            "activation-evidence-semantics-invalid",
            "activation evidence does not bind the exact confirmed plan",
        )
    if (
        not isinstance(expected_sources, dict)
        or set(expected_sources) != _REQUIRED_SOURCE_NAMES
        or expected_sources != _source_hashes()
    ):
        raise DeepSeekRuntimeActivationRejected(
            "activation-source-digest-mismatch",
            "the confirmed source contract changed and requires a successor preview",
        )
    experiment_base = Path(str(authority.get("experiment_base", "")))
    if (
        not experiment_base.is_absolute()
        or experiment_base.name != DEEPSEEK_EXPERIMENT_ID
    ):
        raise DeepSeekRuntimeActivationRejected(
            "activation-path-mismatch",
            "the confirmed experimental authority path is invalid",
        )
    return _existing_prepared(experiment_base)


class DeepSeekRuntimeActivator:
    """One-method Interface for an exact empty DeepSeek authority activation."""

    def __new__(cls, *args: object, **kwargs: object) -> DeepSeekRuntimeActivator:
        raise TypeError("DeepSeekRuntimeActivator is not instantiable")

    @staticmethod
    def activate(
        *,
        preview_record: Path,
        confirmation_record: Path,
    ) -> DeepSeekRuntimeActivationReceipt:
        return _activate(
            _prepared_from_evidence(
                preview_record=preview_record,
                confirmation_record=confirmation_record,
            )
        )

    @staticmethod
    def _activate_test(
        test_parent: Path,
        *,
        _fault_hook: Callable[[RuntimeHostFaultPoint], None] | None = None,
    ) -> DeepSeekRuntimeActivationReceipt:
        return _activate(
            _prepare_test_authority(test_parent),
            fault_hook=_fault_hook,
        )


__all__: list[str] = []
