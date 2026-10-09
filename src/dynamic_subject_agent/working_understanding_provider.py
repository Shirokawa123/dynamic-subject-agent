"""Approved S146 HTTPS only after exact one-use delivery consumption."""
from hashlib import sha256
from time import perf_counter

from dynamic_subject_agent.cognition import CredentialRef
from dynamic_subject_agent.deepseek import (DeepSeekTransport,DeepSeekResponseDiagnosticFailure,
    _post_json_reply_content,_post_text_reply_content,DEEPSEEK_ENDPOINT,DEEPSEEK_TIMEOUT_SECONDS,
    DEEPSEEK_CREDENTIAL_BACKEND_ID,DEEPSEEK_CREDENTIAL_KEY_ID)
from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
from dynamic_subject_agent.first_life_reply_live_provider import _ObservedTransport
from dynamic_subject_agent.model_gateway import (ProviderAdapter,ProviderCapabilities,StructuredOutputMode,
    ModelTaskKind,ModelResult,ModelGatewayFailure)
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.original_whole_chat import validate_whole_reply
from dynamic_subject_agent.first_life import validate_plan
from dynamic_subject_agent.shared_activity import digest,adjudicate_choice
from dynamic_subject_agent.working_understanding import validate_form,working_choice_for_adjudication
from dynamic_subject_agent.working_understanding_live import WorkingUnderstandingDelivery
from dynamic_subject_agent.working_understanding_remote_preview import working_remote_request_preview


class WorkingUnderstandingObservations(list):
    def append(self,row):
        fields=('task_kind','purpose','status','request_digest','wire_sha256','error_code',
            'model','usage','finish_reason','elapsed_seconds')
        super().append({key:row[key] for key in fields if key in row})


class DeepSeekWorkingUnderstandingAdapter(ProviderAdapter):
    capabilities=ProviderCapabilities('deepseek','deepseek-flash',False,(StructuredOutputMode.JSON_OBJECT,StructuredOutputMode.TEXT))

    def __init__(self, *, transport, credential_ref, delivery, observations=None):
        if (not isinstance(transport,DeepSeekTransport) or type(credential_ref) is not CredentialRef
            or type(delivery) is not WorkingUnderstandingDelivery
            or DEEPSEEK_ENDPOINT!='https://api.deepseek.com/chat/completions' or DEEPSEEK_TIMEOUT_SECONDS!=30
            or (credential_ref.backend_id,credential_ref.key_id)!=(DEEPSEEK_CREDENTIAL_BACKEND_ID,DEEPSEEK_CREDENTIAL_KEY_ID)):
            raise ValueError('exact S146 approved transport slot and delivery required')
        delivery.grant.validate()
        self.transport,self.credential_ref,self.delivery=transport,credential_ref,delivery
        self.observations=WorkingUnderstandingObservations() if observations is None else observations

    def invoke(self,task):
        started=perf_counter()
        kind=getattr(task,'kind',None)
        row=dict(task_kind=getattr(kind,'value',''),purpose=getattr(kind,'value',''),status='failed-closed')
        observed=value=None
        code=None
        try:
            actual=self.delivery.consume(task)
            request=working_remote_request_preview(actual)
            wire=canonical_json(request['body']).encode()
            if sha256(wire).hexdigest()!=request['wire_sha256']:
                raise ValueError('exact working wire changed')
            row.update(request_digest=digest(actual.payload),wire_sha256=request['wire_sha256'])
        except Exception:
            try:
                self.delivery.record('failed-closed')
            except Exception:
                pass
            raise ModelGatewayFailure('delivery-unverified') from None
        try:
            observed=_ObservedTransport(self.transport)
            if actual.kind is ModelTaskKind.WORKING_ACTIVITY_REPLY:
                value=dict(reply_text=_post_text_reply_content(observed,self.credential_ref,wire,max_output_tokens=4096),language='zh')
                validate_whole_reply(value)
            else:
                value=_post_json_reply_content(observed,self.credential_ref,wire,max_output_tokens=4096,
                    require_complete=True,discard_reasoning=True,safe_diagnostics=True)
                payload=actual.payload['payload']
                if actual.kind is ModelTaskKind.WORKING_UNDERSTANDING_FORM:
                    validate_form(value,payload['activity_result'] is not None)
                else:
                    choice,_=working_choice_for_adjudication(value,has_understanding=payload['working_understanding'] is not None)
                    current=None if payload['current_plan'] is None else validate_plan(payload['current_plan'])
                    phase=payload['current_activity']['phase']
                    if current is None and phase!='unstarted':
                        phase='rework'
                    adjudicate_choice(choice,phase=phase,current_plan=current,source=None,plan_dependencies=())
            row['status']='complete'
        except CharacterCredentialUnavailable:
            code,row['status']='character-credential-unavailable','unavailable'
        except DeepSeekResponseDiagnosticFailure as error:
            code=error.diagnostic_code
            row['status']='unknown' if code in ('transport-timeout','transport-delivery-ambiguous') else 'failed-closed'
        except Exception:
            code='expression-invalid' if actual.kind is ModelTaskKind.WORKING_ACTIVITY_REPLY else 'structured-choice-invalid'
        try:
            self.delivery.record(row['status'],value if code is None else None)
        except Exception:
            code,row['status']='audit-failed','failed-closed'
        if code is not None:
            row['error_code']=code
        if observed is not None:
            row.update({key:observed.row[key] for key in ('model','usage','finish_reason')})
        row['elapsed_seconds']=max(0.0,perf_counter()-started)
        self.observations.append(row)
        if code is not None:
            raise ModelGatewayFailure(code)
        return ModelResult(actual.kind,value)
