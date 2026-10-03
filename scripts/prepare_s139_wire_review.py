"""Freeze exact unsent DeepSeek candidate requests; the Adapter stays unavailable."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelGateway, ModelGatewayFailure, ModelTask, ModelTaskKind
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
from dynamic_subject_agent.shared_activity_remote_preview import (
    PendingSharedActivityGrant, UnapprovedSharedActivityAdapter, shared_remote_request_preview,
)

REPO = Path(__file__).resolve().parents[1]


def digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('local_preview', type=Path)
    args = parser.parse_args()
    source = args.local_preview.resolve()
    preview = json.loads(source.read_text(encoding='utf-8'))
    if preview['version'] != 's139-local-exact-review-1' or preview['remote_calls'] != 0 or preview['simulated_outputs'] is not True:
        raise ValueError('Explicitly synthetic local evidence required.')
    rows, tasks = [], []
    for branch in preview['branches']:
        for kind, key in ((ModelTaskKind.SHARED_ACTIVITY_CHOICE, 'choice_preview'),
                          (ModelTaskKind.SHARED_ACTIVITY_REPLY, 'result_reply_preview')):
            task = ModelTask(kind, branch[key])
            wire = shared_remote_request_preview(task)
            if (wire['body']['messages'][0]['content'] != task.payload['policy']
                or json.loads(wire['body']['messages'][1]['content']) != task.payload['payload']):
                raise ValueError('Exact local builder policy/payload must survive wire serialization.')
            tasks.append(task)
            rows.append(dict(branch=branch['branch'], **wire))
    protocol_keys = tuple(key for key in rows[0]['body'] if key != 'messages')
    protocol = {key: rows[0]['body'][key] for key in protocol_keys}
    if any({key: row['body'][key] for key in protocol_keys} != protocol for row in rows):
        raise ValueError('Both proposed purposes must use the reviewed exact protocol.')
    review = dict(version='s139-shared-activity-new-use-review-1', approval_status='not-granted',
        material_binding=APPROVED_BINDING, provider='deepseek',
        endpoint=rows[0]['endpoint'], credential_use=rows[0]['credential_use'], protocol=protocol,
        timeout_seconds=30, requests_per_manual_action=1, automatic_retries=0,
        source=dict(maximum_count=1, maximum_characters=400, selection='explicit-exact-contiguous-committed-user-quote',
            projection_fields=['label', 'quote'], label='E1', absent=None),
        choice_input_fields=['background', 'shared_experience', 'current_activity', 'current_plan'],
        activity_fields=['phase', 'allowed_actions'],
        plan_limits=dict(subject=160, composition=800, focus=400),
        reply_input_fields=['turn', 'background', 'exchange', 'evidence'],
        reply_evidence_fields=['shared_experience', 'activity_result'], result_fields=['kind', 'plan'],
        current_message_limit=1000, recent_dialogue_complete_turns=2, recent_dialogue_total_characters=4000,
        output_note=dict(maximum_characters=160, use='local-visible-decision-only-never-subsequent-model-input'),
        source_controls='deactivate-replace-history-off-context-cutoff-filter-all-dependent-results-and-complete-dialogue-turns',
        excluded=['automatic-life', 'proactive-sharing', 'notifications', 'personality-rewrite', 'reflection',
            'cloud', 'old-root-migration', 'new-credential-purpose', 'external-actions'],
        local_preview_sha256=digest(preview), scenario_sha256=preview['scenario_sha256'],
        samples=[dict(branch=row['branch'], purpose=row['purpose'], wire_sha256=row['wire_sha256'],
            policy_sha256=sha256(row['body']['messages'][0]['content'].encode()).hexdigest()) for row in rows])
    basis = digest(review)
    gateway = ModelGateway(UnapprovedSharedActivityAdapter(PendingSharedActivityGrant(basis)))
    denied = 0
    for task in tasks:
        try:
            gateway.execute(task)
        except ModelGatewayFailure as failure:
            if failure.code != 'shared-activity-use-unapproved':
                raise
            denied += 1
        else:
            raise ValueError('Unapproved Adapter must never invoke a model.')
    local_output = source.with_name('exact-unsent-wire-previews.json')
    with local_output.open('x', encoding='utf-8') as target:
        json.dump(dict(review_basis=basis, simulated_outputs=True, remote_calls=0, requests=rows),
            target, ensure_ascii=False, indent=2)
    review_output = REPO/'docs/experiments/s139/review.json'
    with review_output.open('x', encoding='utf-8') as target:
        json.dump(dict(review_basis=basis, review=review), target, ensure_ascii=False, indent=2)
    print(json.dumps(dict(review_basis=basis, reviewed_request_samples=len(rows),
        unapproved_adapter_denials=denied, credential_reads=0, remote_calls=0,
        exact_local_wire_path=str(local_output), review_path=str(review_output)), ensure_ascii=False))


if __name__ == '__main__':
    main()
