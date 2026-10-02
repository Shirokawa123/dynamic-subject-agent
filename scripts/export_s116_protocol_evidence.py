"""Export every completed live S116 run, including failures, without new calls."""
from hashlib import sha256
import json
from pathlib import Path

from dynamic_subject_agent.development_model_calls import DevelopmentCallAudit
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.reply_protocol_trial import ProtocolRun, fixed_protocol_runs_root, fixed_development_audit_path


def main():
    runs, transcript = [], ["# S116：固定输入的全部实际输出", "", "以下是协议诊断；输出未进入人物聊天历史。结构通过不等于语义通过。", ""]
    for path in sorted(fixed_protocol_runs_root().glob("*/summary.json"), key=lambda p: p.stat().st_mtime_ns):
        summary = json.loads(path.read_text(encoding="utf-8"))
        if not summary.get("live"):
            continue
        if summary["package_sha256"]!="4e4ed6a664821d18f827d7a6f62d50aeec8b07222709ef238a9853bbba2e88e5":
            continue
        manifest_path = path.with_name("manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        plan = ProtocolRun(path.parent, summary["run_digest"])
        assert plan.read() == manifest and summary["character_history_empty"]
        assert summary["call_limit"] is None and summary["automatic_retries"] == 0
        journal_path = path.with_name("results.jsonl")
        journal = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
        assert [dict((k, v) for k, v in row.items() if k != "event") for row in journal if row["event"] == "model-attempt"] == summary["observations"]
        requests = []
        for row in plan.sequence:
            request = plan.request_for(row["case_id"], row["variant"])
            wire = plan.wire_for(request)
            requests.append(dict(case_id=request.case_id, variant=request.variant, attempt_id=request.attempt_id,
                wire_sha256=sha256(wire).hexdigest(), request_body=json.loads(wire)))
        request_index = {r["attempt_id"]: r for r in requests}
        audit = DevelopmentCallAudit(fixed_development_audit_path())
        for row in summary["observations"]:
            assert request_index[row["attempt_id"]]["wire_sha256"] == row["wire_sha256"]
            recorded = audit.query(row["attempt_id"])
            assert recorded["request_digest"] == row["wire_sha256"] and recorded["run_digest"] == plan.digest
            assert recorded["status"] == row["audit_status"]
        runs.append(dict(manifest=manifest, summary=summary, requests=requests,
            source_sha256={p.name: sha256(p.read_bytes()).hexdigest() for p in (path, manifest_path, journal_path)}))
        transcript.extend(["## " + summary["label"], "", "运行：`" + summary["run_id"] + "`；研究：`" + plan.study + "`。", ""])
        observations = {r["attempt_id"]: r for r in summary["observations"]}
        for row in summary["results"]:
            transcript.extend(["### " + str(row["number"]) + ". " + row["case_id"] + " / " + row["variant"], "",
                "状态：`" + row["status"] + "`；诊断：`" + str(row["diagnostic_code"]) + "`。", ""])
            if row["value"] is not None:
                transcript.extend([row["value"]["reply_text"], "", "```json", json.dumps(row["value"], ensure_ascii=False, indent=2), "```", ""])
            else:
                content = observations[row["attempt_id"]]["final_content"]
                transcript.extend(["最终字段（JSON字符串保留空格）：", "", "```json", json.dumps(content, ensure_ascii=False), "```", ""])
    evidence = dict(version="s116-protocol-evidence-1", runs=runs,
        call_limit=None, automatic_retries=0, hidden_reasoning_saved=False,
        total_attempts=sum(len(r["summary"]["observations"]) for r in runs))
    evidence["evidence_digest"] = sha256(canonical_json(evidence).encode()).hexdigest()
    destination = Path(__file__).resolve().parents[1] / "docs/reports/2026-10-01-slice-116"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "protocol-results.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (destination / "TRANSCRIPT.md").write_text("\n".join(transcript), encoding="utf-8")
    print(canonical_json(dict(attempts=evidence["total_attempts"], runs=len(runs), evidence_digest=evidence["evidence_digest"])))


if __name__ == "__main__":
    main()
