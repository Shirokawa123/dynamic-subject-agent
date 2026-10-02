"""Finite read-only life questions within the existing dialogue permission boundary."""
import re
import unicodedata

from dynamic_subject_agent.recent_dialogue import is_dialogue_control


def _requires_control(text):
    # First-life chat has no participant-goal domain. Topic nouns and temporal
    # references are not control acts; explicit operations remain conservative.
    if is_dialogue_control(text, legacy_topic_markers=False):
        return True
    # A usage restriction is independent of whether its object comes before or
    # after the verb. The modal 不用 (e.g. 不用担心) needs an object/use ending.
    source = r'(?:聊天|对话|历史|原话|句话|记录|资料|内容|方案|构图|版本|目标|承诺|这(?:个|些|件事)|那(?:个|些|件事)|它)'
    if (re.search(r'(?:不要|不再|不能|不许|不准|禁止|停止|别|勿)[^。！？!?]*用', text)
        or re.search(r'不用(?:再|继续)?(?:此前|之前|刚才|上面|先前|任何|' + source + r')', text)
        or re.search(source + r'[^。！？!?，,]*不用(?:了|啦|吧)?(?:$|[。！？!?，,])', text)):
        return True
    operation = r'(?:设立|设置|创建|新增|更新|修改|变更|取消|撤销|撤回|放弃|完成)'
    # Whole explicit command clauses only. Discussing how goals are completed
    # or why promises are hard to keep is ordinary conversation.
    ending = r'(?:(?:为|成|到|：|:)[^。！？!?，,]{1,200})?(?:吧|一下|好吗|可以吗)?'
    direct = r'(?:请(?:你)?|帮我|替我|给我|麻烦(?:你)?)?' + operation + r'[^。！？!?，,]{0,40}(?:目标|承诺)' + ending
    referred = r'(?:请(?:你)?|帮我|替我|给我|麻烦(?:你)?)?(?:把|将)[^。！？!?，,]{0,40}(?:目标|承诺)' + operation + ending
    return any(re.fullmatch(pattern, clause) for clause in re.split(r'[。！？!?，,]', text) for pattern in (direct, referred))


def is_first_life_dialogue_control(message):
    text = re.sub(r'\s+', '', unicodedata.normalize('NFKC', message))
    referenced = re.sub(r'保存的(?:方案|构图|版本)', '该创作内容', text)
    if referenced == text:
        return _requires_control(text)
    source = r'(?:该创作内容|聊天|对话|历史|原话|记录|资料|它|这(?:个|些|件事)|那(?:个|些|件事))'
    # Only a complete question can use this narrow nominal-reference exception.
    # Negative usage instructions have priority, including the shorter Chinese 用.
    # These finite editing/effect exclusions apply only to a candidate exception;
    # they do not introduce a general Chinese command classifier.
    if (not text.endswith(('?', '？'))
        # Negating plan content is not a withdrawal. Any negative form with a
        # source action stays conservative; it need not be an imperative.
        or re.search(r'拒绝|取消|停|撤回|放弃|禁止|反对', text)
        or re.search(
        r'[不勿别没无莫][^。！？!?]*(?:用|记|提|说|保留|存|分享|发送|删|清除|移除)', referenced)
        # Use can precede refusal (再用下去我不同意). Descriptive 说/提 do
        # not enter this reverse check: 说右边没留东西 is the reported claim.
        or re.search(
        r'(?:用|记|保留|存|分享|发送|删|清除|移除)[^。！？!?]*[不勿别没无莫]', referenced)
        # Disclosure/留 before refusal needs a source before that refusal too.
        # In the reported claim 说…没留东西, the plan reference follows 没.
        or re.search(
        r'(?:(?:说|提|留)[^。！？!?]*' + source + r'|' + source +
        r'[^。！？!?]*(?:说|提|留))[^。！？!?]*[不勿别没无莫]', referenced)
        # Bare 留 also describes layout (没留东西). Keep it a source action
        # when its same clause names the source or refers back to it.
        or any(re.search(r'[不勿别没无莫][^。！？!?，,]*留', clause)
            and re.search(source, clause)
            for clause in re.split(r'[。！？!?，,]', referenced))
        or re.search(r'改|加|换|调整|移动|重做|存|生成|导出|复制|执行', referenced)
        or re.search(
        r'(?:不要|不再|不用|不能|不许|不准|禁止|停止|别|勿|请|帮我|替我|给我|麻烦|把|将)'
        r'[^。！？!?]*(?:用|记|提|说|留|存|分享|发送|删|清除|移除)', text)):
        return _requires_control(text)
    # All remaining control vocabulary still applies, including mixed questions
    # containing an actual save/delete/withdrawal instruction elsewhere.
    return _requires_control(referenced)
