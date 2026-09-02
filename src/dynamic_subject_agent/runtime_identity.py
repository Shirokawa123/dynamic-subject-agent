"""Typed minimal projection of one sealed identity into runtime cognition."""

from __future__ import annotations

from dataclasses import dataclass


class RuntimeIdentityFailedClosed(ValueError):
    """The sealed authority cannot produce one safe runtime identity view."""


def _text(value: object, field: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or "\x00" in value
    ):
        raise RuntimeIdentityFailedClosed(f"runtime-identity-{field}-invalid")
    return value


@dataclass(frozen=True)
class RuntimeIdentityProjection:
    subject_name: str
    subject_identity: str
    canon_start: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "subject_name",
            _text(self.subject_name, "subject-name", 128),
        )
        object.__setattr__(
            self,
            "subject_identity",
            _text(self.subject_identity, "subject-identity", 2_000),
        )
        object.__setattr__(
            self,
            "canon_start",
            _text(self.canon_start, "canon-start", 4_000),
        )

__all__ = [
    "RuntimeIdentityFailedClosed",
    "RuntimeIdentityProjection",
]
