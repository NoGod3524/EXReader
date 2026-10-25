"""Authenticate this run's real owner ZIP; preserve the pinned original judge body."""
import json
import os
import subprocess
import sys
import zipfile

import guard
from projection import ORIGINAL, OLD_AUTH, adapt_auth, project_auth, current_producer_identity
from selftest import EXPECTED


def need(value, message):
    if not value:
        raise RuntimeError(message)


def api(path):
    return json.loads(subprocess.check_output(
        ['gh', 'api', 'repos/' + os.environ['GITHUB_REPOSITORY'] + path]))


def current_producer(run, args):
    need(args.source == os.environ['GITHUB_SHA'] and args.run == int(os.environ['GITHUB_RUN_ID']),
         'only the actual current run/source may be authenticated')
    attempt = int(os.environ['GITHUB_RUN_ATTEMPT'])
    jobs = api(f'/actions/runs/{args.run}/attempts/{attempt}/jobs?per_page=100')
    context = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
               'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'job': os.environ['GITHUB_JOB']}
    return current_producer_identity(run, args, context, jobs)


def source_provenance(archive, source, run, attempt, root, network_verified, peer_verified):
    # The original verifier has already checked every original ZIP byte, all nine
    # owner reports, three kill boundaries and both complete received-owner runs.
    need(network_verified is True and peer_verified is True, 'actual TLS/Mac11 paths are mandatory, not optional')
    need(root.get('actual_account_window_mac_receive_passed') is True
         and root.get('actual_received_owner_all11_two_processes_passed') is True,
         'complete actual account receiver and two-process Mac11 proof required')
    need([item['original_compact_ui_checks'] for item in root['profiles']] == [22, 22]
         and [item['bulk_original_checks'] for item in root['profiles']] == [21, 21],
         'both complete original compact22/bulk21 profiles required')
    expected = guard.inspect_source()
    with zipfile.ZipFile(archive) as packed:
        def read(suffix):
            found = [item for item in packed.infolist()
                     if item.filename == suffix or item.filename.endswith('/' + suffix)]
            need(len(found) == 1 and found[0].file_size <= 1024**2
                 and (found[0].external_attr >> 16) & 0o170000 != 0o120000,
                 'unique bounded regular common source report required')
            return json.loads(packed.read(found[0]))
        stored = read('windows-raw3-preflight/common-source.json')
        controls = read('windows-raw3-preflight/common-negative.json')
    need(stored == expected and stored['guard_kind'] == 'common-windows-owner'
         and stored['legacy_guard_executed'] is False and stored['source_preflight_passed'] is True,
         'raw ZIP source guard is not the fresh explicit common guard')
    need(stored['accepted'] is False and stored['runtime_accepted'] is False,
         'source preflight must not impersonate runtime or old-guard acceptance')
    need(controls['source_sha'] == source and str(controls['run_id']) == str(run)
         and int(controls['attempt']) == attempt and controls['negative_controls_passed'] is True
         and controls['checkout_and_index_unchanged'] is True,
         'negative report identity/state differs')
    need({row['name'] for row in controls['controls']} == EXPECTED
         and len(controls['controls']) == len(EXPECTED)
         and all(row['rejected'] is True for row in controls['controls']), 'incomplete refusal controls')
    return {'guard_kind': stored['guard_kind'], 'source_sha': source, 'run_id': run, 'attempt': attempt,
            'legacy_guard_executed': False, 'negative_controls': len(EXPECTED),
            'workflow_projection_exact': stored['workflow_projection_exact'],
            'original_auth_source': ORIGINAL, 'old_auth_run_reused': False,
            'original_auth_sha256': stored['original_auth_sha256']}


def main():
    guard.inspect_source()
    original = guard.git('show', ORIGINAL + ':' + OLD_AUTH).decode('utf-8')
    need((guard.ROOT / OLD_AUTH).read_text(encoding='utf-8') == original, 'pinned original authentication source changed')
    adapted = adapt_auth(original)
    need(project_auth(adapted) == original, 'adaptation changed an original owner/capture assertion')
    namespace = {'__name__': 'common_owner_original_auth_entry', '__file__': str(guard.ROOT / OLD_AUTH),
                 'common_current_producer': current_producer, 'common_source_provenance': source_provenance}
    # No API metadata, environment identity or original file is patched. Only the
    # enumerated standalone entry adapts to this actual in-progress two-job run.
    exec(compile(adapted, str(guard.ROOT / OLD_AUTH) + ' [common entry]', 'exec'), namespace)
    sys.path.insert(0, str(guard.ROOT / 'tests/reader_windows_compact'))
    namespace['main']()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        folder = guard.ROOT / 'build/windows-owner-authentication'
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'common-failure.json').write_text(json.dumps({
            'source_sha': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
            'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'accepted': False, 'complete_product': False,
            'guard_kind': 'common-windows-owner', 'error': str(error)}, indent=2) + '\n', encoding='utf-8')
        raise
