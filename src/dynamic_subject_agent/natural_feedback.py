"""Source-bound partial revision of a currently visible composition, LOCAL only."""
from dataclasses import asdict, replace
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from dynamic_subject_agent.shared_activity import (
    ActivityDecision, ActivityResult, build_record, build_choice_preview,
    build_reply_preview, shared_contract, digest)
from dynamic_subject_agent.first_life import validate_plan, LifeFieldDiff, LifeEvent

FEEDBACK_VERSION = 'natural-feedback-local-s150-1'
FEEDBACK_POLICY = (
    '回应当前用户消息，同时判断是否明确要求修订唯一当前构图文字方案。'
    'background是有范围的已审人物资料，exchange仅是双方原话；当前方案是已提交文字，不是成图或离线经历。'
    '只有明确针对当前方案、目标和范围可确定的修改才提议revise；普通聊天、提问、仅条件假想或不采纳建议为chat。'
    '目标不清时clarify，只问缺失目标，不替用户决定；current_plan为null时不得恢复或猜旧方案。'
    '修订只提出局部文字替换，保持未要求修改的主体、视点及全部其他细节，不重写整个方案。'
    '有自己的意见和理由，用户原话不是事实真值或永久偏好。若不同意可以chat说明理由；不得声称没有提交的修改已完成。'
    '仅输出JSON exact {intent,activity_revision,edits,reason_code,reply_text,language}；'
    'intent仅chat/clarify/revise，activity_revision照抄输入。language=zh，正文非空最多1200字符。'
    'chat/clarify的edits=[]、reason_code=null；revise最多4项非空编辑，每项exact {field,before,after}，'
    'field仅subject/composition/focus，before为该字段唯一的逐字连续片段1至160字，after最多240字，替换后有变化。'
    '同字段多项编辑必须在原版本互不重叠。revise的reason_code仅improve-readability/balance-space/emphasize-subject/try-alternative。'
    'current_feedback若有仅限当前文字活动，以最新反馈及当前方案为准，不把旧建议当永久要求。'
)
CHOICE_SCOPE = (
    'current_feedback若有是当前活动真实收到的最近修订原话，不是永久偏好。'
    '当前方案已包含获接纳的局部修订；以它为基准继续一项具体活动取舍，不退回已纠正的安排。'
    '没有新用户要求也可按本人关注推进，允许有理由保留或暂缓。不要声称已成图或离线做过新活动。'
)


def feedback_contract(binding):
    return dict(shared_contract(binding), version=FEEDBACK_VERSION,
        excluded='remote-automatic-life-sharing-persona-rewrite-reflection-cloud-migration',
        technical_variant=dict(name='feedback-local', timeline_schema=8,
            max_feedback_sources=8, max_feedback_chars=400, max_edits=4,
            feedback_policy_sha=sha256(FEEDBACK_POLICY.encode()).hexdigest(),
            choice_policy_sha=sha256(feedback_choice_policy().encode()).hexdigest()))


def feedback_choice_policy():
    from dynamic_subject_agent.living_action_contract import action_contract_policies
    return action_contract_policies()[0] + CHOICE_SCOPE


def feedback_key(source):
    return 'F:' + digest(source)


def initial_feedback():
    return dict(sources=[], proposal=None)


def validate_feedback(value):
    if type(value) is not dict or set(value) != {'sources', 'proposal'}:
        raise ValueError('exact feedback record required')
    sources = value['sources']
    if type(sources) is not list or len(sources) > 8:
        raise ValueError('bounded feedback sources required')
    heads = []
    for source in sources:
        if (type(source) is not dict or set(source) != {'source_head_sequence', 'quote'}
            or type(source['source_head_sequence']) is not int or source['source_head_sequence'] <= 0
            or type(source['quote']) is not str or not source['quote'].strip()
            or len(source['quote']) > 400 or '\x00' in source['quote']):
            raise ValueError('exact feedback user source required')
        heads.append(source['source_head_sequence'])
    if heads != sorted(set(heads)):
        raise ValueError('ordered distinct feedback sources required')
    if value['proposal'] is not None:
        validate_proposal(value['proposal'])
    return value


def valid_feedback_sources(record, enabled, cutoff):
    if not enabled or record.feedback is None:
        return set()
    return {feedback_key(x) for x in record.feedback['sources'] if x['source_head_sequence'] > cutoff}


def current_feedback(view):
    record = view['record']
    if record.feedback is None or view['current_plan'] is None:
        return None
    sources = record.feedback['sources']
    if (not sources or feedback_key(sources[-1]) not in view['valid_sources']
        or feedback_key(sources[-1]) not in record.source_dependencies):
        return None
    return dict(label='F1', quote=sources[-1]['quote'])


def validate_proposal(value):
    if (type(value) is not dict
        or set(value) != {'intent', 'activity_revision', 'edits', 'reason_code', 'reply_text', 'language'}
        or value['intent'] not in ('chat', 'clarify', 'revise')
        or type(value['activity_revision']) is not int or value['activity_revision'] < 0
        or type(value['edits']) is not list or len(value['edits']) > 4):
        raise ValueError('exact feedback proposal required')
    from dynamic_subject_agent.original_whole_chat import validate_whole_reply
    validate_whole_reply(dict(reply_text=value['reply_text'], language=value['language']))
    if value['intent'] != 'revise':
        if value['edits'] or value['reason_code'] is not None:
            raise ValueError('chat/clarify has no plan effect')
    elif not value['edits'] or value['reason_code'] not in (
        'improve-readability', 'balance-space', 'emphasize-subject', 'try-alternative'):
        raise ValueError('revision needs a bounded effect and reason')
    for edit in value['edits']:
        if (type(edit) is not dict or set(edit) != {'field', 'before', 'after'}
            or edit['field'] not in ('subject', 'composition', 'focus')
            or type(edit['before']) is not str or not edit['before'] or len(edit['before']) > 160
            or type(edit['after']) is not str or len(edit['after']) > 240
            or '\x00' in edit['before'] + edit['after'] or edit['before'] == edit['after']):
            raise ValueError('bounded exact substring edit required')
    return value


def apply_edits(plan, edits):
    """Compute all offsets on the baseline, reject ambiguity, then apply on a copy."""
    fields = asdict(plan)
    intervals = {name: [] for name in fields}
    for edit in edits:
        text = fields[edit['field']]
        before = edit['before']
        start = text.find(before)
        if start < 0 or text.find(before, start + 1) >= 0:
            raise ValueError('edit target must exist exactly once')
        end = start + len(before)
        ranges = intervals[edit['field']]
        if any(start < old_end and old_start < end for old_start, old_end, _ in ranges):
            raise ValueError('baseline edit intervals overlap')
        ranges.append((start, end, edit['after']))
    for name, ranges in intervals.items():
        for start, end, after in sorted(ranges, reverse=True):
            fields[name] = fields[name][:start] + after + fields[name][end:]
    updated = validate_plan(fields)
    if updated == plan:
        raise ValueError('revision must change the actual plan')
    return updated


def build_feedback_record(view, *, command, authorization, head_sequence, choice=None, proposal=None):
    from dynamic_subject_agent.shared_activity import SharedActivityInput
    from dynamic_subject_agent.whole_context_boundary import WholeContextInput
    before = view['record']
    feedback = initial_feedback() if before.feedback is None else dict(sources=[dict(x) for x in before.feedback['sources']], proposal=None)
    normal = type(command) not in (SharedActivityInput, WholeContextInput)
    if not normal:
        record = build_record(before, command=command, authorization=authorization,
            cutoff=view['cutoff_sequence'], context_revision=view['context_revision'],
            head_sequence=head_sequence, choice=choice, dialogue_dependencies=view['dialogue_dependencies'])
        if type(command) is SharedActivityInput and command.input_kind in ('select', 'disable'):
            feedback['sources'] = []
        elif type(command) is SharedActivityInput and record.kind == 'decision':
            feedback['sources'] = [x for x in feedback['sources'] if feedback_key(x) in record.source_dependencies]
        return replace(record, feedback=feedback)
    proposal = validate_proposal(proposal)
    if proposal['activity_revision'] != before.activity_revision:
        raise ValueError('feedback activity baseline changed')
    record = build_record(before, command=command, authorization=authorization,
        cutoff=view['cutoff_sequence'], context_revision=view['context_revision'], head_sequence=head_sequence,
        dialogue_dependencies=view['dialogue_dependencies'])
    feedback['proposal'] = proposal
    if proposal['intent'] != 'revise':
        return replace(record, feedback=feedback)
    old = view['current_plan']
    if old is None or not authorization.history_enabled or len(feedback['sources']) >= 8:
        raise ValueError('only a visible source-eligible bounded plan may be revised')
    if len(command.utterance) > 400:
        raise ValueError('feedback source must be complete and bounded')
    updated = apply_edits(old, proposal['edits'])
    source = dict(source_head_sequence=head_sequence, quote=command.utterance)
    feedback['sources'].append(source)
    # The current E1 is supplied even if the independent baseline predates its
    # selection. Claimed edits/reasons cannot omit an actually supplied source.
    deps = tuple(sorted(set(record.reply_dependencies) | {feedback_key(source)}))
    differences = tuple(LifeFieldDiff(name, getattr(old, name), getattr(updated, name))
        for name in ('subject', 'composition', 'focus') if getattr(old, name) != getattr(updated, name))
    revision = before.activity_revision + 1
    event = LifeEvent(str(uuid5(NAMESPACE_URL, 'natural-feedback:' + command.payload_fingerprint)), head_sequence,
        'revise', '已按本次反馈局部修订文字方案。', revision, proposal['reason_code'])
    decision = ActivityDecision('revise', proposal['reason_code'], (), '依据本次反馈局部修订。', deps)
    result = ActivityResult('composition-text', updated, revision, differences, event, deps)
    return replace(record, kind='feedback', phase='rework', plan=updated, activity_revision=revision,
        decision=decision, result=result, source_dependencies=deps,
        reply_dependencies=tuple(sorted(set(record.reply_dependencies) | set(deps))), feedback=feedback)


def build_feedback_preview(envelope, identity, message, dialogue, enabled, view, contract):
    # Existing bounded projection builder, while the new purpose is explicit.
    preview = build_reply_preview(envelope, identity, message, dialogue, enabled, view, contract)
    payload = dict(preview['payload'])
    payload['evidence'] = dict(shared_experience=payload['evidence']['shared_experience'])
    return dict(policy=FEEDBACK_POLICY, payload=dict(payload,
        current_plan=None if view['current_plan'] is None else asdict(view['current_plan']),
        activity_revision=view['activity_revision'], current_feedback=current_feedback(view)))


def build_feedback_choice_preview(envelope, identity, view, contract):
    preview = build_choice_preview(envelope, identity, view, contract)
    return dict(policy=feedback_choice_policy(),
        payload=dict(preview['payload'], current_feedback=current_feedback(view)))
