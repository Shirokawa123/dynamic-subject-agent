from dataclasses import replace

import pytest

from dynamic_subject_agent.current_activity_change import current_activity_change, validate_current_activity_change
from dynamic_subject_agent.first_life import CompositionPlan, LifeEvent, LifeFieldDiff
from dynamic_subject_agent.shared_activity import ActivityResult


def changed(before, after, *, field='composition'):
    plan = CompositionPlan('当前主体', '当前构图', '当前关注点')
    plan = replace(plan, **{field: after})
    result = ActivityResult('composition-text', plan, 2, (LifeFieldDiff(field, before, after),),
        LifeEvent('local-event', 3, 'revise', '本地摘要不可出站', 2, 'try-alternative'), ('new-source',))
    return dict(visible_result=result, result_before_dependencies=('old-source',), valid_sources={'old-source', 'new-source'})


@pytest.mark.parametrize('before,after,old,new', [
    ('窗边冷光照衣褶。', '窗边暖光照衣褶。', '冷', '暖'),
    ('窗边衣架。', '窗边木质衣架。', '', '木质'),
    ('窗边木质衣架。', '窗边衣架。', '木质', ''),
    ('甲旧中间旧乙', '甲新中间新乙', '旧中间旧', '新中间新'),
    ('甲乙甲', '甲乙甲乙甲', '', '乙甲'),
])
def test_minimal_cover_keeps_every_change_including_insertions_and_deletions(before, after, old, new):
    assert current_activity_change(changed(before, after)) == dict(action='revise',
        changes=[dict(field='composition', before=old, after=new)], unexpanded_fields=[])


@pytest.mark.parametrize('before_count,after_count,expanded', [(160, 240, True), (161, 240, False), (160, 241, False)])
def test_bounds_are_exact_and_never_truncate(before_count, after_count, expanded):
    old, new = '旧' * before_count, '新' * after_count
    result = current_activity_change(changed('前'+old+'后', '前'+new+'后'))
    assert result == dict(action='revise',
        changes=[dict(field='composition', before=old, after=new)] if expanded else [],
        unexpanded_fields=[] if expanded else ['composition'])


def test_three_fields_are_once_and_long_change_does_not_hide_other_fields():
    view = changed('旧'*161, '新'*241)
    result = view['visible_result']
    plan = replace(result.plan, subject='新主体', focus='新关注点')
    view['visible_result'] = replace(result, plan=plan, differences=(
        LifeFieldDiff('focus', '旧关注点', '新关注点'), *result.differences, LifeFieldDiff('subject', '旧主体', '新主体')))
    assert current_activity_change(view) == dict(action='revise', changes=[
        dict(field='subject', before='旧', after='新'), dict(field='focus', before='旧', after='新')],
        unexpanded_fields=['composition'])


@pytest.mark.parametrize('mode', ['before-revoked', 'before-unknown', 'before-missing', 'current-revoked', 'valid-missing'])
def test_both_sides_need_complete_current_permission_proof(mode):
    view = changed('此前不可外发的旧文字', '当前新文字')
    if mode == 'before-revoked':
        view['valid_sources'] = {'new-source'}
    elif mode == 'before-unknown':
        view['result_before_dependencies'] = None
    elif mode == 'before-missing':
        del view['result_before_dependencies']
    elif mode == 'current-revoked':
        view['valid_sources'] = {'old-source'}
    else:
        del view['valid_sources']
    assert current_activity_change(view) is None


def test_verified_independent_before_basis_is_different_from_unknown_basis():
    view = changed('旧文字', '新文字')
    view['result_before_dependencies'] = ()
    view['valid_sources'] = {'new-source'}
    assert current_activity_change(view)['changes'] == [dict(field='composition', before='旧', after='新')]
    view['result_before_dependencies'] = ''
    assert current_activity_change(view) is None


@pytest.mark.parametrize('kind', ['start', 'keep', 'defer', 'rework'])
def test_only_actual_revision_has_change_projection(kind):
    view = changed('旧', '新')
    result = view['visible_result']
    view['visible_result'] = replace(result, event=replace(result.event, kind=kind))
    assert current_activity_change(view) is None
    view['visible_result'] = None
    assert current_activity_change(view) is None


@pytest.mark.parametrize('difference', [LifeFieldDiff('composition', '旧', '与当前方案不符'),
    LifeFieldDiff('unknown', '旧', '新'), LifeFieldDiff('composition', '新', '新')])
def test_inconsistent_difference_cannot_be_reported(difference):
    view = changed('旧', '新')
    view['visible_result'] = replace(view['visible_result'], differences=(difference,))
    with pytest.raises(ValueError):
        current_activity_change(view)


@pytest.mark.parametrize('malformed', [
    dict(action='revise', changes=[], unexpanded_fields=[]),
    dict(action='revise', changes=[], unexpanded_fields=['composition'], note='内部理由'),
    dict(action='keep', changes=[], unexpanded_fields=['composition']),
    dict(action='revise', changes=[], unexpanded_fields=['composition', 'composition']),
    dict(action='revise', changes=[dict(field='composition', before='', after='新')], unexpanded_fields=['composition']),
    dict(action='revise', changes=[dict(field='composition', before='', after='')], unexpanded_fields=[]),
    dict(action='revise', changes=[dict(field='composition', before='旧'*161, after='新')], unexpanded_fields=[]),
])
def test_projection_validator_is_closed_and_bounded(malformed):
    assert validate_current_activity_change(None) is None
    with pytest.raises(ValueError):
        validate_current_activity_change(malformed)
