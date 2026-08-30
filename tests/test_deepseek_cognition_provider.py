from __future__ import annotations

import json
from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest

from dynamic_subject_agent.cognition import (
    CognitionProviderRequest,
    CredentialRef,
    OperationEgressApproval,
    ProviderFailure,
    ProviderFailureCode,
)
from dynamic_subject_agent.deepseek import (
    DEEPSEEK_CREDENTIAL_BACKEND_ID,
    DEEPSEEK_CREDENTIAL_KEY_ID,
    DEEPSEEK_ENDPOINT,
    DEEPSEEK_MODEL,
    DeepSeekCognitionProvider,
    DeepSeekCredentialResolver,
    DeepSeekHttpResponse,
    DeepSeekTransport,
    DeepSeekUrlLibTransport,
)


class _CapturingTransport(DeepSeekTransport):
    def __init__(self, response: DeepSeekHttpResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def post_json(
        self,
        *,
        endpoint: str,
        body: bytes,
        credential_ref: CredentialRef,
        timeout_seconds: float,
    ) -> DeepSeekHttpResponse:
        self.calls.append(
            {
                "endpoint": endpoint,
                "body": body,
                "credential_ref": credential_ref,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.response


class _TimeoutTransport(DeepSeekTransport):
    def __init__(self) -> None:
        self.call_count = 0

    def post_json(
        self,
        *,
        endpoint: str,
        body: bytes,
        credential_ref: CredentialRef,
        timeout_seconds: float,
    ) -> DeepSeekHttpResponse:
        del endpoint, body, credential_ref, timeout_seconds
        self.call_count += 1
        raise TimeoutError("synthetic secret-bearing transport detail")


class _DummyCredentialResolver(DeepSeekCredentialResolver):
    def __init__(self) -> None:
        self.references: list[CredentialRef] = []

    def resolve(self, credential_ref: CredentialRef) -> str:
        self.references.append(credential_ref)
        return "test-only-deepseek-secret"


class _FakeUrlResponse:
    status = 200

    def __enter__(self) -> _FakeUrlResponse:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def read(self, limit: int) -> bytes:
        assert limit == 65_537
        return b'{"ok":true}'


def _request() -> CognitionProviderRequest:
    return CognitionProviderRequest(
        request_id=str(uuid4()),
        request_digest="a" * 64,
        operation_id=str(uuid4()),
        profile_id=str(uuid4()),
        timeline_id=str(uuid4()),
        provider="deepseek-official-api",
        model=DEEPSEEK_MODEL,
        current_command=(
            "Avery，我们正在筹备 Lantern Zine。给出三条下一步的建议，说明一下你缺少哪些信息，我告诉你。"
        ),
        language="zh-cn",
        brief_id=str(uuid4()),
        brief_digest="b" * 64,
        confirmed_facts=(),
        acknowledged_unknowns=(),
    )


def test_confirmed_flash_adapter_emits_only_the_approved_json_body() -> None:
    request = _request()
    response_content = {
        "experience_summary": "已处理当前 Lantern Zine 状态询问。",
        "expression_text": (
            "目前能确认的是我们正在检查下一期能否赶上周五印刷；"
            "你可以先确认印刷档期，其他进度和负责人仍未知。"
        ),
        "language": "zh-cn",
    }
    transport = _CapturingTransport(
        DeepSeekHttpResponse(
            status_code=200,
            body=json.dumps(
                {
                    "id": "chatcmpl-test",
                    "model": DEEPSEEK_MODEL,
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(
                                    response_content,
                                    ensure_ascii=False,
                                ),
                                "reasoning_content": None,
                            },
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 300,
                        "completion_tokens": 80,
                        "total_tokens": 380,
                    },
                },
                ensure_ascii=False,
            ).encode("utf-8"),
        )
    )
    terms = DeepSeekCognitionProvider.terms_disclosure()
    approval = OperationEgressApproval.approve(
        approval_id=str(uuid4()),
        operation_id=request.operation_id,
        outbound_digest=DeepSeekCognitionProvider.outbound_digest(request),
        disclosure=terms,
    )
    provider = DeepSeekCognitionProvider(
        transport=transport,
        egress_approval=approval,
    )
    credential_ref = CredentialRef.reference(
        backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
        key_id=DEEPSEEK_CREDENTIAL_KEY_ID,
    )

    result = provider.generate(request, credential_ref=credential_ref)

    assert result.expression_text == response_content["expression_text"]
    assert result.experience_summary == response_content["experience_summary"]
    assert result.language == "zh-cn"
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["endpoint"] == DEEPSEEK_ENDPOINT
    assert call["credential_ref"] is credential_ref
    assert call["timeout_seconds"] == 30.0
    outbound = json.loads(call["body"].decode("utf-8"))
    assert outbound == {
        "model": "deepseek-v4-flash",
        "messages": [
            {
                "role": "system",
                "content": (
                    "请用简洁、自然的中文回答当前请求。只能使用 "
                    "USER_CONFIRMED_CONTEXT 中的已确认事实；必须明确区分已确认、未知和 "
                    "unavailable，不得编造过去对话、项目进展、承诺、记忆或关系。"
                    "不要输出分析过程、推理过程或内在思维。只返回一个 JSON 对象，"
                    "并且只能包含 experience_summary、expression_text、language 三个字段；"
                    "language 必须是 zh-cn。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "CURRENT_COMMAND:\n"
                    f"{request.current_command}\n\n"
                    "USER_CONFIRMED_CONTEXT:\n"
                    "CONFIRMED_FACTS:\n\n"
                    "UNKNOWNS:"
                ),
            },
        ],
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "max_tokens": 400,
        "temperature": 0.2,
        "stream": False,
        "tools": [],
        "tool_choice": "none",
    }
    serialized = call["body"].decode("utf-8")
    for excluded in (
        request.request_id,
        request.request_digest,
        request.operation_id,
        request.profile_id,
        request.timeline_id,
        request.brief_id,
        request.brief_digest,
    ):
        assert excluded not in serialized


def test_adapter_rejects_changed_outbound_even_with_a_new_digest_approval() -> None:
    changed_request = replace(
        _request(),
        current_command="Avery，关于我们的Lantern Zine，现在进度到哪了？有什么是我需要做的吗？",
    )
    transport = _CapturingTransport(
        DeepSeekHttpResponse(status_code=200, body=b"{}")
    )
    terms = DeepSeekCognitionProvider.terms_disclosure()
    approval = OperationEgressApproval.approve(
        approval_id=str(uuid4()),
        operation_id=changed_request.operation_id,
        outbound_digest=DeepSeekCognitionProvider.outbound_digest(changed_request),
        disclosure=terms,
    )
    provider = DeepSeekCognitionProvider(
        transport=transport,
        egress_approval=approval,
    )

    with pytest.raises(ProviderFailure) as caught:
        provider.generate(
            changed_request,
            credential_ref=CredentialRef.reference(
                backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
                key_id=DEEPSEEK_CREDENTIAL_KEY_ID,
            ),
        )

    assert caught.value.code is ProviderFailureCode.UNAVAILABLE
    assert transport.calls == []


def test_empty_brief_payload_contains_no_history_or_private_context() -> None:
    payload = json.loads(
        DeepSeekCognitionProvider.outbound_bytes(_request()).decode("utf-8")
    )
    user_message = payload["messages"][1]["content"]

    assert user_message == (
        "CURRENT_COMMAND:\n"
        "Avery，我们正在筹备 Lantern Zine。给出三条下一步的建议，说明一下你缺少哪些信息，我告诉你。\n\n"
        "USER_CONFIRMED_CONTEXT:\n"
        "CONFIRMED_FACTS:\n\n"
        "UNKNOWNS:"
    )
    for forbidden in ("M0-15", "Timeline", "legacy", "private", "export"):
        assert forbidden not in user_message


def test_adapter_rejects_context_when_the_confirmed_brief_is_empty() -> None:
    changed_request = replace(
        _request(),
        confirmed_facts=("This test-only fact was not user-confirmed for egress.",),
    )
    transport = _CapturingTransport(
        DeepSeekHttpResponse(status_code=200, body=b"{}")
    )
    terms = DeepSeekCognitionProvider.terms_disclosure()
    provider = DeepSeekCognitionProvider(
        transport=transport,
        egress_approval=OperationEgressApproval.approve(
            approval_id=str(uuid4()),
            operation_id=changed_request.operation_id,
            outbound_digest=DeepSeekCognitionProvider.outbound_digest(changed_request),
            disclosure=terms,
        ),
    )

    with pytest.raises(ProviderFailure) as caught:
        provider.generate(
            changed_request,
            credential_ref=CredentialRef.reference(
                backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
                key_id=DEEPSEEK_CREDENTIAL_KEY_ID,
            ),
        )

    assert caught.value.code is ProviderFailureCode.UNAVAILABLE
    assert transport.calls == []


def test_transport_timeout_is_ambiguous_and_never_retried() -> None:
    request = _request()
    transport = _TimeoutTransport()
    terms = DeepSeekCognitionProvider.terms_disclosure()
    provider = DeepSeekCognitionProvider(
        transport=transport,
        egress_approval=OperationEgressApproval.approve(
            approval_id=str(uuid4()),
            operation_id=request.operation_id,
            outbound_digest=DeepSeekCognitionProvider.outbound_digest(request),
            disclosure=terms,
        ),
    )

    with pytest.raises(ProviderFailure) as caught:
        provider.generate(
            request,
            credential_ref=CredentialRef.reference(
                backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
                key_id=DEEPSEEK_CREDENTIAL_KEY_ID,
            ),
        )

    assert caught.value.code is ProviderFailureCode.DELIVERY_AMBIGUOUS
    assert "synthetic" not in str(caught.value)
    assert transport.call_count == 1


def test_url_transport_builds_the_exact_headers_without_environment_discovery() -> None:
    resolver = _DummyCredentialResolver()
    captured: list[dict[str, Any]] = []

    def opener(request: Any, *, timeout: float) -> _FakeUrlResponse:
        captured.append(
            {
                "url": request.full_url,
                "method": request.get_method(),
                "content_type": request.get_header("Content-type"),
                "authorization": request.get_header("Authorization"),
                "data": request.data,
                "timeout": timeout,
            }
        )
        return _FakeUrlResponse()

    transport = DeepSeekUrlLibTransport(
        credential_resolver=resolver,
        _opener=opener,
    )
    credential_ref = CredentialRef.reference(
        backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
        key_id=DEEPSEEK_CREDENTIAL_KEY_ID,
    )

    response = transport.post_json(
        endpoint=DEEPSEEK_ENDPOINT,
        body=b'{"bounded":true}',
        credential_ref=credential_ref,
        timeout_seconds=30.0,
    )

    assert response == DeepSeekHttpResponse(
        status_code=200,
        body=b'{"ok":true}',
    )
    assert resolver.references == [credential_ref]
    assert captured == [
        {
            "url": DEEPSEEK_ENDPOINT,
            "method": "POST",
            "content_type": "application/json",
            "authorization": "Bearer test-only-deepseek-secret",
            "data": b'{"bounded":true}',
            "timeout": 30.0,
        }
    ]


def test_wrong_credential_identity_is_rejected_before_transport() -> None:
    request = _request()
    transport = _CapturingTransport(
        DeepSeekHttpResponse(status_code=200, body=b"{}")
    )
    terms = DeepSeekCognitionProvider.terms_disclosure()
    provider = DeepSeekCognitionProvider(
        transport=transport,
        egress_approval=OperationEgressApproval.approve(
            approval_id=str(uuid4()),
            operation_id=request.operation_id,
            outbound_digest=DeepSeekCognitionProvider.outbound_digest(request),
            disclosure=terms,
        ),
    )

    with pytest.raises(ProviderFailure) as caught:
        provider.generate(
            request,
            credential_ref=CredentialRef.reference(
                backend_id="another-explicit-boundary",
                key_id=DEEPSEEK_CREDENTIAL_KEY_ID,
            ),
        )

    assert caught.value.code is ProviderFailureCode.UNAVAILABLE
    assert transport.calls == []


def test_reasoning_content_is_rejected_without_projection_or_leak() -> None:
    request = _request()
    raw_reasoning = "test-only raw reasoning that must not cross the adapter"
    transport = _CapturingTransport(
        DeepSeekHttpResponse(
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
                                        "experience_summary": "bounded summary",
                                        "expression_text": "bounded expression",
                                        "language": "zh-cn",
                                    }
                                ),
                                "reasoning_content": raw_reasoning,
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 20,
                    },
                }
            ).encode("utf-8"),
        )
    )
    terms = DeepSeekCognitionProvider.terms_disclosure()
    provider = DeepSeekCognitionProvider(
        transport=transport,
        egress_approval=OperationEgressApproval.approve(
            approval_id=str(uuid4()),
            operation_id=request.operation_id,
            outbound_digest=DeepSeekCognitionProvider.outbound_digest(request),
            disclosure=terms,
        ),
    )

    with pytest.raises(ProviderFailure) as caught:
        provider.generate(
            request,
            credential_ref=CredentialRef.reference(
                backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
                key_id=DEEPSEEK_CREDENTIAL_KEY_ID,
            ),
        )

    assert caught.value.code.value == "invalid-output"
    assert raw_reasoning not in str(caught.value)
    assert len(transport.calls) == 1
