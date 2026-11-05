"""Invoke original compact and recursive OFF/F3/atomic judges via SDK-only adapter."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
assert os.environ.get('GITHUB_ACTIONS') == 'true'
sys.path.insert(0, str(ROOT / 'tests/reader_windows_compact'))
path = ROOT / 'tests/reader_windows_compact/verify.py'
code = path.read_text(encoding='utf-8')
old = "ROOT/'tests/reader_windows_341/verify.py'"
assert code.count(old) == 1
namespace = dict(__name__='current_compact_judge', __file__=str(path))
exec(compile(code.replace(old, "ROOT/'tests/windows_common_gate/verify_341.py'"), str(path), 'exec'), namespace)
namespace['WORKFLOW'] = '.github/workflows/reader-raw3-common-windows.yml'
namespace['main']()
