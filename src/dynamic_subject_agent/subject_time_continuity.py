"""Deterministic day-precision orientation within one Subject Timeline."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from zoneinfo import ZoneInfo

from dynamic_subject_agent.temporal_grounding import DEFAULT_TIMEZONE_ID


_SUPPORTED_QUERIES = frozenset(
    {
        "我们上次什么时候聊的",
        "我们上次是什么时候聊的",
        "我们多久没聊了",
        "距离我们上次聊天多久了",
    }
)
_TIMEZONE = ZoneInfo(DEFAULT_TIMEZONE_ID)


class SubjectTimeStatus(str, Enum):
    ANSWER = "answer"
    NO_OP = "no-op"
    FAILED_CLOSED = "failed-closed"


class SubjectTimeHistoryFailedClosed(RuntimeError):
    """The injected canonical history reader failed integrity validation."""


class _SubjectTimeInvalid(ValueError):
    pass


@dataclass(frozen=True)
class SubjectTimeAnswer:
    text: str


@dataclass(frozen=True)
class SubjectTimeResult:
    status: SubjectTimeStatus
    answer: SubjectTimeAnswer | None = None
    problem_code: str | None = None

    @classmethod
    def answered(cls, text: str) -> SubjectTimeResult:
        return cls(SubjectTimeStatus.ANSWER, SubjectTimeAnswer(text))

    @classmethod
    def no_op(cls) -> SubjectTimeResult:
        return cls(SubjectTimeStatus.NO_OP)

    @classmethod
    def failed_closed(cls, code: str) -> SubjectTimeResult:
        return cls(SubjectTimeStatus.FAILED_CLOSED, problem_code=code)


def _normalized_query(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = re.sub(r"\s+", "", value).rstrip("。.!！?？")
    return normalized if normalized in _SUPPORTED_QUERIES else None


def _local_date(value: int) -> date:
    try:
        return datetime.fromtimestamp(value // 1_000_000, tz=UTC).astimezone(
            _TIMEZONE
        ).date()
    except (OverflowError, OSError, ValueError) as error:
        raise _SubjectTimeInvalid("subject-time-civil-time-invalid") from error


def _positive_microseconds(value: object, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise _SubjectTimeInvalid(code)
    return value


class SubjectTimeContinuity:
    """Deep local Module for exact Interaction Recency questions."""

    def evaluate(
        self,
        *,
        query_text: object,
        current_admitted_at_us: object,
        load_last_committed_at_us: Callable[[], object | None],
    ) -> SubjectTimeResult:
        if _normalized_query(query_text) is None:
            return SubjectTimeResult.no_op()
        try:
            current = _positive_microseconds(
                current_admitted_at_us,
                "subject-time-current-admission-invalid",
            )
            current_date = _local_date(current)
            if not callable(load_last_committed_at_us):
                raise _SubjectTimeInvalid("subject-time-history-reader-invalid")
            try:
                raw_last = load_last_committed_at_us()
            except SubjectTimeHistoryFailedClosed:
                return SubjectTimeResult.failed_closed(
                    "subject-time-history-failed-closed"
                )
            if raw_last is None:
                return SubjectTimeResult.answered(
                    "在这条身份时间线上，还没有更早的已提交对话。"
                )
            last = _positive_microseconds(
                raw_last,
                "subject-time-last-commit-invalid",
            )
            if current < last:
                raise _SubjectTimeInvalid("subject-time-clock-regressed")
            last_date = _local_date(last)
            elapsed_days = (current_date - last_date).days
            if elapsed_days < 0:
                raise _SubjectTimeInvalid("subject-time-clock-regressed")
            if elapsed_days == 0:
                recency = "今天"
            elif elapsed_days == 1:
                recency = "昨天"
            elif elapsed_days == 2:
                recency = "前天"
            elif elapsed_days <= 6:
                recency = f"{elapsed_days} 天前"
            else:
                recency = (
                    f"{last_date.year}年{last_date.month}月{last_date.day}日"
                    f"（距今 {elapsed_days} 天）"
                )
            return SubjectTimeResult.answered(f"我们上次聊天是{recency}。")
        except _SubjectTimeInvalid as error:
            return SubjectTimeResult.failed_closed(str(error))


__all__ = [
    "SubjectTimeAnswer",
    "SubjectTimeContinuity",
    "SubjectTimeHistoryFailedClosed",
    "SubjectTimeResult",
    "SubjectTimeStatus",
]
