from dynamic_subject_agent.living_memory import LivingMemoryReplyResult
from test_grounded_role_expression import MemoryProvider, KnowledgeProvider, turn
import pytest


REQUEST = '明天晚上我想写完给邻居的明信片，提醒我下次聊天时接着写。'


@pytest.mark.parametrize('evidence', [REQUEST, ''])
def test_saved_plan_cannot_be_confirmed_as_a_scheduled_reminder(tmp_path, evidence):
    promise = '好的，下次聊天时我会提醒你接着写明信片。'
    result = turn(tmp_path, REQUEST, KnowledgeProvider('没有资料。'), knowledge=True,
        also_memory=MemoryProvider(promise, evidence=evidence, refined=LivingMemoryReplyResult(promise, 'zh')))
    assert result.living_memory_status == ('accepted' if evidence else 'no-op')
    assert promise not in result.expression_text
    assert '提醒' in result.expression_text
    assert '不能' in result.expression_text or '不提供' in result.expression_text


def test_memory_failure_cannot_confirm_saved_plan(tmp_path):
    class Failed(MemoryProvider):
        def propose(self, request):
            raise RuntimeError('synthetic failure')
    result = turn(tmp_path, REQUEST, KnowledgeProvider('没有资料。'), knowledge=True,
        also_memory=Failed('我会提醒你。'))
    assert result.living_memory_status == 'failed-closed'
    assert '已记录' not in result.expression_text
    assert '未能完成记忆记录' in result.expression_text
    assert '不提供定时提醒' in result.expression_text


@pytest.mark.parametrize('message,kind,text', [
    ('请写一个虚构故事：人物说“我会提醒你。”', 'creative', '机器人说：“我会提醒你。”'),
    ('“明天提醒我喝水”这句话表达了什么？', 'conversation', '它表达了希望获得提醒的请求。'),
    ('现在提醒我一下刚才的计划是什么。', 'conversation', '你打算写一张明信片。'),
])
def test_fiction_quotation_and_current_recall_are_not_scheduled_tasks(tmp_path, message, kind, text):
    result = turn(tmp_path, message, KnowledgeProvider('没有资料。'), knowledge=True,
        also_memory=MemoryProvider(text, refined=LivingMemoryReplyResult(text, 'zh', kind)))
    assert text in result.expression_text


def test_greeting_cannot_revive_a_future_reminder_promise(tmp_path):
    result = turn(tmp_path, '你好，我回来了。', KnowledgeProvider('没有资料。'), knowledge=True,
        also_memory=MemoryProvider('我会在下次聊天时提醒你。'))
    assert '我会在下次聊天时提醒你' not in result.expression_text
    assert '不提供定时提醒' in result.expression_text


def test_declining_reminder_does_not_claim_to_cancel_a_task(tmp_path):
    result = turn(tmp_path, '不用再提醒我了。', KnowledgeProvider('没有资料。'), knowledge=True,
        also_memory=MemoryProvider('提醒已取消。'))
    assert '提醒已取消' not in result.expression_text
    assert '不提供定时提醒' in result.expression_text


@pytest.mark.parametrize('message,kind,text', [
    ('现在提醒我一下刚才的计划是什么。', 'conversation', '我可以提醒你：你打算写一张明信片。'),
    ('现在提醒我一下刚才的计划是什么。', 'conversation', '我可以提醒你：你打算明天写一张明信片。'),
    ('“我会提醒你”这句话表达了什么？', 'conversation', '“我会提醒你”表达了一项承诺。'),
    ('请写一个虚构故事：人物说，明天提醒我喝水。', 'creative', '人物说：“明天提醒我喝水。”'),
])
def test_reminder_words_keep_current_recall_reference_and_story_scope(tmp_path, message, kind, text):
    result = turn(tmp_path, message, KnowledgeProvider('没有资料。'), knowledge=True,
        also_memory=MemoryProvider(text, refined=LivingMemoryReplyResult(text, 'zh', kind)))
    assert text in result.expression_text


@pytest.mark.parametrize('message,goal_reply', [
    ('下次提醒我接着写。', '提醒已设置成功。'),
    ('我喜欢深蓝色。请写一句祝福。', '下次聊天时我会提醒你。'),
])
def test_other_capability_cannot_restore_reminder_claim(tmp_path, message, goal_reply):
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from dynamic_subject_agent.runtime import M0_A_PROVIDER_AUTHORITY
    from dynamic_subject_agent.model_gateway import ModelGateway, ProviderCapabilities, StructuredOutputMode
    from dynamic_subject_agent.participant_goal_cognition import ParticipantGoalProviderAdapter, ParticipantGoalClassificationResult, ParticipantGoalReplyResult
    from test_situated_integration import _NoopKnowledgeProvider, _NoopRelationshipProvider
    from test_recent_dialogue import open_app, submit
    class Goal:
        def classify(self, request):
            return ParticipantGoalClassificationResult(None, tuple(r.turn_ref for r in request.active_records), '选中既有目标。', 'zh')
        def reply(self, request):
            return ParticipantGoalReplyResult(goal_reply, 'zh')
    class Memory(MemoryProvider):
        def propose(self, request):
            self.evidence = '我喜欢深蓝色' if request.current_user_message.startswith('我喜欢') else ''
            return super().propose(request)
    memory = Memory('普通回复。', refined=LivingMemoryReplyResult('愿你安稳。', 'zh', 'creative'))
    knowledge, relationship = _NoopKnowledgeProvider(), _NoopRelationshipProvider()
    for provider in (knowledge, relationship):
        provider.provider_authority = M0_A_PROVIDER_AUTHORITY
    gateway = ModelGateway(ParticipantGoalProviderAdapter(provider=Goal(), capabilities=ProviderCapabilities(
        M0_A_PROVIDER_AUTHORITY, 'test-goal', True, (StructuredOutputMode.JSON_OBJECT,))))
    opened = open_app(tmp_path, memory, cognition=ControlledCompositeCognition(memory_provider=memory,
        knowledge_provider=knowledge, relationship_provider=relationship, participant_goal_gateway=gateway))
    try:
        submit(opened, '我的目标是今年通过 N1。')
        result = submit(opened, message)
        assert goal_reply not in result.projection.expression_text
        if message.startswith('我喜欢'):
            assert '愿你安稳' in result.projection.expression_text
            assert result.projection.living_memory_status == 'accepted'
    finally:
        opened.app.close()


def test_factual_boundary_does_not_replace_reminder_boundary(tmp_path):
    result = turn(tmp_path, '下次提醒我判断这张票是什么纸。', KnowledgeProvider('没有资料。'), knowledge=True,
        also_memory=MemoryProvider('我会提醒你。'))
    assert '不提供定时提醒' in result.expression_text
    assert '资料' in result.expression_text


def test_wrong_creative_label_does_not_hide_independent_source(tmp_path):
    from test_grounded_role_expression import ENTRY
    from dynamic_subject_agent.knowledge import KnowledgeReplyResult
    result = turn(tmp_path, '下次提醒我看看纸灯节。纸灯节在哪举行？',
        KnowledgeProvider('来源外的承诺。', refined=KnowledgeReplyResult('我会提醒你。', 'zh', 'creative')), knowledge=True,
        also_memory=MemoryProvider('我会提醒你。', refined=LivingMemoryReplyResult('我会提醒你。', 'zh', 'creative')))
    assert ENTRY.content in result.expression_text
    assert '不提供定时提醒' in result.expression_text
