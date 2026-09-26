"""Preview exact local personality envelopes; optional fixed substitute, no remote."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
from dynamic_subject_agent.local_product import open_character_personality_lab
from dynamic_subject_agent.model_gateway import ModelGateway, ModelTaskKind, ModelResult, ProviderAdapter, ProviderCapabilities, StructuredOutputMode


class LocalSubstitute(ProviderAdapter):
    capabilities = ProviderCapabilities("local-substitute", "fixed-personality-demo", True, (StructuredOutputMode.JSON_OBJECT,))
    def invoke(self, task):
        if task.kind is ModelTaskKind.CHARACTER_COMMUNICATION_PLAN:
            value = dict(action="offer_topic", fact_refs=[])
        elif task.kind is ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION:
            value = dict(reply_text="这轮想聊聊画画的取舍。", language="zh")
        else: raise ValueError("unsupported substitute task")
        return ModelResult(task.kind, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--reviewed-digest", required=True)
    parser.add_argument("--sidecar", required=True, type=Path)
    parser.add_argument("--personality-digest", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--anchor", required=True)
    parser.add_argument("--message", default="聊聊画画？")
    parser.add_argument("--context-mode", choices=("auto", "flat", "organized"), default="auto")
    parser.add_argument("--demo", action="store_true", help="本地固定替身，仅验证流程，不是人物效果证据")
    parser.add_argument("--output", type=Path, help="显式写出预览JSON，拒绝覆盖已有文件")
    args = parser.parse_args()
    gateways = dict(plan_gateway=ModelGateway(LocalSubstitute()), expression_gateway=ModelGateway(LocalSubstitute())) if args.demo else {}
    root = Path(__file__).resolve().parents[2] / ".artifacts/character-personality-previews"
    with open_character_personality_lab(root, draft_path=args.draft.resolve(), source_root=args.source_root.resolve(), reviewed_digest=args.reviewed_digest,
        sidecar_path=args.sidecar.resolve(), personality_digest=args.personality_digest, **gateways) as product:
        request = CharacterChatContextRequest(args.subject, args.anchor, args.message, args.context_mode)
        payload = dict(mode="local-substitute-demo" if args.demo else "read-only-preview",
            limitation="作者候选解释及结构预览；固定替身不证明人物效果或自由台词事实成立。",
            preview=asdict(product.application.preview_character_reply(request)))
        if args.demo: payload["candidate"] = asdict(product.application.propose_character_reply(request))
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output is not None:
        path = args.output.resolve(); path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream: stream.write(text + "\n")
        print(json.dumps(dict(mode=payload["mode"], output=str(path)), ensure_ascii=False))
    else: print(text)


if __name__ == "__main__": main()
