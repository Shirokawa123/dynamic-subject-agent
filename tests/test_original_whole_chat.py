from dataclasses import asdict, replace
from copy import deepcopy
from hashlib import sha256
import json
import sqlite3

import pytest

from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.local_product import open_original_whole_product, open_reviewed_character_chat_product
from dynamic_subject_agent.original_whole_chat import WHOLE_AUTHORITY
from dynamic_subject_agent.source_character_authoring import LocalIdentitySelectRequest
from dynamic_subject_agent.timeline import SubjectCommand, TimelineEngine, FaultPoint
from test_character_evidence_model import model_fixture
from test_character_personality import personality_fixture
from test_reviewed_character_identity import approved


class WholeTransport(DeepSeekTransport):
    def __init__(self, *, fault=None, callback=None, reply="合成单阶段回复。"):
        self.calls, self.fault, self.callback, self.reply = [], fault, callback, reply

    def post_json(self, **kwargs):
        body = json.loads(kwargs["body"])
        self.calls.append(body)
        if self.callback:
            self.callback()
        if self.fault == "timeout":
            raise TimeoutError("RAW_PRIVATE_DETAIL")
        value = dict(reply_text=self.reply, language="zh")
        if self.fault == "schema":
            value["use_life"] = False
        return DeepSeekHttpResponse(200, canonical_json(dict(model="deepseek-flash",
            choices=[dict(finish_reason="stop", message=dict(role="assistant", content=canonical_json(value), reasoning_content="RAW_PRIVATE_REASONING"))],
            usage=dict(prompt_tokens=100, completion_tokens=20, total_tokens=120))).encode())


@pytest.fixture
def whole_fixture(approved, monkeypatch, tmp_path):
    product, config, request, view = approved
    result = product.application.freeze_source_identity(request)
    assert result.status == "created"
    assert product.application.select_local_identity(LocalIdentitySelectRequest(result.view.identity_id, True)).status == "selected"
    product.close()
    asset = json.loads(view.runtime_asset_json)
    # Synthetic test object substitution is local to this fixture, never a production approval.
    import dynamic_subject_agent.original_whole_chat as contract_module
    binding = dict(definition_basis=view.definition_basis, runtime_asset_sha=view.runtime_asset_sha,
        persona_digest=asset["persona_digest"], review_basis="1" * 64, scope_digest="2" * 64,
        subject_id=asset["subject"]["subject_id"], anchor_id=asset["anchor"]["anchor_id"])
    monkeypatch.setattr(contract_module, "APPROVED_BINDING", binding)
    options = {key: binding[key] for key in ("definition_basis", "runtime_asset_sha", "persona_digest", "review_basis", "scope_digest")}
    options["audit_path"] = tmp_path / "whole-audit"
    opened = []
    def opening(transport=None, observations=None, **overrides):
        result = open_original_whole_product(config, **{**options, **overrides}, _transport=transport or WholeTransport(), observations=observations)
        opened.append(result)
        return result
    yield opening, options, config, request
    for product in opened:
        product.close()


def send(product, message, key):
    result = product.application.submit(SubjectCommand.contribute_utterance(target_profile_id=product.profile_id,
        target_timeline_id=product.timeline_id, declared_intent="ask-collaborator-status", utterance=message,
        language="zh", provenance="project-original"), idempotency_key="original-whole-test-" + key)
    if result.status == "pending":
        result = product.application.wait(result.operation_ref, timeout_seconds=30)
    return result


def history(product):
    result = product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY, product.profile_id, product.timeline_id))
    assert result.status == "available"
    return result.projection.turns


def test_facade_one_stage_minimal_projection_noop_reopen_history_and_metadata(whole_fixture):
    opening, options, config, _ = whole_fixture
    transport, observations = WholeTransport(), []
    product = opening(transport, observations)
    assert not transport.calls
    assert product.application.reviewed_character_chat_status().budget_used == 0
    first = send(product, "先聊画画。", "one")
    assert first.status == "terminal", first
    assert first.projection.living_memory_status == "no-op"
    assert first.projection.relationship_event is None
    assert first.projection.committed_effect_count == 0
    assert len(transport.calls) == 1
    assert send(product, "接着说。", "two").status == "terminal"
    payload = json.loads(transport.calls[1]["messages"][1]["content"])
    assert set(payload) == {"turn", "background", "exchange", "evidence"}
    assert payload["exchange"] == [dict(user_text="先聊画画。", assistant_text="合成单阶段回复。")]
    assert payload["evidence"] == dict(current_activity=None, current_plan=None, related_event=None)
    assert set(payload["background"]["runtime_identity"]) == {"subject_name", "subject_identity", "canon_start"}
    for secret in ("item_id", "claim_ids", "evidence_ids", "persona_digest", "source_declaration", "RAW_PRIVATE"):
        assert secret not in canonical_json(payload)
    assert transport.calls[0]["reasoning_effort"] == "high" and transport.calls[0]["max_tokens"] == 4096
    assert not any(key in canonical_json(observations) for key in ("先聊", "合成单阶段", "RAW_PRIVATE", "final_content", "payload"))
    assert observations[0]["usage"]["total_tokens"] == 120
    assert observations[0]["purpose"] == "original-character-whole-chat" and observations[0]["status"] == "complete"
    saved = history(product)
    product.close()
    second = WholeTransport()
    restarted = opening(second)
    assert history(restarted) == saved and not second.calls
    assert send(restarted, "先聊画画。", "one").replayed and not second.calls
    assert restarted.application.set_reviewed_character_history(False).history_enabled is False
    assert send(restarted, "换个话题。", "three").status == "terminal"
    projection = json.loads(second.calls[0]["messages"][1]["content"])
    assert projection["exchange"] == [] and projection["turn"]["has_prior_committed_exchange"]
    assert restarted.application.set_reviewed_character_history(True).history_enabled is True
    assert send(restarted, "继续吧。", "four").status == "terminal"
    assert len(json.loads(second.calls[1]["messages"][1]["content"])["exchange"]) == 2
    from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
    restarted.close()
    loaded = LocalIdentityAuthority(config).load_active()
    assert loaded.qri.provider_authority == WHOLE_AUTHORITY and loaded.qri.first_life_contract is None


@pytest.mark.parametrize("field", ["definition_basis", "runtime_asset_sha", "persona_digest", "review_basis", "scope_digest"])
def test_stale_approval_rejected_before_audit_or_registry_mutation(whole_fixture, field):
    opening, options, config, _ = whole_fixture
    before = config.state_path.read_bytes()
    with pytest.raises(ValueError):
        opening(**{field: "0" * 64})
    assert config.state_path.read_bytes() == before and not options["audit_path"].exists()


def test_old_two_stage_qualification_cannot_switch_to_whole(whole_fixture):
    _, options, config, _ = whole_fixture
    from dynamic_subject_agent.reviewed_character_chat import continuity_scope
    scope = sha256(canonical_json(continuity_scope(options["definition_basis"])).encode()).hexdigest()
    review = sha256(canonical_json(dict(definition_basis=options["definition_basis"], scope_digest=scope)).encode()).hexdigest()
    with open_reviewed_character_chat_product(config, definition_basis=options["definition_basis"], scope_digest=scope,
        review_request_basis=review, budget_path=options["audit_path"].with_name("old-budget"), _transport=WholeTransport()):
        pass
    with pytest.raises(RuntimeError, match="predecessor-invalid"):
        open_original_whole_product(config, **options, _transport=WholeTransport())
    assert not options["audit_path"].exists()


@pytest.mark.parametrize("fault,status", [("timeout", "unknown"), ("schema", "failed-closed")])
def test_failed_model_is_counted_once_terminal_and_never_retried(whole_fixture, fault, status):
    opening, _, _, _ = whole_fixture
    transport = WholeTransport(fault=fault)
    product = opening(transport)
    result = send(product, "当前合成问题。", "failed")
    assert result.status == status and len(transport.calls) == 1, result
    assert history(product) == ()
    assert send(product, "当前合成问题。", "failed").status == status and len(transport.calls) == 1
    product.close()
    restarted_transport = WholeTransport()
    restarted = opening(restarted_transport)
    assert send(restarted, "当前合成问题。", "failed").status == status and not restarted_transport.calls
    assert restarted.application.reviewed_character_chat_status().budget_used == 1


@pytest.mark.parametrize("enabled", [True, False])
def test_current_control_and_bad_history_close_even_when_history_off(whole_fixture, monkeypatch, enabled):
    opening, _, _, _ = whole_fixture
    transport = WholeTransport()
    product = opening(transport)
    assert product.application.set_reviewed_character_history(enabled).history_enabled is enabled
    assert send(product, "不要再使用之前的聊天。", "control").status == "failed-closed"
    assert not transport.calls
    monkeypatch.setattr(TimelineEngine, "_verified_dialogue_prefix", lambda *a, **kw: None)
    assert send(product, "一个正常话题。", "broken").status == "failed-closed"
    assert not transport.calls


def test_off_on_revision_during_generation_blocks_final_publication(whole_fixture):
    opening, _, config, _ = whole_fixture
    from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
    authority = LocalIdentityAuthority(config)
    def change():
        assert authority.set_reviewed_character_history(False).history_enabled is False
        assert authority.set_reviewed_character_history(True).history_enabled is True
    transport = WholeTransport(callback=change)
    product = opening(transport)
    result = send(product, "设置变化中的问题。", "revision")
    assert result.status == "failed-closed", result
    assert result.projection.failure_code == "original-whole-authorization-changed"
    assert len(transport.calls) == 1 and history(product) == ()


@pytest.mark.parametrize("interruption", ["before-plan", "after-claim"])
def test_cold_pending_after_delivery_fails_closed_without_resend(whole_fixture, monkeypatch, interruption):
    opening, _, _, _ = whole_fixture
    transport = WholeTransport()
    product = opening(transport)
    original = TimelineEngine.publish if interruption == "before-plan" else TimelineEngine._hit
    from dynamic_subject_agent.timeline import PublicationInterrupted
    if interruption == "before-plan":
        monkeypatch.setattr(TimelineEngine, "publish", lambda *a, **kw: (_ for _ in ()).throw(PublicationInterrupted("synthetic-interruption", "Synthetic cold interruption.")))
    else:
        def hit(self, point):
            if point is FaultPoint.AFTER_PLAN_CLAIM:
                raise OSError("Synthetic claimed-plan interruption.")
            return original(self, point)
        monkeypatch.setattr(TimelineEngine, "_hit", hit)
    result = send(product, "中断中的问题。", "interrupted")
    assert len(transport.calls) == 1
    product.close()
    monkeypatch.setattr(TimelineEngine, "publish" if interruption == "before-plan" else "_hit", original)
    transport2 = WholeTransport()
    restarted = opening(transport2)
    result = send(restarted, "中断中的问题。", "interrupted")
    assert result.status == "failed-closed", result
    assert result.projection.failure_code == "original-whole-unprepared-interruption"
    assert not transport2.calls and history(restarted) == ()
    assert send(restarted, "恢复后的新问题。", "fresh").status == "terminal"
    assert len(transport2.calls) == 1


def test_two_long_complete_turns_are_never_split(whole_fixture):
    opening, _, _, _ = whole_fixture
    transport = WholeTransport(reply="字" * 1200)
    product = opening(transport)
    assert send(product, "甲" * 1000, "long-one").status == "terminal"
    assert send(product, "乙" * 1000, "long-two").status == "terminal"
    assert send(product, "继续。", "long-three").status == "terminal"
    assert json.loads(transport.calls[2]["messages"][1]["content"])["exchange"] == [dict(user_text="乙" * 1000, assistant_text="字" * 1200)]


def test_gateway_requires_one_exact_unreconstructable_ticket_and_separate_audit(whole_fixture):
    opening, options, config, _ = whole_fixture
    product = opening()
    product.close()
    from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
    from dynamic_subject_agent.original_whole_chat import whole_projection, digest
    from dynamic_subject_agent.original_whole_chat_audit import OriginalWholeDelivery, open_original_whole_audit
    from dynamic_subject_agent.original_whole_chat_provider import DeepSeekOriginalWholeAdapter
    from dynamic_subject_agent.reviewed_character_chat import CharacterDialogueBasis
    from dynamic_subject_agent.model_gateway import ModelGateway, ModelTask, ModelTaskKind, ModelGatewayFailure
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID
    from dynamic_subject_agent.development_model_calls import DevelopmentCallAudit
    loaded = LocalIdentityAuthority(config).load_active()
    audit = open_original_whole_audit(options["audit_path"])
    projection = whole_projection(loaded.reviewed_definition, loaded.runtime_identity, "当前合成问题。", CharacterDialogueBasis("available"), True)
    delivery = OriginalWholeDelivery(audit, contract=loaded.qri.reviewed_chat_contract, state_path=config.state_path)
    transport = WholeTransport()
    def gateway_for(delivery):
        return ModelGateway(DeepSeekOriginalWholeAdapter(transport=transport, envelope=loaded.reviewed_definition, delivery=delivery,
            credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID)))
    task = ModelTask(ModelTaskKind.CHARACTER_ORIGINAL_WHOLE_REPLY, projection)
    delivery.claim("a" * 64, "b" * 64, digest(asdict(projection)))
    changed = replace(projection, turn={**projection.turn, "current_message": "擅自更换输入。"})
    with pytest.raises(ModelGatewayFailure):
        gateway_for(delivery).execute(ModelTask(task.kind, changed))
    delivery.record("failed-closed")
    assert not transport.calls and audit.counts() == (None, 1, None)
    reopened = OriginalWholeDelivery(open_original_whole_audit(options["audit_path"]), contract=loaded.qri.reviewed_chat_contract, state_path=config.state_path)
    with pytest.raises(ModelGatewayFailure):
        gateway_for(reopened).execute(task)
    with pytest.raises(ValueError, match="already claimed"):
        reopened.claim("a" * 64, "b" * 64, digest(asdict(projection)))
    with pytest.raises(ValueError):
        DevelopmentCallAudit(options["audit_path"])
    assert not transport.calls


def test_final_commit_identity_switch_out_and_back_revokes_old_proposal(whole_fixture, monkeypatch):
    opening, _, config, _ = whole_fixture
    opening().close()
    from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
    authority = LocalIdentityAuthority(config)
    loaded = authority.load_active()
    transport = WholeTransport()
    product = opening(transport)
    state = json.loads(config.state_path.read_text(encoding="utf-8"))
    other = next(row["identity_id"] for row in state["identities"] if row["identity_id"] != product.profile_id)
    original = TimelineEngine._hit
    def hit(self, point):
        if point is FaultPoint.BEFORE_PUBLICATION_COMMIT:
            # Both selections use the same Authority interface/registry lock;
            # the old bool still equals True when the final guard runs.
            assert authority.select(LocalIdentitySelectRequest(other, True), current=loaded).status == "selected"
            assert authority.select(LocalIdentitySelectRequest(product.profile_id, True), current=loaded).status == "selected"
        return original(self, point)
    monkeypatch.setattr(TimelineEngine, "_hit", hit)
    result = send(product, "切换身份时的合成问题。", "identity-race")
    assert result.status == "failed-closed", result
    assert result.projection.failure_code == "original-whole-authorization-changed"
    assert len(transport.calls) == 1 and not history(product)


def test_activation_after_host_swap_replays_same_new_qualification_and_timeline(whole_fixture, monkeypatch):
    opening, _, config, _ = whole_fixture
    import dynamic_subject_agent.local_identity_authority as authority_module
    before = json.loads(config.state_path.read_text(encoding="utf-8"))["identities"][-1]
    original = authority_module._write_state
    def interrupt(path, state):
        if "whole_chat_activation" in state["identities"][-1] and "pending_whole_chat_activation" not in state["identities"][-1]:
            raise OSError("Synthetic registry interruption after Host swap.")
        return original(path, state)
    monkeypatch.setattr(authority_module, "_write_state", interrupt)
    transport = WholeTransport()
    with pytest.raises(OSError):
        opening(transport)
    monkeypatch.setattr(authority_module, "_write_state", original)
    product = opening(transport)
    after = json.loads(config.state_path.read_text(encoding="utf-8"))["identities"][-1]
    assert after["identity_id"] == before["identity_id"] and after["timeline_id"] == before["timeline_id"]
    assert after["host_location"] == before["host_location"] and "pending_whole_chat_activation" not in after
    assert product.application.reviewed_character_chat_status().status == "active" and not transport.calls


def test_generic_composition_cannot_assemble_an_unqualified_whole_gateway(whole_fixture):
    opening, _, config, _ = whole_fixture
    opening().close()
    from dynamic_subject_agent.local_product import open_local_product
    from dynamic_subject_agent.original_whole_chat_cognition import OriginalWholeChatCognition
    with pytest.raises(ValueError, match="exact production composition"):
        open_local_product(config, cognition=OriginalWholeChatCognition(gateway=object()))


@pytest.mark.parametrize("changed", ["knowledge", "personality", "stage", "genesis"])
def test_gateway_recomputes_sealed_content_even_when_all_approved_hash_labels_are_preserved(whole_fixture, changed):
    opening, options, config, _ = whole_fixture
    opening().close()
    from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
    from dynamic_subject_agent.original_whole_chat import whole_projection, digest
    from dynamic_subject_agent.original_whole_chat_audit import OriginalWholeDelivery, open_original_whole_audit
    from dynamic_subject_agent.original_whole_chat_provider import DeepSeekOriginalWholeAdapter
    from dynamic_subject_agent.reviewed_character_chat import CharacterDialogueBasis
    from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection
    from dynamic_subject_agent.model_gateway import ModelGateway, ModelTask, ModelTaskKind, ModelGatewayFailure
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID
    loaded = LocalIdentityAuthority(config).load_active()
    envelope = deepcopy(loaded.reviewed_definition)
    transport = WholeTransport()
    delivery = OriginalWholeDelivery(open_original_whole_audit(options["audit_path"]),
        contract=loaded.qri.reviewed_chat_contract, state_path=config.state_path)
    credential = CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID)
    # A legitimately constructed sender must also revalidate its later mutable
    # input; deriving both the task and expected task from the forgery is unsafe.
    adapter = DeepSeekOriginalWholeAdapter(transport=transport, envelope=envelope, delivery=delivery, credential_ref=credential)
    if changed == "knowledge":
        envelope["runtime_asset"]["eligible"][0]["statement"] = "未经批准的合成本人认识。"
    elif changed == "personality":
        envelope["runtime_asset"]["personality"][0]["interpretation"] = "未经批准的合成人格解释。"
    elif changed == "stage":
        envelope["runtime_asset"]["initial_stage"] = "未经批准的合成起点。"
    else:
        envelope["genesis_content"]["subject_identity"] = "未经批准的合成身份。"
    assert envelope["definition_basis"] == loaded.reviewed_definition["definition_basis"]
    assert envelope["runtime_asset_sha"] == loaded.reviewed_definition["runtime_asset_sha"]
    assert envelope["runtime_asset"]["persona_digest"] == loaded.reviewed_definition["runtime_asset"]["persona_digest"]
    identity = RuntimeIdentityProjection(envelope["runtime_asset"]["subject"]["name"],
        envelope["genesis_content"]["subject_identity"], envelope["genesis_content"]["canon_start"])
    projection = whole_projection(envelope, identity, "当前合成问题。", CharacterDialogueBasis("available"), True)
    delivery.claim("c" * 64, "d" * 64, digest(asdict(projection)))
    task = ModelTask(ModelTaskKind.CHARACTER_ORIGINAL_WHOLE_REPLY, projection)
    gateway = ModelGateway(adapter)
    with pytest.raises(ModelGatewayFailure):
        gateway.execute(task)
    delivery.record("failed-closed")
    with pytest.raises(ModelGatewayFailure):
        gateway.execute(task)
    with pytest.raises(ValueError):
        DeepSeekOriginalWholeAdapter(transport=transport, envelope=envelope, delivery=delivery, credential_ref=credential)
    assert not transport.calls and delivery.counts() == (None, 1, None)
