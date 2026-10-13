"""Single combined proposal path, independently qualified for LOCAL or LIVE."""
from dataclasses import asdict, replace

from dynamic_subject_agent.shared_activity_cognition import SharedActivityCognition
from dynamic_subject_agent.original_whole_chat_cognition import OriginalWholeChatCognition
from dynamic_subject_agent.shared_activity import SharedActivityInput, INTEGRATED_AUTHORITY, INTEGRATED_LIVE_AUTHORITY, INTEGRATED_AUTHORITIES
from dynamic_subject_agent.whole_context_boundary import WholeContextInput, CONTEXT_RECEIPT
from dynamic_subject_agent.whole_dialogue_scope import whole_dialogue_scope, WITHDRAWAL, UNRESOLVED
from dynamic_subject_agent.original_whole_chat import contract_variant
from dynamic_subject_agent.first_life_authorization import ShareAuthorizationChanged
from dynamic_subject_agent.runtime import CognitionFailedClosed, ExpressionCandidate
from dynamic_subject_agent.timeline import PreAdmissionRejected
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind, ModelGatewayFailure
from dynamic_subject_agent.natural_feedback_multispan import multispan_proposal
from dynamic_subject_agent.integrated_character import (
    integrated_choice_preview, integrated_feedback_preview, integrated_share_preview,
    build_integrated_record, validate_share)


class IntegratedCharacterCognition(SharedActivityCognition):
    supports_integrated_character = True

    def __init__(self, *, provider_authority=INTEGRATED_AUTHORITY, **kwargs):
        if provider_authority not in INTEGRATED_AUTHORITIES:
            raise ValueError('exact integrated authority required')
        super().__init__(provider_authority=provider_authority, **kwargs)
        self.supports_natural_feedback = self.supports_living_activity = True
        self.adapter_version = ('integrated-character-live-cognition-s158-1'
            if provider_authority == INTEGRATED_LIVE_AUTHORITY else 'integrated-character-local-cognition-s158-1')

    def preflight(self, *, context, command):
        if self.provider_authority == INTEGRATED_LIVE_AUTHORITY:
            from dynamic_subject_agent.integrated_character_live import IntegratedCharacterDelivery
            if (self.gateway is None or self.gateway.capabilities.local is not False
                or self.gateway.capabilities.provider_id != 'deepseek' or type(self.delivery) is not IntegratedCharacterDelivery
                or self.snapshot_loader is None or contract_variant(self.contract) != 'integrated-live'
                or self.contract != self.delivery.contract):
                raise PreAdmissionRejected('integrated-live-grant-required', 'Exact S158 delivery composition required.')
            self.delivery.grant.validate()
        elif (self.gateway is None or self.gateway.capabilities.local is not True
            or contract_variant(self.contract) != 'integrated-local'):
            raise PreAdmissionRejected('integrated-local-required', 'The prepared contract has no remote grant.')
        if type(command) is SharedActivityInput:
            if command.living_permission is None:
                raise PreAdmissionRejected('living-permission-required', 'Exact permission is required.')
            if (self.provider_authority == INTEGRATED_LIVE_AUTHORITY and command.input_kind == 'advance'
                and command.living_trigger not in ('online', 'simulation')):
                raise PreAdmissionRejected('integrated-opportunity-required', 'Approved living opportunity required.')
            return
        return OriginalWholeChatCognition.preflight(self, context=context, command=command)

    def choice_preview(self, identity, view):
        return integrated_choice_preview(self.envelope, identity, view, self.contract)

    def propose(self, *, plan, context, command, basis):
        ordinary = type(command) not in (SharedActivityInput, WholeContextInput)
        if ordinary and whole_dialogue_scope(command.utterance) in (WITHDRAWAL, UNRESOLVED):
            code = 'history-withdrawn' if whole_dialogue_scope(command.utterance) == WITHDRAWAL else 'history-control-unresolved'
            raise CognitionFailedClosed('history', 'original-whole-' + code, 'Disclosure control is not sent.')
        try:
            authorization = self.authorization()
            permission = self.living_permission()
            effective = replace(authorization, history_enabled=False) if permission['source_blocked'] else authorization
            view = context.load_shared_activity(effective)
            choice = share = feedback = None
            if type(command) is WholeContextInput:
                text = CONTEXT_RECEIPT
            elif type(command) is SharedActivityInput and command.input_kind in ('select', 'disable'):
                text = '已更新共同依据；原记录保留。'
            else:
                with self.guard(authorization):
                    if type(command) is SharedActivityInput:
                        if command.living_permission != permission or permission['paused'] or permission['needs_attention']:
                            raise ShareAuthorizationChanged('living-permission-changed')
                        if command.input_kind == 'share':
                            preview = integrated_share_preview(self.envelope, context.runtime_identity, view, self.contract)
                            share = validate_share(self._execute_integrated(ModelTask(ModelTaskKind.LIVING_ACTIVITY_SHARE, preview),
                                plan=plan, context=context, command=command, authorization=authorization, permission=permission))
                            text = share['reply_text'] if share['share'] else '本次保留分享；已记录这次考虑。'
                        else:
                            preview = self.choice_preview(context.runtime_identity, view)
                            choice = self._execute_integrated(ModelTask(ModelTaskKind.LIVING_ACTIVITY_CHOICE, preview),
                                plan=plan, context=context, command=command, authorization=authorization, permission=permission)
                            text = '本次活动取舍已提交。'
                    else:
                        dialogue = context.load_character_dialogue(effective.history_enabled)
                        preview = integrated_feedback_preview(self.envelope, context.runtime_identity, command.utterance,
                            dialogue, effective.history_enabled, view, self.contract)
                        raw = self._execute_integrated(ModelTask(ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK, preview),
                            plan=plan, context=context, command=command, authorization=authorization, permission=permission)
                        feedback = multispan_proposal(raw, preview['payload'])
                        text = feedback['reply_text']
            if self.authorization() != authorization or self.living_permission() != permission:
                raise ShareAuthorizationChanged('integrated-permission-changed')
            record = build_integrated_record(view, command=command, authorization=authorization,
                permission=permission, head_sequence=plan.expected_basis.head_sequence+1,
                choice=choice, share=share, proposal=feedback, contract=self.contract)
            if record.kind == 'decision':
                text = record.result.event.summary
            proposal = self._bounded_noop_proposal(context=context, basis=basis,
                experience_summary='同一人物已提交的交流、有限文字活动与分享。',
                expression_candidate=ExpressionCandidate(text, 'zh'))
            return replace(proposal, shared_record=record)
        except CognitionFailedClosed:
            raise
        except Exception as error:
            if type(command) is SharedActivityInput and command.input_kind in ('advance', 'share'):
                self.living_failure()
            code = error.code if isinstance(error, ModelGatewayFailure) else 'history-changed' if isinstance(error, ShareAuthorizationChanged) else 'structured-choice-invalid'
            from dynamic_subject_agent.reply_review_diagnostics import REVIEW_DIAGNOSTIC_CODES
            if code not in REVIEW_DIAGNOSTIC_CODES | {'structured-choice-invalid', 'history-changed',
                'character-credential-unavailable', 'audit-failed', 'delivery-unverified'}:
                code = 'provider-failed'
            raise CognitionFailedClosed('whole-reply', 'original-whole-' + code,
                'The operation did not commit and will not be retried.') from None

    def _execute_integrated(self, task, *, plan, context, command, authorization, permission):
        if self.provider_authority == INTEGRATED_LIVE_AUTHORITY:
            from dynamic_subject_agent.original_whole_chat import validate_whole_envelope
            from dynamic_subject_agent.living_activity import validate_permission, sharing_gate
            def rebuild():
                snapshot = self.snapshot_loader()
                if (snapshot['authorization'] != authorization or snapshot['contract'] != self.contract
                    or self.contract != self.delivery.contract):
                    raise ValueError('integrated sealed authorization changed')
                validate_whole_envelope(snapshot['envelope'], snapshot['contract'])
                fresh = validate_permission(snapshot['living_permission'])
                if fresh != permission or self.living_permission() != permission:
                    raise ValueError('integrated living permission changed')
                effective = replace(authorization, history_enabled=False) if fresh['source_blocked'] else authorization
                view = context.load_shared_activity(effective)
                if view['basis'] != asdict(plan.expected_basis):
                    raise ValueError('integrated canonical prefix changed')
                if task.kind in (ModelTaskKind.LIVING_ACTIVITY_CHOICE, ModelTaskKind.LIVING_ACTIVITY_SHARE):
                    if type(command) is not SharedActivityInput or command.living_permission != fresh or fresh['paused'] or fresh['needs_attention']:
                        raise ValueError('exact current living action required')
                    if task.kind is ModelTaskKind.LIVING_ACTIVITY_CHOICE:
                        if command.input_kind != 'advance' or command.living_trigger not in ('online', 'simulation'):
                            raise ValueError('exact approved opportunity required')
                        return integrated_choice_preview(snapshot['envelope'], snapshot['identity'], view, snapshot['contract'])
                    if (command.input_kind != 'share' or command.living_day != self.living_day()
                        or sharing_gate(view, fresh, command.living_day)
                        or view['visible_result'].event.event_id != command.target_event_id):
                        raise ValueError('exact eligible sharing action required')
                    return integrated_share_preview(snapshot['envelope'], snapshot['identity'], view, snapshot['contract'])
                if task.kind is not ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK or type(command) in (SharedActivityInput, WholeContextInput):
                    raise ValueError('exact submitted feedback required')
                dialogue = context.load_character_dialogue(effective.history_enabled)
                return integrated_feedback_preview(snapshot['envelope'], snapshot['identity'], command.utterance,
                    dialogue, effective.history_enabled, view, snapshot['contract'])
            try:
                self.delivery.claim(plan.operation_ref.operation_id + ':' + plan.attempt_id, task, rebuild)
            except Exception:
                raise ModelGatewayFailure('delivery-unverified') from None
        return self.gateway.execute(task).value
