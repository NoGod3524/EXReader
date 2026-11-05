import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path('tests/reader_perf_windows').resolve()))
from perf_windows import make_txt_fixture

out = Path('build/txt-candidate-evidence')
fixtures = out / 'fixtures'
fixtures.mkdir(parents=True, exist_ok=True)
path = make_txt_fixture(fixtures, 0)
digest = hashlib.sha256(path.read_bytes()).hexdigest()
assert path.stat().st_size == 16792975
assert digest == '4f45393b25817f506a51b56cc5d61599556e4dd5b0bd59aa00f7eb43cbfc0a86'
font = Path('C:/Windows/Fonts/arial.ttf')
runs = []
for attempt in range(3):
    result = subprocess.run(['build/txt-candidate/bounded_txt_host.exe', str(path), str(font)],
                            check=True, capture_output=True, text=True)
    runs.append(json.loads(result.stdout))
    print(result.stdout.strip(), flush=True)
assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
report = {'source_sha256': digest, 'source_unchanged': True, 'runs': runs,
          'scope': 'experimental standalone host; not the Windows product import path'}
(out / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
