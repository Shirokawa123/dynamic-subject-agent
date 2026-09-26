"""The one fresh production composition root for the M0 application slice."""

from __future__ import annotations

from dynamic_subject_agent.character_dialogue import CharacterDialogueSession
from dynamic_subject_agent.conversation_basis import ConversationBasisPreview
from dynamic_subject_agent.character_reply_candidate import CharacterReplyLab
from dynamic_subject_agent.character_context_trial import CharacterContextTrial
from dynamic_subject_agent.character_evidence_model import CharacterEvidenceModel
from dynamic_subject_agent.evidence_extraction import EvidenceExtractionLab

from importlib import metadata
from pathlib import Path
from threading import RLock
from collections.abc import Callable

from dynamic_subject_agent.application import (
    ApplicationFacade,
    _ApplicationRouter,
    _create_application_facade,
)
from dynamic_subject_agent.host import (
    RuntimeHost,
    RuntimeHostFaultPoint,
    RuntimeHostRejected,
    RuntimeHostRootRef,
    _CognitionAssembly,
    _DormantArtifactActivationPlan,
    _DormantArtifactExperimentalActivationPlan,
    _RuntimeActivationPlan,
    _LocalServingAuthorization,
)
from dynamic_subject_agent.runtime import (
    CognitionEngine,
    FakeCognition,
    RuntimeFaultPoint,
)
from dynamic_subject_agent.timeline import OperationRef
from dynamic_subject_agent.knowledge_entries import KnowledgeEntry
from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection
from dynamic_subject_agent.source_character_authoring import (
    LocalIdentityListResponse,
    LocalIdentitySelectResponse,
    SourceIdentityFreezeResponse,
    TextSourceCharacterAuthoring,
)
from dynamic_subject_agent.studio import (
    CapabilityManifest,
    QualifiedRuntimeInput,
    StudioRootRef,
)


class _ApplicationComposition:
    def __init__(
        self,
        application: ApplicationFacade,
        router: _ApplicationRouter,
        host: RuntimeHost,
    ) -> None:
        self.application = application
        self.host_location = host.location
        self._router = router
        self._host = host
        self._lock = RLock()
        self._closed = False

    def __enter__(self) -> _ApplicationComposition:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                self._router.close()
                self._host.close()
            finally:
                self._closed = True


def _verify_installed_distribution_authority() -> None:
    package_root = Path(__file__).resolve().parent
    if "site-packages" not in {part.casefold() for part in package_root.parts}:
        return
    providers = metadata.packages_distributions().get("dynamic_subject_agent", [])
    if providers != ["dynamic-subject-agent"]:
        raise RuntimeError("fresh-distribution-authority-conflict")
    try:
        version = metadata.version("dynamic-subject-agent")
    except metadata.PackageNotFoundError as error:
        raise RuntimeError("fresh-distribution-authority-unavailable") from error
    if version != "0.0.0":
        raise RuntimeError("fresh-distribution-authority-conflict")


def compose_application(
    *,
    m0_root: Path,
    studio_location: StudioRootRef,
    qualified_runtime_input: QualifiedRuntimeInput,
    timeline_id: str,
    host_location: RuntimeHostRootRef | None = None,
    _cognition: CognitionEngine | None = None,
    _cognition_assembly: _CognitionAssembly | None = None,
    _runtime_interrupt_at: RuntimeFaultPoint | None = None,
    _runtime_fault_hook: Callable[[RuntimeFaultPoint, OperationRef], None] | None = None,
    _activation_plan: (
        _RuntimeActivationPlan
        | _DormantArtifactActivationPlan
        | _DormantArtifactExperimentalActivationPlan
        | None
    ) = None,
    _local_serving_authorization: _LocalServingAuthorization | None = None,
    _local_serving_stop_timeout_seconds: float = 30.0,
    relationship_mode: str = "off",
    _host_fault_hook: Callable[[RuntimeHostFaultPoint], None] | None = None,
    _character_dialogue: CharacterDialogueSession | None = None,
    _basis_preview: ConversationBasisPreview | None = None,
    _character_model: CharacterEvidenceModel | None = None,
    _character_reply_lab: CharacterReplyLab | CharacterContextTrial | None = None,
    _evidence_extraction: EvidenceExtractionLab | None = None,
    _source_authoring: TextSourceCharacterAuthoring | None = None,
    _source_studio_location: StudioRootRef | None = None,
    _source_identity_freezer: Callable[[object], SourceIdentityFreezeResponse]
    | None = None,
    _local_identity_lister: Callable[[], LocalIdentityListResponse] | None = None,
    _local_identity_selector: Callable[[object], LocalIdentitySelectResponse]
    | None = None,
    _knowledge_entries: tuple[KnowledgeEntry, ...] = (),
    _runtime_identity: RuntimeIdentityProjection | None = None,
) -> _ApplicationComposition:
    """Build the one fresh QRI→Host→Runtime→Facade authority lane."""

    _verify_installed_distribution_authority()
    if not isinstance(m0_root, Path):
        raise TypeError("compose_application requires an explicit Path M0 root")
    if not m0_root.is_absolute():
        raise ValueError("compose_application requires an absolute M0 root")
    if type(studio_location) is not StudioRootRef:
        raise TypeError("compose_application requires StudioRootRef authority")
    if type(qualified_runtime_input) is not QualifiedRuntimeInput:
        raise TypeError("compose_application requires a published QRI")
    if (
        isinstance(_local_serving_stop_timeout_seconds, bool)
        or not isinstance(_local_serving_stop_timeout_seconds, (int, float))
        or _local_serving_stop_timeout_seconds <= 0
        or _local_serving_stop_timeout_seconds > 30
    ):
        raise ValueError("local serving stop timeout must be in (0, 30]")
    cognition = FakeCognition() if _cognition is None else _cognition
    if not isinstance(cognition, CognitionEngine):
        raise TypeError("compose_application requires a fresh CognitionEngine")
    if relationship_mode not in {"off", "dynamic"}:
        raise ValueError("relationship_mode must be off or dynamic")
    relationship_enabled = relationship_mode == "dynamic"
    host_roots = m0_root / "mature-runtime-m0" / "host-roots"
    if host_location is None and host_roots.exists() and any(host_roots.iterdir()):
        raise RuntimeError("explicit-host-location-required")
    if host_location is None:
        host = RuntimeHost.create(
            m0_root,
            studio_location=studio_location,
            cognition=cognition,
            relationship_enabled=relationship_enabled,
            _cognition_assembly=_cognition_assembly,
            _runtime_interrupt_at=_runtime_interrupt_at,
            _runtime_fault_hook=_runtime_fault_hook,
            _activation_plan=_activation_plan,
            _fault_hook=_host_fault_hook,
            _runtime_identity=_runtime_identity,
        )
    else:
        if type(host_location) is not RuntimeHostRootRef:
            raise TypeError("host_location must be RuntimeHostRootRef")
        host = RuntimeHost.open(
            host_location,
            studio_location=studio_location,
            cognition=cognition,
            relationship_enabled=relationship_enabled,
            _cognition_assembly=_cognition_assembly,
            _runtime_interrupt_at=_runtime_interrupt_at,
            _runtime_fault_hook=_runtime_fault_hook,
            _fault_hook=_host_fault_hook,
            _local_serving_authorization=_local_serving_authorization,
            _runtime_identity=_runtime_identity,
        )
    try:
        route = (
            None
            if _local_serving_authorization is not None
            else host.open_runtime(
                qualified_runtime_input,
                timeline_id=timeline_id,
                _activation_plan=_activation_plan,
            )
        )
        binding = (
            host.query_binding(
                profile_id=qualified_runtime_input.profile_id,
                timeline_id=timeline_id,
            )
            if route is None
            else route.binding
        )
        if _local_serving_authorization is not None:
            if type(_cognition_assembly) is not _CognitionAssembly:
                raise RuntimeHostRejected(
                    "cognition-assembly-mismatch",
                    "local serving requires one exact private cognition assembly",
                )
            host._require_local_serving_plan(
                qualified_runtime_input,
                binding,
                authorization=_local_serving_authorization,
                cognition_assembly=_cognition_assembly,
            )
        submission_authorization = (
            None
            if _cognition_assembly is None
            else _cognition_assembly.submission_authorization(
                qualified_runtime_input,
                binding,
            )
        )
        if (
            qualified_runtime_input.capabilities
            == CapabilityManifest._local_first_test_double()
            and submission_authorization is None
        ):
            raise RuntimeHostRejected(
                "local-interaction-plan-mismatch",
                "local successor requires its exact single-command authorization",
            )
        application, router = _create_application_facade(
            host,
            binding,
            _single_command_authorization=submission_authorization,
            _start_runtime=(
                None
                if _local_serving_authorization is None
                else lambda: host.open_runtime(
                    qualified_runtime_input,
                    timeline_id=timeline_id,
                    _local_serving_authorization=_local_serving_authorization,
                    _serving_cognition_assembly=_cognition_assembly,
                )
            ),
            _stop_runtime=(
                None
                if _local_serving_authorization is None
                else lambda: host._stop_local_serving(
                    profile_id=qualified_runtime_input.profile_id,
                    timeline_id=timeline_id,
                    timeout_seconds=float(_local_serving_stop_timeout_seconds),
                    _authorization=_local_serving_authorization,
                )
            ),
            _query_runtime=(
                None
                if _local_serving_authorization is None
                else lambda: host._local_serving_health(
                    profile_id=qualified_runtime_input.profile_id,
                    timeline_id=timeline_id,
                    _authorization=_local_serving_authorization,
                )
            ),
            _follow_runtime=(
                None
                if _local_serving_authorization is None
                else lambda operation_ref: host._follow_local_serving(
                    operation_ref,
                    profile_id=qualified_runtime_input.profile_id,
                    timeline_id=timeline_id,
                    _authorization=_local_serving_authorization,
                )
            ),
            _character_dialogue=_character_dialogue,
            _basis_preview=_basis_preview,
            _character_model=_character_model,
            _character_reply_lab=_character_reply_lab,
            _evidence_extraction=_evidence_extraction,
            _source_authoring=_source_authoring,
            _source_studio_location=_source_studio_location,
            _source_identity_freezer=_source_identity_freezer,
            _local_identity_lister=_local_identity_lister,
            _local_identity_selector=_local_identity_selector,
            _knowledge_entries=_knowledge_entries,
        )
        return _ApplicationComposition(application, router, host)
    except Exception:
        host.close()
        raise


__all__ = ["compose_application"]
