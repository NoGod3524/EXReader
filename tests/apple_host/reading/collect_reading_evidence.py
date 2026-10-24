# SPDX-License-Identifier: MIT
"""Authenticate the seven native reading UI cases and original attachments."""
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
from reading_contract import CASES


def case_name(value):
    names = re.findall(r'\btest[A-Za-z0-9_]+\b', value or '')
    require(len(names) == 1 and names[0] in CASES, 'unknown/ambiguous reading case')
    return names[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('platform', 'xcresult', 'output', 'app', 'sdk_root', 'sdk_identity', 'destination', 'fixtures'):
        parser.add_argument('--' + name.replace('_', '-'), required=True)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    source, run, attempt = (os.environ[name] for name in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    require(command('git', 'rev-parse', 'HEAD') == source, 'checkout source differs')
    output, xcresult, app = Path(args.output), Path(args.xcresult), Path(args.app)
    output.mkdir(parents=True, exist_ok=False)
    target = 'macos' if args.platform == 'macos' else 'iphonesimulator'
    sdk = json.loads(Path(args.sdk_identity).read_text())
    validate_sdk(Path(args.sdk_root), sdk, source, run, attempt, target)
    destination = Path(args.destination).read_text().splitlines()
    require(len(destination) == 4 and all(destination), 'missing real destination')
    require((args.platform == 'macos' and destination[0] == 'platform=macOS') or
            (args.platform in ('iphone', 'ipad') and destination[0].startswith('platform=iOS Simulator,id=') and
             destination[2].lower().startswith(args.platform)), 'destination differs')
    plist = app / ('Contents/Info.plist' if target == 'macos' else 'Info.plist')
    require(plistlib.loads(plist.read_bytes())['EXRSourceSHA'] == source, 'app source differs')
    binary = app / ('Contents/MacOS/EXReaderHost' if target == 'macos' else 'EXReaderHost')
    provider = inspect(binary, app.parent / 'EXReaderHost.link.map')
    require(provider['installed_reading_commands_linked'] is True and provider['installed_annotation_view_linked'] is True and provider['static_sdk_linked'] is False, 'F2 provider differs')
    shutil.copytree(app, output / 'program/EXReaderHost.app')
    cases = load_results(xcresult)
    require(len(cases) == 7 and {case_name(row['name']) for row in cases} == set(CASES) and
            all(row['result'] == 'Passed' for row in cases), 'missing/failed/skipped reading case')
    attachments = output / 'attachments'
    command('xcrun', 'xcresulttool', 'export', 'attachments', '--path', xcresult, '--output-path', attachments)
    manifest = json.loads((attachments / 'manifest.json').read_text())
    roles, steps = set(), {}
    for group in manifest:
        owner = case_name(group.get('testIdentifier') or group.get('testName'))
        for item in group['attachments']:
            filename = item['exportedFileName']
            require(Path(filename).name == filename, 'attachment path refused')
            path = attachments / filename
            require(path.is_file() and 0 < path.stat().st_size <= 16 * 1024 * 1024, 'attachment bytes missing')
            match = re.fullmatch(r'(.+)_(?:0|[1-9]\d*)_[0-9A-Fa-f-]{36}\.(png|json|txt)', item['suggestedHumanReadableName'])
            require(match is not None, 'attachment name changed')
            name, extension = match.groups()
            if name.startswith('reading-steps-'):
                payload = json.loads(path.read_text())
                require(extension == 'json' and owner not in steps and case_name(payload['test']) == owner and
                        payload['steps'] == CASES[owner], 'reading step sequence differs')
                steps[owner] = payload['steps']; role = 'steps'
            else:
                require(name.startswith('reading-') and name[8:] in CASES[owner] and extension == 'png' and
                        path.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n', 'unexpected screenshot')
                role = name[8:]
            require((owner, role) not in roles, 'duplicate attachment')
            roles.add((owner, role))
    require(roles == {(owner, role) for owner in CASES for role in ['steps', *CASES[owner]]}, 'missing native attachment')
    result = {'accepted': True, 'source_sha': source, 'run_id': run, 'attempt': attempt,
        'platform': args.platform, 'destination': destination, 'sdk': sdk,
        'fixture_manifest_sha256': digest(Path(args.fixtures)), 'app_sha256': digest(binary),
        'cases': cases, 'steps': steps, 'attachments': inventory(attachments), 'provider': provider,
        'physical_device_execution': False, 'performance_accepted': False}
    (output / 'reading-ui.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'accepted': True, 'platform': args.platform, 'cases': len(cases), 'attachments': len(roles)}))


if __name__ == '__main__':
    main()
