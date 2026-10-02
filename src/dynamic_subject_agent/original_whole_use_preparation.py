"""Pure author review of an existing definition; no task, sender or runtime opening."""
from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
import re

from dynamic_subject_agent.character_chat_context import MAX_KNOWLEDGE_CHARS, MAX_RELATED_UNITS, knowledge_chars, prepare_context
from dynamic_subject_agent.original_whole_chat import WHOLE_USE_POLICY
from dynamic_subject_agent.character_communication_trial_provider import communication_protocol
from dynamic_subject_agent.character_identity_preparation import CharacterIdentityPreparationView
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.reviewed_character_chat import sealed_model
from dynamic_subject_agent.reviewed_character_definition import validate_character_preparation
from dynamic_subject_agent.runtime_identity import RuntimeIdentityProjection


REVIEW_VERSION = "original-character-whole-use-review-s126-1"
SCOPE_VERSION = "original-character-whole-use-proposal-s126-1"
SYNTHETIC_MESSAGE = "你好，想和你聊聊绘画，你现在想聊什么？"


@dataclass(frozen=True)
class OriginalWholeUsePreparationRequest:
    package_path: Path
    expected_definition_basis: str
    expected_runtime_asset_sha: str
    expected_persona_digest: str
    subject_id: str
    anchor_id: str


@dataclass(frozen=True)
class OriginalWholeUsePreparationView:
    status: str
    code: str = ""
    version: str = REVIEW_VERSION
    definition_basis: str = ""
    runtime_asset_sha: str = ""
    persona_digest: str = ""
    subject_id: str = ""
    anchor_id: str = ""
    eligible_count: int = 0
    personality_count: int = 0
    core_count: int = 0
    related_count: int = 0
    selected_knowledge_chars: int = 0
    selected_material_sha256: str = ""
    proposed_scope_json: str = ""
    synthetic_example_json: str = ""
    scope_digest: str = ""
    review_basis: str = ""
    local_only: bool = True
    remote_use_authorized: bool = False
    execution_ready: bool = False
    rights_confirmed: bool = False
    use_confirmed: bool = False
    semantic_quality: str = "not-evaluated-no-model-call"
    approval_status: str = "awaiting-exact-whole-use-approval"


def _digest(value):
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _valid_request(request):
    if type(request) is not OriginalWholeUsePreparationRequest or not isinstance(request.package_path, Path) or not request.package_path.is_absolute():
        return False
    return (all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None for value in (
        request.expected_definition_basis, request.expected_runtime_asset_sha, request.expected_persona_digest))
        and all(isinstance(value, str) and value.strip() == value and 0 < len(value) <= 120
            and not any(char in value for char in ("\x00", "\n", "\r")) for value in (request.subject_id, request.anchor_id)))


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate-json-property")
        result[key] = value
    return result


def _synthetic_example():
    """Field illustration only: every character sentence below is newly synthetic."""
    return dict(example_kind="synthetic-field-example-not-a-model-task", actual_character_material_included=False,
        turn=dict(current_message=SYNTHETIC_MESSAGE, history_enabled=True, has_prior_committed_exchange=False),
        background=dict(runtime_identity=dict(subject_name="合成示例人物", subject_identity="我在练习静物画。", canon_start="这次新写的合成示例起点。"),
            character_core=[dict(dimension="core", content="我喜欢比较不同的画面布局。", kind="fact", basis="direct", event_scope="before", knowledge_scope="before")],
            self_knowledge=[], personality=[dict(title="合成解释", interpretation="可对构图取舍感兴趣。", when="谈论画面时", choice="可以比较方案", expression="说明本次想法", limits="不补造既往习惯", basis="author-interpretation", support_includes_belief=False)],
            stage_description="合成示例的初次交流。", encounter=["系统按兴趣推荐联系人，用户主动发送消息。"],
            disclosure=["知情与愿意透露分开。"]),
        exchange=[], evidence=dict(current_activity=None, current_plan=None, related_event=None))


def _scope():
    return dict(version=SCOPE_VERSION, proposal_only=True, local_only=True, remote_use_authorized=False,
        purpose="generate-one-whole-character-reply", source_kind="reviewed-fiction-derived", definition_source_use="private-character-chat",
        destination="https://api.deepseek.com/chat/completions",
        provider="deepseek", model=communication_protocol("thinking-high", "low")["model"],
        credential_use="existing-Windows-Credential-Manager-slot-HTTPS-Bearer-only",
        input_fields=dict(turn=dict(current_message=dict(max_chars=1000, source="user-explicitly-submitted-in-this-future-entry"),
                history_enabled="boolean", has_prior_committed_exchange="verified-existence-only-no-trust-or-time-inference"),
            background=dict(runtime_identity=["subject_name", "subject_identity", "canon_start"],
                character_core="verified-sealed-core-with-kind-basis-event_scope-knowledge_scope",
                self_knowledge=dict(organized_max_related_units=MAX_RELATED_UNITS, flat_max_items=1000, combined_core_and_related_json_max_chars=MAX_KNOWLEDGE_CHARS,
                    selector="existing-sealed_model-and-prepare_context-auto"),
                personality=dict(max_items=8, json_max_chars=12000, fields=["title", "interpretation", "when", "choice", "expression", "limits", "basis", "support_includes_belief"]),
                stage_description=dict(max_chars=500), encounter="existing-approved-cross-world-interest-recommendation",
                disclosure="verified-knowledge-is-not-automatic-disclosure"),
            exchange=dict(source="same-identity-verified-canonical-complete-committed-turns-only", max_complete_turns=2,
                max_total_chars=4000, fields=["user_text", "assistant_text"], history_off="empty-array",
                no_partial_turn_or_older_replacement=True),
            evidence=dict(current_activity=None, current_plan=None, related_event=None)),
        output=dict(exact_fields=["reply_text", "language"], reply_text=dict(nonblank=True, max_chars=1200, no_nul=True), language="zh"),
        protocol=dict(thinking="enabled-high", max_completion_tokens=4096, timeout_seconds=30, max_requests_per_turn=1,
            automatic_retries=0, call_limit=None, required_audit="purpose-stage-status-and-usage-metadata-only"),
        local_retention="submitted-messages-and-committed-replies-only-in-existing-canonical-Timeline-no-second-chat-store",
        policy=WHOLE_USE_POLICY,
        excluded=["S1-and-assistant-origin-share", "life-generation", "life-events", "full-source-or-quotes", "evidence-and-database-IDs",
            "private-old-chat-for-this-preparation", "other-identities", "unsent-drafts", "failed-incomplete-replies", "full-history",
            "timestamps", "raw-reasoning", "credentials", "attachments", "cloud-deployment", "notifications", "persona-rewrite", "migration"],
        implementation_status="review-only-no-runtime-route-no-provider-qualification",
        prior_approval="S103-S108-definition-and-old-two-stage-uses-remain-separate; synthetic-Xiaolin-scope-cannot-authorize-this-use")


def _selected_material(envelope):
    model = sealed_model(envelope)
    context = prepare_context(model, SYNTHETIC_MESSAGE)
    if context.status != "previewed":
        return context, None, (), ()
    core = tuple(item for item in context.self_knowledge if item.dimension == "core") if model.chat_organization is not None else tuple(
        item for item in context.self_knowledge if item.dimension == "identity")
    if not core:
        raise ValueError("review-core-missing")
    related = tuple(item for item in context.self_knowledge if item not in core)
    identity = RuntimeIdentityProjection(envelope["runtime_asset"]["subject"]["name"],
        envelope["genesis_content"]["subject_identity"], envelope["genesis_content"]["canon_start"])
    # Only hash this real-character projection. It never enters the returned review.
    material = dict(turn=dict(current_message=SYNTHETIC_MESSAGE, history_enabled=True, has_prior_committed_exchange=False),
        background=dict(runtime_identity=asdict(identity), character_core=[asdict(item) for item in core],
            self_knowledge=[asdict(item) for item in related], personality=envelope["runtime_asset"]["personality"],
            stage_description=context.stage_description,
            encounter=["社交软件的文字私信", context.encounter.world_context,
                "系统按兴趣推荐联系人，本轮由用户主动发送消息。", "初识；不据此推断信任、亲密或时间推进。"],
            disclosure=list(context.disclosure)), exchange=[], evidence=dict(current_activity=None, current_plan=None, related_event=None))
    if len(canonical_json(material).encode("utf-8")) > 65536:
        raise ValueError("review-selected-material-too-large")
    return context, material, core, related


def prepare_original_whole_use(request):
    if not _valid_request(request):
        return OriginalWholeUsePreparationView("rejected", "typed-exact-whole-use-request-required")
    try:
        with request.package_path.open("rb") as stream:
            raw = stream.read(4_000_001)
        if len(raw) > 4_000_000:
            raise ValueError("review-package-too-large")
        content = raw.decode("utf-8")
        # Unambiguous parsing at the new boundary; existing canonical basis remains unchanged.
        package = json.loads(content, object_pairs_hook=_unique_object)
        if type(package) is not dict or set(package) != {field.name for field in fields(CharacterIdentityPreparationView)}:
            raise ValueError("review-package-shape-invalid")
        if any(package[key] is not None for key in ("source_request", "save_request", "freeze_request")):
            raise ValueError("review-package-command-not-allowed")
        json.loads(package["runtime_asset_json"], object_pairs_hook=_unique_object)
        envelope = validate_character_preparation(content, request.expected_definition_basis)
        asset = envelope["runtime_asset"]
        if (envelope["runtime_asset_sha"] != request.expected_runtime_asset_sha
                or asset["persona_digest"] != request.expected_persona_digest
                or asset["subject"]["subject_id"] != request.subject_id or asset["anchor"]["anchor_id"] != request.anchor_id):
            raise ValueError("review-exact-object-mismatch")
        context, material, core, related = _selected_material(envelope)
        if material is None:
            return OriginalWholeUsePreparationView(context.status, context.code)
        scope, example = _scope(), _synthetic_example()
        scope_digest, material_sha = _digest(scope), _digest(material)
        basis = _digest(dict(version=REVIEW_VERSION, definition_basis=envelope["definition_basis"],
            runtime_asset_sha=envelope["runtime_asset_sha"], persona_digest=asset["persona_digest"],
            subject_id=request.subject_id, anchor_id=request.anchor_id, scope_digest=scope_digest,
            selected_material_sha256=material_sha, synthetic_example=example))
        return OriginalWholeUsePreparationView("previewed", definition_basis=envelope["definition_basis"],
            runtime_asset_sha=envelope["runtime_asset_sha"], persona_digest=asset["persona_digest"],
            subject_id=request.subject_id, anchor_id=request.anchor_id, eligible_count=len(asset["eligible"]),
            personality_count=len(asset["personality"]), core_count=len(core), related_count=len(related),
            selected_knowledge_chars=knowledge_chars(context.self_knowledge), selected_material_sha256=material_sha,
            proposed_scope_json=canonical_json(scope), synthetic_example_json=canonical_json(example),
            scope_digest=scope_digest, review_basis=basis)
    except FileNotFoundError:
        return OriginalWholeUsePreparationView("unavailable", "whole-use-package-missing")
    except OSError:
        return OriginalWholeUsePreparationView("unavailable", "whole-use-package-unavailable")
    except Exception:
        return OriginalWholeUsePreparationView("failed-closed", "whole-use-preparation-invalid")
