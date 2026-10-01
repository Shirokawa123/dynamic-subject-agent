"""Approved protocol replay is a Facade lab, never character history."""
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest

from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse
from dynamic_subject_agent.development_model_calls import DevelopmentCallAudit
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.local_product import open_reply_protocol_lab
from dynamic_subject_agent.reply_protocol_trial import open_protocol_run
from test_s109_continuous_baseline import no_remote_io

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs/experiments/s115/protocol-comparison.json"


class LocalProtocolTransport(DeepSeekTransport):
    def __init__(self, *, blank=False):
        self.calls, self.blank = [], blank

    def post_json(self, **kwargs):
        self.calls.append(kwargs["body"])
        body = json.loads(kwargs["body"])
        data = json.loads(body["messages"][1]["content"])
        value = dict(reply_text="仅用于接口检查的合成正文。", language="zh")
        if "action" not in data["turn"]:
            value["use_life"] = False
        content = "  " if self.blank else canonical_json(value)
        return DeepSeekHttpResponse(200, canonical_json(dict(model="deepseek-flash",
            choices=[dict(finish_reason="stop", message=dict(role="assistant", content=content,
                reasoning_content="DO_NOT_PERSIST_REASONING"))],
            usage=dict(prompt_tokens=10, completion_tokens=20, total_tokens=30))).encode())


def test_facade_records_once_without_chat_publication_and_reopen_cannot_resend(tmp_path):
    root = tmp_path / str(uuid4())
    plan = open_protocol_run(root, PACKAGE, live=False)
    request = plan.request_for(**{k:plan.sequence[0][k] for k in ("case_id", "variant")})
    transport, observed = LocalProtocolTransport(), []
    with open_reply_protocol_lab(root, PACKAGE, _transport=transport, response_audit=observed.append) as product:
        result = product.application.evaluate_reply_protocol(request)
        assert result.status == "structured" and result.value["reply_text"] == "仅用于接口检查的合成正文。"
        history = product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
            product.profile_id, product.timeline_id))
        assert history.status == "available" and history.projection.turns == ()
        again = product.application.evaluate_reply_protocol(request)
        assert again.diagnostic_code == "protocol-attempt-already-recorded"
    assert product.application.evaluate_reply_protocol(request).status == "unavailable"
    with open_reply_protocol_lab(root, PACKAGE, _transport=transport) as restored:
        assert restored.application.evaluate_reply_protocol(request).diagnostic_code == "protocol-attempt-already-recorded"
    assert len(transport.calls) == 1
    assert DevelopmentCallAudit(root / "offline-audit").counts() == (None, 1, None)
    assert "DO_NOT_PERSIST_REASONING" not in canonical_json(observed)


@pytest.mark.parametrize("study", ["json-example", "response-format", "instruction-scope", "reasoning-effort"])
def test_eight_planned_arms_keep_blank_failures_without_hidden_retries(tmp_path, study):
    spec = importlib.util.spec_from_file_location("s116_runner", ROOT / "scripts/run_s116_protocol_comparison.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    root = tmp_path / str(uuid4())
    transport = LocalProtocolTransport(blank=True)
    result = runner.run_once(root, live=False, transport=transport, study=study)
    assert result["status"] == "completed" and len(transport.calls) == 8
    assert result["call_limit"] is None and result["remaining"] is None
    assert result["character_history_empty"] is True
    assert all(r["status"] == "failed-closed" and r["diagnostic_code"] == "response-content-empty" for r in result["results"])
    assert all(variant["structured"] == 0 for variant in result["variants"].values())
    if study == "response-format":
        assert {json.loads(body)["response_format"]["type"] for body in transport.calls} == {"json_object", "text"}
    with pytest.raises(FileExistsError):
        runner.run_once(root, live=False, transport=transport, study=study)
    assert len(transport.calls) == 8


def test_missing_whole_audit_cannot_initialize_again_and_resend_an_existing_attempt(tmp_path):
    root = tmp_path / str(uuid4())
    plan = open_protocol_run(root, PACKAGE, live=False)
    request = plan.request_for(**{k:plan.sequence[0][k] for k in ("case_id", "variant")})
    transport = LocalProtocolTransport()
    with open_reply_protocol_lab(root, PACKAGE, _transport=transport) as product:
        assert product.application.evaluate_reply_protocol(request).status == "structured"
    audit = (root / "offline-audit").resolve()
    retained = (root / "retained-audit").resolve()
    assert audit.is_relative_to(tmp_path.resolve()) and retained.is_relative_to(tmp_path.resolve())
    audit.rename(retained)  # Preserve the isolated fixture; never delete it.
    with pytest.raises(ValueError, match="audit"):
        open_reply_protocol_lab(root, PACKAGE, _transport=transport)
    assert not audit.exists() and len(transport.calls) == 1
    assert DevelopmentCallAudit(retained).counts() == (None, 1, None)
