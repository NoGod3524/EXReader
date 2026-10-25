"""Read-only cloud inspection, never a host-compatibility acceptance grant."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch

assert os.environ.get('GITHUB_ACTIONS') == 'true'
SOURCE = '126b4f78cb09a259fb8263d06dabf3a44f3f7a5f'
RUN = 40176886653
ARTIFACT = 12592797096
SIZE = 48061050
DIGEST = 'sha256:62293efeb04d76fd5ff72689460ccf472c557c31a6110c4842421af5b1efd5e0'
run = fetch('actions/runs/' + str(RUN))
assert run['head_sha'] == SOURCE and run['run_attempt'] == 1 and run['status'] == 'completed' and run['conclusion'] == 'failure'
assert run['path'] == '.github/workflows/reader-gtk-record-compatibility.yml'
metadata = fetch('actions/artifacts/' + str(ARTIFACT))
assert metadata['workflow_run']['head_sha'] == SOURCE and metadata['workflow_run']['id'] == RUN
assert metadata['size_in_bytes'] == SIZE and metadata['digest'] == DIGEST and metadata['expired'] is False
with tempfile.TemporaryFile() as stream:
    download_artifact_zip(ARTIFACT, stream);stream.seek(0);data = stream.read()
assert len(data) == SIZE and 'sha256:' + hashlib.sha256(data).hexdigest() == DIGEST
with zipfile.ZipFile(io.BytesIO(data)) as archive:
    names = archive.namelist()
    assert len(names) == len(set(names)) and sum(row.file_size for row in archive.infolist()) < 1024 ** 3
    assert all(not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts and '\\' not in name for name in names)
    def raw(tail):
        matches = [name for name in names if name == tail or name.endswith('/' + tail)]
        assert len(matches) == 1, tail
        return archive.read(matches[0])
    report = json.loads(raw('gtk-record-compatibility-evidence/result.json'))
    assert report['source_sha'] == SOURCE and report['run_id'] == str(RUN) and report['accepted'] is False
    print(json.dumps(dict(accepted=False, diagnostic_only=True, source_sha=SOURCE, run_id=RUN,
          artifact_id=ARTIFACT, artifact_digest=DIGEST, programs=report['programs'], problems=report['problems'])), flush=True)
    for kind in ('txt', 'epub'):
        prefix = 'gtk-record-compatibility-evidence/profile-old-old-' + kind + '/'
        for name in names:
            if prefix not in name or '-verify-' not in name or not name.endswith('.json'):
                continue
            payload = archive.read(name)
            try:
                partial = json.loads(payload)
            except json.JSONDecodeError:
                # An interrupted test's FILE contains a flushed array prefix.
                # This diagnostic repairs only a temporary parse copy, never
                # edits the producer bytes or turns it into an accepted report.
                partial = json.loads(payload + b'],"partial_diagnostic":true}')
            print(json.dumps(dict(path=name, raw_sha256=hashlib.sha256(payload).hexdigest(),
                  diagnostic_only=True, checks=partial['checks'])), flush=True)
        wires = []
        for name in names:
            if prefix in name and name.endswith('.json') and len(PurePosixPath(name).stem) == 32:
                wire = json.loads(archive.read(name))
                wires.append(wire)
        parents = {parent for wire in wires for parent in wire['parents']}
        selected = [wire for wire in wires if wire['id'] not in parents]
        for wire in selected:
            print(json.dumps(dict(diagnostic_only=True, profile=kind, selected_wire=wire), ensure_ascii=False), flush=True)
