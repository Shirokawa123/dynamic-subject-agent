"""Local reminder capability wording; never schedules or changes state."""
from __future__ import annotations

import re
from dynamic_subject_agent.recent_dialogue import expression_request_text

REMINDER_BOUNDARY = '我目前不提供定时提醒，也不能保证在下次聊天时自动提起这件事。你可以在需要时问我，我们再根据当时可用的记录继续。'


def reminder_request_kind(message: str) -> str | None:
    text = expression_request_text(message)
    clauses = []
    for sentence in re.split(r'[。！？!?；;]', text):
        narrative = False
        for clause in re.split(r'[，,]', sentence):
            clause = clause.strip()
            if re.match(r'^(?:请|帮我|替我)?(?:写|编|创作).*(?:故事|对白|场景)[：:]', clause):
                narrative = True
                continue
            if narrative and not re.match(r'^(?:另外|也请|同时请)', clause):
                continue
            narrative = False
            clauses.append(clause)
    for clause in clauses:
        clause = clause.strip()
        if re.match(r'^(?:请)?(?:不用|不要|别|不必|取消)(?:再)?(?:提醒我|提醒)', clause):
            return 'declined'
        if re.match(r'^(?:请|帮我|另外)?(?:设置|设个|安排)(?:一个)?提醒', clause):
            return 'requested'
        if (re.match(r'^(?:请|另外)?(?:你(?:能|会|可以|能不能|是否)?|提醒我|明天|后天|今晚|下次|到时候|届时)', clause)
            and '提醒我' in clause
            and (re.search(r'下次|明天|后天|今晚|定时|到时候|届时', clause)
                or re.fullmatch(r'你(?:能|会|可以|能不能|是否)(?:自动)?提醒我(?:吗)?', clause))):
            return 'requested'
    return None


def has_reminder_promise(text: str) -> bool:
    future = re.search(r'我(?:一定)?(?:会|将)(?:在[^。！？!?，,]{0,24})?提醒你|(?:下次(?:聊天|见面)?(?:时)?|到时候|届时)(?:我)?(?:会|再)提醒你', text)
    capability = re.search(r'我(?:可以|能)(?:在)?(?:下次|明天|后天|定时|自动|后台)[^。！？!?，,：:]{0,24}提醒你', text)
    result = re.search(r'提醒(?:任务)?(?:已经|已)(?:设置|安排|创建|取消|删除|关闭|开启)|提醒(?:设置|安排|取消)(?:成功|完成|好了|了)', text)
    return bool(future or capability or result)


def quoted_reminder_reference(message: str) -> tuple[str, ...]:
    if reminder_request_kind(message) is None and re.search(r'表达了什么|什么意思|解释|翻译|含义|意思', expression_request_text(message)):
        return tuple(re.findall(r'“[^”]*”|「[^」]*」|‘[^’]*’|"[^"]*"', message))
    return ()


def remove_reminder_promises(text: str, *, protected: tuple[str, ...] = ()) -> tuple[str, bool]:
    masked = text
    replacements = []
    for index, part in enumerate(protected):
        if part and part in masked:
            marker = f'\x00reminder-quote-{index}\x00'
            masked = masked.replace(part, marker)
            replacements.append((marker, part))
    originals = dict(replacements)
    kept = []
    removed = False
    for fragment in re.split(r'(\x00reminder-quote-\d+\x00)', masked):
        if fragment in originals:
            kept.append(originals[fragment])
            continue
        for sentence in re.findall(r'[^。！？!?]+[。！？!?]?', fragment):
            if has_reminder_promise(sentence):
                removed = True
            else:
                kept.append(sentence)
    return ''.join(kept).strip(), removed
