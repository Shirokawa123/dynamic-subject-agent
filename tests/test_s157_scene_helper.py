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
from dynamic_subject_agent.local_product import open_natural_feedback_product_live
from dynamic_subject_agent.natural_feedback_choice_budget import NaturalFeedbackChoiceBudgetGrant,CHOICE_DEVELOPMENT
from dynamic_subject_agent.natural_feedback_live import APPROVED_FEEDBACK_REVIEW
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_s157_candidate_scene as helper

@pytest.fixture
def s157_helper_fixture(multispan_fixture,monkeypatch,tmp_path):
    _,config,opts=multispan_fixture;root=tmp_path/'first-scoped';root.mkdir()
    opts=dict(opts,grant=NaturalFeedbackChoiceBudgetGrant(APPROVED_FEEDBACK_REVIEW,CHOICE_DEVELOPMENT,'choice-final'),audit_path=opts['audit_path'].with_name('scene-choice-final-audit'))
    def opening(transport):return open_natural_feedback_product_live(config,**opts,_transport=transport)
    monkeypatch.setattr(helper,'ROOT',root);monkeypatch.setattr(helper.evidence,'ROOT',root)
    monkeypatch.setattr(helper,'audit',lambda:list(open_natural_feedback_audit(opts['audit_path'],technical_variant='choice-final').snapshot()))
    captures=[]
    class Capture(DeepSeekTransport):
        def __init__(self,report,blocked=False):self.report=report;self.blocked=blocked;self.total=0;self.expected=None;self.final=None;self.fail=False;self.inner=MultispanTransport();self.inner.plan={k:v.replace("青台","晴架") for k,v in PLAN.items()};captures.append(self)
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
    monkeypatch.setattr(helper,'eligible_variant',lambda:'choice-final')
    report=dict(status='ready',next_stage=0,calls=[],stages=[],credential_read_attempts=0,automatic_retries=0,human_content_reviews={},provider_observations=[])
    yield report,captures


def test_compact_raw_and_bound_dto_exact10_source_patch_reopen_and_choice(s157_helper_fixture):
    report,captures=s157_helper_fixture
    for index in range(10):
        if index==2:helper.grade_long(report,2,'仅合成fixture中存在长距晴架。')
        assert helper.next_stage(report)==0,report
    assert report['status']=='scene-complete' and len(report['calls'])==10
    assert [r['after']['activity_revision'] for r in report['stages']]==[0,1,1,2,2,2,2,2,3,3]
    for row in report['stages']:
        if row.get('intent'):
            assert row['raw_output_fields']==['intent','reply_text']
            assert row['normalized_output_fields']==['activity_revision','edits','intent','language','reason_code','reply_text']
    assert '晴湾' in report['final_view']['current_plan']['composition'] and '侧窗光' in report['final_view']['current_plan']['composition']
    assert report['actual_reopen_after_gap']['requests']==0
    with pytest.raises(RuntimeError):helper.next_stage(report)
    assert sum(x.total for x in captures)==10



def test_compact_first_failure_is_terminal_without_retry(s157_helper_fixture,monkeypatch):
    report,captures=s157_helper_fixture;original=helper.evidence.CapturingTransport
    def failed(*args,**kwargs):x=original(*args,**kwargs);x.fail=True;return x
    monkeypatch.setattr(helper.evidence,'CapturingTransport',failed)
    assert helper.next_stage(report)==2
    with pytest.raises(RuntimeError):helper.next_stage(report)
    assert sum(x.total for x in captures)==1



def test_short_first_plan_cannot_be_used_as_long_sample_or_retried(s157_helper_fixture):
    report,captures=s157_helper_fixture
    assert helper.next_stage(report)==0 and helper.next_stage(report)==0
    report['status']='ready';report['next_stage']=2
    final_path=helper.ROOT/'finals/initial-activity.json'
    saved=json.loads(final_path.read_text(encoding='utf-8'));raw=json.loads(saved['final'])
    raw['plan']['composition']='晴架短稿。';saved['final']=canonical_json(raw)
    final_path.write_text(canonical_json(saved),encoding='utf-8')
    helper.grade_long(report,2,'合成短稿：内容分不能越过长距门槛。')
    assert report['status']=='bounded-end-initial-content-not-met' and report['human_content_reviews']['long']['score']==0
    with pytest.raises(RuntimeError):helper.next_stage(report)
    assert sum(x.total for x in captures)==2



@pytest.mark.parametrize('intent',['chat','clarify'])
def test_legal_non_revision_at_correction_ends_scene_without_followup_or_retry(s157_helper_fixture,monkeypatch,intent):
    report,captures=s157_helper_fixture
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



def test_nine_target_first_plan_stays_terminal_without_pruning_or_followup(s157_helper_fixture,monkeypatch):
    report,captures=s157_helper_fixture;original=helper.evidence.CapturingTransport
    def nine(*args,**kwargs):
        x=original(*args,**kwargs)
        x.inner.plan=dict(subject='晴架的少女',composition='晴架左侧。'+'原光线与镜头。'*30+'晴架右侧。',focus='晴架'*6)
        return x
    monkeypatch.setattr(helper.evidence,'CapturingTransport',nine)
    assert helper.next_stage(report)==0 and helper.next_stage(report)==0
    before=report['final_view']['current_plan']
    assert sum(text.count('晴架') for text in before.values())==9
    helper.grade_long(report,2,'合成九目标必须原样保留，内容分不能越过资格。')
    assert report['status']=='bounded-end-initial-content-not-met' and not report['human_content_reviews']['long']['eligible']
    assert report['final_view']['current_plan']==before
    with pytest.raises(RuntimeError):helper.next_stage(report)
    assert sum(x.total for x in captures)==2
