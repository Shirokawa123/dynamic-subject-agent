"""Read-only preparation and synthetic legacy-record preservation via Facade."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from dynamic_subject_agent.application import ApplicationFacade, ApplicationQuery, ApplicationQueryKind, SubjectRequestLookupRequest
from dynamic_subject_agent.memorie_continuation import MemorieSourceInspectionRequest
from dynamic_subject_agent.local_product import open_memorie_companion_product, open_memorie_native_product
from dynamic_subject_agent.memorie_companion_contract import INTENT_VERSION, MemorieCallAudit
from dynamic_subject_agent.memorie_companion_preparation import MemoriePreparationView
from dynamic_subject_agent.timeline import SubjectCommand
from test_memorie_native import native, Transport


@pytest.fixture
def legacy(native):
    _, config, private, root = native
    products = []
    def opening(transport=None):
        product = open_memorie_companion_product(config, approval_path=private / 'approval.json',
            audit_path=root / 'legacy-audit', contract_version=INTENT_VERSION, _transport=transport or Transport())
        products.append(product)
        return product
    yield opening, config, private, root
    for p in products: p.close()


def send_old(product, text, key):
    command = SubjectCommand.contribute_utterance(target_profile_id=product.profile_id, target_timeline_id=product.timeline_id,
        declared_intent='ask-collaborator-status', utterance=text, language='zh', provenance='project-original')
    result = product.application.submit(command, idempotency_key='continuation-old-' + key)
    if result.status == 'pending': result = product.application.wait(result.operation_ref, timeout_seconds=30)
    assert result.status == 'terminal', result
    return command


def files(root):
    return {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


def test_inspection_reads_only_metadata_and_opens_no_host_or_studio(legacy, monkeypatch):
    import dynamic_subject_agent.host as host
    from dynamic_subject_agent.studio import SubjectStudio
    opening, config, _, root = legacy
    product = opening(); send_old(product, 'SYNTHETIC_PRIVATE_OLD_TEXT', 'first')
    before = files(root)
    monkeypatch.setattr(host.RuntimeHost, 'open', lambda *a, **k: pytest.fail('inspection opened Host'))
    monkeypatch.setattr(SubjectStudio, 'open', lambda *a, **k: pytest.fail('inspection opened writable Studio'))
    connect = host._connect_readonly
    allowed = {'qri_publication', 'host_manifest', 'runtime_authority_binding', 'runtime_instance_lease',
        'timeline_registration', 'store_manifest', 'admission_gate', 'timeline_head', 'subject_operation',
        'operation_publication_state', 'operation_failure', 'timeline_outcome', 'subject_event'}
    def readonly(path):
        db = connect(path)
        def authorize(action, table, *rest):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_READ and table not in allowed else sqlite3.SQLITE_OK
        db.set_authorizer(authorize)
        return db
    monkeypatch.setattr(host, '_connect_readonly', readonly)
    result = ApplicationFacade.inspect_memorie_continuation_source(MemorieSourceInspectionRequest(config.state_path, config.product_parent))
    assert result.status == 'available', result
    metadata = json.loads(result.metadata_json)
    assert metadata['head_sequence'] == metadata['publication_count'] == 1
    assert metadata['schema_version'] == 1 and metadata['first_subject_event_sealed'] is True
    assert metadata['operation_counts'] == {'completed': 1}
    assert metadata['admission_record_counts'] == {'admitted-pending': 1}
    assert metadata['transcript_read'] is False and 'SYNTHETIC_PRIVATE_OLD_TEXT' not in result.metadata_json
    assert result.apply_supported is False and result.publication_prefix_verified is False
    assert 'nonempty-timeline-binding-sealed' in metadata['blockers']
    assert files(root) == before


def test_missing_and_wrong_writer_never_create_or_report_a_ready_migration(legacy, tmp_path):
    opening, config, _, _ = legacy
    opening()
    missing = MemorieSourceInspectionRequest(tmp_path / 'absent/state.json', config.product_parent)
    assert ApplicationFacade.inspect_memorie_continuation_source(missing).status == 'unavailable'
    assert not missing.state_path.parent.exists()
    wrong = MemorieSourceInspectionRequest(config.state_path, config.product_parent, expected_owner_pid=1)
    result = ApplicationFacade.inspect_memorie_continuation_source(wrong)
    assert result.status == 'unavailable' and result.metadata_json == ''


def test_native_source_is_a_noop_without_any_requalification(native):
    opening, config, _, root = native
    opening()
    before = files(root)
    result = ApplicationFacade.inspect_memorie_continuation_source(MemorieSourceInspectionRequest(config.state_path, config.product_parent))
    assert result.status == 'no-op', result
    assert json.loads(result.metadata_json)['schema_version'] == 10
    assert not result.apply_supported and files(root) == before


def test_a_lagging_seal_flag_does_not_make_nonempty_history_eligible(legacy):
    opening, config, _, root = legacy
    product = opening(); send_old(product, '合成已有事件。', 'sealed')
    product.close()
    state = json.loads(config.state_path.read_bytes())
    record = next(r for r in state['identities'] if r['identity_id'] == state['active_identity_id'])
    path = Path(record['host_location']['root_path']) / 'control/host.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute("UPDATE runtime_authority_binding SET first_subject_event_sealed=0 WHERE state='active' AND profile_id=?",
            (record['identity_id'],))
    before = files(root)
    result = ApplicationFacade.inspect_memorie_continuation_source(MemorieSourceInspectionRequest(config.state_path, config.product_parent))
    assert result.status == 'available', result
    metadata = json.loads(result.metadata_json)
    assert metadata['first_subject_event_sealed'] is False and metadata['subject_event_count'] == 1
    assert 'nonempty-timeline-binding-sealed' in metadata['blockers'] and result.apply_supported is False
    assert files(root) == before


def test_legacy_history_can_be_typed_for_preview_but_failed_upgrade_preserves_records_and_requests(legacy):
    opening, config, private, root = legacy
    transport = Transport(); product = opening(transport)
    original = send_old(product, '合成旧记录：先研究一种草药。', 'one')
    send_old(product, '合成旧记录：我只是提出设想，还没开始。', 'two')
    scope = product.profile_id, product.timeline_id
    history = product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY, *scope))
    assert history.status == 'available' and len(history.projection.turns) == 2
    prepared = MemoriePreparationView(**json.loads((private / 'preparation.json').read_bytes()))
    typed = tuple(dict(interaction=dict(kind='text', text=t.user_text), assistant_text=t.assistant_text) for t in history.projection.turns)
    wire = ApplicationFacade.preview_memorie_native_message(prepared, {'kind': 'character-click'}, {'timer_phase': 'work'}, typed)
    payload = json.loads(json.loads(wire)['messages'][1]['content'])
    assert payload['exchange'] == list(typed) and payload['interaction'] == {'kind': 'character-click'}
    # A preview is not permission to rebind or to inject this history into a
    # different development identity's runtime.
    product.close()
    before = files(root)
    after = Transport()
    with pytest.raises(RuntimeError, match='activation-conflict'):
        open_memorie_native_product(config, approval_path=private / 'native-approval.json',
            audit_path=root / 'new-native-audit', _transport=after)
    assert files(root) == before and not after.calls
    restored = opening(after)
    assert (restored.profile_id, restored.timeline_id) == scope
    lookup = restored.application.lookup_subject_request(SubjectRequestLookupRequest(original, 'continuation-old-one'))
    assert lookup.query_status == 'found' and lookup.operation.status == 'terminal'
    restored_history = restored.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY, *scope))
    assert restored_history.projection.turns == history.projection.turns and not after.calls
    assert MemorieCallAudit(root / 'legacy-audit').counts() == (None, 2, None)
