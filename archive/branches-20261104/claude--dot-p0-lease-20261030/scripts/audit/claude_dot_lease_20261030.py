#!/usr/bin/env python3
"""Independent auditor for the C01 admission lease. Never grants acceptance.
  --paths BASE   : changed paths since BASE are exactly inside the owned set.
  --receipt DIR  : receipt.json from the Actions-produced evidence is honest."""
import argparse, json, os, pathlib, subprocess, sys
BASE = '2743f32a4eccd5823657da19cb4f77f2411424af'
PREFIXES = ('extras/migration/windows_admission_lease_20261030/', 'tests/migration/windows_admission_lease_20261030/')
EXACT = {'.github/workflows/claude_dot_lease_20261030.yml', 'scripts/audit/claude_dot_lease_20261030.py',
         'docs/reader-total-progress/CLAUDE_DOT_C01_20261030.md'}
CASES = ['shared_cross_process_then_hard_kill_release', 'exclusive_blocks_all_then_graceful_release',
         'prefix32_matching_tail16_distinct_custody', 'generation_gate_stale_after_commit', 'process_death_cuts_fail_closed',
         'begin_commit_misuse_refused',
         'same_process_second_handle_conflicts', 'non_full49_identity_rejected_without_side_effect',
         'foreign_header_size_hardlink_junction_refused', 'reparse_lease_directory_refused',
         'held_lease_file_delete_and_rename_refused',
         'metadata_malformed_truncated_corrupted_fail_closed', 'interrupted_commit_states_and_kill_loop',
         'concurrent_processes_pending_intent_invariants']
def fail(m): print('AUDIT FAIL:', m); sys.exit(1)
# ---- Original-artifact qualification (self-authored by C01; NOT independent) ----
import copy, hashlib, io, warnings, zipfile
PIN = dict(repo='NoGod3524/EXReader', branch='claude/dot-p0-lease-20261030',
           source='11dca84e429d84e2ffe7b248ccc8d743c8157e67', run=41031464318, attempt=1,
           artifact=12966217138, size=11890,
           sha256='c408772332daebff89904e703d3c6708b3a40242099446d60d3a5982d1f53f5a')
MAX_MEMBERS, MAX_MEMBER, MAX_TOTAL = 50, 5 << 20, 20 << 20
class Reject(Exception): pass
def need(cond, msg):
    if not cond: raise Reject(msg)
def bind(meta, zbytes):
    run, att, art = meta['run'], meta['attempt'], meta['artifact']
    need(run.get('id') == PIN['run'], 'run id'); need(att.get('id') == PIN['run'], 'attempt run id')
    need(att.get('run_attempt') == PIN['attempt'], 'attempt number')
    for n, j in (('run', run), ('attempt', att)):
        need(j.get('head_sha') == PIN['source'], f'{n} source'); need(j.get('status') == 'completed' and j.get('conclusion') == 'success', f'{n} conclusion')
        need((j.get('repository') or {}).get('full_name') == PIN['repo'], f'{n} repository'); need(j.get('head_branch') == PIN['branch'], f'{n} branch')
    need(art.get('id') == PIN['artifact'], 'artifact id'); need(art.get('size_in_bytes') == PIN['size'], 'artifact API size')
    need(art.get('digest') == 'sha256:' + PIN['sha256'], 'artifact API digest'); need(art.get('expired') is False, 'artifact expired')
    need(art.get('name') == 'claude-dot-lease-' + PIN['source'], 'artifact name')
    wr = art.get('workflow_run') or {}
    need(wr.get('id') == PIN['run'] and wr.get('head_sha') == PIN['source'], 'artifact workflow_run binding')
    need(len(zbytes) == PIN['size'], 'zip byte size'); need(hashlib.sha256(zbytes).hexdigest() == PIN['sha256'], 'zip sha256')
def load_zip(zbytes):
    try: z = zipfile.ZipFile(io.BytesIO(zbytes))
    except zipfile.BadZipFile as ex: raise Reject(f'bad zip: {ex}')
    infos = z.infolist(); need(0 < len(infos) <= MAX_MEMBERS, 'member count')
    names = [i.filename for i in infos]; need(len(set(names)) == len(names), 'duplicate member')
    need(sum(i.file_size for i in infos) <= MAX_TOTAL, 'total size')
    for i in infos:
        n = i.filename
        need(n and not n.startswith('/') and '\\' not in n and ':' not in n and '..' not in n.split('/'), f'unsafe member {n!r}')
        need(i.file_size <= MAX_MEMBER, f'oversized member {n}')
    need(z.testzip() is None, 'crc')
    return {i.filename: z.read(i) for i in infos if not i.is_dir()}
def pick(members, suffix):
    hit = [n for n in members if n.endswith(suffix)]
    need(len(hit) == 1, f'expected exactly one {suffix}, got {hit}')
    return hit[0]
EXPECT_REFUSED = ['pending_2', 'pending_2e63', 'pending_ff', 'bad_magic', 'foreign_identity', 'missing_newline',
                  'identity_case_flip', 'padding_59', 'padding_63'] + [f'size_{s}' for s in (1, 10, 40, 58, 59, 63, 64, 72, 79, 81, 160, 4096)]
def check_receipt(r, lib):
    need(r.get('source') == PIN['source'] and str(r.get('run')) == str(PIN['run']) and str(r.get('attempt')) == str(PIN['attempt']), 'receipt identity')
    need(r.get('passed') is True and r.get('case_count') == len(CASES) == len(r.get('cases', [])), 'receipt case count')
    need([c.get('case') for c in r['cases']] == CASES, 'case set/order'); need(all(c.get('passed') is True for c in r['cases']), 'case failed')
    for k in ('recovery_admission', 'commit_acknowledged', 'full_p0_acceptance', 'physical_power_loss'): need(r.get(k) is False, k)
    need(r.get('sdk_open_attempts') == 0, 'sdk opens'); need(r.get('library_sha256') == hashlib.sha256(lib).hexdigest(), 'library hash binding')
    need(isinstance(r.get('probe_sha256'), str) and len(r['probe_sha256']) == 64, 'probe hash')
    C = {c['case']: c for c in r['cases']}
    # kill loop
    kl = C['interrupted_commit_states_and_kill_loop']; cuts = kl['cuts']
    need(len(cuts) == 12, 'kill-loop cut count'); post = []
    for c in cuts:
        need(c['pending'] in (0, 1), 'pending value'); need(c['file_generation'] >= c['acked'] >= 1, 'acked/generation')
        need(c['post_generation'] >= c['file_generation'], 'post generation'); need(c['kill_return_code'] not in (0, None), 'process not killed')
        post.append(c['post_generation'])
    need(post == sorted(post), 'post generations regress'); need(kl['pending_cuts'] == sum(c['pending'] for c in cuts), 'pending_cuts mismatch')
    # death cuts
    dc = C['process_death_cuts_fail_closed']['cuts']
    need(dc['before-begin']['shared']['status'] == 0 and dc['before-begin']['shared']['generation'] == 0, 'before-begin')
    ab = dc['after-begin']; need(ab['announced']['pending'] == 1 and ab['shared_refused']['status'] == 3 and ab['exclusive']['pending'] == 1, 'after-begin')
    need(ab['resolved']['generation'] == 1 and ab['shared_after']['status'] == 0 and ab['shared_after']['pending'] == 0, 'after-begin resolve')
    ac = dc['after-commit']; need(ac['announced']['pending'] == 0 and ac['shared']['generation'] == 1, 'after-commit')
    for k in dc: need(dc[k]['kill_return_code'] not in (0, None), f'{k} not killed')
    # metadata
    mo = C['metadata_malformed_truncated_corrupted_fail_closed']['outcomes']
    for k in EXPECT_REFUSED: need(mo.get(k) == 'refused', f'metadata {k}')
    need(mo.get('size_0') == 'initialised', 'size_0'); need(mo['interrupted_commit_resolved_monotonic']['generation'] == 2, 'interrupted resolve')
    need(len(mo) == len(EXPECT_REFUSED) + 2, 'unexpected metadata entries')
    # concurrency
    cc = C['concurrent_processes_pending_intent_invariants']
    need(len(cc['writers']) == 6 and all(w['bad'] == 0 and w['ok'] + w['busy'] == 25 for w in cc['writers']), 'writers')
    need(len(cc['readers']) == 4 and all(x['bad'] == 0 and x['stale'] == 0 and x['ok'] > 0 for x in cc['readers']), 'readers')
    need(cc['committed'] == sum(w['ok'] for w in cc['writers']) > 0, 'committed total')
    need(cc['init_race_pids'] == [8, 8, 8], 'init race processes')
    return dict(cases=len(CASES), kill_loop=[dict(acked=c['acked'], file_generation=c['file_generation'], pending=c['pending'], post=c['post_generation'], kill_rc=c['kill_return_code']) for c in cuts],
                pending_cuts=kl['pending_cuts'], metadata_refused=len(EXPECT_REFUSED), writers_ok=[w['ok'] for w in cc['writers']], writers_busy=[w['busy'] for w in cc['writers']],
                readers_ok=[x['ok'] for x in cc['readers']], committed=cc['committed'], init_race=cc['init_race_pids'])
def qualify(meta, zbytes):
    bind(meta, zbytes); m = load_zip(zbytes)
    rn, ln, hn = pick(m, 'receipt.json'), pick(m, '.lib'), pick(m, 'lm_win_lease.h')
    facts = check_receipt(json.loads(m[rn]), m[ln])
    return dict(members={n: dict(bytes=len(b), sha256=hashlib.sha256(b).hexdigest()) for n, b in sorted(m.items())}, facts=facts, receipt_member=rn)
def make_zip(entries):
    buf = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            for n, b in entries: z.writestr(n, b)
    return buf.getvalue()
def controls(meta, zbytes):
    m = load_zip(zbytes); rn, ln = pick(m, 'receipt.json'), pick(m, '.lib'); rec0 = json.loads(m[rn]); lib = m[ln]
    out = []
    def expect_reject(name, fn):
        try: fn()
        except Reject as ex: out.append(dict(control=name, rejected=True, reason=str(ex))); return
        raise SystemExit(f'AUDIT FAIL: negative control {name!r} was ACCEPTED')
    def M(path, value):
        mm = copy.deepcopy(meta); o = mm
        for k in path[:-1]: o = o[k]
        o[path[-1]] = value; return mm
    for name, mm in [('artifact id', M(['artifact', 'id'], PIN['artifact'] + 1)), ('artifact API size', M(['artifact', 'size_in_bytes'], PIN['size'] + 1)),
                     ('artifact API digest', M(['artifact', 'digest'], 'sha256:' + '0' * 64)), ('artifact source', M(['artifact', 'workflow_run', 'head_sha'], '0' * 40)),
                     ('artifact run', M(['artifact', 'workflow_run', 'id'], 1)), ('artifact expired', M(['artifact', 'expired'], True)),
                     ('run source', M(['run', 'head_sha'], '0' * 40)), ('run conclusion', M(['run', 'conclusion'], 'failure')),
                     ('attempt number', M(['attempt', 'run_attempt'], 2)), ('repository', M(['run', 'repository', 'full_name'], 'other/EXReader')),
                     ('branch', M(['run', 'head_branch'], 'main'))]:
        expect_reject('metadata: ' + name, lambda mm=mm: bind(mm, zbytes))
    flipped = bytearray(zbytes); flipped[len(flipped) // 2] ^= 1
    expect_reject('zip: bit flip (digest)', lambda: qualify(meta, bytes(flipped)))
    expect_reject('zip: truncated (size)', lambda: qualify(meta, zbytes[:-1]))
    expect_reject('zip: empty', lambda: qualify(meta, b''))
    items = sorted(m.items())
    def without(sfx): return [(n, b) for n, b in items if not n.endswith(sfx)]
    for label, entries in [('missing receipt', without('receipt.json')), ('missing library', without('.lib')), ('missing header', without('lm_win_lease.h')),
                           ('duplicate member', items + [items[0]]), ('path traversal member', items + [('../evil', b'x')]),
                           ('absolute member', items + [('/evil', b'x')]), ('backslash member', items + [('a\\b', b'x')]),
                           ('oversized member', items + [('big.bin', b'0' * (MAX_MEMBER + 1))])]:
        z2 = make_zip(entries); mm = copy.deepcopy(meta)
        def run_it(z2=z2, mm=mm):
            load_zip(z2); mp = load_zip(z2); pick(mp, 'receipt.json'); pick(mp, '.lib'); pick(mp, 'lm_win_lease.h')
        expect_reject('zip content: ' + label, run_it)
    def R(fn):
        r = copy.deepcopy(rec0); fn(r); return lambda: check_receipt(r, lib)
    def case(r, n): return next(c for c in r['cases'] if c['case'] == n)
    expect_reject('receipt: source', R(lambda r: r.__setitem__('source', '0' * 40)))
    expect_reject('receipt: run', R(lambda r: r.__setitem__('run', '1')))
    expect_reject('receipt: attempt', R(lambda r: r.__setitem__('attempt', '2')))
    expect_reject('receipt: dropped case', R(lambda r: r['cases'].pop()))
    expect_reject('receipt: reordered cases', R(lambda r: r['cases'].reverse()))
    expect_reject('receipt: case failed', R(lambda r: r['cases'][3].__setitem__('passed', False)))
    expect_reject('receipt: full_p0_acceptance true', R(lambda r: r.__setitem__('full_p0_acceptance', True)))
    expect_reject('receipt: physical_power_loss true', R(lambda r: r.__setitem__('physical_power_loss', True)))
    expect_reject('receipt: sdk opens', R(lambda r: r.__setitem__('sdk_open_attempts', 1)))
    expect_reject('receipt: library hash', R(lambda r: r.__setitem__('library_sha256', '0' * 64)))
    expect_reject('receipt: library bytes tampered', lambda: check_receipt(rec0, lib + b'x'))
    K = 'interrupted_commit_states_and_kill_loop'
    expect_reject('kill-loop: missing cut', R(lambda r: case(r, K)['cuts'].pop()))
    expect_reject('kill-loop: pending_cuts lie', R(lambda r: case(r, K).__setitem__('pending_cuts', case(r, K)['pending_cuts'] + 1)))
    expect_reject('kill-loop: process exited 0', R(lambda r: case(r, K)['cuts'][4].__setitem__('kill_return_code', 0)))
    expect_reject('kill-loop: generation regress', R(lambda r: case(r, K)['cuts'][5].__setitem__('post_generation', 0)))
    expect_reject('kill-loop: acked above file', R(lambda r: case(r, K)['cuts'][2].__setitem__('acked', case(r, K)['cuts'][2]['file_generation'] + 5)))
    expect_reject('kill-loop: bad pending value', R(lambda r: case(r, K)['cuts'][1].__setitem__('pending', 2)))
    expect_reject('death cut: after-begin shared admitted', R(lambda r: case(r, 'process_death_cuts_fail_closed')['cuts']['after-begin']['shared_refused'].__setitem__('status', 0)))
    M_ = 'metadata_malformed_truncated_corrupted_fail_closed'
    expect_reject('metadata: padding case missing', R(lambda r: case(r, M_)['outcomes'].pop('padding_59')))
    expect_reject('metadata: size case accepted', R(lambda r: case(r, M_)['outcomes'].__setitem__('size_79', 'accepted')))
    C_ = 'concurrent_processes_pending_intent_invariants'
    expect_reject('concurrency: writer bad', R(lambda r: case(r, C_)['writers'][0].__setitem__('bad', 1)))
    expect_reject('concurrency: reader saw stale', R(lambda r: case(r, C_)['readers'][1].__setitem__('stale', 1)))
    expect_reject('concurrency: generation total', R(lambda r: case(r, C_).__setitem__('committed', case(r, C_)['committed'] + 1)))
    expect_reject('concurrency: init race short', R(lambda r: case(r, C_)['init_race_pids'].__setitem__(0, 7)))
    return out
def run_qualify(raw_dir, out_dir):
    raw = pathlib.Path(raw_dir); out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=False)
    meta = {k: json.loads((raw / f'{k}.json').read_text()) for k in ('run', 'attempt', 'artifact')}
    zbytes = (raw / 'artifact.zip').read_bytes()
    try: base = qualify(meta, zbytes)
    except Reject as ex: fail(f'original artifact rejected: {ex}')
    ctl = controls(meta, zbytes)
    rep = dict(kind='c01-original-artifact-qualification', self_authored_not_independent=True, pins=PIN, zip_bytes=len(zbytes),
               zip_sha256=hashlib.sha256(zbytes).hexdigest(), qualified=base, negative_controls=ctl, negative_control_count=len(ctl),
               all_controls_rejected=all(c['rejected'] for c in ctl), publisher_integration=False, full_p0_acceptance=False, physical_power_loss=False,
               workflow_run=dict(run=os.environ.get('GITHUB_RUN_ID'), attempt=os.environ.get('GITHUB_RUN_ATTEMPT'), sha=os.environ.get('GITHUB_SHA')))
    (out / 'qualification.json').write_text(json.dumps(rep, indent=2) + '\n')
    print('facts', json.dumps(base['facts'], sort_keys=True))
    print('members', json.dumps(base['members'], sort_keys=True))
    print('qualification ok; controls rejected:', len(ctl))

ap = argparse.ArgumentParser(); ap.add_argument('--paths'); ap.add_argument('--receipt'); ap.add_argument('--qualify'); ap.add_argument('--out'); a = ap.parse_args()
if a.qualify:
    if not a.out: fail('--out required')
    run_qualify(a.qualify, a.out)
if a.paths:
    anc = subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'])
    if anc.returncode: fail('exact base is not an ancestor of HEAD')
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASE, 'HEAD'], text=True).splitlines()
    bad = [p for p in changed if not (p.startswith(PREFIXES) or p in EXACT)]
    if not changed or bad: fail(f'paths outside owned set: {bad}')
    print('paths ok', len(changed))
if a.receipt:
    r = json.loads((pathlib.Path(a.receipt) / 'receipt.json').read_text())
    if r['source'] != os.environ['GITHUB_SHA'] or r['run'] != os.environ['GITHUB_RUN_ID']: fail('source/run mismatch')
    if r['passed'] is not True or [c['case'] for c in r['cases']] != CASES or r['case_count'] != len(CASES): fail('case set')
    if not all(c['passed'] is True for c in r['cases']): fail('case failed')
    for k in ('recovery_admission', 'commit_acknowledged', 'full_p0_acceptance', 'physical_power_loss'):
        if r[k] is not False: fail(f'{k} must be false')
    if r['sdk_open_attempts'] != 0 or len(r['probe_sha256']) != 64 or len(r['library_sha256']) != 64: fail('identity')
    print('receipt ok; cases', len(CASES), '; not P0 acceptance')
