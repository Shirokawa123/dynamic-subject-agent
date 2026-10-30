"""Real LOCAL Facade/Timeline; model decisions are explicit synthetic fixtures."""
import json
import sqlite3
from copy import deepcopy
from contextlib import closing
from hashlib import sha256
from dataclasses import replace
import pytest

from test_original_whole_chat import approved, model_fixture, personality_fixture, send, history
from dynamic_subject_agent.local_product import open_natural_experience_product_local
from dynamic_subject_agent.model_gateway import ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelGateway, ModelResult, ModelTaskKind
from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint, PublicationInterrupted
from test_living_activity import control, act

TEMP = '今天我只想安静看书，明天不一定。'
CORRECT = '刚才说错了，今天只是想一起讨论。'
STOP = '那段经历不用再记住了。'
CONTINUE = '我们接着聊。'
PAST = '你刚才在做什么？'


class LocalAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities('natural-local-fixture', 'synthetic', True, (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self):
        self.calls = []
        self.bad_speech = False
        self.request_plan = False

    def invoke(self, task):
        self.calls.append(task)
        if task.kind is ModelTaskKind.MEMORIE_NATURAL_EXPERIENCE:
            text = task.payload['current_user_text']
            value = dict(action='remember', duration='today', reason_code='temporary') if text == TEMP else (
                dict(action='remember', duration='until_changed', reason_code='correction') if text == CORRECT else
                dict(action='forget', duration=None, reason_code='explicit-forget') if text == STOP else
                dict(action='keep', duration=None, reason_code='unclear'))
        elif task.kind is ModelTaskKind.MEMORIE_GROUNDED_EXPRESSION:
            text = task.payload['current_user_text']
            if self.bad_speech:
                value = dict(act='discuss_plan', reference='A1', style='gentle', text='刚才整理了桌上的药草笔记。')
            elif self.request_plan:
                value = dict(act='discuss_plan', reference='A1', style='brief')
            elif text in (CORRECT, STOP):
                value = dict(act='acknowledge_change', reference=None, style='gentle')
            elif text == PAST:
                value = dict(act='unknown_past', reference=None, style='gentle')
            else:
                source = task.payload['experience']
                value = dict(act='recall_user' if source else 'ask', reference='E1' if source else None, style='gentle')
        elif task.kind is ModelTaskKind.LIVING_ACTIVITY_CHOICE:
            p=task.payload['payload']
            value=dict(action='start' if p['current_plan'] is None else 'revise',
                plan=dict(subject='合成：观察与待核问题分栏',composition='只整理观察与问题，不宣称采药或药效。',focus='核对差异'),
                reason_code='improve-readability',basis_refs=['E1'] if p['shared_experience'] else [],decision_note='合成根据给定经历安排栏目。')
        else:
            raise AssertionError('Unexpected fixture task')
        return ModelResult(task.kind, value)


@pytest.fixture
def natural_fixture(approved, monkeypatch):
    author, config, request, view = approved
    frozen = author.application.freeze_source_identity(request)
    assert frozen.status == 'created'
    author.close()
    asset = json.loads(view.runtime_asset_json)
    binding = dict(definition_basis=view.definition_basis, runtime_asset_sha=view.runtime_asset_sha,
        persona_digest=asset['persona_digest'], review_basis='e'*64, scope_digest='f'*64,
        subject_id=asset['subject']['subject_id'], anchor_id=asset['anchor']['anchor_id'])
    import dynamic_subject_agent.timeline as timeline
    now = [timeline._utc_microseconds()]
    monkeypatch.setattr(timeline, '_utc_microseconds', lambda: now[0])
    opened = []
    def opening(adapter=None):
        p = open_natural_experience_product_local(config, gateway=ModelGateway(adapter or LocalAdapter()),
            identity_id=frozen.view.identity_id, binding=binding, now_us=lambda: now[0])
        opened.append(p)
        return p
    opening.now, opening.config, opening.identity_id, opening.binding = now, config, frozen.view.identity_id, binding
    yield opening
    for p in opened:
        p.close()


def state(product):
    result = product.application.query_living_activity()
    assert result.status == 'available', result
    return result.view


def test_remember_correct_reopen_and_stop_share_one_timeline(natural_fixture):
    adapter = LocalAdapter(); p = natural_fixture(adapter)
    scope = p.profile_id, p.timeline_id
    first = send(p, TEMP, 'natural-first')
    assert first.status == 'terminal' and first.projection.failure_code is None, first
    assert state(p)['natural_experience']['quote'] == TEMP
    changed = send(p, CORRECT, 'natural-correction')
    assert changed.status == 'terminal' and changed.projection.failure_code is None, changed
    assert state(p)['natural_experience']['quote'] == CORRECT
    assert state(p)['natural_experience']['duration'] == 'today'
    p.close(); fresh = LocalAdapter(); p = natural_fixture(fresh)
    assert (p.profile_id,p.timeline_id)==scope and not fresh.calls
    assert state(p)['natural_experience']['quote']==CORRECT
    result=send(p,CONTINUE,'natural-continue')
    assert CORRECT in result.projection.expression_text and TEMP not in result.projection.expression_text
    assert send(p,STOP,'natural-stop').projection.failure_code is None
    assert state(p)['natural_experience'] is None and state(p)['source'] is None
    result=send(p,PAST,'natural-past')
    assert result.projection.expression_text=='刚才那段我说不准，先不乱讲。我们从现在接着聊吧。'
    assert not any(x in result.projection.expression_text for x in ('浇水','整理桌','香草搭配'))
    count=len(fresh.calls)
    assert send(p,PAST,'natural-past').status=='terminal'
    assert len(fresh.calls)==count


def test_expiry_filters_source_on_read_and_next_reply(natural_fixture):
    adapter=LocalAdapter();p=natural_fixture(adapter)
    assert send(p,TEMP,'natural-day-one').projection.failure_code is None
    before=state(p)['revision'];count=len(adapter.calls)
    timelines=list(natural_fixture.config.product_parent.rglob('timeline.sqlite3'))
    assert timelines
    digests={path:sha256(path.read_bytes()).hexdigest() for path in timelines}
    natural_fixture.now[0]+=86400*1_000_000
    assert state(p)['natural_experience'] is None and state(p)['source'] is None
    assert state(p)['revision']==before and len(adapter.calls)==count
    assert {path:sha256(path.read_bytes()).hexdigest() for path in timelines}==digests
    result=send(p,CONTINUE,'natural-day-two')
    assert result.projection.failure_code is None and TEMP not in result.projection.expression_text
    assert adapter.calls[-2].payload['current_experience'] is None
    assert adapter.calls[-1].payload['experience'] is None


def test_failed_expression_does_not_partially_apply_new_memory(natural_fixture):
    adapter=LocalAdapter();p=natural_fixture(adapter)
    assert send(p,TEMP,'natural-before-failure').projection.failure_code is None
    before=state(p)['natural_experience'];adapter.bad_speech=True
    result=send(p,CORRECT,'natural-invalid-speech')
    assert result.status=='failed-closed' or result.projection.failure_code
    assert state(p)['natural_experience']==before
    p.close();fresh=LocalAdapter();p=natural_fixture(fresh)
    assert state(p)['natural_experience']==before and not fresh.calls


@pytest.mark.parametrize('prepared',[False,True])
def test_prepared_publication_recovers_once_without_regeneration(natural_fixture,monkeypatch,prepared):
    adapter=LocalAdapter();p=natural_fixture(adapter)
    assert send(p,TEMP,'natural-recovery-before').projection.failure_code is None
    with monkeypatch.context() as crash:
        if prepared:
            hit=TimelineEngine._hit
            def fail(self,point):
                if point is FaultPoint.AFTER_PLAN_CLAIM:raise OSError('Synthetic interrupted natural publication')
                return hit(self,point)
            crash.setattr(TimelineEngine,'_hit',fail)
        else:
            crash.setattr(TimelineEngine,'publish',lambda *a,**kw:(_ for _ in ()).throw(PublicationInterrupted('synthetic','before preparation')))
        send(p,CORRECT,'natural-recovery-current')
    p.close();fresh=LocalAdapter();p=natural_fixture(fresh)
    expected=CORRECT if prepared else TEMP
    assert state(p)['natural_experience']['quote']==expected and not fresh.calls
    send(p,CORRECT,'natural-recovery-current')
    assert not fresh.calls


def test_committed_plan_can_be_referenced_but_stopped_source_invalidates_it(natural_fixture):
    adapter=LocalAdapter();p=natural_fixture(adapter)
    assert send(p,TEMP,'natural-plan-source').projection.failure_code is None
    control(p,paused=False)
    result=act(p,'simulation','natural-plan-start')
    assert result.status=='committed',result
    plan=state(p)['current_plan'];assert plan is not None
    adapter.request_plan=True
    reply=send(p,'我们聊聊这份方案。','natural-plan-reply')
    assert reply.projection.failure_code is None and plan.subject in reply.projection.expression_text
    assert '文字方案' in reply.projection.expression_text
    adapter.request_plan=False
    assert send(p,STOP,'natural-plan-stop').projection.failure_code is None
    assert state(p)['current_plan'] is None and state(p)['visible_result'] is None
    adapter.request_plan=True
    rejected=send(p,'还讲讲那份方案。','natural-plan-invalid-reference')
    assert rejected.status=='failed-closed' or rejected.projection.failure_code
    assert state(p)['natural_experience'] is None


def test_remote_gateway_rejected_before_identity_access(tmp_path):
    from dynamic_subject_agent.local_product import LocalProductConfig
    class Remote(LocalAdapter):
        capabilities=ProviderCapabilities('remote-test','synthetic',False,(StructuredOutputMode.JSON_OBJECT,))
    root=tmp_path/'never-opened'
    config=LocalProductConfig(root/'DynamicSubjectAgent/m0/experiments',root/'state.json')
    with pytest.raises(ValueError,match='LOCAL natural gateway'):
        open_natural_experience_product_local(config,gateway=ModelGateway(Remote()),identity_id='unused',binding={})
    assert not root.exists()


def test_old_local_identity_is_not_automatically_converted(natural_fixture):
    from dynamic_subject_agent.local_product import open_living_activity_product_local
    old=open_living_activity_product_local(natural_fixture.config,gateway=ModelGateway(LocalAdapter()),
        identity_id=natural_fixture.identity_id,binding=natural_fixture.binding,activity_kind='herb-note-outline')
    old.close()
    raw=natural_fixture.config.state_path.read_bytes()
    with pytest.raises(RuntimeError,match='activation-conflict'):
        natural_fixture()
    assert natural_fixture.config.state_path.read_bytes()==raw


def test_publication_recomputes_source_instead_of_trusting_cognition(natural_fixture,monkeypatch):
    from dynamic_subject_agent.natural_experience_cognition import NaturalExperienceCognition
    p=natural_fixture()
    paths=list(natural_fixture.config.product_parent.rglob('timeline.sqlite3'))
    def heads():
        result={}
        for path in paths:
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
                result[str(path)]=db.execute('SELECT COUNT(*) FROM timeline_outcome').fetchone()[0]
        return result
    before=heads()
    original=NaturalExperienceCognition._propose_living
    def forged(self,**kwargs):
        proposal=original(self,**kwargs)
        record=proposal.shared_record;data=deepcopy(record.natural)
        data['experience']['quote']='合成伪造的用户原话'
        return replace(proposal,shared_record=replace(record,
            source=replace(record.source,quote=data['experience']['quote']),natural=data))
    monkeypatch.setattr(NaturalExperienceCognition,'_propose_living',forged)
    result=send(p,TEMP,'natural-forged-source')
    assert result.status=='failed-closed' or result.projection.failure_code
    assert heads()==before


def test_quoted_control_is_discussion_but_explicit_nondisclosure_never_calls_model(natural_fixture):
    adapter=LocalAdapter();p=natural_fixture(adapter)
    result=send(p,'我是在解释“不要外发”这句话的意思。','natural-quoted-control')
    assert result.status=='terminal' and result.projection.failure_code is None
    count=len(adapter.calls)
    result=send(p,'不要把这段聊天发送给模型。','natural-real-disclosure')
    assert result.status!='terminal' or result.projection.failure_code
    assert len(adapter.calls)==count


def test_cited_original_cannot_break_its_speaker_quotation():
    from dynamic_subject_agent.natural_experience_cycle import render_speech
    quote='今天想看书”。我刚才采了药。'
    frame=dict(experience=dict(label='E1',quote=quote),activity_result=None,allowed_acts=['recall_user'])
    text=render_speech(dict(act='recall_user',reference='E1',style='brief'),frame,changed=False)
    assert text.count('“')==text.count('”')==1 and '看书」' in text
    assert frame['experience']['quote']==quote
