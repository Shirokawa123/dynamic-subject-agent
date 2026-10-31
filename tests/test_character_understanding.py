from copy import deepcopy
from dataclasses import replace
import json
import pytest
from dynamic_subject_agent.character_understanding import propose_understanding,validate_understanding,reply_from_understanding,reply_projection
from dynamic_subject_agent.model_gateway import ModelGateway,ModelTaskKind,ModelResult,ProviderAdapter,ProviderCapabilities,StructuredOutputMode


def material(name='甲'):
    return dict(target=name,starting_point='材料之后的新交流；没有已发生的新活动',source_scenes=[
        dict(label='S1',lines=[dict(label='L1',speaker='other',text='你总能想到办法。'),
            dict(label='L2',speaker='character',text='先别急着下结论。我想再看看连接处。')]),
        dict(label='S2',lines=[dict(label='L3',speaker='character',text='这次平安过桥，就值得一起喝杯茶。')])])


def proposal():
    return dict(observations=[dict(statement='先检查再下结论',dimension='values',kind='interpretation',about=['甲'],
        evidence=[dict(label='L2',quote='先别急着下结论。')])],interpretations=[dict(title='谨慎判断',interpretation='重视实际检查',
        when='面对信息不足的判断',choice='先确认具体细节',expression='简短提出具体需要',limits='仅为两段材料支持的条件性解释',basis_refs=['O1'])])


class Adapter(ProviderAdapter):
    capabilities=ProviderCapabilities('synthetic-understanding','synthetic',True,(StructuredOutputMode.JSON_OBJECT,))
    def __init__(self):self.calls=[]
    def invoke(self,task):
        self.calls.append(deepcopy(task))
        if task.kind is ModelTaskKind.CHARACTER_SOURCE_UNDERSTANDING:value=proposal()
        else:value='合成：先确认具体细节。' if task.payload['understanding'] else '合成：直接根据材料回应。'
        return ModelResult(task.kind,value)


def test_same_facade_flow_uses_actual_model_proposal_in_reply_and_raw_baseline():
    from dynamic_subject_agent.application import ApplicationFacade
    adapter=Adapter();gateway=ModelGateway(adapter);source=material();before=deepcopy(source)
    understanding=ApplicationFacade.propose_character_understanding_local(gateway,source)
    assert understanding.status=='unreviewed-model-proposal'
    assert understanding.interpretations[0].basis=='model-proposed-interpretation'
    reply=ApplicationFacade.reply_from_character_understanding_local(gateway,source,'你怎么看？',understanding)
    baseline=ApplicationFacade.reply_from_character_understanding_local(gateway,source,'你怎么看？')
    assert reply.reply_text!=baseline.reply_text and not reply.persisted and reply.semantic_review=='required'
    assert adapter.calls[1].payload['understanding']['interpretations'][0]['choice']==proposal()['interpretations'][0]['choice']
    assert adapter.calls[2].payload['understanding'] is None
    assert adapter.calls[1].payload['source_scenes']==adapter.calls[2].payload['source_scenes']
    assert source==before


@pytest.mark.parametrize('bad',['quote','speaker','reference','time'])
def test_bad_evidence_or_invented_authority_never_becomes_understanding(bad):
    value=proposal()
    if bad=='quote':value['observations'][0]['evidence'][0]['quote']='不存在的原话'
    if bad=='speaker':value['observations'][0]['evidence']=[dict(label='L1',quote='你总能想到办法。')]
    if bad=='reference':value['interpretations'][0]['basis_refs']=['O9']
    if bad=='time':value['observations'][0]['knowledge_time']='now'
    with pytest.raises(ValueError):validate_understanding(material(),value)


def test_understanding_does_not_transfer_to_another_role_or_mutated_material():
    understanding=validate_understanding(material(),proposal())
    with pytest.raises(ValueError,match='different material'):reply_projection(material('乙'),'你好',understanding)
    value=replace(understanding,interpretations=())
    with pytest.raises(ValueError,match='changed'):reply_projection(material(),'你好',value)


def test_remote_gateway_not_usable_through_local_facade():
    from dynamic_subject_agent.application import ApplicationFacade
    class Remote(Adapter):capabilities=ProviderCapabilities('remote','synthetic',False,(StructuredOutputMode.JSON_OBJECT,))
    adapter=Remote()
    with pytest.raises(ValueError,match='LOCAL'):ApplicationFacade.propose_character_understanding_local(ModelGateway(adapter),material())
    assert not adapter.calls


def test_insufficient_material_has_no_invented_interpretation():
    result=validate_understanding(material(),dict(observations=[],interpretations=[]))
    assert result.status=='no-op' and not result.observations and not result.interpretations
    with pytest.raises(ValueError,match='no interpretation'):reply_projection(material(),'你好',result)
