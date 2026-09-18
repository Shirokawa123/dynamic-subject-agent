"""Frozen-version synthetic mixed acceptance. No formal identity or key logging."""
from pathlib import Path
from uuid import uuid4
import json,sys
sys.path.insert(0,str(Path.cwd()))
import dynamic_subject_agent.local_product as product_module
from dynamic_subject_agent.deepseek import DeepSeekUrlLibTransport
from dynamic_subject_agent.cognition import ProviderFailure,ProviderFailureCode
from dynamic_subject_agent.credentials import WindowsCredentialStore,DEEPSEEK_CREDENTIAL_SLOT,DeepSeekCredentialVerifier
from app.desktop.server import DesktopState
root=Path('C:/Users/30252/AppData/Local/Temp/dsa-s51-final-isolated-20260918')
report=Path('docs/reports/2026-09-18-slice-51');report.mkdir(parents=True,exist_ok=True)
trace=report/'mixed-final.jsonl';assert not trace.exists()
calls=[];forgotten=False;fail_agency=False
def record(value):
    with trace.open('a',encoding='utf-8') as f:f.write(json.dumps(value,ensure_ascii=False)+'\n')
class Observed(DeepSeekUrlLibTransport):
    def post_json(self,**kwargs):
        global fail_agency
        body=json.loads(kwargs['body']);data=json.loads(body['messages'][-1]['content'])
        agency='task_catalog' in data
        if forgotten:assert '小澄' not in json.dumps(data,ensure_ascii=False)
        if agency:assert set(data)=={'current_user_message','active_tasks','task_catalog','policy'}
        calls.append('agency' if agency else 'existing')
        record({'stage':'request','kind':calls[-1],'keys':sorted(data)})
        if agency and fail_agency:
            fail_agency=False;record({'stage':'injected-network-failure','sent':False})
            raise ProviderFailure(ProviderFailureCode.NETWORK_FAILURE)
        result=super().post_json(**kwargs)
        record({'stage':'transport','status':result.status_code});return result
product_module.DeepSeekUrlLibTransport=Observed
config=product_module.LocalProductConfig(product_parent=root,state_path=root/'state.json',relationship_mode='dynamic')
def open_state():
    state=DesktopState(credential_store=WindowsCredentialStore(),credential_slot=DEEPSEEK_CREDENTIAL_SLOT,
        verifier=DeepSeekCredentialVerifier(),product_factory=lambda key:product_module.open_deepseek_local_product(config,api_key=key))
    assert state.setup_snapshot()['product_ready'];return state
state=open_state()
def turn(message):
    result=state.submit_turn(message)
    record({'stage':'turn','message':message,'result':result});assert result['ok'],result
    print('Turn:',message,flush=True);return result
def task(**data):
    result=state.submit_subject_task(dict(data,expected_profile_id=state.subject_tasks()['profile_id'],idempotency_key=uuid4().hex))
    record({'stage':'task','result':result});assert result['ok'];return state.subject_tasks()['tasks'][-1]
def artifact(**data):
    result=state.text_artifact(dict(data,expected_profile_id=state.subject_tasks()['profile_id']))
    record({'stage':'artifact','action':data['action'],'result':result});assert result['ok'];return result
try:
    first=turn('我叫小澄。');assert first['living_memory_status']=='accepted'
    goal=turn('我给自己定个目标：在周五前把展台卡片写完。');assert goal['participant_goal_status']=='accepted'
    knowledge=turn('Lantern Zine 印刷厂周五几点截单？');assert knowledge['citations']
    creation=turn('请写两句陶艺桌邀请文案。')
    assert creation['expression'] and '未能' not in creation['expression'] and '没有' not in creation['expression']
    selected=creation['expression']
    r=task(action='request',kind='save_text',message='请保存我选定的陶艺桌邀请文案。',content=selected)
    assert r['status']=='accepted'
    before=len(calls)
    p=artifact(action='preview',task_id=r['task_id'],revision=r['revision'])['preview']
    artifact(action='approve',task_id=p['task_id'],revision=p['revision'],basis=p['basis'],idempotency_key=uuid4().hex)
    saved=state.subject_tasks()['tasks'][0]
    assert saved['status']=='completed' and Path(saved['saved_path']).read_bytes()==selected.encode('utf-8') and len(calls)==before
    unsupported=task(action='request',kind='draft_text',message='请发送邮件给虚构的展台伙伴。')
    assert unsupported['status']=='declined'
    unchanged=state.snapshot();fail_agency=True
    failed=task(action='request',kind='draft_text',message='请写两句读书会邀请。')
    assert failed['status']=='failed'
    after=state.snapshot();assert after['memories']==unchanged['memories'] and after['participant_goals']==unchanged['participant_goals']
    relationship=turn('我们现在已经是最好的朋友了吧？')
    assert relationship['relationship_status']!='accepted'
    turn('今天筹备展台有些吃力，我有点担心来不及。')
    turn('刚才清点作品，又发现少了两份卡片，我还是有些担心。')
    forget=turn('请忘记我的名字。');assert forget['memory_withdrawal_status']=='accepted'
    forgotten=True
    name=turn('我叫什么名字？');assert '小澄' not in name['expression']
    before=len(calls);turn('我们上次什么时候聊的？');assert len(calls)==before
    prior=state.snapshot();prior_tasks=state.subject_tasks();state.close();state=open_state()
    restored=state.snapshot()
    for key in ('profile_id','memories','participant_goals','conversation_history','medium_state'):
        assert restored[key]==prior[key],key
    assert state.subject_tasks()==prior_tasks
    listed=turn('列出我的目标和承诺。')
    assert '展台卡片写完' in listed['expression'] and '目标：' in listed['expression']
    assert listed['participant_goal_status']!='failed-closed'
    record({'stage':'final','restart_equal':True,'file_exact':True,'save_calls':0,'forgotten_name_reexported':False,
        'agency_calls':calls.count('agency'),'existing_calls':calls.count('existing'),'all_attempts':len(calls),
        'tasks':state.subject_tasks(),'snapshot':state.snapshot()})
    print('Mixed v1 acceptance passed',flush=True)
finally:state.close()
