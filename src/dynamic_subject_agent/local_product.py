"""Production creation and opening seam for one persistent local product."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from dynamic_subject_agent.application import ApplicationFacade
from dynamic_subject_agent.bootstrap import compose_application
from dynamic_subject_agent.cognition import CredentialRef
from dynamic_subject_agent.composite import ControlledCompositeCognition
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


def _load_or_create_authority(
    config: LocalProductConfig,
) -> tuple[Path, StudioRootRef, RuntimeHostRootRef, QualifiedRuntimeInput, str]:
    if config.state_path.exists():
        saved = json.loads(config.state_path.read_text(encoding="utf-8"))
        if saved.get("schema_version") != _STATE_SCHEMA_VERSION:
            raise RuntimeError("unsupported-local-product-state")
        experiment_base = Path(str(saved["experiment_base"]))
        studio_location = StudioRootRef.from_dict(saved["studio_location"])
        host_location = RuntimeHostRootRef.from_dict(saved["host_location"])
        timeline_id = str(saved["timeline_id"])
        studio = SubjectStudio.open(studio_location, policy_kernel=PolicyKernel())
        try:
            qri = studio.query_qri(publication_key=str(saved["publication_key"]))
        finally:
            studio.close()
        return experiment_base, studio_location, host_location, qri, timeline_id

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
    )


def open_local_product(
    config: LocalProductConfig,
    *,
    cognition: CognitionEngine,
) -> OpenedLocalProduct:
    """Open the one persistent product through its production composition root."""

    if not isinstance(config, LocalProductConfig):
        raise TypeError("config must be LocalProductConfig")
    if not isinstance(cognition, CognitionEngine):
        raise TypeError("cognition must satisfy the CognitionEngine Interface")
    experiment_base, studio_location, host_location, qri, timeline_id = (
        _load_or_create_authority(config)
    )
    composition = compose_application(
        m0_root=experiment_base,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
        _cognition=cognition,
        relationship_mode=config.relationship_mode,
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
        participant_goal_gateway=participant_goal_gateway,
        situated_gateway=situated_gateway,
        medium_gateway=medium_gateway,
    )
    return open_local_product(config, cognition=cognition)


__all__ = [
    "LocalProductConfig",
    "LocalProductIdentity",
    "OpenedLocalProduct",
    "create_local_product_identity",
    "open_deepseek_local_product",
    "open_local_product",
]
