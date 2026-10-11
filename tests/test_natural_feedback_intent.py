import json
from dataclasses import asdict,replace
from copy import deepcopy
import pytest
from test_original_whole_chat import approved,personality_fixture,model_fixture,send,history
from test_natural_feedback_live import feedback_live_fixture,state
from test_shared_activity import step_request,select
from dynamic_subject_agent.local_product import open_natural_feedback_product_live
from dynamic_subject_agent.deepseek import DeepSeekTransport,DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.natural_feedback_intent import NaturalFeedbackIntentDevelopmentGrant,INTENT_DEVELOPMENT
from dynamic_subject_agent.natural_feedback_live import APPROVED_FEEDBACK_REVIEW

PLAN=dict(subject='原创少女',composition='中景平视，室内侧逆光。纸鹤靠左，远处纸鹤有灰影。少女在右侧。',focus='纸鹤与圆润体块的关系')
MESSAGE='这版把所有“纸鹤”换成“布偶”，其他照旧。'

class IntentTransport(DeepSeekTransport):
    def __init__(self):self.calls=[];self.override=None;self.plan=PLAN
    def post_json(self,**kwargs):
        body=json.loads(kwargs['body']);self.calls.append(body);p=json.loads(body['messages'][1]['content'])
        if self.override is not None:value=self.override
        elif 'current_activity' in p:
            current=p['current_plan'];value=dict(action='start' if current is None else 'revise',
                plan=self.plan if current is None else dict(current,composition=current['composition']+'物件稍向前。'),
                reason_code='improve-readability',basis_refs=['E1'] if p['shared_experience'] else [],decision_note='合成具体取舍。')
        else:
            message=p['turn']['current_message']
            value=dict(intent='revise' if message.startswith('这版把所有') else 'clarify' if message=='有一处没说清。' else 'chat',reply_text='合成意图与接话，无模型edit。')
        return DeepSeekHttpResponse(200,canonical_json(dict(model='deepseek-flash',choices=[dict(finish_reason='stop',message=dict(role='assistant',content=canonical_json(value)))],
            usage=dict(prompt_tokens=100,completion_tokens=80,total_tokens=180))).encode())

@pytest.fixture
def intent_fixture(feedback_live_fixture):
    _,config,options,_=feedback_live_fixture
    opts=dict(options,grant=NaturalFeedbackIntentDevelopmentGrant(APPROVED_FEEDBACK_REVIEW,INTENT_DEVELOPMENT),audit_path=options['audit_path'].with_name('intent-audit'))
    opened=[]
    def opening(transport=None):
        p=open_natural_feedback_product_live(config,**opts,_transport=transport or IntentTransport());opened.append(p);return p
    yield opening,config,opts
    for p in opened:p.close()

def started(intent_fixture,source=False,plan=None):
    t=IntentTransport()
    if plan is not None:t.plan=plan
    p=intent_fixture[0](t)
    if source:
        assert send(p,'画面放纸鹤。','intent-source').status=='terminal'
        assert select(p,'画面放纸鹤。').status=='committed'
    result=p.application.advance_shared_activity(step_request(p,'intent-first-activity-start'))
    assert result.status=='committed',result
    return p,t

def test_python_edits_multiple_targets_without_identity_edits_and_after_window_reopen_new_choice(intent_fixture):
    p,t=started(intent_fixture,source=True)
    assert send(p,MESSAGE,'intent-correction').status=='terminal'
    after=state(p);assert asdict(after['current_plan'])=={f:x.replace('纸鹤','布偶') for f,x in PLAN.items()}
    assert '侧逆光' in after['current_plan'].composition and after['activity_revision']==2
    assert len(after['result'].source_dependencies)==2
    import sqlite3
    binding=p._composition._host.query_binding(profile_id=p.profile_id,timeline_id=p.timeline_id)
    with sqlite3.connect(binding.timeline_root.timeline_database.as_uri()+'?mode=ro',uri=True) as db:
        records=[json.loads(row[0]) for row in db.execute('SELECT record_json FROM shared_activity_record')]
        edits=records[-1]['feedback']['proposal']['edits']
        assert [edit['field'] for edit in edits]==['composition','focus']
        assert all(edit['before']!=edit['after'] for edit in edits)
    for i in range(3):assert send(p,'合成换题'+str(i),'intent-topic-'+str(i)).status=='terminal'
    preview=p.application.preview_natural_feedback('此刻想法。').view['payload']
    assert MESSAGE not in canonical_json(preview['exchange'])
    saved=history(p);ids=p.profile_id,p.timeline_id;p.close();fresh=IntentTransport();p=intent_fixture[0](fresh)
    assert not fresh.calls and ids==(p.profile_id,p.timeline_id) and history(p)==saved
    assert p.application.preview_shared_activity_step().view['payload']['current_feedback']['quote']==MESSAGE
    assert p.application.advance_shared_activity(step_request(p,'intent-post-gap-activity')).status=='committed'
    assert state(p)['activity_revision']==3 and '布偶' in state(p)['current_plan'].composition
    assert send(p,'现在是什么？','intent-result').status=='terminal'

@pytest.mark.parametrize('extra',['edits','plan','language','activity_revision','reason_code'])
def test_model_cannot_supply_local_fields_or_patch(intent_fixture,extra):
    p,t=started(intent_fixture);n=len(history(p));old=state(p)['current_plan']
    t.override=dict(intent='revise',reply_text='不能发表。');t.override[extra]=[] if extra=='edits' else PLAN if extra=='plan' else 'invalid'
    assert send(p,MESSAGE,'intent-extra-'+extra).status=='failed-closed'
    assert len(history(p))==n and state(p)['current_plan']==old
    assert send(p,MESSAGE,'intent-extra-'+extra).status=='failed-closed' and len(t.calls)==2

@pytest.mark.parametrize('message',['换成布偶，光线照旧。','把“纸鹤”换成“布偶”，其他照旧。','以后把所有“纸鹤”换成“布偶”，其他照旧。'])
def test_revise_intent_does_not_grant_scope(intent_fixture,message):
    p,t=started(intent_fixture);old=state(p)['current_plan'];t.override=dict(intent='revise',reply_text='不能发表。')
    assert send(p,message,'intent-missing-frame').status=='failed-closed'
    assert state(p)['current_plan']==old and state(p)['activity_revision']==1

def test_local_edits_do_not_copy_long_unchanged_text_or_expand_existing_bounds(intent_fixture):
    long=dict(PLAN,composition='光线照旧。'+'空间'*100+'纸鹤靠左。')
    p,t=started(intent_fixture,plan=long)
    assert send(p,MESSAGE,'intent-long-untouched').status=='terminal'
    assert state(p)['current_plan'].composition==long['composition'].replace('纸鹤','布偶')
    p.close()

def test_unrepresentable_frame_does_not_expand_the_old_edit_bounds(intent_fixture):
    far=dict(PLAN,composition='纸鹤'+('空间'*100)+'纸鹤')
    p,t=started(intent_fixture,plan=far);old=state(p)['current_plan']
    assert send(p,MESSAGE,'intent-unrepresentable').status=='failed-closed'
    assert state(p)['current_plan']==old and state(p)['activity_revision']==1

@pytest.mark.parametrize('control',['disable','off','context'])
def test_existing_privacy_controls_remove_derived_feedback_before_next_choice(intent_fixture,control):
    p,t=started(intent_fixture,source=True)
    assert send(p,MESSAGE,'intent-private-feedback').status=='terminal'
    calls=len(t.calls)
    if control=='disable':assert select(p,'',None,'intent-disable-source').status=='committed'
    elif control=='off':
        status=p.application.set_reviewed_character_history(False)
        assert status.status=='active' and status.history_enabled is False
    else:
        from dynamic_subject_agent.whole_context_boundary import WholeContextBoundaryRequest
        assert p.application.apply_whole_context_boundary(WholeContextBoundaryRequest(p.profile_id,p.timeline_id,'intent-context-boundary',0,True)).status=='committed'
    assert len(t.calls)==calls;p.close();fresh=IntentTransport();p=intent_fixture[0](fresh)
    preview=p.application.preview_shared_activity_step()
    assert preview.status=='previewed' and not fresh.calls
    assert preview.view['payload']['current_plan'] is None and preview.view['payload']['current_feedback'] is None

def test_intent_candidate_publication_still_rejects_self_consistent_extra_light_change(intent_fixture,monkeypatch):
    from dynamic_subject_agent.shared_activity_cognition import SharedActivityCognition
    from dynamic_subject_agent.natural_feedback import build_feedback_record
    p,t=started(intent_fixture);old=state(p)['current_plan'];original=SharedActivityCognition.propose
    def mutate(self,**kwargs):
        result=original(self,**kwargs)
        if kwargs['command'].utterance==MESSAGE:
            proposal=deepcopy(result.shared_record.feedback['proposal'])
            proposal['edits'].append(dict(field='composition',before='室内侧逆光',after='均匀平光'))
            view=kwargs['context'].load_shared_activity(self.authorization())
            bad=build_feedback_record(view,command=kwargs['command'],authorization=self.authorization(),head_sequence=kwargs['plan'].expected_basis.head_sequence+1,proposal=proposal)
            result=replace(result,shared_record=bad)
        return result
    monkeypatch.setattr(SharedActivityCognition,'propose',mutate)
    assert send(p,MESSAGE,'intent-extra-publication').status=='failed-closed'
    import sqlite3
    binding=p._composition._host.query_binding(profile_id=p.profile_id,timeline_id=p.timeline_id)
    with sqlite3.connect(binding.timeline_root.timeline_database.as_uri()+'?mode=ro',uri=True) as db:
        rows=db.execute('SELECT record_json FROM shared_activity_record').fetchall()
        assert len(rows)==1 and json.loads(rows[0][0])['plan']==asdict(old)

@pytest.mark.parametrize('prepared',[False,True])
def test_intent_cold_recovery_preserves_atomicity_and_original_nonce_zero_resend(intent_fixture,monkeypatch,prepared):
    from dynamic_subject_agent.timeline import TimelineEngine,FaultPoint,PublicationInterrupted
    p,t=started(intent_fixture)
    with monkeypatch.context() as crash:
        if prepared:
            original=TimelineEngine._hit
            def hit(self,point):
                if point is FaultPoint.AFTER_PLAN_CLAIM:raise OSError('Synthetic intent interruption')
                return original(self,point)
            crash.setattr(TimelineEngine,'_hit',hit)
        else:crash.setattr(TimelineEngine,'publish',lambda *a,**kw: (_ for _ in ()).throw(PublicationInterrupted('synthetic','Before prepared')))
        send(p,MESSAGE,'intent-interrupted')
    assert len(t.calls)==2;p.close();fresh=IntentTransport();p=intent_fixture[0](fresh)
    assert not fresh.calls and state(p)['activity_revision']==(2 if prepared else 1)
    assert send(p,MESSAGE,'intent-interrupted').status==('terminal' if prepared else 'failed-closed') and not fresh.calls

@pytest.mark.parametrize('variant',['baseline','direct-final','scoped'])
def test_existing_feedback_variants_history_control_receipt_matches_verified_audit(feedback_live_fixture,variant):
    opening,config,options,_=feedback_live_fixture
    if variant=='baseline':p=opening()
    else:
        from dynamic_subject_agent.natural_feedback_budget import NaturalFeedbackBudgetDevelopmentGrant,BUDGET_DEVELOPMENT
        from dynamic_subject_agent.natural_feedback_scoped import NaturalFeedbackScopedDevelopmentGrant
        from dynamic_subject_agent.natural_feedback_frame import SCOPED_DEVELOPMENT
        grant=NaturalFeedbackBudgetDevelopmentGrant(APPROVED_FEEDBACK_REVIEW,BUDGET_DEVELOPMENT) if variant=='direct-final' else NaturalFeedbackScopedDevelopmentGrant(APPROVED_FEEDBACK_REVIEW,SCOPED_DEVELOPMENT)
        p=open_natural_feedback_product_live(config,**dict(options,grant=grant,audit_path=options['audit_path'].with_name('status-'+variant)),_transport=IntentTransport())
    try:
        status=p.application.set_reviewed_character_history(False)
        assert status.status=='active' and status.history_enabled is False
        assert p.application.preview_shared_activity_step().view['payload']['current_feedback'] is None
    finally:p.close()
