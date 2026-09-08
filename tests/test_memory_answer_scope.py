from dynamic_subject_agent.living_memory import LivingMemoryAction, LivingMemoryProposal, LivingMemoryProviderResult, LivingMemoryReplyResult
from test_recent_dialogue import open_app, submit, DialogueProvider
import pytest

PLAN = '我明天整理青舟小册子。'
PREFERENCE = '我喜欢深蓝色。'
QUERY = '青舟小册子那条计划现在还在你的活跃记忆里吗？'
BAD = '我现在没有活跃记忆，所以那条计划不在其中。'


class ScopeProvider(DialogueProvider):
    def propose(self, request):
        self.proposals.append(request)
        save = request.current_user_message in {PLAN, PREFERENCE}
        selected = tuple(m.memory_id for m in request.active_memories if '颜色' in request.current_user_message and '深蓝' in m.content)
        return LivingMemoryProviderResult(LivingMemoryProposal(LivingMemoryAction.CREATE if save else LivingMemoryAction.NONE,
            request.current_user_message if save else '', recalled_memory_ids=selected), '本轮记忆处理。', '收到。', 'zh')

    def reply(self, request):
        self.replies.append(request)
        text = BAD if request.current_user_message == QUERY else '你喜欢深蓝色。' if request.selected_memories else '收到。'
        return LivingMemoryReplyResult(text, 'zh')


def test_missing_selected_memory_does_not_mean_inventory_is_empty(tmp_path):
    provider = ScopeProvider()
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, PLAN)
        submit(opened, PREFERENCE)
        forgotten = submit(opened, f'请忘记「{PLAN}」')
        assert forgotten.projection.memory_withdrawal_status == 'accepted'
        result = submit(opened, QUERY)
        assert BAD not in result.projection.expression_text
        assert '本轮' in result.projection.expression_text
        assert PLAN not in result.projection.expression_text
        assert '深蓝' in submit(opened, '我喜欢哪种颜色？').projection.expression_text
        inventory = submit(opened, '你现在还记得哪些内容？')
        assert PREFERENCE in inventory.projection.expression_text
        assert PLAN not in inventory.projection.expression_text
    finally:
        opened.app.close()


def test_empty_inventory_is_confirmed_locally_not_by_the_model(tmp_path):
    provider = ScopeProvider()
    opened = open_app(tmp_path, provider)
    try:
        result = submit(opened, '你现在还记得哪些内容？')
        assert '当前没有可用于召回的活跃记忆' in result.projection.expression_text
        assert provider.proposals == provider.replies == []
    finally:
        opened.app.close()


def test_memory_selection_failure_is_not_an_empty_selection(tmp_path):
    class Failed(ScopeProvider):
        def propose(self, request):
            raise RuntimeError('synthetic provider failure')
    opened = open_app(tmp_path, Failed())
    try:
        result = submit(opened, QUERY)
        assert result.projection.living_memory_status == 'failed-closed'
        assert '无法核实' in result.projection.expression_text
        assert '没有活跃记忆' not in result.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('mode', ['unreadable', 'incomplete', 'pending'])
def test_uncertain_scope_never_claims_empty_or_successful_withdrawal(tmp_path, mode):
    from dataclasses import replace
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition
    class Uncertain(ControlledLivingMemoryCognition):
        def propose(self, *, context, **kwargs):
            def unreadable():
                raise OSError('synthetic disclosure read failure')
            changes = {'load_withheld_memory_ids': unreadable} if mode == 'unreadable' else (
                {'memory_control_complete': False} if mode == 'incomplete' else {'load_withheld_memory_ids': lambda: ('pending-id',)})
            return super().propose(context=replace(context, **changes), **kwargs)
    provider = ScopeProvider()
    opened = open_app(tmp_path, provider, cognition=Uncertain(provider=provider))
    try:
        result = submit(opened, f'「{PLAN}」这条记录现在还活跃吗？')
        assert '无法核实' in result.projection.expression_text
        assert '这条记录已停用' not in result.projection.expression_text
        assert provider.proposals == provider.replies == []
    finally:
        opened.app.close()


def test_exact_forgotten_record_status_does_not_echo_original(tmp_path):
    provider = ScopeProvider()
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, PLAN)
        submit(opened, f'请忘记「{PLAN}」')
        result = submit(opened, f'「{PLAN}」这条记录现在还活跃吗？')
        assert '已停用' in result.projection.expression_text
        assert PLAN not in result.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('text', [BAD, '你从未告诉我相关内容。'])
def test_free_reply_does_not_infer_global_absence_from_empty_selection(tmp_path, text):
    from test_grounded_role_expression import MemoryProvider, turn
    result = turn(tmp_path, '还有什么之前的安排？', MemoryProvider(text, refined=LivingMemoryReplyResult(text, 'zh')))
    assert text not in result.expression_text
    assert '本轮' in result.expression_text


def test_creative_and_quoted_memory_absence_stays_literal(tmp_path):
    from test_grounded_role_expression import MemoryProvider, turn
    text = '机器人说：“我现在没有活跃记忆。”'
    result = turn(tmp_path, '请写一个虚构故事：机器人说自己没有记忆。',
        MemoryProvider('基础回复。', refined=LivingMemoryReplyResult(text, 'zh', 'creative')))
    assert text in result.expression_text


def test_scope_answer_is_not_replaced_by_background_knowledge(tmp_path):
    from test_grounded_role_expression import MemoryProvider, KnowledgeProvider, ENTRY, turn
    from dynamic_subject_agent.knowledge_entries import KnowledgeEntry
    entry = KnowledgeEntry(ENTRY.entry_id, '青舟小册子', '青舟小册子是虚构练习素材。', ENTRY.source_ref)
    result = turn(tmp_path, QUERY, KnowledgeProvider('来源外回答。', entry=entry), knowledge=True, entry=entry,
        also_memory=MemoryProvider(BAD, refined=LivingMemoryReplyResult(BAD, 'zh')))
    assert '本轮没有选到' in result.expression_text
    assert entry.content in result.expression_text
