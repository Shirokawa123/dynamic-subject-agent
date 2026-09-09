"""Memory write confirmations must follow final Domain results."""

import pytest
from dynamic_subject_agent.living_memory import (
    LivingMemoryAction, LivingMemoryProposal, LivingMemoryProviderResult, LivingMemoryReplyResult,
)
from test_recent_dialogue import DialogueProvider, open_app, submit


PLAN = '我周日整理雾桥手册，但目前没有校样，没收到就顺延。'
NEW_PLAN = '雾桥手册改到周一整理，但没收到校样仍然顺延。'
BAD = '好，那周日先不安排，等校样到了再顺延整理。'


class WriteProvider(DialogueProvider):
    def __init__(self, mode='create'):
        super().__init__()
        self.mode = mode
    def propose(self, request):
        self.proposals.append(request)
        if self.mode == 'failure':
            raise OSError('synthetic proposal failure')
        action = LivingMemoryAction.NONE if self.mode == 'noop' else LivingMemoryAction.CREATE
        evidence = request.current_user_message if action is not LivingMemoryAction.NONE else ''
        previous = None
        if request.current_user_message == NEW_PLAN:
            action = LivingMemoryAction.REVISE
            previous = request.active_memories[0].memory_id
        if self.mode == 'rejected':
            evidence = '不在当前消息中的证据。'
        return LivingMemoryProviderResult(LivingMemoryProposal(action, evidence, previous),
            '处理记忆候选。', BAD, 'zh')
    def reply(self, request):
        self.replies.append(request)
        return LivingMemoryReplyResult(BAD, 'zh', 'conversation')


def test_write_confirmation_preserves_condition_and_confirmed_revision(tmp_path):
    opened = open_app(tmp_path, WriteProvider())
    try:
        created = submit(opened, PLAN)
        assert created.projection.living_memory_status == 'accepted'
        assert PLAN in created.projection.expression_text
        assert BAD not in created.projection.expression_text
        revised = submit(opened, NEW_PLAN)
        assert revised.projection.living_memory_status == 'accepted'
        assert NEW_PLAN in revised.projection.expression_text
        assert PLAN not in revised.projection.expression_text
        assert BAD not in revised.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('mode', ['rejected', 'failure', 'noop'])
def test_unconfirmed_write_does_not_use_a_success_acknowledgement(tmp_path, mode):
    provider = WriteProvider(mode)
    opened = open_app(tmp_path, provider)
    try:
        response = submit(opened, '请记住：' + PLAN)
        assert BAD not in response.projection.expression_text
        assert any(word in response.projection.expression_text for word in ('未', '没有', '没能'))
        assert '已记录' not in response.projection.expression_text
    finally:
        opened.app.close()


def open_composite(root, provider, *, goal=None, knowledge=None):
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from dynamic_subject_agent.model_gateway import ModelGateway, ProviderCapabilities, StructuredOutputMode
    from dynamic_subject_agent.participant_goal_cognition import ParticipantGoalProviderAdapter
    from dynamic_subject_agent.runtime import M0_A_PROVIDER_AUTHORITY
    from test_participant_goal_integration import _NoopKnowledgeProvider, _NoopRelationshipProvider
    from test_grounded_role_expression import ENTRY
    related = _NoopRelationshipProvider()
    related.provider_authority = M0_A_PROVIDER_AUTHORITY
    known = knowledge or _NoopKnowledgeProvider()
    known.provider_authority = M0_A_PROVIDER_AUTHORITY
    gateway = None if goal is None else ModelGateway(ParticipantGoalProviderAdapter(provider=goal,
        capabilities=ProviderCapabilities(M0_A_PROVIDER_AUTHORITY, 'receipt-test', True, (StructuredOutputMode.JSON_OBJECT,))))
    return open_app(root, provider, cognition=ControlledCompositeCognition(memory_provider=provider,
        knowledge_provider=known, knowledge_entries=(ENTRY,) if knowledge else (),
        relationship_provider=related, participant_goal_gateway=gateway))


@pytest.mark.parametrize('mode', ['create', 'rejected', 'failure', 'noop'])
def test_composite_uses_final_memory_result(tmp_path, mode):
    opened = open_composite(tmp_path, WriteProvider(mode))
    try:
        answer = submit(opened, '请记住：' + PLAN)
        assert BAD not in answer.projection.expression_text
        if mode == 'create':
            assert '已记录' in answer.projection.expression_text
            assert PLAN in answer.projection.expression_text
        else:
            assert '已记录' not in answer.projection.expression_text
            assert '记忆' in answer.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('bad_claim', [False, True])
def test_independent_question_is_separate_from_storage_confirmation(tmp_path, bad_claim):
    from dataclasses import replace
    reply = '可以先列出要核对的项目。' if not bad_claim else '我已经帮你保存这份计划，稍后再看看。'
    class Discussion(WriteProvider):
        def propose(self, request):
            return replace(super().propose(request), proposal=LivingMemoryProposal(LivingMemoryAction.CREATE, PLAN))
        def reply(self, request):
            return LivingMemoryReplyResult(reply, 'zh')
    opened = open_composite(tmp_path, Discussion())
    try:
        answer = submit(opened, PLAN + '你觉得先准备什么？')
        assert PLAN in answer.projection.expression_text
        if bad_claim:
            assert reply not in answer.projection.expression_text
            assert '另外的问题' in answer.projection.expression_text
        else:
            assert reply in answer.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('goal_failed', [False, True])
def test_memory_receipt_preserves_creation_and_independent_goal_result(tmp_path, goal_failed):
    from dataclasses import replace
    from dynamic_subject_agent.participant_goal_cognition import ParticipantGoalClassificationResult, ParticipantGoalReplyResult
    from dynamic_subject_agent.participant_goals import ParticipantGoalCommitmentCandidate
    poem = '月光落在纸上，风轻轻翻页。'
    class Creative(WriteProvider):
        def propose(self, request):
            return replace(super().propose(request), proposal=LivingMemoryProposal(LivingMemoryAction.CREATE, PLAN))
        def reply(self, request):
            return LivingMemoryReplyResult(poem, 'zh', 'creative')
    class Goal:
        def classify(self, request):
            if goal_failed:
                raise OSError('synthetic goal failure')
            return ParticipantGoalClassificationResult(ParticipantGoalCommitmentCandidate(
                'create', 'goal', '今年通过 N1', None, 'active', '我的目标是今年通过 N1'), (), '处理目标。', 'zh')
        def reply(self, request):
            return ParticipantGoalReplyResult('目标内容以本轮结果为准。', 'zh')
    opened = open_composite(tmp_path, Creative(), goal=Goal())
    try:
        answer = submit(opened, PLAN + '我的目标是今年通过 N1。请写一句关于月光的短诗。')
        assert PLAN in answer.projection.expression_text
        assert answer.projection.expression_text.count(poem) == 1
        assert answer.projection.expression_text.count('已记录你的原话') == 1
        assert ('没能完成目标' if goal_failed else '已记录你的目标') in answer.projection.expression_text
    finally:
        opened.app.close()


def test_receipt_and_independent_knowledge_both_remain(tmp_path):
    from dataclasses import replace
    from test_grounded_role_expression import KnowledgeProvider, ENTRY
    class Recorded(WriteProvider):
        def propose(self, request):
            return replace(super().propose(request), proposal=LivingMemoryProposal(LivingMemoryAction.CREATE, PLAN))
    opened = open_composite(tmp_path, Recorded(), knowledge=KnowledgeProvider('没有额外说明。'))
    try:
        answer = submit(opened, PLAN + '纸灯节有什么规矩？')
        assert PLAN in answer.projection.expression_text
        assert ENTRY.content in answer.projection.expression_text
        assert BAD not in answer.projection.expression_text
    finally:
        opened.app.close()


def test_no_write_chat_is_not_replaced_by_a_receipt(tmp_path):
    opened = open_composite(tmp_path, DialogueProvider())
    try:
        answer = submit(opened, '你好。')
        assert answer.projection.expression_text == '你可以继续说。'
    finally:
        opened.app.close()


def test_unpublished_receipt_is_not_visible_as_a_success(tmp_path):
    from dynamic_subject_agent.runtime import RuntimeFaultPoint
    from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
    opened = open_app(tmp_path, WriteProvider(), _runtime_interrupt_at=RuntimeFaultPoint.BEFORE_PUBLICATION)
    try:
        answer = submit(opened, PLAN)
        assert answer.projection is None or '已记录' not in (answer.projection.expression_text or '')
        for kind, field in ((ApplicationQueryKind.LIVING_MEMORY, 'memories'), (ApplicationQueryKind.CONVERSATION_HISTORY, 'turns')):
            result = opened.app.application.query(ApplicationQuery(kind, opened.qri.profile_id, opened.timeline))
            assert getattr(result.projection, field) == ()
    finally:
        opened.app.close()


def test_restart_keeps_old_wrong_expression_and_new_truthful_receipt(tmp_path):
    from dynamic_subject_agent.runtime import ExpressionCandidate
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition
    from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
    class OldExpression(ControlledLivingMemoryCognition):
        def express(self, *, command, **kwargs):
            return ExpressionCandidate(BAD, command.language)
    provider = WriteProvider()
    original = open_app(tmp_path, provider, cognition=OldExpression(provider=provider))
    submit(original, PLAN)
    original.app.close()
    restarted = open_app(tmp_path, provider, saved=original)
    try:
        changed = submit(restarted, NEW_PLAN)
        assert NEW_PLAN in changed.projection.expression_text
    finally:
        restarted.app.close()
    reopened = open_app(tmp_path, provider, saved=original)
    try:
        history = reopened.app.application.query(ApplicationQuery(
            ApplicationQueryKind.CONVERSATION_HISTORY, reopened.qri.profile_id, reopened.timeline)).projection.turns
        assert history[0].assistant_text == BAD
        assert history[1].assistant_text == changed.projection.expression_text
    finally:
        reopened.app.close()


def test_noop_cannot_claim_a_write_without_an_explicit_user_command(tmp_path):
    class Claimed(WriteProvider):
        def reply(self, request):
            return LivingMemoryReplyResult('已保存你的安排。', 'zh')
    opened = open_composite(tmp_path, Claimed('noop'))
    try:
        answer = submit(opened, '我们继续。')
        assert '已保存' not in answer.projection.expression_text
        assert '没有新增' in answer.projection.expression_text
    finally:
        opened.app.close()


def test_quoted_question_is_not_an_independent_request(tmp_path):
    quoted = '我抄了一句“你觉得先准备什么？”用于稿件。'
    opened = open_composite(tmp_path, WriteProvider())
    try:
        answer = submit(opened, '请记住：' + quoted)
        assert quoted in answer.projection.expression_text
        assert '关于你的问题' not in answer.projection.expression_text
        assert BAD not in answer.projection.expression_text
    finally:
        opened.app.close()


def test_independent_knowledge_creation_is_not_hidden_by_memory_receipt(tmp_path):
    from dataclasses import replace
    from test_grounded_role_expression import KnowledgeProvider
    from dynamic_subject_agent.knowledge import KnowledgeReplyResult
    poem = '纸灯点亮桥边，月光落入人间。'
    class Recorded(WriteProvider):
        def propose(self, request):
            return replace(super().propose(request), proposal=LivingMemoryProposal(LivingMemoryAction.CREATE, PLAN))
    knowledge = KnowledgeProvider('备用。', refined=KnowledgeReplyResult(poem, 'zh', 'creative'))
    opened = open_composite(tmp_path, Recorded(), knowledge=knowledge)
    try:
        answer = submit(opened, PLAN + '请给纸灯节写一句短诗。')
        assert PLAN in answer.projection.expression_text
        assert poem in answer.projection.expression_text
        assert '没有完成' not in answer.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('repeat', [False, True])
def test_receipt_is_not_part_of_a_followup_draft_edit(tmp_path, repeat):
    from dynamic_subject_agent.runtime_identity_reply import CREATIVE_REPLY_PREFIX
    poem = '月光落纸。风轻翻页。'
    revised = '月光落纸。山色入窗。'
    class Draft(WriteProvider):
        def propose(self, request):
            self.proposals.append(request)
            initial = PLAN in request.current_user_message
            return LivingMemoryProviderResult(LivingMemoryProposal(
                LivingMemoryAction.CREATE if initial else LivingMemoryAction.NONE,
                PLAN if initial else ''), '处理当前请求。', '收到。', 'zh')
        def reply(self, request):
            self.replies.append(request)
            return LivingMemoryReplyResult(poem if PLAN in request.current_user_message or repeat else revised, 'zh', 'creative')
    opened = open_composite(tmp_path, Draft())
    try:
        first = submit(opened, PLAN + '请写一句关于月光的短诗。')
        assert first.projection.expression_text.startswith(CREATIVE_REPLY_PREFIX)
        assert PLAN in first.projection.expression_text
        after = submit(opened, '再给我一个版本。' if repeat else '第二句我想改成带山的意象。')
        if repeat:
            assert '没有形成新的改写版本' in after.projection.expression_text
        else:
            assert revised in after.projection.expression_text
        assert '已记录' not in after.projection.expression_text
    finally:
        opened.app.close()


def test_discussion_about_memory_is_not_an_operation_confirmation(tmp_path):
    from dataclasses import replace
    response = '我们可以聊聊哪些经历对你更重要。'
    class Discuss(WriteProvider):
        def propose(self, request):
            return replace(super().propose(request), proposal=LivingMemoryProposal(LivingMemoryAction.CREATE, PLAN))
        def reply(self, request):
            return LivingMemoryReplyResult(response, 'zh')
    opened = open_composite(tmp_path, Discuss())
    try:
        answer = submit(opened, PLAN + '你觉得记忆和情感有什么关系？')
        assert PLAN in answer.projection.expression_text
        assert response in answer.projection.expression_text
    finally:
        opened.app.close()
