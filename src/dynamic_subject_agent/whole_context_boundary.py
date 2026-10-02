"""Closed local whole-chat boundary; no life, model, history deletion, or wire."""
from dataclasses import dataclass, asdict
from hashlib import sha256
from uuid import UUID
import re

from dynamic_subject_agent.frozen_attempt import canonical_json

CONTEXT_AUTHORITY = "original-character-whole-context-deepseek-s132-1"
CONTEXT_INTENT = "whole-context-boundary-input"
CONTEXT_RUNTIME_CONTRACT = "original-whole-context-cycle-s132-1"
CONTEXT_VERSION = "whole-context-boundary-s132-1"
CONTEXT_RECEIPT = "已开始新一段交流；此前聊天仍可查询，人物资料与历史开关保持。"


@dataclass(frozen=True)
class WholeContextBoundaryRequest:
    target_profile_id: str
    target_timeline_id: str
    request_id: str
    expected_revision: int
    confirmed: bool = False

    @property
    def request_digest(self):
        return sha256(canonical_json(asdict(self)).encode()).hexdigest()


@dataclass(frozen=True)
class WholeContextBoundaryResponse:
    status: str
    receipt: object | None = None
    problem_code: str = ""


@dataclass(frozen=True)
class WholeContextInput:
    target_profile_id: str
    target_timeline_id: str
    request_digest: str
    expected_revision: int
    expected_basis: dict
    authorization: dict

    def __post_init__(self):
        from dynamic_subject_agent.original_whole_chat import OriginalWholeAuthorization
        if (any(str(UUID(value)) != value for value in (self.target_profile_id, self.target_timeline_id))
            or re.fullmatch(r"[0-9a-f]{64}", self.request_digest) is None
            or type(self.expected_revision) is not int or self.expected_revision < 0
            or type(self.expected_basis) is not dict
            or set(self.expected_basis) != {"head_sequence", "published_outcome_digest", "verified_prefix_digest", "revision_head_digest"}
            or type(self.expected_basis["head_sequence"]) is not int or self.expected_basis["head_sequence"] < 0
            or any(re.fullmatch(r"[0-9a-f]{64}", self.expected_basis[key]) is None for key in ("verified_prefix_digest", "revision_head_digest"))):
            raise ValueError("exact whole boundary input required")
        outcome = self.expected_basis['published_outcome_digest']
        if (self.expected_basis['head_sequence'] == 0 and outcome is not None
            or self.expected_basis['head_sequence'] > 0 and (type(outcome) is not str or re.fullmatch(r'[0-9a-f]{64}', outcome) is None)):
            raise ValueError('whole boundary outcome prefix invalid')
        authorization = OriginalWholeAuthorization(**self.authorization)
        if authorization.identity_id != self.target_profile_id:
            raise ValueError('whole boundary authorization target differs')

    contract_version = "M0-CONTRACT-1.0"
    kind = "WholeContextBoundaryInput"
    declared_intent = CONTEXT_INTENT
    normalization_version = CONTEXT_VERSION
    language = "zh"
    provenance = "project-original"

    @property
    def payload_fingerprint(self):
        return sha256(canonical_json(dict(version=CONTEXT_VERSION, **asdict(self))).encode()).hexdigest()


CONTEXT_DDL = (
    "CREATE TABLE whole_context_input (operation_id BLOB PRIMARY KEY REFERENCES subject_operation(operation_id), input_json TEXT NOT NULL, payload_fingerprint BLOB NOT NULL)",
    "CREATE TABLE whole_context_boundary (plan_id BLOB PRIMARY KEY REFERENCES cycle_commit_plan_receipt(plan_id), revision INTEGER NOT NULL UNIQUE, cutoff_sequence INTEGER NOT NULL UNIQUE, record_json TEXT NOT NULL, record_digest TEXT NOT NULL)",
)
