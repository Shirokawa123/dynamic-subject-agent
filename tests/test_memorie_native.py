"""Facade/production tests with explicit private definition and synthetic transport."""
from dataclasses import replace
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3

import pytest

from dynamic_subject_agent.application import SubjectRequestLookupRequest
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product, open_memorie_native_product, open_memorie_companion_product
from dynamic_subject_agent.memorie_companion_contract import DEFINITION
from dynamic_subject_agent.memorie_native import NativeInteractionInput, NativeCallAudit
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
from dynamic_subject_agent.source_character_authoring import LocalIdentitySelectRequest


class Transport(DeepSeekTransport):
    def __init__(self, fault=None): self.calls, self.fault = [], fault
    def post_json(self, **kwargs):
        self.calls.append(kwargs)
        if self.fault == 'timeout': raise TimeoutError('synthetic ambiguous delivery')
        if self.fault == 'credential':
            from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
            raise CharacterCredentialUnavailable()
        value = '甲' * 121 if self.fault == 'oversized' else '合成短回应。'
        return DeepSeekHttpResponse(200, canonical_json(dict(model='deepseek-flash', choices=[dict(
            finish_reason='length' if self.fault == 'length' else 'stop',
            message=dict(role='assistant', content=value, reasoning_content='NEVER_RETAIN_REASONING'))],
            usage=dict(prompt_tokens=100, completion_tokens=12))).encode())


@pytest.fixture
def native(tmp_path):
    private = Path(os.environ.get('MEMORIE_NATIVE_QUALIFICATION', 'missing-native-qualification'))
    if not (private / 'native-approval.json').is_file(): pytest.skip('explicit private native qualification required')
    preparation = json.loads((private / 'preparation.json').read_bytes())
    config = LocalProductConfig(tmp_path / 'product/m0/experiments', tmp_path / 'product/state.json')
    with open_local_product(config, cognition=DormantDeepSeekCognition()) as dormant:
        frozen = dormant.application.freeze_source_identity(ReviewedCharacterFreezeRequest(preparation['definition_json'], DEFINITION, True, True))
        assert frozen.status == 'created', frozen
        assert dormant.application.select_local_identity(LocalIdentitySelectRequest(frozen.view.identity_id, True)).status == 'selected'
    opened = []
    def opening(transport=None):
        product = open_memorie_native_product(config, approval_path=private / 'native-approval.json',
            audit_path=tmp_path / 'native-audit', _transport=transport or Transport())
        opened.append(product)
        return product
    yield opening, config, private, tmp_path
    for product in opened: product.close()


def command(product, interaction=None, phase='idle'):
    return NativeInteractionInput(product.profile_id, product.timeline_id,
        canonical_json(interaction or {'kind': 'character-click'}),
        canonical_json(None if phase is None else {'timer_phase': phase}))


def send(product, value, key):
    result = product.application.submit(value, idempotency_key='native-test-request-' + key)
    if result.status == 'pending': result = product.application.wait(result.operation_ref, timeout_seconds=30)
    return result


def payload(call): return json.loads(json.loads(call['body'])['messages'][1]['content'])


def test_native_qualification_has_typed_unavailable_activity_without_model(native):
    opening,_,_,_=native
    transport=Transport()
    with opening(transport) as product:
        shared=product.application.query_shared_activity()
        assert shared.status=='unavailable' and shared.problem_code=='independent-shared-authority-required'
        assert shared.view is None and shared.receipt is None
        assert product.application.query_living_activity().status=='unavailable'
        assert not transport.calls


def test_typed_click_text_same_timeline_restart_exact_request_and_no_fake_speech(native):
    opening, _, private, root = native
    transport = Transport(); product = opening(transport)
    assert product.application.reviewed_character_chat_status().status == 'active' and not transport.calls
    first = command(product)
    result = send(product, first, 'first')
    assert result.status == 'terminal', result
    assert payload(transport.calls[0])['interaction'] == {'kind': 'character-click'}
    assert payload(transport.calls[0])['situation'] == {'timer_phase': 'idle'}
    assert payload(transport.calls[0])['exchange'] == []
    assert len(transport.calls) == 1
    assert send(product, first, 'first').replayed and len(transport.calls) == 1
    history = product.application.query_memorie_interactions()
    assert history.status == 'available' and len(history.turns) == 1
    assert json.loads(history.turns[0].interaction_json) == {'kind': 'character-click'}
    scope = product.profile_id, product.timeline_id
    product.close()
    second_transport = Transport(); restarted = opening(second_transport)
    assert (restarted.profile_id, restarted.timeline_id) == scope
    lookup = restarted.application.lookup_subject_request(SubjectRequestLookupRequest(first, 'native-test-request-first'))
    assert lookup.query_status == 'found' and lookup.operation.status == 'terminal', lookup
    assert not second_transport.calls
    followup = command(restarted, {'kind': 'text', 'text': '刚才点你时，你说了什么？'}, 'rest')
    assert send(restarted, followup, 'followup').status == 'terminal'
    assert payload(second_transport.calls[0])['exchange'] == [dict(interaction={'kind': 'character-click'}, assistant_text='合成短回应。')]
    assert restarted.application.set_reviewed_character_history(False).history_enabled is False
    assert send(restarted, command(restarted, {'kind': 'text', 'text': '只聊当前。'}, None), 'off').status == 'terminal'
    assert payload(second_transport.calls[1])['exchange'] == []
    assert NativeCallAudit(root / 'native-audit').counts() == (None, 3, None)


@pytest.mark.parametrize('fault,status', [('timeout','unknown'), ('credential','unavailable'), ('length','failed-closed'), ('oversized','failed-closed')])
def test_failure_is_terminal_without_publication_or_model_redelivery(native, fault, status):
    opening, _, _, _ = native
    transport = Transport(fault); product = opening(transport)
    value = command(product)
    result = send(product, value, 'failure')
    assert result.status == status, result
    assert not product.application.query_memorie_interactions().turns and len(transport.calls) == 1
    product.close()
    after = Transport(); restarted = opening(after)
    assert send(restarted, value, 'failure').status == status and not after.calls


def test_old_root_is_not_upgraded_and_old_approval_does_not_qualify(native):
    _, config, private, root = native
    old = open_memorie_companion_product(config, approval_path=private / 'approval.json', audit_path=root / 'old-audit', _transport=Transport())
    old.close()
    before = config.state_path.read_bytes()
    with pytest.raises(RuntimeError, match='activation-conflict'):
        open_memorie_native_product(config, approval_path=private / 'native-approval.json', audit_path=root / 'native-audit', _transport=Transport())
    assert config.state_path.read_bytes() == before and not (root / 'native-audit').exists()
    with pytest.raises(ValueError):
        open_memorie_native_product(config, approval_path=private / 'approval.json', audit_path=root / 'native-audit', _transport=Transport())


def test_history_revision_and_interrupted_publication_cannot_publish_or_retry(native, monkeypatch):
    from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint
    opening, _, _, _ = native
    transport = Transport(); product = opening(transport)
    original = TimelineEngine._hit
    def hit(engine, point):
        if point is FaultPoint.BEFORE_PUBLICATION_COMMIT:
            product.application.set_reviewed_character_history(False)
            product.application.set_reviewed_character_history(True)
        return original(engine, point)
    monkeypatch.setattr(TimelineEngine, '_hit', hit)
    result = send(product, command(product), 'changed')
    assert result.status == 'failed-closed' and len(transport.calls) == 1, result
    assert not product.application.query_memorie_interactions().turns
    product.close()
    monkeypatch.setattr(TimelineEngine, '_hit', original)
    after = Transport(); restored = opening(after)
    def interrupted(engine, point):
        if point is FaultPoint.BEFORE_PUBLICATION_TRANSACTION: raise OSError('synthetic interruption after delivery')
        return original(engine, point)
    monkeypatch.setattr(TimelineEngine, '_hit', interrupted)
    value = command(restored)
    assert send(restored, value, 'interrupted').status == 'pending'
    assert len(after.calls) == 1
    restored.close()
    monkeypatch.setattr(TimelineEngine, '_hit', original)
    final = Transport(); recovered = opening(final)
    assert send(recovered, value, 'interrupted').status == 'failed-closed' and not final.calls
    assert not recovered.application.query_memorie_interactions().turns


def test_approved_preview_bytes_and_rejects_extra_private_state(native):
    from dynamic_subject_agent.application import ApplicationFacade
    from dynamic_subject_agent.memorie_companion_preparation import MemoriePreparationView
    from dynamic_subject_agent.memorie_native import wire, NativeReplyProjection
    _, _, private, _ = native
    prepared = MemoriePreparationView(**json.loads((private / 'preparation.json').read_bytes()))
    directory = Path(os.environ['MEMORIE_NATIVE_REVIEW'])
    for name in ('idle-click', 'work-click', 'rest-followup', 'unknown-text'):
        raw = (directory / (name + '.json')).read_bytes()
        value = json.loads(json.loads(raw)['messages'][1]['content'])
        expected = ApplicationFacade.preview_memorie_native_message(prepared, value['interaction'], value['situation'], tuple(value['exchange']))
        assert expected == raw
        value['situation'] = {'timer_phase': 'work', 'elapsed_seconds': 23, 'note': 'PRIVATE_SENTINEL'}
        with pytest.raises(ValueError): wire(NativeReplyProjection(canonical_json(value)))


def test_wrong_original_payload_and_legacy_speech_never_generate(native):
    from dynamic_subject_agent.timeline import SubjectCommand
    opening, _, _, _ = native
    transport = Transport(); product = opening(transport)
    value = command(product)
    assert send(product, value, 'original').status == 'terminal'
    changed = replace(value, situation_json=canonical_json({'timer_phase': 'work'}))
    query = product.application.lookup_subject_request(SubjectRequestLookupRequest(changed, 'native-test-request-original'))
    assert query.query_status == 'unavailable', query
    old = SubjectCommand.contribute_utterance(target_profile_id=product.profile_id,
        target_timeline_id=product.timeline_id, declared_intent='ask-collaborator-status',
        utterance='不能绕过typed输入。', language='zh', provenance='project-original')
    assert send(product, old, 'legacy').status == 'unavailable'
    assert len(transport.calls) == 1


def test_canonical_input_corruption_fails_reopen_without_model_or_fake_history(native):
    opening, config, _, root = native
    transport = Transport(); product = opening(transport)
    assert send(product, command(product), 'committed').status == 'terminal'
    product.close()
    changed = False
    for path in root.rglob('timeline.sqlite3'):
        with closing(sqlite3.connect(path)) as db, db:
            if db.execute('PRAGMA user_version').fetchone() != (10,): continue
            row = db.execute('SELECT operation_id,input_json FROM memorie_native_input').fetchone()
            if row is None: continue
            value = json.loads(row[1]); value['situation_json'] = canonical_json({'timer_phase': 'work'})
            db.execute('UPDATE memorie_native_input SET input_json=? WHERE operation_id=?', (canonical_json(value), row[0]))
            changed = True
    assert changed
    after = Transport()
    with pytest.raises(Exception): opening(after)
    assert not after.calls


def test_timer_is_not_learning_progress_is_expression_but_disclosure_stays_local(native):
    opening, _, _, _ = native
    transport = Transport(); product = opening(transport)
    ordinary = '刚才我怎么跟你打招呼的？也请别把计时状态说成我已经学完了。'
    assert send(product, command(product), 'click').status == 'terminal'
    assert send(product, command(product, {'kind': 'text', 'text': ordinary}, 'rest'), 'clarify').status == 'terminal'
    assert payload(transport.calls[1])['exchange'][0]['interaction'] == {'kind': 'character-click'}
    for index, restricted in enumerate(('不要把之前的聊天发给模型。', '别再提刚才的事。',
        '别把计时当成完成任务，同时不要发送聊天记录。', '忘掉我的名字。')):
        result = send(product, command(product, {'kind': 'text', 'text': restricted}), 'restricted-' + str(index))
        assert result.status == 'failed-closed', result
    assert len(transport.calls) == 2
