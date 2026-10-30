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

# 10 malformed / truncated / corrupted metadata fails closed and is never modified
import struct
MAXU = 2**64 - 1
def craft(ident, gen=0, pending=0, mutate=None, size=None):
    b = bytearray((b'EXRLEASE1\n' + ident.encode() + b'\n').ljust(64, b'\0') + struct.pack('<QQ', gen, pending))
    if mutate: mutate(b)
    if size is not None: b = b[:size] if size <= len(b) else b + bytearray(size - len(b))
    return bytes(b)
def put(ident, data):
    f = d / f'{ident}.lease'
    if f.exists(): f.unlink()
    f.write_bytes(data); return f
def refused_both(ident, data, name):
    f = put(ident, data)
    for mode in ('shared', 'exclusive'):
        status(run('try', d, ident, mode, 0), REFUSED, f'{name} {mode}')
    assert f.read_bytes() == data, f'{name}: refusal modified the lease file'
    f.unlink()  # a leaked handle/lock would make this fail on Windows
meta = {}
n = 0
def mid():
    global n; n += 1; return f'{n:02x}' * 24
for name, data_fn in {
    'pending_2': lambda i: craft(i, 0, 2),
    'pending_2e63': lambda i: craft(i, 0, 2**63),
    'pending_ff': lambda i: craft(i, 5, MAXU),
    'bad_magic': lambda i: craft(i, mutate=lambda b: b.__setitem__(0, ord('Y'))),
    'foreign_identity': lambda i: craft('9' * 48),
    'missing_newline': lambda i: craft(i, mutate=lambda b: b.__setitem__(58, ord(' '))),
    'identity_case_flip': lambda i: craft(i, mutate=lambda b: b.__setitem__(10, ord(i[0].upper()) if i[0].isalpha() else ord('X'))),
    'padding_59': lambda i: craft(i, mutate=lambda b: b.__setitem__(59, 1)),
    'padding_63': lambda i: craft(i, mutate=lambda b: b.__setitem__(63, 0x80)),
}.items():
    i = mid(); refused_both(i, data_fn(i), name); meta[name] = 'refused'
for size in (1, 10, 40, 58, 59, 63, 64, 72, 79, 81, 160, 4096):
    i = mid(); refused_both(i, craft(i, size=size), f'size_{size}'); meta[f'size_{size}'] = 'refused'
# zero-length (interrupted before first write) is initialised, not refused
i = mid(); put(i, b'')
z = status(run('try', d, i, 'shared', 0), OK, 'zero-length'); assert z['generation'] == 0 and z['pending'] == 0
assert (d / f'{i}.lease').read_bytes() == craft(i) and len(craft(i)) == 80
meta['size_0'] = 'initialised'
# pending=1 : shared STALE, exclusive sees it
i = mid(); f = put(i, craft(i, 3, 1))
status(run('try', d, i, 'shared', 0), STALE, 'pending shared')
x = status(run('try', d, i, 'exclusive', 0), OK, 'pending exclusive'); assert x['pending'] == 1 and x['generation'] == 3
assert f.read_bytes() == craft(i, 3, 1)
# interrupted commit (generation written, pending not yet cleared): still fail closed, then monotonic
i = mid(); put(i, craft(i, 1, 1))
status(run('try', d, i, 'shared', 0), STALE, 'interrupted commit shared')
r = status(run('resolve', d, i), OK, 'resolve interrupted commit'); assert r['generation'] == 2
s = status(run('try', d, i, 'shared', 0), OK, 'after resolve'); assert s['generation'] == 2 and s['pending'] == 0
meta['interrupted_commit_resolved_monotonic'] = r
# generation exhaustion: pending stays, file unchanged
i = mid(); f = put(i, craft(i, MAXU, 1))
status(run('resolve', d, i), REFUSED, 'exhausted commit')
assert f.read_bytes() == craft(i, MAXU, 1)
status(run('try', d, i, 'shared', 0), STALE, 'exhausted still pending')
i = mid(); put(i, craft(i, MAXU, 0))
mx = status(run('try', d, i, 'shared', 0), OK, 'max generation readable'); assert mx['generation'] == MAXU
rec('metadata_malformed_truncated_corrupted_fail_closed', outcomes=meta)

# 11 hard-killed begin/commit loop: invariants after every cut
import random
random.seed(20261030)
L = 'c1' * 24
loop_results = []
for k in [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233]:
    proc = subprocess.Popen([probe, 'loop', str(d), L], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    last = None
    for _ in range(k):
        line = proc.stdout.readline(); assert line, proc.stderr.read()
        last = int(line)
    code = kill(proc)
    raw = (d / f'{L}.lease').read_bytes()
    assert len(raw) == 80 and raw[:64] == craft(L)[:64], 'header damaged by kill'
    gen, pend = struct.unpack('<QQ', raw[64:])
    assert pend in (0, 1), pend
    assert last <= gen <= last + 1 + 100000, (last, gen)  # pipe buffering: child may be ahead of reader
    st = run('try', d, L, 'shared', 3000)[1]
    if pend: assert st['status'] == STALE, st
    else: assert st['status'] == OK and st['generation'] == gen and st['pending'] == 0, st
    if pend: status(run('resolve', d, L), OK, 'resolve after kill'); post = status(run('try', d, L, 'shared', 0), OK, 'after resolve')
    else: post = st
    assert post['generation'] >= gen and post['pending'] == 0
    loop_results.append(dict(acked=last, file_generation=gen, pending=pend, kill_return_code=code, post_generation=post['generation']))
assert [r['post_generation'] for r in loop_results] == sorted(r['post_generation'] for r in loop_results)
rec('interrupted_commit_states_and_kill_loop', cuts=loop_results, pending_cuts=sum(r['pending'] for r in loop_results))

# 12 concurrent processes: exclusive writers, shared readers, first-time initialisation races
R = 'd2' * 24
writers = [subprocess.Popen([probe, 'race', str(d), R, '25'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(6)]
readers = [subprocess.Popen([probe, 'readers', str(d), R, '3000'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(4)]
wout = []; rout = []
for pr in writers:
    out, err = pr.communicate(timeout=120); assert pr.returncode == 0, (out, err); wout.append(json.loads(out.strip().splitlines()[-1]))
for pr in readers:
    out, err = pr.communicate(timeout=120); assert pr.returncode == 0, (out, err); rout.append(json.loads(out.strip().splitlines()[-1]))
committed = sum(w['ok'] for w in wout)
assert all(w['bad'] == 0 and w['ok'] + w['busy'] == 25 for w in wout), wout
assert all(r['bad'] == 0 and r['stale'] == 0 for r in rout), rout
fin = status(run('try', d, R, 'shared', 0), OK, 'final'); assert fin['generation'] == committed and fin['pending'] == 0, (fin, committed)
raw = (d / f'{R}.lease').read_bytes(); assert raw == craft(R, committed, 0)
inits = []
for j in range(3):
    ident = f'e{j}' * 24
    ps = [subprocess.Popen([probe, 'try', str(d), ident, 'shared', '5000'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(8)]
    outs = [json.loads(p_.communicate(timeout=60)[0].strip().splitlines()[-1]) for p_ in ps]
    assert all(o['status'] == OK and o['generation'] == 0 and o['pending'] == 0 for o in outs), outs
    assert (d / f'{ident}.lease').read_bytes() == craft(ident)
    inits.append(len(set(o['pid'] for o in outs)))
rec('concurrent_processes_pending_intent_invariants', writers=wout, readers=rout, committed=committed, init_race_pids=inits)

receipt = dict(source=os.environ['GITHUB_SHA'], run=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
               passed=True, case_count=len(cases), cases=cases,
               probe_sha256=hashlib.sha256(pathlib.Path(probe).read_bytes()).hexdigest(),
               library_sha256=hashlib.sha256(pathlib.Path(a.lib).read_bytes()).hexdigest(),
               sdk_open_attempts=0, recovery_admission=False, commit_acknowledged=False,
               full_p0_acceptance=False, physical_power_loss=False)
(work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')

