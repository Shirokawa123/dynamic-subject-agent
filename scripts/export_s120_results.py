"""Export specified synthetic runs; never scan or export live user chats."""
from hashlib import sha256
import json
from pathlib import Path
import os

from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.reply_protocol_trial import ProtocolRun,EXPRESSION_SCOPE_PACKAGE_DIGEST


STATIC_RUNS=("9cee018d-1e88-4f0e-a578-589edd9392ca","59f06972-aa8c-475d-b165-37665e4e3cb1")
CONTINUOUS_RUNS=("fd40e7d1-b249-4aff-90ff-26a158bf03d8","bbeacec6-f87b-4e87-9411-e6493b6c40a7")


def main():
    base=Path(os.environ["LOCALAPPDATA"])/"DynamicSubjectAgent/development-calls"
    static=[];continuous=[]
    lines=["# S120：全部实际输出", "", "只导出指定的开发合成实验，原失败不补答。", ""]
    for run_id in STATIC_RUNS:
        path=base/"runs"/run_id/"summary.json"
        summary=json.loads(path.read_text(encoding="utf-8"))
        plan=ProtocolRun(path.parent,summary["run_digest"])
        assert plan.read()["package_digest"]==EXPRESSION_SCOPE_PACKAGE_DIGEST and summary["character_history_empty"]
        static.append(dict(manifest=plan.read(),summary=summary,source_sha256=sha256(path.read_bytes()).hexdigest()))
        lines += ["## "+summary["label"], ""]
        observations={row["attempt_id"]:row for row in summary["observations"]}
        for row in summary["results"]:
            lines += ["### "+row["case_id"]+" / "+row["variant"], "", "状态：`"+row["status"]+"`。", ""]
            if row["value"] is not None:lines += [row["value"]["reply_text"], ""]
            else:lines += ["最终content：", "", "```json",json.dumps(observations[row["attempt_id"]]["final_content"],ensure_ascii=False),"```", ""]
    for run_id in CONTINUOUS_RUNS:
        path=base/"free-input-runs"/run_id/"s120-dialogue-summary.json"
        summary=json.loads(path.read_text(encoding="utf-8"))
        assert summary["private_user_content_exported"] is False and summary["automatic_retries"]==0
        manifest=json.loads(path.with_name("approval.json").read_text(encoding="utf-8"))
        continuous.append(dict(manifest=manifest,summary=summary,source_sha256=sha256(path.read_bytes()).hexdigest()))
        lines += ["## 连续链 / "+summary["variant"], "", "收口：`"+summary["status"]+"`。", ""]
        for row in summary["steps"]:
            lines += ["### 第"+str(row["number"])+"轮", "", "用户："+row["user_text"], "", "小林："+(row["assistant_text"] or "[未提交回复]"), "", "错误：`"+str(row["failure_code"])+"`。", ""]
    first=[run["summary"]["steps"][0]["observations"][0]["request_digest"] for run in continuous]
    assert first[0]==first[1]
    value=dict(version="s120-owned-comparison-results-1",static=static,continuous=continuous,
        same_initial_request_digest=first[0],actual_static_requests=sum(len(row["summary"]["observations"]) for row in static),
        actual_continuous_requests=sum(row["summary"]["actual_attempts"] for row in continuous))
    value["evidence_digest"]=sha256(canonical_json(value).encode()).hexdigest()
    output=Path(__file__).resolve().parents[1]/"docs/reports/2026-10-02-slice-120"
    output.mkdir(parents=True,exist_ok=True)
    (output/"comparisons.json").write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (output/"TRANSCRIPT.md").write_text("\n".join(lines),encoding="utf-8")
    print(canonical_json(dict(static_requests=value["actual_static_requests"],continuous_requests=value["actual_continuous_requests"],evidence_digest=value["evidence_digest"])))


if __name__=="__main__":main()
