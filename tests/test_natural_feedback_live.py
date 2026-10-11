"""Exact approved LIVE composition with synthetic transport, no remote model."""
import json
from copy import deepcopy
from dataclasses import asdict
import pytest

from test_original_whole_chat import approved, personality_fixture, model_fixture, send, history
from test_shared_activity import step_request, select
from test_natural_feedback import PLAN, FEEDBACK, LocalAdapter
from dynamic_subject_agent.local_product import open_natural_feedback_product_live, open_natural_feedback_product_local
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind, ModelGateway
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.natural_feedback import feedback_contract
from dynamic_subject_agent.natural_feedback_live import (
    ApprovedNaturalFeedbackGrant, APPROVED_FEEDBACK_REVIEW, NaturalFeedbackDelivery, open_natural_feedback_audit)
from dynamic_subject_agent.natural_feedback_remote_preview import PendingNaturalFeedbackGrant, natural_feedback_remote_request_preview


class FeedbackTransport(DeepSeekTransport):
    def __init__(self, fault=None):self.calls=[];self.fault=fault
    def post_json(self, **kwargs):
        body=json.loads(kwargs['body']);self.calls.append(body)
        if self.fault=='timeout':raise TimeoutError('synthetic delivery unknown')
        if self.fault=='credential':
            from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
            raise CharacterCredentialUnavailable()
        payload=json.loads(body['messages'][1]['content'])
        if 'current_activity' in payload:
            current=payload['current_plan'];action=payload['current_activity']['allowed_actions'][0]
            value=dict(action=action,plan=PLAN if current is None else dict(current,focus='表情与明暗的清晰关系'),
                reason_code='improve-readability',basis_refs=['E1'] if payload['shared_experience'] else [],decision_note='合成已审批活动选择。')
        else:
            message=payload['turn']['current_message'];intent='revise' if message==FEEDBACK else 'clarify' if message=='暖一点。' else 'chat'
            edits=[dict(field='composition',before='冷色主光',after='暖色主光'),
                dict(field='composition',before='背景压暗。',after='背景压暗。冷色只留低亮边缘反光。')] if intent=='revise' else []
            value=dict(intent=intent,activity_revision=payload['activity_revision'],edits=edits,
                reason_code='improve-readability' if edits else None,reply_text='合成已审批路径正文。',language='zh')
            if self.fault=='wrong-revision':value['activity_revision']+=1
            if self.fault=='bad-patch':value['edits']=[dict(field='composition',before='不存在的片段',after='不能发表')];value['intent']='revise';value['reason_code']='improve-readability'
        content=' ' if self.fault=='blank' else canonical_json(value)
        return DeepSeekHttpResponse(200,canonical_json(dict(model='deepseek-flash',choices=[dict(finish_reason='stop',
            message=dict(role='assistant',content=content,reasoning_content='SYNTHETIC_REASONING_MUST_NOT_RETAIN'))],
            usage=dict(prompt_tokens=100,completion_tokens=20,total_tokens=120))).encode())


@pytest.fixture
def feedback_live_fixture(approved,monkeypatch,tmp_path):
    author,config,request,view=approved
    frozen=author.application.freeze_source_identity(request);assert frozen.status=='created';author.close()
    asset=json.loads(view.runtime_asset_json)
    import dynamic_subject_agent.original_whole_chat as module
    binding=dict(definition_basis=view.definition_basis,runtime_asset_sha=view.runtime_asset_sha,persona_digest=asset['persona_digest'],
        review_basis='1'*64,scope_digest='2'*64,subject_id=asset['subject']['subject_id'],anchor_id=asset['anchor']['anchor_id'])
    monkeypatch.setattr(module,'APPROVED_BINDING',binding)
    import dynamic_subject_agent.natural_feedback_live as live
    # Only the synthetic local test binding is substituted; human production
    # policy/protocol pins and grant confirmation stay exact.
    monkeypatch.setattr(live,'APPROVED_FEEDBACK_MATERIAL',live.digest(binding))
    monkeypatch.setattr(live,'APPROVED_FEEDBACK_LOCAL_CONTRACT',live.digest(feedback_contract(binding)))
    options=dict(identity_id=frozen.view.identity_id,grant=ApprovedNaturalFeedbackGrant(APPROVED_FEEDBACK_REVIEW,True),audit_path=tmp_path/'feedback-live-audit')
    opened=[]
    def opening(transport=None,observations=None):
        result=open_natural_feedback_product_live(config,**options,_transport=transport or FeedbackTransport(),observations=observations)
        opened.append(result);return result
    yield opening,config,options,binding
    for product in opened:product.close()


def state(product):
    r=product.application.query_shared_activity();assert r.status=='available',r
    return r.view


def test_live_wire_canonical_patch_over_window_reopen_next_activity_and_metadata(feedback_live_fixture):
    opening,_,options,_=feedback_live_fixture
    transport=FeedbackTransport();observations=[];product=opening(transport,observations)
    assert not transport.calls and not open_natural_feedback_audit(options['audit_path']).snapshot()
    assert product.application.advance_shared_activity(step_request(product,'live-feedback-initial')).status=='committed'
    preview=product.application.preview_natural_feedback(FEEDBACK);assert preview.status=='previewed',preview
    assert send(product,FEEDBACK,'live-feedback-natural').status=='terminal'
    expected=natural_feedback_remote_request_preview(ModelTask(ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK,preview.view))
    assert transport.calls[-1]==expected['body'] and observations[-1]['wire_sha256']==expected['wire_sha256']
    plan=state(product)['current_plan'];assert '暖色主光' in plan.composition
    for i in range(3):assert send(product,'合成无关话题'+str(i),'live-feedback-gap-'+str(i)).status=='terminal'
    assert FEEDBACK not in canonical_json(product.application.preview_natural_feedback('继续。').view['payload']['exchange'])
    saved=history(product);identity=(product.profile_id,product.timeline_id);product.close()
    fresh=FeedbackTransport();product=opening(fresh)
    assert not fresh.calls and history(product)==saved and identity==(product.profile_id,product.timeline_id)
    assert product.application.preview_shared_activity_step().view['payload']['current_feedback']['quote']==FEEDBACK
    req=step_request(product,'live-feedback-after-gap')
    assert product.application.advance_shared_activity(req).status=='committed'
    assert product.application.advance_shared_activity(req).status=='replayed' and len(fresh.calls)==1
    assert state(product)['activity_revision']==3 and state(product)['current_plan'].composition==plan.composition
    assert send(product,'说说当前方案。','live-feedback-current-result').status=='terminal'
    assert json.loads(fresh.calls[-1]['messages'][1]['content'])['current_plan']==asdict(state(product)['current_plan'])
    rows=open_natural_feedback_audit(options['audit_path']).snapshot()
    assert len(rows)==7 and all(r['status']=='complete' for r in rows)
    assert {r['purpose'] for r in rows}=={'natural-activity-feedback','shared-activity-choice'}
    assert FEEDBACK not in canonical_json(rows) and 'SYNTHETIC_REASONING' not in canonical_json(observations)


def test_pending_and_existing_local_root_cannot_convert_to_live(feedback_live_fixture):
    _,config,options,binding=feedback_live_fixture;transport=FeedbackTransport()
    with pytest.raises(ValueError):
        open_natural_feedback_product_live(None,**dict(options,grant=PendingNaturalFeedbackGrant(APPROVED_FEEDBACK_REVIEW)),_transport=transport)
    assert not options['audit_path'].exists() and not transport.calls
    product=open_natural_feedback_product_local(config,gateway=ModelGateway(LocalAdapter()),identity_id=options['identity_id'],binding=binding);product.close()
    before=config.state_path.read_bytes()
    with pytest.raises(RuntimeError):open_natural_feedback_product_live(config,**options,_transport=transport)
    assert config.state_path.read_bytes()==before and not options['audit_path'].exists() and not transport.calls


@pytest.mark.parametrize('when',['before-claim','after-claim'])
def test_mutated_projection_is_discarded_before_transport(feedback_live_fixture,monkeypatch,when):
    opening,_,options,_=feedback_live_fixture;transport=FeedbackTransport();product=opening(transport)
    original=NaturalFeedbackDelivery.claim
    def claim(self,operation,task,rebuild):
        changed=deepcopy(task.payload);changed['payload']['background']['runtime_identity']['subject_name']='WRONG_SYNTHETIC_SCOPE'
        if when=='before-claim':return original(self,operation,ModelTask(task.kind,changed),rebuild)
        original(self,operation,task,rebuild)
        task.payload['payload']['background']['runtime_identity']['subject_name']='WRONG_SYNTHETIC_SCOPE'
    monkeypatch.setattr(NaturalFeedbackDelivery,'claim',claim)
    assert send(product,'普通合成消息。','live-feedback-mutated').status=='failed-closed'
    assert not transport.calls and not history(product)
    rows=open_natural_feedback_audit(options['audit_path']).snapshot()
    assert len(rows)==(0 if when=='before-claim' else 1)


@pytest.mark.parametrize('fault,status',[('credential','unavailable'),('timeout','unknown'),('blank','failed-closed'),
    ('wrong-revision','failed-closed'),('bad-patch','failed-closed')])
def test_first_transport_or_content_failure_is_typed_uncommitted_and_not_retried(feedback_live_fixture,fault,status):
    opening,_,options,_=feedback_live_fixture;transport=FeedbackTransport(fault);product=opening(transport)
    result=send(product,'这是一条普通消息。','live-feedback-failure')
    assert result.status==status,result
    assert len(transport.calls)==1 and not history(product)
    if status=='unknown':
        # Unknown delivery deliberately prevents a fresh activity projection.
        assert product.application.query_shared_activity().status=='failed-closed'
    else:assert state(product)['activity_revision']==0
    assert send(product,'这是一条普通消息。','live-feedback-failure').status==status and len(transport.calls)==1
    rows=open_natural_feedback_audit(options['audit_path']).snapshot();assert len(rows)==1 and rows[0]['status']!= 'complete'


@pytest.mark.parametrize('prepared',[False,True])
def test_cold_recovery_never_resends_and_feedback_publication_is_atomic(feedback_live_fixture,monkeypatch,prepared):
    from dynamic_subject_agent.timeline import TimelineEngine,FaultPoint,PublicationInterrupted
    opening,_,options,_=feedback_live_fixture;transport=FeedbackTransport();product=opening(transport)
    assert product.application.advance_shared_activity(step_request(product,'live-feedback-recovery-baseline')).status=='committed'
    with monkeypatch.context() as crash:
        if prepared:
            original=TimelineEngine._hit
            def hit(self,point):
                if point is FaultPoint.AFTER_PLAN_CLAIM:raise OSError('Synthetic prepared interruption')
                return original(self,point)
            crash.setattr(TimelineEngine,'_hit',hit)
        else:crash.setattr(TimelineEngine,'publish',lambda *a,**kw: (_ for _ in ()).throw(PublicationInterrupted('synthetic','Before preparation')))
        send(product,FEEDBACK,'live-feedback-recovery')
    assert len(transport.calls)==2
    product.close();fresh=FeedbackTransport();product=opening(fresh)
    assert not fresh.calls and state(product)['activity_revision']==(2 if prepared else 1)
    assert send(product,FEEDBACK,'live-feedback-recovery').status==('terminal' if prepared else 'failed-closed') and not fresh.calls


def test_material_or_protocol_change_cannot_use_original_approval(feedback_live_fixture,monkeypatch):
    _,config,options,_=feedback_live_fixture;transport=FeedbackTransport()
    import dynamic_subject_agent.original_whole_chat as module
    monkeypatch.setattr(module,'APPROVED_BINDING',dict(module.APPROVED_BINDING,runtime_asset_sha='f'*64))
    with pytest.raises(ValueError,match='changed material'):open_natural_feedback_product_live(config,**options,_transport=transport)
    assert not options['audit_path'].exists() and not transport.calls
