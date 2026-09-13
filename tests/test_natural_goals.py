"""Natural goal changes must preserve independently declared arrangements."""
from dynamic_subject_agent.living_memory import LivingMemoryAction, LivingMemoryProposal, LivingMemoryProviderResult
from dynamic_subject_agent.participant_goal_cognition import ParticipantGoalClassificationResult, ParticipantGoalReplyResult
from dynamic_subject_agent.participant_goals import ParticipantGoalCommitmentCandidate
from test_recent_dialogue import DialogueProvider, submit
from test_memory_write_receipts import open_composite
from test_scoped_preferences import records
from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
import pytest

CREATE = '周六我准备请两个朋友来吃早餐；我也给自己定个目标：在周五前把菜单想清楚。'
REVISE = '菜单这个目标我想改成先定下三道菜，朋友来吃早餐的安排不变。'
PLAN = '周六我准备请两个朋友来吃早餐；'

class Memory(DialogueProvider):
    def propose(self, request):
        self.proposals.append(request)
        return LivingMemoryProviderResult(LivingMemoryProposal(
            LivingMemoryAction.REVISE if request.current_user_message == REVISE else LivingMemoryAction.CREATE,
            request.current_user_message, request.active_memories[0].memory_id if request.current_user_message == REVISE else None,
            memory_kind='plan'), '提出候选。', '收到。', 'zh')

class Goal:
    def classify(self, request):
        if request.current_user_message == CREATE:
            return ParticipantGoalClassificationResult(ParticipantGoalCommitmentCandidate('create', 'goal', '在周五前把菜单想清楚',
                None, 'active', '我也给自己定个目标：在周五前把菜单想清楚'), (), '提出目标。', 'zh')
        raise OSError('synthetic unsupported natural revision')
    def reply(self, request):
        return ParticipantGoalReplyResult('目标以最终结果为准。', 'zh')

def goals(opened):
    return opened.app.application.query(ApplicationQuery(ApplicationQueryKind.PARTICIPANT_GOALS,
        opened.qri.profile_id, opened.timeline)).projection.records

def test_original_natural_goal_creation_and_revision(tmp_path):
    opened = open_composite(tmp_path, Memory(), goal=Goal())
    try:
        created = submit(opened, CREATE)
        assert created.projection.participant_goal_commitment_status == 'accepted'
        assert [g.terms for g in goals(opened)] == ['在周五前把菜单想清楚']
        assert [m.content for m in records(opened) if m.status == 'active'] == [PLAN]
        before = records(opened)
        revised = submit(opened, REVISE)
        assert revised.projection.participant_goal_commitment_status == 'accepted'
        assert [g.terms for g in goals(opened) if g.status == 'active'] == ['先定下三道菜']
        assert records(opened) == before
        again = submit(opened, '菜单这个目标我想改成列好采购清单，安排不变。')
        assert again.projection.participant_goal_commitment_status == 'accepted'
        assert [g.terms for g in goals(opened) if g.status == 'active'] == ['列好采购清单']
        assert records(opened) == before
    finally:
        opened.app.close()


@pytest.mark.parametrize('create,revise,expected', [
    ('我也给自己定一个目标：这个月整理旅行照片。', '旅行照片这项目标我希望换成先整理十张照片，安排保持不变。', '先整理十张照片'),
    ('我给自己定个目标：每周练习法语。', '法语这个目标我想改为每天练习十分钟。', '每天练习十分钟'),
])
def test_other_current_goal_labels_and_actions(tmp_path, create, revise, expected):
    class UnusedGoal(Goal):
        def classify(self, request):
            raise AssertionError('explicit local route must not need a classifier')
    opened = open_composite(tmp_path, DialogueProvider(), goal=UnusedGoal())
    try:
        assert submit(opened, create).projection.participant_goal_commitment_status == 'accepted'
        assert submit(opened, revise).projection.participant_goal_commitment_status == 'accepted'
        assert [g.terms for g in goals(opened) if g.status == 'active'] == [expected]
    finally:
        opened.app.close()


def test_same_label_on_two_goals_requires_disambiguation(tmp_path):
    opened = open_composite(tmp_path, DialogueProvider(), goal=Goal())
    try:
        submit(opened, '我的目标是完成早餐菜单。')
        submit(opened, '我的目标是完成晚餐菜单。')
        before = goals(opened)
        answer = submit(opened, '菜单这个目标我想改成先定下三道菜。')
        assert answer.projection.participant_goal_commitment_status == 'rejected'
        assert '不能确定' in answer.projection.expression_text
        assert goals(opened) == before
    finally:
        opened.app.close()


@pytest.mark.parametrize('message', [
    '朋友说：“菜单这个目标我想改成先定下三道菜。”',
    '如果菜单这个目标我想改成先定下三道菜，你怎么看？',
    '朋友的菜单这个目标我想改成先定下三道菜。',
    '菜单这个目标我想改成先定下三道菜，但只有朋友确定来才做。',
    '菜单这个目标我想改成先定下三道菜。算了，不要保存。',
    '菜单这个目标我想改成先定下三道菜。我的目标改为只做一道菜。',
])
def test_unsupported_or_conflicting_revision_cannot_change_goal_or_plan(tmp_path, message):
    class Proposed(Memory):
        def propose(self, request):
            if request.current_user_message == CREATE:
                return super().propose(request)
            return LivingMemoryProviderResult(LivingMemoryProposal(LivingMemoryAction.NONE, ''), '没有记忆变化。', '收到。', 'zh')
    class MaliciousGoal(Goal):
        def classify(self, request):
            return ParticipantGoalClassificationResult(ParticipantGoalCommitmentCandidate('revise', 'goal', '先定下三道菜',
                request.active_records[0].turn_ref, 'active', '菜单这个目标我想改成先定下三道菜'), (), '提出修改。', 'zh')
    opened = open_composite(tmp_path, Proposed(), goal=MaliciousGoal())
    try:
        submit(opened, CREATE)
        old_goals, old_memories = goals(opened), records(opened)
        answer = submit(opened, message)
        assert answer.projection.participant_goal_commitment_status != 'accepted'
        assert goals(opened) == old_goals
        assert records(opened) == old_memories
    finally:
        opened.app.close()


@pytest.mark.parametrize('complete', [False, True])
def test_natural_selection_uses_full_local_inventory_not_provider_window(tmp_path, monkeypatch, complete):
    from dataclasses import replace
    from dynamic_subject_agent.participant_goal_cognition import ControlledParticipantGoalCognition
    original = ControlledParticipantGoalCognition.propose
    def narrow(self, *, context, command, **kwargs):
        if command.utterance.startswith('菜单这个'):
            context = replace(context, participant_goal_commitments=(), participant_goal_inventory_complete=complete)
        return original(self, context=context, command=command, **kwargs)
    monkeypatch.setattr(ControlledParticipantGoalCognition, 'propose', narrow)
    opened = open_composite(tmp_path, DialogueProvider(), goal=Goal())
    try:
        submit(opened, '我的目标是完成菜单。')
        submit(opened, '我的目标是每天阅读。')
        before = goals(opened)
        result = submit(opened, '菜单这个目标我想改成先定下三道菜。')
        assert result.projection.participant_goal_commitment_status == ('accepted' if complete else 'rejected')
        if not complete:
            assert goals(opened) == before
    finally:
        opened.app.close()


@pytest.mark.parametrize('tail', ['如果下雨早餐安排不变', '早餐取消但午餐安排不变',
    '假设下雨早餐安排不变', '只有晴天早餐安排不变'])
def test_mixed_change_is_not_disguised_as_an_unchanged_arrangement(tmp_path, tail):
    class Whole(Memory):
        def propose(self, request):
            if request.current_user_message == CREATE:
                return super().propose(request)
            return LivingMemoryProviderResult(LivingMemoryProposal(LivingMemoryAction.REVISE, request.current_user_message,
                request.active_memories[0].memory_id, memory_kind='plan'), '提出修改。', '收到。', 'zh')
    opened = open_composite(tmp_path, Whole(), goal=Goal())
    try:
        submit(opened, CREATE)
        old_goals, old_memories = goals(opened), records(opened)
        result = submit(opened, '菜单这个目标我想改成只做两道菜，' + tail + '。')
        assert result.projection.participant_goal_commitment_status == 'rejected'
        assert result.projection.living_memory_status == 'rejected'
        assert goals(opened) == old_goals and records(opened) == old_memories
    finally:
        opened.app.close()


def test_unknown_named_goal_does_not_select_an_unrelated_singleton(tmp_path):
    opened = open_composite(tmp_path, DialogueProvider(), goal=Goal())
    try:
        submit(opened, '我的目标是每天练习法语。')
        before = goals(opened)
        result = submit(opened, '菜单这个目标我想改成先定下三道菜。')
        assert result.projection.participant_goal_commitment_status == 'rejected'
        assert goals(opened) == before
    finally:
        opened.app.close()
