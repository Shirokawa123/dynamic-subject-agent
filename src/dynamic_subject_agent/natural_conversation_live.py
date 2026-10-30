"""Approved bounded conversation delivery; never a LOCAL remote masquerade."""
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from threading import get_ident
from urllib.request import urlopen

from dynamic_subject_agent.natural_experience_cycle import LIVE_REVIEW as REVIEW
from dynamic_subject_agent.frozen_attempt import canonical_json, write_once
from dynamic_subject_agent.model_gateway import ProviderAdapter, ProviderCapabilities, StructuredOutputMode, ModelResult, ModelTaskKind, ModelGatewayFailure
from dynamic_subject_agent.deepseek import (_post_json_reply_content, _post_text_reply_content,
    DeepSeekUrlLibTransport, DEEPSEEK_CREDENTIAL_BACKEND_ID, DEEPSEEK_CREDENTIAL_KEY_ID)
from dynamic_subject_agent.cognition import CredentialRef
from dynamic_subject_agent.first_life_reply_live_provider import _ObservedTransport


@dataclass(frozen=True)
class NaturalConversationRequest:
    review_directory: Path
    approval_path: Path
    preparation_path: Path
    output: Path


def validate_material(request):
    raw = (request.review_directory / 'review.json').read_bytes()
    if sha256(raw).hexdigest() != REVIEW:
        raise ValueError('exact M032 review required')
    review = json.loads(raw)
    receipt = json.loads(request.approval_path.read_bytes())
    expected = dict(version='memorie-natural-conversation-m032-1', review_sha256=REVIEW,
        human_confirmed=True, user_reply='同意这次隔离试验',
        authorization_source='direct-user-reply:2026-10-30-current-chat', maximum_requests=12,
        automatic_retries=0, installation_included=False, user_data_upgrade_included=False)
    if canonical_json(receipt) != canonical_json(expected):
        raise ValueError('exact conversation approval required')
    if sha256(request.preparation_path.read_bytes()).hexdigest() != review['preparation_sha256']:
        raise ValueError('reviewed character material changed')
    bodies = {}
    for name, digest in review['illustrative_unsent_request_sha256'].items():
        raw = (request.review_directory / (name + '.UNSENT.json')).read_bytes()
        if sha256(raw).hexdigest() != digest:
            raise ValueError('reviewed preview changed')
        bodies[name] = json.loads(raw)
    source = json.loads(bodies['first-selection']['messages'][1]['content'])
    return review, {key: source[key] for key in ('character', 'personality')}


class NaturalConversationDelivery(ProviderAdapter):
    capabilities = ProviderCapabilities('deepseek', 'deepseek-flash', False,
        (StructuredOutputMode.JSON_OBJECT, StructuredOutputMode.TEXT))

    def __init__(self, request, journal, contract, *, transport_factory=None):
        self.request, self.journal, self.contract = request, journal, contract
        self.transport_factory = transport_factory
        self._frame = None
        self.validate()

    def validate(self):
        review, background = validate_material(self.request)
        from dynamic_subject_agent.natural_experience_cycle import LIVE_VERSION
        if self.contract['version'] != LIVE_VERSION or self.contract['technical_variant']['natural_render_version'] != REVIEW:
            raise ValueError('exact LIVE conversation contract required')
        return review, background

    @contextmanager
    def frame(self, projection):
        if self._frame is not None:
            raise ValueError('one request frame at a time')
        self._frame = (get_ident(), projection)
        try:
            yield
        finally:
            self._frame = None

    def _body(self, task, index):
        review, background = self.validate()
        if self._frame is None or self._frame[0] != get_ident() or task.payload != self._frame[1]():
            raise ValueError('current canonical request frame required')
        if not 0 <= index < 12:
            raise ValueError('approved attempt limit reached')
        selection = index % 2 == 0
        expected_kind = ModelTaskKind.MEMORIE_NATURAL_EXPERIENCE if selection else ModelTaskKind.MEMORIE_GROUNDED_EXPRESSION
        if task.kind is not expected_kind or task.payload['current_user_text'] != review['scenario'][index // 2]['text']:
            raise ValueError('exact next trial turn and purpose required')
        spec = review['selection' if selection else 'reply']
        payload = dict(background, **task.payload)
        if set(payload) != set(spec['fields']):
            raise ValueError('exact approved projection fields required')
        if not selection:
            pairs = payload['exchange']
            if (type(pairs) is not list or len(pairs) > 2 or payload['activity_evidence'] is not None
                    or any(type(row) is not dict or set(row) != {'user_text', 'assistant_text'} for row in pairs)
                    or sum(len(row['user_text']) + len(row['assistant_text']) for row in pairs) > 4000):
                raise ValueError('bounded real exchange required')
        body = dict(spec['parameters'], messages=[dict(role='system', content=spec['policy']),
            dict(role='user', content=canonical_json(payload))])
        raw = canonical_json(body).encode()
        if len(raw) > 65536:
            raise ValueError('request too large')
        return raw

    def invoke(self, task):
        index = self.journal.next
        raw = self._body(task, index)
        digest = sha256(raw).hexdigest()
        self.journal.claim(digest)  # Global once-per-review claim, before credentials.
        write_once(self.request.output / f'{index + 1:02d}.request.json', json.loads(raw))
        sent = False

        def opener(request, *, timeout):
            nonlocal sent
            if (sent or self._body(task, index) != raw or request.data != raw
                    or request.get_method() != 'POST' or timeout != 30
                    or request.full_url != 'https://api.deepseek.com/chat/completions'):
                raise ValueError('exact one-shot approved delivery required')
            sent = True
            return urlopen(request, timeout=timeout)

        if self.transport_factory is None:
            from dynamic_subject_agent.local_product import _WindowsLabResolver
            transport = DeepSeekUrlLibTransport(credential_resolver=_WindowsLabResolver(), _opener=opener)
        else:
            transport = self.transport_factory(opener)
        observed = _ObservedTransport(transport)
        ref = CredentialRef.reference(backend_id=DEEPSEEK_CREDENTIAL_BACKEND_ID, key_id=DEEPSEEK_CREDENTIAL_KEY_ID)
        value, error, status = None, None, 'complete'
        try:
            if index % 2 == 0:
                value = _post_json_reply_content(observed, ref, raw, max_output_tokens=4096,
                    require_complete=True, discard_reasoning=True, safe_diagnostics=True)
            else:
                value = _post_text_reply_content(observed, ref, raw, max_output_tokens=4096)
                from dynamic_subject_agent.original_whole_chat import validate_whole_reply
                validate_whole_reply(dict(reply_text=value, language='zh'))
        except Exception as exc:
            from dynamic_subject_agent.character_dialogue_provider import CharacterCredentialUnavailable
            error = 'character-credential-unavailable' if isinstance(exc, CharacterCredentialUnavailable) else getattr(exc, 'diagnostic_code', 'conversation-delivery-failed')
            status = 'unavailable' if isinstance(exc, CharacterCredentialUnavailable) else 'unknown' if error in ('transport-timeout', 'transport-delivery-ambiguous') else 'failed-closed'
        row = dict(index=index, request_sha256=digest, status=status,
            error_code=error, value=value, **{k: observed.row[k] for k in ('model', 'usage', 'finish_reason', 'final_content')})
        self.journal.record(digest, row)
        write_once(self.request.output / f'{index + 1:02d}.result.json', row)
        if error:
            self.journal.stop(error)
            raise ModelGatewayFailure(error)
        return ModelResult(task.kind, value)


def run_trial(request, *, _transport_factory=None, _audit_parent=None, reviewed=False):
    import os
    from time import monotonic
    from dynamic_subject_agent.frozen_attempt import FrozenAttemptRun
    from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product, open_natural_conversation_product_live
    from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
    from dynamic_subject_agent.reviewed_character_definition import ReviewedCharacterFreezeRequest
    from dynamic_subject_agent.memorie_companion_contract import DEFINITION
    from dynamic_subject_agent.timeline import SubjectCommand
    validator=validate_material;review_id=REVIEW
    if reviewed:
        from dynamic_subject_agent.reviewed_natural_live import validate_material as validator, REVIEW as review_id
    review, _ = validator(request)
    if (request.output.exists() or request.output.resolve().parent != request.review_directory.resolve().parent
            or request.output.resolve().parent.name != '.artifacts'):
        raise ValueError('fresh isolated sibling output required')
    if _audit_parent is not None and _transport_factory is None:
        raise ValueError('real attempt journal cannot be redirected')
    parent = _audit_parent if _transport_factory is not None else Path(os.environ['LOCALAPPDATA']) / ('DynamicSubjectAgent/reviewed-natural-conversation-m034' if reviewed else 'DynamicSubjectAgent/memorie-natural-conversation-m032')
    parent.mkdir(parents=True, exist_ok=True)
    journal = FrozenAttemptRun(parent, review_id, approved=True)
    if journal.resumed:
        raise ValueError('this review already started; no rerun or new-root resend')
    request.output.mkdir()
    product, rows, reopen = None, [], None
    try:
        prepared = json.loads(request.preparation_path.read_bytes())
        config = LocalProductConfig(request.output / 'identity/DynamicSubjectAgent/m0/experiments', request.output / 'identity/state.json')
        with open_local_product(config, cognition=DormantDeepSeekCognition()) as author:
            frozen = author.application.freeze_source_identity(ReviewedCharacterFreezeRequest(prepared['definition_json'], DEFINITION, True, True))
            if frozen.status != 'created':
                raise ValueError('isolated reviewed identity required')
        definition = json.loads(prepared['definition_json'])
        asset = json.loads(definition['runtime_asset_json'])
        binding = dict(definition_basis=DEFINITION, runtime_asset_sha=definition['runtime_asset_sha'],
            persona_digest=asset['persona_digest'], subject_id=asset['subject']['subject_id'],
            anchor_id=asset['anchor']['anchor_id'], review_basis=review_id, scope_digest=review_id)

        def opening():
            return open_natural_conversation_product_live(config, request=request, journal=journal,
                identity_id=frozen.view.identity_id, binding=binding, _transport_factory=_transport_factory,reviewed=reviewed)

        product = opening()
        scope = product.profile_id, product.timeline_id
        for step in review['scenario']:
            if step.get('reopen_before'):
                prior = product.application.query_living_activity()
                count = journal.next
                product.close(); product = None
                product = opening()
                current = product.application.query_living_activity()
                if (scope != (product.profile_id, product.timeline_id) or count != journal.next
                        or current.status != 'available' or current.view != prior.view):
                    raise ValueError('reopen changed canonical state or generated a request')
                reopen = dict(same_scope=True, same_state=True, model_calls=0)
            command = SubjectCommand.contribute_utterance(target_profile_id=product.profile_id,
                target_timeline_id=product.timeline_id, declared_intent='ask-collaborator-status',
                utterance=step['text'], language='zh', provenance='project-original')
            started=monotonic();before_calls=journal.next
            result = product.application.submit(command, idempotency_key=('reviewed-conversation-m034-' if reviewed else 'natural-conversation-m032-') + step['id'])
            for _ in range(6 if reviewed else 3):
                if result.status != 'pending':
                    break
                result = product.application.wait(result.operation_ref, timeout_seconds=30)
            state = product.application.query_living_activity()
            row = dict(turn=step['id'], user_text=step['text'], status=result.status,
                problem_code=getattr(result.problem, 'code', None),
                failure_code=getattr(result.projection, 'failure_code', None),
                reply_text=getattr(result.projection, 'expression_text', None),
                experience=state.view.get('natural_experience') if state.status == 'available' else None)
            if reviewed:row.update(elapsed_seconds=round(monotonic()-started,3),model_calls=journal.next-before_calls)
            rows.append(row)
            write_once(request.output / (step['id'] + '.turn.json'), row)
            if result.status != 'terminal' or row['failure_code']:
                journal.stop('conversation-turn-failed')
                break
        complete = len(rows) == 6 and all(row['status'] == 'terminal' and row['failure_code'] is None for row in rows)
        report = dict(status='complete' if complete else 'stopped', attempts=journal.next,
            rows=rows, reopen=reopen, semantic_acceptance='not-yet-evaluated',
            user_canonical_opened=False, installed=False)
        write_once(request.output / 'results.json', report)
        return report
    except Exception:
        journal.stop('conversation-setup-or-recording-failed')
        raise
    finally:
        if product is not None:
            product.close()
