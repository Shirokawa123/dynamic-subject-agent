"""Read a reviewed local character draft through ApplicationFacade; no model calls."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

from dynamic_subject_agent.character_evidence_model import CharacterModelRequest
from dynamic_subject_agent.local_product import open_character_model_preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--reviewed-digest", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--anchor", required=True)
    args = parser.parse_args()
    parent = Path(__file__).resolve().parents[2] / ".artifacts/character-model-previews"
    with open_character_model_preview(parent, draft_path=args.draft.resolve(),
                                      source_root=args.source_root.resolve(),
                                      reviewed_digest=args.reviewed_digest) as product:
        view = product.application.preview_character_model(CharacterModelRequest(args.subject, args.anchor))
        print(json.dumps(asdict(view), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
