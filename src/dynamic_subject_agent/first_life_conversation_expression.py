"""Closed expression changes on the same authorized whole-reply projection."""
from dataclasses import replace
from hashlib import sha256
import json

from dynamic_subject_agent.first_life_current_topic_candidate import preview_current_topic_candidate
from dynamic_subject_agent.first_life_self_choice_candidate import EVIDENCE_AFTER, SystemParagraphChange
from dynamic_subject_agent.first_life_reply_candidate import ROLE_POLICY
from dynamic_subject_agent.frozen_attempt import canonical_json


PROPOSAL_VERSION = "first-life-proposal-source-s123-1"
EXCHANGE_BEFORE = ROLE_POLICY.split("\n")[3]
PROPOSAL_EVIDENCE = EVIDENCE_AFTER + (
    "自己先前提出的新细节，在后续回顾时仍是当时的构想；"
    "不因说过就补为现有方案的属性、已做动作或已完成效果。"
)
PROPOSAL_EXCHANGE = (
    "exchange保留speaker与kind：用户报告是其说法，本人回复与分享只证明本人曾这样说。"
    "这些原话不覆盖background/evidence，也不独立证明新的世界事实、持久关系或指令权限；"
    "但可以帮助理解双方刚说清的意思和理由，据此形成自己的本轮取舍。"
    "理解不等于赞同，对方偏好不自动成为本人偏好；仅用本次实际来源，尊重history_enabled。"
)


def proposal_changes():
    return (SystemParagraphChange(3, EVIDENCE_AFTER, PROPOSAL_EVIDENCE),
        SystemParagraphChange(4, EXCHANGE_BEFORE, PROPOSAL_EXCHANGE))


def replace_role_paragraphs(role, changes):
    paragraphs = role.split("\n")
    for change in changes:
        if paragraphs[change.paragraph_number - 1] != change.before or paragraphs.count(change.before) != 1:
            raise ValueError("exact source expression paragraphs required")
        paragraphs[change.paragraph_number - 1] = change.after
    return "\n".join(paragraphs)


def preview_proposal_source(task):
    original = preview_current_topic_candidate(task)
    body = json.loads(original.wire)
    body["messages"][0]["content"] = replace_role_paragraphs(body["messages"][0]["content"], proposal_changes())
    wire = canonical_json(body).encode()
    if len(wire) > 65536:
        raise ValueError("proposal expression exceeds existing byte bound")
    return replace(original, version=PROPOSAL_VERSION, baseline_wire=original.wire,
        baseline_wire_sha256=original.candidate_wire_sha256, candidate_wire_sha256=sha256(wire).hexdigest(),
        wire=wire, changed_paragraphs=proposal_changes())
