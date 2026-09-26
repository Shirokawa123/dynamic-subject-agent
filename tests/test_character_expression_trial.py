from dataclasses import asdict
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import shutil
import sys

import pytest

from dynamic_subject_agent.character_communication_trial import stage_digest
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import FrozenAttemptRun, canonical_json
from dynamic_subject_agent.local_product import prepare_character_expression_thinking_trial, open_character_expression_thinking_trial
from test_character_evidence_model import model_fixture, organize_fixture
from test_character_communication_plan import communication_fixture
from test_character_communication_trial import communication_trial_fixture, CommunicationTransport, request


class ExpressionTransport(DeepSeekTransport):
    def __init__(self, fault=None): self.fault, self.calls = fault, []
    def post_json(self, **kwargs):
        self.calls.append(kwargs)
        body = json.loads(kwargs["body"])
        assert "selected_facts" in json.loads(body["messages"][1]["content"])
        if self.fault == "crash": raise SystemExit("simulated expression crash")
        if self.fault == "network": raise ConnectionError("RAW_NETWORK_SECRET")
        if self.fault == "timeout": raise TimeoutError("RAW_TIMEOUT_SECRET")
        if self.fault == "credential":
            from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
            raise CharacterCredentialUnavailable()
        value = {"reply_text": "本轮提出一个话题。", "language": "zh"}
        if self.fault == "schema": value["old_answer"] = "RAW_SCHEMA_SECRET"
        finish, content = ("length", "") if self.fault == "length" else ("stop", json.dumps(value))
        return DeepSeekHttpResponse(200, json.dumps(dict(model="deepseek-flash", choices=[dict(finish_reason=finish,
            message=dict(role="assistant", content=content, reasoning_content="RAW_REASONING_SECRET"))],
            usage=dict(prompt_tokens=100, completion_tokens=4097 if self.fault == "budget" else 80))).encode())


@pytest.fixture
def expression_trial_fixture(communication_trial_fixture):
    parent_root, parent, parent_options, open_parent, book = communication_trial_fixture
    class ParentTransport(CommunicationTransport):
        def post_json(self, **kwargs):
            response = super().post_json(**kwargs)
            payload = json.loads(response.body)
            if "selected_facts" in json.loads(json.loads(kwargs["body"])["messages"][1]["content"]):
                payload["choices"][0]["message"]["content"] = json.dumps({"reply_text": "PARENT_OLD_ANSWER", "language": "zh"})
            return DeepSeekHttpResponse(response.status_code, json.dumps(payload).encode())
    transport = ParentTransport()
    app = open_parent(approved=parent.digest, transport=transport).application
    for i in range(6): assert app.propose_character_reply(request(parent_options, i)).status == "candidate"
    root = parent_root.parent / "expression-thinking"
    options = dict(parent_trial_root=parent_root, parent_plan_digest=parent.digest,
                   draft_path=parent_options["draft_path"], source_root=parent_options["source_root"])
    plan = prepare_character_expression_thinking_trial(root, **options)
    opened = []
    def open_trial(*, approved=None, transport=None):
        product = open_character_expression_thinking_trial(root, **options, approved_plan=approved, _transport=transport)
        opened.append(product)
        return product
    yield root, plan, options, open_trial, parent_root, parent, parent_options, book
    for product in opened: product.close()


def test_offline_prepare_and_old_approval_do_not_execute_any_task(expression_trial_fixture, monkeypatch):
    from dynamic_subject_agent.model_gateway import ModelGateway
    root, plan, _, open_trial, _, parent, parent_options, _ = expression_trial_fixture
    monkeypatch.setattr(ModelGateway, "execute", lambda *a: pytest.fail("offline expression planning or delivery"))
    transport = ExpressionTransport()
    app = open_trial(transport=transport).application
    preview = app.preview_character_reply(request(parent_options))
    assert preview.status == "previewed"
    assert canonical_json(asdict(preview.projection)) == canonical_json(plan.payload["requests"][0]["projection"])
    assert app.propose_character_reply(request(parent_options)).code == "expression-trial-not-approved"
    with pytest.raises(ValueError): open_trial(approved=parent.digest, transport=transport)
    assert plan.payload["limits"] == dict(cases=6, expression_calls=6, planning_calls=0)
    assert not transport.calls and not (root / plan.digest).exists()


def test_six_original_expression_inputs_change_only_generation_config_and_never_repeat(expression_trial_fixture):
    root, plan, _, open_trial, parent_root, parent, parent_options, _ = expression_trial_fixture
    transport = ExpressionTransport()
    app = open_trial(approved=plan.digest, transport=transport).application
    before = {str(path): path.read_bytes() for path in (root / "products").rglob("*") if path.is_file()}
    results = []
    for i, row in enumerate(plan.payload["requests"]):
        result = app.propose_character_reply(request(parent_options, i)); results.append(result)
        assert result.status == "candidate" and result.semantic_review == "required" and not result.persisted
        assert app.propose_character_reply(request(parent_options, i)) == result and len(transport.calls) == i + 1
        call = transport.calls[-1]; body = json.loads(call["body"])
        old_request = json.loads((parent_root / parent.digest / (stage_digest(parent.payload["requests"][i], "expression") + ".request.json")).read_text(encoding="utf-8"))
        assert json.loads(body["messages"][1]["content"]) == old_request["projection"] == row["projection"]
        assert body["messages"][0]["content"] == old_request["projection"]["policy"]
        assert sha256(call["body"]).hexdigest() == row["outbound_digest"]
        assert body["max_tokens"] == 4096 and body["thinking"] == {"type": "enabled"} and body["reasoning_effort"] == "high"
        assert "temperature" not in body and "tools" not in body and body["stream"] is False
        assert body["model"] == "deepseek-flash" and body["response_format"] == {"type": "json_object"} and call["timeout_seconds"] == 30
        for forbidden in ("PARENT_OLD_ANSWER", "UNSELECTED_PRIVATE_EXPERIENCE", "FUTURE_SECRET", "parent", "case_id", "request_digest", "source_context_digest", "expected", "audit_fingerprints"):
            assert forbidden not in body["messages"][1]["content"]
    assert len(list((root / plan.digest).glob("*.attempt.json"))) == len(list((root / plan.digest).glob("*.result.json"))) == 6
    assert before == {str(path): path.read_bytes() for path in (root / "products").rglob("*") if path.is_file()}
    audit = "".join(path.read_text(encoding="utf-8") for path in (root / plan.digest).glob("*.json"))
    assert "RAW_" not in audit and "PARENT_OLD_ANSWER" not in audit and "reasoning_content" not in audit
    resumed = open_trial(approved=plan.digest, transport=transport).application
    for i, result in enumerate(results): assert resumed.propose_character_reply(request(parent_options, i)) == result
    assert len(transport.calls) == 6


@pytest.mark.parametrize("change", ["partial", "references", "derived", "old-answer", "source"])
def test_parent_or_source_changes_reject_before_any_new_delivery(expression_trial_fixture, change):
    _, plan, _, open_trial, parent_root, parent, _, book = expression_trial_fixture
    row = parent.payload["requests"][0]
    if change == "source": book.write_bytes(book.read_bytes() + b"changed")
    else:
        phase, suffix = ("planning", ".result.json") if change == "references" else ("expression", ".request.json" if change == "derived" else ".result.json")
        path = parent_root / parent.digest / (stage_digest(row, phase) + suffix)
        if change == "partial": path.rename(path.with_suffix(".withheld"))
        else:
            value = json.loads(path.read_text(encoding="utf-8"))
            if change == "references": value["value"]["fact_refs"] = ["F2"]
            elif change == "derived": value["projection"]["selected_facts"][0]["content"] = "HAND_WRITTEN_PROJECTION"
            else: value["value"]["reply_text"] = "Changed but structurally valid old answer"
            path.write_text(json.dumps(value), encoding="utf-8")
    transport = ExpressionTransport()
    with pytest.raises((ValueError, OSError)): open_trial(approved=plan.digest, transport=transport)
    assert not transport.calls


def test_parent_change_during_active_trial_stops_even_after_repair(expression_trial_fixture):
    _, plan, _, open_trial, parent_root, parent, parent_options, _ = expression_trial_fixture
    transport = ExpressionTransport()
    app = open_trial(approved=plan.digest, transport=transport).application
    path = parent_root / parent.digest / (stage_digest(parent.payload["requests"][0], "expression") + ".result.json")
    original = path.read_bytes(); path.write_bytes(original + b" ")
    result = app.propose_character_reply(request(parent_options))
    assert result.status == "failed-closed" and result.code == "expression-parent-unavailable"
    path.write_bytes(original)
    assert app.propose_character_reply(request(parent_options)).code == "expression-trial-stopped" and not transport.calls


@pytest.mark.parametrize("fault,status,code", [
    ("network", "failed-closed", "transport-network"), ("timeout", "unknown", "transport-timeout"),
    ("length", "failed-closed", "response-truncated"), ("budget", "failed-closed", "response-overbudget"),
    ("schema", "failed-closed", "communication-expression-invalid"), ("credential", "unavailable", "character-credential-unavailable"),
])
def test_single_stage_faults_are_closed_stop_and_cached_without_resend(expression_trial_fixture, fault, status, code):
    root, plan, _, open_trial, _, _, parent_options, _ = expression_trial_fixture
    transport = ExpressionTransport(fault)
    app = open_trial(approved=plan.digest, transport=transport).application
    result = app.propose_character_reply(request(parent_options))
    assert result.status == status and result.code == code and not result.reply_text
    assert app.propose_character_reply(request(parent_options)) == result
    assert app.propose_character_reply(request(parent_options, 1)).code == "expression-trial-stopped"
    assert open_trial(approved=plan.digest, transport=transport).application.propose_character_reply(request(parent_options)) == result
    audit = "".join(path.read_text(encoding="utf-8") for path in (root / plan.digest).glob("*.json"))
    assert "RAW_" not in audit and len(transport.calls) == 1


@pytest.mark.parametrize("kind", ["crash", "partial", "phase", "digest", "unknown-code"])
def test_incomplete_or_tampered_expression_cache_is_unknown_and_never_restarts(expression_trial_fixture, kind):
    root, plan, _, open_trial, _, _, parent_options, _ = expression_trial_fixture
    transport = ExpressionTransport("crash" if kind == "crash" else "timeout" if kind == "unknown-code" else None)
    app = open_trial(approved=plan.digest, transport=transport).application
    if kind == "crash":
        with pytest.raises(SystemExit): app.propose_character_reply(request(parent_options))
    else:
        app.propose_character_reply(request(parent_options))
        path = root / plan.digest / (plan.payload["requests"][0]["request_digest"] + ".result.json")
        if kind == "partial": path.rename(path.with_suffix(".withheld"))
        else:
            value = json.loads(path.read_text(encoding="utf-8"))
            if kind == "phase": value["stage"] = "planning"
            elif kind == "digest": value["source_context_digest"] = "0" * 64
            else: value["status"] = "failed-closed"  # Timeout cannot become a known failure.
            path.write_text(json.dumps(value), encoding="utf-8")
    resumed = open_trial(approved=plan.digest, transport=transport).application
    assert resumed.propose_character_reply(request(parent_options)).status == "unknown"
    assert resumed.propose_character_reply(request(parent_options, 1)).status == "unknown" and len(transport.calls) == 1


@pytest.mark.parametrize("operation,calls", [("claim", 0), ("record", 1)])
def test_expression_audit_fault_stops_and_cannot_resume(expression_trial_fixture, monkeypatch, operation, calls):
    _, plan, _, open_trial, _, _, parent_options, _ = expression_trial_fixture
    transport = ExpressionTransport()
    app = open_trial(approved=plan.digest, transport=transport).application
    def fail(*args): raise OSError("RAW_AUDIT_SECRET")
    monkeypatch.setattr(FrozenAttemptRun, operation, fail)
    result = app.propose_character_reply(request(parent_options))
    assert result.status == "unknown" and not result.reply_text and "RAW_" not in str(result)
    assert app.propose_character_reply(request(parent_options, 1)).code == "expression-trial-stopped"
    assert open_trial(approved=plan.digest, transport=transport).application.propose_character_reply(request(parent_options)).status == "unknown"
    assert len(transport.calls) == calls


def test_cli_fixed_root_default_prepare_does_not_print_parent_answers_or_execute(expression_trial_fixture, tmp_path, monkeypatch, capsys):
    from dynamic_subject_agent.model_gateway import ModelGateway
    _, plan, options, _, parent_root, parent, _, _ = expression_trial_fixture
    repo = tmp_path / "cli-repo"
    destination = repo / ".artifacts/character-communication-trials"
    destination.mkdir(parents=True)
    shutil.copyfile(parent_root / (parent.digest + ".plan.json"), destination / (parent.digest + ".plan.json"))
    shutil.copytree(parent_root / parent.digest, destination / parent.digest)
    path = Path(__file__).resolve().parents[1] / "app/desktop/character_expression_thinking_trial.py"
    spec = importlib.util.spec_from_file_location("expression_thinking_cli", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setattr(module, "__file__", str(repo / "app/desktop/character_expression_thinking_trial.py"))
    monkeypatch.setattr(sys, "argv", ["expression-thinking", "--draft", str(options["draft_path"]), "--source-root", str(options["source_root"]), "--parent-plan", parent.digest])
    monkeypatch.setattr(ModelGateway, "execute", lambda *a: pytest.fail("default CLI executed a task"))
    module.main()
    output = capsys.readouterr().out; summary = json.loads(output)
    assert summary["digest"] == plan.digest and summary["expression_calls"] == 6 and summary["planning_calls"] == 0
    assert "PARENT_OLD_ANSWER" not in output and "selected_facts" not in output
    assert not (Path(summary["plan_path"]).parent / summary["digest"]).exists()


def test_prepare_rejects_identical_expressions_from_distinct_valid_parent_contexts(model_fixture):
    from dynamic_subject_agent.local_product import prepare_character_communication_trial, open_character_communication_trial
    draft, create, path, book = model_fixture
    organize_fixture(draft); create()
    cases = dict(version="character-communication-plan-cases-1", cases=[dict(id=f"c-{i}", message="同一个当前问题" if i < 2 else f"问题{i}",
        context_mode="organized" if i == 1 else "flat") for i in range(6)])
    options = dict(draft_path=path, source_root=book.parent, reviewed_digest=sha256(path.read_bytes()).hexdigest(), subject_id="self", anchor_id="start", cases=cases)
    parent_root = path.parent / "duplicate-parent"
    parent = prepare_character_communication_trial(parent_root, **options)
    class EmptyFactPlanning(CommunicationTransport):
        def post_json(self, **kwargs):
            response = super().post_json(**kwargs); value = json.loads(response.body)
            if "self_knowledge" in json.loads(json.loads(kwargs["body"])["messages"][1]["content"]):
                value["choices"][0]["message"]["content"] = json.dumps({"action": "offer_topic", "fact_refs": []})
            return DeepSeekHttpResponse(200, json.dumps(value).encode())
    with open_character_communication_trial(parent_root, **options, approved_plan=parent.digest, _transport=EmptyFactPlanning()) as product:
        for i in range(6): assert product.application.propose_character_reply(request(options, i)).status == "candidate"
    with pytest.raises(ValueError, match="duplicate frozen expression"):
        prepare_character_expression_thinking_trial(path.parent / "duplicate-expression", parent_trial_root=parent_root,
            parent_plan_digest=parent.digest, draft_path=path, source_root=book.parent)
