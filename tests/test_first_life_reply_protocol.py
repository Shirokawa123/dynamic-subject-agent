"""Same strict output boundary, one request variable, and offline failure evidence."""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import importlib.util
import json
from pathlib import Path

import pytest

from dynamic_subject_agent.cognition import CredentialRef
from dynamic_subject_agent.deepseek import DeepSeekHttpResponse, DeepSeekResponseDiagnosticFailure, _post_json_reply_content
from dynamic_subject_agent.first_life_reply_candidate import recorded_reply_task
from dynamic_subject_agent.first_life_reply_live_provider import _ObservedTransport
from dynamic_subject_agent.first_life_reply_protocol import EXAMPLE_BODY, output_example, preview_json_example, replay_recorded_reply
from dynamic_subject_agent.first_life_reply_routes import REPLY_POLICIES, validate_whole_reply
from dynamic_subject_agent.character_communication_plan import _validated_expression
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelTaskKind, ModelGateway, ModelGatewayFailure, ProviderAdapter, ProviderCapabilities, StructuredOutputMode
from test_s109_continuous_baseline import no_remote_io


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = json.loads((ROOT / "docs/experiments/s115/protocol-comparison.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", PACKAGE["cases"], ids=lambda row: row["case_id"])
def test_json_example_is_the_only_request_change_with_valid_original_schema(case):
    task = recorded_reply_task(case["task_kind"], case["payload"])
    before = canonical_json(asdict(task.payload))
    preview = preview_json_example(task)
    assert preview.wire.decode() == case["candidate_wire_utf8"]
    assert sha256(preview.wire).hexdigest() == case["candidate_wire_sha256"]
    baseline, candidate = json.loads(case["baseline_wire_utf8"]), json.loads(preview.wire)
    expected = deepcopy(baseline)
    expected["messages"][0]["content"] += preview.appended_system
    assert candidate == expected and preview.appended_system == case["appended_system"]
    assert candidate["messages"][1] == baseline["messages"][1]
    assert canonical_json(asdict(task.payload)) == before
    example = output_example(task.kind)
    assert json.loads(canonical_json(example)) == example
    if task.kind is ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY:
        assert validate_whole_reply(task.payload, example) == (EXAMPLE_BODY, False)
    else:
        assert _validated_expression(example) == EXAMPLE_BODY
    assert preview.remote_use_authorized is False and preview.version not in REPLY_POLICIES


def test_all_recorded_final_fields_keep_successes_and_reject_empty_without_raw_packet_claim():
    assert len(PACKAGE["replay"]) == 24
    results = [row["replay"] for row in PACKAGE["replay"]]
    assert sum(row["status"] == "structured" for row in results) == 18
    assert sum(row["diagnostic_code"] == "response-content-empty" for row in results) == 4
    assert sum(row["status"] == "unavailable" for row in results) == 2
    assert all(row["reconstruction"] == "retained-final-fields-not-original-http-envelope" for row in results)
    assert all(row["semantic_quality"] == "not-evaluated" for row in results)
    package = dict(PACKAGE)
    expected = package.pop("package_sha256")
    assert sha256(canonical_json(package).encode()).hexdigest() == expected
    spec = importlib.util.spec_from_file_location("prepare_s115", ROOT / "scripts/prepare_s115_protocol_trial.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.prepare_package() == PACKAGE


def _response_stage(value):
    case = PACKAGE["cases"][0]
    return dict(task_kind=case["task_kind"], payload=case["payload"], model="deepseek-flash",
        finish_reason="stop", usage=dict(prompt_tokens=10, completion_tokens=10), final_content=canonical_json(value))


@pytest.mark.parametrize("response", [
    dict(reply_text="合成正文", language="zh", use_life="false"),
    dict(reply_text="合成正文", language="zh", use_life=False, unexpected=True),
    dict(reply_text="", language="zh", use_life=False),
])
def test_protocol_inspection_keeps_original_strict_reply_validation(response):
    stage = _response_stage(response)
    before = canonical_json(stage)
    result = replay_recorded_reply(stage)
    assert result["status"] == "failed-closed" and result["diagnostic_code"] == "structured-choice-invalid"
    assert canonical_json(stage) == before


def test_valid_format_example_echo_is_not_silently_counted_as_usable_dialogue():
    result = replay_recorded_reply(_response_stage(dict(reply_text=EXAMPLE_BODY, language="zh", use_life=False)))
    assert result["status"] == "structured" and result["format_example_copied"] is True
    assert result["semantic_quality"] == "not-evaluated"


def test_blank_observation_precedes_reasoning_cleanup_and_content_parsing():
    final = PACKAGE["cases"][0]["original_final_content"]
    body = canonical_json(dict(model="deepseek-flash", choices=[dict(finish_reason="stop",
        message=dict(role="assistant", content=final, reasoning_content="DO_NOT_COPY_HIDDEN_REASONING"))],
        usage=dict(prompt_tokens=10, completion_tokens=20))).encode()
    class RetainedFieldsTransport:
        calls = 0
        def post_json(self, **kwargs):
            self.calls += 1
            return DeepSeekHttpResponse(200, body)
    transport = RetainedFieldsTransport()
    observed = _ObservedTransport(transport)
    with pytest.raises(DeepSeekResponseDiagnosticFailure) as error:
        _post_json_reply_content(observed, CredentialRef.reference(backend_id="offline", key_id="unused"),
            PACKAGE["cases"][0]["baseline_wire_utf8"].encode(), max_output_tokens=4096,
            require_complete=True, discard_reasoning=True, safe_diagnostics=True)
    assert error.value.diagnostic_code == "response-content-empty" and transport.calls == 1
    assert observed.row["final_content"] == final and body.decode().find("DO_NOT_COPY_HIDDEN_REASONING") >= 0
    assert "DO_NOT_COPY_HIDDEN_REASONING" not in canonical_json(observed.row)


def test_preview_cannot_be_executed_or_promoted_to_an_existing_runtime_route():
    class ForbiddenAdapter(ProviderAdapter):
        capabilities = ProviderCapabilities("local", "not-called", True, (StructuredOutputMode.JSON_OBJECT,))
        def invoke(self, task):
            pytest.fail("no execution is authorized by a format preview")
    case = PACKAGE["cases"][0]
    task = recorded_reply_task(case["task_kind"], case["payload"])
    with pytest.raises(ModelGatewayFailure, match="typed-model-task-required"):
        ModelGateway(ForbiddenAdapter()).execute(preview_json_example(task))
    with pytest.raises(ValueError):
        output_example(task.kind.value)
