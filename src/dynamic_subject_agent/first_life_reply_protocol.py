"""S115 offline JSON-example intervention and safe recorded-field replay.

No sender, allowance, credential or runtime policy is registered here. Existing
reply tasks and output validators remain the authority for shape/disclosure.
"""
from dataclasses import dataclass
from hashlib import sha256
import json

from dynamic_subject_agent.character_communication_plan import _validated_expression
from dynamic_subject_agent.deepseek import DeepSeekHttpResponse, DeepSeekResponseDiagnosticFailure, _diagnostic_json_reply_content
from dynamic_subject_agent.first_life_reply_candidate import preview_reply_candidate, recorded_reply_task
from dynamic_subject_agent.first_life_reply_routes import validate_whole_reply
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelTaskKind


PROTOCOL_VERSION = "first-life-json-example-preview-s115-1"
EXAMPLE_BODY = "<根据本轮消息填写回复正文>"
EXAMPLE_INTRO = (
    "\n输出格式示例（只示范JSON语法与字段，不是本轮回答）：\n"
)
EXAMPLE_END = (
    "\n请把reply_text示例文字替换为针对本轮消息的实际回复，按原契约填写其余字段。"
    "只输出一个JSON对象，不加代码块、前缀或后记。"
)


def output_example(kind):
    if type(kind) is not ModelTaskKind or kind not in (ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY,
            ModelTaskKind.CHARACTER_FIRST_LIFE_FACT_EXPRESSION):
        raise ValueError("only existing whole reply or fact expression can be previewed")
    example = dict(reply_text=EXAMPLE_BODY, language="zh")
    if kind is ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY:
        example["use_life"] = False
    return example


@dataclass(frozen=True)
class JsonExamplePreview:
    version: str
    task_kind: str
    source_payload_sha256: str
    baseline_wire_sha256: str
    candidate_wire_sha256: str
    appended_system: str
    wire: bytes
    remote_use_authorized: bool = False


def preview_json_example(task):
    """Append a valid format example; preserve every other request byte/value."""
    baseline = preview_reply_candidate(task)
    example = output_example(task.kind)
    suffix = EXAMPLE_INTRO + canonical_json(example) + EXAMPLE_END
    if "use_life" in example:
        suffix += "示例的use_life=false仅展示布尔值写法，不替本轮作披露选择。"
    body = json.loads(baseline.wire)
    body["messages"][0]["content"] += suffix
    wire = canonical_json(body).encode()
    if len(wire) > 65536:
        raise ValueError("JSON example request exceeds the existing byte bound")
    return JsonExamplePreview(PROTOCOL_VERSION, task.kind.value, baseline.source_payload_sha256,
        baseline.candidate_wire_sha256, sha256(wire).hexdigest(), suffix, wire)


def replay_recorded_reply(stage):
    """Reconstruct only retained final fields, never pretend to have a raw packet.

    A template echo is reported separately from structural validity. Neither a
    valid JSON object nor a non-echo verdict measures factual/natural dialogue.
    """
    task = recorded_reply_task(stage["task_kind"], stage["payload"])
    base = dict(reconstruction="retained-final-fields-not-original-http-envelope",
        semantic_quality="not-evaluated", format_example_copied=False)
    if (stage.get("model") is None or stage.get("finish_reason") is None
        or stage.get("final_content") is None or not stage.get("usage")):
        return dict(base, status="unavailable", diagnostic_code="recorded-response-unavailable", value=None)
    envelope = dict(model=stage["model"],
        choices=[dict(message=dict(role="assistant", content=stage["final_content"]), finish_reason=stage["finish_reason"])],
        usage=stage["usage"])
    try:
        value = _diagnostic_json_reply_content(DeepSeekHttpResponse(200, canonical_json(envelope).encode()),
            max_output_tokens=4096, require_complete=True, discard_reasoning=True)
    except DeepSeekResponseDiagnosticFailure as error:
        return dict(base, status="failed-closed", diagnostic_code=error.diagnostic_code, value=None)
    try:
        if task.kind is ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY:
            text, _ = validate_whole_reply(task.payload, value)
        else:
            text = _validated_expression(value)
    except (TypeError, ValueError, KeyError):
        return dict(base, status="failed-closed", diagnostic_code="structured-choice-invalid", value=None)
    return dict(base, status="structured", diagnostic_code=None, value=value,
        format_example_copied=text == EXAMPLE_BODY)
