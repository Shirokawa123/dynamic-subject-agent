"""Positive continuation through the sole Facade and production composition."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import pytest
from dynamic_subject_agent.application import ApplicationFacade, SubjectRequestLookupRequest
from dynamic_subject_agent.memorie_qualification_continuation import MemorieContinuationRequest, MemorieContinuationConsent
from dynamic_subject_agent.local_product import open_memorie_native_product
from test_memorie_continuation import legacy, send_old, files
from test_memorie_native import native, Transport, command, send, payload


def prepare(config, private, root):
    return ApplicationFacade.prepare_memorie_continuation(MemorieContinuationRequest(config.state_path,
        config.product_parent, private / 'native-approval.json', root / 'continued-audit'))


def consent(plan):
    assert plan.status == 'available', plan
    return MemorieContinuationConsent(plan.plan_digest, True)


def opening(config, private, root, transport):
    return open_memorie_native_product(config, approval_path=private / 'native-approval.json',
        audit_path=root / 'continued-audit', _transport=transport)


def canonical_rows(path):
    with closing(sqlite3.connect(path)) as db, db:
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")
            if r[0] not in ('store_manifest','admission_gate','timeline_head')]
        return {name: set(db.execute('SELECT * FROM ' + name)) for name in tables}


def test_old_text_click_text_restart_same_store_and_exact_old_uuid(legacy):
    old_open, config, private, root = legacy
    old = old_open(); original = send_old(old, '合成旧记录：先认识一种草药。', 'first')
    before_lookup = old.application.lookup_subject_request(SubjectRequestLookupRequest(original, 'continuation-old-first'))
    scope = old.profile_id, old.timeline_id
    old.close()
    before_files = files(root)
    plan = prepare(config, private, root)
    assert files(root) == before_files
    canonical = Path(json.loads(plan.plan_json)['source_files']['timeline_database'])
    original_rows = canonical_rows(canonical)
    result = ApplicationFacade.apply_memorie_continuation(plan, consent(plan))
    assert result.status == 'continued', result
    assert {k:v for k,v in canonical_rows(canonical).items() if k in original_rows} == original_rows
    transport = Transport()
    with opening(config, private, root, transport) as product:
        assert (product.profile_id, product.timeline_id) == scope
        lookup = product.application.lookup_subject_request(SubjectRequestLookupRequest(original, 'continuation-old-first'))
        assert lookup.query_status == 'found', lookup
        assert lookup.operation.operation_ref == before_lookup.operation.operation_ref
        assert not transport.calls
        # Neither re-submitting legacy speech nor reusing its nonce for a click
        # can turn an old request into a fresh delivery.
        refused=product.application.submit(original,idempotency_key='continuation-old-first')
        assert refused.status not in ('terminal','pending') and not transport.calls
        refused=product.application.submit(command(product),idempotency_key='continuation-old-first')
        assert refused.status not in ('terminal','pending') and not transport.calls
        assert send(product, command(product, phase='work'), 'click').status == 'terminal'
        assert payload(transport.calls[0])['exchange'] == [dict(interaction=dict(kind='text',text=original.utterance),assistant_text='合成短回应。')]
        assert send(product, command(product, dict(kind='text',text='刚才只是在计时。'), 'rest'), 'text').status == 'terminal'
        assert len(product.application.query_memorie_interactions().turns) == 3
    after = Transport()
    with opening(config, private, root, after) as reopened:
        assert len(reopened.application.query_memorie_interactions().turns) == 3
        assert reopened.application.lookup_subject_request(SubjectRequestLookupRequest(original,'continuation-old-first')).query_status == 'found'
        assert not after.calls
        reopened.application.set_reviewed_character_history(False)
        assert send(reopened, command(reopened), 'off').status == 'terminal'
        assert payload(after.calls[0])['exchange'] == []
    assert ApplicationFacade.apply_memorie_continuation(plan, consent(plan)).status == 'no-op'
    with opening(config, private, root, Transport()) as final:
        assert len(final.application.query_memorie_interactions().turns) == 4
    assert all(rows <= canonical_rows(canonical)[table] for table,rows in original_rows.items())
    from dynamic_subject_agent.memorie_continuation import MemorieSourceInspectionRequest
    observation = ApplicationFacade.inspect_memorie_continuation_source(MemorieSourceInspectionRequest(config.state_path,config.product_parent))
    assert observation.status == 'no-op' and json.loads(observation.metadata_json)['schema_version'] == 11


@pytest.mark.parametrize('point', ['after-pending','after-qualification','before-database-commit','after-database-commit','before-registry-commit'])
def test_exact_plan_recovers_each_interruption_without_redelivery(legacy, point):
    old_open, config, private, root = legacy
    old = old_open(); original = send_old(old,'合成恢复前原话。', 'first'); old.close()
    plan = prepare(config,private,root)
    def interrupt(actual):
        if actual == point: raise OSError('synthetic interruption')
    result = ApplicationFacade.apply_memorie_continuation(plan, consent(plan), _fault_hook=interrupt)
    assert result.status == 'failed-closed', result
    with pytest.raises(RuntimeError, match='recovery-required'):
        old_open()
    assert ApplicationFacade.apply_memorie_continuation(plan, consent(plan)).status == 'continued'
    transport = Transport()
    with opening(config,private,root,transport) as product:
        assert product.application.lookup_subject_request(SubjectRequestLookupRequest(original,'continuation-old-first')).query_status == 'found'
        assert len(product.application.query_memorie_interactions().turns) == 1
        assert not transport.calls
        assert send(product, command(product), 'after-recovery').status == 'terminal'


def test_requires_closed_source_exact_consent_and_unchanged_basis(legacy):
    old_open,config,private,root = legacy
    old=old_open(); send_old(old,'合成第一句。','first')
    assert prepare(config,private,root).status == 'unavailable'
    old.close(); plan=prepare(config,private,root); consent(plan)
    before=files(root)
    assert ApplicationFacade.apply_memorie_continuation(plan,MemorieContinuationConsent('wrong',True)).status == 'unavailable'
    assert files(root)==before
    changed=old_open(); send_old(changed,'合成新增第二句。','second'); changed.close()
    advanced=files(root)
    assert ApplicationFacade.apply_memorie_continuation(plan,consent(plan)).status=='failed-closed'
    assert files(root)==advanced


def test_unpublished_legacy_attempt_is_preserved_without_upgrade_or_redelivery(legacy):
    from dynamic_subject_agent.timeline import SubjectCommand
    old_open,config,private,root=legacy
    transport=Transport('timeout'); old=old_open(transport)
    value=SubjectCommand.contribute_utterance(target_profile_id=old.profile_id,target_timeline_id=old.timeline_id,
        declared_intent='ask-collaborator-status',utterance='合成未知投递。',language='zh',provenance='project-original')
    response=old.application.submit(value,idempotency_key='continuation-unknown')
    if response.status=='pending': response=old.application.wait(response.operation_ref,timeout_seconds=30)
    assert response.status=='unknown' and len(transport.calls)==1
    old.close(); before=files(root)
    assert prepare(config,private,root).status=='unavailable' and files(root)==before
    after=Transport()
    with old_open(after) as restored:
        assert restored.application.lookup_subject_request(SubjectRequestLookupRequest(value,'continuation-unknown')).query_status=='found'
        assert not after.calls


def test_corrupt_old_publication_is_closed_before_model_even_with_history_off(legacy):
    old_open,config,private,root=legacy
    old=old_open(); send_old(old,'合成不可改写的原话。','first'); old.close()
    plan=prepare(config,private,root)
    assert ApplicationFacade.apply_memorie_continuation(plan,consent(plan)).status=='continued'
    with opening(config,private,root,Transport()) as product:
        product.application.set_reviewed_character_history(False)
    canonical=Path(json.loads(plan.plan_json)['source_files']['timeline_database'])
    with closing(sqlite3.connect(canonical)) as db, db:
        db.execute("UPDATE expression_record SET expression_text='SYNTHETIC_CORRUPTION'")
    transport=Transport()
    with pytest.raises(Exception): opening(config,private,root,transport)
    assert not transport.calls
    assert ApplicationFacade.apply_memorie_continuation(plan,consent(plan)).status=='failed-closed'


@pytest.mark.parametrize('point', ['before-database-commit','after-database-commit'])
def test_process_loss_recovers_atomic_host_timeline_switch(legacy, point):
    old_open,config,private,root=legacy
    old=old_open(); original=send_old(old,'合成硬中断前原话。','first'); old.close()
    plan=prepare(config,private,root); consent(plan)
    plan_file=root/'crash-plan.json'; plan_file.write_text(json.dumps(vars(plan)),encoding='utf-8')
    code='''import json,os,sys
from pathlib import Path
from dynamic_subject_agent.application import ApplicationFacade
from dynamic_subject_agent.memorie_qualification_continuation import MemorieContinuationPlan,MemorieContinuationConsent
plan=MemorieContinuationPlan(**json.loads(Path(sys.argv[1]).read_bytes()))
def hit(point):
    if point==sys.argv[2]: os._exit(23)
result=ApplicationFacade.apply_memorie_continuation(plan,MemorieContinuationConsent(plan.plan_digest,True),_fault_hook=hit)
sys.exit(99)
'''
    process=subprocess.run([sys.executable,'-c',code,str(plan_file),point],capture_output=True,timeout=45)
    assert process.returncode==23, (process.returncode,process.stderr.decode(errors='replace'))
    result=ApplicationFacade.apply_memorie_continuation(plan,consent(plan))
    assert result.status=='continued', result
    transport=Transport()
    with opening(config,private,root,transport) as product:
        assert product.application.lookup_subject_request(SubjectRequestLookupRequest(original,'continuation-old-first')).query_status=='found'
        assert len(product.application.query_memorie_interactions().turns)==1 and not transport.calls


def test_verify_is_read_only_and_absent_legacy_nonce_never_becomes_submission(legacy):
    from dynamic_subject_agent.timeline import SubjectCommand
    old_open,config,private,root=legacy
    old=old_open(); original=send_old(old,'合成已提交的旧原话。','first'); old.close()
    plan=prepare(config,private,root); before=files(root)
    assert ApplicationFacade.verify_memorie_continuation(plan).status=='unavailable'
    assert files(root)==before
    assert ApplicationFacade.apply_memorie_continuation(plan,consent(plan)).status=='continued'
    before=files(root)
    assert ApplicationFacade.verify_memorie_continuation(plan).status=='verified'
    assert files(root)==before
    after=Transport()
    with opening(config,private,root,after) as product:
        absent=SubjectCommand.contribute_utterance(target_profile_id=product.profile_id,target_timeline_id=product.timeline_id,
            declared_intent='ask-collaborator-status',utterance='合成未曾送达的旧原话。',language='zh',provenance='project-original')
        query=product.application.lookup_subject_request(SubjectRequestLookupRequest(absent,'never-submitted-old-nonce'))
        assert query.query_status=='not-found',query
        mismatch=product.application.lookup_subject_request(SubjectRequestLookupRequest(absent,'continuation-old-first'))
        assert mismatch.query_status!='found'
        refused=product.application.submit(absent,idempotency_key='never-submitted-old-nonce')
        assert refused.status not in ('pending','terminal')
        assert len(product.application.query_memorie_interactions().turns)==1 and not after.calls
