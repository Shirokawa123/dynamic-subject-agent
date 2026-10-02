"""Review one exact existing character package locally; never open a runtime or send."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

from dynamic_subject_agent.application import ApplicationFacade
from dynamic_subject_agent.original_whole_use_preparation import OriginalWholeUsePreparationRequest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--definition-basis", required=True)
    parser.add_argument("--asset-sha", required=True)
    parser.add_argument("--persona-digest", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--anchor", required=True)
    parser.add_argument("--output", type=Path, help="显式新建无人物正文的本地review JSON，不覆盖已有文件")
    args = parser.parse_args()
    view = ApplicationFacade.preview_original_character_whole_use_preparation(OriginalWholeUsePreparationRequest(
        args.package.resolve(), args.definition_basis, args.asset_sha, args.persona_digest, args.subject, args.anchor))
    if args.output is not None and view.status == "previewed":
        path = args.output.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(asdict(view), ensure_ascii=False, indent=2) + "\n")
    summary = {key: value for key, value in asdict(view).items() if key not in ("proposed_scope_json", "synthetic_example_json")}
    if args.output is not None and view.status == "previewed":
        summary["output"] = str(args.output.resolve())
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if view.status == "previewed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
