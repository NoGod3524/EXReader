#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fail closed on missing Apple organization UI cases and retained evidence."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collect_evidence import command, load_results
from evidence_contract import digest, require

CASES = {
    'testGroupLifecycleAndProcessRestart': ['created', 'renamed', 'deleted', 'restored', 'restart'],
    'testMembershipAndProcessRestart': ['imported', 'added', 'restart', 'removed'],
    'testTagAndSeriesPersist': ['tag', 'series', 'restart'],
    'testStagedIntentSurvivesTerminationAndRetry': ['staged', 'reopened', 'retried', 'persisted'],
    'testNestedShelfSurvivesRestart': ['created', 'restart'],
    'testStaleEditDoesNotOverwriteCompetingRevision': ['competing', 'refused', 'preserved'],
}


def owner(name):
    matches = re.findall(r'\btest[A-Za-z0-9_]+\b', name or '')
    require(len(matches) == 1 and matches[0] in CASES, 'unknown organization case')
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=['macos', 'iphone', 'ipad'], required=True)
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'collection requires Actions')
    source, run, attempt = (os.environ[name] for name in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    require(command('git', 'rev-parse', 'HEAD') == source, 'checkout differs from source')
    plist = args.app / ('Contents/Info.plist' if args.platform == 'macos' else 'Info.plist')
    executable = args.app / ('Contents/MacOS/EXReaderHost' if args.platform == 'macos' else 'EXReaderHost')
    require(plistlib.loads(plist.read_bytes())['EXRSourceSHA'] == source, 'application source differs')
    cases = load_results(args.result)
    require(len(cases) == len(CASES) and {owner(row['name']) for row in cases} == set(CASES)
            and all(row['result'] == 'Passed' for row in cases), 'UI cases missing, skipped or failed')
    args.output.mkdir(parents=True, exist_ok=False)
    attachments = args.output / 'attachments'
    command('xcrun', 'xcresulttool', 'export', 'attachments', '--path', args.result, '--output-path', attachments)
    manifest = json.loads((attachments / 'manifest.json').read_text())
    seen = set()
    for group in manifest:
        case = owner(group.get('testIdentifier') or group.get('testName'))
        for item in group['attachments']:
            name = item['suggestedHumanReadableName']
            filename = item['exportedFileName']
            require(Path(filename).name == filename, 'invalid attachment path')
            path = attachments / filename
            require(path.is_file() and 0 < path.stat().st_size <= 16 * 1024 * 1024, 'attachment missing')
            if name.startswith('organization-steps-'):
                role = 'steps'
                payload = json.loads(path.read_text())
                require(owner(payload['test']) == case and payload['steps'] == CASES[case], 'steps differ')
            elif name.startswith('organization-screen-'):
                role = 'screen'
                require(path.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n', 'screenshot invalid')
            else:
                continue
            require((case, role) not in seen, 'duplicate attachment')
            seen.add((case, role))
    require(seen == {(case, role) for case in CASES for role in ('steps', 'screen')}, 'attachments incomplete')
    result = {'accepted': True, 'source_sha': source, 'run_id': run, 'attempt': attempt,
              'platform': args.platform, 'cases': list(CASES), 'executable_sha256': digest(executable),
              'scope': 'native organization UI cases and process restart only',
              'complete_product_accepted': False, 'physical_device_execution': False, 'problems': []}
    (args.output / 'organization-ui.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
