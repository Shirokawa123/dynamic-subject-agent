"""Independently qualified shared proposals; canonical adjudication stays Python."""
from contextlib import contextmanager
from dataclasses import asdict, replace

from dynamic_subject_agent.runtime import CognitionFailedClosed, ExpressionCandidate
from dynamic_subject_agent.timeline import PreAdmissionRejected
from dynamic_subject_agent.original_whole_chat_cognition import OriginalWholeChatCognition
from dynamic_subject_agent.original_whole_chat import OriginalWholeAuthorization, validate_whole_reply
from dynamic_subject_agent.first_life_authorization import ShareAuthorizationChanged
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind, ModelGatewayFailure
from dynamic_subject_agent.whole_context_boundary import WholeContextInput, CONTEXT_RECEIPT
from dynamic_subject_agent.whole_dialogue_scope import whole_dialogue_scope, WITHDRAWAL, UNRESOLVED
from dynamic_subject_agent.shared_activity import (
    SHARED_AUTHORITY, SHARED_LIVE_AUTHORITY, SharedActivityInput, build_record, build_choice_preview, build_reply_preview,
    shared_variant_for_contract)


class SharedActivityCognition(OriginalWholeChatCognition):
    adapter_version = 'shared-activity-local-cognition-s139-1'
    supports_shared_activity = True

    def __init__(self, *, envelope=None, gateway=None, contract=None, authorization=None, guard=None,
                 provider_authority=SHARED_AUTHORITY, delivery=None, snapshot_loader=None):
        super().__init__(envelope=envelope, gateway=gateway, authorization=authorization, guard=guard,
            provider_authority=provider_authority)
        self.supports_whole_context = True
        if provider_authority == SHARED_LIVE_AUTHORITY:
            self.adapter_version = 'shared-activity-live-cognition-s139-1'
        self.contract = contract
        self.delivery, self.snapshot_loader = delivery, snapshot_loader

    def preflight(self, *, context, command):
        live = self.provider_authority == SHARED_LIVE_AUTHORITY
        if live:
            from dynamic_subject_agent.shared_activity_live import SharedActivityDelivery
            if (self.gateway is None or self.gateway.capabilities.local is not False
                or self.gateway.capabilities.provider_id != 'deepseek' or type(self.delivery) is not SharedActivityDelivery
                or self.snapshot_loader is None):
                raise PreAdmissionRejected('shared-approved-gateway-required', 'exact live shared qualification is required')
            self.delivery.grant.validate()
            from dynamic_subject_agent.original_whole_chat import contract_variant
            if (contract_variant(self.contract) != 'shared-live' or self.contract != self.delivery.contract
                or shared_variant_for_contract(self.contract) != self.delivery.grant.technical_variant):
                raise ValueError('current shared live expression qualification changed')
        elif self.gateway is None or self.gateway.capabilities.local is not True:
            raise PreAdmissionRejected('shared-local-gateway-required', 'this qualification has no remote data grant')
        else:
            from dynamic_subject_agent.original_whole_chat import contract_variant
            if contract_variant(self.contract) != 'shared-local':
                raise ValueError('exact local preparation qualification required')
        if type(command) is SharedActivityInput:
            return
        return super().preflight(context=context, command=command)

    @contextmanager
    def publication_guard(self, plan):
        record = plan.shared_record
        if record is None or self.guard is None:
            raise ValueError('complete shared preparation required')
        if self._context_revision_at(plan.expected_basis.head_sequence) != record.context_revision:
            raise ShareAuthorizationChanged('shared-context-revision-changed')
        with self.guard(OriginalWholeAuthorization(**record.authorization)):
            yield

    def choice_preview(self, identity, view):
        return build_choice_preview(self.envelope, identity, view, self.contract)

    def _execute(self, task, *, plan, context, command, authorization):
        if self.provider_authority == SHARED_LIVE_AUTHORITY:
            from dynamic_subject_agent.original_whole_chat import validate_whole_envelope
            def rebuild():
                snapshot = self.snapshot_loader()
                if (snapshot['authorization'] != authorization or snapshot['contract'] != self.delivery.contract
                    or self.contract != self.delivery.contract):
                    raise ValueError('shared live scope changed')
                validate_whole_envelope(snapshot['envelope'], snapshot['contract'])
                view = context.load_shared_activity(authorization)
                if view['basis'] != asdict(plan.expected_basis):
                    raise ValueError('shared canonical prefix changed')
                if task.kind is ModelTaskKind.SHARED_ACTIVITY_CHOICE:
                    return build_choice_preview(snapshot['envelope'], snapshot['identity'], view, snapshot['contract'])
                dialogue = context.load_character_dialogue(authorization.history_enabled)
                return build_reply_preview(snapshot['envelope'], snapshot['identity'], command.utterance, dialogue,
                    authorization.history_enabled, view, snapshot['contract'])
            try:
                self.delivery.claim(plan.operation_ref.operation_id + ':' + plan.attempt_id, task, rebuild)
            except Exception:
                raise ModelGatewayFailure('delivery-unverified') from None
        return self.gateway.execute(task).value

    def propose(self, *, plan, context, command, basis):
        if type(command) not in (SharedActivityInput, WholeContextInput):
            scope = whole_dialogue_scope(command.utterance)
            if scope in (WITHDRAWAL, UNRESOLVED):
                code = 'original-whole-history-withdrawn' if scope == WITHDRAWAL else 'original-whole-history-control-unresolved'
                raise CognitionFailedClosed('history', code, 'The current disclosure act is not sent.')
        try:
            authorization = self.authorization()
            view = context.load_shared_activity(authorization)
            choice = None
            if type(command) is WholeContextInput:
                text = CONTEXT_RECEIPT
            elif type(command) is SharedActivityInput and command.input_kind != 'advance':
                text = '已选定这条用户原话作为共同依据。' if command.input_kind == 'select' else '已停用这条共同依据；原记录保留。'
            else:
                with self.guard(authorization):
                    if type(command) is SharedActivityInput:
                        preview = self.choice_preview(context.runtime_identity, view)
                        choice = self._execute(ModelTask(ModelTaskKind.SHARED_ACTIVITY_CHOICE, preview), plan=plan,
                            context=context, command=command, authorization=authorization)
                        text = '本次活动取舍已提交。'
                    else:
                        dialogue = context.load_character_dialogue(authorization.history_enabled)
                        preview = build_reply_preview(self.envelope, context.runtime_identity, command.utterance, dialogue,
                            authorization.history_enabled, view, self.contract)
                        value = self._execute(ModelTask(ModelTaskKind.SHARED_ACTIVITY_REPLY, preview), plan=plan,
                            context=context, command=command, authorization=authorization)
                        text = validate_whole_reply(value)
            record = build_record(view['record'], command=command, authorization=authorization,
                cutoff=view['cutoff_sequence'], context_revision=view['context_revision'],
                head_sequence=plan.expected_basis.head_sequence+1, choice=choice, dialogue_dependencies=view['dialogue_dependencies'])
            if record.kind == 'decision':
                text = record.result.event.summary
            proposal = self._bounded_noop_proposal(context=context, basis=basis,
                experience_summary='已提交有来源的本地活动记录；用户原话不成为世界事实或人格。',
                expression_candidate=ExpressionCandidate(text, 'zh'))
            return replace(proposal, shared_record=record)
        except CognitionFailedClosed:
            raise
        except Exception as error:
            from dynamic_subject_agent.reply_review_diagnostics import REVIEW_DIAGNOSTIC_CODES
            code = error.code if isinstance(error, ModelGatewayFailure) else 'history-changed' if isinstance(error, ShareAuthorizationChanged) else 'provider-failed'
            if code not in REVIEW_DIAGNOSTIC_CODES | {'character-credential-unavailable', 'structured-choice-invalid', 'expression-invalid', 'audit-failed', 'delivery-unverified', 'history-changed'}:
                code = 'provider-failed'
            raise CognitionFailedClosed('whole-reply', 'original-whole-' + code,
                'The shared proposal failed; no activity event or automatic retry is produced.') from None
