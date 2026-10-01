"""Focused runner checks; no live model, credential lookup or large trial matrix."""
from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from dynamic_subject_agent.character_chat_budget import CharacterChatBudget
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse
from dynamic_subject_agent.first_life_reply_drafts import reply_scope_digest
from dynamic_subject_agent.first_life_reply_routes import WHOLE_LOCAL_POLICY, WHOLE_REPLY_POLICY
from dynamic_subject_agent.local_product import open_first_life_reply_lab
from dynamic_subject_agent.model_gateway import (ModelGateway, ModelResult, ModelTaskKind,
    ProviderAdapter, ProviderCapabilities, StructuredOutputMode)
from test_s109_continuous_baseline import no_remote_io


PATH = Path(__file__).resolve().parents[1] / "scripts/run_s112_reply_comparison.py"
SPEC = importlib.util.spec_from_file_location("s112_comparison_runner", PATH)
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


@pytest.fixture
def specification():
    return json.loads(runner.SCENARIOS_PATH.read_text(encoding="utf-8"))


class CaptureFirstReply(ProviderAdapter):
    capabilities = ProviderCapabilities("synthetic-local-s112", "fixed", True, (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self):
        self.calls = []

    def invoke(self, task):
        assert task.kind is ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY
        self.calls.append(task)
        return ModelResult(task.kind, dict(reply_text="合成验收回复。", language="zh", use_life=False))


def test_original_material_and_programmed_seed_match_the_frozen_S111_request(tmp_path, specification):
    scenario = specification["scenarios"][0]
    branch = runner.prepare_branch(tmp_path / "objects-and-versions-A", specification)
    twin = runner.prepare_branch(tmp_path / "objects-and-versions-B", specification)
    assert branch.definition_basis == twin.definition_basis
    assert branch.runtime_asset_sha == twin.runtime_asset_sha
    assert branch.config.state_path != twin.config.state_path
    asset = json.loads((branch.config.state_path.parent / "authoring/runtime-asset.json").read_text(encoding="utf-8"))
    assert [row["statement"] for row in asset["eligible"]] == [row["text"] for row in specification["character"]["facts"]]
    assert asset["personality"][0]["support_includes_belief"] is True
    assert asset["subject"]["name"] == "小林"
    budget = branch.config.state_path.parent / "local-budget"
    CharacterChatBudget(budget, total=200, initial_used=61, initialize=True)
    def opening(adapter):
        return open_first_life_reply_lab(branch.config, definition_basis=branch.definition_basis,
            life_scope_digest=branch.life_scope_digest, budget_path=budget,
            runtime_policy=WHOLE_LOCAL_POLICY,
            runtime_policy_digest=reply_scope_digest(branch.definition_basis, WHOLE_LOCAL_POLICY),
            gateway=ModelGateway(adapter), _clock=lambda: 0.0, _civil_day=lambda: "2026-10-01")
    seed = runner.SeedAdapter(specification, scenario)
    with opening(seed) as product:
        record = runner.seed_branch(product, seed)
        saved = runner.read_history(product)
        identity = product.profile_id, product.timeline_id
    assert record["real_provider_calls"] == 0 and len(record["calls"]) == 4
    assert record["status"]["paused"] is True and record["status"]["sharing_enabled"] is False
    assert record["life"]["shares"][0]["text"] == scenario["share"]
    reply = CaptureFirstReply()
    with opening(reply) as product:
        assert (product.profile_id, product.timeline_id) == identity
        assert runner.read_history(product) == saved and not reply.calls
        result = runner.send(product, scenario["turns"][0]["user"], "s112-test-first-frozen-chat")
        assert result.status == "terminal"
        assert runner.read_history(product)[-1].assistant_text == "合成验收回复。"
    payload = asdict(reply.calls[0].payload)
    normalized = json.loads(runner.canonical_json(payload))
    normalized.pop("policy")
    normalized["conversation"].pop("policy")
    report = json.loads((PATH.parents[1] / "docs/reports/2026-10-01-slice-111/continuous-comparison.json").read_text(encoding="utf-8"))
    expected = next(row["initial_source_digest"] for row in report["chains"] if row["scenario"] == scenario["id"])
    assert runner.digest(normalized) == expected
    with pytest.raises(ValueError, match="seed-cannot-answer"):
        seed.invoke(reply.calls[0])


def test_runner_preserves_a_stage_if_following_facade_work_fails_and_never_retries(tmp_path, specification, monkeypatch):
    """A runner unit fault, deliberately separate from canonical product proof above."""
    approval = SimpleNamespace(root=tmp_path, scenarios=specification, observations=[])
    attempted = []
    monkeypatch.setattr(runner, "prepare_branch", lambda root, _: runner.PreparedBranch(
        SimpleNamespace(state_path=root / "state.json"), "same-definition", "scope", "asset", "material"))
    monkeypatch.setattr(runner, "seed_branch", lambda *args: dict(source_digest="same-seed"))
    class Product:
        profile_id = "same-profile"
        timeline_id = "synthetic-test-timeline"
        def __init__(self, branch_id):
            self.branch_id = branch_id
        def close(self):
            pass
    def opening(config, *, branch_id, **kwargs):
        return Product(branch_id)
    def fail_after_stage(product, message, key):
        attempted.append((product.branch_id, key))
        approval.observations.append(dict(branch_id=product.branch_id, task_kind="synthetic-test-stage",
            payload=dict(conversation=dict(current_message=message)), value=dict(reply_text="已得到的合成原回复。")))
        raise RuntimeError("DO_NOT_LOG_ARBITRARY_ERROR_OR_CREDENTIAL_TEXT")
    monkeypatch.setattr(runner, "send", fail_after_stage)
    summary = runner.run_comparison(approval, opener=opening)
    assert len(attempted) == 4 and len(set(attempted)) == 4
    assert all(row["status"] == "stopped-technical-failure" for row in summary["branches"])
    raw = (tmp_path / "continuous-results.jsonl").read_text(encoding="utf-8")
    assert "DO_NOT_LOG_ARBITRARY_ERROR_OR_CREDENTIAL_TEXT" not in raw
    rows = [json.loads(line) for line in raw.splitlines()]
    stages = [row for row in rows if row["event"] == "stage-observed"]
    assert len(stages) == 4
    assert all(row["value"]["reply_text"] == "已得到的合成原回复。" for row in stages)
    for stage in stages:
        stopped = next(row for row in rows if row["event"] == "branch-stopped" and row["branch_id"] == stage["branch_id"])
        assert rows.index(stage) < rows.index(stopped)
    assert len(approval.observations) == 4
    with pytest.raises(FileExistsError):
        runner.run_comparison(approval, opener=opening)
    assert len(attempted) == 4


class FrozenTrialTransport(DeepSeekTransport):
    """Exercise live admission/tickets with locally synthesized HTTPS responses."""

    def __init__(self):
        self.calls = []

    def post_json(self, **kwargs):
        wire = json.loads(kwargs["body"])
        payload = json.loads(wire["messages"][1]["content"])
        assert "conversation" in payload, "real-adapter path cannot request life/share seed generation"
        self.calls.append(payload)
        if payload["policy"] == WHOLE_REPLY_POLICY:
            value = dict(reply_text=f"合成独立回复{len(self.calls)}。", language="zh", use_life=False)
        elif "selected_dialogue" in payload:
            value = dict(reply_text=f"合成独立回复{len(self.calls)}。", language="zh")
        else:
            value = dict(action="answer", fact_refs=[], use_life=False, focus="respond-current",
                dialogue_refs=[row["label"] for row in payload["dialogue_sources"]][-2:])
        body = dict(model="deepseek-flash", choices=[dict(finish_reason="stop",
            message=dict(role="assistant", content=runner.canonical_json(value), reasoning_content="EXCLUDED_RAW_REASONING"))],
            usage=dict(prompt_tokens=10, completion_tokens=5, total_tokens=15))
        return DeepSeekHttpResponse(200, runner.canonical_json(body).encode())


def test_live_qualified_runner_uses_all_frozen_chains_with_synthetic_transport(tmp_path, monkeypatch):
    from dynamic_subject_agent.first_life_reply_live import open_approved_trial
    monkeypatch.setattr("dynamic_subject_agent.first_life.current_civil_day", lambda: "2026-10-01")
    approval = open_approved_trial(tmp_path / "synthetic-trial", runner.SCENARIOS_PATH, confirmed=True, live=False)
    transport = FrozenTrialTransport()
    result = runner.run_comparison(approval, transport=transport)
    assert [branch["status"] for branch in result["branches"]] == ["completed"] * 4, result
    assert len(transport.calls) == 42 and approval.shared_budget().counts() == (42, 42, 0)
    for branch in result["branches"]:
        steps = branch["steps"]
        assert len(steps) == 8
        expected_calls = 1 if branch["branch_id"].endswith("-A") else 2
        assert [len(step["stages"]) for step in steps] == [expected_calls] * 5 + [0, expected_calls, expected_calls]
        assert not steps[6]["stages"][0]["payload"]["dialogue_sources"]
        after_restart = steps[7]["stages"][0]["payload"]["dialogue_sources"]
        assert any(row["text"] == steps[6]["reply"] for row in after_restart)
        assert steps[-1]["canonical_history"][-1]["assistant_text"] == steps[-1]["reply"]
    for scenario in approval.scenarios["scenarios"]:
        pair = [branch for branch in result["branches"] if branch["branch_id"].startswith(scenario["id"])]
        assert len({branch["initial_source_digest"] for branch in pair}) == 1
    journal = (approval.root / "continuous-results.jsonl").read_text(encoding="utf-8")
    assert "EXCLUDED_RAW_REASONING" not in journal
    assert sum(json.loads(line)["event"] == "stage-observed" for line in journal.splitlines()) == 42
