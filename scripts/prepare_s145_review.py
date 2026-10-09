"""Freeze exact unsent S145 wire from completed LOCAL tasks; always unapproved."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind, ModelGatewayFailure
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
from dynamic_subject_agent.working_understanding import working_contract
from dynamic_subject_agent.working_understanding_remote_preview import (
    PendingWorkingUnderstandingGrant, UnapprovedWorkingUnderstandingAdapter,
    working_remote_request_preview,
)

REPO = Path(__file__).resolve().parents[1]
REQUIRED_CHECKS = frozenset((
    'source_heads_outside_recent_two', 'reopen_zero_model_same_view',
    'next_choice_plan_changed', 'choice_includes_working_understanding',
    'same_nonce_zero_model', 'reply_same_committed_plan',
    'disabled_whole_derived_chain_hidden', 'disabled_preview_no_working_understanding',
    'disabled_preview_no_old_result_or_history', 'disabled_actual_reply_no_old_chain',
    'correction_new_understanding_and_plan', 'corrected_reply_same_plan',
))


def digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


def run(root):
    root=root.resolve()
    if not root.is_relative_to((REPO/'.local_indexes/s145').resolve()):
        raise ValueError('Only the owned S145 exact review resource is readable.')
    exact=json.loads((root/'exact-unsent-previews.json').read_text(encoding='utf-8'))
    metadata=json.loads((root/'metadata.json').read_text(encoding='utf-8'))
    if (exact['status']!='complete' or metadata['status']!='complete'
        or exact['synthetic_outputs'] is not True
        or not REQUIRED_CHECKS <= set(metadata['checks'])
        or any(metadata['checks'][name] is not True for name in REQUIRED_CHECKS)
        or metadata['exact_unsent_previews_sha256']!=digest(exact)):
        raise ValueError('Complete, verified first LOCAL evidence is required.')
    tasks=exact['tasks']
    if not tasks or any(row['status']!='complete' for row in tasks):
        raise ValueError('All retained actual model attempts must be complete before freezing.')
    contract=working_contract(APPROVED_BINDING)
    scene=json.loads((REPO/'docs/experiments/s145/scene.json').read_text(encoding='utf-8'))
    live_scene=json.loads((REPO/'docs/experiments/s145/live-scene.json').read_text(encoding='utf-8'))
    current_runner_sha=sha256((REPO/'scripts/run_s145_local_review.py').read_bytes()).hexdigest()
    if (metadata['scene_sha256']!=digest(scene)
        or metadata['runner_sha256_at_execution']!=current_runner_sha
        or exact['runner_sha256_at_execution']!=current_runner_sha
        or metadata['local_contract_sha256_at_execution']!=digest(contract)
        or exact['local_contract_sha256_at_execution']!=digest(contract)):
        raise ValueError('Current scene/runner/contract does not match the executed LOCAL witnesses.')
    wires=[]
    rejected=0
    pending=UnapprovedWorkingUnderstandingAdapter(PendingWorkingUnderstandingGrant('0'*64))
    summaries=[]
    for index,row in enumerate(tasks):
        task=ModelTask(ModelTaskKind(row['kind']), row['preview'])
        wire=working_remote_request_preview(task)
        if json.loads(wire['body']['messages'][1]['content']) != row['preview']['payload']:
            raise ValueError('Wire payload does not match actual LOCAL execution.')
        if wire['body']['messages'][0]['content'] != row['preview']['policy']:
            raise ValueError('Wire policy does not match actual LOCAL execution.')
        payload=row['preview']['payload']
        original_source=(payload.get('evidence') or payload).get('shared_experience')
        if original_source is not None:
            raise ValueError('The new candidate does not acquire the legacy E1 selection capability.')
        try:
            pending.invoke(task)
        except ModelGatewayFailure as error:
            if error.code!='working-understanding-use-unapproved':
                raise
            rejected+=1
        else:
            raise ValueError('Pending authority executed a request.')
        wires.append(dict(ordinal=index, request=wire))
        summaries.append(dict(ordinal=index,purpose=task.kind.value,
            task_sha256=digest(row['preview']), output_sha256=digest(row['output']),
            wire_sha256=wire['wire_sha256'], output_mode='json' if 'response_format' in wire['body'] else 'text'))
    purposes=sorted({row['purpose'] for row in summaries})
    if len(purposes)!=3:
        raise ValueError('All three new purposes require actual LOCAL witnesses.')
    wire_resource=dict(version='s145-exact-unsent-wires-1',status='unapproved',requests=wires)
    wire_path=root/'exact-unsent-wire-previews.json'
    if wire_path.exists():
        raise ValueError('Prior wire evidence is retained; no overwrite.')
    wire_path.write_text(json.dumps(wire_resource,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    review=dict(version='s145-working-understanding-review-1',approval_status='not-granted',
        existing_material_binding=APPROVED_BINDING,local_contract_sha256=digest(contract),
        scene_sha256=digest(scene),actual_local_tasks_sha256=digest(exact),
        first_live_scene_sha256=digest(live_scene),
        first_live_scene_maximum_requests=live_scene['maximum_first_requests'],
        exact_unsent_wire_previews_sha256=digest(wire_resource),
        local_runner_sha256=current_runner_sha,
        review_preparer_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        provider='deepseek',credential_slot=dict(provider_id='deepseek',account_id='default'),
        endpoint='https://api.deepseek.com/chat/completions',requests_per_manual_action=1,automatic_retries=0,
        new_purposes=purposes,source_scope='exactly-two-distinct-committed-user-quotes-each-400-or-less',
        understanding_scope='tentative-composition-text-not-permanent-preference-persona-or-world-fact',
        understanding_max_chars=240,understandings_per_choice_or_reply=1,
        committed_plan_limits=dict(subject=160,composition=800,focus=400),
        ordinary_current_max_chars=1000,ordinary_recent_complete_turns=2,ordinary_recent_max_chars=4000,
        existing_shared_experience='always-null-no-legacy-E1-selection-capability',
        formation_activity_result='at-most-one-committed-independent-composition-text-plan-or-null',
        note_policy='existing-choice-note-160-local-only-never-reprojected',
        entry_policy='independent-new-identity-only-no-legacy-migration-no-production-service-restart',
        triggers='explicit-manual-form-choice-or-ordinary-message-only',
        invalidation='disable-replace-history-off-cutoff-and-permission-fence-filter-whole-derived-chain',
        excluded=['automatic-reflection','persona-rewrite','background-life','system-notification','cloud',
            'new-private-material','new-provider','new-credential-use','physical-delete','legacy-migration'],
        local_witnesses=summaries,pending_rejections=rejected,remote_calls=0,credential_reads=0,
        character_effect_verified=False,real_cross_day_verified=False,day_boundary_logic_verified=False)
    review['review_basis']=digest(review)
    destination=REPO/'docs/experiments/s145/review.json'
    if destination.exists():
        raise ValueError('Existing exact review retained; do not silently replace it.')
    destination.write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    safe=dict(status='unapproved-review-frozen',review_basis=review['review_basis'],
        local_model_tasks=len(tasks),pending_rejections=rejected,remote_calls=0,credential_reads=0,
        all_wire_payloads_match_actual_tasks=True,purposes=purposes,
        exact_wire_resource_sha256=review['exact_unsent_wire_previews_sha256'])
    (root/'wire-review-metadata.json').write_text(json.dumps(safe,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return safe


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True,type=Path)
    args=parser.parse_args()
    try:
        result=run(args.root)
    except Exception as error:
        raise SystemExit('S145 review not frozen; '+type(error).__name__) from None
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
