"""One extra relevance condition, replacing only S118's repair paragraph."""
from dataclasses import replace
from hashlib import sha256
import json

from dynamic_subject_agent.first_life_self_choice_candidate import (
    preview_self_choice_candidate, REPAIR_AFTER, SystemParagraphChange,
)
from dynamic_subject_agent.frozen_attempt import canonical_json


CANDIDATE_VERSION = "first-life-current-topic-preview-s120-1"
TOPIC_REPAIR = (
    "先判断当前问题要推进什么交流。只有理解或回答当前问题确实依赖那段旧话时，才对照当前依据和exchange处理其中的错误；"
    "无关旧错仍约束本轮不沿用错误，但不插入当前回复。"
    "相关的质疑先核对最近原话是否真的有错，有冲突才修正，已经说清则澄清当前疑点。"
    "不要为认领错误或使两种说法成立而补造原因、中间经过或新的自我事实；无法确定的经过保持未知。"
)


def preview_current_topic_candidate(task):
    original=preview_self_choice_candidate(task)
    body=json.loads(original.wire)
    paragraphs=body["messages"][0]["content"].split("\n")
    if paragraphs[4]!=REPAIR_AFTER or paragraphs.count(REPAIR_AFTER)!=1:
        raise ValueError("exact S118 repair paragraph required")
    paragraphs[4]=TOPIC_REPAIR
    body["messages"][0]["content"]="\n".join(paragraphs)
    wire=canonical_json(body).encode()
    if len(wire)>65536:raise ValueError("topic preview exceeds existing byte bound")
    return replace(original,version=CANDIDATE_VERSION,baseline_wire=original.wire,
        baseline_wire_sha256=original.candidate_wire_sha256,candidate_wire_sha256=sha256(wire).hexdigest(),wire=wire,
        changed_paragraphs=(SystemParagraphChange(5,REPAIR_AFTER,TOPIC_REPAIR),))
