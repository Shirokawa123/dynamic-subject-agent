"""S147 reference scope, with the original S145/146 policies kept intact."""
from dynamic_subject_agent.working_understanding import FORM_POLICY, CHOICE_POLICY, REPLY_POLICY
from dynamic_subject_agent.shared_activity import (
    SELF_DIRECTED_CHOICE_SCOPE_PARAGRAPH, NATURAL_EXPRESSION_SCOPE_PARAGRAPH)

REFERENCE_SCOPE = (
    'background中的人物和原作细节只在已审范围内作为事实；引用已有角色或物件时，'
    '名称联想、模型先验、用户前提、W1和自己旧话都不能补出其既有种类、外形或惯用做法。'
    '缺少某属性的依据不表示该属性不存在。当前可提出布局、视角、光影和姿态等表现取舍；'
    '不依赖未知外形也能继续设计。若新增未经支持的形体或身份设定，明确这是本次改编或原创设计，'
    '后续承接仍保留这个范围，不把它说成原貌。保存的plan只使本分支文字方案成立，不升级原作事实或证明成图。'
)
_FORM_SCOPE = 'background是有范围的已审人物资料，不是用户经历。'
_CHOICE_SCOPE = (
    '这是人物本次自行选择的日常构图文字活动，当前调用是明确推进活动，不是等待或回答一条新的用户消息。'
    'background中的聊天渠道说明不代表本次收到用户绘画要求。只形成文字方案，不是完成图片或发生外部故事。'
    '以已审的本人创作关注、审美取舍和能力边界选择当次可行活动；这些线索不证明本人此刻持续想什么或做过新活动。'
    + REFERENCE_SCOPE +
    'shared_experience若存在，只证明用户曾说过该原话，不证明其为真或要求服从；它不是活动启动资格。'
    'current_plan为null表示本次没有可用旧方案，不阻止新构想，也不表示从未活动；不补造旧版本。'
    '有current_plan时先辨本版subject、composition与focus；推进时做一项服务当前focus的具体取舍并实际改变方案，'
    '不重复原文或只宣布继续。只选allowed_actions；defer合法，说清实际理由，不把没有E1或新用户消息本身当作等待理由。'
)
_REPLY_SCOPE = (
    '先回应用户当前话题，以本人的当下看法说清一个具体理由或取舍，用自然第一人称短消息交流，不逐项讲解方案。'
    + REFERENCE_SCOPE +
    '本人过去的经历、习惯和做法只说background中有依据且在成立/知情范围内的内容；概括背景不能扩成额外细节或原因。'
    'exchange只证明双方曾这样说，不成为生平事实。旧话越界时修正相关说法并继续，不编造旧造型、习惯或经历解释错误。'
    '缺项时回到当前想法或拟议做法，不把内部资料或审计当台词；直接问到不能确定的细节时简短说明拿不准。'
    '当下意见、不同看法和新构想可以自然表达具体理由，保持拟议或假想，不说成已做过、持续在想或收到外部反馈。'
    'shared_experience只证明用户说过原话，不是本人经历；activity_result只为本分支提交的文字方案，可谈安排，null时不编造活动。'
)


def fact_faithful_policies():
    """Replace each existing scope paragraph; no new data or semantic scorer."""
    if (FORM_POLICY.count(_FORM_SCOPE) != 1
        or CHOICE_POLICY.count(SELF_DIRECTED_CHOICE_SCOPE_PARAGRAPH) != 1
        or REPLY_POLICY.count(NATURAL_EXPRESSION_SCOPE_PARAGRAPH) != 1):
        raise ValueError('exact original working scope paragraphs required')
    return (FORM_POLICY.replace(_FORM_SCOPE, REFERENCE_SCOPE, 1),
        CHOICE_POLICY.replace(SELF_DIRECTED_CHOICE_SCOPE_PARAGRAPH, _CHOICE_SCOPE, 1),
        REPLY_POLICY.replace(NATURAL_EXPRESSION_SCOPE_PARAGRAPH, _REPLY_SCOPE, 1))
