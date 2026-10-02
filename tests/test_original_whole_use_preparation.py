from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from dynamic_subject_agent.application import ApplicationFacade
from dynamic_subject_agent.character_identity_preparation import CharacterDefinitionPreparationRequest
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.original_whole_use_preparation import OriginalWholeUsePreparationRequest
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest, prepare_reviewed_definition, validate_character_preparation
from test_character_evidence_model import model_fixture
from test_character_personality import personality_fixture


@pytest.fixture
def preparation(personality_fixture, tmp_path):
    _, _, _, _, open_lab = personality_fixture
    product, _, _, sidecar = open_lab(preview_only=True)
    definition = product.application.preview_character_identity_preparation(CharacterDefinitionPreparationRequest(
        "self", "start", sidecar, sha256(sidecar.read_bytes()).hexdigest()))
    package = tmp_path / "complete-definition.json"
    package.write_text(canonical_json(asdict(definition)), encoding="utf-8")
    asset = json.loads(definition.runtime_asset_json)
    request = OriginalWholeUsePreparationRequest(package, definition.definition_basis, definition.runtime_asset_sha,
        asset["persona_digest"], "self", "start")
    return request, definition, product


def preview(request):
    return ApplicationFacade.preview_original_character_whole_use_preparation(request)


def test_facade_reads_only_package_and_exports_no_real_character_text_or_executable_request(preparation, monkeypatch):
    from dynamic_subject_agent.model_gateway import ModelGateway
    from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
    from dynamic_subject_agent.credentials import WindowsCredentialStore
    from dynamic_subject_agent.studio import SubjectStudio
    from dynamic_subject_agent import local_product
    request, definition, _ = preparation
    before = request.package_path.read_bytes()
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(True)
        pytest.fail("pure author review opened runtime, credentials, model or identity writes")
    for owner, names in ((ModelGateway, ("execute",)), (LocalIdentityAuthority, ("load_active", "freeze")),
            (WindowsCredentialStore, ("load", "save", "delete")), (SubjectStudio, ("open",)),
            (local_product, ("open_local_product",)), (ApplicationFacade, ("freeze_source_identity", "select_local_identity"))):
        for name in names:
            monkeypatch.setattr(owner, name, forbidden)
    view = preview(request)
    assert view.status == "previewed", view
    assert view == preview(request) and not calls and before == request.package_path.read_bytes()
    assert view.definition_basis == definition.definition_basis and view.runtime_asset_sha == definition.runtime_asset_sha
    assert view.local_only and not view.remote_use_authorized and not view.execution_ready
    assert not view.rights_confirmed and not view.use_confirmed and view.approval_status == "awaiting-exact-whole-use-approval"
    assert view.eligible_count == len(definition.trace.eligible_items) and view.personality_count == 1 and view.core_count > 0
    rendered = canonical_json(asdict(view))
    real_asset = json.loads(definition.runtime_asset_json)
    for item in real_asset["eligible"]:
        assert item["statement"] not in rendered
    for item in real_asset["personality"]:
        assert item["interpretation"] not in rendered
    for forbidden_text in ("candidate-private-id", "claim_ids", "evidence_ids", "runtime_asset_json", "freeze_request", "save_request", "ModelTask"):
        assert forbidden_text not in rendered
    scope = json.loads(view.proposed_scope_json)
    assert scope["input_fields"]["exchange"]["max_complete_turns"] == 2
    assert scope["input_fields"]["exchange"]["max_total_chars"] == 4000
    assert scope["input_fields"]["turn"]["current_message"]["max_chars"] == 1000
    assert scope["protocol"]["max_requests_per_turn"] == 1 and scope["protocol"]["automatic_retries"] == 0
    example = json.loads(view.synthetic_example_json)
    assert not example["actual_character_material_included"] and example["exchange"] == []
    assert example["evidence"] == scope["input_fields"]["evidence"] == dict(current_activity=None, current_plan=None, related_event=None)


@pytest.mark.parametrize("field", ["expected_definition_basis", "expected_runtime_asset_sha", "expected_persona_digest", "subject_id", "anchor_id"])
def test_foreign_or_stale_expected_object_fails_closed_without_partial_review(preparation, field):
    request, _, _ = preparation
    view = preview(replace(request, **{field: "different" if field in ("subject_id", "anchor_id") else "0" * 64}))
    assert view.status == "failed-closed"
    assert view.review_basis == view.scope_digest == view.selected_material_sha256 == view.synthetic_example_json == ""


@pytest.mark.parametrize("problem", ["asset", "mapping", "source-kind", "unknown-use", "unknown-field", "command", "duplicate-key", "duplicate-asset-key", "too-large"])
def test_corrupt_or_unknown_package_cannot_become_review(preparation, problem):
    request, _, _ = preparation
    package = json.loads(request.package_path.read_text(encoding="utf-8"))
    if problem == "asset":
        asset = json.loads(package["runtime_asset_json"]); asset["eligible"][0]["statement"] += " changed"
        package["runtime_asset_json"] = canonical_json(asset)
    elif problem == "mapping": package["mapping"]["profile"]["identity_core"] = "changed"
    elif problem == "source-kind": package["source_declaration"]["origin_kind"] = "project-original"
    elif problem == "unknown-use": package["source_declaration"]["intended_use"] = "unreviewed-upload"
    elif problem == "unknown-field": package["activation"] = True
    elif problem == "command": package["freeze_request"] = dict(confirmed=True)
    elif problem == "duplicate-asset-key":
        package["runtime_asset_json"] = package["runtime_asset_json"].replace("{", '{"version":"unknown",', 1)
    rendered = canonical_json(package)
    if problem == "duplicate-key": rendered = rendered.replace("{", '{"status":"candidate",', 1)
    elif problem == "too-large": rendered = " " * 4_000_001
    request.package_path.write_text(rendered, encoding="utf-8")
    view = preview(request)
    assert view.status == "failed-closed" and not view.review_basis and not view.proposed_scope_json


def test_missing_package_and_invalid_request_have_distinct_status(preparation):
    request, _, _ = preparation
    assert preview(replace(request, package_path=request.package_path.with_name("missing.json"))).status == "unavailable"
    assert preview(replace(request, package_path=Path("relative.json"))).status == "rejected"
    assert preview(replace(request, expected_persona_digest="unknown")).status == "rejected"
    assert preview(dict(asdict(request))).status == "rejected"


def test_content_validation_preserves_confirmation_and_existing_signed_freeze_contract(preparation):
    request, definition, _ = preparation
    content = request.package_path.read_text(encoding="utf-8")
    unconfirmed = validate_character_preparation(content, request.expected_definition_basis)
    assert unconfirmed["source_declaration"]["rights_confirmed"] is False
    signed = prepare_reviewed_definition(ReviewedCharacterFreezeRequest(content, request.expected_definition_basis, True, True))
    assert signed == {**unconfirmed, "source_declaration": {**unconfirmed["source_declaration"], "rights_confirmed": True}}
    assert signed["runtime_asset"] == json.loads(definition.runtime_asset_json)
    with pytest.raises(ValueError, match="reviewed-character-confirmation-required"):
        prepare_reviewed_definition(ReviewedCharacterFreezeRequest(content, request.expected_definition_basis))
    # Existing freeze normalizes the confirmation only after its explicit command check.
    package = json.loads(content); package["source_declaration"]["rights_confirmed"] = "old-ignored-package-flag"
    assert prepare_reviewed_definition(ReviewedCharacterFreezeRequest(canonical_json(package), request.expected_definition_basis, True, True)) == signed


def test_source_and_package_confirmation_never_grant_new_use_or_change_review_basis(preparation):
    request, _, _ = preparation
    original = preview(request)
    package = json.loads(request.package_path.read_text(encoding="utf-8"))
    package["source_declaration"]["rights_confirmed"] = True
    package["confirmation_request"]["rights_confirmed"] = package["confirmation_request"]["confirmed"] = True
    request.package_path.write_text(canonical_json(package), encoding="utf-8")
    assert preview(request) == original


def test_new_scope_content_changes_independent_basis_not_existing_definition(preparation, monkeypatch):
    import dynamic_subject_agent.original_whole_use_preparation as preparation_module
    request, definition, _ = preparation
    old = preview(request)
    scope = preparation_module._scope()
    scope["input_fields"]["exchange"]["max_total_chars"] = 3999
    monkeypatch.setattr(preparation_module, "_scope", lambda: scope)
    changed = preview(request)
    assert changed.status == "previewed" and changed.review_basis != old.review_basis and changed.scope_digest != old.scope_digest
    assert changed.definition_basis == old.definition_basis == definition.definition_basis
    assert changed.runtime_asset_sha == old.runtime_asset_sha


def test_valid_new_personality_content_requires_new_expected_object_and_review_basis(preparation, personality_fixture):
    request, _, product = preparation
    original = preview(request)
    _, draft_path, _, _, _ = personality_fixture
    sidecar = draft_path.parent / "personality.json"
    source = json.loads(sidecar.read_text(encoding="utf-8"))
    source["items"][0]["limits"] += " 这次新的合成解释仍不证明新经历。"
    sidecar.write_text(canonical_json(source), encoding="utf-8")
    new_persona = sha256(sidecar.read_bytes()).hexdigest()
    changed_definition = product.application.preview_character_identity_preparation(
        CharacterDefinitionPreparationRequest("self", "start", sidecar, new_persona))
    assert changed_definition.status == "previewed"
    request.package_path.write_text(canonical_json(asdict(changed_definition)), encoding="utf-8")
    assert preview(request).status == "failed-closed"
    changed = preview(replace(request, expected_definition_basis=changed_definition.definition_basis,
        expected_runtime_asset_sha=changed_definition.runtime_asset_sha, expected_persona_digest=new_persona))
    assert changed.status == "previewed" and changed.review_basis != original.review_basis
    assert changed.selected_material_sha256 != original.selected_material_sha256
    assert changed.scope_digest == original.scope_digest


def test_review_is_not_a_gateway_task_or_a_legacy_remote_projection(preparation):
    from dynamic_subject_agent.model_gateway import ModelGateway, ModelGatewayFailure, ModelTask, ModelTaskKind
    from dynamic_subject_agent.reviewed_character_chat_provider import DeepSeekReviewedCharacterChatAdapter
    from dynamic_subject_agent.first_life_reply_drafts import draft_wire
    request, _, _ = preparation
    view = preview(request)
    def forbidden(*args, **kwargs): pytest.fail("review reached transport or credentials")
    gateway = ModelGateway(DeepSeekReviewedCharacterChatAdapter(transport=forbidden, credential_ref=forbidden))
    with pytest.raises(ModelGatewayFailure, match="typed-model-task-required"): gateway.execute(view)
    for kind in (ModelTaskKind.CHARACTER_COMMUNICATION_PLAN, ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION,
                 ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY):
        with pytest.raises(ModelGatewayFailure): gateway.execute(ModelTask(kind, view))
    with pytest.raises(ValueError): draft_wire(ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY, view))


def test_cli_defaults_to_summary_and_explicitly_exports_only_review(preparation, tmp_path):
    request, _, _ = preparation
    command = [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts/prepare_original_whole_use.py"),
        "--package", str(request.package_path), "--definition-basis", request.expected_definition_basis,
        "--asset-sha", request.expected_runtime_asset_sha, "--persona-digest", request.expected_persona_digest,
        "--subject", request.subject_id, "--anchor", request.anchor_id]
    completed = subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8")
    summary = json.loads(completed.stdout)
    assert summary["status"] == "previewed" and "proposed_scope_json" not in summary and "synthetic_example_json" not in summary
    output = tmp_path / "use-review.json"
    completed = subprocess.run([*command, "--output", str(output)], check=True, capture_output=True, text=True, encoding="utf-8")
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["review_basis"] == summary["review_basis"] and "runtime_asset_json" not in payload
    assert not payload["remote_use_authorized"] and not payload["execution_ready"]
    before = output.read_bytes()
    completed = subprocess.run([*command, "--output", str(output)], capture_output=True)
    assert completed.returncode != 0 and output.read_bytes() == before
