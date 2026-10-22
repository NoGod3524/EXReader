#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Synthetic forged-evidence checks plus real packaged-input preflight, cloud only."""
import argparse
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('windows_evidence', ROOT / 'tools/check_windows_host.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def encode(fields):
    def escape(value):
        return str(value).replace('%', '%25').replace(';', '%3B').replace('\t', '%09')
    return ';'.join(key + '=' + escape(value) for key, value in fields.items())


def synthetic_log(plan, phase, version='3.40.0', pid=123):
    lines = ['HOST\tphase=%d\tengine=%s\tpid=%d' % (c.PHASES.index(phase) + 1, version, pid)]
    for row in plan:
        index, action, args = row['index'], row['action'], row['parameters']
        prefix = lambda kind, name, detail: '%s\t%d\t%s\tPASS\t%s' % (kind, index, name, encode(detail))
        if action == 'state':
            lines.append(prefix('STATE', args[0], {'state': args[0]}))
        if action == 'snapshot':
            lines.append(prefix('SHOT', args[0], {'file': args[0], 'nonzero': '1'}))
        observed = {}
        if action == 'check':
            kind = args[0]
            key = {'shelf': 'count', 'notes': 'count', 'page': 'page', 'font': 'font',
                   'selection': 'active', 'status': 'needle', 'clipboard': 'needle', 'book': 'title'}[kind]
            observed[key] = ('1' if kind == 'selection' else
                             args[2] if kind in ('shelf', 'status', 'clipboard') else args[1])
        lines.append(prefix('STEP', action, observed))
    lines.append('DONE\t%d\teof\tPASS\tscript finished' % len(plan))
    return lines


def main():
    parser = argparse.ArgumentParser()
    for name in ('package', 'sdk', 'manifest', 'fixtures', 'selftest-report', 'consumer-binary', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    c.require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Run evidence checks in GitHub cloud')
    args.output.mkdir(parents=True, exist_ok=False)
    checks = []
    def passed(name):
        checks.append(name)
    def refuses(name, operation):
        try:
            operation()
        except (OSError, ValueError, KeyError, TypeError):
            passed(name)
        else:
            raise AssertionError(name)

    with tempfile.TemporaryDirectory(prefix='windows-evidence-') as folder:
        temp = Path(folder)
        plans = {}
        for phase in c.PHASES:
            text = (ROOT / 'tests/windows_host' / ('phase-' + phase.lower() + '.txt')).read_text(encoding='utf-8')
            plans[phase] = c.script_plan(c.render_script(text, args.package.resolve(), args.fixtures.resolve()), phase)
            log = temp / (phase + '.log')
            log.write_text('\n'.join(synthetic_log(plans[phase], phase)) + '\n', encoding='utf-8')
            parsed = c.parse_log(log, plans[phase], phase, '3.40.0', 123)
            assert len(parsed[0]) == c.EXPECTED_STEPS[phase] and set(parsed[4]) == c.EXPECTED_SHOTS[phase]
            passed('positive_complete_phase_' + phase)
        plan, original = plans['A'], synthetic_log(plans['A'], 'A')
        def forged(name, modify):
            lines = list(original)
            modify(lines)
            path = temp / (name + '.log')
            path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            refuses(name, lambda: c.parse_log(path, plan, 'A', '3.40.0', 123))
        def at(lines, kind):
            return next(i for i, line in enumerate(lines) if line.startswith(kind + '\t'))
        forged('missing_step', lambda lines: lines.pop(at(lines, 'STEP')))
        forged('duplicate_step', lambda lines: lines.insert(at(lines, 'STEP'), lines[at(lines, 'STEP')]))
        forged('unknown_step', lambda lines: lines.__setitem__(at(lines, 'STEP'), 'STEP\t1\tunknown\tPASS\t'))
        forged('reordered_step', lambda lines: lines.__setitem__(at(lines, 'STEP'), 'STEP\t2\tstate\tPASS\t'))
        forged('missing_screenshot', lambda lines: lines.pop(at(lines, 'SHOT')))
        forged('duplicate_screenshot', lambda lines: lines.insert(at(lines, 'SHOT'), lines[at(lines, 'SHOT')]))
        forged('screenshot_path_escape', lambda lines: lines.__setitem__(at(lines, 'SHOT'),
            lines[at(lines, 'SHOT')].replace('file=00-empty-shelf', 'file=../outside')))
        forged('blank_screenshot', lambda lines: lines.__setitem__(at(lines, 'SHOT'), lines[at(lines, 'SHOT')].replace('nonzero=1', 'nonzero=0')))
        forged('missing_state', lambda lines: lines.pop(at(lines, 'STATE')))
        forged('duplicate_state', lambda lines: lines.insert(at(lines, 'STATE'), lines[at(lines, 'STATE')]))
        forged('missing_host', lambda lines: lines.pop(0))
        forged('duplicate_host', lambda lines: lines.insert(1, lines[0]))
        forged('wrong_host_phase', lambda lines: lines.__setitem__(0, lines[0].replace('phase=1', 'phase=2')))
        forged('wrong_runtime_version', lambda lines: lines.__setitem__(0, lines[0].replace('engine=3.40.0', 'engine=3.39.0')))
        forged('wrong_process_identity', lambda lines: lines.__setitem__(0, lines[0].replace('pid=123', 'pid=124')))
        forged('missing_done', lambda lines: lines.pop())
        forged('duplicate_done', lambda lines: lines.append(lines[-1]))
        forged('premature_done', lambda lines: lines.insert(1, lines[-1]))
        forged('contradictory_done', lambda lines: lines.__setitem__(-1, lines[-1].replace('\tPASS\t', '\tFAIL\t')))
        forged('unknown_record', lambda lines: lines.insert(1, 'UNKNOWN\t1\tx\tPASS\t'))
        forged('extra_after_done', lambda lines: lines.append('STEP\t120\tquit\tPASS\t'))
        def change_check(lines):
            index = next(i for i, line in enumerate(lines) if '\tcheck\tPASS\tcount=0' in line)
            lines[index] = lines[index].replace('count=0', 'count=1')
        forged('changed_check_parameter', change_check)
        def duplicate_field(lines):
            index = at(lines, 'STATE')
            lines[index] += ';state=changed'
        forged('duplicate_observed_field', duplicate_field)
        log = temp / 'invalid-utf8.log'
        log.write_bytes(b'\xff')
        refuses('non_utf8_evidence', lambda: c.parse_log(log, plan, 'A', '3.40.0', 123))
        original_script = (ROOT / 'tests/windows_host/phase-a.txt').read_text(encoding='utf-8')
        refuses('shortened_script', lambda: c.script_plan(original_script.replace('next\n', '', 1), 'A'))
        refuses('script_snapshot_escape', lambda: c.script_plan(original_script.replace('00-empty-shelf', '../outside'), 'A'))
        binding = temp / 'sealed.txt'
        binding.write_bytes(b'original identity')
        identity = c.snapshot([binding])
        c.unchanged(identity)
        passed('positive_sealed_identity')
        binding.write_bytes(b'changed identity')
        refuses('post_run_input_mutation', lambda: c.unchanged(identity))
        package = temp / 'small-package'
        package.mkdir()
        (package / 'EXReader.exe').write_bytes(b'program')
        expected = {'EXReader.exe': c.digest(package / 'EXReader.exe')}
        c.verify_file_manifest(package, expected, {'EXReader.exe'})
        passed('positive_complete_file_manifest')
        refuses('empty_file_manifest', lambda: c.verify_file_manifest(package, {}, {'EXReader.exe'}))
        refuses('changed_package_hash', lambda: c.verify_file_manifest(package, {'EXReader.exe': '0' * 64}, {'EXReader.exe'}))
        refuses('manifest_path_escape', lambda: c.safe_file(package, '../sealed.txt'))

        # The same preflight used by real UI execution, with the real cloud-built package.
        original_manifest = json.loads(args.manifest.read_text())
        def seal(manifest, steps=ROOT / 'tests/windows_host', fixtures=args.fixtures):
            target = temp / ('preflight-' + str(len(checks)))
            target.mkdir()
            registration = target / 'build.json'
            registration.write_text(json.dumps(manifest), encoding='utf-8')
            return c.seal_inputs(args.package.resolve(), args.sdk.resolve(), registration,
                args.selftest_report.resolve(), args.consumer_binary.resolve(), steps.resolve(), fixtures.resolve(), target)
        seal(original_manifest)
        passed('positive_real_cloud_package_preflight')
        def bad_manifest(name, modify):
            value = deepcopy(original_manifest)
            modify(value)
            refuses(name, lambda: seal(value))
        bad_manifest('wrong_package_source', lambda value: value.update(source_sha='0' * 40))
        bad_manifest('wrong_package_version', lambda value: value.update(sdk_version='0.0.0'))
        bad_manifest('selftest_reduced_to_20', lambda value: value.update(selftest_checks=20))
        bad_manifest('selftest_report_identity_mismatch', lambda value: value.update(report_sha256='0' * 64))
        bad_manifest('selftest_image_identity_mismatch', lambda value: value.update(image_sha256='0' * 64))
        for name in ('EXReader.exe', 'Reader.otf', 'Sample.epub', 'Sample.pdf', 'Sample-Text.pdf'):
            bad_manifest('mandatory_file_missing_' + name, lambda value, name=name: value['files'].pop(name))
        runtime = next(name for name in ('exreader.dll', 'libexreader.dll') if name in original_manifest['files'])
        bad_manifest('mandatory_runtime_missing', lambda value: value['files'].pop(runtime))
        altered_steps = temp / 'steps'
        shutil.copytree(ROOT / 'tests/windows_host', altered_steps)
        phase_a = altered_steps / 'phase-a.txt'
        phase_a.write_text(phase_a.read_text(encoding='utf-8').replace('resize|1120|820', 'resize|1000|800'), encoding='utf-8')
        refuses('action_parameter_script_identity_changed', lambda: seal(original_manifest, steps=altered_steps))
        altered_fixtures = temp / 'fixtures'
        shutil.copytree(args.fixtures, altered_fixtures)
        (altered_fixtures / 'Pages.pdf').write_bytes(b'changed original')
        refuses('original_fixture_changed', lambda: seal(original_manifest, fixtures=altered_fixtures))
    report = {'schema': 1, 'passed': True, 'checks': checks, 'count': len(checks),
              'source_sha': c.source_identity(), 'native_ui_steps_replaced': 0,
              'scope': 'forged-evidence refusal self-tests; actual UI runs separately'}
    (args.output / 'checks.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'evidence_selftests': len(checks), 'passed': True}))


if __name__ == '__main__':
    main()
