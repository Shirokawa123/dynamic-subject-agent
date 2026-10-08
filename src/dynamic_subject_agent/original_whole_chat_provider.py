"""Exact S127 delivery, separate metadata ledger, and one-use claim tickets."""
from dataclasses import asdict
from copy import deepcopy
from hashlib import sha256
from time import perf_counter

from dynamic_subject_agent.deepseek import (DeepSeekTransport,
    _post_json_reply_content, DeepSeekResponseDiagnosticFailure, DEEPSEEK_ENDPOINT, DEEPSEEK_TIMEOUT_SECONDS)
from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
from dynamic_subject_agent.character_communication_trial_provider import communication_protocol
from dynamic_subject_agent.first_life_reply_live_provider import _ObservedTransport
from dynamic_subject_agent.cognition import CredentialRef
from dynamic_subject_agent.deepseek import DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import (ProviderAdapter, ProviderCapabilities, StructuredOutputMode,
    ModelTask, ModelTaskKind, ModelResult, ModelGatewayFailure)
from dynamic_subject_agent.original_whole_chat import (digest, validate_whole_envelope,
    validate_whole_projection, projection_for_contract, validate_whole_reply, contract_variant, policy_for_contract)
from dynamic_subject_agent.reviewed_character_chat import CharacterDialogueBasis
from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection

from dynamic_subject_agent.original_whole_chat_audit import OriginalWholeDelivery, PURPOSE


class OriginalWholeObservations(list):
    """Metadata whitelist; original character text never enters observations."""
    def append(self, row):
        super().append({key: row[key] for key in ("task_kind", "purpose", "stage", "status", "request_digest", "wire_sha256",
            "error_code", "model", "usage", "finish_reason", "elapsed_seconds") if key in row})


class DeepSeekOriginalWholeAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities("deepseek", "deepseek-flash", False, (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self, *, transport, credential_ref, delivery, envelope, observations=None):
        if (not isinstance(transport, DeepSeekTransport) or type(credential_ref) is not CredentialRef
            or type(delivery) is not OriginalWholeDelivery or DEEPSEEK_ENDPOINT != "https://api.deepseek.com/chat/completions"
            or DEEPSEEK_TIMEOUT_SECONDS != 30
            or (credential_ref.backend_id, credential_ref.key_id) != (DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID)):
            raise ValueError("approved whole transport, slot and delivery required")
        validate_whole_envelope(envelope, delivery.contract)
        if contract_variant(delivery.contract) in ('living-local', 'living-live', 'living-final-text-live'):
            raise ValueError('LOCAL living has no original-whole remote delivery authority')
        if contract_variant(delivery.contract) == "followup-legacy":
            raise ValueError("legacy followup qualification is receipt-only; no sender is available")
        self.transport, self.credential_ref, self.delivery, self.envelope = transport, credential_ref, delivery, envelope
        self.rows = observations if observations is not None else OriginalWholeObservations()

    def _wire(self, task):
        if type(task) is not ModelTask or task.kind is not ModelTaskKind.CHARACTER_ORIGINAL_WHOLE_REPLY:
            raise ValueError("exact original whole task required")
        projection = task.payload
        validate_whole_projection(projection)
        # Validation and projection assembly consume one local snapshot, so a
        # later mutation of the shared envelope cannot replace checked content.
        envelope = deepcopy(self.envelope)
        validate_whole_envelope(envelope, self.delivery.contract)
        identity = RuntimeIdentityProjection(envelope["runtime_asset"]["subject"]["name"],
            envelope["genesis_content"]["subject_identity"], envelope["genesis_content"]["canon_start"])
        expected = projection_for_contract(envelope, identity, projection.turn["current_message"],
            CharacterDialogueBasis("available", projection.turn["has_prior_committed_exchange"], projection.exchange),
            projection.turn["history_enabled"], self.delivery.contract)
        if projection != expected:
            raise ValueError("whole material differs from sealed approved selection")
        protocol = communication_protocol("thinking-high", "low")
        body = dict(model=protocol["model"], messages=[dict(role="system", content=policy_for_contract(self.delivery.contract)),
            dict(role="user", content=canonical_json(asdict(projection)))], **protocol["expression"])
        if (body["model"] != self.delivery.contract["model"] or body["max_tokens"] != 4096
            or body["reasoning_effort"] != "high" or body["thinking"] != {"type": "enabled"}):
            raise ValueError("whole approved protocol changed")
        wire = canonical_json(body).encode()
        if len(wire) > 65536:
            raise ValueError("whole wire oversized")
        return wire

    def invoke(self, task):
        # Consume even a malformed task: correcting it never issues a retry.
        try:
            self.delivery.consume(task)
            wire = self._wire(task)
        except Exception:
            raise ModelGatewayFailure("structured-choice-invalid") from None
        observed, started = _ObservedTransport(self.transport), perf_counter()
        row = dict(task_kind=task.kind.value, purpose=PURPOSE, stage="whole-reply", status="complete",
            request_digest=digest(asdict(task.payload)), wire_sha256=sha256(wire).hexdigest())
        try:
            value = _post_json_reply_content(observed, self.credential_ref, wire, max_output_tokens=4096,
                require_complete=True, discard_reasoning=True, safe_diagnostics=True)
            validate_whole_reply(value)
        except CharacterCredentialUnavailable:
            row["error_code"] = "character-credential-unavailable"
            row["status"] = "unavailable"
            raise ModelGatewayFailure(row["error_code"]) from None
        except DeepSeekResponseDiagnosticFailure as error:
            row["error_code"] = error.diagnostic_code
            row["status"] = "unknown" if error.diagnostic_code in ("transport-timeout", "transport-delivery-ambiguous") else "failed-closed"
            raise ModelGatewayFailure(error.diagnostic_code) from None
        except Exception:
            row["error_code"] = "expression-invalid"
            row["status"] = "failed-closed"
            raise ModelGatewayFailure(row["error_code"]) from None
        finally:
            # Only this allowlist reaches an observation callback/list.
            row.update({key: observed.row[key] for key in ("model", "usage", "finish_reason")})
            row["elapsed_seconds"] = max(0.0, perf_counter() - started)
            self.rows.append(row)
        return ModelResult(task.kind, value)
