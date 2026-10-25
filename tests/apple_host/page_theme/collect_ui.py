# SPDX-License-Identifier: MIT
"""Authenticate the original XCTest observations and real installed provider."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collect_evidence import command, load_results
from evidence_contract import digest, inventory, require, validate_sdk
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tools'))
from check_apple_product import inspect

CASES = {
    'testTextThemesPreserveNonzeroPosition': ['text-original', 'text-dark', 'text-light', 'text-original-roundtrip'],
    'testEPUBThemesAndNativeReachability': ['epub-original', 'epub-dark', None, 'epub-light', 'epub-original-roundtrip'],
    'testFixedPDFAndCBZRemainOriginal': ['pdf-original', 'pdf-dark-original-pixels', 'records-cbz-original', 'records-cbz-dark-original-pixels'],
    'testLiveSystemAppearance': ['system-initial-light', 'system-os-dark', 'system-os-light'],
}


def case_name(value):
    matches = re.findall(r'\btest[A-Za-z0-9_]+\b', value or '')
    require(len(matches) == 1 and matches[0] in CASES, 'unknown/ambiguous theme test')
    return matches[0]


def validate_observations(platform, owner, rows):
    expected = list(CASES[owner])
    if None in expected:
        expected[expected.index(None)] = 'native-choices-reachable' if platform == 'macos' else 'landscape-choices-reachable'
    require([row['role'] for row in rows] == expected, 'missing/reordered/duplicate theme observation')
    fields = {}
    for row in rows:
        value = row['bitmap'].split('|')
        require(len(value) == 5 and value[0] in ('original', 'light', 'dark', 'system') and
                re.fullmatch('[0-9a-f]{8}', value[1]) and re.fullmatch('[0-9a-f]{64}', value[2]) and
                value[3].isdigit() and value[4], 'not an actual bitmap observation')
        fields[row['role']] = value
    if owner == 'testTextThemesPreserveNonzeroPosition':
        initial = fields['text-original']
        require(int(initial[3]) > 0, 'text did not move to nonzero offset')
        require(fields['text-dark'][0:2] == ['dark', '101010ff'] and fields['text-light'][0:2] == ['light', 'ffffffff'], 'text canvas differs')
        require(initial == fields['text-original-roundtrip'] and fields['text-dark'][2] != initial[2], 'original roundtrip or changed pixels missing')
        require(all(value[3:] == initial[3:] for value in fields.values()), 'text position changed')
    elif owner == 'testLiveSystemAppearance':
        require(fields['system-initial-light'] == fields['system-os-light'] and
                fields['system-os-dark'][0:2] == ['system', '101010ff'] and
                fields['system-initial-light'][0:2] == ['system', 'ffffffff'] and
                fields['system-os-dark'][3:] == fields['system-initial-light'][3:], 'system notification did not update real pixels')
    elif owner == 'testFixedPDFAndCBZRemainOriginal':
        for kind in ('pdf', 'records-cbz'):
            require(fields[kind + '-original'][1:] == fields[kind + '-dark-original-pixels'][1:], 'fixed pixels changed')
    else:
        require(fields['epub-dark'][0:2] == ['dark', '101010ff'] and fields['epub-light'][0:2] == ['light', 'ffffffff'], 'EPUB canvas differs')


def main():
    parser = argparse.ArgumentParser()
    for key in ('platform', 'xcresult', 'output', 'app', 'sdk-root', 'sdk-identity', 'fixtures', 'system-commands', 'destination'):
        parser.add_argument('--' + key, required=True)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    source, run, attempt = (os.environ[key] for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    output, app, xcresult = Path(args.output), Path(args.app), Path(args.xcresult)
    output.mkdir(parents=True, exist_ok=False)
    target = 'macos' if args.platform == 'macos' else 'iphonesimulator'
    sdk = json.loads(Path(args.sdk_identity).read_text()); validate_sdk(args.sdk_root, sdk, source, run, attempt, target)
    require(sdk['sdk_version'] == '3.41.0' and sdk['abi'] == 1, 'wrong theme SDK')
    info = plistlib.loads((app / ('Contents/Info.plist' if target == 'macos' else 'Info.plist')).read_bytes())
    require(info['EXRSourceSHA'] == source and info['EXRSDKVersion'] == '3.41.0' and info['EXRPageThemeEnabled'] is True, 'theme bundle identity differs')
    binary = app / ('Contents/MacOS/EXReaderHost' if target == 'macos' else 'EXReaderHost')
    provider = inspect(binary, app.parent / 'EXReaderHost.link.map')
    symbols = command('nm', '-g', binary)
    require(len(re.findall(r'\bU\s+_exr_render_page_background\s*$', symbols, re.M)) == 1 and
            not re.search(r'\b[Tt]\s+_exr_render_page', symbols) and provider['static_sdk_linked'] is False, 'alternate/static renderer')
    cases = load_results(xcresult)
    require(len(cases) == len(CASES) and {case_name(row['name']) for row in cases} == set(CASES) and
            all(row['result'] == 'Passed' for row in cases), 'missing/failed/skipped theme case')
    attachments = output / 'attachments'
    command('xcrun', 'xcresulttool', 'export', 'attachments', '--path', xcresult, '--output-path', attachments)
    manifest = json.loads((attachments / 'manifest.json').read_text()); observations, screenshots = {}, set()
    for group in manifest:
        owner = case_name(group.get('testIdentifier') or group.get('testName'))
        for item in group['attachments']:
            filename = item['exportedFileName']; require(Path(filename).name == filename, 'unsafe attachment path')
            path = attachments / filename; require(path.is_file() and 0 < path.stat().st_size < 16 * 1024 * 1024, 'empty/large attachment')
            match = re.fullmatch(r'(.+)_(?:0|[1-9]\d*)_[0-9A-Fa-f-]{36}\.(png|json|txt)', item['suggestedHumanReadableName'])
            require(match is not None, 'attachment name changed')
            role, extension = match.groups()
            if role.startswith('theme-observations-'):
                data = json.loads(path.read_text()); require(owner not in observations and case_name(data['test']) == owner, 'duplicate observation')
                validate_observations(args.platform, owner, data['observations']); observations[owner] = data['observations']
            else:
                require(role.startswith('theme-') and extension == 'png' and path.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n', 'unexpected screenshot')
                require((owner, role[6:]) not in screenshots, 'duplicate screenshot'); screenshots.add((owner, role[6:]))
    require(set(observations) == set(CASES), 'missing observation case')
    require(screenshots == {(owner, row['role']) for owner, rows in observations.items() for row in rows}, 'missing/unowned screenshot')
    system = json.loads(Path(args.system_commands).read_text())
    require(system['served'] == ['dark', 'light'] and system['platform'] == args.platform and system['source_sha'] == source and
            system['run_id'] == run and system['attempt'] == attempt and all(row['exit_code'] == 0 for row in system['commands'] if 'appearance' in row['argv'] or 'osascript' == row['argv'][0]), 'real OS command evidence differs')
    shutil.copytree(app, output / 'program/EXReaderHost.app')
    result = {'accepted': True, 'source_sha': source, 'run_id': run, 'attempt': attempt, 'platform': args.platform,
              'sdk': sdk, 'cases': cases, 'observations': observations, 'attachments': inventory(attachments),
              'app_sha256': digest(binary), 'provider': provider, 'system_commands': system,
              'destination': Path(args.destination).read_text().splitlines(), 'fixture_manifest_sha256': digest(Path(args.fixtures)),
              'physical_device_execution': False, 'old_340_migration_tested': False, 'complete_product': False}
    (output / 'theme-ui.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print('PAGE_THEME_UI_VERIFIED ' + args.platform)


if __name__ == '__main__':
    main()
