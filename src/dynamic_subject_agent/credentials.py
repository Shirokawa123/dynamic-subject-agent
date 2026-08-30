"""Secure local credential storage and explicit DeepSeek verification."""

from __future__ import annotations

import socket
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEEPSEEK_MODELS_ENDPOINT = "https://api.deepseek.com/models"
_MAX_KEY_CHARACTERS = 4_096
_SLOT_PART = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


@dataclass(frozen=True)
class CredentialSlot:
    provider_id: str
    account_id: str = "default"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.provider_id, str)
            or not _SLOT_PART.fullmatch(self.provider_id)
            or not isinstance(self.account_id, str)
            or not _SLOT_PART.fullmatch(self.account_id)
        ):
            raise ValueError("credential slot identity is invalid")

    @property
    def service_name(self) -> str:
        if self.provider_id == "deepseek":
            return "DynamicSubjectAgent.DeepSeek"
        return f"DynamicSubjectAgent.{self.provider_id}"


DEEPSEEK_CREDENTIAL_SLOT = CredentialSlot("deepseek", "default")


class CredentialStoreUnavailable(RuntimeError):
    """The requested secure credential operation could not be completed."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CredentialVerificationStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"


class CredentialStore(ABC):
    """Small Interface for one local DeepSeek credential."""

    @abstractmethod
    def load(self, slot: CredentialSlot) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def save(self, slot: CredentialSlot, api_key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, slot: CredentialSlot) -> bool:
        raise NotImplementedError

    def configured(self, slot: CredentialSlot) -> bool:
        return self.load(slot) is not None


def _validated_key(value: object) -> str:
    if not isinstance(value, str):
        raise CredentialStoreUnavailable("credential-invalid")
    key = value.strip()
    if (
        not key
        or len(key) > _MAX_KEY_CHARACTERS
        or any(character in key for character in ("\x00", "\r", "\n"))
    ):
        raise CredentialStoreUnavailable("credential-invalid")
    return key


class InMemoryCredentialStore(CredentialStore):
    """Local-substitutable Adapter used by behavior tests."""

    def __init__(self) -> None:
        self._secrets: dict[CredentialSlot, str] = {}

    def load(self, slot: CredentialSlot) -> str | None:
        if not isinstance(slot, CredentialSlot):
            raise TypeError("slot must be CredentialSlot")
        return self._secrets.get(slot)

    def save(self, slot: CredentialSlot, api_key: str) -> None:
        if not isinstance(slot, CredentialSlot):
            raise TypeError("slot must be CredentialSlot")
        self._secrets[slot] = _validated_key(api_key)

    def delete(self, slot: CredentialSlot) -> bool:
        if not isinstance(slot, CredentialSlot):
            raise TypeError("slot must be CredentialSlot")
        return self._secrets.pop(slot, None) is not None


class WindowsCredentialStore(CredentialStore):
    """Adapter backed only by Windows Credential Manager through keyring."""

    @staticmethod
    def _keyring_module():
        try:
            import keyring
            from keyring.backends.Windows import WinVaultKeyring
            from keyring.errors import KeyringError, NoKeyringError, PasswordDeleteError
        except (ImportError, RuntimeError) as error:
            raise CredentialStoreUnavailable("secure-backend-unavailable") from None
        try:
            backend = keyring.get_keyring()
        except (KeyringError, NoKeyringError, RuntimeError):
            raise CredentialStoreUnavailable("secure-backend-unavailable") from None
        if not isinstance(backend, WinVaultKeyring):
            raise CredentialStoreUnavailable("secure-backend-unavailable")
        return keyring, (KeyringError, NoKeyringError), PasswordDeleteError

    def load(self, slot: CredentialSlot) -> str | None:
        if not isinstance(slot, CredentialSlot):
            raise TypeError("slot must be CredentialSlot")
        keyring, read_errors, _ = self._keyring_module()
        try:
            value = keyring.get_password(
                slot.service_name,
                slot.account_id,
            )
        except read_errors:
            raise CredentialStoreUnavailable("credential-read-failed") from None
        if value is None:
            return None
        return _validated_key(value)

    def save(self, slot: CredentialSlot, api_key: str) -> None:
        if not isinstance(slot, CredentialSlot):
            raise TypeError("slot must be CredentialSlot")
        key = _validated_key(api_key)
        keyring, write_errors, _ = self._keyring_module()
        try:
            keyring.set_password(
                slot.service_name,
                slot.account_id,
                key,
            )
        except write_errors:
            raise CredentialStoreUnavailable("credential-write-failed") from None
        finally:
            key = ""

    def delete(self, slot: CredentialSlot) -> bool:
        if not isinstance(slot, CredentialSlot):
            raise TypeError("slot must be CredentialSlot")
        keyring, read_errors, delete_error = self._keyring_module()
        try:
            if (
                keyring.get_password(
                    slot.service_name,
                    slot.account_id,
                )
                is None
            ):
                return False
            keyring.delete_password(
                slot.service_name,
                slot.account_id,
            )
            return True
        except delete_error:
            raise CredentialStoreUnavailable("credential-delete-failed") from None
        except read_errors:
            raise CredentialStoreUnavailable("credential-read-failed") from None


class DeepSeekCredentialVerifier:
    """Use the official models endpoint without sending product or user data."""

    def __init__(self, *, _opener=urlopen) -> None:
        self._opener = _opener

    def verify(self, api_key: str) -> CredentialVerificationStatus:
        key = _validated_key(api_key)
        request = Request(
            DEEPSEEK_MODELS_ENDPOINT,
            method="GET",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {key}",
            },
        )
        try:
            with self._opener(request, timeout=10.0) as response:
                status = int(getattr(response, "status", 0))
                response.read(1)
        except HTTPError as error:
            if int(error.code) in {401, 403}:
                return CredentialVerificationStatus.INVALID
            return CredentialVerificationStatus.UNAVAILABLE
        except (TimeoutError, socket.timeout, URLError, OSError):
            return CredentialVerificationStatus.UNAVAILABLE
        finally:
            key = ""
        return (
            CredentialVerificationStatus.VALID
            if status == 200
            else CredentialVerificationStatus.UNAVAILABLE
        )


__all__ = [
    "CredentialStore",
    "CredentialStoreUnavailable",
    "CredentialSlot",
    "CredentialVerificationStatus",
    "DEEPSEEK_CREDENTIAL_SLOT",
    "DeepSeekCredentialVerifier",
    "InMemoryCredentialStore",
    "WindowsCredentialStore",
]
