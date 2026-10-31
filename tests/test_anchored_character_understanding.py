from copy import deepcopy
import pytest
from dynamic_subject_agent.anchored_character_understanding import validate_material,validate_understanding,reply_projection,understanding_coverage
from dynamic_subject_agent.model_gateway import ModelGateway,ModelResult,ModelTaskKind,ProviderAdapter,ProviderCapabilities,StructuredOutputMode


def material():
    return dict(target='甲',current_anchor=dict(description='修理之后的新交流',facts=[dict(label='A1',statement='先前松动的螺栓已经固定，当前没有新的故障记录。')]),
        source_scenes=[dict(label='S1',time_scope='before',lines=[dict(label='L1',speaker='other',text='是不是整座桥都坏了？'),dict(label='L2',speaker='character',text='先检查这颗松动的螺栓，再下结论。')]),
            dict(label='S2',time_scope='before',lines=[dict(label='L3',speaker='character',text='这次平安过桥就值得庆祝。')])])


def proposal():
    observations=[dict(statement='先检查再判断',dimension='values',kind='interpretation',about=['甲'],evidence=[dict(label='L2',quote='先检查这颗松动的螺栓')]),
        dict(statement='重视共同平安',dimension='values',kind='interpretation',about=['甲'],evidence=[dict(label='L3',quote='平安过桥就值得庆祝')])]
    return dict(scene_readings=[dict(scene_ref=f'S{i+1}',status='observed',observation=o,
        use_at_anchor='superseded_situation' if i==0 else 'possible_tendency',anchor_refs=['A1'] if i==0 else [],
        scope_note='原故障已经处理，可回顾检查过程。' if i==0 else '该场景体现一种条件性的关注。') for i,o in enumerate(observations)],
        interpretations=[dict(title='谨慎判断',interpretation='先核对实际问题',when='讨论不明情况时',choice='先核实再结论',
            expression='提出具体需要',limits='不能推断所有问题都必须先查螺栓',evidence=[dict(label='L2',quote='再下结论。')])])


def test_same_material_conditions_preserve_current_anchor_and_history():
    source=material();u=validate_understanding(source,proposal())
    a=reply_projection(source,'现在想聊什么？');b=reply_projection(source,'现在想聊什么？',u)
    assert a['current_anchor']==b['current_anchor']==source['current_anchor']
    assert a['source_scenes']==b['source_scenes']==source['source_scenes']
    assert a['understanding'] is None and b['understanding']['scene_readings'][0]['use_at_anchor']=='superseded_situation'
    assert understanding_coverage(source,u)['considered_scenes']==['S1','S2']


@pytest.mark.parametrize('bad',['missing-scene','unknown-anchor','missing-anchor-support','borrowed-scene-quote','nonexistent-direct-quote','old-observation-only-ref','other-only'])
def test_invalid_support_cannot_pass_as_anchored_understanding(bad):
    value=proposal()
    if bad=='missing-scene':value['scene_readings'].pop()
    if bad=='unknown-anchor':value['scene_readings'][0]['anchor_refs']=['A9']
    if bad=='missing-anchor-support':value['scene_readings'][0]['anchor_refs']=[]
    if bad=='borrowed-scene-quote':value['scene_readings'][0]['observation']['evidence']=[dict(label='L3',quote='平安过桥就值得庆祝')]
    if bad=='nonexistent-direct-quote':value['interpretations'][0]['evidence']=[dict(label='L2',quote='不存在的原话')]
    if bad=='old-observation-only-ref':value['interpretations'][0]['evidence']=[dict(label='O1',quote='先核实再结论')]
    if bad=='other-only':value['interpretations'][0]['evidence']=[dict(label='L1',quote='是不是整座桥都坏了？')]
    with pytest.raises(ValueError):validate_understanding(material(),value)


def test_scene_coverage_does_not_force_invented_observations():
    value=dict(scene_readings=[dict(scene_ref=s['label'],status='insufficient',observation=None,
        use_at_anchor='uncertain',anchor_refs=[],scope_note='尚不足以提出人物理解。') for s in material()['source_scenes']],interpretations=[])
    u=validate_understanding(material(),value)
    assert u.status=='no-op' and understanding_coverage(material(),u)['insufficient_scenes']==['S1','S2']


def test_changed_anchor_cannot_reuse_old_understanding_and_future_sources_are_ineligible():
    source=material();u=validate_understanding(source,proposal())
    changed=deepcopy(source);changed['current_anchor']['facts'][0]['statement']='尚未修复。'
    with pytest.raises(ValueError):reply_projection(changed,'接着聊',u)
    changed=deepcopy(source);changed['source_scenes'][0]['time_scope']='after'
    with pytest.raises(ValueError):validate_material(changed)


def test_facade_uses_model_readings_not_handwritten_role_rules():
    from dynamic_subject_agent.application import ApplicationFacade
    class Local(ProviderAdapter):
        capabilities=ProviderCapabilities('local','synthetic',True,(StructuredOutputMode.JSON_OBJECT,))
        def __init__(self):self.calls=[]
        def invoke(self,task):
            self.calls.append(deepcopy(task))
            return ModelResult(task.kind,proposal() if task.kind is ModelTaskKind.CHARACTER_SOURCE_UNDERSTANDING else '可以回顾当时的检查，现在的故障已经处理了。')
    adapter=Local();gateway=ModelGateway(adapter)
    u=ApplicationFacade.propose_anchored_character_understanding_local(gateway,material())
    result=ApplicationFacade.reply_from_anchored_character_understanding_local(gateway,material(),'想起以前那件事呢？',u)
    assert result.status=='candidate' and not result.persisted
    assert adapter.calls[-1].payload['understanding']['interpretations'][0]['evidence']==proposal()['interpretations'][0]['evidence']
