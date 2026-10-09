"""S146 production Interface with fake HTTPS/credential, never actual keys."""
from copy import deepcopy
from dataclasses import asdict,replace
import json
from threading import Thread

import pytest

from test_original_whole_chat import approved,personality_fixture,model_fixture,send,history
from test_working_understanding import state,request,step,LocalAdapter
from test_whole_chat_archive import canonical_path
from dynamic_subject_agent.deepseek import DeepSeekTransport,DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelGateway,ModelTask,ModelTaskKind,ModelGatewayFailure
from dynamic_subject_agent.local_product import open_working_understanding_product_live,open_working_understanding_product_local
from dynamic_subject_agent.working_understanding_live import (
    ApprovedWorkingUnderstandingGrant,APPROVED_WORKING_REVIEW,WorkingUnderstandingDelivery,
    open_working_understanding_audit,working_live_contract,digest)
from dynamic_subject_agent.working_understanding_remote_preview import PendingWorkingUnderstandingGrant,working_remote_request_preview
from dynamic_subject_agent.shared_activity import WORKING_LIVE_AUTHORITY,SharedExperienceRequest

RAW='  这次先比较主体旁的留白。\n再看光影的位置。  '


class FakeCredential:
    def __init__(self):
        self.reads=0

    def authorize(self,credential_ref, *, unavailable=False):
        from dynamic_subject_agent.deepseek import DEEPSEEK_CREDENTIAL_BACKEND_ID,DEEPSEEK_CREDENTIAL_KEY_ID
        self.reads+=1
        assert (credential_ref.backend_id,credential_ref.key_id)==(DEEPSEEK_CREDENTIAL_BACKEND_ID,DEEPSEEK_CREDENTIAL_KEY_ID)
        if unavailable:
            from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
            raise CharacterCredentialUnavailable()
        # No secret or plaintext token is generated, stored or resolved.


class WorkingTransport(DeepSeekTransport):
    def __init__(self,fault=None):
        self.calls=[];self.credential=FakeCredential();self.fault=fault
        self.form_override=None;self.callback=None

    def post_json(self,**kwargs):
        self.credential.authorize(kwargs['credential_ref'],unavailable=self.fault=='credential')
        body=json.loads(kwargs['body']);self.calls.append(body)
        if self.callback:
            self.callback()
        if self.fault=='timeout':
            raise TimeoutError('synthetic private timeout detail')
        payload=json.loads(body['messages'][1]['content'])
        if 'scope' in payload:
            value=self.form_override or dict(status='formed',scope='composition-text',
                statement='本次先比较暖色与桌边留白，不是永久偏好。',basis_refs=['U1','U2']+(['A1'] if payload['activity_result'] else []))
            content=canonical_json(value)
        elif 'current_activity' in payload:
            action=payload['current_activity']['allowed_actions'][0]
            understanding=payload['working_understanding']
            value=dict(action=action,plan=dict(subject='静物',composition='合成独立布局'+str(len(self.calls)) if understanding is None else understanding['statement'],focus='光线')
                if action in ('start','revise') else None,reason_code='balance-space',basis_refs=[] if understanding is None else ['W1'],decision_note='合成取舍只保本地。')
            content=canonical_json(value)
        else:
            content=RAW
        if self.fault=='blank':
            content=' \n\t'
        message=dict(role='user' if self.fault=='role' else 'assistant',content=content,
            reasoning_content='discarded synthetic hidden content never used as final reply')
        return DeepSeekHttpResponse(200,canonical_json(dict(model='deepseek-flash',
            choices=[dict(finish_reason='stop',message=message)],
            usage=dict(prompt_tokens=100,completion_tokens=20,total_tokens=120))).encode())


@pytest.fixture
def working_live_fixture(approved,monkeypatch,tmp_path):
    author,config,freeze,view=approved
    frozen=author.application.freeze_source_identity(freeze)
    assert frozen.status=='created';author.close()
    asset=json.loads(view.runtime_asset_json)
    import dynamic_subject_agent.original_whole_chat as whole
    binding=dict(definition_basis=view.definition_basis,runtime_asset_sha=view.runtime_asset_sha,
        persona_digest=asset['persona_digest'],review_basis='1'*64,scope_digest='2'*64,
        subject_id=asset['subject']['subject_id'],anchor_id=asset['anchor']['anchor_id'])
    monkeypatch.setattr(whole,'APPROVED_BINDING',binding)
    import dynamic_subject_agent.working_understanding_live as live
    from dynamic_subject_agent.working_understanding import working_contract
    monkeypatch.setattr(live,'APPROVED_WORKING_MATERIAL_DIGEST',digest(binding))
    monkeypatch.setattr(live,'APPROVED_WORKING_LOCAL_CONTRACT_SHA',digest(working_contract(binding)))
    options=dict(identity_id=frozen.view.identity_id,grant=ApprovedWorkingUnderstandingGrant(APPROVED_WORKING_REVIEW,True),audit_path=tmp_path/'s146-working-audit')
    opened=[]
    def opening(transport=None,observations=None):
        product=open_working_understanding_product_live(config,**options,_transport=transport or WorkingTransport(),observations=observations)
        opened.append(product)
        return product
    yield opening,config,options,binding
    for product in opened:
        product.close()


def sources(product):
    assert send(product,'这一次构图试少量暖色。','working-live-source-a').status=='terminal'
    assert send(product,'桌边留白可以帮助看清主体。','working-live-source-b').status=='terminal'


def test_exact_live_three_purposes_current_result_original_text_reopen_nonce_and_audit(working_live_fixture):
    import sqlite3
    opening,_,options,_=working_live_fixture
    transport=WorkingTransport();observations=[];product=opening(transport,observations)
    assert product._qri.provider_authority==WORKING_LIVE_AUTHORITY and not transport.calls and transport.credential.reads==0
    assert product.application.reviewed_character_chat_status().status=='active'
    with sqlite3.connect(canonical_path(product)) as db:
        assert db.execute('PRAGMA user_version').fetchone()==(7,)
    sources(product)
    assert history(product)[0].assistant_text==RAW
    preview=product.application.preview_working_activity('choice').view
    advance=step(product,'working-live-independent-plan')
    assert product.application.advance_working_activity(advance).status=='committed'
    assert transport.calls[-1]==working_remote_request_preview(ModelTask(ModelTaskKind.WORKING_ACTIVITY_CHOICE,preview))['body']
    form=request(product,'working-live-form-source-1')
    preview=product.application.preview_working_understanding(form).view
    assert product.application.apply_working_understanding(form).status=='committed'
    assert transport.calls[-1]==working_remote_request_preview(ModelTask(ModelTaskKind.WORKING_UNDERSTANDING_FORM,preview))['body']
    saved=state(product);stored=history(product);count=len(transport.calls)
    assert product.application.apply_working_understanding(form).status=='replayed' and len(transport.calls)==count
    product.close();fresh=WorkingTransport();product=opening(fresh)
    assert state(product)==saved and history(product)==stored and not fresh.calls and fresh.credential.reads==0
    assert product.application.advance_working_activity(step(product,'working-live-dependent-plan')).status=='committed'
    message='说说这一版的文字安排。'
    preview=product.application.preview_working_activity('reply',message).view
    assert send(product,message,'working-live-current-result').status=='terminal'
    expected=working_remote_request_preview(ModelTask(ModelTaskKind.WORKING_ACTIVITY_REPLY,preview))
    assert fresh.calls[-1]==expected['body'] and 'response_format' not in fresh.calls[-1]
    payload=json.loads(fresh.calls[-1]['messages'][1]['content'])
    assert payload['evidence']['activity_result']['plan']==asdict(state(product)['current_plan'])
    assert payload['evidence']['working_understanding'] is not None and payload['evidence']['shared_experience'] is None
    assert history(product)[-1].assistant_text==RAW
    rows=open_working_understanding_audit(options['audit_path']).snapshot()
    assert len(rows)==6 and {row['purpose'] for row in rows}=={'working-understanding-form','working-activity-choice','working-activity-reply'}
    assert {row['status'] for row in rows}=={'complete'}
    assert rows[-1]['output_digest']==digest(dict(reply_text=RAW,language='zh'))
    assert RAW not in canonical_json(rows) and RAW not in canonical_json(observations)


@pytest.mark.parametrize('fault,status,code',[
    ('blank','failed-closed','response-content-empty'),('role','failed-closed','response-envelope'),
    ('timeout','unknown','transport-timeout'),('credential','unavailable','character-credential-unavailable')])
def test_live_text_failures_have_exact_typed_audit_no_fallback_no_retry(working_live_fixture,fault,status,code):
    opening,_,options,_=working_live_fixture
    transport=WorkingTransport(fault);observations=[];product=opening(transport,observations)
    result=send(product,'合成失败问题。','working-live-failure-'+fault)
    assert result.status==status and result.projection.failure_code=='original-whole-'+code
    if status!='unknown':
        assert history(product)==()
    else:
        assert product.application.query_working_understanding().status=='failed-closed'
    assert transport.credential.reads==1 and len(transport.calls)==(0 if fault=='credential' else 1)
    row=open_working_understanding_audit(options['audit_path']).snapshot()[0]
    assert row['status']==status and row['output_digest'] is None
    assert observations[0]['status']==status and observations[0]['error_code']==code
    assert 'hidden content' not in canonical_json(observations) and 'private timeout detail' not in canonical_json(observations)


def test_insufficient_is_remote_complete_but_canonical_typed_noop_preserving_old_understanding(working_live_fixture):
    opening,_,options,_=working_live_fixture
    transport=WorkingTransport();product=opening(transport);sources(product)
    assert product.application.apply_working_understanding(request(product,'working-live-old-form')).status=='committed'
    old=state(product)['understanding']
    transport.form_override=dict(status='insufficient',scope='composition-text',statement='',basis_refs=[])
    form=request(product,'working-live-insufficient-form')
    result=product.application.apply_working_understanding(form)
    assert result.status=='no-op' and result.problem_code=='working-understanding-insufficient' and result.receipt
    assert state(product)['understanding']==old and state(product)['formation_status']=='insufficient'
    count=len(transport.calls)
    assert product.application.query_working_understanding(form).status=='no-op'
    assert product.application.apply_working_understanding(form).status=='no-op' and len(transport.calls)==count
    assert open_working_understanding_audit(options['audit_path']).snapshot()[-1]['status']=='complete'


def test_pending_and_local_qualification_never_convert_to_live_or_create_audit(working_live_fixture):
    _,config,options,binding=working_live_fixture
    transport=WorkingTransport()
    with pytest.raises(ValueError):
        open_working_understanding_product_live(None,**dict(options,grant=PendingWorkingUnderstandingGrant(APPROVED_WORKING_REVIEW)),_transport=transport)
    local=open_working_understanding_product_local(config,gateway=ModelGateway(LocalAdapter()),identity_id=options['identity_id'],binding=binding)
    local.close();before=config.state_path.read_bytes()
    with pytest.raises(RuntimeError,match='activation-conflict'):
        open_working_understanding_product_live(config,**options,_transport=transport)
    assert config.state_path.read_bytes()==before and not options['audit_path'].exists() and not transport.calls and transport.credential.reads==0


@pytest.mark.parametrize('when',['before-claim','after-claim'])
def test_reconstruction_mismatch_is_refused_before_fake_credential_or_https(working_live_fixture,monkeypatch,when):
    opening,_,options,_=working_live_fixture
    transport=WorkingTransport();product=opening(transport)
    original=WorkingUnderstandingDelivery.claim
    def changed(sender,operation,task,rebuild):
        modified=deepcopy(task.payload);modified['payload']['background']['runtime_identity']['subject_name']='wrong synthetic scope'
        if when=='before-claim':
            return original(sender,operation,ModelTask(task.kind,modified),rebuild)
        original(sender,operation,task,rebuild)
        ticket=replace(sender._ticket,rebuild=lambda:modified)
        sender._ticket=sender._pending=ticket
    monkeypatch.setattr(WorkingUnderstandingDelivery,'claim',changed)
    result=send(product,'合成重建问题。','working-live-rebuild-'+when)
    assert result.status=='failed-closed' and not transport.calls and transport.credential.reads==0
    assert result.projection.failure_code=='original-whole-delivery-unverified'
    rows=open_working_understanding_audit(options['audit_path']).snapshot()
    assert len(rows)==(0 if when=='before-claim' else 1)
    if rows:
        assert rows[0]['status']=='failed-closed'


@pytest.mark.parametrize('prepared',[False,True])
def test_cold_live_formation_has_zero_new_https_and_prepared_is_atomic(working_live_fixture,monkeypatch,prepared):
    from dynamic_subject_agent.timeline import TimelineEngine,FaultPoint,PublicationInterrupted
    opening,_,options,_=working_live_fixture
    transport=WorkingTransport();product=opening(transport);sources(product)
    form=request(product,'working-live-cold-form-1')
    with monkeypatch.context() as crash:
        if prepared:
            original=TimelineEngine._hit
            def hit(engine,point):
                if point is FaultPoint.AFTER_PLAN_CLAIM:
                    raise OSError('synthetic immutable prepared interruption')
                return original(engine,point)
            crash.setattr(TimelineEngine,'_hit',hit)
        else:
            crash.setattr(TimelineEngine,'publish',lambda *a,**kw:(_ for _ in ()).throw(PublicationInterrupted('synthetic','before preparation')))
        product.application.apply_working_understanding(form)
    assert len(transport.calls)==3
    product.close();fresh=WorkingTransport();product=opening(fresh)
    assert not fresh.calls and fresh.credential.reads==0 and bool(state(product)['visible_understanding']) is prepared
    assert product.application.apply_working_understanding(form).status==('replayed' if prepared else 'failed-closed')
    assert len(open_working_understanding_audit(options['audit_path']).snapshot())==3


def test_disable_and_history_off_filter_live_input_and_do_not_grant_e1(working_live_fixture):
    opening,_,_,_=working_live_fixture
    transport=WorkingTransport();product=opening(transport);sources(product)
    assert product.application.apply_working_understanding(request(product,'working-live-form-for-disable')).status=='committed'
    assert product.application.advance_working_activity(step(product,'working-live-dependent-for-disable')).status=='committed'
    assert send(product,'承接这个方案。','working-live-derived-reply').status=='terminal'
    count=len(transport.calls)
    assert send(product,'不要再使用之前的聊天。','working-live-withdrawal').status=='failed-closed'
    assert len(transport.calls)==count
    e1=SharedExperienceRequest(product.profile_id,product.timeline_id,'working-live-rejected-e1',state(product)['revision'],1,'暖色',True)
    assert product.application.set_shared_experience(e1).status=='unavailable'
    assert product.application.apply_working_understanding(request(product,'working-live-disable-no-model',action='disable')).status=='committed'
    assert len(transport.calls)==count
    assert send(product,'继续一个新话题。','working-live-after-disable').status=='terminal'
    payload=json.loads(transport.calls[-1]['messages'][1]['content'])
    assert payload['evidence']==dict(shared_experience=None,activity_result=None,working_understanding=None) and payload['exchange']==[]
    assert product.application.set_reviewed_character_history(False).history_enabled is False
    assert send(product,'历史已关闭后的当前话题。','working-live-history-off').status=='terminal'
    assert json.loads(transport.calls[-1]['messages'][1]['content'])['exchange']==[]


def test_tickets_are_same_client_same_thread_once_only_before_fake_key_or_https(working_live_fixture):
    from dynamic_subject_agent.working_understanding_provider import DeepSeekWorkingUnderstandingAdapter
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import DEEPSEEK_CREDENTIAL_BACKEND_ID,DEEPSEEK_CREDENTIAL_KEY_ID
    opening,config,options,binding=working_live_fixture
    product=opening();preview=product.application.preview_working_activity('choice').view
    task=ModelTask(ModelTaskKind.WORKING_ACTIVITY_CHOICE,preview)
    audit=open_working_understanding_audit(options['audit_path']);transport=WorkingTransport()
    def client():
        sender=WorkingUnderstandingDelivery(grant=options['grant'],audit=audit,contract=working_live_contract(binding),state_path=config.state_path)
        adapter=DeepSeekWorkingUnderstandingAdapter(transport=transport,delivery=sender,
            credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,key_id=DEEPSEEK_CREDENTIAL_KEY_ID))
        return sender,ModelGateway(adapter)
    owner,gateway=client();other,foreign=client()
    owner.claim('working-ticket-client-1',task,lambda:deepcopy(preview))
    with pytest.raises(ModelGatewayFailure,match='delivery-unverified'):
        foreign.execute(task)
    assert not transport.calls and transport.credential.reads==0
    assert gateway.execute(task).kind is task.kind
    with pytest.raises(ModelGatewayFailure,match='delivery-unverified'):
        gateway.execute(task)
    assert len(transport.calls)==1 and transport.credential.reads==1
    threaded,gateway=client();threaded.claim('working-ticket-thread-2',task,lambda:deepcopy(preview))
    errors=[]
    def elsewhere():
        try:
            threaded.consume(task)
        except ValueError:
            errors.append(True)
    worker=Thread(target=elsewhere);worker.start();worker.join()
    assert errors
    with pytest.raises(ModelGatewayFailure,match='delivery-unverified'):
        gateway.execute(task)
    assert len(transport.calls)==1 and transport.credential.reads==1 and audit.snapshot()[-1]['status']=='failed-closed'


def test_authoritative_history_change_after_claim_rebuilds_before_fake_credential_or_https(working_live_fixture,monkeypatch):
    opening,_,options,_=working_live_fixture
    transport=WorkingTransport();product=opening(transport)
    original=WorkingUnderstandingDelivery.claim
    def revoked(sender,operation,task,rebuild):
        original(sender,operation,task,rebuild)
        assert product.application.set_reviewed_character_history(False).history_enabled is False
    monkeypatch.setattr(WorkingUnderstandingDelivery,'claim',revoked)
    result=send(product,'当前合成范围问题。','working-live-history-race')
    assert result.status=='failed-closed' and not transport.calls and transport.credential.reads==0
    assert result.projection.failure_code=='original-whole-delivery-unverified'
    assert open_working_understanding_audit(options['audit_path']).snapshot()[-1]['status']=='failed-closed'


def test_exact_material_policy_protocol_and_slot_pins_cannot_follow_changed_source(working_live_fixture,monkeypatch):
    _,_,options,_=working_live_fixture
    grant=options['grant'];grant.validate()
    import dynamic_subject_agent.working_understanding_live as live
    import dynamic_subject_agent.original_whole_chat as whole
    with monkeypatch.context() as changed:
        changed.setattr(whole,'APPROVED_BINDING',dict(whole.APPROVED_BINDING,runtime_asset_sha='f'*64))
        with pytest.raises(ValueError,match='material'):
            grant.validate()
    with monkeypatch.context() as changed:
        changed.setattr(live,'FORM_POLICY',live.FORM_POLICY+' changed')
        with pytest.raises(ValueError,match='policy'):
            grant.validate()
    with monkeypatch.context() as changed:
        original=live.working_protocol_for_kind
        changed.setattr(live,'working_protocol_for_kind',lambda kind:dict(original(kind),slot=dict(provider_id='deepseek',account_id='other')))
        with pytest.raises(ValueError,match='protocol or slot'):
            grant.validate()
    assert not options['audit_path'].exists()
