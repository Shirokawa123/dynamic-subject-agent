"""The current sealed character basis, distinct from model utterances and IDs."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CharacterBasisKnowledge:
    dimension: str
    statement: str
    kind: str
    basis: str
    event_scope: str
    knowledge_scope: str


@dataclass(frozen=True)
class CharacterBasisUnit:
    title: str
    content: str
    support: tuple[CharacterBasisKnowledge, ...]


@dataclass(frozen=True)
class CharacterBasisInterpretation:
    title: str
    interpretation: str
    when: str
    choice: str
    expression: str
    limits: str
    basis: str
    support_includes_belief: bool


@dataclass(frozen=True)
class CharacterBasisView:
    status: str
    problem_code: str = ""
    subject_name: str = ""
    subject_identity: str = ""
    canon_start: str = ""
    stage_description: str = ""
    knowledge: tuple[CharacterBasisKnowledge, ...] = ()
    core: tuple[CharacterBasisUnit, ...] = ()
    episodes: tuple[CharacterBasisUnit, ...] = ()
    details: tuple[CharacterBasisUnit, ...] = ()
    personality: tuple[CharacterBasisInterpretation, ...] = ()
    source_note: str = ""
    trace_note: str = ""
    limitations: tuple[str, ...] = ()


def build_character_basis(envelope, contract):
    from dynamic_subject_agent.original_whole_chat import validate_whole_envelope
    validate_whole_envelope(envelope, contract)
    asset = envelope['runtime_asset']
    knowledge = tuple(CharacterBasisKnowledge(row['dimension'], row['statement'], row['kind'], row['derivation'],
        row['event_time'], row['knowledge_time']) for row in asset['eligible'])
    by_id = {row['item_id']: item for row, item in zip(asset['eligible'], knowledge, strict=True)}
    groups = {key: () for key in ('core', 'episodes', 'details')}
    if asset['chat_organization'] is not None:
        groups = {group: tuple(CharacterBasisUnit(row['title'], row['content'], tuple(by_id[key] for key in row['claim_ids']))
            for row in asset['chat_organization'][group]) for group in groups}
    return CharacterBasisView('available', subject_name=asset['subject']['name'],
        subject_identity=envelope['genesis_content']['subject_identity'], canon_start=envelope['genesis_content']['canon_start'],
        stage_description=asset['initial_stage'], knowledge=knowledge, **groups,
        personality=tuple(CharacterBasisInterpretation(**row) for row in asset['personality']),
        source_note='这里展示当前封存的已审认识与作者解释；模型聊天回复不是新增的人物依据，也不表示每轮都采用了全部资料。',
        trace_note='当前封存资产未保留原小说逐段定位；这里不能提供页码或原文出处，逐段追溯尚未接入。',
        limitations=('已审事实和人物信念分别呈现，两者不相互替代。',
            '事件成立与本人知情的起点前、起点时范围分别保留。',
            '性格部分是有边界的作者解释，不是原作事实或已经发生的持续情绪。',
            '封存资料不覆盖完整人生；未列出或未在本轮选中，不等于不存在或本人不知道。'))
