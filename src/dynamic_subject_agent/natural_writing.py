"""Current writing language, without assigning state or widening history."""
import re


def collaborative_clause(clause: str) -> str:
    # A discourse lead-in does not change the following direct writing act.
    clause = re.sub(r'^那就(?=请|帮我|替我|给|为|写|编|创作)', '', clause)
    return re.sub(r'^(?:(?:我们|咱们)(?:一起|顺手|先|来|再)*|(?:一起|顺手))(?=给|为|写|编|创作)', '', clause)


def natural_sentence_index(message: str, *, style_only: bool = False) -> int | None:
    from dynamic_subject_agent.recent_dialogue import expression_request_text
    from dynamic_subject_agent.current_message import mask_quoted_text
    indexes = []
    request_text = expression_request_text(mask_quoted_text(message))
    for sentence in re.split(r'[。！？!?；;\n]', request_text):
        if re.match(r'^\s*(?:如果|假如|要是|假设)', sentence):
            continue
        clauses = re.split(r'[，,]', sentence)
        for position, clause in enumerate(clauses):
            match = re.fullmatch(r'第([一二三123])句(.+)', clause.strip())
            if match is None:
                continue
            tail = match[2]
            direct = re.match(r'^(?:我)?(?:也)?(?:想|希望|请)?(?:再)?(?:保留|改(?:成|为|得|一下)|换(?:成|为|得|一下))', tail)
            # A numbered current wish can request a style change without 改.
            # Do not lift it out of a preceding reported/conditional clause.
            style = re.fullmatch(
                r'(?:我)?(?:也)?(?:想|希望|请)(?:再)?更[^。！？!?；;：:，,]{1,20}(?:一点|一些|些|点)', tail)
            if style and position != 0:
                return None
            wording = (re.fullmatch(r'(?:也)?(?:别|不要)(?:再)?提[^，,]{1,16}', tail)
                and position + 1 < len(clauses)
                and re.match(r'^\s*(?:请)?(?:改成|改为|换成|换得)', clauses[position + 1]))
            if direct or wording or style:
                indexes.append(({'一': 1, '二': 2, '三': 3, '1': 1, '2': 2, '3': 3}[match[1]], bool(style)))
    if any(style for _, style in indexes) and len(re.findall(r'第[一二三四五六七八九十0-9]+句', request_text)) != 1:
        return None
    return indexes[0][0] if len(indexes) == 1 and (not style_only or indexes[0][1]) else None


def authored_drafts(message: str) -> tuple[str | None, ...]:
    drafts = []
    previous_end = 0
    for match in re.finditer(r'“([^”]+)”|「([^」]+)」|"([^"]+)"', message):
        prefix = re.split(r'[。！？!?；;\n]', message[previous_end:match.start()])[-1].strip()
        previous_end = match.end()
        if re.search(r'如果|假如|假设|要是|朋友|他说|她说|转述', prefix):
            continue
        if re.fullmatch(r'[^「」“”"]{0,40}我(?:先|自己|刚刚|刚|已经)*写(?:了|的)[一两三123]句[：:]?\s*', prefix):
            body = next(part for part in match.groups() if part)
            drafts.append(None if any(char in body for char in '「」“”"') else body)
    return tuple(drafts)


def sentence_edit_forbidden_terms(message: str, index: int) -> tuple[str, ...] | None:
    """Literal current constraints; None means a malformed quoted constraint."""
    from dynamic_subject_agent.current_message import mask_quoted_text
    masked = mask_quoted_text(message)
    numeral = {1: '一1', 2: '二2', 3: '三3'}[index]
    pairs = {'“': '”', '「': '」', '‘': '’', '"': '"'}
    terms = []
    for unit in re.finditer(r'[^。！？!?；;\n]+[。！？!?；;\n]?', masked):
        visible = unit[0].strip()
        raw = message[unit.start():unit.end()].strip().rstrip('。！？!?；;')
        if re.match(r'^第[' + numeral + r']句', visible):
            clauses = re.split(r'[，,]', raw)[1:]
        elif re.match(r'^(?:也)?(?:别|不要)(?:再)?用', visible):
            clauses = re.split(r'[，,]', raw)
        else:
            continue
        for clause in clauses:
            match = re.fullmatch(r'(?:也)?(?:别|不要)(?:再)?用([“「‘"])([^“”「」‘’"。！？!?；;，,\n]{1,24})([”」’"])(?:这个词)?', clause.strip())
            if match and pairs[match[1]] == match[3] and match[2].strip():
                terms.append(match[2])
            elif (re.match(r'^(?:也)?(?:别|不要)(?:再)?用', clause.strip())
                and any(char in clause for char in '“”「」‘’"')):
                return None
            else:
                # Unknown intervening clauses may establish report/condition
                # scope. Do not promote a later fragment into an instruction.
                break
    return tuple(dict.fromkeys(terms))
