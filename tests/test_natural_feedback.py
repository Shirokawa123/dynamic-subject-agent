"""Facade behavior for LOCAL preparation; synthetic responses are not character evidence."""
import json
from dataclasses import asdict
import pytest

from test_original_whole_chat import approved, personality_fixture, model_fixture, send, history
from test_shared_activity import step_request, select, shared_fixture
from dynamic_subject_agent.local_product import open_natural_feedback_product_local
from dynamic_subject_agent.model_gateway import ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelGateway, ModelResult, ModelTaskKind

PLAN = dict(subject='人物文字构图', composition='半身侧视。左前方冷色主光照亮脸。枪在左下后景，枪口出画。背景压暗。', focus='先看表情')
FEEDBACK = '主光改暖，冷色只留一点边缘反光，其他照旧。'

class LocalAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities('local-feedback-fixture', 'synthetic', True, (StructuredOutputMode.JSON_OBJECT,))
    def __init__(self):
        self.calls = []
        self.override = None
        self.callback = None
    def invoke(self, task):
        self.calls.append(task)
        if self.callback:
            self.callback()
        if self.override is not None:
            return ModelResult(task.kind, self.override)
        payload = task.payload['payload']
        if task.kind is ModelTaskKind.SHARED_ACTIVITY_CHOICE:
            current = payload['current_plan']
            next_plan = dict(PLAN) if current is None else dict(current, focus='表情与明暗的清晰关系')
            action='start' if 'start' in payload['current_activity']['allowed_actions'] else 'revise'
            value = dict(action=action, plan=next_plan,
                reason_code='improve-readability', basis_refs=['E1'] if payload['shared_experience'] else [], decision_note='合成后续活动取舍。')
        else:
            message = payload['turn']['current_message']
            intent = 'revise' if message == FEEDBACK else 'clarify' if message == '暖一点。' else 'chat'
            edits = [dict(field='composition', before='冷色主光', after='暖色主光'),
                dict(field='composition', before='背景压暗。', after='背景压暗。冷色只留低亮边缘反光。')] if intent == 'revise' else []
            value = dict(intent=intent, activity_revision=payload['activity_revision'], edits=edits,
                reason_code='improve-readability' if edits else None,
                reply_text='合成局部修订回执。' if edits else '合成澄清：指主光还是背景？' if intent == 'clarify' else '合成接话。', language='zh')
        return ModelResult(task.kind, value)

@pytest.fixture
def feedback_fixture(approved, monkeypatch):
    author, config, request, view = approved
    frozen = author.application.freeze_source_identity(request)
    assert frozen.status == 'created'
    author.close()
    asset = json.loads(view.runtime_asset_json)
    import dynamic_subject_agent.original_whole_chat as module
    binding = dict(definition_basis=view.definition_basis, runtime_asset_sha=view.runtime_asset_sha,
        persona_digest=asset['persona_digest'], review_basis='1'*64, scope_digest='2'*64,
        subject_id=asset['subject']['subject_id'], anchor_id=asset['anchor']['anchor_id'])
    monkeypatch.setattr(module, 'APPROVED_BINDING', binding)
    opened=[]
    def opening(adapter=None):
        result=open_natural_feedback_product_local(config, gateway=ModelGateway(adapter or LocalAdapter()),
            identity_id=frozen.view.identity_id, binding=binding)
        opened.append(result)
        return result
    yield opening
    for product in opened:
        product.close()

def state(product):
    result=product.application.query_shared_activity()
    assert result.status == 'available', result
    return result.view

def started(feedback_fixture, with_source=False):
    adapter=LocalAdapter(); product=feedback_fixture(adapter)
    if with_source:
        assert send(product, '这一版用冷色主光。', 'feedback-early-source').status == 'terminal'
        assert select(product, '这一版用冷色主光。').status == 'committed'
    result=product.application.advance_shared_activity(step_request(product, 'feedback-initial-activity'))
    assert result.status == 'committed', result
    return product, adapter

def test_one_natural_message_revises_atomically_and_after_window_reopen_actual_activity_continues(feedback_fixture):
    product, adapter=started(feedback_fixture)
    before=state(product)['current_plan']
    preview=product.application.preview_natural_feedback(FEEDBACK)
    assert preview.status == 'previewed', preview
    result=send(product, FEEDBACK, 'feedback-message')
    assert result.status == 'terminal', (result, adapter.calls[-1].payload)
    assert adapter.calls[-1].payload == preview.view
    updated=state(product)['current_plan']
    assert updated.subject == before.subject and updated.focus == before.focus
    assert updated.composition == before.composition.replace('冷色主光','暖色主光') + '冷色只留低亮边缘反光。'
    assert state(product)['activity_revision'] == 2 and state(product)['result'].event.kind == 'revise'
    calls=len(adapter.calls)
    assert send(product, FEEDBACK, 'feedback-message').status == 'terminal'
    assert len(adapter.calls) == calls
    for i in range(3):
        assert send(product, '合成无关话题'+str(i), 'feedback-topic-gap-'+str(i)).status == 'terminal'
        assert state(product)['current_plan'] == updated
    latest=product.application.preview_natural_feedback('接着聊。').view['payload']['exchange']
    assert FEEDBACK not in json.dumps(latest, ensure_ascii=False)
    identity=(product.profile_id,product.timeline_id); saved=history(product);product.close()
    fresh=LocalAdapter(); product=feedback_fixture(fresh)
    assert (product.profile_id,product.timeline_id) == identity and history(product) == saved and not fresh.calls
    choice=product.application.preview_shared_activity_step()
    assert choice.view['payload']['current_feedback']['quote'] == FEEDBACK
    assert choice.view['payload']['current_plan'] == asdict(updated)
    result=product.application.advance_shared_activity(step_request(product,'feedback-post-gap-choice'))
    assert result.status == 'committed', result
    assert state(product)['activity_revision'] == 3
    assert state(product)['current_plan'].composition == updated.composition
    assert state(product)['current_plan'].focus != updated.focus
    assert send(product,'现在这一版怎样？','feedback-current-result').status == 'terminal'
    assert fresh.calls[-1].payload['payload']['current_plan'] == asdict(state(product)['current_plan'])

@pytest.mark.parametrize('message',['暖一点。','换个话题说故事。','如果改画夜景，可以加蓝光。'])
def test_ambiguous_unrelated_and_conditional_have_no_plan_effect(feedback_fixture,message):
    product, adapter=started(feedback_fixture)
    before=state(product)['current_plan']; revision=state(product)['activity_revision']
    assert send(product,message,'feedback-no-effect').status == 'terminal'
    assert state(product)['current_plan'] == before and state(product)['activity_revision'] == revision
    assert not adapter.calls[-1].payload['payload']['current_feedback']

@pytest.mark.parametrize('failure',['stale','absent','nonunique','duplicate','overlap','noop-effect','missing-plan'])
def test_invalid_proposal_never_commits_partial_or_false_success(feedback_fixture,failure):
    product, adapter=started(feedback_fixture)
    before=state(product)['current_plan']; length=len(history(product))
    proposal=dict(intent='revise',activity_revision=1,edits=[dict(field='composition',before='冷色主光',after='暖色主光')],
        reason_code='improve-readability',reply_text='合成候选，绝不应发表。',language='zh')
    if failure=='stale': proposal['activity_revision']=0
    if failure=='absent': proposal['edits'][0]['before']='不存在的原文'
    if failure=='nonunique': proposal['edits'][0]['before']='。'
    if failure=='duplicate': proposal['edits'].append(dict(proposal['edits'][0]))
    if failure=='overlap': proposal['edits'].append(dict(field='composition',before='左前方冷色主光',after='后方'))
    if failure=='noop-effect': proposal['intent']='chat'
    if failure=='missing-plan':
        product.application.set_reviewed_character_history(False)
    adapter.override=proposal
    result=send(product,FEEDBACK,'feedback-invalid-first')
    assert result.status == 'failed-closed', result
    assert len(history(product)) == length
    if failure!='missing-plan': assert state(product)['current_plan'] == before

@pytest.mark.parametrize('control',['disable','off','context','withdraw'])
def test_feedback_preserves_old_dependencies_and_privacy_invalidates_derived_plan(feedback_fixture,control):
    product, adapter=started(feedback_fixture, with_source=True)
    assert send(product,FEEDBACK,'feedback-dependent-message').status == 'terminal'
    assert len(state(product)['result'].source_dependencies) == 2
    if control=='disable': assert select(product,'',None,'feedback-disable').status == 'committed'
    elif control=='off': product.application.set_reviewed_character_history(False)
    elif control=='context':
        from dynamic_subject_agent.whole_context_boundary import WholeContextBoundaryRequest
        assert product.application.apply_whole_context_boundary(WholeContextBoundaryRequest(product.profile_id,product.timeline_id,'feedback-context',0,True)).status == 'committed'
    else:
        calls=len(adapter.calls)
        assert send(product,'不要再使用之前的聊天。','feedback-withdraw').status == 'failed-closed'
        assert len(adapter.calls)==calls
    product.close();fresh=LocalAdapter();product=feedback_fixture(fresh)
    assert not fresh.calls
    preview=product.application.preview_shared_activity_step()
    assert preview.status=='previewed', preview
    assert preview.view['payload']['current_plan'] is None and preview.view['payload']['current_feedback'] is None

@pytest.mark.parametrize('prepared',[False,True])
def test_feedback_cold_recovery_is_atomic_and_zero_model(feedback_fixture,monkeypatch,prepared):
    from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint, PublicationInterrupted
    product,adapter=started(feedback_fixture)
    with monkeypatch.context() as crash:
        if prepared:
            original=TimelineEngine._hit
            def hit(self,point):
                if point is FaultPoint.AFTER_PLAN_CLAIM: raise OSError('Synthetic interruption')
                return original(self,point)
            crash.setattr(TimelineEngine,'_hit',hit)
        else:
            crash.setattr(TimelineEngine,'publish',lambda *a,**kw: (_ for _ in ()).throw(PublicationInterrupted('synthetic','Before preparation')))
        send(product,FEEDBACK,'feedback-interrupted')
    assert len(adapter.calls)==2
    product.close();fresh=LocalAdapter();product=feedback_fixture(fresh)
    assert not fresh.calls and state(product)['activity_revision']==(2 if prepared else 1)
    replay=send(product,FEEDBACK,'feedback-interrupted')
    assert replay.status==('terminal' if prepared else 'failed-closed') and not fresh.calls

def test_old_shared_qualification_has_no_feedback_entry(shared_fixture):
    product=shared_fixture()
    assert product.application.preview_natural_feedback(FEEDBACK).status=='unavailable'

def test_exact_unsent_wire_matches_local_execution_and_pending_refuses_every_task(feedback_fixture):
    from dynamic_subject_agent.natural_feedback_remote_preview import (
        natural_feedback_remote_request_preview, PendingNaturalFeedbackGrant, UnapprovedNaturalFeedbackAdapter)
    from dynamic_subject_agent.model_gateway import ModelTask, ModelGatewayFailure
    from dynamic_subject_agent.frozen_attempt import canonical_json
    product,adapter=started(feedback_fixture)
    assert send(product,FEEDBACK,'feedback-wire-message').status=='terminal'
    assert send(product,'暖一点。','feedback-wire-clarify').status=='terminal'
    pending=ModelGateway(UnapprovedNaturalFeedbackAdapter(PendingNaturalFeedbackGrant('0'*64)))
    for task in adapter.calls:
        wire=natural_feedback_remote_request_preview(task)
        assert wire['body']['messages'][1]['content']==canonical_json(task.payload['payload'])
        assert wire['automatic_retries']==0 and wire['max_requests_per_action']==1
        with pytest.raises(ModelGatewayFailure,match='natural-feedback-use-unapproved'):pending.execute(task)
    with pytest.raises(ValueError,match='unapproved'):
        open_natural_feedback_product_local(None,gateway=pending,identity_id=product.profile_id)
    from copy import deepcopy
    bad=deepcopy(adapter.calls[-1].payload);bad['payload']['extra_private_data']='should refuse'
    with pytest.raises(ValueError): natural_feedback_remote_request_preview(ModelTask(ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK,bad))

def test_permission_change_during_proposal_never_publishes(feedback_fixture):
    product,adapter=started(feedback_fixture)
    before=len(history(product)); old=state(product)['current_plan']
    def change():
        assert product.application.set_reviewed_character_history(False).history_enabled is False
    adapter.callback=change
    result=send(product,FEEDBACK,'feedback-permission-race')
    assert result.status=='failed-closed'
    assert len(history(product))==before and state(product)['current_plan']==old
    assert state(product)['activity_revision']==1

def test_independent_new_plan_does_not_reintroduce_feedback_from_ineligible_prior_plan(feedback_fixture):
    product,adapter=started(feedback_fixture)
    assert send(product,FEEDBACK,'feedback-old-dependent').status=='terminal'
    assert product.application.set_reviewed_character_history(False).history_enabled is False
    assert state(product)['current_plan'] is None
    assert product.application.advance_shared_activity(step_request(product,'feedback-new-independent')).status=='committed'
    assert state(product)['result'].source_dependencies==()
    assert product.application.set_reviewed_character_history(True).history_enabled is True
    preview=product.application.preview_shared_activity_step()
    assert preview.view['payload']['current_feedback'] is None
    assert product.application.preview_natural_feedback('说说新方案。').view['payload']['current_feedback'] is None

def test_source_selected_after_independent_plan_still_taints_natural_revision(feedback_fixture):
    product,adapter=started(feedback_fixture)
    assert state(product)['result'].source_dependencies==()
    assert send(product,'这版考虑稍微降低边缘亮度。','feedback-late-e1-message').status=='terminal'
    head=history(product)[-1].head_sequence
    assert select(product,'这版考虑稍微降低边缘亮度。',head,'feedback-late-e1-selection').status=='committed'
    key=state(product)['source'].source_key
    assert product.application.preview_natural_feedback(FEEDBACK).view['payload']['evidence']['shared_experience'] is not None
    assert send(product,FEEDBACK,'feedback-after-late-e1').status=='terminal'
    assert key in state(product)['result'].source_dependencies
    assert len(state(product)['result'].source_dependencies)==2
    assert key in state(product)['decision'].source_dependencies
