"""Unchanged arrangement context is not an extra Memory operation."""
import pytest
from test_mixed_goal_operations import WholeMemory, NoGoalModel
from test_natural_goals import goals
from test_scoped_preferences import records
from test_memory_write_receipts import open_composite
from test_recent_dialogue import submit

CREATE = '换个话题：周六我会带两块桌布去旧书交换会，也给自己定个目标：把书签的两句正文定下来。'
EDIT = '把目标“把书签的两句正文定下来”改成“先写好一句邀请”，桌布照带。'

@pytest.mark.parametrize('message', [EDIT, '书签这个目标我想改成先写好一句邀请，桌布照带。'])
def test_original_goal_edit_keeps_independent_arrangement(tmp_path, message):
    goal = NoGoalModel()
    opened = open_composite(tmp_path, WholeMemory(), goal=goal)
    try:
        submit(opened, CREATE)
        before = records(opened)
        result = submit(opened, message)
        assert result.projection.participant_goal_commitment_status == 'accepted'
        assert [g.terms for g in goals(opened) if g.status=='active'] == ['先写好一句邀请']
        assert records(opened)==before
        assert goal.calls==[]
    finally:
        opened.app.close()

@pytest.mark.parametrize('item', ['雨伞', '画板', '三盒彩笔', 'A4纸'])
def test_other_literal_objects_do_not_need_a_name_allowlist_or_create_memories(tmp_path, item):
    opened = open_composite(tmp_path, WholeMemory(), goal=NoGoalModel())
    try:
        submit(opened, CREATE)
        before = records(opened)
        result = submit(opened, f'把目标“把书签的两句正文定下来”改成“先写好一句邀请”，{item}照带。')
        assert result.projection.participant_goal_commitment_status == 'accepted'
        assert records(opened)==before
        assert all(item not in r.content for r in records(opened))
    finally:
        opened.app.close()

@pytest.mark.parametrize('tail', ['如果晴天桌布照带', '桌布不照带', '取消目标桌布照带',
    '桌布换成雨伞照带', '桌布照带，雨伞也照带', '桌布照带。我的目标是跳舞', '“桌布照带”'])
@pytest.mark.parametrize('named', [False, True])
def test_conditions_negation_operations_and_multiple_tails_do_not_change_either_inventory(tmp_path, tail, named):
    opened = open_composite(tmp_path, WholeMemory(), goal=NoGoalModel())
    try:
        submit(opened, CREATE)
        old_memories, old_goals = records(opened), goals(opened)
        prefix = '书签这个目标我想改成先写好一句邀请' if named else '把目标“把书签的两句正文定下来”改成“先写好一句邀请”'
        result = submit(opened, prefix + '，' + tail + '。')
        # An independent second goal remains its own operation; never silently
        # accept the first edit or revise the arrangement from its tail.
        assert not any(g.terms=='先写好一句邀请' for g in goals(opened) if g.status=='active')
        assert records(opened)==old_memories
        if '我的目标' not in tail:
            assert goals(opened)==old_goals
    finally:
        opened.app.close()

def test_restart_restores_modified_goal_and_unchanged_arrangement(tmp_path):
    opened = open_composite(tmp_path, WholeMemory(), goal=NoGoalModel())
    try:
        submit(opened, CREATE)
        before = records(opened)
        submit(opened, EDIT)
        after = goals(opened)
        opened.app.close()
        opened = open_composite(tmp_path, WholeMemory(), goal=NoGoalModel(), saved=opened)
        assert records(opened)==before and goals(opened)==after
    finally:
        opened.app.close()
