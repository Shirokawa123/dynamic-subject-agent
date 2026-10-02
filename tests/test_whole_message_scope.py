from threading import Event
import json
import sqlite3

import pytest

from dynamic_subject_agent.whole_message_scope import WholeMessageScopePreviewRequest
from test_whole_context_boundary import context_fixture,request_for
from test_original_whole_chat import whole_fixture,approved,personality_fixture,model_fixture,WholeTransport,send,history


def preview(product,text):
    return product.application.preview_whole_message_scope(WholeMessageScopePreviewRequest(product.profile_id,product.timeline_id,text))


def test_preview_exact_formal_projection_without_admission_or_model_and_boundary_range(context_fixture):
    opening,config,_=context_fixture
    transport=WholeTransport(); product=opening(transport)
    assert send(product,'你小时候怎么学画的？','scope-before').status=='terminal'
    assert send(product,'当时是什么样？','scope-before-two').status=='terminal'
    before=history(product); registry=config.state_path.read_bytes(); count=len(transport.calls)
    view=preview(product,'为什么呢？')
    assert view.status=='available' and len(view.recent_dialogue)==2 and len(view.self_knowledge)==1
    assert history(product)==before and config.state_path.read_bytes()==registry and len(transport.calls)==count
    assert send(product,'为什么呢？','scope-preview-send').status=='terminal'
    from dynamic_subject_agent.original_whole_chat import digest
    payload=json.loads(transport.calls[-1]['messages'][1]['content'])
    assert view.projection_digest==digest(payload)
    request=request_for(product)
    assert product.application.apply_whole_context_boundary(request).status=='committed'
    fresh=preview(product,'为什么呢？')
    assert fresh.status=='available' and fresh.context_revision==1 and fresh.recent_dialogue==() and fresh.self_knowledge==()
    assert fresh.has_prior_committed_exchange and fresh.snapshot_fingerprint!=view.snapshot_fingerprint
    assert product.application.set_reviewed_character_history(False).history_enabled is False
    off=preview(product,'你好。')
    assert off.status=='available' and off.recent_dialogue==() and not off.history_enabled
    assert product.application.set_reviewed_character_history(True).history_enabled is True
    assert preview(product,'你好。').recent_dialogue==()


def test_schema1_preview_shares_control_historyoff_and_exact_baseline_bytes(whole_fixture):
    opening,_,config,_=whole_fixture
    opening().close()
    from test_subject_request_lookup import canonical_path, counts
    path=canonical_path(config)
    transport=WholeTransport(); product=opening(transport)
    before=counts(path)
    empty=preview(product,'你好。')
    assert empty.status=='available' and empty.recent_dialogue==() and not transport.calls
    assert counts(path)==before
    assert send(product,'你好。','preview-baseline').status=='terminal'
    from dynamic_subject_agent.original_whole_chat import digest
    assert empty.projection_digest==digest(json.loads(transport.calls[0]['messages'][1]['content']))
    assert product.application.set_reviewed_character_history(False).history_enabled is False
    restricted=preview(product,'不要再使用之前的聊天。')
    assert restricted.status=='unavailable' and restricted.recent_dialogue==() and len(transport.calls)==1
    saved_counts=counts(path)
    db=sqlite3.connect(path,autocommit=True)
    try: db.execute("UPDATE expression_record SET expression_text='TAMPERED_SYNTHETIC_TEXT'")
    finally: db.close()
    unverified=preview(product,'历史关闭也不能显示坏前缀。')
    assert unverified.status!='available' and unverified.character_core==() and unverified.projection_digest==''
    assert len(transport.calls)==1 and counts(path)==saved_counts


def test_pending_or_changing_authority_preview_cannot_show_old_scope(whole_fixture,monkeypatch):
    opening,_,_,_=whole_fixture
    entered,release=Event(),Event()
    def blocking(): entered.set(); assert release.wait(10)
    transport=WholeTransport(callback=blocking); product=opening(transport)
    from dynamic_subject_agent.timeline import SubjectCommand
    command=SubjectCommand.contribute_utterance(target_profile_id=product.profile_id,target_timeline_id=product.timeline_id,
        declared_intent='ask-collaborator-status',utterance='合成在途消息。',language='zh',provenance='project-original')
    pending=product.application.submit(command,idempotency_key='whole-scope-preview-pending')
    assert entered.wait(5)
    try:
        unavailable=preview(product,'未提交的合成草稿。')
        assert unavailable.status=='unavailable' and unavailable.character_core==() and len(transport.calls)==1
    finally: release.set()
    assert product.application.wait(pending.operation_ref,timeout_seconds=30).status=='terminal'
    from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
    original=LocalIdentityAuthority.try_whole_scope_snapshot
    calls=[0]
    def changed(self,*args):
        source=original(self,*args); calls[0]+=1
        if calls[0]==2:
            self.set_reviewed_character_history(False)
        return source
    monkeypatch.setattr(LocalIdentityAuthority,'try_whole_scope_snapshot',changed)
    assert preview(product,'另一份未提交草稿。').status=='unavailable'
