"""Fixed four new-input protocol cells, no Timeline proposals are published."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'src'))
import run_s148_choice_comparison as evidence
from dynamic_subject_agent.local_product import LocalProductConfig,open_natural_feedback_product_live
from dynamic_subject_agent.natural_feedback_live import (
    ApprovedNaturalFeedbackGrant,APPROVED_FEEDBACK_REVIEW,NaturalFeedbackDelivery,open_natural_feedback_audit,
    feedback_live_contract_for_variant)
from dynamic_subject_agent.natural_feedback_budget import NaturalFeedbackBudgetDevelopmentGrant,BUDGET_DEVELOPMENT
from dynamic_subject_agent.natural_feedback_provider import DeepSeekNaturalFeedbackAdapter
from dynamic_subject_agent.natural_feedback_remote_preview import natural_feedback_remote_request_preview
from dynamic_subject_agent.model_gateway import ModelTask,ModelTaskKind,ModelGateway,ModelGatewayFailure
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
from dynamic_subject_agent.cognition import CredentialRef
from dynamic_subject_agent.deepseek import DEEPSEEK_CREDENTIAL_BACKEND_ID,DEEPSEEK_CREDENTIAL_KEY_ID
from dynamic_subject_agent.shared_activity import digest
from dynamic_subject_agent.frozen_attempt import canonical_json

ROOT=REPO/'.artifacts/s151/four-cell-first'
SOURCE=REPO/'.artifacts/s150/real-first'
MESSAGES=dict(A='这份配色如果要印成明信片，你觉得要注意什么？只谈目前想法，不修改方案。',
    B='请把远景列车灯的暖白改成偏中性的白，其他安排照旧。')
ORDER=(('A','baseline'),('A','direct-final'),('B','direct-final'),('B','baseline'))

def require(ok,code):
    if not ok:raise RuntimeError(code)

def stamp(paths):
    result={name:sha256(Path(path).read_bytes()).hexdigest() for name,path in paths.items()}
    wal=Path(paths['canonical']+'-wal')
    result['wal']=sha256(wal.read_bytes()).hexdigest() if wal.exists() else None
    return result

def prepare():
    require(not ROOT.exists(),'first-diagnostic-directory-preserved-no-repeat')
    ROOT.mkdir(parents=True,exist_ok=False)
    report=dict(status='preparing',calls=[],cells=[],credential_read_attempts=0,automatic_retries=0,
        runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    evidence.save(ROOT/'metadata.json',report)
    previous=json.loads((SOURCE/'metadata.json').read_text(encoding='utf-8'))
    require(previous['status']=='first-stage-failed' and previous['review_basis']==APPROVED_FEEDBACK_REVIEW,'exact-preserved-S150-source-required')
    config=LocalProductConfig(SOURCE/'entry/DynamicSubjectAgent/m0/experiments',SOURCE/'entry/state.json')
    blocked=evidence.CapturingTransport(report,blocked=True)
    previews={}
    with open_natural_feedback_product_live(config,identity_id=previous['identity_id'],
        grant=ApprovedNaturalFeedbackGrant(APPROVED_FEEDBACK_REVIEW,True),audit_path=SOURCE/'audit',_transport=blocked) as product:
        require((product.profile_id,product.timeline_id)==(previous['profile_id'],previous['timeline_id']),'original-source-scope-required')
        for name,message in MESSAGES.items():
            r=product.application.preview_natural_feedback(message)
            require(r.status=='previewed','new-message-canonical-preview-unavailable')
            previews[name]=evidence.plain(r.view)
        binding=product._composition._host.query_binding(profile_id=product.profile_id,timeline_id=product.timeline_id)
        paths=dict(state=str(config.state_path),canonical=str(binding.timeline_root.timeline_database))
        require(blocked.total==0,'preparation-must-not-send')
    manifest=dict(version='s151-four-cell-budget-diagnostic-1',source_paths=paths,source_stamp=stamp(paths),
        runner_sha256=report['runner_sha256'],order=ORDER,previews=previews,review_basis=APPROVED_FEEDBACK_REVIEW,
        plan=previews['A']['payload']['current_plan'])
    report.update(status='prepared',manifest_sha256=digest(manifest))
    evidence.save(ROOT/'manifest.json',manifest);evidence.save(ROOT/'metadata.json',report)
    print(canonical_json(dict(status='prepared',new_inputs=2,planned_first_cells=4,source_model_requests=0)),flush=True)

def run():
    manifest=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
    report=json.loads((ROOT/'metadata.json').read_text(encoding='utf-8'))
    require(report['status']=='prepared' and not report['cells'] and not report['calls'],'reserved-or-terminal-diagnostic-cannot-repeat')
    require(digest(manifest)==report['manifest_sha256'] and manifest['runner_sha256']==sha256(Path(__file__).read_bytes()).hexdigest(),'frozen-diagnostic-required')
    require(stamp(manifest['source_paths'])==manifest['source_stamp'],'source-or-permission-changed')
    report['status']='diagnostic-started';evidence.save(ROOT/'metadata.json',report)
    transport=evidence.CapturingTransport(report)
    for name,variant in ORDER:
        label=name+'-'+variant
        row=dict(label=label,status='reserved',purpose=ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK.value)
        report['cells'].append(row);evidence.save(ROOT/'metadata.json',report)
        preview=manifest['previews'][name]
        task=ModelTask(ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK,preview)
        grant=(ApprovedNaturalFeedbackGrant(APPROVED_FEEDBACK_REVIEW,True) if variant=='baseline'
            else NaturalFeedbackBudgetDevelopmentGrant(APPROVED_FEEDBACK_REVIEW,BUDGET_DEVELOPMENT))
        audit=open_natural_feedback_audit(ROOT/variant/'audit',initialize=True if not (ROOT/variant/'audit').exists() else False,technical_variant=variant)
        delivery=NaturalFeedbackDelivery(grant=grant,audit=audit,contract=feedback_live_contract_for_variant(APPROVED_BINDING,variant),
            state_path=Path(manifest['source_paths']['state']))
        observations=[]
        adapter=DeepSeekNaturalFeedbackAdapter(transport=transport,delivery=delivery,
            credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,key_id=DEEPSEEK_CREDENTIAL_KEY_ID),observations=observations)
        def rebuild():
            fresh=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
            require(digest(fresh)==report['manifest_sha256'] and stamp(fresh['source_paths'])==fresh['source_stamp'],'frozen-source-changed-before-delivery')
            return fresh['previews'][name]
        wire=natural_feedback_remote_request_preview(task,technical_variant=variant)
        evidence.save(ROOT/'previews'/(label+'.json'),dict(preview=preview,wire=wire))
        delivery.claim('s151-fixed-cell:'+label,task,rebuild)
        before=transport.total
        transport.arm(label,canonical_json(wire['body']).encode());transport.expected['purpose']=task.kind.value
        try:
            value=ModelGateway(adapter).execute(task).value
            row.update(status='complete',value=value)
        except ModelGatewayFailure as error:
            row.update(status='failed',failure_code=error.code)
        row.update(requests=transport.total-before,observations=observations)
        require(row['requests']==1,'each-diagnostic-cell-exactly-one')
        require(stamp(manifest['source_paths'])==manifest['source_stamp'],'diagnostic-must-not-modify-source')
        evidence.save(ROOT/'metadata.json',report)
        print(canonical_json(dict(cell=label,status=row['status'],requests=1,finish_reason=observations[-1].get('finish_reason'),
            reasoning_tokens=observations[-1].get('reasoning_tokens'),completion_tokens=observations[-1].get('usage',{}).get('completion_tokens'),
            final_chars=observations[-1].get('final_chars'))),flush=True)
    report.update(status='fixed-four-cells-complete',source_unchanged=True,product_publications=0)
    evidence.save(ROOT/'metadata.json',report)
    print(canonical_json(dict(status=report['status'],requests=transport.total,retries=0,publications=0)),flush=True)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','run','evaluate'))
    p.add_argument('--score-a',type=int);p.add_argument('--score-b',type=int);p.add_argument('--note');args=p.parse_args(argv)
    evidence.ROOT=ROOT
    if args.mode=='prepare':prepare()
    elif args.mode=='run':run()
    else:
        report=json.loads((ROOT/'metadata.json').read_text(encoding='utf-8'))
        require(report['status']=='fixed-four-cells-complete','all-first-diagnostic-results-required')
        require(args.score_a in (0,1,2) and args.score_b in (0,1,2) and args.note and len(args.note)<=2000,'bounded-human-semantic-verdict-required')
        require(not (ROOT/'eligibility.json').exists(),'first-eligibility-verdict-preserved')
        direct=[c for c in report['cells'] if c['label'].endswith('direct-final')]
        technical=len(direct)==2 and all(c['status']=='complete' and c['requests']==1
            and c['observations'][-1]['finish_reason']=='stop' and c['observations'][-1]['final_chars']>0 for c in direct)
        verdict=dict(status='eligible' if technical and args.score_a==2 and args.score_b==2 else 'not-eligible',
            semantic_scores=dict(A=args.score_a,B=args.score_b),note=args.note,
            manifest_sha256=report['manifest_sha256'],metadata_sha256=sha256((ROOT/'metadata.json').read_bytes()).hexdigest(),
            final_sha256={c['label']:sha256((ROOT/'finals'/(c['label']+'.json')).read_bytes()).hexdigest() for c in direct})
        evidence.save(ROOT/'eligibility.json',verdict);print(canonical_json(dict(status=verdict['status'],requests=0)),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
