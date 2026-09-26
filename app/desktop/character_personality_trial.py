"""Prepare a frozen six-case personality trial; new exact approval before delivery."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

from dynamic_subject_agent.character_chat_context import CharacterChatContextRequest
from dynamic_subject_agent.character_communication_trial import save_communication_trial_plan
from dynamic_subject_agent.local_product import prepare_character_personality_trial, open_character_personality_trial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("draft", "source-root", "sidecar", "cases"): parser.add_argument("--" + name, required=True, type=Path)
    for name in ("reviewed-digest", "personality-digest", "subject", "anchor"): parser.add_argument("--" + name, required=True)
    parser.add_argument("--max-knowledge-chars", type=int, default=20000)
    parser.add_argument("--planning-effort", choices=("low", "high"), default="high")
    parser.add_argument("--approve-plan", help="操作人声明当前新人格输入用途与精确计划已获批准；参数本身不构成批准")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2] / ".artifacts/character-personality-trials"
    try:
        cases = json.loads(args.cases.read_text(encoding="utf-8"))
        options = dict(draft_path=args.draft.resolve(), source_root=args.source_root.resolve(), sidecar_path=args.sidecar.resolve(),
            cases=cases, reviewed_digest=args.reviewed_digest, personality_digest=args.personality_digest,
            subject_id=args.subject, anchor_id=args.anchor, max_knowledge_chars=args.max_knowledge_chars, planning_effort=args.planning_effort)
        plan = prepare_character_personality_trial(root, **options)
        if args.approve_plan is not None and args.approve_plan != plan.digest: parser.error("必须批准当前新人格精确计划")
        print(json.dumps(dict(status="prepared", digest=plan.digest, plan_path=str(save_communication_trial_plan(root, plan)),
            cases=6, max_calls=12, condition="resident-core-and-personality"), ensure_ascii=False), flush=True)
        if args.approve_plan is None: return
        with open_character_personality_trial(root, **options, approved_plan=args.approve_plan) as product:
            for case in cases["cases"]:
                result = product.application.propose_character_reply(CharacterChatContextRequest(args.subject, args.anchor,
                    case["message"], case["context_mode"], args.max_knowledge_chars))
                print(json.dumps(dict(case_id=case["id"], result=asdict(result)), ensure_ascii=False), flush=True)
                if result.status != "candidate": return
    except (OSError, ValueError, KeyError, TypeError):
        parser.error("人格资料或冻结审计不可用；没有自动重试")


if __name__ == "__main__": main()
