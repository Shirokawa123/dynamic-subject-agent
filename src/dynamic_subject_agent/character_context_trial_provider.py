"""Exact frozen DeepSeek wire requests for the separately approved trial."""
from dataclasses import asdict
from hashlib import sha256

from dynamic_subject_agent.character_context_trial import canonical_json, TRIAL_POLICY, TRIAL_MODEL
from dynamic_subject_agent.character_reply_candidate import CharacterReplyProjection
from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
from dynamic_subject_agent.deepseek import DEEPSEEK_PROVIDER_AUTHORITY_ID, _post_json_reply_content, _TRANSPORT_MAX_REQUEST_BYTES
from dynamic_subject_agent.model_gateway import ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelTaskKind, ModelResult, ModelGatewayFailure


class DeepSeekCharacterContextAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities(DEEPSEEK_PROVIDER_AUTHORITY_ID, TRIAL_MODEL, False,
                                         (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self, *, transport, credential_ref, allowed_outbound_digests):
        self._transport, self._credential_ref = transport, credential_ref
        self._allowed = frozenset(allowed_outbound_digests)

    @staticmethod
    def outbound_bytes(projection):
        if type(projection) is not CharacterReplyProjection or projection.policy != TRIAL_POLICY:
            raise ValueError("typed exact trial projection required")
        body = dict(model=TRIAL_MODEL,
            messages=[dict(role="system", content=TRIAL_POLICY), dict(role="user", content=canonical_json(asdict(projection)))],
            thinking={"type": "disabled"}, response_format={"type": "json_object"},
            max_tokens=600, temperature=0.3, stream=False)
        wire = canonical_json(body).encode()
        if len(wire) > _TRANSPORT_MAX_REQUEST_BYTES:
            raise ValueError("trial-outbound-too-large")
        return wire

    def invoke(self, task):
        if task.kind is not ModelTaskKind.CHARACTER_CONTEXT_REPLY:
            raise ValueError("unsupported trial task")
        wire = self.outbound_bytes(task.payload)
        if sha256(wire).hexdigest() not in self._allowed:
            raise ValueError("request not in frozen trial")
        try:
            value = _post_json_reply_content(self._transport, self._credential_ref, wire,
                                            max_output_tokens=600, require_complete=True)
        except CharacterCredentialUnavailable:
            raise ModelGatewayFailure("character-credential-unavailable") from None
        return ModelResult(task.kind, value)
