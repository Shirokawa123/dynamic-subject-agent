"""One bounded S147 HTTP first pilot; only the main agent executes --execute.

Self-check/preflight create no roots, transport, server, product or credentials.
Form pauses for one exact main-agent canonical semantic token on stdin. Final
and reasoning strings never leave the canonical store for stdout or metadata.
"""
import argparse
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import sys
from threading import RLock, Thread
from time import perf_counter, sleep
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

from dynamic_subject_agent.deepseek import DeepSeekTransport
from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind

REPO = Path(__file__).resolve().parents[1]
REVIEW_BASIS = 'e87c9db1f6f52409faee497ca05f0852362add519e461d48f50bee27d760977c'
SCENE_SHA = 'eac5620acf9ce53af20a2089ca229db9888c4dc2e4f3e9421d6040fef6fe80bb'
SCENE_PATH = REPO/'docs/experiments/s147/live-entry-scene.json'
ROOT_RELATIVE = Path('DynamicSubjectAgent/working-understanding-development/s147/live-entry-first-20261009-1')
REAL_LOCAL_APPDATA = Path('C:/Users/30252/AppData/Local')
PURPOSES = ('working-understanding-form', 'working-activity-choice', 'working-activity-reply')
MAX_REQUESTS = 8
SAFE_STATUSES = frozenset(('available', 'previewed', 'committed', 'replayed', 'terminal', 'pending',
    'no-op', 'unavailable', 'unknown', 'failed-closed', 'busy', 'conflict', 'cancelled', 'not-found'))


def plain(value):
    if is_dataclass(value):
        return plain(asdict(value))
    if isinstance(value, dict):
        return {key:plain(item) for key,item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value.value if hasattr(value, 'value') else value


def digest(value):
    return sha256(canonical_json(plain(value)).encode('utf-8')).hexdigest()


def text_sha(text):
    return sha256(text.encode('utf-8')).hexdigest()


class AcceptanceStopped(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class NormalEnd(AcceptanceStopped):
    """An observed bounded no-op/content decision, distinct from failure."""


def require(condition, code):
    if not condition:
        raise AcceptanceStopped(code)


def status_of(response):
    status = response.get('status') if type(response) is dict else plain(getattr(response, 'status', None))
    return status if status in SAFE_STATUSES else 'unverified'


def safe_problem_code(value):
    from dynamic_subject_agent.reply_review_diagnostics import REVIEW_DIAGNOSTIC_CODES
    codes=REVIEW_DIAGNOSTIC_CODES | {'working-understanding-insufficient','working-operation-unverified',
        'working-preview-unverified','working-state-unverified','working-operation-pending',
        'working-source-isolated-canonical-pending','working-source-permission-changed',
        'character-credential-unavailable','structured-choice-invalid','working-output-invalid',
        'expression-invalid','delivery-unverified','audit-failed',
        'original-whole-provider-failed','original-whole-history-changed'}
    return value if type(value) is str and value in codes else ('other' if value is not None else None)


def strict_json(text):
    def pairs(items):
        value = {}
        for key,item in items:
            if key in value:
                raise ValueError('duplicate-json-key')
            value[key] = item
        return value
    def invalid_number(_value):
        raise ValueError('non-json-number')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_number)


def validate_preview(preview, purpose):
    from dynamic_subject_agent.working_understanding_remote_preview import working_remote_request_preview
    require(purpose in PURPOSES and type(preview) is dict and set(preview)=={'policy','payload'},
        'closed-working-preview-required')
    wire = working_remote_request_preview(ModelTask(ModelTaskKind(purpose), preview), technical_variant='fact-faithful')
    body, payload = wire['body'], preview['payload']
    protocol = {key:value for key,value in body.items() if key!='messages'}
    expected = dict(model='deepseek-flash', max_tokens=4096, thinking={'type':'enabled'},
        reasoning_effort='high', stream=False)
    if purpose != PURPOSES[2]:
        expected['response_format'] = {'type':'json_object'}
    require(protocol==expected and wire['endpoint']=='https://api.deepseek.com/chat/completions'
        and wire['timeout_seconds']==30 and wire['automatic_retries']==0
        and wire['requests_per_manual_action']==1, 'approved-protocol-parameters-changed')
    require(body['messages'][0]['content']==preview['policy']
        and strict_json(body['messages'][1]['content'])==payload, 'wire-does-not-match-preview')
    if purpose!=PURPOSES[0]:
        evidence = payload['evidence'] if purpose==PURPOSES[2] else payload
        require(evidence['shared_experience'] is None, 'new-working-has-no-legacy-e1')
    return wire


SCENE_ORDER = [
    'source-reply-1', 'source-reply-2', 'independent-choice-1',
    'form-from-two-quotes-and-actual-plan', 'name-is-not-appearance-probe', 'story-topic-gap',
    'close-and-reopen-zero-model', 'choice-using-valid-understanding',
    'same-nonce-read-zero-model', 'result-reply',
]
STOP_CONDITIONS = [
    'first-technical-failure-or-unknown-integrity-stop-all',
    'initial-choice-without-eligible-new-plan-end',
    'form-insufficient-or-out-of-scope-end',
    'later-choice-without-actual-plan-change-end',
    'no-rescue-branch-no-repeat-failed-stage-no-success-selection',
]
INDEPENDENT_POLICY_PINS = (
    '909d7f6cfbf8fadce1e548f803dcd99cf85b1bfd0337bf759c9c4f8af6529f27',
    '102cd1e31a127e1cadcbc001902873aa1fd3d97473bd4eb8c015e026abdbe02c',
    '174c545df32e46b0709fc55c3f508545b885f2414c5e71771508e39b5fbb5abe')


def validate_scene(scene):
    """Pure immutable pilot checks; no resource or authority construction."""
    fields = {'version', 'use_review_basis', 'technical_variant', 'maximum_first_requests',
        'requests_per_stage', 'automatic_retries', 'independent_fresh_identity',
        'production_service_started', 'user_roots_or_drafts_touched', 'real_cross_day_claimed',
        'source_messages', 'source_quotes', 'gap_messages', 'result_question', 'order',
        'stop_conditions'}
    require(type(scene) is dict and set(scene) == fields, 'closed-first-scene-required')
    require(scene['version'] == 's147-first-live-entry-reference-scene-1'
        and scene['use_review_basis'] == REVIEW_BASIS and scene['technical_variant'] == 'fact-faithful'
        and type(scene['maximum_first_requests']) is int and scene['maximum_first_requests'] == MAX_REQUESTS
        and type(scene['requests_per_stage']) is int and scene['requests_per_stage'] == 1
        and type(scene['automatic_retries']) is int and scene['automatic_retries'] == 0
        and scene['independent_fresh_identity'] is True and scene['user_roots_or_drafts_touched'] is False
        and scene['production_service_started'] is False and scene['real_cross_day_claimed'] is False
        and scene['order'] == SCENE_ORDER and scene['stop_conditions'] == STOP_CONDITIONS,
        'bounded-first-scene-changed')
    require(type(scene['source_messages']) is list and type(scene['source_quotes']) is list
        and len(scene['source_messages']) == len(scene['source_quotes']) == 2,
        'exactly-two-source-pairs-required')
    for message, quote in zip(scene['source_messages'], scene['source_quotes']):
        require(type(message) is str and 0 < len(message) <= 1000 and '\x00' not in message
            and type(quote) is str and 0 < len(quote) <= 400 and quote.strip() and quote in message,
            'fixed-source-boundary-changed')
    require(type(scene['gap_messages']) is list and len(scene['gap_messages']) == 2,
        'fixed-gap-count-changed')
    require(all(type(text) is str and 0 < len(text) <= 1000 and text.strip() and '\x00' not in text
        for text in [*scene['gap_messages'], scene['result_question']]), 'fixed-message-boundary-changed')
    return scene


def preflight():
    """Pure read/qualification checks, including actual rather than virtual AppData."""
    from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
    from dynamic_subject_agent.working_understanding_live import (WorkingFactFaithfulDevelopmentGrant,
        FACT_FAITHFUL_DEVELOPMENT_AUTHORIZATION, FACT_FAITHFUL_POLICY_HASHES,
        FACT_FAITHFUL_PROTOCOL_HASHES, working_fact_faithful_contract)
    review = strict_json((REPO/'docs/experiments/s145/review.json').read_text(encoding='utf-8'))
    unsigned = dict(review); unsigned.pop('review_basis')
    scene = validate_scene(strict_json(SCENE_PATH.read_text(encoding='utf-8')))
    require(review['review_basis'] == digest(unsigned) == REVIEW_BASIS, 'approved-review-pin-changed')
    require(digest(scene) == SCENE_SHA, 'first-live-scene-pin-changed')
    require(review['existing_material_binding'] == APPROVED_BINDING
        and sorted(PURPOSES) == review['new_purposes']
        and review['existing_shared_experience'] == 'always-null-no-legacy-E1-selection-capability',
        'approved-material-or-purposes-changed')
    require(tuple(FACT_FAITHFUL_POLICY_HASHES) == INDEPENDENT_POLICY_PINS, 'independent-candidate-policy-pins-changed')
    require(tuple(FACT_FAITHFUL_PROTOCOL_HASHES) == (
        '3c1bd02909292fd4a835a663d9c3d5e28ff81c1bbaadf6564fed03290dda7450',
        '3c1bd02909292fd4a835a663d9c3d5e28ff81c1bbaadf6564fed03290dda7450',
        '6cb5917026e0a98048608b2fc8ae7901385e12241d713b54767e1b4020420d31'),
        'inherited-protocol-pins-changed')
    WorkingFactFaithfulDevelopmentGrant(REVIEW_BASIS, FACT_FAITHFUL_DEVELOPMENT_AUTHORIZATION).validate()
    contract = working_fact_faithful_contract(APPROVED_BINDING)
    require(contract['version'] == 'working-fact-faithful-live-s147-1'
        and contract['technical_variant']['name'] == 'working-fact-faithful-live'
        and contract['technical_variant']['timeline_schema'] == 7, 'candidate-contract-unverified')
    local = Path(os.environ.get('LOCALAPPDATA', ''))
    require(local.is_absolute() and local.resolve() == REAL_LOCAL_APPDATA.resolve(), 'real-local-appdata-required')
    root = local/ROOT_RELATIVE
    require(root.resolve() == REAL_LOCAL_APPDATA/ROOT_RELATIVE and not root.exists() and not root.is_symlink(),
        'new-owned-first-root-required-existing-evidence-retained')
    return scene, root, digest(contract)


class SafeReport:
    def __init__(self, root, contract_sha):
        self.root, self.path = root, root/'metadata.json'
        self.lock, self.io_error_types = RLock(), []
        self.data = dict(version='s147-first-live-working-entry-1', review_basis=REVIEW_BASIS,
            first_live_scene_sha256=SCENE_SHA, runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
            live_contract_sha256=contract_sha, independent_root=str(root), status='preparing',
            synthetic_outputs=False, simulated_day=False, real_cross_day_verified=False,
            day_boundary_logic_verified=False, character_effect_verified=False,
            maximum_first_requests=MAX_REQUESTS, requests_per_stage=1, automatic_retries=0,
            raw_text_exported=False, reasoning_text_exported=False, service_started=False, production_service_started=False, temporary_loopback_server_started=False, temporary_loopback_server_closed=False,
            direct_https_without_proxy=True, remote_calls=0, credential_read_attempts=0,
            remote_call_count_semantics='single-provider-transport-attempts-not-confirmed-delivery',
            stages=[], transport=[], http=[], audit=[], checks={}, semantic_reviews=[], first_failure=None,
            audit_count=0, person_content_assessment='main-canonical-review-required')

    def save(self):
        with self.lock:
            try:
                self.data['checkpoint_io_error_types'] = self.io_error_types[:]
                temporary = self.path.with_name('metadata.json.next')
                temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
                temporary.replace(self.path)
                return True
            except Exception as error:
                name = type(error).__name__
                if name not in self.io_error_types:
                    self.io_error_types.append(name)
                return False

    def checked_save(self, code):
        require(self.save() and not self.io_error_types, code)

    def begin(self, label, **metadata):
        row = dict(stage=label, status='started', error_type=None, **metadata)
        self.data['stages'].append(row)
        self.checked_save('checkpoint-before-stage-failed')
        return row

    def stop(self, error):
        normal = isinstance(error, NormalEnd)
        code = error.code if isinstance(error, AcceptanceStopped) else 'unexpected-runner-failure'
        stage = self.data['stages'][-1] if self.data['stages'] else None
        if stage and stage['status']=='started':
            stage.update(status='failed-or-unverified', error_type=type(error).__name__)
        stop = dict(stage=None if stage is None else stage['stage'], stop_code=code, error_type=type(error).__name__)
        if not normal and self.data['first_failure'] is None:
            self.data['first_failure'] = stop
        self.data.update(status='normal-bounded-end' if normal else 'stopped-on-first-failure-or-integrity',
            stopped_stage=stop['stage'], stop_code=code, error_type=stop['error_type'], runner_exit_code=0 if normal else 1)
        self.save()


def final_boundary(response, purpose, preview):
    """Inspect one response transiently; never retain final/reasoning strings."""
    from dynamic_subject_agent.deepseek import _ACCEPTED_RESPONSE_MODELS
    row = dict(http_status=response.status_code, response_body_bytes=len(response.body),
        response_body_sha256=sha256(response.body).hexdigest(), exact_output_contract=False,
        final_value_sha256=None, final_text_sha256=None, reply_sha256=None)
    try:
        envelope = strict_json(response.body.decode('utf-8'))
        choices, usage = envelope.get('choices'), envelope.get('usage')
        require(type(choices) is list and len(choices)==1 and type(choices[0]) is dict, 'response-choice-invalid')
        message = choices[0].get('message')
        require(type(message) is dict, 'response-message-invalid')
        content = message.get('content')
        row.update(model='deepseek-flash' if envelope.get('model')=='deepseek-flash' else 'other',
            assistant_role=message.get('role')=='assistant', finish_reason='stop' if choices[0].get('finish_reason')=='stop' else 'other',
            reasoning_chars=len(message['reasoning_content']) if type(message.get('reasoning_content')) is str else 0)
        row['usage'] = {key:count for key,count in (usage or {}).items()
            if key in ('prompt_tokens','completion_tokens','total_tokens') and type(count) is int and 0<=count<2**53}
        require(response.status_code==200 and len(response.body)<=65536 and envelope.get('model') in _ACCEPTED_RESPONSE_MODELS
            and message.get('role')=='assistant' and choices[0].get('finish_reason')=='stop'
            and 'delta' not in choices[0] and message.get('tool_calls') in (None,[])
            and message.get('refusal') in (None,'') and message.get('final') in (None,'')
            and (message.get('reasoning_content') is None or type(message.get('reasoning_content')) is str)
            and type(usage) is dict and type(usage.get('prompt_tokens')) is int and usage['prompt_tokens']>=0
            and type(usage.get('completion_tokens')) is int and 0<=usage['completion_tokens']<=4096
            and type(content) is str and bool(content.strip()), 'response-envelope-or-final-invalid')
        row['final_text_sha256'] = text_sha(content)
        if purpose==PURPOSES[2]:
            from dynamic_subject_agent.original_whole_chat import validate_whole_reply
            value = dict(reply_text=content, language='zh'); validate_whole_reply(value)
            row.update(reply_chars=len(content), reply_sha256=text_sha(content), wrapped_model_result_value_sha256=digest(value))
        else:
            value = strict_json(content)
            if purpose==PURPOSES[0]:
                from dynamic_subject_agent.working_understanding import validate_form
                validate_form(value, preview['payload']['activity_result'] is not None)
                row.update(formation_status=value['status'], statement_chars=len(value['statement']),
                    statement_sha256=text_sha(value['statement']), basis_refs=list(value['basis_refs']))
            else:
                from dynamic_subject_agent.first_life import validate_plan, LIFE_REASONS
                allowed_refs = {'W1'} if preview['payload']['working_understanding'] is not None else set()
                require(type(value) is dict and set(value)=={'action','plan','reason_code','basis_refs','decision_note'}
                    and value['action'] in preview['payload']['current_activity']['allowed_actions']
                    and value['reason_code'] in LIFE_REASONS and type(value['decision_note']) is str
                    and 0<len(value['decision_note'].strip())<=160 and '\x00' not in value['decision_note']
                    and type(value['basis_refs']) is list and all(type(x) is str for x in value['basis_refs'])
                    and len(value['basis_refs'])==len(set(value['basis_refs'])) and set(value['basis_refs'])<=allowed_refs,
                    'response-choice-output-invalid')
                if value['action'] in ('start','revise'):
                    validate_plan(value['plan'])
                else:
                    require(value['plan'] is None, 'response-noop-choice-has-plan')
                row.update(action=value['action'], plan_sha256=None if value['plan'] is None else digest(value['plan']),
                    basis_refs=list(value['basis_refs']), decision_note_sha256=digest(value['decision_note']))
        row.update(exact_output_contract=True, final_value_sha256=digest(value))
    except (Exception,):
        # Exception messages may contain response text; only a closed validity
        # flag escapes. The production Adapter independently adjudicates it.
        pass
    return row


def safe_observation(value):
    from dynamic_subject_agent.reply_review_diagnostics import REVIEW_DIAGNOSTIC_CODES
    row = {}
    for key in ('task_kind','purpose'):
        if value.get(key) in PURPOSES: row[key]=value[key]
    if value.get('status') in ('complete','unavailable','unknown','failed-closed'): row['status']=value['status']
    for key in ('request_digest','wire_sha256'):
        if type(value.get(key)) is str and re.fullmatch('[0-9a-f]{64}', value[key]): row[key]=value[key]
    codes=REVIEW_DIAGNOSTIC_CODES | {'character-credential-unavailable','structured-choice-invalid',
        'working-output-invalid','expression-invalid','delivery-unverified','audit-failed'}
    if type(value.get('error_code')) is str and value['error_code'] in codes: row['error_code']=value['error_code']
    if 'model' in value: row['model']='deepseek-flash' if value['model']=='deepseek-flash' else 'other'
    if value.get('finish_reason') in ('stop','length','tool_calls','content_filter','aborted','other'): row['finish_reason']=value['finish_reason']
    if type(value.get('elapsed_seconds')) in (int,float) and math.isfinite(value['elapsed_seconds']): row['elapsed_seconds']=max(0.,value['elapsed_seconds'])
    if type(value.get('usage')) is dict:
        row['usage']={key:count for key,count in value['usage'].items() if key in
            ('prompt_tokens','completion_tokens','total_tokens','reasoning_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens')
            and type(count) is int and 0<=count<2**53}
    return row


class ObservedTransport(DeepSeekTransport):
    def __init__(self, report):
        from dynamic_subject_agent.deepseek import DeepSeekUrlLibTransport, DeepSeekCredentialResolver
        from dynamic_subject_agent.local_product import _WindowsLabResolver
        class CountedResolver(DeepSeekCredentialResolver):
            def resolve(self, credential_ref):
                from dynamic_subject_agent.deepseek import DEEPSEEK_CREDENTIAL_BACKEND_ID,DEEPSEEK_CREDENTIAL_KEY_ID
                require((credential_ref.backend_id,credential_ref.key_id)==
                    (DEEPSEEK_CREDENTIAL_BACKEND_ID,DEEPSEEK_CREDENTIAL_KEY_ID),'unapproved-credential-slot')
                report.data['credential_read_attempts'] += 1
                report.checked_save('checkpoint-before-credential-read-failed')
                return _WindowsLabResolver().resolve(credential_ref)
        self.report = report
        self.delegate = DeepSeekUrlLibTransport(credential_resolver=CountedResolver(),
            _opener=build_opener(ProxyHandler({})).open)
        self.expected, self.active_stage, self.stage_calls, self.total_calls = None, None, 0, 0

    def arm(self, label, preview=None, purpose=None):
        self.active_stage, self.stage_calls, self.expected = label, 0, None
        if preview is not None:
            preview=deepcopy(preview)
            wire = validate_preview(preview,purpose)
            self.expected = dict(purpose=purpose, endpoint=wire['endpoint'], wire_sha256=wire['wire_sha256'],
                task_sha256=digest(preview), payload_sha256=digest(preview['payload']),
                policy_sha256=text_sha(preview['policy']), output_mode='text' if purpose==PURPOSES[2] else 'json',
                preview=preview)
        return None if self.expected is None else {key:value for key,value in self.expected.items() if key!='preview'}

    def disarm(self):
        self.expected = None

    def post_json(self, **kwargs):
        # Disarming revokes future admission; an in-flight response still
        # belongs to the exact request that passed this boundary.
        expected, stage = deepcopy(self.expected), self.active_stage
        require(expected is not None and self.stage_calls==0 and self.total_calls<MAX_REQUESTS
            and not self.report.io_error_types, 'extra-or-unarmed-transport-request')
        require(kwargs['endpoint']==expected['endpoint'] and kwargs['timeout_seconds']==30
            and sha256(kwargs['body']).hexdigest()==expected['wire_sha256'], 'actual-http-wire-differs-from-preview')
        self.stage_calls+=1; self.total_calls+=1
        self.report.data['remote_calls']=self.total_calls
        row = dict(stage=stage, status='request-started', error_type=None,
            **{key:value for key,value in expected.items() if key!='preview'})
        self.report.data['transport'].append(row)
        self.report.checked_save('checkpoint-before-provider-failed')
        started=perf_counter()
        try:
            response=self.delegate.post_json(**kwargs)
            row.update(status='response-received',response_boundary=final_boundary(response,expected['purpose'],expected['preview']))
            return response
        except BaseException as error:
            row.update(status='transport-exception',error_type=type(error).__name__)
            raise
        finally:
            row['elapsed_seconds']=max(0.,perf_counter()-started)
            self.report.save()  # Never substitute an already received body.


def semantic_decision(line, statement_sha):
    """A single exact canonical review token; no retries or inferred approval."""
    if not line: raise NormalEnd('canonical-semantic-review-eof')
    try: value=strict_json(line)
    except Exception: raise AcceptanceStopped('canonical-semantic-review-token-invalid') from None
    require(type(value) is dict and set(value)=={'statement_sha256','decision'}
        and value['statement_sha256']==statement_sha and value['decision'] in ('continue','stop-out-of-scope'),
        'canonical-semantic-review-token-invalid')
    if value['decision']=='stop-out-of-scope': raise NormalEnd('canonical-working-understanding-out-of-scope')
    return value['decision']


class FirstRun:
    """Own one temporary server and entry; all mutations use its HTTP Adapter."""
    ROUTES = frozenset(('/', '/health', '/status', '/send', '/request-result', '/chat-archive',
        '/message-scope', '/reload', '/working-understanding', '/working-understanding-preview',
        '/working-understanding-form', '/working-understanding-request', '/working-activity-preview',
        '/working-activity-advance'))

    def __init__(self, root, scene, report):
        self.root, self.scene, self.report = root, scene, report
        self.entry_root, self.audit_path = root/'entry', root/'audit'
        self.transport, self.observations = ObservedTransport(report), []
        self.entry = self.server = self.server_thread = self.token = self.origin = None
        self.http_open = build_opener(ProxyHandler({})).open

    @property
    def product(self):
        return self.entry.product

    def audit(self):
        from dynamic_subject_agent.working_understanding_live import open_working_understanding_audit
        audit = list(open_working_understanding_audit(self.audit_path, technical_variant='fact-faithful').snapshot())
        require(len(audit) <= MAX_REQUESTS and all(row['purpose'] in PURPOSES for row in audit),
            'audit-purpose-or-count-unverified')
        self.report.data.update(audit=audit, audit_count=len(audit))
        return audit

    def counts(self):
        return len(self.audit())

    def view(self):
        sent = self.transport.total_calls
        result = self.product.application.query_working_understanding()
        require(status_of(result) == 'available' and type(result.view) is dict and sent == self.transport.total_calls,
            'canonical-working-view-unverified')
        return plain(result.view)

    def shared(self):
        sent = self.transport.total_calls
        result = self.product.application.query_shared_activity()
        require(status_of(result) == 'available' and type(result.view) is dict and sent == self.transport.total_calls,
            'canonical-shared-decision-unverified')
        return plain(result.view)

    def history(self):
        from dynamic_subject_agent.application import ApplicationQuery, ApplicationQueryKind
        sent = self.transport.total_calls
        result = self.product.application.query(ApplicationQuery(ApplicationQueryKind.CONVERSATION_HISTORY,
            self.product.profile_id, self.product.timeline_id))
        require(status_of(result) == 'available' and result.projection is not None and sent == self.transport.total_calls,
            'canonical-history-unverified')
        return plain(result.projection.turns)

    def fingerprint(self):
        return digest(dict(view=self.view(), shared=self.shared(), history=self.history()))

    def verify_support(self, preview, purpose, view):
        from dynamic_subject_agent.working_understanding import support_projection
        payload = preview['payload']
        evidence = payload['evidence'] if purpose == PURPOSES[2] else payload
        require(evidence['shared_experience'] is None
            and evidence['working_understanding'] == support_projection(view['visible_understanding']),
            'preview-working-support-differs-from-current-canonical-closure')
        if purpose == PURPOSES[2]:
            result = view['visible_result']
            expected = None if result is None else dict(kind=result['kind'], plan=result['plan'])
            require(evidence['activity_result'] == expected, 'reply-result-differs-from-current-canonical-closure')
        else:
            require(payload['current_plan'] == view['current_plan'], 'choice-plan-differs-from-current-canonical-closure')

    def http(self, route, payload=None):
        require(route in self.ROUTES and self.server is not None and self.server_thread.is_alive(),
            'owned-loopback-route-or-lifecycle-unverified')
        headers = {'Host': f'127.0.0.1:{self.server.server_port}'}
        if payload is None:
            request = Request(self.origin + route, headers=headers)
        else:
            headers.update({'Content-Type': 'application/json', 'X-Chat-Token': self.token, 'Origin': self.origin})
            request = Request(self.origin + route, data=canonical_json(payload).encode('utf-8'), headers=headers, method='POST')
        row = dict(stage=self.transport.active_stage, route=route, method=request.get_method(), status='started')
        self.report.data['http'].append(row)
        try:
            with self.http_open(request, timeout=6) as response:
                body = response.read(1048577)
                row.update(http_status=response.status, response_bytes=len(body), response_sha256=sha256(body).hexdigest())
                require(response.status == 200 and len(body) <= 1048576, 'entry-http-response-unverified')
            if route == '/':
                page = body.decode('utf-8')
                match = re.search(r"const TOKEN='([A-Za-z0-9_-]{32,128})'", page)
                require(match is not None, 'entry-session-token-unverified')
                self.token = match[1]
                value = None
            else:
                value = strict_json(body.decode('utf-8'))
                require(type(value) is dict, 'entry-http-object-required')
            row['status'] = 'received'
            return value
        except BaseException as error:
            row.update(status='unverified', error_type=type(error).__name__)
            raise
        finally:
            self.report.save()

    def verify_http_state(self, state):
        require(type(state) is dict and state.get('presentation_pending') is False
            and state.get('shared_pending') is False and state.get('working_pending') is False
            and state['history']['status'] == 'available' and state['character']['status'] == 'active',
            'entry-current-state-unverified')
        require(state['working_understanding']['status'] == state['shared_activity']['status'] == 'available'
            and state['working_understanding']['view'] == self.view()
            and state['shared_activity']['view'] == self.shared()
            and state['history']['turns'] == [dict(user_text=row['user_text'], assistant_text=row['assistant_text'])
                for row in self.history()], 'entry-http-state-differs-from-canonical')
        return state

    def opening(self):
        sys.path.insert(0, str(REPO/'app/desktop'))
        sys.path.insert(0, str(REPO/'scripts'))
        from serve_working_understanding_chat import WorkingUnderstandingChatEntry
        from working_understanding_chat import working_understanding_server, APPLICATION_ID
        self.entry = WorkingUnderstandingChatEntry(self.entry_root, live=False, transport=self.transport,
            audit_path=self.audit_path, observations=self.observations)
        self.server = working_understanding_server(self.product, reopen=self.entry.reopen, port=0)
        require(self.server.server_address[0] == '127.0.0.1' and self.server.server_port != 8794,
            'temporary-loopback-server-required')
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
        self.server_thread = Thread(target=self.server.serve_forever, name='s147-owned-acceptance-http', daemon=True)
        self.server_thread.start()
        self.report.data.update(service_started=True, temporary_loopback_server_started=True)
        require(self.http('/health') == dict(application=APPLICATION_ID), 'entry-application-unverified')
        self.http('/')
        self.verify_http_state(self.http('/status'))

    def close_server(self):
        if self.server is not None:
            self.server.shutdown(); self.server.server_close()
            self.server_thread.join(timeout=6)
            require(not self.server_thread.is_alive(), 'temporary-server-close-unverified')
            self.server = self.server_thread = self.token = self.origin = None

    def create(self):
        row = self.report.begin('create-independent-working-http-entry', maximum_requests=0)
        self.transport.arm(row['stage'])
        self.opening()
        view = self.view()
        require(not self.history() and view['current_plan'] is None and view['visible_understanding'] is None
            and view['visible_result'] is None and self.counts() == self.transport.total_calls == 0,
            'fresh-entry-or-zero-call-precondition-unverified')
        row.update(status='complete', audit_before=0, audit_after=0)
        self.report.checked_save('checkpoint-after-create-failed')

    def zero(self, label, action):
        before, sent = self.counts(), self.transport.total_calls
        row = self.report.begin(label, maximum_requests=0, audit_before=before)
        self.transport.arm(label)
        result = action()
        require(self.counts() == before and self.transport.total_calls == sent and not self.report.io_error_types,
            'zero-operation-produced-request-or-integrity-unknown')
        row.update(status='complete', audit_after=before, transport_count=0)
        self.report.checked_save('checkpoint-after-zero-operation-failed')
        return result

    def model_stage(self, label, purpose, preview, operation):
        before, sent, observed = self.counts(), self.transport.total_calls, len(self.observations)
        row = self.report.begin(label, purpose=purpose, maximum_requests=1, audit_before=before)
        row.update(**self.transport.arm(label, preview, purpose))
        self.report.checked_save('checkpoint-before-model-stage-failed')
        try:
            result = operation()
            row['status'] = status_of(result)
            row['problem_code'] = safe_problem_code(result.get('shared_problem_code'))
        except BaseException as error:
            row.update(status='failed-or-unverified', error_type=type(error).__name__)
            raise
        finally:
            self.transport.disarm()
            row.update(transport_count=self.transport.total_calls-sent,
                observations=[safe_observation(value) for value in self.observations[observed:]])
            try: row['audit_after'] = self.counts()
            except Exception as error:
                row.update(audit_after=None, audit_unverified=True, audit_error_type=type(error).__name__)
            self.report.save()
        require(not row.get('audit_unverified') and not self.report.io_error_types,
            'model-stage-audit-or-checkpoint-unverified')
        audit = self.audit()
        require(self.counts()-before <= 1 and self.transport.total_calls-sent <= 1, 'single-stage-request-bound-exceeded')
        require(row['status'] in ('terminal', 'committed', 'replayed', 'no-op') and result.get('ok') is True,
            'first-technical-failure-'+row['status'])
        require(self.counts()-before == self.transport.total_calls-sent == 1, 'stage-without-one-verified-request')
        raw = self.report.data['transport'][-1].get('response_boundary', {})
        require(raw.get('exact_output_contract') is True and audit[-1]['status'] == 'complete'
            and audit[-1]['purpose'] == purpose and audit[-1]['request_digest'] == digest(preview)
            and audit[-1]['output_digest'] == raw.get('final_value_sha256'), 'raw-http-audit-or-preview-mismatch')
        self.verify_http_state(result['state'])
        row['raw_http_matches_completed_audit'] = True
        self.report.checked_save('checkpoint-after-model-stage-failed')
        return result, row, raw

    def ordinary_operation(self, request):
        value = self.http('/send', request)
        deadline = perf_counter()+150
        while value.get('pending') is not None:
            require(perf_counter() < deadline, 'entry-original-request-still-pending')
            require(value.get('ok') is True and value.get('request_id') == request['request_id'],
                'entry-original-request-handle-unverified')
            sleep(.15)
            value = self.http('/request-result', request)
        require(value.get('request_id') == request['request_id'], 'entry-original-reply-nonce-unverified')
        status = 'terminal' if value.get('settled') is True and value.get('ok') is True else (
            'failed-closed' if value.get('settled') is True else 'unknown')
        return dict(value, status=status)

    def shared_operation(self, kind, request):
        route = '/working-understanding-form' if kind == 'form' else '/working-activity-advance'
        value = self.http(route, request)
        deadline = perf_counter()+150
        while value.get('shared_status') == 'busy':
            require(perf_counter() < deadline, 'entry-original-shared-request-still-busy')
            require(value.get('shared_request_id') == request['request_id'], 'entry-original-shared-request-unverified')
            sleep(.15)
            value = self.http('/working-understanding-request', dict(kind=kind, request=request))
        require(value.get('shared_request_id') == request['request_id'] and value.get('shared_kind') == kind,
            'entry-original-shared-nonce-unverified')
        if value.get('shared_status') in ('committed','replayed','no-op'):
            require(value.get('shared_settled') is True and type(value.get('shared_receipt')) is dict,
                'entry-settled-receipt-unverified')
        return dict(value, status=value.get('shared_status'))

    def reply(self, label, text, *, expected_plan=None):
        before = self.history()
        candidate = self.product.application.preview_working_activity('reply', text)
        require(status_of(candidate) == 'previewed', 'reply-preview-'+status_of(candidate))
        preview = plain(candidate.view); payload = preview['payload']
        self.verify_support(preview, PURPOSES[2], self.view())
        require(payload['turn']['current_message'] == text, 'reply-current-message-differs')
        if expected_plan is not None:
            require(payload['evidence']['activity_result']['plan'] == expected_plan,
                'reply-preview-differs-from-committed-result')
        scope = self.zero(label+'-scope-zero-model', lambda: self.http('/message-scope', dict(text=text)))
        require(scope.get('ok') is True
            and scope['message_scope']['working_understanding'] == payload['evidence']['working_understanding'],
            'entry-message-scope-differs-from-actual-preview')
        request = dict(text=text, request_id=str(uuid4()))
        _, row, raw = self.model_stage(label, PURPOSES[2], preview, lambda: self.ordinary_operation(request))
        history = self.history()
        require(len(history) == len(before)+1 and history[-1]['user_text'] == text, 'canonical-complete-round-missing')
        canonical = dict(reply_text=history[-1]['assistant_text'], language='zh')
        require(text_sha(canonical['reply_text']) == raw['reply_sha256'] and digest(canonical) == raw['final_value_sha256'],
            'raw-final-reply-differs-from-canonical')
        row.update(raw_reply_equals_canonical=True, canonical_head_sequence=history[-1]['head_sequence'],
            canonical_reply_sha256=raw['reply_sha256'], reply_chars=raw['reply_chars'])
        self.report.checked_save('checkpoint-after-canonical-reply-failed')
        return history[-1]['head_sequence']

    def choice(self, label, *, initial=False):
        before = self.view()
        candidate = self.product.application.preview_working_activity('choice')
        require(status_of(candidate) == 'previewed', 'choice-preview-'+status_of(candidate))
        preview = plain(candidate.view)
        self.verify_support(preview, PURPOSES[1], before)
        shown = self.zero(label+'-preview-zero-model', lambda: self.http('/working-activity-preview', {}))
        require(shown.get('ok') is True and shown['shared_preview'] == {key:preview['payload'][key]
            for key in ('current_activity', 'current_plan', 'working_understanding')}, 'entry-choice-preview-differs')
        if initial:
            require(before['current_plan'] is None and before['visible_understanding'] is None,
                'first-plan-is-not-independent-empty-baseline')
        request = dict(request_id=str(uuid4()), expected_revision=before['revision'])
        result, row, raw = self.model_stage(label, PURPOSES[1], preview,
            lambda: self.shared_operation('advance', request))
        view, shared = self.view(), self.shared(); decision = shared['decision']
        canonical = dict(action=decision['action'], plan=shared['current_plan'] if decision['action'] in ('start','revise') else None,
            reason_code=decision['reason_code'], basis_refs=decision['basis_refs'], decision_note=decision['decision_note'])
        require(digest(canonical) == raw['final_value_sha256'], 'raw-choice-differs-from-canonical')
        row.update(raw_choice_equals_canonical=True, action=canonical['action'], canonical_plan_sha256=digest(view['current_plan']),
            receipt_sha256=digest(result.get('shared_receipt')))
        self.report.checked_save('checkpoint-after-canonical-choice-failed')
        if canonical['action'] not in ('start','revise') or view['current_plan'] is None:
            raise NormalEnd('no-eligible-new-plan' if initial else 'no-actual-plan-change')
        if view['current_plan'] == before['current_plan']:
            raise NormalEnd('no-actual-plan-change')
        require(view['visible_result']['plan'] == view['current_plan'], 'canonical-result-does-not-match-plan')
        if initial:
            require(view['visible_result']['source_dependencies'] == [], 'first-A1-plan-has-dependent-sources')
        else:
            require(preview['payload']['working_understanding'] is not None, 'later-choice-without-working-understanding')
        return request, view['current_plan']

    def form(self, label, sources, *, activity_plan=None):
        from dynamic_subject_agent.working_understanding import WorkingSourceQuote, WorkingUnderstandingRequest
        before = self.view()
        request = dict(request_id=str(uuid4()), expected_revision=before['revision'],
            sources=[dict(source_head_sequence=head, quote=quote) for head,quote in sources], confirmed=True)
        qualified = WorkingUnderstandingRequest(self.product.profile_id, self.product.timeline_id,
            request['request_id'], request['expected_revision'], tuple(WorkingSourceQuote(head,quote) for head,quote in sources), confirmed=True)
        candidate = self.product.application.preview_working_understanding(qualified)
        require(status_of(candidate) == 'previewed', 'form-preview-'+status_of(candidate))
        preview = plain(candidate.view)
        expected_activity = None if activity_plan is None else dict(label='A1', kind='composition-text', plan=activity_plan)
        exchanges = [dict(label='U'+str(i+1), quote=quote) for i,(_,quote) in enumerate(sources)]
        require(preview['payload']['exchanges'] == exchanges and preview['payload']['activity_result'] == expected_activity,
            'form-input-differs-from-selected-canonical-sources')
        archive = self.zero('select-two-committed-http-sources-zero-model',
            lambda: self.http('/chat-archive', dict(query='', before_sequence=None)))
        require(archive.get('ok') is True and all(any(row['head_sequence'] == head and quote in row['user_text']
            for row in archive['archive']['rows']) for head,quote in sources), 'entry-selected-archive-source-unverified')
        shown = self.zero('form-preview-zero-model',
            lambda: self.http('/working-understanding-preview', dict(request, confirmed=False)))
        require(shown.get('ok') is True and shown['working_preview'] == {key:preview['payload'][key]
            for key in ('scope','exchanges','activity_result')}, 'entry-form-preview-differs')
        result, row, raw = self.model_stage(label, PURPOSES[0], preview, lambda: self.shared_operation('form', request))
        view = self.view()
        if raw['formation_status'] == 'insufficient':
            require(status_of(result) == 'no-op' and result.get('shared_problem_code') == 'working-understanding-insufficient'
                and view['formation_status'] == 'insufficient' and view['understanding'] == before['understanding'],
                'insufficient-is-not-typed-noop-or-lost-prior-understanding')
            row['typed_insufficient_noop'] = True
            self.report.checked_save('checkpoint-after-insufficient-noop-failed')
            raise NormalEnd('working-understanding-insufficient')
        require(status_of(result) in ('committed','replayed') and view['formation_status'] == 'formed'
            and view['visible_understanding'] is not None, 'formed-understanding-not-visible')
        understanding = view['visible_understanding']
        canonical = dict(status='formed', scope=understanding['scope'], statement=understanding['statement'], basis_refs=understanding['basis_refs'])
        require(digest(canonical) == raw['final_value_sha256']
            and [(x['source_head_sequence'],x['quote']) for x in understanding['sources']] == sources,
            'raw-form-or-committed-sources-differ')
        actual = understanding['activity_result']
        require((actual is None and activity_plan is None) or (actual is not None and actual['kind'] == 'composition-text'
            and actual['plan'] == activity_plan), 'committed-A1-differs-from-independent-plan')
        row.update(raw_form_equals_canonical=True, canonical_statement_sha256=text_sha(understanding['statement']),
            canonical_understanding_sha256=digest(understanding), canonical_head_sequence=result['shared_receipt']['head_sequence'])
        self.report.checked_save('checkpoint-after-canonical-form-failed')
        self.semantic_gate(label, understanding, row['canonical_head_sequence'])

    def semantic_gate(self, label, understanding, head):
        statement_sha = text_sha(understanding['statement'])
        gate = dict(stage=label, canonical_head_sequence=head, statement_sha256=statement_sha,
            understanding_sha256=digest(understanding), current_plan_sha256=digest(self.view()['current_plan']), status='awaiting')
        self.report.data['semantic_reviews'].append(gate)
        self.report.data['status'] = 'awaiting-canonical-semantic-review'
        self.report.checked_save('checkpoint-before-semantic-review-failed')
        print(json.dumps({**gate, 'status':'awaiting-canonical-semantic-review'}, ensure_ascii=False), flush=True)
        try:
            decision = semantic_decision(sys.stdin.readline(512), statement_sha)
        except BaseException as error:
            gate.update(status='stopped', stop_code=error.code if isinstance(error,AcceptanceStopped) else 'semantic-review-input-failed')
            self.report.save(); raise
        gate.update(status='accepted', decision=decision)
        self.report.data['status'] = 'running'
        self.report.checked_save('checkpoint-after-semantic-review-failed')

    def reopen(self):
        fingerprint = self.fingerprint()
        def action():
            self.close_server()
            self.entry.close(); self.entry = None
            self.opening()
            require(self.fingerprint() == fingerprint, 'reopen-changed-canonical-business-state')
        self.zero('close-and-reopen-zero-model', action)

    def nonce(self, request):
        fingerprint = self.fingerprint()
        result = self.zero('same-nonce-read-zero-model', lambda: self.http('/working-understanding-request',
            dict(kind='advance', request=request)))
        require(result.get('shared_status') == 'replayed' and self.fingerprint() == fingerprint,
            'same-nonce-changed-state-or-not-replayed')
        self.verify_http_state(result['state'])

    def close(self):
        self.transport.disarm()
        first_error = None
        try: self.close_server()
        except BaseException as error: first_error = error
        try:
            if self.entry is not None:
                self.entry.close(); self.entry = None
        except BaseException as error:
            if first_error is None: first_error = error
        self.report.data['temporary_loopback_server_closed'] = self.server is None
        if first_error is not None: raise first_error


def execute_scene(run, scene):
    """One fixed branch; the first stop prevents every following operation."""
    heads = [run.reply('source-reply-'+str(i+1), text) for i,text in enumerate(scene['source_messages'])]
    _, first_plan = run.choice('independent-choice-1', initial=True)
    run.form('form-from-two-quotes-and-actual-plan', list(zip(heads,scene['source_quotes'])), activity_plan=first_plan)
    for label,text in zip(('name-is-not-appearance-probe', 'story-topic-gap'),scene['gap_messages'],strict=True):
        run.reply(label, text)
    require(all(row['head_sequence'] not in heads for row in run.history()[-2:]), 'selected-sources-still-in-recent-two-window')
    run.reopen()
    request, plan = run.choice('choice-using-valid-understanding')
    run.nonce(request)
    run.reply('result-reply', scene['result_question'], expected_plan=plan)


def self_check():
    """Pure fixtures; never construct a product, transport or credential resolver."""
    from dynamic_subject_agent.deepseek import DeepSeekHttpResponse
    marker = 'PRIVATE_FIXTURE_FINAL_AND_REASONING'
    reply = dict(model='deepseek-flash', usage=dict(prompt_tokens=1,completion_tokens=2), choices=[dict(
        finish_reason='stop',message=dict(role='assistant',content='合成完整短回复。',reasoning_content=marker))])
    raw = final_boundary(DeepSeekHttpResponse(200,json.dumps(reply).encode()), PURPOSES[2], {})
    require(raw['exact_output_contract'] and marker not in json.dumps(raw), 'self-check-private-boundary-exported')
    statement_sha = '1'*64
    require(semantic_decision(json.dumps(dict(statement_sha256=statement_sha,decision='continue')),statement_sha) == 'continue',
        'self-check-semantic-continue-failed')
    rejected = 0
    for line in ('', json.dumps(dict(statement_sha256='2'*64,decision='continue')),
        json.dumps(dict(statement_sha256=statement_sha,decision='unknown')),
        json.dumps(dict(statement_sha256=statement_sha,decision='stop-out-of-scope'))):
        try: semantic_decision(line,statement_sha)
        except AcceptanceStopped: rejected += 1
        else: raise AcceptanceStopped('self-check-semantic-gate-opened')
    return dict(status='self-check-passed', semantic_gate_rejections=rejected, private_text_exported=False,
        product_roots_created=0, product_opened=False, transport_created=False, temporary_server_created=False,
        remote_calls=0, credential_reads=0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--self-check', action='store_true'); modes.add_argument('--preflight', action='store_true')
    modes.add_argument('--execute', action='store_true'); args = parser.parse_args(argv)
    report = run = None
    try:
        if args.self_check:
            print(json.dumps(self_check(),ensure_ascii=False),flush=True); return 0
        scene, root, contract_sha = preflight()
        if args.preflight:
            print(json.dumps(dict(status='preflight-passed',review_basis=REVIEW_BASIS,scene_sha256=SCENE_SHA,
                runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),maximum_first_requests=MAX_REQUESTS,
                product_roots_created=0,product_opened=False,transport_created=False,temporary_server_created=False,
                remote_calls=0,credential_reads=0)),flush=True)
            return 0
        root.mkdir(parents=True,exist_ok=False)
        report = SafeReport(root,contract_sha); report.checked_save('initial-checkpoint-failed')
        run = FirstRun(root,scene,report); run.create(); execute_scene(run,scene)
        require(run.counts() == run.transport.total_calls == MAX_REQUESTS, 'complete-scene-request-count-unverified')
        report.data.update(status='complete-first-engineering-scene',runner_exit_code=0,
            main_canonical_form_semantic_reviews=1,real_server_product_reopen_verified=True)
        report.checked_save('final-complete-checkpoint-failed')
    except BaseException as error:
        if report is None:
            print(json.dumps(dict(status='preflight-stopped',error_type=type(error).__name__,
                stop_code=error.code if isinstance(error,AcceptanceStopped) else 'unexpected-preflight-failure',
                product_roots_created=0,remote_calls=0,credential_reads=0)),flush=True)
            return 1
        report.stop(error)
    finally:
        if run is not None:
            try: run.close()
            except BaseException as error:
                report.data['close_error_type'] = type(error).__name__
                report.stop(AcceptanceStopped('final-entry-or-server-close-unverified'))
            try:
                if run.audit_path.exists(): run.audit()
            except BaseException as error:
                report.data['final_audit_error_type'] = type(error).__name__
                report.stop(AcceptanceStopped('final-audit-unverified'))
        if report is not None:
            if not report.save() or report.io_error_types:
                report.stop(AcceptanceStopped('final-checkpoint-unverified'))
            print(json.dumps({key:report.data.get(key) for key in ('status','runner_exit_code','stop_code',
                'maximum_first_requests','remote_calls','audit_count','automatic_retries','production_service_started',
                'temporary_loopback_server_started','temporary_loopback_server_closed','raw_text_exported',
                'reasoning_text_exported','real_cross_day_verified','character_effect_verified')},
                ensure_ascii=False),flush=True)
    return 0 if report is None else report.data.get('runner_exit_code',1)


if __name__ == '__main__':
    raise SystemExit(main())
