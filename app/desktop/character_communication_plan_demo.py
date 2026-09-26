"""Local substitute demonstration, not a remote-model quality evaluation."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
from dynamic_subject_agent.local_product import open_character_communication_plan_lab
from dynamic_subject_agent.model_gateway import (
    ModelGateway, ModelResult, ModelTaskKind, ProviderAdapter, ProviderCapabilities, StructuredOutputMode,
)


class LocalSubstituteAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities("local-substitute", "fixed-demo", True, (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self, *, action="offer_topic", reply_text="这轮我想聊聊画画。你更在意线条还是配色？"):
        self.action, self.reply_text, self.calls = action, reply_text, []

    def invoke(self, task):
        self.calls.append(task)
        if task.kind is ModelTaskKind.CHARACTER_COMMUNICATION_PLAN:
            value = dict(action=self.action, fact_refs=[task.payload.self_knowledge[0].label] if task.payload.self_knowledge else [])
        elif task.kind is ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION:
            value = dict(reply_text=self.reply_text, language="zh")
        else:
            raise ValueError("unsupported local demonstration task")
        return ModelResult(task.kind, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--reviewed-digest", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--anchor", required=True)
    parser.add_argument("--message", default="随便聊点什么？")
    parser.add_argument("--context-mode", choices=("auto", "flat", "organized"), default="auto")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2] / ".artifacts/character-communication-plan-demo"
    scenarios = (
        ("本轮提话题", "offer_topic", "这轮我想聊聊画画。你更在意线条还是配色？"),
        ("规划提出新历史活动：不许可", "recent_activity", "这句不应生成。"),
        ("表达器故意越界：仍待审核", "offer_topic", "最近我一直在想线条和配色的取舍。"),
    )
    print(json.dumps(dict(demonstration="本地替身演示", limitation="固定替身台词只验证流程，不证明真实模型效果或自由台词事实成立。"), ensure_ascii=False))
    try:
        for name, action, text in scenarios:
            planner = LocalSubstituteAdapter(action=action)
            expresser = LocalSubstituteAdapter(reply_text=text)
            with open_character_communication_plan_lab(root, draft_path=args.draft.resolve(), source_root=args.source_root.resolve(),
                reviewed_digest=args.reviewed_digest, plan_gateway=ModelGateway(planner), expression_gateway=ModelGateway(expresser)) as product:
                request = CharacterChatContextRequest(args.subject, args.anchor, args.message, args.context_mode)
                preview = product.application.preview_character_reply(request)
                result = product.application.propose_character_reply(request)
                print(json.dumps(dict(scenario=name, proposed_action=action,
                    preview_status=preview.status, request_digest=preview.request_digest,
                    plan_calls=len(planner.calls), expression_calls=len(expresser.calls), result=asdict(result)), ensure_ascii=False))
    except (OSError, ValueError, TypeError):
        parser.error("本地演示资料或装配不可用；没有启用远程调用")


if __name__ == "__main__":
    main()
