"""Independent sealed objects reuse canonical LOCAL experience/activity ports."""
import json
from dataclasses import replace

import pytest

from test_reviewed_character_identity import approved, personality_fixture, model_fixture
from test_original_whole_chat import send, history
from dynamic_subject_agent.local_product import open_living_activity_product_local
from dynamic_subject_agent.model_gateway import ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelGateway, ModelResult, ModelTaskKind
from dynamic_subject_agent.shared_activity import SharedExperienceRequest
from dynamic_subject_agent.living_activity import LivingActionRequest, LivingControlRequest


class Adapter(ProviderAdapter):
    capabilities = ProviderCapabilities('independent-local-fixture', 'deterministic-test', True, (StructuredOutputMode.JSON_OBJECT,))
    def __init__(self): self.calls = []
    def invoke(self, task):
        self.calls.append(task)
        if task.kind is ModelTaskKind.LIVING_ACTIVITY_REPLY:
            value = dict(reply_text='合成接续。', language='zh')
        elif task.kind is ModelTaskKind.LIVING_ACTIVITY_SHARE:
            value = dict(share=True, reply_text='我把笔记的条目分成外观和待核问题两栏。', language='zh')
        else:
            payload = task.payload['payload']; action = payload['current_activity']['allowed_actions'][0]
            value = dict(action=action, plan=dict(subject='药草笔记文字方案', composition='外观与待核问题分栏'+str(len(self.calls)), focus='留待核实')
                if action in ('start', 'revise') else None, reason_code='improve-readability',
                basis_refs=['E1'] if payload['shared_experience'] else [], decision_note='只整理条目结构。')
        return ModelResult(task.kind, value)


@pytest.fixture
def independent(approved):
    author, config, request, view = approved
    frozen = author.application.freeze_source_identity(request)
    assert frozen.status == 'created'; author.close()
    asset = json.loads(view.runtime_asset_json)
    binding = dict(definition_basis=view.definition_basis, runtime_asset_sha=view.runtime_asset_sha,
        persona_digest=asset['persona_digest'], review_basis='1'*64, scope_digest='2'*64,
        subject_id=asset['subject']['subject_id'], anchor_id=asset['anchor']['anchor_id'])
    opened = []
    def opening(adapter=None, **kwargs):
        result = open_living_activity_product_local(config, gateway=ModelGateway(adapter or Adapter()),
            identity_id=frozen.view.identity_id, binding=binding, activity_kind='herb-note-outline', **kwargs)
        opened.append(result); return result
    opening.config, opening.binding = config, binding
    yield opening
    for product in opened: product.close()


def select(p, quote, head, key):
    s = p.application.query_shared_activity()
    return p.application.set_shared_experience(SharedExperienceRequest(p.profile_id, p.timeline_id, key, s.view['revision'], head, quote, True))


def enable(p):
    s = p.application.query_living_controls()
    return p.application.set_living_controls(LivingControlRequest(p.profile_id, p.timeline_id, 'independent-enable-1',
        s.view['revision'], False, True, True))


def act(p, key, action='simulation'):
    s = p.application.query_living_activity()
    return p.application.advance_living_activity(LivingActionRequest(p.profile_id, p.timeline_id,key,s.view['revision'],action))


def test_independent_experience_reopen_correction_and_end(independent):
    a=Adapter();p=independent(a)
    assert send(p,'合成陈述：我偏好分栏。','source-1').status=='terminal'
    assert select(p,'我偏好分栏',1,'independent-select-1').status=='committed'
    for i in range(3): assert send(p,'无关合成话题'+str(i),'unrelated-'+str(i)).status=='terminal'
    saved=history(p);scope=p.profile_id,p.timeline_id;p.close()
    fresh=Adapter();p=independent(fresh)
    assert (p.profile_id,p.timeline_id)==scope and history(p)==saved and not fresh.calls
    payload=p.application.preview_living_activity('reply','接着说。').view['payload']
    assert payload['evidence']['shared_experience']==dict(label='E1',quote='我偏好分栏')
    assert send(p,'修正：我现在偏好按问题排列。','correction-1').status=='terminal'
    head=history(p)[-1].head_sequence
    assert select(p,'我现在偏好按问题排列',head,'independent-correct-1').status=='committed'
    assert p.application.preview_living_activity('reply','接着说。').view['payload']['evidence']['shared_experience']['quote']=='我现在偏好按问题排列'
    assert select(p,'',None,'independent-end-1').status=='committed'
    assert p.application.preview_living_activity('reply','新话题。').view['payload']['evidence']['shared_experience'] is None
    assert len(history(p))==5


def test_uncommitted_assistant_or_stale_source_rejected_without_generation(independent):
    a=Adapter();p=independent(a);assert send(p,'合成用户原话。','source-1').status=='terminal'
    for quote, head in [('合成接续',1),('合成用户原话',99)]:
        assert select(p,quote,head,'independent-invalid-'+str(head)).status=='unavailable'
    s=p.application.query_shared_activity();r=SharedExperienceRequest(p.profile_id,p.timeline_id,'independent-stale-1',s.view['revision'],'', '',True)
    assert select(p,'合成用户原话',1,'independent-valid-1').status=='committed'
    assert p.application.set_shared_experience(replace(r,source_head_sequence=1,quote='合成用户原话')).status=='conflict'
    assert len(a.calls)==1


def test_herb_outline_actual_publication_share_and_reopen(independent):
    a=Adapter();p=independent(a)
    assert act(p,'independent-paused-1').status=='no-op' and not a.calls
    assert enable(p).status=='committed'
    preview=p.application.preview_living_activity('choice');assert preview.status=='previewed',preview
    assert '药草笔记' in preview.view['policy'] and '剂量' in preview.view['policy']
    assert preview.view['payload']['background']['encounter'][0]=='本地隔离的角色活动验证'
    assert act(p,'independent-step-1').status=='committed'
    assert a.calls[-1].payload==preview.view
    assert act(p,'independent-share-1','share').status=='committed'
    s=p.application.query_living_activity().view;assert len(s['shares'])==1
    p.close();fresh=Adapter();p=independent(fresh);assert not fresh.calls
    assert p.application.query_living_activity().view['shares']==s['shares']
    assert send(p,'这份编排下一步怎么调整？','followup-1').status=='terminal'
    assert fresh.calls[-1].payload['payload']['evidence']['latest_share']['text']==s['shares'][0]['text']


def test_independent_binding_never_grants_remote_use(independent):
    from dynamic_subject_agent.original_whole_chat import whole_contract
    from dynamic_subject_agent.local_activity_contract import local_whole_contract
    with pytest.raises(ValueError): whole_contract(independent.binding)
    from dynamic_subject_agent.shared_activity_live import shared_live_contract
    from dynamic_subject_agent.living_activity_live import living_live_contract, living_final_text_contract
    for builder in (shared_live_contract, living_live_contract, living_final_text_contract):
        with pytest.raises(ValueError): builder(independent.binding)
    class Remote(Adapter): capabilities=replace(Adapter.capabilities, local=False)
    before=independent.config.state_path.read_bytes()
    with pytest.raises(ValueError,match='LOCAL-only'):
        open_living_activity_product_local(independent.config,gateway=ModelGateway(Remote()),identity_id=None,
            binding=independent.binding,activity_kind='herb-note-outline')
    assert independent.config.state_path.read_bytes()==before
    c=local_whole_contract(independent.binding,technical_variant='grounded')
    assert c['provider']=='local' and c['credential_use']=='none'
    from dynamic_subject_agent.original_whole_chat import contract_variant
    with pytest.raises(ValueError): contract_variant(dict(c,provider='deepseek'))
