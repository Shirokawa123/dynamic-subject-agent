"""Local limits for unsourced physical explanations and material advice."""
from __future__ import annotations

import re
from dynamic_subject_agent.runtime_identity_reply import explicit_creation_request


_INQUIRY = r'为什么|为何|原理|原因|判断|辨别|鉴别|看出来|是不是|是否|什么纸'


def _evaluation_text(message: str) -> str:
    # Quotes remain attached to their introducing clause. Creative permission
    # removes only its own scope, never constraints preceding that request.
    parts = re.findall(r'(?:“[^”]*”|「[^」]*」|"[^"]*"|[^，,。！？!?；;\n])+[，,。！？!?；;\n]?', message)
    kept = []
    narrative = False
    for part in parts:
        outside = re.sub(r'“[^”]*”|「[^」]*」|"[^"]*"', '', part).strip()
        independent = re.match(r'^(?:也|还|再|另外|同时|并|但是|但)(?:请)?(?:回答|说说|给|告诉|解释|建议|教|帮)', outside)
        if independent:
            narrative = False
        if explicit_creation_request(outside):
            # A colon-delimited story premise includes the character's own
            # questions; a separately requested answer ends that premise.
            narrative = bool(re.search(r'(?:故事|场景|对白)[^：:]*[：:]', outside)) and not bool(re.search(r'[。！？!?；;\n]$', part))
            continue
        if narrative:
            if re.search(r'[。！？!?；;\n]$', part):
                narrative = False
            continue
        if re.match(r'^(?:请)?(?:评价|分析|看看)', outside) and re.search(r'语气|措辞|语法|口吻|通顺|语序', outside):
            kept.append(outside)
        else:
            kept.append(part)
    return ''.join(kept)


def _noncreative_sentences(message: str) -> tuple[str, ...]:
    return tuple(re.split(r'[。！？!?；;\n]', _evaluation_text(message)))


def _noncreative_clauses(message: str) -> tuple[str, ...]:
    return tuple(clause.strip() for sentence in _noncreative_sentences(message)
        for clause in re.split(r'[，,：:]', sentence) if clause.strip())


def material_uncertainty_reply(message: str) -> str | None:
    # User constraints, not a material diagnosis or a newly imported fact.
    message = '。'.join(_noncreative_sentences(message))
    material = bool(re.search(r'材质|材料|什么纸|热敏纸|纸质|纸种', message))
    unknown = bool(re.search(r'不确定|不知道|不清楚|不能确定|能(?:不能|否)?(?:看出来|判断|辨别)|是不是', message))
    preserve = bool(re.search(r'怕[^。！？!?]*(?:坏|损|伤)|不想[^。！？!?]*(?:坏|损|伤)|避免[^。！？!?]*(?:坏|损|伤)', message))
    if material and unknown and preserve:
        return '我无法确认这件物品的材质。既然你希望保留原物，我不建议为鉴别而做划痕或加热试验；现有资料不足以支持具体处理方法。'
    return None


def unsourced_fact_reply(message: str) -> str | None:
    preservation = material_uncertainty_reply(message)
    if preservation is not None:
        return preservation
    for clause in _noncreative_clauses(message):
        if re.search(r'(?:你|我)(?:用|把|拿).*比喻|(?:这|这个|这种)比喻', clause):
            continue
        physical = re.search(r'地面|路面|纸张|热敏纸|物体|光线|水膜|物理|化学', clause)
        causal = physical and re.search(r'为什么|为何|原理|原因', clause)
        material = re.search(r'材质|材料|什么纸|热敏纸|纸质|纸种', clause) and re.search(_INQUIRY, clause)
        if causal or material:
            return '这个问题目前没有可靠资料可以核对，我不能给你一个确定的解释或判断。'
    return None
