"""Finite unchanged context, never permission to create or revise a plan."""
import re


def is_unchanged_arrangement(text: str) -> bool:
    text = text.strip()
    if re.fullmatch(
        r'(?:(?:原有|原来|其他|其它|别的)(?:的)?|'
        r'(?:我|我们|朋友|同事|家人)(?:来|一起)?(?:吃(?:早餐|午餐|晚餐)|聚餐|见面|出游)的)?'
        r'(?:安排|计划)(?:保持)?不变', text):
        return True
    carry = re.fullmatch(r'([\u4e00-\u9fffA-Za-z0-9]{1,24})照带', text)
    if carry is None:
        return False
    # The literal subject is not an object lookup or a new arrangement. Keep
    # explicit conditions, negation and additional operations out of this form.
    return not any(marker in carry[1] for marker in (
        '如果', '假如', '假设', '要是', '除非', '只有', '只要', '否则', '前提',
        '但', '不过', '不', '别', '勿', '取消', '改', '换', '新增', '删除',
        '目标', '承诺', '然后', '同时', '并且', '以及', '把',
    ))
