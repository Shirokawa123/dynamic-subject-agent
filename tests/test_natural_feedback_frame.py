import json
from copy import deepcopy
from dataclasses import asdict,replace
import pytest

from test_original_whole_chat import approved,personality_fixture,model_fixture,send,history
from test_natural_feedback_live import feedback_live_fixture,state
from test_shared_activity import step_request,select
from dynamic_subject_agent.local_product import open_natural_feedback_product_live
from dynamic_subject_agent.deepseek import DeepSeekTransport,DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.natural_feedback_frame import requested_frame,SCOPED_DEVELOPMENT
from dynamic_subject_agent.natural_feedback_scoped import NaturalFeedbackScopedDevelopmentGrant
from dynamic_subject_agent.natural_feedback_live import APPROVED_FEEDBACK_REVIEW,open_natural_feedback_audit

PLAN=dict(subject='原创少女',composition='中景平视。桌上纸签写等风来。左上保留一点渐变光。人物在右侧。',focus='等风来与可爱体块的关系')
MESSAGE='这版把所有“等风来”换成“向光走”，其他照旧。'

class ScopedTransport(DeepSeekTransport):
    def __init__(self):self.calls=[];self.override=None
    def post_json(self,**kwargs):
        body=json.loads(kwargs['body']);self.calls.append(body);p=json.loads(body['messages'][1]['content'])
        if self.override is not None:value=self.override
        elif 'current_activity' in p:
            current=p['current_plan'];value=dict(action='start' if current is None else 'revise',
                plan=PLAN if current is None else dict(current,composition=current['composition']+'纸签稍微向前。'),
                reason_code='improve-readability',basis_refs=['E1'] if p['shared_experience'] else [],decision_note='合成具体取舍。')
        else:
            message=p['turn']['current_message'];current=p['current_plan']
            frame=requested_frame(message,None if current is None else __import__('dynamic_subject_agent.first_life',fromlist=['validate_plan']).validate_plan(current))
            edits=[] if frame is None else [dict(field=f,before=frame.before,after=frame.after) for f,text in current.items() if frame.before in text]
            value=dict(intent='revise' if edits else 'clarify' if message=='那个调一下。' else 'chat',edits=edits,
                reply_text='合成：只改纸签文案，其他字节保留。' if edits else '合成普通接话或澄清。')
        return DeepSeekHttpResponse(200,canonical_json(dict(model='deepseek-flash',choices=[dict(finish_reason='stop',message=dict(role='assistant',content=canonical_json(value)))],
            usage=dict(prompt_tokens=100,completion_tokens=100,total_tokens=200))).encode())

@pytest.fixture
def scoped_fixture(feedback_live_fixture):
    _,config,options,_=feedback_live_fixture
    opts=dict(options,grant=NaturalFeedbackScopedDevelopmentGrant(APPROVED_FEEDBACK_REVIEW,SCOPED_DEVELOPMENT),audit_path=options['audit_path'].with_name('scoped-audit'))
    opened=[]
    def opening(transport=None):
        p=open_natural_feedback_product_live(config,**opts,_transport=transport or ScopedTransport());opened.append(p);return p
    yield opening,config,opts
    for p in opened:p.close()

def started(scoped_fixture,source=False):
    opening,_,_=scoped_fixture;t=ScopedTransport();p=opening(t)
    if source:
        assert send(p,'纸签上写等风来。','frame-source').status=='terminal'
        assert select(p,'纸签上写等风来。').status=='committed'
    assert p.application.advance_shared_activity(step_request(p,'scoped-first-plan')).status=='committed'
    return p,t

def test_compact_constant_binding_requested_all_only_and_after_topics_reopen_new_activity(scoped_fixture):
    p,t=started(scoped_fixture,source=True)
    preview=p.application.preview_natural_feedback(MESSAGE);assert preview.status=='previewed',preview
    assert send(p,MESSAGE,'scoped-valid-feedback').status=='terminal'
    updated=state(p)['current_plan']
    assert asdict(updated)=={f:text.replace('等风来','向光走') for f,text in PLAN.items()}
    assert '一点渐变光' in updated.composition and updated.subject==PLAN['subject']
    assert state(p)['activity_revision']==2 and len(state(p)['result'].source_dependencies)==2
    for i in range(3):assert send(p,'合成新话题'+str(i),'frame-gap-'+str(i)).status=='terminal'
    assert MESSAGE not in canonical_json(p.application.preview_natural_feedback('继续。').view['payload']['exchange'])
    saved=history(p);identity=(p.profile_id,p.timeline_id);p.close()
    fresh=ScopedTransport();p=scoped_fixture[0](fresh)
    assert not fresh.calls and identity==(p.profile_id,p.timeline_id) and history(p)==saved
    assert p.application.preview_shared_activity_step().view['payload']['current_feedback']['quote']==MESSAGE
    assert p.application.advance_shared_activity(step_request(p,'frame-post-gap-activity')).status=='committed'
    assert '向光走' in state(p)['current_plan'].composition and '一点渐变光' in state(p)['current_plan'].composition
    assert state(p)['activity_revision']==3
    assert send(p,'现在这版呢？','frame-current-reply').status=='terminal'

@pytest.mark.parametrize('case',['light-delete','light-negate','subject','view','only-one-target','redundant-language','redundant-version','no-frame'])
def test_requested_frame_rejects_scope_expansion_whole_transaction_and_false_success(scoped_fixture,case):
    p,t=started(scoped_fixture);before=state(p)['current_plan'];n=len(history(p))
    edits=[dict(field='composition',before='等风来',after='向光走'),dict(field='focus',before='等风来',after='向光走')]
    raw=dict(intent='revise',edits=edits,reply_text='绝不应发表的合成候选。')
    if case=='light-delete':raw['edits'][0]=dict(field='composition',before='纸签写等风来。左上保留一点渐变光。',after='纸签写向光走。')
    if case=='light-negate':edits.append(dict(field='composition',before='一点渐变光',after='没有渐变光'))
    if case=='subject':edits.append(dict(field='subject',before='少女',after='少年'))
    if case=='view':edits.append(dict(field='composition',before='中景平视',after='近景俯视'))
    if case=='only-one-target':raw['edits']=edits[:1]
    if case=='redundant-language':raw['language']='zh'
    if case=='redundant-version':raw['activity_revision']=999
    t.override=raw
    message='把左边留白换纹理，光线照旧。' if case=='no-frame' else MESSAGE
    result=send(p,message,'scoped-invalid-'+case)
    assert result.status=='failed-closed',result
    assert len(history(p))==n and state(p)['current_plan']==before
    assert send(p,message,'scoped-invalid-'+case).status=='failed-closed'
    assert len(t.calls)==2

def test_uncertain_and_conditional_inputs_have_no_automatic_plan_effect(scoped_fixture):
    p,t=started(scoped_fixture);before=state(p)['current_plan']
    for i,message in enumerate(('那个调一下。','如果以后把所有“等风来”换成“向光走”，其他照旧。','先聊一下，不改当前版。')):
        assert send(p,message,'scoped-noop-'+str(i)).status=='terminal'
        assert state(p)['current_plan']==before and state(p)['activity_revision']==1

def test_publication_recomputes_frame_even_after_provider_precheck(scoped_fixture,monkeypatch):
    from dynamic_subject_agent.shared_activity_cognition import SharedActivityCognition
    from dynamic_subject_agent.natural_feedback import build_feedback_record
    p,t=started(scoped_fixture);before=state(p)['current_plan'];original=SharedActivityCognition.propose
    def mutate(self,**kwargs):
        value=original(self,**kwargs)
        if kwargs['command'].utterance==MESSAGE:
            raw=deepcopy(value.shared_record.feedback['proposal'])
            raw['edits'].append(dict(field='composition',before='一点渐变光',after='均匀暗部'))
            view=kwargs['context'].load_shared_activity(self.authorization())
            # Build a self-consistent old unscoped record, so only the new
            # Publication frame check can reject it.
            bad=build_feedback_record(view,command=kwargs['command'],authorization=self.authorization(),
                head_sequence=kwargs['plan'].expected_basis.head_sequence+1,proposal=raw)
            value=replace(value,shared_record=bad)
        return value
    monkeypatch.setattr(SharedActivityCognition,'propose',mutate)
    assert send(p,MESSAGE,'frame-publication-mutation').status=='failed-closed'
    # An inconsistent prepared candidate also closes fresh projections. Read
    # the canonical committed prefix to prove no illegal effect was published.
    assert p.application.query_shared_activity().status=='failed-closed'
    import sqlite3
    binding=p._composition._host.query_binding(profile_id=p.profile_id,timeline_id=p.timeline_id)
    with sqlite3.connect(binding.timeline_root.timeline_database.as_uri()+'?mode=ro',uri=True) as db:
        rows=db.execute('SELECT record_json FROM shared_activity_record').fetchall()
        assert len(rows)==1 and json.loads(rows[0][0])['plan']==asdict(before)

@pytest.mark.parametrize('prepared',[False,True])
def test_scoped_cold_recovery_rechecks_frame_and_never_resends(scoped_fixture,monkeypatch,prepared):
    from dynamic_subject_agent.timeline import TimelineEngine,FaultPoint,PublicationInterrupted
    p,t=started(scoped_fixture)
    with monkeypatch.context() as crash:
        if prepared:
            original=TimelineEngine._hit
            def hit(self,point):
                if point is FaultPoint.AFTER_PLAN_CLAIM:raise OSError('Synthetic scoped interruption')
                return original(self,point)
            crash.setattr(TimelineEngine,'_hit',hit)
        else:crash.setattr(TimelineEngine,'publish',lambda *a,**kw: (_ for _ in ()).throw(PublicationInterrupted('synthetic','Before prepared')))
        send(p,MESSAGE,'frame-interrupted')
    assert len(t.calls)==2;p.close();fresh=ScopedTransport();p=scoped_fixture[0](fresh)
    assert not fresh.calls and state(p)['activity_revision']==(2 if prepared else 1)
    assert send(p,MESSAGE,'frame-interrupted').status==('terminal' if prepared else 'failed-closed') and not fresh.calls

def test_frame_is_not_authorized_by_model_span_or_conditional_keyword():
    from dynamic_subject_agent.first_life import validate_plan
    plan=validate_plan(PLAN)
    assert requested_frame('把“等风来”换成“向光走”，其他照旧。',plan) is None
    assert requested_frame('以后把所有“等风来”换成“向光走”，其他照旧。',plan) is None
    assert requested_frame(MESSAGE,plan).expected_plan.composition==PLAN['composition'].replace('等风来','向光走')
