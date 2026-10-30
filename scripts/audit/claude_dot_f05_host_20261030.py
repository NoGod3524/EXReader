# SPDX-License-Identifier: MIT
"""Actions-only independent audit of the real-host F05 original artifact ZIP.

Downloads the ZIP uploaded by this run and attempt through the GitHub API,
authenticates its size and SHA-256 against the API metadata, extracts it into a
fresh directory with path checks, and re-derives the claims from the raw
requests.json and result.json instead of trusting a summary.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

EXPECTED = [
    'peerA_real_import_edit_and_scan_put_exact_history_to_https_wire',
    'peerB_independent_profile_receives_same_revisions_via_get_without_local_planting',
    'peerB_imports_identical_original_and_keeps_received_history',
    'both_peers_make_distinct_offline_children_of_one_received_head',
    'peerB_cancel_at_gated_wire_request_leaves_remote_unchanged_and_outbox_pending',
    'peerB_partial_put_body_reset_stores_nothing_and_explicit_retry_state_is_visible',
    'peerB_host_process_sigkill_after_remote_commit_before_acknowledgement',
    'peerB_restart_is_idempotent_one_wire_object_one_local_row_and_outbox_acknowledged',
    'peerA_wire_receive_of_peerB_sibling_yields_two_heads_without_selecting_or_projecting',
    'both_peers_converge_on_identical_sibling_heads_titles_unselected_and_wire_history',
    'credentials_and_authorization_are_absent_from_evidence_and_wire_bodies',
]


def gh(*arguments, output=None):
    command = ['gh', 'api', *arguments]
    if output:
        with open(output, 'wb') as handle:
            subprocess.run(command, stdout=handle, check=True, timeout=300)
        return None
    return json.loads(subprocess.run(command, capture_output=True, check=True, timeout=120).stdout)


def main():
    parser = argparse.ArgumentParser()
    for name in ('repo', 'run-id', 'attempt', 'source', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True)
    audit = {'repo': args.repo, 'run_id': args.run_id, 'attempt': args.attempt, 'source': args.source,
             'accepted': False, 'problems': []}
    problems = audit['problems']
    wanted = 'claude-dot-f05-host-%s-%s' % (args.run_id, args.attempt)
    listing = gh('repos/%s/actions/runs/%s/artifacts?per_page=100' % (args.repo, args.run_id))
    matches = [a for a in listing['artifacts'] if a['name'] == wanted and not a['expired']]
    if len(matches) != 1:
        problems.append('expected exactly one artifact %s, found %d' % (wanted, len(matches)))
    else:
        meta = matches[0]
        audit['artifact'] = {k: meta.get(k) for k in ('id', 'name', 'size_in_bytes', 'digest', 'created_at')}
        zip_path = out / 'original.zip'
        gh('repos/%s/actions/artifacts/%d/zip' % (args.repo, meta['id']), output=zip_path)
        data = zip_path.read_bytes()
        audit['zip'] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        if meta.get('digest') and meta['digest'] != 'sha256:' + audit['zip']['sha256']:
            problems.append('ZIP digest differs from the API digest')
        if len(data) != meta['size_in_bytes']:
            problems.append('ZIP size differs from the API size')
        folder = out / 'extracted'
        folder.mkdir()
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.namelist():
                target = (folder / member).resolve()
                if folder.resolve() not in target.parents and target != folder.resolve():
                    problems.append('unsafe member ' + member)
            if not problems:
                archive.extractall(folder)
        results = list(folder.rglob('f05-host-evidence/result.json'))
        if len(results) != 1:
            problems.append('expected exactly one result.json')
        else:
            result = json.loads(results[0].read_text(encoding='utf-8'))
            requests = json.loads((results[0].parent / 'requests.json').read_text(encoding='utf-8'))
            audit['result_sha256'] = hashlib.sha256(results[0].read_bytes()).hexdigest()
            if result.get('source_sha') != args.source:
                problems.append('result source differs from this workflow source')
            if (result.get('run_id'), result.get('attempt')) != (args.run_id, args.attempt):
                problems.append('result run/attempt differs')
            if result.get('accepted') is not True or result.get('checks') != EXPECTED or result.get('count') != 11:
                problems.append('result does not carry exactly the 11 expected passing checks: %r' % (result.get('checks'),))
            for flag in ('database_planting', 'six_platform_claim', 'complete_product'):
                if result.get(flag) is not False:
                    problems.append('flag %s must be false' % flag)
            # Re-derive wire facts from the raw fixture request log.
            puts = [r for r in requests if r['method'] == 'PUT' and '/revisions/' in r['path']]
            audit['revision_put_statuses'] = [(r['peer'], r['status']) for r in puts]
            faults = sorted({r['fault'] for r in requests if r.get('fault')})
            audit['faults_observed'] = faults
            if faults != ['commit_withhold', 'gate', 'partial']:
                problems.append('fixture faults observed: %r' % faults)
            if any(r['peer'] is None for r in requests if r['status'] != 401):
                problems.append('unauthenticated request accepted')
            peerb_gets = [r for r in requests if r['peer'] == 'peerB' and r['method'] == 'GET' and '/revisions/' in r['path']
                          and r['status'] == 200]
            if not peerb_gets:
                problems.append('peerB never received a revision over GET')
            audit['request_count'] = len(requests)
    audit['accepted'] = not problems
    (out / 'audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    print(json.dumps(audit, indent=2))
    if problems:
        sys.exit(1)


if __name__ == '__main__':
    main()
