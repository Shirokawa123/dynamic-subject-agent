"""Explicit new-context boundaries through the production Facade and Timeline."""
from dataclasses import asdict, replace
from hashlib import sha256
import json

import pytest

from dynamic_subject_agent.first_life import (
    FirstLifeContextResetRequest, FirstLifeInput, CONTEXT_RESET_KIND, CONTEXT_RESET_RECEIPT,
)
from dynamic_subject_agent.first_life_budget import FirstLifeBudget
from dynamic_subject_agent.first_life_dialogue import is_first_life_dialogue_control
from dynamic_subject_agent.recent_dialogue import is_dialogue_control
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.timeline import FaultPoint, PublicationProblem, OperationState, CommitPlanRejected
from dynamic_subject_agent.runtime import ExpressionCandidate, CycleFailedClosed
from test_first_life_facade import life_fixture, approved, model_fixture, personality_fixture, settle
from test_first_life_followup import enable, share
from test_first_life_publication import life_runtime, SyntheticLife, chat
from test_s109_continuous_baseline import no_remote_io, history
from test_reviewed_character_chat import send


@pytest.mark.parametrize("message", ["你平时会给自己定目标吗？", "承诺对你意味着什么？", "你最初是怎么认识我的？",
    "我觉得犯错误也可以学到东西。", "这个目标听起来挺有意思的。",
    "你完成目标的时候会觉得高兴吗？", "履行承诺为什么有时很难？", "你会怎样兑现自己的承诺？", "你如何看待放弃目标？"])
def test_topic_content_is_not_a_control_act_but_legacy_predicate_is_unchanged(message):
    assert is_dialogue_control(message)
    assert not is_first_life_dialogue_control(message)


def test_unused_modal_does_not_turn_courtesy_or_reassurance_into_a_control():
    assert not is_first_life_dialogue_control("不用谢。")
    assert not is_first_life_dialogue_control("这个目标暂时不用担心。")


@pytest.mark.parametrize("message", ["不要再提这件事。", "不要使用之前的聊天。", "删除这个目标。",
    "取消目标", "请帮我记下这个承诺。", "保存的方案能改成夜景吗？", "不要记录任何内容。",
    "不要再用刚才的聊天。", "别用之前的聊天作为回答依据。", "不许用上面那句话。", "不用此前对话了。",
    "这个目标不要再用了。", "此前聊天不用了。", "将目标修改为每天跑步。", "把晨跑目标修改成周末跑步。"])
def test_explicit_controls_are_not_relaxed_with_topic_nouns(message):
    assert is_first_life_dialogue_control(message)


def test_continuous_chat_reset_is_confirmed_local_idempotent_and_survives_restart(life_fixture, monkeypatch):
    opening, transport, _, _, _ = life_fixture
    product = enable(life_fixture)
    prior_share = share(product)
    assert send(product, "你平时会给自己定目标吗？", "s110-goal").status == "terminal"
    assert send(product, "那你怎么选择？", "s110-goal-followup").status == "terminal"
    old_turns = history(product)
    old_life = product.application.query_first_life()
    before = len(transport.calls)
    rejected = send(product, "不要再提此前的聊天。", "s110-withdrawal")
    assert rejected.status == "failed-closed" and len(transport.calls) == before
    assert product.application.set_reviewed_character_history(False).status == "active"
    assert send(product, "那我们聊蓝色吧。", "s110-still-unresolved").status == "failed-closed"
    assert len(transport.calls) == before
    request = FirstLifeContextResetRequest("s110-context-boundary", True)
    assert product.application.reset_first_life_context(replace(request, confirmed=False)).status == "unavailable"
    assert product.application.first_life_status().context_start_sequence == 0
    # A local boundary does not consume a model allowance, even with no balance.
    with monkeypatch.context() as patch:
        patch.setattr(FirstLifeBudget, "counts", lambda self: (200, 200, 0))
        reset = settle(product.application, product.application.reset_first_life_context(request))
    assert reset.status == "terminal" and reset.projection.expression_text == CONTEXT_RESET_RECEIPT
    boundary = product.application.first_life_status().context_start_sequence
    assert boundary > 0 and len(transport.calls) == before
    repeated = settle(product.application, product.application.reset_first_life_context(request))
    assert repeated.operation_ref == reset.operation_ref
    assert product.application.first_life_status().context_start_sequence == boundary
    assert history(product) == old_turns and product.application.query_first_life() == old_life
    assert product.application.set_reviewed_character_history(True).status == "active"
    assert send(product, "从蓝色开始聊吧。", "s110-fresh-first").status == "terminal"
    assert transport.calls[-2][1]["dialogue_sources"] == []
    assert transport.calls[-2][1]["current_plan"] is not None  # Explicit confirmation preserves this use.
    assert send(product, "浅蓝色呢？", "s110-fresh-second").status == "terminal"
    assert [r["text"] for r in transport.calls[-2][1]["dialogue_sources"]][0] == "从蓝色开始聊吧。"
    identity = product.profile_id, product.timeline_id
    saved = history(product)
    count = len(transport.calls)
    product.close()
    product = opening()
    assert (product.profile_id, product.timeline_id) == identity
    assert history(product) == saved and len(transport.calls) == count
    assert product.application.first_life_status().context_start_sequence == boundary
    assert send(product, "继续说浅蓝色。", "s110-fresh-after-reopen").status == "terminal"
    sources = transport.calls[-2][1]["dialogue_sources"]
    assert len(sources) == 4 and prior_share not in canonical_json(sources)
    assert not any(row["text"] in {turn.user_text for turn in old_turns} for row in sources)
    count = len(transport.calls)
    newer = send(product, "不要再用这些新聊天。", "s110-new-withdrawal")
    assert newer.status == "failed-closed"
    assert send(product, "继续聊别的。", "s110-new-still-blocked").status == "failed-closed"
    assert len(transport.calls) == count  # The old boundary cannot absolve a new control.
    print("S110_CONTEXT " + canonical_json(dict(normal_topics="committed", withdrawal="zero-call-failed-closed",
        reset="explicit-local-atomic", old_history="preserved-not-exported", restart="same-identity-and-boundary",
        new_withdrawal="blocked", real_provider_calls=0, synthetic_calls=count)))


class ResetCognition(SyntheticLife):
    def propose(self, **kwargs):
        if type(kwargs["command"]) is not FirstLifeInput or kwargs["command"].input_kind != CONTEXT_RESET_KIND:
            return super().propose(**kwargs)
        before = kwargs["context"].load_first_life().record
        record = replace(before, kind=CONTEXT_RESET_KIND, reason_code="", differences=(), event_id="", summary="",
            simulated=False, disclosed_event_id="", share_id="", share_text="", considered_event_id="")
        proposal = self._bounded_noop_proposal(context=kwargs["context"], basis=kwargs["basis"],
            experience_summary="Explicit local context boundary.",
            expression_candidate=ExpressionCandidate(CONTEXT_RESET_RECEIPT, "zh"))
        return replace(proposal, life_record=record)


def reset_input(authority, key):
    return FirstLifeInput(authority.profile_id, authority.timeline_id, CONTEXT_RESET_KIND, "control",
        "2026-09-27", sha256(key.encode()).hexdigest())


def test_prepared_context_reset_recovers_without_generation_and_preserves_old_input_fingerprints(life_runtime):
    opening, authority, _ = life_runtime
    cognition = ResetCognition()
    runtime = opening(cognition)
    chat(runtime, authority, "old")
    legacy = FirstLifeInput(authority.profile_id, authority.timeline_id, "control", "control", "2026-09-27",
        "a" * 64, paused=True)
    assert legacy.payload_fingerprint == sha256(canonical_json(dict(version="first-life-input-1",
        role="trusted-local-system", **asdict(legacy))).encode()).hexdigest()
    def fault(point):
        if point is FaultPoint.AFTER_PLAN_CLAIM:
            raise RuntimeError("synthetic interruption after durable reset preparation")
    runtime._engine._fault_hook = fault
    admitted = runtime.admit_first_life(reset_input(authority, "recover"), idempotency_key="s110-recover-boundary")
    with pytest.raises(PublicationProblem):
        runtime.resume(admitted.operation_ref)
    assert runtime.first_life_basis().context_start_sequence == 0
    runtime.close()
    fresh = ResetCognition()
    runtime = opening(fresh)
    recovered = runtime.recover_first_life_pending()
    assert recovered[0].snapshot.operation_state is OperationState.COMPLETED
    assert runtime.first_life_basis().context_start_sequence == 2 and fresh.calls == 0
    assert runtime.resume(admitted.operation_ref).outcome == recovered[0].outcome


def test_boundary_does_not_skip_unfrozen_pending(life_runtime):
    from dynamic_subject_agent.timeline import SubjectCommand
    opening, authority, _ = life_runtime
    runtime = opening(ResetCognition())
    chat(runtime, authority, "old")
    command = SubjectCommand.contribute_utterance(target_profile_id=authority.profile_id,
        target_timeline_id=authority.timeline_id, declared_intent="ask-collaborator-status",
        utterance="pending", language="zh", provenance="project-original")
    pending = runtime.admit(command, idempotency_key="s110-old-pending")
    reset = runtime.admit_first_life(reset_input(authority, "pending"), idempotency_key="s110-reset-before-pending")
    assert runtime.resume(reset.operation_ref).snapshot.operation_state is OperationState.COMPLETED
    # Fresh work must still settle the pending operation, never treat reset as its approval.
    with pytest.raises(CycleFailedClosed, match="first-life-recovery-required"):
        chat(runtime, authority, "new")
    runtime.recover_first_life_pending()
    # The unfrozen intent was never anchored to a pre-reset head; a reset does not
    # silently turn it into approved history. This remains explicitly unavailable.
    current = runtime.admit(command, idempotency_key="s110-after-unfrozen")
    runtime._engine.freeze_attempt_basis(current.operation_ref)
    assert runtime._engine.character_dialogue_before(current.operation_ref,
        expected_head=runtime.first_life_basis().head_sequence, enabled=True).status == "unavailable"


def test_context_boundary_fences_a_previously_prepared_chat(life_runtime):
    from dynamic_subject_agent.timeline import SubjectCommand
    opening, authority, _ = life_runtime
    runtime = opening(ResetCognition())
    chat(runtime, authority, "original")
    command = SubjectCommand.contribute_utterance(target_profile_id=authority.profile_id,
        target_timeline_id=authority.timeline_id, declared_intent="ask-collaborator-status",
        utterance="old candidate", language="zh", provenance="project-original")
    def fault(point):
        if point is FaultPoint.AFTER_PLAN_CLAIM:
            raise RuntimeError("synthetic prepared reply interruption")
    runtime._engine._fault_hook = fault
    old = runtime.admit(command, idempotency_key="s110-prepared-old-reply")
    with pytest.raises(PublicationProblem):
        runtime.resume(old.operation_ref)
    prepared = runtime._engine.prepared_plan(old.operation_ref)
    runtime._engine._fault_hook = None
    boundary = runtime.admit_first_life(reset_input(authority, "fence"), idempotency_key="s110-reset-fence")
    assert runtime.resume(boundary.operation_ref).snapshot.operation_state is OperationState.COMPLETED
    result = runtime.resume(old.operation_ref)
    assert result.snapshot.operation_state is OperationState.FAILED_CLOSED
    with pytest.raises(CommitPlanRejected):
        runtime._engine.publish(prepared)
    assert [row.user_text for row in runtime.list_conversation_turns()] == ["original"]


def test_persisted_old_false_positive_recovers_without_rewriting_its_failure(life_fixture, monkeypatch):
    import dynamic_subject_agent.first_life_dialogue as module
    product = enable(life_fixture)
    _, transport, _, _, _ = life_fixture
    with monkeypatch.context() as patch:
        patch.setattr(module, "is_first_life_dialogue_control", is_dialogue_control)
        old = send(product, "你平时会给自己定目标吗？", "s110-old-incorrect-control")
    assert old.status == "failed-closed" and transport.calls == []
    assert send(product, "接着谈这个想法。", "s110-after-old-false-positive").status == "terminal"
    assert transport.calls[-2][1]["dialogue_sources"] == []
    replay = product.application.wait(old.operation_ref, timeout_seconds=0)
    assert replay.status == "failed-closed"
    assert len(history(product)) == 1


def test_damaged_frozen_basis_cannot_move_a_new_withdrawal_behind_the_boundary(life_runtime):
    from dynamic_subject_agent.timeline import SubjectCommand, PublicationFailedClosed
    from uuid import UUID
    opening, authority, _ = life_runtime
    runtime = opening(ResetCognition())
    chat(runtime, authority, "old")
    boundary = runtime.admit_first_life(reset_input(authority, "integrity"), idempotency_key="s110-integrity-reset")
    runtime.resume(boundary.operation_ref)
    chat(runtime, authority, "new-context-secret")
    def command(text):
        return SubjectCommand.contribute_utterance(target_profile_id=authority.profile_id,
            target_timeline_id=authority.timeline_id, declared_intent="ask-collaborator-status",
            utterance=text, language="zh", provenance="project-original")
    withdrawal = runtime.admit(command("不要再使用新聊天。"), idempotency_key="s110-integrity-withdrawal")
    runtime._engine.freeze_attempt_basis(withdrawal.operation_ref)
    runtime._engine.fail_operation(withdrawal.operation_ref, stage="history", code="first-life-history-unverified",
        detail="Synthetic withdrawal is unresolved.")
    current = runtime.admit(command("继续"), idempotency_key="s110-integrity-current")
    runtime._engine.freeze_attempt_basis(current.operation_ref)
    assert runtime._engine.character_dialogue_before(current.operation_ref, expected_head=3, enabled=True).status == "unavailable"
    # Fault injection changes only the apparent sequence, retaining the real
    # newer digests. It must not make a post-reset control look historical.
    runtime._engine._writer.execute('UPDATE attempt_cycle_basis SET head_sequence=1 WHERE operation_id=?',
        (UUID(withdrawal.operation_ref.operation_id).bytes,))
    with pytest.raises(PublicationFailedClosed, match="dialogue-reset-prefix-unverified"):
        runtime._engine.character_dialogue_before(current.operation_ref, expected_head=3, enabled=True)
