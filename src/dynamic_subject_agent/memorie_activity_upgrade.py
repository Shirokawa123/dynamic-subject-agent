"""Explicit same-store schema11 -> native activity continuation.

The first continuation receipt stays intact. Its finite read authority and a
second frozen prefix establish history; no synthetic shared records are added.
"""
from contextlib import ExitStack
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
import json
import re
import sqlite3

from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.memorie_qualification_continuation import (
    MemorieContinuationPlan, MemorieContinuationResult, _digest, _hash, _record, _readonly_host)
from dynamic_subject_agent.memorie_activity_live import NATIVE_RUNTIME as RUNTIME_CONTRACT

VERSION = 'memorie-native-activity-continuation-m027-1'
TABLE = 'memorie_activity_continuation'
DDL = '''CREATE TABLE memorie_activity_continuation (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    receipt_json TEXT NOT NULL, receipt_digest TEXT NOT NULL)'''


@dataclass(frozen=True)
class NativeActivityUpgradeRequest:
    predecessor: MemorieContinuationPlan
    approval_path: Path

    @property
    def state_path(self): return Path(json.loads(self.predecessor.plan_json)['request']['state_path'])
    @property
    def product_parent(self): return Path(json.loads(self.predecessor.plan_json)['request']['product_parent'])


@dataclass(frozen=True)
class NativeActivityUpgradePlan:
    status: str
    problem_code: str = ''
    plan_json: str = ''
    plan_digest: str = ''


@dataclass(frozen=True)
class NativeActivityUpgradeConsent:
    plan_digest: str
    data_upgrade_confirmed: bool


def request_from_body(body):
    value = body['request']
    return NativeActivityUpgradeRequest(MemorieContinuationPlan(**value['predecessor']), Path(value['approval_path']))


def target_contract(source_qri, envelope):
    from dynamic_subject_agent.memorie_activity_live import contract, REVIEW
    from dynamic_subject_agent.original_whole_chat import validate_whole_envelope
    from dynamic_subject_agent.memorie_native import contract as native_contract, SCOPE, REVIEW as NATIVE_REVIEW
    old = source_qri['reviewed_chat_contract']
    if native_contract(envelope,SCOPE,NATIVE_REVIEW)!=old:raise ValueError('same native sealed material required')
    asset=envelope['runtime_asset']
    binding=dict(definition_basis=envelope['definition_basis'],runtime_asset_sha=envelope['runtime_asset_sha'],
        persona_digest=asset['persona_digest'],subject_id=asset['subject']['subject_id'],anchor_id=asset['anchor']['anchor_id'])
    result=contract(dict(binding, review_basis=REVIEW, scope_digest=REVIEW), native=True)
    validate_whole_envelope(envelope,result)
    return result


def publication_key(contract):
    from dynamic_subject_agent.original_whole_chat import whole_publication_key
    return whole_publication_key(contract)


def _proofs(db, head):
    rows = db.execute('''SELECT hex(op.operation_id),hex(op.payload_fingerprint),hex(claim.key_digest),
        outcome.head_sequence,hex(outcome.outcome_digest),hex(outcome.plan_id)
        FROM subject_operation op LEFT JOIN idempotency_claim claim USING(operation_id)
        LEFT JOIN timeline_outcome outcome USING(operation_id)
        WHERE outcome.head_sequence<=? ORDER BY outcome.head_sequence''', (head,)).fetchall()
    result = [dict(operation_id=str(UUID(hex=r[0])),fingerprint=r[1].lower(),key_digest=r[2].lower(),
        head_sequence=r[3],outcome_digest=r[4].lower(),plan_id=str(UUID(hex=r[5]))) for r in rows]
    if len(result) != head or [r['head_sequence'] for r in result] != list(range(1, head+1)):
        raise ValueError('complete original prefix required')
    return result


def prepare(request):
    if (type(request) is not NativeActivityUpgradeRequest or type(request.predecessor) is not MemorieContinuationPlan
        or not isinstance(request.approval_path, Path) or not request.approval_path.is_absolute()):
        return NativeActivityUpgradePlan('unavailable','typed-activity-upgrade-request-required')
    try:
        body = _prepare(request)
        return NativeActivityUpgradePlan('available',plan_json=canonical_json(body),plan_digest=_digest(body))
    except (ValueError, FileNotFoundError):
        return NativeActivityUpgradePlan('unavailable','activity-upgrade-source-not-cold-or-verified')
    except Exception as error:
        return NativeActivityUpgradePlan('failed-closed',getattr(error,'code','') or 'activity-upgrade-source-unverified')


def _prepare(request):
    from dynamic_subject_agent.memorie_activity_live import ApprovedNativeActivityGrant, audit_path
    from dynamic_subject_agent.memorie_qualification_continuation import verify as verify_predecessor
    from dynamic_subject_agent.memorie_continuation import MemorieSourceInspectionRequest, inspect_memorie_source
    from dynamic_subject_agent.host import RuntimeHostRootRef, _connect_readonly, _BINDING_COLUMNS
    from dynamic_subject_agent.studio import StudioRootRef
    from dynamic_subject_agent.timeline import TimelineEngine, _read_admission_gate, _read_timeline_basis
    approval = ApprovedNativeActivityGrant(request.approval_path).validate()
    if verify_predecessor(request.predecessor).status != 'verified':
        raise ValueError('exact committed predecessor required')
    source = inspect_memorie_source(MemorieSourceInspectionRequest(request.state_path, request.product_parent))
    if source.status != 'no-op': raise ValueError('native source required')
    metadata = json.loads(source.metadata_json)
    if (metadata['schema_version'] != 11 or metadata['writer_leases'] or metadata['gate_state'] != 'closed'
        or metadata['operation_counts'] not in ({}, {'completed':metadata['head_sequence']})):
        raise ValueError('cold completed native prefix required')
    paths = metadata['source_files']; hashes = {k:_hash(v) for k,v in paths.items()}
    record = _record(json.loads(request.state_path.read_bytes()))
    if any(record.get(k) for k in ('pending_memorie_continuation','pending_memorie_activity_continuation','whole_chat_activation','pending_whole_chat_activation')):
        raise ValueError('unmodified source registry required')
    hostref = RuntimeHostRootRef.from_dict(record['host_location']); studio = StudioRootRef.from_dict(record['studio_location'])
    with ExitStack() as stack:
        control = _connect_readonly(hostref.control_database); stack.callback(control.close)
        host = _readonly_host(hostref, studio, control)
        binding = host._binding_from_row(control.execute(f'SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding WHERE binding_id=?',
            (metadata['binding_id'],)).fetchone())
        host._require_binding_permit(binding)
        db = _connect_readonly(binding.timeline_root.timeline_database); stack.callback(db.close); db.execute('BEGIN')
        if db.execute("SELECT COUNT(*) FROM sqlite_schema WHERE type='trigger'").fetchone()[0]:
            raise ValueError('unexpected canonical triggers')
        authority = host._authority_for_binding(binding)
        if _read_admission_gate(db).authority != authority: raise ValueError('source authority differs')
        engine = TimelineEngine(binding.timeline_root, authority, db, None)
        engine.list_native_interactions()
        proofs = _proofs(db, metadata['head_sequence'])
        if len(proofs) != db.execute('SELECT COUNT(*) FROM subject_operation').fetchone()[0]:
            raise ValueError('unpublished original operations retained, not redelivered')
        profile = _connect_readonly(studio.profile_database); stack.callback(profile.close)
        qri = json.loads(profile.execute('SELECT qri_json FROM qri_publication WHERE publication_key=?',(record['publication_key'],)).fetchone()[0])
        envelope=json.loads(profile.execute('SELECT snapshot_json FROM genesis_snapshot WHERE snapshot_id=?',(qri['genesis_snapshot_id'],)).fetchone()[0])['reviewed_definition']
        control.row_factory = db.row_factory = sqlite3.Row
        body = dict(version=VERSION,request=dict(predecessor=asdict(request.predecessor),approval_path=str(request.approval_path)),
            source_files=paths,source_hashes=hashes,source_registry=record,
            source_binding=dict(control.execute('SELECT * FROM runtime_authority_binding WHERE binding_id=?',(binding.binding_id,)).fetchone()),
            source_qri=qri,source_definition=envelope,source_gate=dict(db.execute('SELECT * FROM admission_gate').fetchone()),
            source_basis=vars(_read_timeline_basis(db)),original_requests=proofs,
            use_approval=approval,use_approval_sha256=_hash(request.approval_path),
            target_activation=dict(contract=target_contract(qri,envelope),audit_path=str(audit_path().resolve())))
    if hashes != {k:_hash(v) for k,v in paths.items()} or verify_predecessor(request.predecessor).status != 'verified':
        raise ValueError('source advanced during preparation')
    return body


def _checked_plan(plan):
    if type(plan) is not NativeActivityUpgradePlan or plan.status != 'available':
        raise ValueError('exact activity plan required')
    body = json.loads(plan.plan_json)
    if body['version'] != VERSION or canonical_json(body) != plan.plan_json or _digest(body) != plan.plan_digest:
        raise ValueError('activity plan changed')
    return body


def apply(plan, consent, *, _fault_hook=None):
    if (type(plan) is not NativeActivityUpgradePlan or type(consent) is not NativeActivityUpgradeConsent
        or consent.data_upgrade_confirmed is not True or consent.plan_digest != plan.plan_digest):
        return MemorieContinuationResult('unavailable','exact-activity-data-consent-required')
    try:
        from dynamic_subject_agent.memorie_qualification_continuation import _apply
        return _apply(_checked_plan(plan),plan.plan_digest,consent,_fault_hook or (lambda point:None),_activity=True)
    except Exception as error:
        return MemorieContinuationResult('failed-closed',getattr(error,'code','') or 'activity-upgrade-not-applied-or-needs-recovery',plan.plan_digest)


def upgrade_store(db):
    from dynamic_subject_agent.timeline import _LIFE_DDL
    from dynamic_subject_agent.shared_activity import SHARED_DDL
    from dynamic_subject_agent.whole_context_boundary import CONTEXT_DDL
    for statement in (*SHARED_DDL,*CONTEXT_DDL,_LIFE_DDL[1],DDL):
        db.execute(re.sub(r'(CREATE TABLE\s+)(\w+)',r'\1canonical.\2',statement,count=1))


def finish_registry(body, record):
    from dynamic_subject_agent.memorie_activity_live import ApprovedNativeActivityGrant, open_audit
    audit = open_audit(ApprovedNativeActivityGrant(Path(body['request']['approval_path'])))
    if str(audit.path.resolve()) != body['target_activation']['audit_path']: raise ValueError('approved audit path changed')
    record['memorie_activity_predecessor_activation'] = record.pop('chat_activation')
    record['living_permission'] = dict(paused=True,sharing_enabled=False,revision=0,needs_attention=False,source_blocked=False)
    record['living_control_receipts'] = {}


def read_receipt(db, authority=None):
    from dynamic_subject_agent.timeline import AdmissionFailedClosed
    try:
        return _read_receipt(db,authority)
    except Exception as error:
        raise AdmissionFailedClosed('activity-continuation-receipt-unverified','Activity continuation read authority is unverified') from error


def _read_receipt(db, authority=None):
    if db.execute('PRAGMA user_version').fetchone()[0] != 12: return None
    if not db.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?",(TABLE,)).fetchone(): return None
    from dynamic_subject_agent.memorie_qualification_continuation import read_receipt as read_predecessor
    from dynamic_subject_agent.memorie_activity_live import ApprovedNativeActivityGrant
    from dynamic_subject_agent.shared_activity import LIVING_LIVE_AUTHORITY
    row = db.execute('SELECT receipt_json,receipt_digest FROM memorie_activity_continuation WHERE singleton=1').fetchone()
    receipt = json.loads(row[0]); body = receipt['plan']; before,after = body['source_binding'],receipt['target_binding']
    if (canonical_json(receipt)!=row[0] or _digest(receipt)!=row[1] or receipt['version']!=VERSION or body['version']!=VERSION
        or receipt['plan_digest']!=_digest(body)
        or receipt['consent']!=dict(plan_digest=receipt['plan_digest'],data_upgrade_confirmed=True)):
        raise ValueError('activity receipt changed')
    old = read_predecessor(db)
    if old is None or old['target_binding']!=before or body['request']['predecessor']!=asdict(MemorieContinuationPlan('available',plan_json=canonical_json(old['plan']),plan_digest=old['plan_digest'])):
        raise ValueError('exact predecessor receipt required')
    qri=body['source_qri']; unsigned=dict(qri);unsigned.pop('integrity_digest')
    if (_digest(unsigned)!=qri['integrity_digest'] or qri['integrity_digest']!=before['qri_integrity_digest']
        or any(qri[k]!=before[k] for k in ('qualification_id','qualification_revision','profile_id','genesis_snapshot_id','knowledge_snapshot_id','provider_authority'))
        or qri['reviewed_chat_contract']!=old['plan']['target_activation']['contract']):
        raise ValueError('native predecessor qualification changed')
    grant=ApprovedNativeActivityGrant(Path(body['request']['approval_path']))
    if grant.validate()!=body['use_approval'] or _hash(grant.approval_path)!=body['use_approval_sha256']:
        raise ValueError('approved use changed')
    if body['target_activation']['contract']!=target_contract(qri,body['source_definition']):raise ValueError('activity target use changed')
    stable=('binding_id','authority_scope_id','profile_id','timeline_id','timeline_root_json','timeline_root_id',
        'timeline_control_store_id','timeline_store_id','genesis_snapshot_id','knowledge_snapshot_id',
        'studio_root_id','studio_store_id','host_root_id','host_control_store_id')
    if (any(before[k]!=after[k] for k in stable) or after['binding_revision']!=before['binding_revision']+1
        or after['binding_epoch']!=before['binding_epoch']+1 or after['qualification_id']==before['qualification_id']
        or after['provider_authority']!=LIVING_LIVE_AUTHORITY or after['runtime_contract_version']!=RUNTIME_CONTRACT):
        raise ValueError('activity identity changed')
    if authority is not None and any(getattr(authority,k)!=after[k] for k in
        ('binding_id','binding_revision','binding_epoch','qualification_id','qualification_revision','authority_scope_id','profile_id','timeline_id','provider_authority')):
        raise ValueError('activity receipt is not current authority')
    proofs=_proofs(db,body['source_basis']['head_sequence'])
    if proofs!=body['original_requests'] or body['source_basis']['published_outcome_digest']!=(proofs[-1]['outcome_digest'] if proofs else None):
        raise ValueError('original request prefix changed')
    return receipt


def historical_binding(current, *, member=None):
    from dynamic_subject_agent.host import _connect_readonly,_branch_governance_member_matches
    from dynamic_subject_agent.memorie_qualification_continuation import historical_binding as predecessor_binding
    db=_connect_readonly(current.timeline_root.timeline_database)
    try: receipt=read_receipt(db)
    finally: db.close()
    if receipt is None:return None
    before,after=receipt['plan']['source_binding'],receipt['target_binding']
    if any(getattr(current,k)!=after[k] for k in ('binding_id','binding_revision','binding_epoch','qualification_id','qri_integrity_digest','provider_authority')):
        raise ValueError('current activity binding differs')
    old=replace(current,**{k:before[k] for k in ('binding_revision','binding_epoch','qualification_id','qualification_revision',
        'qri_publication_key','qri_integrity_digest','runtime_contract_version','provider_authority','capability_manifest_version')},
        policy_decision_ids=tuple(json.loads(before['policy_decision_ids_json'])))
    if member is None or _branch_governance_member_matches(member,old):return old
    return predecessor_binding(old,member=member)


def _verify_committed(body,digest,record):
    from dynamic_subject_agent.host import RuntimeHostRootRef,_connect_readonly,_BINDING_COLUMNS
    from dynamic_subject_agent.studio import StudioRootRef
    from dynamic_subject_agent.timeline import TimelineEngine,_read_admission_gate,_verify_manifest,_verify_store_integrity,_TIMELINE_TABLES,TIMELINE_SCHEMA_FAMILY
    hostref=RuntimeHostRootRef.from_dict(record['host_location']);studio=StudioRootRef.from_dict(record['studio_location'])
    with ExitStack() as stack:
        control=_connect_readonly(hostref.control_database);stack.callback(control.close);control.execute('BEGIN')
        host=_readonly_host(hostref,studio,control)
        binding=host._binding_from_row(control.execute(f'SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding WHERE binding_id=?',(body['source_binding']['binding_id'],)).fetchone())
        host._require_binding_permit(binding);qri=host._qri_for_binding(binding)
        if qri.predecessor_qualification_id!=body['source_binding']['qualification_id'] or qri.reviewed_chat_contract!=body['target_activation']['contract']:
            raise ValueError('committed activity qualification differs')
        db=_connect_readonly(binding.timeline_root.timeline_database);stack.callback(db.close);db.execute('BEGIN')
        _verify_manifest(db,root_id=binding.timeline_root.root_id,store_id=binding.timeline_root.timeline_store_id,store_kind='timeline',schema_family=TIMELINE_SCHEMA_FAMILY)
        _verify_store_integrity(db,expected_tables=_TIMELINE_TABLES)
        authority=host._authority_for_binding(binding)
        if _read_admission_gate(db).authority!=authority:raise ValueError('activity gate differs')
        receipt=read_receipt(db,authority)
        if receipt is None or receipt['plan_digest']!=digest or receipt['plan']!=body:raise ValueError('wrong activity receipt')
        engine=TimelineEngine(binding.timeline_root,authority,db,None)
        engine.list_native_interactions();engine.shared_activity_basis(SimpleNamespace(history_enabled=False))
        return qri


def verify(plan):
    if type(plan) is not NativeActivityUpgradePlan or plan.status != 'available':
        return MemorieContinuationResult('unavailable','exact-activity-continuation-plan-required')
    try:
        from dynamic_subject_agent.first_life_authorization import registry_lock
        body=_checked_plan(plan);request=request_from_body(body)
        with registry_lock(request.state_path):
            record=_record(json.loads(request.state_path.read_bytes()))
            if record.get('pending_memorie_activity_continuation') or record.get('memorie_activity_continuation')!=plan.plan_digest:
                return MemorieContinuationResult('unavailable','activity-continuation-not-committed',plan.plan_digest)
            if record['whole_chat_activation']!=body['target_activation'] or record['memorie_activity_predecessor_activation']!=body['source_registry']['chat_activation']:
                raise ValueError('activity registry differs')
            qri=_verify_committed(body,plan.plan_digest,record)
            if qri.publication_key!=record['publication_key']:raise ValueError('activity registry qualification differs')
        return MemorieContinuationResult('verified',plan_digest=plan.plan_digest)
    except Exception:
        return MemorieContinuationResult('failed-closed','activity-continuation-verification-failed',getattr(plan,'plan_digest',''))
