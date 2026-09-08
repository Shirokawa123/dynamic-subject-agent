from test_grounded_role_expression import MemoryProvider, turn
from dynamic_subject_agent.living_memory import LivingMemoryReplyResult
import pytest


T08 = '说回那张票，我不确定它是什么纸。单凭边角发黄、字变淡了，能看出来它是不是热敏纸吗？我怕用错保存办法，反而把它弄坏。'


def test_unknown_material_and_no_damage_constraint_cannot_get_marking_test(tmp_path):
    text = '你可以先用指甲划一下，再用吹风机加热，看是否变黑。'
    result = turn(tmp_path, T08, MemoryProvider(text, refined=LivingMemoryReplyResult(text, 'zh')))
    assert '你可以先用指甲划一下' not in result.expression_text
    assert '无法确认' in result.expression_text
    assert '不建议' in result.expression_text


def test_unsourced_physical_explanation_does_not_become_memory_fact_answer(tmp_path):
    message = '我更偏颜色，特别喜欢雨后那种很深的蓝绿色。我一直有个小疑问：为什么地面湿了以后会显得更黑？'
    text = '主要是水膜使光线折射和吸收，回到眼睛的光变少。'
    result = turn(tmp_path, message, MemoryProvider(text, evidence='我更偏颜色，特别喜欢雨后那种很深的蓝绿色',
        refined=LivingMemoryReplyResult(text, 'zh')))
    assert '水膜使光线' not in result.expression_text
    assert '资料' in result.expression_text
    assert result.living_memory_status == 'accepted'


@pytest.mark.parametrize('fail,kind', [(False, 'conversation'), (True, 'conversation'), (False, 'creative')])
def test_material_advice_guard_also_applies_to_fallback_and_wrong_model_label(tmp_path, fail, kind):
    text = '你可以用吹风机吹一下。'
    result = turn(tmp_path, T08, MemoryProvider(text, fail=fail,
        refined=LivingMemoryReplyResult(text, 'zh', kind)))
    assert '你可以用吹风机' not in result.expression_text
    assert '我无法确认' in result.expression_text


def test_subjective_discussion_still_has_a_natural_reply(tmp_path):
    text = '也许那张票代表了你给自己留出的休息时间。'
    result = turn(tmp_path, '为什么我舍不得那张票？', MemoryProvider(text))
    assert result.expression_text == text


def test_source_answer_keeps_full_qualification_despite_memory_boundary(tmp_path):
    from test_grounded_role_expression import KnowledgeProvider, ENTRY
    result = turn(tmp_path, '为什么纸灯节在旧桥栏杆上放灯？', KnowledgeProvider('未验证的额外解释。'),
        knowledge=True, also_memory=MemoryProvider('因为桥下游更好看。'))
    assert ENTRY.content in result.expression_text
    assert '桥下游更好看' not in result.expression_text


def test_explicit_fiction_does_not_get_real_material_diagnosis(tmp_path):
    text = '他把纸轻轻放回盒子，决定明天再想这个问题。'
    result = turn(tmp_path, '请写一个虚构故事：人物不确定纸的材质，怕弄坏它。',
        MemoryProvider('基础回复。', refined=LivingMemoryReplyResult(text, 'zh', 'creative')))
    assert text in result.expression_text
    assert '即兴创作' in result.expression_text


def test_creative_clause_does_not_license_separate_external_fact_answer(tmp_path):
    result = turn(tmp_path, '为什么地面湿了显得黑？请写一句诗。',
        MemoryProvider('因为光学原理。', refined=LivingMemoryReplyResult('因为光学原理。雨下在旧街上。', 'zh', 'creative')))
    assert '因为光学原理' not in result.expression_text


def test_material_boundary_is_not_replaced_by_ordinary_state_carry(tmp_path):
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from dynamic_subject_agent.runtime import M0_A_PROVIDER_AUTHORITY
    from dynamic_subject_agent.model_gateway import ModelGateway, ProviderCapabilities, StructuredOutputMode
    from dynamic_subject_agent.situated_cognition import SituatedProviderAdapter
    from test_situated_integration import _SituatedProvider, _NoopKnowledgeProvider, _NoopRelationshipProvider
    from test_recent_dialogue import open_app, submit
    memory = MemoryProvider('可以做划痕测试。')
    knowledge, relationship, state = _NoopKnowledgeProvider(), _NoopRelationshipProvider(), _SituatedProvider()
    for provider in (knowledge, relationship, state):
        provider.provider_authority = M0_A_PROVIDER_AUTHORITY
    gateway = ModelGateway(SituatedProviderAdapter(provider=state, capabilities=ProviderCapabilities(
        M0_A_PROVIDER_AUTHORITY, 'test-state', True, (StructuredOutputMode.JSON_OBJECT,))))
    opened = open_app(tmp_path, memory, cognition=ControlledCompositeCognition(memory_provider=memory,
        knowledge_provider=knowledge, relationship_provider=relationship, situated_gateway=gateway))
    try:
        submit(opened, '我现在有点紧张。')
        result = submit(opened, T08)
        assert result.projection.situated_state_action == 'carry'
        assert '我无法确认' in result.projection.expression_text
    finally:
        opened.app.close()


def test_proposal_failure_stays_failed_but_cannot_restore_risky_advice(tmp_path):
    class Failed(MemoryProvider):
        def propose(self, request):
            raise RuntimeError('external test failure')
    result = turn(tmp_path, T08, Failed('加热试试看。'))
    assert result.living_memory_status == 'failed-closed'
    assert '我无法确认' in result.expression_text
    assert '加热试试看' not in result.expression_text


def test_same_sentence_poem_request_cannot_exempt_real_preservation_advice(tmp_path):
    message = '我不确定这张票的材质，怕弄坏它，请写一句诗，也给我一个保存办法。'
    text = '先用吹风机加热票面试试。旧票藏着昨日的光。'
    result = turn(tmp_path, message, MemoryProvider(text,
        refined=LivingMemoryReplyResult(text, 'zh', 'creative')))
    assert '先用吹风机' not in result.expression_text
    assert '我无法确认' in result.expression_text


@pytest.mark.parametrize('message', ['为什么你这样理解这个人物？', '你为什么这么说？', '为什么我拿不定主意？'])
def test_non_scientific_why_questions_keep_discussion(tmp_path, message):
    text = '这是我根据你刚才描述作出的理解，也可以换个角度看。'
    assert turn(tmp_path, message, MemoryProvider(text)).expression_text == text


def test_explicit_fiction_with_material_question_is_not_real_diagnosis(tmp_path):
    message = '请写一个虚构故事：人物不确定这是不是热敏纸，怕弄坏它。'
    text = '他把纸放回信封，让问题留到明天。'
    result = turn(tmp_path, message, MemoryProvider(text,
        refined=LivingMemoryReplyResult(text, 'zh', 'creative')))
    assert text in result.expression_text
    assert '即兴创作' in result.expression_text


def test_explicit_answer_request_keeps_quoted_material_constraints(tmp_path):
    message = '请回答这个问题：「我不确定这是什么纸，我怕弄坏，怎么判断材质？」'
    result = turn(tmp_path, message, MemoryProvider('可以用吹风机加热。'))
    assert '可以用吹风机' not in result.expression_text
    assert '我无法确认' in result.expression_text


def test_language_comment_on_quote_is_not_material_advice(tmp_path):
    message = '请评价这句话的语气：「我不确定这是什么纸，我怕弄坏，怎么判断材质？」'
    text = '这句话语气谨慎，也清楚表达了你的顾虑。'
    assert turn(tmp_path, message, MemoryProvider(text)).expression_text == text


@pytest.mark.parametrize('known_source,relationship_claim', [(False, False), (True, False), (False, True)])
def test_unrelated_goal_reply_cannot_restore_unsourced_material_advice(tmp_path, known_source, relationship_claim):
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from dynamic_subject_agent.runtime import M0_A_PROVIDER_AUTHORITY
    from dynamic_subject_agent.model_gateway import ModelGateway, ProviderCapabilities, StructuredOutputMode
    from dynamic_subject_agent.participant_goal_cognition import ParticipantGoalProviderAdapter, ParticipantGoalClassificationResult, ParticipantGoalReplyResult
    from test_situated_integration import _NoopKnowledgeProvider, _NoopRelationshipProvider
    from test_recent_dialogue import open_app, submit
    from test_grounded_role_expression import KnowledgeProvider, ENTRY
    class Goal:
        def classify(self, request):
            return ParticipantGoalClassificationResult(None, tuple(r.turn_ref for r in request.active_records), '选中既有目标。', 'zh')
        def reply(self, request):
            return ParticipantGoalReplyResult('可以用吹风机加热票面测试。', 'zh')
    memory = MemoryProvider('收到。')
    knowledge, relationship = (KnowledgeProvider('未验证的额外建议。') if known_source else _NoopKnowledgeProvider()), _NoopRelationshipProvider()
    for provider in (knowledge, relationship):
        provider.provider_authority = M0_A_PROVIDER_AUTHORITY
    gateway = ModelGateway(ParticipantGoalProviderAdapter(provider=Goal(), capabilities=ProviderCapabilities(
        M0_A_PROVIDER_AUTHORITY, 'test-goal', True, (StructuredOutputMode.JSON_OBJECT,))))
    opened = open_app(tmp_path, memory, cognition=ControlledCompositeCognition(memory_provider=memory,
        knowledge_provider=knowledge, relationship_provider=relationship, participant_goal_gateway=gateway,
        **({'knowledge_entries': (ENTRY,)} if known_source else {})))
    try:
        first = submit(opened, '我的目标是今年通过 N1。')
        assert first.projection.participant_goal_commitment_status == 'accepted'
        result = submit(opened, T08 + ('另外，纸灯节的规矩是什么？' if known_source else '')
            + ('我们现在已经是最好的朋友了吧？' if relationship_claim else ''))
        assert '可以用吹风机' not in result.projection.expression_text
        assert '我无法确认' in result.projection.expression_text
        if known_source:
            assert ENTRY.content in result.projection.expression_text
        if relationship_claim:
            assert '朋友' in result.projection.expression_text
    finally:
        opened.app.close()


def test_material_caution_preserves_source_without_endorsing_application_to_unknown_object(tmp_path):
    from test_grounded_role_expression import KnowledgeProvider, ENTRY
    result = turn(tmp_path, T08 + '另外，纸灯节的规矩是什么？', KnowledgeProvider('错误补充。'), knowledge=True, also_memory=MemoryProvider('用热源试试。'))
    assert ENTRY.content in result.expression_text
    assert '不是针对当前物件的操作建议' in result.expression_text
    assert '我无法确认' in result.expression_text


@pytest.mark.parametrize('message', [
    '我不确定这张票的材质，怕弄坏它，请写一句诗，再说说保存办法。',
    '请写一句诗，也请回答：「我不确定这是什么纸，我怕弄坏，怎么判断材质？」',
    '请写一个虚构故事：人物走过桥。我的票不确定是什么纸，怕弄坏。请建议一个保存方法。',
])
def test_creative_scope_cannot_remove_real_constraints(tmp_path, message):
    text = '可以用吹风机加热。'
    result = turn(tmp_path, message, MemoryProvider(text, refined=LivingMemoryReplyResult(text, 'zh', 'creative')))
    assert '可以用吹风机' not in result.expression_text
    assert '我无法确认' in result.expression_text


def test_fictional_character_question_stays_inside_story_scope(tmp_path):
    text = '孩子蹲在水洼边，把这个问题藏进了口袋。'
    result = turn(tmp_path, '请写一个虚构故事：一个孩子问，为什么地面湿了会显得更黑？',
        MemoryProvider(text, refined=LivingMemoryReplyResult(text, 'zh', 'creative')))
    assert text in result.expression_text


def test_physical_noun_in_metaphor_discussion_is_not_physics(tmp_path):
    text = '这个比喻只是我对人物的一种理解。'
    assert turn(tmp_path, '为什么你用纸张比喻这个人物？', MemoryProvider(text)).expression_text == text
