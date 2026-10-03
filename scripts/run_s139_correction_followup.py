"""At most four new messages on the successful live branch; never retry a failure."""
import json
from hashlib import sha256
from time import perf_counter
from uuid import uuid4

from run_s139_live_acceptance import BASE, REPO, REVIEW_BASIS, LiveObservedTransport, digest, history, state
from dynamic_subject_agent.local_product import LocalProductConfig, open_shared_activity_product_live
from dynamic_subject_agent.shared_activity_live import ApprovedSharedActivityGrant, open_shared_activity_audit
from dynamic_subject_agent.timeline import SubjectCommand

SCENARIO_SHA256 = '0488bdb0e6d952ac7f8fb405312c95cd58412ac55f6e8a5c951473a896e22d7e'


def main():
    scenario_path = REPO/'docs/experiments/s139/correction-followup.json'
    scenario_bytes = scenario_path.read_bytes()
    if sha256(scenario_bytes).hexdigest() != SCENARIO_SHA256:
        raise ValueError('Frozen four-message scenario changed; no activation or sending.')
    scenario = json.loads(scenario_bytes.decode('utf-8'))
    output = REPO/'docs/reports/2026-10-03-slice-139/correction-followup-metadata.json'
    if output.exists():
        raise SystemExit('Existing first follow-up retained; this script does not retry.')
    if (scenario['maximum_new_requests'] != 4 or scenario['automatic_retries'] != 0
        or scenario['stop_on_first_failure'] is not True or len(scenario['messages']) != 4):
        raise ValueError('Exactly the frozen bounded four-message follow-up is required.')
    root = BASE/scenario['branch']
    identity = json.loads((root/'state.json').read_text(encoding='utf-8'))['active_identity_id']
    config = LocalProductConfig(root/'DynamicSubjectAgent/m0/experiments', root/'state.json')
    audit = open_shared_activity_audit(BASE/'audit')
    if audit.counts()[1] != scenario['audit_before']:
        raise ValueError('Previous first-run audit basis changed; no messages sent.')
    transport, observations = LiveObservedTransport(), []
    def opening():
        return open_shared_activity_product_live(config, identity_id=identity,
            grant=ApprovedSharedActivityGrant(REVIEW_BASIS, True), audit_path=BASE/'audit',
            _transport=transport, observations=observations)
    product = opening()
    report = dict(version=scenario['version'], scenario_sha256=sha256(scenario_path.read_bytes()).hexdigest(),
        baseline_normal_reply_sha256=scenario['normal_reply_sha256'], audit_before=scenario['audit_before'],
        maximum_new_requests=4, automatic_retries=0, raw_text_exported=False, stages=[])
    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        previous = history(product)
        if (len(previous) != scenario['normal_turn_count']
            or sha256(previous[-1].assistant_text.encode()).hexdigest() != scenario['normal_reply_sha256']
            or '也不替你补成什么习惯' not in previous[-1].assistant_text):
            raise ValueError('Actual normal reply differs from the frozen correction basis.')
        from dataclasses import asdict
        if digest(asdict(state(product)['visible_result'].plan)) != scenario['normal_plan_sha256']:
            raise ValueError('Committed activity basis changed.')
        report['baseline_normal_chat_verified'] = True; save()
        for index, message in enumerate(scenario['messages']):
            if index == 3:
                before = history(product), state(product)
                calls = audit.counts()[1]
                product.close(); product = opening()
                if (history(product), state(product)) != before or audit.counts()[1] != calls:
                    raise ValueError('Reopen changed business state or used a model.')
                report['reopen_preserved_state_zero_calls'] = True
            transport.rows.clear(); observations.clear()
            before = len(history(product)); started = perf_counter()
            result = product.application.submit(SubjectCommand.contribute_utterance(
                target_profile_id=product.profile_id, target_timeline_id=product.timeline_id,
                declared_intent='ask-collaborator-status', utterance=message['text'], language='zh',
                provenance='project-original'), idempotency_key='s139-correction-'+str(uuid4()))
            deadline = perf_counter()+120
            while result.status.value == 'pending' and perf_counter() < deadline:
                result = product.application.wait(result.operation_ref, timeout_seconds=30)
            expression = getattr(result.projection, 'expression_text', '') or ''
            row = dict(stage=message['stage'], status=result.status.value,
                failure_code=getattr(result.projection, 'failure_code', None),
                reply_chars=len(expression), reply_sha256=sha256(expression.encode()).hexdigest() if expression else None,
                committed_before=before, committed_after=len(history(product)), elapsed_seconds=perf_counter()-started,
                observations=list(observations), transport=list(transport.rows))
            raw_sha = transport.rows[0].get('response_boundary', {}).get('reply_sha256') if len(transport.rows)==1 else None
            if raw_sha is not None:
                row['final_expression_matches_raw_reply'] = row['reply_sha256']==raw_sha
            report['stages'].append(row); report['audit_after']=audit.counts()[1]; save()
            print(json.dumps(row, ensure_ascii=False), flush=True)
            if result.status.value != 'terminal' or row.get('final_expression_matches_raw_reply') is False:
                report['stopped_on_failure']=True; save()
                return
        report['completed_five_step_chain']=True; save()
    finally:
        product.close()


if __name__ == '__main__':
    main()
