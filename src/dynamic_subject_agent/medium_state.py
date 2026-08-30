"""Evidence-gated, versioned Medium State domain rules."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from unicodedata import category, normalize


POLICY_ID = "evidence-constrained-medium-state"
POLICY_VERSION = 1
BASELINES = frozenset({"settled", "concerned", "encouraged"})
SIGNALS = frozenset({"concern", "encouragement", "settling"})
WINDOW_COMPLETED_EXPERIENCES = 7
REQUIRED_INDEPENDENT_SIGNALS = 2
COOLDOWN_COMPLETED_EXPERIENCES = 2
MAX_EVIDENCE_QUOTE_CHARS = 1_000
TRANSITIONS = {
    "settled": {"concern": "concerned", "encouragement": "encouraged"},
    "concerned": {"settling": "settled"},
    "encouraged": {"settling": "settled"},
}
POLICY_CONTENT = {
    "baselines": sorted(BASELINES),
    "signals": sorted(SIGNALS),
    "window": WINDOW_COMPLETED_EXPERIENCES,
    "required_independent_signals": REQUIRED_INDEPENDENT_SIGNALS,
    "cooldown_completed_experiences": COOLDOWN_COMPLETED_EXPERIENCES,
    "reject_direct_subject_state_command": True,
    "transitions": TRANSITIONS,
}
POLICY_CANONICAL_CONTENT = json.dumps(
    POLICY_CONTENT,
    ensure_ascii=False,
    separators=(",", ":"),
    sort_keys=True,
)
POLICY_HASH = hashlib.sha256(POLICY_CANONICAL_CONTENT.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MediumStateCandidate:
    action: str
    signal: str | None
    evidence_quote: str


@dataclass(frozen=True)
class MediumStateRecord:
    revision_id: str | None
    baseline: str
    version: int
    entered_head_sequence: int | None
    policy_id: str = POLICY_ID
    policy_version: int = POLICY_VERSION
    policy_hash: str = POLICY_HASH


@dataclass(frozen=True)
class MediumSignalRecord:
    head_sequence: int
    signal: str
    evidence_quote: str

    @property
    def normalized_quote(self) -> str:
        return normalize_evidence_quote(self.evidence_quote)


@dataclass(frozen=True)
class MediumStatePlan:
    decision: str
    reason_code: str
    action: str
    before_baseline: str
    after_baseline: str
    base_version: int
    source_user_message_id: str
    signal: str | None
    evidence_quote: str
    corroborating_head_sequence: int | None = None
    policy_id: str = POLICY_ID
    policy_version: int = POLICY_VERSION
    policy_hash: str = POLICY_HASH


class MediumStateEngine:
    def evaluate(
        self,
        *,
        current_head_sequence: int,
        source_user_message_id: str,
        message_text: str,
        current_state: MediumStateRecord | None,
        recent_completed_signals: tuple[MediumSignalRecord, ...],
        candidate: MediumStateCandidate | None,
        analysis_status: str = "succeeded",
    ) -> MediumStatePlan:
        before, version, last_changed, state_error = _current_state(current_state)
        current_sequence = current_head_sequence + 1
        history = _valid_history(
            recent_completed_signals,
            before_head_sequence=current_sequence,
        )
        if state_error is not None:
            return _plan("rejected", state_error, before, version, source_user_message_id, candidate)
        if analysis_status != "succeeded":
            return _plan("no_update", "provider_error", before, version, source_user_message_id)
        invalid = _invalid_candidate_reason(candidate, message_text)
        if invalid is not None:
            return _plan(
                "rejected" if candidate is not None else "no_update",
                invalid,
                before,
                version,
                source_user_message_id,
                candidate,
            )
        if candidate is None or candidate.action == "noop":
            return _plan("no_update", "no_candidate", before, version, source_user_message_id)
        assert candidate.signal is not None
        if _is_direct_subject_state_command(message_text):
            return _plan(
                "rejected",
                "direct_subject_state_command",
                before,
                version,
                source_user_message_id,
                candidate,
            )
        normalized = normalize_evidence_quote(candidate.evidence_quote)
        if any(item.normalized_quote == normalized for item in history):
            return _plan(
                "rejected",
                "duplicate_evidence_quote",
                before,
                version,
                source_user_message_id,
                candidate,
            )
        target = TRANSITIONS[before].get(candidate.signal)
        if target is None:
            reason = (
                "already_at_baseline"
                if candidate.signal == _state_signal(before)
                else "illegal_direct_transition"
            )
            return _plan(
                "no_update" if reason == "already_at_baseline" else "rejected",
                reason,
                before,
                version,
                source_user_message_id,
                candidate,
            )
        if not _cooldown_satisfied(history, last_changed, current_sequence):
            return _plan(
                "rejected",
                "cooldown_not_satisfied",
                before,
                version,
                source_user_message_id,
                candidate,
            )
        corroborator = _latest_corroborator(
            history,
            candidate.signal,
            current_sequence,
            after_head_sequence=last_changed,
        )
        if corroborator is None:
            return _plan(
                "rejected",
                "insufficient_independent_evidence",
                before,
                version,
                source_user_message_id,
                candidate,
            )
        if _has_newer_counterevidence(
            history,
            corroborator,
            candidate.signal,
            current_sequence,
            after_head_sequence=last_changed,
        ):
            return _plan(
                "rejected",
                "counterevidence_after_corroboration",
                before,
                version,
                source_user_message_id,
                candidate,
            )
        return MediumStatePlan(
            decision="accepted",
            reason_code="transition_accepted",
            action="transition",
            before_baseline=before,
            after_baseline=target,
            base_version=version,
            source_user_message_id=source_user_message_id,
            signal=candidate.signal,
            evidence_quote=candidate.evidence_quote,
            corroborating_head_sequence=corroborator.head_sequence,
        )


def normalize_evidence_quote(value: str) -> str:
    if not isinstance(value, str):
        return ""
    normalized = normalize("NFKC", value).casefold()
    return "".join(
        char
        for char in normalized
        if not category(char).startswith("P") and not char.isspace()
    )


def virtual_or_current(state: MediumStateRecord | None) -> MediumStateRecord:
    return state or MediumStateRecord(None, "settled", 0, None)


def _current_state(
    state: MediumStateRecord | None,
) -> tuple[str, int, int | None, str | None]:
    if state is None:
        return "settled", 0, None, None
    if (
        not isinstance(state, MediumStateRecord)
        or state.baseline not in BASELINES
        or state.version < 0
        or state.entered_head_sequence is not None
        and state.entered_head_sequence < 1
        or state.policy_id != POLICY_ID
        or state.policy_version != POLICY_VERSION
        or state.policy_hash != POLICY_HASH
    ):
        return "settled", 0, None, "invalid_current_state"
    return state.baseline, state.version, state.entered_head_sequence, None


def _valid_history(
    signals: tuple[MediumSignalRecord, ...],
    *,
    before_head_sequence: int,
) -> tuple[MediumSignalRecord, ...]:
    valid = tuple(
        item
        for item in signals
        if isinstance(item, MediumSignalRecord)
        and 0 < item.head_sequence < before_head_sequence
        and item.signal in SIGNALS
        and bool(item.normalized_quote)
    )
    return tuple(sorted(valid, key=lambda item: item.head_sequence))[
        -WINDOW_COMPLETED_EXPERIENCES:
    ]


def _invalid_candidate_reason(
    candidate: MediumStateCandidate | None,
    message_text: str,
) -> str | None:
    if candidate is None:
        return "no_candidate"
    if not isinstance(candidate, MediumStateCandidate):
        return "invalid_candidate_type"
    if candidate.action == "noop":
        return None if candidate.signal is None and candidate.evidence_quote == "" else "invalid_noop_combination"
    if candidate.action != "signal":
        return "invalid_candidate_action"
    if candidate.signal not in SIGNALS:
        return "invalid_signal"
    if not isinstance(candidate.evidence_quote, str) or not candidate.evidence_quote.strip():
        return "missing_evidence_quote"
    if len(candidate.evidence_quote) > MAX_EVIDENCE_QUOTE_CHARS:
        return "evidence_quote_too_long"
    if candidate.evidence_quote not in message_text:
        return "evidence_not_verbatim_current_message"
    return None


def _state_signal(baseline: str) -> str:
    return {"settled": "settling", "concerned": "concern", "encouraged": "encouragement"}[baseline]


def _cooldown_satisfied(
    history: tuple[MediumSignalRecord, ...],
    last_changed: int | None,
    current_sequence: int,
) -> bool:
    if last_changed is None:
        return True
    completed = {item.head_sequence for item in history if item.head_sequence > last_changed}
    return current_sequence > last_changed and len(completed) + 1 >= COOLDOWN_COMPLETED_EXPERIENCES


def _latest_corroborator(
    history: tuple[MediumSignalRecord, ...],
    signal: str,
    current_sequence: int,
    *,
    after_head_sequence: int | None,
) -> MediumSignalRecord | None:
    matches = [
        item
        for item in history
        if item.signal == signal
        and item.head_sequence < current_sequence
        and (after_head_sequence is None or item.head_sequence > after_head_sequence)
    ]
    return matches[-1] if matches else None


def _has_newer_counterevidence(
    history: tuple[MediumSignalRecord, ...],
    corroborator: MediumSignalRecord,
    signal: str,
    current_sequence: int,
    *,
    after_head_sequence: int | None,
) -> bool:
    return any(
        corroborator.head_sequence < item.head_sequence < current_sequence
        and (after_head_sequence is None or item.head_sequence > after_head_sequence)
        and item.signal != signal
        for item in history
    )


def _is_direct_subject_state_command(message: str) -> bool:
    normalized = normalize_evidence_quote(message)
    state = r"(?:担心|高兴|平静|振奋)"
    patterns = (
        rf"(?:请|必须|应该|要|务必).{{0,4}}你.{{0,8}}{state}",
        rf"你.{{0,4}}(?:必须|应该|要|得).{{0,8}}{state}",
        rf"你现在(?:很)?{state}",
    )
    return any(re.search(pattern, normalized) is not None for pattern in patterns)


def _plan(
    decision: str,
    reason: str,
    baseline: str,
    version: int,
    source_id: str,
    candidate: MediumStateCandidate | None = None,
) -> MediumStatePlan:
    return MediumStatePlan(
        decision=decision,
        reason_code=reason,
        action="noop",
        before_baseline=baseline,
        after_baseline=baseline,
        base_version=version,
        source_user_message_id=source_id,
        signal=candidate.signal if isinstance(candidate, MediumStateCandidate) else None,
        evidence_quote=(
            candidate.evidence_quote if isinstance(candidate, MediumStateCandidate) else ""
        ),
    )


__all__ = [
    "BASELINES",
    "POLICY_CANONICAL_CONTENT",
    "POLICY_HASH",
    "POLICY_ID",
    "POLICY_VERSION",
    "SIGNALS",
    "MediumSignalRecord",
    "MediumStateCandidate",
    "MediumStateEngine",
    "MediumStatePlan",
    "MediumStateRecord",
    "normalize_evidence_quote",
    "virtual_or_current",
]
