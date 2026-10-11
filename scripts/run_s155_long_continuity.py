"""Frozen S155 multi-span local-frame first space scene, one next stage per invocation, zero retries.

First finals remain local. An interrupted/reserved attempt only permits inspect;
it cannot resend. Opening/reopening never arms transport. No server is started.
"""
import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'src'))
import run_s148_choice_comparison as evidence
from run_s150_local_feedback import PACKAGE, history, plain
from dynamic_subject_agent.application import ApplicationFacade, SubjectRequestLookupRequest
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product, open_natural_feedback_product_live
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
from dynamic_subject_agent.original_whole_use_preparation import OriginalWholeUsePreparationRequest
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
from dynamic_subject_agent.shared_activity import SharedActivityStepRequest, SharedExperienceRequest, digest
from dynamic_subject_agent.timeline import SubjectCommand
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
from dynamic_subject_agent.natural_feedback_live import APPROVED_FEEDBACK_REVIEW, open_natural_feedback_audit
from dynamic_subject_agent.natural_feedback_multispan import NaturalFeedbackMultispanDevelopmentGrant,MULTISPAN_DEVELOPMENT,multispan_proposal
from serve_natural_feedback_chat import NaturalFeedbackChatEntry
from dynamic_subject_agent.natural_feedback_frame import requested_frame
from dynamic_subject_agent.natural_feedback_multispan import construct_multispan_edits
from dynamic_subject_agent.first_life import validate_plan
from dynamic_subject_agent.natural_feedback_remote_preview import natural_feedback_remote_request_preview
from dynamic_subject_agent.frozen_attempt import canonical_json

ROOT=REPO/'.artifacts/s155/long-first'
SCENE=REPO/'docs/experiments/s155/SCENE.md'
REVIEW=REPO/'docs/experiments/s150/review.json'
STAGES=(('initial-source', '先做一版原创亭子‘汀舍’的文字构图。按你的关注自行选人物、物件、镜头和光线；从前景、中景到远景各写一段完整的安排，每段都沿用‘汀舍’这个地点名。最后再说明你最看重什么。这只是未成图的文字方案。'), ('initial-activity', None), ('natural-reference', '那三个地方提到的名字，能换个叫法吗？其他先别动。'), ('natural-correction', '这版把所有‘汀舍’换成‘栖舍’，其他照旧。'), ('conditional-feedback', '要是以后另做清晨版，我可能会想让远景淡一点；现在这版先别改。'), ('topic-gap-1', '一个镜头先停在空椅子上，你现在会想看到谁坐下？'), ('topic-gap-2', '虚构故事把一段对白藏在信封背面，你会想先看信还是先看背面？'), ('topic-gap-3', '同一个人停在两扇门之间，你会想画他抬脚还是回头？'), ('post-gap-activity', None), ('current-result-reply', '现在这一版的地点叫什么，前后景怎样安排？你最在意哪个取舍？'))


def require(condition,code):
    if not condition:raise RuntimeError(code)


def pins():
    return dict(runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        capture_helper_sha256=sha256((REPO/'scripts/run_s148_choice_comparison.py').read_bytes()).hexdigest(),
        scene_sha256=sha256(SCENE.read_bytes()).hexdigest(),review_sha256=sha256(REVIEW.read_bytes()).hexdigest(),
        execution_sources={name:sha256((REPO/name).read_bytes()).hexdigest() for name in (
            'scripts/run_s150_local_feedback.py','scripts/serve_natural_feedback_chat.py',
            *('src/dynamic_subject_agent/'+name for name in ('natural_feedback.py','natural_feedback_live.py',
                'natural_feedback_provider.py','natural_feedback_budget.py','natural_feedback_frame.py','natural_feedback_scoped.py','natural_feedback_intent.py','natural_feedback_multispan.py','natural_feedback_output_metadata.py','natural_feedback_remote_preview.py','shared_activity.py',
                'shared_activity_cognition.py','local_product.py','local_identity_authority.py','host.py',
                'timeline.py','studio.py','application.py','original_whole_chat.py','model_gateway.py')))})


def verified_review():
    value=json.loads(REVIEW.read_text(encoding='utf-8'));basis=value.pop('review_basis')
    require(basis==APPROVED_FEEDBACK_REVIEW and digest(value)==basis,'exact-approved-review-required')
    require(pins()['scene_sha256']=='4efa28ac0f7d2450adcdde238d6c85b2e1c6da749b947685047e6e5b9f4dd9c8','frozen-new-scene-changed')
    NaturalFeedbackMultispanDevelopmentGrant(basis,MULTISPAN_DEVELOPMENT).validate()
    return value


def save(report):evidence.save(ROOT/'metadata.json',report)




def view(product):
    response=product.application.query_shared_activity()
    require(response.status=='available','canonical-activity-unverified')
    return plain(response.view)


def command_for(product,text):
    return SubjectCommand.contribute_utterance(target_profile_id=product.profile_id,target_timeline_id=product.timeline_id,
        declared_intent='ask-collaborator-status',utterance=text,language='zh',provenance='project-original')


def opening(report,transport):
    entry=NaturalFeedbackChatEntry(ROOT/'entry',live=False,package_path=PACKAGE,transport=transport,audit_path=ROOT/'audit',observations=report['provider_observations'])
    product=entry.product
    if report.get('timeline_id'):
        require((product.profile_id,product.timeline_id)==(report['profile_id'],report['timeline_id']),'same-identity-timeline-required')
    return product


def initialize():
    require(not ROOT.exists(),'first-scene-must-not-be-recreated')
    ROOT.mkdir(parents=True,exist_ok=False)
    report=dict(status='initializing',next_stage=0,calls=[],stages=[],credential_read_attempts=0,automatic_retries=0,
        review_basis=APPROVED_FEEDBACK_REVIEW,pins=pins(),human_content_reviews={},provider_observations=[])
    save(report)
    transport=evidence.CapturingTransport(report,blocked=True)
    with opening(report,transport) as product:
        report.update(identity_id=product.profile_id,profile_id=product.profile_id,timeline_id=product.timeline_id,status='ready')
        require(not history(product) and not transport.total and not open_natural_feedback_audit(ROOT/'audit',technical_variant='multi-span').snapshot(),'new-opening-must-be-empty-zero-model')
    save(report)
    return report


def audit():return list(open_natural_feedback_audit(ROOT/'audit',technical_variant='multi-span').snapshot())


def inspect(report):
    transport=evidence.CapturingTransport(report,blocked=True)
    with opening(report,transport) as product:
        current=product.application.query_shared_activity()
        report['readonly_inspection']=dict(status=plain(current.status),view=plain(current.view),audit=audit(),requests=0)
        if report['stages'] and report['stages'][-1]['status'] in ('started','pending'):
            row=report['stages'][-1]; index=row['index']; text=STAGES[index][1]
            if text is not None:
                lookup=product.application.lookup_subject_request(SubjectRequestLookupRequest(command_for(product,text),row['nonce']))
            else:
                lookup=product.application.query_shared_activity(SharedActivityStepRequest(product.profile_id,product.timeline_id,row['nonce'],row['expected_revision']))
            report['readonly_inspection']['original_nonce']=plain(lookup)
        require(not transport.total,'inspection-must-never-send')
    save(report)
    print(canonical_json(dict(status=report['status'],audit_attempts=len(audit()),inspection=report['readonly_inspection']['status'],requests=0)),flush=True)


def next_stage(report):
    require(report['status']=='ready','terminal-or-reserved-first-attempt-cannot-resend')
    index=report['next_stage'];require(type(index) is int and 0<=index<10,'fixed-ten-stage-bound')
    if index==2:
        require(report['human_content_reviews'].get('long',{}).get('score')==2,'object-content-must-be-reviewed-before-correction')
    label,text=STAGES[index];transport=evidence.CapturingTransport(report)
    product=None
    result_code=0
    try:
        product=opening(report,transport);before=view(product);previous=plain(history(product));audited=len(audit())
        if index==8:
            preview=product.application.preview_natural_feedback('只核当前接话范围。')
            require(preview.status=='previewed','topic-window-preview-unavailable')
            recent=canonical_json(preview.view['payload']['exchange'])
            require(STAGES[2][1] not in recent and STAGES[3][1] not in recent and STAGES[4][1] not in recent,'feedback-must-leave-recent-window')
            product.close();product=None
            product=opening(report,transport)
            require(before==view(product) and previous==plain(history(product)) and not transport.total,'actual-reopen-zero-same-state')
            report['actual_reopen_after_gap']=dict(requests=0,same_identity=True,same_state=True,feedback_outside_recent=True);save(report)
        kind=ModelTaskKind.SHARED_ACTIVITY_CHOICE if text is None else ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK
        preview=product.application.preview_shared_activity_step() if text is None else product.application.preview_natural_feedback(text)
        require(preview.status=='previewed','exact-stage-preview-unavailable')
        wire=natural_feedback_remote_request_preview(ModelTask(kind,preview.view),technical_variant='multi-span')
        row=dict(index=index,stage=label,status='started',purpose=kind.value,nonce='s155-real-first-'+str(uuid4()),
            expected_revision=before['revision'],preview_sha256=digest(preview.view),before=before)
        report['stages'].append(row);report['status']='attempt-reserved';save(report)
        require(len(report['calls'])<10,'fixed-first-request-limit')
        evidence.save(ROOT/'previews'/(label+'.json'),dict(preview=preview.view,unsent_wire=wire))
        transport.arm(label,canonical_json(wire['body']).encode());transport.expected['purpose']=kind.value
        if text is None:
            result=product.application.advance_shared_activity(SharedActivityStepRequest(product.profile_id,product.timeline_id,row['nonce'],before['revision']))
        else:
            result=product.application.submit(command_for(product,text),idempotency_key=row['nonce'])
        deadline=perf_counter()+150
        while result.status=='pending' and perf_counter()<deadline:result=product.application.wait(result.operation_ref,timeout_seconds=30)
        row.update(status=plain(result.status),requests=transport.total,problem_code=getattr(getattr(result,'problem',None),'code',getattr(result,'problem_code','')),
            failure_code=getattr(getattr(result,'projection',None),'failure_code',''))
        save(report)
        require(transport.total==1 and row['status'] in ('terminal','committed') and not row['failure_code'],'first-technical-stage-failed')
        raw_value=json.loads(transport.final)
        value=multispan_proposal(raw_value,preview.view['payload']) if text is not None else raw_value
        row['raw_output_fields']=sorted(raw_value)
        row['normalized_output_fields']=sorted(value)
        rows=audit()
        require(len(rows)==audited+1 and rows[-1]['status']=='complete' and rows[-1]['request_digest']==digest(preview.view)
            and rows[-1]['output_digest']==digest(value),'audit-final-preview-mismatch')
        after=view(product);row['after']=after;row['audit_matches_final']=True
        if text is not None:
            actual=plain(history(product))
            require(len(actual)==len(previous)+1 and actual[-1]['user_text']==text and actual[-1]['assistant_text']==value['reply_text'],
                'final-must-equal-canonical-expression')
            row['intent']=value['intent'];row['canonical_head']=actual[-1]['head_sequence']
        else:
            require(value==dict(action=after['decision']['action'],plan=after['current_plan'] if value['action'] in ('start','revise') else None,
                reason_code=after['decision']['reason_code'],basis_refs=after['decision']['basis_refs'],decision_note=after['decision']['decision_note']),
                'choice-must-equal-canonical')
            row['action']=value['action']
        if index==0:
            request=SharedExperienceRequest(product.profile_id,product.timeline_id,'s155-real-source-'+str(uuid4()),after['revision'],row['canonical_head'],text,True)
            selected=product.application.set_shared_experience(request)
            require(selected.status=='committed' and transport.total==1 and len(audit())==audited+1,'source-selection-must-be-zero-model')
            row['zero_source_selection']=plain(selected.status)
        report['next_stage']=index+1;report['status']='ready' if index<9 else 'scene-complete'
        if index==1 and (value['action'] not in ('start','revise') or after['current_plan'] is None):report['status']='bounded-end-initial-no-plan'
        if index in (2,4,5,6,7):
            require(after['current_plan']==before['current_plan'] and after['activity_revision']==before['activity_revision'],
                'non-correction-must-preserve-current-plan')
        if index==3:
            if value['intent']!='revise':
                report['status']='bounded-end-correction-not-applied'
            else:
                frame=requested_frame(text,validate_plan(before['current_plan']))
                require(frame is not None and after['current_plan']==plain(frame.expected_plan)
                    and after['activity_revision']==before['activity_revision']+1,'correction-must-equal-complete-exact-frame')
        if index==8:
            if value['action'] not in ('start','revise'):
                report['status']='bounded-end-post-gap-no-new-plan'
            else:
                require(after['current_plan']!=before['current_plan'] and after['activity_revision']==before['activity_revision']+1,
                    'post-gap-choice-must-create-new-version')
                names=after['current_plan'].values()
                if not any('栖舍' in text for text in names) or any('汀舍' in text for text in names):
                    report['status']='bounded-end-post-gap-name-not-preserved'
        evidence.save(ROOT/'canonical-history.json',plain(history(product)));report['final_view']=view(product)
        save(report)
        print(canonical_json(dict(stage=label,status=row['status'],requests=1,audit_complete=True,next_stage=report['next_stage'],scene_status=report['status'],
            intent=row.get('intent'),action=row.get('action'),activity_revision=after['activity_revision'])),flush=True)
    except Exception as error:
        report.update(status='first-stage-failed',failure_type=type(error).__name__,failure_code=str(error) if isinstance(error,RuntimeError) else 'technical-error')
        save(report)
        print(canonical_json(dict(status=report['status'],requests=len(report['calls']),failure_code=report['failure_code'])),flush=True)
        result_code=2
    finally:
        transport.blocked=True;transport.expected=None
        if product is not None:
            try:product.close()
            except Exception as error:
                report.update(status='first-stage-failed',failure_type=type(error).__name__,failure_code='product-close-failed')
                save(report);result_code=2
                print(canonical_json(dict(status=report['status'],failure_code='product-close-failed',requests=len(report['calls']))),flush=True)
    return result_code


def grade_long(report,score,note):
    require(report['next_stage']==2 and report['status']=='ready','only-initial-object-review-allowed')
    require(score in (0,1,2) and type(note) is str and 0<len(note)<=1000,'bounded-human-review-required')
    final=json.loads((ROOT/'finals/initial-activity.json').read_text(encoding='utf-8'))['final']
    plan=validate_plan(json.loads(final)['plan'])
    frame=requested_frame(STAGES[3][1],plan)
    try:edits=construct_multispan_edits(plan,frame)
    except ValueError:edits=None
    span=(plan.composition.rfind('汀舍')+2-plan.composition.find('汀舍')) if '汀舍' in plan.composition else 0
    eligible=frame is not None and plan.composition.count('汀舍')>=2 and span>160 and edits is not None
    effective_score=score if eligible else 0
    report['human_content_reviews']['long']=dict(score=effective_score,supplied_content_score=score,note=note,span=span,eligible=eligible,final_sha256=sha256(final.encode()).hexdigest(),
        criterion='SCENE stage2 actual same-field target span over160 and representable under old bounds; no invented image')
    if effective_score!=2:report['status']='bounded-end-initial-content-not-met'
    save(report);print(canonical_json(dict(status=report['status'],score=effective_score,requests=0)),flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('check','next','inspect','grade-long'))
    parser.add_argument('--score',type=int);parser.add_argument('--note');args=parser.parse_args(argv)
    verified_review();evidence.ROOT=ROOT
    if args.mode=='check':
        print(canonical_json(dict(status='frozen-review-and-grant-verified',remote_calls=0,credential_reads=0,product_opened=False)),flush=True);return 0
    report=initialize() if not ROOT.exists() and args.mode=='next' else json.loads((ROOT/'metadata.json').read_text(encoding='utf-8'))
    require(report['pins']==pins(),'frozen-first-run-files-changed')
    if args.mode=='inspect':inspect(report);return 0
    if args.mode=='grade-long':grade_long(report,args.score,args.note);return 0
    return next_stage(report)


if __name__=='__main__':raise SystemExit(main())
