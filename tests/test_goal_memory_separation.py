"""A participant goal update cannot replace an independent arrangement."""
from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from dynamic_subject_agent.living_memory import LivingMemoryAction, LivingMemoryProposal, LivingMemoryProviderResult, LivingMemoryReplyResult
from test_memory_write_receipts import open_composite
from test_compound_requests import NoopGoal
from test_recent_dialogue import DialogueProvider, submit
import pytest

PLAN = '我周六整理栖云手册，但如果校样没到就顺延。'
GOAL = '我的目标是今年完成四篇随笔。'
REVISION = '把今年完成四篇随笔的目标改成今年完成六篇随笔。'

class MixedMemory(DialogueProvider):
    def propose(self, request):
        self.proposals.append(request)
        action, evidence, previous, recalled = LivingMemoryAction.NONE, '', None, ()
        if request.current_user_message == PLAN + GOAL:
            action, evidence = LivingMemoryAction.CREATE, request.current_user_message
        elif request.current_user_message == REVISION:
            action, evidence, previous = LivingMemoryAction.REVISE, REVISION, request.active_memories[0].memory_id
        else:
            recalled = tuple(m.memory_id for m in request.active_memories if '栖云手册' in m.content)
        return LivingMemoryProviderResult(LivingMemoryProposal(action, evidence, previous, recalled, 'plan'), '处理当前信息。', '收到。', 'zh')
    def reply(self, request):
        self.replies.append(request)
        return LivingMemoryReplyResult('', 'zh', 'memory')

def memories(opened):
    return opened.app.application.query(ApplicationQuery(ApplicationQueryKind.LIVING_MEMORY,
        opened.qri.profile_id, opened.timeline)).projection.memories

def test_mixed_current_message_keeps_goal_operation_out_of_memory(tmp_path):
    opened = open_composite(tmp_path, MixedMemory(), goal=NoopGoal())
    try:
        result = submit(opened, PLAN + GOAL)
        assert result.projection.participant_goal_commitment_status == 'accepted'
        assert [m.content for m in memories(opened)] == [PLAN]
    finally:
        opened.app.close()

def test_goal_revision_keeps_independent_plan_available(tmp_path):
    opened = open_composite(tmp_path, MixedMemory(), goal=NoopGoal())
    try:
        submit(opened, PLAN + GOAL)
        before = memories(opened)
        revised = submit(opened, REVISION)
        assert revised.projection.participant_goal_commitment_status == 'accepted'
        assert memories(opened) == before
        answer = submit(opened, '栖云手册的安排是什么？')
        assert PLAN in answer.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('message,expected', [
    (GOAL + PLAN, PLAN),
    (PLAN + GOAL, PLAN),
    ('我的目标是今年完成四篇随笔；' + PLAN, PLAN),
    (PLAN + '我给自己定个目标：今年完成四篇随笔。', PLAN),
    (PLAN + '我承诺每天阅读。', PLAN),
    ('我的目标是今年完成四篇随笔。', None),
    ('我放弃这个目标。', None),
])
def test_only_contiguous_independent_evidence_is_saved(tmp_path, message, expected):
    class Whole(MixedMemory):
        def propose(self, request):
            self.proposals.append(request)
            return LivingMemoryProviderResult(LivingMemoryProposal(LivingMemoryAction.CREATE, message, memory_kind='plan'),
                '提议记忆。', '收到。', 'zh')
    provider = Whole()
    opened = open_composite(tmp_path, provider, goal=NoopGoal())
    try:
        result = submit(opened, message)
        actual = [m.content for m in memories(opened) if m.status == 'active']
        assert actual == ([] if expected is None else [expected])
        assert result.projection.living_memory_status == ('no-op' if expected is None else 'accepted')
        assert len(provider.proposals) == len(provider.replies) == 1
        assert provider.proposals[0].current_user_message == message
    finally:
        opened.app.close()


def test_disjoint_remaining_facts_are_not_joined_into_fabricated_evidence(tmp_path):
    message = PLAN + GOAL + '我做封面时喜欢留白。'
    class Whole(MixedMemory):
        def propose(self, request):
            return LivingMemoryProviderResult(LivingMemoryProposal(LivingMemoryAction.CREATE, message), '提议记忆。', '收到。', 'zh')
    opened = open_composite(tmp_path, Whole(), goal=NoopGoal())
    try:
        result = submit(opened, message)
        assert result.projection.living_memory_status == 'rejected'
        assert result.projection.participant_goal_commitment_status == 'accepted'
        assert memories(opened) == ()
        assert '已记录你的原话' not in result.projection.expression_text
    finally:
        opened.app.close()


def test_goal_qualification_is_not_saved_as_an_independent_fact(tmp_path):
    message = GOAL + '但只有校样齐全时才开始。'
    class Whole(MixedMemory):
        def propose(self, request):
            return LivingMemoryProviderResult(LivingMemoryProposal(LivingMemoryAction.CREATE, message), '提议记忆。', '收到。', 'zh')
    opened = open_composite(tmp_path, Whole(), goal=NoopGoal())
    try:
        result = submit(opened, message)
        assert result.projection.living_memory_status == 'rejected'
        assert memories(opened) == ()
    finally:
        opened.app.close()


@pytest.mark.parametrize('message', [
    '朋友说：“先休息。我的目标是今年完成四篇随笔。之后再聊。”',
    '朋友说：「先休息。我的目标是今年完成四篇随笔。之后再聊。」',
    '如果我的目标是今年完成四篇随笔，我会很开心。',
    '我的目标是今年完成四篇随笔，但如果校样没到就顺延。',
])
def test_quoted_conditional_or_comma_bound_evidence_is_not_cut(tmp_path, message):
    class Whole(MixedMemory):
        def propose(self, request):
            return LivingMemoryProviderResult(LivingMemoryProposal(LivingMemoryAction.CREATE, message), '提议记忆。', '收到。', 'zh')
    opened = open_composite(tmp_path, Whole())
    try:
        result = submit(opened, message)
        assert result.projection.living_memory_status == 'accepted'
        assert [m.content for m in memories(opened)] == [message]
    finally:
        opened.app.close()


def test_legacy_mixed_memory_is_not_rewritten_by_goal_revision(tmp_path, monkeypatch):
    from dynamic_subject_agent.domains import experience
    from dynamic_subject_agent.memory_evidence_scope import MemoryEvidenceScope, MemoryEvidenceStatus
    # Replay pre-Slice-34 acceptance via the same Facade, then restore the new adjudicator.
    opened = open_composite(tmp_path, MixedMemory(), goal=NoopGoal())
    try:
        with monkeypatch.context() as old:
            old.setattr(experience, 'scope_memory_evidence', lambda message, evidence, **kwargs: MemoryEvidenceScope(MemoryEvidenceStatus.ELIGIBLE, evidence))
            submit(opened, PLAN + GOAL)
        before = memories(opened)
        assert before[0].content == PLAN + GOAL
        result = submit(opened, REVISION)
        assert result.projection.participant_goal_commitment_status == 'accepted'
        assert memories(opened) == before
    finally:
        opened.app.close()


def test_independent_memory_revision_still_replaces_its_plan(tmp_path):
    new_plan = '栖云手册改到周日整理，但校样没到仍然顺延。'
    class Explicit(MixedMemory):
        def propose(self, request):
            if request.current_user_message == '更正记忆：' + new_plan:
                return LivingMemoryProviderResult(LivingMemoryProposal(LivingMemoryAction.REVISE, new_plan,
                    request.active_memories[0].memory_id, memory_kind='plan'), '修改安排。', '收到。', 'zh')
            return super().propose(request)
    opened = open_composite(tmp_path, Explicit(), goal=NoopGoal())
    try:
        submit(opened, PLAN + GOAL)
        submit(opened, REVISION)
        result = submit(opened, '更正记忆：' + new_plan)
        assert result.projection.living_memory_status == 'accepted'
        assert [m.content for m in memories(opened) if m.status == 'active'] == [new_plan]
    finally:
        opened.app.close()
