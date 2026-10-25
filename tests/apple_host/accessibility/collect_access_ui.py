# SPDX-License-Identifier: MIT
"""Actions-only production semantics and real touch/scroll regressions."""
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
    'test01ProductionBodyNamesAndActualEdgeTap': ['complete_actual_page_body',
        'production_control_names_without_internal_hash', 'actual_outer_hit_region_navigates_back'],
    'test02CompactReaderActualTurnFontAndNotes': ['platform_text_size_fixture',
        'compact_header_and_actual_page_inside_window', 'actual_page_turn_in_compact_layout',
        'actual_font_change_after_reaching_toolbar_control', 'actual_notes_dialog_after_reaching_toolbar_control',
        'actual_edge_back_after_toolbar_scroll'],
}


def owner(name):
    found = re.findall(r'\btest[A-Za-z0-9_]+\b', name or '')
    require(len(found) == 1 and found[0] in CASES, 'unknown production accessibility case')
    return found[0]


def inside(window, frame):
    x, y, width, height = window
    a, b, w, h = frame
    return w > 0 and h > 0 and a >= x - 2 and b >= y - 2 and a + w <= x + width + 2 and b + h <= y + height + 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=('macos', 'iphone', 'ipad'), required=True)
    for name in ('root', 'app', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'production access evidence runs only in Actions')
    source, run, attempt = (os.environ[name] for name in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    require(command('git', 'rev-parse', 'HEAD') == source, 'production access checkout source differs')
    info = args.app / ('Contents/Info.plist' if args.platform == 'macos' else 'Info.plist')
    require(plistlib.loads(info.read_bytes())['EXRSourceSHA'] == source, 'production access actual program source differs')
    args.output.mkdir(parents=True, exist_ok=False)
    roles, observations = set(), {}
    for result_name, expected in zip(('semantics', 'layout'), CASES):
        result = args.root / (result_name + '.xcresult')
        cases = load_results(result)
        require(len(cases) == 1 and owner(cases[0]['name']) == expected and cases[0]['result'] == 'Passed',
                'production access actual case failed, skipped or missing')
        attachments = args.output / (result_name + '-attachments')
        command('xcrun', 'xcresulttool', 'export', 'attachments', '--path', result, '--output-path', attachments)
        manifest = json.loads((attachments / 'manifest.json').read_text())
        for group in manifest:
            case = owner(group.get('testIdentifier') or group.get('testName'))
            require(case == expected, 'production access attachment source case differs')
            for item in group['attachments']:
                filename = item['exportedFileName']
                require(Path(filename).name == filename, 'production access attachment path refused')
                path = attachments / filename
                require(path.is_file() and 0 < path.stat().st_size <= 16 * 1024 * 1024, 'production access attachment missing')
                label = item['suggestedHumanReadableName']
                if label.startswith('access-observations-'):
                    value = json.loads(path.read_text())
                    require(owner(value['test']) == case and [row['id'] for row in value['observations']] == CASES[case],
                            'production access actual observations differ')
                    observations.update({row['id']: row['values'] for row in value['observations']})
                    role = 'observations'
                else:
                    require(label.startswith('access-screen-') and path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'),
                            'unexpected production access screenshot')
                    role = 'screen'
                require((case, role) not in roles, 'duplicate production access attachment')
                roles.add((case, role))
    require(roles == {(case, role) for case in CASES for role in ('observations', 'screen')}, 'production access attachments incomplete')
    body = observations['complete_actual_page_body']['body']
    require(len(body) > 60 and 'annotations.' in body, 'production page text still truncated')
    names = observations['production_control_names_without_internal_hash']
    require(names == {'decrease': '减小字号', 'increase': '增大字号', 'internal_hash_present': False}, 'production semantic names differ')
    layout = observations['compact_header_and_actual_page_inside_window']
    require(inside(layout['window'], layout['back']) and inside(layout['window'], layout['page']), 'production compact controls clipped')
    fixture = observations['platform_text_size_fixture']
    require(fixture['dynamic_type_tested'] is (args.platform != 'macos'), 'actual content size fixture scope differs')
    if args.platform != 'macos':
        require(fixture['caption1_points'] > 20, 'actual device content size did not change')
        require(layout['back'][2] >= 44 and layout['back'][3] >= 44, 'actual back touch target too small')
    executable = args.app / ('Contents/MacOS/EXReaderHost' if args.platform == 'macos' else 'EXReaderHost')
    report = {'accepted': True, 'source_sha': source, 'run_id': run, 'attempt': attempt,
              'platform': args.platform, 'cases': 2, 'named_observations': 9, 'attachments': 4,
              'scope': 'production body/name semantics and actual reachable touch/scroll operations',
              'actual_executable_sha256': digest(executable), 'dynamic_type_tested': args.platform != 'macos',
              'voiceover_accepted': False, 'full_accessibility_accepted': False,
              'focus_order_accepted': False, 'physical_device_execution': False,
              'audible_announcements_verified': False, 'observations': observations}
    (args.output / 'production-access-ui.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
