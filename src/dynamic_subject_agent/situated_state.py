"""Evidence-constrained, short-lived Situated State domain rules."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from math import ceil


POLICY_ID = "evidence-constrained-situated-state"
POLICY_VERSION = 1
POSTURES = frozenset({"focused", "gentle", "cautious"})
TTL_SECONDS = 30 * 60
ACCEPTED_REMAINING_TURNS = 1
POLICY_CONTENT = {
    "candidate": {
        "actions": ["noop", "set"],
        "postures": sorted(POSTURES),
        "set_requires": "nonempty_verbatim_current_user_message",
        "direct_command_with_must": "reject",
    },
    "provider_active_projection": {
        "fields": ["posture", "remaining_turns", "expires_in_seconds"],
        "max_items": 1,
    },
    "replacement": "accepted_set_replaces_existing_record",
    "ttl": {
        "absolute_seconds": TTL_SECONDS,
        "accepted_set_remaining_turns": ACCEPTED_REMAINING_TURNS,
        "carry_requires_provider_success_and_no_candidate": True,
        "next_completed_turn_uses_at_most_once_then_consumes": True,
    },
}
POLICY_CANONICAL_CONTENT = json.dumps(
    POLICY_CONTENT,
    ensure_ascii=False,
    separators=(",", ":"),
    sort_keys=True,
)
POLICY_HASH = hashlib.sha256(POLICY_CANONICAL_CONTENT.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SituatedStateCandidate:
    action: str
    posture: str | None
    evidence_quote: str


@dataclass(frozen=True)
class SituatedStateRecord:
    state_id: str
    posture: str
    source_user_message_id: str
    evidence_quote: str
    remaining_turns: int
    expires_at_us: int
    created_head_sequence: int
    status: str = "active"
    ended_head_sequence: int | None = None
    end_reason: str | None = None
    policy_id: str = POLICY_ID
    policy_version: int = POLICY_VERSION
    policy_hash: str = POLICY_HASH


@dataclass(frozen=True)
class SituatedStateTarget:
    posture: str
    remaining_turns: int
    expires_in_seconds: int


@dataclass(frozen=True)
class SituatedStatePlan:
    decision: str
    reason_code: str
    action: str
    posture: str | None
    source_user_message_id: str
    evidence_quote: str
    target_state_id: str | None = None
    remaining_turns: int | None = None
    expires_at_us: int | None = None
    policy_id: str = POLICY_ID
    policy_version: int = POLICY_VERSION
    policy_hash: str = POLICY_HASH


def usable_state(
    record: SituatedStateRecord | None,
    *,
    now_us: int,
) -> SituatedStateRecord | None:
    if (
        record is None
        or record.status != "active"
        or record.posture not in POSTURES
        or record.remaining_turns != 1
        or record.expires_at_us <= now_us
    ):
        return None
    return record


def provider_projection(
    record: SituatedStateRecord | None,
    *,
    now_us: int,
) -> tuple[SituatedStateTarget, ...]:
    current = usable_state(record, now_us=now_us)
    if current is None:
        return ()
    remaining_seconds = max(1, ceil((current.expires_at_us - now_us) / 1_000_000))
    return (
        SituatedStateTarget(
            posture=current.posture,
            remaining_turns=current.remaining_turns,
            expires_in_seconds=remaining_seconds,
        ),
    )


class SituatedStateEngine:
    """Adjudicate one candidate without I/O or model authority."""

    def evaluate(
        self,
        *,
        source_user_message_id: str,
        message_text: str,
        current_state: SituatedStateRecord | None,
        candidate: SituatedStateCandidate | None,
        analysis_status: str,
        now_us: int,
    ) -> SituatedStatePlan:
        if analysis_status not in {"succeeded", "failed"}:
            raise ValueError("analysis_status must be succeeded or failed")
        if analysis_status == "failed":
            return _consume_or_noop(
                source_user_message_id,
                current_state,
                reason_code="provider_error",
            )
        if _is_direct_posture_command(message_text):
            return SituatedStatePlan(
                decision="rejected",
                reason_code="direct_command_not_evidence",
                action="consume" if current_state is not None else "noop",
                posture=None,
                source_user_message_id=source_user_message_id,
                evidence_quote=(
                    candidate.evidence_quote
                    if candidate is not None
                    and isinstance(candidate.evidence_quote, str)
                    else ""
                ),
                target_state_id=(
                    current_state.state_id if current_state is not None else None
                ),
            )
        if candidate is not None and candidate.action == "set":
            invalid = _invalid_set_reason(candidate, message_text)
            if invalid is None:
                return SituatedStatePlan(
                    decision="accepted",
                    reason_code="set_accepted",
                    action="set",
                    posture=candidate.posture,
                    source_user_message_id=source_user_message_id,
                    evidence_quote=candidate.evidence_quote,
                    target_state_id=(
                        current_state.state_id if current_state is not None else None
                    ),
                    remaining_turns=ACCEPTED_REMAINING_TURNS,
                    expires_at_us=now_us + TTL_SECONDS * 1_000_000,
                )
            return SituatedStatePlan(
                decision="rejected",
                reason_code=invalid,
                action="consume" if current_state is not None else "noop",
                posture=None,
                source_user_message_id=source_user_message_id,
                evidence_quote=(
                    candidate.evidence_quote
                    if isinstance(candidate.evidence_quote, str)
                    else ""
                ),
                target_state_id=(
                    current_state.state_id if current_state is not None else None
                ),
            )
        if candidate is not None and (
            candidate.action != "noop"
            or candidate.posture is not None
            or candidate.evidence_quote != ""
        ):
            return SituatedStatePlan(
                decision="rejected",
                reason_code="invalid_noop_combination",
                action="consume" if current_state is not None else "noop",
                posture=None,
                source_user_message_id=source_user_message_id,
                evidence_quote="",
                target_state_id=(
                    current_state.state_id if current_state is not None else None
                ),
            )
        if usable_state(current_state, now_us=now_us) is not None:
            assert current_state is not None
            return SituatedStatePlan(
                decision="accepted",
                reason_code="carry_accepted",
                action="carry",
                posture=current_state.posture,
                source_user_message_id=source_user_message_id,
                evidence_quote=current_state.evidence_quote,
                target_state_id=current_state.state_id,
            )
        if current_state is not None:
            return SituatedStatePlan(
                decision="no_update",
                reason_code="state_expired",
                action="consume",
                posture=None,
                source_user_message_id=source_user_message_id,
                evidence_quote="",
                target_state_id=current_state.state_id,
            )
        return SituatedStatePlan(
            decision="no_update",
            reason_code="no_candidate",
            action="noop",
            posture=None,
            source_user_message_id=source_user_message_id,
            evidence_quote="",
        )


def direct_command_posture(message: str) -> str | None:
    if "必须" not in message:
        return None
    for posture, markers in (
        ("focused", ("专注",)),
        ("gentle", ("温柔", "温和")),
        ("cautious", ("谨慎",)),
    ):
        if any(marker in message for marker in markers):
            return posture
    return None


def _is_direct_posture_command(message: str) -> bool:
    return direct_command_posture(message) is not None


def _consume_or_noop(
    source_user_message_id: str,
    current_state: SituatedStateRecord | None,
    *,
    reason_code: str,
) -> SituatedStatePlan:
    return SituatedStatePlan(
        decision="no_update",
        reason_code=reason_code,
        action="consume" if current_state is not None else "noop",
        posture=None,
        source_user_message_id=source_user_message_id,
        evidence_quote="",
        target_state_id=(current_state.state_id if current_state is not None else None),
    )


def _invalid_set_reason(
    candidate: SituatedStateCandidate,
    message_text: str,
) -> str | None:
    if candidate.posture not in POSTURES:
        return "invalid_posture"
    if not isinstance(candidate.evidence_quote, str) or not candidate.evidence_quote.strip():
        return "missing_evidence_quote"
    if candidate.evidence_quote not in message_text:
        return "evidence_not_verbatim_current_message"
    if "必须" in candidate.evidence_quote:
        return "direct_command_not_evidence"
    return None


__all__ = [
    "ACCEPTED_REMAINING_TURNS",
    "POLICY_CANONICAL_CONTENT",
    "POLICY_HASH",
    "POLICY_ID",
    "POLICY_VERSION",
    "POSTURES",
    "TTL_SECONDS",
    "SituatedStateCandidate",
    "SituatedStateEngine",
    "SituatedStatePlan",
    "SituatedStateRecord",
    "SituatedStateTarget",
    "direct_command_posture",
    "provider_projection",
    "usable_state",
]
