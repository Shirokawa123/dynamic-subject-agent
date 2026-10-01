"""Export an existing S117 run; no replays, credentials, or model calls."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from dynamic_subject_agent.first_life_development_trial import DevelopmentReplyTrial
from dynamic_subject_agent.frozen_attempt import canonical_json


def export_run(root: Path):
    paths = [root / name for name in ("approval.json", "continuous-summary.json", "continuous-results.jsonl")]
    manifest, summary = [json.loads(p.read_text(encoding="utf-8")) for p in paths[:2]]
    trial = DevelopmentReplyTrial(root, sha256(canonical_json(manifest).encode()).hexdigest())
    assert trial.read() == manifest and manifest["live"]
    observations = [row for line in paths[2].read_text(encoding="utf-8").splitlines()
        if (row := json.loads(line))["event"] == "stage-observed"]
    stages = [stage for branch in summary["branches"] for step in branch["steps"] for stage in step["stages"]]
    # Branch failures before a Facade result still preserve their stage in the journal.
    for stage in stages:
        assert any(all(row.get(k) == v for k, v in stage.items()) for row in observations)
    audit = trial.shared_budget()
    audit.counts()
    with sqlite3.connect(audit.path / "calls.sqlite3") as db:
        db.row_factory = sqlite3.Row
        records = [dict(row) for row in db.execute("SELECT ordinal,attempt_id,request_digest,purpose,run_digest,status,output_digest FROM call_attempt WHERE run_digest=? ORDER BY ordinal", (trial.manifest_digest,))]
    for row in observations:
        assert row["request_digest"] == sha256(canonical_json(row["payload"]).encode()).hexdigest()
        assert row["wire_sha256"] == sha256(canonical_json(row["request_body"]).encode()).hexdigest()
        assert any(r["request_digest"] == row["request_digest"] for r in records)
    evidence = dict(version="s117-continuous-evidence-1", manifest=manifest, manifest_digest=trial.manifest_digest,
        summary=summary, observations=observations, call_audit=records, call_limit=None,
        automatic_retries=0, source_sha256={p.name:sha256(p.read_bytes()).hexdigest() for p in paths})
    evidence["evidence_digest"] = sha256(canonical_json(evidence).encode()).hexdigest()
    output = Path(__file__).resolve().parents[1] / "docs/reports/2026-10-01-slice-117"
    output.mkdir(parents=True, exist_ok=True)
    (output / "continuous-comparison.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text = ["# S117：完整连续链实际原文", "", "运行：`" + root.name + "`。原错误与失败没有补写，seed为原获准程序材料。", ""]
    for branch in summary["branches"]:
        text += ["## " + branch["branch_id"], "", "收口：`" + branch["status"] + "`。", ""]
        for step in branch["steps"]:
            text += ["### 第" + str(step["step"]) + "步 / " + step["kind"], ""]
            if step["user"]:
                text += ["用户：" + step["user"], ""]
            text += ["人物：" + (step["reply"] or "[未提交回复]"), "",
                "状态：`" + step["status"] + "`；错误：`" + str(step["failure_code"]) + "`。", ""]
            for stage in step["stages"]:
                if stage["error_code"]:
                    text += ["阶段：`" + stage["task_kind"] + "`，`" + stage["error_code"] + "`；最终字段：", "", "```json", json.dumps(stage["final_content"], ensure_ascii=False), "```", ""]
    (output / "TRANSCRIPT.md").write_text("\n".join(text), encoding="utf-8")
    print(canonical_json(dict(attempts=len(records), observations=len(observations), evidence_digest=evidence["evidence_digest"])))
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path)
    export_run(parser.parse_args().run_root.resolve())
