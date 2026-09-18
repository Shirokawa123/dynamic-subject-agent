"""Literal goal-change commands and their independent unchanged context."""
from dataclasses import dataclass
import re
from dynamic_subject_agent.current_message import DirectStatement, direct_statement_spans
from dynamic_subject_agent.unchanged_arrangement import is_unchanged_arrangement

@dataclass(frozen=True)
class NamedGoalChange:
    name: str
    terms: str
    evidence: str
    start: int
    end: int
    supported: bool

def named_goal_changes(message: str) -> tuple[NamedGoalChange, ...]:
    changes = []
    statements = direct_statement_spans(message)
    raw = message.strip().rstrip('。')
    parts = re.split(r'[，,]', raw, maxsplit=1)
    if (not statements and len(parts) == 2 and any(char in parts[1] for char in '“”「」"')
        and len(direct_statement_spans(parts[0])) == 1):
        # A quoted tail cannot hide a current explicit edit from the rejection
        # path and let Memory save the command instead. The tail stays invalid.
        statements = (DirectStatement(raw, len(message) - len(message.lstrip()), len(message)),)
    for statement in statements:
        parts = re.split(r'[，,]', statement.text, maxsplit=1)
        match = re.fullmatch(r'([^，,。！？!?；;：:]{2,60}?)(?:这个|这项)目标我(?:想|希望)?(?:改成|改为|换成)([^，,。！？!?；;：:]{1,500})', parts[0])
        if match is None:
            continue
        name = match[1].removeprefix('我的').strip()
        supported = bool(name) and not any(word in name for word in ('朋友的', '他的', '她的', '你的', '我们的', '如果', '假如'))
        if len(parts) > 1:
            tail = parts[1].strip()
            # A closed nominal structure cannot silently swallow another action
            # or condition. Unrecognized context must be stated separately.
            supported = supported and is_unchanged_arrangement(tail)
        changes.append(NamedGoalChange(name, match[2].strip(), parts[0], statement.start, statement.end, supported))
    return tuple(changes)

def matching_goal_refs(change: NamedGoalChange, targets) -> tuple[str, ...]:
    if not change.supported:
        return ()
    return tuple(target.turn_ref for target in targets if target.record.kind == 'goal'
        and target.record.status == 'active' and (
            change.name in target.record.terms
            or target.record.revision_of_record_id is not None and any(prior.supported and prior.name == change.name
                for prior in named_goal_changes(target.record.evidence_quote))))
