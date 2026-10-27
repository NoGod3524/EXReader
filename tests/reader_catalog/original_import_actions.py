import hashlib
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path('tests/reader_perf_windows').resolve()))
from perf_windows import make_txt_fixture
base = Path('build/original-import-fixture').resolve()
base.mkdir(parents=True, exist_ok=True)
source = make_txt_fixture(base, 0)
expected = '4f45393b25817f506a51b56cc5d61599556e4dd5b0bd59aa00f7eb43cbfc0a86'
def digest(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()
assert source.stat().st_size == 16792975 and digest(source) == expected
exe = Path('build/catalog/reader-original-import-check' + ('.exe' if os.name == 'nt' else '')).resolve()
def run(case, mode, code=0):
    root = base / case
    root.mkdir(exist_ok=True)
    args = [str(exe), str(root / 'catalog.db'), str(root), str(base), source.name, mode]
    result = subprocess.run(args)
    assert result.returncode == code, (case, mode, result.returncode)
for case in ('import', 'cancel'):
    run(case, case)
for event in (1, 2, 3):
    case = 'crash' + str(event)
    run(case, case, 42)
    run(case, 'published' if event == 3 else 'recover')
original = base / 'import' / (expected + '.txt')
assert digest(original) == expected and digest(source) == expected
with original.open('r+b') as f:
    f.write(b'X')
run('import', 'corrupt')
print('16,792,975-byte fixture, interruption, cancellation, duplicate, reopen and corruption checks passed')
