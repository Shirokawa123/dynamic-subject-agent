"""One frozen, approved M030 experiment; not a deployed memory runtime.

Reuses the credential transport, gateway, identity freeze and attempt journal.
All messages are reviewed synthetic examples; user canonical is never opened.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from urllib.request import urlopen

from dynamic_subject_agent.frozen_attempt import FrozenAttemptRun, canonical_json, write_once
from dynamic_subject_agent.model_gateway import (ModelTask, ModelTaskKind, ModelResult, ModelGateway,
    ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelGatewayFailure)
from dynamic_subject_agent.deepseek import (_post_json_reply_content, _post_text_reply_content,
    DeepSeekUrlLibTransport, DeepSeekResponseDiagnosticFailure,
    DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID)
from dynamic_subject_agent.first_life_reply_live_provider import _ObservedTransport
from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
from dynamic_subject_agent.cognition import CredentialRef
from dynamic_subject_agent.natural_experience import NaturalExperience, adjudicate_experience, encode_experience

REVIEW = 'e593155cb74ad823414f95cf7d6ea7e4259932e0a60806bb392fa30ebaf65477'
SELECTIONS = ('temporary', 'ongoing', 'correction', 'forget', 'irrelevant', 'unclear')
DOWNSTREAM = ('reply_after_memory', 'choice_after_memory', 'share_after_memory', 'reply_after_forget')
DIAGNOSTIC_REVIEW = '5847a962eab987bbb72c3e36e8d4d4de8dab676733371f2e6a883d65a05c1152'
DIAGNOSTIC_SELECTIONS = ('A_temporary', 'A_correction', 'B_temporary', 'B_correction')
DIAGNOSTIC_REPLIES = ('C_change_topic', 'C_recent_activity')


@dataclass(frozen=True)
class NaturalExperienceTrialRequest:
    review_directory: Path
    approval_path: Path
    preparation_path: Path
    output: Path
    diagnostic_directory: Path | None = None
    diagnostic_approval_path: Path | None = None
    first_results_path: Path | None = None


def trial_scope(request):
    if request.diagnostic_directory is not None:
        return DIAGNOSTIC_REVIEW, DIAGNOSTIC_SELECTIONS, DIAGNOSTIC_REPLIES
    return REVIEW, SELECTIONS, DOWNSTREAM


def validate_material(request):
    raw = (request.review_directory / 'review.json').read_bytes()
    if sha256(raw).hexdigest() != REVIEW:
        raise ValueError('approved review changed')
    review = json.loads(raw)
    approval = json.loads(request.approval_path.read_bytes())
    expected = dict(version=review['version'], review_sha256=REVIEW, human_confirmed=True,
        data_upgrade_included=False, installation_included=False, user_reply='agree',
        authorization_source='direct-user-reply:2026-10-29-current-chat')
    if (approval != expected or approval.get('human_confirmed') is not True
            or approval.get('data_upgrade_included') is not False or approval.get('installation_included') is not False):
        raise ValueError('exact human approval required')
    if sha256(request.preparation_path.read_bytes()).hexdigest() != review['preparation_sha256']:
        raise ValueError('reviewed character preparation changed')
    bodies = {}
    if set(review['examples_sha256']) != set(SELECTIONS + DOWNSTREAM):
        raise ValueError('exact ten reviewed examples required')
    for name, expected_sha in review['examples_sha256'].items():
        body = (request.review_directory / (name + '.request.json')).read_bytes()
        if sha256(body).hexdigest() != expected_sha or len(body) > 65536:
            raise ValueError('reviewed request changed')
        bodies[name] = body
    diagnostic_fields = (request.diagnostic_directory, request.diagnostic_approval_path, request.first_results_path)
    if any(value is not None for value in diagnostic_fields):
        if any(value is None for value in diagnostic_fields):
            raise ValueError('complete diagnostic binding required')
        if request.diagnostic_directory.resolve().parent != request.review_directory.resolve().parent:
            raise ValueError('diagnostic review must share the isolated artifact parent')
        raw = (request.diagnostic_directory / 'review.json').read_bytes()
        if sha256(raw).hexdigest() != DIAGNOSTIC_REVIEW:
            raise ValueError('diagnostic review changed')
        diagnostic = json.loads(raw)
        if (diagnostic['parent_review_sha256'] != REVIEW
                or sha256(request.first_results_path.read_bytes()).hexdigest() != diagnostic['first_results_sha256']
                or set(diagnostic['cases_sha256']) != set(DIAGNOSTIC_SELECTIONS + DIAGNOSTIC_REPLIES)):
            raise ValueError('preserved first results and exact six follow-ups required')
        approval = json.loads(request.diagnostic_approval_path.read_bytes())
        expected = dict(version='memorie-natural-experience-diagnostic-r2', review_sha256=DIAGNOSTIC_REVIEW,
            human_confirmed=True, user_reply='同意', authorization_source='direct-user-reply:2026-10-29-current-chat',
            maximum_new_requests=6, automatic_retries=0, data_upgrade_included=False, installation_included=False)
        if (approval != expected or approval.get('human_confirmed') is not True
                or approval.get('data_upgrade_included') is not False or approval.get('installation_included') is not False
                or type(approval.get('maximum_new_requests')) is not int or type(approval.get('automatic_retries')) is not int):
            raise ValueError('separate exact diagnostic approval required')
        bodies = {}
        for name, expected_sha in diagnostic['cases_sha256'].items():
            body = (request.diagnostic_directory / (name + '.request.json')).read_bytes()
            if sha256(body).hexdigest() != expected_sha or len(body) > 65536:
                raise ValueError('diagnostic request changed')
            bodies[name] = body
    return bodies


class _FrozenAdapter(ProviderAdapter):
    capabilities = ProviderCapabilities('deepseek', 'deepseek-flash', False,
        (StructuredOutputMode.JSON_OBJECT, StructuredOutputMode.TEXT))

    def __init__(self, request, journal, transport_factory, activity_audit):
        self.request, self.journal, self.transport_factory = request, journal, transport_factory
        self.activity_audit = activity_audit

    def invoke(self, task):
        name = task.payload
        review_id, selections, downstream = trial_scope(self.request)
        if task.kind is not ModelTaskKind.MEMORIE_NATURAL_EXPERIENCE or name not in selections + downstream:
            raise ModelGatewayFailure('trial-task-invalid')
        bodies = validate_material(self.request)
        raw = bodies[name]
        request_digest = sha256(raw).hexdigest()
        self.journal.claim(request_digest)  # persisted before resolving any secret
        purpose = None if name in selections else 'reply' if name.startswith('reply_') or name in DIAGNOSTIC_REPLIES else 'choice' if name.startswith('choice_') else 'share'
        day = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        attempt = sha256((review_id + ':' + name).encode()).hexdigest()
        if purpose:
            self.activity_audit.claim_daily(attempt, request_digest, purpose=purpose, day=day, run=review_id)
        sent = False
        def opener(request, *, timeout):
            nonlocal sent
            current = validate_material(self.request)[name]
            if (sent or current != raw or request.data != current or request.get_method() != 'POST'
                    or purpose and datetime.now(timezone(timedelta(hours=8))).date().isoformat() != day
                    or request.full_url != 'https://api.deepseek.com/chat/completions' or timeout != 30):
                raise ValueError('exact one-shot reviewed delivery required')
            sent = True
            return urlopen(request, timeout=timeout)
        observed = _ObservedTransport(self.transport_factory(opener))
        ref = CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID)
        value, selected, code, status = None, None, None, 'failed-closed'
        try:
            if purpose == 'reply':
                value = _post_text_reply_content(observed, ref, raw, max_output_tokens=4096)
                from dynamic_subject_agent.original_whole_chat import validate_whole_reply
                validate_whole_reply(dict(reply_text=value, language='zh'))
            else:
                value = _post_json_reply_content(observed, ref, raw, max_output_tokens=4096,
                    require_complete=True, discard_reasoning=True, safe_diagnostics=True)
                payload = json.loads(json.loads(raw)['messages'][1]['content'])
                if name in selections:
                    old = payload['current_experience']
                    previous = None if old is None else NaturalExperience(old['quote'], old['duration'], 1, '2026-10-29')
                    selected = encode_experience(adjudicate_experience(value, current_text=payload['current_user_text'],
                        previous=previous, source_head_sequence=2, local_day='2026-10-29'))
                elif name == 'share_after_memory':
                    from dynamic_subject_agent.living_activity import validate_share
                    validate_share(value)
                    if len(value['reply_text']) > 120:
                        raise ValueError('native share too long')
                else:
                    from dynamic_subject_agent.shared_activity import SharedExperience, adjudicate_choice
                    from dynamic_subject_agent.first_life import validate_plan
                    source = payload['experience']
                    adjudicate_choice(value, phase=payload['current_activity']['phase'],
                        current_plan=validate_plan(payload['current_plan']),
                        source=SharedExperience(1, 1, source['quote']), plan_dependencies=())
            status = 'complete'
        except CharacterCredentialUnavailable:
            code, status = 'character-credential-unavailable', 'unavailable'
        except DeepSeekResponseDiagnosticFailure as error:
            code = error.diagnostic_code
            status = 'unknown' if code in ('transport-timeout', 'transport-delivery-ambiguous') else 'failed-closed'
        except Exception:
            code = 'trial-output-invalid'
        row = dict(case=name, status=status, error_code=code, value=value, selected=selected,
            final_content=observed.row['final_content'],
            **{k: observed.row[k] for k in ('model', 'usage', 'finish_reason')})
        self.journal.record(request_digest, row)
        if purpose:
            self.activity_audit.record(attempt, status=status,
                output_digest=None if code else sha256(canonical_json(value).encode()).hexdigest())
        if code:
            raise ModelGatewayFailure(code)
        return ModelResult(task.kind, row)


def run_trial(request, *, _transport=None, _audit_parent=None):
    """Production composition for this bounded experiment, never user runtime."""
    from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product, _WindowsLabResolver
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
    from dynamic_subject_agent.memorie_companion_contract import DEFINITION
    from dynamic_subject_agent.memorie_activity_live import ApprovedNativeActivityGrant, open_audit
    if type(request) is not NaturalExperienceTrialRequest:
        raise ValueError('typed trial request required')
    validate_material(request)
    review_id, selections, downstream = trial_scope(request)
    if (request.output.resolve().parent != request.review_directory.resolve().parent
            or request.review_directory.resolve().parent.name != '.artifacts'):
        raise ValueError('isolated sibling artifact root required')
    if request.output.exists() or any(request.output.resolve().is_relative_to(path.resolve()) for path in
            (request.review_directory, request.approval_path.parent, request.preparation_path.parent)):
        raise ValueError('fresh isolated output required')
    if _transport is None and _audit_parent is not None:
        raise ValueError('live audit root cannot be overridden')
    audit_parent = _audit_parent if _transport is not None else Path(os.environ['LOCALAPPDATA']) / 'DynamicSubjectAgent' / 'memorie-natural-experience-m030'
    audit_parent.mkdir(parents=True, exist_ok=True)
    journal = FrozenAttemptRun(audit_parent, review_id, approved=True)
    if journal.resumed:
        raise ValueError('first trial already started; no resend or replay')
    request.output.mkdir(parents=True)
    prepared = json.loads(request.preparation_path.read_bytes())
    config = LocalProductConfig(request.output / 'identity/DynamicSubjectAgent/m0/experiments', request.output / 'identity/state.json')
    rows = []
    try:
        with open_local_product(config, cognition=DormantDeepSeekCognition()) as author:
            frozen = author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(prepared['definition_json'], DEFINITION, True, True))
            if frozen.status != 'created':
                raise ValueError('independent reviewed development identity required')
        write_once(request.output / 'scope.json', dict(identity_id=frozen.view.identity_id, synthetic_messages=True,
            user_canonical_opened=False, runtime_memory_implemented=False, review_sha256=review_id))
        factory = (lambda opener: _transport) if _transport is not None else (
            lambda opener: DeepSeekUrlLibTransport(credential_resolver=_WindowsLabResolver(), _opener=opener))
        activity_audit = open_audit(ApprovedNativeActivityGrant(request.approval_path.with_name('native-activity-approval.json')))
        gateway = ModelGateway(_FrozenAdapter(request, journal, factory, activity_audit))
        for name in selections + downstream:
            try:
                row = gateway.execute(ModelTask(ModelTaskKind.MEMORIE_NATURAL_EXPERIENCE, name)).value
            except ModelGatewayFailure as error:
                journal.stop(error.code)
                rows.append(dict(case=name, status='stopped', error_code=error.code))
                break
            rows.append(row)
        summary = dict(status='complete' if len(rows) == len(selections + downstream) and all(r['status'] == 'complete' for r in rows) else 'stopped',
            attempts=journal.next, user_canonical_opened=False, runtime_memory_implemented=False, results=rows)
        write_once(request.output / 'results.json', summary)
        return summary
    except Exception:
        journal.stop('trial-setup-or-recording-failed')
        raise
