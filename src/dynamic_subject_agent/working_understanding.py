"""S145 bounded, revisable working interpretations; no remote authority."""
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from hashlib import sha256

from dynamic_subject_agent.shared_activity import (
    SharedActivityInput, shared_contract, build_record, build_choice_preview,
    build_reply_preview, shared_choice_policy, shared_reply_policy, digest)

WORKING_AUTHORITY = 'original-working-understanding-local-s145-1'
WORKING_INTENT = 'working-understanding-system-input'
WORKING_VERSION = 'working-understanding-local-s145-1'
SCOPE = 'composition-text'
FORM_POLICY = (
    '只为当前构图文字活动提出可修正的暂定工作理解，不形成永久用户偏好、人物身份、关系或人格，不进行Reflection。'
    'exchanges是本身份已提交用户逐字原话，只证明曾这样说；activity_result若有只是已提交的构图文字方案，不证明图片完成。'
    '保留否定、假想和情境限定；原话不足或互相冲突无法支持当前工作理解时返回insufficient。'
    'background是有范围的已审人物资料，不是用户经历。'
    '只输出JSON exact {status,scope,statement,basis_refs}；scope=composition-text；status仅formed或insufficient。'
    'formed的statement非空且最多240字符，basis_refs为实际提供的U1/U2/A1中不重复的标签，必须包含U1和U2。'
    'insufficient的statement为空字符串且basis_refs为空数组，不补造来源。'
)
WORKING_SCOPE_POLICY = (
    'working_understanding若有是当前构图讨论的可修正暂定理解，support保留原话与形成时的文字方案。'
    '它不是永久偏好、世界事实、已完成图片或本人的人格；仅在当前话题或构图取舍相关时参考，允许不同意或不使用。'
    'null不证明从未交流，不补造旧理解。不要把内部标签或形成流程当台词。'
)
CHOICE_POLICY = shared_choice_policy('self-directed-activity').replace(
    'basis_refs只可为空或本请求实际提供的E1；',
    'basis_refs仅可为空或不重复的本请求实际提供的E1/W1标签；') + WORKING_SCOPE_POLICY
# Retain S144's natural final-text expression protocol for this new LOCAL
# candidate; the ModelGateway result is still a typed local reply DTO.
from dynamic_subject_agent.living_activity import living_policies
REPLY_POLICY = living_policies('final-text')[2] + WORKING_SCOPE_POLICY


def working_contract(binding):
    return dict(shared_contract(binding), version=WORKING_VERSION,
        excluded='remote-automatic-life-sharing-persona-rewrite-reflection-cloud-migration',
        technical_variant=dict(name='working-local', timeline_schema=7, scope=SCOPE,
            max_sources=2, max_quote_chars=400, max_statement_chars=240,
            form_policy_sha=sha256(FORM_POLICY.encode()).hexdigest(),
            choice_policy_sha=sha256(CHOICE_POLICY.encode()).hexdigest(),
            reply_policy_sha=sha256(REPLY_POLICY.encode()).hexdigest()))


@dataclass(frozen=True)
class WorkingSourceQuote:
    source_head_sequence: int
    quote: str


@dataclass(frozen=True)
class WorkingUnderstandingRequest:
    target_profile_id: str
    target_timeline_id: str
    request_id: str
    expected_revision: int
    sources: tuple[WorkingSourceQuote, ...] = ()
    action: str = 'form'
    confirmed: bool = False

    @property
    def request_digest(self):
        return digest(asdict(self))


def validate_sources(sources):
    if type(sources) not in (tuple, list) or len(sources) != 2:
        raise ValueError('two distinct committed sources required')
    result = []
    for source in sources:
        row = asdict(source) if type(source) is WorkingSourceQuote else source
        if (type(row) is not dict or set(row) != {'source_head_sequence', 'quote'}
            or type(row['source_head_sequence']) is not int or row['source_head_sequence'] <= 0
            or type(row['quote']) is not str or not row['quote'].strip() or len(row['quote']) > 400 or '\x00' in row['quote']):
            raise ValueError('bounded exact user quote required')
        result.append(dict(row))
    if result[0]['source_head_sequence'] == result[1]['source_head_sequence']:
        raise ValueError('different committed user turns required')
    return tuple(result)


def source_key(source):
    return 'U:' + digest(source)


def understanding_key(understanding):
    return 'W:' + digest(understanding)


def validate_permission(value):
    if (type(value) is not dict or set(value) != {'revision', 'source_blocked'}
        or type(value['revision']) is not int or value['revision'] < 0 or type(value['source_blocked']) is not bool):
        raise ValueError('exact working source permission required')
    return dict(value)


def initial_working(permission):
    return dict(revision=0, permission=validate_permission(permission), formation_status='initial', understanding=None)


def validate_working(value):
    if (type(value) is not dict or set(value) != {'revision', 'permission', 'formation_status', 'understanding'}
        or type(value['revision']) is not int or value['revision'] < 0
        or value['formation_status'] not in ('initial', 'formed', 'insufficient', 'disabled')):
        raise ValueError('exact bounded working record required')
    validate_permission(value['permission'])
    understanding = value['understanding']
    if understanding is not None:
        if (type(understanding) is not dict or set(understanding) != {'scope','statement','basis_refs','sources','activity_result','dependencies','revision'}
            or understanding['scope'] != SCOPE or type(understanding['statement']) is not str
            or not understanding['statement'].strip() or len(understanding['statement']) > 240 or '\x00' in understanding['statement']
            or type(understanding['revision']) is not int or not 0 < understanding['revision'] <= value['revision']
            or type(understanding['dependencies']) is not list or any(type(x) is not str for x in understanding['dependencies'])
            or understanding['dependencies'] != sorted(set(understanding['dependencies']))):
            raise ValueError('bounded tentative understanding required')
        validate_sources(understanding['sources'])
        validate_form(dict(status='formed', scope=SCOPE, statement=understanding['statement'], basis_refs=understanding['basis_refs']),
            understanding['activity_result'] is not None)
        activity = understanding['activity_result']
        if activity is not None:
            from dynamic_subject_agent.first_life import validate_plan
            if (type(activity) is not dict or set(activity) != {'source_head_sequence','event_id','kind','plan','dependencies'}
                or type(activity['source_head_sequence']) is not int or activity['source_head_sequence'] <= 0
                or type(activity['event_id']) is not str or activity['kind'] != SCOPE
                or type(activity['dependencies']) is not list):
                raise ValueError('typed committed composition source required')
            validate_plan(activity['plan'])
    return value


def validate_form(value, has_activity):
    if (type(value) is not dict or set(value) != {'status','scope','statement','basis_refs'}
        or value['scope'] != SCOPE or value['status'] not in ('formed','insufficient')
        or type(value['statement']) is not str or type(value['basis_refs']) is not list):
        raise ValueError('exact working formation output required')
    refs = value['basis_refs']
    if value['status'] == 'insufficient':
        if value['statement'] != '' or refs != []:
            raise ValueError('insufficient has no proposed effect')
    elif (not value['statement'].strip() or len(value['statement']) > 240 or '\x00' in value['statement']
        or any(type(x) is not str for x in refs) or len(refs) != len(set(refs))
        or not {'U1','U2'} <= set(refs) or not set(refs) <= ({'U1','U2','A1'} if has_activity else {'U1','U2'})):
        raise ValueError('working source references invalid')
    return value


def visible_understanding(record, enabled, cutoff):
    if not enabled or record.working is None:
        return None
    understanding = record.working['understanding']
    if understanding is None or any(x['source_head_sequence'] <= cutoff for x in understanding['sources']):
        return None
    activity = understanding['activity_result']
    if activity is not None and activity['source_head_sequence'] <= cutoff:
        return None
    # Any transitive dependencies from a previous interpretation/selected E1
    # must still be eligible. Never erase them when a model omits a reference.
    direct = {source_key(x) for x in understanding['sources']}
    source = record.source if record.source and record.source.source_head_sequence > cutoff else None
    if source:
        direct.add(source.source_key)
    if not set(understanding['dependencies']) <= direct:
        return None
    return understanding


def working_valid_sources(record, enabled, cutoff):
    understanding = visible_understanding(record, enabled, cutoff)
    if understanding is None:
        return set()
    return {understanding_key(understanding), *(source_key(x) for x in understanding['sources'])}


def support_projection(understanding):
    if understanding is None:
        return None
    activity = understanding['activity_result']
    return dict(label='W1', scope=SCOPE, statement=understanding['statement'], support=dict(
        exchanges=[dict(label='U'+str(i+1), quote=x['quote']) for i,x in enumerate(understanding['sources'])],
        activity_result=None if activity is None else dict(label='A1', kind=SCOPE, plan=deepcopy(activity['plan']))))


def _old_contract(contract):
    from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
    return shared_contract({key:contract[key] for key in APPROVED_BINDING})


def build_form_preview(envelope, identity, view, contract, sources):
    sources = validate_sources(sources)
    base = build_choice_preview(envelope, identity, view, _old_contract(contract))
    result = view['visible_result']
    return dict(policy=FORM_POLICY, payload=dict(background=base['payload']['background'], scope=SCOPE,
        exchanges=[dict(label='U'+str(i+1), quote=x['quote']) for i,x in enumerate(sources)],
        activity_result=None if result is None or result.plan is None else dict(label='A1', kind=SCOPE, plan=asdict(result.plan))))


def build_working_choice_preview(envelope, identity, view, contract):
    value = build_choice_preview(envelope, identity, view, _old_contract(contract))
    value['policy'] = CHOICE_POLICY
    value['payload']['working_understanding'] = support_projection(view['visible_understanding'])
    if view['current_plan'] is None and view['phase'] != 'unstarted':
        value['payload']['current_activity']['allowed_actions'] = ('revise','defer')
    return value


def build_working_reply_preview(envelope, identity, message, dialogue, enabled, view, contract):
    value = build_reply_preview(envelope, identity, message, dialogue, enabled, view, _old_contract(contract))
    value['policy'] = REPLY_POLICY
    value['payload']['evidence']['working_understanding'] = support_projection(view['visible_understanding'])
    return value


def build_working_record(view, *, command, authorization, permission, head_sequence, choice=None, formation=None):
    permission = validate_permission(permission)
    before = view['record']
    state = deepcopy(before.working or initial_working(permission))
    state['permission'] = permission
    working_command = type(command) is SharedActivityInput and command.input_kind in ('understand','understanding-disable')
    if working_command:
        if command.working_permission != permission or command.expected_revision != before.revision:
            raise ValueError('working preparation permission changed')
        record = replace(before, revision=before.revision+1, kind='understanding', reply_dependencies=(), dialogue_dependencies=(),
            authorization=asdict(authorization), context_revision=view['context_revision'])
        if command.input_kind == 'understanding-disable':
            state.update(revision=state['revision']+1, formation_status='disabled', understanding=None)
        else:
            if permission['source_blocked'] or not authorization.history_enabled:
                raise ValueError('working formation requires active source disclosure permission')
            value = validate_form(formation, view['visible_result'] is not None and view['visible_result'].plan is not None)
            state['formation_status'] = value['status']
            if value['status'] == 'formed':
                sources = validate_sources(command.working_sources)
                result = view['visible_result']
                activity = None if result is None or result.plan is None else dict(source_head_sequence=result.event.head_sequence,
                    event_id=result.event.event_id, kind=SCOPE, plan=asdict(result.plan), dependencies=list(result.source_dependencies))
                deps = {source_key(x) for x in sources}
                for source in sources:
                    deps.update(view['reply_dependencies'].get(source['source_head_sequence'], ()))
                if activity:
                    deps.update(activity['dependencies'])
                state['revision'] += 1
                state['understanding'] = dict(scope=SCOPE, statement=value['statement'], basis_refs=list(value['basis_refs']),
                    sources=list(sources), activity_result=activity, dependencies=sorted(deps), revision=state['revision'])
        return replace(record, working=validate_working(state))
    effective = replace(authorization, history_enabled=False) if permission['source_blocked'] else authorization
    # Reuse exact phase/difference adjudication, then add every supplied working
    # input to the resulting taint, regardless of the model's claimed reasons.
    refs = None
    if choice is not None:
        refs = choice.get('basis_refs')
        allowed = ({'E1'} if view['visible_source'] is not None else set()) | ({'W1'} if view['visible_understanding'] is not None else set())
        if type(refs) is not list or any(type(x) is not str for x in refs) or len(refs) != len(set(refs)) or not set(refs) <= allowed:
            raise ValueError('actual working choice references required')
        choice = dict(choice, basis_refs=[x for x in refs if x != 'W1'])
    transition_before = before
    if (type(command) is SharedActivityInput and command.input_kind == 'advance'
        and view['current_plan'] is None and before.phase != 'unstarted'):
        # The old phase remains historical. With its plan unavailable, a new
        # independent revision follows the existing rework adjudication rule.
        transition_before = replace(before,phase='rework')
    record = build_record(transition_before, command=command, authorization=effective, cutoff=view['cutoff_sequence'],
        context_revision=view['context_revision'], head_sequence=head_sequence, choice=choice,
        dialogue_dependencies=view['dialogue_dependencies'])
    record = replace(record, authorization=asdict(authorization))
    if refs is not None:
        record = replace(record, decision=replace(record.decision, basis_refs=tuple(refs)))
    understanding = view['visible_understanding'] if not permission['source_blocked'] else None
    if understanding is not None and (record.kind == 'decision' or record.kind == 'chat'):
        deps = {understanding_key(understanding), *understanding['dependencies']}
        if record.kind == 'decision':
            merged = tuple(sorted(set(record.source_dependencies)|deps))
            record = replace(record, source_dependencies=merged, decision=replace(record.decision, source_dependencies=merged),
                result=replace(record.result, source_dependencies=merged))
        else:
            record = replace(record, reply_dependencies=tuple(sorted(set(record.reply_dependencies)|deps)))
    return replace(record, working=validate_working(state))
