"""Ephemeral lexical candidate selection; canonical records are never changed."""

from __future__ import annotations

from contextlib import closing
import re
import sqlite3
from typing import TYPE_CHECKING
import unicodedata
from dynamic_subject_agent.memory_subject import requested_memory_subject, select_subject_memories

if TYPE_CHECKING:
    from dynamic_subject_agent.timeline import LivingMemoryRecord


_WORDS = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff]+|[a-z0-9]+')
_MAX_QUERY_TERMS = 128


class MemoryRetrievalUnavailable(Exception):
    """The local ranking facility could not produce a candidate window."""


def _terms(text: str) -> tuple[str, ...]:
    tokens = []
    for word in _WORDS.findall(unicodedata.normalize('NFKC', text).casefold()):
        if '\u3400' <= word[0] <= '\u9fff':
            # Overlapping Chinese bigrams require no dictionary or model.
            tokens.extend(word[i:i + 2] for i in range(len(word) - 1))
        else:
            tokens.append(word)
    return tuple(tokens)


def select_memory_candidates(
    history: tuple[LivingMemoryRecord, ...], query: object, *, limit: int = 20,
) -> tuple[LivingMemoryRecord, ...]:
    """Rank active records in the supplied newest-first, bounded local history.

    Under budget, preserve the existing projection exactly. On overflow, use
    SQLite's BM25 implementation, then fill unused slots in recency order.
    Ranking proves neither relevance nor truth; the existing provider selection
    and Domain adjudication still apply. FTS failures are distinct from no match.
    """
    active = tuple(memory for memory in history if memory.status == 'active')
    subject = requested_memory_subject(query)
    if subject is not None:
        active = select_subject_memories(active, subject)
    if len(active) <= limit or not isinstance(query, str):
        return active[:limit]
    documents = tuple(_terms(memory.content) for memory in active)
    vocabulary = set(token for document in documents for token in document)
    terms = set(_terms(query)) & vocabulary
    if not terms:
        return active[:limit]
    # Bound MATCH complexity; keep rarer terms first with deterministic ties.
    terms = sorted(terms, key=lambda term: (sum(term in doc for doc in documents), term))[:_MAX_QUERY_TERMS]
    try:
        with closing(sqlite3.connect(':memory:')) as connection:
            connection.execute('CREATE VIRTUAL TABLE candidates USING fts5(terms)')
            connection.executemany('INSERT INTO candidates(rowid, terms) VALUES (?, ?)',
                                   ((index + 1, ' '.join(doc)) for index, doc in enumerate(documents)))
            # Only tokenizer-produced words enter the FTS expression, all quoted;
            # user text is never SQL or MATCH syntax.
            matches = connection.execute(
                'SELECT rowid FROM candidates WHERE candidates MATCH ? '
                'ORDER BY bm25(candidates), rowid LIMIT ?',
                (' OR '.join('"' + term + '"' for term in terms), limit),
            ).fetchall()
    except sqlite3.Error:
        raise MemoryRetrievalUnavailable('memory-candidate-ranking-unavailable') from None
    selected = [row[0] - 1 for row in matches]
    selected_set = set(selected)
    selected.extend(index for index in range(len(active)) if index not in selected_set)
    return tuple(active[index] for index in selected[:limit])
