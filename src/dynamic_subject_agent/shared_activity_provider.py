"""One approved HTTPS request, from a freshly rebuilt canonical projection."""
from hashlib import sha256
from time import perf_counter

from dynamic_subject_agent.cognition import CredentialRef
from dynamic_subject_agent.deepseek import (DeepSeekTransport, _post_json_reply_content, DeepSeekResponseDiagnosticFailure,
    DEEPSEEK_ENDPOINT, DEEPSEEK_TIMEOUT_SECONDS, DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID)
from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
from dynamic_subject_agent.first_life_reply_live_provider import _ObservedTransport
from dynamic_subject_agent.model_gateway import ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelTaskKind, ModelResult, ModelGatewayFailure
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.original_whole_chat import validate_whole_reply
from dynamic_subject_agent.shared_activity import SharedExperience, adjudicate_choice, digest
from dynamic_subject_agent.first_life import validate_plan
from dynamic_subject_agent.shared_activity_live import SharedActivityDelivery
from dynamic_subject_agent.shared_activity_remote_preview import shared_remote_request_preview


class DeepSeekSharedActivityAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities('deepseek', 'deepseek-flash', False, (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self, *, transport, credential_ref, delivery, observations=None):
        if (not isinstance(transport, DeepSeekTransport) or type(credential_ref) is not CredentialRef
            or type(delivery) is not SharedActivityDelivery
            or DEEPSEEK_ENDPOINT != 'https://api.deepseek.com/chat/completions' or DEEPSEEK_TIMEOUT_SECONDS != 30
            or (credential_ref.backend_id, credential_ref.key_id) != (DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID)):
            raise ValueError('exact approved shared transport, slot and delivery required')
        delivery.grant.validate()
        self.transport, self.credential_ref, self.delivery = transport, credential_ref, delivery
        self.observations = [] if observations is None else observations

    def invoke(self, task):
        started = perf_counter()
        row = dict(task_kind=getattr(task.kind, 'value', ''), purpose=getattr(task.kind, 'value', ''), status='failed-closed')
        observed = None
        value = None
        code = None
        try:
            actual = self.delivery.consume(task)
            request = shared_remote_request_preview(actual, technical_variant=self.delivery.grant.technical_variant)
            wire = canonical_json(request['body']).encode()
            if sha256(wire).hexdigest() != request['wire_sha256']:
                raise ValueError('exact reviewed wire changed')
            row.update(request_digest=digest(actual.payload), wire_sha256=request['wire_sha256'])
        except Exception:
            try:
                self.delivery.record('failed-closed')
            except Exception:
                pass
            raise ModelGatewayFailure('delivery-unverified') from None
        try:
            observed = _ObservedTransport(self.transport)
            value = _post_json_reply_content(observed, self.credential_ref, wire, max_output_tokens=4096,
                require_complete=True, discard_reasoning=True, safe_diagnostics=True)
            if actual.kind is ModelTaskKind.SHARED_ACTIVITY_REPLY:
                validate_whole_reply(value)
            else:
                payload = actual.payload['payload']
                source = None if payload['shared_experience'] is None else SharedExperience(1, 1, payload['shared_experience']['quote'])
                current = None if payload['current_plan'] is None else validate_plan(payload['current_plan'])
                adjudicate_choice(value, phase=payload['current_activity']['phase'], current_plan=current, source=source, plan_dependencies=())
            row['status'] = 'complete'
        except CharacterCredentialUnavailable:
            code, row['status'] = 'character-credential-unavailable', 'unavailable'
        except DeepSeekResponseDiagnosticFailure as error:
            code = error.diagnostic_code
            row['status'] = 'unknown' if code in ('transport-timeout', 'transport-delivery-ambiguous') else 'failed-closed'
        except Exception:
            code = 'structured-choice-invalid'
        try:
            self.delivery.record(row['status'], value if code is None else None)
        except Exception:
            code, row['status'] = 'audit-failed', 'failed-closed'
        if code is not None:
            row['error_code'] = code
        if observed is not None:
            row.update({key: observed.row[key] for key in ('model', 'usage', 'finish_reason')})
        row['elapsed_seconds'] = max(0.0, perf_counter() - started)
        self.observations.append(row)
        if code is not None:
            raise ModelGatewayFailure(code)
        return ModelResult(actual.kind, value)
