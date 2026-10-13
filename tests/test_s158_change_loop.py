"""The new scene uses fake HTTPS, actual Facade evidence and one first attempt."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

from test_original_whole_chat import approved,personality_fixture,model_fixture
from test_integrated_character_live import integrated_live_fixture
from test_living_activity import control
from dynamic_subject_agent.deepseek import DeepSeekTransport,DeepSeekHttpResponse
from dynamic_subject_agent.model_gateway import ModelTask,ModelTaskKind

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_s158_change_loop as change

PLAN=dict(subject='旧电影院放映室',composition='门口小牌写映川。人物站在放映机旁，扶住胶片盒，光柱越过肩侧，右边留出暗处。',focus='先看手与胶片盒的距离')


@pytest.fixture
def change_loop(integrated_live_fixture,monkeypatch,tmp_path):
    from dynamic_subject_agent.integrated_character_live import ApprovedIntegratedCharacterGrant,APPROVED_CHANGE_REVIEW
    opening,_,settings,_=integrated_live_fixture
    root=tmp_path/'change-first';root.mkdir()
    settings['audit_path']=root/'audit'
    settings['grant']=ApprovedIntegratedCharacterGrant(APPROVED_CHANGE_REVIEW,True,technical_variant='change-evidence')
    monkeypatch.setattr(change,'ROOT',root)
    options=dict(fail=False,next_action='revise',plan=PLAN)
    captures=[]
    class Capture(DeepSeekTransport):
        def __init__(self,report,blocked=False):
            self.report,self.blocked,self.total,self.expected,self.final=report,blocked,0,None,None
            captures.append(self)
        def arm(self,label,wire):
            self.expected=dict(label=label,wire_sha256=sha256(wire).hexdigest())
        def post_json(self,**kwargs):
            assert not self.blocked and self.expected and self.total==0
            assert sha256(kwargs['body']).hexdigest()==self.expected['wire_sha256']
            label=self.expected['label'];self.expected=None;self.total+=1
            self.report['calls'].append(dict(label=label,status='synthetic'))
            body=json.loads(kwargs['body']);payload=json.loads(body['messages'][1]['content'])
            if 'turn' in payload:
                intent='revise' if payload['turn']['current_message'].startswith('把所有“') else 'chat'
                text='合成原文：只依据实际方案接话。'
                value=dict(intent=intent,reply_text=text)
                final=f'[{intent}]\n{text}' if '第一行只能是[revise]' in body['messages'][0]['content'] else text
            elif 'activity_result' in payload:
                value=dict(share=True,reply_text='合成分享：我想让扶胶片盒的手落在光柱边。',language='zh')
                final=change.engine.canonical_json(value)
            else:
                current=payload['current_plan'];action='start' if current is None else options['next_action']
                value=dict(action=action,plan=options['plan'] if current is None else dict(current,focus='让扶盒子的手转向光柱边缘') if action=='revise' else None,
                    reason_code='improve-readability',basis_refs=['E1'] if payload['shared_experience'] else [],decision_note='合成具体取舍。')
                final=change.engine.canonical_json(value)
            self.final='' if options['fail'] else final
            change.engine.save(root/'finals'/(label+'.json'),dict(final=self.final),exclusive=True)
            change.engine.persist(self.report)
            return DeepSeekHttpResponse(200,change.engine.canonical_json(dict(model='deepseek-flash',
                choices=[dict(finish_reason='stop',message=dict(role='assistant',content=self.final))],
                usage=dict(prompt_tokens=100,completion_tokens=40,total_tokens=140))).encode())
    monkeypatch.setattr(change.engine.evidence,'CapturingTransport',Capture)
    def open_product(report,transport):
        product=opening(transport,report['provider_observations'])
        assert (product.profile_id,product.timeline_id)==(report['profile_id'],report['timeline_id'])
        change.capture_change(report,product)
        return product
    monkeypatch.setattr(change,'opening',open_product)
    report=dict(status='ready',next_stage=0,calls=[],stages=[],provider_observations=[],checks={},
        human_content_reviews={},credential_read_attempts=0,automatic_retries=0)
    product=opening(Capture(report,blocked=True))
    assert control(product,paused=False,sharing=True).status=='committed'
    report.update(profile_id=product.profile_id,timeline_id=product.timeline_id)
    product.close()
    return report,captures,options


@pytest.mark.parametrize('next_action',['revise','defer'])
def test_full_wrapper_uses_same_actual_change_and_never_promotes_defer(change_loop,next_action):
    report,captures,options=change_loop;options['next_action']=next_action
    before_root=change.engine.ROOT
    with change.configured():
        for _ in change.STAGES:
            assert change.engine.next_stage(report)==0,report
        assert report['status']=='execution-ended-semantic-review-required'
        assert report['checks']['initial-chat_change_null']
        assert report['checks']['first-share_change_null']
        assert report['checks']['choice_change_omitted']
        assert report['checks']['same_identity_reopened_zero_calls']
        actual=next_action=='revise'
        assert report['checks']['actual_new_choice'] is actual
        assert report['checks']['new_revision_change_in_share_and_reply'] is actual
        assert sum(c.total for c in captures)==(11 if actual else 10)
        if actual:
            assert report['change_inputs']['second-share']==report['change_inputs']['faithful-reply']
            assert report['change_inputs']['second-share']['changes']==[
                dict(field='focus',before='先看手与胶片盒的距离',after='让扶盒子的手转向光柱边缘')]
        else:
            assert report['change_inputs']['faithful-reply'] is None
            assert report['stages'][9]['status']=='not-executed-gate'
            scores={name:dict(score=2,note='合成上限输入不能把暂缓当作新进展。') for name in change.engine.SCORES}
            change.engine.grade(report,scores)
            assert report['status']=='scene-effect-not-met'
        with pytest.raises(RuntimeError):change.engine.next_stage(report)
    assert change.engine.ROOT==before_root


def test_first_failure_and_missing_target_end_without_retry(change_loop,monkeypatch):
    report,captures,options=change_loop;options['fail']=True
    with change.configured():
        assert change.engine.next_stage(report)==2
        saved=(change.ROOT/'finals/initial-chat.json').read_bytes()
        monkeypatch.setattr(change.engine,'opening',lambda *args:pytest.fail('terminal reopened product'))
        with pytest.raises(RuntimeError):change.engine.next_stage(report)
        assert change.engine.inspect(report)['inspection_requests']==0
        assert (change.ROOT/'finals/initial-chat.json').read_bytes()==saved
        assert change.engine.derive_feedback(dict(PLAN,composition='门口只有空牌。')) is None
    assert report['status']=='bounded-terminal' and sum(c.total for c in captures)==1


def test_change_field_must_match_visible_evidence_and_choice_never_receives_it():
    report=dict(next_stage=0,checks={},change_views={'initial-chat':None})
    natural=ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK
    change.check_projection(ModelTask(natural,dict(payload=dict(current_result_change=None))),report)
    for payload in ({},dict(current_result_change=dict(action='revise'))):
        with pytest.raises(RuntimeError):change.check_projection(ModelTask(natural,dict(payload=payload)),report)
    choice=ModelTask(ModelTaskKind.LIVING_ACTIVITY_CHOICE,dict(payload=dict(current_result_change=None)))
    with pytest.raises(RuntimeError,match='choice-must-not'):change.check_projection(choice,report)
    report.update(next_stage=9,change_views={'second-share':dict(action='revise',changes=[],unexpanded_fields=['composition'])})
    expected=deepcopy(report['change_views']['second-share'])
    change.check_projection(ModelTask(ModelTaskKind.LIVING_ACTIVITY_SHARE,dict(payload=dict(current_result_change=expected))),report)
    expected['unexpanded_fields'].clear()
    assert report['change_inputs']['second-share']['unexpanded_fields']==['composition']


def test_scene_is_single_pair_ordinary_input_and_pins_its_own_sources():
    with change.configured():
        assert change.engine.PAIRS==(('映川','映汀'),) and len(change.engine.STAGES)==11
        assert len(change.engine.SOURCE)<=400 and '长距' not in change.engine.SOURCE and '字数' not in change.engine.SOURCE
        assert change.engine.derive_feedback(PLAN)['text']=='把所有“映川”换成“映汀”，其他照旧。'
        assert change.engine.derive_feedback(dict(PLAN,composition='映川'*9)) is None
        pins=change.engine.pins()
        for path in (Path(change.__file__),change.SCENE,change.REVIEW,Path(change.engine.__file__)):
            assert pins[str(path.relative_to(change.REPO))]==sha256(path.read_bytes()).hexdigest()
