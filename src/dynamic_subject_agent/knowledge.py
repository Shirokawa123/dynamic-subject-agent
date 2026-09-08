"""Controlled knowledge citation cognition using provider proposals and Python adjudication."""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from uuid import NAMESPACE_URL, uuid5

from dynamic_subject_agent.domains import (
    ExperienceAdjudicationRequest,
    ExperienceChangeCandidate,
    ExperienceReadView,
)
from dynamic_subject_agent.knowledge_entries import (
    KNOWLEDGE_CANDIDATE_LIMIT,
    KnowledgeEntry,
    SEALED_KNOWLEDGE_ENTRIES,
    select_knowledge_candidates,
)
from dynamic_subject_agent.runtime import (
    CognitionEngine,
    CognitionRuntimeView,
    CognitiveProposal,
    CyclePlan,
    ExperienceBasis,
    ExpressionCandidate,
    M0_A_PROVIDER_AUTHORITY,
)
from dynamic_subject_agent.model_gateway import (
    ModelGateway,
    ModelGatewayFailure,
    ModelResult,
    ModelTask,
    ModelTaskKind,
    ProviderAdapter,
    ProviderCapabilities,
    StructuredOutputMode,
)
from dynamic_subject_agent.timeline import SubjectCommand
from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection
from dynamic_subject_agent.runtime_identity_reply import activity_boundary_reply, contextual_reply, CREATIVE_REPLY_PREFIX


_NO_KNOWLEDGE_EXPRESSION = "（无知识相关内容）"


@dataclass(frozen=True)
class KnowledgeProviderRequest:
    current_user_message: str
    candidate_entries: tuple[KnowledgeEntry, ...]


@dataclass(frozen=True)
class KnowledgeReplyEntry:
    title: str
    content: str


@dataclass(frozen=True)
class KnowledgeReplyRequest:
    current_user_message: str
    selected_entries: tuple[KnowledgeReplyEntry, ...]
    runtime_identity: RuntimeIdentityProjection


@dataclass(frozen=True)
class KnowledgeReplyQuote:
    title: str
    quote: str


@dataclass(frozen=True)
class KnowledgeReplyResult:
    reply_text: str
    language: str
    reply_kind: str = 'source'
    source_quotes: tuple[KnowledgeReplyQuote, ...] = ()

    @classmethod
    def from_mapping(cls, value: object) -> KnowledgeReplyResult:
        if not isinstance(value, dict) or set(value) != {'reply_text', 'language', 'reply_kind', 'source_quotes'}:
            raise ValueError('knowledge-reply-fields-invalid')
        text, kind, quotes = value['reply_text'], value['reply_kind'], value['source_quotes']
        if (value['language'] != 'zh' or kind not in {'source', 'unknown', 'creative'}
            or not isinstance(text, str) or len(text) > 8_000
            or not isinstance(quotes, list) or len(quotes) > KNOWLEDGE_CANDIDATE_LIMIT):
            raise ValueError('knowledge-reply-shape-invalid')
        parsed = []
        for item in quotes:
            if (not isinstance(item, dict) or set(item) != {'title', 'quote'}
                or not isinstance(item['title'], str) or not 0 < len(item['title']) <= 200
                or not isinstance(item['quote'], str) or not 0 < len(item['quote']) <= 4_000):
                raise ValueError('knowledge-reply-quote-invalid')
            parsed.append(KnowledgeReplyQuote(item['title'], item['quote']))
        if kind == 'creative' and (not text.strip() or parsed):
            raise ValueError('knowledge-reply-creative-invalid')
        return cls(text, 'zh', kind, tuple(parsed))


def _source_sentences(content: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in re.findall(r'[^。！？!?]+[。！？!?]?', content) if part.strip())


def render_source_reply(entries: tuple[KnowledgeReplyEntry, ...], reply: KnowledgeReplyResult | None = None) -> str:
    """Render checked source text, never treat citation membership as entailment."""
    if not entries:
        return '这个问题我还没有可引用的来源。'
    quotes = ()
    if reply is not None and reply.reply_kind in ('source', 'unknown') and isinstance(reply.source_quotes, tuple):
        proposed = reply.source_quotes
        if 0 < len(proposed) <= KNOWLEDGE_CANDIDATE_LIMIT and all(
            isinstance(item, KnowledgeReplyQuote) and any(
                item.title == entry.title and item.quote in _source_sentences(entry.content)
                for entry in entries
            ) for item in proposed
        ):
            # Keep the enclosing entry: even a complete sentence may be an
            # explicitly false example or depend on a preceding qualification.
            quotes = tuple(KnowledgeReplyQuote(entry.title, entry.content) for entry in entries
                if any(item.title == entry.title and item.quote in _source_sentences(entry.content) for item in proposed))
    if not quotes:
        # A failed refinement cannot revive the proposal's ungrounded free text.
        quotes = tuple(KnowledgeReplyQuote(entry.title, entry.content) for entry in entries)
    parts = []
    for item in dict.fromkeys(quotes):
        part = f'资料《{item.title}》写的是：「{item.quote}」'
        if sum(map(len, parts)) + len(part) > 5_000:
            parts.append('其余资料本轮未展开。')
            break
        parts.append(part)
    parts.append('资料没有说明的细节，我不能据此确定。')
    return '\n\n'.join(parts)


@dataclass(frozen=True)
class KnowledgeProposal:
    citation_ids: tuple[str, ...]


@dataclass(frozen=True)
class KnowledgeProviderResult:
    proposal: KnowledgeProposal
    experience_summary: str
    reply_text: str
    language: str


class KnowledgeProviderAdapter(ProviderAdapter):
    def __init__(self, *, provider: object) -> None:
        self._split = callable(getattr(provider, "propose", None)) and callable(
            getattr(provider, "reply", None)
        )
        if not self._split and not callable(getattr(provider, "analyze", None)):
            raise TypeError("provider must expose propose/reply or analyze")
        provider_id = getattr(provider, "provider_authority", M0_A_PROVIDER_AUTHORITY)
        if not isinstance(provider_id, str) or not provider_id:
            raise TypeError("provider_authority must be a non-empty string")
        self._provider = provider
        self.capabilities = ProviderCapabilities(
            provider_id=provider_id,
            model_id=str(getattr(provider, "model_id", type(provider).__name__)),
            local=bool(getattr(provider, "local", False)),
            structured_output_modes=(StructuredOutputMode.JSON_OBJECT,),
        )

    def invoke(self, task: ModelTask) -> ModelResult:
        if task.kind is ModelTaskKind.KNOWLEDGE_ANALYSIS and isinstance(
            task.payload,
            KnowledgeProviderRequest,
        ):
            result = (
                self._provider.propose(task.payload)
                if self._split
                else self._provider.analyze(task.payload)
            )
            return ModelResult(task.kind, result)
        if (
            task.kind is ModelTaskKind.KNOWLEDGE_REPLY
            and isinstance(task.payload, KnowledgeReplyRequest)
            and self._split
        ):
            return ModelResult(task.kind, self._provider.reply(task.payload))
        raise ModelGatewayFailure("knowledge-task-invalid")


class ControlledKnowledgeCognition(CognitionEngine):
    """No-write cognition seam; only ExperienceDomain may accept a citation."""

    adapter_version = "knowledge-citation-cognition-1.0"
    provider_authority = M0_A_PROVIDER_AUTHORITY
    experimental = True
    test_only = True

    def __init__(
        self,
        *,
        provider: object,
        entries: tuple[KnowledgeEntry, ...] = SEALED_KNOWLEDGE_ENTRIES,
    ) -> None:
        split = callable(getattr(provider, "propose", None)) and callable(
            getattr(provider, "reply", None)
        )
        if not split and not callable(getattr(provider, "analyze", None)):
            raise TypeError("provider must expose propose/reply or analyze")
        provider_authority = getattr(
            provider,
            "provider_authority",
            M0_A_PROVIDER_AUTHORITY,
        )
        if not isinstance(provider_authority, str) or not provider_authority:
            raise TypeError("provider_authority must be a non-empty string")
        self.provider_authority = provider_authority
        self.test_only = bool(getattr(provider, "test_only", True))
        self._gateway = ModelGateway(KnowledgeProviderAdapter(provider=provider))
        self._split = split
        if not isinstance(entries, tuple) or any(
            not isinstance(entry, KnowledgeEntry) for entry in entries
        ):
            raise TypeError("entries must be sealed KnowledgeEntry values")
        self._entries = entries

    def propose(
        self,
        *,
        plan: CyclePlan,
        context: CognitionRuntimeView,
        command: SubjectCommand,
        basis: ExperienceBasis,
    ) -> CognitiveProposal:
        candidates = select_knowledge_candidates(command.utterance, self._entries)
        request = KnowledgeProviderRequest(
            current_user_message=command.utterance,
            candidate_entries=candidates,
        )
        try:
            result = self._gateway.execute(
                ModelTask(ModelTaskKind.KNOWLEDGE_ANALYSIS, request)
            ).value
        except Exception as error:
            return self._failure(context, basis, command, "knowledge-provider-failed")
        candidate_ids = {entry.entry_id for entry in candidates}
        if (
            not isinstance(result, KnowledgeProviderResult)
            or not isinstance(result.proposal, KnowledgeProposal)
            or not isinstance(result.proposal.citation_ids, tuple)
            or any(entry_id not in candidate_ids for entry_id in result.proposal.citation_ids)
            or len(set(result.proposal.citation_ids)) != len(result.proposal.citation_ids)
            or not result.reply_text.strip()
            or result.language != command.language
        ):
            return self._failure(
                context,
                basis,
                command,
                "knowledge-provider-invalid-output",
            )
        citation_candidate: ExperienceChangeCandidate | None = None
        if result.proposal.citation_ids:
            citation_candidate = ExperienceChangeCandidate(
                candidate_id=str(
                    uuid5(
                        NAMESPACE_URL,
                        "knowledge:"
                        f"{basis.operation_id}:"
                        f"{':'.join(sorted(result.proposal.citation_ids))}",
                    )
                ),
                target_experience_id=basis.experience_id,
                evidence_refs=(basis.operation_id,),
                knowledge_citation_ids=result.proposal.citation_ids,
            )
        summary = result.experience_summary.strip() or (
            f"引用 {len(result.proposal.citation_ids)} 条封存知识条目。"
            if result.proposal.citation_ids
            else "本轮无适用的封存知识条目。"
        )
        selected_by_id = {entry.entry_id: entry for entry in candidates}
        selected_entries = tuple(
            KnowledgeReplyEntry(selected_by_id[entry_id].title, selected_by_id[entry_id].content)
            for entry_id in result.proposal.citation_ids
        )
        reply_result = None
        if self._split:
            if not isinstance(context.runtime_identity, RuntimeIdentityProjection):
                return self._failure(
                    context,
                    basis,
                    command,
                    "knowledge-provider-invalid-output",
                )
            try:
                reply_result = self._gateway.execute(
                    ModelTask(
                        ModelTaskKind.KNOWLEDGE_REPLY,
                        KnowledgeReplyRequest(
                            command.utterance,
                            selected_entries,
                            context.runtime_identity,
                        ),
                    )
                ).value
            except Exception:
                reply_result = None
        reply_text = render_source_reply(selected_entries,
            reply_result if isinstance(reply_result, KnowledgeReplyResult) and reply_result.language == command.language else None)
        activity = activity_boundary_reply(command.utterance)
        is_creative = False
        if activity is not None:
            reply_text = activity
        elif isinstance(reply_result, KnowledgeReplyResult) and reply_result.language == command.language and reply_result.reply_kind == 'creative':
            creative = contextual_reply(reply_result.reply_text, message=command.utterance, reply_kind='creative')
            if creative is not None and creative.startswith(CREATIVE_REPLY_PREFIX):
                is_creative = True
                reply_text = creative + ('\n引用仅作为创作背景。' if selected_entries else '')
        base = self._bounded_noop_proposal(
            context=context,
            basis=basis,
            experience_summary=summary,
            expression_candidate=ExpressionCandidate(
                text=reply_text,
                language=result.language,
                is_creative=is_creative,
            ),
        )
        experience_request = ExperienceAdjudicationRequest(
            basis=basis,
            current_state=ExperienceReadView(
                verified_prefix_digest=basis.verified_prefix_digest,
                memory_trace_refs=(),
            ),
            candidates=(citation_candidate,) if citation_candidate else (),
            knowledge_candidates=candidates,
        )
        return replace(
            base,
            impact_envelope=replace(
                base.impact_envelope,
                experience=experience_request,
            ),
        )

    def _failure(
        self,
        context: CognitionRuntimeView,
        basis: ExperienceBasis,
        command: SubjectCommand,
        code: str,
    ) -> CognitiveProposal:
        base = self._bounded_noop_proposal(
            context=context,
            basis=basis,
            experience_summary="Knowledge 本轮失败关闭。",
            expression_candidate=ExpressionCandidate(
                _NO_KNOWLEDGE_EXPRESSION,
                command.language,
            ),
        )
        return replace(
            base,
            impact_envelope=replace(
                base.impact_envelope,
                experience=ExperienceAdjudicationRequest(
                    basis=basis,
                    current_state=ExperienceReadView(
                        verified_prefix_digest=basis.verified_prefix_digest,
                        memory_trace_refs=(),
                    ),
                    candidates=(),
                    knowledge_failure_code=code,
                ),
            ),
        )

    @classmethod
    def for_profile(
        cls,
        profile: str,
        *,
        deepseek_transport: object | None = None,
        credential_ref: object | None = None,
    ) -> "ControlledKnowledgeCognition":
        if profile != "default":
            raise ValueError("Knowledge profile adapter is unavailable")
        from dynamic_subject_agent.deepseek import DeepSeekKnowledgeProvider

        return cls(
            provider=DeepSeekKnowledgeProvider(
                transport=deepseek_transport,
                credential_ref=credential_ref,
            )
        )


__all__ = [
    "ControlledKnowledgeCognition",
    "KnowledgeProviderAdapter",
    "KnowledgeProposal",
    "KnowledgeProviderRequest",
    "KnowledgeProviderResult",
    "KnowledgeReplyEntry",
    "KnowledgeReplyRequest",
    "KnowledgeReplyResult",
]
