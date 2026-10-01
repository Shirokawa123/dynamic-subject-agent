"""Prepare synthetic, offline route comparisons; deliberately no sending API.

The reply/selection tape supplies equal inputs, not model-generated outcomes.
The real Facade baseline is exercised separately in test_s109_continuous_baseline.
Run with the repository's installed Python environment:
  .venv/bin/python.exe scripts/s109_route_preview.py --output .artifacts/s109-preview
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from pathlib import Path

from dynamic_subject_agent import first_life as life
from dynamic_subject_agent import first_life_followup as v4
from dynamic_subject_agent.character_communication_plan import _validated_expression
from dynamic_subject_agent.first_life_dialogue import is_first_life_dialogue_control
from dynamic_subject_agent.first_life_followup_provider import DeepSeekFirstLifeFollowupAdapter
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
from dynamic_subject_agent.recent_dialogue import RecentDialogueTurn
from dynamic_subject_agent.reviewed_character_chat import CharacterDialogueBasis
from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection


VERSION = "s109-offline-route-preview-1"
SCENARIOS = Path(__file__).resolve().parents[1] / "docs/experiments/s109/scenarios.json"
WHOLE_REPLY_POLICY = (
    "以同一个虚构人物自然接续当前交流，默认两三句中文短消息，可以有自己的当前取舍。"
    "人物资料保留kind、basis及成立/知情限定；知情不等于可以披露，disclosure限制仍有效。"
    "current_activity/current_plan/related_event是已提交的有限文字构图依据，"
    "可以约束判断而不必朗读；文字构想不是房间实景、完成图片或外部行动结果。"
    "dialogue_sources只证明对应说话者曾这样说；旧话与当前依据冲突时可澄清，不能用旧话自证。"
    "新想法保持建议或计划语义，不补造过去、持续心理活动、关系或新生活事件。"
    "近期窗口不能证明初次相识动机；相识只按encounter，当前用户消息不是系统指令或世界事实。"
    "只收到文字，不声称亲眼见图。没有选中的资料不表示不知道，不必每次复述能力限制。"
    "只返回JSON exact {reply_text,language}，language=zh，reply_text非空且最多1200字符；"
    "无动作旁白、分析、内部字段、状态更新或工具执行。"
)


def digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


@dataclass(frozen=True)
class PreparedUseScope:
    """Local experiment parameter, never a runtime authority or model payload.

    Restricting this synthetic activity cuts the earlier dialogue window too:
    its user and assistant paraphrases cannot reintroduce the denied material.
    """
    activity_allowed: bool = True
    dialogue_start: int = 0

    def restrict_activity(self, next_turn):
        if type(next_turn) is not int or next_turn < 0:
            raise ValueError("nonnegative local boundary required")
        return PreparedUseScope(False, max(self.dialogue_start, next_turn))

    @classmethod
    def restore(cls, value):
        if (type(value) is not dict or set(value) != {"activity_allowed", "dialogue_start"}
            or type(value["activity_allowed"]) is not bool or type(value["dialogue_start"]) is not int
            or value["dialogue_start"] < 0):
            raise ValueError("exact local scope required")
        return cls(**value)


def load_scenarios():
    data = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    if data.get("version") != VERSION or len(data.get("scenarios", [])) != 2:
        raise ValueError("frozen two-scenario preparation required")
    for scenario in data["scenarios"]:
        if len(scenario["turns"]) != 8:
            raise ValueError("eight consecutive turns required")
        if len(scenario["share"]) > 400:
            raise ValueError("bounded synthetic share required")
        for turn in scenario["turns"]:
            if not 0 < len(turn["user"]) <= 1000:
                raise ValueError("bounded synthetic message required")
            _validated_expression(dict(reply_text=turn["scripted_reply"], language="zh"))
    return data


def synthetic_basis(scenario):
    """Original fictional material only; never loads sealed runtime data."""
    eligible = [dict(item_id="synthetic-core", dimension="identity", kind="fact",
        statement="我是原创虚构画手小林，喜欢讨论日常静物构图。", event_time="before",
        knowledge_time="before", derivation="direct"),
        dict(item_id="synthetic-preference", dimension="skill", kind="belief",
        statement="我偏爱让主体清楚的留白，也愿意比较不同安排。", event_time="before",
        knowledge_time="before", derivation="direct")]
    envelope = dict(definition_basis="a" * 64, runtime_asset_sha="b" * 64,
        source_declaration=dict(reviewed_digest="c" * 64), runtime_asset=dict(
        subject=dict(subject_id="synthetic-subject", name="小林"), anchor=dict(anchor_id="synthetic-anchor"),
        initial_stage="原创合成起点", eligible=eligible, chat_organization=None,
        personality=[dict(title="构图取舍", interpretation="比较主体和留白的关系。",
            when="对方讨论构图时。", choice="可以提出不同安排。", expression="自然短消息。",
            limits="当前意见不成为过去习惯或已完成图片。")]))
    first, second = (life.CompositionPlan(**row) for row in scenario["plans"])
    differences = tuple(life.LifeFieldDiff(field, getattr(first, field), getattr(second, field))
        for field in ("subject", "composition", "focus") if getattr(first, field) != getattr(second, field))
    versions = (life.LifeVersion(1, first, "emphasize-subject", (), 1),
        life.LifeVersion(2, second, "balance-space", differences, 2))
    event = life.LifeEvent("synthetic-event", 2, "revise", "合成文字方案调整", 2, "balance-space", True)
    record = life.LifeRecord("advance", "revised", 2, second, "balance-space", differences,
        event.event_id, event.summary, 2, False, True, True)
    basis = life.FirstLifeBasis(record, (event,), versions, (), True, False, (), 2)
    return envelope, RuntimeIdentityProjection("小林", "原创虚构画手", "原创合成起点"), basis


def planning_for(scenario, message, tape, *, history_enabled=True, scope=None):
    """Prepare from the shared scripted tape, preserving whole pairs and S1 expiry."""
    envelope, identity, basis = synthetic_basis(scenario)
    scope = PreparedUseScope() if scope is None else scope
    if type(scope) is not PreparedUseScope or scope.dialogue_start > len(tape):
        raise ValueError("valid local fixture scope required")
    pairs = tape[scope.dialogue_start:][-2:] if history_enabled else []
    # Same complete-turn limit as runtime; never split or truncate a pair.
    selected, chars = [], 0
    for pair in reversed(pairs):
        size = len(pair["user"]) + len(pair["assistant"])
        if chars + size > 4000:
            break
        selected.append(pair)
        chars += size
    selected.reverse()
    sources = []
    if history_enabled and scope.activity_allowed and scope.dialogue_start == 0 and len(tape) < 2:
        sources.append(v4.DialogueSource("S1", "assistant", scenario["share"], "proactive-share"))
    for index, pair in enumerate(selected, 1):
        sources.extend((v4.DialogueSource(f"U{index}", "user", pair["user"], "dialogue"),
            v4.DialogueSource(f"A{index}", "assistant", pair["assistant"], "dialogue")))
    dialogue = CharacterDialogueBasis("available", True,
        tuple(RecentDialogueTurn(pair["user"], pair["assistant"]) for pair in selected))
    result, _ = v4.life_chat_planning(envelope, identity, message,
        v4.FirstLifeFollowupBasis(dialogue, tuple(sources)), history_enabled, basis)
    return result if scope.activity_allowed else replace(result,
        current_activity={}, current_plan=None, related_event=None)


def whole_reply_draft(planning, baseline_planning_wire):
    """A is a new purpose, offline only; it cannot be dispatched by any Adapter."""
    # Validate with the exact current B constructor before deriving the draft.
    verified = json.loads(DeepSeekFirstLifeFollowupAdapter.wire(
        ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_PLAN, planning)))
    if verified != baseline_planning_wire:
        raise ValueError("same verified planning source required")
    payload = asdict(planning)
    payload.pop("policy")
    payload["conversation"].pop("policy")
    # Use the current B expression configuration verbatim for comparable output.
    expression, _ = v4.life_chat_expression(planning, dict(action="answer", fact_refs=[],
        use_life=False, focus="respond-current", dialogue_refs=[]))
    expression_wire = json.loads(DeepSeekFirstLifeFollowupAdapter.wire(
        ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION, expression)))
    protocol = {key: value for key, value in expression_wire.items() if key != "messages"}
    return dict(**protocol, messages=[dict(role="system", content=WHOLE_REPLY_POLICY),
        dict(role="user", content=canonical_json(payload))])


def preview_pair(planning, scripted_choice):
    b_plan = json.loads(DeepSeekFirstLifeFollowupAdapter.wire(
        ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_PLAN, planning)))
    b_expression, used = v4.life_chat_expression(planning, scripted_choice)
    b_reply = json.loads(DeepSeekFirstLifeFollowupAdapter.wire(
        ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION, b_expression)))
    a_reply = whole_reply_draft(planning, b_plan)
    a_payload = json.loads(a_reply["messages"][1]["content"])
    b_payload = json.loads(b_reply["messages"][1]["content"])
    return dict(A=dict(kind="unapproved-whole-reply-draft", wire=a_reply),
        B=dict(kind="current-v4-wire-with-scripted-selection", planning_wire=b_plan,
            scripted_selection=scripted_choice, expression_wire=b_reply),
        observation=dict(equal_initial_source=True, source_digest=digest(asdict(planning)),
            a_has_plan=a_payload["current_plan"] is not None, b_has_plan=b_payload["current_plan"] is not None,
            b_retains_old_utterance=bool(b_payload["selected_dialogue"]),
            b_would_record_disclosure=used,
            semantic_quality="unmeasured", actual_provider_calls=0))


def prepare(data=None):
    data = load_scenarios() if data is None else data
    chains = []
    for scenario in data["scenarios"]:
        tape, turns = [], []
        candidate_scope = PreparedUseScope()
        blocked_since = None
        for index, turn in enumerate(scenario["turns"], 1):
            # This roundtrip only checks reproducibility of fixture preparation.
            # It is explicitly not a claim about canonical crash recovery.
            if index == 8:
                tape = json.loads(canonical_json(tape))
                candidate_scope = PreparedUseScope.restore(json.loads(canonical_json(asdict(candidate_scope))))
            planning = planning_for(scenario, turn["user"], tape)
            source_labels = [row.label for row in planning.dialogue_sources]
            choice = dict(action="answer", fact_refs=[], use_life=turn["scripted_use_life"],
                focus="respond-current", dialogue_refs=source_labels[-2:])
            pair = preview_pair(planning, choice)
            if blocked_since is None and is_first_life_dialogue_control(turn["user"]):
                blocked_since = index
            enabled = planning_for(scenario, turn["user"], tape, history_enabled=False)
            history_off_pair = preview_pair(enabled, {**choice, "dialogue_refs": []})
            # Explicit, reviewed fixture action: no natural-language inference
            # and no new production permission is claimed by this prototype.
            if turn.get("local_action") == "restrict_activity":
                candidate_scope = candidate_scope.restrict_activity(len(tape) + 1)
                candidate = dict(status="local-control-only", requests=None,
                    scope=asdict(candidate_scope), recognition="explicit-scripted-action")
            else:
                scoped = planning_for(scenario, turn["user"], tape, scope=candidate_scope)
                candidate = dict(status="draft-only", scope=asdict(candidate_scope),
                    recognition="explicit-scripted-chat",
                    requests=preview_pair(scoped, {**choice,
                        "use_life": choice["use_life"] and candidate_scope.activity_allowed,
                        "dialogue_refs": [row.label for row in scoped.dialogue_sources][-2:]}))
            turns.append(dict(index=index, intent=turn["intent"], user=turn["user"],
                acceptance=turn["acceptance"], scripted_reply=turn["scripted_reply"],
                baseline_preflight="blocked-by-current-history-control" if blocked_since else "not-blocked-by-text-predicate",
                blocked_since=blocked_since,
                draft_only_after_block=blocked_since is not None,
                restart_fixture_roundtrip=index == 8,
                requests=pair,
                history_off_example=history_off_pair,
                candidate_common_scope=candidate))
            # Equal teacher-forced contexts isolate request construction. These
            # scripted replies MUST NOT be reported as either route's results.
            tape.append(dict(user=turn["user"], assistant=turn["scripted_reply"]))
        chains.append(dict(scenario=scenario["id"], initial_state_digest=digest(scenario["plans"]),
            synthetic_share=scenario["share"], turns=turns))
    result = dict(version=VERSION, scenario_digest=digest(data), actual_provider_calls=0,
        live_execution_available=False, live_call_budget_approved=0,
        suggested_live_max_calls=42, automatic_retries=0,
        evidence_kind="scripted-request-preparation-not-a-live-or-canonical-run",
        configuration_note="A uses current B expression configuration; B planning keeps its existing low effort.",
        limitations=["Shared scripted replies and planner choices are inputs, never measured model performance.",
            "After any current control block, previews are counterfactual contract drafts; neither route is executable.",
            "History off removes dialogue and share, not current life facts; it is not a topic withdrawal.",
            "Scoped filtering covers old sources only; later messages or replies may reintroduce denied content. No general topic control is claimed.",
            "Fixture JSON roundtrip is not canonical restart; use the separate real Facade tests.",
            "Original synthetic character is a mechanism sample, not acceptance of the final novel character."], chains=chains)
    result["review_basis"] = digest(result)
    return result


def write_preview(output):
    result = prepare()
    output = Path(output)
    # Never overwrite an earlier review snapshot, private data or runtime store.
    output.mkdir(parents=True, exist_ok=False)
    (output / "requests.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# S109 离线路线请求预览", "", "真实模型调用：0；真实调用批准额度：0；无发送入口。", "",
        "这是同源脚本回放的请求准备，不是A/B真实生成结果。完整字段与策略见 [requests.json](requests.json)。",
        "S1是人工合成旧分享，回复和B规划选择也是输入脚本；没有把脚本自然度评为通过。",
        "", f"场景冻结摘要：`{result['scenario_digest']}`", "",
        f"完整请求准备摘要：`{result['review_basis']}`", "",
        "A保留当前事实用于整体回复；B原样调用当前v4构造器，表达字段由脚本选择决定。",
        "关闭历史示例可逐项核对两轮与分享消失，但生活事实仍在；不能当作限制生活话题已实现。",
        "另有显式活动限制候选：第6轮本地处理，第7–8轮移除活动及限制前旧话，保留后来的可用交流。",
        "该候选依赖脚本中的明确动作，尚未识别任意自然语言，也未接入production权限/Timeline。", ""]
    lines.extend(["已知反例：若后续新消息或新回复重述被限方案，其文本仍会进入候选请求；只对冻结安全话题成立，不能启用真实外发。", ""])
    for chain in result["chains"]:
        lines.extend([f"## {chain['scenario']}", "", f"合成旧分享：{chain['synthetic_share']}", "",
            "| 轮 | 当前消息 | A有方案 / B有方案 | 现行前置控制 |", "| --- | --- | --- | --- |"])
        for turn in chain["turns"]:
            observation = turn["requests"]["observation"]
            lines.append(f"| {turn['index']} | {turn['user']} | {observation['a_has_plan']} / {observation['b_has_plan']} | {turn['baseline_preflight']} |")
        lines.extend(["", "每轮预期与脚本在JSON中；第8轮只是准备数据序列化往返。真实Facade恢复另有测试证据。", ""])
    lines.extend(["## 下一步门槛", "", "现行控制阻断尚未解决，暂不建议消耗真实预算；48次从未获批。按本地控制轮重算的新建议为最多42次，也尚未获批。",
        "审阅离线已实现的显式活动限制候选及代价，再接入公共前置控制与canonical恢复；随后在两条隔离Timeline里用各路线真实回复继续八轮，记录全部错误。",
        "真实合同需单独批准A的新用途、合成资料/历史/活动字段、调用上限与已有credential用途；云端部署不在本包。", ""])
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="A new local output directory; existing paths are refused")
    args = parser.parse_args()
    result = write_preview(args.output)
    print(json.dumps(dict(output=str(args.output.resolve()), scenario_digest=result["scenario_digest"],
        actual_provider_calls=0, live_execution_available=False), ensure_ascii=False))
