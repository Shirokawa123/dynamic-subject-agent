"""S109 continuous scenarios carried forward through the S110 control repair.

The original failed results remain in the S109 report. The transport supplies every
word and planning choice; no assertion measures model quality or naturalness.
Only the production Facade/Timeline decides publication and restored context.
"""
import json
import socket
from hashlib import sha256

import pytest

from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from dynamic_subject_agent.deepseek import DeepSeekHttpResponse, DeepSeekUrlLibTransport
from dynamic_subject_agent.first_life import LIFE_POLICY, FirstLifeHeartbeatRequest, FirstLifeSimulationRequest
from dynamic_subject_agent.first_life_followup import FOLLOWUP_VERSION, first_life_scope_digest
from dynamic_subject_agent.first_life_relevance import SHARE_POLICY
from dynamic_subject_agent.frozen_attempt import canonical_json
from test_first_life_facade import (
    LifeTransport, approved, life_fixture, model_fixture, personality_fixture, settle,
)
from test_reviewed_character_chat import send


INTRO = "先聊聊你最近在构思什么。"
FOLLOWUP = "然后呢？"
CONFLICT = "你说右侧没有灯，可当前构图里还有台灯，这两句话怎么对得上？"
NEW_IDEA = "要不要试试让窗光更柔和一点？"
ORDINARY_GOAL = "你平时会给自己定目标吗？"
WITHDRAWAL = "不要再提刚才那句话。"
SHARE = "合成台词：我把右侧的台灯拿掉了，只留下窗光。"
V1 = dict(subject="窗边的书桌", composition="书桌靠左，右侧放着台灯", focus="桌面轮廓")
V2 = dict(subject="窗边的书桌", composition="书桌居中，右侧仍放着台灯", focus="窗光与桌面轮廓")


@pytest.fixture(autouse=True)
def no_remote_io(monkeypatch):
    """Fail loudly if composition ever falls back to real networking or a key."""
    from dynamic_subject_agent import deepseek, local_product
    from dynamic_subject_agent.credentials import WindowsCredentialStore

    def forbidden(*args, **kwargs):
        pytest.fail("S109 synthetic baseline must never access network or credentials")

    monkeypatch.setattr(DeepSeekUrlLibTransport, "post_json", forbidden)
    monkeypatch.setattr(deepseek, "urlopen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(local_product._WindowsLabResolver, "resolve", forbidden)
    monkeypatch.setattr(WindowsCredentialStore, "load", forbidden)


class ContinuousBaselineTransport(LifeTransport):
    """Capture the actual v4 wire; responses below are hand-authored fixtures."""

    def post_json(self, **kwargs):
        body = json.loads(kwargs["body"])
        projection = json.loads(body["messages"][1]["content"])
        self.calls.append((body, projection))
        self.wire_digests.append(sha256(kwargs["body"]).hexdigest())
        if "conversation" in projection:
            message = projection["conversation"]["current_message"]
            if "dialogue_sources" in projection:
                sources = projection["dialogue_sources"]
                selected = [r["label"] for r in sources if r["label"] == "S1"]
                if not selected:
                    selected = [r["label"] for r in sources if r["speaker"] == "assistant"][-1:]
                value = dict(action="answer", fact_refs=[], use_life=message == CONFLICT,
                    focus="clarify-premise" if message == CONFLICT else "respond-current",
                    dialogue_refs=selected)
            else:
                value = dict(reply_text="合成回复：" + message, language="zh")
        elif projection["policy"] == LIFE_POLICY:
            self.actions += 1
            assert self.actions in (1, 2), "only the two explicit synthetic activity inputs are allowed"
            value = dict(action="start" if self.actions == 1 else "revise",
                plan=V1 if self.actions == 1 else V2, reason_code="balance-space")
        else:
            assert projection["policy"] == SHARE_POLICY
            value = dict(share=True, reply_text=SHARE, language="zh",
                focus="composition", opening="self-interest")
        self.responses.append(value)
        response = dict(model="deepseek-flash", choices=[dict(finish_reason="stop",
            message=dict(role="assistant", content=canonical_json(value)))],
            usage=dict(prompt_tokens=0, completion_tokens=0))
        return DeepSeekHttpResponse(200, canonical_json(response).encode())


def history(product):
    result = product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
        product.profile_id, product.timeline_id))
    assert result.status == "available", result
    return result.projection.turns


def chat(product, transport, steps, message, *, status="terminal"):
    before = len(transport.calls)
    result = send(product, message, f"s109-continuous-{len(steps) + 1}")
    failure = getattr(result.projection, "failure_code", "")
    steps.append(dict(turn=len(steps) + 1, user=message, status=str(result.status), failure=failure,
        synthetic_calls=len(transport.calls) - before, canonical_turns=len(history(product))))
    assert result.status == status, result
    if status == "failed-closed":
        assert failure == "first-life-history-unverified"
        assert len(transport.calls) == before
    else:
        assert len(transport.calls) == before + 2
        assert result.projection.expression_text == "合成回复：" + message
    return result


def open_baseline(life_fixture):
    opening, transport, _, _, view = life_fixture
    transport.__class__ = ContinuousBaselineTransport
    transport.responses, transport.wire_digests = [], []
    product = opening(runtime_policy=FOLLOWUP_VERSION,
        runtime_policy_digest=first_life_scope_digest(view.definition_basis))
    steps = []
    chat(product, transport, steps, INTRO)
    app = product.application
    for index in (1, 2):
        result = settle(app, app.simulate_first_life_step(FirstLifeSimulationRequest(f"s109-life-version-{index}")))
        assert result.status == "terminal", result
    result = settle(app, app.heartbeat_first_life(FirstLifeHeartbeatRequest("s109-session-0001", "s109-continuous-share")))
    assert result.status == "terminal", (result.status, getattr(result.projection, "failure_code", ""))
    state = app.query_first_life()
    assert state.status == "available" and len(state.versions) == 2 and len(state.events) == 2
    assert state.versions[0].plan.composition == V1["composition"]
    assert state.versions[1].plan.composition == V2["composition"]
    assert all(event.simulated for event in state.events)
    assert state.shares[0].text == SHARE and not state.shares[0].answered
    assert len(history(product)) == 1  # System events and shares never become fake user turns.

    chat(product, transport, steps, FOLLOWUP)
    planning, expression = transport.calls[-2][1], transport.calls[-1][1]
    assert planning["current_plan"] == V2
    assert any(row["label"] == "S1" and row["text"] == SHARE for row in planning["dialogue_sources"])
    assert expression["selected_dialogue"] == [dict(label="S1", speaker="assistant", text=SHARE, kind="proactive-share")]
    assert expression["current_activity"] == {} and expression["current_plan"] is None
    assert expression["related_event"] is None

    chat(product, transport, steps, CONFLICT)
    expression = transport.calls[-1][1]
    assert expression["current_plan"] == V2 and expression["related_event"]["revision"] == 2
    assert any(row["label"] == "S1" and row["text"] == SHARE for row in expression["selected_dialogue"])
    chat(product, transport, steps, NEW_IDEA)
    assert all(row["label"] != "S1" for row in transport.calls[-2][1]["dialogue_sources"])
    assert [turn.user_text for turn in history(product)] == [INTRO, FOLLOWUP, CONFLICT, NEW_IDEA]
    assert product.application.query_first_life().project.current_plan.composition == V2["composition"]
    return product, opening, transport, steps


def report(name, product, transport, steps):
    print("S109_BASELINE " + canonical_json(dict(chain=name,
        generation="all planning choices, life text, share and replies are hand-authored synthetic responses",
        persistence="production Facade with S110 controls, existing authority/budget and canonical Timeline; no transcript input store",
        quality_verdict="not evaluated", real_provider_calls=0, synthetic_calls=len(transport.calls),
        wire_digests=transport.wire_digests, canonical_turns=len(history(product)), steps=steps)))


def test_ordinary_goal_now_continues_through_the_remaining_chain_and_restart(life_fixture):
    product, opening, transport, steps = open_baseline(life_fixture)
    chat(product, transport, steps, ORDINARY_GOAL)
    chat(product, transport, steps, "那聊聊你喜欢哪种颜色吧。")
    saved_history, saved_life = history(product), product.application.query_first_life()
    identity = product.profile_id, product.timeline_id
    before_restart = len(transport.calls)
    product.close()
    product = opening()
    assert (product.profile_id, product.timeline_id) == identity
    assert history(product) == saved_history and product.application.query_first_life() == saved_life
    assert len(transport.calls) == before_restart
    chat(product, transport, steps, "接着聊窗边的颜色吧。")
    chat(product, transport, steps, "也可以聊聊今天的天气题材。")
    assert history(product)[:6] == saved_history and len(history(product)) == 8
    report("ordinary-goal-eight-turns-repaired", product, transport, steps)


def test_history_off_does_not_resolve_withdrawal_but_explicit_context_reset_does(life_fixture):
    from dynamic_subject_agent.first_life import FirstLifeContextResetRequest
    product, opening, transport, steps = open_baseline(life_fixture)
    chat(product, transport, steps, WITHDRAWAL, status="failed-closed")
    chat(product, transport, steps, "换个话题，聊聊蓝色。", status="failed-closed")
    before_setting = len(transport.calls)
    assert product.application.set_reviewed_character_history(False).status == "active"
    assert len(transport.calls) == before_setting
    chat(product, transport, steps, "现在聊聊蓝色吧。", status="failed-closed")
    boundary = settle(product.application, product.application.reset_first_life_context(
        FirstLifeContextResetRequest("s110-baseline-explicit-boundary", True)))
    assert boundary.status == "terminal" and len(transport.calls) == before_setting
    chat(product, transport, steps, "从现在的蓝色话题继续。")
    assert transport.calls[-2][1]["history_enabled"] is False
    assert transport.calls[-2][1]["dialogue_sources"] == []
    assert transport.calls[-1][1]["selected_dialogue"] == []
    # Turning dialogue export off does not withdraw independently authorized life facts.
    assert transport.calls[-2][1]["current_plan"] == V2
    saved_history, saved_life = history(product), product.application.query_first_life()
    identity = product.profile_id, product.timeline_id
    before_restart = len(transport.calls)
    product.close()
    product = opening()
    assert (product.profile_id, product.timeline_id) == identity
    assert history(product) == saved_history and product.application.query_first_life() == saved_life
    assert product.application.reviewed_character_chat_status().history_enabled is False
    assert len(transport.calls) == before_restart
    chat(product, transport, steps, "仍然聊蓝色，先从浅色说起。")
    assert transport.calls[-2][1]["dialogue_sources"] == []
    before_setting = len(transport.calls)
    assert product.application.set_reviewed_character_history(True).status == "active"
    assert len(transport.calls) == before_setting
    chat(product, transport, steps, "继续刚才的颜色话题。")
    assert len(history(product)) == 7
    report("withdrawal-explicit-reset-ten-turns", product, transport, steps)
