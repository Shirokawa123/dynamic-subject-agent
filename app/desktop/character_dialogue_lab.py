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


def make_server(application, port=0):
    token = secrets.token_urlsafe(32)
    page = Path(__file__).with_suffix(".html").read_text(encoding="utf-8").replace("__TOKEN__", token)

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
            if (not self.valid_host() or self.path != "/send"
                    or self.headers.get("X-Lab-Token") != token
                    or self.headers.get("Content-Type") != "application/json"):
                return self.respond(403, {"error": "request-rejected"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    raise ValueError()
                request = DialogueRequest(**json.loads(self.rfile.read(length)))
            except (ValueError, TypeError, UnicodeError):
                return self.respond(400, {"error": "invalid-request"})
            result = application.character_dialogue_send(request)
            self.respond(200, asdict(result))

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve-plan", help="仅在用户批准当前具体方案后，显式填写其摘要")
    parser.add_argument("--run-suite", action="store_true")
    parser.add_argument("--print-plan", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    if args.print_plan:
        print(json.dumps(dict(plan=plan_payload(), digest=plan_digest()), ensure_ascii=False, indent=2))
        return
    if args.approve_plan is not None and not args.run_suite:
        parser.error("本轮真实入口仅开放已审阅的六条验收文本；交互页面保持离线")
    parent = Path(__file__).resolve().parents[2] / ".artifacts" / "character-dialogue-labs"
    with open_character_dialogue_lab(parent, approved_plan=args.approve_plan) as product:
        if args.run_suite:
            print(json.dumps(run_suite(product.application), ensure_ascii=False, indent=2))
            return
        server = make_server(product.application, args.port)
        print(f"离线联调：http://127.0.0.1:{server.server_port} （固定回声；Ctrl+C关闭）", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
