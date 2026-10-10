"""One new light-correction scene; no repeat of S148 or automatic retries.

The completed-day date is canonical. A later-day attempt is durably reserved
before opening; interrupted attempts only query their exact nonce with a blocked
transport. Every raw final stays in ignored local evidence, not Git.
"""
import argparse
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
from time import perf_counter

import run_s148_source_life_continuation as life
import run_s148_choice_comparison as evidence
from serve_living_action_contract_chat import ActionContractLivingChatEntry
from dynamic_subject_agent.living_activity_live import open_living_activity_audit
from dynamic_subject_agent.living_activity_remote_preview import living_remote_request_preview
from dynamic_subject_agent.model_gateway import ModelTask,ModelTaskKind
from dynamic_subject_agent.frozen_attempt import canonical_json

ROOT=evidence.REPO/'.artifacts/s149/light-correction-first'
SOURCE='只针对这份原创文字构图，我建议只保留一个冷色主光源，让主体更清楚。这个建议不适用于我的其他画，也不要求改动你选的主体或视点；现在还没有成图。'
FEEDBACK='更正刚才只留冷色主光的建议：这一版改用暖色主光，冷色只做很低亮度的边缘反光。主体和视点保持，不要把整个画面改成冷色；仅限这份原创文字方案，不表示已经画完。'
RESULT='这一版实际提交的光源安排是什么，为什么这样选？先说一个你在意的具体取舍，不把准备修改当成已经完成图片。'
GAP='先换个话题：讲故事时，你觉得先交代一个小细节再出现转折，有什么好处或不方便？只谈现在的看法。'
NEXT_DAY='接着上一次更正后保留的同一份文字方案。现在光线怎样安排，为什么？这只是接续原来的讨论，不表示离线已经画完或做过新活动。'
MAX_DAY1_CALLS=9


def feedback_for(plan):
    value='这份文字方案主题：'+plan['subject']+'；原构图开头：'+plan['composition'][:80]+'；'+FEEDBACK
    evidence.require(len(value)<=400,'explicit-feedback-source-over-budget')
    return value


def helper_pins():
    return {name:evidence.sha256((evidence.REPO/'scripts'/name).read_bytes()).hexdigest() for name in
        ('run_s148_source_life_continuation.py','run_s148_choice_comparison.py','serve_living_action_contract_chat.py')}


class ActionRun(life.LifeRun):
    def audit(self):return list(open_living_activity_audit(self.audit_path,technical_variant='action-contract').snapshot())

    def stage(self,label,kind,preview,action):
        wire=living_remote_request_preview(ModelTask(kind,preview),technical_variant='action-contract')
        before=self.transport.total;audited=len(self.audit())
        limit=1 if label=='real-next-day-corrected-continuation' else MAX_DAY1_CALLS
        evidence.require(before<limit,'fixed-scene-request-bound-exceeded')
        row=dict(stage=label,status='started',purpose=kind.value,preview_sha256=evidence.digest(preview))
        self.report['stages'].append(row);self.checkpoint()
        self.transport.arm(label,canonical_json(wire['body']).encode())
        self.transport.expected['purpose']=kind.value
        result=action();deadline=perf_counter()+150
        while evidence.plain(result.status)=='pending' and perf_counter()<deadline:
            result=self.product.application.wait(result.operation_ref,timeout_seconds=30)
        row.update(status=evidence.plain(result.status),requests=self.transport.total-before,
            problem_code=getattr(result,'problem_code',None),failure_code=getattr(getattr(result,'projection',None),'failure_code',None))
        self.checkpoint()
        evidence.require(row['requests']==1 and row['status'] in ('terminal','committed','no-op') and not row['failure_code'],'first-live-stage-failed')
        audit=self.audit()
        value=dict(reply_text=self.transport.final,language='zh') if kind is ModelTaskKind.LIVING_ACTIVITY_REPLY else json.loads(self.transport.final)
        evidence.require(len(audit)==audited+1 and audit[-1]['status']=='complete'
            and audit[-1]['request_digest']==evidence.digest(preview) and audit[-1]['output_digest']==evidence.digest(value),'audit-final-preview-mismatch')
        row['audit_matches_raw_final']=True;self.checkpoint();return result

    def day1(self):
        self.controls(False,True)
        if self.choice('independent-initial-A1') not in ('start','revise'):
            self.report['status']='bounded-end-initial-no-plan';return
        independent=self.view()['current_plan']
        head=self.reply('new-cold-light-source',SOURCE)
        self.select('select-exact-cold-light-source',head,SOURCE)
        if self.choice('cold-light-activity') not in ('start','revise'):
            self.report['status']='bounded-end-source-without-new-plan';return
        cold=self.view()['current_plan']
        self.report['initial_plan_sha256']=evidence.digest(independent)
        self.report['cold_plan_sha256']=evidence.digest(cold)
        self.share()  # false is a valid decision; do not force a second share.
        text=feedback_for(cold);self.report['actual_feedback_sha256']=evidence.digest(text)
        head=self.reply('new-warm-light-feedback',text)
        self.select('replace-source-with-exact-warm-feedback',head,text)
        evidence.require(self.view()['current_plan'] is None and self.view()['latest_share'] is None,'old-correction-chain-still-eligible')
        before_revision=self.product.application.query_shared_activity().view['activity_revision']
        action=self.choice('warm-feedback-first-action')
        if action=='rework':
            saved=self.view();rework=self.product.application.query_shared_activity().view
            # An archived, invalidated plan may remain stored. The raw proposal
            # is null, differences empty, and no new version was published.
            self.report['rework_without_new_plan']=(json.loads(self.transport.final)['plan'] is None
                and rework['activity_revision']==before_revision and not rework['result'].differences)
            # Actual process-side close/reopen after rework occurs in main's
            # callback; neither method can trigger a model by opening.
            self.reopen_after_rework()
            evidence.require(self.view()==saved,'rework-reopen-state-changed')
            action=self.choice('warm-feedback-new-revision')
        if action not in ('start','revise'):
            self.report['status']='bounded-end-feedback-without-new-plan';return
        self.reply('actual-warm-plan-result',RESULT)
        self.report['feedback_completed_civil_date']=datetime.fromtimestamp(
            self.history()[-1]['published_at_us']/1e6,timezone(timedelta(hours=8))).date().isoformat()
        self.report['feedback_plan_sha256']=evidence.digest(self.view()['current_plan'])
        self.report['feedback_source_sha256']=evidence.digest(self.view()['source'])
        self.reply('new-topic-after-correction',GAP)
        self.report['status']='day1-complete-awaiting-real-next-day'


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('day1','next-day','check'))
    args=parser.parse_args(argv)
    if args.mode=='check':
        from dynamic_subject_agent.living_action_contract import LivingActionContractDevelopmentGrant,ACTION_DEVELOPMENT_AUTHORIZATION
        from dynamic_subject_agent.living_activity_live import APPROVED_LIVING_REVIEW
        LivingActionContractDevelopmentGrant(APPROVED_LIVING_REVIEW,ACTION_DEVELOPMENT_AUTHORIZATION).validate()
        evidence.require(len(feedback_for(dict(subject='题'*160,composition='构'*800)))<=400,'feedback-fixture-bound')
        print(canonical_json(dict(status='pure-check-passed',remote_calls=0,credential_reads=0,product_opened=False)),flush=True);return 0
    entry=run=None;readonly=False
    evidence.ROOT=ROOT;life.ROOT=ROOT;life.NEXT_DAY=NEXT_DAY
    if args.mode=='day1':
        evidence.require(not ROOT.exists(),'first-scene-evidence-preserved-no-repeat')
        ROOT.mkdir(parents=True,exist_ok=False)
        report=dict(status='running-day1',day1_civil_date=life.today(),calls=[],stages=[],credential_read_attempts=0,
            automatic_retries=0,simulated_opportunities=True,feedback_real_next_day_verified=False,
            runner_sha256=evidence.sha256(Path(__file__).read_bytes()).hexdigest(),helper_sha256=helper_pins(),
            scene_sha256=evidence.sha256((evidence.REPO/'docs/experiments/s149/SCENE.md').read_bytes()).hexdigest())
    else:
        report=json.loads((ROOT/'metadata.json').read_text(encoding='utf-8'))
        readonly=bool(report.get('next_day_attempt') and not report['feedback_real_next_day_verified'])
        if not readonly and not life.next_day_allowed(report,life.today()):
            print(canonical_json(dict(status='next-day-ineligible',remote_calls=0,credential_reads=0)),flush=True);return 0
        evidence.require(report['runner_sha256']==evidence.sha256(Path(__file__).read_bytes()).hexdigest()
            and report['helper_sha256']==helper_pins()
            and report['scene_sha256']==evidence.sha256((evidence.REPO/'docs/experiments/s149/SCENE.md').read_bytes()).hexdigest(),
            'frozen-runner-helpers-or-scene-changed')
        if not readonly:life.reserve_next_day(report)
    transport=evidence.CapturingTransport(report,blocked=readonly)
    try:
        entry=ActionContractLivingChatEntry(ROOT/'entry',live=False,transport=transport,audit_path=ROOT/'audit')
        run=ActionRun(entry.product,transport,report,ROOT/'audit')
        identity=dict(profile_id=entry.product.profile_id,timeline_id=entry.product.timeline_id)
        if args.mode=='day1':
            evidence.require(not run.history() and run.view()['revision']==0 and transport.total==0,'new-independent-empty-scene-required')
            report['identity']=identity
        else:evidence.require(report['identity']==identity,'same-person-timeline-required')
        def reopen():
            sent=transport.total;before=run.view();stored=run.history()
            entry.reopen();run.product=entry.product
            evidence.require(transport.total==sent and run.view()==before and run.history()==stored,'zero-model-reopen-changed-state')
        run.reopen_after_rework=reopen
        if args.mode=='day1':run.day1()
        elif readonly:run.lookup_next_day()
        else:run.next_day()
        reopen()
        report['final_reopen_verified']=True
    except BaseException as error:
        report.update(status='stopped-first-failure',error_type=type(error).__name__,
            stop_code=str(error) if type(error) is RuntimeError else 'unexpected-error')
    finally:
        if run is not None and not readonly:
            try:run.controls(True,False)
            except BaseException as error:report.update(status='stopped-first-failure',final_controls_error=type(error).__name__)
        if entry is not None:
            try:entry.close()
            except BaseException as error:report.update(status='stopped-first-failure',close_error=type(error).__name__)
        report['this_invocation_remote_calls']=transport.total
        evidence.save(ROOT/'metadata.json',report)
        print(canonical_json(dict(status=report['status'],remote_calls=transport.total,share_decision=report.get('share_decision'),
            feedback_real_next_day_verified=report['feedback_real_next_day_verified'],automatic_retries=0)),flush=True)
    return 1 if report['status']=='stopped-first-failure' else 0


if __name__=='__main__':raise SystemExit(main())
