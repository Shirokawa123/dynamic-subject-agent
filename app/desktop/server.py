"""Loopback HTTP Adapter over the local product ApplicationFacade."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import RLock
from collections.abc import Callable
from time import time_ns
from uuid import uuid4

from dynamic_subject_agent.credentials import (
    CredentialStore,
    CredentialSlot,
    CredentialStoreUnavailable,
    CredentialVerificationStatus,
    DeepSeekCredentialVerifier,
    DEEPSEEK_CREDENTIAL_SLOT,
    WindowsCredentialStore,
)
from dynamic_subject_agent.local_product import (
    LocalProductConfig,
    OpenedLocalProduct,
    open_deepseek_local_product,
)


STATIC_DIR = Path(__file__).resolve().parent / "static"
_DEFAULT_CONFIG = LocalProductConfig.default()
STATE_PATH = _DEFAULT_CONFIG.state_path
PERSISTENT_PARENT = _DEFAULT_CONFIG.product_parent


def build_product(
    api_key: str,
    relationship_mode: str = "dynamic",
) -> OpenedLocalProduct:
    config = LocalProductConfig(
        product_parent=PERSISTENT_PARENT,
        state_path=STATE_PATH,
        relationship_mode=relationship_mode,
    )
    return open_deepseek_local_product(config, api_key=api_key)


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
            "participant_goals": self._participant_goals(),
            "situated_state": self._situated_state(),
        }

    def _participant_goals(self) -> list[dict]:
        from dynamic_subject_agent.application import (
            ApplicationQuery,
            ApplicationQueryKind,
            ApplicationQueryStatus,
            ParticipantGoalCommitmentApplicationProjection,
        )

        response = self.product.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.PARTICIPANT_GOALS,
                target_profile_id=self.product.profile_id,
                target_timeline_id=self.product.timeline_id,
            )
        )
        if (
            response.status is ApplicationQueryStatus.AVAILABLE
            and isinstance(
                response.projection,
                ParticipantGoalCommitmentApplicationProjection,
            )
        ):
            return [
                {
                    "kind": record.kind,
                    "terms": record.terms,
                    "status": record.status,
                    "evidence_quote": record.evidence_quote,
                }
                for record in response.projection.records
            ]
        return []

    def _situated_state(self) -> dict | None:
        from dynamic_subject_agent.application import (
            ApplicationQuery,
            ApplicationQueryKind,
            ApplicationQueryStatus,
            SituatedStateApplicationProjection,
        )

        response = self.product.application.query(
            ApplicationQuery(
                kind=ApplicationQueryKind.SITUATED_STATE,
                target_profile_id=self.product.profile_id,
                target_timeline_id=self.product.timeline_id,
            )
        )
        if (
            response.status is not ApplicationQueryStatus.AVAILABLE
            or not isinstance(response.projection, SituatedStateApplicationProjection)
            or response.projection.state is None
        ):
            return None
        state = response.projection.state
        expires_in = max(0, (state.expires_at_us - time_ns() // 1_000) // 1_000_000)
        return {
            "posture": state.posture,
            "remaining_turns": state.remaining_turns,
            "expires_in_seconds": int(expires_in),
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
            "participant_goal_status": (
                projection.participant_goal_commitment_status
            ),
            "participant_goal_action": (
                projection.participant_goal_commitment_action
            ),
            "situated_state_status": projection.situated_state_status,
            "situated_state_action": projection.situated_state_action,
            "situated_state_posture": projection.situated_state_posture,
            "citations": citations,
        }


class DesktopState:
    """Own credential setup and the optional opened product lifecycle."""

    def __init__(
        self,
        *,
        credential_store: CredentialStore,
        credential_slot: CredentialSlot,
        verifier: DeepSeekCredentialVerifier,
        product_factory: Callable[[str], OpenedLocalProduct] = build_product,
    ) -> None:
        if not isinstance(credential_store, CredentialStore):
            raise TypeError("credential_store must satisfy CredentialStore")
        if not isinstance(verifier, DeepSeekCredentialVerifier):
            raise TypeError("verifier must be DeepSeekCredentialVerifier")
        if not isinstance(credential_slot, CredentialSlot):
            raise TypeError("credential_slot must be CredentialSlot")
        self._credential_store = credential_store
        self._credential_slot = credential_slot
        self._verifier = verifier
        self._product_factory = product_factory
        self._product: OpenedLocalProduct | None = None
        self._app: AppState | None = None
        self._problem: str | None = None
        self._verification = "not-run"
        self._lock = RLock()
        self._open_existing()

    def _open_existing(self) -> None:
        key = ""
        try:
            key = self._credential_store.load(self._credential_slot) or ""
            if key:
                self._replace_product(self._product_factory(key))
        except CredentialStoreUnavailable as error:
            self._problem = error.code
        except Exception:
            self._problem = "product-open-failed"
        finally:
            key = ""

    def _replace_product(self, product: OpenedLocalProduct | None) -> None:
        previous = self._product
        self._product = product
        self._app = None if product is None else AppState(product)
        if previous is not None and previous is not product:
            previous.close()

    def setup_snapshot(self) -> dict:
        with self._lock:
            try:
                configured = self._credential_store.configured(self._credential_slot)
            except CredentialStoreUnavailable as error:
                configured = False
                self._problem = error.code
            return {
                "configured": configured,
                "provider_id": self._credential_slot.provider_id,
                "product_ready": self._app is not None,
                "verification": self._verification,
                "problem": self._problem,
            }

    def save_and_verify(self, api_key: object) -> dict:
        with self._lock:
            try:
                verification = self._verifier.verify(api_key)  # type: ignore[arg-type]
            except CredentialStoreUnavailable as error:
                self._problem = error.code
                return {"ok": False, **self.setup_snapshot()}
            self._verification = verification.value
            if verification is not CredentialVerificationStatus.VALID:
                self._problem = (
                    "credential-invalid"
                    if verification is CredentialVerificationStatus.INVALID
                    else "credential-verification-unavailable"
                )
                return {"ok": False, **self.setup_snapshot()}
            key = str(api_key)
            try:
                self._credential_store.save(self._credential_slot, key)
                self._replace_product(None)
                product = self._product_factory(key)
                self._replace_product(product)
                self._problem = None
            except CredentialStoreUnavailable as error:
                self._problem = error.code
                return {"ok": False, **self.setup_snapshot()}
            except Exception:
                self._problem = "product-open-failed"
                return {"ok": False, **self.setup_snapshot()}
            finally:
                key = ""
            return {"ok": True, **self.setup_snapshot()}

    def delete_credential(self) -> dict:
        with self._lock:
            self._replace_product(None)
            try:
                deleted = self._credential_store.delete(self._credential_slot)
                self._problem = None
                self._verification = "not-run"
            except CredentialStoreUnavailable as error:
                deleted = False
                self._problem = error.code
            return {"ok": self._problem is None, "deleted": deleted, **self.setup_snapshot()}

    def snapshot(self) -> dict:
        with self._lock:
            if self._app is None:
                return {"ok": False, "error": "credential-setup-required"}
            return {"ok": True, **self._app.snapshot()}

    def submit_turn(self, text: str) -> dict:
        with self._lock:
            if self._app is None:
                return {"ok": False, "stage": "credential", "code": "setup-required"}
            return self._app.submit_turn(text)

    def close(self) -> None:
        with self._lock:
            self._replace_product(None)


def build_handler(state: DesktopState):
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

        def _read_json(self, *, maximum: int = 8_192) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > maximum:
                raise ValueError("request-size-invalid")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("request-body-invalid")
            return payload

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                self._send(
                    200,
                    (STATIC_DIR / "index.html").read_bytes(),
                    "text/html; charset=utf-8",
                )
            elif path == "/api/state":
                payload = state.snapshot()
                self._json(200 if payload.get("ok") else 409, payload)
            elif path == "/api/setup":
                self._json(200, state.setup_snapshot())
            else:
                self._json(404, {"error": "not-found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path == "/api/credential":
                try:
                    payload = self._read_json(maximum=8_192)
                    api_key = payload.pop("api_key", None)
                    if payload:
                        raise ValueError("unexpected-fields")
                    try:
                        result = state.save_and_verify(api_key)
                    finally:
                        api_key = None
                except (UnicodeError, ValueError, json.JSONDecodeError):
                    self._json(400, {"ok": False, "problem": "invalid-request"})
                    return
                self._json(200 if result["ok"] else 422, result)
                return
            if self.path != "/api/turn":
                self._json(404, {"error": "not-found"})
                return
            try:
                body = self._read_json()
            except (UnicodeError, ValueError, json.JSONDecodeError):
                self._json(400, {"error": "invalid-request"})
                return
            text = str(body.get("text", "")).strip()
            if not text:
                self._json(400, {"error": "empty-text"})
                return
            self._json(200, state.submit_turn(text))

        def do_DELETE(self) -> None:  # noqa: N802
            if self.path != "/api/credential":
                self._json(404, {"error": "not-found"})
                return
            self._json(200, state.delete_credential())

        def log_message(self, *args: object) -> None:
            del args

    return Handler


def main() -> int:
    state = DesktopState(
        credential_store=WindowsCredentialStore(),
        credential_slot=DEEPSEEK_CREDENTIAL_SLOT,
        verifier=DeepSeekCredentialVerifier(),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(state))
    port = server.server_address[1]
    print(f"Avery 已就绪：http://127.0.0.1:{port}（Ctrl+C 退出）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        state.close()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
