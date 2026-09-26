"""Two proposals for one character utterance; all persistent Domain effects are NoOp."""
from dataclasses import asdict
from hashlib import sha256

from dynamic_subject_agent.runtime import CognitionEngine, CognitionFailedClosed, ExpressionCandidate
from dynamic_subject_agent.timeline import PreAdmissionRejected
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind, ModelGatewayFailure
from dynamic_subject_agent.character_communication_plan import _validated_expression
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.reply_review_diagnostics import REVIEW_DIAGNOSTIC_CODES
from dynamic_subject_agent.reviewed_character_chat import CHAT_AUTHORITY, planning_projection, expression_projection


class ReviewedCharacterChatCognition(CognitionEngine):
    adapter_version = "reviewed-character-chat-cognition-1"
    provider_authority = CHAT_AUTHORITY
    experimental = True
    test_only = False
    supports_subject_tasks = False
    supports_text_effects = False

    def __init__(self, *, envelope=None, gateway=None, budget=None, history_preference=None):
        self.envelope, self.gateway, self.budget, self.history_preference = envelope, gateway, budget, history_preference

    def preflight(self, *, context, command):
        if self.gateway is None: raise PreAdmissionRejected("reviewed-character-chat-unavailable", "The character chat provider is not assembled.")
        if command.language != "zh" or len(command.utterance) > 1000:
            raise PreAdmissionRejected("reviewed-character-message-invalid", "Chinese character messages accept at most 1000 characters.")
    def _call(self, plan, stage, projection):
        operation = sha256((plan.operation_ref.operation_id + ":" + plan.attempt_id).encode()).hexdigest()
        identity = sha256(plan.operation_ref.authority_scope_id.encode()).hexdigest()
        request_sha = sha256(canonical_json(asdict(projection)).encode()).hexdigest()
        try:
            self.budget.claim(identity, operation, stage, request_sha)
        except Exception:
            raise CognitionFailedClosed(stage, "reviewed-chat-attempt-unavailable", "An existing or unverified stage will not be sent again.") from None
        try:
            kind = ModelTaskKind.CHARACTER_COMMUNICATION_PLAN if stage == "planning" else ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION
            value = self.gateway.execute(ModelTask(kind, projection)).value
            try:
                if stage == "planning": expression_projection(projection, value)
                else: _validated_expression(value)
            except Exception:
                raise ModelGatewayFailure("plan-invalid" if stage == "planning" else "expression-invalid") from None
        except Exception as error:
            allowed = (REVIEW_DIAGNOSTIC_CODES - {"review-schema", "review-quote", "review-label"}) | {"character-credential-unavailable", "plan-invalid", "expression-invalid"}
            code = error.code if isinstance(error, ModelGatewayFailure) and error.code in allowed else "provider-failed"
            status = "unavailable" if code == "character-credential-unavailable" else "unknown" if code in ("transport-timeout", "transport-delivery-ambiguous") else "failed-closed"
            try: self.budget.record(identity, operation, stage, status=status)
            except Exception: code = "reviewed-chat-audit-failed"
            raise CognitionFailedClosed(stage, "reviewed-chat-" + code, "The bounded character stage did not complete safely.") from None
        try:
            self.budget.record(identity, operation, stage, status="complete", output_digest=sha256(canonical_json(value).encode()).hexdigest())
        except Exception:
            raise CognitionFailedClosed(stage, "reviewed-chat-audit-failed", "Completed delivery could not be audited safely.") from None
        return value

    def propose(self, *, plan, context, command, basis):
        try:
            if self.budget.counts()[2] < 2: raise ValueError("budget insufficient")
        except Exception:
            raise CognitionFailedClosed("budget", "reviewed-chat-budget-unavailable", "A new turn has no verified two-stage budget.") from None
        try:
            enabled = self.history_preference()
            if type(enabled) is not bool or context.load_character_dialogue is None: raise ValueError("history policy unavailable")
            dialogue = context.load_character_dialogue(enabled)
            planning = planning_projection(self.envelope, context.runtime_identity, command.utterance, dialogue, enabled)
        except Exception:
            raise CognitionFailedClosed("history", "reviewed-chat-history-unverified", "Dialogue integrity or disclosure could not be confirmed.") from None
        selected = self._call(plan, "planning", planning)
        try:
            if self.history_preference() != enabled: raise ValueError("history disclosure changed during planning")
        except Exception:
            raise CognitionFailedClosed("history", "reviewed-chat-history-changed", "Disclosure or sealed authority changed before expression.") from None
        try: expression = expression_projection(planning, selected)
        except Exception:
            raise CognitionFailedClosed("planning", "reviewed-chat-plan-invalid", "The model did not return a legal action and current fact references.") from None
        value = self._call(plan, "expression", expression)
        try: text = _validated_expression(value)
        except Exception:
            raise CognitionFailedClosed("expression", "reviewed-chat-expression-invalid", "No complete bounded expression was returned.") from None
        return self._bounded_noop_proposal(context=context, basis=basis,
            experience_summary="已提交一轮人物聊天；自由台词未成为知识、生活事件或持久人格依据。",
            expression_candidate=ExpressionCandidate(text, "zh"))
