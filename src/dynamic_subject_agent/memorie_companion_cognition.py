"""Single-call strategy behind the existing reviewed-chat Runtime/Publication."""
from contextlib import contextmanager
from hashlib import sha256

from dynamic_subject_agent.memorie_companion_contract import projection, wire, validate_reply, PURPOSE
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind, ModelGatewayFailure
from dynamic_subject_agent.runtime import CognitionFailedClosed, ExpressionCandidate
from dynamic_subject_agent.first_life_authorization import ShareAuthorizationChanged
from dynamic_subject_agent.reply_review_diagnostics import REVIEW_DIAGNOSTIC_CODES


class MemorieCompanionSession:
    def __init__(self, *, envelope, contract, audit, gateway, authorization, guard):
        self.envelope, self.contract, self.audit, self.gateway = envelope, contract, audit, gateway
        self.authorization, self.guard = authorization, guard
        self._publication = None

    @contextmanager
    def publication_guard(self, plan):
        if self._publication is None or self._publication[0] != plan.operation_ref.operation_id:
            raise ValueError('no current Memorie publication authorization')
        with self.guard(self._publication[1]):
            yield

    def propose(self, engine, *, plan, context, command, basis):
        self._publication = None
        try:
            authorization = self.authorization()
            dialogue = context.load_character_dialogue(authorization['history_enabled'])
            payload = projection(self.envelope, command.utterance, dialogue, authorization['history_enabled'],
                version=self.contract['version'])
        except Exception:
            raise CognitionFailedClosed('history', 'memorie-history-unverified', 'The current committed dialogue could not be verified.') from None
        # A retry with another attempt ID must not redeliver the same operation.
        operation = sha256((plan.operation_ref.authority_scope_id + ':' + plan.operation_ref.operation_id).encode()).hexdigest()
        claimed = False
        try:
            with self.guard(authorization):
                self.audit.claim(operation, sha256(wire(payload)).hexdigest(), purpose=PURPOSE,
                    run_digest=authorization['contract_digest'])
                claimed = True
                value = self.gateway.execute(ModelTask(ModelTaskKind.MEMORIE_COMPANION_REPLY, payload)).value
                text = validate_reply(value)
            self.audit.record(operation, status='complete', output_digest=sha256(text.encode()).hexdigest())
        except Exception as error:
            safe = (REVIEW_DIAGNOSTIC_CODES - {'review-schema', 'review-quote', 'review-label'}) | {
                'character-credential-unavailable', 'expression-invalid'}
            code = error.code if isinstance(error, ModelGatewayFailure) and error.code in safe else (
                'history-changed' if isinstance(error, ShareAuthorizationChanged) else 'delivery-unverified')
            status = 'unavailable' if code == 'character-credential-unavailable' else 'unknown' if code in (
                'transport-timeout', 'transport-delivery-ambiguous') else 'failed-closed'
            if claimed:
                try:
                    self.audit.record(operation, status=status)
                except Exception:
                    code = 'audit-failed'
            raise CognitionFailedClosed('reply', 'memorie-' + code, 'The reply did not complete safely and will not be retried.') from None
        self._publication = (plan.operation_ref.operation_id, authorization)
        return engine._bounded_noop_proposal(context=context, basis=basis,
            experience_summary='已提交一轮梅莫莉交流；自由回复不写回知识、人格、关系或游戏事件。',
            expression_candidate=ExpressionCandidate(text, 'zh'))
