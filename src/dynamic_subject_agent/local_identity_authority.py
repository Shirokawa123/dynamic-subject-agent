"""Deep local identity authority Module.

Owns registry schemas, exact source freeze, authority validation, active
selection, and Host/Timeline preparation behind one small Interface.
"""

from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from functools import wraps
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5
from dynamic_subject_agent.first_life_authorization import LEGACY_RUNTIME_POLICY, ShareAuthorization, ShareAuthorizationChanged, registry_lock

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
from dynamic_subject_agent.host import RuntimeHost, RuntimeHostRootRef, _CognitionAssembly
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


from dynamic_subject_agent.reviewed_character_definition import (
    ReviewedCharacterFreezeRequest, REVIEWED_CHARACTER_AUTHORITY,
    prepare_reviewed_definition, reviewed_source_refs, reviewed_profile_id,
)
from dynamic_subject_agent.reviewed_character_cognition import ReviewedCharacterDormantCognition

from dynamic_subject_agent.first_life import (LIFE_AUTHORITY, LIFE_DORMANT_AUTHORITY, FirstLifeIdentityRequest, first_life_definition, first_life_source_refs, life_profile_id)
from dynamic_subject_agent.first_life_cognition import FirstLifeCognition, FirstLifeDormantCognition
from dynamic_subject_agent.first_life_budget import FirstLifeBudget
from dynamic_subject_agent.reviewed_character_chat import CHAT_AUTHORITY, chat_contract, ReviewedCharacterChatStatus
from dynamic_subject_agent.reviewed_character_chat_cognition import ReviewedCharacterChatCognition
from dynamic_subject_agent.character_chat_budget import CharacterChatBudget
from dynamic_subject_agent.original_whole_chat import (WHOLE_AUTHORITY, WHOLE_AUTHORITIES, whole_contract,
    validate_whole_envelope, OriginalWholeAuthorization, digest as whole_digest, whole_publication_key, contract_variant)
from dynamic_subject_agent.whole_context_boundary import CONTEXT_AUTHORITY
from dynamic_subject_agent.shared_activity import SHARED_AUTHORITY, SHARED_LIVE_AUTHORITY, LIVING_AUTHORITY, LIVING_LIVE_AUTHORITY, LIVING_AUTHORITIES, SHARED_AUTHORITIES, shared_contract
from dynamic_subject_agent.original_whole_chat_cognition import OriginalWholeChatCognition
from dynamic_subject_agent.original_whole_chat_audit import open_original_whole_audit

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
            product_parent=product_root / "DynamicSubjectAgent" / "m0" / "experiments",
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
    reviewed_definition: dict | None = None


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


def _validate_identity_record(record: object, *, expected_parent: Path | None = None) -> _ValidatedLocalIdentity:
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
    if snapshot.reviewed_definition is not None:
        envelope = snapshot.reviewed_definition
        if (expected_parent is None or experiment_base.resolve().parent != expected_parent.resolve()
            or record.get("identity_kind") != "reviewed-fiction-derived"
            or record.get("definition_basis") != envelope["definition_basis"]
            or record.get("runtime_asset_sha") != envelope["runtime_asset_sha"]):
            raise RuntimeError("reviewed-local-identity-authority-mismatch")
    elif any(key in record for key in ("identity_kind", "definition_basis", "runtime_asset_sha")):
        raise RuntimeError("reviewed-local-identity-pointer-invalid")
    if qri.provider_authority in (LIFE_AUTHORITY, LIFE_DORMANT_AUTHORITY):
        contract = snapshot.first_life_contract
        if (contract is None or record.get("life_scope_digest") != contract["life_scope_digest"]
            or record.get("life_identity_basis") != contract["identity_basis"]):
            raise RuntimeError("first-life-identity-pointer-invalid")
        if qri.provider_authority == LIFE_AUTHORITY:
            from dynamic_subject_agent.first_life_reply_routes import LOCAL_REPLY_POLICIES, REMOTE_REPLY_POLICIES as LIVE_REPLY_POLICIES, REPLY_POLICIES
            from dynamic_subject_agent.first_life_reply_drafts import reply_scope_digest
            metadata = record.get("life_activation")
            keys = {"contract", "budget_path", "budget_total", "initial_budget_used", "development_run"}
            saved_policy = record.get("life_runtime_policy")
            local_policy = isinstance(saved_policy, dict) and saved_policy.get("version") in LOCAL_REPLY_POLICIES
            if type(metadata) is dict and "local_reply_route" in metadata or local_policy:
                if (not local_policy or type(metadata) is not dict or set(metadata) != keys | {"local_reply_route"}
                    or metadata["development_run"] is not True
                    or metadata["local_reply_route"] != dict(version=saved_policy["version"],
                        digest=reply_scope_digest(envelope["definition_basis"], saved_policy["version"]))
                    or saved_policy.get("digest") != metadata["local_reply_route"]["digest"]):
                    raise RuntimeError("local-reply-activation-invalid")
                keys = keys | {"local_reply_route"}
            live_policy = isinstance(saved_policy, dict) and saved_policy.get("version") in LIVE_REPLY_POLICIES
            if type(metadata) is dict and "live_reply_route" in metadata or live_policy:
                from dynamic_subject_agent.first_life_reply_live import resolve_reply_trial as approved_trial_from_witness, approved_reply_scope_digest as live_reply_scope_digest
                if (not live_policy or type(metadata) is not dict or set(metadata) != keys | {"live_reply_route"}
                    or metadata["development_run"] is not True or type(record.get("reply_live_started")) is not bool):
                    raise RuntimeError("live-reply-activation-invalid")
                witness = metadata["live_reply_route"]
                if type(witness) is not dict or set(witness) != {"version", "digest", "approval"}:
                    raise RuntimeError("live-reply-activation-invalid")
                approval = approved_trial_from_witness(witness["approval"])
                branch = witness["approval"]["branch_id"]
                _, policy = approval.branch(branch)
                if (witness != dict(version=policy, digest=live_reply_scope_digest(envelope["definition_basis"], policy), approval=witness["approval"])
                    or saved_policy.get("version") != policy or saved_policy.get("digest") != witness["digest"]
                    or expected_parent.resolve() != (approval.root / branch / "DynamicSubjectAgent" / "m0" / "experiments").resolve()
                    or Path(metadata["budget_path"]).resolve() != (approval.root / branch / "local-stage-budget").resolve()
                    or metadata["budget_total"] != 200 or metadata["initial_budget_used"] != 61):
                    raise RuntimeError("live-reply-activation-invalid")
                keys = keys | {"live_reply_route"}
            if (type(metadata) is not dict or set(metadata) != keys
                or metadata["contract"] != contract or type(metadata["development_run"]) is not bool
                or type(record.get("history_enabled")) is not bool): raise RuntimeError("first-life-activation-invalid")
            FirstLifeBudget(Path(metadata["budget_path"]), total=metadata["budget_total"], initial_used=metadata["initial_budget_used"]).counts()
    if qri.provider_authority == CHAT_AUTHORITY:
        metadata = record.get("chat_activation")
        if (type(metadata) is not dict or set(metadata) != {"contract", "budget_path", "budget_total", "initial_budget_used"}
            or metadata["contract"] != qri.reviewed_chat_contract or type(record.get("history_enabled")) is not bool):
            raise RuntimeError("reviewed-chat-activation-metadata-invalid")
        CharacterChatBudget(Path(metadata["budget_path"]), total=metadata["budget_total"], initial_used=metadata["initial_budget_used"]).counts()
    if qri.provider_authority in WHOLE_AUTHORITIES:
        metadata = record.get("whole_chat_activation")
        if (type(metadata) is not dict or set(metadata) != {"contract", "audit_path"}
            or metadata["contract"] != qri.reviewed_chat_contract
            or any(key in record for key in ("chat_activation", "pending_chat_activation", "life_activation", "pending_life_activation", "pending_whole_chat_activation"))
            or type(record.get("history_enabled")) is not bool
            or type(record.get("history_revision")) is not int or record["history_revision"] < 0):
            raise RuntimeError("original-whole-activation-invalid")
        validate_whole_envelope(snapshot.reviewed_definition, metadata["contract"])
        if qri.provider_authority in LIVING_AUTHORITIES:
            from dynamic_subject_agent.living_activity import validate_permission
            validate_permission(record['living_permission'])
            receipts = record['living_control_receipts']
            if (type(receipts) is not dict or any(type(key) is not str or type(value) is not dict
                or set(value) != {'digest'} or type(value['digest']) is not str
                or re.fullmatch('[0-9a-f]{64}', value['digest']) is None for key, value in receipts.items())):
                raise RuntimeError('living-control-receipts-invalid')
        if qri.provider_authority == SHARED_LIVE_AUTHORITY:
            from dynamic_subject_agent.shared_activity_live import open_shared_activity_audit
            open_shared_activity_audit(Path(metadata["audit_path"])).counts()
        elif qri.provider_authority == LIVING_LIVE_AUTHORITY:
            from dynamic_subject_agent.living_activity_live import open_living_activity_audit
            open_living_activity_audit(Path(metadata['audit_path'])).counts()
        else:
            open_original_whole_audit(Path(metadata["audit_path"])).counts()
    if record.get("host_location") is not None:
        RuntimeHostRootRef.from_dict(record["host_location"])
    return _ValidatedLocalIdentity(
        qri=qri,
        studio_location=studio_location,
        experiment_base=experiment_base,
        display_name=expected_display_name,
        freeze_basis_digest=snapshot.source_freeze_basis_digest,
        reviewed_definition=snapshot.reviewed_definition,
        knowledge_member_count=len(entries),        knowledge_entries=entries,
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


def _freeze_reviewed_identity(config, request):
    # All consent and exact-content checks precede any Studio or registry write.
    try:
        envelope = prepare_reviewed_definition(request)
    except Exception:
        return SourceIdentityFreezeResponse(SourceIdentityFreezeStatus.REJECTED,
            problem_code="reviewed-character-definition-invalid")
    if not config.state_path.exists():
        return SourceIdentityFreezeResponse(SourceIdentityFreezeStatus.UNAVAILABLE,
            problem_code="local-identity-registry-unavailable")
    try:
        state = _state_v2(json.loads(config.state_path.read_text(encoding="utf-8")))
        basis = envelope["definition_basis"]
        pid = reviewed_profile_id(basis)
        existing = next((item for item in state["identities"] if item["identity_id"] == pid), None)
        if existing is not None:
            validated = _validate_identity_record(existing, expected_parent=config.product_parent)
            if validated.reviewed_definition != envelope:
                raise RuntimeError("reviewed-character-replay-conflict")
            return _reviewed_freeze_response(state, validated.qri, envelope, True)
        source = SourceDeclaration(
            source_id=str(uuid5(NAMESPACE_URL, "reviewed-character-source:" + basis)),
            origin_kind="reviewed-fiction-derived", rights_confirmed=True,
            source_asset_refs=reviewed_source_refs(basis, envelope["runtime_asset_sha"]),
            uses_disallowed_inheritance=False)
        pc, gc = envelope["profile_content"], envelope["genesis_content"]
        profile = ParticipantProfile(pid, pc["display_name"], pc["identity_core"], source)
        premise = GenesisPremise(gc["subject_identity"], gc["canon_start"], gc["initial_relationship_premise"], source)
        target, base = SubjectStudio.open_or_create_source_identity(config.product_parent,
            freeze_basis_digest=basis, policy_kernel=PolicyKernel())
        try:
            key = "reviewed-character-" + basis
            try:
                qri = target.query_qri(publication_key=key)
                replayed = True
            except Exception as error:
                if getattr(error, "code", None) != "qri-not-found":
                    raise
                draft = target.ensure_source_identity_draft(profile=profile, premise=premise,
                    source_freeze_basis_digest=basis)
                preview = target.preview(draft.draft_id)
                policy = target.decide_policy(draft.draft_id, CapabilityManifest.reviewed_character_dormant(),
                    validity_us=300_000_000)
                freeze = FreezeDecision(
                    decision_id=str(uuid5(NAMESPACE_URL, "reviewed-character-freeze:" + basis)),
                    draft_id=draft.draft_id, expected_revision=preview.revision,
                    freeze_basis_digest=preview.freeze_basis_digest,
                    decided_by="local-user-reviewed-character-freeze",
                    rationale="Explicitly confirmed private reviewed-fiction-derived complete definition.")
                snapshot = target.seal(draft.draft_id, freeze, policy_decision_id=policy.decision_id,
                    source_freeze_basis_digest=basis, reviewed_definition=envelope)
                qri = target.publish(snapshot.snapshot_id, policy_decision_id=policy.decision_id, publication_key=key)
                replayed = False
            snapshot = target.query_snapshot(qri.genesis_snapshot_id)
            if snapshot.reviewed_definition != envelope or target.query_profile(qri.profile_id) != profile:
                raise RuntimeError("reviewed-character-sealed-content-conflict")
            location = target.location
        finally:
            target.close()
        record = dict(identity_id=pid, display_name=pc["display_name"], freeze_basis_digest=basis,
            identity_kind="reviewed-fiction-derived", definition_basis=basis, runtime_asset_sha=envelope["runtime_asset_sha"],
            experiment_base=str(base), studio_location=location.to_dict(), host_location=None,
            timeline_id=None, publication_key=qri.publication_key)
        _validate_identity_record(record, expected_parent=config.product_parent)
        state["identities"].append(record)
        _write_state(config.state_path, state)
        return _reviewed_freeze_response(state, qri, envelope, replayed)
    except Exception:
        return SourceIdentityFreezeResponse(SourceIdentityFreezeStatus.FAILED_CLOSED,
            problem_code="reviewed-character-freeze-failed-closed")


def _reviewed_freeze_response(state, qri, envelope, replayed):
    return SourceIdentityFreezeResponse(
        SourceIdentityFreezeStatus.REPLAYED if replayed else SourceIdentityFreezeStatus.CREATED,
        view=SourceIdentityFreezeView(identity_id=qri.profile_id,
            display_name=envelope["profile_content"]["display_name"],
            freeze_basis_digest=envelope["definition_basis"], publication_key=qri.publication_key,
            knowledge_member_count=0, active=state["active_identity_id"] == qri.profile_id))


def _freeze_first_life_identity(config, request):
    if type(request) is not FirstLifeIdentityRequest or request.confirmed is not True:
        return SourceIdentityFreezeResponse(SourceIdentityFreezeStatus.REJECTED, problem_code="first-life-confirmation-required")
    try:
        state = _state_v2(json.loads(config.state_path.read_text(encoding="utf-8")))
        active = next(item for item in state["identities"] if item["identity_id"] == state["active_identity_id"])
        source_identity = _validate_identity_record(active, expected_parent=config.product_parent)
        envelope = source_identity.reviewed_definition
        if envelope is None or envelope["definition_basis"] != request.definition_basis:
            raise ValueError("exact sealed definition required")
        contract = first_life_definition(envelope, request.life_scope_digest)
        pid = life_profile_id(request.definition_basis, request.life_scope_digest)
        existing = next((item for item in state["identities"] if item["identity_id"] == pid), None)
        if existing is not None:
            validated = _validate_identity_record(existing, expected_parent=config.product_parent)
            if validated.qri.first_life_contract != contract: raise RuntimeError("life replay conflict")
            return SourceIdentityFreezeResponse(SourceIdentityFreezeStatus.REPLAYED,
                view=SourceIdentityFreezeView(pid, validated.display_name, contract["identity_basis"], validated.qri.publication_key, 0,
                    state["active_identity_id"] == pid))
        source = SourceDeclaration(str(uuid5(NAMESPACE_URL, "first-life-source:" + contract["identity_basis"])),
            "reviewed-fiction-derived", True, first_life_source_refs(envelope, request.life_scope_digest), False)
        pc, gc = envelope["profile_content"], envelope["genesis_content"]
        profile = ParticipantProfile(pid, pc["display_name"], pc["identity_core"], source)
        premise = GenesisPremise(gc["subject_identity"], gc["canon_start"], gc["initial_relationship_premise"], source)
        target, base = SubjectStudio.open_or_create_source_identity(config.product_parent,
            freeze_basis_digest=contract["identity_basis"], policy_kernel=PolicyKernel())
        try:
            key = "first-life-dormant-" + contract["identity_basis"]
            try: qri = target.query_qri(publication_key=key)
            except Exception as error:
                if getattr(error, "code", None) != "qri-not-found": raise
                draft = target.ensure_source_identity_draft(profile=profile, premise=premise, source_freeze_basis_digest=contract["identity_basis"])
                preview = target.preview(draft.draft_id)
                policy = target.decide_policy(draft.draft_id, CapabilityManifest.first_life_dormant(), validity_us=300_000_000)
                freeze = FreezeDecision(str(uuid5(NAMESPACE_URL, "first-life-freeze:" + contract["identity_basis"])),
                    draft.draft_id, preview.revision, preview.freeze_basis_digest, "local-user-first-life-freeze",
                    "Create the confirmed isolated finite life branch; preserve the original identity.")
                snapshot = target.seal(draft.draft_id, freeze, policy_decision_id=policy.decision_id,
                    source_freeze_basis_digest=contract["identity_basis"], reviewed_definition=envelope, first_life_contract=contract)
                qri = target.publish(snapshot.snapshot_id, policy_decision_id=policy.decision_id, publication_key=key)
            snapshot = target.query_snapshot(qri.genesis_snapshot_id)
            if snapshot.reviewed_definition != envelope or snapshot.first_life_contract != contract or target.query_profile(pid) != profile:
                raise RuntimeError("first life sealed source conflict")
            location = target.location
        finally: target.close()
        record = dict(identity_id=pid, display_name=pc["display_name"], freeze_basis_digest=contract["identity_basis"],
            identity_kind="reviewed-fiction-derived", definition_basis=request.definition_basis, runtime_asset_sha=envelope["runtime_asset_sha"],
            life_scope_digest=request.life_scope_digest, life_identity_basis=contract["identity_basis"],
            experiment_base=str(base), studio_location=location.to_dict(), host_location=None, timeline_id=None, publication_key=qri.publication_key)
        _validate_identity_record(record, expected_parent=config.product_parent)
        state["identities"].append(record)
        _write_state(config.state_path, state)
        return SourceIdentityFreezeResponse(SourceIdentityFreezeStatus.CREATED,
            view=SourceIdentityFreezeView(pid, pc["display_name"], contract["identity_basis"], qri.publication_key, 0, False))
    except ValueError:
        return SourceIdentityFreezeResponse(SourceIdentityFreezeStatus.REJECTED, problem_code="first-life-definition-invalid")
    except Exception:
        return SourceIdentityFreezeResponse(SourceIdentityFreezeStatus.FAILED_CLOSED, problem_code="first-life-freeze-unverified")


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
            (_validate_identity_record(item, expected_parent=config.product_parent), item) for item in identities
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


def _whole_dormant_cognition(authority):
    if authority in SHARED_AUTHORITIES:
        from dynamic_subject_agent.shared_activity_cognition import SharedActivityCognition
        return SharedActivityCognition(provider_authority=authority)
    return OriginalWholeChatCognition(provider_authority=authority)


def _create_identity_host(
    identity: _ValidatedLocalIdentity,
) -> tuple[RuntimeHostRootRef, str]:
    timeline_id = str(uuid4())
    dormant = (_whole_dormant_cognition(identity.qri.provider_authority) if identity.qri.provider_authority in WHOLE_AUTHORITIES else
        FirstLifeCognition() if identity.qri.provider_authority == LIFE_AUTHORITY else
        FirstLifeDormantCognition() if identity.qri.provider_authority == LIFE_DORMANT_AUTHORITY else
        ReviewedCharacterChatCognition() if identity.qri.provider_authority == CHAT_AUTHORITY
        else ReviewedCharacterDormantCognition() if identity.reviewed_definition is not None else DormantDeepSeekCognition())
    # New identities opt into the task contract; dormant preflight still denies
    # submission. Existing bindings are read by their persisted version.
    if identity.reviewed_definition is None:
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
        cognition=(_whole_dormant_cognition(identity.qri.provider_authority) if identity.qri.provider_authority in WHOLE_AUTHORITIES else
            FirstLifeCognition() if identity.qri.provider_authority == LIFE_AUTHORITY else
            FirstLifeDormantCognition() if identity.qri.provider_authority == LIFE_DORMANT_AUTHORITY else
            ReviewedCharacterChatCognition() if identity.qri.provider_authority == CHAT_AUTHORITY
            else ReviewedCharacterDormantCognition() if identity.reviewed_definition is not None else DormantDeepSeekCognition()),
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
        validated = _validate_identity_record(selected, expected_parent=config.product_parent)
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
        if "chat_identity_revision" in state or any(
            isinstance(row.get("life_runtime_policy"), dict)
            and row["life_runtime_policy"].get("version") in (
                "first-life-followup-4", "first-life-whole-local-1", "first-life-planned-local-1",
                "first-life-whole-live-s112-1", "first-life-planned-live-s112-1",
                "first-life-whole-candidate-s114-1", "first-life-planned-candidate-s114-1") for row in identities):
            revision = state.get("chat_identity_revision")
            if type(revision) is not int or revision < 0:
                raise RuntimeError("chat-identity-revision-invalid")
            state["chat_identity_revision"] = revision + (state["active_identity_id"] != request.identity_id)
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
        validated = _validate_identity_record(active, expected_parent=config.product_parent)
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
    reviewed_definition: dict | None = None


def _registry_mutation(method):
    """Serialize complete registry read/modify/write operations, including recovery."""
    @wraps(method)
    def locked(self, *args, **kwargs):
        with self._history_lock:
            return method(self, *args, **kwargs)
    return locked


class LocalIdentityAuthority:
    """Small Interface over all persistent local identity authority behaviour."""

    def __init__(self, config: LocalProductConfig) -> None:
        if not isinstance(config, LocalProductConfig):
            raise TypeError("config must be LocalProductConfig")
        self._config = config
        self._history_lock = registry_lock(config.state_path)

    @_registry_mutation
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
        reviewed_definition = None
        if qri.provider_authority in (REVIEWED_CHARACTER_AUTHORITY, CHAT_AUTHORITY, *WHOLE_AUTHORITIES, LIFE_AUTHORITY, LIFE_DORMANT_AUTHORITY):
            studio = SubjectStudio.open(studio_location, policy_kernel=PolicyKernel())
            try:
                reviewed_definition = studio.query_snapshot(qri.genesis_snapshot_id).reviewed_definition
            finally:
                studio.close()
        return LoadedLocalIdentity(
            reviewed_definition=reviewed_definition,
            experiment_base=experiment_base,
            studio_location=studio_location,
            host_location=host_location,
            qri=qri,
            timeline_id=timeline_id,
            authoring_studio_location=authoring_studio_location,
            knowledge_entries=knowledge_entries,
            runtime_identity=runtime_identity,
        )

    @_registry_mutation
    def activate_reviewed_chat(self, *, definition_basis, scope_digest, review_request_basis,
                               budget_path, budget_total=200, initial_budget_used=61):
        state = _state_v2(json.loads(self._config.state_path.read_text(encoding="utf-8")))
        record = next(item for item in state["identities"] if item["identity_id"] == state["active_identity_id"])
        identity = _validate_identity_record(record, expected_parent=self._config.product_parent)
        if identity.reviewed_definition is None or identity.reviewed_definition["definition_basis"] != definition_basis:
            raise RuntimeError("reviewed-chat-definition-mismatch")
        contract = chat_contract(identity.reviewed_definition, scope_digest, review_request_basis)
        metadata = dict(contract=contract, budget_path=str(budget_path.resolve()), budget_total=budget_total, initial_budget_used=initial_budget_used)
        existing = record.get("chat_activation") or record.get("pending_chat_activation")
        if existing is not None and existing != metadata: raise RuntimeError("reviewed-chat-activation-conflict")
        CharacterChatBudget(budget_path, total=budget_total, initial_used=initial_budget_used, initialize=existing is None)
        if identity.qri.provider_authority == CHAT_AUTHORITY:
            if identity.qri.reviewed_chat_contract != contract: raise RuntimeError("reviewed-chat-contract-mismatch")
            return self.load_active()
        if identity.qri.provider_authority != REVIEWED_CHARACTER_AUTHORITY:
            raise RuntimeError("reviewed-chat-predecessor-invalid")
        # Persist the exact recovery target before publication/swap. A restart
        # can recover this one successor, never an arbitrary mismatched binding.
        record["pending_chat_activation"] = metadata
        record.setdefault("history_enabled", True)
        _write_state(self._config.state_path, state)
        predecessor = identity.qri
        studio = SubjectStudio.open(identity.studio_location, policy_kernel=PolicyKernel())
        try:
            key = "reviewed-character-chat-" + definition_basis + "-" + scope_digest
            try: successor = studio.query_qri(publication_key=key)
            except Exception as error:
                if getattr(error, "code", None) != "qri-not-found": raise
                snapshot = studio.query_snapshot(predecessor.genesis_snapshot_id)
                policy = studio.decide_policy(snapshot.draft_id, CapabilityManifest.reviewed_character_chat(),
                    validity_us=300_000_000, reviewed_chat_contract=contract)
                successor = studio.publish(snapshot.snapshot_id, policy_decision_id=policy.decision_id,
                    publication_key=key, predecessor_qualification_id=predecessor.qualification_id, reviewed_chat_contract=contract)
            assembly = _CognitionAssembly._reviewed_character_transition(predecessor, successor)
        finally: studio.close()
        if record.get("host_location") is None:
            location, timeline = _create_identity_host(identity)
            record["host_location"], record["timeline_id"] = location.to_dict(), timeline
            _write_state(self._config.state_path, state)
        host = RuntimeHost.open(RuntimeHostRootRef.from_dict(record["host_location"]), studio_location=identity.studio_location,
            cognition=ReviewedCharacterDormantCognition(), _cognition_assembly=assembly, _runtime_identity=identity.runtime_identity)
        try: host.open_runtime(successor, timeline_id=record["timeline_id"])
        finally: host.close()
        record["publication_key"] = successor.publication_key
        record["chat_activation"] = metadata
        record.pop("pending_chat_activation", None)
        _write_state(self._config.state_path, state)
        return self.load_active()

    @_registry_mutation
    def activate_original_whole(self, *, binding, audit_path, technical_variant="baseline", identity_id=None):
        contract = whole_contract(binding, technical_variant=technical_variant)
        if technical_variant == 'context-boundary':
            return self._activate_context_identity(contract, audit_path, identity_id)
        state, record, identity = self._active_chat_record()
        if (identity.qri.provider_authority in WHOLE_AUTHORITIES
            and contract_variant(identity.qri.reviewed_chat_contract) == "followup-legacy"):
            raise RuntimeError("original-whole-legacy-live-unavailable")
        validate_whole_envelope(identity.reviewed_definition, contract)
        metadata = dict(contract=contract, audit_path=str(audit_path.resolve()))
        existing = record.get("whole_chat_activation") or record.get("pending_whole_chat_activation")
        if existing is not None and existing != metadata:
            raise RuntimeError("original-whole-activation-conflict")
        if identity.qri.provider_authority not in (REVIEWED_CHARACTER_AUTHORITY, WHOLE_AUTHORITY):
            raise RuntimeError("original-whole-predecessor-invalid")
        if any(key in record for key in ("chat_activation", "pending_chat_activation", "life_activation", "pending_life_activation")):
            raise RuntimeError("original-whole-activation-conflict")
        open_original_whole_audit(audit_path, initialize=existing is None)
        if identity.qri.provider_authority in WHOLE_AUTHORITIES:
            if identity.qri.reviewed_chat_contract != contract:
                raise RuntimeError("original-whole-contract-mismatch")
            return self.load_active()
        record["pending_whole_chat_activation"] = metadata
        record.setdefault("history_enabled", True)
        record.setdefault("history_revision", 0)
        state.setdefault("chat_identity_revision", 0)
        if (type(record["history_enabled"]) is not bool or type(record["history_revision"]) is not int
            or record["history_revision"] < 0 or type(state["chat_identity_revision"]) is not int or state["chat_identity_revision"] < 0):
            raise RuntimeError("original-whole-history-invalid")
        _write_state(self._config.state_path, state)
        predecessor = identity.qri
        studio = SubjectStudio.open(identity.studio_location, policy_kernel=PolicyKernel())
        try:
            key = whole_publication_key(contract)
            try:
                successor = studio.query_qri(publication_key=key)
            except Exception as error:
                if getattr(error, "code", None) != "qri-not-found":
                    raise
                snapshot = studio.query_snapshot(predecessor.genesis_snapshot_id)
                policy = studio.decide_policy(snapshot.draft_id, CapabilityManifest.original_whole_chat(),
                    validity_us=300_000_000, reviewed_chat_contract=contract)
                successor = studio.publish(snapshot.snapshot_id, policy_decision_id=policy.decision_id, publication_key=key,
                    predecessor_qualification_id=predecessor.qualification_id, reviewed_chat_contract=contract)
            assembly = _CognitionAssembly._original_whole_transition(predecessor, successor)
        finally:
            studio.close()
        if record.get("host_location") is None:
            location, timeline = _create_identity_host(identity)
            record["host_location"], record["timeline_id"] = location.to_dict(), timeline
            _write_state(self._config.state_path, state)
        host = RuntimeHost.open(RuntimeHostRootRef.from_dict(record["host_location"]), studio_location=identity.studio_location,
            cognition=ReviewedCharacterDormantCognition(), _cognition_assembly=assembly, _runtime_identity=identity.runtime_identity)
        try:
            host.open_runtime(successor, timeline_id=record["timeline_id"])
        finally:
            host.close()
        record["publication_key"] = successor.publication_key
        record["whole_chat_activation"] = metadata
        record.pop("pending_whole_chat_activation", None)
        _write_state(self._config.state_path, state)
        return self.load_active()

    @_registry_mutation
    def activate_shared_activity_local(self, *, binding, identity_id):
        contract = shared_contract(binding)
        return self._activate_context_identity(contract, self._config.state_path.parent / 'shared-local-audit', identity_id)

    @_registry_mutation
    def activate_living_activity_local(self, *, binding, identity_id):
        from dynamic_subject_agent.living_activity import living_contract
        return self._activate_context_identity(living_contract(binding), self._config.state_path.parent / 'living-local-audit', identity_id)

    @_registry_mutation
    def activate_living_activity_live(self, *, grant, audit_path, identity_id):
        from dynamic_subject_agent.living_activity_live import ApprovedLivingActivityGrant, living_live_contract
        from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
        if type(grant) is not ApprovedLivingActivityGrant:
            raise ValueError('exact S142 human approval is required')
        grant.validate()
        return self._activate_context_identity(living_live_contract(APPROVED_BINDING), audit_path, identity_id)

    @_registry_mutation
    def activate_shared_activity_live(self, *, grant, audit_path, identity_id):
        from dynamic_subject_agent.shared_activity_live import ApprovedSharedActivityGrant, shared_live_contract
        from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
        if type(grant) is not ApprovedSharedActivityGrant:
            raise ValueError('typed exact shared use approval required')
        grant.validate()
        return self._activate_context_identity(shared_live_contract(APPROVED_BINDING, technical_variant=grant.technical_variant), audit_path, identity_id)

    def _activate_context_identity(self, contract, audit_path, identity_id):
        living_live = contract_variant(contract) == 'living-live'
        living = contract_variant(contract) in ('living-local', 'living-live')
        shared = contract_variant(contract) in ('shared-local', 'shared-live', 'living-local', 'living-live')
        live = contract_variant(contract) == 'shared-live'
        state = _state_v2(json.loads(self._config.state_path.read_text(encoding='utf-8')))
        if identity_id is None:
            identity_id = state['active_identity_id']
        record = next(row for row in state['identities'] if row['identity_id'] == identity_id)
        identity = _validate_identity_record(record, expected_parent=self._config.product_parent)
        validate_whole_envelope(identity.reviewed_definition, contract)
        metadata = dict(contract=contract, audit_path=str(audit_path.resolve()))
        existing = record.get('whole_chat_activation') or record.get('pending_whole_chat_activation')
        if existing is not None and existing != metadata:
            raise RuntimeError('whole-context-activation-conflict')
        if identity.qri.provider_authority == (LIVING_LIVE_AUTHORITY if living_live else LIVING_AUTHORITY if living else SHARED_LIVE_AUTHORITY if live else SHARED_AUTHORITY if shared else CONTEXT_AUTHORITY):
            if state['active_identity_id'] != identity_id:
                raise RuntimeError('whole-context-selection-required')
            return self.load_active()
        if (identity.qri.provider_authority != REVIEWED_CHARACTER_AUTHORITY or existing is None and record.get('host_location') is not None):
            raise RuntimeError('whole-context-requires-new-unserved-identity')
        if living_live:
            from dynamic_subject_agent.living_activity_live import open_living_activity_audit
            open_living_activity_audit(audit_path, initialize=existing is None)
        elif live:
            from dynamic_subject_agent.shared_activity_live import open_shared_activity_audit
            open_shared_activity_audit(audit_path, initialize=existing is None)
        else:
            open_original_whole_audit(audit_path, initialize=existing is None)
        record['pending_whole_chat_activation'] = metadata
        record.setdefault('history_enabled', True); record.setdefault('history_revision', 0)
        if living:
            record.setdefault('living_permission', dict(paused=True, sharing_enabled=False, revision=0, needs_attention=False, source_blocked=False))
            record.setdefault('living_control_receipts', {})
        state.setdefault('chat_identity_revision', 0)
        _write_state(self._config.state_path, state)
        studio = SubjectStudio.open(identity.studio_location, policy_kernel=PolicyKernel())
        try:
            key = whole_publication_key(contract)
            try:
                successor = studio.query_qri(publication_key=key)
            except Exception as error:
                if getattr(error, 'code', None) != 'qri-not-found':
                    raise
                snapshot = studio.query_snapshot(identity.qri.genesis_snapshot_id)
                policy = studio.decide_policy(snapshot.draft_id, CapabilityManifest.living_activity_live() if living_live else CapabilityManifest.living_activity_local() if living else CapabilityManifest.shared_activity_live() if live else CapabilityManifest.shared_activity_local() if shared else CapabilityManifest.original_whole_context(),
                    reviewed_chat_contract=contract, validity_us=300_000_000)
                successor = studio.publish(snapshot.snapshot_id, policy_decision_id=policy.decision_id, publication_key=key,
                    predecessor_qualification_id=identity.qri.qualification_id, reviewed_chat_contract=contract)
        finally:
            studio.close()
        assembly = _CognitionAssembly._original_whole_context_transition(identity.qri, successor)
        dormant = ReviewedCharacterDormantCognition()
        dormant.supports_whole_context = True
        dormant.supports_shared_activity = shared
        dormant.supports_living_activity = living
        if record.get('host_location') is None:
            host = RuntimeHost.create(identity.experiment_base, studio_location=identity.studio_location, cognition=dormant, _cognition_assembly=assembly)
            timeline = str(uuid4())
            try:
                host.open_runtime(identity.qri, timeline_id=timeline)
                host.open_runtime(successor, timeline_id=timeline)
                location = host.location
            finally:
                host.close()
            record['host_location'], record['timeline_id'] = location.to_dict(), timeline
            _write_state(self._config.state_path, state)
        else:
            host = RuntimeHost.open(RuntimeHostRootRef.from_dict(record['host_location']), studio_location=identity.studio_location,
                cognition=dormant, _cognition_assembly=assembly)
            try:
                host.open_runtime(successor, timeline_id=record['timeline_id'])
            finally:
                host.close()
        record['publication_key'] = successor.publication_key
        record['whole_chat_activation'] = metadata
        record.pop('pending_whole_chat_activation', None)
        state['chat_identity_revision'] += state['active_identity_id'] != identity_id
        state['active_identity_id'] = identity_id
        _write_state(self._config.state_path, state)
        return self.load_active()

    def living_permission(self, expected_identity_id):
        from dynamic_subject_agent.living_activity import validate_permission
        state, record, identity = self._active_chat_record(expected_identity_id)
        if identity.qri.provider_authority not in LIVING_AUTHORITIES:
            raise RuntimeError('independent-living-authority-required')
        return validate_permission(record['living_permission'])

    @_registry_mutation
    def change_living_permission(self, expected_identity_id, request=None, *, attention=False, revoke=False, block_source=None):
        from dynamic_subject_agent.living_activity import validate_permission
        state, record, identity = self._active_chat_record(expected_identity_id)
        if identity.qri.provider_authority not in LIVING_AUTHORITIES:
            raise RuntimeError('independent-living-authority-required')
        permission = validate_permission(record['living_permission'])
        if request is not None:
            old = record['living_control_receipts'].get(request.request_id)
            if old is not None:
                return dict(status='replayed' if old['digest'] == request.request_digest else 'conflict', permission=permission)
            if request.expected_permission_revision != permission['revision']:
                return dict(status='conflict', permission=permission)
            for key in ('paused', 'sharing_enabled'):
                value = getattr(request, key)
                if value is not None:
                    permission[key] = value
            permission['needs_attention'] = False
            record['living_control_receipts'][request.request_id] = dict(digest=request.request_digest)
        elif attention:
            permission.update(paused=True, needs_attention=True)
        elif not revoke:
            raise ValueError('explicit living control required')
        if block_source is not None:
            if type(block_source) is not bool:
                raise ValueError('typed source fence required')
            permission['source_blocked'] = block_source
        permission['revision'] += 1
        record['living_permission'] = permission
        _write_state(self._config.state_path, state)
        return dict(status='committed', permission=permission)

    def _original_whole_authorization_from_record(self, state, record, identity):
        if identity.qri.provider_authority not in WHOLE_AUTHORITIES:
            raise RuntimeError("original-whole-authority-required")
        return OriginalWholeAuthorization(identity.qri.profile_id, whole_digest(record["whole_chat_activation"]["contract"]),
            record["history_enabled"], record["history_revision"], state["chat_identity_revision"])

    def original_whole_authorization(self, expected_identity_id):
        with self._history_lock:
            return self._original_whole_authorization_from_record(*self._active_chat_record(expected_identity_id))

    def try_original_whole_authorization(self, expected_identity_id):
        if not self._history_lock.acquire(blocking=False):
            raise RuntimeError('whole-context-busy')
        try:
            return self._original_whole_authorization_from_record(*self._active_chat_record(expected_identity_id))
        finally:
            self._history_lock.release()

    def try_whole_scope_snapshot(self, expected_identity_id, expected_timeline_id):
        if not self._history_lock.acquire(blocking=False):
            raise RuntimeError('whole-scope-busy')
        try:
            state, record, identity = self._active_chat_record(expected_identity_id)
            if identity.qri.provider_authority not in WHOLE_AUTHORITIES or record.get('timeline_id') != expected_timeline_id:
                raise RuntimeError('whole-scope-changed')
            from copy import deepcopy
            return dict(envelope=deepcopy(identity.reviewed_definition), contract=deepcopy(identity.qri.reviewed_chat_contract),
                identity=identity.runtime_identity, authorization=self._original_whole_authorization_from_record(state,record,identity),
                **(dict(living_permission=deepcopy(record['living_permission'])) if identity.qri.provider_authority in LIVING_AUTHORITIES else {}))
        finally:
            self._history_lock.release()

    def whole_archive_authorization(self, expected_identity_id, expected_timeline_id):
        # Registry replacement is atomic. This read must not wait for a model's
        # publication guard; the Facade rechecks the fresh scope after reading.
        state, record, identity = self._active_chat_record(expected_identity_id)
        if identity.qri.provider_authority not in WHOLE_AUTHORITIES or record.get('timeline_id') != expected_timeline_id:
            raise RuntimeError('whole-archive-scope-changed')
        return self._original_whole_authorization_from_record(state, record, identity)

    def validate_original_context_entry(self, expected_identity_id, expected_timeline_id):
        _, record, identity = self._active_chat_record(expected_identity_id)
        if (identity.qri.provider_authority != CONTEXT_AUTHORITY
            or record.get('timeline_id') != expected_timeline_id
            or contract_variant(identity.qri.reviewed_chat_contract) != 'context-boundary'):
            raise RuntimeError('context-entry-identity-unverified')

    def validate_shared_activity_entry(self, expected_identity_id, expected_timeline_id, *, technical_variant='baseline'):
        from dynamic_subject_agent.shared_activity import SHARED_TECHNICAL_VARIANTS, shared_variant_for_contract
        if type(technical_variant) is not str or technical_variant not in SHARED_TECHNICAL_VARIANTS:
            raise ValueError('known exact shared entry variant required')
        _, record, identity = self._active_chat_record(expected_identity_id)
        if (identity.qri.provider_authority != SHARED_LIVE_AUTHORITY
            or record.get('timeline_id') != expected_timeline_id
            or contract_variant(identity.qri.reviewed_chat_contract) != 'shared-live'
            or shared_variant_for_contract(identity.qri.reviewed_chat_contract) != technical_variant):
            raise RuntimeError('shared-entry-identity-unverified')

    @contextmanager
    def original_whole_guard(self, authorization):
        if type(authorization) is not OriginalWholeAuthorization:
            raise ValueError("exact original whole authorization required")
        with self._history_lock:
            state, record, identity = self._active_chat_record()
            if state["active_identity_id"] != authorization.identity_id:
                raise ShareAuthorizationChanged("original-whole-identity-changed")
            current = self._original_whole_authorization_from_record(state, record, identity)
            if current != authorization:
                raise ShareAuthorizationChanged("original-whole-authorization-changed")
            yield

    @_registry_mutation
    def activate_first_life(self, *, definition_basis, life_scope_digest, budget_path, budget_total=200, initial_budget_used=61,
                            development_run=False, local_reply_policy=None, live_reply_witness=None):
        if type(development_run) is not bool: raise ValueError("trusted development mode required")
        state = _state_v2(json.loads(self._config.state_path.read_text(encoding="utf-8")))
        record = next(item for item in state["identities"] if item["identity_id"] == state["active_identity_id"])
        identity = _validate_identity_record(record, expected_parent=self._config.product_parent)
        expected = first_life_definition(identity.reviewed_definition, life_scope_digest)
        if definition_basis != expected["definition_basis"] or identity.qri.first_life_contract != expected:
            raise RuntimeError("first-life-definition-mismatch")
        metadata = dict(contract=expected, budget_path=str(budget_path.resolve()), budget_total=budget_total,
            initial_budget_used=initial_budget_used, development_run=development_run)
        from dynamic_subject_agent.first_life_reply_routes import LOCAL_REPLY_POLICIES, REMOTE_REPLY_POLICIES as LIVE_REPLY_POLICIES, REPLY_POLICIES
        from dynamic_subject_agent.first_life_reply_drafts import reply_scope_digest
        saved_policy = record.get("life_runtime_policy")
        if local_reply_policy is not None:
            if (local_reply_policy not in LOCAL_REPLY_POLICIES or development_run is not True
                or not isinstance(saved_policy, dict) or saved_policy.get("version") != local_reply_policy
                or saved_policy.get("digest") != reply_scope_digest(definition_basis, local_reply_policy)):
                raise ValueError("exact bound local reply activation required")
            metadata["local_reply_route"] = dict(version=local_reply_policy, digest=saved_policy["digest"])
        elif live_reply_witness is not None:
            from dynamic_subject_agent.first_life_reply_live import resolve_reply_trial as approved_trial_from_witness, approved_reply_scope_digest as live_reply_scope_digest
            approval = approved_trial_from_witness(live_reply_witness)
            _, live_policy = approval.branch(live_reply_witness["branch_id"])
            if (development_run is not True or not isinstance(saved_policy, dict)
                or saved_policy.get("version") != live_policy
                or saved_policy.get("digest") != live_reply_scope_digest(definition_basis, live_policy)):
                raise ValueError("exact approved reply trial activation required")
            metadata["live_reply_route"] = dict(version=live_policy, digest=saved_policy["digest"], approval=live_reply_witness)
        elif isinstance(saved_policy, dict) and saved_policy.get("version") in REPLY_POLICIES:
            raise ValueError("local-only or trial reply activation requires its isolated entrypoint")
        existing = record.get("life_activation") or record.get("pending_life_activation")
        if existing is not None and existing != metadata: raise RuntimeError("first-life-activation-conflict")
        # The shared 200 ledger must already exist; this new identity cannot
        # initialize another allowance. Life counters share that same writer.
        FirstLifeBudget(budget_path, total=budget_total, initial_used=initial_budget_used)
        if identity.qri.provider_authority == LIFE_AUTHORITY: return self.load_active()
        if identity.qri.provider_authority != LIFE_DORMANT_AUTHORITY: raise RuntimeError("first-life-predecessor-required")
        record["pending_life_activation"] = metadata; record.setdefault("history_enabled", True)
        _write_state(self._config.state_path, state)
        predecessor = identity.qri
        studio = SubjectStudio.open(identity.studio_location, policy_kernel=PolicyKernel())
        try:
            key = "first-life-active-" + expected["identity_basis"]
            try: successor = studio.query_qri(publication_key=key)
            except Exception as error:
                if getattr(error, "code", None) != "qri-not-found": raise
                snapshot = studio.query_snapshot(predecessor.genesis_snapshot_id)
                policy = studio.decide_policy(snapshot.draft_id, CapabilityManifest.first_life_active(), validity_us=300_000_000)
                successor = studio.publish(snapshot.snapshot_id, policy_decision_id=policy.decision_id, publication_key=key,
                    predecessor_qualification_id=predecessor.qualification_id)
            assembly = _CognitionAssembly._first_life_transition(predecessor, successor)
        finally: studio.close()
        if record.get("host_location") is None:
            location, timeline = _create_identity_host(identity)
            record["host_location"], record["timeline_id"] = location.to_dict(), timeline
            _write_state(self._config.state_path, state)
        host = RuntimeHost.open(RuntimeHostRootRef.from_dict(record["host_location"]), studio_location=identity.studio_location,
            cognition=FirstLifeDormantCognition(), _cognition_assembly=assembly, _runtime_identity=identity.runtime_identity)
        try: host.open_runtime(successor, timeline_id=record["timeline_id"])
        finally: host.close()
        record["publication_key"] = successor.publication_key
        record["life_activation"] = metadata; record.pop("pending_life_activation", None)
        _write_state(self._config.state_path, state)
        return self.load_active()

    def _active_chat_record(self, expected_identity_id=None):
        state = _state_v2(json.loads(self._config.state_path.read_text(encoding="utf-8")))
        record = next(item for item in state["identities"] if item["identity_id"] == state["active_identity_id"])
        identity = _validate_identity_record(record, expected_parent=self._config.product_parent)
        if expected_identity_id is not None and identity.qri.profile_id != expected_identity_id: raise RuntimeError("reviewed-chat-identity-changed")
        return state, record, identity

    def reviewed_character_chat_status(self, expected_identity_id=None):
        try:
            _, record, identity = self._active_chat_record(expected_identity_id)
            if identity.reviewed_definition is None: return ReviewedCharacterChatStatus("unavailable", problem_code="reviewed-character-required")
            if identity.qri.provider_authority not in (CHAT_AUTHORITY, LIFE_AUTHORITY, *WHOLE_AUTHORITIES):
                return ReviewedCharacterChatStatus("dormant", identity.display_name, record.get("history_enabled", False))
            if identity.qri.provider_authority in WHOLE_AUTHORITIES:
                opener = open_original_whole_audit
                if identity.qri.provider_authority == SHARED_LIVE_AUTHORITY:
                    from dynamic_subject_agent.shared_activity_live import open_shared_activity_audit
                    opener = open_shared_activity_audit
                elif identity.qri.provider_authority == LIVING_LIVE_AUTHORITY:
                    from dynamic_subject_agent.living_activity_live import open_living_activity_audit
                    opener = open_living_activity_audit
                total, used, remaining = opener(Path(record["whole_chat_activation"]["audit_path"])).counts()
                return ReviewedCharacterChatStatus("active", identity.display_name, record["history_enabled"], total, used, remaining)
            metadata = record["life_activation"] if identity.qri.provider_authority == LIFE_AUTHORITY else record["chat_activation"]
            if "live_reply_route" in metadata:
                from dynamic_subject_agent.first_life_reply_live import resolve_reply_trial as approved_trial_from_witness
                trial = approved_trial_from_witness(metadata["live_reply_route"]["approval"])
                total, used, remaining = trial.shared_budget().counts()
            else:
                total, used, remaining = CharacterChatBudget(Path(metadata["budget_path"]), total=metadata["budget_total"], initial_used=metadata["initial_budget_used"]).counts()
            return ReviewedCharacterChatStatus("active", identity.display_name, record["history_enabled"], total, used, remaining)
        except Exception:
            return ReviewedCharacterChatStatus("failed-closed", problem_code="reviewed-character-status-unverified")

    def character_basis(self, expected_identity_id, expected_timeline_id):
        from dynamic_subject_agent.character_basis import CharacterBasisView, build_character_basis
        try:
            _, record, identity = self._active_chat_record(expected_identity_id)
            if identity.qri.provider_authority not in WHOLE_AUTHORITIES or record.get('timeline_id') != expected_timeline_id:
                return CharacterBasisView('unavailable', 'current-whole-character-required')
            view = build_character_basis(identity.reviewed_definition, identity.qri.reviewed_chat_contract)
            # Registry publication uses atomic replacement. Recheck current
            # scope after validating the snapshot without locking a model call.
            state = _state_v2(json.loads(self._config.state_path.read_text(encoding='utf-8')))
            current = next(row for row in state['identities'] if row['identity_id'] == state['active_identity_id'])
            if (state['active_identity_id'] != expected_identity_id or current.get('timeline_id') != expected_timeline_id
                or current.get('publication_key') != record['publication_key']):
                return CharacterBasisView('unavailable', 'character-basis-scope-changed')
            return view
        except RuntimeError as error:
            if str(error) == 'reviewed-chat-identity-changed':
                return CharacterBasisView('unavailable', 'character-basis-scope-changed')
            return CharacterBasisView('failed-closed', 'character-basis-unverified')
        except Exception:
            return CharacterBasisView('failed-closed', 'character-basis-unverified')

    def character_history_preference(self, expected_identity_id=None):
        _, record, identity = self._active_chat_record(expected_identity_id)
        if identity.qri.provider_authority not in (CHAT_AUTHORITY, LIFE_AUTHORITY, *WHOLE_AUTHORITIES): raise RuntimeError("reviewed chat inactive")
        return record["history_enabled"]

    def first_life_runtime_policy(self, expected_identity_id, *, runtime_policy=None, runtime_policy_digest=None):
        """Select a reversible addon using one freshly validated registry snapshot."""
        with self._history_lock:
            state, record, identity = self._active_chat_record(expected_identity_id)
            return self._first_life_policy_from_record(state, record, identity,
                runtime_policy=runtime_policy, runtime_policy_digest=runtime_policy_digest)

    def _first_life_policy_from_record(self, state, record, identity, *, runtime_policy=None, runtime_policy_digest=None):
        """Consume this locked operation's verified record; never cache across guards."""
        from dynamic_subject_agent.first_life_relevance import RELEVANCE_VERSION, first_life_scope_digest
        from dynamic_subject_agent.first_life_grounded import GROUNDED_VERSION, first_life_scope_digest as grounded_scope_digest
        from dynamic_subject_agent.first_life_followup import FOLLOWUP_VERSION, first_life_scope_digest as followup_scope_digest
        from dynamic_subject_agent.first_life_reply_routes import LOCAL_REPLY_POLICIES, REMOTE_REPLY_POLICIES as LIVE_REPLY_POLICIES, REPLY_POLICIES
        from dynamic_subject_agent.first_life_reply_drafts import reply_scope_digest
        if identity.qri.provider_authority != LIFE_AUTHORITY:
            raise RuntimeError("first-life-active-required")
        definition = identity.reviewed_definition["definition_basis"]
        versions = {LEGACY_RUNTIME_POLICY: record["life_scope_digest"],
            RELEVANCE_VERSION: first_life_scope_digest(definition), GROUNDED_VERSION: grounded_scope_digest(definition), FOLLOWUP_VERSION: followup_scope_digest(definition)}
        versions.update({version: reply_scope_digest(definition, version) for version in LOCAL_REPLY_POLICIES})
        from dynamic_subject_agent.first_life_reply_live import approved_reply_scope_digest as live_reply_scope_digest
        versions.update({version: live_reply_scope_digest(definition, version) for version in LIVE_REPLY_POLICIES})
        saved = record.get("life_runtime_policy")
        if "life_runtime_policy" in record:
            if (type(saved) is not dict or set(saved) != {"version", "digest", "definition_basis", "life_scope_digest", "revision"}
                or saved["version"] not in versions
                or saved["digest"] != versions[saved["version"]]
                or saved["definition_basis"] != definition or saved["life_scope_digest"] != record["life_scope_digest"]
                or type(saved["revision"]) is not int or saved["revision"] < 1
                or type(record.get("history_revision")) is not int or record["history_revision"] < 0):
                raise RuntimeError("first-life-runtime-policy-invalid")
        if "chat_identity_revision" in state or any(
            isinstance(row.get("life_runtime_policy"), dict)
            and row["life_runtime_policy"].get("version") in (FOLLOWUP_VERSION, *REPLY_POLICIES) for row in state["identities"]):
            if type(state.get("chat_identity_revision")) is not int or state["chat_identity_revision"] < 0:
                raise RuntimeError("chat-identity-revision-invalid")
        if runtime_policy is None:
            if runtime_policy_digest is not None: raise ValueError("runtime policy version required")
            return LEGACY_RUNTIME_POLICY if saved is None else saved["version"]
        if ((saved is not None and saved["version"] in REPLY_POLICIES and runtime_policy != saved["version"])
            or runtime_policy in REPLY_POLICIES and (saved is None or saved["version"] != runtime_policy)):
            raise ValueError("local reply route is fixed on a separately bound dormant identity")
        digest = versions.get(runtime_policy)
        if runtime_policy not in versions or runtime_policy_digest != digest:
            raise ValueError("exact approved runtime policy digest required")
        if saved is None or saved["version"] != runtime_policy:
            record["life_runtime_policy"] = dict(version=runtime_policy, digest=digest, definition_basis=definition,
                life_scope_digest=record["life_scope_digest"], revision=1 if saved is None else saved["revision"] + 1)
            record.setdefault("history_revision", 0)
            if runtime_policy == FOLLOWUP_VERSION:
                if "chat_identity_revision" not in state:
                    state["chat_identity_revision"] = 0
                if type(state["chat_identity_revision"]) is not int or state["chat_identity_revision"] < 0:
                    raise RuntimeError("chat-identity-revision-invalid")
            _write_state(self._config.state_path, state)
        return runtime_policy

    def bind_first_life_reply_lab(self, **kwargs):
        return self._bind_first_life_reply_route(**kwargs)

    def bind_first_life_reply_trial(self, *, approval_witness, **kwargs):
        from dynamic_subject_agent.first_life_reply_live import resolve_reply_trial as approved_trial_from_witness, approved_reply_scope_digest as live_reply_scope_digest
        approval = approved_trial_from_witness(approval_witness)
        branch = approval_witness["branch_id"]
        _, policy = approval.branch(branch)
        if (self._config.state_path.resolve() != (approval.root / branch / "state.json").resolve()
            or self._config.product_parent.resolve() != (approval.root / branch / "DynamicSubjectAgent" / "m0" / "experiments").resolve()
            or kwargs["runtime_policy"] != policy
            or kwargs["runtime_policy_digest"] != live_reply_scope_digest(kwargs["definition_basis"], policy)):
            raise ValueError("exact approved reply trial branch scope required")
        return self._bind_first_life_reply_route(**kwargs, _live=True)

    @_registry_mutation
    def first_life_reply_trial_mode(self, *, seed, begin=False):
        state, record, _ = self._active_chat_record()
        if "live_reply_route" not in record.get("life_activation", {}):
            raise ValueError("approved reply trial activation required")
        if seed and record["reply_live_started"]:
            raise ValueError("live trial cannot return to synthetic seeding")
        started = record["reply_live_started"]
        if not seed and begin and not started:
            record["reply_live_started"] = True
            _write_state(self._config.state_path, state)
        return started

    @_registry_mutation
    def _bind_first_life_reply_route(self, *, definition_basis, life_scope_digest, runtime_policy, runtime_policy_digest, _live=False):
        """Bind a never-activated dormant branch to one local-only reply route.

        The existing version field makes older and remote readers reject it;
        no optional marker can be silently ignored to enable remote generation.
        """
        from dynamic_subject_agent.first_life_reply_routes import LOCAL_REPLY_POLICIES, REMOTE_REPLY_POLICIES as LIVE_REPLY_POLICIES, REPLY_POLICIES
        from dynamic_subject_agent.first_life_reply_drafts import reply_scope_digest
        from dynamic_subject_agent.first_life_reply_live import approved_reply_scope_digest as live_reply_scope_digest
        allowed, digest_fn = (LIVE_REPLY_POLICIES, live_reply_scope_digest) if _live else (LOCAL_REPLY_POLICIES, reply_scope_digest)
        if runtime_policy not in allowed or runtime_policy_digest != digest_fn(definition_basis, runtime_policy):
            raise ValueError("exact isolated reply route required")
        state, record, identity = self._active_chat_record()
        if (identity.reviewed_definition is None or identity.reviewed_definition["definition_basis"] != definition_basis
            or record.get("life_scope_digest") != life_scope_digest):
            raise ValueError("local reply definition mismatch")
        saved = record.get("life_runtime_policy")
        if saved is not None:
            if (identity.qri.provider_authority == LIFE_AUTHORITY
                and self.first_life_runtime_policy(identity.qri.profile_id) == runtime_policy
                and saved["digest"] == runtime_policy_digest):
                return
            # A crash may leave the local binding before the existing activation
            # protocol completes. Validate the exact saved binding for replay.
            expected = dict(version=runtime_policy, digest=runtime_policy_digest, definition_basis=definition_basis,
                life_scope_digest=record.get("life_scope_digest"), revision=1)
            if (identity.qri.provider_authority == LIFE_DORMANT_AUTHORITY and saved == expected
                and type(record.get("history_revision")) is int and record["history_revision"] >= 0
                and type(state.get("chat_identity_revision")) is int and state["chat_identity_revision"] >= 0):
                return
            raise ValueError("reply lab cannot replace an existing route")
        if ("life_runtime_policy" in record or identity.qri.provider_authority != LIFE_DORMANT_AUTHORITY
            or "life_activation" in record or "pending_life_activation" in record):
            raise ValueError("reply lab requires a new dormant life identity")
        if "chat_identity_revision" in state and (type(state["chat_identity_revision"]) is not int or state["chat_identity_revision"] < 0):
            raise RuntimeError("chat-identity-revision-invalid")
        if (type(record.get("history_enabled", True)) is not bool
            or type(record.get("history_revision", 0)) is not int or record.get("history_revision", 0) < 0):
            raise RuntimeError("history-policy-invalid")
        record["life_runtime_policy"] = dict(version=runtime_policy, digest=runtime_policy_digest,
            definition_basis=definition_basis, life_scope_digest=record["life_scope_digest"], revision=1)
        if _live:
            record["reply_live_started"] = False
        record.setdefault("history_enabled", True)
        record.setdefault("history_revision", 0)
        state.setdefault("chat_identity_revision", 0)
        _write_state(self._config.state_path, state)

    def require_remote_first_life(self):
        from dynamic_subject_agent.first_life_reply_routes import LOCAL_REPLY_POLICIES, REMOTE_REPLY_POLICIES as LIVE_REPLY_POLICIES, REPLY_POLICIES
        _, record, _ = self._active_chat_record()
        saved = record.get("life_runtime_policy")
        if type(saved) is dict and saved.get("version") in REPLY_POLICIES:
            raise ValueError("local-only or S112 reply identity requires its isolated provider entrypoint")

    def _first_life_share_authorization_from_record(self, state, record, identity):
        policy = self._first_life_policy_from_record(state, record, identity)
        saved = record.get("life_runtime_policy")
        if saved is None or policy == LEGACY_RUNTIME_POLICY:
            raise RuntimeError("first-life-share-authorization-unavailable")
        return ShareAuthorization(identity.qri.profile_id, policy, saved["digest"], saved["revision"],
            record["history_revision"], record["history_enabled"])

    def first_life_share_authorization(self, expected_identity_id):
        with self._history_lock:
            snapshot = self._active_chat_record(expected_identity_id)
            return self._first_life_share_authorization_from_record(*snapshot)

    @contextmanager
    def first_life_share_guard(self, authorization):
        """Fresh authorization at each send/commit boundary, serialized with edits.

        Nested policy/token checks reuse only this call's fully verified record.
        The next guard repeats the full validation, including after generation.
        """
        with self._history_lock:
            if type(authorization) is not ShareAuthorization:
                raise ValueError("invalid share authorization")
            snapshot = self._active_chat_record(authorization.identity_id)
            if "life_runtime_policy" not in snapshot[1]:
                raise RuntimeError("first-life-share-authorization-missing")
            if self._first_life_policy_from_record(*snapshot) != authorization.runtime_policy:
                raise ShareAuthorizationChanged("first-life-share-authorization-changed")
            current = self._first_life_share_authorization_from_record(*snapshot)
            if current != authorization:
                raise ShareAuthorizationChanged("first-life-share-authorization-changed")
            yield

    def first_life_chat_authorization(self, expected_identity_id):
        from dataclasses import asdict
        from dynamic_subject_agent.first_life_authorization import ChatAuthorization
        with self._history_lock:
            state, record, identity = self._active_chat_record(expected_identity_id)
            token = self._first_life_share_authorization_from_record(state, record, identity)
            return ChatAuthorization(**asdict(token), identity_revision=state["chat_identity_revision"])

    @contextmanager
    def first_life_chat_guard(self, authorization):
        from dataclasses import asdict
        from dynamic_subject_agent.first_life_authorization import ChatAuthorization
        if type(authorization) is not ChatAuthorization:
            raise ValueError("exact chat authorization required")
        with self._history_lock:
            state = _state_v2(json.loads(self._config.state_path.read_text(encoding="utf-8")))
            revision = state.get("chat_identity_revision")
            if type(revision) is not int or revision < 0:
                raise RuntimeError("chat-identity-revision-invalid")
            if (state["active_identity_id"] != authorization.identity_id
                or revision != authorization.identity_revision):
                raise ShareAuthorizationChanged("first-life-chat-identity-changed")
            value = asdict(authorization)
            value.pop("identity_revision")
            with self.first_life_share_guard(ShareAuthorization(**value)):
                yield

    def set_reviewed_character_history(self, enabled, expected_identity_id=None):
        if type(enabled) is not bool: return ReviewedCharacterChatStatus("unavailable", problem_code="typed-history-preference-required")
        try:
            with self._history_lock:
                state, record, identity = self._active_chat_record(expected_identity_id)
                if identity.qri.provider_authority not in (CHAT_AUTHORITY, LIFE_AUTHORITY, *WHOLE_AUTHORITIES): raise RuntimeError("reviewed chat inactive")
                revision = record["history_revision"] if "life_runtime_policy" in record else record.get("history_revision", 0)
                if type(revision) is not int or revision < 0: raise RuntimeError("history revision invalid")
                record["history_revision"] = revision + (record["history_enabled"] != enabled)
                record["history_enabled"] = enabled
                _write_state(self._config.state_path, state)
        except Exception:
            return ReviewedCharacterChatStatus("failed-closed", problem_code="reviewed-character-history-unverified")
        return self.reviewed_character_chat_status(expected_identity_id)

    @_registry_mutation
    def freeze(
        self,
        request: object,
    ) -> SourceIdentityFreezeResponse:
        if type(request) is FirstLifeIdentityRequest:
            return _freeze_first_life_identity(self._config, request)
        if type(request) is ReviewedCharacterFreezeRequest:
            return _freeze_reviewed_identity(self._config, request)
        return _freeze_source_identity(
            self._config,
            source_studio_location=_authoring_studio_location(self._config),
            request=request,
        )

    def list(self) -> LocalIdentityListResponse:
        return _list_local_identities(self._config)

    @_registry_mutation
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
