from hashlib import sha256
import json

import pytest

from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse
from dynamic_subject_agent.local_product import open_reviewed_character_chat_product
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.reviewed_character_chat import continuity_scope
from dynamic_subject_agent.source_character_authoring import LocalIdentitySelectRequest
from dynamic_subject_agent.timeline import SubjectCommand
from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from test_character_evidence_model import model_fixture
from test_character_personality import personality_fixture
from test_reviewed_character_identity import approved


class ChatTransport(DeepSeekTransport):
    def __init__(self, fault=None, phase="planning"):
        self.calls = []; self.fault = fault; self.phase = phase

    def post_json(self, **kwargs):
        body = json.loads(kwargs["body"]); projection = json.loads(body["messages"][1]["content"])
        phase = "planning" if "self_knowledge" in projection["conversation"] else "expression"
        self.calls.append((body, projection))
        if phase == self.phase and self.fault == "timeout": raise TimeoutError("RAW_SECRET_TIMEOUT")
        if phase == self.phase and self.fault == "credential":
            from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
            raise CharacterCredentialUnavailable()
        value = dict(action="answer", fact_refs=[]) if phase == "planning" else dict(reply_text=f"合成回复第{len(self.calls)//2}轮。", language="zh")
        if phase == self.phase and self.fault == "refs": value["fact_refs"] = ["F999"]
        if phase == self.phase and self.fault == "language": value["language"] = "en"
        if phase == "expression" and self.fault == "long": value["reply_text"] = "合" * 1200
        finish = "length" if phase == self.phase and self.fault == "length" else "stop"
        return DeepSeekHttpResponse(200, canonical_json(dict(model="deepseek-flash", choices=[dict(finish_reason=finish,
            message=dict(role="assistant", content=canonical_json(value), reasoning_content="RAW_REASONING_SECRET"))],
            usage=dict(prompt_tokens=100, completion_tokens=30))).encode())


@pytest.fixture
def chat_fixture(approved, tmp_path):
    product, config, request, view = approved
    result = product.application.freeze_source_identity(request); assert result.status == "created"
    assert product.application.select_local_identity(LocalIdentitySelectRequest(result.view.identity_id, True)).status == "selected"
    product.close()
    scope_sha = sha256(canonical_json(continuity_scope(view.definition_basis)).encode()).hexdigest()
    review_sha = sha256(canonical_json(dict(definition_basis=view.definition_basis, scope_digest=scope_sha)).encode()).hexdigest()
    options = dict(definition_basis=view.definition_basis, scope_digest=scope_sha, review_request_basis=review_sha,
        budget_path=tmp_path / "shared-budget", budget_total=200, initial_budget_used=61)
    opened = []
    def opening(transport=None, **overrides):
        result = open_reviewed_character_chat_product(config, **{**options, **overrides}, _transport=transport or ChatTransport())
        opened.append(result)
        return result
    yield opening, options, config, view
    for product in opened: product.close()


def send(product, message, key):
    app = product.application
    response = app.submit(SubjectCommand.contribute_utterance(target_profile_id=product.profile_id,
        target_timeline_id=product.timeline_id, declared_intent="ask-collaborator-status", utterance=message,
        language="zh", provenance="project-original"), idempotency_key="reviewed-character-test-" + key)
    if response.status == "pending": response = app.wait(response.operation_ref, timeout_seconds=30)
    return response


def test_facade_three_turns_restart_closed_history_and_sealed_source_independence(chat_fixture, personality_fixture):
    opening, options, config, view = chat_fixture
    transport = ChatTransport(); product = opening(transport)
    initial = product.application.reviewed_character_chat_status()
    assert initial.status == "active" and initial.budget_used == 61 and initial.budget_remaining == 139
    assert not transport.calls
    first = send(product, "先聊画画。", "first")
    assert first.status == "terminal" and first.projection.expression_text == "合成回复第1轮。", first
    second = send(product, "你刚说什么？", "second")
    assert second.status == "terminal", second
    assert transport.calls[0][1]["recent_dialogue"] == []
    assert transport.calls[2][1]["recent_dialogue"] == [dict(user_text="先聊画画。", assistant_text="合成回复第1轮。")]
    assert transport.calls[2][1]["has_prior_committed_exchange"] is True
    assert all("第一条" not in " ".join(call[1]["conversation"]["encounter"]) for call in transport.calls)
    for index, (body, projection) in enumerate(transport.calls):
        assert body["reasoning_effort"] == ("low" if index % 2 == 0 else "high") and body["max_tokens"] == 4096
        assert "temperature" not in body and body["stream"] is False
        assert projection["personality"] and projection["character_core"]
        assert set(projection["runtime_identity"]) == {"subject_name", "subject_identity", "canon_start"}
        for forbidden in ("item_id", "claim_ids", "source_declaration", "evidence_ids", "persona_digest", "RAW_REASONING_SECRET"):
            assert forbidden not in canonical_json(projection)
    assert transport.calls[1][1]["conversation"]["selected_facts"] == []
    product.close()
    _, path, book, _, _ = personality_fixture
    path.unlink(); book.unlink()
    next_transport = ChatTransport(); restarted = opening(next_transport)
    third = send(restarted, "接着说吧。", "third")
    assert third.status == "terminal", third
    assert next_transport.calls[0][1]["recent_dialogue"] == [dict(user_text="先聊画画。", assistant_text="合成回复第1轮。"),
        dict(user_text="你刚说什么？", assistant_text="合成回复第2轮。")]
    assert restarted.application.set_reviewed_character_history(False).history_enabled is False
    assert send(restarted, "换个话题。", "fourth").status == "terminal"
    assert next_transport.calls[2][1]["recent_dialogue"] == [] and next_transport.calls[2][1]["has_prior_committed_exchange"]
    count = len(next_transport.calls)
    assert send(restarted, "换个话题。", "fourth").replayed
    assert len(next_transport.calls) == count
    history = restarted.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY, restarted.profile_id, restarted.timeline_id))
    assert history.status == "available" and len(history.projection.turns) == 4
    assert restarted.application.reviewed_character_chat_status().budget_used == 69


@pytest.mark.parametrize("fault,phase,status,count", [("timeout", "planning", "unknown", 1), ("timeout", "expression", "unknown", 2),
    ("length", "planning", "failed-closed", 1), ("length", "expression", "failed-closed", 2),
    ("refs", "planning", "failed-closed", 1), ("language", "expression", "failed-closed", 2), ("credential", "planning", "unavailable", 1)])
def test_stage_fault_is_typed_charged_and_never_replayed_or_published(chat_fixture, fault, phase, status, count):
    opening, options, config, _ = chat_fixture
    transport = ChatTransport(fault, phase); product = opening(transport)
    failed = send(product, "一个合成问题。", "failed")
    assert failed.status == status and failed.projection.expression_text is None, failed
    assert len(transport.calls) == count
    assert product.application.reviewed_character_chat_status().budget_used == 61 + count
    assert send(product, "一个合成问题。", "failed").status == status
    assert len(transport.calls) == count
    history = product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY, product.profile_id, product.timeline_id))
    assert history.status == "available" and not history.projection.turns
    product.close()
    next_transport = ChatTransport(); restarted = opening(next_transport)
    assert send(restarted, "一个合成问题。", "failed").status == status
    assert not next_transport.calls and restarted.application.reviewed_character_chat_status().budget_used == 61 + count
    import sqlite3
    db = sqlite3.connect(options["budget_path"] / "attempts.sqlite3")
    try:
        audit = " ".join(str(row) for row in db.execute("SELECT * FROM stage_attempt"))
        assert "一个合成问题" not in audit and "RAW_" not in audit and "合成回复" not in audit
    finally: db.close()


@pytest.mark.parametrize("point", ["publication", "registry-after-swap"])
def test_activation_interruptions_recover_one_successor_and_same_timeline(chat_fixture, monkeypatch, point):
    import dynamic_subject_agent.local_identity_authority as authority
    from dynamic_subject_agent.studio import SubjectStudio
    opening, _, config, _ = chat_fixture
    before = json.loads(config.state_path.read_text(encoding="utf-8"))["identities"][-1]
    if point == "publication":
        original = SubjectStudio.publish
        def interrupted(*a, **kw): raise OSError("synthetic before publication")
        monkeypatch.setattr(SubjectStudio, "publish", interrupted)
    else:
        original = authority._write_state
        def interrupted(path, payload):
            record = payload["identities"][-1]
            if "chat_activation" in record and "pending_chat_activation" not in record:
                raise OSError("synthetic after Host swap")
            original(path, payload)
        monkeypatch.setattr(authority, "_write_state", interrupted)
    with pytest.raises(OSError): opening()
    if point == "publication": monkeypatch.setattr(SubjectStudio, "publish", original)
    else: monkeypatch.setattr(authority, "_write_state", original)
    recovered = opening()
    assert recovered.application.reviewed_character_chat_status().status == "active"
    after = json.loads(config.state_path.read_text(encoding="utf-8"))["identities"][-1]
    assert after["identity_id"] == before["identity_id"] and after["timeline_id"] == before["timeline_id"]
    assert after["host_location"] == before["host_location"] and "pending_chat_activation" not in after
    assert send(recovered, "恢复后的当前消息。", "recover").status == "terminal"


@pytest.mark.parametrize("field", ["definition_basis", "scope_digest", "review_request_basis"])
def test_changed_definition_or_scope_approval_is_rejected_before_activation_or_budget(chat_fixture, field):
    opening, options, config, _ = chat_fixture
    before = config.state_path.read_bytes()
    with pytest.raises((RuntimeError, ValueError)): opening(**{field: "0" * 64})
    assert config.state_path.read_bytes() == before and not options["budget_path"].exists()


def test_budget_exhaustion_missing_ledger_and_initialization_conflict_never_reset_or_send(chat_fixture):
    opening, options, _, _ = chat_fixture
    transport = ChatTransport(); product = opening(transport, budget_total=63)
    assert send(product, "仅一次完整消息。", "once").status == "terminal"
    repeated = send(product, "仅一次完整消息。", "once")
    assert repeated.status == "terminal" and repeated.replayed and len(transport.calls) == 2
    conflicting = send(product, "同key的不同消息。", "once")
    assert conflicting.status == "conflict" and len(transport.calls) == 2
    refused = send(product, "额度不足。", "second")
    assert refused.status == "unavailable" and len(transport.calls) == 2
    product.close()
    with pytest.raises(RuntimeError, match="activation-conflict"): opening(budget_total=64)
    db = options["budget_path"] / "attempts.sqlite3"
    db.rename(db.with_suffix(".withheld"))
    with pytest.raises(ValueError, match="existing budget"): opening(budget_total=63)
    assert not db.exists()


def test_history_unknown_stops_before_both_models_and_explicit_off_keeps_current_only(chat_fixture, monkeypatch):
    from dynamic_subject_agent.timeline import TimelineEngine
    opening, _, _, _ = chat_fixture
    transport = ChatTransport(); product = opening(transport)
    monkeypatch.setattr(TimelineEngine, "_verified_dialogue_prefix", lambda *a, **kw: None)
    response = send(product, "当前问题。", "unknown-history")
    assert response.status == "failed-closed" and response.projection.failure_code == "reviewed-chat-history-unverified"
    assert not transport.calls and product.application.reviewed_character_chat_status().budget_used == 61
    assert product.application.set_reviewed_character_history(False).history_enabled is False
    assert product.application.set_reviewed_character_history(1).status == "unavailable"
    assert send(product, "关闭后仅当前问题。", "without-history").status == "terminal"
    assert transport.calls[0][1]["recent_dialogue"] == []


def test_history_size_keeps_only_complete_turns_and_never_halves_content(chat_fixture):
    opening, _, _, _ = chat_fixture
    transport = ChatTransport("long"); product = opening(transport)
    assert send(product, "甲" * 1000, "long-first").status == "terminal"
    assert send(product, "乙" * 1000, "long-second").status == "terminal"
    assert send(product, "继续。", "long-third").status == "terminal"
    selected = transport.calls[4][1]["recent_dialogue"]
    assert selected == [dict(user_text="乙" * 1000, assistant_text="合" * 1200)]


def test_two_products_share_one_existing_budget_without_reset(chat_fixture, tmp_path):
    from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
    from dataclasses import asdict
    opening, options, _, view = chat_fixture
    first = opening(); assert send(first, "第一产品消息。", "product-one").status == "terminal"
    other_config = LocalProductConfig(tmp_path / "second" / "m0" / "experiments", tmp_path / "second" / "state.json")
    with open_local_product(other_config, cognition=DormantDeepSeekCognition()) as preparing:
        result = preparing.application.freeze_source_identity(ReviewedCharacterFreezeRequest(canonical_json(asdict(view)), view.definition_basis, True, True))
        assert result.status == "created"
        assert preparing.application.select_local_identity(LocalIdentitySelectRequest(result.view.identity_id, True)).status == "selected"
    transport = ChatTransport()
    with open_reviewed_character_chat_product(other_config, **options, _transport=transport) as second:
        assert second.application.reviewed_character_chat_status().budget_used == 63
        assert send(second, "另一产品当前消息。", "product-two").status == "terminal"
        assert second.application.reviewed_character_chat_status().budget_used == 65
        assert transport.calls[0][1]["recent_dialogue"] == []
    assert first.application.reviewed_character_chat_status().budget_used == 65


def test_stage_claim_is_cross_process_atomic_and_claimed_delivery_is_never_refunded(tmp_path):
    import subprocess
    import sys
    from dynamic_subject_agent.character_chat_budget import CharacterChatBudget
    path = tmp_path / "shared-atomic-budget"
    ledger = CharacterChatBudget(path, total=62, initial_used=61, initialize=True)
    code = """from pathlib import Path
import sys
from dynamic_subject_agent.character_chat_budget import CharacterChatBudget
budget=CharacterChatBudget(Path(sys.argv[1]),total=62,initial_used=61)
try:
 budget.claim('a'*64,sys.argv[2],'planning','c'*64)
 print('claimed')
except ValueError:
 print('closed')
"""
    children = [subprocess.Popen([sys.executable, "-c", code, str(path), marker * 64], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for marker in ("d", "e")]
    outputs = [child.communicate(timeout=30) for child in children]
    assert all(child.returncode == 0 for child in children), outputs
    assert sorted(stdout.strip() for stdout, _ in outputs) == ["claimed", "closed"]
    assert ledger.counts() == (62, 62, 0)
    assert CharacterChatBudget(path, total=62, initial_used=61).counts() == (62, 62, 0)


def test_sealed_or_history_preference_change_after_planning_blocks_expression(chat_fixture, monkeypatch):
    import dynamic_subject_agent.local_identity_authority as module
    opening, _, config, _ = chat_fixture
    transport = ChatTransport(); product = opening(transport)
    original = transport.post_json
    def changed(**kwargs):
        response = original(**kwargs)
        state = json.loads(config.state_path.read_text(encoding="utf-8"))
        state["identities"][-1]["history_enabled"] = False
        config.state_path.write_text(canonical_json(state), encoding="utf-8")
        return response
    monkeypatch.setattr(transport, "post_json", changed)
    result = send(product, "规划期间关闭历史。", "preference-race")
    assert result.status == "failed-closed" and result.projection.failure_code == "reviewed-chat-history-changed"
    assert len(transport.calls) == 1 and product.application.reviewed_character_chat_status().budget_used == 62


def test_missing_or_tampered_budget_during_open_session_never_creates_a_new_ledger(chat_fixture):
    import sqlite3
    opening, options, _, _ = chat_fixture
    transport = ChatTransport(); product = opening(transport)
    path = options["budget_path"] / "attempts.sqlite3"
    db = sqlite3.connect(path, autocommit=True)
    try: db.execute("UPDATE config SET body='{}'")
    finally: db.close()
    assert product.application.reviewed_character_chat_status().status == "failed-closed"
    assert send(product, "被破坏的预算。", "bad-budget").status == "unavailable"
    assert not transport.calls
    path.rename(path.with_suffix(".withheld"))
    assert send(product, "缺失的预算。", "missing-budget").status == "unavailable"
    assert not path.exists() and not transport.calls


def test_deleting_unknown_tail_attempt_cannot_refund_budget_on_reopen_or_live_object(tmp_path):
    import sqlite3
    from dynamic_subject_agent.character_chat_budget import CharacterChatBudget
    path = tmp_path / "tail-loss-budget"
    ledger = CharacterChatBudget(path, total=200, initial_used=61, initialize=True)
    ledger.claim("a" * 64, "b" * 64, "planning", "c" * 64)
    ledger.record("a" * 64, "b" * 64, "planning", status="unknown")
    assert ledger.counts() == (200, 62, 138)
    db = sqlite3.connect(path / "attempts.sqlite3", autocommit=True)
    try: db.execute("DELETE FROM stage_attempt WHERE ordinal=0")
    finally: db.close()
    with pytest.raises(ValueError, match="cumulative head"):
        ledger.counts()
    with pytest.raises(ValueError, match="cumulative head"):
        CharacterChatBudget(path, total=200, initial_used=61)
    with pytest.raises(ValueError, match="cumulative head"):
        ledger.claim("a" * 64, "d" * 64, "expression", "e" * 64)


def test_pure_policy_kernel_qualifies_only_exact_chat_scope_and_configuration():
    from dataclasses import replace
    from uuid import uuid4
    from dynamic_subject_agent.reviewed_character_chat import chat_contract
    from dynamic_subject_agent.reviewed_character_definition import reviewed_source_refs
    from dynamic_subject_agent.studio import SourceDeclaration, CapabilityManifest, IsolationProof, PolicyQuestion, PolicyKernel
    envelope = dict(definition_basis="a" * 64, runtime_asset_sha="b" * 64)
    scope = sha256(canonical_json(continuity_scope(envelope["definition_basis"])).encode()).hexdigest()
    review = sha256(canonical_json(dict(definition_basis=envelope["definition_basis"], scope_digest=scope)).encode()).hexdigest()
    contract = chat_contract(envelope, scope, review)
    source = SourceDeclaration(str(uuid4()), "reviewed-fiction-derived", True, reviewed_source_refs(envelope["definition_basis"], envelope["runtime_asset_sha"]), False)
    question = PolicyQuestion("c" * 64, "d" * 64, "e" * 64, CapabilityManifest.reviewed_character_chat(),
        IsolationProof(str(uuid4()), "experimental", "system-temporary-experimental", "private-reviewed-fiction-derived"), source, source, contract)
    assert PolicyKernel().decide(question).disposition == "qualified"
    for key, value in (("scope_digest", "0" * 64), ("expression_effort", "low"), ("max_tokens", 600)):
        assert PolicyKernel().decide(replace(question, reviewed_chat_contract={**contract, key: value})).disposition == "denied"


def test_fresh_identity_initializer_cannot_rebuild_lost_or_empty_existing_shared_ledger(tmp_path):
    import sqlite3
    from dynamic_subject_agent.character_chat_budget import CharacterChatBudget
    path = tmp_path / "shared-initialization-claim"
    ledger = CharacterChatBudget(path, total=200, initial_used=61, initialize=True)
    ledger.claim("a" * 64, "b" * 64, "planning", "c" * 64)
    ledger.record("a" * 64, "b" * 64, "planning", status="unknown")
    assert ledger.counts() == (200, 62, 138)
    database = path / "attempts.sqlite3"
    database.rename(path / "withheld.sqlite3")
    with pytest.raises(ValueError, match="existing budget ledger"):
        CharacterChatBudget(path, total=200, initial_used=61, initialize=True)
    assert not database.exists()
    # Even a new identity's initializer cannot fill an existing empty DB.
    sqlite3.connect(database).close()
    with pytest.raises(ValueError, match="configuration missing"):
        CharacterChatBudget(path, total=200, initial_used=61, initialize=True)
    connection = sqlite3.connect(database)
    try:
        assert not connection.execute("SELECT name FROM sqlite_schema WHERE type='table'").fetchall()
    finally: connection.close()
    interrupted = tmp_path / "interrupted-initialization"
    interrupted.mkdir()
    with pytest.raises(ValueError, match="existing budget ledger"):
        CharacterChatBudget(interrupted, total=200, initial_used=61, initialize=True)
    assert not (interrupted / "attempts.sqlite3").exists()
