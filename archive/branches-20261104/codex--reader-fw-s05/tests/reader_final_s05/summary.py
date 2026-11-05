#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Collect the S05 evidence and refuse to call a fixture or a failed producer a pass.

The summary keeps three results apart by construction:

* tool capability: the CI generated fixture is accepted and every mutant is
  rejected with its named check,
* simulator capability: the fixture installs, launches and is identified on a
  clean iPhone and on a clean iPad,
* producer acceptance: only a successful, digest authenticated producer run can
  grant it, separately for iPhone and iPad.

A missing or failed producer leaves the producer result pending; it never
inherits the fixture result.
"""
import argparse
import json
from pathlib import Path
import sys

CLASSES = ('iphone', 'ipad')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    return json.loads(Path(path).read_text())


def collect(root):
    root = Path(root)
    found = {'fixture_checks': [], 'results': [], 'producer_source': []}
    for path in sorted(root.rglob('fixture-checks.json')):
        found['fixture_checks'].append(load(path))
    for path in sorted(root.rglob('result.json')):
        value = load(path)
        if isinstance(value, dict) and value.get('kind') == 'reader-final-s05-simulator-distribution':
            found['results'].append(value)
    for path in sorted(root.rglob('producer-source.json')):
        found['producer_source'].append(load(path))
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--branch', default=None)
    args = parser.parse_args()
    output = args.output.absolute()
    require(not output.exists(), 'choose a new summary directory: ' + str(output))
    found = collect(args.evidence)
    problems = []
    checks = [item for item in found['fixture_checks']
              if (item.get('implementation') or {}).get('sha') == args.sha]
    if not checks:
        problems.append('no fixture self-check evidence was produced by this implementation commit')
        harness = {'passed': False, 'valid': {'accepted': False, 'failing': []}, 'mutants': [],
                   'fixture_cannot_be_producer': False, 'runtime_version': None,
                   'fixture': {'executable_sha256': None}}
    else:
        harness = checks[0]
    if not harness['passed']:
        problems.append('fixture harness did not prove the verifier')
    if harness['valid']['failing']:
        problems.append('untouched fixture was rejected: %s' % ','.join(harness['valid']['failing']))
    rejected = [item['mutant'] for item in harness['mutants'] if item['rejected']]
    accepted = [item['mutant'] for item in harness['mutants'] if not item['rejected']]
    if accepted:
        problems.append('mutants were accepted: %s' % ','.join(accepted))
    if not harness['fixture_cannot_be_producer']:
        problems.append('a fixture was accepted as a producer source')

    results = [value for value in found['results']
               if (value.get('sources') or {}).get('implementation', {}).get('sha') == args.sha]
    if not results:
        problems.append('no verifier result was produced by this implementation commit')
    fixtures = {}
    for value in results:
        if value['mode'] == 'fixture':
            fixtures.setdefault(value['device_class'], []).append(value)
    producers = {value['device_class']: value for value in results
                 if value['mode'] in ('producer', 'diagnostic')}
    simulator = {}
    for device_class in CLASSES:
        values = fixtures.get(device_class) or []
        if not values:
            problems.append('no fixture simulator result for ' + device_class)
            simulator[device_class] = {'manifest_complete': None, 'install_smoke': None,
                                       'device': None, 'bundle': None}
            continue
        if any(item['granted'] for item in values):
            problems.append('a fixture result claimed producer acceptance on ' + device_class)
        smoke_values = [item for item in values if item['install_smoke']['requested']]
        chosen = next((item for item in smoke_values if item['capability_verified']), None)
        if chosen is None:
            detail = smoke_values or values
            problems.append('fixture simulator capability failed on %s: %s'
                            % (device_class, ','.join(detail[0]['blocking']) or 'no clean install smoke'))
            chosen = detail[0]
        simulator[device_class] = {
            'manifest_complete': chosen['manifest_complete'],
            'install_smoke': chosen['install_smoke']['status'],
            'device': chosen['device'],
            'bundle': chosen['bundle'],
        }
    source = found['producer_source'][0] if found['producer_source'] else None
    if source is None:
        problems.append('no producer source record was downloaded')
    elif source['implementation']['sha'] != args.sha:
        problems.append('the producer source was staged by a different implementation commit')

    producer = {}
    pending = []
    for device_class in CLASSES:
        value = producers.get(device_class)
        if value is None:
            producer[device_class] = {'mode': None, 'granted': False,
                                      'blocked_by': ['producer_result_missing']}
            pending.append('%s: no producer verification result' % device_class)
            continue
        producer[device_class] = {
            'mode': value['mode'],
            'manifest_complete': value['manifest_complete'],
            'install_smoke': value['install_smoke']['status'],
            'install_manifest_complete': value['install_manifest_complete'],
            'granted': value['granted'],
            'blocked_by': value['blocked_by'],
            'bundle': value['bundle'],
        }
        if not value['granted']:
            pending.append('%s: %s' % (device_class, ','.join(value['blocked_by']) or 'not granted'))
    granted = all(producer[device_class]['granted'] for device_class in CLASSES)
    accepted_result = granted and not problems
    summary = {
        'schema': 1,
        'kind': 'reader-final-s05-summary',
        'implementation': {'sha': args.sha, 'branch': args.branch, 'run_id': args.run_id,
                           'attempt': args.attempt},
        'producer_source': {
            'kind': (source or {}).get('kind'),
            'designation': (source or {}).get('designation'),
            'run': (source or {}).get('run'),
            'artifact': (source or {}).get('artifact'),
            'eligible': (source or {}).get('eligible'),
            'blocked_by': (source or {}).get('blocked_by'),
        },
        'capability': {
            'verifier': {'valid_accepted': harness['valid']['accepted'],
                         'mutants_rejected': len(rejected), 'mutants_total': len(harness['mutants']),
                         'mutants_accepted': accepted,
                         'fixture_cannot_be_producer': harness['fixture_cannot_be_producer'],
                         'runtime_version': harness['runtime_version'],
                         'fixture_executable_sha256': harness['fixture']['executable_sha256']},
            'simulator': simulator,
        },
        'producer': producer,
        'problems': problems,
        'pending': pending,
        'accepted': accepted_result,
        'grants': {'device_signing': False, 'app_store': False, 'physical_device': False,
                   'simulator': True},
        'limits': ['simulator installation only; no physical device run',
                   'no device signing identity, provisioning profile or notarization',
                   'no App Store or TestFlight delivery',
                   'file sharing only as the actual Info.plist declares',
                   'fixture evidence proves the verifier, never the product'],
    }
    output.mkdir(parents=True)
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'accepted': accepted_result,
                      'verifier': summary['capability']['verifier'],
                      'simulator': {key: value['install_smoke']
                                    for key, value in summary['capability']['simulator'].items()},
                      'producer': {key: {'mode': value['mode'], 'granted': value['granted'],
                                         'blocked_by': value['blocked_by']}
                                   for key, value in producer.items()},
                      'problems': problems, 'pending': pending}, indent=2))
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
