from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest

from dynamic_subject_agent.cognition import (
    CognitionProvider,
    CognitionProviderRequest,
    CognitionProviderResult,
    ControlledCognition,
    CredentialRef,
    DisclosureItem,
    DisclosureKnowledge,
    OperationEgressApproval,
    ProviderDescriptor,
    ProviderFailure,
    ProviderFailureCode,
    ProviderTermsDisclosure,
    ProviderTransport,
    UserConfirmedContextBrief,
)
from dynamic_subject_agent.timeline import PreAdmissionRejected, SubjectCommand
from test_runtime_host_binding import _publish_qri


class _DeterministicChineseProvider(CognitionProvider):
    def __init__(self) -> None:
        self.descriptor = ProviderDescriptor.test_only(
            authority_id="fake-cognition:m0-a-cycle-1.0",
            provider="deterministic-test-double",
            model="bounded-zh-v1",
        )
        self.terms = ProviderTermsDisclosure.test_only(self.descriptor)
        self.requests: list[CognitionProviderRequest] = []

    def generate(
        self,
        request: CognitionProviderRequest,
        *,
        credential_ref: object | None,
    ) -> CognitionProviderResult:
        assert credential_ref is None
        self.requests.append(request)
        return CognitionProviderResult.delivered(
            request,
            experience_summary="已处理这次明确限定的 Lantern Zine 当前状态询问。",
            expression_text=(
                "Lantern Zine 目前处于样稿校对阶段；你接下来需要确认最终页序。"
            ),
        )


class _ForbiddenNetworkProvider(CognitionProvider):
    def __init__(self, descriptor: ProviderDescriptor) -> None:
        self.descriptor = descriptor
        item = DisclosureItem(
            knowledge=DisclosureKnowledge.UNKNOWN,
            statement="No current real-provider term has been approved.",
        )
        self.terms = ProviderTermsDisclosure.disclose(
            disclosure_id=str(uuid4()),
            descriptor=descriptor,
            training_use=item,
            retention=item,
            processing_location=item,
            deletion_method=item,
            terms_version="unapproved-preview",
        )
        self.call_count = 0

    def generate(
        self,
        request: CognitionProviderRequest,
        *,
        credential_ref: object | None,
    ) -> CognitionProviderResult:
        del request, credential_ref
        self.call_count += 1
        raise AssertionError("phase 1 must never call a network provider")


class _FailingTestProvider(_DeterministicChineseProvider):
    def __init__(self, code: ProviderFailureCode) -> None:
        super().__init__()
        self._code = code
        self.call_count = 0

    def generate(
        self,
        request: CognitionProviderRequest,
        *,
        credential_ref: object | None,
    ) -> CognitionProviderResult:
        del request, credential_ref
        self.call_count += 1
        raise ProviderFailure(self._code)


class _InvalidIdentityProvider(_DeterministicChineseProvider):
    def generate(
        self,
        request: CognitionProviderRequest,
        *,
        credential_ref: object | None,
    ) -> CognitionProviderResult:
        result = super().generate(request, credential_ref=credential_ref)
        return replace(result, request_digest="0" * 64)


class _BlockingTestProvider(_DeterministicChineseProvider):
    def __init__(self, entered: Event, release: Event) -> None:
        super().__init__()
        self._entered = entered
        self._release = release

    def generate(
        self,
        request: CognitionProviderRequest,
        *,
        credential_ref: object | None,
    ) -> CognitionProviderResult:
        self._entered.set()
        if not self._release.wait(timeout=5):
            raise AssertionError("test did not release provider double")
        return super().generate(request, credential_ref=credential_ref)


def test_controlled_test_provider_publishes_one_relevant_chinese_outcome(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import ApplicationOperationStatus
    from dynamic_subject_agent.bootstrap import compose_application

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="Avery，Lantern Zine 现在进展到哪了？我需要做什么？",
        language="zh",
        provenance="project-original",
    )
    brief = UserConfirmedContextBrief.confirm(
        brief_id=str(uuid4()),
        profile_id=qri.profile_id,
        timeline_id=timeline_id,
        command_fingerprint=command.payload_fingerprint,
        language="zh",
        confirmed_facts=("Lantern Zine 当前处于样稿校对阶段。",),
        acknowledged_unknowns=("最终印刷日期尚未确认。",),
    )
    provider = _DeterministicChineseProvider()
    cognition = ControlledCognition(
        provider=provider,
        context_brief=brief,
    )
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=cognition,
    )
    try:
        submitted = composition.application.submit(
            command,
            idempotency_key="post-m0-controlled-cognition-0001",
        )
        terminal = composition.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )
        repeated = composition.application.submit(
            command,
            idempotency_key="post-m0-controlled-cognition-0001",
        )
    finally:
        composition.close()

    assert terminal.status is ApplicationOperationStatus.TERMINAL
    assert repeated.status is ApplicationOperationStatus.TERMINAL
    assert submitted.operation_ref == terminal.operation_ref == repeated.operation_ref
    assert terminal.projection == repeated.projection
    assert terminal.projection is not None
    assert terminal.projection.expression_language == "zh"
    assert terminal.projection.expression_text == (
        "Lantern Zine 目前处于样稿校对阶段；你接下来需要确认最终页序。"
    )
    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.current_command == command.utterance
    assert request.confirmed_facts == brief.confirmed_facts
    assert request.acknowledged_unknowns == brief.acknowledged_unknowns
    assert not hasattr(request, "timeline_history")
    assert not hasattr(request, "credential")


def test_egress_approval_and_credential_reference_are_narrow_and_operation_bound() -> (
    None
):
    descriptor = ProviderDescriptor(
        authority_id="controlled-provider:future-preview",
        provider="future-provider",
        model="future-model",
        transport=ProviderTransport.EXTERNAL_NETWORK,
    )
    disclosure = ProviderTermsDisclosure.disclose(
        disclosure_id=str(uuid4()),
        descriptor=descriptor,
        training_use=DisclosureItem(
            knowledge=DisclosureKnowledge.UNKNOWN,
            statement="The current provider term is not yet established.",
        ),
        retention=DisclosureItem(
            knowledge=DisclosureKnowledge.AMBIGUOUS,
            statement="The published term does not state one exact duration.",
        ),
        processing_location=DisclosureItem(
            knowledge=DisclosureKnowledge.KNOWN,
            statement="Declared region for this test metadata only.",
        ),
        deletion_method=DisclosureItem(
            knowledge=DisclosureKnowledge.UNKNOWN,
            statement="No verified deletion method is available.",
        ),
        terms_version="future-preview-only",
    )
    operation_id = str(uuid4())
    outbound_digest = "a" * 64
    approval = OperationEgressApproval.approve(
        approval_id=str(uuid4()),
        operation_id=operation_id,
        outbound_digest=outbound_digest,
        disclosure=disclosure,
    )
    credential_ref = CredentialRef.reference(
        backend_id="future-secret-boundary",
        key_id="provider-key-alias",
    )

    assert approval.authorizes(
        operation_id=operation_id,
        outbound_digest=outbound_digest,
        disclosure=disclosure,
    )
    assert not approval.authorizes(
        operation_id=str(uuid4()),
        outbound_digest=outbound_digest,
        disclosure=disclosure,
    )
    assert not approval.authorizes(
        operation_id=operation_id,
        outbound_digest="b" * 64,
        disclosure=disclosure,
    )
    assert repr(credential_ref) == "CredentialRef(<redacted>)"
    assert not hasattr(credential_ref, "secret")
    assert not hasattr(credential_ref, "value")


def test_phase_one_rejects_network_provider_even_with_approval_and_credential() -> None:
    profile_id = str(uuid4())
    timeline_id = str(uuid4())
    command = SubjectCommand.contribute_utterance(
        target_profile_id=profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="这次只验证默认无外发。",
        language="zh",
        provenance="project-original",
    )
    brief = UserConfirmedContextBrief.confirm(
        brief_id=str(uuid4()),
        profile_id=profile_id,
        timeline_id=timeline_id,
        command_fingerprint=command.payload_fingerprint,
        language="zh",
        confirmed_facts=(),
        acknowledged_unknowns=("真实 provider 尚未选择。",),
    )
    descriptor = ProviderDescriptor(
        authority_id="controlled-provider:unapproved",
        provider="unapproved-provider",
        model="unapproved-model",
        transport=ProviderTransport.EXTERNAL_NETWORK,
    )
    provider = _ForbiddenNetworkProvider(descriptor)
    credential_ref = CredentialRef.reference(
        backend_id="unconfigured-secret-boundary",
        key_id="unconfigured-key",
    )
    approval = OperationEgressApproval.approve(
        approval_id=str(uuid4()),
        operation_id=str(uuid4()),
        outbound_digest="c" * 64,
        disclosure=provider.terms,
    )

    with pytest.raises(PreAdmissionRejected) as caught:
        ControlledCognition(
            provider=provider,
            context_brief=brief,
            egress_approval=approval,
            credential_ref=credential_ref,
        )

    assert caught.value.code == "real-provider-hitl-preview-required"
    assert provider.call_count == 0


@pytest.mark.parametrize(
    ("failure_code", "expected_code"),
    [
        (ProviderFailureCode.TIMEOUT, "provider-timeout"),
        (ProviderFailureCode.RATE_LIMIT, "provider-rate-limit"),
        (ProviderFailureCode.NETWORK_FAILURE, "provider-network-failure"),
        (
            ProviderFailureCode.DELIVERY_AMBIGUOUS,
            "provider-delivery-ambiguous",
        ),
        (ProviderFailureCode.INVALID_OUTPUT, "provider-invalid-output"),
        (ProviderFailureCode.UNAVAILABLE, "provider-unavailable"),
    ],
)
def test_provider_failures_are_typed_terminal_and_never_blindly_retried(
    tmp_path: Path,
    failure_code: ProviderFailureCode,
    expected_code: str,
) -> None:
    from dynamic_subject_agent.application import ApplicationOperationStatus
    from dynamic_subject_agent.bootstrap import compose_application

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="请在 provider 失败时保持同一个 canonical operation。",
        language="zh",
        provenance="project-original",
    )
    brief = UserConfirmedContextBrief.confirm(
        brief_id=str(uuid4()),
        profile_id=qri.profile_id,
        timeline_id=timeline_id,
        command_fingerprint=command.payload_fingerprint,
        language="zh",
        confirmed_facts=(),
        acknowledged_unknowns=("Provider 本次不可用。",),
    )
    provider = _FailingTestProvider(failure_code)
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=ControlledCognition(
            provider=provider,
            context_brief=brief,
        ),
    )
    try:
        submitted = composition.application.submit(
            command,
            idempotency_key=f"post-m0-provider-failure-{failure_code.value}",
        )
        terminal = composition.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )
        repeated = composition.application.submit(
            command,
            idempotency_key=f"post-m0-provider-failure-{failure_code.value}",
        )
    finally:
        composition.close()

    assert terminal.status is ApplicationOperationStatus.FAILED_CLOSED
    assert repeated.status is ApplicationOperationStatus.FAILED_CLOSED
    assert terminal.operation_ref == submitted.operation_ref == repeated.operation_ref
    assert terminal.projection == repeated.projection
    assert terminal.projection is not None
    assert terminal.projection.failure_stage == "provider"
    assert terminal.projection.failure_code == expected_code
    assert terminal.projection.expression_text is None
    assert provider.call_count == 1


def test_context_brief_identity_mismatch_is_unavailable_before_admission(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import (
        ApplicationOperationStatus,
        ApplicationQuery,
        ApplicationQueryKind,
        ApplicationQueryStatus,
        TimelineApplicationProjection,
    )
    from dynamic_subject_agent.bootstrap import compose_application

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="这条命令不能借用另一条命令的 brief。",
        language="zh",
        provenance="project-original",
    )
    provider = _DeterministicChineseProvider()
    mismatched_brief = UserConfirmedContextBrief.confirm(
        brief_id=str(uuid4()),
        profile_id=qri.profile_id,
        timeline_id=timeline_id,
        command_fingerprint="0" * 64,
        language="zh",
        confirmed_facts=(),
        acknowledged_unknowns=(),
    )
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=ControlledCognition(
            provider=provider,
            context_brief=mismatched_brief,
        ),
    )
    try:
        response = composition.application.submit(
            command,
            idempotency_key="post-m0-mismatched-brief-0001",
        )
        timeline = composition.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.TIMELINE,
                target_profile_id=qri.profile_id,
                target_timeline_id=timeline_id,
            )
        )
    finally:
        composition.close()

    assert response.status is ApplicationOperationStatus.UNAVAILABLE
    assert response.operation_ref is None
    assert response.problem is not None
    assert response.problem.code == "context-brief-identity-mismatch"
    assert timeline.status is ApplicationQueryStatus.AVAILABLE
    assert isinstance(timeline.projection, TimelineApplicationProjection)
    assert timeline.projection.head_sequence == 0
    assert provider.requests == []


def test_invalid_provider_result_is_failed_closed_without_projection_leak(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import ApplicationOperationStatus
    from dynamic_subject_agent.bootstrap import compose_application

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="拒绝没有绑定当前 request 的 provider 输出。",
        language="zh",
        provenance="project-original",
    )
    brief = UserConfirmedContextBrief.confirm(
        brief_id=str(uuid4()),
        profile_id=qri.profile_id,
        timeline_id=timeline_id,
        command_fingerprint=command.payload_fingerprint,
        language="zh",
        confirmed_facts=(),
        acknowledged_unknowns=(),
    )
    provider = _InvalidIdentityProvider()
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=ControlledCognition(
            provider=provider,
            context_brief=brief,
        ),
    )
    try:
        submitted = composition.application.submit(
            command,
            idempotency_key="post-m0-invalid-provider-result-0001",
        )
        terminal = composition.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )
    finally:
        composition.close()

    assert terminal.status is ApplicationOperationStatus.FAILED_CLOSED
    assert terminal.projection is not None
    assert terminal.projection.failure_code == "provider-result-identity-mismatch"
    assert terminal.projection.expression_text is None
    assert terminal.projection.expression_language is None
    assert len(provider.requests) == 1


def test_concurrent_submit_and_restart_reuse_one_provider_call_and_outcome(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import ApplicationOperationStatus
    from dynamic_subject_agent.bootstrap import compose_application

    entered = Event()
    release = Event()
    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="并发和重启都必须复用同一个受控回应。",
        language="zh",
        provenance="project-original",
    )
    brief = UserConfirmedContextBrief.confirm(
        brief_id=str(uuid4()),
        profile_id=qri.profile_id,
        timeline_id=timeline_id,
        command_fingerprint=command.payload_fingerprint,
        language="zh",
        confirmed_facts=("本测试只使用当前 command 和 brief。",),
        acknowledged_unknowns=(),
    )
    first_provider = _BlockingTestProvider(entered, release)
    first = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=ControlledCognition(
            provider=first_provider,
            context_brief=brief,
        ),
    )

    def submit() -> object:
        return first.application.submit(
            command,
            idempotency_key="post-m0-concurrent-restart-0001",
        )

    try:
        with ThreadPoolExecutor(max_workers=4) as callers:
            futures = [callers.submit(submit) for _ in range(4)]
            assert entered.wait(timeout=5)
            submitted = [future.result(timeout=5) for future in futures]
        release.set()
        terminal = first.application.wait(
            submitted[0].operation_ref,
            timeout_seconds=5,
        )
        host_location = first.host_location
    finally:
        release.set()
        first.close()

    restarted_provider = _DeterministicChineseProvider()
    restarted = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
        _cognition=ControlledCognition(
            provider=restarted_provider,
            context_brief=brief,
        ),
    )
    try:
        replayed = restarted.application.submit(
            command,
            idempotency_key="post-m0-concurrent-restart-0001",
        )
        followed = restarted.application.follow(terminal.operation_ref)
    finally:
        restarted.close()

    assert len({response.operation_ref for response in submitted}) == 1
    assert terminal.status is ApplicationOperationStatus.TERMINAL
    assert replayed.status is ApplicationOperationStatus.TERMINAL
    assert followed.status is ApplicationOperationStatus.TERMINAL
    assert terminal.operation_ref == replayed.operation_ref == followed.operation_ref
    assert terminal.projection == replayed.projection == followed.projection
    assert len(first_provider.requests) == 1
    assert restarted_provider.requests == []
