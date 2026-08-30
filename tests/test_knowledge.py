"""Slice-02 behavior tests: sealed knowledge retrieval and citation adjudication."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from dynamic_subject_agent.knowledge_entries import (
    KNOWLEDGE_CANDIDATE_LIMIT,
    KnowledgeEntry,
    select_knowledge_candidates,
)


PRINT_SPEC_ENTRY_ID = "a1f4c2d8-0002-4a61-9e1f-3b5c7d9e0a02"
DEADLINE_ENTRY_ID = "a1f4c2d8-0001-4a61-9e1f-3b5c7d9e0a01"


def test_retrieval_ranks_relevant_entry_first() -> None:
    ranked = select_knowledge_candidates("创刊号要用什么纸？多少页？")
    assert ranked, "印刷规格问题必须命中至少一条条目"
    assert ranked[0].entry_id == PRINT_SPEC_ENTRY_ID


def test_retrieval_returns_empty_for_unrelated_message() -> None:
    assert select_knowledge_candidates("今天天气怎么样？") == ()


def test_retrieval_caps_candidates_and_is_deterministic() -> None:
    message = "印刷 截单 创刊号 样张 发行 市集 牛皮纸 骑马钉"
    first = select_knowledge_candidates(message)
    assert len(first) <= KNOWLEDGE_CANDIDATE_LIMIT
    assert first == select_knowledge_candidates(message)


def test_default_knowledge_adapter_parses_citations_and_teaches_the_contract() -> None:
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import (
        DEEPSEEK_CREDENTIAL_BACKEND_ID,
        DEEPSEEK_CREDENTIAL_KEY_ID,
        DEEPSEEK_MODEL,
        DeepSeekHttpResponse,
        DeepSeekKnowledgeProvider,
        DeepSeekTransport,
    )
    from dynamic_subject_agent.knowledge import KnowledgeProviderRequest

    class CiteTransport(DeepSeekTransport):
        def __init__(self) -> None:
            self.calls = []

        def post_json(self, *, endpoint, body, credential_ref, timeout_seconds):
            self.calls.append(body)
            content = {
                "citations": [PRINT_SPEC_ENTRY_ID],
                "experience_summary": "",
                "reply_text": "创刊号是 32 页，内页用 120g 道林纸。",
                "language": "zh",
            }
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
                                        content,
                                        ensure_ascii=False,
                                    ),
                                    "reasoning_content": None,
                                    "tool_calls": None,
                                }
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 200,
                            "completion_tokens": 80,
                        },
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )

    entry = KnowledgeEntry(
        entry_id=PRINT_SPEC_ENTRY_ID,
        title="创刊号规格",
        content="创刊号目标 32 页。",
        source_ref="project-original:lantern-zine-fixture-v1",
    )
    transport = CiteTransport()
    provider = DeepSeekKnowledgeProvider(
        transport=transport,
        credential_ref=CredentialRef.reference(
            backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
            key_id=DEEPSEEK_CREDENTIAL_KEY_ID,
        ),
    )
    request = KnowledgeProviderRequest(
        current_user_message="创刊号要用什么纸？多少页？",
        candidate_entries=(entry,),
    )

    result = provider.analyze(request)

    assert result.proposal.citation_ids == (PRINT_SPEC_ENTRY_ID,)
    assert result.reply_text == "创刊号是 32 页，内页用 120g 道林纸。"
    assert result.language == "zh"
    body = json.loads(transport.calls[0].decode("utf-8"))
    system_message = body["messages"][0]["content"]
    assert "只能取自 candidate_entries" in system_message
    assert "不得编造" in system_message
    outbound_projection = json.loads(body["messages"][1]["content"])
    assert outbound_projection == {
        "current_user_message": "创刊号要用什么纸？多少页？",
        "candidate_entries": [
            {
                "entry_id": PRINT_SPEC_ENTRY_ID,
                "title": "创刊号规格",
                "content": "创刊号目标 32 页。",
            }
        ],
    }


def test_default_knowledge_profile_adapter_carries_deepseek_authority() -> None:
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import (
        DEEPSEEK_CREDENTIAL_BACKEND_ID,
        DEEPSEEK_CREDENTIAL_KEY_ID,
        DEEPSEEK_PROVIDER_AUTHORITY_ID,
        DeepSeekKnowledgeProvider,
        DeepSeekTransport,
    )
    from dynamic_subject_agent.knowledge import ControlledKnowledgeCognition

    class _NoopTransport(DeepSeekTransport):
        def post_json(self, *, endpoint, body, credential_ref, timeout_seconds):
            raise AssertionError("real transport must not be called in this test")

    cognition = ControlledKnowledgeCognition.for_profile(
        "default",
        deepseek_transport=_NoopTransport(),
        credential_ref=CredentialRef.reference(
            backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
            key_id=DEEPSEEK_CREDENTIAL_KEY_ID,
        ),
    )

    assert cognition.provider_authority == DEEPSEEK_PROVIDER_AUTHORITY_ID
    assert cognition.test_only is False


def test_default_knowledge_adapter_rejects_citation_outside_projection() -> None:
    import json

    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import (
        DEEPSEEK_CREDENTIAL_BACKEND_ID,
        DEEPSEEK_CREDENTIAL_KEY_ID,
        DEEPSEEK_MODEL,
        DeepSeekHttpResponse,
        DeepSeekKnowledgeProvider,
        DeepSeekTransport,
    )
    from dynamic_subject_agent.knowledge import KnowledgeProviderRequest

    class RogueTransport(DeepSeekTransport):
        def post_json(self, *, endpoint, body, credential_ref, timeout_seconds):
            content = {
                "citations": [str(uuid4())],
                "experience_summary": "越界引用。",
                "reply_text": "不应发布。",
                "language": "zh",
            }
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
                                        content,
                                        ensure_ascii=False,
                                    ),
                                    "reasoning_content": None,
                                    "tool_calls": None,
                                }
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 200,
                            "completion_tokens": 80,
                        },
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
            )

    provider = DeepSeekKnowledgeProvider(
        transport=RogueTransport(),
        credential_ref=CredentialRef.reference(
            backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
            key_id=DEEPSEEK_CREDENTIAL_KEY_ID,
        ),
    )
    request = KnowledgeProviderRequest(
        current_user_message="创刊号要用什么纸？",
        candidate_entries=(
            KnowledgeEntry(
                entry_id=PRINT_SPEC_ENTRY_ID,
                title="创刊号规格",
                content="创刊号目标 32 页。",
                source_ref="project-original:lantern-zine-fixture-v1",
            ),
        ),
    )

    from dynamic_subject_agent.deepseek import ProviderFailure

    with pytest.raises(ProviderFailure):
        provider.analyze(request)


class _CiteWhenAvailableProvider:
    def __init__(self) -> None:
        self.requests = []

    def analyze(self, request):
        from dynamic_subject_agent.knowledge import (
            KnowledgeProposal,
            KnowledgeProviderResult,
        )

        self.requests.append(request)
        if request.candidate_entries:
            entry = request.candidate_entries[0]
            return KnowledgeProviderResult(
                proposal=KnowledgeProposal(citation_ids=(entry.entry_id,)),
                experience_summary="回答引用了封存条目。",
                reply_text="根据封存设定：创刊号目标 32 页。",
                language="zh",
            )
        return KnowledgeProviderResult(
            proposal=KnowledgeProposal(citation_ids=()),
            experience_summary="没有可引用的条目。",
            reply_text="这个问题我还没有可引用的来源。",
            language="zh",
        )


def test_facade_grounds_reply_in_sealed_knowledge_and_recovers_after_restart(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.knowledge import ControlledKnowledgeCognition
    from dynamic_subject_agent.timeline import SubjectCommand
    from test_runtime_host_binding import _publish_qri

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    provider = _CiteWhenAvailableProvider()

    def submit_and_wait(application, text, key):
        command = SubjectCommand.contribute_utterance(
            target_profile_id=qri.profile_id,
            target_timeline_id=timeline_id,
            declared_intent="ask-collaborator-status",
            utterance=text,
            language="zh",
            provenance="project-original",
        )
        submitted = application.submit(command, idempotency_key=key)
        return application.wait(submitted.operation_ref, timeout_seconds=30)

    first = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=ControlledKnowledgeCognition(provider=provider),
    )
    try:
        host_location = first.host_location
        covered = submit_and_wait(
            first.application,
            "创刊号要用什么纸？多少页？",
            "knowledge-covered-0001",
        )
    finally:
        first.close()

    assert covered.status.value == "terminal"
    assert covered.projection is not None
    assert covered.projection.expression_text == "根据封存设定：创刊号目标 32 页。"
    assert covered.projection.knowledge_citation_ids == (PRINT_SPEC_ENTRY_ID,)
    assert provider.requests[0].candidate_entries[0].entry_id == PRINT_SPEC_ENTRY_ID

    restarted = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
        _cognition=ControlledKnowledgeCognition(provider=provider),
    )
    try:
        again = submit_and_wait(
            restarted.application,
            "创刊号的纸后来定下来了吗？",
            "knowledge-covered-0002",
        )
    finally:
        restarted.close()

    assert again.projection is not None
    assert again.projection.knowledge_citation_ids == (PRINT_SPEC_ENTRY_ID,)


def test_facade_answers_uncovered_question_without_citation(tmp_path: Path) -> None:
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.knowledge import ControlledKnowledgeCognition
    from dynamic_subject_agent.timeline import SubjectCommand
    from test_runtime_host_binding import _publish_qri

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    provider = _CiteWhenAvailableProvider()
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=ControlledKnowledgeCognition(provider=provider),
    )
    try:
        command = SubjectCommand.contribute_utterance(
            target_profile_id=qri.profile_id,
            target_timeline_id=timeline_id,
            declared_intent="ask-collaborator-status",
            utterance="今天天气怎么样？",
            language="zh",
            provenance="project-original",
        )
        submitted = composition.application.submit(
            command,
            idempotency_key="knowledge-uncovered-0001",
        )
        terminal = composition.application.wait(
            submitted.operation_ref,
            timeout_seconds=30,
        )
    finally:
        composition.close()

    assert terminal.projection is not None
    assert terminal.projection.expression_text == "这个问题我还没有可引用的来源。"
    assert terminal.projection.knowledge_citation_ids == ()
    assert provider.requests[0].candidate_entries == ()


def test_serving_cli_prints_cited_entry_lines(tmp_path: Path) -> None:
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.knowledge import ControlledKnowledgeCognition
    from dynamic_subject_agent.serving import run_cli
    from test_runtime_host_binding import _publish_qri

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    provider = _CiteWhenAvailableProvider()
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=ControlledKnowledgeCognition(provider=provider),
    )
    inputs = iter(("创刊号要用什么纸？多少页？", "/exit"))
    output: list[str] = []
    try:
        exit_code = run_cli(
            composition.application,
            profile_id=qri.profile_id,
            timeline_id=timeline_id,
            input_fn=lambda _prompt: next(inputs),
            output_fn=output.append,
        )
    finally:
        composition.close()

    assert exit_code == 0
    assert any(
        line.startswith("引用[") and PRINT_SPEC_ENTRY_ID in line for line in output
    )
    assert not any(line.startswith("本轮失败关闭") for line in output)
