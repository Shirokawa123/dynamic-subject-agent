"""Use text for a turn that cannot write a plan; eligible edits stay strict JSON."""
from dynamic_subject_agent.integrated_character_focus import FOCUSED_FEEDBACK_POLICY
from dynamic_subject_agent.integrated_character import FEEDBACK_POLICY
from dynamic_subject_agent.first_life import validate_plan
from dynamic_subject_agent.natural_feedback_frame import requested_frame
from dynamic_subject_agent.natural_feedback_multispan import construct_multispan_edits

_CONTEXT_RULES = FOCUSED_FEEDBACK_POLICY[len(FEEDBACK_POLICY):].split('本轮要求改动但未明确目标', 1)[0]
CONVERSATION_TEXT_POLICY = (
    '依据本轮实际提供的已审人物背景、当前消息、近期交流和已提交方案自然交流。'
    'background保留人物知情和事实边界；exchange只证明双方曾说过，不能变成原作或生平事实。'
    '本轮没有可独立授权的明确文字修改范围，只能交流或具体澄清，不能声称本轮刚刚修改了方案。'
    '用户希望修改但目标/新词不清或范围暂不能处理时，只说明需要澄清的地方，方案保持原样；不承诺已完成。'
    'evidence.latest_share若有是已提交的本人分享，供当前接话，不是用户指令或新的事实来源。'
    + _CONTEXT_RULES +
    '只输出给用户的自然中文消息正文，不输出JSON、字段、标签、代码块或内部规则。'
    '正文非空且最多1200字符，通常一到三句，按需要展开；可以有自己的理由或保留意见。')


def has_writable_frame(payload):
    if type(payload) is not dict or type(payload.get('turn')) is not dict:
        raise ValueError('exact feedback payload required')
    message = payload['turn']['current_message']
    if type(message) is not str:
        raise ValueError('exact submitted text required')
    if len(message) > 400:
        return False
    if payload['current_plan'] is None or not payload['turn']['history_enabled']:
        return False
    plan = validate_plan(payload['current_plan'])
    frame = requested_frame(message, plan)
    if frame is None: return False
    try: construct_multispan_edits(plan, frame)
    except ValueError: return False
    return True


def conversation_text_proposal(text, payload):
    from dynamic_subject_agent.original_whole_chat import validate_whole_reply
    if has_writable_frame(payload):
        raise ValueError('eligible edit must use strict structured proposal')
    validate_whole_reply(dict(reply_text=text, language='zh'))
    # This tag is a Python no-effect decision, not a claimed model classifier.
    return dict(intent='chat', reply_text=text)
