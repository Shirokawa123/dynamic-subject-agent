from __future__ import annotations

import pytest

from test_participant_goal_integration import (
    _ScriptedParticipantGoalProvider, _composition, _submit, _query,
)
from dynamic_subject_agent.deepseek import DEEPSEEK_PROVIDER_AUTHORITY_ID


class _MisleadingMemory:
    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def analyze(self, request):
        from dynamic_subject_agent.living_memory import (
            LivingMemoryAction, LivingMemoryProposal, LivingMemoryProviderResult,
        )
        return LivingMemoryProviderResult(
            LivingMemoryProposal(LivingMemoryAction.CREATE, request.current_user_message),
            '用户报告一项打算。', '好，目标记下了，已经修改成功。', 'zh',
        )


class _RejectedGoal(_ScriptedParticipantGoalProvider):
    def classify(self, request):
        from dynamic_subject_agent.participant_goal_cognition import ParticipantGoalClassificationResult
        from dynamic_subject_agent.participant_goals import ParticipantGoalCommitmentCandidate
        return ParticipantGoalClassificationResult(
            ParticipantGoalCommitmentCandidate(
                'create', 'goal', '完成练习', None, 'active', request.current_user_message,
            ), (), '提议目标。', 'zh',
        )


@pytest.mark.parametrize('failed', [False, True])
def test_goal_failure_cannot_be_hidden_by_successful_memory(tmp_path, failed):
    provider = _ScriptedParticipantGoalProvider(fail_classify=True) if failed else _RejectedGoal()
    _, qri, timeline, app = _composition(tmp_path, provider, memory_provider=_MisleadingMemory())
    try:
        turn = _submit(app, qri, timeline, '关于目标，我打算完成练习。')
        assert turn.status.value == 'terminal'
        assert turn.projection.living_memory_status == 'accepted'
        assert turn.projection.participant_goal_commitment_status == ('failed-closed' if failed else 'rejected')
        assert '目标记下了' not in turn.projection.expression_text
        assert '修改成功' not in turn.projection.expression_text
        assert ('没能完成目标' if failed else '没有保存或修改目标') in turn.projection.expression_text
        assert _query(app, qri, timeline) == ()
    finally:
        app.close()


def test_empty_goal_query_is_not_answered_from_memory(tmp_path):
    _, qri, timeline, app = _composition(tmp_path, _ScriptedParticipantGoalProvider(), memory_provider=_MisleadingMemory())
    try:
        turn = _submit(app, qri, timeline, '我现在有哪些目标？')
        assert turn.projection.expression_text == '你目前还没有明确记录的目标。'
        assert _query(app, qri, timeline) == ()
    finally:
        app.close()


def test_report_goal_create_revise_and_query(tmp_path):
    _, qri, timeline, app = _composition(tmp_path, _ScriptedParticipantGoalProvider(), memory_provider=_MisleadingMemory())
    try:
        created = _submit(app, qri, timeline, '我给自己定个目标：明天把小本子里的三句话写完。请帮我记住这个目标，送人的事可以晚一点再说。')
        assert created.projection.participant_goal_commitment_status == 'accepted'
        assert _query(app, qri, timeline)[0].terms == '明天把小本子里的三句话写完'
        revised = _submit(app, qri, timeline, '我改主意了：把写三句话的目标改成后天只写一句。明天不写了，原来的三句目标也不保留。')
        assert revised.projection.participant_goal_commitment_action == 'revise'
        assert revised.projection.participant_goal_commitment_status == 'accepted'
        queried = _submit(app, qri, timeline, '我现在有哪些目标？')
        assert queried.projection.expression_text == '你当前的目标是：后天只写一句。'
        assert [r.terms for r in _query(app, qri, timeline) if r.status == 'active'] == ['后天只写一句']
    finally:
        app.close()


@pytest.mark.parametrize('legacy_expression', [False, True])
def test_historical_feedback_survives_next_turn_and_restart(tmp_path, monkeypatch, legacy_expression):
    from types import SimpleNamespace
    from app.desktop.server import AppState
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.composite import ControlledCompositeCognition
    from dynamic_subject_agent.runtime import ExpressionCandidate
    from test_participant_goal_integration import _NoopKnowledgeProvider, _NoopRelationshipProvider, _goal_gateway

    goal = _ScriptedParticipantGoalProvider(fail_classify=True)
    prepared, qri, timeline, app = _composition(tmp_path, goal, memory_provider=_MisleadingMemory())
    def desktop(composition):
        return AppState(SimpleNamespace(application=composition.application, profile_id=qri.profile_id, timeline_id=timeline))
    try:
        state = desktop(app)
        with monkeypatch.context() as patch:
            if legacy_expression:
                # Publish an old-style misleading expression, then restore current code.
                patch.setattr(ControlledCompositeCognition, 'express', lambda *a, **k: ExpressionCandidate('好的，目标记下了。', 'zh'))
            first = state.submit_turn('关于目标，我打算完成练习。')
        second = state.submit_turn('我们多久没聊了？')
        assert first['ok'] and second['ok']
        assert any(note['kind'] == 'failed' for note in first['explanations'])
        assert second['conversation_history'][0]['explanations'] == first['explanations']
        if legacy_expression:
            assert second['conversation_history'][0]['assistant_text'] == '好的，目标记下了。'
        host_location = app.host_location
    finally:
        app.close()
    restarted = compose_application(
        m0_root=prepared.experiment_base, studio_location=prepared.location,
        qualified_runtime_input=qri, timeline_id=timeline, host_location=host_location,
        _cognition=ControlledCompositeCognition(
            memory_provider=_MisleadingMemory(), knowledge_provider=_NoopKnowledgeProvider(),
            relationship_provider=_NoopRelationshipProvider(), participant_goal_gateway=_goal_gateway(goal),
        ), relationship_mode='dynamic',
    )
    try:
        history = desktop(restarted).snapshot()['conversation_history']
        assert history == second['conversation_history']
    finally:
        restarted.close()


def test_revision_with_no_target_or_ambiguous_targets_cannot_succeed(tmp_path):
    _, qri, timeline, app = _composition(tmp_path, _ScriptedParticipantGoalProvider(), memory_provider=_MisleadingMemory())
    try:
        missing = _submit(app, qri, timeline, '把练习的目标改成只写一句。')
        assert missing.projection.participant_goal_commitment_status == 'rejected'
        assert '没有找到' in missing.projection.expression_text
        for text in ('我的目标是学习法语。', '我的目标是练习写作。'):
            _submit(app, qri, timeline, text)
        ambiguous = _submit(app, qri, timeline, '我的目标改为每天阅读。')
        assert ambiguous.projection.participant_goal_commitment_status == 'rejected'
        assert {r.terms for r in _query(app, qri, timeline) if r.status == 'active'} == {'学习法语', '练习写作'}
    finally:
        app.close()


@pytest.mark.parametrize('message', [
    '朋友给自己定个目标：完成练习。',
    '如果我给自己定个目标：完成练习，你怎么看？',
    '朋友说：我给自己定个目标：完成练习。',
    '我打算明天完成练习。',
    '你承诺明天提醒我复习。',
])
def test_natural_goal_route_does_not_promote_out_of_scope_inputs(tmp_path, message):
    # The classifier attempts a write, including when it quotes conditional text.
    _, qri, timeline, app = _composition(tmp_path, _RejectedGoal())
    try:
        _submit(app, qri, timeline, message)
        assert _query(app, qri, timeline) == ()
    finally:
        app.close()


@pytest.mark.parametrize('message', [
    '我给自己定个目标：每天阅读。算了，不要保存这个目标。',
    '我给自己定个目标：每天阅读。我的目标改为练习写作。',
    '我给自己定个目标：每天阅读。我放弃这个目标。',
    '我给自己定个目标：每天阅读。算了，别记这个目标。',
    '我承诺每天阅读。我取消承诺。',
])
def test_full_message_cannot_contradict_first_goal_clause(tmp_path, message):
    _, qri, timeline, app = _composition(tmp_path, _ScriptedParticipantGoalProvider(), memory_provider=_MisleadingMemory())
    try:
        turn = _submit(app, qri, timeline, message)
        assert turn.projection.participant_goal_commitment_status == 'rejected'
        assert _query(app, qri, timeline) == ()
        assert '已记录你的目标' not in turn.projection.expression_text
    finally:
        app.close()


@pytest.mark.parametrize('message', [
    '把跑步的目标改成游泳。',
    '把朋友的目标改成每天阅读。',
])
def test_named_revision_cannot_modify_unrelated_singleton(tmp_path, message):
    _, qri, timeline, app = _composition(tmp_path, _ScriptedParticipantGoalProvider())
    try:
        _submit(app, qri, timeline, '我的目标是学习法语。')
        turn = _submit(app, qri, timeline, message)
        assert turn.projection.participant_goal_commitment_status == 'rejected'
        assert [r.terms for r in _query(app, qri, timeline) if r.status == 'active'] == ['学习法语']
    finally:
        app.close()


def test_unrelated_goal_failure_does_not_erase_memory_reply(tmp_path):
    from dynamic_subject_agent.living_memory import LivingMemoryAction, LivingMemoryProposal, LivingMemoryProviderResult

    class RecallMemory(_MisleadingMemory):
        def analyze(self, request):
            if '之前说过生日' in request.current_user_message and request.active_memories:
                return LivingMemoryProviderResult(
                    LivingMemoryProposal(LivingMemoryAction.NONE, '', recalled_memory_ids=(request.active_memories[0].memory_id,)), '召回生日。',
                    '你之前说过生日是四月五号。', 'zh',
                )
            return super().analyze(request)

    _, qri, timeline, app = _composition(tmp_path, _ScriptedParticipantGoalProvider(fail_classify=True), memory_provider=RecallMemory())
    try:
        _submit(app, qri, timeline, '我的目标是学习法语。')
        _submit(app, qri, timeline, '我的生日是四月五号。')
        turn = _submit(app, qri, timeline, '我之前说过生日是什么时候？')
        assert turn.projection.participant_goal_commitment_status == 'failed-closed'
        assert turn.projection.living_memory_status != 'failed-closed'
        assert '四月五号' in turn.projection.expression_text
        assert '目标或承诺的处理' not in turn.projection.expression_text
    finally:
        app.close()


def test_explicit_goal_request_with_no_candidate_cannot_claim_success(tmp_path):
    _, qri, timeline, app = _composition(tmp_path, _ScriptedParticipantGoalProvider(), memory_provider=_MisleadingMemory())
    try:
        turn = _submit(app, qri, timeline, '请帮我记住这个目标：每天阅读。')
        assert turn.projection.participant_goal_commitment_status in {None, 'no-update'}
        assert '目标记下了' not in turn.projection.expression_text
        assert '没有' in turn.projection.expression_text
        assert _query(app, qri, timeline) == ()
    finally:
        app.close()


def test_legacy_plaintext_outcome_still_projects_history(tmp_path):
    from test_atomic_publication import _authority, _command, _commit_plan
    from dynamic_subject_agent.timeline import TimelineEngine

    engine = TimelineEngine.create_test(tmp_path, _authority())
    try:
        admitted = engine.admit(_command(), idempotency_key='s18-legacy-plain-reason')
        engine.publish(_commit_plan(engine, admitted.operation_ref, admitted.attempt_id))
        turn = engine.list_conversation_turns()[0]
        assert turn.assistant_text == 'I can check the print-slot status within this fixture.'
        assert turn.outcome_summary.memory_content is None
        assert turn.outcome_summary.participant_goal_commitment_status is None
    finally:
        engine.close()
