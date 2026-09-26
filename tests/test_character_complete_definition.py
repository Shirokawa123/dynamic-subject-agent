from dataclasses import asdict, replace
from hashlib import sha256
import json

import pytest

from dynamic_subject_agent.character_evidence_model import CharacterModelRequest
from dynamic_subject_agent.character_identity_preparation import (
    CharacterDefinitionPreparationRequest, _definition_basis, _complete_definition_basis,
)
from test_character_evidence_model import model_fixture
from test_character_personality import personality_fixture


def setup_view(personality_fixture):
    _, path, _, _, open_lab = personality_fixture
    product, _, _, sidecar = open_lab(preview_only=True)
    request = CharacterDefinitionPreparationRequest("self", "start", sidecar, sha256(sidecar.read_bytes()).hexdigest())
    return product, request, path


def test_complete_package_keeps_personality_separate_and_performs_no_model_or_identity_write(personality_fixture, monkeypatch):
    from dynamic_subject_agent.model_gateway import ModelGateway
    from dynamic_subject_agent.application import ApplicationFacade
    product, request, path = setup_view(personality_fixture)
    app = product.application
    old = app.preview_character_identity_preparation(CharacterModelRequest("self", "start"))
    before = {str(file): file.read_bytes() for file in (path.parent / "personality-products").rglob("*") if file.is_file()}
    monkeypatch.setattr(ModelGateway, "execute", lambda *a: pytest.fail("definition preview called provider"))
    for name in ("source_draft", "freeze_source_identity", "select_local_identity"):
        monkeypatch.setattr(ApplicationFacade, name, lambda *a: pytest.fail("definition preview called write interface"))
    view = app.preview_character_identity_preparation(request)
    assert view.status == "previewed" and view.definition_version == "character-definition-approval-2"
    assert view.mapping == old.mapping and view.source_text == old.source_text and view.definition_basis != old.definition_basis
    asset = json.loads(view.runtime_asset_json); old_asset = json.loads(old.runtime_asset_json)
    assert asset["version"] == "character-runtime-definition-2" and asset["persona_digest"] == request.personality_digest
    for key in ("subject", "anchor", "initial_stage", "eligible", "chat_organization"): assert asset[key] == old_asset[key]
    assert asset["personality"][0]["basis"] == "author-interpretation" and asset["personality"][0]["support_includes_belief"] is True
    assert "candidate-private-id" not in view.runtime_asset_json and "claim_ids" not in json.dumps(asset["personality"])
    assert "future" not in view.runtime_asset_json and "evidence_ids" not in view.runtime_asset_json and "time_basis" not in view.runtime_asset_json
    supports = json.loads(view.trace.personality_support_json)
    assert supports[0]["id"] == "candidate-private-id" and set(supports[0]["claim_ids"]) == {"a", "work"}
    assert all("适合的话题可以投入" not in member.content for member in view.mapping.knowledge_members)
    assert not view.execution_ready and view.blocker == "original-only-freezer" and view.save_request is None and view.freeze_request is None
    assert view.confirmation_request.rights_confirmed is False and view.confirmation_request.confirmed is False
    assert not view.draft_saved and not view.identity_created
    assert before == {str(file): file.read_bytes() for file in (path.parent / "personality-products").rglob("*") if file.is_file()}


def test_content_basis_changes_with_persona_or_use_not_with_confirmation(personality_fixture):
    product, request, _ = setup_view(personality_fixture)
    app = product.application
    first = app.preview_character_identity_preparation(request)
    assert _complete_definition_basis(first.provisional_basis, replace(first.source_declaration, rights_confirmed=True),
        first.runtime_asset_sha, request.personality_digest) == first.definition_basis
    confirmation = replace(first.confirmation_request, confirmed=True, rights_confirmed=True)
    assert confirmation.definition_basis == first.definition_basis
    assert _complete_definition_basis(first.provisional_basis, replace(first.source_declaration, intended_use="different-use"),
        first.runtime_asset_sha, request.personality_digest) != first.definition_basis
    data = json.loads(request.sidecar_path.read_text(encoding="utf-8")); data["items"][0]["limits"] += " 改过的实质界限。"
    request.sidecar_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    changed = app.preview_character_identity_preparation(replace(request, personality_digest=sha256(request.sidecar_path.read_bytes()).hexdigest()))
    assert changed.status == "previewed" and changed.definition_basis != first.definition_basis and changed.runtime_asset_sha != first.runtime_asset_sha


@pytest.mark.parametrize("problem", ["missing", "hash", "foreign-ref", "subject", "anchor"])
def test_invalid_persona_or_selection_cannot_create_partial_complete_definition(personality_fixture, problem):
    product, request, _ = setup_view(personality_fixture)
    if problem == "missing": request.sidecar_path.rename(request.sidecar_path.with_suffix(".withheld"))
    elif problem == "hash": request.sidecar_path.write_bytes(request.sidecar_path.read_bytes() + b" ")
    elif problem == "foreign-ref":
        data = json.loads(request.sidecar_path.read_text(encoding="utf-8")); data["items"][0]["claim_ids"] = ["future"]
        request.sidecar_path.write_text(json.dumps(data), encoding="utf-8")
        request = replace(request, personality_digest=sha256(request.sidecar_path.read_bytes()).hexdigest())
    else: request = replace(request, **{problem + "_id": "different"})
    view = product.application.preview_character_identity_preparation(request)
    assert view.status == ("unavailable" if problem == "missing" else "rejected" if problem in ("subject", "anchor") else "failed-closed")
    assert not view.runtime_asset_json and not view.definition_basis and view.mapping is None


def test_without_sidecar_original_v1_asset_and_basis_are_unchanged(personality_fixture):
    product, _, _ = setup_view(personality_fixture)
    view = product.application.preview_character_identity_preparation(CharacterModelRequest("self", "start"))
    assert view.definition_version == "character-definition-approval-1"
    assert json.loads(view.runtime_asset_json)["version"] == "character-runtime-definition-1"
    assert "personality" not in json.loads(view.runtime_asset_json)
    assert view.definition_basis == _definition_basis(view.provisional_basis, view.source_declaration, view.runtime_asset_sha)
    assert view.trace.persona_digest == "" and view.trace.personality_support_json == ""
