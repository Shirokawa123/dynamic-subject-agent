from hashlib import sha256
import json

import pytest

from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.local_product import (
    prepare_character_communication_trial, open_character_communication_trial,
    prepare_character_personality_trial, open_character_personality_trial,
)
from test_character_evidence_model import model_fixture
from test_character_communication_plan import communication_fixture
from test_character_communication_trial import communication_trial_fixture, request as context_request
from test_communication_expression_profile import high_expression_fixture, HighExpressionTransport
from test_character_personality import personality_fixture
from test_character_personality_trial import personality_trial_fixture, PersonalityTransport


@pytest.fixture(params=["baseline", "personality"])
def effort_fixture(request):
    if request.param == "baseline":
        root, high, _, options, _, _ = request.getfixturevalue("high_expression_fixture")
        options = {**options, "expression_profile": "thinking-high"}
        prepare, open_trial, transport = prepare_character_communication_trial, open_character_communication_trial, HighExpressionTransport
    else:
        root, high, options, _ = request.getfixturevalue("personality_trial_fixture")
        prepare, open_trial, transport = prepare_character_personality_trial, open_character_personality_trial, PersonalityTransport
    low = prepare(root, **options, planning_effort="low")
    return root, high, low, options, prepare, open_trial, transport


def test_explicit_low_has_new_approval_but_high_default_plan_stays_exact(effort_fixture, monkeypatch):
    from dynamic_subject_agent.model_gateway import ModelGateway
    root, high, low, options, prepare, open_trial, Transport = effort_fixture
    assert prepare(root, **options, planning_effort="high").serialized == high.serialized
    assert "planning_effort" not in high.payload and low.payload["planning_effort"] == "low" and low.digest != high.digest
    assert low.payload["protocol"]["expression"] == high.payload["protocol"]["expression"]
    assert low.payload["protocol"]["planning"] == {**high.payload["protocol"]["planning"], "reasoning_effort": "low"}
    assert all({key: value for key, value in new.items() if key != "outbound_digest"} ==
               {key: value for key, value in old.items() if key != "outbound_digest"} for new, old in zip(low.payload["requests"], high.payload["requests"]))
    monkeypatch.setattr(ModelGateway, "execute", lambda *a: pytest.fail("unapproved low request"))
    transport = Transport()
    with open_trial(root, **options, planning_effort="low", _transport=transport) as product:
        assert product.application.propose_character_reply(context_request(options)).code == "communication-trial-not-approved"
    with pytest.raises(ValueError): open_trial(root, **options, planning_effort="low", approved_plan=high.digest, _transport=transport)
    for invalid in ("medium", "max", "xhigh", None):
        with pytest.raises(ValueError): prepare(root, **options, planning_effort=invalid)
    assert not transport.calls and not (root / low.digest).exists()


def test_actual_low_planner_high_expression_and_restart_keep_exact_expression_bytes(effort_fixture):
    root, high, low, options, _, open_trial, Transport = effort_fixture
    transport = Transport()
    with open_trial(root, **options, planning_effort="low", approved_plan=low.digest, _transport=transport) as product:
        results = []
        for i, row in enumerate(low.payload["requests"]):
            result = product.application.propose_character_reply(context_request(options, i)); results.append(result)
            assert result.status == "candidate" and result.semantic_review == "required" and not result.persisted
            planning, expression = [json.loads(call["body"]) for call in transport.calls[-2:]]
            assert planning["reasoning_effort"] == "low" and expression["reasoning_effort"] == "high"
            assert planning["max_tokens"] == expression["max_tokens"] == 4096
            assert "temperature" not in planning and "temperature" not in expression
            old_planning = dict(planning, reasoning_effort="high")
            assert sha256(canonical_json(old_planning).encode()).hexdigest() == high.payload["requests"][i]["outbound_digest"]
            assert sha256(transport.calls[-2]["body"]).hexdigest() == row["outbound_digest"]
            assert product.application.propose_character_reply(context_request(options, i)) == result
        assert len(transport.calls) == 12
    with open_trial(root, **options, planning_effort="low", approved_plan=low.digest, _transport=transport) as resumed:
        for i, result in enumerate(results): assert resumed.application.propose_character_reply(context_request(options, i)) == result
    assert len(transport.calls) == 12


def test_low_still_stops_on_expression_timeout_and_never_resends(effort_fixture):
    root, _, low, options, _, open_trial, Transport = effort_fixture
    if Transport is PersonalityTransport:
        transport = Transport(fault="timeout", stage="expression")
    else:
        class TimeoutExpression(Transport):
            def post_json(self, **kwargs):
                body = json.loads(kwargs["body"])
                if "selected_facts" in json.loads(body["messages"][1]["content"]):
                    self.calls.append(kwargs); raise TimeoutError("synthetic timeout")
                return super().post_json(**kwargs)
        transport = TimeoutExpression()
    with open_trial(root, **options, planning_effort="low", approved_plan=low.digest, _transport=transport) as product:
        result = product.application.propose_character_reply(context_request(options))
        assert result.status == "unknown" and result.code == "transport-timeout"
        assert product.application.propose_character_reply(context_request(options, 1)).code == "communication-trial-stopped"
    with open_trial(root, **options, planning_effort="low", approved_plan=low.digest, _transport=transport) as resumed:
        assert resumed.application.propose_character_reply(context_request(options)) == result
    assert len(transport.calls) == 2
