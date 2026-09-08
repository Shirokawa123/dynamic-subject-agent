"""Local limits for unsourced physical explanations and material advice."""
from __future__ import annotations

import re
from dynamic_subject_agent.runtime_identity_reply import explicit_creation_request


_INQUIRY = r'为什么|为何|原理|原因|判断|辨别|鉴别|看出来|是不是|是否|什么纸'


def _noncreative_sentences(message: str) -> tuple[str, ...]:
    unquoted = re.sub(r'“[^”]*”|「[^」]*」|"[^"]*"', '', message)
    sentences = re.split(r'[。！？!?；;\n]', unquoted)
    return tuple(sentence for sentence in sentences
        if not (explicit_creation_request(sentence) and not re.search(_INQUIRY, sentence)))


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
        subjective = re.search(r'(?:为什么|为何)(?:我|你|他|她|我们|你们|他们|这个角色|这位老板).{0,4}'
            r'(?:喜欢|舍不得|犹豫|在意|珍惜|想念|后悔)(?!的)', clause)
        causal = re.search(r'为什么|为何|什么原理|原因是什么', clause) and not subjective
        material = re.search(r'材质|材料|什么纸|热敏纸|纸质|纸种', clause) and re.search(_INQUIRY, clause)
        if causal or material:
            return '这个问题目前没有可靠资料可以核对，我不能给你一个确定的解释或判断。'
    return None
