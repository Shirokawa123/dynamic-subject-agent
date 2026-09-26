from dataclasses import asdict, replace
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from dynamic_subject_agent.character_evidence_model import CharacterModelRequest, DIMENSIONS
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.source_character_authoring import prepare_source_freeze_mapping, SourceFreezeMappingRequest
from test_character_evidence_model import model_fixture


def request(): return CharacterModelRequest("self", "start")


def set_thirty(draft):
    template = draft["assertions"][0]
    draft["entities"][0]["name"] = "未补年龄的人物"
    draft["assertions"] = [dict(template, id=f"claim-id-{i:02}", dimension=DIMENSIONS[i % len(DIMENSIONS)],
        kind="belief" if i == 5 else "fact", event_time="at" if i % 2 else "before", knowledge_time="at" if i % 3 else "before",
        statement=f"第{i}条原陈述只适用于那次合作；未说每次都这样。") for i in range(30)]
    draft["assertions"].extend([
        dict(template, id="future", statement="EXCLUDED_FUTURE_TOKEN", event_time="after"),
        dict(template, id="unreviewed", statement="EXCLUDED_REVIEW_TOKEN", review="candidate"),
    ])


def test_facade_covers_all_thirty_complete_items_without_ids_excluded_or_implicit_confirmation(model_fixture, monkeypatch):
    from dynamic_subject_agent.model_gateway import ModelGateway
    from dynamic_subject_agent.application import ApplicationFacade
    from dynamic_subject_agent.studio import SubjectStudio
    import dynamic_subject_agent.source_character_authoring as authoring
    draft, create, _, _ = model_fixture
    set_thirty(draft)
    product = create(); app = product.application
    monkeypatch.setattr(ModelGateway, "execute", lambda *a: pytest.fail("identity preparation called a model"))
    for method in ("source_draft", "freeze_source_identity", "select_local_identity"):
        monkeypatch.setattr(ApplicationFacade, method, lambda *a: pytest.fail("identity preparation called a write interface"))
    monkeypatch.setattr(SubjectStudio, "source_draft", lambda *a: pytest.fail("identity preparation accessed drafts"))
    monkeypatch.setattr(authoring, "prepare_source_draft_save", lambda *a: pytest.fail("preparation fabricated save confirmation"))
    view = app.preview_character_identity_preparation(request())
    assert view.status == "previewed" and not view.draft_saved and not view.identity_created
    assert view.basis_is_provisional and view.selection_status == "proposed-unconfirmed"
    assert view.source_request is None
    assert view.save_request is None and view.freeze_request is None
    assert view.confirmation_request.confirmed is False and view.confirmation_request.rights_confirmed is False
    assert not view.execution_ready and view.blocker == "original-only-freezer" and view.content_mapping_only
    assert view.mapping.draft_revision == view.proposed_draft.revision == 1
    assert view.mapping.profile.display_name == "未补年龄的人物" and view.mapping.freeze_basis_digest == view.provisional_basis
    assert view.trace.reviewed_digest in view.source_text and "不是小说原文" in view.source_text
    assert view.proposed_draft.source_digest == sha256(view.source_text.encode()).hexdigest()
    assert len(view.proposed_draft.candidates) <= 16 and len(view.source_text) <= 16000
    mapped = view.mapping.profile.identity_core + view.mapping.genesis.subject_identity + "\n".join(item.content for item in view.mapping.knowledge_members)
    for item in draft["assertions"][:30]:
        assert item["statement"] in view.source_text
        assert any(item["statement"] in candidate.content for candidate in view.proposed_draft.candidates)
        assert item["statement"].strip().rstrip("。；;") in mapped
        assert item["id"] not in mapped
    assert "本人相信（非已证实事实）" in mapped and "成立范围：起点当时" in mapped and "本人知情范围：起点前" in mapped
    assert "EXCLUDED_FUTURE_TOKEN" not in view.source_text + mapped and "EXCLUDED_REVIEW_TOKEN" not in view.source_text + mapped
    assert {item.item_id for item in view.excluded_diagnostics} == {"future", "unreviewed"}
    covered = [item_id for item in view.trace.coverage for item_id in item.item_ids]
    assert len(covered) == len(set(covered)) == 30 and set(covered) == {item["id"] for item in draft["assertions"][:30]}
    assert all(item.evidence_quote == item.content and item.content in view.source_text and len(item.evidence_quote) <= 500 for item in view.proposed_draft.candidates)
    assert all(len(item.content) <= 1000 for item in view.mapping.knowledge_members)
    assert not any(item.kind in ("trait", "voice") for item in view.proposed_draft.candidates)
    assert view.mapping.genesis.initial_relationship_premise.startswith("这是一个新创建的身份")
    assert app.preview_character_identity_preparation(request()) == view


def test_preview_restarts_with_same_basis_and_keeps_canonical_and_studio_bytes_unchanged(model_fixture):
    draft, create, path, _ = model_fixture
    set_thirty(draft)
    product = create()
    parent = path.parent / "products"
    before = {str(file): file.read_bytes() for file in parent.rglob("*") if file.is_file()}
    first = product.application.preview_character_identity_preparation(request())
    assert first.status == "previewed"
    assert before == {str(file): file.read_bytes() for file in parent.rglob("*") if file.is_file()}
    product.close()
    second = create().application.preview_character_identity_preparation(request())
    assert second == first
    pure = prepare_source_freeze_mapping(second.proposed_draft, SourceFreezeMappingRequest(1, second.mapping.profile.display_name))
    assert pure.view == second.mapping and second.save_request is None


def test_draft_or_stage_change_changes_provisional_basis_while_bad_source_fails_closed(model_fixture):
    from dynamic_subject_agent.local_product import open_character_model_preview
    draft, create, path, book = model_fixture
    original_product = create()
    first = original_product.application.preview_character_identity_preparation(request())
    assert first.status == "previewed"
    path.write_bytes(path.read_bytes() + b" ")
    assert original_product.application.preview_character_identity_preparation(request()).status == "failed-closed"
    with open_character_model_preview(path.parent / "reviewed-whitespace", draft_path=path, source_root=book.parent,
        reviewed_digest=sha256(path.read_bytes()).hexdigest()) as product:
        assert product.application.preview_character_identity_preparation(request()).provisional_basis != first.provisional_basis
    draft["assertions"][0]["statement"] += " Additional exact limitation."
    changed = create().application.preview_character_identity_preparation(request())
    assert changed.status == "previewed" and changed.provisional_basis != first.provisional_basis
    draft["chat_stage_description"] += " A different reviewed moment."
    shifted_product = create()
    shifted = shifted_product.application.preview_character_identity_preparation(request())
    assert shifted.provisional_basis != changed.provisional_basis
    book.write_bytes(book.read_bytes() + b"bad")
    failed = shifted_product.application.preview_character_identity_preparation(request())
    assert failed.status == "failed-closed" and failed.mapping is None and failed.save_request is None


@pytest.mark.parametrize("limit", ["single-item", "stage", "candidate-count", "identity-total", "title"])
def test_complete_content_over_limits_is_rejected_without_partial_truncation(model_fixture, limit):
    draft, create, _, _ = model_fixture
    template = draft["assertions"][0]
    if limit == "single-item": draft["assertions"][0]["statement"] = "长" * 500
    elif limit == "stage": draft["chat_stage_description"] = "段" * 500
    elif limit == "candidate-count":
        draft["assertions"].extend(dict(template, id=f"long-{i}", dimension="work", statement=f"完整第{i}条" + "知" * 420) for i in range(17))
    elif limit == "identity-total":
        draft["assertions"] = [dict(template, id=f"identity-{i}", statement=f"身份第{i}条" + "知" * 370) for i in range(5)]
    else: draft["entities"][0]["name"] = "名" * 115
    view = create().application.preview_character_identity_preparation(request())
    assert view.status == "failed-closed" and view.code in ("identity-complete-item-too-long", "identity-complete-stage-too-long", "identity-candidate-limit",
        "source-freeze-mapped-content-too-long", "identity-source-title-too-long")
    assert not view.source_text and view.mapping is None and view.proposed_draft is None and not view.draft_saved and not view.identity_created


def test_entity_name_and_only_known_identity_drive_profile_without_book_origin_or_product_voice(model_fixture):
    draft, create, _, _ = model_fixture
    draft["entities"][0]["name"] = "源内本人名"
    draft["assertions"][0]["statement"] = "本人使用一个工作署名，具体年龄尚未列明。"
    view = create().application.preview_character_identity_preparation(request())
    assert view.status == "previewed" and view.mapping.profile.display_name == "源内本人名"
    profile = view.mapping.profile.identity_core
    assert draft["assertions"][0]["statement"].rstrip("。；;") in profile
    for unwanted in ("来自小说", "sample.epub", "十二岁", "25岁", "短消息", "每轮两三句"):
        assert unwanted not in profile + view.mapping.genesis.subject_identity
    assert "此身份尚无运行时经历" in view.mapping.genesis.canon_start


def test_only_known_trailing_tool_note_is_removed_from_genesis_and_original_stage_is_traced(model_fixture):
    draft, create, _, _ = model_fixture
    stage = "已有此前直播经验；当天预告直播尚未发生；过去与当时均相对此起点。此离线预览不推进时间。"
    draft["chat_stage_description"] = stage
    view = create().application.preview_character_identity_preparation(request())
    assert view.status == "previewed" and view.trace.original_stage_description == stage
    assert stage.removesuffix("此离线预览不推进时间。") in view.mapping.genesis.canon_start
    assert "此离线预览不推进时间" not in view.mapping.genesis.canon_start
    assert "这里不推进运行时间" not in view.mapping.genesis.canon_start
    assert "身份条目结束" not in view.mapping.profile.identity_core + view.source_text
    identity = next(item for item in view.proposed_draft.candidates if item.kind == "identity")
    assert draft["assertions"][0]["statement"] in identity.content and identity.evidence_quote == identity.content
    assert view.mapping.profile.identity_core == identity.content.strip().rstrip("。；;")
    draft["chat_stage_description"] = "资料引用此离线预览不推进时间。后面仍有剧情起点限制。"
    changed = create().application.preview_character_identity_preparation(request())
    assert changed.trace.original_stage_description in changed.mapping.genesis.canon_start


@pytest.mark.parametrize("field,value", [("subject_id", "another-subject"), ("anchor_id", "another-anchor")])
def test_same_reviewed_text_under_different_local_selection_has_different_basis(model_fixture, monkeypatch, field, value):
    from dynamic_subject_agent.character_evidence_model import CharacterEvidenceModel
    draft, create, _, _ = model_fixture
    draft["assertions"].append(dict(draft["assertions"][0], id="work", dimension="work", statement="工作原陈述也完整保持。"))
    app = create().application
    model = app.preview_character_model(request())
    first = app.preview_character_identity_preparation(request())
    def alternative(self, selected):
        return replace(model, subject_id=selected.subject_id, anchor_id=selected.anchor_id,
            entities=tuple(replace(entity, entity_id=selected.subject_id) if entity.entity_id == model.subject_id else entity for entity in model.entities),
            known=tuple(replace(item, knower_id=selected.subject_id) for item in model.known))
    monkeypatch.setattr(CharacterEvidenceModel, "preview", alternative)
    second = app.preview_character_identity_preparation(replace(request(), **{field: value}))
    assert first.status == second.status == "previewed" and first.trace.reviewed_digest == second.trace.reviewed_digest
    assert first.mapping.profile.identity_core == second.mapping.profile.identity_core
    assert first.mapping.genesis == second.mapping.genesis
    assert first.provisional_basis != second.provisional_basis
    assert first.definition_basis != second.definition_basis
    assert value in second.source_text
    assert value not in second.mapping.profile.identity_core + second.mapping.genesis.canon_start
    assert all(value not in member.content for member in second.mapping.knowledge_members)
    assert len(second.mapping.knowledge_members) == 1 and first.mapping.knowledge_members[0].content == second.mapping.knowledge_members[0].content
    assert second.source_request is None and second.save_request is None and second.freeze_request is None
    assert second.confirmation_request.confirmed is False and second.confirmation_request.rights_confirmed is False


def test_wrong_subject_closed_facade_and_missing_identity_never_produce_mapping(model_fixture):
    draft, create, _, _ = model_fixture
    product = create()
    assert product.application.preview_character_identity_preparation(CharacterModelRequest("other", "start")).status == "rejected"
    product.close()
    assert product.application.preview_character_identity_preparation(request()).status == "unavailable"
    draft["assertions"][0]["dimension"] = "work"
    assert create().application.preview_character_identity_preparation(request()).code == "identity-knowledge-required"


def test_cli_only_writes_explicit_preview_with_all_confirmations_false(model_fixture, tmp_path):
    _, create, path, book = model_fixture
    create()
    output = tmp_path / "explicit-preview.json"
    cli = Path(__file__).resolve().parents[1] / "app/desktop/character_identity_preparation.py"
    completed = subprocess.run([sys.executable, str(cli), "--draft", str(path), "--source-root", str(book.parent),
        "--reviewed-digest", sha256(path.read_bytes()).hexdigest(), "--subject", "self", "--anchor", "start", "--output", str(output)],
        capture_output=True, check=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    summary = json.loads(completed.stdout); saved = json.loads(output.read_text(encoding="utf-8"))
    assert summary["draft_saved"] is False and summary["identity_created"] is False and summary["status"] == "previewed"
    assert saved["save_request"] is None and saved["freeze_request"] is None
    assert saved["confirmation_request"]["rights_confirmed"] is False and saved["confirmation_request"]["confirmed"] is False
    assert saved["source_request"] is None


def test_definition_package_declares_fiction_source_and_binds_minimal_self_contained_asset(model_fixture):
    from dynamic_subject_agent.character_identity_preparation import _definition_basis
    from dynamic_subject_agent.source_character_authoring import SourceIdentityFreezeRequest
    draft, create, _, _ = model_fixture
    set_thirty(draft)
    view = create().application.preview_character_identity_preparation(request())
    assert view.status == "previewed" and view.source_declaration.origin_kind == "reviewed-fiction-derived"
    assert view.source_declaration.intended_use == "private-character-chat"
    assert view.source_declaration.rights_confirmation_required and not view.source_declaration.rights_confirmed
    assert view.source_declaration.derived_document_digest == view.proposed_draft.source_digest
    asset = json.loads(view.runtime_asset_json)
    assert view.runtime_asset_json == canonical_json(asset) and sha256(view.runtime_asset_json.encode()).hexdigest() == view.runtime_asset_sha
    assert len(asset["eligible"]) == 30 and asset["subject"]["subject_id"] == "self" and asset["anchor"]["anchor_id"] == "start"
    assert {item["statement"] for item in asset["eligible"]} == {item.statement for item in view.trace.eligible_items}
    for forbidden in ("EXCLUDED_FUTURE_TOKEN", "EXCLUDED_REVIEW_TOKEN", "citations", "evidence_ids", "time_basis", "sample.epub", "reviewed source"):
        assert forbidden not in view.runtime_asset_json
    assert set(asdict(view.confirmation_request)) == {"definition_basis", "rights_confirmed", "confirmed"}
    assert not isinstance(view.confirmation_request, SourceIdentityFreezeRequest)
    assert view.definition_basis == _definition_basis(view.provisional_basis, view.source_declaration, view.runtime_asset_sha)
    assert _definition_basis(view.provisional_basis, replace(view.source_declaration, intended_use="changed-use"), view.runtime_asset_sha) != view.definition_basis
    assert _definition_basis(view.provisional_basis, view.source_declaration, "0" * 64) != view.definition_basis
