"""Frozen M033 review of existing outputs; no generation or canonical writes."""
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
from urllib.request import urlopen

from dynamic_subject_agent.activity_reply_review import VERSION, adjudicate_review, outbound_bytes
from dynamic_subject_agent.frozen_attempt import FrozenAttemptRun, canonical_json, write_once
from dynamic_subject_agent.model_gateway import ModelGateway, ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelTaskKind, ModelTask, ModelResult, ModelGatewayFailure
from dynamic_subject_agent.deepseek import DeepSeekUrlLibTransport, _post_json_reply_content, DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID
from dynamic_subject_agent.first_life_reply_live_provider import _ObservedTransport
from dynamic_subject_agent.cognition import CredentialRef

REVIEW = '38f2ee1788e23746e42bf2946be953b28008041d3db85a6705f326b1445f902b'


@dataclass(frozen=True)
class ActivityReviewTrialRequest:
    review_directory: Path
    approval_path: Path
    source_directory: Path
    preparation_path: Path
    output: Path


def validate_material(request):
    raw=(request.review_directory/'review.json').read_bytes()
    if sha256(raw).hexdigest()!=REVIEW:
        raise ValueError('exact activity-review plan required')
    review=json.loads(raw)
    receipt=json.loads(request.approval_path.read_bytes())
    fields=dict(version=VERSION,review_sha256=REVIEW,human_confirmed=True,maximum_requests=10,
        automatic_retries=0,installation_included=False,user_data_upgrade_included=False,
        authorization_source='direct-user-reply:2026-10-30-current-chat')
    if (set(receipt)!=set(fields)|{'user_reply'} or type(receipt['user_reply']) is not str or not receipt['user_reply'].strip()
            or canonical_json({k:receipt[k] for k in fields})!=canonical_json(fields)):
        raise ValueError('exact explicit activity-review approval required')
    if (sha256(request.preparation_path.read_bytes()).hexdigest()!=review['preparation_sha256']
            or sha256((request.source_directory/'results.json').read_bytes()).hexdigest()!=review['source_summary_sha256']):
        raise ValueError('reviewed material or preserved trial changed')
    for name,digest in review['source_file_sha256'].items():
        if sha256((request.source_directory/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('preserved original request/result changed')
    bodies={}
    for case in review['cases']:
        raw=(request.review_directory/(case['id']+'.request.json')).read_bytes()
        payload=json.loads(json.loads(raw)['messages'][1]['content'])
        if sha256(raw).hexdigest()!=case['request_sha256'] or outbound_bytes(payload)!=raw:
            raise ValueError('exact frozen review request required')
        bodies[case['id']]=raw
    return review,bodies


class FrozenReviewAdapter(ProviderAdapter):
    capabilities=ProviderCapabilities('deepseek','deepseek-flash',False,(StructuredOutputMode.JSON_OBJECT,))

    def __init__(self,request,journal,transport_factory=None):
        self.request,self.journal,self.transport_factory=request,journal,transport_factory

    def invoke(self,task):
        review,bodies=validate_material(self.request)
        if (task.kind is not ModelTaskKind.ACTIVITY_REPLY_REVIEW or self.journal.next>=10
                or task.payload!=review['cases'][self.journal.next]['id']):
            raise ModelGatewayFailure('review-trial-order-invalid')
        name=task.payload;raw=bodies[name];digest=sha256(raw).hexdigest()
        self.journal.claim(digest)
        sent=False
        def opener(request,*,timeout):
            nonlocal sent
            if (sent or validate_material(self.request)[1][name]!=raw or request.data!=raw
                    or request.get_method()!='POST' or timeout!=30
                    or request.full_url!='https://api.deepseek.com/chat/completions'):
                raise ValueError('one-shot approved review delivery required')
            sent=True
            return urlopen(request,timeout=timeout)
        if self.transport_factory is None:
            from dynamic_subject_agent.local_product import _WindowsLabResolver
            transport=DeepSeekUrlLibTransport(credential_resolver=_WindowsLabResolver(),_opener=opener)
        else:
            transport=self.transport_factory(opener)
        observed=_ObservedTransport(transport)
        ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,key_id=DEEPSEEK_CREDENTIAL_KEY_ID)
        value=None;gate=None;code=None;status='complete'
        try:
            value=_post_json_reply_content(observed,ref,raw,max_output_tokens=4096,
                require_complete=True,discard_reasoning=True,safe_diagnostics=True)
            payload=json.loads(json.loads(raw)['messages'][1]['content'])
            gate=adjudicate_review(payload,value,request_digest=digest)
        except Exception as exc:
            from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
            code='character-credential-unavailable' if isinstance(exc,CharacterCredentialUnavailable) else getattr(exc,'diagnostic_code','activity-review-failed')
            status='unavailable' if isinstance(exc,CharacterCredentialUnavailable) else 'unknown' if code in ('transport-timeout','transport-delivery-ambiguous') else 'failed-closed'
        row=dict(case=name,status=status,error_code=code,value=value,
            gate_status=None if gate is None else gate.status,
            accepted_reply=None if gate is None else gate.reply_text,
            **{k:observed.row[k] for k in ('model','usage','finish_reason','final_content')})
        self.journal.record(digest,row)
        write_once(self.request.output/(name+'.result.json'),row)
        if code:
            self.journal.stop(code)
            raise ModelGatewayFailure(code)
        return ModelResult(task.kind,row)


def run_trial(request,*,_transport_factory=None,_audit_parent=None):
    review,_=validate_material(request)
    if (request.output.exists() or request.output.resolve().parent!=request.review_directory.resolve().parent
            or request.output.resolve().parent.name!='.artifacts'):
        raise ValueError('fresh isolated sibling output required')
    if _audit_parent is not None and _transport_factory is None:
        raise ValueError('real journal cannot be redirected')
    parent=_audit_parent if _transport_factory is not None else Path(os.environ['LOCALAPPDATA'])/'DynamicSubjectAgent/activity-reply-review-m033'
    parent.mkdir(parents=True,exist_ok=True)
    journal=FrozenAttemptRun(parent,REVIEW,approved=True)
    if journal.resumed:
        raise ValueError('review already started; no second root or resend')
    request.output.mkdir()
    gateway=ModelGateway(FrozenReviewAdapter(request,journal,_transport_factory));rows=[]
    try:
        for case in review['cases']:
            try:
                rows.append(gateway.execute(ModelTask(ModelTaskKind.ACTIVITY_REPLY_REVIEW,case['id'])).value)
            except ModelGatewayFailure as error:
                journal.stop(error.code)
                rows.append(dict(case=case['id'],status='stopped',error_code=error.code))
                break
        result=dict(status='complete' if len(rows)==10 and all(row['status']=='complete' for row in rows) else 'stopped',
            attempts=journal.next,rows=rows,reply_generation_calls=0,canonical_writes=0,runtime_activated=False)
        write_once(request.output/'results.json',result)
        return result
    except Exception:
        journal.stop('review-recording-failed')
        raise
