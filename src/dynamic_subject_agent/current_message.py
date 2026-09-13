"""Literal current statement boundaries; never manufacture admitted evidence."""
import re
from dynamic_subject_agent.recent_dialogue import expression_request_text


def mask_quoted_text(message: str) -> str:
    """Mask whole nested/unclosed quote spans before looking for boundaries."""
    pairs = {'“': '”', '「': '」', '‘': '’', '"': '"'}
    expected = []
    output = []
    for index, char in enumerate(message):
        if expected and char == expected[-1]:
            expected.pop()
            # A finished quoted sentence may separate a following real request.
            output.append('。' if not expected and index and message[index - 1] in '。！？!?' else ' ')
        elif char in pairs:
            expected.append(pairs[char])
            output.append(' ')
        elif expected:
            output.append(' ')
        elif char in '”」’':
            output.extend(' ' * (len(message) - index))
            break
        else:
            output.append(char)
    return ''.join(output)


def direct_statement_clauses(message: str) -> tuple[str, ...]:
    """Only complete unquoted statements, not comma-lifted conditional tails."""
    clauses = []
    masked = mask_quoted_text(message)
    for match in re.finditer(r'[^。！？!?；;\n]+[。！？!?；;\n]?', masked):
        if message[match.start():match.end()] != match[0]:
            continue
        raw = match[0].strip()
        if raw.endswith(('?', '？')) or any(char in raw for char in '“”「」‘’"'):
            continue
        clause = raw.rstrip('。！？!?；;\n').strip()
        if re.match(r'^(?:如果|假如|假设|要是|(?:朋友|他|她|你)(?:说|问)|我(?:说|问)(?:过|了)?[：:])', clause):
            continue
        if clause and expression_request_text(clause).strip() == clause:
            clauses.append(clause)
    return tuple(clauses)
