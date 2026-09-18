"""Subject tasks use the sole Facade and canonical, restartable outcomes."""
from uuid import uuid4
import json
import pytest
from dynamic_subject_agent.model_gateway import ModelGateway, ModelResult, ProviderAdapter, ProviderCapabilities, StructuredOutputMode
from dynamic_subject_agent.subject_tasks import SubjectTaskCommand, SubjectTaskProposal
from dynamic_subject_agent.subject_task_cognition import SubjectTaskCognition
from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition
from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from test_recent_dialogue import DialogueProvider, open_app, submit




class TaskAdapter(ProviderAdapter):
    capabilities=ProviderCapabilities('test','task-test',True,(StructuredOutputMode.JSON_OBJECT,))
    def __init__(self,decision='accept',reason='supported_request'):
        self.requests=[];self.decision=decision;self.reason=reason
    def invoke(self,task):
        self.requests.append(task.payload)
        return ModelResult(task.kind,SubjectTaskProposal(self.decision,self.reason))


def opened(root,adapter=None,saved=None,**kwargs):
    provider=DialogueProvider();adapter=adapter or TaskAdapter()
    return open_app(root,provider,saved=saved,cognition=SubjectTaskCognition(ControlledLivingMemoryCognition(provider=provider),ModelGateway(adapter)),**kwargs),provider,adapter


def task_turn(app,command,key=None):
    pending=app.app.application.subject_task(command,idempotency_key=key or uuid4().hex)
    assert pending.operation_ref is not None,pending
    result=app.app.application.wait(pending.operation_ref,timeout_seconds=15)
    assert result.projection is not None,result
    return result


def tasks(app):
    result=app.app.application.query(ApplicationQuery(ApplicationQueryKind.SUBJECT_TASKS,app.qri.profile_id,app.timeline))
    assert result.status.value=='available',result
    return result.projection.records


def test_accept_cancel_restart_and_chat_projection_isolation(tmp_path):
    app,chat,model=opened(tmp_path)
    try:
        result=task_turn(app,SubjectTaskCommand('request','draft_text','请写两句邀请短诗。'))
        assert '已接受' in result.projection.expression_text
        first=tasks(app)[0]
        assert first.status=='accepted'
        assert chat.proposals==[] and chat.replies==[]
        assert model.requests[0].payload()['active_tasks']==[]
        app.app.close()
        app,chat,model=opened(tmp_path,saved=app)
        assert tasks(app)==(first,)
        submit(app,'我们聊一会儿。')
        assert chat.replies[-1].recent_dialogue==()
        result=task_turn(app,SubjectTaskCommand('cancel',task_id=first.task_id,expected_revision=1))
        assert '已取消' in result.projection.expression_text
        assert tasks(app)[0].status=='cancelled'
        assert model.requests==[]
    finally:
        app.app.close()


def test_task_idempotency_and_stale_action_do_not_repeat_mutation(tmp_path):
    app,_,model=opened(tmp_path)
    try:
        cmd=SubjectTaskCommand('request','draft_text','请写一段问候。')
        key=uuid4().hex
        first=task_turn(app,cmd,key)
        task_turn(app,cmd,key)
        assert len(tasks(app))==1 and len(model.requests)==1
        record=tasks(app)[0]
        task_turn(app,SubjectTaskCommand('cancel',task_id=record.task_id,expected_revision=1))
        before=tasks(app)
        stale=task_turn(app,SubjectTaskCommand('cancel',task_id=record.task_id,expected_revision=1))
        assert '状态已变化' in stale.projection.expression_text and tasks(app)==before
    finally:
        app.app.close()


def test_capacity_and_clarification_preserve_local_content_without_egress(tmp_path):
    app,_,model=opened(tmp_path)
    try:
        task_turn(app,SubjectTaskCommand('request','save_text','请保存这份文字。'))
        record=tasks(app)[0]
        assert record.status=='needs_input'
        task_turn(app,SubjectTaskCommand('revise','save_text','请保存正文。',record.task_id,record.revision,'PRIVATE_LOCAL_CONTENT'))
        assert tasks(app)[0].status=='accepted'
        task_turn(app,SubjectTaskCommand('request','draft_text','请写一首短诗。'))
        assert tasks(app)[1].status=='deferred'
        payload=json.dumps(model.requests[-1].payload(),ensure_ascii=False)
        assert 'PRIVATE_LOCAL_CONTENT' not in payload and record.task_id not in payload
        assert set(model.requests[-1].payload())=={'current_user_message','active_tasks','task_catalog','policy'}
    finally:
        app.app.close()


def test_task_snapshot_cannot_be_forged_by_cognition(tmp_path):
    from dataclasses import replace
    from dynamic_subject_agent.subject_tasks import TASK_INTENT
    class WrongSnapshot(SubjectTaskCognition):
        def propose(self, **kwargs):
            result=super().propose(**kwargs)
            if kwargs['command'].declared_intent==TASK_INTENT:
                agency=result.impact_envelope.agency
                return replace(result,impact_envelope=replace(result.impact_envelope,
                    agency=replace(agency,current_state=replace(agency.current_state,tasks=()))))
            return result
    app,_,_=opened(tmp_path)
    task_turn(app,SubjectTaskCommand('request','draft_text','请写两句短诗。'))
    before=tasks(app)
    app.app.close()
    chat=DialogueProvider()
    app=open_app(tmp_path,chat,saved=app,cognition=WrongSnapshot(ControlledLivingMemoryCognition(provider=chat),ModelGateway(TaskAdapter())))
    try:
        result=task_turn(app,SubjectTaskCommand('request','draft_text','请写一封邀请函。'))
        assert result.status.value=='failed-closed'
        assert tasks(app)==before
    finally:
        app.app.close()


def test_revision_does_not_project_its_own_old_task_as_competing_capacity(tmp_path):
    class Capacity(TaskAdapter):
        def invoke(self,task):
            self.requests.append(task.payload)
            busy=any(t['status']=='accepted' for t in task.payload.active_tasks)
            return ModelResult(task.kind,SubjectTaskProposal('defer' if busy else 'accept','capacity' if busy else 'supported_request'))
    model=Capacity();app,_,_=opened(tmp_path,model)
    try:
        task_turn(app,SubjectTaskCommand('request','draft_text','请写两句短诗。'))
        record=tasks(app)[0]
        task_turn(app,SubjectTaskCommand('revise','draft_text','请写两句邀请短诗。',record.task_id,record.revision))
        assert tasks(app)[0].status=='accepted'
        assert model.requests[-1].active_tasks==()
    finally:
        app.app.close()


def test_http_conflict_does_not_wait_for_old_success(tmp_path):
    from types import SimpleNamespace
    from app.desktop.server import AppState
    app,_,_=opened(tmp_path)
    product=SimpleNamespace(application=app.app.application,profile_id=app.qri.profile_id,timeline_id=app.timeline)
    session=AppState(product)
    key=uuid4().hex
    payload={'action':'request','kind':'draft_text','message':'请写两句短诗。','expected_profile_id':app.qri.profile_id,'idempotency_key':key}
    try:
        initial=session.submit_subject_task(payload)
        assert initial['ok'],initial
        result=session.submit_subject_task(dict(payload,message='请写一封邀请函。'))
        assert not result['ok'] and result['status']=='conflict'
        assert len(tasks(app))==1
    finally:
        app.app.close()


@pytest.mark.parametrize('mode',['failure','clarify','unsupported'])
def test_unsuccessful_revision_preserves_an_accepted_task(tmp_path,mode):
    class Model(TaskAdapter):
        broken=False
        def invoke(self,task):
            if self.broken and mode=='failure':
                raise OSError('synthetic unavailable')
            if self.broken and mode=='clarify':
                return ModelResult(task.kind,SubjectTaskProposal('clarify','clarification_requested'))
            return super().invoke(task)
    model=Model();app,_,_=opened(tmp_path,model)
    try:
        task_turn(app,SubjectTaskCommand('request','draft_text','请写两句短诗。'))
        before=tasks(app);record=before[0];model.broken=True
        text='请发送邮件给小夏。' if mode=='unsupported' else '请把短诗写得更轻快。'
        task_turn(app,SubjectTaskCommand('revise','draft_text',text,record.task_id,record.revision))
        assert tasks(app)==before
    finally:
        app.app.close()


def test_legacy_identity_keeps_chat_permission_and_never_calls_task_model(tmp_path):
    legacy=open_app(tmp_path,DialogueProvider())
    submit(legacy,'这是原来的聊天。')
    legacy.app.close()
    app,chat,model=opened(tmp_path,saved=legacy)
    try:
        view=app.app.application.query(ApplicationQuery(ApplicationQueryKind.SUBJECT_TASKS,app.qri.profile_id,app.timeline))
        assert view.status.value=='available' and not view.projection.enabled
        result=app.app.application.subject_task(SubjectTaskCommand('request','draft_text','请写两句短诗。'),idempotency_key=uuid4().hex)
        assert result.status.value=='unavailable' and model.requests==[]
        assert submit(app,'再聊一句。').status.value=='terminal'
        assert tasks(app)==()
    finally:
        app.app.close()


def test_other_identity_task_reference_cannot_cancel_or_enter_projection(tmp_path):
    left,_,_=opened(tmp_path/'left');right,_,model=opened(tmp_path/'right')
    try:
        task_turn(left,SubjectTaskCommand('request','draft_text','只属于甲的任务。'))
        record=tasks(left)[0]
        task_turn(right,SubjectTaskCommand('cancel',task_id=record.task_id,expected_revision=1))
        assert tasks(right)==() and tasks(left)[0]==record and model.requests==[]
    finally:
        left.app.close();right.app.close()


def test_interrupted_publication_does_not_create_a_task(tmp_path):
    from dynamic_subject_agent.runtime import RuntimeFaultPoint
    app,_,_=opened(tmp_path,_runtime_interrupt_at=RuntimeFaultPoint.BEFORE_PUBLICATION)
    pending=app.app.application.subject_task(SubjectTaskCommand('request','draft_text','请写短诗。'),idempotency_key=uuid4().hex)
    app.app.application.wait(pending.operation_ref,timeout_seconds=15)
    app.app.close()
    restored,_,_=opened(tmp_path,saved=app)
    try:
        assert tasks(restored)==()
    finally:
        restored.app.close()


def test_projection_limits_and_excluded_data_are_checked_before_transport(tmp_path):
    from dynamic_subject_agent.subject_task_provider import DeepSeekSubjectTaskAdapter
    from dynamic_subject_agent.subject_tasks import SubjectTaskProjection
    app,_,model=opened(tmp_path)
    try:
        for index in range(5):
            task_turn(app,SubjectTaskCommand('request','save_text',str(index)+'说明'*200,content='LOCAL_ONLY_BODY'))
        before=len(model.requests)
        task_turn(app,SubjectTaskCommand('request','draft_text','第六项任务。'))
        assert len(model.requests)==before and tasks(app)[-1].status=='declined'
        projection=SubjectTaskProjection.build('当前消息',tasks(app))
        body=json.loads(DeepSeekSubjectTaskAdapter.outbound_bytes(projection))
        data=json.loads(body['messages'][1]['content'])
        assert len(data['active_tasks'])==5 and sum(len(r['summary']) for r in data['active_tasks'])==1000
        encoded=json.dumps(data,ensure_ascii=False)
        assert 'LOCAL_ONLY_BODY' not in encoded and all(r.task_id not in encoded for r in tasks(app))
        with pytest.raises(ValueError):
            DeepSeekSubjectTaskAdapter.outbound_bytes(SubjectTaskProjection('字'*1001,()))
        with pytest.raises(ValueError):
            DeepSeekSubjectTaskAdapter.outbound_bytes(SubjectTaskProjection('消息',({'kind':'draft_text','summary':'私有','status':'accepted','task_id':'not-allowed'},)))
    finally:
        app.app.close()


def test_http_identity_and_local_content_stay_bound_to_current_product(tmp_path):
    from types import SimpleNamespace
    from app.desktop.server import AppState
    app,_,model=opened(tmp_path)
    session=AppState(SimpleNamespace(application=app.app.application,profile_id=app.qri.profile_id,timeline_id=app.timeline))
    try:
        result=session.submit_subject_task({'action':'request','kind':'save_text','message':'保存文本。','content':'BODY',
            'expected_profile_id':str(uuid4()),'idempotency_key':uuid4().hex})
        assert not result['ok'] and result['status']=='conflict'
        assert tasks(app)==() and model.requests==[]
    finally:
        app.app.close()


def test_local_text_is_exact_and_serialization_limit_is_rejected_before_admission(tmp_path):
    app,_,model=opened(tmp_path)
    try:
        body='Cafe\u0301\r\n正文'
        task_turn(app,SubjectTaskCommand('request','save_text','保存文字。',content=body))
        assert tasks(app)[0].content==body
        with pytest.raises(ValueError,match='canonical command bound'):
            SubjectTaskCommand('request','save_text','保存文字。',content='\x01'*16000)
        assert len(tasks(app))==1 and len(model.requests)==1
    finally:
        app.app.close()


@pytest.mark.parametrize('content',[{'decision':'accept','reason':'supported_request'},
    {'decision':'accept','reason':'supported_request','extra':'forbidden'},
    {'decision':'accept','reason':'capacity'}])
def test_deepseek_task_adapter_accepts_only_exact_closed_proposal(tmp_path,content):
    from dynamic_subject_agent.subject_task_provider import DeepSeekSubjectTaskAdapter
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import DEEPSEEK_MODEL,DEEPSEEK_CREDENTIAL_BACKEND_ID,DEEPSEEK_CREDENTIAL_KEY_ID,DeepSeekHttpResponse
    from test_deepseek_cognition_provider import _CapturingTransport
    transport=_CapturingTransport(DeepSeekHttpResponse(200,json.dumps({'model':DEEPSEEK_MODEL,
        'choices':[{'message':{'role':'assistant','content':json.dumps(content)}}],
        'usage':{'prompt_tokens':10,'completion_tokens':10}}).encode()))
    adapter=DeepSeekSubjectTaskAdapter(transport=transport,credential_ref=CredentialRef.reference(
        backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,key_id=DEEPSEEK_CREDENTIAL_KEY_ID))
    app,_,_=opened(tmp_path,adapter)
    try:
        task_turn(app,SubjectTaskCommand('request','draft_text','请写两句短诗。'))
        assert tasks(app)[0].status==('accepted' if content=={'decision':'accept','reason':'supported_request'} else 'failed')
        assert len(transport.calls)==1
    finally:
        app.app.close()
