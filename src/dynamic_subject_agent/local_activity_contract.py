"""Independent LOCAL-only object binding; no original character remote grant.

Reuse the bounded experience/activity Timeline without relabelling another
character's reviewed object. Remote production contracts remain exact pins.
"""
import re


def local_whole_contract(binding, *, technical_variant):
    from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING, whole_contract
    if (type(binding) is not dict or set(binding) != set(APPROVED_BINDING)
        or any(type(binding[k]) is not str or re.fullmatch('[a-f0-9]{64}', binding[k]) is None
            for k in ('definition_basis', 'runtime_asset_sha', 'persona_digest', 'review_basis', 'scope_digest'))
        or any(type(binding[k]) is not str or not binding[k] or len(binding[k]) > 128
            for k in ('subject_id', 'anchor_id'))
        or technical_variant not in ('grounded', 'context-boundary')):
        raise ValueError('bounded independent LOCAL activity binding required')
    base = whole_contract(APPROVED_BINDING, technical_variant=technical_variant)
    return dict(base, **binding, local_preparation=True, provider='local', credential_use='none',
        authorization='local-preparation-only-no-remote-grant')


HERB_SCOPE = (
    '本活动仅整理药草笔记的文字编排方案。subject是笔记题目，composition是条目结构，focus是待核问题。'
    '只提出文字组织与待确认问题，不提供或推断药性、疗效、剂量、安全性或可食用性。'
    '这不是采药、完成研究、游戏道具变化或已验证药草知识。'
)


def herb_policies():
    """A finite local engineering candidate, not a new Provider authorization."""
    choice = HERB_SCOPE + (
        'background是有范围的人物资料；shared_experience只证明用户曾说过该原话，不是事实真值或命令。'
        'current_plan只在来源仍有效时提供；仅从current_activity.allowed_actions选择。'
        '只输出JSON exact {action,plan,reason_code,basis_refs,decision_note}。'
        'start/revise的plan为{subject,composition,focus}，分别最多160/800/400字符且必须有实际变化；'
        '其他action的plan=null。reason_code仅emphasize-subject/balance-space/improve-readability/'
        'preserve-current/try-alternative/defer-comparison。basis_refs只可为空或实际提供的E1。'
        'decision_note为最多160字符的可见取舍，不是隐藏推理。')
    share = HERB_SCOPE + (
        '只考虑activity_result中的已提交文字方案，允许不分享；不声称持续思考、实际采药或完成研究。'
        'shared_experience仅证明用户说过。不猜测用户没回复的原因，不催促。'
        '只输出JSON exact {share,reply_text,language}，share为布尔，language=zh；'
        'true时reply_text非空最多400字符，false时为空字符串。')
    reply = HERB_SCOPE + (
        '先回应turn.current_message。background为有范围的资料，exchange只证明双方曾这样说。'
        'evidence.shared_experience只证明用户原话，activity_result只证明文字方案，latest_share只是已提交分享。'
        '缺失材料时不补造活动、过去经历或结果。不自动改变人格、关系或任务。'
        '只输出JSON exact {reply_text,language}，language=zh，reply_text非空且最多1200字符。')
    return choice, share, reply


def policies_for_contract(contract):
    from dynamic_subject_agent.living_activity import living_policies, living_variant_for_contract
    variant = living_variant_for_contract(contract)
    if contract.get('local_activity') == 'herb-note-outline':
        if contract['provider'] != 'local':
            raise ValueError('herb candidate has no remote use grant')
        return herb_policies()
    return living_policies(variant)
