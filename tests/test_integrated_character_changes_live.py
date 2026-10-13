"""Change-use delivery and source lifetime, with synthetic HTTPS only."""
from copy import deepcopy
from dataclasses import asdict, replace
import json

import pytest

from test_original_whole_chat import approved, personality_fixture, model_fixture, send, history
from test_integrated_character_live import integrated_live_fixture, IntegratedTransport
from test_integrated_character import MESSAGE, PLAN
from test_living_activity import state, control, act, action_request
from test_shared_activity import select
from dynamic_subject_agent.integrated_character_live import (
    ApprovedIntegratedCharacterGrant, APPROVED_INTEGRATED_REVIEW, APPROVED_CHANGE_REVIEW,
    IntegratedCharacterDelivery, open_integrated_character_audit)
from dynamic_subject_agent.integrated_character_remote_preview import integrated_remote_request_preview
from dynamic_subject_agent.integrated_character_change_preview import CHANGE_POLICY, current_change_request_preview
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind


@pytest.fixture
def changes_fixture(integrated_live_fixture):
    opening, config, options, binding = integrated_live_fixture
    options['grant'] = ApprovedIntegratedCharacterGrant(APPROVED_CHANGE_REVIEW, True, 'change-evidence')
    return opening, config, options, binding


def started(fixture, *, source=False):
    transport = IntegratedTransport(); observations = []
    product = fixture[0](transport, observations)
    if source:
        assert send(product, '这一版保留窗边暖光。', 'changes-source-chat-1').status == 'terminal'
        assert select(product, '这一版保留窗边暖光。').status == 'committed'
    assert control(product, paused=False, sharing=True).status == 'committed'
    assert act(product).status == 'committed'
    return product, transport, observations


def task(product, kind, text='说说这次变化。'):
    response = (product.application.preview_natural_feedback(text) if kind is ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK
        else product.application.preview_living_activity('share' if kind is ModelTaskKind.LIVING_ACTIVITY_SHARE else 'choice'))
    assert response.status == 'previewed', response
    return ModelTask(kind, response.view)


def payload(transport):
    return json.loads(transport.calls[-1]['messages'][1]['content'])


def test_new_explicit_approval_preserves_old_grants_and_exact_reviewed_wire(changes_fixture):
    with pytest.raises(ValueError):
        ApprovedIntegratedCharacterGrant(APPROVED_INTEGRATED_REVIEW, True, 'change-evidence')
    with pytest.raises(ValueError):
        ApprovedIntegratedCharacterGrant(APPROVED_CHANGE_REVIEW, True, 'intent-text')
    product, transport, observations = started(changes_fixture, source=True)
    choice = task(product, ModelTaskKind.LIVING_ACTIVITY_CHOICE)
    assert 'current_result_change' not in choice.payload['payload']
    assert integrated_remote_request_preview(choice, technical_variant='change-evidence') == integrated_remote_request_preview(choice, technical_variant='intent-text')
    original = state(product)['current_plan']
    assert send(product, MESSAGE, 'changes-exact-edit-1').status == 'terminal'
    assert asdict(state(product)['current_plan']) == {key: value.replace('松架', '杉架') for key, value in asdict(original).items()}
    assert act(product, key='changes-after-feedback-choice').status == 'committed'
    for kind in (ModelTaskKind.LIVING_ACTIVITY_SHARE, ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK):
        proposed = task(product, kind)
        change = proposed.payload['payload']['current_result_change']
        assert change == dict(action='revise', changes=[dict(field='focus', before=PLAN['focus'], after='观察衣褶的明暗')], unexpanded_fields=[])
        base_payload = dict(proposed.payload['payload']); del base_payload['current_result_change']
        base = ModelTask(kind, dict(policy=proposed.payload['policy'][:-len('\n\n'+CHANGE_POLICY)], payload=base_payload))
        expected = current_change_request_preview(base, change)
        actual = integrated_remote_request_preview(proposed, technical_variant='change-evidence')
        assert actual == expected and actual['body']['max_tokens'] == 4096
        with pytest.raises(ValueError):
            integrated_remote_request_preview(proposed, technical_variant='intent-text')
        for bad in ({}, {'note':'not-approved'}):
            forged = deepcopy(proposed.payload)
            if bad:
                forged['payload'].update(bad)
            else:
                del forged['payload']['current_result_change']
            with pytest.raises(ValueError):
                integrated_remote_request_preview(ModelTask(kind, forged), technical_variant='change-evidence')
        if kind is ModelTaskKind.LIVING_ACTIVITY_SHARE:
            assert act(product, 'share', 'changes-share-first-1').status == 'committed'
        else:
            assert send(product, '说说这次变化。', 'changes-actual-reply-1').status == 'terminal'
        assert transport.calls[-1] == actual['body']
    saved, identity = history(product), (product.profile_id, product.timeline_id)
    product.close(); fresh = IntegratedTransport(); product = changes_fixture[0](fresh)
    assert history(product) == saved and (product.profile_id, product.timeline_id) == identity and not fresh.calls
    assert task(product, ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK).payload['payload']['current_result_change'] == change
    assert all(row['status']=='complete' for row in open_integrated_character_audit(changes_fixture[2]['audit_path']).snapshot())


def test_source_free_old_and_new_plans_still_hide_change_when_history_is_off(changes_fixture):
    product, transport, _ = started(changes_fixture)
    assert act(product, key='changes-source-free-revision').status == 'committed'
    assert state(product)['visible_result'].source_dependencies == ()
    assert task(product, ModelTaskKind.LIVING_ACTIVITY_SHARE).payload['payload']['current_result_change'] is not None
    assert product.application.set_reviewed_character_history(False).history_enabled is False
    assert control(product, paused=False, key='changes-source-free-resume').status == 'committed'
    for kind in (ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK, ModelTaskKind.LIVING_ACTIVITY_SHARE):
        proposed = task(product, kind)
        assert proposed.payload['payload']['current_result_change'] is None
        if kind is ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK:
            assert send(product, '现在这版如何？', 'changes-source-free-history-off').status == 'terminal'
        else:
            assert act(product, 'share', 'changes-source-free-share').status == 'committed'
        assert payload(transport)['current_result_change'] is None


def test_source_free_boundary_blocks_old_result_and_old_before_until_both_plans_are_new(changes_fixture):
    from dynamic_subject_agent.whole_context_boundary import WholeContextBoundaryRequest
    product, transport, _ = started(changes_fixture)
    assert act(product, key='changes-boundary-original-revision').status == 'committed'
    assert task(product, ModelTaskKind.LIVING_ACTIVITY_SHARE).payload['payload']['current_result_change'] is not None
    assert product.application.apply_whole_context_boundary(WholeContextBoundaryRequest(
        product.profile_id, product.timeline_id, 'changes-source-free-boundary', 0, True)).status == 'committed'
    assert control(product, paused=False, key='changes-boundary-resume').status == 'committed'
    assert state(product)['current_plan'] is not None
    for kind in (ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK, ModelTaskKind.LIVING_ACTIVITY_SHARE):
        assert task(product, kind).payload['payload']['current_result_change'] is None
    assert product.application.query_current_activity_change().view == dict(current_activity_change=None)
    transport.synthetic.override = dict(action='rework', plan=None, reason_code='try-alternative', basis_refs=[], decision_note='合成返工。')
    assert act(product, key='changes-boundary-rework').status == 'committed'
    current = asdict(state(product)['current_plan'])
    transport.synthetic.override = dict(action='revise', plan=dict(current, focus='边界后形成的新重点'),
        reason_code='try-alternative', basis_refs=[], decision_note='合成新的取舍。')
    assert act(product, key='changes-boundary-first-new-plan').status == 'committed'
    transport.synthetic.override = None
    assert state(product)['visible_result'].source_dependencies == ()
    for kind in (ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK, ModelTaskKind.LIVING_ACTIVITY_SHARE):
        assert task(product, kind).payload['payload']['current_result_change'] is None
    assert product.application.query_current_activity_change().view == dict(current_activity_change=None)
    assert send(product, MESSAGE, 'changes-boundary-second-new-plan').status == 'terminal'
    change = product.application.query_current_activity_change().view['current_activity_change']
    assert change is not None
    for kind in (ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK, ModelTaskKind.LIVING_ACTIVITY_SHARE):
        assert task(product, kind).payload['payload']['current_result_change'] == change


def test_source_revoke_filters_share_followup_lineage_and_new_independent_before_text(changes_fixture):
    product, transport, _ = started(changes_fixture, source=True)
    assert act(product, key='changes-dependent-revision').status == 'committed'
    old = state(product)['current_plan']
    assert act(product, 'share', 'changes-dependent-share').status == 'committed'
    assert send(product, '记着你刚说的变化。', 'changes-dependent-followup').status == 'terminal'
    assert select(product, '', None, 'changes-disable-source').status == 'committed'
    proposed = task(product, ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK)
    assert proposed.payload['payload']['current_result_change'] is None
    assert proposed.payload['payload']['evidence']['latest_share'] is None
    assert not proposed.payload['payload']['exchange']
    assert control(product, paused=False, key='changes-independent-resume').status == 'committed'
    # Revised phase requires a separate actual rework choice before the new plan.
    transport.synthetic.override = dict(action='rework', plan=None, reason_code='try-alternative', basis_refs=[], decision_note='合成转入返工。')
    assert act(product, key='changes-independent-rework').status == 'committed'
    transport.synthetic.override = dict(action='revise', plan=dict(subject='独立新主体', composition='独立新构图。', focus='独立新关注点'),
        reason_code='try-alternative', basis_refs=[], decision_note='合成独立新选择。')
    assert act(product, key='changes-independent-choice').status == 'committed'
    transport.synthetic.override = None
    result = state(product)['visible_result']
    assert result.source_dependencies == () and any(row.before == old.composition for row in result.differences)
    for kind in (ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK, ModelTaskKind.LIVING_ACTIVITY_SHARE):
        assert task(product, kind).payload['payload']['current_result_change'] is None
    assert send(product, '现在的新安排呢？', 'changes-independent-reply').status == 'terminal'
    assert payload(transport)['current_result_change'] is None


@pytest.mark.parametrize('race', ['permission', 'forged-change'])
def test_change_claim_rebuild_and_permission_race_never_send(changes_fixture, monkeypatch, race):
    product, transport, _ = started(changes_fixture)
    assert act(product, key='changes-race-revision').status == 'committed'
    previous = len(transport.calls)
    original = IntegratedCharacterDelivery.claim
    def altered(self, operation, proposal, rebuild):
        if race == 'forged-change':
            forged = deepcopy(proposal.payload)
            forged['payload']['current_result_change'] = None
            return original(self, operation, ModelTask(proposal.kind, forged), rebuild)
        original(self, operation, proposal, rebuild)
        product.application.set_reviewed_character_history(False)
    monkeypatch.setattr(IntegratedCharacterDelivery, 'claim', altered)
    assert send(product, '描述具体变化。', 'changes-first-race').status == 'failed-closed'
    assert len(transport.calls) == previous


@pytest.mark.parametrize('kind', ['feedback', 'share'])
def test_prepared_change_expression_recovers_without_losing_sources_or_resending(changes_fixture, monkeypatch, kind):
    from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint
    product, transport, _ = started(changes_fixture, source=True)
    assert act(product, key='changes-prepared-revision').status == 'committed'
    source_dependencies = set(state(product)['visible_result'].source_dependencies)
    request = action_request(product, 'share', 'changes-prepared-share')
    with monkeypatch.context() as crash:
        original = TimelineEngine._hit
        def hit(self, point):
            if point is FaultPoint.AFTER_PLAN_CLAIM:
                raise OSError('Synthetic prepared change-expression interruption')
            return original(self, point)
        crash.setattr(TimelineEngine, '_hit', hit)
        if kind == 'feedback':
            send(product, MESSAGE, 'changes-prepared-feedback')
        else:
            product.application.advance_living_activity(request)
    calls = len(transport.calls)
    product.close(); fresh = IntegratedTransport(); product = changes_fixture[0](fresh)
    assert not fresh.calls
    if kind == 'feedback':
        assert send(product, MESSAGE, 'changes-prepared-feedback').status == 'terminal'
        assert product.application.query_shared_activity().view['activity_revision'] == 3
        assert source_dependencies <= set(state(product)['visible_result'].source_dependencies)
    else:
        assert product.application.query_living_activity(request).status == 'replayed'
        assert source_dependencies <= set(state(product)['shares'][-1]['dependencies'])
    assert not fresh.calls and len(transport.calls) == calls


def test_expression_only_before_sources_never_become_plan_sources():
    from dynamic_subject_agent.integrated_character_changes import add_change_expression_dependencies
    from dynamic_subject_agent.shared_activity import initial_record, ActivityResult
    from dynamic_subject_agent.first_life import CompositionPlan, LifeFieldDiff, LifeEvent
    plan = CompositionPlan('主体', '新构图', '关注点')
    result = ActivityResult('composition-text', plan, 2, (LifeFieldDiff('composition','旧构图','新构图'),),
        LifeEvent('synthetic-event',2,'revise','summary',2,'try-alternative'), ('plan-source',))
    view = dict(visible_result=result,result_before_dependencies=('before-source',),valid_sources={'before-source','plan-source'},
        cutoff_sequence=0,result_before_plan_head=1)
    record = replace(initial_record(), plan=plan, result=result, source_dependencies=('plan-source',), reply_dependencies=('plan-source',),
        living=dict(considered=[dict(share=True)],shares=[dict(dependencies=['plan-source'])]))
    reply = add_change_expression_dependencies(record,view,enabled=True,ordinary=True)
    share = add_change_expression_dependencies(record,view,enabled=True,sharing=True)
    assert reply.reply_dependencies == ('before-source','plan-source')
    assert share.living['shares'][-1]['dependencies'] == ['before-source','plan-source']
    assert reply.source_dependencies == share.source_dependencies == result.source_dependencies == ('plan-source',)
    assert record.living['shares'][-1]['dependencies'] == ['plan-source']
