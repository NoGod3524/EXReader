#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run the installed keyboard-actions consumers and the platform probe.

Every expectation below was fixed before any binary was executed. The script
refuses a suite whose named case set differs from the fixed set, refuses a FAIL,
and only tolerates the SKIPs that are documented as uncovered. Suite results are
collected first so one refusal never hides the per-case table; the install-proof
checks then decide acceptance together with the case outcomes. It writes
keyboard-evidence/result.json for the artifact verifier."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

COMMON_START = 'f43baf9182d75907c0cb5d6f77048f27bca8c950'
PACKAGE = 'EXReaderKeyboardActions 0.1.0'

# Fixed before the first run: installed C consumer cases.
CASE_C = (
    'abi-and-names', 'config-from-preferences', 'struct-validation', 'page-direction-matrix',
    'page-input-gating', 'command-matrix', 'modifier-conflicts', 'context-gating',
    'keyup-pairing', 'repeat-policy', 'held-table-limit', 'cancel', 'handler-commit-boundary',
    'reentry-refused', 'set-config-atomic', 'win32-translator', 'x11-translator',
    'apple-translator', 'android-translator', 'translator-to-actions',
)
# Installed C++ consumer cases: ownership, dispatch, exception and thread rules.
CASE_CPP = (
    'create-move-ownership', 'dispatch-and-keyup', 'decline-rollback', 'throw-declines',
    'wrong-thread-refused', 'empty-object-argument', 'config-and-cancel',
)
# Native probe cases: identical names on all three desktop platforms.
CASE_PROBE = (
    'probe-window-ready', 'reader-page-next-consumed', 'reader-page-previous-consumed',
    'reader-command-search', 'reader-shift-space-previous', 'reader-modifier-conflict-passes',
    'reader-key-up-swallowed', 'reader-repeat-bounded', 'edit-keeps-editing-keys',
    'edit-command-passes', 'modal-keeps-keys', 'focus-change-forgets-hold', 'deactivate-cancels',
    'ime-composing-passthrough',
)
# The only cases allowed to skip, with the reason they are recorded as uncovered.
DOCUMENTED_SKIPS = {
    'ime-composing-passthrough': 'no input method is installed on a hosted runner',
    'reader-repeat-bounded': 'the runner did not auto-repeat the injected key',
    'deactivate-cancels': 'the runner had no window that could take activation',
}
CASE_LINE = re.compile(r'^(CHECK|PROBE) (\S+) (PASS|FAIL|SKIP)(?: (.*))?$')
INCLUDE_LINE = re.compile(r'EXReaderKeyboardActions_DIR:PATH=(.*)')


def parse(text, prefix, expected):
    cases = {}
    for line in text.splitlines():
        match = CASE_LINE.match(line.strip())
        if match is None or match.group(1) != prefix:
            continue
        name = match.group(2)
        if name in cases:
            raise ValueError('duplicate case ' + name)
        cases[name] = (match.group(3), (match.group(4) or '').strip())
    if set(cases) != set(expected):
        raise ValueError('%s case set differs: missing=%s extra=%s' %
                         (prefix, sorted(set(expected) - set(cases)),
                          sorted(set(cases) - set(expected))))
    return cases


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def collect(binary, log, prefix, expected):
    if not Path(binary).is_file():
        raise ValueError('missing binary ' + str(binary))
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('w', encoding='utf-8') as stream:
        stream.write('$ %s\n' % binary)
        stream.flush()
        process = subprocess.Popen([str(binary)], stdout=stream, stderr=subprocess.STDOUT)
        try:
            code = process.wait(timeout=300)
        except subprocess.TimeoutExpired:
            process.kill()
            code = process.wait()
            stream.write('[stopped after the 300 second budget]\n')
    cases = parse(log.read_text(encoding='utf-8', errors='replace'), prefix, expected)
    return cases, code


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--c', required=True)
    parser.add_argument('--cpp', required=True)
    parser.add_argument('--probe', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--platform', required=True, choices=['Linux', 'Windows', 'macOS'])
    parser.add_argument('--stage', required=True, help='installed prefix')
    parser.add_argument('--build-log', required=True)
    parser.add_argument('--cache', required=True, help='consumer CMakeCache.txt')
    arguments = parser.parse_args()

    out = Path(arguments.output)
    out.mkdir(parents=True, exist_ok=True)
    stage = Path(arguments.stage)
    report = {
        'accepted': False,
        'package': PACKAGE,
        'common_start': COMMON_START,
        'source_sha': os.environ.get('GITHUB_SHA', ''),
        'run_id': int(os.environ.get('GITHUB_RUN_ID', '0')),
        'attempt': int(os.environ.get('GITHUB_RUN_ATTEMPT', '0')),
        'platform': arguments.platform,
        'granted_platform': arguments.platform.lower(),
        'installed_prefix': str(stage),
        'checks': 0,
        'cases': [],
        'skipped': [],
        'uncovered': [],
        'problems': [],
        'install_proof': {},
        'macos_accepted': False,
        'host_ui_accepted': False,
        'performance_claimed': False,
        'sdk_changed': False,
        'schema_changed': False,
        'binaries': {},
    }
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        report['problems'].append('cloud only')

    # 1. Collect the three suites first, so a refusal never hides the case table.
    suites = (('consumer-c', arguments.c, out / 'c-consumer.log', 'CHECK', CASE_C),
              ('consumer-cpp', arguments.cpp, out / 'cpp-consumer.log', 'CHECK', CASE_CPP),
              ('probe', arguments.probe, out / 'probe.log', 'PROBE', CASE_PROBE))
    collected = []
    for suite, binary, log, prefix, expected in suites:
        try:
            cases, code = collect(binary, log, prefix, expected)
            collected.append((suite, cases, code))
        except Exception as error:  # noqa: BLE001 - a refusal is evidence
            report['problems'].append('%s: %s' % (suite, error))

    # 2. Turn the collected cases into fixed named results.
    for suite, cases, code in collected:
        for name in sorted(cases):
            status, detail = cases[name]
            if status == 'FAIL':
                report['problems'].append('%s.%s failed: %s' % (suite, name, detail))
            if status == 'SKIP':
                if suite != 'probe':
                    report['problems'].append('%s.%s may not skip' % (suite, name))
                elif name not in DOCUMENTED_SKIPS:
                    report['problems'].append('undocumented skip ' + name)
                else:
                    report['skipped'].append({'suite': suite, 'name': name, 'detail': detail})
                    report['uncovered'].append({'case': name,
                                                'reason': DOCUMENTED_SKIPS[name]})
            report['cases'].append({'suite': suite, 'name': name, 'status': status,
                                    'detail': detail})
        if code != 0 and not any(c['suite'] == suite and c['status'] == 'FAIL'
                                 for c in report['cases']):
            report['problems'].append('%s exited %d without a named failure' % (suite, code))
    report['checks'] = len(report['cases'])
    if len(collected) == 3 and report['checks'] != len(CASE_C) + len(CASE_CPP) + len(CASE_PROBE):
        report['problems'].append('the executed case count differs from the fixed expectation')

    # 3. Prove the consumers were compiled from the installed prefix only.
    try:
        build_log = Path(arguments.build_log).read_text(encoding='utf-8', errors='replace')
        cache = Path(arguments.cache).read_text(encoding='utf-8', errors='replace')
        package_dir = None
        for line in cache.splitlines():
            match = INCLUDE_LINE.match(line.strip())
            if match is not None:
                package_dir = match.group(1).strip()
        report['install_proof'] = {
            'package_dir': package_dir,
            'build_log_mentions_prefix': stage.name in build_log.replace('\\', '/'),
            'source_include_absent': 'apps/reader/keyboard-actions/include' not in \
                build_log.replace('\\', '/'),
        }
        if package_dir is None:
            report['problems'].append('CMakeCache records no EXReaderKeyboardActions_DIR')
        elif 'EXReaderKeyboardActions' not in package_dir.replace('\\', '/'):
            report['problems'].append('EXReaderKeyboardActions_DIR is not the installed package')
        if not report['install_proof']['build_log_mentions_prefix']:
            report['problems'].append('the consumer build log never mentions the install prefix')
        if not report['install_proof']['source_include_absent']:
            report['problems'].append('the consumers compiled against the source tree')
        for name in ('include/reader_keyboard_actions.h', 'include/reader_keyboard_actions.hpp',
                     'lib/cmake/EXReaderKeyboardActions/EXReaderKeyboardActionsConfig.cmake'):
            if not (stage / name).is_file():
                report['problems'].append('installed package is incomplete: ' + name)
    except Exception as error:  # noqa: BLE001 - a refusal is evidence
        report['problems'].append('install proof: %s' % error)

    for label, path in (('c', arguments.c), ('cpp', arguments.cpp), ('probe', arguments.probe)):
        if Path(path).is_file():
            report['binaries'][label] = {'path': str(path), 'sha256': digest(path),
                                         'bytes': Path(path).stat().st_size}
    report['macos_accepted'] = arguments.platform == 'macOS'
    report['accepted'] = not report['problems']
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    lines = ['# keyboard-actions ' + arguments.platform, '',
             '- source: %s run %s attempt %s' % (report['source_sha'], report['run_id'],
                                                report['attempt']),
             '- accepted: %s' % report['accepted'],
             '- checks: %d' % report['checks'],
             '- skipped: %d' % len(report['skipped']),
             '- problems: %s' % ('; '.join(report['problems']) if report['problems'] else 'none'),
             '']
    for case in report['cases']:
        lines.append('| %s | %s | %s | %s |' % (case['suite'], case['name'], case['status'],
                                                case['detail'].replace('|', '/')))
    (out / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)
    raise SystemExit(0 if report['accepted'] else 1)


if __name__ == '__main__':
    main()
