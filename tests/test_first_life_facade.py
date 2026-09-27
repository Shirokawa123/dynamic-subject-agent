from hashlib import sha256
from dataclasses import asdict
import json

import pytest

from dynamic_subject_agent.first_life import FirstLifeIdentityRequest, FirstLifeSimulationRequest, FirstLifeHeartbeatRequest, FirstLifeControlRequest, first_life_scope_digest
from dynamic_subject_agent.local_product import open_first_life_product
from dynamic_subject_agent.source_character_authoring import LocalIdentitySelectRequest
from dynamic_subject_agent.character_chat_budget import CharacterChatBudget
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json
from test_character_evidence_model import model_fixture
from test_character_personality import personality_fixture
from test_reviewed_character_identity import approved


class LifeTransport(DeepSeekTransport):
    def __init__(self): self.calls = []; self.actions = 0; self.share = True

    def post_json(self, **kwargs):
        body = json.loads(kwargs["body"]); projection = json.loads(body["messages"][1]["content"])
        self.calls.append((body, projection))
        policy = body["messages"][0]["content"]
        if "current_activity" in projection and "conversation" not in projection and "只返回JSON exact字段action,plan,reason_code" in policy:
            self.actions += 1
            action = {1:"start", 2:"revise", 3:"keep"}[self.actions]
            plan = dict(subject="小兔子", composition="靠左留出空白" if action == "start" else "主体移到中央，左右留白", focus="可辨识的耳朵") if action != "keep" else None
            value = dict(action=action, plan=plan, reason_code="preserve-current" if action == "keep" else "balance-space")
        elif "conversation" not in projection:
            value = dict(share=self.share, reply_text="这次把构图的留白改了一下。" if self.share else "", language="zh")
        elif "self_knowledge" in projection["conversation"]:
            value = dict(action="answer", fact_refs=[], use_life="改" in projection["conversation"]["current_message"])
        else: value = dict(reply_text="我把主体从靠左改到了中央。", language="zh")
        return DeepSeekHttpResponse(200, canonical_json(dict(model="deepseek-flash", choices=[dict(finish_reason="stop",
            message=dict(role="assistant", content=canonical_json(value), reasoning_content="SECRET_REASONING"))],
            usage=dict(prompt_tokens=50, completion_tokens=50))).encode())


@pytest.fixture
def life_fixture(approved, tmp_path, monkeypatch):
    import dynamic_subject_agent.first_life as life_module
    monkeypatch.setattr(life_module, "current_civil_day", lambda: "2026-09-27")
    product, config, request, view = approved
    base = product.application.freeze_source_identity(request); assert base.status == "created"
    assert product.application.select_local_identity(LocalIdentitySelectRequest(base.view.identity_id, True)).status == "selected"
    scope = first_life_scope_digest(view.definition_basis)
    frozen = product.application.freeze_first_life_identity(FirstLifeIdentityRequest(view.definition_basis, scope, True))
    assert frozen.status == "created", frozen
    assert frozen.view.identity_id != base.view.identity_id
    assert product.application.select_local_identity(LocalIdentitySelectRequest(frozen.view.identity_id, True)).status == "selected"
    product.close()
    budget_path = tmp_path / "shared-budget"
    CharacterChatBudget(budget_path, total=200, initial_used=61, initialize=True)
    clock = [0.0]; transport = LifeTransport(); opened = []
    def opening(**changes):
        product = open_first_life_product(config, definition_basis=view.definition_basis, life_scope_digest=scope,
            budget_path=budget_path, initial_budget_used=61, development_run=True, _transport=transport,
            _clock=lambda: clock[0], _civil_day=lambda: "2026-09-27", **changes)
        opened.append(product); return product
    yield opening, transport, clock, config, view
    for product in opened: product.close()


def settle(app, result):
    return app.wait(result.operation_ref, timeout_seconds=30) if result.status == "pending" else result


def test_facade_three_real_content_steps_pause_restart_and_no_fake_chat(life_fixture):
    opening, transport, clock, config, view = life_fixture
    product = opening(); app = product.application
    assert app.first_life_status().phase == "unstarted" and not transport.calls
    for index in range(3):
        result = settle(app, app.simulate_first_life_step(FirstLifeSimulationRequest(f"first-life-simulation-{index:02}")))
        assert result.status == "terminal", result
    query = app.query_first_life()
    assert query.status == "available" and query.project.phase == "kept", query
    assert len(query.versions) == 2 and len(query.events) == 3
    assert query.versions[0].plan.composition != query.versions[1].plan.composition
    assert query.versions[1].differences[0].before == "靠左留出空白"
    assert all(event.simulated for event in query.events)
    assert not query.shares
    assert len(transport.calls) == 3
    from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
    history = app.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY, product.profile_id, product.timeline_id))
    assert history.status == "available" and history.projection.turns == ()
    controlled = settle(app, app.set_first_life_controls(FirstLifeControlRequest("first-life-pause-control", paused=True)))
    assert controlled.status == "terminal" and app.first_life_status().paused
    assert app.simulate_first_life_step(FirstLifeSimulationRequest("first-life-paused-simulation")).operation_ref is None
    assert len(transport.calls) == 3
    product.close()
    restored = opening(); q2 = restored.application.query_first_life()
    assert q2 == query and restored.application.first_life_status().paused


def test_committed_share_is_assistant_origin_unanswered_survives_restart_and_controls(life_fixture):
    from test_reviewed_character_chat import send
    from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
    opening, transport, clock, _, _ = life_fixture
    product = opening(); app = product.application
    for index in range(3):
        assert settle(app, app.simulate_first_life_step(FirstLifeSimulationRequest(f"share-life-step-{index:02}"))).status == "terminal"
    assert send(product, "你好，聊点别的吧。", "initial-life-contact").status == "terminal"
    before = len(transport.calls)
    shared = settle(app, app.heartbeat_first_life(FirstLifeHeartbeatRequest("share-window-session-0001", "share-life-heartbeat-01")))
    assert shared.status == "terminal", shared
    query = app.query_first_life(); assert len(query.shares) == 1 and query.shares[0].answered is False
    assert len(transport.calls) == before + 1
    assert "conversation" not in transport.calls[-1][1] and "recent_dialogue" not in transport.calls[-1][1]
    assert "你好" not in canonical_json(transport.calls[-1][1]) and "event_id" not in canonical_json(transport.calls[-1][1])
    assert app.first_life_status().unanswered_share
    for index in range(3):
        clock[0] += 5
        result = app.heartbeat_first_life(FirstLifeHeartbeatRequest("share-window-session-0001", f"share-unanswered-hb-{index}"))
        assert result.operation_ref is None
    assert len(transport.calls) == before + 1
    assert settle(app, app.set_first_life_controls(FirstLifeControlRequest("pause-after-share-control", paused=True))).status == "terminal"
    assert settle(app, app.set_first_life_controls(FirstLifeControlRequest("off-after-share-control", sharing_enabled=False))).status == "terminal"
    history = app.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY, product.profile_id, product.timeline_id))
    assert len(history.projection.turns) == 1 and history.projection.turns[0].user_text == "你好，聊点别的吧。"
    product.close()
    restored = opening(); assert restored.application.first_life_status().unanswered_share
    assert restored.application.query_first_life().shares == query.shares
    assert send(restored, "我看到你的分享了。", "answer-share").status == "terminal"
    assert restored.application.query_first_life().shares[0].answered is True
    assert not restored.application.first_life_status().unanswered_share


def test_chat_can_select_historical_revision_diff_and_conservatively_disclose_only_selected_event(life_fixture):
    from test_reviewed_character_chat import send
    opening, transport, _, _, _ = life_fixture
    product = opening(); app = product.application
    for index in range(3):
        assert settle(app, app.simulate_first_life_step(FirstLifeSimulationRequest(f"chat-diff-life-step-{index}"))).status == "terminal"
    assert send(product, "这份构图具体改过哪里？", "specific-life-diff").status == "terminal"
    selected = transport.calls[-1][1]["related_event"]
    assert selected["kind"] == "revise" and selected["revision"] == 2
    assert selected["differences"] == [dict(field="composition", before="靠左留出空白", after="主体移到中央，左右留白")]
    assert app.first_life_status().project_revision == 2
    assert app.reviewed_character_chat_status().history_enabled
    assert app.set_reviewed_character_history(False).history_enabled is False
    assert send(product, "再聊一次。", "life-no-history").status == "terminal"
    assert transport.calls[-1][1]["recent_dialogue"] == []


def test_declined_share_is_considered_once_and_does_not_mark_unanswered(life_fixture):
    from test_reviewed_character_chat import send
    opening, transport, clock, _, _ = life_fixture
    product = opening(); app = product.application
    for index in range(3):
        assert settle(app, app.simulate_first_life_step(FirstLifeSimulationRequest(f"decline-life-step-{index}"))).status == "terminal"
    assert send(product, "你好，换个话题。", "decline-contact").status == "terminal"
    transport.share = False
    first = settle(app, app.heartbeat_first_life(FirstLifeHeartbeatRequest("decline-window-session-0001", "decline-heartbeat-01")))
    assert first.status == "terminal"
    count = len(transport.calls)
    assert not app.query_first_life().shares and not app.first_life_status().unanswered_share
    for index in range(4):
        clock[0] += 5
        assert app.heartbeat_first_life(FirstLifeHeartbeatRequest("decline-window-session-0001", f"decline-heartbeat-{index+2:02}")).operation_ref is None
    assert len(transport.calls) == count
    product.close()
    restarted = opening()
    assert restarted.application.heartbeat_first_life(FirstLifeHeartbeatRequest("another-window-session-0001", "decline-restart-heartbeat")).operation_ref is None
    assert len(transport.calls) == count


def test_single_online_lease_advances_only_open_intervals_and_never_catches_up(life_fixture):
    opening, transport, clock, _, _ = life_fixture
    app = opening().application
    request = lambda session, index: FirstLifeHeartbeatRequest(session, f"online-life-hb-request-{index:03}")
    assert app.heartbeat_first_life(request("online-owner-session-0001", 0)).operation_ref is None
    for index in range(1, 12):
        clock[0] = index * 5
        assert app.heartbeat_first_life(request("online-owner-session-0001", index)).operation_ref is None
        assert app.heartbeat_first_life(request("online-other-session-0001", index + 100)).operation_ref is None
    assert not transport.calls
    clock[0] = 60
    result = settle(app, app.heartbeat_first_life(request("online-owner-session-0001", 12)))
    assert result.status == "terminal" and len(transport.calls) == 1
    assert app.first_life_status().virtual_minutes == 1
    clock[0] = 10000
    assert app.heartbeat_first_life(request("online-owner-session-0001", 13)).operation_ref is None
    assert len(transport.calls) == 1 and app.first_life_status().virtual_minutes == 1


def test_life_quota_metadata_is_shared_atomic_and_compatible_with_old_budget_reader(tmp_path):
    from dynamic_subject_agent.first_life_budget import FirstLifeBudget
    from dynamic_subject_agent.first_life import DEVELOPMENT_SCOPE
    import sqlite3
    path = tmp_path / "shared-life-budget"
    old = CharacterChatBudget(path, total=200, initial_used=61, initialize=True)
    life = FirstLifeBudget(path, civil_day=lambda: "2026-09-27")
    for index in range(6):
        operation = sha256(f"decision-{index}".encode()).hexdigest()
        life.claim_life("a" * 64, operation, "planning", "b" * 64, purpose="life-decision", civil_day="2026-09-27", development_run=True)
        life.record("a" * 64, operation, "planning", status="unknown")
    with pytest.raises(ValueError, match="daily life quota"):
        life.claim_life("c" * 64, "d" * 64, "planning", "e" * 64, purpose="life-decision", civil_day="2026-09-27", development_run=True)
    assert old.counts() == (200, 67, 133)
    # An old S104 process can continue updating its original stage/head format.
    old.claim("f" * 64, "1" * 64, "expression", "2" * 64)
    old.record("f" * 64, "1" * 64, "expression", status="complete", output_digest="3" * 64)
    assert life.life_counts("2026-09-27", development_run=True) == (6, 0, 18)
    assert life.counts() == (200, 68, 132)
    with pytest.raises(ValueError, match="day-expired"):
        life.claim_life("a" * 64, "4" * 64, "expression", "5" * 64, purpose="life-share", civil_day="2026-09-26", development_run=True)
    assert old.counts() == (200, 68, 132)
    db = sqlite3.connect(path / "attempts.sqlite3", autocommit=True)
    try: db.execute("DELETE FROM life_limit_claim WHERE stage_ordinal=5")
    finally: db.close()
    with pytest.raises(ValueError, match="cumulative head"):
        life.life_counts("2026-09-27", development_run=True)


def test_development_run_limit_covers_chat_stages_across_roots_and_cannot_be_reset(tmp_path):
    from dynamic_subject_agent.first_life_budget import FirstLifeBudget
    path = tmp_path / "development-shared-budget"
    old = CharacterChatBudget(path, total=200, initial_used=61, initialize=True)
    first = FirstLifeBudget(path, civil_day=lambda: "2026-09-27")
    for index in range(24):
        stage, purpose = ("planning", "chat-planning") if index % 2 == 0 else ("expression", "chat-expression")
        operation = sha256(f"development-chat-{index}".encode()).hexdigest()
        first.claim_life("a" * 64, operation, stage, "b" * 64, purpose=purpose, civil_day="2026-09-27", development_run=True)
        first.record("a" * 64, operation, stage, status="unknown")
    another = FirstLifeBudget(path, civil_day=lambda: "2026-09-27")
    assert another.life_counts("2026-09-27", development_run=True) == (0, 0, 0)
    with pytest.raises(ValueError, match="development quota"):
        another.claim_life("c" * 64, "d" * 64, "planning", "e" * 64, purpose="life-decision", civil_day="2026-09-27", development_run=True)
    assert old.counts() == (200, 85, 115)
    # Ordinary user usage remains under the global/day grant, not a lifetime 24 cap.
    another.claim_life("c" * 64, "f" * 64, "planning", "e" * 64, purpose="life-decision", civil_day="2026-09-27", development_run=False)
    assert old.counts() == (200, 86, 114)


def test_invalid_model_life_choice_fails_as_system_status_without_version_or_automatic_retry(life_fixture, monkeypatch):
    opening, transport, clock, _, _ = life_fixture
    product = opening(); app = product.application
    original = transport.post_json
    def failed(**kwargs):
        transport.calls.append((json.loads(kwargs["body"]), {}))
        raise TimeoutError("PRIVATE_TRANSPORT_TEXT")
    monkeypatch.setattr(transport, "post_json", failed)
    response = settle(app, app.simulate_first_life_step(FirstLifeSimulationRequest("failed-life-simulation-01")))
    assert response.status == "unknown"
    assert not app.query_first_life().versions and not app.query_first_life().events
    assert app.first_life_status().status == "needs-attention"
    count = len(transport.calls)
    for index in range(3):
        clock[0] += 60
        assert app.heartbeat_first_life(FirstLifeHeartbeatRequest("failed-window-session-0001", f"failed-life-hb-{index}")).operation_ref is None
    assert len(transport.calls) == count
    monkeypatch.setattr(transport, "post_json", original)
    assert settle(app, app.set_first_life_controls(FirstLifeControlRequest("explicit-life-resume-01", paused=False))).status == "terminal"
    assert settle(app, app.simulate_first_life_step(FirstLifeSimulationRequest("new-life-simulation-after-control"))).status == "terminal"
    assert len(app.query_first_life().versions) == 1


def test_quota_read_failure_before_future_releases_clock_for_explicit_later_step(life_fixture, monkeypatch):
    from dynamic_subject_agent.first_life_budget import FirstLifeBudget
    opening, transport, _, _, _ = life_fixture
    app = opening().application
    original = FirstLifeBudget.life_counts
    def failed(*args, **kwargs): raise ValueError("synthetic one-time quota read failure")
    monkeypatch.setattr(FirstLifeBudget, "life_counts", failed)
    result = app.simulate_first_life_step(FirstLifeSimulationRequest("quota-read-failed-step"))
    assert result.status == "unavailable" and not transport.calls
    monkeypatch.setattr(FirstLifeBudget, "life_counts", original)
    recovered = settle(app, app.simulate_first_life_step(FirstLifeSimulationRequest("quota-read-recovered-step")))
    assert recovered.status == "terminal" and len(transport.calls) == 1
    assert app.first_life_status().phase == "drafted"


def test_share_raw_length_over_limit_is_closed_before_publication_and_never_automatically_retried(life_fixture, monkeypatch):
    from test_reviewed_character_chat import send
    opening, transport, clock, _, _ = life_fixture
    app_product = opening(); app = app_product.application
    for index in range(3):
        assert settle(app, app.simulate_first_life_step(FirstLifeSimulationRequest(f"oversized-share-life-step-{index}"))).status == "terminal"
    assert send(app_product, "你好，聊点别的。", "oversized-share-contact").status == "terminal"
    original = transport.post_json
    def oversized(**kwargs):
        reply = original(**kwargs)
        data = json.loads(reply.body)
        output = json.loads(data["choices"][0]["message"]["content"])
        if "share" in output:
            output["reply_text"] = "合" * 400 + " "
            data["choices"][0]["message"]["content"] = canonical_json(output)
        return DeepSeekHttpResponse(reply.status_code, canonical_json(data).encode())
    monkeypatch.setattr(transport, "post_json", oversized)
    result = settle(app, app.heartbeat_first_life(FirstLifeHeartbeatRequest("oversized-share-window-0001", "oversized-share-hb-01")))
    assert result.status == "failed-closed" and result.projection.failure_code == "first-life-share-structured-choice-invalid"
    assert not app.query_first_life().shares and app.first_life_status().status == "needs-attention"
    count = len(transport.calls)
    for index in range(3):
        clock[0] += 5
        assert app.heartbeat_first_life(FirstLifeHeartbeatRequest("oversized-share-window-0001", f"oversized-share-hb-{index+2:02}")).operation_ref is None
    assert len(transport.calls) == count


def test_sharing_only_control_does_not_erase_online_activity_minutes(life_fixture):
    opening, transport, clock, _, _ = life_fixture
    app = opening().application
    hb = lambda index: FirstLifeHeartbeatRequest("sharing-control-clock-session", f"sharing-clock-hb-{index:03}")
    assert app.heartbeat_first_life(hb(0)).operation_ref is None
    for index in range(1, 12):
        clock[0] = index * 5
        assert app.heartbeat_first_life(hb(index)).operation_ref is None
    assert not transport.calls
    assert settle(app, app.set_first_life_controls(FirstLifeControlRequest("sharing-only-control-01", sharing_enabled=False))).status == "terminal"
    clock[0] = 60
    assert settle(app, app.heartbeat_first_life(hb(12))).status == "terminal"
    assert len(transport.calls) == 1 and app.first_life_status().virtual_minutes == 1


def test_system_request_receipt_replays_before_paused_terminal_and_budget_gates(life_fixture):
    opening, transport, _, _, _ = life_fixture
    product = opening(); app = product.application
    requests = [FirstLifeSimulationRequest(f"receipt-life-step-{index}") for index in range(3)]
    responses = [settle(app, app.simulate_first_life_step(request)) for request in requests]
    assert all(response.status == "terminal" for response in responses)
    assert settle(app, app.set_first_life_controls(FirstLifeControlRequest("receipt-life-paused-01", paused=True))).status == "terminal"
    repeated = app.simulate_first_life_step(requests[-1])
    assert repeated.status == "terminal" and repeated.replayed and repeated.operation_ref == responses[-1].operation_ref
    assert len(transport.calls) == 3
    product.close()
    restarted = opening()
    repeated_again = restarted.application.simulate_first_life_step(requests[0])
    assert repeated_again.status == "terminal" and repeated_again.replayed and repeated_again.operation_ref == responses[0].operation_ref
    assert len(transport.calls) == 3


def test_share_claim_day_change_fails_before_any_quota_or_transport(tmp_path):
    from dynamic_subject_agent.first_life_budget import FirstLifeBudget
    path = tmp_path / "actual-call-day-budget"
    CharacterChatBudget(path, total=200, initial_used=61, initialize=True)
    trusted = ["2026-09-27"]
    budget = FirstLifeBudget(path, civil_day=lambda: trusted[0])
    trusted[0] = "2026-09-28"
    with pytest.raises(ValueError, match="day-expired"):
        budget.claim_life("a" * 64, "b" * 64, "expression", "c" * 64, purpose="life-share", civil_day="2026-09-27", development_run=True)
    assert budget.counts() == (200, 61, 139)
    assert budget.life_counts("2026-09-27", development_run=True) == (0, 0, 24)
    budget.claim_life("a" * 64, "b" * 64, "expression", "c" * 64, purpose="life-share", civil_day="2026-09-28", development_run=True)
    assert budget.life_counts("2026-09-28", development_run=True) == (0, 1, 23)


def test_plain_reopen_recovers_prepared_step_before_new_browser_nonce_without_model(life_fixture, monkeypatch):
    from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint
    opening, transport, clock, _, _ = life_fixture
    product = opening(); app = product.application
    original = TimelineEngine._hit
    hit = [False]
    def interrupted(engine, point):
        original(engine, point)
        if point is FaultPoint.AFTER_PLAN_CLAIM and not hit[0]:
            hit[0] = True
            raise OSError("synthetic after durable plan claim")
    monkeypatch.setattr(TimelineEngine, "_hit", interrupted)
    first = settle(app, app.simulate_first_life_step(FirstLifeSimulationRequest("cold-pending-life-step-01")))
    assert first.status != "terminal" and len(transport.calls) == 1
    assert app.first_life_status().phase == "unstarted"
    product.close()
    monkeypatch.setattr(TimelineEngine, "_hit", original)
    restarted = opening(); restored = restarted.application
    assert len(transport.calls) == 1 and restored.first_life_status().phase == "drafted"
    assert len(restored.query_first_life().versions) == 1 and len(restored.query_first_life().events) == 1
    # New browser nonce baseline is not a retry of the unobserved old response.
    assert restored.heartbeat_first_life(FirstLifeHeartbeatRequest("new-browser-session-nonce", "new-browser-hb-baseline")).operation_ref is None
    assert len(transport.calls) == 1


def test_heartbeat_during_blocking_chat_only_renews_lease_without_writer_or_step(life_fixture, monkeypatch):
    from threading import Event
    from time import monotonic
    from dynamic_subject_agent.timeline import SubjectCommand
    opening, transport, clock, _, _ = life_fixture
    product = opening(); app = product.application
    assert app.first_life_status().paused is False
    session = "blocking-chat-life-session-0001"
    assert app.heartbeat_first_life(FirstLifeHeartbeatRequest(session, "blocking-life-baseline")).operation_ref is None
    entered, release = Event(), Event()
    original = transport.post_json
    first = [True]
    def blocked(**kwargs):
        if first[0]:
            first[0] = False; entered.set()
            if not release.wait(10): raise RuntimeError("test release timeout")
        return original(**kwargs)
    monkeypatch.setattr(transport, "post_json", blocked)
    pending = app.submit(SubjectCommand.contribute_utterance(target_profile_id=product.profile_id, target_timeline_id=product.timeline_id,
        declared_intent="ask-collaborator-status", utterance="随便聊聊。", language="zh", provenance="project-original"), idempotency_key="blocking-normal-chat-01")
    assert pending.status == "pending" and entered.wait(3)
    try:
        for index in range(1, 13):
            clock[0] = index * 5
            start = monotonic()
            response = app.heartbeat_first_life(FirstLifeHeartbeatRequest(session, f"blocking-hb-renew-{index:02}"))
            assert monotonic() - start < 0.5
            assert response.operation_ref is None and response.problem.code == "pending-lease-renewed"
        assert not transport.calls
    finally: release.set()
    completed = app.wait(pending.operation_ref, timeout_seconds=30)
    assert completed.status == "terminal" and len(transport.calls) == 2
    monkeypatch.setattr(transport, "post_json", original)
    # All renewals kept the same online lease and did not consume its ready
    # minute or mark a phantom busy step. It can advance once after completion.
    clock[0] = 65
    advanced = settle(app, app.heartbeat_first_life(FirstLifeHeartbeatRequest(session, "blocking-after-chat-step")))
    assert advanced.status == "terminal" and len(transport.calls) == 3
    assert app.first_life_status().virtual_minutes == 1
