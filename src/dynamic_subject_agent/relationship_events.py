"""Closed relationship event vocabulary (port of legacy relationship_policy.py).

Pure data module: importable by Domain modules, cognition modules and
adapters without import cycles. The vocabulary and its semantics are the
specification ported from config/relationship_policy.json v1.
"""

from __future__ import annotations

UPDATE_EVENTS = (
    "stable_positive_interaction",
    "promise_fulfilled",
    "boundary_respected",
    "boundary_violation",
    "repeated_boundary_violation",
    "apology_only",
    "repair_action",
)
NO_UPDATE_EVENTS = (
    "praise_only",
    "relationship_claim",
    "promise_only",
    "no_persistent_evidence",
)
ALL_RELATIONSHIP_EVENTS = frozenset((*UPDATE_EVENTS, *NO_UPDATE_EVENTS))

__all__ = [
    "ALL_RELATIONSHIP_EVENTS",
    "NO_UPDATE_EVENTS",
    "UPDATE_EVENTS",
]
