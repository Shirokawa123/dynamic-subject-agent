"""Wire adapter for the separately activated character dialogue experiment."""
import json

from dynamic_subject_agent.cognition import ProviderFailure, ProviderFailureCode

from dynamic_subject_agent.character_dialogue import DialogueProjection, DialogueReply, POLICY
from dynamic_subject_agent.deepseek import (
    DEEPSEEK_MODEL, DEEPSEEK_PROVIDER_AUTHORITY_ID,
    DeepSeekLivingMemoryProvider, _post_identity_reply_content,
)
from dynamic_subject_agent.model_gateway import (
    ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelTaskKind, ModelResult, ModelGatewayFailure,
)


class CharacterCredentialUnavailable(ProviderFailure):
    def __init__(self):
        super().__init__(ProviderFailureCode.UNAVAILABLE)


class OfflineCharacterDialogueAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities("offline-lab", "fixture", True, (StructuredOutputMode.JSON_OBJECT,))

    def invoke(self, task):
        if task.kind is not ModelTaskKind.CHARACTER_DIALOGUE_REPLY or type(task.payload) is not DialogueProjection:
            raise ValueError("unsupported task")
        task.payload.payload()
        return ModelResult(task.kind, DialogueReply("离线联调已收到消息。这是固定测试回声，不是纱雾的生成回复。"))


class DeepSeekCharacterDialogueAdapter(ProviderAdapter):
    def __init__(self, *, transport, credential_ref):
        self._base = DeepSeekLivingMemoryProvider(transport=transport, credential_ref=credential_ref)
        self.capabilities = ProviderCapabilities(DEEPSEEK_PROVIDER_AUTHORITY_ID, DEEPSEEK_MODEL,
                                                 False, (StructuredOutputMode.JSON_OBJECT,))

    @staticmethod
    def outbound_bytes(projection: DialogueProjection) -> bytes:
        if type(projection) is not DialogueProjection:
            raise TypeError("typed dialogue projection required")
        body = dict(model=DEEPSEEK_MODEL, messages=[dict(role="system", content=POLICY),
                    dict(role="user", content=json.dumps(projection.payload(), ensure_ascii=False,
                         sort_keys=True, separators=(",", ":")))],
                    thinking={"type": "disabled"}, response_format={"type": "json_object"},
                    max_tokens=400, temperature=0.7, stream=False)
        return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

    def invoke(self, task):
        if task.kind is not ModelTaskKind.CHARACTER_DIALOGUE_REPLY:
            raise ValueError("unsupported task")
        try:
            value = _post_identity_reply_content(self._base._transport, self._base._credential_ref,
                                                 self.outbound_bytes(task.payload))
        except CharacterCredentialUnavailable:
            raise ModelGatewayFailure("character-credential-unavailable") from None
        if set(value) != {"reply_text", "language"}:
            raise ValueError("invalid dialogue result fields")
        return ModelResult(task.kind, DialogueReply(**value))
