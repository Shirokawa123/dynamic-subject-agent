from __future__ import annotations

from io import BytesIO
import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dynamic_subject_agent.credentials import (
    DeepSeekCredentialVerifier,
    InMemoryCredentialStore,
)


def _dummy_key() -> str:
    return "x" * 32


class _ValidResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return b"{"


def _valid_opener(request, *, timeout: float):
    return _ValidResponse()


class _FakeProduct:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _server_module():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "app" / "desktop" / "server.py"
    spec = importlib.util.spec_from_file_location("desktop_credentials", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_desktop_starts_in_setup_mode_without_credential() -> None:
    server = _server_module()
    state = server.DesktopState(
        credential_store=InMemoryCredentialStore(),
        verifier=DeepSeekCredentialVerifier(_opener=_valid_opener),
        product_factory=lambda key: _FakeProduct(),
    )
    try:
        assert state.setup_snapshot() == {
            "configured": False,
            "product_ready": False,
            "verification": "not-run",
            "problem": None,
        }
        assert state.snapshot() == {
            "ok": False,
            "error": "credential-setup-required",
        }
    finally:
        state.close()


def test_save_verify_replace_and_delete_never_return_secret() -> None:
    server = _server_module()
    store = InMemoryCredentialStore()
    opened: list[_FakeProduct] = []

    def factory(key: str):
        assert key == _dummy_key()
        product = _FakeProduct()
        opened.append(product)
        return product

    state = server.DesktopState(
        credential_store=store,
        verifier=DeepSeekCredentialVerifier(_opener=_valid_opener),
        product_factory=factory,
    )
    try:
        saved = state.save_and_verify(_dummy_key())
        assert saved == {
            "ok": True,
            "configured": True,
            "product_ready": True,
            "verification": "valid",
            "problem": None,
        }
        replaced = state.save_and_verify(_dummy_key())
        assert replaced["ok"] is True
        assert opened[0].closed is True
        deleted = state.delete_credential()
        assert deleted["ok"] is True
        assert deleted["deleted"] is True
        assert deleted["configured"] is False
        assert opened[-1].closed is True
        assert _dummy_key() not in str([saved, replaced, deleted])
    finally:
        state.close()


def test_invalid_or_unavailable_verification_does_not_store_key() -> None:
    def invalid(request, *, timeout: float):
        raise HTTPError(request.full_url, 401, "unauthorized", {}, BytesIO())

    def unavailable(request, *, timeout: float):
        raise TimeoutError

    server = _server_module()
    for opener, expected in (
        (invalid, "credential-invalid"),
        (unavailable, "credential-verification-unavailable"),
    ):
        store = InMemoryCredentialStore()
        state = server.DesktopState(
            credential_store=store,
            verifier=DeepSeekCredentialVerifier(_opener=opener),
            product_factory=lambda key: _FakeProduct(),
        )
        try:
            result = state.save_and_verify(_dummy_key())
            assert result["ok"] is False
            assert result["problem"] == expected
            assert store.load() is None
            assert result["product_ready"] is False
            assert _dummy_key() not in str(result)
        finally:
            state.close()


def test_desktop_setup_ui_never_uses_browser_or_repository_storage() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    html = (root / "app" / "desktop" / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    server = (root / "app" / "desktop" / "server.py").read_text(encoding="utf-8")
    assert 'type="password"' in html
    assert 'autocomplete="new-password"' in html
    assert 'fetch("/api/credential"' in html
    assert "localStorage" not in html
    assert "sessionStorage" not in html
    assert "DEEPSEEK_API_KEY" not in server
    assert "ds_key.txt" not in server


def test_loopback_credential_endpoints_save_status_and_delete_without_echo() -> None:
    server_module = _server_module()
    store = InMemoryCredentialStore()
    state = server_module.DesktopState(
        credential_store=store,
        verifier=DeepSeekCredentialVerifier(_opener=_valid_opener),
        product_factory=lambda key: _FakeProduct(),
    )
    httpd = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        server_module.build_handler(state),
    )
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with urlopen(f"{base}/api/setup", timeout=5) as response:
            initial = json.loads(response.read().decode("utf-8"))
        request = Request(
            f"{base}/api/credential",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"api_key": _dummy_key()}).encode("utf-8"),
        )
        with urlopen(request, timeout=5) as response:
            saved_raw = response.read().decode("utf-8")
            saved = json.loads(saved_raw)
        delete = Request(f"{base}/api/credential", method="DELETE")
        with urlopen(delete, timeout=5) as response:
            deleted_raw = response.read().decode("utf-8")
            deleted = json.loads(deleted_raw)
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        state.close()

    assert initial["configured"] is False
    assert saved["configured"] is True
    assert saved["product_ready"] is True
    assert deleted["configured"] is False
    assert _dummy_key() not in saved_raw
    assert _dummy_key() not in deleted_raw
