"""Full canonical S117 chains plus durable one-shot development claims."""
from dataclasses import asdict
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
from uuid import uuid4

import pytest

from dynamic_subject_agent.character_chat_budget import CharacterChatBudget
from dynamic_subject_agent.cognition import CredentialRef
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse, DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID
from dynamic_subject_agent.first_life_budget import FirstLifeBudget
from dynamic_subject_agent.first_life_development_trial import (open_development_reply_trial, DevelopmentReplyBudget,
    DevelopmentReplyAdapter, scoped_reply_wire, OFFLINE_BACKEND, OFFLINE_KEY)
from dynamic_subject_agent.first_life_reply_protocol import EXAMPLE_BODY
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelTaskKind, ModelGatewayFailure, ModelGateway
from dynamic_subject_agent.reply_protocol_trial import GLOBAL_STYLE_SENTENCE, REPLY_TEXT_STYLE_SENTENCE
from test_s109_continuous_baseline import no_remote_io


PATH = Path(__file__).resolve().parents[1] / "scripts/run_s117_continuous_comparison.py"
sys.path.insert(0, str(PATH.parent))
SPEC = importlib.util.spec_from_file_location("s117_comparison_runner", PATH)
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


class SyntheticTransport(DeepSeekTransport):
    def __init__(self, *, blank=False):
        self.calls, self.blank = [], blank

    def post_json(self, **kwargs):
        wire = json.loads(kwargs["body"])
        material = json.loads(wire["messages"][1]["content"])
        self.calls.append(wire)
        if "turn" in material:
            assert GLOBAL_STYLE_SENTENCE not in wire["messages"][0]["content"]
            assert REPLY_TEXT_STYLE_SENTENCE in wire["messages"][0]["content"]
            value = dict(reply_text=f"合成独立回复{len(self.calls)}。", language="zh")
            if "action" not in material["turn"]:
                value["use_life"] = False
        else:
            assert wire["reasoning_effort"] == "low"
            value = dict(action="answer", fact_refs=[], use_life=False, focus="respond-current",
                dialogue_refs=[row["label"] for row in material["dialogue_sources"]][-2:])
        body = dict(model="deepseek-flash", choices=[dict(finish_reason="stop",
            message=dict(role="assistant", content="  " if self.blank else canonical_json(value),
                reasoning_content="DO_NOT_KEEP_HIDDEN_THOUGHT"))],
            usage=dict(prompt_tokens=10, completion_tokens=5, total_tokens=15))
        return DeepSeekHttpResponse(200, canonical_json(body).encode())


def test_all_full_chains_commit_and_cold_recover_without_old_quota(tmp_path, monkeypatch):
    monkeypatch.setattr("dynamic_subject_agent.first_life.current_civil_day", lambda: "2026-10-01")
    transport = SyntheticTransport()
    approval, summary = runner.run_once(tmp_path / str(uuid4()), live=False, transport=transport)
    assert [row["status"] for row in summary["branches"]] == ["completed"] * 4, summary
    assert len(transport.calls) == 42 and approval.shared_budget().counts() == (None, 42, None)
    for branch in summary["branches"]:
        steps = branch["steps"]
        assert len(steps) == 8
        expected = 1 if branch["branch_id"].endswith("-A") else 2
        assert [len(row["stages"]) for row in steps] == [expected] * 5 + [0, expected, expected]
        assert not steps[6]["stages"][0]["payload"]["dialogue_sources"]
        after_restart = steps[7]["stages"][0]["payload"]["dialogue_sources"]
        assert any(row["text"] == steps[6]["reply"] for row in after_restart)
        assert steps[-1]["canonical_history"][-1]["assistant_text"] == steps[-1]["reply"]
    journal = (approval.root / "continuous-results.jsonl").read_text(encoding="utf-8")
    assert "DO_NOT_KEEP_HIDDEN_THOUGHT" not in journal
    assert len({row["initial_source_digest"] for row in summary["branches"]}) == 2
    with pytest.raises(FileExistsError):
        runner.run_once(approval.root, live=False, transport=transport)
    assert len(transport.calls) == 42


def test_blank_stops_each_chain_without_repair_or_failed_reply_publication(tmp_path):
    transport = SyntheticTransport(blank=True)
    approval, summary = runner.run_once(tmp_path / str(uuid4()), live=False, transport=transport)
    assert len(transport.calls) == 4 and approval.shared_budget().counts() == (None, 4, None)
    for branch in summary["branches"]:
        assert branch["status"] == "stopped-technical-failure"
        assert len(branch["steps"]) == 1
        assert len(branch["steps"][0]["canonical_history"]) == 1  # only program seed
        assert branch["steps"][0]["reply"] is None


def test_claim_has_no_quantity_ceiling_and_cannot_recover_or_correct_into_resend(tmp_path):
    from dynamic_subject_agent.first_life_reply_candidate import recorded_reply_task
    package = json.loads((PATH.parents[1] / "docs/experiments/s115/protocol-comparison.json").read_text(encoding="utf-8"))
    case = package["cases"][0]
    task = recorded_reply_task(case["task_kind"], case["payload"])
    trial = open_development_reply_trial(tmp_path / str(uuid4()), runner.SCENARIOS_PATH, live=False)
    branch_id = "objects-and-versions-A"
    path = trial.root / branch_id / "local-stage-budget"
    CharacterChatBudget(path, initialize=True)
    local = FirstLifeBudget(path)
    budget = DevelopmentReplyBudget(local, trial, branch_id)
    request = sha256(canonical_json(asdict(task.payload)).encode()).hexdigest()
    identity = "1" * 64
    for i in range(205):
        operation = sha256(str(i).encode()).hexdigest()
        budget.claim_life(identity, operation, "expression", request,
            purpose="chat-expression", civil_day="2026-10-01", development_run=True)
        budget.consume(task)
        budget.record(identity, operation, "expression", status="unknown")
    assert budget.counts() == (None, 205, None) and budget.life_counts("2026-10-01", development_run=True)[2] is None
    assert budget.life_counts("2026-10-01", development_run=True)[:2] == (0, 0)
    operation = "2" * 64
    budget.claim_life(identity, operation, "expression", request,
        purpose="chat-expression", civil_day="2026-10-01", development_run=True)
    restored = DevelopmentReplyBudget(local, trial, branch_id)
    with pytest.raises(ValueError):
        restored.consume(task)
    with pytest.raises(ValueError):
        restored.claim_life(identity, operation, "expression", request,
            purpose="chat-expression", civil_day="2026-10-01", development_run=True)
    assert trial.shared_budget().counts() == (None, 206, None)


def test_offline_rejects_real_credential_and_no_ticket_cannot_send(tmp_path):
    from dynamic_subject_agent.first_life_reply_candidate import recorded_reply_task
    package = json.loads((PATH.parents[1] / "docs/experiments/s115/protocol-comparison.json").read_text(encoding="utf-8"))
    case = package["cases"][0]
    task = recorded_reply_task(case["task_kind"], case["payload"])
    trial = open_development_reply_trial(tmp_path / str(uuid4()), runner.SCENARIOS_PATH, live=False)
    branch_id = "objects-and-versions-A"
    path = trial.root / branch_id / "local-stage-budget"
    CharacterChatBudget(path, initialize=True)
    budget = DevelopmentReplyBudget(FirstLifeBudget(path), trial, branch_id)
    transport = SyntheticTransport()
    with pytest.raises(ValueError):
        DevelopmentReplyAdapter(transport, CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
            key_id=DEEPSEEK_CREDENTIAL_KEY_ID), budget, approval=trial, branch_id=branch_id)
    # No ticket is recovered from SQLite; a directly invoked valid task cannot send.
    adapter = DevelopmentReplyAdapter(transport, CredentialRef.reference(backend_id=OFFLINE_BACKEND,
        key_id=OFFLINE_KEY), budget, approval=trial, branch_id=branch_id)
    with pytest.raises(ModelGatewayFailure):
        ModelGateway(adapter).execute(task)
    assert not transport.calls


def test_template_echo_is_retained_but_rejected_and_scoped_wire_matches_the_measured_study(tmp_path):
    from dynamic_subject_agent.first_life_reply_candidate import recorded_reply_task
    from dynamic_subject_agent.reply_protocol_trial import open_protocol_run
    package_path = PATH.parents[1] / "docs/experiments/s115/protocol-comparison.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    case = package["cases"][0]
    task = recorded_reply_task(case["task_kind"], case["payload"])
    protocol = open_protocol_run(tmp_path / str(uuid4()), package_path, live=False, study="instruction-scope")
    assert scoped_reply_wire(task) == protocol.wire_for(protocol.request_for(case["case_id"], "reply-text-style"))
    trial = open_development_reply_trial(tmp_path / str(uuid4()), runner.SCENARIOS_PATH, live=False)
    branch_id = "objects-and-versions-A"
    path = trial.root / branch_id / "local-stage-budget"
    CharacterChatBudget(path, initialize=True)
    budget = DevelopmentReplyBudget(FirstLifeBudget(path), trial, branch_id)
    class EchoTransport(DeepSeekTransport):
        def post_json(self, **kwargs):
            value = dict(reply_text=EXAMPLE_BODY, language="zh", use_life=False)
            return DeepSeekHttpResponse(200, canonical_json(dict(model="deepseek-flash",
                choices=[dict(finish_reason="stop", message=dict(role="assistant", content=canonical_json(value)))],
                usage=dict(prompt_tokens=10, completion_tokens=5, total_tokens=15))).encode())
    adapter = DevelopmentReplyAdapter(EchoTransport(), CredentialRef.reference(backend_id=OFFLINE_BACKEND,
        key_id=OFFLINE_KEY), budget, approval=trial, branch_id=branch_id)
    from run_s112_reply_comparison import Journal, JournaledObservations
    journal = Journal(trial.root / "echo-observation.jsonl")
    adapter.rows = JournaledObservations([], journal)
    request = sha256(canonical_json(asdict(task.payload)).encode()).hexdigest()
    budget.claim_life("1"*64, "2"*64, "expression", request,
        purpose="chat-expression", civil_day="2026-10-01", development_run=True)
    with pytest.raises(ModelGatewayFailure, match="structured-choice-invalid"):
        ModelGateway(adapter).execute(task)
    journal.close()
    budget.record("1"*64, "2"*64, "expression", status="failed-closed")
    assert adapter.rows[0]["value"]["reply_text"] == EXAMPLE_BODY
    assert adapter.rows[0]["error_code"] == "structured-choice-invalid"
    recorded = json.loads((trial.root / "echo-observation.jsonl").read_text(encoding="utf-8"))
    assert recorded["error_code"] == "structured-choice-invalid"
