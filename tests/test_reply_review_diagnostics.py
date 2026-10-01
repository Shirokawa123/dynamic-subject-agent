"""S113 replay and real transport-seam faults; no network or stored credentials."""
import errno
import json
from pathlib import Path
import socket
import ssl
from urllib.error import URLError

import pytest

from dynamic_subject_agent.cognition import CredentialRef, ProviderFailure, ProviderFailureCode
from dynamic_subject_agent.deepseek import (
    DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID,
    DeepSeekCredentialResolver, DeepSeekHttpResponse, DeepSeekResponseDiagnosticFailure,
    DeepSeekUrlLibTransport, _post_json_reply_content,
)
from dynamic_subject_agent.first_life_followup_provider import DeepSeekFirstLifeFollowupAdapter
from dynamic_subject_agent.model_gateway import ModelGateway, ModelGatewayFailure, ModelTask, ModelTaskKind
from dynamic_subject_agent.reply_review_diagnostics import REVIEW_DIAGNOSTIC_CODES
from test_first_life_reply_routes import planning_for
from test_first_life_relevance_projection import relevance_fixture


DETAIL = "RAW_SECRET https://private.invalid/?key=private private-host"


def credential_reference():
    return CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID)


class SyntheticResolver(DeepSeekCredentialResolver):
    def __init__(self):
        self.calls = 0

    def resolve(self, reference):
        self.calls += 1
        return "synthetic-only-key"


def failing_url_transport(error):
    calls = []
    resolver = SyntheticResolver()
    def opener(request, *, timeout):
        calls.append((request.data, timeout))
        raise error
    return DeepSeekUrlLibTransport(credential_resolver=resolver, _opener=opener), calls, resolver


class ResponseTransport:
    def __init__(self, content, *, finish="stop"):
        self.calls = 0
        self.payload = dict(model="deepseek-flash", choices=[dict(finish_reason=finish,
            message=dict(role="assistant", content=content, reasoning_content="HIDDEN_REASONING"))],
            usage=dict(prompt_tokens=10, completion_tokens=100))

    def post_json(self, **kwargs):
        self.calls += 1
        return DeepSeekHttpResponse(200, json.dumps(self.payload).encode())


def call(transport, *, safe=True):
    return _post_json_reply_content(transport, credential_reference(), b'{"synthetic":true}',
        max_output_tokens=4096, require_complete=True, discard_reasoning=True, safe_diagnostics=safe)


def test_s112_committed_blank_final_is_replayed_as_empty_without_changing_evidence():
    path = Path(__file__).resolve().parents[1] / "docs/reports/2026-10-01-slice-112/continuous-comparison.json"
    original = path.read_bytes()
    def failures(value):
        if type(value) is dict:
            if value.get("error_code") == "response-content-json":
                yield value
            for child in value.values():
                yield from failures(child)
        elif type(value) is list:
            for child in value:
                yield from failures(child)
    row, = failures(json.loads(original))
    assert row["final_content"] == " " * 57 and row["finish_reason"] == "stop"
    transport = ResponseTransport(row["final_content"], finish=row["finish_reason"])
    with pytest.raises(DeepSeekResponseDiagnosticFailure) as failure:
        call(transport)
    assert failure.value.diagnostic_code == "response-content-empty"
    assert transport.calls == 1 and path.read_bytes() == original


@pytest.mark.parametrize("content,finish,expected", [
    ("", "stop", "response-content-empty"), (" \n\t\r\u3000", "stop", "response-content-empty"),
    ("{bad json", "stop", "response-content-json"), (None, "stop", "response-content-json"),
    ("null", "stop", "response-content-json"), (" " * 57, "length", "response-truncated"),
])
def test_empty_content_is_separate_from_malformed_or_truncated_response(content, finish, expected):
    transport = ResponseTransport(content, finish=finish)
    with pytest.raises(DeepSeekResponseDiagnosticFailure) as failure:
        call(transport)
    assert failure.value.diagnostic_code == expected and expected in REVIEW_DIAGNOSTIC_CODES
    assert failure.value.code is ProviderFailureCode.INVALID_OUTPUT and transport.calls == 1


NETWORK_CASES = [
    (lambda: socket.gaierror(socket.EAI_NONAME, DETAIL), "transport-dns"),
    (lambda: ssl.SSLCertVerificationError(1, DETAIL), "transport-tls-certificate"),
    (lambda: ssl.SSLError(1, DETAIL), "transport-tls"),
    (lambda: ConnectionRefusedError(errno.ECONNREFUSED, DETAIL), "transport-connect-refused"),
    (lambda: ConnectionResetError(errno.ECONNRESET, DETAIL), "transport-connection-reset"),
    (lambda: ConnectionAbortedError(errno.ECONNABORTED, DETAIL), "transport-connection-aborted"),
    (lambda: BrokenPipeError(errno.EPIPE, DETAIL), "transport-broken-pipe"),
    (lambda: OSError(errno.ENETUNREACH, DETAIL), "transport-connect-unreachable"),
    (lambda: TimeoutError(DETAIL), "transport-timeout"),
]


@pytest.mark.parametrize("wrapped", [False, True], ids=["direct", "urllib-reason"])
@pytest.mark.parametrize("factory,expected", NETWORK_CASES, ids=[code for _, code in NETWORK_CASES])
def test_url_transport_preserves_only_type_diagnostic_and_legacy_failure_code(factory, expected, wrapped):
    raw = factory()
    error = URLError(raw) if wrapped else raw
    transport, calls, resolver = failing_url_transport(error)
    with pytest.raises(DeepSeekResponseDiagnosticFailure) as failure:
        call(transport)
    assert failure.value.diagnostic_code == expected and expected in REVIEW_DIAGNOSTIC_CODES
    legacy_code = (ProviderFailureCode.DELIVERY_AMBIGUOUS if isinstance(raw, TimeoutError) and not wrapped
        else ProviderFailureCode.NETWORK_FAILURE)
    assert failure.value.code is legacy_code
    assert DETAIL not in repr(failure.value) and vars(failure.value) == dict(code=legacy_code, diagnostic_code=expected)
    assert calls == [(b'{"synthetic":true}', 30.0)] and resolver.calls == 1

    # A separate synthetic request exercises the unchanged legacy mode, not retry.
    legacy, legacy_calls, legacy_resolver = failing_url_transport(error)
    with pytest.raises(ProviderFailure) as plain:
        call(legacy, safe=False)
    assert type(plain.value) is ProviderFailure and plain.value.code is legacy_code
    assert vars(plain.value) == dict(code=legacy_code)
    assert len(legacy_calls) == legacy_resolver.calls == 1


@pytest.mark.parametrize("error", [URLError(DETAIL + " DNS TLS reset refused"),
    OSError(987654, DETAIL), ConnectionError(DETAIL), RuntimeError(DETAIL)])
def test_unknown_or_text_reason_never_guesses_a_network_cause(error):
    transport, calls, resolver = failing_url_transport(error)
    with pytest.raises(DeepSeekResponseDiagnosticFailure) as failure:
        call(transport)
    assert failure.value.diagnostic_code == "transport-network"
    assert DETAIL not in repr(failure.value) and len(calls) == resolver.calls == 1


def test_errno_only_error_and_nested_url_reason_are_bounded():
    error = OSError()
    error.errno = errno.ECONNREFUSED
    transport, calls, _ = failing_url_transport(URLError(URLError(error)))
    with pytest.raises(DeepSeekResponseDiagnosticFailure) as failure:
        call(transport)
    assert failure.value.diagnostic_code == "transport-connect-refused" and len(calls) == 1

    cyclic = URLError("unused")
    cyclic.reason = cyclic
    transport, calls, _ = failing_url_transport(cyclic)
    with pytest.raises(DeepSeekResponseDiagnosticFailure) as failure:
        call(transport)
    assert failure.value.diagnostic_code == "transport-network" and len(calls) == 1


@pytest.mark.parametrize("failure_kind,expected", [("dns", "transport-dns"), ("blank", "response-content-empty")])
def test_existing_first_life_gateway_surfaces_diagnostic_without_retry(relevance_fixture, failure_kind, expected):
    transport = (failing_url_transport(URLError(socket.gaierror(socket.EAI_NONAME, DETAIL)))[0]
        if failure_kind == "dns" else ResponseTransport(" " * 57))
    adapter = DeepSeekFirstLifeFollowupAdapter(transport=transport, credential_ref=credential_reference())
    task = ModelTask(ModelTaskKind.CHARACTER_COMMUNICATION_PLAN, planning_for(relevance_fixture))
    with pytest.raises(ModelGatewayFailure) as failure:
        ModelGateway(adapter).execute(task)
    assert failure.value.code == expected and DETAIL not in str(failure.value)


def test_blank_response_and_typed_unavailable_keep_legacy_semantics():
    with pytest.raises(ProviderFailure) as failure:
        call(ResponseTransport(" " * 57), safe=False)
    assert type(failure.value) is ProviderFailure and failure.value.code is ProviderFailureCode.INVALID_OUTPUT
    from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
    class Unavailable:
        def post_json(self, **kwargs):
            raise CharacterCredentialUnavailable()
    with pytest.raises(CharacterCredentialUnavailable):
        call(Unavailable())
