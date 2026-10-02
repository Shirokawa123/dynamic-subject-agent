from dataclasses import asdict, replace
import json

import pytest

from dynamic_subject_agent.original_whole_chat import (APPROVED_BINDING, whole_contract, digest, whole_publication_key,
    whole_projection, projection_for_contract, contract_variant, validate_whole_envelope)
from dynamic_subject_agent.original_whole_followup import select_followup_context
from dynamic_subject_agent.reviewed_character_chat import CharacterDialogueBasis, sealed_model
from dynamic_subject_agent.recent_dialogue import RecentDialogueTurn
from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
from test_original_whole_chat import whole_fixture, approved, personality_fixture, model_fixture, WholeTransport, send, history


def loaded_fixture(whole_fixture):
    opening, _, config, _ = whole_fixture
    opening().close()
    return LocalIdentityAuthority(config).load_active()


def test_baseline_contract_policy_key_and_projection_bytes_are_unchanged():
    # This metadata-only golden digest is the released S127 contract.
    original = whole_contract(APPROVED_BINDING)
    assert digest(original) == "764d47ab726959464aae403d809843f0ed624c07bc4bc1ff32016243d2c73731"
    assert whole_contract(APPROVED_BINDING, technical_variant="baseline") == original
    assert "technical_variant" not in original
    assert whole_publication_key(original) == "original-character-whole-" + APPROVED_BINDING["definition_basis"] + "-" + APPROVED_BINDING["scope_digest"]
    followup = whole_contract(APPROVED_BINDING, technical_variant="followup")
    assert followup["policy_sha"] == original["policy_sha"]
    assert whole_publication_key(followup) != whole_publication_key(original)
    assert len(whole_publication_key(followup)) <= 256


def test_candidate_recovers_only_recent_user_sealed_topic_and_preserves_scope(whole_fixture):
    loaded = loaded_fixture(whole_fixture)
    envelope, model = loaded.reviewed_definition, sealed_model(loaded.reviewed_definition)
    dialogue = CharacterDialogueBasis("available", True, (RecentDialogueTurn("你小时候怎么学画的？", "旧回复不能成为事实。"),))
    baseline = whole_projection(envelope, loaded.runtime_identity, "当时是什么样？", dialogue, True)
    candidate_contract = whole_contract({key: loaded.qri.reviewed_chat_contract[key] for key in APPROVED_BINDING}, technical_variant="followup")
    candidate = projection_for_contract(envelope, loaded.runtime_identity, "当时是什么样？", dialogue, True, candidate_contract)
    assert baseline.background["self_knowledge"] == ()
    assert len(candidate.background["self_knowledge"]) == 1
    assert candidate.background["self_knowledge"][0]["event_scope"] == "before"
    assert candidate.turn == baseline.turn and candidate.exchange == baseline.exchange
    assert candidate.background["character_core"] == baseline.background["character_core"]
    assert candidate.evidence == baseline.evidence
    context, reason, offset = select_followup_context(model, "当时是什么样？", dialogue, True)
    assert reason == "recovered-user-topic" and offset == 1
    # Different user topic gives different reviewed material, with its belief
    # type retained; assistant text cannot choose or manufacture either item.
    work = CharacterDialogueBasis("available", True, (RecentDialogueTurn("交稿时有什么压力？", "我昨天去过不存在的展览。"),))
    work_context, _, _ = select_followup_context(model, "为什么呢？", work, True)
    assert context.self_knowledge[-1] != work_context.self_knowledge[-1]
    assert work_context.self_knowledge[-1].kind == "belief"


def test_current_topic_topic_boundary_history_off_and_assistant_invention_do_not_leak_old_material(whole_fixture):
    model = sealed_model(loaded_fixture(whole_fixture).reviewed_definition)
    old = RecentDialogueTurn("你小时候怎么学画的？", "旧回复。")
    dialogue = CharacterDialogueBasis("available", True, (old, RecentDialogueTurn("换个话题，蓝色和绿色呢？", "我去过展览。")))
    context, reason, _ = select_followup_context(model, "当时呢？", dialogue, True)
    assert len(context.self_knowledge) == 1 and reason == "history-topic-boundary"
    current, reason, _ = select_followup_context(model, "交稿时有什么压力？", CharacterDialogueBasis("available", True, (old,)), True)
    assert reason == "current-related-preferred" and current.self_knowledge[-1].kind == "belief"
    unrelated, reason, _ = select_followup_context(model, "蓝色和绿色呢？", CharacterDialogueBasis("available", True, (old,)), True)
    assert reason == "not-a-bounded-followup" and len(unrelated.self_knowledge) == 1
    off, reason, _ = select_followup_context(model, "为什么呢？", CharacterDialogueBasis("available", True), False)
    assert reason == "history-not-used" and len(off.self_knowledge) == 1
    assistant_only = CharacterDialogueBasis("available", True, (RecentDialogueTurn("你好。", "小时候母亲教我画画，还去过展览。"),))
    nothing, reason, _ = select_followup_context(model, "为什么呢？", assistant_only, True)
    assert reason == "no-sealed-user-topic" and len(nothing.self_knowledge) == 1


def test_followup_facade_sender_reconstructs_selection_off_on_and_reopen(whole_fixture):
    opening, _, _, _ = whole_fixture
    transport = WholeTransport()
    product = opening(transport, technical_variant="followup")
    assert not transport.calls
    assert send(product, "你小时候怎么学画的？", "first").status == "terminal"
    assert send(product, "当时是什么样？", "followup").status == "terminal"
    payload = json.loads(transport.calls[1]["messages"][1]["content"])
    assert payload["turn"]["current_message"] == "当时是什么样？" and len(payload["background"]["self_knowledge"]) == 1
    assert set(payload) == {"turn", "background", "exchange", "evidence"}
    assert send(product, "换个话题，蓝色和绿色呢？", "new-topic").status == "terminal"
    assert send(product, "当时呢？", "new-followup").status == "terminal"
    assert json.loads(transport.calls[-1]["messages"][1]["content"])["background"]["self_knowledge"] == []
    assert product.application.set_reviewed_character_history(False).history_enabled is False
    assert send(product, "为什么呢？", "off").status == "terminal"
    assert json.loads(transport.calls[-1]["messages"][1]["content"])["exchange"] == []
    saved = history(product)
    product.close()
    transport2 = WholeTransport()
    reopened = opening(transport2, technical_variant="followup")
    assert history(reopened) == saved and not transport2.calls
    assert reopened.application.set_reviewed_character_history(True).history_enabled is True
    assert send(reopened, "你小时候怎么学画的？", "restored-topic").status == "terminal"
    assert send(reopened, "为什么呢？", "restored-followup").status == "terminal"
    assert len(json.loads(transport2.calls[-1]["messages"][1]["content"])["background"]["self_knowledge"]) == 1


def test_explicit_topic_boundary_with_old_cues_cannot_restore_that_old_topic(whole_fixture):
    opening, _, _, _ = whole_fixture
    transport = WholeTransport()
    product = opening(transport, technical_variant="followup")
    assert send(product, "你小时候怎么学画的？", "boundary-first").status == "terminal"
    boundary = "换个话题，先说蓝色，不是继续说小时候怎么学画的。"
    assert send(product, boundary, "boundary-second").status == "terminal"
    assert send(product, "为什么呢？", "boundary-followup").status == "terminal"
    payload = json.loads(transport.calls[-1]["messages"][1]["content"])
    assert payload["background"]["self_knowledge"] == []
    assert payload["turn"]["current_message"] == "为什么呢？" and len(payload["exchange"]) == 2
    # Both the boundary sentence and its mentioned old cues are real canonical
    # input, but they do not authorize reusing that old query for this followup.
    assert payload["exchange"][-1]["user_text"] == boundary


def test_variants_share_existing_audit_but_cannot_replace_bound_baseline_root(whole_fixture, tmp_path):
    opening, options, config, request = whole_fixture
    baseline = opening()
    assert send(baseline, "你好。", "baseline").status == "terminal"
    baseline.close()
    before = config.state_path.read_bytes()
    with pytest.raises(RuntimeError, match="activation-conflict"):
        opening(technical_variant="followup")
    assert config.state_path.read_bytes() == before
    from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product, open_original_whole_product
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    from dynamic_subject_agent.source_character_authoring import LocalIdentitySelectRequest
    candidate_config = LocalProductConfig(tmp_path / "candidate" / "DynamicSubjectAgent/m0/experiments", tmp_path / "candidate" / "state.json")
    with open_local_product(candidate_config, cognition=DormantDeepSeekCognition()) as author:
        frozen = author.application.freeze_source_identity(request)
        assert frozen.status == "created"
        assert author.application.select_local_identity(LocalIdentitySelectRequest(frozen.view.identity_id, True)).status == "selected"
    with open_original_whole_product(candidate_config, **options, technical_variant="followup", _transport=WholeTransport()) as candidate:
        assert history(candidate) == () and candidate.application.reviewed_character_chat_status().budget_used == 1
        assert send(candidate, "你好。", "candidate").status == "terminal"
        assert candidate.application.reviewed_character_chat_status().budget_used == 2
    with opening() as restored:
        assert restored.application.reviewed_character_chat_status().budget_used == 2 and len(history(restored)) == 1


def test_unknown_or_tampered_selector_witness_is_rejected(whole_fixture):
    opening, options, config, _ = whole_fixture
    before = config.state_path.read_bytes()
    with pytest.raises(ValueError):
        opening(technical_variant="arbitrary-query-function")
    assert config.state_path.read_bytes() == before and not options["audit_path"].exists()
    loaded = loaded_fixture(whole_fixture)
    binding = {key: loaded.qri.reviewed_chat_contract[key] for key in APPROVED_BINDING}
    candidate = whole_contract(binding, technical_variant="followup")
    candidate["technical_variant"]["selector_digest"] = "0" * 64
    with pytest.raises(ValueError):
        validate_whole_envelope(loaded.reviewed_definition, candidate)


def test_baseline_sender_cannot_send_candidate_selected_material_even_with_matching_ticket(whole_fixture):
    loaded = loaded_fixture(whole_fixture)
    _, options, config, _ = whole_fixture
    from dynamic_subject_agent.original_whole_chat_audit import OriginalWholeDelivery, open_original_whole_audit
    from dynamic_subject_agent.original_whole_chat_provider import DeepSeekOriginalWholeAdapter
    from dynamic_subject_agent.model_gateway import ModelGateway, ModelTask, ModelTaskKind, ModelGatewayFailure
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID
    binding = {key: loaded.qri.reviewed_chat_contract[key] for key in APPROVED_BINDING}
    dialogue = CharacterDialogueBasis("available", True, (RecentDialogueTurn("你小时候怎么学画的？", "合成回复。"),))
    candidate = projection_for_contract(loaded.reviewed_definition, loaded.runtime_identity, "当时呢？", dialogue, True,
        whole_contract(binding, technical_variant="followup"))
    delivery = OriginalWholeDelivery(open_original_whole_audit(options["audit_path"]), contract=loaded.qri.reviewed_chat_contract,
        state_path=config.state_path)
    transport = WholeTransport()
    gateway = ModelGateway(DeepSeekOriginalWholeAdapter(transport=transport, delivery=delivery, envelope=loaded.reviewed_definition,
        credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID)))
    delivery.claim("e" * 64, "f" * 64, digest(asdict(candidate)))
    with pytest.raises(ModelGatewayFailure):
        gateway.execute(ModelTask(ModelTaskKind.CHARACTER_ORIGINAL_WHOLE_REPLY, candidate))
    delivery.record("failed-closed")
    assert not transport.calls and delivery.counts() == (None, 1, None)


@pytest.mark.parametrize("fault,code", [("empty", "response-content-empty"), ("json", "response-content-json")])
def test_known_content_failure_stays_precise_and_never_retries(whole_fixture, fault, code):
    opening, _, _, _ = whole_fixture
    transport, rows = WholeTransport(fault=fault), []
    product = opening(transport, rows, technical_variant="followup")
    result = send(product, "普通合成问题。", "content-failure")
    assert result.status == "failed-closed" and result.projection.failure_code == "original-whole-" + code
    assert rows[-1]["error_code"] == code and len(transport.calls) == 1
    assert send(product, "普通合成问题。", "content-failure").projection.failure_code == result.projection.failure_code
    assert len(transport.calls) == 1 and not history(product)


def test_unknown_gateway_failure_never_exposes_arbitrary_code(whole_fixture, monkeypatch):
    opening, _, _, _ = whole_fixture
    from dynamic_subject_agent.original_whole_chat_provider import DeepSeekOriginalWholeAdapter
    from dynamic_subject_agent.model_gateway import ModelGatewayFailure
    def unknown(self, task):
        self.delivery.consume(task)
        raise ModelGatewayFailure("PRIVATE_UNKNOWN_PROVIDER_DETAIL")
    monkeypatch.setattr(DeepSeekOriginalWholeAdapter, "invoke", unknown)
    product = opening(technical_variant="followup")
    result = send(product, "普通合成问题。", "unknown-code")
    assert result.status == "failed-closed" and result.projection.failure_code == "original-whole-provider-failed"


def test_immutable_legacy_candidate_allows_receipt_reads_but_never_new_activation_or_sender(whole_fixture, monkeypatch):
    opening, options, config, _ = whole_fixture
    import dynamic_subject_agent.original_whole_chat as whole_module
    import dynamic_subject_agent.original_whole_followup as selection_module
    from dynamic_subject_agent.local_product import open_local_product
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    # Emulate the pre-fix binary with a synthetic approved object; all frozen
    # data and Publications are produced through the normal Interfaces.
    with monkeypatch.context() as old_binary:
        old_binary.setattr(selection_module, "SELECTOR_VERSION", whole_module.LEGACY_FOLLOWUP_WITNESS["selector_version"])
        old_binary.setattr(selection_module, "selector_digest", lambda: "096496df339ea4eb730c66e3e6d34ec7403a68155dc64473b8729cdd0b51dfd5")
        old_binary.setattr(whole_module, "LEGACY_FOLLOWUP_WITNESS", {})
        product = opening(technical_variant="followup")
        original = send(product, "普通合成问题。", "legacy-complete")
        assert original.status == "terminal"
        saved = history(product)
        product.close()
    before = config.state_path.read_bytes()
    loaded = LocalIdentityAuthority(config).load_active()
    assert contract_variant(loaded.qri.reviewed_chat_contract) == "followup-legacy"
    with open_local_product(config, cognition=DormantDeepSeekCognition()) as receipts:
        assert history(receipts) == saved
        assert receipts.application.follow(original.operation_ref).projection.expression_text == original.projection.expression_text
        from dynamic_subject_agent.application import SubjectRequestLookupRequest
        from dynamic_subject_agent.timeline import SubjectCommand
        command = SubjectCommand.contribute_utterance(target_profile_id=receipts.profile_id, target_timeline_id=receipts.timeline_id,
            declared_intent="ask-collaborator-status", utterance="普通合成问题。", language="zh", provenance="project-original")
        lookup = receipts.application.lookup_subject_request(SubjectRequestLookupRequest(command, "original-whole-test-legacy-complete"))
        assert lookup.query_status == "found" and lookup.operation.projection.expression_text == original.projection.expression_text
        from dynamic_subject_agent.whole_message_scope import WholeMessageScopePreviewRequest
        preview = receipts.application.preview_whole_message_scope(WholeMessageScopePreviewRequest(receipts.profile_id, receipts.timeline_id, "旧候选只读结果。"))
        assert preview.status == "unavailable" and preview.problem_code == "whole-scope-receipt-only" and preview.character_core == ()
        from dynamic_subject_agent.whole_chat_archive import WholeChatArchiveRequest
        archive = receipts.application.query_whole_chat_archive(WholeChatArchiveRequest(receipts.profile_id, receipts.timeline_id))
        assert archive.status == "available" and len(archive.rows) == 1 and archive.rows[0].assistant_text == original.projection.expression_text
        rejected = send(receipts, "新输入不得启旧候选。", "legacy-new")
        assert rejected.status == "unavailable" and rejected.operation_ref is None
        assert receipts.application.set_reviewed_character_history(False).status == "unavailable"
    assert config.state_path.read_bytes() == before
    with pytest.raises(RuntimeError, match="legacy-live-unavailable"):
        opening(technical_variant="followup")
    with pytest.raises(ValueError):
        opening(technical_variant="followup-legacy")
    assert config.state_path.read_bytes() == before
    # The known witness is accepted only when rebuilding the prior policy
    # question; a fresh policy decision cannot qualify that legacy sender.
    from dynamic_subject_agent.studio import SubjectStudio, PolicyKernel, CapabilityManifest
    studio = SubjectStudio.open(loaded.studio_location, policy_kernel=PolicyKernel())
    try:
        snapshot = studio.query_snapshot(loaded.qri.genesis_snapshot_id)
        denied = studio.decide_policy(snapshot.draft_id, CapabilityManifest.original_whole_chat(),
            reviewed_chat_contract=loaded.qri.reviewed_chat_contract)
        assert denied.disposition.value == "denied"
        assert studio.query_qri(publication_key=loaded.qri.publication_key) == loaded.qri
    finally:
        studio.close()
    from dynamic_subject_agent.original_whole_chat_audit import OriginalWholeDelivery, open_original_whole_audit
    from dynamic_subject_agent.original_whole_chat_provider import DeepSeekOriginalWholeAdapter
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID
    transport = WholeTransport()
    delivery = OriginalWholeDelivery(open_original_whole_audit(options["audit_path"]), contract=loaded.qri.reviewed_chat_contract,
        state_path=config.state_path)
    with pytest.raises(ValueError, match="receipt-only"):
        DeepSeekOriginalWholeAdapter(transport=transport, delivery=delivery, envelope=loaded.reviewed_definition,
            credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID))
    assert not transport.calls and delivery.counts() == (None, 1, None)
