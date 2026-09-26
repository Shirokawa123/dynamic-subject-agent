"""Read-only derived identity proposal; no draft save, freeze or authority writes."""
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from dynamic_subject_agent.character_evidence_model import CharacterModelView, CharacterModelItem, DIMENSIONS
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.source_character_authoring import (
    SourceDraftCandidate, SourceDraftView,
    SourceFreezeMappingRequest, SourceFreezeMappingView, SourceFreezeMappingStatus,
    TextSourceCharacterAuthoring, ProposedGenesisCandidate,
    ProposedKnowledgeCandidate, prepare_source_freeze_mapping, SOURCE_TITLE_MAX_CHARS,
    SOURCE_TEXT_MAX_CHARS, SOURCE_CANDIDATE_LIMIT,
)

_DIMENSION_NAMES = dict(identity="身份", biography="生平", relationships="人物关系", work="工作",
    abilities="能力与局限", values="价值与投入", concerns="关切", situation="起点处境", **{"world-knowledge": "世界知识"})
_SCOPES = {"before": "起点前", "at": "起点当时"}
DEFINITION_APPROVAL_VERSION = "character-definition-approval-1"
COMPLETE_DEFINITION_VERSION = "character-definition-approval-2"


@dataclass(frozen=True)
class CharacterDefinitionPreparationRequest:
    subject_id: str
    anchor_id: str
    sidecar_path: Path
    personality_digest: str


@dataclass(frozen=True)
class CharacterSourceDeclaration:
    reviewed_digest: str
    subject_id: str
    anchor_id: str
    derived_document_digest: str
    origin_kind: str = "reviewed-fiction-derived"
    intended_use: str = "private-character-chat"
    rights_confirmation_required: bool = True
    rights_confirmed: bool = False


@dataclass(frozen=True)
class CharacterDefinitionConfirmationRequest:
    definition_basis: str
    rights_confirmed: bool = False
    confirmed: bool = False


def _definition_basis(mapping_basis, declaration, runtime_asset_sha):
    return sha256(canonical_json(dict(version=DEFINITION_APPROVAL_VERSION, content_mapping_basis=mapping_basis,
        source_declaration=asdict(declaration), runtime_asset_sha=runtime_asset_sha)).encode()).hexdigest()


def _complete_definition_basis(mapping_basis, declaration, runtime_asset_sha, persona_digest):
    content = asdict(declaration)
    del content["rights_confirmed"]  # Approval state is not the approved object.
    return sha256(canonical_json(dict(version=COMPLETE_DEFINITION_VERSION, content_mapping_basis=mapping_basis,
        source_declaration=content, persona_digest=persona_digest, runtime_asset_sha=runtime_asset_sha)).encode()).hexdigest()


@dataclass(frozen=True)
class IdentityCandidateCoverage:
    candidate_index: int
    dimension: str
    item_ids: tuple[str, ...]


@dataclass(frozen=True)
class IdentityPreparationTrace:
    reviewed_digest: str
    subject_id: str
    anchor_id: str
    original_stage_description: str
    eligible_items: tuple[CharacterModelItem, ...]
    coverage: tuple[IdentityCandidateCoverage, ...]
    persona_digest: str = ""
    personality_support_json: str = ""


@dataclass(frozen=True)
class CharacterIdentityPreparationView:
    status: str
    code: str = ""
    source_title: str = ""
    source_text: str = ""
    proposed_draft: SourceDraftView | None = None
    mapping: SourceFreezeMappingView | None = None
    provisional_basis: str = ""
    basis_is_provisional: bool = True
    selection_status: str = "proposed-unconfirmed"
    source_request: None = None
    save_request: None = None
    freeze_request: None = None
    execution_ready: bool = False
    blocker: str = "original-only-freezer"
    content_mapping_only: bool = True
    source_declaration: CharacterSourceDeclaration | None = None
    runtime_asset_json: str = ""
    runtime_asset_sha: str = ""
    definition_basis: str = ""
    definition_version: str = DEFINITION_APPROVAL_VERSION
    confirmation_request: CharacterDefinitionConfirmationRequest | None = None
    trace: IdentityPreparationTrace | None = None
    excluded_diagnostics: tuple[CharacterModelItem, ...] = ()
    draft_saved: bool = False
    identity_created: bool = False


class _PreparationProblem(ValueError):
    pass


def _entry(item):
    if (item.kind not in ("fact", "belief") or item.event_time not in _SCOPES or item.knowledge_time not in _SCOPES
            or not isinstance(item.statement, str) or not item.statement.strip() or "\x00" in item.statement):
        raise _PreparationProblem("identity-eligible-item-invalid")
    kind = "事实" if item.kind == "fact" else "本人相信（非已证实事实）"
    return f"【{kind}；成立范围：{_SCOPES[item.event_time]}；本人知情范围：{_SCOPES[item.knowledge_time]}】\n{item.statement}"


def _chunks(items, *, prefix=""):
    current, refs = [], []
    for item in items:
        text = _entry(item)
        if len(prefix + text) > 500:
            raise _PreparationProblem("identity-complete-item-too-long")
        if current and len(prefix + "\n\n".join([*current, text])) > 500:
            yield prefix + "\n\n".join(current), tuple(refs)
            current, refs = [], []
        current.append(text); refs.append(item.item_id)
    if current:
        yield prefix + "\n\n".join(current), tuple(refs)


def prepare_character_identity(model, *, personality_request=None):
    if type(model) is not CharacterModelView:
        return CharacterIdentityPreparationView("rejected", "typed-character-model-required")
    if model.status != "previewed":
        return CharacterIdentityPreparationView(model.status, model.code)
    try:
        subject = next((entity for entity in model.entities if entity.entity_id == model.subject_id), None)
        if subject is None or not subject.name.strip(): raise _PreparationProblem("identity-subject-name-unavailable")
        name = subject.name
        if name != name.strip() or len(name) > 128 or any(char in name for char in ("\x00", "\r", "\n")):
            raise _PreparationProblem("identity-subject-name-invalid")
        if not model.chat_stage_description: raise _PreparationProblem("identity-stage-unavailable")
        identities = tuple(item for item in model.known if item.dimension == "identity")
        if not identities: raise _PreparationProblem("identity-knowledge-required")
        candidates, coverage = [], []
        def add(category, kind, title, content, dimension, refs=()):
            candidates.append(SourceDraftCandidate(category, kind, title, content, content, True))
            coverage.append(IdentityCandidateCoverage(len(candidates) - 1, dimension, refs))
        for content, refs in _chunks(identities, prefix=f"主体名称：{name}。\n"):
            add("genesis", "identity", None, content, "identity", refs)
        # This is a starting-point description, never a claim that the person
        # knows they are a character from a book or follows a product voice.
        # Only this known trailing tool note is omitted from the initial
        # definition. Keep the exact reviewed stage in the human-only trace.
        reviewed_stage = model.chat_stage_description.removesuffix("此离线预览不推进时间。")
        stage = f"起点说明：{reviewed_stage}\n过去与当时均相对此起点。"
        if len(stage) > 500: raise _PreparationProblem("identity-complete-stage-too-long")
        add("genesis", "origin", None, stage, "stage")
        for dimension in DIMENSIONS:
            if dimension == "identity": continue
            items = tuple(item for item in model.known if item.dimension == dimension)
            for index, (content, refs) in enumerate(_chunks(items), 1):
                add("knowledge", None, f"{_DIMENSION_NAMES[dimension]} {index}", content, dimension, refs)
        covered = [item_id for item in coverage for item_id in item.item_ids]
        if len(covered) != len(model.known) or set(covered) != {item.item_id for item in model.known}:
            raise _PreparationProblem("identity-coverage-incomplete")
        if len(candidates) > SOURCE_CANDIDATE_LIMIT * 2: raise _PreparationProblem("identity-candidate-limit")
        title = f"已审人物起点派生定义：{name}"
        if len(title) > SOURCE_TITLE_MAX_CHARS: raise _PreparationProblem("identity-source-title-too-long")
        header = ("这是从已审核人物资料确定性整理的派生定义，不是小说原文。\n"
                  "候选的逐字引用指向本派生文档，不冒称原作直接引文；排除及待核项没有进入定义。\n"
                  "此文档仅供本地保存与封存准备，不用于远程重新提取。\n"
                  "本地选择绑定：" + canonical_json(dict(subject_id=model.subject_id, anchor_id=model.anchor_id)) + "\n"
                  f"已审资料指纹：{model.draft_digest}\n")
        source = header + "\n\n".join(item.content for item in candidates)
        if len(source) > SOURCE_TEXT_MAX_CHARS or "\x00" in source: raise _PreparationProblem("identity-source-too-long")
        seen = set()
        for item in candidates:
            if item.category == "genesis":
                verdict = TextSourceCharacterAuthoring._adjudicate_genesis(ProposedGenesisCandidate(item.kind, item.content, item.evidence_quote),
                    source_text=source, over_limit=False, seen=seen)
            else:
                verdict = TextSourceCharacterAuthoring._adjudicate_knowledge(ProposedKnowledgeCandidate(item.title, item.content, item.evidence_quote),
                    source_text=source, over_limit=False, seen=seen)
            if verdict.status != "accepted": raise _PreparationProblem("identity-derived-candidate-invalid")
        digest = sha256(source.encode()).hexdigest()
        draft = SourceDraftView(title, digest, 1, tuple(candidates))
        mapping = prepare_source_freeze_mapping(draft, SourceFreezeMappingRequest(1, name))
        if mapping.status is not SourceFreezeMappingStatus.AVAILABLE or mapping.view is None:
            raise _PreparationProblem(mapping.problem_code or "identity-mapping-unavailable")
        declaration = CharacterSourceDeclaration(model.draft_digest, model.subject_id, model.anchor_id, digest)
        asset = dict(version="character-runtime-definition-1", subject=dict(subject_id=model.subject_id, name=name),
            anchor=dict(anchor_id=model.anchor_id), initial_stage=reviewed_stage,
            eligible=[dict(item_id=item.item_id, dimension=item.dimension, kind=item.kind, statement=item.statement,
                derivation=item.derivation, event_time=item.event_time, knowledge_time=item.knowledge_time) for item in model.known],
            chat_organization=asdict(model.chat_organization) if model.chat_organization is not None else None)
        asset_json = canonical_json(asset)
        asset_sha = sha256(asset_json.encode()).hexdigest()
        definition_basis = _definition_basis(mapping.view.freeze_basis_digest, declaration, asset_sha)
        definition_version, persona_digest, supports = DEFINITION_APPROVAL_VERSION, "", ""
        if personality_request is not None:
            from dynamic_subject_agent.character_personality import load_personality_draft
            if (type(personality_request) is not CharacterDefinitionPreparationRequest
                    or personality_request.subject_id != model.subject_id or personality_request.anchor_id != model.anchor_id):
                raise _PreparationProblem("complete-definition-selection-invalid")
            interpretations, sidecar = load_personality_draft(model, personality_request.sidecar_path, personality_request.personality_digest)
            persona_digest = personality_request.personality_digest
            asset.update(version="character-runtime-definition-2", personality=[asdict(item) for item in interpretations], persona_digest=persona_digest)
            asset_json = canonical_json(asset)
            asset_sha = sha256(asset_json.encode()).hexdigest()
            definition_basis = _complete_definition_basis(mapping.view.freeze_basis_digest, declaration, asset_sha, persona_digest)
            definition_version = COMPLETE_DEFINITION_VERSION
            supports = canonical_json([dict(id=item["id"], claim_ids=item["claim_ids"]) for item in sidecar["items"]])
        return CharacterIdentityPreparationView("previewed", source_title=title, source_text=source, proposed_draft=draft,
            mapping=mapping.view, provisional_basis=mapping.view.freeze_basis_digest,
            source_declaration=declaration, runtime_asset_json=asset_json, runtime_asset_sha=asset_sha,
            definition_basis=definition_basis, definition_version=definition_version, confirmation_request=CharacterDefinitionConfirmationRequest(definition_basis),
            trace=IdentityPreparationTrace(model.draft_digest, model.subject_id, model.anchor_id, model.chat_stage_description, model.known, tuple(coverage), persona_digest, supports),
            excluded_diagnostics=model.excluded)
    except _PreparationProblem as failure:
        return CharacterIdentityPreparationView("failed-closed", str(failure))
    except FileNotFoundError:
        return CharacterIdentityPreparationView("unavailable", "definition-personality-source-missing")
    except Exception:
        return CharacterIdentityPreparationView("failed-closed", "identity-preparation-unavailable")
