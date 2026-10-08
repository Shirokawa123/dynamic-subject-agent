"""One S144 initial pair and the same candidate continuation, main-owned.

--preflight and --self-check never open a product, service, credential or model.
--execute is bounded to seven first requests, one per stage and zero retries.
Only closed metadata/counts/hashes leave memory; successful text stays canonical.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import Thread
from time import perf_counter
from urllib.request import ProxyHandler, build_opener
from uuid import uuid4

import run_s142_live_acceptance as base
import run_s143_entry_acceptance as entry_base
from dynamic_subject_agent.deepseek import DeepSeekTransport, DeepSeekUrlLibTransport
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind

REPO = Path(__file__).resolve().parents[1]
REVIEW_BASIS, SCENARIO_SHA, PURPOSES = base.REVIEW_BASIS, base.SCENARIO_SHA, base.PURPOSES
SCENE_PATH = REPO/'docs/experiments/s144/scene.json'
SCENE_SHA = '307ff255ca652a7bdabc329b82f7ce59af6a117b45ad6680cc85b6a02d44a77d'
OUTPUT = REPO/'docs/reports/2026-10-08-slice-144/live-acceptance-metadata.json'
TEMP_PARENT = REPO/'.tmp-s144-acceptance-parent'
ROOTS = {branch: Path('DynamicSubjectAgent/living-activity-development/s144')/
    ('live-'+branch+'-first-20261008-1') for branch in ('baseline', 'candidate')}
HELPER_PINS = {
    'run_s142_live_acceptance.py': '50e9998db00185271a0c20464bf05aef2fd885760864f6c932662b7d833efd64',
    'run_s143_entry_acceptance.py': 'f69b2d4f04bbc2eee1037c5dcf245f6cbb2ea8841d2f2150e59ff6d8df7859a6'}
LEGACY_METADATA = REPO/'docs/reports/2026-10-07-slice-143/live-entry-metadata.json'
LEGACY_METADATA_SHA = 'c18eeda0d76627c3f2e58f557351fd4ae02f4509a9c1d18f12de7d5fde175184'
CANDIDATE_VARIANT = 'final-text'
AcceptanceStopped, require = base.AcceptanceStopped, base.require
plain, digest = base.plain, base.digest


def validate_preview(preview, purpose):
    """Use the actual closed Python projection validator, including no result."""
    from dynamic_subject_agent.living_activity_live import validate_living_request_payload
    require(type(preview) is dict and set(preview) == {'policy', 'payload'}
        and type(preview['policy']) is str, 'closed-living-preview-required')
    validate_living_request_payload(ModelTask(ModelTaskKind(purpose), preview))
    payload = preview['payload']
    evidence = payload['evidence'] if purpose == PURPOSES[2] else payload
    require(evidence['shared_experience'] is None, 'this-scene-requires-no-E1')
    if purpose == PURPOSES[2]:
        require(payload['turn']['history_enabled'] is True, 'this-scene-requires-history-on')


def wire_preview(preview, purpose, variant):
    from dynamic_subject_agent.living_activity_remote_preview import living_remote_request_preview
    task = ModelTask(ModelTaskKind(purpose), preview)
    return living_remote_request_preview(task, technical_variant=variant)


def preflight():
    """Pure reads/validation; immutable evidence and unused roots stay intact."""
    from dynamic_subject_agent.original_whole_chat import APPROVED_BINDING
    from dynamic_subject_agent.living_activity_live import (
        ApprovedLivingActivityGrant, LivingFinalTextDevelopmentGrant, FINAL_TEXT_DEVELOPMENT_AUTHORIZATION,
        FINAL_TEXT_POLICY_HASHES, FINAL_TEXT_PROTOCOL_HASHES)
    review = json.loads((REPO/'docs/experiments/s142/review.json').read_text(encoding='utf-8'))
    scenarios = json.loads((REPO/'docs/experiments/s142/scenarios.json').read_text(encoding='utf-8'))
    scene = json.loads(SCENE_PATH.read_text(encoding='utf-8'))
    require(review['review_basis'] == digest(review['review']) == REVIEW_BASIS, 'approved-review-pin-changed')
    require(digest(scenarios) == SCENARIO_SHA == review['review']['scenario_sha256'], 'approved-scenarios-changed')
    require(digest(scene) == SCENE_SHA and scene['base_review_basis'] == REVIEW_BASIS
        and scene['approved_scenario_sha256'] == SCENARIO_SHA, 's144-scene-pin-changed')
    require(APPROVED_BINDING == review['review']['material_binding']
        and digest(APPROVED_BINDING) == scene['material_binding_sha256'], 'approved-binding-changed')
    require(scene['followup_messages'] == scenarios['followup_messages'], 'approved-followups-changed')
    require(type(scene['initial_message']) is str and 0 < len(scene['initial_message']) <= 1000,
        'initial-current-message-bound-changed')
    require(scene['candidate_technical_variant'] == CANDIDATE_VARIANT, 'candidate-variant-changed')
    require(scene['baseline_protocol'] == review['review']['protocol']
        and scene['baseline_policy_sha256'] == review['review']['policy_sha256'], 'legacy-protocol-or-policy-changed')
    raw_protocol = dict(scene['baseline_protocol'])
    raw_protocol.pop('response_format')
    require(scene['candidate_protocol_by_purpose'] == {purpose:raw_protocol if purpose == PURPOSES[2]
        else scene['baseline_protocol'] for purpose in PURPOSES}, 'candidate-protocol-expands-approved-use')
    ApprovedLivingActivityGrant(REVIEW_BASIS, True).validate()
    require(scene['development_authorization'] == FINAL_TEXT_DEVELOPMENT_AUTHORIZATION
        == 'user-continued-same-use-final-text-development-2026-10-07', 'same-use-development-authorization-changed')
    LivingFinalTextDevelopmentGrant(REVIEW_BASIS, FINAL_TEXT_DEVELOPMENT_AUTHORIZATION).validate()
    require(scene['candidate_policy_sha256'] == dict(zip(PURPOSES, FINAL_TEXT_POLICY_HASHES, strict=True))
        and scene['candidate_full_protocol_sha256'] == dict(zip(PURPOSES, FINAL_TEXT_PROTOCOL_HASHES, strict=True)),
        'candidate-policy-or-full-protocol-metadata-differs')
    contract = scene['scene']
    require(contract['time_is_simulated'] is True and contract['maximum_first_requests'] == 7
        and contract['stage_request_limit'] == 1 and contract['automatic_retries'] == 0
        and contract['initial_pairs'] == 1 and contract['candidate_continuations'] == 1
        and all(contract[key] is True for key in ('stop_candidate_on_first_technical_failure',
            'stop_when_no_eligible_new_text_plan', 'stop_when_share_false',
            'retain_first_result_without_resampling', 'baseline_failure_does_not_cancel_preplanned_candidate',
            'stop_all_on_unknown_io_audit_pins_or_integrity')),
        'bounded-first-scene-contract-changed')
    require(scene['report'] == OUTPUT.relative_to(REPO).as_posix(), 'independent-report-changed')
    for name, pin in HELPER_PINS.items():
        require(sha256((REPO/'scripts'/name).read_bytes()).hexdigest() == pin, 'legacy-safe-helper-changed')
    require(sha256(LEGACY_METADATA.read_bytes()).hexdigest() == LEGACY_METADATA_SHA, 'legacy-failure-evidence-changed')
    local = Path(os.environ.get('LOCALAPPDATA', ''))
    require(local.is_absolute() and local.resolve() == Path('C:/Users/30252/AppData/Local').resolve(),
        'real-local-appdata-required')
    roots = {branch: local/relative for branch,relative in ROOTS.items()}
    require(scene['resources'] == {branch: 'LOCALAPPDATA/'+relative.as_posix()
        for branch,relative in ROOTS.items()}, 'independent-roots-changed')
    require(all(not root.exists() for root in roots.values()) and not OUTPUT.exists()
        and not OUTPUT.with_name(OUTPUT.name+'.next').exists(), 'first-resources-already-exist-retained')
    require(OUTPUT.parent.is_dir(), 'report-directory-required')
    require(TEMP_PARENT.is_dir() and all(Path(os.environ.get(key, '')).is_absolute()
        and Path(os.environ[key]).resolve() == TEMP_PARENT.resolve() for key in ('TEMP', 'TMP')),
        'own-repo-temp-parent-required')
    require(os.environ.get('NO_PROXY', '').split(',') == ['127.0.0.1', 'localhost', '::1', 'api.deepseek.com'],
        'process-scoped-no-proxy-required')
    return scene, roots


class SafeReport(base.SafeReport):
    """One independent atomic metadata sink; old report writers never run."""
    def __init__(self, roots, scene):
        super().__init__(roots['candidate'], scene)
        self.active_branch, self.scene = None, scene
        self.data.update(version='s144-initial-pair-candidate-chain-1', base_review_basis=REVIEW_BASIS,
            scene_sha256=SCENE_SHA, runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
            maximum_first_requests=7, independent_roots={key:str(value) for key,value in roots.items()},
            legacy_failure_metadata_sha256=LEGACY_METADATA_SHA, legacy_helper_sha256=HELPER_PINS,
            branches={key:dict(status='not-started', technical_variant='baseline' if key == 'baseline' else CANDIDATE_VARIANT,
                audit=[], audit_count=0, transport_count=0) for key in roots}, first_failure=None,
            simulated_choice=True, real_900_seconds_repeated=False, automatic_system_service=False,
            source_deactivation_product_causality_verified=False, no_source_deactivation_publication=True,
            person_content_assessment='main-review-required', status='preparing')
        self.data.pop('audit', None)
        self.data.pop('independent_root', None)
        self.data.pop('first_scene_sha256', None)

    def save(self):
        with self.lock:
            try:
                self.data['checkpoint_io_error_types'] = self.io_error_types[:]
                temporary = OUTPUT.with_name(OUTPUT.name+'.next')
                temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
                temporary.replace(OUTPUT)
                return True
            except Exception as error:
                name = type(error).__name__
                if name not in self.io_error_types:
                    self.io_error_types.append(name)
                return False

    def begin(self, label, **metadata):
        row = dict(stage=label, branch=self.active_branch, status='started', error_type=None,
            time_is_simulated=True, **metadata)
        with self.lock:
            self.data['stages'].append(row)
            self.checked_save('checkpoint-before-stage-failed')
        return row

    def failure(self, branch, stage, code, error_type):
        failure = dict(branch=branch, stage=stage, stop_code=code, error_type=error_type)
        if self.data['first_failure'] is None:
            self.data['first_failure'] = failure
        self.data['branches'][branch].update(status='stopped-on-first-technical-failure', **failure)
        self.data['runner_exit_code'] = 1


def final_boundary(response, purpose, output_mode):
    """Transient purpose-aware strict parse; never retain raw or reasoning text."""
    from observe_whole_reply_boundaries import response_metadata
    from dynamic_subject_agent.deepseek import DEEPSEEK_MODEL
    row = response_metadata(response)
    row.update(output_mode=output_mode, exact_task_schema=False, exact_output_contract=False,
        strict_envelope=False, final_value_sha256=None, wrapped_model_result_value_sha256=None,
        final_text_sha256=None, plan_sha256=None, reply_sha256=None, reply_chars=None, action=None, share=None)
    duplicates = []
    watched = {'choices', 'message', 'role', 'finish_reason', 'delta', 'content', 'reasoning_content',
        'final', 'refusal', 'tool_calls', 'model', 'usage', 'prompt_tokens', 'completion_tokens',
        'share', 'reply_text', 'language', 'action', 'plan', 'subject', 'composition', 'focus',
        'reason_code', 'basis_refs', 'decision_note'}
    def pairs(items):
        value = {}
        for key,item in items:
            if key in value and key in watched:
                duplicates.append(True)
            value[key] = item
        return value
    def invalid_constant(_value):
        raise ValueError('non-JSON-number')
    try:
        envelope = json.loads(response.body.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid_constant)
        row['duplicate_semantic_keys'] = bool(duplicates)
        if type(envelope) is not dict:
            return row
        choices, usage = envelope.get('choices'), envelope.get('usage')
        if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
            return row
        choice = choices[0]; message = choice.get('message')
        if type(message) is not dict:
            return row
        content = message.get('content')
        # Reasoning is discarded; its type is checked without using its text.
        row['strict_envelope'] = (response.status_code == 200 and type(response.body) is bytes
            and len(response.body) <= 65536 and envelope.get('model') in (DEEPSEEK_MODEL, 'deepseek-flash')
            and message.get('role') == 'assistant' and choice.get('finish_reason') == 'stop'
            and 'delta' not in choice and message.get('tool_calls') in (None, [])
            and message.get('refusal') in (None, '') and message.get('final') in (None, '')
            and (message.get('reasoning_content') is None or type(message.get('reasoning_content')) is str)
            and type(usage) is dict and type(usage.get('prompt_tokens')) is int and usage['prompt_tokens'] >= 0
            and type(usage.get('completion_tokens')) is int and 0 <= usage['completion_tokens'] <= 4096
            and not duplicates)
        if type(content) is not str or not content.strip():
            return row
        row['final_text_sha256'] = sha256(content.encode('utf-8')).hexdigest()
        if purpose == PURPOSES[2] and output_mode == 'text':
            value = dict(reply_text=content, language='zh')
            valid = len(content) <= 1200 and '\x00' not in content
        else:
            value = json.loads(content, object_pairs_hook=pairs, parse_constant=invalid_constant)
            if type(value) is not dict:
                return row
            if purpose == PURPOSES[0]:
                from dynamic_subject_agent.first_life import validate_plan, LIFE_REASONS
                fields = {'action', 'plan', 'reason_code', 'basis_refs', 'decision_note'}
                valid = set(value) == fields and value.get('action') in ('start', 'revise', 'keep', 'rework', 'defer')
                if value.get('plan') is not None:
                    validate_plan(value['plan'])
                valid = valid and value.get('basis_refs') in ([], ['E1']) \
                    and value.get('reason_code') in LIFE_REASONS \
                    and type(value.get('decision_note')) is str and 0 < len(value['decision_note'].strip()) \
                    and len(value['decision_note']) <= 160 \
                    and '\x00' not in value['decision_note']
            elif purpose == PURPOSES[1]:
                from dynamic_subject_agent.living_activity import validate_share
                validate_share(value); valid = True
            else:
                from dynamic_subject_agent.original_whole_chat import validate_whole_reply
                validate_whole_reply(value); valid = True
        row['duplicate_semantic_keys'] = bool(duplicates)
        row['exact_task_schema'] = valid and not duplicates
        row['exact_output_contract'] = row['strict_envelope'] and row['exact_task_schema'] and not duplicates
        row['final_value_sha256'] = digest(value)
        row['wrapped_model_result_value_sha256'] = digest(value) if output_mode == 'text' else None
        if purpose == PURPOSES[0]:
            row['action'] = value.get('action') if value.get('action') in ('start', 'revise', 'keep', 'rework', 'defer') else 'other'
            row['plan_sha256'] = None if value.get('plan') is None else digest(value['plan'])
        elif type(value.get('reply_text')) is str:
            row['reply_chars'] = len(value['reply_text'])
            row['reply_sha256'] = sha256(value['reply_text'].encode('utf-8')).hexdigest()
            row['share'] = value.get('share') if type(value.get('share')) is bool else None
        return row
    except (ValueError, UnicodeError, TypeError, KeyError, IndexError, AttributeError):
        row['duplicate_semantic_keys'] = bool(duplicates)
        return row


class ObservedTransport(DeepSeekTransport):
    def __init__(self, report, branch, variant):
        from dynamic_subject_agent.local_product import _WindowsLabResolver
        self.delegate = DeepSeekUrlLibTransport(credential_resolver=_WindowsLabResolver())
        self.report, self.branch, self.variant = report, branch, variant
        self.expected, self.active_stage = None, None
        self.stage_calls, self.total_calls, self.allowed = 0, 0, 0

    def arm(self, label, preview=None, purpose=None):
        self.active_stage, self.stage_calls = label, 0
        self.allowed, self.expected = (0 if preview is None else 1), None
        if preview is not None:
            validate_preview(preview, purpose)
            wire = wire_preview(preview, purpose, self.variant)
            output_mode = 'text' if self.branch == 'candidate' and purpose == PURPOSES[2] else 'json'
            policy_sha = sha256(preview['policy'].encode()).hexdigest()
            scene = self.report.scene
            expected_protocol = scene['baseline_protocol'] if self.branch == 'baseline' \
                else scene['candidate_protocol_by_purpose'][purpose]
            require(policy_sha == scene[self.branch+'_policy_sha256'][purpose]
                and {key:value for key,value in wire['body'].items() if key != 'messages'} == expected_protocol,
                'actual-policy-or-protocol-differs-from-scene')
            self.expected = dict(branch=self.branch, purpose=purpose, endpoint=wire['endpoint'],
                wire_sha256=wire['wire_sha256'], task_sha256=digest(preview), output_mode=output_mode,
                payload_sha256=digest(preview['payload']), policy_sha256=policy_sha)
        return deepcopy(self.expected)

    def post_json(self, **kwargs):
        require(self.expected is not None and self.allowed == 1 and self.stage_calls == 0
            and sum(item['transport_count'] for item in self.report.data['branches'].values()) < 7
            and self.total_calls < (1 if self.branch == 'baseline' else 6) and not self.report.io_error_types,
            'unapproved-extra-transport-request')
        require(kwargs['endpoint'] == self.expected['endpoint'] and kwargs['timeout_seconds'] == 30
            and sha256(kwargs['body']).hexdigest() == self.expected['wire_sha256'], 'actual-wire-differs-from-preview')
        self.stage_calls += 1; self.total_calls += 1
        self.report.data['branches'][self.branch]['transport_count'] = self.total_calls
        row = dict(stage=self.active_stage, status='request-started', error_type=None, **deepcopy(self.expected))
        self.report.data['transport'].append(row)
        self.report.checked_save('checkpoint-before-provider-failed')
        started = perf_counter()
        try:
            response = self.delegate.post_json(**kwargs)
            row.update(status='response-received', response_boundary=final_boundary(response,
                self.expected['purpose'], self.expected['output_mode']))
            return response
        except BaseException as error:
            row.update(status='transport-exception', error_type=type(error).__name__)
            raise
        finally:
            row['elapsed_seconds'] = max(0.0, perf_counter()-started)
            self.report.save()  # Metadata I/O never substitutes a received body.


class BranchRun(entry_base.EntryRun):
    def __init__(self, root, scene, report, branch):
        super().__init__(root, scene, report)
        self.branch = branch
        self.variant = 'baseline' if branch == 'baseline' else CANDIDATE_VARIANT

    def activate(self):
        self.report.active_branch = self.branch

    def counts(self):
        return self.audit_store().counts()[1]

    def audit_store(self):
        from dynamic_subject_agent.living_activity_live import open_living_activity_audit
        return open_living_activity_audit(self.audit_path, technical_variant=self.variant)

    def audit(self):
        value = list(self.audit_store().snapshot())
        state = self.report.data['branches'][self.branch]
        state.update(audit=value, audit_count=len(value))
        self.report.data['audit_count'] = sum(item['audit_count'] for item in self.report.data['branches'].values())
        require(len(value) <= (1 if self.branch == 'baseline' else 6)
            and self.report.data['audit_count'] <= 7, 'first-request-bound-exceeded')
        return value

    def zero(self, label, action):
        self.activate()
        before, sent = self.counts(), self.transport.total_calls
        row = self.report.begin(label, maximum_requests=0, audit_before=before, transport_before=sent)
        self.transport.arm(label)
        try:
            result = action()
        except BaseException as error:
            row.update(status='failed-or-unverified', error_type=type(error).__name__)
            raise
        finally:
            row.update(transport_after=self.transport.total_calls,
                transport_count=self.transport.total_calls-sent)
            try:
                row['audit_after'] = self.counts(); self.audit()
            except Exception as error:
                row.update(audit_after=None, audit_unverified=True, audit_error_type=type(error).__name__)
                self.report.unverified('zero-stage-audit-unverified')
            self.report.save()
        require(row.get('audit_unverified') is not True and self.counts() == before
            and self.transport.total_calls == sent and not self.report.io_error_types,
            'zero-call-operation-or-checkpoint-unverified')
        row['status'] = 'complete'
        self.report.checked_save('checkpoint-after-zero-operation-failed')
        return result

    def create(self):
        from serve_living_activity_chat import LivingActivityChatEntry
        from serve_living_final_text_chat import FinalTextLivingActivityChatEntry
        from living_activity_chat import APPLICATION_ID, FINAL_TEXT_APPLICATION_ID, living_activity_server
        self.activate()
        row = self.report.begin('create-own-entry-http-defaults', maximum_requests=0)
        self.transport = ObservedTransport(self.report, self.branch, self.variant)
        self.transport.arm(row['stage'])
        entry_type = LivingActivityChatEntry if self.branch == 'baseline' else FinalTextLivingActivityChatEntry
        self.entry = entry_type(self.root, live=False, transport=self.transport,
            audit_path=self.audit_path, observations=self.observations)
        application_id = APPLICATION_ID if self.branch == 'baseline' else FINAL_TEXT_APPLICATION_ID
        self.server = living_activity_server(self.product, reopen=self.entry.reopen, port=0,
            allow_simulation=True, application_id=application_id)
        require(self.server.server_address[0] == '127.0.0.1'
            and self.server.server_port not in (8790, 8791, 8792, 8793), 'independent-loopback-port-required')
        self.base_url = 'http://127.0.0.1:'+str(self.server.server_port)
        self.server_thread = Thread(target=self.server.serve_forever, name='s144-'+self.branch+'-http', daemon=True)
        self.server_thread.start()
        page = self.http('/', text=True)
        match = re.search(r"\bconst\s+TOKEN\s*=\s*'([A-Za-z0-9_-]{30,})'", page)
        require(match is not None, 'entry-http-session-token-unverified')
        self.token = match.group(1)
        require(self.http('/health') == dict(application=application_id), 'own-http-health-mismatch')
        state = self.http_state(); view = state['living_activity']['view']
        require(self.history() == [] and view['source'] is None and view['phase'] == 'unstarted'
            and view['current_plan'] is None and view['shares'] == [] and view['considered'] == []
            and view['permission'] == dict(paused=True, sharing_enabled=False, revision=0,
                needs_attention=False, source_blocked=False) and self.counts() == 0 and self.transport.total_calls == 0,
            'fresh-entry-preconditions-differ')
        require(self.http('/living-controls-query', {}).get('ok') is True, 'default-controls-query-unverified')
        row.update(status='complete', audit_before=0, audit_after=0, initial_page_sha256=sha256(page.encode()).hexdigest())
        self.report.data['branches'][self.branch].update(server_port=self.server.server_port, status='fresh-empty-ready')
        self.audit(); self.report.checked_save('checkpoint-after-create-failed')
        self.reload('initial-http-reload-zero-model')

    def stage(self, label, purpose, request_id, preview, operation):
        self.activate()
        before, sent, observed = self.counts(), self.transport.total_calls, len(self.observations)
        row = self.report.begin(label, purpose=purpose, request_id=request_id,
            audit_before=before, transport_before=sent, maximum_requests=1, expected_task_sha256=digest(preview))
        expected = self.transport.arm(label, preview, purpose)
        row.update(expected_wire_sha256=expected['wire_sha256'], expected_payload_sha256=expected['payload_sha256'],
            policy_sha256=expected['policy_sha256'], output_mode=expected['output_mode'])
        self.report.checked_save('checkpoint-before-http-model-stage-failed')
        try:
            result = operation()
        except BaseException as error:
            row.update(status='failed-or-unverified', error_type=type(error).__name__)
            raise
        finally:
            row.update(transport_after=self.transport.total_calls, transport_count=self.transport.total_calls-sent,
                observations=[base.safe_observation(value) for value in self.observations[observed:]])
            try:
                row['audit_after'] = self.counts(); self.audit()
            except Exception as error:
                row.update(audit_after=None, audit_unverified=True, audit_error_type=type(error).__name__)
                self.report.unverified('stage-audit-unverified')
            self.report.save()
        require(row.get('audit_unverified') is not True and not self.report.io_error_types, 'stage-checkpoint-or-audit-unverified')
        require(self.counts()-before <= 1 and self.transport.total_calls-sent <= 1, 'single-stage-request-bound-exceeded')
        status = result.get('living_status', 'terminal' if result.get('ok') is True and result.get('settled') is True else 'unverified')
        row['status'] = status
        if status not in ('committed', 'replayed', 'terminal') or result.get('ok') is not True:
            self.report.failure(self.branch, label, 'first-http-technical-failure', 'AcceptanceStopped')
            self.report.checked_save('checkpoint-after-first-failure-failed')
            raise AcceptanceStopped('first-http-technical-failure')
        audit = self.audit()
        require(self.counts()-before == 1 and self.transport.total_calls-sent == 1 and len(audit) > before,
            'successful-stage-without-one-verified-request')
        wire = self.report.data['transport'][-1]; raw = wire.get('response_boundary', {})
        require(wire['branch'] == self.branch and wire['status'] == 'response-received'
            and raw.get('exact_output_contract') is True and not raw.get('duplicate_semantic_keys')
            and audit[-1]['status'] == 'complete' and audit[-1]['purpose'] == purpose
            and audit[-1]['request_digest'] == digest(preview)
            and audit[-1]['output_digest'] == raw.get('final_value_sha256'), 'raw-final-audit-or-preview-mismatch')
        row['raw_final_matches_completed_audit'] = True
        if expected['output_mode'] == 'text':
            require(raw['wrapped_model_result_value_sha256'] == audit[-1]['output_digest']
                and raw['final_text_sha256'] == raw['reply_sha256'], 'raw-text-wrapper-audit-mismatch')
            row['raw_text_wrapper_matches_audit'] = True
        self.report.checked_save('checkpoint-after-raw-verification-failed')
        return result, row, raw

    def initial_reply(self, text, preview):
        self.activate()
        require(preview['payload']['turn'] == dict(current_message=text, history_enabled=True,
            has_prior_committed_exchange=False) and preview['payload']['exchange'] == []
            and preview['payload']['evidence'] == dict(shared_experience=None, activity_result=None, latest_share=None),
            'initial-pair-state-differs')
        request = dict(request_id=str(uuid4()), text=text)
        _, row, raw = self.stage('initial-ordinary-chat', PURPOSES[2], request['request_id'], preview,
            lambda:self.settle_reply(self.http('/send', request), request))
        turns = self.history()
        require(len(turns) == 1 and turns[0]['user_text'] == text, 'initial-canonical-round-missing')
        self.check_reply_canonical(row, raw, turns[-1])
        self.report.data['branches'][self.branch]['status'] = 'initial-chat-complete'
        self.report.checked_save('checkpoint-after-initial-reply-failed')
        self.replay_reply(request, 'initial-chat')

    def check_reply_canonical(self, row, raw, turn):
        actual_sha = sha256(turn['assistant_text'].encode('utf-8')).hexdigest()
        canonical = dict(reply_text=turn['assistant_text'], language='zh')
        require(actual_sha == raw['reply_sha256'] and digest(canonical) == raw['final_value_sha256'],
            'raw-full-reply-differs-from-canonical')
        if self.branch == 'candidate':
            require(actual_sha == raw['final_text_sha256']
                and digest(canonical) == raw['wrapped_model_result_value_sha256'], 'raw-text-not-original-canonical')
        row.update(reply_chars=raw['reply_chars'], reply_sha256=actual_sha, raw_reply_equals_canonical=True,
            canonical_complete_round=True, canonical_reply_value_sha256=digest(canonical))

    def replay_reply(self, request, label):
        def operation():
            before = self.fingerprint()
            query, response = self.http('/request-result', request), self.http('/send', request)
            require(query.get('query_status') == 'found' and query.get('request_verified') is True
                and query.get('ok') is True and query.get('settled') is True
                and response.get('ok') is True and response.get('settled') is True
                and query.get('request_id') == response.get('request_id') == request['request_id']
                and self.fingerprint() == before, 'original-reply-nonce-or-query-not-replayed')
        self.zero(label+'-nonce-replay-query-zero-model', operation)
        self.reload(label+'-restart-zero-model')
        self.zero(label+'-after-restart-query-zero-model', operation)

    def simulated_choice(self):
        self.activate()
        preview = self.preview('choice')
        require(preview['payload']['shared_experience'] is None and preview['payload']['current_plan'] is None,
            'first-choice-has-prior-plan-or-source')
        request = self.choice_request = dict(request_id=str(uuid4()), expected_revision=self.view()['revision'])
        _, row, raw = self.stage('one-explicitly-labelled-simulation-choice', PURPOSES[0], request['request_id'], preview,
            lambda:self.settle_living(self.http('/living-simulation', request), request, 'simulation'))
        actual = self.http_state()['living_activity']['view']['visible_result']
        require(actual is not None and actual['event']['kind'] == raw['action']
            and (None if actual['plan'] is None else digest(actual['plan'])) == raw['plan_sha256']
            and actual['event']['simulated'] is True, 'raw-choice-or-simulation-differs-from-canonical')
        decision = self.product.application.query_shared_activity()
        require(decision.status == 'available' and type(decision.view) is dict, 'canonical-choice-decision-unverified')
        value = plain(decision.view['decision'])
        canonical = dict(action=value['action'], plan=actual['plan'], reason_code=value['reason_code'],
            basis_refs=value['basis_refs'], decision_note=value['decision_note'])
        require(digest(canonical) == raw['final_value_sha256'], 'raw-full-choice-differs-from-canonical')
        row.update(action=raw['action'], plan_sha256=raw['plan_sha256'], simulated_event=True,
            canonical_actual_plan_matches_raw=True, canonical_choice_value_sha256=digest(canonical))
        self.report.checked_save('checkpoint-after-simulation-choice-failed')
        self.replay_living('simulation', request, 'choice-nonce-replay-query-zero-model')
        if actual['event']['kind'] not in ('start', 'revise') or actual['plan'] is None:
            self.report.data['branches'][self.branch]['status'] = 'stopped-no-eligible-new-text-plan'
            self.report.data.update(status='stopped-no-eligible-new-text-plan', runner_exit_code=1)
            self.report.checked_save('checkpoint-after-no-eligible-stop-failed')
            return False
        self.actual_plan_sha256 = digest(actual['plan'])
        return True

    def replay_living(self, kind, request, label):
        kind = 'simulation' if kind == 'online' else kind  # Inherited share recovery refers to the choice.
        def operation():
            before = self.fingerprint()
            query = self.http('/living-request', dict(kind=kind, request=request))
            route = '/living-simulation' if kind == 'simulation' else '/living-share'
            replay = self.http(route, request)
            require(query.get('living_status') == replay.get('living_status') == 'replayed'
                and query.get('living_receipt') == replay.get('living_receipt')
                and query.get('living_settled') is True and replay.get('living_settled') is True
                and self.fingerprint() == before, 'original-living-nonce-not-replayed')
        self.zero(label, operation)

    def reply(self, index, text):
        self.activate()
        preview = self.preview('reply', text); payload = preview['payload']; evidence = payload['evidence']
        history = self.history()
        require(payload['turn'] == dict(current_message=text, history_enabled=True, has_prior_committed_exchange=True)
            and evidence['shared_experience'] is None and digest(evidence['activity_result']['plan']) == self.actual_plan_sha256,
            'reply-current-result-E1-or-has-prior-differs')
        supplied = evidence['latest_share']
        require((supplied is not None and sha256(supplied['text'].encode()).hexdigest() == self.share_text_sha256)
            if index < 2 else supplied is None, 'latest-share-two-successful-round-window-differs')
        # The existing window selects the most recent two first, then removes
        # S1-dependent complete rounds. It never backfills older dialogue.
        expected = [] if index == 2 else [{key:turn[key] for key in ('user_text', 'assistant_text')}
            for turn in history[-2:]]
        require(payload['exchange'] == expected and sum(len(turn['user_text'])+len(turn['assistant_text'])
            for turn in expected) <= 4000, 'complete-derived-history-filter-or-window-differs')
        request = dict(request_id=str(uuid4()), text=text)
        _, row, raw = self.stage('ordinary-followup-'+str(index+1), PURPOSES[2], request['request_id'], preview,
            lambda:self.settle_reply(self.http('/send', request), request))
        self.http_state(); turns = self.history()
        require(len(turns) == len(history)+1 and turns[-1]['user_text'] == text, 'exact-complete-canonical-round-missing')
        self.check_reply_canonical(row, raw, turns[-1])
        row.update(latest_share_sha256=None if supplied is None else self.share_text_sha256,
            exchange_complete_turn_count=len(expected), exchange_sha256=digest(expected),
            has_prior_committed_exchange=True, third_complete_S1_history_filtered=index == 2,
            third_no_older_history_backfill=index == 2)
        self.report.checked_save('checkpoint-after-followup-failed')
        self.replay_reply(request, 'reply-'+str(index+1))

    def close(self):
        self.activate()
        branch = self.report.data['branches'][self.branch]
        if self.product is not None:
            before = self.counts(), self.transport.total_calls
            self.transport.arm('final-permission-query-and-pause')
            response = self.product.application.query_living_controls()
            require(response.status == 'available' and type(response.view) is dict, 'final-permission-before-pause-unverified')
            branch['permission_before_final_pause'] = plain(response.view)
            self.report.checked_save('final-permission-before-pause-checkpoint-failed')
            self.controls(paused=True, sharing_enabled=False, label='final-explicit-pause-shareoff-zero-model')
            final = self.product.application.query_living_controls()
            require(final.status == 'available' and type(final.view) is dict
                and final.view['paused'] is True and final.view['sharing_enabled'] is False
                and (self.counts(), self.transport.total_calls) == before, 'final-paused-permission-unverified')
            branch['final_permission'] = plain(final.view)
            state = self.http('/status')
            require(state.get('living_pending') is False and state.get('presentation_pending') is False,
                'final-http-operation-still-unverified')
        if self.server is not None:
            self.server.shutdown(); self.server.server_close()
            if self.server_thread is not None:
                self.server_thread.join(timeout=5)
                require(not self.server_thread.is_alive(), 'own-http-server-close-unverified')
            branch['own_http_server_closed'] = True
        if self.entry is not None:
            self.entry.close()
            require(self.entry.product is None, 'own-entry-product-close-unverified')
            branch['entry_product_closed'] = True


def compare_initial_pair(baseline, candidate, scene):
    text = scene['initial_message']
    previews = {run.branch:run.preview('reply', text) for run in (baseline, candidate)}
    first, second = previews['baseline'], previews['candidate']
    require(first['payload'] == second['payload'], 'initial-pair-actual-payload-differs')
    wires = {run.branch:wire_preview(previews[run.branch], PURPOSES[2], run.variant) for run in (baseline, candidate)}
    one, two = deepcopy(wires['baseline']['body']), deepcopy(wires['candidate']['body'])
    for wire in (one, two):
        require(type(wire['messages']) is list and len(wire['messages']) == 2
            and wire['messages'][0]['role'] == 'system' and wire['messages'][1]['role'] == 'user', 'closed-pair-messages-required')
    require(one['messages'][1] == two['messages'][1]
        and one['response_format'] == {'type':'json_object'} and 'response_format' not in two,
        'initial-pair-user-or-response-mode-differs')
    one.pop('response_format'); one['messages'][0]['content'] = two['messages'][0]['content']
    require(one == two and first['policy'] != second['policy'], 'initial-pair-has-additional-protocol-difference')
    baseline.report.data['initial_pair'] = dict(payload_values_equal=True,
        payload_sha256=digest(first['payload']), current_message_sha256=sha256(text.encode()).hexdigest(),
        evidence_sha256=digest(first['payload']['evidence']), exchange_sha256=digest(first['payload']['exchange']),
        protocol_equal_except_system_policy_and_response_format=True,
        changed_elements=['system-format-policy', 'response-format-mode'], single_field_causality_claimed=False,
        provider_internal_root_cause_proven=False, baseline_wire_sha256=wires['baseline']['wire_sha256'],
        candidate_wire_sha256=wires['candidate']['wire_sha256'])
    baseline.report.checked_save('checkpoint-after-pair-compare-failed')
    return previews


def self_check():
    """Synthetic observer/orchestration fixtures only; no product construction."""
    from dynamic_subject_agent.deepseek import DeepSeekHttpResponse
    def response(content, **message_extra):
        message = dict(role='assistant', content=content, reasoning_content='PRIVATE_SYNTHETIC_REASONING', **message_extra)
        return DeepSeekHttpResponse(200, json.dumps(dict(model='deepseek-flash',
            choices=[dict(finish_reason='stop', message=message)], usage=dict(prompt_tokens=10, completion_tokens=20))).encode())
    cases = []
    for label, content, purpose, mode, expected in (
        ('plain-text', ' 合成正文。\n', PURPOSES[2], 'text', True),
        ('white-space', ' \n\t', PURPOSES[2], 'text', False),
        ('overlong-text', '合'*1201, PURPOSES[2], 'text', False),
        ('nul-text', '合\x00成', PURPOSES[2], 'text', False),
        ('json-reply', json.dumps(dict(reply_text='合成正文。', language='zh')), PURPOSES[2], 'json', True),
        ('share-false', json.dumps(dict(share=False, reply_text='', language='zh')), PURPOSES[1], 'json', True),
        ('share-true', json.dumps(dict(share=True, reply_text='合成分享。', language='zh')), PURPOSES[1], 'json', True),
        ('choice', json.dumps(dict(action='start', plan=dict(subject='合成主体', composition='合成安排', focus='合成重点'),
            reason_code='emphasize-subject', basis_refs=[], decision_note='合成取舍')), PURPOSES[0], 'json', True),
        ('duplicate-value', '{"reply_text":"合成", "reply_text":"正文", "language":"zh"}', PURPOSES[2], 'json', False)):
        row = final_boundary(response(content), purpose, mode)
        require(row['exact_output_contract'] is expected, 'synthetic-observer-contract-mismatch')
        require('PRIVATE_SYNTHETIC_REASONING' not in json.dumps(row) and content not in json.dumps(row), 'synthetic-raw-text-leaked')
        if label == 'plain-text':
            require(row['reply_sha256'] == sha256(content.encode()).hexdigest()
                and row['wrapped_model_result_value_sha256'] == digest(dict(reply_text=content, language='zh')),
                'synthetic-raw-text-wrapper-changed')
        cases.append(dict(case=label, accepted=expected))
    for label, extra in (('refusal',dict(refusal='拒绝')), ('tools',dict(tool_calls=[{}])), ('second-final',dict(final='第二正文'))):
        row = final_boundary(response('合成正文。', **extra), PURPOSES[2], 'text')
        require(row['exact_output_contract'] is False, 'synthetic-extra-envelope-accepted')
        cases.append(dict(case=label, accepted=False))
    duplicate = b'{"model":"deepseek-flash","choices":[{"finish_reason":"stop","message":{"role":"user","role":"assistant","content":"text"}}],"usage":{"prompt_tokens":1,"completion_tokens":1}}'
    row = final_boundary(DeepSeekHttpResponse(200, duplicate), PURPOSES[2], 'text')
    require(row['duplicate_semantic_keys'] and not row['exact_output_contract'], 'synthetic-duplicate-role-accepted')
    cases.append(dict(case='duplicate-role', accepted=False))
    from unittest.mock import patch
    fixture_roots = {key:REPO/('.synthetic-never-created-s144-'+key) for key in ROOTS}
    report = SafeReport(fixture_roots, {})
    report.failure('baseline', 'synthetic-first', 'synthetic-failure', 'RuntimeError')
    first = deepcopy(report.data['first_failure'])
    report.failure('candidate', 'synthetic-second', 'synthetic-failure', 'RuntimeError')
    with patch.object(Path, 'write_text', side_effect=OSError('PRIVATE_SYNTHETIC_ERROR')):
        require(report.save() is False and report.io_error_types == ['OSError'], 'synthetic-io-unknown-not-retained')
    report.unverified('synthetic-close-unknown')
    require(report.data['runner_exit_code'] == 1 and report.data['first_failure'] == first
        and 'PRIVATE_SYNTHETIC_ERROR' not in json.dumps(report.data), 'synthetic-first-failure-or-unknown-exit-lost')
    initial = dict(user_text='合成初始问句', assistant_text='合成初始回复')
    follow1 = dict(user_text='合成首追问', assistant_text='合成首回复')
    follow2 = dict(user_text='合成次追问', assistant_text='合成次回复')
    histories = [[initial], [initial, follow1], [initial, follow1, follow2]]
    plan = dict(subject='合成主体', composition='合成安排', focus='合成重点')
    share = '合成分享'
    for index, exchange, admitted in ((0,[initial],True), (1,[initial,follow1],True), (2,[],True), (2,[initial],False)):
        run = BranchRun.__new__(BranchRun)
        run.branch, run.report = 'candidate', SafeReport(fixture_roots, {})
        run.actual_plan_sha256, run.share_text_sha256 = digest(plan), sha256(share.encode()).hexdigest()
        run.history = lambda:histories[index]
        run.preview = lambda *_args:dict(payload=dict(turn=dict(current_message='合成当前消息',
            history_enabled=True, has_prior_committed_exchange=True), exchange=exchange,
            evidence=dict(shared_experience=None, activity_result=dict(kind='composition-text', plan=plan),
                latest_share=dict(text=share) if index < 2 else None)))
        stage_entered = []
        def stop_before_model(*_args):
            stage_entered.append(True)
            raise AcceptanceStopped('synthetic-stop-before-model')
        run.stage = stop_before_model
        try:
            run.reply(index, '合成当前消息')
        except AcceptanceStopped as error:
            require(error.code == ('synthetic-stop-before-model' if admitted
                else 'complete-derived-history-filter-or-window-differs'), 'synthetic-history-window-expectation-mismatch')
        require(bool(stage_entered) is admitted, 'synthetic-history-window-started-wrong-stage')
    from contextlib import redirect_stdout
    from io import StringIO
    from types import SimpleNamespace
    for verified in (False, True):
        fixture_report = SafeReport(fixture_roots, {})
        fixture_report.data['initial_pair'] = {}
        entered = []
        def fixture_run(_root, _scene, current_report, branch):
            def initial_reply(*_args):
                current_report.active_branch = branch
                current_report.begin('synthetic-initial', maximum_requests=0)
                if branch == 'candidate':
                    entered.append(branch)
                    raise AcceptanceStopped('synthetic-stop-before-model')
                current_report.failure(branch, 'synthetic-initial', 'first-http-technical-failure', 'AcceptanceStopped')
                raise AcceptanceStopped('first-http-technical-failure')
            def history():
                require(verified, 'canonical-history-unverified')
                return []
            return SimpleNamespace(branch=branch, create=lambda:None, audit=lambda:[], close=lambda:None,
                initial_reply=initial_reply, history=history)
        with patch.object(fixture_report, 'save', return_value=True), \
            patch.dict(main.__globals__, preflight=lambda:({'initial_message':'合成当前消息'}, fixture_roots),
                SafeReport=lambda *_args:fixture_report, BranchRun=fixture_run,
                compare_initial_pair=lambda *_args:dict(baseline={}, candidate={})), \
            patch('sys.argv', ['run_s144_acceptance.py', '--execute']), redirect_stdout(StringIO()):
            try:
                main()
            except SystemExit as error:
                require(error.code == 1, 'synthetic-baseline-gate-exit-invalid')
        require(entered == (['candidate'] if verified else []), 'synthetic-unverified-baseline-entered-candidate')
        require(fixture_report.data['first_failure']['branch'] == 'baseline', 'synthetic-baseline-first-result-lost')
    return dict(status='self-check-passed', cases=cases,
        first_failure_retained=True, io_unknown_nonzero=True, close_unknown_nonzero=True,
        unverified_baseline_stops_candidate=True, verified_baseline_failure_allows_preplanned_candidate=True,
        recent_two_then_S1_filter_without_backfill=True, third_empty_exchange_preserves_has_prior=True,
        product_roots_created=0, services_started=0,
        credential_reads=0, model_invocations=0, remote_calls=0, report_written=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--preflight', action='store_true')
    modes.add_argument('--self-check', action='store_true')
    modes.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    report, runs, failed = None, [], False
    try:
        if args.self_check:
            print(json.dumps(self_check(), ensure_ascii=False), flush=True); return
        scene, roots = preflight()
        if args.preflight:
            print(json.dumps(dict(status='preflight-passed', base_review_basis=REVIEW_BASIS, scene_sha256=SCENE_SHA,
                runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), maximum_first_requests=7,
                requests_per_stage=1, automatic_retries=0, initial_pairs=1, candidate_continuations=1,
                time_is_simulated=True, identity_opened=False, service_started=False, transport_created=False,
                credential_reads=0, remote_calls=0, resource_exists=False, output_exists=False), ensure_ascii=False), flush=True)
            return
        report = SafeReport(roots, scene); report.checked_save('initial-checkpoint-failed')
        for branch in ('baseline', 'candidate'):
            run = BranchRun(roots[branch], scene, report, branch); runs.append(run); run.create()
        baseline, candidate = runs
        previews = compare_initial_pair(baseline, candidate, scene)
        try:
            baseline.initial_reply(scene['initial_message'], previews['baseline'])
        except AcceptanceStopped as error:
            require(error.code == 'first-http-technical-failure', 'baseline-integrity-failure-stops-pair')
            require(baseline.history() == [], 'failed-baseline-published-canonical-text')
            report.data['initial_pair']['failed_baseline_has_no_canonical_round'] = True
            report.data['initial_pair']['baseline_first_failed_without_resampling'] = True
            report.checked_save('baseline-first-failure-retained-checkpoint-failed')
        candidate.initial_reply(scene['initial_message'], previews['candidate'])
        candidate.enable()
        if candidate.simulated_choice() and candidate.share():
            for index,text in enumerate(scene['followup_messages']):
                candidate.reply(index, text)
            report.data['branches']['candidate']['status'] = 'candidate-scene-completed'
            report.data.update(status='candidate-scene-completed', candidate_initial_choice_share_reopen_two_followups_third_filter=True)
        elif report.data.get('status') == 'stopped-first-share-false':
            report.data['branches']['candidate']['status'] = 'stopped-first-share-false'
            report.data['runner_exit_code'] = 1
        report.checked_save('checkpoint-after-candidate-scene-failed')
    except BaseException as error:
        failed = True
        if report is not None:
            row = report.data['stages'][-1] if report.data['stages'] else None
            if row is not None:
                row.update(error_type=type(error).__name__)
                if row['status'] in ('started', 'pending'):
                    row['status'] = 'failed-or-unverified'
            code = error.code if type(error) is AcceptanceStopped else 'unexpected-runner-failure'
            if report.active_branch is not None:
                report.failure(report.active_branch, None if row is None else row['stage'], code, type(error).__name__)
            report.data.update(error_type=type(error).__name__, stop_code=code, runner_exit_code=1,
                status='stopped-on-first-technical-failure' if code == 'first-http-technical-failure' else 'stopped-for-unverified-or-integrity')
            report.save()
        else:
            print(json.dumps(dict(status='preflight-stopped', error_type=type(error).__name__,
                stop_code=error.code if type(error) is AcceptanceStopped else 'unexpected-preflight-failure',
                runner_exit_code=1, remote_calls=0, credential_reads=0), ensure_ascii=False), flush=True)
    finally:
        for run in runs:
            try:
                run.audit()
            except Exception as error:
                report.data['branches'][run.branch].update(audit_unverified=True, audit_error_type=type(error).__name__)
                report.unverified('final-audit-unverified')
            try:
                run.close()
            except Exception as error:
                report.data['branches'][run.branch].update(close_unverified=True, close_error_type=type(error).__name__)
                report.unverified('final-pause-or-close-unverified')
                for action in ((lambda:run.server.shutdown()) if run.server is not None else None,
                    (lambda:run.server.server_close()) if run.server is not None else None,
                    run.entry.close if run.entry is not None else None):
                    if action is not None:
                        try:
                            action()
                        except Exception:
                            pass
        if report is not None:
            try:
                require(sha256(LEGACY_METADATA.read_bytes()).hexdigest() == LEGACY_METADATA_SHA, 'legacy-failure-evidence-changed')
                report.data['checks']['legacy-failure-evidence-unchanged'] = True
            except Exception as error:
                report.data.update(legacy_evidence_unverified=True, legacy_evidence_error_type=type(error).__name__)
                report.unverified('legacy-evidence-unverified')
            report.data.setdefault('runner_exit_code', 1 if failed else 0)
            if not report.save() or report.io_error_types:
                report.unverified('final-checkpoint-unverified'); report.save()
            print(json.dumps({key:value for key,value in report.data.items() if key not in ('stages', 'transport')},
                ensure_ascii=False), flush=True)
            failed = failed or report.data['runner_exit_code'] != 0
    if failed:
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
