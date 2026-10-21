"""Concrete HTTPS Adapter; one text request, no retries, no reasoning retained."""
from dynamic_subject_agent.model_gateway import (
    ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelTaskKind, ModelResult, ModelGatewayFailure,
)
from dynamic_subject_agent.deepseek import _post_text_reply_content, DeepSeekResponseDiagnosticFailure
from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
from dynamic_subject_agent.memorie_companion_contract import wire, validate_reply


class DeepSeekMemorieAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities('deepseek', 'deepseek-flash', False, (StructuredOutputMode.TEXT,))

    def __init__(self, *, transport, credential_ref):
        self.transport, self.credential_ref = transport, credential_ref

    def invoke(self, task):
        native = task.kind is ModelTaskKind.MEMORIE_NATIVE_REPLY
        if native:
            from dynamic_subject_agent.memorie_native import wire as native_wire, validate_reply as native_reply
        if task.kind not in (ModelTaskKind.MEMORIE_COMPANION_REPLY, ModelTaskKind.MEMORIE_NATIVE_REPLY):
            raise ValueError('unsupported Memorie task')
        body = native_wire(task.payload) if native else wire(task.payload)
        try:
            value = _post_text_reply_content(self.transport, self.credential_ref, body, max_output_tokens=4096)
        except CharacterCredentialUnavailable:
            raise ModelGatewayFailure('character-credential-unavailable') from None
        except DeepSeekResponseDiagnosticFailure as error:
            raise ModelGatewayFailure(error.diagnostic_code) from None
        try:
            if native:
                import json
                text = native_reply(value, json.loads(task.payload.payload_json)['interaction'])
            else:
                text = validate_reply(value)
        except ValueError:
            raise ModelGatewayFailure('expression-invalid') from None
        return ModelResult(task.kind, text)
