"""Bounded first real runs through the S140 HTTP entry; no retries or text copies."""
import json
import os
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import re
from threading import Thread
from time import monotonic, sleep
from urllib.request import Request, urlopen
from uuid import uuid4

from run_s139_live_acceptance import LiveObservedTransport, digest
from serve_shared_activity_chat import SharedActivityChatEntry
from shared_activity_chat import shared_activity_server
from dynamic_subject_agent.shared_activity_live import open_shared_activity_audit

REPO = Path(__file__).resolve().parents[1]
SCENARIO = REPO / 'docs/experiments/s140/scenarios.json'
OUTPUT = REPO / 'docs/reports/2026-10-06-slice-140/live-entry-metadata.json'
BASE = Path(os.environ['LOCALAPPDATA']) / 'DynamicSubjectAgent/shared-activity-development/s140/first-entry-20261006'
SCENARIO_SHA = '7fd7060f47c40fb2de031918ea43257e430b315a660527763babe39c5609613a'


def turn_digest(turn):
    return digest({key: turn[key] for key in ('user_text', 'assistant_text')})


class EntryObservedTransport(LiveObservedTransport):
    def post_json(self, **kwargs):
        body = json.loads(kwargs['body'])
        payload = json.loads(body['messages'][1]['content'])
        exchange = payload.get('exchange', [])
        response = super().post_json(**kwargs)
        self.rows[-1]['exchange_turn_sha256'] = [turn_digest(turn) for turn in exchange]
        return response


class EntryRun:
    def __init__(self, name, variant):
        self.root = BASE / name
        self.transport = EntryObservedTransport()
        self.audit_path = BASE / (name + '-audit')
        self.entry = SharedActivityChatEntry(self.root, live=False, transport=self.transport,
            audit_path=self.audit_path, technical_variant=variant)
        self.server = shared_activity_server(self.entry.product, reopen=self.entry.reopen, port=0,
            technical_variant=self.entry.technical_variant)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.page = self.get('/')
        token = re.search(r"const TOKEN=['\"]([^'\"]+)['\"]", self.page)
        if token is None:
            self.close()
            raise ValueError('actual entry session token is unavailable')
        self.token = token.group(1)

    def get(self, path):
        with urlopen(self.url + path, timeout=15) as response:
            body = response.read().decode('utf-8')
        return body if path == '/' else json.loads(body)

    def post(self, path, payload):
        request = Request(self.url + path, json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'X-Chat-Token': self.token}, method='POST')
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode('utf-8'))

    def calls(self):
        return open_shared_activity_audit(self.audit_path).counts()[1]

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.entry.close()


def view(state):
    shared = state['shared_activity']
    if shared['status'] != 'available':
        raise ValueError('verified shared state unavailable')
    return shared['view']


def fingerprint(state):
    return digest(dict(history=state['history'], shared=state['shared_activity'],
        scope=state['scope_key'], context=state['context_boundary']))


def main():
    scenario_bytes = SCENARIO.read_bytes()
    scenario = json.loads(scenario_bytes.decode('utf-8'))
    if digest(scenario) != SCENARIO_SHA:
        raise SystemExit('Frozen scenario differs; no roots or requests created.')
    if BASE.exists() or OUTPUT.exists():
        raise SystemExit('Existing first runs retained; no overwrite, retry or replacement.')
    BASE.mkdir(parents=True, exist_ok=False)
    report = dict(version=scenario['version'], scenario_sha256=SCENARIO_SHA, automatic_retries=0,
        maximum_requests=scenario['maximum_requests_if_all_first_attempts_succeed'], raw_text_exported=False,
        branches=[], comparison=[])

    def save():
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    def stage(run, row, label, request, *, activity=False):
        before = run.calls()
        run.transport.rows.clear()
        started = monotonic()
        result = run.post('/shared-activity-advance' if activity else '/send', request)
        deadline = monotonic() + 120
        while (result.get('shared_status') == 'busy' if activity else bool(result.get('pending'))):
            if monotonic() > deadline:
                raise RuntimeError('unverified pending: further calls stopped')
            sleep(.2)
            result = run.post('/shared-activity-request', dict(kind='advance', request=request)) if activity else run.post(
                '/request-result', request)
        calls = deepcopy(run.transport.rows)
        state = result['state']
        item = dict(stage=label, http_status='completed', operation_status=result.get('shared_status') if activity else (
            'terminal' if result['ok'] else 'uncommitted'), elapsed_seconds=monotonic()-started,
            audit_before=before, audit_after=run.calls(), transport=calls,
            history_turn_count=len(state['history']['turns']))
        row['stages'].append(item); save()
        if activity:
            item['shared_state_status'] = state['shared_activity']['status']
            if item['shared_state_status'] == 'available':
                current = view(state)
                actual = current['visible_result']
                item.update(phase=current['phase'], source_visible=current['visible_source'] is not None,
                    action=None if current['decision'] is None else current['decision']['action'],
                    basis_refs=[] if current['decision'] is None else current['decision']['basis_refs'],
                    plan_sha256=None if actual is None or actual['plan'] is None else digest(actual['plan']))
            elif result['shared_status'] in ('committed', 'replayed'):
                save()
                raise RuntimeError('committed activity state could not be verified')
        elif result['ok'] and not result.get('pending'):
            actual = state['history']['turns'][-1]['assistant_text']
            item.update(reply_chars=len(actual), reply_sha256=sha256(actual.encode()).hexdigest())
            raw_sha = calls[0].get('response_boundary', {}).get('reply_sha256') if len(calls) == 1 else None
            item['final_expression_matches_raw_reply'] = raw_sha == item['reply_sha256']
            if raw_sha != item['reply_sha256']:
                save()
                raise RuntimeError('raw-canonical mismatch: further calls stopped')
        save()
        print(json.dumps(dict(branch=row['name'], stage=label, status=item['operation_status'],
            requests=item['audit_after']-before), ensure_ascii=False), flush=True)
        ok = result['shared_status'] in ('committed', 'replayed') if activity else result['ok']
        claims = run.calls()-before
        if claims > 1 or len(calls) > 1 or ok and (claims != 1 or len(calls) != 1):
            raise RuntimeError('manual action violated its single-request boundary')
        if not ok:
            row['stopped_on_first_failure'] = True; save()
        return ok, result

    def chat(run, row, text, label):
        return stage(run, row, label, dict(text=text, request_id=str(uuid4())))

    def zero_reload(run, row, label):
        before, state = run.calls(), run.get('/status')
        fresh = run.post('/reload', {})
        row[label] = fresh['ok'] and fingerprint(state) == fingerprint(fresh['state']) and before == run.calls()
        if not row[label]:
            raise RuntimeError('cold reopen changed business state or sent a request')
        save()

    def source(run, quote, message):
        result = run.post('/chat-archive', dict(query='', before_sequence=None))
        rows = [item for item in result['archive']['rows'] if item.get('user_text') == message]
        if not result['ok'] or len(rows) != 1:
            raise ValueError('unique committed source unavailable')
        before = run.calls()
        state = run.get('/status')
        response = run.post('/shared-experience', dict(request_id=str(uuid4()), expected_revision=view(state)['revision'],
            source_head_sequence=rows[0]['head_sequence'], quote=quote, confirmed=True))
        if response['shared_status'] != 'committed' or run.calls() != before:
            raise ValueError('zero-call exact selection failed')
        return rows[0]['head_sequence']

    def disable(run):
        before = run.calls()
        response = run.post('/shared-experience', dict(request_id=str(uuid4()), expected_revision=view(run.get('/status'))['revision'],
            source_head_sequence=None, quote='', confirmed=True))
        if response['shared_status'] != 'committed' or run.calls() != before:
            raise ValueError('zero-call explicit disable failed')
        if view(response['state'])['visible_source'] is not None or view(response['state'])['visible_result'] is not None:
            raise ValueError('disabled source or dependent result remained visible')

    completed_branch_followup = False
    for branch in scenario['branches']:
        row = dict(name=branch['name'], technical_variant='natural-expression', stages=[], completed=False)
        report['branches'].append(row); save()
        run = EntryRun(branch['name'], 'natural-expression')
        try:
            row['empty_entry_zero_calls'] = not run.get('/status')['history']['turns'] and run.calls() == 0
            if not chat(run, row, branch['source_message'], 'source')[0]:
                continue
            head = source(run, branch['selected_quote'], branch['source_message'])
            row['source_selected_zero_calls'] = True
            failed = False
            for index, message in enumerate(scenario['gap_messages']):
                if not chat(run, row, message, f'gap-{index+1}')[0]:
                    failed = True; break
            if failed:
                continue
            archive = run.post('/chat-archive', dict(query='', before_sequence=None))['archive']['rows']
            row['source_outside_two_turn_window'] = all(item['head_sequence'] != head for item in archive[:2])
            zero_reload(run, row, 'pre_activity_reopen_zero_calls')
            if branch['disable_before_activity']:
                disable(run); row['source_disabled_zero_calls'] = True
            state = run.get('/status')
            request = dict(request_id=str(uuid4()), expected_revision=view(state)['revision'])
            ok, result = stage(run, row, 'activity', request, activity=True)
            if not ok:
                continue
            before = run.calls()
            replay = run.post('/shared-activity-advance', request)
            row['replayed_activity_zero_calls'] = replay['shared_status'] == 'replayed' and run.calls() == before
            if not row['replayed_activity_zero_calls']:
                raise RuntimeError('same nonce executed again or changed result')
            zero_reload(run, row, 'post_activity_reopen_zero_calls')
            if not chat(run, row, scenario['activity_followup'], 'activity-followup')[0]:
                continue
            expected_plan = row['stages'][-2]['plan_sha256']
            supplied_plan = row['stages'][-1]['transport'][0]['supplied_plan_sha256']
            row['same_result_projection_in_reply'] = supplied_plan == expected_plan
            row['text_plan_formed'] = expected_plan is not None
            row['same_committed_plan_in_reply'] = expected_plan is not None and supplied_plan == expected_plan
            if not row['same_result_projection_in_reply']:
                raise RuntimeError('reply did not receive the actual committed plan')
            row['workflow_completed'] = True
            row['completed'] = row['same_committed_plan_in_reply']
            if not row['text_plan_formed']:
                row['outcome'] = 'decision-committed-without-text-plan'
            if row['completed'] and not completed_branch_followup and not branch['disable_before_activity']:
                completed_branch_followup = True
                for index, message in enumerate(scenario['completed_branch_followup']):
                    if not chat(run, row, message, f'continuity-{index+1}')[0]:
                        failed = True; break
                if not failed:
                    # Every prior turn in this fixed prefix is either the
                    # selected source turn, or was generated with that E1.
                    # Compare complete pairs so an echoed old reply cannot
                    # bypass disable through the recent dialogue window.
                    dependent = [turn_digest(turn) for turn in run.get('/status')['history']['turns']]
                    row['pre_disable_dependent_turn_sha256'] = dependent
                    disable(run); row['post_result_disable_zero_calls'] = True
                    zero_reload(run, row, 'post_disable_reopen_zero_calls')
                    ok, _ = chat(run, row, scenario['after_disable_message'], 'after-disable-topic')
                    if ok:
                        supplied = row['stages'][-1]['transport'][0]
                        row['disabled_quote_and_plan_absent_from_wire'] = supplied['shared_quote_chars'] == 0 and supplied['supplied_plan_sha256'] is None
                        row['complete_dependent_turns_absent_from_wire'] = not set(dependent).intersection(supplied['exchange_turn_sha256'])
                        if not row['disabled_quote_and_plan_absent_from_wire'] or not row['complete_dependent_turns_absent_from_wire']:
                            raise RuntimeError('disabled source leaked through a dependent result or complete turn')
            save()
        finally:
            row['audit'] = list(open_shared_activity_audit(run.audit_path).snapshot()); save()
            run.close()

    for variant in ('baseline', 'natural-expression'):
        row = dict(name='expression-'+variant, technical_variant=variant, stages=[], completed=False)
        report['comparison'].append(row); save()
        run = EntryRun(row['name'], variant)
        try:
            for index, message in enumerate(scenario['expression_comparison_messages']):
                if not chat(run, row, message, f'expression-{index+1}')[0]:
                    break
            else:
                row['completed'] = True
        finally:
            row['audit'] = list(open_shared_activity_audit(run.audit_path).snapshot()); save()
            run.close()
    choice_digests = [item['transport'][0]['common_choice_payload_sha256'] for row in report['branches']
        for item in row['stages'] if item['stage'] == 'activity' and len(item['transport']) == 1]
    report['completed_branches'] = sum(row['completed'] for row in report['branches'])
    report['activity_preconditions_equal_except_source'] = len(choice_digests) == 3 and len(set(choice_digests)) == 1
    report['total_requests'] = sum(len(row['audit']) for row in report['branches']+report['comparison'])
    report['transport_invocations'] = sum(len(item['transport']) for row in report['branches']+report['comparison'] for item in row['stages'])
    if report['total_requests'] > report['maximum_requests']:
        raise RuntimeError('frozen first-run bound exceeded')
    report['scheduled_first_runs_finished'] = True; save()
    print(json.dumps({key:value for key,value in report.items() if key not in ('branches', 'comparison')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
