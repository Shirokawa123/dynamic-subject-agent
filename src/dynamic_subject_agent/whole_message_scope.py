"""One local draft scope snapshot; never an Admission or permission to send."""
from dataclasses import dataclass

from dynamic_subject_agent.character_chat_context import SelfKnowledge
from dynamic_subject_agent.recent_dialogue import RecentDialogueTurn


@dataclass(frozen=True)
class WholeMessageScopePreviewRequest:
    target_profile_id: str
    target_timeline_id: str
    text: str


@dataclass(frozen=True)
class WholeMessageScopePreviewView:
    status: str
    problem_code: str = ""
    current_message: str = ""
    history_enabled: bool = False
    has_prior_committed_exchange: bool = False
    character_core: tuple[SelfKnowledge, ...] = ()
    self_knowledge: tuple[SelfKnowledge, ...] = ()
    personality_count: int = 0
    recent_dialogue: tuple[RecentDialogueTurn, ...] = ()
    context_revision: int = 0
    cutoff_sequence: int = 0
    projection_digest: str = ""
    snapshot_fingerprint: str = ""
    limitations: tuple[str, ...] = ()
