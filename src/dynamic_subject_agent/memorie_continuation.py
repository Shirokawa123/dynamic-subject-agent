"""Read-only source metadata for preparing a Memorie continuation.

No Host/Studio is opened, no transcript is selected, and no migration is
authorized. An observation binds metadata at one read, not a verified old
Publication prefix or permission to install a successor.
"""
from contextlib import ExitStack
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from dynamic_subject_agent.frozen_attempt import canonical_json


@dataclass(frozen=True)
class MemorieSourceInspectionRequest:
    state_path: Path
    product_parent: Path
    expected_owner_pid: int | None = None


@dataclass(frozen=True)
class MemorieSourceInspection:
    status: str
    problem_code: str = ''
    metadata_json: str = ''
    metadata_digest: str = ''
    publication_prefix_verified: bool = False
    apply_supported: bool = False


class _Unavailable(Exception):
    pass


def _bounded_file(path, maximum):
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('inspection source oversized')
    return raw


def _inside(path, parent):
    if not path.is_absolute() or not path.resolve().is_relative_to(parent.resolve()):
        raise ValueError('inspection path outside selected product')


def inspect_memorie_source(request):
    if type(request) is not MemorieSourceInspectionRequest:
        return MemorieSourceInspection('unavailable', 'typed-memorie-source-inspection-required')
    if (not all(isinstance(p, Path) and p.is_absolute() for p in (request.state_path, request.product_parent))
        or request.expected_owner_pid is not None and (type(request.expected_owner_pid) is not int or request.expected_owner_pid <= 0)):
        return MemorieSourceInspection('unavailable', 'memorie-source-inspection-invalid')
    try:
        return _inspect(request)
    except (FileNotFoundError, _Unavailable):
        return MemorieSourceInspection('unavailable', 'memorie-source-not-ready-or-changed')
    except sqlite3.OperationalError as error:
        transient = getattr(error, 'sqlite_errorcode', None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
        return MemorieSourceInspection('unavailable' if transient else 'failed-closed', 'memorie-source-read-unavailable')
    except Exception:
        return MemorieSourceInspection('failed-closed', 'memorie-source-metadata-unverified')


def _inspect(request):
    # Use the existing file/root checks and the existing read-only connection
    # profile, without constructing a RuntimeHost or writable Studio.
    from dynamic_subject_agent.host import RuntimeHostRootRef, _connect_readonly, _verify_forward_governance_regular_paths
    from dynamic_subject_agent.studio import StudioRootRef
    from dynamic_subject_agent.timeline import CanonicalRootRef
    from dynamic_subject_agent.memorie_companion_contract import contract, DEFINITION, NATIVE_VERSION, validate_approval
    from dynamic_subject_agent.memorie_native import validate_approval as native_approval

    state_path, parent = request.state_path, request.product_parent
    _inside(state_path, parent.parents[2])
    if not state_path.is_file():
        raise _Unavailable()
    _verify_forward_governance_regular_paths((state_path,))
    before = _bounded_file(state_path, 2_000_000)
    state = json.loads(before)
    if state['schema_version'] != 2:
        raise ValueError('source inspection requires explicit registry schema2')
    records = [r for r in state['identities'] if r['identity_id'] == state['active_identity_id']]
    if len(records) != 1:
        raise ValueError('exact active identity missing')
    record = records[0]
    activation = record.get('chat_activation')
    if activation is None or record.get('pending_chat_activation') is not None:
        raise _Unavailable()
    grant = activation['contract']
    if grant['definition_basis'] != DEFINITION or grant != contract(grant, grant['scope_digest'],
        grant['review_request_basis'], version=grant['version']):
        raise ValueError('exact approved Memorie source required')
    native = grant['version'] == NATIVE_VERSION
    (native_approval if native else validate_approval)(activation['approval'])
    host = RuntimeHostRootRef.from_dict(record['host_location'])
    studio = StudioRootRef.from_dict(record['studio_location'])
    for path in (Path(record['experiment_base']), host.root, studio.root):
        _inside(path, parent)
    _verify_forward_governance_regular_paths((host.control_database, studio.profile_database))

    with ExitStack() as stack:
        def read(path):
            _inside(path, parent)
            _verify_forward_governance_regular_paths((path,))
            db = _connect_readonly(path)
            stack.callback(db.close)
            # DELETE mode is the engine's actual canonical profile. Do not
            # use immutable/nolock or create WAL/SHM files for this inspection.
            if db.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete':
                raise _Unavailable()
            db.execute('BEGIN')
            return db

        profile = read(studio.profile_database)
        publication = profile.execute('SELECT qualification_id,qri_json,integrity_digest FROM qri_publication WHERE publication_key=?',
            (record['publication_key'],)).fetchone()
        if publication is None:
            raise ValueError('published source qualification missing')
        qri = json.loads(publication[1])
        unsigned = dict(qri); unsigned.pop('integrity_digest')
        if (sha256(canonical_json(unsigned).encode()).hexdigest() != publication[2]
            or qri['integrity_digest'] != publication[2] or qri['qualification_id'] != publication[0]
            or qri['profile_id'] != record['identity_id'] or qri['reviewed_chat_contract'] != grant):
            raise ValueError('source qualification metadata differs')
        control = read(host.control_database)
        control.row_factory = sqlite3.Row
        manifest = control.execute('SELECT root_id,control_store_id,studio_root_id,studio_store_id FROM host_manifest WHERE singleton=1').fetchone()
        if tuple(manifest) != (host.root_id, host.control_store_id, studio.root_id, studio.profile_store_id):
            raise ValueError('source Host manifest differs')
        bindings = control.execute("SELECT * FROM runtime_authority_binding WHERE profile_id=? AND timeline_id=? AND state='active'",
            (record['identity_id'], record['timeline_id'])).fetchall()
        if len(bindings) != 1:
            raise ValueError('source binding is not unique')
        binding = dict(bindings[0])
        if (binding['qri_publication_key'] != record['publication_key'] or binding['qualification_id'] != publication[0]
            or binding['qri_integrity_digest'] != publication[2]):
            raise ValueError('source binding qualification differs')
        leases = control.execute("SELECT owner_pid,generation,lease_state FROM runtime_instance_lease WHERE binding_id=? AND lease_state IN ('active','draining')",
            (binding['binding_id'],)).fetchall()
        if len(leases) > 1:
            raise ValueError('more than one recorded writer')
        if request.expected_owner_pid is not None and (len(leases) != 1 or leases[0]['owner_pid'] != request.expected_owner_pid):
            raise _Unavailable()
        timeline = CanonicalRootRef.from_dict(json.loads(binding['timeline_root_json']))
        _inside(timeline.root, host.root)
        if (timeline.root_id != binding['timeline_root_id'] or timeline.control_store_id != binding['timeline_control_store_id']
            or timeline.timeline_store_id != binding['timeline_store_id'] or timeline.timeline_id != record['timeline_id']):
            raise ValueError('source Timeline reference differs')
        registration = read(timeline.control_database)
        row = registration.execute('SELECT timeline_store_id,relative_database_path,registration_state FROM timeline_registration WHERE timeline_id=?',
            (timeline.timeline_id,)).fetchone()
        if row != (timeline.timeline_store_id, f'timelines/{timeline.timeline_id}/timeline.sqlite3', 'ready'):
            raise ValueError('source Timeline registration differs')
        db = read(timeline.timeline_database)
        db.row_factory = sqlite3.Row
        schema = db.execute('PRAGMA user_version').fetchone()[0]
        manifest = db.execute('SELECT root_id,store_id,schema_version FROM store_manifest WHERE singleton=1').fetchone()
        if tuple(manifest) != (timeline.root_id, timeline.timeline_store_id, schema) or schema not in ((10,11) if native else (1,)):
            raise ValueError('source schema differs from qualification')
        gate = dict(db.execute('SELECT * FROM admission_gate WHERE singleton=1').fetchone())
        for key in ('binding_id','binding_revision','binding_epoch','authority_scope_id','profile_id','timeline_id','qualification_id','qualification_revision','provider_authority'):
            if gate[key] != binding[key]:
                raise ValueError('source gate differs from binding')
        head = db.execute('SELECT head_sequence,hex(published_outcome_digest) FROM timeline_head WHERE singleton=1').fetchone()
        admissions = dict(db.execute('SELECT operation_state,COUNT(*) FROM subject_operation GROUP BY operation_state').fetchall())
        # Admission rows are immutable and remain admitted-pending after a
        # successful Publication. Follow the existing query() terminal sources.
        operations = dict(db.execute('''SELECT CASE
            WHEN publication.operation_id IS NOT NULL AND failure.operation_id IS NOT NULL THEN 'conflict'
            WHEN publication.operation_id IS NOT NULL THEN publication.operation_state
            WHEN failure.operation_id IS NOT NULL THEN 'failed-closed'
            ELSE 'admitted-pending' END AS state, COUNT(*)
            FROM subject_operation operation
            LEFT JOIN operation_publication_state publication USING(operation_id)
            LEFT JOIN operation_failure failure USING(operation_id)
            GROUP BY state''').fetchall())
        if 'conflict' in operations:
            raise ValueError('source has conflicting terminal metadata')
        count, first, last = db.execute('SELECT COUNT(*),MIN(head_sequence),MAX(head_sequence) FROM timeline_outcome').fetchone()
        if count != head[0] or count and (first != 1 or last != count):
            raise ValueError('source head count differs')
        events = db.execute('SELECT COUNT(*) FROM subject_event').fetchone()[0]
        metadata = dict(version='memorie-source-observation-m002-2', identity_id=record['identity_id'],
            timeline_id=record['timeline_id'], scope_key=sha256((record['identity_id'] + ':' + record['timeline_id']).encode()).hexdigest(),
            contract_version=grant['version'], binding_id=binding['binding_id'], authority_scope_id=binding['authority_scope_id'],
            qualification_id=publication[0], qri_integrity_digest=publication[2],
            source_files=dict(registry=str(state_path), studio_database=str(studio.profile_database),
                host_database=str(host.control_database), timeline_control_database=str(timeline.control_database),
                timeline_database=str(timeline.timeline_database)),
            timeline_path=str(timeline.timeline_database), schema_version=schema, head_sequence=head[0],
            published_outcome_digest=str(head[1]).lower(), publication_count=count, subject_event_count=events,
            first_subject_event_sealed=bool(binding['first_subject_event_sealed']), gate_state=gate['gate_state'],
            operation_counts=operations, admission_record_counts=admissions,
            operation_counts_basis='publication-or-failure-else-admission',
            writer_leases=[dict(r) for r in leases], history_enabled=record['history_enabled'],
            history_revision=record.get('history_revision'), identity_revision=state.get('chat_identity_revision'),
            registry_sha256=sha256(before).hexdigest(), transcript_read=False,
            qualification_metadata_checked=True, publication_prefix_verified=False,
            blockers=[] if native else ['existing-chat-activation-conflict', 'legacy-native-schema-and-input-gap']
                + (['nonempty-timeline-binding-sealed'] if events or binding['first_subject_event_sealed'] else []),
            apply_supported=False)
    if state_path.read_bytes() != before:
        raise _Unavailable()
    raw = canonical_json(metadata)
    return MemorieSourceInspection('no-op' if native else 'available', metadata_json=raw,
        metadata_digest=sha256(raw.encode()).hexdigest())
