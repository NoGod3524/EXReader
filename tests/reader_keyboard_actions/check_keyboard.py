#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run the installed keyboard-actions consumers and the platform probe.

Every expectation below was fixed before any binary was executed. The script
refuses a suite whose named case set differs from the fixed set, refuses a FAIL,
and only tolerates the SKIPs that are documented as uncovered. It writes
keyboard-evidence/result.json for the artifact verifier."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

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
    'deactivate-cancels': 'the runner had no second window that could take activation',
}
CASE_LINE = re.compile(r'^(CHECK|PROBE) (\S+) (PASS|FAIL|SKIP)(?: (.*))?$')


def require(value, message):
    if not value:
        raise ValueError(message)


def run(binary, log):
    require(Path(binary).is_file(), 'missing binary ' + str(binary))
    completed = subprocess.run([str(binary)], capture_output=True, text=True, timeout=900)
    text = completed.stdout
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text('$ %s\n%s\n[stderr]\n%s\n[exit %d]\n' % (binary, text, completed.stderr,
                                                           completed.returncode),
                   encoding='utf-8')
    return completed.returncode, text, completed.stderr


def parse(text, prefix, expected):
    cases = {}
    for line in text.splitlines():
        match = CASE_LINE.match(line.strip())
        if match is None or match.group(1) != prefix:
            continue
        name = match.group(2)
        require(name not in cases, 'duplicate case ' + name)
        cases[name] = (match.group(3), (match.group(4) or '').strip())
    require(set(cases) == set(expected),
            '%s case set differs: missing=%s extra=%s' % (prefix,
                                                          sorted(set(expected) - set(cases)),
                                                          sorted(set(cases) - set(expected))))
    return cases


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--c', required=True)
    parser.add_argument('--cpp', required=True)
    parser.add_argument('--probe', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--platform', required=True, choices=['Linux', 'Windows', 'macOS'])
    parser.add_argument('--stage', required=True, help='installed prefix')
    parser.add_argument('--build-log', required=True)
    parser.add_argument('--configure-log', required=True)
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
        'macos_accepted': False,
        'host_ui_accepted': False,
        'performance_claimed': False,
        'sdk_changed': False,
        'schema_changed': False,
        'binaries': {},
    }
    try:
        require(os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud only')
        require(Path(arguments.build_log).is_file(), 'missing consumer build log')
        require(Path(arguments.configure_log).is_file(), 'missing consumer configure log')
        build_log = Path(arguments.build_log).read_text(encoding='utf-8', errors='replace')
        configure_log = Path(arguments.configure_log).read_text(encoding='utf-8', errors='replace')
        require('apps/reader/keyboard-actions/include' not in build_log,
                'the consumers compiled against the source tree, not the install prefix')
        require(stage.name in build_log.replace('\\', '/'),
                'the consumer build log never mentions the install prefix')
        require('EXReaderKeyboardActions' in configure_log,
                'the consumer configure log did not resolve the installed package')
        for name in ('include/reader_keyboard_actions.h', 'include/reader_keyboard_actions.hpp',
                     'lib/cmake/EXReaderKeyboardActions/EXReaderKeyboardActionsConfig.cmake'):
            require((stage / name).is_file(), 'installed package is incomplete: ' + name)

        code_c, text_c, _ = run(arguments.c, out / 'c-consumer.log')
        require(code_c == 0, 'the installed C consumer failed')
        require('c-consumer ok' in text_c, 'the installed C consumer printed no verdict')
        cases_c = parse(text_c, 'CHECK', CASE_C)

        code_cpp, text_cpp, _ = run(arguments.cpp, out / 'cpp-consumer.log')
        require(code_cpp == 0, 'the installed C++ consumer failed')
        require('cpp-consumer ok' in text_cpp, 'the installed C++ consumer printed no verdict')
        cases_cpp = parse(text_cpp, 'CHECK', CASE_CPP)

        code_probe, text_probe, _ = run(arguments.probe, out / 'probe.log')
        require('probe ' in text_probe, 'the native probe printed no verdict')
        cases_probe = parse(text_probe, 'PROBE', CASE_PROBE)
        require(code_probe == 0, 'the native probe reported a failure')

        for suite, cases in (('consumer-c', cases_c), ('consumer-cpp', cases_cpp),
                             ('probe', cases_probe)):
            for name in sorted(cases):
                status, detail = cases[name]
                require(status != 'FAIL', '%s.%s failed: %s' % (suite, name, detail))
                if status == 'SKIP':
                    require(suite == 'probe', '%s.%s may not skip' % (suite, name))
                    require(name in DOCUMENTED_SKIPS, 'undocumented skip ' + name)
                    report['skipped'].append({'suite': suite, 'name': name, 'detail': detail})
                    report['uncovered'].append({'case': name,
                                                'reason': DOCUMENTED_SKIPS[name]})
                report['cases'].append({'suite': suite, 'name': name, 'status': status,
                                        'detail': detail})
        report['checks'] = len(report['cases'])
        require(report['checks'] == len(CASE_C) + len(CASE_CPP) + len(CASE_PROBE),
                'the executed case count differs from the fixed expectation')
        report['macos_accepted'] = arguments.platform == 'macOS'
        for label, path in (('c', arguments.c), ('cpp', arguments.cpp),
                            ('probe', arguments.probe)):
            report['binaries'][label] = {'path': str(path), 'sha256': digest(path),
                                         'bytes': Path(path).stat().st_size}
        report['accepted'] = True
    except Exception as error:  # noqa: BLE001 - a refusal is evidence
        report['problems'].append(str(error))

    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    lines = ['# keyboard-actions ' + arguments.platform,
             '',
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
