"""Exclusive local attempt journal shared by bounded character experiments."""
import json
import os


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_once(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(canonical_json(value))
        stream.flush()
        os.fsync(stream.fileno())


class FrozenAttemptRun:
    """Claim before credentials; prior startup forbids continuation or resend."""

    def __init__(self, root, digest, *, approved):
        self.path, self.digest = root / digest, digest
        self.approved, self.resumed, self.stopped = approved, False, False
        self.next, self.results = 0, {}
        if approved:
            try:
                self.path.mkdir(exist_ok=False)
            except FileExistsError:
                self.resumed = True
            else:
                write_once(self.path / "started.json", dict(plan_digest=digest, status="started"))

    def stop(self, reason):
        self.stopped = True
        if self.approved and not self.resumed:
            try:
                write_once(self.path / "stopped.json", dict(plan_digest=self.digest, reason=reason))
            except OSError:
                pass  # Existing startup and attempt claims still forbid replay.

    def claim(self, digest):
        if not self.approved or self.resumed or self.stopped:
            raise ValueError("run not active")
        write_once(self.path / (digest + ".attempt.json"),
                   dict(request_digest=digest, index=self.next, status="attempted"))
        self.next += 1

    def read_result(self, digest):
        return json.loads((self.path / (digest + ".result.json")).read_text(encoding="utf-8"))

    def record(self, digest, audit):
        write_once(self.path / (digest + ".result.json"), audit)
