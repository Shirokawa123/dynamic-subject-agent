"""Approved change evidence for expression, separate from plan mutation sources."""
from dataclasses import replace

from dynamic_subject_agent.current_activity_change import current_activity_change, validate_current_activity_change
from dynamic_subject_agent.integrated_character_change_preview import CHANGE_POLICY


def eligible_current_change(view, *, enabled):
    """A context boundary also revokes source-free historical change excerpts."""
    result = view.get('visible_result')
    cutoff, before_head = view.get('cutoff_sequence'), view.get('result_before_plan_head')
    if (not enabled or result is None or type(cutoff) is not int or cutoff < 0
        or type(before_head) is not int or before_head <= cutoff
        or type(result.event.head_sequence) is not int or result.event.head_sequence <= cutoff):
        return None
    return current_activity_change(view)


def add_change_evidence(preview, view, *, enabled):
    change = eligible_current_change(view, enabled=enabled)
    return dict(policy=preview['policy'] + '\n\n' + CHANGE_POLICY,
        payload=dict(preview['payload'], current_result_change=change))


def without_change_evidence(payload):
    """Only the new mode may use this wrapper before the old exact validator."""
    if type(payload) is not dict or 'current_result_change' not in payload:
        raise ValueError('exact approved current result change field required')
    change = validate_current_activity_change(payload['current_result_change'])
    if 'turn' in payload and not payload['turn']['history_enabled'] and change is not None:
        raise ValueError('history-off cannot expose change evidence')
    return {key: value for key, value in payload.items() if key != 'current_result_change'}


def add_change_expression_dependencies(record, view, *, enabled, ordinary=False, sharing=False):
    if not (ordinary or sharing) or eligible_current_change(view, enabled=enabled) is None:
        return record
    dependencies = set(view['result_before_dependencies']) | set(view['visible_result'].source_dependencies)
    if ordinary:
        # Do not add expression-only old text to the new plan/result sources.
        return replace(record, reply_dependencies=tuple(sorted(set(record.reply_dependencies) | dependencies)))
    if sharing and record.living['considered'][-1]['share']:
        living = dict(record.living, shares=[dict(row) for row in record.living['shares']])
        latest = living['shares'][-1]
        latest['dependencies'] = sorted(set(latest['dependencies']) | dependencies)
        return replace(record, living=living)
    return record
