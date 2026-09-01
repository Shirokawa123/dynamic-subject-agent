"""Sealed project-original knowledge entries and deterministic retrieval.

Entries are code fixtures at the same trust level as the version-controlled
lantern-zine fixture profile; true snapshot sealing upgrades together with the
later private-source slice (see docs/slices/slice-02-knowledge-port.md).
Retrieval is pure Python with no model participation. This module is
deliberately outside the domains package so Domain modules can share the
entry type without cross-domain imports.
"""

from __future__ import annotations

from dataclasses import dataclass

KNOWLEDGE_CANDIDATE_LIMIT = 6
KNOWLEDGE_MINIMUM_RELEVANCE_SCORE = 2


@dataclass(frozen=True)
class KnowledgeEntry:
    entry_id: str
    title: str
    content: str
    source_ref: str
    evidence_quote: str | None = None


SEALED_KNOWLEDGE_SOURCE_REF = "project-original:lantern-zine-fixture-v1"

SEALED_KNOWLEDGE_ENTRIES: tuple[KnowledgeEntry, ...] = (
    KnowledgeEntry(
        entry_id="a1f4c2d8-0001-4a61-9e1f-3b5c7d9e0a01",
        title="Lantern Zine 印刷截单时间",
        content=(
            "Lantern Zine 合作的印刷厂每周五 17:00 截单，错过截单则顺延到"
            "下一个周五；加急插单需要提前两个工作日确认。"
        ),
        source_ref=SEALED_KNOWLEDGE_SOURCE_REF,
    ),
    KnowledgeEntry(
        entry_id="a1f4c2d8-0002-4a61-9e1f-3b5c7d9e0a02",
        title="创刊号规格",
        content=(
            "创刊号目标 32 页，A4 骑马钉装订，封面用 250g 牛皮纸，"
            "内页 120g 道林纸；夜景灯笼主题插画至少占 12 页。"
        ),
        source_ref=SEALED_KNOWLEDGE_SOURCE_REF,
    ),
    KnowledgeEntry(
        entry_id="a1f4c2d8-0003-4a61-9e1f-3b5c7d9e0a03",
        title="试印样张流程",
        content=(
            "正式付印前必须试印一张样张并双方确认配色；样张保存在"
            " Rowan 的工作室，确认后才能排入周五截单批次。"
        ),
        source_ref=SEALED_KNOWLEDGE_SOURCE_REF,
    ),
    KnowledgeEntry(
        entry_id="a1f4c2d8-0004-4a61-9e1f-3b5c7d9e0a04",
        title="社区发行方式",
        content=(
            "Lantern Zine 只在社区市集和独立书店寄售，不做线上邮购；"
            "首印 200 册，售罄后按需评估加印。"
        ),
        source_ref=SEALED_KNOWLEDGE_SOURCE_REF,
    ),
)

_ENTRIES_BY_ID = {entry.entry_id: entry for entry in SEALED_KNOWLEDGE_ENTRIES}


def knowledge_entry_by_id(entry_id: str) -> KnowledgeEntry | None:
    return _ENTRIES_BY_ID.get(entry_id)


def _char_bigrams(text: str) -> set[str]:
    stripped = "".join(text.split())
    return {stripped[index : index + 2] for index in range(len(stripped) - 1)}


def select_knowledge_candidates(
    message: str,
    entries: tuple[KnowledgeEntry, ...] = SEALED_KNOWLEDGE_ENTRIES,
    *,
    limit: int = KNOWLEDGE_CANDIDATE_LIMIT,
) -> tuple[KnowledgeEntry, ...]:
    """Deterministically rank entries by character-bigram overlap with the message.

    Title matches count double; ties break by entry_id so the selection is
    stable for identical inputs.
    """

    if limit <= 0 or not entries or not message.strip():
        return ()
    message_grams = _char_bigrams(message)
    if not message_grams:
        return ()
    scored = []
    for entry in entries:
        title_overlap = len(message_grams & _char_bigrams(entry.title))
        content_overlap = len(message_grams & _char_bigrams(entry.content))
        score = title_overlap * 2 + content_overlap
        if score >= KNOWLEDGE_MINIMUM_RELEVANCE_SCORE:
            scored.append((score, entry.entry_id, entry))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return tuple(entry for _, _, entry in scored[:limit])


__all__ = [
    "KNOWLEDGE_CANDIDATE_LIMIT",
    "KNOWLEDGE_MINIMUM_RELEVANCE_SCORE",
    "KnowledgeEntry",
    "SEALED_KNOWLEDGE_ENTRIES",
    "SEALED_KNOWLEDGE_SOURCE_REF",
    "knowledge_entry_by_id",
    "select_knowledge_candidates",
]
