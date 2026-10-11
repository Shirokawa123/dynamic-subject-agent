from contextlib import contextmanager
import importlib,json,re,time
from threading import Thread
from urllib.request import Request,urlopen
from uuid import uuid4
import pytest
from test_shared_activity_chat_entry import entry_setup,chat,advance,select_source
from test_original_whole_chat import approved,personality_fixture,model_fixture
from test_natural_feedback_multispan import MultispanTransport,PLAN,MESSAGE

@pytest.fixture
def natural_entry_setup(entry_setup,monkeypatch):
    shared,_,root,options,_,_=entry_setup
    script=importlib.import_module('serve_natural_feedback_chat');desktop=importlib.import_module('natural_feedback_chat')
    monkeypatch.setattr(script,'APPROVED_BINDING',shared.APPROVED_BINDING)
    import dynamic_subject_agent.natural_feedback_live as live
    from dynamic_subject_agent.natural_feedback import feedback_contract
    monkeypatch.setattr(live,'APPROVED_FEEDBACK_MATERIAL',live.digest(shared.APPROVED_BINDING))
    monkeypatch.setattr(live,'APPROVED_FEEDBACK_LOCAL_CONTRACT',live.digest(feedback_contract(shared.APPROVED_BINDING)))
    transport=MultispanTransport()
    return script,desktop,root.with_name('natural-entry'),dict(options,transport=transport,audit_path=root.with_name('natural-audit')),transport

@contextmanager
def http_entry(entry,desktop):
    server=desktop.natural_feedback_server(entry.product,reopen=entry.reopen)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
    try:
        with urlopen(base+'/',timeout=4) as response:page=response.read().decode()
        token=re.search(r"TOKEN='([^']+)'",page).group(1)
        class Http:
            def get(self,path):
                with urlopen(base+path,timeout=5) as r:return json.load(r)
            def post(self,path,payload):
                with urlopen(Request(base+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-Chat-Token':token}),timeout=10) as r:return json.load(r)
        h=Http();h.page=page;yield h
    finally:server.shutdown();server.server_close();thread.join(timeout=5)

def test_empty_entry_hidden_http_scope_feedback_long_patch_topics_reopen_and_activity(natural_entry_setup):
    script,desktop,root,options,t=natural_entry_setup;entry=script.NaturalFeedbackChatEntry(root,**options)
    try:
        identity=entry.identity
        with http_entry(entry,desktop) as h:
            assert h.get('/health')==dict(application=desktop.APPLICATION_ID)
            assert not h.get('/status')['history']['turns'] and not t.calls
            assert 's155-draft:' in h.page and 's140-draft:' not in h.page
            assert '最近有效反馈' in h.page and '其他内容照旧' in h.page
            scope=h.post('/message-scope',dict(text='普通合成消息。'))
            assert scope['ok'] and scope['message_scope']['current_feedback'] is None and not t.calls
            chat(h,'空间暂叫青台。');select_source(h);result,req=advance(h);assert result['shared_status'] in ('committed','replayed'),result
            assert result['state']['shared_activity']['view']['activity_revision']==1
            before=h.get('/status')['shared_activity']['view']['current_plan'];assert before==PLAN
            result,_=chat(h,MESSAGE)
            assert result['state']['shared_activity']['view']['activity_revision']==2
            after=result['state']['shared_activity']['view']['current_plan']
            assert after=={k:v.replace('青台','禾台') for k,v in before.items()}
            n=len(t.calls);scope=h.post('/message-scope',dict(text='当前合成接话。'))['message_scope']
            assert scope['current_feedback']['quote']==MESSAGE and scope['activity_result']['plan']==after and len(t.calls)==n
            nxt=h.post('/shared-activity-preview',{})
            assert nxt['shared_preview']['current_feedback']['quote']==MESSAGE and len(t.calls)==n
            for i in range(3):chat(h,'合成新话题'+str(i))
            scope=h.post('/message-scope',dict(text='接着说。'))['message_scope']
            assert MESSAGE not in json.dumps(scope['recent_dialogue'],ensure_ascii=False)
            n=len(t.calls);assert h.post('/reload',{})['ok'] and entry.identity==identity and len(t.calls)==n
            result,request=advance(h);assert result['shared_status'] in ('committed','replayed') and result['state']['shared_activity']['view']['activity_revision']==3
            n=len(t.calls);assert h.post('/shared-activity-request',dict(kind='advance',request=request))['shared_status']=='replayed' and len(t.calls)==n
            assert '禾台' in result['state']['shared_activity']['view']['current_plan']['composition']
            assert h.post('/history',dict(enabled=False))['ok']
            scope=h.post('/message-scope',dict(text='独立消息。'))['message_scope']
            assert scope['current_feedback'] is None and scope['activity_result'] is None and not scope['recent_dialogue']
    finally:entry.close()

def test_partial_root_and_changed_pointer_are_preserved_and_rejected_before_open(natural_entry_setup,monkeypatch):
    script,desktop,root,options,t=natural_entry_setup;root.mkdir();marker=root/'keep.txt';marker.write_text('keep')
    with pytest.raises((ValueError,FileNotFoundError)):script.NaturalFeedbackChatEntry(root,**options)
    assert marker.read_text()=='keep' and not t.calls
    fresh=root.with_name('complete-entry');entry=script.NaturalFeedbackChatEntry(fresh,**options);entry.close()
    pointer=fresh/'current.json';value=json.loads(pointer.read_text());value['timeline_id']=str(uuid4());pointer.write_text(json.dumps(value))
    old=pointer.read_bytes();called=[]
    monkeypatch.setattr(script.NaturalFeedbackChatEntry,'_open',lambda self:called.append(True))
    with pytest.raises(RuntimeError):script.NaturalFeedbackChatEntry(fresh,**options)
    assert pointer.read_bytes()==old and not called and not t.calls

def test_production_and_prior_experiment_roots_cannot_be_used_as_fake_entry(natural_entry_setup):
    script,_,_,options,t=natural_entry_setup
    for root in (script.default_entry_root(),script.ROOT/'.artifacts/s154/new-scene-first'):
        with pytest.raises(ValueError):script.NaturalFeedbackChatEntry(root,**options)
    assert not t.calls

def test_unknown_delivery_keeps_entry_open_for_original_nonce_lookup_without_retry(natural_entry_setup,monkeypatch):
    script,desktop,root,options,t=natural_entry_setup
    def timeout(**kwargs):t.calls.append(kwargs['body']);raise TimeoutError('Synthetic UNKNOWN')
    monkeypatch.setattr(t,'post_json',timeout)
    entry=script.NaturalFeedbackChatEntry(root,**options)
    try:
        with http_entry(entry,desktop) as h:
            result,payload=advance(h)
            assert result['shared_status']=='unknown',result
            assert len(t.calls)==1
            before=h.get('/status')['history']
            assert h.post('/reload',{})['ok'] and len(t.calls)==1
            assert h.get('/status')['history']==before and before['status'] in ('available','failed-closed')
            assert h.get('/status')['shared_activity']['status']=='failed-closed'
        entry.close();entry=script.NaturalFeedbackChatEntry(root,**options)
        with http_entry(entry,desktop) as h:
            result=h.post('/shared-activity-request',dict(kind='advance',request=payload))
            assert result['shared_status']=='unknown' and len(t.calls)==1
            assert h.get('/status')['history']==before
    finally:entry.close()

def test_verified_closed_history_still_permits_same_entry_reopen_and_hides_body(natural_entry_setup,monkeypatch):
    from types import SimpleNamespace
    from dynamic_subject_agent.application import ApplicationFacade,ApplicationQueryKind
    script,desktop,root,options,t=natural_entry_setup;entry=script.NaturalFeedbackChatEntry(root,**options)
    original=ApplicationFacade.query
    def closed(self,request):
        if request.kind is ApplicationQueryKind.CONVERSATION_HISTORY:
            return SimpleNamespace(status=SimpleNamespace(value='failed-closed'),projection=None)
        return original(self,request)
    monkeypatch.setattr(ApplicationFacade,'query',closed)
    try:
        with http_entry(entry,desktop) as h:
            assert h.post('/reload',{})['ok']
            assert h.get('/status')['history']==dict(status='failed-closed',turns=[])
        entry.close();entry=script.NaturalFeedbackChatEntry(root,**options)
        assert script.NaturalFeedbackChatEntry._history_state(entry.product)==('failed-closed',None) and not t.calls
    finally:entry.close()
