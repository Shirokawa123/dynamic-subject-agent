from dataclasses import replace
from hashlib import sha256
import json
import pytest
from dynamic_subject_agent.character_understanding_trial import UnderstandingTrialRequest,run_trial,VERSION
from dynamic_subject_agent.character_understanding import UNDERSTANDING_POLICY,REPLY_POLICY
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.deepseek import DeepSeekTransport,DeepSeekHttpResponse
from test_character_understanding import material,proposal


@pytest.fixture
def prepared(tmp_path,monkeypatch):
    root=tmp_path/'.artifacts';root.mkdir();directory=root/'review';directory.mkdir()
    source=root/'original.json';source.write_text('[]');cases=[];materials={}
    for role,name in [('first','甲'),('second','乙')]:
        raw=canonical_json(material(name)).encode();(directory/(role+'.material.json')).write_bytes(raw)
        materials[role]=sha256(raw).hexdigest();cases.append(dict(id=role+'-understanding',role=role,purpose='understanding'))
        for q in range(2):
            for condition in ('source-only','with-understanding'):
                cases.append(dict(id=f'{role}-{q}-{condition}',role=role,purpose='reply',condition=condition,question=f'合成新问题{q}'))
    review=dict(source_file=dict(path=str(source),sha256=sha256(source.read_bytes()).hexdigest()),
        policies=dict(understanding=UNDERSTANDING_POLICY,reply=REPLY_POLICY),material_sha256=materials,
        parameters=dict(model='deepseek-flash',thinking=dict(type='disabled'),max_tokens=4096,stream=False),cases=cases,example_sha256={})
    raw=canonical_json(review).encode();digest=sha256(raw).hexdigest();(directory/'review.json').write_bytes(raw)
    from dynamic_subject_agent import character_understanding_trial as module
    monkeypatch.setattr(module,'REVIEW',digest)
    approval=root/'approval.json';approval.write_text(canonical_json(dict(version=VERSION,review_sha256=digest,
        human_confirmed=True,source_excerpt_use_confirmed=True,maximum_requests=10,automatic_retries=0,
        persona_activation_included=False,installation_included=False,authorization_source='direct-user-reply:2026-10-31-current-chat',user_reply='合成批准')),encoding='utf-8')
    return UnderstandingTrialRequest(directory,approval,root/'result'),root/'audit'


class Transport(DeepSeekTransport):
    def __init__(self,bad=False,callback=None,empty=False):self.calls=[];self.bad=bad;self.callback=callback;self.empty=empty
    def post_json(self,**kwargs):
        p=json.loads(json.loads(kwargs['body'])['messages'][1]['content']);self.calls.append(p)
        if self.callback:self.callback(kwargs)
        if 'current_message' not in p:
            value=proposal();value['observations'][0]['about']=[p['target']]
            if self.bad:value['observations'][0]['evidence'][0]['quote']='不存在的原话'
            if self.empty:value=dict(observations=[],interpretations=[])
            content=canonical_json(value)
        else:content='合成直接回答' if p['understanding'] is None else '合成理解后回答'
        return DeepSeekHttpResponse(200,canonical_json(dict(model='deepseek-flash',choices=[dict(finish_reason='stop',message=dict(role='assistant',content=content))],usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))).encode())


def test_two_roles_same_flow_matches_sources_and_forwards_actual_understanding(prepared):
    request,audit=prepared;t=Transport()
    before={p:sha256(p.read_bytes()).hexdigest() for p in request.review_directory.iterdir()}
    r=run_trial(request,_transport_factory=lambda _:t,_audit_parent=audit)
    assert r['status']=='complete' and r['attempts']==len(t.calls)==10 and r['canonical_writes']==0
    assert not r['persona_activated'] and not (request.output/'identity').exists()
    for offset in (0,5):
        for q in range(2):
            a,b=t.calls[offset+1+2*q:offset+3+2*q]
            assert a['understanding'] is None and b['understanding']['status']=='unreviewed-model-proposal'
            assert a['source_scenes']==b['source_scenes'] and a['current_message']==b['current_message']
            assert b['understanding']['interpretations'][0]['choice']==proposal()['interpretations'][0]['choice']
    assert before=={p:sha256(p.read_bytes()).hexdigest() for p in before}
    with pytest.raises(ValueError,match='already started'):
        run_trial(replace(request,output=request.output.with_name('again')),_transport_factory=lambda _:t,_audit_parent=audit)
    assert len(t.calls)==10


def test_bad_citation_stops_before_any_dialogue_without_hand_filling(prepared):
    request,audit=prepared;t=Transport(bad=True)
    r=run_trial(request,_transport_factory=lambda _:t,_audit_parent=audit)
    assert r['status']=='stopped' and r['attempts']==1 and len(t.calls)==1
    assert not list(request.output.glob('*.understanding.json'))


def test_insufficient_understanding_returns_noop_without_claiming_comparison(prepared):
    request,audit=prepared;t=Transport(empty=True)
    r=run_trial(request,_transport_factory=lambda _:t,_audit_parent=audit)
    assert r['status']=='no-op' and r['attempts']==1 and len(t.calls)==1
    assert r['rows'][0]['interpretations']==0


def test_excerpt_use_requires_explicit_approval(prepared):
    request,audit=prepared;t=Transport();value=json.loads(request.approval_path.read_bytes())
    value['source_excerpt_use_confirmed']=False;request.approval_path.write_text(canonical_json(value),encoding='utf-8')
    with pytest.raises(ValueError,match='excerpt'):run_trial(request,_transport_factory=lambda _:t,_audit_parent=audit)
    assert not t.calls and not request.output.exists()


def test_revocation_before_final_delivery_prevents_network(prepared,monkeypatch):
    request,audit=prepared
    from dynamic_subject_agent import character_understanding_trial as module
    monkeypatch.setattr(module,'urlopen',lambda *a,**kw:pytest.fail('unapproved network call'))
    def factory(opener):
        def revoke(kwargs):
            from urllib.request import Request
            value=json.loads(request.approval_path.read_bytes());value['source_excerpt_use_confirmed']=False
            request.approval_path.write_text(canonical_json(value),encoding='utf-8')
            opener(Request('https://api.deepseek.com/chat/completions',data=kwargs['body'],method='POST'),timeout=30)
        return Transport(callback=revoke)
    r=run_trial(request,_transport_factory=factory,_audit_parent=audit)
    assert r['status']=='stopped' and r['attempts']==1
