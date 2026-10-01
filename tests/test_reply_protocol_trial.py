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


def test_response_format_study_changes_only_the_one_field_and_preserves_counterbalance(tmp_path):
    plan = trial.open_protocol_run(tmp_path / str(uuid4()), PACKAGE, live=False, study="response-format")
    assert plan.study == "response-format" and plan.variants == ("json-object", "text-json")
    manifest = plan.read()
    assert manifest["version"] == "reply-protocol-run-2" and manifest["call_limit"] is None
    package = plan.package
    mapped = {"baseline": "json-object", "json-example": "text-json"}
    assert [(row["case_id"], row["variant"]) for row in plan.sequence] == [
        (row["case_id"], mapped[row["variant"]]) for row in package["sequence"]]
    frozen = {(row["case_id"], row["variant"]): row["wire_sha256"] for row in manifest["study_spec"]["sequence"]}
    for case in package["cases"]:
        baseline = plan.wire_for(plan.request_for(case["case_id"], "json-object"))
        text = plan.wire_for(plan.request_for(case["case_id"], "text-json"))
        assert baseline == case["candidate_wire_utf8"].encode("utf-8")
        before, after = json.loads(baseline), json.loads(text)
        assert before["response_format"] == {"type": "json_object"}
        assert after["response_format"] == {"type": "text"}
        after["response_format"] = before["response_format"]
        assert after == before
        assert frozen[case["case_id"], "json-object"] == sha256(baseline).hexdigest()
        assert frozen[case["case_id"], "text-json"] == sha256(text).hexdigest()
    with pytest.raises(ValueError):
        plan.request_for(package["cases"][0]["case_id"], "baseline")
    manifest["study_spec"]["sequence"][0]["wire_sha256"] = "0" * 64
    (plan.root / "manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        plan.read()


def test_old_v1_manifest_reopens_byte_exact_and_same_run_cannot_change_study(tmp_path):
    root = tmp_path / str(uuid4())
    root.mkdir()
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    old = dict(version="reply-protocol-run-1", authorization=trial.AUTHORIZATION, purpose=trial.PURPOSE,
        call_limit=None, automatic_retries=0, live=False, run_id=root.name, root=str(root.resolve()),
        package_digest=trial.PACKAGE_DIGEST, package=package)
    original_bytes = canonical_json(old).encode("utf-8")
    (root / "manifest.json").write_bytes(original_bytes)
    plan = trial.open_protocol_run(root, PACKAGE, live=False)
    assert plan.digest == sha256(original_bytes).hexdigest()
    assert plan.study == "json-example" and plan.variants == trial.VARIANTS
    assert "study" not in plan.read() and (root / "manifest.json").read_bytes() == original_bytes
    assert trial.open_protocol_run(root, PACKAGE, live=False, study="json-example").digest == plan.digest
    with pytest.raises(ValueError):
        trial.open_protocol_run(root, PACKAGE, live=False, study="response-format")
    with pytest.raises(ValueError):
        trial.open_protocol_run(root, PACKAGE, live=False, study="instruction-scope")
    assert (root / "manifest.json").read_bytes() == original_bytes
    new = trial.open_protocol_run(tmp_path / str(uuid4()), PACKAGE, live=False, study="response-format")
    new_bytes = (new.root / "manifest.json").read_bytes()
    with pytest.raises(ValueError):
        trial.open_protocol_run(new.root, PACKAGE, live=False)
    assert (new.root / "manifest.json").read_bytes() == new_bytes


@pytest.mark.parametrize("valid_json", [False, True])
def test_text_response_mode_keeps_the_original_strict_json_output_requirement(tmp_path, valid_json):
    plan = trial.open_protocol_run(tmp_path / str(uuid4()), PACKAGE, live=False, study="response-format")
    request = plan.request_for(plan.package["cases"][0]["case_id"], "text-json")
    audit = DevelopmentCallAudit(plan.root / "offline-audit", initialize=True)
    transport = SyntheticTransport(value=valid_value(plan, request), content=None if valid_json else "只有自然语言正文。")
    ref = CredentialRef.reference(backend_id=OFFLINE_CREDENTIAL_BACKEND, key_id=OFFLINE_CREDENTIAL_KEY)
    adapter = ProtocolTrialAdapter(transport, ref, plan, audit)
    service = trial.ReplyProtocolTrial(ModelGateway(adapter), plan)
    try:
        view = service.evaluate(request)
    finally:
        service.close()
    assert json.loads(transport.calls[0])["response_format"] == {"type": "text"}
    if valid_json:
        assert view.status == "structured" and view.value == transport.value
    else:
        assert view.status == "failed-closed" and view.diagnostic_code == "response-content-json" and view.value is None
    assert len(transport.calls) == 1 and audit.counts() == (None, 1, None)


def test_instruction_scope_replaces_exactly_one_sentence_and_nothing_else(tmp_path):
    plan = trial.open_protocol_run(tmp_path / str(uuid4()), PACKAGE, live=False, study="instruction-scope")
    assert plan.study == "instruction-scope" and plan.variants == ("global-style", "reply-text-style")
    manifest = plan.read()
    assert manifest["version"] == "reply-protocol-run-3" and manifest["study_spec"]["scope"]
    expected_sentence = (
        "本接口需要JSON数据，外层字段供程序读取。reply_text的值才是给用户看的正文："
        "使用第一人称自然中文短消息，通常两三句；这段正文不写动作旁白、档案、字段标签、规则说明、分析或思考过程。"
    )
    assert manifest["study_spec"]["replacement_sentence"] == expected_sentence
    mapped = {"baseline": "global-style", "json-example": "reply-text-style"}
    assert [(row["case_id"], row["variant"]) for row in plan.sequence] == [
        (row["case_id"], mapped[row["variant"]]) for row in plan.package["sequence"]]
    hashes = {(row["case_id"], row["variant"]): row["wire_sha256"] for row in manifest["study_spec"]["sequence"]}
    for case in plan.package["cases"]:
        old_wire = plan.wire_for(plan.request_for(case["case_id"], "global-style"))
        new_wire = plan.wire_for(plan.request_for(case["case_id"], "reply-text-style"))
        assert old_wire == case["candidate_wire_utf8"].encode("utf-8")
        before, after = json.loads(old_wire), json.loads(new_wire)
        assert before["messages"][0]["content"].count(trial.GLOBAL_STYLE_SENTENCE) == 1
        assert after["messages"][0]["content"].count(expected_sentence) == 1
        assert trial.GLOBAL_STYLE_SENTENCE not in after["messages"][0]["content"]
        after["messages"][0]["content"] = after["messages"][0]["content"].replace(expected_sentence, trial.GLOBAL_STYLE_SENTENCE, 1)
        assert after == before and before["response_format"] == {"type": "json_object"}
        assert hashes[case["case_id"], "global-style"] == sha256(old_wire).hexdigest()
        assert hashes[case["case_id"], "reply-text-style"] == sha256(new_wire).hexdigest()
    original_bytes = (plan.root / "manifest.json").read_bytes()
    assert trial.open_protocol_run(plan.root, PACKAGE, live=False, study="instruction-scope").digest == plan.digest
    with pytest.raises(ValueError):
        trial.open_protocol_run(plan.root, PACKAGE, live=False, study="response-format")
    assert (plan.root / "manifest.json").read_bytes() == original_bytes


def test_preexisting_v2_response_format_manifest_and_wires_remain_exact(tmp_path):
    root = tmp_path / str(uuid4())
    root.mkdir()
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    cases = {row["case_id"]: row for row in package["cases"]}
    names = {"baseline": "json-object", "json-example": "text-json"}
    sequence, original_wires = [], {}
    for entry in package["sequence"]:
        variant = names[entry["variant"]]
        wire = cases[entry["case_id"]]["candidate_wire_utf8"].encode("utf-8")
        if variant == "text-json":
            body = json.loads(wire)
            body["response_format"] = {"type": "text"}
            wire = canonical_json(body).encode("utf-8")
        original_wires[entry["case_id"], variant] = wire
        sequence.append(dict(case_id=entry["case_id"], variant=variant, wire_sha256=sha256(wire).hexdigest()))
    old = dict(version="reply-protocol-run-2", authorization=trial.AUTHORIZATION, purpose=trial.PURPOSE,
        call_limit=None, automatic_retries=0, live=False, run_id=root.name, root=str(root.resolve()),
        package_digest=trial.PACKAGE_DIGEST, package=package, study="response-format",
        study_spec=dict(version="reply-response-format-study-1", source_variant="json-example",
            changed_field="response_format.type", variants=["json-object", "text-json"],
            output_validation="unchanged-strict-json-and-original-reply-schema", sequence=sequence))
    original_bytes = canonical_json(old).encode("utf-8")
    (root / "manifest.json").write_bytes(original_bytes)
    plan = trial.open_protocol_run(root, PACKAGE, live=False, study="response-format")
    assert plan.digest == sha256(original_bytes).hexdigest()
    for pair, wire in original_wires.items():
        assert plan.wire_for(plan.request_for(*pair)) == wire
    with pytest.raises(ValueError):
        trial.open_protocol_run(root, PACKAGE, live=False, study="instruction-scope")
    assert (root / "manifest.json").read_bytes() == original_bytes


def test_reasoning_effort_changes_only_high_to_low_from_the_common_scoped_json_wire(tmp_path):
    plan = trial.open_protocol_run(tmp_path / str(uuid4()), PACKAGE, live=False, study="reasoning-effort")
    scoped = trial.open_protocol_run(tmp_path / str(uuid4()), PACKAGE, live=False, study="instruction-scope")
    assert plan.study == "reasoning-effort" and plan.variants == ("high", "low")
    manifest = plan.read()
    assert manifest["version"] == "reply-protocol-run-4"
    assert manifest["study_spec"]["base_study"] == "instruction-scope"
    assert manifest["study_spec"]["base_variant"] == "reply-text-style"
    names = {"baseline": "high", "json-example": "low"}
    assert [(row["case_id"], row["variant"]) for row in plan.sequence] == [
        (row["case_id"], names[row["variant"]]) for row in plan.package["sequence"]]
    hashes = {(row["case_id"], row["variant"]): row["wire_sha256"] for row in manifest["study_spec"]["sequence"]}
    for case in plan.package["cases"]:
        high_request = plan.request_for(case["case_id"], "high")
        low_request = plan.request_for(case["case_id"], "low")
        high_wire, low_wire = plan.wire_for(high_request), plan.wire_for(low_request)
        assert high_wire == scoped.wire_for(scoped.request_for(case["case_id"], "reply-text-style"))
        high, low = json.loads(high_wire), json.loads(low_wire)
        assert high["reasoning_effort"] == "high" and low["reasoning_effort"] == "low"
        assert low["thinking"] == {"type": "enabled"} and low["max_tokens"] == 4096
        assert low["response_format"] == {"type": "json_object"}
        low["reasoning_effort"] = "high"
        assert low == high
        assert hashes[case["case_id"], "high"] == sha256(high_wire).hexdigest()
        assert hashes[case["case_id"], "low"] == sha256(low_wire).hexdigest()
        assert plan.validate_output(low_request, valid_value(plan, low_request)) is False
        with pytest.raises(ValueError):
            plan.validate_output(low_request, "unparsed free text")
    before = (plan.root / "manifest.json").read_bytes()
    assert trial.open_protocol_run(plan.root, PACKAGE, live=False, study="reasoning-effort").digest == plan.digest
    with pytest.raises(ValueError):
        trial.open_protocol_run(plan.root, PACKAGE, live=False, study="instruction-scope")
    assert (plan.root / "manifest.json").read_bytes() == before


def test_preexisting_v3_instruction_scope_manifest_and_wires_remain_exact(tmp_path):
    root = tmp_path / str(uuid4())
    root.mkdir()
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    cases = {row["case_id"]: row for row in package["cases"]}
    old_sentence = "使用第一人称自然中文短消息，通常两三句；不输出动作旁白、档案、字段名、规则、分析或思考过程。"
    new_sentence = (
        "本接口需要JSON数据，外层字段供程序读取。reply_text的值才是给用户看的正文："
        "使用第一人称自然中文短消息，通常两三句；这段正文不写动作旁白、档案、字段标签、规则说明、分析或思考过程。"
    )
    names = {"baseline": "global-style", "json-example": "reply-text-style"}
    sequence, original_wires = [], {}
    for entry in package["sequence"]:
        variant = names[entry["variant"]]
        wire = cases[entry["case_id"]]["candidate_wire_utf8"].encode("utf-8")
        if variant == "reply-text-style":
            body = json.loads(wire)
            body["messages"][0]["content"] = body["messages"][0]["content"].replace(old_sentence, new_sentence, 1)
            wire = canonical_json(body).encode("utf-8")
        original_wires[entry["case_id"], variant] = wire
        sequence.append(dict(case_id=entry["case_id"], variant=variant, wire_sha256=sha256(wire).hexdigest()))
    old = dict(version="reply-protocol-run-3", authorization=trial.AUTHORIZATION, purpose=trial.PURPOSE,
        call_limit=None, automatic_retries=0, live=False, run_id=root.name, root=str(root.resolve()),
        package_digest=trial.PACKAGE_DIGEST, package=package, study="instruction-scope",
        study_spec=dict(version="reply-instruction-scope-study-1", source_variant="json-example",
            changed_field="messages[0].content", scope="style instructions apply only to the reply_text value",
            original_sentence=old_sentence, replacement_sentence=new_sentence,
            variants=["global-style", "reply-text-style"], response_format=dict(type="json_object"),
            output_validation="unchanged-strict-json-and-original-reply-schema", sequence=sequence))
    original_bytes = canonical_json(old).encode("utf-8")
    (root / "manifest.json").write_bytes(original_bytes)
    plan = trial.open_protocol_run(root, PACKAGE, live=False, study="instruction-scope")
    assert plan.digest == sha256(original_bytes).hexdigest()
    for pair, wire in original_wires.items():
        assert plan.wire_for(plan.request_for(*pair)) == wire
    with pytest.raises(ValueError):
        trial.open_protocol_run(root, PACKAGE, live=False, study="reasoning-effort")
    assert (root / "manifest.json").read_bytes() == original_bytes


def test_thinking_mode_changes_only_consistent_api_mode_fields_and_preserves_old_runs(tmp_path):
    scoped = trial.open_protocol_run(tmp_path / str(uuid4()), PACKAGE, live=False, study="instruction-scope")
    effort = trial.open_protocol_run(tmp_path / str(uuid4()), PACKAGE, live=False, study="reasoning-effort")
    old_manifest = (effort.root / "manifest.json").read_bytes()
    old_wires = [effort.wire_for(effort.request_for(row["case_id"], row["variant"])) for row in effort.sequence]
    plan = trial.open_protocol_run(tmp_path / str(uuid4()), PACKAGE, live=False, study="thinking-mode")
    assert plan.variants == ("thinking", "non-thinking")
    assert plan.read()["version"] == "reply-protocol-run-5"
    assert plan.read()["study_spec"]["changed_fields"] == ["thinking.type", "reasoning_effort"]
    for case in plan.package["cases"]:
        thinking = plan.wire_for(plan.request_for(case["case_id"], "thinking"))
        candidate_request = plan.request_for(case["case_id"], "non-thinking")
        candidate = json.loads(plan.wire_for(candidate_request))
        assert thinking == scoped.wire_for(scoped.request_for(case["case_id"], "reply-text-style"))
        assert candidate["thinking"] == {"type": "disabled"} and candidate["reasoning_effort"] == "none"
        candidate["thinking"], candidate["reasoning_effort"] = {"type": "enabled"}, "high"
        assert candidate == json.loads(thinking)
        assert plan.validate_output(candidate_request, valid_value(plan, candidate_request)) is False
        with pytest.raises(ValueError):
            plan.validate_output(candidate_request, "unparsed free text")
    restored = trial.open_protocol_run(effort.root, PACKAGE, live=False, study="reasoning-effort")
    assert (effort.root / "manifest.json").read_bytes() == old_manifest and restored.digest == effort.digest
    assert [restored.wire_for(restored.request_for(row["case_id"], row["variant"])) for row in restored.sequence] == old_wires
    with pytest.raises(ValueError):
        trial.open_protocol_run(effort.root, PACKAGE, live=False, study="thinking-mode")
