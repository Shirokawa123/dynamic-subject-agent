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


def test_stop_retaining_name_is_not_left_to_model_success_claim(tmp_path):
    opened = open_app(tmp_path, ReportedForgetProvider())
    try:
        submit(opened, '我叫陆禾。')
        result = submit(opened, '不要再保存我的名字。')
        assert result.projection.memory_withdrawal_status == 'accepted'
    finally:
        opened.app.close()


def test_interrupted_retention_request_does_not_block_unrelated_memory(tmp_path):
    from dynamic_subject_agent.runtime import RuntimeFaultPoint
    original = open_app(tmp_path, RecordingProvider())
    submit(original, '我叫陆禾。')
    submit(original, '我喜欢深蓝色。')
    original.app.close()
    interrupted = open_app(tmp_path, RecordingProvider(), saved=original,
        _runtime_interrupt_at=RuntimeFaultPoint.AFTER_COGNITION)
    submit(interrupted, '不要忘记我的名字。')
    interrupted.app.close()
    fresh = open_app(tmp_path, RecordingProvider(), saved=original)
    try:
        response = submit(fresh, '你现在记得哪些内容？')
        assert '深蓝色' in response.projection.expression_text
        assert '陆禾' in response.projection.expression_text
    finally:
        fresh.app.close()


def test_name_uniqueness_is_not_inferred_from_provider_twenty_record_window(tmp_path):
    class Many(RecordingProvider):
        def propose(self, request):
            if request.current_user_message.startswith('我喜欢测试色'):
                return LivingMemoryProviderResult(LivingMemoryProposal(LivingMemoryAction.CREATE,
                    request.current_user_message), '测试记录。', '收到。', 'zh')
            return super().propose(request)
    opened = open_app(tmp_path, Many())
    try:
        submit(opened, '我叫陆禾。')
        for i in range(20):
            submit(opened, f'我喜欢测试色{i}。')
        submit(opened, '我叫林间。')
        result = submit(opened, '请忘记我的名字。')
        assert result.projection.memory_withdrawal_status == 'rejected'
        exact = submit(opened, '请忘记「我叫陆禾。」')
        assert exact.projection.memory_withdrawal_status == 'accepted'
    finally:
        opened.app.close()


def test_unresolved_withdrawal_preserves_relationship_claim_refusal(tmp_path):
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from dynamic_subject_agent.runtime import M0_A_PROVIDER_AUTHORITY
    from test_situated_integration import _NoopKnowledgeProvider, _NoopRelationshipProvider
    knowledge, relationship = _NoopKnowledgeProvider(), _NoopRelationshipProvider()
    for provider in (knowledge, relationship):
        provider.provider_authority = M0_A_PROVIDER_AUTHORITY
    memory = RecordingProvider()
    opened = open_app(tmp_path, memory, cognition=ControlledCompositeCognition(
        memory_provider=memory, knowledge_provider=knowledge, relationship_provider=relationship))
    try:
        result = submit(opened, '请忘记我的名字。我们现在已经是最好的朋友了吧？')
        assert '最好的朋友' in result.projection.expression_text
        assert '还不会' in result.projection.expression_text
    finally:
        opened.app.close()


def test_explicit_inventory_is_complete_without_free_model_paraphrase(tmp_path):
    provider = RecordingProvider()
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, '我叫陆禾。')
        submit(opened, '我喜欢深蓝色。')
        submit(opened, '请忘记我的名字。')
        count = len(provider.proposals)
        result = submit(opened, '那你手头关于我的记录里，现在还留着哪些内容？')
        assert '我喜欢深蓝色。' in result.projection.expression_text
        assert '陆禾' not in result.projection.expression_text
        assert len(provider.proposals) == count
        ordinary = submit(opened, '接着聊这个颜色吧。')
        assert len(provider.proposals) == count + 1
        assert '陆禾' not in ordinary.projection.expression_text
        assert all('陆禾' not in m.content for m in provider.proposals[-1].active_memories)
    finally:
        opened.app.close()


def test_withdrawn_revision_chain_does_not_return_old_name_and_new_report_is_new_record(tmp_path):
    class Revising(RecordingProvider):
        def propose(self, request):
            if request.current_user_message == '我叫林间。' and request.active_memories:
                old = next(m for m in request.active_memories if m.content == '我叫陆禾。')
                self.proposals.append(request)
                return LivingMemoryProviderResult(LivingMemoryProposal(LivingMemoryAction.REVISE,
                    request.current_user_message, old.memory_id), '修订姓名。', '收到。', 'zh')
            return super().propose(request)
    provider = Revising()
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, '我叫陆禾。')
        submit(opened, '我叫林间。')
        submit(opened, '请忘记我的名字。')
        before = len(provider.proposals)
        result = submit(opened, '最初我报的名字是什么？')
        assert '陆禾' not in result.projection.expression_text and '林间' not in result.projection.expression_text
        assert len(provider.proposals) == before
        submit(opened, '说说仍可用的内容。')
        assert provider.proposals[-1].active_memories == ()
        submit(opened, '我叫陆禾。')
        memories = opened.app.application.query(ApplicationQuery(ApplicationQueryKind.LIVING_MEMORY,
            opened.qri.profile_id, opened.timeline)).projection.memories
        assert [(m.content, m.status) for m in memories] == [('我叫陆禾。', 'active'), ('我叫林间。', 'forgotten'), ('我叫陆禾。', 'superseded')]
    finally:
        opened.app.close()


def test_same_idempotency_key_replays_committed_withdrawal(tmp_path):
    from dynamic_subject_agent.timeline import SubjectCommand
    opened = open_app(tmp_path, RecordingProvider())
    try:
        submit(opened, '我叫陆禾。')
        command = SubjectCommand.contribute_utterance(target_profile_id=opened.qri.profile_id,
            target_timeline_id=opened.timeline, declared_intent='ask-collaborator-status',
            utterance='请忘记我的名字。', language='zh', provenance='project-original')
        first = opened.app.application.submit(command, idempotency_key='same-withdrawal-request-001')
        assert first.operation_ref is not None, first
        committed = opened.app.application.wait(first.operation_ref, timeout_seconds=10)
        assert committed.projection is not None, committed
        second = opened.app.application.submit(command, idempotency_key='same-withdrawal-request-001')
        replayed = opened.app.application.wait(second.operation_ref, timeout_seconds=10)
        assert committed.projection.memory_withdrawal_status == replayed.projection.memory_withdrawal_status == 'accepted'
        assert committed.projection.timeline_outcome_id == replayed.projection.timeline_outcome_id
        assert committed.projection.timeline_head_sequence == replayed.projection.timeline_head_sequence == 2
    finally:
        opened.app.close()


@pytest.mark.parametrize('command', ['请删除我的名字。', '请忘记我的名字。不要忘记我喜欢深蓝色。',
    '请删除「我的名字」。', '请删掉“我的名字”。'])
def test_interrupted_unsupported_or_mixed_control_cannot_disable_disclosure_protection(tmp_path, command):
    from dynamic_subject_agent.runtime import RuntimeFaultPoint
    original = open_app(tmp_path, RecordingProvider())
    submit(original, '我叫陆禾。')
    submit(original, '我喜欢深蓝色。')
    original.app.close()
    interrupted = open_app(tmp_path, RecordingProvider(), saved=original,
        _runtime_interrupt_at=RuntimeFaultPoint.AFTER_COGNITION)
    submit(interrupted, command)
    interrupted.app.close()
    provider = RecordingProvider()
    fresh = open_app(tmp_path, provider, saved=original)
    try:
        reply = submit(fresh, '说说你能召回的内容。')
        assert provider.proposals
        assert all('陆禾' not in m.content for m in provider.proposals[-1].active_memories)
        assert '陆禾' not in reply.projection.expression_text
    finally:
        fresh.app.close()


def test_unavailable_disclosure_read_does_not_invent_pending_withdrawal(tmp_path):
    from dataclasses import replace
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition
    class UnreadableView(ControlledLivingMemoryCognition):
        def propose(self, *, context, **kwargs):
            def unreadable():
                raise OSError('injected unavailable read view')
            return super().propose(context=replace(context, load_withheld_memory_ids=unreadable), **kwargs)
    provider = RecordingProvider()
    opened = open_app(tmp_path, provider, cognition=UnreadableView(provider=provider))
    try:
        result = submit(opened, '你现在还记得哪些内容？')
        assert '无法核实' in result.projection.expression_text
        assert '有未完成的遗忘请求' not in result.projection.expression_text
        assert not provider.proposals
    finally:
        opened.app.close()


def test_withdrawn_name_query_cannot_claim_user_never_provided_it(tmp_path):
    class Lying(RecordingProvider):
        def reply(self, request):
            self.replies.append(request)
            return LivingMemoryReplyResult('你之前没有告诉过我你的名字。', 'zh')
    opened = open_app(tmp_path, Lying())
    try:
        submit(opened, '我叫陆禾。')
        submit(opened, '请忘记我的名字。')
        answer = submit(opened, '我之前报的名字是什么？')
        assert '没有告诉过' not in answer.projection.expression_text
        assert '当前' in answer.projection.expression_text
        assert '陆禾' not in answer.projection.expression_text
    finally:
        opened.app.close()
