from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from dynamic_subject_agent.timeline import SubjectCommand
from test_runtime_host_binding import _publish_qri


class _CreateMemoryProvider:
    def __init__(self) -> None:
        self.requests = []

    def analyze(self, request):
        from dynamic_subject_agent.living_memory import (
            LivingMemoryAction,
            LivingMemoryProposal,
            LivingMemoryProviderResult,
        )

        self.requests.append(request)
        return LivingMemoryProviderResult(
            proposal=LivingMemoryProposal(
                action=LivingMemoryAction.CREATE,
                evidence_quote="每周三晚上上课",
            ),
            experience_summary="用户说明了固定课程时间。",
            reply_text="我会记住你每周三晚上有课。",
            language="zh",
        )


class _CreateThenRecallProvider:
    def __init__(self) -> None:
        self.requests = []

    def analyze(self, request):
        from dynamic_subject_agent.living_memory import (
            LivingMemoryAction,
            LivingMemoryProposal,
            LivingMemoryProviderResult,
        )

        self.requests.append(request)
        if not request.active_memories:
            proposal = LivingMemoryProposal(
                action=LivingMemoryAction.CREATE,
                evidence_quote="每周三晚上上课",
            )
            reply = "我会记住你每周三晚上有课。"
        else:
            proposal = LivingMemoryProposal(
                action=LivingMemoryAction.NONE,
                evidence_quote="",
                recalled_memory_ids=(request.active_memories[0].memory_id,),
            )
            reply = "那我们避开你每周三晚上的课程再细聊。"
        return LivingMemoryProviderResult(
            proposal=proposal,
            experience_summary="Living Memory fake provider 完成本轮建议。",
            reply_text=reply,
            language="zh",
        )


class _CreateThenReviseProvider:
    def __init__(self, *, foreign_revision: bool = False) -> None:
        self.foreign_revision = foreign_revision

    def analyze(self, request):
        from dynamic_subject_agent.living_memory import (
            LivingMemoryAction,
            LivingMemoryProposal,
            LivingMemoryProviderResult,
        )

        if not request.active_memories:
            proposal = LivingMemoryProposal(
                action=LivingMemoryAction.CREATE,
                evidence_quote="每周三晚上上课",
            )
        else:
            proposal = LivingMemoryProposal(
                action=LivingMemoryAction.REVISE,
                evidence_quote="课程改到周四晚上",
                supersedes_memory_id=(
                    str(uuid4())
                    if self.foreign_revision
                    else request.active_memories[0].memory_id
                ),
            )
        return LivingMemoryProviderResult(
            proposal=proposal,
            experience_summary="fake provider 提议课程时间记忆。",
            reply_text="我已按你这次说明理解课程时间。",
            language="zh",
        )


class _BirthdayCorrectionProvider:
    def __init__(self) -> None:
        self.requests = []

    def analyze(self, request):
        from dynamic_subject_agent.living_memory import (
            LivingMemoryAction,
            LivingMemoryProposal,
            LivingMemoryProviderResult,
        )

        self.requests.append(request)
        if len(self.requests) == 1:
            proposal = LivingMemoryProposal(
                action=LivingMemoryAction.CREATE,
                evidence_quote="我的生日是四月五号",
            )
            reply = "好的，我记住了，你的生日是四月五号。"
        elif len(self.requests) == 2:
            proposal = LivingMemoryProposal(
                action=LivingMemoryAction.REVISE,
                evidence_quote="我是7月20号的生日",
                supersedes_memory_id=request.active_memories[0].memory_id,
            )
            reply = "好的，我记住了，你的生日是7月20号。"
        else:
            proposal = LivingMemoryProposal(
                action=LivingMemoryAction.NONE,
                evidence_quote="",
                recalled_memory_ids=(request.active_memories[0].memory_id,),
            )
            reply = "你之前说错的生日是7月20号。"
        return LivingMemoryProviderResult(
            proposal=proposal,
            experience_summary="fake provider 处理生日记忆。",
            reply_text=reply,
            language="zh",
        )


class _CreateEveryTurnProvider:
    def __init__(self) -> None:
        self.requests = []

    def analyze(self, request):
        from dynamic_subject_agent.living_memory import (
            LivingMemoryAction,
            LivingMemoryProposal,
            LivingMemoryProviderResult,
        )

        self.requests.append(request)
        return LivingMemoryProviderResult(
            proposal=LivingMemoryProposal(
                action=LivingMemoryAction.CREATE,
                evidence_quote=request.current_user_message,
            ),
            experience_summary="fake provider 提议形成一条记忆。",
            reply_text="已收到。",
            language="zh",
        )


class _FailingProvider:
    def analyze(self, request):
        del request
        raise RuntimeError("fake provider unavailable")


class _ForeignRecallProvider:
    def analyze(self, request):
        from dynamic_subject_agent.living_memory import (
            LivingMemoryAction,
            LivingMemoryProposal,
            LivingMemoryProviderResult,
        )

        return LivingMemoryProviderResult(
            proposal=LivingMemoryProposal(
                action=LivingMemoryAction.NONE,
                evidence_quote="",
                recalled_memory_ids=(str(uuid4()),),
            ),
            experience_summary="fake provider 返回了越界 recall。",
            reply_text="这条回复不应发布。",
            language="zh",
        )


def _command(qri, timeline_id: str, utterance: str) -> SubjectCommand:
    return SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance=utterance,
        language="zh",
        provenance="project-original",
    )


def test_facade_forms_memory_from_provider_evidence_in_submitted_user_message(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import (
        ApplicationOperationStatus,
        ApplicationQuery,
        ApplicationQueryKind,
        ApplicationQueryStatus,
        LivingMemoryApplicationProjection,
    )
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    provider = _CreateMemoryProvider()
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=ControlledLivingMemoryCognition(provider=provider),
    )
    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance="我每周三晚上上课，所以那时不适合长聊。",
        language="zh",
        provenance="project-original",
    )
    try:
        submitted = composition.application.submit(
            command,
            idempotency_key="living-memory-create-0001",
        )
        terminal = composition.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )
        memories = composition.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.LIVING_MEMORY,
                target_profile_id=qri.profile_id,
                target_timeline_id=timeline_id,
            )
        )
    finally:
        composition.close()

    assert terminal.status is ApplicationOperationStatus.TERMINAL
    assert terminal.projection is not None
    assert terminal.projection.expression_text == "我会记住你每周三晚上有课。"
    assert terminal.projection.living_memory_status == "accepted"
    assert memories.status is ApplicationQueryStatus.AVAILABLE
    assert isinstance(memories.projection, LivingMemoryApplicationProjection)
    assert len(memories.projection.memories) == 1
    memory = memories.projection.memories[0]
    assert memory.content == "每周三晚上上课"
    assert memory.source_user_message_id == terminal.operation_ref.operation_id
    assert memory.status == "active"


def test_facade_recalls_active_memory_and_restores_it_after_restart(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import (
        ApplicationOperationStatus,
        ApplicationQuery,
        ApplicationQueryKind,
        LivingMemoryApplicationProjection,
    )
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    provider = _CreateThenRecallProvider()
    first = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=ControlledLivingMemoryCognition(provider=provider),
    )
    created = first.application.submit(
        _command(qri, timeline_id, "我每周三晚上上课，所以那时不适合长聊。"),
        idempotency_key="living-memory-restart-0001",
    )
    created_terminal = first.application.wait(
        created.operation_ref,
        timeout_seconds=5,
    )
    recalled = first.application.submit(
        _command(qri, timeline_id, "我们什么时候适合细聊最近的创作？"),
        idempotency_key="living-memory-restart-0002",
    )
    recalled_terminal = first.application.wait(
        recalled.operation_ref,
        timeout_seconds=5,
    )
    host_location = first.host_location
    first.close()

    restarted = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
        _cognition=ControlledLivingMemoryCognition(provider=provider),
    )
    try:
        restored = restarted.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.LIVING_MEMORY,
                target_profile_id=qri.profile_id,
                target_timeline_id=timeline_id,
            )
        )
    finally:
        restarted.close()

    assert created_terminal.status is ApplicationOperationStatus.TERMINAL
    assert recalled_terminal.status is ApplicationOperationStatus.TERMINAL
    assert recalled_terminal.projection is not None
    assert recalled_terminal.projection.living_memory_status == "no-op"
    assert recalled_terminal.projection.expression_text == (
        "那我们避开你每周三晚上的课程再细聊。"
    )
    assert len(provider.requests) == 2
    assert set(asdict(provider.requests[1])) == {
        "current_user_message",
        "active_memories",
    }
    assert len(provider.requests[1].active_memories) == 1
    assert recalled_terminal.projection.living_memory_recalled_ids == (
        provider.requests[1].active_memories[0].memory_id,
    )
    assert set(asdict(provider.requests[1].active_memories[0])) == {
        "memory_id",
        "content",
        "source_user_message_id",
    }
    assert isinstance(restored.projection, LivingMemoryApplicationProjection)
    assert restored.projection.memories[0].content == "每周三晚上上课"
    assert restored.projection.memories[0].source_user_message_id == (
        created_terminal.operation_ref.operation_id
    )


def test_facade_revises_active_memory_without_erasing_history(tmp_path: Path) -> None:
    from dynamic_subject_agent.application import (
        ApplicationQuery,
        ApplicationQueryKind,
        LivingMemoryApplicationProjection,
    )
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    provider = _CreateThenReviseProvider()
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=ControlledLivingMemoryCognition(provider=provider),
    )
    try:
        first = composition.application.submit(
            _command(qri, timeline_id, "我每周三晚上上课，所以那时不适合长聊。"),
            idempotency_key="living-memory-revise-0001",
        )
        first_terminal = composition.application.wait(
            first.operation_ref,
            timeout_seconds=5,
        )
        second = composition.application.submit(
            _command(qri, timeline_id, "课程改到周四晚上了，周三已经空出来。"),
            idempotency_key="living-memory-revise-0002",
        )
        second_terminal = composition.application.wait(
            second.operation_ref,
            timeout_seconds=5,
        )
        result = composition.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.LIVING_MEMORY,
                target_profile_id=qri.profile_id,
                target_timeline_id=timeline_id,
            )
        )
    finally:
        composition.close()

    assert first_terminal.projection is not None
    assert first_terminal.projection.living_memory_status == "accepted"
    assert second_terminal.projection is not None
    assert second_terminal.projection.living_memory_status == "accepted"
    assert isinstance(result.projection, LivingMemoryApplicationProjection)
    assert [memory.content for memory in result.projection.memories] == [
        "课程改到周四晚上",
        "每周三晚上上课",
    ]
    assert [memory.status for memory in result.projection.memories] == [
        "active",
        "superseded",
    ]
    assert result.projection.memories[0].supersedes_memory_id == (
        result.projection.memories[1].memory_id
    )


def test_facade_can_answer_with_the_superseded_value_after_a_correction(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    provider = _BirthdayCorrectionProvider()
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=ControlledLivingMemoryCognition(provider=provider),
    )
    try:
        for sequence, utterance in enumerate(
            (
                "我的生日是四月五号。",
                "我的生日之前和你说错了，我是7月20号的生日。",
                "我之前说的错误的生日是什么时候来着？",
            ),
            start=1,
        ):
            submitted = composition.application.submit(
                _command(qri, timeline_id, utterance),
                idempotency_key=f"living-memory-birthday-correction-{sequence}",
            )
            terminal = composition.application.wait(
                submitted.operation_ref,
                timeout_seconds=5,
            )
    finally:
        composition.close()

    assert terminal.projection is not None
    assert "四月五号" in terminal.projection.expression_text
    assert len(provider.requests[2].active_memories) == 1
    assert "7月20号" in provider.requests[2].active_memories[0].content
    assert "四月五号" not in provider.requests[2].active_memories[0].content


def test_facade_rejects_revision_id_outside_current_active_memories(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import (
        ApplicationQuery,
        ApplicationQueryKind,
        LivingMemoryApplicationProjection,
    )
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    provider = _CreateThenReviseProvider(foreign_revision=True)
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=ControlledLivingMemoryCognition(provider=provider),
    )
    try:
        first = composition.application.submit(
            _command(qri, timeline_id, "我每周三晚上上课，所以那时不适合长聊。"),
            idempotency_key="living-memory-reject-0001",
        )
        composition.application.wait(first.operation_ref, timeout_seconds=5)
        second = composition.application.submit(
            _command(qri, timeline_id, "课程改到周四晚上了。"),
            idempotency_key="living-memory-reject-0002",
        )
        rejected = composition.application.wait(
            second.operation_ref,
            timeout_seconds=5,
        )
        result = composition.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.LIVING_MEMORY,
                target_profile_id=qri.profile_id,
                target_timeline_id=timeline_id,
            )
        )
    finally:
        composition.close()

    assert rejected.projection is not None
    assert rejected.projection.living_memory_status == "rejected"
    assert isinstance(result.projection, LivingMemoryApplicationProjection)
    assert len(result.projection.memories) == 1
    assert result.projection.memories[0].content == "每周三晚上上课"
    assert result.projection.memories[0].status == "active"


def test_provider_projection_caps_active_memories_at_twenty(tmp_path: Path) -> None:
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    provider = _CreateEveryTurnProvider()
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=ControlledLivingMemoryCognition(provider=provider),
    )
    try:
        for index in range(21):
            submitted = composition.application.submit(
                _command(qri, timeline_id, f"第 {index:02d} 条长期偏好"),
                idempotency_key=f"living-memory-cap-{index:04d}",
            )
            composition.application.wait(submitted.operation_ref, timeout_seconds=5)
    finally:
        composition.close()

    assert len(provider.requests) == 21
    assert len(provider.requests[-1].active_memories) == 20
    assert provider.requests[-1].active_memories[0].content == "第 19 条长期偏好"
    assert provider.requests[-1].active_memories[-1].content == "第 00 条长期偏好"


def test_provider_failure_is_failed_closed_without_memory_write(tmp_path: Path) -> None:
    from dynamic_subject_agent.application import (
        ApplicationOperationStatus,
        ApplicationQuery,
        ApplicationQueryKind,
        LivingMemoryApplicationProjection,
    )
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=ControlledLivingMemoryCognition(provider=_FailingProvider()),
    )
    try:
        submitted = composition.application.submit(
            _command(qri, timeline_id, "这条输入不应形成记忆。"),
            idempotency_key="living-memory-provider-failure-0001",
        )
        failed = composition.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )
        result = composition.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.LIVING_MEMORY,
                target_profile_id=qri.profile_id,
                target_timeline_id=timeline_id,
            )
        )
    finally:
        composition.close()

    assert failed.status is ApplicationOperationStatus.TERMINAL
    assert failed.projection is not None
    assert failed.projection.living_memory_status == "failed-closed"
    assert failed.projection.failure_code is None
    assert isinstance(result.projection, LivingMemoryApplicationProjection)
    assert result.projection.memories == ()


def test_foreign_recall_id_fails_closed_before_reply_publication(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import ApplicationOperationStatus
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=ControlledLivingMemoryCognition(provider=_ForeignRecallProvider()),
    )
    try:
        submitted = composition.application.submit(
            _command(qri, timeline_id, "我们什么时候适合细聊？"),
            idempotency_key="living-memory-foreign-recall-0001",
        )
        failed = composition.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )
    finally:
        composition.close()

    assert failed.status is ApplicationOperationStatus.TERMINAL
    assert failed.projection is not None
    assert failed.projection.living_memory_status == "failed-closed"
    assert failed.projection.failure_code is None
    assert failed.projection.expression_text


def test_minimal_cli_routes_through_facade_and_shows_memory_source(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition
    from dynamic_subject_agent.serving import run_cli

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=ControlledLivingMemoryCognition(provider=_CreateMemoryProvider()),
    )
    scripted = iter(("我每周三晚上上课，所以那时不适合长聊。", "/exit"))
    output: list[str] = []
    try:
        exit_code = run_cli(
            composition.application,
            profile_id=qri.profile_id,
            timeline_id=timeline_id,
            input_fn=lambda _prompt: next(scripted),
            output_fn=output.append,
        )
    finally:
        composition.close()

    assert exit_code == 0
    assert "AI: 我会记住你每周三晚上有课。" in output
    memory_line = next(line for line in output if line.startswith("记忆[active]"))
    assert "每周三晚上上课" in memory_line
    assert "source_user_message_id=" in memory_line


def test_restarted_cli_shows_restored_memory_before_input_and_submits_new_message(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition
    from dynamic_subject_agent.serving import run_cli

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    provider = _CreateThenRecallProvider()
    first = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=ControlledLivingMemoryCognition(provider=provider),
    )
    first_inputs = iter(("我每周三晚上上课，所以那时不适合长聊。", "/exit"))
    try:
        assert run_cli(
            first.application,
            profile_id=qri.profile_id,
            timeline_id=timeline_id,
            input_fn=lambda _prompt: next(first_inputs),
            output_fn=lambda _line: None,
        ) == 0
        host_location = first.host_location
    finally:
        first.close()

    restarted = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
        _cognition=ControlledLivingMemoryCognition(provider=provider),
    )
    output: list[str] = []
    restarted_inputs = iter(("我们什么时候适合细聊最近的创作？", "/exit"))
    input_calls = 0

    def restarted_input(_prompt: str) -> str:
        nonlocal input_calls
        input_calls += 1
        if input_calls == 1:
            assert any(line.startswith("记忆[active]") for line in output)
        return next(restarted_inputs)

    try:
        exit_code = run_cli(
            restarted.application,
            profile_id=qri.profile_id,
            timeline_id=timeline_id,
            input_fn=restarted_input,
            output_fn=output.append,
        )
    finally:
        restarted.close()

    assert exit_code == 0
    assert len(provider.requests) == 2
    assert "AI: 那我们避开你每周三晚上的课程再细聊。" in output
    assert not any(line.startswith("本轮失败关闭:") for line in output)


def test_default_profile_deepseek_adapter_uses_only_authorized_projection() -> None:
    import json

    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import (
        DEEPSEEK_CREDENTIAL_BACKEND_ID,
        DEEPSEEK_CREDENTIAL_KEY_ID,
        DEEPSEEK_ENDPOINT,
        DEEPSEEK_MODEL,
        DEEPSEEK_PROVIDER_AUTHORITY_ID,
        DeepSeekHttpResponse,
        DeepSeekLivingMemoryProvider,
        DeepSeekTransport,
    )
    from dynamic_subject_agent.living_memory import (
        ControlledLivingMemoryCognition,
        LivingMemoryProviderMemory,
        LivingMemoryProviderRequest,
    )

    class CapturingTransport(DeepSeekTransport):
        def __init__(self) -> None:
            self.calls = []

        def post_json(
            self,
            *,
            endpoint,
            body,
            credential_ref,
            timeout_seconds,
        ):
            self.calls.append(
                {
                    "endpoint": endpoint,
                    "body": body,
                    "credential_ref": credential_ref,
                    "timeout_seconds": timeout_seconds,
                }
            )
            content = {
                "action": "create",
                "evidence_quote": "每周三晚上上课",
                "memory_kind": "plan",
                "supersedes_memory_id": None,
                "recalled_memory_ids": [],
                "experience_summary": "用户说明了固定课程时间。",
                "reply_text": "我会记住你每周三晚上有课。",
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

    transport = CapturingTransport()
    credential_ref = CredentialRef.reference(
        backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
        key_id=DEEPSEEK_CREDENTIAL_KEY_ID,
    )
    request = LivingMemoryProviderRequest(
        current_user_message="我每周三晚上上课，所以那时不适合长聊。",
        active_memories=(
            LivingMemoryProviderMemory(
                memory_id=str(uuid4()),
                content="我喜欢先看结论",
                source_user_message_id=str(uuid4()),
            ),
        ),
    )
    provider = DeepSeekLivingMemoryProvider(
        transport=transport,
        credential_ref=credential_ref,
    )

    result = provider.analyze(request)
    cognition = ControlledLivingMemoryCognition.for_profile(
        "default",
        deepseek_transport=transport,
        credential_ref=credential_ref,
    )

    assert result.proposal.action.value == "create"
    assert result.proposal.memory_kind == "plan"
    assert result.proposal.evidence_quote == "每周三晚上上课"
    assert result.reply_text == "我会记住你每周三晚上有课。"
    assert cognition.provider_authority == DEEPSEEK_PROVIDER_AUTHORITY_ID
    assert cognition.test_only is False
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["endpoint"] == DEEPSEEK_ENDPOINT
    assert call["credential_ref"] is credential_ref
    outbound = json.loads(call["body"].decode("utf-8"))
    assert set(outbound) == {
        "model",
        "messages",
        "thinking",
        "response_format",
        "max_tokens",
        "temperature",
        "stream",
        "tools",
        "tool_choice",
    }
    assert outbound["thinking"] == {"type": "disabled"}
    assert outbound["response_format"] == {"type": "json_object"}
    provider_projection = json.loads(outbound["messages"][1]["content"])
    assert provider_projection == {
        "current_user_message": request.current_user_message,
        "active_memories": [
            {
                "memory_id": request.active_memories[0].memory_id,
                "content": "我喜欢先看结论",
                "source_user_message_id": (
                    request.active_memories[0].source_user_message_id
                ),
            }
        ],
    }


def test_default_profile_adapter_parses_recall_shaped_none_action() -> None:
    import json

    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import (
        DEEPSEEK_CREDENTIAL_BACKEND_ID,
        DEEPSEEK_CREDENTIAL_KEY_ID,
        DEEPSEEK_MODEL,
        DeepSeekHttpResponse,
        DeepSeekLivingMemoryProvider,
        DeepSeekTransport,
    )
    from dynamic_subject_agent.living_memory import (
        LivingMemoryAction,
        LivingMemoryProviderMemory,
        LivingMemoryProviderRequest,
    )

    memory_id = "11111111-1111-4111-8111-111111111111"

    class RecallTransport(DeepSeekTransport):
        def __init__(self) -> None:
            self.calls = []

        def post_json(
            self,
            *,
            endpoint,
            body,
            credential_ref,
            timeout_seconds,
        ):
            self.calls.append(body)
            content = {
                "action": "none",
                "evidence_quote": "",
                "supersedes_memory_id": None,
                "recalled_memory_ids": [memory_id],
                "experience_summary": "用户询问不便时间，召回相关记忆。",
                "reply_text": "记得，你每周四下午要开组会。",
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

    transport = RecallTransport()
    provider = DeepSeekLivingMemoryProvider(
        transport=transport,
        credential_ref=CredentialRef.reference(
            backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
            key_id=DEEPSEEK_CREDENTIAL_KEY_ID,
        ),
    )
    request = LivingMemoryProviderRequest(
        current_user_message="那你还记得我哪天不方便吗？",
        active_memories=(
            LivingMemoryProviderMemory(
                memory_id=memory_id,
                content="我每周四下午要开组会，那个时间不方便。",
                source_user_message_id=str(uuid4()),
            ),
        ),
    )

    result = provider.analyze(request)

    assert result.proposal.action is LivingMemoryAction.NONE
    assert result.proposal.evidence_quote == ""
    assert result.proposal.recalled_memory_ids == (memory_id,)
    assert result.reply_text == "记得，你每周四下午要开组会。"
    assert result.language == "zh"
    system_message = json.loads(transport.calls[0].decode("utf-8"))["messages"][0][
        "content"
    ]
    assert "始终以 Avery 第一人称表达" in system_message
    assert "不得声称或提议提醒" in system_message
    assert "action 必须为 none" in system_message
    assert "recalled_memory_ids" in system_message


def test_living_memory_adapter_rejects_create_without_memory_kind() -> None:
    import json

    import pytest

    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import (
        DEEPSEEK_CREDENTIAL_BACKEND_ID,
        DEEPSEEK_CREDENTIAL_KEY_ID,
        DEEPSEEK_MODEL,
        DeepSeekHttpResponse,
        DeepSeekLivingMemoryProvider,
        DeepSeekTransport,
    )

    class MissingKindTransport(DeepSeekTransport):
        def post_json(self, *, endpoint, body, credential_ref, timeout_seconds):
            content = {
                "action": "create",
                "evidence_quote": "每周三晚上上课",
                "supersedes_memory_id": None,
                "recalled_memory_ids": [],
                "experience_summary": "用户说明了固定课程时间。",
                "reply_text": "我会记住你每周三晚上有课。",
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
                                        content, ensure_ascii=False
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

    from dynamic_subject_agent.cognition import CredentialRef as _CR
    from dynamic_subject_agent.deepseek import (
        DEEPSEEK_CREDENTIAL_BACKEND_ID as _B,
        DEEPSEEK_CREDENTIAL_KEY_ID as _K,
        DeepSeekLivingMemoryProvider as _P,
    )

    provider = _P(
        transport=MissingKindTransport(),
        credential_ref=_CR.reference(backend_id=_B, key_id=_K),
    )
    from dynamic_subject_agent.living_memory import LivingMemoryProviderRequest

    request = LivingMemoryProviderRequest(
        current_user_message="我每周三晚上上课。",
        active_memories=(),
    )
    from dynamic_subject_agent.deepseek import ProviderFailure

    with pytest.raises(ProviderFailure):
        provider.analyze(request)
