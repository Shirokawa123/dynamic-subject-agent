"""Controlled Cognition boundary with a default-deny provider policy.

Phase 1 deliberately permits only an injected, process-local, deterministic
test provider.  It contains no network client, credential resolver, canonical
store handle, Domain, TimelineEngine, or effect dispatcher.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from dynamic_subject_agent.domains import CompleteDomainOutcomeSet, ExperienceBasis
from dynamic_subject_agent.runtime import (
    CognitionEngine,
    CognitionFailedClosed,
    CognitionRuntimeView,
    CognitiveProposal,
    CyclePlan,
    ExpressionCandidate,
)
from dynamic_subject_agent.timeline import PreAdmissionRejected, SubjectCommand


CONTROLLED_COGNITION_VERSION = "post-m0-controlled-cognition-test-1.0"
TEST_PROVIDER_AUTHORITY = "fake-cognition:m0-a-cycle-1.0"
_MAX_CONTEXT_ITEM_LENGTH = 2_000
_MAX_EXPRESSION_LENGTH = 4_000
_MAX_SUMMARY_LENGTH = 1_000


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_uuid(value: str, field: str) -> str:
    try:
        canonical = str(UUID(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError(f"{field} must be a canonical UUID") from error
    if canonical != value:
        raise ValueError(f"{field} must be a canonical UUID")
    return canonical


def _bounded_text(value: str, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field} must be non-empty and bounded")
    return value


def _bounded_items(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field} must be an immutable tuple")
    for value in values:
        _bounded_text(value, field, _MAX_CONTEXT_ITEM_LENGTH)
    return values


class ProviderTransport(str, Enum):
    TEST_ONLY_LOCAL = "test-only-local"
    EXTERNAL_NETWORK = "external-network"


class ProviderFailureCode(str, Enum):
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate-limit"
    NETWORK_FAILURE = "network-failure"
    DELIVERY_AMBIGUOUS = "delivery-ambiguous"
    INVALID_OUTPUT = "invalid-output"
    UNAVAILABLE = "unavailable"


class ProviderFailure(Exception):
    """Sanitized provider failure crossing the narrow provider boundary."""

    def __init__(self, code: ProviderFailureCode) -> None:
        if not isinstance(code, ProviderFailureCode):
            raise TypeError("ProviderFailure requires ProviderFailureCode")
        super().__init__(code.value)
        self.code = code


class DisclosureKnowledge(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"
    NOT_APPLICABLE_TEST_ONLY = "not-applicable-test-only"


@dataclass(frozen=True)
class DisclosureItem:
    knowledge: DisclosureKnowledge
    statement: str

    def __post_init__(self) -> None:
        if not isinstance(self.knowledge, DisclosureKnowledge):
            raise TypeError("knowledge must be DisclosureKnowledge")
        _bounded_text(self.statement, "statement", 1_000)

    def to_dict(self) -> dict[str, str]:
        return {
            "knowledge": self.knowledge.value,
            "statement": self.statement,
        }


@dataclass(frozen=True)
class ProviderDescriptor:
    authority_id: str
    provider: str
    model: str
    transport: ProviderTransport

    def __post_init__(self) -> None:
        _bounded_text(self.authority_id, "authority_id", 200)
        _bounded_text(self.provider, "provider", 200)
        _bounded_text(self.model, "model", 200)
        if not isinstance(self.transport, ProviderTransport):
            raise TypeError("transport must be ProviderTransport")

    @classmethod
    def test_only(
        cls,
        *,
        authority_id: str,
        provider: str,
        model: str,
    ) -> ProviderDescriptor:
        return cls(
            authority_id=authority_id,
            provider=provider,
            model=model,
            transport=ProviderTransport.TEST_ONLY_LOCAL,
        )


@dataclass(frozen=True)
class ProviderTermsDisclosure:
    disclosure_id: str
    descriptor: ProviderDescriptor
    training_use: DisclosureItem
    retention: DisclosureItem
    processing_location: DisclosureItem
    deletion_method: DisclosureItem
    terms_version: str
    integrity_digest: str

    def __post_init__(self) -> None:
        _canonical_uuid(self.disclosure_id, "disclosure_id")
        if not isinstance(self.descriptor, ProviderDescriptor):
            raise TypeError("descriptor must be ProviderDescriptor")
        for field in (
            "training_use",
            "retention",
            "processing_location",
            "deletion_method",
        ):
            if not isinstance(getattr(self, field), DisclosureItem):
                raise TypeError(f"{field} must be DisclosureItem")
        _bounded_text(self.terms_version, "terms_version", 1_000)
        if self.integrity_digest != _digest(self._payload()):
            raise ValueError("ProviderTermsDisclosure integrity mismatch")

    def _payload(self) -> dict[str, Any]:
        return {
            "disclosure_id": self.disclosure_id,
            "authority_id": self.descriptor.authority_id,
            "provider": self.descriptor.provider,
            "model": self.descriptor.model,
            "transport": self.descriptor.transport.value,
            "training_use": self.training_use.to_dict(),
            "retention": self.retention.to_dict(),
            "processing_location": self.processing_location.to_dict(),
            "deletion_method": self.deletion_method.to_dict(),
            "terms_version": self.terms_version,
        }

    @classmethod
    def test_only(
        cls,
        descriptor: ProviderDescriptor,
    ) -> ProviderTermsDisclosure:
        if descriptor.transport is not ProviderTransport.TEST_ONLY_LOCAL:
            raise ValueError("test-only terms require a test-only provider")
        disclosure_id = str(
            uuid5(
                NAMESPACE_URL,
                "post-m0-test-terms:"
                f"{descriptor.authority_id}:{descriptor.provider}:{descriptor.model}",
            )
        )
        values = {
            "disclosure_id": disclosure_id,
            "descriptor": descriptor,
            "training_use": DisclosureItem(
                DisclosureKnowledge.NOT_APPLICABLE_TEST_ONLY,
                "No external provider training use exists for the test double.",
            ),
            "retention": DisclosureItem(
                DisclosureKnowledge.NOT_APPLICABLE_TEST_ONLY,
                "No external provider retention exists for the test double.",
            ),
            "processing_location": DisclosureItem(
                DisclosureKnowledge.NOT_APPLICABLE_TEST_ONLY,
                "The deterministic double runs only inside the test process.",
            ),
            "deletion_method": DisclosureItem(
                DisclosureKnowledge.NOT_APPLICABLE_TEST_ONLY,
                "The deterministic double creates no provider-side data.",
            ),
            "terms_version": "test-only-1.0",
        }
        provisional = cls.__new__(cls)
        for name, value in values.items():
            object.__setattr__(provisional, name, value)
        object.__setattr__(provisional, "integrity_digest", "")
        return cls(**values, integrity_digest=_digest(provisional._payload()))

    @classmethod
    def disclose(
        cls,
        *,
        disclosure_id: str,
        descriptor: ProviderDescriptor,
        training_use: DisclosureItem,
        retention: DisclosureItem,
        processing_location: DisclosureItem,
        deletion_method: DisclosureItem,
        terms_version: str,
    ) -> ProviderTermsDisclosure:
        values = {
            "disclosure_id": disclosure_id,
            "descriptor": descriptor,
            "training_use": training_use,
            "retention": retention,
            "processing_location": processing_location,
            "deletion_method": deletion_method,
            "terms_version": terms_version,
        }
        provisional = cls.__new__(cls)
        for name, value in values.items():
            object.__setattr__(provisional, name, value)
        object.__setattr__(provisional, "integrity_digest", "")
        return cls(**values, integrity_digest=_digest(provisional._payload()))


@dataclass(frozen=True, repr=False)
class CredentialRef:
    backend_id: str
    key_id: str
    integrity_digest: str

    def __post_init__(self) -> None:
        _bounded_text(self.backend_id, "backend_id", 200)
        _bounded_text(self.key_id, "key_id", 200)
        if self.integrity_digest != _digest(
            {"backend_id": self.backend_id, "key_id": self.key_id}
        ):
            raise ValueError("CredentialRef integrity mismatch")

    def __repr__(self) -> str:
        return "CredentialRef(<redacted>)"

    @classmethod
    def reference(cls, *, backend_id: str, key_id: str) -> CredentialRef:
        return cls(
            backend_id=backend_id,
            key_id=key_id,
            integrity_digest=_digest({"backend_id": backend_id, "key_id": key_id}),
        )


@dataclass(frozen=True)
class OperationEgressApproval:
    approval_id: str
    operation_id: str
    outbound_digest: str
    disclosure_digest: str
    approval_kind: str
    integrity_digest: str

    def __post_init__(self) -> None:
        _canonical_uuid(self.approval_id, "approval_id")
        _canonical_uuid(self.operation_id, "operation_id")
        if len(self.outbound_digest) != 64 or len(self.disclosure_digest) != 64:
            raise ValueError("approval digests must be SHA-256 values")
        if self.approval_kind != "explicit-single-operation":
            raise ValueError("approval must be explicit and operation-bound")
        if self.integrity_digest != _digest(self._payload()):
            raise ValueError("OperationEgressApproval integrity mismatch")

    def _payload(self) -> dict[str, str]:
        return {
            "approval_id": self.approval_id,
            "operation_id": self.operation_id,
            "outbound_digest": self.outbound_digest,
            "disclosure_digest": self.disclosure_digest,
            "approval_kind": self.approval_kind,
        }

    @classmethod
    def approve(
        cls,
        *,
        approval_id: str,
        operation_id: str,
        outbound_digest: str,
        disclosure: ProviderTermsDisclosure,
    ) -> OperationEgressApproval:
        if not isinstance(disclosure, ProviderTermsDisclosure):
            raise TypeError("disclosure must be ProviderTermsDisclosure")
        values = {
            "approval_id": approval_id,
            "operation_id": operation_id,
            "outbound_digest": outbound_digest,
            "disclosure_digest": disclosure.integrity_digest,
            "approval_kind": "explicit-single-operation",
        }
        provisional = cls.__new__(cls)
        for name, value in values.items():
            object.__setattr__(provisional, name, value)
        object.__setattr__(provisional, "integrity_digest", "")
        return cls(**values, integrity_digest=_digest(provisional._payload()))

    def authorizes(
        self,
        *,
        operation_id: str,
        outbound_digest: str,
        disclosure: ProviderTermsDisclosure,
    ) -> bool:
        return (
            isinstance(disclosure, ProviderTermsDisclosure)
            and self.operation_id == operation_id
            and self.outbound_digest == outbound_digest
            and self.disclosure_digest == disclosure.integrity_digest
            and self.integrity_digest == _digest(self._payload())
        )


@dataclass(frozen=True)
class OperationEgressReservation:
    """One immutable identity reservation consumed by canonical Admission."""

    operation_id: str
    binding_id: str
    profile_id: str
    timeline_id: str
    command_fingerprint: str
    provider_authority: str
    integrity_digest: str

    def __post_init__(self) -> None:
        for field in ("operation_id", "binding_id", "profile_id", "timeline_id"):
            _canonical_uuid(getattr(self, field), field)
        if len(self.command_fingerprint) != 64:
            raise ValueError("command_fingerprint must be a SHA-256 digest")
        _bounded_text(self.provider_authority, "provider_authority", 200)
        if self.integrity_digest != _digest(self._payload()):
            raise ValueError("OperationEgressReservation integrity mismatch")

    def _payload(self) -> dict[str, str]:
        return {
            "operation_id": self.operation_id,
            "binding_id": self.binding_id,
            "profile_id": self.profile_id,
            "timeline_id": self.timeline_id,
            "command_fingerprint": self.command_fingerprint,
            "provider_authority": self.provider_authority,
        }

    @classmethod
    def reserve(
        cls,
        *,
        operation_id: str,
        binding_id: str,
        profile_id: str,
        timeline_id: str,
        command_fingerprint: str,
        provider_authority: str,
    ) -> OperationEgressReservation:
        values = {
            "operation_id": operation_id,
            "binding_id": binding_id,
            "profile_id": profile_id,
            "timeline_id": timeline_id,
            "command_fingerprint": command_fingerprint,
            "provider_authority": provider_authority,
        }
        provisional = cls.__new__(cls)
        for name, value in values.items():
            object.__setattr__(provisional, name, value)
        object.__setattr__(provisional, "integrity_digest", "")
        return cls(**values, integrity_digest=_digest(provisional._payload()))

    def binds(
        self,
        *,
        context: CognitionRuntimeView,
        command: SubjectCommand,
    ) -> bool:
        return (
            self.integrity_digest == _digest(self._payload())
            and self.binding_id == context.runtime_authority_id
            and self.profile_id == context.profile_id
            and self.timeline_id == context.timeline_id
            and self.command_fingerprint == command.payload_fingerprint
            and self.provider_authority == context.provider_authority
        )


@dataclass(frozen=True)
class UserConfirmedContextBrief:
    brief_id: str
    profile_id: str
    timeline_id: str
    command_fingerprint: str
    language: str
    confirmed_facts: tuple[str, ...]
    acknowledged_unknowns: tuple[str, ...]
    source_kind: str
    integrity_digest: str

    def __post_init__(self) -> None:
        _canonical_uuid(self.brief_id, "brief_id")
        _canonical_uuid(self.profile_id, "profile_id")
        _canonical_uuid(self.timeline_id, "timeline_id")
        if len(self.command_fingerprint) != 64:
            raise ValueError("command_fingerprint must be a SHA-256 digest")
        _bounded_text(self.language, "language", 32)
        _bounded_items(self.confirmed_facts, "confirmed_facts")
        _bounded_items(self.acknowledged_unknowns, "acknowledged_unknowns")
        if self.source_kind != "user-confirmed-current-operation":
            raise ValueError("context brief source_kind is not authorized")
        if self.integrity_digest != _digest(self._payload()):
            raise ValueError("UserConfirmedContextBrief integrity mismatch")

    def _payload(self) -> dict[str, Any]:
        return {
            "brief_id": self.brief_id,
            "profile_id": self.profile_id,
            "timeline_id": self.timeline_id,
            "command_fingerprint": self.command_fingerprint,
            "language": self.language,
            "confirmed_facts": list(self.confirmed_facts),
            "acknowledged_unknowns": list(self.acknowledged_unknowns),
            "source_kind": self.source_kind,
        }

    @classmethod
    def confirm(
        cls,
        *,
        brief_id: str,
        profile_id: str,
        timeline_id: str,
        command_fingerprint: str,
        language: str,
        confirmed_facts: tuple[str, ...],
        acknowledged_unknowns: tuple[str, ...],
    ) -> UserConfirmedContextBrief:
        values = {
            "brief_id": brief_id,
            "profile_id": profile_id,
            "timeline_id": timeline_id,
            "command_fingerprint": command_fingerprint,
            "language": language,
            "confirmed_facts": confirmed_facts,
            "acknowledged_unknowns": acknowledged_unknowns,
            "source_kind": "user-confirmed-current-operation",
        }
        provisional = cls.__new__(cls)
        for name, value in values.items():
            object.__setattr__(provisional, name, value)
        object.__setattr__(provisional, "integrity_digest", "")
        return cls(**values, integrity_digest=_digest(provisional._payload()))


@dataclass(frozen=True)
class CognitionProviderRequest:
    request_id: str
    request_digest: str
    operation_id: str
    profile_id: str
    timeline_id: str
    provider: str
    model: str
    current_command: str
    language: str
    brief_id: str
    brief_digest: str
    confirmed_facts: tuple[str, ...]
    acknowledged_unknowns: tuple[str, ...]


@dataclass(frozen=True)
class CognitionProviderResult:
    request_id: str
    request_digest: str
    experience_summary: str
    expression_text: str
    language: str
    delivery_state: str

    @classmethod
    def delivered(
        cls,
        request: CognitionProviderRequest,
        *,
        experience_summary: str,
        expression_text: str,
    ) -> CognitionProviderResult:
        return cls(
            request_id=request.request_id,
            request_digest=request.request_digest,
            experience_summary=experience_summary,
            expression_text=expression_text,
            language=request.language,
            delivery_state="delivered",
        )


class CognitionProvider(ABC):
    """External seam. Phase 1 supplies implementations only from tests."""

    descriptor: ProviderDescriptor
    terms: ProviderTermsDisclosure

    @abstractmethod
    def generate(
        self,
        request: CognitionProviderRequest,
        *,
        credential_ref: object | None,
    ) -> CognitionProviderResult:
        raise NotImplementedError


class ControlledCognition(CognitionEngine):
    """Deep no-egress phase-1 engine around one operation-bound context brief."""

    adapter_version = CONTROLLED_COGNITION_VERSION
    experimental = True
    test_only = True

    def __init__(
        self,
        *,
        provider: CognitionProvider,
        context_brief: UserConfirmedContextBrief,
        egress_approval: OperationEgressApproval | None = None,
        credential_ref: CredentialRef | None = None,
        operation_reservation: OperationEgressReservation | None = None,
    ) -> None:
        if not isinstance(provider, CognitionProvider):
            raise TypeError("provider must implement CognitionProvider")
        if not isinstance(provider.descriptor, ProviderDescriptor):
            raise TypeError("provider descriptor is required")
        if not isinstance(provider.terms, ProviderTermsDisclosure):
            raise TypeError("provider terms disclosure is required")
        if provider.terms.descriptor != provider.descriptor:
            raise ValueError("provider terms do not bind the selected provider")
        if egress_approval is not None and not isinstance(
            egress_approval,
            OperationEgressApproval,
        ):
            raise TypeError("egress_approval must be OperationEgressApproval")
        if credential_ref is not None and not isinstance(
            credential_ref,
            CredentialRef,
        ):
            raise TypeError("credential_ref must be CredentialRef")
        if operation_reservation is not None and not isinstance(
            operation_reservation,
            OperationEgressReservation,
        ):
            raise TypeError("operation_reservation must be OperationEgressReservation")
        is_external = provider.descriptor.transport is ProviderTransport.EXTERNAL_NETWORK
        if provider.descriptor.transport is ProviderTransport.TEST_ONLY_LOCAL:
            if provider.descriptor.authority_id != TEST_PROVIDER_AUTHORITY:
                raise PreAdmissionRejected(
                    "provider-authority-unavailable",
                    "test provider does not match the current QRI authority",
                )
            if (
                egress_approval is not None
                or credential_ref is not None
                or operation_reservation is not None
            ):
                raise PreAdmissionRejected(
                    "test-provider-egress-artifact-forbidden",
                    "the no-egress test provider accepts no approval or credential",
                )
        elif not is_external or not self._permits_external_provider(provider):
            raise PreAdmissionRejected(
                "real-provider-hitl-preview-required",
                "the controlled route permits no unrecognized external provider",
            )
        elif (
            egress_approval is None
            or credential_ref is None
            or operation_reservation is None
        ):
            raise PreAdmissionRejected(
                "operation-egress-approval-required",
                "external provider routing requires approval, credential reference and reservation",
            )
        if not isinstance(context_brief, UserConfirmedContextBrief):
            raise TypeError("context_brief must be UserConfirmedContextBrief")
        self.provider_authority = provider.descriptor.authority_id
        self._provider = provider
        self._brief = context_brief
        self._egress_approval = egress_approval
        self._credential_ref = credential_ref
        self._operation_reservation = operation_reservation
        self._external = is_external
        self.test_only = not is_external

    def _permits_external_provider(self, provider: CognitionProvider) -> bool:
        del provider
        return False

    def preflight(
        self,
        *,
        context: CognitionRuntimeView,
        command: SubjectCommand,
    ) -> None:
        brief = self._brief
        if (
            brief.profile_id != context.profile_id
            or brief.timeline_id != context.timeline_id
            or brief.command_fingerprint != command.payload_fingerprint
            or brief.language != command.language
            or context.provider_authority != self.provider_authority
        ):
            raise PreAdmissionRejected(
                "context-brief-identity-mismatch",
                "UserConfirmedContextBrief does not bind this exact operation input",
            )
        if self._external:
            reservation = self._operation_reservation
            approval = self._egress_approval
            if (
                reservation is None
                or approval is None
                or not reservation.binds(context=context, command=command)
                or approval.operation_id != reservation.operation_id
            ):
                raise PreAdmissionRejected(
                    "operation-egress-reservation-mismatch",
                    "operation approval does not bind this exact authority and command",
                )

    def reserved_operation_id(
        self,
        *,
        context: CognitionRuntimeView,
        command: SubjectCommand,
    ) -> str | None:
        self.preflight(context=context, command=command)
        if self._external:
            assert self._operation_reservation is not None
            return self._operation_reservation.operation_id
        return None

    def _request(
        self,
        *,
        plan: CyclePlan,
        context: CognitionRuntimeView,
        command: SubjectCommand,
    ) -> CognitionProviderRequest:
        descriptor = self._provider.descriptor
        request_id = str(
            uuid5(
                NAMESPACE_URL,
                f"post-m0-cognition:{plan.operation_ref.operation_id}:"
                f"{self._brief.integrity_digest}:{descriptor.provider}:"
                f"{descriptor.model}",
            )
        )
        payload = {
            "request_id": request_id,
            "operation_id": plan.operation_ref.operation_id,
            "profile_id": context.profile_id,
            "timeline_id": context.timeline_id,
            "provider": descriptor.provider,
            "model": descriptor.model,
            "current_command": command.utterance,
            "language": command.language,
            "brief_id": self._brief.brief_id,
            "brief_digest": self._brief.integrity_digest,
            "confirmed_facts": list(self._brief.confirmed_facts),
            "acknowledged_unknowns": list(self._brief.acknowledged_unknowns),
        }
        return CognitionProviderRequest(
            request_id=request_id,
            request_digest=_digest(payload),
            operation_id=plan.operation_ref.operation_id,
            profile_id=context.profile_id,
            timeline_id=context.timeline_id,
            provider=descriptor.provider,
            model=descriptor.model,
            current_command=command.utterance,
            language=command.language,
            brief_id=self._brief.brief_id,
            brief_digest=self._brief.integrity_digest,
            confirmed_facts=self._brief.confirmed_facts,
            acknowledged_unknowns=self._brief.acknowledged_unknowns,
        )

    def propose(
        self,
        *,
        plan: CyclePlan,
        context: CognitionRuntimeView,
        command: SubjectCommand,
        basis: ExperienceBasis,
    ) -> CognitiveProposal:
        self.preflight(context=context, command=command)
        request = self._request(plan=plan, context=context, command=command)
        try:
            result = self._provider.generate(
                request,
                credential_ref=self._credential_ref,
            )
        except CognitionFailedClosed:
            raise
        except ProviderFailure as error:
            failure_codes = {
                ProviderFailureCode.TIMEOUT: "provider-timeout",
                ProviderFailureCode.RATE_LIMIT: "provider-rate-limit",
                ProviderFailureCode.NETWORK_FAILURE: "provider-network-failure",
                ProviderFailureCode.DELIVERY_AMBIGUOUS: ("provider-delivery-ambiguous"),
                ProviderFailureCode.INVALID_OUTPUT: "provider-invalid-output",
                ProviderFailureCode.UNAVAILABLE: "provider-unavailable",
            }
            raise CognitionFailedClosed(
                "provider",
                failure_codes[error.code],
                "the bounded provider operation failed without a usable delivery",
            ) from error
        except Exception as error:
            raise CognitionFailedClosed(
                "provider",
                "provider-technical-failure",
                "the bounded provider did not return a usable result",
            ) from error
        if (
            type(result) is not CognitionProviderResult
            or result.request_id != request.request_id
            or result.request_digest != request.request_digest
            or result.delivery_state != "delivered"
            or result.language != command.language
        ):
            raise CognitionFailedClosed(
                "provider",
                "provider-result-identity-mismatch",
                "provider result did not bind the exact request",
            )
        try:
            summary = _bounded_text(
                result.experience_summary,
                "experience_summary",
                _MAX_SUMMARY_LENGTH,
            )
            expression = _bounded_text(
                result.expression_text,
                "expression_text",
                _MAX_EXPRESSION_LENGTH,
            )
        except ValueError as error:
            raise CognitionFailedClosed(
                "provider",
                "provider-invalid-output",
                "provider output violated the bounded projection contract",
            ) from error
        return self._bounded_noop_proposal(
            context=context,
            basis=basis,
            experience_summary=summary,
            expression_candidate=ExpressionCandidate(
                text=expression,
                language=result.language,
            ),
        )

    def express(
        self,
        *,
        proposal: CognitiveProposal,
        context: CognitionRuntimeView,
        command: SubjectCommand,
        outcomes: CompleteDomainOutcomeSet,
    ) -> ExpressionCandidate:
        return super().express(
            proposal=proposal,
            context=context,
            command=command,
            outcomes=outcomes,
        )


__all__ = [
    "CognitionProvider",
    "CognitionProviderRequest",
    "CognitionProviderResult",
    "ControlledCognition",
    "CredentialRef",
    "DisclosureItem",
    "DisclosureKnowledge",
    "OperationEgressApproval",
    "OperationEgressReservation",
    "ProviderDescriptor",
    "ProviderFailure",
    "ProviderFailureCode",
    "ProviderTermsDisclosure",
    "ProviderTransport",
    "UserConfirmedContextBrief",
]
