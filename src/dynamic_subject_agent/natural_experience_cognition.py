"""Qualified experience/reply proposals; final publication remains Python-owned."""
from dataclasses import replace
from contextlib import contextmanager
from time import time_ns
import re

from dynamic_subject_agent.shared_activity_cognition import SharedActivityCognition
from dynamic_subject_agent.shared_activity import SharedActivityInput
from dynamic_subject_agent.whole_context_boundary import WholeContextInput
from dynamic_subject_agent.runtime import CognitionFailedClosed, ExpressionCandidate
from dynamic_subject_agent.timeline import PreAdmissionRejected
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
from dynamic_subject_agent.natural_experience_cycle import (
    is_contract, local_day, natural_view, expression_frame, build_natural_record, LIVE_VERSION, CHECKED_VERSION, CHECKED_LIVE_VERSION,
    is_reviewed_version,is_live_version,checked_reply_frame)
from dynamic_subject_agent.natural_experience import selection_projection, encode_experience


class NaturalExperienceCognition(SharedActivityCognition):
    supports_natural_experience = True
    adapter_version = 'natural-experience-local-cognition-m031-1'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.adapter_version = 'natural-conversation-reviewed-local-cognition-m034-1' if self.contract['version']==CHECKED_VERSION else 'natural-conversation-live-cognition-m032-1' if self.contract['version'] == LIVE_VERSION else 'natural-experience-local-cognition-m031-1'
        if self.contract['version']==CHECKED_LIVE_VERSION:self.adapter_version='natural-conversation-reviewed-live-cognition-m034-1'
        self.natural_now_us = lambda: time_ns() // 1000

    def preflight(self, *, context, command):
        live = is_contract(self.contract) and is_live_version(self.contract['version'])
        if live:
            from dynamic_subject_agent.natural_conversation_live import NaturalConversationDelivery
            from dynamic_subject_agent.reviewed_natural_live import ReviewedNaturalDelivery
            expected=ReviewedNaturalDelivery if self.contract['version']==CHECKED_LIVE_VERSION else NaturalConversationDelivery
            if (type(self.delivery) is not expected or self.gateway is None
                    or self.gateway.capabilities.local is not False or self.delivery.contract != self.contract):
                raise PreAdmissionRejected('natural-live-required', 'exact approved conversation delivery required')
            self.delivery.validate()
            if type(command) in (SharedActivityInput, WholeContextInput):
                raise PreAdmissionRejected('natural-trial-text-only', 'this trial only admits its fixed user turns')
        elif not is_contract(self.contract) or self.gateway is None or self.gateway.capabilities.local is not True:
            raise PreAdmissionRejected('natural-local-required', 'no remote or existing-root activation')
        if is_reviewed_version(self.contract['version']) and type(command) in (SharedActivityInput,WholeContextInput):
            raise PreAdmissionRejected('reviewed-conversation-text-only','bounded text experience only')
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

    @contextmanager
    def publication_guard(self, plan):
        with super().publication_guard(plan):
            if is_live_version(self.contract['version']):
                self.delivery.validate()
            if self.contract['version']==CHECKED_LIVE_VERSION:
                self.delivery.validate_final(plan.shared_record.natural['speech'])
            yield

    def _propose_conversation(self, *, plan, context, command, basis, authorization, permission, effective, view, day):
        def projection(selection=None, *, reply=False):
            if self.authorization() != authorization or self.living_permission() != permission:
                raise ValueError('authority changed')
            current = context.load_shared_activity(effective)
            if current['basis'] != view['basis'] or local_day(self.natural_now_us()) != day:
                raise ValueError('conversation basis or day changed')
            current = natural_view(current, day)
            if not reply:
                return dict(current_user_text=command.utterance,
                    current_experience=selection_projection(current['natural_experience'], day))
            proposed, _ = build_natural_record(current, command=command, authorization=authorization,
                permission=permission, head_sequence=plan.expected_basis.head_sequence + 1, day=day,
                selection=selection, speech=dict(reply_text='临时构造，不发表。'), version=LIVE_VERSION)
            changed = proposed.natural['experience'] != encode_experience(current['natural_experience'])
            from dynamic_subject_agent.natural_experience import decode_experience
            return dict(current_user_text=command.utterance,
                experience=selection_projection(decode_experience(proposed.natural['experience']), day),
                exchange=[] if changed else current.get('natural_exchange', []), activity_evidence=None)
        with self.delivery.frame(projection):
            selection = self.gateway.execute(ModelTask(ModelTaskKind.MEMORIE_NATURAL_EXPERIENCE, projection())).value
        reply_projection = lambda: projection(selection, reply=True)
        with self.delivery.frame(reply_projection):
            reply = self.gateway.execute(ModelTask(ModelTaskKind.MEMORIE_GROUNDED_EXPRESSION, reply_projection())).value
        record, text = build_natural_record(view, command=command, authorization=authorization,
            permission=permission, head_sequence=plan.expected_basis.head_sequence + 1, day=day,
            selection=selection, speech=dict(reply_text=reply), version=LIVE_VERSION)
        projection(selection, reply=True)
        proposal = self._bounded_noop_proposal(context=context, basis=basis,
            experience_summary='隔离自然交流试验；真实模型提议，来源与期限由Python裁决。',
            expression_candidate=ExpressionCandidate(text, 'zh'))
        return replace(proposal, shared_record=record)

    def _propose_reviewed_conversation(self, *, plan, context, command, basis, authorization, permission, effective, view, day):
        from dynamic_subject_agent.natural_experience import adjudicate_experience
        from dynamic_subject_agent.reviewed_natural_reply import generate_reviewed_reply,review_payload
        live=self.contract['version']==CHECKED_LIVE_VERSION
        if live:self.delivery.assert_turn(view['revision'])
        asset=self.envelope['runtime_asset']
        material=dict(character=dict(name=asset['subject']['name'],stage=asset['initial_stage'],
            knowledge=[{k:row[k] for k in ('dimension','kind','statement','event_time','knowledge_time')} for row in asset['eligible']]),
            personality=asset['personality'])
        def current_view():
            if self.authorization()!=authorization or self.living_permission()!=permission or not effective.history_enabled:
                raise ValueError('reviewed conversation authority changed')
            current=context.load_shared_activity(effective)
            if current['basis']!=view['basis'] or local_day(self.natural_now_us())!=day:
                raise ValueError('reviewed conversation basis or day changed')
            return natural_view(current,day)
        def source_projection():
            current=current_view()
            return dict(material,current_user_text=command.utterance,current_experience=selection_projection(current['natural_experience'],day))
        if live:
            with self.delivery.frame(source_projection):
                selection=self.gateway.execute(ModelTask(ModelTaskKind.MEMORIE_NATURAL_EXPERIENCE,source_projection())).value
        else:
            selection=self.gateway.execute(ModelTask(ModelTaskKind.MEMORIE_NATURAL_EXPERIENCE,source_projection())).value
        def projection():
            current=current_view()
            selected=adjudicate_experience(selection,current_text=command.utterance,
                previous=current['natural_experience'],source_head_sequence=plan.expected_basis.head_sequence+1,local_day=day)
            return dict(material,**checked_reply_frame(current,command.utterance,selected,day))
        def execute(task):
            def fresh():
                base=projection()
                if task.kind is ModelTaskKind.ACTIVITY_REPLY_REVIEW:return review_payload(base,task.payload['candidate_text'])
                if task.kind is ModelTaskKind.MEMORIE_REPLY_REPAIR:
                    return dict(base,rejected_reply=task.payload['rejected_reply'],review_issues=task.payload['review_issues'])
                return base
            with self.delivery.frame(fresh):return self.gateway.execute(task)
        speech=generate_reviewed_reply(self.gateway,projection,execute=execute if live else None)
        projection()
        record,text=build_natural_record(view,command=command,authorization=authorization,permission=permission,
            head_sequence=plan.expected_basis.head_sequence+1,day=day,selection=selection,speech=speech,version=self.contract['version'])
        proposal=self._bounded_noop_proposal(context=context,basis=basis,
            experience_summary='完整审核流程；仅最终合格回复与经历发表。',expression_candidate=ExpressionCandidate(text,'zh'))
        return replace(proposal,shared_record=record)

    def _propose_living(self, *, plan, context, command, basis):
        try:
            authorization = self.authorization()
            permission = self.living_permission()
            effective = replace(authorization, history_enabled=False) if permission['source_blocked'] else authorization
            view = context.load_shared_activity(effective)
            day = local_day(context.observed_at_us)
            view = natural_view(view, day)
            if is_reviewed_version(self.contract['version']):
                return self._propose_reviewed_conversation(plan=plan,context=context,command=command,basis=basis,
                    authorization=authorization,permission=permission,effective=effective,view=view,day=day)
            if self.contract['version'] == LIVE_VERSION:
                return self._propose_conversation(plan=plan, context=context, command=command, basis=basis,
                    authorization=authorization, permission=permission, effective=effective, view=view, day=day)
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
