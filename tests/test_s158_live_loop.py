"""Bounded S158 runner behavior with synthetic LOCAL proposals, no credentials."""
from hashlib import sha256
import json
from pathlib import Path
import sys
import pytest

from test_original_whole_chat import approved, personality_fixture, model_fixture
from test_integrated_character import integrated_fixture, LocalAdapter
from test_living_activity import control
from dynamic_subject_agent.model_gateway import ModelResult, ModelTaskKind
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.shared_activity import digest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_s158_live_loop as helper

PLAN=dict(subject='雨后蕨庭',composition='蕨庭的长凳靠门，人物伸手托住滴水的叶片，视点略低。',focus='观察指尖和叶片的距离')


@pytest.fixture
def loop_fixture(integrated_fixture,monkeypatch,tmp_path):
    root=tmp_path/'first';root.mkdir()
    monkeypatch.setattr(helper,'ROOT',root)
    captures=[];audits=[];options=dict(fail=False,share=True,plan=PLAN)
    class Capture:
        def __init__(self,report,blocked=False):
            self.report,self.blocked,self.total,self.expected,self.final=report,blocked,0,None,None
            captures.append(self)
        def arm(self,label,wire):self.expected=dict(label=label,wire_sha256=sha256(wire).hexdigest())
    class Adapter(LocalAdapter):
        def __init__(self,transport):super().__init__();self.transport=transport
        def invoke(self,task):
            t=self.transport
            assert not t.blocked and t.expected
            assert t.expected['wire_sha256']==helper.integrated_remote_request_preview(task)['wire_sha256']
            label=t.expected['label'];t.expected=None;t.total+=1
            t.report['calls'].append(dict(label=label,status='synthetic'))
            data=task.payload['payload']
            if options['fail']:
                t.final='';helper.save(root/'finals'/(label+'.json'),dict(final=''),exclusive=True)
                audits.append(dict(status='failed-closed'))
                raise ValueError('synthetic provider failure')
            if task.kind is ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK:
                message=data['turn']['current_message']
                value=dict(intent='revise' if message.startswith('把所有“') else 'clarify' if message==helper.STAGES[3][1] else 'chat',reply_text='合成：仅依据实际方案回复。')
            elif task.kind is ModelTaskKind.LIVING_ACTIVITY_SHARE:
                value=dict(share=options['share'],reply_text='合成分享：我想画托住叶片的手。' if options['share'] else '',language='zh')
            else:
                current=data['current_plan']
                value=dict(action='start' if current is None else 'revise',plan=options['plan'] if current is None else dict(current,focus='让指尖和水珠的间隔更清楚'),
                    reason_code='improve-readability',basis_refs=['E1'] if data['shared_experience'] else [],decision_note='合成具体取舍。')
            t.final=canonical_json(value)
            helper.save(root/'finals'/(label+'.json'),dict(final=t.final),exclusive=True)
            helper.normalized(value,task.payload,task.kind)
            audits.append(dict(status='complete',request_digest=digest(task.payload),output_digest=digest(value)))
            helper.persist(t.report)
            return ModelResult(task.kind,value)
    monkeypatch.setattr(helper.evidence,'CapturingTransport',Capture)
    monkeypatch.setattr(helper,'audit',lambda:list(audits))
    monkeypatch.setattr(helper,'audit_readonly',lambda:list(audits))
    monkeypatch.setattr(helper,'opening',lambda report,transport:integrated_fixture(Adapter(transport)))
    report=dict(status='ready',next_stage=0,calls=[],stages=[],provider_observations=[],checks={},human_content_reviews={},credential_read_attempts=0,automatic_retries=0)
    with integrated_fixture() as product:
        assert control(product,paused=False,sharing=True).status=='committed'
        report.update(profile_id=product.profile_id,timeline_id=product.timeline_id)
    yield report,captures,options


def test_full_short_loop_continues_without_claiming_long_or_person_effect(loop_fixture):
    report,captures,_=loop_fixture
    for _ in helper.STAGES:assert helper.next_stage(report)==0,report
    assert report['status']=='execution-ended-semantic-review-required'
    assert sum(x.total for x in captures)==11 and len(report['calls'])==11
    assert report['long_distance']==dict(eligible=False,status='not-tested-this-scene')
    assert all(report['checks'].values())
    assert report['final_view']['activity_revision']==3
    assert report['checks']['same_identity_reopened_zero_calls']
    with pytest.raises(RuntimeError):helper.next_stage(report)


def test_first_failure_keeps_raw_terminal_and_inspect_never_opens(loop_fixture,monkeypatch):
    report,captures,options=loop_fixture;options['fail']=True
    assert helper.next_stage(report)==2
    assert report['status']=='bounded-terminal' and len(report['calls'])==1
    saved=(helper.ROOT/'finals/initial-chat.json').read_bytes()
    monkeypatch.setattr(helper,'opening',lambda *a:pytest.fail('inspect or repeated first attempt opened product'))
    with pytest.raises(RuntimeError):helper.next_stage(report)
    inspected=helper.inspect(report)
    assert inspected['inspection_requests']==0 and inspected['product_opened'] is False
    assert (helper.ROOT/'finals/initial-chat.json').read_bytes()==saved
    assert sum(x.total for x in captures)==1


def test_reserved_attempt_survives_stale_metadata_without_open(loop_fixture,monkeypatch):
    report,captures,_=loop_fixture
    helper.save(helper.ROOT/'attempts/00.json',dict(status='reserved'),exclusive=True)
    monkeypatch.setattr(helper,'opening',lambda *a:pytest.fail('reserved attempt opened product'))
    with pytest.raises(RuntimeError,match='existing-first-attempt-preserved'):helper.next_stage(report)
    assert not captures and not report['calls']


def test_nine_targets_not_pruned_and_frozen_fallback_only():
    plan=dict(PLAN,subject='蕨庭'*9,composition='温室留着水珠。')
    result=helper.derive_feedback(plan)
    assert result['old']=='温室' and result['occurrences']==1
    assert result['expected_plan']['subject']==plan['subject']
    assert helper.derive_feedback(dict(plan,composition='只写叶片。')) is None


def test_long_qualification_uses_same_field_actual_span():
    plan=dict(PLAN,subject='雨后场景',composition='蕨庭近处。'+'保留手部动作和水珠，远处保持空白。'*12+'蕨庭远处。')
    result=helper.derive_feedback(plan)
    assert result['long_eligible'] and result['spans']['composition']>160
    assert len(result['edits'])<=4
    assert result['expected_plan']=={key:text.replace('蕨庭','叶庭') for key,text in plan.items()}


def test_no_share_is_valid_evidence_but_cannot_grade_full_effect(loop_fixture):
    report,_,options=loop_fixture;options['share']=False
    for _ in helper.STAGES:assert helper.next_stage(report)==0,report
    assert report['checks']['first-share_delivered'] is False
    scores={name:dict(score=2,note='合成测试：记录不是人物证据。') for name in helper.SCORES}
    helper.grade(report,scores)
    assert report['status']=='scene-effect-not-met'
    with pytest.raises(RuntimeError):helper.grade(report,scores)


def test_inspection_verifies_audit_without_writer_or_recovery(tmp_path,monkeypatch):
    from dynamic_subject_agent.integrated_character_live import open_integrated_character_audit, IntegratedCharacterCallAudit
    root=tmp_path/'readonly';root.mkdir()
    monkeypatch.setattr(helper,'ROOT',root)
    open_integrated_character_audit(root/'audit',initialize=True)
    before={str(p):sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
    monkeypatch.setattr(IntegratedCharacterCallAudit,'__init__',lambda *a,**k:pytest.fail('read-only inspect constructed audit writer'))
    assert helper.audit_readonly()==[]
    assert before=={str(p):sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
