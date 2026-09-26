"""Prepare 24 frozen candidate reviews; executing them needs new exact approval."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
from dynamic_subject_agent.character_reply_review_trial import CharacterReplyReviewRequest
from dynamic_subject_agent.character_context_trial import save_trial_plan
from dynamic_subject_agent.local_product import prepare_character_reply_review_trial, open_character_reply_review_trial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--reviewed-digest", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--anchor", required=True)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--max-knowledge-chars", type=int, default=20000)
    parser.add_argument("--approve-plan", help="操作人声明此精确新审核用途已获用户批准；参数本身不构成批准")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2] / ".artifacts/character-reply-review-trials"
    try:
        cases = json.loads(args.cases.read_text(encoding="utf-8"))
        options = dict(draft_path=args.draft.resolve(), source_root=args.source_root.resolve(),
            reviewed_digest=args.reviewed_digest, subject_id=args.subject, anchor_id=args.anchor,
            cases=cases, max_knowledge_chars=args.max_knowledge_chars)
        plan = prepare_character_reply_review_trial(root, **options)
        if args.approve_plan is not None and args.approve_plan != plan.digest:
            parser.error("必须批准当前精确审核计划digest")
        path = save_trial_plan(root, plan)
        print(json.dumps(dict(status="prepared", digest=plan.digest, plan_path=str(path), request_count=24,
                              plan_chars=len(plan.serialized), max_knowledge_chars=args.max_knowledge_chars), ensure_ascii=False), flush=True)
        if args.approve_plan is None:
            return
        with open_character_reply_review_trial(root, **options, approved_plan=args.approve_plan) as product:
            for case in cases["cases"]:
                request = CharacterReplyReviewRequest(CharacterChatContextRequest(
                    args.subject, args.anchor, case["message"], case["context_mode"], args.max_knowledge_chars), case["id"])
                result = product.application.propose_character_reply(request)
                print(json.dumps(dict(case_id=case["id"], mode=case["context_mode"], result=asdict(result)), ensure_ascii=False), flush=True)
                if result.review_verdict not in ("supported", "unsupported", "uncertain"):
                    return
    except (OSError, ValueError, KeyError, TypeError):
        parser.error("审核计划准备或审计校验失败；未自动重试，请核对本地资料与计划")


if __name__ == "__main__":
    main()
