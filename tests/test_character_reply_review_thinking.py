from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from dynamic_subject_agent.character_reply_review import REVIEW_POLICY
from dynamic_subject_agent.character_reply_review_provider import DeepSeekCharacterReplyReviewAdapter
from dynamic_subject_agent.cognition import CredentialRef, ProviderFailure
from dynamic_subject_agent.deepseek import _post_json_reply_content
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.local_product import prepare_character_reply_review_trial
from test_character_context_trial import TrialTransport
from test_character_evidence_model import model_fixture
from test_character_reply_review import review_trial_fixture, request, review_value, ReviewTransport


@pytest.fixture
def thinking_fixture(review_trial_fixture):
    root, standard, options, open_trial, path, book = review_trial_fixture
    thinking_options = {**options, "cases": {**options["cases"], "cases": options["cases"]["cases"][:8]},
                        "review_profile": "thinking-high"}
    plan = prepare_character_reply_review_trial(root, **thinking_options)
    def open_thinking(*, approved=None, transport=None, **overrides):
        return open_trial(approved=approved, transport=transport, **{**thinking_options, **overrides})
    return root, plan, standard, thinking_options, open_thinking, path


def test_thinking_profile_freezes_only_eight_same_inputs_and_default_plan_wire_are_unchanged(thinking_fixture):
    root, plan, standard, options, open_thinking, _ = thinking_fixture
    assert plan.payload["review_profile"] == "thinking-high" and len(plan.payload["requests"]) == 8
    assert plan.payload["generation"] == dict(max_tokens=4096, thinking={"type": "enabled"},
        reasoning_effort="high", response_format={"type": "json_object"}, stream=False)
    assert plan.digest != standard.digest and "review_profile" not in standard.payload
    assert standard.payload["generation"] == dict(max_tokens=600, temperature=0.0, thinking={"type": "disabled"},
        response_format={"type": "json_object"}, stream=False)
    app = open_thinking().application
    for new, old in zip(plan.payload["requests"], standard.payload["requests"]):
        assert {key: value for key, value in new.items() if key != "outbound_digest"} == {
            key: value for key, value in old.items() if key != "outbound_digest"}
        projection = app.preview_character_reply(request(options, plan.payload["requests"].index(new))).projection
        old_body = dict(model="deepseek-flash", messages=[dict(role="system", content=REVIEW_POLICY),
            dict(role="user", content=canonical_json(asdict(projection)))], thinking={"type": "disabled"},
            response_format={"type": "json_object"}, max_tokens=600, temperature=0.0, stream=False)
        assert DeepSeekCharacterReplyReviewAdapter.outbound_bytes(projection) == canonical_json(old_body).encode()
        assert sha256(canonical_json(old_body).encode()).hexdigest() == old["outbound_digest"]
    default_cases = {**options["cases"], "cases": standard.payload["cases"]}
    explicit = prepare_character_reply_review_trial(root, **{**options, "cases": default_cases, "review_profile": "standard"})
    assert explicit.serialized == standard.serialized


def test_thinking_unapproved_and_old_approval_or_wrong_count_are_zero_calls(thinking_fixture, monkeypatch):
    from dynamic_subject_agent.model_gateway import ModelGateway
    root, plan, standard, options, open_thinking, _ = thinking_fixture
    transport = ReviewTransport()
    monkeypatch.setattr(ModelGateway, "execute", lambda *a: pytest.fail("unapproved gateway called"))
    app = open_thinking(transport=transport).application
    assert app.propose_character_reply(request(options)).code == "review-not-approved"
    with pytest.raises(ValueError): open_thinking(approved=standard.digest, transport=transport)
    with pytest.raises(ValueError): open_thinking(approved=plan.digest, transport=transport, review_profile="standard")
    with pytest.raises(ValueError): open_thinking(transport=transport, review_profile="thinking-medium")
    with pytest.raises(ValueError): open_thinking(transport=transport, cases={**options["cases"], "cases": standard.payload["cases"]})
    assert not transport.calls and not (root / plan.digest).exists()


def test_thinking_eight_exact_requests_discard_reasoning_and_replay_never_resends(thinking_fixture):
    root, plan, _, options, open_thinking, _ = thinking_fixture
    secret = "PRIVATE_REASONING_NOT_EVIDENCE"
    transport = ReviewTransport(reasoning=secret, completion=4096)
    app = open_thinking(approved=plan.digest, transport=transport).application
    results = []
    for i, row in enumerate(plan.payload["requests"]):
        result = app.propose_character_reply(request(options, i))
        results.append(result)
        assert result.review_verdict in ("supported", "unsupported", "uncertain")
        assert secret not in str(asdict(result))
        assert app.propose_character_reply(request(options, i)) == result
        assert len(transport.calls) == i + 1
        wire = json.loads(transport.calls[-1]["body"])
        assert set(wire) == {"model", "messages", "thinking", "reasoning_effort", "response_format", "max_tokens", "stream"}
        assert wire["max_tokens"] == 4096 and wire["thinking"] == {"type": "enabled"}
        assert wire["reasoning_effort"] == "high" and wire["stream"] is False
        assert wire["response_format"] == {"type": "json_object"}
        assert json.loads(wire["messages"][1]["content"]) == row["projection"]
        assert sha256(transport.calls[-1]["body"]).hexdigest() == row["outbound_digest"]
    audit = "".join(path.read_text(encoding="utf-8") for path in (root / plan.digest).glob("*.json"))
    assert secret not in audit and "reasoning_content" not in audit
    resumed = open_thinking(approved=plan.digest, transport=transport).application
    for i, result in enumerate(results):
        assert resumed.propose_character_reply(request(options, i)) == result
    assert len(transport.calls) == 8


@pytest.mark.parametrize("bad", [dict(reasoning={"SECRET": "RAW_REASONING"}), dict(reasoning=19),
    dict(reasoning="RAW_REASONING" * 6000), dict(finish="length"), dict(completion=4097),
    dict(completion="40"), dict(completion=True), dict(completion=-1),
    dict(tools=[{"secret": "RAW_TOOL"}]), dict(value={"verdict": "supported", "issues": [{}]}),
    dict(failure=TimeoutError("SECRET_TIMEOUT")), dict(model="unapproved-model")])
def test_thinking_malformed_truncated_or_total_completion_excess_stops_without_raw_audit(thinking_fixture, bad):
    root, plan, _, options, open_thinking, _ = thinking_fixture
    transport = TrialTransport(**{**bad, "value": bad.get("value", review_value())})
    app = open_thinking(approved=plan.digest, transport=transport).application
    result = app.propose_character_reply(request(options))
    assert result.status == "failed-closed" and result.code == "reply-review-failed" and not result.reply_text
    assert app.propose_character_reply(request(options)) == result
    assert app.propose_character_reply(request(options, 1)).code == "review-stopped"
    audit = "".join(path.read_text(encoding="utf-8") for path in (root / plan.digest).glob("*.json"))
    for forbidden in ("RAW_REASONING", "RAW_TOOL", "SECRET_TIMEOUT", "reasoning_content"):
        assert forbidden not in audit
    resumed = open_thinking(approved=plan.digest, transport=transport).application
    assert resumed.propose_character_reply(request(options)) == result
    assert len(transport.calls) == 1


@pytest.mark.parametrize("tokens,discard", [(4096, False), (4097, True), (True, True), (600, "yes"), (600, 1)])
def test_response_helper_budget_and_discard_switch_validate_before_delivery(tokens, discard):
    transport = TrialTransport(value=review_value(), reasoning="SECRET")
    credential = CredentialRef.reference(backend_id="test", key_id="test")
    with pytest.raises(ProviderFailure):
        _post_json_reply_content(transport, credential, b"{}", max_output_tokens=tokens, discard_reasoning=discard)
    assert not transport.calls


def test_standard_helper_still_rejects_reasoning_and_over_2048_without_explicit_opt_in():
    credential = CredentialRef.reference(backend_id="test", key_id="test")
    transport = TrialTransport(value=review_value(), reasoning="SECRET")
    with pytest.raises(ProviderFailure):
        _post_json_reply_content(transport, credential, b"{}", max_output_tokens=600, require_complete=True)
    assert len(transport.calls) == 1
    transport = TrialTransport(value=review_value(), completion=2048)
    assert _post_json_reply_content(transport, credential, b"{}", max_output_tokens=2048) == review_value()


def test_thinking_cli_prepares_eight_only_and_never_prints_candidate_or_starts(thinking_fixture, tmp_path):
    _, plan, _, options, _, path = thinking_fixture
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps(options["cases"], ensure_ascii=False), encoding="utf-8")
    cli = Path(__file__).resolve().parents[1] / "app/desktop/character_reply_review_trial.py"
    completed = subprocess.run([sys.executable, str(cli), "--draft", str(path), "--source-root", str(options["source_root"]),
        "--reviewed-digest", options["reviewed_digest"], "--subject", "self", "--anchor", "start", "--cases", str(cases_path),
        "--review-profile", "thinking-high"], capture_output=True, check=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    summary = json.loads(completed.stdout)
    assert summary["request_count"] == 8 and summary["digest"] == plan.digest
    assert "冻结的候选" not in completed.stdout and "projection" not in summary
    assert not (Path(summary["plan_path"]).parent / summary["digest"]).exists()
