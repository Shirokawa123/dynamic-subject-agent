"""Current writing language, without assigning state or widening history."""
import re


def collaborative_clause(clause: str) -> str:
    return re.sub(r'^(?:(?:我们|咱们)(?:一起|顺手|先|来|再)*|(?:一起|顺手))(?=给|为|写|编|创作)', '', clause)


def natural_sentence_index(message: str) -> int | None:
    from dynamic_subject_agent.recent_dialogue import expression_request_text
    indexes = []
    for sentence in re.split(r'[。！？!?；;\n]', expression_request_text(message)):
        if re.match(r'^\s*(?:如果|假如|要是|假设)', sentence):
            continue
        clauses = re.split(r'[，,]', sentence)
        for position, clause in enumerate(clauses):
            match = re.fullmatch(r'第([一二三123])句(.+)', clause.strip())
            if match is None:
                continue
            tail = match[2]
            direct = re.match(r'^(?:我)?(?:也)?(?:想|希望|请)?(?:保留|改(?:成|为|得|一下)|换(?:成|为|得|一下))', tail)
            wording = (re.fullmatch(r'(?:也)?(?:别|不要)(?:再)?提[^，,]{1,16}', tail)
                and position + 1 < len(clauses)
                and re.match(r'^\s*(?:请)?(?:改成|改为|换成|换得)', clauses[position + 1]))
            if direct or wording:
                indexes.append({'一': 1, '二': 2, '三': 3, '1': 1, '2': 2, '3': 3}[match[1]])
    return indexes[0] if len(indexes) == 1 else None


def authored_draft(message: str) -> str | None:
    drafts = []
    for match in re.finditer(r'“([^”]+)”|「([^」]+)」|"([^"]+)"', message):
        prefix = re.split(r'[。！？!?；;\n]', message[:match.start()])[-1].strip()
        if re.search(r'如果|假如|假设|要是|朋友|他说|她说|转述', prefix):
            continue
        if re.fullmatch(r'[^「」“”"]{0,40}我(?:先|自己|刚刚|刚|已经)*写(?:了|的)[一两三123]句[：:]?\s*', prefix):
            drafts.append(next(part for part in match.groups() if part))
    return drafts[0] if len(drafts) == 1 else None
