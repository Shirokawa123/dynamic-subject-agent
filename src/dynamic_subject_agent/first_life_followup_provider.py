"""V4 followup chat wire; life/share keep their existing exact bytes."""
from dataclasses import asdict

from dynamic_subject_agent.first_life_relevance_provider import DeepSeekFirstLifeRelevanceAdapter
from dynamic_subject_agent.first_life_relevance import PERSONALITY_RELEVANCE_POLICY, CHAT_FOCUS
from dynamic_subject_agent.first_life_followup import (
    FirstLifeChatPlanning, FirstLifeChatExpression, LIFE_CHAT_POLICY, LIFE_CHAT_SELECTION_POLICY,
    LIFE_CHAT_EXPRESSION_POLICY, HISTORY_GROUNDED_POLICY, _validate_sources,
)
from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection
from dynamic_subject_agent.character_communication_trial_provider import communication_protocol
from dynamic_subject_agent.model_gateway import ModelTaskKind
from dynamic_subject_agent.frozen_attempt import canonical_json


class DeepSeekFirstLifeFollowupAdapter(DeepSeekFirstLifeRelevanceAdapter):
    @staticmethod
    def wire(task):
        if task.kind in (ModelTaskKind.CHARACTER_FIRST_LIFE_DECISION, ModelTaskKind.CHARACTER_FIRST_LIFE_SHARE):
            return DeepSeekFirstLifeRelevanceAdapter.wire(task)
        projection = task.payload
        if task.kind is ModelTaskKind.CHARACTER_COMMUNICATION_PLAN:
            if (type(projection) is not FirstLifeChatPlanning or projection.policy != LIFE_CHAT_POLICY
                or projection.conversation.policy != LIFE_CHAT_SELECTION_POLICY):
                raise ValueError("exact grounded planning projection required")
            _validate_sources(projection.dialogue_sources, projection.history_enabled)
            stage, policy = "planning", LIFE_CHAT_SELECTION_POLICY
        elif task.kind is ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION:
            if (type(projection) is not FirstLifeChatExpression or projection.policy != LIFE_CHAT_POLICY
                or projection.conversation.policy != LIFE_CHAT_EXPRESSION_POLICY or projection.focus not in CHAT_FOCUS
                or projection.focus == "explain-encounter" and projection.selected_dialogue):
                raise ValueError("exact grounded expression projection required")
            _validate_sources(projection.selected_dialogue, projection.history_enabled, selected=True)
            stage, policy = "expression", LIFE_CHAT_EXPRESSION_POLICY
        else:
            raise ValueError("unsupported grounded first-life task")
        if (type(projection.runtime_identity) is not RuntimeIdentityProjection
            or type(projection.has_prior_committed_exchange) is not bool):
            raise ValueError("exact grounded identity foreground required")
        protocol = communication_protocol("thinking-high", "low")
        wire = canonical_json(dict(model="deepseek-flash", messages=[dict(role="system",
            content=PERSONALITY_RELEVANCE_POLICY + HISTORY_GROUNDED_POLICY + LIFE_CHAT_POLICY + policy),
            dict(role="user", content=canonical_json(asdict(projection)))], **protocol[stage])).encode()
        if len(wire) > 65536:
            raise ValueError("grounded outbound oversized")
        return wire
