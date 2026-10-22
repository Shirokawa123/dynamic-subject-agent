"""Schema12 native interactions and bounded activities on one real Facade."""
import json
import os
from pathlib import Path

import pytest

from dynamic_subject_agent.local_product import LocalProductConfig,open_local_product,open_memorie_native_activity_product
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
from dynamic_subject_agent.memorie_companion_contract import DEFINITION
from dynamic_subject_agent.memorie_native import NativeInteractionInput
from dynamic_subject_agent.shared_activity import SharedExperienceRequest
from dynamic_subject_agent.application import SubjectRequestLookupRequest
from dynamic_subject_agent.frozen_attempt import canonical_json
from test_memorie_activity_live import Transport,state,control,act


@pytest.fixture
def native_activity(tmp_path,monkeypatch):
    private=Path(os.environ.get('MEMORIE_NATIVE_QUALIFICATION','missing'))
    approval=private/'native-activity-approval.json'
    if not approval.is_file():pytest.skip('Exact M012 human receipt required')
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'account-control'))
    config=LocalProductConfig(tmp_path/'dev/DynamicSubjectAgent/m0/experiments',tmp_path/'dev/state.json')
    prepared=json.loads((private/'preparation.json').read_bytes())
    with open_local_product(config,cognition=DormantDeepSeekCognition()) as p:
        frozen=p.application.freeze_source_identity(ReviewedCharacterFreezeRequest(prepared['definition_json'],DEFINITION,True,True))
        assert frozen.status=='created'
    opened=[]
    def opening(model=None,*,clock=None,live_transport=False):
        p=open_memorie_native_activity_product(config,identity_id=frozen.view.identity_id,approval_path=approval,_transport=None if live_transport else model or Transport(),clock=clock)
        opened.append(p);return p
    opening.config=config
    yield opening
    for p in opened:p.close()


def send_native(p,key,text=None,phase='idle'):
    command=NativeInteractionInput(p.profile_id,p.timeline_id,canonical_json(dict(kind='character-click') if text is None else dict(kind='text',text=text)),
        canonical_json(dict(timer_phase=phase)))
    value=p.application.submit(command,idempotency_key=key)
    if value.status=='pending':value=p.application.wait(value.operation_ref,timeout_seconds=30)
    assert value.status=='terminal' and value.projection.failure_code is None,value
    return command,value


def test_native_text_source_outline_share_and_click_reopen_one_timeline(native_activity):
    model=Transport();p=native_activity(model)
    first,_=send_native(p,'m018-first-character-click-1')
    _,text=send_native(p,'m018-first-explicit-text-1','合成原话：把待核问题另列。')
    shared=p.application.query_shared_activity().view
    selected=p.application.set_shared_experience(SharedExperienceRequest(p.profile_id,p.timeline_id,'m019-confirm-user-quote-1',shared['revision'],2,'把待核问题另列',True))
    assert selected.status=='committed',selected
    assert control(p).status=='committed'
    assert act(p,'m020-native-choice-1').status=='committed'
    assert act(p,'m020-native-share-1','share').status=='committed'
    send_native(p,'m020-followup-character-click-1',phase='rest')
    payload=json.loads(model.calls[-1]['messages'][1]['content'])
    assert payload['interaction']==dict(kind='character-click') and payload['situation']==dict(timer_phase='rest')
    assert payload['experience']['quote']=='把待核问题另列' and payload['activity_result'] is not None and payload['latest_share'] is not None
    assert payload['exchange'][0]['interaction']==dict(kind='character-click')
    assert len(model.calls)==5
    saved=p.application.query_memorie_interactions();scope=p.profile_id,p.timeline_id;p.close()
    fresh=Transport();p=native_activity(fresh)
    assert (p.profile_id,p.timeline_id)==scope and not fresh.calls
    assert p.application.query_memorie_interactions()==saved and len(saved.turns)==3
    lookup=p.application.lookup_subject_request(SubjectRequestLookupRequest(first,'m018-first-character-click-1'))
    assert lookup.query_status=='found' and lookup.operation.status=='terminal' and not fresh.calls


def test_native_source_disable_filters_derived_clicks_plans_and_shares_after_reopen(native_activity):
    model=Transport();p=native_activity(model)
    send_native(p,'m019-source-text-original-1','合成原话：待核问题另列。')
    view=p.application.query_shared_activity().view
    assert p.application.set_shared_experience(SharedExperienceRequest(p.profile_id,p.timeline_id,'m019-source-select-original-1',view['revision'],1,'待核问题另列',True)).status=='committed'
    assert control(p).status=='committed';assert act(p,'m019-source-outline-1').status=='committed'
    assert act(p,'m019-source-outline-share-1','share').status=='committed'
    send_native(p,'m019-dependent-native-click-1')
    view=p.application.query_shared_activity().view
    assert p.application.set_shared_experience(SharedExperienceRequest(p.profile_id,p.timeline_id,'m019-source-disable-final-1',view['revision'],None,'',True)).status=='committed'
    p.close();fresh=Transport();p=native_activity(fresh)
    assert not fresh.calls
    send_native(p,'m019-after-disable-new-click-1')
    payload=json.loads(fresh.calls[-1]['messages'][1]['content'])
    assert payload['experience'] is None and payload['activity_result'] is None and payload['latest_share'] is None and payload['exchange']==[]


def test_click_and_assistant_text_cannot_be_confirmed_as_user_source(native_activity):
    model=Transport();p=native_activity(model)
    send_native(p,'m019-source-must-be-user-click-1')
    before=p.application.query_shared_activity().view
    value=p.application.set_shared_experience(SharedExperienceRequest(p.profile_id,p.timeline_id,'m019-reject-click-as-source-1',before['revision'],1,'合成回应',True))
    assert value.status=='unavailable' and p.application.query_shared_activity().view==before and len(model.calls)==1


def test_native_prepared_activity_recovers_without_model_and_keeps_original_uuid(native_activity,monkeypatch):
    from dynamic_subject_agent.timeline import TimelineEngine,FaultPoint
    from dynamic_subject_agent.living_activity import LivingActionRequest
    model=Transport();p=native_activity(model)
    first,_=send_native(p,'m020-original-native-request-1')
    assert control(p).status=='committed'
    request=LivingActionRequest(p.profile_id,p.timeline_id,'m020-native-prepared-choice-1',state(p)['revision'],'simulation')
    original=TimelineEngine._hit
    def hit(self,point):
        if point is FaultPoint.AFTER_PLAN_CLAIM:raise OSError('synthetic prepared native activity interruption')
        return original(self,point)
    with monkeypatch.context() as interrupted:
        interrupted.setattr(TimelineEngine,'_hit',hit)
        p.application.advance_living_activity(request)
    p.close();fresh=Transport();p=native_activity(fresh)
    assert not fresh.calls and p.application.query_shared_activity().view['activity_revision']==1
    assert p.application.advance_living_activity(request).status=='replayed' and not fresh.calls
    found=p.application.lookup_subject_request(SubjectRequestLookupRequest(first,'m020-original-native-request-1'))
    assert found.query_status=='found' and found.operation.status=='terminal' and not fresh.calls


def test_native_click_output_limit_does_not_commit_an_overlong_reply(native_activity):
    from dynamic_subject_agent.deepseek import DeepSeekHttpResponse
    class LongReply(Transport):
        def post_json(self,**kwargs):
            super().post_json(**kwargs)
            return DeepSeekHttpResponse(200,canonical_json(dict(model='deepseek-flash',choices=[dict(finish_reason='stop',message=dict(content='字'*121))],usage=dict(prompt_tokens=20,completion_tokens=121))).encode())
    model=LongReply();p=native_activity(model)
    cmd=NativeInteractionInput(p.profile_id,p.timeline_id,canonical_json(dict(kind='character-click')),canonical_json(dict(timer_phase='idle')))
    value=p.application.submit(cmd,idempotency_key='m018-overlong-click-reply-1')
    if value.status=='pending':value=p.application.wait(value.operation_ref,timeout_seconds=30)
    assert value.status in ('terminal','failed-closed') and value.projection.failure_code is not None
    assert not p.application.query_memorie_interactions().turns and len(model.calls)==1


def test_presence_suspension_discards_story_time_and_other_session_cannot_reset_owner(native_activity):
    from dynamic_subject_agent.living_activity import LivingClock,LivingPresenceRequest,LivingActionRequest
    now=[0.0];model=Transport();p=native_activity(model,clock=LivingClock(lambda:now[0]))
    assert control(p).status=='committed'
    request=LivingPresenceRequest(p.profile_id,p.timeline_id,'m020-owner-session-1')
    p.application.heartbeat_living_presence(request)
    for _ in range(89):
        now[0]+=10;p.application.heartbeat_living_presence(request)
    assert state(p)['online_seconds']==890 and not model.calls
    other=LivingPresenceRequest(p.profile_id,p.timeline_id,'m020-other-session-1')
    assert p.application.suspend_living_presence(other).problem_code=='another-life-window'
    assert state(p)['online_seconds']==890
    assert p.application.suspend_living_presence(request).problem_code=='presence-suspended'
    now[0]+=10;p.application.heartbeat_living_presence(request)
    assert state(p)['online_seconds']==0 and not model.calls
    for _ in range(90):
        now[0]+=10;p.application.heartbeat_living_presence(request)
    action=LivingActionRequest(p.profile_id,p.timeline_id,'m020-after-story-full-online-1',state(p)['revision'],'online',request.session_id)
    assert p.application.advance_living_activity(action).status=='committed' and len(model.calls)==1
    p.close();fresh=Transport();p=native_activity(fresh)
    assert state(p)['online_seconds']==0 and not fresh.calls


def test_native_timer_clarification_keeps_history_but_disclosure_control_never_sends(native_activity):
    model=Transport();p=native_activity(model)
    send_native(p,'m018-timer-original-click-1')
    send_native(p,'m018-timer-clarification-text-1','刚才我怎么跟你打招呼的？也请别把计时状态说成我已经学完了。')
    assert len(model.calls)==2
    payload=json.loads(model.calls[-1]['messages'][1]['content'])
    assert payload['exchange'][0]['interaction']==dict(kind='character-click')
    command=NativeInteractionInput(p.profile_id,p.timeline_id,canonical_json(dict(kind='text',text='不要把之前的聊天发给模型。')),canonical_json(None))
    value=p.application.submit(command,idempotency_key='m018-native-privacy-control-1')
    if value.status=='pending':value=p.application.wait(value.operation_ref,timeout_seconds=30)
    assert value.projection.failure_code is not None and len(model.calls)==2


def test_source_revocation_after_ticket_consumption_is_rechecked_at_transport(native_activity,monkeypatch):
    from dynamic_subject_agent.memorie_activity_live import NativeActivityDelivery
    model=Transport();p=native_activity(model);assert control(p).status=='committed'
    original=NativeActivityDelivery.consume
    def consume(self,task):
        actual=original(self,task)
        assert p.application.set_reviewed_character_history(False).history_enabled is False
        return actual
    monkeypatch.setattr(NativeActivityDelivery,'consume',consume)
    value=act(p,'m020-revoke-after-consumption-1')
    assert value.status=='failed-closed' and not model.calls
    assert p.application.query_living_controls().view['needs_attention'] is True


def test_revocation_during_credential_resolution_never_enters_https_opener(native_activity,monkeypatch):
    from dynamic_subject_agent import local_product,memorie_activity_provider
    from dynamic_subject_agent.deepseek import DeepSeekCredentialResolver
    class DelayedResolver(DeepSeekCredentialResolver):
        def resolve(self,ref):
            assert p.application.set_reviewed_character_history(False).history_enabled is False
            return 'synthetic-non-secret'
    monkeypatch.setattr(local_product,'_WindowsLabResolver',DelayedResolver)
    monkeypatch.setattr(memorie_activity_provider,'urlopen',lambda *a,**k:pytest.fail('revoked projection entered real HTTPS'))
    p=native_activity(live_transport=True);assert control(p).status=='committed'
    result=act(p,'m020-revoked-during-key-read-1')
    assert result.status=='failed-closed' and p.application.query_living_controls().view['needs_attention'] is True


def test_default_https_composition_rechecks_then_delivers_without_real_credentials(native_activity,monkeypatch):
    from io import BytesIO
    from dynamic_subject_agent import local_product,memorie_activity_provider
    from dynamic_subject_agent.deepseek import DeepSeekCredentialResolver
    class Resolver(DeepSeekCredentialResolver):
        def resolve(self,ref):return 'synthetic-non-secret'
    class Response(BytesIO):status=200
    model=Transport()
    def opening(request,*,timeout):
        value=model.post_json(body=request.data)
        return Response(value.body)
    monkeypatch.setattr(local_product,'_WindowsLabResolver',Resolver)
    monkeypatch.setattr(memorie_activity_provider,'urlopen',opening)
    p=native_activity(live_transport=True)
    send_native(p,'m020-default-https-typed-click-1')
    assert control(p).status=='committed'
    assert act(p,'m020-default-https-choice-1').status=='committed' and len(model.calls)==2
