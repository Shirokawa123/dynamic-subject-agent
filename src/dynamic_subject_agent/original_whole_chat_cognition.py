"""One whole proposal; Python retains all persistent Domains as typed NoOp."""
from contextlib import contextmanager
from hashlib import sha256

from dynamic_subject_agent.runtime import CognitionEngine, CognitionFailedClosed, ExpressionCandidate
from dynamic_subject_agent.timeline import PreAdmissionRejected
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind, ModelGatewayFailure
from dynamic_subject_agent.first_life_authorization import ShareAuthorizationChanged
from dynamic_subject_agent.whole_dialogue_scope import whole_dialogue_scope, WITHDRAWAL, UNRESOLVED, UNSUPPORTED
from dynamic_subject_agent.original_whole_chat import (WHOLE_AUTHORITY, OriginalWholeAuthorization,
    projection_for_contract, validate_whole_reply, digest)
from dynamic_subject_agent.reply_review_diagnostics import REVIEW_DIAGNOSTIC_CODES
from dataclasses import asdict
from dynamic_subject_agent.whole_context_boundary import CONTEXT_AUTHORITY, WholeContextInput, CONTEXT_RECEIPT


class OriginalWholeChatCognition(CognitionEngine):
    adapter_version = "original-whole-chat-cognition-s127-1"
    provider_authority = WHOLE_AUTHORITY
    experimental, test_only = True, False
    supports_subject_tasks, supports_text_effects = False, False

    def __init__(self, *, envelope=None, gateway=None, delivery=None, authorization=None, guard=None, provider_authority=WHOLE_AUTHORITY):
        self.envelope, self.gateway, self.delivery = envelope, gateway, delivery
        self.authorization, self.guard = authorization, guard
        self._publication = None
        self.provider_authority = provider_authority
        self.supports_whole_context = provider_authority == CONTEXT_AUTHORITY
        self._publication_context_revision = 0

    def preflight(self, *, context, command):
        if type(command) is WholeContextInput:
            if not self.supports_whole_context or self.guard is None:
                raise PreAdmissionRejected("whole-context-unavailable", "No exact local context control is assembled.")
            return
        if self.gateway is None:
            raise PreAdmissionRejected("original-whole-chat-unavailable", "The exact whole provider is not assembled.")
        if command.language != "zh" or not command.utterance.strip() or len(command.utterance) > 1000:
            raise PreAdmissionRejected("original-whole-message-invalid", "Whole chat accepts bounded submitted Chinese text.")
        if whole_dialogue_scope(command.utterance) == UNSUPPORTED:
            raise PreAdmissionRejected('original-whole-operation-unavailable', 'Whole chat cannot perform memory, goal or file operations.')

    @contextmanager
    def publication_guard(self, plan):
        if self._publication is None or self._publication[0] != plan.operation_ref.operation_id:
            raise ValueError("this whole proposal has no current publication authorization")
        if self.supports_whole_context and self._context_revision_at(plan.expected_basis.head_sequence) != self._publication_context_revision:
            raise ShareAuthorizationChanged("whole-context-revision-changed")
        with self.guard(self._publication[1]):
            yield

    def propose(self, *, plan, context, command, basis):
        self._publication = None
        if type(command) is WholeContextInput:
            self._publication = (plan.operation_ref.operation_id, OriginalWholeAuthorization(**command.authorization))
            self._publication_context_revision = command.expected_revision
            return self._bounded_noop_proposal(context=context, basis=basis,
                experience_summary="已建立本地交流边界；人物、旧记录与历史开关保持。",
                expression_candidate=ExpressionCandidate(CONTEXT_RECEIPT, "zh"))
        scope = whole_dialogue_scope(command.utterance)
        if scope in (WITHDRAWAL, UNRESOLVED):
            code = 'original-whole-history-withdrawn' if scope == WITHDRAWAL else 'original-whole-history-control-unresolved'
            raise CognitionFailedClosed('history', code, 'This disclosure act is not sent; no memory revision or deletion is claimed.')
        try:
            authorization = self.authorization()
            if type(authorization) is not OriginalWholeAuthorization:
                raise ValueError("exact whole authorization required")
            dialogue = context.load_character_dialogue(authorization.history_enabled)
            projection = projection_for_contract(self.envelope, context.runtime_identity, command.utterance,
                dialogue, authorization.history_enabled, self.delivery.contract)
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
            safe = (REVIEW_DIAGNOSTIC_CODES - {"review-schema", "review-quote", "review-label"}) | {
                "character-credential-unavailable", "structured-choice-invalid", "expression-invalid", "provider-failed", "history-changed", "delivery-unverified"}
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
        self._publication_context_revision = context.load_whole_context()["context_revision"] if self.supports_whole_context else 0
        return self._bounded_noop_proposal(context=context, basis=basis,
            experience_summary="已提交一轮整体人物回复；台词不成为知识、生活、人格或关系写回。",
            expression_candidate=ExpressionCandidate(text, "zh"))
