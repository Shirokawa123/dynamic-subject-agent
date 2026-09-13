"""Literal goal-change commands and their independent unchanged context."""
from dataclasses import dataclass
import re
from dynamic_subject_agent.current_message import direct_statement_spans

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
    for statement in direct_statement_spans(message):
        parts = re.split(r'[，,]', statement.text, maxsplit=1)
        match = re.fullmatch(r'([^，,。！？!?；;：:]{2,60}?)(?:这个|这项)目标我(?:想|希望)?(?:改成|改为|换成)([^，,。！？!?；;：:]{1,500})', parts[0])
        if match is None:
            continue
        name = match[1].removeprefix('我的').strip()
        supported = bool(name) and not any(word in name for word in ('朋友的', '他的', '她的', '你的', '我们的', '如果', '假如'))
        if len(parts) > 1:
            supported = supported and re.fullmatch(r'[^，,。！？!?；;]{0,100}(?:安排|计划)(?:保持)?不变', parts[1].strip()) is not None
        changes.append(NamedGoalChange(name, match[2].strip(), parts[0], statement.start, statement.end, supported))
    return tuple(changes)

def matching_goal_refs(change: NamedGoalChange, targets) -> tuple[str, ...]:
    if not change.supported:
        return ()
    return tuple(target.turn_ref for target in targets if target.record.kind == 'goal'
        and target.record.status == 'active' and (
            change.name in target.record.terms
            or any(prior.supported and prior.name == change.name
                for prior in named_goal_changes(target.record.evidence_quote))))
