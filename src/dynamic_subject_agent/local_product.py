"""Production creation and opening seam for one persistent local product."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from dynamic_subject_agent.application import ApplicationFacade
from dynamic_subject_agent.bootstrap import compose_application
from dynamic_subject_agent.cognition import CredentialRef
from dynamic_subject_agent.composite import ControlledCompositeCognition
from dynamic_subject_agent.knowledge_entries import (
    KnowledgeEntry,
    SEALED_KNOWLEDGE_ENTRIES,
)
from dynamic_subject_agent.deepseek import (
    DEEPSEEK_CREDENTIAL_BACKEND_ID,
    DEEPSEEK_CREDENTIAL_KEY_ID,
    DEEPSEEK_MODEL,
    DEEPSEEK_PROVIDER_AUTHORITY_ID,
    DeepSeekCredentialResolver,
    DeepSeekKnowledgeProvider,
    DeepSeekLivingMemoryProvider,
    DeepSeekParticipantGoalProvider,
    DeepSeekRelationshipProvider,
    DeepSeekSituatedProvider,
    DeepSeekMediumProvider,
    DeepSeekSourceCharacterProvider,
    DeepSeekUrlLibTransport,
)
from dynamic_subject_agent.model_gateway import (
    ModelGateway,
    ProviderCapabilities,
    StructuredOutputMode,
)
from dynamic_subject_agent.participant_goal_cognition import (
    ParticipantGoalProviderAdapter,
)
from dynamic_subject_agent.situated_cognition import SituatedProviderAdapter
from dynamic_subject_agent.medium_cognition import MediumProviderAdapter
from dynamic_subject_agent.source_character_authoring import (
    LocalIdentityListResponse,
    LocalIdentitySelectRequest,
    LocalIdentitySelectResponse,
    LocalIdentityStatus,
    LocalIdentityView,
    SourceFreezeMappingRequest,
    SourceFreezeMappingResponse,
    SourceFreezeMappingStatus,
    SourceFreezeMappingView,
    SourceCharacterProviderAdapter,
    SourceIdentityFreezeRequest,
    SourceIdentityFreezeResponse,
    SourceIdentityFreezeStatus,
    SourceIdentityFreezeView,
    TextSourceCharacterAuthoring,
)
from dynamic_subject_agent.host import RuntimeHost, RuntimeHostRootRef
from dynamic_subject_agent.runtime import CognitionEngine
from dynamic_subject_agent.studio import (
    CapabilityManifest,
    FreezeDecision,
    GenesisPremise,
    ParticipantProfile,
    PolicyKernel,
    QualifiedRuntimeInput,
    SourceDeclaration,
    StudioRootRef,
    SubjectStudio,
)
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition


_STATE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class LocalProductIdentity:
    """The complete authority required to open one persistent local product."""

    experiment_base: Path
    studio_location: StudioRootRef
    qualified_runtime_input: QualifiedRuntimeInput


@dataclass(frozen=True)
class LocalProductConfig:
    """Paths and policy needed by the local composition Interface."""

    product_parent: Path
    state_path: Path
    relationship_mode: str = "dynamic"

    def __post_init__(self) -> None:
        if not isinstance(self.product_parent, Path) or not self.product_parent.is_absolute():
            raise TypeError("product_parent must be an explicit absolute Path")
        if not isinstance(self.state_path, Path) or not self.state_path.is_absolute():
            raise TypeError("state_path must be an explicit absolute Path")
        if self.relationship_mode not in {"off", "dynamic"}:
            raise ValueError("relationship_mode must be off or dynamic")

    @classmethod
    def default(cls) -> LocalProductConfig:
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        product_root = base / "DynamicSubjectAgent"
        return cls(
            product_parent=product_root / "m0" / "experiments",
            state_path=product_root / "state.json",
        )


class OpenedLocalProduct:
    """A running local product with one public application Interface."""

    def __init__(
        self,
        *,
        composition: object,
        qualified_runtime_input: QualifiedRuntimeInput,
        timeline_id: str,
    ) -> None:
        self._composition = composition
        self._qri = qualified_runtime_input
        self.timeline_id = timeline_id

    @property
    def application(self) -> ApplicationFacade:
        return self._composition.application  # type: ignore[attr-defined,no-any-return]

    @property
    def profile_id(self) -> str:
        return self._qri.profile_id

    @property
    def publication_key(self) -> str:
        return self._qri.publication_key

    def __enter__(self) -> OpenedLocalProduct:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._composition.close()  # type: ignore[attr-defined]


def create_local_product_identity(product_parent: Path) -> LocalProductIdentity:
    """Create and publish one original Avery identity through production seams."""

    if not isinstance(product_parent, Path) or not product_parent.is_absolute():
        raise TypeError("product_parent must be an explicit absolute Path")
    experiment_base = product_parent / str(uuid4())
    profile = ParticipantProfile.original(
        display_name="Current participant",
        identity_core=(
            "The current user is the sole present-day participant in this local "
            "product; no legacy/private identity, role, approval, history, trust, "
            "or relationship state is inherited."
        ),
        source=SourceDeclaration.project_original(rights_confirmed=True),
    )
    premise = GenesisPremise(
        subject_identity=(
            "Avery is an adult fictional creator and editor of the original "
            "community publication Lantern Zine."
        ),
        canon_start=(
            "Avery and the participant are preparing the original Lantern Zine and "
            "checking whether its next issue can still reach Friday's print slot; "
            "no later progress is asserted."
        ),
        initial_relationship_premise=(
            "Avery and the participant are newly acquainted collaborators; no trust, "
            "promise, shared memory, completed work, or earned relationship state is "
            "preloaded."
        ),
        source=SourceDeclaration.project_original(rights_confirmed=True),
    )
    studio = SubjectStudio.create(experiment_base, policy_kernel=PolicyKernel())
    try:
        draft = studio.create_draft(profile=profile, premise=premise)
        preview = studio.preview(draft.draft_id)
        decision = studio.decide_policy(
            draft.draft_id,
            CapabilityManifest.deepseek_v4_flash_experimental(),
        )
        snapshot = studio.seal(
            draft.draft_id,
            FreezeDecision.for_preview(
                preview,
                decided_by="local-user-startup",
                rationale="Create the explicitly selected original local product identity.",
            ),
            policy_decision_id=decision.decision_id,
        )
        qri = studio.publish(
            snapshot.snapshot_id,
            policy_decision_id=decision.decision_id,
            publication_key="local-product-deepseek-qri-v1",
        )
        return LocalProductIdentity(
            experiment_base=experiment_base,
            studio_location=studio.location,
            qualified_runtime_input=qri,
        )
    finally:
        studio.close()


def _write_state(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _authority_record_from_v1(saved: dict[str, object]) -> dict[str, object]:
    studio_location = StudioRootRef.from_dict(saved["studio_location"])
    studio = SubjectStudio.open(studio_location, policy_kernel=PolicyKernel())
    try:
        qri = studio.query_qri(publication_key=str(saved["publication_key"]))
    finally:
        studio.close()
    return {
        "identity_id": qri.profile_id,
        "display_name": "Avery",
        "freeze_basis_digest": None,
        "experiment_base": str(saved["experiment_base"]),
        "studio_location": saved["studio_location"],
        "host_location": saved["host_location"],
        "timeline_id": str(saved["timeline_id"]),
        "publication_key": str(saved["publication_key"]),
    }


def _state_v2(saved: dict[str, object]) -> dict[str, object]:
    if saved.get("schema_version") == 2:
        identities = saved.get("identities")
        if not isinstance(identities, list) or not identities:
            raise RuntimeError("invalid-local-product-state")
        return saved
    if saved.get("schema_version") != 1:
        raise RuntimeError("unsupported-local-product-state")
    legacy = _authority_record_from_v1(saved)
    return {
        "schema_version": 2,
        "active_identity_id": legacy["identity_id"],
        "authoring_studio_location": saved["studio_location"],
        "identities": [legacy],
    }


@dataclass(frozen=True)
class _ValidatedLocalIdentity:
    qri: QualifiedRuntimeInput
    studio_location: StudioRootRef
    experiment_base: Path
    display_name: str
    freeze_basis_digest: str | None
    knowledge_member_count: int


def _validate_identity_record(record: object) -> _ValidatedLocalIdentity:
    if not isinstance(record, dict):
        raise RuntimeError("local-identity-registry-invalid")
    studio_location = StudioRootRef.from_dict(record["studio_location"])
    experiment_base = Path(str(record["experiment_base"]))
    studio = SubjectStudio.open(studio_location, policy_kernel=PolicyKernel())
    try:
        qri = studio.query_qri(publication_key=str(record["publication_key"]))
        profile = studio.query_profile(qri.profile_id)
        snapshot = studio.query_snapshot(qri.genesis_snapshot_id)
        entries = studio.knowledge_entries(qri.knowledge_snapshot_id)
    finally:
        studio.close()
    expected_display_name = (
        "Avery"
        if qri.publication_key == "local-product-deepseek-qri-v1"
        else profile.display_name
    )
    if (
        record.get("identity_id") != qri.profile_id
        or record.get("display_name") != expected_display_name
        or experiment_base.resolve() != studio_location.root.parents[2].resolve()
        or record.get("freeze_basis_digest")
        != snapshot.source_freeze_basis_digest
        or (record.get("host_location") is None)
        != (record.get("timeline_id") is None)
    ):
        raise RuntimeError("local-identity-authority-mismatch")
    if record.get("host_location") is not None:
        RuntimeHostRootRef.from_dict(record["host_location"])
    return _ValidatedLocalIdentity(
        qri=qri,
        studio_location=studio_location,
        experiment_base=experiment_base,
        display_name=expected_display_name,
        freeze_basis_digest=snapshot.source_freeze_basis_digest,
        knowledge_member_count=len(entries),
    )


def freeze_source_identity(
    config: LocalProductConfig,
    *,
    source_studio_location: StudioRootRef,
    request: object,
) -> SourceIdentityFreezeResponse:
    """Freeze one exact Source Draft basis and register it without activating it."""

    if not isinstance(request, SourceIdentityFreezeRequest):
        return SourceIdentityFreezeResponse(
            SourceIdentityFreezeStatus.REJECTED,
            problem_code="source-identity-freeze-request-invalid",
        )
    if request.confirmed is not True:
        return SourceIdentityFreezeResponse(
            SourceIdentityFreezeStatus.REJECTED,
            problem_code="source-identity-freeze-confirmation-required",
        )
    replay = _replay_registered_source_identity(config, request)
    if replay is not None:
        return replay
    source_studio = SubjectStudio.open(
        source_studio_location,
        policy_kernel=PolicyKernel(),
    )
    try:
        result = source_studio.execute_locked_source_freeze(
            SourceFreezeMappingRequest(
                expected_revision=request.expected_revision,
                display_name=request.display_name,
            ),
            lambda mapping: _freeze_mapped_source_identity(
                config,
                request=request,
                mapping=mapping,
            ),
        )
    finally:
        source_studio.close()
    if isinstance(result, SourceFreezeMappingResponse):
        status = {
            SourceFreezeMappingStatus.CONFLICT: SourceIdentityFreezeStatus.CONFLICT,
            SourceFreezeMappingStatus.FAILED_CLOSED: (
                SourceIdentityFreezeStatus.FAILED_CLOSED
            ),
            SourceFreezeMappingStatus.UNAVAILABLE: SourceIdentityFreezeStatus.UNAVAILABLE,
        }.get(result.status, SourceIdentityFreezeStatus.REJECTED)
        return SourceIdentityFreezeResponse(
            status,
            problem_code=result.problem_code,
        )
    if not isinstance(result, SourceIdentityFreezeResponse):
        return SourceIdentityFreezeResponse(
            SourceIdentityFreezeStatus.FAILED_CLOSED,
            problem_code="source-identity-freeze-result-invalid",
        )
    return result


def _replay_registered_source_identity(
    config: LocalProductConfig,
    request: SourceIdentityFreezeRequest,
) -> SourceIdentityFreezeResponse | None:
    if not config.state_path.exists():
        return None
    try:
        state = json.loads(config.state_path.read_text(encoding="utf-8"))
        if state.get("schema_version") != 2:
            return None
        identities = state.get("identities")
        if not isinstance(identities, list):
            return SourceIdentityFreezeResponse(
                SourceIdentityFreezeStatus.FAILED_CLOSED,
                problem_code="local-identity-registry-invalid",
            )
        record = next(
            (
                item
                for item in identities
                if isinstance(item, dict)
                and item.get("freeze_basis_digest")
                == request.freeze_basis_digest
            ),
            None,
        )
        if record is None or "source_draft_revision" not in record:
            return None
        if (
            record.get("source_draft_revision") != request.expected_revision
            or record.get("display_name") != request.display_name.strip()
        ):
            return SourceIdentityFreezeResponse(
                SourceIdentityFreezeStatus.CONFLICT,
                problem_code="source-identity-freeze-command-conflict",
            )
        validated = _validate_identity_record(record)
        if validated.display_name != request.display_name.strip():
            return SourceIdentityFreezeResponse(
                SourceIdentityFreezeStatus.FAILED_CLOSED,
                problem_code="local-identity-authority-mismatch",
            )
        return SourceIdentityFreezeResponse(
            SourceIdentityFreezeStatus.REPLAYED,
            view=SourceIdentityFreezeView(
                identity_id=validated.qri.profile_id,
                display_name=validated.display_name,
                freeze_basis_digest=request.freeze_basis_digest,
                publication_key=validated.qri.publication_key,
                knowledge_member_count=validated.knowledge_member_count,
                active=(
                    state.get("active_identity_id")
                    == validated.qri.profile_id
                ),
            ),
        )
    except Exception:
        return SourceIdentityFreezeResponse(
            SourceIdentityFreezeStatus.FAILED_CLOSED,
            problem_code="source-identity-replay-failed-closed",
        )


def _freeze_mapped_source_identity(
    config: LocalProductConfig,
    *,
    request: SourceIdentityFreezeRequest,
    mapping: SourceFreezeMappingView,
) -> SourceIdentityFreezeResponse:
    if request.freeze_basis_digest != mapping.freeze_basis_digest:
        return SourceIdentityFreezeResponse(
            SourceIdentityFreezeStatus.CONFLICT,
            problem_code="source-identity-freeze-basis-conflict",
        )

    source_id = str(
        uuid5(
            NAMESPACE_URL,
            "dynamic-subject-agent:source-declaration:"
            f"{mapping.source_digest}:{mapping.freeze_basis_digest}",
        )
    )
    source = SourceDeclaration(
        source_id=source_id,
        origin_kind="project-original",
        rights_confirmed=True,
        source_asset_refs=(),
        uses_disallowed_inheritance=False,
    )
    profile = ParticipantProfile(
        profile_id=mapping.profile.profile_id,
        display_name=mapping.profile.display_name,
        identity_core=mapping.profile.identity_core,
        source=source,
    )
    premise = GenesisPremise(
        subject_identity=mapping.genesis.subject_identity,
        canon_start=mapping.genesis.canon_start,
        initial_relationship_premise=(
            mapping.genesis.initial_relationship_premise
        ),
        source=source,
    )
    knowledge_entries = tuple(
        KnowledgeEntry(
            entry_id=str(
                uuid5(
                    NAMESPACE_URL,
                    "dynamic-subject-agent:source-knowledge:"
                    f"{mapping.freeze_basis_digest}:{ordinal}",
                )
            ),
            title=member.title,
            content=member.content,
            source_ref=f"source-freeze:{member.source_digest}",
            evidence_quote=member.evidence_quote,
        )
        for ordinal, member in enumerate(mapping.knowledge_members)
    )
    target, experiment_base = SubjectStudio.open_or_create_source_identity(
        config.product_parent,
        freeze_basis_digest=mapping.freeze_basis_digest,
        policy_kernel=PolicyKernel(),
    )
    try:
        publication_key = "source-freeze-" + mapping.freeze_basis_digest
        try:
            qri = target.query_qri(publication_key=publication_key)
            snapshot = target.query_snapshot(qri.genesis_snapshot_id)
            replayed = True
        except Exception as error:
            if getattr(error, "code", None) != "qri-not-found":
                raise
            draft = target.ensure_source_identity_draft(
                profile=profile,
                premise=premise,
                source_freeze_basis_digest=mapping.freeze_basis_digest,
            )
            preview = target.preview(draft.draft_id)
            policy = target.decide_policy(
                draft.draft_id,
                CapabilityManifest.deepseek_v4_flash_experimental(),
                validity_us=300_000_000,
            )
            freeze = FreezeDecision(
                decision_id=str(
                    uuid5(
                        NAMESPACE_URL,
                        "dynamic-subject-agent:source-freeze-decision:"
                        + mapping.freeze_basis_digest,
                    )
                ),
                draft_id=draft.draft_id,
                expected_revision=preview.revision,
                freeze_basis_digest=preview.freeze_basis_digest,
                decided_by="local-user-source-freeze",
                rationale=(
                    "Create the explicitly confirmed source-derived isolated identity."
                ),
            )
            snapshot = target.seal(
                draft.draft_id,
                freeze,
                policy_decision_id=policy.decision_id,
                knowledge_entries=knowledge_entries,
                source_freeze_basis_digest=mapping.freeze_basis_digest,
            )
            qri = target.publish(
                snapshot.snapshot_id,
                policy_decision_id=policy.decision_id,
                publication_key=publication_key,
            )
            replayed = False
        sealed_entries = target.knowledge_entries(qri.knowledge_snapshot_id)
        if (
            qri.profile_id != mapping.profile.profile_id
            or snapshot.source_freeze_basis_digest != mapping.freeze_basis_digest
            or sealed_entries != knowledge_entries
        ):
            raise RuntimeError("source-identity-sealed-authority-mismatch")
        studio_location = target.location
    finally:
        target.close()

    if not config.state_path.exists():
        return SourceIdentityFreezeResponse(
            SourceIdentityFreezeStatus.FAILED_CLOSED,
            problem_code="local-identity-registry-unavailable",
        )
    state = _state_v2(json.loads(config.state_path.read_text(encoding="utf-8")))
    identities = state["identities"]
    assert isinstance(identities, list)
    existing = next(
        (
            item
            for item in identities
            if isinstance(item, dict)
            and item.get("identity_id") == qri.profile_id
        ),
        None,
    )
    record = {
        "identity_id": qri.profile_id,
        "display_name": mapping.profile.display_name,
        "freeze_basis_digest": mapping.freeze_basis_digest,
        "source_draft_revision": mapping.draft_revision,
        "experiment_base": str(experiment_base),
        "studio_location": studio_location.to_dict(),
        "host_location": None,
        "timeline_id": None,
        "publication_key": qri.publication_key,
    }
    if existing is None:
        identities.append(record)
    else:
        if "source_draft_revision" not in existing:
            existing["source_draft_revision"] = mapping.draft_revision
    if existing is not None and any(
        existing.get(field) != record[field]
        for field in (
            "identity_id",
            "display_name",
            "freeze_basis_digest",
            "source_draft_revision",
            "experiment_base",
            "studio_location",
            "publication_key",
        )
    ):
        raise RuntimeError("local-identity-registry-conflict")
    _write_state(config.state_path, state)
    return SourceIdentityFreezeResponse(
        SourceIdentityFreezeStatus.REPLAYED if replayed else SourceIdentityFreezeStatus.CREATED,
        view=SourceIdentityFreezeView(
            identity_id=qri.profile_id,
            display_name=mapping.profile.display_name,
            freeze_basis_digest=mapping.freeze_basis_digest,
            publication_key=qri.publication_key,
            knowledge_member_count=len(sealed_entries),
            active=state["active_identity_id"] == qri.profile_id,
        ),
    )


def list_local_identities(config: LocalProductConfig) -> LocalIdentityListResponse:
    if not config.state_path.exists():
        return LocalIdentityListResponse(LocalIdentityStatus.UNAVAILABLE)
    try:
        state = _state_v2(
            json.loads(config.state_path.read_text(encoding="utf-8"))
        )
        identities = state["identities"]
        assert isinstance(identities, list)
        validated = tuple(
            (_validate_identity_record(item), item) for item in identities
        )
        views = tuple(
            LocalIdentityView(
                identity_id=value.qri.profile_id,
                display_name=value.display_name,
                freeze_basis_digest=value.freeze_basis_digest,
                active=item["identity_id"] == state["active_identity_id"],
            )
            for value, item in validated
        )
    except Exception:
        return LocalIdentityListResponse(
            LocalIdentityStatus.FAILED_CLOSED,
            problem_code="local-identity-registry-invalid",
        )
    return LocalIdentityListResponse(LocalIdentityStatus.AVAILABLE, views)


def select_local_identity(
    config: LocalProductConfig,
    request: object,
    *,
    current_profile_id: str | None = None,
    current_studio_location: StudioRootRef | None = None,
    current_host_location: RuntimeHostRootRef | None = None,
    current_timeline_id: str | None = None,
    current_publication_key: str | None = None,
) -> LocalIdentitySelectResponse:
    if (
        not isinstance(request, LocalIdentitySelectRequest)
        or request.confirmed is not True
        or not request.identity_id
    ):
        return LocalIdentitySelectResponse(
            LocalIdentityStatus.REJECTED,
            problem_code="local-identity-selection-invalid",
        )
    try:
        state = _state_v2(
            json.loads(config.state_path.read_text(encoding="utf-8"))
        )
        identities = state["identities"]
        assert isinstance(identities, list)
        selected = next(
            (
                item
                for item in identities
                if isinstance(item, dict)
                and item.get("identity_id") == request.identity_id
            ),
            None,
        )
        if selected is None:
            return LocalIdentitySelectResponse(
                LocalIdentityStatus.NOT_FOUND,
                problem_code="local-identity-not-found",
            )
        validated = _validate_identity_record(selected)
        qri = validated.qri
        experiment_base = validated.experiment_base
        studio_location = validated.studio_location
        if selected.get("host_location") is None or selected.get("timeline_id") is None:
            timeline_id = str(uuid4())
            dormant_host = RuntimeHost.create(
                experiment_base,
                studio_location=studio_location,
                cognition=DormantDeepSeekCognition(),
            )
            try:
                dormant_host.open_runtime(qri, timeline_id=timeline_id)
                host_location = dormant_host.location
            finally:
                dormant_host.close()
            selected["host_location"] = host_location.to_dict()
            selected["timeline_id"] = timeline_id
        elif request.identity_id == current_profile_id:
            if (
                current_studio_location is None
                or current_host_location is None
                or current_timeline_id is None
                or current_publication_key is None
                or selected.get("studio_location")
                != current_studio_location.to_dict()
                or selected.get("host_location") != current_host_location.to_dict()
                or selected.get("timeline_id") != current_timeline_id
                or selected.get("publication_key") != current_publication_key
            ):
                raise RuntimeError("local-identity-current-authority-mismatch")
        else:
            host_location = RuntimeHostRootRef.from_dict(selected["host_location"])
            timeline_id = str(selected["timeline_id"])
            host = RuntimeHost.open(
                host_location,
                studio_location=studio_location,
                cognition=DormantDeepSeekCognition(),
                relationship_enabled=config.relationship_mode == "dynamic",
            )
            try:
                route = host.open_runtime(qri, timeline_id=timeline_id)
                if (
                    route.binding.profile_id != qri.profile_id
                    or route.binding.timeline_id != timeline_id
                ):
                    raise RuntimeError("local-identity-host-binding-mismatch")
            finally:
                host.close()
        state["active_identity_id"] = request.identity_id
        _write_state(config.state_path, state)
        view = LocalIdentityView(
            identity_id=str(selected["identity_id"]),
            display_name=validated.display_name,
            freeze_basis_digest=validated.freeze_basis_digest,
            active=True,
        )
    except Exception:
        return LocalIdentitySelectResponse(
            LocalIdentityStatus.FAILED_CLOSED,
            problem_code="local-identity-selection-failed-closed",
        )
    return LocalIdentitySelectResponse(LocalIdentityStatus.SELECTED, view)


def _load_or_create_authority(
    config: LocalProductConfig,
) -> tuple[
    Path,
    StudioRootRef,
    RuntimeHostRootRef,
    QualifiedRuntimeInput,
    str,
    StudioRootRef,
]:
    if config.state_path.exists():
        saved = json.loads(config.state_path.read_text(encoding="utf-8"))
        active: dict[str, object] | None = None
        if saved.get("schema_version") == 1:
            experiment_base = Path(str(saved["experiment_base"]))
            studio_location = StudioRootRef.from_dict(saved["studio_location"])
            host_location = RuntimeHostRootRef.from_dict(saved["host_location"])
            timeline_id = str(saved["timeline_id"])
            authoring_location = studio_location
            publication_key = str(saved["publication_key"])
        else:
            state = _state_v2(saved)
            identities = state["identities"]
            assert isinstance(identities, list)
            active = next(
                (
                    item
                    for item in identities
                    if isinstance(item, dict)
                    and item.get("identity_id") == state["active_identity_id"]
                ),
                None,
            )
            if active is None:
                raise RuntimeError("active-local-identity-not-found")
            experiment_base = Path(str(active["experiment_base"]))
            studio_location = StudioRootRef.from_dict(active["studio_location"])
            publication_key = str(active["publication_key"])
            authoring_location = StudioRootRef.from_dict(
                state["authoring_studio_location"]
            )
            if active.get("host_location") is None or active.get("timeline_id") is None:
                studio = SubjectStudio.open(
                    studio_location,
                    policy_kernel=PolicyKernel(),
                )
                try:
                    qri = studio.query_qri(publication_key=publication_key)
                finally:
                    studio.close()
                timeline_id = str(uuid4())
                dormant_host = RuntimeHost.create(
                    experiment_base,
                    studio_location=studio_location,
                    cognition=DormantDeepSeekCognition(),
                )
                try:
                    dormant_host.open_runtime(qri, timeline_id=timeline_id)
                    host_location = dormant_host.location
                finally:
                    dormant_host.close()
                active["host_location"] = host_location.to_dict()
                active["timeline_id"] = timeline_id
                _write_state(config.state_path, state)
            else:
                host_location = RuntimeHostRootRef.from_dict(active["host_location"])
                timeline_id = str(active["timeline_id"])
        studio = SubjectStudio.open(studio_location, policy_kernel=PolicyKernel())
        try:
            qri = studio.query_qri(publication_key=publication_key)
            if active is not None:
                profile = studio.query_profile(qri.profile_id)
                snapshot = studio.query_snapshot(qri.genesis_snapshot_id)
                expected_experiment_base = studio_location.root.parents[2]
                expected_display_name = (
                    "Avery"
                    if qri.publication_key == "local-product-deepseek-qri-v1"
                    else profile.display_name
                )
                if (
                    active.get("identity_id") != qri.profile_id
                    or active.get("display_name") != expected_display_name
                    or Path(str(active.get("experiment_base"))).resolve()
                    != expected_experiment_base.resolve()
                    or snapshot.profile_id != qri.profile_id
                    or active.get("freeze_basis_digest")
                    != snapshot.source_freeze_basis_digest
                ):
                    raise RuntimeError("local-identity-authority-mismatch")
        finally:
            studio.close()
        return (
            experiment_base,
            studio_location,
            host_location,
            qri,
            timeline_id,
            authoring_location,
        )

    identity = create_local_product_identity(config.product_parent)
    timeline_id = str(uuid4())
    dormant_host = RuntimeHost.create(
        identity.experiment_base,
        studio_location=identity.studio_location,
        cognition=DormantDeepSeekCognition(),
    )
    try:
        dormant_host.open_runtime(
            identity.qualified_runtime_input,
            timeline_id=timeline_id,
        )
        host_location = dormant_host.location
    finally:
        dormant_host.close()
    _write_state(
        config.state_path,
        {
            "schema_version": _STATE_SCHEMA_VERSION,
            "studio_location": identity.studio_location.to_dict(),
            "host_location": host_location.to_dict(),
            "experiment_base": str(identity.experiment_base),
            "timeline_id": timeline_id,
            "publication_key": identity.qualified_runtime_input.publication_key,
        },
    )
    return (
        identity.experiment_base,
        identity.studio_location,
        host_location,
        identity.qualified_runtime_input,
        timeline_id,
        identity.studio_location,
    )


def open_local_product(
    config: LocalProductConfig,
    *,
    cognition: CognitionEngine,
    source_authoring: TextSourceCharacterAuthoring | None = None,
) -> OpenedLocalProduct:
    """Open the one persistent product through its production composition root."""

    if not isinstance(config, LocalProductConfig):
        raise TypeError("config must be LocalProductConfig")
    if not isinstance(cognition, CognitionEngine):
        raise TypeError("cognition must satisfy the CognitionEngine Interface")
    return _open_loaded_local_product(
        config,
        cognition=cognition,
        source_authoring=source_authoring,
        loaded=_load_or_create_authority(config),
    )


def _open_loaded_local_product(
    config: LocalProductConfig,
    *,
    cognition: CognitionEngine,
    source_authoring: TextSourceCharacterAuthoring | None,
    loaded: tuple[
        Path,
        StudioRootRef,
        RuntimeHostRootRef,
        QualifiedRuntimeInput,
        str,
        StudioRootRef,
    ],
) -> OpenedLocalProduct:
    (
        experiment_base,
        studio_location,
        host_location,
        qri,
        timeline_id,
        authoring_studio_location,
    ) = loaded
    studio = SubjectStudio.open(studio_location, policy_kernel=PolicyKernel())
    try:
        sealed_knowledge_entries = studio.knowledge_entries(qri.knowledge_snapshot_id)
    finally:
        studio.close()
    effective_knowledge_entries = (
        SEALED_KNOWLEDGE_ENTRIES
        if qri.publication_key == "local-product-deepseek-qri-v1"
        else sealed_knowledge_entries
    )
    composition = compose_application(
        m0_root=experiment_base,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
        _cognition=cognition,
        relationship_mode=config.relationship_mode,
        _source_authoring=source_authoring,
        _source_studio_location=authoring_studio_location,
        _source_identity_freezer=lambda request: freeze_source_identity(
            config,
            source_studio_location=authoring_studio_location,
            request=request,
        ),
        _local_identity_lister=lambda: list_local_identities(config),
        _local_identity_selector=lambda request: select_local_identity(
            config,
            request,
            current_profile_id=qri.profile_id,
            current_studio_location=studio_location,
            current_host_location=host_location,
            current_timeline_id=timeline_id,
            current_publication_key=qri.publication_key,
        ),
        _knowledge_entries=effective_knowledge_entries,
    )
    return OpenedLocalProduct(
        composition=composition,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
    )


def open_deepseek_local_product(
    config: LocalProductConfig,
    *,
    api_key: str,
) -> OpenedLocalProduct:
    """Open the default product with the DeepSeek cognition Adapter."""

    key = api_key.strip() if isinstance(api_key, str) else ""
    if not key:
        raise RuntimeError("DeepSeek API key is required")

    loaded = _load_or_create_authority(config)
    (
        _experiment_base,
        studio_location,
        _host_location,
        qri,
        _timeline_id,
        _authoring_location,
    ) = loaded
    studio = SubjectStudio.open(studio_location, policy_kernel=PolicyKernel())
    try:
        snapshot_entries = studio.knowledge_entries(qri.knowledge_snapshot_id)
    finally:
        studio.close()
    effective_knowledge_entries = (
        SEALED_KNOWLEDGE_ENTRIES
        if qri.publication_key == "local-product-deepseek-qri-v1"
        else snapshot_entries
    )

    class _Resolver(DeepSeekCredentialResolver):
        def resolve(self, credential_ref: CredentialRef) -> str:
            del credential_ref
            return key

    transport = DeepSeekUrlLibTransport(credential_resolver=_Resolver())
    credential_ref = CredentialRef.reference(
        backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
        key_id=DEEPSEEK_CREDENTIAL_KEY_ID,
    )
    provider_kwargs = {
        "transport": transport,
        "credential_ref": credential_ref,
    }
    participant_goal_gateway = ModelGateway(
        ParticipantGoalProviderAdapter(
            provider=DeepSeekParticipantGoalProvider(**provider_kwargs),
            capabilities=ProviderCapabilities(
                provider_id=DEEPSEEK_PROVIDER_AUTHORITY_ID,
                model_id=DEEPSEEK_MODEL,
                local=False,
                structured_output_modes=(StructuredOutputMode.JSON_OBJECT,),
            ),
        )
    )
    situated_gateway = ModelGateway(
        SituatedProviderAdapter(
            provider=DeepSeekSituatedProvider(**provider_kwargs),
            capabilities=ProviderCapabilities(
                provider_id=DEEPSEEK_PROVIDER_AUTHORITY_ID,
                model_id=DEEPSEEK_MODEL,
                local=False,
                structured_output_modes=(StructuredOutputMode.JSON_OBJECT,),
            ),
        )
    )
    medium_gateway = ModelGateway(
        MediumProviderAdapter(
            provider=DeepSeekMediumProvider(**provider_kwargs),
            capabilities=ProviderCapabilities(
                provider_id=DEEPSEEK_PROVIDER_AUTHORITY_ID,
                model_id=DEEPSEEK_MODEL,
                local=False,
                structured_output_modes=(StructuredOutputMode.JSON_OBJECT,),
            ),
        )
    )
    cognition = ControlledCompositeCognition(
        memory_provider=DeepSeekLivingMemoryProvider(**provider_kwargs),
        knowledge_provider=DeepSeekKnowledgeProvider(**provider_kwargs),
        relationship_provider=DeepSeekRelationshipProvider(**provider_kwargs),
        knowledge_entries=effective_knowledge_entries,
        participant_goal_gateway=participant_goal_gateway,
        situated_gateway=situated_gateway,
        medium_gateway=medium_gateway,
    )
    source_authoring = TextSourceCharacterAuthoring(
        gateway=ModelGateway(
            SourceCharacterProviderAdapter(
                provider=DeepSeekSourceCharacterProvider(**provider_kwargs),
                capabilities=ProviderCapabilities(
                    provider_id=DEEPSEEK_PROVIDER_AUTHORITY_ID,
                    model_id=DEEPSEEK_MODEL,
                    local=False,
                    structured_output_modes=(StructuredOutputMode.JSON_OBJECT,),
                ),
            )
        )
    )
    return _open_loaded_local_product(
        config,
        cognition=cognition,
        source_authoring=source_authoring,
        loaded=loaded,
    )


__all__ = [
    "LocalProductConfig",
    "LocalProductIdentity",
    "OpenedLocalProduct",
    "create_local_product_identity",
    "freeze_source_identity",
    "list_local_identities",
    "open_deepseek_local_product",
    "open_local_product",
    "select_local_identity",
]
