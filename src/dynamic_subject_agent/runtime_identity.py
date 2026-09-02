"""Typed minimal projection of one sealed identity into runtime cognition."""

from __future__ import annotations

import re
from dataclasses import dataclass

from dynamic_subject_agent.studio import (
    GenesisSnapshot,
    ParticipantProfile,
    QualifiedRuntimeInput,
)


LEGACY_AVERY_PUBLICATION_KEY = "local-product-deepseek-qri-v1"
_REPLY_SENTENCE_PATTERN = re.compile(r"[^。！？!?]+[。！？!?]?")
_UNSUPPORTED_CURRENT_ACTIVITY_MARKERS = (
    "我也刚",
    "我正好",
    "我刚刚",
    "我刚",
    "我今天",
    "我正在",
    "我已经",
    "我还没",
    "我尚未",
    "我这边",
)


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

    def guard_reply(self, text: object) -> str | None:
        if not isinstance(text, str) or not text.strip():
            return None
        kept = tuple(
            sentence.strip()
            for sentence in _REPLY_SENTENCE_PATTERN.findall(text)
            if sentence.strip()
            and not any(
                marker in sentence
                for marker in _UNSUPPORTED_CURRENT_ACTIVITY_MARKERS
            )
        )
        guarded = "".join(kept).strip()
        return guarded or None

    @classmethod
    def from_sealed_authority(
        cls,
        *,
        qri: QualifiedRuntimeInput,
        profile: ParticipantProfile,
        snapshot: GenesisSnapshot,
    ) -> RuntimeIdentityProjection:
        if (
            not isinstance(qri, QualifiedRuntimeInput)
            or not isinstance(profile, ParticipantProfile)
            or not isinstance(snapshot, GenesisSnapshot)
            or qri.profile_id != profile.profile_id
            or qri.profile_id != snapshot.profile_id
            or qri.genesis_snapshot_id != snapshot.snapshot_id
            or qri.knowledge_snapshot_id != snapshot.knowledge_snapshot_id
        ):
            raise RuntimeIdentityFailedClosed(
                "runtime-identity-sealed-authority-mismatch"
            )
        subject_name = (
            "Avery"
            if qri.publication_key == LEGACY_AVERY_PUBLICATION_KEY
            else profile.display_name
        )
        return cls(
            subject_name=subject_name,
            subject_identity=snapshot.premise.subject_identity,
            canon_start=snapshot.premise.canon_start,
        )


__all__ = [
    "LEGACY_AVERY_PUBLICATION_KEY",
    "RuntimeIdentityFailedClosed",
    "RuntimeIdentityProjection",
]
