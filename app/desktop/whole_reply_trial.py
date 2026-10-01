"""Thin HTTP presentation for the two already-authorized synthetic A branches."""
from threading import RLock

from character_chat import create_server
from first_life import FirstLifeAdapter


APPLICATION_ID = "whole-reply-fixed-material-trial-s118"


class TrialConversationAdapter(FirstLifeAdapter):
    def __init__(self, product):
        self._request_ids = {}
        super().__init__(product)

    def snapshot(self):
        state = super().snapshot()
        return dict(state, pending_request_id=self._request_ids.get(state.get("pending_handle")))

    def send(self, payload):
        result = super().send(payload)
        if result.get("pending"):
            self._request_ids[result["pending"]] = payload["request_id"]
        return dict(result, request_id=payload["request_id"])

    def poll(self, payload):
        result = super().poll(payload)
        return dict(result, request_id=self._request_ids.get(payload["handle"]))

    def _result(self, response, *, handle=None):
        if response.status.value == "pending" and response.operation_ref is not None and handle is None:
            handle = next((key for key, ref in self.pending.items() if ref == response.operation_ref), None)
        if response.status.value in ("terminal", "failed-closed"):
            ref = response.operation_ref if response.operation_ref is not None else self.pending.get(handle)
            if ref is not None:
                self.inflight.difference_update(key for key, value in self.pending.items() if value == ref)
        result = super()._result(response, handle=handle)
        code = getattr(response.projection, "failure_code", None)
        messages = {
            "first-life-response-content-empty":"模型返回了空白，这轮没有形成可提交的回复。所选消息保留。",
            "first-life-response-content-json":"模型回复未通过格式校验，这轮未提交。所选消息保留。",
            "first-life-character-credential-unavailable":"无法使用已配置的模型凭据。所选消息保留。",
            "first-life-transport-timeout":"回复交付尚未确认。请先检查现有记录，所选消息和原请求保留。",
            "first-life-transport-delivery-ambiguous":"回复交付尚未确认。请先检查现有记录，所选消息和原请求保留。",
        }
        if not result["ok"] and code in messages:
            result["message"] = messages[code]
        return result


class WholeReplyTrialAdapter:
    def __init__(self, products, *, choices, scope_key, reopen):
        if set(products) != set(choices) or not callable(reopen):
            raise ValueError("exact trial presentation required")
        self.lock = RLock()
        self.adapters = {key:TrialConversationAdapter(product) for key, product in products.items()}
        self.choices, self.scope_key, self.reopen = choices, scope_key, reopen

    def snapshot(self):
        with self.lock:
            return dict(scope_key=self.scope_key, mode="approved-test-messages",
                cases=[dict(case_id=key, title=spec["title"], choices=spec["choices"],
                    state=self.adapters[key].snapshot()) for key, spec in self.choices.items()])

    def _case(self, payload, fields):
        if type(payload) is not dict or set(payload) != fields | {"case_id"}:
            raise ValueError("invalid-request")
        case = payload["case_id"]
        if type(case) is not str or case not in self.adapters:
            raise ValueError("invalid-request")
        return case, self.adapters[case], {k:v for k,v in payload.items() if k != "case_id"}

    @staticmethod
    def _wrap(case, result):
        return dict(result, case_id=case)

    def send(self, payload):
        with self.lock:
            case, adapter, data = self._case(payload, {"choice_id", "request_id"})
            choice = next((row for row in self.choices[case]["choices"] if row["id"] == data["choice_id"]), None)
            if choice is None:
                raise ValueError("invalid-request")
            # Only exact approved text is admitted. Arbitrary browser text is not
            # written to Timeline, sent to a model, or substituted into a choice.
            return self._wrap(case, adapter.send(dict(text=choice["text"], request_id=data["request_id"])))

    def poll(self, payload):
        with self.lock:
            case, adapter, data = self._case(payload, {"handle"})
            return self._wrap(case, adapter.poll(data))

    def history(self, payload):
        with self.lock:
            case, adapter, data = self._case(payload, {"enabled"})
            return self._wrap(case, adapter.set_history(data))

    def reset_context(self, payload):
        with self.lock:
            case, adapter, data = self._case(payload, {"request_id", "confirmed"})
            return self._wrap(case, adapter.reset_context(data))

    def reload(self, payload):
        with self.lock:
            case, adapter, data = self._case(payload, set())
            if adapter.inflight:
                return self._wrap(case, dict(ok=False, message="这一轮仍在处理，结束后再重开。", state=adapter.snapshot()))
            # The composition owns close/open. No Provider or store is assembled
            # by the HTTP adapter, and reloading never submits a message.
            product = self.reopen(case)
            self.adapters[case] = TrialConversationAdapter(product)
            return self._wrap(case, dict(ok=True, message="已从本地记录重新打开。", state=self.adapters[case].snapshot()))


def trial_server(products, *, choices, scope_key, reopen, port=0):
    adapter = WholeReplyTrialAdapter(products, choices=choices, scope_key=scope_key, reopen=reopen)
    return create_server(None, port=port, adapter=adapter, page_name="whole_reply_trial.html",
        application_id=APPLICATION_ID, post_routes={"/send":adapter.send, "/operation":adapter.poll,
            "/history":adapter.history, "/context-reset":adapter.reset_context, "/reload":adapter.reload})
