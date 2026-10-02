"""S128's bounded local retrieval candidate; no model, wire, or new knowledge."""
from dataclasses import replace
import unicodedata

from dynamic_subject_agent.character_chat_context import prepare_context, knowledge_chars, MAX_KNOWLEDGE_CHARS, MAX_RELATED_UNITS
from dynamic_subject_agent.reviewed_character_chat import CharacterDialogueBasis
from dynamic_subject_agent.frozen_attempt import canonical_json
from hashlib import sha256

SELECTOR_VERSION = "original-whole-user-followup-selection-s128-2"
FOLLOWUP_FORMS = ("为什么", "为什么呢", "当时呢", "当时是什么样", "那当时呢", "那后来呢", "后来呢", "你说的那个人呢")
TOPIC_BREAKS = ("换个话题", "不聊这个")
SELECTOR_CONTRACT = dict(version=SELECTOR_VERSION, current_first=True, fallback_only_when_current_related_empty=True,
    followup_forms=list(FOLLOWUP_FORMS), topic_breaks=list(TOPIC_BREAKS), history_enabled_required=True,
    max_complete_turns=2, source="same-identity-verified-canonical-user-text-only",
    choice="topic-break-is-a-boundary-before-selection; otherwise-nearest-user-turn-with-sealed-related-selection",
    no_assistant_fact_source=True, no_current_message_rewrite=True, max_related_units=6, max_knowledge_chars=20000)


def selector_digest():
    return sha256(canonical_json(SELECTOR_CONTRACT).encode()).hexdigest()


def _short_question(message):
    start, end = 0, len(message)
    while start < end and (message[start].isspace() or unicodedata.category(message[start]).startswith("P")):
        start += 1
    while end > start and (message[end - 1].isspace() or unicodedata.category(message[end - 1]).startswith("P")):
        end -= 1
    return message[start:end]


def select_followup_context(model, message, dialogue, enabled):
    """Use a previous user question only as a query into the same sealed asset."""
    if (type(dialogue) is not CharacterDialogueBasis or dialogue.status != "available" or type(enabled) is not bool
        or len(dialogue.recent_dialogue) > 2 or not enabled and dialogue.recent_dialogue):
        raise ValueError("bounded verified followup basis required")
    current = prepare_context(model, message)
    if current.status != "previewed":
        return current, "current-context-unavailable", None
    core_dimension = "core" if model.chat_organization is not None else "identity"
    core = tuple(row for row in current.self_knowledge if row.dimension == core_dimension)
    related = tuple(row for row in current.self_knowledge if row not in core)
    if related:
        return current, "current-related-preferred", None
    if not enabled or not dialogue.recent_dialogue:
        return current, "history-not-used", None
    if _short_question(message) not in FOLLOWUP_FORMS:
        return current, "not-a-bounded-followup", None
    for offset, turn in enumerate(reversed(dialogue.recent_dialogue), 1):
        # The same sentence can negate an old topic using its reviewed cues.
        # A declared boundary wins before lexical selection of that sentence;
        # this limited candidate does not attempt to split out a new topic.
        if any(marker in turn.user_text for marker in TOPIC_BREAKS):
            return current, "history-topic-boundary", offset
        previous = prepare_context(model, turn.user_text)
        if previous.status != "previewed":
            raise ValueError("previous sealed selection unavailable")
        previous_related = tuple(row for row in previous.self_knowledge if row.dimension != core_dimension)
        if previous_related:
            knowledge = (*core, *previous_related)
            if len(previous_related) > MAX_RELATED_UNITS or knowledge_chars(knowledge) > MAX_KNOWLEDGE_CHARS:
                raise ValueError("bounded followup material required")
            return replace(current, self_knowledge=knowledge, selection=previous.selection), "recovered-user-topic", offset
    return current, "no-sealed-user-topic", None
