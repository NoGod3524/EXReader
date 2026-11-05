# SPDX-License-Identifier: MIT
"""Actions only. Strict same-run evidence for S19.

Every number here is recomputed from the artifacts this run produced: the tested
source, each platform report, the two program identities, the identical named
check set across platforms, and the ZIP size/digest/expiry that GitHub reports
for the very artifacts uploaded by this attempt.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from protocol import platform_artifacts, sdk_aliases, looks_like_sdk
from run import windows_static_ownership
from pe import PE

EXPECTED_CHECKS = [
    'installed-sdk-is-the-reviewed-candidate',
    'installed-five-reviewed-packages',
    'host-dso-and-executable-built-from-installed-packages',
    'six-mixed-graphs-refused',
    'font-library-real-import-lease-and-removal',
    'original-export-real-original-bytes',
    'annotation-export-then-import-round-trip',
    'jump-history-real-landing-and-back',
    'sync-status-real-session-capture',
    'one-loaded-sdk-implementation',
    'installed-webdav-extra-is-distinct-from-sdk',
    'host-executable-holds-no-sdk-module-or-store-copy',
    'product-dso-holds-no-sdk-object-copy',
    'one-sdk-shared-lib-per-image',
]
NEGATIVES = ['negative-dso-static-sdk', 'negative-two-feature-dso', 'negative-host-links-module',
             'negative-module-outside-prefix', 'negative-standalone-alongside-dso',
             'negative-private-store']
WINDOWS_CHECKS = EXPECTED_CHECKS[:2] + ['real-win32-static-product-built',
    'six-mixed-graphs-refused', 'native-gui-open-render-and-five-feature-dispatch'] + EXPECTED_CHECKS[4:9] + [
    'single-static-sdk-store-and-five-module-owner']
WINDOWS_NEGATIVES = ['negative-dso-static-sdk', 'negative-windows-shared-owner',
    'negative-two-standalone-owners', 'negative-module-outside-prefix', 'negative-cli-as-gui', 'negative-private-store']


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-source', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--attempt', required=True)
    options = parser.parse_args()

    api = json.loads(options.artifacts.read_text(encoding='utf-8'))
    platforms = {}
    problems = []
    try:recorded = platform_artifacts(api['artifacts'], options.expect_source, options.run, options.attempt)
    except (ValueError, KeyError, TypeError) as error:
        recorded = {};problems.append('platform artifact identities: ' + str(error))
    for folder in sorted(item for item in options.root.iterdir() if item.is_dir()):
        result_path = folder / 'result.json'
        if not result_path.exists():
            problems.append('missing result.json in ' + folder.name)
            continue
        result = json.loads(result_path.read_text(encoding='utf-8'))
        key = result.get('runner_os') or folder.name
        identity = (result['source_sha'], str(result['run_id']), str(result['attempt']))
        if identity != (options.expect_source, options.run, options.attempt):
            problems.append(key + ': source/run/attempt mismatch ' + repr(identity))
        if not result['accepted']:
            problems.append(key + ': not accepted')
        windows = key == 'Windows'
        names = [item['name'] for item in result['checks']]
        if names != (WINDOWS_CHECKS if windows else EXPECTED_CHECKS):
            problems.append(key + ': check set differs ' + repr(names))
        if result['count'] != len(result['checks']):
            problems.append(key + ': count mismatch')
        if result['negatives'] != (WINDOWS_NEGATIVES if windows else NEGATIVES):
            problems.append(key + ': negative set differs ' + repr(result['negatives']))
        if not result['single_sdk_module'] or not result['exr_pointer_identity']:
            problems.append(key + ': single SDK identity not proven')
        if windows:
            product = folder / 'EXReaderProduct.exe'
            native_log = folder / 'drive.log'
            if (result.get('provider_mode') != 'static-win32-product' or not result.get('host_ui')
                    or set(result['programs']) != {'EXReaderProduct'} or not product.is_file()
                    or PE(product).subsystem != 2 or not native_log.is_file()
                    or not (folder / 's19-native-render.png').is_file() or not (folder / 'Reader.otf').is_file()):
                problems.append('Windows: real native GUI static-owner evidence missing; historical CLI cannot grant acceptance')
            else:
                imports = PE(product).imports()
                loaded = result['modules_loaded']
                if any(looks_like_sdk(name) or 'reader_host_features' in name for name in imports + loaded):
                    problems.append('Windows: static GUI imported/loaded a second SDK or feature image')
                ownership = windows_static_ownership(folder / 'windows-host.map')
                if ownership != result.get('static_ownership'):
                    problems.append('Windows: staged link map differs from static definition ownership report')
                text = native_log.read_text(encoding='utf-8')
                if 's19_features' not in text or 'SHOT' not in text or '\tFAIL\t' in text:
                    problems.append('Windows: native open/render/feature drive failed')
        else:
          if result.get('provider_mode') != 'shared-feature-dso':
            problems.append(key + ': wrong provider contract')
          sdk = result.get('sdk_image', {})
          allowed_aliases = sdk_aliases(key, result['sdk_version'])
          aliases = sdk.get('aliases', [])
          if not aliases or any(name not in allowed_aliases for name in aliases):
            problems.append(key + ': installed SDK alias set is invalid')
          sdk_modules = [name for name in result['modules_loaded'] if looks_like_sdk(name)]
          if len(sdk_modules) != 1 or sdk_modules[0] not in aliases:
            problems.append(key + ': loaded SDK module count ' + repr(result['modules_loaded']))
          image = folder / sdk.get('artifact_name', 'missing-sdk-image')
          if (sdk.get('artifact_name') not in aliases or not image.is_file()
                or image.stat().st_size != sdk.get('bytes') or sha256(image) != sdk.get('sha256')):
            problems.append(key + ': staged SDK image identity differs from installed provider')
        for name, recorded_program in result['programs'].items():
            candidates = [folder / name, folder / (name + '.exe'), folder / (name + '.dll'),
                          folder / (name + '.dylib'), folder / ('lib' + name + '.so'),
                          folder / ('lib' + name + '.dylib'), folder / ('lib' + name + '.a')]
            found = next((item for item in candidates if item.exists()), None)
            if found is None:
                problems.append(key + ': artifact missing for ' + name)
                continue
            if found.stat().st_size != recorded_program['bytes']:
                problems.append(key + ': size changed for ' + name)
            if sha256(found) != recorded_program['sha256']:
                problems.append(key + ': digest changed for ' + name)
        report = result['report']
        raw = json.loads((folder / 'host-evidence.json').read_text(encoding='utf-8'))
        original = json.loads((folder / 'features-report.json').read_text(encoding='utf-8'))
        if raw.get('report') != report or original != report or raw.get('run') != 0:
            problems.append(key + ': raw business reports differ from the acceptance result')
        if raw.get('exe_pointer') != raw.get('dso_pointer') or raw.get('identity') != 1:
            problems.append(key + ': actual process SDK pointers differ')
        if sorted({item['name'] for item in raw['loaded']}) != result['modules_loaded']:
            problems.append(key + ': actual process module inventory differs')
        if (not (report['font']['glyph_A'] or report['font']['glyph_0'])
                or report['original']['bytes_match'] != 1):
            problems.append(key + ': business path did not produce real bytes')
        if report['annotations']['created'] != 2 or report['history']['resolve'] != 1:
            problems.append(key + ': module business path incomplete')
        if report['sync']['mirrored'] != 1 or report['sync']['outbox_included'] != 1:
            problems.append(key + ': sync view did not mirror the real session')
        platforms[key] = {
            'result_sha256': sha256(result_path),
            'count': result['count'],
            'checks': names,
            'programs': result['programs'],
            'negatives': result['negatives'],
            'report': report,
            'dav_requests': result['dav_requests'],
            'platform': result['platform'],
        }

    check_sets = {json.dumps(item['checks']) for key, item in platforms.items() if key != 'Windows'}
    if len(check_sets) != 1:
        problems.append('shared-provider Linux/macOS check sets differ')
    if set(platforms) != {'Linux', 'Windows', 'macOS'}:
        problems.append('expected Linux/Windows/macOS reports, got ' + repr(sorted(platforms)))

    artifacts = {}
    for name, entry in recorded.items():
        artifacts[name] = {'id': entry['id'], 'size_in_bytes': entry['size_in_bytes'],
                           'digest': entry['digest'], 'expires_at': entry['expires_at'],
                           'expired': entry.get('expired')}
        if entry.get('expired'):
            problems.append('artifact expired: ' + name)

    payload = {
        'accepted': not problems,
        'problems': problems,
        'source_sha': options.expect_source,
        'run_id': options.run,
        'attempt': options.attempt,
        'platforms': platforms,
        'shared_platform_identical_checks': len(check_sets) == 1,
        'windows_static_contract': 'real WIN32 EXReaderProduct, five business paths, one static owner',
        'artifacts': artifacts,
        'host_ui': False,
        'actual_hosts': False,
        'complete_product': False,
    }
    options.output.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in payload.items() if key != 'platforms'}, indent=2))
    if problems:
        sys.exit(1)


if __name__ == '__main__':
    main()
