"""Approved LIVE wiring with fake HTTPS; never resolves a credential or calls a model."""
import json
from copy import deepcopy
from dataclasses import asdict
import pytest

from test_original_whole_chat import approved, personality_fixture, model_fixture, send, history
from test_integrated_character import LocalAdapter, PLAN, MESSAGE
from test_living_activity import state, control, act, action_request
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind, ModelGatewayFailure
from dynamic_subject_agent.integrated_character import integrated_contract
from dynamic_subject_agent.integrated_character_live import (
    ApprovedIntegratedCharacterGrant, APPROVED_INTEGRATED_REVIEW, IntegratedCharacterDelivery, open_integrated_character_audit)
from dynamic_subject_agent.integrated_character_remote_preview import integrated_remote_request_preview
from dynamic_subject_agent.local_product import open_integrated_character_product_live


class IntegratedTransport(DeepSeekTransport):
    def __init__(self, fault=None):
        self.calls, self.fault, self.synthetic = [], fault, LocalAdapter()
    def post_json(self, **kwargs):
        body=json.loads(kwargs['body']); self.calls.append(body)
        if self.fault=='timeout': raise TimeoutError('synthetic delivery unknown')
        if self.fault=='credential':
            from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
            raise CharacterCredentialUnavailable()
        payload=json.loads(body['messages'][1]['content'])
        kind=ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK if 'turn' in payload else ModelTaskKind.LIVING_ACTIVITY_SHARE if 'activity_result' in payload else ModelTaskKind.LIVING_ACTIVITY_CHOICE
        value=self.synthetic.invoke(ModelTask(kind,dict(policy=body['messages'][0]['content'],payload=payload))).value
        if self.fault=='extra': value=dict(value,activity_revision=1)
        content='' if self.fault in ('blank','length') else value['reply_text'] if 'response_format' not in body else canonical_json(value)
        if self.fault not in ('blank','length') and 'response_format' not in body and '第一行只能是[revise]' in body['messages'][0]['content']:
            content=f"[{value['intent']}]\n{value['reply_text']}"
        if self.fault=='trailing': content += ','
        return DeepSeekHttpResponse(200,canonical_json(dict(model='deepseek-flash',choices=[dict(
            finish_reason='length' if self.fault=='length' else 'stop',message=dict(role='assistant',content=content,
                reasoning_content='SYNTHETIC_REASONING_NEVER_RETAIN'))],
            usage=dict(prompt_tokens=100,completion_tokens=4096 if self.fault=='length' else 30,total_tokens=4196 if self.fault=='length' else 130))).encode())


@pytest.fixture
def integrated_live_fixture(approved,monkeypatch,tmp_path):
    author,config,request,view=approved
    frozen=author.application.freeze_source_identity(request); assert frozen.status=='created'; author.close()
    asset=json.loads(view.runtime_asset_json)
    import dynamic_subject_agent.original_whole_chat as module
    binding=dict(definition_basis=view.definition_basis,runtime_asset_sha=view.runtime_asset_sha,persona_digest=asset['persona_digest'],
        review_basis='1'*64,scope_digest='2'*64,subject_id=asset['subject']['subject_id'],anchor_id=asset['anchor']['anchor_id'])
    monkeypatch.setattr(module,'APPROVED_BINDING',binding)
    import dynamic_subject_agent.integrated_character_live as live
    monkeypatch.setattr(live,'APPROVED_INTEGRATED_MATERIAL',live.digest(binding))
    monkeypatch.setattr(live,'APPROVED_INTEGRATED_LOCAL_CONTRACT',live.digest(integrated_contract(binding)))
    options=dict(identity_id=frozen.view.identity_id,grant=ApprovedIntegratedCharacterGrant(APPROVED_INTEGRATED_REVIEW,True),audit_path=tmp_path/'integrated-live-audit')
    opened=[]
    def opening(transport=None,observations=None,**kwargs):
        product=open_integrated_character_product_live(config,**options,_transport=transport or IntegratedTransport(),observations=observations,**kwargs)
        opened.append(product);return product
    yield opening,config,options,binding
    for product in opened: product.close()


def start(integrated_live_fixture):
    opening,_,options,_=integrated_live_fixture
    transport=IntegratedTransport(); observations=[]; product=opening(transport,observations)
    assert not transport.calls and not open_integrated_character_audit(options['audit_path']).snapshot()
    assert control(product,paused=False,sharing=True).status=='committed'
    assert act(product).status=='committed'
    return product,transport,observations


def test_live_three_purposes_exact_wire_reopen_and_no_repeat(integrated_live_fixture):
    opening,_,options,_=integrated_live_fixture
    product,transport,observations=start(integrated_live_fixture)
    assert act(product,'share','integrated-live-share-1').status=='committed'
    preview=product.application.preview_natural_feedback(MESSAGE)
    assert send(product,MESSAGE,'integrated-live-feedback-1').status=='terminal'
    expected=integrated_remote_request_preview(ModelTask(ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK,preview.view))
    assert transport.calls[-1]==expected['body'] and observations[-1]['wire_sha256']==expected['wire_sha256']
    updated=state(product)['current_plan']
    assert asdict(updated)=={k:v.replace('松架','杉架') for k,v in PLAN.items()}
    for index in range(3): assert send(product,'合成换题'+str(index),'integrated-live-topic-'+str(index)).status=='terminal'
    saved=history(product); identity=(product.profile_id,product.timeline_id); product.close()
    fresh=IntegratedTransport(); product=opening(fresh,observations)
    assert not fresh.calls and history(product)==saved and identity==(product.profile_id,product.timeline_id)
    req=action_request(product,key='integrated-live-next-choice')
    assert product.application.advance_living_activity(req).status=='committed'
    payload=json.loads(fresh.calls[-1]['messages'][1]['content'])
    assert payload['current_feedback']==dict(label='F1',quote=MESSAGE)
    assert state(product)['current_plan'].composition==updated.composition
    assert product.application.advance_living_activity(req).status=='replayed' and len(fresh.calls)==1
    assert act(product,'share','integrated-live-share-2').status=='committed'
    rows=open_integrated_character_audit(options['audit_path']).snapshot()
    assert len(rows)==8 and all(row['status']=='complete' for row in rows)
    assert {row['purpose'] for row in rows}=={'natural-activity-feedback','living-activity-choice','living-activity-share'}
    assert 'SYNTHETIC_REASONING' not in canonical_json(observations)
    assert MESSAGE not in canonical_json(rows)


@pytest.mark.parametrize('fault,status',[('length','failed-closed'),('extra','failed-closed'),('timeout','unknown'),('credential','unavailable')])
def test_first_failure_is_retained_and_original_nonce_never_resends(integrated_live_fixture,fault,status):
    _,_,options,_=integrated_live_fixture
    product,transport,observations=start(integrated_live_fixture)
    original=state(product)['current_plan']; transport.fault=fault
    result=send(product,MESSAGE,'integrated-live-failure-first')
    assert result.status!='terminal' and len(transport.calls)==2
    if status == 'unknown':
        assert product.application.query_living_activity().status == 'failed-closed'
    else:
        assert state(product)['current_plan']==original and not history(product)
    assert open_integrated_character_audit(options['audit_path']).snapshot()[-1]['status']==status
    assert observations[-1]['status']==status
    send(product,MESSAGE,'integrated-live-failure-first')
    assert len(transport.calls)==2


def test_permission_changed_between_claim_and_consume_never_sends(integrated_live_fixture,monkeypatch):
    _,_,options,_=integrated_live_fixture
    product,transport,_=start(integrated_live_fixture)
    original=IntegratedCharacterDelivery.claim
    def changed(self,*args,**kwargs):
        original(self,*args,**kwargs)
        product.application.set_reviewed_character_history(False)
    monkeypatch.setattr(IntegratedCharacterDelivery,'claim',changed)
    assert send(product,MESSAGE,'integrated-live-race-first').status=='failed-closed'
    assert len(transport.calls)==1
    assert open_integrated_character_audit(options['audit_path']).snapshot()[-1]['status']=='failed-closed'


def test_unapproved_grant_and_manual_opportunity_have_no_live_call(integrated_live_fixture):
    with pytest.raises(ValueError): ApprovedIntegratedCharacterGrant(APPROVED_INTEGRATED_REVIEW,False)
    with pytest.raises(ValueError): ApprovedIntegratedCharacterGrant('0'*64,True)
    product,transport,_=start(integrated_live_fixture)
    before=len(transport.calls)
    assert act(product,'manual','integrated-live-manual-denied').status=='unavailable'
    assert len(transport.calls)==before


def test_focused_candidate_keeps_projection_budget_and_independent_exact_identity(integrated_live_fixture):
    from dynamic_subject_agent.integrated_character import integrated_policies
    from dynamic_subject_agent.local_product import validate_integrated_character_entry
    opening,config,options,_=integrated_live_fixture
    options['grant']=ApprovedIntegratedCharacterGrant(APPROVED_INTEGRATED_REVIEW,True,technical_variant='focused')
    product,transport,_=start(integrated_live_fixture)
    assert act(product,'share','integrated-focused-share-1').status=='committed'
    preview=product.application.preview_natural_feedback(MESSAGE)
    assert send(product,MESSAGE,'integrated-focused-feedback').status=='terminal'
    wire=integrated_remote_request_preview(ModelTask(ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK,preview.view),technical_variant='focused')
    assert transport.calls[-1]==wire['body']
    assert wire['body']['max_tokens']==4096 and wire['automatic_retries']==0
    assert set(preview.view['payload'])=={'turn','background','exchange','evidence','current_plan','activity_revision','current_feedback'}
    assert set(preview.view['payload']['evidence'])=={'shared_experience','latest_share'}
    assert preview.view['policy']==integrated_policies(technical_variant='focused')[0]
    validate_integrated_character_entry(config,profile_id=product.profile_id,timeline_id=product.timeline_id,technical_variant='focused')
    with pytest.raises(RuntimeError):
        validate_integrated_character_entry(config,profile_id=product.profile_id,timeline_id=product.timeline_id)
    product.close();calls=len(transport.calls);product=opening(transport)
    assert len(transport.calls)==calls and '杉架' in state(product)['current_plan'].composition
    saved=config.state_path.read_bytes()
    with pytest.raises(RuntimeError,match='activation-conflict'):
        open_integrated_character_product_live(config,identity_id=options['identity_id'],audit_path=options['audit_path'],
            grant=ApprovedIntegratedCharacterGrant(APPROVED_INTEGRATED_REVIEW,True),_transport=transport)
    assert config.state_path.read_bytes()==saved and len(transport.calls)==calls


def test_conversation_text_turns_are_no_effect_and_eligible_edits_remain_strict_json(integrated_live_fixture):
    from dynamic_subject_agent.integrated_character_text import conversation_text_proposal
    opening,_,options,_=integrated_live_fixture
    options['grant']=ApprovedIntegratedCharacterGrant(APPROVED_INTEGRATED_REVIEW,True,technical_variant='conversation-text')
    product,transport,observations=start(integrated_live_fixture)
    original=state(product)['current_plan']
    assert act(product,'share','conversation-mode-share-1').status=='committed'
    preview=product.application.preview_natural_feedback('那一处也改掉。')
    expected=integrated_remote_request_preview(ModelTask(ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK,preview.view),technical_variant='conversation-text')
    assert 'response_format' not in expected['body'] and expected['body']['max_tokens']==4096
    assert send(product,'那一处也改掉。','conversation-mode-ambiguous').status=='terminal'
    assert transport.calls[-1]==expected['body'] and observations[-1]['output_mode']=='plain-text-local-no-effect-wrapper'
    assert state(product)['current_plan']==original
    # Literal punctuation in prose is not parsed or repaired as a state command.
    transport.fault='trailing'
    assert send(product,'说说别的。','conversation-mode-prose-comma').status=='terminal'
    assert history(product)[-1].assistant_text.endswith(',') and state(product)['current_plan']==original
    candidate=product.application.preview_natural_feedback(MESSAGE)
    exact=integrated_remote_request_preview(ModelTask(ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK,candidate.view),technical_variant='conversation-text')
    assert exact['body']['response_format']=={'type':'json_object'}
    with pytest.raises(ValueError,match='eligible edit'):
        conversation_text_proposal('不能当成普通文字。',candidate.view['payload'])
    count=len(transport.calls)
    assert send(product,MESSAGE,'conversation-mode-json-comma').status=='failed-closed'
    assert len(transport.calls)==count+1 and state(product)['current_plan']==original
    assert open_integrated_character_audit(options['audit_path']).snapshot()[-1]['status']=='failed-closed'
    assert observations[-1]['error_code']=='response-content-json'


def test_text_selection_preserves_complete_feedback_source_length_bound():
    from dynamic_subject_agent.integrated_character_text import has_writable_frame, conversation_text_proposal
    payload=dict(turn=dict(current_message=MESSAGE,history_enabled=True),current_plan=PLAN)
    assert has_writable_frame(payload)
    payload['turn']['current_message']=' '*(401-len(MESSAGE))+MESSAGE
    assert len(payload['turn']['current_message'])==401 and not has_writable_frame(payload)
    assert conversation_text_proposal('这一轮先保留方案。',payload)==dict(intent='chat',reply_text='这一轮先保留方案。')


def test_strict_intent_text_live_preserves_model_choice_and_exact_frame(integrated_live_fixture):
    opening,_,options,_=integrated_live_fixture
    options['grant']=ApprovedIntegratedCharacterGrant(APPROVED_INTEGRATED_REVIEW,True,technical_variant='intent-text')
    product,transport,observations=start(integrated_live_fixture)
    original=state(product)['current_plan']
    transport.synthetic.override=dict(intent='chat',reply_text='我这次想保留原名。')
    assert send(product,MESSAGE,'intent-text-refusal-1').status=='terminal'
    assert state(product)['current_plan']==original
    transport.synthetic.override=None
    preview=product.application.preview_natural_feedback(MESSAGE)
    expected=integrated_remote_request_preview(ModelTask(ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK,preview.view),technical_variant='intent-text')
    assert expected['output_contract']['final_content']=='intent-prefixed-text' and 'response_format' not in expected['body']
    assert send(product,MESSAGE,'intent-text-accepted-1').status=='terminal'
    assert transport.calls[-1]==expected['body'] and observations[-1]['output_mode']=='strict-intent-text'
    assert asdict(state(product)['current_plan'])=={k:v.replace('松架','杉架') for k,v in asdict(original).items()}
    assert history(product)[-1].assistant_text=='合成修订回复。'
    assert len(open_integrated_character_audit(options['audit_path']).snapshot())==3


@pytest.mark.parametrize('text',['收到，已经改了。','[revise],\n收到。','[revise]\n[chat]\n收到。','{"intent":"revise","reply_text":"收到。"},','[revise]\n'])
def test_intent_decoder_is_strict_and_never_repairs_old_json(text):
    from dynamic_subject_agent.integrated_character_text import intent_text_proposal
    payload=dict(turn=dict(current_message=MESSAGE,history_enabled=True),current_plan=PLAN,activity_revision=1)
    with pytest.raises(ValueError): intent_text_proposal(text,payload)


@pytest.mark.parametrize('prepared',[False,True])
def test_live_feedback_cold_recovery_does_not_call_provider(integrated_live_fixture,monkeypatch,prepared):
    from dynamic_subject_agent.timeline import TimelineEngine,FaultPoint,PublicationInterrupted
    opening,_,options,_=integrated_live_fixture
    product,transport,_=start(integrated_live_fixture)
    with monkeypatch.context() as crash:
        if prepared:
            original=TimelineEngine._hit
            def hit(self,point):
                if point is FaultPoint.AFTER_PLAN_CLAIM: raise OSError('Synthetic integrated interruption')
                return original(self,point)
            crash.setattr(TimelineEngine,'_hit',hit)
        else:
            crash.setattr(TimelineEngine,'publish',lambda *a,**kw:(_ for _ in ()).throw(PublicationInterrupted('synthetic','before preparation')))
        send(product,MESSAGE,'integrated-live-interrupted')
    assert len(transport.calls)==2
    product.close();fresh=IntegratedTransport();product=opening(fresh)
    assert not fresh.calls
    assert product.application.query_shared_activity().view['activity_revision']==(2 if prepared else 1)
    assert send(product,MESSAGE,'integrated-live-interrupted').status==('terminal' if prepared else 'failed-closed')
    assert not fresh.calls and len(open_integrated_character_audit(options['audit_path']).snapshot())==2
