"""Local private-source integration; no credentials or network are used.

The approved source package remains private. The same Interface checks can run
where its explicitly supplied review is present, without copying it into Git.
"""
from hashlib import sha256
import json
from pathlib import Path

import pytest

from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product, open_memorie_companion_product
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
from dynamic_subject_agent.source_character_authoring import LocalIdentitySelectRequest
from dynamic_subject_agent.memorie_companion_contract import (
    MemorieCallAudit, DEFINITION, SCOPE, USE_REVIEW, contract, projection, wire, VERSION, ATTRIBUTION_VERSION, INTENT_VERSION,
)
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from test_reviewed_character_chat import send


class MemorieTransport(DeepSeekTransport):
    def __init__(self, fault=None):
        self.calls, self.fault = [], fault

    def post_json(self, **kwargs):
        self.calls.append(kwargs)
        if self.fault == 'timeout':
            raise TimeoutError('PRIVATE_ERROR_NEVER_EXPOSE')
        if self.fault == 'credential':
            from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
            raise CharacterCredentialUnavailable()
        text = '合成回复。' if self.fault != 'oversized' else '甲' * 1201
        body = dict(model='deepseek-flash', choices=[dict(finish_reason='length' if self.fault == 'length' else 'stop',
            message=dict(role='assistant', content=text, reasoning_content='PRIVATE_REASONING_NEVER_EXPOSE'))],
            usage=dict(prompt_tokens=100, completion_tokens=20))
        return DeepSeekHttpResponse(200, canonical_json(body).encode())


@pytest.fixture
def memorie_product(tmp_path):
    private = Path(__file__).resolve().parents[1] / '.artifacts/s160'
    if not (private / 'approval.json').exists():
        pytest.skip('explicit private S160 review not present')
    prepared = json.loads((private / 'preparation.json').read_text('utf-8'))
    config = LocalProductConfig(tmp_path / 'product/m0/experiments', tmp_path / 'product/state.json')
    with open_local_product(config, cognition=DormantDeepSeekCognition()) as dormant:
        result = dormant.application.freeze_source_identity(ReviewedCharacterFreezeRequest(
            prepared['definition_json'], DEFINITION, True, True))
        assert result.status == 'created', result
        assert dormant.application.select_local_identity(LocalIdentitySelectRequest(result.view.identity_id, True)).status == 'selected'
    opened = []
    def opening(transport=None, **overrides):
        product = open_memorie_companion_product(config, approval_path=private / 'approval.json',
            audit_path=tmp_path / 'calls', _transport=transport or MemorieTransport(), **overrides)
        opened.append(product)
        return product
    yield opening, config, private, tmp_path / 'calls'
    for product in opened:
        product.close()


def history(product):
    return product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
        product.profile_id, product.timeline_id))


def test_real_composition_exact_reviewed_wire_restart_history_and_same_uuid(memorie_product):
    opening, config, private, audit_path = memorie_product
    transport = MemorieTransport()
    product = opening(transport)
    assert product.application.reviewed_character_chat_status().budget_used == 0
    assert not transport.calls
    first = send(product, '合成：我打算看一节课程。', 'first')
    assert first.status == 'terminal', first
    assert len(transport.calls) == 1
    from dynamic_subject_agent.memorie_companion_preparation import MemoriePreparationView, preview_memorie_wire
    prepared = MemoriePreparationView(**json.loads((private / 'preparation.json').read_text('utf-8')))
    assert transport.calls[0]['body'] == preview_memorie_wire(prepared, '合成：我打算看一节课程。')
    body = json.loads(transport.calls[0]['body'])
    payload = json.loads(body['messages'][1]['content'])
    assert set(payload) == {'character', 'personality', 'exchange', 'current_message'}
    assert body['thinking'] == {'type': 'disabled'} and body['max_tokens'] == 4096
    assert len(payload['character']['knowledge']) == 30 and len(payload['personality']) == 4
    for denied in ('line:', 'claim_ids', 'source_declaration', 'runtime_identity', 'PRIVATE_REASONING', 'publication_timestamp'):
        assert denied not in transport.calls[0]['body'].decode()
    assert send(product, '合成：我打算看一节课程。', 'first').replayed
    assert len(transport.calls) == 1 and len(history(product).projection.turns) == 1
    identity, timeline = product.profile_id, product.timeline_id
    product.close()
    transport2 = MemorieTransport(); restored = opening(transport2)
    assert (restored.profile_id, restored.timeline_id) == (identity, timeline)
    assert send(restored, '刚刚我准备做什么？', 'second').status == 'terminal'
    second = json.loads(json.loads(transport2.calls[0]['body'])['messages'][1]['content'])
    assert second['exchange'] == [dict(user_text='合成：我打算看一节课程。', assistant_text='合成回复。')]
    assert restored.application.set_reviewed_character_history(False).history_enabled is False
    assert send(restored, '仅当前消息。', 'off').status == 'terminal'
    assert json.loads(json.loads(transport2.calls[1]['body'])['messages'][1]['content'])['exchange'] == []
    assert MemorieCallAudit(audit_path).counts() == (None, 3, None)


@pytest.mark.parametrize('fault,status', [('timeout', 'unknown'), ('credential', 'unavailable'),
    ('length', 'failed-closed'), ('oversized', 'failed-closed')])
def test_fault_is_terminal_without_publication_or_redelivery_across_restart(memorie_product, fault, status):
    opening, _, _, audit_path = memorie_product
    transport = MemorieTransport(fault); product = opening(transport)
    result = send(product, '合成故障检查。', 'fault')
    assert result.status == status, result
    assert len(transport.calls) == 1 and not history(product).projection.turns
    assert send(product, '合成故障检查。', 'fault').status == status
    assert len(transport.calls) == 1
    product.close()
    next_transport = MemorieTransport(); restored = opening(next_transport)
    assert send(restored, '合成故障检查。', 'fault').status == status
    assert not next_transport.calls and MemorieCallAudit(audit_path).counts() == (None, 1, None)


@pytest.mark.parametrize('point', ['publication', 'registry-after-swap'])
def test_exact_activation_recovers_same_identity_and_timeline(memorie_product, monkeypatch, point):
    import dynamic_subject_agent.local_identity_authority as authority
    from dynamic_subject_agent.studio import SubjectStudio
    opening, config, _, _ = memorie_product
    before = json.loads(config.state_path.read_text('utf-8'))['identities'][-1]
    if point == 'publication':
        original = SubjectStudio.publish
        monkeypatch.setattr(SubjectStudio, 'publish', lambda *a, **kw: (_ for _ in ()).throw(OSError('synthetic interruption')))
    else:
        original = authority._write_state
        def interrupted(path, payload):
            row = payload['identities'][-1]
            if 'chat_activation' in row and 'pending_chat_activation' not in row:
                raise OSError('synthetic interrupted swap')
            original(path, payload)
        monkeypatch.setattr(authority, '_write_state', interrupted)
    with pytest.raises(OSError):
        opening()
    monkeypatch.setattr(SubjectStudio if point == 'publication' else authority,
        'publish' if point == 'publication' else '_write_state', original)
    from dynamic_subject_agent.local_product import open_or_create_memorie_companion_product
    private = memorie_product[2]
    restored = open_or_create_memorie_companion_product(config, approval_path=private / 'approval.json',
        audit_path=memorie_product[3], preparation_json=json.loads((private / 'preparation.json').read_text('utf-8'))['definition_json'],
        _transport=MemorieTransport())
    assert restored.profile_id == before['identity_id'] and restored.timeline_id == before['timeline_id']
    assert send(restored, '恢复后交流。', 'recovered').status == 'terminal'
    restored.close()


def test_publication_rechecks_history_revision_even_after_off_on(memorie_product, monkeypatch):
    from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint
    opening, _, _, _ = memorie_product
    transport = MemorieTransport(); product = opening(transport)
    original = TimelineEngine._hit
    def hit(engine, point):
        if point is FaultPoint.BEFORE_PUBLICATION_COMMIT:
            assert product.application.set_reviewed_character_history(False).history_enabled is False
            assert product.application.set_reviewed_character_history(True).history_enabled is True
        return original(engine, point)
    monkeypatch.setattr(TimelineEngine, '_hit', hit)
    result = send(product, '合成提交前切换。', 'guard')
    assert result.status == 'failed-closed', result
    assert len(transport.calls) == 1 and not history(product).projection.turns


def test_cold_recovery_closes_claimed_reply_without_model_redelivery(memorie_product, monkeypatch):
    from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint
    opening, _, _, audit_path = memorie_product
    transport = MemorieTransport(); product = opening(transport)
    original = TimelineEngine._hit
    def interrupted(engine, point):
        if point is FaultPoint.BEFORE_PUBLICATION_TRANSACTION:
            raise OSError('synthetic interrupted after durable claim')
        return original(engine, point)
    monkeypatch.setattr(TimelineEngine, '_hit', interrupted)
    result = send(product, '合成：已交付但未提交。', 'cold')
    assert result.status == 'pending' and len(transport.calls) == 1
    product.close()
    monkeypatch.setattr(TimelineEngine, '_hit', original)
    next_transport = MemorieTransport(); restored = opening(next_transport)
    recovered = send(restored, '合成：已交付但未提交。', 'cold')
    assert recovered.status == 'failed-closed', recovered
    assert not next_transport.calls and not history(restored).projection.turns
    assert MemorieCallAudit(audit_path).counts() == (None, 1, None)


def test_learning_goal_topic_continues_but_explicit_disclosure_stops_before_wire(memorie_product):
    opening, _, _, _ = memorie_product
    transport = MemorieTransport(); product = opening(transport)
    first = '我准备先学二十五分钟。目标是弄清一个概念，而不是只把计时器跑完。'
    assert send(product, first, 'study-goal').status == 'terminal'
    assert send(product, '刚才我的学习目标是什么？', 'study-followup').status == 'terminal'
    payload = json.loads(json.loads(transport.calls[1]['body'])['messages'][1]['content'])
    assert payload['exchange'] == [dict(user_text=first, assistant_text='合成回复。')]
    refused = send(product, '不要把之前的聊天发给模型。', 'disclosure')
    assert refused.status == 'failed-closed' and len(transport.calls) == 2
    assert len(history(product).projection.turns) == 2
    assert product.application.set_reviewed_character_history(False).history_enabled is False
    assert send(product, '只发这一句，聊聊魔法。', 'without-history').status == 'terminal'
    assert json.loads(json.loads(transport.calls[2]['body'])['messages'][1]['content'])['exchange'] == []


def test_qualified_http_send_lookup_and_restart_never_wait_or_resubmit(memorie_product, monkeypatch):
    import importlib, sys, time
    from threading import Thread
    from uuid import uuid4
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app/desktop'))
    from test_memorie_companion_entry import call
    server_factory = importlib.import_module('memorie_companion').memorie_companion_server
    opening, _, _, _ = memorie_product
    transport = MemorieTransport(); product = opening(transport)
    request = None
    for restart in (False, True):
        server = server_factory(product, reopen=lambda: product)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        root = f'http://127.0.0.1:{server.server_port}/'
        try:
            session = call(root, 'session')
            if not restart:
                request = dict(text='合成原消息恢复。', request_id=str(uuid4()), scope_key=call(root, 'status')['scope_key'])
                assert call(root, 'send', request, session['token'])['pending']
            for _ in range(80):
                result = call(root, 'result', request, session['token'])
                if result['settled']:
                    break
                time.sleep(.05)
            assert result['settled'] and result['ok'], result
            assert result['state']['turns'] == [dict(user_text=request['text'], assistant_text='合成回复。')]
            assert len(transport.calls) == 1
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)
        product.close()
        if not restart:
            product = opening(transport)


def test_original_chat_scope_cannot_qualify_memorie_and_changed_approval_does_not_activate(memorie_product, tmp_path):
    from dynamic_subject_agent.local_product import open_reviewed_character_chat_product
    from dynamic_subject_agent.reviewed_character_chat import continuity_scope
    opening, config, private, audit_path = memorie_product
    old_scope = sha256(canonical_json(continuity_scope(DEFINITION)).encode()).hexdigest()
    old_review = sha256(canonical_json(dict(definition_basis=DEFINITION, scope_digest=old_scope)).encode()).hexdigest()
    # The original entry never receives the new approval implicitly. Once new
    # qualification exists, its exact metadata cannot be replaced by old scope.
    product = opening(); product.close()
    before = config.state_path.read_bytes()
    with pytest.raises(RuntimeError, match='conflict'):
        open_reviewed_character_chat_product(config, definition_basis=DEFINITION, scope_digest=old_scope,
            review_request_basis=old_review, budget_path=tmp_path / 'legacy-budget', _transport=MemorieTransport())
    assert not (tmp_path / 'legacy-budget').exists() and config.state_path.read_bytes() == before
    receipt = json.loads((private / 'approval.json').read_text('utf-8')); receipt['model_use_confirmed'] = False
    wrong = tmp_path / 'wrong-approval.json'; wrong.write_text(canonical_json(receipt), encoding='utf-8')
    with pytest.raises(ValueError):
        open_memorie_companion_product(config, approval_path=wrong, audit_path=audit_path, _transport=MemorieTransport())
    assert config.state_path.read_bytes() == before


def test_attribution_version_uses_same_approved_material_and_persists_exact_qualification(memorie_product):
    from dynamic_subject_agent.application import ApplicationFacade, SubjectRequestLookupRequest
    from dynamic_subject_agent.memorie_companion_preparation import MemoriePreparationView
    from dynamic_subject_agent.timeline import SubjectCommand
    opening, config, private, audit_path = memorie_product
    transport = MemorieTransport()
    product = opening(transport, contract_version=ATTRIBUTION_VERSION)
    before = product.application.reviewed_character_chat_status()
    assert before.status == 'active' and before.budget_used == 0 and not transport.calls
    prepared = MemoriePreparationView(**json.loads((private / 'preparation.json').read_text('utf-8')))
    message = '合成：你刚才的建议，我还没决定采用。'
    expected = ApplicationFacade.preview_memorie_companion_message(prepared, message, contract_version=ATTRIBUTION_VERSION)
    legacy = json.loads(ApplicationFacade.preview_memorie_companion_message(prepared, message))
    assert send(product, message, 'attribution-first').status == 'terminal'
    actual = json.loads(transport.calls[0]['body'])
    assert transport.calls[0]['body'] == expected
    assert actual['messages'][0]['content'].startswith(legacy['messages'][0]['content'])
    assert actual['messages'][0]['content'] != legacy['messages'][0]['content']
    actual['messages'][0]['content'] = legacy['messages'][0]['content']
    assert actual == legacy  # No new fields, sources, dialogue, stages or limits.
    scope = (product.profile_id, product.timeline_id)
    product.close()
    next_transport = MemorieTransport()
    restored = opening(next_transport, contract_version=ATTRIBUTION_VERSION)
    assert (restored.profile_id, restored.timeline_id) == scope
    command = SubjectCommand.contribute_utterance(target_profile_id=restored.profile_id,
        target_timeline_id=restored.timeline_id, declared_intent='ask-collaborator-status', utterance=message,
        language='zh', provenance='project-original')
    found = restored.application.lookup_subject_request(SubjectRequestLookupRequest(command, 'reviewed-character-test-attribution-first'))
    assert found.query_status == 'found' and found.operation.status == 'terminal' and not next_transport.calls
    assert send(restored, '继续合成接话。', 'attribution-next').status == 'terminal'
    payload = json.loads(json.loads(next_transport.calls[0]['body'])['messages'][1]['content'])
    assert payload['exchange'] == [dict(user_text=message, assistant_text='合成回复。')]
    assert MemorieCallAudit(audit_path).counts() == (None, 2, None)


def test_attribution_never_upgrades_existing_baseline_or_creates_unknown_version(memorie_product):
    opening, config, _, audit_path = memorie_product
    product = opening(); product.close()
    before = config.state_path.read_bytes()
    with pytest.raises(RuntimeError, match='activation-conflict'):
        opening(contract_version=ATTRIBUTION_VERSION)
    with pytest.raises(ValueError, match='unknown Memorie'):
        opening(contract_version='unreviewed-future-policy')
    assert config.state_path.read_bytes() == before and MemorieCallAudit(audit_path).counts() == (None, 0, None)
    restored = opening()
    assert restored._memorie_composition_witness['version'] == VERSION


def test_attribution_final_guard_and_cold_recovery_keep_terminal_without_redelivery(memorie_product, monkeypatch):
    from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint
    opening, _, _, _ = memorie_product
    transport = MemorieTransport(); product = opening(transport, contract_version=ATTRIBUTION_VERSION)
    original = TimelineEngine._hit
    def hit(engine, point):
        if point is FaultPoint.BEFORE_PUBLICATION_COMMIT:
            assert product.application.set_reviewed_character_history(False).history_enabled is False
            assert product.application.set_reviewed_character_history(True).history_enabled is True
        return original(engine, point)
    monkeypatch.setattr(TimelineEngine, '_hit', hit)
    assert send(product, '合成提交前撤回。', 'attribution-guard').status == 'failed-closed'
    assert len(transport.calls) == 1 and not history(product).projection.turns
    product.close()
    monkeypatch.setattr(TimelineEngine, '_hit', original)
    next_transport = MemorieTransport(); restored = opening(next_transport, contract_version=ATTRIBUTION_VERSION)
    assert send(restored, '合成提交前撤回。', 'attribution-guard').status == 'failed-closed'
    assert not next_transport.calls


def test_intent_refinement_preserves_parent_policy_and_exact_source_across_reopen(memorie_product):
    from dynamic_subject_agent.memorie_companion_contract import policy
    from dynamic_subject_agent.memorie_companion_preparation import POLICY
    opening, _, _, _ = memorie_product
    assert policy(VERSION) == POLICY
    assert policy(INTENT_VERSION).startswith(policy(ATTRIBUTION_VERSION))
    transport = MemorieTransport(); product = opening(transport, contract_version=INTENT_VERSION)
    assert product._memorie_composition_witness['technical_parent_version'] == ATTRIBUTION_VERSION
    message = '合成：我只是打算整理笔记，具体办法还没定。'
    assert send(product, message, 'intent-first').status == 'terminal'
    body = json.loads(transport.calls[0]['body'])
    assert body['messages'][0]['content'] == policy(INTENT_VERSION)
    assert set(json.loads(body['messages'][1]['content'])) == {'character', 'personality', 'exchange', 'current_message'}
    product.close()
    restored = opening(transport, contract_version=INTENT_VERSION)
    assert send(restored, '那我现在确定了什么？', 'intent-next').status == 'terminal'
    payload = json.loads(json.loads(transport.calls[1]['body'])['messages'][1]['content'])
    assert payload['exchange'] == [dict(user_text=message, assistant_text='合成回复。')]
