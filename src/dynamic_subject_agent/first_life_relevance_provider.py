"""Explicit v2 chat/share wire; v1 life-decision wire is reused byte for byte."""
from dataclasses import asdict

from dynamic_subject_agent.first_life_provider import DeepSeekFirstLifeAdapter
from dynamic_subject_agent.first_life_relevance import (
    FirstLifeChatPlanning, FirstLifeChatExpression, FirstLifeShareProjection,
    PERSONALITY_RELEVANCE_POLICY, LIFE_CHAT_POLICY, LIFE_CHAT_SELECTION_POLICY,
    LIFE_CHAT_EXPRESSION_POLICY, SHARE_POLICY, CHAT_FOCUS, _dialogue,
)
from dynamic_subject_agent.reviewed_character_chat import HISTORY_POLICY, CharacterDialogueBasis
from dynamic_subject_agent.character_communication_trial_provider import communication_protocol
from dynamic_subject_agent.model_gateway import ModelTaskKind
from dynamic_subject_agent.frozen_attempt import canonical_json


class DeepSeekFirstLifeRelevanceAdapter(DeepSeekFirstLifeAdapter):
    @staticmethod
    def wire(task):
        if task.kind is ModelTaskKind.CHARACTER_FIRST_LIFE_DECISION:
            return DeepSeekFirstLifeAdapter.wire(task)
        projection = task.payload
        if task.kind is ModelTaskKind.CHARACTER_FIRST_LIFE_SHARE:
            if type(projection) is not FirstLifeShareProjection or projection.policy != SHARE_POLICY:
                raise ValueError("exact v2 share projection required")
            stage, policy = "expression", PERSONALITY_RELEVANCE_POLICY + HISTORY_POLICY + SHARE_POLICY
        elif task.kind is ModelTaskKind.CHARACTER_COMMUNICATION_PLAN:
            if (type(projection) is not FirstLifeChatPlanning or projection.policy != LIFE_CHAT_POLICY
                or projection.conversation.policy != LIFE_CHAT_SELECTION_POLICY):
                raise ValueError("exact v2 chat planning required")
            stage, policy = "planning", PERSONALITY_RELEVANCE_POLICY + HISTORY_POLICY + LIFE_CHAT_POLICY + LIFE_CHAT_SELECTION_POLICY
        elif task.kind is ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION:
            if (type(projection) is not FirstLifeChatExpression or projection.policy != LIFE_CHAT_POLICY
                or projection.conversation.policy != LIFE_CHAT_EXPRESSION_POLICY or projection.focus not in CHAT_FOCUS):
                raise ValueError("exact v2 chat expression required")
            stage, policy = "expression", PERSONALITY_RELEVANCE_POLICY + HISTORY_POLICY + LIFE_CHAT_POLICY + LIFE_CHAT_EXPRESSION_POLICY
        else:
            raise ValueError("unsupported v2 first-life task")
        _dialogue(projection.runtime_identity, CharacterDialogueBasis("available",
            projection.has_prior_committed_exchange, projection.recent_dialogue), projection.history_enabled)
        protocol = communication_protocol("thinking-high", "low")
        wire = canonical_json(dict(model="deepseek-flash", messages=[dict(role="system", content=policy),
            dict(role="user", content=canonical_json(asdict(projection)))], **protocol[stage])).encode()
        if len(wire) > 65536:
            raise ValueError("v2 first-life outbound oversized")
        return wire
