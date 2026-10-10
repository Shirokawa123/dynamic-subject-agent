"""S149 same-purpose choice clarification; no changed action/state semantics."""
from dataclasses import dataclass
from hashlib import sha256

from dynamic_subject_agent.shared_activity import digest

ACTION_VERSION = 'living-action-contract-live-s149-1'
ACTION_DEVELOPMENT_AUTHORIZATION = 'user-continued-rework-contract-development-2026-10-10'
ACTION_POLICY_HASHES = ('be5f565ce2eba9410963f1509a5241ab5850e0dc16828b61b15d03da0e4868df',
    '4df535d7abf64f946a721d634efa179ee095f65bb2d29f7aff31e808976de671',
    '7a429342805e6095f425864750ef4047782dd4f354e61d9d64dfc74f01b8534a')
ACTION_PROTOCOL_HASHES = ('3c1bd02909292fd4a835a663d9c3d5e28ff81c1bbaadf6564fed03290dda7450',
    '3c1bd02909292fd4a835a663d9c3d5e28ff81c1bbaadf6564fed03290dda7450',
    '6cb5917026e0a98048608b2fc8ae7901385e12241d713b54767e1b4020420d31')
_OLD_ACTION_OUTPUT = 'start/revise必须形成有实际变化的新方案；其他action的plan必须null。'
_ACTION_OUTPUT = (
    'action=start或revise时，plan必须是{subject,composition,focus}且有实际变化；'
    'action=keep、rework或defer时，plan必须是JSON null，不得带新方案或空对象。'
    'rework只决定进入返工阶段，本次不提交新方案；下一次明确推进、allowed_actions含revise时才可提交修订。'
    '每次先核当前allowed_actions；例子不授予未列出的动作资格，current_plan=null也不能跳过阶段或补造旧方案。'
    '例如合法进入返工的结构为{"action":"rework","plan":null,"reason_code":"try-alternative",'
    '"basis_refs":[],"decision_note":"下一步比较新的构图取舍。"}。'
    '这只是格式例子，不是已发生事件、当前理由或必须选择的动作；实际理由仍来自人物关注与本次可用来源。')


def action_contract_policies():
    from dynamic_subject_agent.living_activity import living_policies
    choice,share,reply=living_policies('final-text')
    if choice.count(_OLD_ACTION_OUTPUT)!=1:
        raise ValueError('exact existing choice action paragraph required')
    return choice.replace(_OLD_ACTION_OUTPUT,_ACTION_OUTPUT,1),share,reply


@dataclass(frozen=True)
class LivingActionContractDevelopmentGrant:
    review_basis: str
    development_authorization: str

    def __post_init__(self):
        from dynamic_subject_agent.living_activity_live import APPROVED_LIVING_REVIEW
        if self.review_basis!=APPROVED_LIVING_REVIEW or self.development_authorization!=ACTION_DEVELOPMENT_AUTHORIZATION:
            raise ValueError('existing living use and exact continued rework decision required')

    def validate(self):
        from dynamic_subject_agent.living_activity_live import (LivingFinalTextDevelopmentGrant,
            FINAL_TEXT_DEVELOPMENT_AUTHORIZATION,living_protocol_for_kind)
        from dynamic_subject_agent.model_gateway import ModelTaskKind
        self.__post_init__()
        LivingFinalTextDevelopmentGrant(self.review_basis,FINAL_TEXT_DEVELOPMENT_AUTHORIZATION).validate()
        if tuple(sha256(p.encode()).hexdigest() for p in action_contract_policies())!=ACTION_POLICY_HASHES:
            raise ValueError('independently pinned action policy changed')
        kinds=(ModelTaskKind.LIVING_ACTIVITY_CHOICE,ModelTaskKind.LIVING_ACTIVITY_SHARE,ModelTaskKind.LIVING_ACTIVITY_REPLY)
        if tuple(digest(living_protocol_for_kind(k,technical_variant='action-contract')) for k in kinds)!=ACTION_PROTOCOL_HASHES:
            raise ValueError('independently pinned action protocol or slot changed')


def living_action_contract(binding):
    from dynamic_subject_agent.living_activity_live import APPROVED_LIVING_REVIEW,living_final_text_contract
    LivingActionContractDevelopmentGrant(APPROVED_LIVING_REVIEW,ACTION_DEVELOPMENT_AUTHORIZATION).validate()
    base=living_final_text_contract(binding)
    return dict(base,version=ACTION_VERSION,development_authorization=ACTION_DEVELOPMENT_AUTHORIZATION,
        technical_variant=dict(base['technical_variant'],choice_policy_sha=ACTION_POLICY_HASHES[0],
            purpose_protocol_sha=dict(zip(('choice','share','reply'),ACTION_PROTOCOL_HASHES,strict=True)),
            choice_output='explicit-action-plan-contract-s149-1'))
