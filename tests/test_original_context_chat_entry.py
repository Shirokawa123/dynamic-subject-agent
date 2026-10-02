import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from dynamic_subject_agent.application import ApplicationFacade
from dynamic_subject_agent.local_product import LocalProductConfig, open_local_product
from dynamic_subject_agent._deepseek_activation import DormantDeepSeekCognition
from dynamic_subject_agent.whole_context_boundary import CONTEXT_AUTHORITY
from test_original_whole_chat import approved, personality_fixture, model_fixture, WholeTransport
from test_whole_chat_archive import canonical_path

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def context_entry(approved, monkeypatch, tmp_path):
    _, _, request, view = approved
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    base = importlib.import_module('serve_original_whole_chat')
    script = importlib.import_module('serve_original_context_chat')
    asset = json.loads(view.runtime_asset_json)
    binding = dict(definition_basis=view.definition_basis, runtime_asset_sha=view.runtime_asset_sha,
        persona_digest=asset['persona_digest'], review_basis='1'*64, scope_digest='2'*64,
        subject_id=asset['subject']['subject_id'], anchor_id=asset['anchor']['anchor_id'])
    import dynamic_subject_agent.original_whole_chat as contract
    for module in (contract, base, script): monkeypatch.setattr(module, 'APPROVED_BINDING', binding)
    reviews = []
    def review(value):
        reviews.append(value)
        assert value.expected_definition_basis == binding['definition_basis']
        return SimpleNamespace(status='previewed', review_basis=binding['review_basis'])
    monkeypatch.setattr(ApplicationFacade, 'preview_original_character_whole_use_preparation', staticmethod(review))
    def no_select(*a, **kw): raise AssertionError('context entry must freeze without old select/schema1')
    monkeypatch.setattr(ApplicationFacade, 'select_local_identity', no_select)
    package = tmp_path / 'owned-synthetic-package.json'
    package.write_text(request.preparation_json, encoding='utf-8')
    options = dict(live=False, package_path=package, transport=WholeTransport(), audit_path=tmp_path/'entry-audit')
    return script, tmp_path/'context-entry', options, reviews, request


def test_new_context_entry_is_empty_schema4_and_sealed_reopens_without_package(context_entry):
    script, root, options, reviews, _ = context_entry
    entry = script.OriginalContextChatEntry(root, **options)
    try:
        qri = entry.product._qri
        assert qri.provider_authority == CONTEXT_AUTHORITY
        assert qri.reviewed_chat_contract['technical_variant']['name'] == 'context-boundary'
        path = canonical_path(entry.product)
        import sqlite3
        with sqlite3.connect(path) as db:
            assert db.execute('PRAGMA user_version').fetchone() == (4,)
            assert db.execute('SELECT COUNT(*) FROM timeline_outcome').fetchone() == (0,)
            assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='life_record'").fetchone() == (0,)
        assert entry.product.application.query_whole_context_boundary()['context_revision'] == 0
        pointer = (root/'current.json').read_bytes(); identity = entry.identity
        options['package_path'].unlink()  # Only this owned synthetic package.
        entry.reopen()
        assert entry.identity == identity and not options['transport'].calls
    finally: entry.close()
    reopened = script.OriginalContextChatEntry(root, **options)
    try:
        assert reopened.identity == identity and (root/'current.json').read_bytes() == pointer
        assert len(reviews) == 1 and not options['transport'].calls
        value = json.loads(pointer); value['profile_id'] = str(uuid4())
        (root/'current.json').write_text(json.dumps(value), encoding='utf-8')
        registry = reopened.config.state_path.read_bytes()
        with pytest.raises(ValueError, match='witness changed'): reopened.reopen()
        assert reopened.config.state_path.read_bytes() == registry
    finally: reopened.close()
    with pytest.raises(RuntimeError): script.OriginalContextChatEntry(root, **options)
    assert not options['transport'].calls


def test_missing_package_and_partial_witness_preserve_root_without_activation(context_entry, monkeypatch):
    script, root, options, _, _ = context_entry
    options['package_path'].unlink()
    with pytest.raises(FileNotFoundError): script.OriginalContextChatEntry(root, **options)
    assert not root.exists()
    root.mkdir(); (root/'initialized').mkdir()
    saved = sorted(root.iterdir())
    def forbidden(*a, **kw): raise AssertionError('partial entry must not activate or re-freeze')
    monkeypatch.setattr(script, 'open_original_whole_product', forbidden)
    with pytest.raises(ValueError, match='incomplete'): script.OriginalContextChatEntry(root, **options)
    assert sorted(root.iterdir()) == saved and not options['transport'].calls


def test_valid_dormant_same_basis_rejects_before_any_activation(context_entry, monkeypatch):
    script, root, options, _, request = context_entry
    entry = script.OriginalContextChatEntry(root, **options)
    config = entry.config; entry.close()
    # Obtain a fully valid dormant sealed witness by ordinary freeze/replay in
    # the same parent. Its approved asset is exact, but it has no served timeline.
    alternate = LocalProductConfig(config.product_parent, root/'alternate-state.json')
    with open_local_product(alternate, cognition=DormantDeepSeekCognition()) as author:
        frozen = author.application.freeze_source_identity(request)
        assert frozen.status in ('created', 'replayed')
    other = json.loads(alternate.state_path.read_text(encoding='utf-8'))
    record = next(row for row in other['identities'] if row['identity_id'] == frozen.view.identity_id)
    assert record.get('host_location') is None
    state = json.loads(config.state_path.read_text(encoding='utf-8'))
    state['identities'] = [row for row in state['identities'] if row['identity_id'] != record['identity_id']] + [record]
    state['active_identity_id'] = record['identity_id']
    state['chat_identity_revision'] += 1
    config.state_path.write_text(json.dumps(state), encoding='utf-8')
    before = config.state_path.read_bytes(); marker = (root/'current.json').read_bytes()
    def forbidden(*a, **kw): raise AssertionError('wrong active identity must not reach activation/Host/cold recovery')
    monkeypatch.setattr(script, 'open_original_whole_product', forbidden)
    with pytest.raises(RuntimeError, match='identity-unverified'): script.OriginalContextChatEntry(root, **options)
    assert config.state_path.read_bytes() == before and (root/'current.json').read_bytes() == marker
    assert not options['transport'].calls


def test_main_reuses_only_exact_health_and_opens_browser_only_explicitly(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'scripts'))
    script = importlib.import_module('serve_original_context_chat')
    opened = []
    monkeypatch.setattr(script.webbrowser, 'open', opened.append)
    class Response:
        def __init__(self, value): self.value = value
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, n): return json.dumps(self.value).encode()
    def no_entry(*a, **kw): raise AssertionError('an occupied port must never initialize another root')
    monkeypatch.setattr(script, 'OriginalContextChatEntry', no_entry)
    monkeypatch.setattr(script, 'urlopen', lambda *a, **kw: Response(dict(application=script.APPLICATION_ID)))
    monkeypatch.setattr('sys.argv', ['entry'])
    script.main(); assert opened == []
    monkeypatch.setattr('sys.argv', ['entry', '--open-browser'])
    script.main(); assert opened == ['http://127.0.0.1:8788']
    monkeypatch.setattr(script, 'urlopen', lambda *a, **kw: Response(dict(application='original-character-whole-chat-s127')))
    with pytest.raises(SystemExit, match='其他服务'): script.main()
    from urllib.error import HTTPError
    def bad_health(*a, **kw): raise HTTPError('http://127.0.0.1:8788/health', 404, 'fixture', {}, None)
    monkeypatch.setattr(script, 'urlopen', bad_health)
    with pytest.raises(SystemExit, match='未创建'): script.main()
    assert len(opened) == 1
    from urllib.error import URLError
    def refused(*a, **kw):
        assert kw['timeout'] == 6
        raise URLError(ConnectionRefusedError('owned fixture refused'))
    closed, server_options = [], []
    product = object()
    monkeypatch.setattr(script, 'urlopen', refused)
    monkeypatch.setattr(script, 'OriginalContextChatEntry', lambda *a, **kw: SimpleNamespace(
        product=product, reopen=lambda: product, close=lambda: closed.append('entry')))
    def start_server(actual_product, **kwargs):
        assert actual_product is product
        server_options.append(kwargs)
        def stop(): raise KeyboardInterrupt()
        return SimpleNamespace(server_port=8788, serve_forever=stop, server_close=lambda: closed.append('server'))
    monkeypatch.setattr(script, 'original_whole_server', start_server)
    monkeypatch.setattr('sys.argv', ['entry'])
    script.main()
    assert closed == ['server', 'entry'] and len(opened) == 1
    assert server_options[0]['application_id'] == script.APPLICATION_ID and server_options[0]['port'] == 8788
