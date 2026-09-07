from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from dynamic_subject_agent.composite import ControlledCompositeCognition
from dynamic_subject_agent.runtime import M0_A_PROVIDER_AUTHORITY
from dynamic_subject_agent.living_memory import LivingMemoryReplyResult
import pytest
from test_grounded_role_expression import MemoryProvider, turn
from test_recent_dialogue import open_app, submit
from test_situated_integration import _NoopKnowledgeProvider, _NoopRelationshipProvider


def test_current_story_can_be_discussed_without_memory_or_source(tmp_path):
    memory = MemoryProvider('这个道别场景，你想先聊人物，还是先聊他们为什么分开？')
    knowledge, relationship = _NoopKnowledgeProvider(), _NoopRelationshipProvider()
    for provider in (knowledge, relationship):
        provider.provider_authority = M0_A_PROVIDER_AUTHORITY
    cognition = ControlledCompositeCognition(memory_provider=memory,
        knowledge_provider=knowledge, relationship_provider=relationship)
    opened = open_app(tmp_path, memory, cognition=cognition)
    try:
        result = submit(opened, '接下来是另一段虚构小故事：两个人在鸢尾桥道别。')
        assert result.projection.expression_text == '这个道别场景，你想先聊人物，还是先聊他们为什么分开？'
        records = opened.app.application.query(ApplicationQuery(ApplicationQueryKind.LIVING_MEMORY,
            opened.qri.profile_id, opened.timeline))
        assert records.projection.memories == ()
    finally:
        opened.app.close()


def test_unrequested_model_creation_reports_expression_failure_not_missing_information(tmp_path):
    memory = MemoryProvider('（无记忆相关内容）', refined=LivingMemoryReplyResult(
        '鸢尾桥横在薄雾上，两个人停步。风把花瓣吹进衣领，谁都没先开口。', 'zh', 'creative'))
    knowledge, relationship = _NoopKnowledgeProvider(), _NoopRelationshipProvider()
    for provider in (knowledge, relationship):
        provider.provider_authority = M0_A_PROVIDER_AUTHORITY
    opened = open_app(tmp_path, memory, cognition=ControlledCompositeCognition(
        memory_provider=memory, knowledge_provider=knowledge, relationship_provider=relationship))
    try:
        result = submit(opened, '接下来是另一段虚构小故事：两个人在鸢尾桥道别。')
        assert result.projection.expression_text == '这次没能给出符合你请求的回复，我不会用擅自创作的内容代替。'
        assert result.projection.living_memory_status == 'no-op'
    finally:
        opened.app.close()


def test_rejected_creation_does_not_offer_writing_after_user_asked_not_to_create(tmp_path):
    result = turn(tmp_path, '这是朋友写的故事，请不要创作新内容，我只是想聊聊。',
        MemoryProvider('（无记忆相关内容）', refined=LivingMemoryReplyResult('我来编一个新的故事。', 'zh', 'creative')))
    assert '写' not in result.expression_text
    assert '没能给出符合你请求的回复' in result.expression_text


@pytest.mark.parametrize('message,base,evidence', [
    ('我的生日是四月五号。', '我记下了生日。', '我的生日是四月五号'),
    ('这是一个桥上道别的场景。', '我们可以先聊聊这次道别。', ''),
])
def test_rejected_creation_preserves_valid_base_and_independent_memory(tmp_path, message, base, evidence):
    result = turn(tmp_path, message, MemoryProvider(base, evidence=evidence,
        refined=LivingMemoryReplyResult('桥上的人挥手道别。', 'zh', 'creative')))
    assert result.expression_text == base
    assert result.living_memory_status == ('accepted' if evidence else 'no-op')


def test_expression_failure_cannot_override_cited_source_context(tmp_path):
    from test_grounded_role_expression import KnowledgeProvider, ENTRY
    result = turn(tmp_path, '纸灯节的规矩是什么？', KnowledgeProvider('资料外回答。'), knowledge=True,
        also_memory=MemoryProvider('（无记忆相关内容）',
            refined=LivingMemoryReplyResult('桥下游可以放灯。', 'zh', 'creative')))
    assert ENTRY.content in result.expression_text
    assert '桥下游' not in result.expression_text
    assert '哪一部分' not in result.expression_text


def test_expression_failure_survives_carry_but_not_explicit_state_query(tmp_path):
    from test_situated_integration import _SituatedProvider
    from dynamic_subject_agent.model_gateway import ModelGateway, ProviderCapabilities, StructuredOutputMode
    from dynamic_subject_agent.situated_cognition import SituatedProviderAdapter
    memory = MemoryProvider('（无记忆相关内容）',
        refined=LivingMemoryReplyResult('风吹过桥头。', 'zh', 'creative'))
    knowledge, relationship, state = _NoopKnowledgeProvider(), _NoopRelationshipProvider(), _SituatedProvider()
    for provider in (knowledge, relationship, state):
        provider.provider_authority = M0_A_PROVIDER_AUTHORITY
    gateway = ModelGateway(SituatedProviderAdapter(provider=state, capabilities=ProviderCapabilities(
        M0_A_PROVIDER_AUTHORITY, 'test-state', True, (StructuredOutputMode.JSON_OBJECT,))))
    opened = open_app(tmp_path, memory, cognition=ControlledCompositeCognition(memory_provider=memory,
        knowledge_provider=knowledge, relationship_provider=relationship, situated_gateway=gateway))
    try:
        first = submit(opened, '我现在有点紧张。')
        assert first.projection.situated_state_status == 'accepted'
        second = submit(opened, '换个话题，这里有一个桥上道别的故事。')
        assert second.projection.situated_state_action == 'carry'
        assert '没能给出符合你请求的回复' in second.projection.expression_text
        third = submit(opened, '你现在的姿态是什么？')
        assert '姿态' in third.projection.expression_text
    finally:
        opened.app.close()


@pytest.mark.parametrize('message', ['明天上海会不会下雨？不要编造。',
    '我想先聊人物，请不要再问我想聊哪一部分。'])
def test_rejected_expression_does_not_reclassify_clear_request_as_unclear(tmp_path, message):
    result = turn(tmp_path, message, MemoryProvider('（无记忆相关内容）',
        refined=LivingMemoryReplyResult('我来编一个晴天的故事。', 'zh', 'creative')))
    assert '哪一部分' not in result.expression_text
    assert '没能给出符合你请求的回复' in result.expression_text
