"""Bounded metadata only; leave HTTPS responses and qualified requests unchanged."""
from hashlib import sha256
import json

from dynamic_subject_agent.deepseek import DeepSeekTransport


def _field(value, key):
    if key not in value:
        return dict(state='missing', chars=None, stripped_chars=None)
    item = value[key]
    state = 'null' if item is None else 'string' if type(item) is str else 'other'
    return dict(state=state, chars=len(item) if type(item) is str else None,
        stripped_chars=len(item.strip()) if type(item) is str else None)


def response_metadata(response):
    """No body, text, arbitrary error/field names, credentials, or reasoning value."""
    body = response.body
    row = dict(http_status=response.status_code, body_bytes=len(body), envelope_json=False,
        duplicate_semantic_keys=False, choices_count=None, final_json=False, exact_reply_schema=False)
    duplicates = []
    watched = {'choices', 'message', 'content', 'reasoning_content', 'reply_text', 'language', 'model', 'usage'}
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value and key in watched:
                duplicates.append(True)
            value[key] = item
        return value
    try:
        payload = json.loads(body.decode('utf-8'), object_pairs_hook=pairs)
        row['duplicate_semantic_keys'] = bool(duplicates)
        if type(payload) is not dict:
            return row
        row['envelope_json'] = True
        choices = payload.get('choices')
        row['choices_count'] = len(choices) if type(choices) is list else None
        usage = payload.get('usage')
        if type(usage) is dict:
            row['usage'] = {key: usage[key] for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')
                if type(usage.get(key)) is int and 0 <= usage[key] < 2**53}
            details = usage.get('completion_tokens_details')
            count = details.get('reasoning_tokens') if type(details) is dict else None
            row['reasoning_tokens'] = count if type(count) is int and 0 <= count < 2**53 else None
        if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
            return row
        choice = choices[0]
        finish = choice.get('finish_reason')
        row['finish_reason'] = finish if finish in ('stop', 'length', 'tool_calls', 'content_filter',
            'insufficient_system_resource', 'aborted') else 'other'
        row['delta_present'] = 'delta' in choice
        message = choice.get('message')
        if type(message) is not dict:
            return row
        row['assistant_role'] = message.get('role') == 'assistant'
        row['content'] = _field(message, 'content')
        row['reasoning'] = _field(message, 'reasoning_content')
        row['undocumented_final'] = _field(message, 'final')
        row['undocumented_refusal'] = _field(message, 'refusal')
        tools = message.get('tool_calls')
        row['tool_calls_count'] = len(tools) if type(tools) is list else None
        content = message.get('content')
        if type(content) is str and content.strip():
            try:
                value = json.loads(content)
                row['final_json'] = True
            except (ValueError, TypeError):
                return row
            if type(value) is dict and set(value) == {'reply_text', 'language'}:
                row['exact_reply_schema'] = type(value['reply_text']) is str and value['language'] == 'zh'
                if type(value['reply_text']) is str:
                    row['reply_chars'] = len(value['reply_text'])
                    row['reply_sha256'] = sha256(value['reply_text'].encode()).hexdigest()
        return row
    except (ValueError, UnicodeError, TypeError):
        return row


class BoundaryObservedTransport(DeepSeekTransport):
    def __init__(self, delegate):
        self.delegate, self.rows = delegate, []

    def post_json(self, **kwargs):
        response = self.delegate.post_json(**kwargs)
        self.rows.append(response_metadata(response))
        return response


def self_check():
    from dynamic_subject_agent.deepseek import DeepSeekHttpResponse, _diagnostic_json_reply_content
    from dynamic_subject_agent.original_whole_chat import validate_whole_reply
    cases = [('raw-empty', '', 'response-content-empty'),
        ('empty-reply-json', json.dumps(dict(reply_text='', language='zh')), 'expression-invalid'),
        ('valid-final', json.dumps(dict(reply_text='合成完整正文。', language='zh')), 'complete')]
    results = []
    for name, content, expected in cases:
        body = json.dumps(dict(model='deepseek-flash', choices=[dict(finish_reason='stop',
            message=dict(role='assistant', content=content, reasoning_content='PRIVATE_SYNTHETIC_REASONING'))],
            usage=dict(prompt_tokens=10, completion_tokens=20))).encode()
        response = DeepSeekHttpResponse(200, body)
        metadata = response_metadata(response)
        try:
            value = _diagnostic_json_reply_content(response, max_output_tokens=4096,
                discard_reasoning=True, require_complete=True)
            validate_whole_reply(value)
            status = 'complete'
        except Exception as error:
            status = getattr(error, 'diagnostic_code', 'expression-invalid')
        assert status == expected, (name, status)
        assert 'PRIVATE_SYNTHETIC_REASONING' not in json.dumps(metadata)
        results.append(dict(case=name, status=status, metadata=metadata))
    duplicate = b'{"choices":[{"message":{"content":"first","content":""}}]}'
    assert response_metadata(DeepSeekHttpResponse(200, duplicate))['duplicate_semantic_keys']
    print(json.dumps(dict(self_check='passed', cases=results), ensure_ascii=False))


if __name__ == '__main__':
    self_check()
