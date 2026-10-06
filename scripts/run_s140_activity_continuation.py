"""Six new manual activity/result actions, preserving the first failed chats."""
import json
import sqlite3
from copy import deepcopy
from hashlib import sha256
from time import monotonic, sleep
from uuid import uuid4

from run_s140_live_entry_acceptance import EntryRun, REPO, BASE, view, turn_digest, digest
from dynamic_subject_agent.shared_activity_live import open_shared_activity_audit

FIRST = REPO / 'docs/reports/2026-10-06-slice-140/live-entry-metadata.json'
OUTPUT = REPO / 'docs/reports/2026-10-06-slice-140/activity-continuation-metadata.json'
FIRST_SHA = 'beded65fd780ee88db112e7ead0972a3a2a7af2bc8d60dc17c9d7d6747e56775'
FOLLOWUP = '你这次实际决定的文字构图是什么？为什么这样安排主体和空间？如果这次暂缓，也直接告诉我还没有形成方案。'


def canonical_prefix(root, sequence, path=None):
    """Read-only integrity evidence; business actions still use the Facade."""
    candidates = [path] if path is not None else list(root.rglob('timeline.sqlite3'))
    matches = []
    for database in candidates:
        if not database.resolve().is_relative_to(root.resolve()):
            raise ValueError('Canonical database escaped the owned development root.')
        with sqlite3.connect(database.as_uri()+'?mode=ro', uri=True) as reader:
            if reader.execute('PRAGMA user_version').fetchone() != (5,):
                continue
            rows = reader.execute('SELECT * FROM timeline_outcome WHERE head_sequence <= ? ORDER BY head_sequence', (sequence,)).fetchall()
            if len(rows) == sequence:
                encoded = [[dict(blob=value.hex()) if isinstance(value, bytes) else value for value in row] for row in rows]
                matches.append((database, [digest(row) for row in encoded]))
    if len(matches) != 1:
        raise ValueError('Exactly one populated qualified canonical prefix is required.')
    return matches[0]


def main():
    first = json.loads(FIRST.read_text(encoding='utf-8'))
    if digest(first) != FIRST_SHA or first['total_requests'] != 11 or OUTPUT.exists():
        raise SystemExit('First-run basis changed or continuation exists; no action started.')
    scenario = json.loads((REPO/'docs/experiments/s140/scenarios.json').read_text(encoding='utf-8'))
    from run_s140_live_entry_acceptance import SCENARIO_SHA
    if digest(scenario) != SCENARIO_SHA:
        raise ValueError('Frozen source scenario changed.')
    # Inspect all required first resources before any EntryRun can create a
    # directory or before any branch sends its new manual action.
    for original in first['branches']:
        root = BASE/original['name']
        if not root.is_dir() or not (root/'initialized').is_dir() or any(
            not (root/name).is_file() for name in ('current.json', 'state.json')):
            raise SystemExit('Original root is incomplete; no branch is recreated.')
        if list(open_shared_activity_audit(BASE/(original['name']+'-audit')).snapshot()) != original['audit']:
            raise ValueError('Immutable first audit differs; no new action started.')
    witnesses = {}
    for original, branch in zip(first['branches'], scenario['branches'], strict=True):
        if original['name'] != branch['name']:
            raise ValueError('Frozen branch order differs.')
        run = EntryRun(original['name'], 'natural-expression')
        try:
            state = run.get('/status'); shared = view(state)
            source = shared['visible_source']
            expected_head = original['stages'][-1]['history_turn_count'] + 1
            archive_result = run.post('/chat-archive', dict(query='', before_sequence=None))
            archive = archive_result['archive']
            if (shared['phase'] != 'unstarted' or shared['current_plan'] is not None or source is None
                or source['quote'] != branch['selected_quote'] or source['source_head_sequence'] != 1
                or source['selection_revision'] != 2 or not archive_result['ok'] or archive['snapshot_head_sequence'] != expected_head):
                raise ValueError('Exact first source or complete business prefix changed.')
            if not any(item.get('head_sequence') == 1 and item.get('user_text') == branch['source_message'] for item in archive['rows']):
                raise ValueError('Canonical source turn differs from the frozen utterance.')
            database, hashes = canonical_prefix(run.root, expected_head)
            witnesses[original['name']] = (database, hashes, expected_head, digest(shared))
        finally:
            run.close()
    report = dict(version='s140-new-activity-continuation-1', first_metadata_sha256=FIRST_SHA,
        original_chat_failures_preserved=True, automatic_retries=0, maximum_new_requests=6,
        raw_text_exported=False, branches=[])

    def save():
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    for original in first['branches']:
        row = dict(name=original['name'], stages=[], plan_loop_completed=False)
        report['branches'].append(row); save()
        run = EntryRun(original['name'], 'natural-expression')
        audit = open_shared_activity_audit(run.audit_path)
        try:
            prefix = list(audit.snapshot())
            if prefix != original['audit']:
                raise ValueError('Immutable first audit prefix differs before a new action.')
            state = run.get('/status')
            shared = view(state)
            database, hashes, expected_head, shared_digest = witnesses[original['name']]
            row['canonical_prefix_head_sequence'] = expected_head
            row['canonical_prefix_row_sha256'] = hashes
            if digest(shared) != shared_digest or canonical_prefix(run.root, expected_head, database)[1] != hashes:
                raise ValueError('Source or canonical prefix changed after all-branch preflight.')
            source_turns = [turn_digest(turn) for turn in state['history']['turns']]
            if original['name'] == 'disabled':
                before = run.calls()
                disabled = run.post('/shared-experience', dict(request_id=str(uuid4()), expected_revision=shared['revision'],
                    source_head_sequence=None, quote='', confirmed=True))
                if disabled['shared_status'] != 'committed' or run.calls() != before:
                    raise ValueError('Explicit disable was not committed without a model.')
                row['source_disabled_zero_calls'] = True
                state = disabled['state']
            before = run.calls(); run.transport.rows.clear()
            request = dict(request_id=str(uuid4()), expected_revision=view(state)['revision'])
            started = monotonic()
            result = run.post('/shared-activity-advance', request)
            while result['shared_status'] == 'busy':
                if monotonic()-started > 120:
                    raise RuntimeError('Pending is unverified; all further actions stopped.')
                sleep(.2)
                result = run.post('/shared-activity-request', dict(kind='advance', request=request))
            item = dict(stage='new-activity', status=result['shared_status'], audit_before=before, audit_after=run.calls(),
                transport=deepcopy(run.transport.rows), shared_state_status=result['state']['shared_activity']['status'])
            row['stages'].append(item); save()
            if run.calls()-before > 1 or len(run.transport.rows) > 1:
                raise RuntimeError('More than one request for a manual action.')
            if result['shared_status'] not in ('committed', 'replayed'):
                row['stopped_on_first_activity_failure'] = True; save(); continue
            if item['shared_state_status'] != 'available' or run.calls()-before != 1 or len(run.transport.rows) != 1:
                raise RuntimeError('Committed activity has no verified single request or state.')
            shared = view(result['state'])
            actual = shared['visible_result']
            item.update(action=shared['decision']['action'], basis_refs=shared['decision']['basis_refs'],
                reason_code=shared['decision']['reason_code'], plan_sha256=None if actual is None or actual['plan'] is None else digest(actual['plan']))
            before = run.calls()
            replay = run.post('/shared-activity-advance', request)
            row['same_nonce_zero_calls'] = replay['shared_status'] == 'replayed' and before == run.calls()
            previous = digest(result['state']['shared_activity']), digest(result['state']['history'])
            reloaded = run.post('/reload', {})
            row['reopen_zero_calls_same_state'] = reloaded['ok'] and run.calls() == before and previous == (
                digest(reloaded['state']['shared_activity']), digest(reloaded['state']['history']))
            if not row['same_nonce_zero_calls'] or not row['reopen_zero_calls_same_state']:
                raise RuntimeError('Replay/reopen changed the committed state or invoked a model.')
            before = run.calls(); run.transport.rows.clear()
            request = dict(request_id=str(uuid4()), text=FOLLOWUP)
            started = monotonic(); reply = run.post('/send', request)
            while reply.get('pending'):
                if monotonic()-started > 120:
                    raise RuntimeError('Reply pending is unverified; further actions stopped.')
                sleep(.2); reply = run.post('/request-result', request)
            item_reply = dict(stage='new-result-followup', status='terminal' if reply['ok'] else 'uncommitted',
                audit_before=before, audit_after=run.calls(), transport=deepcopy(run.transport.rows))
            row['stages'].append(item_reply); save()
            if run.calls()-before > 1 or len(run.transport.rows) > 1:
                raise RuntimeError('More than one request for a manual reply.')
            if not reply['ok']:
                row['stopped_on_first_followup_failure'] = True; save(); continue
            expression = reply['state']['history']['turns'][-1]['assistant_text']
            if run.calls()-before != 1 or len(run.transport.rows) != 1:
                raise RuntimeError('Successful reply has no exact single request.')
            raw = run.transport.rows[0]
            item_reply.update(reply_sha256=sha256(expression.encode()).hexdigest(), reply_chars=len(expression))
            row['raw_final_reply_matches'] = item_reply['reply_sha256'] == raw['response_boundary']['reply_sha256']
            row['same_result_projection_in_reply'] = raw['supplied_plan_sha256'] == item['plan_sha256']
            row['source_prefix_absent_from_exchange_after_known_failure_cutoff'] = not set(source_turns).intersection(raw['exchange_turn_sha256'])
            row['plan_loop_completed'] = item['plan_sha256'] is not None and row['same_result_projection_in_reply']
            if not row['raw_final_reply_matches'] or not row['same_result_projection_in_reply']:
                raise RuntimeError('Raw/final or committed result does not match.')
            if original['name'] == 'disabled' and (raw['shared_quote_chars'] != 0 or not row['source_prefix_absent_from_exchange_after_known_failure_cutoff']):
                raise RuntimeError('Disabled source leaked through E1 or a complete old turn.')
            save()
        finally:
            row['audit'] = list(audit.snapshot())
            row['original_audit_prefix_unchanged'] = row['audit'][:len(original['audit'])] == original['audit']
            row['new_requests'] = len(row['audit'])-len(original['audit']); save()
            row['canonical_original_prefix_unchanged'] = canonical_prefix(run.root, expected_head, database)[1] == hashes
            save()
            run.close()
            if not row['original_audit_prefix_unchanged'] or not row['canonical_original_prefix_unchanged']:
                raise RuntimeError('The original first audit or canonical prefix was changed.')
    choices = [stage['transport'][0]['common_choice_payload_sha256'] for row in report['branches']
        for stage in row['stages'] if stage['stage'] == 'new-activity' and len(stage['transport']) == 1]
    report['activity_preconditions_equal_except_source'] = len(choices) == 3 and len(set(choices)) == 1
    report['new_requests'] = sum(row['new_requests'] for row in report['branches'])
    report['first_plus_new_requests'] = 11+report['new_requests']
    report['plan_loops_completed'] = sum(row['plan_loop_completed'] for row in report['branches'])
    report['scheduled_new_actions_finished'] = True
    if report['new_requests'] > 6 or digest(json.loads(FIRST.read_text(encoding='utf-8'))) != FIRST_SHA:
        raise RuntimeError('Bound or immutable first metadata changed.')
    save(); print(json.dumps({key:value for key,value in report.items() if key != 'branches'}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
