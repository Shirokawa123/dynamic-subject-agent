"""LOCAL natural experience cycle on the existing shared Publication record.

No transport, sidecar memory store or remote qualification. Model output picks
bounded speech acts; Python supplies any quoted source or completed-plan fact.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone, timedelta

from dynamic_subject_agent.natural_experience import (
    adjudicate_experience, decode_experience, encode_experience, visible_experience)
from dynamic_subject_agent.shared_activity import SharedExperience, SharedActivityInput, visible_state
from dynamic_subject_agent.living_activity import living_contract, build_living_record
from dynamic_subject_agent.whole_context_boundary import WholeContextInput

VERSION = 'natural-experience-local-m031-1'
LIVE_VERSION = 'natural-conversation-live-m032-1'
LIVE_REVIEW = 'd077bebe7d0c9dd32c0ae8473cb2af491818c4e8841dedcc5fea282d32b8ce48'
RENDER_VERSION = 'source-bound-speech-m031-1'
ACTS = ('ask', 'wish_compare', 'recall_user', 'discuss_plan', 'unknown_past', 'acknowledge_change')


def local_day(observed_at_us):
    if type(observed_at_us) is not int or observed_at_us <= 0:
        raise ValueError('trusted operation time required')
    return datetime.fromtimestamp(observed_at_us // 1_000_000, timezone(timedelta(hours=8))).date().isoformat()


def contract(binding, *, live=False):
    base = living_contract(binding, activity_kind='herb-note-outline', independent=True)
    return dict(base, version=LIVE_VERSION if live else VERSION, natural_experience_local=not live,
        technical_variant=dict(base['technical_variant'], natural_record_version=1,
            natural_render_version=LIVE_REVIEW if live else RENDER_VERSION, natural_timezone='Asia/Shanghai', automatic_source_limit=1))


def is_contract(value):
    return type(value) is dict and value.get('version') in (VERSION, LIVE_VERSION)


def validate_speech(value, *, live=False):
    if live:
        if type(value) is not dict or set(value) != {'reply_text'}:
            raise ValueError('exact natural reply required')
        from dynamic_subject_agent.original_whole_chat import validate_whole_reply
        validate_whole_reply(dict(reply_text=value['reply_text'], language='zh'))
        return deepcopy(value)
    if (type(value) is not dict or set(value) != {'act', 'reference', 'style'}
            or value['act'] not in ACTS or value['style'] not in ('brief', 'gentle')
            or value['reference'] not in (None, 'E1', 'A1')):
        raise ValueError('closed speech plan required; free text cannot assert an activity')
    expected = 'E1' if value['act'] == 'recall_user' else 'A1' if value['act'] == 'discuss_plan' else None
    if value['reference'] != expected:
        raise ValueError('speech act/reference mismatch')
    return deepcopy(value)


def validate_natural(value):
    if (type(value) is not dict or set(value) != {'version', 'experience', 'selection', 'speech', 'day'}
            or value['version'] not in (VERSION, LIVE_VERSION)):
        raise ValueError('exact natural record required')
    from datetime import date
    if type(value['day']) is not str or date.fromisoformat(value['day']).isoformat() != value['day']:
        raise ValueError('exact local day required')
    experience = decode_experience(value['experience'])
    if experience is not None and experience.local_day > value['day']:
        raise ValueError('source from future day')
    if value['speech'] is not None:
        validate_speech(value['speech'], live=value['version'] == LIVE_VERSION)
    if value['selection'] is not None and (type(value['selection']) is not dict
            or set(value['selection']) != {'action', 'duration', 'reason_code'}):
        raise ValueError('exact stored selection required')
    selection = value['selection']
    if selection is not None:
        action, duration, reason = (selection[k] for k in ('action', 'duration', 'reason_code'))
        valid = (action == 'remember' and duration in ('today', 'until_changed') and reason in ('temporary', 'ongoing', 'correction')
            or action == 'keep' and duration is None and reason in ('irrelevant', 'unclear', 'too-long')
            or action == 'forget' and duration is None and reason == 'explicit-forget')
        if not valid:
            raise ValueError('closed stored selection required')
    return value


def _experience(record, day, enabled, cutoff):
    value = None if record.natural is None else decode_experience(validate_natural(record.natural)['experience'])
    value = visible_experience(value, day)
    return value if enabled and value is not None and value.source_head_sequence > cutoff else None


def natural_view(view, day):
    """Filter expired/stopped sources and their plans without a read-side write."""
    experience = _experience(view['record'], day, view['effective_history_enabled'], view['cutoff_sequence'])
    source = view['record'].source if experience is not None else None
    current = replace(view['record'], source=source)
    visible = visible_state(current, enabled=view['effective_history_enabled'], cutoff=view['cutoff_sequence'])
    from dynamic_subject_agent.living_activity import living_valid_sources
    valid = living_valid_sources(current, visible['valid_sources'], enabled=view['effective_history_enabled'], cutoff=view['cutoff_sequence'])
    exchange = view.get('natural_exchange', [])
    if record_value := view['record'].natural:
        if record_value['experience'] != encode_experience(experience):
            exchange = []
    return dict(view, natural_exchange=exchange, visible_source=visible['source'], current_plan=visible['current_plan'],
        visible_result=visible['result'], valid_sources=valid, natural_experience=experience,
        dialogue_dependencies=())


def expression_frame(view, current_text, *, changed=False):
    source, result = view['visible_source'], view['visible_result']
    allowed = [act for act in ACTS if (act != 'recall_user' or source is not None)
        and (act != 'discuss_plan' or result is not None and result.plan is not None)
        and (act != 'acknowledge_change' or changed)]
    return dict(current_user_text=current_text,
        experience=None if source is None else dict(label='E1', quote=source.quote),
        activity_result=None if result is None or result.plan is None else
            dict(label='A1', kind='text-outline', subject=result.plan.subject),
        allowed_acts=allowed)


def render_speech(speech, frame, *, changed):
    speech = validate_speech(speech)
    if speech['act'] not in frame['allowed_acts']:
        raise ValueError('speech act lacks current evidence or change')
    act, gentle = speech['act'], speech['style'] == 'gentle'
    if act == 'recall_user':
        source = frame['experience']
        if source is None:
            raise ValueError('no valid user source for this utterance')
        return '你说过：' + _quoted(source['quote']) + ('\n现在还是这样想的吗？' if gentle else '\n想接着聊这件事吗？')
    if act == 'discuss_plan':
        result = frame['activity_result']
        if result is None:
            raise ValueError('no committed text plan for this utterance')
        return '我留下的那份文字方案是' + _quoted(result['subject']) + '。你想先看哪一处？'
    if act == 'acknowledge_change':
        if not changed:
            raise ValueError('cannot claim a source change that did not happen')
        return '好，我按你现在的意思重新理解。我们从这里接着聊。'
    if act == 'wish_compare':
        return '我想一起比较不同的想法。你愿意和我聊聊吗？'
    if act == 'unknown_past':
        return '刚才那段我说不准，先不乱讲。我们从现在接着聊吧。'
    return '我想听听你这会儿在意的事。想从哪里聊起？' if gentle else '这会儿想聊点什么？'


def _quoted(text):
    # Only presentation punctuation changes; the canonical original is intact.
    return '“' + text.replace('“', '「').replace('”', '」').replace('\r', ' ').replace('\n', ' ') + '”'


def build_natural_record(view, *, command, authorization, permission, head_sequence, day,
        selection=None, speech=None, choice=None, version=VERSION):
    """Recomputed by Publication; neither a second write nor a hidden confirm."""
    before = view['record']
    enabled = authorization.history_enabled and not permission['source_blocked']
    previous = _experience(before, day, enabled, view['cutoff_sequence'])
    ordinary = type(command) not in (SharedActivityInput, WholeContextInput)
    if ordinary and enabled:
        selected = adjudicate_experience(selection, current_text=command.utterance, previous=previous,
            source_head_sequence=head_sequence, local_day=day)
    else:
        if selection is not None:
            raise ValueError('only an enabled user text can select experience')
        selected = previous
    if type(command) is WholeContextInput or type(command) is SharedActivityInput and command.input_kind == 'disable':
        selected = None
    if type(command) is SharedActivityInput and command.input_kind == 'select':
        raise ValueError('this LOCAL lane forms sources through user text, not implicit confirmations')
    old_source = before.source
    source = None if selected is None else (old_source if previous == selected and old_source is not None else
        SharedExperience(selected.source_head_sequence, before.revision + 1, selected.quote))
    effective_before = replace(before, source=source)
    effective_view = dict(view, record=effective_before, effective_history_enabled=enabled)
    visible = visible_state(effective_before, enabled=enabled, cutoff=view['cutoff_sequence'])
    # A dependent plan remains in history, but is no longer a live plan after
    # its source is corrected, stopped or expired. A fresh plan can then start.
    if before.plan is not None and visible['current_plan'] is None:
        effective_before = replace(effective_before, phase='unstarted', plan=None, result=None,
            decision=None, source_dependencies=())
    effective_view.update(record=effective_before, visible_source=visible['source'],
        current_plan=visible['current_plan'], visible_result=visible['result'], valid_sources=visible['valid_sources'],
        dialogue_dependencies=())
    record = build_living_record(effective_view, command=command, authorization=authorization,
        permission=permission, head_sequence=head_sequence, choice=choice)
    if version not in (VERSION, LIVE_VERSION):
        raise ValueError('exact natural version required')
    live = version == LIVE_VERSION
    natural = dict(version=version, experience=encode_experience(selected), selection=deepcopy(selection),
        speech=None if speech is None else validate_speech(speech, live=live), day=day)
    record = replace(record, source=source, natural=validate_natural(natural))
    if ordinary:
        frame = expression_frame(effective_view, command.utterance, changed=selected != previous)
        text = speech['reply_text'] if live else render_speech(speech, frame, changed=selected != previous)
    else:
        if speech is not None:
            raise ValueError('control/action does not carry a free speech plan')
        from dynamic_subject_agent.whole_context_boundary import CONTEXT_RECEIPT
        text = CONTEXT_RECEIPT if type(command) is WholeContextInput else ('已停用这段共同经历。' if record.result is None else record.result.event.summary)
    return record, text
