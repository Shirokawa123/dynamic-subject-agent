"""M034 exact LIVE delivery: bounded stage order and persisted review receipts."""
from contextlib import contextmanager
from hashlib import sha256
from threading import get_ident
from time import monotonic
from urllib.request import urlopen
import json

from dynamic_subject_agent.natural_experience_cycle import CHECKED_LIVE_VERSION,CHECKED_REVIEW as REVIEW
from dynamic_subject_agent.reviewed_natural_reply import PROTOCOL,REPAIR_POLICY,context_digest,review_payload,validate_receipt
from dynamic_subject_agent.activity_reply_review import POLICY as REVIEW_POLICY,PARAMETERS as REVIEW_PARAMETERS,adjudicate_review
from dynamic_subject_agent.frozen_attempt import canonical_json,write_once
from dynamic_subject_agent.model_gateway import ProviderAdapter,ProviderCapabilities,StructuredOutputMode,ModelTaskKind,ModelResult,ModelGatewayFailure
from dynamic_subject_agent.deepseek import DeepSeekUrlLibTransport,_post_json_reply_content,_post_text_reply_content,DEEPSEEK_CREDENTIAL_BACKEND_ID,DEEPSEEK_CREDENTIAL_KEY_ID
from dynamic_subject_agent.first_life_reply_live_provider import _ObservedTransport
from dynamic_subject_agent.cognition import CredentialRef


def validate_material(request):
    raw=(request.review_directory/'review.json').read_bytes()
    if sha256(raw).hexdigest()!=REVIEW:raise ValueError('exact M034 review required')
    review=json.loads(raw);receipt=json.loads(request.approval_path.read_bytes())
    expected=dict(version='reviewed-natural-conversation-use-m034-1',review_sha256=REVIEW,human_confirmed=True,
        maximum_requests=30,automatic_retries=0,installation_included=False,user_data_upgrade_included=False,
        authorization_source='direct-user-reply:2026-10-30-current-chat',user_reply='同意这次完整隔离验证')
    if canonical_json(receipt)!=canonical_json(expected):raise ValueError('exact M034 approval required')
    if sha256(request.preparation_path.read_bytes()).hexdigest()!=review['preparation_sha256']:
        raise ValueError('reviewed preparation changed')
    if (review['protocol']!=PROTOCOL or review['review']['policy']!=REVIEW_POLICY
            or review['review']['parameters']!=REVIEW_PARAMETERS or review['repair']['policy']!=REPAIR_POLICY):
        raise ValueError('approved protocol implementation changed')
    examples={}
    for name,digest in review['examples_sha256'].items():
        raw=(request.review_directory/(name+'.UNSENT.json')).read_bytes()
        if sha256(raw).hexdigest()!=digest:raise ValueError('illustrative reviewed request changed')
        examples[name]=json.loads(raw)
    source=json.loads(examples['first-selection']['messages'][1]['content'])
    return review,{k:source[k] for k in ('character','personality')}


class ReviewedNaturalDelivery(ProviderAdapter):
    capabilities=ProviderCapabilities('deepseek','deepseek-flash',False,(StructuredOutputMode.JSON_OBJECT,StructuredOutputMode.TEXT))

    def __init__(self,request,journal,contract,*,transport_factory=None):
        self.request,self.journal,self.contract=request,journal,contract
        self.transport_factory=transport_factory;self._frame=None
        self.turn=0;self.stage='selection';self.base=None;self.candidate=None;self.issues=None
        self.validate()
        if journal.resumed or journal.stopped:
            # A stopped/previous process may reopen to read or recover its
            # committed prefix. It never gets another generation opportunity.
            self.stage='stopped'
            return
        if journal.next:
            row=json.loads((request.output/f'{journal.next:02d}.result.json').read_bytes())
            if (row!=journal.read_result(row['request_sha256']) or row['status']!='complete'
                    or row['next_stage']!='selection' or row['index']!=journal.next-1):
                raise ValueError('only a completed turn can reopen this trial')
            self.turn=row['next_turn']

    def validate(self):
        result=validate_material(self.request)
        if self.contract['version']!=CHECKED_LIVE_VERSION or self.contract['technical_variant']['natural_render_version']!=REVIEW:
            raise ValueError('exact M034 LIVE qualification required')
        return result

    def assert_turn(self,revision):
        if revision!=self.turn or self.stage!='selection':raise ValueError('canonical turn and sender position differ')

    @contextmanager
    def frame(self,projection):
        if self._frame is not None:raise ValueError('one current delivery frame required')
        self._frame=(get_ident(),projection)
        try:yield
        finally:self._frame=None

    def _body(self,task):
        review,background=self.validate()
        if (self.journal.next>=30 or self.turn>=6 or self._frame is None or self._frame[0]!=get_ident()
                or task.payload!=self._frame[1]()):
            raise ValueError('bounded current approved frame required')
        kinds={'selection':ModelTaskKind.MEMORIE_NATURAL_EXPERIENCE,'draft':ModelTaskKind.MEMORIE_GROUNDED_EXPRESSION,
            'review-draft':ModelTaskKind.ACTIVITY_REPLY_REVIEW,'repair':ModelTaskKind.MEMORIE_REPLY_REPAIR,
            'review-repair':ModelTaskKind.ACTIVITY_REPLY_REVIEW}
        if kinds.get(self.stage)!=task.kind:raise ValueError('exact next phase required')
        p=task.payload;spec=review['review' if self.stage.startswith('review-') else self.stage]
        message=p['current_message'] if task.kind is ModelTaskKind.ACTIVITY_REPLY_REVIEW else p['current_user_text']
        if message!=review['scenario'][self.turn]['text'] or set(p)!=set(spec['fields']):
            raise ValueError('exact approved user turn and fields required')
        if p['character']!=background['character'] or ('personality' in p and p['personality']!=background['personality']):
            raise ValueError('exact sealed material required')
        if self.stage.startswith('review-') and p!=review_payload(self.base,self.candidate):
            raise ValueError('review must inspect the actual previous candidate')
        if self.stage=='repair' and p!=dict(self.base,rejected_reply=self.candidate,review_issues=self.issues):
            raise ValueError('one targeted repair of actual rejected candidate required')
        raw=canonical_json(dict(spec['parameters'],messages=[dict(role='system',content=spec['policy']),
            dict(role='user',content=canonical_json(p))])).encode()
        if len(raw)>65536:raise ValueError('request oversized')
        return raw

    def validate_final(self,speech):
        self.validate();validate_receipt(speech)
        receipt=speech['review'];row=self.journal.read_result(receipt['request_sha256'])
        if (row['status']!='complete' or row['purpose'] not in ('review-draft','review-repair')
                or row['value']!=receipt['proposal'] or row['candidate_sha256']!=receipt['candidate_sha256']
                or row['context_sha256']!=receipt['context_sha256']
                or receipt['repaired']!=(row['purpose']=='review-repair')):
            raise ValueError('final speech lacks its actual accepted review')

    def invoke(self,task):
        raw=self._body(task);index=self.journal.next;purpose=self.stage;turn=self.turn
        digest=sha256(raw).hexdigest();self.journal.claim(digest)
        write_once(self.request.output/f'{index+1:02d}.request.json',json.loads(raw))
        sent=False;started=monotonic()
        def opener(request,*,timeout):
            nonlocal sent
            if (sent or self._body(task)!=raw or request.data!=raw or timeout!=30 or request.get_method()!='POST'
                    or request.full_url!='https://api.deepseek.com/chat/completions'):
                raise ValueError('one-shot current approved request required')
            sent=True;return urlopen(request,timeout=timeout)
        if self.transport_factory is None:
            from dynamic_subject_agent.local_product import _WindowsLabResolver
            transport=DeepSeekUrlLibTransport(credential_resolver=_WindowsLabResolver(),_opener=opener)
        else:transport=self.transport_factory(opener)
        observed=_ObservedTransport(transport)
        ref=CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,key_id=DEEPSEEK_CREDENTIAL_KEY_ID)
        value=None;code=None;status='complete';candidate_sha=None;ctx=None
        try:
            if purpose in ('draft','repair'):
                value=_post_text_reply_content(observed,ref,raw,max_output_tokens=4096)
                from dynamic_subject_agent.original_whole_chat import validate_whole_reply
                validate_whole_reply(dict(reply_text=value,language='zh'))
                if purpose=='draft':self.base=json.loads(canonical_json(task.payload))
                self.candidate=value;self.stage='review-'+purpose
            else:
                value=_post_json_reply_content(observed,ref,raw,max_output_tokens=4096,
                    require_complete=True,discard_reasoning=True,safe_diagnostics=True)
                if purpose=='selection':self.stage='draft'
                else:
                    gate=adjudicate_review(task.payload,value,request_digest=digest)
                    candidate_sha=sha256(self.candidate.encode()).hexdigest();ctx=context_digest(self.base)
                    if gate.status=='candidate':self.turn+=1;self.stage='selection'
                    elif purpose=='review-draft' and value['verdict']=='unsupported':
                        self.issues=value['issues'];self.stage='repair'
                    else:self.stage='stopped'
        except Exception as exc:
            from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
            code='character-credential-unavailable' if isinstance(exc,CharacterCredentialUnavailable) else getattr(exc,'diagnostic_code','reviewed-conversation-delivery-failed')
            status='unavailable' if isinstance(exc,CharacterCredentialUnavailable) else 'unknown' if code in ('transport-timeout','transport-delivery-ambiguous') else 'failed-closed'
            self.stage='stopped'
        row=dict(index=index,turn=turn,purpose=purpose,request_sha256=digest,status=status,error_code=code,value=value,
            candidate_sha256=candidate_sha,context_sha256=ctx,next_turn=self.turn,next_stage=self.stage,
            elapsed_seconds=round(monotonic()-started,3),
            **{k:observed.row[k] for k in ('model','usage','finish_reason','final_content')})
        self.journal.record(digest,row);write_once(self.request.output/f'{index+1:02d}.result.json',row)
        if code:
            self.journal.stop(code);raise ModelGatewayFailure(code)
        return ModelResult(task.kind,value)
