"""Production composition root for one persistent local product."""

from __future__ import annotations

from pathlib import Path

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
    DeepSeekMediumProvider,
    DeepSeekParticipantGoalProvider,
    DeepSeekRelationshipProvider,
    DeepSeekSituatedProvider,
    DeepSeekSourceCharacterProvider,
    DeepSeekUrlLibTransport,
)
from dynamic_subject_agent.local_identity_authority import (
    LoadedLocalIdentity,
    LocalIdentityAuthority,
    LocalProductConfig,
    LocalProductIdentity,
    create_local_product_identity,
)
from dynamic_subject_agent.medium_cognition import MediumProviderAdapter
from dynamic_subject_agent.model_gateway import (
    ModelGateway,
    ProviderCapabilities,
    StructuredOutputMode,
)
from dynamic_subject_agent.participant_goal_cognition import (
    ParticipantGoalProviderAdapter,
)
from dynamic_subject_agent.runtime import CognitionEngine
from dynamic_subject_agent.situated_cognition import SituatedProviderAdapter
from dynamic_subject_agent.source_character_authoring import (
    SourceCharacterProviderAdapter,
    TextSourceCharacterAuthoring,
)
from dynamic_subject_agent.studio import QualifiedRuntimeInput

DOGFOOD_BUILD_ID = "dogfood-s34"


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

    def __enter__(self) -> "OpenedLocalProduct":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._composition.close()  # type: ignore[attr-defined]


def open_local_product(
    config: LocalProductConfig,
    *,
    cognition: CognitionEngine,
    source_authoring: TextSourceCharacterAuthoring | None = None,
) -> OpenedLocalProduct:
    """Open the selected identity through the only production composition root."""

    if not isinstance(config, LocalProductConfig):
        raise TypeError("config must be LocalProductConfig")
    if not isinstance(cognition, CognitionEngine):
        raise TypeError("cognition must satisfy the CognitionEngine Interface")
    authority = LocalIdentityAuthority(config)
    loaded = authority.load_active()
    return _open_loaded_local_product(
        config,
        authority=authority,
        loaded=loaded,
        cognition=cognition,
        source_authoring=source_authoring,
    )


def _open_loaded_local_product(
    config: LocalProductConfig,
    *,
    authority: LocalIdentityAuthority,
    loaded: LoadedLocalIdentity,
    cognition: CognitionEngine,
    source_authoring: TextSourceCharacterAuthoring | None,
) -> OpenedLocalProduct:
    composition = compose_application(
        m0_root=loaded.experiment_base,
        studio_location=loaded.studio_location,
        qualified_runtime_input=loaded.qri,
        timeline_id=loaded.timeline_id,
        host_location=loaded.host_location,
        _cognition=cognition,
        relationship_mode=config.relationship_mode,
        _source_authoring=source_authoring,
        _source_studio_location=loaded.authoring_studio_location,
        _source_identity_freezer=authority.freeze,
        _local_identity_lister=authority.list,
        _local_identity_selector=lambda request: authority.select(
            request,
            current=loaded,
        ),
        _knowledge_entries=loaded.knowledge_entries,
        _runtime_identity=loaded.runtime_identity,
    )
    return OpenedLocalProduct(
        composition=composition,
        qualified_runtime_input=loaded.qri,
        timeline_id=loaded.timeline_id,
    )


def open_deepseek_local_product(
    config: LocalProductConfig,
    *,
    api_key: str,
) -> OpenedLocalProduct:
    """Open the selected identity with the DeepSeek cognition Adapter."""

    key = api_key.strip() if isinstance(api_key, str) else ""
    if not key:
        raise RuntimeError("DeepSeek API key is required")
    authority = LocalIdentityAuthority(config)
    loaded = authority.load_active()

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
        knowledge_entries=loaded.knowledge_entries,
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
        authority=authority,
        loaded=loaded,
        cognition=cognition,
        source_authoring=source_authoring,
    )


__all__ = [
    "DOGFOOD_BUILD_ID",
    "LocalProductConfig",
    "LocalProductIdentity",
    "OpenedLocalProduct",
    "create_local_product_identity",
    "open_deepseek_local_product",
    "open_local_product",
]
