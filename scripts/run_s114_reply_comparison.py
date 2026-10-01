"""Execute the approved S114 short chains using the existing continuous runner.

The inherited S112 version describes the reused runner/output format, not this
trial's approval. Separate metadata records S114, its 18 sublimit, and the parent
42-wide totals. This entrypoint cannot initialize a missing S112 parent ledger.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path

from dynamic_subject_agent.first_life_candidate_trial import (
    ApprovedCandidateTrial, AUTHORIZATION, PROPOSAL_DIGEST, PACKAGE_DIGEST,
    fixed_candidate_root, open_approved_candidate_trial,
)
from dynamic_subject_agent.first_life_reply_live import ApprovedReplyTrial, fixed_live_root
from dynamic_subject_agent.frozen_attempt import canonical_json

if __package__:
    from .run_s112_reply_comparison import run_comparison, VERSION as BASE_RUNNER_VERSION, SCENARIOS_PATH
else:
    from run_s112_reply_comparison import run_comparison, VERSION as BASE_RUNNER_VERSION, SCENARIOS_PATH


VERSION = "s114-candidate-comparison-runner-1"
PROPOSAL_PATH = Path(__file__).resolve().parents[1] / "docs/experiments/s113/continuous-proposal.json"
PACKAGE_PATH = PROPOSAL_PATH.with_name("reply-candidate.json")


def _write_new(path, value):
    with path.open("x", encoding="utf-8") as output:
        output.write(canonical_json(value) + "\n")
        output.flush()
        os.fsync(output.fileno())


def open_existing_parent(root, scenarios_path):
    """Read the already existing approved parent; never call its initializer."""
    root = Path(root).resolve()
    if not (root / "approval.json").is_file() or not (root / "real-budget/attempts.sqlite3").is_file():
        raise ValueError("the existing S112 approval and ledger are required")
    existing = json.loads((root / "approval.json").read_text(encoding="utf-8"))
    parent = ApprovedReplyTrial(root, sha256(canonical_json(existing).encode()).hexdigest())
    value = parent.read()
    if value["live"] is not True or value["scenarios"] != json.loads(scenarios_path.read_text(encoding="utf-8")):
        raise ValueError("the existing live S112 material must still match its approved file")
    return parent


def _counts(approval):
    child_total, child_used, child_available = approval.shared_budget().counts()
    parent_total, parent_used, parent_remaining = approval.parent_counts()
    return dict(candidate=dict(limit=child_total, used=child_used, available=child_available),
        parent=dict(limit=parent_total, used=parent_used, remaining=parent_remaining))


def run_candidate_comparison(approval, *, opener=None, transport=None):
    if type(approval) is not ApprovedCandidateTrial:
        raise ValueError("verified S114 candidate approval required")
    manifest = approval.read()
    metadata = dict(version=VERSION, authorization=AUTHORIZATION, approval_digest=approval.manifest_digest,
        proposal_sha256=PROPOSAL_DIGEST, package_sha256=PACKAGE_DIGEST,
        reused_runner_version=BASE_RUNNER_VERSION,
        inherited_output_note="continuous-results/summary keep the reused runner format; their approval is S114, not a S112 rerun",
        parent=manifest["parent"], live=manifest["live"], opening_counts=_counts(approval))
    _write_new(approval.root / "candidate-run-metadata.json", metadata)
    if opener is None:
        from dynamic_subject_agent.local_product import open_first_life_candidate_trial
        opener = open_first_life_candidate_trial
    summary = run_comparison(approval, opener=opener, transport=transport)
    result = dict(version=VERSION, authorization=AUTHORIZATION, approval_digest=approval.manifest_digest,
        reused_runner_version=BASE_RUNNER_VERSION, live=manifest["live"], closing_counts=_counts(approval),
        continuous_summary="continuous-summary.json", continuous_journal="continuous-results.jsonl",
        branches=[dict(branch_id=row["branch_id"], status=row["status"]) for row in summary["branches"]])
    _write_new(approval.root / "candidate-run-result.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--confirmed", action="store_true")
    args = parser.parse_args(argv)
    if not args.live or not args.confirmed:
        parser.error("S114 execution requires --live --confirmed for the already approved exact scope")
    parent = open_existing_parent(fixed_live_root(), SCENARIOS_PATH)
    approval = open_approved_candidate_trial(fixed_candidate_root(), PROPOSAL_PATH, PACKAGE_PATH,
        parent=parent, confirmed=True, live=True)
    result = run_candidate_comparison(approval)
    print(canonical_json(dict(result=str(approval.root / "candidate-run-result.json"), **result)))
    return 0 if all(row["status"] == "completed" for row in result["branches"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
