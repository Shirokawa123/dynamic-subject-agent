"""Bounded color preference routing over existing canonical Memory records."""
from __future__ import annotations
import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING
from dynamic_subject_agent.current_message import direct_statement_clauses, direct_statement_spans

if TYPE_CHECKING:
    from dynamic_subject_agent.timeline import LivingMemoryRecord

_SCOPE = r'(?P<scope>[^，,。！？!?；;：:\n「」“”]{1,24}?)'
_COLOR = r'(?P<color>[^，,。！？!?；;：:\n「」“”]{1,24}色)'
_STATEMENT = re.compile(r'我(?:做)?' + _SCOPE + r'时(?P<add>也)?(?:偏爱|喜欢)' + _COLOR + r'(?P<tail>(?:[，,][^。！？!?；;\n]+)?)[。]?')
_NATURAL_STATEMENT = re.compile(r'给' + _SCOPE + r'挑颜色时[，,]我(?:通常)?(?P<add>也)?(?:偏爱|喜欢)' + _COLOR + r'(?P<tail>(?:[，,][^。！？!?；;\n]+)?)[。]?')
_UNCERTAIN = re.compile(r'(?:最近)?' + _SCOPE + r'用' + _COLOR + r'也不错(?P<tail>[，,](?:我)?(?:拿不准|不确定)(?:这算|是)(?:添一种|补充)还是(?:换掉原来的|替换))[。]?')
_CHANGE = re.compile(_SCOPE + r'改用' + _COLOR + r'[。]?')
_QUERY = re.compile(r'我(?:现在|目前)?(?:做)?' + _SCOPE + r'时(?:现在|目前)?(?:偏爱|喜欢)(?:什么|哪种)颜色[？?。]?')
UNAVAILABLE = '这次无法核实该场景的完整偏好记录，暂不判断当前偏好或执行更正。'

@dataclass(frozen=True)
class ColorPreference:
    scope: str
    color: str
    additive: bool
    tail: str
    needs_choice: bool = False

@dataclass(frozen=True)
class PreferenceRoute:
    action: str
    evidence: str = ''
    target: str | None = None
    reply: str = ''
    needs_choice: bool = False

def _preference(text: str) -> ColorPreference | None:
    if len(direct_statement_clauses(text)) != 1:
        return None
    match = _STATEMENT.fullmatch(text.strip()) or _NATURAL_STATEMENT.fullmatch(text.strip())
    if match:
        if any(marker in match['color'] for marker in ('不', '而', '但', '且', '或', '以及', '只', '如果')):
            return None
        return ColorPreference(match['scope'], match['color'], bool(match['add']), match['tail'])
    match = _UNCERTAIN.fullmatch(text.strip())
    if match:
        # An explicitly undecided option must never become a direct write.
        if (any(marker in match['scope'] for marker in ('如果', '假如', '假设', '要是', '朋友', '他说', '她说', '你说'))
            or any(marker in match['color'] for marker in ('不', '而', '但', '且', '或', '以及', '只', '如果'))):
            return None
        return ColorPreference(match['scope'], match['color'], False, match['tail'], needs_choice=True)
    match = _CHANGE.fullmatch(text.strip())
    if match and any(marker in match['color'] for marker in ('不', '而', '但', '且', '或', '以及', '只', '如果')):
        return None
    return ColorPreference(match['scope'], match['color'], False, '') if match else None

def _quotes(records: tuple[LivingMemoryRecord, ...]) -> str:
    return '\n'.join(f'「{content}」' for content in dict.fromkeys(record.content for record in records))


def recorded_preference(record: LivingMemoryRecord) -> ColorPreference | None:
    """Undecided legacy text alone cannot prove the user confirmed a choice."""
    parsed = _preference(record.content)
    if parsed is None or (parsed.needs_choice and not record.preference_confirmed):
        return None
    return replace(parsed, additive=parsed.additive or record.preference_additive)


def explicit_preference_replacement(message: str):
    """Only the existing complete old/new literal command, not quoted speech."""
    match = re.fullmatch(r'更正记忆：把「([^」]+)」改成「([^」]+)」[。]?', message.strip())
    return match if match is not None and _preference(match[2]) is not None else None

def route_preference(message: str, records: tuple[LivingMemoryRecord, ...], *, complete: bool, readable: bool = True) -> PreferenceRoute | None:
    """No guessed aliases, inferred recency, or cross-scenario replacements."""
    text = message.strip()
    if re.fullmatch(r'(?:也喜欢|也偏爱|改用)[^。！？!?；;\n]{1,24}色[。]?', text):
        return PreferenceRoute('none', reply='这是哪个场景的偏好？请把场景和颜色一起写明，这次暂未保存或更正。')
    query = _QUERY.fullmatch(text)
    if query and len(direct_statement_clauses(text.rstrip('？?'))) != 1:
        query = None
    literal = explicit_preference_replacement(text)
    body = text.removeprefix('更正记忆：').removeprefix('请记住：')
    pref = _preference(literal[2] if literal else body)
    if query is None and pref is None:
        return None
    if not complete or not readable:
        return PreferenceRoute('none', reply=UNAVAILABLE)
    scope = query['scope'] if query else pref.scope
    matched = tuple((record, parsed) for record in records if record.status == 'active'
        and (parsed := recorded_preference(record)) is not None and parsed.scope == scope)
    selected = tuple(record for record, _ in matched)
    if query:
        if not selected:
            return PreferenceRoute('none', reply=f'暂时没有能明确对应“{scope}”场景的颜色偏好记录；这不代表全部记忆为空。')
        if len(selected) > 5:
            return PreferenceRoute('none', reply=f'“{scope}”有超过五条适用记录，暂时无法简洁确认；请用完整原文指定要核对的记录。')
        bases = {parsed.color for _, parsed in matched if not parsed.additive}
        colors = {parsed.color for _, parsed in matched}
        quotes = _quotes(selected)
        if len(bases) > 1:
            return PreferenceRoute('none', reply=f'“{scope}”场景下有多条仍活跃的偏好：\n{quotes}\n这些是同时喜欢，还是后来替换了之前的偏好？请写明要补充的颜色，或用完整原文指定要更正的一条。')
        lead = '其中明确表述或经确认的新增偏好作为补充保留。' if len(colors) > 1 else ''
        return PreferenceRoute('none', reply=f'关于“{scope}”的颜色偏好，你明确记录过：\n{quotes}' + ('\n' + lead if lead else ''))
    if literal:
        if pref.needs_choice:
            return PreferenceRoute('none', reply='新原文仍未明确补充还是替换，这次没有更正。请先单独说明该场景的新颜色，再确认选择。')
        old = tuple(record for record in selected if record.content == literal[1])
        if len(old) != 1:
            return PreferenceRoute('none', reply='无法按完整旧原文唯一定位同场景的活跃偏好，这次没有更正。')
        return PreferenceRoute('revise', literal[2], old[0].memory_id)
    changing = not pref.needs_choice and (text.startswith('更正记忆：') or _CHANGE.fullmatch(body) is not None)
    if changing:
        if len(matched) != 1:
            return PreferenceRoute('none', reply=f'“{scope}”的旧偏好无法唯一确定。这次没有更正；请用“更正记忆：把「完整旧原文」改成「完整新原文」”指定一条。')
        old, old_pref = matched[0]
        if old_pref.tail and not text.startswith('更正记忆：'):
            return PreferenceRoute('none', reply=f'原记录还包含其他内容：\n「{old.content}」\n这次没有更正。请提供完整新原文，明确哪些内容要保留。')
        if body == old.content:
            return PreferenceRoute('none', reply='这条偏好已是所提供的内容，本轮没有重复更正。')
        return PreferenceRoute('revise', body, old.memory_id)
    if any(parsed.color == pref.color and parsed.tail == pref.tail for _, parsed in matched):
        return PreferenceRoute('none', reply='该场景已有相同颜色和限定内容的记录，本轮没有重复保存。')
    if pref.needs_choice and not matched:
        return PreferenceRoute('none', reply=f'暂时没有能明确对应“{scope}”场景的旧偏好，无法判断补充或替换。请把该场景的完整偏好重新说明，这次暂未保存。')
    if matched and not pref.additive:
        return PreferenceRoute('none', evidence=body, needs_choice=True, reply=f'“{scope}”已有偏好：\n{_quotes(selected[:5])}\n“{pref.color}”是补充还是替换？这次暂未保存。请在下一条消息回答“是补充”“替换”或“算了”；30分钟内有效。')
    return PreferenceRoute('create', body)


def preference_change_allowed(message: str, evidence: str, action: str, target: str | None, kind: str,
    records: tuple[LivingMemoryRecord, ...], *, complete: bool) -> bool:
    """A provider-selected substring is not authority to replace a preference."""
    route = route_preference(message, records, complete=complete)
    old = next((record for record in records if record.memory_id == target), None)
    if route is None and _preference(evidence) is not None:
        direct = [message[clause.start:clause.end].strip() for clause in direct_statement_spans(message)
            if clause.text.removeprefix('更正记忆：').removeprefix('请记住：') == evidence.rstrip('。')]
        route = route_preference(direct[0], records, complete=complete) if len(direct) == 1 else None
        if route is None:
            return False
    if route is None:
        return old is None or _preference(old.content) is None
    return (route.action == action and route.evidence.rstrip('。') == evidence.rstrip('。') and route.target == target and kind == 'durable')
