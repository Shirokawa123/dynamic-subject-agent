"""New evidence-extraction wire purpose; no existing task gets these fields."""
import json
from dynamic_subject_agent.evidence_extraction import EvidenceProjection, EXTRACTION_POLICY
from dynamic_subject_agent.model_gateway import (
    ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelTaskKind, ModelResult, ModelGatewayFailure,
)
from dynamic_subject_agent.deepseek import (
    DEEPSEEK_MODEL, DEEPSEEK_PROVIDER_AUTHORITY_ID, DeepSeekLivingMemoryProvider, _post_json_reply_content,
)
from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable


class OfflineEvidenceAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities("offline-evidence", "fixture", True, (StructuredOutputMode.JSON_OBJECT,))

    def invoke(self, task):
        if task.kind is not ModelTaskKind.CHARACTER_EVIDENCE_EXTRACTION or type(task.payload) is not EvidenceProjection:
            raise ValueError("unsupported task")
        task.payload.payload()
        return ModelResult(task.kind, {"candidates": [], "language": "zh"})


class DeepSeekEvidenceAdapter(ProviderAdapter):
    def __init__(self, *, transport, credential_ref):
        self._base = DeepSeekLivingMemoryProvider(transport=transport, credential_ref=credential_ref)
        self.capabilities = ProviderCapabilities(DEEPSEEK_PROVIDER_AUTHORITY_ID, DEEPSEEK_MODEL,
                                                 False, (StructuredOutputMode.JSON_OBJECT,))

    @staticmethod
    def outbound_bytes(projection):
        if type(projection) is not EvidenceProjection:
            raise TypeError("typed evidence projection required")
        body = dict(model=DEEPSEEK_MODEL, messages=[dict(role="system", content=EXTRACTION_POLICY),
                    dict(role="user", content=json.dumps(projection.payload(), ensure_ascii=False,
                                                       sort_keys=True, separators=(",", ":")))],
                    max_tokens=2048, temperature=0.0, thinking={"type": "disabled"},
                    response_format={"type": "json_object"}, stream=False)
        return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

    def invoke(self, task):
        if task.kind is not ModelTaskKind.CHARACTER_EVIDENCE_EXTRACTION:
            raise ValueError("unsupported task")
        try:
            result = _post_json_reply_content(self._base._transport, self._base._credential_ref,
                self.outbound_bytes(task.payload), max_output_tokens=2048, require_complete=True)
        except CharacterCredentialUnavailable:
            raise ModelGatewayFailure("character-credential-unavailable") from None
        return ModelResult(task.kind, result)
