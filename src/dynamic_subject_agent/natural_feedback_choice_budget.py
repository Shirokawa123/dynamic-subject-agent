"""Exact S157 same-use choice modes; feedback and edit authority stay multi-span."""
from dataclasses import dataclass
from dynamic_subject_agent.model_gateway import ModelTaskKind
from dynamic_subject_agent.shared_activity import digest
from dynamic_subject_agent.natural_feedback_live import NaturalFeedbackMultispanCallAudit

CHOICE_DEVELOPMENT='user-fixed-six-choice-2026-10-11'
CHOICE_VERSIONS={'choice-low':'natural-feedback-choice-low-live-s157-1',
    'choice-final':'natural-feedback-choice-final-live-s157-1'}
CHOICE_PROTOCOL_HASHES={'choice-low':'7ab4e3cddce108ed1a5f2b6a7fa626f1deddecf7922c29a3812c4723f8ac5df7',
    'choice-final':'6c4f925d39d79af11394211087703124297baacfd0471af3596fb5bf59ad8b8b'}

def choice_protocol(kind,variant):
    if variant not in CHOICE_VERSIONS:raise ValueError('closed independent choice mode required')
    from dynamic_subject_agent.natural_feedback_budget import feedback_protocol
    base=feedback_protocol(kind,'multi-span');expression=dict(base['expression'])
    if kind is ModelTaskKind.SHARED_ACTIVITY_CHOICE:
        if variant=='choice-low':expression['reasoning_effort']='low'
        else:
            expression['thinking']={'type':'disabled'};expression.pop('reasoning_effort')
    return dict(base,expression=expression)

def choice_protocol_witness(variant):
    return {kind.value:choice_protocol(kind,variant) for kind in (
        ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK,ModelTaskKind.SHARED_ACTIVITY_CHOICE)}

@dataclass(frozen=True)
class NaturalFeedbackChoiceBudgetGrant:
    review_basis:str
    development_authorization:str
    variant:str
    def __post_init__(self):
        from dynamic_subject_agent.natural_feedback_live import APPROVED_FEEDBACK_REVIEW
        if (self.review_basis!=APPROVED_FEEDBACK_REVIEW or self.development_authorization!=CHOICE_DEVELOPMENT
            or type(self.variant) is not str or self.variant not in CHOICE_VERSIONS):
            raise ValueError('exact same-use S157 choice development required')
    def validate(self):
        from dynamic_subject_agent.natural_feedback_multispan import NaturalFeedbackMultispanDevelopmentGrant,MULTISPAN_DEVELOPMENT
        self.__post_init__()
        NaturalFeedbackMultispanDevelopmentGrant(self.review_basis,MULTISPAN_DEVELOPMENT).validate()
        if digest(choice_protocol_witness(self.variant))!=CHOICE_PROTOCOL_HASHES[self.variant]:
            raise ValueError('pinned choice budget protocol changed')

def choice_budget_contract(binding,variant):
    from dynamic_subject_agent.natural_feedback_live import APPROVED_FEEDBACK_REVIEW
    from dynamic_subject_agent.natural_feedback_multispan import multispan_contract
    NaturalFeedbackChoiceBudgetGrant(APPROVED_FEEDBACK_REVIEW,CHOICE_DEVELOPMENT,variant).validate()
    base=multispan_contract(binding)
    return dict(base,version=CHOICE_VERSIONS[variant],development_authorization=CHOICE_DEVELOPMENT,
        technical_variant=dict(base['technical_variant'],protocol_variant=variant,
            protocol_sha=CHOICE_PROTOCOL_HASHES[variant],choice_output_mode=variant))

def _audit_config(variant):
    return dict(NaturalFeedbackMultispanCallAudit.configuration(),version='natural-feedback-'+variant+'-audit-s157-1',
        development_authorization=CHOICE_DEVELOPMENT,protocol_sha=CHOICE_PROTOCOL_HASHES[variant],choice_output_mode=variant)

class NaturalFeedbackChoiceLowCallAudit(NaturalFeedbackMultispanCallAudit):
    @staticmethod
    def configuration():return _audit_config('choice-low')

class NaturalFeedbackChoiceFinalCallAudit(NaturalFeedbackMultispanCallAudit):
    @staticmethod
    def configuration():return _audit_config('choice-final')
