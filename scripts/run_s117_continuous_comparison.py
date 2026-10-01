"""Run one complete frozen A/B comparison using the scoped JSON candidate."""
import argparse
from pathlib import Path
from uuid import uuid4

from dynamic_subject_agent.first_life_development_trial import open_development_reply_trial, fixed_continuous_runs_root
from dynamic_subject_agent.local_product import open_first_life_development_trial
from dynamic_subject_agent.frozen_attempt import canonical_json

if __package__:
    from .run_s112_reply_comparison import run_comparison, SCENARIOS_PATH
else:
    from run_s112_reply_comparison import run_comparison, SCENARIOS_PATH


def run_once(root: Path, *, live, transport=None):
    approval = open_development_reply_trial(root, SCENARIOS_PATH, live=live)
    summary = run_comparison(approval, opener=open_first_life_development_trial, transport=transport)
    return approval, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if not args.live:
        parser.error("actual execution requires --live; offline checks inject synthetic transport")
    root = fixed_continuous_runs_root() / str(uuid4())
    print(canonical_json(dict(started_run=str(root), call_limit=None)), flush=True)
    approval, summary = run_once(root, live=True)
    print(canonical_json(dict(root=str(root), calls=len(approval.observations), call_limit=None,
        branches=[dict(branch_id=row["branch_id"], status=row["status"]) for row in summary["branches"]])))
    return 0 if all(row["status"] == "completed" for row in summary["branches"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
