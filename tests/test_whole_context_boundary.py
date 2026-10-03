from dataclasses import asdict, replace
import json
from threading import Event
from time import monotonic

import pytest

from dynamic_subject_agent.local_product import open_original_whole_product
from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
from dynamic_subject_agent.whole_context_boundary import WholeContextBoundaryRequest
from test_original_whole_chat import approved, personality_fixture, model_fixture, WholeTransport, send, history


@pytest.fixture
def context_fixture(approved, monkeypatch, tmp_path):
    author, config, request, view = approved
    frozen = author.application.freeze_source_identity(request)
    assert frozen.status == 'created'
    author.close()  # Do not select the dormant identity or create a schema-1 Host.
    asset = json.loads(view.runtime_asset_json)
    import dynamic_subject_agent.original_whole_chat as module
    binding = dict(definition_basis=view.definition_basis, runtime_asset_sha=view.runtime_asset_sha,
        persona_digest=asset['persona_digest'], review_basis='1'*64, scope_digest='2'*64,
        subject_id=asset['subject']['subject_id'], anchor_id=asset['anchor']['anchor_id'])
    monkeypatch.setattr(module, 'APPROVED_BINDING', binding)
    options = {key:binding[key] for key in ('definition_basis','runtime_asset_sha','persona_digest','review_basis','scope_digest')}
    options.update(audit_path=tmp_path/'context-audit', technical_variant='context-boundary', identity_id=frozen.view.identity_id)
    opened=[]
    def opening(transport=None):
        product = open_original_whole_product(config, **options, _transport=transport or WholeTransport())
        opened.append(product)
        return product
    yield opening, config, options
    for product in opened: product.close()


def request_for(product, key='whole-context-test-boundary', revision=0, confirmed=True):
    return WholeContextBoundaryRequest(product.profile_id, product.timeline_id, key, revision, confirmed)


def test_same_identity_two_turns_boundary_and_new_exchange_persist_without_model_control(context_fixture):
    opening, _, _ = context_fixture
    transport=WholeTransport(); product=opening(transport)
    scope=product.application.query_whole_context_boundary()
    assert scope['status']=='available' and scope['context_revision']==0, scope
    assert send(product,'你小时候怎么学画的？','before-one').status=='terminal'
    assert send(product,'当时是什么样？','before-two').status=='terminal'
    old=history(product)
    request=request_for(product)
    result=product.application.apply_whole_context_boundary(request)
    assert result.status=='committed', result
    assert len(transport.calls)==2 and history(product)==old
    replay=product.application.apply_whole_context_boundary(request)
    assert replay.status=='replayed' and replay.receipt==result.receipt
    query=product.application.query_whole_context_boundary(request)
    assert query['request_status']=='replayed' and query['receipt']==result.receipt
    assert send(product,'为什么呢？','after-one').status=='terminal'
    payload=json.loads(transport.calls[-1]['messages'][1]['content'])
    assert payload['exchange']==[] and payload['background']['self_knowledge']==[]
    assert payload['turn']['has_prior_committed_exchange'] is True
    saved=history(product); product.close()
    restarted_transport=WholeTransport(); restarted=opening(restarted_transport)
    assert history(restarted)==saved and not restarted_transport.calls
    assert restarted.application.query_whole_context_boundary()['context_revision']==1


def test_cancel_conflict_history_setting_and_post_boundary_window(context_fixture):
    opening, _, _=context_fixture
    transport=WholeTransport(); product=opening(transport)
    assert send(product,'你小时候怎么学画的？','prior').status=='terminal'
    assert product.application.set_reviewed_character_history(False).history_enabled is False
    request=request_for(product)
    cancelled=product.application.apply_whole_context_boundary(replace(request,confirmed=False))
    assert cancelled.status=='cancelled' and product.application.query_whole_context_boundary()['context_revision']==0
    assert product.application.apply_whole_context_boundary(request).status=='committed'
    assert product.application.reviewed_character_chat_status().history_enabled is False
    assert product.application.apply_whole_context_boundary(replace(request,expected_revision=1)).status=='conflict'
    assert product.application.set_reviewed_character_history(True).history_enabled is True
    assert send(product,'为什么呢？','fresh-empty').status=='terminal'
    first=json.loads(transport.calls[-1]['messages'][1]['content'])
    assert first['exchange']==[] and first['background']['self_knowledge']==[]
    assert send(product,'现在聊什么？','fresh-next').status=='terminal'
    assert len(json.loads(transport.calls[-1]['messages'][1]['content'])['exchange'])==1


def test_inflight_control_is_immediately_busy_without_waiting_registry_or_worker(context_fixture):
    opening,_,_=context_fixture
    entered,release=Event(),Event()
    def blocking():
        entered.set(); assert release.wait(10)
    transport=WholeTransport(callback=blocking); product=opening(transport)
    from dynamic_subject_agent.timeline import SubjectCommand
    command=SubjectCommand.contribute_utterance(target_profile_id=product.profile_id,target_timeline_id=product.timeline_id,
        declared_intent='ask-collaborator-status',utterance='在途合成消息。',language='zh',provenance='project-original')
    pending=product.application.submit(command,idempotency_key='whole-context-inflight-chat')
    assert entered.wait(5)
    try:
        start=monotonic(); result=product.application.apply_whole_context_boundary(request_for(product))
        assert monotonic()-start<3 and result.status=='busy',result
        assert product.application.query_whole_context_boundary()['context_revision']==0
    finally:
        release.set()
    assert product.application.wait(pending.operation_ref,timeout_seconds=30).status=='terminal'
    assert len(transport.calls)==1


@pytest.mark.parametrize('after_commit',[False,True])
def test_boundary_interruption_is_atomic_and_receipt_replays_without_model(context_fixture,monkeypatch,after_commit):
    opening,_,_=context_fixture
    transport=WholeTransport(); product=opening(transport)
    assert send(product,'已提交合成消息。','saved').status=='terminal'
    from dynamic_subject_agent.timeline import TimelineEngine,FaultPoint
    original=TimelineEngine._hit
    def hit(self,point):
        if point is (FaultPoint.AFTER_PUBLICATION_COMMIT if after_commit else FaultPoint.BEFORE_PUBLICATION_COMMIT):
            raise OSError('Synthetic local boundary interruption.')
        return original(self,point)
    monkeypatch.setattr(TimelineEngine,'_hit',hit)
    request=request_for(product)
    result=product.application.apply_whole_context_boundary(request)
    monkeypatch.setattr(TimelineEngine,'_hit',original)
    scope=product.application.query_whole_context_boundary()
    assert scope['context_revision']==(1 if after_commit else 0)
    assert len(transport.calls)==1 and len(history(product))==1
    product.close(); restarted=opening(WholeTransport())
    query=restarted.application.query_whole_context_boundary(request)
    assert query['context_revision']==(1 if after_commit else 0)
    if after_commit:
        assert query['request_status']=='replayed' and result.receipt==query['receipt']
    else:
        assert query['request_status']=='failed-closed'
        assert send(restarted,'中断后正常新话题。','after-control-interruption').status=='terminal'


def test_terminal_old_control_crosses_proven_boundary_and_new_withdrawal_cuts_only_old_window(context_fixture):
    opening,_,_=context_fixture
    transport=WholeTransport(); product=opening(transport)
    assert send(product,'不要再使用之前的聊天。','old-control').status=='failed-closed'
    assert product.application.apply_whole_context_boundary(request_for(product)).status=='committed'
    assert send(product,'普通新话题。','safe-new').status=='terminal'
    assert send(product,'不要再使用之前的聊天。','new-control').status=='failed-closed'
    assert send(product,'接着说吧。','after-new-withdrawal').status=='terminal'
    assert len(transport.calls)==2
    assert json.loads(transport.calls[-1]['messages'][1]['content'])['exchange']==[]


def test_missing_boundary_record_is_not_a_permitted_nonchat_head(context_fixture):
    opening,config,_=context_fixture
    product=opening(); assert send(product,'原合成消息。','before-missing').status=='terminal'
    assert product.application.apply_whole_context_boundary(request_for(product)).status=='committed'
    product.close()
    from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
    from dynamic_subject_agent.host import RuntimeHost
    from dynamic_subject_agent.original_whole_chat_cognition import OriginalWholeChatCognition
    from dynamic_subject_agent.whole_context_boundary import CONTEXT_AUTHORITY
    loaded=LocalIdentityAuthority(config).load_active()
    host=RuntimeHost.open(loaded.host_location,studio_location=loaded.studio_location,
        cognition=OriginalWholeChatCognition(provider_authority=CONTEXT_AUTHORITY))
    try:
        path=host.query_binding(profile_id=loaded.qri.profile_id,timeline_id=loaded.timeline_id).timeline_root.timeline_database
    finally:
        host.close()
    import sqlite3
    db=sqlite3.connect(path,autocommit=True)
    try: db.execute('DELETE FROM whole_context_boundary')
    finally: db.close()
    with pytest.raises(Exception): opening()


def test_old_unfrozen_failure_cannot_be_hidden_by_boundary(context_fixture,monkeypatch):
    opening,config,_=context_fixture
    product=opening()
    assert send(product,'不要再使用之前的聊天。','unfrozen-old').status=='failed-closed'
    from dynamic_subject_agent.timeline import TimelineEngine
    original=TimelineEngine._verify_whole_failed_prefix
    def broken(*a,**kw): raise ValueError('Synthetic absent four-field failure proof.')
    monkeypatch.setattr(TimelineEngine,'_verify_whole_failed_prefix',broken)
    assert product.application.apply_whole_context_boundary(request_for(product)).status=='failed-closed'
    assert product.application.query_whole_context_boundary()['context_revision']==0


def test_history_revision_change_at_boundary_commit_cancels_without_partial_control(context_fixture,monkeypatch):
    opening,config,_=context_fixture
    product=opening()
    from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
    from dynamic_subject_agent.timeline import TimelineEngine,FaultPoint
    authority=LocalIdentityAuthority(config); original=TimelineEngine._hit
    def hit(self,point):
        if point is FaultPoint.BEFORE_PUBLICATION_COMMIT:
            assert authority.set_reviewed_character_history(False).history_enabled is False
            assert authority.set_reviewed_character_history(True).history_enabled is True
        return original(self,point)
    monkeypatch.setattr(TimelineEngine,'_hit',hit)
    assert product.application.apply_whole_context_boundary(request_for(product)).status=='failed-closed'
    assert product.application.query_whole_context_boundary()['context_revision']==0


def test_subject_cannot_impersonate_context_or_life_system_input(context_fixture):
    opening,_,_=context_fixture
    transport=WholeTransport(); product=opening(transport)
    from dynamic_subject_agent.timeline import SubjectCommand
    for intent in ('whole-context-boundary-input','first-life-system-input'):
        command=SubjectCommand.contribute_utterance(target_profile_id=product.profile_id,target_timeline_id=product.timeline_id,
            declared_intent=intent,utterance='伪装系统输入的合成文字。',language='zh',provenance='project-original')
        response=product.application.submit(command,idempotency_key='whole-context-spoof-'+intent)
        assert response.operation_ref is None and response.status=='unavailable'
    assert not transport.calls and product.application.query_whole_context_boundary()['context_revision']==0
