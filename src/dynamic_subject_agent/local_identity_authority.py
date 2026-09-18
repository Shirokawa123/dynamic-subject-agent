"""Deep local identity authority Module.

Owns registry schemas, exact source freeze, authority validation, active
selection, and Host/Timeline preparation behind one small Interface.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from dynamic_subject_agent.knowledge_entries import (
    KnowledgeEntry,
    SEALED_KNOWLEDGE_ENTRIES,
)
from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection
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
    SourceIdentityFreezeRequest,
    SourceIdentityFreezeResponse,
    SourceIdentityFreezeStatus,
    SourceIdentityFreezeView,
)
from dynamic_subject_agent.host import RuntimeHost, RuntimeHostRootRef
from dynamic_subject_agent.studio import (
    CapabilityManifest,
    FreezeDecision,
    GenesisPremise,
    GenesisSnapshot,
    ParticipantProfile,
    PolicyKernel,
    QualifiedRuntimeInput,
    SourceDeclaration,
    StudioRootRef,
    SubjectStudio,
)
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition


_STATE_SCHEMA_VERSION = 1
_LEGACY_AVERY_PUBLICATION_KEY = "local-product-deepseek-qri-v1"


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


def _authoring_studio_location(config: LocalProductConfig) -> StudioRootRef:
    if not config.state_path.exists():
        raise RuntimeError("local-identity-registry-unavailable")
    saved = json.loads(config.state_path.read_text(encoding="utf-8"))
    if saved.get("schema_version") == _STATE_SCHEMA_VERSION:
        return StudioRootRef.from_dict(saved["studio_location"])
    state = _state_v2(saved)
    return StudioRootRef.from_dict(state["authoring_studio_location"])


@dataclass(frozen=True)
class _ValidatedLocalIdentity:
    qri: QualifiedRuntimeInput
    studio_location: StudioRootRef
    experiment_base: Path
    display_name: str
    freeze_basis_digest: str | None
    knowledge_member_count: int
    knowledge_entries: tuple[KnowledgeEntry, ...]
    runtime_identity: RuntimeIdentityProjection


def _runtime_identity_projection(
    *,
    qri: QualifiedRuntimeInput,
    profile: ParticipantProfile,
    snapshot: GenesisSnapshot,
) -> RuntimeIdentityProjection:
    if (
        qri.profile_id != profile.profile_id
        or qri.profile_id != snapshot.profile_id
        or qri.genesis_snapshot_id != snapshot.snapshot_id
        or qri.knowledge_snapshot_id != snapshot.knowledge_snapshot_id
    ):
        raise RuntimeError("local-runtime-identity-authority-mismatch")
    return RuntimeIdentityProjection(
        subject_name=(
            "Avery"
            if qri.publication_key == _LEGACY_AVERY_PUBLICATION_KEY
            else profile.display_name
        ),
        subject_identity=snapshot.premise.subject_identity,
        canon_start=snapshot.premise.canon_start,
    )


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
        knowledge_entries=entries,
        runtime_identity=_runtime_identity_projection(
            qri=qri,
            profile=profile,
            snapshot=snapshot,
        ),
    )


def _freeze_source_identity(
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


def _list_local_identities(config: LocalProductConfig) -> LocalIdentityListResponse:
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


def _create_identity_host(
    identity: _ValidatedLocalIdentity,
) -> tuple[RuntimeHostRootRef, str]:
    timeline_id = str(uuid4())
    dormant = DormantDeepSeekCognition()
    # New identities opt into the task contract; dormant preflight still denies
    # submission. Existing bindings are read by their persisted version.
    dormant.supports_subject_tasks = True
    dormant.supports_text_effects = True
    host = RuntimeHost.create(
        identity.experiment_base,
        studio_location=identity.studio_location,
        cognition=dormant,
    )
    try:
        host.open_runtime(identity.qri, timeline_id=timeline_id)
        return host.location, timeline_id
    finally:
        host.close()


def _validate_host_binding(
    config: LocalProductConfig,
    identity: _ValidatedLocalIdentity,
    host_location: RuntimeHostRootRef,
    timeline_id: str,
) -> None:
    host = RuntimeHost.open(
        host_location,
        studio_location=identity.studio_location,
        cognition=DormantDeepSeekCognition(),
        relationship_enabled=config.relationship_mode == "dynamic",
    )
    try:
        binding = host.query_binding(
            profile_id=identity.qri.profile_id,
            timeline_id=timeline_id,
        )
    finally:
        host.close()
    if (
        binding.qualification_id != identity.qri.qualification_id
        or binding.qri_publication_key != identity.qri.publication_key
        or binding.qri_integrity_digest != identity.qri.integrity_digest
        or binding.genesis_snapshot_id != identity.qri.genesis_snapshot_id
        or binding.knowledge_snapshot_id != identity.qri.knowledge_snapshot_id
        or binding.studio_root_id != identity.studio_location.root_id
        or binding.studio_store_id != identity.studio_location.profile_store_id
        or binding.host_root_id != host_location.root_id
        or binding.host_control_store_id != host_location.control_store_id
    ):
        raise RuntimeError("local-identity-host-binding-mismatch")


def _select_local_identity(
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
        if selected.get("host_location") is None or selected.get("timeline_id") is None:
            host_location, timeline_id = _create_identity_host(validated)
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
            _validate_host_binding(
                config,
                validated,
                host_location,
                timeline_id,
            )
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
    tuple[KnowledgeEntry, ...],
    RuntimeIdentityProjection,
]:
    if config.state_path.exists():
        saved = json.loads(config.state_path.read_text(encoding="utf-8"))
        if saved.get("schema_version") == _STATE_SCHEMA_VERSION:
            validated = _validate_identity_record(
                _authority_record_from_v1(saved)
            )
            host_location = RuntimeHostRootRef.from_dict(saved["host_location"])
            timeline_id = str(saved["timeline_id"])
            _validate_host_binding(
                config,
                validated,
                host_location,
                timeline_id,
            )
            return (
                validated.experiment_base,
                validated.studio_location,
                host_location,
                validated.qri,
                timeline_id,
                validated.studio_location,
                validated.knowledge_entries,
                validated.runtime_identity,
            )

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
        validated = _validate_identity_record(active)
        if active.get("host_location") is None:
            host_location, timeline_id = _create_identity_host(validated)
            active["host_location"] = host_location.to_dict()
            active["timeline_id"] = timeline_id
            _write_state(config.state_path, state)
        else:
            host_location = RuntimeHostRootRef.from_dict(active["host_location"])
            timeline_id = str(active["timeline_id"])
            _validate_host_binding(
                config,
                validated,
                host_location,
                timeline_id,
            )
        return (
            validated.experiment_base,
            validated.studio_location,
            host_location,
            validated.qri,
            timeline_id,
            StudioRootRef.from_dict(state["authoring_studio_location"]),
            validated.knowledge_entries,
            validated.runtime_identity,
        )

    identity = create_local_product_identity(config.product_parent)
    initial_record = _validate_identity_record(
        {
            "identity_id": identity.qualified_runtime_input.profile_id,
            "display_name": "Avery",
            "freeze_basis_digest": None,
            "experiment_base": str(identity.experiment_base),
            "studio_location": identity.studio_location.to_dict(),
            "host_location": None,
            "timeline_id": None,
            "publication_key": identity.qualified_runtime_input.publication_key,
        }
    )
    host_location, timeline_id = _create_identity_host(initial_record)
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
        initial_record.knowledge_entries,
        initial_record.runtime_identity,
    )


@dataclass(frozen=True)
class LoadedLocalIdentity:
    experiment_base: Path
    studio_location: StudioRootRef
    host_location: RuntimeHostRootRef
    qri: QualifiedRuntimeInput
    timeline_id: str
    authoring_studio_location: StudioRootRef
    knowledge_entries: tuple[KnowledgeEntry, ...]
    runtime_identity: RuntimeIdentityProjection


class LocalIdentityAuthority:
    """Small Interface over all persistent local identity authority behaviour."""

    def __init__(self, config: LocalProductConfig) -> None:
        if not isinstance(config, LocalProductConfig):
            raise TypeError("config must be LocalProductConfig")
        self._config = config

    def load_active(self) -> LoadedLocalIdentity:
        (
            experiment_base,
            studio_location,
            host_location,
            qri,
            timeline_id,
            authoring_studio_location,
            snapshot_entries,
            runtime_identity,
        ) = _load_or_create_authority(self._config)
        knowledge_entries = (
            SEALED_KNOWLEDGE_ENTRIES
            if qri.publication_key == "local-product-deepseek-qri-v1"
            else snapshot_entries
        )
        return LoadedLocalIdentity(
            experiment_base=experiment_base,
            studio_location=studio_location,
            host_location=host_location,
            qri=qri,
            timeline_id=timeline_id,
            authoring_studio_location=authoring_studio_location,
            knowledge_entries=knowledge_entries,
            runtime_identity=runtime_identity,
        )

    def freeze(
        self,
        request: object,
    ) -> SourceIdentityFreezeResponse:
        return _freeze_source_identity(
            self._config,
            source_studio_location=_authoring_studio_location(self._config),
            request=request,
        )

    def list(self) -> LocalIdentityListResponse:
        return _list_local_identities(self._config)

    def select(
        self,
        request: object,
        *,
        current: LoadedLocalIdentity | None,
    ) -> LocalIdentitySelectResponse:
        return _select_local_identity(
            self._config,
            request,
            current_profile_id=None if current is None else current.qri.profile_id,
            current_studio_location=(
                None if current is None else current.studio_location
            ),
            current_host_location=None if current is None else current.host_location,
            current_timeline_id=None if current is None else current.timeline_id,
            current_publication_key=(
                None if current is None else current.qri.publication_key
            ),
        )


__all__ = [
    "LoadedLocalIdentity",
    "LocalIdentityAuthority",
    "LocalProductConfig",
    "LocalProductIdentity",
    "create_local_product_identity",
]
