"""Complete bounded interval cover of independently authorized text targets."""
from dataclasses import asdict,dataclass
from functools import lru_cache
from dynamic_subject_agent.first_life import validate_plan
from dynamic_subject_agent.natural_feedback import validate_proposal,apply_edits
from dynamic_subject_agent.natural_feedback_frame import requested_frame,compact_proposal
from dynamic_subject_agent.natural_feedback_intent import INTENT_DEVELOPMENT,INTENT_POLICY_SHA

MULTISPAN_VERSION='natural-feedback-multispan-live-s154-1'
MULTISPAN_DEVELOPMENT='user-requested-multispan-2026-10-11'


def _field_cover(text,old,new):
    positions=[];start=0
    while True:
        index=text.find(old,start)
        if index<0:break
        positions.append(index);start=index+len(old)
    if not positions:return ()

    @lru_cache(None)
    def windows(i,j):
        # Context must not include a target assigned to another group.
        left=positions[i-1]+len(old) if i else 0
        right=positions[j+1] if j+1<len(positions) else len(text)
        core_start=positions[i];core_end=positions[j]+len(old)
        max_width=min(160,240-(j-i+1)*(len(new)-len(old)))
        found=[]
        for width in range(core_end-core_start,max_width+1):
            for a in range(max(left,core_end-width),min(core_start,right-width)+1):
                b=a+width;snippet=text[a:b]
                if text.find(snippet)==a and text.find(snippet,a+1)<0:
                    found.append((a,b))
        # A later start and earlier end admits every neighbour admitted by a
        # wider window, with less unchanged context. Keep only the frontier.
        frontier=[];best_end=len(text)+1
        for a,b in sorted(found,key=lambda pair:(-pair[0],pair[1])):
            if b<best_end:frontier.append((a,b));best_end=b
        return tuple(frontier)

    @lru_cache(None)
    def cover(i,previous_end):
        if i==len(positions):return ()
        best=None
        for j in range(i,len(positions)):
            for a,b in windows(i,j):
                if a<previous_end:continue
                rest=cover(j+1,b)
                if rest is None or len(rest)>=4:continue
                candidate=((a,b),)+rest
                rank=lambda value:(len(value),sum(y-x for x,y in value),value)
                if best is None or rank(candidate)<rank(best):best=candidate
        return best

    result=cover(0,0)
    if result is None:raise ValueError('no complete bounded unique interval cover')
    return result


def construct_multispan_edits(plan,frame):
    if frame is None:raise ValueError('independent requested frame unavailable; clarify instead')
    edits=[]
    for field,text in asdict(plan).items():
        for a,b in _field_cover(text,frame.before,frame.after):
            before=text[a:b]
            edits.append(dict(field=field,before=before,after=before.replace(frame.before,frame.after)))
    probe=dict(intent='revise',activity_revision=0,edits=edits,reply_text='本地校验。',language='zh',reason_code='try-alternative')
    validate_proposal(probe)
    if apply_edits(plan,edits)!=frame.expected_plan:
        raise ValueError('complete interval cover differs from independent expected plan')
    return edits


def multispan_proposal(raw,payload, *, frame=None):
    if type(raw) is not dict or set(raw)!={'intent','reply_text'}:
        raise ValueError('exact intent-only feedback proposal required')
    edits=[]
    if raw['intent']=='revise':
        if payload['current_plan'] is None:raise ValueError('current plan required for revision')
        plan=validate_plan(payload['current_plan'])
        frame=requested_frame(payload['turn']['current_message'],plan) if frame is None else frame
        edits=construct_multispan_edits(plan,frame)
    return compact_proposal(dict(raw,edits=edits),payload,frame=frame)


@dataclass(frozen=True)
class NaturalFeedbackMultispanDevelopmentGrant:
    review_basis:str
    development_authorization:str
    def __post_init__(self):
        from dynamic_subject_agent.natural_feedback_live import APPROVED_FEEDBACK_REVIEW
        if self.review_basis!=APPROVED_FEEDBACK_REVIEW or self.development_authorization!=MULTISPAN_DEVELOPMENT:
            raise ValueError('approved feedback uses and exact S154 continued development required')
    def validate(self):
        from dynamic_subject_agent.natural_feedback_intent import NaturalFeedbackIntentDevelopmentGrant
        self.__post_init__()
        NaturalFeedbackIntentDevelopmentGrant(self.review_basis,INTENT_DEVELOPMENT).validate()


def multispan_contract(binding):
    from dynamic_subject_agent.natural_feedback_intent import intent_contract
    from dynamic_subject_agent.natural_feedback_live import APPROVED_FEEDBACK_REVIEW
    NaturalFeedbackMultispanDevelopmentGrant(APPROVED_FEEDBACK_REVIEW,MULTISPAN_DEVELOPMENT).validate()
    base=intent_contract(binding)
    return dict(base,version=MULTISPAN_VERSION,development_authorization=MULTISPAN_DEVELOPMENT,
        technical_variant=dict(base['technical_variant'],protocol_variant='multi-span',
            feedback_policy_sha=INTENT_POLICY_SHA,edit_construction='complete-bounded-unique-interval-cover-1'))
