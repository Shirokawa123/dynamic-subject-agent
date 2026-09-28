"""Finite read-only life questions within the existing dialogue permission boundary."""
import re
import unicodedata

from dynamic_subject_agent.recent_dialogue import is_dialogue_control


def is_first_life_dialogue_control(message):
    text = re.sub(r'\s+', '', unicodedata.normalize('NFKC', message))
    referenced = re.sub(r'保存的(?:方案|构图|版本)', '该创作内容', text)
    if referenced == text:
        return is_dialogue_control(message)
    # Only a complete question can use this narrow nominal-reference exception.
    # Negative usage instructions have priority, including the shorter Chinese 用.
    # These finite editing/effect exclusions apply only to a candidate exception;
    # they do not introduce a general Chinese command classifier.
    if (not text.endswith(('?', '？'))
        # A negative or stopping expression is not eligible for this exception,
        # even when phrased as willingness rather than an imperative.
        or re.search(r'[不勿别没无莫]|拒绝|取消|停|撤回|放弃|禁止|反对', text)
        or re.search(r'改|加|换|调整|移动|重做|存|生成|导出|复制|执行', referenced)
        or re.search(
        r'(?:不要|不再|不用|不能|不许|不准|禁止|停止|别|勿|请|帮我|替我|给我|麻烦|把|将)'
        r'[^。！？!?]*(?:用|记|提|说|留|存|分享|发送|删|清除|移除)', text)):
        return is_dialogue_control(text)
    # All remaining control vocabulary still applies, including mixed questions
    # containing an actual save/delete/withdrawal instruction elsewhere.
    return is_dialogue_control(referenced)
