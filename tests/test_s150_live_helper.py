"""First-scene orchestration through the Facade, with a synthetic transport."""
import json
from hashlib import sha256
from pathlib import Path
import sys
import pytest

from test_original_whole_chat import approved, personality_fixture, model_fixture
from test_natural_feedback_live import feedback_live_fixture, FeedbackTransport
from dynamic_subject_agent.natural_feedback_live import open_natural_feedback_audit
from dynamic_subject_agent.deepseek import DeepSeekTransport

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_s150_live_feedback as helper


@pytest.fixture
def helper_fixture(feedback_live_fixture,monkeypatch,tmp_path):
    opening,_,options,_=feedback_live_fixture
    root=tmp_path/'first-run';root.mkdir()
    monkeypatch.setattr(helper,'ROOT',root)
    monkeypatch.setattr(helper.evidence,'ROOT',root)
    monkeypatch.setattr(helper,'audit',lambda:list(open_natural_feedback_audit(options['audit_path']).snapshot()))
    captures=[]
    class FakeCapture(DeepSeekTransport):
        def __init__(self,report,blocked=False):
            self.report=report;self.blocked=blocked;self.total=0;self.expected=None;self.final=None
            self.inner=FeedbackTransport();captures.append(self)
        def arm(self,label,wire):self.expected=dict(label=label,wire_sha256=sha256(wire).hexdigest())
        def post_json(self,**kwargs):
            assert not self.blocked and self.expected is not None
            assert sha256(kwargs['body']).hexdigest()==self.expected['wire_sha256']
            self.total+=1
            row=dict(self.expected,status='received');self.report['calls'].append(row)
            response=self.inner.post_json(**kwargs);envelope=json.loads(response.body)
            self.final=envelope['choices'][0]['message']['content']
            helper.evidence.save(root/'finals'/(self.expected['label']+'.json'),dict(final=self.final))
            helper.save(self.report);self.expected=None
            return response
    monkeypatch.setattr(helper.evidence,'CapturingTransport',FakeCapture)
    monkeypatch.setattr(helper,'opening',lambda report,transport:opening(transport))
    report=dict(status='ready',next_stage=0,calls=[],stages=[],credential_read_attempts=0,automatic_retries=0,human_content_reviews={})
    return report,root,captures


def test_frozen_first_scene_ten_requests_one_source_selection_reopen_zero_and_no_extra_request(helper_fixture):
    report,root,captures=helper_fixture
    for index in range(10):
        if index==2:helper.grade_cold(report,2,'只在合成工程fixture中确认偏冷主光。')
        assert helper.next_stage(report)==0,report
        assert report['next_stage']==index+1
    assert report['status']=='scene-complete' and len(report['calls'])==10
    assert len(list((root/'finals').glob('*.json')))==10
    assert report['actual_reopen_after_gap']==dict(requests=0,same_identity=True,same_state=True,feedback_outside_recent=True)
    assert report['stages'][0]['zero_source_selection']=='committed'
    assert all(row['requests']==1 and row['audit_matches_final'] for row in report['stages'])
    with pytest.raises(RuntimeError,match='cannot-resend'):helper.next_stage(report)
    assert sum(c.total for c in captures)==10


def test_reserved_attempt_cannot_resend_and_inspection_is_zero_transport(helper_fixture):
    report,_,captures=helper_fixture
    report.update(status='attempt-reserved')
    report['stages'].append(dict(index=0,stage='initial-source',status='started',nonce='s150-test-reserved-nonce',expected_revision=0))
    with pytest.raises(RuntimeError,match='cannot-resend'):helper.next_stage(report)
    helper.inspect(report)
    assert not any(c.total for c in captures)
    assert report['readonly_inspection']['requests']==0


def test_first_technical_failure_stops_scene_without_retry_or_new_nonce(helper_fixture,monkeypatch):
    report,root,captures=helper_fixture
    original=helper.evidence.CapturingTransport
    def capture(*args,**kwargs):
        value=original(*args,**kwargs);value.inner.fault='blank';return value
    monkeypatch.setattr(helper.evidence,'CapturingTransport',capture)
    assert helper.next_stage(report)==2
    assert report['status']=='first-stage-failed' and len(report['stages'])==1
    assert (root/'finals/initial-source.json').is_file()
    with pytest.raises(RuntimeError,match='cannot-resend'):helper.next_stage(report)
    assert sum(c.total for c in captures)==1


def test_close_failure_is_persisted_terminal_and_cannot_start_next_stage(helper_fixture,monkeypatch):
    report,_,captures=helper_fixture
    original=helper.opening
    class ClosingFailure:
        def __init__(self,product):self.product=product
        def __getattr__(self,name):return getattr(self.product,name)
        def close(self):
            self.product.close()
            raise OSError('Synthetic close failure after actual close')
    monkeypatch.setattr(helper,'opening',lambda *args:ClosingFailure(original(*args)))
    assert helper.next_stage(report)==2
    assert report['status']=='first-stage-failed' and report['failure_code']=='product-close-failed'
    with pytest.raises(RuntimeError,match='cannot-resend'):helper.next_stage(report)
    assert sum(c.total for c in captures)==1
