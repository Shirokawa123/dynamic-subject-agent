"""Actual S117 inputs retain their bytes and authority in the offline preview.

These checks measure request differences and execution boundaries, not dialogue
quality. The archived original replies are not replaced by invented successes.
"""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

import pytest

from dynamic_subject_agent.first_life_development_trial import scoped_reply_wire
from dynamic_subject_agent.first_life_reply_candidate import recorded_reply_task
from dynamic_subject_agent.first_life_reply_routes import REPLY_POLICIES
from dynamic_subject_agent.first_life_self_choice_candidate import (
    CANDIDATE_VERSION, EVIDENCE_AFTER, REPAIR_AFTER, preview_self_choice_candidate,
)
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import (
    ModelGateway, ModelGatewayFailure, ModelTaskKind, ProviderAdapter,
    ProviderCapabilities, StructuredOutputMode,
)
from test_s109_continuous_baseline import no_remote_io


REPORT = json.loads((Path(__file__).resolve().parents[1]
    / "docs/reports/2026-10-01-slice-117/continuous-comparison.json").read_text(encoding="utf-8"))
CASES = [row for row in REPORT["observations"] if row["event"] == "stage-observed"
    and (row["branch_id"], row["step"]) in {
        ("objects-and-versions-A", 3), ("objects-and-versions-A", 5),
        ("plan-versus-completion-A", 3), ("plan-versus-completion-A", 7),
    }]


@pytest.mark.parametrize("case", CASES, ids=lambda row: f'{row["branch_id"]}-{row["step"]}')
def test_only_two_system_paragraphs_change_in_actual_s117_requests(case):
    task = recorded_reply_task(case["task_kind"], case["payload"])
    original_payload = canonical_json(asdict(task.payload))
    baseline = scoped_reply_wire(task)
    assert baseline == canonical_json(case["request_body"]).encode()
    preview = preview_self_choice_candidate(task)
    assert preview.baseline_wire == baseline
    assert preview.baseline_wire_sha256 == sha256(baseline).hexdigest()
    assert preview.candidate_wire_sha256 == sha256(preview.wire).hexdigest()
    assert preview.source_payload_sha256 == sha256(original_payload.encode()).hexdigest()
    expected = json.loads(baseline)
    before = expected["messages"][0]["content"].split("\n")
    after = json.loads(preview.wire)["messages"][0]["content"].split("\n")
    assert len(before) == len(after)
    assert [i + 1 for i, pair in enumerate(zip(before, after)) if pair[0] != pair[1]] == [3, 5]
    assert [change.paragraph_number for change in preview.changed_paragraphs] == [3, 5]
    for change in preview.changed_paragraphs:
        assert change.before == before[change.paragraph_number - 1]
        assert change.after == after[change.paragraph_number - 1]
        before[change.paragraph_number - 1] = change.after
    expected["messages"][0]["content"] = "\n".join(before)
    assert preview.wire == canonical_json(expected).encode()
    # Exact wire equality above preserves every other value, including user data,
    # output contract/example, model settings and the history/reset window.
    assert after[2] == EVIDENCE_AFTER and after[4] == REPAIR_AFTER
    assert canonical_json(asdict(task.payload)) == original_payload
    assert scoped_reply_wire(task) == baseline
    assert preview.remote_use_authorized is False
    assert preview.semantic_quality == "not-evaluated-no-model-call"
    assert CANDIDATE_VERSION not in REPLY_POLICIES


def test_selected_archive_cases_include_repaired_history_and_empty_reset_history():
    assert len(CASES) == 4
    flower = next(row for row in CASES if row["branch_id"] == "objects-and-versions-A" and row["step"] == 3)
    assert len(flower["payload"]["dialogue_sources"]) == 4
    assert all(row["kind"] == "dialogue" for row in flower["payload"]["dialogue_sources"])
    shape = next(row for row in CASES if row["step"] == 7)
    assert shape["payload"]["dialogue_sources"] == []
    assert "画东西时我常" in shape["final_content"]  # Original failure remains.


def test_preview_is_not_executable_and_only_accepts_typed_a_task():
    class ForbiddenAdapter(ProviderAdapter):
        capabilities = ProviderCapabilities("local", "not-called", True,
            (StructuredOutputMode.JSON_OBJECT,))
        def invoke(self, task):
            pytest.fail("a self choice preview must not reach an adapter")
    case = CASES[0]
    task = recorded_reply_task(case["task_kind"], case["payload"])
    preview = preview_self_choice_candidate(task)
    with pytest.raises(ModelGatewayFailure, match="typed-model-task-required"):
        ModelGateway(ForbiddenAdapter()).execute(preview)
    with pytest.raises(ValueError, match="typed whole reply"):
        preview_self_choice_candidate(case["payload"])
    expression = next(row for row in REPORT["observations"] if row["event"] == "stage-observed"
        and row["task_kind"] == ModelTaskKind.CHARACTER_FIRST_LIFE_FACT_EXPRESSION.value)
    with pytest.raises(ValueError, match="typed whole reply"):
        preview_self_choice_candidate(recorded_reply_task(expression["task_kind"], expression["payload"]))
