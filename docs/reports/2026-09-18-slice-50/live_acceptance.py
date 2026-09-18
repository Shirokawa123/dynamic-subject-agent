"""Approved synthetic task save; credentials are never printed or persisted."""
from pathlib import Path
from uuid import uuid4
import json,sys
sys.path.insert(0,str(Path.cwd()))
import dynamic_subject_agent.local_product as product_module
from dynamic_subject_agent.deepseek import DeepSeekUrlLibTransport
from dynamic_subject_agent.credentials import WindowsCredentialStore,DEEPSEEK_CREDENTIAL_SLOT,DeepSeekCredentialVerifier
from app.desktop.server import DesktopState
root=Path('C:/Users/30252/AppData/Local/Temp/dsa-s50-isolated-20260918')
report=Path('docs/reports/2026-09-18-slice-50');report.mkdir(parents=True,exist_ok=True)
trace=report/'live.jsonl';assert not trace.exists()
def record(value):
    with trace.open('a',encoding='utf-8') as f:f.write(json.dumps(value,ensure_ascii=False)+'\n')
calls=[]
class Observed(DeepSeekUrlLibTransport):
    def post_json(self,**kwargs):
        data=json.loads(json.loads(kwargs['body'])['messages'][1]['content'])
        assert set(data)=={'current_user_message','active_tasks','task_catalog','policy'}
        assert 'LOCAL_ONLY' not in json.dumps(data)
        calls.append(data);record({'stage':'outbound','projection':data})
        result=super().post_json(**kwargs)
        record({'stage':'transport','status':result.status_code});return result
product_module.DeepSeekUrlLibTransport=Observed
config=product_module.LocalProductConfig(product_parent=root,state_path=root/'state.json',relationship_mode='dynamic')
def open_state():
    state=DesktopState(credential_store=WindowsCredentialStore(),credential_slot=DEEPSEEK_CREDENTIAL_SLOT,
        verifier=DeepSeekCredentialVerifier(),product_factory=lambda key:product_module.open_deepseek_local_product(config,api_key=key))
    assert state.setup_snapshot()['product_ready']
    return state
state=open_state()
def view():
    value=state.subject_tasks();assert value['ok'] and value['effects_enabled'];return value
def task(**data):
    result=state.submit_subject_task(dict(data,expected_profile_id=view()['profile_id'],idempotency_key=uuid4().hex))
    record({'stage':'task','result':result});assert result['ok'];return view()['tasks'][0]
def artifact(**data):
    result=state.text_artifact(dict(data,expected_profile_id=view()['profile_id']))
    record({'stage':'artifact','action':data['action'],'result':result});assert result['ok'];return result
try:
    assert view()['tasks']==[]
    r=task(action='request',kind='save_text',message='请保存这份陶艺桌说明文字。',content='LOCAL_ONLY：陶艺桌欢迎你。')
    assert r['status']=='accepted'
    first=artifact(action='preview',task_id=r['task_id'],revision=r['revision'])['preview']
    assert not Path(first['directory']).exists()
    r=task(action='revise',kind='save_text',message='请保存新版陶艺桌说明。',content='LOCAL_ONLY：陶艺桌欢迎你。\n来捏一颗小星星。',task_id=r['task_id'],expected_revision=r['revision'])
    artifact(action='approve',task_id=first['task_id'],revision=first['revision'],basis=first['basis'],idempotency_key=uuid4().hex)
    assert not Path(first['directory']).exists()
    p=artifact(action='preview',task_id=r['task_id'],revision=r['revision'])['preview']
    key=uuid4().hex
    artifact(action='approve',task_id=p['task_id'],revision=p['revision'],basis=p['basis'],idempotency_key=key)
    saved=view()['tasks'][0];record({'stage':'saved','task':saved})
    target=Path(saved['saved_path']);assert saved['status']=='completed' and target.read_bytes()==p['content'].encode()
    before=target.stat()
    artifact(action='approve',task_id=p['task_id'],revision=p['revision'],basis=p['basis'],idempotency_key=key)
    assert target.stat().st_ino==before.st_ino and target.stat().st_mtime_ns==before.st_mtime_ns
    state.close();state=open_state();assert view()['tasks'][0]==saved
    assert len(calls)==2
    record({'stage':'final','restart_equal':True,'file_exact':True,'duplicate_did_not_rewrite':True,'agency_calls':len(calls),'save_provider_calls':0})
    print('Production confirmed text save and restart passed',flush=True)
finally:state.close()
