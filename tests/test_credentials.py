from __future__ import annotations

from io import BytesIO
from urllib.error import HTTPError

import pytest

from dynamic_subject_agent.credentials import (
    CredentialStoreUnavailable,
    CredentialSlot,
    CredentialVerificationStatus,
    DEEPSEEK_CREDENTIAL_SLOT,
    DeepSeekCredentialVerifier,
    InMemoryCredentialStore,
    WindowsCredentialStore,
)


def _dummy_key() -> str:
    return "x" * 32


def test_in_memory_store_has_the_same_save_load_delete_interface() -> None:
    store = InMemoryCredentialStore()
    assert store.configured(DEEPSEEK_CREDENTIAL_SLOT) is False
    store.save(DEEPSEEK_CREDENTIAL_SLOT, _dummy_key())
    assert store.configured(DEEPSEEK_CREDENTIAL_SLOT) is True
    assert store.load(DEEPSEEK_CREDENTIAL_SLOT) == _dummy_key()
    assert store.delete(DEEPSEEK_CREDENTIAL_SLOT) is True
    assert store.delete(DEEPSEEK_CREDENTIAL_SLOT) is False
    assert store.load(DEEPSEEK_CREDENTIAL_SLOT) is None


@pytest.mark.parametrize("invalid", ["", "   ", "x\nsecret", "x" * 4097])
def test_store_rejects_invalid_secret_shape(invalid: str) -> None:
    with pytest.raises(CredentialStoreUnavailable) as captured:
        InMemoryCredentialStore().save(DEEPSEEK_CREDENTIAL_SLOT, invalid)
    assert captured.value.code == "credential-invalid"


def test_windows_adapter_uses_fixed_service_and_never_a_file(monkeypatch) -> None:
    import keyring
    from keyring.backends.Windows import WinVaultKeyring

    calls: list[tuple[str, ...]] = []
    secret: dict[str, str] = {}
    monkeypatch.setattr(keyring, "get_keyring", lambda: WinVaultKeyring())

    def get_password(service: str, username: str):
        calls.append(("get", service, username))
        return secret.get("value")

    def set_password(service: str, username: str, value: str):
        calls.append(("set", service, username))
        secret["value"] = value

    def delete_password(service: str, username: str):
        calls.append(("delete", service, username))
        secret.pop("value", None)

    monkeypatch.setattr(keyring, "get_password", get_password)
    monkeypatch.setattr(keyring, "set_password", set_password)
    monkeypatch.setattr(keyring, "delete_password", delete_password)
    store = WindowsCredentialStore()

    store.save(DEEPSEEK_CREDENTIAL_SLOT, _dummy_key())
    assert store.load(DEEPSEEK_CREDENTIAL_SLOT) == _dummy_key()
    assert store.delete(DEEPSEEK_CREDENTIAL_SLOT) is True
    assert store.load(DEEPSEEK_CREDENTIAL_SLOT) is None
    assert {call[1:] for call in calls} == {
        (
            DEEPSEEK_CREDENTIAL_SLOT.service_name,
            DEEPSEEK_CREDENTIAL_SLOT.account_id,
        )
    }


def test_windows_adapter_fails_closed_for_non_windows_backend(monkeypatch) -> None:
    import keyring

    monkeypatch.setattr(keyring, "get_keyring", lambda: object())
    with pytest.raises(CredentialStoreUnavailable) as captured:
        WindowsCredentialStore().load(DEEPSEEK_CREDENTIAL_SLOT)
    assert captured.value.code == "secure-backend-unavailable"


def test_slots_keep_provider_accounts_separate() -> None:
    store = InMemoryCredentialStore()
    deepseek = CredentialSlot("deepseek", "default")
    future = CredentialSlot("future-provider", "work")
    store.save(deepseek, "d" * 32)
    store.save(future, "f" * 32)
    assert store.load(deepseek) == "d" * 32
    assert store.load(future) == "f" * 32
    store.delete(deepseek)
    assert store.load(deepseek) is None
    assert store.load(future) == "f" * 32


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        assert limit == 1
        return b"{"


def test_verifier_sends_only_bearer_auth_to_models_endpoint() -> None:
    observed = {}

    def opener(request, *, timeout: float):
        observed["url"] = request.full_url
        observed["authorization"] = request.get_header("Authorization")
        observed["method"] = request.get_method()
        observed["timeout"] = timeout
        return _Response()

    status = DeepSeekCredentialVerifier(_opener=opener).verify(_dummy_key())

    assert status is CredentialVerificationStatus.VALID
    assert observed == {
        "url": "https://api.deepseek.com/models",
        "authorization": f"Bearer {_dummy_key()}",
        "method": "GET",
        "timeout": 10.0,
    }


def test_verifier_distinguishes_invalid_from_unavailable() -> None:
    def unauthorized(request, *, timeout: float):
        raise HTTPError(request.full_url, 401, "unauthorized", {}, BytesIO())

    def unavailable(request, *, timeout: float):
        raise TimeoutError

    assert DeepSeekCredentialVerifier(_opener=unauthorized).verify(
        _dummy_key()
    ) is CredentialVerificationStatus.INVALID
    assert DeepSeekCredentialVerifier(_opener=unavailable).verify(
        _dummy_key()
    ) is CredentialVerificationStatus.UNAVAILABLE
