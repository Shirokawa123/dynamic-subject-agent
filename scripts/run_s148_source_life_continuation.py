"""Source-first continuation on the SAME existing S144 development Timeline.

No W1-to-share expansion: one exact committed E1, existing S142/S144 purposes.
The activity opportunity is explicitly simulated/manual, never elapsed time.
day1 preserves every first result; next-day refuses the same civil date before
opening a product or reading a credential. No persistent service is started.
"""
import argparse
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import run_s148_choice_comparison as evidence
from dynamic_subject_agent.application import ApplicationQuery,ApplicationQueryKind,SubjectRequestLookupRequest
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.living_activity import LivingActionRequest,LivingControlRequest
from dynamic_subject_agent.living_activity_remote_preview import living_remote_request_preview
from dynamic_subject_agent.model_gateway import ModelTask,ModelTaskKind
from dynamic_subject_agent.shared_activity import SharedExperienceRequest
from dynamic_subject_agent.timeline import SubjectCommand

ROOT=evidence.REPO/'.artifacts/s148/source-life'
PRIOR=Path('C:/Users/30252/AppData/Local/DynamicSubjectAgent/living-activity-development/s144/live-candidate-first-20261008-1')
SOURCE='接着上次那份抱膝少女和幻想小兽的原创文字方案。这一版主体旁留一个安静的角落供视线停下来，角落要有很淡的光影变化；仅限这份构图，不是我所有画的偏好。仍只讨论文字方案，没有成图。'
FEEDBACK='延续抱膝少女和幻想小兽的同一份原创文字方案。我收回主体旁整块留空的建议，这一版要在主体旁用少量纹理和阴影层次，让那里不整块空白，也不抢表情和拿笔的手。只针对这一版，不要求改成已画完。'
RESULT='现在这份文字方案怎样落实我刚才的纠正？说一个具体取舍就好；仍没有成图。'
NEXT_DAY='接着我们上一回保留的同一份文字方案。现在主体旁怎样安排，为什么？这是接续先前的讨论，不表示离线已经画完或做过新活动。'


def today(): return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def next_day_allowed(report,day):
    completed=report.get('feedback_completed_civil_date')
    return (report.get('status')=='day1-complete-awaiting-real-next-day'
        and type(completed) is str and day>completed)


def reserve_next_day(report):
    evidence.require(next_day_allowed(report,today()),'real-feedback-next-day-not-ready')
    report.update(status='next-day-attempt-started',next_day_attempt=dict(
        idempotency_key='s148-life-'+str(uuid4()),civil_date=today(),message_sha256=evidence.digest(NEXT_DAY)))
    evidence.save(ROOT/'metadata.json',report)


class LifeRun:
    def __init__(self,product,transport,report,audit_path):
        self.product,self.transport,self.report,self.audit_path=product,transport,report,audit_path

    def audit(self):
        from dynamic_subject_agent.living_activity_live import open_living_activity_audit
        return list(open_living_activity_audit(self.audit_path,technical_variant='final-text').snapshot())

    def view(self):
        response=self.product.application.query_living_activity()
        evidence.require(response.status=='available','living-canonical-unavailable')
        return evidence.plain(response.view)

    def history(self):
        response=self.product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
            self.product.profile_id,self.product.timeline_id))
        evidence.require(evidence.plain(response.status)=='available','history-unavailable')
        return evidence.plain(response.projection.turns)

    def checkpoint(self): evidence.save(ROOT/'metadata.json',self.report)

    def zero(self,label,action):
        before=self.transport.total;audited=len(self.audit())
        result=action()
        evidence.require(before==self.transport.total and len(self.audit())==audited,'zero-operation-sent-model')
        self.report['stages'].append(dict(stage=label,status=evidence.plain(result.status),requests=0))
        self.checkpoint()
        evidence.require(evidence.plain(result.status) in ('committed','replayed'),'zero-operation-not-committed')
        return result

    def controls(self,paused,sharing):
        request=LivingControlRequest(self.product.profile_id,self.product.timeline_id,str(uuid4()),
            self.view()['permission']['revision'],paused=paused,sharing_enabled=sharing,confirmed=True)
        self.zero('explicit-controls',lambda:self.product.application.set_living_controls(request))

    def stage(self,label,kind,preview,action):
        wire=living_remote_request_preview(ModelTask(kind,preview),technical_variant='final-text')
        before=self.transport.total;audited=len(self.audit())
        row=dict(stage=label,status='started',purpose=kind.value,preview_sha256=evidence.digest(preview))
        self.report['stages'].append(row);self.checkpoint()
        self.transport.arm(label,canonical_json(wire['body']).encode())
        self.transport.expected['purpose']=kind.value
        result=action()
        deadline=perf_counter()+150
        while evidence.plain(result.status)=='pending' and perf_counter()<deadline:
            result=self.product.application.wait(result.operation_ref,timeout_seconds=30)
        status=evidence.plain(result.status)
        row.update(status=status,requests=self.transport.total-before,problem_code=getattr(result,'problem_code',None),
            failure_code=getattr(getattr(result,'projection',None),'failure_code',None))
        self.checkpoint()
        evidence.require(row['requests']==1 and status in ('terminal','committed','no-op')
            and not row['failure_code'],'first-live-stage-failed')
        audit=self.audit()
        value=dict(reply_text=self.transport.final,language='zh') if kind is ModelTaskKind.LIVING_ACTIVITY_REPLY else json.loads(self.transport.final)
        evidence.require(len(audit)==audited+1 and audit[-1]['status']=='complete'
            and audit[-1]['request_digest']==evidence.digest(preview) and audit[-1]['output_digest']==evidence.digest(value),
            'single-call-audit-or-final-mismatch')
        row['audit_matches_raw_final']=True;self.checkpoint()
        return result

    def reply(self,label,text,idempotency_key=None):
        preview=self.product.application.preview_living_activity('reply',text)
        evidence.require(preview.status=='previewed','reply-preview-unavailable')
        before=self.history()
        result=self.stage(label,ModelTaskKind.LIVING_ACTIVITY_REPLY,evidence.plain(preview.view),lambda:
            self.product.application.submit(SubjectCommand.contribute_utterance(target_profile_id=self.product.profile_id,
                target_timeline_id=self.product.timeline_id,declared_intent='ask-collaborator-status',utterance=text,
                language='zh',provenance='project-original'),idempotency_key=idempotency_key or 's148-life-'+str(uuid4())))
        after=self.history()
        evidence.require(len(after)==len(before)+1 and after[-1]['user_text']==text
            and after[-1]['assistant_text']==self.transport.final,'reply-not-exact-canonical')
        return after[-1]['head_sequence']

    def select(self,label,head,quote):
        request=SharedExperienceRequest(self.product.profile_id,self.product.timeline_id,str(uuid4()),
            self.view()['revision'],head,quote,True)
        self.zero(label,lambda:self.product.application.set_shared_experience(request))
        source=self.view()['source']
        evidence.require(source['source_head_sequence']==head and source['quote']==quote,'selected-source-not-exact')

    def choice(self,label):
        preview=self.product.application.preview_living_activity('choice')
        evidence.require(preview.status=='previewed','choice-preview-unavailable')
        request=LivingActionRequest(self.product.profile_id,self.product.timeline_id,str(uuid4()),self.view()['revision'],'simulation')
        result=self.stage(label,ModelTaskKind.LIVING_ACTIVITY_CHOICE,evidence.plain(preview.view),lambda:
            self.product.application.advance_living_activity(request))
        current=self.view()['visible_result']
        shared=evidence.plain(self.product.application.query_shared_activity().view)
        decision=shared['decision']
        raw=json.loads(self.transport.final)
        canonical=dict(action=decision['action'],plan=current['plan'] if decision['action'] in ('start','revise') else None,
            reason_code=decision['reason_code'],basis_refs=decision['basis_refs'],decision_note=decision['decision_note'])
        evidence.require(raw==canonical and (current is None or current['event']['simulated'] is True),'choice-not-exact-canonical')
        self.zero(label+'-nonce-read',lambda:self.product.application.query_living_activity(request))
        self.report['stages'][-2].update(action=raw['action'],simulated_opportunity=True)
        self.checkpoint()
        return raw['action']

    def share(self):
        before=self.history();prior=len(self.view()['considered'])
        preview=self.product.application.preview_living_activity('share')
        evidence.require(preview.status=='previewed','share-preview-unavailable')
        request=LivingActionRequest(self.product.profile_id,self.product.timeline_id,str(uuid4()),self.view()['revision'],'share')
        self.stage('consider-whether-to-share',ModelTaskKind.LIVING_ACTIVITY_SHARE,evidence.plain(preview.view),lambda:
            self.product.application.advance_living_activity(request))
        raw=json.loads(self.transport.final);view=self.view()
        evidence.require(self.history()==before and len(view['considered'])==prior+1
            and view['considered'][-1]['share']==raw['share'],'share-origin-or-decision-mismatch')
        if raw['share']:
            evidence.require(view['shares'][-1]['text']==raw['reply_text'],'share-text-mismatch')
        else: evidence.require(raw['reply_text']=='','false-share-has-text')
        self.report['share_decision']=raw['share'];self.checkpoint()
        self.zero('share-nonce-read',lambda:self.product.application.query_living_activity(request))
        return raw['share']

    def day1(self):
        old=self.history()
        evidence.require(old and today()>datetime.fromtimestamp(old[-1]['published_at_us']/1e6,timezone(timedelta(hours=8))).date().isoformat(),
            'prior-real-day-boundary-required')
        self.report['prior_real_day_boundary']=True
        head=self.reply('source-after-real-day-gap',SOURCE)
        self.select('select-single-exact-source',head,SOURCE)
        self.controls(False,True)
        action=self.choice('source-influenced-activity')
        if action not in ('start','revise'):
            self.report['status']='bounded-end-no-new-plan';return
        self.share()  # False is a legal completed choice; feedback still follows.
        feedback=self.reply('feedback-about-actual-plan',FEEDBACK)
        self.select('replace-source-with-exact-correction',feedback,FEEDBACK)
        # The old E1-derived plan/share is now ineligible. Preserve its history.
        evidence.require(self.view()['current_plan'] is None and self.view()['latest_share'] is None,'old-corrected-chain-still-eligible')
        action=self.choice('corrected-activity')
        if action=='rework': action=self.choice('corrected-activity-after-rework')
        if action not in ('start','revise'):
            self.report['status']='bounded-end-correction-without-new-plan';return
        self.reply('corrected-result-reply',RESULT)
        self.report['status']='day1-complete-awaiting-real-next-day'
        self.report['feedback_plan_sha256']=evidence.digest(self.view()['current_plan'])
        self.report['feedback_source_sha256']=evidence.digest(self.view()['source'])
        self.report['feedback_completed_civil_date']=datetime.fromtimestamp(
            self.history()[-1]['published_at_us']/1e6,timezone(timedelta(hours=8))).date().isoformat()

    def next_day(self):
        evidence.require(evidence.digest(self.view()['current_plan'])==self.report['feedback_plan_sha256']
            and evidence.digest(self.view()['source'])==self.report['feedback_source_sha256'],'day1-saved-plan-or-source-changed')
        self.reply('real-next-day-corrected-continuation',NEXT_DAY,
            idempotency_key=self.report['next_day_attempt']['idempotency_key'])
        self.report.update(status='real-next-day-scene-complete',feedback_real_next_day_verified=True,next_day_civil_date=today())

    def lookup_next_day(self):
        command=SubjectCommand.contribute_utterance(target_profile_id=self.product.profile_id,
            target_timeline_id=self.product.timeline_id,declared_intent='ask-collaborator-status',
            utterance=NEXT_DAY,language='zh',provenance='project-original')
        result=self.product.application.lookup_subject_request(SubjectRequestLookupRequest(command,
            self.report['next_day_attempt']['idempotency_key']))
        self.report['next_day_readonly_lookup']=evidence.plain(result)
        evidence.require(self.transport.total==0,'readonly-recovery-sent-model')
        # Finding the original result is engineering recovery, not human content
        # acceptance or permission to send another attempt.
        self.report['status']='next-day-readonly-recovery-needs-content-review'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('day1','next-day'))
    args=parser.parse_args();entry=None;run=None;readonly_recovery=False
    evidence.ROOT=ROOT  # Capture goes to this runner's own experiment directory.
    if args.mode=='day1':
        evidence.require(not ROOT.exists(),'existing-life-first-results-preserved')
        ROOT.mkdir(parents=True,exist_ok=False)
        report=dict(status='running-day1',day1_civil_date=today(),calls=[],stages=[],credential_read_attempts=0,
            automatic_retries=0,simulated_opportunities=True,feedback_real_next_day_verified=False,
            runtime_root=str(PRIOR),runner_sha256=evidence.sha256(Path(__file__).read_bytes()).hexdigest())
    else:
        report=json.loads((ROOT/'metadata.json').read_text(encoding='utf-8'))
        readonly_recovery=bool(report.get('next_day_attempt') and not report['feedback_real_next_day_verified'])
        if readonly_recovery:
            evidence.require(report['runner_sha256']==evidence.sha256(Path(__file__).read_bytes()).hexdigest(),'runner-changed-after-day1')
        elif not next_day_allowed(report,today()):
            print(canonical_json(dict(status='not-yet-eligible-real-next-day',remote_calls=0,credential_reads=0)),flush=True);return 0
        else:
            evidence.require(report['runner_sha256']==evidence.sha256(Path(__file__).read_bytes()).hexdigest(),'runner-changed-after-day1')
            reserve_next_day(report)  # Durable burn + exact nonce BEFORE opening.
    transport=evidence.CapturingTransport(report,blocked=readonly_recovery)
    try:
        from serve_living_final_text_chat import FinalTextLivingActivityChatEntry
        entry=FinalTextLivingActivityChatEntry(PRIOR,live=False,transport=transport,audit_path=PRIOR/'provider-audit')
        run=LifeRun(entry.product,transport,report,PRIOR/'provider-audit')
        identity=dict(profile_id=entry.product.profile_id,timeline_id=entry.product.timeline_id)
        if args.mode=='next-day': evidence.require(report['identity']==identity,'same-person-and-timeline-required')
        else: report['identity']=identity
        before=run.view();stored=run.history();entry.reopen();run.product=entry.product
        evidence.require(run.view()==before and run.history()==stored and transport.total==0,'real-reopen-not-zero-or-changed')
        if args.mode=='day1': run.day1()
        elif readonly_recovery: run.lookup_next_day()
        else: run.next_day()
    except BaseException as error:
        report.update(status='stopped-first-failure',error_type=type(error).__name__,
            stop_code=str(error) if type(error) is RuntimeError else 'unexpected-error')
    finally:
        if run is not None and not readonly_recovery:
            try: run.controls(True,False)
            except BaseException as error:
                report.update(status='stopped-first-failure',final_controls_error=type(error).__name__)
        if entry is not None:
            try: entry.close()
            except BaseException as error:
                report.update(status='stopped-first-failure',close_error=type(error).__name__)
        report['this_invocation_remote_calls']=transport.total
        evidence.save(ROOT/'metadata.json',report)
        print(canonical_json(dict(status=report['status'],remote_calls=transport.total,
            share_decision=report.get('share_decision'),prior_real_day_boundary=report.get('prior_real_day_boundary'),
            feedback_real_next_day_verified=report['feedback_real_next_day_verified'],automatic_retries=0)),flush=True)
    return 1 if report['status']=='stopped-first-failure' else 0


if __name__=='__main__':raise SystemExit(main())
