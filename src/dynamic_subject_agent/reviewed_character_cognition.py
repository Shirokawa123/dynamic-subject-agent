"""A distinct no-egress authority for a sealed reviewed character."""
from dynamic_subject_agent.reviewed_character_definition import REVIEWED_CHARACTER_AUTHORITY
from dynamic_subject_agent.runtime import CognitionEngine, CognitionFailedClosed
from dynamic_subject_agent.timeline import PreAdmissionRejected


class ReviewedCharacterDormantCognition(CognitionEngine):
    adapter_version = "reviewed-character-dormant-cognition-1"
    provider_authority = REVIEWED_CHARACTER_AUTHORITY
    experimental = True
    test_only = False
    supports_subject_tasks = False
    supports_text_effects = False

    def preflight(self, *, context, command):
        raise PreAdmissionRejected("reviewed-character-chat-unavailable", "The sealed character has no active production chat lane.")

    def propose(self, *, plan, context, command, basis):
        raise CognitionFailedClosed("provider", "reviewed-character-chat-unavailable", "No provider is assembled for this identity.")
