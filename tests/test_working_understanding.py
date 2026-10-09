import json
from dataclasses import asdict, replace

import pytest

from test_original_whole_chat import approved, personality_fixture, model_fixture, send, history
from dynamic_subject_agent.local_product import open_working_understanding_product_local
from dynamic_subject_agent.model_gateway import (
    ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelGateway, ModelResult, ModelTaskKind,
    ModelGatewayFailure)
from dynamic_subject_agent.working_understanding import WorkingSourceQuote, WorkingUnderstandingRequest
from dynamic_subject_agent.shared_activity import SharedActivityStepRequest
from test_shared_activity import shared_fixture


class LocalAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities('local-working-fixture','fixed-synthetic',True,(StructuredOutputMode.JSON_OBJECT,))

    def __init__(self):
        self.calls=[]
        self.override=None
        self.callback=None

    def invoke(self, task):
        self.calls.append(task)
        if self.callback:
            self.callback()
        if self.override is not None:
            return ModelResult(task.kind,self.override)
        payload=task.payload['payload']
        if task.kind is ModelTaskKind.WORKING_UNDERSTANDING_FORM:
            value=dict(status='formed',scope='composition-text',statement='这次构图先试少量暖色和桌边留白。',basis_refs=['U1','U2'])
        elif task.kind is ModelTaskKind.WORKING_ACTIVITY_CHOICE:
            action=payload['current_activity']['allowed_actions'][0]
            understanding=payload['working_understanding']
            value=dict(action=action,plan=dict(subject='静物',composition='合成独立布局' if understanding is None else understanding['statement'],
                focus='光线') if action in ('start','revise') else None,reason_code='balance-space',
                basis_refs=[] if understanding is None else ['W1'],decision_note='仅本地的合成取舍说明。')
        else:
            result=payload['evidence']['activity_result']
            value=dict(reply_text='合成初聊。' if result is None else '合成接话：'+result['plan']['composition'],language='zh')
        return ModelResult(task.kind,value)


@pytest.fixture
def working_fixture(approved,monkeypatch):
    author,config,request,view=approved
    frozen=author.application.freeze_source_identity(request)
    assert frozen.status=='created'
    author.close()
    asset=json.loads(view.runtime_asset_json)
    import dynamic_subject_agent.original_whole_chat as module
    binding=dict(definition_basis=view.definition_basis,runtime_asset_sha=view.runtime_asset_sha,
        persona_digest=asset['persona_digest'],review_basis='1'*64,scope_digest='2'*64,
        subject_id=asset['subject']['subject_id'],anchor_id=asset['anchor']['anchor_id'])
    monkeypatch.setattr(module,'APPROVED_BINDING',binding)
    opened=[]
    def opening(adapter=None,day=None):
        result=open_working_understanding_product_local(config,gateway=ModelGateway(adapter or LocalAdapter()),
            identity_id=frozen.view.identity_id,binding=binding,day=day)
        opened.append(result)
        return result
    yield opening
    for product in opened:
        product.close()


def state(product):
    result=product.application.query_working_understanding()
    assert result.status=='available',result
    return result.view


def request(product,key='working-form-source-1',heads=(1,2),quotes=('暖色','桌边留白'),action='form'):
    return WorkingUnderstandingRequest(product.profile_id,product.timeline_id,key,state(product)['revision'],
        () if action=='disable' else tuple(WorkingSourceQuote(h,q) for h,q in zip(heads,quotes)),action,True)


def step(product,key='working-activity-step-1'):
    return SharedActivityStepRequest(product.profile_id,product.timeline_id,key,state(product)['revision'])


def form(product,adapter):
    assert send(product,'这一次构图试少量暖色。','working-source-a').status=='terminal'
    assert send(product,'桌边留白可以帮助看清主体。','working-source-b').status=='terminal'
    req=request(product)
    preview=product.application.preview_working_understanding(req)
    assert preview.status=='previewed',preview
    assert product.application.apply_working_understanding(req).status=='committed'
    assert adapter.calls[-1].payload==preview.view
    return req


def test_two_sources_leave_window_reopen_next_day_change_plan_and_reenter_canonical_reply(working_fixture):
    adapter=LocalAdapter();product=working_fixture(adapter,day=lambda:'2030-01-01')
    assert send(product,'这一次构图试少量暖色。','working-source-a').status=='terminal'
    assert send(product,'桌边留白可以帮助看清主体。','working-source-b').status=='terminal'
    assert product.application.advance_working_activity(step(product,'working-independent-plan')).status=='committed'
    baseline=state(product)['current_plan']
    req=request(product)
    assert product.application.apply_working_understanding(req).status=='committed'
    assert len({x['source_head_sequence'] for x in state(product)['understanding']['sources']})==2
    for i in range(3):
        assert send(product,'合成换题'+str(i),'working-unrelated-'+str(i)).status=='terminal'
    saved=history(product);product.close()
    fresh=LocalAdapter();product=working_fixture(fresh,day=lambda:'2030-01-02')
    assert history(product)==saved and not fresh.calls
    preview=product.application.preview_working_activity('choice')
    assert preview.status=='previewed' and preview.view['payload']['working_understanding']['support']['activity_result'] is not None
    advance=step(product,'working-after-reopen-plan')
    assert product.application.advance_working_activity(advance).status=='committed'
    assert product.application.advance_working_activity(advance).status=='replayed' and len(fresh.calls)==1
    assert state(product)['current_plan'].composition!=baseline.composition
    assert send(product,'这一版准备怎么安排？','working-reply-plan').status=='terminal'
    assert state(product)['current_plan'].composition in history(product)[-1].assistant_text
    assert fresh.calls[-1].payload['payload']['evidence']['activity_result']['plan']==asdict(state(product)['current_plan'])


@pytest.mark.parametrize('control',['disable','off','context','withdraw'])
def test_invalidated_understanding_plan_and_transitive_dialogue_never_return(working_fixture,control):
    from dynamic_subject_agent.application import ApplicationQuery,ApplicationQueryKind
    from dynamic_subject_agent.whole_context_boundary import WholeContextBoundaryRequest
    adapter=LocalAdapter();product=working_fixture(adapter);form(product,adapter)
    assert product.application.advance_working_activity(step(product)).status=='committed'
    assert send(product,'承接刚才的安排。','working-echo-result').status=='terminal'
    if control=='disable':
        assert product.application.apply_working_understanding(request(product,'working-disable-1',action='disable')).status=='committed'
    elif control=='off':
        assert product.application.set_reviewed_character_history(False).history_enabled is False
    elif control=='context':
        assert product.application.apply_whole_context_boundary(WholeContextBoundaryRequest(product.profile_id,product.timeline_id,'working-cutoff-1',0,True)).status=='committed'
    else:
        assert send(product,'不要再使用之前的聊天。','working-withdraw-1').status=='failed-closed'
    assert state(product)['visible_understanding'] is None and state(product)['current_plan'] is None
    product.close();fresh=LocalAdapter();product=working_fixture(fresh)
    assert send(product,'现在继续交流。','working-after-control').status=='terminal'
    payload=fresh.calls[-1].payload['payload']
    assert payload['evidence']['working_understanding'] is None and payload['evidence']['activity_result'] is None
    assert payload['exchange']==()


def test_disable_then_new_corrected_exchanges_rebuild_understanding_and_independent_plan(working_fixture):
    adapter=LocalAdapter();product=working_fixture(adapter);form(product,adapter)
    assert product.application.advance_working_activity(step(product)).status=='committed'
    assert product.application.apply_working_understanding(request(product,'working-disable-old',action='disable')).status=='committed'
    assert send(product,'更正当前安排：这次改为少量冷色。','working-correction-a').status=='terminal'
    a=history(product)[-1].head_sequence
    assert send(product,'保留中心轮廓，减少桌边留白。','working-correction-b').status=='terminal'
    b=history(product)[-1].head_sequence
    adapter.override=dict(status='formed',scope='composition-text',statement='本次改为冷色并减少桌边留白。',basis_refs=['U1','U2'])
    assert product.application.apply_working_understanding(request(product,'working-new-form',(a,b),('冷色','减少桌边留白'))).status=='committed'
    adapter.override=None
    assert product.application.advance_working_activity(step(product,'working-new-independent-plan')).status=='committed'
    assert '冷色' in state(product)['current_plan'].composition


def test_insufficient_is_typed_noop_preserves_old_understanding_and_nonce(working_fixture):
    adapter=LocalAdapter();product=working_fixture(adapter);form(product,adapter)
    old=state(product)['understanding']
    adapter.override=dict(status='insufficient',scope='composition-text',statement='',basis_refs=[])
    req=request(product,'working-insufficient-1')
    result=product.application.apply_working_understanding(req)
    assert result.status=='no-op' and result.problem_code=='working-understanding-insufficient' and result.receipt
    assert state(product)['understanding']==old and state(product)['formation_status']=='insufficient'
    count=len(adapter.calls)
    assert product.application.query_working_understanding(req).status=='no-op'
    assert product.application.apply_working_understanding(req).status=='no-op' and len(adapter.calls)==count


def test_bad_refs_or_same_head_or_derived_plan_cannot_form(working_fixture):
    adapter=LocalAdapter();product=working_fixture(adapter);form(product,adapter)
    bad=replace(request(product,'working-same-head'),sources=(WorkingSourceQuote(1,'暖色'),WorkingSourceQuote(1,'暖色')))
    count=len(adapter.calls)
    assert product.application.apply_working_understanding(bad).status=='unavailable' and len(adapter.calls)==count
    adapter.override=dict(status='formed',scope='composition-text',statement='无据解释',basis_refs=['U1','bad'])
    assert product.application.apply_working_understanding(request(product,'working-bad-refs')).status=='failed-closed'
    adapter.override=None
    assert product.application.advance_working_activity(step(product)).status=='committed'
    count=len(adapter.calls)
    blocked=product.application.apply_working_understanding(request(product,'working-derived-plan'))
    assert blocked.status=='unavailable' and blocked.problem_code=='working-derived-source-unavailable' and len(adapter.calls)==count


def test_exact_new_purewire_pending_denial_and_local_composition_rejects_remote_before_registry(working_fixture):
    from dynamic_subject_agent.working_understanding_remote_preview import (
        PendingWorkingUnderstandingGrant,UnapprovedWorkingUnderstandingAdapter,working_remote_request_preview)
    adapter=LocalAdapter();product=working_fixture(adapter);form(product,adapter)
    assert product.application.advance_working_activity(step(product)).status=='committed'
    assert send(product,'合成结果接话。','working-wire-reply').status=='terminal'
    for task in adapter.calls:
        wire=working_remote_request_preview(task)
        assert json.loads(wire['body']['messages'][1]['content'])==json.loads(json.dumps(task.payload['payload'],ensure_ascii=False))
        assert ('response_format' in wire['body']) is (task.kind is not ModelTaskKind.WORKING_ACTIVITY_REPLY)
    pending=UnapprovedWorkingUnderstandingAdapter(PendingWorkingUnderstandingGrant('1'*64))
    for task in adapter.calls:
        with pytest.raises(ModelGatewayFailure,match='working-understanding-use-unapproved'):
            pending.invoke(task)
    with pytest.raises(ValueError,match='local-only'):
        open_working_understanding_product_local(None,gateway=ModelGateway(pending),identity_id='unused')


@pytest.mark.parametrize('prepared',[False,True])
def test_cold_formation_is_atomic_and_never_repeats_model(working_fixture,monkeypatch,prepared):
    from dynamic_subject_agent.timeline import TimelineEngine,PublicationInterrupted,FaultPoint
    adapter=LocalAdapter();product=working_fixture(adapter)
    assert send(product,'这一次构图试少量暖色。','working-source-a').status=='terminal'
    assert send(product,'桌边留白可以帮助看清主体。','working-source-b').status=='terminal'
    req=request(product)
    with monkeypatch.context() as crash:
        if prepared:
            original=TimelineEngine._hit
            def hit(engine,point):
                if point is FaultPoint.AFTER_PLAN_CLAIM:
                    raise OSError('synthetic immutable prepared interruption')
                return original(engine,point)
            crash.setattr(TimelineEngine,'_hit',hit)
        else:
            crash.setattr(TimelineEngine,'publish',lambda *args,**kwargs: (_ for _ in ()).throw(PublicationInterrupted('synthetic','unprepared')))
        product.application.apply_working_understanding(req)
    product.close();fresh=LocalAdapter();product=working_fixture(fresh)
    assert bool(state(product)['visible_understanding']) is prepared and not fresh.calls
    assert product.application.apply_working_understanding(req).status==('replayed' if prepared else 'failed-closed')


def test_source_privacy_fence_cancels_inflight_form_then_disable_can_commit(working_fixture):
    adapter=LocalAdapter();product=working_fixture(adapter)
    assert send(product,'这一次构图试少量暖色。','working-source-a').status=='terminal'
    assert send(product,'桌边留白可以帮助看清主体。','working-source-b').status=='terminal'
    req=request(product)
    disable=request(product,'working-race-disable-1',action='disable')
    observed=[]
    def revoke():
        adapter.callback=None
        observed.append(product.application.apply_working_understanding(disable))
    adapter.callback=revoke
    assert product.application.apply_working_understanding(req).status=='failed-closed'
    assert observed[0].status=='busy' and observed[0].problem_code=='working-source-isolated-canonical-pending'
    assert state(product)['visible_understanding'] is None
    # A fenced source may remain pending while independent conversation
    # continues. Its complete-history input and the canonical re-adjudication
    # must both use the same disabled projection, including the second turn.
    assert send(product,'现在聊一个新的构图。','working-fenced-independent-a').status=='terminal'
    assert send(product,'先讨论主体摆在哪里。','working-fenced-independent-b').status=='terminal'
    for task in adapter.calls[-2:]:
        assert task.payload['payload']['exchange']==()
        assert task.payload['payload']['evidence']['working_understanding'] is None
    count=len(adapter.calls)
    disable=request(product,'working-race-disable-complete',action='disable')
    assert product.application.apply_working_understanding(disable).status=='committed'
    assert len(adapter.calls)==count


def test_cold_prepared_form_cannot_publish_after_history_revision_changes(working_fixture,monkeypatch):
    from dynamic_subject_agent.timeline import TimelineEngine,FaultPoint
    adapter=LocalAdapter();product=working_fixture(adapter)
    assert send(product,'这一次构图试少量暖色。','working-source-a').status=='terminal'
    assert send(product,'桌边留白可以帮助看清主体。','working-source-b').status=='terminal'
    req=request(product)
    with monkeypatch.context() as crash:
        original=TimelineEngine._hit
        def hit(engine,point):
            if point is FaultPoint.AFTER_PLAN_CLAIM:
                raise OSError('synthetic prepared interruption')
            return original(engine,point)
        crash.setattr(TimelineEngine,'_hit',hit)
        product.application.apply_working_understanding(req)
    assert product.application.set_reviewed_character_history(False).history_enabled is False
    product.close();fresh=LocalAdapter();product=working_fixture(fresh)
    assert state(product)['visible_understanding'] is None and not fresh.calls
    assert product.application.apply_working_understanding(req).status=='failed-closed'


def test_old_shared_qualification_does_not_gain_working_use(shared_fixture):
    product=shared_fixture()
    assert product.application.query_working_understanding().status=='unavailable'
    req=WorkingUnderstandingRequest(product.profile_id,product.timeline_id,'working-old-qualification-1',0,
        (WorkingSourceQuote(1,'甲'),WorkingSourceQuote(2,'乙')),'form',True)
    assert product.application.apply_working_understanding(req).status=='unavailable'
    assert product.application.query_shared_activity().view['revision']==0


def test_invalid_disable_nonce_cannot_mutate_source_permission_or_hide_understanding(working_fixture):
    adapter=LocalAdapter();product=working_fixture(adapter);form(product,adapter)
    before=state(product)
    count=len(adapter.calls)
    for key in ('','short'):
        invalid=request(product,key,action='disable')
        assert product.application.apply_working_understanding(invalid).status=='unavailable'
        assert state(product)==before and len(adapter.calls)==count


def test_new_working_scope_rejects_legacy_e1_selection_without_any_permission_change(working_fixture):
    from dynamic_subject_agent.shared_activity import SharedExperienceRequest
    adapter=LocalAdapter();product=working_fixture(adapter);form(product,adapter)
    before=state(product);count=len(adapter.calls)
    for head,quote in ((1,'暖色'),(None,'')):
        req=SharedExperienceRequest(product.profile_id,product.timeline_id,'working-old-e1-source-'+str(head),
            before['revision'],head,quote,True)
        result=product.application.set_shared_experience(req)
        assert result.status=='unavailable' and result.problem_code=='working-e1-selection-unavailable'
        assert state(product)==before and len(adapter.calls)==count


def test_cold_prepared_disable_reconciles_only_its_committed_fence_then_new_sources_can_form(working_fixture,monkeypatch):
    from dynamic_subject_agent.timeline import TimelineEngine,FaultPoint
    adapter=LocalAdapter();product=working_fixture(adapter);form(product,adapter)
    disable=request(product,'working-cold-disable-1',action='disable')
    count=len(adapter.calls)
    with monkeypatch.context() as crash:
        original=TimelineEngine._hit
        def hit(engine,point):
            if point is FaultPoint.AFTER_PLAN_CLAIM:
                raise OSError('synthetic immutable disable interruption')
            return original(engine,point)
        crash.setattr(TimelineEngine,'_hit',hit)
        product.application.apply_working_understanding(disable)
    assert len(adapter.calls)==count
    product.close();fresh=LocalAdapter();product=working_fixture(fresh)
    assert not fresh.calls and state(product)['visible_understanding'] is None
    assert product.application.apply_working_understanding(disable).status=='replayed'
    assert send(product,'重新确定本次构图：少量冷色。','working-cold-new-a').status=='terminal'
    a=history(product)[-1].head_sequence
    second=send(product,'只保留中心主体周围空白。','working-cold-new-b')
    assert second.status=='terminal',(second.projection.failure_stage,second.projection.failure_code)
    b=history(product)[-1].head_sequence
    req=request(product,'working-cold-rebuild-1',(a,b),('冷色','周围空白'))
    assert product.application.apply_working_understanding(req).status=='committed'


def test_opening_reconciliation_scope_failure_closes_product_and_allows_same_root_reopen(working_fixture,monkeypatch):
    from dynamic_subject_agent.host import RuntimeHost
    adapter=LocalAdapter()
    with monkeypatch.context() as scope:
        def changed(*args,**kwargs):
            raise RuntimeError('synthetic opening identity scope change')
        scope.setattr(RuntimeHost,'_reconcile_working_source_fence',changed)
        with pytest.raises(RuntimeError,match='synthetic opening identity scope change'):
            working_fixture(adapter)
    product=working_fixture(adapter)
    assert state(product)['revision']==0 and not adapter.calls
