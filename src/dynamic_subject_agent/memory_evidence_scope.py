"""Keep a Memory write inside its own literal current-message evidence."""
import re
from dataclasses import dataclass
from enum import Enum
from dynamic_subject_agent.current_message import direct_statement_spans
from dynamic_subject_agent.participant_goals import DIRECT_OPERATION_PATTERNS, DIRECT_TRANSITION_COMMANDS
from dynamic_subject_agent.natural_goals import named_goal_changes


class MemoryEvidenceStatus(str, Enum):
    ELIGIBLE = 'eligible'
    PARTICIPANT_ONLY = 'participant-only'
    AMBIGUOUS = 'ambiguous'


@dataclass(frozen=True)
class MemoryEvidenceScope:
    status: MemoryEvidenceStatus
    evidence: str


def scope_memory_evidence(message: str, evidence: str, *, goal_records=()) -> MemoryEvidenceScope:
    """Reduce only validated verbatim evidence; never join disjoint remnants."""
    operations = tuple(statement for statement in direct_statement_spans(message)
        if not any(char in statement.text for char in '，,') and (
            any(re.fullmatch(pattern, statement.text) for pattern, _, _ in DIRECT_OPERATION_PATTERNS)
            or any(statement.text in phrases for _, _, phrases in DIRECT_TRANSITION_COMMANDS)))
    from dynamic_subject_agent.current_goal_commands import applicable_goal_commands
    natural = (*named_goal_changes(message), *applicable_goal_commands(message, goal_records))
    if named_goal_changes(evidence) and not natural:
        return MemoryEvidenceScope(MemoryEvidenceStatus.AMBIGUOUS, '')
    if natural:
        if not evidence or message.count(evidence) != 1:
            return MemoryEvidenceScope(MemoryEvidenceStatus.AMBIGUOUS, '')
        offset = message.index(evidence)
        if any(not change.supported and change.start < offset + len(evidence) and change.end > offset for change in natural):
            return MemoryEvidenceScope(MemoryEvidenceStatus.AMBIGUOUS, '')
        operations = tuple(sorted((*operations, *natural), key=lambda item: item.start))
    if not operations:
        return MemoryEvidenceScope(MemoryEvidenceStatus.ELIGIBLE, evidence)
    if not evidence or message.count(evidence) != 1:
        return MemoryEvidenceScope(MemoryEvidenceStatus.AMBIGUOUS, '')
    start = message.index(evidence)
    end = start + len(evidence)
    remaining = []
    cursor = start
    for operation in operations:
        if operation.end <= cursor or operation.start >= end:
            continue
        fragment = message[cursor:min(end, operation.start)].strip()
        if fragment:
            remaining.append(fragment)
        cursor = min(end, operation.end)
    fragment = message[cursor:end].strip()
    if fragment:
        remaining.append(fragment)
    if not remaining:
        return MemoryEvidenceScope(MemoryEvidenceStatus.PARTICIPANT_ONLY, '')
    if len(remaining) != 1:
        return MemoryEvidenceScope(MemoryEvidenceStatus.AMBIGUOUS, '')
    if remaining[0] != evidence.strip() and re.match(
        r'^(?:但|不过|然而|前提|否则|除非|只(?:在|有)|仅在|如果|假如|若|要是|届时|到时|这(?:个|项)|上述|它|其)', remaining[0]
    ):
        # A remaining qualification or reference is not an independent fact.
        return MemoryEvidenceScope(MemoryEvidenceStatus.AMBIGUOUS, '')
    return MemoryEvidenceScope(MemoryEvidenceStatus.ELIGIBLE, remaining[0])
