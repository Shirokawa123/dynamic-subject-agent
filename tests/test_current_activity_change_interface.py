"""Facade-only change evidence, using isolated synthetic character timelines."""
from dataclasses import asdict

import pytest

from test_original_whole_chat import approved, personality_fixture, model_fixture, send, history
from test_integrated_character import integrated_fixture, LocalAdapter, start
from test_living_activity import state, control, act
from test_shared_activity import select
from test_whole_chat_archive import canonical_path
from test_subject_request_lookup import counts
from dynamic_subject_agent.whole_context_boundary import WholeContextBoundaryRequest


def change(product):
    response = product.application.query_current_activity_change()
    assert response.status == 'available', response
    assert set(response.view) == {'current_activity_change'}
    return response.view['current_activity_change']


def revise_focus(product, adapter):
    plan = asdict(state(product)['current_plan'])
    adapter.override = dict(action='revise', plan=dict(plan, focus='先看窗边的衣褶'),
        reason_code='emphasize-subject', basis_refs=[], decision_note='合成取舍，不参与变化出站。')
    assert act(product, key='change-focus-revision-1').status == 'committed'
    adapter.override = None
    return dict(action='revise', changes=[dict(field='focus', before='手上的动作', after='窗边的衣褶')], unexpanded_fields=[])


def test_exact_changes_survive_chat_share_and_reopen_without_query_calls_or_publications(integrated_fixture):
    product, adapter = start(integrated_fixture, with_source=True)
    assert change(product) is None  # A first plan does not claim a revision.
    expected = revise_focus(product, adapter)
    original_query = product.application.query_shared_activity()
    share = product.application.preview_living_activity('share')
    reply = product.application.preview_natural_feedback('聊聊刚才的变化。')
    calls, before_counts = len(adapter.calls), counts(canonical_path(product))
    assert change(product) == expected
    assert change(product) == expected
    assert len(adapter.calls) == calls and counts(canonical_path(product)) == before_counts
    assert product.application.query_shared_activity() == original_query
    assert product.application.preview_living_activity('share') == share
    assert product.application.preview_natural_feedback('聊聊刚才的变化。') == reply
    assert 'current_activity_change' not in share.view['payload']
    assert 'current_activity_change' not in reply.view['payload']['evidence']
    assert act(product, 'share', 'change-share-first-1').status == 'committed'
    assert change(product) == expected
    assert send(product, '我们聊一个别的话题。', 'change-topic-first-1').status == 'terminal'
    assert change(product) == expected
    saved_history, identity = history(product), (product.profile_id, product.timeline_id)
    before_counts = counts(canonical_path(product))
    product.close()
    fresh = LocalAdapter(); product = integrated_fixture(fresh)
    assert (product.profile_id, product.timeline_id) == identity and history(product) == saved_history
    assert change(product) == expected and not fresh.calls
    assert counts(canonical_path(product)) == before_counts


@pytest.mark.parametrize('mode', ['history', 'context', 'source'])
def test_history_context_or_source_control_removes_the_whole_change_projection(integrated_fixture, mode):
    product, adapter = start(integrated_fixture, with_source=True)
    assert change(product) is None
    expected = revise_focus(product, adapter)
    assert change(product) == expected
    if mode == 'history':
        assert product.application.set_reviewed_character_history(False).history_enabled is False
    elif mode == 'context':
        assert product.application.apply_whole_context_boundary(WholeContextBoundaryRequest(
            product.profile_id, product.timeline_id, 'change-context-boundary-1', 0, True)).status == 'committed'
    else:
        assert select(product, '', None, 'change-disable-source-1').status == 'committed'
    calls, before_counts = len(adapter.calls), counts(canonical_path(product))
    assert change(product) is None
    assert len(adapter.calls) == calls and counts(canonical_path(product)) == before_counts


def test_new_independent_result_never_discloses_before_text_from_a_revoked_plan(integrated_fixture):
    product, adapter = start(integrated_fixture, with_source=True)
    old = state(product)['current_plan']
    assert select(product, '', None, 'change-revoke-old-plan-1').status == 'committed'
    assert state(product)['current_plan'] is None
    assert control(product, paused=False, key='change-resume-independent-1').status == 'committed'
    new = dict(subject='新独立主体', composition='新的独立文字安排。', focus='新独立关注点')
    adapter.override = dict(action='revise', plan=new, reason_code='try-alternative',
        basis_refs=[], decision_note='合成独立选择。')
    assert act(product, key='change-independent-revision-1').status == 'committed'
    current = state(product)
    assert asdict(current['current_plan']) == new and current['visible_result'].source_dependencies == ()
    assert current['visible_result'].differences[1].before == old.composition
    calls, before_counts = len(adapter.calls), counts(canonical_path(product))
    assert change(product) is None
    assert len(adapter.calls) == calls and counts(canonical_path(product)) == before_counts
    product.close()
    fresh = LocalAdapter(); product = integrated_fixture(fresh)
    assert asdict(state(product)['current_plan']) == new
    assert change(product) is None and not fresh.calls


def test_non_integrated_authority_has_no_change_projection(approved):
    product, _, _, _ = approved
    response = product.application.query_current_activity_change()
    assert response.status == 'unavailable' and response.view is None
