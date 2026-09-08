"""只为离线回归派生当前实现的临时协议；历史冻结文件不改写。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from refractrouter.dag_study import implementation_fingerprint, load_study
from refractrouter.handoff_validation import load_handoff


def current_protocol(path, loader):
    path = Path(path)
    raw = json.loads(path.read_text())
    raw['implementation_sha256'] = implementation_fingerprint()
    for key in ('manifest_path', 'context_source_protocol_path'):
        if key in raw:
            raw[key] = str((path.parent/raw[key]).resolve())
    for context in raw.get('probe_contexts', []):
        context['source_path'] = str((path.parent/context['source_path']).resolve())
    with TemporaryDirectory() as directory:
        derived = Path(directory)/path.name
        derived.write_text(json.dumps(raw, ensure_ascii=False))
        return loader(derived)


def current_study(path):
    return current_protocol(path, load_study)


def current_handoff(path):
    return current_protocol(path, load_handoff)
