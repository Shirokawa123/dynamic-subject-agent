"""Approved source-understanding comparison with exact, source-bound delivery."""
from dataclasses import dataclass,asdict
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen
from time import monotonic
import json,os
from dynamic_subject_agent.character_understanding import (UNDERSTANDING_POLICY,REPLY_POLICY,validate_material as validate_source,
    validate_understanding,propose_understanding,reply_projection,reply_from_understanding,understanding_coverage)
from dynamic_subject_agent.frozen_attempt import FrozenAttemptRun,canonical_json,write_once
from dynamic_subject_agent.model_gateway import ModelGateway,ModelTaskKind,ModelResult,ProviderAdapter,ProviderCapabilities,StructuredOutputMode,ModelGatewayFailure
from dynamic_subject_agent.deepseek import DeepSeekUrlLibTransport,_post_json_reply_content,_post_text_reply_content,DEEPSEEK_CREDENTIAL_BACKEND_ID,DEEPSEEK_CREDENTIAL_KEY_ID
from dynamic_subject_agent.first_life_reply_live_provider import _ObservedTransport
from dynamic_subject_agent.cognition import CredentialRef

REVIEW='0e5dc916b57883205acd918629355202fe6279fc9b37f000ccf84b28719c7a6f'
VERSION='character-understanding-trial-m035-1'


@dataclass(frozen=True)
class UnderstandingTrialRequest:
    review_directory:Path
    approval_path:Path
    output:Path


def validate_trial(request):
    raw=(request.review_directory/'review.json').read_bytes()
    if sha256(raw).hexdigest()!=REVIEW:raise ValueError('exact M035 review required')
    review=json.loads(raw);approval=json.loads(request.approval_path.read_bytes())
    expected=dict(version=VERSION,review_sha256=REVIEW,human_confirmed=True,source_excerpt_use_confirmed=True,
        maximum_requests=10,automatic_retries=0,persona_activation_included=False,installation_included=False,
        authorization_source='direct-user-reply:2026-10-31-current-chat')
    if (set(approval)!=set(expected)|{'user_reply'} or type(approval['user_reply']) is not str or not approval['user_reply'].strip()
            or canonical_json({k:approval[k] for k in expected})!=canonical_json(expected)):
        raise ValueError('explicit excerpt and comparison approval required')
    if review['policies']!=dict(understanding=UNDERSTANDING_POLICY,reply=REPLY_POLICY):raise ValueError('approved policies changed')
    source=review['source_file']
    raw=Path(source['path']).read_bytes()
    if sha256(raw).hexdigest()!=source['sha256']:raise ValueError('original source changed')
    materials={}
    for role,digest in review['material_sha256'].items():
        raw=(request.review_directory/(role+'.material.json')).read_bytes()
        if sha256(raw).hexdigest()!=digest:raise ValueError('material packet changed')
        materials[role]=json.loads(raw);validate_source(materials[role])
    for name,digest in review['example_sha256'].items():
        if sha256((request.review_directory/(name+'.UNSENT.json')).read_bytes()).hexdigest()!=digest:
            raise ValueError('reviewed example changed')
    return review,materials


class UnderstandingDelivery(ProviderAdapter):
    capabilities=ProviderCapabilities('deepseek','deepseek-flash',False,(StructuredOutputMode.JSON_OBJECT,StructuredOutputMode.TEXT))
    validate_inputs=staticmethod(validate_trial)
    decode_understanding=staticmethod(validate_understanding)
    project_reply=staticmethod(reply_projection)
    maximum_requests=10
    def __init__(self,request,journal,transport_factory=None):
        self.request,self.journal,self.transport_factory=request,journal,transport_factory
        self.understandings={}
    def body(self,task,index):
        review,materials=self.validate_inputs(self.request)
        if not 0<=index<self.maximum_requests:raise ValueError('approved request bound reached')
        case=review['cases'][index];material=materials[case['role']]
        if case['purpose']=='understanding':
            expected=material;kind=ModelTaskKind.CHARACTER_SOURCE_UNDERSTANDING
        else:
            derived=self.understandings[case['role']] if case['condition']=='with-understanding' else None
            expected=self.project_reply(material,case['question'],derived);kind=ModelTaskKind.CHARACTER_UNDERSTANDING_REPLY
        if task.kind is not kind or task.payload!=expected:raise ValueError('exact source-bound next task required')
        params=dict(review['parameters'])
        if case['purpose']=='understanding':params['response_format']=dict(type='json_object')
        raw=canonical_json(dict(params,messages=[dict(role='system',content=review['policies'][case['purpose']]),
            dict(role='user',content=canonical_json(expected))])).encode()
        if len(raw)>65536:raise ValueError('request oversized')
        return raw,case,material
    def invoke(self,task):
        index=self.journal.next;raw,case,material=self.body(task,index);digest=sha256(raw).hexdigest()
        self.journal.claim(digest);write_once(self.request.output/(case['id']+'.request.json'),json.loads(raw))
        sent=False;started=monotonic()
        def opener(request,*,timeout):
            nonlocal sent
            if (sent or self.body(task,index)[0]!=raw or request.data!=raw or request.get_method()!='POST'
                    or request.full_url!='https://api.deepseek.com/chat/completions' or timeout!=30):
                raise ValueError('one-shot approved source delivery required')
            sent=True;return urlopen(request,timeout=timeout)
        if self.transport_factory is None:
            from dynamic_subject_agent.local_product import _WindowsLabResolver
            transport=DeepSeekUrlLibTransport(credential_resolver=_WindowsLabResolver(),_opener=opener)
        else:transport=self.transport_factory(opener)
        observed=_ObservedTransport(transport)
        ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,key_id=DEEPSEEK_CREDENTIAL_KEY_ID)
        value=None;code=None;status='complete'
        try:
            if case['purpose']=='understanding':
                value=_post_json_reply_content(observed,ref,raw,max_output_tokens=4096,require_complete=True,discard_reasoning=True,safe_diagnostics=True)
                self.understandings[case['role']]=self.decode_understanding(material,value)
            else:
                from dynamic_subject_agent.original_whole_chat import validate_whole_reply
                value=_post_text_reply_content(observed,ref,raw,max_output_tokens=4096)
                validate_whole_reply(dict(reply_text=value,language='zh'))
        except Exception as exc:
            from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
            code='character-credential-unavailable' if isinstance(exc,CharacterCredentialUnavailable) else getattr(exc,'diagnostic_code','source-understanding-invalid')
            status='unavailable' if isinstance(exc,CharacterCredentialUnavailable) else 'unknown' if code in ('transport-timeout','transport-delivery-ambiguous') else 'failed-closed'
        row=dict(case=case['id'],role=case['role'],purpose=case['purpose'],status=status,error_code=code,value=value,
            elapsed_seconds=round(monotonic()-started,3),request_sha256=digest,
            **{k:observed.row[k] for k in ('model','usage','finish_reason','final_content')})
        self.journal.record(digest,row);write_once(self.request.output/(case['id']+'.result.json'),row)
        if code:
            self.journal.stop(code);raise ModelGatewayFailure(code)
        return ModelResult(task.kind,value)


def run_trial(request,*,_transport_factory=None,_audit_parent=None,anchored=False):
    validator=validate_trial;delivery_type=UnderstandingDelivery;review_id=REVIEW
    propose=propose_understanding;reply=reply_from_understanding;coverage=understanding_coverage
    if anchored:
        from dynamic_subject_agent.anchored_understanding_trial import validate_trial as validator,AnchoredUnderstandingDelivery as delivery_type,REVIEW as review_id
        from dynamic_subject_agent.anchored_character_understanding import propose_understanding as propose,reply_from_understanding as reply,understanding_coverage as coverage
    review,materials=validator(request)
    if request.output.exists() or request.output.resolve().parent!=request.review_directory.resolve().parent or request.output.resolve().parent.name!='.artifacts':
        raise ValueError('fresh sibling artifact root required')
    if _audit_parent is not None and _transport_factory is None:raise ValueError('real journal cannot be redirected')
    audit=_audit_parent if _transport_factory is not None else Path(os.environ['LOCALAPPDATA'])/('DynamicSubjectAgent/anchored-understanding-m036' if anchored else 'DynamicSubjectAgent/character-understanding-m035')
    audit.mkdir(parents=True,exist_ok=True);journal=FrozenAttemptRun(audit,review_id,approved=True)
    if journal.resumed:raise ValueError('review already started; no resend or new-root retry')
    request.output.mkdir();delivery=delivery_type(request,journal,_transport_factory);gateway=ModelGateway(delivery)
    understandings={};rows=[]
    try:
        for case in review['cases']:
            material=materials[case['role']]
            try:
                if case['purpose']=='understanding':
                    understanding=propose(gateway,material);understandings[case['role']]=understanding
                    write_once(request.output/(case['role']+'.understanding.json'),asdict(understanding))
                    write_once(request.output/(case['role']+'.coverage.json'),coverage(material,understanding))
                    row=dict(case=case['id'],status='proposed',observations=len(understanding.observations),interpretations=len(understanding.interpretations))
                    if understanding.status=='no-op':
                        row['status']='no-op';rows.append(row);journal.stop('no-character-interpretation');break
                else:
                    value=reply(gateway,material,case['question'],understandings[case['role']] if case['condition']=='with-understanding' else None)
                    row=dict(case=case['id'],status='candidate',question=case['question'],reply_text=value.reply_text,condition=case['condition'])
                rows.append(row)
            except Exception as exc:
                code=getattr(exc,'code','understanding-trial-invalid');journal.stop(code)
                rows.append(dict(case=case['id'],status='stopped',error_code=code));break
        result=dict(status='no-op' if any(r['status']=='no-op' for r in rows) else 'complete' if len(rows)==len(review['cases']) and all(r['status']!='stopped' for r in rows) else 'stopped',
            attempts=journal.next,rows=rows,semantic_acceptance='not-evaluated',persona_activated=False,canonical_writes=0)
        write_once(request.output/'results.json',result);return result
    except Exception:
        journal.stop('trial-recording-failed');raise
