"""Frozen S153 intent-only local-frame first object scene, one next stage per invocation, zero retries.

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
from dynamic_subject_agent.natural_feedback_intent import NaturalFeedbackIntentDevelopmentGrant,INTENT_DEVELOPMENT,intent_proposal
from dynamic_subject_agent.natural_feedback_remote_preview import natural_feedback_remote_request_preview
from dynamic_subject_agent.frozen_attempt import canonical_json

ROOT=REPO/'.artifacts/s153/new-scene-first'
SCENE=REPO/'docs/experiments/s153/SCENE.md'
REVIEW=REPO/'docs/experiments/s150/review.json'
STAGES=(('initial-source', '这次原创文字构图里，放一只叫作‘纸鹤’的小物件；主体、镜头与光线由你按自己的关注决定。现在只是文字方案，还没有画出来。'), ('initial-activity', None), ('natural-correction', '这版把所有‘纸鹤’换成‘布偶’，其他照旧。'), ('ambiguous-feedback', '细节里还有一个地方，我没想清楚，你怎么看？'), ('conditional-feedback', '要是另做雨天版，我可能会想让窗外更暗；现在这版先别动。'), ('topic-gap-1', '漫画把同一个动作拆成三格，你更在意节奏还是表情变化？'), ('topic-gap-2', '虚构故事里有一间常年不开灯的店，你现在会先好奇什么？'), ('topic-gap-3', '给故事开头留一小段空白，你会想快点填上，还是多等一会儿？'), ('post-gap-activity', None), ('current-result-reply', '现在这一版的小物件是什么，放在哪里？你为什么这样安排？'))


def require(condition,code):
    if not condition:raise RuntimeError(code)


def pins():
    return dict(runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        capture_helper_sha256=sha256((REPO/'scripts/run_s148_choice_comparison.py').read_bytes()).hexdigest(),
        scene_sha256=sha256(SCENE.read_bytes()).hexdigest(),review_sha256=sha256(REVIEW.read_bytes()).hexdigest(),
        execution_sources={name:sha256((REPO/name).read_bytes()).hexdigest() for name in (
            'scripts/run_s150_local_feedback.py',
            *('src/dynamic_subject_agent/'+name for name in ('natural_feedback.py','natural_feedback_live.py',
                'natural_feedback_provider.py','natural_feedback_budget.py','natural_feedback_frame.py','natural_feedback_scoped.py','natural_feedback_intent.py','natural_feedback_output_metadata.py','natural_feedback_remote_preview.py','shared_activity.py',
                'shared_activity_cognition.py','local_product.py','local_identity_authority.py','host.py',
                'timeline.py','studio.py','application.py','original_whole_chat.py','model_gateway.py')))})


def verified_review():
    value=json.loads(REVIEW.read_text(encoding='utf-8'));basis=value.pop('review_basis')
    require(basis==APPROVED_FEEDBACK_REVIEW and digest(value)==basis,'exact-approved-review-required')
    require(pins()['scene_sha256']=='ec3e2fb0c2f4d9b4d896f08ddd8c842475ead378cb99123fbae510cf0a5f81e8','frozen-new-scene-changed')
    NaturalFeedbackIntentDevelopmentGrant(basis,INTENT_DEVELOPMENT).validate()
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
    config=LocalProductConfig(ROOT/'entry/DynamicSubjectAgent/m0/experiments',ROOT/'entry/state.json')
    product=open_natural_feedback_product_live(config,identity_id=report['identity_id'],
        grant=NaturalFeedbackIntentDevelopmentGrant(APPROVED_FEEDBACK_REVIEW,INTENT_DEVELOPMENT),audit_path=ROOT/'audit',_transport=transport,observations=report['provider_observations'])
    if report.get('timeline_id'):
        require((product.profile_id,product.timeline_id)==(report['profile_id'],report['timeline_id']),'same-identity-timeline-required')
    return product


def initialize():
    require(not ROOT.exists(),'first-scene-must-not-be-recreated')
    ROOT.mkdir(parents=True,exist_ok=False)
    report=dict(status='initializing',next_stage=0,calls=[],stages=[],credential_read_attempts=0,automatic_retries=0,
        review_basis=APPROVED_FEEDBACK_REVIEW,pins=pins(),human_content_reviews={},provider_observations=[])
    save(report)
    review=ApplicationFacade.preview_original_character_whole_use_preparation(OriginalWholeUsePreparationRequest(PACKAGE,
        APPROVED_BINDING['definition_basis'],APPROVED_BINDING['runtime_asset_sha'],APPROVED_BINDING['persona_digest'],
        APPROVED_BINDING['subject_id'],APPROVED_BINDING['anchor_id']))
    require(review.status=='previewed' and review.review_basis==APPROVED_BINDING['review_basis'],'exact-approved-character-package-required')
    config=LocalProductConfig(ROOT/'entry/DynamicSubjectAgent/m0/experiments',ROOT/'entry/state.json')
    with open_local_product(config,cognition=DormantDeepSeekCognition()) as author:
        frozen=author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(PACKAGE.read_text(encoding='utf-8'),
            APPROVED_BINDING['definition_basis'],True,True))
        require(frozen.status=='created','new-independent-scene-identity-required')
        report['identity_id']=frozen.view.identity_id;save(report)
    transport=evidence.CapturingTransport(report,blocked=True)
    with opening(report,transport) as product:
        report.update(profile_id=product.profile_id,timeline_id=product.timeline_id,status='ready')
        require(not history(product) and not transport.total and not open_natural_feedback_audit(ROOT/'audit',technical_variant='intent-only').snapshot(),'new-opening-must-be-empty-zero-model')
    save(report)
    return report


def audit():return list(open_natural_feedback_audit(ROOT/'audit',technical_variant='intent-only').snapshot())


def inspect(report):
    transport=evidence.CapturingTransport(report,blocked=True)
    with opening(report,transport) as product:
        current=product.application.query_shared_activity()
        report['readonly_inspection']=dict(status=plain(current.status),view=plain(current.view),audit=audit(),requests=0)
        if report['stages'] and report['stages'][-1]['status']=='started':
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
        require(report['human_content_reviews'].get('object',{}).get('score')==2,'object-content-must-be-reviewed-before-correction')
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
        wire=natural_feedback_remote_request_preview(ModelTask(kind,preview.view),technical_variant='intent-only')
        row=dict(index=index,stage=label,status='started',purpose=kind.value,nonce='s153-real-first-'+str(uuid4()),
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
        value=intent_proposal(raw_value,preview.view['payload']) if text is not None else raw_value
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
            request=SharedExperienceRequest(product.profile_id,product.timeline_id,'s153-real-source-'+str(uuid4()),after['revision'],row['canonical_head'],text,True)
            selected=product.application.set_shared_experience(request)
            require(selected.status=='committed' and transport.total==1 and len(audit())==audited+1,'source-selection-must-be-zero-model')
            row['zero_source_selection']=plain(selected.status)
        report['next_stage']=index+1;report['status']='ready' if index<9 else 'scene-complete'
        if index==1 and (value['action'] not in ('start','revise') or after['current_plan'] is None):report['status']='bounded-end-initial-no-plan'
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


def grade_object(report,score,note):
    require(report['next_stage']==2 and report['status']=='ready','only-initial-object-review-allowed')
    require(score in (0,1,2) and type(note) is str and 0<len(note)<=1000,'bounded-human-review-required')
    final=json.loads((ROOT/'finals/initial-activity.json').read_text(encoding='utf-8'))['final']
    report['human_content_reviews']['object']=dict(score=score,note=note,final_sha256=sha256(final.encode()).hexdigest(),
        criterion='SCENE stage2 actual original paper-crane object; no invented image')
    if score!=2:report['status']='bounded-end-initial-content-not-met'
    save(report);print(canonical_json(dict(status=report['status'],score=score,requests=0)),flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('check','next','inspect','grade-object'))
    parser.add_argument('--score',type=int);parser.add_argument('--note');args=parser.parse_args(argv)
    verified_review();evidence.ROOT=ROOT
    if args.mode=='check':
        print(canonical_json(dict(status='frozen-review-and-grant-verified',remote_calls=0,credential_reads=0,product_opened=False)),flush=True);return 0
    report=initialize() if not ROOT.exists() and args.mode=='next' else json.loads((ROOT/'metadata.json').read_text(encoding='utf-8'))
    require(report['pins']==pins(),'frozen-first-run-files-changed')
    if args.mode=='inspect':inspect(report);return 0
    if args.mode=='grade-object':grade_object(report,args.score,args.note);return 0
    return next_stage(report)


if __name__=='__main__':raise SystemExit(main())
