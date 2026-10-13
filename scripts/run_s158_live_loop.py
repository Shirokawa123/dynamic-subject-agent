"""Frozen S158 first greenhouse loop. One first stage per next, never retry."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import sys
from time import perf_counter
from uuid import uuid4

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'src'))
import run_s148_choice_comparison as evidence
from run_s158_local_loop import PACKAGE, history, plain
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.shared_activity import SharedExperienceRequest, digest
from dynamic_subject_agent.living_activity import LivingActionRequest, LivingControlRequest
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
from dynamic_subject_agent.timeline import SubjectCommand
from dynamic_subject_agent.first_life import validate_plan
from dynamic_subject_agent.natural_feedback_frame import requested_frame
from dynamic_subject_agent.natural_feedback_multispan import construct_multispan_edits, multispan_proposal
from dynamic_subject_agent.integrated_character_remote_preview import integrated_remote_request_preview

ROOT = REPO/'.artifacts/s158/live-loop-first'
SCENE = REPO/'docs/experiments/s158/SCENE.md'
REVIEW = REPO/'docs/experiments/s158/review.json'
REVIEW_BASIS = '35da99cca813588f534a83be0a2fdeab5730f2e2793ba03726fd5f06d50d3d95'
SOURCE = '我想和你一起想一幅原创的雨后植物温室，暂时叫‘蕨庭’。门口有长凳，叶片上留着水珠。人物在做什么、从哪里看、哪里留空，都由你自己挑一个值得画的安排。现在只是文字构图，不是已经画好的图。'
PAIRS = (('蕨庭', '叶庭'), ('温室', '植物暖房'))
STAGES = (
    ('initial-chat', SOURCE, None),
    ('initial-activity', None, 'simulation'),
    ('first-share', None, 'share'),
    ('natural-reference', '刚才那一处，我想换个叫法，其他先保持。', None),
    ('explicit-feedback', '$derived', None),
    ('topic-one', '画一个人刚把书合上，你会先抓住手停住的那一瞬，还是桌面突然空出来的感觉？', None),
    ('topic-two', '如果只能用两种颜色画风，你会怎么选？我想听听你的理由。', None),
    ('topic-three', '两个人隔着一扇没关严的门说话，你觉得什么细节能让距离看起来不一样？', None),
    ('next-activity', None, 'simulation'),
    ('second-share', None, 'share'),
    ('faithful-reply', '现在这版温室方案里，你最后决定保留什么、改了什么？有哪一点是你自己最想试的？', None))
SCORES = ('independent-choice', 'natural-sharing', 'reference-clarification', 'feedback-continuity', 'faithful-conversation')


def require(value, code):
    if not value: raise RuntimeError(code)


def save(path, value, *, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        with path.open('x', encoding='utf-8') as stream:
            stream.write(canonical_json(plain(value))); stream.flush(); os.fsync(stream.fileno())
    else:
        pending = path.with_name(path.name+'.pending')
        with pending.open('w', encoding='utf-8') as stream:
            stream.write(canonical_json(plain(value))); stream.flush(); os.fsync(stream.fileno())
        pending.replace(path)


def persist(report): save(ROOT/'metadata.json', report)


def pins():
    files = [Path(__file__), SCENE, REVIEW, REPO/'scripts/run_s148_choice_comparison.py',
             REPO/'scripts/run_s158_local_loop.py', REPO/'scripts/serve_integrated_character_chat.py']
    files.extend(sorted((REPO/'src/dynamic_subject_agent').glob('*.py')))
    return {str(path.relative_to(REPO)):sha256(path.read_bytes()).hexdigest() for path in files}


def verify_review():
    value = json.loads(REVIEW.read_text(encoding='utf-8'))
    basis = value.pop('review_basis')
    require(basis == REVIEW_BASIS and digest(value) == basis, 'exact-approved-review-required')
    from dynamic_subject_agent.integrated_character_live import ApprovedIntegratedCharacterGrant, APPROVED_INTEGRATED_REVIEW
    require(APPROVED_INTEGRATED_REVIEW == basis, 'live-grant-basis-mismatch')
    ApprovedIntegratedCharacterGrant(basis, True).validate()


def derive_feedback(plan):
    """First representable frozen name pair; never prune occurrences."""
    typed = validate_plan(plan)
    for old, new in PAIRS:
        text = f'把所有“{old}”换成“{new}”，其他照旧。'
        frame = requested_frame(text, typed)
        if frame is None: continue
        try: edits = construct_multispan_edits(typed, frame)
        except ValueError: continue
        spans = {key:value.rfind(old)+len(old)-value.find(old)
                 for key,value in plan.items() if value.count(old) >= 2}
        return dict(text=text, old=old, new=new, expected_plan=plain(frame.expected_plan),
            occurrences=frame.occurrences, edits=plain(edits), spans=spans,
            long_eligible=any(span > 160 for span in spans.values()))
    return None


def opening(report, transport):
    from serve_integrated_character_chat import IntegratedCharacterChatEntry
    entry = IntegratedCharacterChatEntry(ROOT/'entry', audit_path=ROOT/'audit',
        transport=transport, observations=report['provider_observations'], package_path=PACKAGE)
    product = entry.product
    if report.get('timeline_id'):
        require((product.profile_id, product.timeline_id) == (report['profile_id'], report['timeline_id']), 'same-identity-timeline-required')
    return product


def audit():
    from dynamic_subject_agent.integrated_character_live import open_integrated_character_audit
    return list(open_integrated_character_audit(ROOT/'audit').snapshot())


def audit_readonly():
    # The audit's normal constructor takes a write transaction even for a
    # snapshot. Inspect uses the same verifier through an explicit read-only DB.
    from dynamic_subject_agent.integrated_character_live import IntegratedCharacterCallAudit
    from dynamic_subject_agent.development_model_calls import _DATABASE, _MARKER
    directory=ROOT/'audit'
    require((directory.with_name('audit-initialized')).is_dir() and (directory/_MARKER).is_dir(), 'audit-witness-unavailable')
    verifier=IntegratedCharacterCallAudit.__new__(IntegratedCharacterCallAudit)
    verifier.config=verifier.configuration()
    connection=sqlite3.connect((directory/_DATABASE).resolve().as_uri()+'?mode=ro',uri=True)
    try:
        fields=('ordinal','attempt_id','request_digest','purpose','run_digest','status','output_digest')
        return [dict(zip(fields,row[:-1],strict=True)) for row in verifier._verified(connection)]
    finally:connection.close()


def view(product):
    response = product.application.query_shared_activity()
    require(response.status == 'available', 'canonical-state-unavailable')
    return plain(response.view)


def initialize():
    require(not ROOT.exists(), 'existing-first-run-preserved')
    ROOT.mkdir(parents=True, exist_ok=False)
    report = dict(status='initializing', next_stage=0, calls=[], stages=[], provider_observations=[],
        credential_read_attempts=0, automatic_retries=0, review_basis=REVIEW_BASIS, pins=pins(),
        checks={}, human_content_reviews={}, simulation_activity=True, real_next_day=False)
    persist(report)
    evidence.ROOT = ROOT
    transport = evidence.CapturingTransport(report, blocked=True)
    with opening(report, transport) as product:
        require(not transport.total and not audit() and view(product)['revision'] == 0 and not history(product), 'new-empty-zero-call-entry-required')
        permission = product.application.query_living_controls().view
        controls = product.application.set_living_controls(LivingControlRequest(product.profile_id,product.timeline_id,
            's158-first-enable-'+str(uuid4()),permission['revision'],False,True,True))
        require(controls.status == 'committed' and not transport.total, 'zero-call-controls-required')
        report.update(profile_id=product.profile_id,timeline_id=product.timeline_id,status='ready')
    persist(report)
    return report


def inspect(report):
    """Artifacts only: no product open/recovery, no transport or credential."""
    finals = {path.name:sha256(path.read_bytes()).hexdigest() for path in (ROOT/'finals').glob('*.json')}
    return dict(status=report['status'],next_stage=report['next_stage'],attempts=len(report['stages']),
        requests=len(report['calls']),audit=audit_readonly(),finals=finals,product_opened=False,inspection_requests=0)


def normalized(raw, preview, kind):
    return multispan_proposal(raw, preview['payload']) if kind is ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK else raw


def next_stage(report):
    require(report['status'] == 'ready', 'terminal-or-reserved-attempt-cannot-resend')
    index = report['next_stage']
    require(type(index) is int and 0 <= index < len(STAGES), 'fixed-stage-bound')
    require(not (ROOT/'attempts'/f'{index:02d}.json').exists(), 'existing-first-attempt-preserved')
    label, text, action = STAGES[index]
    if text == '$derived': text = report['feedback']['text']
    evidence.ROOT = ROOT
    transport = evidence.CapturingTransport(report)
    product = None
    row = dict(index=index,stage=label,status='reserved',nonce='s158-first-'+str(uuid4()),text=text,action=action)
    # Reserve before opening: an interruption can only be inspected, never resent.
    save(ROOT/'attempts'/f'{index:02d}.json', row, exclusive=True)
    report['stages'].append(row); report['status']='attempt-reserved'; persist(report)
    try:
        product = opening(report, transport)
        before = view(product); prior = plain(history(product)); audited = len(audit())
        row['before'] = before; row['expected_revision'] = before['revision']; persist(report)
        if index == 8:
            require(report['final_view'] == before and report['canonical_history'] == prior and transport.total == 0, 'reopen-state-or-calls-changed')
            check = product.application.preview_natural_feedback('仅核对当前交流范围。')
            require(check.status == 'previewed', 'reopen-preview-unavailable')
            exchange = canonical_json(check.view['payload']['exchange'])
            require(STAGES[3][1] not in exchange and report['feedback']['text'] not in exchange, 'feedback-still-in-recent-window')
            report['checks']['same_identity_reopened_zero_calls'] = True
            report['checks']['feedback_outside_recent_window'] = True
        kind = (ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK if action is None else
            ModelTaskKind.LIVING_ACTIVITY_SHARE if action == 'share' else ModelTaskKind.LIVING_ACTIVITY_CHOICE)
        preview = (product.application.preview_natural_feedback(text) if action is None else
            product.application.preview_living_activity('share' if action == 'share' else 'choice'))
        if action == 'share' and preview.status == 'no-op':
            row.update(status='not-executed-gate',problem_code=preview.problem_code,requests=0)
            report['checks'][label+'_delivered']=False
        else:
            require(preview.status == 'previewed', 'stage-preview-unavailable')
            wire = integrated_remote_request_preview(ModelTask(kind,preview.view))
            row['purpose']=kind.value
            save(ROOT/'previews'/(label+'.json'),dict(preview=preview.view,unsent_wire=wire),exclusive=True)
            persist(report)
            transport.arm(label,canonical_json(wire['body']).encode()); transport.expected['purpose']=kind.value
            if action is None:
                command=SubjectCommand.contribute_utterance(target_profile_id=product.profile_id,target_timeline_id=product.timeline_id,
                    declared_intent='ask-collaborator-status',utterance=text,language='zh',provenance='project-original')
                result=product.application.submit(command,idempotency_key=row['nonce'])
            else:
                result=product.application.advance_living_activity(LivingActionRequest(product.profile_id,product.timeline_id,row['nonce'],before['revision'],action))
            deadline=perf_counter()+150
            while result.status=='pending' and perf_counter()<deadline:
                result=product.application.wait(result.operation_ref,timeout_seconds=30)
            row.update(status=plain(result.status),requests=transport.total,
                failure_code=getattr(getattr(result,'projection',None),'failure_code',''),
                problem_code=getattr(getattr(result,'problem',None),'code',getattr(result,'problem_code','')))
            persist(report)
            require(transport.total==1 and row['status'] in ('terminal','committed') and not row['failure_code'], 'first-technical-stage-failed-or-unknown')
            raw=json.loads(transport.final); value=normalized(raw,preview.view,kind)
            save(ROOT/'normalized'/(label+'.json'),value,exclusive=True)
            rows=audit()
            require(len(rows)==audited+1 and rows[-1]['status']=='complete'
                and rows[-1]['request_digest']==digest(preview.view) and rows[-1]['output_digest']==digest(raw), 'audit-final-preview-mismatch')
            after=view(product); row['audit_matches_final']=True
            if action is None:
                current=plain(history(product))
                require(len(current)==len(prior)+1 and current[-1]['user_text']==text and current[-1]['assistant_text']==value['reply_text'], 'canonical-expression-mismatch')
                row['intent']=value['intent'];row['canonical_head']=current[-1]['head_sequence']
            elif action=='share':
                row['shared']=value['share'];report['checks'][label+'_delivered']=value['share']
                living=product.application.query_living_activity()
                require(living.status=='available' and living.view['considered'][-1]['share']==value['share'], 'canonical-share-consideration-mismatch')
                if value['share']:
                    require(living.view['shares'][-1]['text']==value['reply_text'], 'canonical-share-expression-mismatch')
            else:
                row['choice']=value
                require(value==dict(action=after['decision']['action'],
                    plan=after['current_plan'] if value['action'] in ('start','revise') else None,
                    reason_code=after['decision']['reason_code'],basis_refs=after['decision']['basis_refs'],
                    decision_note=after['decision']['decision_note']), 'canonical-choice-mismatch')
            if index==0:
                selected=product.application.set_shared_experience(SharedExperienceRequest(product.profile_id,product.timeline_id,
                    's158-first-source-'+str(uuid4()),after['revision'],row['canonical_head'],text,True))
                require(selected.status=='committed' and transport.total==1 and len(audit())==audited+1, 'source-selection-not-zero-call')
            if index==1:
                require(after['current_plan'] is not None, 'initial-no-plan-bounded-end')
                report['feedback']=derive_feedback(after['current_plan'])
                require(report['feedback'] is not None, 'no-frozen-feedback-target-bounded-end')
                report['long_distance']=dict(eligible=report['feedback']['long_eligible'],status='eligible-awaiting-feedback' if report['feedback']['long_eligible'] else 'not-tested-this-scene')
            if index in (3,5,6,7):
                require(after['current_plan']==before['current_plan'] and after['activity_revision']==before['activity_revision'], 'non-correction-changed-plan')
            if index==3: report['checks']['reference_clarifies_without_effect']=value['intent']=='clarify'
            if index==4:
                require(value['intent']=='revise', 'explicit-feedback-not-applied-bounded-end')
                require(after['current_plan']==report['feedback']['expected_plan'] and after['activity_revision']==before['activity_revision']+1, 'feedback-not-exact-frame')
                report['checks']['feedback_exact']=True
                if report['long_distance']['eligible']:report['long_distance']['status']='actual-exact-long-revision'
            if index==8:
                report['checks']['actual_new_choice']=value['action']=='revise' and after['activity_revision']==before['activity_revision']+1 and after['current_plan']!=before['current_plan']
                body=canonical_json(after['current_plan'])
                report['checks']['corrected_name_retained']=report['feedback']['new'] in body and report['feedback']['old'] not in body
                report['checks']['next_choice_reads_f1']=preview.view['payload']['current_feedback']==dict(label='F1',quote=report['feedback']['text'])
        report['final_view']=view(product);report['canonical_history']=plain(history(product));row['after']=report['final_view']
        save(ROOT/'stages'/(label+'.json'),row,exclusive=True)
        report['next_stage']=index+1
        report['status']='ready' if index+1<len(STAGES) else 'execution-ended-semantic-review-required'
        persist(report)
        return 0
    except Exception as error:
        report.update(status='bounded-terminal',failure_type=type(error).__name__,failure_code=str(error) if isinstance(error,RuntimeError) else 'technical-error')
        row['status']='failed-or-unknown';persist(report)
        return 2
    finally:
        transport.blocked=True;transport.expected=None
        if product is not None:
            try:product.close()
            except Exception:
                report.update(status='bounded-terminal',failure_code='product-close-failed');persist(report)


def grade(report, scores):
    require(report['status']=='execution-ended-semantic-review-required' and not report['human_content_reviews'], 'first-complete-semantic-review-only')
    require(type(scores) is dict and set(scores)==set(SCORES), 'exact-five-semantic-scores-required')
    for value in scores.values():
        require(type(value) is dict and set(value)=={'score','note'} and type(value['score']) is int
            and value['score'] in (0,1,2) and type(value['note']) is str and 0<len(value['note'])<=1500, 'bounded-score-with-evidence-required')
    save(ROOT/'semantic-review.json',scores,exclusive=True)
    report['human_content_reviews']=scores
    report['status']='scene-effect-passed' if all(report['checks'].values()) and all(x['score']==2 for x in scores.values()) else 'scene-effect-not-met'
    persist(report)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('check','init','next','inspect','grade'))
    parser.add_argument('--scores',type=Path)
    args=parser.parse_args(argv)
    if args.mode=='inspect':
        report=json.loads((ROOT/'metadata.json').read_text(encoding='utf-8'))
        print(canonical_json(inspect(report)));return 0
    verify_review()
    if args.mode=='check':
        print(canonical_json(dict(status='review-and-grant-verified',requests=0,product_opened=False)));return 0
    if args.mode=='init':report=initialize();code=0
    else:
        report=json.loads((ROOT/'metadata.json').read_text(encoding='utf-8'))
        require(report['pins']==pins(), 'frozen-first-run-files-changed')
        if args.mode=='grade':
            require(args.scores is not None,'scores-file-required')
            grade(report,json.loads(args.scores.read_text(encoding='utf-8')));code=0
        else:code=next_stage(report)
    print(canonical_json(dict(status=report['status'],next_stage=report['next_stage'],requests=len(report['calls']))))
    return code


if __name__=='__main__':raise SystemExit(main())
