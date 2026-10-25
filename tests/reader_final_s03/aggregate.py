#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Combine this run's recorded verdicts into result.json and validation.json.

The four source identities stay separate: this verifier branch, the actual macOS
producer commit, the approved SDK commit and the producer's own artifact. A
candidate is only accepted when its manifest and its relocation/offline smoke
were both produced by this run from those exact bytes.
"""
import argparse
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / 'tests/reader_distribution_inventory'))
sys.path.insert(0, str(HERE))
import contract as distribution
import spec


def load(path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verifier-sha', default=os.environ.get('GITHUB_SHA', ''))
    parser.add_argument('--producer-sha', default=spec.PRODUCER_SHA)
    parser.add_argument('--sdk-sha', default=spec.SDK_SHA)
    args = parser.parse_args()

    evidence = args.evidence.absolute()
    args.output.mkdir(parents=True, exist_ok=True)
    problems = []
    identity = load(evidence / 'identity.json')
    if identity is None:
        problems.append('identity_evidence_missing')
        identity = {}
    if args.producer_sha != spec.PRODUCER_SHA:
        problems.append('producer_sha_argument:' + args.producer_sha)
    if args.sdk_sha != spec.SDK_SHA:
        problems.append('sdk_sha_argument:' + args.sdk_sha)
    problems += spec.identity_problems(identity, args.verifier_sha)
    producer_sha = (identity.get('producer') or {}).get('sha')
    if not producer_sha:
        problems.append('producer_sha_missing')
    if args.verifier_sha and producer_sha and args.verifier_sha == producer_sha:
        problems.append('verifier_source_substituted_for_producer')

    manifests, smokes, candidates = {}, {}, {}
    for name in sorted(spec.CANDIDATES):
        manifest = load(evidence / ('manifest-' + name + '.json'))
        smoke = load(evidence / ('smoke-' + name + '.json'))
        manifests[name], smokes[name] = manifest, smoke
        entry = {'label': spec.candidate(name)['label'],
                 'selector_bytes_candidate': spec.candidate(name)['selector_bytes'],
                 'manifest_evidence': 'manifest-' + name + '.json',
                 'smoke_evidence': 'smoke-' + name + '.json'}
        candidate_problems = []
        if manifest is None:
            candidate_problems.append('manifest_evidence_missing')
        else:
            candidate_problems += manifest.get('problems') or []
            if manifest.get('accepted') is not True:
                candidate_problems.append('manifest_not_accepted')
            if manifest.get('producer_sha') != producer_sha:
                candidate_problems.append('manifest_producer_sha')
            if manifest.get('sdk_version') != spec.SDK_VERSION:
                candidate_problems.append('manifest_sdk_version')
            if manifest.get('selector_bytes_candidate') != spec.candidate(name)['selector_bytes']:
                candidate_problems.append('manifest_selector_flag')
        if smoke is None:
            candidate_problems.append('smoke_evidence_missing')
        else:
            candidate_problems += smoke.get('problems') or []
            if smoke.get('accepted') is not True:
                candidate_problems.append('smoke_not_accepted')
            if smoke.get('producer_sha') != producer_sha:
                candidate_problems.append('smoke_producer_sha')
            if smoke.get('check_count') is None or smoke['check_count'] < spec.MIN_CHECKS:
                candidate_problems.append('smoke_check_count')
            if not (smoke.get('relocated_bundle') or '').startswith(str(evidence)):
                candidate_problems.append('smoke_bundle_not_relocated_here')
            if manifest is not None:
                libraries = manifest.get('sdk_library') or {}
                if len(libraries) != 1:
                    candidate_problems.append('manifest_sdk_library_count')
                for relative, entry_library in libraries.items():
                    install = entry_library.get('install_name') or ''
                    if not install.startswith('@rpath/' + spec.SDK_LIBRARY_TOKEN):
                        candidate_problems.append('manifest_sdk_install_name:' + str(relative))
                if (manifest.get('info_plist') or {}).get('EXRSourceSHA') != producer_sha:
                    candidate_problems.append('info_plist_source_sha')
        entry['accepted'] = not candidate_problems
        entry['problems'] = candidate_problems
        if manifest is not None:
            entry['executable_sha256'] = manifest.get('signed_binary_sha256')
            entry['pre_sign_binary_sha256'] = manifest.get('pre_sign_binary_sha256')
            entry['sdk_library'] = manifest.get('sdk_library')
            entry['file_count'] = manifest.get('file_count')
            entry['bundle_bytes'] = manifest.get('bundle_bytes')
            entry['dependency_count'] = manifest.get('dependency_count')
            entry['resource_count'] = len(manifest.get('resources') or {})
            entry['license_count'] = len(manifest.get('licenses') or {})
            entry['architecture'] = manifest.get('architecture', {}).get(spec.BUNDLE_EXECUTABLE)
            entry['build_version'] = manifest.get('build_version', {}).get(spec.BUNDLE_EXECUTABLE)
            entry['release_ready'] = manifest.get('release_ready')
            entry['private_path_hits'] = manifest.get('private_path_hits')
            entry['product_library_negative_checks'] = len(
                (manifest.get('product_library') or {}).get('negative_checks') or [])
            entry['raw_providers'] = manifest.get('raw_providers')
        if smoke is not None:
            entry['check_count'] = smoke.get('check_count')
            entry['checks'] = smoke.get('checks')
            entry['relocated_bundle'] = smoke.get('relocated_bundle')
            entry['relocated_archive'] = smoke.get('relocated_archive')
            entry['offline'] = {key: (smoke.get('offline') or {}).get(key)
                                for key in ('mechanism', 'control_reachable', 'denied')}
            entry['codesign'] = {key: (smoke.get('codesign') or {}).get(key)
                                 for key in ('verify_exit', 'adhoc', 'authority', 'gatekeeper_exit',
                                             'notarized', 'quarantined')}
        candidates[name] = entry
        problems += [name + ': ' + item for item in candidate_problems]

    run = {
        'id': os.environ.get('GITHUB_RUN_ID'),
        'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
        'workflow': os.environ.get('GITHUB_WORKFLOW'),
        'job': os.environ.get('GITHUB_JOB'),
        'source_sha': args.verifier_sha,
        'url': ('https://github.com/' + os.environ.get('GITHUB_REPOSITORY', '') + '/actions/runs/'
                + os.environ.get('GITHUB_RUN_ID', '')) if os.environ.get('GITHUB_RUN_ID') else None,
    }
    release_blockers = []
    for name in sorted(candidates):
        hits = (manifests.get(name) or {}).get('private_path_hits') or []
        for blocker in distribution.private_path_blockers(hits):
            release_blockers.append(name + ': ' + blocker)
    pending = [
        'signing identity, notarization, Gatekeeper acceptance and store publication: '
        'no signing secret is used; the candidate is ad-hoc signed only',
        'physical Apple hardware (iPhone/iPad/Mac test devices), USB cabling and human screen '
        'reading: not executed in this package',
        'long-session reading, performance budgets and energy measurements: not measured here',
        'the final unified source integration: this package consumes the pinned producer commit '
        'and does not modify product owners',
    ]
    if release_blockers:
        pending.insert(0, 'distributed bytes carrying build-machine absolute paths: '
                          'owner and release decision outside this package')

    validation = {
        'schema': 1,
        'accepted': not problems,
        'adopted': False,
        'complete_product': False,
        'scope': ('macOS ARM64 .app candidate assembly, dependency closure, resource manifest, '
                  'relocated original native smoke test, offline open and reopen for the pinned '
                  'producer source'),
        'verifier_source_sha': args.verifier_sha,
        'verifier_package': 'tests/reader_final_s03',
        'start_sha': spec.START_SHA,
        'sdk_source_sha': spec.SDK_SHA,
        'sdk_version': spec.SDK_VERSION,
        'sdk_abi': spec.SDK_ABI,
        'frozen_sdk_340': spec.FROZEN_SDK_340,
        'producer': {'branch': spec.PRODUCER_BRANCH, 'source_sha': producer_sha,
                     'expected_sha': spec.PRODUCER_SHA, 'seal_sha': spec.PRODUCER_SEAL_SHA,
                     'run': spec.PRODUCER_RUN, 'run_attempt': spec.PRODUCER_RUN_ATTEMPT,
                     'jobs': spec.PRODUCER_JOBS, 'artifact': spec.PRODUCER_ARTIFACT,
                     'artifact_bytes_or_digest_rechecked_here': False},
        'runs': [run],
        'artifacts': [],
        'candidates': candidates,
        'checks': {
            'candidates': len(candidates),
            'native_self_checks': {name: candidates[name].get('check_count')
                                   for name in sorted(candidates)},
            'app_phases': len(spec.SMOKE_PHASES),
            'dependency_records': {name: candidates[name].get('dependency_count')
                                   for name in sorted(candidates)},
            'product_library_negative_checks': {name: candidates[name].get(
                'product_library_negative_checks') for name in sorted(candidates)},
            'sdk_tree_files': (identity.get('sdk') or {}).get('tree_files'),
            'sdk_libraries': {name: sorted((candidates[name].get('sdk_library') or {}))
                              for name in sorted(candidates)},
            'offline_envelope': {name: candidates[name].get('offline')
                                 for name in sorted(candidates)},
        },
        'release_readiness': {
            'signed_with_owner_identity': False,
            'notarized': False,
            'gatekeeper_accepted': all(
                (smokes[name] or {}).get('codesign', {}).get('gatekeeper_exit') == 0
                for name in smokes) if smokes else False,
            'release_ready': all(candidates[name].get('release_ready') for name in candidates),
            'physical_device_execution': False,
            'blockers': release_blockers,
        },
        'pending': pending,
        'problems': problems,
    }
    (args.output / 'validation.json').write_text(json.dumps(validation, indent=2) + '\n',
                                                encoding='utf-8')
    index = {}
    for path in sorted(evidence.rglob('*')):
        if path.is_file():
            index[path.relative_to(evidence).as_posix()] = {
                'bytes': path.stat().st_size, 'sha256': spec.digest(path)}
    (args.output / 'artifact-index.json').write_text(json.dumps(index, indent=2) + '\n',
                                                     encoding='utf-8')
    result = {'schema': 1, 'accepted': validation['accepted'], 'run': run,
              'producer_sha': producer_sha, 'verifier_sha': args.verifier_sha,
              'sdk_source_sha': spec.SDK_SHA, 'candidates': candidates,
              'checks': validation['checks'], 'problems': problems,
              'evidence_index': 'artifact-index.json'}
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'accepted': validation['accepted'],
                      'candidates': {name: candidates[name]['accepted'] for name in candidates},
                      'native_self_checks': validation['checks']['native_self_checks'],
                      'problems': problems}, indent=2))
    return 0 if validation['accepted'] else 1


if __name__ == '__main__':
    sys.exit(main())
