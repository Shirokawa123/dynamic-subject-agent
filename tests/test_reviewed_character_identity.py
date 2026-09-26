from dataclasses import asdict, replace
from hashlib import sha256
import json

import pytest

from dynamic_subject_agent.character_identity_preparation import CharacterDefinitionPreparationRequest
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product, open_deepseek_local_product
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest, REVIEWED_CHARACTER_AUTHORITY
from dynamic_subject_agent.source_character_authoring import LocalIdentitySelectRequest
from dynamic_subject_agent.studio import SubjectStudio, PolicyKernel
from test_character_evidence_model import model_fixture
from test_character_personality import personality_fixture


@pytest.fixture
def approved(personality_fixture, tmp_path):
    _, _, _, _, open_lab = personality_fixture
    product, _, _, sidecar = open_lab(preview_only=True)
    view = product.application.preview_character_identity_preparation(CharacterDefinitionPreparationRequest(
        "self", "start", sidecar, sha256(sidecar.read_bytes()).hexdigest()))
    assert view.status == "previewed"
    request = ReviewedCharacterFreezeRequest(canonical_json(asdict(view)), view.definition_basis, True, True)
    config = LocalProductConfig(tmp_path / "sealed" / "m0" / "experiments", tmp_path / "sealed" / "state.json")
    opened = open_local_product(config, cognition=DormantDeepSeekCognition())
    yield opened, config, request, view
    opened.close()


def test_complete_definition_seals_replays_selects_and_restores_without_source(approved, personality_fixture):
    product, config, request, view = approved
    result = product.application.freeze_source_identity(request)
    assert result.status == "created", result
    assert result.view.identity_id != view.mapping.profile.profile_id
    assert result.view.freeze_basis_digest == view.definition_basis
    replay = product.application.freeze_source_identity(request)
    assert replay.status == "replayed" and replay.view == result.view
    selected = product.application.select_local_identity(LocalIdentitySelectRequest(result.view.identity_id, True))
    assert selected.status == "selected", selected
    product.close()
    _, path, book, _, _ = personality_fixture
    path.unlink(); book.unlink()
    with open_local_product(config, cognition=DormantDeepSeekCognition()) as restored:
        state = json.loads(config.state_path.read_text(encoding="utf-8"))
        record = next(r for r in state["identities"] if r["identity_id"] == result.view.identity_id)
        from dynamic_subject_agent.studio import StudioRootRef
        studio = SubjectStudio.open(StudioRootRef.from_dict(record["studio_location"]), policy_kernel=PolicyKernel())
        try:
            qri = studio.query_qri(publication_key=restored.publication_key)
            assert qri.provider_authority == REVIEWED_CHARACTER_AUTHORITY
            snapshot = studio.query_snapshot(qri.genesis_snapshot_id)
            assert snapshot.reviewed_definition["runtime_asset"] == json.loads(view.runtime_asset_json)
            assert snapshot.reviewed_definition["source_declaration"]["rights_confirmed"] is True
            assert view.source_declaration.rights_confirmed is False
            assert not studio.knowledge_entries(snapshot.knowledge_snapshot_id)
            assert qri.isolation_proof.provenance_class == "private-reviewed-fiction-derived"
        finally:
            studio.close()
        from dynamic_subject_agent.timeline import SubjectCommand
        rejected = restored.application.submit(SubjectCommand.contribute_utterance(target_profile_id=restored.profile_id,
            target_timeline_id=restored.timeline_id, declared_intent="ask-collaborator-status", utterance="你好",
            language="zh", provenance="project-original"), idempotency_key="dormant-no-chat")
        assert rejected.operation_ref is None and rejected.problem.code == "reviewed-character-chat-unavailable"
    from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
    from dynamic_subject_agent.host import RuntimeHost, RUNTIME_CONTRACT_VERSION
    from dynamic_subject_agent.reviewed_character_cognition import ReviewedCharacterDormantCognition
    loaded = LocalIdentityAuthority(config).load_active()
    host = RuntimeHost.open(loaded.host_location, studio_location=loaded.studio_location,
        cognition=ReviewedCharacterDormantCognition())
    try:
        assert host.query_binding(profile_id=loaded.qri.profile_id, timeline_id=loaded.timeline_id).runtime_contract_version == RUNTIME_CONTRACT_VERSION
    finally: host.close()
    with pytest.raises(RuntimeError, match="legacy-provider-denied"):
        open_deepseek_local_product(config, api_key="synthetic-unused-key")


@pytest.mark.parametrize("field", ["confirmed", "rights_confirmed", "definition_basis", "asset", "source", "mapping"])
def test_invalid_confirmation_or_content_has_no_writes(approved, field):
    product, config, request, _ = approved
    before = {str(p): p.read_bytes() for p in config.state_path.parent.rglob("*") if p.is_file()}
    if field in ("confirmed", "rights_confirmed"):
        request = replace(request, **{field: False})
    elif field == "definition_basis": request = replace(request, definition_basis="0" * 64)
    else:
        data = json.loads(request.preparation_json)
        if field == "asset":
            asset = json.loads(data["runtime_asset_json"]); asset["eligible"][0]["statement"] = "changed"
            data["runtime_asset_json"] = canonical_json(asset)
        elif field == "source": data["source_declaration"]["origin_kind"] = "project-original"
        else: data["mapping"]["profile"]["identity_core"] = "changed"
        request = replace(request, preparation_json=canonical_json(data))
    assert product.application.freeze_source_identity(request).status == "rejected"
    assert before == {str(p): p.read_bytes() for p in config.state_path.parent.rglob("*") if p.is_file()}


@pytest.mark.parametrize("problem", ["source-sha", "source-shape", "persona-sha", "empty-id", "duplicate-id", "dimension", "derivation",
    "organization", "empty-core", "foreign-organization-ref", "duplicate-organization-ref", "revision-bool", "persona-id", "belief-bool",
    "different-statement", "different-name", "different-stage"])
def test_recomputed_hash_does_not_authorize_bad_schema_or_runtime_mapping_disagreement(approved, problem):
    from dynamic_subject_agent.character_identity_preparation import CharacterSourceDeclaration, _complete_definition_basis
    product, config, request, _ = approved
    data = json.loads(request.preparation_json); asset = json.loads(data["runtime_asset_json"])
    if problem == "source-sha": data["source_declaration"]["reviewed_digest"] = "not-a-digest"
    elif problem == "source-shape": data["source_declaration"].pop("origin_kind")
    elif problem == "persona-sha": asset["persona_digest"] = "not-a-digest"
    elif problem == "empty-id": asset["eligible"][0]["item_id"] = ""
    elif problem == "duplicate-id": asset["eligible"].append(asset["eligible"][0])
    elif problem in ("dimension", "derivation"): asset["eligible"][0][problem] = 23
    elif problem == "organization": asset["chat_organization"] = 3
    elif problem == "empty-core": asset["chat_organization"]["core"] = []
    elif problem == "foreign-organization-ref": asset["chat_organization"]["core"][0]["claim_ids"] = ["unknown"]
    elif problem == "duplicate-organization-ref": asset["chat_organization"]["core"][0]["claim_ids"] *= 2
    elif problem == "revision-bool": data["proposed_draft"]["revision"] = True
    elif problem == "persona-id": asset["personality"][0]["claim_ids"] = ["a"]
    elif problem == "belief-bool": asset["personality"][0]["support_includes_belief"] = 1
    elif problem == "different-statement": asset["eligible"][0]["statement"] = "合法字符串却不同于显示的映射。"
    elif problem == "different-name": asset["subject"]["name"] = "另一个显示名称"
    else: asset["initial_stage"] = "一个不同的起点"
    data["runtime_asset_json"] = canonical_json(asset)
    data["runtime_asset_sha"] = sha256(data["runtime_asset_json"].encode()).hexdigest()
    data["definition_basis"] = _complete_definition_basis(data["provisional_basis"], CharacterSourceDeclaration(**data["source_declaration"]),
        data["runtime_asset_sha"], asset["persona_digest"])
    before = config.state_path.read_bytes()
    modified = replace(request, preparation_json=canonical_json(data), definition_basis=data["definition_basis"])
    assert product.application.freeze_source_identity(modified).status == "rejected"
    assert config.state_path.read_bytes() == before


@pytest.mark.parametrize("point", ["publication", "registry"])
def test_interruption_recovers_same_sealed_asset_without_duplicate_identity(approved, monkeypatch, point):
    import dynamic_subject_agent.local_identity_authority as authority
    product, config, request, _ = approved
    target, name = (SubjectStudio, "publish") if point == "publication" else (authority, "_write_state")
    original = getattr(target, name)
    def interrupted(*args, **kwargs): raise OSError("synthetic interruption")
    monkeypatch.setattr(target, name, interrupted)
    assert product.application.freeze_source_identity(request).status == "failed-closed"
    monkeypatch.setattr(target, name, original)
    recovered = product.application.freeze_source_identity(request)
    assert recovered.status in ("created", "replayed"), recovered
    assert product.application.freeze_source_identity(request).status == "replayed"
    assert len(json.loads(config.state_path.read_text(encoding="utf-8"))["identities"]) == 2


@pytest.mark.parametrize("part", ["asset", "source-refs", "qri-authority", "registry-pointer"])
def test_tampered_definition_source_qri_or_registry_fails_closed_before_select_or_replay(approved, part):
    import sqlite3
    from dynamic_subject_agent.studio import StudioRootRef
    product, config, request, _ = approved
    result = product.application.freeze_source_identity(request); assert result.status == "created"
    state = json.loads(config.state_path.read_text(encoding="utf-8")); record = state["identities"][-1]
    location = StudioRootRef.from_dict(record["studio_location"])
    if part == "registry-pointer":
        record["runtime_asset_sha"] = "0" * 64
        config.state_path.write_text(canonical_json(state), encoding="utf-8")
    else:
        db = sqlite3.connect(location.profile_database, autocommit=True)
        try:
            if part == "asset":
                raw = json.loads(db.execute("SELECT snapshot_json FROM genesis_snapshot").fetchone()[0])
                raw["reviewed_definition"]["runtime_asset"]["personality"][0]["limits"] = "changed"
                db.execute("UPDATE genesis_snapshot SET snapshot_json=?,snapshot_digest=?", (canonical_json(raw), sha256(canonical_json(raw).encode()).hexdigest()))
            elif part == "source-refs":
                raw = json.loads(db.execute("SELECT profile_json FROM participant_profile").fetchone()[0])
                raw["source"]["source_asset_refs"][1] = "runtime-asset:" + "0" * 64
                db.execute("UPDATE participant_profile SET profile_json=?,profile_digest=?", (canonical_json(raw), sha256(canonical_json(raw).encode()).hexdigest()))
            else:
                raw = json.loads(db.execute("SELECT qri_json FROM qri_publication").fetchone()[0])
                raw["provider_authority"] = "deepseek-v4-flash-experimental"
                body = dict(raw); body.pop("integrity_digest"); raw["integrity_digest"] = sha256(canonical_json(body).encode()).hexdigest()
                db.execute("UPDATE qri_publication SET qri_json=?,integrity_digest=?", (canonical_json(raw), raw["integrity_digest"]))
        finally: db.close()
    assert product.application.local_identities().status == "failed-closed"
    assert product.application.select_local_identity(LocalIdentitySelectRequest(result.view.identity_id, True)).status == "failed-closed"
    assert product.application.freeze_source_identity(request).status == "failed-closed"


def test_valid_foreign_product_root_cannot_replace_local_reviewed_pointer(approved, tmp_path):
    product, config, request, _ = approved
    result = product.application.freeze_source_identity(request); assert result.status == "created"
    foreign = LocalProductConfig(tmp_path / "foreign" / "m0" / "experiments", tmp_path / "foreign" / "state.json")
    with open_local_product(foreign, cognition=DormantDeepSeekCognition()) as other:
        assert other.application.freeze_source_identity(request).status == "created"
    state = json.loads(config.state_path.read_text(encoding="utf-8"))
    state["identities"][-1] = json.loads(foreign.state_path.read_text(encoding="utf-8"))["identities"][-1]
    config.state_path.write_text(canonical_json(state), encoding="utf-8")
    assert product.application.local_identities().status == "failed-closed"
    assert product.application.freeze_source_identity(request).status == "failed-closed"
    assert product.application.select_local_identity(LocalIdentitySelectRequest(result.view.identity_id, True)).status == "failed-closed"
    state["active_identity_id"] = result.view.identity_id
    config.state_path.write_text(canonical_json(state), encoding="utf-8")
    product.close()
    with pytest.raises(RuntimeError, match="reviewed-local-identity-authority-mismatch"):
        open_local_product(config, cognition=DormantDeepSeekCognition())


def test_thirty_items_eight_mapping_groups_and_four_interpretations_remain_complete_asset(personality_fixture, tmp_path):
    from dynamic_subject_agent.character_evidence_model import DIMENSIONS
    draft, _, _, data, open_lab = personality_fixture
    def add_items(value):
        template = value["assertions"][0]
        dimensions = [dimension for dimension in DIMENSIONS if dimension != "identity"]
        value["assertions"].extend(dict(template, id=f"extra-{i}", dimension=dimensions[i % len(dimensions)],
            statement=f"第{i}条有限认识，只适用于那一次。") for i in range(27))
    items = [dict(data["items"][0], id=f"interpretation-{i}") for i in range(4)]
    preview, _, _, sidecar = open_lab(source_changes=add_items, overrides=dict(items=items), preview_only=True)
    view = preview.application.preview_character_identity_preparation(CharacterDefinitionPreparationRequest("self", "start", sidecar,
        sha256(sidecar.read_bytes()).hexdigest()))
    assert view.status == "previewed" and len(view.mapping.knowledge_members) == 8
    config = LocalProductConfig(tmp_path / "thirty" / "m0" / "experiments", tmp_path / "thirty" / "state.json")
    with open_local_product(config, cognition=DormantDeepSeekCognition()) as product:
        response = product.application.freeze_source_identity(ReviewedCharacterFreezeRequest(canonical_json(asdict(view)), view.definition_basis, True, True))
        assert response.status == "created", response
    from dynamic_subject_agent.studio import StudioRootRef
    record = json.loads(config.state_path.read_text(encoding="utf-8"))["identities"][-1]
    studio = SubjectStudio.open(StudioRootRef.from_dict(record["studio_location"]), policy_kernel=PolicyKernel())
    try:
        qri = studio.query_qri(publication_key=record["publication_key"])
        asset = studio.query_snapshot(qri.genesis_snapshot_id).reviewed_definition["runtime_asset"]
        assert len(asset["eligible"]) == 30 and len(asset["personality"]) == 4
        assert {item["statement"] for item in asset["eligible"]} == {item["statement"] for item in draft["assertions"] if item["knowledge_time"] != "after"}
        assert len(studio.knowledge_entries(qri.knowledge_snapshot_id)) == 0
        assert all(item["basis"] == "author-interpretation" for item in asset["personality"])
    finally: studio.close()
