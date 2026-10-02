"""One whole proposal; Python retains all persistent Domains as typed NoOp."""
from contextlib import contextmanager
from hashlib import sha256

from dynamic_subject_agent.runtime import CognitionEngine, CognitionFailedClosed, ExpressionCandidate
from dynamic_subject_agent.timeline import PreAdmissionRejected
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind, ModelGatewayFailure
from dynamic_subject_agent.first_life_authorization import ShareAuthorizationChanged
from dynamic_subject_agent.first_life_dialogue import is_first_life_dialogue_control
from dynamic_subject_agent.original_whole_chat import (WHOLE_AUTHORITY, OriginalWholeAuthorization,
    whole_projection, validate_whole_reply, digest)
from dataclasses import asdict


class OriginalWholeChatCognition(CognitionEngine):
    adapter_version = "original-whole-chat-cognition-s127-1"
    provider_authority = WHOLE_AUTHORITY
    experimental, test_only = True, False
    supports_subject_tasks, supports_text_effects = False, False

    def __init__(self, *, envelope=None, gateway=None, delivery=None, authorization=None, guard=None):
        self.envelope, self.gateway, self.delivery = envelope, gateway, delivery
        self.authorization, self.guard = authorization, guard
        self._publication = None

    def preflight(self, *, context, command):
        if self.gateway is None:
            raise PreAdmissionRejected("original-whole-chat-unavailable", "The exact whole provider is not assembled.")
        if command.language != "zh" or not command.utterance.strip() or len(command.utterance) > 1000:
            raise PreAdmissionRejected("original-whole-message-invalid", "Whole chat accepts bounded submitted Chinese text.")

    @contextmanager
    def publication_guard(self, plan):
        if self._publication is None or self._publication[0] != plan.operation_ref.operation_id:
            raise ValueError("this whole proposal has no current publication authorization")
        with self.guard(self._publication[1]):
            yield

    def propose(self, *, plan, context, command, basis):
        self._publication = None
        try:
            if is_first_life_dialogue_control(command.utterance):
                raise ValueError("current control must be resolved locally")
            authorization = self.authorization()
            if type(authorization) is not OriginalWholeAuthorization:
                raise ValueError("exact whole authorization required")
            dialogue = context.load_character_dialogue(authorization.history_enabled)
            projection = whole_projection(self.envelope, context.runtime_identity, command.utterance,
                dialogue, authorization.history_enabled)
        except Exception:
            raise CognitionFailedClosed("history", "original-whole-history-unverified", "History and exact whole disclosure are unavailable.") from None
        identity = sha256(plan.operation_ref.authority_scope_id.encode()).hexdigest()
        operation = sha256((plan.operation_ref.operation_id + ":" + plan.attempt_id).encode()).hexdigest()
        claimed = False
        try:
            with self.guard(authorization):
                self.delivery.claim(identity, operation, digest(asdict(projection)))
                claimed = True
                value = self.gateway.execute(ModelTask(ModelTaskKind.CHARACTER_ORIGINAL_WHOLE_REPLY, projection)).value
                text = validate_whole_reply(value)
            self.delivery.record("complete", value=value)
        except Exception as error:
            code = error.code if isinstance(error, ModelGatewayFailure) else "history-changed" if isinstance(error, ShareAuthorizationChanged) else "delivery-unverified"
            safe = {"character-credential-unavailable", "transport-timeout", "transport-delivery-ambiguous", "structured-choice-invalid",
                "expression-invalid", "response-empty-content", "response-incomplete", "provider-failed", "history-changed", "delivery-unverified"}
            if code not in safe:
                code = "provider-failed"
            status = "unavailable" if code == "character-credential-unavailable" else "unknown" if code in ("transport-timeout", "transport-delivery-ambiguous") else "failed-closed"
            if claimed:
                try:
                    self.delivery.record(status)
                except Exception:
                    code = "audit-failed"
            raise CognitionFailedClosed("whole-reply", "original-whole-" + code, "The whole reply did not complete safely; it will not be retried.") from None
        self._publication = (plan.operation_ref.operation_id, authorization)
        return self._bounded_noop_proposal(context=context, basis=basis,
            experience_summary="已提交一轮整体人物回复；台词不成为知识、生活、人格或关系写回。",
            expression_candidate=ExpressionCandidate(text, "zh"))
