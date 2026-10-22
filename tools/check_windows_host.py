#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Drive the packaged Windows host through the acceptance phases and validate.

The host records every UI-level action it receives (button clicks, keyboard
focus traversal, mouse selection, window resizes, cancellations) in a
line-oriented drive.log. This checker starts the real executable three times,
then verifies persistence, anchored restore, cancellation, stale-task ownership
and packaging hashes. Raw logs stay in the CI artifact.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ACTIONS = {
    'import', 'import_async', 'open', 'next', 'prev', 'font_inc', 'resize',
    'select_all', 'drag', 'add_note', 'update_note', 'delete_note',
    'delete_book', 'jump_note', 'cancel', 'wait_idle',
}
PHASES = ('A', 'B', 'C')
EXPECTED_STEPS = {'A': 120, 'B': 29, 'C': 9}
EXPECTED_SHOTS = {'A': {'00-empty-shelf', '01-epub-page1', '02-resized', '03-pdf-page1', '04-stale-final'},
                  'B': {'10-restored', '11-font-changed'}, 'C': {'20-restored-after-font'}}
ARITIES = {'state': 1, 'snapshot': 1, 'import': 1, 'import_async': 1, 'open': 1,
           'note': 1, 'delete_book': 1, 'note_select': 1, 'jump_note': 1,
           'resize': 2, 'drag': 4, 'delay': 1, 'wait_idle': 0, 'next': 0,
           'prev': 0, 'font_inc': 0, 'font_dec': 0, 'select_all': 0,
           'copy': 0, 'add_note': 0, 'update_note': 0, 'delete_note': 0,
           'cancel': 0, 'quit': 0}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


def unescape(value):
    out = []
    i = 0
    while i < len(value):
        if value[i] == '%' and i + 2 < len(value):
            try:
                out.append(chr(int(value[i + 1:i + 3], 16)))
                i += 3
                continue
            except ValueError:
                pass
        out.append(value[i])
        i += 1
    return ''.join(out)


def fields(text):
    result = {}
    for part in (text or '').split(';'):
        if '=' in part:
            key, value = part.split('=', 1)
            key = unescape(key)
            require(key and key not in result, 'duplicate or empty evidence field')
            result[key] = unescape(value)
    return result


def script_plan(text, phase):
    plan = []
    for line in text.splitlines():
        if not line or line.startswith('#'):
            continue
        parts = line.split('|')
        action, parameters = parts[0], parts[1:]
        if action == 'check':
            sizes = {'shelf': 4, 'status': 4, 'clipboard': 4, 'selection': 3,
                     'book': 3, 'page': 3, 'notes': 3, 'font': 3}
            require(len(parts) >= 2 and len(parts) == sizes.get(parts[1]), 'unknown check or parameter count')
            if parts[1] in ('status', 'clipboard'):
                require(parts[2] == 'contains', 'unsupported check comparison')
            if parts[1] == 'shelf':
                require(parts[2] == 'count', 'unsupported shelf comparison')
            if parts[1] == 'selection':
                require(parts[2] == 'nonempty', 'unsupported selection comparison')
        else:
            require(action in ARITIES and len(parameters) == ARITIES[action], 'unknown action or parameter count')
        require(all(parameters) and not any('\t' in x or '\r' in x for x in parts), 'empty or malformed action parameter')
        if action in ('state', 'snapshot'):
            require(re.fullmatch('[A-Za-z0-9_-]+', parameters[0]) is not None, 'unsafe evidence name')
        plan.append({'index': len(plan) + 1, 'action': action, 'parameters': parameters})
    require(len(plan) == EXPECTED_STEPS[phase] and plan[-1]['action'] == 'quit' and
            sum(x['action'] == 'quit' for x in plan) == 1, 'script differs from the fixed phase plan')
    names = [x['parameters'][0] for x in plan if x['action'] == 'snapshot']
    require(len(names) == len(set(names)) and set(names) == EXPECTED_SHOTS[phase], 'script screenshot plan changed')
    state_names = [x['parameters'][0] for x in plan if x['action'] == 'state']
    require(len(state_names) == len(set(state_names)), 'duplicate planned state')
    return plan


def check_parameters(planned, observed):
    args = planned['parameters']
    if planned['action'] != 'check':
        return
    kind = args[0]
    key = {'shelf': 'count', 'notes': 'count', 'page': 'page', 'font': 'font',
           'selection': 'active', 'status': 'needle', 'clipboard': 'needle', 'book': 'title'}[kind]
    expected = args[2] if kind in ('shelf', 'status', 'clipboard') else args[1]
    actual = observed.get(key)
    if kind == 'selection':
        require(actual == '1', 'selection parameter was not satisfied')
    elif kind == 'book':
        require(isinstance(actual, str) and expected in actual, 'book parameter was not satisfied')
    else:
        require(actual == expected, 'check parameter differs from observed evidence')


def parse_log(path, plan, phase, version, pid):
    steps, states, shelf, notes, shots = [], {}, {}, {}, {}
    done, host = [], []
    require(path.is_file(), 'missing phase drive.log')
    for line_number, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        require(raw and not done, 'empty evidence record or records after DONE')
        parts = raw.split('\t')
        kind = parts[0]
        if kind == 'HOST':
            require(line_number == 1 and len(parts) == 4 and not host, 'missing or duplicate HOST header')
            header = fields(';'.join(parts[1:]))
            require(header == {'phase': str(PHASES.index(phase) + 1), 'engine': version, 'pid': str(pid)} and pid > 0,
                    'HOST phase, runtime version or process identity mismatch')
            host.append(header)
            continue
        require(host and len(parts) == 5 and kind in ('STEP', 'STATE', 'SHELF', 'NOTE', 'SHOT', 'DONE'),
                'unknown or malformed evidence record')
        require(parts[1].isdigit(), 'invalid evidence index')
        index, action, result = int(parts[1]), parts[2], parts[3]
        require(1 <= index <= len(plan) and result == 'PASS', 'invalid index or failed evidence record')
        detail = fields(parts[4])
        planned = plan[index - 1]
        if kind == 'STEP':
            require(index == len(steps) + 1 and action == planned['action'], 'missing, duplicate or reordered STEP')
            check_parameters(planned, detail)
            if action == 'state':
                require(planned['parameters'][0] in states, 'state action lacks its STATE record')
            if action == 'snapshot':
                require(planned['parameters'][0] in shots, 'snapshot action lacks its SHOT record')
            steps.append({'index': index, 'action': action, 'parameters': planned['parameters'],
                          'parameter_binding': 'sealed executed script and index; check observations revalidated',
                          'result': result, 'observed': detail})
        elif kind == 'STATE':
            require(index == len(steps) + 1 and planned['action'] == 'state' and
                    action == planned['parameters'][0] and action not in states and detail.get('state') == action,
                    'duplicate or unplanned STATE')
            states[action] = detail
        elif kind in ('SHELF', 'NOTE'):
            require(index == len(steps) + 1 and planned['action'] == 'state' and
                    action == planned['parameters'][0] and action in states and detail.get('id'),
                    'unplanned shelf or note row')
            rows = (shelf if kind == 'SHELF' else notes).setdefault(action, [])
            require(detail['id'] not in {row['id'] for row in rows}, 'duplicate shelf or note identity')
            rows.append(detail)
        elif kind == 'SHOT':
            require(index == len(steps) + 1 and planned['action'] == 'snapshot' and
                    action == planned['parameters'][0] and action not in shots and
                    detail.get('file') == action and detail.get('nonzero') == '1', 'missing, blank or unsafe SHOT')
            shots[action] = detail
        elif kind == 'DONE':
            require(index == len(plan) == len(steps) and action == 'eof' and parts[4] == 'script finished' and
                    steps[-1]['action'] == 'quit', 'DONE contradicts the complete script')
            done.append({'action': action, 'result': result, 'detail': detail})
    require(len(steps) == len(plan) and len(done) == 1 and set(shots) == EXPECTED_SHOTS[phase],
            'truncated phase or missing planned screenshots')
    return steps, states, shelf, notes, shots, done, host


def png_identity(path):
    header = path.read_bytes()[:24]
    require(len(header) == 24 and header[:8] == b'\x89PNG\r\n\x1a\n' and header[12:16] == b'IHDR' and
            all(struct.unpack('>II', header[16:24])), 'invalid screenshot PNG')
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest(path)}


def safe_file(root, name):
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name and
            not Path(name).is_absolute() and '..' not in Path(name).parts and Path(name).as_posix() == name,
            'unsafe manifest path')
    path = root / name
    require(path.resolve().is_relative_to(root.resolve()) and path.is_file(), 'missing or escaped manifest file')
    return path


def verify_file_manifest(root, expected, required):
    require(isinstance(expected, dict) and required <= expected.keys(), 'manifest lacks mandatory files')
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    require(actual == set(expected), 'manifest omits or adds package files')
    for name, sha in expected.items():
        require(isinstance(sha, str) and re.fullmatch('[0-9a-f]{64}', sha) and
                digest(safe_file(root, name)) == sha, 'manifest file hash mismatch: ' + name)


def snapshot(paths):
    return {str(p.resolve()): digest(p) for p in sorted(set(paths))}


def unchanged(identities):
    require(all(Path(name).is_file() and digest(Path(name)) == sha for name, sha in identities.items()),
            'sealed program, SDK, font, original, script or manifest changed during execution')


def source_identity():
    sha = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    require(sha == os.environ.get('GITHUB_SHA', sha), 'checkout and workflow source differ')
    dirty = subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=no'], text=True)
    require(not dirty.strip(), 'tracked source changed')
    return sha


def render_script(template, package, fixtures):
    return (template.replace('@@SAMPLE@@', str(package))
                    .replace('@@FIXTURES@@', str(fixtures)))


def run_phase(exe, script, output, phase, data, package, timeout):
    evidence = output / phase
    evidence.mkdir(parents=True, exist_ok=True)
    command = [str(exe), '--drive', str(script), '--evidence', str(evidence),
               '--data', str(data), '--library', str(data / 'library.sqlite'),
               '--phase', str(PHASES.index(phase) + 1)]
    env = dict(os.environ)
    env.setdefault('EXREADER_HOST_ACCEPTANCE', '1')
    creationflags = 0
    if os.name == 'nt':
        creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    started = time.time()
    try:
        process = subprocess.Popen(command, cwd=str(package), env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, encoding='utf-8',
                                   errors='replace', creationflags=creationflags)
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as expired:
        process.kill()
        stdout, stderr = process.communicate()
        (output / ('phase-' + phase + '.stdout.log')).write_text(
            'timeout after %.1fs\nstdout=%r\nstderr=%r' % (timeout, stdout, stderr), encoding='utf-8')
        return 124, timeout, process.pid
    elapsed = time.time() - started
    (output / ('phase-' + phase + '.stdout.log')).write_text(
        (stdout or '') + '\n--- stderr ---\n' + (stderr or ''), encoding='utf-8')
    return process.returncode, elapsed, process.pid


def seal_inputs(package, sdk, manifest_path, selftest_path, consumer, steps_dir, fixtures, output):
    from host_font import ASSETS
    source_sha = source_identity()
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    base_header = sdk / 'include/exr/base.h'
    version_match = re.search(r'#define EXR_VERSION "([^"]+)"', base_header.read_text(encoding='utf-8'))
    require(version_match is not None, 'installed SDK version is missing')
    version = version_match[1]
    require(type(manifest.get('schema')) is int and manifest['schema'] == 1 and manifest.get('passed') is True and
            manifest.get('source_sha') == source_sha and manifest.get('sdk_version') == version and
            type(manifest.get('selftest_checks')) is int and manifest['selftest_checks'] == 26,
            'package source, version or native self-test identity mismatch')
    runtime_names = [name for name in ('exreader.dll', 'libexreader.dll') if (package / name).is_file()]
    require(len(runtime_names) == 1, 'require exactly one packaged runtime')
    runtime = runtime_names[0]
    required = {'EXReader.exe', runtime, 'Reader.otf', 'OFL.txt', 'LICENSE.txt', 'THIRD_PARTY_NOTICES.md',
                'Sample.epub', 'Sample.pdf', 'Sample-Text.pdf'}
    verify_file_manifest(package, manifest.get('files'), required)
    require(digest(package / 'EXReader.exe') == digest(consumer), 'packaged executable differs from installed SDK consumer')
    require(digest(package / runtime) == digest(sdk / 'bin' / runtime), 'packaged runtime differs from installed SDK')
    require(all(digest(package / name) == expected for name, (_, expected) in ASSETS.items()),
            'font or font license differs from the pinned reference asset')
    selftest = json.loads(selftest_path.read_text(encoding='utf-8'))
    require(type(selftest.get('schema')) is int and selftest['schema'] == 1 and selftest.get('passed') is True and
            type(selftest.get('checks')) is int and selftest['checks'] == 26 and
            selftest.get('engine_version') == version and digest(selftest_path) == manifest.get('report_sha256'),
            'native 26-check self-test report differs from package registration')
    image = selftest_path.parent / 'page.png'
    require(png_identity(image)['sha256'] == manifest.get('image_sha256'), 'self-test PNG differs from package registration')
    fixture_manifest_path = fixtures / 'fixtures.json'
    fixture_manifest = json.loads(fixture_manifest_path.read_text(encoding='utf-8'))
    fixture_names = {'Extra-Book.epub', 'Stale-Book.epub', 'Cancel-Big.epub', 'Pages.pdf', 'Broken.epub', 'Unsupported.bin'}
    require(type(fixture_manifest.get('schema')) is int and fixture_manifest['schema'] == 1 and
            set(fixture_manifest.get('files', {})) == fixture_names,
            'fixture inventory differs from the original acceptance inputs')
    require({p.name for p in fixtures.iterdir()} == fixture_names | {'fixtures.json'}, 'unexpected fixture inputs')
    for name, record in fixture_manifest['files'].items():
        path = safe_file(fixtures, name)
        require(path.stat().st_size == record.get('bytes') and digest(path) == record.get('sha256'),
                'original fixture identity mismatch: ' + name)
    plans, scripts = {}, {}
    paths = [manifest_path, selftest_path, image, consumer, base_header, sdk / 'bin' / runtime,
             ROOT / 'tools/check_windows_host.py', ROOT / 'tools/build_windows_host.py',
             ROOT / 'tests/windows_host/make_fixtures.py', ROOT / 'examples/reader.c',
             *[p for p in package.rglob('*') if p.is_file()], *[p for p in fixtures.iterdir() if p.is_file()]]
    for phase in PHASES:
        template = steps_dir / ('phase-' + phase.lower() + '.txt')
        canonical = ROOT / 'tests/windows_host' / template.name
        require(digest(template) == digest(canonical), 'input phase differs from the committed acceptance script')
        script = output / ('phase-' + phase + '.script')
        script.write_text(render_script(template.read_text(encoding='utf-8'), package, fixtures), encoding='utf-8')
        plans[phase] = script_plan(script.read_text(encoding='utf-8'), phase)
        scripts[phase] = script
        paths.extend((template, canonical, script))
    acceptance_source = subprocess.check_output(['git', '-C', str(ROOT), 'log', '-1', '--format=%H', '--',
        'examples/reader.c', 'tools/build_windows_host.py', 'tests/windows_host/phase-a.txt',
        'tests/windows_host/phase-b.txt', 'tests/windows_host/phase-c.txt', 'tests/windows_host/make_fixtures.py'], text=True).strip()
    seal = {'schema': 1, 'source_sha': source_sha, 'checker_source_sha': source_sha,
            'checker_sha256': digest(ROOT / 'tools/check_windows_host.py'),
            'acceptance_definition_sha': acceptance_source, 'sdk_version': version,
            'identities': snapshot(paths), 'plans': plans,
            'package_files': manifest['files'], 'runtime': runtime,
            'selftest': {'passed': True, 'checks': 26, 'engine_version': version, 'sha256': digest(selftest_path)},
            'parameter_observation_scope': 'Native log echoes check results and named states/screenshots. Other action parameters are bound to the sealed executed script, not independently echoed by this unchanged host.'}
    (output / 'pre-run-identities.json').write_text(json.dumps(seal, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    seal['seal_sha256'] = digest(output / 'pre-run-identities.json')
    return seal, plans, scripts


def normalized_notes(rows):
    return sorted((row.get('id', ''), row.get('quote', ''), row.get('comment', '')) for row in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--steps', type=Path, default=ROOT / 'tests' / 'windows_host')
    parser.add_argument('--fixtures', type=Path)
    parser.add_argument('--selftest-report', type=Path, required=True)
    parser.add_argument('--consumer-binary', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=420)
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    package = args.package.resolve()
    output = args.output.resolve()
    sdk = args.sdk.resolve()
    if output.exists():
        parser.error('choose a new evidence directory')
    output.mkdir(parents=True)
    errors = []
    exe = package / 'EXReader.exe'
    if not exe.exists():
        parser.error('packaged EXReader.exe is missing')
    fixtures = args.fixtures.resolve() if args.fixtures else output / 'fixtures'
    if not args.fixtures:
        subprocess.run([sys.executable, str(ROOT / 'tests' / 'windows_host' / 'make_fixtures.py'),
                        '--output', str(fixtures)], check=True, capture_output=True, text=True)
    elif not fixtures.exists():
        parser.error('fixture directory is missing')
    data = output / 'data'
    if data.exists():
        shutil.rmtree(data)
    data.mkdir(parents=True)

    try:
        seal, plans, scripts = seal_inputs(package, sdk, args.manifest.resolve(), args.selftest_report.resolve(),
                                          args.consumer_binary.resolve(), args.steps.resolve(), fixtures, output)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        refusal = {'schema': 1, 'passed': False, 'errors': ['preflight: ' + str(error)]}
        (output / 'summary.json').write_text(json.dumps(refusal, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(refusal))
        return 1

    runs = {}
    for phase in PHASES:
        try:
            unchanged(seal['identities'])
        except (OSError, ValueError) as error:
            errors.append(str(error))
            break
        code, elapsed, pid = run_phase(exe, scripts[phase], output, phase, data, package, args.timeout)
        runs[phase] = {'exit_code': code, 'elapsed_seconds': round(elapsed, 3), 'pid': pid}
        log_path = output / phase / 'drive.log'
        print('PHASE %s exit=%s elapsed=%.2fs log=%s' % (phase, code, elapsed, log_path.exists()),
              flush=True)
        if not log_path.exists():
            stdout_path = output / ('phase-' + phase + '.stdout.log')
            if stdout_path.exists():
                print('PHASE %s stdout tail: %s' % (phase, stdout_path.read_text(
                    encoding='utf-8', errors='replace')[-800:]), flush=True)

    parsed = {}
    for phase in PHASES:
        try:
            require(phase in runs, 'phase was not executed')
            parsed[phase] = parse_log(output / phase / 'drive.log', plans[phase], phase, seal['sdk_version'], runs[phase]['pid'])
        except (OSError, ValueError) as error:
            errors.append('phase ' + phase + ': ' + str(error))
            parsed[phase] = ([], {}, {}, {}, {}, [], [])
            runs.setdefault(phase, {'exit_code': 125, 'elapsed_seconds': 0, 'pid': 0})

    steps = []
    states, shelf, notes, shots, done, host = {}, {}, {}, {}, {}, {}
    for phase in PHASES:
        psteps, pstates, pshelf, pnotes, pshots, pdone, phost = parsed[phase]
        for step in psteps:
            step['phase'] = phase
            steps.append(step)
        states[phase] = pstates
        shelf[phase] = pshelf
        notes[phase] = pnotes
        shots[phase] = pshots
        done[phase] = pdone
        host[phase] = phost
        if runs[phase]['exit_code'] != 0:
            errors.append('phase ' + phase + ' exited with ' + str(runs[phase]['exit_code']))
        if not pdone or pdone[-1]['result'] != 'PASS':
            errors.append('phase ' + phase + ' did not finish cleanly')
        for step in psteps:
            if step['result'] != 'PASS':
                errors.append('phase ' + phase + ' step ' + str(step['index']) + ' ' +
                              step['action'] + ' failed: ' + json.dumps(step['observed'], ensure_ascii=False))
        for name, shot in pshots.items():
            image = output / phase / (shot.get('file', name) + '.png')
            try:
                require(image.resolve().is_relative_to((output / phase).resolve()), 'screenshot escapes phase directory')
                shot.update(png_identity(image))
            except (OSError, ValueError) as error:
                errors.append('phase ' + phase + ' screenshot ' + name + ': ' + str(error))

    if errors:
        for phase in PHASES:
            for name in ('epub_open', 'pdf_open', 'stale_done', 'final', 'restored', 'after_restart'):
                if name in states.get(phase, {}):
                    print('STATEDIAG %s/%s %s' % (phase, name, json.dumps(
                        states[phase][name], ensure_ascii=True)), flush=True)
            for step in steps:
                if step['phase'] != phase:
                    continue
                if step['result'] != 'PASS' or step['index'] <= 20:
                    print('STEPDIAG %s %d %s %s %s' % (
                        phase, step['index'], step['action'], step['result'],
                        json.dumps(step['observed'], ensure_ascii=True)), flush=True)

    if len(steps) != sum(EXPECTED_STEPS.values()):
        errors.append('UI steps differ from the fixed 158-action plan')
    actions = {step['action'] for step in steps}
    missing = sorted(REQUIRED_ACTIONS - actions)
    if missing:
        errors.append('missing required UI actions: ' + ', '.join(missing))

    def state(phase, name):
        value = states.get(phase, {}).get(name)
        if value is None:
            errors.append('missing state ' + phase + '/' + name)
            return {}
        return value

    a_start = state('A', 'start')
    a_import = state('A', 'epub_imported')
    a_open = state('A', 'epub_open')
    a_final = state('A', 'final')
    a_stale = state('A', 'stale_done')
    a_cancel = state('A', 'cancel_done')
    b_restored = state('B', 'restored')
    b_before = state('B', 'before_restart_font')
    c_after = state('C', 'after_restart')
    if a_start.get('page') not in (None, '0') or a_start.get('book_id') != '0':
        errors.append('phase A did not start with an empty reading state')
    if a_import.get('selected_id') in (None, '', '0'):
        errors.append('EPUB import did not produce a selected shelf row')
    if a_open.get('kind') != 'reflow':
        errors.append('EPUB did not open through the reflow path')
    if a_final.get('kind') != 'reflow':
        errors.append('phase A did not finish on the reflow book')
    if a_final.get('book_id') != b_restored.get('book_id'):
        errors.append('restart did not restore the same book')
    if a_final.get('page') != b_restored.get('page'):
        errors.append('restart did not restore the same page')
    if a_final.get('title') != b_restored.get('title'):
        errors.append('restart changed the logical book title')
    if a_final.get('notes') != b_restored.get('notes'):
        errors.append('restart changed the logical annotation count')
    if normalized_notes(notes.get('A', {}).get('final', [])) != \
            normalized_notes(notes.get('B', {}).get('restored', [])):
        errors.append('saved annotations were not preserved across restart')
    shelf_a = sorted((row.get('id'), row.get('title')) for row in shelf.get('A', {}).get('final', []))
    shelf_b = sorted((row.get('id'), row.get('title')) for row in shelf.get('B', {}).get('restored', []))
    if shelf_a != shelf_b:
        errors.append('bookshelf contents changed across restart')
    if len(shelf_a) != 2:
        errors.append('expected two shelf books at the end of phase A, found ' + str(len(shelf_a)))
    if b_before.get('offset') != c_after.get('offset') or \
            b_before.get('offset_text') != c_after.get('offset_text'):
        errors.append('restart after a font change did not restore the anchored text offset')
    if '恢复' not in c_after.get('status', ''):
        errors.append('the restart did not report an explicit restore decision')
    if a_stale.get('book_id') != a_open.get('book_id') or \
            'EXReader benchmark' not in a_stale.get('title', ''):
        errors.append('a superseded import overwrote the newly opened book')
    if len(shelf.get('A', {}).get('stale_done', [])) != 2:
        errors.append('the superseded import added a shelf row')
    if '取消' not in a_cancel.get('status', ''):
        errors.append('cancelled import did not report cancellation')
    if len(shelf.get('A', {}).get('cancel_done', [])) != 2:
        errors.append('cancelled import changed the shelf')
    for name in ('unsupported_error', 'broken_error'):
        if len(shelf.get('A', {}).get(name, [])) != 2:
            errors.append(name + ' changed the shelf after a failed import')
        status_text = state('A', name).get('status', '')
        if '失败' not in status_text and '不支持' not in status_text:
            errors.append(name + ' did not report an explicit error')
    if state('A', 'pdf_note_deleted').get('notes') != '0':
        errors.append('fixed-page annotation deletion was not persisted')
    if state('A', 'note_deleted').get('notes') != '1':
        errors.append('reflow annotation deletion was not persisted')

    identities_unchanged = False
    try:
        unchanged(seal['identities'])
        require(source_identity() == seal['source_sha'], 'source changed during UI execution')
        require(digest(output / 'pre-run-identities.json') == seal['seal_sha256'], 'pre-run identity seal changed')
        identities_unchanged = True
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        errors.append(str(error))
    package_hashes = seal['package_files']
    runtime, source_sha, sdk_version, selftest = seal['runtime'], seal['source_sha'], seal['sdk_version'], seal['selftest']
    def sealed_digest(path):
        return seal['identities'][str(path.resolve())]

    screenshots = {}
    for phase in PHASES:
        screenshots[phase] = shots[phase]
    counts = {'steps': len(steps), 'passed': sum(1 for s in steps if s['result'] == 'PASS'),
              'failed': sum(1 for s in steps if s['result'] != 'PASS')}
    evidence = {
        'schema': 1,
        'platform': 'Windows',
        'source_sha': source_sha,
        'checker_source_sha': seal['checker_source_sha'],
        'checker_sha256': seal['checker_sha256'],
        'acceptance_definition_sha': seal['acceptance_definition_sha'],
        'pre_run_seal': {'path': str(output / 'pre-run-identities.json'),
                        'sha256': seal['seal_sha256']},
        'identities_unchanged': identities_unchanged,
        'parameter_observation_scope': seal['parameter_observation_scope'],
        'raw_evidence': snapshot([p for p in output.rglob('*') if p.is_file() and p.suffix in ('.log', '.script', '.png')]),
        'sdk_version': sdk_version,
        'package': str(package),
        'program_sha256': sealed_digest(exe),
        'sdk_runtime': {'name': runtime, 'sha256': sealed_digest(package / runtime)},
        'font_sha256': sealed_digest(package / 'Reader.otf'),
        'books': {name: {'sha256': sealed_digest(package / name)}
                  for name in ('Sample.epub', 'Sample.pdf', 'Sample-Text.pdf')
                  },
        'fixtures': {Path(path).name: {'sha256': sha} for path, sha in seal['identities'].items()
                     if Path(path).parent == fixtures},
        'library_sha256': digest(data / 'library.sqlite') if (data / 'library.sqlite').exists() else None,
        'runs': runs,
        'counts': counts,
        'selftest': selftest,
        'steps': steps,
        'states': states,
        'shelf': shelf,
        'notes': notes,
        'screenshots': screenshots,
        'host': host,
        'package_hashes': package_hashes,
        'restart': {
            'book_id_match': a_final.get('book_id') == b_restored.get('book_id'),
            'page_match': a_final.get('page') == b_restored.get('page'),
            'title_match': a_final.get('title') == b_restored.get('title'),
            'notes_match': normalized_notes(notes.get('A', {}).get('final', [])) ==
                           normalized_notes(notes.get('B', {}).get('restored', [])),
            'anchor_offset_match': b_before.get('offset') == c_after.get('offset'),
        },
        'zero_tolerance': {
            'cancel_no_shelf_change': len(shelf.get('A', {}).get('cancel_done', [])) == 2,
            'stale_no_shelf_change': len(shelf.get('A', {}).get('stale_done', [])) == 2,
            'stale_view_is_new_book': a_stale.get('book_id') == a_open.get('book_id'),
            'saved_notes_preserved': normalized_notes(notes.get('A', {}).get('final', [])) ==
                                     normalized_notes(notes.get('B', {}).get('restored', [])),
            'no_silent_wrong_restore': b_before.get('offset') == c_after.get('offset'),
        },
        'checks': [],
        'failures': errors,
        'passed': not errors,
    }
    evidence['checks'] = [
        {'name': 'ui_steps_match_fixed_plan', 'passed': len(steps) == 158, 'value': len(steps)},
        {'name': 'no_failed_steps', 'passed': counts['failed'] == 0, 'value': counts['failed']},
        {'name': 'shelf_match', 'passed': shelf_a == shelf_b},
        {'name': 'notes_match', 'passed': evidence['restart']['notes_match']},
        {'name': 'anchor_offset_match', 'passed': evidence['restart']['anchor_offset_match']},
        {'name': 'stale_ownership', 'passed': evidence['zero_tolerance']['stale_view_is_new_book']},
        {'name': 'cancel_no_change', 'passed': evidence['zero_tolerance']['cancel_no_shelf_change']},
        {'name': 'screenshots_match_plan', 'passed': all(set(shots[p]) == EXPECTED_SHOTS[p] for p in PHASES)},
        {'name': 'identities_unchanged', 'passed': identities_unchanged},
    ]
    (output / 'wp13-windows-evidence.json').write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    summary = {'passed': evidence['passed'], 'counts': counts,
               'screenshots': sum(len(shots[p]) for p in PHASES),
               'errors': errors, 'evidence': str(output / 'wp13-windows-evidence.json')}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n',
                                         encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=True))
    return 0 if evidence['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
