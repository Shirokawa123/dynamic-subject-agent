"""Small response-budget facts only; never inspect or retain reasoning text."""
import json
from dynamic_subject_agent.deepseek import DeepSeekHttpResponse
from dynamic_subject_agent.first_life_reply_live_provider import _ObservedTransport


def output_metadata(response):
    result=dict(reasoning_tokens=None,final_chars=None,finish_reason=None)
    if type(response) is not DeepSeekHttpResponse or type(response.body) is not bytes or len(response.body)>65536:return result
    try:
        payload=json.loads(response.body.decode('utf-8'))
        choices=payload.get('choices')
        if type(choices) is list and len(choices)==1 and type(choices[0]) is dict:
            if choices[0].get('finish_reason') in ('stop','length','tool_calls','content_filter','insufficient_system_resource','aborted'):
                result['finish_reason']=choices[0]['finish_reason']
            message=choices[0].get('message')
            if type(message) is dict and type(message.get('content')) is str:result['final_chars']=len(message['content'])
        usage=payload.get('usage')
        if type(usage) is dict:
            details=usage.get('completion_tokens_details')
            value=details.get('reasoning_tokens') if type(details) is dict else None
            total=usage.get('completion_tokens')
            if type(value) is int and type(total) is int and 0<=value<=total<=2**53-1:result['reasoning_tokens']=value
    except (ValueError,UnicodeError,TypeError,AttributeError):pass
    return result


class BudgetObservedTransport(_ObservedTransport):
    def __init__(self,transport):
        super().__init__(transport)
        self.row.update(reasoning_tokens=None,final_chars=None)
    def post_json(self,**kwargs):
        response=super().post_json(**kwargs)
        self.row.update(output_metadata(response))
        return response
