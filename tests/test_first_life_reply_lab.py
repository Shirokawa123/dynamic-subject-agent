"""A/B reply routes through the real Facade, canonical history and recovery.

All returned text and choices are deterministic local fixtures, not model quality.
"""
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from dynamic_subject_agent.character_chat_budget import CharacterChatBudget
from dynamic_subject_agent.first_life import (FirstLifeIdentityRequest, FirstLifeSimulationRequest,
    FirstLifeHeartbeatRequest, FirstLifeControlRequest, FirstLifeContextResetRequest, first_life_scope_digest)
from dynamic_subject_agent.first_life_reply_routes import WHOLE_LOCAL_POLICY, PLANNED_LOCAL_POLICY
from dynamic_subject_agent.first_life_reply_drafts import reply_scope_digest, draft_wire
from dynamic_subject_agent.first_life_budget import FirstLifeBudget
from dynamic_subject_agent.first_life_followup import FOLLOWUP_VERSION, first_life_scope_digest as v4_digest
from dynamic_subject_agent.local_product import open_first_life_reply_lab, open_first_life_product
from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
from dynamic_subject_agent.source_character_authoring import LocalIdentitySelectRequest
from dynamic_subject_agent.model_gateway import ModelGateway, ModelTaskKind, ModelResult, ProviderAdapter, ProviderCapabilities, StructuredOutputMode
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint
from test_reviewed_character_identity import model_fixture, personality_fixture
from test_first_life_facade import settle
from test_reviewed_character_chat import send
from test_s109_continuous_baseline import no_remote_io


@pytest.fixture
def approved(personality_fixture, tmp_path):
    """A coherent project-original character, through the same authoring Facade."""
    from dynamic_subject_agent.character_identity_preparation import CharacterDefinitionPreparationRequest
    from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
    from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    _, path, book, personality, open_lab = personality_fixture
    specification = json.loads((Path(__file__).resolve().parents[1] / "docs/experiments/s111/scenarios.json").read_text(encoding="utf-8"))
    character = specification["character"]
    def original_source(draft):
        facts = dict(zip(("a", "art", "work"), character["facts"], strict=True))
        statements = {key: row["text"] for key, row in facts.items()}
        quote = character["name"] + "的原创合成设定：" + "".join(statements.values())
        content = ("<html><p>" + quote + "</p></html>").encode()
        with ZipFile(book, "w") as archive:
            archive.writestr("ch.html", content)
        draft["evidence"][0].update(file_sha256=sha256(book.read_bytes()).hexdigest(),
            document_sha256=sha256(content).hexdigest(), quote=quote, quote_sha256=sha256(quote.encode()).hexdigest())
        draft["entities"][0]["name"] = character["name"]
        draft["chat_stage_description"] = character["stage"]
        draft["assertions"] = [dict(row, statement=statements[row["id"]], kind=facts[row["id"]]["kind"])
            for row in draft["assertions"] if row["id"] in statements]
        draft["chat_organization"]["core"][0]["content"] = statements["a"]
    preview, _, _, sidecar = open_lab(source_changes=original_source,
        overrides=dict(items=[dict(personality["items"][0], **character["personality"])]), preview_only=True)
    view = preview.application.preview_character_identity_preparation(CharacterDefinitionPreparationRequest(
        "self", "start", sidecar, sha256(sidecar.read_bytes()).hexdigest()))
    assert view.status == "previewed"
    request = ReviewedCharacterFreezeRequest(canonical_json(asdict(view)), view.definition_basis, True, True)
    config = LocalProductConfig(tmp_path / "sealed" / "m0" / "experiments", tmp_path / "sealed" / "state.json")
    product = open_local_product(config, cognition=DormantDeepSeekCognition())
    yield product, config, request, view
    product.close()


class LocalReplyAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities("synthetic-local-reply", "scripted", True, (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self, name="A", scenario=None):
        self.name, self.scenario = name, scenario
        self.calls, self.replies, self.drafts = [], [], []
        self.actions = 0
        self.use_life = False
        self.invalid = False
        self.on_call = None

    def invoke(self, task):
        projection = json.loads(canonical_json(asdict(task.payload)))
        self.calls.append((task.kind.value, projection))
        self.drafts.append(json.loads(draft_wire(task)) if task.kind in (
            ModelTaskKind.CHARACTER_COMMUNICATION_PLAN, ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY,
            ModelTaskKind.CHARACTER_FIRST_LIFE_FACT_EXPRESSION) else None)
        if task.kind is ModelTaskKind.CHARACTER_FIRST_LIFE_DECISION:
            self.actions += 1
            plans = self.scenario["plans"] if self.scenario else [
                dict(subject="静物", composition="右侧有书", focus="轮廓"),
                dict(subject="静物", composition="主体居中，右侧仍有书", focus="轮廓")]
            value = dict(action="start" if self.actions == 1 else "revise", plan=plans[self.actions - 1], reason_code="balance-space")
        elif task.kind is ModelTaskKind.CHARACTER_FIRST_LIFE_SHARE:
            value = dict(share=True, reply_text=self.scenario["share"] if self.scenario else "合成旧话：右侧没有书。",
                language="zh", focus="composition", opening="self-interest")
        elif task.kind is ModelTaskKind.CHARACTER_COMMUNICATION_PLAN:
            sources = projection["dialogue_sources"]
            value = dict(action="answer", fact_refs=[], use_life=self.use_life,
                focus="respond-current", dialogue_refs=[row["label"] for row in sources][-2:])
        else:
            assert task.kind in (ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY, ModelTaskKind.CHARACTER_FIRST_LIFE_FACT_EXPRESSION)
            message = projection["conversation"]["current_message"]
            # Different route outputs must become the NEXT request's actual
            # canonical context; neither route is fed a shared answer tape.
            reply = ("合成共同开场：你好，之后可以聊聊构图。" if message == "先打个招呼。" else
                f"合成本地{self.name}第{len(self.replies) + 1}轮：{message}")
            self.replies.append(reply)
            value = dict(reply_text=reply, language="zh")
            if task.kind is ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY:
                value["use_life"] = self.use_life
        if self.invalid:
            value = {}
        if self.on_call:
            self.on_call()
        return ModelResult(task.kind, value)


@pytest.fixture
def local_lab(approved, tmp_path, monkeypatch):
    monkeypatch.setattr("dynamic_subject_agent.first_life.current_civil_day", lambda: "2026-10-01")
    product, config, request, view = approved
    base = product.application.freeze_source_identity(request)
    assert base.status == "created"
    assert product.application.select_local_identity(LocalIdentitySelectRequest(base.view.identity_id, True)).status == "selected"
    scope = first_life_scope_digest(view.definition_basis)
    frozen = product.application.freeze_first_life_identity(FirstLifeIdentityRequest(view.definition_basis, scope, True))
    assert frozen.status == "created"
    assert product.application.select_local_identity(LocalIdentitySelectRequest(frozen.view.identity_id, True)).status == "selected"
    product.close()
    budget = config.state_path.parent / "local-reply-budget"
    CharacterChatBudget(budget, total=200, initial_used=61, initialize=True)
    opened = []
    def opening(route, adapter):
        gateway = ModelGateway(adapter)
        opening.gateway = gateway
        result = open_first_life_reply_lab(config, definition_basis=view.definition_basis, life_scope_digest=scope,
            budget_path=budget, runtime_policy=route, runtime_policy_digest=reply_scope_digest(view.definition_basis, route),
            gateway=gateway, _clock=lambda: 0.0, _civil_day=lambda: "2026-10-01")
        opened.append(result)
        return result
    yield opening, config, view, budget, scope
    for item in opened:
        item.close()


def history(product):
    result = product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY, product.profile_id, product.timeline_id))
    assert result.status == "available"
    return result.projection.turns


def seed(product, adapter):
    assert send(product, "先打个招呼。", "s111-seed-intro").status == "terminal"
    for index in range(2):
        assert settle(product.application, product.application.simulate_first_life_step(
            FirstLifeSimulationRequest(f"s111-seed-life-{index}"))).status == "terminal"
    shared = settle(product.application, product.application.heartbeat_first_life(
        FirstLifeHeartbeatRequest("s111-seed-session-0001", "s111-seed-share-0001")))
    assert shared.status == "terminal", shared
    assert settle(product.application, product.application.set_first_life_controls(
        FirstLifeControlRequest("s111-pause-seeded-life", paused=True, sharing_enabled=False))).status == "terminal"
    assert len(product.application.query_first_life().shares) == 1


@pytest.mark.parametrize("route", [WHOLE_LOCAL_POLICY, PLANNED_LOCAL_POLICY])
@pytest.mark.parametrize("scenario_index", [0, 1])
def test_route_continues_its_own_eight_step_chain_and_keeps_judgment_facts(local_lab, route, scenario_index):
    opening, _, _, _, _ = local_lab
    frozen = json.loads((Path(__file__).resolve().parents[1] / "docs/experiments/s111/scenarios.json").read_text(encoding="utf-8"))
    scenario = frozen["scenarios"][scenario_index]
    adapter = LocalReplyAdapter("A" if route == WHOLE_LOCAL_POLICY else "B", scenario)
    product = opening(route, adapter)
    seed(product, adapter)
    bootstrap_calls = len(adapter.calls)
    steps = []
    initial_source_digest = None
    expected_plan = product.application.query_first_life().project.current_plan
    identity = product.profile_id, product.timeline_id
    for index, row in enumerate(scenario["turns"], 1):
        if row["kind"] == "explicit-context-reset":
            before = len(adapter.calls)
            reset = settle(product.application, product.application.reset_first_life_context(
                FirstLifeContextResetRequest("s111-explicit-context-reset", True)))
            assert reset.status == "terminal" and len(adapter.calls) == before
            steps.append(dict(step=index, kind="explicit-context-reset", local_calls=0,
                meaning="previous dialogue/share excluded; existing character/life use reaffirmed"))
            continue
        if row.get("restart_before"):
            saved = history(product)
            before = len(adapter.calls)
            product.close()
            product = opening(route, adapter)
            assert (product.profile_id, product.timeline_id) == identity
            assert history(product) == saved and len(adapter.calls) == before
        before = len(adapter.calls)
        previous = history(product)[-1].assistant_text
        adapter.use_life = index in (3, 4)
        result = send(product, row["user"], f"s111-route-{index}")
        assert result.status == "terminal", result
        calls = adapter.calls[before:]
        assert len(calls) == (1 if route == WHOLE_LOCAL_POLICY else 2)
        initial = calls[0][1]
        if index == 1:
            normalized = json.loads(canonical_json(initial))
            normalized.pop("policy")
            normalized["conversation"].pop("policy")
            initial_source_digest = sha256(canonical_json(normalized).encode()).hexdigest()
        sources = initial["dialogue_sources"]
        if index == 7:
            assert sources == []
        else:
            assert any(source["speaker"] == "assistant" and source["text"] == previous for source in sources)
        final = calls[-1][1]
        assert final["current_plan"] == asdict(expected_plan)
        assert final["related_event"] is not None  # Even when use_life is False.
        assert product.application.query_first_life().project.current_plan == expected_plan
        assert history(product)[-1].assistant_text == adapter.replies[-1]
        step = dict(step=index, user=row["user"], reply=adapter.replies[-1], local_calls=len(calls),
            source_texts=[source["text"] for source in sources], has_current_plan=True,
            disclosure_proposed=adapter.use_life, request_digest=sha256(canonical_json(final).encode()).hexdigest())
        if index in (1, 7):
            step["request_drafts"] = adapter.drafts[before:]
        steps.append(step)
    print("S111_ROUTE " + canonical_json(dict(route=route, scenario=scenario["id"],
        initial_source_digest=initial_source_digest,
        canonical_turns=len(history(product)), seed_calls=bootstrap_calls, chat_calls=len(adapter.calls) - bootstrap_calls,
        real_provider_calls=0, semantic_quality="not-evaluated-scripted-output", steps=steps)))


@pytest.mark.parametrize("route", [WHOLE_LOCAL_POLICY, PLANNED_LOCAL_POLICY])
@pytest.mark.parametrize("disclose", [False, True])
def test_having_life_facts_is_not_automatic_disclosure(local_lab, route, disclose):
    opening, _, _, _, _ = local_lab
    adapter = LocalReplyAdapter()
    product = opening(route, adapter)
    assert settle(product.application, product.application.simulate_first_life_step(FirstLifeSimulationRequest("s111-disclosure-seed"))).status == "terminal"
    adapter.use_life = disclose
    assert send(product, "随便聊聊。", "s111-disclosure-chat").status == "terminal"
    assert adapter.calls[-1][1]["current_plan"] is not None
    before = len(adapter.calls)
    shared = settle(product.application, product.application.heartbeat_first_life(
        FirstLifeHeartbeatRequest("s111-disclosure-session", "s111-disclosure-share")))
    assert shared.status == "terminal"
    assert len(adapter.calls) == before + (0 if disclose else 1)
    assert len(product.application.query_first_life().shares) == (0 if disclose else 1)


def test_local_binding_cannot_reopen_remote_switch_routes_or_claim_with_remote_gateway(local_lab):
    from dynamic_subject_agent.local_product import open_local_product
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    opening, config, view, budget, scope = local_lab
    adapter = LocalReplyAdapter()
    product = opening(WHOLE_LOCAL_POLICY, adapter)
    identity = product.profile_id
    assert send(product, "你好。", "s111-local-binding").status == "terminal"
    product.close()
    before = config.state_path.read_bytes()
    counts = FirstLifeBudget(budget).counts()
    with pytest.raises(ValueError, match="local-only"):
        open_first_life_product(config, definition_basis=view.definition_basis, life_scope_digest=scope,
            budget_path=budget, development_run=True)
    with pytest.raises(ValueError, match="local-only"):
        open_local_product(config, cognition=DormantDeepSeekCognition())
    with pytest.raises(ValueError):
        opening(PLANNED_LOCAL_POLICY, adapter)
    with pytest.raises(ValueError):
        LocalIdentityAuthority(config).first_life_runtime_policy(identity,
            runtime_policy=FOLLOWUP_VERSION, runtime_policy_digest=v4_digest(view.definition_basis))
    remote = LocalReplyAdapter()
    remote.capabilities = replace(remote.capabilities, local=False)
    with pytest.raises(ValueError, match="local-only"):
        opening(WHOLE_LOCAL_POLICY, remote)
    assert remote.calls == [] and config.state_path.read_bytes() == before
    assert FirstLifeBudget(budget).counts() == counts


@pytest.mark.parametrize("route", [WHOLE_LOCAL_POLICY, PLANNED_LOCAL_POLICY])
def test_local_route_failure_has_no_reply_no_retry_and_history_off_is_respected(local_lab, route):
    opening, _, _, budget, _ = local_lab
    adapter = LocalReplyAdapter()
    product = opening(route, adapter)
    assert send(product, "旧话题。", "s111-failure-initial").status == "terminal"
    assert product.application.set_reviewed_character_history(False).status == "active"
    adapter.invalid = True
    before = len(adapter.calls)
    failed = send(product, "新的话题。", "s111-invalid-candidate")
    assert failed.status == "failed-closed" and len(adapter.calls) == before + 1
    assert adapter.calls[-1][1]["dialogue_sources"] == []
    assert len(history(product)) == 1
    used = FirstLifeBudget(budget).counts()[1]
    assert product.application.wait(failed.operation_ref, timeout_seconds=0).status == "failed-closed"
    assert len(adapter.calls) == before + 1 and FirstLifeBudget(budget).counts()[1] == used


@pytest.mark.parametrize("route", [WHOLE_LOCAL_POLICY, PLANNED_LOCAL_POLICY])
def test_prepared_local_reply_recovers_without_a_second_generation(local_lab, route, monkeypatch):
    opening, _, _, _, _ = local_lab
    adapter = LocalReplyAdapter()
    product = opening(route, adapter)
    original = TimelineEngine._hit
    def interrupt(engine, point):
        original(engine, point)
        if point is FaultPoint.AFTER_PLAN_CLAIM:
            raise OSError("synthetic interruption after durable local reply preparation")
    monkeypatch.setattr(TimelineEngine, "_hit", interrupt)
    failed = send(product, "准备一轮。", "s111-prepared-local")
    assert failed.status != "terminal"
    count = len(adapter.calls)
    product.close()
    monkeypatch.setattr(TimelineEngine, "_hit", original)
    restored = opening(route, adapter)
    assert len(adapter.calls) == count
    assert history(restored)[0].assistant_text == adapter.replies[-1]


@pytest.mark.parametrize("route", [WHOLE_LOCAL_POLICY, PLANNED_LOCAL_POLICY])
def test_route_checks_one_or_two_stage_allowance_and_rechecks_local_gateway(local_lab, route, monkeypatch):
    opening, _, _, budget, _ = local_lab
    adapter = LocalReplyAdapter()
    product = opening(route, adapter)
    with monkeypatch.context() as patch:
        patch.setattr(FirstLifeBudget, "counts", lambda self: (200, 199, 1))
        patch.setattr(FirstLifeBudget, "life_counts", lambda self, day, development_run: (0, 0, 1))
        result = send(product, "只有一次机会。", "s111-single-stage-allowance")
    result = product.application.follow(result.operation_ref)
    assert result.status == ("terminal" if route == WHOLE_LOCAL_POLICY else "unavailable"), result
    if route == PLANNED_LOCAL_POLICY:
        assert result.projection.failure_code == "first-life-budget-unavailable"
    assert len(adapter.calls) == (1 if route == WHOLE_LOCAL_POLICY else 0)
    counts = FirstLifeBudget(budget).counts()
    opening.gateway.capabilities = replace(opening.gateway.capabilities, local=False)
    before = len(adapter.calls)
    denied = send(product, "不能变成远程。", "s111-local-recheck")
    denied = product.application.follow(denied.operation_ref)
    assert denied.status == "failed-closed", denied
    assert denied.projection.failure_code == "first-life-local-route-required"
    assert len(adapter.calls) == before and FirstLifeBudget(budget).counts() == counts


@pytest.mark.parametrize("route", [WHOLE_LOCAL_POLICY, PLANNED_LOCAL_POLICY])
def test_history_revocation_during_generation_cannot_publish_local_reply(local_lab, route):
    opening, _, _, _, _ = local_lab
    adapter = LocalReplyAdapter()
    product = opening(route, adapter)
    adapter.on_call = lambda: product.application.set_reviewed_character_history(False)
    result = send(product, "这轮权限会变化。", "s111-local-history-revoked")
    assert result.status == "failed-closed"
    assert len(adapter.calls) == 1 and history(product) == ()


def test_an_activated_existing_branch_cannot_be_repurposed_as_a_reply_lab(local_lab):
    from test_first_life_followup import FollowupTransport
    opening, config, view, budget, scope = local_lab
    old = open_first_life_product(config, definition_basis=view.definition_basis, life_scope_digest=scope,
        budget_path=budget, development_run=True, _transport=FollowupTransport(),
        runtime_policy=FOLLOWUP_VERSION, runtime_policy_digest=v4_digest(view.definition_basis))
    old.close()
    before = config.state_path.read_bytes()
    with pytest.raises(ValueError, match="existing route"):
        opening(WHOLE_LOCAL_POLICY, LocalReplyAdapter())
    assert config.state_path.read_bytes() == before


@pytest.mark.parametrize("missing", ["policy", "activation-witness"])
def test_missing_local_route_marker_cannot_fall_back_to_remote(local_lab, missing):
    opening, config, view, budget, scope = local_lab
    product = opening(WHOLE_LOCAL_POLICY, LocalReplyAdapter())
    product.close()
    state = json.loads(config.state_path.read_text(encoding="utf-8"))
    record = next(row for row in state["identities"] if row["identity_id"] == state["active_identity_id"])
    if missing == "policy":
        record.pop("life_runtime_policy")
    else:
        record["life_activation"].pop("local_reply_route")
    config.state_path.write_text(canonical_json(state), encoding="utf-8")
    with pytest.raises(RuntimeError, match="local-reply-activation-invalid"):
        open_first_life_product(config, definition_basis=view.definition_basis, life_scope_digest=scope,
            budget_path=budget, development_run=True)
