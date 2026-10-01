"""Prepare S115 from committed synthetic evidence; never send a model request."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from dynamic_subject_agent.first_life_reply_candidate import recorded_reply_task
from dynamic_subject_agent.first_life_reply_protocol import (
    PROTOCOL_VERSION, preview_json_example, replay_recorded_reply,
)
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelTaskKind


ROOT = Path(__file__).resolve().parents[1]
REPORTS = (
    "docs/reports/2026-10-01-slice-112/continuous-comparison.json",
    "docs/reports/2026-10-01-slice-114/continuous-comparison.json",
)
CASES = (
    ("objects-and-versions-A", 1),
    ("plan-versus-completion-A", 4),
    ("plan-versus-completion-B", 1),
    ("objects-and-versions-B", 3),
)
REPLY_KINDS = (ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY.value,
    ModelTaskKind.CHARACTER_FIRST_LIFE_FACT_EXPRESSION.value)


def digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


def load_report(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    content = dict(value)
    expected = content.pop("evidence_digest")
    if digest(content) != expected:
        raise ValueError("committed synthetic evidence digest changed")
    return value


def prepare_package():
    reports = [load_report(ROOT / path) for path in REPORTS]
    package = dict(version="s115-json-example-paired-proposal-1", protocol_version=PROTOCOL_VERSION,
        authorization="pending-user-confirmation", requested_attempts=8, automatic_retries=0,
        product_calls_during_preparation=0, model_grading_calls=0,
        purpose="Isolate one JSON-format-example change; no claim of stable language quality or continuous character acceptance",
        sources=[dict(path=path, canonical_sha256=digest(report), evidence_digest=report["evidence_digest"])
            for path, report in zip(REPORTS, reports, strict=True)], replay=[], cases=[], sequence=[])
    for source, report in zip(REPORTS, reports, strict=True):
        for branch in report["branches"]:
            for step in branch["steps"]:
                for stage in step["stages"]:
                    if stage["task_kind"] not in REPLY_KINDS:
                        continue
                    replay = replay_recorded_reply(stage)
                    if replay["status"] == "structured" and replay["value"] != stage["value"]:
                        raise ValueError("recorded success changed during offline replay")
                    package["replay"].append(dict(source=source, branch_id=branch["branch_id"], step=step["step"],
                        task_kind=stage["task_kind"], original_error_code=stage["error_code"], replay=replay))
    for index, (branch_id, step_number) in enumerate(CASES):
        branch = next(b for b in reports[1]["branches"] if b["branch_id"] == branch_id)
        step = next(s for s in branch["steps"] if s["step"] == step_number)
        stage = step["stages"][-1]
        task = recorded_reply_task(stage["task_kind"], stage["payload"])
        candidate = preview_json_example(task)
        baseline = canonical_json(stage["request_body"])
        if (sha256(baseline.encode()).hexdigest() != stage["wire_sha256"]
            or candidate.baseline_wire_sha256 != stage["wire_sha256"]
            or candidate.source_payload_sha256 != stage["request_digest"]):
            raise ValueError("protocol baseline does not match actual sent request")
        case_id = f"{branch_id}-step-{step_number}"
        package["cases"].append(dict(case_id=case_id, source=REPORTS[1], branch_id=branch_id, step=step_number,
            task_kind=stage["task_kind"], payload=stage["payload"], request_digest=stage["request_digest"],
            original_reply=step["reply"], original_final_content=stage["final_content"],
            original_error_code=stage["error_code"], baseline_wire_utf8=baseline,
            baseline_wire_sha256=stage["wire_sha256"], candidate_wire_utf8=candidate.wire.decode("utf-8"),
            candidate_wire_sha256=candidate.candidate_wire_sha256, appended_system=candidate.appended_system))
        # Both arms are predefined, not triggered by a failed delivery. Alternate
        # first arm to avoid always warming the same protocol's prompt cache.
        for variant in (("baseline", "json-example") if index % 2 == 0 else ("json-example", "baseline")):
            package["sequence"].append(dict(case_id=case_id, variant=variant, maximum_attempts=1))
    package["package_sha256"] = digest(package)
    return package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = prepare_package()
    content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_text(encoding="utf-8") != content:
        raise ValueError("an existing different review package cannot be silently replaced")
    if not args.output.exists():
        args.output.write_text(content, encoding="utf-8")
    print(canonical_json(dict(output=str(args.output.resolve()), package_sha256=value["package_sha256"],
        cases=len(value["cases"]), proposed_calls=len(value["sequence"]), actual_calls=0)))


if __name__ == "__main__":
    main()
