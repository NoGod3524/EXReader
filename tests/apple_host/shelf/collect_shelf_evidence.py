#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only evidence for the production native Apple catalog shelf."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collect_evidence import command, load_results
from evidence_contract import digest, inventory, require, tree_digest, validate_sdk

CASES = {
    'test01RealShelfAndBoundedInteractiveRows': ['initial-real-shelf'],
    'test02ForwardTraversalOfAllOriginals': ['forward-every-original', 'reverse-every-original'],
    'test03StableEqualTitles': ['equal-titles'],
    'test04TitleAuthorAndLiteralSearch': ['bOoK 0201', 'Unique Shelf Author', '100%_', 'no matching shelf book'],
    'test05RapidSearchRefreshAndNativeViewport': ['refresh-keeps-source-anchor'],
    'test06RotationBackgroundAndProcessRestore': ['native-resize-and-fresh-process'],
    'test07StoredOriginalReadingAndFilteredReturn': ['stored-original-and-filtered-return'],
}


def owner(name):
    matches = re.findall(r'\btest[A-Za-z0-9_]+\b', name or '')
    require(len(matches) == 1 and matches[0] in CASES, 'unknown shelf case')
    return matches[0]


def states(value):
    if isinstance(value, dict):
        if 'cached_rows' in value:
            yield value
        for child in value.values():
            yield from states(child)
    elif isinstance(value, list):
        for child in value:
            yield from states(child)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('platform', 'xcresult', 'output', 'container', 'app', 'seed', 'sdk_root', 'sdk_identity', 'destination'):
        parser.add_argument('--' + name.replace('_', '-'), required=True)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'shelf collection runs only in Actions')
    source, run, attempt = (os.environ[name] for name in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    destination = Path(args.destination).read_text().splitlines()
    require(args.platform in ('macos', 'iphone', 'ipad') and len(destination) == 4 and all(destination), 'shelf destination missing')
    require((args.platform == 'macos' and destination[0] == 'platform=macOS') or
            (args.platform != 'macos' and destination[0].startswith('platform=iOS Simulator,id=') and
             destination[2].lower().startswith(args.platform)), 'shelf destination platform differs')
    seed = json.loads(Path(args.seed).read_text())
    require(seed['accepted'] is True and seed['books'] == len(set(seed['source_keys'])) == 2202 and
            seed['source_sha'] == source and str(seed['run_id']) == run and str(seed['attempt']) == attempt,
            'real SDK seed identity differs')
    expected = set(seed['source_keys'])
    output, result, app = Path(args.output), Path(args.xcresult), Path(args.app)
    output.mkdir(parents=True, exist_ok=False)
    sdk = json.loads(Path(args.sdk_identity).read_text())
    validate_sdk(Path(args.sdk_root), sdk, source, run, attempt, 'macos' if args.platform == 'macos' else 'iphonesimulator')
    plist = app / ('Contents/Info.plist' if args.platform == 'macos' else 'Info.plist')
    require(plistlib.loads(plist.read_bytes())['EXRSourceSHA'] == source and command('git', 'rev-parse', 'HEAD') == source,
            'shelf executable source differs')
    cases = load_results(result)
    require(len(cases) == 7 and {owner(row['name']) for row in cases} == set(CASES) and
            all(row['result'] == 'Passed' for row in cases), 'shelf UI cases failed, skipped or missing')
    attachments = output / 'attachments'
    command('xcrun', 'xcresulttool', 'export', 'attachments', '--path', result, '--output-path', attachments)
    manifest = json.loads((attachments / 'manifest.json').read_text())
    payloads, roles = {}, set()
    for group in manifest:
        case = owner(group.get('testIdentifier') or group.get('testName'))
        for item in group['attachments']:
            filename = item['exportedFileName']
            require(Path(filename).name == filename, 'shelf attachment path refused')
            path = attachments / filename
            require(path.is_file() and 0 < path.stat().st_size <= 16 * 1024 * 1024, 'shelf attachment missing')
            readable = item['suggestedHumanReadableName']
            if readable.startswith('shelf-observations-'):
                require(case not in payloads, 'duplicate shelf observation set')
                payload = json.loads(path.read_text())
                require(owner(payload['test']) == case and [row['id'] for row in payload['observations']] == CASES[case],
                        'shelf named observations differ')
                payloads[case] = payload
                role = 'observations'
            else:
                require(readable.startswith('shelf-screen-') and path.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n',
                        'unexpected shelf screenshot')
                role = 'screen'
            require((case, role) not in roles, 'duplicate shelf attachment')
            roles.add((case, role))
    require(roles == {(case, role) for case in CASES for role in ('observations', 'screen')}, 'shelf attachment set incomplete')
    measured = list(states(payloads))
    require(measured, 'native shelf observations missing')
    for value in measured:
        require(value['page_limit'] == 50 and value['cache_limit'] == 150 and
                0 <= value['cached_rows'] <= value['max_cached_rows'] <= 150 and
                value['cached_rows'] == len(value['keys']) == len(set(value['keys'])) and
                set(value['keys']) <= expected and set(value['visible_keys']) <= set(value['keys']) and
                value['process_peak_rss_bytes'] > 0 and value['generation'] == value['applied_generation'] and not value['loading']
                and not value['restoring_layout'],
                'unbounded, stale or foreign shelf observation')
    walk = payloads['test02ForwardTraversalOfAllOriginals']['observations']
    require(all(row['state']['sources'] == 2202 and row['state']['gestures'] > 0 for row in walk), 'real traversal incomplete')
    require(payloads['test03StableEqualTitles']['observations'][0]['state']['ties'] == 130, 'same-title keys incomplete')
    folder = Path(args.container)
    if args.platform != 'macos':
        folder = folder / 'Library/Application Support/EXReader'
    database_records = {}
    for name in ('library.sqlite', 'reader-catalog.db'):
        saved = output / name
        with sqlite3.connect((folder / name).resolve().as_uri() + '?mode=ro', uri=True) as database:
            with sqlite3.connect(saved) as target:
                database.backup(target)
        database_records[name] = {'sha256': digest(saved), 'bytes': saved.stat().st_size}
    with sqlite3.connect(output / 'library.sqlite') as database:
        originals = {row[0]: 'txt:' + hashlib.sha256(row[1]).hexdigest() for row in database.execute('SELECT id,source FROM books')}
    with sqlite3.connect(output / 'reader-catalog.db') as database:
        require(database.execute('PRAGMA integrity_check').fetchone()[0] == 'ok' and
                not database.execute('PRAGMA foreign_key_check').fetchall(), 'product snapshot integrity differs')
        mappings = database.execute('SELECT book_key,sdk_book_id,location_kind FROM reader_local_books').fetchall()
    require(len(originals) == len(mappings) == 2202 and set(originals.values()) == expected and
            all(originals[sdk_id] == key and mode == 'reflow_global' for key, sdk_id, mode in mappings),
            'actual SDK originals do not match the product shelf')
    shutil.copytree(app, output / 'program/EXReaderHost.app')
    report = {'accepted': True, 'source_sha': source, 'run_id': run, 'attempt': attempt, 'platform': args.platform,
        'ui_cases': 7, 'named_observations': 11, 'attachments': 14, 'originals': 2202, 'cases': cases,
        'page_limit': 50, 'retained_ui_cache_limit': 150, 'sdk_startup_bounded': False,
        'measurements': {'process_peak_rss_bytes': max(row['process_peak_rss_bytes'] for row in measured),
                         'timing_scope': 'actual native layout observations and screenshots; no display-FPS claim'},
        'hard_performance_budget_accepted': False, 'physical_device_execution': False,
        'observations': payloads, 'databases': database_records, 'sdk': sdk,
        'attachment_files': inventory(attachments), 'program_files': inventory(output / 'program'),
        'xcresult_sha256': tree_digest(result), 'destination': Path(args.destination).read_text(), 'problems': []}
    (output / 'shelf-ui.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('accepted', 'source_sha', 'run_id', 'attempt', 'platform', 'ui_cases',
        'named_observations', 'attachments', 'originals', 'measurements', 'sdk_startup_bounded', 'problems')}))


if __name__ == '__main__':
    main()
