from __future__ import annotations

import hashlib

from dynamic_subject_agent.situated_state import (
    POLICY_CANONICAL_CONTENT,
    POLICY_HASH,
    SituatedStateCandidate,
    SituatedStateEngine,
    SituatedStateRecord,
    provider_projection,
)


NOW_US = 1_788_102_000_000_000


def _record(
    *,
    posture: str = "gentle",
    remaining_turns: int = 1,
    expires_at_us: int = NOW_US + 1_800_000_000,
) -> SituatedStateRecord:
    return SituatedStateRecord(
        state_id="11111111-1111-4111-8111-111111111111",
        posture=posture,
        source_user_message_id="22222222-2222-4222-8222-222222222222",
        evidence_quote="我现在有点紧张",
        remaining_turns=remaining_turns,
        expires_at_us=expires_at_us,
        created_head_sequence=1,
    )


def _evaluate(
    *,
    message: str,
    current_state: SituatedStateRecord | None = None,
    candidate: SituatedStateCandidate | None = None,
    analysis_status: str = "succeeded",
    now_us: int = NOW_US,
):
    return SituatedStateEngine().evaluate(
        source_user_message_id="33333333-3333-4333-8333-333333333333",
        message_text=message,
        current_state=current_state,
        candidate=candidate,
        analysis_status=analysis_status,
        now_us=now_us,
    )


def test_accepts_verbatim_set_with_fixed_python_lifetime() -> None:
    plan = _evaluate(
        message="我现在有点紧张，想请你说得温柔一点。",
        candidate=SituatedStateCandidate("set", "gentle", "我现在有点紧张"),
    )
    assert (plan.decision, plan.action, plan.posture) == (
        "accepted",
        "set",
        "gentle",
    )
    assert plan.remaining_turns == 1
    assert plan.expires_at_us == NOW_US + 1_800_000_000


def test_rejects_nonverbatim_closed_enum_and_direct_command() -> None:
    nonverbatim = _evaluate(
        message="随便聊聊。",
        candidate=SituatedStateCandidate("set", "focused", "我需要专注"),
    )
    invalid = _evaluate(
        message="请保持冷静。",
        candidate=SituatedStateCandidate("set", "calm", "请保持冷静"),
    )
    command = _evaluate(
        message="你现在必须谨慎一点。",
        candidate=SituatedStateCandidate("set", "cautious", "必须谨慎一点"),
    )
    provider_noop = _evaluate(
        message="你现在必须谨慎一点。",
        candidate=None,
    )
    assert nonverbatim.reason_code == "evidence_not_verbatim_current_message"
    assert invalid.reason_code == "invalid_posture"
    assert command.reason_code == "direct_command_not_evidence"
    assert (provider_noop.decision, provider_noop.action, provider_noop.reason_code) == (
        "rejected",
        "noop",
        "direct_command_not_evidence",
    )


def test_carries_once_then_expired_record_is_consumed() -> None:
    current = _record()
    carry = _evaluate(message="继续。", current_state=current)
    expired = _evaluate(
        message="继续。",
        current_state=_record(remaining_turns=0),
    )
    assert (carry.action, carry.posture, carry.target_state_id) == (
        "carry",
        "gentle",
        current.state_id,
    )
    assert (expired.action, expired.reason_code) == ("consume", "state_expired")


def test_provider_failure_consumes_old_state_without_reusing_it() -> None:
    current = _record()
    plan = _evaluate(
        message="继续。",
        current_state=current,
        analysis_status="failed",
    )
    assert (plan.decision, plan.action, plan.posture) == (
        "no_update",
        "consume",
        None,
    )
    assert plan.reason_code == "provider_error"


def test_replacement_names_old_state_and_subsecond_projection_rounds_up() -> None:
    current = _record(posture="gentle")
    replacement = _evaluate(
        message="我现在需要专注处理。",
        current_state=current,
        candidate=SituatedStateCandidate("set", "focused", "我现在需要专注"),
    )
    projection = provider_projection(
        _record(expires_at_us=NOW_US + 100_000),
        now_us=NOW_US,
    )
    assert replacement.target_state_id == current.state_id
    assert replacement.posture == "focused"
    assert projection[0].expires_in_seconds == 1


def test_policy_hash_is_derived_from_canonical_content() -> None:
    assert POLICY_HASH == hashlib.sha256(
        POLICY_CANONICAL_CONTENT.encode("utf-8")
    ).hexdigest()
