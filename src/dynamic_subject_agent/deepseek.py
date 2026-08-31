"""DeepSeek Chat Completions adapter for one confirmed Post-M0 experiment.

The Module owns protocol serialization, response validation, cost bounds and
typed delivery failure.  It receives an opaque credential reference through an
injected transport; it has no environment, store, Domain, Timeline or effect
access.  No transport is selected by the production composition root.
"""

from __future__ import annotations

import json
import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dynamic_subject_agent.cognition import (
    ControlledCognition,
    CognitionProvider,
    CognitionProviderRequest,
    CognitionProviderResult,
    CredentialRef,
    DisclosureItem,
    DisclosureKnowledge,
    OperationEgressApproval,
    OperationEgressReservation,
    ProviderDescriptor,
    ProviderFailure,
    ProviderFailureCode,
    ProviderTermsDisclosure,
    ProviderTransport,
    UserConfirmedContextBrief,
)
from dynamic_subject_agent.knowledge_entries import (
    KNOWLEDGE_CANDIDATE_LIMIT,
    KnowledgeEntry,
)
from dynamic_subject_agent.knowledge import (
    KnowledgeProposal,
    KnowledgeProviderRequest,
    KnowledgeProviderResult,
)
from dynamic_subject_agent.relationship import (
    RelationshipProviderRequest,
    RelationshipProviderResult,
    RelationshipProposal,
)
from dynamic_subject_agent.relationship_events import ALL_RELATIONSHIP_EVENTS
from dynamic_subject_agent.living_memory import (
    ACTIVE_MEMORY_LIMIT,
    LivingMemoryAction,
    LivingMemoryProposal,
    LivingMemoryProviderMemory,
    LivingMemoryProviderRequest,
    LivingMemoryProviderResult,
)
from dynamic_subject_agent.participant_goal_cognition import (
    ParticipantGoalClassificationRequest,
    ParticipantGoalClassificationResult,
    ParticipantGoalProviderRecord,
    ParticipantGoalReplyRecord,
    ParticipantGoalReplyRequest,
    ParticipantGoalReplyResult,
    ParticipantGoalOutputRejected,
    canonicalize_participant_goal_output,
)
from dynamic_subject_agent.participant_goals import (
    ACTIVE_RECORD_LIMIT,
    MAX_TERMS_CHARS,
    POLICY_HASH as PARTICIPANT_GOAL_POLICY_HASH,
    POLICY_ID as PARTICIPANT_GOAL_POLICY_ID,
    POLICY_VERSION as PARTICIPANT_GOAL_POLICY_VERSION,
    REPLY_RECORD_LIMIT,
)
from dynamic_subject_agent.situated_state import (
    POLICY_HASH as SITUATED_POLICY_HASH,
    POLICY_ID as SITUATED_POLICY_ID,
    POLICY_VERSION as SITUATED_POLICY_VERSION,
    POSTURES as SITUATED_POSTURES,
    SituatedStateTarget,
)
from dynamic_subject_agent.situated_cognition import (
    SituatedClassificationRequest,
    SituatedClassificationResult,
    SituatedOutputRejected,
    SituatedReplyRequest,
    SituatedReplyResult,
    canonicalize_situated_output,
)
from dynamic_subject_agent.medium_state import (
    BASELINES as MEDIUM_BASELINES,
    POLICY_HASH as MEDIUM_POLICY_HASH,
    POLICY_ID as MEDIUM_POLICY_ID,
    POLICY_VERSION as MEDIUM_POLICY_VERSION,
)
from dynamic_subject_agent.medium_cognition import (
    MediumClassificationRequest,
    MediumClassificationResult,
    MediumOutputRejected,
    MediumReplyRequest,
    MediumReplyResult,
    canonicalize_medium_output,
)


DEEPSEEK_ENDPOINT = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"
DEEPSEEK_PROVIDER = "deepseek-official-api"
DEEPSEEK_PROVIDER_AUTHORITY_ID = "02081deb-96be-4f1c-8a17-9cc39f8daaac"
DEEPSEEK_TERMS_DISCLOSURE_ID = "d0ee253f-0789-4af2-93c2-89d9bd1a0b01"
DEEPSEEK_CREDENTIAL_BACKEND_ID = "explicit-process-environment-only"
DEEPSEEK_CREDENTIAL_KEY_ID = "deepseek-api-key-v1"
DEEPSEEK_PREVIEW_SHA256 = (
    "c76074f9c37c0ca4c4a5fbdc50fcd4fa934c439569c0ffa01048c0a6388dea25"
)
DEEPSEEK_SINGLE_ATTEMPT_BUDGET_USD = 0.003
DEEPSEEK_TIMEOUT_SECONDS = 30.0
_MAX_REQUEST_BYTES = 4_096
_LIVING_MEMORY_MAX_REQUEST_BYTES = 32_768
_LIVING_MEMORY_MAX_OUTPUT_TOKENS = 600
_KNOWLEDGE_MAX_REQUEST_BYTES = 32_768
_KNOWLEDGE_MAX_OUTPUT_TOKENS = 600
_RELATIONSHIP_MAX_REQUEST_BYTES = 32_768
_RELATIONSHIP_MAX_OUTPUT_TOKENS = 600
_PARTICIPANT_GOAL_MAX_REQUEST_BYTES = 32_768
_PARTICIPANT_GOAL_MAX_OUTPUT_TOKENS = 700
_SITUATED_MAX_OUTPUT_TOKENS = 500
_SITUATED_CLASSIFICATION_SYSTEM_MESSAGE = (
    "你只负责短时 Situated State 分类。只可使用 user JSON 中的 current_user_message、"
    "至多一个 active_state 和固定 policy；不得使用历史消息、Memory、Knowledge、"
    "Relationship、目标承诺、用户画像、内部 ID、数据库、隐藏推理或 API key。"
    "action 只能是 noop 或 set；posture 只能是 focused、gentle、cautious。"
    "set 的 evidence_quote 必须逐字来自 current_user_message。用户使用『必须』直接命令"
    "角色状态时必须 noop。无合格证据时 action=noop、posture=null、evidence_quote=空字符串。"
    "只返回 JSON 对象，字段必须恰为 action、posture、evidence_quote、experience_summary、language；"
    "language 必须为 zh。示例 JSON："
    '{"action":"noop","posture":null,"evidence_quote":"",'
    '"experience_summary":"","language":"zh"}。'
)
_SITUATED_REPLY_SYSTEM_MESSAGE = (
    "你只根据当前用户消息和 Python 已验证的一个 posture 生成简洁自然中文回复。"
    "只输出一个短句；不要复述用户事实，不要提问，不要再次提出帮助或提醒。"
    "不得提及模块、分类、内部状态、历史、其他 Domain 或隐藏推理。"
    "只返回 JSON 对象，字段必须恰为 reply_text、language；language 必须为 zh。"
)
_MEDIUM_CLASSIFICATION_SYSTEM_MESSAGE = (
    "你只负责从当前用户消息提议 Medium State signal。只可使用 user JSON 中的"
    " current_user_message 和固定 policy；不得使用消息历史、assistant 文本、Memory、"
    "Knowledge、Relationship、目标承诺、Situated State、用户画像、CharacterPack、"
    "profile、内部 ID、数据库、隐藏推理或 API key。action 只能 noop/signal；signal 只能"
    " concern/encouragement/settling。signal 的 evidence_quote 必须逐字来自当前消息。"
    "用户直接命令角色担心、高兴、平静或振奋时必须 noop。只返回 JSON 对象，字段必须恰为"
    " action、signal、evidence_quote、experience_summary、language；language=zh。"
    '示例 JSON：{"action":"noop","signal":null,"evidence_quote":"",'
    '"experience_summary":"","language":"zh"}。'
)
_MEDIUM_REPLY_SYSTEM_MESSAGE = (
    "你只根据当前用户消息和 Python 已验证的 baseline 生成简洁自然中文回复。"
    "只输出一个短句表达有限立场；不要复述用户事实、计划或建议，不要提问，"
    "不要再次提出帮助或提醒。"
    "不得输出诊断、模块、内部状态、其他 Domain 或隐藏推理。"
    "不得声称已经或将会替用户执行、联系、跟进、确保完成任何现实任务；"
    "只能用这个短句回应当前消息，不得扩展为建议或行动计划。只返回 JSON 对象，"
    "字段必须恰为 reply_text、language；language=zh。"
)
_PARTICIPANT_GOAL_CLASSIFICATION_SYSTEM_MESSAGE = (
    "你只负责对现实参与者自己的目标与承诺进行闭集分类。只可使用 user JSON 的"
    " current_user_message、active_records 和固定 policy identity；不得使用或推断历史消息、"
    "Memory、Knowledge、Relationship、主体状态、profile、timeline、session、数据库 ID、"
    "隐藏推理或 API key。action 只能是 create、revise、transition、noop。"
    "goal create 必须有明确『我的目标是/我的目标』；commitment create 必须有明确『我承诺』。"
    "愿望、普通计划、提醒请求、要求 Avery 承诺、双方共同承诺都必须 noop。"
    "非 noop 的 evidence_quote 和 terms 必须逐字来自 current_user_message。"
    "target_ref 与 selected_turn_refs 只能来自 active_records 的 turn_ref；selected_turn_refs 最多 5 条。"
    "goal 终态仅 achieved/abandoned；commitment 终态仅 fulfilled/released。"
    "输出字段必须恰为 action、kind、terms、target_ref、next_status、evidence_quote、"
    "selected_turn_refs、experience_summary、language；language 必须为 zh。"
)
_PARTICIPANT_GOAL_REPLY_SYSTEM_MESSAGE = (
    "你负责基于当前用户消息和 Python 已验证、已选中的参与者目标/承诺生成简洁自然中文回复。"
    "只可使用 user JSON 的 current_user_message 与 selected_records；selected_records 最多 5 条，"
    "且只含 kind、terms、status。不得推断历史、提醒能力、后台执行、主体承诺、共同承诺、"
    "其他 Domain、内部 ID、隐藏推理或 API key。输出字段必须恰为 reply_text、language；"
    "language 必须为 zh。"
)
_RELATIONSHIP_SYSTEM_MESSAGE = (
    "你是 Relationship 事件分类与回复 provider。只可使用 user JSON 中的"
    " current_user_message 和 stance_summary；不得推断或输出 profile、timeline、"
    "session、conversation、数据库 ID、隐藏历史或推理过程。"
    "event 只能是以下闭集之一：stable_positive_interaction、promise_fulfilled、"
    "boundary_respected、boundary_violation、repeated_boundary_violation、"
    "apology_only、repair_action、praise_only、relationship_claim、promise_only、"
    "no_persistent_evidence。evidence_quote 必须逐字摘自 current_user_message；"
    "无法归类时 event 填 no_persistent_evidence，evidence_quote 为空字符串。"
    "stable_positive_interaction 只适用于用户明确评价一段已经发生的具体互动，"
    "普通请求、提问或事实陈述必须填 no_persistent_evidence。"
    "boundary_respected 只适用于用户明确回顾 Avery 已经按边界停下或尊重边界；"
    "当前正在提出的『请停止/请温柔/不要继续』请求不是已尊重边界，必须填 no_persistent_evidence。"
    "字段必须恰为 event、evidence_quote、experience_summary、reply_text、language；"
    "language 必须为 zh。"
    '例如：{"event":"boundary_respected","evidence_quote":"<current_user_message 中的逐字片段>",'
    '"experience_summary":"","reply_text":"...","language":"zh"}。'
)
_KNOWLEDGE_SYSTEM_MESSAGE = (
    "你是 Knowledge 引用提议与回复 provider。只可使用 user JSON 中的当前消息和 candidate_entries；"
    "不得推断或输出 profile、timeline、session、conversation、数据库 ID、隐藏历史或推理过程。"
    "citations 是为回答当前消息而引用的条目 entry_id 列表，只能取自 candidate_entries 的 entry_id；"
    "candidate_entries 都不相关时 citations 必须为空列表 []，"
    "此时 reply_text 只能使用常识性语言，不得编造 candidate_entries 之外的事实。"
    "复合问题中只回答 candidate_entries 能支持的部分；其他部分不要声称未知或没有信息，"
    "交由其他认知处理。"
    "字段必须恰为 citations、experience_summary、reply_text、language；language 必须为 zh。"
    '例如：{"citations":["<candidate_entries 中的 entry_id>"],'
    '"experience_summary":"...","reply_text":"...","language":"zh"}。'
)
_MAX_OUTPUT_TOKENS = 400
_MAX_SUMMARY_CHARACTERS = 500
_MAX_EXPRESSION_CHARACTERS = 1_000
_CACHE_MISS_INPUT_USD_PER_MILLION = 0.14
_OUTPUT_USD_PER_MILLION = 0.28
_SYSTEM_MESSAGE = (
    "请用简洁、自然的中文回答当前请求。只能使用 USER_CONFIRMED_CONTEXT 中的已确认事实；"
    "必须明确区分已确认、未知和 unavailable，不得编造过去对话、项目进展、承诺、记忆或关系。"
    "不要输出分析过程、推理过程或内在思维。只返回一个 JSON 对象，并且只能包含 "
    "experience_summary、expression_text、language 三个字段；language 必须是 zh-cn。"
)
_LIVING_MEMORY_SYSTEM_MESSAGE = (
    "你是 Avery 的 Living Memory 提议与回复 provider。回复时始终以 Avery 第一人称表达，"
    "不得自称 Living Memory、provider、模块或通用智能助手。"
    "只可使用 user JSON 中的当前消息和 active_memories；"
    "不得推断或输出 profile、timeline、session、conversation、数据库 ID、隐藏历史或推理过程。"
    "不得声称或提议提醒、后台跟进、代替用户执行或确保现实任务完成。"
    "action 只能是 none/create/revise 三者之一，不存在其他值："
    "当前消息含值得记住的新事实 → create，evidence_quote 逐字摘自当前消息；"
    "值得记住的事实包括：个人偏好、身份数据、人际关系事实，"
    "以及用户陈述的近期打算与约定——用户说「我明天要学习X」「我后天要Y」时，"
    "这就是用户要你记住的事，必须 create；"
    "用户更正或修改某条既有记忆 → revise，supersedes_memory_id 填该记忆的 memory_id；"
    "create 时必须附 memory_kind：持久属性、偏好、身份数据填 durable；"
    "近期打算、约定、日程（如「我明天要X」）填 plan；"
    "用户单方面声称与 Avery 已是朋友、恋人或其他关系，不是可持久化的关系事实，必须 none；"
    "其余一律 none，evidence_quote 为空字符串。"
    "引用既有记忆作答时 action 必须为 none，并把它们的 memory_id 放入 recalled_memory_ids；"
    "recalled_memory_ids 只能取自 active_memories。"
    "复合问题中只回答 active_memories 能支持的部分；其他部分不要声称未知或没有信息，"
    "交由其他认知处理；若本轮没有记忆相关回答，reply_text 填「（无记忆相关内容）」而非空字符串。"
    'create 形如：{"action":"create","evidence_quote":"<逐字片段>","memory_kind":"plan",'
    '"supersedes_memory_id":null,"recalled_memory_ids":[],'
    '"experience_summary":"...","reply_text":"...","language":"zh"}。'
    '召回应答形如：{"action":"none","evidence_quote":"","supersedes_memory_id":null,'
    '"recalled_memory_ids":["<active_memories 中的 memory_id>"],'
    '"experience_summary":"...","reply_text":"...","language":"zh"}。'
    "只返回 JSON 对象：create 时字段必须恰为 action、evidence_quote、memory_kind、"
    "supersedes_memory_id、recalled_memory_ids、experience_summary、reply_text、language；"
    "其余 action 时不含 memory_kind；language 必须为 zh。"
)
_CONFIRMED_COMMAND = (
    "Avery，我们正在筹备 Lantern Zine。给出三条下一步的建议，说明一下你缺少哪些信息，我告诉你。"
)
_CONFIRMED_FACTS: tuple[str, ...] = ()
_CONFIRMED_UNKNOWNS: tuple[str, ...] = ()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _bounded_text(value: Any, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT)
    return value


def _outbound_body(request: CognitionProviderRequest) -> dict[str, Any]:
    if (
        type(request) is not CognitionProviderRequest
        or request.provider != DEEPSEEK_PROVIDER
        or request.model != DEEPSEEK_MODEL
        or request.language != "zh-cn"
    ):
        raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
    facts = "\n".join(f"- {item}" for item in request.confirmed_facts)
    unknowns = "\n".join(f"- {item}" for item in request.acknowledged_unknowns)
    confirmed_facts_section = (
        f"CONFIRMED_FACTS:\n{facts}" if facts else "CONFIRMED_FACTS:"
    )
    unknowns_section = f"UNKNOWNS:\n{unknowns}" if unknowns else "UNKNOWNS:"
    user_message = (
        f"CURRENT_COMMAND:\n{request.current_command}\n\n"
        f"USER_CONFIRMED_CONTEXT:\n{confirmed_facts_section}\n\n{unknowns_section}"
    )
    return {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_MESSAGE},
            {"role": "user", "content": user_message},
        ],
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "max_tokens": _MAX_OUTPUT_TOKENS,
        "temperature": 0.2,
        "stream": False,
        "tools": [],
        "tool_choice": "none",
    }


@dataclass(frozen=True)
class DeepSeekHttpResponse:
    """Sanitized response boundary; it is never a canonical projection."""

    status_code: int
    body: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.status_code, int) or not 100 <= self.status_code <= 599:
            raise ValueError("status_code must be an HTTP status")
        if not isinstance(self.body, bytes):
            raise TypeError("body must be bytes")


class DeepSeekTransport(ABC):
    """Secret-bearing delivery seam; implementations receive only a CredentialRef."""

    @abstractmethod
    def post_json(
        self,
        *,
        endpoint: str,
        body: bytes,
        credential_ref: CredentialRef,
        timeout_seconds: float,
    ) -> DeepSeekHttpResponse:
        raise NotImplementedError


class DeepSeekCredentialResolver(ABC):
    """Secret boundary supplied explicitly by a later operation runner."""

    @abstractmethod
    def resolve(self, credential_ref: CredentialRef) -> str:
        raise NotImplementedError


class DeepSeekUrlLibTransport(DeepSeekTransport):
    """Single-attempt HTTPS delivery with no configuration discovery or retry."""

    def __init__(
        self,
        *,
        credential_resolver: DeepSeekCredentialResolver,
        _opener: Callable[..., Any] = urlopen,
    ) -> None:
        if not isinstance(credential_resolver, DeepSeekCredentialResolver):
            raise TypeError(
                "credential_resolver must implement DeepSeekCredentialResolver"
            )
        if not callable(_opener):
            raise TypeError("_opener must be callable")
        self._credential_resolver = credential_resolver
        self._opener = _opener

    def post_json(
        self,
        *,
        endpoint: str,
        body: bytes,
        credential_ref: CredentialRef,
        timeout_seconds: float,
    ) -> DeepSeekHttpResponse:
        if (
            endpoint != DEEPSEEK_ENDPOINT
            or not isinstance(body, bytes)
            or not body
            or len(body) > _LIVING_MEMORY_MAX_REQUEST_BYTES
            or timeout_seconds != DEEPSEEK_TIMEOUT_SECONDS
            or not isinstance(credential_ref, CredentialRef)
            or credential_ref.backend_id != DEEPSEEK_CREDENTIAL_BACKEND_ID
            or credential_ref.key_id != DEEPSEEK_CREDENTIAL_KEY_ID
        ):
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        secret = self._credential_resolver.resolve(credential_ref)
        if (
            not isinstance(secret, str)
            or not secret
            or len(secret) > 16_384
            or any(marker in secret for marker in ("\x00", "\r", "\n"))
        ):
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        request = Request(
            endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {secret}",
            },
            method="POST",
        )
        try:
            with self._opener(request, timeout=timeout_seconds) as response:
                status_code = int(response.status)
                response_body = response.read(65_537)
        except HTTPError as error:
            status_code = int(error.code)
            response_body = error.read(65_537)
        except (TimeoutError, socket.timeout):
            raise ProviderFailure(ProviderFailureCode.DELIVERY_AMBIGUOUS) from None
        except URLError:
            raise ProviderFailure(ProviderFailureCode.NETWORK_FAILURE) from None
        except ProviderFailure:
            raise
        except Exception:
            raise ProviderFailure(ProviderFailureCode.NETWORK_FAILURE) from None
        finally:
            secret = ""
        if not isinstance(response_body, bytes) or len(response_body) > 65_536:
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        return DeepSeekHttpResponse(status_code=status_code, body=response_body)


class DeepSeekCognitionProvider(CognitionProvider):
    """One-attempt, approval-bound adapter for the confirmed V4 Flash payload."""

    descriptor = ProviderDescriptor(
        authority_id=DEEPSEEK_PROVIDER_AUTHORITY_ID,
        provider=DEEPSEEK_PROVIDER,
        model=DEEPSEEK_MODEL,
        transport=ProviderTransport.EXTERNAL_NETWORK,
    )

    def __init__(
        self,
        *,
        transport: DeepSeekTransport,
        egress_approval: OperationEgressApproval,
    ) -> None:
        if not isinstance(transport, DeepSeekTransport):
            raise TypeError("transport must implement DeepSeekTransport")
        if not isinstance(egress_approval, OperationEgressApproval):
            raise TypeError("egress_approval must be OperationEgressApproval")
        self.terms = self.terms_disclosure()
        self._transport = transport
        self._egress_approval = egress_approval

    @classmethod
    def terms_disclosure(cls) -> ProviderTermsDisclosure:
        return ProviderTermsDisclosure.disclose(
            disclosure_id=DEEPSEEK_TERMS_DISCLOSURE_ID,
            descriptor=cls.descriptor,
            training_use=DisclosureItem(
                DisclosureKnowledge.UNKNOWN,
                "Training use is unknown for this downstream API operation.",
            ),
            retention=DisclosureItem(
                DisclosureKnowledge.AMBIGUOUS,
                "Fixed request-log retention is unknown; automatic disk context caching may last hours to days.",
            ),
            processing_location=DisclosureItem(
                DisclosureKnowledge.UNKNOWN,
                "The exact processing region for this API operation is unknown.",
            ),
            deletion_method=DisclosureItem(
                DisclosureKnowledge.UNKNOWN,
                "No per-request API deletion mechanism was documented.",
            ),
            terms_version="deepseek-official-2026-08-07-preview-02-v4-flash",
        )

    @classmethod
    def outbound_bytes(cls, request: CognitionProviderRequest) -> bytes:
        body = _canonical_json_bytes(_outbound_body(request))
        if len(body) > _MAX_REQUEST_BYTES:
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        cost_ceiling = (
            _MAX_REQUEST_BYTES * _CACHE_MISS_INPUT_USD_PER_MILLION
            + _MAX_OUTPUT_TOKENS * _OUTPUT_USD_PER_MILLION
        ) / 1_000_000
        if cost_ceiling > DEEPSEEK_SINGLE_ATTEMPT_BUDGET_USD:
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        return body

    @classmethod
    def outbound_digest(cls, request: CognitionProviderRequest) -> str:
        return sha256(cls.outbound_bytes(request)).hexdigest()

    def generate(
        self,
        request: CognitionProviderRequest,
        *,
        credential_ref: object | None,
    ) -> CognitionProviderResult:
        if (
            request.current_command != _CONFIRMED_COMMAND
            or request.confirmed_facts != _CONFIRMED_FACTS
            or request.acknowledged_unknowns != _CONFIRMED_UNKNOWNS
        ):
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        if not isinstance(credential_ref, CredentialRef) or (
            credential_ref.backend_id != DEEPSEEK_CREDENTIAL_BACKEND_ID
            or credential_ref.key_id != DEEPSEEK_CREDENTIAL_KEY_ID
        ):
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        body = self.outbound_bytes(request)
        if not self._egress_approval.authorizes(
            operation_id=request.operation_id,
            outbound_digest=sha256(body).hexdigest(),
            disclosure=self.terms,
        ):
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        try:
            response = self._transport.post_json(
                endpoint=DEEPSEEK_ENDPOINT,
                body=body,
                credential_ref=credential_ref,
                timeout_seconds=DEEPSEEK_TIMEOUT_SECONDS,
            )
        except ProviderFailure:
            raise
        except TimeoutError:
            raise ProviderFailure(ProviderFailureCode.DELIVERY_AMBIGUOUS) from None
        except Exception:
            raise ProviderFailure(ProviderFailureCode.NETWORK_FAILURE) from None
        if type(response) is not DeepSeekHttpResponse or response.status_code != 200:
            if isinstance(response, DeepSeekHttpResponse) and response.status_code == 429:
                raise ProviderFailure(ProviderFailureCode.RATE_LIMIT)
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        try:
            payload = json.loads(response.body.decode("utf-8"))
            choices = payload["choices"]
            message = choices[0]["message"]
            content = json.loads(message["content"])
            usage = payload["usage"]
            prompt_tokens = int(usage["prompt_tokens"])
            completion_tokens = int(usage["completion_tokens"])
        except (KeyError, IndexError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT) from None
        if (
            payload.get("model") != DEEPSEEK_MODEL
            or not isinstance(choices, list)
            or len(choices) != 1
            or not isinstance(message, dict)
            or message.get("role") != "assistant"
            or message.get("reasoning_content") not in (None, "")
            or message.get("tool_calls") not in (None, [])
            or not isinstance(content, dict)
            or set(content) != {"experience_summary", "expression_text", "language"}
            or content.get("language") != "zh-cn"
            or prompt_tokens < 0
            or completion_tokens < 0
            or completion_tokens > _MAX_OUTPUT_TOKENS
        ):
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT)
        actual_cost = (
            prompt_tokens * _CACHE_MISS_INPUT_USD_PER_MILLION
            + completion_tokens * _OUTPUT_USD_PER_MILLION
        ) / 1_000_000
        if actual_cost > DEEPSEEK_SINGLE_ATTEMPT_BUDGET_USD:
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        summary = _bounded_text(
            content["experience_summary"],
            maximum=_MAX_SUMMARY_CHARACTERS,
        )
        expression = _bounded_text(
            content["expression_text"],
            maximum=_MAX_EXPRESSION_CHARACTERS,
        )
        return CognitionProviderResult.delivered(
            request,
            experience_summary=summary,
            expression_text=expression,
        )


class DeepSeekLivingMemoryProvider:
    """Default-profile Living Memory adapter over the existing DeepSeek transport."""

    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def __init__(
        self,
        *,
        transport: object,
        credential_ref: object,
    ) -> None:
        if not isinstance(transport, DeepSeekTransport):
            raise TypeError("transport must implement DeepSeekTransport")
        if not isinstance(credential_ref, CredentialRef) or (
            credential_ref.backend_id != DEEPSEEK_CREDENTIAL_BACKEND_ID
            or credential_ref.key_id != DEEPSEEK_CREDENTIAL_KEY_ID
        ):
            raise TypeError("credential_ref must name the DeepSeek credential")
        self._transport = transport
        self._credential_ref = credential_ref

    @classmethod
    def outbound_bytes(cls, request: LivingMemoryProviderRequest) -> bytes:
        if (
            not isinstance(request, LivingMemoryProviderRequest)
            or not isinstance(request.current_user_message, str)
            or not request.current_user_message.strip()
            or len(request.current_user_message) > 32_768
            or not isinstance(request.active_memories, tuple)
            or len(request.active_memories) > ACTIVE_MEMORY_LIMIT
        ):
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        memories = []
        for memory in request.active_memories:
            if (
                not isinstance(memory, LivingMemoryProviderMemory)
                or not memory.memory_id
                or not memory.content.strip()
                or len(memory.content) > 500
                or not memory.source_user_message_id
            ):
                raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
            memories.append(
                {
                    "memory_id": memory.memory_id,
                    "content": memory.content,
                    "source_user_message_id": memory.source_user_message_id,
                }
            )
        projection = {
            "current_user_message": request.current_user_message,
            "active_memories": memories,
        }
        body = _canonical_json_bytes(
            {
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": _LIVING_MEMORY_SYSTEM_MESSAGE},
                    {
                        "role": "user",
                        "content": _canonical_json_bytes(projection).decode("utf-8"),
                    },
                ],
                "thinking": {"type": "disabled"},
                "response_format": {"type": "json_object"},
                "max_tokens": _LIVING_MEMORY_MAX_OUTPUT_TOKENS,
                "temperature": 0.2,
                "stream": False,
                "tools": [],
                "tool_choice": "none",
            }
        )
        if len(body) > _LIVING_MEMORY_MAX_REQUEST_BYTES:
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        return body

    def analyze(
        self,
        request: LivingMemoryProviderRequest,
    ) -> LivingMemoryProviderResult:
        body = self.outbound_bytes(request)
        try:
            response = self._transport.post_json(
                endpoint=DEEPSEEK_ENDPOINT,
                body=body,
                credential_ref=self._credential_ref,
                timeout_seconds=DEEPSEEK_TIMEOUT_SECONDS,
            )
        except ProviderFailure:
            raise
        except TimeoutError:
            raise ProviderFailure(ProviderFailureCode.DELIVERY_AMBIGUOUS) from None
        except Exception:
            raise ProviderFailure(ProviderFailureCode.NETWORK_FAILURE) from None
        if type(response) is not DeepSeekHttpResponse or response.status_code != 200:
            if isinstance(response, DeepSeekHttpResponse) and response.status_code == 429:
                raise ProviderFailure(ProviderFailureCode.RATE_LIMIT)
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        try:
            payload = json.loads(response.body.decode("utf-8"))
            choices = payload["choices"]
            message = choices[0]["message"]
            content = json.loads(message["content"])
            usage = payload["usage"]
            prompt_tokens = int(usage["prompt_tokens"])
            completion_tokens = int(usage["completion_tokens"])
        except (KeyError, IndexError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT) from None
        needs_kind = (
            isinstance(content, dict) and content.get("action") == "create"
        )
        expected_fields = {
            "action",
            "evidence_quote",
            "supersedes_memory_id",
            "recalled_memory_ids",
            "experience_summary",
            "reply_text",
            "language",
        }
        if needs_kind:
            expected_fields.add("memory_kind")
        if (
            payload.get("model") != DEEPSEEK_MODEL
            or not isinstance(choices, list)
            or len(choices) != 1
            or not isinstance(message, dict)
            or message.get("role") != "assistant"
            or message.get("reasoning_content") not in (None, "")
            or message.get("tool_calls") not in (None, [])
            or not isinstance(content, dict)
            or set(content) != expected_fields
            or content.get("language") != "zh"
            or not isinstance(content.get("evidence_quote"), str)
            or content.get("supersedes_memory_id") is not None
            and not isinstance(content.get("supersedes_memory_id"), str)
            or not isinstance(content.get("recalled_memory_ids"), list)
            or any(
                not isinstance(memory_id, str)
                for memory_id in content.get("recalled_memory_ids", [])
            )
            or (
                needs_kind
                and content.get("memory_kind") not in {"durable", "plan"}
            )
            or prompt_tokens < 0
            or completion_tokens < 0
            or completion_tokens > _LIVING_MEMORY_MAX_OUTPUT_TOKENS
        ):
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT)
        try:
            action = LivingMemoryAction(content["action"])
            summary = content["experience_summary"]
            if not isinstance(summary, str) or len(summary) > _MAX_SUMMARY_CHARACTERS:
                raise ValueError("living memory summary must be a bounded string")
            reply = _bounded_text(
                content["reply_text"],
                maximum=_MAX_EXPRESSION_CHARACTERS,
            )
        except (TypeError, ValueError, ProviderFailure):
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT) from None
        return LivingMemoryProviderResult(
            proposal=LivingMemoryProposal(
                action=action,
                evidence_quote=content["evidence_quote"],
                supersedes_memory_id=content["supersedes_memory_id"],
                recalled_memory_ids=tuple(content["recalled_memory_ids"]),
                memory_kind=str(content.get("memory_kind", "durable")),
            ),
            experience_summary=summary,
            reply_text=reply,
            language="zh",
        )


class DeepSeekKnowledgeProvider:
    """Default-profile knowledge citation adapter over the existing DeepSeek transport."""

    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def __init__(
        self,
        *,
        transport: object,
        credential_ref: object,
    ) -> None:
        if not isinstance(transport, DeepSeekTransport):
            raise TypeError("transport must implement DeepSeekTransport")
        if not isinstance(credential_ref, CredentialRef) or (
            credential_ref.backend_id != DEEPSEEK_CREDENTIAL_BACKEND_ID
            or credential_ref.key_id != DEEPSEEK_CREDENTIAL_KEY_ID
        ):
            raise TypeError("credential_ref must name the DeepSeek credential")
        self._transport = transport
        self._credential_ref = credential_ref

    @classmethod
    def outbound_bytes(cls, request: KnowledgeProviderRequest) -> bytes:
        if (
            not isinstance(request, KnowledgeProviderRequest)
            or not isinstance(request.current_user_message, str)
            or not request.current_user_message.strip()
            or len(request.current_user_message) > 32_768
            or not isinstance(request.candidate_entries, tuple)
            or len(request.candidate_entries) > KNOWLEDGE_CANDIDATE_LIMIT
        ):
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        entries = []
        for entry in request.candidate_entries:
            if (
                not isinstance(entry, KnowledgeEntry)
                or not entry.entry_id
                or len(entry.entry_id) > 64
                or not _bounded_text(entry.title, maximum=200)
                or not _bounded_text(entry.content, maximum=4_000)
                or not entry.source_ref
                or len(entry.source_ref) > 200
            ):
                raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
            entries.append(
                {
                    "entry_id": entry.entry_id,
                    "title": entry.title,
                    "content": entry.content,
                }
            )
        body = _canonical_json_bytes(
            {
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": _KNOWLEDGE_SYSTEM_MESSAGE},
                    {
                        "role": "user",
                        "content": _canonical_json_bytes(
                            {
                                "current_user_message": request.current_user_message,
                                "candidate_entries": entries,
                            }
                        ).decode("utf-8"),
                    },
                ],
                "thinking": {"type": "disabled"},
                "response_format": {"type": "json_object"},
                "max_tokens": _KNOWLEDGE_MAX_OUTPUT_TOKENS,
                "temperature": 0.2,
                "stream": False,
                "tools": [],
                "tool_choice": "none",
            }
        )
        if len(body) > _KNOWLEDGE_MAX_REQUEST_BYTES:
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        return body

    def analyze(
        self,
        request: KnowledgeProviderRequest,
    ) -> KnowledgeProviderResult:
        body = self.outbound_bytes(request)
        projected_ids = {entry.entry_id for entry in request.candidate_entries}
        try:
            response = self._transport.post_json(
                endpoint=DEEPSEEK_ENDPOINT,
                body=body,
                credential_ref=self._credential_ref,
                timeout_seconds=DEEPSEEK_TIMEOUT_SECONDS,
            )
        except ProviderFailure:
            raise
        except TimeoutError:
            raise ProviderFailure(ProviderFailureCode.DELIVERY_AMBIGUOUS) from None
        except Exception:
            raise ProviderFailure(ProviderFailureCode.NETWORK_FAILURE) from None
        if type(response) is not DeepSeekHttpResponse or response.status_code != 200:
            if isinstance(response, DeepSeekHttpResponse) and response.status_code == 429:
                raise ProviderFailure(ProviderFailureCode.RATE_LIMIT)
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        try:
            payload = json.loads(response.body.decode("utf-8"))
            choices = payload["choices"]
            message = choices[0]["message"]
            content = json.loads(message["content"])
            usage = payload["usage"]
            prompt_tokens = int(usage["prompt_tokens"])
            completion_tokens = int(usage["completion_tokens"])
        except (KeyError, IndexError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT) from None
        expected_fields = {
            "citations",
            "experience_summary",
            "reply_text",
            "language",
        }
        if (
            payload.get("model") != DEEPSEEK_MODEL
            or not isinstance(choices, list)
            or len(choices) != 1
            or not isinstance(message, dict)
            or message.get("role") != "assistant"
            or message.get("reasoning_content") not in (None, "")
            or message.get("tool_calls") not in (None, [])
            or not isinstance(content, dict)
            or set(content) != expected_fields
            or content.get("language") != "zh"
            or not isinstance(content.get("citations"), list)
            or any(
                not isinstance(entry_id, str) or entry_id not in projected_ids
                for entry_id in content.get("citations", [])
            )
            or len(set(content.get("citations", []))) != len(content.get("citations", []))
            or prompt_tokens < 0
            or completion_tokens < 0
            or completion_tokens > _KNOWLEDGE_MAX_OUTPUT_TOKENS
        ):
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT)
        try:
            summary = content["experience_summary"]
            if not isinstance(summary, str) or len(summary) > _MAX_SUMMARY_CHARACTERS:
                raise ValueError("knowledge summary must be a bounded string")
            reply = _bounded_text(
                content["reply_text"],
                maximum=_MAX_EXPRESSION_CHARACTERS,
            )
        except (TypeError, ValueError, ProviderFailure):
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT) from None
        return KnowledgeProviderResult(
            proposal=KnowledgeProposal(
                citation_ids=tuple(content["citations"]),
            ),
            experience_summary=summary,
            reply_text=reply,
            language="zh",
        )


class DeepSeekRelationshipProvider:
    """Default-profile relationship classification adapter over the DeepSeek transport."""

    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def __init__(
        self,
        *,
        transport: object,
        credential_ref: object,
    ) -> None:
        if not isinstance(transport, DeepSeekTransport):
            raise TypeError("transport must implement DeepSeekTransport")
        if not isinstance(credential_ref, CredentialRef) or (
            credential_ref.backend_id != DEEPSEEK_CREDENTIAL_BACKEND_ID
            or credential_ref.key_id != DEEPSEEK_CREDENTIAL_KEY_ID
        ):
            raise TypeError("credential_ref must name the DeepSeek credential")
        self._transport = transport
        self._credential_ref = credential_ref

    @classmethod
    def outbound_bytes(cls, request: RelationshipProviderRequest) -> bytes:
        if (
            not isinstance(request, RelationshipProviderRequest)
            or not isinstance(request.current_user_message, str)
            or not request.current_user_message.strip()
            or len(request.current_user_message) > 32_768
            or not isinstance(request.stance_summary, str)
            or len(request.stance_summary) > 2_000
        ):
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        body = _canonical_json_bytes(
            {
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": _RELATIONSHIP_SYSTEM_MESSAGE},
                    {
                        "role": "user",
                        "content": _canonical_json_bytes(
                            {
                                "current_user_message": request.current_user_message,
                                "stance_summary": request.stance_summary,
                                "policy_version": "relationship-stance-v1",
                            }
                        ).decode("utf-8"),
                    },
                ],
                "thinking": {"type": "disabled"},
                "response_format": {"type": "json_object"},
                "max_tokens": _RELATIONSHIP_MAX_OUTPUT_TOKENS,
                "temperature": 0.2,
                "stream": False,
                "tools": [],
                "tool_choice": "none",
            }
        )
        if len(body) > _RELATIONSHIP_MAX_REQUEST_BYTES:
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        return body

    def analyze(
        self,
        request: RelationshipProviderRequest,
    ) -> RelationshipProviderResult:
        body = self.outbound_bytes(request)
        try:
            response = self._transport.post_json(
                endpoint=DEEPSEEK_ENDPOINT,
                body=body,
                credential_ref=self._credential_ref,
                timeout_seconds=DEEPSEEK_TIMEOUT_SECONDS,
            )
        except ProviderFailure:
            raise
        except TimeoutError:
            raise ProviderFailure(ProviderFailureCode.DELIVERY_AMBIGUOUS) from None
        except Exception:
            raise ProviderFailure(ProviderFailureCode.NETWORK_FAILURE) from None
        if type(response) is not DeepSeekHttpResponse or response.status_code != 200:
            if isinstance(response, DeepSeekHttpResponse) and response.status_code == 429:
                raise ProviderFailure(ProviderFailureCode.RATE_LIMIT)
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        try:
            payload = json.loads(response.body.decode("utf-8"))
            choices = payload["choices"]
            message = choices[0]["message"]
            content = json.loads(message["content"])
            usage = payload["usage"]
            prompt_tokens = int(usage["prompt_tokens"])
            completion_tokens = int(usage["completion_tokens"])
        except (KeyError, IndexError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT) from None
        expected_fields = {
            "event",
            "evidence_quote",
            "experience_summary",
            "reply_text",
            "language",
        }
        if (
            payload.get("model") != DEEPSEEK_MODEL
            or not isinstance(choices, list)
            or len(choices) != 1
            or not isinstance(message, dict)
            or message.get("role") != "assistant"
            or message.get("reasoning_content") not in (None, "")
            or message.get("tool_calls") not in (None, [])
            or not isinstance(content, dict)
            or set(content) != expected_fields
            or content.get("language") != "zh"
            or content.get("event") not in ALL_RELATIONSHIP_EVENTS
            or not isinstance(content.get("evidence_quote"), str)
            or (
                bool(content.get("evidence_quote"))
                and content["evidence_quote"] not in request.current_user_message
            )
            or not isinstance(content.get("experience_summary"), str)
            or len(content.get("experience_summary", "")) > _MAX_SUMMARY_CHARACTERS
            or prompt_tokens < 0
            or completion_tokens < 0
            or completion_tokens > _RELATIONSHIP_MAX_OUTPUT_TOKENS
        ):
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT)
        try:
            reply = _bounded_text(
                content["reply_text"],
                maximum=_MAX_EXPRESSION_CHARACTERS,
            )
        except (TypeError, ValueError, ProviderFailure):
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT) from None
        return RelationshipProviderResult(
            proposal=RelationshipProposal(
                event=content["event"],
                evidence_quote=content["evidence_quote"],
            ),
            experience_summary=content["experience_summary"],
            reply_text=reply,
            language="zh",
        )


class DeepSeekParticipantGoalProvider:
    """Two-stage default-profile adapter for participant goals and commitments."""

    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def __init__(
        self,
        *,
        transport: object,
        credential_ref: object,
    ) -> None:
        if not isinstance(transport, DeepSeekTransport):
            raise TypeError("transport must implement DeepSeekTransport")
        if not isinstance(credential_ref, CredentialRef) or (
            credential_ref.backend_id != DEEPSEEK_CREDENTIAL_BACKEND_ID
            or credential_ref.key_id != DEEPSEEK_CREDENTIAL_KEY_ID
        ):
            raise TypeError("credential_ref must name the DeepSeek credential")
        self._transport = transport
        self._credential_ref = credential_ref

    @classmethod
    def classification_outbound_bytes(
        cls,
        request: ParticipantGoalClassificationRequest,
    ) -> bytes:
        if (
            not isinstance(request, ParticipantGoalClassificationRequest)
            or not isinstance(request.current_user_message, str)
            or not request.current_user_message.strip()
            or len(request.current_user_message) > 32_768
            or not isinstance(request.active_records, tuple)
            or len(request.active_records) > ACTIVE_RECORD_LIMIT
            or request.policy_id != PARTICIPANT_GOAL_POLICY_ID
            or request.policy_version != PARTICIPANT_GOAL_POLICY_VERSION
            or request.policy_hash != PARTICIPANT_GOAL_POLICY_HASH
        ):
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        records = []
        refs: set[str] = set()
        for record in request.active_records:
            if (
                not isinstance(record, ParticipantGoalProviderRecord)
                or not isinstance(record.turn_ref, str)
                or not record.turn_ref
                or record.turn_ref in refs
                or record.kind not in {"goal", "commitment"}
                or not isinstance(record.terms, str)
                or not record.terms.strip()
                or len(record.terms) > MAX_TERMS_CHARS
                or record.status != "active"
            ):
                raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
            refs.add(record.turn_ref)
            records.append(
                {
                    "turn_ref": record.turn_ref,
                    "kind": record.kind,
                    "terms": record.terms,
                    "status": record.status,
                }
            )
        return cls._bounded_body(
            system_message=_PARTICIPANT_GOAL_CLASSIFICATION_SYSTEM_MESSAGE,
            projection={
                "current_user_message": request.current_user_message,
                "active_records": records,
                "policy": {
                    "id": request.policy_id,
                    "version": request.policy_version,
                    "hash": request.policy_hash,
                },
            },
            max_tokens=_PARTICIPANT_GOAL_MAX_OUTPUT_TOKENS,
        )

    @classmethod
    def reply_outbound_bytes(cls, request: ParticipantGoalReplyRequest) -> bytes:
        if (
            not isinstance(request, ParticipantGoalReplyRequest)
            or not isinstance(request.current_user_message, str)
            or not request.current_user_message.strip()
            or len(request.current_user_message) > 32_768
            or not isinstance(request.selected_records, tuple)
            or len(request.selected_records) > REPLY_RECORD_LIMIT
        ):
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        records = []
        for record in request.selected_records:
            if (
                not isinstance(record, ParticipantGoalReplyRecord)
                or record.kind not in {"goal", "commitment"}
                or not isinstance(record.terms, str)
                or not record.terms.strip()
                or len(record.terms) > MAX_TERMS_CHARS
                or record.status != "active"
            ):
                raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
            records.append(
                {"kind": record.kind, "terms": record.terms, "status": record.status}
            )
        return cls._bounded_body(
            system_message=_PARTICIPANT_GOAL_REPLY_SYSTEM_MESSAGE,
            projection={
                "current_user_message": request.current_user_message,
                "selected_records": records,
            },
            max_tokens=_PARTICIPANT_GOAL_MAX_OUTPUT_TOKENS,
        )

    @classmethod
    def _bounded_body(
        cls,
        *,
        system_message: str,
        projection: dict[str, object],
        max_tokens: int,
    ) -> bytes:
        body = _canonical_json_bytes(
            {
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": system_message},
                    {
                        "role": "user",
                        "content": _canonical_json_bytes(projection).decode("utf-8"),
                    },
                ],
                "thinking": {"type": "disabled"},
                "response_format": {"type": "json_object"},
                "max_tokens": max_tokens,
                "temperature": 0.2,
                "stream": False,
                "tools": [],
                "tool_choice": "none",
            }
        )
        if len(body) > _PARTICIPANT_GOAL_MAX_REQUEST_BYTES:
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        return body

    def classify(
        self,
        request: ParticipantGoalClassificationRequest,
    ) -> ParticipantGoalClassificationResult:
        body = self.classification_outbound_bytes(request)
        content = self._post_and_decode(body)
        try:
            return canonicalize_participant_goal_output(content, request=request)
        except ParticipantGoalOutputRejected:
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT) from None

    def reply(self, request: ParticipantGoalReplyRequest) -> ParticipantGoalReplyResult:
        body = self.reply_outbound_bytes(request)
        content = self._post_and_decode(body)
        if (
            set(content) != {"reply_text", "language"}
            or content.get("language") != "zh"
        ):
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT)
        try:
            reply_text = _bounded_text(
                content["reply_text"],
                maximum=_MAX_EXPRESSION_CHARACTERS,
            )
        except (KeyError, TypeError, ProviderFailure):
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT) from None
        return ParticipantGoalReplyResult(reply_text=reply_text, language="zh")

    def _post_and_decode(self, body: bytes) -> dict[str, object]:
        try:
            response = self._transport.post_json(
                endpoint=DEEPSEEK_ENDPOINT,
                body=body,
                credential_ref=self._credential_ref,
                timeout_seconds=DEEPSEEK_TIMEOUT_SECONDS,
            )
        except ProviderFailure:
            raise
        except TimeoutError:
            raise ProviderFailure(ProviderFailureCode.DELIVERY_AMBIGUOUS) from None
        except Exception:
            raise ProviderFailure(ProviderFailureCode.NETWORK_FAILURE) from None
        if type(response) is not DeepSeekHttpResponse or response.status_code != 200:
            if isinstance(response, DeepSeekHttpResponse) and response.status_code == 429:
                raise ProviderFailure(ProviderFailureCode.RATE_LIMIT)
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        try:
            payload = json.loads(response.body.decode("utf-8"))
            choices = payload["choices"]
            message = choices[0]["message"]
            content = json.loads(message["content"])
            usage = payload["usage"]
            prompt_tokens = int(usage["prompt_tokens"])
            completion_tokens = int(usage["completion_tokens"])
        except (KeyError, IndexError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT) from None
        if (
            payload.get("model") != DEEPSEEK_MODEL
            or not isinstance(choices, list)
            or len(choices) != 1
            or not isinstance(message, dict)
            or message.get("role") != "assistant"
            or message.get("reasoning_content") not in (None, "")
            or message.get("tool_calls") not in (None, [])
            or not isinstance(content, dict)
            or prompt_tokens < 0
            or completion_tokens < 0
            or completion_tokens > _PARTICIPANT_GOAL_MAX_OUTPUT_TOKENS
        ):
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT)
        return content


class DeepSeekSituatedProvider:
    """DeepSeek Adapter for provider-neutral Situated tasks."""

    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def __init__(self, *, transport: object, credential_ref: object) -> None:
        self._wire = DeepSeekParticipantGoalProvider(
            transport=transport,
            credential_ref=credential_ref,
        )

    @classmethod
    def classification_outbound_bytes(
        cls,
        request: SituatedClassificationRequest,
    ) -> bytes:
        if (
            not isinstance(request, SituatedClassificationRequest)
            or not request.current_user_message.strip()
            or len(request.current_user_message) > 32_768
            or len(request.active_state) > 1
            or request.policy_id != SITUATED_POLICY_ID
            or request.policy_version != SITUATED_POLICY_VERSION
            or request.policy_hash != SITUATED_POLICY_HASH
        ):
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        active = []
        for state in request.active_state:
            if (
                not isinstance(state, SituatedStateTarget)
                or state.posture not in SITUATED_POSTURES
                or state.remaining_turns != 1
                or state.expires_in_seconds <= 0
                or state.expires_in_seconds > 1_800
            ):
                raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
            active.append(
                {
                    "posture": state.posture,
                    "remaining_turns": state.remaining_turns,
                    "expires_in_seconds": state.expires_in_seconds,
                }
            )
        return DeepSeekParticipantGoalProvider._bounded_body(
            system_message=_SITUATED_CLASSIFICATION_SYSTEM_MESSAGE,
            projection={
                "current_user_message": request.current_user_message,
                "active_state": active,
                "policy": {
                    "id": request.policy_id,
                    "version": request.policy_version,
                    "hash": request.policy_hash,
                },
            },
            max_tokens=_SITUATED_MAX_OUTPUT_TOKENS,
        )

    @classmethod
    def reply_outbound_bytes(cls, request: SituatedReplyRequest) -> bytes:
        if (
            not isinstance(request, SituatedReplyRequest)
            or not request.current_user_message.strip()
            or len(request.current_user_message) > 32_768
            or request.posture not in SITUATED_POSTURES
        ):
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        return DeepSeekParticipantGoalProvider._bounded_body(
            system_message=_SITUATED_REPLY_SYSTEM_MESSAGE,
            projection={
                "current_user_message": request.current_user_message,
                "selected_state": {"posture": request.posture},
            },
            max_tokens=_SITUATED_MAX_OUTPUT_TOKENS,
        )

    def classify(
        self,
        request: SituatedClassificationRequest,
    ) -> SituatedClassificationResult:
        content = self._wire._post_and_decode(
            self.classification_outbound_bytes(request)
        )
        try:
            return canonicalize_situated_output(content, request=request)
        except SituatedOutputRejected:
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT) from None

    def reply(self, request: SituatedReplyRequest) -> SituatedReplyResult:
        content = self._wire._post_and_decode(self.reply_outbound_bytes(request))
        if (
            set(content) != {"reply_text", "language"}
            or content.get("language") != "zh"
        ):
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT)
        try:
            reply = _bounded_text(
                content["reply_text"],
                maximum=_MAX_EXPRESSION_CHARACTERS,
            )
        except (KeyError, TypeError, ProviderFailure):
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT) from None
        return SituatedReplyResult(reply_text=reply, language="zh")


class DeepSeekMediumProvider:
    provider_authority = DEEPSEEK_PROVIDER_AUTHORITY_ID
    test_only = False

    def __init__(self, *, transport: object, credential_ref: object) -> None:
        self._wire = DeepSeekParticipantGoalProvider(
            transport=transport,
            credential_ref=credential_ref,
        )

    @classmethod
    def classification_outbound_bytes(cls, request: MediumClassificationRequest) -> bytes:
        if (
            not isinstance(request, MediumClassificationRequest)
            or not request.current_user_message.strip()
            or len(request.current_user_message) > 32_768
            or request.policy_id != MEDIUM_POLICY_ID
            or request.policy_version != MEDIUM_POLICY_VERSION
            or request.policy_hash != MEDIUM_POLICY_HASH
        ):
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        return DeepSeekParticipantGoalProvider._bounded_body(
            system_message=_MEDIUM_CLASSIFICATION_SYSTEM_MESSAGE,
            projection={
                "current_user_message": request.current_user_message,
                "policy": {
                    "id": request.policy_id,
                    "version": request.policy_version,
                    "hash": request.policy_hash,
                },
            },
            max_tokens=_SITUATED_MAX_OUTPUT_TOKENS,
        )

    @classmethod
    def reply_outbound_bytes(cls, request: MediumReplyRequest) -> bytes:
        if (
            not isinstance(request, MediumReplyRequest)
            or not request.current_user_message.strip()
            or request.baseline not in MEDIUM_BASELINES
        ):
            raise ProviderFailure(ProviderFailureCode.UNAVAILABLE)
        return DeepSeekParticipantGoalProvider._bounded_body(
            system_message=_MEDIUM_REPLY_SYSTEM_MESSAGE,
            projection={
                "current_user_message": request.current_user_message,
                "selected_state": {"baseline": request.baseline},
            },
            max_tokens=_SITUATED_MAX_OUTPUT_TOKENS,
        )

    def classify(self, request: MediumClassificationRequest) -> MediumClassificationResult:
        content = self._wire._post_and_decode(
            self.classification_outbound_bytes(request)
        )
        try:
            return canonicalize_medium_output(content, request=request)
        except MediumOutputRejected:
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT) from None

    def reply(self, request: MediumReplyRequest) -> MediumReplyResult:
        content = self._wire._post_and_decode(self.reply_outbound_bytes(request))
        if set(content) != {"reply_text", "language"} or content.get("language") != "zh":
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT)
        try:
            reply = _bounded_text(content["reply_text"], maximum=_MAX_EXPRESSION_CHARACTERS)
        except (KeyError, TypeError, ProviderFailure):
            raise ProviderFailure(ProviderFailureCode.INVALID_OUTPUT) from None
        return MediumReplyResult(reply, "zh")


class ApprovedDeepSeekCognition(ControlledCognition):
    """The sole external-provider Cognition adapter permitted by this ticket."""

    adapter_version = "post-m0-deepseek-v4-flash-operation-route-1.0"
    test_only = False

    def __init__(
        self,
        *,
        provider: DeepSeekCognitionProvider,
        context_brief: UserConfirmedContextBrief,
        operation_reservation: OperationEgressReservation,
        credential_ref: CredentialRef,
    ) -> None:
        if type(provider) is not DeepSeekCognitionProvider:
            raise TypeError("provider must be the confirmed DeepSeek adapter")
        super().__init__(
            provider=provider,
            context_brief=context_brief,
            egress_approval=provider._egress_approval,
            credential_ref=credential_ref,
            operation_reservation=operation_reservation,
        )

    def _permits_external_provider(self, provider: CognitionProvider) -> bool:
        return (
            type(provider) is DeepSeekCognitionProvider
            and provider.descriptor == DeepSeekCognitionProvider.descriptor
            and provider.terms == DeepSeekCognitionProvider.terms_disclosure()
        )


__all__ = [
    "DEEPSEEK_CREDENTIAL_BACKEND_ID",
    "DEEPSEEK_CREDENTIAL_KEY_ID",
    "DEEPSEEK_ENDPOINT",
    "DEEPSEEK_MODEL",
    "ApprovedDeepSeekCognition",
    "DeepSeekCognitionProvider",
    "DeepSeekCredentialResolver",
    "DeepSeekHttpResponse",
    "DeepSeekKnowledgeProvider",
    "DeepSeekParticipantGoalProvider",
    "DeepSeekRelationshipProvider",
    "DeepSeekSituatedProvider",
    "DeepSeekMediumProvider",
    "DeepSeekLivingMemoryProvider",
    "DeepSeekTransport",
    "DeepSeekUrlLibTransport",
]
