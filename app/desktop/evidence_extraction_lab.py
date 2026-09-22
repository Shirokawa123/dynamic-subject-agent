"""Fixed three-packet evidence extraction. Offline unless explicitly approved."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from uuid import uuid4

from dynamic_subject_agent.evidence_extraction import EvidenceExtractionRequest, extraction_plan_digest, extraction_plan_payload
from dynamic_subject_agent.local_product import open_evidence_extraction_lab


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-plan", action="store_true")
    parser.add_argument("--approve-plan")
    parser.add_argument("--confirm-source-rights-and-use", action="store_true")
    args = parser.parse_args()
    if args.print_plan:
        print(json.dumps(dict(plan=extraction_plan_payload(), digest=extraction_plan_digest()),ensure_ascii=False,indent=2))
        return
    if args.approve_plan is not None and not args.confirm_source_rights_and_use:
        parser.error("真实提取需要已确认来源权利及本次用途")
    root = Path(__file__).resolve().parents[2]
    with open_evidence_extraction_lab(root / ".artifacts/evidence-extraction-labs", workspace=root,
                                      approved_plan=args.approve_plan) as product:
        for index in range(3):
            # Offline uses a no-op adapter for wiring verification, never a real rights assertion.
            result = product.application.extract_character_evidence(EvidenceExtractionRequest(index, uuid4().hex, True, True))
            print(json.dumps(asdict(result),ensure_ascii=False),flush=True)
            if result.status not in ("candidates", "no-op"):
                break


if __name__ == "__main__":
    main()
