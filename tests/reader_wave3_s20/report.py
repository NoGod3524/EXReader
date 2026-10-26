#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Turn one target's existing driver reports into the S20 operation matrix.

This module never drives a UI and never rewrites a driver verdict: it only
requires the drivers' own reports, binds them to the unpacked delivery bytes and
records which required native operations were actually observed. A failing
driver never hides the evidence that other drivers already produced.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).absolute().parents[2] / 'tools' / 'reader_wave3_package'))
from diagnostics import android_cases

TARGETS = ('windows', 'linux', 'macos', 'android', 'iphone', 'ipad')
REQUIRED = ('import', 'open', 'page', 'settings')
RECOMMENDED = ('search', 'toc')
WINDOWS_SEARCH_REQUIRED = (
    'native-secondary-entry', 'exactly-32-results', 'unicode-query',
    'independently-resolved-jump-moves-progress', 'closed-dialog-is-destroyed',
    'original-bytes-unchanged')
WINDOWS_NAV_REQUIRED = (
    'native-directory-secondary-entry', 'authored-order-and-duplicates',
    'fragment-native-resolution-opens-second-chapter', '32-row-first-page')
LINUX_HOST_REQUIRED = {
    'import': '03 unicode path EPUB import and open',
    'open': '03 unicode path EPUB import and open',
    'page': '05 next page',
    'settings': '08 increase font and repaginate',
}
APPLE_SELFCHECK_REQUIRED = {
    'import': ('library_insert',),
    'open': ('epub_width', 'epub_text'),
    'page': ('next_page', 'previous_page_pixels'),
    'settings': ('font_increase', 'font_decrease'),
}
ANDROID_CASES = {
    'import': ('import_epub',),
    'open': ('open_epub',),
    'page': ('page_next', 'page_prev'),
    'settings': ('font_increase', 'font_decrease'),
}


class Evidence(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Evidence(message)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def load(path):
    path = Path(path)
    require(path.is_file(), 'missing evidence file: ' + str(path))
    return json.loads(path.read_text(encoding='utf-8'))


def name_list(items):
    values = []
    for item in items or []:
        if isinstance(item, str):
            values.append(item)
        elif isinstance(item, dict) and isinstance(item.get('name'), str):
            values.append(item['name'])
    return values


def driver_record(name, kind, path, checks, accepted, extra=None):
    path = Path(path)
    record = {'name': name, 'kind': kind, 'report': str(path), 'sha256': digest(path),
              'checks': len(checks), 'accepted': bool(accepted)}
    if extra:
        record.update(extra)
    return record


def section(problems, label):
    """Run one driver section and keep the failures of the others."""
    class Guard:
        def __enter__(self):
            return self

        def __exit__(self, kind, value, traceback):
            if value is None:
                return False
            if not isinstance(value, (Evidence, OSError, KeyError, TypeError, ValueError)):
                return False
            problems.append(label + ': ' + type(value).__name__ + ': ' + str(value))
            return True

    return Guard()


def optional(problems, label):
    """A driver that only adds a second, non-required operation."""
    class Guard:
        def __enter__(self):
            return self

        def __exit__(self, kind, value, traceback):
            if value is None:
                return False
            if not isinstance(value, (Evidence, OSError, KeyError, TypeError, ValueError)):
                return False
            problems.append(label + ': ' + type(value).__name__ + ': ' + str(value))
            return True

    return Guard()


def windows(evidence, unpack):
    source, entry = unpack['source_sha'], unpack['entry_sha256']
    drivers, operations, problems, optional_failures = [], {}, [], []
    with section(problems, 'windows-search'):
        search_path = evidence / 'windows-search' / 'search-ui.json'
        search = load(search_path)
        require(search.get('accepted') is True, 'search driver did not accept its run')
        require(search.get('consumer_sha256') == entry, 'search driver used different bytes than the delivery entry')
        require(search.get('source_sha') == source, 'search driver ran another source')
        checks = name_list(search.get('checks'))
        require(set(WINDOWS_SEARCH_REQUIRED) <= set(checks), 'search driver named checks are incomplete')
        operations['search'] = ['windows-search: ' + ', '.join(WINDOWS_SEARCH_REQUIRED)]
        drivers.append(driver_record('windows-search', 'win32-native-ui', search_path, checks, True,
                                     {'program_sha256': search.get('consumer_sha256')}))
    with optional(optional_failures, 'windows-navigation'):
        nav_path = evidence / 'windows-navigation' / 'navigation-ui.json'
        nav = load(nav_path)
        require(nav.get('accepted') is True, 'navigation driver did not accept its run')
        require(nav.get('consumer_sha256') == entry, 'navigation driver used different bytes than the delivery entry')
        require(nav.get('source_sha') == source, 'navigation driver ran another source')
        nav_checks = name_list(nav.get('checks'))
        require(set(WINDOWS_NAV_REQUIRED) <= set(nav_checks), 'navigation driver named checks are incomplete')
        operations['toc'] = ['windows-navigation: ' + ', '.join(WINDOWS_NAV_REQUIRED)]
        drivers.append(driver_record('windows-navigation', 'win32-native-ui', nav_path, nav_checks, True,
                                     {'program_sha256': nav.get('consumer_sha256')}))
    with section(problems, 'windows-host'):
        summary_path = evidence / 'windows-host' / 'summary.json'
        summary = load(summary_path)
        require(summary.get('passed') is True, 'host acceptance report did not pass')
        host = load(summary['evidence'])
        steps = host.get('steps') or []
        require(len(steps) == 158, 'host acceptance did not run the fixed 158 actions')
        failed = [step for step in steps if step.get('result') != 'PASS']
        require(not failed, 'host acceptance recorded failed actions')
        actions = {step.get('action') for step in steps}
        for operation, needed in (('import', {'import'}), ('open', {'open'}),
                                  ('page', {'next', 'prev'}), ('settings', {'font_inc'})):
            require(needed <= actions, 'host acceptance never ran ' + ', '.join(sorted(needed)))
            operations[operation] = ['windows-host: ' + ', '.join(sorted(needed)) +
                                     ' action(s) in the 158-action plan']
        require(host.get('program_sha256') == entry, 'host acceptance ran different packaged bytes')
        require(host.get('source_sha') == source, 'host acceptance ran another source')
        drivers.append(driver_record('windows-host', 'win32-native-ui', summary_path,
                                     [step.get('action') for step in steps], True,
                                     {'program_sha256': host.get('program_sha256'), 'steps': len(steps)}))
    return drivers, operations, problems, optional_failures


def linux(evidence, unpack):
    source, entry = unpack['source_sha'], unpack['entry_sha256']
    drivers, operations, problems = [], {}, []
    with section(problems, 'linux-host'):
        host_path = evidence / 'linux-host' / 'report.json'
        host = load(host_path)
        require(host.get('passed') is True, 'GTK host acceptance report did not pass')
        require(host.get('source_sha') == source, 'GTK host acceptance ran another source')
        checks = host.get('checks') or []
        require(len(checks) == 20, 'GTK host acceptance did not run twenty real X11 operations')
        require(all(item.get('pass') is True for item in checks), 'GTK host acceptance recorded a failed operation')
        observed = {item.get('name') for item in checks}
        for operation, name in LINUX_HOST_REQUIRED.items():
            require(name in observed, 'GTK host acceptance lacks: ' + name)
            operations.setdefault(operation, []).append('gtk-host: ' + name)
        require('06 previous page' in observed, 'GTK host acceptance lacks the previous-page operation')
        operations['page'].append('gtk-host: 06 previous page')
        require('09 decrease font and repaginate' in observed, 'GTK host acceptance lacks the font decrease')
        operations['settings'].append('gtk-host: 09 decrease font and repaginate')
        drivers.append(driver_record('gtk-host', 'real-x11-input', host_path,
                                     [item.get('name') for item in checks], True))
    with section(problems, 'linux-search'):
        search_path = evidence / 'linux-search' / 'result.json'
        search = load(search_path)
        require(search.get('search_scope_passed') is True, 'GTK search driver did not accept its run')
        require(search.get('source_sha') == source, 'GTK search driver ran another source')
        require(search.get('program_sha256') == entry, 'GTK search driver used different bytes than the delivery entry')
        search_names = [item.get('name') for item in search.get('checks') or []]
        require(search_names and all(item.get('pass') is True for item in search.get('checks') or []),
                'GTK search driver recorded a failed check')
        require('250_actual_result_rows_continue_in_32_row_pages' in search_names,
                'GTK search driver lacks the real result-row operation')
        operations['search'] = ['gtk-search: 250_actual_result_rows_continue_in_32_row_pages and ' +
                                str(len(search_names)) + ' named checks']
        drivers.append(driver_record('gtk-search', 'real-atspi-ui', search_path, search_names, True,
                                     {'program_sha256': search.get('program_sha256')}))
    return drivers, operations, problems, []


def apple(evidence, unpack, target):
    source = unpack['source_sha']
    drivers, operations, problems = [], {}, []
    with section(problems, target + '-selfcheck'):
        check_path = evidence / (target + '-selfcheck') / 'report.json'
        check = load(check_path)
        require(check.get('passed') is True, 'packaged app self-check did not pass')
        require(int(check.get('check_count') or 0) >= 20, 'packaged app self-check is incomplete')
        require(check.get('source_sha') == source, 'packaged app carries another source SHA')
        observed = set(check.get('checks') or [])
        for operation, needed in APPLE_SELFCHECK_REQUIRED.items():
            require(set(needed) <= observed, 'packaged app self-check lacks ' + ', '.join(needed))
            operations[operation] = ['apple-selfcheck: ' + ', '.join(needed)]
        drivers.append(driver_record(target + '-selfcheck', 'packaged-app-selfcheck', check_path,
                                     sorted(observed), True, {'source_sha': check.get('source_sha')}))
    with section(problems, target + '-xctest-broad'):
        broad_path = evidence / (target + '-xctest-broad') / 'status.json'
        broad = load(broad_path)
        require(broad.get('exit') == 0, 'broad XCUITest suite failed: ' + json.dumps(
            {'failed_cases': broad.get('failed_cases'), 'first_assertion': broad.get('first_assertion')}, ensure_ascii=True))
        require(broad.get('succeeded_marker') is True and not broad.get('failed_marker'),
                'broad XCUITest lacks an unambiguous success marker')
        require(int(broad.get('failed') or 0) == 0 and int(broad.get('passed') or 0) > 0,
                'broad XCUITest suite reported no passing test')
        broad_tests = [item.get('name') for item in broad.get('tests') or [] if item.get('result') == 'Passed']
        require(any('Import' in name or 'import' in name for name in broad_tests),
                'broad XCUITest suite lacks the import case')
        require(any('Paging' in name or 'paging' in name for name in broad_tests),
                'broad XCUITest suite lacks the paging/typography case')
        operations.setdefault('import', []).append('apple-xctest: import case')
        operations.setdefault('open', []).append('apple-xctest: import case')
        operations.setdefault('page', []).append('apple-xctest: paging case')
        operations.setdefault('settings', []).append('apple-xctest: typography case')
        drivers.append(driver_record(target + '-xctest-broad', 'xcuitest-ui', broad_path, broad_tests, True,
                                     {'passed': broad.get('passed'), 'failed': broad.get('failed')}))
    with section(problems, target + '-xctest-search'):
        search_path = evidence / (target + '-xctest-search') / 'status.json'
        search = load(search_path)
        require(search.get('exit') == 0, 'search XCUITest suite failed')
        require(search.get('succeeded_marker') is True and not search.get('failed_marker'),
                'search XCUITest lacks an unambiguous success marker')
        require(int(search.get('failed') or 0) == 0 and int(search.get('passed') or 0) > 0,
                'search XCUITest suite reported no passing test')
        search_tests = [item.get('name') for item in search.get('tests') or [] if item.get('result') == 'Passed']
        require(any('Search' in name or 'search' in name for name in search_tests),
                'search XCUITest suite lacks a search case')
        operations['search'] = ['apple-xctest: ' + ', '.join(sorted(search_tests)[:3])]
        drivers.append(driver_record(target + '-xctest-search', 'xcuitest-ui', search_path, search_tests, True,
                                     {'passed': search.get('passed'), 'failed': search.get('failed')}))
    return drivers, operations, problems, []


def android(evidence, unpack):
    source = unpack['source_sha']
    drivers, operations, problems = [], {}, []
    with section(problems, 'android-walkthrough'):
        execution_path = evidence / 'execution.json'
        execution = load(execution_path)
        require(execution.get('completed') is True, 'device execution did not complete every suite')
        require(execution.get('source_sha') == source, 'device execution ran another source')
        validation_path = evidence / 'device' / 'validation.json'
        validation = load(validation_path)
        named = android_cases(validation)
        require(named['accepted'], 'walkthrough named verdicts failed: ' + json.dumps(named, ensure_ascii=True))
        summary = validation.get('summary') or {}
        require(int(summary.get('failed') or 0) == 0 and int(summary.get('skipped') or 0) == 0,
                'walkthrough reported a failed or skipped case')
        require(int(summary.get('passed') or 0) == int(summary.get('total') or -1),
                'walkthrough summary is inconsistent')
        require(validation.get('apk_sha256') == unpack['digests'].get('artifacts/app-debug.apk'),
                'walkthrough ran a different application package than the delivery')
        cases = {item.get('id'): item.get('status') for item in validation.get('cases') or []}
        for operation, needed in ANDROID_CASES.items():
            require(all(cases.get(name) == 'pass' for name in needed),
                    'walkthrough lacks passing case(s): ' + ', '.join(needed))
            operations[operation] = ['android-walkthrough: ' + ', '.join(needed)]
        drivers.append(driver_record('android-walkthrough', 'instrumented-real-ui', execution_path,
                                     sorted(cases), True, {'apk_sha256': validation.get('apk_sha256')}))
    return drivers, operations, problems, []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True, choices=TARGETS)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--unpack', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    problems, optional_failures = [], []
    drivers, operations = [], {}
    unpack = {}
    try:
        unpack = json.loads(args.unpack.read_text(encoding='utf-8'))
        require(isinstance(unpack, dict) and unpack.get('entry'), 'unpack report is missing or incomplete')
    except (OSError, ValueError, Evidence) as error:
        unpack = {}
        problems.append('unpack: ' + type(error).__name__ + ': ' + str(error))
    try:
        require(unpack, 'no unpack report')
        require(unpack.get('target') == args.target, 'unpack report belongs to another target')
        if args.target == 'windows':
            drivers, operations, problems, optional_failures = windows(args.evidence.resolve(), unpack)
        elif args.target == 'linux':
            drivers, operations, problems, optional_failures = linux(args.evidence.resolve(), unpack)
        elif args.target == 'android':
            drivers, operations, problems, optional_failures = android(args.evidence.resolve(), unpack)
        else:
            drivers, operations, problems, optional_failures = apple(args.evidence.resolve(), unpack, args.target)
    except (Evidence, OSError, KeyError, TypeError, ValueError) as error:
        problems.append(type(error).__name__ + ': ' + str(error))
    missing = [name for name in REQUIRED if name not in operations]
    if not any(name in operations for name in RECOMMENDED):
        missing.append('search_or_toc')
    accepted = not problems and not missing
    report = {
        'schema': 1,
        'kind': 'exreader-native-launch-matrix',
        'target': args.target,
        'source_sha': unpack.get('source_sha'),
        'sdk_version': unpack.get('sdk_version'),
        'entry': unpack.get('entry'),
        'entry_sha256': unpack.get('entry_sha256'),
        'package': {'archive': unpack.get('archive'), 'files': unpack.get('files'),
                    'checksums_checked': unpack.get('checksums_checked')},
        'drivers': drivers,
        'operations': operations,
        'missing': missing,
        'problems': problems,
        'optional_failures': optional_failures,
        'required': list(REQUIRED) + ['search_or_toc'],
        'accepted': accepted,
        'run_id': os.environ.get('GITHUB_RUN_ID', ''),
        'attempt': os.environ.get('GITHUB_RUN_ATTEMPT', ''),
        'physical_device_execution': False,
        'scope': 'native delivery archive + existing platform UI drivers; no tag, Release or store publication',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'target': args.target, 'accepted': accepted, 'missing': missing,
                      'problems': problems, 'optional_failures': optional_failures,
                      'operations': sorted(operations),
                      'drivers': [item['name'] for item in drivers]}, ensure_ascii=True))
    return 0 if accepted else 1


if __name__ == '__main__':
    raise SystemExit(main())
