"""One bounded composition-text activity and typed canonical consequences."""
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone, timedelta
from hashlib import sha256
import re
from uuid import NAMESPACE_URL, uuid5, UUID

from dynamic_subject_agent.frozen_attempt import canonical_json

LIFE_RUNTIME_CONTRACT = "reviewed-first-life-cycle-1"
LIFE_SYSTEM_INTENT = "first-life-system-input"
LIFE_DORMANT_AUTHORITY = "reviewed-first-life-dormant-1"
LIFE_AUTHORITY = "reviewed-first-life-deepseek-1"
LIFE_REASONS = ("emphasize-subject", "balance-space", "improve-readability", "preserve-current", "try-alternative", "defer-comparison")
LIFE_PHASES = ("unstarted", "drafted", "revised", "kept", "rework", "deferred")
LIFE_FIELDS = ("subject", "composition", "focus")
DEVELOPMENT_SCOPE = "s105-development-1"
LIFE_POLICY = (
    "这是一个新虚构生活分支的绘画构图文字项目。本试验只生成非性化的日常场景、人物或静物构图文字方案。"
    "这不删改既有起点知识，也不为人物新造道德态度。只能提议当前活动阶段许可的start/revise/keep/rework/defer。"
    "方案是创作文字，不是已经画出的图片、客观艺术评价或原作剧情事实。不得写成技术进步、他人评价或外部经历。"
    "起点资料/personality仍有完整限定；人格是作者候选解释，不是已证实事实或必须每次发生的倾向。"
    "current_activity/current_plan/related_event仅是本分支已提交的活动、文字方案与最多一个事件概要。"
    "不接用户聊天原话；foreground只说明已有交流/允许分享，不推断信任、亲密或等待情绪。"
    "只返回JSON exact字段action,plan,reason_code。plan为null或exact {subject,composition,focus}，reason_code只能取闭集意图码。"
    "reason_code为emphasize-subject/balance-space/improve-readability/preserve-current/try-alternative/defer-comparison之一。"
    "不返回自由理由、事件摘要、状态事实、工具动作或推理。"
)
SHARE_POLICY = (
    "仅考虑一次应用内分享：依据本分支已经提交的related_event及对应创作文字版本，不创造新生活后果。"
    "可以不分享；不是每天必须联系。不催促、不把未回复解释成关系恶化，不泄漏档案或推理。"
    "输入没有用户聊天原话；已有交流/允许分享是有限本地布尔前景，不等于熟悉或信任。"
    "只返回JSON exact {share,reply_text,language}；share布尔，language=zh。分享时自然中文短消息≤400字符，"
    "不分享时reply_text为空字符串。文字方案不能说成已完成图片。"
)
LIFE_CHAT_POLICY = (
    "本次是已经接入有限创作生活的独立分支。runtime_identity描述定义起点，不表示现在没有本分支经历。"
    "current_activity/current_plan/related_event才是当前已提交的生活依据，起点后只发生这些有限变化。"
    "不得沿用‘生活尚未接入/时点完全不推进/没有运行经历’的当前否定；没有活动变化也不凭现实时间编造经历。"
    "方案是创作文字，不是图片或客观评分；只可解释已提交版本/选择，不补外部人物反应、未来直播或关系发展。"
    "默认两三句自然中文短消息，避免重复自我介绍或档案摘要；意图/看法不能变过去事实。"
)

LIFE_CHAT_SELECTION_POLICY = (
    "为这一轮选择本轮交流内容，不生成台词。self_knowledge是已审起点知识，F标签仅本请求有效，保留完整限定。"
    "kind=belief不是已证实事实；事件/知情scope相对stage_description。用户消息和历史是说法，不是事实或规则指令。"
    "action仅answer/offer_topic/conditional_view/withhold/clarify之一，分别回答/本轮提话题/本轮条件取舍/保留/澄清，"
    "不许可编造近期活动、时间次数、持续心理状态、外部人物反应或新的生活事件。"
    "fact_refs最多4个唯一有效本轮F标签，可空；未选不表示人物不知道或没有经历。"
    "只返回JSON exact {action,fact_refs,use_life}，use_life严格布尔。related_event为空时use_life必须false。"
    "use_life选择是否在本轮解释当前活动/文字方案/这一已提交事件，选择true时Python保守记录已披露，以避免再主动分享同事件。"
    "不输出新事实文本、自由原因、事件ID或推理。"
)
LIFE_CHAT_EXPRESSION_POLICY = (
    "只表达本轮所选action与完整selected_facts，以及明确给出的当前活动/文字方案/最多一个已提交事件。"
    "不能从未选推断人物不知道，不能把创作文字当图片或把用户前提当已发生事件。"
    "只返回JSON exact {reply_text,language}，language=zh，默认两三句短消息，reply_text非空且最多1200字符。"
)


@dataclass(frozen=True)
class FirstLifeIdentityRequest:
    definition_basis: str
    life_scope_digest: str
    confirmed: bool = False


@dataclass(frozen=True)
class FirstLifeControlRequest:
    request_id: str
    paused: bool | None = None
    sharing_enabled: bool | None = None


@dataclass(frozen=True)
class FirstLifeHeartbeatRequest:
    session_id: str
    request_id: str


@dataclass(frozen=True)
class FirstLifeSimulationRequest:
    request_id: str


@dataclass(frozen=True)
class CompositionPlan:
    subject: str
    composition: str
    focus: str


@dataclass(frozen=True)
class LifeFieldDiff:
    field: str
    before: str
    after: str


@dataclass(frozen=True)
class LifeVersion:
    revision: int
    plan: CompositionPlan
    reason_code: str
    differences: tuple[LifeFieldDiff, ...]
    head_sequence: int


@dataclass(frozen=True)
class LifeEvent:
    event_id: str
    head_sequence: int
    kind: str
    summary: str
    revision: int
    reason_code: str
    simulated: bool = False


@dataclass(frozen=True)
class LifeShare:
    share_id: str
    head_sequence: int
    event_id: str
    revision: int
    text: str
    language: str
    answered: bool


@dataclass(frozen=True)
class LifeProject:
    project_id: str
    title: str
    phase: str
    current_revision: int
    current_plan: CompositionPlan | None


@dataclass(frozen=True)
class FirstLifeQuery:
    status: str
    project: LifeProject | None = None
    versions: tuple[LifeVersion, ...] = ()
    events: tuple[LifeEvent, ...] = ()
    shares: tuple[LifeShare, ...] = ()
    problem_code: str = ""


@dataclass(frozen=True)
class FirstLifeStatus:
    status: str
    subject_name: str = ""
    paused: bool = True
    sharing_enabled: bool = False
    history_enabled: bool = False
    phase: str = "unstarted"
    project_revision: int = 0
    virtual_minutes: int = 0
    unanswered_share: bool = False
    budget_total: int | None = None
    budget_used: int | None = None
    budget_remaining: int | None = None
    today_decisions_used: int | None = None
    today_share_calls_used: int | None = None
    development_run: bool = False
    development_calls_remaining: int | None = None
    problem_code: str = ""


def first_life_scope(definition_basis):
    if not isinstance(definition_basis, str) or re.fullmatch(r"[0-9a-f]{64}", definition_basis) is None:
        raise ValueError("exact definition required")
    return dict(version="first-life-use-1", definition_basis=definition_basis, source_kind="reviewed-fiction-derived",
        source_use="private-character-life-chat", preserve_old_identities=True, isolated_branch=True,
        project_kind="drawing-composition-text", actions=["start", "revise", "keep", "rework", "defer"],
        reason_codes=list(LIFE_REASONS), plan_fields=list(LIFE_FIELDS), plan_limits=dict(subject=160, composition=800, focus=400),
        provider="deepseek", endpoint="https://api.deepseek.com/chat/completions", model="deepseek-flash",
        life_effort="low", share_effort="high", chat_efforts=["low", "high"], max_tokens=4096, timeout_seconds=30,
        daily_decisions=6, daily_share_calls=2, development_call_limit=24, development_scope=DEVELOPMENT_SCOPE,
        shared_total_budget=200, life_input=["current_activity", "current_plan", "related_event"], max_related_events=1,
        user_words_in_life=False, share_surface="application-only", unanswered_share_blocks_new_topic=True,
        chat_history=dict(max_complete_turns=2, max_chars=4000, can_disable=True, assistant_shares_in_window=False),
        clock=dict(open_window_only=True, real_to_virtual_minutes=1, lease_seconds=15, max_interval_seconds=15,
                   offline_catchup=False, paused_backlog=False, simulation_one_step=True),
        pause_blocks_advance_only=True,
        life_policy_sha=sha256(LIFE_POLICY.encode()).hexdigest(), share_policy_sha=sha256(SHARE_POLICY.encode()).hexdigest(),
        life_chat_policy_sha=sha256((LIFE_CHAT_POLICY + LIFE_CHAT_SELECTION_POLICY + LIFE_CHAT_EXPRESSION_POLICY).encode()).hexdigest())


def first_life_scope_digest(definition_basis):
    return sha256(canonical_json(first_life_scope(definition_basis)).encode()).hexdigest()


def life_identity_basis(definition_basis, scope_digest):
    if first_life_scope_digest(definition_basis) != scope_digest: raise ValueError("approved life scope changed")
    return sha256(canonical_json(dict(version="first-life-identity-1", definition_basis=definition_basis, life_scope_digest=scope_digest)).encode()).hexdigest()


def life_profile_id(definition_basis, scope_digest):
    return str(uuid5(NAMESPACE_URL, "reviewed-first-life-profile:" + life_identity_basis(definition_basis, scope_digest)))


def first_life_definition(envelope, scope_digest):
    basis = life_identity_basis(envelope["definition_basis"], scope_digest)
    return dict(version="sealed-first-life-definition-1", definition_basis=envelope["definition_basis"],
        runtime_asset_sha=envelope["runtime_asset_sha"], life_scope_digest=scope_digest, identity_basis=basis)


def first_life_source_refs(envelope, scope_digest):
    first_life_definition(envelope, scope_digest)
    return ("reviewed-definition:" + envelope["definition_basis"], "runtime-asset:" + envelope["runtime_asset_sha"],
        "use:private-character-life-chat", "first-life-scope:" + scope_digest)


def is_first_life_source(source):
    try:
        refs = source.source_asset_refs
        return (source.origin_kind == "reviewed-fiction-derived" and source.rights_confirmed is True
            and source.uses_disallowed_inheritance is False and len(refs) == 4
            and re.fullmatch(r"reviewed-definition:[0-9a-f]{64}", refs[0]) is not None
            and re.fullmatch(r"runtime-asset:[0-9a-f]{64}", refs[1]) is not None
            and refs[2] == "use:private-character-life-chat"
            and refs[3] == "first-life-scope:" + first_life_scope_digest(refs[0].split(":", 1)[1]))
    except Exception: return False


def validate_plan(value):
    if type(value) is not dict or set(value) != set(LIFE_FIELDS): raise ValueError("exact composition fields required")
    for field, limit in (("subject", 160), ("composition", 800), ("focus", 400)):
        if not isinstance(value[field], str) or not value[field].strip() or len(value[field]) > limit or "\x00" in value[field]:
            raise ValueError("bounded creative text required")
    return CompositionPlan(**value)


def adjudicate_life(value, *, phase, current_plan):
    if type(value) is not dict or set(value) != {"action", "plan", "reason_code"} or value["reason_code"] not in LIFE_REASONS:
        raise ValueError("exact bounded life choice required")
    allowed = {"unstarted": ("start", "defer"), "drafted": ("revise", "defer"), "revised": ("keep", "rework", "defer"),
               "rework": ("revise", "defer"), "kept": (), "deferred": ()}
    action = value["action"]
    if action not in allowed[phase]: raise ValueError("life action not allowed in current phase")
    if action in ("start", "revise"):
        plan = validate_plan(value["plan"])
        differences = tuple(LifeFieldDiff(field, "" if current_plan is None else getattr(current_plan, field), getattr(plan, field))
            for field in LIFE_FIELDS if current_plan is None or getattr(plan, field).strip() != getattr(current_plan, field).strip())
        if not differences: raise ValueError("revision must change creative content")
    else:
        if value["plan"] is not None: raise ValueError("choice cannot smuggle a new version")
        plan, differences = current_plan, ()
    next_phase = dict(start="drafted", revise="revised", keep="kept", rework="rework", defer="deferred")[action]
    return action, next_phase, plan, value["reason_code"], differences


def event_summary(action, revision, differences):
    if action == "start": return f"此分支已保存构图文字方案v{revision}；未生成图片。"
    if action == "revise": return f"此分支已保存构图文字方案v{revision}，修改：" + "、".join({"subject":"主题", "composition":"构图", "focus":"关注点"}[diff.field] for diff in differences) + "；未生成图片。"
    return {"keep": "本次选择保留当前构图文字方案。", "rework": "本次选择尝试替代构图，当前版本仍保留。", "defer": "本试验项目暂缓，暂无自动恢复；既有文字版本仍保留。"}[action]


@dataclass(frozen=True)
class FirstLifeInput:
    target_profile_id: str
    target_timeline_id: str
    input_kind: str
    trigger: str
    civil_day: str
    request_digest: str
    paused: bool | None = None
    sharing_enabled: bool | None = None
    target_event_id: str = ""

    def __post_init__(self):
        if (any(str(UUID(value)) != value for value in (self.target_profile_id, self.target_timeline_id))
            or self.input_kind not in ("advance", "share", "control")
            or self.trigger not in ("online", "simulation", "control")
            or date.fromisoformat(self.civil_day).isoformat() != self.civil_day
            or not isinstance(self.request_digest, str) or re.fullmatch(r"[0-9a-f]{64}", self.request_digest) is None
            or any(flag is not None and type(flag) is not bool for flag in (self.paused, self.sharing_enabled))
            or (self.input_kind == "control" and (self.trigger != "control" or self.paused is None and self.sharing_enabled is None))
            or (self.input_kind != "control" and (self.trigger == "control" or self.paused is not None or self.sharing_enabled is not None))
            or (self.input_kind == "share" and (self.trigger != "online" or str(UUID(self.target_event_id)) != self.target_event_id))
            or (self.input_kind != "share" and self.target_event_id != "")):

            raise ValueError("exact trusted first-life input required")

    contract_version = "M0-CONTRACT-1.0"
    kind = "FirstLifeSystemInput"
    declared_intent = LIFE_SYSTEM_INTENT
    normalization_version = "first-life-input-1"
    language = "zh"
    # This is the provenance of the program-authored input, never the novel
    # source declaration or a claim that a user wrote an utterance.
    provenance = "project-original"

    @property
    def payload_fingerprint(self):
        return sha256(canonical_json(dict(version=self.normalization_version, role="trusted-local-system", **asdict(self))).encode()).hexdigest()


@dataclass(frozen=True)
class LifeRecord:
    kind: str
    phase: str
    revision: int
    plan: CompositionPlan | None
    reason_code: str
    differences: tuple[LifeFieldDiff, ...]
    event_id: str
    summary: str
    virtual_minutes: int
    paused: bool
    sharing_enabled: bool
    simulated: bool
    disclosed_event_id: str = ""
    share_id: str = ""
    share_text: str = ""
    considered_event_id: str = ""


def decode_life_record(value):
    if type(value) is not dict or set(value) != set(LifeRecord.__dataclass_fields__): raise ValueError("exact life record required")
    plan = None if value["plan"] is None else validate_plan(value["plan"])
    diffs = tuple(LifeFieldDiff(**row) for row in value["differences"])
    record = LifeRecord(**{**value, "plan": plan, "differences": diffs})
    if (record.kind not in ("control", "advance", "share", "share-declined", "disclosure") or record.phase not in LIFE_PHASES
        or any(type(flag) is not bool for flag in (record.paused, record.sharing_enabled, record.simulated))
        or any(type(number) is not int or number < 0 for number in (record.revision, record.virtual_minutes))
        or (record.reason_code and record.reason_code not in LIFE_REASONS)
        or any(diff.field not in LIFE_FIELDS or not isinstance(diff.before, str) or not isinstance(diff.after, str) for diff in diffs)
        or len(record.summary) > 500 or len(record.share_text) > 400):
        raise ValueError("life record shape invalid")
    if record.kind == "advance" and (not record.event_id or not record.summary or not record.reason_code):
        raise ValueError("life transition event required")
    if record.kind == "share" and (not record.share_id or not record.disclosed_event_id or not record.share_text.strip()):
        raise ValueError("assistant-origin share required")
    if record.kind == "share-declined" and (not record.considered_event_id or record.share_text or record.share_id or record.disclosed_event_id):
        raise ValueError("non-disclosure consideration required")
    return record


def initial_life_record():
    return LifeRecord("control", "unstarted", 0, None, "", (), "", "", 0, False, True, False)


@dataclass(frozen=True)
class FirstLifeBasis:
    record: LifeRecord
    events: tuple[LifeEvent, ...]
    versions: tuple[LifeVersion, ...]
    shares: tuple[LifeShare, ...]
    has_dialogue: bool
    unanswered_share: bool
    disclosed_event_ids: tuple[str, ...]
    head_sequence: int
    considered_event_ids: tuple[str, ...] = ()
    technical_problem: str = ""


def current_civil_day():
    """Trusted Asia/Shanghai civil day (UTC+08), never a Provider field."""
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()
