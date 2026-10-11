"""Independent requested text frame, compact wire DTO, exact final-state check."""
from dataclasses import asdict,dataclass
import re

from dynamic_subject_agent.first_life import validate_plan
from dynamic_subject_agent.natural_feedback import FEEDBACK_POLICY,validate_proposal,apply_edits,build_feedback_record

SCOPED_VERSION='natural-feedback-scoped-live-s152-1'
SCOPED_DEVELOPMENT='user-requested-safe-feedback-2026-10-11'
SCOPED_POLICY=(FEEDBACK_POLICY.split('仅输出JSON exact',1)[0]+
    '本候选只在用户本轮明确用引号指定旧词与新词，并要求其他照旧时自动修订，例如把“甲”换成“乙”，其他照旧。'
    '这是格式说明，不是当前内容。旧词必须在当前方案可定位；用户明确“所有”才可多处同步替换。'
    '不把同义词、那个、条件假想或自己想改的句子猜成授权；无法定位先clarify，普通话题chat。'
    '只修改用户明确替换的文字，光线、主体、视点和所有其他内容逐字保留；个人建议可以说，不能擅自执行。'
    '仅输出JSON exact {intent,edits,reply_text}；intent仅chat/clarify/revise；'
    '正文非空最多1200字符，默认中文自然短消息，不生成language、activity_revision或reason_code。'
    'chat/clarify edits=[]；revise为1到4项，每项exact {field,before,after}，field仅subject/composition/focus，'
    'before是该字段唯一连续原文最多160字，after最多240字。重复目标可用较长唯一片段，但只能替换授权字词，'
    '不得顺带改标点、语序、光路或其他文字。所有被授权目标须同步改到，其他字节不能动。')

_REQUEST=re.compile(
    r'^\s*(?:这(?:一)?版(?:里|中)?[，,：:]?\s*)?(?:请\s*)?(?:把|将)\s*'
    r'(?P<all>所有|全部)?\s*(?P<oq>[“‘「"])(?P<before>[^“”‘’「」"\x00]{1,80})(?P<oc>[”’」"])\s*'
    r'(?:换成|改成|替换为)\s*(?P<aq>[“‘「"])(?P<after>[^“”‘’「」"\x00]{0,80})(?P<ac>[”’」"])'
    r'\s*[，,]\s*(?:其他|其余)(?:照旧|不变|不动)[。.!！]?\s*$')
_CLOSE={'“':'”','‘':'’','「':'」','"':'"'}

@dataclass(frozen=True)
class RequestedTextFrame:
    before:str
    after:str
    all_occurrences:bool
    expected_plan:object
    occurrences:int


def requested_frame(message,plan):
    """No model result participates in this authorization calculation."""
    if plan is None or type(message) is not str:return None
    match=_REQUEST.fullmatch(message)
    if match is None:return None
    g=match.groupdict()
    if _CLOSE[g['oq']]!=g['oc'] or _CLOSE[g['aq']]!=g['ac'] or g['before']==g['after']:return None
    fields=asdict(plan);count=0
    for text in fields.values():
        offsets=[];start=0
        while True:
            index=text.find(g['before'],start)
            if index<0:break
            if offsets and index<offsets[-1]+len(g['before']):return None
            offsets.append(index);start=index+1
        count+=len(offsets)
    if not 1<=count<=8 or not g['all'] and count!=1:return None
    try:expected=validate_plan({field:text.replace(g['before'],g['after']) for field,text in fields.items()})
    except ValueError:return None
    return RequestedTextFrame(g['before'],g['after'],bool(g['all']),expected,count)


def validate_frame_effect(proposal, *, message,plan,frame=None):
    validate_proposal(proposal)
    if proposal['intent']!='revise':return
    frame=requested_frame(message,plan) if frame is None else frame
    if frame is None:raise ValueError('independent requested frame unavailable; clarify instead')
    proposed=apply_edits(plan,proposal['edits'])
    if proposed!=frame.expected_plan:
        raise ValueError('proposal changed text outside the independently requested frame')


def compact_proposal(raw,payload, *, frame=None):
    if type(raw) is not dict or set(raw)!={'intent','edits','reply_text'}:
        raise ValueError('exact compact scoped proposal required')
    result=dict(raw,activity_revision=payload['activity_revision'],language='zh',
        reason_code='try-alternative' if raw['intent']=='revise' else None)
    current=None if payload['current_plan'] is None else validate_plan(payload['current_plan'])
    validate_frame_effect(result,message=payload['turn']['current_message'],plan=current,frame=frame)
    return result


def scoped_feedback_record(view, *, command,authorization,head_sequence,choice=None,proposal=None):
    from dynamic_subject_agent.shared_activity import SharedActivityInput
    from dynamic_subject_agent.whole_context_boundary import WholeContextInput
    if type(command) not in (SharedActivityInput,WholeContextInput):
        validate_frame_effect(proposal,message=command.utterance,plan=view['current_plan'])
    return build_feedback_record(view,command=command,authorization=authorization,head_sequence=head_sequence,
        choice=choice,proposal=proposal)


def scoped_contract(binding):
    from hashlib import sha256
    from dynamic_subject_agent.natural_feedback_budget import feedback_budget_contract
    from dynamic_subject_agent.natural_feedback_live import APPROVED_FEEDBACK_REVIEW
    from dynamic_subject_agent.natural_feedback_scoped import NaturalFeedbackScopedDevelopmentGrant
    NaturalFeedbackScopedDevelopmentGrant(APPROVED_FEEDBACK_REVIEW,SCOPED_DEVELOPMENT).validate()
    base=feedback_budget_contract(binding)
    return dict(base,version=SCOPED_VERSION,development_authorization=SCOPED_DEVELOPMENT,
        technical_variant=dict(base['technical_variant'],name='feedback-scoped-live',protocol_variant='scoped',
            feedback_policy_sha=sha256(SCOPED_POLICY.encode()).hexdigest(),
            feedback_output='intent-edits-reply-constants-bound-locally',write_frame='explicit-quoted-replacement-1'))


def scoped_preview(preview,contract=None):
    if contract is not None and contract['version']=='natural-feedback-intent-live-s153-1':
        from dynamic_subject_agent.natural_feedback_intent import intent_preview
        return intent_preview(preview)
    return dict(preview,policy=SCOPED_POLICY)
