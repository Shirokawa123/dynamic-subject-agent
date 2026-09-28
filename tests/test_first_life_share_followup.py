"""Conversation after a committed proactive share, via the public Facade."""
import json
import pytest

from dynamic_subject_agent.first_life import FirstLifeControlRequest, FirstLifeHeartbeatRequest, FirstLifeSimulationRequest
from dynamic_subject_agent.first_life_grounded import GROUNDED_VERSION
from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from dynamic_subject_agent.deepseek import DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json
from test_first_life_grounded import open_version, GroundedTransport
from test_first_life_facade import life_fixture, settle, approved, model_fixture, personality_fixture
from test_reviewed_character_chat import send


@pytest.mark.parametrize('history_enabled', [True, False])
def test_conversation_continues_after_share_controls_and_restart(life_fixture, history_enabled):
    opening, transport, _, _, view = life_fixture
    product = open_version(opening, transport, view, GROUNDED_VERSION)
    app = product.application
    intro = send(product, '我喜欢聊画面里的留白。', 'share-followup-intro')
    assert intro.status == 'terminal', repr(intro)
    assert settle(app, app.simulate_first_life_step(FirstLifeSimulationRequest('share-followup-step'))).status == 'terminal'
    shared = settle(app, app.heartbeat_first_life(FirstLifeHeartbeatRequest('share-followup-session', 'share-followup-heartbeat')))
    assert shared.status == 'terminal', repr(shared)
    assert len(app.query_first_life().shares) == 1
    assert settle(app, app.set_first_life_controls(FirstLifeControlRequest('share-followup-controls', paused=True,
        sharing_enabled=False))).status == 'terminal'
    assert app.set_reviewed_character_history(history_enabled).status == 'active'
    product.close()
    restored = opening()
    history = restored.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
        restored.profile_id, restored.timeline_id))
    assert history.status == 'available', repr(history)
    assert len(history.projection.turns) == 1
    before = len(transport.calls)
    question = '你说的屏幕上线稿，是现在真的已经画在数位板上，还是构图里的设想？你说四周留白，是保存的方案已有这个决定，还是刚才聊着想到的？'
    followed = send(restored, question, 'share-followup-after-restart')
    assert followed.status == 'terminal', repr(followed)
    assert len(transport.calls) == before + 2
    planning = transport.calls[-2][1]
    assert planning['history_enabled'] is history_enabled
    assert bool(planning['dialogue_sources']) is history_enabled
    assert planning['has_prior_committed_exchange'] is True
    assert restored.application.query_first_life().shares[0].answered is True
    ordinary = send(restored, '接着说说画面。', 'share-followup-next-ordinary')
    assert ordinary.status == 'terminal', repr(ordinary)
    sources = transport.calls[-2][1]['dialogue_sources']
    assert any(source['speaker'] == 'user' and source['text'] == question for source in sources) is history_enabled


@pytest.mark.parametrize('message', [
    '不要用保存的方案，构图现在是什么？',
    '请保存这个方案，刚才保存的版本是什么？',
    '删除保存的方案，后面怎么调整？',
    pytest.param('保存的方案里帮我加个灯好吗？', id='nominal-add'),
    pytest.param('保存的方案能改成夜景吗？', id='nominal-change'),
    pytest.param('保存的方案存起来好吗？', id='nominal-save'),
    pytest.param('我不愿再用保存的方案，好吗？', id='nominal-unwilling'),
])
def test_actual_control_and_mixed_questions_still_block_history_and_later_attempts(life_fixture, message):
    opening, transport, _, _, view = life_fixture
    product = open_version(opening, transport, view, GROUNDED_VERSION)
    assert send(product, '合成开场聊留白。', 'share-control-intro').status == 'terminal'
    before = len(transport.calls)
    controlled = send(product, message, 'share-control-request')
    assert controlled.status == 'failed-closed'
    assert controlled.projection.failure_code == 'first-life-history-unverified'
    assert len(transport.calls) == before
    later = send(product, '接着说说画面。', 'share-control-later')
    assert later.status == 'failed-closed'
    assert len(transport.calls) == before


@pytest.mark.parametrize('message', [
    '我不愿再用保存的方案，好吗？',
    '我不想让你再提保存的方案，可以吗？',
])
def test_negative_willingness_cannot_use_the_nominal_readonly_exception(message):
    from dynamic_subject_agent.first_life_dialogue import is_first_life_dialogue_control
    from dynamic_subject_agent.recent_dialogue import is_dialogue_control
    assert is_dialogue_control(message) is True
    assert is_first_life_dialogue_control(message) is True


class InvalidOnceTransport(GroundedTransport):
    invalid_once = False

    def post_json(self, **kwargs):
        response = super().post_json(**kwargs)
        if self.invalid_once:
            self.invalid_once = False
            value = json.loads(response.body)
            value['choices'][0]['message']['content'] = '{}'
            return DeepSeekHttpResponse(200, canonical_json(value).encode())
        return response


def test_failed_readonly_question_does_not_become_an_unresolved_history_control(life_fixture):
    opening, transport, _, _, view = life_fixture
    product = open_version(opening, transport, view, GROUNDED_VERSION)
    assert send(product, '先聊聊画面。', 'failed-reference-intro').status == 'terminal'
    transport.__class__ = InvalidOnceTransport
    transport.invalid_once = True
    failed = send(product, '保存的版本里有哪些留白？', 'failed-reference-question')
    assert failed.status == 'failed-closed'
    assert failed.projection.failure_code == 'first-life-structured-choice-invalid'
    product.close()
    restored = opening()
    before = len(transport.calls)
    continued = send(restored, '接着聊构图吧。', 'failed-reference-continue')
    assert continued.status == 'terminal', repr(continued)
    assert len(transport.calls) == before + 2
    # A finalized failed attempt still cuts off older dialogue. It is neither
    # exported as a committed pair nor mistaken for an unresolved withdrawal.
    assert transport.calls[-2][1]['dialogue_sources'] == []
    assert transport.calls[-2][1]['has_prior_committed_exchange'] is True
