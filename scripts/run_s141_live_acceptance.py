"""First empty-history activity chains; no source, retries or text exports."""
import json
import os
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import re
from threading import Thread
from time import monotonic, sleep
from uuid import uuid4

from run_s140_live_entry_acceptance import EntryRun, EntryObservedTransport, view, digest
from serve_shared_activity_chat import SharedActivityChatEntry
from shared_activity_chat import shared_activity_server
from dynamic_subject_agent.shared_activity_live import open_shared_activity_audit

REPO = Path(__file__).resolve().parents[1]
BASE = Path(os.environ['LOCALAPPDATA'])/'DynamicSubjectAgent/shared-activity-development/s141/first-20261006'
SCENARIO = REPO/'docs/experiments/s141/scenarios.json'
OUTPUT = REPO/'docs/reports/2026-10-06-slice-141/live-metadata.json'
SCENARIO_SHA = '457832d5eb7aa3aa3b4bb83a6e87c65ddd66048d519cc1a6d83cd76d833db6dd'


class S141Run(EntryRun):
    def __init__(self, name, variant):
        self.root = BASE/name
        self.transport = EntryObservedTransport()
        self.audit_path = BASE/(name+'-audit')
        self.entry = SharedActivityChatEntry(self.root, live=False, transport=self.transport,
            audit_path=self.audit_path, technical_variant=variant)
        self.server = shared_activity_server(self.entry.product, reopen=self.entry.reopen, port=0,
            technical_variant=self.entry.technical_variant)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        page = self.get('/')
        token = re.search(r"const TOKEN=['\"]([^'\"]+)['\"]", page)
        if token is None:
            self.close(); raise ValueError('Actual entry token unavailable.')
        self.token = token.group(1)


def state_digest(state):
    return digest(dict(shared=state['shared_activity'], history=state['history'], context=state['context_boundary'], scope=state['scope_key']))


def main():
    scenario = json.loads(SCENARIO.read_text(encoding='utf-8'))
    if digest(scenario) != SCENARIO_SHA or BASE.exists() or OUTPUT.exists():
        raise SystemExit('Frozen first resources changed or already exist; nothing executed.')
    if not OUTPUT.parent.is_dir():
        raise SystemExit('Report directory unavailable; no first resources created.')
    report = dict(version=scenario['version'], scenario_sha256=SCENARIO_SHA, automatic_retries=0,
        maximum_first_requests=scenario['maximum_first_requests'], raw_text_exported=False, branches=[])
    BASE.mkdir(parents=True, exist_ok=False)

    def save():
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    def execute(run, row, label, request, *, activity):
        before = run.calls(); run.transport.rows.clear(); started = monotonic()
        item = dict(stage=label, status='not-started', audit_before=before, audit_after=before,
            transport=[], elapsed_seconds=0)
        row['stages'].append(item); save()
        try:
            result = run.post('/shared-activity-advance' if activity else '/send', request)
            while result.get('shared_status') == 'busy' if activity else bool(result.get('pending')):
                if monotonic()-started > 120:
                    raise TimeoutError('Unverified pending.')
                sleep(.2)
                result = run.post('/shared-activity-request', dict(kind='advance', request=request)) if activity else run.post(
                    '/request-result', request)
        except Exception as error:
            item.update(status='unverified', error_type=type(error).__name__, elapsed_seconds=monotonic()-started,
                audit_after=run.calls(), transport=deepcopy(run.transport.rows))
            row['stopped_for_unverified_delivery'] = True; save()
            raise RuntimeError('Unverified HTTP stage; further live calls stopped.') from None
        item.update(status=result['shared_status'] if activity else 'terminal' if result['ok'] else 'uncommitted',
            audit_after=run.calls(), transport=deepcopy(run.transport.rows), elapsed_seconds=monotonic()-started)
        save()
        return result, item, before

    def reopen(run, row, label):
        before, state = run.calls(), run.get('/status')
        fresh = run.post('/reload', {})
        row[label] = fresh['ok'] and before == run.calls() and state_digest(state) == state_digest(fresh['state'])
        save()
        if not row[label]:
            raise RuntimeError('Reopen changed business state or invoked a model.')

    def step(run, row, label):
        state = run.get('/status'); shared = view(state)
        if shared['visible_source'] is not None or state['history']['turns']:
            raise RuntimeError('Activity requires no E1 and no committed conversation.')
        preview = run.post('/shared-activity-preview', {})
        if not preview['ok']:
            raise RuntimeError('Exact activity preview unavailable.')
        current_plan = shared['current_plan']
        expected_plan_sha = None if current_plan is None else digest(current_plan)
        request = dict(request_id=str(uuid4()), expected_revision=shared['revision'])
        result, item, before = execute(run, row, label, request, activity=True)
        item.update(supplied_previous_plan_sha256=expected_plan_sha,
            shared_state_status=result['state']['shared_activity']['status']); save()
        success = result['shared_status'] in ('committed', 'replayed')
        if run.calls()-before > 1 or len(run.transport.rows) > 1 or success and (run.calls()-before != 1 or len(run.transport.rows) != 1):
            raise RuntimeError('Manual action violated its single-request boundary.')
        if run.transport.rows:
            sent = run.transport.rows[0]
            item['actual_no_e1'] = sent['shared_quote_chars'] == 0
            item['actual_previous_plan_matches'] = sent['supplied_plan_sha256'] == expected_plan_sha
            if not item['actual_no_e1'] or not item['actual_previous_plan_matches']:
                save(); raise RuntimeError('Actual choice differs from source/plan preview.')
        if not success:
            row['stopped_on_first_technical_failure'] = True; save(); return None
        if item['shared_state_status'] != 'available':
            raise RuntimeError('Committed activity cannot be verified.')
        shared = view(result['state']); actual = shared['visible_result']
        item.update(action=shared['decision']['action'], basis_refs=shared['decision']['basis_refs'],
            reason_code=shared['decision']['reason_code'], decision_note_sha256=digest(shared['decision']['decision_note']),
            phase=shared['phase'], activity_revision=shared['activity_revision'],
            plan_sha256=None if actual is None or actual['plan'] is None else digest(actual['plan']),
            difference_fields=[] if actual is None else [difference['field'] for difference in actual['differences']])
        before = run.calls(); replay = run.post('/shared-activity-advance', request)
        item['same_nonce_zero_calls'] = replay['shared_status'] == 'replayed' and run.calls() == before
        save()
        if not item['same_nonce_zero_calls']:
            raise RuntimeError('Original action replay did not preserve its receipt.')
        print(json.dumps(dict(branch=row['name'], stage=label, action=item['action'], phase=item['phase']), ensure_ascii=False), flush=True)
        return item

    for branch in scenario['branches']:
        row = dict(name=branch['name'], technical_variant=branch['technical_variant'], stages=[], plan_reply_loop_completed=False)
        report['branches'].append(row); save()
        run = S141Run(branch['name'], branch['technical_variant'])
        audit = open_shared_activity_audit(run.audit_path)
        try:
            initial = run.get('/status'); shared = view(initial)
            row['fresh_no_source_no_chat_zero_calls'] = run.calls() == 0 and not initial['history']['turns'] and shared['visible_source'] is None and shared['phase'] == 'unstarted' and shared['current_plan'] is None
            if not row['fresh_no_source_no_chat_zero_calls']:
                raise RuntimeError('Exact fresh same-input activity basis required.')
            first = step(run, row, 'first-activity')
            if first is None:
                continue
            if first['plan_sha256'] is None:
                row['first_no_plan_outcome'] = first['action']; save(); continue
            reopen(run, row, 'first_reopen_zero_calls')
            second = step(run, row, 'next-activity')
            if second is None:
                continue
            row['actual_second_input_is_first_plan'] = second['supplied_previous_plan_sha256'] == first['plan_sha256']
            if not row['actual_second_input_is_first_plan']:
                save(); raise RuntimeError('Next choice did not receive the committed first plan.')
            row['new_plan_version_committed'] = second['activity_revision'] > first['activity_revision'] and second['plan_sha256'] != first['plan_sha256']
            reopen(run, row, 'second_reopen_zero_calls')
            if second['plan_sha256'] is None:
                row['final_no_plan_outcome'] = second['action']; save(); continue
            request = dict(request_id=str(uuid4()), text=scenario['followup_message'])
            reply, item, before = execute(run, row, 'current-result-followup', request, activity=False)
            if run.calls()-before > 1 or len(run.transport.rows) > 1:
                raise RuntimeError('Reply violated its single-request boundary.')
            if not reply['ok']:
                row['stopped_on_first_technical_failure'] = True; save(); continue
            if run.calls()-before != 1 or len(run.transport.rows) != 1:
                raise RuntimeError('Successful reply has no verified one request.')
            actual = reply['state']['history']['turns'][-1]['assistant_text']
            item.update(reply_chars=len(actual), reply_sha256=sha256(actual.encode()).hexdigest())
            sent = run.transport.rows[0]
            row['raw_final_reply_matches'] = sent['response_boundary']['reply_sha256'] == item['reply_sha256']
            row['reply_gets_same_final_plan'] = sent['supplied_plan_sha256'] == second['plan_sha256']
            row['reply_no_e1_no_prior_dialogue'] = sent['shared_quote_chars'] == 0 and sent['exchange_turn_sha256'] == []
            if not row['raw_final_reply_matches'] or not row['reply_gets_same_final_plan'] or not row['reply_no_e1_no_prior_dialogue']:
                save(); raise RuntimeError('Actual reply material or final text differs.')
            row['plan_reply_loop_completed'] = True; save()
        finally:
            row['audit'] = list(audit.snapshot()); row['requests'] = len(row['audit']); save()
            run.close()
    first_choices = [row['stages'][0]['transport'][0]['payload_sha256'] for row in report['branches'] if row['stages'] and row['stages'][0]['transport']]
    report['first_choice_payloads_equal'] = len(first_choices) == 3 and len(set(first_choices)) == 1
    report['total_requests'] = sum(row['requests'] for row in report['branches'])
    report['transport_invocations'] = sum(len(item['transport']) for row in report['branches'] for item in row['stages'])
    report['plan_reply_loops_completed'] = sum(row['plan_reply_loop_completed'] for row in report['branches'])
    report['scheduled_first_runs_finished'] = True
    if report['total_requests'] > 9:
        raise RuntimeError('Frozen first-request bound exceeded.')
    save(); print(json.dumps({key:value for key,value in report.items() if key != 'branches'}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
