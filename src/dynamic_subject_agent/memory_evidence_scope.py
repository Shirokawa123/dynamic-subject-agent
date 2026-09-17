"""Keep a Memory write inside its own literal current-message evidence."""
import re
from dataclasses import dataclass
from enum import Enum
from dynamic_subject_agent.current_message import direct_statement_spans, mask_quoted_text
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


def _context_bounds(message: str, span: re.Match) -> tuple[int, int]:
    source = message[span.start():span.end()]
    context = source.strip().removeprefix('请记住：').lstrip()
    left = span.start() + source.index(context)
    right = span.start() + len(source.rstrip('。！？!?；;\n \t'))
    return left, right


def _preserves_source_context(message: str, evidence: str) -> bool:
    """Verbatim text is insufficient when an excerpt drops its source scope.

    Presence is checked by Domain; confirmed preferences use their separately
    verified source message, so evidence absent from this short answer is not
    reinterpreted here. Quoted excerpts preserve their containing source unit
    (apart from the explicit recording wrapper), or an existing exact
    preference-replacement parameter whose target is checked by Domain later.
    """
    if not evidence or evidence not in message:
        return True
    if evidence.strip() in {message.strip(), message.strip().removeprefix('请记住：')}:
        return True
    masked = mask_quoted_text(message)
    spans = tuple(re.finditer(r'[^。！？!?；;\n]+[。！？!?；;\n]?', masked))
    # The ordinary request parser inserts a sentence boundary at a quote close.
    # For attribution, keep following text such as "小夏说" in the same unit.
    quote_mask = ''.join(' ' if original in '”」’"' and char == '。' else char
        for original, char in zip(message, masked))
    quote_units = tuple(re.finditer(r'[^。！？!?；;\n]+[。！？!?；;\n]?', quote_mask))
    bound_prefix = r'^(?:如果|假如|假设|要是|除非|只有|只要|[^，,。！？!?；;：:\n]{1,24}(?:说|表示|提到|告诉我)(?:[：:,，]|(?=我|你|他|她)))'
    for occurrence in re.finditer(re.escape(evidence), message):
        start, end = occurrence.span()
        if masked[start:end] != message[start:end]:
            from dynamic_subject_agent.scoped_preferences import explicit_preference_replacement
            replacement = explicit_preference_replacement(message)
            prefix_space = len(message) - len(message.lstrip())
            if replacement is None or evidence != replacement[2] or start != prefix_space + replacement.start(2):
                for unit in quote_units:
                    if unit.end() <= start or unit.start() >= end:
                        continue
                    left, right = _context_bounds(message, unit)
                    if start > left or end < right:
                        return False
        for span in spans:
            if span.end() <= start or span.start() >= end:
                continue
            source = message[span.start():span.end()]
            context = source.strip().removeprefix('请记住：').lstrip()
            if re.match(bound_prefix, context):
                left, right = _context_bounds(message, span)
                if start > left or end < right:
                    return False
    return True


def scope_memory_evidence(message: str, evidence: str, *, goal_records=()) -> MemoryEvidenceScope:
    """Reduce only validated verbatim evidence; never join disjoint remnants."""
    if not _preserves_source_context(message, evidence):
        return MemoryEvidenceScope(MemoryEvidenceStatus.AMBIGUOUS, '')
    operations = tuple(statement for statement in direct_statement_spans(message)
        if not any(char in statement.text for char in '，,') and (
            any(re.fullmatch(pattern, statement.text) for pattern, _, _ in DIRECT_OPERATION_PATTERNS)
            or any(statement.text in phrases for _, _, phrases in DIRECT_TRANSITION_COMMANDS)))
    from dynamic_subject_agent.current_goal_commands import applicable_goal_commands
    current = applicable_goal_commands(message, goal_records)
    lifted = applicable_goal_commands(evidence, goal_records)
    if lifted:
        if not evidence or message.count(evidence) != 1:
            return MemoryEvidenceScope(MemoryEvidenceStatus.AMBIGUOUS, '')
        offset = message.index(evidence)
        if any(not any(command.evidence == fragment.evidence and command.start == offset + fragment.start
            for command in current) for fragment in lifted):
            return MemoryEvidenceScope(MemoryEvidenceStatus.AMBIGUOUS, '')
    natural = (*named_goal_changes(message), *current)
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
