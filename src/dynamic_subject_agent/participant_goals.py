"""Evidence-constrained participant goals and commitments."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from dynamic_subject_agent.temporal_grounding import TemporalAnchor


POLICY_ID = "participant-goal-commitment"
POLICY_VERSION = 1
MAX_TERMS_CHARS = 500
MAX_EVIDENCE_QUOTE_CHARS = 1_000
ACTIVE_RECORD_LIMIT = 20
REPLY_RECORD_LIMIT = 5
PARTICIPANT_GOAL_FAILURE_CODES = frozenset({
    'participant-goal-classification-failed', 'participant-goal-classification-invalid',
    'participant-goal-selection-invalid', 'participant-goal-reply-failed', 'participant-goal-reply-invalid',
})

DIRECT_OPERATION_PATTERNS = (
    (r'^我给自己定(?:个|一个)目标[：:]([^。；;！？!?]+)(?:[。；;！？!?]|$)', 'create', 'goal'),
    (r'^(?:我改主意了[：:]\s*)?把[^。；;！？!?]+的目标改成([^。；;！？!?]+)(?:[。；;！？!?]|$)', 'revise', 'goal'),
    (r'^我的目标改为([^。；;！？!?]+)(?:[。；;！？!?]|$)', 'revise', 'goal'),
    (r'^我的承诺改为([^。；;！？!?]+)(?:[。；;！？!?]|$)', 'revise', 'commitment'),
    (r'^我的目标是([^。；;！？!?]+)(?:[。；;！？!?]|$)', 'create', 'goal'),
    (r'^我承诺([^。；;！？!?]+)(?:[。；;！？!?]|$)', 'create', 'commitment'),
)

DIRECT_TRANSITION_COMMANDS = (
    ('goal', 'achieved', ('我的目标已达成', '目标已达成')),
    ('goal', 'abandoned', ('我放弃这个目标', '我放弃目标')),
    ('commitment', 'fulfilled', ('我已履行承诺', '我的承诺已履行')),
    ('commitment', 'released', ('我取消承诺', '我解除承诺')),
)

TRANSITION_INTENT_RULES = {
    "achieved": (
        ("目标已达成",),
        ("我已达成",),
        ("已经实现", "目标"),
        ("目标", "已经实现"),
        ("目标", "我已经完成"),
        ("目标", "我已完成"),
        ("目标", "目标完成了"),
    ),
    "abandoned": (("放弃", "目标"), ("不再以", "为目标")),
    "fulfilled": (("已履行", "承诺"), ("我已经完成",), ("我已完成",)),
    "released": (("解除",), ("取消",), ("不再承诺",)),
}

POLICY_CONTENT = {
    "actions": ["create", "transition", "revise", "noop"],
    "candidate_evidence": {
        "evidence_quote_must_be_verbatim_current_user_message": True,
        "non_noop_requires_nonempty_evidence_quote": True,
        "terms_must_be_verbatim_in_evidence_quote_and_current_user_message": True,
    },
    "candidate_fail_closed": {
        "invalid_candidate": "rejected",
        "missing_candidate": "no_update",
        "unknown_target_ref": "rejected",
    },
    "create_exclusions": [
        "wish",
        "ordinary_plan",
        "reminder",
        "subject_commitment",
        "mutual_commitment",
    ],
    "create_requires": ["explicit_user_intent", "active_initial_status"],
    "duplicate_active_create": "reject_same_kind_and_terms",
    "kinds": ["goal", "commitment"],
    "limits": {
        "evidence_quote_max_chars": MAX_EVIDENCE_QUOTE_CHARS,
        "terms_max_chars": MAX_TERMS_CHARS,
    },
    "revision": "append_only",
    "revision_requires": {
        "new_record_starts_active": True,
        "same_kind_as_active_target": True,
        "supersede_target_before_insert": True,
    },
    "target_selection": {
        "active_only": True,
        "multiple_same_kind_requires_verbatim_old_terms_in_current_message": True,
        "unique_same_kind_allows_target_ref": True,
    },
    "terminal_statuses": {
        "commitment": ["fulfilled", "released"],
        "goal": ["achieved", "abandoned"],
    },
    "transition_intent_phrases": TRANSITION_INTENT_RULES,
    "terminal_status_semantics": "participant_report_only_not_externally_verified",
    "turn_cardinality": "at_most_one_plan",
}
POLICY_CANONICAL_CONTENT = json.dumps(
    POLICY_CONTENT,
    ensure_ascii=False,
    separators=(",", ":"),
    sort_keys=True,
)
POLICY_HASH = hashlib.sha256(POLICY_CANONICAL_CONTENT.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ParticipantGoalCommitmentRecord:
    record_id: str
    kind: str
    terms: str
    status: str
    source_user_message_id: str
    evidence_quote: str
    created_head_sequence: int
    revision_of_record_id: str | None = None
    status_changed_head_sequence: int | None = None
    policy_id: str = POLICY_ID
    policy_version: int = POLICY_VERSION
    policy_hash: str = POLICY_HASH
    temporal_anchor: TemporalAnchor | None = None


@dataclass(frozen=True)
class ParticipantGoalCommitmentTarget:
    turn_ref: str
    record: ParticipantGoalCommitmentRecord


@dataclass(frozen=True)
class ParticipantGoalCommitmentCandidate:
    action: str
    kind: str | None
    terms: str | None
    target_ref: str | None
    next_status: str | None
    evidence_quote: str


@dataclass(frozen=True)
class ParticipantGoalCommitmentPlan:
    decision: str
    reason_code: str
    action: str
    kind: str | None
    terms: str | None
    next_status: str | None
    source_user_message_id: str
    evidence_quote: str
    target_record_id: str | None = None
    policy_id: str = POLICY_ID
    policy_version: int = POLICY_VERSION
    policy_hash: str = POLICY_HASH


def active_targets(
    records: tuple[ParticipantGoalCommitmentRecord, ...],
) -> tuple[ParticipantGoalCommitmentTarget, ...]:
    active = tuple(record for record in records if record.status == "active")
    return tuple(
        ParticipantGoalCommitmentTarget(f"target-{index}", record)
        for index, record in enumerate(active, start=1)
    )


def participant_operation_requested(message: str) -> bool:
    """A local feedback gate, not evidence permitting a state mutation."""
    return any(noun in message for noun in ('目标', '承诺')) and any(
        verb in message for verb in (
            '记住', '记录', '保存', '改为', '改成', '修改', '目标是',
            '定个', '定一个', '我承诺', '达成', '放弃', '履行', '取消', '解除', '打算',
        )
    )


def named_goal_revision_matches(message: str, terms: str) -> bool:
    """Do not let an explicitly named old goal silently select a singleton.

    Besides literal old terms, the bounded writing form 写X can name X写完.
    Other paraphrases remain ambiguous; this is not fuzzy semantic matching.
    """
    match = re.search(r'把([^。；;！？!?]+)的目标改成', message)
    if match is None:
        return True
    name = match.group(1).strip()
    if name == '我':
        return True
    if any(owner in name for owner in ('朋友', '他的', '她的', '你的', '我们的')) or name in {'他', '她', '你', '我们'}:
        return False
    if name.startswith('我的'):
        name = name[2:]
    return bool(name) and (
        name in terms
        or name.startswith('写') and len(name) > 1 and name[1:] + '写完' in terms
    )


def _has_conflicting_operation_intent(message: str) -> bool:
    # Inspect the whole admitted message, not a provider-selected first clause.
    commands = re.findall(
        r'我给自己定(?:个|一个)目标[：:]|我的(?:目标|承诺)(?:是|改为)|'
        r'我承诺|把[^。；;！？!?]+的目标改成', message,
    )
    terminal_pattern = '|'.join(
        re.escape(phrase) for _, _, phrases in DIRECT_TRANSITION_COMMANDS for phrase in phrases
    )
    commands.extend(re.findall(terminal_pattern, message))
    withdrawal = re.search(r'(?:不要|不用|别)(?:再)?(?:保存|记录|记(?:住|下)?)', message)
    return len(commands) > 1 or withdrawal is not None


class ParticipantGoalCommitmentEngine:
    """Reduce one untrusted provider candidate to one deterministic plan."""

    def evaluate(
        self,
        *,
        source_user_message_id: str,
        message_text: str,
        current_records: tuple[ParticipantGoalCommitmentTarget, ...],
        candidate: ParticipantGoalCommitmentCandidate | None,
    ) -> ParticipantGoalCommitmentPlan:
        if candidate is None or candidate.action == "noop":
            return _plan(
                source_user_message_id,
                decision="no_update",
                reason_code="no_candidate",
            )
        if _has_conflicting_operation_intent(message_text):
            return _plan(
                source_user_message_id,
                decision="rejected",
                reason_code="conflicting_operation_intent",
            )
        if (
            not isinstance(candidate.evidence_quote, str)
            or len(candidate.evidence_quote) > MAX_EVIDENCE_QUOTE_CHARS
        ):
            return _plan(
                source_user_message_id,
                decision="rejected",
                reason_code="evidence_quote_too_long",
            )
        if (
            isinstance(candidate.terms, str)
            and len(candidate.terms.strip()) > MAX_TERMS_CHARS
        ):
            return _plan(
                source_user_message_id,
                decision="rejected",
                reason_code="terms_too_long",
                evidence_quote=candidate.evidence_quote,
            )
        if candidate.terms is not None and (
            not isinstance(candidate.terms, str)
            or not candidate.terms.strip()
            or candidate.terms.strip() not in candidate.evidence_quote
            or candidate.terms.strip() not in message_text
        ):
            return _plan(
                source_user_message_id,
                decision="rejected",
                reason_code="terms_not_verbatim_evidence",
                evidence_quote=candidate.evidence_quote,
            )
        if candidate.action == "transition":
            return self._transition(
                source_user_message_id,
                message_text,
                current_records,
                candidate,
            )
        if candidate.action == "revise":
            return self._revise(
                source_user_message_id,
                message_text,
                current_records,
                candidate,
            )
        if candidate.action == "create":
            return self._create(
                source_user_message_id,
                message_text,
                current_records,
                candidate,
            )
        return _plan(
            source_user_message_id,
            decision="rejected",
            reason_code="invalid_candidate",
            evidence_quote=candidate.evidence_quote,
        )

    def _transition(
        self,
        source_user_message_id: str,
        message_text: str,
        current_records: tuple[ParticipantGoalCommitmentTarget, ...],
        candidate: ParticipantGoalCommitmentCandidate,
    ) -> ParticipantGoalCommitmentPlan:
        target = _find_target(current_records, candidate.target_ref)
        if target is None:
            return _plan(
                source_user_message_id,
                decision="rejected",
                reason_code="unknown_target_ref",
                evidence_quote=candidate.evidence_quote,
            )
        if _requires_target_term_evidence(target, current_records, message_text):
            return _plan(
                source_user_message_id,
                decision="rejected",
                reason_code="ambiguous_target_evidence",
                evidence_quote=candidate.evidence_quote,
            )
        if not _has_explicit_transition_intent(
            target.record.kind,
            candidate.next_status,
            candidate.evidence_quote,
        ):
            return _plan(
                source_user_message_id,
                decision="rejected",
                reason_code="insufficient_explicit_transition_intent",
                evidence_quote=candidate.evidence_quote,
            )
        if (
            target.record.status == "active"
            and candidate.kind is None
            and candidate.terms is None
            and candidate.next_status in _allowed_terminal_statuses(target.record.kind)
            and candidate.evidence_quote
            and candidate.evidence_quote in message_text
        ):
            return ParticipantGoalCommitmentPlan(
                decision="accepted",
                reason_code="transition_accepted",
                action="transition",
                kind=target.record.kind,
                terms=None,
                next_status=candidate.next_status,
                source_user_message_id=source_user_message_id,
                evidence_quote=candidate.evidence_quote,
                target_record_id=target.record.record_id,
            )
        return _plan(
            source_user_message_id,
            decision="rejected",
            reason_code="invalid_candidate",
            evidence_quote=candidate.evidence_quote,
        )

    def _revise(
        self,
        source_user_message_id: str,
        message_text: str,
        current_records: tuple[ParticipantGoalCommitmentTarget, ...],
        candidate: ParticipantGoalCommitmentCandidate,
    ) -> ParticipantGoalCommitmentPlan:
        target = _find_target(current_records, candidate.target_ref)
        if target is None:
            return _plan(
                source_user_message_id,
                decision="rejected",
                reason_code="unknown_target_ref",
                evidence_quote=candidate.evidence_quote,
            )
        if target.record.kind == 'goal' and not named_goal_revision_matches(message_text, target.record.terms):
            return _plan(
                source_user_message_id,
                decision='rejected',
                reason_code='ambiguous_target_evidence',
                evidence_quote=candidate.evidence_quote,
            )
        if _requires_target_term_evidence(target, current_records, message_text):
            return _plan(
                source_user_message_id,
                decision="rejected",
                reason_code="ambiguous_target_evidence",
                evidence_quote=candidate.evidence_quote,
            )
        if (
            target.record.status == "active"
            and candidate.kind == target.record.kind
            and candidate.terms
            and candidate.next_status == "active"
            and candidate.evidence_quote
            and candidate.evidence_quote in message_text
            and _has_explicit_revision_intent(candidate.kind, candidate.evidence_quote)
        ):
            return ParticipantGoalCommitmentPlan(
                decision="accepted",
                reason_code="revision_accepted",
                action="revise",
                kind=candidate.kind,
                terms=candidate.terms.strip(),
                next_status="active",
                source_user_message_id=source_user_message_id,
                evidence_quote=candidate.evidence_quote,
                target_record_id=target.record.record_id,
            )
        return _plan(
            source_user_message_id,
            decision="rejected",
            reason_code="invalid_candidate",
            evidence_quote=candidate.evidence_quote,
        )

    def _create(
        self,
        source_user_message_id: str,
        message_text: str,
        current_records: tuple[ParticipantGoalCommitmentTarget, ...],
        candidate: ParticipantGoalCommitmentCandidate,
    ) -> ParticipantGoalCommitmentPlan:
        if not (
            candidate.kind in {"goal", "commitment"}
            and candidate.terms
            and candidate.next_status == "active"
            and candidate.target_ref is None
            and candidate.evidence_quote
            and candidate.evidence_quote in message_text
        ):
            return _plan(
                source_user_message_id,
                decision="rejected",
                reason_code="invalid_candidate",
                evidence_quote=candidate.evidence_quote,
            )
        if any(
            target.record.status == "active"
            and target.record.kind == candidate.kind
            and target.record.terms == candidate.terms.strip()
            for target in current_records
        ):
            return _plan(
                source_user_message_id,
                decision="rejected",
                reason_code="duplicate_active_record",
                evidence_quote=candidate.evidence_quote,
            )
        if _is_subject_or_mutual_commitment(candidate.evidence_quote):
            reason = "out_of_scope_subject_commitment"
        elif _is_reminder_request(candidate.evidence_quote):
            reason = "out_of_scope_reminder"
        elif _is_ordinary_plan(candidate.evidence_quote):
            reason = "ordinary_plan_not_commitment"
        elif not _has_explicit_user_intent(candidate.kind, candidate.evidence_quote, message_text):
            reason = "insufficient_explicit_user_intent"
        else:
            return ParticipantGoalCommitmentPlan(
                decision="accepted",
                reason_code="create_accepted",
                action="create",
                kind=candidate.kind,
                terms=candidate.terms.strip(),
                next_status="active",
                source_user_message_id=source_user_message_id,
                evidence_quote=candidate.evidence_quote,
            )
        return _plan(
            source_user_message_id,
            decision="rejected",
            reason_code=reason,
            evidence_quote=candidate.evidence_quote,
        )


def _plan(
    source_user_message_id: str,
    *,
    decision: str,
    reason_code: str,
    evidence_quote: str = "",
) -> ParticipantGoalCommitmentPlan:
    return ParticipantGoalCommitmentPlan(
        decision=decision,
        reason_code=reason_code,
        action="noop",
        kind=None,
        terms=None,
        next_status=None,
        source_user_message_id=source_user_message_id,
        evidence_quote=evidence_quote,
    )


def _find_target(
    current_records: tuple[ParticipantGoalCommitmentTarget, ...],
    target_ref: str | None,
) -> ParticipantGoalCommitmentTarget | None:
    if not isinstance(target_ref, str):
        return None
    return next(
        (target for target in current_records if target.turn_ref == target_ref),
        None,
    )


def _allowed_terminal_statuses(kind: str) -> tuple[str, ...]:
    return ("achieved", "abandoned") if kind == "goal" else ("fulfilled", "released")


def _has_explicit_user_intent(kind: str, evidence_quote: str, message_text: str) -> bool:
    from dynamic_subject_agent.current_message import direct_statement_clauses
    direct = tuple(clause for clause in direct_statement_clauses(message_text) if evidence_quote.rstrip('。') in clause)
    if not direct:
        return False
    if kind == "goal":
        natural = r'我给自己定(?:个|一个)目标[：:]'
        if re.search(natural, evidence_quote):
            # Quoting a conditional or another speaker's declaration is not consent.
            return any(re.match(natural, clause) is not None for clause in direct)
        return '目标是' in evidence_quote or '我的目标' in evidence_quote
    return "我承诺" in evidence_quote


def _has_explicit_revision_intent(kind: str, evidence_quote: str) -> bool:
    if kind == 'goal':
        return '目标改为' in evidence_quote or '的目标改成' in evidence_quote
    return '承诺改为' in evidence_quote


def _is_reminder_request(evidence_quote: str) -> bool:
    return "提醒" in evidence_quote


def _is_ordinary_plan(evidence_quote: str) -> bool:
    return "计划" in evidence_quote


def _is_subject_or_mutual_commitment(evidence_quote: str) -> bool:
    return "你承诺" in evidence_quote or "我们承诺" in evidence_quote


def _requires_target_term_evidence(
    target: ParticipantGoalCommitmentTarget,
    current_records: tuple[ParticipantGoalCommitmentTarget, ...],
    message_text: str,
) -> bool:
    same_kind_active = tuple(
        item
        for item in current_records
        if item.record.kind == target.record.kind and item.record.status == "active"
    )
    return len(same_kind_active) > 1 and target.record.terms not in message_text


def _has_explicit_transition_intent(
    kind: str,
    next_status: str | None,
    evidence_quote: str,
) -> bool:
    if next_status not in _allowed_terminal_statuses(kind):
        return False
    return any(
        all(phrase in evidence_quote for phrase in required)
        for required in TRANSITION_INTENT_RULES[next_status]
    )


__all__ = [
    "ACTIVE_RECORD_LIMIT",
    "MAX_EVIDENCE_QUOTE_CHARS",
    "MAX_TERMS_CHARS",
    "POLICY_CANONICAL_CONTENT",
    "POLICY_HASH",
    "POLICY_ID",
    "POLICY_VERSION",
    "REPLY_RECORD_LIMIT",
    "ParticipantGoalCommitmentCandidate",
    "ParticipantGoalCommitmentEngine",
    "ParticipantGoalCommitmentPlan",
    "ParticipantGoalCommitmentRecord",
    "ParticipantGoalCommitmentTarget",
    "active_targets",
]
