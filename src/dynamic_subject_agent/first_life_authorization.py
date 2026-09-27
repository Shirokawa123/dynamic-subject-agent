"""Local, versioned disclosure authority; never included in Provider requests."""
from dataclasses import dataclass, fields
import re
from threading import RLock
from uuid import UUID


LEGACY_RUNTIME_POLICY = "first-life-use-1"
_LOCKS = {}
_LOCKS_LOCK = RLock()


class ShareAuthorizationChanged(RuntimeError):
    """The readable current authorization differs from a prepared snapshot."""


def registry_lock(path):
    # All in-process authorities for this registry share one linearization lock.
    # RuntimeHost owns the single serving process/Timeline writer.
    key = str(path.resolve()).casefold()
    with _LOCKS_LOCK:
        return _LOCKS.setdefault(key, RLock())


@dataclass(frozen=True)
class ShareAuthorization:
    identity_id: str
    runtime_policy: str
    runtime_policy_digest: str
    policy_revision: int
    history_revision: int
    history_enabled: bool

    def __post_init__(self):
        if (str(UUID(self.identity_id)) != self.identity_id
            or self.runtime_policy not in ("first-life-relevance-2", "first-life-grounded-3")
            or re.fullmatch(r"[0-9a-f]{64}", self.runtime_policy_digest) is None
            or type(self.policy_revision) is not int or self.policy_revision < 1
            or type(self.history_revision) is not int or self.history_revision < 0
            or type(self.history_enabled) is not bool):
            raise ValueError("invalid local share authorization")


def decode_share_authorization(value):
    if type(value) is not dict or set(value) != {field.name for field in fields(ShareAuthorization)}:
        raise ValueError("exact share authorization required")
    return ShareAuthorization(**value)
