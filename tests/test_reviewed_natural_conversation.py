"""Actual LOCAL publication/recovery; all model proposals explicitly synthetic."""
import json
from copy import deepcopy
from dataclasses import replace
import pytest
from test_original_whole_chat import approved, model_fixture, personality_fixture, send, history
from test_natural_experience_cycle import TEMP, CORRECT, STOP, CONTINUE, state
from dynamic_subject_agent.local_product import open_natural_experience_product_local
from dynamic_subject_agent.model_gateway import ProviderAdapter,ProviderCapabilities,StructuredOutputMode,ModelGateway,ModelResult,ModelTaskKind
from dynamic_subject_agent.timeline import TimelineEngine,FaultPoint

BAD='我刚完成了一个没有记录的实验。'
GOOD='我想和你一起找个轻松的切入点。你想从哪里开始？'


class Adapter(ProviderAdapter):
    capabilities=ProviderCapabilities('reviewed-local-fixture','synthetic',True,(StructuredOutputMode.JSON_OBJECT,))
    def __init__(self):
        self.calls=[];self.reject_draft=True;self.reject_repair=False;self.uncertain=False
    def invoke(self,task):
        self.calls.append(deepcopy(task));p=task.payload
        if task.kind is ModelTaskKind.MEMORIE_NATURAL_EXPERIENCE:
            text=p['current_user_text']
            value=(dict(action='remember',duration='today',reason_code='correction' if text==CORRECT else 'temporary')
                if text in (TEMP,CORRECT) else dict(action='forget',duration=None,reason_code='explicit-forget')
                if text==STOP else dict(action='keep',duration=None,reason_code='irrelevant'))
        elif task.kind is ModelTaskKind.MEMORIE_GROUNDED_EXPRESSION:
            value=BAD if self.reject_draft else GOOD
        elif task.kind is ModelTaskKind.MEMORIE_REPLY_REPAIR:
            assert p['rejected_reply']==BAD and p['review_issues'][0]['quote']==BAD
            value=BAD if self.reject_repair else GOOD
        elif task.kind is ModelTaskKind.ACTIVITY_REPLY_REVIEW:
            value=dict(verdict='uncertain',issues=[]) if self.uncertain else (
                dict(verdict='unsupported',issues=[dict(quote=BAD,kind='unsupported_event',basis_labels=[])])
                if p['candidate_text']==BAD else dict(verdict='supported',issues=[]))
        else:raise AssertionError(task.kind)
        return ModelResult(task.kind,value)


@pytest.fixture
def opening(approved):
    author,config,request,view=approved
    frozen=author.application.freeze_source_identity(request);assert frozen.status=='created';author.close()
    asset=json.loads(view.runtime_asset_json)
    binding=dict(definition_basis=view.definition_basis,runtime_asset_sha=view.runtime_asset_sha,
        persona_digest=asset['persona_digest'],review_basis='a'*64,scope_digest='b'*64,
        subject_id=asset['subject']['subject_id'],anchor_id=asset['anchor']['anchor_id'])
    opened=[]
    def open_one(adapter=None,reviewed=True):
        product=open_natural_experience_product_local(config,gateway=ModelGateway(adapter or Adapter()),
            identity_id=frozen.view.identity_id,binding=binding,reviewed=reviewed)
        opened.append(product);return product
    open_one.config=config
    yield open_one
    for product in opened:product.close()


def test_full_repair_correct_reopen_stop_and_only_final_reply_in_history(opening):
    adapter=Adapter();p=opening(adapter);scope=p.profile_id,p.timeline_id
    first=send(p,TEMP,'reviewed-first')
    assert first.projection.failure_code is None and first.projection.expression_text==GOOD,first
    assert len(adapter.calls)==5 and state(p)['natural_experience']['quote']==TEMP
    assert send(p,CORRECT,'reviewed-correction').projection.failure_code is None
    p.close();fresh=Adapter();fresh.reject_draft=False;p=opening(fresh)
    assert (p.profile_id,p.timeline_id)==scope and not fresh.calls
    result=send(p,CONTINUE,'reviewed-continue');assert result.projection.failure_code is None
    assert len(fresh.calls)==3
    draft=fresh.calls[1].payload
    assert draft['experience']['quote']==CORRECT
    assert draft['exchange']==[dict(user_text=CORRECT,assistant_text=GOOD)]
    assert BAD not in str(history(p)) and all(row.assistant_text==GOOD for row in history(p))
    assert send(p,STOP,'reviewed-stop').projection.failure_code is None
    assert state(p)['natural_experience'] is None
    count=len(fresh.calls)
    assert send(p,STOP,'reviewed-stop').status=='terminal' and len(fresh.calls)==count


@pytest.mark.parametrize('uncertain',[False,True])
def test_failed_or_uncertain_review_preserves_old_memory_and_no_bad_history(opening,uncertain):
    adapter=Adapter();adapter.reject_draft=False;p=opening(adapter)
    assert send(p,TEMP,'reviewed-old-source').projection.failure_code is None
    before=state(p)['natural_experience'];turns=history(p);count=len(adapter.calls)
    adapter.reject_draft=True;adapter.reject_repair=True;adapter.uncertain=uncertain
    result=send(p,CORRECT,'reviewed-rejected')
    assert result.status=='failed-closed' or result.projection.failure_code
    assert len(adapter.calls)-count==(3 if uncertain else 5)
    assert state(p)['natural_experience']==before and history(p)==turns
    p.close();fresh=Adapter();p=opening(fresh)
    assert state(p)['natural_experience']==before and not fresh.calls


def test_final_publication_rejects_receipt_for_different_context(opening,monkeypatch):
    from dynamic_subject_agent.natural_experience_cognition import NaturalExperienceCognition
    original=NaturalExperienceCognition._propose_reviewed_conversation
    def forged(self,**kwargs):
        proposal=original(self,**kwargs);natural=deepcopy(proposal.shared_record.natural)
        natural['speech']['review']['context_sha256']='0'*64
        return replace(proposal,shared_record=replace(proposal.shared_record,natural=natural))
    monkeypatch.setattr(NaturalExperienceCognition,'_propose_reviewed_conversation',forged)
    p=opening();result=send(p,TEMP,'reviewed-forged-context')
    assert result.status=='failed-closed' or result.projection.failure_code
    # A forged publication is an integrity failure, not an ordinary rejected
    # draft. Do not weaken the read-side failure merely to inspect its state.
    import sqlite3
    from contextlib import closing
    for path in opening.config.product_parent.rglob('timeline.sqlite3'):
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
            assert db.execute('SELECT COUNT(*) FROM timeline_outcome').fetchone()[0]==0


def test_prepared_reviewed_reply_recovers_without_regenerating_or_reviewing(opening,monkeypatch):
    adapter=Adapter();p=opening(adapter)
    hit=TimelineEngine._hit
    with monkeypatch.context() as crash:
        def fail(self,point):
            if point is FaultPoint.AFTER_PLAN_CLAIM:raise OSError('synthetic reviewed interruption')
            return hit(self,point)
        crash.setattr(TimelineEngine,'_hit',fail)
        send(p,TEMP,'reviewed-recover')
    p.close();fresh=Adapter();p=opening(fresh)
    assert not fresh.calls and state(p)['natural_experience']['quote']==TEMP
    assert history(p)[-1].assistant_text==GOOD and BAD not in str(history(p))
    send(p,TEMP,'reviewed-recover');assert not fresh.calls


def test_existing_unreviewed_root_cannot_silently_upgrade(opening):
    p=opening(reviewed=False);p.close()
    before=opening.config.state_path.read_bytes()
    with pytest.raises(RuntimeError,match='activation-conflict'):opening()
    assert opening.config.state_path.read_bytes()==before
