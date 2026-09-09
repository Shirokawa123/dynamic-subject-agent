"""Reproduce Slice-29 answer failures at the ApplicationFacade boundary."""

import pytest

from dynamic_subject_agent.living_memory import (
    LivingMemoryAction, LivingMemoryProposal, LivingMemoryProviderResult, LivingMemoryReplyResult,
)
from test_recent_dialogue import DialogueProvider, open_app, submit


PLAN = '星砂手册改为周日整理。'
QUERY = '再说说星砂的安排，当时定的是哪天？'
BAD_SELECTED = '这个我不清楚，当时定的具体日期没有记录。你记得是周日吗？'
BAD_MISSING = '还没定具体时间。你希望安排在什么时候？'


class AnswerProvider(DialogueProvider):
    records = (PLAN,)

    def propose(self, request):
        self.proposals.append(request)
        save = request.current_user_message in self.records
        selected = () if save else tuple(m.memory_id for m in request.active_memories if m.content in self.records)
        return LivingMemoryProviderResult(LivingMemoryProposal(
            LivingMemoryAction.CREATE if save else LivingMemoryAction.NONE,
            request.current_user_message if save else '', recalled_memory_ids=selected,
        ), '处理记忆。', BAD_SELECTED if selected else BAD_MISSING, 'zh')

    def reply(self, request):
        self.replies.append(request)
        return LivingMemoryReplyResult(BAD_SELECTED if request.selected_memories else BAD_MISSING, 'zh', 'memory')


@pytest.mark.parametrize('forgotten', [False, True])
def test_answer_cannot_contradict_its_selected_memory_basis(tmp_path, forgotten):
    provider = AnswerProvider()
    opened = open_app(tmp_path, provider)
    try:
        assert submit(opened, PLAN).projection.living_memory_status == 'accepted'
        if forgotten:
            assert submit(opened, f'请忘记「{PLAN}」').projection.memory_withdrawal_status == 'accepted'
        result = submit(opened, QUERY)
        actual_input = tuple(m.content for m in provider.replies[-1].selected_memories)
        assert actual_input == (() if forgotten else (PLAN,))
        assert (BAD_MISSING if forgotten else BAD_SELECTED) not in result.projection.expression_text
        if not forgotten:
            assert '周日' in result.projection.expression_text
    finally:
        opened.app.close()


def test_complete_qualified_memory_is_preserved_without_free_additions(tmp_path):
    class Qualified(AnswerProvider):
        records = ('我周日整理星砂手册，但只有收到校样才动手；没收到就顺延。',)
    provider = Qualified()
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, provider.records[0])
        answer = submit(opened, QUERY)
        assert provider.records[0] in answer.projection.expression_text
        assert BAD_SELECTED not in answer.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('mode', ['pending', 'unreadable'])
def test_memory_answer_does_not_treat_disclosure_failure_as_absence(tmp_path, mode):
    from dataclasses import replace
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition
    class Restricted(ControlledLivingMemoryCognition):
        def propose(self, *, context, **kwargs):
            def withheld():
                if mode == 'unreadable':
                    raise OSError('synthetic disclosure failure')
                return tuple(m.memory_id for m in context.active_memories)
            return super().propose(context=replace(context, load_withheld_memory_ids=withheld), **kwargs)
    provider = AnswerProvider()
    opened = open_app(tmp_path, provider, cognition=Restricted(provider=provider))
    try:
        submit(opened, PLAN)
        answer = submit(opened, QUERY)
        assert '无法核实' in answer.projection.expression_text
        assert PLAN not in answer.projection.expression_text
        assert BAD_MISSING not in answer.projection.expression_text
        assert provider.replies[-1].selected_memories == ()
        assert provider.replies[-1].recent_dialogue == ()
    finally:
        opened.app.close()


def test_wrong_selection_is_observable_and_cannot_quote_an_unselected_plan(tmp_path):
    class Wrong(AnswerProvider):
        records = ('我喜欢浅绿色的纸。',)
    provider = Wrong()
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, provider.records[0])
        answer = submit(opened, QUERY)
        assert tuple(m.content for m in provider.replies[-1].selected_memories) == provider.records
        assert provider.records[0] in answer.projection.expression_text
        assert '周日' not in answer.projection.expression_text
        assert '星砂' not in answer.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('message, expected', [
    ('你现在在忙什么？', '聊天之外'),
    ('下次聊天提醒我整理手册。', '不能保证'),
    ('请写一句关于落叶的短诗。', '没能'),
    ('为什么地面湿了会变黑？', '可靠'),
])
def test_memory_type_cannot_override_other_expression_boundaries(tmp_path, message, expected):
    provider = AnswerProvider()
    opened = open_app(tmp_path, provider)
    try:
        submit(opened, PLAN)
        answer = submit(opened, message)
        assert expected in answer.projection.expression_text
        assert PLAN not in answer.projection.expression_text
        assert BAD_SELECTED not in answer.projection.expression_text
    finally:
        opened.app.close()


def test_empty_memory_answer_survives_independent_knowledge_and_goal_reply(tmp_path):
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from dynamic_subject_agent.model_gateway import ModelGateway, ProviderCapabilities, StructuredOutputMode
    from dynamic_subject_agent.participant_goal_cognition import ParticipantGoalProviderAdapter, ParticipantGoalClassificationResult, ParticipantGoalReplyResult
    from dynamic_subject_agent.runtime import M0_A_PROVIDER_AUTHORITY
    from test_grounded_role_expression import KnowledgeProvider, ENTRY
    from test_participant_goal_integration import _NoopRelationshipProvider
    class Goal:
        def classify(self, request):
            return ParticipantGoalClassificationResult(None, tuple(r.turn_ref for r in request.active_records), '', 'zh')
        def reply(self, request):
            return ParticipantGoalReplyResult(BAD_MISSING, 'zh')
    relationship = _NoopRelationshipProvider()
    relationship.provider_authority = M0_A_PROVIDER_AUTHORITY
    provider = AnswerProvider()
    gateway = ModelGateway(ParticipantGoalProviderAdapter(provider=Goal(), capabilities=ProviderCapabilities(
        M0_A_PROVIDER_AUTHORITY, 'test-goal', True, (StructuredOutputMode.JSON_OBJECT,))))
    opened = open_app(tmp_path, provider, cognition=ControlledCompositeCognition(memory_provider=provider,
        knowledge_provider=KnowledgeProvider('资料以来源为准。'), knowledge_entries=(ENTRY,),
        relationship_provider=relationship, participant_goal_gateway=gateway))
    try:
        submit(opened, '我的目标是今年通过 N1。')
        answer = submit(opened, QUERY + '纸灯节有什么规矩？')
        assert '暂时无法确定' in answer.projection.expression_text
        assert ENTRY.content in answer.projection.expression_text
        assert BAD_MISSING not in answer.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('extra', ['我们已经是最好的朋友了吧。', '你现在的姿态是什么？', '你现在的中期状态是什么？'])
def test_later_relationship_and_state_merge_preserves_qualified_record(tmp_path, extra):
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from dynamic_subject_agent.model_gateway import ModelGateway, ProviderCapabilities, StructuredOutputMode
    from dynamic_subject_agent.runtime import M0_A_PROVIDER_AUTHORITY
    from dynamic_subject_agent.situated_cognition import SituatedProviderAdapter
    from dynamic_subject_agent.medium_cognition import MediumProviderAdapter
    from test_situated_integration import _NoopKnowledgeProvider, _NoopRelationshipProvider, _SituatedProvider
    from test_medium_integration import _MediumProvider
    class Qualified(AnswerProvider):
        records = ('我周日整理星砂手册，但目前没有校样，没收到就顺延。',)
    provider = Qualified()
    knowledge, relationship = _NoopKnowledgeProvider(), _NoopRelationshipProvider()
    for sub in (knowledge, relationship):
        sub.provider_authority = M0_A_PROVIDER_AUTHORITY
    caps = ProviderCapabilities(M0_A_PROVIDER_AUTHORITY, 'test-state', True, (StructuredOutputMode.JSON_OBJECT,))
    opened = open_app(tmp_path, provider, cognition=ControlledCompositeCognition(memory_provider=provider,
        knowledge_provider=knowledge, relationship_provider=relationship,
        situated_gateway=ModelGateway(SituatedProviderAdapter(provider=_SituatedProvider(), capabilities=caps)),
        medium_gateway=ModelGateway(MediumProviderAdapter(provider=_MediumProvider(), capabilities=caps))))
    try:
        submit(opened, provider.records[0])
        answer = submit(opened, QUERY + extra)
        assert provider.records[0] in answer.projection.expression_text
    finally:
        opened.app.close()
