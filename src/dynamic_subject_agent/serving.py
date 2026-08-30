"""Minimal framework-free CLI above the mature ApplicationFacade."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from dynamic_subject_agent.application import (
    ApplicationFacade,
    ApplicationOperationStatus,
    ApplicationQuery,
    ApplicationQueryKind,
    ApplicationQueryStatus,
    LivingMemoryApplicationProjection,
)
from dynamic_subject_agent.knowledge_entries import knowledge_entry_by_id
from dynamic_subject_agent.timeline import SubjectCommand


def run_cli(
    application: ApplicationFacade,
    *,
    profile_id: str,
    timeline_id: str,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    """Submit user text only through Facade and show canonical memory projections."""

    if not isinstance(application, ApplicationFacade):
        raise TypeError("run_cli requires the mature ApplicationFacade")
    session_prefix = uuid4().hex
    output_fn("输入 /exit 退出。")
    _print_living_memories(
        application,
        profile_id=profile_id,
        timeline_id=timeline_id,
        output_fn=output_fn,
    )
    ordinal = 0
    while True:
        try:
            user_text = input_fn("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            output_fn("已退出。")
            return 0
        if user_text == "/exit":
            output_fn("已退出。")
            return 0
        if not user_text:
            output_fn("输入为空，未提交。")
            continue
        ordinal += 1
        command = SubjectCommand.contribute_utterance(
            target_profile_id=profile_id,
            target_timeline_id=timeline_id,
            declared_intent="ask-collaborator-status",
            utterance=user_text,
            language="zh",
            provenance="project-original",
        )
        submitted = application.submit(
            command,
            idempotency_key=(
                f"living-memory-cli-{session_prefix}-{ordinal:08d}"
            ),
        )
        response = (
            application.wait(submitted.operation_ref, timeout_seconds=30)
            if submitted.operation_ref is not None
            and submitted.status is ApplicationOperationStatus.PENDING
            else submitted
        )
        if (
            response.status is not ApplicationOperationStatus.TERMINAL
            or response.projection is None
            or response.projection.expression_text is None
        ):
            code = "operation-unavailable"
            stage = None
            if response.projection is not None:
                stage = response.projection.failure_stage
                code = response.projection.failure_code or code
            elif response.problem is not None:
                code = response.problem.code
            output_fn(f"本轮失败关闭: {stage or 'unknown'}:{code}")
            continue
        output_fn(f"AI: {response.projection.expression_text}")
        if response.projection.relationship_event:
            output_fn(f"立场事件: {response.projection.relationship_event}")
        _print_knowledge_citations(response.projection, output_fn)
        _print_living_memories(
            application,
            profile_id=profile_id,
            timeline_id=timeline_id,
            output_fn=output_fn,
        )


def _print_knowledge_citations(projection, output_fn) -> None:
    for entry_id in projection.knowledge_citation_ids:
        entry = knowledge_entry_by_id(entry_id)
        if entry is not None:
            output_fn(
                f"引用[{entry.title}] (entry_id={entry.entry_id}, "
                f"source={entry.source_ref})"
            )


def _print_living_memories(
    application: ApplicationFacade,
    *,
    profile_id: str,
    timeline_id: str,
    output_fn: Callable[[str], None],
) -> None:
    memory_response = application.query(
        ApplicationQuery(
            kind=ApplicationQueryKind.LIVING_MEMORY,
            target_profile_id=profile_id,
            target_timeline_id=timeline_id,
        )
    )
    if (
        memory_response.status is ApplicationQueryStatus.AVAILABLE
        and isinstance(
            memory_response.projection,
            LivingMemoryApplicationProjection,
        )
    ):
        for memory in memory_response.projection.memories:
            output_fn(
                f"记忆[{memory.status}] {memory.content} "
                f"(memory_id={memory.memory_id}, "
                f"source_user_message_id={memory.source_user_message_id})"
            )


__all__ = ["run_cli"]
