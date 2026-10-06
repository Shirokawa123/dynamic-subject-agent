"""Approved S142 delivery tests use a synthetic transport and never load keys."""
import json
from copy import deepcopy
from hashlib import sha256
from threading import Thread

import pytest

from test_original_whole_chat import approved, personality_fixture, model_fixture, send, history
from test_living_activity import state, control, act, action_request, LocalAdapter
from dynamic_subject_agent.local_product import open_living_activity_product_live, open_living_activity_product_local
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelGateway, ModelTask, ModelTaskKind, ModelGatewayFailure
from dynamic_subject_agent.living_activity_live import (
    ApprovedLivingActivityGrant, APPROVED_LIVING_REVIEW, LivingActivityDelivery, open_living_activity_audit)
from dynamic_subject_agent.living_activity_remote_preview import PendingLivingActivityGrant, living_remote_request_preview


class LivingTransport(DeepSeekTransport):
    def __init__(self, fault=None):
        self.calls, self.fault, self.callback, self.override = [], fault, None, None

    def post_json(self, **kwargs):
        body = json.loads(kwargs['body']); self.calls.append(body)
        if self.callback:
            self.callback()
        if self.fault == 'timeout':
            raise TimeoutError('synthetic private transport detail')
        if self.fault == 'credential':
            from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
            raise CharacterCredentialUnavailable()
        payload = json.loads(body['messages'][1]['content'])
        if 'current_activity' in payload:
            action = payload['current_activity']['allowed_actions'][0]
            value = dict(action=action, plan=dict(subject='静物', composition='合成留白'+str(len(self.calls)), focus='光线') if action in ('start', 'revise') else None,
                reason_code='balance-space', basis_refs=['E1'] if payload['shared_experience'] else [], decision_note='合成可见取舍。')
        elif 'turn' in payload:
            value = dict(reply_text='合成已批准路径回复。', language='zh')
        else:
            value = dict(share=True, reply_text='合成分享：我把留白写成了这版文字方案。', language='zh')
        if self.override is not None:
            value = self.override
        return DeepSeekHttpResponse(200, canonical_json(dict(model='deepseek-flash',
            choices=[dict(finish_reason='stop', message=dict(role='assistant', content='' if self.fault == 'blank' else canonical_json(value)))],
            usage=dict(prompt_tokens=100, completion_tokens=20, total_tokens=120))).encode())


@pytest.fixture
def living_live_fixture(approved, monkeypatch, tmp_path):
    author, config, request, view = approved
    frozen = author.application.freeze_source_identity(request)
    assert frozen.status == 'created'; author.close()
    asset = json.loads(view.runtime_asset_json)
    import dynamic_subject_agent.original_whole_chat as module
    binding = dict(definition_basis=view.definition_basis, runtime_asset_sha=view.runtime_asset_sha,
        persona_digest=asset['persona_digest'], review_basis='1'*64, scope_digest='2'*64,
        subject_id=asset['subject']['subject_id'], anchor_id=asset['anchor']['anchor_id'])
    monkeypatch.setattr(module, 'APPROVED_BINDING', binding)
    import dynamic_subject_agent.living_activity_live as live
    monkeypatch.setattr(live, 'APPROVED_LIVING_MATERIAL_DIGEST', live.digest(binding))
    from dynamic_subject_agent.living_activity import living_contract
    monkeypatch.setattr(live, 'APPROVED_LIVING_LOCAL_CONTRACT_SHA', live.digest(living_contract(binding)))
    options = dict(identity_id=frozen.view.identity_id, grant=ApprovedLivingActivityGrant(APPROVED_LIVING_REVIEW, True), audit_path=tmp_path/'s142-live-audit')
    opened = []
    def opening(transport=None, observations=None, **kwargs):
        product = open_living_activity_product_live(config, **options, _transport=transport or LivingTransport(), observations=observations, **kwargs)
        opened.append(product)
        return product
    yield opening, config, options, binding
    for product in opened:
        product.close()


def test_independent_live_chain_exact_three_wires_reopen_and_share_window(living_live_fixture):
    opening, _, options, _ = living_live_fixture
    transport = LivingTransport(); observations = []; product = opening(transport, observations)
    assert not transport.calls and open_living_activity_audit(options['audit_path']).counts() == (None, 0, None)
    assert product.application.reviewed_character_chat_status().status == 'active'
    assert state(product)['permission']['paused'] is True
    assert control(product, paused=False, sharing=True).status == 'committed'
    assert act(product, 'manual', 'live-manual-outside-approved-trigger-1').status == 'unavailable'
    assert not transport.calls
    preview = product.application.preview_living_activity('choice').view
    assert act(product).status == 'committed'
    expected = living_remote_request_preview(ModelTask(ModelTaskKind.LIVING_ACTIVITY_CHOICE, preview))
    assert transport.calls[-1] == expected['body'] and observations[-1]['wire_sha256'] == expected['wire_sha256']
    preview = product.application.preview_living_activity('share').view
    share_request = action_request(product, 'share', 'live-living-share-once-1')
    assert product.application.advance_living_activity(share_request).status == 'committed'
    assert transport.calls[-1] == living_remote_request_preview(ModelTask(ModelTaskKind.LIVING_ACTIVITY_SHARE, preview))['body']
    assert product.application.advance_living_activity(share_request).status == 'replayed'
    shares = state(product)['shares']; assert len(shares) == 1 and history(product) == ()
    product.close(); fresh = LivingTransport(); product = opening(fresh)
    assert not fresh.calls and state(product)['shares'] == shares
    for index in range(3):
        preview = product.application.preview_living_activity('reply', '说说这个文字方案。').view
        assert send(product, '说说这个文字方案。', 'live-living-followup-'+str(index)).status == 'terminal'
        expected = living_remote_request_preview(ModelTask(ModelTaskKind.LIVING_ACTIVITY_REPLY, preview))
        assert fresh.calls[-1] == expected['body']
        payload = json.loads(fresh.calls[-1]['messages'][1]['content'])
        assert payload['evidence']['latest_share'] == (dict(text=shares[0]['text']) if index < 2 else None)
        if index == 2:
            assert payload['exchange'] == []
    rows = open_living_activity_audit(options['audit_path']).snapshot()
    assert len(rows) == 5 and [row['purpose'] for row in rows] == ['living-activity-choice', 'living-activity-share', *['living-activity-reply']*3]
    assert {row['status'] for row in rows} == {'complete'}
    assert '合成' not in canonical_json(rows) and '合成' not in canonical_json(observations)


def test_pending_local_and_changed_material_do_not_activate_live(living_live_fixture, monkeypatch):
    _, config, options, binding = living_live_fixture
    transport = LivingTransport()
    with pytest.raises(ValueError):
        open_living_activity_product_live(None, **dict(options, grant=PendingLivingActivityGrant(APPROVED_LIVING_REVIEW)), _transport=transport)
    assert not options['audit_path'].exists() and not transport.calls
    import dynamic_subject_agent.original_whole_chat as module
    with monkeypatch.context() as changed:
        changed.setattr(module, 'APPROVED_BINDING', dict(binding, runtime_asset_sha='f'*64))
        with pytest.raises(ValueError, match='material'):
            open_living_activity_product_live(config, **options, _transport=transport)
    local = open_living_activity_product_local(config, gateway=ModelGateway(LocalAdapter()), identity_id=options['identity_id'], binding=binding)
    local.close(); before = config.state_path.read_bytes()
    with pytest.raises(RuntimeError, match='activation-conflict'):
        open_living_activity_product_live(config, **options, _transport=transport)
    assert config.state_path.read_bytes() == before and not options['audit_path'].exists() and not transport.calls


def test_policy_and_protocol_pins_do_not_follow_changed_source(living_live_fixture, monkeypatch):
    opening, config, options, _ = living_live_fixture
    transport = LivingTransport(); before = config.state_path.read_bytes()
    import dynamic_subject_agent.living_activity_live as live
    with monkeypatch.context() as altered:
        altered.setattr(live, 'SHARE_POLICY', live.SHARE_POLICY+'changed')
        with pytest.raises(ValueError, match='policy'):
            opening(transport)
    with monkeypatch.context() as altered:
        original = live.current_living_protocol
        altered.setattr(live, 'current_living_protocol', lambda: dict(original(), timeout_seconds=31))
        with pytest.raises(ValueError, match='protocol'):
            opening(transport)
    assert config.state_path.read_bytes() == before and not options['audit_path'].exists() and not transport.calls


@pytest.mark.parametrize('fault,status,code', [('blank','failed-closed','response-content-empty'), ('timeout','unknown','transport-timeout'), ('credential','unavailable','character-credential-unavailable')])
def test_live_technical_failure_keeps_typed_audit_and_stops_without_retry(living_live_fixture, fault, status, code):
    opening, _, options, _ = living_live_fixture
    transport = LivingTransport(fault); product = opening(transport)
    assert control(product, paused=False, sharing=True).status == 'committed'
    request = action_request(product)
    result = product.application.advance_living_activity(request)
    assert result.status == status and result.problem_code == 'original-whole-'+code
    assert product.application.advance_living_activity(request).status == status
    assert len(transport.calls) == 1
    if status == 'unknown':
        assert product.application.query_living_activity().status == 'failed-closed'
    else:
        assert state(product)['visible_result'] is None
    permission = product.application.query_living_controls()
    assert permission.status == 'available' and permission.view['needs_attention'] is True and permission.view['paused'] is True
    rows = open_living_activity_audit(options['audit_path']).snapshot()
    assert len(rows) == 1 and rows[0]['status'] == status


@pytest.mark.parametrize('prepared', [False, True])
def test_live_cold_prepared_or_unprepared_never_repeat_transport(living_live_fixture, monkeypatch, prepared):
    from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint, PublicationInterrupted
    opening, _, options, _ = living_live_fixture
    transport = LivingTransport(); product = opening(transport)
    assert control(product, paused=False, sharing=True).status == 'committed'
    request = action_request(product)
    with monkeypatch.context() as crash:
        if prepared:
            original = TimelineEngine._hit
            def hit(self, point):
                if point is FaultPoint.AFTER_PLAN_CLAIM:
                    raise OSError('synthetic durable live preparation interruption')
                return original(self, point)
            crash.setattr(TimelineEngine, '_hit', hit)
        else:
            crash.setattr(TimelineEngine, 'publish', lambda *a, **k: (_ for _ in ()).throw(PublicationInterrupted('synthetic','before preparation')))
        product.application.advance_living_activity(request)
    assert len(transport.calls) == 1
    product.close(); fresh = LivingTransport(); product = opening(fresh)
    assert not fresh.calls and (state(product)['visible_result'] is not None) is prepared
    assert product.application.advance_living_activity(request).status == ('replayed' if prepared else 'failed-closed')
    assert not fresh.calls and len(open_living_activity_audit(options['audit_path']).snapshot()) == 1


def test_tickets_require_same_client_thread_kind_and_never_repeat(living_live_fixture):
    from dynamic_subject_agent.living_activity_live import living_live_contract
    from dynamic_subject_agent.living_activity_provider import DeepSeekLivingActivityAdapter
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID
    opening, config, options, binding = living_live_fixture
    product = opening()
    payload = product.application.preview_living_activity('choice').view
    task = ModelTask(ModelTaskKind.LIVING_ACTIVITY_CHOICE, payload)
    audit = open_living_activity_audit(options['audit_path'])
    transport = LivingTransport()
    def client():
        delivery = LivingActivityDelivery(grant=options['grant'], audit=audit, contract=living_live_contract(binding), state_path=config.state_path)
        adapter = DeepSeekLivingActivityAdapter(transport=transport, delivery=delivery,
            credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID))
        return delivery, ModelGateway(adapter)
    first, gateway = client()
    first.claim('synthetic-kind-ticket-1', task, lambda: deepcopy(payload))
    with pytest.raises(ModelGatewayFailure, match='delivery-unverified'):
        gateway.execute(ModelTask(ModelTaskKind.LIVING_ACTIVITY_REPLY, payload))
    assert not transport.calls and audit.snapshot()[-1]['status'] == 'failed-closed'
    owner, gateway = client(); other, other_gateway = client()
    owner.claim('synthetic-client-ticket-2', task, lambda: deepcopy(payload))
    with pytest.raises(ModelGatewayFailure, match='delivery-unverified'):
        other_gateway.execute(task)
    assert not transport.calls
    assert gateway.execute(task).kind is task.kind
    with pytest.raises(ModelGatewayFailure, match='delivery-unverified'):
        gateway.execute(task)
    with pytest.raises(ValueError, match='already claimed'):
        other.claim('synthetic-client-ticket-2', task, lambda: deepcopy(payload))
    assert len(transport.calls) == 1
    threaded, gateway = client()
    threaded.claim('synthetic-thread-ticket-3', task, lambda: deepcopy(payload))
    errors = []
    def consume_elsewhere():
        try:
            threaded.consume(task)
        except ValueError as error:
            errors.append(str(error))
    worker = Thread(target=consume_elsewhere); worker.start(); worker.join()
    assert errors
    with pytest.raises(ModelGatewayFailure, match='delivery-unverified'):
        gateway.execute(task)
    assert len(transport.calls) == 1 and audit.snapshot()[-1]['status'] == 'failed-closed'


@pytest.mark.parametrize('changed', ['permission', 'source', 'day', 'payload'])
def test_claimed_scope_changes_are_rebuilt_and_rejected_before_transport(living_live_fixture, monkeypatch, changed):
    from dataclasses import replace
    from dynamic_subject_agent.shared_activity import SharedExperienceRequest
    opening, _, options, _ = living_live_fixture
    day = ['2026-10-06']; transport = LivingTransport(); product = opening(transport, day=lambda: day[0])
    assert control(product, paused=False, sharing=True).status == 'committed'
    if changed == 'day':
        assert act(product).status == 'committed'
    before_calls = len(transport.calls); revision = state(product)['revision']; permission = state(product)['permission']
    original = LivingActivityDelivery.claim
    def mutate(self, operation, task, rebuild):
        original(self, operation, task, rebuild)
        if changed == 'permission':
            from dynamic_subject_agent.living_activity import LivingControlRequest
            result = product.application.set_living_controls(LivingControlRequest(product.profile_id, product.timeline_id,
                'live-scope-pause-after-claim-1', permission['revision'], paused=True, confirmed=True))
            assert result.status == 'committed'
        elif changed == 'source':
            response = product.application.set_shared_experience(SharedExperienceRequest(product.profile_id, product.timeline_id,
                'live-scope-source-after-claim-1', revision, None, '', True))
            assert response.status == 'busy'
        elif changed == 'day':
            day[0] = '2026-10-07'
        else:
            bad = deepcopy(task.payload)
            bad['payload']['background']['runtime_identity']['subject_name'] = 'WRONG_SCOPE_SYNTHETIC'
            self._ticket = self._pending = replace(self._ticket, rebuild=lambda: bad)
    with monkeypatch.context() as altered:
        altered.setattr(LivingActivityDelivery, 'claim', mutate)
        result = act(product, 'share' if changed == 'day' else 'simulation', 'live-scope-changed-at-consume-1')
    assert result.status == 'failed-closed' and result.problem_code == 'original-whole-delivery-unverified'
    assert len(transport.calls) == before_calls
    controls = product.application.query_living_controls()
    assert controls.status == 'available' and controls.view['needs_attention'] is True
    assert open_living_activity_audit(options['audit_path']).snapshot()[-1]['status'] == 'failed-closed'


def test_closed_live_payload_and_dynamic_endpoint_slot_cannot_expand_the_pin(living_live_fixture, monkeypatch):
    from dynamic_subject_agent.living_activity_live import validate_living_request_payload
    opening, _, options, _ = living_live_fixture
    product = opening(); preview = product.application.preview_living_activity('choice').view
    bad = deepcopy(preview); bad['payload']['publication_timestamp'] = 'PRIVATE_SYNTHETIC'
    with pytest.raises(ValueError, match='fields'):
        validate_living_request_payload(ModelTask(ModelTaskKind.LIVING_ACTIVITY_CHOICE, bad))
    from dynamic_subject_agent import deepseek, credentials
    with monkeypatch.context() as changed:
        changed.setattr(deepseek, 'DEEPSEEK_ENDPOINT', 'https://wrong.invalid')
        with pytest.raises(ValueError, match='protocol'):
            options['grant'].validate()
    from dataclasses import replace
    with monkeypatch.context() as changed:
        changed.setattr(credentials, 'DEEPSEEK_CREDENTIAL_SLOT', replace(credentials.DEEPSEEK_CREDENTIAL_SLOT, account_id='other'))
        with pytest.raises(ValueError, match='protocol'):
            options['grant'].validate()
