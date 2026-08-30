"""Exact qualified local llama.cpp Cognition adapter (loopback-only).

This module owns the only loopback inference surface in the production local
route: the bounded transport protocol, the real runner process transport bound
to the exact qualified runner, and the LocalLlamaCognition adapter.  The
adapter performs no cloud transport, credential access, or fallback; OS-level
network-deny is a separate execution gate.
"""

from __future__ import annotations

import json
import subprocess
import urllib.request
from abc import ABC
from hashlib import sha256
from pathlib import Path
from time import monotonic, sleep

from dynamic_subject_agent.runtime import (
    _LOCAL_LLAMA_COGNITION_TOKEN,
    CognitionEngine,
    CognitionFailedClosed,
    CognitionRuntimeView,
    CognitiveProposal,
    CyclePlan,
    ExperienceBasis,
    ExpressionCandidate,
    PreAdmissionRejected,
    SubjectCommand,
    _UserConfirmedContextBrief,
)

_LOCAL_LLAMA_RUNNER_ROOT = Path(
    r"C:\Users\30252\AppData\Local\DynamicSubjectAgent\Post-M0"
    r"\local-model-qualification\qwen3-4b-q4-k-m--llama-b10331"
)
_LOCAL_LLAMA_RUNNER_MODEL = (
    _LOCAL_LLAMA_RUNNER_ROOT / "model" / "Qwen3-4B-Q4_K_M.gguf"
)
_LOCAL_LLAMA_RUNNER_MODEL_HASH = (
    "7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5"
)
_LOCAL_LLAMA_RUNNER_SERVER_HASH = (
    "23f1fa1f7fc673768b10fba736e3bc34ba6ae03187f94c37eb70d9699617ee9d"
)
_LOCAL_LLAMA_RUNNER_IMPL_HASH = (
    "45953d105c1ce5745fdf3242d2c3719affcbc84c0ff3efa85d15e562a87e8eb9"
)
_LOCAL_LLAMA_LISTENER_HOST = "127.0.0.1"
_LOCAL_LLAMA_LISTENER_PORT = 39041
_LOCAL_LLAMA_RUNNER_ARGUMENTS = (
    "--offline",
    "--host",
    "127.0.0.1",
    "--port",
    "39041",
    "--no-webui",
    "--no-slots",
    "--parallel",
    "1",
    "--ctx-size",
    "8192",
    "--predict",
    "512",
    "--batch-size",
    "256",
    "--ubatch-size",
    "256",
    "--threads",
    "16",
    "--threads-batch",
    "16",
    "--n-gpu-layers",
    "all",
    "--fit",
    "off",
    "--split-mode",
    "none",
    "--main-gpu",
    "0",
    "--cache-type-k",
    "f16",
    "--cache-type-v",
    "f16",
    "--reasoning",
    "off",
    "--reasoning-budget",
    "0",
    "--no-reasoning-preserve",
    "--no-cache-prompt",
    "--log-disable",
    "--no-warmup",
    "--no-mmproj",
    "--no-models-autoload",
    "--models-max",
    "1",
    "--no-cont-batching",
)
_LOCAL_LLAMA_HEALTH_ATTEMPTS = 90
_LOCAL_LLAMA_HEALTH_DELAY_SECONDS = 1.0
_LOCAL_LLAMA_REQUEST_TIMEOUT_SECONDS = 180.0
_LOCAL_LLAMA_MAX_RESPONSE_LENGTH = 2048


class _LocalLlamaTransport(ABC):
    """Bounded local inference transport; manages one exact runner process."""

    def start(self) -> str:
        raise NotImplementedError

    def request(self, prompt: str) -> str:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def serving_plan_digest(self) -> str:
        """Return the exact non-secret runner/loopback plan identity."""

        raise NotImplementedError

    def preflight_serving_plan(self) -> None:
        """Verify exact local plan inputs without launching or requesting."""

        raise NotImplementedError


def _local_llama_loopback_opener():
    """Return a proxy-less opener so loopback requests never use a proxy."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _local_llama_typed_failure(code: str, detail: str) -> CognitionFailedClosed:
    return CognitionFailedClosed("cognition", code, detail)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1 << 20)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


class _LocalLlamaProcessTransport(_LocalLlamaTransport):
    """Start the exact qualified llama.cpp server loopback-only.

    The runner is launched with the qualified offline/loopback arguments and a
    poisoned proxy environment; it never receives network-egress arguments.
    OS-level network-deny rules are the separate Phase-4 execution gate.
    """

    def __init__(
        self,
        *,
        root: Path = _LOCAL_LLAMA_RUNNER_ROOT,
        model: Path = _LOCAL_LLAMA_RUNNER_MODEL,
        server_hash: str = _LOCAL_LLAMA_RUNNER_SERVER_HASH,
        impl_hash: str = _LOCAL_LLAMA_RUNNER_IMPL_HASH,
        model_hash: str = _LOCAL_LLAMA_RUNNER_MODEL_HASH,
        arguments: tuple[str, ...] = _LOCAL_LLAMA_RUNNER_ARGUMENTS,
        host: str = _LOCAL_LLAMA_LISTENER_HOST,
        port: int = _LOCAL_LLAMA_LISTENER_PORT,
        _authority: object,
    ) -> None:
        if _authority is not _LOCAL_LLAMA_COGNITION_TOKEN:
            raise TypeError("local llama transport requires Host assembly authority")
        for label, candidate in (
            ("root", root),
            ("model", model),
        ):
            if not isinstance(candidate, Path) or not candidate.is_absolute():
                raise TypeError(f"local llama {label} must be an absolute Path")
        for label, value in (
            ("server_hash", server_hash),
            ("impl_hash", impl_hash),
            ("model_hash", model_hash),
        ):
            if not isinstance(value, str) or len(value) != 64:
                raise TypeError(f"local llama {label} must be canonical SHA-256")
        if not arguments or any(
            not isinstance(argument, str) or not argument for argument in arguments
        ):
            raise TypeError("local llama arguments must be non-empty strings")
        if host != _LOCAL_LLAMA_LISTENER_HOST:
            raise TypeError("local llama listener host must be exactly loopback")
        if port != _LOCAL_LLAMA_LISTENER_PORT:
            raise TypeError("local llama listener port must be the qualified port")
        self._root = root
        self._model = model
        self._server_hash = server_hash
        self._impl_hash = impl_hash
        self._model_hash = model_hash
        self._arguments = arguments
        self._host = host
        self._port = port
        self._process: subprocess.Popen[str] | None = None

    def serving_plan_digest(self) -> str:
        basis = {
            "root": str(self._root),
            "model": str(self._model),
            "server_hash": self._server_hash,
            "impl_hash": self._impl_hash,
            "model_hash": self._model_hash,
            "arguments": list(self._arguments),
            "host": self._host,
            "port": self._port,
        }
        return sha256(
            json.dumps(basis, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()

    def preflight_serving_plan(self) -> None:
        self._verify_hashes()

    def _verify_hashes(self) -> None:
        server = self._root / "runner" / "llama-server.exe"
        impl = self._root / "runner" / "llama-server-impl.dll"
        for label, path, expected in (
            ("llama-server.exe", server, self._server_hash),
            ("llama-server-impl.dll", impl, self._impl_hash),
            ("Qwen3-4B-Q4_K_M.gguf", self._model, self._model_hash),
        ):
            if not path.is_file():
                raise CognitionFailedClosed(
                    "cognition",
                    "local-llama-runner-missing",
                    f"qualified runner file is missing: {path}",
                )
            if _sha256_file(path) != expected:
                raise CognitionFailedClosed(
                    "cognition",
                    "local-llama-runner-hash-mismatch",
                    f"qualified runner file hash mismatch: {path}",
                )

    def _health_ready(self) -> bool:
        try:
            with _local_llama_loopback_opener().open(
                (
                    f"http://{self._host}:{self._port}/health"
                ),
                timeout=min(5.0, _LOCAL_LLAMA_HEALTH_DELAY_SECONDS + 2.0),
            ) as response:
                return response.status == 200
        except Exception:
            return False

    def start(self) -> str:
        if self._process is not None:
            return f"{self._host}:{self._port}"
        self._verify_hashes()
        environment = {
            "PATH": str(self._root / "runner"),
            "SystemRoot": r"C:\Windows",
            "ComSpec": r"C:\Windows\system32\cmd.exe",
            "http_proxy": "",
            "https_proxy": "",
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "ALL_PROXY": "",
            "all_proxy": "",
            "no_proxy": "*",
            "NO_PROXY": "*",
        }
        try:
            self._process = subprocess.Popen(
                [
                    str(self._root / "runner" / "llama-server.exe"),
                    "--model",
                    str(self._model),
                    *self._arguments,
                ],
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as error:
            raise _local_llama_typed_failure(
                "local-llama-launch-failed",
                f"the qualified local runner could not be launched: {error}",
            ) from error
        deadline = monotonic() + (
            _LOCAL_LLAMA_HEALTH_ATTEMPTS * _LOCAL_LLAMA_HEALTH_DELAY_SECONDS
        )
        while monotonic() < deadline:
            if self._process.poll() is not None:
                self.close()
                raise CognitionFailedClosed(
                    "cognition",
                    "local-llama-runner-exited",
                    "the qualified local runner exited before serving",
                )
            if self._health_ready():
                return f"{self._host}:{self._port}"
            sleep(_LOCAL_LLAMA_HEALTH_DELAY_SECONDS)
        self.close()
        raise CognitionFailedClosed(
            "cognition",
            "local-llama-health-timeout",
            "the qualified local runner did not become healthy in time",
        )

    def request(self, prompt: str) -> str:
        if self._process is None or self._process.poll() is not None:
            raise CognitionFailedClosed(
                "cognition",
                "local-llama-not-serving",
                "the qualified local runner is not serving a request",
            )
        body = json.dumps(
            {
                "prompt": prompt,
                "n_predict": 512,
                "temperature": 0.7,
                "cache_prompt": False,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"http://{self._host}:{self._port}/completion",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with _local_llama_loopback_opener().open(
                request,
                timeout=_LOCAL_LLAMA_REQUEST_TIMEOUT_SECONDS,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError) as error:
            raise _local_llama_typed_failure(
                "local-llama-request-failed",
                f"the qualified local runner request failed: {error}",
            ) from error
        content = str(payload.get("content", ""))
        if not content:
            raise CognitionFailedClosed(
                "cognition",
                "local-llama-empty-response",
                "the qualified local runner returned no content",
            )
        return content

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=15.0)


class LocalLlamaCognition(CognitionEngine):
    """Exact qualified local llama.cpp Cognition adapter (loopback-only).

    It binds one user-confirmed context brief and one exact command
    fingerprint, launches the qualified runner, requests exactly one response
    over loopback, and closes the runner.  It performs no cloud transport,
    credential access, or fallback.
    """

    adapter_version = "post-m0-04-local-llama-qwen3-4b-q4-k-m-1.0"
    provider_authority = "local-first:llama:qwen3-4b-q4-k-m-1.0"
    experimental = True
    test_only = False

    def __init__(
        self,
        *,
        confirmed_brief: _UserConfirmedContextBrief,
        expected_command_fingerprint: str,
        transport: _LocalLlamaTransport,
        _authority: object,
    ) -> None:
        if _authority is not _LOCAL_LLAMA_COGNITION_TOKEN:
            raise TypeError(
                "local llama Cognition requires Host assembly authority"
            )
        if type(confirmed_brief) is not _UserConfirmedContextBrief:
            raise TypeError("local llama Cognition requires an exact confirmed brief")
        if (
            not isinstance(expected_command_fingerprint, str)
            or len(expected_command_fingerprint) != 64
            or expected_command_fingerprint.casefold()
            != expected_command_fingerprint
        ):
            raise TypeError("local llama Cognition requires an exact command fingerprint")
        if not isinstance(transport, _LocalLlamaTransport):
            raise TypeError("local llama Cognition requires a bounded transport")
        self._confirmed_brief = confirmed_brief
        self._expected_command_fingerprint = expected_command_fingerprint
        self._transport = transport

    @classmethod
    def _for_host_assembly(
        cls,
        *,
        confirmed_brief: _UserConfirmedContextBrief,
        expected_command_fingerprint: str,
        transport: _LocalLlamaTransport,
        _authority: object,
    ) -> LocalLlamaCognition:
        return cls(
            confirmed_brief=confirmed_brief,
            expected_command_fingerprint=expected_command_fingerprint,
            transport=transport,
            _authority=_authority,
        )

    def _matches_phase1_plan(
        self,
        *,
        command_fingerprint: str,
        confirmed_brief_digest: str,
    ) -> bool:
        return (
            command_fingerprint == self._expected_command_fingerprint
            and confirmed_brief_digest == self._confirmed_brief.content_digest
        )

    def _serving_plan_digest(self) -> str:
        transport_digest = self._transport.serving_plan_digest()
        if (
            not isinstance(transport_digest, str)
            or len(transport_digest) != 64
            or any(character not in "0123456789abcdef" for character in transport_digest)
        ):
            raise TypeError("local llama transport serving plan digest is invalid")
        basis = {
            "adapter_version": self.adapter_version,
            "provider_authority": self.provider_authority,
            "command_fingerprint": self._expected_command_fingerprint,
            "confirmed_brief_digest": self._confirmed_brief.content_digest,
            "transport_plan_digest": transport_digest,
        }
        return sha256(
            json.dumps(basis, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()

    def _preflight_serving_plan(self) -> None:
        self._transport.preflight_serving_plan()

    def preflight(
        self,
        *,
        context: CognitionRuntimeView,
        command: SubjectCommand,
    ) -> None:
        if (
            command.payload_fingerprint != self._expected_command_fingerprint
            or command.target_profile_id != context.profile_id
            or command.target_timeline_id != context.timeline_id
            or context.provider_authority != self.provider_authority
        ):
            raise PreAdmissionRejected(
                "local-interaction-plan-mismatch",
                "the current command does not match the confirmed local plan",
            )

    def _build_prompt(self, command: SubjectCommand) -> str:
        brief = self._confirmed_brief.text
        return (
            f"{brief}\n\n"
            f"当前命令：{command.utterance}\n"
            f"请只根据这条当前命令和上述已确认简报，用中文简短回复。"
        )

    def propose(
        self,
        *,
        plan: CyclePlan,
        context: CognitionRuntimeView,
        command: SubjectCommand,
        basis: ExperienceBasis,
    ) -> CognitiveProposal:
        del plan
        endpoint = self._transport.start()
        try:
            text = self._transport.request(self._build_prompt(command))
        finally:
            self._transport.close()
        if not isinstance(text, str):
            raise CognitionFailedClosed(
                "cognition",
                "local-llama-invalid-response",
                "the local runner returned a non-text response",
            )
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if (
            not normalized
            or "\x00" in normalized
            or len(normalized) > _LOCAL_LLAMA_MAX_RESPONSE_LENGTH
        ):
            raise CognitionFailedClosed(
                "cognition",
                "local-llama-invalid-response",
                "the local runner response is empty, oversized, or invalid",
            )
        expression = ExpressionCandidate(
            text=normalized,
            language=command.language,
        )
        return self._bounded_noop_proposal(
            context=context,
            basis=basis,
            experience_summary=(
                f"local-llama qwen3-4b proposal via {endpoint}; "
                f"confirmed-brief={self._confirmed_brief.content_digest}."
            ),
            expression_candidate=expression,
        )
