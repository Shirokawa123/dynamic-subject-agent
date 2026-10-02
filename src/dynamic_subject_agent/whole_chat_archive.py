"""Local canonical chat pages; neither a Provider window nor another store."""
from dataclasses import dataclass


@dataclass(frozen=True)
class WholeChatArchiveRequest:
    target_profile_id: str
    target_timeline_id: str
    before_sequence: int | None = None
    query: str = ''


@dataclass(frozen=True)
class WholeChatArchiveRow:
    kind: str
    head_sequence: int
    context_revision: int
    user_text: str = ''
    assistant_text: str = ''
    published_at_us: int = 0
    label: str = ''


@dataclass(frozen=True)
class WholeChatArchiveView:
    status: str
    problem_code: str = ''
    rows: tuple[WholeChatArchiveRow, ...] = ()
    query: str = ''
    next_before_sequence: int | None = None
    has_more: bool = False
    pending: bool = False
    snapshot_head_sequence: int = 0
    context_revision: int = 0
    target_profile_id: str = ''
    target_timeline_id: str = ''
    limitations: tuple[str, ...] = ()
