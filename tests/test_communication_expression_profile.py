from hashlib import sha256
import json

import pytest

from dynamic_subject_agent.character_communication_trial import stage_digest
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.local_product import prepare_character_communication_trial, prepare_character_expression_thinking_trial
from test_character_evidence_model import model_fixture
from test_character_communication_plan import communication_fixture
from test_character_communication_trial import communication_trial_fixture, CommunicationTransport, request


@pytest.fixture
def high_expression_fixture(communication_trial_fixture):
    root, standard, options, open_trial, book = communication_trial_fixture
    high_options = {**options, "expression_profile": "thinking-high"}
    plan = prepare_character_communication_trial(root, **high_options)
    def open_high(*, approved=None, transport=None, **overrides):
        return open_trial(approved=approved, transport=transport, **{"expression_profile": "thinking-high", **overrides})
    return root, plan, standard, options, open_high, book


class HighExpressionTransport(CommunicationTransport):
    def post_json(self, **kwargs):
        response = super().post_json(**kwargs)
        body = json.loads(kwargs["body"])
        if "selected_facts" in json.loads(body["messages"][1]["content"]):
            payload = json.loads(response.body)
            payload["choices"][0]["message"]["reasoning_content"] = "HIGH_EXPRESSION_REASONING_SECRET"
            if self.fault == "budget": payload["usage"]["completion_tokens"] = 4097
            elif self.fault == "boundary": payload["usage"]["completion_tokens"] = 4096
            return type(response)(response.status_code, json.dumps(payload).encode())
        return response


def test_default_protocol_and_plan_stay_exact_while_high_is_separately_bound(high_expression_fixture, monkeypatch):
    from dynamic_subject_agent.model_gateway import ModelGateway
    root, high, standard, options, open_high, _ = high_expression_fixture
    explicit = prepare_character_communication_trial(root, **options, expression_profile="standard")
    assert explicit.serialized == standard.serialized and "expression_profile" not in standard.payload
    assert high.payload["expression_profile"] == "thinking-high" and high.digest != standard.digest
    assert high.payload["requests"] == standard.payload["requests"]
    assert high.payload["protocol"]["planning"] == standard.payload["protocol"]["planning"]
    assert high.payload["protocol"]["expression"] == dict(max_tokens=4096, thinking={"type": "enabled"}, reasoning_effort="high",
        response_format={"type": "json_object"}, stream=False)
    monkeypatch.setattr(ModelGateway, "execute", lambda *a: pytest.fail("unapproved high trial called gateway"))
    transport = HighExpressionTransport()
    assert open_high(transport=transport).application.propose_character_reply(request(options)).code == "communication-trial-not-approved"
    with pytest.raises(ValueError): open_high(approved=standard.digest, transport=transport)
    with pytest.raises(ValueError): open_high(approved=high.digest, transport=transport, expression_profile="standard")
    assert not transport.calls and not (root / high.digest).exists()


def test_high_expression_all_six_full_paths_use_matching_derived_wire_and_cache_without_reasoning(high_expression_fixture):
    root, plan, _, options, open_high, _ = high_expression_fixture
    transport = HighExpressionTransport(phase="expression", fault="boundary")
    app = open_high(approved=plan.digest, transport=transport).application
    results = []
    for i, row in enumerate(plan.payload["requests"]):
        result = app.propose_character_reply(request(options, i)); results.append(result)
        assert result.status == "candidate" and result.semantic_review == "required" and not result.persisted
        assert app.propose_character_reply(request(options, i)) == result and len(transport.calls) == 2 * (i + 1)
        planning, expression = [json.loads(call["body"]) for call in transport.calls[-2:]]
        assert sha256(transport.calls[-2]["body"]).hexdigest() == row["outbound_digest"]
        for body in (planning, expression):
            assert body["max_tokens"] == 4096 and body["thinking"] == {"type": "enabled"} and body["reasoning_effort"] == "high"
            assert "temperature" not in body and body["stream"] is False and "tools" not in body
        derived = json.loads((root / plan.digest / (stage_digest(row, "expression") + ".request.json")).read_text(encoding="utf-8"))
        assert sha256(transport.calls[-1]["body"]).hexdigest() == derived["outbound_digest"]
        assert json.loads(expression["messages"][1]["content"]) == derived["projection"]
        legacy = dict(expression, max_tokens=600, thinking={"type": "disabled"}, temperature=0.3)
        del legacy["reasoning_effort"]
        assert sha256(canonical_json(legacy).encode()).hexdigest() != derived["outbound_digest"]
    audit = "".join(path.read_text(encoding="utf-8") for path in (root / plan.digest).glob("*.json"))
    assert "HIGH_EXPRESSION_REASONING_SECRET" not in audit and "RAW_REASONING_SECRET" not in audit
    resumed = open_high(approved=plan.digest, transport=transport).application
    for i, result in enumerate(results): assert resumed.propose_character_reply(request(options, i)) == result
    assert len(transport.calls) == 12


@pytest.mark.parametrize("fault,code", [("length", "response-truncated"), ("budget", "response-overbudget")])
def test_high_expression_truncated_or_combined_budget_excess_stops_and_never_resends(high_expression_fixture, fault, code):
    _, plan, _, options, open_high, _ = high_expression_fixture
    transport = HighExpressionTransport(phase="expression", fault=fault)
    app = open_high(approved=plan.digest, transport=transport).application
    result = app.propose_character_reply(request(options))
    assert result.status == "failed-closed" and result.code == code and not result.reply_text
    assert app.propose_character_reply(request(options, 1)).code == "communication-trial-stopped"
    assert open_high(approved=plan.digest, transport=transport).application.propose_character_reply(request(options)) == result
    assert len(transport.calls) == 2


def test_s94_refuses_high_parent_instead_of_preparing_identical_configuration(high_expression_fixture):
    root, plan, _, options, open_high, _ = high_expression_fixture
    app = open_high(approved=plan.digest, transport=HighExpressionTransport()).application
    for i in range(6): assert app.propose_character_reply(request(options, i)).status == "candidate"
    with pytest.raises(ValueError, match="only original non-thinking expression parent"):
        prepare_character_expression_thinking_trial(root / "unsupported-comparison", parent_trial_root=root, parent_plan_digest=plan.digest,
            draft_path=options["draft_path"], source_root=options["source_root"])
