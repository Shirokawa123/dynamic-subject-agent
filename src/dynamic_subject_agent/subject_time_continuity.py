"""Deterministic day-precision orientation within one Subject Timeline."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


_SUPPORTED_QUERIES = frozenset(
    {
        "我们上次什么时候聊的",
        "我们上次是什么时候聊的",
        "我们多久没聊了",
        "距离我们上次聊天多久了",
    }
)
_TIMEZONE = ZoneInfo("Asia/Shanghai")


class SubjectTimeFailedClosed(ValueError):
    """Canonical Subject Time inputs cannot be safely oriented."""


@dataclass(frozen=True)
class SubjectTimeAnswer:
    text: str


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
        raise SubjectTimeFailedClosed("subject-time-civil-time-invalid") from error


class SubjectTimeContinuity:
    """Deep local Module for exact Interaction Recency questions."""

    @staticmethod
    def is_query(query_text: object) -> bool:
        return _normalized_query(query_text) is not None

    def answer(
        self,
        *,
        query_text: object,
        current_admitted_at_us: object,
        last_committed_at_us: object | None,
    ) -> SubjectTimeAnswer | None:
        if not self.is_query(query_text):
            return None
        if (
            isinstance(current_admitted_at_us, bool)
            or not isinstance(current_admitted_at_us, int)
            or current_admitted_at_us <= 0
        ):
            raise SubjectTimeFailedClosed("subject-time-current-admission-invalid")
        if last_committed_at_us is None:
            return SubjectTimeAnswer(
                "在这条身份时间线上，还没有更早的已提交对话。"
            )
        if (
            isinstance(last_committed_at_us, bool)
            or not isinstance(last_committed_at_us, int)
            or last_committed_at_us <= 0
        ):
            raise SubjectTimeFailedClosed("subject-time-last-commit-invalid")
        if current_admitted_at_us < last_committed_at_us:
            raise SubjectTimeFailedClosed("subject-time-clock-regressed")
        current_date = _local_date(current_admitted_at_us)
        last_date = _local_date(last_committed_at_us)
        elapsed_days = (current_date - last_date).days
        if elapsed_days < 0:
            raise SubjectTimeFailedClosed("subject-time-clock-regressed")
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
        return SubjectTimeAnswer(f"我们上次聊天是{recency}。")


__all__ = [
    "SubjectTimeAnswer",
    "SubjectTimeContinuity",
    "SubjectTimeFailedClosed",
]
