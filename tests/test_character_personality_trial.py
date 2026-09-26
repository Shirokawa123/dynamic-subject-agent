from dataclasses import asdict
from hashlib import sha256
import json

import pytest

from dynamic_subject_agent.character_communication_trial import stage_digest
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse
from dynamic_subject_agent.local_product import prepare_character_personality_trial, open_character_personality_trial, prepare_character_communication_trial
from test_character_evidence_model import model_fixture
from test_character_personality import personality_fixture


class PersonalityTransport(DeepSeekTransport):
    def __init__(self, *, fault=None, stage="expression"):
        self.fault, self.stage, self.calls = fault, stage, []
    def post_json(self, **kwargs):
        self.calls.append(kwargs)
        body = json.loads(kwargs["body"]); envelope = json.loads(body["messages"][1]["content"])
        stage = "planning" if "self_knowledge" in envelope["conversation"] else "expression"
        if stage == self.stage and self.fault == "timeout": raise TimeoutError("RAW_TIMEOUT_SECRET")
        if stage == self.stage and self.fault == "crash": raise SystemExit("simulated crash")
        value = dict(action="offer_topic", fact_refs=[]) if stage == "planning" else dict(reply_text="这轮可以聊一个创作取舍。", language="zh")
        if stage == self.stage and self.fault == "refs": value = dict(action="answer", fact_refs=["UNKNOWN_REF"])
        finish = "length" if stage == self.stage and self.fault == "length" else "stop"
        return DeepSeekHttpResponse(200, json.dumps(dict(model="deepseek-flash", choices=[dict(finish_reason=finish,
            message=dict(role="assistant", content="" if finish == "length" else json.dumps(value), reasoning_content="RAW_REASONING_SECRET"))],
            usage=dict(prompt_tokens=100, completion_tokens=80))).encode())


@pytest.fixture
def personality_trial_fixture(personality_fixture):
    _, path, book, _, open_local = personality_fixture
    _, _, _, sidecar = open_local(preview_only=True)
    root = path.parent / "personality-trials"
    cases = dict(version="character-communication-plan-cases-1", cases=[dict(id=f"case-{i}", message=f"聊一件绘画取舍，第{i}题。", context_mode="flat") for i in range(6)])
    options = dict(draft_path=path, source_root=book.parent, reviewed_digest=sha256(path.read_bytes()).hexdigest(),
        sidecar_path=sidecar, personality_digest=sha256(sidecar.read_bytes()).hexdigest(), subject_id="self", anchor_id="start", cases=cases)
    plan = prepare_character_personality_trial(root, **options)
    opened = []
    def open_trial(*, approved=None, transport=None, **overrides):
        product = open_character_personality_trial(root, **{**options, **overrides}, approved_plan=approved, _transport=transport)
        opened.append(product); return product
    yield root, plan, options, open_trial
    for product in opened: product.close()


def request(options, i=0):
    from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
    case = options["cases"]["cases"][i]
    return CharacterChatContextRequest("self", "start", case["message"], "flat")


def test_new_plan_approval_is_required_and_both_adapter_versions_are_isolated(personality_trial_fixture, monkeypatch):
    from dynamic_subject_agent.model_gateway import ModelGateway
    from dynamic_subject_agent.character_communication_trial_provider import DeepSeekCommunicationTrialAdapter, DeepSeekPersonalityTrialAdapter
    from dynamic_subject_agent.cognition import CredentialRef
    root, plan, options, open_trial = personality_trial_fixture
    baseline_options = {key: value for key, value in options.items() if key not in ("sidecar_path", "personality_digest")}
    baseline = prepare_character_communication_trial(root / "baseline", **baseline_options, expression_profile="thinking-high")
    monkeypatch.setattr(ModelGateway, "execute", lambda *a: pytest.fail("unapproved invoked model gateway"))
    transport = PersonalityTransport()
    app = open_trial(transport=transport).application
    assert app.preview_character_reply(request(options)).status == "previewed"
    assert app.propose_character_reply(request(options)).code == "communication-trial-not-approved"
    with pytest.raises(ValueError): open_trial(approved=baseline.digest, transport=transport)
    credential = CredentialRef.reference(backend_id="test", key_id="test")
    with pytest.raises(ValueError): DeepSeekCommunicationTrialAdapter(plan, run_root=root / plan.digest, transport=transport, credential_ref=credential)
    with pytest.raises(ValueError): DeepSeekPersonalityTrialAdapter(baseline, sidecar_path=options["sidecar_path"], run_root=root / baseline.digest,
        transport=transport, credential_ref=credential)
    assert not transport.calls and not (root / plan.digest).exists()


def test_six_personality_cases_claim_first_preserve_wrapper_and_restart_never_resends(personality_trial_fixture):
    root, plan, options, open_trial = personality_trial_fixture
    class ObservedTransport(PersonalityTransport):
        def post_json(self, **kwargs):
            i = len(self.calls) // 2; stage = "planning" if len(self.calls) % 2 == 0 else "expression"
            assert (root / plan.digest / (stage_digest(plan.payload["requests"][i], stage) + ".attempt.json")).exists()
            return super().post_json(**kwargs)
    transport = ObservedTransport()
    app = open_trial(approved=plan.digest, transport=transport).application
    results = []
    for i, row in enumerate(plan.payload["requests"]):
        result = app.propose_character_reply(request(options, i)); results.append(result)
        assert result.status == "candidate" and result.semantic_review == "required" and not result.persisted
        assert app.propose_character_reply(request(options, i)) == result and len(transport.calls) == (i + 1) * 2
        planning, expression = [json.loads(call["body"]) for call in transport.calls[-2:]]
        envelopes = [json.loads(body["messages"][1]["content"]) for body in (planning, expression)]
        assert envelopes[0] == row["projection"]
        assert envelopes[1]["conversation"]["selected_facts"] == []
        for key in ("character_core", "personality", "policy"):
            assert envelopes[1][key] == envelopes[0][key]
        derived = json.loads((root / plan.digest / (stage_digest(row, "expression") + ".request.json")).read_text(encoding="utf-8"))
        assert derived["projection"] == envelopes[1] and sha256(transport.calls[-1]["body"]).hexdigest() == derived["outbound_digest"]
        for body, call in zip((planning, expression), transport.calls[-2:]):
            assert body["max_tokens"] == 4096 and body["thinking"] == {"type": "enabled"} and body["reasoning_effort"] == "high"
            assert body["stream"] is False and body["response_format"] == {"type": "json_object"} and call["timeout_seconds"] == 30
            assert "temperature" not in body and "tools" not in body
            for forbidden in ("claim_ids", "sidecar_digest", "candidate-private-id", "core-self", "reviewed_digest", "FUTURE_PRIVATE_SECRET"):
                assert forbidden not in body["messages"][1]["content"]
    assert len(list((root / plan.digest).glob("*.attempt.json"))) == 12
    audit = "".join(path.read_text(encoding="utf-8") for path in (root / plan.digest).glob("*.json"))
    assert "RAW_REASONING_SECRET" not in audit
    resumed = open_trial(approved=plan.digest, transport=transport).application
    for i, result in enumerate(results): assert resumed.propose_character_reply(request(options, i)) == result
    assert len(transport.calls) == 12


@pytest.mark.parametrize("stage,fault,status,code,calls", [("planning", "refs", "failed-closed", "communication-plan-invalid", 1),
    ("expression", "timeout", "unknown", "transport-timeout", 2), ("planning", "timeout", "unknown", "transport-timeout", 1),
    ("expression", "length", "failed-closed", "response-truncated", 2)])
def test_personality_failures_stop_and_cache_without_retry(personality_trial_fixture, stage, fault, status, code, calls):
    _, plan, options, open_trial = personality_trial_fixture
    transport = PersonalityTransport(stage=stage, fault=fault)
    app = open_trial(approved=plan.digest, transport=transport).application
    result = app.propose_character_reply(request(options))
    assert result.status == status and result.code == code and not result.reply_text
    assert app.propose_character_reply(request(options, 1)).code == "communication-trial-stopped"
    assert open_trial(approved=plan.digest, transport=transport).application.propose_character_reply(request(options)) == result
    assert len(transport.calls) == calls


@pytest.mark.parametrize("change", ["sidecar", "derived-wrapper", "planning-result", "partial", "crash"])
def test_changed_source_or_incomplete_audit_never_resumes_expression(personality_trial_fixture, change):
    root, plan, options, open_trial = personality_trial_fixture
    transport = PersonalityTransport(stage="expression", fault="crash" if change == "crash" else None)
    app = open_trial(approved=plan.digest, transport=transport).application
    if change == "sidecar":
        options["sidecar_path"].write_bytes(options["sidecar_path"].read_bytes() + b" ")
        assert app.propose_character_reply(request(options)).status == "failed-closed" and not transport.calls
        with pytest.raises(ValueError): open_trial(approved=plan.digest, transport=transport)
        return
    if change == "crash":
        with pytest.raises(SystemExit): app.propose_character_reply(request(options))
    else:
        app.propose_character_reply(request(options))
        row = plan.payload["requests"][0]
        stage = "planning" if change == "planning-result" else "expression"
        suffix = ".request.json" if change == "derived-wrapper" else ".result.json"
        path = root / plan.digest / (stage_digest(row, stage) + suffix)
        if change == "partial": path.rename(path.with_suffix(".withheld"))
        else:
            value = json.loads(path.read_text(encoding="utf-8"))
            if change == "derived-wrapper": value["projection"]["personality"][0]["limits"] = "TAMPERED"
            else: value["value"]["fact_refs"] = ["F1"]
            path.write_text(json.dumps(value), encoding="utf-8")
    assert open_trial(approved=plan.digest, transport=transport).application.propose_character_reply(request(options)).status == "unknown"
    assert len(transport.calls) == 2


def test_missing_credential_is_lazy_after_attempt_and_never_reaches_network(personality_trial_fixture):
    from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
    from dynamic_subject_agent.deepseek import DeepSeekCredentialResolver, DeepSeekUrlLibTransport
    root, plan, options, open_trial = personality_trial_fixture
    class Missing(DeepSeekCredentialResolver):
        calls = 0
        def resolve(self, reference):
            self.calls += 1
            assert (root / plan.digest / (stage_digest(plan.payload["requests"][0], "planning") + ".attempt.json")).exists()
            raise CharacterCredentialUnavailable()
    resolver = Missing()
    transport = DeepSeekUrlLibTransport(credential_resolver=resolver, _opener=lambda *a, **kw: pytest.fail("missing credential reached network"))
    result = open_trial(approved=plan.digest, transport=transport).application.propose_character_reply(request(options))
    assert result.status == "unavailable" and result.code == "character-credential-unavailable" and resolver.calls == 1


def test_sidecar_changed_after_planning_audit_blocks_expression_transport(personality_trial_fixture, monkeypatch):
    from dynamic_subject_agent.frozen_attempt import FrozenAttemptRun
    _, plan, options, open_trial = personality_trial_fixture
    transport = PersonalityTransport()
    app = open_trial(approved=plan.digest, transport=transport).application
    original = FrozenAttemptRun.record
    raw = options["sidecar_path"].read_bytes()
    def changed(self, digest, audit):
        original(self, digest, audit)
        if audit["stage"] == "planning": options["sidecar_path"].write_bytes(raw + b" ")
    monkeypatch.setattr(FrozenAttemptRun, "record", changed)
    result = app.propose_character_reply(request(options))
    assert result.status == "failed-closed" and len(transport.calls) == 1
    options["sidecar_path"].write_bytes(raw)
    assert open_trial(approved=plan.digest, transport=transport).application.propose_character_reply(request(options)) == result
    assert len(transport.calls) == 1
