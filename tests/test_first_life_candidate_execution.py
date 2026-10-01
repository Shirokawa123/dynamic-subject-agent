"""S114 complete candidate chains and qualification through the real Facade."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from dynamic_subject_agent.deepseek import DeepSeekHttpResponse
from dynamic_subject_agent.first_life_reply_live import open_approved_trial
from dynamic_subject_agent.first_life_candidate_trial import open_approved_candidate_trial
from dynamic_subject_agent.local_product import (
    open_first_life_candidate_trial, open_first_life_reply_trial, open_first_life_product,
    open_local_product,
)
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.model_gateway import ModelGateway
from dynamic_subject_agent.timeline import FaultPoint, TimelineEngine
from dynamic_subject_agent.frozen_attempt import canonical_json
from test_s109_continuous_baseline import no_remote_io
from test_s112_reply_comparison import runner

ROOT = Path(__file__).resolve().parents[1]


def approval_at(tmp_path):
    parent = open_approved_trial(tmp_path / "parent", runner.SCENARIOS_PATH, confirmed=True, live=False)
    ledger = parent.shared_budget()
    for index in range(22):
        operation = sha256(f"prior-synthetic-stage-{index}".encode()).hexdigest()
        ledger.claim("1" * 64, operation, "expression", "2" * 64)
        ledger.record("1" * 64, operation, "expression", status="complete", output_digest="3" * 64)
    approval = open_approved_candidate_trial(parent.root / "candidate-s114",
        ROOT / "docs/experiments/s113/continuous-proposal.json", ROOT / "docs/experiments/s113/reply-candidate.json",
        parent=parent, confirmed=True, live=False)
    return approval, parent


class CandidateTransport:
    def __init__(self):
        self.calls = []
        self.after_call = None

    def post_json(self, **kwargs):
        wire = json.loads(kwargs["body"])
        payload = json.loads(wire["messages"][1]["content"])
        self.calls.append(wire)
        if "conversation" in payload:
            value = dict(action="answer", fact_refs=[], use_life=False, focus="respond-current",
                dialogue_refs=[r["label"] for r in payload["dialogue_sources"]][-2:])
        else:
            assert set(payload) == {"background", "evidence", "exchange", "turn"}
            value = dict(reply_text=f"本分支合成回复{len(self.calls)}。", language="zh")
            if "action" not in payload["turn"]:
                value["use_life"] = False
        if self.after_call:
            self.after_call()
        return DeepSeekHttpResponse(200, canonical_json(dict(model="deepseek-flash",
            choices=[dict(finish_reason="stop", message=dict(role="assistant", content=canonical_json(value)))],
            usage=dict(prompt_tokens=10, completion_tokens=5, total_tokens=15))).encode())


def test_candidate_runs_all_frozen_chains_on_one_parent_without_changing_old_approval(tmp_path):
    approval, parent = approval_at(tmp_path)
    original = (parent.root / "approval.json").read_bytes()
    transport = CandidateTransport()
    result = runner.run_comparison(approval, opener=open_first_life_candidate_trial, transport=transport)
    assert [r["status"] for r in result["branches"]] == ["completed"] * 4, result
    assert len(transport.calls) == 18 and approval.shared_budget().counts() == (18, 18, 0)
    assert parent.shared_budget().counts() == (42, 40, 2)
    assert (parent.root / "approval.json").read_bytes() == original
    for branch in result["branches"]:
        n = 1 if branch["branch_id"].endswith("-A") else 2
        steps = branch["steps"]
        assert [len(r["stages"]) for r in steps] == ([n] * 3 if branch["branch_id"].startswith("objects") else [n, 0, n, n])
        for step in steps:
            for stage in step["stages"]:
                assert sha256(canonical_json(stage["request_body"]).encode()).hexdigest() == stage["wire_sha256"]
            if step["stages"]:
                final = step["stages"][-1]
                actual = json.loads(final["request_body"]["messages"][1]["content"])
                assert "evidence" in actual and "policy" not in actual
                assert actual["evidence"]["current_plan"] == final["payload"]["current_plan"]
        if branch["branch_id"].startswith("plan"):
            assert not steps[2]["stages"][0]["payload"]["dialogue_sources"]
            assert any(r["text"] == steps[2]["reply"] for r in steps[3]["stages"][0]["payload"]["dialogue_sources"])
    for scenario in approval.scenarios["scenarios"]:
        pair = [r for r in result["branches"] if r["branch_id"].startswith(scenario["id"])]
        assert len({r["initial_source_digest"] for r in pair}) == 1


@pytest.fixture
def candidate_branch(tmp_path):
    approval, parent = approval_at(tmp_path)
    branch_id = "objects-and-versions-A"
    branch = runner.prepare_branch(approval.root / branch_id, approval.scenarios)
    scenario, _ = approval.branch(branch_id)
    def opening(**kwargs):
        return open_first_life_candidate_trial(branch.config, definition_basis=branch.definition_basis,
            life_scope_digest=branch.life_scope_digest, approval=approval, branch_id=branch_id, **kwargs)
    seed = runner.SeedAdapter(approval.scenarios, scenario)
    with opening(seed_gateway=ModelGateway(seed)) as product:
        runner.seed_branch(product, seed)
    return opening, approval, parent, branch, scenario


def test_candidate_prepared_recovery_does_not_reissue_a_parent_claim(candidate_branch, monkeypatch):
    opening, approval, parent, _, scenario = candidate_branch
    transport = CandidateTransport()
    original = TimelineEngine._hit
    def interrupt(engine, point):
        original(engine, point)
        if point is FaultPoint.AFTER_PLAN_CLAIM:
            raise OSError("synthetic interruption after preparation")
    with monkeypatch.context() as patch:
        patch.setattr(TimelineEngine, "_hit", interrupt)
        with opening(_transport=transport) as product:
            result = runner.send(product, scenario["turns"][0]["user"], "s114-prepared-response")
            assert result.status != "terminal"
    assert len(transport.calls) == 1 and parent.shared_budget().counts() == (42, 23, 19)
    with opening(_transport=transport) as product:
        assert len(runner.read_history(product)) == 2
    assert len(transport.calls) == 1 and approval.shared_budget().counts() == (18, 1, 17)


def test_candidate_qualification_cannot_use_old_entries_or_reseed_and_revocation_still_fences(candidate_branch):
    opening, approval, parent, branch, scenario = candidate_branch
    transport = CandidateTransport()
    with opening(_transport=transport) as product:
        transport.after_call = lambda: product.application.set_reviewed_character_history(False)
        result = runner.send(product, scenario["turns"][0]["user"], "s114-revoked-history")
        assert result.status == "failed-closed" and len(runner.read_history(product)) == 1
    with pytest.raises(ValueError):
        opening(seed_gateway=ModelGateway(runner.SeedAdapter(approval.scenarios, scenario)))
    with pytest.raises(ValueError):
        open_first_life_reply_trial(branch.config, approval=approval)
    with pytest.raises(ValueError):
        open_local_product(branch.config, cognition=DormantDeepSeekCognition())
    with pytest.raises(ValueError):
        open_first_life_product(branch.config, definition_basis=branch.definition_basis,
            life_scope_digest=branch.life_scope_digest, budget_path=branch.config.state_path.parent / "local-stage-budget")
    assert len(transport.calls) == 1 and parent.shared_budget().counts()[1] == 23
