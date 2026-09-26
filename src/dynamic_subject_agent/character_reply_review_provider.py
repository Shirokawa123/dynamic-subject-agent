"""DeepSeek review adapter, allowed only exact newly approved frozen bytes."""
from dataclasses import asdict
from hashlib import sha256

from dynamic_subject_agent.character_reply_review import validate_projection, REVIEW_POLICY
from dynamic_subject_agent.character_reply_review_trial import REVIEW_MODEL, review_settings
from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
from dynamic_subject_agent.deepseek import DEEPSEEK_PROVIDER_AUTHORITY_ID, _post_json_reply_content, _TRANSPORT_MAX_REQUEST_BYTES
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelTaskKind, ModelResult, ModelGatewayFailure


class DeepSeekCharacterReplyReviewAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities(DEEPSEEK_PROVIDER_AUTHORITY_ID, REVIEW_MODEL, False,
                                         (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self, *, transport, credential_ref, allowed_outbound_digests, review_profile="standard"):
        _, self._generation = review_settings(review_profile)
        self._review_profile = review_profile
        self._transport, self._credential_ref = transport, credential_ref
        self._allowed = frozenset(allowed_outbound_digests)

    @staticmethod
    def outbound_bytes(projection, *, review_profile="standard"):
        validate_projection(projection)
        _, generation = review_settings(review_profile)
        body = dict(model=REVIEW_MODEL,
            messages=[dict(role="system", content=REVIEW_POLICY), dict(role="user", content=canonical_json(asdict(projection)))],
            **generation)
        wire = canonical_json(body).encode()
        if len(wire) > _TRANSPORT_MAX_REQUEST_BYTES:
            raise ValueError("review-outbound-too-large")
        return wire

    def invoke(self, task):
        if task.kind is not ModelTaskKind.CHARACTER_REPLY_REVIEW:
            raise ValueError("unsupported review task")
        wire = self.outbound_bytes(task.payload, review_profile=self._review_profile)
        if sha256(wire).hexdigest() not in self._allowed:
            raise ValueError("request not in frozen review plan")
        try:
            value = _post_json_reply_content(self._transport, self._credential_ref, wire,
                                            max_output_tokens=self._generation["max_tokens"], require_complete=True,
                                            discard_reasoning=self._review_profile == "thinking-high")
        except CharacterCredentialUnavailable:
            raise ModelGatewayFailure("character-credential-unavailable") from None
        return ModelResult(task.kind, value)
