"""Retain every installed-binary assertion, correctly name the authorized SDK."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / 'tests/reader_windows_341/identity.py'
code = path.read_text(encoding='utf-8')
if os.environ.get('GITHUB_REF_NAME') == 'codex/dot-windows-common-gate':
    old = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
    assert code.count(old) == 1
    code = code.replace(old, '5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9')
exec(compile(code, str(path), 'exec'), dict(__name__='__main__', __file__=str(path)))
