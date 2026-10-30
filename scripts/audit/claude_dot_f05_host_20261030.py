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

LIVE_EXPECTED = [
    'live_peerA_pushes_exact_history_while_peerB_process_is_alive_and_untouched',
    'live_peerB_receives_same_revisions_by_get_while_peerA_process_is_alive',
    'live_peerB_imports_identical_original_and_keeps_received_history',
    'live_both_hosts_make_distinct_offline_children_of_one_received_head',
    'live_two_account_sessions_are_in_flight_on_the_server_simultaneously',
    'live_peers_converge_on_identical_sibling_heads_titles_unselected_and_wire_history',
    'live_group_created_in_peerA_ui_reaches_peerB_history_over_wire',
    'live_group_remove_tombstone_in_peerA_ui_propagates_over_wire_to_peerB',
    'live_group_restore_in_peerA_ui_propagates_over_wire_and_clears_peerB_tombstone',
    None,
    'credentials_and_authorization_are_absent_from_evidence_and_wire_bodies',
]
LIVE_TENTH = {'live_delete_versus_update_conflict_blocked_peerB_ui_does_not_project_received_group',
              'live_delete_versus_update_conflict_converges_without_selection_or_data_loss'}


def gh(*arguments, output=None):
    command = ['gh', 'api', *arguments]
    if output:
        with open(output, 'wb') as handle:
            subprocess.run(command, stdout=handle, check=True, timeout=300)
        return None
    return json.loads(subprocess.run(command, capture_output=True, check=True, timeout=120).stdout)


def main():
    if sys.argv[1:2] == ['verify-original']:
        return verify_original(sys.argv[2:])
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
        lives = list(folder.rglob('f05-host-live-evidence/result.json'))
        if len(lives) != 1:
            problems.append('expected exactly one live result.json')
        else:
            live = json.loads(lives[0].read_text(encoding='utf-8'))
            lreq = json.loads((lives[0].parent / 'requests.json').read_text(encoding='utf-8'))
            audit['live_result_sha256'] = hashlib.sha256(lives[0].read_bytes()).hexdigest()
            if live.get('source_sha') != args.source or (live.get('run_id'), live.get('attempt')) != (args.run_id, args.attempt):
                problems.append('live result identity differs')
            names = live.get('checks') or []
            shape = [n if i != 9 else None for i, n in enumerate(names)]
            if live.get('accepted') is not True or live.get('count') != 11 or shape != LIVE_EXPECTED or \
                    len(names) != 11 or names[9] not in LIVE_TENTH:
                problems.append('live result does not carry the expected 11 passing checks: %r' % (names,))
            for flag in ('database_planting', 'six_platform_claim', 'complete_product'):
                if live.get(flag) is not False:
                    problems.append('live flag %s must be false' % flag)
            gates = [r for r in lreq if r.get('fault') == 'gate']
            if sorted(r['peer'] for r in gates) != ['peerA', 'peerB']:
                problems.append('live gates were not hit once by each peer')
            tombs = [r for r in lreq if r['method'] == 'PUT' and r['status'] == 201 and '/revisions/' in r['path']]
            audit['live'] = {'checks': names, 'request_count': len(lreq), 'revision_puts_201': len(tombs),
                             'tenth': names[9] if len(names) > 9 else None,
                             'group_ui_projected_in_peerB': live.get('group_ui_projected_in_peerB'),
                             'pids': {k: v.get('pid') for k, v in (live.get('peers') or {}).items()}}
    audit['accepted'] = not problems
    (out / 'audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    print(json.dumps(audit, indent=2))
    if problems:
        sys.exit(1)


# ---------------------------------------------------------------------------
# verify-original: pinned, fail-closed re-verification of run 41027848917 with negative controls.
# Authorship: this verifier is written by the same author as the harness it checks. It authenticates identity and
# re-derives wire facts from the raw logs; it is not independent authorship and not an independent oracle.
# ---------------------------------------------------------------------------
PIN = {
    'repo': 'NoGod3524/EXReader', 'run_id': 41027848917, 'attempt': 1,
    'source': 'd939a2115f893a04d279ce526feba3ebfe7b4fea', 'branch': 'claude/dot-f05-host-20261030',
    'artifact_id': 12964756717, 'artifact_name': 'claude-dot-f05-host-41027848917-1',
    'zip_sha256': '7b1a7cb386dfc53a17fa398d17e022547a4dbe8c78804e903799bb2d8f1de8eb',
    'workflow_path': '.github/workflows/claude_dot_f05_host_20261030.yml',
    'workflow_name': 'Claude Dot F05 real-host two-peer wire recovery',
}
GAPS = ['GTK (Linux) host only: no Windows, Apple or Android host and no six-platform claim',
        'delete-versus-update is unproven: peerB UI does not project the received group (group_ui_projected_in_peerB=false)',
        'book delete has no host UI, so book tombstones are untested',
        'the verifier shares authorship with the harness: identity and consistency check, not independent authorship']


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _member(members, suffix):
    found = [k for k in members if k.endswith(suffix)]
    return found[0] if len(found) == 1 else None


def _load(members, suffix, problems, tag):
    name = _member(members, suffix)
    if name is None:
        problems.append('%s: missing or ambiguous member %s' % (tag, suffix))
        return None
    try:
        return json.loads(members[name].decode('utf-8'))
    except ValueError:
        problems.append('%s: unparsable %s' % (tag, suffix))
        return None


def verify_bundle(ctx):
    """Return the list of problems for one candidate bundle; empty means every pinned claim held."""
    problems = []
    run, art, blob, members = ctx['run'], ctx['artifact'], ctx['zip'], ctx['members']
    # identity
    expect = {'head_sha': PIN['source'], 'run_attempt': PIN['attempt'], 'id': PIN['run_id'],
              'head_branch': PIN['branch'], 'name': PIN['workflow_name'], 'status': 'completed',
              'conclusion': 'success'}
    for key, value in expect.items():
        if run.get(key) != value:
            problems.append('identity: run %s is %r, pinned %r' % (key, run.get(key), value))
    if not str(run.get('path', '')).startswith(PIN['workflow_path']):
        problems.append('identity: workflow path %r' % run.get('path'))
    if (run.get('repository') or {}).get('full_name') != PIN['repo']:
        problems.append('identity: repository differs')
    if art.get('id') != PIN['artifact_id'] or art.get('name') != PIN['artifact_name'] or art.get('expired'):
        problems.append('identity: artifact id/name/expiry differ or expired')
    if (art.get('workflow_run') or {}).get('head_sha') != PIN['source'] or \
            (art.get('workflow_run') or {}).get('id') != PIN['run_id']:
        problems.append('identity: artifact is not bound to the pinned run/source')
    # digest
    if _sha(blob) != PIN['zip_sha256']:
        problems.append('digest: ZIP bytes do not hash to the pinned SHA-256')
    if art.get('digest') != 'sha256:' + PIN['zip_sha256']:
        problems.append('digest: API artifact digest differs from the pin')
    if art.get('size_in_bytes') != len(blob):
        problems.append('digest: API size differs from the ZIP length')
    orig = _load(members, 'f05-host-evidence/result.json', problems, 'identity')
    live = _load(members, 'f05-host-live-evidence/result.json', problems, 'identity')
    oreq = _load(members, 'f05-host-evidence/requests.json', problems, 'wire')
    lreq = _load(members, 'f05-host-live-evidence/requests.json', problems, 'wire')
    lwire = _load(members, 'f05-host-live-evidence/wire.json', problems, 'wire')
    if None in (orig, live, oreq, lreq, lwire):
        return problems
    for tag, result, names in (('original', orig, EXPECTED), ('live', live, None)):
        if result.get('source_sha') != PIN['source'] or str(result.get('run_id')) != str(PIN['run_id']) or \
                str(result.get('attempt')) != str(PIN['attempt']):
            problems.append('identity: %s result source/run/attempt differ from the pin' % tag)
        if result.get('accepted') is not True or result.get('runner_os') != 'Linux':
            problems.append('identity: %s result not accepted on Linux' % tag)
        for flag in ('database_planting', 'six_platform_claim', 'complete_product'):
            if result.get(flag) is not False:
                problems.append('identity: %s flag %s must be false' % (tag, flag))
        if names is not None and result.get('checks') != names:
            problems.append('identity: original checks differ from the preserved 11')
    if live.get('count') != 11 or len(live.get('checks') or []) != 11 or \
            [c if i != 9 else None for i, c in enumerate(live['checks'])] != LIVE_EXPECTED or \
            live['checks'][9] not in LIVE_TENTH:
        problems.append('identity: live checks differ from the expected 11')
    if live.get('group_ui_projected_in_peerB') is not False or \
            live['checks'][9:10] != ['live_delete_versus_update_conflict_blocked_peerB_ui_does_not_project_received_group']:
        problems.append('identity: recorded delete-versus-update gap is absent')
    if orig.get('program_sha256') != live.get('program_sha256'):
        problems.append('identity: host binary hash differs between original and live results')
    for tag, result in (('original', orig), ('live', live)):
        build = _member(members, 'f05-package/build.json')
        consumer = _member(members, 'f05-revision-consumer/revision-consumer')
        if build is None or _sha(members[build]) != result.get('build_json_sha256'):
            problems.append('identity: %s build.json hash is not bound' % tag)
        if consumer is None or _sha(members[consumer]) != result.get('revision_consumer_sha256'):
            problems.append('identity: %s revision consumer hash is not bound' % tag)
    # original wire facts
    puts = [r for r in oreq if r['method'] == 'PUT' and '/revisions/' in r['path']]
    statuses = [(r['peer'], r['status']) for r in puts]
    if ('peerB', 'partial-reset') not in statuses or ('peerB', 'committed-unanswered') not in statuses:
        problems.append('wire: original partial-body or commit-withheld PUT evidence missing')
    elif statuses.index(('peerB', 412)) < statuses.index(('peerB', 'committed-unanswered')) if ('peerB', 412) in statuses else True:
        problems.append('wire: original idempotent 412 after the committed PUT is missing')
    if sorted({r['fault'] for r in oreq if r.get('fault')}) != ['commit_withhold', 'gate', 'partial']:
        problems.append('wire: original fault set differs')
    # live overlap, re-derived only from request order
    gates = sorted((r for r in lreq if r.get('fault') == 'gate'), key=lambda r: r['n'])
    if len(gates) != 2 or {g['peer'] for g in gates} != {'peerA', 'peerB'}:
        problems.append('overlap: the two peers did not each hit a gate')
    else:
        first, second = gates
        later = sorted((r for r in lreq if r['peer'] == first['peer'] and r['n'] > first['n']), key=lambda r: r['n'])
        if not later or not first['n'] < second['n'] < later[0]['n']:
            problems.append('overlap: second peer did not reach its gate before the first peer resumed')
        later2 = [r for r in lreq if r['peer'] == second['peer'] and r['n'] > second['n']]
        if not later2 or min(r['n'] for r in later2) < max(g['n'] for g in gates):
            problems.append('overlap: second peer resumed before both gates were held')
    # live wire evidence: every claimed revision is on the wire, authored by one peer and fetched by the other
    claimed = set()
    for name, evidence in (live.get('observations') or {}).items():
        for rid in (evidence.get('revisions') or []) + (evidence.get('tombstone') or []):
            claimed.add(rid)
    if len(claimed) < 6:
        problems.append('wire: too few claimed revisions in the live result (%d)' % len(claimed))
    tombstones = set((live.get('observations') or {}).get(
        'live_group_remove_tombstone_in_peerA_ui_propagates_over_wire_to_peerB', {}).get('tombstone') or [])
    if not tombstones:
        problems.append('wire: no tombstone revision is claimed')
    paths = {}
    for path, digest in lwire.items():
        if '/revisions/' in path:
            paths[path.rsplit('/', 1)[1].split('-', 1)[0]] = (path, digest)
    for rid in sorted(claimed):
        if rid not in paths:
            problems.append('wire: claimed revision %s is absent from wire.json' % rid)
            continue
        path, digest = paths[rid]
        if not path.endswith('-' + digest + '.json'):
            problems.append('wire: revision %s file name does not carry its body SHA-256' % rid)
        wrote = [r for r in lreq if r['method'] == 'PUT' and r['path'] == path and r['status'] == 201]
        if len(wrote) != 1:
            problems.append('wire: revision %s has %d accepted PUTs' % (rid, len(wrote)))
            continue
        readers = [r for r in lreq if r['method'] == 'GET' and r['path'] == path and r['status'] == 200
                   and r['peer'] not in (None, wrote[0]['peer'])]
        if not readers:
            problems.append('wire: revision %s was never fetched by the other peer' % rid)
    for rid in tombstones:
        if rid in paths:
            wrote = [r for r in lreq if r['method'] == 'PUT' and r['path'] == paths[rid][0] and r['status'] == 201]
            if wrote and wrote[0]['peer'] != 'peerA':
                problems.append('wire: tombstone %s was not authored by peerA' % rid)
    return problems


def _mutated(ctx, mutate):
    clone = {'run': json.loads(json.dumps(ctx['run'])), 'artifact': json.loads(json.dumps(ctx['artifact'])),
             'zip': ctx['zip'], 'members': dict(ctx['members'])}
    mutate(clone)
    return clone


def _edit_json(clone, suffix, edit):
    name = _member(clone['members'], suffix)
    value = json.loads(clone['members'][name].decode('utf-8'))
    edit(value)
    clone['members'][name] = json.dumps(value).encode('utf-8')


def negative_controls(ctx):
    live = 'f05-host-live-evidence/'

    def flip(clone):
        data = bytearray(clone['zip'])
        data[len(data) // 2] ^= 1
        clone['zip'] = bytes(data)

    def tombstone_paths(value):
        return [p for p in value if '/revisions/' in p]

    def drop_tombstone_wire(clone):
        res = json.loads(ctx['members'][_member(ctx['members'], live + 'result.json')].decode('utf-8'))
        rid = res['observations']['live_group_remove_tombstone_in_peerA_ui_propagates_over_wire_to_peerB']['tombstone'][0]
        _edit_json(clone, live + 'wire.json', lambda w: [w.pop(p) for p in [p for p in w if rid in p]])

    def drop_tombstone_get(clone):
        res = json.loads(ctx['members'][_member(ctx['members'], live + 'result.json')].decode('utf-8'))
        rid = res['observations']['live_group_remove_tombstone_in_peerA_ui_propagates_over_wire_to_peerB']['tombstone'][0]
        _edit_json(clone, live + 'requests.json',
                   lambda r: r.__setitem__(slice(None), [x for x in r if not (x['method'] == 'GET' and rid in x['path'])]))

    def drop_tombstone_put(clone):
        res = json.loads(ctx['members'][_member(ctx['members'], live + 'result.json')].decode('utf-8'))
        rid = res['observations']['live_group_remove_tombstone_in_peerA_ui_propagates_over_wire_to_peerB']['tombstone'][0]
        _edit_json(clone, live + 'requests.json',
                   lambda r: r.__setitem__(slice(None), [x for x in r if not (x['method'] == 'PUT' and rid in x['path'])]))

    def corrupt_wire_digest(clone):
        def edit(w):
            path = tombstone_paths(w)[0]
            w[path] = '0' * 64
        _edit_json(clone, live + 'wire.json', edit)

    def remove_gate(clone):
        def edit(r):
            gates = [x for x in r if x.get('fault') == 'gate' and x['peer'] == 'peerB']
            r.remove(gates[-1])
        _edit_json(clone, live + 'requests.json', edit)

    def serialise_gates(clone):
        def edit(r):
            first = min((x for x in r if x.get('fault') == 'gate'), key=lambda x: x['n'])
            second = max((x for x in r if x.get('fault') == 'gate'), key=lambda x: x['n'])
            second['n'] = 10 ** 9
            first['n'] = first['n']
        _edit_json(clone, live + 'requests.json', edit)

    def drop_all_gate_marks(clone):
        _edit_json(clone, live + 'requests.json',
                   lambda r: [x.__setitem__('fault', None) for x in r if x.get('fault') == 'gate'])

    def result_edit(field, value):
        def mutate(clone):
            _edit_json(clone, live + 'result.json', lambda v: v.__setitem__(field, value))
        return mutate

    def set_run(field, value):
        return lambda clone: clone['run'].__setitem__(field, value)

    def set_art(field, value):
        return lambda clone: clone['artifact'].__setitem__(field, value)

    def drop_group_gap(clone):
        _edit_json(clone, live + 'result.json', lambda v: v.__setitem__('group_ui_projected_in_peerB', True))

    cases = [
        ('identity', 'live result source_sha replaced', result_edit('source_sha', 'f' * 40)),
        ('identity', 'live result run_id changed', result_edit('run_id', '41027848918')),
        ('identity', 'live result attempt changed', result_edit('attempt', '2')),
        ('identity', 'API run head_sha changed', set_run('head_sha', 'e' * 40)),
        ('identity', 'API run attempt changed', set_run('run_attempt', 2)),
        ('identity', 'API artifact bound to another source', lambda c: c['artifact'].__setitem__('workflow_run', {'id': 1, 'head_sha': 'e' * 40})),
        ('identity', 'API workflow path changed', set_run('path', '.github/workflows/other.yml')),
        ('digest', 'one ZIP byte flipped', flip),
        ('digest', 'API digest altered', set_art('digest', 'sha256:' + '0' * 64)),
        ('digest', 'API size altered', set_art('size_in_bytes', 1)),
        ('overlap', 'peerB gate row removed', remove_gate),
        ('overlap', 'peerB gate moved after peerA resumed', serialise_gates),
        ('overlap', 'gate markers erased', drop_all_gate_marks),
        ('wire', 'tombstone revision removed from wire.json', drop_tombstone_wire),
        ('wire', 'tombstone GET by the other peer removed', drop_tombstone_get),
        ('wire', 'tombstone PUT removed', drop_tombstone_put),
        ('wire', 'wire.json digest of a revision corrupted', corrupt_wire_digest),
        ('identity', 'recorded delete-versus-update gap erased', drop_group_gap),
    ]
    table = []
    for tag, label, mutate in cases:
        problems = verify_bundle(_mutated(ctx, mutate))
        hit = [p for p in problems if p.startswith(tag + ':')]
        table.append({'class': tag, 'mutation': label, 'rejected': bool(hit), 'problems': problems[:4]})
    return table


def verify_original(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    out = Path(args.output)
    out.mkdir(parents=True)
    record = {'mode': 'verify-original', 'pin': PIN, 'authorship': GAPS[3], 'gaps': GAPS, 'accepted': False,
              'problems': []}
    code = 1
    try:
        repo = PIN['repo']
        run = gh('repos/%s/actions/runs/%d/attempts/%d' % (repo, PIN['run_id'], PIN['attempt']))
        listing = gh('repos/%s/actions/runs/%d/artifacts?per_page=100' % (repo, PIN['run_id']))
        arts = [a for a in listing['artifacts'] if a['id'] == PIN['artifact_id']]
        if len(arts) != 1:
            raise SystemExit('fail closed: pinned artifact %d is not available' % PIN['artifact_id'])
        zip_path = out / 'original.zip'
        gh('repos/%s/actions/artifacts/%d/zip' % (repo, PIN['artifact_id']), output=zip_path)
        blob = zip_path.read_bytes()
        folder = out / 'extracted'
        folder.mkdir()
        members = {}
        with zipfile.ZipFile(zip_path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                target = (folder / info.filename).resolve()
                if folder.resolve() not in target.parents:
                    raise SystemExit('fail closed: unsafe ZIP member ' + info.filename)
                members[info.filename] = archive.read(info)
            archive.extractall(folder)
        ctx = {'run': run, 'artifact': arts[0], 'zip': blob, 'members': members}
        positive = verify_bundle(ctx)
        record.update(zip={'bytes': len(blob), 'sha256': _sha(blob)}, positive_control_problems=positive,
                      member_count=len(members),
                      api={'run': {k: run.get(k) for k in ('id', 'run_attempt', 'head_sha', 'head_branch', 'name', 'path',
                                                           'event', 'status', 'conclusion')},
                           'artifact': {k: arts[0].get(k) for k in ('id', 'name', 'size_in_bytes', 'digest', 'created_at')}})
        table = negative_controls(ctx) if not positive else []
        record['negative_controls'] = table
        survivors = [t for t in table if not t['rejected']]
        record['problems'] = list(positive) + ['negative control not rejected: %s' % t['mutation'] for t in survivors]
        if not table and not positive:
            record['problems'].append('no negative controls ran')
        record['accepted'] = not record['problems']
        code = 0 if record['accepted'] else 1
    except SystemExit as stop:
        record['problems'].append(str(stop))
    except Exception as error:  # fail closed: any unexpected evidence problem rejects
        record['problems'].append('fail closed: %s: %s' % (type(error).__name__, error))
    (out / 'verify.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps(record, indent=2))
    sys.exit(code)


if __name__ == '__main__':
    main()
