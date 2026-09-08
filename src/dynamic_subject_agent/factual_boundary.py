"""Local limits for unsourced physical explanations and material advice."""
from __future__ import annotations

import re
from dynamic_subject_agent.runtime_identity_reply import explicit_creation_request


_INQUIRY = r'为什么|为何|原理|原因|判断|辨别|鉴别|看出来|是不是|是否|什么纸'


def _evaluation_text(message: str) -> str:
    outside_quotes = re.sub(r'“[^”]*”|「[^」]*」|"[^"]*"', '', message)
    parts = re.split(r'[，,。！？!?；;：:\n]', outside_quotes)
    real_requests = any(not explicit_creation_request(part) and (
        re.match(r'^(?:也|还|再|另外|同时|并)?(?:请)?(?:给我|告诉我|教我|帮我|回答|解释|建议)', part.strip())
        and re.search(r'保存|处理|鉴别|判断|测试|办法|方法|步骤|建议|问题|原理|原因|为什么', part))
        for part in parts)
    real_requests = real_requests or any(
        re.match(r'^(?:为什么|为何|怎么|如何|(?:你|我)?能|可以|地面|路面|纸张|热敏纸|材质|材料)', part.strip())
        and re.search(r'地面|路面|纸张|热敏纸|材质|材料|物理|化学|光线|水膜', part)
        and re.search(_INQUIRY, part) for part in parts if not explicit_creation_request(part))
    # Only a complete creative purpose is exempt; an additional real-world
    # request cannot borrow that permission. Narrative questions stay fiction.
    if explicit_creation_request(outside_quotes) and not real_requests:
        return ''
    if re.search(r'语气|措辞|语法|口吻|通顺|语序', outside_quotes) and not real_requests:
        return outside_quotes
    # A quoted question can be the actual question. Quotes alone do not exempt
    # its material constraints from the reply policy.
    return message


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
        physical = re.search(r'地面|路面|纸张|热敏纸|物体|光线|水膜|物理|化学', clause)
        causal = physical and re.search(r'为什么|为何|原理|原因', clause)
        material = re.search(r'材质|材料|什么纸|热敏纸|纸质|纸种', clause) and re.search(_INQUIRY, clause)
        if causal or material:
            return '这个问题目前没有可靠资料可以核对，我不能给你一个确定的解释或判断。'
    return None
