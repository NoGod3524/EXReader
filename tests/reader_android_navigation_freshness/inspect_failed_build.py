"""Read only the authenticated first diagnostic's retained real cloud log."""
import hashlib
import io
import json
import os
import zipfile

from authenticate import api, need

RUN = 40232637095
SOURCE = '6c7438b81b81f7a6ce0ef5eb16085404401b7d2b'
ARTIFACT = 12613414210
SIZE = 896505
DIGEST = '136edda4d4be705e5055908ca553d53753092b96eb2173ccf8b38ab7a935906c'

need(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
run = api(f'actions/runs/{RUN}/attempts/1')
need(run['head_sha'] == SOURCE and run['conclusion'] == 'failure', 'diagnostic producer differs')
metadata = api(f'actions/artifacts/{ARTIFACT}')
need(metadata['name'] == f'android-navigation-freshness-{RUN}-1'
     and metadata['size_in_bytes'] == SIZE and metadata['digest'] == 'sha256:' + DIGEST
     and metadata['workflow_run']['id'] == RUN and metadata['workflow_run']['head_sha'] == SOURCE
     and not metadata['expired'], 'diagnostic artifact identity differs')
body = api(f'actions/artifacts/{ARTIFACT}/zip', raw=True)
need(len(body) == SIZE and hashlib.sha256(body).hexdigest() == DIGEST, 'diagnostic ZIP bytes differ')
with zipfile.ZipFile(io.BytesIO(body)) as archive:
    names = archive.namelist()
    for suffix in ('trace-probe-build.log', 'original-control/result.json',
                   'original-apk-trace/first-instrumentation.txt', 'original-apk-trace/runner.log'):
        matches = [name for name in names if name == suffix or name.endswith('/' + suffix)]
        need(len(matches) == 1, 'requested original diagnostic member absent or duplicated: ' + suffix)
        data = archive.read(matches[0]); need(len(data) <= 512 * 1024, 'unexpected diagnostic log size')
        print('AUTHENTICATED CLOUD MEMBER ' + matches[0], flush=True)
        if suffix.endswith('.json'):
            report = json.loads(data)
            print(json.dumps({'source_sha': report['source_sha'], 'accepted': report['accepted'],
                              'checks': report['checks'], 'phases': [
                                  {'phase': row['phase'], 'passed': row['passed'], 'count': row['count']}
                                  for row in report['phases']]}), flush=True)
        else:
            print(data.decode('utf-8', errors='replace'), flush=True)
print(json.dumps({'inspected_run': RUN, 'artifact_id': ARTIFACT, 'digest': DIGEST,
                  'emulator_started': False, 'accepted': False}), flush=True)
