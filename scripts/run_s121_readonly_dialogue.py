"""Owned synthetic text through Facade: readonly negation, withdrawal and recovery."""
import argparse
from dataclasses import asdict
import json
from uuid import uuid4

from dynamic_subject_agent.first_life import FirstLifeContextResetRequest
from dynamic_subject_agent.first_life_free_input_trial import open_free_input_reply_trial, fixed_free_input_runs_root
from dynamic_subject_agent.local_product import open_first_life_free_input_trial
from dynamic_subject_agent.model_gateway import ModelGateway
from dynamic_subject_agent.frozen_attempt import canonical_json
from run_s112_reply_comparison import (SCENARIOS_PATH, prepare_branch, SeedAdapter, seed_branch,
    read_history, send, settle, Journal)


ORIGINAL_QUESTION = "你开头那条近况说右边没留东西，但保存的方案里书一直在。你想怎么说明？"


def run(*, live, root, transport=None):
    trial = open_free_input_reply_trial(root, SCENARIOS_PATH, live=live, confirmed=True,
        expression_variant="current-topic")
    scenario = trial.scenarios["scenarios"][0]
    branch_id = scenario["id"] + "-A"
    branch = prepare_branch(root / branch_id, trial.scenarios)

    def opening(seed_gateway=None):
        return open_first_life_free_input_trial(branch.config, approval=trial, branch_id=branch_id,
            definition_basis=branch.definition_basis, life_scope_digest=branch.life_scope_digest,
            seed_gateway=seed_gateway, _transport=None if seed_gateway else transport)

    adapter = SeedAdapter(trial.scenarios, scenario)
    with opening(ModelGateway(adapter)) as seeded:
        seed = seed_branch(seeded, adapter)
    journal = Journal(root / "s121-dialogue.jsonl")
    summary = dict(version="s121-owned-readonly-dialogue-1", live=live, root=str(root),
        run_digest=trial.manifest_digest, seed_source_digest=seed["source_digest"], steps=[],
        status="stopped-failure", automatic_retries=0, private_user_content_exported=False)
    product = opening()

    def check(condition):
        if not condition:
            raise ValueError("s121-observed-behavior-mismatch")

    def contribute(label, text, expected, expected_calls):
        before = len(trial.observations)
        journal.append(dict(event="started", label=label, user_text=text))
        response = send(product, text, "s121-owned-" + label)
        row = dict(label=label, user_text=text, status=response.status.value,
            failure_code=getattr(response.projection, "failure_code", None),
            assistant_text=getattr(response.projection, "expression_text", None),
            observations=trial.observations[before:],
            canonical_history=[asdict(turn) for turn in read_history(product)])
        summary["steps"].append(row)
        journal.append(dict(event="finished", **row))
        check(response.status.value == expected and len(row["observations"]) == expected_calls)

    def reopen(label):
        nonlocal product
        saved = read_history(product)
        before = len(trial.observations)
        product.close()
        product = opening()
        check(read_history(product) == saved and len(trial.observations) == before)
        journal.append(dict(event="reopened", label=label, history_equal=True, additional_model_calls=0))

    try:
        contribute("original-question", ORIGINAL_QUESTION, "terminal", 1)
        contribute("continue-question", "明白了，书一直在右边。接着说说这幅构图里的留白吧。", "terminal", 1)
        reopen("after-readonly")
        check(product.application.set_reviewed_character_history(False).status == "active")
        contribute("history-off-question", "保存的方案里右边没有书吗？", "terminal", 1)
        contribute("source-restriction", "我不希望你使用保存的方案，可以吗？", "failed-closed", 0)
        reopen("after-source-restriction")
        contribute("unresolved-restriction", "接着聊这幅构图吧。", "failed-closed", 0)
        before = len(trial.observations)
        saved = read_history(product)
        reset = settle(product.application, product.application.reset_first_life_context(
            FirstLifeContextResetRequest("s121-owned-confirmed-context", True)))
        check(reset.status == "terminal" and len(trial.observations) == before and read_history(product) == saved)
        journal.append(dict(event="confirmed-context-reset", additional_model_calls=0, history_equal=True))
        check(product.application.set_reviewed_character_history(True).status == "active")
        contribute("fresh-readonly-question", "保存的构图里书不在右侧吗？", "terminal", 1)
        summary["status"] = "completed"
    except ValueError as error:
        if str(error) != "s121-observed-behavior-mismatch":
            raise
    finally:
        summary["actual_attempts"] = len(trial.observations)
        journal.append(dict(event="run-finished", status=summary["status"], actual_attempts=summary["actual_attempts"]))
        journal.close()
        product.close()
        (root / "s121-dialogue-summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    args = parser.parse_args()
    root = fixed_free_input_runs_root() / str(uuid4())
    print(canonical_json(dict(started_run=str(root))), flush=True)
    summary = run(live=args.live, root=root)
    print(canonical_json(dict(root=str(root), status=summary["status"], actual_attempts=summary["actual_attempts"])), flush=True)
    return 0 if summary["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
