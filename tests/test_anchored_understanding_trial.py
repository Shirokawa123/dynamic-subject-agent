from dataclasses import replace
from hashlib import sha256
import json
import pytest
from dynamic_subject_agent.character_understanding_trial import UnderstandingTrialRequest,run_trial
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.deepseek import DeepSeekTransport,DeepSeekHttpResponse
from dynamic_subject_agent.anchored_character_understanding import UNDERSTANDING_POLICY,REPLY_POLICY
from test_anchored_character_understanding import material,proposal


@pytest.fixture
def prepared(tmp_path,monkeypatch):
    root=tmp_path/'.artifacts';root.mkdir();directory=root/'review';directory.mkdir()
    source=root/'source.json';source.write_text('[]');materials={};cases=[]
    for role,target in [('first','甲'),('second','乙')]:
        value=material();value['target']=target;raw=canonical_json(value).encode()
        (directory/(role+'.material.json')).write_bytes(raw);materials[role]=sha256(raw).hexdigest()
        cases.append(dict(id=role+'-understanding',role=role,purpose='understanding'))
        for i in range(3):
            for condition in ('source-only','with-understanding'):
                cases.append(dict(id=f'{role}-{i}-{condition}',role=role,purpose='reply',condition=condition,question=f'合成新问题{i}'))
    review=dict(source_file=dict(path=str(source),sha256=sha256(source.read_bytes()).hexdigest()),
        anchor_source=dict(path=str(source),sha256=sha256(source.read_bytes()).hexdigest()),
        policies=dict(understanding=UNDERSTANDING_POLICY,reply=REPLY_POLICY),material_sha256=materials,
        parameters=dict(model='deepseek-flash',thinking=dict(type='disabled'),max_tokens=4096,stream=False),cases=cases,example_sha256={})
    raw=canonical_json(review).encode();digest=sha256(raw).hexdigest();(directory/'review.json').write_bytes(raw)
    from dynamic_subject_agent import anchored_understanding_trial as module
    monkeypatch.setattr(module,'REVIEW',digest)
    approval=root/'approval.json';approval.write_text(canonical_json(dict(version=module.VERSION,review_sha256=digest,
        human_confirmed=True,anchor_and_direct_reference_use_confirmed=True,maximum_requests=14,automatic_retries=0,
        persona_activation_included=False,installation_included=False,authorization_source='direct-user-reply:2026-10-31-current-chat',user_reply='合成批准')),encoding='utf-8')
    return UnderstandingTrialRequest(directory,approval,root/'result'),root/'audit'


class Transport(DeepSeekTransport):
    def __init__(self,bad=False,callback=None):self.calls=[];self.bad=bad;self.callback=callback
    def post_json(self,**kwargs):
        p=json.loads(json.loads(kwargs['body'])['messages'][1]['content']);self.calls.append(p)
        if self.callback:self.callback(kwargs)
        if 'current_message' not in p:
            value=proposal()
            for reading in value['scene_readings']:reading['observation']['about']=[p['target']]
            if self.bad:value['interpretations'][0]['evidence'][0]['quote']='错误引文'
            content=canonical_json(value)
        else:content='合成：过去的问题已经处理，可以回顾当时的经验。'
        return DeepSeekHttpResponse(200,canonical_json(dict(model='deepseek-flash',choices=[dict(finish_reason='stop',message=dict(role='assistant',content=content))],usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))).encode())


def test_same_anchor_and_scenes_in_fourteen_calls_and_no_replay(prepared):
    request,audit=prepared;t=Transport()
    result=run_trial(request,_transport_factory=lambda _:t,_audit_parent=audit,anchored=True)
    assert result['status']=='complete' and result['attempts']==len(t.calls)==14 and result['canonical_writes']==0
    for offset in (0,7):
        for q in range(3):
            a,b=t.calls[offset+1+q*2:offset+3+q*2]
            assert a['current_anchor']==b['current_anchor'] and a['source_scenes']==b['source_scenes']
            assert a['understanding'] is None and b['understanding']['interpretations'][0]['evidence']==proposal()['interpretations'][0]['evidence']
    with pytest.raises(ValueError,match='already started'):
        run_trial(replace(request,output=request.output.with_name('again')),_transport_factory=lambda _:t,_audit_parent=audit,anchored=True)
    assert len(t.calls)==14


def test_wrong_direct_evidence_stops_before_reply(prepared):
    request,audit=prepared;t=Transport(bad=True)
    result=run_trial(request,_transport_factory=lambda _:t,_audit_parent=audit,anchored=True)
    assert result['status']=='stopped' and result['attempts']==1


def test_anchor_approval_revoked_before_actual_send(prepared,monkeypatch):
    request,audit=prepared
    from dynamic_subject_agent import character_understanding_trial as transport_module
    monkeypatch.setattr(transport_module,'urlopen',lambda *a,**k:pytest.fail('network reached'))
    def factory(opener):
        def revoke(kwargs):
            from urllib.request import Request
            receipt=json.loads(request.approval_path.read_bytes());receipt['anchor_and_direct_reference_use_confirmed']=False
            request.approval_path.write_text(canonical_json(receipt),encoding='utf-8')
            opener(Request('https://api.deepseek.com/chat/completions',data=kwargs['body'],method='POST'),timeout=30)
        return Transport(callback=revoke)
    result=run_trial(request,_transport_factory=factory,_audit_parent=audit,anchored=True)
    assert result['status']=='stopped' and result['attempts']==1
