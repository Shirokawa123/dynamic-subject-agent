"""Same-use S158 behavior candidate; baseline policies remain immutable."""
from dynamic_subject_agent.integrated_character import FEEDBACK_POLICY
from dynamic_subject_agent.natural_feedback import feedback_choice_policy
from dynamic_subject_agent.living_activity import living_policies

FOCUSED_FEEDBACK_POLICY = FEEDBACK_POLICY + (
    '本轮唯一的新请求是turn.current_message；current_feedback是此前已经接纳并执行过的修订依据，不是待办或本轮重发的指令。'
    'current_plan是现在这一版，不能据它声称初稿或所有旧版从来如此；没有旧版全文时不编造完整变更历史。'
    '回顾修改时，可依据F1说明此前那次明确改动，随后回答当前问题；不要因旧词已被替换而要求用户再次确认已经完成的修改。'
    '无关新话题优先按当前问题回应，不把可用的活动背景强行带进所有回答。'
    '本轮要求改动但未明确目标、需要询问哪个词或换成什么时，intent必须为clarify；普通意见和回顾才用chat。')
FOCUSED_CHOICE_POLICY = feedback_choice_policy() + (
    'F1记录的那次修订已经完成，当前方案就是其后可用的版本；本次不是再执行F1。'
    '若选revise，应做一项本次新的具体构图取舍，例如人物动作、视线关系、空间位置、光影或留白，说明本人为什么现在这样选。'
    '不要把已完成改名、同义词替换、句式润色或重复当前安排当成新的活动推进。'
    '没有实质新取舍时，从allowed_actions中选择合法的保留或暂缓，不能编造进展。')
FOCUSED_SHARE_POLICY = living_policies('action-contract')[1] + (
    '这是你主动开启的一条消息，不是在回答一个新问题。只挑当前方案里一个最在意的安排，用一到两个自然短句说出来。'
    '不要逐项交代整个视点、主体、左右位置、背景和焦点；不重新介绍整幅方案，也不例行询问先从哪里开始。'
    '只知当前已提交结果，不假造与旧版的具体对比；文字构想仍是构想，不说成已成图或离线做过。')


def focused_policies():
    return FOCUSED_FEEDBACK_POLICY, FOCUSED_CHOICE_POLICY, FOCUSED_SHARE_POLICY
