from __future__ import annotations

import json
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from dynamic_subject_agent.cognition import (
    CognitionProviderRequest,
    CredentialRef,
    OperationEgressApproval,
    OperationEgressReservation,
    PreAdmissionRejected,
    UserConfirmedContextBrief,
)
from dynamic_subject_agent.deepseek import (
    DEEPSEEK_CREDENTIAL_BACKEND_ID,
    DEEPSEEK_CREDENTIAL_KEY_ID,
    DEEPSEEK_MODEL,
    ApprovedDeepSeekCognition,
    DeepSeekCognitionProvider,
    DeepSeekHttpResponse,
    DeepSeekTransport,
)
from dynamic_subject_agent.host import RuntimeHost
from dynamic_subject_agent.timeline import SubjectCommand


class _SingleResponseTransport(DeepSeekTransport):
    def __init__(self) -> None:
        self.calls = 0

    def post_json(
        self,
        *,
        endpoint: str,
        body: bytes,
        credential_ref: CredentialRef,
        timeout_seconds: float,
    ) -> DeepSeekHttpResponse:
        del endpoint, body, credential_ref, timeout_seconds
        self.calls += 1
        return DeepSeekHttpResponse(
            status_code=200,
            body=json.dumps(
                {
                    "model": DEEPSEEK_MODEL,
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(
                                    {
                                        "experience_summary": "只处理当前请求。",
                                        "expression_text": "请先确定下一期的读者、篇幅和发布时间。",
                                        "language": "zh-cn",
                                    },
                                    ensure_ascii=False,
                                ),
                                "reasoning_content": None,
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                },
                ensure_ascii=False,
            ).encode("utf-8"),
        )


class _AmbiguousTransport(DeepSeekTransport):
    def __init__(self) -> None:
        self.calls = 0

    def post_json(
        self,
        *,
        endpoint: str,
        body: bytes,
        credential_ref: CredentialRef,
        timeout_seconds: float,
    ) -> DeepSeekHttpResponse:
        del endpoint, body, credential_ref, timeout_seconds
        self.calls += 1
        raise TimeoutError("test-only ambiguous delivery")


def _publish_deepseek_qri(tmp_path: Path):
    from dynamic_subject_agent.local_product import create_local_product_identity

    identity = create_local_product_identity(tmp_path)
    prepared = SimpleNamespace(
        experiment_base=identity.experiment_base,
        location=identity.studio_location,
    )
    return prepared, identity.qualified_runtime_input


def test_desktop_first_start_uses_the_production_local_product_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    server_path = Path(__file__).resolve().parents[1] / "app" / "desktop" / "server.py"
    spec = importlib.util.spec_from_file_location(
        "mature_desktop_server_first_start_test",
        server_path,
    )
    assert spec is not None and spec.loader is not None
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    app_dir = tmp_path / "state"
    monkeypatch.setattr(server, "STATE_PATH", app_dir / "state.json")
    monkeypatch.setattr(server, "PERSISTENT_PARENT", tmp_path / "product")
    monkeypatch.setattr(server, "_resolve_key", lambda: "test-only-key")

    product = server.build_product(relationship_mode="off")
    try:
        assert product.publication_key == "local-product-deepseek-qri-v1"
        assert product.timeline_id
        assert server.STATE_PATH.is_file()
    finally:
        product.close()


def test_approved_deepseek_route_uses_the_reserved_canonical_operation_once(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import ApplicationOperationStatus
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition

    prepared, qri = _publish_deepseek_qri(tmp_path)
    timeline_id = str(uuid4())
    dormant_host = RuntimeHost.create(
        prepared.experiment_base,
        studio_location=prepared.location,
        cognition=DormantDeepSeekCognition(),
    )
    try:
        binding = dormant_host.open_runtime(qri, timeline_id=timeline_id).binding
        host_location = dormant_host.location
    finally:
        dormant_host.close()

    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance=(
            "Avery，我们正在筹备 Lantern Zine。给出三条下一步的建议，说明一下你缺少哪些信息，我告诉你。"
        ),
        language="zh-CN",
        provenance="project-original",
    )
    operation_id = str(uuid4())
    brief = UserConfirmedContextBrief.confirm(
        brief_id=str(uuid4()),
        profile_id=qri.profile_id,
        timeline_id=timeline_id,
        command_fingerprint=command.payload_fingerprint,
        language=command.language,
        confirmed_facts=(),
        acknowledged_unknowns=(),
    )
    reservation = OperationEgressReservation.reserve(
        operation_id=operation_id,
        binding_id=binding.binding_id,
        profile_id=qri.profile_id,
        timeline_id=timeline_id,
        command_fingerprint=command.payload_fingerprint,
        provider_authority=qri.provider_authority,
    )
    request = CognitionProviderRequest(
        request_id=str(uuid4()),
        request_digest="a" * 64,
        operation_id=operation_id,
        profile_id=qri.profile_id,
        timeline_id=timeline_id,
        provider="deepseek-official-api",
        model=DEEPSEEK_MODEL,
        current_command=command.utterance,
        language=command.language,
        brief_id=brief.brief_id,
        brief_digest=brief.integrity_digest,
        confirmed_facts=(),
        acknowledged_unknowns=(),
    )
    transport = _SingleResponseTransport()
    provider = DeepSeekCognitionProvider(
        transport=transport,
        egress_approval=OperationEgressApproval.approve(
            approval_id=str(uuid4()),
            operation_id=operation_id,
            outbound_digest=DeepSeekCognitionProvider.outbound_digest(request),
            disclosure=DeepSeekCognitionProvider.terms_disclosure(),
        ),
    )
    cognition = ApprovedDeepSeekCognition(
        provider=provider,
        context_brief=brief,
        operation_reservation=reservation,
        credential_ref=CredentialRef.reference(
            backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
            key_id=DEEPSEEK_CREDENTIAL_KEY_ID,
        ),
    )
    composition = compose_application(
        m0_root=prepared.experiment_base,
        studio_location=prepared.location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
        _cognition=cognition,
    )
    try:
        submitted = composition.application.submit(
            command,
            idempotency_key="test-only-approved-deepseek-route-0001",
        )
        terminal = composition.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )
        repeated = composition.application.submit(
            command,
            idempotency_key="test-only-approved-deepseek-route-0001",
        )
    finally:
        composition.close()

    assert submitted.operation_ref is not None
    assert submitted.operation_ref.operation_id == operation_id
    assert terminal.status is ApplicationOperationStatus.TERMINAL
    assert repeated.status is ApplicationOperationStatus.TERMINAL
    assert terminal.operation_ref == repeated.operation_ref == submitted.operation_ref
    assert transport.calls == 1


def test_reservation_with_a_wrong_binding_fails_before_admission_or_transport() -> None:
    from dynamic_subject_agent.runtime import CognitionRuntimeView

    profile_id = str(uuid4())
    timeline_id = str(uuid4())
    command = SubjectCommand.contribute_utterance(
        target_profile_id=profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance=(
            "Avery，我们正在筹备 Lantern Zine。给出三条下一步的建议，说明一下你缺少哪些信息，我告诉你。"
        ),
        language="zh-CN",
        provenance="project-original",
    )
    brief = UserConfirmedContextBrief.confirm(
        brief_id=str(uuid4()),
        profile_id=profile_id,
        timeline_id=timeline_id,
        command_fingerprint=command.payload_fingerprint,
        language=command.language,
        confirmed_facts=(),
        acknowledged_unknowns=(),
    )
    request = CognitionProviderRequest(
        request_id=str(uuid4()),
        request_digest="a" * 64,
        operation_id=str(uuid4()),
        profile_id=profile_id,
        timeline_id=timeline_id,
        provider="deepseek-official-api",
        model=DEEPSEEK_MODEL,
        current_command=command.utterance,
        language=command.language,
        brief_id=brief.brief_id,
        brief_digest=brief.integrity_digest,
        confirmed_facts=(),
        acknowledged_unknowns=(),
    )
    transport = _SingleResponseTransport()
    provider = DeepSeekCognitionProvider(
        transport=transport,
        egress_approval=OperationEgressApproval.approve(
            approval_id=str(uuid4()),
            operation_id=request.operation_id,
            outbound_digest=DeepSeekCognitionProvider.outbound_digest(request),
            disclosure=DeepSeekCognitionProvider.terms_disclosure(),
        ),
    )
    cognition = ApprovedDeepSeekCognition(
        provider=provider,
        context_brief=brief,
        operation_reservation=OperationEgressReservation.reserve(
            operation_id=request.operation_id,
            binding_id=str(uuid4()),
            profile_id=profile_id,
            timeline_id=timeline_id,
            command_fingerprint=command.payload_fingerprint,
            provider_authority=provider.descriptor.authority_id,
        ),
        credential_ref=CredentialRef.reference(
            backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
            key_id=DEEPSEEK_CREDENTIAL_KEY_ID,
        ),
    )

    with pytest.raises(PreAdmissionRejected) as caught:
        cognition.preflight(
            context=CognitionRuntimeView(
                runtime_authority_id=str(uuid4()),
                profile_id=profile_id,
                timeline_id=timeline_id,
                provider_authority=provider.descriptor.authority_id,
                relationship_enabled=False,
                fixture=False,
            ),
            command=command,
        )

    assert caught.value.code == "operation-egress-reservation-mismatch"
    assert transport.calls == 0


def test_deepseek_route_cannot_be_constructed_without_an_operation_approval() -> None:
    transport = _SingleResponseTransport()

    with pytest.raises(TypeError, match="egress_approval"):
        DeepSeekCognitionProvider(
            transport=transport,
            egress_approval=None,  # type: ignore[arg-type]
        )

    assert transport.calls == 0
