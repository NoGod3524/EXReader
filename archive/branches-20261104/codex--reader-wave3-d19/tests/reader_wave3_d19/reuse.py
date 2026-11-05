"""Read immutable D14 judges as source, never import historical test results."""
import hashlib
import os
from pathlib import Path
import subprocess
import types

ROOT = Path(__file__).resolve().parents[2]
D14 = '93c2f583c7e54eb2aebcba13a18b532bd0a967f5'
SEED = 'd263ce5228838ac90c0a0dc13a5193d4a7739681'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'

def source(name):
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    raw = subprocess.check_output(['git', 'show', D14 + ':tests/reader_dot_wave2/d14/' + name], cwd=ROOT)
    folder = ROOT / 'evidence/judge/d14'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(raw)
    return raw

def module(name):
    raw = source(name)
    loaded = types.ModuleType('d19_original_' + name.replace('.', '_'))
    loaded.__file__ = str(ROOT / 'evidence/judge/d14' / name)
    exec(compile(raw, loaded.__file__, 'exec'), loaded.__dict__)
    return loaded
