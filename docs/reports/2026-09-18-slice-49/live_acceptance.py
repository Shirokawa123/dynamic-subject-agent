"""Approved synthetic task negotiation; never log credentials or raw responses."""
import json
from pathlib import Path
from dataclasses import asdict
from uuid import uuid4
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import dynamic_subject_agent.local_product as product_module
from dynamic_subject_agent.deepseek import DeepSeekUrlLibTransport
from dynamic_subject_agent.credentials import WindowsCredentialStore, DEEPSEEK_CREDENTIAL_SLOT, DeepSeekCredentialVerifier
from app.desktop.server import DesktopState

root=Path('C:/Users/30252/AppData/Local/Temp/dsa-s49-isolated-20260918')
report=Path('docs/reports/2026-09-18-slice-49/raw')
report.mkdir(parents=True,exist_ok=True)
trace=report/'live.jsonl'
assert not trace.exists()
def record(value):
    with trace.open('a',encoding='utf-8') as f:f.write(json.dumps(value,ensure_ascii=False)+'\n')
class Observed(DeepSeekUrlLibTransport):
    def post_json(self,**kwargs):
        body=json.loads(kwargs['body']); projection=json.loads(body['messages'][1]['content'])
        assert set(projection)=={'current_user_message','active_tasks','task_catalog','policy'}
        assert 'LOCAL_ONLY_BODY' not in json.dumps(projection)
        record({'stage':'outbound','projection':projection})
        response=super().post_json(**kwargs)
        record({'stage':'transport','status':response.status_code})
        return response
product_module.DeepSeekUrlLibTransport=Observed
config=product_module.LocalProductConfig(product_parent=root,state_path=root/'state.json',relationship_mode='dynamic')
def open_state():
    state=DesktopState(credential_store=WindowsCredentialStore(),credential_slot=DEEPSEEK_CREDENTIAL_SLOT,
        verifier=DeepSeekCredentialVerifier(),product_factory=lambda key:product_module.open_deepseek_local_product(config,api_key=key))
    assert state.setup_snapshot()['product_ready']
    return state
state=open_state()
def view():
    result=state.subject_tasks();assert result['ok'] and result['enabled'],result
    record({'stage':'tasks','tasks':result['tasks']})
    return result
def turn(**kwargs):
    result=state.submit_subject_task(dict(kwargs,expected_profile_id=view()['profile_id'],idempotency_key=uuid4().hex))
    record({'stage':'receipt','result':result});assert result['ok'],result
    return view()['tasks']
try:
    assert view()['tasks']==[]
    records=turn(action='request',kind='draft_text',message='请写两句陶艺桌的邀请短诗。')
    assert records[0]['status']=='accepted'
    records=turn(action='request',kind='draft_text',message='请写两句展台卡片文案。')
    assert records[1]['status']=='deferred'
    first=records[0]
    records=turn(action='cancel',task_id=first['task_id'],expected_revision=first['revision'])
    second=records[1]
    records=turn(action='revise',kind='draft_text',message='请写两句展台卡片文案。',task_id=second['task_id'],expected_revision=second['revision'])
    assert records[1]['status']=='accepted'
    second=records[1]
    records=turn(action='revise',kind='draft_text',message='请把两句展台卡片文案写得轻快。',task_id=second['task_id'],expected_revision=second['revision'])
    assert records[1]['status']=='accepted'
    second=records[1]
    turn(action='cancel',task_id=second['task_id'],expected_revision=second['revision'])
    records=turn(action='request',kind='save_text',message='请保存这份陶艺桌说明文字。')
    assert records[2]['status']=='needs_input'
    third=records[2]
    records=turn(action='revise',kind='save_text',message='请保存正文。',content='LOCAL_ONLY_BODY：陶艺桌欢迎你。',task_id=third['task_id'],expected_revision=third['revision'])
    assert records[2]['status']=='accepted'
    before=view()['tasks'];state.close();state=open_state()
    assert view()['tasks']==before
    record({'stage':'final','restart_equal':True,'file_effects_executed':False})
    print('Live task lifecycle and restart passed',flush=True)
finally:state.close()
