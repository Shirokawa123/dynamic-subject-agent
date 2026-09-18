"""Exact local text approval and no-clobber file publication. No network access."""
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from uuid import UUID, uuid5

TEXT_EFFECT_INTENT = 'confirmed-text-save-v1'
POLICY = 'local-text-save-1'


@dataclass(frozen=True)
class TextSaveApproval:
    task_id: str
    revision: int
    basis: str

    def __post_init__(self):
        if str(UUID(self.task_id)) != self.task_id or type(self.revision) is not int or self.revision < 1:
            raise ValueError('invalid artifact task reference')
        if not isinstance(self.basis,str) or len(self.basis)!=64 or any(c not in '0123456789abcdef' for c in self.basis):
            raise ValueError('invalid exact approval basis')

    def to_json(self):
        return json.dumps(asdict(self),sort_keys=True,separators=(',',':'))

    @classmethod
    def from_json(cls,text):
        value=json.loads(text)
        if type(value) is not dict or set(value)!=set(cls.__dataclass_fields__):
            raise ValueError('invalid text approval')
        return cls(**value)


@dataclass(frozen=True)
class TextArtifactPreview:
    task_id: str
    revision: int
    content: str
    filename: str
    directory: str
    basis: str
    effect_id: str
    content_digest: str
    root_id: str
    profile_id: str
    timeline_id: str
    policy: str = POLICY


def make_preview(record, *, root_id, profile_id, timeline_id, directory):
    if record.status!='accepted' or not record.content.strip():
        return None
    filename=f'text-{record.task_id}-r{record.revision}.txt'
    digest=sha256(record.content.encode('utf-8')).hexdigest()
    effect_id=str(uuid5(UUID(record.task_id),f'{POLICY}:{record.revision}'))
    values=dict(task_id=record.task_id,revision=record.revision,content=record.content,filename=filename,
        directory=str(directory),effect_id=effect_id,content_digest=digest,root_id=root_id,
        profile_id=profile_id,timeline_id=timeline_id,policy=POLICY)
    basis=sha256(json.dumps(values,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return TextArtifactPreview(**values,basis=basis)


def approve(approval, records, preview):
    old=next((r for r in records if r.task_id==approval.task_id),None)
    if old is None or old.revision!=approval.revision or old.status!='accepted' or preview is None or preview.basis!=approval.basis:
        return None, None, '任务或正文已变化，这次确认没有生效；请重新预览。'
    expected=make_preview(old,root_id=preview.root_id,profile_id=preview.profile_id,
        timeline_id=preview.timeline_id,directory=preview.directory)
    if preview!=expected:
        raise ValueError('preview differs from current task')
    return replace(old,status='executing',revision=old.revision+1,reason='save_approved'),preview,'保存授权已提交，文件结果请查看任务状态。'


class TextArtifactFailure(Exception):
    pass


def _plain(path, *, directory=False):
    info=path.lstat()
    if (stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400
        or (directory and not stat.S_ISDIR(info.st_mode))
        or (not directory and not stat.S_ISREG(info.st_mode))):
        raise TextArtifactFailure('unsafe-path')
    return info


def publish_text(preview: TextArtifactPreview, *, canonical_root: Path, fault_hook=None) -> str:
    """Return created or a closed failure code. Never overwrite or remove files."""
    directory=canonical_root/'artifacts'
    if str(directory)!=preview.directory or preview.filename!=f'text-{preview.task_id}-r{preview.revision}.txt':
        return 'target-mismatch'
    body=preview.content.encode('utf-8')
    if sha256(body).hexdigest()!=preview.content_digest:
        return 'content-mismatch'
    try:
        _plain(canonical_root,directory=True)
        directory.mkdir(exist_ok=True)
        _plain(directory,directory=True)
        staging=directory/'.staged'
        staging.mkdir(exist_ok=True)
        _plain(staging,directory=True)
        stage=staging/(preview.effect_id+'.txt')
        target=directory/preview.filename
        if target.exists() or target.is_symlink():
            _plain(target);_plain(stage)
            return 'created' if os.path.samefile(stage,target) and target.read_bytes()==body else 'target-conflict'
        try:
            with stage.open('xb') as stream:
                stream.write(body)
                stream.flush();os.fsync(stream.fileno())
        except FileExistsError:
            _plain(stage)
            if stage.read_bytes()!=body:
                return 'partial-staging'
        _plain(stage)
        if stage.read_bytes()!=body:
            return 'content-mismatch'
        if fault_hook: fault_hook('after-staging')
        try:
            os.link(stage,target)
        except FileExistsError:
            _plain(target)
            if not os.path.samefile(stage,target) or target.read_bytes()!=body:
                return 'target-conflict'
        if fault_hook: fault_hook('after-file')
        _plain(target)
        return 'created' if os.path.samefile(stage,target) and target.read_bytes()==body else 'content-mismatch'
    except (OSError,TextArtifactFailure):
        return 'file-unavailable'


FILE_RESULTS=frozenset({'created','target-mismatch','content-mismatch','target-conflict','partial-staging','file-unavailable'})


def effect_from_reason(decision):
    if decision.rule_version!='agency-text-effect-1.0':
        return None
    from dynamic_subject_agent.subject_tasks import SubjectTaskRecord
    value=json.loads(decision.reason)
    if set(value)!={'code','provenance','subject_task','reply','approval','effect'} or value['code']!='text-effect.result':
        raise ValueError('invalid text effect outcome')
    approval=TextSaveApproval(**value['approval'])
    if not isinstance(value['reply'],str) or not 1<=len(value['reply'])<=1000:
        raise ValueError('invalid artifact receipt')
    if value['effect'] is None:
        if value['subject_task'] is not None:
            raise ValueError('record without effect')
        return None
    preview=TextArtifactPreview(**value['effect'])
    record=SubjectTaskRecord.from_dict(value['subject_task'])
    if record.status!='executing' or record.reason!='save_approved' or record.revision!=approval.revision+1:
        raise ValueError('invalid executing task')
    prior=replace(record,status='accepted',revision=approval.revision,reason='supported_request')
    result,effect,reply=approve(approval,(prior,),preview)
    if result!=record or effect!=preview or value['reply']!=reply:
        raise ValueError('effect differs from exact approval')
    return preview


@dataclass(frozen=True)
class TextArtifactResponse:
    status: str
    preview: TextArtifactPreview | None = None
    message: str = ''
