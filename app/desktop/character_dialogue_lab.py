"""Optional S55 lab. Default offline; remote mode only runs the reviewed six texts."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from uuid import uuid4

from dynamic_subject_agent.character_dialogue import DialogueRequest, TEST_MESSAGES, plan_payload, plan_digest
from dynamic_subject_agent.conversation_basis import BasisPreviewRequest, BasisMessageRequest, TOPICS
from dynamic_subject_agent.local_product import open_character_dialogue_lab


def run_suite(application):
    rows = []
    for message in TEST_MESSAGES:
        current = application.character_dialogue_status()
        result = application.character_dialogue_send(DialogueRequest(
            current.lab_id, current.revision, uuid4().hex, message, current.history_enabled))
        rows.append(dict(message=message, result=asdict(result)))
        if result.status != "replied":
            break
    return dict(plan_digest=plan_digest(), mode=application.character_dialogue_status().mode, rows=rows)


def make_server(application, port=0, *, basis_preview_enabled=False):
    token = secrets.token_urlsafe(32)
    page = Path(__file__).with_suffix(".html").read_text(encoding="utf-8").replace("__TOKEN__", token)
    page = page.replace("__BASIS_AUTO__", "enabled" if basis_preview_enabled else "disabled")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log message bodies, keys or exception details.

        def respond(self, status, value, content_type="application/json; charset=utf-8"):
            body = value.encode() if isinstance(value, str) else json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self):
            if not self.valid_host():
                return self.respond(403, {"error": "invalid-host"})
            if self.path == "/":
                return self.respond(200, page, "text/html; charset=utf-8")
            if self.path == "/status":
                return self.respond(200, asdict(application.character_dialogue_status()))
            if self.path == "/plan":
                return self.respond(200, dict(plan=plan_payload(), digest=plan_digest()))
            self.respond(404, {"error": "not-found"})

        def do_POST(self):
            if (not self.valid_host() or self.path not in ("/send", "/basis-preview")
                    or self.headers.get("X-Lab-Token") != token
                    or self.headers.get("Content-Type") != "application/json"):
                return self.respond(403, {"error": "request-rejected"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    raise ValueError()
                payload = json.loads(self.rfile.read(length))
                request = ((BasisMessageRequest(**payload) if "message" in payload else BasisPreviewRequest(**payload)) if self.path == "/basis-preview"
                           else DialogueRequest(**payload))
            except (ValueError, TypeError, UnicodeError):
                return self.respond(400, {"error": "invalid-request"})
            result = (application.preview_conversation_basis(request) if self.path == "/basis-preview"
                      else application.character_dialogue_send(request))
            self.respond(200, asdict(result))

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve-plan", help="仅在用户批准当前具体方案后，显式填写其摘要")
    parser.add_argument("--run-suite", action="store_true")
    parser.add_argument("--print-plan", action="store_true")
    parser.add_argument("--basis-preview", action="store_true", help="启用S59本地材料预览，不加入聊天投影")
    parser.add_argument("--preview-topic", choices=TOPICS, help="只打印该话题的本地材料预览")
    parser.add_argument("--preview-message", help="按有限明确问法预览整条消息的本地材料")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    if args.preview_topic is not None and args.preview_message is not None:
        parser.error("请选择话题或消息中的一个预览入口")
    if (args.basis_preview or args.preview_topic or args.preview_message is not None) and (args.approve_plan is not None or args.run_suite):
        parser.error("材料预览必须单独离线运行")
    if args.print_plan:
        print(json.dumps(dict(plan=plan_payload(), digest=plan_digest()), ensure_ascii=False, indent=2))
        return
    if args.approve_plan is not None and not args.run_suite:
        parser.error("本轮真实入口仅开放已审阅的六条验收文本；交互页面保持离线")
    parent = Path(__file__).resolve().parents[2] / ".artifacts" / "character-dialogue-labs"
    workspace = Path(__file__).resolve().parents[2] if args.basis_preview or args.preview_topic or args.preview_message is not None else None
    with open_character_dialogue_lab(parent, approved_plan=args.approve_plan, basis_workspace=workspace) as product:
        if args.preview_topic or args.preview_message is not None:
            print(json.dumps(asdict(product.application.preview_conversation_basis(
                BasisMessageRequest(args.preview_message) if args.preview_message is not None
                else BasisPreviewRequest(args.preview_topic))), ensure_ascii=False, indent=2))
            return
        if args.run_suite:
            print(json.dumps(run_suite(product.application), ensure_ascii=False, indent=2))
            return
        server = make_server(product.application, args.port, basis_preview_enabled=workspace is not None)
        print(f"离线联调：http://127.0.0.1:{server.server_port} （固定回声；Ctrl+C关闭）", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
