import json
from dataclasses import asdict,replace
from copy import deepcopy
import pytest
from test_original_whole_chat import approved,personality_fixture,model_fixture,send,history
from test_natural_feedback_live import feedback_live_fixture,state
from test_natural_feedback_intent import IntentTransport
from test_shared_activity import step_request,select
from dynamic_subject_agent.local_product import open_natural_feedback_product_live
from dynamic_subject_agent.natural_feedback_multispan import NaturalFeedbackMultispanDevelopmentGrant,MULTISPAN_DEVELOPMENT
from dynamic_subject_agent.natural_feedback_live import APPROVED_FEEDBACK_REVIEW

PLAN=dict(subject='青台内的原创少女',composition='侧窗光不变。青台左角。'+'空间'*90+'青台右角。',focus='青台中的视线与小物件')
MESSAGE='这版把所有“青台”换成“禾台”，其他照旧。'

class MultispanTransport(IntentTransport):
    def __init__(self):super().__init__();self.plan=PLAN

@pytest.fixture
def multispan_fixture(feedback_live_fixture):
    _,config,options,_=feedback_live_fixture
    opts=dict(options,grant=NaturalFeedbackMultispanDevelopmentGrant(APPROVED_FEEDBACK_REVIEW,MULTISPAN_DEVELOPMENT),audit_path=options['audit_path'].with_name('multispan-audit'))
    opened=[]
    def opening(transport=None):
        p=open_natural_feedback_product_live(config,**opts,_transport=transport or MultispanTransport());opened.append(p);return p
    yield opening,config,opts
    for p in opened:p.close()

def started(multispan_fixture,plan=None,source=False):
    t=MultispanTransport()
    if plan is not None:t.plan=plan
    p=multispan_fixture[0](t)
    if source:
        assert send(p,'空间暂叫青台。','multispan-source').status=='terminal'
        assert select(p,'空间暂叫青台。').status=='committed'
    assert p.application.advance_shared_activity(step_request(p,'multispan-first-activity')).status=='committed'
    return p,t

def recorded_edits(p):
    import sqlite3
    binding=p._composition._host.query_binding(profile_id=p.profile_id,timeline_id=p.timeline_id)
    with sqlite3.connect(binding.timeline_root.timeline_database.as_uri()+'?mode=ro',uri=True) as db:
        records=[json.loads(row[0]) for row in db.execute('SELECT record_json FROM shared_activity_record')]
        return records[-1]['feedback']['proposal']['edits']

@pytest.mark.parametrize('case',['far-four','neighbour-context','exact-before-160','exact-after-240'])
def test_complete_facade_cover_preserves_every_non_target_character_and_old_bounds(multispan_fixture,case):
    plan=PLAN;new='禾台'
    if case=='neighbour-context':plan=dict(subject='少女',composition='侧窗光。青台甲青台乙青台丙。',focus='安静')
    if case=='exact-before-160':plan=dict(subject='少女',composition='青台'+'界'*156+'青台',focus='安静')
    if case=='exact-after-240':plan=dict(subject='少女',composition='青台'*3,focus='安静');new='新'*80
    p,t=started(multispan_fixture,plan);message='这版把所有“青台”换成“'+new+'”，其他照旧。'
    assert send(p,message,'multispan-positive-'+case).status=='terminal'
    assert asdict(state(p)['current_plan'])=={f:x.replace('青台',new) for f,x in plan.items()}
    edits=recorded_edits(p);assert 1<=len(edits)<=4
    intervals={f:[] for f in plan}
    for e in edits:
        assert len(e['before'])<=160 and len(e['after'])<=240 and e['before']!=e['after']
        text=plan[e['field']];start=text.find(e['before'])
        assert start>=0 and text.find(e['before'],start+1)<0
        end=start+len(e['before'])
        assert not any(start<b and a<end for a,b in intervals[e['field']])
        intervals[e['field']].append((start,end))
        assert e['after']==e['before'].replace('青台',new)
    if case=='far-four':assert len(edits)==4 and sum(e['field']=='composition' for e in edits)==2
    if case=='exact-before-160':assert len(edits)==1 and len(edits[0]['before'])==160
    if case=='exact-after-240':assert len(edits)==1 and len(edits[0]['after'])==240

@pytest.mark.parametrize('case',['needs-five','no-unique-window','after-limit'])
def test_unrepresentable_full_cover_is_rejected_without_partial_effect(multispan_fixture,case):
    new='禾台'
    if case=='needs-five':plan=dict(subject='青台的少女',composition=('一青台'+'空'*170+'二青台'+'空'*170+'三青台'+'空'*170+'四青台'),focus='安静')
    elif case=='no-unique-window':plan=dict(subject='少女',composition=('空'*170+'青台')*3,focus='安静')
    else:plan=dict(subject='少女',composition='青台'*4,focus='安静');new='新'*80
    p,t=started(multispan_fixture,plan);n=len(history(p));before=state(p)['current_plan']
    message='这版把所有“青台”换成“'+new+'”，其他照旧。'
    assert send(p,message,'multispan-no-cover-'+case).status=='failed-closed'
    assert state(p)['current_plan']==before and state(p)['activity_revision']==1 and len(history(p))==n
    assert send(p,message,'multispan-no-cover-'+case).status=='failed-closed' and len(t.calls)==2

def test_multispan_after_window_reopen_new_choice_and_privacy_receipt(multispan_fixture):
    p,t=started(multispan_fixture,source=True)
    assert send(p,MESSAGE,'multispan-shared-correction').status=='terminal'
    assert len(state(p)['result'].source_dependencies)==2
    for i in range(3):assert send(p,'合成新话题'+str(i),'multispan-topic-'+str(i)).status=='terminal'
    preview=p.application.preview_natural_feedback('当前看法。').view['payload']
    assert MESSAGE not in json.dumps(preview['exchange'],ensure_ascii=False)
    saved=history(p);ids=p.profile_id,p.timeline_id;p.close();fresh=MultispanTransport();p=multispan_fixture[0](fresh)
    assert not fresh.calls and history(p)==saved and ids==(p.profile_id,p.timeline_id)
    assert p.application.preview_shared_activity_step().view['payload']['current_feedback']['quote']==MESSAGE
    assert p.application.advance_shared_activity(step_request(p,'multispan-post-window-choice')).status=='committed'
    assert state(p)['activity_revision']==3 and '禾台' in state(p)['current_plan'].composition
    status=p.application.set_reviewed_character_history(False)
    assert status.status=='active' and status.history_enabled is False
    preview=p.application.preview_shared_activity_step().view['payload']
    assert preview['current_feedback'] is None and preview['current_plan'] is None

@pytest.mark.parametrize('message',[MESSAGE,'以后'+MESSAGE])
def test_extra_model_patch_and_missing_frame_cannot_grant_authority(multispan_fixture,message):
    p,t=started(multispan_fixture);before=state(p)['current_plan']
    t.override=dict(intent='revise',reply_text='不能发表。')
    if message==MESSAGE:t.override['edits']=[dict(field='composition',before='侧窗光',after='无光')]
    assert send(p,message,'multispan-scope-invalid').status=='failed-closed'
    assert state(p)['current_plan']==before

def test_final_publication_rejects_self_consistent_light_change_after_multispan_provider_check(multispan_fixture,monkeypatch):
    from dynamic_subject_agent.shared_activity_cognition import SharedActivityCognition
    from dynamic_subject_agent.natural_feedback import build_feedback_record
    p,t=started(multispan_fixture);before=state(p)['current_plan'];original=SharedActivityCognition.propose
    def mutate(self,**kwargs):
        value=original(self,**kwargs)
        if kwargs['command'].utterance==MESSAGE:
            raw=deepcopy(value.shared_record.feedback['proposal'])
            # Replace an existing composition span with a self-consistent
            # larger one while keeping <=4, so the final frame is decisive.
            edit=next(e for e in raw['edits'] if e['field']=='composition')
            edit.update(before='侧窗光不变。青台左角。',after='无光。禾台左角。')
            view=kwargs['context'].load_shared_activity(self.authorization())
            bad=build_feedback_record(view,command=kwargs['command'],authorization=self.authorization(),head_sequence=kwargs['plan'].expected_basis.head_sequence+1,proposal=raw)
            value=replace(value,shared_record=bad)
        return value
    monkeypatch.setattr(SharedActivityCognition,'propose',mutate)
    assert send(p,MESSAGE,'multispan-publication-extra').status=='failed-closed'
    import sqlite3
    binding=p._composition._host.query_binding(profile_id=p.profile_id,timeline_id=p.timeline_id)
    with sqlite3.connect(binding.timeline_root.timeline_database.as_uri()+'?mode=ro',uri=True) as db:
        rows=db.execute('SELECT record_json FROM shared_activity_record').fetchall()
        assert len(rows)==1 and json.loads(rows[0][0])['plan']==asdict(before)

@pytest.mark.parametrize('prepared',[False,True])
def test_multispan_cold_recovery_never_resends(multispan_fixture,monkeypatch,prepared):
    from dynamic_subject_agent.timeline import TimelineEngine,FaultPoint,PublicationInterrupted
    p,t=started(multispan_fixture)
    with monkeypatch.context() as crash:
        if prepared:
            original=TimelineEngine._hit
            def hit(self,point):
                if point is FaultPoint.AFTER_PLAN_CLAIM:raise OSError('Synthetic multi-span interruption')
                return original(self,point)
            crash.setattr(TimelineEngine,'_hit',hit)
        else:crash.setattr(TimelineEngine,'publish',lambda *a,**kw: (_ for _ in ()).throw(PublicationInterrupted('synthetic','Before prepared')))
        send(p,MESSAGE,'multispan-interrupted')
    assert len(t.calls)==2;p.close();fresh=MultispanTransport();p=multispan_fixture[0](fresh)
    assert not fresh.calls and state(p)['activity_revision']==(2 if prepared else 1)
    assert send(p,MESSAGE,'multispan-interrupted').status==('terminal' if prepared else 'failed-closed') and not fresh.calls
