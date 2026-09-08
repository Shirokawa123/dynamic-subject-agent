"""Interface regressions for confirmed forward-only logical forgetting."""
from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from dynamic_subject_agent.living_memory import (
    LivingMemoryAction, LivingMemoryProposal, LivingMemoryProviderResult, LivingMemoryReplyResult,
)
from test_recent_dialogue import open_app, submit
import pytest


class ReportedForgetProvider:
    """External-boundary fixture preserving the independent report's NoOp symptom."""
    def propose(self, request):
        created = request.current_user_message == '我叫陆禾。'
        return LivingMemoryProviderResult(
            LivingMemoryProposal(LivingMemoryAction.CREATE if created else LivingMemoryAction.NONE,
                '我叫陆禾。' if created else ''), '本轮记忆处理。',
            '记下了。' if created else '好的，之前那个名字我不会再用了。', 'zh')

    def reply(self, request):
        return LivingMemoryReplyResult('好的，之前那个名字我不会再用了。', 'zh')


def test_natural_name_forget_cannot_leave_the_name_active(tmp_path):
    opened = open_app(tmp_path, ReportedForgetProvider())
    try:
        submit(opened, '我叫陆禾。')
        forgotten = submit(opened, '这里叫我访客就好。把我之前报的名字忘掉，不用再保存了。')
        assert forgotten.projection.memory_withdrawal_status == 'accepted'
        assert '旧聊天和本地审计原文仍保留' in forgotten.projection.expression_text
        result = opened.app.application.query(ApplicationQuery(ApplicationQueryKind.LIVING_MEMORY,
            opened.qri.profile_id, opened.timeline))
        assert not any(item.status == 'active' and '陆禾' in item.content
            for item in result.projection.memories)
    finally:
        opened.app.close()


class RecordingProvider:
    def __init__(self):
        self.proposals, self.replies = [], []

    def propose(self, request):
        self.proposals.append(request)
        created = request.current_user_message in {'我叫陆禾。', '我喜欢深蓝色。', '我叫林间。'}
        return LivingMemoryProviderResult(LivingMemoryProposal(
            LivingMemoryAction.CREATE if created else LivingMemoryAction.NONE,
            request.current_user_message if created else '',
            recalled_memory_ids=() if created else tuple(m.memory_id for m in request.active_memories)),
            '处理本轮内容。', '收到。', 'zh')

    def reply(self, request):
        self.replies.append(request)
        return LivingMemoryReplyResult('；'.join(m.content for m in request.selected_memories) or '当前没有召回内容。', 'zh')


def test_withdrawal_survives_restart_preserves_other_memory_and_historical_text(tmp_path):
    provider = RecordingProvider()
    original = open_app(tmp_path, provider)
    first = submit(original, '我叫陆禾。')
    submit(original, '我喜欢深蓝色。')
    submit(original, '请忘记我的名字。')
    original.app.close()
    fresh = RecordingProvider()
    restarted = open_app(tmp_path, fresh, saved=original)
    try:
        reply = submit(restarted, '你现在还记得哪些内容？')
        assert '陆禾' not in reply.projection.expression_text
        assert '深蓝色' in reply.projection.expression_text
        assert all('陆禾' not in m.content for request in fresh.proposals for m in request.active_memories)
        assert all('陆禾' not in m.content for request in fresh.replies for m in request.selected_memories)
        assert all(not request.recent_dialogue for request in fresh.replies)
        history = restarted.app.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
            restarted.qri.profile_id, restarted.timeline))
        assert history.projection.turns[0].user_text == '我叫陆禾。'
        assert history.projection.turns[0].assistant_text == first.projection.expression_text
        memories = restarted.app.application.query(ApplicationQuery(ApplicationQueryKind.LIVING_MEMORY,
            restarted.qri.profile_id, restarted.timeline)).projection.memories
        assert [(m.content, m.status) for m in memories] == [('我喜欢深蓝色。', 'active'), ('我叫陆禾。', 'forgotten')]
    finally:
        restarted.app.close()


@pytest.mark.parametrize('command', ['不要忘记我的名字。', '他说“请忘记我的名字”。',
    '请忘记我的名字。算了，不要忘记。', '如果我让你忘记我的名字会怎么样？'])
def test_quoted_negated_or_conflicting_withdrawal_does_not_change_memory(tmp_path, command):
    opened = open_app(tmp_path, RecordingProvider())
    try:
        submit(opened, '我叫陆禾。')
        result = submit(opened, command)
        assert result.projection.memory_withdrawal_status != 'accepted'
        memories = opened.app.application.query(ApplicationQuery(ApplicationQueryKind.LIVING_MEMORY,
            opened.qri.profile_id, opened.timeline)).projection.memories
        assert memories[0].status == 'active'
        assert '已停止' not in result.projection.expression_text
    finally:
        opened.app.close()


def test_ambiguous_name_requires_exact_record_and_repeat_is_not_false_success(tmp_path):
    opened = open_app(tmp_path, RecordingProvider())
    try:
        submit(opened, '我叫陆禾。')
        submit(opened, '我叫林间。')
        ambiguous = submit(opened, '请忘记我的名字。')
        assert ambiguous.projection.memory_withdrawal_status == 'rejected'
        chosen = submit(opened, '请忘记「我叫陆禾。」')
        assert chosen.projection.memory_withdrawal_status == 'accepted'
        repeated = submit(opened, '请忘记「我叫陆禾。」')
        assert repeated.projection.memory_withdrawal_status == 'rejected'
        memories = opened.app.application.query(ApplicationQuery(ApplicationQueryKind.LIVING_MEMORY,
            opened.qri.profile_id, opened.timeline)).projection.memories
        assert [(m.content, m.status) for m in memories] == [('我叫林间。', 'active'), ('我叫陆禾。', 'forgotten')]
    finally:
        opened.app.close()


def test_interrupted_withdrawal_withholds_target_until_retry_without_claiming_success(tmp_path):
    from dynamic_subject_agent.runtime import RuntimeFaultPoint
    original = open_app(tmp_path, RecordingProvider())
    submit(original, '我叫陆禾。')
    submit(original, '我喜欢深蓝色。')
    original.app.close()
    interrupted = open_app(tmp_path, RecordingProvider(), saved=original,
        _runtime_interrupt_at=RuntimeFaultPoint.AFTER_COGNITION)
    submit(interrupted, '请忘记我的名字。')
    interrupted.app.close()
    provider = RecordingProvider()
    fresh = open_app(tmp_path, provider, saved=original)
    try:
        response = submit(fresh, '你现在还能说哪些记忆？')
        assert '陆禾' not in response.projection.expression_text
        assert all('陆禾' not in m.content for r in provider.proposals for m in r.active_memories)
        assert '深蓝色' in response.projection.expression_text
        result = submit(fresh, '请忘记我的名字。')
        assert result.projection.memory_withdrawal_status == 'accepted'
    finally:
        fresh.app.close()


def test_unresolved_withdrawal_does_not_hide_independent_sealed_answer(tmp_path):
    from test_grounded_role_expression import turn, KnowledgeProvider, ENTRY
    result = turn(tmp_path, '请忘记我的名字。纸灯节的规矩是什么？', KnowledgeProvider('未核实的自由文本。'),
        knowledge=True, also_memory=ReportedForgetProvider())
    assert result.memory_withdrawal_status == 'rejected'
    assert ENTRY.content in result.expression_text
    assert '这次没有停用' in result.expression_text
