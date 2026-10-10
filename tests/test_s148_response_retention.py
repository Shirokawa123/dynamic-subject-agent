import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_s148_choice_comparison as trial
from dynamic_subject_agent.deepseek import DeepSeekHttpResponse


def test_final_survives_invalid_usage_and_does_not_store_reasoning(tmp_path,monkeypatch):
    monkeypatch.setattr(trial,'ROOT',tmp_path/'owned')
    report=dict(calls=[])
    transport=trial.CapturingTransport(report)
    response=DeepSeekHttpResponse(200,json.dumps(dict(choices=[dict(message=dict(content='{}',reasoning_content='PRIVATE-HIDDEN'))],usage=None)).encode())
    transport.delegate=SimpleNamespace(post_json=lambda **kwargs:response)
    wire=trial.canonical_json(dict(messages=[dict(content='system'),dict(content='{"scope":"composition-text"}')])).encode()
    transport.arm('form-insufficient',wire)
    actual=transport.post_json(endpoint='https://api.deepseek.com/chat/completions',timeout_seconds=30,body=wire)
    assert actual is response
    stored=(trial.ROOT/'finals/form-insufficient.json').read_text(encoding='utf-8')
    assert json.loads(stored)==dict(final='{}')
    assert 'PRIVATE-HIDDEN' not in stored and report['calls'][0]['usage'] is None


def test_permission_or_canonical_change_rejects_frozen_source(tmp_path,monkeypatch):
    root=tmp_path/'owned';root.mkdir();monkeypatch.setattr(trial,'ROOT',root)
    state,canonical=root/'state.json',root/'canonical.sqlite3'
    state.write_text('enabled');canonical.write_bytes(b'owned fixture')
    stamp=trial.source_stamp(dict(state=str(state),canonical=str(canonical)))
    manifest=dict(source_witnesses=dict(base=stamp,R=stamp))
    trial.verify_sources(manifest,'R-Q')
    state.write_text('disabled')
    try: trial.verify_sources(manifest,'R-Q')
    except RuntimeError as error: assert str(error)=='canonical-or-source-permission-changed'
    else: raise AssertionError('changed source permission was accepted')
