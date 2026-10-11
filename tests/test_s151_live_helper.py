import json
from hashlib import sha256
from pathlib import Path
import sys
import pytest

from test_original_whole_chat import approved,personality_fixture,model_fixture
from test_natural_feedback_live import feedback_live_fixture
from test_natural_feedback_budget import budget_options
from dynamic_subject_agent.local_product import open_natural_feedback_product_live
from dynamic_subject_agent.natural_feedback_live import open_natural_feedback_audit
from dynamic_subject_agent.deepseek import DeepSeekTransport,DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_s151_live_continuity as helper

SPACE=dict(subject='原创画者桌边',composition='主体在右侧，左侧大片干净留白。视点平视，主光从窗边落下。前景一本合上的书。',focus='可爱轮廓')

@pytest.fixture
def s151_helper_fixture(feedback_live_fixture,monkeypatch,tmp_path):
    _,config,options,_=feedback_live_fixture;opts=budget_options(options)
    root=tmp_path/'new-first';root.mkdir()
    monkeypatch.setattr(helper,'ROOT',root);monkeypatch.setattr(helper.evidence,'ROOT',root)
    monkeypatch.setattr(helper,'verify_diagnostic_eligibility',lambda:None)
    monkeypatch.setattr(helper,'audit',lambda:list(open_natural_feedback_audit(opts['audit_path'],technical_variant='direct-final').snapshot()))
    captures=[]
    class Capture(DeepSeekTransport):
        def __init__(self,report,blocked=False):self.report=report;self.blocked=blocked;self.total=0;self.expected=None;self.final=None;self.fail=False;captures.append(self)
        def arm(self,label,wire):self.expected=dict(label=label,wire_sha256=sha256(wire).hexdigest())
        def post_json(self,**kwargs):
            assert not self.blocked and self.expected is not None
            body=json.loads(kwargs['body']);p=json.loads(body['messages'][1]['content'])
            assert sha256(kwargs['body']).hexdigest()==self.expected['wire_sha256']
            self.total+=1;self.report['calls'].append(dict(self.expected,status='received'))
            if 'current_activity' in p:
                assert body['thinking']['type']=='enabled'
                current=p['current_plan'];value=dict(action='start' if current is None else 'revise',
                    plan=SPACE if current is None else dict(current,focus='主体与明暗关系'),reason_code='improve-readability',
                    basis_refs=['E1'] if p['shared_experience'] else [],decision_note='合成自身活动取舍。')
            else:
                assert body['thinking']['type']=='disabled' and 'reasoning_effort' not in body
                message=p['turn']['current_message'];intent='revise' if message==helper.STAGES[2][1] else 'clarify' if message==helper.STAGES[3][1] else 'chat'
                edits=[dict(field='composition',before='左侧大片干净留白',after='左侧浅灰细纹理背景')] if intent=='revise' else []
                value=dict(intent=intent,activity_revision=p['activity_revision'],edits=edits,reason_code='improve-readability' if edits else None,
                    reply_text='合成空间纹理接话。',language='zh')
            self.final='' if self.fail else canonical_json(value)
            helper.evidence.save(root/'finals'/(self.expected['label']+'.json'),dict(final=self.final));self.expected=None;helper.save(self.report)
            return DeepSeekHttpResponse(200,canonical_json(dict(model='deepseek-flash',choices=[dict(finish_reason='length' if self.fail else 'stop',
                message=dict(role='assistant',content=self.final))],usage=dict(prompt_tokens=100,completion_tokens=4096 if self.fail else 80,
                total_tokens=4196 if self.fail else 180,completion_tokens_details=dict(reasoning_tokens=0)))).encode())
    monkeypatch.setattr(helper.evidence,'CapturingTransport',Capture)
    opened=[]
    def opening(report,transport):
        product=open_natural_feedback_product_live(config,**opts,_transport=transport,observations=report['provider_observations'])
        opened.append(product);return product
    monkeypatch.setattr(helper,'opening',opening)
    report=dict(status='ready',next_stage=0,calls=[],stages=[],credential_read_attempts=0,automatic_retries=0,human_content_reviews={},provider_observations=[])
    yield report,captures
    for product in opened:product.close()

def test_new_space_scene_exact10_patch_noop_topics_actual_reopen_and_new_activity(s151_helper_fixture):
    report,captures=s151_helper_fixture
    for index in range(10):
        if index==2:helper.grade_space(report,2,'仅合成工程：明确左侧干净留白。')
        assert helper.next_stage(report)==0,report
    assert report['status']=='scene-complete' and len(report['calls'])==10
    assert [r['after']['activity_revision'] for r in report['stages']]==[0,1,2,2,2,2,2,2,3,3]
    assert report['final_view']['current_plan']['composition']==SPACE['composition'].replace('左侧大片干净留白','左侧浅灰细纹理背景')
    assert report['final_view']['current_plan']['subject']==SPACE['subject']
    assert report['actual_reopen_after_gap']['requests']==0
    assert all(row['finish_reason']=='stop' for row in report['provider_observations'])
    with pytest.raises(RuntimeError):helper.next_stage(report)
    assert sum(c.total for c in captures)==10

def test_new_scene_truncation_stops_one_attempt_no_retry(s151_helper_fixture,monkeypatch):
    report,captures=s151_helper_fixture;original=helper.evidence.CapturingTransport
    def failed(*args,**kwargs):c=original(*args,**kwargs);c.fail=True;return c
    monkeypatch.setattr(helper.evidence,'CapturingTransport',failed)
    assert helper.next_stage(report)==2 and report['status']=='first-stage-failed'
    with pytest.raises(RuntimeError):helper.next_stage(report)
    assert sum(c.total for c in captures)==1

def test_missing_diagnostic_gate_refuses_before_any_model_or_opening(s151_helper_fixture,monkeypatch,tmp_path):
    report,captures=s151_helper_fixture
    # Restore the real function from a fresh module binding without opening.
    import importlib.util
    spec=importlib.util.spec_from_file_location('s151_gate_readonly',Path(helper.__file__))
    fresh=importlib.util.module_from_spec(spec);spec.loader.exec_module(fresh)
    monkeypatch.setattr(fresh,'DIAGNOSTIC_ROOT',tmp_path/'not-yet-run')
    monkeypatch.setattr(helper,'verify_diagnostic_eligibility',fresh.verify_diagnostic_eligibility)
    with pytest.raises(RuntimeError,match='eligibility-required'):helper.next_stage(report)
    assert not captures and not report['calls']
