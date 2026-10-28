"""Authenticate the original successful capture upload without rebuilding it."""
import json
from pathlib import Path
import shutil
import subprocess
import zipfile
import frozen_capture as F
import wf07_contract as C


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', 'repos/NoGod3524/EXReader/' + path]))


def download():
    C.guard()
    run = api('actions/runs/' + str(C.RUN))
    C.require((run['head_sha'], run['run_attempt'], run['conclusion'], run['path'], run['head_branch']) ==
        (C.SOURCE, C.ATTEMPT, 'success', '.github/workflows/reader-windows-f07-capture-20261028.yml',
         'codex/reader-windows-f07-capture-20261028'), 'original capture run differs/failed')
    jobs = api(f'actions/runs/{C.RUN}/attempts/{C.ATTEMPT}/jobs?per_page=100')['jobs']
    C.require(len(jobs) == 3 and {j['name'] for j in jobs} ==
              {'capture-protocol', 'windows-capture', 'authenticate-capture'} and
              all(j['head_sha'] == C.SOURCE and j['conclusion'] == 'success' for j in jobs), 'original producers incomplete')
    C.OUT.mkdir(parents=True, exist_ok=False)
    records = {}
    for key, (id_, name, size, digest) in C.PINS.items():
        item = api('actions/artifacts/' + str(id_))
        C.require((item['id'], item['name'], item['size_in_bytes'], item['digest'], item['expired'],
            item['workflow_run']['head_sha'], item['workflow_run']['id']) ==
            (id_, name, size, 'sha256:' + digest, False, C.SOURCE, C.RUN), 'original artifact pin differs')
        path = C.OUT / (key + '-original.zip')
        with path.open('wb') as stream:
            subprocess.run(['gh', 'api', 'repos/NoGod3524/EXReader/actions/artifacts/' + str(id_) + '/zip'],
                           stdout=stream, check=True)
        C.require(path.stat().st_size == size and C.digest(path) == digest, 'original upload bytes differ')
        records[key] = item
    C.save(C.OUT / 'original-artifacts.json', dict(C.identity(), artifacts=records, run=run, jobs=jobs))
    outer = C.OUT / 'outer'
    extract(C.OUT / 'capture-original.zip', outer)
    C.require({p.name for p in outer.iterdir()} ==
        {'snapshot.zip', 'inventory.json', 'report.json', 'source.json', 'producer.json', 'producer-console.log'},
        'unexpected outer capture members')
    inventory = json.loads((outer / 'inventory.json').read_text())
    expected = dict(source_sha=C.SOURCE, run_id=str(C.RUN), attempt=str(C.ATTEMPT))
    F.same(inventory, expected)
    C.require(F.file_digest(outer / 'snapshot.zip') == inventory['archive'], 'snapshot digest differs')
    with zipfile.ZipFile(outer / 'snapshot.zip') as archive:
        verified = F.validate_capture(archive, inventory['files'], expected)
        source = json.loads(archive.read('capture/source.json'))
        for name in ('source.json', 'producer.json', 'producer-console.log'):
            C.require((outer / name).read_bytes() == archive.read('capture/' + name), 'outer/inner captured evidence differs')
    claimed = json.loads((outer / 'report.json').read_text())
    C.require(claimed['capture_complete'] is True and claimed['f07_accepted'] is False and
              all(claimed[key] == value for key, value in verified.items()), 'capture claim differs from replay')
    raw = C.OUT / 'retained'
    extract(outer / 'snapshot.zip', raw)
    C.save(C.OUT / 'capture-recomputed.json', dict(C.identity(), verified=verified,
             captured_files=len(inventory['files']), source=source))
    return raw, inventory['files'], source


def extract(path, folder):
    C.require(not folder.exists(), 'fresh extraction required')
    with zipfile.ZipFile(path) as archive:
        members = F.safe_members(archive)
        folder.mkdir(parents=True)
        for name in members:
            target = folder / name; target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as source, target.open('wb') as destination:
                shutil.copyfileobj(source, destination, 1024 * 1024)

