import hashlib
import os
from pathlib import Path
import subprocess
import sys
base = Path('build/original-import-fixture').resolve()
base.mkdir(parents=True, exist_ok=True)
# Byte-identical parameters of the original Windows performance fixture.
source = base / 'Perf Import 0000.txt'
unit = ('Perf Import 0000\n' + ''.join(
    'Perf Import %04d line %04d keeps the import worker busy while input continues.\n' % (0, n)
    for n in range(512))).encode()
with source.open('wb') as f:
    written = 0
    while written < 16 << 20:
        f.write(unit)
        written += len(unit)
expected = '4f45393b25817f506a51b56cc5d61599556e4dd5b0bd59aa00f7eb43cbfc0a86'
def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(65536), b''):
            h.update(block)
    return h.hexdigest()
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
