# D26 current gate; all original integrity and rejection checks retained.
#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict validator for the GTK AT-SPI audit report, Actions only.

The validator is the acceptance gate: it re-reads the produced evidence, binds
it to one source/run/attempt, requires every declared phase and check, requires
every failed check to carry an element path, a reproduction, an actual, an
expected and a minimal fix, and refuses a report that claims acceptance while a
blocking check failed.  audit_completed and accessibility_accepted are checked
separately, so "the audit ran" can never be read as "accessibility passed".

--self-test mutates a synthetic completed baseline six ways and requires the
validator to reject each mutation, so the gate itself is regression-tested.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import current_expectations as contract

MIN_KEYS = 60
MIN_TREES = 10
MIN_SHOTS = 6
REQUIRED_FIELDS = ('element', 'expected', 'actual', 'minimal_fix', 'reproduction')


class Invalid(Exception):
    pass


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_report(report, root, expect):
    """Return (completed, accepted, problems); raise Invalid on a hard violation."""
    if report.get('schema') != 1:
        raise Invalid('schema must be 1')
    if report.get('kind') != 'gtk-atspi-keyboard-audit':
        raise Invalid('kind must be gtk-atspi-keyboard-audit')
    problems = []

    # -- source and attempt binding ---------------------------------------
    for key, wanted in (('source_sha', expect.get('source_sha')),
                        ('run_id', expect.get('run_id')),
                        ('attempt', expect.get('attempt'))):
        if wanted is not None and str(report.get(key, '')) != str(wanted):
            raise Invalid('%s is %r but this run is %r' % (key, report.get(key), wanted))
    if report.get('start_sha') != contract.START_SHA:
        raise Invalid('start_sha %r is not the fixed implementation start'
                      % (report.get('start_sha'),))
    sdk = report.get('sdk') or {}
    if sdk.get('commit') != contract.SDK_SHA or sdk.get('version') != contract.SDK_VERSION \
            or int(sdk.get('abi', 0)) != contract.SDK_ABI:
        raise Invalid('sdk binding %r is not the frozen SDK contract' % (sdk,))
    if report.get('orca_screen_reader_accepted') is not False:
        raise Invalid('this audit cannot grant Orca or screen-reader acceptance')
    if report.get('human_reader_review_accepted') is not False:
        raise Invalid('this audit cannot grant human review acceptance')

    # -- phases ------------------------------------------------------------
    phases = {entry.get('name'): entry for entry in report.get('phases') or []}
    missing_phases = [name for name in contract.PHASES
                      if name not in phases or not phases[name].get('executed')]
    completed = not missing_phases
    if missing_phases:
        problems.append('phases not executed: %r' % (missing_phases,))
    if bool(report.get('audit_completed')) != completed:
        raise Invalid('audit_completed=%r contradicts the phase record (missing=%r)'
                      % (report.get('audit_completed'), missing_phases))

    # -- checks ------------------------------------------------------------
    by_name = {}
    for entry in report.get('checks') or []:
        name = entry.get('name')
        if not name:
            raise Invalid('a check has no name')
        if name in by_name:
            raise Invalid('duplicate check %r' % name)
        by_name[name] = entry
        for field in ('pass', 'evaluated', 'severity', 'expected', 'actual'):
            if field not in entry:
                raise Invalid('check %r has no %r' % (name, field))
        if entry['severity'] not in ('blocking', 'advisory'):
            raise Invalid('check %r has severity %r' % (name, entry['severity']))
        if not entry['pass']:
            for field in REQUIRED_FIELDS:
                if not entry.get(field):
                    raise Invalid('failed check %r has no %r, so it cannot be reproduced or '
                                  'fixed' % (name, field))
    missing_checks = [name for name, _ in contract.CHECKS if name not in by_name]
    if missing_checks:
        raise Invalid('checks not recorded: %r' % (missing_checks,))
    unevaluated = [name for name, entry in by_name.items() if not entry['evaluated']]
    if unevaluated and report.get('audit_completed'):
        raise Invalid('unevaluated checks %r cannot coexist with audit_completed'
                      % (unevaluated,))
    for name in unevaluated:
        problems.append('check %r was not evaluated' % name)

    blocking = [name for name, entry in by_name.items()
                if not entry['pass'] and entry['severity'] == 'blocking']
    accepted = completed and not blocking
    if bool(report.get('accessibility_accepted')) != accepted:
        raise Invalid('accessibility_accepted=%r contradicts blocking failures %r'
                      % (report.get('accessibility_accepted'), blocking))

    # -- findings and gaps -------------------------------------------------
    findings = report.get('findings') or []
    failed = [entry for entry in by_name.values() if not entry['pass']]
    if len(findings) != len(failed):
        raise Invalid('findings must describe exactly the failed checks (%d findings, %d failed '
                      'checks)' % (len(findings), len(failed)))
    for finding in findings:
        if finding.get('check') not in by_name:
            raise Invalid('finding references an unknown check %r' % (finding.get('check'),))
        for field in REQUIRED_FIELDS:
            if not finding.get(field):
                raise Invalid('finding %r has no %r' % (finding.get('check'), field))
    gaps = report.get('gaps') or []
    if not gaps:
        raise Invalid('the report must list the capabilities this audit cannot decide')
    if not any('screen reader' in entry.lower() for entry in gaps):
        raise Invalid('the gap list must state that screen-reader output is not covered')

    # -- evidence ----------------------------------------------------------
    evidence = report.get('evidence') or {}
    if not evidence:
        raise Invalid('no evidence files were recorded')
    for name, identity in evidence.items():
        path = Path(root) / name
        if not path.is_file():
            raise Invalid('evidence file %r is missing' % name)
        if path.stat().st_size != identity.get('bytes'):
            raise Invalid('evidence file %r size differs from the report' % name)
        if sha256_file(path) != identity.get('sha256'):
            raise Invalid('evidence file %r digest differs from the report' % name)
    trees = [name for name in evidence if name.startswith('tree/') and name.endswith('.json')]
    shots = [name for name in evidence if name.startswith('shots/') and name.endswith('.png')]
    if len(trees) < MIN_TREES:
        raise Invalid('only %d accessibility tree dumps were kept' % len(trees))
    if len(shots) < MIN_SHOTS:
        raise Invalid('only %d screenshots were kept' % len(shots))
    for name in shots:
        with (Path(root) / name).open('rb') as handle:
            if handle.read(8) != b'\x89PNG\r\n\x1a\n':
                raise Invalid('%r is not a PNG file' % name)
    if 'keys.log' not in evidence:
        raise Invalid('keys.log is missing, so no keystroke record exists')
    lines = [line for line in (Path(root) / 'keys.log').read_text(
        encoding='utf-8', errors='replace').splitlines() if line.strip()]
    if len(lines) < MIN_KEYS:
        raise Invalid('keys.log has %d keystrokes, fewer than %d' % (len(lines), MIN_KEYS))
    if 'application.log' not in evidence:
        raise Invalid('the host application log is missing')
    if 'logs/window-tree.txt' not in evidence:
        raise Invalid('the X11 window tree was not captured')
    if int(report.get('secret_leak_hits', -1)) != 0:
        raise Invalid('the secret typed into the password field leaked into evidence')

    observations = report.get('observations') or {}
    if completed and not observations.get('bridge'):
        raise Invalid('no bridge observation was recorded for a completed audit')
    return completed, accepted, problems


def synthetic_baseline(report):
    """A completed, self-consistent copy used only to exercise the gate."""
    clone = copy.deepcopy(report)
    clone['phases'] = [{'name': name, 'executed': True, 'seconds': 0.0}
                       for name in contract.PHASES]
    for entry in clone['checks']:
        entry['evaluated'] = True
        for field in REQUIRED_FIELDS:
            if not entry.get(field):
                entry[field] = 'synthetic' if field != 'reproduction' else ['synthetic']
    clone['audit_completed'] = True
    clone['orca_screen_reader_accepted'] = False
    clone['human_reader_review_accepted'] = False
    blocking = [entry for entry in clone['checks']
                if not entry['pass'] and entry['severity'] == 'blocking']
    if not blocking:
        first = clone['checks'][0]
        first['pass'] = False
        first['severity'] = 'blocking'
        blocking = [first]
    clone['accessibility_accepted'] = False
    clone['findings'] = [{'check': entry['name'], 'severity': entry['severity'],
                          'evaluated': True,
                          'element': entry.get('element') or 'synthetic',
                          'expected': entry['expected'], 'actual': entry['actual'],
                          'reproduction': entry['reproduction'],
                          'minimal_fix': entry.get('minimal_fix') or 'synthetic'}
                         for entry in clone['checks'] if not entry['pass']]
    return clone


def mutate(report, kind):
    """Deterministic negative controls for the validator itself."""
    clone = copy.deepcopy(report)
    first = clone['checks'][0]
    if kind == 'accepted_with_blocking_failure':
        first['pass'] = False
        first['severity'] = 'blocking'
        for field in REQUIRED_FIELDS:
            first[field] = first.get(field) or ('synthetic' if field != 'reproduction'
                                                else ['synthetic'])
        clone['findings'] = [{'check': first['name'], 'severity': 'blocking', 'evaluated': True,
                              'element': first['element'], 'expected': first['expected'],
                              'actual': first['actual'], 'reproduction': first['reproduction'],
                              'minimal_fix': first['minimal_fix']}]
        clone['accessibility_accepted'] = True
    elif kind == 'completed_with_missing_phase':
        clone['phases'] = [entry for entry in clone['phases']
                           if entry['name'] != contract.PHASES[-1]]
        clone['audit_completed'] = True
    elif kind == 'dropped_check':
        clone['checks'] = [entry for entry in clone['checks']
                           if entry['name'] != contract.CHECKS[0][0]]
    elif kind == 'finding_without_fix':
        first['pass'] = False
        first['severity'] = 'blocking'
        for field in ('element', 'expected', 'actual'):
            first[field] = first.get(field) or 'synthetic'
        first['reproduction'] = first.get('reproduction') or ['synthetic']
        first['minimal_fix'] = ''
        clone['findings'] = [{'check': first['name'], 'severity': 'blocking', 'evaluated': True,
                              'element': first['element'], 'expected': first['expected'],
                              'actual': first['actual'], 'reproduction': first['reproduction'],
                              'minimal_fix': ''}]
        clone['accessibility_accepted'] = False
    elif kind == 'evidence_digest_drift':
        name = sorted(clone['evidence'])[0]
        clone['evidence'][name]['sha256'] = '0' * 64
    elif kind == 'accepted_without_orca_disclaimer':
        clone['orca_screen_reader_accepted'] = True
    else:
        raise Invalid('unknown mutation %r' % kind)
    return clone


def self_test(report, root, expect):
    baseline = synthetic_baseline(report)
    completed, accepted, _ = check_report(baseline, root, expect)
    if not completed or accepted:
        raise Invalid('the synthetic baseline must be completed and refused, got %r/%r'
                      % (completed, accepted))
    print(json.dumps({'self_test': 'baseline', 'audit_completed': completed,
                      'accessibility_accepted': accepted}), flush=True)
    kinds = ['accepted_with_blocking_failure', 'completed_with_missing_phase', 'dropped_check',
             'finding_without_fix', 'evidence_digest_drift', 'accepted_without_orca_disclaimer']
    for kind in kinds:
        try:
            check_report(mutate(baseline, kind), root, expect)
        except Invalid as error:
            print(json.dumps({'mutation': kind, 'rejected': True, 'reason': str(error)}),
                  flush=True)
        else:
            raise Invalid('mutation %r was accepted by the validator' % kind)
    print(json.dumps({'self_test': 'passed', 'mutations': len(kinds)}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--evidence-root', type=Path)
    parser.add_argument('--expect-source')
    parser.add_argument('--expect-run')
    parser.add_argument('--expect-attempt')
    parser.add_argument('--require-accepted', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'This validator runs on Actions only'
    root = (args.evidence_root or args.report.parent).resolve()
    expect = {'source_sha': args.expect_source if args.expect_source is not None
              else os.environ.get('GITHUB_SHA'),
              'run_id': args.expect_run if args.expect_run is not None
              else os.environ.get('GITHUB_RUN_ID'),
              'attempt': args.expect_attempt if args.expect_attempt is not None
              else os.environ.get('GITHUB_RUN_ATTEMPT')}
    report = json.loads(args.report.read_text(encoding='utf-8'))
    if args.self_test:
        self_test(report, root, expect)
    completed, accepted, problems = check_report(report, root, expect)
    verdict = {'audit_completed': completed, 'accessibility_accepted': accepted,
               'counts': report.get('counts'), 'source_sha': report.get('source_sha'),
               'run_id': report.get('run_id'), 'attempt': report.get('attempt'),
               'blocking_findings': [entry['name'] for entry in report['checks']
                                     if not entry['pass'] and entry['severity'] == 'blocking'],
               'problems': problems}
    print(json.dumps(verdict, indent=2), flush=True)
    if not completed:
        print('REFUSED: the audit did not complete, so no accessibility claim is possible',
              flush=True)
        return 1
    if args.require_accepted and not accepted:
        print('REFUSED: blocking accessibility findings are recorded; this GTK audit does not '
              'grant accessibility acceptance for this source', flush=True)
        return 2
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Invalid as error:
        print('INVALID REPORT: %s' % error, flush=True)
        sys.exit(1)
