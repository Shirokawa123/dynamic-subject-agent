from __future__ import annotations

import json

import pytest

from dynamic_subject_agent.deepseek import (
    DEEPSEEK_CREDENTIAL_BACKEND_ID,
    DEEPSEEK_CREDENTIAL_KEY_ID,
    DEEPSEEK_MODEL,
    DeepSeekHttpResponse,
    DeepSeekParticipantGoalProvider,
    DeepSeekTransport,
    ProviderFailure,
)
from dynamic_subject_agent.participant_goal_cognition import (
    ParticipantGoalClassificationRequest,
    ParticipantGoalProviderRecord,
    ParticipantGoalReplyRecord,
    ParticipantGoalReplyRequest,
)


def _response(content: dict) -> DeepSeekHttpResponse:
    return DeepSeekHttpResponse(
        status_code=200,
        body=json.dumps(
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
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            },
            ensure_ascii=False,
        ).encode("utf-8"),
    )


class _ScriptedTransport(DeepSeekTransport):
    def __init__(self, *contents: dict) -> None:
        self.contents = list(contents)
        self.bodies = []

    def post_json(self, *, endpoint, body, credential_ref, timeout_seconds):
        self.bodies.append(body)
        return _response(self.contents.pop(0))


def _provider(transport: DeepSeekTransport) -> DeepSeekParticipantGoalProvider:
    from dynamic_subject_agent.cognition import CredentialRef

    return DeepSeekParticipantGoalProvider(
        transport=transport,
        credential_ref=CredentialRef.reference(
            backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
            key_id=DEEPSEEK_CREDENTIAL_KEY_ID,
        ),
    )


def test_two_stage_projection_contains_no_persistent_ids_or_other_domains() -> None:
    transport = _ScriptedTransport(
        {
            "action": "noop",
            "kind": None,
            "terms": None,
            "target_ref": None,
            "next_status": None,
            "evidence_quote": "",
            "selected_turn_refs": ["target-1"],
            "experience_summary": "选中现有目标用于回复。",
            "language": "zh",
        },
        {"reply_text": "你的目标是今年通过 N1。", "language": "zh"},
    )
    provider = _provider(transport)
    classified = provider.classify(
        ParticipantGoalClassificationRequest(
            current_user_message="我的目标是什么？",
            active_records=(
                ParticipantGoalProviderRecord(
                    turn_ref="target-1",
                    kind="goal",
                    terms="今年通过 N1",
                    status="active",
                ),
            ),
        )
    )
    replied = provider.reply(
        ParticipantGoalReplyRequest(
            current_user_message="我的目标是什么？",
            selected_records=(
                ParticipantGoalReplyRecord(
                    kind="goal",
                    terms="今年通过 N1",
                    status="active",
                ),
            ),
        )
    )

    assert classified.selected_turn_refs == ("target-1",)
    assert replied.reply_text == "你的目标是今年通过 N1。"
    classification_body = json.loads(transport.bodies[0].decode("utf-8"))
    classification_projection = json.loads(
        classification_body["messages"][1]["content"]
    )
    assert set(classification_projection) == {
        "current_user_message",
        "active_records",
        "policy",
    }
    assert classification_projection["active_records"] == [
        {
            "turn_ref": "target-1",
            "kind": "goal",
            "terms": "今年通过 N1",
            "status": "active",
        }
    ]
    reply_body = json.loads(transport.bodies[1].decode("utf-8"))
    reply_projection = json.loads(reply_body["messages"][1]["content"])
    assert reply_projection == {
        "current_user_message": "我的目标是什么？",
        "selected_records": [
            {"kind": "goal", "terms": "今年通过 N1", "status": "active"}
        ],
    }
    serialized = json.dumps(
        [classification_projection, reply_projection],
        ensure_ascii=False,
    )
    for forbidden in (
        "record_id",
        "timeline_id",
        "session_id",
        "memory_id",
        "relationship",
        "api_key",
    ):
        assert forbidden not in serialized.casefold()


def test_classification_rejects_unprojected_target_reference() -> None:
    transport = _ScriptedTransport(
        {
            "action": "transition",
            "kind": None,
            "terms": None,
            "target_ref": "invented-target",
            "next_status": "achieved",
            "evidence_quote": "我的目标已达成",
            "selected_turn_refs": [],
            "experience_summary": "",
            "language": "zh",
        }
    )
    provider = _provider(transport)
    with pytest.raises(ProviderFailure):
        provider.classify(
            ParticipantGoalClassificationRequest(
                current_user_message="我的目标已达成。",
                active_records=(),
            )
        )


def test_classification_rejects_extra_provider_field() -> None:
    content = {
        "action": "noop",
        "kind": None,
        "terms": None,
        "target_ref": None,
        "next_status": None,
        "evidence_quote": "",
        "selected_turn_refs": [],
        "experience_summary": "",
        "language": "zh",
        "reasoning": "must not cross the provider seam",
    }
    with pytest.raises(ProviderFailure):
        _provider(_ScriptedTransport(content)).classify(
            ParticipantGoalClassificationRequest(
                current_user_message="继续。",
                active_records=(),
            )
        )
