"""Current-message goal commands with literal operands and source spans."""
from dataclasses import dataclass
import re
from dynamic_subject_agent.current_message import direct_statement_spans

_PREFIX = r'(?:(?:换个话题|说正事)[：:]|[（(]诊断对照[）)])'
SELF_GOAL_PREFIX = r'我(?:也)?给自己定(?:个|一个)目标[：:]'
_CONDITIONS = ('如果', '假如', '假设', '要是', '除非', '只有', '只要', '否则', '前提', '但', '不过')

@dataclass(frozen=True)
class CurrentGoalCommand:
    action: str
    terms: str
    evidence: str
    start: int
    end: int
    old_terms: str | None = None
    explicit: bool = True
    supported: bool = True


def current_goal_commands(message: str) -> tuple[CurrentGoalCommand, ...]:
    commands = []
    for statement in direct_statement_spans(message):
        raw = statement.text
        prefix = re.match(_PREFIX, raw)
        body = raw[prefix.end():].lstrip() if prefix else raw
        direct = re.fullmatch(SELF_GOAL_PREFIX + r'(.+)', body) if prefix else None
        if direct:
            commands.append(CurrentGoalCommand('create', direct[1].strip(), raw, statement.start, statement.end,
                supported=not any(x in body for x in (*_CONDITIONS, '，', ','))))
            continue
        compound = re.fullmatch(r'(.+?)[，,]((?:我)?也给自己定(?:个|一个)目标[：:])(.+)', body)
        if not compound:
            continue
        arrangement = compound[1]
        # Resolve omitted 我 only from a current, direct first-person arrangement.
        own = re.match(r'^(?:(?:今天|明天|后天|周[一二三四五六日天]|下周[一二三四五六日天])(?:上午|下午|晚上)?)?我(?:会|准备|打算|要)', arrangement)
        if own is None:
            continue
        offset = raw.index(compound[2], len(raw) - len(body) + len(arrangement))
        commands.append(CurrentGoalCommand('create', compound[3].strip(), raw[offset:],
            statement.start + offset, statement.end,
            supported=not any(x in body for x in _CONDITIONS) and not any(x in compound[3] for x in '，,')))
    # Quotes here are operands of a full explicit edit, never unwrapped commands.
    # Full matching prevents lifting an edit out of a quote, condition or report.
    quote = r'(?P<oq>[“「"])(?P<old>[^“”「」"\n]+)(?P<oc>[”」"])'
    new = r'(?P<nq>[“「"])(?P<new>[^“”「」"\n]+)(?P<nc>[”」"])'
    pattern = r'\s*(?:' + _PREFIX + r')?\s*把(?P<label>目标)?' + quote + r'(?:改成|改为|换成)' + new + r'(?P<tail>[^\n]*)'
    matched = re.fullmatch(pattern, message)
    if matched:
        pairs = {'“': '”', '「': '」', '"': '"'}
        paired = pairs[matched['oq']] == matched['oc'] and pairs[matched['nq']] == matched['nc']
        tail = matched['tail'].rstrip('。').strip()
        unchanged = not tail or re.fullmatch(r'[，,](?:(?:安排|计划)(?:保持)?不变|(?:椅子|工具|材料|点心)照带)', tail) is not None
        commands.append(CurrentGoalCommand('revise', matched['new'], message[:matched.end('nc')].strip(),
            0, len(message), matched['old'], bool(matched['label']), paired and unchanged))
    return tuple(commands)


def applicable_goal_commands(message: str, records) -> tuple[CurrentGoalCommand, ...]:
    active_terms = {record.terms for record in records if record.kind == 'goal' and record.status == 'active'}
    return tuple(command for command in current_goal_commands(message)
        if command.explicit or command.old_terms in active_terms)
