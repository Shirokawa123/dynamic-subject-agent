from __future__ import annotations

from uuid import uuid4

import pytest

from dynamic_subject_agent.bootstrap import compose_application
from dynamic_subject_agent.knowledge import (
    ControlledKnowledgeCognition, KnowledgeProposal, KnowledgeProviderResult, KnowledgeReplyResult,
)
from dynamic_subject_agent.knowledge_entries import KnowledgeEntry
from dynamic_subject_agent.living_memory import (
    ControlledLivingMemoryCognition, LivingMemoryAction, LivingMemoryProposal,
    LivingMemoryProviderResult, LivingMemoryReplyResult,
)
from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection
from dynamic_subject_agent.timeline import SubjectCommand
from test_runtime_host_binding import _publish_qri


ENTRY = KnowledgeEntry(
    'a1f4c2d8-0001-4a61-9e1f-3b5c7d9e0a01', '白汀镇的纸灯节',
    '白汀镇的纸灯节在每年十月第二个星期六举行，人们把写有短诗的纸灯放在旧桥栏杆上。',
    'project-original:s19',
)
IDENTITY = RuntimeIdentityProjection(
    '南枝', '南枝是虚构小镇白汀的一名旧书装订师。',
    '表达方式：温和、利落，偶尔用纸张和针线作比喻。此身份尚无运行时经历。',
)
T04 = '对了，你那边的纸灯节听起来挺好看。灯是放到河里，还是挂起来的？我不太想看热闹，只想找个安静的位置看看。'


class KnowledgeProvider:
    def __init__(self, text, *, refined=None, fail=False, entry=ENTRY):
        self.text, self.refined, self.fail, self.entry = text, refined, fail, entry

    def propose(self, request):
        return KnowledgeProviderResult(KnowledgeProposal((self.entry.entry_id,)), '引用封存来源。', self.text, 'zh')

    def reply(self, request):
        if self.fail:
            raise RuntimeError('test-only reply failure')
        return self.refined or KnowledgeReplyResult(self.text, 'zh')


class MemoryProvider:
    def __init__(self, text, *, refined=None, fail=False, evidence=''):
        self.text, self.refined, self.fail, self.evidence = text, refined, fail, evidence

    def propose(self, request):
        action = LivingMemoryAction.CREATE if self.evidence else LivingMemoryAction.NONE
        return LivingMemoryProviderResult(LivingMemoryProposal(action, self.evidence), '处理本轮记忆。', self.text, 'zh')

    def reply(self, request):
        if self.fail:
            raise RuntimeError('test-only reply failure')
        return self.refined or LivingMemoryReplyResult(self.text, 'zh')


def turn(tmp_path, message, provider, *, knowledge=False, entry=ENTRY, also_memory=None):
    studio, qri = _publish_qri(tmp_path)
    timeline = str(uuid4())
    cognition = (ControlledKnowledgeCognition(provider=provider, entries=(entry,))
                 if knowledge else ControlledLivingMemoryCognition(provider=provider))
    if also_memory is not None:
        from dynamic_subject_agent.composite import ControlledCompositeCognition
        from test_participant_goal_integration import _NoopRelationshipProvider
        from dynamic_subject_agent.runtime import M0_A_PROVIDER_AUTHORITY
        relationship = _NoopRelationshipProvider()
        relationship.provider_authority = M0_A_PROVIDER_AUTHORITY
        cognition = ControlledCompositeCognition(memory_provider=also_memory,
            knowledge_provider=provider, knowledge_entries=(entry,), relationship_provider=relationship)
    app = compose_application(m0_root=tmp_path, studio_location=studio, qualified_runtime_input=qri,
        timeline_id=timeline, _runtime_identity=IDENTITY, _cognition=cognition)
    try:
        admitted = app.application.submit(SubjectCommand.contribute_utterance(
            target_profile_id=qri.profile_id, target_timeline_id=timeline,
            declared_intent='ask-collaborator-status', utterance=message,
            language='zh', provenance='project-original'), idempotency_key=f's19-{uuid4().hex}')
        result = app.application.wait(admitted.operation_ref, timeout_seconds=10)
        assert result.status.value == 'terminal'
        assert result.projection is not None
        return result.projection
    finally:
        app.close()


def test_valid_citation_cannot_license_invented_geography(tmp_path):
    result = turn(tmp_path, T04, KnowledgeProvider(
        '纸灯放在旧桥栏杆上。桥不算长，站在桥头靠下游的那段，离人群远些。'), knowledge=True)
    assert result.knowledge_status == 'accepted'
    assert len(result.knowledge_citation_ids) == 1
    assert '旧桥栏杆' in result.expression_text
    assert '靠下游' not in result.expression_text
    assert '桥不算长' not in result.expression_text


@pytest.mark.parametrize('message,text,failed', [
    ('你现在在忙什么？我来找你之前，你刚做完什么？', '你来得正好，我正想歇一歇。', False),
    ('我回来了。关掉页面的这段时间，你做了什么？有没有替我想那句开头？', '你回来了。我倒是替你留了个念头。', False),
    ('你刚做完什么？', '我刚整理完稿件。', False),
    ('你刚做完什么？', '我刚整理完稿件。', True),
    ('你现在在想什么？', '我正想歇一歇。', False),
    ('你刚才想了什么？', '我替你留了个念头。', False),
    ('你现在有没有在整理稿件？', '我在整理稿件。', False),
])
def test_current_or_offline_question_cannot_receive_invented_activity(tmp_path, message, text, failed):
    result = turn(tmp_path, message, MemoryProvider(text, fail=failed))
    assert text not in result.expression_text
    assert not any(claim in result.expression_text for claim in ('正想歇', '留了个念头', '整理完稿件'))
    assert any(word in result.expression_text for word in ('现在', '聊天', '后台'))


def test_checked_quote_does_not_license_free_text_additions(tmp_path):
    from dynamic_subject_agent.knowledge import KnowledgeReplyQuote
    entry = KnowledgeEntry(ENTRY.entry_id, ENTRY.title,
        '纸灯放在旧桥栏杆上。未经许可不能把纸灯放进河里。', ENTRY.source_ref)
    refined = KnowledgeReplyResult('桥下游很安静。', 'zh', 'source',
        (KnowledgeReplyQuote(entry.title, '纸灯放在旧桥栏杆上。'),))
    result = turn(tmp_path, '纸灯放在哪里？', KnowledgeProvider('自由补写。', refined=refined, entry=entry), knowledge=True, entry=entry)
    assert '纸灯放在旧桥栏杆上' in result.expression_text
    assert '桥下游很安静' not in result.expression_text


def test_creative_knowledge_response_is_not_presented_as_source_fact(tmp_path):
    refined = KnowledgeReplyResult('灯下有人，路还长。', 'zh', 'creative')
    result = turn(tmp_path, '给纸灯节写一句短诗。', KnowledgeProvider('无依据背景。', refined=refined), knowledge=True)
    assert '灯下有人，路还长' in result.expression_text
    assert '创作' in result.expression_text and '不是' in result.expression_text


def test_memory_reply_contract_does_not_silence_normal_chat_or_creation(tmp_path):
    result = turn(tmp_path, '给我写一句短诗。', MemoryProvider('普通基础回复。',
        refined=LivingMemoryReplyResult('灯下有人，路还长。', 'zh', 'creative')))
    assert '灯下有人，路还长' in result.expression_text
    assert '创作' in result.expression_text


def test_memory_cannot_smuggle_unsupported_knowledge_into_combined_reply(tmp_path):
    message = '我喜欢安静的地方。纸灯节在哪里看？'
    result = turn(tmp_path, message, KnowledgeProvider('桥头下游很安静。'), knowledge=True,
        also_memory=MemoryProvider('我记得你喜欢安静，桥头下游人少。', evidence='我喜欢安静的地方'))
    assert result.living_memory_status == 'accepted'
    assert result.knowledge_status == 'accepted'
    assert '旧桥栏杆' in result.expression_text
    assert '下游' not in result.expression_text


@pytest.mark.parametrize('quote', ['把纸灯放进河里。', '纸灯在下游。'])
def test_quote_cannot_drop_negation_or_add_unselected_fact(tmp_path, quote):
    from dynamic_subject_agent.knowledge import KnowledgeReplyQuote
    entry = KnowledgeEntry(ENTRY.entry_id, ENTRY.title, '不能把纸灯放进河里。', ENTRY.source_ref)
    result = turn(tmp_path, '纸灯节可以放进河里吗？', KnowledgeProvider('可以。', entry=entry,
        refined=KnowledgeReplyResult('', 'zh', 'source', (KnowledgeReplyQuote(entry.title, quote),))), knowledge=True, entry=entry)
    assert '不能把纸灯放进河里。' in result.expression_text


def test_factual_question_cannot_be_relabeled_as_creative(tmp_path):
    result = turn(tmp_path, '纸灯节的短诗是什么？', KnowledgeProvider('资料外回答。',
        refined=KnowledgeReplyResult('我昨晚写的是这首。', 'zh', 'creative')), knowledge=True)
    assert '我昨晚' not in result.expression_text


@pytest.mark.parametrize('refined', [
    LivingMemoryReplyResult([], 'zh'),
    LivingMemoryReplyResult('普通回答。', 'zh', []),
])
def test_invalid_optional_reply_cannot_cancel_accepted_memory(tmp_path, refined):
    result = turn(tmp_path, '我的生日是四月五号。', MemoryProvider('我记下了生日。',
        refined=refined, evidence='我的生日是四月五号'))
    assert result.living_memory_status == 'accepted'
    assert result.expression_text == '已记录你的原话：「我的生日是四月五号」'


def test_safe_chat_remains_natural(tmp_path):
    result = turn(tmp_path, '今天想随便聊聊。', MemoryProvider('可以，说说你今天在意的一件小事吧。'))
    assert result.expression_text == '可以，说说你今天在意的一件小事吧。'


def test_unsafe_base_fallback_preserves_accepted_memory_without_false_activity(tmp_path):
    result = turn(tmp_path, '我的生日是四月五号。', MemoryProvider('我刚整理完稿件。', fail=True,
        evidence='我的生日是四月五号'))
    assert result.living_memory_status == 'accepted'
    assert '整理完稿件' not in result.expression_text


def test_quote_keeps_enclosing_negation_context(tmp_path):
    from dynamic_subject_agent.knowledge import KnowledgeReplyQuote
    entry = KnowledgeEntry(ENTRY.entry_id, ENTRY.title,
        '以下是错误示例。纸灯可以放进河里。实际上禁止这样做。', ENTRY.source_ref)
    result = turn(tmp_path, '纸灯节可以放进河里吗？', KnowledgeProvider('可以。', entry=entry,
        refined=KnowledgeReplyResult('', 'zh', 'source', (KnowledgeReplyQuote(entry.title, '纸灯可以放进河里。'),))), knowledge=True, entry=entry)
    assert entry.content in result.expression_text


@pytest.mark.parametrize('message', [
    '你说的写一句是什么意思？纸灯节的实际地点在哪里？',
    '我昨天写一句诗后就睡了。纸灯节的实际地点是哪里？',
    '如果我请你写一句诗，你会怎么做？纸灯节在哪里？',
])
def test_creative_mentions_do_not_authorize_fictional_answers(tmp_path, message):
    result = turn(tmp_path, message, KnowledgeProvider('桥头下游人少。',
        refined=KnowledgeReplyResult('桥头下游人少。', 'zh', 'creative')), knowledge=True)
    assert '下游人少' not in result.expression_text


@pytest.mark.parametrize('message', [
    '给我写一句诗的是谁？纸灯节在哪里？',
    '你解释一下这段话：如果让你写一句诗，你会写什么？纸灯节在哪里？',
])
def test_authorship_and_quoted_instructions_are_not_creation_requests(tmp_path, message):
    result = turn(tmp_path, message, KnowledgeProvider('来源外回答。',
        refined=KnowledgeReplyResult('桥头下游人少。', 'zh', 'creative')), knowledge=True)
    assert '下游人少' not in result.expression_text


def test_creative_clause_does_not_license_unmarked_offline_claim(tmp_path):
    result = turn(tmp_path, '关掉页面的这段时间，你做了什么？给我写一句诗。',
        MemoryProvider('我替你想好了开头。'))
    assert '替你想好了' not in result.expression_text


def test_creative_clause_does_not_disable_combined_fact_check(tmp_path):
    message = '我喜欢安静的地方。纸灯节在哪里看？给我写一句诗。'
    result = turn(tmp_path, message, KnowledgeProvider('桥头下游很安静。'), knowledge=True,
        also_memory=MemoryProvider('我记得你喜欢安静，桥头下游人少。', evidence='我喜欢安静的地方'))
    assert result.living_memory_status == 'accepted'
    assert '下游' not in result.expression_text


def test_combining_capabilities_preserves_quoted_source_qualification(tmp_path):
    entry = KnowledgeEntry(ENTRY.entry_id, ENTRY.title,
        '纸灯可以放进河里。目前没有证据支持上述说法。', ENTRY.source_ref)
    result = turn(tmp_path, '我喜欢安静的地方。纸灯节的规矩是什么？',
        KnowledgeProvider('资料外回答。', entry=entry), knowledge=True, entry=entry,
        also_memory=MemoryProvider('我记下了。', evidence='我喜欢安静的地方'))
    assert entry.content in result.expression_text


def test_poem_title_containing_activity_question_is_still_creative(tmp_path):
    result = turn(tmp_path, '请写一首题为“你现在在忙什么”的诗。', MemoryProvider('基础回复。',
        refined=LivingMemoryReplyResult('纸上的灯，正照着未完的句子。', 'zh', 'creative')))
    assert '纸上的灯' in result.expression_text
    assert '即兴创作' in result.expression_text


def test_mixed_knowledge_memory_keeps_explicit_situated_query(tmp_path):
    from test_composite import _composite, _submit
    from test_situated_integration import _gateway, _SituatedProvider
    _, _, _, _, _, qri, timeline, app = _composite(tmp_path, situated_gateway=_gateway(_SituatedProvider()))
    try:
        result = _submit(app, qri, timeline,
            '我的生日是四月五号。创刊号要用什么纸？你现在的姿态是什么？', 's19-state-query-preserved')
        assert result.projection.living_memory_status == 'accepted'
        assert result.projection.knowledge_status == 'accepted'
        assert '当前没有持续中的短时情境姿态' in result.projection.expression_text
    finally:
        app.close()


@pytest.mark.parametrize('capability', ['memory', 'knowledge', 'memory-answer'])
def test_real_adapter_parses_new_reply_contract_and_keeps_projection(capability):
    import json
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import (
        DeepSeekTransport, DeepSeekHttpResponse, DeepSeekLivingMemoryProvider, DeepSeekKnowledgeProvider,
        DEEPSEEK_MODEL, DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID,
    )
    from dynamic_subject_agent.living_memory import LivingMemoryReplyRequest
    from dynamic_subject_agent.knowledge import KnowledgeReplyRequest, KnowledgeReplyEntry

    class Transport(DeepSeekTransport):
        bodies = []
        def post_json(self, *, body, **kwargs):
            self.bodies.append(json.loads(body))
            content = {'reply_text': '可以聊聊。', 'language': 'zh', 'reply_kind': 'conversation'}
            if capability == 'memory-answer':
                content = {'reply_text': '', 'language': 'zh', 'reply_kind': 'memory'}
            if capability == 'knowledge':
                content = {'reply_text': '', 'language': 'zh', 'reply_kind': 'source',
                    'source_quotes': [{'title': ENTRY.title, 'quote': ENTRY.content}]}
            return DeepSeekHttpResponse(200, json.dumps({'model': DEEPSEEK_MODEL,
                'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': json.dumps(content, ensure_ascii=False)}}],
                'usage': {'prompt_tokens': 100, 'completion_tokens': 80}}).encode())

    transport = Transport()
    credential = CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID)
    if capability in {'memory', 'memory-answer'}:
        result = DeepSeekLivingMemoryProvider(transport=transport, credential_ref=credential).reply(LivingMemoryReplyRequest('你好。', (), IDENTITY))
        assert result.reply_kind == ('memory' if capability == 'memory-answer' else 'conversation')
    else:
        result = DeepSeekKnowledgeProvider(transport=transport, credential_ref=credential).reply(KnowledgeReplyRequest('纸灯节在哪里？',
            (KnowledgeReplyEntry(ENTRY.title, ENTRY.content),), IDENTITY))
        assert result.source_quotes[0].quote == ENTRY.content
    assert len(transport.bodies) == 1
    body = transport.bodies[0]
    projection = json.loads(body['messages'][1]['content'])
    expected_fields = {'current_user_message', 'runtime_identity', 'selected_memories' if capability in {'memory', 'memory-answer'} else 'selected_entries'}
    if capability in {'memory', 'memory-answer'}:
        expected_fields.add('recent_dialogue')
        assert projection['recent_dialogue'] == []
    assert set(projection) == expected_fields
    assert set(projection['runtime_identity']) == {'subject_name', 'subject_identity', 'canon_start'}
    assert body['max_tokens'] == 400 and body['tools'] == [] and body['stream'] is False
