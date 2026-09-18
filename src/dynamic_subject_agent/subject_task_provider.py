"""The one approved Agency projection over the existing DeepSeek transport."""
import json
from dynamic_subject_agent.model_gateway import ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelTaskKind, ModelResult
from dynamic_subject_agent.subject_tasks import SubjectTaskProjection, SubjectTaskProposal
from dynamic_subject_agent.deepseek import (DEEPSEEK_PROVIDER_AUTHORITY_ID, DEEPSEEK_MODEL,
    DeepSeekLivingMemoryProvider, _post_identity_reply_content)

SYSTEM = ('只提议主体任务的处理决定，不执行任务。目录限文字起草和本地文本保存；不发送消息、不定时、不运行命令。'
    '明确文字请求用accept/supported_request；需要澄清用clarify/clarification_requested；已有接受任务占用时用defer/capacity；'
    '明确外部操作用decline/unsupported_request。本地正文是否存在由Python检查，不因投影没有正文而猜测缺失。'
    '仅返回JSON对象，exact字段decision和reason；禁止其他字段或自由理由。')


class DeepSeekSubjectTaskAdapter(ProviderAdapter):
    def __init__(self, *, transport, credential_ref):
        # Reuse the established credential/transport validation, not its task.
        self._base = DeepSeekLivingMemoryProvider(transport=transport,credential_ref=credential_ref)
        self.capabilities = ProviderCapabilities(DEEPSEEK_PROVIDER_AUTHORITY_ID,DEEPSEEK_MODEL,False,(StructuredOutputMode.JSON_OBJECT,))

    @staticmethod
    def outbound_bytes(request: SubjectTaskProjection) -> bytes:
        if not isinstance(request,SubjectTaskProjection):
            raise TypeError('typed agency projection required')
        body=json.dumps({'model':DEEPSEEK_MODEL,'messages':[{'role':'system','content':SYSTEM},
            {'role':'user','content':json.dumps(request.payload(),ensure_ascii=False,sort_keys=True,separators=(',',':'))}],
            'thinking':{'type':'disabled'},'response_format':{'type':'json_object'},'max_tokens':256,
            'temperature':0.0,'stream':False},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
        if len(body)>16384:
            raise ValueError('agency request exceeds byte budget')
        return body

    def invoke(self, task):
        if task.kind is not ModelTaskKind.SUBJECT_TASK_PROPOSAL:
            raise ValueError('unsupported task')
        value=_post_identity_reply_content(self._base._transport,self._base._credential_ref,self.outbound_bytes(task.payload))
        if set(value) != {'decision','reason'}:
            raise ValueError('invalid agency result fields')
        return ModelResult(task.kind,SubjectTaskProposal(**value))
