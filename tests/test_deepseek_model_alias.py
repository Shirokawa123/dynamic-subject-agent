"""The documented Flash redirect does not broaden model/output acceptance."""
import json
import pytest
from dynamic_subject_agent.cognition import CredentialRef, ProviderFailure, ProviderFailureCode
from dynamic_subject_agent.deepseek import (
    DEEPSEEK_MODEL, DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID,
    DeepSeekHttpResponse, DeepSeekTransport, DeepSeekLivingMemoryProvider, DeepSeekRelationshipProvider,
)
from dynamic_subject_agent.living_memory import LivingMemoryProviderRequest
from dynamic_subject_agent.relationship import RelationshipReplyRequest
from test_recent_dialogue import IDENTITY


@pytest.mark.parametrize('route', ['memory-proposal', 'relationship-reply'])
@pytest.mark.parametrize('model', [DEEPSEEK_MODEL, 'deepseek-flash', 'deepseek-v4-pro', 'deepseek-flash-other', None, ['deepseek-flash']])
def test_only_exact_documented_response_names_are_accepted(route, model):
    calls = []
    class Transport(DeepSeekTransport):
        def post_json(self, *, body, **kwargs):
            calls.append(json.loads(body))
            content = {'reply_text': '收到。', 'language': 'zh'}
            if route == 'memory-proposal':
                content.update(action='none', evidence_quote='',
                    supersedes_memory_id=None, recalled_memory_ids=[], experience_summary='没有新增。')
            return DeepSeekHttpResponse(200, json.dumps({'model': model,
                'choices': [{'message': {'role': 'assistant', 'content': json.dumps(content)}}],
                'usage': {'prompt_tokens': 100, 'completion_tokens': 80}}).encode())
    credential = CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID)
    if route == 'memory-proposal':
        provider = DeepSeekLivingMemoryProvider(transport=Transport(), credential_ref=credential)
        invoke = lambda: provider.propose(LivingMemoryProviderRequest('你好。', ()))
    else:
        provider = DeepSeekRelationshipProvider(transport=Transport(), credential_ref=credential)
        invoke = lambda: provider.reply(RelationshipReplyRequest('你好。', '当前无新增关系。', IDENTITY))
    if isinstance(model, str) and model in {DEEPSEEK_MODEL, 'deepseek-flash'}:
        assert invoke().language == 'zh'
    else:
        with pytest.raises(ProviderFailure) as failure:
            invoke()
        assert failure.value.code is ProviderFailureCode.INVALID_OUTPUT
    assert len(calls) == 1
    assert calls[0]['model'] == DEEPSEEK_MODEL
