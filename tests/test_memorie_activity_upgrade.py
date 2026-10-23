"""Same-store continuation through the Facade, using synthetic transport only."""
from contextlib import closing
from pathlib import Path
from dataclasses import replace
import json
import os
import sqlite3
import subprocess
import sys

import pytest

from dynamic_subject_agent.application import ApplicationFacade,SubjectRequestLookupRequest
from dynamic_subject_agent.memorie_activity_upgrade import NativeActivityUpgradeRequest,NativeActivityUpgradeConsent
from dynamic_subject_agent.memorie_qualification_continuation import MemorieContinuationConsent
from dynamic_subject_agent.local_product import open_continued_memorie_activity_product
from dynamic_subject_agent.shared_activity import SharedExperienceRequest
from test_memorie_activity_preparation import continued,prepared,native,legacy
from test_memorie_continuation import files
from test_memorie_activity_live import Transport,state,control,act
from test_memorie_native_activity import send_native


@pytest.fixture
def upgrade(continued,tmp_path,monkeypatch):
    p,_,config,root,source,old=continued
    grant=Path(os.environ['MEMORIE_NATIVE_QUALIFICATION'])/'native-activity-approval.json'
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'account-control'))
    from dynamic_subject_agent.host import RuntimeHost
    original=RuntimeHost.apply_living_activity
    def diagnosed(host,*args,**kwargs):
        try:return original(host,*args,**kwargs)
        except Exception:
            import traceback
            traceback.print_exc()
            raise
    monkeypatch.setattr(RuntimeHost,'apply_living_activity',diagnosed)
    request=NativeActivityUpgradeRequest(source.predecessor,grant)
    yield p,config,root,request,old
    p.close()


def test_same_identity_old_prefix_new_activity_and_original_requests_reopen(upgrade):
    p,config,root,request,old=upgrade
    scope=p.profile_id,p.timeline_id;old_turns=p.application.query_memorie_interactions();p.close()
    before=files(root);plan=ApplicationFacade.prepare_memorie_activity_upgrade(request)
    assert plan.status=='available',plan
    assert files(root)==before
    body=json.loads(plan.plan_json);timeline=Path(body['source_files']['timeline_database'])
    with closing(sqlite3.connect(timeline)) as db:
        originals={t:list(db.execute('SELECT * FROM '+t)) for t in ('memorie_qualification_continuation','subject_operation','idempotency_claim','timeline_outcome','memorie_native_input')}
    assert ApplicationFacade.apply_memorie_activity_upgrade(plan,MemorieContinuationConsent(plan.plan_digest,True)).status=='unavailable'
    result=ApplicationFacade.apply_memorie_activity_upgrade(plan,NativeActivityUpgradeConsent(plan.plan_digest,True))
    assert result.status=='continued',result
    assert ApplicationFacade.verify_memorie_activity_upgrade(plan).status=='verified'
    with closing(sqlite3.connect(timeline)) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==12
        assert db.execute('SELECT COUNT(*) FROM shared_activity_record').fetchone()[0]==0
        assert originals=={t:list(db.execute('SELECT * FROM '+t)) for t in originals}
    model=Transport()
    with open_continued_memorie_activity_product(config,plan=plan,approval_path=request.approval_path,_transport=model) as active:
        assert (active.profile_id,active.timeline_id)==scope and active.application.query_memorie_interactions()==old_turns and not model.calls
        initial=state(active);assert initial['revision']==0 and initial['permission']['paused'] and not initial['permission']['sharing_enabled']
        original=active.application.lookup_subject_request(SubjectRequestLookupRequest(old,'continuation-old-activity-source-1'))
        assert original.query_status=='found' and original.operation.status=='terminal',original
        assert active.application.set_shared_experience(SharedExperienceRequest(*scope,'m027-source-select-1',0,1,'按问题分栏',True)).status=='committed'
        assert control(active).status=='committed'
        formed=act(active,'m027-outline-original-1');assert formed.status=='committed',formed
        assert act(active,'m027-share-original-1','share').status=='committed'
        send_native(active,'m027-native-reply-1')
        payload=json.loads(model.calls[-1]['messages'][1]['content'])
        assert payload['experience']['quote']=='按问题分栏' and payload['latest_share'] is not None
        assert len(model.calls)==3
    fresh=Transport()
    with open_continued_memorie_activity_product(config,plan=plan,approval_path=request.approval_path,_transport=fresh) as reopened:
        assert len(reopened.application.query_memorie_interactions().turns)==4 and not fresh.calls
        v=state(reopened)
        assert reopened.application.set_shared_experience(SharedExperienceRequest(*scope,'m027-disable-source-1',v['revision'],None,'',True)).status=='committed'
        send_native(reopened,'m027-after-disable-1')
        payload=json.loads(fresh.calls[-1]['messages'][1]['content'])
        assert payload['experience'] is None and payload['latest_share'] is None and payload['activity_result'] is None
    assert ApplicationFacade.verify_memorie_activity_upgrade(plan).status=='verified'
    assert ApplicationFacade.apply_memorie_activity_upgrade(plan,NativeActivityUpgradeConsent(plan.plan_digest,True)).status=='no-op'


def test_live_source_and_unapproved_or_changed_plan_never_upgrade(upgrade):
    p,config,root,request,_=upgrade
    before=files(root)
    assert ApplicationFacade.prepare_memorie_activity_upgrade(request).status=='unavailable'
    assert files(root)==before
    p.close();plan=ApplicationFacade.prepare_memorie_activity_upgrade(request);assert plan.status=='available',plan
    before=files(root)
    assert ApplicationFacade.apply_memorie_activity_upgrade(plan,NativeActivityUpgradeConsent('0'*64,True)).status=='unavailable'
    changed=replace(plan,plan_json=plan.plan_json+' ')
    assert ApplicationFacade.apply_memorie_activity_upgrade(changed,NativeActivityUpgradeConsent(plan.plan_digest,True)).status=='failed-closed'
    with pytest.raises(ValueError):open_continued_memorie_activity_product(config,plan=plan,approval_path=request.approval_path,_transport=Transport())
    assert files(root)==before


@pytest.mark.parametrize('point',['after-pending','after-qualification','before-database-commit','after-database-commit','before-registry-commit'])
def test_activity_continuation_recovers_same_plan_without_redelivery(upgrade,point):
    p,config,root,request,_=upgrade;p.close()
    plan=ApplicationFacade.prepare_memorie_activity_upgrade(request);assert plan.status=='available',plan
    consent=NativeActivityUpgradeConsent(plan.plan_digest,True)
    def hit(actual):
        if actual==point:raise RuntimeError('synthetic interruption')
    assert ApplicationFacade.apply_memorie_activity_upgrade(plan,consent,_fault_hook=hit).status=='failed-closed'
    from dynamic_subject_agent.local_product import open_local_product
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    with pytest.raises(RuntimeError,match='recovery-required'):open_local_product(config,cognition=DormantDeepSeekCognition())
    result=ApplicationFacade.apply_memorie_activity_upgrade(plan,consent);assert result.status=='continued',result
    before=files(root);assert ApplicationFacade.verify_memorie_activity_upgrade(plan).status=='verified';assert files(root)==before
    transport=Transport()
    with open_continued_memorie_activity_product(config,plan=plan,approval_path=request.approval_path,_transport=transport) as current:
        assert len(current.application.query_memorie_interactions().turns)==3 and not transport.calls
        assert state(current)['permission']['paused']


@pytest.mark.parametrize('point',['before-database-commit','after-database-commit'])
def test_activity_upgrade_process_loss_keeps_single_store_and_old_uuid(upgrade,point):
    p,config,root,request,old=upgrade;p.close()
    plan=ApplicationFacade.prepare_memorie_activity_upgrade(request);assert plan.status=='available'
    path=root/'activity-crash-plan.json';path.write_text(json.dumps(vars(plan)),encoding='utf-8')
    code='''import json,os,sys
from pathlib import Path
from dynamic_subject_agent.application import ApplicationFacade
from dynamic_subject_agent.memorie_activity_upgrade import NativeActivityUpgradePlan,NativeActivityUpgradeConsent
plan=NativeActivityUpgradePlan(**json.loads(Path(sys.argv[1]).read_bytes()))
def hit(point):
    if point==sys.argv[2]:os._exit(23)
ApplicationFacade.apply_memorie_activity_upgrade(plan,NativeActivityUpgradeConsent(plan.plan_digest,True),_fault_hook=hit)
sys.exit(99)
'''
    child=subprocess.run([sys.executable,'-c',code,str(path),point],capture_output=True,timeout=60)
    assert child.returncode==23,(child.returncode,child.stderr.decode(errors='replace'))
    result=ApplicationFacade.apply_memorie_activity_upgrade(plan,NativeActivityUpgradeConsent(plan.plan_digest,True))
    assert result.status=='continued',result
    transport=Transport()
    with open_continued_memorie_activity_product(config,plan=plan,approval_path=request.approval_path,_transport=transport) as current:
        assert current.application.lookup_subject_request(SubjectRequestLookupRequest(old,'continuation-old-activity-source-1')).query_status=='found'
        assert len(current.application.query_memorie_interactions().turns)==3 and not transport.calls


def test_disabled_history_survives_upgrade_and_old_corruption_is_closed(upgrade):
    p,config,root,request,_=upgrade
    assert p.application.set_reviewed_character_history(False).history_enabled is False;p.close()
    plan=ApplicationFacade.prepare_memorie_activity_upgrade(request);assert plan.status=='available'
    assert ApplicationFacade.apply_memorie_activity_upgrade(plan,NativeActivityUpgradeConsent(plan.plan_digest,True)).status=='continued'
    model=Transport()
    with open_continued_memorie_activity_product(config,plan=plan,approval_path=request.approval_path,_transport=model) as current:
        send_native(current,'m027-history-disabled-click')
        assert json.loads(model.calls[-1]['messages'][1]['content'])['exchange']==[]
    before=files(root);assert ApplicationFacade.verify_memorie_activity_upgrade(plan).status=='verified';assert files(root)==before
    path=Path(json.loads(plan.plan_json)['source_files']['timeline_database'])
    with closing(sqlite3.connect(path)) as db:
        db.execute("UPDATE expression_record SET expression_text='SYNTHETIC_CORRUPTION' WHERE plan_id=(SELECT plan_id FROM timeline_outcome WHERE head_sequence=1)");db.commit()
    fresh=Transport()
    assert ApplicationFacade.verify_memorie_activity_upgrade(plan).status=='failed-closed'
    with pytest.raises(ValueError):open_continued_memorie_activity_product(config,plan=plan,approval_path=request.approval_path,_transport=fresh)
    assert not fresh.calls


def test_qualification_read_rechecks_snapshots_on_every_call(upgrade):
    p,config,root,request,_=upgrade;p.close()
    plan=ApplicationFacade.prepare_memorie_activity_upgrade(request);assert plan.status=='available'
    assert ApplicationFacade.apply_memorie_activity_upgrade(plan,NativeActivityUpgradeConsent(plan.plan_digest,True)).status=='continued'
    from dynamic_subject_agent.studio import SubjectStudio,StudioRootRef,PolicyKernel
    body=json.loads(plan.plan_json);registry=json.loads(config.state_path.read_bytes())
    record=next(r for r in registry['identities'] if r['identity_id']==registry['active_identity_id'])
    studio=SubjectStudio.open(StudioRootRef.from_dict(record['studio_location']),policy_kernel=PolicyKernel())
    try:
        qri=studio.query_qri(publication_key=record['publication_key'])
        with closing(sqlite3.connect(body['source_files']['studio_database'])) as db:
            db.execute('UPDATE genesis_snapshot SET snapshot_digest=? WHERE snapshot_id=?',('0'*64,qri.genesis_snapshot_id));db.commit()
        with pytest.raises(Exception):studio.query_qri(publication_key=record['publication_key'])
    finally:studio.close()
    assert ApplicationFacade.verify_memorie_activity_upgrade(plan).status=='failed-closed'
