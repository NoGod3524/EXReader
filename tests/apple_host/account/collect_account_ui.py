# SPDX-License-Identifier: MIT
"""Actions-only actual production SwiftUI accounts and retained native state."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collect_evidence import command, load_results
from evidence_contract import digest, require

CASES = {
    'test01RootValidationAnonymousRestartAndUpdate': [
        'http_root_rejected_with_recoverable_form',
        'anonymous_profile_created_through_actual_swiftui',
        'selected_anonymous_profile_survives_actual_process_restart',
        'existing_profile_authorization_form_keeps_root_identity',
        'local_library_remains_selectable_without_network'],
    'test02SeparateAccountLibrariesAndRestart': [
        'first_account_imports_actual_epub_fixture',
        'second_account_does_not_inherit_first_account_original',
        'switching_back_restores_first_account_import',
        'selected_account_and_import_survive_process_restart',
        'account_import_does_not_change_local_library_rows'],
    'test03NativeHTTPSBackgroundCloseAndRetry': [
        'actual_ui_upload_and_256_shard_https_sweep',
        'actual_background_transition_closes_active_account_session',
        'manual_retry_after_background_reopens_and_completes_native_session',
        'local_library_stays_accessible_after_real_network_sync'],
}


def owner(name):
    names = re.findall(r'\btest[A-Za-z0-9_]+\b', name or '')
    require(len(names) == 1 and names[0] in CASES, 'unknown account UI case')
    return names[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('platform', 'xcresult', 'app', 'container', 'output'):
        parser.add_argument('--' + name, required=True, type=Path if name != 'platform' else str)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'account UI evidence runs only in Actions')
    source, run, attempt = (os.environ[name] for name in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    require(args.platform in ('macos', 'iphone', 'ipad'), 'unsupported UI destination')
    require(command('git', 'rev-parse', 'HEAD') == source, 'checkout identity differs')
    info = args.app / ('Contents/Info.plist' if args.platform == 'macos' else 'Info.plist')
    require(plistlib.loads(info.read_bytes())['EXRSourceSHA'] == source, 'actual account UI executable source differs')
    binary = args.app / ('Contents/MacOS/EXReaderHost' if args.platform == 'macos' else 'EXReaderHost')
    args.output.mkdir(parents=True, exist_ok=False)
    cases = load_results(args.xcresult)
    require(len(cases) == 3 and {owner(case['name']) for case in cases} == set(CASES) and
            all(case['result'] == 'Passed' for case in cases), 'account UI cases failed, missing or skipped')
    attachments = args.output / 'attachments'
    command('xcrun', 'xcresulttool', 'export', 'attachments', '--path', args.xcresult, '--output-path', attachments)
    manifest = json.loads((attachments / 'manifest.json').read_text())
    roles = set()
    for group in manifest:
        case = owner(group.get('testIdentifier') or group.get('testName'))
        for row in group['attachments']:
            name = row['exportedFileName']
            require(Path(name).name == name, 'account UI attachment path refused')
            path = attachments / name
            require(path.is_file() and 0 < path.stat().st_size <= 16 * 1024 * 1024, 'account UI attachment missing')
            label = row['suggestedHumanReadableName']
            if label.startswith('account-steps-'):
                payload = json.loads(path.read_text())
                require(owner(payload['test']) == case and payload['steps'] == CASES[case], 'account UI named steps differ')
                role = 'steps'
            else:
                require(label.startswith('account-screen-') and path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'),
                        'unexpected account UI screenshot')
                role = 'screen'
            require((case, role) not in roles, 'duplicate account UI attachment')
            roles.add((case, role))
    require(roles == {(case, role) for case in CASES for role in ('steps', 'screen')}, 'account UI attachments incomplete')
    folder = args.container
    if not (folder / 'accounts.json').is_file():
        folder = folder / 'Library/Application Support/EXReader'
    raw = (folder / 'accounts.json').read_bytes()
    require(0 < len(raw) <= 64 * 1024, 'persisted account metadata missing or over limit')
    profiles = json.loads(raw)
    https = json.loads((args.output.parent / 'https-ui.json').read_text())
    require(https['accepted'] is True and https['source_sha'] == source and
            str(https['run_id']) == run and str(https['attempt']) == attempt and https['platform'] == args.platform,
            'account UI HTTPS evidence source differs')
    require(https['actual_shards'] == 256 and https['minimum_completed_sweeps'] >= 2 and
            https['remote_revisions'] == 1 and https['password_authentication_used'] is False,
            'account UI HTTPS original and retry proof missing')
    require(len(profiles) == 4 and len({profile['id'] for profile in profiles}) == 4, 'unexpected UI profile count')
    for profile in profiles:
        require(set(profile) == {'id', 'root', 'anonymous'} and profile['anonymous'] is True,
                'anonymous UI metadata contains credential fields')
        require(re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', profile['id']) is not None,
                'profile UUID is invalid')
        product = folder / 'accounts' / profile['id'] / 'reader-catalog.db'
        require(product.is_file(), 'actual account product store missing')
        with sqlite3.connect(product.resolve().as_uri() + '?mode=ro', uri=True) as db:
            count = db.execute('SELECT count(*) FROM reader_local_books').fetchone()[0]
            network = profile['root'].startswith('https://127.0.0.1:')
            if network:
                require(profile['root'] == https['root'], 'persisted account differs from actual UI HTTPS endpoint')
            require(count == (1 if '/isolation-a-' in profile['root'] or network else 0), 'persisted account import isolation differs')
            if network:
                require(db.execute('SELECT count(*) FROM reader_outbox').fetchone()[0] == 0,
                        'completed account UI sync retains unacknowledged revisions')
    result = {'accepted': True, 'source_sha': source, 'run_id': run, 'attempt': attempt,
              'platform': args.platform, 'cases': 3, 'named_steps': 14, 'attachments': 6,
              'profiles': 4, 'actual_executable_sha256': digest(binary),
              'scope': 'anonymous SwiftUI accounts, import isolation, real HTTPS and background close/retry',
              'password_ui_accepted': False, 'network_sync_ui_accepted': True,
              'https': https,
              'physical_device_execution': False, 'voiceover_accepted': False}
    (args.output / 'account-ui.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
