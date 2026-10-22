"""Approved M012 three purposes through one real development Facade."""
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from dynamic_subject_agent.local_product import LocalProductConfig,open_local_product,open_memorie_activity_development_product
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
from dynamic_subject_agent.memorie_companion_contract import DEFINITION
from dynamic_subject_agent.memorie_activity_live import ApprovedNativeActivityGrant,open_audit
from dynamic_subject_agent.living_activity import LivingActionRequest,LivingControlRequest
from dynamic_subject_agent.shared_activity import SharedExperienceRequest
from dynamic_subject_agent.application import ApplicationQuery,ApplicationQueryKind
from dynamic_subject_agent.deepseek import DeepSeekTransport,DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json
from test_original_whole_chat import send,history


class Transport(DeepSeekTransport):
    def __init__(self):self.calls=[];self.callback=None;self.fault=None
    def post_json(self,**kwargs):
        body=json.loads(kwargs['body']);self.calls.append(body)
        if self.callback:self.callback()
        if self.fault=='timeout':raise TimeoutError('synthetic ambiguous send')
        p=json.loads(body['messages'][1]['content'])
        if 'current_activity' in p:
            action=p['current_activity']['allowed_actions'][0]
            value=dict(action=action,plan=dict(subject='药草笔记文字方案',composition='外观与待核问题分栏'+str(len(self.calls)),focus='只列待核问题')
                if action in ('start','revise') else None,reason_code='improve-readability',basis_refs=['E1'] if p['experience'] else [],decision_note='区分观察和待核问题。')
            content=canonical_json(value)
        elif 'interaction' in p:content='合成回应，只承接这次给出的依据。'
        else:content=canonical_json(dict(share=True,reply_text='我把这份文字方案分成外观和待核问题两栏了。',language='zh'))
        return DeepSeekHttpResponse(200,canonical_json(dict(model='deepseek-flash',choices=[dict(finish_reason='stop',message=dict(role='assistant',content=content))],usage=dict(prompt_tokens=100,completion_tokens=40))).encode())


@pytest.fixture
def development(tmp_path,monkeypatch):
    private=Path(os.environ.get('MEMORIE_NATIVE_QUALIFICATION','missing'))
    approval=private/'native-activity-approval.json'
    if not approval.is_file():pytest.skip('Exact approved M012 receipt required')
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'account-control'))
    prepared=json.loads((private/'preparation.json').read_bytes())
    config=LocalProductConfig(tmp_path/'dev/DynamicSubjectAgent/m0/experiments',tmp_path/'dev/state.json')
    with open_local_product(config,cognition=DormantDeepSeekCognition()) as author:
        frozen=author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(prepared['definition_json'],DEFINITION,True,True))
        assert frozen.status=='created'
    opened=[]
    def opening(transport=None):
        p=open_memorie_activity_development_product(config,identity_id=frozen.view.identity_id,approval_path=approval,_transport=transport or Transport())
        opened.append(p);return p
    opening.approval=approval;opening.config=config
    yield opening
    for p in opened:p.close()


def state(p):
    value=p.application.query_living_activity();assert value.status=='available',value
    return value.view


def control(p,*,paused=False,sharing=True,key='m015-control-enable-1'):
    return p.application.set_living_controls(LivingControlRequest(p.profile_id,p.timeline_id,key,state(p)['permission']['revision'],paused,sharing,True))


def act(p,key='m015-first-choice-1',kind='simulation'):
    return p.application.advance_living_activity(LivingActionRequest(p.profile_id,p.timeline_id,key,state(p)['revision'],kind))


def test_selected_experience_choice_share_and_reply_are_same_canonical_timeline(development):
    model=Transport();p=development(model)
    assert not model.calls and state(p)['permission']['paused']
    first=send(p,'合成明确原话：先列待核问题。','m015-source-1')
    assert first.status=='terminal' and first.projection.failure_code is None,first
    s=p.application.query_shared_activity().view
    selected=p.application.set_shared_experience(SharedExperienceRequest(p.profile_id,p.timeline_id,'m015-source-selection-1',s['revision'],1,'先列待核问题',True))
    assert selected.status=='committed',selected
    before=p.application.preview_living_activity('reply','接着说。')
    assert before.status=='previewed',before
    assert before.view['payload']['experience']==dict(label='E1',quote='先列待核问题')
    assert control(p).status=='committed'
    preview=p.application.preview_living_activity('choice')
    result=act(p);assert result.status=='committed',result
    assert json.loads(model.calls[-1]['messages'][1]['content'])==json.loads(canonical_json(preview.view['payload']))
    assert act(p,'m015-committed-share-1','share').status=='committed'
    assert send(p,'说说这份编排。','m015-followup-1').status=='terminal'
    payload=json.loads(model.calls[-1]['messages'][1]['content'])
    assert payload['latest_share']['text']==state(p)['shares'][-1]['text']
    assert len(model.calls)==4 and all('background' not in json.loads(c['messages'][1]['content']) for c in model.calls)
    saved=history(p);scope=p.profile_id,p.timeline_id;p.close();fresh=Transport();p=development(fresh)
    assert (p.profile_id,p.timeline_id)==scope and history(p)==saved and not fresh.calls
    assert len(state(p)['shares'])==1


def test_global_audit_counts_failed_attempts_across_data_roots(development):
    grant=ApprovedNativeActivityGrant(development.approval);audit=open_audit(grant)
    for i in range(4):
        op=sha256(str(i).encode()).hexdigest()
        audit.claim_daily(op,'a'*64,purpose='choice',day='2026-10-22',run='b'*64)
        audit.record(op,status='unknown')
    other=open_audit(grant)
    assert other.path==audit.path and other.count('choice','2026-10-22')==4
    with pytest.raises(ValueError):other.claim_daily('c'*64,'d'*64,purpose='choice',day='2026-10-22',run='e'*64)


def test_m012_grant_does_not_include_upgrade_or_install(development,tmp_path):
    value=json.loads(development.approval.read_bytes());value['data_upgrade_included']=True
    bad=tmp_path/'bad.json';bad.write_text(canonical_json(value),encoding='utf-8')
    with pytest.raises(ValueError):ApprovedNativeActivityGrant(bad).validate()


def test_disabled_source_filters_plan_share_and_dialogue_after_reopen(development):
    model=Transport();p=development(model)
    assert send(p,'合成原话：待核问题另列。','m016-source').projection.failure_code is None
    s=p.application.query_shared_activity().view
    assert p.application.set_shared_experience(SharedExperienceRequest(p.profile_id,p.timeline_id,'m016-source-select-1',s['revision'],1,'待核问题另列',True)).status=='committed'
    assert control(p).status=='committed';assert act(p).status=='committed'
    assert act(p,'m016-share-source-1','share').status=='committed'
    assert send(p,'接着说这个方案。','m016-derived').projection.failure_code is None
    s=p.application.query_shared_activity().view
    assert p.application.set_shared_experience(SharedExperienceRequest(p.profile_id,p.timeline_id,'m016-disable-source-1',s['revision'],None,'',True)).status=='committed'
    p.close();fresh=Transport();p=development(fresh)
    assert not fresh.calls
    assert send(p,'现在聊新话题。','m016-after-disable').projection.failure_code is None
    payload=json.loads(fresh.calls[-1]['messages'][1]['content'])
    assert payload['experience'] is None and payload['activity_result'] is None and payload['latest_share'] is None and payload['exchange']==[]


def test_prepared_choice_recovers_without_a_second_model_request(development,monkeypatch):
    from dynamic_subject_agent.timeline import TimelineEngine,FaultPoint
    p=development();assert control(p).status=='committed'
    request=LivingActionRequest(p.profile_id,p.timeline_id,'m017-prepared-choice-1',state(p)['revision'],'simulation')
    original=TimelineEngine._hit
    def hit(self,point):
        if point is FaultPoint.AFTER_PLAN_CLAIM:raise OSError('synthetic durable preparation interruption')
        return original(self,point)
    with monkeypatch.context() as interrupted:
        interrupted.setattr(TimelineEngine,'_hit',hit)
        p.application.advance_living_activity(request)
    p.close();fresh=Transport();p=development(fresh)
    assert not fresh.calls and p.application.query_shared_activity().view['activity_revision']==1
    assert p.application.advance_living_activity(request).status=='replayed' and not fresh.calls


def test_choice_daily_limit_is_noop_without_another_request(development):
    model=Transport();p=development(model);assert control(p).status=='committed'
    for i in range(4):assert act(p,'m017-capped-choice-'+str(i)).status=='committed'
    before=state(p)['revision']
    value=act(p,'m017-capped-choice-5')
    assert value.status=='no-op' and value.problem_code=='native-choice-daily-limit'
    assert len(model.calls)==4 and state(p)['revision']==before


def test_source_change_before_delivery_never_reaches_transport(development,monkeypatch):
    from dynamic_subject_agent.memorie_activity_live import NativeActivityDelivery
    model=Transport();p=development(model);assert control(p).status=='committed'
    original=NativeActivityDelivery.consume
    def consume(self,task):
        assert p.application.set_reviewed_character_history(False).history_enabled is False
        return original(self,task)
    monkeypatch.setattr(NativeActivityDelivery,'consume',consume)
    value=act(p,'m017-source-fence-choice-1')
    assert value.status=='failed-closed' and not model.calls
    unverified=p.application.query_living_activity()
    assert unverified.status=='failed-closed' and unverified.view is None
    assert p.application.query_living_controls().view['needs_attention'] is True


def test_dynamic_endpoint_or_slot_change_cannot_borrow_approval(development,monkeypatch):
    from dynamic_subject_agent import deepseek,credentials
    grant=ApprovedNativeActivityGrant(development.approval)
    with monkeypatch.context() as changed:
        changed.setattr(deepseek,'DEEPSEEK_ENDPOINT','https://wrong.invalid')
        with pytest.raises(ValueError):grant.validate()
    with monkeypatch.context() as changed:
        changed.setattr(credentials,'DEEPSEEK_CREDENTIAL_SLOT',replace(credentials.DEEPSEEK_CREDENTIAL_SLOT,account_id='other'))
        with pytest.raises(ValueError):grant.validate()


def test_development_schema6_does_not_fake_or_admit_a_native_click(development):
    from dynamic_subject_agent.memorie_native import NativeInteractionInput
    model=Transport();p=development(model)
    request=NativeInteractionInput(p.profile_id,p.timeline_id,canonical_json({'kind':'character-click'}),canonical_json({'timer_phase':'idle'}))
    value=p.application.submit(request,idempotency_key='m017-no-fake-native-click-1')
    assert value.status=='unavailable' and not model.calls and not history(p)
