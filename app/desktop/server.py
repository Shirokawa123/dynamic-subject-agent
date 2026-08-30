"""Loopback HTTP Adapter over the local product ApplicationFacade."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from dynamic_subject_agent.local_product import (
    LocalProductConfig,
    OpenedLocalProduct,
    open_deepseek_local_product,
)


STATIC_DIR = Path(__file__).resolve().parent / "static"
_DEFAULT_CONFIG = LocalProductConfig.default()
STATE_PATH = _DEFAULT_CONFIG.state_path
PERSISTENT_PARENT = _DEFAULT_CONFIG.product_parent


def _resolve_key() -> str:
    """Read the process credential without a repository-local fallback."""

    return os.environ.get("DEEPSEEK_API_KEY", "").strip()


def build_product(relationship_mode: str = "dynamic") -> OpenedLocalProduct:
    config = LocalProductConfig(
        product_parent=PERSISTENT_PARENT,
        state_path=STATE_PATH,
        relationship_mode=relationship_mode,
    )
    return open_deepseek_local_product(config, api_key=_resolve_key())


class AppState:
    """Translate HTTP turns into the public application Interface."""

    def __init__(self, product: OpenedLocalProduct) -> None:
        self.product = product

    def _memories(self) -> list[dict]:
        from dynamic_subject_agent.application import (
            ApplicationQuery,
            ApplicationQueryKind,
            ApplicationQueryStatus,
            LivingMemoryApplicationProjection,
        )

        response = self.product.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.LIVING_MEMORY,
                target_profile_id=self.product.profile_id,
                target_timeline_id=self.product.timeline_id,
            )
        )
        if (
            response.status is ApplicationQueryStatus.AVAILABLE
            and isinstance(response.projection, LivingMemoryApplicationProjection)
        ):
            return [
                {
                    "memory_id": memory.memory_id,
                    "content": memory.content,
                    "status": memory.status,
                    "memory_kind": memory.memory_kind,
                }
                for memory in response.projection.memories
            ]
        return []

    def snapshot(self) -> dict:
        from dynamic_subject_agent.application import (
            ApplicationQuery,
            ApplicationQueryKind,
            ApplicationQueryStatus,
            RelationshipApplicationProjection,
        )

        relationship = self.product.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.RELATIONSHIP,
                target_profile_id=self.product.profile_id,
                target_timeline_id=self.product.timeline_id,
            )
        )
        accepted = (
            tuple(
                interaction
                for interaction in relationship.projection.interactions
                if interaction.status == "accepted"
            )
            if (
                relationship.status is ApplicationQueryStatus.AVAILABLE
                and isinstance(
                    relationship.projection,
                    RelationshipApplicationProjection,
                )
            )
            else ()
        )
        return {
            "profile_id": self.product.profile_id,
            "memories": self._memories(),
            "knowledge_count": 4,
            "relationship_accepted_count": len(accepted),
            "relationship_latest_event": accepted[0].event if accepted else None,
        }

    def submit_turn(self, text: str) -> dict:
        from dynamic_subject_agent.knowledge_entries import knowledge_entry_by_id
        from dynamic_subject_agent.timeline import SubjectCommand

        command = SubjectCommand.contribute_utterance(
            target_profile_id=self.product.profile_id,
            target_timeline_id=self.product.timeline_id,
            declared_intent="ask-collaborator-status",
            utterance=text,
            language="zh",
            provenance="project-original",
        )
        submitted = self.product.application.submit(
            command,
            idempotency_key=f"local-product-{uuid4().hex}",
        )
        terminal = self.product.application.wait(
            submitted.operation_ref,
            timeout_seconds=30,
        )
        projection = terminal.projection
        if terminal.status.value != "terminal" or projection is None:
            stage = projection.failure_stage if projection else None
            code = (
                projection.failure_code
                if projection
                else (terminal.problem.code if terminal.problem else "unknown")
            )
            return {"ok": False, "stage": stage, "code": code}
        citations = []
        for entry_id in projection.knowledge_citation_ids:
            entry = knowledge_entry_by_id(entry_id)
            citations.append(
                {
                    "entry_id": entry_id,
                    "title": entry.title if entry else entry_id,
                    "source": entry.source_ref if entry else "",
                }
            )
        new_kind = None
        if projection.living_memory_status == "accepted" and self._memories():
            new_kind = self._memories()[0]["memory_kind"]
        return {
            "ok": True,
            "new_memory_kind": new_kind,
            "expression": projection.expression_text,
            "living_memory_status": projection.living_memory_status,
            "recalled_ids": list(projection.living_memory_recalled_ids),
            "relationship_event": projection.relationship_event,
            "citations": citations,
        }


def build_handler(state: AppState):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: object) -> None:
            self._send(
                status,
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
            )

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                self._send(
                    200,
                    (STATIC_DIR / "index.html").read_bytes(),
                    "text/html; charset=utf-8",
                )
            elif path == "/api/state":
                self._json(200, state.snapshot())
            else:
                self._json(404, {"error": "not-found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/turn":
                self._json(404, {"error": "not-found"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            text = str(body.get("text", "")).strip()
            if not text:
                self._json(400, {"error": "empty-text"})
                return
            self._json(200, state.submit_turn(text))

        def log_message(self, *args: object) -> None:
            del args

    return Handler


def main() -> int:
    product = build_product()
    state = AppState(product)
    server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(state))
    port = server.server_address[1]
    print(f"Avery 已就绪：http://127.0.0.1:{port}（Ctrl+C 退出）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        product.close()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
