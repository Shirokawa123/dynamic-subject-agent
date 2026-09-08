"""Memory continuity through the product Interface, with a bounded provider double."""

from dynamic_subject_agent.living_memory import (
    LivingMemoryAction, LivingMemoryProposal, LivingMemoryProviderResult, LivingMemoryReplyResult,
)
from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
import pytest
from test_recent_dialogue import DialogueProvider, open_app, submit


PLAN = '我计划周六整理星砂手册。'
REVISED_PLAN = '星砂手册改为周日整理。'
DISTRACTORS = tuple(f'我给资料夹编号为 archive-{index:02d}。' for index in range(20))


class RetrievalProvider(DialogueProvider):
    """Select a known subject only if the application actually supplied it."""

    def propose(self, request):
        self.proposals.append(request)
        save = request.current_user_message in {PLAN, *DISTRACTORS}
        revise = request.current_user_message == REVISED_PLAN
        selected = () if save else tuple(
            item.memory_id for item in request.active_memories if '星砂' in item.content
        )
        return LivingMemoryProviderResult(
            LivingMemoryProposal(
                LivingMemoryAction.REVISE if revise else LivingMemoryAction.CREATE if save else LivingMemoryAction.NONE,
                request.current_user_message if save or revise else '',
                supersedes_memory_id=selected[0] if revise and selected else None,
                recalled_memory_ids=() if revise else selected,
            ), '处理本轮记忆。', '收到。', 'zh',
        )

    def reply(self, request):
        self.replies.append(request)
        text = ('你之前说的是：「' + request.selected_memories[0].content + '」'
                if request.selected_memories else '这轮没有找到对应记录。')
        return LivingMemoryReplyResult(text, 'zh')


@pytest.mark.parametrize('distractor_count', [19, 20])
def test_older_relevant_memory_survives_topic_changes_and_restart(tmp_path, distractor_count):
    provider = RetrievalProvider()
    opened = open_app(tmp_path, provider)
    try:
        for text in (PLAN, *DISTRACTORS[:distractor_count]):
            result = submit(opened, text)
            assert result.projection.living_memory_status == 'accepted'
    finally:
        opened.app.close()
    restarted = open_app(tmp_path, provider, saved=opened)
    try:
        inventory = restarted.app.application.query(ApplicationQuery(
            ApplicationQueryKind.LIVING_MEMORY, restarted.qri.profile_id, restarted.timeline,
        ))
        assert any(m.content == PLAN and m.status == 'active' for m in inventory.projection.memories)
        result = submit(restarted, '回到星砂这件事，我之前准备做什么？')
        assert any(m.content == PLAN for m in provider.proposals[-1].active_memories)
        assert PLAN in result.projection.expression_text
        assert len(provider.proposals[-1].active_memories) <= 20
        assert len(provider.replies[-1].selected_memories) <= 5
        assert all(not hasattr(request, 'recent_dialogue') for request in provider.proposals)
        # Held-out phrasing keeps the subject but changes the request wording.
        assert PLAN in submit(restarted, '星砂手册原来安排在哪天处理？').projection.expression_text
    finally:
        restarted.app.close()


@pytest.fixture
def populated(tmp_path):
    provider = RetrievalProvider()
    opened = open_app(tmp_path, provider)
    try:
        for text in (PLAN, *DISTRACTORS):
            assert submit(opened, text).projection.living_memory_status == 'accepted'
        yield opened, provider
    finally:
        opened.app.close()


def test_revision_after_overflow_replaces_old_fact_and_survives_restart(tmp_path, populated):
    opened, provider = populated
    assert submit(opened, REVISED_PLAN).projection.living_memory_status == 'accepted'
    opened.app.close()
    restarted = open_app(tmp_path, provider, saved=opened)
    try:
        answer = submit(restarted, '接着谈星砂手册，整理时间怎么定的？')
        assert REVISED_PLAN in answer.projection.expression_text
        assert PLAN not in answer.projection.expression_text
        assert all(m.content != PLAN for m in provider.proposals[-1].active_memories)
        assert all(m.content != PLAN for m in provider.replies[-1].selected_memories)
        assert provider.replies[-1].recent_dialogue == ()
        memories = restarted.app.application.query(ApplicationQuery(
            ApplicationQueryKind.LIVING_MEMORY, restarted.qri.profile_id, restarted.timeline,
        )).projection.memories
        assert {(m.content, m.status) for m in memories if '星砂' in m.content} == {
            (PLAN, 'superseded'), (REVISED_PLAN, 'active'),
        }
    finally:
        restarted.app.close()


def test_forgotten_match_cannot_return_through_ranking_or_history(populated):
    opened, provider = populated
    assert submit(opened, f'请忘记「{PLAN}」').projection.memory_withdrawal_status == 'accepted'
    answer = submit(opened, '星砂手册原来安排在哪天处理？')
    assert PLAN not in answer.projection.expression_text
    assert all('星砂' not in m.content for m in provider.proposals[-1].active_memories)
    assert provider.replies[-1].recent_dialogue == ()


def test_no_lexical_match_keeps_recent_window_and_does_not_guess(populated):
    opened, provider = populated
    submit(opened, '聊聊音乐吧。')
    assert tuple(m.content for m in provider.proposals[-1].active_memories) == tuple(reversed(DISTRACTORS))
    assert provider.replies[-1].selected_memories == ()


@pytest.mark.parametrize('mode', ['pending', 'unreadable'])
def test_disclosure_boundary_still_filters_ranked_old_memory(tmp_path, populated, mode):
    from dataclasses import replace
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition
    opened, provider = populated
    class Restricted(ControlledLivingMemoryCognition):
        def propose(self, *, context, **kwargs):
            def withheld():
                if mode == 'unreadable':
                    raise OSError('synthetic disclosure failure')
                return tuple(m.memory_id for m in context.living_memory_history if '星砂' in m.content)
            return super().propose(context=replace(context, load_withheld_memory_ids=withheld), **kwargs)
    opened.app.close()
    restarted = open_app(tmp_path, provider, saved=opened, cognition=Restricted(provider=provider))
    try:
        answer = submit(restarted, '星砂手册原来安排在哪天处理？')
        assert PLAN not in answer.projection.expression_text
        assert all('星砂' not in m.content for m in provider.proposals[-1].active_memories)
        assert provider.replies[-1].recent_dialogue == ()
        if mode == 'unreadable':
            assert provider.proposals[-1].active_memories == ()
    finally:
        restarted.app.close()


def test_ranking_failure_is_local_failed_closed_and_inventory_remains_readable(tmp_path, populated, monkeypatch):
    from types import SimpleNamespace
    import sqlite3
    import dynamic_subject_agent.memory_retrieval as retrieval
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from dynamic_subject_agent.runtime import M0_A_PROVIDER_AUTHORITY
    from test_situated_integration import _NoopRelationshipProvider
    from test_grounded_role_expression import KnowledgeProvider, ENTRY
    opened, provider = populated
    opened.app.close()
    relationship = _NoopRelationshipProvider()
    relationship.provider_authority = M0_A_PROVIDER_AUTHORITY
    restarted = open_app(tmp_path, provider, saved=opened, cognition=ControlledCompositeCognition(
        memory_provider=provider, knowledge_provider=KnowledgeProvider('资料以来源为准。'),
        knowledge_entries=(ENTRY,), relationship_provider=relationship,
    ))
    def unavailable(*args, **kwargs):
        raise sqlite3.OperationalError('synthetic FTS5 unavailable')
    monkeypatch.setattr(retrieval, 'sqlite3', SimpleNamespace(connect=unavailable, Error=sqlite3.Error))
    try:
        count = len(provider.proposals)
        answer = submit(restarted, '星砂手册原来安排在哪天处理？纸灯节有什么规矩？')
        assert answer.projection.living_memory_status == 'failed-closed'
        assert answer.projection.knowledge_status == 'accepted'
        assert ENTRY.content in answer.projection.expression_text
        assert len(provider.proposals) == count
        inventory = submit(restarted, '你现在还记得哪些内容？')
        assert PLAN in inventory.projection.expression_text
        assert len(provider.proposals) == count
        status = submit(restarted, f'「{PLAN}」记录现在活跃吗？')
        assert '处于活跃状态' in status.projection.expression_text
    finally:
        restarted.app.close()
