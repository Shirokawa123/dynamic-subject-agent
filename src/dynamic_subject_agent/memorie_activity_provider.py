"""Exact M012 HTTPS transport behind same-Timeline one-use reconstruction."""
from hashlib import sha256
from urllib.request import urlopen
from dynamic_subject_agent.cognition import CredentialRef
from dynamic_subject_agent.deepseek import (DeepSeekTransport,_post_json_reply_content,_post_text_reply_content,
    DeepSeekResponseDiagnosticFailure,DEEPSEEK_ENDPOINT,DEEPSEEK_TIMEOUT_SECONDS,DEEPSEEK_CREDENTIAL_BACKEND_ID,DEEPSEEK_CREDENTIAL_KEY_ID)
from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
from dynamic_subject_agent.first_life_reply_live_provider import _ObservedTransport
from dynamic_subject_agent.model_gateway import ProviderAdapter,ProviderCapabilities,StructuredOutputMode,ModelResult,ModelGatewayFailure
from dynamic_subject_agent.memorie_activity_live import NativeActivityDelivery,KINDS,wire
from dynamic_subject_agent.original_whole_chat import validate_whole_reply
from dynamic_subject_agent.shared_activity import SharedExperience,adjudicate_choice
from dynamic_subject_agent.first_life import validate_plan
from dynamic_subject_agent.living_activity import validate_share


def guarded_native_activity_opener(delivery):
    """Final check after Windows credential resolution, before network I/O."""
    def opening(request,*,timeout):
        raw=delivery.check_before_send()
        if request.full_url!='https://api.deepseek.com/chat/completions' or request.get_method()!='POST' or request.data!=raw or timeout!=30:
            raise ValueError('approved final HTTPS request changed')
        return urlopen(request,timeout=timeout)
    return opening


class DeepSeekNativeActivityAdapter(ProviderAdapter):
    capabilities=ProviderCapabilities('deepseek','deepseek-flash',False,(StructuredOutputMode.JSON_OBJECT,StructuredOutputMode.TEXT))
    def __init__(self,*,transport,credential_ref,delivery,observations=None):
        if (not isinstance(transport,DeepSeekTransport) or type(delivery) is not NativeActivityDelivery
            or type(credential_ref) is not CredentialRef or DEEPSEEK_ENDPOINT!='https://api.deepseek.com/chat/completions'
            or DEEPSEEK_TIMEOUT_SECONDS!=30 or (credential_ref.backend_id,credential_ref.key_id)!=(DEEPSEEK_CREDENTIAL_BACKEND_ID,DEEPSEEK_CREDENTIAL_KEY_ID)):
            raise ValueError('exact approved existing transport and Windows slot required')
        delivery.grant.validate()
        self.transport,self.credential_ref,self.delivery=transport,credential_ref,delivery
        self.observations=[] if observations is None else observations

    def invoke(self,task):
        try:actual=self.delivery.consume(task);raw=wire(actual)
        except Exception:
            try:self.delivery.record('failed-closed')
            except Exception:pass
            raise ModelGatewayFailure('delivery-unverified') from None
        delivery=self.delivery;transport=self.transport
        class ScopedTransport(DeepSeekTransport):
            def post_json(self,**kwargs):
                delivery.grant.validate()
                if (kwargs.get('endpoint')!='https://api.deepseek.com/chat/completions' or kwargs.get('timeout_seconds')!=30
                    or kwargs.get('body')!=raw):
                    raise ValueError('approved HTTPS destination changed')
                delivery.check_before_send(actual)
                return transport.post_json(**kwargs)
        observed=_ObservedTransport(ScopedTransport());value=None;code=None;status='failed-closed'
        try:
            purpose=KINDS[actual.kind]
            if purpose=='reply':
                value=dict(reply_text=_post_text_reply_content(observed,self.credential_ref,raw,max_output_tokens=4096),language='zh')
                validate_whole_reply(value)
                from dynamic_subject_agent.memorie_native import validate_reply
                validate_reply(value['reply_text'],actual.payload['payload']['interaction'])
            else:
                value=_post_json_reply_content(observed,self.credential_ref,raw,max_output_tokens=4096,require_complete=True,discard_reasoning=True,safe_diagnostics=True)
                if purpose=='share':
                    validate_share(value)
                    if len(value['reply_text'])>120:raise ValueError('native share too long')
                else:
                    p=actual.payload['payload'];source=p['experience']
                    adjudicate_choice(value,phase=p['current_activity']['phase'],current_plan=None if p['current_plan'] is None else validate_plan(p['current_plan']),
                        source=None if source is None else SharedExperience(1,1,source['quote']),plan_dependencies=())
            status='complete'
        except CharacterCredentialUnavailable:code,status='character-credential-unavailable','unavailable'
        except DeepSeekResponseDiagnosticFailure as error:
            code=error.diagnostic_code;status='unknown' if code in ('transport-timeout','transport-delivery-ambiguous') else 'failed-closed'
        except Exception:code='expression-invalid' if KINDS[actual.kind]=='reply' else 'structured-choice-invalid'
        try:self.delivery.record(status,value if code is None else None)
        except Exception:code,status='audit-failed','failed-closed'
        self.observations.append(dict(purpose=KINDS[actual.kind],status=status,error_code=code,wire_sha256=sha256(raw).hexdigest(),
            **{k:observed.row[k] for k in ('model','usage','finish_reason')}))
        if code:raise ModelGatewayFailure(code)
        return ModelResult(actual.kind,value)
