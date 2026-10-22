"""Read-only source proof and upgrade BLUEPRINT. Deliberately no apply API."""
from contextlib import ExitStack
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID

from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.memorie_qualification_continuation import MemorieContinuationPlan


@dataclass(frozen=True)
class NativeActivityContinuationRequest:
    predecessor: MemorieContinuationPlan
    use_review_json: str
    expected_scope: str
    expected_owner_pid: int | None = None


@dataclass(frozen=True)
class NativeActivityContinuationView:
    status: str
    problem_code: str = ''
    proposal_json: str = ''
    proposal_digest: str = ''
    publication_prefix_verified: bool = False
    cold_source_observed: bool = False
    apply_supported: bool = False


def prepare(request):
    if type(request) is not NativeActivityContinuationRequest or type(request.predecessor) is not MemorieContinuationPlan:
        return NativeActivityContinuationView('unavailable','typed-native-activity-continuation-required')
    try:
        return _prepare(request)
    except FileNotFoundError:
        return NativeActivityContinuationView('unavailable','native-activity-source-not-ready')
    except ValueError:
        return NativeActivityContinuationView('unavailable','native-activity-source-or-review-changed')
    except Exception:
        return NativeActivityContinuationView('failed-closed','native-activity-source-unverified')


def _prepare(request):
    from dynamic_subject_agent.memorie_activity_use import validate_review
    from dynamic_subject_agent.memorie_qualification_continuation import verify
    from dynamic_subject_agent.memorie_continuation import MemorieSourceInspectionRequest, inspect_memorie_source
    from dynamic_subject_agent.host import _connect_readonly
    from dynamic_subject_agent.shared_activity import SHARED_DDL
    review_basis=validate_review(request.use_review_json)
    predecessor=request.predecessor
    original=json.loads(predecessor.plan_json)
    if predecessor.status!='available' or sha256(predecessor.plan_json.encode()).hexdigest()!=predecessor.plan_digest:
        raise ValueError('exact verified predecessor plan required')
    source=original['source_binding']
    expected=sha256((source['profile_id']+':'+source['timeline_id']).encode()).hexdigest()
    if request.expected_scope!=expected:
        raise ValueError('same original identity scope required')
    source_request=MemorieSourceInspectionRequest(Path(original['request']['state_path']),Path(original['request']['product_parent']),request.expected_owner_pid)
    before=inspect_memorie_source(source_request)
    if before.status!='no-op' or not before.metadata_json:
        return NativeActivityContinuationView(before.status if before.status=='failed-closed' else 'unavailable','native-activity-native-source-required')
    metadata=json.loads(before.metadata_json)
    if metadata['scope_key']!=expected or metadata['schema_version']!=11:
        raise ValueError('exact existing native schema11 required')
    if metadata['operation_counts'] not in ({},{'completed':metadata['head_sequence']}):
        return NativeActivityContinuationView('unavailable','native-activity-unresolved-source-operation')
    if verify(predecessor).status!='verified':
        return NativeActivityContinuationView('failed-closed','native-activity-predecessor-prefix-unverified')
    # Return metadata proofs, never user or assistant text. The existing verifier
    # checks the canonical bodies internally under the old receipt authority.
    with ExitStack() as stack:
        db=_connect_readonly(Path(metadata['timeline_path']));stack.callback(db.close);db.execute('BEGIN')
        rows=db.execute('''SELECT hex(op.operation_id),hex(op.payload_fingerprint),hex(claim.key_digest),
            outcome.head_sequence,hex(outcome.outcome_digest)
            FROM subject_operation op LEFT JOIN idempotency_claim claim USING(operation_id)
            LEFT JOIN timeline_outcome outcome USING(operation_id) ORDER BY outcome.head_sequence''').fetchall()
        proofs=[dict(operation_id=str(UUID(hex=row[0])),payload_fingerprint=row[1].lower(),key_digest=row[2].lower(),
            head_sequence=row[3],outcome_digest=row[4].lower()) for row in rows]
        if len(proofs)!=metadata['head_sequence'] or [p['head_sequence'] for p in proofs]!=list(range(1,len(proofs)+1)):
            raise ValueError('complete unique original claims required')
        if any(len(p[k])!=64 for p in proofs for k in ('payload_fingerprint','key_digest','outcome_digest')):
            raise ValueError('source proof incomplete')
    after=inspect_memorie_source(source_request)
    if after.metadata_digest!=before.metadata_digest or verify(predecessor).status!='verified':
        raise ValueError('source advanced or changed')
    cold=not metadata['writer_leases'] and metadata['gate_state']=='closed'
    body=dict(version='memorie-native-activity-continuation-blueprint-m013-1',status='blueprint-not-executable',
        source_observation=metadata,source_observation_digest=before.metadata_digest,
        predecessor_plan_digest=predecessor.plan_digest,use_review_basis=review_basis,original_request_proofs=proofs,
        target_schema_candidate=12,target_http_protocol_candidate=3,planned_added_tables=list(SHARED_DDL),
        preserve=['profile_id','timeline_id','scope_key','canonical-root-and-store-ids','all-existing-table-rows',
            'all-original-request-ids-claims-and-outcomes','schema11-continuation-receipt','legacy-read-only-authorities',
            'history-permissions-and-cutoffs','unsent-drafts-and-client-receipts'],
        activation=dict(same_root=True,copy_development_timeline=False,new_writer=False,
            entry_key_change_required=True,scope_key_change=False,old_nonce_read_only=True,old_nonce_redelivery=False),
        recovery=['freeze-new-cold-source-and-full-object-digests','separate-exact-data-consent',
            'prepare-successor-qualification-without-activation','registry-pending-fence',
            'atomic-same-store-DDL-binding-gate-receipt-governance-commit','reconcile-registry-forward',
            'verify-old-and-new-publications-and-original-UUIDs-before-opening-one-writer'],
        cold_source_observed=cold,publication_prefix_verified=True,transcript_exposed=False,
        remaining=['human-new-use-approval','native-plus-shared-runtime-and-schema12-recovery-implementation',
            'fresh-cold-byte-bound-plan-and-separate-data-consent','new-client-binding-and-separate-installation-consent'],
        apply_supported=False,data_upgrade_authorized=False,installation_authorized=False)
    raw=canonical_json(body)
    return NativeActivityContinuationView('prepared',proposal_json=raw,proposal_digest=sha256(raw.encode()).hexdigest(),
        publication_prefix_verified=True,cold_source_observed=cold)
