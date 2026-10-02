"""Owned whole-chain checks for new topics, visible scope and history controls."""
import argparse
import json
from pathlib import Path
from uuid import uuid4

from dynamic_subject_agent.first_life_free_input_trial import fixed_free_input_runs_root
from dynamic_subject_agent.frozen_attempt import canonical_json
from owned_dialogue_trial import OwnedDialogueBranch


PACKAGE = Path(__file__).resolve().parents[1] / "docs/experiments/s124/conversation-scope.json"
SOURCE_PACKAGE = PACKAGE.with_name("source-cue.json")


def run_case(row, *, live, root, transport=None, history_controls=True):
    branch = OwnedDialogueBranch(root, row["scenario_id"], live=live, messages=row["messages"],
        variant="conversation", transport=transport)
    try:
        for index in range(len(row["messages"])):
            if history_controls and index in (2, 3):
                enabled = index == 3
                before = len(branch.trial.observations)
                assert branch.product.application.set_reviewed_character_history(enabled).status == "active"
                assert len(branch.trial.observations) == before
                branch.action("history-setting", enabled=enabled, additional_model_calls=0)
            if history_controls and index == 3:
                branch.reopen()
            if branch.contribute(index) != "terminal":
                break
        return branch.finish()
    finally:
        branch.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--source-cue", action="store_true")
    args = parser.parse_args()
    package = SOURCE_PACKAGE if args.source_cue else PACKAGE
    for row in json.loads(package.read_text(encoding="utf-8"))["cases"]:
        root = fixed_free_input_runs_root() / str(uuid4())
        print(canonical_json(dict(started_run=str(root), case=row["scenario_id"])), flush=True)
        result = run_case(row, live=args.live, root=root, history_controls=not args.source_cue)
        print(canonical_json(dict(root=str(root), status=result["status"], actual_attempts=result["actual_attempts"])), flush=True)


if __name__ == "__main__":
    main()
