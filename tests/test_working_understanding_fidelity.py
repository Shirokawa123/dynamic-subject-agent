"""S147 exact same-use candidate Interface; synthetic transport and sources."""
from dataclasses import asdict
from hashlib import sha256
import json

import pytest

from test_original_whole_chat import approved,personality_fixture,model_fixture,send,history
from test_working_understanding import state,request,step
from test_working_understanding_live import working_live_fixture,WorkingTransport,sources,RAW
from test_whole_chat_archive import canonical_path
from dynamic_subject_agent.model_gateway import ModelTask,ModelTaskKind
from dynamic_subject_agent.local_product import open_working_understanding_product_live,validate_working_understanding_entry
from dynamic_subject_agent.shared_activity import WORKING_FACT_FAITHFUL_AUTHORITY,SharedExperienceRequest
from dynamic_subject_agent.working_understanding import FORM_POLICY,CHOICE_POLICY,REPLY_POLICY,working_contract,working_policies
from dynamic_subject_agent.working_understanding_fidelity import REFERENCE_SCOPE
from dynamic_subject_agent.working_understanding_live import (
    ApprovedWorkingUnderstandingGrant,APPROVED_WORKING_REVIEW,APPROVED_WORKING_LOCAL_CONTRACT_SHA,
    APPROVED_WORKING_POLICY_HASHES,APPROVED_WORKING_PROTOCOL_HASHES,WORKING_APPROVAL,
    WorkingFactFaithfulDevelopmentGrant,FACT_FAITHFUL_DEVELOPMENT_AUTHORIZATION,
    FACT_FAITHFUL_POLICY_HASHES,FACT_FAITHFUL_PROTOCOL_HASHES,
    working_fact_faithful_contract,working_live_contract,working_protocol_for_kind,KINDS,
    open_working_understanding_audit,digest)
from dynamic_subject_agent.working_understanding_remote_preview import working_remote_request_preview


@pytest.fixture
def faithful_fixture(working_live_fixture):
    opening,config,options,binding=working_live_fixture
    options['grant']=WorkingFactFaithfulDevelopmentGrant(APPROVED_WORKING_REVIEW,FACT_FAITHFUL_DEVELOPMENT_AUTHORIZATION)
    options['audit_path']=options['audit_path'].with_name('s147-faithful-audit')
    return opening,config,options,binding


def audit(options):
    return open_working_understanding_audit(options['audit_path'],technical_variant='fact-faithful')


def test_candidate_complete_three_purposes_exact_wire_archive_nonce_and_reopen(faithful_fixture):
    import sqlite3
    opening,config,options,_=faithful_fixture
    transport=WorkingTransport();product=opening(transport)
    assert product._qri.provider_authority==WORKING_FACT_FAITHFUL_AUTHORITY
    assert product._qri.reviewed_chat_contract['technical_variant']['timeline_schema']==7
    assert product.application.reviewed_character_chat_status().status=='active'
    validate_working_understanding_entry(config,profile_id=product.profile_id,timeline_id=product.timeline_id)
    with sqlite3.connect(canonical_path(product)) as db:
        assert db.execute('PRAGMA user_version').fetchone()==(7,)
    assert not transport.calls and transport.credential.reads==0
    sources(product)
    previews=[]
    choice=product.application.preview_working_activity('choice').view
    previews.append((ModelTaskKind.WORKING_ACTIVITY_CHOICE,choice))
    activity=step(product,'s147-independent-plan')
    assert product.application.advance_working_activity(activity).status=='committed'
    assert product.application.query_shared_activity(activity).status=='replayed'
    form=request(product,'s147-supported-form')
    formed=product.application.preview_working_understanding(form).view
    previews.append((ModelTaskKind.WORKING_UNDERSTANDING_FORM,formed))
    formation=product.application.apply_working_understanding(form)
    assert formation.status=='committed',(formation.status,formation.problem_code)
    assert product.application.query_working_understanding(form).status=='replayed'
    count=len(transport.calls)
    assert product.application.apply_working_understanding(form).status=='replayed' and len(transport.calls)==count
    saved=state(product);stored=history(product)
    assert saved['visible_understanding']['activity_result'] is not None
    product.close();fresh=WorkingTransport();product=opening(fresh)
    assert saved==state(product) and stored==history(product) and not fresh.calls and fresh.credential.reads==0
    dependent=step(product,'s147-dependent-plan')
    assert product.application.advance_working_activity(dependent).status=='committed'
    message='这次光影的位置为什么这样安排？'
    reply=product.application.preview_working_activity('reply',message).view
    previews.append((ModelTaskKind.WORKING_ACTIVITY_REPLY,reply))
    assert send(product,message,'s147-result-reply').status=='terminal'
    expected_calls=(transport.calls[2],transport.calls[3],fresh.calls[1])
    for (kind,preview),body in zip(previews,expected_calls,strict=True):
        task=ModelTask(kind,preview)
        exact=working_remote_request_preview(task,technical_variant='fact-faithful')
        assert body==exact['body'] and body['messages'][0]['content'].count(REFERENCE_SCOPE)==1
        # Identical protocol and data bytes; only the system scope is replaced.
        old=working_remote_request_preview(ModelTask(kind,dict(preview,policy=working_policies()[KINDS.index(kind)])))
        assert dict(body,messages=body['messages'][1:])==dict(old['body'],messages=old['body']['messages'][1:])
        with pytest.raises(ValueError,match='execution policy'):
            working_remote_request_preview(task)
    evidence=json.loads(fresh.calls[-1]['messages'][1]['content'])['evidence']
    assert evidence['shared_experience'] is None and evidence['working_understanding']['label']=='W1'
    assert evidence['activity_result']['plan']==asdict(state(product)['current_plan'])
    assert history(product)[-1].assistant_text==RAW and 'response_format' not in fresh.calls[-1]
    rows=audit(options).snapshot()
    assert len(rows)==6 and {r['purpose'] for r in rows}=={kind.value for kind in KINDS}
    assert {r['status'] for r in rows}=={'complete'} and RAW not in json.dumps(rows)


def test_candidate_disable_invalidates_support_plan_and_recent_inputs_without_model(faithful_fixture):
    opening,_,_,_=faithful_fixture
    transport=WorkingTransport();product=opening(transport);sources(product)
    assert product.application.apply_working_understanding(request(product,'s147-form-for-disable')).status=='committed'
    assert product.application.advance_working_activity(step(product,'s147-derived-plan')).status=='committed'
    assert send(product,'接着说这个安排。','s147-derived-dialogue').status=='terminal'
    count=len(transport.calls)
    disable=request(product,'s147-disable-understanding',action='disable')
    assert product.application.apply_working_understanding(disable).status=='committed'
    assert len(transport.calls)==count and state(product)['visible_understanding'] is None
    assert send(product,'换个话题。','s147-after-disable').status=='terminal'
    payload=json.loads(transport.calls[-1]['messages'][1]['content'])
    assert payload['evidence']==dict(shared_experience=None,activity_result=None,working_understanding=None) and payload['exchange']==[]
    e1=SharedExperienceRequest(product.profile_id,product.timeline_id,'s147-e1-refused',state(product)['revision'],1,'暖色',True)
    assert product.application.set_shared_experience(e1).status=='unavailable'
    assert product.application.set_reviewed_character_history(False).history_enabled is False
    preview=product.application.preview_working_activity('reply','当前话题。').view
    assert preview['payload']['exchange']==() and preview['payload']['evidence']['working_understanding'] is None


@pytest.mark.parametrize('prepared',[False,True])
def test_candidate_uses_existing_atomic_prepared_recovery_with_zero_new_transport(faithful_fixture,monkeypatch,prepared):
    from dynamic_subject_agent.timeline import TimelineEngine,FaultPoint,PublicationInterrupted
    opening,_,options,_=faithful_fixture
    transport=WorkingTransport();product=opening(transport);sources(product)
    form=request(product,'s147-cold-form-request')
    with monkeypatch.context() as crash:
        if prepared:
            original=TimelineEngine._hit
            def hit(engine,point):
                if point is FaultPoint.AFTER_PLAN_CLAIM:
                    raise OSError('synthetic prepared interruption')
                return original(engine,point)
            crash.setattr(TimelineEngine,'_hit',hit)
        else:
            crash.setattr(TimelineEngine,'publish',lambda *a,**kw:(_ for _ in ()).throw(PublicationInterrupted('synthetic','before preparation')))
        product.application.apply_working_understanding(form)
    assert len(transport.calls)==3
    product.close();fresh=WorkingTransport();product=opening(fresh)
    assert not fresh.calls and fresh.credential.reads==0 and bool(state(product)['visible_understanding']) is prepared
    assert product.application.apply_working_understanding(form).status==('replayed' if prepared else 'failed-closed')
    assert len(audit(options).snapshot())==3


def test_entry_validation_is_pure_and_wrong_scope_or_variant_cannot_open_or_recover(faithful_fixture,monkeypatch):
    from dynamic_subject_agent.host import RuntimeHost
    opening,config,_,_=faithful_fixture
    transport=WorkingTransport();product=opening(transport)
    profile,timeline=product.profile_id,product.timeline_id;product.close()
    before=config.state_path.read_bytes()
    monkeypatch.setattr(RuntimeHost,'open',lambda *a,**kw:pytest.fail('pure validator must not open Host'))
    validate_working_understanding_entry(config,profile_id=profile,timeline_id=timeline)
    for params in (dict(profile_id=profile,timeline_id='wrong'),dict(profile_id='wrong',timeline_id=timeline),
        dict(profile_id=profile,timeline_id=timeline,technical_variant='baseline')):
        with pytest.raises(RuntimeError):
            validate_working_understanding_entry(config,**params)
    assert config.state_path.read_bytes()==before and not transport.calls and transport.credential.reads==0


@pytest.mark.parametrize('first',['baseline','fact-faithful'])
def test_old_and_new_roots_and_audits_refuse_cross_variant_activation(working_live_fixture,first):
    opening,config,options,_=working_live_fixture
    old=options['grant'];new=WorkingFactFaithfulDevelopmentGrant(APPROVED_WORKING_REVIEW,FACT_FAITHFUL_DEVELOPMENT_AUTHORIZATION)
    options['grant']=old if first=='baseline' else new
    product=opening();product.close();before=config.state_path.read_bytes()
    other=dict(options,grant=new if first=='baseline' else old,audit_path=options['audit_path'].with_name('uncreated-other-audit'))
    transport=WorkingTransport()
    with pytest.raises(RuntimeError,match='activation-conflict'):
        open_working_understanding_product_live(config,**other,_transport=transport)
    assert before==config.state_path.read_bytes() and not other['audit_path'].exists()
    assert not transport.calls and transport.credential.reads==0
    with pytest.raises(ValueError):
        open_working_understanding_audit(options['audit_path'],technical_variant='fact-faithful' if first=='baseline' else 'baseline')


def test_candidate_policy_integrity_inherits_use_without_claiming_new_human_hashes(faithful_fixture,monkeypatch):
    import dynamic_subject_agent.working_understanding_fidelity as fidelity
    _,_,options,binding=faithful_fixture
    grant=options['grant'];grant.validate()
    old=working_live_contract(binding);candidate=working_fact_faithful_contract(binding)
    assert old['authorization']==candidate['authorization']==WORKING_APPROVAL
    assert candidate['development_authorization']==FACT_FAITHFUL_DEVELOPMENT_AUTHORIZATION
    assert candidate['technical_variant']['inherited_use_review_basis']==APPROVED_WORKING_REVIEW
    assert 'approved_review_basis' not in candidate['technical_variant']
    assert tuple(sha256(p.encode()).hexdigest() for p in working_policies('fact-faithful'))==FACT_FAITHFUL_POLICY_HASHES
    assert tuple(digest(working_protocol_for_kind(kind)) for kind in KINDS)==FACT_FAITHFUL_PROTOCOL_HASHES
    with monkeypatch.context() as changed:
        changed.setattr(fidelity,'REFERENCE_SCOPE',REFERENCE_SCOPE+' changed')
        with pytest.raises(ValueError,match='fact-faithful policy'):
            grant.validate()
    with pytest.raises(ValueError,match='development decision'):
        WorkingFactFaithfulDevelopmentGrant(APPROVED_WORKING_REVIEW,'unapproved')
    assert not options['audit_path'].exists()


def test_original_s145_s146_material_policy_and_protocol_pins_remain_literal():
    from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
    assert digest(working_contract(APPROVED_BINDING))==APPROVED_WORKING_LOCAL_CONTRACT_SHA
    assert APPROVED_WORKING_LOCAL_CONTRACT_SHA=='ddc346d616a434ebb94c5dc45145be8c7c1221266f337b21af687226300239e3'
    assert tuple(sha256(p.encode()).hexdigest() for p in (FORM_POLICY,CHOICE_POLICY,REPLY_POLICY))==APPROVED_WORKING_POLICY_HASHES
    assert APPROVED_WORKING_POLICY_HASHES==('a45773c93835e96ecb28510eafe4a6aa8531026bde059ab314f0c10652bb3527',
        'a25327a7b67d90205c9eb281b6afa0a08949cda4a54e051d6c231c44b490ee78',
        'f9ca9cbc083736e3c1500b2cda5e54a7af585f4458400c810054d44391bd0cc6')
    assert tuple(digest(working_protocol_for_kind(kind)) for kind in KINDS)==APPROVED_WORKING_PROTOCOL_HASHES
    ApprovedWorkingUnderstandingGrant(APPROVED_WORKING_REVIEW,True).validate()
