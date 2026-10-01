"""S118 offline hypothesis: distinguish self facts from current choices.

Only two system paragraphs of the S117 scoped whole-reply request are replaced.
Materials, parameters, output contract and existing builders remain unchanged.
The preview is not a ModelTask; no sender or runtime route is registered here.
"""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json

from dynamic_subject_agent.first_life_development_trial import scoped_reply_wire
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind


CANDIDATE_VERSION = "first-life-self-choice-preview-s118-1"
EVIDENCE_BEFORE = (
    "evidence只支持所记录的文字构图及明确列出的变化；它不能证明看见了图片、真实场所细节、成图、外部行动或这些情况的否定。"
    "当前意见和新建议可以表达为此刻的取舍，不能因此变成已经发生的行动或更新保存方案。"
)
EVIDENCE_AFTER = (
    "关于自己是谁、长期习惯以及过去发生或未发生的事，只在background或evidence有相同成立范围的明确依据时作为自我事实表达。"
    "evidence记录的是文字构图及明确变化，其中明示的完成或未完成也只约束所记录的分支产物，不扩大为外部行动或经历的肯定与否定。"
    "本轮可以形成自己的意见、理由、取舍或设想，将它们表达为此刻的看法或条件下的可能，不变成已有习惯、过去行动或保存方案的新属性；范围外未确定的内容保持未知。"
)
REPAIR_BEFORE = (
    "自己旧话与可核依据冲突时，修复自己的说法：承认需要修正之处，说明相关依据，接着处理当前交流。"
    "不要为了让两种说法都成立而填补材料没有记录的中间经过；无法确定的经过保持未知，不补造原因。"
)
REPAIR_AFTER = (
    "用户质疑与自己旧话都需要对照当前依据和exchange，先判断哪一句确实需要修正；质疑不自动证明最近的回复有错。"
    "有冲突时修正自己的说法并说明相关依据，已经说清的内容则直接澄清当前疑点、继续交流。"
    "不为了认领错误或使两种说法都成立而补造原因、中间经过或新的自我事实；无法确定的经过保持未知。"
)


@dataclass(frozen=True)
class SystemParagraphChange:
    paragraph_number: int
    before: str
    after: str


@dataclass(frozen=True)
class SelfChoiceCandidatePreview:
    version: str
    task_kind: str
    source_payload_sha256: str
    baseline_wire_sha256: str
    candidate_wire_sha256: str
    changed_paragraphs: tuple[SystemParagraphChange, ...]
    baseline_wire: bytes
    wire: bytes
    remote_use_authorized: bool = False
    semantic_quality: str = "not-evaluated-no-model-call"


def preview_self_choice_candidate(task):
    """Return review-only bytes for an existing typed A task, without mutation."""
    if (type(task) is not ModelTask
            or task.kind is not ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY):
        raise ValueError("existing typed whole reply task required")
    baseline = scoped_reply_wire(task)  # Existing builder validates the bounded DTO.
    body = json.loads(baseline)
    paragraphs = body["messages"][0]["content"].split("\n")
    changes = (
        SystemParagraphChange(3, EVIDENCE_BEFORE, EVIDENCE_AFTER),
        SystemParagraphChange(5, REPAIR_BEFORE, REPAIR_AFTER),
    )
    for change in changes:
        position = change.paragraph_number - 1
        if (paragraphs[position] != change.before
                or paragraphs.count(change.before) != 1):
            raise ValueError("exact S117 system paragraphs required")
        paragraphs[position] = change.after
    body["messages"][0]["content"] = "\n".join(paragraphs)
    wire = canonical_json(body).encode()
    if len(wire) > 65536:
        raise ValueError("self choice preview exceeds the existing byte bound")
    return SelfChoiceCandidatePreview(
        CANDIDATE_VERSION, task.kind.value,
        sha256(canonical_json(asdict(task.payload)).encode()).hexdigest(),
        sha256(baseline).hexdigest(), sha256(wire).hexdigest(), changes, baseline, wire,
    )
