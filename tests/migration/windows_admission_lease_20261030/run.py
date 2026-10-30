"""Actions-only cross-process acceptance of the Windows admission lease.
Grants no migration admission, SDK open, publication or commit acknowledgement."""
import argparse, concurrent.futures, hashlib, json, os, pathlib, subprocess
p = argparse.ArgumentParser(); p.add_argument('--probe', required=True); p.add_argument('--lib', required=True)
p.add_argument('--work', required=True); a = p.parse_args()
probe = str(pathlib.Path(a.probe).resolve()); work = pathlib.Path(a.work).resolve(); work.mkdir(parents=True, exist_ok=False)
OK, INVALID, BUSY, STALE, REFUSED, NATIVE = 0, 1, 2, 3, 4, 5
cases = []
def rec(name, **kw):
    cases.append(dict(case=name, passed=True, **kw))
def run(*args, timeout=30):
    r = subprocess.run([probe, *map(str, args)], text=True, capture_output=True, timeout=timeout)
    try: data = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception: data = {'raw': r.stdout, 'stderr': r.stderr}
    return r.returncode, data
def hold(d, ident, mode):
    proc = subprocess.Popen([probe, 'hold', str(d), ident, mode], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(proc.stdout.readline)
        try: line = fut.result(timeout=30)
        except BaseException:
            proc.kill(); proc.wait(timeout=10); raise
    data = json.loads(line)
    assert data['status'] == OK, data
    return proc, data
def kill(proc):
    proc.kill(); proc.wait(timeout=10); return proc.returncode
def say(proc, text):
    proc.stdin.write(text); proc.stdin.flush()
A = 'a' * 32 + '0123456789abcdef'
B = 'a' * 32 + 'fedcba9876543210'   # same prefix32, different tail16
C = '0123456789abcdef' * 3
d = work / 'leases'; d.mkdir()
def status(rc_data, expect, what):
    rc, data = rc_data
    assert data.get('status') == expect, (what, rc, data)
    return data

# 1 shared custody across processes: several hold, exclusive refused, hard kill releases
holders = [hold(d, A, 'shared') for _ in range(4)]
pids = [h[1]['pid'] for h in holders]; assert len(set(pids)) == 4
status(run('try', d, A, 'shared', 0), OK, 'fifth shared')
busy = status(run('try', d, A, 'exclusive', 200), BUSY, 'exclusive vs shared')
for h in holders: say(h[0], 'check\n'); assert json.loads(h[0].stdout.readline())['status'] == OK
codes = [kill(h[0]) for h in holders]
exc = status(run('try', d, A, 'exclusive', 3000), OK, 'exclusive after hard kill')
rec('shared_cross_process_then_hard_kill_release', holder_pids=pids, kill_return_codes=codes, exclusive_busy_native=busy['native'], exclusive_after_kill=exc)

# 2 exclusive custody and graceful release
proc, info = hold(d, A, 'exclusive')
status(run('try', d, A, 'shared', 0), BUSY, 'shared vs exclusive')
status(run('try', d, A, 'exclusive', 0), BUSY, 'exclusive vs exclusive')
say(proc, 'release\n'); assert proc.wait(timeout=10) == 0
status(run('try', d, A, 'shared', 0), OK, 'shared after graceful release')
rec('exclusive_blocks_all_then_graceful_release', holder_pid=info['pid'])

# 3 distinct full49 identities are independent; prefix32 never aliases
proc, info = hold(d, A, 'exclusive')
status(run('try', d, B, 'exclusive', 0), OK, 'same-prefix different tail')
leases = sorted(x.name for x in d.iterdir())
assert f'{A}.lease' in leases and f'{B}.lease' in leases and len(leases) == 2, leases
status(run('try', d, A, 'shared', 0), BUSY, 'full identity still conflicts')
kill(proc)
rec('prefix32_matching_tail16_distinct_custody', files=leases)

# 4 generation / admit-reopen gate (begin -> commit)
g0 = status(run('try', d, C, 'shared', 0), OK, 'fresh')['generation']; assert g0 == 0
proc, _ = hold(d, C, 'shared')
status(run('publish', d, C, 'none'), BUSY, 'publish while shared held')
kill(proc)
done = status(run('publish', d, C, 'none'), OK, 'full begin/commit'); assert done['generation'] == 1 and done['pending'] == 0
status(run('expect', d, C, 0), STALE, 'stale admission after commit')
status(run('expect', d, C, 1), OK, 'current admission')
status(run('expect', d, A, 0), OK, 'other identity unaffected')
rec('generation_gate_stale_after_commit', commit=done)

# 4b hard process-death cuts around begin/commit: unacknowledged intent fails closed
def cut(ident, point):
    proc = subprocess.Popen([probe, 'publish', str(d), ident, point], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(proc.stdout.readline)
        try: line = fut.result(timeout=30)
        except BaseException:
            proc.kill(); proc.wait(timeout=10); raise
    ann = json.loads(line); assert ann['status'] == OK, ann
    code = kill(proc)
    return ann, code
cuts = {}
X = '2' * 48
ann, code = cut(X, 'before-begin'); assert ann['pending'] == 0
s1 = status(run('try', d, X, 'shared', 3000), OK, 'shared after pre-begin death'); assert s1['generation'] == 0 and s1['pending'] == 0
cuts['before-begin'] = dict(announced=ann, kill_return_code=code, shared=s1)
Y = '3' * 48
ann, code = cut(Y, 'after-begin'); assert ann['pending'] == 1
s_stale = status(run('try', d, Y, 'shared', 3000), STALE, 'shared after post-begin death')
status(run('expect', d, Y, 0), STALE, 'expect after post-begin death')
ex = status(run('try', d, Y, 'exclusive', 3000), OK, 'exclusive sees intent'); assert ex['pending'] == 1 and ex['generation'] == 0
res = status(run('resolve', d, Y), OK, 'exclusive re-qualification commit'); assert res['generation'] == 1
s2 = status(run('try', d, Y, 'shared', 0), OK, 'shared after resolve'); assert s2['generation'] == 1 and s2['pending'] == 0
cuts['after-begin'] = dict(announced=ann, kill_return_code=code, shared_refused=s_stale, exclusive=ex, resolved=res, shared_after=s2)
Z = '4' * 48
ann, code = cut(Z, 'after-commit'); assert ann['pending'] == 0 and ann['generation'] == 1
s3 = status(run('try', d, Z, 'shared', 3000), OK, 'shared after committed death'); assert s3['generation'] == 1 and s3['pending'] == 0
cuts['after-commit'] = dict(announced=ann, kill_return_code=code, shared=s3)
rec('process_death_cuts_fail_closed', cuts=cuts)

rc, data = run('misuse', d, '5' * 48); assert rc == 0 and data['misuse'] == 1, data
rec('begin_commit_misuse_refused')
# 5 in-process handles also conflict
rc, data = run('selfconflict', d, 'b' * 48); assert rc == 0 and data['selfconflict'] == 1, data
rec('same_process_second_handle_conflicts')

# 6 invalid identities refused and create nothing
before = sorted(x.name for x in d.iterdir())
for bad in ['A' * 48, 'a' * 47, 'a' * 49, 'g' * 48, 'a' * 32 + '0123456789abcdeF', '..\\\\' + 'a' * 45]:
    rc, data = run('try', d, bad, 'shared', 0)
    status((rc, data), INVALID, f'identity {bad!r}')
assert sorted(x.name for x in d.iterdir()) == before
rec('non_full49_identity_rejected_without_side_effect', count=6)

# 7 hostile lease state fails closed
e = 'c' * 48
(d / f'{e}.lease').write_bytes(b'x' * 80); status(run('try', d, e, 'shared', 0), REFUSED, 'foreign header')
f = 'd' * 48
(d / f'{f}.lease').write_bytes(b'short'); status(run('try', d, f, 'shared', 0), REFUSED, 'size mismatch')
g = 'e' * 48
status(run('try', d, g, 'shared', 0), OK, 'create'); os.link(d / f'{g}.lease', work / 'alias.lease')
status(run('try', d, g, 'shared', 0), REFUSED, 'hard link')
h = '1' * 48
target = work / 'junction-target'; target.mkdir()
subprocess.run(['cmd', '/c', 'mklink', '/J', str(d / f'{h}.lease'), str(target)], check=True, capture_output=True)
rc, data = run('try', d, h, 'shared', 0); assert data['status'] != OK, data
rec('foreign_header_size_hardlink_junction_refused', junction_status=data['status'], junction_native=data['native'])

# 8 lease directory that is a junction is refused
real = work / 'real-dir'; real.mkdir(); jd = work / 'dir-junction'
subprocess.run(['cmd', '/c', 'mklink', '/J', str(jd), str(real)], check=True, capture_output=True)
rc, data = run('try', jd, 'f' * 48, 'shared', 0); assert data['status'] == REFUSED and not list(real.iterdir()), data
rec('reparse_lease_directory_refused')

# 9 pinned: held lease cannot be removed or renamed by another process
proc, _ = hold(d, A, 'shared')
for op in (lambda: os.remove(d / f'{A}.lease'), lambda: os.rename(d / f'{A}.lease', d / 'moved')):
    try: op(); raise AssertionError('lease file removed while held')
    except PermissionError: pass
    except OSError: pass
assert (d / f'{A}.lease').exists()
kill(proc)
rec('held_lease_file_delete_and_rename_refused')

receipt = dict(source=os.environ['GITHUB_SHA'], run=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
               passed=True, case_count=len(cases), cases=cases,
               probe_sha256=hashlib.sha256(pathlib.Path(probe).read_bytes()).hexdigest(),
               library_sha256=hashlib.sha256(pathlib.Path(a.lib).read_bytes()).hexdigest(),
               sdk_open_attempts=0, recovery_admission=False, commit_acknowledged=False,
               full_p0_acceptance=False, physical_power_loss=False)
(work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')

