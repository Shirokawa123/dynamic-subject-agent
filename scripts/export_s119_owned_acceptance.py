"""Export only this development-owned example session, never arbitrary user chat."""
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from urllib.request import urlopen

from dynamic_subject_agent.development_model_calls import DevelopmentCallAudit
from dynamic_subject_agent.first_life_free_input_trial import fixed_free_input_audit_path
from dynamic_subject_agent.reply_protocol_trial import fixed_development_root, fixed_development_audit_path
from dynamic_subject_agent.frozen_attempt import canonical_json


OWNED_MESSAGES = (
    "今天先聊点新的吧：圆形和方形，哪个更容易让你想到安静？",
    "那我选方形。你觉得先聊它的边缘，还是它在画面里的位置更有意思？",
    "那就先说你刚才选的那部分吧，给我一个简单的例子。",
    "换个话题：蓝色和绿色搭在一起，你现在更想让哪一种做主色？",
)


def main():
    states={}
    for port in (8780,8781):
        with urlopen(f"http://127.0.0.1:{port}/status",timeout=20) as response:
            states[port]=json.load(response)
    for case in states[8781]["cases"]:
        assert case["state"]["history"]["status"]=="available" and not case["state"]["presentation_pending"]
        for item in case["state"]["messages"]:
            if item["kind"]=="dialogue" and item["user_text"] not in {*OWNED_MESSAGES,"先打个招呼。"}:
                raise ValueError("user-owned content present: do not export the conversation")
    pointer=json.loads((fixed_development_root()/"whole-reply-free-input-entry/current.json").read_text(encoding="utf-8"))
    audit=DevelopmentCallAudit(fixed_free_input_audit_path())
    audit.counts()
    with sqlite3.connect(audit.path/"calls.sqlite3") as db:
        db.row_factory=sqlite3.Row
        attempts=[dict(row) for row in db.execute("SELECT ordinal,attempt_id,request_digest,purpose,run_digest,status,output_digest FROM call_attempt WHERE run_digest=? ORDER BY ordinal",(pointer["manifest_digest"],))]
    assert len(attempts)==4 and all(row["status"]=="complete" for row in attempts)
    old_counts=DevelopmentCallAudit(fixed_development_audit_path()).counts()
    value=dict(version="s119-owned-ui-acceptance-1", data_origin="developer-authored synthetic ordinary messages",
        state=states[8781], attempts=attempts, actual_requests=len(attempts), call_limit=None,
        old_audit_used=old_counts[1], old_service_readable=all(c["state"]["history"]["status"]=="available" for c in states[8780]["cases"]),
        automatic_retries=0, startup_model_calls=0, reopen_model_calls=0, pending_refresh_extra_calls=0,
        history_off_boundary="real toggle plus existing synthetic wire verification; raw private wire not exported")
    value["evidence_digest"]=sha256(canonical_json(value).encode()).hexdigest()
    root=Path(__file__).resolve().parents[1]/"docs/reports/2026-10-02-slice-119"
    root.mkdir(parents=True,exist_ok=True)
    (root/"owned-ui-acceptance.json").write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["# S119：开发合成普通问法的实际对话", "", "以下四句由开发编写，不是用户私人聊天；只导出这个受控样本。", ""]
    for case in value["state"]["cases"]:
        for item in case["state"]["messages"]:
            if item["kind"]=="dialogue" and item["user_text"] in OWNED_MESSAGES:
                lines += ["用户："+item["user_text"],"","小林："+item["assistant_text"],""]
    (root/"TRANSCRIPT.md").write_text("\n".join(lines),encoding="utf-8")
    print(canonical_json(dict(requests=len(attempts),old_audit_used=old_counts[1],evidence_digest=value["evidence_digest"])))


if __name__=="__main__":main()
