"""S142 Facade results with deterministic LOCAL proposals, never character QA."""
import json
from dataclasses import asdict, replace

import pytest

from test_original_whole_chat import approved, personality_fixture, model_fixture, send, history
from test_shared_activity import select
from dynamic_subject_agent.local_product import open_living_activity_product_local
from dynamic_subject_agent.model_gateway import ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelGateway, ModelResult, ModelTaskKind
from dynamic_subject_agent.living_activity import LivingActionRequest, LivingControlRequest, LivingClock


class LocalAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities('local-living-fixture', 'deterministic-test', True, (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self):
        self.calls, self.callback = [], None
        self.fail, self.share, self.override = False, True, None

    def invoke(self, task):
        self.calls.append(task)
        if self.callback:
            self.callback()
        if self.fail:
            raise ValueError('synthetic model failure')
        if self.override is not None:
            return ModelResult(task.kind, self.override)
        if task.kind is ModelTaskKind.LIVING_ACTIVITY_REPLY:
            value = dict(reply_text='合成交流回复。', language='zh')
        elif task.kind is ModelTaskKind.LIVING_ACTIVITY_SHARE:
            value = dict(share=self.share, reply_text='我把桌边的留白写进这个文字方案，准备比较光线。' if self.share else '', language='zh')
        else:
            payload = task.payload['payload']
            action = payload['current_activity']['allowed_actions'][0]
            if action not in ('start', 'revise'):
                action = 'defer'
            value = dict(action=action, plan=dict(subject='静物', composition='桌边留白'+str(len(self.calls)), focus='光线') if action in ('start', 'revise') else None,
                reason_code='balance-space', basis_refs=['E1'] if payload['shared_experience'] else [], decision_note='合成的具体取舍。')
        return ModelResult(task.kind, value)


@pytest.fixture
def living_fixture(approved, monkeypatch):
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
    opened = []
    def opening(adapter=None, **kwargs):
        result = open_living_activity_product_local(config, gateway=ModelGateway(adapter or LocalAdapter()),
            identity_id=frozen.view.identity_id, binding=binding, **kwargs)
        opened.append(result)
        return result
    opening.config, opening.identity_id, opening.binding = config, frozen.view.identity_id, binding
    yield opening
    for product in opened:
        product.close()


def state(product):
    result = product.application.query_living_activity()
    assert result.status == 'available', result
    return result.view


def control(product, *, paused=None, sharing=None, key='living-control-start-1'):
    permission = state(product)['permission']
    return product.application.set_living_controls(LivingControlRequest(product.profile_id, product.timeline_id,
        key, permission['revision'], paused, sharing, True))


def action_request(product, action='simulation', key='living-opportunity-1', session='living-session-window-1'):
    return LivingActionRequest(product.profile_id, product.timeline_id, key, state(product)['revision'], action, session)


def act(product, action='simulation', key='living-opportunity-1'):
    return product.application.advance_living_activity(action_request(product, action, key))


def test_complete_local_life_share_reopen_and_two_successful_followups(living_fixture):
    adapter = LocalAdapter(); product = living_fixture(adapter)
    assert state(product)['permission'] == dict(paused=True, sharing_enabled=False, revision=0, needs_attention=False, source_blocked=False)
    assert act(product).status == 'no-op' and not adapter.calls
    assert control(product, paused=False, sharing=True).status == 'committed'
    assert act(product).status == 'committed'
    assert len(adapter.calls) == 1 and adapter.calls[0].kind is ModelTaskKind.LIVING_ACTIVITY_CHOICE
    assert not state(product)['shares']
    share_request = action_request(product, 'share', 'living-sharing-one-1')
    preview = product.application.preview_living_activity('share')
    assert preview.status == 'previewed' and len(adapter.calls) == 1
    assert product.application.advance_living_activity(share_request).status == 'committed'
    assert adapter.calls[-1].payload == preview.view
    saved = state(product)['shares']; assert len(saved) == 1 and history(product) == ()
    assert product.application.advance_living_activity(share_request).status == 'replayed'
    product.close(); fresh = LocalAdapter(); product = living_fixture(fresh)
    assert state(product)['shares'] == saved and not fresh.calls
    for index in range(3):
        before_calls = len(fresh.calls)
        preview = product.application.preview_living_activity('reply', '说说这个安排。')
        assert preview.status == 'previewed' and len(fresh.calls) == before_calls
        assert send(product, '说说这个安排。', 'living-followup-'+str(index)).status == 'terminal'
        assert fresh.calls[-1].payload == preview.view
        latest = fresh.calls[-1].payload['payload']['evidence']['latest_share']
        assert latest == (dict(text=saved[0]['text']) if index < 2 else None)
        if index == 2:
            assert fresh.calls[-1].payload['payload']['exchange'] == ()
    assert len(history(product)) == 3


def test_false_is_canonical_once_and_unchanged_result_does_not_request_share(living_fixture):
    adapter = LocalAdapter(); adapter.share = False; product = living_fixture(adapter)
    assert control(product, paused=False, sharing=True).status == 'committed'
    assert act(product).status == 'committed'
    assert act(product, 'share', 'living-false-share-1').status == 'committed'
    assert len(adapter.calls) == 2 and not state(product)['shares']
    assert len(state(product)['considered']) == 1
    product.close(); fresh = LocalAdapter(); product = living_fixture(fresh)
    assert act(product, 'share', 'living-false-share-again-2').status == 'no-op' and not fresh.calls
    fresh.override = dict(action='defer', plan=None, reason_code='defer-comparison', basis_refs=[], decision_note='合成的本次暂缓。')
    assert act(product, key='living-defer-opportunity-2').status == 'committed'
    assert len(fresh.calls) == 1
    assert act(product, 'share', 'living-no-change-share-3').status == 'no-op' and len(fresh.calls) == 1


def test_online_clock_accumulates_900_seconds_single_session_without_offline_catchup(living_fixture):
    now = [0.0]; clock = LivingClock(lambda: now[0]); adapter = LocalAdapter(); product = living_fixture(adapter, clock=clock)
    assert control(product, paused=False).status == 'committed'
    assert act(product, 'online', 'living-online-baseline-1').status == 'no-op'
    for index in range(89):
        now[0] += 10
        assert act(product, 'online', 'living-online-tick-'+str(index)).status == 'no-op'
    assert not adapter.calls
    other = action_request(product, 'online', 'living-other-session-tick-1', 'another-living-window-1')
    assert product.application.advance_living_activity(other).problem_code == 'another-life-window'
    now[0] += 10
    assert act(product, 'online', 'living-online-due-900').status == 'committed'
    assert len(adapter.calls) == 1 and state(product)['visible_result'].event.simulated is False
    now[0] += 10000
    assert act(product, 'online', 'living-online-after-offline-1').status == 'no-op'
    assert state(product)['online_seconds'] == 0 and len(adapter.calls) == 1
    product.close(); fresh = LocalAdapter(); product = living_fixture(fresh)
    assert state(product)['online_seconds'] == 0
    fresh.override = dict(action='revise', plan=dict(subject='静物', composition='重开后不同的合成文字版本', focus='光线'),
        reason_code='balance-space', basis_refs=[], decision_note='合成的新版本。')
    assert act(product, key='living-explicit-simulation-2').status == 'committed'
    assert state(product)['visible_result'].event.simulated is True


def test_unanswered_topic_suppresses_share_and_utc8_cap_counts_only_true_topics(living_fixture):
    day = ['2026-10-06']; adapter = LocalAdapter(); product = living_fixture(adapter, day=lambda: day[0])
    assert control(product, paused=False, sharing=True).status == 'committed'
    assert act(product).status == 'committed'
    assert act(product, 'share', 'living-first-topic-1').status == 'committed'
    assert act(product, key='living-second-plan-2').status == 'committed'
    calls = len(adapter.calls)
    assert act(product, 'share', 'living-unanswered-topic-2').problem_code == 'living-awaiting-reply'
    assert len(adapter.calls) == calls
    assert send(product, '这个安排挺明确。', 'living-answer-first-topic').status == 'terminal'
    assert act(product, 'share', 'living-second-topic-2').status == 'committed'
    assert send(product, '继续比较光线。', 'living-answer-second-topic').status == 'terminal'
    # From revised, defer remains legitimate; the following opportunity can
    # revise the actual stored plan without resetting it to unstarted.
    assert act(product, key='living-third-plan-3').status == 'committed'
    assert act(product, key='living-fourth-plan-4').status == 'committed'
    calls = len(adapter.calls)
    assert act(product, 'share', 'living-capped-topic-3').problem_code == 'living-daily-topic-limit'
    assert len(adapter.calls) == calls and len(state(product)['shares']) == 2
    day[0] = '2026-10-07'
    assert act(product, 'share', 'living-next-day-topic-1').status == 'committed'
    assert len(state(product)['shares']) == 3


@pytest.mark.parametrize('control_kind', ['disable', 'history-off', 'cutoff'])
def test_invalid_source_filters_share_text_and_all_derived_complete_history(living_fixture, control_kind):
    adapter = LocalAdapter(); product = living_fixture(adapter)
    assert send(product, '合成来源：桌边留白。', 'living-source-user-1').status == 'terminal'
    assert select(product, '桌边留白', key='living-source-selected-1').status == 'committed'
    assert control(product, paused=False, sharing=True).status == 'committed'
    assert act(product).status == 'committed'
    assert act(product, 'share', 'living-source-share-1').status == 'committed'
    assert send(product, '这个文字方案如何安排？', 'living-source-derived-reply-1').status == 'terminal'
    if control_kind == 'disable':
        request = select(product, '', None, 'living-source-disabled-1')
        assert request.status == 'committed'
    elif control_kind == 'history-off':
        assert product.application.set_reviewed_character_history(False).history_enabled is False
    else:
        from dynamic_subject_agent.whole_context_boundary import WholeContextBoundaryRequest
        assert product.application.apply_whole_context_boundary(WholeContextBoundaryRequest(product.profile_id, product.timeline_id,
            'living-explicit-context-cutoff-1', 0, True)).status == 'committed'
    product.close(); fresh = LocalAdapter(); product = living_fixture(fresh)
    assert not fresh.calls
    assert send(product, '现在谈点别的。', 'living-source-after-control-1').status == 'terminal'
    payload = fresh.calls[-1].payload['payload']
    assert payload['evidence'] == dict(shared_experience=None, activity_result=None, latest_share=None)
    assert payload['exchange'] == ()


@pytest.mark.parametrize('race', ['pause', 'share-off', 'history-revision', 'day'])
def test_final_share_fence_cancels_without_message_or_retry(living_fixture, monkeypatch, race):
    from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint
    day = ['2026-10-06']; adapter = LocalAdapter(); product = living_fixture(adapter, day=lambda: day[0])
    assert control(product, paused=False, sharing=True).status == 'committed'
    assert act(product).status == 'committed'
    request = action_request(product, 'share', 'living-raced-sharing-1')
    permission = state(product)['permission']
    original = TimelineEngine._hit
    def hit(self, point):
        if point is FaultPoint.BEFORE_PUBLICATION_COMMIT:
            if race == 'day':
                day[0] = '2026-10-07'
            elif race == 'history-revision':
                product.application.set_reviewed_character_history(False)
                product.application.set_reviewed_character_history(True)
            else:
                result = product.application.set_living_controls(LivingControlRequest(product.profile_id, product.timeline_id,
                    'living-raced-control-1', permission['revision'], paused=race == 'pause',
                    sharing_enabled=race != 'share-off', confirmed=True))
                assert result.status == 'committed'
        return original(self, point)
    with monkeypatch.context() as patch:
        patch.setattr(TimelineEngine, '_hit', hit)
        assert product.application.advance_living_activity(request).status == 'failed-closed'
    assert len(adapter.calls) == 2 and not state(product)['shares']
    assert state(product)['permission']['needs_attention'] is True
    assert product.application.advance_living_activity(request).status == 'failed-closed'
    assert len(adapter.calls) == 2


@pytest.mark.parametrize('prepared', [False, True])
def test_cold_share_preparation_and_nonce_requery_never_generate_again(living_fixture, monkeypatch, prepared):
    from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint, PublicationInterrupted
    adapter = LocalAdapter(); product = living_fixture(adapter)
    assert control(product, paused=False, sharing=True).status == 'committed'
    assert act(product).status == 'committed'
    request = action_request(product, 'share', 'living-interrupted-share-1')
    with monkeypatch.context() as crash:
        if prepared:
            original = TimelineEngine._hit
            def hit(self, point):
                if point is FaultPoint.AFTER_PLAN_CLAIM:
                    raise OSError('Synthetic interruption after durable share preparation')
                return original(self, point)
            crash.setattr(TimelineEngine, '_hit', hit)
        else:
            crash.setattr(TimelineEngine, 'publish', lambda *a, **k: (_ for _ in ()).throw(PublicationInterrupted('synthetic', 'before share preparation')))
        product.application.advance_living_activity(request)
    assert len(adapter.calls) == 2
    queried = product.application.query_living_activity(request)
    assert queried.status == 'busy' and len(adapter.calls) == 2
    product.close(); fresh = LocalAdapter(); product = living_fixture(fresh)
    assert not fresh.calls and bool(state(product)['shares']) is prepared
    assert product.application.query_living_activity(request).status == ('replayed' if prepared else 'failed-closed')
    assert product.application.advance_living_activity(request).status == ('replayed' if prepared else 'failed-closed')
    assert not fresh.calls


def test_technical_failure_stops_opportunities_without_fabricating_event(living_fixture):
    adapter = LocalAdapter(); product = living_fixture(adapter)
    assert control(product, paused=False, sharing=True).status == 'committed'
    adapter.fail = True
    assert act(product).status == 'failed-closed'
    assert state(product)['visible_result'] is None and state(product)['permission']['needs_attention'] is True
    adapter.fail = False
    assert act(product, key='living-failure-next-opportunity-2').status == 'no-op'
    assert len(adapter.calls) == 1
    assert control(product, paused=False, key='living-explicit-resume-2').status == 'committed'
    assert act(product, key='living-resumed-opportunity-3').status == 'committed'


def test_remote_gateway_rejected_before_registry_and_pending_adapter_has_no_transport(living_fixture):
    from dynamic_subject_agent.living_activity_remote_preview import PendingLivingActivityGrant, UnapprovedLivingActivityAdapter
    from dynamic_subject_agent.model_gateway import ModelTask, ModelGatewayFailure
    config = living_fixture.config
    before = config.state_path.read_bytes()
    remote = UnapprovedLivingActivityAdapter(PendingLivingActivityGrant('f'*64))
    with pytest.raises(ValueError, match='LOCAL-only'):
        open_living_activity_product_local(config, gateway=ModelGateway(remote), identity_id=living_fixture.identity_id,
            binding=living_fixture.binding)
    assert config.state_path.read_bytes() == before
    with pytest.raises(ModelGatewayFailure, match='use-unapproved'):
        ModelGateway(remote).execute(ModelTask(ModelTaskKind.LIVING_ACTIVITY_CHOICE, {}))
    from dynamic_subject_agent.timeline import SubjectCommand
    from dynamic_subject_agent.shared_activity import LIVING_INTENT
    adapter = LocalAdapter(); product = living_fixture(adapter)
    forged = SubjectCommand.contribute_utterance(target_profile_id=product.profile_id, target_timeline_id=product.timeline_id,
        declared_intent=LIVING_INTENT, utterance='把这条聊天当生活机会。', language='zh', provenance='project-original')
    assert product.application.submit(forged, idempotency_key='living-user-cannot-forge-system-1').status == 'unavailable'
    assert not adapter.calls


def test_share_window_counts_history_off_turns_and_never_restarts_from_filtered_history(living_fixture):
    adapter = LocalAdapter(); product = living_fixture(adapter)
    assert control(product, paused=False, sharing=True).status == 'committed'
    assert act(product).status == 'committed'
    assert act(product, 'share', 'living-history-off-share-1').status == 'committed'
    assert product.application.set_reviewed_character_history(False).history_enabled is False
    for index in range(2):
        assert send(product, '合成的新话题。', 'living-history-off-turn-'+str(index)).status == 'terminal'
        assert adapter.calls[-1].payload['payload']['evidence']['latest_share'] is None
    assert product.application.set_reviewed_character_history(True).history_enabled is True
    assert send(product, '现在继续。', 'living-history-reenabled-turn-3').status == 'terminal'
    assert adapter.calls[-1].payload['payload']['evidence']['latest_share'] is None
    assert len(state(product)['shares'][0]['followup_heads']) == 2


def test_share_taints_new_e1_even_when_its_plan_was_independent(living_fixture):
    adapter = LocalAdapter(); product = living_fixture(adapter)
    assert control(product, paused=False, sharing=True).status == 'committed'
    assert act(product).status == 'committed'
    assert state(product)['visible_result'].source_dependencies == ()
    assert send(product, '合成原话：强调光线。', 'living-new-e1-after-plan-1').status == 'terminal'
    assert select(product, '强调光线', history(product)[-1].head_sequence, 'living-new-e1-select-1').status == 'committed'
    assert act(product, 'share', 'living-new-e1-sharing-1').status == 'committed'
    assert state(product)['shares'][0]['dependencies']
    assert select(product, '', None, 'living-new-e1-disable-1').status == 'committed'
    assert send(product, '新话题。', 'living-new-e1-after-disable-1').status == 'terminal'
    payload = adapter.calls[-1].payload['payload']
    assert payload['evidence']['activity_result'] is not None
    assert payload['evidence']['latest_share'] is None
    assert payload['exchange'] == ()


@pytest.mark.parametrize('control_kind', ['source', 'cutoff'])
def test_pending_privacy_control_isolated_before_canonical_control_and_never_revives(living_fixture, control_kind):
    from dynamic_subject_agent.shared_activity import SharedExperienceRequest
    from dynamic_subject_agent.whole_context_boundary import WholeContextBoundaryRequest
    adapter = LocalAdapter(); product = living_fixture(adapter)
    assert send(product, '合成来源：桌边留白。', 'living-race-source-user-1').status == 'terminal'
    assert select(product, '桌边留白', key='living-race-source-selected-1').status == 'committed'
    assert control(product, paused=False, sharing=True).status == 'committed'
    revision = state(product)['revision']
    control_request = (SharedExperienceRequest(product.profile_id, product.timeline_id,
        'living-race-source-disable-1', revision, None, '', True) if control_kind == 'source'
        else WholeContextBoundaryRequest(product.profile_id, product.timeline_id, 'living-race-cutoff-1', 0, True))
    def disable():
        adapter.callback = None
        result = (product.application.set_shared_experience(control_request) if control_kind == 'source'
            else product.application.apply_whole_context_boundary(control_request))
        assert result.status == 'busy'
    adapter.callback = disable
    assert act(product, key='living-race-pending-plan-1').status == 'failed-closed'
    assert state(product)['permission']['source_blocked'] is True
    product.close(); fresh = LocalAdapter(); product = living_fixture(fresh)
    assert not fresh.calls
    assert send(product, '合成新话题。', 'living-race-after-reopen-1').status == 'terminal'
    assert fresh.calls[-1].payload['payload']['exchange'] == ()
    assert fresh.calls[-1].payload['payload']['evidence'] == dict(shared_experience=None, activity_result=None, latest_share=None)
    if control_kind == 'source':
        control_request = replace(control_request, expected_revision=state(product)['revision'])
        assert product.application.set_shared_experience(control_request).status == 'committed'
        after = state(product)['permission']['revision']
        assert product.application.set_shared_experience(control_request).status == 'replayed'
        assert state(product)['permission']['revision'] == after
    else:
        assert product.application.apply_whole_context_boundary(control_request).status == 'committed'
    assert state(product)['permission']['source_blocked'] is False


@pytest.mark.parametrize('revoke', ['paused', 'day'])
def test_cold_prepared_share_revalidates_day_and_permission_without_regenerating(living_fixture, monkeypatch, revoke):
    from dynamic_subject_agent.timeline import TimelineEngine, FaultPoint
    day = ['2026-10-06']; adapter = LocalAdapter(); product = living_fixture(adapter, day=lambda: day[0])
    assert control(product, paused=False, sharing=True).status == 'committed'
    assert act(product).status == 'committed'
    request = action_request(product, 'share', 'living-cold-stale-sharing-1')
    original = TimelineEngine._hit
    def hit(self, point):
        if point is FaultPoint.AFTER_PLAN_CLAIM:
            raise OSError('Synthetic interruption after immutable prepared share')
        return original(self, point)
    with monkeypatch.context() as crash:
        crash.setattr(TimelineEngine, '_hit', hit)
        product.application.advance_living_activity(request)
    if revoke == 'paused':
        # Controls can revoke a pending proposal without entering its worker.
        assert product.application.set_living_controls(LivingControlRequest(product.profile_id, product.timeline_id,
            'living-pause-during-prepared-1', 1, paused=True, confirmed=True)).status == 'committed'
    else:
        day[0] = '2026-10-07'
    product.close(); fresh = LocalAdapter(); product = living_fixture(fresh, day=lambda: day[0])
    assert not fresh.calls and not state(product)['shares']
    assert product.application.query_living_activity(request).status == 'failed-closed'
    assert state(product)['permission']['needs_attention'] is True


def test_corrupt_canonical_share_record_closes_queries_and_previews_without_model(living_fixture):
    import sqlite3
    adapter = LocalAdapter(); product = living_fixture(adapter)
    assert control(product, paused=False, sharing=True).status == 'committed'
    assert act(product).status == 'committed'
    database = None
    for candidate in living_fixture.config.product_parent.rglob('timeline.sqlite3'):
        with sqlite3.connect(candidate) as probe:
            if (probe.execute('PRAGMA user_version').fetchone() == (6,)
                and candidate.parent.name == product.timeline_id
                and probe.execute('SELECT COUNT(*) FROM shared_activity_record').fetchone()[0] > 0):
                database = candidate
                break
    assert database is not None
    with sqlite3.connect(database) as connection:
        assert connection.execute("UPDATE shared_activity_record SET record_json='{}'").rowcount > 0
    calls = len(adapter.calls)
    assert product.application.query_living_activity().status == 'failed-closed'
    assert product.application.preview_living_activity('share').status == 'failed-closed'
    assert len(adapter.calls) == calls


def test_schema6_inherits_readonly_subject_nonce_lookup_after_share_and_reopen(living_fixture, monkeypatch):
    from dynamic_subject_agent.application import SubjectRequestLookupRequest
    from dynamic_subject_agent.timeline import SubjectCommand
    from dynamic_subject_agent.runtime import SubjectRuntime
    adapter = LocalAdapter(); product = living_fixture(adapter)
    assert send(product, '已经提交的普通合成原话。', 'living-lookup-original-1').status == 'terminal'
    assert control(product, paused=False, sharing=True).status == 'committed'
    assert act(product).status == 'committed'
    assert act(product, 'share', 'living-lookup-system-share-1').status == 'committed'
    command = SubjectCommand.contribute_utterance(target_profile_id=product.profile_id, target_timeline_id=product.timeline_id,
        declared_intent='ask-collaborator-status', utterance='已经提交的普通合成原话。', language='zh', provenance='project-original')
    request = SubjectRequestLookupRequest(command, 'original-whole-test-living-lookup-original-1')
    before = state(product)['revision']; calls = len(adapter.calls)
    def forbidden(*args, **kwargs):
        pytest.fail('readonly nonce lookup entered cold recovery')
    with monkeypatch.context() as no_recovery:
        no_recovery.setattr(SubjectRuntime, 'recover_original_whole_pending', forbidden)
        found = product.application.lookup_subject_request(request)
        assert found.query_status == 'found' and found.operation.status == 'terminal'
        assert found.operation.projection.expression_text == '合成交流回复。'
        changed = SubjectCommand.contribute_utterance(target_profile_id=product.profile_id, target_timeline_id=product.timeline_id,
            declared_intent='ask-collaborator-status', utterance='不同的原话。', language='zh', provenance='project-original')
        wrong = product.application.lookup_subject_request(SubjectRequestLookupRequest(changed, request.idempotency_key))
        assert wrong.query_status == 'unavailable' and wrong.operation is None
        absent = product.application.lookup_subject_request(SubjectRequestLookupRequest(command, 'living-lookup-not-admitted-1'))
        assert absent.query_status == 'not-found' and absent.operation is None
    assert state(product)['revision'] == before and len(adapter.calls) == calls
    product.close(); fresh = LocalAdapter(); product = living_fixture(fresh)
    assert not fresh.calls
    replay = product.application.lookup_subject_request(request)
    assert replay.query_status == 'found' and replay.operation.projection == found.operation.projection
    assert state(product)['revision'] == before and not fresh.calls
