"""Isolated Actions inspection of the original failed OFF controls, never acceptance."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip
RUN = 40203714083
SOURCE = '72c6bbdd14ebf3be453fa7f0da81119d52675eb5'
ARTIFACT = 12602953966
CASES = ('testFixedCbzAndPdfRealPointRecords', 'testRealTerminationAfterCommitReplaysExactlyOnce')


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    out = ROOT / 'build/apple-raw3-ios-inspection'; out.mkdir(parents=True, exist_ok=False)
    run = fetch('actions/runs/' + str(RUN))
    assert run['head_sha'] == SOURCE and run['run_attempt'] == 1 and run['path'] == '.github/workflows/reader-apple-raw3-ios.yml'
    jobs = fetch(f'actions/runs/{RUN}/attempts/1/jobs?per_page=100')['jobs']
    assert any(row['id'] == 121200931637 and row['name'] == 'Actual raw iOS UI iphone' and row['conclusion'] == 'failure' for row in jobs)
    meta = fetch('actions/artifacts/' + str(ARTIFACT))
    assert meta['name'] == 'apple-raw3-ios-iphone-40203714083-1' and not meta['expired']
    assert meta['workflow_run']['head_sha'] == SOURCE and meta['workflow_run']['id'] == RUN
    assert meta['size_in_bytes'] == 182452877 and meta['digest'] == 'sha256:3675f79031dc88ec8abf5217cf70a856a967c74812cd8a8030410bbbf7a48ad3'
    raw = download_artifact_zip(ARTIFACT)
    assert len(raw) == meta['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == meta['digest']
    original = out / 'original'; original.mkdir()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert len(archive.namelist()) == len(set(archive.namelist()))
        for info in archive.infolist():
            path = PurePosixPath(info.filename)
            assert not path.is_absolute() and '..' not in path.parts and '\\' not in info.filename
            assert (info.external_attr >> 16) & 0o170000 != 0o120000
            if not (any(part.endswith('.xcresult') for part in path.parts) or path.suffix in ('.log', '.json', '.txt')): continue
            assert info.file_size <= 256 * 1024**2
            destination = original.joinpath(*path.parts)
            if info.is_dir(): destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, destination.open('wb') as output: shutil.copyfileobj(source, output)
    logs = list(original.rglob('original-OFF-seven-cases.log'))
    assert len(logs) == 1
    lines = logs[0].read_text(errors='replace').splitlines()
    indices = [index for index, line in enumerate(lines) if 'error:' in line or 'exceeded execution time' in line or 'Test Case' in line and 'failed' in line]
    excerpts = []
    for index in indices[:20]:
        text = '\n'.join(lines[max(0, index - 8):index + 10])
        print('ORIGINAL-ERROR-CONTEXT', index + 1, text, flush=True); excerpts.append(text)
    (out / 'original-error-context.txt').write_text('\n\n'.join(excerpts) + '\n')
    bundles = list(original.rglob('original-OFF-seven-cases.xcresult')); assert len(bundles) == 1
    bundle = bundles[0]
    commands = []
    def command(name, *args):
        value = subprocess.run(['xcrun', 'xcresulttool', *map(str, args)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
        body = value.stdout.decode(errors='replace')
        (out / (name + '.txt')).write_text(body)
        commands.append({'name': name, 'exit': value.returncode})
        print(name, body[:26000], flush=True)
        return body if value.returncode == 0 else None
    command('summary', 'get', 'test-results', 'summary', '--path', bundle, '--format', 'json')
    tests = command('tests', 'get', 'test-results', 'tests', '--path', bundle, '--format', 'json')
    identifiers = []
    def walk(value):
        if isinstance(value, dict):
            if any(case in str(value.get('name', '')) for case in CASES):
                print('FAILED-CASE-NODE', json.dumps(value), flush=True)
                identifiers.extend(str(value[key]) for key in ('nodeIdentifier', 'testIdentifier', 'identifier') if value.get(key))
            for child in value.values(): walk(child)
        elif isinstance(value, list):
            for child in value: walk(child)
    if tests: walk(json.loads(tests))
    for index, identifier in enumerate(dict.fromkeys(identifiers or ['ReadingUITests/' + case + '()' for case in CASES])):
        command('activities-' + str(index), 'get', 'test-results', 'activities', '--path', bundle, '--test-id', identifier, '--format', 'json')
    attachments = out / 'attachments'
    command('attachments-export', 'export', 'attachments', '--path', bundle, '--output-path', attachments)
    traces = []
    for path in attachments.rglob('*'):
        if path.is_file() and path.suffix in ('.txt', '.json', '.log') and path.stat().st_size <= 2 * 1024**2:
            text = path.read_text(errors='replace')
            if any(key in text for key in ('fixture-request', 'import-request', 'rejected-unready', 'committed', 'library.title')):
                print('ORIGINAL-AX-TRACE', path.name, text[:26000], flush=True); traces.append(path.name)
    result = {'accepted': False, 'diagnostic_only': True, 'original_source': SOURCE, 'original_run': RUN, 'original_attempt': 1,
              'original_job': 121200931637, 'diagnostic_source': os.environ['GITHUB_SHA'],
              'artifact': {key: meta[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')},
              'failed_cases': CASES, 'commands': commands, 'AX_trace_attachments': traces, 'original_failure_preserved': True}
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
