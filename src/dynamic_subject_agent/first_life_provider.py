"""Explicit life/chat/share protocol; no old six-domain or trial use."""
from dataclasses import asdict

from dynamic_subject_agent.deepseek import _post_json_reply_content, DeepSeekResponseDiagnosticFailure, DEEPSEEK_ENDPOINT, DEEPSEEK_TIMEOUT_SECONDS
from dynamic_subject_agent.model_gateway import ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelTaskKind, ModelResult, ModelGatewayFailure
from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
from dynamic_subject_agent.character_communication_trial_provider import communication_protocol
from dynamic_subject_agent.character_personality import PERSONALITY_POLICY
from dynamic_subject_agent.reviewed_character_chat import HISTORY_POLICY
from dynamic_subject_agent.first_life import LIFE_POLICY, SHARE_POLICY, LIFE_CHAT_POLICY, LIFE_CHAT_SELECTION_POLICY, LIFE_CHAT_EXPRESSION_POLICY
from dynamic_subject_agent.first_life_projection import LifeModelProjection, FirstLifeChatPlanning, FirstLifeChatExpression
from dynamic_subject_agent.frozen_attempt import canonical_json


class DeepSeekFirstLifeAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities("deepseek", "deepseek-flash", False, (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self, *, transport, credential_ref):
        if DEEPSEEK_ENDPOINT != "https://api.deepseek.com/chat/completions" or DEEPSEEK_TIMEOUT_SECONDS != 30:
            raise ValueError("approved first-life protocol changed")
        self.transport, self.credential_ref = transport, credential_ref

    @staticmethod
    def wire(task):
        projection = task.payload
        if task.kind is ModelTaskKind.CHARACTER_FIRST_LIFE_DECISION:
            if type(projection) is not LifeModelProjection or projection.policy != LIFE_POLICY: raise ValueError("exact life decision required")
            stage, policy = "planning", LIFE_POLICY
        elif task.kind is ModelTaskKind.CHARACTER_FIRST_LIFE_SHARE:
            if type(projection) is not LifeModelProjection or projection.policy != SHARE_POLICY: raise ValueError("exact committed-event share required")
            stage, policy = "expression", SHARE_POLICY
        elif task.kind is ModelTaskKind.CHARACTER_COMMUNICATION_PLAN:
            if type(projection) is not FirstLifeChatPlanning or projection.policy != LIFE_CHAT_POLICY: raise ValueError("exact life chat selection required")
            stage, policy = "planning", PERSONALITY_POLICY + HISTORY_POLICY + LIFE_CHAT_POLICY + LIFE_CHAT_SELECTION_POLICY
        elif task.kind is ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION:
            if type(projection) is not FirstLifeChatExpression or projection.policy != LIFE_CHAT_POLICY: raise ValueError("exact life chat expression required")
            stage, policy = "expression", PERSONALITY_POLICY + HISTORY_POLICY + LIFE_CHAT_POLICY + LIFE_CHAT_EXPRESSION_POLICY
        else: raise ValueError("unsupported first-life task")
        protocol = communication_protocol("thinking-high", "low")
        body = dict(model="deepseek-flash", messages=[dict(role="system", content=policy), dict(role="user", content=canonical_json(asdict(projection)))], **protocol[stage])
        wire = canonical_json(body).encode()
        if len(wire) > 65536: raise ValueError("first-life outbound oversized")
        return wire

    def invoke(self, task):
        wire = self.wire(task)
        try:
            value = _post_json_reply_content(self.transport, self.credential_ref, wire, max_output_tokens=4096,
                require_complete=True, discard_reasoning=True, safe_diagnostics=True)
        except CharacterCredentialUnavailable: raise ModelGatewayFailure("character-credential-unavailable") from None
        except DeepSeekResponseDiagnosticFailure as failure: raise ModelGatewayFailure(failure.diagnostic_code) from None
        return ModelResult(task.kind, value)
