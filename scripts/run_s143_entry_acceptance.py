"""One frozen S143 HTTP entry scene; main alone may run --execute.

--preflight is read-only and opens no identity, service, audit or credential.
Actual online opportunity uses the unmodified production monotonic clock.
Reports contain closed metadata/hashes only; HTTP bodies remain transient.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
from threading import Thread
from time import perf_counter, sleep
from urllib.request import Request, ProxyHandler, build_opener
from uuid import uuid4

import run_s142_live_acceptance as prior

REPO = Path(__file__).resolve().parents[1]
REVIEW_BASIS = prior.REVIEW_BASIS
SCENARIO_SHA = prior.SCENARIO_SHA
OBSERVER_SHA = '50e9998db00185271a0c20464bf05aef2fd885760864f6c932662b7d833efd64'
SCENE_PATH = REPO/'docs/experiments/s143/scene.json'
SCENE_SHA = 'badb3381b75958adb20c18bd7b54d24bb467dff3175ba5e7ecdb3e3149eda508'
OUTPUT = REPO/'docs/reports/2026-10-07-slice-143/live-entry-metadata.json'
ROOT_RELATIVE = Path('DynamicSubjectAgent/living-activity-development/s143/live-http-first-20261007-1')
TEMP_PARENT = REPO/'.tmp-s143-live-entry-parent'
PURPOSES = prior.PURPOSES
AcceptanceStopped, require = prior.AcceptanceStopped, prior.require
plain, digest = prior.plain, prior.digest


def preflight():
    """Verify immutable scope and unused resources without constructing them."""
    review = json.loads((REPO/'docs/experiments/s142/review.json').read_text(encoding='utf-8'))
    scenarios = json.loads((REPO/'docs/experiments/s142/scenarios.json').read_text(encoding='utf-8'))
    scene = json.loads(SCENE_PATH.read_text(encoding='utf-8'))
    from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
    from dynamic_subject_agent.living_activity_live import ApprovedLivingActivityGrant
    require(sha256(Path(prior.__file__).read_bytes()).hexdigest() == OBSERVER_SHA, 'safe-observer-source-changed')
    require(review['review_basis'] == digest(review['review']) == REVIEW_BASIS, 'approved-review-pin-changed')
    require(digest(scenarios) == SCENARIO_SHA == review['review']['scenario_sha256'], 'approved-scenarios-changed')
    require(digest(scene) == SCENE_SHA and scene['review_basis'] == REVIEW_BASIS
        and scene['approved_scenario_sha256'] == SCENARIO_SHA, 's143-scene-pin-changed')
    require(scene['followup_messages'] == scenarios['followup_messages']
        and scene['protocol'] == review['review']['protocol']
        and scene['policy_sha256'] == review['review']['policy_sha256'], 'approved-purposes-or-material-changed')
    require(digest(APPROVED_BINDING) == scene['material_binding_sha256']
        and APPROVED_BINDING == review['review']['material_binding'], 'approved-binding-changed')
    ApprovedLivingActivityGrant(REVIEW_BASIS, True).validate()  # No resolver or key read.
    contract = scene['scene']
    require(contract['time_is_simulated'] is False and contract['opportunity_seconds'] == 900
        and contract['heartbeat_interval_seconds'] == 5 and contract['session_lease_seconds'] == 15
        and contract['presence_endpoint'] == '/living-presence' and contract['presence_model_free'] is True
        and contract['presence_consumes_opportunity'] is False
        and contract['maximum_first_requests'] == 5 and contract['stage_request_limit'] == 1
        and contract['automatic_retries'] == 0 and all(contract[key] is True for key in (
            'stop_on_first_technical_failure', 'stop_when_no_eligible_new_text_plan',
            'stop_when_share_false', 'retain_first_result_without_resampling')), 'first-scene-stopping-bound-changed')
    local = Path(os.environ.get('LOCALAPPDATA', ''))
    require(local.is_absolute() and local.resolve() == Path('C:/Users/30252/AppData/Local').resolve(),
        'real-local-appdata-required')
    root = local/ROOT_RELATIVE
    require(scene['resource'] == 'LOCALAPPDATA/'+ROOT_RELATIVE.as_posix()
        and scene['report'] == OUTPUT.relative_to(REPO).as_posix(), 'independent-resources-changed')
    require(not root.exists() and not OUTPUT.exists() and not OUTPUT.with_name(OUTPUT.name+'.next').exists(),
        'existing-first-resources-retained')
    require(OUTPUT.parent.is_dir(), 'report-directory-required')
    require(all(Path(os.environ.get(key, '')).is_absolute()
        and Path(os.environ[key]).resolve() == TEMP_PARENT.resolve() for key in ('TEMP', 'TMP')),
        'own-repo-temp-parent-required')
    require(TEMP_PARENT.is_dir(), 'own-repo-temp-parent-missing')
    return scene, root


class SafeReport(prior.SafeReport):
    """Independent output; never call the S142 output writer."""
    def __init__(self, root, scene):
        super().__init__(root, scene)
        self.data.update(version='s143-entry-http-first-live-2', first_scene_sha256=SCENE_SHA,
            safe_observer_sha256=OBSERVER_SHA, runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
            time_is_simulated=False, http_driven_online=True, browser_visible_900_seconds_verified=False,
            independent_model_free_presence=True, presence_consumes_opportunity=False,
            draft_browser_behavior_verified=False, automatic_system_service=False,
            progress=dict(heartbeat_count=0, uninterrupted_owner_seconds=0.0),
            status='preparing')

    def save(self):
        with self.lock:
            try:
                self.data['checkpoint_io_error_types'] = self.io_error_types[:]
                temporary = OUTPUT.with_name(OUTPUT.name+'.next')
                temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
                temporary.replace(OUTPUT)
                return True
            except Exception as error:
                name = type(error).__name__
                if name not in self.io_error_types:
                    self.io_error_types.append(name)
                return False

    def begin(self, label, **metadata):
        row = dict(stage=label, status='started', error_type=None, time_is_simulated=False, **metadata)
        with self.lock:
            self.data['stages'].append(row)
            self.checked_save('checkpoint-before-stage-failed')
        return row


class EntryRun(prior.FirstRun):
    def __init__(self, root, scene, report):
        self.root, self.scene, self.report = root, scene, report
        self.audit_path = root/'provider-audit'
        self.entry = self.server = self.server_thread = None
        self.transport = None
        self.observations = []
        self.opener = build_opener(ProxyHandler({}))
        self.token = None
        self.choice_request = self.share_request = None
        self.owner = str(uuid4())

    @property
    def product(self):
        return None if self.entry is None else self.entry.product

    def http(self, path, payload=None, *, text=False):
        require(self.server is not None and self.server_thread.is_alive(), 'own-http-server-unverified')
        headers = {} if payload is None else {'Content-Type': 'application/json', 'X-Chat-Token': self.token}
        request = Request(self.base_url+path, headers=headers, data=None if payload is None
            else json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        with self.opener.open(request, timeout=10) as response:
            require(response.status == 200, 'entry-http-response-unverified')
            body = response.read(4*1024*1024+1)
            require(len(body) <= 4*1024*1024, 'entry-http-body-bound-exceeded')
        value = body.decode('utf-8')
        if text:
            return value
        value = json.loads(value)
        require(type(value) is dict, 'entry-http-object-required')
        return value

    def http_state(self):
        state = self.http('/status')
        living, history = state.get('living_activity'), state.get('history')
        require(type(living) is dict and living.get('status') == 'available'
            and living.get('view') == self.view(), 'http-living-differs-from-canonical')
        require(type(history) is dict and history.get('status') == 'available'
            and history.get('turns') == [{key: row[key] for key in ('user_text', 'assistant_text')}
                for row in self.history()], 'http-history-differs-from-canonical')
        require(state.get('character', {}).get('status') == 'active', 'entry-character-unverified')
        return state

    def create(self):
        from serve_living_activity_chat import LivingActivityChatEntry
        from living_activity_chat import APPLICATION_ID, living_activity_server
        row = self.report.begin('create-own-entry-and-http-defaults', maximum_requests=0)
        self.transport = prior.ObservedTransport(self.report)
        self.transport.arm(row['stage'])
        self.entry = LivingActivityChatEntry(self.root, live=False, transport=self.transport,
            audit_path=self.audit_path, observations=self.observations)
        self.server = living_activity_server(self.product, reopen=self.entry.reopen,
            port=0, allow_simulation=False)
        require(self.server.server_address[0] == '127.0.0.1' and self.server.server_port not in (8790, 8791, 8792),
            'independent-loopback-port-required')
        self.base_url = 'http://127.0.0.1:'+str(self.server.server_port)
        self.server_thread = Thread(target=self.server.serve_forever, name='s143-own-http-entry', daemon=True)
        self.server_thread.start()
        page = self.http('/', text=True)
        match = re.search(r"\bconst\s+TOKEN\s*=\s*'([A-Za-z0-9_-]{30,})'", page)
        require(match is not None, 'entry-http-session-token-unverified')
        self.token = match.group(1)
        require(self.http('/health') == dict(application=APPLICATION_ID), 'own-http-health-mismatch')
        state = self.http_state(); view = state['living_activity']['view']
        require(self.history() == [] and view['source'] is None and view['phase'] == 'unstarted'
            and view['current_plan'] is None and view['shares'] == [] and view['considered'] == []
            and view['permission'] == dict(paused=True, sharing_enabled=False, revision=0,
                needs_attention=False, source_blocked=False)
            and self.counts() == 0 and self.transport.total_calls == 0, 'fresh-entry-preconditions-differ')
        require(self.http('/living-controls-query', {}).get('ok') is True, 'default-controls-query-unverified')
        row.update(status='complete', audit_before=0, audit_after=0, initial_page_sha256=sha256(page.encode()).hexdigest())
        self.scope_key = state['scope_key']
        self.report.data.update(server_port=self.server.server_port)
        self.report.data['checks']['fresh-empty-http-default-paused-sharing-off-zero-model'] = True
        self.audit(); self.report.checked_save('checkpoint-after-create-failed')
        self.reload('initial-http-reload-zero-model')

    def zero(self, label, action):
        before, sent = self.counts(), self.transport.total_calls
        row = self.report.begin(label, maximum_requests=0, audit_before=before)
        self.transport.arm(label)
        result = action()
        require(self.counts() == before and self.transport.total_calls == sent and not self.report.io_error_types,
            'zero-call-http-operation-generated-request')
        row.update(status='complete', audit_after=self.counts())
        self.audit(); self.report.checked_save('checkpoint-after-zero-http-operation-failed')
        return result

    def reload(self, label):
        def operation():
            before = self.fingerprint()
            require(self.http('/reload', {}).get('ok') is True, 'http-reload-unverified')
            self.http_state()
            require(self.fingerprint() == before, 'http-reload-changed-canonical-business-state')
        return self.zero(label, operation)

    def controls(self, *, paused, sharing_enabled, label):
        def operation():
            before = self.view()['permission']['revision']
            payload = dict(request_id=str(uuid4()), expected_permission_revision=before,
                paused=paused, sharing_enabled=sharing_enabled, confirmed=True)
            result = self.http('/living-controls', payload)
            require(result.get('ok') is True, 'explicit-http-controls-unverified')
            permission = self.http_state()['living_activity']['view']['permission']
            require(permission['paused'] is paused and permission['sharing_enabled'] is sharing_enabled
                and permission['revision'] == before+1, 'explicit-http-permission-differs')
            replay = self.http('/living-controls', payload)
            require(replay.get('ok') is True and self.view()['permission'] == permission, 'http-control-nonce-not-replayed')
        return self.zero(label, operation)

    def enable(self):
        self.controls(paused=False, sharing_enabled=True, label='explicit-http-unpause-enable-sharing')

    def preview(self, purpose, text=None):
        candidate = self.product.application.preview_living_activity(purpose, text)
        require(candidate.status == 'previewed', 'current-stage-preview-unavailable')
        return plain(candidate.view)

    def settle_living(self, result, request, kind):
        deadline = perf_counter()+150
        while result.get('living_status') == 'busy':
            require(perf_counter() < deadline, 'http-living-pending-delivery-unverified')
            sleep(1)
            self.report.data['stages'][-1]['status'] = 'pending'
            self.report.checked_save('pending-http-checkpoint-failed')
            result = self.http('/living-request', dict(kind=kind, request=request))
        return result

    def stage(self, label, purpose, request_id, preview, operation):
        before, sent, observed = self.counts(), self.transport.total_calls, len(self.observations)
        row = self.report.begin(label, purpose=purpose, request_id=request_id,
            audit_before=before, maximum_requests=1, expected_task_sha256=digest(preview))
        expected = self.transport.arm(label, preview, purpose)
        row.update(expected_wire_sha256=expected['wire_sha256'], expected_payload_sha256=expected['payload_sha256'],
            policy_sha256=expected['policy_sha256'])
        self.report.checked_save('checkpoint-before-http-model-stage-failed')
        result = operation()
        status = result.get('living_status', 'terminal' if result.get('ok') is True and result.get('settled') is True else 'unverified')
        row.update(status=status, audit_after=self.counts(), transport_count=self.transport.total_calls-sent,
            observations=[prior.safe_observation(value) for value in self.observations[observed:]])
        audit = self.audit()
        self.report.checked_save('checkpoint-after-http-model-stage-failed')
        require(self.counts()-before <= 1 and self.transport.total_calls-sent <= 1, 'single-stage-request-bound-exceeded')
        if status not in ('committed', 'replayed', 'terminal') or result.get('ok') is not True:
            self.report.data.update(status='stopped-on-first-technical-failure', stopped_stage=label, runner_exit_code=1)
            raise AcceptanceStopped('first-http-technical-failure')
        require(self.counts()-before == 1 and self.transport.total_calls-sent == 1 and len(audit) > before,
            'successful-http-stage-without-one-verified-request')
        wire = self.report.data['transport'][-1]; raw = wire.get('response_boundary', {})
        require(wire['status'] == 'response-received' and raw.get('http_status') == 200
            and raw.get('envelope_json') is True and raw.get('choices_count') == 1
            and raw.get('assistant_role') is True and raw.get('finish_reason') == 'stop'
            and raw.get('exact_task_schema') is True and not raw.get('duplicate_semantic_keys')
            and audit[-1]['status'] == 'complete' and audit[-1]['purpose'] == purpose
            and audit[-1]['request_digest'] == digest(preview)
            and audit[-1]['output_digest'] == raw.get('final_value_sha256'), 'http-raw-final-audit-or-preview-mismatch')
        row['raw_final_matches_completed_audit'] = True
        self.report.checked_save('checkpoint-after-http-raw-verification-failed')
        return result, row, raw

    def replay_living(self, kind, request, label):
        def operation():
            before = self.fingerprint()
            query = self.http('/living-request', dict(kind=kind, request=request))
            route = '/living-heartbeat' if kind == 'online' else '/living-share'
            replay = self.http(route, request)
            require(query.get('living_status') == replay.get('living_status') == 'replayed'
                and query.get('living_receipt') == replay.get('living_receipt')
                and query.get('living_settled') is True and replay.get('living_settled') is True
                and self.fingerprint() == before, 'http-original-living-nonce-not-replayed')
        self.zero(label, operation)

    def wait_presence(self):
        """Keep one real lease online; this stage cannot call a model."""
        clock_start = perf_counter()
        heartbeat_count, last_started, baseline_started = 0, None, None
        previous_seconds = 0.0
        permission = self.view()['permission']
        def business_fingerprint():
            living = dict(self.view())
            living.pop('online_seconds')
            return digest(dict(living=living, history=self.history(),
                context=self.product.application.query_whole_context_boundary()))
        original = business_fingerprint()
        def operation():
            nonlocal heartbeat_count, last_started, baseline_started, previous_seconds
            next_heartbeat, last_progress = clock_start, clock_start
            deadline = clock_start+960
            while True:
                now = perf_counter()
                require(now < deadline, 'one-online-opportunity-unverified-no-resampling')
                if now < next_heartbeat:
                    sleep(min(5.0, next_heartbeat-now))
                started = perf_counter()
                if last_started is not None:
                    require(started-last_started < 15, 'online-lease-gap-stop-no-catchup')
                before, sent = self.counts(), self.transport.total_calls
                result = self.http('/living-presence', dict(session_id=self.owner))
                heartbeat_count += 1
                status, code = result.get('presence_status'), result.get('presence_problem_code')
                presence = result.get('presence')
                require(result.get('ok') is True and status == 'available' and type(presence) is dict
                    and result.get('scope_key') == self.scope_key and presence.get('session_owner') is True
                    and presence.get('permission') == permission
                    and type(presence.get('opportunity_due')) is bool
                    and type(presence.get('online_seconds')) in (int, float)
                    and math.isfinite(presence['online_seconds'])
                    and previous_seconds <= presence['online_seconds'] <= 900,
                    'http-presence-owner-or-seconds-unverified')
                if heartbeat_count == 1:
                    require(code == 'online-baseline' and presence['online_seconds'] == 0
                        and presence['opportunity_due'] is False, 'first-online-baseline-unverified')
                    baseline_started = started
                elapsed = max(0.0, started-baseline_started)
                progress = dict(heartbeat_count=heartbeat_count, uninterrupted_owner_seconds=elapsed,
                    heartbeat_gap_seconds=0.0 if last_started is None else started-last_started,
                    presence_online_seconds=presence['online_seconds'], opportunity_due=presence['opportunity_due'],
                    presence_status='available')
                self.report.data['progress'] = progress
                self.report.checked_save('online-progress-checkpoint-failed')
                if perf_counter()-last_progress >= 55 or presence['opportunity_due']:
                    print(json.dumps(dict(status='online-progress', **progress), ensure_ascii=False), flush=True)
                    last_progress = perf_counter()
                require(self.counts() == before and self.transport.total_calls == sent,
                    'model-free-presence-generated-request')
                if presence['opportunity_due']:
                    require(code == 'online-ready' and presence['online_seconds'] == 900 and elapsed >= 900,
                        'presence-due-before-real-900-owner-seconds')
                    require(business_fingerprint() == original, 'model-free-presence-changed-canonical-business-state')
                    self.report.data['stages'][-1].update(online_owner_seconds_before_choice=elapsed,
                        heartbeat_count=heartbeat_count, canonical_business_unchanged=True)
                    return dict(elapsed=elapsed, last_started=started, baseline_started=baseline_started,
                        heartbeat_count=heartbeat_count)
                require(code == ('online-baseline' if heartbeat_count == 1 else 'no-decision-boundary'),
                    'presence-lease-continuity-unverified')
                previous_seconds = presence['online_seconds']
                last_started = started
                next_heartbeat = started+5
        return self.zero('real-monotonic-http-model-free-presence', operation)

    def online_choice(self):
        presence = self.wait_presence()
        preview = self.preview('choice')
        require(preview['payload']['shared_experience'] is None and preview['payload']['current_plan'] is None,
            'first-choice-has-unapproved-prior-material')
        self.choice_request = dict(request_id=str(uuid4()), expected_revision=self.view()['revision'], session_id=self.owner)
        request = self.choice_request
        def operation():
            require(perf_counter()-presence['last_started'] < 15, 'due-presence-lease-expired-before-choice')
            result = self.settle_living(self.http('/living-heartbeat', request), request, 'online')
            require(result.get('living_request_id') == request['request_id']
                and result.get('living_kind') == 'online' and result.get('living_settled') is True,
                'online-choice-original-result-unverified')
            if result.get('living_status') in ('committed', 'replayed'):
                require(presence['elapsed'] >= 900, 'choice-arrived-before-real-900-owner-seconds')
            return result
        _, row, raw = self.stage('one-http-online-choice-after-presence-due', PURPOSES[0], request['request_id'], preview, operation)
        row.update(online_owner_seconds_before_choice=presence['elapsed'], heartbeat_count=presence['heartbeat_count'])
        state = self.http_state()['living_activity']['view']; actual = state['visible_result']
        require(actual is not None and actual['event']['kind'] == raw['action']
            and (None if actual['plan'] is None else digest(actual['plan'])) == raw['plan_sha256']
            and actual['event']['simulated'] is False, 'raw-choice-or-real-event-differs-from-canonical')
        decision = self.product.application.query_shared_activity()
        require(decision.status == 'available' and type(decision.view) is dict, 'canonical-choice-decision-unverified')
        value = plain(decision.view['decision'])
        canonical = dict(action=value['action'], plan=actual['plan'], reason_code=value['reason_code'],
            basis_refs=value['basis_refs'], decision_note=value['decision_note'])
        require(digest(canonical) == raw['final_value_sha256'], 'raw-full-choice-differs-from-canonical')
        row.update(action=raw['action'], plan_sha256=raw['plan_sha256'], simulated_event=False,
            canonical_actual_plan_matches_raw=True, canonical_choice_value_sha256=digest(canonical))
        self.report.data['checks']['real-900-http-owner-single-choice-no-lease-reset'] = True
        self.report.checked_save('checkpoint-after-real-choice-failed')
        self.replay_living('online', self.choice_request, 'http-choice-nonce-replay-query-zero-model')
        if actual['event']['kind'] not in ('start', 'revise') or actual['plan'] is None:
            self.report.data.update(status='stopped-no-eligible-new-text-plan', first_choice_action=raw['action'])
            self.report.checked_save('checkpoint-after-no-eligible-stop-failed')
            return False
        self.actual_plan_sha256 = digest(actual['plan'])
        return True

    def share(self):
        preview = self.preview('share')
        require(preview['payload']['shared_experience'] is None
            and digest(preview['payload']['activity_result']['plan']) == self.actual_plan_sha256,
            'independent-share-has-wrong-actual-plan')
        before_history = self.history()
        self.share_request = dict(request_id=str(uuid4()), expected_revision=self.view()['revision'])
        request = self.share_request
        _, row, raw = self.stage('independent-http-share-consider', PURPOSES[1], request['request_id'], preview,
            lambda: self.settle_living(self.http('/living-share', request), request, 'share'))
        state = self.http_state(); view = state['living_activity']['view']
        require(len(view['considered']) == 1 and view['considered'][0]['share'] is raw['share']
            and self.history() == before_history, 'canonical-share-decision-or-assistant-origin-differs')
        row.update(share=raw['share'], share_chars=raw['reply_chars'], assistant_origin_no_fake_user_turn=True)
        if raw['share']:
            require(len(view['shares']) == 1 and sha256(view['shares'][0]['text'].encode('utf-8')).hexdigest() == raw['reply_sha256'],
                'raw-share-text-differs-from-canonical')
            self.share_text_sha256 = raw['reply_sha256']
            canonical = dict(share=True, reply_text=view['shares'][0]['text'], language='zh')
            row['raw_share_equals_canonical'] = True
        else:
            require(view['shares'] == [] and raw['reply_chars'] == 0, 'false-share-created-message')
            canonical = dict(share=False, reply_text='', language='zh')
        require(digest(canonical) == raw['final_value_sha256'], 'raw-full-share-differs-from-canonical')
        row['canonical_share_value_sha256'] = digest(canonical)
        self.report.checked_save('checkpoint-after-http-share-failed')
        self.replay_living('share', request, 'http-share-nonce-replay-query-zero-model')
        self.reload('http-share-restart-zero-model')
        self.replay_living('online', self.choice_request, 'http-choice-after-restart-query-zero-model')
        self.replay_living('share', request, 'http-share-after-restart-query-zero-model')
        if raw['share'] is False:
            self.report.data.update(status='stopped-first-share-false')
            self.report.checked_save('checkpoint-after-false-stop-failed')
            return False
        require(raw['share'] is True, 'share-boolean-unverified')
        return True

    def settle_reply(self, result, request):
        deadline = perf_counter()+150
        while result.get('pending') is not None:
            require(perf_counter() < deadline, 'http-reply-pending-delivery-unverified')
            sleep(1)
            self.report.data['stages'][-1]['status'] = 'pending'
            self.report.checked_save('pending-http-reply-checkpoint-failed')
            result = self.http('/request-result', request)
        return result

    def reply(self, index, text):
        preview = self.preview('reply', text); payload = preview['payload']; evidence = payload['evidence']
        require(payload['turn']['current_message'] == text and evidence['shared_experience'] is None
            and digest(evidence['activity_result']['plan']) == self.actual_plan_sha256,
            'reply-current-result-or-E1-differs')
        supplied = evidence['latest_share']
        require((supplied is not None and sha256(supplied['text'].encode('utf-8')).hexdigest() == self.share_text_sha256)
            if index < 2 else supplied is None, 'latest-share-two-successful-round-window-differs')
        expected_exchange = [] if index == 2 else [{key: turn[key] for key in ('user_text', 'assistant_text')}
            for turn in self.history()]
        require(payload['exchange'] == expected_exchange, 'actual-complete-derived-history-filter-differs')
        request = dict(request_id=str(uuid4()), text=text)
        previous_count = len(self.history())
        _, row, raw = self.stage('ordinary-http-followup-'+str(index+1), PURPOSES[2], request['request_id'], preview,
            lambda: self.settle_reply(self.http('/send', request), request))
        self.http_state()
        turns = self.history()
        require(len(turns) == previous_count+1 and turns[-1]['user_text'] == text
            and sha256(turns[-1]['assistant_text'].encode('utf-8')).hexdigest() == raw['reply_sha256'],
            'raw-reply-differs-from-exact-complete-canonical-round')
        canonical = dict(reply_text=turns[-1]['assistant_text'], language='zh')
        require(digest(canonical) == raw['final_value_sha256'], 'raw-full-reply-differs-from-canonical')
        row.update(reply_chars=raw['reply_chars'], reply_sha256=raw['reply_sha256'], raw_reply_equals_canonical=True,
            latest_share_sha256=None if supplied is None else self.share_text_sha256,
            exchange_complete_turn_count=len(payload['exchange']), exchange_sha256=digest(payload['exchange']),
            canonical_complete_round=True, canonical_reply_value_sha256=digest(canonical),
            third_complete_S1_history_filtered=index == 2)
        self.report.checked_save('checkpoint-after-http-reply-failed')
        def replay():
            before = self.fingerprint()
            query, response = self.http('/request-result', request), self.http('/send', request)
            require(query.get('query_status') == 'found' and query.get('request_verified') is True
                and query.get('ok') is True and query.get('settled') is True
                and response.get('ok') is True and response.get('settled') is True
                and query.get('request_id') == response.get('request_id') == request['request_id']
                and self.fingerprint() == before, 'original-http-reply-nonce-or-query-not-replayed')
        self.zero('http-reply-'+str(index+1)+'-nonce-replay-query-zero-model', replay)
        self.reload('http-reply-'+str(index+1)+'-restart-zero-model')
        self.zero('http-reply-'+str(index+1)+'-after-restart-query-zero-model', replay)

    def close(self):
        if self.product is not None:
            before = self.counts(), self.transport.total_calls
            self.transport.arm('final-explicit-pause-and-close')
            response = self.product.application.query_living_controls()
            require(response.status == 'available' and type(response.view) is dict, 'final-permission-before-pause-unverified')
            self.report.data['permission_before_final_pause'] = plain(response.view)
            self.report.checked_save('final-permission-before-pause-checkpoint-failed')
            self.controls(paused=True, sharing_enabled=False, label='final-explicit-http-pause-shareoff-zero-model')
            final = self.product.application.query_living_controls()
            require(final.status == 'available' and type(final.view) is dict
                and final.view['paused'] is True and final.view['sharing_enabled'] is False
                and (self.counts(), self.transport.total_calls) == before, 'final-paused-permission-unverified')
            self.report.data['final_permission'] = plain(final.view)
            state = self.http('/status')
            require(state.get('living_pending') is False and state.get('presentation_pending') is False,
                'final-http-operation-still-unverified')
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            if self.server_thread is not None:
                self.server_thread.join(timeout=5)
                require(not self.server_thread.is_alive(), 'own-http-server-close-unverified')
            self.report.data['own_http_server_closed'] = True
        if self.entry is not None:
            self.entry.close()
            require(self.entry.product is None, 'own-entry-product-close-unverified')
            self.report.data['entry_product_closed'] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--preflight', action='store_true')
    modes.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    report, run, failed = None, None, False
    try:
        scene, root = preflight()
        if args.preflight:
            print(json.dumps(dict(status='preflight-passed', review_basis=REVIEW_BASIS,
                approved_scenario_sha256=SCENARIO_SHA, first_scene_sha256=SCENE_SHA,
                runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), safe_observer_sha256=OBSERVER_SHA,
                time_is_simulated=False, opportunity_seconds=900, maximum_first_requests=5,
                independent_model_free_presence=True, presence_consumes_opportunity=False,
                requests_per_stage=1, automatic_retries=0, identity_opened=False, service_started=False,
                transport_created=False, credential_reads=0, remote_calls=0, resource_exists=False,
                output_exists=False, browser_visible_900_seconds_verified=False), ensure_ascii=False), flush=True)
            return
        report = SafeReport(root, scene)
        report.checked_save('initial-http-checkpoint-failed')
        run = EntryRun(root, scene, report)
        run.create(); run.enable()
        if run.online_choice() and run.share():
            for index, text in enumerate(scene['followup_messages']):
                run.reply(index, text)
            report.data.update(status='first-http-scene-completed', real_online_plan_share_two_followups_third_filter=True)
        report.checked_save('checkpoint-after-first-http-scene-failed')
    except BaseException as error:
        failed = True
        if report is not None:
            row = report.data['stages'][-1] if report.data['stages'] else None
            if row is not None:
                row.update(error_type=type(error).__name__)
                if row['status'] in ('started', 'pending'):
                    row['status'] = 'failed-or-unverified'
            report.data.update(error_type=type(error).__name__,
                stop_code=error.code if type(error) is AcceptanceStopped else 'unexpected-http-runner-failure',
                runner_exit_code=1)
            if report.data['status'] != 'stopped-on-first-technical-failure':
                report.data['status'] = 'stopped-for-unverified-or-integrity'
            report.save()
        else:
            print(json.dumps(dict(status='preflight-stopped', error_type=type(error).__name__,
                stop_code=error.code if type(error) is AcceptanceStopped else 'unexpected-preflight-failure',
                runner_exit_code=1, remote_calls=0, credential_reads=0), ensure_ascii=False), flush=True)
    finally:
        if run is not None:
            try:
                run.audit()
            except Exception as error:
                report.data.update(audit_unverified=True, audit_error_type=type(error).__name__)
                report.unverified('final-http-audit-unverified')
            try:
                run.close()
            except Exception as error:
                report.data.update(close_unverified=True, close_error_type=type(error).__name__)
                report.unverified('final-pause-or-close-unverified')
                # Best effort release; an unknown close is never called success.
                for action in ((lambda: run.server.shutdown()) if run.server is not None else None,
                    (lambda: run.server.server_close()) if run.server is not None else None,
                    run.entry.close if run.entry is not None else None):
                    if action is not None:
                        try:
                            action()
                        except Exception:
                            pass
        if report is not None:
            report.data.setdefault('runner_exit_code', 1 if failed else 0)
            if not report.save() or report.io_error_types:
                report.unverified('final-http-checkpoint-unverified')
                report.save()
            print(json.dumps({key: value for key, value in report.data.items()
                if key not in ('stages', 'transport', 'audit')}, ensure_ascii=False), flush=True)
            failed = failed or report.data['runner_exit_code'] != 0
    if failed:
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()

