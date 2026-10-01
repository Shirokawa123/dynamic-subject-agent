"""S114 approval tests on fresh synthetic 22-attempt parents; no real ledger."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from dynamic_subject_agent import first_life_candidate_trial as trial
from dynamic_subject_agent import first_life_reply_candidate as candidate
from dynamic_subject_agent import first_life_reply_live as parent_module
from dynamic_subject_agent.frozen_attempt import canonical_json
from scripts import run_s114_reply_comparison as runner
from test_s109_continuous_baseline import no_remote_io


ROOT = Path(__file__).resolve().parents[1]
PROPOSAL = ROOT / "docs/experiments/s113/continuous-proposal.json"
PACKAGE = PROPOSAL.with_name("reply-candidate.json")
SCENARIOS = ROOT / "docs/experiments/s111/scenarios.json"


def seed_terminal_parent(root, *, live=False):
    """Reusable synthetic prefix helper; never accepts an existing budget."""
    assert not root.exists()
    parent = parent_module.open_approved_trial(root, SCENARIOS, confirmed=True, live=live)
    budget = parent.shared_budget()
    for index in range(22):
        identity = sha256(b"synthetic-S114-parent").hexdigest()
        operation = sha256(f"synthetic-{index}".encode()).hexdigest()
        request = sha256(f"request-{index}".encode()).hexdigest()
        budget.claim(identity, operation, "expression", request)
        budget.record(identity, operation, "expression", status="complete", output_digest=request)
    assert budget.counts() == (42, 22, 20)
    return parent


@pytest.fixture
def parent(tmp_path):
    return seed_terminal_parent(tmp_path / "synthetic-parent")


@pytest.fixture
def approval(parent):
    return trial.open_approved_candidate_trial(parent.root / "candidate-s114", PROPOSAL, PACKAGE,
        parent=parent, confirmed=True, live=False)


def test_exact_approval_maps_only_the_new_short_sequences_and_preserves_parent(parent, approval, monkeypatch):
    parent_before = (parent.root / "approval.json").read_bytes()
    assert approval.parent_budget_path == parent.root / "real-budget"
    assert approval.parent_counts() == (42, 22, 20)
    assert approval.shared_budget().counts() == (18, 0, 18)
    assert approval.shared_budget().grant_digest == approval.manifest_digest
    assert approval.read()["background"] == parent.read()["background"]
    sequences = approval.scenarios["scenarios"]
    assert [len(row["turns"]) for row in sequences] == [3, 4]
    assert sum(step["kind"] == "chat" for row in sequences for step in row["turns"]) * 3 == 18
    assert sequences[1]["turns"][1]["kind"] == "explicit-context-reset"
    assert sequences[1]["turns"][-1]["restart_before"] is True
    branch_id = "objects-and-versions-A"
    assert approval.branch(branch_id)[1] == trial.WHOLE_CANDIDATE_POLICY
    assert approval.branch("objects-and-versions-B")[1] == trial.PLANNED_CANDIDATE_POLICY
    witness = approval.witness(branch_id)
    assert witness["kind"] == "s114-candidate"
    assert trial.candidate_trial_from_witness(witness).manifest_digest == approval.manifest_digest
    with pytest.raises(ValueError):
        trial.candidate_trial_from_witness({key: value for key, value in witness.items() if key != "kind"})
    monkeypatch.setattr("dynamic_subject_agent.first_life_candidate_budget.approve_candidate_allowance",
        lambda *a, **k: pytest.fail("an existing candidate root must not apply for its grant again"))
    reopened = trial.open_approved_candidate_trial(approval.root, PROPOSAL, PACKAGE,
        parent=parent, confirmed=True, live=False)
    assert reopened.manifest_digest == approval.manifest_digest
    assert (parent.root / "approval.json").read_bytes() == parent_before
    assert parent.shared_budget().counts() == (42, 22, 20)


@pytest.mark.parametrize("field", ["proposal", "package", "candidate_contract", "parent", "live", "root"])
def test_approval_tampering_is_not_accepted(approval, field):
    path = approval.root / "approval.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if field == "proposal":
        value[field]["sequences"][0]["steps"][0]["user"] = "unapproved message"
    elif field == "package":
        value[field]["cases"][0]["candidate_wire_utf8"] += " "
    elif field == "candidate_contract":
        value[field]["role_policy"] += "changed"
    elif field == "parent":
        value[field]["manifest_digest"] = "0" * 64
    elif field == "live":
        value[field] = True
    else:
        value[field] = str(approval.root.parent / "different-root")
    path.write_text(canonical_json(value), encoding="utf-8")
    with pytest.raises(ValueError):
        approval.read()


def test_current_builder_must_still_produce_all_reviewed_candidate_bytes(approval, monkeypatch):
    monkeypatch.setattr(candidate, "ROLE_POLICY", candidate.ROLE_POLICY + "unreviewed instruction")
    with pytest.raises(ValueError, match="reviewed exact bytes"):
        approval.read()


def test_partial_new_root_cannot_recreate_its_missing_grant(parent, monkeypatch):
    calls = []
    def interrupted(*args, **kwargs):
        calls.append(kwargs["grant_digest"])
        raise ValueError("synthetic interruption before allowance write")
    monkeypatch.setattr("dynamic_subject_agent.first_life_candidate_budget.approve_candidate_allowance", interrupted)
    root = parent.root / "candidate-s114"
    with pytest.raises(ValueError, match="synthetic interruption"):
        trial.open_approved_candidate_trial(root, PROPOSAL, PACKAGE, parent=parent, confirmed=True, live=False)
    assert (root / "approval.json").is_file()
    with pytest.raises(ValueError, match="grant witness"):
        trial.open_approved_candidate_trial(root, PROPOSAL, PACKAGE, parent=parent, confirmed=True, live=False)
    assert len(calls) == 1 and parent.shared_budget().counts() == (42, 22, 20)


def test_scope_digest_is_pure_and_changes_with_route_or_definition(monkeypatch):
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: pytest.fail("scope calculation must not read files"))
    whole = trial.candidate_reply_scope_digest("a" * 64, trial.WHOLE_CANDIDATE_POLICY)
    planned = trial.candidate_reply_scope_digest("a" * 64, trial.PLANNED_CANDIDATE_POLICY)
    another = trial.candidate_reply_scope_digest("b" * 64, trial.WHOLE_CANDIDATE_POLICY)
    assert len({whole, planned, another}) == 3
    with pytest.raises(ValueError):
        trial.candidate_reply_scope_digest("a" * 64, "first-life-whole-live-s112-1")


def test_new_user_sequence_is_checked_without_expanding_the_data_contract(approval):
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    row = package["cases"][0]
    payload = json.loads(json.loads(row["baseline_wire_utf8"])["messages"][1]["content"])
    task = candidate.recorded_reply_task(row["task_kind"], payload)
    # The S112 fixture's previous open invitation is deliberately not a S114
    # authorized user turn. Start with no historic turn for this scope test.
    task = replace(task, payload=replace(task.payload, dialogue_sources=()))
    approval.validate_task("objects-and-versions-A", task)
    old_only = replace(task, payload=replace(task.payload,
        conversation=replace(task.payload.conversation, current_message="随便聊聊，你想从哪儿说起？")))
    with pytest.raises(ValueError, match="current message"):
        approval.validate_task("objects-and-versions-A", old_only)


def test_offline_cannot_bind_or_write_a_live_parent_or_protected_root(tmp_path, parent, monkeypatch):
    protected = tmp_path / "mock-real-root"
    monkeypatch.setattr(trial, "fixed_live_root", lambda: protected)
    with pytest.raises(ValueError, match="offline candidate"):
        trial.open_approved_candidate_trial(protected / "candidate-s114", PROPOSAL, PACKAGE,
            parent=parent, confirmed=True, live=False)
    assert not protected.exists()
    monkeypatch.setattr(parent_module, "fixed_live_root", lambda: protected)
    simulated_live_parent = seed_terminal_parent(protected, live=True)
    with pytest.raises(ValueError, match="matching parent execution mode"):
        trial.open_approved_candidate_trial(protected / "candidate-s114", PROPOSAL, PACKAGE,
            parent=simulated_live_parent, confirmed=True, live=False)
    assert not (protected / "candidate-s114").exists()
    read_only = runner.open_existing_parent(protected, SCENARIOS)
    assert read_only.manifest_digest == simulated_live_parent.manifest_digest
    assert read_only.shared_budget().counts() == (42, 22, 20)
    missing = tmp_path / "missing-parent"
    with pytest.raises(ValueError, match="existing S112"):
        runner.open_existing_parent(missing, SCENARIOS)
    assert not missing.exists()


def test_runner_metadata_distinguishes_child_and_parent_without_reinitializing(approval, monkeypatch):
    calls = []
    def reused(*args, **kwargs):
        calls.append(kwargs)
        return dict(branches=[dict(branch_id="objects-and-versions-A", status="completed")])
    monkeypatch.setattr(runner, "run_comparison", reused)
    result = runner.run_candidate_comparison(approval, opener=object())
    assert result["version"] == "s114-candidate-comparison-runner-1"
    assert result["reused_runner_version"] == "s112-reply-comparison-runner-1"
    assert result["closing_counts"] == dict(candidate=dict(limit=18, used=0, available=18),
        parent=dict(limit=42, used=22, remaining=20))
    metadata = json.loads((approval.root / "candidate-run-metadata.json").read_text(encoding="utf-8"))
    assert metadata["authorization"] == trial.AUTHORIZATION
    assert metadata["parent"]["root"] == str(approval.root.parent)
    with pytest.raises(FileExistsError):
        runner.run_candidate_comparison(approval, opener=object())
    assert len(calls) == 1 and approval.parent_counts() == (42, 22, 20)
