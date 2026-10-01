"""Run the approved S112 frozen comparison through real Facade/Timeline branches.

Preparation and seeding are deterministic local work. Live delivery is available
only through open_approved_trial and the separate production composition root.
Results are append-only observations, never an input store for later replies.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
from time import perf_counter
import traceback
from zipfile import ZipFile, ZipInfo

from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
from dynamic_subject_agent.character_evidence_model import DIMENSIONS
from dynamic_subject_agent.character_identity_preparation import CharacterDefinitionPreparationRequest
from dynamic_subject_agent.first_life import (FirstLifeContextResetRequest, FirstLifeControlRequest,
    FirstLifeHeartbeatRequest, FirstLifeIdentityRequest, FirstLifeSimulationRequest, first_life_scope_digest)
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.local_product import LocalProductConfig, open_character_personality_lab, open_local_product
from dynamic_subject_agent.model_gateway import (ModelGateway, ModelResult, ModelTaskKind,
    ProviderAdapter, ProviderCapabilities, StructuredOutputMode)
from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
from dynamic_subject_agent.source_character_authoring import LocalIdentitySelectRequest
from dynamic_subject_agent.timeline import SubjectCommand


SCENARIOS_PATH = Path(__file__).resolve().parents[1] / "docs/experiments/s111/scenarios.json"
VERSION = "s112-reply-comparison-runner-1"


def digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


def _write_new(path, value):
    with path.open("x", encoding="utf-8") as output:
        output.write(canonical_json(value) + "\n")
        output.flush()
        os.fsync(output.fileno())


class Journal:
    """Durably record before and after each action; never drive a retry from it."""

    def __init__(self, path):
        self.path = path
        self.file = path.open("x", encoding="utf-8")
        self.lock = RLock()

    def append(self, value):
        with self.lock:
            self.file.write(canonical_json(value) + "\n")
            self.file.flush()
            os.fsync(self.file.fileno())

    def close(self):
        self.file.close()


class JournaledObservations(list):
    """Persist a completed stage before the worker proceeds to another stage."""

    def __init__(self, previous, journal):
        super().__init__(previous)
        self.journal = journal
        self.branch_id = None
        self.step = None

    def append(self, row):
        attributed = {"branch_id": self.branch_id, "step": self.step, **row}
        self.journal.append(dict(event="stage-observed", **attributed))
        super().append(attributed)


@dataclass(frozen=True)
class PreparedBranch:
    config: LocalProductConfig
    definition_basis: str
    life_scope_digest: str
    runtime_asset_sha: str
    material_digest: str


def prepare_branch(branch_root, specification):
    """Rebuild S111's exact original character via public authoring interfaces.

    Names, statements, labels, organization and qualification metadata follow the
    S111 source fixture. ZIP timestamps are fixed, so isolated roots share a
    definition basis; distinct identity authority/Timeline roots provide isolation.
    """
    branch_root = Path(branch_root).resolve()
    branch_root.mkdir(parents=False, exist_ok=False)
    authoring = branch_root / "authoring"
    sources = authoring / "sources"
    sources.mkdir(parents=True)
    character = specification["character"]
    facts = dict(zip(("a", "art", "work"), character["facts"], strict=True))
    quote = character["name"] + "的原创合成设定：" + "".join(row["text"] for row in facts.values())
    content = ("<html><p>" + quote + "</p></html>").encode()
    book = sources / "sample.epub"
    with ZipFile(book, "w") as archive:
        archive.writestr(ZipInfo("ch.html", date_time=(2026, 10, 1, 0, 0, 0)), content)
    evidence = dict(id="r1", file=book.name, file_sha256=sha256(book.read_bytes()).hexdigest(), href="ch.html",
        document_sha256=sha256(content).hexdigest(), paragraph=1, quote=quote,
        quote_sha256=sha256(quote.encode()).hexdigest(), speaker_id="narrator", source_group="main")
    assertions = [dict(id=key, dimension=dimension, kind=facts[key]["kind"], statement=facts[key]["text"],
        about=["self"], knower_id="self", event_time="before", knowledge_time="before", review="reviewed",
        depends_on=[], evidence_ids=["r1"], relation="identity", time_basis="Explicit prior background in synthetic source.")
        for key, dimension in (("a", "identity"), ("art", "biography"), ("work", "work"))]
    organization = dict(version="character-chat-organization-1", subject_id="self", anchor_id="start",
        core=[dict(id="core-self", title="自我认识", content=facts["a"]["text"], claim_ids=["a"])],
        episodes=[dict(id="child-art", title="学画的经历", content=facts["art"]["text"], claim_ids=["art"],
            cues=["画画", "学画", "小时候", "母亲"])],
        details=[dict(id="work-detail", title="创作的压力", content=facts["work"]["text"], claim_ids=["work"],
            cues=["截止", "交稿", "赶稿"])])
    draft = dict(version="character-evidence-draft-1", status="local-review-only", subject_id="self",
        anchor=dict(id="start", status="proposed"), chat_stage_description=character["stage"],
        entities=[dict(id=value, name=character["name"] if value == "self" else value, kind="person-reference")
            for value in ("self", "narrator", "other", "hidden")], evidence=[evidence], assertions=assertions,
        coverage_review={dimension: dict(assessment="partial", gaps=["Still incomplete."]) for dimension in DIMENSIONS},
        chat_organization=organization)
    draft_path, sidecar = authoring / "draft.json", authoring / "personality.json"
    _write_new(draft_path, draft)
    reviewed_digest = sha256(draft_path.read_bytes()).hexdigest()
    personality = dict(version="character-personality-draft-1", status="local-interpretation-candidates",
        base_reviewed_digest=reviewed_digest, subject_id="self", anchor_id="start",
        items=[dict(id="candidate-private-id", **character["personality"], claim_ids=["a", "work"])])
    _write_new(sidecar, personality)
    personality_digest = sha256(sidecar.read_bytes()).hexdigest()
    with open_character_personality_lab(authoring / "preview-products", draft_path=draft_path,
            source_root=sources, reviewed_digest=reviewed_digest, sidecar_path=sidecar,
            personality_digest=personality_digest) as preview:
        view = preview.application.preview_character_identity_preparation(CharacterDefinitionPreparationRequest(
            "self", "start", sidecar, personality_digest))
    if view.status != "previewed":
        raise ValueError("synthetic-character-preparation-failed")
    _write_new(authoring / "preparation.json", asdict(view))
    _write_new(authoring / "runtime-asset.json", json.loads(view.runtime_asset_json))
    config = LocalProductConfig(branch_root / "DynamicSubjectAgent/m0/experiments", branch_root / "state.json")
    scope = first_life_scope_digest(view.definition_basis)
    with open_local_product(config, cognition=DormantDeepSeekCognition()) as product:
        frozen = product.application.freeze_source_identity(ReviewedCharacterFreezeRequest(
            canonical_json(asdict(view)), view.definition_basis, True, True))
        if frozen.status != "created":
            raise ValueError("synthetic-character-freeze-failed")
        selected = product.application.select_local_identity(LocalIdentitySelectRequest(frozen.view.identity_id, True))
        if selected.status != "selected":
            raise ValueError("synthetic-character-select-failed")
        life = product.application.freeze_first_life_identity(FirstLifeIdentityRequest(view.definition_basis, scope, True))
        if life.status != "created":
            raise ValueError("synthetic-life-freeze-failed")
        selected = product.application.select_local_identity(LocalIdentitySelectRequest(life.view.identity_id, True))
        if selected.status != "selected":
            raise ValueError("synthetic-life-select-failed")
    return PreparedBranch(config, view.definition_basis, scope, view.runtime_asset_sha, digest(character))


class SeedAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities("s112-synthetic-seed", "fixed-program", True, (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self, specification, scenario):
        self.specification, self.scenario = specification, scenario
        self.actions = 0
        self.calls = []

    def invoke(self, task):
        projection = asdict(task.payload)
        if task.kind is ModelTaskKind.CHARACTER_FIRST_LIFE_DECISION:
            if self.actions >= 2:
                raise ValueError("seed-does-not-generate-additional-life")
            value = dict(action="start" if self.actions == 0 else "revise",
                plan=self.scenario["plans"][self.actions], reason_code="balance-space")
            self.actions += 1
        elif task.kind is ModelTaskKind.CHARACTER_FIRST_LIFE_SHARE:
            value = dict(share=True, reply_text=self.scenario["share"], language="zh",
                focus="composition", opening="self-interest")
        else:
            if projection["conversation"]["current_message"] != self.specification["shared_intro"]["user"]:
                raise ValueError("seed-cannot-answer-experiment-turns")
            if task.kind is ModelTaskKind.CHARACTER_COMMUNICATION_PLAN:
                value = dict(action="answer", fact_refs=[], use_life=False, focus="respond-current", dialogue_refs=[])
            elif task.kind in (ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY,
                    ModelTaskKind.CHARACTER_FIRST_LIFE_FACT_EXPRESSION):
                value = dict(reply_text=self.specification["shared_intro"]["assistant"], language="zh")
                if task.kind is ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY:
                    value["use_life"] = False
            else:
                raise ValueError("unsupported-synthetic-seed-task")
        self.calls.append(dict(task_kind=task.kind.value, payload=projection, value=value, generation="programmed-synthetic-seed"))
        return ModelResult(task.kind, value)


def settle(application, result):
    # Facade waits are bounded to 30 seconds; observing the same operation is
    # not an additional generation attempt or a transport retry.
    for _ in range(3):
        if result.status != "pending":
            break
        result = application.wait(result.operation_ref, timeout_seconds=30)
    return result


def send(product, message, key):
    command = SubjectCommand.contribute_utterance(target_profile_id=product.profile_id,
        target_timeline_id=product.timeline_id, declared_intent="ask-collaborator-status", utterance=message,
        language="zh", provenance="project-original")
    return settle(product.application, product.application.submit(command, idempotency_key=key))


def read_history(product):
    result = product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
        product.profile_id, product.timeline_id))
    if result.status != "available":
        raise ValueError("canonical-history-unavailable")
    return result.projection.turns


def _require_terminal(result):
    if result.status != "terminal":
        raise ValueError(getattr(result.projection, "failure_code", None)
            or getattr(result.problem, "code", None) or "operation-not-terminal")


def seed_branch(product, adapter):
    _require_terminal(send(product, adapter.specification["shared_intro"]["user"], "s112-common-seed-intro"))
    for index in range(2):
        _require_terminal(settle(product.application, product.application.simulate_first_life_step(
            FirstLifeSimulationRequest(f"s112-common-seed-life-{index}"))))
    _require_terminal(settle(product.application, product.application.heartbeat_first_life(
        FirstLifeHeartbeatRequest("s112-common-seed-session", "s112-common-seed-share"))))
    _require_terminal(settle(product.application, product.application.set_first_life_controls(
        FirstLifeControlRequest("s112-common-seed-pause", paused=True, sharing_enabled=False))))
    history = read_history(product)
    life = product.application.query_first_life()
    if (life.status != "available" or len(history) != 1 or len(life.versions) != 2 or len(life.shares) != 1
        or history[0].assistant_text != adapter.specification["shared_intro"]["assistant"]
        or [asdict(version.plan) for version in life.versions] != adapter.scenario["plans"]
        or life.shares[0].text != adapter.scenario["share"]):
        raise ValueError("canonical-synthetic-seed-mismatch")
    status = product.application.first_life_status()
    if not status.paused or status.sharing_enabled:
        raise ValueError("synthetic-life-was-not-paused")
    return dict(history=[asdict(row) for row in history], life=asdict(life), status=asdict(status),
        source_digest=digest(dict(character=adapter.specification["character"], intro=adapter.specification["shared_intro"],
            plans=adapter.scenario["plans"], share=adapter.scenario["share"])), calls=adapter.calls,
        generation="programmed-synthetic-seed", real_provider_calls=0)


def _safe_error(error):
    # Do not serialize arbitrary exception strings from transports or credentials.
    return dict(type=type(error).__name__, code=getattr(error, "code", None),
        location=[dict(file=Path(frame.filename).name, line=frame.lineno, function=frame.name)
            for frame in traceback.extract_tb(error.__traceback__)])


def _result(result):
    return dict(status=result.status.value, failure_code=getattr(result.projection, "failure_code", None),
        problem_code=getattr(result.problem, "code", None),
        reply=getattr(result.projection, "expression_text", None))


def run_comparison(approval, *, opener=None, transport=None):
    """Run once; an existing journal prevents implicit retry after interruption."""
    if opener is None:
        from dynamic_subject_agent.local_product import open_first_life_reply_trial
        opener = open_first_life_reply_trial
    specification = approval.scenarios
    root = Path(approval.root).resolve()
    journal = Journal(root / "continuous-results.jsonl")
    original_observations = approval.observations
    approval.observations = JournaledObservations(original_observations, journal)
    summary = dict(version=VERSION, scenario_digest=digest(specification), branches=[])
    initial_sources = {}
    try:
        journal.append(dict(event="run-started", version=VERSION, scenario_digest=digest(specification),
            identity_scope="separate authority/root/Timeline; same sealed definition and profile ID are allowed"))
        prepared = []
        for scenario in specification["scenarios"]:
            for route in ("A", "B"):
                branch_id = scenario["id"] + "-" + route
                branch = prepare_branch(root / branch_id, specification)
                prepared.append((scenario, branch_id, branch))
                journal.append(dict(event="branch-prepared", branch_id=branch_id,
                    definition_basis=branch.definition_basis, runtime_asset_sha=branch.runtime_asset_sha,
                    material_digest=branch.material_digest))
        if len({branch.definition_basis for _, _, branch in prepared}) != 1:
            raise ValueError("same-source-definition-mismatch")
        for scenario, branch_id, branch in prepared:
            product = None
            branch_observations_start = len(approval.observations)
            approval.observations.branch_id = branch_id
            approval.observations.step = None
            entry = dict(branch_id=branch_id, steps=[], status="preparing")
            summary["branches"].append(entry)
            def opening(seed_gateway=None):
                return opener(branch.config, definition_basis=branch.definition_basis,
                    life_scope_digest=branch.life_scope_digest, approval=approval, branch_id=branch_id,
                    seed_gateway=seed_gateway, _transport=None if seed_gateway is not None else transport)
            try:
                adapter = SeedAdapter(specification, scenario)
                product = opening(ModelGateway(adapter))
                seed = seed_branch(product, adapter)
                identity = (product.profile_id, product.timeline_id)
                entry.update(status="running", seed_source_digest=seed["source_digest"],
                    profile_id=identity[0], timeline_id=identity[1])
                journal.append(dict(event="branch-seeded", branch_id=branch_id, **seed))
                product.close()
                product = opening()
                if (product.profile_id, product.timeline_id) != identity:
                    raise ValueError("branch-identity-changed")
                for index, row in enumerate(scenario["turns"], 1):
                    approval.observations.step = index
                    if row.get("restart_before"):
                        saved = read_history(product)
                        before = len(approval.observations)
                        product.close()
                        product = opening()
                        if ((product.profile_id, product.timeline_id) != identity or read_history(product) != saved
                            or len(approval.observations) != before):
                            raise ValueError("canonical-restart-mismatch")
                        journal.append(dict(event="branch-restarted", branch_id=branch_id, step=index,
                            canonical_history_equal=True, additional_provider_calls=0))
                    start = perf_counter()
                    before = len(approval.observations)
                    journal.append(dict(event="step-started", branch_id=branch_id, step=index,
                        kind=row["kind"], user=row.get("user"), acceptance=row.get("acceptance")))
                    if row["kind"] == "explicit-context-reset":
                        result = settle(product.application, product.application.reset_first_life_context(
                            FirstLifeContextResetRequest("s112-frozen-explicit-reset", row["confirmed"])))
                    else:
                        result = send(product, row["user"], f"s112-frozen-chat-step-{index}")
                    step = dict(step=index, kind=row["kind"], user=row.get("user"),
                        elapsed_seconds=perf_counter() - start, **_result(result),
                        stages=approval.observations[before:],
                        canonical_history=[asdict(turn) for turn in read_history(product)])
                    entry["steps"].append(step)
                    journal.append(dict(event="step-finished", branch_id=branch_id, **step))
                    if index == 1 and step["stages"]:
                        source = json.loads(canonical_json(step["stages"][0]["payload"]))
                        source.pop("policy")
                        source["conversation"].pop("policy")
                        entry["initial_source_digest"] = digest(source)
                        if initial_sources.setdefault(scenario["id"], digest(source)) != digest(source):
                            raise ValueError("A-B-initial-source-mismatch")
                        journal.append(dict(event="initial-sources-verified", branch_id=branch_id,
                            source_digest=digest(source)))
                    if result.status != "terminal":
                        entry["status"] = "stopped-technical-failure"
                        break
                    if row["kind"] == "explicit-context-reset" and step["stages"]:
                        raise ValueError("context-reset-called-model")
                    if product.application.query_first_life().project.current_plan != life_plan(seed):
                        raise ValueError("chat-mutated-seeded-plan")
                else:
                    entry["status"] = "completed"
            except Exception as error:
                entry["status"] = "stopped-technical-failure"
                entry["error"] = _safe_error(error)
                journal.append(dict(event="branch-stopped", branch_id=branch_id, error=entry["error"],
                    observations=approval.observations[branch_observations_start:]))
            finally:
                if product is not None:
                    product.close()
                journal.append(dict(event="branch-finished", branch_id=branch_id, status=entry["status"]))
        if hasattr(approval, "shared_budget"):
            total, used, remaining = approval.shared_budget().counts()
            summary["shared_attempt_budget"] = dict(total=total, used=used, remaining=remaining,
                mode="live" if approval.read()["live"] else "synthetic-transport-validation")
        journal.append(dict(event="run-finished", branches=[dict(branch_id=row["branch_id"], status=row["status"])
            for row in summary["branches"]]))
        _write_new(root / "continuous-summary.json", summary)
        return summary
    finally:
        original_observations[:] = approval.observations
        approval.observations = original_observations
        journal.close()


def life_plan(seed):
    from dynamic_subject_agent.first_life import CompositionPlan
    return CompositionPlan(**seed["life"]["project"]["current_plan"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="execute the already approved fixed-root real comparison")
    parser.add_argument("--confirmed", action="store_true", help="assert the recorded S112 approval")
    args = parser.parse_args(argv)
    if not args.live or not args.confirmed:
        parser.error("real execution requires --live --confirmed; offline tests inject a synthetic transport")
    from dynamic_subject_agent.first_life_reply_live import fixed_live_root, open_approved_trial
    approval = open_approved_trial(fixed_live_root(), SCENARIOS_PATH, confirmed=True, live=True)
    summary = run_comparison(approval)
    print(canonical_json(dict(result=str(approval.root / "continuous-summary.json"),
        branches=[dict(branch_id=row["branch_id"], status=row["status"]) for row in summary["branches"]])))
    return 0 if all(row["status"] == "completed" for row in summary["branches"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
