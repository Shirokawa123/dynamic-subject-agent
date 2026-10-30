"""LOCAL two-stage proposals with source-bound expression, no remote sender."""
from dataclasses import replace
from time import time_ns
import re

from dynamic_subject_agent.shared_activity_cognition import SharedActivityCognition
from dynamic_subject_agent.shared_activity import SharedActivityInput
from dynamic_subject_agent.whole_context_boundary import WholeContextInput
from dynamic_subject_agent.runtime import CognitionFailedClosed, ExpressionCandidate
from dynamic_subject_agent.timeline import PreAdmissionRejected
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
from dynamic_subject_agent.natural_experience_cycle import (
    is_contract, local_day, natural_view, expression_frame, build_natural_record)
from dynamic_subject_agent.natural_experience import selection_projection, encode_experience


class NaturalExperienceCognition(SharedActivityCognition):
    supports_natural_experience = True
    adapter_version = 'natural-experience-local-cognition-m031-1'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.adapter_version = 'natural-experience-local-cognition-m031-1'
        self.natural_now_us = lambda: time_ns() // 1000

    def preflight(self, *, context, command):
        if not is_contract(self.contract) or self.gateway is None or self.gateway.capabilities.local is not True:
            raise PreAdmissionRejected('natural-local-required', 'no remote or existing-root activation')
        if type(command) is SharedActivityInput:
            if command.input_kind not in ('disable', 'advance'):
                raise PreAdmissionRejected('natural-action-unavailable', 'only existing bounded controls/actions')
            return
        if type(command) is WholeContextInput:
            return
        if command.language != 'zh' or not command.utterance.strip() or len(command.utterance) > 1000:
            raise PreAdmissionRejected('natural-text-invalid', 'bounded current user text required')
        # Disclosure commands remain explicit controls; memory corrections are
        # not automatically treated as revocation of all conversation access.
        from dynamic_subject_agent.whole_dialogue_scope import whole_dialogue_scope, _unquoted, WITHDRAWAL, UNRESOLVED
        scope = whole_dialogue_scope(command.utterance)
        unquoted = _unquoted(command.utterance)[0]
        direct = re.match(r'^(?:请)?(?:不要外发|不要发送给模型|别发给模型|不要读取聊天历史)', unquoted)
        if (scope == UNRESOLVED or direct or scope == WITHDRAWAL and any(x in unquoted for x in
                ('聊天', '对话', '历史', '资料', '发送', '发给', '分享', '外发', 'history', 'send', 'share', 'conversation'))):
            raise PreAdmissionRejected('natural-disclosure-control-required', 'use the existing disclosure control')

    def prepare_natural_view(self, view):
        return natural_view(view, local_day(self.natural_now_us()))

    def _propose_living(self, *, plan, context, command, basis):
        try:
            authorization = self.authorization()
            permission = self.living_permission()
            effective = replace(authorization, history_enabled=False) if permission['source_blocked'] else authorization
            view = context.load_shared_activity(effective)
            day = local_day(context.observed_at_us)
            view = natural_view(view, day)
            selection = speech = choice = None
            ordinary = type(command) not in (SharedActivityInput, WholeContextInput)
            if ordinary:
                from dynamic_subject_agent.living_activity import build_living_reply_preview
                from dynamic_subject_agent.reviewed_character_chat import CharacterDialogueBasis
                background = build_living_reply_preview(self.envelope, context.runtime_identity,
                    command.utterance, CharacterDialogueBasis('available'), False, view, self.contract)['payload']['background']
                if effective.history_enabled:
                    projection = dict(background=background, current_user_text=command.utterance,
                        current_experience=selection_projection(view['natural_experience'], day))
                    selection = self.gateway.execute(ModelTask(ModelTaskKind.MEMORIE_NATURAL_EXPERIENCE, projection)).value
                # Prepare a view of the proposed source for expression without
                # publishing it. Failure of expression leaves the prior source.
                provisional, _ = build_natural_record(view, command=command, authorization=authorization,
                    permission=permission, head_sequence=plan.expected_basis.head_sequence + 1, day=day,
                    selection=selection, speech=dict(act='ask', reference=None, style='brief'))
                next_view = natural_view(dict(view, record=provisional), day)
                changed = provisional.natural['experience'] != encode_experience(view['natural_experience'])
                speech = self.gateway.execute(ModelTask(ModelTaskKind.MEMORIE_GROUNDED_EXPRESSION,
                    dict(expression_frame(next_view, command.utterance, changed=changed), background=background))).value
            elif type(command) is SharedActivityInput and command.input_kind == 'advance':
                if permission['paused'] or permission['needs_attention']:
                    raise ValueError('activity paused')
                choice = self.gateway.execute(ModelTask(ModelTaskKind.LIVING_ACTIVITY_CHOICE,
                    self.choice_preview(context.runtime_identity, view))).value
            record, text = build_natural_record(view, command=command, authorization=authorization,
                permission=permission, head_sequence=plan.expected_basis.head_sequence + 1, day=day,
                selection=selection, speech=speech, choice=choice)
            if self.authorization() != authorization or self.living_permission() != permission:
                raise ValueError('authority changed')
            proposal = self._bounded_noop_proposal(context=context, basis=basis,
                experience_summary='LOCAL自然经历与有据表达；合成模型不代表人物效果。',
                expression_candidate=ExpressionCandidate(text, 'zh'))
            return replace(proposal, shared_record=record)
        except Exception:
            raise CognitionFailedClosed('whole-reply', 'original-whole-natural-cycle-invalid', 'No source or reply was published.') from None
