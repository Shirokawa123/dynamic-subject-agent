from pathlib import Path
from uuid import uuid4
import sqlite3
import pytest
from dynamic_subject_agent.subject_tasks import SubjectTaskCommand
from dynamic_subject_agent.text_artifacts import TextSaveApproval
from dynamic_subject_agent.runtime import RuntimeFaultPoint
from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from test_subject_tasks import opened,task_turn,tasks


def prepared(root):
    app,chat,model=opened(root)
    task_turn(app,SubjectTaskCommand('request','save_text','保存这份陶艺桌文字。',content='Cafe\u0301\r\n陶艺桌欢迎你。'))
    record=tasks(app)[0]
    preview=app.app.application.preview_text_artifact(record.task_id,record.revision)
    assert preview.status=='available',preview
    return app,chat,model,preview.preview


def save(app,preview,key=None):
    result=app.app.application.approve_text_artifact(TextSaveApproval(preview.task_id,preview.revision,preview.basis),
        idempotency_key=key or uuid4().hex)
    assert result.operation_ref,result
    return app.app.application.wait(result.operation_ref,timeout_seconds=15)


def test_exact_preview_has_no_side_effect_then_save_is_local_and_idempotent(tmp_path):
    app,chat,model,p=prepared(tmp_path)
    target=Path(p.directory)/p.filename
    try:
        assert not target.parent.exists()
        key=uuid4().hex
        result=save(app,p,key)
        assert result.status.value=='terminal',result
        assert tasks(app)[0].status=='completed'
        assert result.projection.committed_effect_count==1
        assert target.read_bytes()==p.content.encode('utf-8')
        before=target.stat()
        save(app,p,key);save(app,p)
        assert target.stat().st_ino==before.st_ino and target.stat().st_mtime_ns==before.st_mtime_ns
        assert len(list(target.parent.glob('*.txt')))==1
        assert len(model.requests)==1 and not chat.replies and not chat.proposals
    finally:app.app.close()


def test_stale_cancelled_and_cross_identity_approval_never_save(tmp_path):
    app,_,_,p=prepared(tmp_path/'left');other,_,_=opened(tmp_path/'right')
    try:
        save(other,p)
        assert tasks(other)==()
        r=tasks(app)[0]
        task_turn(app,SubjectTaskCommand('revise','save_text','保存新版。',r.task_id,r.revision,'新正文'))
        save(app,p)
        assert tasks(app)[0].status=='accepted' and not Path(p.directory).exists()
        r=tasks(app)[0];fresh=app.app.application.preview_text_artifact(r.task_id,r.revision).preview
        task_turn(app,SubjectTaskCommand('cancel',task_id=r.task_id,expected_revision=r.revision))
        save(app,fresh)
        assert tasks(app)[0].status=='cancelled' and not Path(p.directory).exists()
    finally:app.app.close();other.app.close()


@pytest.mark.parametrize('point',[RuntimeFaultPoint.BEFORE_PUBLICATION,RuntimeFaultPoint.AFTER_PUBLICATION,RuntimeFaultPoint.AFTER_EFFECT_FILE])
def test_restart_recovers_only_committed_effect_and_queries_do_not_execute(tmp_path,point):
    app,_,_,p=prepared(tmp_path);app.app.close()
    faulty,_,_=opened(tmp_path,saved=app,_runtime_interrupt_at=point)
    save(faulty,p);faulty.app.close()
    restored,chat,model=opened(tmp_path,saved=app)
    target=Path(p.directory)/p.filename
    try:
        current=tasks(restored)[0]
        assert target.exists()==(point==RuntimeFaultPoint.AFTER_EFFECT_FILE)
        assert current.status==('accepted' if point==RuntimeFaultPoint.BEFORE_PUBLICATION else 'executing')
        result=restored.app.application.recover_text_artifacts()
        assert result.status=='available',result
        assert tasks(restored)[0].status==('accepted' if point==RuntimeFaultPoint.BEFORE_PUBLICATION else 'completed')
        assert target.exists()==(point!=RuntimeFaultPoint.BEFORE_PUBLICATION)
        assert model.requests==[] and chat.replies==[]
    finally:restored.app.close()


@pytest.mark.parametrize('collision',['identical-target','partial-stage'])
def test_existing_file_is_never_claimed_or_overwritten(tmp_path,collision):
    app,_,_,p=prepared(tmp_path)
    directory=Path(p.directory);directory.mkdir()
    if collision=='identical-target':
        conflict=directory/p.filename;data=p.content.encode('utf-8')
    else:
        (directory/'.staged').mkdir();conflict=directory/'.staged'/(p.effect_id+'.txt');data=b'partial'
    conflict.write_bytes(data)
    try:
        result=save(app,p)
        assert result.status.value=='terminal',result
        assert tasks(app)[0].status=='failed'
        assert conflict.read_bytes()==data
    finally:app.app.close()


def test_receipt_tail_deletion_is_failed_closed_not_pending(tmp_path):
    app,_,_,p=prepared(tmp_path)
    save(app,p);app.app.close()
    database=next(tmp_path.rglob('timeline.sqlite3'))
    with sqlite3.connect(database) as connection:
        connection.execute('DELETE FROM effect_receipt')
    restored,_,_=opened(tmp_path,saved=app)
    try:
        result=restored.app.application.query(ApplicationQuery(ApplicationQueryKind.SUBJECT_TASKS,restored.qri.profile_id,restored.timeline))
        assert result.status.value=='failed-closed'
        assert restored.app.application.recover_text_artifacts().status=='failed-closed'
    finally:restored.app.close()


def test_next_request_recovers_before_capacity_adjudication(tmp_path):
    app,_,_,p=prepared(tmp_path);app.app.close()
    faulty,_,_=opened(tmp_path,saved=app,_runtime_interrupt_at=RuntimeFaultPoint.AFTER_PUBLICATION)
    save(faulty,p);faulty.app.close()
    restored,_,model=opened(tmp_path,saved=app)
    try:
        task_turn(restored,SubjectTaskCommand('request','draft_text','请写两句展台邀请。'))
        assert [r.status for r in tasks(restored)]==['completed','accepted']
        assert model.requests[0].active_tasks==()
    finally:restored.app.close()


def test_http_preview_never_saves_and_approval_is_identity_bound(tmp_path):
    from types import SimpleNamespace
    from app.desktop.server import AppState
    app,_,_,p=prepared(tmp_path)
    state=AppState(SimpleNamespace(application=app.app.application,profile_id=app.qri.profile_id,timeline_id=app.timeline))
    target=Path(p.directory)/p.filename
    try:
        result=state.text_artifact({'action':'preview','task_id':p.task_id,'revision':p.revision,'expected_profile_id':app.qri.profile_id})
        assert result['ok'] and result['preview']['content']==p.content and not target.exists()
        approval={'action':'approve','task_id':p.task_id,'revision':p.revision,'basis':p.basis,'idempotency_key':uuid4().hex}
        assert not state.text_artifact(dict(approval,expected_profile_id=str(uuid4())))['ok']
        assert not target.exists()
        assert state.text_artifact(dict(approval,expected_profile_id=app.qri.profile_id))['ok']
        assert state.subject_tasks()['tasks'][0]['saved_path']==str(target)
    finally:app.app.close()


def test_legacy_identity_effect_is_explicitly_unavailable(tmp_path):
    from test_recent_dialogue import open_app,DialogueProvider
    app=open_app(tmp_path,DialogueProvider())
    try:
        assert app.app.application.recover_text_artifacts().status=='unavailable'
        assert app.app.application.preview_text_artifact(str(uuid4()),1).status=='unavailable'
    finally:app.app.close()


@pytest.mark.parametrize('completed',[False,True])
def test_export_includes_receipt_chain_without_dispatching_pending_file(tmp_path,completed):
    from dynamic_subject_agent.host import _data_control_timeline_authority
    from dynamic_subject_agent.timeline import _data_control_export_snapshot
    app,_,_,p=prepared(tmp_path)
    if not completed:
        app.app.close();app,_,_=opened(tmp_path,saved=app,_runtime_interrupt_at=RuntimeFaultPoint.AFTER_PUBLICATION)
    save(app,p)
    binding=app.app._host.query_binding(profile_id=app.qri.profile_id,timeline_id=app.timeline)
    app.app.close()
    snapshot=_data_control_export_snapshot(binding.timeline_root,expected_authority=_data_control_timeline_authority(binding))
    exported=snapshot['runtime_timeline']
    assert exported['schema_version']==2
    assert len(exported['effect_receipts'])==int(completed)
    assert exported['effect_receipt_head'][0]==int(completed)
    assert (Path(p.directory)/p.filename).exists()==completed
