from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from dynamic_subject_agent.temporal_grounding import (
    TemporalAnchor,
    TemporalGrounding,
    TemporalGroundingFailedClosed,
)


def _us(year: int, month: int, day: int, hour: int = 12) -> int:
    return int(
        datetime(
            year,
            month,
            day,
            hour,
            tzinfo=ZoneInfo("Asia/Shanghai"),
        ).timestamp()
        * 1_000_000
    )


def test_relative_day_anchor_keeps_evidence_and_rerenders_across_days() -> None:
    grounding = TemporalGrounding()
    original = "我后天要学习 LLM"
    anchor = grounding.anchor(original, observed_at_us=_us(2026, 9, 1))
    assert anchor == TemporalAnchor(
        original_expression="后天",
        anchor_date="2026-09-01",
        target_date="2026-09-03",
    )
    assert grounding.render(original, anchor, observed_at_us=_us(2026, 9, 1)) == original
    assert grounding.render(original, anchor, observed_at_us=_us(2026, 9, 2)) == (
        "我明天要学习 LLM"
    )
    assert grounding.render(original, anchor, observed_at_us=_us(2026, 9, 3)) == (
        "我今天要学习 LLM"
    )
    assert grounding.render(original, anchor, observed_at_us=_us(2026, 9, 4)) == (
        "我昨天要学习 LLM"
    )


def test_explicit_dates_and_timezone_day_boundary_are_deterministic() -> None:
    grounding = TemporalGrounding()
    anchored = grounding.anchor(
        "我计划在 2026年9月3日 学习 LLM",
        observed_at_us=_us(2026, 9, 1, 23),
    )
    assert anchored is not None
    assert anchored.anchor_date == "2026-09-01"
    assert anchored.target_date == "2026-09-03"
    assert grounding.render(
        "我计划在 2026年9月3日 学习 LLM",
        anchored,
        observed_at_us=_us(2026, 9, 2),
    ) == "我计划在 明天 学习 LLM"


@pytest.mark.parametrize(
    "text",
    [
        "我过几天学习 LLM",
        "我明天或后天学习 LLM",
        "我在 2026-02-30 学习 LLM",
        "我今天确认 2026-09-03 的安排",
        "没有时间表达",
    ],
)
def test_ambiguous_invalid_or_unsupported_time_is_unanchored(text: str) -> None:
    assert TemporalGrounding().anchor(text, observed_at_us=_us(2026, 9, 1)) is None


def test_anchor_round_trip_and_render_integrity_fail_closed() -> None:
    grounding = TemporalGrounding()
    anchor = grounding.anchor("我后天学习", observed_at_us=_us(2026, 9, 1))
    assert anchor is not None
    assert TemporalAnchor.from_dict(anchor.to_dict()) == anchor
    with pytest.raises(TemporalGroundingFailedClosed):
        grounding.render("我明天学习", anchor, observed_at_us=_us(2026, 9, 2))
    payload = anchor.to_dict()
    payload["target_date"] = "not-a-date"
    with pytest.raises(TemporalGroundingFailedClosed):
        TemporalAnchor.from_dict(payload)
    payload = anchor.to_dict()
    payload["target_date"] = "2026-09-04"
    with pytest.raises(TemporalGroundingFailedClosed):
        TemporalAnchor.from_dict(payload)


class _TemporalMemoryProvider:
    def __init__(self) -> None:
        self.requests = []

    def analyze(self, request):
        from dynamic_subject_agent.living_memory import (
            LivingMemoryAction,
            LivingMemoryProposal,
            LivingMemoryProviderResult,
        )

        self.requests.append(request)
        if "后天" in request.current_user_message:
            proposal = LivingMemoryProposal(
                action=LivingMemoryAction.CREATE,
                evidence_quote="我后天要学习 LLM",
                memory_kind="plan",
            )
            reply = "我记下了这个学习计划。"
        else:
            proposal = LivingMemoryProposal(
                action=LivingMemoryAction.NONE,
                evidence_quote="",
                recalled_memory_ids=(request.active_memories[0].memory_id,),
            )
            reply = f"你说的是：{request.active_memories[0].content}。"
        return LivingMemoryProviderResult(
            proposal=proposal,
            experience_summary="Temporal Memory 测试。",
            reply_text=reply,
            language="zh",
        )


def _query_memories(application, profile_id: str, timeline_id: str):
    from dynamic_subject_agent.application import (
        ApplicationQuery,
        ApplicationQueryKind,
        LivingMemoryApplicationProjection,
    )

    response = application.query(
        ApplicationQuery(
            kind=ApplicationQueryKind.LIVING_MEMORY,
            target_profile_id=profile_id,
            target_timeline_id=timeline_id,
        )
    )
    assert isinstance(response.projection, LivingMemoryApplicationProjection)
    return response.projection.memories


def test_memory_plan_uses_admission_anchor_and_projects_current_day(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import dynamic_subject_agent.application as application_module
    import dynamic_subject_agent.timeline as timeline_module
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.living_memory import ControlledLivingMemoryCognition
    from dynamic_subject_agent.timeline import SubjectCommand
    from test_runtime_host_binding import _publish_qri

    studio_location, qri = _publish_qri(tmp_path)
    timeline_id = str(uuid4())
    provider = _TemporalMemoryProvider()
    day1 = _us(2026, 9, 1)
    day2 = _us(2026, 9, 2)
    day3 = _us(2026, 9, 3)
    day4 = _us(2026, 9, 4)
    monkeypatch.setattr(timeline_module, "_utc_microseconds", lambda: day1)
    composition = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        _cognition=ControlledLivingMemoryCognition(provider=provider),
    )

    def submit(text: str, key: str):
        command = SubjectCommand.contribute_utterance(
            target_profile_id=qri.profile_id,
            target_timeline_id=timeline_id,
            declared_intent="ask-collaborator-status",
            utterance=text,
            language="zh",
            provenance="project-original",
        )
        submitted = composition.application.submit(command, idempotency_key=key)
        return composition.application.wait(
            submitted.operation_ref,
            timeout_seconds=5,
        )

    created = submit("我后天要学习 LLM。", "temporal-plan-create-0001")
    assert created.projection is not None
    with composition._host.lease(
        profile_id=qri.profile_id,
        timeline_id=timeline_id,
    ) as lease:
        created_runtime = lease.follow(
            created.operation_ref,
            timeout_seconds=5,
        )
        canonical = lease.list_living_memories(active_only=True, limit=20)
    assert created_runtime.outcome is not None
    assert created_runtime.outcome.experience.experienced_at_us == day1
    assert canonical[0].content == "我后天要学习 LLM"
    assert canonical[0].temporal_anchor == TemporalAnchor(
        original_expression="后天",
        anchor_date="2026-09-01",
        target_date="2026-09-03",
    )

    monkeypatch.setattr(application_module, "time_ns", lambda: day2 * 1_000)
    assert _query_memories(composition.application, qri.profile_id, timeline_id)[
        0
    ].content == "我明天要学习 LLM"
    monkeypatch.setattr(timeline_module, "_utc_microseconds", lambda: day2)
    recalled = submit("之前说的学习计划是什么？", "temporal-plan-recall-0001")
    assert recalled.projection is not None
    assert provider.requests[-1].active_memories[0].content == "我明天要学习 LLM"
    assert "明天" in recalled.projection.expression_text
    from dynamic_subject_agent.deepseek import DeepSeekLivingMemoryProvider

    outbound = json.loads(
        DeepSeekLivingMemoryProvider.outbound_bytes(
            provider.requests[-1]
        ).decode("utf-8")
    )
    outbound_projection = json.loads(outbound["messages"][1]["content"])
    assert set(outbound_projection) == {
        "current_user_message",
        "active_memories",
    }
    assert set(outbound_projection["active_memories"][0]) == {
        "memory_id",
        "content",
        "source_user_message_id",
    }
    assert "temporal_anchor" not in json.dumps(outbound, ensure_ascii=False)
    assert "Asia/Shanghai" not in json.dumps(outbound, ensure_ascii=False)
    with composition._host.lease(
        profile_id=qri.profile_id,
        timeline_id=timeline_id,
    ) as lease:
        recalled_runtime = lease.follow(
            recalled.operation_ref,
            timeout_seconds=5,
        )
    assert recalled_runtime.outcome is not None
    assert recalled_runtime.outcome.experience.experienced_at_us == day2
    host_location = composition.host_location
    composition.close()

    restarted = compose_application(
        m0_root=tmp_path,
        studio_location=studio_location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
        _cognition=ControlledLivingMemoryCognition(provider=_TemporalMemoryProvider()),
    )
    try:
        monkeypatch.setattr(application_module, "time_ns", lambda: day3 * 1_000)
        assert _query_memories(
            restarted.application,
            qri.profile_id,
            timeline_id,
        )[0].content == "我今天要学习 LLM"
        monkeypatch.setattr(application_module, "time_ns", lambda: day4 * 1_000)
        assert _query_memories(
            restarted.application,
            qri.profile_id,
            timeline_id,
        )[0].content == "我昨天要学习 LLM"
        with restarted._host.lease(
            profile_id=qri.profile_id,
            timeline_id=timeline_id,
        ) as lease:
            restored_canonical = lease.list_living_memories(
                active_only=True,
                limit=20,
            )
    finally:
        restarted.close()
    assert restored_canonical == canonical


def test_participant_goal_uses_same_temporal_anchor_and_projection_boundary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import dynamic_subject_agent.application as application_module
    import dynamic_subject_agent.timeline as timeline_module
    from test_participant_goal_integration import (
        _ScriptedParticipantGoalProvider,
        _composition,
        _query,
        _submit,
    )

    day1 = _us(2026, 9, 1)
    day2 = _us(2026, 9, 2)
    day3 = _us(2026, 9, 3)
    monkeypatch.setattr(timeline_module, "_utc_microseconds", lambda: day1)
    provider = _ScriptedParticipantGoalProvider()
    _, qri, timeline_id, composition = _composition(tmp_path, provider)
    try:
        created = _submit(
            composition,
            qri,
            timeline_id,
            "我的目标是后天学习 LLM。",
        )
        assert created.projection is not None
        with composition._host.lease(
            profile_id=qri.profile_id,
            timeline_id=timeline_id,
        ) as lease:
            created_runtime = lease.follow(
                created.operation_ref,
                timeout_seconds=5,
            )
            canonical = lease.list_participant_goal_commitments(
                active_only=True,
                limit=20,
            )
        assert created_runtime.outcome is not None
        assert created_runtime.outcome.experience.experienced_at_us == day1
        assert canonical[0].terms == "后天学习 LLM"
        assert canonical[0].temporal_anchor == TemporalAnchor(
            original_expression="后天",
            anchor_date="2026-09-01",
            target_date="2026-09-03",
        )

        monkeypatch.setattr(application_module, "time_ns", lambda: day2 * 1_000)
        assert _query(composition, qri, timeline_id)[0].terms == "明天学习 LLM"
        monkeypatch.setattr(timeline_module, "_utc_microseconds", lambda: day2)
        recalled = _submit(
            composition,
            qri,
            timeline_id,
            "我的目标是什么？",
        )
        assert recalled.projection is not None
        assert "明天学习 LLM" in recalled.projection.expression_text
        inspected = _submit(
            composition,
            qri,
            timeline_id,
            "关于目标，我最近有些想法。",
        )
        assert inspected.projection is not None
        assert provider.classification_requests[-1].active_records[0].terms == (
            "明天学习 LLM"
        )
        from dynamic_subject_agent.deepseek import DeepSeekParticipantGoalProvider

        outbound = json.loads(
            DeepSeekParticipantGoalProvider.classification_outbound_bytes(
                provider.classification_requests[-1]
            ).decode("utf-8")
        )
        outbound_projection = json.loads(outbound["messages"][1]["content"])
        assert set(outbound_projection["active_records"][0]) == {
            "turn_ref",
            "kind",
            "terms",
            "status",
        }
        assert "temporal_anchor" not in json.dumps(outbound, ensure_ascii=False)
        assert "Asia/Shanghai" not in json.dumps(outbound, ensure_ascii=False)

        monkeypatch.setattr(application_module, "time_ns", lambda: day3 * 1_000)
        assert _query(composition, qri, timeline_id)[0].terms == "今天学习 LLM"
        transitioned = _submit(
            composition,
            qri,
            timeline_id,
            "我的目标已达成。",
        )
        assert transitioned.projection is not None
        with composition._host.lease(
            profile_id=qri.profile_id,
            timeline_id=timeline_id,
        ) as lease:
            transitioned_canonical = lease.list_participant_goal_commitments(
                active_only=False,
                limit=20,
            )
    finally:
        composition.close()
    assert transitioned_canonical[0].terms == canonical[0].terms
    assert transitioned_canonical[0].status == "achieved"
    assert transitioned_canonical[0].temporal_anchor == canonical[0].temporal_anchor
