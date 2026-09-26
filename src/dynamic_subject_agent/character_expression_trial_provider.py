"""One approved frozen expression set; high-thinking, no planning or raw audit."""
from dataclasses import asdict
from hashlib import sha256

from dynamic_subject_agent.character_communication_plan import CommunicationExpressionProjection, EXPRESSION_POLICY, _projection_digest
from dynamic_subject_agent.character_expression_trial import frozen_expression, verify_parent_fingerprints, validate_expression_attempt
from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
from dynamic_subject_agent.deepseek import (
    DEEPSEEK_ENDPOINT, DEEPSEEK_TIMEOUT_SECONDS, DEEPSEEK_PROVIDER_AUTHORITY_ID, _ACCEPTED_RESPONSE_MODELS,
    _TRANSPORT_MAX_REQUEST_BYTES, _post_json_reply_content, DeepSeekResponseDiagnosticFailure,
)
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelTaskKind, ModelResult, ModelGatewayFailure


def expression_thinking_protocol():
    return dict(endpoint=DEEPSEEK_ENDPOINT, model="deepseek-flash", timeout_seconds=DEEPSEEK_TIMEOUT_SECONDS,
        accepted_response_models=list(_ACCEPTED_RESPONSE_MODELS),
        generation=dict(max_tokens=4096, thinking={"type": "enabled"}, reasoning_effort="high",
                        response_format={"type": "json_object"}, stream=False))


class DeepSeekExpressionThinkingAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities(DEEPSEEK_PROVIDER_AUTHORITY_ID, "deepseek-flash", False, (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self, plan, *, run_root, parent_root, transport, credential_ref):
        if plan.payload["protocol"] != expression_thinking_protocol():
            raise ValueError("current expression protocol required")
        self._plan, self._root, self._parent_root = plan, run_root, parent_root
        self._transport, self._credential_ref = transport, credential_ref
        self._rows = {row["request_digest"]: row for row in plan.payload["requests"]}
        self._sent = set()

    @staticmethod
    def expression_wire(projection):
        if type(projection) is not CommunicationExpressionProjection or projection.policy != EXPRESSION_POLICY:
            raise ValueError("typed original expression required")
        protocol = expression_thinking_protocol()
        wire = canonical_json(dict(model=protocol["model"], messages=[dict(role="system", content=projection.policy),
            dict(role="user", content=canonical_json(asdict(projection)))], **protocol["generation"])).encode()
        if len(wire) > _TRANSPORT_MAX_REQUEST_BYTES: raise ValueError("expression outbound too large")
        return wire

    def invoke(self, task):
        if task.kind is not ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION or type(task.payload) is not CommunicationExpressionProjection:
            raise ValueError("expression-only trial task required")
        row = self._rows.get(_projection_digest(task.payload))
        if row is None or task.payload != frozen_expression(row): raise ValueError("expression not frozen")
        try: verify_parent_fingerprints(self._parent_root, self._plan)
        except Exception: raise ModelGatewayFailure("expression-parent-invalid") from None
        validate_expression_attempt(self._root, self._plan, row)
        wire = self.expression_wire(task.payload)
        if sha256(wire).hexdigest() != row["outbound_digest"] or row["request_digest"] in self._sent or len(self._sent) >= 6 or (self._root / (row["request_digest"] + ".result.json")).exists():
            raise ValueError("expression delivery not available")
        self._sent.add(row["request_digest"])
        try:
            value = _post_json_reply_content(self._transport, self._credential_ref, wire,
                max_output_tokens=4096, require_complete=True, discard_reasoning=True, safe_diagnostics=True)
        except CharacterCredentialUnavailable:
            raise ModelGatewayFailure("character-credential-unavailable") from None
        except DeepSeekResponseDiagnosticFailure as failure:
            raise ModelGatewayFailure(failure.diagnostic_code) from None
        return ModelResult(task.kind, value)
