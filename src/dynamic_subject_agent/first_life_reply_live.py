"""One explicitly approved S112 trial; immutable materials and one shared cap.

This is experiment authority, not a new product data store. Runtime history
continues to belong exclusively to each branch's existing Timeline.
"""
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path

from dynamic_subject_agent.character_chat_budget import CharacterChatBudget
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.first_life_reply_routes import (
    WHOLE_LIVE_POLICY, PLANNED_LIVE_POLICY, LIVE_REPLY_POLICIES,
    WHOLE_LOCAL_POLICY, PLANNED_LOCAL_POLICY,
)
from dynamic_subject_agent.first_life_reply_drafts import reply_scope_digest
from dynamic_subject_agent.model_gateway import ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelTaskKind

AUTHORIZATION = "s112-user-approved-s111-42-zero-retry-2026-10-01"
SCENARIOS_DIGEST = "a59e2022e84b7d5414d58b6d12580e0daf35a2acbb4a153847feb645f20141d3"
BACKGROUND_DIGEST = "859bf423e98ca372f7f86ba79751d92ebcfea5e4724234bdcce3171c16883934"
REVIEW_DIGEST = "1a53333b984463f58715a5fb81afe260756d7202fd9e5eafd92a9f313b7fdc6e"


def _digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


def fixed_live_root():
    return Path(os.environ["LOCALAPPDATA"]) / "DynamicSubjectAgent" / "s112-reply-comparison"


def live_reply_scope_digest(definition_basis, policy):
    if policy not in LIVE_REPLY_POLICIES:
        raise ValueError("exact S112 route required")
    local = WHOLE_LOCAL_POLICY if policy == WHOLE_LIVE_POLICY else PLANNED_LOCAL_POLICY
    return _digest(dict(version=policy, authorization=AUTHORIZATION,
        scenarios=SCENARIOS_DIGEST, review=REVIEW_DIGEST, background=BACKGROUND_DIGEST,
        local_design=reply_scope_digest(definition_basis, local), max_real_calls=42, retries=0))


def _manifest(scenarios, background, live):
    if type(live) is not bool or _digest(scenarios) != SCENARIOS_DIGEST or _digest(background) != BACKGROUND_DIGEST:
        raise ValueError("exact approved synthetic materials required")
    return dict(version="s112-reply-approval-1", authorization=AUTHORIZATION, live=live,
        provider="deepseek", max_real_calls=42, initial_used=0, retries=0,
        scenarios=scenarios, background=background, review_digest=REVIEW_DIGEST)


@dataclass
class ApprovedReplyTrial:
    root: Path
    manifest_digest: str
    observations: list = field(default_factory=list)

    def read(self):
        value = json.loads((self.root / "approval.json").read_text(encoding="utf-8"))
        if value != _manifest(value["scenarios"], value["background"], value["live"]) or _digest(value) != self.manifest_digest:
            raise ValueError("S112 approval changed")
        if value["live"] and self.root.resolve() != fixed_live_root().resolve():
            raise ValueError("real trial requires the single approved local root")
        self.shared_budget().counts()
        return value

    def shared_budget(self):
        return CharacterChatBudget(self.root / "real-budget", total=42, initial_used=0)

    @property
    def scenarios(self):
        return self.read()["scenarios"]

    def branch(self, branch_id):
        value = self.read()
        for scenario in value["scenarios"]["scenarios"]:
            for letter, policy in (("A", WHOLE_LIVE_POLICY), ("B", PLANNED_LIVE_POLICY)):
                if branch_id == scenario["id"] + "-" + letter:
                    return scenario, policy
        raise ValueError("one of the four approved branches required")

    def witness(self, branch_id):
        self.branch(branch_id)
        return dict(root=str(self.root.resolve()), manifest_digest=self.manifest_digest, branch_id=branch_id)

    def validate_task(self, branch_id, task):
        """Enforce the frozen experiment's material scope before any HTTPS call."""
        scenario, _ = self.branch(branch_id)
        approved = self.read()["background"]
        payload = json.loads(canonical_json(asdict(task.payload)))
        for key in ("character_core", "personality", "runtime_identity", "current_activity"):
            if payload[key] != approved[key]:
                raise ValueError("unapproved S112 character/activity material")
        if (payload["current_plan"] != scenario["plans"][-1]
            or payload["related_event"] != approved["related_events"][scenario["id"]]):
            raise ValueError("unapproved S112 life material")
        conversation = payload["conversation"]
        for key, value in approved["conversation"].items():
            if conversation[key] != value:
                raise ValueError("unapproved S112 conversation foreground")
        if conversation["current_message"] not in [row["user"] for row in scenario["turns"] if row["kind"] == "chat"]:
            raise ValueError("unapproved S112 current message")
        allowed_users = {row["user"] for row in scenario["turns"] if row["kind"] == "chat"}
        allowed_users.add(self.scenarios["shared_intro"]["user"])
        for row in payload.get("dialogue_sources", payload.get("selected_dialogue", [])):
            if (row["speaker"] == "user" and row["text"] not in allowed_users
                or row["kind"] == "proactive-share" and row["text"] != scenario["share"]):
                raise ValueError("unapproved S112 prior user or share material")
        for row in conversation.get("self_knowledge", conversation.get("selected_facts", [])):
            if {k: v for k, v in row.items() if k != "label"} not in approved["knowledge"]:
                raise ValueError("unapproved S112 selected fact")


def approved_trial_from_witness(witness):
    if type(witness) is not dict or set(witness) != {"root", "manifest_digest", "branch_id"}:
        raise ValueError("exact S112 approval witness required")
    result = ApprovedReplyTrial(Path(witness["root"]), witness["manifest_digest"])
    if result.witness(witness["branch_id"]) != witness:
        raise ValueError("S112 witness mismatch")
    return result


def resolve_reply_trial(witness):
    """Exact dispatch for independently approved trial witnesses, no fallback."""
    if type(witness) is dict and witness.get("kind") == "s114-candidate":
        from dynamic_subject_agent.first_life_candidate_trial import candidate_trial_from_witness
        return candidate_trial_from_witness(witness)
    return approved_trial_from_witness(witness)


def approved_reply_scope_digest(definition_basis, policy):
    from dynamic_subject_agent.first_life_reply_routes import CANDIDATE_REPLY_POLICIES
    if policy in CANDIDATE_REPLY_POLICIES:
        from dynamic_subject_agent.first_life_candidate_trial import candidate_reply_scope_digest
        return candidate_reply_scope_digest(definition_basis, policy)
    return live_reply_scope_digest(definition_basis, policy)


class ApprovedSeedAdapter(ProviderAdapter):
    """A local seed gateway cannot introduce arbitrary prior dialogue or life."""
    capabilities = ProviderCapabilities("s112-fixed-seed", "program", True, (StructuredOutputMode.JSON_OBJECT,))

    def __init__(self, gateway, approval, branch_id):
        if gateway.capabilities.local is not True:
            raise ValueError("local seed gateway required")
        self.gateway, self.approval, self.branch_id = gateway, approval, branch_id

    def invoke(self, task):
        specification = self.approval.scenarios
        scenario, _ = self.approval.branch(self.branch_id)
        projection = asdict(task.payload)
        if task.kind is ModelTaskKind.CHARACTER_FIRST_LIFE_DECISION:
            phase = projection["current_activity"]["phase"]
            if phase not in ("unstarted", "drafted"):
                raise ValueError("only the two approved seed life decisions are allowed")
            index = 0 if phase == "unstarted" else 1
            expected = dict(action="start" if index == 0 else "revise", plan=scenario["plans"][index], reason_code="balance-space")
        elif task.kind is ModelTaskKind.CHARACTER_FIRST_LIFE_SHARE:
            expected = dict(share=True, reply_text=scenario["share"], language="zh", focus="composition", opening="self-interest")
        else:
            if projection["conversation"]["current_message"] != specification["shared_intro"]["user"]:
                raise ValueError("only the approved common opening can use seed mode")
            if task.kind is ModelTaskKind.CHARACTER_COMMUNICATION_PLAN:
                expected = dict(action="answer", fact_refs=[], use_life=False, focus="respond-current", dialogue_refs=[])
            elif task.kind in (ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY, ModelTaskKind.CHARACTER_FIRST_LIFE_FACT_EXPRESSION):
                expected = dict(reply_text=specification["shared_intro"]["assistant"], language="zh")
                if task.kind is ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY:
                    expected["use_life"] = False
            else:
                raise ValueError("unapproved seed stage")
        result = self.gateway.execute(task)
        if result.value != expected:
            raise ValueError("seed response differs from the approved synthetic material")
        return result


def verify_trial_seed(product, approval, branch_id):
    from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
    scenario, _ = approval.branch(branch_id)
    intro = approval.scenarios["shared_intro"]
    history = product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
        product.profile_id, product.timeline_id))
    life = product.application.query_first_life()
    status = product.application.first_life_status()
    if (history.status != "available" or len(history.projection.turns) != 1
        or history.projection.turns[0].user_text != intro["user"]
        or history.projection.turns[0].assistant_text != intro["assistant"]
        or life.status != "available" or len(life.versions) != 2 or len(life.shares) != 1
        or [asdict(version.plan) for version in life.versions] != scenario["plans"]
        or life.shares[0].text != scenario["share"] or not status.paused or status.sharing_enabled):
        raise ValueError("canonical S112 seed must exactly match the approved material before live mode")


def open_approved_trial(root, scenarios_path, *, confirmed, live):
    if confirmed is not True or type(live) is not bool or not isinstance(root, Path) or not root.is_absolute():
        raise ValueError("explicit S112 approval and absolute trial root required")
    root = root.resolve()
    if live and root != fixed_live_root().resolve():
        raise ValueError("one approved real trial root required")
    scenarios = json.loads(scenarios_path.read_text(encoding="utf-8"))
    background = json.loads(scenarios_path.with_name("s112-reviewed-background.json").read_text(encoding="utf-8"))
    manifest = _manifest(scenarios, background, live)
    if not root.exists():
        root.mkdir(parents=True, exist_ok=False)
        # If interrupted, the incomplete root cannot silently allocate again.
        with (root / "approval.json").open("x", encoding="utf-8") as stream:
            stream.write(canonical_json(manifest))
        CharacterChatBudget(root / "real-budget", total=42, initial_used=0, initialize=True)
    result = ApprovedReplyTrial(root, _digest(manifest))
    if result.read() != manifest:
        raise ValueError("S112 trial cannot be reinitialized or repurposed")
    return result
