"""Independent qualification for S152 compact output and requested frame."""
from dataclasses import dataclass
from hashlib import sha256
from dynamic_subject_agent.natural_feedback_frame import SCOPED_POLICY,SCOPED_DEVELOPMENT

SCOPED_POLICY_SHA='876c2d4bf485c2e7b0a6a257b55b21a76b55d61ebffbc59c70d43b541b0109c6'

@dataclass(frozen=True)
class NaturalFeedbackScopedDevelopmentGrant:
    review_basis:str
    development_authorization:str
    def __post_init__(self):
        from dynamic_subject_agent.natural_feedback_live import APPROVED_FEEDBACK_REVIEW
        if self.review_basis!=APPROVED_FEEDBACK_REVIEW or self.development_authorization!=SCOPED_DEVELOPMENT:
            raise ValueError('approved feedback uses and S152 continued decision required')
    def validate(self):
        from dynamic_subject_agent.natural_feedback_budget import NaturalFeedbackBudgetDevelopmentGrant,BUDGET_DEVELOPMENT
        self.__post_init__()
        NaturalFeedbackBudgetDevelopmentGrant(self.review_basis,BUDGET_DEVELOPMENT).validate()
        if sha256(SCOPED_POLICY.encode()).hexdigest()!=SCOPED_POLICY_SHA:raise ValueError('pinned scoped policy changed')
