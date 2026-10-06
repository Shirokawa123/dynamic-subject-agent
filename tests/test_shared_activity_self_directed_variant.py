"""S141 qualification and persisted inputs, with synthetic delivery only."""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json

import pytest

from test_original_whole_chat import approved, personality_fixture, model_fixture, send, history
from test_shared_activity import select, step_request
from test_shared_activity_live import live_fixture, SharedTransport
from dynamic_subject_agent.deepseek import DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.local_product import open_shared_activity_product_live, validate_shared_activity_entry
from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING, contract_variant, whole_publication_key
from dynamic_subject_agent.shared_activity import (
    digest, shared_contract, shared_choice_policy, shared_reply_policy,
    SHARED_SELF_DIRECTED_CHOICE_POLICY_SHA, SHARED_EXPRESSION_POLICY_SHA)
from dynamic_subject_agent.shared_activity_live import (
    ApprovedSharedActivityGrant, APPROVED_SHARED_REVIEW, SharedActivityDelivery,
    shared_live_contract, open_shared_activity_audit)
from dynamic_subject_agent.shared_activity_remote_preview import shared_remote_request_preview
from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint
from dynamic_subject_agent.whole_context_boundary import WholeContextBoundaryRequest


def self_options(options):
    return dict(options, grant=ApprovedSharedActivityGrant(APPROVED_SHARED_REVIEW, True, 'self-directed-activity'),
        technical_variant='self-directed-activity')


class PlanTransport(SharedTransport):
    """Use received plan/focus to expose wiring; this is no semantic oracle."""
    def __init__(self, *, defer=False):
        super().__init__()
        self.defer = defer

    def post_json(self, **kwargs):
        body = json.loads(kwargs['body']); self.calls.append(body)
        payload = json.loads(body['messages'][1]['content'])
        if 'current_activity' not in payload:
            value = dict(reply_text='合成当前文字方案说明。', language='zh')
        else:
            action = 'defer' if self.defer else payload['current_activity']['allowed_actions'][0]
            plan = payload['current_plan']
            if action in ('start', 'revise'):
                if plan is None:
                    source = payload['shared_experience']
                    plan = dict(subject='窗边静物', composition='主体偏左，突出轮廓' + (source['quote'] if source else ''), focus='轮廓')
                else:
                    plan = dict(plan, composition=plan['composition'] + '；减少背景线条以突出' + plan['focus'])
            else:
                plan = None
            value = dict(action=action, plan=plan, reason_code='defer-comparison' if self.defer else 'improve-readability',
                basis_refs=['E1'] if payload['shared_experience'] else [],
                decision_note='合成暂缓：两种轮廓安排仍需比较。' if self.defer else '合成当前focus的具体取舍。')
        return DeepSeekHttpResponse(200, canonical_json(dict(model='deepseek-flash',
            choices=[dict(finish_reason='stop', message=dict(role='assistant', content=canonical_json(value)))],
            usage=dict(prompt_tokens=100, completion_tokens=20, total_tokens=120))).encode())


def test_closed_candidate_retains_old_exact_contracts_and_natural_reply():
    baseline = shared_live_contract(APPROVED_BINDING)
    natural = shared_live_contract(APPROVED_BINDING, technical_variant='natural-expression')
    candidate = shared_live_contract(APPROVED_BINDING, technical_variant='self-directed-activity')
    assert digest(baseline) == 'f37edb00aec3e999fc0ed0c09c5b30a9535a5e882054a3fc9c75db40e4666f66'
    assert digest(natural) == '20d3f2feac1019fc95094bace950203fba850df6c1e277d611a8f8c489372c6b'
    assert digest(shared_contract(APPROVED_BINDING)) == '0b60787ec732c7c35b5e124497b0600f94d146b28d8a17aea049594163dba7e5'
    assert contract_variant(candidate) == 'shared-live'
    assert whole_publication_key(candidate).startswith('original-shared-activity-live-s141-')
    assert candidate['technical_variant']['choice_policy_sha'] == SHARED_SELF_DIRECTED_CHOICE_POLICY_SHA
    assert candidate['policy_sha'] == candidate['technical_variant']['chat_policy_sha'] == SHARED_EXPRESSION_POLICY_SHA
    assert shared_reply_policy('self-directed-activity') == shared_reply_policy('natural-expression')
    assert sha256(shared_choice_policy('self-directed-activity').encode()).hexdigest() == SHARED_SELF_DIRECTED_CHOICE_POLICY_SHA
    for field in ('max_current_chars', 'max_complete_turns', 'max_exchange_chars', 'max_reply_chars', 'model', 'max_tokens',
        'thinking', 'reasoning_effort', 'provider', 'credential_use', 'max_requests_per_turn', 'automatic_retries'):
        assert candidate[field] == natural[field] == baseline[field]
    with pytest.raises(ValueError, match='exact local execution policy'):
        shared_remote_request_preview(ModelTask(ModelTaskKind.SHARED_ACTIVITY_CHOICE,
            dict(policy=shared_choice_policy(), payload={})), technical_variant='self-directed-activity')
    with pytest.raises(ValueError):
        ApprovedSharedActivityGrant(APPROVED_SHARED_REVIEW, True, 'caller-authored-policy')


def test_no_user_message_or_source_start_and_focus_revision_survive_prepared_reopen(live_fixture, monkeypatch):
    _, config, options, binding = live_fixture
    transport = PlanTransport()
    product = open_shared_activity_product_live(config, **self_options(options), _transport=transport)
    try:
        assert not history(product) and not transport.calls
        preview = product.application.preview_shared_activity_step().view
        assert set(preview['payload']) == {'background', 'shared_experience', 'current_activity', 'current_plan'}
        assert preview['payload']['shared_experience'] is preview['payload']['current_plan'] is None
        assert preview['payload']['current_activity'] == dict(phase='unstarted', allowed_actions=('start', 'defer'))
        # Both variants consume exactly the existing material; only choice text changes.
        snapshot = LocalIdentityAuthority(config).try_whole_scope_snapshot(product.profile_id, product.timeline_id)
        from dynamic_subject_agent.shared_activity import build_choice_preview
        baseline = build_choice_preview(snapshot['envelope'], snapshot['identity'], product.application.query_shared_activity().view,
            shared_live_contract(binding, technical_variant='natural-expression'))
        assert baseline['payload'] == preview['payload'] and baseline['policy'] != preview['policy']
        first = step_request(product, 'self-directed-start')
        result = product.application.advance_shared_activity(first)
        assert result.status == 'committed'
        wire = shared_remote_request_preview(ModelTask(ModelTaskKind.SHARED_ACTIVITY_CHOICE, preview), technical_variant='self-directed-activity')
        assert transport.calls == [wire['body']]
        initial = product.application.query_shared_activity().view
        assert initial['decision'].basis_refs == () and initial['activity_revision'] == 1 and not history(product)
        initial_plan = initial['current_plan']
    finally:
        product.close()
    fresh = PlanTransport()
    product = open_shared_activity_product_live(config, **self_options(options), _transport=fresh)
    try:
        assert not fresh.calls and product.application.query_shared_activity().view == initial
        assert product.application.advance_shared_activity(first).status == 'replayed' and not fresh.calls
        next_preview = product.application.preview_shared_activity_step().view
        assert next_preview['payload']['current_plan'] == asdict(initial_plan)
        second = step_request(product, 'self-directed-next-version')
        original = TimelineEngine._hit
        def hit(engine, point):
            if point is FaultPoint.AFTER_PLAN_CLAIM:
                raise OSError('synthetic durable candidate preparation interruption')
            return original(engine, point)
        with monkeypatch.context() as crash:
            crash.setattr(TimelineEngine, '_hit', hit)
            product.application.advance_shared_activity(second)
        assert len(fresh.calls) == 1
        assert json.loads(fresh.calls[0]['messages'][1]['content'])['current_plan'] == asdict(initial_plan)
    finally:
        product.close()
    final_transport = PlanTransport()
    product = open_shared_activity_product_live(config, **self_options(options), _transport=final_transport)
    try:
        assert not final_transport.calls
        replay = product.application.advance_shared_activity(second)
        assert replay.status == 'replayed' and not final_transport.calls
        state = product.application.query_shared_activity().view
        assert state['activity_revision'] == 2 and state['phase'] == 'revised'
        assert state['current_plan'].composition == initial_plan.composition + '；减少背景线条以突出' + initial_plan.focus
        assert len(state['result'].differences) == 1 and state['result'].differences[0].field == 'composition'
        assert send(product, '这次文字方案的取舍是什么？', 'self-directed-result-chat').status == 'terminal'
        payload = json.loads(final_transport.calls[0]['messages'][1]['content'])
        assert payload['evidence'] == dict(shared_experience=None, activity_result=dict(kind='composition-text', plan=asdict(state['current_plan'])))
        assert payload['exchange'] == []
        assert [row['purpose'] for row in open_shared_activity_audit(options['audit_path']).snapshot()] == [
            'shared-activity-choice', 'shared-activity-choice', 'shared-activity-reply']
    finally:
        product.close()


@pytest.mark.parametrize('control', ['disable', 'history', 'cutoff'])
def test_candidate_revocation_keeps_local_fact_but_removes_all_derived_inputs(live_fixture, control):
    _, config, options, _ = live_fixture
    transport = PlanTransport()
    product = open_shared_activity_product_live(config, **self_options(options), _transport=transport)
    try:
        assert send(product, '合成已提交依据TOKEN。', 'self-source').status == 'terminal'
        assert select(product, 'TOKEN').status == 'committed'
        assert product.application.advance_shared_activity(step_request(product)).status == 'committed'
        assert send(product, '说说本次文字方案。', 'self-derived-chat').status == 'terminal'
        if control == 'disable':
            assert select(product, '', head=None, key='self-directed-disable-source').status == 'committed'
        elif control == 'history':
            assert not product.application.set_reviewed_character_history(False).history_enabled
        else:
            assert product.application.apply_whole_context_boundary(WholeContextBoundaryRequest(product.profile_id,
                product.timeline_id, 'self-directed-context-cutoff', 0, True)).status == 'committed'
        retained = product.application.query_shared_activity().view['result']
        assert retained is not None
    finally:
        product.close()
    fresh = PlanTransport()
    product = open_shared_activity_product_live(config, **self_options(options), _transport=fresh)
    try:
        assert not fresh.calls
        state = product.application.query_shared_activity().view
        assert state['result'] == retained and state['phase'] == 'drafted'
        preview = product.application.preview_shared_activity_step().view['payload']
        assert preview['shared_experience'] is preview['current_plan'] is None and 'TOKEN' not in canonical_json(preview)
        assert send(product, '合成新话题。', 'self-after-revocation').status == 'terminal'
        payload = json.loads(fresh.calls[0]['messages'][1]['content'])
        assert payload['exchange'] == [] and payload['evidence'] == dict(shared_experience=None, activity_result=None)
        assert 'TOKEN' not in canonical_json(payload)
        assert product.application.advance_shared_activity(step_request(product, 'self-independent-next')).status == 'committed'
        assert product.application.query_shared_activity().view['activity_revision'] == 2
        assert 'TOKEN' not in canonical_json(fresh.calls[-1])
    finally:
        product.close()


def test_existing_natural_root_cannot_change_to_self_directed_candidate(live_fixture):
    _, config, options, _ = live_fixture
    natural_options = dict(options, grant=ApprovedSharedActivityGrant(APPROVED_SHARED_REVIEW, True, 'natural-expression'),
        technical_variant='natural-expression')
    product = open_shared_activity_product_live(config, **natural_options, _transport=SharedTransport())
    try:
        validate_shared_activity_entry(config, profile_id=product.profile_id, timeline_id=product.timeline_id, technical_variant='natural-expression')
        with pytest.raises(RuntimeError, match='entry-identity-unverified'):
            validate_shared_activity_entry(config, profile_id=product.profile_id, timeline_id=product.timeline_id, technical_variant='self-directed-activity')
    finally:
        product.close()
    before = config.state_path.read_bytes(); transport = SharedTransport()
    audit = open_shared_activity_audit(options['audit_path']).snapshot()
    with pytest.raises(RuntimeError, match='activation-conflict'):
        open_shared_activity_product_live(config, **self_options(options), _transport=transport)
    assert config.state_path.read_bytes() == before and not transport.calls
    assert open_shared_activity_audit(options['audit_path']).snapshot() == audit


def test_source_and_caller_choice_policy_mutations_fail_before_transport(live_fixture, monkeypatch):
    _, config, options, _ = live_fixture
    transport = SharedTransport()
    product = open_shared_activity_product_live(config, **self_options(options), _transport=transport)
    try:
        import dynamic_subject_agent.shared_activity as module
        request = step_request(product, 'self-mutated-source')
        with monkeypatch.context() as changed:
            changed.setattr(module, 'SELF_DIRECTED_CHOICE_SCOPE_PARAGRAPH', module.SELF_DIRECTED_CHOICE_SCOPE_PARAGRAPH + 'changed')
            assert product.application.advance_shared_activity(request).status == 'failed-closed'
        assert not transport.calls and open_shared_activity_audit(options['audit_path']).snapshot() == ()
        with monkeypatch.context() as changed:
            changed.setattr(module, 'CHOICE_POLICY', module.CHOICE_POLICY + 'changed')
            with pytest.raises(ValueError, match='pinned shared choice policy changed'):
                ApprovedSharedActivityGrant(APPROVED_SHARED_REVIEW, True, 'self-directed-activity').validate()
        original = SharedActivityDelivery.claim
        def claim(self, operation, task, rebuild):
            changed = deepcopy(task.payload); changed['policy'] = shared_choice_policy()
            return original(self, operation, ModelTask(task.kind, changed), rebuild)
        with monkeypatch.context() as changed:
            changed.setattr(SharedActivityDelivery, 'claim', claim)
            result = product.application.advance_shared_activity(step_request(product, 'self-mutated-caller'))
        assert result.status == 'failed-closed' and result.problem_code == 'original-whole-delivery-unverified'
        assert not transport.calls and not history(product)
        assert open_shared_activity_audit(options['audit_path']).snapshot() == ()
        # An unverified delivery also closes the state projection. It must not
        # be reinterpreted as a successful empty activity.
        state = product.application.query_shared_activity()
        assert state.status == 'failed-closed' and state.view is None
    finally:
        product.close()


def test_candidate_allows_actual_defer_and_failed_attempt_does_not_create_activity(live_fixture):
    _, config, options, _ = live_fixture
    transport = PlanTransport(defer=True)
    product = open_shared_activity_product_live(config, **self_options(options), _transport=transport)
    try:
        request = step_request(product, 'self-legal-defer')
        assert product.application.advance_shared_activity(request).status == 'committed'
        state = product.application.query_shared_activity().view
        assert state['decision'].action == 'defer' and state['current_plan'] is None and state['activity_revision'] == 0
        assert state['decision'].basis_refs == () and len(transport.calls) == 1
    finally:
        product.close()
    fault = SharedTransport('blank')
    product = open_shared_activity_product_live(config, **self_options(options), _transport=fault)
    try:
        request = step_request(product, 'self-failed-advance')
        first = product.application.advance_shared_activity(request)
        assert first.status == 'failed-closed' and first.problem_code == 'original-whole-response-content-empty'
        assert product.application.advance_shared_activity(request).status == first.status and len(fault.calls) == 1
        assert product.application.query_shared_activity().view == state
    finally:
        product.close()
