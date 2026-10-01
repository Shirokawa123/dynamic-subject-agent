"""Exact protocol experiments with synthetic transport and fresh unlimited audit."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

import pytest

from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
from dynamic_subject_agent.cognition import CredentialRef
from dynamic_subject_agent.deepseek import (
    DeepSeekTransport, DeepSeekHttpResponse, DeepSeekUrlLibTransport, DeepSeekCredentialResolver,
    DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID,
)
from dynamic_subject_agent.development_model_calls import DevelopmentCallAudit
from dynamic_subject_agent.first_life_reply_protocol import EXAMPLE_BODY
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelGateway, ModelTaskKind
from dynamic_subject_agent import reply_protocol_trial as trial
from dynamic_subject_agent.reply_protocol_trial_provider import (
    ProtocolTrialAdapter, OFFLINE_CREDENTIAL_BACKEND, OFFLINE_CREDENTIAL_KEY,
)
from test_s109_continuous_baseline import no_remote_io


PACKAGE = Path(__file__).resolve().parents[1] / "docs/experiments/s115/protocol-comparison.json"


class SyntheticTransport(DeepSeekTransport):
    def __init__(self, value=None, *, content=None, failure=None):
        self.value, self.content, self.failure = value, content, failure
        self.calls, self.before_send = [], None

    def post_json(self, **kwargs):
        self.calls.append(kwargs["body"])
        if self.before_send:
            self.before_send()
        if self.failure == "timeout":
            raise TimeoutError("DO_NOT_LOG_RAW_PRIVATE_HOST")
        if self.failure == "credential":
            raise CharacterCredentialUnavailable()
        content = self.content if self.content is not None else canonical_json(self.value)
        response = dict(model="deepseek-flash", choices=[dict(finish_reason="stop",
            message=dict(role="assistant", content=content, reasoning_content="EXCLUDED_HIDDEN_REASONING"))],
            usage=dict(prompt_tokens=10, completion_tokens=5, total_tokens=15))
        return DeepSeekHttpResponse(200, canonical_json(response).encode())


def valid_value(plan, request, text="合成协议验收正文。"):
    value = dict(reply_text=text, language="zh")
    if plan.task_for_case(request).kind is ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY:
        value["use_life"] = False
    return value


@pytest.fixture
def lab(tmp_path):
    plan = trial.open_protocol_run(tmp_path / str(uuid4()), PACKAGE, live=False)
    audit = DevelopmentCallAudit(plan.root / "offline-audit", initialize=True)
    transport = SyntheticTransport()
    ref = CredentialRef.reference(backend_id=OFFLINE_CREDENTIAL_BACKEND, key_id=OFFLINE_CREDENTIAL_KEY)
    adapter = ProtocolTrialAdapter(transport, ref, plan, audit)
    service = trial.ReplyProtocolTrial(ModelGateway(adapter), plan)
    yield plan, audit, transport, adapter, service
    service.close()


def request_at(plan, index=0):
    row = plan.sequence[index]
    return plan.request_for(row["case_id"], row["variant"])


def test_all_eight_exact_wires_are_sent_only_after_claim_without_local_ids_or_reasoning(lab):
    plan, audit, transport, adapter, service = lab
    assert plan.read()["call_limit"] is None and plan.read()["authorization"] == trial.AUTHORIZATION
    package = plan.package
    for index, entry in enumerate(plan.sequence):
        request = request_at(plan, index)
        transport.value = valid_value(plan, request)
        transport.before_send = lambda: audit.query(request.attempt_id)["status"] == "claimed" or pytest.fail("send before claim")
        view = service.evaluate(request)
        assert view.status == "structured" and not view.format_example_copied
        assert view.value == transport.value
        case = next(row for row in package["cases"] if row["case_id"] == entry["case_id"])
        key = "baseline_wire_utf8" if entry["variant"] == "baseline" else "candidate_wire_utf8"
        assert transport.calls[-1] == case[key].encode("utf-8") == plan.wire_for(request)
        assert request.attempt_id.encode() not in transport.calls[-1]
        assert request.case_id.encode() not in transport.calls[-1]
        assert audit.query(request.attempt_id)["request_digest"] == sha256(transport.calls[-1]).hexdigest()
        assert audit.query(request.attempt_id)["status"] == "complete"
    assert audit.counts() == (None, 8, None)
    assert len(adapter.rows) == 8
    assert all(row["transport_attempted"] and row["audit_status"] == "complete" for row in adapter.rows)
    assert "EXCLUDED_HIDDEN_REASONING" not in canonical_json(adapter.rows)
    assert all(row["final_content"] and row["usage"]["total_tokens"] == 15 for row in adapter.rows)


@pytest.mark.parametrize("state", ["claimed", "complete"])
def test_existing_attempt_never_sends_or_claims_again_even_after_reopen(lab, state):
    plan, audit, transport, adapter, service = lab
    request = request_at(plan)
    if state == "claimed":
        audit.claim(request.attempt_id, sha256(plan.wire_for(request)).hexdigest(),
            purpose=trial.PURPOSE, run_digest=plan.digest)
    else:
        transport.value = valid_value(plan, request)
        assert service.evaluate(request).status == "structured"
    before = len(transport.calls)
    reopened = trial.open_protocol_run(plan.root, PACKAGE, live=False)
    assert reopened.digest == plan.digest and request_at(reopened) == request
    view = trial.ReplyProtocolTrial(ModelGateway(adapter), reopened).evaluate(request)
    assert view.diagnostic_code == "protocol-attempt-already-recorded"
    assert len(transport.calls) == before and audit.counts() == (None, 1, None)


@pytest.mark.parametrize("content,expected", [
    (" " * 57, "response-content-empty"), ("not JSON", "response-content-json"),
    ('{"reply_text":"","language":"zh","use_life":false}', "protocol-response-invalid"),
    ('{"reply_text":"hello","language":"en","use_life":false}', "protocol-response-invalid"),
])
def test_blank_json_and_original_schema_failures_remain_strict(lab, content, expected):
    plan, audit, transport, adapter, service = lab
    request = request_at(plan)
    transport.content = content
    view = service.evaluate(request)
    assert view.status == "failed-closed" and view.diagnostic_code == expected and view.value is None
    assert audit.query(request.attempt_id)["status"] == "failed-closed"
    assert adapter.rows[-1]["final_content"] == content and len(transport.calls) == 1


@pytest.mark.parametrize("index", [1, 5])
def test_exact_example_echo_is_separate_from_usable_structured_reply(lab, index):
    plan, audit, transport, adapter, service = lab
    request = request_at(plan, index)
    transport.value = valid_value(plan, request, EXAMPLE_BODY)
    view = service.evaluate(request)
    assert view.status == "format-example-copied" and view.format_example_copied is True
    assert view.value == transport.value
    assert adapter.rows[-1]["format_example_copied"] is True
    assert audit.query(request.attempt_id)["status"] == "complete"  # Delivery was valid, dialogue was not accepted.


@pytest.mark.parametrize("failure,code,status", [
    ("timeout", "transport-timeout", "unknown"),
    ("credential", "character-credential-unavailable", "unavailable"),
])
def test_transport_and_credential_failures_are_closed_safe_and_not_retried(lab, failure, code, status):
    plan, audit, transport, adapter, service = lab
    request = request_at(plan)
    transport.failure = failure
    view = service.evaluate(request)
    assert view.diagnostic_code == code
    assert audit.query(request.attempt_id)["status"] == status
    assert "DO_NOT_LOG_RAW_PRIVATE_HOST" not in canonical_json(adapter.rows)
    assert service.evaluate(request).diagnostic_code == "protocol-attempt-already-recorded"
    assert len(transport.calls) == 1 and audit.counts() == (None, 1, None)


def test_audit_finalization_failure_retains_observation_and_blocks_resend(lab, monkeypatch):
    plan, audit, transport, adapter, service = lab
    request = request_at(plan)
    transport.value = valid_value(plan, request)
    def fail(*args, **kwargs):
        raise ValueError("DO_NOT_LOG_AUDIT_EXCEPTION")
    monkeypatch.setattr(audit, "record", fail)
    assert service.evaluate(request).diagnostic_code == "protocol-audit-failed"
    assert adapter.rows[-1]["audit_status"] == "unverified"
    assert adapter.rows[-1]["value"] == transport.value
    assert audit.query(request.attempt_id)["status"] == "claimed"
    assert service.evaluate(request).diagnostic_code == "protocol-attempt-already-recorded"
    assert len(transport.calls) == 1 and "DO_NOT_LOG_AUDIT_EXCEPTION" not in canonical_json(adapter.rows)


def test_scope_builder_and_attempt_binding_fail_before_delivery_and_close_is_unavailable(lab, monkeypatch):
    plan, audit, transport, adapter, service = lab
    request = request_at(plan)
    assert service.evaluate(replace(request, attempt_id="0" * 64)).diagnostic_code == "protocol-request-invalid"
    monkeypatch.setattr("dynamic_subject_agent.first_life_reply_protocol.EXAMPLE_END", "unreviewed change")
    assert service.evaluate(request).status == "failed-closed"
    assert not transport.calls and audit.counts() == (None, 0, None)
    service.close()
    assert service.evaluate(request).status == "unavailable"


def test_existing_incomplete_metadata_is_not_initialized_and_new_run_has_new_attempts(tmp_path, lab):
    plan, *_ = lab
    incomplete = tmp_path / str(uuid4())
    incomplete.mkdir()
    with pytest.raises(FileNotFoundError):
        trial.open_protocol_run(incomplete, PACKAGE, live=False)
    assert list(incomplete.iterdir()) == []
    new_run = trial.open_protocol_run(tmp_path / str(uuid4()), PACKAGE, live=False)
    assert new_run.digest != plan.digest and request_at(new_run).attempt_id != request_at(plan).attempt_id
    assert new_run.read()["call_limit"] is None
    manifest = json.loads((plan.root / "manifest.json").read_text(encoding="utf-8"))
    manifest["call_limit"] = 8
    (plan.root / "manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        plan.read()


def test_offline_rejects_real_credentials_transport_and_misbound_audit(lab):
    plan, audit, transport, *_ = lab
    real_ref = CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID)
    with pytest.raises(ValueError, match="offline protocol"):
        ProtocolTrialAdapter(transport, real_ref, plan, audit)
    class NeverResolve(DeepSeekCredentialResolver):
        def resolve(self, credential_ref):
            pytest.fail("an offline trial must not look up a key")
    invalid_ref = CredentialRef.reference(backend_id=OFFLINE_CREDENTIAL_BACKEND, key_id=OFFLINE_CREDENTIAL_KEY)
    with pytest.raises(ValueError, match="offline protocol"):
        ProtocolTrialAdapter(DeepSeekUrlLibTransport(credential_resolver=NeverResolve()), invalid_ref, plan, audit)
    other = DevelopmentCallAudit(plan.root / "different-audit", initialize=True)
    with pytest.raises(ValueError, match="offline protocol"):
        ProtocolTrialAdapter(transport, invalid_ref, plan, other)
    assert audit.counts() == (None, 0, None) and not transport.calls


def test_live_mode_requires_canonical_run_directory_and_single_fixed_audit(tmp_path, monkeypatch):
    root = tmp_path / "pretend-real-development"
    monkeypatch.setattr(trial, "fixed_development_root", lambda: root)
    with pytest.raises(ValueError, match="fixed development"):
        trial.open_protocol_run(tmp_path / str(uuid4()), PACKAGE, live=True)
    with pytest.raises(ValueError, match="offline protocol"):
        trial.open_protocol_run(root / "runs" / str(uuid4()), PACKAGE, live=False)
    plan = trial.open_protocol_run(root / "runs" / str(uuid4()), PACKAGE, live=True)
    audit = DevelopmentCallAudit(root / "audit", initialize=True)
    real_ref = CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID)
    transport = SyntheticTransport()
    adapter = ProtocolTrialAdapter(transport, real_ref, plan, audit)
    request = request_at(plan)
    transport.value = valid_value(plan, request)
    assert trial.ReplyProtocolTrial(ModelGateway(adapter), plan).evaluate(request).status == "structured"
    assert audit.counts() == (None, 1, None)
