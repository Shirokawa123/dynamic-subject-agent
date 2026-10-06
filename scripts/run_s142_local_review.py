"""Run the real S142 LOCAL Facade with synthetic outputs and simulated clocks.

No credential, remote Provider, user service or legacy root is accessed.
Exact builder tasks stay only in the newly owned local review resource.
"""
import argparse
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from functools import wraps
from threading import RLock
from uuid import uuid4

from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import (ModelGateway, ModelGatewayFailure,
    ModelResult, ModelTaskKind, ProviderAdapter, ProviderCapabilities, StructuredOutputMode)

REPO = Path(__file__).resolve().parents[1]
SCENARIO = REPO / 'docs/experiments/s142/scenarios.json'
ACTIVE_CHECKPOINT = None


def plain(value):
    if is_dataclass(value):
        return plain(asdict(value))
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value.value if hasattr(value, 'value') else value


def digest(value):
    return sha256(canonical_json(plain(value)).encode('utf-8')).hexdigest()


class SafeCheckpoints:
    """Own partial review files only; never query or write business state."""
    def __init__(self, base, scenario):
        self.base, self.scenario = base, scenario
        self.runs, self.events, self.completed = [], [], {}
        self.status, self.error_type = 'running', None
        self.io_error_types, self.lock = [], RLock()
        self.last_exact_sha256 = None

    def register(self, run):
        with self.lock:
            self.runs.append(run)
            self.capture()

    def begin(self, run, label):
        with self.lock:
            event = dict(branch=run.name, stage=label, status='running', error_type=None,
                calls_before=len(run.adapter.calls), calls_after=len(run.adapter.calls))
            self.events.append(event)
            self.capture()
            return event

    def end(self, run, event, result=None, error=None):
        with self.lock:
            event.update(status='failed' if error is not None else 'completed',
                error_type=None if error is None else type(error).__name__, calls_after=len(run.adapter.calls))
            if isinstance(result, dict) and 'checks' in result:
                self.completed[run.name] = {key:value for key,value in result.items() if key != 'actual_tasks'}
            if error is not None:
                self.status, self.error_type = 'failed-partial', type(error).__name__
            self.capture()

    def fail(self, error):
        with self.lock:
            self.status, self.error_type = 'failed-partial', type(error).__name__
            for event in self.events:
                if event['status'] == 'running':
                    event.update(status='failed', error_type=self.error_type)
            self.capture()

    def capture(self):
        # Observers cannot turn a checkpoint I/O problem into a model/domain
        # failure. The outer runner reports the I/O failure without its text.
        with self.lock:
            try:
                exact = dict(version='s142-local-partial-exact-1', status=self.status,
                    simulated_outputs=True, simulated_time=True, remote_calls=0, credential_reads=0,
                    scenario_sha256=digest(self.scenario), branches=[dict(branch=run.name,
                        actual_tasks=deepcopy(run.adapter.calls)) for run in self.runs])
                safe = dict(version='s142-local-safe-checkpoint-1', status=self.status,
                    error_type=self.error_type, simulated_outputs=True, simulated_time=True,
                    remote_calls=0, credential_reads=0, scenario_sha256=digest(self.scenario),
                    checkpoint_io_error_types=self.io_error_types[:], events=deepcopy(self.events),
                    branches=[dict(branch=run.name, local_model_calls=len(run.adapter.calls),
                        stages=deepcopy(run.stages), checks=self.completed.get(run.name, {}).get('checks', {}),
                        tasks=[dict(stage=task['stage'], kind=task['kind'],
                            preview_sha256=digest(task['preview']), output_sha256=task.get('output_sha256'),
                            simulated_failure=task.get('simulated_failure', False)) for task in run.adapter.calls])
                        for run in self.runs])
                for name, value in (('partial-exact-unsent-previews.json', exact), ('partial-metadata.json', safe)):
                    exact_sha = digest(value) if name == 'partial-exact-unsent-previews.json' else None
                    if exact_sha is not None and exact_sha == self.last_exact_sha256:
                        continue
                    target = self.base/name
                    temporary = self.base/(name+'.next')
                    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
                    temporary.replace(target)
                    if exact_sha is not None:
                        self.last_exact_sha256 = exact_sha
            except Exception as error:
                name = type(error).__name__
                if name not in self.io_error_types:
                    self.io_error_types.append(name)


def checkpointed(function):
    @wraps(function)
    def call(run, *args, **kwargs):
        recorder = run.checkpoint
        label = args[0] if args and type(args[0]) is str else function.__name__
        event = None if recorder is None else recorder.begin(run, label)
        try:
            result = function(run, *args, **kwargs)
        except BaseException as error:
            if recorder is not None:
                recorder.end(run, event, error=error)
            raise
        if recorder is not None:
            recorder.end(run, event, result=result)
        return result
    return call


class SimulatedTime:
    def __init__(self):
        self.seconds = 0.0
        self.day = '2026-10-06'

    def now(self):
        return self.seconds

    def civil_day(self):
        return self.day


class SyntheticLocalAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities('local-s142-review', 'synthetic-fixed-output', True,
        (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self):
        self.calls, self.label = [], ''
        self.share = True
        self.fail_next = False
        self.choice_number = 0
        self.observer = None

    def checkpoint(self):
        if self.observer is not None:
            self.observer()

    def invoke(self, task):
        self.calls.append(dict(stage=self.label, kind=task.kind.value,
            preview=deepcopy(plain(task.payload)), synthetic_output=True))
        self.checkpoint()
        if self.fail_next:
            self.fail_next = False
            self.calls[-1]['simulated_failure'] = True
            self.checkpoint()
            raise ModelGatewayFailure('provider-task-failed')
        payload = task.payload['payload']
        if task.kind is ModelTaskKind.LIVING_ACTIVITY_CHOICE:
            self.choice_number += 1
            actions = payload['current_activity']['allowed_actions']
            action = next(item for item in ('start', 'revise', 'keep', 'rework', 'defer') if item in actions)
            plan = dict(subject='合成验收用窗边静物',
                composition='固定合成文字方案第' + str(self.choice_number) + '版：主体在中央，背景简洁，左侧保留空白。',
                focus='仅检查实际提交与依赖过滤，不判断人物效果。') if action in ('start', 'revise') else None
            value = dict(action=action, plan=plan, reason_code='balance-space',
                basis_refs=['E1'] if payload['shared_experience'] else [],
                decision_note='固定合成输出；模拟机会不代表现实中画过图片。')
        elif task.kind is ModelTaskKind.LIVING_ACTIVITY_SHARE:
            value = dict(share=self.share, reply_text='【LOCAL合成】这版文字方案保留左侧空白，想让窗边主体更安静。' if self.share else '', language='zh')
        elif task.kind is ModelTaskKind.LIVING_ACTIVITY_REPLY:
            share = payload['evidence']['latest_share']
            value = dict(reply_text='【LOCAL合成S1接话】'+share['text']+'；这是固定合成接话。'
                if share is not None else '【LOCAL合成普通回复】只验证本地提交，不作为人物体验。', language='zh')
        else:
            raise ValueError('Unexpected task; no fallback or remote adapter exists.')
        self.calls[-1]['output_sha256'] = digest(value)
        self.checkpoint()
        return ModelResult(task.kind, value)


class Run:
    def __init__(self, base, name, scenario):
        self.name, self.scenario = name, scenario
        self.adapter, self.time = SyntheticLocalAdapter(), SimulatedTime()
        self.stages, self.checkpoint = [], ACTIVE_CHECKPOINT
        if self.checkpoint is not None:
            self.checkpoint.register(self)
            self.adapter.observer = self.checkpoint.capture
            setup_event = self.checkpoint.begin(self, 'material-and-root-setup')
        from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
        from dynamic_subject_agent.application import ApplicationFacade
        from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product
        from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
        from dynamic_subject_agent.original_whole_use_preparation import OriginalWholeUsePreparationRequest
        from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
        from dynamic_subject_agent.living_activity import living_contract
        package = REPO / '.local_indexes/eromanga-sensei/s102/full-definition-v2.json'
        review = ApplicationFacade.preview_original_character_whole_use_preparation(
            OriginalWholeUsePreparationRequest(package, APPROVED_BINDING['definition_basis'],
                APPROVED_BINDING['runtime_asset_sha'], APPROVED_BINDING['persona_digest'],
                APPROVED_BINDING['subject_id'], APPROVED_BINDING['anchor_id']))
        if review.status != 'previewed' or review.review_basis != APPROVED_BINDING['review_basis']:
            raise ValueError('Existing exact material binding must match before LOCAL creation.')
        root = base / name
        if root.exists():
            raise ValueError('Existing resource retained; no overwrite or automatic retry.')
        self.config = LocalProductConfig(root / 'DynamicSubjectAgent/m0/experiments', root / 'state.json')
        with open_local_product(self.config, cognition=DormantDeepSeekCognition()) as author:
            frozen = author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(
                package.read_text(encoding='utf-8'), APPROVED_BINDING['definition_basis'], True, True))
            if frozen.status != 'created':
                raise ValueError('Fresh dormant identity required.')
            self.identity_id = frozen.view.identity_id
        self.contract = living_contract(APPROVED_BINDING)
        self.product = self.opening()
        if self.checkpoint is not None:
            self.checkpoint.end(self, setup_event)

    @checkpointed
    def opening(self):
        from dynamic_subject_agent.living_activity import LivingClock
        from dynamic_subject_agent.local_product import open_living_activity_product_local
        return open_living_activity_product_local(self.config, gateway=ModelGateway(self.adapter),
            identity_id=self.identity_id, clock=LivingClock(self.time.now), day=self.time.civil_day)

    def view(self):
        result = self.product.application.query_living_activity()
        if result.status != 'available' or type(result.view) is not dict:
            raise ValueError('Verified LOCAL living view required: ' + result.status + ':' + str(result.problem_code))
        return plain(result.view)

    def history(self):
        from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
        result = self.product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
            self.product.profile_id, self.product.timeline_id))
        if result.status.value != 'available' or result.projection is None:
            raise ValueError('Verified conversation history required.')
        return plain(result.projection.turns)

    @checkpointed
    def controls(self, label, *, paused=None, sharing_enabled=None):
        from dynamic_subject_agent.living_activity import LivingControlRequest
        before = len(self.adapter.calls)
        request = LivingControlRequest(self.product.profile_id, self.product.timeline_id, str(uuid4()),
            self.view()['permission']['revision'], paused, sharing_enabled, True)
        result = self.product.application.set_living_controls(request)
        if result.status != 'committed' or len(self.adapter.calls) != before:
            raise ValueError('Explicit controls must commit with zero model requests.')
        self.stages.append(dict(stage=label, synthetic_output=True, simulated_time=True,
            local_calls=0, status=result.status, permission=plain(result.view)))

    @checkpointed
    def action(self, label, action, *, expected='committed', calls=1, replay=True, revision=None):
        from dynamic_subject_agent.living_activity import LivingActionRequest
        before = len(self.adapter.calls)
        request = LivingActionRequest(self.product.profile_id, self.product.timeline_id, str(uuid4()),
            self.view()['revision'] if revision is None else revision, action,
            's142-local-owner-session' if action == 'online' else '')
        preview = None
        if expected == 'committed':
            candidate = self.product.application.preview_living_activity('share' if action == 'share' else 'choice')
            if candidate.status != 'previewed':
                raise ValueError('Actual builder preview required before task.')
            preview = plain(candidate.view)
        self.adapter.label = label
        result = self.product.application.advance_living_activity(request)
        count = len(self.adapter.calls) - before
        row = dict(stage=label, trigger=action, synthetic_output=True, simulated_time=True,
            status=result.status, problem_code=result.problem_code, local_calls=count)
        self.stages.append(row)
        if result.status != expected or count != calls or count > 1:
            raise ValueError('Unexpected LOCAL action stage: ' + canonical_json(row))
        if calls and preview is not None:
            row['preview_equals_actual_task'] = self.adapter.calls[-1]['preview'] == preview
            if not row['preview_equals_actual_task']:
                raise ValueError('Actual task differs from the current builder preview.')
        if replay and expected == 'committed':
            replayed = self.product.application.advance_living_activity(request)
            queried = self.product.application.query_living_activity(request)
            row['same_nonce_and_query_zero_calls'] = replayed.status == queried.status == 'replayed' and len(self.adapter.calls) == before+calls
            if not row['same_nonce_and_query_zero_calls']:
                raise ValueError('Canonical receipt cannot replay with zero calls.')
        return row

    @checkpointed
    def send(self, label, text):
        from dynamic_subject_agent.timeline import SubjectCommand
        before = len(self.adapter.calls)
        previous_history = self.history()
        candidate = self.product.application.preview_living_activity('reply', text)
        if candidate.status != 'previewed' or len(self.adapter.calls) != before:
            raise ValueError('Actual readonly reply builder preview required with zero model requests.')
        exact_preview = plain(candidate.view)
        self.adapter.label = label
        response = self.product.application.submit(SubjectCommand.contribute_utterance(
            target_profile_id=self.product.profile_id, target_timeline_id=self.product.timeline_id,
            declared_intent='ask-collaborator-status', utterance=text, language='zh',
            provenance='project-original'), idempotency_key=str(uuid4()))
        if response.status.value == 'pending':
            response = self.product.application.wait(response.operation_ref, timeout_seconds=30)
        count = len(self.adapter.calls)-before
        row = dict(stage=label, trigger='ordinary-user-message', synthetic_output=True,
            simulated_time=True, status=response.status.value, local_calls=count)
        self.stages.append(row)
        committed = self.history()
        if (response.status.value != 'terminal' or response.projection is None
            or response.projection.failure_code is not None or count != 1
            or len(committed) != len(previous_history)+1
            or committed[-1]['user_text'] != text
            or committed[-1]['head_sequence'] != response.projection.timeline_head_sequence
            or digest(dict(reply_text=committed[-1]['assistant_text'], language=committed[-1]['assistant_language']))
                != self.adapter.calls[-1]['output_sha256']):
            raise ValueError('Single LOCAL ordinary reply did not commit.')
        row['canonical_complete_round_and_exact_output_verified'] = True
        row['preview_equals_actual_task'] = self.adapter.calls[-1]['preview'] == exact_preview
        if not row['preview_equals_actual_task']:
            raise ValueError('Actual reply task differs from readonly builder preview.')
        return self.adapter.calls[-1]['preview']

    @checkpointed
    def select_source(self):
        from dynamic_subject_agent.shared_activity import SharedExperienceRequest
        self.send('source-chat', self.scenario['source_message'])
        before = len(self.adapter.calls)
        selected = self.product.application.set_shared_experience(SharedExperienceRequest(
            self.product.profile_id, self.product.timeline_id, str(uuid4()), self.view()['revision'],
            self.history()[-1]['head_sequence'], self.scenario['selected_quote'], True))
        if selected.status != 'committed' or len(self.adapter.calls) != before:
            raise ValueError('Exact committed source selection must use zero model requests.')
        for index, text in enumerate(self.scenario['gap_messages']):
            self.send('source-gap-' + str(index+1), text)
        if self.scenario['selected_quote'] in ''.join(turn['user_text'] for turn in self.history()[-2:]):
            raise ValueError('Selected source must be outside the recent two-turn window.')

    @checkpointed
    def disable_source(self):
        from dynamic_subject_agent.shared_activity import SharedExperienceRequest
        before = len(self.adapter.calls)
        result = self.product.application.set_shared_experience(SharedExperienceRequest(
            self.product.profile_id, self.product.timeline_id, str(uuid4()), self.view()['revision'], None, '', True))
        if result.status != 'committed' or len(self.adapter.calls) != before:
            raise ValueError('Source deactivation must commit with zero calls.')

    @checkpointed
    def reopen(self, label):
        before, history, view = len(self.adapter.calls), self.history(), self.view()
        self.product.close()
        self.product = self.opening()
        if self.history() != history or self.view() != {**view, 'online_seconds': 0.0} or len(self.adapter.calls) != before:
            raise ValueError('Reopen changed canonical state or generated a task.')
        self.stages.append(dict(stage=label, synthetic_output=True, simulated_time=True,
            local_calls=0, status='reopened', canonical_state_unchanged=True))

    @checkpointed
    def finish(self, checks):
        view = self.view()
        self.product.close()
        return dict(branch=self.name, synthetic_output=True, simulated_time=True,
            local_model_calls=len(self.adapter.calls), stages=self.stages, checks=checks,
            final_view_sha256=digest(view), actual_tasks=self.adapter.calls)


def primary(base, scenario):
    run = Run(base, 'online-share-followup', scenario)
    try:
        initial = run.view()
        assert all(initial['permission'][key] == value for key,value in
            dict(paused=True, sharing_enabled=False, revision=0, needs_attention=False).items())
        assert initial['permission'].get('source_blocked', False) is False
        run.action('default-paused', 'simulation', expected='no-op', calls=0)
        run.select_source()
        run.controls('explicit-controls-on', paused=False, sharing_enabled=True)
        online_revision = run.view()['revision']
        run.action('simulated-online-baseline', 'online', expected='no-op', calls=0, revision=online_revision)
        for index in range(90):
            run.time.seconds += 10
            run.action('simulated-online-' + str(index+1), 'online', expected='committed' if index == 89 else 'no-op',
                calls=1 if index == 89 else 0, revision=online_revision)
        before_history = run.history()
        run.action('independent-share-true', 'share')
        view = run.view()
        assert len(view['shares']) == 1 and view['considered'][-1]['share'] is True
        assert run.history() == before_history
        share = {'text': view['shares'][-1]['text']}
        run.reopen('share-restart')
        run.action('same-result-no-repeat', 'share', expected='no-op', calls=0)
        run.action('next-actual-plan-before-response', 'simulation')
        run.action('awaiting-reply-no-new-topic', 'share', expected='no-op', calls=0)
        previews = [run.send('ordinary-followup-' + str(index+1), text)
            for index, text in enumerate(scenario['followup_messages'])]
        assert [preview['payload']['evidence']['latest_share'] for preview in previews] == [share, share, None]
        assert all(share['text'] not in canonical_json(preview['payload']['exchange']) for preview in previews[:1])
        third_exchange = canonical_json(previews[2]['payload']['exchange'])
        assert share['text'] not in third_exchange and '【LOCAL合成S1接话】' not in third_exchange
        assert not any(text in third_exchange for text in scenario['followup_messages'][:2])
        return run.finish(dict(default_paused_sharing_off=True, simulated_900_seconds_only_one_choice=True,
            share_committed_as_assistant_origin_no_fake_user_turn=True, share_restart_zero_calls=True,
            considered_once=True, awaiting_reply_zero_share_calls=True,
            same_share_in_two_successful_rounds_then_absent=True,
            third_round_filters_complete_S1_derived_exchange=True, selected_E1_outside_recent_window=True))
    finally:
        run.product.close()


def false_branch(base, scenario):
    run = Run(base, 'false-and-no-change', scenario)
    try:
        run.controls('controls-on', paused=False, sharing_enabled=True)
        run.action('no-eligible-result', 'share', expected='no-op', calls=0)
        run.action('new-plan', 'simulation')
        run.adapter.share = False
        before = run.history()
        run.action('independent-share-false', 'share')
        state = run.view()
        assert state['shares'] == [] and state['considered'][-1]['share'] is False and run.history() == before
        run.action('false-considered-once', 'share', expected='no-op', calls=0)
        run.reopen('false-restart')
        return run.finish(dict(no_new_result_zero_calls=True, false_canonical_once=True,
            false_no_assistant_share_no_fake_user_round=True, false_no_daily_topic_consumption=True, reopen_zero_calls=True))
    finally:
        run.product.close()


def revoked_branch(base, scenario):
    run = Run(base, 'source-deactivated', scenario)
    try:
        run.select_source()
        run.controls('controls-on', paused=False, sharing_enabled=True)
        run.action('dependent-plan', 'simulation')
        run.action('dependent-share', 'share')
        run.send('dependent-followup', scenario['followup_messages'][0])
        run.disable_source()
        state = run.view()
        assert state['source'] is None and state['current_plan'] is None and state['visible_result'] is None and state['latest_share'] is None
        preview = run.send('after-source-deactivation', '换个话题，说说学习时比较两种方法的想法。')
        evidence = preview['payload']['evidence']
        assert evidence == dict(shared_experience=None, activity_result=None, latest_share=None)
        forbidden = [scenario['selected_quote'], '合成验收用窗边静物', '【LOCAL合成】这版文字方案',
            '【LOCAL合成S1接话】', scenario['followup_messages'][0]]
        assert not any(text in canonical_json(preview['payload']['exchange']) for text in forbidden)
        run.reopen('deactivated-restart')
        return run.finish(dict(source_plan_result_share_removed_together=True,
            dependent_complete_dialogue_not_reintroduced=True, source_deactivation_zero_calls=True,
            after_deactivation_actual_reply_task_has_null_evidence=True, reopen_zero_calls=True))
    finally:
        run.product.close()


def failure_branch(base, scenario):
    run = Run(base, 'paused-and-failure', scenario)
    try:
        run.controls('controls-on', paused=False, sharing_enabled=True)
        run.action('first-plan', 'simulation')
        run.controls('explicit-pause', paused=True)
        run.action('paused-choice', 'simulation', expected='no-op', calls=0)
        run.action('paused-share', 'share', expected='no-op', calls=0)
        run.controls('explicit-resume', paused=False)
        before = run.view()['visible_result']
        run.adapter.fail_next = True
        run.action('simulated-technical-failure', 'simulation', expected='failed-closed', replay=False)
        state = run.view()
        assert state['permission']['paused'] is True and state['permission']['needs_attention'] is True
        assert state['visible_result'] == before
        run.action('attention-stops-auto-choice', 'simulation', expected='no-op', calls=0)
        run.action('attention-stops-share', 'share', expected='no-op', calls=0)
        run.reopen('attention-restart')
        run.controls('explicit-check-and-resume', paused=False)
        assert run.view()['permission']['needs_attention'] is False
        run.action('new-opportunity-after-explicit-resume', 'simulation')
        assert run.view()['visible_result'] != before
        return run.finish(dict(pause_zero_calls=True, explicit_resume_required=True,
            simulated_failure_no_event_or_retry=True, failure_paused_needs_attention=True,
            further_auto_actions_zero_calls=True, reopen_zero_calls=True,
            explicit_failure_resume_new_nonce_next_plan=True))
    finally:
        run.product.close()


def daily_branch(base, scenario):
    run = Run(base, 'daily-topic-limit', scenario)
    try:
        run.controls('controls-on', paused=False, sharing_enabled=True)
        for index in range(2):
            run.action('new-plan-' + str(index+1), 'simulation')
            run.action('new-topic-' + str(index+1), 'share')
            run.send('answer-' + str(index+1), scenario['followup_messages'][index])
        run.action('keep-no-new-text-version', 'simulation')
        run.action('keep-not-eligible', 'share', expected='no-op', calls=0)
        run.action('third-new-plan', 'simulation')
        run.action('daily-third-topic-suppressed', 'share', expected='no-op', calls=0)
        assert len(run.view()['shares']) == 2
        return run.finish(dict(two_true_topics_utc8_day=True, keep_is_not_new_eligible_plan=True,
            daily_third_topic_zero_share_calls=True, daily_limit_is_not_model_call_budget=True))
    finally:
        run.product.close()


def reject_remote(base):
    from dynamic_subject_agent.local_product import LocalProductConfig, open_living_activity_product_local
    class RemoteForbidden(ProviderAdapter):
        capabilities = ProviderCapabilities('deepseek', 'deepseek-flash', False, (StructuredOutputMode.JSON_OBJECT,))
        def invoke(self, task):
            raise AssertionError('A remote adapter must never be invoked.')
    root = base/'remote-rejection-no-registry'
    try:
        open_living_activity_product_local(LocalProductConfig(root/'experiments', root/'state.json'),
            gateway=ModelGateway(RemoteForbidden()), identity_id='invalid-no-registry')
    except ValueError as error:
        if str(error) != 'LOCAL-only living gateway required before any identity access' or root.exists():
            raise
    else:
        raise ValueError('LOCAL composition did not reject remote before registry access.')


def main():
    global ACTIVE_CHECKPOINT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', default=str(uuid4()))
    parser.add_argument('--base', type=Path)
    args = parser.parse_args()
    if re.fullmatch(r'[A-Za-z0-9-]{1,80}', args.run_id) is None:
        raise SystemExit('Simple nonempty run id required.')
    parent = args.base or Path(os.environ['LOCALAPPDATA'])/'DynamicSubjectAgent/living-activity-development/s142'
    base = parent.resolve()/args.run_id
    if base.exists():
        raise SystemExit('Existing resources retained; use a new explicit run id after investigation.')
    scenario = json.loads(SCENARIO.read_text(encoding='utf-8'))
    base.mkdir(parents=True, exist_ok=False)
    checkpoint = SafeCheckpoints(base, scenario)
    ACTIVE_CHECKPOINT = checkpoint
    checkpoint.capture()
    try:
        execute(base, scenario, checkpoint)
        if checkpoint.io_error_types:
            raise OSError('safe checkpoint I/O failed')
        checkpoint.status = 'complete'
    except BaseException as error:
        checkpoint.fail(error)
        print(json.dumps(dict(status='failed-partial', error_type=type(error).__name__,
            checkpoint_io_error_types=checkpoint.io_error_types,
            remote_calls=0, credential_reads=0,
            partial_metadata_path=str(base/'partial-metadata.json')), ensure_ascii=False), flush=True)
        raise SystemExit(1) from None
    finally:
        checkpoint.capture()
        ACTIVE_CHECKPOINT = None


def execute(base, scenario, checkpoint):
    reject_remote(base)
    rows = []
    for operation in (primary, false_branch, revoked_branch, failure_branch, daily_branch):
        row = operation(base, scenario)
        rows.append(row)
        print(json.dumps(dict(branch=row['branch'], local_model_calls=row['local_model_calls'],
            simulated_outputs=True, simulated_time=True, checks=row['checks']), ensure_ascii=False), flush=True)
    from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
    from dynamic_subject_agent.living_activity import living_contract
    preview = dict(version='s142-local-exact-review-1', simulated_outputs=True, simulated_time=True,
        remote_calls=0, credential_reads=0, material_binding=APPROVED_BINDING,
        contract=living_contract(APPROVED_BINDING), scenario_sha256=digest(scenario), branches=rows)
    output = base/'exact-unsent-previews.json'
    with output.open('x', encoding='utf-8') as target:
        json.dump(preview, target, ensure_ascii=False, indent=2)
    metadata = dict(version=preview['version'], simulated_outputs=True, simulated_time=True,
        remote_calls=0, credential_reads=0, remote_rejected_before_registry=True,
        scenario_sha256=preview['scenario_sha256'], local_preview_sha256=digest(preview),
        contract_sha256=digest(preview['contract']), exact_local_preview_path=str(output), branches=[
            {key:value for key,value in row.items() if key != 'actual_tasks'} for row in rows])
    with (base/'metadata.json').open('x', encoding='utf-8') as target:
        json.dump(metadata, target, ensure_ascii=False, indent=2)
    print(json.dumps({key:value for key,value in metadata.items() if key != 'branches'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
