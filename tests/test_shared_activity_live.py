import json
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256

import pytest

from test_original_whole_chat import approved, personality_fixture, model_fixture, send, history
from test_shared_activity import select, step_request, LocalAdapter
from dynamic_subject_agent.local_product import open_shared_activity_product_live, open_shared_activity_product_local
from dynamic_subject_agent.shared_activity_live import ApprovedSharedActivityGrant, APPROVED_SHARED_REVIEW, open_shared_activity_audit, SharedActivityDelivery
from dynamic_subject_agent.shared_activity_remote_preview import PendingSharedActivityGrant, shared_remote_request_preview
from dynamic_subject_agent.model_gateway import ModelGateway, ModelTask, ModelTaskKind
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json


class SharedTransport(DeepSeekTransport):
    def __init__(self, fault=None):
        self.calls, self.fault = [], fault

    def post_json(self, **kwargs):
        body = json.loads(kwargs['body']); self.calls.append(body)
        if self.fault == 'timeout':
            raise TimeoutError('synthetic unknown delivery')
        if self.fault == 'credential':
            from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
            raise CharacterCredentialUnavailable()
        payload = json.loads(body['messages'][1]['content'])
        if 'current_activity' in payload:
            action = payload['current_activity']['allowed_actions'][0]
            value = dict(action=action, plan=dict(subject='静物', composition='留白' + str(len(self.calls)), focus='光线') if action in ('start', 'revise') else None,
                reason_code='balance-space', basis_refs=['E1'] if payload['shared_experience'] else [], decision_note='合成可见取舍。')
        else:
            value = dict(reply_text='合成已审批路径回复。', language='zh')
        return DeepSeekHttpResponse(200, canonical_json(dict(model='deepseek-flash',
            choices=[dict(finish_reason='stop', message=dict(role='assistant', content='' if self.fault == 'blank' else canonical_json(value)))],
            usage=dict(prompt_tokens=100, completion_tokens=20, total_tokens=120))).encode())


@pytest.fixture
def live_fixture(approved, monkeypatch, tmp_path):
    author, config, request, view = approved
    frozen = author.application.freeze_source_identity(request)
    assert frozen.status == 'created'; author.close()
    asset = json.loads(view.runtime_asset_json)
    import dynamic_subject_agent.original_whole_chat as module
    binding = dict(definition_basis=view.definition_basis, runtime_asset_sha=view.runtime_asset_sha,
        persona_digest=asset['persona_digest'], review_basis='1'*64, scope_digest='2'*64,
        subject_id=asset['subject']['subject_id'], anchor_id=asset['anchor']['anchor_id'])
    monkeypatch.setattr(module, 'APPROVED_BINDING', binding)
    import dynamic_subject_agent.shared_activity_live as live_module
    monkeypatch.setattr(live_module, 'APPROVED_SHARED_MATERIAL_DIGEST', live_module.digest(binding))
    options = dict(identity_id=frozen.view.identity_id, grant=ApprovedSharedActivityGrant(APPROVED_SHARED_REVIEW, True), audit_path=tmp_path/'live-shared-audit')
    opened = []
    def opening(transport=None, observations=None):
        product = open_shared_activity_product_live(config, **options, _transport=transport or SharedTransport(), observations=observations)
        opened.append(product)
        return product
    yield opening, config, options, binding
    for product in opened:
        product.close()


def test_live_facade_uses_exact_reviewed_wire_and_new_scope_audit_without_retries(live_fixture):
    opening, _, options, _ = live_fixture
    transport = SharedTransport(); observations = []; product = opening(transport, observations)
    assert not transport.calls and open_shared_activity_audit(options['audit_path']).counts() == (None, 0, None)
    assert send(product, '合成来源TOKEN留白。', 'live-source').status == 'terminal'
    assert select(product, 'TOKEN留白').status == 'committed'
    preview = product.application.preview_shared_activity_step().view
    request = step_request(product)
    result = product.application.advance_shared_activity(request)
    assert result.status == 'committed', result
    expected = shared_remote_request_preview(ModelTask(ModelTaskKind.SHARED_ACTIVITY_CHOICE, preview))
    assert transport.calls[-1] == expected['body']
    assert observations[-1]['wire_sha256'] == expected['wire_sha256']
    assert product.application.advance_shared_activity(request).status == 'replayed' and len(transport.calls) == 2
    result_plan = product.application.query_shared_activity().view['visible_result'].plan
    saved = history(product); product.close(); fresh = SharedTransport(); product = opening(fresh)
    assert not fresh.calls and history(product) == saved
    assert send(product, '请说说已提交结果。', 'live-result-followup').status == 'terminal'
    payload = json.loads(fresh.calls[0]['messages'][1]['content'])
    assert payload['evidence']['activity_result'] == dict(kind='composition-text', plan=asdict(result_plan))
    rows = open_shared_activity_audit(options['audit_path']).snapshot()
    assert len(rows) == 3 and [row['purpose'] for row in rows] == ['shared-activity-reply', 'shared-activity-choice', 'shared-activity-reply']
    assert {row['status'] for row in rows} == {'complete'}
    assert 'TOKEN' not in canonical_json(rows) and 'TOKEN' not in canonical_json(observations)


def test_unapproved_grant_and_local_identity_cannot_activate_live(live_fixture):
    _, config, options, binding = live_fixture
    transport = SharedTransport()
    with pytest.raises(ValueError):
        open_shared_activity_product_live(None, **dict(options, grant=PendingSharedActivityGrant(APPROVED_SHARED_REVIEW)), _transport=transport)
    assert not options['audit_path'].exists() and not transport.calls
    local = open_shared_activity_product_local(config, gateway=ModelGateway(LocalAdapter()), identity_id=options['identity_id'], binding=binding)
    local.close()
    before = config.state_path.read_bytes()
    with pytest.raises(RuntimeError):
        open_shared_activity_product_live(config, **options, _transport=transport)
    assert config.state_path.read_bytes() == before and not options['audit_path'].exists() and not transport.calls


def test_approved_review_does_not_follow_a_changed_original_material_binding(live_fixture, monkeypatch):
    _, config, options, _ = live_fixture
    import dynamic_subject_agent.original_whole_chat as module
    monkeypatch.setattr(module, 'APPROVED_BINDING', dict(module.APPROVED_BINDING, runtime_asset_sha='f'*64))
    transport = SharedTransport()
    with pytest.raises(ValueError, match='changed material binding'):
        open_shared_activity_product_live(config, **options, _transport=transport)
    assert not transport.calls and not options['audit_path'].exists()


@pytest.mark.parametrize('when', ['before-claim', 'after-claim'])
def test_scope_mutation_is_rebuilt_and_discarded_before_transport(live_fixture, monkeypatch, when):
    opening, _, options, _ = live_fixture
    transport = SharedTransport(); product = opening(transport)
    original = SharedActivityDelivery.claim
    def claim(self, operation, task, rebuild):
        changed = deepcopy(task.payload)
        changed['payload']['background']['runtime_identity']['subject_name'] = 'WRONG_SCOPE_SYNTHETIC'
        if when == 'before-claim':
            return original(self, operation, ModelTask(task.kind, changed), rebuild)
        original(self, operation, task, rebuild)
        # A second canonical read no longer matches the admitted request.
        from dataclasses import replace
        ticket = replace(self._ticket, rebuild=lambda: changed)
        self._ticket = self._pending = ticket
    with monkeypatch.context() as corrupt:
        corrupt.setattr(SharedActivityDelivery, 'claim', claim)
        result = send(product, '普通合成消息。', 'live-wrong-scope')
    assert result.status == 'failed-closed' and result.projection.failure_code == 'original-whole-delivery-unverified'
    assert not transport.calls
    rows = open_shared_activity_audit(options['audit_path']).snapshot()
    assert len(rows) == (0 if when == 'before-claim' else 1)
    if rows:
        assert rows[0]['status'] == 'failed-closed'


@pytest.mark.parametrize('fault, status, code', [('blank', 'failed-closed', 'response-content-empty'), ('timeout', 'unknown', 'transport-timeout'), ('credential', 'unavailable', 'character-credential-unavailable')])
def test_provider_failures_have_typed_audit_without_retry_or_activity_event(live_fixture, fault, status, code):
    opening, _, options, _ = live_fixture
    transport = SharedTransport(fault); product = opening(transport)
    result = send(product, '合成失败观察。', 'live-failure')
    assert result.status == status and result.projection.failure_code == 'original-whole-' + code
    repeated = send(product, '合成失败观察。', 'live-failure')
    assert repeated.status == result.status and repeated.operation_ref == result.operation_ref
    assert len(transport.calls) == 1
    assert len(open_shared_activity_audit(options['audit_path']).snapshot()) == 1
    assert open_shared_activity_audit(options['audit_path']).snapshot()[0]['status'] == status
    assert not history(product)


def test_live_prepared_choice_reopens_with_no_new_transport_and_exact_same_receipt(live_fixture, monkeypatch):
    from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint
    opening, _, options, _ = live_fixture
    transport = SharedTransport(); product = opening(transport)
    request = step_request(product)
    original = TimelineEngine._hit
    def hit(self, point):
        if point is FaultPoint.AFTER_PLAN_CLAIM:
            raise OSError('synthetic after approved response preparation')
        return original(self, point)
    with monkeypatch.context() as crash:
        crash.setattr(TimelineEngine, '_hit', hit)
        product.application.advance_shared_activity(request)
    product.close(); fresh = SharedTransport(); product = opening(fresh)
    assert len(transport.calls) == 1 and not fresh.calls
    assert product.application.advance_shared_activity(request).status == 'replayed'
    assert product.application.query_shared_activity().view['phase'] == 'drafted'
    assert len(open_shared_activity_audit(options['audit_path']).snapshot()) == 1


def test_authoritative_history_change_after_claim_discards_without_delivery(live_fixture, monkeypatch):
    opening, _, options, _ = live_fixture
    transport = SharedTransport(); product = opening(transport)
    original = SharedActivityDelivery.claim
    def claim(self, operation, task, rebuild):
        original(self, operation, task, rebuild)
        assert product.application.set_reviewed_character_history(False).history_enabled is False
    with monkeypatch.context() as changed:
        changed.setattr(SharedActivityDelivery, 'claim', claim)
        response = send(product, '本次权限变化。', 'live-after-claim-revoked')
    assert response.status == 'failed-closed' and response.projection.failure_code == 'original-whole-delivery-unverified'
    assert not transport.calls and open_shared_activity_audit(options['audit_path']).snapshot()[0]['status'] == 'failed-closed'


def test_live_final_publication_revision_change_cannot_publish_response(live_fixture, monkeypatch):
    from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint
    opening, _, options, _ = live_fixture
    transport = SharedTransport(); product = opening(transport)
    original = TimelineEngine._hit
    def changed(self, point):
        if point is FaultPoint.BEFORE_PUBLICATION_COMMIT:
            assert product.application.set_reviewed_character_history(False).history_enabled is False
            assert product.application.set_reviewed_character_history(True).history_enabled is True
        return original(self, point)
    with monkeypatch.context() as revoke:
        revoke.setattr(TimelineEngine, '_hit', changed)
        result = product.application.advance_shared_activity(step_request(product))
    assert result.status == 'failed-closed'
    assert product.application.query_shared_activity().view['result'] is None
    assert len(transport.calls) == 1 and len(open_shared_activity_audit(options['audit_path']).snapshot()) == 1


@pytest.mark.parametrize('fault, expected, code', [('timeout', 'unknown', 'original-whole-transport-timeout'),
    ('credential', 'unavailable', 'original-whole-character-credential-unavailable')])
def test_manual_activity_preserves_typed_failure_on_first_result_and_same_nonce(live_fixture, fault, expected, code):
    opening, _, options, _ = live_fixture
    transport = SharedTransport(fault); product = opening(transport)
    request = step_request(product)
    first = product.application.advance_shared_activity(request)
    assert first.status == expected and first.problem_code == code, first
    replay = product.application.advance_shared_activity(request)
    assert replay.status == expected and replay.problem_code == code, replay
    assert len(transport.calls) == 1 and len(open_shared_activity_audit(options['audit_path']).snapshot()) == 1
