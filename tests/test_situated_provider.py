from __future__ import annotations

import json

import pytest

from dynamic_subject_agent.deepseek import (
    DEEPSEEK_CREDENTIAL_BACKEND_ID,
    DEEPSEEK_CREDENTIAL_KEY_ID,
    DEEPSEEK_MODEL,
    DeepSeekHttpResponse,
    DeepSeekSituatedProvider,
    DeepSeekTransport,
    ProviderFailure,
)
from dynamic_subject_agent.situated_cognition import (
    SituatedClassificationRequest,
    SituatedReplyRequest,
)
from dynamic_subject_agent.situated_state import SituatedStateTarget


def _response(content: dict) -> DeepSeekHttpResponse:
    return DeepSeekHttpResponse(
        200,
        json.dumps(
            {
                "model": DEEPSEEK_MODEL,
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(content, ensure_ascii=False),
                            "reasoning_content": None,
                            "tool_calls": None,
                        }
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 40},
            },
            ensure_ascii=False,
        ).encode("utf-8"),
    )


class _Transport(DeepSeekTransport):
    def __init__(self, *contents: dict) -> None:
        self.contents = list(contents)
        self.bodies = []

    def post_json(self, *, endpoint, body, credential_ref, timeout_seconds):
        self.bodies.append(body)
        return _response(self.contents.pop(0))


def _provider(transport):
    from dynamic_subject_agent.cognition import CredentialRef

    return DeepSeekSituatedProvider(
        transport=transport,
        credential_ref=CredentialRef.reference(
            backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
            key_id=DEEPSEEK_CREDENTIAL_KEY_ID,
        ),
    )


def test_situated_projection_and_reply_are_isolated() -> None:
    transport = _Transport(
        {
            "action": "noop",
            "posture": None,
            "evidence_quote": None,
            "experience_summary": None,
            "language": "zh",
        },
        {"reply_text": "我会温和地继续。", "language": "zh"},
    )
    provider = _provider(transport)
    request = SituatedClassificationRequest(
        "继续。",
        (SituatedStateTarget("gentle", 1, 900),),
    )
    result = provider.classify(request)
    reply = provider.reply(SituatedReplyRequest("继续。", "gentle"))

    assert result.candidate is None
    assert result.experience_summary == ""
    assert reply.reply_text == "我会温和地继续。"
    classification = json.loads(transport.bodies[0].decode("utf-8"))
    projection = json.loads(classification["messages"][1]["content"])
    assert set(projection) == {"current_user_message", "active_state", "policy"}
    assert projection["active_state"] == [
        {"posture": "gentle", "remaining_turns": 1, "expires_in_seconds": 900}
    ]
    reply_body = json.loads(transport.bodies[1].decode("utf-8"))
    assert "只输出一个短句" in reply_body["messages"][0]["content"]
    reply_projection = json.loads(reply_body["messages"][1]["content"])
    assert reply_projection == {
        "current_user_message": "继续。",
        "selected_state": {"posture": "gentle"},
    }
    serialized = json.dumps([projection, reply_projection], ensure_ascii=False)
    for forbidden in (
        "memory",
        "knowledge",
        "relationship",
        "goal",
        "timeline_id",
        "session_id",
        "api_key",
    ):
        assert forbidden not in serialized.casefold()


def test_situated_adapter_rejects_nonverbatim_and_extra_fields() -> None:
    nonverbatim = {
        "action": "set",
        "posture": "focused",
        "evidence_quote": "不存在的证据",
        "experience_summary": "",
        "language": "zh",
    }
    with pytest.raises(ProviderFailure):
        _provider(_Transport(nonverbatim)).classify(
            SituatedClassificationRequest("继续。", ())
        )

    extra = {
        "action": "noop",
        "posture": None,
        "evidence_quote": "",
        "experience_summary": "",
        "language": "zh",
        "hidden_state": "forbidden",
    }
    with pytest.raises(ProviderFailure):
        _provider(_Transport(extra)).classify(
            SituatedClassificationRequest("继续。", ())
        )
