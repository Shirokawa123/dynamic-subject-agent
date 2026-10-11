import json
from hashlib import sha256
from pathlib import Path
import sys
import pytest

from test_original_whole_chat import approved,personality_fixture,model_fixture
from test_natural_feedback_live import feedback_live_fixture
from test_natural_feedback_multispan import multispan_fixture,MultispanTransport,PLAN
from dynamic_subject_agent.natural_feedback_live import open_natural_feedback_audit
from dynamic_subject_agent.deepseek import DeepSeekTransport,DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_s155_long_continuity as helper

@pytest.fixture
def s155_helper_fixture(multispan_fixture,monkeypatch,tmp_path):
    opening,_,opts=multispan_fixture;root=tmp_path/'first-scoped';root.mkdir()
    monkeypatch.setattr(helper,'ROOT',root);monkeypatch.setattr(helper.evidence,'ROOT',root)
    monkeypatch.setattr(helper,'audit',lambda:list(open_natural_feedback_audit(opts['audit_path'],technical_variant='multi-span').snapshot()))
    captures=[]
    class Capture(DeepSeekTransport):
        def __init__(self,report,blocked=False):self.report=report;self.blocked=blocked;self.total=0;self.expected=None;self.final=None;self.fail=False;self.inner=MultispanTransport();self.inner.plan={k:v.replace("青台","汀舍") for k,v in PLAN.items()};captures.append(self)
        def arm(self,label,wire):self.expected=dict(label=label,wire_sha256=sha256(wire).hexdigest())
        def post_json(self,**kwargs):
            assert not self.blocked and self.expected
            assert sha256(kwargs['body']).hexdigest()==self.expected['wire_sha256']
            self.total+=1;self.report['calls'].append(dict(self.expected,status='received'))
            response=self.inner.post_json(**kwargs);payload=json.loads(response.body)
            self.final='' if self.fail else payload['choices'][0]['message']['content']
            helper.evidence.save(root/'finals'/(self.expected['label']+'.json'),dict(final=self.final));self.expected=None;helper.save(self.report)
            if self.fail:
                payload['choices'][0]['message']['content']='';payload['choices'][0]['finish_reason']='length'
                return DeepSeekHttpResponse(200,canonical_json(payload).encode())
            return response
    monkeypatch.setattr(helper.evidence,'CapturingTransport',Capture)
    monkeypatch.setattr(helper,'opening',lambda report,transport:opening(transport))
    report=dict(status='ready',next_stage=0,calls=[],stages=[],credential_read_attempts=0,automatic_retries=0,human_content_reviews={},provider_observations=[])
    yield report,captures

def test_compact_raw_and_bound_dto_exact10_source_patch_reopen_and_choice(s155_helper_fixture):
    report,captures=s155_helper_fixture
    for index in range(10):
        if index==2:helper.grade_long(report,2,'仅合成fixture中存在长距汀舍。')
        assert helper.next_stage(report)==0,report
    assert report['status']=='scene-complete' and len(report['calls'])==10
    assert [r['after']['activity_revision'] for r in report['stages']]==[0,1,1,2,2,2,2,2,3,3]
    for row in report['stages']:
        if row.get('intent'):
            assert row['raw_output_fields']==['intent','reply_text']
            assert row['normalized_output_fields']==['activity_revision','edits','intent','language','reason_code','reply_text']
    assert '栖舍' in report['final_view']['current_plan']['composition'] and '侧窗光' in report['final_view']['current_plan']['composition']
    assert report['actual_reopen_after_gap']['requests']==0
    with pytest.raises(RuntimeError):helper.next_stage(report)
    assert sum(x.total for x in captures)==10

def test_compact_first_failure_is_terminal_without_retry(s155_helper_fixture,monkeypatch):
    report,captures=s155_helper_fixture;original=helper.evidence.CapturingTransport
    def failed(*args,**kwargs):x=original(*args,**kwargs);x.fail=True;return x
    monkeypatch.setattr(helper.evidence,'CapturingTransport',failed)
    assert helper.next_stage(report)==2
    with pytest.raises(RuntimeError):helper.next_stage(report)
    assert sum(x.total for x in captures)==1


def test_short_first_plan_cannot_be_used_as_long_sample_or_retried(s155_helper_fixture):
    report,captures=s155_helper_fixture
    assert helper.next_stage(report)==0 and helper.next_stage(report)==0
    report['status']='ready';report['next_stage']=2
    final_path=helper.ROOT/'finals/initial-activity.json'
    saved=json.loads(final_path.read_text(encoding='utf-8'));raw=json.loads(saved['final'])
    raw['plan']['composition']='汀舍短稿。';saved['final']=canonical_json(raw)
    final_path.write_text(canonical_json(saved),encoding='utf-8')
    helper.grade_long(report,2,'合成短稿：内容分不能越过长距门槛。')
    assert report['status']=='bounded-end-initial-content-not-met' and report['human_content_reviews']['long']['score']==0
    with pytest.raises(RuntimeError):helper.next_stage(report)
    assert sum(x.total for x in captures)==2


@pytest.mark.parametrize('intent',['chat','clarify'])
def test_legal_non_revision_at_correction_ends_scene_without_followup_or_retry(s155_helper_fixture,monkeypatch,intent):
    report,captures=s155_helper_fixture
    for index in range(3):
        if index==2:helper.grade_long(report,2,'合成长距初稿满足门槛。')
        assert helper.next_stage(report)==0
    before=report['final_view']['current_plan'];original=helper.evidence.CapturingTransport
    def unchanged(*args,**kwargs):
        x=original(*args,**kwargs);x.inner.override=dict(intent=intent,reply_text='合成询问，当前未改。');return x
    monkeypatch.setattr(helper.evidence,'CapturingTransport',unchanged)
    assert helper.next_stage(report)==0 and report['status']=='bounded-end-correction-not-applied'
    assert report['final_view']['current_plan']==before and report['final_view']['activity_revision']==1
    with pytest.raises(RuntimeError):helper.next_stage(report)
    assert sum(x.total for x in captures)==4


@pytest.mark.parametrize('outcome',['defer','old-name','split-new-name'])
def test_post_gap_legal_choice_without_required_result_ends_without_result_reply_or_retry(s155_helper_fixture,monkeypatch,outcome):
    report,captures=s155_helper_fixture
    for index in range(8):
        if index==2:helper.grade_long(report,2,'合成长距初稿满足门槛。')
        assert helper.next_stage(report)==0
    original=helper.evidence.CapturingTransport
    def incomplete(*args,**kwargs):
        x=original(*args,**kwargs)
        plan=dict(report['final_view']['current_plan'],composition='汀舍旧名合成新稿。')
        if outcome=='split-new-name':plan=dict(subject='窗边的栖',composition='舍内合成新稿。',focus='安静的窗光。')
        x.inner.override=dict(action='defer' if outcome=='defer' else 'revise',
            plan=None if outcome=='defer' else plan,
            reason_code='defer-comparison' if outcome=='defer' else 'try-alternative',basis_refs=[],decision_note='合成本次选择。')
        return x
    monkeypatch.setattr(helper.evidence,'CapturingTransport',incomplete)
    assert helper.next_stage(report)==0
    assert report['status']==('bounded-end-post-gap-no-new-plan' if outcome=='defer' else 'bounded-end-post-gap-name-not-preserved')
    assert report['actual_reopen_after_gap']['requests']==0
    with pytest.raises(RuntimeError):helper.next_stage(report)
    assert sum(x.total for x in captures)==9


def test_inspection_looks_up_saved_pending_nonce_without_sending(s155_helper_fixture):
    report,captures=s155_helper_fixture
    assert helper.next_stage(report)==0
    report['stages'][-1]['status']='pending';report['status']='first-stage-failed'
    helper.inspect(report)
    assert report['readonly_inspection']['original_nonce'] and report['readonly_inspection']['requests']==0
    assert sum(x.total for x in captures)==1
