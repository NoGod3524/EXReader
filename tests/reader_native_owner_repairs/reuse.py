"""Read exact historical test sources in Actions without altering the old files."""
import hashlib
import os
from pathlib import Path
import subprocess
import types

ROOT = Path(__file__).resolve().parents[2]
D12 = 'db6c726c2f5bcee03d697e90b4865e7874e6b2a0'
D09 = '2ccceba85cb12a9cab5c00e5cb62a7c5a4a4ece5'


def source(commit, path):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Actions only')
    raw = subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT)
    return raw


def module(commit, path, name):
    raw = source(commit, path)
    folder = ROOT / 'build/native-owner-reuse'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / Path(path).name
    target.write_bytes(raw)
    loaded = types.ModuleType(name)
    loaded.__file__ = str(target)
    loaded.__dict__['historical_source_sha256'] = hashlib.sha256(raw).hexdigest()
    exec(compile(raw, str(target), 'exec'), loaded.__dict__)
    return loaded
