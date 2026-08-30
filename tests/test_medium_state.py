from __future__ import annotations

import hashlib

from dynamic_subject_agent.medium_state import (
    POLICY_CANONICAL_CONTENT,
    POLICY_HASH,
    MediumSignalRecord,
    MediumStateCandidate,
    MediumStateEngine,
    MediumStateRecord,
)


SOURCE = "11111111-1111-4111-8111-111111111111"


def _evaluate(
    sequence: int,
    message: str,
    candidate: MediumStateCandidate | None,
    *,
    state: MediumStateRecord | None = None,
    history: tuple[MediumSignalRecord, ...] = (),
    analysis_status: str = "succeeded",
):
    return MediumStateEngine().evaluate(
        current_head_sequence=sequence - 1,
        source_user_message_id=SOURCE,
        message_text=message,
        current_state=state,
        recent_completed_signals=history,
        candidate=candidate,
        analysis_status=analysis_status,
    )


def test_two_independent_signals_transition_settled_to_concerned() -> None:
    plan = _evaluate(
        2,
        "这件事仍让我担心。",
        MediumStateCandidate("signal", "concern", "仍让我担心"),
        history=(MediumSignalRecord(1, "concern", "最近压力很大"),),
    )
    assert (plan.decision, plan.action, plan.before_baseline, plan.after_baseline) == (
        "accepted", "transition", "settled", "concerned"
    )
    assert plan.corroborating_head_sequence == 1


def test_single_duplicate_and_direct_command_cannot_transition() -> None:
    single = _evaluate(
        1,
        "我这两天一直很焦虑。",
        MediumStateCandidate("signal", "concern", "一直很焦虑"),
    )
    duplicate = _evaluate(
        2,
        "最近压力很大！",
        MediumStateCandidate("signal", "concern", "最近压力很大"),
        history=(MediumSignalRecord(1, "concern", "最近压力很大。"),),
    )
    command = _evaluate(
        2,
        "你现在应该担心。",
        MediumStateCandidate("signal", "concern", "你现在应该担心"),
        history=(MediumSignalRecord(1, "concern", "最近压力很大"),),
    )
    assert single.reason_code == "insufficient_independent_evidence"
    assert duplicate.reason_code == "duplicate_evidence_quote"
    assert command.reason_code == "direct_subject_state_command"


def test_cooldown_and_post_change_evidence_are_required() -> None:
    state = MediumStateRecord("revision", "concerned", 1, 2)
    too_soon = _evaluate(
        3,
        "现在平静了。",
        MediumStateCandidate("signal", "settling", "现在平静了"),
        state=state,
        history=(MediumSignalRecord(1, "settling", "之前平静"),),
    )
    accepted = _evaluate(
        4,
        "现在我已经安定下来了。",
        MediumStateCandidate("signal", "settling", "已经安定下来了"),
        state=state,
        history=(MediumSignalRecord(3, "settling", "情绪慢慢稳定"),),
    )
    assert too_soon.reason_code == "cooldown_not_satisfied"
    assert accepted.after_baseline == "settled"


def test_provider_failure_keeps_verified_baseline() -> None:
    state = MediumStateRecord("revision", "encouraged", 3, 20)
    plan = _evaluate(
        22,
        "继续。",
        None,
        state=state,
        analysis_status="failed",
    )
    assert (plan.decision, plan.action, plan.after_baseline) == (
        "no_update", "noop", "encouraged"
    )
    assert plan.reason_code == "provider_error"


def test_illegal_direct_jump_and_counterevidence_are_rejected() -> None:
    state = MediumStateRecord("revision", "concerned", 1, 1)
    illegal = _evaluate(
        3,
        "进展让我很开心。",
        MediumStateCandidate("signal", "encouragement", "让我很开心"),
        state=state,
    )
    counter = _evaluate(
        4,
        "我仍然非常担心。",
        MediumStateCandidate("signal", "concern", "仍然非常担心"),
        history=(
            MediumSignalRecord(1, "concern", "压力很大"),
            MediumSignalRecord(2, "settling", "已经平静"),
        ),
    )
    assert illegal.reason_code == "illegal_direct_transition"
    assert counter.reason_code == "counterevidence_after_corroboration"


def test_policy_hash_is_derived_from_canonical_content() -> None:
    assert POLICY_HASH == hashlib.sha256(
        POLICY_CANONICAL_CONTENT.encode("utf-8")
    ).hexdigest()
