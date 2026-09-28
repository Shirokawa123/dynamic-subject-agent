"""V4 frozen share followup and revocation, only synthetic transports."""
from dataclasses import asdict, replace
from contextlib import contextmanager
import json
import pytest

from dynamic_subject_agent import first_life_followup as v4
from dynamic_subject_agent import first_life_grounded as v3
from dynamic_subject_agent.first_life_followup_provider import DeepSeekFirstLifeFollowupAdapter
from dynamic_subject_agent.first_life_grounded_provider import DeepSeekFirstLifeGroundedAdapter
from dynamic_subject_agent.first_life_relevance_provider import DeepSeekFirstLifeRelevanceAdapter
from dynamic_subject_agent.first_life import FirstLifeSimulationRequest, FirstLifeHeartbeatRequest
from dynamic_subject_agent.first_life_authorization import ChatAuthorization, ShareAuthorizationChanged
from dynamic_subject_agent.local_identity_authority import LocalIdentityAuthority
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
from dynamic_subject_agent.deepseek import DeepSeekHttpResponse
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.runtime import CycleFailedClosed
from dynamic_subject_agent.timeline import FaultPoint, PublicationProblem, OperationState, SubjectCommand, CycleCommitPlan, CommitPlanRejected
from test_first_life_facade import life_fixture, settle, approved, model_fixture, personality_fixture
from test_first_life_relevance_compat import RelevanceTransport
from test_first_life_grounded import choice
from test_first_life_relevance_projection import relevance_fixture
from test_first_life_publication import life_runtime, SyntheticLife, chat, advance, system
from test_reviewed_character_chat import send


class FollowupTransport(RelevanceTransport):
    def post_json(self, **kwargs):
        result = super().post_json(**kwargs)
        projection = self.calls[-1][1]
        if "dialogue_sources" in projection:
            outer = json.loads(result.body)
            value = json.loads(outer["choices"][0]["message"]["content"])
            sources = projection["dialogue_sources"]
            value["dialogue_refs"] = ["S1"] if any(r["label"] == "S1" for r in sources) else []
            outer["choices"][0]["message"]["content"] = canonical_json(value)
            return DeepSeekHttpResponse(200, canonical_json(outer).encode())
        return result


def enable(life_fixture):
    opening, transport, _, config, view = life_fixture
    transport.__class__ = FollowupTransport
    return opening(runtime_policy=v4.FOLLOWUP_VERSION, runtime_policy_digest=v4.first_life_scope_digest(view.definition_basis))


def share(product):
    app = product.application
    assert send(product, "合成开场。", "s108-test-followup-intro").status == "terminal"
    step = settle(app, app.simulate_first_life_step(FirstLifeSimulationRequest("s108-test-followup-life")))
    assert step.status == "terminal", repr(step)
    assert settle(app, app.heartbeat_first_life(FirstLifeHeartbeatRequest("s108-test-followup-session", "s108-test-followup-share"))).status == "terminal"
    return app.query_first_life().shares[-1].text


def test_share_at_frozen_head_two_turns_answered_restart_then_expires(life_fixture):
    opening, transport, _, config, view = life_fixture
    product = enable(life_fixture)
    text = share(product)
    first = send(product, "为什么这么想？", "s108-test-followup-first")
    assert first.status == "terminal", first
    sources = transport.calls[-2][1]["dialogue_sources"]
    assert [r["label"] for r in sources] == ["U1", "A1", "S1"]
    assert sources[-1] == dict(label="S1", speaker="assistant", kind="proactive-share", text=text)
    assert transport.calls[-1][1]["selected_dialogue"] == [sources[-1]]
    assert product.application.query_first_life().shares[-1].answered
    product.close()
    restored = opening()
    assert send(restored, "那这一点呢？", "s108-test-followup-second").status == "terminal"
    assert [r["label"] for r in transport.calls[-2][1]["dialogue_sources"]] == ["U1", "A1", "S1", "U2", "A2"]
    assert send(restored, "再聊聊。", "s108-test-followup-third").status == "terminal"
    assert all(r["label"] != "S1" for r in transport.calls[-2][1]["dialogue_sources"])
    assert len(transport.calls) == 10


def test_history_off_then_new_request_can_reuse_unexpired_share(life_fixture):
    _, transport, _, _, _ = life_fixture
    product = enable(life_fixture)
    text = share(product)
    assert product.application.set_reviewed_character_history(False).status == "active"
    assert send(product, "说说现在。", "s108-test-followup-off").status == "terminal"
    assert transport.calls[-2][1]["dialogue_sources"] == []
    assert transport.calls[-1][1]["selected_dialogue"] == []
    assert product.application.set_reviewed_character_history(True).status == "active"
    assert send(product, "为什么这么想？", "s108-test-followup-on").status == "terminal"
    assert any(r["text"] == text and r["label"] == "S1" for r in transport.calls[-2][1]["dialogue_sources"])


@pytest.mark.parametrize("stage", ["before-send", "planning-return", "expression-return"])
def test_history_aba_fences_outbound_and_prevents_publication(life_fixture, monkeypatch, stage):
    _, transport, _, _, _ = life_fixture
    product = enable(life_fixture)
    share(product)
    app = product.application
    before = len(transport.calls)
    def revoke():
        assert app.set_reviewed_character_history(False).status == "active"
        assert app.set_reviewed_character_history(True).status == "active"
    if stage == "before-send":
        original = v4.life_chat_planning
        def projecting(*args, **kwargs):
            result = original(*args, **kwargs)
            revoke()
            return result
        monkeypatch.setattr(v4, "life_chat_planning", projecting)
    else:
        original = transport.post_json
        def posting(**kwargs):
            result = original(**kwargs)
            if len(transport.calls) - before == (1 if stage == "planning-return" else 2): revoke()
            return result
        transport.post_json = posting
    result = send(product, "为什么这么想？", "s108-test-followup-revoked")
    assert result.status == "failed-closed"
    assert len(transport.calls) - before == {"before-send": 0, "planning-return": 1, "expression-return": 2}[stage]
    assert not app.query_first_life().shares[-1].answered


def test_control_and_failed_prefix_prevent_share_disclosure(life_fixture):
    _, transport, _, _, _ = life_fixture
    product = enable(life_fixture)
    share(product)
    before = len(transport.calls)
    assert send(product, "不要再提刚才那句话。", "s108-test-followup-control").status == "failed-closed"
    assert send(product, "为什么这么想？", "s108-test-followup-after-control").status == "failed-closed"
    assert len(transport.calls) == before


class FollowupReader(SyntheticLife):
    def propose(self, **kwargs):
        if type(kwargs["command"]) is SubjectCommand:
            self.followup = kwargs["context"].load_first_life_followup(True)
        return super().propose(**kwargs)


def test_duplicate_turn_text_keeps_canonical_interleaving_and_new_share_replaces_old(life_runtime):
    opening, authority, _ = life_runtime
    cognition = FollowupReader()
    runtime = opening(cognition)
    chat(runtime, authority, "duplicate")
    advance(runtime, authority)
    event = runtime.first_life_basis().events[-1]
    admitted = runtime.admit_first_life(system(authority, "share", target_event_id=event.event_id), idempotency_key="s108-test-duplicate-share")
    runtime.resume(admitted.operation_ref)
    # Different idempotency key, exactly identical committed user/assistant text.
    command = SubjectCommand.contribute_utterance(target_profile_id=authority.profile_id,
        target_timeline_id=authority.timeline_id, declared_intent="ask-collaborator-status", utterance="duplicate",
        language="zh", provenance="project-original")
    runtime.execute(command, idempotency_key="s108-test-duplicate-second")
    chat(runtime, authority, "inspect")
    assert [r.label for r in cognition.followup.sources] == ["U1", "A1", "S1", "U2", "A2"]
    advance(runtime, authority, "second-event")
    event = runtime.first_life_basis().events[-1]
    admitted = runtime.admit_first_life(system(authority, "share", target_event_id=event.event_id), idempotency_key="s108-test-new-share")
    runtime.resume(admitted.operation_ref)
    chat(runtime, authority, "inspect-new")
    assert [r.label for r in cognition.followup.sources] == ["U1", "A1", "U2", "A2", "S1"]


class AuthorizedChat(SyntheticLife):
    def __init__(self, box):
        super().__init__()
        self.box = box
    @contextmanager
    def chat_guard(self, token):
        if token != self.box[0]: raise ShareAuthorizationChanged("changed")
        yield
    def propose(self, **kwargs):
        proposal = super().propose(**kwargs)
        if type(kwargs["command"]) is SubjectCommand:
            return replace(proposal, chat_authorization=self.box[0])
        return proposal


@pytest.mark.parametrize("when", ["final-commit", "cold-revoked", "cold-missing", "cold-valid"])
def test_chat_preparation_authorization_survives_recovery_and_fences_publication(life_runtime, when):
    opening, authority, _ = life_runtime
    box = [ChatAuthorization(authority.profile_id, v4.FOLLOWUP_VERSION, "a" * 64, 1, 0, True)]
    runtime = opening(AuthorizedChat(box))
    def fault(point):
        if when == "final-commit" and point is FaultPoint.BEFORE_PUBLICATION_COMMIT:
            box[0] = replace(box[0], history_revision=2)
        elif when != "final-commit" and point is FaultPoint.AFTER_PLAN_CLAIM:
            raise RuntimeError("synthetic interruption")
    runtime._engine._fault_hook = fault
    command = SubjectCommand.contribute_utterance(target_profile_id=authority.profile_id,
        target_timeline_id=authority.timeline_id, declared_intent="ask-collaborator-status", utterance="合成追问。",
        language="zh", provenance="project-original")
    admitted = runtime.admit(command, idempotency_key="authorized-followup")
    if when == "final-commit":
        result = runtime.resume(admitted.operation_ref)
    else:
        with pytest.raises(PublicationProblem): runtime.resume(admitted.operation_ref)
        assert runtime._engine.prepared_plan(admitted.operation_ref).chat_authorization == box[0]
        runtime.close()
        if when == "cold-revoked": box[0] = replace(box[0], history_revision=2)
        cognition = SyntheticLife() if when == "cold-missing" else AuthorizedChat(box)
        runtime = opening(cognition)
        result = runtime.recover_first_life_pending()[0]
        assert cognition.calls == 0
    if when == "cold-valid":
        assert result.snapshot.operation_state is OperationState.COMPLETED
        box[0] = replace(box[0], history_revision=2)
        assert runtime.resume(admitted.operation_ref).outcome == result.outcome
    else:
        assert result.snapshot.operation_state is OperationState.FAILED_CLOSED
        assert runtime._engine.query_failure(admitted.operation_ref).code == (
            "first-life-chat-authorization-unverified" if when == "cold-missing" else "first-life-chat-authorization-changed")
        with pytest.raises(PublicationProblem): runtime._engine.publish(runtime._engine.prepared_plan(admitted.operation_ref))


def test_source_caps_exact_copy_and_old_wire_isolation(relevance_fixture):
    from dynamic_subject_agent.recent_dialogue import RecentDialogueTurn
    from dynamic_subject_agent.reviewed_character_chat import CharacterDialogueBasis
    from dynamic_subject_agent import first_life_relevance as v2
    from dynamic_subject_agent.first_life_projection import life_model_projection
    envelope, identity, basis, dialogue, event = relevance_fixture
    full = CharacterDialogueBasis("available", True, (RecentDialogueTurn("U" * 1000, "A" * 1000),) * 2)
    rows = (v4.DialogueSource("U1", "user", "U" * 1000, "dialogue"), v4.DialogueSource("A1", "assistant", "A" * 1000, "dialogue"),
        v4.DialogueSource("S1", "assistant", "S" * 400, "proactive-share"),
        v4.DialogueSource("U2", "user", "U" * 1000, "dialogue"), v4.DialogueSource("A2", "assistant", "A" * 1000, "dialogue"))
    planning, _ = v4.life_chat_planning(envelope, identity, "为什么这么想？", v4.FirstLifeFollowupBasis(full, rows), True, basis)
    assert sum(len(row.text) for row in planning.dialogue_sources) == 4400
    expression, _ = v4.life_chat_expression(planning, choice(dialogue_refs=["S1", "A1"]))
    assert expression.selected_dialogue == (rows[1], rows[2])
    payload = json.loads(json.loads(DeepSeekFirstLifeFollowupAdapter.wire(ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_PLAN, planning)))["messages"][1]["content"])
    assert payload["dialogue_sources"] == [asdict(row) for row in rows]
    assert all(set(row) == {"label", "speaker", "text", "kind"} for row in payload["dialogue_sources"])
    with pytest.raises(ValueError): v4._validate_sources((replace(rows[2], text="S" * 401),), True)
    with pytest.raises(ValueError): v4.life_chat_expression(planning, choice(dialogue_refs=["S1", "A1", "U1"]))
    with pytest.raises(ValueError): DeepSeekFirstLifeGroundedAdapter.wire(ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_PLAN, planning))
    old, _ = v3.life_chat_planning(envelope, identity, "旧版", dialogue, True, basis)
    with pytest.raises(ValueError): DeepSeekFirstLifeFollowupAdapter.wire(ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_PLAN, old))
    for task in (ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_SHARE, v2.share_model_projection(envelope, identity, basis, dialogue, True, event)),
                 ModelTask(ModelTaskKind.CHARACTER_FIRST_LIFE_DECISION, life_model_projection(envelope, identity, basis))):
        assert DeepSeekFirstLifeFollowupAdapter.wire(task) == DeepSeekFirstLifeRelevanceAdapter.wire(task)


@pytest.mark.parametrize("change", ["identity-aba", "policy-aba", "missing-revision", "null-revision"])
def test_registry_chat_revision_fences_identity_policy_and_unknown_metadata(life_fixture, change):
    from dynamic_subject_agent.source_character_authoring import LocalIdentitySelectRequest
    from dynamic_subject_agent.first_life_authorization import LEGACY_RUNTIME_POLICY
    opening, transport, _, config, view = life_fixture
    product = enable(life_fixture)
    authority = LocalIdentityAuthority(config)
    token = authority.first_life_chat_authorization(product.profile_id)
    state = json.loads(config.state_path.read_text(encoding="utf-8"))
    if change == "identity-aba":
        product.close()
        other = next(row["identity_id"] for row in state["identities"] if row["identity_id"] != product.profile_id)
        assert authority.select(LocalIdentitySelectRequest(other, True), current=None).status == "selected"
        assert authority.select(LocalIdentitySelectRequest(product.profile_id, True), current=None).status == "selected"
        assert authority.first_life_chat_authorization(product.profile_id).identity_revision == token.identity_revision + 2
    elif change == "policy-aba":
        record = next(row for row in state["identities"] if row["identity_id"] == product.profile_id)
        authority.first_life_runtime_policy(product.profile_id, runtime_policy=LEGACY_RUNTIME_POLICY,
            runtime_policy_digest=record["life_scope_digest"])
        authority.first_life_runtime_policy(product.profile_id, runtime_policy=v4.FOLLOWUP_VERSION,
            runtime_policy_digest=v4.first_life_scope_digest(view.definition_basis))
    else:
        if change == "missing-revision": state.pop("chat_identity_revision")
        else: state["chat_identity_revision"] = None
        config.state_path.write_text(canonical_json(state), encoding="utf-8")
        with pytest.raises(RuntimeError):
            authority.first_life_runtime_policy(product.profile_id, runtime_policy=v4.FOLLOWUP_VERSION,
                runtime_policy_digest=v4.first_life_scope_digest(view.definition_basis))
        other = next(row["identity_id"] for row in state["identities"] if row["identity_id"] != product.profile_id)
        assert authority.select(LocalIdentitySelectRequest(other, True), current=None).status == "failed-closed"
    with pytest.raises(RuntimeError):
        with authority.first_life_chat_guard(token): pass
    assert transport.calls == []


def test_v4_rollback_keeps_published_chat_readable(life_fixture):
    from dynamic_subject_agent.first_life_authorization import LEGACY_RUNTIME_POLICY
    from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
    opening, transport, _, config, _ = life_fixture
    product = enable(life_fixture)
    assert send(product, "合成新聊天。", "s108-test-versioned-intro").status == "terminal"
    identity = product.profile_id
    state = json.loads(config.state_path.read_text(encoding="utf-8"))
    digest = next(row["life_scope_digest"] for row in state["identities"] if row["identity_id"] == identity)
    product.close()
    restored = opening(runtime_policy=LEGACY_RUNTIME_POLICY, runtime_policy_digest=digest)
    history = restored.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY, restored.profile_id, restored.timeline_id))
    assert history.status == "available" and len(history.projection.turns) == 1
    assert len(transport.calls) == 2


@pytest.mark.parametrize("damage", ["pending", "corrupt-share", "oversized-latest"])
def test_followup_reader_refuses_unresolved_or_damaged_canonical_context(life_runtime, monkeypatch, damage):
    import sqlite3
    opening, authority, location = life_runtime
    cognition = FollowupReader()
    runtime = opening(cognition)
    chat(runtime, authority, "first")
    advance(runtime, authority)
    event = runtime.first_life_basis().events[-1]
    admitted = runtime.admit_first_life(system(authority, "share", target_event_id=event.event_id), idempotency_key="s108-test-reader-share")
    runtime.resume(admitted.operation_ref)
    if damage == "pending":
        command = SubjectCommand.contribute_utterance(target_profile_id=authority.profile_id,
            target_timeline_id=authority.timeline_id, declared_intent="ask-collaborator-status", utterance="未解决。",
            language="zh", provenance="project-original")
        runtime.admit(command, idempotency_key="s108-test-reader-unresolved")
        before = cognition.calls
        with pytest.raises(CycleFailedClosed, match="first-life-recovery-required"):
            chat(runtime, authority, "pending-inspection")
        assert cognition.calls == before
    elif damage == "oversized-latest":
        original = runtime._engine.first_life_basis
        def oversized(**kwargs):
            basis = original(**kwargs)
            return replace(basis, shares=(*basis.shares[:-1], replace(basis.shares[-1], text="大" * 401)))
        monkeypatch.setattr(runtime._engine, "first_life_basis", oversized)
        with pytest.raises(PublicationProblem, match="first-life-followup-invalid"):
            chat(runtime, authority, "oversized-inspection")
    else:
        # Mutation of the sole canonical expression cannot silently look like an empty window.
        with sqlite3.connect(location.timeline_database) as db:
            db.execute("UPDATE expression_record SET expression_text='损坏分享' WHERE expression_text='构图文字方案有一个新版本。'")
        with pytest.raises(PublicationProblem): chat(runtime, authority, "corrupt-inspection")
