"""S144 actual Facade behavior with synthetic transport, never character QA."""
from copy import deepcopy
import importlib
import json
from threading import Event, Thread

import pytest

from test_original_whole_chat import approved, personality_fixture, model_fixture, send, history
from test_living_activity import state, control, act, action_request
from test_living_activity_live import living_live_fixture, LivingTransport
from test_shared_activity import select
from test_whole_chat_archive import canonical_path
from dynamic_subject_agent.deepseek import DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.living_activity import living_policies, LivingClock, LivingPresenceRequest
from dynamic_subject_agent.living_activity_live import (LivingFinalTextDevelopmentGrant,
    FINAL_TEXT_DEVELOPMENT_AUTHORIZATION, APPROVED_LIVING_REVIEW, ApprovedLivingActivityGrant,
    open_living_activity_audit, LivingActivityDelivery, living_final_text_contract, digest)
from dynamic_subject_agent.local_product import open_living_activity_product_live, validate_living_activity_entry
from dynamic_subject_agent.model_gateway import ModelTaskKind, ModelTask
from dynamic_subject_agent.living_activity_remote_preview import living_remote_request_preview
from dynamic_subject_agent.shared_activity import LIVING_FINAL_TEXT_AUTHORITY


RAW = '  我想先比较留白。\n这样线条会更清楚。  '


class FinalTextTransport(LivingTransport):
    def __init__(self, fault=None):
        super().__init__(fault)
        self.text = RAW

    def post_json(self, **kwargs):
        response = super().post_json(**kwargs)
        body = self.calls[-1]
        payload = json.loads(response.body)
        if 'turn' in json.loads(body['messages'][1]['content']) and 'response_format' not in body:
            payload['choices'][0]['message']['content'] = ' \n\t' if self.fault == 'blank' else self.text
            payload['choices'][0]['message']['reasoning_content'] = 'discarded synthetic reasoning, never a reply'
        message = payload['choices'][0]['message']
        if self.fault == 'role':
            message['role'] = 'user'
        if self.fault == 'refusal':
            message['refusal'] = 'synthetic refusal'
        if self.fault == 'tools':
            message['tool_calls'] = [dict(id='synthetic')]
        if self.fault == 'length':
            payload['choices'][0]['finish_reason'] = 'length'
        if self.fault == 'typed-content':
            message['content'] = []
        if self.fault == 'delta':
            payload['choices'][0]['delta'] = dict(content='second synthetic body')
        if self.fault == 'second-final':
            message['final'] = 'second synthetic final body'
        if self.fault == 'empty-final':
            message['final'] = ''
        raw = canonical_json(payload).encode()
        if self.fault == 'duplicate':
            raw = raw[:-1] + b',"model":"deepseek-flash"}'
        if self.fault == 'malformed':
            raw = b'{'
        return DeepSeekHttpResponse(200, raw)


@pytest.fixture
def final_text_fixture(living_live_fixture):
    baseline_opening, config, options, binding = living_live_fixture
    options = dict(options, grant=LivingFinalTextDevelopmentGrant(APPROVED_LIVING_REVIEW,
        FINAL_TEXT_DEVELOPMENT_AUTHORIZATION), audit_path=options['audit_path'].with_name('s144-final-text-audit'))
    opened = []
    def opening(transport=None, observations=None, **kwargs):
        product = open_living_activity_product_live(config, **options,
            _transport=transport or FinalTextTransport(), observations=observations, **kwargs)
        opened.append(product)
        return product
    opening.baseline = baseline_opening
    yield opening, config, options, binding
    for product in opened:
        product.close()


def test_facade_original_text_one_stage_canonical_reopen_and_closed_old_grant(final_text_fixture):
    import sqlite3
    opening, config, options, binding = final_text_fixture
    transport = FinalTextTransport(); observations = []; product = opening(transport, observations)
    assert product._qri.provider_authority == LIVING_FINAL_TEXT_AUTHORITY
    assert not transport.calls and state(product)['permission']['paused'] is True
    with sqlite3.connect(canonical_path(product)) as db:
        assert db.execute('PRAGMA user_version').fetchone() == (6,)
    message = '合成当前构图问题。'
    preview = product.application.preview_living_activity('reply', message).view
    candidate = living_remote_request_preview(ModelTask(ModelTaskKind.LIVING_ACTIVITY_REPLY, preview), technical_variant='final-text')
    baseline_preview = dict(preview, policy=living_policies()[2])
    baseline = living_remote_request_preview(ModelTask(ModelTaskKind.LIVING_ACTIVITY_REPLY, baseline_preview))
    assert json.loads(candidate['body']['messages'][1]['content']) == json.loads(baseline['body']['messages'][1]['content'])
    assert 'response_format' not in candidate['body'] and baseline['body']['response_format'] == dict(type='json_object')
    assert 'reply_text' not in preview['policy'] and '合法JSON格式示例' not in preview['policy']
    assert send(product, message, 'final-text-first').status == 'terminal'
    assert len(transport.calls) == 1 and transport.calls[0] == candidate['body']
    assert history(product)[0].assistant_text == RAW
    rows = open_living_activity_audit(options['audit_path'], technical_variant='final-text').snapshot()
    assert len(rows) == 1 and rows[0]['output_digest'] == digest(dict(reply_text=RAW, language='zh'))
    assert observations[0]['status'] == 'complete' and observations[0]['wire_sha256'] == candidate['wire_sha256']
    assert RAW not in canonical_json(rows) and RAW not in canonical_json(observations)
    assert send(product, message, 'final-text-first').status == 'terminal' and len(transport.calls) == 1
    product.close(); fresh = FinalTextTransport(); product = opening(fresh)
    assert not fresh.calls and history(product)[0].assistant_text == RAW
    assert send(product, message, 'final-text-first').status == 'terminal' and not fresh.calls
    validate_living_activity_entry(config, profile_id=product.profile_id, timeline_id=product.timeline_id, technical_variant='final-text')
    with pytest.raises(RuntimeError):
        validate_living_activity_entry(config, profile_id=product.profile_id, timeline_id=product.timeline_id)
    with pytest.raises(RuntimeError, match='activation-conflict'):
        opening.baseline(FinalTextTransport())
    with pytest.raises(ValueError):
        open_living_activity_audit(options['audit_path'])
    with pytest.raises(ValueError):
        LivingActivityDelivery(grant=ApprovedLivingActivityGrant(APPROVED_LIVING_REVIEW, True),
            audit=open_living_activity_audit(options['audit_path'], technical_variant='final-text'),
            contract=living_final_text_contract(binding), state_path=config.state_path)


@pytest.mark.parametrize('fault,status,code', [
    ('blank', 'failed-closed', 'response-content-empty'),
    ('malformed', 'failed-closed', 'response-envelope'),
    ('duplicate', 'failed-closed', 'response-envelope'),
    ('refusal', 'failed-closed', 'response-envelope'),
    ('delta', 'failed-closed', 'response-envelope'),
    ('second-final', 'failed-closed', 'response-envelope'),
    ('tools', 'failed-closed', 'response-tools'),
    ('role', 'failed-closed', 'response-envelope'),
    ('typed-content', 'failed-closed', 'response-content-json'),
    ('length', 'failed-closed', 'response-truncated'),
    ('timeout', 'unknown', 'transport-timeout'),
    ('credential', 'unavailable', 'character-credential-unavailable'),
    ('oversize', 'failed-closed', 'expression-invalid'),
    ('nul', 'failed-closed', 'expression-invalid'),
])
def test_text_failure_is_typed_never_commits_reasons_or_retries(final_text_fixture, fault, status, code):
    opening, _, options, _ = final_text_fixture
    transport = FinalTextTransport(fault)
    if fault == 'oversize':
        transport.text = '字' * 1201
    if fault == 'nul':
        transport.text = '有正文\x00'
    product = opening(transport)
    result = send(product, '合成当前问题。', 'failed-final-text')
    assert result.status == status and len(transport.calls) == 1
    assert result.projection.failure_code == 'original-whole-' + code
    permission = product.application.query_living_controls().view
    assert permission['paused'] is True and permission['needs_attention'] is True
    rows = open_living_activity_audit(options['audit_path'], technical_variant='final-text').snapshot()
    assert len(rows) == 1 and rows[0]['status'] == status and rows[0]['output_digest'] is None
    if status != 'unknown':
        assert history(product) == ()
    product.close(); fresh = FinalTextTransport(); product = opening(fresh)
    assert send(product, '合成当前问题。', 'failed-final-text').status == status and not fresh.calls


def test_choice_share_json_two_complete_followups_then_filter_whole_s1_window(final_text_fixture):
    opening, _, options, _ = final_text_fixture
    transport = FinalTextTransport(); product = opening(transport)
    assert send(product, '初始合成独立话题。', 'initial').status == 'terminal'
    assert control(product, paused=False, sharing=True).status == 'committed'
    assert act(product).status == 'committed'
    choice_preview = product.application.preview_living_activity('choice').view
    choice_task = ModelTask(ModelTaskKind.LIVING_ACTIVITY_CHOICE, choice_preview)
    assert living_remote_request_preview(choice_task, technical_variant='final-text')['body'] == living_remote_request_preview(choice_task)['body']
    shared = act(product, 'share', 'candidate-share-request-1')
    assert shared.status == 'committed', shared
    shares = state(product)['shares']; assert len(shares) == 1
    assert all(call['response_format'] == dict(type='json_object') for call in transport.calls[1:])
    assert '只选这版方案' in transport.calls[-1]['messages'][0]['content']
    product.close(); fresh = FinalTextTransport(); product = opening(fresh)
    for index in range(3):
        message = '说说这个安排。' if index < 2 else '换个话题聊线条。'
        preview = product.application.preview_living_activity('reply', message).view
        assert preview['payload']['evidence']['latest_share'] == (dict(text=shares[0]['text']) if index < 2 else None)
        exchange = preview['payload']['exchange']
        if index == 2:
            # The most recent two complete turns were both S1-dependent. The
            # existing window does not backfill the earlier independent turn.
            assert exchange == ()
            assert preview['payload']['turn']['has_prior_committed_exchange'] is True
        assert send(product, message, 'followup-' + str(index)).status == 'terminal'
        assert 'response_format' not in fresh.calls[-1]
        assert history(product)[-1].assistant_text == RAW
    assert len(open_living_activity_audit(options['audit_path'], technical_variant='final-text').snapshot()) == 6


@pytest.mark.parametrize('change', ['disable', 'history-off', 'cutoff'])
def test_final_text_source_history_cutoff_filters_derived_evidence_after_reopen(final_text_fixture, change):
    opening, _, _, _ = final_text_fixture
    product = opening()
    assert send(product, '合成来源：桌边留白。', 'source').status == 'terminal'
    selected = select(product, '桌边留白', head=history(product)[0].head_sequence, key='candidate-source-selected-1')
    assert selected.status == 'committed', selected
    assert control(product, paused=False, sharing=True).status == 'committed'
    assert act(product).status == 'committed'
    assert act(product, 'share', 'candidate-source-share-1').status == 'committed'
    assert send(product, '这次构图安排呢？', 'derived').status == 'terminal'
    if change == 'disable':
        assert select(product, '', None, 'candidate-source-disabled-1').status == 'committed'
    elif change == 'history-off':
        assert product.application.set_reviewed_character_history(False).history_enabled is False
    else:
        from dynamic_subject_agent.whole_context_boundary import WholeContextBoundaryRequest
        assert product.application.apply_whole_context_boundary(WholeContextBoundaryRequest(product.profile_id,
            product.timeline_id, 'candidate-context-cutoff-1', 0, True)).status == 'committed'
    product.close(); fresh = FinalTextTransport(); product = opening(fresh)
    assert not fresh.calls
    assert send(product, '现在换个话题。', 'after-filter').status == 'terminal'
    payload = json.loads(fresh.calls[-1]['messages'][1]['content'])
    assert payload['evidence'] == dict(shared_experience=None, activity_result=None, latest_share=None)
    assert payload['exchange'] == [] and payload['turn']['has_prior_committed_exchange'] is True


def test_pending_presence_keeps_prior_seconds_without_publication(final_text_fixture):
    opening, config, _, _ = final_text_fixture
    now = [0.0]; entered, release = Event(), Event(); transport = FinalTextTransport()
    product = opening(transport, clock=LivingClock(lambda: now[0]))
    path = canonical_path(product)
    assert control(product, paused=False, sharing=False).status == 'committed'
    request = LivingPresenceRequest(product.profile_id, product.timeline_id, 'candidate-presence-session')
    assert product.application.heartbeat_living_presence(request).status == 'available'
    now[0] = 10.0
    assert product.application.heartbeat_living_presence(request).status == 'available'
    def pending():
        entered.set(); assert release.wait(20)
    transport.callback = pending
    results = []
    thread = Thread(target=lambda: results.append(send(product, '合成等待问题。', 'pending'))); thread.start()
    assert entered.wait(10)
    before = config.state_path.read_bytes(), path.read_bytes()
    for _ in range(4):
        now[0] += 5
        pulse = product.application.heartbeat_living_presence(request)
        assert pulse.status == 'available' and pulse.view['online_seconds'] == now[0]
    assert len(transport.calls) == 1 and (config.state_path.read_bytes(), path.read_bytes()) == before
    release.set(); thread.join(20)
    assert results[0].status == 'terminal' and history(product)[0].assistant_text == RAW


def test_final_text_empty_marker_exact_limit_and_permission_change_fence(final_text_fixture, monkeypatch):
    opening, config, options, _ = final_text_fixture
    transport = FinalTextTransport('empty-final'); transport.text = '字' * 1200
    product = opening(transport)
    assert send(product, '合成长度上界。', 'limit-boundary').status == 'terminal'
    assert history(product)[0].assistant_text == transport.text
    from dynamic_subject_agent.living_activity import LivingControlRequest
    permission = product.application.query_living_controls().view
    request = LivingControlRequest(product.profile_id, product.timeline_id, 'candidate-change-permission-1',
        permission['revision'], False, False, True)
    def change_permission():
        assert product.application.set_living_controls(request).status == 'committed'
    transport.callback = change_permission
    result = send(product, '合成权限变更。', 'permission-race')
    assert result.status == 'failed-closed' and len(transport.calls) == 2
    assert len(history(product)) == 1
    assert open_living_activity_audit(options['audit_path'], technical_variant='final-text').snapshot()[-1]['status'] == 'complete'
    # Provider delivery completion is distinct from Python Publication.
    assert product.application.query_living_controls().view['needs_attention'] is True


def test_final_text_pins_do_not_follow_mutated_builder(final_text_fixture, monkeypatch):
    opening, config, options, _ = final_text_fixture
    live = importlib.import_module('dynamic_subject_agent.living_activity_live')
    before = config.state_path.read_bytes(); transport = FinalTextTransport()
    with monkeypatch.context() as altered:
        policies = live.living_policies
        altered.setattr(live, 'living_policies', lambda variant='baseline':
            (*policies(variant)[:2], policies(variant)[2] + 'changed'))
        with pytest.raises(ValueError, match='policy'):
            opening(transport)
    with monkeypatch.context() as altered:
        protocol = live.living_protocol_for_kind
        altered.setattr(live, 'living_protocol_for_kind', lambda *a, **kw: dict(protocol(*a, **kw), timeout_seconds=31))
        with pytest.raises(ValueError, match='protocol'):
            opening(transport)
    assert config.state_path.read_bytes() == before and not options['audit_path'].exists() and not transport.calls


@pytest.mark.parametrize('root_kind', ['baseline', 'local'])
def test_old_json_reply_and_local_roots_cannot_convert_to_final_text(final_text_fixture, root_kind):
    opening, config, options, binding = final_text_fixture
    raw = LivingTransport()
    if root_kind == 'baseline':
        raw.override = 'ordinary raw text in old JSON protocol'
        old = opening.baseline(raw)
        result = send(old, '合成旧JSON当前问题。', 'old-json-text-rejected')
        assert result.status == 'failed-closed' and result.projection.failure_code == 'original-whole-response-content-json'
        assert history(old) == () and len(raw.calls) == 1
    else:
        from test_living_activity import LocalAdapter
        from dynamic_subject_agent.local_product import open_living_activity_product_local
        from dynamic_subject_agent.model_gateway import ModelGateway
        old = open_living_activity_product_local(config, identity_id=options['identity_id'], binding=binding,
            gateway=ModelGateway(LocalAdapter()))
        assert not raw.calls
    old.close(); before = config.state_path.read_bytes(); transport = FinalTextTransport()
    with pytest.raises(RuntimeError, match='activation-conflict'):
        opening(transport)
    assert config.state_path.read_bytes() == before and not options['audit_path'].exists() and not transport.calls


@pytest.mark.parametrize('prepared', [False, True])
def test_final_text_cold_prepared_publication_preserves_original_without_model(final_text_fixture, monkeypatch, prepared):
    from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint, PublicationInterrupted
    opening, _, options, _ = final_text_fixture
    transport = FinalTextTransport(); product = opening(transport)
    with monkeypatch.context() as crash:
        if prepared:
            original = TimelineEngine._hit
            def hit(self, point):
                if point is FaultPoint.AFTER_PLAN_CLAIM:
                    raise OSError('synthetic interrupted durable final text')
                return original(self, point)
            crash.setattr(TimelineEngine, '_hit', hit)
        else:
            crash.setattr(TimelineEngine, 'publish', lambda *a, **kw: (_ for _ in ()).throw(PublicationInterrupted('synthetic', 'unprepared')))
        send(product, '合成恢复问题。', 'cold')
    assert len(transport.calls) == 1
    product.close(); fresh = FinalTextTransport(); product = opening(fresh)
    result = send(product, '合成恢复问题。', 'cold')
    assert result.status == ('terminal' if prepared else 'failed-closed') and not fresh.calls
    assert (history(product)[0].assistant_text if prepared else '') == (RAW if prepared else '')
    assert len(open_living_activity_audit(options['audit_path'], technical_variant='final-text').snapshot()) == 1
