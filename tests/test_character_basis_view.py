from dataclasses import asdict
from threading import Event
from time import monotonic
import json
import sqlite3

import pytest

from test_original_whole_chat import whole_fixture, approved, personality_fixture, model_fixture, WholeTransport, send, history


def test_facade_basis_matches_sealed_semantic_layers_and_excludes_internal_source_data(whole_fixture):
    opening,_,config,_=whole_fixture
    product=opening(); product.close()
    from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
    loaded=LocalIdentityAuthority(config).load_active()
    asset=loaded.reviewed_definition['runtime_asset']
    transport=WholeTransport(); product=opening(transport)
    view=product.application.query_character_basis()
    assert view.status=='available'
    assert len(view.knowledge)==len(asset['eligible']) and len(view.personality)==len(asset['personality'])
    for actual,source in zip(view.knowledge,asset['eligible'],strict=True):
        assert asdict(actual)==dict(dimension=source['dimension'],statement=source['statement'],kind=source['kind'],
            basis=source['derivation'],event_scope=source['event_time'],knowledge_scope=source['knowledge_time'])
    assert {row.kind for row in view.knowledge}=={'fact','belief'}
    assert view.core and view.episodes and view.details
    assert all(row.basis=='author-interpretation' for row in view.personality)
    rendered=json.dumps(asdict(view),ensure_ascii=False)
    for excluded in ('item_id','unit_id','claim_ids','cues','definition_basis','runtime_asset_sha','persona_digest','evidence_ids','source_text','sample.epub'):
        assert excluded not in rendered
    assert '逐段定位' in view.trace_note and '尚未接入' in view.trace_note
    assert not transport.calls and history(product)==()
    before=config.state_path.read_bytes()
    assert send(product,'这是不会加入人物依据的合成聊天。','basis-chat').status=='terminal'
    assert product.application.query_character_basis()==view
    assert config.state_path.read_bytes()==before
    saved=history(product); product.close()
    transport2=WholeTransport(); reopened=opening(transport2)
    assert reopened.application.query_character_basis()==view and history(reopened)==saved and not transport2.calls
    reopened.close()
    unavailable=reopened.application.query_character_basis()
    assert unavailable.status=='unavailable' and unavailable.knowledge==() and unavailable.personality==()


def test_basis_remains_readable_during_model_without_worker_or_registry_lock(whole_fixture):
    opening,_,_,_=whole_fixture
    entered,release=Event(),Event()
    def blocking(): entered.set(); assert release.wait(10)
    transport=WholeTransport(callback=blocking); product=opening(transport)
    from dynamic_subject_agent.timeline import SubjectCommand
    command=SubjectCommand.contribute_utterance(target_profile_id=product.profile_id,target_timeline_id=product.timeline_id,
        declared_intent='ask-collaborator-status',utterance='合成在途消息。',language='zh',provenance='project-original')
    pending=product.application.submit(command,idempotency_key='character-basis-inflight-owned')
    assert entered.wait(5)
    try:
        start=monotonic(); view=product.application.query_character_basis()
        assert monotonic()-start<3 and view.status=='available'
        assert len(transport.calls)==1
    finally: release.set()
    assert product.application.wait(pending.operation_ref,timeout_seconds=30).status=='terminal'


def test_basis_identity_changed_or_corrupted_never_returns_previous_cache(whole_fixture):
    opening,_,config,_=whole_fixture
    product=opening(); product.close()
    from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
    loaded=LocalIdentityAuthority(config).load_active()
    product=opening()
    previous=product.application.query_character_basis()
    assert previous.status=='available'
    state=json.loads(config.state_path.read_text(encoding='utf-8'))
    original=state['active_identity_id']
    state['active_identity_id']=next(row['identity_id'] for row in state['identities'] if row['identity_id']!=original)
    config.state_path.write_text(json.dumps(state),encoding='utf-8')
    unavailable=product.application.query_character_basis()
    assert unavailable.status=='unavailable' and unavailable.knowledge==() and unavailable.personality==()
    state['active_identity_id']=original
    config.state_path.write_text(json.dumps(state),encoding='utf-8')
    db=sqlite3.connect(loaded.studio_location.profile_database,autocommit=True)
    try:
        raw=json.loads(db.execute('SELECT snapshot_json FROM genesis_snapshot WHERE snapshot_id=?',(loaded.qri.genesis_snapshot_id,)).fetchone()[0])
        raw['reviewed_definition']['runtime_asset']['eligible'][0]['statement']='TAMPERED_SYNTHETIC_BASIS'
        db.execute('UPDATE genesis_snapshot SET snapshot_json=? WHERE snapshot_id=?',(json.dumps(raw),loaded.qri.genesis_snapshot_id))
    finally: db.close()
    corrupt=product.application.query_character_basis()
    assert corrupt.status=='failed-closed' and corrupt.knowledge==() and corrupt.personality==()
