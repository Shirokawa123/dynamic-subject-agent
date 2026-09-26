from dataclasses import asdict, replace
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
from dynamic_subject_agent.character_reply_candidate import CharacterReplyLab
from dynamic_subject_agent.character_reply_review import REVIEW_POLICY
from dynamic_subject_agent.character_reply_review_trial import CharacterReplyReviewRequest
from dynamic_subject_agent.local_product import prepare_character_reply_review_trial, open_character_reply_review_trial
from dynamic_subject_agent.model_gateway import (
    ModelGateway, ModelTaskKind, ModelGatewayFailure, ModelResult, ProviderAdapter,
    ProviderCapabilities, StructuredOutputMode,
)
from test_character_evidence_model import model_fixture, organize_fixture, CandidateTestAdapter
from test_character_context_trial import TrialTransport


def review_value(verdict="supported", quote="候选", labels=None):
    return dict(verdict=verdict, issues=[] if verdict != "unsupported" else [dict(
        quote=quote, kind="unsupported_detail", basis_labels=["F1"] if labels is None else labels)])


class LocalReviewAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities("test", "review", True, (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self, value=None, failure=None):
        self.value = review_value() if value is None else value
        self.failure, self.calls = failure, []

    def invoke(self, task):
        self.calls.append(task)
        assert task.kind is ModelTaskKind.CHARACTER_REPLY_REVIEW
        if self.failure:
            raise self.failure
        return ModelResult(task.kind, self.value)


@pytest.mark.parametrize("verdict", ["supported", "unsupported", "uncertain"])
def test_full_facade_candidate_review_returns_or_blocks_without_generation_retry(model_fixture, verdict):
    _, create, _, _ = model_fixture
    generator = CandidateTestAdapter.make({"reply_text": "冻结的候选。", "language": "zh"})
    reviewer = LocalReviewAdapter(review_value(verdict))
    product = create(CharacterReplyLab(ModelGateway(generator), review_gateway=ModelGateway(reviewer)))
    app = product.application
    request = CharacterChatContextRequest("self", "start", "聊聊画画")
    preview = app.preview_character_reply(request)
    assert not generator.calls and not reviewer.calls
    result = app.propose_character_reply(request)
    assert result.status == ("candidate" if verdict == "supported" else "rejected")
    assert result.reply_text == ("冻结的候选。" if verdict == "supported" else "")
    assert result.review_verdict == verdict and result.semantic_review == "model-" + verdict
    assert not result.persisted and len(generator.calls) == len(reviewer.calls) == 1
    assert generator.calls[0].kind is ModelTaskKind.CHARACTER_CONTEXT_REPLY
    projection = asdict(reviewer.calls[0].payload)
    assert set(projection) == {"self_knowledge", "stage_description", "interaction_context", "current_message", "candidate_text", "policy"}
    assert projection["candidate_text"] == "冻结的候选。" and projection["policy"] == REVIEW_POLICY
    assert projection["self_knowledge"][0]["label"] == "F1"
    assert projection["self_knowledge"][0]["content"] == preview.projection.self_knowledge[0].content
    assert projection["interaction_context"][0]["label"] == "I1"
    assert tuple(item["content"] for item in projection["interaction_context"]) == preview.projection.encounter
    assert preview.projection.policy not in projection["policy"]
    product.close()
    assert app.propose_character_reply(request).status == "unavailable" and len(reviewer.calls) == 1


@pytest.mark.parametrize("bad", [
    {}, {"verdict": "PASS", "issues": []}, {"verdict": "supported", "issues": [{}]},
    {"verdict": "unsupported", "issues": []},
    review_value("unsupported", quote="不存在的片段"), review_value("unsupported", labels=["F999"]),
    review_value("unsupported", labels=["F1", "F1"]),
    {"verdict": "unsupported", "issues": [dict(quote="候选", kind="arbitrary", basis_labels=[])]},
    {"verdict": "unsupported", "issues": [dict(quote="候选", kind="unsupported_detail", basis_labels=[])] * 7},
    {"verdict": "supported", "issues": [], "private_state": "SECRET"},
])
def test_full_facade_review_invalid_structure_or_evidence_fails_closed(model_fixture, bad):
    _, create, _, _ = model_fixture
    generator = CandidateTestAdapter.make({"reply_text": "候选", "language": "zh"})
    reviewer = LocalReviewAdapter(bad)
    result = create(CharacterReplyLab(ModelGateway(generator), review_gateway=ModelGateway(reviewer))).application.propose_character_reply(
        CharacterChatContextRequest("self", "start", "你好"))
    assert result.status == "failed-closed" and result.code == "reply-review-failed"
    assert not result.reply_text and result.review_verdict == "" and not result.review_issues
    assert len(reviewer.calls) == len(generator.calls) == 1 and "SECRET" not in str(result)


@pytest.mark.parametrize("failure,status,code", [
    (RuntimeError("KEY SECRET"), "failed-closed", "reply-review-failed"),
    (ModelGatewayFailure("character-credential-unavailable"), "unavailable", "character-credential-unavailable"),
])
def test_local_review_failure_and_credential_unavailable_are_not_normal_rejections(model_fixture, failure, status, code):
    _, create, _, _ = model_fixture
    reviewer = LocalReviewAdapter(failure=failure)
    app = create(CharacterReplyLab(ModelGateway(CandidateTestAdapter.make({"reply_text": "候选", "language": "zh"})), review_gateway=ModelGateway(reviewer))).application
    result = app.propose_character_reply(CharacterChatContextRequest("self", "start", "你好"))
    assert result.status == status and result.code == code and not result.reply_text and not result.review_verdict
    assert "KEY" not in str(result)


def test_no_new_default_remote_use_and_no_review_after_bad_generation_or_source(model_fixture):
    _, create, _, book = model_fixture
    generator = CandidateTestAdapter.make({"reply_text": "候选", "language": "zh"})
    app = create(CharacterReplyLab(ModelGateway(generator))).application
    assert app.propose_character_reply(CharacterChatContextRequest("self", "start", "你好")).semantic_review == "required"
    assert len(generator.calls) == 1
    with pytest.raises(ValueError):
        CharacterReplyLab(ModelGateway(generator), review_gateway=ModelGateway(CandidateTestAdapter.make(local=False)))
    reviewer = LocalReviewAdapter()
    bad_generator = CandidateTestAdapter.make(value={})
    app = create(CharacterReplyLab(ModelGateway(bad_generator), review_gateway=ModelGateway(reviewer))).application
    assert app.propose_character_reply(CharacterChatContextRequest("self", "start", "你好")).status == "failed-closed"
    assert not reviewer.calls
    book.write_bytes(book.read_bytes() + b"changed")
    assert app.propose_character_reply(CharacterChatContextRequest("self", "start", "你好")).status == "failed-closed"
    assert len(bad_generator.calls) == 1 and not reviewer.calls


@pytest.fixture
def review_trial_fixture(model_fixture):
    draft, create, path, book = model_fixture
    organize_fixture(draft)
    create()
    root = path.parent / "reviews"
    cases = dict(version="character-reply-review-cases-1", cases=[dict(
        id=f"case-{i:02}", message="我们刚认识，聊聊画画？", context_mode="flat" if i % 2 == 0 else "organized",
        candidate_text=f"冻结的候选{i}。") for i in range(24)])
    options = dict(draft_path=path, source_root=book.parent, reviewed_digest=sha256(path.read_bytes()).hexdigest(),
                   subject_id="self", anchor_id="start", cases=cases)
    plan = prepare_character_reply_review_trial(root, **options)
    opened = []
    def open_trial(*, approved=None, transport=None, **overrides):
        product = open_character_reply_review_trial(root, **{**options, **overrides}, approved_plan=approved, _transport=transport)
        opened.append(product)
        return product
    yield root, plan, options, open_trial, path, book
    for product in opened:
        product.close()


def request(options, index=0):
    case = options["cases"]["cases"][index]
    return CharacterReplyReviewRequest(CharacterChatContextRequest(options["subject_id"], options["anchor_id"],
        case["message"], case["context_mode"]), case["id"])


class ReviewTransport(TrialTransport):
    def __init__(self, **kwargs):
        super().__init__(value=review_value(), **kwargs)

    def post_json(self, **kwargs):
        # Alternate all three normal verdicts; rejections do not stop calibration.
        verdict = ("supported", "unsupported", "uncertain")[len(self.calls) % 3]
        projection = json.loads(json.loads(kwargs["body"])["messages"][1]["content"])
        self.value = review_value(verdict, projection["candidate_text"])
        return super().post_json(**kwargs)


def test_review_prepare_and_unapproved_full_operation_are_completely_offline(review_trial_fixture, monkeypatch):
    root, plan, options, open_trial, _, _ = review_trial_fixture
    monkeypatch.setattr(ModelGateway, "execute", lambda *a: pytest.fail("prepare called gateway"))
    transport = ReviewTransport()
    app = open_trial(transport=transport).application
    preview = app.preview_character_reply(request(options))
    assert preview.status == "previewed" and preview.request_digest == plan.payload["requests"][0]["request_digest"]
    assert app.propose_character_reply(request(options)).code == "review-not-approved"
    assert not transport.calls and not (root / plan.digest).exists()
    assert len(plan.payload["requests"]) == 24


def test_review_exact_24_normal_verdicts_continue_and_replay_or_restart_never_resends(review_trial_fixture):
    root, plan, options, open_trial, _, _ = review_trial_fixture
    transport = ReviewTransport(model="deepseek-flash")
    app = open_trial(approved=plan.digest, transport=transport).application
    results = []
    for i, row in enumerate(plan.payload["requests"]):
        result = app.propose_character_reply(request(options, i))
        assert result.review_verdict == ("supported", "unsupported", "uncertain")[i % 3]
        assert result.status == ("candidate" if i % 3 == 0 else "rejected")
        assert result.reply_text == (row["projection"]["candidate_text"] if i % 3 == 0 else "")
        results.append(result)
        assert app.propose_character_reply(request(options, i)) == result and len(transport.calls) == i + 1
        call = transport.calls[-1]
        assert sha256(call["body"]).hexdigest() == row["outbound_digest"]
        wire = json.loads(call["body"])
        assert wire["model"] == "deepseek-flash" and wire["max_tokens"] == 600
        assert wire["thinking"] == {"type": "disabled"} and wire["temperature"] == 0.0
        assert wire["stream"] is False and wire["response_format"] == {"type": "json_object"}
        assert wire["messages"][0]["content"] == REVIEW_POLICY
        projection = json.loads(wire["messages"][1]["content"])
        assert projection == row["projection"]
        for forbidden in ("case_id", "context_request_digest", "reviewed_digest", "expected", "retain", "hold", "claim_ids",
                          "evidence_ids", "core-self", "sample.epub", "ch.html", "FUTURE_PRIVATE_SECRET", "recent_dialogue"):
            assert forbidden not in wire["messages"][1]["content"]
    assert len(list((root / plan.digest).glob("*.attempt.json"))) == 24
    assert len(list((root / plan.digest).glob("*.result.json"))) == 24
    assert not (root / plan.digest / "stopped.json").exists()
    resumed = open_trial(approved=plan.digest, transport=transport).application
    for i, result in enumerate(results):
        assert resumed.propose_character_reply(request(options, i)) == result
    assert len(transport.calls) == 24


def test_review_approval_changes_extra_cases_and_order_are_zero_call(review_trial_fixture):
    root, plan, options, open_trial, path, _ = review_trial_fixture
    transport = ReviewTransport()
    with pytest.raises(ValueError):
        open_trial(approved="0" * 64, transport=transport)
    changed = json.loads(json.dumps(options["cases"]))
    changed["cases"][0]["candidate_text"] += "改动"
    with pytest.raises(ValueError):
        open_trial(approved=plan.digest, transport=transport, cases=changed)
    with pytest.raises(ValueError):
        open_trial(approved=plan.digest, transport=transport, reviewed_digest="0" * 64)
    assert not (root / plan.digest).exists()
    app = open_trial(approved=plan.digest, transport=transport).application
    assert app.propose_character_reply(request(options, 1)).code == "review-request-out-of-order"
    extra = replace(request(options), case_id="unapproved")
    assert app.propose_character_reply(extra).code == "review-request-not-in-plan"
    altered = replace(request(options), context_request=replace(request(options).context_request, current_message="新问题"))
    assert app.propose_character_reply(altered).code == "review-request-not-in-plan"
    assert not transport.calls


@pytest.mark.parametrize("bad", [dict(failure=TimeoutError("KEY RAW SECRET")), dict(finish="length"),
    dict(reasoning="RAW_REASONING_SECRET"), dict(tools=[{"secret": "RAW_TOOL_SECRET"}]),
    dict(completion=601), dict(model="unapproved-model"),
    dict(value=review_value("unsupported", quote="候选中没有")), dict(value=review_value("unsupported", labels=["F999"]))])
def test_review_transport_or_structure_failure_stops_and_never_retries_or_leaks(review_trial_fixture, bad):
    root, plan, options, open_trial, _, _ = review_trial_fixture
    transport = TrialTransport(**{**bad, "value": bad.get("value", review_value())})
    app = open_trial(approved=plan.digest, transport=transport).application
    result = app.propose_character_reply(request(options))
    assert result.status == "failed-closed" and result.code == "reply-review-failed"
    assert app.propose_character_reply(request(options)) == result
    assert app.propose_character_reply(request(options, 1)).code == "review-stopped"
    audit = "".join(path.read_text(encoding="utf-8") for path in (root / plan.digest).glob("*.json"))
    for forbidden in ("KEY RAW SECRET", "RAW_REASONING_SECRET", "RAW_TOOL_SECRET", "reasoning_content", "headers"):
        assert forbidden not in audit
    resumed = open_trial(approved=plan.digest, transport=transport).application
    assert resumed.propose_character_reply(request(options)) == result
    assert resumed.propose_character_reply(request(options, 1)).status == "unknown"
    assert len(transport.calls) == 1


def test_review_credential_unavailable_claimed_before_resolution_stops_batch(review_trial_fixture):
    from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
    from dynamic_subject_agent.deepseek import DeepSeekCredentialResolver, DeepSeekUrlLibTransport
    root, plan, options, open_trial, _, _ = review_trial_fixture
    class Resolver(DeepSeekCredentialResolver):
        calls = 0
        def resolve(self, credential_ref):
            self.calls += 1
            assert list((root / plan.digest).glob("*.attempt.json"))
            raise CharacterCredentialUnavailable()
    resolver = Resolver()
    transport = DeepSeekUrlLibTransport(credential_resolver=resolver,
        _opener=lambda *a, **kw: pytest.fail("missing key sent request"))
    result = open_trial(approved=plan.digest, transport=transport).application.propose_character_reply(request(options))
    assert result.status == "unavailable" and result.code == "character-credential-unavailable"
    resumed = open_trial(approved=plan.digest, transport=transport).application
    assert resumed.propose_character_reply(request(options)) == result and resolver.calls == 1


def test_review_source_failure_then_repair_remains_stopped_and_second_start_is_exclusive(review_trial_fixture):
    root, plan, options, open_trial, _, book = review_trial_fixture
    transport = ReviewTransport()
    app = open_trial(approved=plan.digest, transport=transport).application
    second = open_trial(approved=plan.digest, transport=transport).application
    assert second.propose_character_reply(request(options)).status == "unknown"
    original = book.read_bytes()
    book.write_bytes(original + b"bad")
    assert app.propose_character_reply(request(options)).status == "failed-closed"
    book.write_bytes(original)
    assert app.propose_character_reply(request(options)).code == "review-stopped" and not transport.calls


@pytest.mark.parametrize("invalid", ["count", "duplicate-id", "duplicate-request", "expected-field"])
def test_review_recipe_rejects_invalid_cases_and_local_expected_labels(review_trial_fixture, invalid):
    root, plan, options, open_trial, _, _ = review_trial_fixture
    cases = json.loads(json.dumps(options["cases"]))
    if invalid == "count": cases["cases"].pop()
    elif invalid == "duplicate-id": cases["cases"][1]["id"] = cases["cases"][0]["id"]
    elif invalid == "duplicate-request": cases["cases"][1] = {**cases["cases"][0], "id": "unique"}
    else: cases["cases"][0]["expected"] = "hold"
    transport = ReviewTransport()
    with pytest.raises(ValueError):
        open_trial(approved=plan.digest, transport=transport, cases=cases)
    assert not transport.calls and not (root / plan.digest).exists()


def test_review_missing_or_corrupt_audit_is_unknown_without_resend(review_trial_fixture):
    root, plan, options, open_trial, _, _ = review_trial_fixture
    transport = ReviewTransport()
    app = open_trial(approved=plan.digest, transport=transport).application
    app.propose_character_reply(request(options))
    path = root / plan.digest / (plan.payload["requests"][0]["request_digest"] + ".result.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    value["reply_text"] = "corrupted"
    path.write_text(json.dumps(value), encoding="utf-8")
    resumed = open_trial(approved=plan.digest, transport=transport).application
    assert resumed.propose_character_reply(request(options)).status == "unknown"
    assert resumed.propose_character_reply(request(options, 1)).status == "unknown" and len(transport.calls) == 1


@pytest.mark.parametrize("method,code,calls", [
    ("claim", "review-attempt-record-unavailable", 0),
    ("record", "review-result-record-unavailable", 1),
])
def test_review_audit_fault_stops_and_restart_cannot_send_again(review_trial_fixture, monkeypatch, method, code, calls):
    from dynamic_subject_agent.frozen_attempt import FrozenAttemptRun
    _, plan, options, open_trial, _, _ = review_trial_fixture
    transport = ReviewTransport()
    app = open_trial(approved=plan.digest, transport=transport).application
    def fail(*args):
        raise OSError("RAW AUDIT SECRET")
    monkeypatch.setattr(FrozenAttemptRun, method, fail)
    result = app.propose_character_reply(request(options))
    assert result.status == "unknown" and result.code == code and not result.reply_text
    assert "RAW AUDIT" not in str(result)
    assert app.propose_character_reply(request(options, 1)).code == "review-stopped"
    resumed = open_trial(approved=plan.digest, transport=transport).application
    assert resumed.propose_character_reply(request(options)).status == "unknown"
    assert len(transport.calls) == calls


def test_review_adapter_disallows_generation_or_unfrozen_wire_and_budget(review_trial_fixture):
    from dynamic_subject_agent.character_reply_review_provider import DeepSeekCharacterReplyReviewAdapter
    from dynamic_subject_agent.character_reply_review import ReviewKnowledge
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.model_gateway import ModelTask
    _, plan, options, open_trial, _, _ = review_trial_fixture
    projection = open_trial().application.preview_character_reply(request(options)).projection
    transport = ReviewTransport()
    adapter = DeepSeekCharacterReplyReviewAdapter(transport=transport, credential_ref=CredentialRef.reference(backend_id="test", key_id="test"),
                                                 allowed_outbound_digests=["0" * 64])
    with pytest.raises(ValueError): adapter.invoke(ModelTask(ModelTaskKind.CHARACTER_CONTEXT_REPLY, projection))
    with pytest.raises(ValueError): adapter.invoke(ModelTask(ModelTaskKind.CHARACTER_REPLY_REVIEW, projection))
    large = replace(projection, self_knowledge=tuple(ReviewKnowledge(f"F{i}", "core", "画" * 4750,
        "fact", "linked-evidence", "start", "start") for i in range(1, 5)), current_message="问" * 1000,
        candidate_text="画" * 1200, stage_description="段" * 500)
    with pytest.raises(ValueError, match="review-(outbound|input)-too-large"):
        adapter.outbound_bytes(large)
    assert not transport.calls


def test_review_cli_default_prepares_without_starting_or_printing_cases(review_trial_fixture, tmp_path):
    _, _, options, _, path, _ = review_trial_fixture
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps(options["cases"], ensure_ascii=False), encoding="utf-8")
    cli = Path(__file__).resolve().parents[1] / "app/desktop/character_reply_review_trial.py"
    completed = subprocess.run([sys.executable, str(cli), "--draft", str(path), "--source-root", str(options["source_root"]),
        "--reviewed-digest", options["reviewed_digest"], "--subject", "self", "--anchor", "start", "--cases", str(cases_path)],
        capture_output=True, check=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    summary = json.loads(completed.stdout)
    assert summary["status"] == "prepared" and summary["request_count"] == 24
    assert "冻结的候选" not in completed.stdout and "projection" not in summary
    saved = json.loads(Path(summary["plan_path"]).read_text(encoding="utf-8"))
    assert saved["digest"] == summary["digest"] and saved["plan"]["version"] == "character-reply-review-trial-1"
    assert not (Path(summary["plan_path"]).parent / summary["digest"]).exists()
