"""Prepare six parent-derived expressions; new exact approval required for delivery."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
from dynamic_subject_agent.character_communication_trial import save_communication_trial_plan
from dynamic_subject_agent.local_product import prepare_character_expression_thinking_trial, open_character_expression_thinking_trial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--parent-plan", required=True)
    parser.add_argument("--approve-plan", help="操作人声明此六次表达用途和精确计划已获新批准；参数本身不构成批准")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    root = repo / ".artifacts/character-expression-thinking-trials"
    options = dict(parent_trial_root=repo / ".artifacts/character-communication-trials", parent_plan_digest=args.parent_plan,
        draft_path=args.draft.resolve(), source_root=args.source_root.resolve())
    try:
        plan = prepare_character_expression_thinking_trial(root, **options)
        if args.approve_plan is not None and args.approve_plan != plan.digest: parser.error("必须批准当前表达精确计划digest")
        print(json.dumps(dict(status="prepared", digest=plan.digest, plan_path=str(save_communication_trial_plan(root, plan)),
            parent_plan_digest=args.parent_plan, expression_calls=6, planning_calls=0), ensure_ascii=False), flush=True)
        if args.approve_plan is None: return
        with open_character_expression_thinking_trial(root, **options, approved_plan=args.approve_plan) as product:
            for row in plan.payload["requests"]:
                result = product.application.propose_character_reply(CharacterChatContextRequest(plan.payload["subject_id"], plan.payload["anchor_id"],
                    row["message"], row["mode"], plan.payload["max_knowledge_chars"]))
                print(json.dumps(dict(case_id=row["case_id"], result=asdict(result)), ensure_ascii=False), flush=True)
                if result.status != "candidate": return
    except (OSError, ValueError, KeyError, TypeError):
        parser.error("父审计、源资料或计划准备不可用；没有自动重试")


if __name__ == "__main__": main()
