"""Independent mixed-scene failures through ApplicationFacade."""
import pytest
from dynamic_subject_agent.living_memory import LivingMemoryAction, LivingMemoryProposal, LivingMemoryProviderResult
from test_natural_goals import Goal, goals
from test_recent_dialogue import DialogueProvider, submit
from test_memory_write_receipts import open_composite
from test_scoped_preferences import records

CREATE = '换个话题：周日我会带三把椅子去修补工坊，也给自己定个目标：把展台卡片的底稿交出来。'
REVISE = '把“把展台卡片的底稿交出来”改成“先定下卡片的两句正文”，椅子照带。'
DIAGNOSTIC = '（诊断对照）我给自己定个目标：把工具箱标签按尺寸重新排一遍。'
DIAGNOSTIC_REVISE = '把目标“把工具箱标签按尺寸重新排一遍”改成“先把常用三种工具分开贴标签”。'

class WholeMemory(DialogueProvider):
    def propose(self, request):
        self.proposals.append(request)
        revise = request.current_user_message.startswith('把') and bool(request.active_memories)
        return LivingMemoryProviderResult(LivingMemoryProposal(
            LivingMemoryAction.REVISE if revise else LivingMemoryAction.CREATE,
            request.current_user_message,
            request.active_memories[0].memory_id if revise else None, memory_kind='plan'), '提出候选。', '收到。', 'zh')

class NoGoalModel(Goal):
    def __init__(self):
        self.calls = []
    def classify(self, request):
        self.calls.append(request)
        raise OSError('synthetic classification failure')

@pytest.mark.parametrize('create,revise,old,new', [
    (CREATE, REVISE, '把展台卡片的底稿交出来', '先定下卡片的两句正文'),
    (DIAGNOSTIC, DIAGNOSTIC_REVISE, '把工具箱标签按尺寸重新排一遍', '先把常用三种工具分开贴标签'),
])
def test_independent_original_create_and_revision(tmp_path, create, revise, old, new):
    provider = NoGoalModel()
    opened = open_composite(tmp_path, WholeMemory(), goal=provider)
    try:
        result = submit(opened, create)
        assert result.projection.participant_goal_commitment_status == 'accepted'
        assert [g.terms for g in goals(opened) if g.status == 'active'] == [old]
        saved = records(opened)
        assert all(old not in m.content for m in saved)
        if create == CREATE:
            assert any('三把椅子去修补工坊' in m.content for m in saved)
        result = submit(opened, revise)
        assert result.projection.participant_goal_commitment_status == 'accepted'
        assert [g.terms for g in goals(opened) if g.status == 'active'] == [new]
        assert records(opened) == saved
        assert provider.calls == []
    finally:
        opened.app.close()


@pytest.mark.parametrize('create,old,new', [
    ('说正事：明天下午我准备带点心去读书会，也给自己定一个目标：读完散文集。', '读完散文集', '先读完前两章'),
    ('换个话题：我也给自己定一个目标：练习陶笛。', '练习陶笛', '练会一首小曲'),
])
def test_other_topics_and_exact_quoted_targets(tmp_path, create, old, new):
    opened = open_composite(tmp_path, WholeMemory(), goal=NoGoalModel())
    try:
        assert submit(opened, create).projection.participant_goal_commitment_status == 'accepted'
        submit(opened, '我的目标是每天散步。')
        before = records(opened)
        result = submit(opened, f'把目标「{old}」换成「{new}」，计划保持不变。')
        assert result.projection.participant_goal_commitment_status == 'accepted'
        assert {g.terms for g in goals(opened) if g.status == 'active'} == {new, '每天散步'}
        assert records(opened) == before
    finally:
        opened.app.close()


@pytest.mark.parametrize('message', [
    '把目标“缺失的目标”改成“新内容”。',
    '把目标“读完散文集”改成“先读两章”，如果晴天安排不变。',
    '把目标“读完散文集”改成“先读两章”，椅子不带了。',
    '把目标“读完散文集”改成“先读两章”。算了，不要保存。',
    '把目标“读完散文集」改成“先读两章”。',
    '把目标“读完散文集”改成“先读两章”。我的目标是学习摄影。',
])
def test_explicit_invalid_edits_never_replace_independent_memory(tmp_path, message):
    opened = open_composite(tmp_path, WholeMemory(), goal=NoGoalModel())
    try:
        submit(opened, '说正事：明天我会带点心去读书会，也给自己定个目标：读完散文集。')
        old_goals, old_memories = goals(opened), records(opened)
        answer = submit(opened, message)
        assert answer.projection.participant_goal_commitment_status != 'accepted'
        assert goals(opened) == old_goals and records(opened) == old_memories
    finally:
        opened.app.close()


@pytest.mark.parametrize('message', [
    '如果明天我会带点心去读书会，也给自己定个目标：读完散文集。',
    '换个话题：如果明天我会带点心去读书会，也给自己定个目标：读完散文集。',
    '朋友说：“（诊断对照）我给自己定个目标：读完散文集。”',
    '周日她会带点心去读书会，也给自己定个目标：读完散文集。',
])
def test_provider_cannot_promote_condition_or_other_speaker_to_goal(tmp_path, message):
    from dynamic_subject_agent.participant_goal_cognition import ParticipantGoalClassificationResult
    from dynamic_subject_agent.participant_goals import ParticipantGoalCommitmentCandidate
    class Proposed(NoGoalModel):
        def classify(self, request):
            evidence = '（诊断对照）我给自己定个目标：读完散文集' if '诊断对照' in message else '也给自己定个目标：读完散文集'
            return ParticipantGoalClassificationResult(ParticipantGoalCommitmentCandidate(
                'create', 'goal', '读完散文集', None, 'active', evidence), (), '提出候选。', 'zh')
    opened = open_composite(tmp_path, DialogueProvider(), goal=Proposed())
    try:
        result = submit(opened, message)
        assert result.projection.participant_goal_commitment_status != 'accepted'
        assert goals(opened) == ()
    finally:
        opened.app.close()


@pytest.mark.parametrize('prefix', ['朋友说：', '如果晴天就', '我昨天说过：'])
def test_provider_cannot_unwrap_quoted_revision(tmp_path, prefix):
    from dynamic_subject_agent.participant_goal_cognition import ParticipantGoalClassificationResult
    from dynamic_subject_agent.participant_goals import ParticipantGoalCommitmentCandidate
    command = '把目标“读完散文集”改成“先读两章”'
    class Proposed(NoGoalModel):
        def classify(self, request):
            return ParticipantGoalClassificationResult(ParticipantGoalCommitmentCandidate(
                'revise', 'goal', '先读两章', request.active_records[0].turn_ref, 'active', command), (), '提出候选。', 'zh')
    opened = open_composite(tmp_path, DialogueProvider(), goal=Proposed())
    try:
        submit(opened, '我的目标是读完散文集。')
        before = goals(opened)
        result = submit(opened, prefix + command + '。')
        assert result.projection.participant_goal_commitment_status != 'accepted'
        assert goals(opened) == before
    finally:
        opened.app.close()


@pytest.mark.parametrize('prefix,suffix', [('朋友说：“', '。”'), ('如果晴天，就', '。')])
def test_memory_provider_cannot_lift_a_reported_goal_edit(tmp_path, prefix, suffix):
    command = '把目标「读完散文集」改成「先读两章」'
    class Lifted(WholeMemory):
        def propose(self, request):
            if request.current_user_message.startswith(prefix):
                return LivingMemoryProviderResult(LivingMemoryProposal(LivingMemoryAction.REVISE,
                    command, request.active_memories[0].memory_id, memory_kind='plan'), '提出修改。', '收到。', 'zh')
            return super().propose(request)
    opened = open_composite(tmp_path, Lifted(), goal=NoGoalModel())
    try:
        submit(opened, '明天我会带点心去读书会，也给自己定个目标：读完散文集。')
        old_goals, old_memories = goals(opened), records(opened)
        result = submit(opened, prefix + command + suffix)
        assert result.projection.living_memory_status == 'rejected'
        assert goals(opened) == old_goals and records(opened) == old_memories
    finally:
        opened.app.close()
