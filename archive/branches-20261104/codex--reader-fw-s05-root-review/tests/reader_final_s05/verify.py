#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify one simulator distribution candidate on one device class.

Reads the app bundle, optionally installs and launches it on a freshly erased
iPhone or iPad simulator, and writes the distribution install manifest with the
checks, the device facts and the exact source separation:

* implementation source: the commit of this verifier,
* producer source: the run, attempt, artifact bytes and head commit of the app.

A failed or missing producer stays pending. A fixture proves the tool, never the
product. The mode follows the authenticated producer record: an eligible
producer is verified as a producer, anything else is a diagnostic record and can
never be granted. No device signing identity, App Store delivery or physical
device run is granted by any result this tool writes.
"""
import argparse
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import app_bundle
import sim_smoke
import bundle_copy
import identity


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_json(path):
    return json.loads(Path(path).read_text())


def signing_established(signature):
    return signature.get('state') == 'signed' and signature.get('bundle_sealed') is True and signature.get('verify') is True


def producer_sources(path, mode, device_class, expected_source, implementation_sha):
    value = load_json(path)
    require(value.get('schema') == 1, 'unsupported producer source schema')
    designation = value.get('designation') or {}
    require(designation.get('head_sha'), 'producer source has no designated head commit')
    require(designation['head_sha'] == expected_source,
            'designated producer commit %r differs from the expected source %r'
            % (designation['head_sha'], expected_source))
    implementation = value.get('implementation') or {}
    require(implementation.get('sha') == implementation_sha,
            'producer source was staged by a different implementation commit')
    identity.same_implementation(implementation, identity.implementation(implementation_sha))
    eligible = value.get('eligible') is True
    if mode == 'producer':
        require(eligible, 'producer source is not eligible: ' + ','.join(value.get('blocked_by') or []))
        artifact = value.get('artifact') or {}
        require((artifact.get('download') or {}).get('matches_api_digest') is True,
                'producer artifact bytes do not match the recorded digest')
    elif mode == 'diagnostic':
        require(not eligible, 'an eligible producer source must be verified in producer mode')
    chosen = (value.get('chosen') or {}).get(device_class)
    require(chosen, 'producer source staged no %s app bundle' % device_class)
    return value, chosen


def smoke_checks(smoke):
    if smoke is None:
        return [{'id': 'install.clean_device', 'status': 'pending', 'detail': 'install smoke not requested'},
                {'id': 'install.installed', 'status': 'pending', 'detail': 'install smoke not requested'},
                {'id': 'install.identity', 'status': 'pending', 'detail': 'install smoke not requested'},
                {'id': 'launch.started', 'status': 'pending', 'detail': 'install smoke not requested'},
                {'id': 'launch.alive', 'status': 'pending', 'detail': 'install smoke not requested'},
                {'id': 'launch.program', 'status': 'pending', 'detail': 'install smoke not requested'}]
    clean = smoke.get('clean') or {}
    installation = smoke.get('installation') or {}
    launch = smoke.get('launch') or {}
    return [
        {'id': 'install.clean_device',
         'status': 'pass' if clean.get('erased') and not clean.get('prior_container') else 'fail',
         'detail': 'erased=%r prior_container=%r' % (clean.get('erased'), clean.get('prior_container'))},
        {'id': 'install.installed',
         'status': 'pass' if installation.get('installed_app_exists') else 'fail',
         'detail': 'installed_app=%r' % (installation.get('installed_app'),)},
        {'id': 'install.identity',
         'status': 'pass' if installation.get('identity_matches') else 'fail',
         'detail': 'source=%r installed=%r' % (installation.get('source_executable_sha256'),
                                               installation.get('installed_executable_sha256'))},
        {'id': 'launch.started',
         'status': 'pass' if launch.get('pid') else 'fail',
         'detail': 'pid=%r bundle=%r' % (launch.get('pid'), launch.get('bundle_identifier'))},
        {'id': 'launch.alive',
         'status': 'pass' if launch.get('alive') else 'fail',
         'detail': 'alive_after_seconds=%r' % (launch.get('alive_after_seconds'),)},
        {'id': 'launch.program',
         'status': 'pass' if launch.get('program_matches') else 'fail',
         'detail': 'program=%r' % (launch.get('program'),)},
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path)
    parser.add_argument('--device-class', choices=('iphone', 'ipad'), required=True)
    parser.add_argument('--mode', choices=('fixture', 'diagnostic', 'producer'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--implementation-sha', required=True)
    parser.add_argument('--expected-source')
    parser.add_argument('--producer-source', type=Path)
    parser.add_argument('--runtime-version')
    parser.add_argument('--no-smoke', action='store_true')
    parser.add_argument('--branch', default=os.environ.get('GITHUB_REF_NAME'))
    args = parser.parse_args()
    output = args.output.absolute()
    require(not output.exists(), 'choose a new output directory: ' + str(output))
    producer = None
    chosen = None
    if args.producer_source is not None:
        source = load_json(args.producer_source)
        require(source.get('schema') == 1, 'unsupported producer source schema')
        staged = (source.get('chosen') or {}).get(args.device_class)
        require(staged, 'producer source staged no %s app bundle' % args.device_class)
        app = args.app.absolute() if args.app is not None else (args.producer_source.absolute().parent / staged['staged'])
        mode = args.mode or ('producer' if source.get('eligible') is True else 'diagnostic')
        expected_source = args.expected_source or source['designation']['head_sha']
        producer, chosen = producer_sources(args.producer_source, mode, args.device_class,
                                            expected_source, args.implementation_sha)
    else:
        require(args.app is not None, 'needs --app or --producer-source')
        require(args.mode in (None, 'fixture'), 'diagnostic and producer modes need --producer-source')
        app = args.app.absolute()
        mode = 'fixture'
        expected_source = args.expected_source or args.implementation_sha
    require(app.is_dir() and app.suffix == '.app', 'not an .app bundle: ' + str(app))
    if mode == 'producer':
        require(Path(producer['chosen'][args.device_class]['staged']).name == app.name,
                'staged app name %r differs from the producer record %r'
                % (app.name, Path(producer['chosen'][args.device_class]['staged']).name))

    output.mkdir(parents=True)
    manifest = app_bundle.manifest(app)
    if chosen is not None:
        bundle_copy.same(bundle_copy.snapshot(app), chosen['snapshot'])
        if mode == 'producer':
            require(chosen.get('original_binding', {}).get('original_bundle_bytes_authenticated') is True,
                    'original complete bundle bytes were not authenticated')
            bundle_copy.same(bundle_copy.snapshot(app), chosen['original_binding']['snapshot'])
        require(chosen.get('executable_sha256') == manifest['executable'].get('sha256'),
                'staged executable bytes differ from the authenticated producer artifact')
        require(chosen.get('info_plist_sha256') == manifest['info_plist'].get('sha256'),
                'staged Info.plist bytes differ from the authenticated producer artifact')
    bundle_identifier = (manifest['product'] or {}).get('CFBundleIdentifier')
    require(bundle_identifier, 'the bundle has no CFBundleIdentifier')
    smoke = None
    smoke_error = None
    if not args.no_smoke:
        try:
            smoke = sim_smoke.run(app, args.device_class, output / 'simulator', bundle_identifier,
                                 (manifest['executable'] or {}).get('name'))
        except Exception as error:  # keep the device facts that were already written
            smoke_error = str(error)
            record = output / 'simulator' / 'simulator.json'
            smoke = json.loads(record.read_text()) if record.is_file() else {'device_class': args.device_class}
            smoke['status'] = 'fail'
            smoke.setdefault('error', smoke_error)
    runtime = args.runtime_version or (smoke or {}).get('device', {}).get('runtime_version')
    checks = app_bundle.check(manifest, args.device_class, mode=mode,
                              runtime_version=runtime, expected_source=expected_source)
    checks += smoke_checks(smoke)
    if producer is not None:
        checks.append(dict(id='producer.original_modes_links_preservation', status='pending',
                           detail='original report attests file bytes only; ZIP does not attest original chmod/link metadata; no chmod or resign applied'))
    if smoke is not None:
        copied = (smoke.get('installation') or {}).get('bundle_copy') or {}
        checks.append(dict(id='install.complete_bundle_bytes', status='pass' if copied.get('all_bundle_bytes_match') else 'fail',
                           detail='all installed files/bytes/hashes and observed safe links compared'))
    blocking = [item['id'] for item in checks if item['status'] == 'fail']
    pending = [item['id'] for item in checks if item['status'] == 'pending']
    manifest_complete = not blocking
    smoke_pass = bool(smoke) and smoke.get('status') == 'pass'
    install_manifest_complete = manifest_complete and smoke_pass
    blocked_by = []
    granted = False
    capability_verified = False
    if mode == 'fixture':
        capability_verified = install_manifest_complete if not args.no_smoke else manifest_complete
        blocked_by = ['fixture_is_not_a_producer_source']
        if not capability_verified:
            blocked_by += blocking
    elif mode == 'diagnostic':
        blocked_by = list((producer or {}).get('blocked_by') or []) + blocking
        if not smoke_pass:
            blocked_by.append('install_smoke_incomplete')
    else:
        granted = bool(producer.get('eligible')) and install_manifest_complete
        if not granted:
            blocked_by = list(producer.get('blocked_by') or []) + blocking
            if not smoke_pass:
                blocked_by.append('install_smoke_incomplete')
    sources = {'implementation': identity.implementation(args.implementation_sha, args.branch),
               'producer': None}
    if producer is not None:
        sources['producer'] = {
            'kind': producer.get('kind'),
            'designation': producer.get('designation'),
            'run': producer.get('run'),
            'artifact': producer.get('artifact'),
            'eligible': producer.get('eligible'),
            'blocked_by': producer.get('blocked_by'),
        }
    result = {
        'schema': app_bundle.SCHEMA,
        'kind': 'reader-final-s05-simulator-distribution',
        'device_class': args.device_class,
        'mode': mode,
        'sources': sources,
        'bundle': {'name': manifest['app']['name'], 'files': manifest['app']['files'],
                   'bytes': manifest['app']['bytes'],
                   'identifier': bundle_identifier,
                   'executable': (manifest['executable'] or {}).get('name'),
                   'executable_sha256': (manifest['executable'] or {}).get('sha256'),
                   'info_plist_sha256': (manifest['info_plist'] or {}).get('sha256'),
                   'source_sha': (manifest['source'] or {}).get('EXRSourceSHA'),
                   'sdk_version': (manifest['source'] or {}).get('EXRSDKVersion'),
                   'platform': (manifest['product'] or {}).get('CFBundleSupportedPlatforms'),
                   'family': (manifest['product'] or {}).get('UIDeviceFamily'),
                   'minimum_os': (manifest['product'] or {}).get('MinimumOSVersion')},
        'signature': {'state': (manifest['signature'] or {}).get('state'),
                      'signed': (manifest['signature'] or {}).get('signed'),
                      'verify': (manifest['signature'] or {}).get('verify'),
                      'bundle_sealed': (manifest['signature'] or {}).get('bundle_sealed'),
                      'entitlements_sha256': (manifest['signature'] or {}).get('entitlements_sha256'),
                      'entitlements': (manifest['signature'] or {}).get('entitlements')},
        'signing': {'state': (manifest['signature'] or {}).get('state'),
                    'verify': (manifest['signature'] or {}).get('verify'),
                    'bundle_sealed': (manifest['signature'] or {}).get('bundle_sealed'),
                    'established': signing_established(manifest['signature'] or {}),
                    'device_signing_granted': False},
        'file_sharing': manifest['file_sharing'],
        'device': (smoke or {}).get('device'),
        'runtime_version': runtime,
        'checks': checks,
        'blocking': blocking,
        'pending': pending,
        'original_modes_links_accepted': False,
        'original_modes_links_status': 'pending',
        'manifest_complete': manifest_complete,
        'install_smoke': {'status': (smoke or {}).get('status', 'skipped'),
                          'requested': not args.no_smoke,
                          'error': smoke_error or (smoke or {}).get('error'),
                          'installation': (smoke or {}).get('installation'),
                          'launch': (smoke or {}).get('launch'),
                          'clean': (smoke or {}).get('clean')},
        'install_manifest_complete': install_manifest_complete,
        'capability_verified': capability_verified,
        'granted': granted,
        'blocked_by': sorted(set(blocked_by)),
        'grants': {'device_signing': False, 'app_store': False, 'physical_device': False,
                   'simulator': True},
        'limits': app_bundle.LIMITS,
        'evidence': {'bundle_manifest': 'bundle-manifest.json',
                     'install_manifest': 'install-manifest.json',
                     'simulator': 'simulator/simulator.json' if smoke else None},
    }
    (output / 'bundle-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    install_manifest = {
        'schema': app_bundle.SCHEMA,
        'kind': 'reader-final-s05-install-manifest',
        'device_class': args.device_class,
        'mode': mode,
        'sources': sources,
        'app': manifest['app'],
        'bundle_identifier': bundle_identifier,
        'executable': manifest['executable'],
        'info_plist': {'sha256': (manifest['info_plist'] or {}).get('sha256'),
                       'format': (manifest['info_plist'] or {}).get('format'),
                       'keys': sorted(((manifest['info_plist'] or {}).get('keys') or {}).keys())},
        'file_sharing': manifest['file_sharing'],
        'signature': result['signature'],
        'files': manifest['resources']['files'],
        'installation': result['install_smoke'],
        'device': result['device'],
        'limits': app_bundle.LIMITS,
    }
    (output / 'install-manifest.json').write_text(json.dumps(install_manifest, indent=2) + '\n')
    (output / 'checks.json').write_text(json.dumps(checks, indent=2) + '\n')
    if smoke is not None:
        (output / 'simulator').mkdir(parents=True, exist_ok=True)
        (output / 'simulator' / 'simulator.json').write_text(json.dumps(smoke, indent=2) + '\n')
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'device_class': args.device_class, 'mode': mode,
                      'bundle': result['bundle'], 'manifest_complete': manifest_complete,
                      'install_smoke': result['install_smoke']['status'],
                      'capability_verified': capability_verified, 'granted': granted,
                      'signing': result['signing'], 'blocking': blocking, 'pending': pending,
                      'blocked_by': result['blocked_by']}, indent=2))
    ok = capability_verified if mode == 'fixture' else (granted if mode == 'producer' else True)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
