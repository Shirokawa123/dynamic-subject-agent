"""Offline preservation/compatibility checks; no claims about generated language."""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

import pytest

from dynamic_subject_agent.first_life_reply_candidate import (
    CANDIDATE_VERSION, recorded_reply_task, preview_reply_candidate,
)
from dynamic_subject_agent.first_life_reply_drafts import draft_wire
from dynamic_subject_agent.first_life_reply_routes import REPLY_POLICIES
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import (
    ModelGateway, ModelGatewayFailure, ProviderAdapter, ProviderCapabilities, StructuredOutputMode,
)
from test_s109_continuous_baseline import no_remote_io


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = json.loads((ROOT / "docs/experiments/s113/reply-candidate.json").read_text(encoding="utf-8"))
REPORT = json.loads((ROOT / PACKAGE["source_report"]).read_text(encoding="utf-8"))


def source_stage(case):
    branch = next(row for row in REPORT["branches"] if row["branch_id"] == case["branch_id"])
    step = next(row for row in branch["steps"] if row["step"] == case["step"])
    return step, step["stages"][-1]


@pytest.mark.parametrize("case", PACKAGE["cases"], ids=lambda row: row["case_id"])
def test_exact_existing_failures_have_lossless_review_bytes_and_unchanged_old_wire(case):
    step, stage = source_stage(case)
    untouched = canonical_json(stage["payload"])
    task = recorded_reply_task(stage["task_kind"], stage["payload"])
    preview = preview_reply_candidate(task)
    assert canonical_json(asdict(task.payload)) == untouched == canonical_json(stage["payload"])
    assert preview.wire == case["candidate_wire_utf8"].encode()
    assert sha256(preview.wire).hexdigest() == case["candidate_wire_sha256"]
    assert draft_wire(task) == case["baseline_wire_utf8"].encode()
    assert preview.baseline_wire_sha256 == stage["wire_sha256"] == case["baseline_wire_sha256"]
    assert preview.source_payload_sha256 == stage["request_digest"]
    assert step["reply"] == case["original_reply"] and stage["final_content"] == case["original_final_content"]
    baseline, candidate = json.loads(draft_wire(task)), json.loads(preview.wire)
    assert {key: value for key, value in baseline.items() if key != "messages"} == {
        key: value for key, value in candidate.items() if key != "messages"}
    assert [row["role"] for row in candidate["messages"]] == ["system", "user"]
    roles = json.loads(candidate["messages"][1]["content"])
    assert set(roles) == {"background", "evidence", "exchange", "turn"}
    original = stage["payload"]
    conversation = original["conversation"]
    # Every original non-policy field occurs once in one data role. Keeping the
    # full structures preserves fact qualifications and attributed source order.
    flattened = {key: value for role in roles.values() for key, value in role.items()}
    expected = {key: value for key, value in original.items() if key not in ("policy", "conversation")}
    expected.update({key: value for key, value in conversation.items() if key != "policy"})
    assert flattened == expected
    assert sum(len(role) for role in roles.values()) == len(flattened)
    assert preview.candidate_bytes < preview.baseline_bytes
    assert preview.remote_use_authorized is False
    assert preview.semantic_quality == "not-evaluated-no-model-call"


def test_reset_stays_empty_and_actual_post_reset_error_is_not_silently_rewritten():
    reset = next(row for row in PACKAGE["cases"] if row["step"] == 7)
    continuation = next(row for row in PACKAGE["cases"] if row["step"] == 8)
    reset_data = json.loads(json.loads(reset["candidate_wire_utf8"])["messages"][1]["content"])
    next_data = json.loads(json.loads(continuation["candidate_wire_utf8"])["messages"][1]["content"])
    assert reset_data["exchange"]["dialogue_sources"] == []
    assert reset_data["evidence"]["current_plan"] is not None
    assert any(row["speaker"] == "assistant" and row["text"] == reset["original_reply"]
        for row in next_data["exchange"]["dialogue_sources"])
    assert all(row["kind"] == "dialogue" for row in next_data["exchange"]["dialogue_sources"])


@pytest.mark.parametrize("change", ["extra-field", "disabled-history-with-text", "oversized-history", "oversized-current-message"])
def test_recorded_data_does_not_bypass_existing_input_bounds(change):
    _, stage = source_stage(PACKAGE["cases"][0])
    value = deepcopy(stage["payload"])
    if change == "extra-field":
        value["extra_history"] = "not an approved field"
    elif change == "disabled-history-with-text":
        value["history_enabled"] = False
    elif change == "oversized-history":
        value["dialogue_sources"][0]["text"] = "字" * 4001
    else:
        value["conversation"]["current_message"] = "字" * 1001
    with pytest.raises(ValueError, match="exact bounded recorded"):
        recorded_reply_task(stage["task_kind"], value)


def test_preview_is_not_an_executable_task_and_package_digest_covers_exact_bytes():
    class NoInvocation(ProviderAdapter):
        capabilities = ProviderCapabilities("local", "not-invoked", True, (StructuredOutputMode.JSON_OBJECT,))
        def invoke(self, task):
            pytest.fail("preview must never enter a Gateway")
    _, stage = source_stage(PACKAGE["cases"][0])
    task = recorded_reply_task(stage["task_kind"], stage["payload"])
    with pytest.raises(ModelGatewayFailure, match="typed-model-task-required"):
        ModelGateway(NoInvocation()).execute(preview_reply_candidate(task))
    assert CANDIDATE_VERSION not in REPLY_POLICIES
    package = dict(PACKAGE)
    expected = package.pop("package_sha256")
    assert sha256(canonical_json(package).encode()).hexdigest() == expected
    assert PACKAGE["source_evidence_digest"] == REPORT["evidence_digest"]
    assert sha256(canonical_json(REPORT).encode()).hexdigest() == PACKAGE["source_json_sha256"]
    report_content = dict(REPORT)
    recorded_evidence = report_content.pop("evidence_digest")
    assert sha256(canonical_json(report_content).encode()).hexdigest() == recorded_evidence
    with pytest.raises(ValueError):
        recorded_reply_task("character-communication-plan", stage["payload"])
