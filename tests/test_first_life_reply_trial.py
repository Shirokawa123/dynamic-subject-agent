"""S112 qualification, material boundary and canonical recovery with fake HTTPS."""
import json
from dataclasses import replace

import pytest

from dynamic_subject_agent.first_life_reply_live import open_approved_trial
from dynamic_subject_agent.local_product import open_first_life_reply_trial, open_first_life_product, open_local_product
from dynamic_subject_agent.model_gateway import ModelGateway
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.timeline import FaultPoint, TimelineEngine
from test_s109_continuous_baseline import no_remote_io
from test_first_life_reply_live_provider import FakeTransport
from test_s112_reply_comparison import runner


@pytest.fixture
def trial(tmp_path):
    approval = open_approved_trial(tmp_path / "trial", runner.SCENARIOS_PATH, confirmed=True, live=False)
    branch_id = "objects-and-versions-A"
    scenario, _ = approval.branch(branch_id)
    branch = runner.prepare_branch(approval.root / branch_id, approval.scenarios)
    seed = runner.SeedAdapter(approval.scenarios, scenario)
    def opening(**kwargs):
        return open_first_life_reply_trial(branch.config, definition_basis=branch.definition_basis,
            life_scope_digest=branch.life_scope_digest, approval=approval, branch_id=branch_id, **kwargs)
    with opening(seed_gateway=ModelGateway(seed)) as product:
        runner.seed_branch(product, seed)
    assert approval.shared_budget().counts() == (42, 0, 42)
    return opening, approval, branch, scenario


def test_manifest_cannot_allocate_a_second_real_root_or_reinitialize(tmp_path):
    with pytest.raises(ValueError):
        open_approved_trial(tmp_path / "wrong-live-root", runner.SCENARIOS_PATH, confirmed=True, live=True)
    with pytest.raises(ValueError):
        open_approved_trial(tmp_path / "not-confirmed", runner.SCENARIOS_PATH, confirmed=False, live=False)
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    with pytest.raises(FileNotFoundError):
        open_approved_trial(incomplete, runner.SCENARIOS_PATH, confirmed=True, live=False)


def test_live_branch_requires_its_exact_entrypoint_and_does_not_spend_on_open(trial):
    opening, approval, branch, _ = trial
    transport = FakeTransport()
    with opening(_transport=transport) as product:
        assert product.application.reviewed_character_chat_status().budget_total == 42
    assert not transport.calls and approval.shared_budget().counts() == (42, 0, 42)
    with pytest.raises(ValueError):
        opening()  # offline approval can never resolve a real credential
    with pytest.raises(ValueError):
        open_local_product(branch.config, cognition=DormantDeepSeekCognition())
    with pytest.raises(ValueError):
        open_first_life_product(branch.config, definition_basis=branch.definition_basis,
            life_scope_digest=branch.life_scope_digest,
            budget_path=branch.config.state_path.parent / "local-stage-budget", development_run=True)


@pytest.mark.parametrize("marker", ["life_runtime_policy", "live_reply_route"])
def test_missing_qualifier_or_witness_cannot_fall_back_to_old_route(trial, marker):
    opening, _, branch, _ = trial
    state = json.loads(branch.config.state_path.read_text(encoding="utf-8"))
    active = next(row for row in state["identities"] if row["identity_id"] == state["active_identity_id"])
    if marker == "life_runtime_policy":
        active.pop(marker)
    else:
        active["life_activation"].pop(marker)
    branch.config.state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(RuntimeError, match="live-reply-activation-invalid"):
        opening(_transport=FakeTransport())


def test_unapproved_message_fails_before_transport_and_keeps_seed_history(trial):
    opening, approval, _, _ = trial
    transport = FakeTransport()
    with opening(_transport=transport) as product:
        result = runner.send(product, "This input is outside the frozen experiment.", "s112-unapproved-test")
        assert result.status == "failed-closed"
        assert len(runner.read_history(product)) == 1
    assert transport.calls == []
    assert approval.shared_budget().counts() == (42, 1, 41)  # conservative claim, zero delivered


def test_prepared_live_reply_recovers_without_resending(trial, monkeypatch):
    opening, approval, _, scenario = trial
    transport = FakeTransport()
    original = TimelineEngine._hit
    def interrupt(engine, point):
        original(engine, point)
        if point is FaultPoint.AFTER_PLAN_CLAIM:
            raise OSError("synthetic interruption after durable preparation")
    with monkeypatch.context() as patch:
        patch.setattr(TimelineEngine, "_hit", interrupt)
        with opening(_transport=transport) as product:
            failed = runner.send(product, scenario["turns"][0]["user"], "s112-prepared-recovery")
            assert failed.status != "terminal"
    assert len(transport.calls) == 1
    assert approval.shared_budget().counts() == (42, 1, 41)
    with opening(_transport=transport) as restored:
        assert len(runner.read_history(restored)) == 2
        assert runner.read_history(restored)[-1].assistant_text == "这是合成最终回答。"
    assert len(transport.calls) == 1


def test_history_revocation_during_live_call_prevents_publication(trial):
    opening, approval, _, scenario = trial
    transport = FakeTransport()
    original = transport.post_json
    with opening(_transport=transport) as product:
        def revoke(**kwargs):
            result = original(**kwargs)
            product.application.set_reviewed_character_history(False)
            return result
        transport.post_json = revoke
        result = runner.send(product, scenario["turns"][0]["user"], "s112-history-revoked")
        assert result.status == "failed-closed"
        assert len(runner.read_history(product)) == 1
    assert len(transport.calls) == 1 and approval.shared_budget().counts()[1] == 1


def test_live_mode_cannot_reseed_and_prior_user_or_share_cannot_be_replaced(trial):
    opening, approval, _, scenario = trial
    captured = []
    original = approval.validate_task
    def capture(branch_id, task):
        captured.append(task)
        return original(branch_id, task)
    approval.validate_task = capture
    with opening(_transport=FakeTransport()) as product:
        assert runner.send(product, scenario["turns"][0]["user"], "s112-capture-material").status == "terminal"
    with pytest.raises(ValueError, match="cannot return"):
        opening(seed_gateway=ModelGateway(runner.SeedAdapter(approval.scenarios, scenario)))
    task = captured[0]
    for label in ("U1", "S1"):
        sources = tuple(replace(row, text="UNAPPROVED_SOURCE") if row.label == label else row
            for row in task.payload.dialogue_sources)
        with pytest.raises(ValueError, match="prior user or share"):
            original("objects-and-versions-A", replace(task, payload=replace(task.payload, dialogue_sources=sources)))


def test_unqualified_sender_with_real_credential_reference_is_rejected(tmp_path):
    from dynamic_subject_agent.cognition import CredentialRef
    from dynamic_subject_agent.deepseek import DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID
    from dynamic_subject_agent.first_life_reply_live_provider import LiveReplyAdapter
    from test_first_life_reply_live_provider import make_budget
    budget, _, _ = make_budget(tmp_path)
    transport = FakeTransport()
    real_ref = CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID)
    with pytest.raises(ValueError, match="approved live experiment"):
        LiveReplyAdapter(transport, real_ref, budget)
    assert not transport.calls
