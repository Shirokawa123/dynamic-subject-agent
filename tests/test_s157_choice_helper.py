import json,sys
from hashlib import sha256
from pathlib import Path
import pytest
from test_natural_feedback_chat_entry import natural_entry_setup,entry_setup
from test_original_whole_chat import approved,personality_fixture,model_fixture
from dynamic_subject_agent.deepseek import DeepSeekTransport,DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_s157_choice_diagnostic as helper

@pytest.fixture
def six_fixture(natural_entry_setup,monkeypatch,tmp_path):
    script,_,_,options,_=natural_entry_setup
    root=tmp_path/'fixed-six'
    monkeypatch.setattr(helper,'ROOT',root);monkeypatch.setattr(helper.evidence,'ROOT',root)
    monkeypatch.setattr(helper,'PACKAGE',options['package_path']);monkeypatch.setattr(helper,'APPROVED_BINDING',script.APPROVED_BINDING)
    captures=[]
    class Capture(DeepSeekTransport):
        fault=None
        def __init__(self,report,blocked=False):self.report=report;self.blocked=blocked;self.total=0;self.expected=None;self.final=None;captures.append(self)
        def arm(self,label,wire):self.expected=dict(label=label,wire_sha256=sha256(wire).hexdigest())
        def post_json(self,**kwargs):
            assert not self.blocked and self.expected and sha256(kwargs['body']).hexdigest()==self.expected['wire_sha256']
            expected=self.expected;self.expected=None;self.total+=1;self.report['calls'].append(dict(expected,status='received'))
            if self.fault=='unknown' and expected['label']=='B-final':raise TimeoutError('Synthetic unknown')
            if self.fault=='http-401' and expected['label']=='A-high':
                self.report['calls'][-1]['response_sha256']=sha256(b'{"error":"synthetic"}').hexdigest();helper.save(self.report)
                return DeepSeekHttpResponse(401,b'{"error":"synthetic"}')
            body=json.loads(kwargs['body']);p=json.loads(body['messages'][1]['content'])
            length=self.fault=='length' and expected['label'].endswith('high')
            unavailable=self.fault=='no-final' and expected['label'].endswith('high')
            plan=dict(subject='云匣中的原创少女',composition='云匣工作台上展开旧地图，平视中景，门外冷光落在纸角。',focus='纸角的光线') if p['current_plan'] is None else dict(p['current_plan'],composition=p['current_plan']['composition']+'木箱稍向前。')
            value=dict(action='start' if p['current_plan'] is None else 'revise',plan=plan,reason_code='try-alternative',basis_refs=['E1'],decision_note='合成具体取舍。')
            self.final=None if unavailable else '' if length else canonical_json(value)
            if self.final is not None:helper.evidence.save(root/'finals'/(expected['label']+'.json'),dict(final=self.final))
            response=canonical_json(dict(model='deepseek-flash',choices=[dict(finish_reason='length' if length else 'stop',message=dict(role='assistant',content=self.final))],
                usage=dict(prompt_tokens=100,completion_tokens=4096 if length else 100 if expected['label'].endswith('final') else 200,total_tokens=4196 if length else 300))).encode()
            self.report['calls'][-1]['response_sha256']=sha256(response).hexdigest();helper.save(self.report)
            return DeepSeekHttpResponse(200,response)
    monkeypatch.setattr(helper.evidence,'CapturingTransport',Capture)
    helper.prepare()
    helper.seal()
    return root,captures,Capture

def test_fixed_six_same_sources_no_publication_and_selected_verdict_is_bound(six_fixture):
    root,captures,_=six_fixture
    helper.run();m=json.loads((root/'metadata.json').read_text(encoding='utf-8'))
    assert m['status']=='fixed-six-cells-complete' and len(m['calls'])==6 and m['diagnostic_publications']==0
    helper.evaluate({a+'-'+b:2 for a,b in helper.ORDER},'仅合成结果全部2，不当人物效果。')
    assert helper.eligible_variant()=='choice-final'
    with pytest.raises(RuntimeError):helper.run()
    with pytest.raises(RuntimeError):helper.evaluate({a+'-'+b:2 for a,b in helper.ORDER},'不可覆盖。')
    assert sum(c.total for c in captures)==6

def test_known_length_cells_are_preserved_not_retried_and_other_fixed_cells_complete(six_fixture):
    root,captures,cls=six_fixture;cls.fault='length'
    helper.run();m=json.loads((root/'metadata.json').read_text(encoding='utf-8'))
    assert m['status']=='fixed-six-cells-complete' and len(m['calls'])==6
    assert [c['status'] for c in m['cells']]==['failed','complete','complete','complete','complete','failed']
    assert sum(c.total for c in captures)==6

def test_unknown_delivery_stops_matrix_and_cannot_resend(six_fixture):
    root,captures,cls=six_fixture;cls.fault='unknown'
    helper.run();m=json.loads((root/'metadata.json').read_text(encoding='utf-8'))
    assert m['status']=='six-cell-blocked' and len(m['calls'])==4 and m['not_executed']==['B-low','B-high']
    with pytest.raises(RuntimeError):helper.run()
    assert sum(c.total for c in captures)==4

def test_changed_canonical_source_stops_before_remote_claim(six_fixture):
    root,captures,_=six_fixture
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'));state=Path(manifest['states']['A'])
    state.write_text(state.read_text(encoding='utf-8')+' ',encoding='utf-8')
    with pytest.raises(RuntimeError):helper.run()
    assert not captures

def test_failed_nonstring_final_is_bound_without_blocking_eligible_other_modes(six_fixture):
    root,captures,cls=six_fixture;cls.fault='no-final'
    helper.run()
    scores={a+'-'+b:0 if b=='high' else 2 for a,b in helper.ORDER}
    helper.evaluate(scores,'合成high没有可提取final，保缺失；两候选完整。')
    assert helper.eligible_variant()=='choice-final' and sum(c.total for c in captures)==6
    v=json.loads((root/'eligibility.json').read_text(encoding='utf-8'))
    assert v['first_final_bindings']['A-high']['status']=='unavailable' and not (root/'finals/A-high.json').exists()
    (root/'finals/A-high.json').write_text('{}',encoding='utf-8')
    with pytest.raises(RuntimeError):helper.eligible_variant()

def test_http_unavailable_stops_entire_matrix_without_trying_other_modes(six_fixture):
    root,captures,cls=six_fixture;cls.fault='http-401'
    helper.run();m=json.loads((root/'metadata.json').read_text(encoding='utf-8'))
    assert m['status']=='six-cell-blocked' and m['cells'][0]['failure_code']=='http-401' and len(m['calls'])==1
    assert len(m['not_executed'])==5 and sum(c.total for c in captures)==1
    with pytest.raises(RuntimeError):helper.run()
