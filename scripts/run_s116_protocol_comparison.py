"""Run one planned eight-entry protocol comparison under ongoing call authority.

Use a new run UUID for an intentional new replication. Existing journals cannot
be replayed, and the audit has no numerical quota. This does not retry a request.
"""
import argparse
from collections import Counter
from dataclasses import asdict
import json
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from dynamic_subject_agent.development_model_calls import DevelopmentCallAudit
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.local_product import open_reply_protocol_lab
from dynamic_subject_agent.reply_protocol_trial import open_protocol_run, fixed_protocol_runs_root, fixed_development_audit_path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs/experiments/s115/protocol-comparison.json"
OUTPUT_FAILURES = frozenset(("response-content-empty", "response-content-json", "protocol-response-invalid",
    "response-truncated", "response-overbudget", "format-example-copied"))


def run_once(run_root, *, live, transport=None, label="initial-format-comparison"):
    plan = open_protocol_run(run_root, PACKAGE, live=live)
    observations, results = [], []
    with (plan.root / "results.jsonl").open("x", encoding="utf-8") as journal:
        def append(row):
            journal.write(canonical_json(row) + "\n")
            journal.flush()
            os.fsync(journal.fileno())
        def observed(row):
            append(dict(event="model-attempt", **row))
            observations.append(row)
        append(dict(event="run-started", version="s116-protocol-comparison-1", label=label,
            run_digest=plan.digest, live=live, call_limit=None,
            planned_requests=len(plan.sequence), automatic_retries=0))
        stop_reason = None
        with open_reply_protocol_lab(plan.root, PACKAGE, live=live, _transport=transport,
                response_audit=observed) as product:
            for number, row in enumerate(plan.sequence, 1):
                request = plan.request_for(row["case_id"], row["variant"])
                append(dict(event="step-started", number=number, **asdict(request)))
                started = perf_counter()
                value = product.application.evaluate_reply_protocol(request)
                result = dict(number=number, **asdict(value), end_to_end_seconds=perf_counter() - started)
                append(dict(event="step-finished", **result))
                results.append(result)
                if value.status != "structured" and getattr(value, "diagnostic_code", None) not in OUTPUT_FAILURES:
                    stop_reason = getattr(value, "diagnostic_code", None) or "protocol-entry-unavailable"
                    break
            history = product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
                product.profile_id, product.timeline_id))
            empty_history = history.status == "available" and not history.projection.turns
            if not empty_history:
                raise ValueError("protocol results must not enter character history")
        audit_path = fixed_development_audit_path() if live else plan.root / "offline-audit"
        limit, used, remaining = DevelopmentCallAudit(audit_path).counts()
        variants = {}
        for variant in ("baseline", "json-example"):
            selected = [r for r in results if r["variant"] == variant]
            variants[variant] = dict(attempts=len(selected), structured=sum(r["status"] == "structured" for r in selected),
                format_example_copied=sum(r["format_example_copied"] for r in selected),
                failures=dict(Counter(r["diagnostic_code"] for r in selected if r["diagnostic_code"])))
        summary = dict(version="s116-protocol-comparison-1", label=label, run_id=plan.root.name,
            run_digest=plan.digest, package_sha256=plan.package["package_sha256"], live=live,
            status="completed" if stop_reason is None else "stopped-infrastructure-failure", stop_reason=stop_reason,
            automatic_retries=0, call_limit=limit, development_attempts_total=used, remaining=remaining,
            character_history_empty=bool(empty_history), results=results, observations=observations, variants=variants)
        append(dict(event="run-finished", status=summary["status"], stop_reason=stop_reason,
            call_limit=limit, development_attempts_total=used, variants=variants, character_history_empty=True))
        with (plan.root / "summary.json").open("x", encoding="utf-8") as output:
            output.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
            output.flush()
            os.fsync(output.fileno())
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--label", default="initial-format-comparison")
    args = parser.parse_args()
    if not args.live:
        parser.error("use --live for the authorized actual run; tests inject a local transport")
    run_root = fixed_protocol_runs_root() / str(uuid4())
    print(canonical_json(dict(started_run=str(run_root), label=args.label, call_limit=None)), flush=True)
    result = run_once(run_root, live=True, label=args.label)
    print(canonical_json(dict(root=str(run_root), status=result["status"], variants=result["variants"],
        development_attempts_total=result["development_attempts_total"], call_limit=None)))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
