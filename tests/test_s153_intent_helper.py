import json
from hashlib import sha256
from pathlib import Path
import sys
import pytest

from test_original_whole_chat import approved,personality_fixture,model_fixture
from test_natural_feedback_live import feedback_live_fixture
from test_natural_feedback_intent import intent_fixture,IntentTransport,PLAN
from dynamic_subject_agent.natural_feedback_live import open_natural_feedback_audit
from dynamic_subject_agent.deepseek import DeepSeekTransport,DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_s153_intent_continuity as helper

@pytest.fixture
def s153_helper_fixture(intent_fixture,monkeypatch,tmp_path):
    opening,_,opts=intent_fixture;root=tmp_path/'first-scoped';root.mkdir()
    monkeypatch.setattr(helper,'ROOT',root);monkeypatch.setattr(helper.evidence,'ROOT',root)
    monkeypatch.setattr(helper,'audit',lambda:list(open_natural_feedback_audit(opts['audit_path'],technical_variant='intent-only').snapshot()))
    captures=[]
    class Capture(DeepSeekTransport):
        def __init__(self,report,blocked=False):self.report=report;self.blocked=blocked;self.total=0;self.expected=None;self.final=None;self.fail=False;self.inner=IntentTransport();captures.append(self)
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

def test_compact_raw_and_bound_dto_exact10_source_patch_reopen_and_choice(s153_helper_fixture):
    report,captures=s153_helper_fixture
    for index in range(10):
        if index==2:helper.grade_object(report,2,'仅合成fixture中存在物件纸鹤。')
        assert helper.next_stage(report)==0,report
    assert report['status']=='scene-complete' and len(report['calls'])==10
    assert [r['after']['activity_revision'] for r in report['stages']]==[0,1,2,2,2,2,2,2,3,3]
    for row in report['stages']:
        if row.get('intent'):
            assert row['raw_output_fields']==['intent','reply_text']
            assert row['normalized_output_fields']==['activity_revision','edits','intent','language','reason_code','reply_text']
    assert '布偶' in report['final_view']['current_plan']['composition'] and '室内侧逆光' in report['final_view']['current_plan']['composition']
    assert report['actual_reopen_after_gap']['requests']==0
    with pytest.raises(RuntimeError):helper.next_stage(report)
    assert sum(x.total for x in captures)==10

def test_compact_first_failure_is_terminal_without_retry(s153_helper_fixture,monkeypatch):
    report,captures=s153_helper_fixture;original=helper.evidence.CapturingTransport
    def failed(*args,**kwargs):x=original(*args,**kwargs);x.fail=True;return x
    monkeypatch.setattr(helper.evidence,'CapturingTransport',failed)
    assert helper.next_stage(report)==2
    with pytest.raises(RuntimeError):helper.next_stage(report)
    assert sum(x.total for x in captures)==1
