"""Synthetic S112 delivery and accounting; no credentials or network calls."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from hashlib import sha256
import json
import sqlite3

import pytest

from dynamic_subject_agent.character_chat_budget import CharacterChatBudget
from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
from dynamic_subject_agent.cognition import CredentialRef
from dynamic_subject_agent.deepseek import DeepSeekHttpResponse, DEEPSEEK_ENDPOINT
from dynamic_subject_agent.first_life_budget import FirstLifeBudget
from dynamic_subject_agent.first_life_reply_drafts import draft_wire
from dynamic_subject_agent.first_life_reply_live_provider import LiveReplyAdapter, LiveReplyBudget
from dynamic_subject_agent.first_life_reply_routes import (
    WHOLE_LIVE_POLICY, PLANNED_LIVE_POLICY, WHOLE_LOCAL_POLICY,
    whole_reply_projection, fact_expression_projection,
)
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelGateway, ModelGatewayFailure, ModelTask, ModelTaskKind
from test_first_life_reply_routes import planning_for, choice
from test_first_life_relevance_projection import relevance_fixture


DAY = "2026-10-01"


def digest(value):
    return sha256(str(value).encode()).hexdigest()


@pytest.fixture
def tasks(relevance_fixture):
    planning = planning_for(relevance_fixture)
    expression, _ = fact_expression_projection(planning, choice())
    return {
        "A": ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY, whole_reply_projection(planning)),
        "plan": ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_PLAN, planning),
        "expression": ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_FACT_EXPRESSION, expression),
    }


def make_budget(tmp_path, *, policy=WHOLE_LIVE_POLICY, shared=None, name="branch"):
    path = tmp_path / name
    CharacterChatBudget(path, total=200, initial_used=0, initialize=True)
    local = FirstLifeBudget(path, total=200, initial_used=0, civil_day=lambda: DAY)
    if shared is None:
        shared = CharacterChatBudget(tmp_path / "shared", total=42, initial_used=0, initialize=True)
    return LiveReplyBudget(local, shared, policy=policy), local, shared


def claim(budget, task, operation="operation", identity="identity"):
    stage = "planning" if task.kind is ModelTaskKind.CHARACTER_COMMUNICATION_PLAN else "expression"
    ids = (digest(identity), digest(operation), stage)
    budget.claim_life(*ids, sha256(canonical_json(asdict(task.payload)).encode()).hexdigest(),
        purpose="chat-" + stage, civil_day=DAY, development_run=True)
    return ids


class FakeTransport:
    def __init__(self, *, error=None, finish="stop", content=None, completion=13):
        self.calls = []
        self.error, self.finish, self.completion = error, finish, completion
        self.content = json.dumps(dict(reply_text="这是合成最终回答。", language="zh", use_life=False), ensure_ascii=False) if content is None else content

    def post_json(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        payload = dict(model="deepseek-v4-flash", choices=[dict(finish_reason=self.finish,
            message=dict(role="assistant", content=self.content, reasoning_content="HIDDEN_REASONING_SENTINEL"))],
            usage=dict(prompt_tokens=11, completion_tokens=self.completion, total_tokens=24,
                prompt_cache_hit_tokens=7, provider_private="UNTRUSTED_USAGE_SENTINEL"))
        return DeepSeekHttpResponse(200, json.dumps(payload, ensure_ascii=False).encode())


def adapter_for(budget, transport=None, **kwargs):
    transport = FakeTransport() if transport is None else transport
    adapter = LiveReplyAdapter(transport, CredentialRef.reference(backend_id="synthetic", key_id="OPAQUE_REFERENCE_SENTINEL"), budget, **kwargs)
    return adapter, ModelGateway(adapter), transport


@pytest.mark.parametrize("name,policy", [("A", WHOLE_LIVE_POLICY), ("plan", PLANNED_LIVE_POLICY), ("expression", PLANNED_LIVE_POLICY)])
def test_only_claimed_exact_route_sends_frozen_wire_once_and_records_safe_output(tmp_path, tasks, name, policy):
    budget, local, shared = make_budget(tmp_path, policy=policy)
    adapter, gateway, transport = adapter_for(budget)
    task = tasks[name]
    with pytest.raises(ModelGatewayFailure):
        gateway.execute(task)
    assert transport.calls == [] and adapter.rows == []
    ids = claim(budget, task)
    result = gateway.execute(task)
    budget.record(*ids, status="complete", output_digest=digest(canonical_json(result.value)))
    with pytest.raises(ModelGatewayFailure):
        gateway.execute(task)
    assert len(transport.calls) == 1
    sent = transport.calls[0]
    assert sent["body"] == draft_wire(task) and sent["endpoint"] == DEEPSEEK_ENDPOINT and sent["timeout_seconds"] == 30
    assert budget.counts() == shared.counts() == (42, 1, 41)
    assert local.counts() == (200, 1, 199)
    row = adapter.rows[0]
    assert row["value"] == result.value and json.loads(row["final_content"]) == result.value
    assert row["payload"] == asdict(task.payload) and row["wire_sha256"] == sha256(sent["body"]).hexdigest()
    assert row["model"] == "deepseek-v4-flash" and row["usage"] == dict(prompt_tokens=11, completion_tokens=13, total_tokens=24, prompt_cache_hit_tokens=7)
    assert row["finish_reason"] == "stop" and row["error_code"] is None and row["elapsed_seconds"] >= 0
    saved = canonical_json(row)
    assert all(secret not in saved for secret in ("HIDDEN_REASONING_SENTINEL", "UNTRUSTED_USAGE_SENTINEL", "OPAQUE_REFERENCE_SENTINEL"))


def test_seed_local_audit_does_not_spend_live_allowance(tmp_path):
    budget, local, shared = make_budget(tmp_path)
    local.claim_life(digest("seed"), digest("seed-op"), "planning", digest("seed-input"),
        purpose="life-decision", civil_day=DAY, development_run=True)
    local.record(digest("seed"), digest("seed-op"), "planning", status="complete", output_digest=digest("seed-output"))
    assert budget.counts() == shared.counts() == (42, 0, 42)
    assert budget.life_counts(DAY, development_run=True) == (1, 0, 23)


def test_reopened_budget_never_reconstitutes_claim_ticket(tmp_path, tasks):
    budget, local, shared = make_budget(tmp_path)
    claim(budget, tasks["A"])
    reopened = LiveReplyBudget(FirstLifeBudget(local.path, total=200, initial_used=0, civil_day=lambda: DAY),
        CharacterChatBudget(shared.path, total=42, initial_used=0), policy=WHOLE_LIVE_POLICY)
    adapter, gateway, transport = adapter_for(reopened)
    with pytest.raises(ModelGatewayFailure):
        gateway.execute(tasks["A"])
    with pytest.raises(ValueError):
        claim(reopened, tasks["A"])
    assert transport.calls == [] and adapter.rows == [] and shared.counts() == (42, 1, 41)


@pytest.mark.parametrize("change", ["payload", "route", "life", "share"])
def test_mismatched_task_burns_ticket_without_delivery(tmp_path, tasks, change):
    budget, _, shared = make_budget(tmp_path)
    adapter, gateway, transport = adapter_for(budget)
    ids = claim(budget, tasks["A"])
    changed = {
        "payload": ModelTask(tasks["A"].kind, replace(tasks["A"].payload, history_enabled=False)),
        "route": tasks["expression"],
        "life": ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_DECISION, tasks["A"].payload),
        "share": ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_SHARE, tasks["A"].payload),
    }[change]
    with pytest.raises(ModelGatewayFailure):
        gateway.execute(changed)
    with pytest.raises(ModelGatewayFailure):
        gateway.execute(tasks["A"])
    budget.record(*ids, status="failed-closed")
    assert transport.calls == [] and adapter.rows == [] and shared.counts() == (42, 1, 41)


def test_claim_rejects_unapproved_purpose_route_and_normal_mode_before_writes(tmp_path):
    budget, local, shared = make_budget(tmp_path)
    for purpose, stage, development in (("life-decision", "planning", True), ("life-share", "expression", True),
        ("chat-planning", "planning", True), ("chat-expression", "planning", True), ("chat-expression", "expression", False)):
        with pytest.raises(ValueError):
            budget.claim_life(digest("identity"), digest("op"), stage, digest("request"),
                purpose=purpose, civil_day=DAY, development_run=development)
    assert shared.counts() == (42, 0, 42) and local.counts() == (200, 0, 200)


def test_shared_42_limit_is_global_across_four_branches(tmp_path, tasks):
    shared = CharacterChatBudget(tmp_path / "shared", total=42, initial_used=0, initialize=True)
    branches = [make_budget(tmp_path, shared=shared, name=f"branch-{index}")[0] for index in range(4)]
    adapters = [adapter_for(budget) for budget in branches]
    for index in range(42):
        branch = index % 4
        ids = claim(branches[branch], tasks["A"], operation=str(index), identity=str(branch))
        result = adapters[branch][1].execute(tasks["A"])
        branches[branch].record(*ids, status="complete", output_digest=digest(canonical_json(result.value)))
    assert shared.counts() == (42, 42, 0)
    with pytest.raises(ValueError):
        claim(branches[0], tasks["A"], operation="forbidden-43")
    with pytest.raises(ModelGatewayFailure):
        adapters[0][1].execute(tasks["A"])
    assert sum(len(transport.calls) for _, _, transport in adapters) == 42


@pytest.mark.parametrize("kwargs,code", [
    ({"error": TimeoutError("PRIVATE_ERROR_SENTINEL")}, "transport-timeout"),
    ({"error": CharacterCredentialUnavailable()}, "character-credential-unavailable"),
    ({"content": "最终正文不是JSON。"}, "response-content-json"),
    ({"finish": "length"}, "response-truncated"),
    ({"completion": 4097}, "response-overbudget"),
])
def test_failed_delivery_is_counted_sanitized_and_never_retried(tmp_path, tasks, kwargs, code):
    budget, local, shared = make_budget(tmp_path)
    adapter, gateway, transport = adapter_for(budget, FakeTransport(**kwargs))
    ids = claim(budget, tasks["A"])
    with pytest.raises(ModelGatewayFailure) as failure:
        gateway.execute(tasks["A"])
    assert failure.value.code == code
    budget.record(*ids, status="unknown" if code == "transport-timeout" else "failed-closed")
    with pytest.raises(ModelGatewayFailure):
        gateway.execute(tasks["A"])
    assert len(transport.calls) == 1 and shared.counts() == (42, 1, 41) and local.counts() == (200, 1, 199)
    assert adapter.rows[0]["error_code"] == code and adapter.rows[0]["value"] is None
    assert "PRIVATE_ERROR_SENTINEL" not in canonical_json(adapter.rows)
    if "content" in kwargs:
        assert adapter.rows[0]["final_content"] == kwargs["content"]


def test_guard_runs_before_consume_but_failure_also_burns_ticket(tmp_path, tasks):
    budget, _, shared = make_budget(tmp_path)
    order = []
    def guard(task):
        order.append("guard")
        assert budget._ticket is not None
        raise ValueError("PRIVATE_GUARD_SENTINEL")
    adapter, gateway, transport = adapter_for(budget, request_guard=guard)
    ids = claim(budget, tasks["A"])
    with pytest.raises(ModelGatewayFailure) as failure:
        gateway.execute(tasks["A"])
    assert failure.value.code == "structured-choice-invalid" and order == ["guard"]
    budget.record(*ids, status="failed-closed")
    assert budget._ticket is None and transport.calls == [] and adapter.rows == [] and shared.counts() == (42, 1, 41)


def test_ticket_cannot_be_used_by_another_thread(tmp_path, tasks):
    budget, _, _ = make_budget(tmp_path)
    adapter, gateway, transport = adapter_for(budget)
    ids = claim(budget, tasks["A"])
    with ThreadPoolExecutor(max_workers=1) as executor:
        with pytest.raises(ModelGatewayFailure):
            executor.submit(gateway.execute, tasks["A"]).result()
    budget.record(*ids, status="failed-closed")
    assert transport.calls == [] and adapter.rows == []


def test_half_claim_or_half_record_stops_bridge_without_refund(tmp_path, tasks, monkeypatch):
    budget, local, shared = make_budget(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(shared, "claim", lambda *args: (_ for _ in ()).throw(ValueError("synthetic failure")))
        with pytest.raises(ValueError):
            claim(budget, tasks["A"])
    assert shared.counts() == (42, 0, 42) and local.counts() == (200, 1, 199)
    with pytest.raises(ValueError):
        budget.counts()
    adapter, gateway, transport = adapter_for(budget)
    with pytest.raises(ModelGatewayFailure):
        gateway.execute(tasks["A"])
    assert transport.calls == []

    next_budget, next_local, _ = make_budget(tmp_path, shared=shared, name="other-branch")
    ids = claim(next_budget, tasks["A"], operation="other")
    next_budget.consume(tasks["A"])
    with monkeypatch.context() as patch:
        patch.setattr(shared, "record", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("synthetic failure")))
        with pytest.raises(ValueError):
            next_budget.record(*ids, status="complete", output_digest=digest("output"))
    with sqlite3.connect(shared.path / "attempts.sqlite3") as db:
        assert db.execute("SELECT status FROM stage_attempt").fetchone()[0] == "claimed"
    with sqlite3.connect(next_local.path / "attempts.sqlite3") as db:
        assert db.execute("SELECT status FROM stage_attempt").fetchone()[0] == "complete"
    assert shared.counts() == (42, 1, 41)
    with pytest.raises(ValueError):
        claim(next_budget, tasks["A"], operation="forbidden")


def test_bridge_rejects_local_policy_nonfixed_cap_and_same_ledger(tmp_path):
    budget, local, shared = make_budget(tmp_path)
    with pytest.raises(ValueError):
        LiveReplyBudget(local, shared, policy=WHOLE_LOCAL_POLICY)
    other = CharacterChatBudget(tmp_path / "other-shared", total=43, initial_used=0, initialize=True)
    with pytest.raises(ValueError):
        LiveReplyBudget(local, other, policy=WHOLE_LIVE_POLICY)
    same = FirstLifeBudget(shared.path, total=42, initial_used=0, civil_day=lambda: DAY)
    with pytest.raises(ValueError):
        LiveReplyBudget(same, shared, policy=WHOLE_LIVE_POLICY)
