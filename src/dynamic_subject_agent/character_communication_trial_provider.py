"""Exact frozen planning and journal-derived expression delivery for one trial."""
from dataclasses import asdict
from hashlib import sha256

from dynamic_subject_agent.character_communication_plan import (
    CommunicationPlanProjection, CommunicationExpressionProjection, PLAN_POLICY, EXPRESSION_POLICY, _projection_digest, _validate_projection,
)
from dynamic_subject_agent.character_communication_trial import (
    CommunicationTrialExpressionRequest, frozen_context, validate_attempt, load_expression_request, stage_digest,
)
from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
from dynamic_subject_agent.deepseek import (
    DEEPSEEK_ENDPOINT, DEEPSEEK_TIMEOUT_SECONDS, DEEPSEEK_PROVIDER_AUTHORITY_ID, _ACCEPTED_RESPONSE_MODELS,
    _TRANSPORT_MAX_REQUEST_BYTES, _post_json_reply_content, DeepSeekResponseDiagnosticFailure,
)
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import (
    ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelTaskKind, ModelResult, ModelGatewayFailure,
)


def communication_protocol(expression_profile="standard"):
    if expression_profile not in ("standard", "thinking-high"):
        raise ValueError("unsupported communication expression profile")
    protocol = dict(endpoint=DEEPSEEK_ENDPOINT, model="deepseek-flash", timeout_seconds=DEEPSEEK_TIMEOUT_SECONDS,
        accepted_response_models=list(_ACCEPTED_RESPONSE_MODELS),
        planning=dict(max_tokens=4096, thinking={"type": "enabled"}, reasoning_effort="high",
                      response_format={"type": "json_object"}, stream=False),
        expression=dict(max_tokens=600, thinking={"type": "disabled"}, temperature=0.3,
                        response_format={"type": "json_object"}, stream=False))
    if expression_profile == "thinking-high":
        protocol["expression"] = dict(max_tokens=4096, thinking={"type": "enabled"}, reasoning_effort="high",
                                      response_format={"type": "json_object"}, stream=False)
    return protocol


def _wire(projection, policy, stage, expression_profile="standard"):
    protocol = communication_protocol(expression_profile)
    body = dict(model=protocol["model"], messages=[dict(role="system", content=policy),
        dict(role="user", content=canonical_json(asdict(projection)))], **protocol[stage])
    wire = canonical_json(body).encode()
    if len(wire) > _TRANSPORT_MAX_REQUEST_BYTES:
        raise ValueError("communication outbound too large")
    return wire


class DeepSeekCommunicationTrialAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities(DEEPSEEK_PROVIDER_AUTHORITY_ID, "deepseek-flash", False, (StructuredOutputMode.JSON_OBJECT,))
    _plan_version = "character-communication-trial-1"
    _planning_type = CommunicationPlanProjection

    def __init__(self, plan, *, run_root, transport, credential_ref):
        if plan.payload["version"] != self._plan_version: raise ValueError("matching communication plan kind required")
        self._expression_profile = plan.payload.get("expression_profile", "standard")
        if plan.payload["protocol"] != communication_protocol(self._expression_profile):
            raise ValueError("current communication protocol required")
        self._plan, self._root, self._transport, self._credential_ref = plan, run_root, transport, credential_ref
        self._rows = {row["request_digest"]: row for row in plan.payload["requests"]}
        self._sent = set()

    @staticmethod
    def planning_wire(projection):
        _validate_projection(projection)
        return _wire(projection, PLAN_POLICY, "planning")

    @staticmethod
    def expression_wire(projection, *, expression_profile="standard"):
        if type(projection) is not CommunicationExpressionProjection or projection.policy != EXPRESSION_POLICY:
            raise ValueError("typed communication expression required")
        return _wire(projection, EXPRESSION_POLICY, "expression", expression_profile)

    def _bound_expression_wire(self, projection):
        return self.expression_wire(projection, expression_profile=self._expression_profile)

    def invoke(self, task):
        if task.kind is ModelTaskKind.CHARACTER_COMMUNICATION_PLAN and type(task.payload) is self._planning_type:
            stage = "planning"
            row = self._rows.get(_projection_digest(task.payload))
            if row is None or task.payload != frozen_context(row):
                raise ValueError("planning request not in frozen plan")
            wire = self.planning_wire(task.payload)
            if sha256(wire).hexdigest() != row["outbound_digest"]:
                raise ValueError("planning wire not frozen")
        elif task.kind is ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION and type(task.payload) is CommunicationTrialExpressionRequest:
            stage = "expression"
            row = self._rows.get(task.payload.context_digest)
            if row is None:
                raise ValueError("unknown expression binding")
            projection, request = load_expression_request(self._root, self._plan, row, self._bound_expression_wire)
            wire = self._bound_expression_wire(projection)
            if sha256(wire).hexdigest() != request["outbound_digest"]:
                raise ValueError("expression wire not derived")
        else:
            raise ValueError("unsupported communication trial task")
        attempt_digest = validate_attempt(self._root, self._plan, row, stage)
        if (attempt_digest in self._sent or len(self._sent) >= 12
                or (self._root / (stage_digest(row, stage) + ".result.json")).exists()):
            raise ValueError("communication stage already delivered")
        self._sent.add(attempt_digest)  # No retry even if the transport raises.
        try:
            value = _post_json_reply_content(self._transport, self._credential_ref, wire,
                max_output_tokens=4096 if stage == "planning" or self._expression_profile == "thinking-high" else 600, require_complete=True,
                discard_reasoning=stage == "planning" or self._expression_profile == "thinking-high", safe_diagnostics=True)
        except CharacterCredentialUnavailable:
            raise ModelGatewayFailure("character-credential-unavailable") from None
        except DeepSeekResponseDiagnosticFailure as failure:
            raise ModelGatewayFailure(failure.diagnostic_code) from None
        return ModelResult(task.kind, value)


class DeepSeekPersonalityTrialAdapter(DeepSeekCommunicationTrialAdapter):
    """Explicit new use; the original Adapter never accepts this plan or type."""
    from dynamic_subject_agent.character_personality import CharacterPlanningEnvelope as _planning_type
    _plan_version = "character-personality-communication-trial-1"

    def __init__(self, plan, *, sidecar_path, run_root, transport, credential_ref):
        from dynamic_subject_agent.character_personality import PERSONALITY_POLICY
        if (plan.payload.get("expression_profile") != "thinking-high" or plan.payload.get("personality_policy") != PERSONALITY_POLICY
                or plan.payload.get("derivation") != "personality-derive-1"):
            raise ValueError("exact personality policy and configuration required")
        self._sidecar_path = sidecar_path
        super().__init__(plan, run_root=run_root, transport=transport, credential_ref=credential_ref)

    @staticmethod
    def planning_wire(projection):
        from dynamic_subject_agent.character_personality import CharacterPlanningEnvelope, frozen_personality_planning, PERSONALITY_POLICY
        if type(projection) is not CharacterPlanningEnvelope: raise ValueError("typed personality planning required")
        frozen_personality_planning(asdict(projection))
        return _wire(projection, PERSONALITY_POLICY + projection.conversation.policy, "planning", "thinking-high")

    @staticmethod
    def expression_wire(projection, *, expression_profile="thinking-high"):
        from dynamic_subject_agent.character_personality import CharacterExpressionEnvelope, PERSONALITY_POLICY, _bounded_envelope
        if (type(projection) is not CharacterExpressionEnvelope or expression_profile != "thinking-high"
                or projection.policy != PERSONALITY_POLICY or projection.conversation.policy != EXPRESSION_POLICY):
            raise ValueError("typed personality expression required")
        _bounded_envelope(projection)
        return _wire(projection, PERSONALITY_POLICY + projection.conversation.policy, "expression", "thinking-high")

    def invoke(self, task):
        try:
            with self._sidecar_path.open("rb") as stream: raw = stream.read(48001)
            if len(raw) > 48000 or sha256(raw).hexdigest() != self._plan.payload["personality_binding"]["sidecar_digest"]:
                raise ValueError("personality source changed")
        except Exception:
            raise ModelGatewayFailure("communication-task-failed") from None
        return super().invoke(task)
