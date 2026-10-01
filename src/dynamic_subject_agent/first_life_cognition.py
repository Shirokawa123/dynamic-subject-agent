"""Typed finite life decisions plus ordinary chat, with no legacy effects."""
from dataclasses import asdict, replace
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from dynamic_subject_agent.runtime import CognitionEngine, CognitionFailedClosed, ExpressionCandidate
from dynamic_subject_agent.timeline import PreAdmissionRejected
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind, ModelGatewayFailure
from dynamic_subject_agent.reply_review_diagnostics import REVIEW_DIAGNOSTIC_CODES
from dynamic_subject_agent.character_communication_plan import _validated_expression
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.first_life import (
    LIFE_AUTHORITY, LIFE_DORMANT_AUTHORITY, FirstLifeInput, LifeRecord, adjudicate_life, event_summary,
    CONTEXT_RESET_KIND, CONTEXT_RESET_RECEIPT,
)
from dynamic_subject_agent.first_life_projection import life_model_projection, life_chat_planning, life_chat_expression
from dynamic_subject_agent.first_life_authorization import LEGACY_RUNTIME_POLICY, ShareAuthorizationChanged, ChatAuthorization


class FirstLifeDormantCognition(CognitionEngine):
    adapter_version = "first-life-dormant-cognition-1"
    provider_authority = LIFE_DORMANT_AUTHORITY
    experimental = True
    test_only = False
    supports_first_life = True
    supports_subject_tasks = False
    supports_text_effects = False

    def preflight(self, *, context, command):
        raise PreAdmissionRejected("first-life-unavailable", "First-life serving is not assembled.")

    def propose(self, *, plan, context, command, basis):
        raise CognitionFailedClosed("first-life", "first-life-unavailable", "First-life serving is not assembled.")


class FirstLifeCognition(CognitionEngine):
    adapter_version = "first-life-cognition-1"
    provider_authority = LIFE_AUTHORITY
    experimental = True
    test_only = False
    supports_first_life = True
    supports_subject_tasks = False
    supports_text_effects = False

    def __init__(self, *, envelope=None, gateway=None, budget=None, history_preference=None, development_run=False, civil_day=None,
                 runtime_policy=LEGACY_RUNTIME_POLICY, share_authorization=None, share_guard=None, chat_authorization=None, chat_guard=None):
        self.envelope, self.gateway, self.budget = envelope, gateway, budget
        self.history_preference, self.development_run, self.civil_day = history_preference, development_run, civil_day
        self.runtime_policy, self.share_authorization, self.share_guard = runtime_policy, share_authorization, share_guard
        self.chat_authorization, self.chat_guard = chat_authorization, chat_guard
        from dynamic_subject_agent.first_life_reply_routes import LOCAL_REPLY_POLICIES, REPLY_POLICIES
        if runtime_policy not in (LEGACY_RUNTIME_POLICY, "first-life-relevance-2", "first-life-grounded-3", "first-life-followup-4", *REPLY_POLICIES):
            raise ValueError("unknown first-life runtime policy")
        if runtime_policy in LOCAL_REPLY_POLICIES and getattr(getattr(gateway, "capabilities", None), "local", None) is not True:
            raise ValueError("local-only reply policy cannot use a remote gateway")

    def preflight(self, *, context, command):
        if type(command) is FirstLifeInput:
            if command.input_kind in ("control", CONTEXT_RESET_KIND): return
        elif command.language != "zh" or len(command.utterance) > 1000:
            raise PreAdmissionRejected("first-life-message-invalid", "Chinese chat accepts at most 1000 characters.")
        if self.gateway is None: raise PreAdmissionRejected("first-life-unavailable", "First-life provider is not assembled.")

    def _call(self, plan, *, purpose, projection, civil_day, validator, authorization=None):
        if authorization is None:
            return self._call_authorized(plan, purpose=purpose, projection=projection, civil_day=civil_day, validator=validator)
        guard = self.chat_guard if type(authorization) is ChatAuthorization else self.share_guard
        purpose_prefix = "first-life-chat-" if type(authorization) is ChatAuthorization else "first-life-share-"
        try:
            with guard(authorization):
                result = self._call_authorized(plan, purpose=purpose, projection=projection, civil_day=civil_day, validator=validator)
            with guard(authorization):
                return result
        except CognitionFailedClosed:
            raise
        except ShareAuthorizationChanged:
            raise CognitionFailedClosed("history", purpose_prefix + "history-changed", "Disclosure authorization was revoked after preparation.") from None
        except Exception:
            raise CognitionFailedClosed("history", purpose_prefix + "history-unverified", "Disclosure authorization became unavailable.") from None

    def _call_authorized(self, plan, *, purpose, projection, civil_day, validator):
        from dynamic_subject_agent.first_life_reply_routes import LOCAL_REPLY_POLICIES, REPLY_POLICIES, WHOLE_REPLY_POLICIES, PLANNED_REPLY_POLICIES
        if (self.runtime_policy in LOCAL_REPLY_POLICIES
            and getattr(getattr(self.gateway, "capabilities", None), "local", None) is not True):
            raise CognitionFailedClosed(purpose, "first-life-local-route-required", "This reply route is local-only; no allowance was claimed.")
        stage = "planning" if purpose in ("life-decision", "chat-planning") else "expression"
        identity = sha256(plan.operation_ref.authority_scope_id.encode()).hexdigest()
        operation = sha256((plan.operation_ref.operation_id + ":" + plan.attempt_id).encode()).hexdigest()
        request = sha256(canonical_json(asdict(projection)).encode()).hexdigest()
        try:
            self.budget.claim_life(identity, operation, stage, request, purpose=purpose, civil_day=civil_day, development_run=self.development_run)
        except Exception:
            code = "first-life-share-not-attempted" if purpose == "life-share" else "first-life-budget-unavailable"
            raise CognitionFailedClosed("first-life-budget", code, "No verified quota or new stage claim is available.") from None
        kinds = {"life-decision": ModelTaskKind.CHARACTER_FIRST_LIFE_DECISION, "life-share": ModelTaskKind.CHARACTER_FIRST_LIFE_SHARE,
                 "chat-planning": ModelTaskKind.CHARACTER_COMMUNICATION_PLAN, "chat-expression": ModelTaskKind.CHARACTER_COMMUNICATION_EXPRESSION}
        if self.runtime_policy in WHOLE_REPLY_POLICIES:
            kinds["chat-expression"] = ModelTaskKind.CHARACTER_FIRST_LIFE_WHOLE_REPLY
        elif self.runtime_policy in PLANNED_REPLY_POLICIES:
            kinds["chat-expression"] = ModelTaskKind.CHARACTER_FIRST_LIFE_FACT_EXPRESSION
        try:
            value = self.gateway.execute(ModelTask(kinds[purpose], projection)).value
            try: validator(value)
            except Exception: raise ModelGatewayFailure("structured-choice-invalid") from None
        except Exception as error:
            allowed = (REVIEW_DIAGNOSTIC_CODES - {"review-schema", "review-quote", "review-label"}) | {"character-credential-unavailable", "structured-choice-invalid"}
            code = error.code if isinstance(error, ModelGatewayFailure) and error.code in allowed else "provider-failed"
            status = "unavailable" if code == "character-credential-unavailable" else "unknown" if code in ("transport-timeout", "transport-delivery-ambiguous") else "failed-closed"
            try: self.budget.record(identity, operation, stage, status=status)
            except Exception: code = "audit-failed"
            prefix = "first-life-share-" if purpose == "life-share" else "first-life-"
            raise CognitionFailedClosed(purpose, prefix + code, "A bounded stage did not complete safely; no story consequence was committed.") from None
        try: self.budget.record(identity, operation, stage, status="complete", output_digest=sha256(canonical_json(value).encode()).hexdigest())
        except Exception:
            raise CognitionFailedClosed(purpose, "first-life-share-audit-failed" if purpose == "life-share" else "first-life-audit-failed", "Delivery could not be audited safely.") from None
        return value

    @staticmethod
    def _share_value(value):
        if (type(value) is not dict or set(value) != {"share", "reply_text", "language"} or type(value["share"]) is not bool
            or value["language"] != "zh" or not isinstance(value["reply_text"], str)
            or (value["share"] and (not value["reply_text"].strip() or len(value["reply_text"]) > 400))
            or (not value["share"] and value["reply_text"] != "")):
            raise ValueError("exact bounded share choice required")
        return value

    def propose(self, *, plan, context, command, basis):
        try:
            current = context.load_first_life()
        except Exception:
            raise CognitionFailedClosed("first-life", "first-life-basis-unverified", "Life state could not be verified.") from None
        if type(command) is not FirstLifeInput:
            return self._chat(plan, context, command, basis, current)
        before = current.record
        if command.input_kind == CONTEXT_RESET_KIND:
            record = replace(before, kind=CONTEXT_RESET_KIND, reason_code="", differences=(), event_id="", summary="", simulated=False,
                disclosed_event_id="", share_id="", share_text="", considered_event_id="")
            return self._proposal(context, basis, record, CONTEXT_RESET_RECEIPT)
        if command.input_kind == "control":
            record = replace(before, kind="control", reason_code="", differences=(), event_id="", summary="", simulated=False,
                paused=before.paused if command.paused is None else command.paused,
                sharing_enabled=before.sharing_enabled if command.sharing_enabled is None else command.sharing_enabled,
                disclosed_event_id="", share_id="", share_text="", considered_event_id="")
            return self._proposal(context, basis, record, "系统：生活控制已提交。")
        if current.technical_problem:
            raise CognitionFailedClosed("first-life", "first-life-needs-attention", "A prior technical failure requires explicit control/resume.")
        if command.input_kind == "advance":
            if before.paused or before.phase in ("kept", "deferred"):
                raise CognitionFailedClosed("first-life", "first-life-no-boundary", "No new life decision is permitted.")
            projection = life_model_projection(self.envelope, context.runtime_identity, current)
            value = self._call(plan, purpose="life-decision", projection=projection, civil_day=command.civil_day,
                validator=lambda value: adjudicate_life(value, phase=before.phase, current_plan=before.plan))
            action, phase, creative, reason, differences = adjudicate_life(value, phase=before.phase, current_plan=before.plan)
            revision = before.revision + (action in ("start", "revise"))
            event_id = str(uuid5(NAMESPACE_URL, "first-life-event:" + plan.operation_ref.operation_id))
            record = LifeRecord("advance", phase, revision, creative, reason, differences, event_id,
                event_summary(action, revision, differences), before.virtual_minutes + 1, before.paused, before.sharing_enabled,
                command.trigger == "simulation")
            return self._proposal(context, basis, record, "系统：已提交一项构图文字活动变化。")
        event = next((event for event in current.events if event.event_id == command.target_event_id), None)
        if (event is None or not current.has_dialogue or not before.sharing_enabled or current.unanswered_share
            or event.event_id in current.disclosed_event_ids or event.event_id in current.considered_event_ids):
            raise CognitionFailedClosed("first-life-share", "first-life-share-not-attempted", "This event is not currently eligible for sharing.")
        authorization = None
        validator = self._share_value
        if self.runtime_policy != LEGACY_RUNTIME_POLICY:
            from dynamic_subject_agent.first_life_relevance import share_model_projection, validate_share_candidate
            try:
                authorization = self.share_authorization()
                dialogue = context.load_character_dialogue(authorization.history_enabled)
                projection = share_model_projection(self.envelope, context.runtime_identity, current, dialogue,
                    authorization.history_enabled, target_event=event)
            except Exception:
                raise CognitionFailedClosed("history", "first-life-share-history-unverified", "Share history or authorization is unavailable.") from None
            validator = lambda value: validate_share_candidate(projection, value)
        else:
            projection = life_model_projection(self.envelope, context.runtime_identity, current, share=True, target_event=event)
        value = self._call(plan, purpose="life-share", projection=projection, civil_day=command.civil_day,
            validator=validator, authorization=authorization)
        base = replace(before, kind="share" if value["share"] else "share-declined", reason_code="", differences=(), event_id="", summary="", simulated=False,
            disclosed_event_id=event.event_id if value["share"] else "", share_id="", share_text="", considered_event_id="" if value["share"] else event.event_id)
        record = replace(base, share_id=str(uuid5(NAMESPACE_URL, "first-life-share:" + plan.operation_ref.operation_id)), share_text=value["reply_text"]) if value["share"] else base
        return replace(self._proposal(context, basis, record, value["reply_text"] if value["share"] else "系统：本次不分享，该事件已考虑。"),
            share_authorization=authorization)

    def _chat(self, plan, context, command, basis, current):
        from dynamic_subject_agent.first_life_dialogue import is_first_life_dialogue_control
        from dynamic_subject_agent.first_life_reply_routes import (
            LOCAL_REPLY_POLICIES, REPLY_POLICIES, WHOLE_REPLY_POLICIES, PLANNED_REPLY_POLICIES,
            whole_reply_projection, fact_expression_projection, validate_whole_reply,
        )
        if is_first_life_dialogue_control(command.utterance):
            raise CognitionFailedClosed("history", "first-life-history-unverified",
                "A control request needs local resolution before model generation.")
        planning_fn, expression_fn = life_chat_planning, life_chat_expression
        if self.runtime_policy == "first-life-relevance-2":
            from dynamic_subject_agent.first_life_relevance import life_chat_planning as planning_fn, life_chat_expression as expression_fn
        elif self.runtime_policy == "first-life-grounded-3":
            from dynamic_subject_agent.first_life_grounded import life_chat_planning as planning_fn, life_chat_expression as expression_fn
        elif self.runtime_policy in ("first-life-followup-4", *REPLY_POLICIES):
            from dynamic_subject_agent.first_life_followup import life_chat_planning as planning_fn, life_chat_expression as expression_fn
            if self.runtime_policy in PLANNED_REPLY_POLICIES:
                expression_fn = fact_expression_projection
        authorization = None
        try:
            remaining = self.budget.counts()[2]
            development = self.budget.life_counts(self.civil_day(), development_run=self.development_run)[2]
            required = 1 if self.runtime_policy in WHOLE_REPLY_POLICIES else 2
            if (remaining is not None and remaining < required
                or development is not None and development < required): raise ValueError("reply allowance unavailable")
        except Exception:
            raise CognitionFailedClosed("budget", "first-life-budget-unavailable", "No verified allowance is available for this reply route.") from None
        try:
            if self.runtime_policy in ("first-life-followup-4", *REPLY_POLICIES):
                authorization = self.chat_authorization()
                if type(authorization) is not ChatAuthorization or authorization.runtime_policy != self.runtime_policy:
                    raise ValueError("exact same-route chat authorization required")
                enabled = authorization.history_enabled
                dialogue = context.load_first_life_followup(enabled)
            else:
                enabled = self.history_preference()
                dialogue = context.load_character_dialogue(enabled)
            planning, event = planning_fn(self.envelope, context.runtime_identity, command.utterance, dialogue, enabled, current)
            day = self.civil_day()
        except Exception:
            raise CognitionFailedClosed("history", "first-life-history-unverified", "History or sealed material is unavailable.") from None
        if self.runtime_policy in WHOLE_REPLY_POLICIES:
            expression = whole_reply_projection(planning)
            output = self._call(plan, purpose="chat-expression", projection=expression, civil_day=day,
                validator=lambda value: validate_whole_reply(expression, value), authorization=authorization)
            text, used = validate_whole_reply(expression, output)
        else:
            value = self._call(plan, purpose="chat-planning", projection=planning, civil_day=day,
                validator=lambda value: expression_fn(planning, value), authorization=authorization)
            if self.history_preference() != enabled:
                raise CognitionFailedClosed("history", "first-life-history-changed", "History preference changed before expression.")
            expression, used = expression_fn(planning, value)
            output = self._call(plan, purpose="chat-expression", projection=expression, civil_day=self.civil_day(), validator=_validated_expression, authorization=authorization)
            text = _validated_expression(output)
        record = None
        if used and event is not None:
            record = replace(current.record, kind="disclosure", reason_code="", differences=(), event_id="", summary="", simulated=False,
                disclosed_event_id=event.event_id, share_id="", share_text="", considered_event_id="")
        return replace(self._proposal(context, basis, record, text), chat_authorization=authorization)

    def _proposal(self, context, basis, record, text):
        proposal = self._bounded_noop_proposal(context=context, basis=basis,
            experience_summary="有限系统活动/交流已提交；创作文字及台词不改起点知识、人格或原作剧情。",
            expression_candidate=ExpressionCandidate(text, "zh"))
        return replace(proposal, life_record=record)
