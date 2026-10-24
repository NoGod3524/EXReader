# SPDX-License-Identifier: MIT
"""Cloud-only diagnosis of the original F5 Windows query; never acceptance."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch, require


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud only')
    artifact = fetch('actions/artifacts/12550071895')
    require(artifact['workflow_run']['head_sha'] == '278d63691a4c73e7aa932d71a40a5938c5427514' and
            artifact['workflow_run']['id'] == 40067425188 and artifact['expired'] is False, 'original identity differs')
    with tempfile.TemporaryFile() as stream:
        download_artifact_zip(artifact['id'], stream); stream.seek(0); data = stream.read()
    require(len(data) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(data).hexdigest() == artifact['digest'], 'original ZIP differs')
    manifest = json.loads(Path('tests/reader_real_corpus/manifest.json').read_text(encoding='utf-8'))
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = [n for n in archive.namelist() if n.endswith('summary.json')]
        require(len(names) == 1, 'original summary absent')
        summary = json.loads(archive.read(names[0]))
    rows = []
    for entry in manifest['files']:
        if entry['format'] != 'FB2': continue
        record = next(r for r in summary['files'] if r['id'] == entry['id'])
        query = record['result']['detail']['find']['query']
        rows.append({'id': entry['id'], 'query_equal': query == entry['query'],
                     'expected_utf8_sha256': hashlib.sha256(entry['query'].encode()).hexdigest(),
                     'observed_utf8_sha256': hashlib.sha256(query.encode()).hexdigest(),
                     'original_status': record['status']})
    require(len(rows) == 2, 'two actual FB2 reports required')
    report = {'accepted': False, 'diagnostic_only': True, 'original_source': summary['source']['commit'],
              'original_run': 40067425188, 'artifact': artifact['id'], 'checks': rows}
    out = Path('build/reader-corpus-original-query-diagnostic.json'); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__': main()
