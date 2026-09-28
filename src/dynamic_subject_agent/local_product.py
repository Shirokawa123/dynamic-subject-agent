"""Production composition root for one persistent local product."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from uuid import uuid4

from dynamic_subject_agent.character_dialogue import CharacterDialogueSession, plan_digest, plan_payload, grounded_plan_digest
from dynamic_subject_agent.conversation_basis import ConversationBasisPreview, S59_DIGEST
from dynamic_subject_agent.character_reply_candidate import CharacterReplyProducer
from dynamic_subject_agent.character_context_trial import CharacterContextTrial, build_trial_plan, save_trial_plan
from dynamic_subject_agent.character_evidence_model import CharacterEvidenceModel
from dynamic_subject_agent.evidence_extraction import EvidenceExtractionLab, extraction_plan_digest, extraction_plan_payload

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

DOGFOOD_BUILD_ID = "dogfood-s51"


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
    _character_dialogue: CharacterDialogueSession | None = None,
    _basis_preview: ConversationBasisPreview | None = None,
    _character_model: CharacterEvidenceModel | None = None,
    _character_reply_lab: CharacterReplyProducer | None = None,
    _evidence_extraction: EvidenceExtractionLab | None = None,
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
        character_dialogue=_character_dialogue,
        basis_preview=_basis_preview,
        character_model=_character_model,
        character_reply_lab=_character_reply_lab,
        evidence_extraction=_evidence_extraction,
    )


def _open_loaded_local_product(
    config: LocalProductConfig,
    *,
    authority: LocalIdentityAuthority,
    loaded: LoadedLocalIdentity,
    cognition: CognitionEngine,
    source_authoring: TextSourceCharacterAuthoring | None,
    character_dialogue: CharacterDialogueSession | None = None,
    basis_preview: ConversationBasisPreview | None = None,
    character_model: CharacterEvidenceModel | None = None,
    character_reply_lab: CharacterReplyProducer | None = None,
    evidence_extraction: EvidenceExtractionLab | None = None,
    first_life_budget=None, first_life_clock=None, first_life_day=None, first_life_development=False,
) -> OpenedLocalProduct:
    if loaded.reviewed_definition is not None:
        from dynamic_subject_agent.reviewed_character_cognition import ReviewedCharacterDormantCognition
        from dynamic_subject_agent.reviewed_character_chat import CHAT_AUTHORITY
        from dynamic_subject_agent.reviewed_character_chat_cognition import ReviewedCharacterChatCognition
        from dynamic_subject_agent.first_life import LIFE_AUTHORITY, LIFE_DORMANT_AUTHORITY
        from dynamic_subject_agent.first_life_cognition import FirstLifeCognition, FirstLifeDormantCognition
        if loaded.qri.provider_authority == LIFE_AUTHORITY:
            if type(cognition) is not FirstLifeCognition: cognition = FirstLifeCognition()
        elif loaded.qri.provider_authority == LIFE_DORMANT_AUTHORITY:
            cognition = FirstLifeDormantCognition()
        elif loaded.qri.provider_authority == CHAT_AUTHORITY:
            if type(cognition) is not ReviewedCharacterChatCognition:
                cognition = ReviewedCharacterChatCognition()
        else:
            cognition = ReviewedCharacterDormantCognition()
        if any(value is not None for value in (source_authoring, character_dialogue, basis_preview, character_model, character_reply_lab, evidence_extraction)):
            raise RuntimeError("reviewed-character-chat-unavailable")
    composition = compose_application(
        m0_root=loaded.experiment_base,
        studio_location=loaded.studio_location,
        qualified_runtime_input=loaded.qri,
        timeline_id=loaded.timeline_id,
        host_location=loaded.host_location,
        _cognition=cognition,
        relationship_mode=config.relationship_mode,
        _source_authoring=source_authoring,
        _character_dialogue=character_dialogue,
        _basis_preview=basis_preview,
        _character_model=character_model,
        _character_reply_lab=character_reply_lab,
        _evidence_extraction=evidence_extraction,
        _source_studio_location=loaded.authoring_studio_location,
        _source_identity_freezer=authority.freeze,
        _first_life_freezer=authority.freeze,
        _first_life_budget=first_life_budget,
        _first_life_clock=first_life_clock,
        _first_life_day=first_life_day,
        _first_life_development=first_life_development,
        _reviewed_chat_status=lambda: authority.reviewed_character_chat_status(loaded.qri.profile_id),
        _reviewed_history_setter=lambda enabled: authority.set_reviewed_character_history(enabled, loaded.qri.profile_id),
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
    if loaded.reviewed_definition is not None:
        raise RuntimeError("reviewed-character-legacy-provider-denied")

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
    from dynamic_subject_agent.subject_task_cognition import SubjectTaskCognition
    from dynamic_subject_agent.subject_task_provider import DeepSeekSubjectTaskAdapter
    cognition = SubjectTaskCognition(cognition, ModelGateway(DeepSeekSubjectTaskAdapter(**provider_kwargs)))
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


_REMOTE_LAB_LOCK = Lock()
_REMOTE_LAB_OPENED = False


def open_character_dialogue_lab(parent: Path, *, approved_plan: str | None = None, basis_workspace: Path | None = None, grounded: bool = False) -> OpenedLocalProduct:
    """Create a fresh lab only. Approval digest is an explicit operator assertion.

    No existing identity path is accepted; no credential discovery occurs offline.
    One remote lab per process prevents resetting the process's attempt budget.
    """
    global _REMOTE_LAB_OPENED
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    from dynamic_subject_agent.character_dialogue_provider import (
        OfflineCharacterDialogueAdapter, DeepSeekCharacterDialogueAdapter,
    )
    if not isinstance(parent, Path) or not parent.is_absolute():
        raise ValueError("absolute lab parent required")
    if type(grounded) is not bool or (grounded and basis_workspace is None):
        raise ValueError("grounded chat requires an explicit basis workspace")
    expected_plan = grounded_plan_digest() if grounded else plan_digest()
    if approved_plan is not None and approved_plan != expected_plan:
        raise ValueError("current plan approval required")
    basis_preview = None
    if basis_workspace is not None:
        if approved_plan is not None and not grounded:
            raise ValueError("basis preview is offline only")
        if not isinstance(basis_workspace, Path) or not basis_workspace.is_absolute():
            raise ValueError("absolute basis workspace required")
        basis_preview = ConversationBasisPreview(
            basis_workspace / ".local_indexes/eromanga-sensei/s59/conversation-basis-v0.2.json",
            basis_workspace / ".local_sources/eromanga-sensei", expected_digest=S59_DIGEST)
    adapter = OfflineCharacterDialogueAdapter()
    if approved_plan is not None:
        from dynamic_subject_agent.deepseek import DEEPSEEK_ENDPOINT
        if (DEEPSEEK_MODEL != plan_payload()["model"]
                or DEEPSEEK_ENDPOINT != plan_payload()["endpoint"]):
            raise ValueError("provider changed; new plan required")
        with _REMOTE_LAB_LOCK:
            if _REMOTE_LAB_OPENED:
                raise ValueError("one remote lab per process")
            _REMOTE_LAB_OPENED = True

        adapter = DeepSeekCharacterDialogueAdapter(
            transport=DeepSeekUrlLibTransport(credential_resolver=_WindowsLabResolver()),
            credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
                                                   key_id=DEEPSEEK_CREDENTIAL_KEY_ID))
    root = parent / ("dialogue-lab-" + uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    config = LocalProductConfig(product_parent=root / "DynamicSubjectAgent" / "m0" / "experiments", state_path=root / "state.json",
                                relationship_mode="off")
    return open_local_product(config, cognition=DormantDeepSeekCognition(),
                              _basis_preview=basis_preview, _character_dialogue=CharacterDialogueSession(ModelGateway(adapter), basis=basis_preview if grounded else None))


def open_character_model_preview(parent: Path, *, draft_path: Path, source_root: Path,
                                 reviewed_digest: str, reply_lab: CharacterReplyProducer | None = None) -> OpenedLocalProduct:
    """Read-only authoring preview in a new isolated product; no provider assembly."""
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    if not isinstance(parent, Path) or not parent.is_absolute():
        raise ValueError("absolute preview parent required")
    model = CharacterEvidenceModel(draft_path, source_root, expected_digest=reviewed_digest)
    root = parent / ("character-model-" + uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    config = LocalProductConfig(root / "DynamicSubjectAgent/m0/experiments", root / "state.json", "off")
    return open_local_product(config, cognition=DormantDeepSeekCognition(), _character_model=model, _character_reply_lab=reply_lab)


def open_character_communication_plan_lab(parent: Path, *, draft_path: Path, source_root: Path,
                                          reviewed_digest: str, plan_gateway: ModelGateway,
                                          expression_gateway: ModelGateway) -> OpenedLocalProduct:
    """Explicit local substitute prototype; no remote composition or state adoption."""
    from dynamic_subject_agent.character_communication_plan import CharacterCommunicationPlanLab
    lab = CharacterCommunicationPlanLab(plan_gateway, expression_gateway)
    return open_character_model_preview(parent, draft_path=draft_path, source_root=source_root,
                                        reviewed_digest=reviewed_digest, reply_lab=lab)


def open_character_personality_lab(parent: Path, *, draft_path: Path, source_root: Path, reviewed_digest: str,
                                   sidecar_path: Path, personality_digest: str, plan_gateway: ModelGateway | None = None,
                                   expression_gateway: ModelGateway | None = None) -> OpenedLocalProduct:
    """Read-only candidate interpretations; preview default, explicit local substitutes only."""
    from dynamic_subject_agent.character_personality import CharacterPersonalityLab
    model = CharacterEvidenceModel(draft_path, source_root, expected_digest=reviewed_digest)
    lab = CharacterPersonalityLab(model=model, sidecar_path=sidecar_path, expected_digest=personality_digest,
                                 plan_gateway=plan_gateway, expression_gateway=expression_gateway)
    return open_character_model_preview(parent, draft_path=draft_path, source_root=source_root,
                                        reviewed_digest=reviewed_digest, reply_lab=lab)


def prepare_character_personality_trial(parent: Path, *, draft_path: Path, source_root: Path, reviewed_digest: str,
                                        subject_id: str, anchor_id: str, cases: dict, sidecar_path: Path,
                                        personality_digest: str, max_knowledge_chars: int = 20000, planning_effort: str = "high"):
    from dynamic_subject_agent.character_communication_trial import build_communication_trial_plan, save_communication_trial_plan
    from dynamic_subject_agent.character_communication_trial_provider import DeepSeekPersonalityTrialAdapter, communication_protocol
    with open_character_personality_lab(parent / "previews", draft_path=draft_path, source_root=source_root, reviewed_digest=reviewed_digest,
        sidecar_path=sidecar_path, personality_digest=personality_digest) as product:
        plan = build_communication_trial_plan(product.application.preview_character_reply,
            reviewed_digest=reviewed_digest, subject_id=subject_id, anchor_id=anchor_id, cases=cases,
            max_knowledge_chars=max_knowledge_chars, protocol=communication_protocol("thinking-high", planning_effort), expression_profile="thinking-high",
            planning_wire=lambda projection: DeepSeekPersonalityTrialAdapter.planning_wire(projection, planning_effort=planning_effort),
            planning_effort=planning_effort,
            personality_binding=dict(version="character-personality-draft-1", base_reviewed_digest=reviewed_digest,
                subject_id=subject_id, anchor_id=anchor_id, sidecar_digest=personality_digest))
    save_communication_trial_plan(parent, plan)
    return plan


def open_character_personality_trial(parent: Path, *, draft_path: Path, source_root: Path, reviewed_digest: str,
                                     subject_id: str, anchor_id: str, cases: dict, sidecar_path: Path, personality_digest: str,
                                     max_knowledge_chars: int = 20000, approved_plan: str | None = None, planning_effort: str = "high", _transport=None) -> OpenedLocalProduct:
    from dynamic_subject_agent.character_personality import CharacterPersonalityLab
    from dynamic_subject_agent.character_communication_trial import CharacterCommunicationTrial
    from dynamic_subject_agent.character_communication_trial_provider import DeepSeekPersonalityTrialAdapter
    plan = prepare_character_personality_trial(parent, draft_path=draft_path, source_root=source_root, reviewed_digest=reviewed_digest,
        subject_id=subject_id, anchor_id=anchor_id, cases=cases, sidecar_path=sidecar_path, personality_digest=personality_digest,
        max_knowledge_chars=max_knowledge_chars, planning_effort=planning_effort)
    if approved_plan is not None and approved_plan != plan.digest: raise ValueError("current personality trial approval required")
    gateway = None
    if approved_plan is not None and not (parent / plan.digest).exists():
        transport = _transport if _transport is not None else DeepSeekUrlLibTransport(credential_resolver=_WindowsLabResolver())
        gateway = ModelGateway(DeepSeekPersonalityTrialAdapter(plan, sidecar_path=sidecar_path, run_root=parent / plan.digest,
            transport=transport, credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID)))
    reader = CharacterPersonalityLab(model=CharacterEvidenceModel(draft_path, source_root, expected_digest=reviewed_digest),
        sidecar_path=sidecar_path, expected_digest=personality_digest)
    trial = CharacterCommunicationTrial(plan, root=parent, gateway=gateway, expression_wire=DeepSeekPersonalityTrialAdapter.expression_wire,
        approved_plan=approved_plan, personality_preview=reader)
    return open_character_model_preview(parent / "products", draft_path=draft_path, source_root=source_root,
                                        reviewed_digest=reviewed_digest, reply_lab=trial)


def prepare_character_communication_trial(parent: Path, *, draft_path: Path, source_root: Path,
                                           reviewed_digest: str, subject_id: str, anchor_id: str, cases: dict,
                                           max_knowledge_chars: int = 20000, expression_profile: str = "standard", planning_effort: str = "high"):
    from dynamic_subject_agent.character_communication_trial import build_communication_trial_plan, save_communication_trial_plan
    from dynamic_subject_agent.character_communication_trial_provider import DeepSeekCommunicationTrialAdapter, communication_protocol
    with open_character_model_preview(parent / "previews", draft_path=draft_path, source_root=source_root,
                                      reviewed_digest=reviewed_digest) as product:
        plan = build_communication_trial_plan(product.application.preview_character_reply,
            reviewed_digest=reviewed_digest, subject_id=subject_id, anchor_id=anchor_id, cases=cases,
            max_knowledge_chars=max_knowledge_chars, protocol=communication_protocol(expression_profile, planning_effort),
            planning_wire=lambda projection: DeepSeekCommunicationTrialAdapter.planning_wire(projection, planning_effort=planning_effort),
            expression_profile=expression_profile, planning_effort=planning_effort)
    save_communication_trial_plan(parent, plan)
    return plan


def open_character_communication_trial(parent: Path, *, draft_path: Path, source_root: Path,
                                        reviewed_digest: str, subject_id: str, anchor_id: str, cases: dict,
                                        max_knowledge_chars: int = 20000, approved_plan: str | None = None,
                                        expression_profile: str = "standard", planning_effort: str = "high", _transport=None) -> OpenedLocalProduct:
    from dynamic_subject_agent.character_communication_trial import CharacterCommunicationTrial
    from dynamic_subject_agent.character_communication_trial_provider import DeepSeekCommunicationTrialAdapter
    plan = prepare_character_communication_trial(parent, draft_path=draft_path, source_root=source_root,
        reviewed_digest=reviewed_digest, subject_id=subject_id, anchor_id=anchor_id, cases=cases, max_knowledge_chars=max_knowledge_chars,
        expression_profile=expression_profile, planning_effort=planning_effort)
    if approved_plan is not None and approved_plan != plan.digest:
        raise ValueError("current communication approval required")
    gateway = None
    if approved_plan is not None and not (parent / plan.digest).exists():
        transport = _transport if _transport is not None else DeepSeekUrlLibTransport(credential_resolver=_WindowsLabResolver())
        gateway = ModelGateway(DeepSeekCommunicationTrialAdapter(plan, run_root=parent / plan.digest,
            transport=transport, credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
                                                                        key_id=DEEPSEEK_CREDENTIAL_KEY_ID)))
    trial = CharacterCommunicationTrial(plan, root=parent, gateway=gateway,
        expression_wire=lambda projection: DeepSeekCommunicationTrialAdapter.expression_wire(projection, expression_profile=expression_profile),
        approved_plan=approved_plan)
    return open_character_model_preview(parent / "products", draft_path=draft_path, source_root=source_root,
                                        reviewed_digest=reviewed_digest, reply_lab=trial)


def prepare_character_expression_thinking_trial(parent: Path, *, parent_trial_root: Path, parent_plan_digest: str,
                                                draft_path: Path, source_root: Path):
    from dynamic_subject_agent.character_expression_trial import read_parent_plan, validated_parent_expressions, build_expression_trial_plan
    from dynamic_subject_agent.character_communication_trial import save_communication_trial_plan
    from dynamic_subject_agent.character_communication_trial_provider import DeepSeekCommunicationTrialAdapter
    from dynamic_subject_agent.character_expression_trial_provider import DeepSeekExpressionThinkingAdapter, expression_thinking_protocol
    original, parent_file_digest = read_parent_plan(parent_trial_root, parent_plan_digest)
    payload = original.payload
    current = prepare_character_communication_trial(parent / "source-preparation", draft_path=draft_path, source_root=source_root,
        reviewed_digest=payload["reviewed_digest"], subject_id=payload["subject_id"], anchor_id=payload["anchor_id"],
        cases=dict(version="character-communication-plan-cases-1", cases=payload["cases"]), max_knowledge_chars=payload["max_knowledge_chars"])
    if current.serialized != original.serialized: raise ValueError("current source does not match parent")
    audited_rows, fingerprints = validated_parent_expressions(parent_trial_root, original, DeepSeekCommunicationTrialAdapter.expression_wire)
    plan = build_expression_trial_plan(parent=original, parent_file_digest=parent_file_digest, audited_rows=audited_rows,
        audit_fingerprints=fingerprints, protocol=expression_thinking_protocol(), expression_wire=DeepSeekExpressionThinkingAdapter.expression_wire)
    save_communication_trial_plan(parent, plan)
    return plan


def open_character_expression_thinking_trial(parent: Path, *, parent_trial_root: Path, parent_plan_digest: str,
                                             draft_path: Path, source_root: Path, approved_plan: str | None = None,
                                             _transport=None) -> OpenedLocalProduct:
    from dynamic_subject_agent.character_expression_trial import CharacterExpressionThinkingTrial
    from dynamic_subject_agent.character_expression_trial_provider import DeepSeekExpressionThinkingAdapter
    plan = prepare_character_expression_thinking_trial(parent, parent_trial_root=parent_trial_root, parent_plan_digest=parent_plan_digest,
        draft_path=draft_path, source_root=source_root)
    if approved_plan is not None and approved_plan != plan.digest: raise ValueError("current expression approval required")
    gateway = None
    if approved_plan is not None and not (parent / plan.digest).exists():
        transport = _transport if _transport is not None else DeepSeekUrlLibTransport(credential_resolver=_WindowsLabResolver())
        gateway = ModelGateway(DeepSeekExpressionThinkingAdapter(plan, run_root=parent / plan.digest, parent_root=parent_trial_root,
            transport=transport, credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID)))
    trial = CharacterExpressionThinkingTrial(plan, root=parent, parent_root=parent_trial_root, gateway=gateway, approved_plan=approved_plan)
    return open_character_model_preview(parent / "products", draft_path=draft_path, source_root=source_root,
        reviewed_digest=plan.payload["reviewed_digest"], reply_lab=trial)


def prepare_character_context_trial(parent: Path, *, draft_path: Path, source_root: Path,
                                    reviewed_digest: str, subject_id: str, anchor_id: str,
                                    cases: dict, max_knowledge_chars: int = 20000):
    """Freeze all 24 current Facade previews; preparation has no gateway/key."""
    with open_character_model_preview(parent / "previews", draft_path=draft_path, source_root=source_root,
                                      reviewed_digest=reviewed_digest) as product:
        plan = build_trial_plan(product.application.preview_character_reply,
            reviewed_digest=reviewed_digest, subject_id=subject_id, anchor_id=anchor_id,
            cases=cases, max_knowledge_chars=max_knowledge_chars)
    save_trial_plan(parent, plan)
    return plan


def open_character_context_trial(parent: Path, *, draft_path: Path, source_root: Path,
                                 reviewed_digest: str, subject_id: str, anchor_id: str, cases: dict,
                                 max_knowledge_chars: int = 20000, approved_plan: str | None = None,
                                 _transport=None) -> OpenedLocalProduct:
    """Only this composition seam can activate the separately approved trial.

    Approval is an operator assertion, not a substitute for user authorization.
    Restarted plans can read prior results, but are never given a gateway again.
    """
    from dynamic_subject_agent.character_context_trial_provider import DeepSeekCharacterContextAdapter
    plan = prepare_character_context_trial(parent, draft_path=draft_path, source_root=source_root,
        reviewed_digest=reviewed_digest, subject_id=subject_id, anchor_id=anchor_id,
        cases=cases, max_knowledge_chars=max_knowledge_chars)
    if approved_plan is not None and approved_plan != plan.digest:
        raise ValueError("current trial approval required")
    gateway = None
    if approved_plan is not None and not (parent / plan.digest).exists():
        transport = _transport if _transport is not None else DeepSeekUrlLibTransport(credential_resolver=_WindowsLabResolver())
        adapter = DeepSeekCharacterContextAdapter(transport=transport,
            credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID),
            allowed_outbound_digests=[row["outbound_digest"] for row in plan.payload["requests"]])
        gateway = ModelGateway(adapter)
    trial = CharacterContextTrial(plan, root=parent, gateway=gateway, approved_plan=approved_plan)
    return open_character_model_preview(parent / "products", draft_path=draft_path, source_root=source_root,
                                        reviewed_digest=reviewed_digest, reply_lab=trial)


def prepare_character_reply_review_trial(parent: Path, *, draft_path: Path, source_root: Path,
                                         reviewed_digest: str, subject_id: str, anchor_id: str,
                                         cases: dict, max_knowledge_chars: int = 20000, review_profile: str = "standard"):
    """Revalidate source through Facade and freeze review requests; no generator/key."""
    from dynamic_subject_agent.character_reply_review_trial import build_review_plan
    with open_character_model_preview(parent / "previews", draft_path=draft_path, source_root=source_root,
                                      reviewed_digest=reviewed_digest) as product:
        plan = build_review_plan(product.application.preview_character_reply,
            reviewed_digest=reviewed_digest, subject_id=subject_id, anchor_id=anchor_id,
            cases=cases, max_knowledge_chars=max_knowledge_chars, review_profile=review_profile)
    save_trial_plan(parent, plan)
    return plan


def open_character_reply_review_trial(parent: Path, *, draft_path: Path, source_root: Path,
                                      reviewed_digest: str, subject_id: str, anchor_id: str, cases: dict,
                                      max_knowledge_chars: int = 20000, approved_plan: str | None = None,
                                      review_profile: str = "standard", _transport=None) -> OpenedLocalProduct:
    """New exact approval activates review only; old generation approvals cannot apply."""
    from dynamic_subject_agent.character_reply_review_trial import CharacterReplyReviewTrial
    from dynamic_subject_agent.character_reply_review_provider import DeepSeekCharacterReplyReviewAdapter
    plan = prepare_character_reply_review_trial(parent, draft_path=draft_path, source_root=source_root,
        reviewed_digest=reviewed_digest, subject_id=subject_id, anchor_id=anchor_id,
        cases=cases, max_knowledge_chars=max_knowledge_chars, review_profile=review_profile)
    if approved_plan is not None and approved_plan != plan.digest:
        raise ValueError("current review approval required")
    gateway = None
    if approved_plan is not None and not (parent / plan.digest).exists():
        transport = _transport if _transport is not None else DeepSeekUrlLibTransport(credential_resolver=_WindowsLabResolver())
        gateway = ModelGateway(DeepSeekCharacterReplyReviewAdapter(transport=transport,
            credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID),
            allowed_outbound_digests=[row["outbound_digest"] for row in plan.payload["requests"]], review_profile=review_profile))
    trial = CharacterReplyReviewTrial(plan, root=parent, gateway=gateway, approved_plan=approved_plan)
    return open_character_model_preview(parent / "products", draft_path=draft_path, source_root=source_root,
                                        reviewed_digest=reviewed_digest, reply_lab=trial)


class _WindowsLabResolver(DeepSeekCredentialResolver):
    def resolve(self, credential_ref: CredentialRef) -> str:
        from dynamic_subject_agent.credentials import WindowsCredentialStore, DEEPSEEK_CREDENTIAL_SLOT, CredentialStoreUnavailable
        from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
        try:
            key = WindowsCredentialStore().load(DEEPSEEK_CREDENTIAL_SLOT)
        except CredentialStoreUnavailable:
            raise CharacterCredentialUnavailable() from None
        if not key:
            raise CharacterCredentialUnavailable()
        return key


_REMOTE_EVIDENCE_OPENED = False


def open_evidence_extraction_lab(parent: Path, *, workspace: Path, approved_plan: str | None = None, response_audit=None) -> OpenedLocalProduct:
    """A single reviewed extraction run. Default offline; no source state adopted."""
    global _REMOTE_EVIDENCE_OPENED
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    from dynamic_subject_agent.evidence_extraction_provider import OfflineEvidenceAdapter, DeepSeekEvidenceAdapter
    from dynamic_subject_agent.deepseek import DEEPSEEK_ENDPOINT
    if not isinstance(parent, Path) or not parent.is_absolute() or not isinstance(workspace, Path) or not workspace.is_absolute():
        raise ValueError("explicit extraction paths required")
    if approved_plan is not None and approved_plan != extraction_plan_digest():
        raise ValueError("current extraction approval required")
    adapter = OfflineEvidenceAdapter()
    if approved_plan is not None:
        if DEEPSEEK_MODEL != extraction_plan_payload()["model"] or DEEPSEEK_ENDPOINT != extraction_plan_payload()["endpoint"]:
            raise ValueError("provider changed")
        with _REMOTE_LAB_LOCK:
            if _REMOTE_EVIDENCE_OPENED:
                raise ValueError("one extraction run per process")
            _REMOTE_EVIDENCE_OPENED = True
        adapter = DeepSeekEvidenceAdapter(transport=DeepSeekUrlLibTransport(credential_resolver=_WindowsLabResolver()),
            credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,key_id=DEEPSEEK_CREDENTIAL_KEY_ID),
            response_audit=response_audit)
    lab = EvidenceExtractionLab(ModelGateway(adapter), workspace / ".local_indexes/eromanga-sensei/s68/focused-context-packets.json",
                                workspace / ".local_sources/eromanga-sensei")
    root = parent / ("evidence-lab-" + uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    config = LocalProductConfig(root / "DynamicSubjectAgent/m0/experiments", root / "state.json", "off")
    return open_local_product(config, cognition=DormantDeepSeekCognition(), _evidence_extraction=lab)


def open_reviewed_character_chat_product(config, *, definition_basis, scope_digest, review_request_basis,
                                         budget_total=200, initial_budget_used=61, budget_path=None, _transport=None):
    """Activate only the approved complete definition/scope, then open production chat.

    No model or credential is accessed until the user submits a bounded message.
    """
    from dynamic_subject_agent.character_chat_budget import CharacterChatBudget
    from dynamic_subject_agent.reviewed_character_chat_cognition import ReviewedCharacterChatCognition
    from dynamic_subject_agent.reviewed_character_chat_provider import DeepSeekReviewedCharacterChatAdapter
    import os
    if budget_path is None:
        local_app = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(local_app) if local_app else Path.home() / "AppData" / "Local"
        budget_path = base / "DynamicSubjectAgent/character-chat-v1/provider-budget"
    if not isinstance(budget_path, Path) or not budget_path.is_absolute(): raise ValueError("explicit absolute shared budget required")
    authority = LocalIdentityAuthority(config)
    loaded = authority.activate_reviewed_chat(definition_basis=definition_basis, scope_digest=scope_digest,
        review_request_basis=review_request_basis, budget_path=budget_path,
        budget_total=budget_total, initial_budget_used=initial_budget_used)
    budget = CharacterChatBudget(budget_path, total=budget_total, initial_used=initial_budget_used)
    transport = _transport if _transport is not None else DeepSeekUrlLibTransport(credential_resolver=_WindowsLabResolver())
    gateway = ModelGateway(DeepSeekReviewedCharacterChatAdapter(transport=transport,
        credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID)))
    cognition = ReviewedCharacterChatCognition(envelope=loaded.reviewed_definition, gateway=gateway, budget=budget,
        history_preference=lambda: authority.character_history_preference(loaded.qri.profile_id))
    return _open_loaded_local_product(config, authority=authority, loaded=loaded, cognition=cognition, source_authoring=None)


def open_first_life_product(config, *, definition_basis, life_scope_digest, budget_path,
                            budget_total=200, initial_budget_used=61, development_run=False,
                            runtime_policy=None, runtime_policy_digest=None,
                            _transport=None, _clock=None, _civil_day=None):
    """Open only the confirmed isolated life branch against the shared allowance."""
    from dynamic_subject_agent.first_life import current_civil_day
    from dynamic_subject_agent.first_life_budget import FirstLifeBudget
    from dynamic_subject_agent.first_life_clock import FirstLifeClock
    from dynamic_subject_agent.first_life_cognition import FirstLifeCognition
    from dynamic_subject_agent.first_life_provider import DeepSeekFirstLifeAdapter
    if not isinstance(budget_path, Path) or not budget_path.is_absolute(): raise ValueError("absolute existing shared budget required")
    authority = LocalIdentityAuthority(config)
    loaded = authority.activate_first_life(definition_basis=definition_basis, life_scope_digest=life_scope_digest,
        budget_path=budget_path, budget_total=budget_total, initial_budget_used=initial_budget_used, development_run=development_run)
    selected_policy = authority.first_life_runtime_policy(loaded.qri.profile_id,
        runtime_policy=runtime_policy, runtime_policy_digest=runtime_policy_digest)
    from dynamic_subject_agent.first_life_authorization import LEGACY_RUNTIME_POLICY
    adapter_type = DeepSeekFirstLifeAdapter
    if selected_policy == "first-life-relevance-2":
        from dynamic_subject_agent.first_life_relevance_provider import DeepSeekFirstLifeRelevanceAdapter
        adapter_type = DeepSeekFirstLifeRelevanceAdapter
    elif selected_policy == "first-life-grounded-3":
        from dynamic_subject_agent.first_life_grounded_provider import DeepSeekFirstLifeGroundedAdapter
        adapter_type = DeepSeekFirstLifeGroundedAdapter
    elif selected_policy == "first-life-followup-4":
        from dynamic_subject_agent.first_life_followup_provider import DeepSeekFirstLifeFollowupAdapter
        adapter_type = DeepSeekFirstLifeFollowupAdapter
    elif selected_policy != LEGACY_RUNTIME_POLICY:
        raise ValueError("unknown first-life runtime policy")
    day = current_civil_day if _civil_day is None else _civil_day
    budget = FirstLifeBudget(budget_path, total=budget_total, initial_used=initial_budget_used, civil_day=day)
    clock = FirstLifeClock() if _clock is None else FirstLifeClock(_clock)
    transport = _transport if _transport is not None else DeepSeekUrlLibTransport(credential_resolver=_WindowsLabResolver())
    gateway = ModelGateway(adapter_type(transport=transport,
        credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID)))
    cognition = FirstLifeCognition(envelope=loaded.reviewed_definition, gateway=gateway, budget=budget,
        history_preference=lambda: authority.character_history_preference(loaded.qri.profile_id), development_run=development_run, civil_day=day,
        runtime_policy=selected_policy, share_authorization=lambda: authority.first_life_share_authorization(loaded.qri.profile_id),
        share_guard=authority.first_life_share_guard,
        chat_authorization=lambda: authority.first_life_chat_authorization(loaded.qri.profile_id),
        chat_guard=authority.first_life_chat_guard)
    return _open_loaded_local_product(config, authority=authority, loaded=loaded, cognition=cognition, source_authoring=None,
        first_life_budget=budget, first_life_clock=clock, first_life_day=day, first_life_development=development_run)
