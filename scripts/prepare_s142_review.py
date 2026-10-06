"""Freeze exact unsent S142 tasks and review basis; leave all remote grants pending."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.credentials import DEEPSEEK_CREDENTIAL_SLOT
from dynamic_subject_agent.living_activity import LIVING_AUTHORITY, living_contract
from dynamic_subject_agent.living_activity_remote_preview import (
    PendingLivingActivityGrant, UnapprovedLivingActivityAdapter, living_remote_request_preview)
from dynamic_subject_agent.model_gateway import ModelGateway, ModelGatewayFailure, ModelTask, ModelTaskKind
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING

REPO = Path(__file__).resolve().parents[1]


def digest(value):
    return sha256(canonical_json(value).encode('utf-8')).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('local_preview', type=Path)
    parser.add_argument('--supersede-review-basis', help='Explicitly preserve and supersede one exact unapproved review object.')
    args = parser.parse_args()
    source = args.local_preview.resolve()
    preview = json.loads(source.read_text(encoding='utf-8'))
    scenario = json.loads((REPO/'docs/experiments/s142/scenarios.json').read_text(encoding='utf-8'))
    if (preview.get('version') != 's142-local-exact-review-1'
        or preview.get('simulated_outputs') is not True or preview.get('simulated_time') is not True
        or preview.get('remote_calls') != 0 or preview.get('credential_reads') != 0
        or preview.get('material_binding') != APPROVED_BINDING
        or preview.get('contract') != living_contract(APPROVED_BINDING)
        or preview.get('scenario_sha256') != digest(scenario)):
        raise ValueError('Current exact material, contract and explicitly synthetic LOCAL evidence required.')
    metadata = json.loads(source.with_name('metadata.json').read_text(encoding='utf-8'))
    witness_path = REPO/'.local_indexes/s142-checkpoint-verification-20261006/verification.json'
    witness = json.loads(witness_path.read_text(encoding='utf-8'))
    if (witness.get('version') != 's142-checkpoint-verification-1'
        or any(witness.get(key) is not True for key in ('previous_stage_preserved', 'failed_partial_saved',
            'task_count_and_sha_only_in_safe_metadata', 'raw_error_and_text_absent', 'io_failure_does_not_change_business_return'))
        or any(witness.get(key) != 0 for key in ('actual_product_calls', 'model_invocations', 'remote_calls', 'credential_reads'))):
        raise ValueError('Local checkpoint-only verification required without any new product/model/remote/credential call.')
    review_output = REPO/'docs/experiments/s142/review.json'
    previous = None
    if args.supersede_review_basis is not None:
        previous = json.loads(review_output.read_text(encoding='utf-8'))
        if (previous['review_basis'] != args.supersede_review_basis
            or digest(previous['review']) != previous['review_basis']
            or previous['review']['approval_status'] != 'not-granted'):
            raise ValueError('Only the exact explicit unapproved review may be preserved and superseded.')
    partial_metadata = source.with_name('partial-metadata.json')
    if partial_metadata.exists():
        checkpoint = json.loads(partial_metadata.read_text(encoding='utf-8'))
        if (checkpoint.get('version') != 's142-local-safe-checkpoint-1' or checkpoint.get('status') != 'complete'
            or checkpoint.get('error_type') is not None or checkpoint.get('checkpoint_io_error_types')):
            raise ValueError('Failed or unverified checkpoint runs cannot become an approved-use review basis.')
    elif previous is None:
        raise ValueError('Fresh runs require complete safe checkpoints; only an exact observability-only supersession may retain prior proven samples.')
    if metadata.get('local_preview_sha256') != digest(preview) or metadata.get('remote_rejected_before_registry') is not True:
        raise ValueError('LOCAL evidence must be complete and reject remote before registry access.')
    branches = {row['branch']: row for row in preview['branches']}
    if len(branches) != len(preview['branches']) or set(branches) != set(scenario['local_branches']):
        raise ValueError('All five distinct frozen LOCAL scenarios required.')
    if (branches['online-share-followup']['checks'].get('third_round_filters_complete_S1_derived_exchange') is not True
        or branches['paused-and-failure']['checks'].get('explicit_failure_resume_new_nonce_next_plan') is not True):
        raise ValueError('Final S1-lineage window and explicit failure-resume evidence required; older preparatory resources are insufficient.')
    rows, tasks = [], []
    for branch in preview['branches']:
        if not branch['checks'] or any(value is not True for value in branch['checks'].values()):
            raise ValueError('All observable LOCAL branch results must be verified before freezing review.')
        for stage in branch['stages']:
            if stage['local_calls'] not in (0, 1):
                raise ValueError('Every stage must remain within the single-request boundary.')
            if stage['status'] in ('committed', 'terminal') and stage['local_calls'] == 1 and stage.get('preview_equals_actual_task') is not True:
                raise ValueError('Every successful model stage must exactly match the readonly current builder preview.')
            if stage['status'] == 'terminal' and stage.get('canonical_complete_round_and_exact_output_verified') is not True:
                raise ValueError('A complete successful ordinary round must be proven in canonical state.')
        for actual in branch['actual_tasks']:
            task = ModelTask(ModelTaskKind(actual['kind']), actual['preview'])
            wire = living_remote_request_preview(task)
            if (wire['body']['messages'][0]['content'] != task.payload['policy']
                or json.loads(wire['body']['messages'][1]['content']) != task.payload['payload']):
                raise ValueError('Actual builder policy and projection must survive wire serialization exactly.')
            tasks.append(task)
            rows.append(dict(branch=branch['branch'], stage=actual['stage'],
                synthetic_output=True, simulated_time=True, **wire))
    required = {kind.value for kind in (ModelTaskKind.LIVING_ACTIVITY_CHOICE,
        ModelTaskKind.LIVING_ACTIVITY_SHARE, ModelTaskKind.LIVING_ACTIVITY_REPLY)}
    if {row['purpose'] for row in rows} != required:
        raise ValueError('Exact samples for all three proposed purposes required.')
    protocol = {key:value for key,value in rows[0]['body'].items() if key != 'messages'}
    if any({key:value for key,value in row['body'].items() if key != 'messages'} != protocol for row in rows):
        raise ValueError('Every proposed purpose must use one reviewed exact protocol.')
    policies, outputs, fields = {}, {}, {}
    for row, task in zip(rows, tasks, strict=True):
        policy_sha = sha256(task.payload['policy'].encode('utf-8')).hexdigest()
        if row['purpose'] in policies and policies[row['purpose']] != policy_sha:
            raise ValueError('A proposed purpose has inconsistent policies.')
        policies[row['purpose']] = policy_sha
        outputs[row['purpose']] = row['output_contract']
        names = sorted(task.payload['payload'])
        if row['purpose'] in fields and fields[row['purpose']] != names:
            raise ValueError('A proposed purpose has inconsistent top-level fields.')
        fields[row['purpose']] = names
    review = dict(version='s142-living-sharing-new-use-review-2', approval_status='not-granted',
        material_binding=APPROVED_BINDING, material_scope='same-reviewed-Sagiri-30-facts-4-author-interpretations-minimal-projection',
        timeline_schema=6, local_authority=LIVING_AUTHORITY,
        executable_remote_grant=None,
        future_execution_qualification='separate-exact-approved-live-qualification-on-new-independent-root;pending-and-local-do-not-upgrade',
        contract=preview['contract'], contract_sha256=digest(preview['contract']),
        provider='deepseek', endpoint=rows[0]['endpoint'], protocol=protocol,
        credential_use=rows[0]['credential_use'], timeout_seconds=30,
        credential_slot=dict(provider_id=DEEPSEEK_CREDENTIAL_SLOT.provider_id,
            account_id=DEEPSEEK_CREDENTIAL_SLOT.account_id, backend='Windows-Credential-Manager', authentication='HTTPS-Bearer-only'),
        requests_per_stage=1, automatic_retries=0, model_call_count_budget=None,
        purposes=dict(
            automatic_choice=dict(task_kind=ModelTaskKind.LIVING_ACTIVITY_CHOICE.value,
                trigger='900-cumulative-online-seconds-under-one-15-second-lease-or-explicit-labelled-simulation-opportunity',
                projection='same-S141-choice-fields-and-limits', input_fields=fields[ModelTaskKind.LIVING_ACTIVITY_CHOICE.value],
                default_paused=True, offline_catchup=False, output_contract=outputs[ModelTaskKind.LIVING_ACTIVITY_CHOICE.value]),
            independent_share=dict(task_kind=ModelTaskKind.LIVING_ACTIVITY_SHARE.value,
                trigger='separate-consider-action-after-new-committed-start-or-revise-text-plan',
                input_fields=fields[ModelTaskKind.LIVING_ACTIVITY_SHARE.value],
                activity_result_fields=['action', 'plan'], default_enabled=False,
                output_contract=outputs[ModelTaskKind.LIVING_ACTIVITY_SHARE.value],
                both_true_and_false_canonical_once=True, false_does_not_consume_new_topic=True,
                assistant_origin_no_fake_user_round=True,
                max_new_topics_per_utc8_day=2, daily_limit_is_model_call_budget=False,
                awaiting_successful_ordinary_reply_suppresses_new_topics=True,
                preflight_zero_calls=['paused', 'sharing-disabled', 'no-new-eligible-plan',
                    'already-considered', 'awaiting-reply', 'daily-topic-limit', 'needs-attention', 'source-blocked']),
            ordinary_share_followup=dict(task_kind=ModelTaskKind.LIVING_ACTIVITY_REPLY.value,
                trigger='explicit-ordinary-user-message', input_fields=fields[ModelTaskKind.LIVING_ACTIVITY_REPLY.value],
                evidence_fields=['shared_experience', 'activity_result', 'latest_share'],
                latest_share=dict(maximum_count=1, maximum_characters=400, fields=['text'],
                    maximum_successful_complete_ordinary_rounds_after_share_head=2,
                    absent=None, requires_history_enabled=True,
                    failed_or_query_or_reopen_does_not_consume_window=True,
                    answered_is_not_followup_window=True,
                    complete_S1_dependent_dialogue_excluded_after_window=True),
                output_contract=outputs[ModelTaskKind.LIVING_ACTIVITY_REPLY.value])),
        source=dict(maximum_count=1, maximum_characters=400,
            selection='explicit-exact-contiguous-committed-user-quote', fields=['label', 'quote'], label='E1', absent=None),
        plan_limits=dict(subject=160, composition=800, focus=400),
        current_message_limit=1000, recent_dialogue_complete_turns=2, recent_dialogue_total_characters=4000,
        source_controls='deactivate-replace-history-off-context-cutoff-filter-all-dependent-plan-result-share-and-complete-dialogue-turns',
        failure='typed-failed-closed;pause-and-needs-attention;no-event;no-automatic-retry;explicit-control-required-for-resume',
        publication='single-canonical-store-and-writer;atomic-prepared-claim-receipt;fresh-permission-head-source-day-fence;original-nonce-zero-model-recovery',
        excluded=['new-source-material', 'sealed-full-package-upload', 'old-root-migration', 'offline-catchup',
            'system-background-service', 'system-notifications', 'personality-rewrite', 'reflection', 'cloud',
            'new-provider', 'new-credential-purpose', 'external-actions', 'drafts', 'uncommitted-text',
            'unselected-history', 'runtime-civil-time-online-seconds-publication-timestamps',
            'internal-runtime-ids', 'local-decision-note-or-before-or-old-differences', 'raw-chain-of-thought'],
        local_preview_sha256=digest(preview), local_metadata_sha256=digest(metadata),
        scenario_sha256=digest(scenario), real_first_scene=scenario['real_first_scene'],
        policy_sha256=policies,
        samples=[dict(branch=row['branch'], stage=row['stage'], purpose=row['purpose'],
            wire_sha256=row['wire_sha256'], policy_sha256=sha256(row['body']['messages'][0]['content'].encode('utf-8')).hexdigest())
            for row in rows])
    review['helper_sha256'] = {name: sha256((REPO/'scripts'/name).read_bytes()).hexdigest()
        for name in ('run_s142_local_review.py', 'prepare_s142_review.py')}
    review['checkpoint_contract'] = dict(version='s142-local-safe-checkpoint-1',
        write_after_each_stage_and_actual_task=True, failure_status='failed-partial',
        safe_metadata='status-error_type-cumulative-counts-task-SHA-and-existing-safe-stage-results-only',
        raw_tasks='new-owned-local-resource-only', exception_text_saved=False,
        canonical_queries_or_mutations=False, checkpoint_io_does_not_change_business_outcome=True,
        validation=witness, validation_sha256=digest(witness),
        existing_31_samples_retained_without_new_product_or_model_run=True)
    if previous is not None:
        if any(review.get(key) != value for key,value in previous['review'].items() if key != 'version'):
            raise ValueError('Observability revision must preserve every original material/purpose/policy/wire/scene contract field.')
        review['previous_review_basis'] = previous['review_basis']
    basis = digest(review)
    gateway = ModelGateway(UnapprovedLivingActivityAdapter(PendingLivingActivityGrant(basis)))
    denied = 0
    for task in tasks:
        try:
            gateway.execute(task)
        except ModelGatewayFailure as failure:
            if failure.code != 'living-activity-use-unapproved':
                raise
            denied += 1
        else:
            raise ValueError('Pending Adapter must never invoke a model.')
    wire_output = source.with_name('exact-unsent-wire-previews-checkpoint-1.json' if previous is not None else 'exact-unsent-wire-previews.json')
    archive = None if previous is None else review_output.with_name('review.previous-'+previous['review_basis']+'.json')
    if wire_output.exists() or (review_output.exists() and previous is None) or (archive is not None and archive.exists()):
        raise ValueError('Frozen review resource already exists; retain it and investigate before replacement.')
    if archive is not None:
        with archive.open('xb') as target:
            target.write(review_output.read_bytes())
    with wire_output.open('x', encoding='utf-8') as target:
        json.dump(dict(review_basis=basis, simulated_outputs=True, simulated_time=True,
            remote_calls=0, credential_reads=0, requests=rows), target, ensure_ascii=False, indent=2)
    current_output = review_output.with_name('review.json.next') if previous is not None else review_output
    with current_output.open('x', encoding='utf-8') as target:
        json.dump(dict(review_basis=basis, review=review), target, ensure_ascii=False, indent=2)
    if previous is not None:
        current_output.replace(review_output)
    print(json.dumps(dict(review_basis=basis, samples=len(rows), pending_adapter_denials=denied,
        credential_reads=0, remote_calls=0, exact_unsent_wire_path=str(wire_output),
        review_path=str(review_output), previous_review_path=None if archive is None else str(archive),
        helper_sha256=review['helper_sha256'], policy_sha256=policies), ensure_ascii=False))


if __name__ == '__main__':
    main()
