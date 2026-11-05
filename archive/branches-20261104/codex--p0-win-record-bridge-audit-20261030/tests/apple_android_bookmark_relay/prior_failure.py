"""Actions-only authenticate and expose original failed Android runtime logs."""
import hashlib
import io
import json
import os
import subprocess
from pathlib import Path
import sys
import zipfile
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip
assert os.environ.get('GITHUB_ACTIONS') == 'true'
artifact_id = 12774061204
meta = fetch('actions/artifacts/' + str(artifact_id))
assert meta['workflow_run']['head_sha'] == '3c2bf73a8f5c2aab93076e6f69d760e9e3cc76fd'
assert meta['workflow_run']['id'] == 40583104086
raw = download_artifact_zip(artifact_id)
assert len(raw) == meta['size_in_bytes']
assert 'sha256:' + hashlib.sha256(raw).hexdigest() == meta['digest'] == 'sha256:68356f007f383fa3b34dd3338de0f5127f4f551da3ba09edfc06f0e79cfd17f0'
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    report = json.loads(archive.read('report.json'))
    assert report['passed'] is False and report['source_sha'] == meta['workflow_run']['head_sha']
    print('ORIGINAL FAILED REPORT', json.dumps(report, ensure_ascii=False), flush=True)
    lines = archive.read('logcat.txt').decode(errors='replace').splitlines()
    selected = [line for line in lines if any(key in line.lower() for key in
        ('exreader', 'exception', 'fatal', 'could not', 'reader', 'sqlite', 'abort'))]
    print('ORIGINAL LOGCAT (filtered, original ZIP retained):\n' + '\n'.join(selected[-250:]), flush=True)
    print('ORIGINAL AUTHENTICATED REQUESTS', archive.read('requests.json').decode(), flush=True)
    image = ROOT / 'build/apple-android/original-failure-screen.png'
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(archive.read('screen.png'))
    print('ORIGINAL FAILURE SCREEN OCR (diagnostic, not UI acceptance):', flush=True)
    subprocess.run(['tesseract', str(image), 'stdout'], check=True)
