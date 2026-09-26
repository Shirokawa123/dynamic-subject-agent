from dataclasses import asdict, replace
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
from dynamic_subject_agent.character_communication_trial import stage_digest, CommunicationTrialExpressionRequest
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import FrozenAttemptRun
from dynamic_subject_agent.local_product import prepare_character_communication_trial, open_character_communication_trial
from test_character_evidence_model import model_fixture
from test_character_communication_plan import communication_fixture


class CommunicationTransport(DeepSeekTransport):
    def __init__(self, *, fault=None, phase="planning"):
        self.fault, self.phase, self.calls = fault, phase, []

    def post_json(self, **kwargs):
        self.calls.append(kwargs)
        body = json.loads(kwargs["body"])
        projection = json.loads(body["messages"][1]["content"])
        stage = "planning" if "self_knowledge" in projection else "expression"
        if stage == self.phase and self.fault == "crash":
            raise SystemExit("simulated process exit")
        if stage == self.phase and self.fault == "network":
            raise ConnectionError("RAW_NETWORK_SECRET")
        if stage == self.phase and self.fault == "timeout":
            raise TimeoutError("RAW_TIMEOUT_SECRET")
        if stage == self.phase and self.fault == "ambiguous":
            from dynamic_subject_agent.cognition import ProviderFailure, ProviderFailureCode
            raise ProviderFailure(ProviderFailureCode.DELIVERY_AMBIGUOUS)
        value = {"action": "offer_topic", "fact_refs": ["F1"]} if stage == "planning" else {"reply_text": "这轮想聊聊创作。", "language": "zh"}
        message = dict(role="assistant", content=json.dumps(value), reasoning_content="RAW_REASONING_SECRET" if stage == "planning" else "")
        finish, tokens = "stop", 40
        if stage == self.phase:
            if self.fault == "refs": message["content"] = json.dumps({"action": "offer_topic", "fact_refs": ["F999"]})
            elif self.fault == "fact-text": message["content"] = json.dumps({"action": "answer", "fact_refs": ["F1"], "fact_text": "RAW_FACT_SECRET"})
            elif self.fault == "length": finish, message["content"] = "length", ""
            elif self.fault == "budget": tokens = 4097 if stage == "planning" else 601
            elif self.fault == "reasoning": message["reasoning_content"] = {"secret": "RAW_REASONING_SECRET"} if stage == "planning" else "RAW_REASONING_SECRET"
            elif self.fault == "reply-schema": message["content"] = json.dumps({"reply_text": "RAW_REPLY_SECRET", "language": "en"})
        return DeepSeekHttpResponse(200, json.dumps(dict(model="deepseek-flash", choices=[dict(message=message, finish_reason=finish)],
            usage=dict(prompt_tokens=100, completion_tokens=tokens))).encode())


@pytest.fixture
def communication_trial_fixture(communication_fixture):
    _, source_options, _, _, book = communication_fixture
    root = source_options["draft_path"].parent / "communication-trials"
    cases = dict(version="character-communication-plan-cases-1", cases=[dict(id=f"case-{i}", message=f"聊聊创作，第{i}个问题。", context_mode="flat") for i in range(6)])
    options = {**source_options, "subject_id": "self", "anchor_id": "start", "cases": cases}
    plan = prepare_character_communication_trial(root, **options)
    opened = []
    def open_trial(*, approved=None, transport=None, **overrides):
        product = open_character_communication_trial(root, **{**options, **overrides}, approved_plan=approved, _transport=transport)
        opened.append(product)
        return product
    yield root, plan, options, open_trial, book
    for product in opened:
        product.close()


def request(options, index=0):
    case = options["cases"]["cases"][index]
    return CharacterChatContextRequest(options["subject_id"], options["anchor_id"], case["message"], case["context_mode"])


def test_default_prepare_and_unapproved_trial_are_zero_gateway_delivery_or_credentials(communication_trial_fixture, monkeypatch):
    from dynamic_subject_agent.model_gateway import ModelGateway
    root, plan, options, open_trial, _ = communication_trial_fixture
    monkeypatch.setattr(ModelGateway, "execute", lambda *a: pytest.fail("prepare called model gateway"))
    transport = CommunicationTransport()
    app = open_trial(transport=transport).application
    preview = app.preview_character_reply(request(options))
    assert preview.status == "previewed" and preview.request_digest == plan.payload["requests"][0]["request_digest"]
    assert app.propose_character_reply(request(options)).code == "communication-trial-not-approved"
    assert len(plan.payload["requests"]) == 6 and plan.payload["limits"]["max_calls"] == 12
    assert not transport.calls and not (root / plan.digest).exists()


def test_all_six_facade_cases_derive_minimal_expression_and_never_exceed_twelve_or_replay(communication_trial_fixture):
    root, plan, options, open_trial, _ = communication_trial_fixture
    transport = CommunicationTransport()
    app = open_trial(approved=plan.digest, transport=transport).application
    canonical_before = {str(path): path.read_bytes() for path in (root / "products").rglob("*") if path.is_file()}
    results = []
    for i, row in enumerate(plan.payload["requests"]):
        result = app.propose_character_reply(request(options, i))
        assert result.status == "candidate" and result.semantic_review == "required" and not result.persisted
        results.append(result)
        assert app.propose_character_reply(request(options, i)) == result and len(transport.calls) == (i + 1) * 2
        planning_call, expression_call = transport.calls[-2:]
        planning, expression = json.loads(planning_call["body"]), json.loads(expression_call["body"])
        assert sha256(planning_call["body"]).hexdigest() == row["outbound_digest"]
        assert planning["max_tokens"] == 4096 and planning["thinking"] == {"type": "enabled"} and planning["reasoning_effort"] == "high"
        assert "temperature" not in planning
        assert expression["max_tokens"] == 600 and expression["thinking"] == {"type": "disabled"} and expression["temperature"] == 0.3
        for body, call in ((planning, planning_call), (expression, expression_call)):
            assert body["model"] == "deepseek-flash" and body["stream"] is False and "tools" not in body
            assert body["response_format"] == {"type": "json_object"} and call["timeout_seconds"] == 30
        projection = json.loads(expression["messages"][1]["content"])
        assert projection["selected_facts"] == [row["projection"]["self_knowledge"][0]]
        assert projection["selected_facts"][0]["content"] == "只在一次旧合作中缺过资料；不代表一直缺资料。"
        for key in ("stage_description", "encounter", "disclosure", "current_message"):
            assert projection[key] == row["projection"][key]
        for forbidden in ("UNSELECTED_PRIVATE_EXPERIENCE", "FUTURE_SECRET", "case_id", "request_digest", "context_digest",
                          "attempt", "plan_digest", "candidate_text", "claim_ids", "expected"):
            assert forbidden not in expression["messages"][1]["content"]
        recorded = json.loads((root / plan.digest / (stage_digest(row, "expression") + ".request.json")).read_text(encoding="utf-8"))
        assert recorded["projection"] == projection and recorded["outbound_digest"] == sha256(expression_call["body"]).hexdigest()
    assert len(list((root / plan.digest).glob("*.attempt.json"))) == 12
    assert len(list((root / plan.digest).glob("*.result.json"))) == 12
    assert len(list((root / plan.digest).glob("*.request.json"))) == 6
    assert canonical_before == {str(path): path.read_bytes() for path in (root / "products").rglob("*") if path.is_file()}
    audit = "".join(path.read_text(encoding="utf-8") for path in (root / plan.digest).glob("*.json"))
    assert "RAW_REASONING_SECRET" not in audit and "reasoning_content" not in audit and "headers" not in audit
    resumed = open_trial(approved=plan.digest, transport=transport).application
    for i, result in enumerate(results):
        assert resumed.propose_character_reply(request(options, i)) == result
    assert len(transport.calls) == 12


def test_current_approval_and_exact_cases_required_before_any_delivery(communication_trial_fixture):
    root, plan, options, open_trial, _ = communication_trial_fixture
    transport = CommunicationTransport()
    with pytest.raises(ValueError): open_trial(approved="0" * 64, transport=transport)
    changed = json.loads(json.dumps(options["cases"]))
    changed["cases"][0]["message"] += "新问题"
    with pytest.raises(ValueError): open_trial(approved=plan.digest, transport=transport, cases=changed)
    with pytest.raises(ValueError): open_trial(approved=plan.digest, transport=transport, reviewed_digest="0" * 64)
    assert not transport.calls and not (root / plan.digest).exists()
    app = open_trial(approved=plan.digest, transport=transport).application
    assert app.propose_character_reply(request(options, 1)).code == "communication-trial-out-of-order"
    assert app.propose_character_reply(replace(request(options), current_message="额外消息")).code == "communication-trial-not-in-plan"
    assert not transport.calls


@pytest.mark.parametrize("phase,fault,code,calls", [
    ("planning", "refs", "communication-plan-invalid", 1), ("planning", "fact-text", "communication-plan-invalid", 1),
    ("planning", "network", "transport-network", 1), ("expression", "network", "transport-network", 2),
    ("planning", "length", "response-truncated", 1), ("expression", "length", "response-truncated", 2),
    ("planning", "budget", "response-overbudget", 1), ("expression", "budget", "response-overbudget", 2),
    ("planning", "reasoning", "response-reasoning", 1), ("expression", "reasoning", "response-reasoning", 2),
    ("expression", "reply-schema", "communication-expression-invalid", 2),
])
def test_either_stage_fault_stops_batch_and_restart_reads_only_valid_failure_without_raw_output(communication_trial_fixture, phase, fault, code, calls):
    root, plan, options, open_trial, _ = communication_trial_fixture
    transport = CommunicationTransport(phase=phase, fault=fault)
    app = open_trial(approved=plan.digest, transport=transport).application
    result = app.propose_character_reply(request(options))
    assert result.status == "failed-closed" and result.code == code and not result.reply_text
    assert app.propose_character_reply(request(options)) == result
    assert app.propose_character_reply(request(options, 1)).code == "communication-trial-stopped"
    audit = "".join(path.read_text(encoding="utf-8") for path in (root / plan.digest).glob("*.json"))
    assert "RAW_" not in audit
    assert open_trial(approved=plan.digest, transport=transport).application.propose_character_reply(request(options)) == result
    assert len(transport.calls) == calls


@pytest.mark.parametrize("phase,calls", [("planning", 1), ("expression", 2)])
@pytest.mark.parametrize("fault,code", [("timeout", "transport-timeout"), ("ambiguous", "transport-delivery-ambiguous")])
def test_delivery_uncertainty_is_unknown_stops_batch_and_remains_unknown_on_restart(communication_trial_fixture, phase, calls, fault, code):
    root, plan, options, open_trial, _ = communication_trial_fixture
    transport = CommunicationTransport(phase=phase, fault=fault)
    app = open_trial(approved=plan.digest, transport=transport).application
    result = app.propose_character_reply(request(options))
    assert result.status == "unknown" and result.code == code and not result.reply_text
    assert app.propose_character_reply(request(options)) == result
    assert app.propose_character_reply(request(options, 1)).code == "communication-trial-stopped"
    resumed = open_trial(approved=plan.digest, transport=transport).application
    assert resumed.propose_character_reply(request(options)) == result
    assert resumed.propose_character_reply(request(options, 1)).status == "unknown"
    assert len(transport.calls) == calls
    audit_path = root / plan.digest / (stage_digest(plan.payload["requests"][0], phase) + ".result.json")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["status"] == "unknown" and audit["code"] == code and audit["value"] is None
    audit["code"] = "transport-network"  # Unknown cannot borrow an ordinary failure code.
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    rejected = open_trial(approved=plan.digest, transport=transport).application.propose_character_reply(request(options))
    assert rejected.status == "unknown" and rejected.code == "communication-trial-previously-started"
    audit["code"], audit["status"] = code, "failed-closed"
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    rejected = open_trial(approved=plan.digest, transport=transport).application.propose_character_reply(request(options))
    assert rejected.status == "unknown" and rejected.code == "communication-trial-previously-started"
    assert len(transport.calls) == calls


@pytest.mark.parametrize("phase,calls", [("planning", 1), ("expression", 2)])
def test_crash_in_either_phase_never_resends_or_continues_expression(communication_trial_fixture, phase, calls):
    _, plan, options, open_trial, _ = communication_trial_fixture
    transport = CommunicationTransport(phase=phase, fault="crash")
    app = open_trial(approved=plan.digest, transport=transport).application
    with pytest.raises(SystemExit): app.propose_character_reply(request(options))
    resumed = open_trial(approved=plan.digest, transport=transport).application
    assert resumed.propose_character_reply(request(options)).status == "unknown"
    assert resumed.propose_character_reply(request(options, 1)).status == "unknown"
    assert len(transport.calls) == calls


@pytest.mark.parametrize("stage,operation,calls", [("planning", "claim", 0), ("planning", "record", 1),
    ("expression", "claim", 1), ("expression", "record", 2), ("expression", "request", 1)])
def test_any_stage_audit_fault_is_unknown_stops_and_cannot_resume(communication_trial_fixture, monkeypatch, stage, operation, calls):
    import dynamic_subject_agent.character_communication_trial as trial_module
    _, plan, options, open_trial, _ = communication_trial_fixture
    transport = CommunicationTransport()
    app = open_trial(approved=plan.digest, transport=transport).application
    if operation in ("claim", "record"):
        original = getattr(FrozenAttemptRun, operation)
        def failing(self, *args):
            target = (0 if stage == "planning" else 1) + (operation == "record")
            if self.next == target: raise OSError("RAW_AUDIT_SECRET")
            return original(self, *args)
        monkeypatch.setattr(FrozenAttemptRun, operation, failing)
    else:
        original = trial_module.write_once
        def failing(path, value):
            if path.name.endswith(".request.json"): raise OSError("RAW_AUDIT_SECRET")
            return original(path, value)
        monkeypatch.setattr(trial_module, "write_once", failing)
    result = app.propose_character_reply(request(options))
    assert result.status == "unknown" and not result.reply_text and "RAW_" not in str(result)
    assert app.propose_character_reply(request(options, 1)).code == "communication-trial-stopped"
    assert open_trial(approved=plan.digest, transport=transport).application.propose_character_reply(request(options)).status == "unknown"
    assert len(transport.calls) == calls


def test_valid_planning_result_must_be_successfully_audited_before_expression(communication_trial_fixture, monkeypatch):
    root, plan, options, open_trial, _ = communication_trial_fixture
    transport = CommunicationTransport()
    app = open_trial(approved=plan.digest, transport=transport).application
    original = FrozenAttemptRun.record
    def altered(self, digest, audit):
        original(self, digest, audit)
        if audit["stage"] == "planning":
            audit["case_id"] = "different-case"
            (self.path / (digest + ".result.json")).write_text(json.dumps(audit), encoding="utf-8")
    monkeypatch.setattr(FrozenAttemptRun, "record", altered)
    assert app.propose_character_reply(request(options)).status == "unknown"
    assert len(transport.calls) == 1


@pytest.mark.parametrize("tamper", ["refs", "cross-case", "phase", "result-digest", "expression-projection", "attempt", "attempt-bool", "partial"])
def test_restart_rejects_partial_or_tampered_stage_bindings_without_any_resend(communication_trial_fixture, tamper):
    root, plan, options, open_trial, _ = communication_trial_fixture
    transport = CommunicationTransport()
    app = open_trial(approved=plan.digest, transport=transport).application
    app.propose_character_reply(request(options))
    row = plan.payload["requests"][0]
    planning_path = root / plan.digest / (stage_digest(row, "planning") + ".result.json")
    expression_path = root / plan.digest / (stage_digest(row, "expression") + ".result.json")
    request_path = root / plan.digest / (stage_digest(row, "expression") + ".request.json")
    target = request_path if tamper == "expression-projection" else expression_path if tamper in ("phase", "result-digest", "partial") else planning_path
    if tamper == "partial": target.rename(target.with_suffix(".withheld"))
    elif tamper in ("attempt", "attempt-bool"):
        target = root / plan.digest / (stage_digest(row, "expression") + ".attempt.json")
        value = json.loads(target.read_text(encoding="utf-8")); value["index"] = True if tamper == "attempt-bool" else 0
        target.write_text(json.dumps(value), encoding="utf-8")
    else:
        value = json.loads(target.read_text(encoding="utf-8"))
        if tamper == "refs": value["value"]["fact_refs"] = ["F2"]
        elif tamper == "cross-case": value["case_id"] = plan.payload["requests"][1]["case_id"]
        elif tamper == "phase": value["stage"] = "planning"
        elif tamper == "result-digest": value["request_digest"] = "0" * 64
        else: value["projection"]["selected_facts"][0]["content"] = "ARBITRARY_FACT"
        target.write_text(json.dumps(value), encoding="utf-8")
    assert open_trial(approved=plan.digest, transport=transport).application.propose_character_reply(request(options)).status == "unknown"
    assert len(transport.calls) == 2


def test_source_failure_stops_and_repair_cannot_continue_and_missing_credentials_are_unavailable(communication_trial_fixture):
    _, plan, options, open_trial, book = communication_trial_fixture
    transport = CommunicationTransport()
    app = open_trial(approved=plan.digest, transport=transport).application
    original = book.read_bytes(); book.write_bytes(original + b"bad")
    assert app.propose_character_reply(request(options)).status == "failed-closed"
    book.write_bytes(original)
    assert app.propose_character_reply(request(options)).code == "communication-trial-stopped" and not transport.calls


@pytest.mark.parametrize("phase,calls", [("planning", 1), ("expression", 2)])
def test_missing_secure_credential_remains_typed_unavailable_per_phase(communication_trial_fixture, phase, calls):
    from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
    _, plan, options, open_trial, _ = communication_trial_fixture
    class MissingCredential(CommunicationTransport):
        def post_json(self, **kwargs):
            projection = json.loads(json.loads(kwargs["body"])["messages"][1]["content"])
            current = "planning" if "self_knowledge" in projection else "expression"
            if current == phase:
                self.calls.append(kwargs)
                raise CharacterCredentialUnavailable()
            return super().post_json(**kwargs)
    transport = MissingCredential()
    result = open_trial(approved=plan.digest, transport=transport).application.propose_character_reply(request(options))
    assert result.status == "unavailable" and result.code == "character-credential-unavailable"
    assert open_trial(approved=plan.digest, transport=transport).application.propose_character_reply(request(options)) == result
    assert len(transport.calls) == calls


def test_adapter_cannot_accept_arbitrary_expression_projection_or_replay_completed_stage(communication_trial_fixture):
    from dynamic_subject_agent.character_communication_trial_provider import DeepSeekCommunicationTrialAdapter
    from dynamic_subject_agent.character_communication_plan import _qualify_plan, _expression_projection
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
    root, plan, options, open_trial, _ = communication_trial_fixture
    transport = CommunicationTransport()
    app = open_trial(approved=plan.digest, transport=transport).application
    projection = app.preview_character_reply(request(options)).projection
    free_expression = _expression_projection(_qualify_plan({"action": "answer", "fact_refs": ["F1"]}, projection,
        plan.payload["requests"][0]["request_digest"]), projection)
    adapter = DeepSeekCommunicationTrialAdapter(plan, run_root=root / plan.digest, transport=transport,
        credential_ref=CredentialRef.reference(backend_id="test", key_id="test"))
    with pytest.raises(ValueError): adapter.invoke(ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION, free_expression))
    with pytest.raises((ValueError, OSError)): adapter.invoke(ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION, CommunicationTrialExpressionRequest("0" * 64)))
    assert not transport.calls
    app.propose_character_reply(request(options))
    with pytest.raises(ValueError): adapter.invoke(ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_PLAN, projection))
    with pytest.raises(ValueError): adapter.invoke(ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION,
        CommunicationTrialExpressionRequest(plan.payload["requests"][0]["request_digest"])))
    assert len(transport.calls) == 2


def test_cli_default_freezes_only_planning_six_with_no_run_or_candidate(communication_trial_fixture, tmp_path):
    _, plan, options, _, _ = communication_trial_fixture
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps(options["cases"]), encoding="utf-8")
    cli = Path(__file__).resolve().parents[1] / "app/desktop/character_communication_trial.py"
    completed = subprocess.run([sys.executable, str(cli), "--draft", str(options["draft_path"]), "--source-root", str(options["source_root"]),
        "--reviewed-digest", options["reviewed_digest"], "--subject", "self", "--anchor", "start", "--cases", str(cases_path)],
        capture_output=True, check=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    summary = json.loads(completed.stdout)
    assert summary["digest"] == plan.digest and summary["frozen_planning_requests"] == 6 and summary["max_calls"] == 12
    assert "projection" not in summary and "聊聊创作" not in completed.stdout
    assert not (Path(summary["plan_path"]).parent / summary["digest"]).exists()
