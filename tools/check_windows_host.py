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


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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
            result[unescape(key)] = unescape(value)
    return result


def parse_log(path):
    steps, states, shelf, notes, shots = [], {}, {}, {}, {}
    done, host = [], []
    if not path.exists():
        return steps, states, shelf, notes, shots, done, host
    for raw in path.read_text(encoding='utf-8', errors='replace').splitlines():
        parts = raw.split('\t')
        if len(parts) < 3:
            continue
        kind = parts[0]
        try:
            index = int(parts[1])
        except ValueError:
            index = -1
        action = parts[2] if len(parts) > 2 else ''
        result = parts[3] if len(parts) > 3 else ''
        detail = fields(parts[4] if len(parts) > 4 else '')
        if kind == 'STEP':
            steps.append({'index': index, 'action': action, 'result': result, 'observed': detail})
        elif kind == 'STATE':
            states[action] = detail
        elif kind == 'SHELF':
            shelf.setdefault(action, []).append(detail)
        elif kind == 'NOTE':
            notes.setdefault(action, []).append(detail)
        elif kind == 'SHOT':
            shots[action] = detail
        elif kind == 'DONE':
            done.append({'action': action, 'result': result, 'detail': detail})
        elif kind == 'HOST':
            host.append(detail)
    return steps, states, shelf, notes, shots, done, host


def render_script(template, package, fixtures):
    return (template.replace('@@SAMPLE@@', str(package))
                    .replace('@@FIXTURES@@', str(fixtures)))


def run_phase(exe, steps_dir, output, phase, data, package, fixtures, timeout):
    template = (steps_dir / ('phase-' + phase.lower() + '.txt')).read_text(encoding='utf-8')
    script = output / ('phase-' + phase + '.script')
    script.write_text(render_script(template, package, fixtures), encoding='utf-8')
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
        completed = subprocess.run(command, cwd=str(package), env=env, timeout=timeout,
                                   capture_output=True, text=True, encoding='utf-8',
                                   errors='replace', creationflags=creationflags)
    except subprocess.TimeoutExpired as expired:
        (output / ('phase-' + phase + '.stdout.log')).write_text(
            'timeout after %.1fs\nstdout=%r\nstderr=%r' % (timeout, expired.stdout, expired.stderr),
            encoding='utf-8')
        return 124, timeout
    elapsed = time.time() - started
    (output / ('phase-' + phase + '.stdout.log')).write_text(
        (completed.stdout or '') + '\n--- stderr ---\n' + (completed.stderr or ''), encoding='utf-8')
    return completed.returncode, elapsed


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
    parser.add_argument('--selftest-report', type=Path)
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

    runs = {}
    for phase in PHASES:
        code, elapsed = run_phase(exe, args.steps.resolve(), output, phase, data, package,
                                  fixtures, args.timeout)
        runs[phase] = {'exit_code': code, 'elapsed_seconds': round(elapsed, 3)}
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
        parsed[phase] = parse_log(output / phase / 'drive.log')
        if not (output / phase / 'drive.log').exists():
            errors.append('phase ' + phase + ' produced no drive.log')

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
            if not image.exists() or image.stat().st_size == 0:
                errors.append('phase ' + phase + ' screenshot ' + name + ' is missing or empty')
            else:
                shot['bytes'] = image.stat().st_size
                shot['sha256'] = digest(image)
                shot['path'] = str(image)

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

    if len(steps) < 20:
        errors.append('only ' + str(len(steps)) + ' UI steps were recorded; at least 20 are required')
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

    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    package_hashes = {}
    for relative, expected in manifest.get('files', {}).items():
        path = package / relative
        if not path.exists():
            errors.append('packaged file missing: ' + relative)
            continue
        actual = digest(path)
        package_hashes[relative] = actual
        if actual != expected:
            errors.append('packaged hash mismatch: ' + relative)
    runtime = next((name for name in ('exreader.dll', 'libexreader.dll')
                    if (package / name).exists()), None)
    if not runtime:
        errors.append('packaged SDK runtime is missing')
    source_sha = os.environ.get('GITHUB_SHA', '')
    try:
        source_sha = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                                             text=True).strip()
    except Exception:
        pass
    base_header = (sdk / 'include' / 'exr' / 'base.h').read_text(encoding='utf-8')
    version = re.search(r'#define EXR_VERSION "([^"]+)"', base_header)
    sdk_version = version[1] if version else ''
    selftest = {}
    if args.selftest_report:
        report = json.loads(args.selftest_report.read_text(encoding='utf-8'))
        selftest = {'passed': report.get('passed'), 'checks': report.get('checks'),
                    'engine_version': report.get('engine_version'),
                    'sha256': digest(args.selftest_report)}
        if report.get('passed') is not True or int(report.get('checks', 0)) < 20:
            errors.append('the preserved native self-check did not pass')
        if report.get('engine_version') != sdk_version:
            errors.append('self-check engine version differs from the installed SDK')

    screenshots = {}
    for phase in PHASES:
        screenshots[phase] = shots[phase]
    counts = {'steps': len(steps), 'passed': sum(1 for s in steps if s['result'] == 'PASS'),
              'failed': sum(1 for s in steps if s['result'] != 'PASS')}
    evidence = {
        'schema': 1,
        'platform': 'Windows',
        'source_sha': source_sha,
        'sdk_version': sdk_version,
        'package': str(package),
        'program_sha256': digest(exe),
        'sdk_runtime': {'name': runtime, 'sha256': digest(package / runtime)} if runtime else None,
        'font_sha256': digest(package / 'Reader.otf') if (package / 'Reader.otf').exists() else None,
        'books': {name: {'sha256': digest(package / name), 'bytes': (package / name).stat().st_size}
                  for name in ('Sample.epub', 'Sample.pdf', 'Sample-Text.pdf')
                  if (package / name).exists()},
        'fixtures': {path.name: {'sha256': digest(path), 'bytes': path.stat().st_size}
                     for path in sorted(fixtures.iterdir()) if path.is_file()},
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
        {'name': 'ui_steps_at_least_20', 'passed': len(steps) >= 20, 'value': len(steps)},
        {'name': 'no_failed_steps', 'passed': counts['failed'] == 0, 'value': counts['failed']},
        {'name': 'shelf_match', 'passed': shelf_a == shelf_b},
        {'name': 'notes_match', 'passed': evidence['restart']['notes_match']},
        {'name': 'anchor_offset_match', 'passed': evidence['restart']['anchor_offset_match']},
        {'name': 'stale_ownership', 'passed': evidence['zero_tolerance']['stale_view_is_new_book']},
        {'name': 'cancel_no_change', 'passed': evidence['zero_tolerance']['cancel_no_shelf_change']},
        {'name': 'screenshots_present', 'passed': all(
            (output / phase / (shot.get('file', name) + '.png')).exists()
            for phase in PHASES for name, shot in shots[phase].items())},
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
