"""Exact review bytes and scope digests for reply experiments; no sender."""
from dataclasses import asdict
from hashlib import sha256
import re

from dynamic_subject_agent import first_life_followup as v4
from dynamic_subject_agent import first_life_reply_routes as routes
from dynamic_subject_agent.first_life_reply_routes import (
    WHOLE_LOCAL_POLICY, PLANNED_LOCAL_POLICY, LOCAL_REPLY_POLICIES,
    _planning, _whole, _expression,
)
from dynamic_subject_agent.first_life_relevance import PERSONALITY_RELEVANCE_POLICY
from dynamic_subject_agent.first_life_followup_provider import DeepSeekFirstLifeFollowupAdapter
from dynamic_subject_agent.character_communication_trial_provider import communication_protocol
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind
from dynamic_subject_agent.frozen_attempt import canonical_json


def draft_wire(task):
    """Return exact review bytes only; this function has no execution path."""
    if type(task) is not ModelTask:
        raise ValueError("typed local reply draft task required")
    if task.kind is ModelTaskKind.CHARACTER_COMMUNICATION_PLAN:
        _planning(task.payload)
        return DeepSeekFirstLifeFollowupAdapter.wire(task)
    if task.kind is ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY:
        _whole(task.payload)
        policy = routes.WHOLE_REPLY_POLICY
    elif task.kind is ModelTaskKind.CHARACTER_FIRST_LIFE_FACT_EXPRESSION:
        _expression(task.payload)
        policy = routes.FACT_EXPRESSION_POLICY
    else:
        raise ValueError("unsupported local reply draft task")
    protocol = communication_protocol("thinking-high", "low")
    wire = canonical_json(dict(model=protocol["model"], messages=[dict(role="system",
        content=PERSONALITY_RELEVANCE_POLICY + v4.HISTORY_GROUNDED_POLICY + v4.LIFE_CHAT_POLICY + policy),
        dict(role="user", content=canonical_json(asdict(task.payload)))], **protocol["expression"])).encode()
    if len(wire) > 65536:
        raise ValueError("local reply draft oversized")
    return wire


def reply_scope_digest(definition_basis, policy):
    if (not isinstance(definition_basis, str) or re.fullmatch(r"[0-9a-f]{64}", definition_basis) is None
        or policy not in LOCAL_REPLY_POLICIES):
        raise ValueError("exact local reply definition and policy required")
    output = dict(type="object", additionalProperties=False, required=["reply_text", "language"],
        properties=dict(reply_text=dict(type="string", minLength=1, maxLength=1200, nonblank=True, no_nul=True),
            language=dict(const="zh")))
    if policy == WHOLE_LOCAL_POLICY:
        output["required"].append("use_life")
        output["properties"]["use_life"] = dict(type="boolean", requires_current_request_event_if_true=True)
    scope = dict(version=policy, local_only=True, remote_use_authorized=False,
        baseline_scope=v4.first_life_scope(definition_basis),
        policy_text=routes.WHOLE_REPLY_POLICY if policy == WHOLE_LOCAL_POLICY else routes.FACT_EXPRESSION_POLICY,
        personality_policy=PERSONALITY_RELEVANCE_POLICY, history_policy=v4.HISTORY_GROUNDED_POLICY,
        life_chat_policy=v4.LIFE_CHAT_POLICY, output_schema=output,
        planning_policy=None if policy == WHOLE_LOCAL_POLICY else v4.LIFE_CHAT_SELECTION_POLICY,
        max_stages=1 if policy == WHOLE_LOCAL_POLICY else 2,
        protocol=communication_protocol("thinking-high", "low"),
        disclosure="Only a validated use_life proposal can select the request's committed event; visible facts alone do not disclose it")
    return sha256(canonical_json(scope).encode()).hexdigest()
