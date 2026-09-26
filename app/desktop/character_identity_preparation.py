"""Read-only derived identity preview; no save, freeze, identity selection or model calls."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

from dynamic_subject_agent.character_evidence_model import CharacterModelRequest
from dynamic_subject_agent.character_identity_preparation import CharacterDefinitionPreparationRequest
from dynamic_subject_agent.local_product import open_character_model_preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--reviewed-digest", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--anchor", required=True)
    parser.add_argument("--sidecar", type=Path, help="可选的人格候选文件，与摘要成对提供")
    parser.add_argument("--personality-digest", help="已审本地人格文件摘要，与sidecar成对提供")
    parser.add_argument("--output", type=Path, help="显式写出本地预览JSON；不保存Source Draft或身份")
    args = parser.parse_args()
    if (args.sidecar is None) != (args.personality_digest is None): parser.error("sidecar和personality-digest必须成对提供")
    root = Path(__file__).resolve().parents[2] / ".artifacts/character-identity-preparations"
    with open_character_model_preview(root, draft_path=args.draft.resolve(), source_root=args.source_root.resolve(),
                                      reviewed_digest=args.reviewed_digest) as product:
        request = CharacterDefinitionPreparationRequest(args.subject, args.anchor, args.sidecar.resolve(), args.personality_digest) if args.sidecar is not None else CharacterModelRequest(args.subject, args.anchor)
        view = product.application.preview_character_identity_preparation(request)
    payload = json.dumps(asdict(view), ensure_ascii=False, indent=2)
    if args.output is not None:
        path = args.output.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream: stream.write(payload + "\n")
        print(json.dumps(dict(status=view.status, code=view.code, output=str(path), draft_saved=False, identity_created=False,
            execution_ready=False, blocker=view.blocker, content_mapping_only=True, definition_basis=view.definition_basis), ensure_ascii=False))
    else:
        print(payload)


if __name__ == "__main__": main()
