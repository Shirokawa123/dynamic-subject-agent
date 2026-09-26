from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
from dynamic_subject_agent.character_context_trial import canonical_json, TRIAL_POLICY
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse, DEEPSEEK_MODEL, DEEPSEEK_ENDPOINT
from dynamic_subject_agent.local_product import prepare_character_context_trial, open_character_context_trial
from test_character_evidence_model import model_fixture, organize_fixture


class TrialTransport(DeepSeekTransport):
    def __init__(self, *, value=None, failure=None, finish="stop", model=DEEPSEEK_MODEL,
                 reasoning="", tools=None, completion=40):
        self.value = {"reply_text": "我也会在意画画的过程。", "language": "zh"} if value is None else value
        self.failure, self.finish, self.model = failure, finish, model
        self.reasoning, self.tools, self.completion = reasoning, tools, completion
        self.calls = []

    def post_json(self, **kwargs):
        self.calls.append(kwargs)
        if self.failure:
            raise self.failure
        payload = dict(model=self.model, choices=[dict(finish_reason=self.finish, message=dict(
            role="assistant", content=json.dumps(self.value), reasoning_content=self.reasoning, tool_calls=self.tools))],
            usage=dict(prompt_tokens=80, completion_tokens=self.completion))
        return DeepSeekHttpResponse(200, json.dumps(payload).encode())


@pytest.fixture
def trial_fixture(model_fixture):
    draft, create, path, book = model_fixture
    organize_fixture(draft)
    create()
    root = path.parent / "trials"
    cases = dict(version="character-context-cases-1", cases=[dict(id=f"case-{i:02}", message=f"聊聊画画，第{i}个话题。") for i in range(12)])
    options = dict(draft_path=path, source_root=book.parent, reviewed_digest=sha256(path.read_bytes()).hexdigest(),
                   subject_id="self", anchor_id="start", cases=cases)
    plan = prepare_character_context_trial(root, **options)
    opened = []
    def open_trial(*, approved=None, transport=None, **overrides):
        product = open_character_context_trial(root, **{**options, **overrides}, approved_plan=approved, _transport=transport)
        opened.append(product)
        return product
    yield root, plan, options, open_trial, path, book
    for product in opened:
        product.close()


def request(options, index=0, mode="flat", message=None):
    return CharacterChatContextRequest(options["subject_id"], options["anchor_id"],
                                      message or options["cases"]["cases"][index]["message"], mode)


def test_prepare_and_default_trial_have_zero_gateway_transport_or_credential_calls(trial_fixture, monkeypatch):
    from dynamic_subject_agent.model_gateway import ModelGateway
    root, plan, options, open_trial, _, _ = trial_fixture
    monkeypatch.setattr(ModelGateway, "execute", lambda *a: pytest.fail("offline trial called gateway"))
    transport = TrialTransport()
    app = open_trial(transport=transport).application
    preview = app.preview_character_reply(request(options))
    assert preview.status == "previewed" and preview.projection.policy == TRIAL_POLICY
    assert preview.request_digest == plan.payload["requests"][0]["request_digest"]
    assert app.propose_character_reply(request(options)).code == "trial-not-approved"
    assert not transport.calls and not (root / plan.digest).exists()
    assert len(plan.payload["requests"]) == 24
    assert {row["projection"]["policy"] for row in plan.payload["requests"]} == {TRIAL_POLICY}
    assert (root / (plan.digest + ".plan.json")).is_file()


def test_all_24_facade_requests_are_exact_frozen_bytes_and_replays_never_resend(trial_fixture):
    root, plan, options, open_trial, _, _ = trial_fixture
    transport = TrialTransport(model="deepseek-flash", completion=550)
    app = open_trial(approved=plan.digest, transport=transport).application
    for index, row in enumerate(plan.payload["requests"]):
        req = request(options, index // 2, row["mode"])
        preview = app.preview_character_reply(req)
        assert asdict(preview.projection) == row["projection"] or canonical_json(asdict(preview.projection)) == canonical_json(row["projection"])
        result = app.propose_character_reply(req)
        assert result.status == "candidate" and result.request_digest == row["request_digest"] and not result.persisted
        assert app.propose_character_reply(req) == result
        assert len(transport.calls) == index + 1
        call = transport.calls[-1]
        assert call["endpoint"] == DEEPSEEK_ENDPOINT
        assert sha256(call["body"]).hexdigest() == row["outbound_digest"]
        body = json.loads(call["body"])
        assert body["model"] == DEEPSEEK_MODEL
        assert body["max_tokens"] == 600 and body["temperature"] == 0.3 and body["stream"] is False
        assert body["thinking"] == {"type": "disabled"} and body["response_format"] == {"type": "json_object"}
        assert body["messages"][0]["content"] == TRIAL_POLICY
        assert json.loads(body["messages"][1]["content"]) == row["projection"]
    assert len(list((root / plan.digest).glob("*.attempt.json"))) == 24
    assert len(list((root / plan.digest).glob("*.result.json"))) == 24
    app_again = open_trial(approved=plan.digest, transport=transport).application
    assert app_again.propose_character_reply(request(options)).status == "candidate" and len(transport.calls) == 24


def test_wrong_approval_changed_cases_or_changed_draft_fail_before_key_or_send(trial_fixture):
    root, plan, options, open_trial, path, _ = trial_fixture
    transport = TrialTransport()
    with pytest.raises(ValueError): open_trial(approved="0" * 64, transport=transport)
    changed = json.loads(json.dumps(options["cases"]))
    changed["cases"][0]["message"] += "换一个问题"
    with pytest.raises(ValueError): open_trial(approved=plan.digest, transport=transport, cases=changed)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError): open_trial(approved=plan.digest, transport=transport)
    assert not transport.calls and not (root / plan.digest).exists()


def test_extra_message_out_of_order_and_wrong_projection_digest_do_not_send(trial_fixture):
    from dynamic_subject_agent.character_context_trial_provider import DeepSeekCharacterContextAdapter
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID
    from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
    root, plan, options, open_trial, _, _ = trial_fixture
    transport = TrialTransport()
    app = open_trial(approved=plan.digest, transport=transport).application
    assert app.propose_character_reply(request(options, message="额外消息")).code == "trial-request-not-in-plan"
    assert app.propose_character_reply(request(options, 1)).code == "trial-request-out-of-order"
    projection = app.preview_character_reply(request(options)).projection
    adapter = DeepSeekCharacterContextAdapter(transport=transport,
        credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID),
        allowed_outbound_digests=["0" * 64])
    with pytest.raises(ValueError): adapter.invoke(ModelTask(ModelTaskKind.CHARACTER_CONTEXT_REPLY, projection))
    with pytest.raises(ValueError): adapter.invoke(ModelTask(ModelTaskKind.CHARACTER_DIALOGUE_REPLY, projection))
    assert not transport.calls
    assert app.propose_character_reply(request(options)).status == "candidate" and len(transport.calls) == 1


@pytest.mark.parametrize("bad", [
    dict(failure=TimeoutError("KEY HEADER RAW SECRET")),
    dict(finish="length"), dict(reasoning="RAW_REASONING_SECRET"), dict(tools=[{"secret": "RAW_TOOL_SECRET"}]),
    dict(model="unapproved-model"), dict(completion=601),
    dict(value={"reply_text": "x", "language": "en"}), dict(value={"reply_text": "x" * 1201, "language": "zh"}),
    dict(value={"reply_text": "x", "language": "zh", "memory": "RAW_MEMORY_SECRET"}),
])
def test_any_transport_or_output_failure_stops_batch_without_retry_or_raw_audit(trial_fixture, bad):
    root, plan, options, open_trial, _, _ = trial_fixture
    transport = TrialTransport(**bad)
    app = open_trial(approved=plan.digest, transport=transport).application
    failed = app.propose_character_reply(request(options))
    assert failed.status == "failed-closed" and failed.code == "trial-attempt-failed"
    assert app.propose_character_reply(request(options)) == failed
    assert app.propose_character_reply(request(options, mode="organized")).code == "trial-stopped"
    assert len(transport.calls) == 1
    audit = "".join(path.read_text(encoding="utf-8") for path in (root / plan.digest).glob("*.json"))
    for secret in ("KEY HEADER RAW SECRET", "RAW_REASONING_SECRET", "RAW_TOOL_SECRET", "RAW_MEMORY_SECRET", "headers", "reasoning_content"):
        assert secret not in audit
    again = open_trial(approved=plan.digest, transport=transport).application
    assert again.propose_character_reply(request(options)) == failed
    assert again.propose_character_reply(request(options, mode="organized")).status == "unknown"
    assert len(transport.calls) == 1


def test_source_failure_then_repair_still_stops_approved_batch_with_zero_sends(trial_fixture):
    root, plan, options, open_trial, _, book = trial_fixture
    transport = TrialTransport()
    app = open_trial(approved=plan.digest, transport=transport).application
    original = book.read_bytes()
    book.write_bytes(original + b"bad")
    assert app.propose_character_reply(request(options)).status == "failed-closed"
    book.write_bytes(original)
    assert app.propose_character_reply(request(options)).code == "trial-stopped"
    assert not transport.calls
    assert json.loads((root / plan.digest / "stopped.json").read_text())["reason"] == "trial-context-unavailable"


def test_missing_secure_credential_is_typed_unavailable_consumes_attempt_and_stops(trial_fixture):
    from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
    from dynamic_subject_agent.deepseek import DeepSeekCredentialResolver, DeepSeekUrlLibTransport
    root, plan, options, open_trial, _, _ = trial_fixture
    class Resolver(DeepSeekCredentialResolver):
        def __init__(self): self.calls = 0
        def resolve(self, credential_ref):
            self.calls += 1
            assert list((root / plan.digest).glob("*.attempt.json"))
            raise CharacterCredentialUnavailable()
    resolver = Resolver()
    transport = DeepSeekUrlLibTransport(credential_resolver=resolver,
                                        _opener=lambda *a, **kw: pytest.fail("missing credential reached network"))
    app = open_trial(approved=plan.digest, transport=transport).application
    result = app.propose_character_reply(request(options))
    assert result.status == "unavailable" and result.code == "character-credential-unavailable"
    assert app.propose_character_reply(request(options)) == result and resolver.calls == 1
    assert app.propose_character_reply(request(options, mode="organized")).code == "trial-stopped"
    resumed = open_trial(approved=plan.digest, transport=transport).application
    assert resumed.propose_character_reply(request(options)) == result and resolver.calls == 1


@pytest.mark.parametrize("invalid", ["count", "duplicate-id", "duplicate-message", "extra-field"])
def test_invalid_case_recipe_is_rejected_before_start_or_send(trial_fixture, invalid):
    root, plan, options, open_trial, _, _ = trial_fixture
    cases = json.loads(json.dumps(options["cases"]))
    if invalid == "count": cases["cases"].pop()
    elif invalid == "duplicate-id": cases["cases"][1]["id"] = cases["cases"][0]["id"]
    elif invalid == "duplicate-message": cases["cases"][1]["message"] = cases["cases"][0]["message"]
    else: cases["cases"][0]["private_history"] = "not permitted"
    transport = TrialTransport()
    with pytest.raises(ValueError): open_trial(approved=plan.digest, transport=transport, cases=cases)
    assert not transport.calls and not (root / plan.digest).exists()


def test_restart_claim_is_exclusive_and_unfinished_attempt_is_unknown(trial_fixture):
    root, plan, options, open_trial, _, _ = trial_fixture
    transport = TrialTransport()
    first = open_trial(approved=plan.digest, transport=transport)
    # A second process/product cannot resume even before the first send.
    second = open_trial(approved=plan.digest, transport=transport)
    assert second.application.propose_character_reply(request(options)).status == "unknown"
    assert not transport.calls
    assert first.application.propose_character_reply(request(options)).status == "candidate"
    digest = plan.payload["requests"][0]["request_digest"]
    (root / plan.digest / (digest + ".result.json")).rename(root / plan.digest / (digest + ".withheld.json"))
    first.close()
    again = open_trial(approved=plan.digest, transport=transport).application
    assert again.propose_character_reply(request(options)).status == "unknown" and len(transport.calls) == 1


def test_plan_and_wire_exclude_source_author_metadata_future_and_private_history(trial_fixture):
    root, plan, options, open_trial, _, _ = trial_fixture
    for row in plan.payload["requests"]:
        wire = canonical_json(row["projection"])
        for forbidden in ("sample.epub", "ch.html", "reviewed source", "FUTURE_PRIVATE_SECRET", "evidence_ids", "claim_ids",
                          "core-self", "child-art", "selection", "recent_dialogue", "time_basis"):
            assert forbidden not in wire
    assert plan.payload["generation"]["max_tokens"] == 600


def test_prepare_rejects_complete_wire_over_transport_limit_before_any_activation(trial_fixture):
    root, _, options, _, path, _ = trial_fixture
    draft = json.loads(path.read_text(encoding="utf-8"))
    draft["chat_stage_description"] = "段" * 500
    draft["chat_organization"]["core"] = [dict(id=f"core-{i}", title="认识", content="画" * 4750, claim_ids=["a"])
                                          for i in range(4)]
    path.write_text(json.dumps(draft), encoding="utf-8")
    cases = dict(version="character-context-cases-1", cases=[dict(id=f"c-{i}", message="问" * 990 + str(i)) for i in range(12)])
    large_root = root / "large"
    with pytest.raises(ValueError, match="trial-outbound-too-large"):
        prepare_character_context_trial(large_root, **{**options, "reviewed_digest": sha256(path.read_bytes()).hexdigest(), "cases": cases})
    assert not list(large_root.glob("*.plan.json"))


def test_default_cli_prints_only_summary_and_saves_complete_plan(trial_fixture, tmp_path):
    _, _, options, _, path, _ = trial_fixture
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps(options["cases"], ensure_ascii=False), encoding="utf-8")
    cli = Path(__file__).resolve().parents[1] / "app/desktop/character_context_trial.py"
    command = [sys.executable, str(cli), "--draft", str(path), "--source-root", str(options["source_root"]),
               "--reviewed-digest", options["reviewed_digest"], "--subject", "self", "--anchor", "start", "--cases", str(cases_path)]
    completed = subprocess.run(command, capture_output=True, check=True, encoding="utf-8",
                               env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    summary = json.loads(completed.stdout)
    assert summary["status"] == "prepared" and summary["request_count"] == 24
    assert "projection" not in summary and "聊聊画画" not in completed.stdout
    saved = json.loads(Path(summary["plan_path"]).read_text(encoding="utf-8"))
    assert saved["digest"] == summary["digest"] and len(saved["plan"]["requests"]) == 24
    assert not (Path(summary["plan_path"]).parent / summary["digest"]).exists()
