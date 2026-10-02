"""Thin HTTP presentation for the separately authorized S119 free-input branch."""
from uuid import UUID

from character_chat import create_server
from whole_reply_trial import WholeReplyTrialAdapter


APPLICATION_ID = "whole-reply-free-input-chat-s119"


class WholeReplyChatAdapter(WholeReplyTrialAdapter):
    def snapshot(self):
        return dict(super().snapshot(), mode="free-input")

    @staticmethod
    def _wrap(case, result):
        result = dict(result)
        if result.get("message"):
            result["message"] = result["message"].replace("所选消息", "草稿")
        return dict(result, case_id=case)

    def send(self, payload):
        with self.lock:
            case, adapter, data = self._case(payload, {"text", "request_id"})
            text, request_id = data["text"], data["request_id"]
            # Reject invalid browser input before Admission or any model claim.
            # Do not trim or otherwise change the explicitly submitted text.
            if (type(text) is not str or not text.strip() or len(text) > 1000
                    or "\x00" in text or type(request_id) is not str
                    or str(UUID(request_id)) != request_id):
                raise ValueError("invalid-request")
            return self._wrap(case, adapter.send(data))


def chat_server(products, *, choices, scope_key, reopen, port=0,application_id=APPLICATION_ID,page_name="whole_reply_chat.html"):
    adapter = WholeReplyChatAdapter(products, choices=choices, scope_key=scope_key, reopen=reopen)
    return create_server(None, port=port, adapter=adapter, page_name=page_name,
        application_id=application_id, post_routes={"/send":adapter.send, "/operation":adapter.poll,
            "/history":adapter.history, "/context-reset":adapter.reset_context, "/reload":adapter.reload})
