"""Read only the authenticated first diagnostic's retained real cloud log."""
import hashlib
import io
import json
import os
import zipfile

from authenticate import api, need

FINAL = os.environ.get('INSPECTION_TARGET', 'original') == 'final'
RUN = 40233907741 if FINAL else 40232637095
SOURCE = '798a96c52932ab67635023b8a2623c7297d281b7' if FINAL else '6c7438b81b81f7a6ce0ef5eb16085404401b7d2b'
ARTIFACT = 12613604629 if FINAL else 12613414210
SIZE = 22249008 if FINAL else 896505
DIGEST = '86489765d5b7fd4a2f9de75c5c5b9e9d1d815c4e8af4662d9946cd2387bc6b29' if FINAL else '136edda4d4be705e5055908ca553d53753092b96eb2173ccf8b38ab7a935906c'

need(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
run = api(f'actions/runs/{RUN}/attempts/1')
need(run['head_sha'] == SOURCE and run['conclusion'] == ('success' if FINAL else 'failure'), 'diagnostic producer differs')
metadata = api(f'actions/artifacts/{ARTIFACT}')
need(metadata['name'] == f'android-navigation-freshness-{RUN}-1'
     and metadata['size_in_bytes'] == SIZE and metadata['digest'] == 'sha256:' + DIGEST
     and metadata['workflow_run']['id'] == RUN and metadata['workflow_run']['head_sha'] == SOURCE
     and not metadata['expired'], 'diagnostic artifact identity differs')
body = api(f'actions/artifacts/{ARTIFACT}/zip', raw=True)
need(len(body) == SIZE and hashlib.sha256(body).hexdigest() == DIGEST, 'diagnostic ZIP bytes differ')
with zipfile.ZipFile(io.BytesIO(body)) as archive:
    names = archive.namelist()
    if FINAL:
        def member(suffix):
            matches = [name for name in names if name == suffix or name.endswith('/' + suffix)]
            need(len(matches) == 1, 'final diagnostic member absent or duplicated: ' + suffix)
            return archive.read(matches[0])
        report = json.loads(member('diagnostic.json'))
        need(report['diagnostic_source'] == SOURCE and report['primary_error'] is None
             and report['collector_errors'] == [] and report['accepted'] is False, 'final diagnostic state differs')
        print(json.dumps({key: report[key] for key in ('diagnostic_source', 'producer_source', 'run_id', 'attempt',
                         'original', 'trace_probe', 'rebuilt', 'groups', 'primary_error', 'collector_errors',
                         'cache_differentials', 'accepted')}, ensure_ascii=False), flush=True)
        config = member('rebuilt-BuildConfig.java').decode()
        need('package org.exreader.host;' in config and 'READER_SELECTOR_BYTES_CANDIDATE = false;' in config,
             'retained owner BuildConfig not OFF')
        caches = [name for name in names if name.rsplit('/', 1)[-1].startswith('rebuilt-cmake-') and name.endswith('.txt')]
        need(caches and all(b'EXR_READER_SELECTOR_BYTES_CANDIDATE:BOOL=OFF' in archive.read(name) for name in caches),
             'retained native cache not OFF')
        print(json.dumps({'owner_build_config_off': True, 'native_caches_off': len(caches),
                          'authenticated_stage_files': len(report['authenticated_stages'])}), flush=True)
        trace = json.loads(member('rebuilt-pair-fresh/navigation-trace-first.json'))
        selected = [event for event in trace['events'] if event['sequence'] in (1, 2)
                    or event['label'] == 'Group' and event['action'] in ('before-cache', 'after-cache')]
        print('AUTHENTICATED FINAL CACHE EVENTS ' + json.dumps(selected, ensure_ascii=False), flush=True)
        print(json.dumps({'inspected_run': RUN, 'artifact_id': ARTIFACT, 'digest': DIGEST,
                          'emulator_started': False, 'accepted': False}), flush=True)
        raise SystemExit(0)
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
