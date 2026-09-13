"""Literal current statement boundaries; never manufacture admitted evidence."""
import re
from dynamic_subject_agent.recent_dialogue import expression_request_text


def direct_statement_clauses(message: str) -> tuple[str, ...]:
    """Only complete unquoted statements, not comma-lifted conditional tails."""
    clauses = []
    for match in re.finditer(r'[^。！？!?；;\n]+[。！？!?；;\n]?', message):
        raw = match[0].strip()
        if raw.endswith(('?', '？')) or any(char in raw for char in '“”「」‘’"'):
            continue
        clause = raw.rstrip('。！？!?；;\n').strip()
        if re.match(r'^(?:如果|假如|假设|要是|(?:朋友|他|她|你)(?:说|问)|我(?:说|问)(?:过|了)?[：:])', clause):
            continue
        if clause and expression_request_text(clause).strip() == clause:
            clauses.append(clause)
    return tuple(clauses)
