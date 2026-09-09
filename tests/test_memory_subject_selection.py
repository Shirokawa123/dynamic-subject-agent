"""Explicit subject selection through the product Interface."""

import pytest
from dynamic_subject_agent.living_memory import (
    LivingMemoryAction, LivingMemoryProposal, LivingMemoryProviderResult, LivingMemoryReplyResult,
)
from test_recent_dialogue import DialogueProvider, open_app, submit


class SimilarProvider(DialogueProvider):
    """Reproduce the observed tendency to select the newest similar record."""
    def __init__(self, records):
        super().__init__()
        self.records = records
    def propose(self, request):
        self.proposals.append(request)
        save = request.current_user_message in self.records
        selected = () if save else tuple(m.memory_id for m in request.active_memories[:1])
        return LivingMemoryProviderResult(LivingMemoryProposal(
            LivingMemoryAction.CREATE if save else LivingMemoryAction.NONE,
            request.current_user_message if save else '', recalled_memory_ids=selected,
        ), '处理记忆。', '收到。', 'zh')
    def reply(self, request):
        self.replies.append(request)
        return LivingMemoryReplyResult('', 'zh', 'memory')


@pytest.mark.parametrize('target,other', [('月港手册', '雾桥手册'), ('苍穹报告', '银湾报告')])
@pytest.mark.parametrize('forgotten', [False, True])
@pytest.mark.parametrize('question', ['{}现在定在什么时间整理？', '请问，{}的安排是什么？', '再说说{}的安排，当时定的是哪天？'])
def test_similar_record_cannot_replace_the_requested_subject(tmp_path, target, other, forgotten, question):
    first, second = f'我周六整理{target}。', f'我周日整理{other}。'
    provider = SimilarProvider((first, second))
    opened = open_app(tmp_path, provider)
    try:
        for text in (first, second):
            assert submit(opened, text).projection.living_memory_status == 'accepted'
        if forgotten:
            assert submit(opened, f'请忘记「{first}」').projection.memory_withdrawal_status == 'accepted'
        answer = submit(opened, question.format(target))
        assert second not in answer.projection.expression_text
        assert tuple(m.content for m in provider.proposals[-1].active_memories) == (() if forgotten else (first,))
        assert tuple(m.content for m in provider.replies[-1].selected_memories) == (() if forgotten else (first,))
        assert ('暂时无法确定' if forgotten else first) in answer.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('failure', ['foreign-id', 'create', 'proposal-failure'])
def test_invalid_proposal_cannot_write_or_choose_another_object(tmp_path, failure):
    from uuid import uuid4
    from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
    first, second = '我周六整理北岸报告。', '我周日整理北湾报告。'
    class Invalid(SimilarProvider):
        def propose(self, request):
            if request.current_user_message in self.records:
                return super().propose(request)
            self.proposals.append(request)
            if failure == 'proposal-failure':
                raise OSError('synthetic proposal failure')
            return LivingMemoryProviderResult(LivingMemoryProposal(
                LivingMemoryAction.CREATE if failure == 'create' else LivingMemoryAction.NONE,
                request.current_user_message if failure == 'create' else '',
                recalled_memory_ids=() if failure == 'create' else (str(uuid4()),),
            ), '错误提议。', second, 'zh')
    provider = Invalid((first, second))
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, first)
        submit(opened, second)
        before = len(provider.replies)
        answer = submit(opened, '北岸报告原来安排在哪天处理？')
        assert answer.projection.living_memory_status == 'failed-closed'
        assert '无法核实' in answer.projection.expression_text
        assert second not in answer.projection.expression_text
        assert len(provider.replies) == before
        memories = opened.app.application.query(ApplicationQuery(
            ApplicationQueryKind.LIVING_MEMORY, opened.qri.profile_id, opened.timeline)).projection.memories
        assert {m.content for m in memories} == {first, second}
    finally:
        opened.app.close()


@pytest.mark.parametrize('failed_reply', [False, True])
def test_optional_reply_cannot_bypass_local_object_binding(tmp_path, failed_reply):
    first, second = '我周六整理苔原笔记。', '我周日整理苔海笔记。'
    class FreeReply(SimilarProvider):
        def reply(self, request):
            self.replies.append(request)
            if failed_reply:
                raise OSError('synthetic optional reply failure')
            return LivingMemoryReplyResult(second, 'zh', 'conversation')
    provider = FreeReply((first, second))
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, first)
        submit(opened, second)
        answer = submit(opened, '苔原笔记的计划怎样？')
        assert first in answer.projection.expression_text
        assert second not in answer.projection.expression_text
    finally:
        opened.app.close()


def test_revised_subject_and_withdrawal_survive_restart(tmp_path):
    first, second = '我周六整理北岸报告。', '我周日整理北湾报告。'
    revised = '北岸报告改为周一整理。'
    class Revising(SimilarProvider):
        def propose(self, request):
            if request.current_user_message != revised:
                return super().propose(request)
            self.proposals.append(request)
            old = next(m for m in request.active_memories if m.content == first)
            return LivingMemoryProviderResult(LivingMemoryProposal(LivingMemoryAction.REVISE,
                revised, supersedes_memory_id=old.memory_id), '更正报告安排。', '收到。', 'zh')
    provider = Revising((first, second))
    original = open_app(tmp_path, provider)
    try:
        submit(original, first)
        submit(original, second)
        assert submit(original, revised).projection.living_memory_status == 'accepted'
    finally:
        original.app.close()
    reopened = open_app(tmp_path, provider, saved=original)
    try:
        answer = submit(reopened, '北岸报告原来安排在哪天处理？')
        assert revised in answer.projection.expression_text
        assert first not in answer.projection.expression_text
        assert submit(reopened, f'请忘记「{revised}」').projection.memory_withdrawal_status == 'accepted'
    finally:
        reopened.app.close()
    reopened = open_app(tmp_path, provider, saved=original)
    try:
        answer = submit(reopened, '北岸报告的安排是什么？')
        assert '暂时无法确定' in answer.projection.expression_text
        assert second not in answer.projection.expression_text
        assert provider.proposals[-1].active_memories == ()
    finally:
        reopened.app.close()


@pytest.mark.parametrize('question', ['你建议月港手册安排在什么时候整理？',
    '他说：“月港手册现在定在什么时间整理？”', '月港手册的安排是什么？雾桥手册的安排是什么？',
    '现在提醒我一下刚才的计划是什么。', '请问，刚才的计划是什么？', '目前的安排是什么？'])
def test_other_intents_are_not_reinterpreted_as_single_bound_queries(tmp_path, question):
    first, second = '我周六整理月港手册。', '我周日整理雾桥手册。'
    provider = SimilarProvider((first, second))
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, first)
        submit(opened, second)
        submit(opened, question)
        assert {m.content for m in provider.proposals[-1].active_memories} == {first, second}
    finally:
        opened.app.close()


def test_legacy_analyze_reply_cannot_substitute_another_subject(tmp_path):
    first, second = '我周六整理青岭笔记。', '我周日整理青川笔记。'
    class Legacy:
        def __init__(self):
            self.delegate = SimilarProvider((first, second))
        def analyze(self, request):
            from dataclasses import replace
            return replace(self.delegate.propose(request), reply_text=second)
    provider = Legacy()
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, first)
        submit(opened, second)
        answer = submit(opened, '青岭笔记的安排是什么？')
        assert first in answer.projection.expression_text
        assert second not in answer.projection.expression_text
    finally:
        opened.app.close()
