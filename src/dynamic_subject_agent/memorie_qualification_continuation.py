"""Explicit cold qualification continuation; never an implicit product upgrade.

The plan and separate consent are local, exact objects. Studio publication is
preparation; the only authority switch is a DELETE-journal multi-store commit.
Registry pending state fences ordinary opening until that commit is reconciled.
"""
from contextlib import ExitStack
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from dynamic_subject_agent.frozen_attempt import canonical_json

VERSION = 'memorie-qualification-continuation-m002-1'
DDL = '''CREATE TABLE memorie_qualification_continuation (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    receipt_json TEXT NOT NULL, receipt_digest TEXT NOT NULL)'''


@dataclass(frozen=True)
class MemorieContinuationRequest:
    state_path: Path
    product_parent: Path
    approval_path: Path
    audit_path: Path


@dataclass(frozen=True)
class MemorieContinuationPlan:
    status: str
    problem_code: str = ''
    plan_json: str = ''
    plan_digest: str = ''


@dataclass(frozen=True)
class MemorieContinuationConsent:
    plan_digest: str
    data_upgrade_confirmed: bool


@dataclass(frozen=True)
class MemorieContinuationResult:
    status: str
    problem_code: str = ''
    plan_digest: str = ''


def _digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


def _hash(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def _record(state):
    return next(r for r in state['identities'] if r['identity_id'] == state['active_identity_id'])


def _readonly_host(location, studio, db):
    from dynamic_subject_agent.host import RuntimeHost, _CognitionAssembly, _verify_control
    _verify_control(location, studio, db)
    return RuntimeHost(location, studio, db, _CognitionAssembly._prepared_control_only(),
        fault_hook=None, runtime_interrupt_at=None, runtime_fault_hook=None,
        instance_id=str(uuid4()), runtime_identity=None)


def prepare(request):
    if type(request) is not MemorieContinuationRequest or not all(
        isinstance(p, Path) and p.is_absolute() for p in vars(request).values()):
        return MemorieContinuationPlan('unavailable', 'typed-cold-continuation-request-required')
    try:
        body = _prepare(request)
        return MemorieContinuationPlan('available', plan_json=canonical_json(body), plan_digest=_digest(body))
    except (ValueError, FileNotFoundError) as error:
        return MemorieContinuationPlan('unavailable', 'memorie-continuation-source-not-quiescent-or-verified')
    except Exception as error:
        code = getattr(error, 'code', '')
        return MemorieContinuationPlan('failed-closed', code or 'memorie-continuation-source-unverified')


def _prepare(request):
    from dynamic_subject_agent.memorie_continuation import MemorieSourceInspectionRequest, inspect_memorie_source
    from dynamic_subject_agent.memorie_native import load_approval, contract, SCOPE, REVIEW
    from dynamic_subject_agent.memorie_companion_contract import INTENT_VERSION
    from dynamic_subject_agent.host import RuntimeHostRootRef, _connect_readonly, _BINDING_COLUMNS
    from dynamic_subject_agent.studio import StudioRootRef
    from dynamic_subject_agent.timeline import (TimelineEngine, _read_admission_gate, _read_timeline_basis, OperationState,
        _verify_manifest, _verify_store_integrity, _TIMELINE_TABLES, TIMELINE_SCHEMA_FAMILY)
    observation = inspect_memorie_source(MemorieSourceInspectionRequest(request.state_path, request.product_parent))
    if observation.status != 'available':
        raise ValueError('exact legacy source required')
    metadata = json.loads(observation.metadata_json)
    if (metadata['contract_version'] != INTENT_VERSION or metadata['schema_version'] != 1
        or metadata['writer_leases'] or metadata['gate_state'] != 'closed'):
        raise ValueError('closed legacy source required')
    # Stable file identities and exact source bytes are part of the consent.
    source_files = metadata['source_files']
    hashes = {name: _hash(path) for name, path in source_files.items()}
    state = json.loads(request.state_path.read_bytes()); record = _record(state)
    if record.get('pending_memorie_continuation'):
        raise ValueError('resume the original plan')
    hostref = RuntimeHostRootRef.from_dict(record['host_location'])
    studio = StudioRootRef.from_dict(record['studio_location'])
    with ExitStack() as stack:
        control = _connect_readonly(hostref.control_database); stack.callback(control.close)
        host = _readonly_host(hostref, studio, control)
        row = control.execute(f"SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding WHERE binding_id=?",
            (metadata['binding_id'],)).fetchone()
        binding = host._binding_from_row(row)
        host._require_binding_permit(binding)
        db = _connect_readonly(binding.timeline_root.timeline_database); stack.callback(db.close)
        db.execute('BEGIN')
        _verify_manifest(db, root_id=binding.timeline_root.root_id, store_id=binding.timeline_root.timeline_store_id,
            store_kind='timeline', schema_family=TIMELINE_SCHEMA_FAMILY)
        _verify_store_integrity(db, expected_tables=_TIMELINE_TABLES)
        if db.execute("SELECT COUNT(*) FROM sqlite_schema WHERE type='trigger'").fetchone()[0]:
            raise ValueError('unexpected canonical triggers')
        gate = _read_admission_gate(db)
        if gate.authority != host._authority_for_binding(binding):
            raise ValueError('gate/binding mismatch')
        engine = TimelineEngine(binding.timeline_root, gate.authority, db, None)
        engine._memorie_request_lookup = True
        publications = engine._verified_publications()
        legacy = []
        for outcome, command, _ in publications:
            ref = outcome.operation_ref
            if engine.query(ref).operation_state is not OperationState.COMPLETED:
                raise ValueError('unresolved source operation')
            claim = db.execute('SELECT hex(key_digest),hex(payload_fingerprint) FROM idempotency_claim WHERE operation_id=?',
                (UUID(ref.operation_id).bytes,)).fetchall()
            if len(claim) != 1 or claim[0][1].lower() != command.payload_fingerprint:
                raise ValueError('source claim mismatch')
            legacy.append(dict(operation_id=ref.operation_id, fingerprint=command.payload_fingerprint,
                key_digest=claim[0][0].lower(), head_sequence=outcome.head_sequence, outcome_digest=outcome.outcome_digest))
        if len(legacy) != db.execute('SELECT COUNT(*) FROM subject_operation').fetchone()[0]:
            raise ValueError('source contains unpublished operations; never redeliver')
        control.row_factory = sqlite3.Row
        source_binding = dict(control.execute('SELECT * FROM runtime_authority_binding WHERE binding_id=?', (binding.binding_id,)).fetchone())
        profile = _connect_readonly(studio.profile_database); stack.callback(profile.close)
        qri_json = profile.execute('SELECT qri_json FROM qri_publication WHERE publication_key=?', (record['publication_key'],)).fetchone()[0]
        source_qri = json.loads(qri_json)
        target_contract = contract(record['chat_activation']['contract'], SCOPE, REVIEW)
        body = dict(version=VERSION, request={k: str(v) for k, v in vars(request).items()},
            source_files=source_files, source_hashes=hashes, source_binding=source_binding, source_qri=source_qri,
            source_basis=vars(_read_timeline_basis(db)), legacy_requests=legacy,
            target_activation=dict(contract=target_contract, approval=load_approval(request.approval_path), audit_path=str(request.audit_path.resolve())))
        db.row_factory = sqlite3.Row
        body['source_gate'] = dict(db.execute('SELECT * FROM admission_gate').fetchone())
    if hashes != {name: _hash(path) for name, path in source_files.items()}:
        raise ValueError('source advanced during preparation')
    return body


def read_receipt(db, authority=None):
    from dynamic_subject_agent.timeline import AdmissionFailedClosed
    try:
        return _read_receipt(db, authority)
    except Exception as error:
        raise AdmissionFailedClosed('memorie-continuation-receipt-unverified', 'Continuation read authority is unverified') from error


def _read_receipt(db, authority=None):
    """A bounded old read authority, never permission to admit old speech."""
    if db.execute('PRAGMA user_version').fetchone()[0] != 11:
        return None
    row = db.execute('SELECT receipt_json,receipt_digest FROM memorie_qualification_continuation WHERE singleton=1').fetchone()
    receipt = json.loads(row[0])
    plan = receipt['plan']
    if (canonical_json(receipt) != row[0] or _digest(receipt) != row[1] or receipt['version'] != VERSION
        or receipt['plan_digest'] != _digest(plan) or plan['version'] != VERSION
        or receipt['consent'] != dict(plan_digest=receipt['plan_digest'], data_upgrade_confirmed=True)):
        raise ValueError('continuation receipt differs')
    from dynamic_subject_agent.memorie_native import contract, SCOPE, REVIEW, validate_approval
    from dynamic_subject_agent.memorie_companion_contract import INTENT_VERSION, contract as old_contract
    old, new = plan['source_binding'], receipt['target_binding']
    source_qri = plan['source_qri']
    grant = source_qri['reviewed_chat_contract']
    unsigned = dict(source_qri); unsigned.pop('integrity_digest')
    if (_digest(unsigned) != source_qri['integrity_digest'] or any(source_qri[k] != old[k] for k in (
        'qualification_id','qualification_revision','profile_id','genesis_snapshot_id','knowledge_snapshot_id','provider_authority'))
        or source_qri['integrity_digest'] != old['qri_integrity_digest']):
        raise ValueError('source qualification image differs')
    if grant != old_contract(grant, grant['scope_digest'], grant['review_request_basis'], version=INTENT_VERSION):
        raise ValueError('legacy qualification differs')
    validate_approval(plan['target_activation']['approval'])
    if plan['target_activation']['contract'] != contract(grant, SCOPE, REVIEW):
        raise ValueError('target use differs')
    stable = ('binding_id','authority_scope_id','profile_id','timeline_id','timeline_root_json',
        'timeline_root_id','timeline_control_store_id','timeline_store_id','genesis_snapshot_id','knowledge_snapshot_id',
        'studio_root_id','studio_store_id','host_root_id','host_control_store_id','provider_authority')
    if (any(old[k] != new[k] for k in stable) or new['binding_revision'] != old['binding_revision']+1
        or new['binding_epoch'] != old['binding_epoch']+1 or new['qualification_id'] == old['qualification_id']):
        raise ValueError('continuation identity changed')
    if authority is not None and any(getattr(authority, k) != new[k] for k in (
        'binding_id','binding_revision','binding_epoch','qualification_id','qualification_revision','authority_scope_id','profile_id','timeline_id')):
        raise ValueError('receipt is not current authority')
    legacy = plan['legacy_requests']
    if len(legacy) != plan['source_basis']['head_sequence'] or [r['head_sequence'] for r in legacy] != list(range(1,len(legacy)+1)):
        raise ValueError('incomplete old prefix')
    # Check the entire frozen request set, including original UUID claims.
    rows = db.execute('''SELECT hex(op.operation_id),hex(op.payload_fingerprint),hex(claim.key_digest),outcome.head_sequence,hex(outcome.outcome_digest)
        FROM subject_operation op LEFT JOIN idempotency_claim claim USING(operation_id)
        LEFT JOIN timeline_outcome outcome USING(operation_id) WHERE op.operation_kind='subject' ORDER BY outcome.head_sequence''').fetchall()
    actual = [dict(operation_id=str(UUID(hex=r[0])), fingerprint=r[1].lower(), key_digest=r[2].lower(),
        head_sequence=r[3], outcome_digest=r[4].lower()) for r in rows]
    if actual != legacy or len({r['operation_id'] for r in legacy}) != len(legacy):
        raise ValueError('old request prefix changed')
    if plan['source_basis']['published_outcome_digest'] != (legacy[-1]['outcome_digest'] if legacy else None):
        raise ValueError('old head commitment differs')
    return receipt


def historical_binding(current, *, member=None):
    from dynamic_subject_agent.host import RuntimeHostFailedClosed
    try:
        return _historical_binding(current, member=member)
    except Exception as error:
        raise RuntimeHostFailedClosed('memorie-continuation-lineage-unverified', 'Historical qualification is unverified') from error


def _historical_binding(current, *, member=None):
    """Recover only the one sealed predecessor image for Host lineage checks."""
    from dynamic_subject_agent.host import _connect_readonly, _branch_governance_member_matches
    db = _connect_readonly(current.timeline_root.timeline_database)
    try:
        receipt = read_receipt(db)
    finally:
        db.close()
    if receipt is None:
        return None
    from dataclasses import replace
    before, after = receipt['plan']['source_binding'], receipt['target_binding']
    if all(getattr(current, k) == before[k] for k in ('binding_id','binding_revision','binding_epoch','qualification_id','qri_integrity_digest')):
        return None
    if any(getattr(current, k) != after[k] for k in ('binding_id','binding_revision','binding_epoch','qualification_id','qri_integrity_digest')):
        raise ValueError('current continuation binding differs')
    old = replace(current, **{k: before[k] for k in ('binding_revision','binding_epoch','qualification_id',
        'qualification_revision','qri_publication_key','qri_integrity_digest','runtime_contract_version')},
        policy_decision_ids=tuple(json.loads(before['policy_decision_ids_json'])))
    return old if member is None or _branch_governance_member_matches(member, old) else None


def apply(plan, consent, *, _fault_hook=None):
    if (type(plan) is not MemorieContinuationPlan or plan.status != 'available'
        or type(consent) is not MemorieContinuationConsent or consent.data_upgrade_confirmed is not True
        or consent.plan_digest != plan.plan_digest):
        return MemorieContinuationResult('unavailable', 'exact-data-upgrade-consent-required')
    try:
        body = json.loads(plan.plan_json)
        if canonical_json(body) != plan.plan_json or _digest(body) != plan.plan_digest or body['version'] != VERSION:
            raise ValueError('plan digest differs')
        return _apply(body, plan.plan_digest, consent, _fault_hook or (lambda point: None))
    except Exception as error:
        return MemorieContinuationResult('failed-closed', getattr(error,'code','') or 'memorie-continuation-not-applied-or-needs-recovery', plan.plan_digest)


def _verify_committed(body, digest, record):
    """Reconcile a committed switch, including any later native Publications."""
    from dynamic_subject_agent.host import RuntimeHostRootRef, _connect_readonly, _BINDING_COLUMNS
    from dynamic_subject_agent.studio import StudioRootRef
    from dynamic_subject_agent.timeline import (TimelineEngine, _read_admission_gate, _verify_manifest,
        _verify_store_integrity, _TIMELINE_TABLES, TIMELINE_SCHEMA_FAMILY)
    hostref = RuntimeHostRootRef.from_dict(record['host_location'])
    studio = StudioRootRef.from_dict(record['studio_location'])
    with ExitStack() as stack:
        control = _connect_readonly(hostref.control_database); stack.callback(control.close)
        control.execute('BEGIN')
        host = _readonly_host(hostref, studio, control)
        binding = host._binding_from_row(control.execute(f'SELECT {_BINDING_COLUMNS} FROM runtime_authority_binding WHERE binding_id=?',
            (body['source_binding']['binding_id'],)).fetchone())
        host._require_binding_permit(binding)
        qri = host._qri_for_binding(binding)
        if (qri.predecessor_qualification_id != body['source_binding']['qualification_id']
            or qri.reviewed_chat_contract != body['target_activation']['contract']):
            raise ValueError('committed qualification differs')
        db = _connect_readonly(binding.timeline_root.timeline_database); stack.callback(db.close)
        db.execute('BEGIN')
        _verify_manifest(db, root_id=binding.timeline_root.root_id, store_id=binding.timeline_root.timeline_store_id,
            store_kind='timeline', schema_family=TIMELINE_SCHEMA_FAMILY)
        _verify_store_integrity(db, expected_tables=_TIMELINE_TABLES)
        authority = host._authority_for_binding(binding)
        if _read_admission_gate(db).authority != authority:
            raise ValueError('committed gate differs')
        receipt = read_receipt(db, authority)
        if receipt is None or receipt['plan_digest'] != digest or receipt['plan'] != body:
            raise ValueError('wrong committed receipt')
        engine = TimelineEngine(binding.timeline_root, authority, db, None)
        engine.list_native_interactions()
        return qri


def _apply(body, digest, consent, hit):
    from dynamic_subject_agent.first_life_authorization import registry_lock
    from dynamic_subject_agent.host import (RuntimeHostRootRef, _connect_existing, _claim_process_registry,
        _release_process_registry, _intents_for_contract, _verify_control, _verify_forward_governance_regular_paths)
    from dynamic_subject_agent.studio import StudioRootRef, SubjectStudio, CapabilityManifest
    from dynamic_subject_agent.studio import PolicyKernel
    from dynamic_subject_agent.local_identity_authority import _write_state, _reviewed_chat_ledger
    from dynamic_subject_agent.memorie_native import DDL as NATIVE_DDL, RUNTIME_CONTRACT
    from dynamic_subject_agent.timeline import _TIMELINE_DDL
    request = MemorieContinuationRequest(**{k: Path(v) for k,v in body['request'].items()})
    token = str(uuid4())
    with registry_lock(request.state_path):
        state = json.loads(request.state_path.read_bytes()); record = _record(state)
        hostref = RuntimeHostRootRef.from_dict(record['host_location'])
        studio_ref = StudioRootRef.from_dict(record['studio_location'])
        _verify_forward_governance_regular_paths(tuple(Path(p) for p in body['source_files'].values()))
        if record.get('memorie_continuation') == digest:
            if record['chat_activation'] != body['target_activation'] or record.get('pending_memorie_continuation'):
                raise ValueError('committed registry differs')
            qri = _verify_committed(body, digest, record)
            if qri.publication_key != record['publication_key']:
                raise ValueError('committed registry qualification differs')
            return MemorieContinuationResult('no-op', plan_digest=digest)
        pending = record.get('pending_memorie_continuation')
        if pending is None:
            if _prepare(request) != body:
                raise ValueError('source advanced after consent')
        elif pending != dict(plan_digest=digest, plan=body):
            raise ValueError('another continuation pending')
        _claim_process_registry(hostref.root_id, token)
        try:
            with ExitStack() as stack:
                db = _connect_existing(hostref.control_database); stack.callback(db.close)
                _verify_control(hostref, studio_ref, db)
                # A live lease is rejected even if it belongs to this PID.
                leases = db.execute("SELECT lease_state FROM runtime_instance_lease WHERE lease_state!='closed'").fetchall()
                if leases:
                    raise ValueError('writer must explicitly close before continuation')
                if pending is None:
                    record['pending_memorie_continuation'] = dict(plan_digest=digest, plan=body)
                    _write_state(request.state_path, state)
                hit('after-pending')
                studio = SubjectStudio.open(studio_ref, policy_kernel=PolicyKernel()); stack.callback(studio.close)
                oldq = studio.query_qri(publication_key=body['source_binding']['qri_publication_key'])
                if oldq.integrity_digest != body['source_binding']['qri_integrity_digest']:
                    raise ValueError('source qualification changed')
                target_contract = body['target_activation']['contract']
                key = 'reviewed-character-chat-' + target_contract['definition_basis'] + '-' + target_contract['scope_digest']
                try:
                    successor = studio.query_qri(publication_key=key)
                except Exception as error:
                    if getattr(error,'code',None) != 'qri-not-found': raise
                    snapshot = studio.query_snapshot(oldq.genesis_snapshot_id)
                    policy = studio.decide_policy(snapshot.draft_id, CapabilityManifest.reviewed_character_chat(),
                        validity_us=300_000_000, reviewed_chat_contract=body['target_activation']['contract'])
                    successor = studio.publish(snapshot.snapshot_id, policy_decision_id=policy.decision_id,
                        publication_key=key, predecessor_qualification_id=oldq.qualification_id,
                        reviewed_chat_contract=body['target_activation']['contract'])
                if (successor.predecessor_qualification_id != body['source_binding']['qualification_id']
                    or successor.profile_id != body['source_binding']['profile_id']
                    or successor.genesis_snapshot_id != body['source_binding']['genesis_snapshot_id']
                    or successor.knowledge_snapshot_id != body['source_binding']['knowledge_snapshot_id']
                    or successor.reviewed_chat_contract != target_contract):
                    raise ValueError('exact continuation successor required')
                hit('after-qualification')
                timeline_path = body['source_files']['timeline_database']
                db.execute('ATTACH DATABASE ? AS canonical', (str(Path(timeline_path).as_uri())+'?mode=rw',))
                for schema in ('main','canonical'):
                    if db.execute(f'PRAGMA {schema}.journal_mode').fetchone()[0].lower() != 'delete':
                        raise ValueError('atomic multi-store commit requires DELETE journals')
                    db.execute(f'PRAGMA {schema}.synchronous=EXTRA')
                db.execute('PRAGMA foreign_keys=OFF')
                db.execute('BEGIN EXCLUSIVE')
                try:
                    if db.execute("SELECT 1 FROM runtime_instance_lease WHERE lease_state!='closed'").fetchone():
                        raise ValueError('source writer reappeared')
                    current = db.execute('PRAGMA canonical.user_version').fetchone()[0]
                    if current == 11:
                        raw = db.execute('SELECT receipt_json FROM canonical.memorie_qualification_continuation WHERE singleton=1').fetchone()[0]
                        if json.loads(raw)['plan_digest'] != digest:
                            raise ValueError('wrong committed continuation')
                    elif current == 1:
                        # Holding both write locks fences reopen and final source
                        # verification. No file copying or second runtime exists.
                        db.row_factory = sqlite3.Row
                        old = dict(db.execute('SELECT * FROM runtime_authority_binding WHERE binding_id=?', (body['source_binding']['binding_id'],)).fetchone())
                        gate = dict(db.execute('SELECT * FROM canonical.admission_gate').fetchone())
                        if old != body['source_binding'] or gate != body['source_gate']:
                            raise ValueError('source authority advanced')
                        if any(_hash(body['source_files'][name]) != body['source_hashes'][name] for name in (
                            'host_database','timeline_control_database')):
                            raise ValueError('source stores advanced')
                        if _hash(timeline_path) != body['source_hashes']['timeline_database']:
                            raise ValueError('source canonical advanced')
                        db.row_factory = None
                        new = dict(old, binding_revision=old['binding_revision']+1, binding_epoch=old['binding_epoch']+1,
                            qualification_id=successor.qualification_id, qualification_revision=successor.qualification_revision,
                            qri_publication_key=successor.publication_key, qri_integrity_digest=successor.integrity_digest,
                            policy_decision_ids_json=canonical_json(successor.policy_decision_ids), runtime_contract_version=RUNTIME_CONTRACT)
                        # SQLite's safe table-rebuild order keeps original values
                        # and all foreign-key names intact (no old-table rename).
                        event_ddl = next(s for s in _TIMELINE_DDL if 'CREATE TABLE subject_event (' in s)
                        db.execute(event_ddl.replace('CREATE TABLE subject_event (','CREATE TABLE canonical.subject_event_new (').replace(
                            "CHECK (event_kind = 'command-admitted')", "CHECK (event_kind IN ('command-admitted','system-input-admitted'))"))
                        db.execute('INSERT INTO canonical.subject_event_new SELECT * FROM canonical.subject_event')
                        db.execute('DROP TABLE canonical.subject_event')
                        db.execute('ALTER TABLE canonical.subject_event_new RENAME TO subject_event')
                        db.execute(NATIVE_DDL.replace('CREATE TABLE memorie_native_input', 'CREATE TABLE canonical.memorie_native_input'))
                        db.execute(DDL.replace('CREATE TABLE memorie_qualification_continuation','CREATE TABLE canonical.memorie_qualification_continuation'))
                        receipt = dict(version=VERSION, plan=body, plan_digest=digest, consent=vars(consent), target_binding=new)
                        raw = canonical_json(receipt)
                        db.execute('INSERT INTO canonical.memorie_qualification_continuation VALUES(1,?,?)', (raw,_digest(receipt)))
                        db.execute('UPDATE canonical.store_manifest SET schema_version=11')
                        db.execute('PRAGMA canonical.user_version=11')
                        db.execute('''UPDATE canonical.admission_gate SET allowed_intents_json=?,binding_revision=?,binding_epoch=?,
                            qualification_id=?,qualification_revision=?,gate_epoch=gate_epoch+1 WHERE singleton=1''',
                            (canonical_json(_intents_for_contract(RUNTIME_CONTRACT)), new['binding_revision'], new['binding_epoch'],
                             successor.qualification_id,successor.qualification_revision))
                        changed = [k for k in new if new[k]!=old[k]]
                        db.execute('UPDATE runtime_authority_binding SET '+','.join(k+'=?' for k in changed)+' WHERE binding_id=?',
                            tuple(new[k] for k in changed)+(old['binding_id'],))
                        _append_governance(db, hostref, new)
                        if db.execute('PRAGMA canonical.foreign_key_check').fetchall() or db.execute('PRAGMA main.foreign_key_check').fetchall():
                            raise ValueError('foreign-key validation failed')
                        hit('before-database-commit')
                    else:
                        raise ValueError('unexpected continuation schema')
                    db.execute('COMMIT')
                except BaseException:
                    if db.in_transaction: db.execute('ROLLBACK')
                    raise
                db.execute('PRAGMA foreign_keys=ON')
                hit('after-database-commit')
                # Verify committed authority/old proofs before registry activation.
                _verify_committed(body, digest, record)
                _reviewed_chat_ledger(body['target_activation'], initialize=True)
                record['publication_key'] = successor.publication_key
                record['chat_activation'] = body['target_activation']
                record['memorie_continuation'] = digest
                record.pop('pending_memorie_continuation', None)
                hit('before-registry-commit')
                _write_state(request.state_path, state)
                return MemorieContinuationResult('continued', plan_digest=digest)
        finally:
            _release_process_registry(hostref.root_id, token)


def _append_governance(db, hostref, binding):
    from dynamic_subject_agent.host import _branch_governance_fact_digest
    from time import time_ns
    # Derive case from the source ledger rather than inventing a new branch.
    rows = db.execute('SELECT DISTINCT case_id FROM branch_governance_member JOIN branch_governance_fact USING(fact_id) WHERE profile_id=?',
        (binding['profile_id'],)).fetchall()
    if len(rows)!=1: raise ValueError('one source governance case required')
    case = rows[0][0]
    prior = db.execute('SELECT sequence,fact_digest FROM branch_governance_fact WHERE case_id=? ORDER BY sequence DESC LIMIT 1',(case,)).fetchone()
    keys = ('binding_id','binding_revision','binding_epoch','profile_id','timeline_id','authority_scope_id','qualification_id',
        'qri_integrity_digest','timeline_root_id','timeline_control_store_id','timeline_store_id')
    member = {k: binding[k] for k in keys}; member.update(classification='normal',serving_disposition='eligible')
    digest = _branch_governance_fact_digest(case_id=case,host_root_id=hostref.root_id,
        host_control_store_id=hostref.control_store_id,sequence=prior[0]+1,previous_fact_digest=prior[1],members=[member])
    fact = str(uuid5(NAMESPACE_URL,f'post-m0-05-branch-fact:{case}:{prior[0]+1}:{digest}'))
    db.execute('INSERT INTO branch_governance_fact VALUES(?,?,?,?,?,?,?,?)',
        (fact,case,hostref.root_id,hostref.control_store_id,prior[0]+1,prior[1],digest,time_ns()//1000))
    db.execute('INSERT INTO branch_governance_member VALUES('+','.join('?' for _ in range(14))+')',(fact,*member.values()))
