"""S119's confirmed, separate free-text use for the original synthetic character.

Reuse the same A projection, strict output, canonical history and development
audit. Only current/user-dialogue text becomes open; all other material remains
the exact original fixture. This does not relax the S117 approval or its reader.
"""
from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
from uuid import UUID

from dynamic_subject_agent.first_life_development_trial import (DevelopmentReplyTrial, digest, _contract)
from dynamic_subject_agent.first_life_reply_drafts import reply_scope_digest
from dynamic_subject_agent.first_life_reply_live import SCENARIOS_DIGEST, BACKGROUND_DIGEST
from dynamic_subject_agent.first_life_reply_routes import (WHOLE_FREE_INPUT_POLICY, WHOLE_FREE_TOPIC_POLICY, WHOLE_LOCAL_POLICY, _whole)
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
from dynamic_subject_agent.reply_protocol_trial import fixed_development_root
from dynamic_subject_agent.development_model_calls import DevelopmentCallAudit


AUTHORIZATION = "user-approved-s118-free-input-purpose-2026-10-02"
CALL_PURPOSE = "free-input-character-chat"


def data_use_contract():
    return dict(version="s119-free-input-data-use-1", authorization=AUTHORIZATION,
        confirmed_user_answer="同意", confirmation_date="2026-10-02",
        provider="deepseek", endpoint="https://api.deepseek.com/chat/completions",
        credential_use="existing-windows-slot-https-bearer-only", current_message_chars=1000,
        committed_turns=2, committed_turns_total_chars=4000, share_chars=400,
        share_count=1, history_off="no-prior-dialogue-or-share",
        history_source="current-identity-canonical-timeline-only", attachments=False,
        life_generation=False, persona_rewrite=False, call_limit=None, automatic_retries=0,
        character_source_sha256=SCENARIOS_DIGEST, background_sha256=BACKGROUND_DIGEST)


def expression_contract(variant):
    contract=_contract()
    if variant=="baseline":return contract
    if variant!="current-topic":raise ValueError("known free input expression variant required")
    from dynamic_subject_agent.first_life_self_choice_candidate import EVIDENCE_BEFORE,EVIDENCE_AFTER,REPAIR_BEFORE
    from dynamic_subject_agent.first_life_current_topic_candidate import TOPIC_REPAIR,CANDIDATE_VERSION
    role=contract["role_policy"]
    if role.count(EVIDENCE_BEFORE)!=1 or role.count(REPAIR_BEFORE)!=1:
        raise ValueError("exact original expression contract required")
    contract["role_policy"]=role.replace(EVIDENCE_BEFORE,EVIDENCE_AFTER,1).replace(REPAIR_BEFORE,TOPIC_REPAIR,1)
    contract["candidate_version"]=CANDIDATE_VERSION
    return contract


def free_input_reply_scope_digest(definition_basis, policy):
    if policy not in (WHOLE_FREE_INPUT_POLICY,WHOLE_FREE_TOPIC_POLICY):
        raise ValueError("exact free input A policy required")
    return digest(dict(version=policy, data_use=data_use_contract(),
        original_design=reply_scope_digest(definition_basis, WHOLE_LOCAL_POLICY),
        contract=expression_contract("baseline" if policy==WHOLE_FREE_INPUT_POLICY else "current-topic")))


def fixed_free_input_runs_root():
    return fixed_development_root() / "free-input-runs"


def fixed_free_input_audit_path():
    # An old, already-running S118 reader does not recognize the new purpose.
    # Keep its audit unchanged instead of adding rows it would reject.
    return fixed_development_root() / "free-input-audit"


def _open_live_audit():
    path=fixed_free_input_audit_path()
    witness=path.with_name(path.name+"-initialized")
    if witness.exists():
        if not witness.is_dir() or not path.exists():
            raise ValueError("free input audit witness mismatch")
        return DevelopmentCallAudit(path)
    if path.exists():
        raise ValueError("free input audit initialization witness missing")
    witness.mkdir(parents=True,exist_ok=False)
    return DevelopmentCallAudit(path,initialize=True)


def _manifest(root, scenarios, background, live,expression_variant="baseline"):
    if (type(live) is not bool or str(UUID(root.name)) != root.name
        or digest(scenarios) != SCENARIOS_DIGEST or digest(background) != BACKGROUND_DIGEST):
        raise ValueError("exact original materials and free input UUID root required")
    if live:
        if root.parent != fixed_free_input_runs_root().resolve():
            raise ValueError("fixed free input live directory required")
    elif root.is_relative_to(fixed_development_root().resolve()):
        raise ValueError("offline free input cannot use the live directory")
    result=dict(version="s119-free-input-approval-1", authorization=AUTHORIZATION, root=str(root),
        live=live, provider="deepseek", call_limit=None, retries=0, call_purpose=CALL_PURPOSE, data_use=data_use_contract(),
        scenarios=scenarios, background=background, contract=expression_contract(expression_variant))
    if expression_variant!="baseline":result.update(version="s120-free-input-approval-1",expression_variant=expression_variant)
    return result


class MetadataOnlyObservations(list):
    """No private prompt or reply retained in a second observation list."""
    def append(self, row):
        super().append({key:row[key] for key in ("task_kind","request_digest","wire_sha256",
            "error_code","model","usage","finish_reason","elapsed_seconds") if key in row})


@dataclass
class FreeInputReplyTrial(DevelopmentReplyTrial):
    observations: list = field(default_factory=MetadataOnlyObservations)
    call_purpose = CALL_PURPOSE

    def _manifest(self):
        root=self.root.resolve()
        value=json.loads((root/"approval.json").read_text(encoding="utf-8"))
        if (value != _manifest(root,value["scenarios"],value["background"],value["live"],value.get("expression_variant","baseline"))
            or digest(value) != self.manifest_digest):
            raise ValueError("free input approval changed")
        return value

    def shared_budget(self):
        value=self._manifest()
        path=fixed_free_input_audit_path() if value["live"] else self.root/"offline-audit"
        if value["live"] and not path.with_name(path.name+"-initialized").is_dir():
            raise ValueError("existing free input audit witness required")
        return DevelopmentCallAudit(path)

    def branch(self, branch_id):
        value=self.read()
        for scenario in value["scenarios"]["scenarios"]:
            if branch_id == scenario["id"]+"-A":
                return scenario, WHOLE_FREE_TOPIC_POLICY if value.get("expression_variant")=="current-topic" else WHOLE_FREE_INPUT_POLICY
        raise ValueError("one of the two authorized free input A branches required")

    def witness(self, branch_id):
        self.branch(branch_id)
        return dict(kind="s119-free-input", root=str(self.root.resolve()),
            manifest_digest=self.manifest_digest, branch_id=branch_id)

    def validate_task(self, branch_id, task):
        if type(task) is not ModelTask or task.kind is not ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY:
            raise ValueError("only typed A reply can use the free input purpose")
        _whole(task.payload)  # Includes complete <=2 pairs/4000, share/400 and history-off.
        scenario,_=self.branch(branch_id)
        approved=self.read()["background"]
        payload=json.loads(canonical_json(asdict(task.payload)))
        for key in ("character_core","personality","runtime_identity","current_activity"):
            if payload[key] != approved[key]:
                raise ValueError("free text does not authorize other character material")
        if (payload["current_plan"] != scenario["plans"][-1]
            or payload["related_event"] != approved["related_events"][scenario["id"]]):
            raise ValueError("free text does not authorize different life material")
        conversation=payload["conversation"]
        for key,value in approved["conversation"].items():
            if conversation[key] != value:
                raise ValueError("free input foreground changed")
        for row in conversation["self_knowledge"]:
            if {k:v for k,v in row.items() if k != "label"} not in approved["knowledge"]:
                raise ValueError("unapproved selected self knowledge")
        message=conversation["current_message"]
        if type(message) is not str or not message.strip() or len(message)>1000 or "\x00" in message:
            raise ValueError("bounded free current text required")
        for row in payload["dialogue_sources"]:
            if row["kind"] == "proactive-share":
                if row["text"] != scenario["share"]:
                    raise ValueError("unapproved share material")
            elif len(row["text"]) > (1000 if row["speaker"] == "user" else 1200):
                raise ValueError("source exceeds the submitted user/reply contract")


def free_input_trial_from_witness(witness):
    if (type(witness) is not dict or set(witness) != {"kind","root","manifest_digest","branch_id"}
        or witness["kind"] != "s119-free-input"):
        raise ValueError("exact free input witness required")
    result=FreeInputReplyTrial(Path(witness["root"]),witness["manifest_digest"])
    if result.witness(witness["branch_id"]) != witness:
        raise ValueError("free input witness changed")
    return result


def open_free_input_reply_trial(root, scenarios_path, *, live, confirmed,expression_variant="baseline"):
    if confirmed is not True or not isinstance(root,Path) or not root.is_absolute():
        raise ValueError("confirmed free input purpose and absolute root required")
    root=root.resolve()
    scenarios=json.loads(scenarios_path.read_text(encoding="utf-8"))
    background=json.loads(scenarios_path.with_name("s112-reviewed-background.json").read_text(encoding="utf-8"))
    manifest=_manifest(root,scenarios,background,live,expression_variant)
    if live:
        _open_live_audit()
    if not root.exists():
        root.mkdir(parents=True,exist_ok=False)
        with (root/"approval.json").open("x",encoding="utf-8") as stream:
            stream.write(canonical_json(manifest));stream.flush();os.fsync(stream.fileno())
        if not live:
            DevelopmentCallAudit(root/"offline-audit",initialize=True)
    result=FreeInputReplyTrial(root,digest(manifest))
    if result.read() != manifest:
        raise ValueError("free input root cannot be reset or repurposed")
    return result
