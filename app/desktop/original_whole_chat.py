"""Thin async loopback presentation for the explicitly approved whole character chat."""
from dataclasses import asdict
from threading import RLock
from uuid import UUID, uuid4
from hashlib import sha256

from character_chat import create_server
from dynamic_subject_agent.application import (ApplicationQuery, ApplicationQueryKind,
    SubjectRequestLookupRequest, SubjectRequestLookupStatus)
from dynamic_subject_agent.timeline import SubjectCommand


APPLICATION_ID = "original-character-whole-chat-s127"


class OriginalWholeChatAdapter:
    def __init__(self, product, *, reopen):
        if not callable(reopen):
            raise ValueError("composition-owned reopen required")
        self.product, self.reopen = product, reopen
        self.lock = RLock()
        self.pending, self.request_ids, self.inflight = {}, {}, set()
        self.request_texts = {}
        self.last_snapshot = None

    def snapshot(self):
        with self.lock:
            if self.inflight and self.last_snapshot is not None:
                handle = next(iter(self.inflight))
                return dict(self.last_snapshot, presentation_pending=True, pending_handle=handle,
                    pending_request_id=self.request_ids.get(handle))
            state = self.product.application.reviewed_character_chat_status()
            history = self.product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
                self.product.profile_id, self.product.timeline_id))
            turns = [] if history.status.value != "available" or history.projection is None else [dict(user_text=row.user_text, assistant_text=row.assistant_text)
                for row in history.projection.turns]
            scope_key = sha256((self.product.profile_id + ":" + self.product.timeline_id).encode()).hexdigest()
            result = dict(scope_key=scope_key, character=asdict(state), history=dict(status=history.status.value, turns=turns),
                presentation_pending=False, pending_handle=None, pending_request_id=None)
            if history.status.value == "available" and state.status == "active":
                self.last_snapshot = result
            return result

    def _result(self, response, handle, request_id, *, request_text=None, verified=False):
        status = response.status.value
        pending = status == "pending" and response.operation_ref is not None
        settled = status in ("terminal", "failed-closed", "unavailable")
        if pending:
            self.pending[handle] = response.operation_ref
            self.request_ids[handle] = request_id
            if request_text is not None:
                self.request_texts[handle] = request_text
            self.inflight.add(handle)
        else:
            ref = response.operation_ref if response.operation_ref is not None else self.pending.get(handle)
            self.inflight.difference_update(key for key, value in self.pending.items() if value == ref)
            self.inflight.discard(handle)
        projection = response.projection
        ok = response.status.value == "terminal" and projection is not None and not projection.failure_code and bool(projection.expression_text)
        code = getattr(projection, "failure_code", None)
        message = "" if ok or pending else (
            "这一轮已结束，没有形成可提交的回复；草稿保留，可以明确重新发送。" if settled
            else "回复交付尚未确认，草稿与原请求保留；请先刷新核对，不会自动重发。")
        if code and "history" in code:
            message = "本轮的上下文范围或完整性未能确认，已停止生成；现有记录和草稿保留。"
        return dict(ok=ok or pending, pending=handle if pending else None, settled=settled, request_id=request_id,
            request_verified=verified, can_abandon=verified and status == "unknown"
                and response.operation_ref is not None and projection is not None,
            message=message, state=self.snapshot())

    @staticmethod
    def _validate_message(payload):
        if (type(payload) is not dict or set(payload) != {"text", "request_id"}
            or type(payload["text"]) is not str or not payload["text"].strip() or len(payload["text"]) > 1000
            or "\x00" in payload["text"] or type(payload["request_id"]) is not str
            or str(UUID(payload["request_id"])) != payload["request_id"]):
            raise ValueError("invalid-request")

    def _command(self, text):
        return SubjectCommand.contribute_utterance(target_profile_id=self.product.profile_id,
            target_timeline_id=self.product.timeline_id, declared_intent="ask-collaborator-status",
            utterance=text, language="zh", provenance="project-original")

    def send(self, payload):
        self._validate_message(payload)
        with self.lock:
            if self.last_snapshot is None:
                self.snapshot()
            command = self._command(payload["text"])
            response = self.product.application.submit(command, idempotency_key="original-whole-" + payload["request_id"])
            handle = next((key for key,value in self.pending.items() if value == response.operation_ref), str(uuid4()))
            return self._result(response, handle, payload["request_id"], request_text=payload["text"])

    def lookup(self, payload):
        self._validate_message(payload)
        with self.lock:
            query = self.product.application.lookup_subject_request(SubjectRequestLookupRequest(
                command=self._command(payload["text"]), idempotency_key="original-whole-" + payload["request_id"]))
            if query.query_status is SubjectRequestLookupStatus.FOUND and query.operation is not None:
                handle = next((key for key, value in self.pending.items() if value == query.operation.operation_ref), str(uuid4()))
                result = self._result(query.operation, handle, payload["request_id"],
                    request_text=payload["text"], verified=True)
                return dict(result, query_status=query.query_status.value)
            not_found = query.query_status is SubjectRequestLookupStatus.NOT_FOUND
            message = ("当前本地交流没有找到这个原请求；草稿保留，只有明确发送才会开始新轮。" if not_found
                else "原请求结果尚无法核实；草稿与原请求保留，不会重新发送。")
            if getattr(query.problem, "code", None) == "subject-request-payload-mismatch":
                message = "原请求标识与保存的原消息不匹配；没有读取别的结果，草稿与原请求保留。"
            return dict(ok=False, pending=None, settled=False, request_id=payload["request_id"],
                query_status=query.query_status.value, request_verified=not_found, can_abandon=False,
                message=message, state=self.snapshot())

    def poll(self, payload):
        if (type(payload) is not dict or set(payload) != {"handle"}
            or type(payload["handle"]) is not str):
            raise ValueError("unknown-operation")
        with self.lock:
            handle = payload["handle"]
            if handle not in self.pending:
                raise ValueError("unknown-operation")
            if handle not in self.request_texts:
                raise ValueError("original-request-unavailable")
            return self.lookup(dict(text=self.request_texts[handle], request_id=self.request_ids[handle]))

    def set_history(self, payload):
        if type(payload) is not dict or set(payload) != {"enabled"} or type(payload["enabled"]) is not bool:
            raise ValueError("invalid-request")
        with self.lock:
            result = self.product.application.set_reviewed_character_history(payload["enabled"])
            ok = result.status == "active" and result.history_enabled == payload["enabled"]
            if ok and self.last_snapshot is not None:
                self.last_snapshot = dict(self.last_snapshot, character=asdict(result))
            return dict(ok=ok,
                state=self.snapshot(), message="")

    def reload(self, payload):
        if type(payload) is not dict or payload != {}:
            raise ValueError("invalid-request")
        with self.lock:
            if self.inflight:
                return dict(ok=False, message="这轮仍在处理，请等待结果后重开。", state=self.snapshot())
            self.product = self.reopen()
            self.pending.clear()
            self.request_ids.clear()
            self.request_texts.clear()
            return dict(ok=True, message="已从本地记录重新打开；草稿未发送。", state=self.snapshot())


def original_whole_server(product, *, reopen, port=0):
    adapter = OriginalWholeChatAdapter(product, reopen=reopen)
    return create_server(None, port=port, adapter=adapter, page_name="original_whole_chat.html",
        application_id=APPLICATION_ID, post_routes={"/send":adapter.send, "/operation":adapter.poll,
            "/request-result":adapter.lookup,
            "/history":adapter.set_history, "/reload":adapter.reload})
