"""S151 same-use direct-final protocol; old S150 policies and grants stay exact."""
from dataclasses import dataclass
from dynamic_subject_agent.model_gateway import ModelTaskKind
from dynamic_subject_agent.shared_activity import digest

BUDGET_VERSION='natural-feedback-direct-final-live-s151-1'
BUDGET_DEVELOPMENT='user-requested-truncation-repair-2026-10-11'
# Set once from the closed protocol, separately from the human S150 use basis.
BUDGET_PROTOCOL_SHA='55a69fdb206af0ba4202ec025bc06ece483b409b3201de2405faa0ac4ae1b41c'


def feedback_protocol(kind,technical_variant='baseline'):
    if technical_variant not in ('baseline','direct-final','scoped','intent-only') or kind not in (
        ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK,ModelTaskKind.SHARED_ACTIVITY_CHOICE):
        raise ValueError('closed feedback protocol kind and variant required')
    from dynamic_subject_agent.character_communication_trial_provider import communication_protocol
    base=communication_protocol('thinking-high','low')
    expression=dict(base['expression'])
    if technical_variant in ('direct-final','scoped','intent-only') and kind is ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK:
        expression.pop('reasoning_effort')
        expression['thinking']={'type':'disabled'}
    return dict(model=base['model'],endpoint=base['endpoint'],timeout_seconds=base['timeout_seconds'],
        accepted_response_models=base['accepted_response_models'],expression=expression)


def budget_protocol_witness():
    return {kind.value:feedback_protocol(kind,'direct-final') for kind in (
        ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK,ModelTaskKind.SHARED_ACTIVITY_CHOICE)}


@dataclass(frozen=True)
class NaturalFeedbackBudgetDevelopmentGrant:
    review_basis:str
    development_authorization:str
    def __post_init__(self):
        from dynamic_subject_agent.natural_feedback_live import APPROVED_FEEDBACK_REVIEW
        if self.review_basis!=APPROVED_FEEDBACK_REVIEW or self.development_authorization!=BUDGET_DEVELOPMENT:
            raise ValueError('approved S150 uses and exact continued S151 development required')
    def validate(self):
        from dynamic_subject_agent.natural_feedback_live import ApprovedNaturalFeedbackGrant
        self.__post_init__()
        ApprovedNaturalFeedbackGrant(self.review_basis,True).validate()
        if digest(budget_protocol_witness())!=BUDGET_PROTOCOL_SHA:
            raise ValueError('pinned S151 budget protocol changed')


def feedback_budget_contract(binding):
    from dynamic_subject_agent.natural_feedback_live import APPROVED_FEEDBACK_REVIEW,feedback_live_contract
    NaturalFeedbackBudgetDevelopmentGrant(APPROVED_FEEDBACK_REVIEW,BUDGET_DEVELOPMENT).validate()
    base=feedback_live_contract(binding)
    return dict(base,version=BUDGET_VERSION,development_authorization=BUDGET_DEVELOPMENT,
        technical_variant=dict(base['technical_variant'],protocol_variant='direct-final',protocol_sha=BUDGET_PROTOCOL_SHA))
