"""Deterministic Civil Time anchoring for sourced plan expressions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


TEMPORAL_POLICY_VERSION = "temporal-anchor-day-v1"
DEFAULT_TIMEZONE_ID = "Asia/Shanghai"
_RELATIVE_PATTERN = re.compile(r"今天|明天|后天")
_ISO_DATE_PATTERN = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_CHINESE_DATE_PATTERN = re.compile(
    r"(?<!\d)(\d{4})年(\d{1,2})月(\d{1,2})日"
)
_RELATIVE_DAY_OFFSETS = {"今天": 0, "明天": 1, "后天": 2}
_CURRENT_RELATIVE_LABELS = {
    -2: "前天",
    -1: "昨天",
    0: "今天",
    1: "明天",
    2: "后天",
}


class TemporalGroundingFailedClosed(ValueError):
    """A persisted Temporal Anchor could not be safely interpreted."""


@dataclass(frozen=True)
class TemporalAnchor:
    original_expression: str
    anchor_date: str
    target_date: str
    timezone_id: str = DEFAULT_TIMEZONE_ID
    precision: str = "day"
    policy_version: str = TEMPORAL_POLICY_VERSION

    def __post_init__(self) -> None:
        if (
            not isinstance(self.original_expression, str)
            or not self.original_expression.strip()
            or len(self.original_expression) > 32
        ):
            raise TemporalGroundingFailedClosed(
                "temporal-anchor-expression-invalid"
            )
        try:
            anchored_on = date.fromisoformat(self.anchor_date)
            target = date.fromisoformat(self.target_date)
            ZoneInfo(self.timezone_id)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise TemporalGroundingFailedClosed(
                "temporal-anchor-civil-time-invalid"
            ) from error
        if (
            self.precision != "day"
            or self.policy_version != TEMPORAL_POLICY_VERSION
        ):
            raise TemporalGroundingFailedClosed(
                "temporal-anchor-policy-invalid"
            )
        relative_offset = _RELATIVE_DAY_OFFSETS.get(self.original_expression)
        if relative_offset is not None:
            expected_target = anchored_on + timedelta(days=relative_offset)
        else:
            absolute_match = _ISO_DATE_PATTERN.fullmatch(
                self.original_expression
            ) or _CHINESE_DATE_PATTERN.fullmatch(self.original_expression)
            expected_target = (
                None
                if absolute_match is None
                else _absolute_date(*absolute_match.groups())
            )
        if expected_target is None or target != expected_target:
            raise TemporalGroundingFailedClosed(
                "temporal-anchor-target-inconsistent"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "original_expression": self.original_expression,
            "anchor_date": self.anchor_date,
            "target_date": self.target_date,
            "timezone_id": self.timezone_id,
            "precision": self.precision,
            "policy_version": self.policy_version,
        }

    @classmethod
    def from_dict(cls, source: Mapping[str, object]) -> TemporalAnchor:
        fields = {
            "original_expression",
            "anchor_date",
            "target_date",
            "timezone_id",
            "precision",
            "policy_version",
        }
        if set(source) != fields or any(
            not isinstance(source[field], str) for field in fields
        ):
            raise TemporalGroundingFailedClosed("temporal-anchor-shape-invalid")
        return cls(
            original_expression=str(source["original_expression"]),
            anchor_date=str(source["anchor_date"]),
            target_date=str(source["target_date"]),
            timezone_id=str(source["timezone_id"]),
            precision=str(source["precision"]),
            policy_version=str(source["policy_version"]),
        )


def _local_date(observed_at_us: int, timezone_id: str) -> date:
    if (
        isinstance(observed_at_us, bool)
        or not isinstance(observed_at_us, int)
        or observed_at_us <= 0
    ):
        raise TemporalGroundingFailedClosed("temporal-observation-invalid")
    try:
        timezone = ZoneInfo(timezone_id)
    except ZoneInfoNotFoundError as error:
        raise TemporalGroundingFailedClosed("temporal-timezone-invalid") from error
    try:
        observed_at_seconds = observed_at_us // 1_000_000
        return datetime.fromtimestamp(
            observed_at_seconds,
            tz=UTC,
        ).astimezone(timezone).date()
    except (OverflowError, OSError, ValueError) as error:
        raise TemporalGroundingFailedClosed(
            "temporal-observation-out-of-range"
        ) from error


def _absolute_date(year: str, month: str, day: str) -> date | None:
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


class TemporalGrounding:
    """Pure deep Module for anchoring and rendering day-precision expressions."""

    def __init__(self) -> None:
        self.timezone_id = DEFAULT_TIMEZONE_ID

    def anchor(self, text: object, *, observed_at_us: int) -> TemporalAnchor | None:
        if not isinstance(text, str) or not text.strip():
            return None
        matches: list[tuple[int, int, str, date | int | None]] = []
        for match in _RELATIVE_PATTERN.finditer(text):
            matches.append(
                (
                    match.start(),
                    match.end(),
                    match.group(0),
                    _RELATIVE_DAY_OFFSETS[match.group(0)],
                )
            )
        for pattern in (_ISO_DATE_PATTERN, _CHINESE_DATE_PATTERN):
            for match in pattern.finditer(text):
                matches.append(
                    (
                        match.start(),
                        match.end(),
                        match.group(0),
                        _absolute_date(*match.groups()),
                    )
                )
        matches.sort(key=lambda item: (item[0], item[1]))
        if len(matches) != 1 or matches[0][3] is None:
            return None
        anchor_date = _local_date(observed_at_us, self.timezone_id)
        value = matches[0][3]
        target = (
            anchor_date + timedelta(days=value)
            if isinstance(value, int)
            else value
        )
        assert isinstance(target, date)
        return TemporalAnchor(
            original_expression=matches[0][2],
            anchor_date=anchor_date.isoformat(),
            target_date=target.isoformat(),
            timezone_id=self.timezone_id,
        )

    def render(
        self,
        text: object,
        anchor: object,
        *,
        observed_at_us: int,
    ) -> str:
        if not isinstance(text, str) or not isinstance(anchor, TemporalAnchor):
            raise TemporalGroundingFailedClosed("temporal-render-input-invalid")
        if anchor.timezone_id != self.timezone_id:
            raise TemporalGroundingFailedClosed("temporal-render-timezone-mismatch")
        if text.count(anchor.original_expression) != 1:
            raise TemporalGroundingFailedClosed(
                "temporal-render-expression-mismatch"
            )
        current_date = _local_date(observed_at_us, self.timezone_id)
        target_date = date.fromisoformat(anchor.target_date)
        delta = (target_date - current_date).days
        rendered = _CURRENT_RELATIVE_LABELS.get(
            delta,
            f"{target_date.year}年{target_date.month}月{target_date.day}日",
        )
        return text.replace(anchor.original_expression, rendered, 1)


__all__ = [
    "DEFAULT_TIMEZONE_ID",
    "TEMPORAL_POLICY_VERSION",
    "TemporalAnchor",
    "TemporalGrounding",
    "TemporalGroundingFailedClosed",
]
