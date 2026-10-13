"""Pure bounded change evidence; both old and new result sources must be visible."""
from dynamic_subject_agent.first_life import LifeFieldDiff
from dynamic_subject_agent.shared_activity import ActivityResult

FIELDS = ('subject', 'composition', 'focus')


def _source_set(value):
    if (type(value) not in (tuple, list, set, frozenset)
        or any(type(source) is not str or not source for source in value)):
        return None
    return set(value)


def current_activity_change(view):
    """Never infer old-text permission from the current result's dependencies."""
    result = view.get('visible_result')
    if result is None:
        return None
    if type(result) is not ActivityResult:
        raise ValueError('verified activity result required')
    if result.event.kind != 'revise' or result.plan is None:
        return None
    before_sources = _source_set(view.get('result_before_dependencies'))
    current_sources = _source_set(result.source_dependencies)
    valid_sources = _source_set(view.get('valid_sources'))
    if (before_sources is None or current_sources is None or valid_sources is None
        or not before_sources <= valid_sources or not current_sources <= valid_sources):
        return None

    differences = {}
    for difference in result.differences:
        if (type(difference) is not LifeFieldDiff or difference.field not in FIELDS
            or difference.field in differences or type(difference.before) is not str
            or type(difference.after) is not str or '\x00' in difference.before + difference.after
            or difference.before == difference.after
            or difference.after != getattr(result.plan, difference.field)):
            raise ValueError('actual distinct result field changes required')
        differences[difference.field] = difference

    changes, unexpanded = [], []
    for field in FIELDS:
        if field not in differences:
            continue
        before, after = differences[field].before, differences[field].after
        start = 0
        while start < min(len(before), len(after)) and before[start] == after[start]:
            start += 1
        before_end, after_end = len(before), len(after)
        while before_end > start and after_end > start and before[before_end - 1] == after[after_end - 1]:
            before_end -= 1
            after_end -= 1
        before, after = before[start:before_end], after[start:after_end]
        if len(before) > 160 or len(after) > 240:
            unexpanded.append(field)
        else:
            changes.append(dict(field=field, before=before, after=after))
    return validate_current_activity_change(dict(action='revise', changes=changes, unexpanded_fields=unexpanded))


def validate_current_activity_change(value):
    """Validate the nullable exact public projection, never a mutation proposal."""
    if value is None:
        return None
    if (type(value) is not dict or set(value) != {'action', 'changes', 'unexpanded_fields'}
        or value['action'] != 'revise' or type(value['changes']) is not list
        or type(value['unexpanded_fields']) is not list
        or not 1 <= len(value['changes']) + len(value['unexpanded_fields']) <= 3):
        raise ValueError('exact bounded activity change required')
    fields = []
    for change in value['changes']:
        if (type(change) is not dict or set(change) != {'field', 'before', 'after'}
            or change['field'] not in FIELDS or type(change['before']) is not str
            or type(change['after']) is not str or len(change['before']) > 160
            or len(change['after']) > 240 or '\x00' in change['before'] + change['after']
            or change['before'] == change['after']):
            raise ValueError('exact actual bounded field change required')
        fields.append(change['field'])
    for field in value['unexpanded_fields']:
        if field not in FIELDS:
            raise ValueError('known unexpanded field required')
        fields.append(field)
    if len(set(fields)) != len(fields):
        raise ValueError('each changed field must occur exactly once')
    return value
