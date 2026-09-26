"""Freeze six planning/expression cases; default preparation never sends requests."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
from dynamic_subject_agent.character_communication_trial import save_communication_trial_plan
from dynamic_subject_agent.local_product import prepare_character_communication_trial, open_character_communication_trial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--reviewed-digest", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--anchor", required=True)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--max-knowledge-chars", type=int, default=20000)
    parser.add_argument("--expression-profile", choices=("standard", "thinking-high"), default="standard")
    parser.add_argument("--approve-plan", help="操作人声明两阶段用途和此精确计划已获用户批准；参数本身不构成批准")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2] / ".artifacts/character-communication-trials"
    try:
        cases = json.loads(args.cases.read_text(encoding="utf-8"))
        options = dict(draft_path=args.draft.resolve(), source_root=args.source_root.resolve(), reviewed_digest=args.reviewed_digest,
            subject_id=args.subject, anchor_id=args.anchor, cases=cases, max_knowledge_chars=args.max_knowledge_chars,
            expression_profile=args.expression_profile)
        plan = prepare_character_communication_trial(root, **options)
        if args.approve_plan is not None and args.approve_plan != plan.digest:
            parser.error("必须批准当前两阶段精确计划digest")
        print(json.dumps(dict(status="prepared", digest=plan.digest, plan_path=str(save_communication_trial_plan(root, plan)),
            case_count=6, frozen_planning_requests=6, max_calls=12, expression_requests="Only derived and recorded after a valid audited plan"), ensure_ascii=False), flush=True)
        if args.approve_plan is None:
            return
        with open_character_communication_trial(root, **options, approved_plan=args.approve_plan) as product:
            for case in cases["cases"]:
                result = product.application.propose_character_reply(CharacterChatContextRequest(
                    args.subject, args.anchor, case["message"], case["context_mode"], args.max_knowledge_chars))
                print(json.dumps(dict(case_id=case["id"], result=asdict(result)), ensure_ascii=False), flush=True)
                if result.status != "candidate":
                    return
    except (OSError, ValueError, KeyError, TypeError):
        parser.error("试验准备或审计校验失败；没有自动重试，请核对固定资料与计划")


if __name__ == "__main__":
    main()
