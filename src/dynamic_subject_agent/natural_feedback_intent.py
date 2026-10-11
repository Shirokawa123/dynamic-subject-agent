"""S153: model proposes intent/text; Python constructs the independently known edit."""
from dataclasses import asdict,dataclass
from hashlib import sha256
from dynamic_subject_agent.natural_feedback_frame import (
    SCOPED_POLICY,SCOPED_DEVELOPMENT,requested_frame,validate_frame_effect)
from dynamic_subject_agent.natural_feedback import validate_proposal,apply_edits
from dynamic_subject_agent.first_life import validate_plan

INTENT_VERSION='natural-feedback-intent-live-s153-1'
INTENT_DEVELOPMENT='user-continued-python-edit-2026-10-11'
INTENT_POLICY=(SCOPED_POLICY.split('仅输出JSON exact',1)[0]+
    '实际替换由Python按当前用户原话独立构造，不由你生成编辑列表或方案。'
    '仅输出JSON exact {intent,reply_text}；intent仅chat/clarify/revise，正文非空最多1200字符。'
    '明确可定位的本次引号替换且其他照旧可提议revise；含糊或不能定位则clarify；普通话题/未来条件chat。'
    '不生成edits、plan、language、activity_revision或reason_code。默认中文自然短消息；'
    '可解释自己的看法，但修改范围只能是本次明确文字，不能暗中改主体、光线或视点。')
INTENT_POLICY_SHA='34967354021b794d1b069bb83ec15480aa6d93a3ab896ab9933a3719acf00396'


def construct_frame_edits(plan,frame):
    if frame is None:raise ValueError('independent requested frame unavailable; clarify instead')
    edits=[]
    for field,text in asdict(plan).items():
        start=text.find(frame.before)
        if start<0:continue
        end=text.rfind(frame.before)+len(frame.before)
        before=text[start:end];after=before.replace(frame.before,frame.after)
        edits.append(dict(field=field,before=before,after=after))
    # Retain the old bounded/unique/real-change representation, never drop or
    # repair a model patch: this protocol does not accept a model patch at all.
    probe=dict(intent='revise',activity_revision=0,edits=edits,reply_text='本地校验。',language='zh',reason_code='try-alternative')
    validate_proposal(probe)
    if apply_edits(plan,edits)!=frame.expected_plan:
        raise ValueError('constructed edit does not equal independent requested frame')
    return edits


def intent_proposal(raw,payload, *, frame=None):
    if type(raw) is not dict or set(raw)!={'intent','reply_text'}:
        raise ValueError('exact intent-only feedback proposal required')
    plan=None if payload['current_plan'] is None else validate_plan(payload['current_plan'])
    edits=[]
    if raw['intent']=='revise':
        if plan is None:raise ValueError('current plan required for revision')
        frame=requested_frame(payload['turn']['current_message'],plan) if frame is None else frame
        edits=construct_frame_edits(plan,frame)
    result=dict(raw,edits=edits,activity_revision=payload['activity_revision'],language='zh',
        reason_code='try-alternative' if raw['intent']=='revise' else None)
    validate_frame_effect(result,message=payload['turn']['current_message'],plan=plan,frame=frame)
    return result


@dataclass(frozen=True)
class NaturalFeedbackIntentDevelopmentGrant:
    review_basis:str
    development_authorization:str
    def __post_init__(self):
        from dynamic_subject_agent.natural_feedback_live import APPROVED_FEEDBACK_REVIEW
        if self.review_basis!=APPROVED_FEEDBACK_REVIEW or self.development_authorization!=INTENT_DEVELOPMENT:
            raise ValueError('approved feedback uses and exact S153 continued development required')
    def validate(self):
        from dynamic_subject_agent.natural_feedback_scoped import NaturalFeedbackScopedDevelopmentGrant
        self.__post_init__()
        NaturalFeedbackScopedDevelopmentGrant(self.review_basis,SCOPED_DEVELOPMENT).validate()
        if sha256(INTENT_POLICY.encode()).hexdigest()!=INTENT_POLICY_SHA:
            raise ValueError('pinned intent-only feedback policy changed')


def intent_contract(binding):
    from dynamic_subject_agent.natural_feedback_frame import scoped_contract
    from dynamic_subject_agent.natural_feedback_live import APPROVED_FEEDBACK_REVIEW
    NaturalFeedbackIntentDevelopmentGrant(APPROVED_FEEDBACK_REVIEW,INTENT_DEVELOPMENT).validate()
    base=scoped_contract(binding)
    return dict(base,version=INTENT_VERSION,development_authorization=INTENT_DEVELOPMENT,
        technical_variant=dict(base['technical_variant'],protocol_variant='intent-only',feedback_policy_sha=INTENT_POLICY_SHA,
            feedback_output='intent-reply-local-frame-edits',edit_construction='per-field-bounded-frame-1'))


def intent_preview(preview):return dict(preview,policy=INTENT_POLICY)
