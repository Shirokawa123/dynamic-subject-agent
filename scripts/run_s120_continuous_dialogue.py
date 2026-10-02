"""Two same-seed A chains, each continuing only its own canonical replies."""
from dataclasses import asdict
import json
import os
from pathlib import Path
from uuid import uuid4

from dynamic_subject_agent.first_life_free_input_trial import open_free_input_reply_trial,fixed_free_input_runs_root
from dynamic_subject_agent.local_product import open_first_life_free_input_trial
from dynamic_subject_agent.model_gateway import ModelGateway
from dynamic_subject_agent.frozen_attempt import canonical_json
from run_s112_reply_comparison import (SCENARIOS_PATH,prepare_branch,SeedAdapter,seed_branch,read_history,send)


MESSAGES=(
    "今天先聊点新的吧：圆形和方形，哪个更容易让你想到安静？",
    "接着你刚才的选择，举个小例子吧。",
    "你平时会给自己定很硬的目标吗？",
    "你开头那条近况说右边空了，但当前文字构图里书一直在。你想怎么说明？",
    "刚才已经说清书仍在，我只是确认。现在接着聊你更想尝试的构图选择吧。",
)


def run(variant,*,live,root=None,transport=None):
    root=root or fixed_free_input_runs_root()/str(uuid4())
    trial=open_free_input_reply_trial(root,SCENARIOS_PATH,live=live,confirmed=True,expression_variant=variant)
    scenario=trial.scenarios["scenarios"][0]
    branch_id=scenario["id"]+"-A"
    branch=prepare_branch(root/branch_id,trial.scenarios)
    def opening(seed_gateway=None):
        return open_first_life_free_input_trial(branch.config,approval=trial,branch_id=branch_id,
            definition_basis=branch.definition_basis,life_scope_digest=branch.life_scope_digest,
            seed_gateway=seed_gateway,_transport=None if seed_gateway else transport)
    seed_adapter=SeedAdapter(trial.scenarios,scenario)
    with opening(ModelGateway(seed_adapter)) as product:
        seed=seed_branch(product,seed_adapter)
    steps=[];product=opening()
    path=root/"s120-dialogue.jsonl"
    with path.open("x",encoding="utf-8") as journal:
        def append(row):
            journal.write(canonical_json(row)+"\n");journal.flush();os.fsync(journal.fileno())
        append(dict(event="started",variant=variant,root=str(root),run_digest=trial.manifest_digest,seed_source_digest=seed["source_digest"]))
        try:
            for number,text in enumerate(MESSAGES,1):
                if number==5:
                    previous=read_history(product);before=len(trial.observations)
                    product.close();product=opening()
                    assert read_history(product)==previous and len(trial.observations)==before
                    append(dict(event="reopened",before_step=number,history_equal=True,additional_model_calls=0))
                before=len(trial.observations)
                append(dict(event="step-started",number=number,user_text=text))
                response=send(product,text,f"s120-owned-dialogue-step-{number}")
                value=dict(number=number,user_text=text,status=response.status.value,
                    failure_code=getattr(response.projection,"failure_code",None),problem_code=getattr(response.problem,"code",None),
                    assistant_text=getattr(response.projection,"expression_text",None),observations=trial.observations[before:],
                    canonical_history=[asdict(row) for row in read_history(product)])
                steps.append(value);append(dict(event="step-finished",**value))
                if response.status.value!="terminal":break
            summary=dict(version="s120-owned-continuous-1",variant=variant,root=str(root),run_digest=trial.manifest_digest,
                seed_source_digest=seed["source_digest"],steps=steps,actual_attempts=len(trial.observations),
                status="completed" if len(steps)==len(MESSAGES) and all(r["status"]=="terminal" for r in steps) else "stopped-failure",
                automatic_retries=0,private_user_content_exported=False)
            append(dict(event="finished",status=summary["status"],actual_attempts=summary["actual_attempts"]))
            (root/"s120-dialogue-summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        finally:product.close()
    return summary


def main():
    results=[]
    for variant in ("baseline","current-topic"):
        root=fixed_free_input_runs_root()/str(uuid4())
        print(canonical_json(dict(started_run=str(root),variant=variant)),flush=True)
        summary=run(variant,live=True,root=root)
        print(canonical_json(dict(root=str(root),variant=variant,status=summary["status"],actual_attempts=summary["actual_attempts"])),flush=True)
        results.append(summary)
    if results[0]["steps"] and results[1]["steps"]:
        first=[r["steps"][0]["observations"][0]["request_digest"] for r in results]
        assert first[0]==first[1],"same initial material required"
    return 0 if all(r["status"]=="completed" for r in results) else 1


if __name__=="__main__":raise SystemExit(main())
