"""Synthetic Runtime/Timeline behavior; no real identities, credentials or Provider."""
from dataclasses import replace
from hashlib import sha256
import sqlite3
from uuid import uuid4

import pytest

from dynamic_subject_agent.first_life import (
    FirstLifeInput, LifeRecord, LIFE_SYSTEM_INTENT, adjudicate_life, event_summary,
)
from dynamic_subject_agent.runtime import (
    CognitionEngine, ExpressionCandidate, SubjectRuntime, _RuntimeContext,
    _HOST_RUNTIME_TOKEN, RuntimeFaultPoint, RuntimeInterrupted, CycleFailedClosed,
)
from dynamic_subject_agent.timeline import (
    TimelineEngine, SubjectCommand, OperationKind, OperationState, FaultPoint,
    PublicationProblem, CommitPlanRejected, PublicationFailedClosed, PayloadConflict,
    _RuntimeBindingAuthority, _HOST_TIMELINE_TOKEN, PreAdmissionRejected,
    _data_control_export_snapshot,
)


class SyntheticLife(CognitionEngine):
    provider_authority = 'synthetic-life'
    adapter_version = 'synthetic-life-1'
    experimental = test_only = True

    def __init__(self):
        self.calls = 0
        self.last_dialogue = None

    def propose(self, *, plan, context, command, basis):
        self.calls += 1
        before = context.load_first_life()
        old = before.record
        record = replace(old, reason_code='', differences=(), event_id='', summary='', simulated=False,
            disclosed_event_id='', share_id='', share_text='', considered_event_id='')
        text = '确定性合成回复。'
        if type(command) is SubjectCommand:
            self.last_dialogue = context.load_character_dialogue(True)
            record = replace(record, kind='disclosure', disclosed_event_id=before.events[-1].event_id) if before.events else None
        elif command.input_kind == 'control':
            record = replace(record, kind='control', paused=old.paused if command.paused is None else command.paused,
                sharing_enabled=old.sharing_enabled if command.sharing_enabled is None else command.sharing_enabled)
        elif command.input_kind == 'share':
            text = '构图文字方案有一个新版本。'
            record = replace(record, kind='share', disclosed_event_id=command.target_event_id, share_id=str(uuid4()), share_text=text)
        else:
            action = 'start' if old.phase == 'unstarted' else 'revise' if old.phase == 'drafted' else 'keep'
            value = dict(action=action, plan=dict(subject='主题', composition=f'构图{old.revision + 1}', focus='明暗')
                if action in ('start', 'revise') else None, reason_code='emphasize-subject')
            action, phase, selected, reason, diffs = adjudicate_life(value, phase=old.phase, current_plan=old.plan)
            revision = old.revision + bool(diffs)
            record = replace(record, kind='advance', phase=phase, revision=revision, plan=selected, reason_code=reason,
                differences=diffs, event_id=str(uuid4()), summary=event_summary(action, revision, diffs),
                virtual_minutes=old.virtual_minutes + 1, simulated=command.trigger == 'simulation')
        proposal = self._bounded_noop_proposal(context=context, basis=basis, experience_summary='合成系统输入。',
            expression_candidate=ExpressionCandidate(text, 'zh'))
        return replace(proposal, life_record=record)


@pytest.fixture
def life_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr('dynamic_subject_agent.first_life.current_civil_day', lambda: '2026-09-27')
    authority = _RuntimeBindingAuthority(
        authority_scope_id=str(uuid4()), profile_id=str(uuid4()), timeline_id=str(uuid4()),
        allowed_intents=('ask-collaborator-status', LIFE_SYSTEM_INTENT), allowed_provenance=('project-original',),
        binding_id=str(uuid4()), binding_revision=1, binding_epoch=1,
        qualification_id=str(uuid4()), qualification_revision=1, provider_authority='synthetic-life')
    location = TimelineEngine._create_root(tmp_path, authority, gate_state='open')
    opened = []
    def opening(cognition=None, fault=None, interrupt=None):
        engine = TimelineEngine.open(location, expected_authority=authority, _host_token=_HOST_TIMELINE_TOKEN, _fault_hook=fault)
        context = _RuntimeContext.from_binding(authority, experienced_at_us=1_800_000_000_000_000,
            runtime_identity=None, _host_token=_HOST_RUNTIME_TOKEN)
        runtime = SubjectRuntime(engine, fixture=None, cognition=cognition or SyntheticLife(), _context=context,
            _host_token=_HOST_RUNTIME_TOKEN, interrupt_at=interrupt)
        opened.append(runtime)
        return runtime
    yield opening, authority, location
    for runtime in opened:
        runtime.close()


def system(authority, kind='advance', key='advance', **kwargs):
    return FirstLifeInput(authority.profile_id, authority.timeline_id, kind,
        'control' if kind == 'control' else 'online' if kind == 'share' else 'simulation',
        '2026-09-27', sha256(key.encode()).hexdigest(), **kwargs)


def advance(runtime, authority, key='advance'):
    admitted = runtime.admit_first_life(system(authority, key=key), idempotency_key='first-life-test-' + key)
    return runtime.resume(admitted.operation_ref)


def chat(runtime, authority, key='chat'):
    return runtime.execute(SubjectCommand.contribute_utterance(target_profile_id=authority.profile_id,
        target_timeline_id=authority.timeline_id, declared_intent='ask-collaborator-status', utterance=key,
        language='zh', provenance='project-original'), idempotency_key='first-life-test-' + key)


def test_typed_system_chain_versions_and_true_dialogue(life_runtime):
    opening, authority, location = life_runtime
    runtime = opening()
    first = advance(runtime, authority)
    assert first.operation_ref.operation_kind is OperationKind.SYSTEM
    assert runtime.list_conversation_turns() == ()
    assert not runtime.first_life_basis().has_dialogue
    chat(runtime, authority, 'first-chat')
    assert not runtime._cognition.last_dialogue.has_prior_committed_exchange
    advance(runtime, authority, 'second')
    advance(runtime, authority, 'third')
    chat(runtime, authority, 'second-chat')
    assert [turn.user_text for turn in runtime.list_conversation_turns()] == ['first-chat', 'second-chat']
    assert [turn.user_text for turn in runtime._cognition.last_dialogue.recent_dialogue] == ['first-chat']
    basis = runtime.first_life_basis()
    assert basis.record.phase == 'kept' and len(basis.events) == 3 and len(basis.versions) == 2
    assert basis.head_sequence == 5 and basis.events[-1].event_id in basis.disclosed_event_ids
    runtime.close()
    restored = opening()
    assert restored.first_life_basis() == basis
    with sqlite3.connect(location.timeline_database) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 3
        assert db.execute('SELECT count(*) FROM subject_command').fetchone()[0] == 2
        assert db.execute('SELECT count(*) FROM system_input').fetchone()[0] == 3


@pytest.mark.parametrize('point', [FaultPoint.AFTER_PLAN_CLAIM, FaultPoint.AFTER_EXPRESSION,
    FaultPoint.AFTER_HEAD_ADVANCE, FaultPoint.BEFORE_PUBLICATION_COMMIT])
def test_prepared_plan_replays_exactly_after_interruption(life_runtime, point):
    opening, authority, location = life_runtime
    def fault(value):
        if value is point:
            raise RuntimeError('synthetic crash')
    cognition = SyntheticLife()
    runtime = opening(cognition, fault=fault)
    admitted = runtime.admit_first_life(system(authority), idempotency_key='first-life-test-prepared')
    with pytest.raises(PublicationProblem):
        runtime.resume(admitted.operation_ref)
    prepared = runtime._engine.prepared_plan(admitted.operation_ref)
    assert prepared is not None and cognition.calls == 1
    runtime.close()
    next_cognition = SyntheticLife()
    restarted = opening(next_cognition)
    result = restarted.resume(admitted.operation_ref)
    assert result.snapshot.operation_state is OperationState.COMPLETED
    assert result.outcome.life_record == prepared.life_record and next_cognition.calls == 0
    assert restarted.resume(admitted.operation_ref).outcome == result.outcome
    assert len(restarted.first_life_basis().events) == 1


def test_control_cancels_stale_preparation_and_fences_direct_publish(life_runtime):
    opening, authority, _ = life_runtime
    def fault(point):
        if point is FaultPoint.AFTER_PLAN_CLAIM:
            raise RuntimeError('synthetic crash')
    runtime = opening(fault=fault)
    admitted = runtime.admit_first_life(system(authority), idempotency_key='first-life-test-cancelled')
    with pytest.raises(PublicationProblem): runtime.resume(admitted.operation_ref)
    prepared = runtime._engine.prepared_plan(admitted.operation_ref)
    runtime.close()
    runtime = opening()
    control = runtime.admit_first_life(system(authority, 'control', paused=True), idempotency_key='first-life-test-paused')
    runtime.resume(control.operation_ref)
    cancelled = runtime.resume(admitted.operation_ref)
    assert cancelled.snapshot.operation_state is OperationState.FAILED_CLOSED
    assert runtime.first_life_basis().events == () and runtime.first_life_basis().record.paused
    with pytest.raises(CommitPlanRejected): runtime._engine.publish(prepared)
    assert runtime.resume(admitted.operation_ref).failure == cancelled.failure
    assert runtime._cognition.calls == 1


def test_share_disclosure_and_unanswered_marker_are_one_publication(life_runtime):
    opening, authority, _ = life_runtime
    runtime = opening()
    chat(runtime, authority)
    advance(runtime, authority)
    event = runtime.first_life_basis().events[-1]
    command = system(authority, 'share', target_event_id=event.event_id)
    admitted = runtime.admit_first_life(command, idempotency_key='first-life-test-share')
    runtime.resume(admitted.operation_ref)
    state = runtime.first_life_basis()
    assert state.unanswered_share and event.event_id in state.disclosed_event_ids
    assert len(state.shares) == 1 and len(runtime.list_conversation_turns()) == 1
    chat(runtime, authority, 'reply-to-share')
    assert not runtime.first_life_basis().unanswered_share
    assert [turn.user_text for turn in runtime._cognition.last_dialogue.recent_dialogue] == ['chat']


def test_cross_day_idempotency_preserves_original_input_and_rejects_changed_control(life_runtime):
    opening, authority, _ = life_runtime
    runtime = opening()
    command = system(authority, 'control', paused=True)
    first = runtime.admit_first_life(command, idempotency_key='first-life-test-crossday')
    runtime.resume(first.operation_ref)
    replay = runtime.admit_first_life(replace(command, civil_day='2026-09-28'), idempotency_key='first-life-test-crossday')
    assert replay.operation_ref == first.operation_ref
    with pytest.raises(PayloadConflict):
        runtime.admit_first_life(replace(command, paused=False), idempotency_key='first-life-test-crossday')


def test_unprepared_attempt_does_not_call_cognition_again(life_runtime):
    opening, authority, _ = life_runtime
    runtime = opening(interrupt=RuntimeFaultPoint.AFTER_COGNITION)
    admitted = runtime.admit_first_life(system(authority), idempotency_key='first-life-test-unprepared')
    with pytest.raises(RuntimeInterrupted): runtime.resume(admitted.operation_ref)
    runtime.close()
    restarted = opening()
    with pytest.raises(CycleFailedClosed): restarted.resume(admitted.operation_ref)
    assert restarted._cognition.calls == 0 and restarted.first_life_basis().technical_problem


@pytest.mark.parametrize('cancel_point', [FaultPoint.BEFORE_PREPARED_CANCEL_COMMIT, FaultPoint.AFTER_PREPARED_CANCEL_COMMIT])
def test_cancelled_share_recovery_is_terminal_and_not_disclosed(life_runtime, cancel_point):
    opening, authority, _ = life_runtime
    runtime = opening()
    chat(runtime, authority)
    advance(runtime, authority)
    event = runtime.first_life_basis().events[-1]
    def stop_claim(point):
        if point is FaultPoint.AFTER_PLAN_CLAIM: raise RuntimeError('synthetic claim interruption')
    runtime._engine._fault_hook = stop_claim
    admitted = runtime.admit_first_life(system(authority, 'share', target_event_id=event.event_id),
        idempotency_key='first-life-test-cancel-share')
    with pytest.raises(PublicationProblem): runtime.resume(admitted.operation_ref)
    runtime.close()
    runtime = opening()
    control = runtime.admit_first_life(system(authority, 'control', sharing_enabled=False),
        idempotency_key='first-life-test-disable-share')
    runtime.resume(control.operation_ref)
    def stop_cancel(point):
        if point is cancel_point: raise RuntimeError('synthetic cancellation interruption')
    runtime._engine._fault_hook = stop_cancel
    with pytest.raises(RuntimeError): runtime.resume(admitted.operation_ref)
    runtime.close()
    restarted = opening()
    terminal = restarted.resume(admitted.operation_ref)
    assert terminal.snapshot.operation_state is OperationState.FAILED_CLOSED
    state = restarted.first_life_basis()
    assert state.shares == () and not state.unanswered_share
    assert event.event_id not in state.disclosed_event_ids and event.event_id in state.considered_event_ids
    assert restarted._cognition.calls == 0 and state.head_sequence == 3


def test_corrupt_preparation_cannot_publish_or_be_cancelled(life_runtime):
    opening, authority, location = life_runtime
    def stop_claim(point):
        if point is FaultPoint.AFTER_PLAN_CLAIM: raise RuntimeError('synthetic claim interruption')
    runtime = opening(fault=stop_claim)
    admitted = runtime.admit_first_life(system(authority), idempotency_key='first-life-test-corrupt-prepare')
    with pytest.raises(PublicationProblem): runtime.resume(admitted.operation_ref)
    runtime.close()
    with sqlite3.connect(location.timeline_database) as db:
        db.execute("UPDATE prepared_cycle_plan SET plan_json='{}'")
    restarted = opening()
    with pytest.raises(PublicationFailedClosed): restarted.resume(admitted.operation_ref)
    assert restarted._cognition.calls == 0
    with sqlite3.connect(location.timeline_database) as db:
        assert db.execute('SELECT count(*) FROM operation_failure').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM timeline_outcome').fetchone()[0] == 0


def test_life_integrity_is_checked_before_filtering_chat(life_runtime):
    opening, authority, location = life_runtime
    runtime = opening()
    chat(runtime, authority)
    advance(runtime, authority)
    runtime.close()
    with sqlite3.connect(location.timeline_database) as db:
        db.execute("UPDATE life_record SET record_json='{}'")
    restarted = opening()
    with pytest.raises(PublicationFailedClosed): restarted.list_conversation_turns()


def test_utterance_cannot_impersonate_system_input(life_runtime):
    opening, authority, _ = life_runtime
    runtime = opening()
    command = SubjectCommand.contribute_utterance(target_profile_id=authority.profile_id,
        target_timeline_id=authority.timeline_id, declared_intent=LIFE_SYSTEM_INTENT,
        utterance='advance', language='zh', provenance='project-original')
    with pytest.raises(PreAdmissionRejected): runtime.admit(command, idempotency_key='first-life-test-fake-input')


def test_commit_response_loss_and_export_preserve_system_origin(life_runtime):
    opening, authority, location = life_runtime
    def response_loss(point):
        if point is FaultPoint.AFTER_PUBLICATION_COMMIT: raise RuntimeError('response lost')
    runtime = opening(fault=response_loss)
    result = advance(runtime, authority)
    assert result.snapshot.operation_state is OperationState.COMPLETED
    assert len(runtime.first_life_basis().events) == 1
    exported = _data_control_export_snapshot(location, expected_authority=authority)
    operations = exported['runtime_timeline']['operations']
    assert len(operations) == 1 and 'system_input' in operations[0] and 'command' not in operations[0]
    assert 'utterance' not in operations[0]['system_input']
    runtime.close()
    restarted = opening()
    assert restarted.resume(result.operation_ref).outcome == result.outcome
    assert restarted._cognition.calls == 0


def test_declining_share_is_considered_but_never_disclosed(life_runtime):
    opening, authority, _ = life_runtime
    class DecliningLife(SyntheticLife):
        def propose(self, **kwargs):
            proposal = super().propose(**kwargs)
            if type(kwargs['command']) is FirstLifeInput and kwargs['command'].input_kind == 'share':
                record = proposal.life_record
                proposal = replace(proposal, life_record=replace(record, kind='share-declined',
                    considered_event_id=record.disclosed_event_id, disclosed_event_id='', share_id='', share_text=''))
            return proposal
    runtime = opening(DecliningLife())
    chat(runtime, authority)
    advance(runtime, authority)
    event_id = runtime.first_life_basis().events[-1].event_id
    admitted = runtime.admit_first_life(system(authority, 'share', target_event_id=event_id),
        idempotency_key='first-life-test-declined')
    runtime.resume(admitted.operation_ref)
    state = runtime.first_life_basis()
    assert event_id in state.considered_event_ids and event_id not in state.disclosed_event_ids
    assert not state.unanswered_share and not state.shares


def test_chat_only_discloses_the_selected_committed_event(life_runtime):
    opening, authority, _ = life_runtime
    class SelectiveLife(SyntheticLife):
        disclose_id = None
        def propose(self, **kwargs):
            proposal = super().propose(**kwargs)
            if type(kwargs['command']) is SubjectCommand:
                record = proposal.life_record
                record = None if self.disclose_id is None else replace(record, disclosed_event_id=self.disclose_id)
                return replace(proposal, life_record=record)
            return proposal
    cognition = SelectiveLife()
    runtime = opening(cognition)
    advance(runtime, authority)
    advance(runtime, authority, 'revision')
    advance(runtime, authority, 'keep')
    events = runtime.first_life_basis().events
    chat(runtime, authority, 'unrelated-topic')
    assert runtime.first_life_basis().disclosed_event_ids == ()
    cognition.disclose_id = events[1].event_id
    chat(runtime, authority, 'which-fields-changed')
    assert runtime.first_life_basis().disclosed_event_ids == (events[1].event_id,)


@pytest.mark.parametrize('boundary', ['during-model', 'prepared-restart', 'final-publication-hook'])
def test_share_crossing_trusted_civil_day_is_cancelled_without_disclosure(life_runtime, monkeypatch, boundary):
    opening, authority, location = life_runtime
    today = ['2026-09-27']
    monkeypatch.setattr('dynamic_subject_agent.first_life.current_civil_day', lambda: today[0])
    class MidnightLife(SyntheticLife):
        def propose(self, **kwargs):
            proposal = super().propose(**kwargs)
            if boundary == 'during-model' and type(kwargs['command']) is FirstLifeInput and kwargs['command'].input_kind == 'share':
                today[0] = '2026-09-28'
            return proposal
    runtime = opening(MidnightLife())
    chat(runtime, authority)
    advance(runtime, authority)
    event_id = runtime.first_life_basis().events[-1].event_id
    def fault(point):
        if boundary == 'prepared-restart' and point is FaultPoint.AFTER_PLAN_CLAIM:
            raise RuntimeError('synthetic prepared interruption')
        if boundary == 'final-publication-hook' and point is FaultPoint.BEFORE_PUBLICATION_COMMIT:
            today[0] = '2026-09-28'
    runtime._engine._fault_hook = fault
    admitted = runtime.admit_first_life(system(authority, 'share', target_event_id=event_id),
        idempotency_key='first-life-test-midnight')
    if boundary == 'prepared-restart':
        with pytest.raises(PublicationProblem): runtime.resume(admitted.operation_ref)
        runtime.close()
        today[0] = '2026-09-28'
        runtime = opening()
    terminal = runtime.resume(admitted.operation_ref)
    assert terminal.snapshot.operation_state is OperationState.FAILED_CLOSED
    assert terminal.failure.code == 'first-life-share-day-expired'
    state = runtime.first_life_basis()
    assert not state.shares and not state.unanswered_share and state.head_sequence == 2
    assert event_id in state.considered_event_ids and event_id not in state.disclosed_event_ids
    before = runtime._cognition.calls
    assert runtime.resume(admitted.operation_ref).failure == terminal.failure
    assert runtime._cognition.calls == before
    if boundary == 'prepared-restart': assert before == 0
    with sqlite3.connect(location.timeline_database) as db:
        assert db.execute('SELECT count(*) FROM prepared_cycle_plan').fetchone()[0] == 3
        assert db.execute('SELECT count(*) FROM cycle_commit_plan_receipt').fetchone()[0] == 2


def test_already_published_share_keeps_its_receipt_next_day(life_runtime, monkeypatch):
    opening, authority, _ = life_runtime
    runtime = opening()
    chat(runtime, authority)
    advance(runtime, authority)
    event_id = runtime.first_life_basis().events[-1].event_id
    admitted = runtime.admit_first_life(system(authority, 'share', target_event_id=event_id),
        idempotency_key='first-life-test-published-yesterday')
    original = runtime.resume(admitted.operation_ref)
    runtime.close()
    monkeypatch.setattr('dynamic_subject_agent.first_life.current_civil_day', lambda: '2026-09-28')
    restarted = opening()
    replay = restarted.resume(admitted.operation_ref)
    assert replay.outcome == original.outcome and restarted._cognition.calls == 0
    assert len(restarted.first_life_basis().shares) == 1


def test_readonly_public_request_lookup_survives_state_change_and_restart(life_runtime):
    opening, authority, location = life_runtime
    runtime = opening()
    request_id = 'first-life-test-public-replay'
    command = system(authority)
    assert runtime.replay_first_life_request(request_id, command.request_digest) is None
    admitted = runtime.admit_first_life(command, idempotency_key=request_id)
    pending = runtime.replay_first_life_request(request_id, command.request_digest)
    assert pending.snapshot.operation_state is OperationState.ADMITTED_PENDING and runtime._cognition.calls == 0
    original = runtime.resume(admitted.operation_ref)
    control = runtime.admit_first_life(system(authority, 'control', paused=True), idempotency_key='first-life-test-later-pause')
    runtime.resume(control.operation_ref)
    runtime.close()
    restarted = opening()
    replay = restarted.replay_first_life_request(request_id, command.request_digest)
    assert replay.operation_ref == original.operation_ref and replay.outcome == original.outcome
    assert replay.admission_replayed and restarted._cognition.calls == 0
    with pytest.raises(PayloadConflict): restarted.replay_first_life_request(request_id, sha256(b'other').hexdigest())
    assert restarted.replay_first_life_request('first-life-test-unknown-request', command.request_digest) is None
    with sqlite3.connect(location.timeline_database) as db:
        assert db.execute('SELECT count(*) FROM subject_operation').fetchone()[0] == 2


def test_invalid_preclaim_share_is_terminal_and_control_remains_usable(life_runtime):
    opening, authority, location = life_runtime
    class InvalidLife(SyntheticLife):
        def propose(self, **kwargs):
            proposal = super().propose(**kwargs)
            if type(kwargs['command']) is FirstLifeInput and kwargs['command'].input_kind == 'share':
                text = '合' * 400 + ' '
                return replace(proposal, life_record=replace(proposal.life_record, share_text=text),
                    expression_candidate=ExpressionCandidate(text, 'zh'))
            return proposal
    runtime = opening(InvalidLife())
    chat(runtime, authority)
    advance(runtime, authority)
    event_id = runtime.first_life_basis().events[-1].event_id
    command = system(authority, 'share', target_event_id=event_id)
    admitted = runtime.admit_first_life(command, idempotency_key='first-life-test-invalid-publication')
    with pytest.raises(CycleFailedClosed): runtime.resume(admitted.operation_ref)
    calls = runtime._cognition.calls
    terminal = runtime.resume(admitted.operation_ref)
    assert terminal.failure.code == 'first-life-prepublication-invalid' and runtime._cognition.calls == calls
    state = runtime.first_life_basis()
    assert state.technical_problem and not state.shares and event_id in state.considered_event_ids
    with sqlite3.connect(location.timeline_database) as db:
        assert db.execute('SELECT count(*) FROM prepared_cycle_plan').fetchone()[0] == 2
        assert db.execute('SELECT count(*) FROM operation_failure').fetchone()[0] == 1
    control = runtime.admit_first_life(system(authority, 'control', paused=True), idempotency_key='first-life-test-control-after-invalid')
    assert runtime.resume(control.operation_ref).snapshot.operation_state is OperationState.COMPLETED
    state = runtime.first_life_basis()
    assert not state.technical_problem and state.record.paused and event_id in state.considered_event_ids


@pytest.mark.parametrize('origin', ['system', 'subject'])
def test_cold_discovery_restores_prepared_work_without_request_handle(life_runtime, origin):
    opening, authority, _ = life_runtime
    runtime = opening()
    def stop_claim(point):
        if point is FaultPoint.AFTER_PLAN_CLAIM: raise RuntimeError('synthetic cold crash')
    runtime._engine._fault_hook = stop_claim
    if origin == 'system':
        admitted = runtime.admit_first_life(system(authority), idempotency_key='first-life-test-cold-system')
    else:
        command = SubjectCommand.contribute_utterance(target_profile_id=authority.profile_id,
            target_timeline_id=authority.timeline_id, declared_intent='ask-collaborator-status',
            utterance='合成未回聊天', language='zh', provenance='project-original')
        admitted = runtime.admit(command, idempotency_key='first-life-test-cold-subject')
    with pytest.raises(PublicationProblem): runtime.resume(admitted.operation_ref)
    runtime.close()
    restarted = opening()
    assert restarted.pending_first_life_operations() == (admitted.operation_ref,)
    assert restarted._cognition.calls == 0
    recovered = restarted.recover_first_life_pending()
    assert len(recovered) == 1 and recovered[0].snapshot.operation_state is OperationState.COMPLETED
    assert restarted.pending_first_life_operations() == () and restarted._cognition.calls == 0
    assert restarted.recover_first_life_pending() == ()
    if origin == 'system': assert len(restarted.first_life_basis().events) == 1
    else: assert len(restarted.list_conversation_turns()) == 1


def test_cold_unprepared_admissions_terminate_in_order_without_models(life_runtime):
    opening, authority, _ = life_runtime
    runtime = opening()
    first = runtime.admit_first_life(system(authority), idempotency_key='first-life-test-cold-unprepared-one')
    second = runtime.admit(SubjectCommand.contribute_utterance(target_profile_id=authority.profile_id,
        target_timeline_id=authority.timeline_id, declared_intent='ask-collaborator-status',
        utterance='合成未执行聊天', language='zh', provenance='project-original'),
        idempotency_key='first-life-test-cold-unprepared-two')
    runtime.close()
    restarted = opening()
    assert restarted.pending_first_life_operations() == (first.operation_ref, second.operation_ref)
    results = restarted.recover_first_life_pending()
    assert [result.operation_ref for result in results] == [first.operation_ref, second.operation_ref]
    assert all(result.failure.code == 'first-life-unprepared-interruption' for result in results)
    assert restarted._cognition.calls == 0 and restarted.pending_first_life_operations() == ()


def test_new_nonce_cannot_start_a_model_while_old_work_is_pending(life_runtime):
    opening, authority, _ = life_runtime
    runtime = opening()
    old = runtime.admit_first_life(system(authority), idempotency_key='first-life-test-old-cold-pending')
    runtime.close()
    restarted = opening()
    fresh = restarted.admit_first_life(system(authority, key='fresh'), idempotency_key='first-life-test-new-nonce')
    with pytest.raises(CycleFailedClosed): restarted.resume(fresh.operation_ref)
    assert restarted._cognition.calls == 0
    assert restarted.resume(fresh.operation_ref).failure.code == 'first-life-recovery-required'
    assert restarted.pending_first_life_operations() == (old.operation_ref,)


def test_cold_corrupt_preparation_blocks_discovery_and_new_work(life_runtime):
    opening, authority, location = life_runtime
    runtime = opening()
    def stop_claim(point):
        if point is FaultPoint.AFTER_PLAN_CLAIM: raise RuntimeError('synthetic cold crash')
    runtime._engine._fault_hook = stop_claim
    old = runtime.admit_first_life(system(authority), idempotency_key='first-life-test-cold-corrupt')
    with pytest.raises(PublicationProblem): runtime.resume(old.operation_ref)
    runtime.close()
    with sqlite3.connect(location.timeline_database) as db:
        db.execute("UPDATE prepared_cycle_plan SET plan_json='{}'")
    restarted = opening()
    with pytest.raises(PublicationFailedClosed): restarted.pending_first_life_operations()
    with pytest.raises(PublicationFailedClosed): restarted.recover_first_life_pending()
    fresh = restarted.admit_first_life(system(authority, key='fresh'), idempotency_key='first-life-test-corrupt-new-nonce')
    with pytest.raises(PublicationFailedClosed): restarted.resume(fresh.operation_ref)
    assert restarted._cognition.calls == 0


def test_cold_expired_share_is_cancelled_without_disclosure(life_runtime, monkeypatch):
    opening, authority, _ = life_runtime
    runtime = opening()
    chat(runtime, authority)
    advance(runtime, authority)
    event_id = runtime.first_life_basis().events[-1].event_id
    def stop_claim(point):
        if point is FaultPoint.AFTER_PLAN_CLAIM: raise RuntimeError('synthetic cold crash')
    runtime._engine._fault_hook = stop_claim
    old = runtime.admit_first_life(system(authority, 'share', target_event_id=event_id),
        idempotency_key='first-life-test-cold-expired-share')
    with pytest.raises(PublicationProblem): runtime.resume(old.operation_ref)
    runtime.close()
    monkeypatch.setattr('dynamic_subject_agent.first_life.current_civil_day', lambda: '2026-09-28')
    restarted = opening()
    result, = restarted.recover_first_life_pending()
    assert result.failure.code == 'first-life-share-day-expired' and restarted._cognition.calls == 0
    state = restarted.first_life_basis()
    assert not state.shares and event_id in state.considered_event_ids
