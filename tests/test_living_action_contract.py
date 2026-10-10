"""S149 exact candidate Interface, old wire compatibility and phase contracts."""
from copy import deepcopy
from dataclasses import asdict
import json

import pytest

from test_original_whole_chat import approved,personality_fixture,model_fixture,send,history
from test_living_activity import state,control,act,action_request
from test_living_activity_live import living_live_fixture
from test_living_final_text import final_text_fixture,FinalTextTransport,RAW
from dynamic_subject_agent.local_product import open_living_activity_product_live,validate_living_activity_entry
from dynamic_subject_agent.living_action_contract import LivingActionContractDevelopmentGrant,ACTION_DEVELOPMENT_AUTHORIZATION,living_action_contract
from dynamic_subject_agent.living_activity_live import APPROVED_LIVING_REVIEW,open_living_activity_audit,living_final_text_contract
from dynamic_subject_agent.living_activity import living_policies
from dynamic_subject_agent.living_activity_remote_preview import living_remote_request_preview
from dynamic_subject_agent.model_gateway import ModelTask,ModelTaskKind
from dynamic_subject_agent.shared_activity import SharedExperienceRequest


class ActionTransport(FinalTextTransport):
    def __init__(self,invalid_rework=False):
        super().__init__();self.invalid_rework=invalid_rework

    def post_json(self,**kwargs):
        payload=json.loads(json.loads(kwargs['body'])['messages'][1]['content'])
        if 'current_activity' in payload and payload['current_activity']['phase']=='revised':
            self.override=dict(action='rework',plan=dict(subject='合成主体',composition='非法阶段新方案',focus='光线') if self.invalid_rework else None,
                reason_code='try-alternative',basis_refs=['E1'] if payload['shared_experience'] else [],decision_note='合成进入返工，不是新方案。')
        else:self.override=None
        return super().post_json(**kwargs)


@pytest.fixture
def action_fixture(final_text_fixture):
    _,config,options,_=final_text_fixture
    options=dict(options,grant=LivingActionContractDevelopmentGrant(APPROVED_LIVING_REVIEW,ACTION_DEVELOPMENT_AUTHORIZATION),
        audit_path=options['audit_path'].with_name('s149-action-audit'))
    products=[]
    def opening(transport=None):
        product=open_living_activity_product_live(config,**options,_transport=transport or ActionTransport())
        products.append(product);return product
    yield opening,config,options
    for product in products:product.close()


def select_last(product,text,key):
    row=history(product)[-1]
    req=SharedExperienceRequest(product.profile_id,product.timeline_id,key,state(product)['revision'],row.head_sequence,text,True)
    assert product.application.set_shared_experience(req).status=='committed'


def prepare_correction(product):
    assert control(product,paused=False,sharing=True,key='s149-initial-controls').status=='committed'
    assert act(product,key='s149-independent-start').status=='committed'
    assert send(product,'这版先考虑单一冷光。','s149-initial-source-chat').status=='terminal'
    select_last(product,'单一冷光','s149-initial-source-select')
    assert act(product,key='s149-first-source-revision').status=='committed'
    assert act(product,'share',key='s149-first-source-share').status=='committed'
    assert send(product,'更正：这版改成暖主光，冷色仅作低亮边缘反光。','s149-corrected-source-chat').status=='terminal'
    select_last(product,'暖主光，冷色仅作低亮边缘反光','s149-corrected-source-select')
    assert state(product)['phase']=='revised' and state(product)['current_plan'] is None and state(product)['latest_share'] is None


def test_candidate_rework_null_then_cold_reopen_revision_real_plan_version_and_exact_three_wires(action_fixture):
    opening,config,options=action_fixture
    transport=ActionTransport();product=opening(transport)
    validate_living_activity_entry(config,profile_id=product.profile_id,timeline_id=product.timeline_id,technical_variant='action-contract')
    assert not transport.calls
    prepare_correction(product)
    before=product.application.query_shared_activity().view
    step=action_request(product,key='s149-enter-rework-once')
    preview=product.application.preview_living_activity('choice').view
    assert tuple(preview['payload']['current_activity']['allowed_actions'])==('keep','rework','defer')
    assert product.application.advance_living_activity(step).status=='committed'
    current=product.application.query_shared_activity().view
    assert current['activity_revision']==before['activity_revision'] and state(product)['phase']=='rework'
    assert not current['result'].differences
    sent=len(transport.calls)
    assert product.application.query_living_activity(step).status=='replayed' and len(transport.calls)==sent
    saved=deepcopy(state(product));product.close();fresh=ActionTransport();product=opening(fresh)
    assert state(product)==saved and not fresh.calls
    assert act(product,key='s149-corrected-new-revision').status=='committed'
    assert product.application.query_shared_activity().view['activity_revision']==before['activity_revision']+1
    for purpose,kind in [('choice',ModelTaskKind.LIVING_ACTIVITY_CHOICE),('share',ModelTaskKind.LIVING_ACTIVITY_SHARE),('reply',ModelTaskKind.LIVING_ACTIVITY_REPLY)]:
        # Share preview requires an actual new eligible result; no extra sends.
        actual=product.application.preview_living_activity(purpose,'当前问题。' if purpose=='reply' else '').view
        candidate=living_remote_request_preview(ModelTask(kind,actual),technical_variant='action-contract')
        old=dict(actual,policy=living_policies('final-text')[('choice','share','reply').index(purpose)])
        baseline=living_remote_request_preview(ModelTask(kind,old),technical_variant='final-text')
        if purpose=='choice':
            assert candidate['body']['messages'][0]!=baseline['body']['messages'][0]
        else:assert candidate['body']==baseline['body']
        assert dict(candidate['body'],messages=candidate['body']['messages'][1:])==dict(baseline['body'],messages=baseline['body']['messages'][1:])
    assert send(product,'这一版的光源是什么？','s149-current-result-reply').status=='terminal'
    assert history(product)[-1].assistant_text==RAW
    rows=open_living_activity_audit(options['audit_path'],technical_variant='action-contract').snapshot()
    assert len(rows)==8 and {x['status'] for x in rows}=={'complete'}


def test_invalid_rework_plan_still_failed_closed_no_publication_or_retry(action_fixture):
    opening,_,options=action_fixture
    transport=ActionTransport(invalid_rework=True);product=opening(transport);prepare_correction(product)
    before=deepcopy(state(product));sent=len(transport.calls)
    result=act(product,key='s149-invalid-rework-plan')
    assert result.status=='failed-closed' and result.problem_code=='original-whole-structured-choice-invalid'
    assert len(transport.calls)==sent+1
    assert state(product)['revision']==before['revision'] and state(product)['current_plan'] is None
    assert open_living_activity_audit(options['audit_path'],technical_variant='action-contract').snapshot()[-1]['status']=='failed-closed'


def test_candidate_old_grant_audit_or_entry_variant_cannot_replace_qualification(action_fixture):
    opening,config,options=action_fixture
    product=opening()
    with pytest.raises(RuntimeError,match='identity-unverified'):
        validate_living_activity_entry(config,profile_id=product.profile_id,timeline_id=product.timeline_id,technical_variant='final-text')
    product.close()
    from dynamic_subject_agent.living_activity_live import LivingFinalTextDevelopmentGrant,FINAL_TEXT_DEVELOPMENT_AUTHORIZATION
    old=LivingFinalTextDevelopmentGrant(APPROVED_LIVING_REVIEW,FINAL_TEXT_DEVELOPMENT_AUTHORIZATION)
    with pytest.raises(RuntimeError,match='conflict'):
        open_living_activity_product_live(config,identity_id=options['identity_id'],grant=old,audit_path=options['audit_path'],_transport=ActionTransport())
    with pytest.raises(ValueError):open_living_activity_audit(options['audit_path'],technical_variant='final-text')
