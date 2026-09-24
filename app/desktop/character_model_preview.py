"""Read a reviewed local character draft through ApplicationFacade; no model calls."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

from dynamic_subject_agent.character_evidence_model import CharacterModelRequest, CharacterContextRequest
from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
from dynamic_subject_agent.local_product import open_character_model_preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--reviewed-digest", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--anchor", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--context", help="查看该证据的同文档相邻语境，仅本地")
    mode.add_argument("--chat-message", help="仅预览该消息的角色上下文；不生成回复或调用模型")
    parser.add_argument("--before", type=int, default=5)
    parser.add_argument("--after", type=int, default=5)
    args = parser.parse_args()
    parent = Path(__file__).resolve().parents[2] / ".artifacts/character-model-previews"
    with open_character_model_preview(parent, draft_path=args.draft.resolve(),
                                      source_root=args.source_root.resolve(),
                                      reviewed_digest=args.reviewed_digest) as product:
        request = (CharacterContextRequest(args.subject, args.anchor, args.context, args.before, args.after)
                   if args.context is not None else CharacterModelRequest(args.subject, args.anchor))
        if args.chat_message is not None:
            view = product.application.preview_character_chat_context(
                CharacterChatContextRequest(args.subject, args.anchor, args.chat_message))
        else:
            view = product.application.preview_character_model(request)
        print(json.dumps(asdict(view), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
