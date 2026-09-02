"""Deterministic expression safety for runtime-identity-grounded replies."""

from __future__ import annotations

import re


_SENTENCE_PATTERN = re.compile(r"[^。！？!?]+[。！？!?]?")
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


def guard_runtime_identity_reply(text: object) -> str | None:
    """Remove current subject activity; no Slice-16 reply input can ground one."""

    if not isinstance(text, str) or not text.strip():
        return None
    kept = tuple(
        sentence.strip()
        for sentence in _SENTENCE_PATTERN.findall(text)
        if sentence.strip()
        and not any(
            marker in sentence
            for marker in _UNSUPPORTED_CURRENT_ACTIVITY_MARKERS
        )
    )
    guarded = "".join(kept).strip()
    return guarded or None


__all__ = ["guard_runtime_identity_reply"]
