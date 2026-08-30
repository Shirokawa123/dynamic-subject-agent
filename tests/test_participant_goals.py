from __future__ import annotations

import hashlib

import pytest

from dynamic_subject_agent.participant_goals import (
    POLICY_CANONICAL_CONTENT,
    POLICY_HASH,
    ParticipantGoalCommitmentCandidate,
    ParticipantGoalCommitmentEngine,
    ParticipantGoalCommitmentRecord,
    active_targets,
)


def _record(
    record_id: str,
    kind: str,
    terms: str,
    status: str = "active",
) -> ParticipantGoalCommitmentRecord:
    return ParticipantGoalCommitmentRecord(
        record_id=record_id,
        kind=kind,
        terms=terms,
        status=status,
        source_user_message_id="source",
        evidence_quote=terms,
        created_head_sequence=1,
    )


def _evaluate(
    message: str,
    candidate: ParticipantGoalCommitmentCandidate | None,
    records: tuple[ParticipantGoalCommitmentRecord, ...] = (),
):
    return ParticipantGoalCommitmentEngine().evaluate(
        source_user_message_id="source",
        message_text=message,
        current_records=active_targets(records),
        candidate=candidate,
    )


def test_accepts_explicit_participant_goal_and_commitment() -> None:
    goal = _evaluate(
        "我的目标是今年通过 N1。",
        ParticipantGoalCommitmentCandidate(
            "create", "goal", "今年通过 N1", None, "active", "我的目标是今年通过 N1"
        ),
    )
    commitment = _evaluate(
        "我承诺周五前完成初稿。",
        ParticipantGoalCommitmentCandidate(
            "create", "commitment", "周五前完成初稿", None, "active", "我承诺周五前完成初稿"
        ),
    )
    assert (goal.decision, goal.kind, goal.terms) == (
        "accepted",
        "goal",
        "今年通过 N1",
    )
    assert (commitment.decision, commitment.kind) == ("accepted", "commitment")


@pytest.mark.parametrize(
    ("message", "candidate", "reason"),
    [
        (
            "我想学钢琴。",
            ParticipantGoalCommitmentCandidate(
                "create", "goal", "学钢琴", None, "active", "我想学钢琴"
            ),
            "insufficient_explicit_user_intent",
        ),
        (
            "明天提醒我复习。",
            ParticipantGoalCommitmentCandidate(
                "create", "commitment", "明天提醒我复习", None, "active", "明天提醒我复习"
            ),
            "out_of_scope_reminder",
        ),
        (
            "我计划周五前完成初稿。",
            ParticipantGoalCommitmentCandidate(
                "create", "commitment", "周五前完成初稿", None, "active", "我计划周五前完成初稿"
            ),
            "ordinary_plan_not_commitment",
        ),
        (
            "你承诺明天提醒我复习。",
            ParticipantGoalCommitmentCandidate(
                "create", "commitment", "明天提醒我复习", None, "active", "你承诺明天提醒我复习"
            ),
            "out_of_scope_subject_commitment",
        ),
    ],
)
def test_rejects_non_goal_and_out_of_scope_commitments(
    message: str,
    candidate: ParticipantGoalCommitmentCandidate,
    reason: str,
) -> None:
    plan = _evaluate(message, candidate)
    assert (plan.decision, plan.reason_code) == ("rejected", reason)


def test_rejects_non_verbatim_and_duplicate_create() -> None:
    non_verbatim = _evaluate(
        "我的目标是今年通过 N1。",
        ParticipantGoalCommitmentCandidate(
            "create",
            "goal",
            "拿到 JLPT N1 证书",
            None,
            "active",
            "我的目标是今年通过 N1",
        ),
    )
    duplicate = _evaluate(
        "我的目标是今年通过 N1。",
        ParticipantGoalCommitmentCandidate(
            "create", "goal", "今年通过 N1", None, "active", "我的目标是今年通过 N1"
        ),
        (_record("goal-1", "goal", "今年通过 N1"),),
    )
    assert non_verbatim.reason_code == "terms_not_verbatim_evidence"
    assert duplicate.reason_code == "duplicate_active_record"


def test_rejects_create_when_full_evidence_quote_is_not_verbatim() -> None:
    plan = _evaluate(
        "我的目标是今年通过 N1。",
        ParticipantGoalCommitmentCandidate(
            "create",
            "goal",
            "今年通过 N1",
            None,
            "active",
            "据说我的目标是今年通过 N1",
        ),
    )
    assert (plan.decision, plan.reason_code) == ("rejected", "invalid_candidate")


def test_accepts_revision_as_a_new_active_record() -> None:
    active = _record("goal-1", "goal", "今年通过 N1")
    plan = _evaluate(
        "我的目标改为明年通过 N1。",
        ParticipantGoalCommitmentCandidate(
            "revise", "goal", "明年通过 N1", "target-1", "active", "我的目标改为明年通过 N1"
        ),
        (active,),
    )
    assert (plan.decision, plan.target_record_id, plan.terms) == (
        "accepted",
        "goal-1",
        "明年通过 N1",
    )


@pytest.mark.parametrize(
    ("kind", "terms", "next_status", "message"),
    [
        ("goal", "今年通过 N1", "achieved", "我的目标已达成。"),
        ("goal", "今年通过 N1", "abandoned", "我放弃这个目标。"),
        ("commitment", "周五前完成初稿", "fulfilled", "我已经完成初稿。"),
        ("commitment", "周五前完成初稿", "released", "我取消承诺。"),
    ],
)
def test_accepts_only_explicit_participant_terminal_reports(
    kind: str,
    terms: str,
    next_status: str,
    message: str,
) -> None:
    plan = _evaluate(
        message,
        ParticipantGoalCommitmentCandidate(
            "transition", None, None, "target-1", next_status, message.rstrip("。")
        ),
        (_record("record-1", kind, terms),),
    )
    assert (plan.decision, plan.next_status, plan.target_record_id) == (
        "accepted",
        next_status,
        "record-1",
    )


def test_rejects_ambiguous_target_without_old_terms() -> None:
    records = (
        _record("commitment-1", "commitment", "周五前完成初稿"),
        _record("commitment-2", "commitment", "下周前完成海报"),
    )
    plan = _evaluate(
        "我已经完成了。",
        ParticipantGoalCommitmentCandidate(
            "transition", None, None, "target-1", "fulfilled", "我已经完成了"
        ),
        records,
    )
    assert plan.reason_code == "ambiguous_target_evidence"


def test_policy_hash_is_derived_from_canonical_content() -> None:
    assert POLICY_HASH == hashlib.sha256(
        POLICY_CANONICAL_CONTENT.encode("utf-8")
    ).hexdigest()
