"""Exact approved private fiction-derived content, independent of source files."""
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
import re
from types import SimpleNamespace
from dynamic_subject_agent.character_evidence_model import CharacterEvidenceModel, CharacterModelView, CharacterModelItem, CharacterEntity, DIMENSIONS
from uuid import NAMESPACE_URL, uuid5

from dynamic_subject_agent.character_identity_preparation import CharacterSourceDeclaration, _complete_definition_basis, prepare_character_identity
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.source_character_authoring import (
    SourceDraftCandidate, SourceDraftView, SourceFreezeMappingRequest, SourceFreezeMappingStatus,
    ProposedGenesisCandidate, ProposedKnowledgeCandidate, TextSourceCharacterAuthoring, prepare_source_freeze_mapping,
)

REVIEWED_CHARACTER_AUTHORITY = "reviewed-character-dormant-1"
REVIEWED_CHARACTER_PROOF = "private-reviewed-fiction-derived"
REVIEWED_DEFINITION_VERSION = "sealed-reviewed-character-definition-1"
REVIEWED_KNOWLEDGE_QUALIFICATION = "qualified-reviewed-character-asset"


@dataclass(frozen=True)
class ReviewedCharacterFreezeRequest:
    preparation_json: str
    definition_basis: str
    rights_confirmed: bool = False
    confirmed: bool = False


def _sha(value):
    return sha256(canonical_json(value).encode()).hexdigest()


def reviewed_source_refs(definition_basis, asset_sha):
    return ("reviewed-definition:" + definition_basis, "runtime-asset:" + asset_sha, "use:private-character-chat")


def is_reviewed_source(source):
    return (source.origin_kind == "reviewed-fiction-derived" and source.rights_confirmed is True
        and source.uses_disallowed_inheritance is False and len(source.source_asset_refs) == 3
        and re.fullmatch(r"reviewed-definition:[0-9a-f]{64}", source.source_asset_refs[0]) is not None
        and re.fullmatch(r"runtime-asset:[0-9a-f]{64}", source.source_asset_refs[1]) is not None
        and source.source_asset_refs[2] == "use:private-character-chat")


def _declaration(value):
    if type(value) is not dict or set(value) != {
        "reviewed_digest", "subject_id", "anchor_id", "derived_document_digest", "origin_kind", "intended_use",
        "rights_confirmation_required", "rights_confirmed"}:
        raise ValueError("reviewed-definition-declaration-invalid")
    return CharacterSourceDeclaration(**value)


def validate_reviewed_envelope(value):
    if type(value) is not dict or set(value) != {"version", "definition_basis", "content_mapping_basis", "source_declaration", "runtime_asset", "runtime_asset_sha", "profile_content", "genesis_content", "source_title", "source_text", "candidates"}:
        raise ValueError("reviewed-definition-shape-invalid")
    if value["version"] != REVIEWED_DEFINITION_VERSION: raise ValueError("reviewed-definition-version-invalid")
    declaration = _declaration(value["source_declaration"])
    asset = value["runtime_asset"]
    def digest(text):
        return isinstance(text, str) and re.fullmatch(r"[0-9a-f]{64}", text) is not None
    def text(value, limit):
        return isinstance(value, str) and bool(value.strip()) and len(value) <= limit and "\x00" not in value
    if (any(not digest(item) for item in (declaration.reviewed_digest, declaration.derived_document_digest,
            value["definition_basis"], value["content_mapping_basis"], value["runtime_asset_sha"]))
        or not text(declaration.subject_id, 120) or not text(declaration.anchor_id, 120)):
        raise ValueError("reviewed-definition-declaration-invalid")
    if (declaration.origin_kind != "reviewed-fiction-derived" or declaration.intended_use != "private-character-chat"
            or declaration.rights_confirmation_required is not True or declaration.rights_confirmed is not True
            or type(asset) is not dict or set(asset) != {"version", "subject", "anchor", "initial_stage", "eligible", "chat_organization", "personality", "persona_digest"}
            or asset["version"] != "character-runtime-definition-2"
            or type(asset["subject"]) is not dict or set(asset["subject"]) != {"subject_id", "name"}
            or type(asset["anchor"]) is not dict or set(asset["anchor"]) != {"anchor_id"}
            or asset["subject"]["subject_id"] != declaration.subject_id or asset["anchor"]["anchor_id"] != declaration.anchor_id
            or not text(asset["subject"]["name"], 128) or not text(asset["initial_stage"], 500)
            or not digest(asset["persona_digest"])
            or type(asset["eligible"]) is not list or not asset["eligible"] or len(asset["eligible"]) > 1000
            or type(asset["personality"]) is not list or not 1 <= len(asset["personality"]) <= 8):
        raise ValueError("reviewed-definition-content-invalid")
    ids = set()
    for item in asset["eligible"]:
        if (type(item) is not dict or set(item) != {"item_id", "dimension", "kind", "statement", "derivation", "event_time", "knowledge_time"}
                or not text(item["item_id"], 120) or item["item_id"] in ids
                or item["dimension"] not in DIMENSIONS or item["derivation"] not in ("direct", "linked-evidence")
                or item["kind"] not in ("fact", "belief")
                or item["event_time"] not in ("before", "at") or item["knowledge_time"] not in ("before", "at")
                or not text(item["statement"], 1500)):
            raise ValueError("reviewed-definition-knowledge-invalid")
        ids.add(item["item_id"])
    organization = asset["chat_organization"]
    if organization is None:
        if not any(item["dimension"] == "identity" for item in asset["eligible"]):
            raise ValueError("reviewed-definition-core-missing")
    else:
        if type(organization) is not dict or set(organization) != {"version", "core", "episodes", "details"}:
            raise ValueError("reviewed-definition-organization-invalid")
        organization_draft = dict(version=organization["version"], subject_id=declaration.subject_id, anchor_id=declaration.anchor_id)
        for group in ("core", "episodes", "details"):
            rows = organization[group]
            if type(rows) is not list: raise ValueError("reviewed-definition-organization-invalid")
            converted = []
            for row in rows:
                if type(row) is not dict or set(row) != {"unit_id", "title", "content", "claim_ids", "cues"}:
                    raise ValueError("reviewed-definition-organization-invalid")
                converted.append(dict(id=row["unit_id"], **{key: row[key] for key in ("title", "content", "claim_ids", "cues")}))
            organization_draft[group] = converted
        CharacterEvidenceModel._organization(dict(subject_id=declaration.subject_id, anchor=dict(id=declaration.anchor_id),
            chat_organization=organization_draft), [SimpleNamespace(item_id=item["item_id"]) for item in asset["eligible"]])
    if len(canonical_json(asset["personality"])) > 12000:
        raise ValueError("reviewed-definition-personality-too-large")
    for item in asset["personality"]:
        if (type(item) is not dict or set(item) != {"title", "interpretation", "when", "choice", "expression", "limits", "basis", "support_includes_belief"}
                or item["basis"] != "author-interpretation" or type(item["support_includes_belief"]) is not bool
                or any(not text(item[key], 100 if key == "title" else 500) for key in ("title", "interpretation", "when", "choice", "expression", "limits"))):
            raise ValueError("reviewed-definition-personality-invalid")
    actual_sha = _sha(asset)
    if actual_sha != value["runtime_asset_sha"] or _complete_definition_basis(value["content_mapping_basis"], declaration,
        actual_sha, asset["persona_digest"]) != value["definition_basis"]:
        raise ValueError("reviewed-definition-basis-invalid")
    source_text = value["source_text"]
    if not isinstance(source_text, str) or len(source_text) > 16000 or sha256(source_text.encode()).hexdigest() != declaration.derived_document_digest:
        raise ValueError("reviewed-definition-source-invalid")
    candidates = tuple(SourceDraftCandidate(**item) for item in value["candidates"])
    if not candidates or len(candidates) > 16 or any(item.selected is not True or item.evidence_quote != item.content or len(item.content) > 500 or item.content not in source_text for item in candidates):
        raise ValueError("reviewed-definition-candidates-invalid")
    mapped = prepare_source_freeze_mapping(SourceDraftView(value["source_title"], declaration.derived_document_digest, 1, candidates),
        SourceFreezeMappingRequest(1, asset["subject"]["name"]))
    if (mapped.status is not SourceFreezeMappingStatus.AVAILABLE or mapped.view.freeze_basis_digest != value["content_mapping_basis"]
            or asdict(mapped.view.profile) != value["profile_content"] or asdict(mapped.view.genesis) != value["genesis_content"]):
        raise ValueError("reviewed-definition-mapping-invalid")
    # Rebuild the same pure S97 content mapping from the sealed asset, so
    # displayed knowledge and runtime knowledge cannot disagree structurally.
    reconstructed = prepare_character_identity(CharacterModelView("previewed",
        subject_id=declaration.subject_id, anchor_id=declaration.anchor_id,
        draft_digest=declaration.reviewed_digest, chat_stage_description=asset["initial_stage"],
        entities=(CharacterEntity(declaration.subject_id, asset["subject"]["name"], "person-reference"),),
        known=tuple(CharacterModelItem(**item, about=(), relation="", evidence_ids=()) for item in asset["eligible"])))
    if (reconstructed.status != "previewed" or reconstructed.source_title != value["source_title"]
        or reconstructed.source_text != source_text
        or canonical_json([asdict(item) for item in reconstructed.proposed_draft.candidates]) != canonical_json(value["candidates"])
        or reconstructed.provisional_basis != value["content_mapping_basis"]):
        raise ValueError("reviewed-definition-runtime-mapping-conflict")
    return value


def prepare_reviewed_definition(request):
    if type(request) is not ReviewedCharacterFreezeRequest or request.confirmed is not True or request.rights_confirmed is not True:
        raise ValueError("reviewed-character-confirmation-required")
    if not isinstance(request.preparation_json, str) or len(request.preparation_json) > 1_000_000:
        raise ValueError("reviewed-character-package-invalid")
    value = json.loads(request.preparation_json)
    if value.get("status") != "previewed" or value.get("definition_version") != "character-definition-approval-2":
        raise ValueError("reviewed-character-package-version-invalid")
    asset_json = value["runtime_asset_json"]
    asset = json.loads(asset_json)
    if canonical_json(asset) != asset_json: raise ValueError("reviewed-character-asset-not-canonical")
    source_text = value["source_text"]
    if not isinstance(source_text, str) or len(source_text) > 16000: raise ValueError("reviewed-character-source-invalid")
    candidates = tuple(SourceDraftCandidate(**item) for item in value["proposed_draft"]["candidates"])
    if not candidates or len(candidates) > 16 or any(item.selected is not True for item in candidates):
        raise ValueError("reviewed-character-candidates-invalid")
    seen = set()
    for item in candidates:
        if item.category == "genesis":
            result = TextSourceCharacterAuthoring._adjudicate_genesis(ProposedGenesisCandidate(item.kind, item.content, item.evidence_quote), source_text=source_text, over_limit=False, seen=seen)
        elif item.category == "knowledge":
            result = TextSourceCharacterAuthoring._adjudicate_knowledge(ProposedKnowledgeCandidate(item.title, item.content, item.evidence_quote), source_text=source_text, over_limit=False, seen=seen)
        else: raise ValueError("reviewed-character-candidate-category-invalid")
        if result.status != "accepted": raise ValueError("reviewed-character-candidate-evidence-invalid")
    source_sha = sha256(source_text.encode()).hexdigest()
    proposed = value["proposed_draft"]
    if type(proposed["revision"]) is not int or proposed["revision"] != 1 or proposed["source_digest"] != source_sha or proposed["source_title"] != value["source_title"]:
        raise ValueError("reviewed-character-source-binding-invalid")
    mapping = prepare_source_freeze_mapping(SourceDraftView(value["source_title"], source_sha, 1, candidates), SourceFreezeMappingRequest(1, asset["subject"]["name"]))
    if mapping.status is not SourceFreezeMappingStatus.AVAILABLE or canonical_json(asdict(mapping.view)) != canonical_json(value["mapping"]):
        raise ValueError("reviewed-character-mapping-invalid")
    declaration = _declaration(value["source_declaration"])
    if declaration.derived_document_digest != source_sha: raise ValueError("reviewed-character-source-digest-invalid")
    # Record the explicit request confirmation in the sealed copy only.
    # The content basis excludes this flag; the unsigned preparation stays intact.
    declaration = replace(declaration, rights_confirmed=True)
    envelope = dict(version=REVIEWED_DEFINITION_VERSION, definition_basis=value["definition_basis"],
        content_mapping_basis=mapping.view.freeze_basis_digest, source_declaration=asdict(declaration),
        runtime_asset=asset, runtime_asset_sha=_sha(asset), profile_content=asdict(mapping.view.profile), genesis_content=asdict(mapping.view.genesis))
    envelope.update(source_title=value["source_title"], source_text=source_text, candidates=[asdict(item) for item in candidates])
    validate_reviewed_envelope(envelope)
    if (envelope["definition_basis"] != request.definition_basis or value["runtime_asset_sha"] != envelope["runtime_asset_sha"]
            or value["provisional_basis"] != envelope["content_mapping_basis"]):
        raise ValueError("reviewed-character-request-basis-conflict")
    return envelope


def reviewed_profile_id(basis):
    return str(uuid5(NAMESPACE_URL, "dynamic-subject-agent:reviewed-character-profile:" + basis))
