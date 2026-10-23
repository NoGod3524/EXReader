"""Diagnose actual bundled FreeType raw CID versus SFNT behavior in CI."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import pymupdf

if not os.environ.get('GITHUB_ACTIONS'):
    raise SystemExit('Run in GitHub Actions')
binary, source, output = map(Path, sys.argv[1:])
output.mkdir(parents=True, exist_ok=False)
assert hashlib.sha256(source.read_bytes()).hexdigest() == '2280fa3e302774d2681a98ba5ff33e7dc3bc63440d13b01453ec1bda36f32b5a'
document = pymupdf.open(source)
raw = output/'nasa-page29.cid'
raw.write_bytes(document.extract_font(820)[3])
wrapped = Path('tests/fixtures/fonts/pdf-cid.otf')
data = wrapped.read_bytes()
synthetic = output/'synthetic.cid'
for index in range(struct.unpack_from('>H', data, 4)[0]):
    tag, _, offset, size = struct.unpack_from('>4sIII', data, 12+16*index)
    if tag == b'CFF ':
        synthetic.write_bytes(data[offset:offset+size])
        break
records = []
for font in (raw, wrapped, synthetic):
    result = subprocess.run([str(binary.resolve()), '--cid-probe', str(font.resolve())], capture_output=True, timeout=120)
    (output/(font.stem+'.stdout')).write_bytes(result.stdout)
    (output/(font.stem+'.stderr')).write_bytes(result.stderr)
    record = {'font': str(font), 'sha256': hashlib.sha256(font.read_bytes()).hexdigest(), 'exit': result.returncode}
    records.append(record)
    print(json.dumps(record), flush=True)
    print(result.stdout.decode(), flush=True)
(output/'summary.json').write_text(json.dumps({'diagnostic_only': True, 'source_sha': os.environ['GITHUB_SHA'], 'records': records}, indent=2)+'\n')
assert all(record['exit'] == 0 for record in records)
