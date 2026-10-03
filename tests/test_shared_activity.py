import json
from dataclasses import asdict

import pytest

from test_original_whole_chat import approved, personality_fixture, model_fixture, send, history
from dynamic_subject_agent.local_product import open_shared_activity_product_local
from dynamic_subject_agent.model_gateway import ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelGateway, ModelResult, ModelTaskKind
from dynamic_subject_agent.shared_activity import SharedExperienceRequest, SharedActivityStepRequest


class LocalAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities('local-shared-fixture', 'deterministic-test', True, (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self):
        self.calls = []
        self.callback = None
        self.fail = False
        self.override = None

    def invoke(self, task):
        self.calls.append(task)
        if self.callback:
            self.callback()
        if self.fail:
            raise ValueError('synthetic model failure')
        if self.override is not None:
            return ModelResult(task.kind, self.override)
        if task.kind is ModelTaskKind.SHARED_ACTIVITY_REPLY:
            value = dict(reply_text='合成交流回复。', language='zh')
        else:
            payload = task.payload['payload']
            action = payload['current_activity']['allowed_actions'][0]
            value = dict(action=action, plan=dict(subject='静物', composition='桌边留白' + str(len(self.calls)), focus='光线') if action in ('start', 'revise') else None,
                reason_code='balance-space', basis_refs=['E1'] if payload['shared_experience'] else [], decision_note='本次合成取舍依据已列原话。')
        return ModelResult(task.kind, value)


@pytest.fixture
def shared_fixture(approved, monkeypatch):
    author, config, request, view = approved
    frozen = author.application.freeze_source_identity(request)
    assert frozen.status == 'created'
    author.close()
    asset = json.loads(view.runtime_asset_json)
    import dynamic_subject_agent.original_whole_chat as module
    binding = dict(definition_basis=view.definition_basis, runtime_asset_sha=view.runtime_asset_sha,
        persona_digest=asset['persona_digest'], review_basis='1'*64, scope_digest='2'*64,
        subject_id=asset['subject']['subject_id'], anchor_id=asset['anchor']['anchor_id'])
    monkeypatch.setattr(module, 'APPROVED_BINDING', binding)
    opened = []
    def opening(adapter=None):
        result = open_shared_activity_product_local(config, gateway=ModelGateway(adapter or LocalAdapter()), identity_id=frozen.view.identity_id, binding=binding)
        opened.append(result)
        return result
    yield opening
    for product in opened:
        product.close()


def select(product, quote, head=1, key='shared-select-source-1'):
    state = product.application.query_shared_activity()
    assert state.status == 'available', state
    return product.application.set_shared_experience(SharedExperienceRequest(product.profile_id, product.timeline_id,
        key, state.view['revision'], head, quote, True))


def step_request(product, key='shared-advance-one-1'):
    state = product.application.query_shared_activity()
    assert state.status == 'available', state
    return SharedActivityStepRequest(product.profile_id, product.timeline_id, key, state.view['revision'])


def test_shared_experience_survives_window_and_reopen_then_choice_result_enters_next_chat(shared_fixture):
    adapter = LocalAdapter(); product = shared_fixture(adapter)
    assert product.application.query_shared_activity().status == 'available'
    assert send(product, '我喜欢桌边留白。', 'source').status == 'terminal'
    selected = select(product, '桌边留白')
    assert selected.status == 'committed', selected
    for index in range(3):
        assert send(product, '无关合成话题' + str(index), 'unrelated-' + str(index)).status == 'terminal'
    saved = history(product); product.close()
    fresh = LocalAdapter(); product = shared_fixture(fresh)
    assert history(product) == saved and not fresh.calls
    preview = product.application.preview_shared_activity_step()
    assert preview.status == 'previewed', preview
    assert preview.view['payload']['shared_experience'] == dict(label='E1', quote='桌边留白')
    request = step_request(product)
    result = product.application.advance_shared_activity(request)
    assert result.status == 'committed', result
    assert fresh.calls[0].payload == preview.view
    assert product.application.advance_shared_activity(request).status == 'replayed'
    assert len(fresh.calls) == 1
    state = product.application.query_shared_activity().view
    assert state['phase'] == 'drafted' and state['activity_revision'] == 1
    assert send(product, '刚才方案有什么安排？', 'after-result').status == 'terminal'
    assert fresh.calls[-1].payload['payload']['evidence']['activity_result'] == dict(kind='composition-text', plan=asdict(state['current_plan']))


@pytest.mark.parametrize('control', ['disable', 'off', 'context', 'withdraw'])
def test_revoked_sources_cannot_return_through_plan_result_or_complete_dialogue(shared_fixture, control):
    adapter = LocalAdapter(); product = shared_fixture(adapter)
    assert send(product, '合成依据：桌边必须留白。', 'filter-source').status == 'terminal'
    assert select(product, '桌边必须留白').status == 'committed'
    assert product.application.advance_shared_activity(step_request(product)).status == 'committed'
    assert send(product, '说说已提交的方案。', 'filter-derived-reply').status == 'terminal'
    if control == 'disable':
        assert select(product, '', head=None, key='shared-disable-source-1').status == 'committed'
    elif control == 'off':
        assert product.application.set_reviewed_character_history(False).history_enabled is False
    elif control == 'context':
        from dynamic_subject_agent.whole_context_boundary import WholeContextBoundaryRequest
        assert product.application.apply_whole_context_boundary(WholeContextBoundaryRequest(product.profile_id, product.timeline_id,
            'shared-context-boundary-1', 0, True)).status == 'committed'
    else:
        calls = len(adapter.calls)
        assert send(product, '不要再使用之前的聊天。', 'filter-withdraw').status == 'failed-closed'
        assert len(adapter.calls) == calls
    product.close(); fresh = LocalAdapter(); product = shared_fixture(fresh)
    preview = product.application.preview_shared_activity_step()
    assert preview.status == 'previewed', preview
    assert preview.view['payload']['shared_experience'] is None
    assert preview.view['payload']['current_plan'] is None
    assert preview.view['payload']['current_activity']['phase'] == 'drafted'
    assert send(product, '现在谈谈新话题。', 'after-source-revoked').status == 'terminal'
    payload = fresh.calls[-1].payload['payload']
    assert payload['evidence'] == dict(shared_experience=None, activity_result=None)
    assert payload['exchange'] == ()
    assert product.application.query_shared_activity().view['result'] is not None


def test_replacement_can_make_independent_revision_without_erasing_old_result(shared_fixture):
    adapter = LocalAdapter(); product = shared_fixture(adapter)
    assert send(product, '旧合成依据留白。', 'old-source').status == 'terminal'
    assert select(product, '旧合成依据留白').status == 'committed'
    assert product.application.advance_shared_activity(step_request(product)).status == 'committed'
    old = product.application.query_shared_activity().view['result']
    assert send(product, '新合成依据强调线条。', 'new-source').status == 'terminal'
    head = history(product)[-1].head_sequence
    assert select(product, '强调线条', head, 'shared-select-replacement-1').status == 'committed'
    preview = product.application.preview_shared_activity_step().view['payload']
    assert preview['current_plan'] is None and preview['current_activity']['phase'] == 'drafted'
    assert product.application.advance_shared_activity(step_request(product, 'shared-new-version-2')).status == 'committed'
    state = product.application.query_shared_activity().view
    assert state['activity_revision'] == 2 and state['phase'] == 'revised'
    assert state['result'].source_dependencies == (state['source'].source_key,)
    assert state['result'].source_dependencies != old.source_dependencies
    assert state['result'].differences[0].before != ''


@pytest.mark.parametrize('prepared', [False, True])
def test_cold_recovery_never_repeats_model_and_prepared_result_is_atomic(shared_fixture, monkeypatch, prepared):
    from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint, PublicationInterrupted
    adapter = LocalAdapter(); product = shared_fixture(adapter)
    request = step_request(product)
    with monkeypatch.context() as crash:
        if prepared:
            original = TimelineEngine._hit
            def hit(self, point):
                if point is FaultPoint.AFTER_PLAN_CLAIM:
                    raise OSError('Synthetic interruption after durable preparation')
                return original(self, point)
            crash.setattr(TimelineEngine, '_hit', hit)
        else:
            crash.setattr(TimelineEngine, 'publish', lambda *a, **kw: (_ for _ in ()).throw(PublicationInterrupted('synthetic', 'Before preparation')))
        product.application.advance_shared_activity(request)
    assert len(adapter.calls) == 1
    product.close(); fresh = LocalAdapter(); product = shared_fixture(fresh)
    assert not fresh.calls
    state = product.application.query_shared_activity()
    assert state.status == 'available', state
    assert (state.view['result'] is not None) is prepared
    replay = product.application.advance_shared_activity(request)
    assert replay.status == ('replayed' if prepared else 'failed-closed'), replay
    assert not fresh.calls


def test_invalid_source_and_wrong_target_do_not_admit_or_call_model(shared_fixture):
    from dataclasses import replace
    from uuid import uuid4
    adapter = LocalAdapter(); product = shared_fixture(adapter)
    assert send(product, '仅此用户原话。', 'source-validation').status == 'terminal'
    assert select(product, '不是原话').status == 'unavailable'
    assert product.application.query_shared_activity().view['revision'] == 1
    request = step_request(product)
    assert product.application.advance_shared_activity(replace(request, target_profile_id=str(uuid4()))).status == 'unavailable'
    assert len(adapter.calls) == 1


def test_model_failure_has_no_activity_event_and_authorization_race_cancels_prepared(shared_fixture, monkeypatch):
    from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint
    adapter = LocalAdapter(); product = shared_fixture(adapter)
    adapter.fail = True
    assert product.application.advance_shared_activity(step_request(product)).status == 'failed-closed'
    adapter.fail = False
    assert product.application.query_shared_activity().view['result'] is None
    original = TimelineEngine._hit
    def revoke(self, point):
        if point is FaultPoint.BEFORE_PUBLICATION_COMMIT:
            assert product.application.set_reviewed_character_history(False).history_enabled is False
            assert product.application.set_reviewed_character_history(True).history_enabled is True
        return original(self, point)
    with monkeypatch.context() as race:
        race.setattr(TimelineEngine, '_hit', revoke)
        result = product.application.advance_shared_activity(step_request(product, 'shared-race-choice-2'))
    assert result.status == 'failed-closed', result
    assert product.application.query_shared_activity().view['result'] is None
    assert len(adapter.calls) == 2


def test_cold_prepared_result_is_cancelled_after_history_revision_changes(shared_fixture, monkeypatch):
    from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint
    adapter = LocalAdapter(); product = shared_fixture(adapter)
    request = step_request(product)
    original = TimelineEngine._hit
    def interrupt(self, point):
        if point is FaultPoint.AFTER_PLAN_CLAIM:
            raise OSError('Synthetic interruption')
        return original(self, point)
    with monkeypatch.context() as crash:
        crash.setattr(TimelineEngine, '_hit', interrupt)
        product.application.advance_shared_activity(request)
    assert product.application.set_reviewed_character_history(False).history_enabled is False
    assert product.application.set_reviewed_character_history(True).history_enabled is True
    product.close(); fresh = LocalAdapter(); product = shared_fixture(fresh)
    assert not fresh.calls and len(adapter.calls) == 1
    assert product.application.query_shared_activity().view['result'] is None
    assert product.application.advance_shared_activity(request).status == 'failed-closed'


def test_corrupt_shared_source_record_closes_query_and_model_disclosure(shared_fixture):
    import sqlite3
    from test_whole_chat_archive import canonical_path
    adapter = LocalAdapter(); product = shared_fixture(adapter)
    assert send(product, '合成来源。', 'corrupt-source').status == 'terminal'
    assert select(product, '合成来源').status == 'committed'
    with sqlite3.connect(canonical_path(product)) as writer:
        writer.execute("UPDATE shared_activity_record SET record_json='{}'")
    assert product.application.query_shared_activity().status == 'failed-closed'
    assert send(product, '继续当前话题。', 'corrupt-shared-after').status == 'failed-closed'
    assert len(adapter.calls) == 1


def test_known_reply_failure_cuts_dialogue_without_revoking_selected_experience(shared_fixture):
    adapter = LocalAdapter(); product = shared_fixture(adapter)
    assert send(product, '合成可用来源留白。', 'retained-source').status == 'terminal'
    assert select(product, '可用来源留白').status == 'committed'
    adapter.fail = True
    assert send(product, '这轮合成技术失败。', 'known-reply-failure').status == 'failed-closed'
    adapter.fail = False
    state = product.application.query_shared_activity()
    assert state.status == 'available' and state.view['visible_source'].quote == '可用来源留白'
    assert send(product, '接着聊。', 'after-known-failure').status == 'terminal'
    payload = adapter.calls[-1].payload['payload']
    assert payload['exchange'] == ()
    assert payload['evidence']['shared_experience'] == dict(label='E1', quote='可用来源留白')


def test_deferred_empty_activity_can_form_its_first_plan_without_rewriting_phase_history(shared_fixture):
    class DeferredAdapter(LocalAdapter):
        def invoke(self, task):
            if not self.calls and task.kind is ModelTaskKind.SHARED_ACTIVITY_CHOICE:
                self.calls.append(task)
                return ModelResult(task.kind, dict(action='defer', plan=None, reason_code='defer-comparison', basis_refs=[], decision_note='先暂缓构图。'))
            return super().invoke(task)
    adapter = DeferredAdapter(); product = shared_fixture(adapter)
    assert product.application.advance_shared_activity(step_request(product)).status == 'committed'
    state = product.application.query_shared_activity().view
    assert state['phase'] == 'deferred' and state['current_plan'] is None and state['activity_revision'] == 0
    assert product.application.advance_shared_activity(step_request(product, 'shared-after-defer-1')).status == 'committed'
    state = product.application.query_shared_activity().view
    assert state['phase'] == 'revised' and state['current_plan'] is not None and state['activity_revision'] == 1
    assert adapter.calls[-1].payload['payload']['current_activity']['phase'] == 'deferred'


def test_exact_remote_preview_is_not_an_executable_grant(shared_fixture):
    from dynamic_subject_agent.shared_activity_remote_preview import PendingSharedActivityGrant, UnapprovedSharedActivityAdapter, shared_remote_request_preview
    from dynamic_subject_agent.model_gateway import ModelTask, ModelGatewayFailure
    adapter = LocalAdapter(); product = shared_fixture(adapter)
    preview = product.application.preview_shared_activity_step().view
    task = ModelTask(ModelTaskKind.SHARED_ACTIVITY_CHOICE, preview)
    wire = shared_remote_request_preview(task)
    assert wire['body']['messages'][0]['content'] == preview['policy']
    assert json.loads(wire['body']['messages'][1]['content']) == json.loads(json.dumps(preview['payload']))
    assert wire['body']['model'] == 'deepseek-flash'
    assert wire['body']['max_tokens'] == 4096 and wire['timeout_seconds'] == 30 and wire['automatic_retries'] == 0
    gateway = ModelGateway(UnapprovedSharedActivityAdapter(PendingSharedActivityGrant('1'*64)))
    with pytest.raises(ModelGatewayFailure, match='shared-activity-use-unapproved'):
        gateway.execute(task)
    with pytest.raises(ValueError, match='local-only'):
        # The production LOCAL composition refuses a remote capability before
        # reading a registry or touching any credential.
        open_shared_activity_product_local(None, gateway=gateway, identity_id='unused')
    assert not adapter.calls


def test_invalid_refs_and_unchanged_plan_cannot_become_activity_results(shared_fixture):
    adapter = LocalAdapter(); product = shared_fixture(adapter)
    adapter.override = dict(action='start', plan=dict(subject='静物', composition='留白', focus='光线'),
        reason_code='balance-space', basis_refs=['E2'], decision_note='合成无效依据。')
    assert product.application.advance_shared_activity(step_request(product)).status == 'failed-closed'
    assert product.application.query_shared_activity().view['result'] is None
    adapter.override = None
    assert product.application.advance_shared_activity(step_request(product, 'shared-valid-after-refs')).status == 'committed'
    saved = product.application.query_shared_activity().view['result']
    adapter.override = dict(action='revise', plan=asdict(saved.plan), reason_code='balance-space', basis_refs=[], decision_note='合成未改变方案。')
    assert product.application.advance_shared_activity(step_request(product, 'shared-unchanged-plan')).status == 'failed-closed'
    state = product.application.query_shared_activity().view
    assert state['result'] == saved and state['activity_revision'] == 1 and len(adapter.calls) == 3


def test_source_selected_after_echo_still_removes_preselection_derived_dialogue(shared_fixture):
    adapter = LocalAdapter(); product = shared_fixture(adapter)
    assert send(product, '合成旧依据蓝桥。', 'before-selection-source').status == 'terminal'
    adapter.override = dict(reply_text='你刚才说了合成旧依据蓝桥。', language='zh')
    assert send(product, '接着聊这段原话。', 'before-selection-echo').status == 'terminal'
    adapter.override = None
    assert select(product, '合成旧依据蓝桥').status == 'committed'
    assert select(product, '', head=None, key='shared-disable-after-echo').status == 'committed'
    product.close(); fresh = LocalAdapter(); product = shared_fixture(fresh)
    assert send(product, '现在谈新话题。', 'after-preselection-echo-disabled').status == 'terminal'
    payload = fresh.calls[-1].payload['payload']
    assert payload['exchange'] == () and payload['evidence']['shared_experience'] is None


def test_replacing_quote_in_same_source_turn_does_not_restore_withdrawn_quote(shared_fixture):
    adapter = LocalAdapter(); product = shared_fixture(adapter)
    assert send(product, '旧依据A；新依据B。', 'same-head-source').status == 'terminal'
    assert select(product, '旧依据A').status == 'committed'
    assert select(product, '新依据B', key='shared-same-head-replacement').status == 'committed'
    assert send(product, '继续当前选择。', 'same-head-followup').status == 'terminal'
    payload = adapter.calls[-1].payload['payload']
    assert payload['exchange'] == ()
    assert payload['evidence']['shared_experience'] == dict(label='E1', quote='新依据B')
