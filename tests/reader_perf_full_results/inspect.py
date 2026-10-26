#!/usr/bin/env python3
"""Parse retained CI artifacts inside Actions after authenticating the outer ZIP."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

repo = os.environ['GITHUB_REPOSITORY']
run_id = os.environ['TARGET_RUN']
name = os.environ['TARGET_NAME']

def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', f'repos/{repo}/{path}']))

run = api('actions/runs/' + run_id)
items = api('actions/runs/' + run_id + '/artifacts')['artifacts']
matches = [item for item in items if item['name'] == name and not item['expired']]
assert len(matches) == 1, matches
artifact = matches[0]
assert artifact['workflow_run']['id'] == int(run_id) and artifact['workflow_run']['head_sha'] == run['head_sha']
raw = subprocess.check_output(['gh', 'api', f'repos/{repo}/actions/artifacts/{artifact["id"]}/zip'])
assert len(raw) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == artifact['digest']
out = Path('build/full-perf-result'); out.mkdir(parents=True, exist_ok=True)
archive_path = out / 'artifact.zip'; archive_path.write_bytes(raw)
with zipfile.ZipFile(archive_path) as archive:
    def read(suffix, optional=False):
        matches = [name for name in archive.namelist() if name.endswith(suffix)]
        if optional and not matches:
            return None
        assert len(matches) == 1, (suffix, matches)
        return json.loads(archive.read(matches[0]))
    if 'windows' in name:
        summary = read('full-perf-windows/summary.json')
        identity = read('full-perf-windows/full-package-identity.json')
        result = {'source_sha': summary['source_sha'], 'run_id': summary['run_id'], 'attempt': summary['attempt'],
                  'cohorts': summary['cohorts'], 'aggregates': summary['aggregates'],
                  'environment': summary['environment'], 'txt_path': summary['txt_path'],
                  'performance_accepted': summary['performance_accepted'], 'frame_time': summary['frame_time'],
                  'package_identity': identity}
    else:
        summary = read('full-gtk-evidence/summary.json')
        report = read('full-gtk-evidence/report.json')
        result = {'source_sha': summary['source_sha'], 'run_id': summary['run_id'], 'attempt': summary['attempt'],
                  'metrics': summary['metrics'], 'environment': summary['environment'], 'rss': summary['rss'],
                  'observation_complete': report['accepted'], 'problems': report['problems'],
                  'grants': report['grants'], 'performance_accepted': False}
        frame = read('full-gtk-evidence/frame-clock-observation.json', optional=True)
        if frame:
            assert frame['source_sha'] == summary['source_sha'] and str(frame['run_id']) == run_id
            assert str(frame['attempt']) == str(run['run_attempt'])
            for launch in frame['launches']:
                raw_name = 'full-gtk-evidence/frame-clock-raw/' + str(launch['pid']) + '.tsv'
                matches = [path for path in archive.namelist() if path.endswith(raw_name)]
                assert len(matches) == 1 and hashlib.sha256(archive.read(matches[0])).hexdigest() == launch['raw_sha256']
            result['frame_clock'] = {'complete': frame['clock_samples_complete'],
                                     'launches': len(frame['launches']),
                                     'after_paint_samples': sum(row['after_paint_samples'] for row in frame['launches']),
                                     'scope': frame['scope'], 'probe': frame['probe'],
                                     'physical_presentation_measured': frame['physical_presentation_measured']}
    assert result['source_sha'] == run['head_sha'] and str(result['run_id']) == run_id
    assert str(result['attempt']) == str(run['run_attempt'])
    result['artifact'] = {key: artifact[key] for key in ('id', 'name', 'digest', 'size_in_bytes', 'expires_at')}
    result['run_conclusion'] = run['conclusion']
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    compact = {key: result[key] for key in ('source_sha', 'run_id', 'attempt', 'run_conclusion', 'artifact')}
    if 'windows' in name:
        compact.update({'cohorts': result['cohorts'], 'aggregates': result['aggregates'],
                        'cpu': result['environment']['cpu'], 'package_identity': result['package_identity'],
                        'performance_accepted': False, 'frame_time': result['frame_time']})
    else:
        compact.update({'metrics': {k: {n: v.get(n) for n in ('count', 'p50_ms', 'p95_ms', 'max_ms')}
                                     for k, v in result['metrics'].items()},
                        'cpu': result['environment']['runner'], 'rss': result['rss'],
                        'observation_complete': result['observation_complete'], 'problems': result['problems'],
                        'frame_clock': result.get('frame_clock')})
    print(json.dumps(compact, ensure_ascii=False))
