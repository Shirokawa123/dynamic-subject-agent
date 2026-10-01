"""One-shot S116 delivery through the existing strict DeepSeek protocol.

S115 froze the approved baseline/example bytes and original output validators;
S116 reuses them and the existing observed-response whitelist. The independent
SQLite audit is claimed before HTTPS, with no quota, retry, Timeline or key store.
Only this exact technical purpose and material package are served here.
"""
from hashlib import sha256
from time import perf_counter

from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
from dynamic_subject_agent.cognition import CredentialRef
from dynamic_subject_agent.deepseek import (
    DeepSeekTransport, DeepSeekUrlLibTransport, DeepSeekResponseDiagnosticFailure,
    DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID,
    DEEPSEEK_ENDPOINT, DEEPSEEK_TIMEOUT_SECONDS, _post_json_reply_content,
)
from dynamic_subject_agent.development_model_calls import DevelopmentCallAudit
from dynamic_subject_agent.first_life_reply_live_provider import _ObservedTransport
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import (
    ModelTask, ModelTaskKind, ModelResult, ModelGatewayFailure,
    ProviderAdapter, ProviderCapabilities, StructuredOutputMode,
)
from dynamic_subject_agent.reply_protocol_trial import (
    ProtocolRun, ProtocolTrialRequest, PURPOSE, PROTOCOL_DIAGNOSTICS, fixed_development_audit_path,
)


OFFLINE_CREDENTIAL_BACKEND = "reply-protocol-offline"
OFFLINE_CREDENTIAL_KEY = "no-credential"


class ProtocolTrialAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities("deepseek", "deepseek-flash", False, (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self, transport, credential_ref, plan, audit):
        if (not isinstance(transport, DeepSeekTransport) or type(credential_ref) is not CredentialRef
            or type(plan) is not ProtocolRun or type(audit) is not DevelopmentCallAudit
            or DEEPSEEK_ENDPOINT != "https://api.deepseek.com/chat/completions" or DEEPSEEK_TIMEOUT_SECONDS != 30):
            raise ValueError("exact protocol transport, run and development audit required")
        self.transport, self.credential_ref, self.plan, self.audit = transport, credential_ref, plan, audit
        self.rows = []
        self._verify_authority()

    def _verify_authority(self):
        manifest = self.plan.read()
        if manifest["live"]:
            if (self.credential_ref.backend_id != DEEPSEEK_CREDENTIAL_BACKEND_ID
                or self.credential_ref.key_id != DEEPSEEK_CREDENTIAL_KEY_ID
                or self.audit.path.resolve() != fixed_development_audit_path().resolve()):
                raise ValueError("real protocol delivery requires the fixed live audit and credential reference")
        elif (self.credential_ref.backend_id != OFFLINE_CREDENTIAL_BACKEND
            or self.credential_ref.key_id != OFFLINE_CREDENTIAL_KEY
            or self.audit.path.resolve() != (self.plan.root / "offline-audit").resolve()
            or isinstance(self.transport, DeepSeekUrlLibTransport)):
            raise ValueError("offline protocol delivery requires its isolated audit and synthetic transport")
        self.audit.counts()

    def _claim(self, request, wire_digest):
        try:
            old = self.audit.query(request.attempt_id)
        except Exception:
            raise ModelGatewayFailure("protocol-audit-failed") from None
        if old is not None:
            raise ModelGatewayFailure("protocol-attempt-already-recorded")
        try:
            self.audit.claim(request.attempt_id, wire_digest, purpose=PURPOSE, run_digest=self.plan.digest)
        except Exception:
            # Another worker or an uncertain claim may already own it. Neither
            # case permits another claim or delivery from this invocation.
            try:
                duplicate = self.audit.query(request.attempt_id) is not None
            except Exception:
                duplicate = False
            raise ModelGatewayFailure("protocol-attempt-already-recorded" if duplicate else "protocol-audit-failed") from None

    def invoke(self, task):
        if (type(task) is not ModelTask or task.kind is not ModelTaskKind.CHARACTER_REPLY_PROTOCOL
            or type(task.payload) is not ProtocolTrialRequest):
            raise ModelGatewayFailure("protocol-request-invalid")
        request = task.payload
        try:
            self._verify_authority()
            wire = self.plan.wire_for(request)
        except Exception:
            raise ModelGatewayFailure("protocol-authority-invalid") from None
        wire_digest = sha256(wire).hexdigest()
        observed = _ObservedTransport(self.transport)
        row = dict(task_kind=task.kind.value, case_id=request.case_id, variant=request.variant,
            attempt_id=request.attempt_id, run_digest=self.plan.digest, wire_sha256=wire_digest,
            value=None, error_code=None, format_example_copied=False, transport_attempted=False)
        started, claimed, audited, error_code, status = perf_counter(), False, False, None, "failed-closed"
        try:
            self._claim(request, wire_digest)
            claimed = True
            try:
                self._verify_authority()
                if self.plan.wire_for(request) != wire:
                    raise ValueError("approved request changed")
            except Exception:
                raise ModelGatewayFailure("protocol-authority-invalid") from None
            row["transport_attempted"] = True
            value = _post_json_reply_content(observed, self.credential_ref, wire, max_output_tokens=4096,
                require_complete=True, discard_reasoning=True, safe_diagnostics=True)
            row["value"] = value
            try:
                self._verify_authority()
            except Exception:
                raise ModelGatewayFailure("protocol-authority-invalid") from None
            try:
                row["format_example_copied"] = self.plan.validate_output(request, value)
            except Exception:
                raise ModelGatewayFailure("protocol-response-invalid") from None
            status = "complete"
        except CharacterCredentialUnavailable:
            error_code, status = "character-credential-unavailable", "unavailable"
        except DeepSeekResponseDiagnosticFailure as error:
            error_code = error.diagnostic_code if error.diagnostic_code in PROTOCOL_DIAGNOSTICS else "provider-failed"
            status = "unknown" if error_code.startswith("transport-") else "failed-closed"
        except ModelGatewayFailure as error:
            error_code = error.code if error.code in PROTOCOL_DIAGNOSTICS else "provider-failed"
        except Exception:
            error_code = "provider-failed"
        finally:
            row["delivery_error_code"] = error_code
            if claimed:
                try:
                    output_digest = (sha256(canonical_json(row["value"]).encode()).hexdigest()
                        if row["value"] is not None else None)
                    self.audit.record(request.attempt_id, status=status, output_digest=output_digest)
                    audited = True
                except Exception:
                    error_code = "protocol-audit-failed"
            row.update(observed.row)
            row.update(error_code=error_code, audit_status=status if audited else "unverified" if claimed else "not-claimed",
                elapsed_seconds=max(0.0, perf_counter() - started))
            try:
                self.rows.append(row)
            except Exception:
                error_code = "protocol-audit-failed"
        if error_code is not None:
            raise ModelGatewayFailure(error_code) from None
        return ModelResult(task.kind, row["value"])
