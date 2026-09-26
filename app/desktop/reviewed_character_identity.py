"""Create the exact confirmed private reviewed-character identity; never activate chat."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preparation", type=Path, required=True)
    parser.add_argument("--definition-basis", required=True)
    parser.add_argument("--product-parent", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--rights-confirmed", action="store_true")
    parser.add_argument("--confirmed", action="store_true")
    args = parser.parse_args()
    if not (args.rights_confirmed and args.confirmed):
        print(json.dumps(dict(status="awaiting-confirmation", definition_basis=args.definition_basis,
            rights_confirmed=args.rights_confirmed, confirmed=args.confirmed, created=False), ensure_ascii=False))
        return
    with args.preparation.resolve().open("rb") as stream:
        raw = stream.read(4_000_001)
    if len(raw) > 4_000_000: parser.error("preparation too large")
    request = ReviewedCharacterFreezeRequest(raw.decode("utf-8"), args.definition_basis, args.rights_confirmed, args.confirmed)
    # Reject malformed content before even initializing a product root.
    from dynamic_subject_agent.reviewed_character_definition import prepare_reviewed_definition
    try:
        prepare_reviewed_definition(request)
    except Exception:
        print(json.dumps(dict(status="rejected", problem_code="reviewed-character-definition-invalid", created=False), ensure_ascii=False))
        return
    config = LocalProductConfig(args.product_parent.resolve(), args.state.resolve())
    with open_local_product(config, cognition=DormantDeepSeekCognition()) as product:
        result = product.application.freeze_source_identity(request)
    print(json.dumps(asdict(result), ensure_ascii=False))


if __name__ == "__main__": main()
