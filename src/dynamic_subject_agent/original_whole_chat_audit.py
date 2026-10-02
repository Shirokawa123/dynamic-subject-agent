"""S127 metadata audit and one-use delivery tickets; no Provider or credentials."""
from dataclasses import asdict
from pathlib import Path
from threading import RLock, get_ident
import os
from dynamic_subject_agent.development_model_calls import DevelopmentCallAudit
from dynamic_subject_agent.original_whole_chat import digest
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind


PURPOSE = "original-character-whole-chat"


def default_original_whole_audit_path():
    base = Path(os.environ.get("LOCALAPPDATA", "").strip() or Path.home() / "AppData" / "Local")
    return base / "DynamicSubjectAgent/character-whole-s127/original-whole-audit"


class OriginalWholeCallAudit(DevelopmentCallAudit):
    """Reuse verified SQLite transactions, without upgrading any old audit."""
    purposes = frozenset((PURPOSE,))

    @staticmethod
    def configuration():
        return dict(version="original-whole-call-audit-s127-1", authorization="user-approved-original-whole-use-2026-10-02",
            provider="deepseek", purpose=PURPOSE, stage="whole-reply", limit=None)


def open_original_whole_audit(path, *, initialize=False):
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError("absolute independent whole audit required")
    witness = path.with_name(path.name + "-initialized")
    if witness.exists():
        if not witness.is_dir() or not path.is_dir():
            raise ValueError("whole audit witness missing")
        return OriginalWholeCallAudit(path)
    if path.exists() or not initialize:
        raise ValueError("whole audit cannot be rebuilt or repurposed")
    witness.mkdir(parents=True, exist_ok=False)
    return OriginalWholeCallAudit(path, initialize=True)


class OriginalWholeDelivery:
    """A durable unique attempt grants exactly one same-thread live delivery."""
    def __init__(self, audit, *, contract, state_path):
        if type(audit) is not OriginalWholeCallAudit:
            raise ValueError("exact independent whole audit required")
        self.audit, self.contract = audit, contract
        self.run_digest = digest(dict(contract=contract, state_path=str(state_path.resolve()), audit_path=str(audit.path.resolve())))
        self._lock, self._ticket, self._pending, self._poisoned = RLock(), None, None, False

    def counts(self):
        return self.audit.counts()

    def claim(self, identity, operation, request):
        with self._lock:
            if self._poisoned or self._pending is not None:
                raise ValueError("whole delivery already pending or unverified")
            attempt = digest(dict(run=self.run_digest, identity=identity, operation=operation, stage="whole-reply"))
            self.audit.claim(attempt, request, purpose=PURPOSE, run_digest=self.run_digest)
            self._pending = self._ticket = (attempt, request, get_ident())

    def consume(self, task):
        with self._lock:
            ticket, self._ticket = self._ticket, None
            if (self._poisoned or ticket is None or ticket[2] != get_ident()
                or type(task) is not ModelTask or task.kind is not ModelTaskKind.CHARACTER_ORIGINAL_WHOLE_REPLY
                or digest(asdict(task.payload)) != ticket[1]):
                raise ValueError("current exact whole ticket required")

    def record(self, status, *, value=None):
        with self._lock:
            if self._pending is None or self._pending[2] != get_ident() or self._ticket is not None:
                raise ValueError("consumed same-thread whole claim required")
            try:
                self.audit.record(self._pending[0], status=status, output_digest=None if value is None else digest(value))
            except Exception:
                self._poisoned = True
                raise
            self._pending = None
