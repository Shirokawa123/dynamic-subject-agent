"""Independent LOCAL S145 cognition; Python owns the complete state delta."""
from contextlib import contextmanager
from dataclasses import asdict, replace

from dynamic_subject_agent.shared_activity_cognition import SharedActivityCognition
from dynamic_subject_agent.original_whole_chat_cognition import OriginalWholeChatCognition
from dynamic_subject_agent.original_whole_chat import OriginalWholeAuthorization, contract_variant, validate_whole_reply
from dynamic_subject_agent.shared_activity import SharedActivityInput, WORKING_LIVE_AUTHORITY
from dynamic_subject_agent.working_understanding import (
    WORKING_AUTHORITY, build_form_preview, build_working_choice_preview, build_working_reply_preview, build_working_record)
from dynamic_subject_agent.whole_context_boundary import WholeContextInput, CONTEXT_RECEIPT
from dynamic_subject_agent.whole_dialogue_scope import whole_dialogue_scope, WITHDRAWAL, UNRESOLVED
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind, ModelGatewayFailure
from dynamic_subject_agent.runtime import CognitionFailedClosed, ExpressionCandidate
from dynamic_subject_agent.timeline import PreAdmissionRejected
from dynamic_subject_agent.first_life_authorization import ShareAuthorizationChanged


class WorkingUnderstandingCognition(SharedActivityCognition):
    adapter_version = 'working-understanding-local-cognition-s145-1'
    supports_working_understanding = True

    def __init__(self, provider_authority=WORKING_AUTHORITY, **kwargs):
        super().__init__(provider_authority=provider_authority, **kwargs)
        if provider_authority==WORKING_LIVE_AUTHORITY:
            self.adapter_version='working-understanding-live-cognition-s146-1'

    def preflight(self, *, context, command):
        if self.provider_authority==WORKING_LIVE_AUTHORITY:
            from dynamic_subject_agent.working_understanding_live import WorkingUnderstandingDelivery
            if (self.gateway is None or self.gateway.capabilities.local is not False
                or self.gateway.capabilities.provider_id!='deepseek' or type(self.delivery) is not WorkingUnderstandingDelivery
                or self.snapshot_loader is None or contract_variant(self.contract)!='working-live'
                or self.contract!=self.delivery.contract):
                raise PreAdmissionRejected('working-approved-gateway-required','exact independently approved LIVE composition required')
            self.delivery.grant.validate()
        elif (self.provider_authority!=WORKING_AUTHORITY or self.gateway is None or self.gateway.capabilities.local is not True
            or contract_variant(self.contract)!='working-local'):
            raise PreAdmissionRejected('working-local-gateway-required','independent LOCAL composition required')
        if type(command) is SharedActivityInput:
            if command.working_permission is None or command.input_kind not in ('advance','understand','understanding-disable'):
                raise PreAdmissionRejected('working-input-unavailable', 'only explicit bounded working activity is available')
            return
        OriginalWholeChatCognition.preflight(self, context=context, command=command)

    @contextmanager
    def publication_guard(self, plan):
        record = plan.shared_record
        if record is None or record.working is None or self.guard is None:
            raise ValueError('complete working preparation required')
        if (self._context_revision_at(plan.expected_basis.head_sequence) != record.context_revision
            or self.working_permission() != record.working['permission']):
            raise ShareAuthorizationChanged('working-source-permission-changed')
        with self.guard(OriginalWholeAuthorization(**record.authorization)):
            if self.working_permission() != record.working['permission']:
                raise ShareAuthorizationChanged('working-source-permission-changed')
            yield

    def choice_preview(self, identity, view):
        return build_working_choice_preview(self.envelope, identity, view, self.contract)

    def _execute_working(self, task, *, plan, context, command, authorization, permission):
        if self.provider_authority==WORKING_LIVE_AUTHORITY:
            from dynamic_subject_agent.original_whole_chat import validate_whole_envelope
            from dynamic_subject_agent.working_understanding import validate_permission
            def rebuild():
                snapshot=self.snapshot_loader()
                fresh=validate_permission(snapshot['working_permission'])
                if (snapshot['authorization']!=authorization or fresh!=permission
                    or snapshot['contract']!=self.delivery.contract or self.contract!=self.delivery.contract):
                    raise ValueError('working sealed authorization or source permission changed')
                validate_whole_envelope(snapshot['envelope'],snapshot['contract'])
                effective=replace(authorization,history_enabled=False) if fresh['source_blocked'] else authorization
                view=context.load_shared_activity(effective)
                if view['basis']!=asdict(plan.expected_basis):
                    raise ValueError('working complete canonical prefix changed')
                if task.kind is ModelTaskKind.WORKING_UNDERSTANDING_FORM:
                    if type(command) is not SharedActivityInput or command.input_kind!='understand' or command.working_permission!=fresh:
                        raise ValueError('exact formation admission required')
                    context.validate_working_sources(command.working_sources,effective)
                    return build_form_preview(snapshot['envelope'],snapshot['identity'],view,snapshot['contract'],command.working_sources)
                if task.kind is ModelTaskKind.WORKING_ACTIVITY_CHOICE:
                    if type(command) is not SharedActivityInput or command.input_kind!='advance' or command.working_permission!=fresh:
                        raise ValueError('exact choice admission required')
                    return build_working_choice_preview(snapshot['envelope'],snapshot['identity'],view,snapshot['contract'])
                if task.kind is not ModelTaskKind.WORKING_ACTIVITY_REPLY or type(command) in (SharedActivityInput,WholeContextInput):
                    raise ValueError('closed working purpose required')
                dialogue=context.load_character_dialogue(effective.history_enabled)
                return build_working_reply_preview(snapshot['envelope'],snapshot['identity'],command.utterance,
                    dialogue,effective.history_enabled,view,snapshot['contract'])
            try:
                self.delivery.claim(plan.operation_ref.operation_id+':'+plan.attempt_id,task,rebuild)
            except Exception:
                raise ModelGatewayFailure('delivery-unverified') from None
        return self.gateway.execute(task).value

    def propose(self, *, plan, context, command, basis):
        if type(command) not in (SharedActivityInput, WholeContextInput):
            scope = whole_dialogue_scope(command.utterance)
            if scope in (WITHDRAWAL, UNRESOLVED):
                code = 'original-whole-history-withdrawn' if scope == WITHDRAWAL else 'original-whole-history-control-unresolved'
                raise CognitionFailedClosed('history', code, 'No current disclosure control is sent.')
        try:
            authorization, permission = self.authorization(), self.working_permission()
            effective = replace(authorization, history_enabled=False) if permission['source_blocked'] else authorization
            view = context.load_shared_activity(effective)
            choice = formation = None
            if type(command) is WholeContextInput:
                text = CONTEXT_RECEIPT
            elif type(command) is SharedActivityInput and command.input_kind == 'understanding-disable':
                text = '已停用当前工作理解；原记录保留。'
            else:
                with self.guard(authorization):
                    if type(command) is SharedActivityInput and command.input_kind == 'understand':
                        context.validate_working_sources(command.working_sources, effective)
                        preview = build_form_preview(self.envelope, context.runtime_identity, view, self.contract, command.working_sources)
                        formation = self._execute_working(ModelTask(ModelTaskKind.WORKING_UNDERSTANDING_FORM, preview),
                            plan=plan,context=context,command=command,authorization=authorization,permission=permission)
                        text = '已形成当前构图的暂定工作理解。' if formation.get('status') == 'formed' else '依据不足；保留原有工作理解。'
                    elif type(command) is SharedActivityInput:
                        preview = self.choice_preview(context.runtime_identity, view)
                        choice = self._execute_working(ModelTask(ModelTaskKind.WORKING_ACTIVITY_CHOICE, preview),
                            plan=plan,context=context,command=command,authorization=authorization,permission=permission)
                        text = '本次构图取舍已提交。'
                    else:
                        dialogue = context.load_character_dialogue(effective.history_enabled)
                        preview = build_working_reply_preview(self.envelope, context.runtime_identity, command.utterance,
                            dialogue, effective.history_enabled, view, self.contract)
                        text = validate_whole_reply(self._execute_working(ModelTask(ModelTaskKind.WORKING_ACTIVITY_REPLY, preview),
                            plan=plan,context=context,command=command,authorization=authorization,permission=permission))
            if self.authorization() != authorization or self.working_permission() != permission:
                raise ShareAuthorizationChanged('working-source-permission-changed')
            record = build_working_record(view, command=command, authorization=authorization, permission=permission,
                head_sequence=plan.expected_basis.head_sequence+1, choice=choice, formation=formation)
            if record.kind == 'decision':
                text = record.result.event.summary
            proposal = self._bounded_noop_proposal(context=context, basis=basis,
                experience_summary=('已提交当前构图的暂定工作理解或文字活动；原话不是事实真值或永久人格。'
                    if self.provider_authority==WORKING_LIVE_AUTHORITY else 'LOCAL当前构图工作理解与文字活动；原话不是事实真值或永久人格。'),
                expression_candidate=ExpressionCandidate(text,'zh'))
            return replace(proposal, shared_record=record)
        except Exception as error:
            if isinstance(error, CognitionFailedClosed):
                raise
            from dynamic_subject_agent.reply_review_diagnostics import REVIEW_DIAGNOSTIC_CODES
            code=error.code if isinstance(error,ModelGatewayFailure) else 'history-changed' if isinstance(error,ShareAuthorizationChanged) else 'provider-failed'
            if code not in REVIEW_DIAGNOSTIC_CODES|{'character-credential-unavailable','structured-choice-invalid','expression-invalid','audit-failed','delivery-unverified','history-changed'}:
                code='provider-failed'
            raise CognitionFailedClosed('whole-reply','original-whole-'+code,
                'Working preparation failed closed, with no new event or retry.') from None
