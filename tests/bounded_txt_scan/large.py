import hashlib
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path('tests/reader_perf_windows').resolve()))
from perf_windows import make_txt_fixture

folder = Path('build/bounded-txt-fixture')
folder.mkdir(parents=True, exist_ok=True)
path = make_txt_fixture(folder, 0)
expected = '4f45393b25817f506a51b56cc5d61599556e4dd5b0bd59aa00f7eb43cbfc0a86'
def verify():
    assert path.stat().st_size == 16792975
    with path.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected
verify()
subprocess.run(['build/bounded-txt-scan/bounded_txt_scan.exe', str(path)], check=True)
verify()
print('original fixture hash preserved:', expected)
