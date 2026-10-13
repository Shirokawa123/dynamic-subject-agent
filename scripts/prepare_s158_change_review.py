"""Read the terminal harbor result and save two unsent change-use samples."""
import json
from hashlib import sha256
from pathlib import Path

from dynamic_subject_agent.frozen_attempt import canonical_json
from dynamic_subject_agent.first_life import LifeEvent, LifeFieldDiff, validate_plan
from dynamic_subject_agent.shared_activity import ActivityResult
from dynamic_subject_agent.current_activity_change import current_activity_change
from dynamic_subject_agent.integrated_character_change_preview import current_change_request_preview
from dynamic_subject_agent.model_gateway import ModelTask, ModelTaskKind

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / '.artifacts/s158/intent-loop-first'
OUTPUT = REPO / '.artifacts/s158/change-review-first'


def hashes(root):
    return {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob('*')) if p.is_file()}


def main():
    if not (SOURCE / 'entry/initialized').is_dir() or OUTPUT.exists():
        raise ValueError('existing terminal source and fresh review output required')
    metadata = json.loads((SOURCE / 'metadata.json').read_text(encoding='utf-8'))
    if metadata['status'] != 'scene-effect-not-met' or metadata['next_stage'] != 11:
        raise ValueError('exact terminal scene required; never resume it')
    before = hashes(SOURCE)
    # Saved, already-verified historical checkpoints; never open/recover a product.
    # This is an exact data-use sample, not a current delivery authorization.
    raw = metadata['final_view']['visible_result']
    choice = next(item for item in metadata['stages'] if item['stage'] == 'next-activity')
    if choice['after']['visible_result'] != raw:
        raise ValueError('same historical committed result required')
    result = ActivityResult(**dict(raw, plan=validate_plan(raw['plan']),
        event=LifeEvent(**raw['event']), differences=tuple(LifeFieldDiff(**item) for item in raw['differences']),
        source_dependencies=tuple(raw['source_dependencies'])))
    change = current_activity_change(dict(visible_result=result,
        result_before_dependencies=choice['before']['visible_result']['source_dependencies'],
        valid_sources=raw['source_dependencies']))
    if change is None or before != hashes(SOURCE):
        raise ValueError('unchanged historical result with conservative source proof required')
    OUTPUT.mkdir()
    samples = {}
    for label, kind in (('faithful-reply', ModelTaskKind.NATURAL_ACTIVITY_FEEDBACK),
                        ('second-share', ModelTaskKind.LIVING_ACTIVITY_SHARE)):
        original = json.loads((SOURCE / 'previews' / (label + '.json')).read_text(encoding='utf-8'))
        stage = next(item for item in metadata['stages'] if item['stage'] == label)
        if stage['before']['visible_result'] != metadata['final_view']['visible_result']:
            raise ValueError('historical checkpoint must have the same current result')
        preview = current_change_request_preview(ModelTask(kind, original['preview']), change)
        path = OUTPUT / (label + '.json')
        with path.open('x', encoding='utf-8') as stream:
            stream.write(canonical_json(dict(checkpoint='historical-eligible-unsent-candidate',
                source_preview_sha256=sha256((SOURCE / 'previews' / (label + '.json')).read_bytes()).hexdigest(),
                proposed_wire=preview)))
        samples[label] = dict(path=str(path.relative_to(REPO)), file_sha256=sha256(path.read_bytes()).hexdigest(),
            wire_sha256=preview['wire_sha256'])
    result = dict(status='unapproved-historical-preview-only', source_files_preserved=len(before), model_requests=0,
        credential_reads=0, product_opened=False, current_result_change=change, samples=samples)
    with (OUTPUT / 'metadata.json').open('x', encoding='utf-8') as stream:
        stream.write(canonical_json(result))
    print(canonical_json(result))


if __name__ == '__main__':
    main()
