"""Six fixed first-only choice cells. Synthetic sources; no diagnostic Publication."""
import argparse,json,sys
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'src'))
import run_s148_choice_comparison as evidence
from run_s150_local_feedback import PACKAGE,history,plain
from run_s155_long_continuity import command_for
from serve_natural_feedback_chat import NaturalFeedbackChatEntry
from dynamic_subject_agent.deepseek import DeepSeekTransport,DeepSeekHttpResponse,DEEPSEEK_CREDENTIAL_BACKEND_ID,DEEPSEEK_CREDENTIAL_KEY_ID
from dynamic_subject_agent.cognition import CredentialRef
from dynamic_subject_agent.model_gateway import ModelTask,ModelTaskKind,ModelGateway,ModelGatewayFailure
from dynamic_subject_agent.shared_activity import SharedExperienceRequest,SharedActivityStepRequest,digest
from dynamic_subject_agent.natural_feedback_live import APPROVED_FEEDBACK_REVIEW,NaturalFeedbackDelivery,open_natural_feedback_audit,feedback_live_contract_for_variant
from dynamic_subject_agent.natural_feedback_multispan import NaturalFeedbackMultispanDevelopmentGrant,MULTISPAN_DEVELOPMENT
from dynamic_subject_agent.natural_feedback_choice_budget import NaturalFeedbackChoiceBudgetGrant,CHOICE_DEVELOPMENT
from dynamic_subject_agent.natural_feedback_provider import DeepSeekNaturalFeedbackAdapter
from dynamic_subject_agent.natural_feedback_remote_preview import natural_feedback_remote_request_preview
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
from dynamic_subject_agent.frozen_attempt import canonical_json

ROOT=REPO/'.artifacts/s157/six-first-live'
DIAGNOSTIC=REPO/'docs/experiments/s157/DIAGNOSTIC.md'
ORDER=(('A','high'),('A','low'),('A','final'),('B','final'),('B','low'),('B','high'))
VARIANTS={'high':'multi-span','low':'choice-low','final':'choice-final'}
SOURCES={'A':'做一间原创旧地图店‘云匣’的未成图文字构图。你自行选择人物、物件、镜头、光线；分工作台、店内、门外三段，各有具体安排和你自己的关注。',
 'B':'做原创山地茶棚‘弦屋’的未成图文字构图。自己选择主体和摆放，关注短暂停留与物件使用痕迹。'}
FEEDBACK='这版把所有‘弦屋’换成‘弦湾’，其他照旧。'
SEED_PLAN=dict(subject='原创少女在弦屋桌边整理旧地图',
 composition='平视中景，左侧小窗的暖灰反照光。弦屋的矮桌上摊开折过边的旧地图，少女正压住纸角，右侧木箱留出通往远处的视线。弦屋窗外细雨停了，地面有一条浅亮反光。',
 focus='弦屋里人的短暂停留与物件痕迹')

def require(ok,code):
    if not ok:raise RuntimeError(code)

def save(value):evidence.save(ROOT/'metadata.json',value)

def grant(mode):
    return NaturalFeedbackMultispanDevelopmentGrant(APPROVED_FEEDBACK_REVIEW,MULTISPAN_DEVELOPMENT) if mode=='high' else NaturalFeedbackChoiceBudgetGrant(APPROVED_FEEDBACK_REVIEW,CHOICE_DEVELOPMENT,VARIANTS[mode])

def pins():
    files=['scripts/run_s157_choice_diagnostic.py','scripts/run_s148_choice_comparison.py','scripts/serve_natural_feedback_chat.py',
        *('src/dynamic_subject_agent/'+name+'.py' for name in ('natural_feedback_choice_budget','natural_feedback_budget','natural_feedback_live',
            'natural_feedback_remote_preview','natural_feedback_provider','natural_feedback_multispan','natural_feedback_frame','natural_feedback',
            'shared_activity','shared_activity_cognition','local_product','local_identity_authority','original_whole_chat','application','timeline','studio'))]
    return dict(diagnostic_sha256=sha256(DIAGNOSTIC.read_bytes()).hexdigest(),files={f:sha256((REPO/f).read_bytes()).hexdigest() for f in files})

def source_stamp(name):
    folder=ROOT/'sources'/name
    return {str(p.relative_to(folder)):sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}

def verify_manifest():
    m=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'));r=json.loads((ROOT/'metadata.json').read_text(encoding='utf-8'))
    ready=json.loads((ROOT/'readiness-final.json').read_text(encoding='utf-8'))
    require(digest(m)==r['manifest_sha256'] and ready['manifest_sha256']==r['manifest_sha256'] and ready['pins']==pins(),'frozen-six-cell-input-or-code-changed')
    require(tuple(tuple(x) for x in m['order'])==ORDER,'fixed-six-cell-order-required')
    for name in ('A','B'):require(source_stamp(name)==m['source_stamps'][name],'canonical-source-or-permission-changed')
    return m,r

def seal():
    m=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'));r=json.loads((ROOT/'metadata.json').read_text(encoding='utf-8'))
    require(r['status']=='prepared' and not r['cells'] and not r['calls'] and digest(m)==r['manifest_sha256'],'only-zero-call-preparation-can-be-sealed')
    current=pins();require(m['pins']['diagnostic_sha256']==current['diagnostic_sha256'],'frozen-material-changed')
    require(all(current['files'][name]==h for name,h in m['pins']['files'].items() if name!='scripts/run_s157_choice_diagnostic.py'),'execution-source-changed-after-preparation')
    for name in ('A','B'):require(source_stamp(name)==m['source_stamps'][name],'source-changed-before-final-readiness')
    require(not (ROOT/'readiness-final.json').exists(),'first-final-readiness-preserved')
    evidence.save(ROOT/'readiness-final.json',dict(status='ready-zero-call',manifest_sha256=r['manifest_sha256'],pins=current,requests=0))
    print(canonical_json(dict(status='sealed-first-readiness',requests=0)),flush=True)

class SyntheticSeedTransport(DeepSeekTransport):
    def __init__(self):self.calls=[]
    def post_json(self,**kwargs):
        body=json.loads(kwargs['body']);self.calls.append(body);p=json.loads(body['messages'][1]['content'])
        if 'current_activity' in p:
            value=dict(action='start',plan=SEED_PLAN,reason_code='try-alternative',basis_refs=['E1'],decision_note='本机合成诊断种子，并非人物模型选择。')
        else:
            value=dict(intent='revise' if p['turn']['current_message']==FEEDBACK else 'chat',reply_text='本机诊断种子回应，不是人物模型输出。')
        return DeepSeekHttpResponse(200,canonical_json(dict(model='deepseek-flash',choices=[dict(finish_reason='stop',message=dict(role='assistant',content=canonical_json(value)))],
            usage=dict(prompt_tokens=100,completion_tokens=20,total_tokens=120))).encode())

def prepare():
    require(not ROOT.exists(),'first-six-directory-preserved-no-recreation')
    ROOT.mkdir(parents=True,exist_ok=False)
    report=dict(status='preparing-synthetic-sources',calls=[],cells=[],credential_read_attempts=0,automatic_retries=0,source_seed_mode='explicit-local-synthetic-not-person-experience')
    save(report);previews={};states={};seed_counts={}
    for name in ('A','B'):
        transport=SyntheticSeedTransport();entry=NaturalFeedbackChatEntry(ROOT/'sources'/name/'entry',live=False,package_path=PACKAGE,transport=transport,audit_path=ROOT/'sources'/name/'seed-audit')
        with entry.product as product:
            cmd=command_for(product,SOURCES[name]);result=product.application.submit(cmd,idempotency_key='s157-local-seed-'+name)
            while result.status=='pending':result=product.application.wait(result.operation_ref,timeout_seconds=30)
            require(result.status=='terminal','synthetic-source-not-committed')
            row=plain(history(product))[-1];view=plain(product.application.query_shared_activity().view)
            selected=product.application.set_shared_experience(SharedExperienceRequest(product.profile_id,product.timeline_id,'s157-local-select-'+name,
                view['revision'],row['head_sequence'],SOURCES[name],True))
            require(selected.status=='committed','synthetic-E1-not-selected')
            if name=='B':
                v=plain(product.application.query_shared_activity().view)
                require(product.application.advance_shared_activity(SharedActivityStepRequest(product.profile_id,product.timeline_id,'s157-local-plan-B',v['revision'])).status=='committed','synthetic-plan-not-prepared')
                result=product.application.submit(command_for(product,FEEDBACK),idempotency_key='s157-local-feedback-B')
                while result.status=='pending':result=product.application.wait(result.operation_ref,timeout_seconds=30)
                require(result.status=='terminal','synthetic-F1-not-prepared')
                require(plain(product.application.query_shared_activity().view)['current_plan']=={k:v.replace('弦屋','弦湾') for k,v in SEED_PLAN.items()},'synthetic-frame-not-exact')
            preview=product.application.preview_shared_activity_step();require(preview.status=='previewed','actual-Facade-preview-required')
            previews[name]=plain(preview.view);states[name]=str(entry.config.state_path);seed_counts[name]=len(transport.calls)
        entry.close()
    manifest=dict(version='s157-choice-six-first-1',pins=pins(),order=ORDER,previews=previews,states=states,
        source_stamps={name:source_stamp(name) for name in ('A','B')},source_seed_fake_calls=seed_counts,source_seed_real_calls=0,source_seed_credential_reads=0)
    for name in ('A','B'):
        bodies=[natural_feedback_remote_request_preview(ModelTask(ModelTaskKind.SHARED_ACTIVITY_CHOICE,previews[name]),technical_variant=VARIANTS[mode])['body'] for mode in ('high','low','final')]
        require(all(b['messages']==bodies[0]['messages'] and b['max_tokens']==4096 for b in bodies),'single-mode-variable-only')
    report.update(status='prepared',manifest_sha256=digest(manifest),source_seed_fake_calls=seed_counts,source_seed_real_calls=0,source_seed_publications=dict(A=2,B=4))
    evidence.save(ROOT/'manifest.json',manifest);save(report)
    print(canonical_json(dict(status=report['status'],planned_first_cells=6,source_seed_fake_calls=seed_counts,remote_calls=0,credential_reads=0)),flush=True)

def run():
    manifest,report=verify_manifest()
    require(report['status']=='prepared' and not report['cells'] and not report['calls'],'reserved-or-terminal-six-cells-never-resend')
    report['status']='diagnostic-started';save(report);transport=evidence.CapturingTransport(report)
    for name,mode in ORDER:
        label=name+'-'+mode;variant=VARIANTS[mode]
        row=dict(label=label,status='reserved',purpose=ModelTaskKind.SHARED_ACTIVITY_CHOICE.value);report['cells'].append(row);save(report)
        task=ModelTask(ModelTaskKind.SHARED_ACTIVITY_CHOICE,manifest['previews'][name])
        path=ROOT/'audits'/mode/'audit';audit=open_natural_feedback_audit(path,initialize=not path.exists(),technical_variant=variant)
        delivery=NaturalFeedbackDelivery(grant=grant(mode),audit=audit,contract=feedback_live_contract_for_variant(APPROVED_BINDING,variant),state_path=Path(manifest['states'][name]))
        observations=[]
        adapter=DeepSeekNaturalFeedbackAdapter(transport=transport,delivery=delivery,observations=observations,
            credential_ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,key_id=DEEPSEEK_CREDENTIAL_KEY_ID))
        def rebuild():return verify_manifest()[0]['previews'][name]
        wire=natural_feedback_remote_request_preview(task,technical_variant=variant)
        evidence.save(ROOT/'previews'/(label+'.json'),dict(preview=task.payload,wire=wire))
        delivery.claim('s157-first-cell:'+label,task,rebuild)
        before=transport.total;transport.arm(label,canonical_json(wire['body']).encode());transport.expected['purpose']=task.kind.value
        try:row.update(status='complete',value=ModelGateway(adapter).execute(task).value)
        except ModelGatewayFailure as error:row.update(status='failed',failure_code=error.code)
        row.update(requests=transport.total-before,observations=observations);save(report)
        require(row['requests']==1,'one-first-request-per-cell-required');verify_manifest()
        print(canonical_json(dict(cell=label,status=row['status'],requests=1,finish_reason=observations[-1].get('finish_reason'),
            completion_tokens=(observations[-1].get('usage') or {}).get('completion_tokens'),reasoning_tokens=observations[-1].get('reasoning_tokens'),final_chars=observations[-1].get('final_chars'))),flush=True)
        output_failures={'response-truncated','response-content-empty','response-content-json','response-envelope','structured-choice-invalid'}
        if observations[-1]['status'] in ('unknown','unavailable') or (row['status']=='failed' and row.get('failure_code') not in output_failures):
            report.update(status='six-cell-blocked',not_executed=[a+'-'+b for a,b in ORDER[len(report['cells']):]]);save(report);return
    report.update(status='fixed-six-cells-complete',source_unchanged=True,diagnostic_publications=0,person_publications=0);save(report)
    print(canonical_json(dict(status=report['status'],first_requests=transport.total,retries=0,diagnostic_publications=0)),flush=True)

def final_bindings(report):
    result={}
    for index,c in enumerate(report['cells']):
        path=ROOT/'finals'/(c['label']+'.json')
        if path.exists():result[c['label']]=dict(status='available',file_sha256=sha256(path.read_bytes()).hexdigest())
        else:
            call=report['calls'][index]
            require(c['status']=='failed' and call.get('final_sha256') is None and c['observations'][-1].get('final_chars') in (None,0),
                'first-final-evidence-missing')
            result[c['label']]=dict(status='unavailable',response_sha256=call.get('response_sha256'),failure_code=c.get('failure_code'))
    return result

def evaluate(scores,note):
    manifest,report=verify_manifest();require(report['status']=='fixed-six-cells-complete','all-six-first-terminals-required')
    labels=[a+'-'+b for a,b in ORDER]
    require(type(scores) is dict and set(scores)==set(labels) and all(type(s) is int and s in (0,1,2) for s in scores.values()) and type(note) is str and 0<len(note)<=3000,'six-bounded-human-scores-required')
    require(not (ROOT/'eligibility.json').exists(),'first-verdict-never-overwritten')
    eligible=[];costs={}
    for mode in ('low','final'):
        rows=[c for c in report['cells'] if c['label'].endswith('-'+mode)]
        technical=len(rows)==2 and all(c['status']=='complete' and c['requests']==1 and c['observations'][-1]['finish_reason']=='stop' and c['observations'][-1]['final_chars']>0 for c in rows)
        if technical and all(scores[c['label']]==2 for c in rows):eligible.append(mode)
        used=[(c['observations'][-1].get('usage') or {}).get('completion_tokens') for c in rows]
        costs[mode]=sum(used) if all(type(x) is int and x>=0 for x in used) else None
    selected=min(eligible,key=lambda mode:(costs[mode] is None,costs[mode] if costs[mode] is not None else 0,mode!='low')) if eligible else None
    verdict=dict(status='eligible' if selected else 'not-eligible',selected_mode=selected,selected_variant=VARIANTS[selected] if selected else None,
        eligible_modes=eligible,completion_totals=costs,semantic_scores=scores,note=note,manifest_sha256=report['manifest_sha256'],
        metadata_sha256=sha256((ROOT/'metadata.json').read_bytes()).hexdigest(),readiness_sha256=sha256((ROOT/'readiness-final.json').read_bytes()).hexdigest(),
        first_final_bindings=final_bindings(report))
    evidence.save(ROOT/'eligibility.json',verdict);print(canonical_json(dict(status=verdict['status'],selected_variant=verdict['selected_variant'],requests=0)),flush=True)

def eligible_variant():
    manifest,report=verify_manifest();v=json.loads((ROOT/'eligibility.json').read_text(encoding='utf-8'))
    require(v['status']=='eligible' and report['status']=='fixed-six-cells-complete' and v['selected_variant'] in ('choice-low','choice-final'),'selected-six-cell-candidate-required')
    require(v['manifest_sha256']==report['manifest_sha256'] and v['metadata_sha256']==sha256((ROOT/'metadata.json').read_bytes()).hexdigest(),'eligibility-basis-changed')
    require(v['readiness_sha256']==sha256((ROOT/'readiness-final.json').read_bytes()).hexdigest(),'eligibility-readiness-changed')
    require(v['first_final_bindings']==final_bindings(report),'first-finals-changed-after-verdict')
    mode=v['selected_mode'];rows=[c for c in report['cells'] if c['label'].endswith('-'+mode)]
    require(len(rows)==2 and all(c['status']=='complete' and c['observations'][-1]['finish_reason']=='stop' and c['observations'][-1]['final_chars']>0 and v['semantic_scores'][c['label']]==2 for c in rows),'candidate-must-pass-both-inputs')
    require(VARIANTS[mode]==v['selected_variant'],'exact-selected-mode-required')
    return v['selected_variant']

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('prepare','seal','run','evaluate','eligible'));parser.add_argument('--scores');parser.add_argument('--note');args=parser.parse_args(argv)
    evidence.ROOT=ROOT
    if args.mode=='prepare':prepare()
    elif args.mode=='seal':seal()
    elif args.mode=='run':run()
    elif args.mode=='evaluate':evaluate(json.loads(args.scores),args.note)
    else:print(canonical_json(dict(status='eligible-verified',selected_variant=eligible_variant(),requests=0)))
    return 0
if __name__=='__main__':raise SystemExit(main())
