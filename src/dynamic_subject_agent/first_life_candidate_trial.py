"""S114's exact candidate approval, bound to the existing S112 parent allowance.

No sender or credential path lives here. A new approval can reserve only the
already approved 18-attempt child allowance; existing roots never reinitialize it.
"""
from dataclasses import dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path

from dynamic_subject_agent import first_life_reply_candidate as candidate
from dynamic_subject_agent.character_communication_trial_provider import communication_protocol
from dynamic_subject_agent.first_life_reply_drafts import draft_wire, reply_scope_digest
from dynamic_subject_agent.first_life_reply_live import ApprovedReplyTrial, fixed_live_root
from dynamic_subject_agent.first_life_reply_routes import WHOLE_LOCAL_POLICY, PLANNED_LOCAL_POLICY
from dynamic_subject_agent.frozen_attempt import canonical_json


AUTHORIZATION = "s114-user-approved-candidate-18-from-s112-zero-retry-2026-10-01"
PROPOSAL_DIGEST = "992ed0050555872219da29103a5c83f41b622ba3f097c92312c251283b7e3c6e"
PACKAGE_DIGEST = "38d0a145d01df525d6fbec3fa2a852a2b2db12a1bd4996fffc158f2b59ed23ea"
WHOLE_CANDIDATE_POLICY = "first-life-whole-candidate-s114-1"
PLANNED_CANDIDATE_POLICY = "first-life-planned-candidate-s114-1"
CANDIDATE_POLICIES = (WHOLE_CANDIDATE_POLICY, PLANNED_CANDIDATE_POLICY)


def _digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


def fixed_candidate_root():
    return fixed_live_root() / "candidate-s114"


def _candidate_contract():
    return dict(version=candidate.CANDIDATE_VERSION, role_policy=candidate.ROLE_POLICY,
        whole_output_policy=candidate.WHOLE_OUTPUT_POLICY,
        expression_output_policy=candidate.EXPRESSION_OUTPUT_POLICY,
        protocol=communication_protocol("thinking-high", "low"))


def candidate_reply_scope_digest(definition_basis, policy):
    if policy not in CANDIDATE_POLICIES:
        raise ValueError("exact S114 candidate route required")
    local = WHOLE_LOCAL_POLICY if policy == WHOLE_CANDIDATE_POLICY else PLANNED_LOCAL_POLICY
    return _digest(dict(version=policy, authorization=AUTHORIZATION, proposal=PROPOSAL_DIGEST,
        package=PACKAGE_DIGEST, candidate_contract=_candidate_contract(),
        original_design=reply_scope_digest(definition_basis, local), max_candidate_calls=18,
        max_parent_calls=42, retries=0))


def _verify_document(value, field, expected):
    if type(value) is not dict or value.get(field) != expected:
        raise ValueError("exact approved S114 document required")
    without_digest = dict(value)
    without_digest.pop(field)
    if _digest(without_digest) != expected:
        raise ValueError("approved S114 document content changed")


def _verify_package(package):
    _verify_document(package, "package_sha256", PACKAGE_DIGEST)
    if package["candidate_version"] != candidate.CANDIDATE_VERSION or len(package["cases"]) != 5:
        raise ValueError("exact reviewed candidate builder required")
    for row in package["cases"]:
        baseline = row["baseline_wire_utf8"].encode("utf-8")
        recorded = json.loads(baseline)
        payload = json.loads(recorded["messages"][1]["content"])
        task = candidate.recorded_reply_task(row["task_kind"], payload)
        preview = candidate.preview_reply_candidate(task)
        if (draft_wire(task) != baseline or preview.wire != row["candidate_wire_utf8"].encode("utf-8")
            or preview.baseline_wire_sha256 != row["baseline_wire_sha256"]
            or preview.candidate_wire_sha256 != row["candidate_wire_sha256"]
            or preview.source_payload_sha256 != row["source_payload_sha256"]
            or preview.baseline_bytes != row["baseline_bytes"] or preview.candidate_bytes != row["candidate_bytes"]):
            raise ValueError("candidate builder no longer matches reviewed exact bytes")


def _scenarios(proposal, parent_scenarios):
    """Translate approved short sequences without importing old replies or turns."""
    _verify_document(proposal, "proposal_sha256", PROPOSAL_DIGEST)
    if proposal["candidate_package_sha256"] != PACKAGE_DIGEST:
        raise ValueError("proposal and candidate package differ")
    scenarios = []
    for sequence in proposal["sequences"]:
        original = next(row for row in parent_scenarios["scenarios"] if row["id"] == sequence["id"])
        seed = sequence["seed"]
        if (seed["character"] != parent_scenarios["character"] or seed["intro"] != parent_scenarios["shared_intro"]
            or seed["plans"] != original["plans"] or seed["share"] != original["share"]):
            raise ValueError("candidate seed differs from the approved parent material")
        for step in sequence["steps"]:
            original_step = original["turns"][step["source_step"] - 1]
            if {key: value for key, value in step.items() if key != "source_step"} != original_step:
                raise ValueError("candidate step differs from the approved source step")
        scenarios.append(dict(id=sequence["id"], plans=seed["plans"], share=seed["share"], turns=sequence["steps"]))
    return dict(version="s114-approved-candidate-sequences-1", authorization=AUTHORIZATION,
        character=parent_scenarios["character"], shared_intro=parent_scenarios["shared_intro"], scenarios=scenarios)


def _validate_location(root, parent, parent_value, live):
    if (type(live) is not bool or type(parent) is not ApprovedReplyTrial or parent_value["live"] is not live
        or not isinstance(root, Path) or not root.is_absolute() or root == parent.root.resolve()):
        raise ValueError("separate candidate root and matching parent execution mode required")
    live_parent = fixed_live_root().resolve()
    if live:
        if root != fixed_candidate_root().resolve() or parent.root.resolve() != live_parent:
            raise ValueError("live candidate requires the fixed existing S112 parent and child roots")
    elif root.is_relative_to(live_parent) or parent.root.resolve().is_relative_to(live_parent):
        raise ValueError("offline candidate cannot access the real trial roots")


def _manifest(root, parent, parent_value, proposal, package, live):
    _validate_location(root, parent, parent_value, live)
    _verify_package(package)
    scenarios = _scenarios(proposal, parent_value["scenarios"])
    return dict(version="s114-candidate-approval-1", authorization=AUTHORIZATION, root=str(root), live=live,
        parent=dict(root=str(parent.root.resolve()), manifest_digest=parent.manifest_digest, live=parent_value["live"]),
        provider="deepseek", max_candidate_calls=18, max_parent_calls=42, retries=0,
        proposal=proposal, package=package, candidate_contract=_candidate_contract(),
        scenarios=scenarios, background=parent_value["background"])


def _parent(value):
    if type(value) is not dict or set(value) != {"root", "manifest_digest", "live"}:
        raise ValueError("exact candidate parent binding required")
    parent = ApprovedReplyTrial(Path(value["root"]), value["manifest_digest"])
    checked = parent.read()
    if checked["live"] is not value["live"]:
        raise ValueError("candidate parent mode changed")
    return parent, checked


def _child_budget(value, grant_digest):
    from dynamic_subject_agent.first_life_candidate_budget import CandidateTrialBudget
    return CandidateTrialBudget(Path(value["parent"]["root"]) / "real-budget", grant_digest=grant_digest)


@dataclass
class ApprovedCandidateTrial:
    root: Path
    manifest_digest: str
    observations: list = field(default_factory=list)

    def _verified_manifest(self):
        try:
            root = self.root.resolve()
            value = json.loads((root / "approval.json").read_text(encoding="utf-8"))
            parent, parent_value = _parent(value["parent"])
            expected = _manifest(root, parent, parent_value, value["proposal"], value["package"], value["live"])
            if value != expected or _digest(value) != self.manifest_digest:
                raise ValueError("candidate approval changed")
            return value
        except (KeyError, TypeError, AttributeError):
            raise ValueError("candidate approval is unavailable or malformed") from None

    def read(self):
        value = self._verified_manifest()
        _child_budget(value, self.manifest_digest).counts()
        return value

    @property
    def scenarios(self):
        return self.read()["scenarios"]

    @property
    def parent_budget_path(self):
        return Path(self._verified_manifest()["parent"]["root"]) / "real-budget"

    def parent_counts(self):
        parent, _ = _parent(self._verified_manifest()["parent"])
        return parent.shared_budget().counts()

    def shared_budget(self):
        return _child_budget(self._verified_manifest(), self.manifest_digest)

    def branch(self, branch_id):
        for scenario in self.scenarios["scenarios"]:
            for letter, policy in (("A", WHOLE_CANDIDATE_POLICY), ("B", PLANNED_CANDIDATE_POLICY)):
                if branch_id == scenario["id"] + "-" + letter:
                    return scenario, policy
        raise ValueError("one of the four approved S114 branches required")

    def witness(self, branch_id):
        self.branch(branch_id)
        return dict(kind="s114-candidate", root=str(self.root.resolve()),
            manifest_digest=self.manifest_digest, branch_id=branch_id)

    def validate_task(self, branch_id, task):
        return ApprovedReplyTrial.validate_task(self, branch_id, task)


def candidate_trial_from_witness(witness):
    if (type(witness) is not dict or set(witness) != {"kind", "root", "manifest_digest", "branch_id"}
        or witness["kind"] != "s114-candidate"):
        raise ValueError("exact S114 candidate witness required")
    result = ApprovedCandidateTrial(Path(witness["root"]), witness["manifest_digest"])
    if result.witness(witness["branch_id"]) != witness:
        raise ValueError("S114 candidate witness changed")
    return result


def open_approved_candidate_trial(root, proposal_path, package_path, *, parent, confirmed, live):
    if confirmed is not True or type(parent) is not ApprovedReplyTrial or not isinstance(root, Path) or not root.is_absolute():
        raise ValueError("explicit S114 approval and existing typed parent required")
    root = root.resolve()
    parent_value = parent.read()  # This never initializes a missing parent allowance.
    _validate_location(root, parent, parent_value, live)
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    package = json.loads(package_path.read_text(encoding="utf-8"))
    manifest = _manifest(root, parent, parent_value, proposal, package, live)
    manifest_digest = _digest(manifest)
    if not root.exists():
        # The directory is the initialization claim. An interruption between this
        # record and its grant cannot become a fresh allowance on reopening.
        root.mkdir(parents=True, exist_ok=False)
        with (root / "approval.json").open("x", encoding="utf-8") as output:
            output.write(canonical_json(manifest))
            output.flush()
            os.fsync(output.fileno())
        from dynamic_subject_agent.first_life_candidate_budget import approve_candidate_allowance
        approve_candidate_allowance(parent.shared_budget(), grant_digest=manifest_digest, confirmed=True)
    result = ApprovedCandidateTrial(root, manifest_digest)
    if result.read() != manifest:
        raise ValueError("S114 candidate root cannot be reinitialized or repurposed")
    return result
