"""Explicit production chat Adapter; old trial envelopes never qualify."""
from dataclasses import asdict

from dynamic_subject_agent.model_gateway import ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelTaskKind, ModelResult, ModelGatewayFailure
from dynamic_subject_agent.deepseek import _post_json_reply_content, DeepSeekResponseDiagnosticFailure, DEEPSEEK_ENDPOINT, DEEPSEEK_TIMEOUT_SECONDS
from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
from dynamic_subject_agent.character_communication_trial_provider import communication_protocol
from dynamic_subject_agent.reviewed_character_chat import ReviewedChatPlanning, ReviewedChatExpression, PERSONALITY_POLICY, HISTORY_POLICY
from dynamic_subject_agent.character_communication_plan import PLAN_POLICY, EXPRESSION_POLICY, _validate_projection
from dynamic_subject_agent.frozen_attempt import canonical_json


class DeepSeekReviewedCharacterChatAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities("deepseek", "deepseek-flash", False, (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self, *, transport, credential_ref):
        if DEEPSEEK_ENDPOINT != "https://api.deepseek.com/chat/completions" or DEEPSEEK_TIMEOUT_SECONDS != 30:
            raise ValueError("approved character protocol changed")
        self.transport, self.credential_ref = transport, credential_ref

    @staticmethod
    def wire(projection, stage):
        expected = ReviewedChatPlanning if stage == "planning" else ReviewedChatExpression
        if type(projection) is not expected or projection.policy != PERSONALITY_POLICY + HISTORY_POLICY:
            raise ValueError("exact reviewed chat projection required")
        if stage == "planning": _validate_projection(projection.conversation)
        elif projection.conversation.policy != EXPRESSION_POLICY: raise ValueError("expression policy changed")
        if (len(projection.recent_dialogue) > 2 or sum(len(t.user_text) + len(t.assistant_text) for t in projection.recent_dialogue) > 4000
            or (not projection.history_enabled and projection.recent_dialogue)):
            raise ValueError("bounded dialogue required")
        policy = projection.policy + (PLAN_POLICY if stage == "planning" else EXPRESSION_POLICY)
        protocol = communication_protocol("thinking-high", "low")
        body = dict(model="deepseek-flash", messages=[dict(role="system", content=policy), dict(role="user", content=canonical_json(asdict(projection)))], **protocol[stage])
        wire = canonical_json(body).encode()
        if len(wire) > 65536: raise ValueError("reviewed chat request oversized")
        return wire

    def invoke(self, task):
        if task.kind is ModelTaskKind.CHARACTER_COMMUNICATION_PLAN: stage = "planning"
        elif task.kind is ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION: stage = "expression"
        else: raise ValueError("unsupported character chat task")
        wire = self.wire(task.payload, stage)
        try:
            value = _post_json_reply_content(self.transport, self.credential_ref, wire, max_output_tokens=4096,
                require_complete=True, discard_reasoning=True, safe_diagnostics=True)
        except CharacterCredentialUnavailable:
            raise ModelGatewayFailure("character-credential-unavailable") from None
        except DeepSeekResponseDiagnosticFailure as failure:
            raise ModelGatewayFailure(failure.diagnostic_code) from None
        return ModelResult(task.kind, value)
