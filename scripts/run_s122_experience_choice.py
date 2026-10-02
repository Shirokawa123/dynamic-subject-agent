"""Run four owned canonical chains with equal questions and different reasons."""
import argparse
import json
from pathlib import Path
from uuid import uuid4

from dynamic_subject_agent.first_life_free_input_trial import fixed_free_input_runs_root
from dynamic_subject_agent.frozen_attempt import canonical_json
from owned_dialogue_trial import OwnedDialogueBranch


PACKAGE = Path(__file__).resolve().parents[1] / "docs/experiments/s122/experience-choice.json"
STUDIES = {"experience-choice": PACKAGE,
    "proposal-source": PACKAGE.parents[1] / "s123/proposal-source.json"}


def run_branch(row, reason_index, *, live, root, transport=None, variant="current-topic"):
    messages = (row["common"], row["reasons"][reason_index], row["question"], row["after_reopen"])
    if row.get("source_check"):
        messages += (row["source_check"],)
    branch = OwnedDialogueBranch(root, row["scenario_id"], live=live, messages=messages,
        transport=transport, variant=variant)
    try:
        for index in range(len(messages)):
            if index == 3:
                branch.reopen()
            if branch.contribute(index) != "terminal":
                break
        return branch.finish()
    finally:
        branch.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--variant", default="current-topic")
    parser.add_argument("--study", choices=tuple(STUDIES), default="experience-choice")
    args = parser.parse_args()
    package = json.loads(STUDIES[args.study].read_text(encoding="utf-8"))
    results = []
    for row in package["cases"]:
        for index in row.get("reason_indices", range(2)):
            root = fixed_free_input_runs_root() / str(uuid4())
            print(canonical_json(dict(started_run=str(root), case=row["scenario_id"], reason=index)), flush=True)
            summary = run_branch(row, index, live=args.live, root=root, variant=args.variant)
            print(canonical_json(dict(root=str(root), status=summary["status"], actual_attempts=summary["actual_attempts"])), flush=True)
            results.append(summary)
    return 0 if all(row["status"] == "completed" for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
