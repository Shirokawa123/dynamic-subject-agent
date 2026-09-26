import json
from pathlib import Path
import os
import subprocess
import sys

import pytest

from dynamic_subject_agent.deepseek import DeepSeekHttpResponse
from dynamic_subject_agent.local_product import prepare_character_reply_review_trial, open_character_reply_review_trial
from dynamic_subject_agent.reply_review_diagnostics import REVIEW_DIAGNOSTIC_CODES
from test_character_context_trial import TrialTransport
from test_character_reply_review import request, review_value
from test_character_reply_review_thinking import thinking_fixture
from test_character_reply_review import review_trial_fixture
from test_character_evidence_model import model_fixture


class DiagnosticTransport(TrialTransport):
    def __init__(self, *, fault=None):
        super().__init__(value=review_value())
        self.fault = fault

    def post_json(self, **kwargs):
        self.calls.append(kwargs)
        if self.fault == "network":
            raise ConnectionError("RAW_NETWORK_SECRET")
        if self.fault == "timeout":
            raise TimeoutError("RAW_TIMEOUT_SECRET")
        payload = dict(model="deepseek-flash", choices=[dict(finish_reason="stop", message=dict(
            role="assistant", content=json.dumps(review_value()), reasoning_content="RAW_REASONING_SECRET"))],
            usage=dict(prompt_tokens=80, completion_tokens=40))
        if self.fault == "length-empty":
            payload["choices"][0]["finish_reason"] = "length"
            payload["choices"][0]["message"]["content"] = ""
        if isinstance(self.fault, int):
            return DeepSeekHttpResponse(self.fault, b"RAW_HTTP_SECRET")
        if self.fault == "size":
            return DeepSeekHttpResponse(200, b"RAW_SIZE_SECRET" * 6000)
        if self.fault == "envelope":
            return DeepSeekHttpResponse(200, b"RAW_ENVELOPE_SECRET")
        if self.fault == "model": payload["model"] = "RAW_MODEL_SECRET"
        if self.fault == "reasoning": payload["choices"][0]["message"]["reasoning_content"] = {"secret": "RAW_REASONING_SECRET"}
        if self.fault == "usage": payload["usage"]["completion_tokens"] = True
        if self.fault == "budget": payload["usage"]["completion_tokens"] = 4097
        if self.fault == "content": payload["choices"][0]["message"]["content"] = "RAW_CONTENT_SECRET"
        if self.fault == "tools": payload["choices"][0]["message"]["tool_calls"] = [{"secret": "RAW_TOOL_SECRET"}]
        if self.fault == "finish": payload["choices"][0]["finish_reason"] = "content_filter"
        if self.fault == "schema": payload["choices"][0]["message"]["content"] = json.dumps({"secret": "RAW_SCHEMA_SECRET"})
        if self.fault == "quote": payload["choices"][0]["message"]["content"] = json.dumps(review_value("unsupported", quote="RAW_QUOTE_SECRET"))
        if self.fault == "label": payload["choices"][0]["message"]["content"] = json.dumps(review_value("unsupported", quote="候选", labels=["RAW_LABEL_SECRET"]))
        if self.fault == "unsupported": payload["choices"][0]["message"]["content"] = json.dumps(review_value("unsupported", quote="候选"))
        if self.fault == "uncertain": payload["choices"][0]["message"]["content"] = json.dumps(review_value("uncertain"))
        return DeepSeekHttpResponse(200, json.dumps(payload).encode())


@pytest.fixture
def diagnostic_fixture(thinking_fixture):
    root, thinking_plan, _, thinking_options, _, path = thinking_fixture
    options = {**thinking_options, "review_profile": "thinking-diagnostic",
               "cases": {**thinking_options["cases"], "cases": thinking_options["cases"]["cases"][:1]}}
    plan = prepare_character_reply_review_trial(root, **options)
    opened = []
    def open_diagnostic(*, approved=None, transport=None, run_root=None, **overrides):
        product = open_character_reply_review_trial(run_root or root, **{**options, **overrides},
            approved_plan=approved, _transport=transport)
        opened.append(product)
        return product
    yield root, plan, thinking_plan, options, open_diagnostic, path
    for product in opened:
        product.close()


@pytest.mark.parametrize("fault,expected", [("network", "transport-network"), ("length-empty", "response-truncated")])
def test_full_facade_distinguishes_masked_network_and_length_empty(diagnostic_fixture, fault, expected):
    _, plan, _, options, open_diagnostic, _ = diagnostic_fixture
    transport = DiagnosticTransport(fault=fault)
    result = open_diagnostic(approved=plan.digest, transport=transport).application.propose_character_reply(request(options))
    assert result.status == "failed-closed" and result.code == expected


def test_explicit_diagnostic_closed_categories_survive_facade_audit_and_restart_without_raw_text(diagnostic_fixture):
    root, plan, _, options, open_diagnostic, _ = diagnostic_fixture
    faults = [("timeout", "transport-timeout"), (401, "http-401"), (429, "http-429"), (503, "http-503"),
        (418, "http-other"), ("envelope", "response-envelope"), ("model", "response-model"),
        ("reasoning", "response-reasoning"), ("usage", "response-usage"), ("budget", "response-overbudget"),
        ("content", "response-content-json"), ("tools", "response-tools"), ("finish", "response-incomplete"),
        ("size", "response-size"), ("schema", "review-schema"), ("quote", "review-quote"), ("label", "review-label")]
    for i, (fault, expected) in enumerate(faults):
        run_root = root / f"isolated-{i}"
        transport = DiagnosticTransport(fault=fault)
        app = open_diagnostic(approved=plan.digest, transport=transport, run_root=run_root).application
        result = app.propose_character_reply(request(options))
        assert result.status == "failed-closed" and result.code == expected and expected in REVIEW_DIAGNOSTIC_CODES
        assert not result.reply_text and not result.review_verdict and not result.review_issues
        assert app.propose_character_reply(request(options)) == result and len(transport.calls) == 1
        assert (run_root / plan.digest / "stopped.json").exists()
        audit = "".join(path.read_text(encoding="utf-8") for path in (run_root / plan.digest).glob("*.json"))
        assert "RAW_" not in audit and "reasoning_content" not in audit and "headers" not in audit
        resumed = open_diagnostic(approved=plan.digest, transport=transport, run_root=run_root).application
        assert resumed.propose_character_reply(request(options)) == result and len(transport.calls) == 1


def test_diagnostic_input_and_body_match_thinking_but_new_plan_and_approval_are_one_case(diagnostic_fixture, monkeypatch):
    from dynamic_subject_agent.model_gateway import ModelGateway
    root, plan, thinking, options, open_diagnostic, _ = diagnostic_fixture
    monkeypatch.setattr(ModelGateway, "execute", lambda *a: pytest.fail("unapproved invoked gateway"))
    assert plan.payload["generation"] == thinking.payload["generation"]
    assert plan.payload["requests"][0] == thinking.payload["requests"][0]
    assert plan.payload["review_profile"] == "thinking-diagnostic" and plan.payload["safe_diagnostics"] is True
    assert len(plan.payload["requests"]) == 1 and plan.digest != thinking.digest
    transport = DiagnosticTransport()
    app = open_diagnostic(transport=transport).application
    assert app.propose_character_reply(request(options)).code == "review-not-approved"
    with pytest.raises(ValueError): open_diagnostic(approved=thinking.digest, transport=transport)
    with pytest.raises(ValueError): open_diagnostic(approved=plan.digest, transport=transport,
        cases={**options["cases"], "cases": thinking.payload["cases"]})
    assert not transport.calls and not (root / plan.digest).exists()


@pytest.mark.parametrize("verdict", ["supported", "unsupported", "uncertain"])
def test_normal_diagnostic_review_verdict_is_not_a_technical_failure(diagnostic_fixture, verdict):
    root, plan, _, options, open_diagnostic, _ = diagnostic_fixture
    transport = DiagnosticTransport(fault=None if verdict == "supported" else verdict)
    result = open_diagnostic(approved=plan.digest, transport=transport).application.propose_character_reply(request(options))
    assert result.review_verdict == verdict
    assert result.status == ("candidate" if verdict == "supported" else "rejected")
    assert not (root / plan.digest / "stopped.json").exists()
    assert "RAW_" not in str(result)


def test_default_thinking_errors_still_use_old_generic_code(thinking_fixture):
    root, plan, _, options, _, _ = thinking_fixture
    for i, fault in enumerate(("network", "length-empty")):
        transport = DiagnosticTransport(fault=fault)
        with open_character_reply_review_trial(root / f"legacy-{i}", **options, approved_plan=plan.digest, _transport=transport) as product:
            result = product.application.propose_character_reply(request(options))
            assert result.status == "failed-closed" and result.code == "reply-review-failed"


def test_cache_accepts_only_mode_specific_closed_codes_and_untrusted_gateway_codes_fail_closed(diagnostic_fixture):
    from dynamic_subject_agent.character_reply_review import review_candidate
    from dynamic_subject_agent.model_gateway import ModelGateway, ModelGatewayFailure
    from test_character_reply_review import LocalReviewAdapter
    root, plan, thinking, options, open_diagnostic, _ = diagnostic_fixture
    transport = DiagnosticTransport(fault="network")
    app = open_diagnostic(approved=plan.digest, transport=transport).application
    app.propose_character_reply(request(options))
    result_path = root / plan.digest / (plan.payload["requests"][0]["request_digest"] + ".result.json")
    audit = json.loads(result_path.read_text(encoding="utf-8"))
    audit["code"] = "RAW_UNTRUSTED_EXCEPTION"
    result_path.write_text(json.dumps(audit), encoding="utf-8")
    assert open_diagnostic(approved=plan.digest, transport=transport).application.propose_character_reply(request(options)).status == "unknown"
    assert len(transport.calls) == 1
    projection = app.preview_character_reply(request(options)).projection
    reviewer = ModelGateway(LocalReviewAdapter(failure=ModelGatewayFailure("RAW_UNTRUSTED_EXCEPTION")))
    result = review_candidate(reviewer, projection, request_digest="local", safe_diagnostics=True)
    assert result.code == "reply-review-failed" and "RAW_" not in str(result)
    legacy_root = root / "legacy-cache"
    legacy_options = {**options, "review_profile": "thinking-high", "cases": {**options["cases"], "cases": thinking.payload["cases"]}}
    with open_character_reply_review_trial(legacy_root, **legacy_options, approved_plan=thinking.digest,
                                           _transport=DiagnosticTransport(fault="network")) as product:
        assert product.application.propose_character_reply(request(legacy_options)).code == "reply-review-failed"
    legacy_path = legacy_root / thinking.digest / (thinking.payload["requests"][0]["request_digest"] + ".result.json")
    legacy_audit = json.loads(legacy_path.read_text(encoding="utf-8"))
    legacy_audit["code"] = "transport-network"
    legacy_path.write_text(json.dumps(legacy_audit), encoding="utf-8")
    with open_character_reply_review_trial(legacy_root, **legacy_options, approved_plan=thinking.digest) as product:
        assert product.application.propose_character_reply(request(legacy_options)).status == "unknown"


def test_diagnostic_credential_unavailable_stays_typed_unavailable(diagnostic_fixture):
    from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
    _, plan, _, options, open_diagnostic, _ = diagnostic_fixture
    transport = TrialTransport(failure=CharacterCredentialUnavailable())
    result = open_diagnostic(approved=plan.digest, transport=transport).application.propose_character_reply(request(options))
    assert result.status == "unavailable" and result.code == "character-credential-unavailable"


def test_production_transport_oversize_body_retains_diagnostic_but_default_semantics(diagnostic_fixture):
    from dynamic_subject_agent.deepseek import DeepSeekUrlLibTransport
    from test_deepseek_cognition_provider import _DummyCredentialResolver
    root, plan, thinking, options, open_diagnostic, _ = diagnostic_fixture
    calls = []
    class OversizedResponse:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, amount):
            assert amount == 65537
            return b"x" * 65537
    def opener(http_request, *, timeout):
        assert timeout == 30
        calls.append("opened")
        return OversizedResponse()
    resolver = _DummyCredentialResolver()
    transport = DeepSeekUrlLibTransport(credential_resolver=resolver, _opener=opener)
    result = open_diagnostic(approved=plan.digest, transport=transport).application.propose_character_reply(request(options))
    assert result.status == "failed-closed" and result.code == "response-size"
    assert len(calls) == len(resolver.references) == 1
    assert open_diagnostic(approved=plan.digest, transport=transport).application.propose_character_reply(request(options)) == result
    assert len(calls) == 1
    audit = "".join(path.read_text(encoding="utf-8") for path in (root / plan.digest).glob("*.json"))
    assert "test-only-deepseek-secret" not in audit and "Authorization" not in audit
    legacy_options = {**options, "review_profile": "thinking-high", "cases": {**options["cases"], "cases": thinking.payload["cases"]}}
    with open_character_reply_review_trial(root / "default-oversize", **legacy_options,
        approved_plan=thinking.digest, _transport=transport) as product:
        assert product.application.propose_character_reply(request(legacy_options)).code == "reply-review-failed"
    assert len(calls) == 2


def test_diagnostic_cli_prepares_one_without_body_or_network(diagnostic_fixture, tmp_path):
    _, plan, _, options, _, path = diagnostic_fixture
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps(options["cases"]), encoding="utf-8")
    cli = Path(__file__).resolve().parents[1] / "app/desktop/character_reply_review_trial.py"
    completed = subprocess.run([sys.executable, str(cli), "--draft", str(path), "--source-root", str(options["source_root"]),
        "--reviewed-digest", options["reviewed_digest"], "--subject", "self", "--anchor", "start", "--cases", str(cases_path),
        "--review-profile", "thinking-diagnostic"], capture_output=True, check=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    summary = json.loads(completed.stdout)
    assert summary["digest"] == plan.digest and summary["request_count"] == 1
    assert "冻结的候选" not in completed.stdout and "projection" not in summary
    assert not (Path(summary["plan_path"]).parent / summary["digest"]).exists()
