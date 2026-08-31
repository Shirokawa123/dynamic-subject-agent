"""Slice-03 behavior tests: relationship stance classification and adjudication."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from dynamic_subject_agent.relationship_events import ALL_RELATIONSHIP_EVENTS

POSITIVE_MESSAGE = "谢谢你把样张提前跟印刷厂确认好了。"
POSITIVE_QUOTE = "把样张提前跟印刷厂确认好了"
DEEPSEEK_AUTHORITY_NOTE = "deepseek authority is propagated from the provider"


def _stance_content(event: str, quote: str) -> dict:
    return {
        "event": event,
        "evidence_quote": quote,
        "experience_summary": "",
        "reply_text": "我记下了这份心意，也会继续把细节确认好。",
        "language": "zh",
    }


def _stance_transport_response(content: dict) -> bytes:
    from dynamic_subject_agent.deepseek import (
        DEEPSEEK_MODEL,
        DeepSeekHttpResponse,
    )

    return json.dumps(
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
            "usage": {"prompt_tokens": 200, "completion_tokens": 80},
        },
        ensure_ascii=False,
    ).encode("utf-8")


from dynamic_subject_agent.deepseek import DeepSeekTransport


class _ScriptedStanceTransport(DeepSeekTransport):
    def __init__(self, content: dict) -> None:
        self.calls = []
        self._content = content

    def post_json(self, *, endpoint, body, credential_ref, timeout_seconds):
        self.calls.append(body)
        from dynamic_subject_agent.deepseek import DeepSeekHttpResponse

        return DeepSeekHttpResponse(
            status_code=200,
            body=_stance_transport_response(self._content),
        )


def _provider(transport):
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import (
        DEEPSEEK_CREDENTIAL_BACKEND_ID,
        DEEPSEEK_CREDENTIAL_KEY_ID,
        DeepSeekRelationshipProvider,
    )

    return DeepSeekRelationshipProvider(
        transport=transport,
        credential_ref=CredentialRef.reference(
            backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID,
            key_id=DEEPSEEK_CREDENTIAL_KEY_ID,
        ),
    )


def test_relationship_adapter_parses_verbatim_evidence_and_teaches_closed_set() -> None:
    from dynamic_subject_agent.relationship import RelationshipProviderRequest

    transport = _ScriptedStanceTransport(
        _stance_content("stable_positive_interaction", POSITIVE_QUOTE)
    )
    provider = _provider(transport)
    request = RelationshipProviderRequest(
        current_user_message=POSITIVE_MESSAGE,
        stance_summary="尚无立场互动记录。",
    )

    result = provider.analyze(request)

    assert result.proposal.event == "stable_positive_interaction"
    assert result.proposal.evidence_quote == POSITIVE_QUOTE
    assert result.reply_text.startswith("我记下了")
    assert result.language == "zh"
    system_message = json.loads(transport.calls[0].decode("utf-8"))["messages"][0][
        "content"
    ]
    assert "no_persistent_evidence" in system_message
    assert "逐字摘自" in system_message
    outbound = json.loads(transport.calls[0].decode("utf-8"))["messages"][1]["content"]
    assert json.loads(outbound) == {
        "current_user_message": POSITIVE_MESSAGE,
        "stance_summary": "尚无立场互动记录。",
        "policy_version": "relationship-stance-v1",
    }


def test_relationship_adapter_rejects_non_verbatim_evidence() -> None:
    from dynamic_subject_agent.deepseek import ProviderFailure
    from dynamic_subject_agent.relationship import RelationshipProviderRequest

    transport = _ScriptedStanceTransport(
        _stance_content("stable_positive_interaction", "你人真好")
    )
    provider = _provider(transport)
    request = RelationshipProviderRequest(
        current_user_message=POSITIVE_MESSAGE,
        stance_summary="",
    )

    with pytest.raises(ProviderFailure):
        provider.analyze(request)


def test_relationship_adapter_rejects_event_outside_closed_set() -> None:
    from dynamic_subject_agent.deepseek import ProviderFailure
    from dynamic_subject_agent.relationship import RelationshipProviderRequest

    transport = _ScriptedStanceTransport(
        _stance_content("best_friend_forever", POSITIVE_QUOTE)
    )
    provider = _provider(transport)
    request = RelationshipProviderRequest(
        current_user_message=POSITIVE_MESSAGE,
        stance_summary="",
    )

    with pytest.raises(ProviderFailure):
        provider.analyze(request)


def test_relationship_events_closed_vocabulary_matches_legacy_port() -> None:
    assert len(ALL_RELATIONSHIP_EVENTS) == 11
    assert "no_persistent_evidence" in ALL_RELATIONSHIP_EVENTS
    assert "stable_positive_interaction" in ALL_RELATIONSHIP_EVENTS


def test_relationship_cognition_rejects_non_verbatim_evidence() -> None:
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import (
        DEEPSEEK_CREDENTIAL_BACKEND_ID,
        DEEPSEEK_CREDENTIAL_KEY_ID,
        DEEPSEEK_PROVIDER_AUTHORITY_ID,
        DeepSeekRelationshipProvider,
    )
    from dynamic_subject_agent.relationship import (
        ControlledRelationshipCognition,
        RelationshipProviderRequest,
        RelationshipProviderResult,
        RelationshipProposal,
    )
    from dynamic_subject_agent.runtime import (
        CognitionRuntimeView,
        CyclePlan,
        M0AFixture,
    )

    class RogueProvider:
        provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
        test_only = False

        def __init__(self) -> None:
            self.quotes = ["你人真好"]

        def analyze(self, request):
            return RelationshipProviderResult(
                proposal=RelationshipProposal(
                    event="stable_positive_interaction",
                    evidence_quote=self.quotes[0],
                ),
                experience_summary="",
                reply_text="不应发布。",
                language="zh",
            )

    fixture = M0AFixture.lantern_zine()
    context = CognitionRuntimeView(
        runtime_authority_id=fixture.fixture_id,
        profile_id=fixture.authority.profile_id,
        timeline_id=fixture.authority.timeline_id,
        provider_authority="fake-cognition:m0-a-cycle-1.0",
        relationship_enabled=True,
        fixture=True,
        relationship_stance_summary="",
    )
    cognition = ControlledRelationshipCognition(provider=RogueProvider())
    from dynamic_subject_agent.timeline import SubjectCommand

    command = SubjectCommand.contribute_utterance(
        target_profile_id=fixture.authority.profile_id,
        target_timeline_id=fixture.authority.timeline_id,
        declared_intent="ask-collaborator-status",
        utterance=POSITIVE_MESSAGE,
        language="zh",
        provenance="project-original",
    )

    basis = _basis_stub()
    proposal = cognition.propose(
        plan=_plan_stub(basis),
        context=context,
        command=command,
        basis=basis,
    )
    request = proposal.impact_envelope.relationship
    assert request.failure_code == "relationship-provider-invalid-output"
    assert request.candidates == ()


def _plan_stub(basis):
    from dynamic_subject_agent.runtime import CyclePlan

    return CyclePlan(
        cycle_plan_id=str(uuid4()),
        cycle_version="cycle-v1",
        operation_ref=None,
        attempt_id=str(uuid4()),
        subject_event_id=str(uuid4()),
        command_fingerprint="f" * 64,
        runtime_authority_id="stub",
        stage_order=(),
        domain_participation=(),
        expected_basis=basis,
        committed_effects_available=(),
    )


def _basis_stub():
    from dynamic_subject_agent.domains._shared import ExperienceBasis

    return ExperienceBasis(
        operation_id=str(uuid4()),
        attempt_id=str(uuid4()),
        subject_event_id=str(uuid4()),
        experience_id=str(uuid4()),
        profile_id="c627e693-68f0-43f7-b3db-e55490b47b32",
        timeline_id="471f4fd1-69fd-49df-aa14-3af405d301cf",
        epistemic_outcome_id=str(uuid4()),
        verified_prefix_digest="a" * 64,
        source_provenance="project-original",
        integrity_verified=True,
    )


class _StanceProvider:
    """Scripted cognition-level provider with DeepSeek authority for e2e runs."""

    provider_authority = "02081deb-96be-4f1c-8a17-9cc39f8daaac"
    test_only = False

    def __init__(self) -> None:
        self.requests = []

    def analyze(self, request):
        from dynamic_subject_agent.relationship import (
            RelationshipProposal,
            RelationshipProviderResult,
        )

        self.requests.append(request)
        message = request.current_user_message
        if "谢谢" in message:
            event, quote = "stable_positive_interaction", POSITIVE_QUOTE
        elif "最好的朋友" in message:
            event, quote = "relationship_claim", ""
        else:
            event, quote = "no_persistent_evidence", ""
        return RelationshipProviderResult(
            proposal=RelationshipProposal(event=event, evidence_quote=quote),
            experience_summary="",
            reply_text="我记下了。",
            language="zh",
        )


class _MisclassifyingStanceProvider(_StanceProvider):
    def analyze(self, request):
        from dynamic_subject_agent.relationship import (
            RelationshipProposal,
            RelationshipProviderResult,
        )

        self.requests.append(request)
        return RelationshipProviderResult(
            proposal=RelationshipProposal(
                event="stable_positive_interaction",
                evidence_quote="请告诉我截单时间",
            ),
            experience_summary="错误分类普通请求。",
            reply_text="周五截单。",
            language="zh",
        )


def _compose_relationship(tmp_path: Path, provider, *, mode: str = "dynamic"):
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.host import RuntimeHost
    from dynamic_subject_agent.relationship import ControlledRelationshipCognition
    from test_deepseek_controlled_route import _publish_deepseek_qri

    prepared, qri = _publish_deepseek_qri(tmp_path)
    timeline_id = str(uuid4())
    dormant_host = RuntimeHost.create(
        prepared.experiment_base,
        studio_location=prepared.location,
        cognition=DormantDeepSeekCognition(),
    )
    try:
        dormant_host.open_runtime(qri, timeline_id=timeline_id)
        host_location = dormant_host.location
    finally:
        dormant_host.close()

    composition = compose_application(
        m0_root=prepared.experiment_base,
        studio_location=prepared.location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
        _cognition=ControlledRelationshipCognition(provider=provider),
        relationship_mode=mode,
    )
    return prepared, qri, timeline_id, composition


def _submit(composition, qri, timeline_id, text, key):
    from dynamic_subject_agent.timeline import SubjectCommand

    command = SubjectCommand.contribute_utterance(
        target_profile_id=qri.profile_id,
        target_timeline_id=timeline_id,
        declared_intent="ask-collaborator-status",
        utterance=text,
        language="zh",
        provenance="project-original",
    )
    submitted = composition.application.submit(command, idempotency_key=key)
    return composition.application.wait(submitted.operation_ref, timeout_seconds=30)


def test_relationship_mode_dynamic_records_stance_event(tmp_path: Path) -> None:
    provider = _StanceProvider()
    prepared, qri, timeline_id, composition = _compose_relationship(
        tmp_path, provider
    )
    try:
        terminal = _submit(
            composition,
            qri,
            timeline_id,
            POSITIVE_MESSAGE,
            "relationship-dynamic-0001",
        )
    finally:
        composition.close()

    assert terminal.projection is not None
    assert terminal.projection.relationship_event == "stable_positive_interaction"
    assert len(provider.requests) == 1
    assert provider.requests[0].stance_summary == "尚无立场互动记录。"


def test_relationship_query_restores_accepted_interaction_after_restart(
    tmp_path: Path,
) -> None:
    from dynamic_subject_agent.application import (
        ApplicationQuery,
        ApplicationQueryKind,
        ApplicationQueryStatus,
        RelationshipApplicationProjection,
    )
    from dynamic_subject_agent.bootstrap import compose_application
    from dynamic_subject_agent.relationship import ControlledRelationshipCognition

    provider = _StanceProvider()
    prepared, qri, timeline_id, composition = _compose_relationship(
        tmp_path, provider
    )
    try:
        terminal = _submit(
            composition,
            qri,
            timeline_id,
            POSITIVE_MESSAGE,
            "relationship-restart-0001",
        )
        host_location = composition.host_location
    finally:
        composition.close()

    assert terminal.projection is not None
    restarted = compose_application(
        m0_root=prepared.experiment_base,
        studio_location=prepared.location,
        qualified_runtime_input=qri,
        timeline_id=timeline_id,
        host_location=host_location,
        _cognition=ControlledRelationshipCognition(provider=_StanceProvider()),
        relationship_mode="dynamic",
    )
    try:
        response = restarted.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.RELATIONSHIP,
                target_profile_id=qri.profile_id,
                target_timeline_id=timeline_id,
            )
        )
    finally:
        restarted.close()

    assert response.status is ApplicationQueryStatus.AVAILABLE
    assert isinstance(response.projection, RelationshipApplicationProjection)
    assert len(response.projection.interactions) == 1
    assert response.projection.interactions[0].event == "stable_positive_interaction"
    assert response.projection.interactions[0].status == "accepted"


def test_relationship_claim_produces_no_stance_event(tmp_path: Path) -> None:
    provider = _StanceProvider()
    prepared, qri, timeline_id, composition = _compose_relationship(
        tmp_path, provider
    )
    try:
        terminal = _submit(
            composition,
            qri,
            timeline_id,
            "我们现在已经是最好的朋友了吧？",
            "relationship-claim-0001",
        )
    finally:
        composition.close()

    assert terminal.projection is not None
    assert terminal.projection.expression_text == "我记下了。"
    assert terminal.projection.relationship_event is None


def test_neutral_request_cannot_be_accepted_as_stable_positive_interaction(
    tmp_path: Path,
) -> None:
    provider = _MisclassifyingStanceProvider()
    prepared, qri, timeline_id, composition = _compose_relationship(
        tmp_path, provider
    )
    try:
        terminal = _submit(
            composition,
            qri,
            timeline_id,
            "请告诉我截单时间。",
            "relationship-neutral-misclassification-0001",
        )
    finally:
        composition.close()

    assert terminal.projection is not None
    assert terminal.projection.relationship_event is None


def test_relationship_mode_off_never_invokes_provider(tmp_path: Path) -> None:
    provider = _StanceProvider()
    prepared, qri, timeline_id, composition = _compose_relationship(
        tmp_path, provider, mode="off"
    )
    try:
        terminal = _submit(
            composition,
            qri,
            timeline_id,
            POSITIVE_MESSAGE,
            "relationship-off-0001",
        )
    finally:
        composition.close()

    assert terminal.projection is not None
    assert terminal.projection.relationship_event is None
    assert len(provider.requests) == 0
