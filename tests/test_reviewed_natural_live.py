"""Full LIVE composition with synthetic transport and no credentials/network."""
from dataclasses import replace
from hashlib import sha256
import json
import pytest
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.deepseek import DeepSeekTransport,DeepSeekHttpResponse
from dynamic_subject_agent.natural_conversation_live import NaturalConversationRequest,run_trial
from dynamic_subject_agent.reviewed_natural_reply import PROTOCOL,REPAIR_POLICY
from dynamic_subject_agent.activity_reply_review import POLICY,PARAMETERS
from test_original_whole_chat import approved,model_fixture,personality_fixture
from test_natural_conversation_live import TEXTS
from test_reviewed_natural_conversation import BAD,BAD_REPAIR,GOOD


@pytest.fixture
def material(approved,tmp_path,monkeypatch):
    author,_,freeze,view=approved;author.close()
    import dynamic_subject_agent.memorie_companion_contract as memorie
    import dynamic_subject_agent.reviewed_natural_live as live
    import dynamic_subject_agent.natural_experience_cycle as cycle
    monkeypatch.setattr(memorie,'DEFINITION',view.definition_basis)
    root=tmp_path/'.artifacts';root.mkdir();directory=root/'review';directory.mkdir()
    preparation=root/'preparation.json';preparation.write_text(canonical_json(dict(definition_json=freeze.preparation_json)),encoding='utf-8')
    asset=json.loads(view.runtime_asset_json)
    background=dict(character=dict(name=asset['subject']['name'],stage=asset['initial_stage'],knowledge=[
        {k:row[k] for k in ('dimension','kind','statement','event_time','knowledge_time')} for row in asset['eligible']]),personality=asset['personality'])
    source=dict(background,current_user_text=TEXTS[0],current_experience=None)
    preview=canonical_json(dict(messages=[{},dict(content=canonical_json(source))])).encode()
    (directory/'first-selection.UNSENT.json').write_bytes(preview)
    parameters=dict(model='deepseek-flash',thinking=dict(type='disabled'),max_tokens=4096)
    fields=['character','personality','current_user_text','experience','exchange','activity_evidence']
    review=dict(protocol=PROTOCOL,preparation_sha256=sha256(preparation.read_bytes()).hexdigest(),
        examples_sha256={'first-selection':sha256(preview).hexdigest()},
        selection=dict(parameters=dict(parameters,response_format=dict(type='json_object')),policy='Synthetic selection',fields=list(source)),
        draft=dict(parameters=parameters,policy='Synthetic draft',fields=fields),
        repair=dict(parameters=parameters,policy=REPAIR_POLICY,fields=fields+['rejected_reply','review_issues']),
        review=dict(parameters=PARAMETERS,policy=POLICY,fields=['character','current_message','exchange','activity_evidence','candidate_text']),
        scenario=[dict(id='t'+str(i+1),text=t,reopen_before=i==3) for i,t in enumerate(TEXTS)])
    raw=canonical_json(review).encode();digest=sha256(raw).hexdigest();(directory/'review.json').write_bytes(raw)
    monkeypatch.setattr(live,'REVIEW',digest);monkeypatch.setattr(cycle,'CHECKED_REVIEW',digest)
    approval=root/'approval.json';approval.write_text(canonical_json(dict(version='reviewed-natural-conversation-use-m034-1',
        review_sha256=digest,human_confirmed=True,maximum_requests=30,automatic_retries=0,installation_included=False,
        user_data_upgrade_included=False,authorization_source='direct-user-reply:2026-10-30-current-chat',user_reply='同意这次完整隔离验证')),encoding='utf-8')
    return NaturalConversationRequest(directory,approval,preparation,root/'result'),root/'audit'


class Transport(DeepSeekTransport):
    def __init__(self,*,bad_first=True,fail_correction=False,callback=None):
        self.calls=[];self.bad_first=bad_first;self.fail_correction=fail_correction;self.callback=callback
    def post_json(self,**kwargs):
        body=json.loads(kwargs['body']);p=json.loads(body['messages'][1]['content']);self.calls.append(p)
        if self.callback:self.callback(kwargs)
        text=p.get('current_user_text',p.get('current_message'))
        if 'current_experience' in p:
            value=dict(action='remember',duration='today',reason_code='correction' if text==TEXTS[2] else 'temporary') if text in (TEXTS[0],TEXTS[2]) else dict(action='forget',duration=None,reason_code='explicit-forget') if text==TEXTS[4] else dict(action='keep',duration=None,reason_code='irrelevant')
            content=canonical_json(value)
        elif 'candidate_text' in p:
            value=dict(verdict='unsupported',issues=[dict(quote=p['candidate_text'],kind='unsupported_event',basis_labels=[])]) if p['candidate_text'] in (BAD,BAD_REPAIR) else dict(verdict='supported',issues=[])
            content=canonical_json(value)
        elif 'rejected_reply' in p:
            assert p['rejected_reply']==BAD and p['review_issues'][0]['quote']==BAD
            content=BAD_REPAIR if self.fail_correction and text==TEXTS[2] else GOOD
        else:content=BAD if self.bad_first else GOOD
        return DeepSeekHttpResponse(200,canonical_json(dict(model='deepseek-flash',choices=[dict(finish_reason='stop',message=dict(role='assistant',content=content))],usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))).encode())


@pytest.mark.parametrize('bad_first',[False,True])
def test_complete_six_turns_eighteen_or_thirty_requests_and_no_draft_history(material,bad_first):
    request,audit=material;transport=Transport(bad_first=bad_first)
    result=run_trial(request,_transport_factory=lambda _:transport,_audit_parent=audit,reviewed=True)
    assert result['status']=='complete',result
    assert result['attempts']==len(transport.calls)==(30 if bad_first else 18)
    assert result['reopen']==dict(same_scope=True,same_state=True,model_calls=0)
    assert all(row['reply_text']==GOOD for row in result['rows'])
    assert result['rows'][2]['experience']['duration']=='today' and result['rows'][4]['experience'] is None
    drafts=[p for p in transport.calls if 'experience' in p and 'rejected_reply' not in p]
    assert drafts[3]['exchange']==[dict(user_text=TEXTS[2],assistant_text=GOOD)]
    assert drafts[5]['exchange']==[dict(user_text=TEXTS[4],assistant_text=GOOD)]
    assert BAD not in str([p['exchange'] for p in transport.calls if 'exchange' in p])
    with pytest.raises(ValueError,match='already started'):
        run_trial(replace(request,output=request.output.with_name('second')),_transport_factory=lambda _:transport,_audit_parent=audit,reviewed=True)


def test_second_rejection_stops_without_replacing_previous_memory(material):
    request,audit=material;transport=Transport(fail_correction=True)
    result=run_trial(request,_transport_factory=lambda _:transport,_audit_parent=audit,reviewed=True)
    assert result['status']=='stopped' and result['attempts']==15
    assert result['rows'][-1]['failure_code'] and result['rows'][-1]['reply_text'] is None
    assert result['rows'][-1]['experience']['quote']==TEXTS[0]


def test_approval_revoked_before_draft_delivery_blocks_network(material,monkeypatch):
    request,audit=material
    import dynamic_subject_agent.reviewed_natural_live as module
    monkeypatch.setattr(module,'urlopen',lambda *a,**k:pytest.fail('network reached'))
    transport=None
    def factory(opener):
        nonlocal transport
        def revoke(kwargs):
            if len(transport.calls)==2:
                from urllib.request import Request
                value=json.loads(request.approval_path.read_bytes());value['human_confirmed']=False
                request.approval_path.write_text(canonical_json(value),encoding='utf-8')
                opener(Request('https://api.deepseek.com/chat/completions',data=kwargs['body'],method='POST'),timeout=30)
        if transport is None:transport=Transport(callback=revoke)
        else:transport.callback=revoke
        return transport
    result=run_trial(request,_transport_factory=factory,_audit_parent=audit,reviewed=True)
    assert result['status']=='stopped' and result['attempts']==2
    assert result['rows'][0]['experience'] is None
