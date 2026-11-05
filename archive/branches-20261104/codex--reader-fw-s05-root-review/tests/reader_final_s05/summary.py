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
import os
from pathlib import Path
import sys
import identity
import zip_stage
import bundle_copy

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
            value['_evidence_directory'] = str(path.parent)
            found['results'].append(value)
    for path in sorted(root.rglob('producer-source.json')):
        found['producer_source'].append(load(path))
    return found


def authenticated_inputs(args):
    implementation = identity.implementation(args.sha, args.branch)
    require((args.run_id, args.attempt) == (implementation['run_id'], implementation['attempt']),
            'summary requested another run/attempt')
    repository = os.environ['GITHUB_REPOSITORY']
    prefix = 'repos/%s/actions/runs/%s' % (repository, args.run_id)
    listing = identity.api(prefix + '/attempts/%s/jobs?per_page=100' % args.attempt)
    expected_jobs = {'Verifier fixture and mutant controls'}
    expected_jobs |= {'Authenticate designated producer ' + device for device in CLASSES}
    expected_jobs |= {'Clean simulator install smoke ' + device for device in CLASSES}
    jobs = [row for row in listing['jobs'] if row['name'] in expected_jobs]
    require(listing['total_count'] == len(listing['jobs']) == 6 and len(jobs) == 5 and
            {row['name'] for row in jobs} == expected_jobs, 'S05 original producer job set changed/duplicated')
    require(all(row['status'] == 'completed' and row['conclusion'] == 'success' and
                row['head_sha'] == args.sha and row['run_attempt'] == int(args.attempt) for row in jobs),
            'S05 job failed or source/run/attempt differs')
    artifacts = identity.api(prefix + '/artifacts?per_page=100')['artifacts']
    names = {'s05-harness-%s-%s' % (args.run_id, args.attempt)}
    names |= {'s05-%s-%s-%s-%s' % (kind, device, args.run_id, args.attempt)
              for kind in ('intake', 'smoke') for device in CLASSES}
    selected = [row for row in artifacts if row['name'] in names]
    require(len(selected) == len(names) and {row['name'] for row in selected} == names,
            'S05 current-attempt artifacts missing/duplicated')
    destination = args.evidence.parent / 'authenticated-inputs'
    require(not destination.exists(), 'new strict input directory required')
    destination.mkdir(parents=True)
    retained = []
    for meta in selected:
        raw = identity.archive_bytes(repository, meta, args.sha, args.run_id)
        archive = destination / (meta['name'] + '.zip')
        archive.write_bytes(raw)
        zip_stage.extract(archive, destination / meta['name'])
        archive.unlink()
        retained.append({key: meta[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
    return destination, implementation, retained, jobs


def validate_unique(found, implementation):
    require(len(found['fixture_checks']) == 1 and len(found['producer_source']) == 2,
            'duplicate/missing harness or per-device producer intake')
    identity.same_implementation(found['fixture_checks'][0]['implementation'], implementation)
    sources = {}
    for source in found['producer_source']:
        identity.same_implementation(source['implementation'], implementation)
        keys = set(source['chosen'])
        require(len(keys) == 1 and keys <= set(CLASSES), 'intake must name exactly one device')
        device = next(iter(keys))
        require(device not in sources, 'duplicate producer intake class')
        sources[device] = source
    require(set(sources) == set(CLASSES), 'missing device intake')
    expected = {(device, 'fixture', smoke) for device in CLASSES for smoke in (False, True)}
    observed = set()
    for value in found['results']:
        identity.same_implementation(value['sources']['implementation'], implementation)
        device, mode = value['device_class'], value['mode']
        key = (device, mode, value['install_smoke']['requested'])
        require(key not in observed, 'duplicate verifier result class/mode/smoke')
        observed.add(key)
        if mode in ('producer', 'diagnostic'):
            require(device in sources, 'foreign result device class')
            producer = value['sources']['producer']
            require(all(producer[name] == sources[device][name] for name in ('designation', 'run', 'artifact', 'eligible', 'blocked_by')),
                    'verifier result differs from authenticated per-device intake')
            expected.add(key)
    require(len(found['results']) == 6 and observed == expected and
            sum(value['mode'] in ('producer', 'diagnostic') for value in found['results']) == 2 and
            {value['device_class'] for value in found['results'] if value['mode'] in ('producer', 'diagnostic')} == set(CLASSES),
            'exact four fixture and two per-device actual producer results required')
    return sources


def validate_producer_bundle(value, source):
    if value['mode'] != 'producer':
        require(value['granted'] is False, 'diagnostic result claimed a grant')
        return
    device = value['device_class']
    pin = identity.ARTIFACTS[device]
    require(all(source['artifact'].get(key) == item for key, item in pin.items()), 'intake producer pin differs')
    require((source['designation']['run_id'], source['designation']['attempt'], source['designation']['head_sha'], source['designation']['workflow']) ==
            (identity.RUN, identity.ATTEMPT, identity.SOURCE, identity.WORKFLOW), 'producer designation differs')
    chosen = source['chosen'][device]
    require(chosen['original_binding']['original_bundle_bytes_authenticated'] and
            chosen['original_binding']['original_modes_links_accepted'] is False, 'original facts overstated')
    root = Path(value['_evidence_directory'])
    manifest = load(root / 'bundle-manifest.json')
    rows = manifest['resources']['files']
    require(len(rows) == len({row['path'] for row in rows}), 'duplicate bundle manifest file')
    content = {row['path']: dict(bytes=row['bytes'], sha256=row['sha256']) for row in rows}
    require(content == chosen['snapshot']['content'], 'verifier full bundle inventory differs from authenticated intake')
    require(value['bundle']['executable_sha256'] == chosen['executable_sha256'] and
            value['bundle']['info_plist_sha256'] == chosen['info_plist_sha256'], 'result bundle identity differs')
    checks = value['checks']
    require(len(checks) == len({row['id'] for row in checks}) and
            value['blocking'] == [row['id'] for row in checks if row['status'] == 'fail'], 'verifier check inventory differs')
    install = value['install_smoke']
    copied = install['installation']['bundle_copy']
    require(copied['all_bundle_bytes_match'] and copied['all_observed_links_match'], 'installed bundle bytes/links incomplete')
    bundle_copy.same(copied['source_snapshot'], chosen['snapshot'])
    bundle_copy.same(copied['installed_snapshot'], copied['source_snapshot'], include_metadata=False)
    launch = install['launch']
    require(bundle_copy.running_program(launch['pid'], launch['program'], launch['expected_program']) and
            launch['program_matches'] and launch['alive'], 'actual installed PID/program did not match')
    require(value['original_modes_links_accepted'] is False and value['original_modes_links_status'] == 'pending',
            'original ZIP mode/link fidelity was incorrectly granted')


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
    strict_root, implementation, authenticated_artifacts, authenticated_jobs = authenticated_inputs(args)
    found = collect(strict_root)
    sources = validate_unique(found, implementation)
    for value in found['results']:
        if value['mode'] in ('producer', 'diagnostic'):
            validate_producer_bundle(value, sources[value['device_class']])
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
    source = sources['iphone']
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
        'producer_sources': sources,
        'authenticated_upstream_jobs': authenticated_jobs,
        'authenticated_artifacts': authenticated_artifacts,
        'original_modes_links_accepted': False,
        'original_modes_links_status': 'pending',
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
    return 0 if accepted_result else 1


if __name__ == '__main__':
    sys.exit(main())
