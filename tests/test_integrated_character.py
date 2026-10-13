"""Integrated Facade behavior; all replies here are explicit synthetic fixtures."""
import json
from dataclasses import asdict
import pytest

from test_original_whole_chat import approved, personality_fixture, model_fixture, send, history
from test_shared_activity import select
from test_living_activity import state, control, act, action_request
from dynamic_subject_agent.local_product import open_integrated_character_product_local
from dynamic_subject_agent.model_gateway import ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelGateway, ModelResult, ModelTaskKind

MESSAGE = '把所有“松架”换成“杉架”，其他照旧。'
PLAN = dict(subject='窗边晾衣处', composition='松架靠窗。'+('左侧暖光照在衣褶上，地面留空，不改镜头。'*10)+'远处松架保留木纹。', focus='先看手上的动作')


class LocalAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities('integrated-local-fixture', 'synthetic', True, (StructuredOutputMode.JSON_OBJECT,))
    def __init__(self):
        self.calls, self.override, self.fail, self.share = [], None, False, True
        self.plan = PLAN
    def invoke(self, task):
        self.calls.append(task)
        if self.fail:
            raise ValueError('synthetic failure')
        if self.override is not None:
            return ModelResult(task.kind, self.override)
        payload = task.payload['payload']
        if task.kind is ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK:
            message = payload['turn']['current_message']
            intent = 'revise' if message == MESSAGE else 'clarify' if message == '那一处也改掉。' else 'chat'
            value = dict(intent=intent, reply_text='合成修订回复。' if intent == 'revise' else '合成接话。')
        elif task.kind is ModelTaskKind.LIVING_ACTIVITY_SHARE:
            value = dict(share=self.share, reply_text='合成分享：这版我想保留窗边的暖光。' if self.share else '', language='zh')
        else:
            current = payload['current_plan']
            action = 'start' if current is None else 'revise'
            value = dict(action=action, plan=dict(self.plan) if current is None else dict(current, focus='观察衣褶的明暗'),
                reason_code='improve-readability', basis_refs=['E1'] if payload['shared_experience'] else [], decision_note='合成具体取舍。')
        return ModelResult(task.kind, value)


@pytest.fixture
def integrated_fixture(approved, monkeypatch):
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
    def opening(adapter=None, **kwargs):
        product = open_integrated_character_product_local(config, gateway=ModelGateway(adapter or LocalAdapter()),
            identity_id=frozen.view.identity_id, binding=binding, **kwargs)
        opened.append(product)
        return product
    opening.config, opening.identity_id, opening.binding = config, frozen.view.identity_id, binding
    yield opening
    for product in opened:
        product.close()


def start(integrated_fixture, *, with_source=False):
    adapter = LocalAdapter(); product = integrated_fixture(adapter)
    if with_source:
        assert send(product, '这一版想保留窗边暖光。', 'integrated-source-chat-1').status == 'terminal'
        assert select(product, '这一版想保留窗边暖光。').status == 'committed'
    assert control(product, paused=False, sharing=True).status == 'committed'
    assert act(product).status == 'committed'
    return product, adapter


def test_one_timeline_share_feedback_long_edit_window_reopen_and_actual_next_choice(integrated_fixture):
    product, adapter = start(integrated_fixture, with_source=True)
    original = state(product)['current_plan']
    assert original.composition.rfind('松架') - original.composition.find('松架') > 160
    before = product.application.preview_living_activity('share')
    assert before.status == 'previewed'
    share_request = action_request(product, 'share', 'integrated-first-share-1')
    assert product.application.advance_living_activity(share_request).status == 'committed'
    assert adapter.calls[-1].payload == before.view
    preview = product.application.preview_natural_feedback(MESSAGE)
    assert preview.status == 'previewed' and preview.view['payload']['evidence']['latest_share']
    assert send(product, MESSAGE, 'integrated-feedback-first').status == 'terminal'
    assert adapter.calls[-1].payload == preview.view
    updated = state(product)['current_plan']
    assert asdict(updated) == {k: v.replace('松架','杉架') for k,v in asdict(original).items()}
    assert product.application.query_shared_activity().view['activity_revision'] == 2
    for index in range(3):
        assert send(product, '合成无关话题'+str(index), 'integrated-topic-'+str(index)).status == 'terminal'
    payload = adapter.calls[-1].payload['payload']
    assert payload['evidence']['latest_share'] is None
    assert MESSAGE not in json.dumps(payload['exchange'], ensure_ascii=False)
    assert state(product)['current_plan'] == updated
    identity = (product.profile_id, product.timeline_id)
    saved = history(product); product.close()
    fresh = LocalAdapter(); product = integrated_fixture(fresh)
    assert (product.profile_id,product.timeline_id) == identity and history(product) == saved and not fresh.calls
    choice = product.application.preview_living_activity('choice')
    assert choice.view['payload']['current_feedback'] == dict(label='F1', quote=MESSAGE)
    assert act(product, key='integrated-next-choice-1').status == 'committed'
    assert fresh.calls[-1].payload == choice.view
    assert product.application.query_shared_activity().view['activity_revision'] == 3
    assert state(product)['current_plan'].composition == updated.composition
    preview = product.application.preview_living_activity('share')
    assert preview.status == 'previewed' and 'current_feedback' not in preview.view['payload']
    assert act(product, 'share', 'integrated-revised-share-1').status == 'committed'
    assert fresh.calls[-1].payload == preview.view
    assert len(state(product)['shares']) == 2
    assert send(product, '说说新的取舍。', 'integrated-result-chat-1').status == 'terminal'
    assert fresh.calls[-1].payload['payload']['current_plan'] == asdict(state(product)['current_plan'])
    calls = len(fresh.calls)
    assert product.application.advance_living_activity(share_request).status == 'replayed'
    assert len(fresh.calls) == calls


@pytest.mark.parametrize('mode', ['history', 'source', 'context'])
def test_controls_filter_feedback_derived_plan_share_and_reply(integrated_fixture, mode):
    product, adapter = start(integrated_fixture, with_source=True)
    assert send(product, MESSAGE, 'integrated-dependent-edit').status == 'terminal'
    assert act(product, 'share', 'integrated-dependent-share').status == 'committed'
    assert send(product, '这个安排呢？', 'integrated-dependent-reply').status == 'terminal'
    if mode == 'history':
        product.application.set_reviewed_character_history(False)
    elif mode == 'source':
        assert select(product, '', None, 'integrated-source-disable').status == 'committed'
    else:
        from dynamic_subject_agent.whole_context_boundary import WholeContextBoundaryRequest
        assert product.application.apply_whole_context_boundary(WholeContextBoundaryRequest(
            product.profile_id,product.timeline_id,'integrated-new-context',0,True)).status == 'committed'
    preview = product.application.preview_natural_feedback('换一个话题。')
    assert preview.status == 'previewed'
    payload = preview.view['payload']
    assert payload['current_plan'] is None and payload['current_feedback'] is None
    assert payload['evidence']['latest_share'] is None and not payload['exchange']
    assert product.application.preview_living_activity('share').status == 'no-op'


def test_failed_chat_preserves_plan_and_next_chat_while_life_failure_requires_attention(integrated_fixture):
    product, adapter = start(integrated_fixture)
    original = state(product)['current_plan']; count = len(history(product))
    adapter.override = dict(intent='revise', reply_text='不能发表的合成回复。', activity_revision=1)
    assert send(product, MESSAGE, 'integrated-extra-field-fail').status == 'failed-closed'
    assert len(history(product)) == count and state(product)['current_plan'] == original
    assert not state(product)['permission']['needs_attention']
    adapter.override = None
    assert send(product, '那一处也改掉。', 'integrated-clarification-1').status == 'terminal'
    assert state(product)['current_plan'] == original
    adapter.fail = True
    assert act(product, key='integrated-life-failure-1').status == 'failed-closed'
    assert state(product)['permission']['needs_attention']
    adapter.fail = False
    assert send(product, '我们聊聊别的。', 'integrated-chat-after-life').status == 'terminal'


def test_nine_targets_are_not_silently_trimmed_or_retried(integrated_fixture):
    adapter = LocalAdapter(); adapter.plan = dict(PLAN, composition='松架。'*9)
    product = integrated_fixture(adapter)
    assert control(product, paused=False).status == 'committed'
    assert act(product).status == 'committed'
    original = state(product)['current_plan']; calls = len(adapter.calls)
    assert send(product, MESSAGE, 'integrated-nine-targets-1').status == 'failed-closed'
    assert len(adapter.calls) == calls + 1 and state(product)['current_plan'] == original


def test_local_composition_rejects_remote_before_identity_access():
    adapter = LocalAdapter()
    adapter.capabilities = ProviderCapabilities('deepseek', 'not-used', False, (StructuredOutputMode.JSON_OBJECT,))
    with pytest.raises(ValueError, match='LOCAL-only integrated'):
        open_integrated_character_product_local(None, gateway=ModelGateway(adapter), identity_id='not-opened')
    assert not adapter.calls


def test_actual_three_purpose_wire_previews_are_bounded_and_reject_extra_fields(integrated_fixture):
    from copy import deepcopy
    from dynamic_subject_agent.model_gateway import ModelTask
    from dynamic_subject_agent.integrated_character_remote_preview import integrated_remote_request_preview
    product, adapter = start(integrated_fixture)
    assert act(product, 'share', 'integrated-wire-share-1').status == 'committed'
    assert send(product, MESSAGE, 'integrated-wire-feedback').status == 'terminal'
    calls = len(adapter.calls)
    for task in adapter.calls:
        preview = integrated_remote_request_preview(task)
        assert preview['status'] == 'unapproved-preview-only'
        assert preview['body']['max_tokens'] == 4096 and preview['automatic_retries'] == 0
        assert preview['body']['thinking'] == {'type':'disabled'}
        assert len(preview['body']['messages']) == 2
        corrupted = deepcopy(task.payload)
        corrupted['payload']['internal_id'] = 'must-not-escape'
        with pytest.raises(ValueError):
            integrated_remote_request_preview(ModelTask(task.kind, corrupted))
    assert len(adapter.calls) == calls


@pytest.mark.parametrize('prepared', [False, True])
@pytest.mark.parametrize('kind', ['feedback', 'share'])
def test_interruption_recovers_one_combined_publication_without_model_or_nonce_resend(integrated_fixture, monkeypatch, prepared, kind):
    from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint, PublicationInterrupted
    product, adapter = start(integrated_fixture)
    request = action_request(product, 'share', 'integrated-interrupted-share')
    with monkeypatch.context() as crash:
        if prepared:
            original = TimelineEngine._hit
            def hit(self, point):
                if point is FaultPoint.AFTER_PLAN_CLAIM:
                    raise OSError('Synthetic interruption after combined preparation')
                return original(self, point)
            crash.setattr(TimelineEngine, '_hit', hit)
        else:
            crash.setattr(TimelineEngine, 'publish', lambda *a, **kw: (_ for _ in ()).throw(
                PublicationInterrupted('synthetic', 'Before combined preparation')))
        if kind == 'feedback':
            send(product, MESSAGE, 'integrated-interrupted-feedback')
        else:
            product.application.advance_living_activity(request)
    calls = len(adapter.calls)
    assert calls == 2
    product.close(); fresh = LocalAdapter(); product = integrated_fixture(fresh)
    assert not fresh.calls
    if kind == 'feedback':
        assert product.application.query_shared_activity().view['activity_revision'] == (2 if prepared else 1)
        assert not state(product)['permission']['needs_attention']
        assert send(product, MESSAGE, 'integrated-interrupted-feedback').status == ('terminal' if prepared else 'failed-closed')
    else:
        assert bool(state(product)['shares']) is prepared
        assert product.application.query_living_activity(request).status == ('replayed' if prepared else 'failed-closed')
        assert product.application.advance_living_activity(request).status == ('replayed' if prepared else 'failed-closed')
    assert not fresh.calls
