"""Actions-only installed SDK correctness orchestration; no product modifications."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/ot-cache-acceptance'
CANDIDATE = '5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9'
BASELINE = '25c2ef86c5c1c4e72b2c9d9daf8c47873c49bcab'


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def identity():
    return {'test_source_sha': os.environ['GITHUB_SHA'], 'candidate_sdk_sha': CANDIDATE,
            'baseline_sdk_sha': BASELINE, 'run_id': os.environ['GITHUB_RUN_ID'],
            'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'os': os.environ['RUNNER_OS']}


def git(*args, cwd=ROOT):
    return subprocess.check_output(['git', *args], cwd=cwd, text=True).strip()


def command(args, name, cwd=ROOT, timeout=1800):
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with (OUT / (name + '.log')).open('w', encoding='utf-8') as log:
        log.write('$ ' + ' '.join(map(str, args)) + '\n')
        log.flush()
        try:
            p = subprocess.run(list(map(str, args)), cwd=cwd, stdout=log,
                               stderr=subprocess.STDOUT, timeout=timeout)
            code = p.returncode
        except subprocess.TimeoutExpired:
            code = 124
            log.write('\nPROCESS TIMEOUT; original timeout retained.\n')
    record = {'command': list(map(str, args)), 'returncode': code,
              'seconds': time.monotonic() - started, 'log': name + '.log'}
    write(OUT / (name + '.command.json'), record)
    print(json.dumps(record), flush=True)
    if code:
        print((OUT / (name + '.log')).read_text(encoding='utf-8', errors='replace')[-24000:])
    return code


def guard():
    assert git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA']
    subprocess.run(['git', 'merge-base', '--is-ancestor', CANDIDATE, 'HEAD'], check=True)
    changed = git('diff', '--name-only', CANDIDATE, 'HEAD').splitlines()
    assert changed
    for path in changed:
        assert path == '.github/workflows/sdk-ot-cache-acceptance.yml' or path.startswith('tests/opentype_cache_acceptance/') or path.startswith('docs/handoffs/ot-cache-acceptance'), path
    for name, sha in [('candidate', CANDIDATE), ('baseline', BASELINE)]:
        directory = ROOT / ('sdk-' + name)
        assert git('rev-parse', 'HEAD', cwd=directory) == sha
        assert not git('status', '--porcelain', cwd=directory)
    write(OUT / 'provenance.json', {**identity(), 'changed_files': changed,
          'frozen_sdk_and_original_tests_unmodified': True})
    print(json.dumps({**identity(), 'admitted': True}))


def build():
    failures = []
    for name in ('baseline', 'candidate'):
        sdk = ROOT / ('sdk-' + name)
        prefix = sdk / 'build/reading-library/stage'
        stages = [(['cmake', '--preset', 'reading-library'], 'configure-sdk', sdk),
                  (['cmake', '--build', '--preset', 'reading-library'], 'build-sdk', sdk),
                  (['cmake', '--install', 'build/reading-library'], 'install-sdk', sdk)]
        ready = True
        for args, label, cwd in stages:
            if command(args, name + '-' + label, cwd):
                failures.append(name + '-' + label)
                ready = False
                break
        if not ready:
            continue
        installed = {str(p.relative_to(prefix)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(prefix.rglob('*')) if p.is_file()}
        write(OUT / (name + '-installed-files.json'), installed)
        for suite, source in [('acceptance', 'tests/opentype_cache_acceptance'),
                              ('retained', 'tests/bounded_txt_scan')]:
            directory = ROOT / 'build' / ('ot-' + name + '-' + suite)
            args = ['cmake', '-S', str(ROOT / source), '-B', str(directory), '-G', 'Ninja',
                    '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_PREFIX_PATH=' + str(prefix)]
            if command(args, name + '-' + suite + '-configure'):
                failures.append(name + '-' + suite + '-configure')
                continue
            if command(['cmake', '--build', directory, '--parallel', '4'], name + '-' + suite + '-build'):
                failures.append(name + '-' + suite + '-build')
                continue
            if suite == 'retained':
                # All seven existing registered checks; excludes unregistered 3000-page benchmark.
                args = ['ctest', '--test-dir', directory, '--output-on-failure', '--no-tests=error',
                        '--output-junit', str(OUT / (name + '-retained.xml'))]
                if command(args, name + '-retained-ctest'):
                    failures.append(name + '-retained-ctest')
    write(OUT / 'build-result.json', {**identity(), 'accepted': not failures, 'failures': failures})
    return int(bool(failures))


def verify():
    fixtures = OUT / 'fixtures'
    if command([sys.executable, ROOT / 'tests/opentype_cache_acceptance/generate_fixtures.py', '--output', fixtures], 'generate-fixtures'):
        return 1
    suffix = '.exe' if os.name == 'nt' else ''
    binaries = {name: ROOT / 'build' / ('ot-' + name + '-acceptance') / ('ot_cache_acceptance' + suffix)
                for name in ('baseline', 'candidate')}
    for path in binaries.values():
        if not path.is_file():
            print('Missing installed-SDK consumer: ' + str(path))
            return 1
    return int(bool(command([sys.executable, ROOT / 'tests/opentype_cache_acceptance/compare.py',
               '--baseline', binaries['baseline'], '--candidate', binaries['candidate'],
               '--fixtures', fixtures, '--output', OUT / 'comparison'], 'compare-public-sdk')))


def seal():
    OUT.mkdir(parents=True, exist_ok=True)
    commands = [json.loads(p.read_text()) for p in sorted(OUT.glob('*.command.json'))]
    required = ['provenance.json', 'build-result.json', 'compare-public-sdk.command.json']
    missing = [name for name in required if not (OUT / name).is_file()]
    failed = [c['log'] for c in commands if c['returncode'] != 0]
    if (OUT / 'build-result.json').is_file() and not json.loads((OUT / 'build-result.json').read_text())['accepted']:
        failed.append('build-result.json')
    files = {str(p.relative_to(OUT)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(OUT.rglob('*')) if p.is_file() and p.name != 'seal.json'}
    report = {**identity(), 'accepted': not missing and not failed, 'missing': missing,
              'failed_commands': failed, 'files': files}
    write(OUT / 'seal.json', report)
    print(json.dumps(report))
    return int(not report['accepted'])


def aggregate():
    found = {}
    errors = []
    for path in (ROOT / 'build/ot-cache-collected').glob('*/seal.json'):
        item = json.loads(path.read_text())
        platform = item['os']
        if platform in found:
            errors.append('duplicate OS: ' + platform)
        found[platform] = item
        for key in ('test_source_sha', 'candidate_sdk_sha', 'baseline_sdk_sha', 'run_id', 'attempt'):
            if item.get(key) != identity()[key]:
                errors.append(platform + ': mismatched ' + key)
        if not item['accepted']:
            errors.append(platform + ': rejected seal')
        for name, digest in item['files'].items():
            file = path.parent / name
            if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != digest:
                errors.append(platform + ': hash mismatch ' + name)
    if set(found) != {'Windows', 'Linux', 'macOS'}:
        errors.append('missing operating systems')
    fixture_sets = {platform: {name: digest for name, digest in item['files'].items()
                    if name.startswith('fixtures/')} for platform, item in found.items()}
    if fixture_sets:
        reference = next(iter(fixture_sets.values()))
        if not reference:
            errors.append('empty fixture evidence')
        for platform, fixtures in fixture_sets.items():
            if fixtures != reference:
                errors.append(platform + ': generated fixture identity differs across platforms')
    if os.environ.get('MATRIX_RESULT') != 'success':
        errors.append('matrix result not success')
    report = {**identity(), 'accepted': not errors, 'failures': errors,
              'platforms': {k: {'accepted': v['accepted'], 'file_count': len(v['files'])} for k, v in found.items()}}
    write(ROOT / 'build/ot-cache-authentication.json', report)
    print(json.dumps(report, indent=2))
    return int(bool(errors))


if __name__ == '__main__':
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Execute only in GitHub Actions.'
    os.chdir(ROOT)
    raise SystemExit({'guard': guard, 'build': build, 'verify': verify, 'seal': seal,
                      'aggregate': aggregate}[sys.argv[1]]() or 0)
