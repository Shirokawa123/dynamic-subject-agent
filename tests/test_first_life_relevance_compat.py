"""Same-identity runtime addon and revocable share publication, synthetic only."""
from contextlib import contextmanager
from dataclasses import replace
import json
from threading import Event, Thread, current_thread

import pytest

from dynamic_subject_agent.deepseek import DeepSeekHttpResponse
from dynamic_subject_agent.first_life import FirstLifeSimulationRequest, FirstLifeHeartbeatRequest
from dynamic_subject_agent.first_life_authorization import ShareAuthorization, ShareAuthorizationChanged, LEGACY_RUNTIME_POLICY
from dynamic_subject_agent.first_life_relevance import RELEVANCE_VERSION, first_life_scope_digest
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
from dynamic_subject_agent.timeline import FaultPoint, PublicationProblem, OperationState
from test_first_life_facade import life_fixture, settle, LifeTransport
from test_first_life_facade import approved, model_fixture, personality_fixture
from test_first_life_publication import life_runtime, SyntheticLife, chat, advance, system
from test_reviewed_character_chat import send


class RelevanceTransport(LifeTransport):
    def post_json(self, **kwargs):
        response = super().post_json(**kwargs)
        body, projection = self.calls[-1]
        outer = json.loads(response.body)
        value = json.loads(outer['choices'][0]['message']['content'])
        if 'conversation' in projection and 'self_knowledge' in projection['conversation']:
            value['focus'] = 'respond-current'
        elif 'share' in value:
            value.update(focus='composition' if value['share'] else 'none',
                opening=('continuation' if projection['recent_dialogue'] else 'self-interest') if value['share'] else 'none')
        outer['choices'][0]['message']['content'] = canonical_json(value)
        return DeepSeekHttpResponse(200, canonical_json(outer).encode())


def enable(opening, transport, view):
    # The fixture retains one transport object; replace only its deterministic
    # response method so all request observations remain in the same list.
    transport.__class__ = RelevanceTransport
    return opening(runtime_policy=RELEVANCE_VERSION, runtime_policy_digest=first_life_scope_digest(view.definition_basis))


def test_upgrade_preserves_identity_history_and_rollback_keeps_original_scope(life_fixture):
    opening, transport, _, config, view = life_fixture
    original = opening()
    assert send(original, '这次聊构图留白。', 'compat-first-dialogue').status == 'terminal'
    old = (original.profile_id, original.timeline_id, original.publication_key)
    state_before = json.loads(config.state_path.read_text())
    original.close()
    upgraded = enable(opening, transport, view)
    assert (upgraded.profile_id, upgraded.timeline_id, upgraded.publication_key) == old
    assert send(upgraded, '继续聊这个。', 'compat-next-dialogue').status == 'terminal'
    assert transport.calls[-2][1]['recent_dialogue'][0]['user_text'] == '这次聊构图留白。'
    state_after = json.loads(config.state_path.read_text())
    assert len(state_after['identities']) == len(state_before['identities'])
    record = next(row for row in state_after['identities'] if row['identity_id'] == upgraded.profile_id)
    before = next(row for row in state_before['identities'] if row['identity_id'] == upgraded.profile_id)
    for key in ('publication_key', 'life_scope_digest', 'life_identity_basis', 'freeze_basis_digest', 'timeline_id'):
        assert record[key] == before[key]
    upgraded.close()
    restarted = opening()
    assert restarted.profile_id == old[0]
    restarted.close()
    transport.post_json = LifeTransport.post_json.__get__(transport, LifeTransport)
    rollback = opening(runtime_policy=LEGACY_RUNTIME_POLICY, runtime_policy_digest=record['life_scope_digest'])
    assert send(rollback, '现在聊另一件事。', 'compat-rollback-dialogue').status == 'terminal'
    assert len(transport.calls[-2][1]['recent_dialogue']) == 2
    assert LocalIdentityAuthority(config).first_life_runtime_policy(old[0]) == LEGACY_RUNTIME_POLICY


@pytest.mark.parametrize('enabled', [True, False])
def test_share_uses_same_identity_window_or_verified_empty_and_decision_has_none(life_fixture, enabled):
    opening, transport, _, config, view = life_fixture
    product = enable(opening, transport, view)
    for index in range(3):
        assert send(product, f'我们聊过轮廓和留白{index}。', f'relevance-window-{index}').status == 'terminal'
    app = product.application
    assert app.set_reviewed_character_history(enabled).status == 'active'
    result = settle(app, app.simulate_first_life_step(FirstLifeSimulationRequest('relevance-window-step')))
    assert result.status == 'terminal'
    assert 'recent_dialogue' not in transport.calls[-1][1]
    share = settle(app, app.heartbeat_first_life(FirstLifeHeartbeatRequest('relevance-window-session', 'relevance-window-share')))
    assert share.status == 'terminal', repr(share) + repr(transport.calls[-1][1])
    outbound = transport.calls[-1][1]
    assert outbound['history_enabled'] is enabled
    assert [row['user_text'] for row in outbound['recent_dialogue']] == ([f'我们聊过轮廓和留白{i}。' for i in (1, 2)] if enabled else [])
    assert len(app.query_first_life().shares) == 1
    product.close()
    restored = opening()
    assert len(restored.application.query_first_life().shares) == 1


@pytest.mark.parametrize('when', ['before-send', 'in-flight', 'unknown-history'])
def test_history_change_around_share_send_blocks_old_candidate(life_fixture, monkeypatch, when):
    opening, transport, _, config, view = life_fixture
    product = enable(opening, transport, view)
    assert send(product, '可以聊留白。', 'revoke-initial-chat').status == 'terminal'
    app = product.application
    settle(app, app.simulate_first_life_step(FirstLifeSimulationRequest('revoke-life-step')))
    before_calls = len(transport.calls)
    if when == 'unknown-history':
        from dynamic_subject_agent.timeline import TimelineEngine
        from dynamic_subject_agent.reviewed_character_chat import CharacterDialogueBasis
        monkeypatch.setattr(TimelineEngine, 'character_dialogue_before',
            lambda *args, **kwargs: CharacterDialogueBasis('unavailable', problem_code='synthetic-history-failure'))
    elif when == 'before-send':
        import dynamic_subject_agent.first_life_relevance as module
        original = module.share_model_projection
        def projecting(*args, **kwargs):
            result = original(*args, **kwargs)
            assert app.set_reviewed_character_history(False).status == 'active'
            assert app.set_reviewed_character_history(True).status == 'active'
            return result
        monkeypatch.setattr(module, 'share_model_projection', projecting)
    else:
        original = transport.post_json
        def posting(**kwargs):
            response = original(**kwargs)
            # Same-thread reentrancy models a completed revocation after send.
            assert app.set_reviewed_character_history(False).status == 'active'
            assert app.set_reviewed_character_history(True).status == 'active'
            return response
        transport.post_json = posting
    result = settle(app, app.heartbeat_first_life(FirstLifeHeartbeatRequest('revoke-window-session', 'revoke-share-request')))
    assert result.status == 'failed-closed'
    assert bool(app.first_life_status().problem_code) == (when == 'unknown-history')
    assert app.query_first_life().shares == ()
    assert len(transport.calls) == before_calls + (when == 'in-flight')
    state = json.loads(config.state_path.read_text())
    record = next(row for row in state['identities'] if row['identity_id'] == product.profile_id)
    assert record['history_enabled'] and record['history_revision'] == (0 if when == 'unknown-history' else 2)


class AuthorizedLife(SyntheticLife):
    def __init__(self, token_box):
        super().__init__()
        self.token_box = token_box

    @contextmanager
    def share_guard(self, token):
        if token != self.token_box[0]: raise ShareAuthorizationChanged('authorization changed')
        yield

    def propose(self, **kwargs):
        proposal = super().propose(**kwargs)
        if getattr(kwargs['command'], 'input_kind', '') == 'share':
            return replace(proposal, share_authorization=self.token_box[0])
        return proposal


@pytest.mark.parametrize('when', ['before-final-commit', 'cold-recovery', 'missing-authority'])
def test_authorization_change_cancels_prepared_share_without_recalling_model(life_runtime, when):
    opening, authority, _ = life_runtime
    token_box = [ShareAuthorization(authority.profile_id, RELEVANCE_VERSION, 'a' * 64, 1, 0, True)]
    cognition = AuthorizedLife(token_box)
    runtime = opening(cognition)
    chat(runtime, authority)
    advance(runtime, authority)
    event = runtime.first_life_basis().events[-1]
    def fault(point):
        if when == 'before-final-commit' and point is FaultPoint.BEFORE_PUBLICATION_COMMIT:
            token_box[0] = replace(token_box[0], history_revision=2)
        elif when != 'before-final-commit' and point is FaultPoint.AFTER_PLAN_CLAIM:
            raise RuntimeError('synthetic crash')
    runtime._engine._fault_hook = fault
    admitted = runtime.admit_first_life(system(authority, 'share', target_event_id=event.event_id), idempotency_key='authorization-share')
    if when == 'before-final-commit':
        result = runtime.resume(admitted.operation_ref)
    else:
        with pytest.raises(PublicationProblem): runtime.resume(admitted.operation_ref)
        prepared = runtime._engine.prepared_plan(admitted.operation_ref)
        assert prepared.share_authorization == token_box[0]
        runtime.close()
        token_box[0] = replace(token_box[0], history_revision=2)
        next_cognition = SyntheticLife() if when == 'missing-authority' else AuthorizedLife(token_box)
        runtime = opening(next_cognition)
        results = runtime.recover_first_life_pending()
        result = results[0]
        assert next_cognition.calls == 0
    assert result.snapshot.operation_state is OperationState.FAILED_CLOSED
    assert runtime._engine.query_failure(admitted.operation_ref).code == ('first-life-share-authorization-unverified' if when == 'missing-authority' else 'first-life-share-authorization-changed')
    assert bool(runtime.first_life_basis().technical_problem) == (when == 'missing-authority')
    assert runtime.first_life_basis().shares == ()
    with pytest.raises(PublicationProblem):
        runtime._engine.publish(runtime._engine.prepared_plan(admitted.operation_ref))


def test_unchanged_authorization_recovers_once_and_replay_ignores_later_revocation(life_runtime):
    opening, authority, _ = life_runtime
    box = [ShareAuthorization(authority.profile_id, RELEVANCE_VERSION, 'b' * 64, 1, 0, True)]
    cognition = AuthorizedLife(box)
    runtime = opening(cognition)
    chat(runtime, authority)
    advance(runtime, authority)
    event = runtime.first_life_basis().events[-1]
    def crash(point):
        if point is FaultPoint.AFTER_PLAN_CLAIM: raise RuntimeError('crash')
    runtime._engine._fault_hook = crash
    admitted = runtime.admit_first_life(system(authority, 'share', target_event_id=event.event_id), idempotency_key='valid-authorization-share')
    with pytest.raises(PublicationProblem): runtime.resume(admitted.operation_ref)
    runtime.close()
    cognition = AuthorizedLife(box)
    runtime = opening(cognition)
    result = runtime.recover_first_life_pending()[0]
    assert result.snapshot.operation_state is OperationState.COMPLETED and cognition.calls == 0
    box[0] = replace(box[0], history_revision=1, history_enabled=False)
    assert runtime.resume(admitted.operation_ref).outcome == result.outcome
    assert len(runtime.first_life_basis().shares) == 1


def test_successful_history_confirmation_fences_send_and_policy_aba(life_fixture):
    opening, transport, _, config, view = life_fixture
    product = enable(opening, transport, view)
    authority = LocalIdentityAuthority(config)
    token = authority.first_life_share_authorization(product.profile_id)
    entered, returned = Event(), Event()
    responses = []
    def closing_history():
        entered.set()
        responses.append(product.application.set_reviewed_character_history(False))
        returned.set()
    # A different authority instance for the same registry shares the lock.
    with authority.first_life_share_guard(token):
        worker = Thread(target=closing_history)
        worker.start()
        assert entered.wait(2)
        assert not returned.wait(.05)
    assert returned.wait(5)
    worker.join()
    assert responses[0].status == 'active'
    with pytest.raises(RuntimeError):
        with authority.first_life_share_guard(token): pass
    fresh = authority.first_life_share_authorization(product.profile_id)
    original_scope = json.loads(config.state_path.read_text())['identities'][-1]['life_scope_digest']
    authority.first_life_runtime_policy(product.profile_id, runtime_policy=LEGACY_RUNTIME_POLICY, runtime_policy_digest=original_scope)
    authority.first_life_runtime_policy(product.profile_id, runtime_policy=RELEVANCE_VERSION,
        runtime_policy_digest=first_life_scope_digest(view.definition_basis))
    with pytest.raises(RuntimeError):
        with authority.first_life_share_guard(fresh): pass
    state = json.loads(config.state_path.read_text())
    record = next(row for row in state['identities'] if row['identity_id'] == product.profile_id)
    record.pop('history_revision')
    config.state_path.write_text(canonical_json(state), encoding='utf-8')
    with pytest.raises(RuntimeError, match='runtime-policy-invalid'):
        authority.first_life_share_authorization(product.profile_id)
    assert authority.set_reviewed_character_history(True, product.profile_id).status == 'failed-closed'
    assert 'history_revision' not in next(row for row in json.loads(config.state_path.read_text())['identities']
        if row['identity_id'] == product.profile_id)
    record['history_revision'] = 0
    record['life_runtime_policy'] = None
    config.state_path.write_text(canonical_json(state), encoding='utf-8')
    with pytest.raises(RuntimeError, match='runtime-policy-invalid'):
        authority.first_life_runtime_policy(product.profile_id)
    with pytest.raises(RuntimeError, match='runtime-policy-invalid'):
        with authority.first_life_share_guard(token): pass
    record.pop('life_runtime_policy')
    config.state_path.write_text(canonical_json(state), encoding='utf-8')
    with pytest.raises(RuntimeError, match='authorization-missing'):
        with authority.first_life_share_guard(token): pass


def test_selection_cannot_overwrite_successful_history_revision(life_fixture, monkeypatch):
    import dynamic_subject_agent.local_identity_authority as module
    from dynamic_subject_agent.source_character_authoring import LocalIdentitySelectRequest
    opening, transport, _, config, view = life_fixture
    product = enable(opening, transport, view)
    authority = LocalIdentityAuthority(config)
    token = authority.first_life_share_authorization(product.profile_id)
    entered, release, edited = Event(), Event(), Event()
    responses, selections = [], []
    validate = module._validate_identity_record
    def validating(*args, **kwargs):
        if current_thread().name == 'selection-probe':
            entered.set()
            assert release.wait(5)
        return validate(*args, **kwargs)
    monkeypatch.setattr(module, '_validate_identity_record', validating)
    selecting = Thread(name='selection-probe', target=lambda: selections.append(
        product.application.select_local_identity(LocalIdentitySelectRequest(product.profile_id, True))))
    def editing():
        responses.extend((product.application.set_reviewed_character_history(False),
            product.application.set_reviewed_character_history(True)))
        edited.set()
    selecting.start()
    assert entered.wait(5)
    setter = Thread(target=editing)
    setter.start()
    try:
        assert not edited.wait(.05)
    finally:
        release.set()
    selecting.join(5)
    setter.join(5)
    assert not selecting.is_alive() and not setter.is_alive()
    assert len(selections) == 1 and selections[0].status == 'selected'
    assert [response.status for response in responses] == ['active', 'active']
    assert authority.first_life_share_authorization(product.profile_id).history_revision == 2
    with pytest.raises(ShareAuthorizationChanged):
        with authority.first_life_share_guard(token): pass
