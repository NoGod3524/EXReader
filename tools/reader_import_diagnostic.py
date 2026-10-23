#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only, read-only inspection of a fixed failed Android original archive."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

REPOSITORY = 'NoGod3524/EXReader'
ARTIFACT = 12528106635
RUN = 40012904324
SOURCE = '72bbc5bd6c3072c904637724387cc515b03e7237'
SIZE = 156876456
SHA256 = 'bed03132d339d0b6d7330cbe8c9e57b9cdd900e74c1c8ad4d13ad7f2e9c5f5b6'


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Only GitHub Actions may download or parse original evidence')
    output = Path('build/import-diagnostic')
    output.mkdir(parents=True, exist_ok=True)
    metadata = json.loads(subprocess.check_output(
        ['gh', 'api', f'repos/{REPOSITORY}/actions/artifacts/{ARTIFACT}']))
    if (metadata.get('id') != ARTIFACT or metadata.get('size_in_bytes') != SIZE
            or metadata.get('digest') != 'sha256:' + SHA256 or metadata.get('expired') is not False
            or metadata.get('workflow_run', {}).get('id') != RUN
            or metadata.get('workflow_run', {}).get('head_sha') != SOURCE):
        raise ValueError('Retained original artifact identity differs')
    archive = output / 'original.zip'
    with archive.open('wb') as stream:
        subprocess.run(['gh', 'api', f'repos/{REPOSITORY}/actions/artifacts/{ARTIFACT}/zip'],
                       stdout=stream, check=True)
    raw = archive.read_bytes()
    if len(raw) != SIZE or hashlib.sha256(raw).hexdigest() != SHA256:
        raise ValueError('Original archive bytes/digest differ')
    report = {'diagnostic_only': True, 'accepted': False, 'original_source_sha': SOURCE,
              'original_run_id': RUN, 'original_artifact_id': ARTIFACT,
              'original_bytes': SIZE, 'original_sha256': SHA256, 'entries': []}
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate ZIP entries')
        print(json.dumps({'verified_original_artifact': ARTIFACT, 'source': SOURCE, 'run': RUN}))
        for name in names:
            if name.endswith('/validation.json') and ('review/' in name or 'bounded/' in name):
                value = json.loads(zipped.read(name))
                selected = [{'id': item.get('id'), 'status': item.get('status'),
                             'error': item.get('error'), 'detail': item.get('detail'),
                             'elapsed_ms': item.get('elapsed_ms')}
                            for item in value.get('cases', []) if item.get('status') != 'pass']
                item = {'path': name, 'summary': value.get('summary'), 'failures': selected}
                report['entries'].append(item); print(json.dumps(item))
                for failed in value.get('cases', []):
                    if failed.get('status') == 'pass':
                        continue
                    shot_name = name.rsplit('/', 1)[0] + '/' + failed['screenshot']
                    shot = output / (failed['id'] + '.png')
                    shot.write_bytes(zipped.read(shot_name))
                    observed = subprocess.run(['tesseract', str(shot), 'stdout'],
                                              capture_output=True, text=True, check=True).stdout
                    item = {'screenshot': shot_name, 'observed_text': observed}
                    report['entries'].append(item); print(json.dumps(item))
            if name.endswith(('review-logcat.txt', 'bounded-logcat.txt')):
                text = zipped.read(name).decode('utf-8', 'replace')
                lines = text.splitlines()
                starts = [line for line in lines if 'EXRReview' in line and 'case start' in line]
                events = [line for line in lines if
                          ('EXRHost' in line and any(token in line for token in (
                              'status ', 'progress attempt', 'worker shutdown', 'repair pending',
                              'Library error', 'budget exhausted', 'storage mode', 'progress resolve')))
                          or re.search(r'AndroidRuntime.*(?:FATAL EXCEPTION|Process:|Exception:|Error:)', line)
                          or re.search(r'ActivityManager.*(?:ANR in|Killing.*org.exreader|Process.*org.exreader.*died)', line)]
                item = {'path': name, 'bytes': len(zipped.read(name)),
                        'case_starts': starts, 'events': events[-160:]}
                report['entries'].append(item); print(json.dumps(item))
                lower, upper = ('10-23 19:49:40', '10-23 19:50:04') if 'review-' in name else (
                    '10-23 19:53:30', '10-23 19:53:56')
                relevant = [line[:700] for line in lines if lower <= line[:14] <= upper
                            and re.search(r'Activity|Window|Input|EXR|ViewRoot|Choreographer|RenderThread|OpenGLRenderer|BufferQueue|Surface', line)
                            and not re.search(r'\bat [\w.$]+\(', line)]
                item = {'window_path': name, 'lower': lower, 'upper': upper, 'lines': relevant[-180:]}
                report['entries'].append(item); print(json.dumps(item))
        print(json.dumps({'other_diagnostic_paths': [name for name in names if any(
            token in name for token in ('uiautomator', 'window', 'hierarchy', 'logcat', 'instrumentation'))]}))
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
