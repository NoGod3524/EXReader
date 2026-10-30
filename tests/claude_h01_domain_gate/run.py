"""Actions-only cases for the H01 domain gate. Each case drives the real CLI as a
subprocess, so exit codes and the stable stdout line are what is verified.
Prints one H01-CASE line per case and a final H01-SUMMARY line; any mismatch
makes the run exit non-zero and nothing is weakened or retried."""
import copy, hashlib, json, pathlib, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve()
GATE = HERE.parents[2] / 'extras/migration/claude_h01_domain_gate/gate.py'
ID_A = 'a' * 48
ID_B = 'b' * 48
PROV = 'ccd7fec67eb8aa463b09533ce320820f2da472d9'
REG = {'domains': {'domain-a': ID_A, 'domain-b': ID_B}}
BIND = {'domain': 'domain-a', 'lease_identity': ID_A, 'expected_generation': 0,
        'run_id': 1, 'run_attempt': 1, 'provider_sha': PROV, 'gates': ['g1']}


def mut(**kw):
    b = copy.deepcopy(BIND)
    b.update(kw)
    return b


def drop(k):
    b = copy.deepcopy(BIND)
    del b[k]
    return b


def reg_with(**doms):
    return {'domains': doms}


# name, binding, registry, expected exit, expected verdict, expected reason
CASES = [
    ('valid', BIND, REG, 0, 'BINDING_VALID', 'ok'),
    ('valid-gen-max', mut(expected_generation=2**64 - 1), REG, 0, 'BINDING_VALID', 'ok'),
    ('valid-domain-b', mut(domain='domain-b', lease_identity=ID_B), REG, 0, 'BINDING_VALID', 'ok'),
    ('unknown-domain', mut(domain='domain-z'), REG, 1, 'REFUSED', 'domain-unknown'),
    ('identity-mismatch', mut(lease_identity=ID_B), REG, 1, 'REFUSED', 'domain-identity-mismatch'),
    ('identity-uppercase', mut(lease_identity='A' * 48), REG, 1, 'REFUSED', 'binding-identity-format'),
    ('identity-short', mut(lease_identity='a' * 47), REG, 1, 'REFUSED', 'binding-identity-format'),
    ('identity-long', mut(lease_identity='a' * 49), REG, 1, 'REFUSED', 'binding-identity-format'),
    ('identity-nonhex', mut(lease_identity='g' * 48), REG, 1, 'REFUSED', 'binding-identity-format'),
    ('identity-not-string', mut(lease_identity=5), REG, 1, 'REFUSED', 'binding-identity-format'),
    ('generation-negative', mut(expected_generation=-1), REG, 1, 'REFUSED', 'binding-generation'),
    ('generation-overflow', mut(expected_generation=2**64), REG, 1, 'REFUSED', 'binding-generation'),
    ('generation-bool', mut(expected_generation=True), REG, 1, 'REFUSED', 'binding-generation'),
    ('generation-string', mut(expected_generation='0'), REG, 1, 'REFUSED', 'binding-generation'),
    ('run-id-zero', mut(run_id=0), REG, 1, 'REFUSED', 'binding-run-id'),
    ('attempt-zero', mut(run_attempt=0), REG, 1, 'REFUSED', 'binding-run-attempt'),
    ('provider-other', mut(provider_sha='0' * 40), REG, 1, 'REFUSED', 'binding-provider-mismatch'),
    ('provider-short', mut(provider_sha=PROV[:12]), REG, 1, 'REFUSED', 'binding-provider-format'),
    ('gates-empty', mut(gates=[]), REG, 1, 'REFUSED', 'binding-gates'),
    ('gates-duplicate', mut(gates=['g1', 'g1']), REG, 1, 'REFUSED', 'binding-gates'),
    ('gates-nonstring', mut(gates=[1]), REG, 1, 'REFUSED', 'binding-gates'),
    ('missing-key', drop('run_id'), REG, 1, 'REFUSED', 'binding-keys'),
    ('extra-key', mut(extra=1), REG, 1, 'REFUSED', 'binding-keys'),
    ('binding-not-object', [], REG, 1, 'REFUSED', 'binding-schema'),
    ('domain-empty', mut(domain=''), REG, 1, 'REFUSED', 'binding-domain'),
    ('registry-shared-identity', BIND, reg_with(**{'domain-a': ID_A, 'domain-b': ID_A}), 1, 'REFUSED', 'registry-identity-shared'),
    ('registry-bad-identity', BIND, reg_with(**{'domain-a': 'xyz'}), 1, 'REFUSED', 'registry-identity-format'),
    ('registry-empty', BIND, {'domains': {}}, 1, 'REFUSED', 'registry-empty'),
    ('registry-extra-key', BIND, {'domains': {'domain-a': ID_A}, 'x': 1}, 1, 'REFUSED', 'registry-schema'),
]

failures = []
rows = []
with tempfile.TemporaryDirectory() as td:
    td = pathlib.Path(td)
    for name, b, r, want_exit, want_verdict, want_reason in CASES:
        bp, rp = td / (name + '.b.json'), td / (name + '.r.json')
        bp.write_text(json.dumps(b), encoding='utf-8')
        rp.write_text(json.dumps(r), encoding='utf-8')
        p = subprocess.run([sys.executable, '-I', str(GATE), '--binding', str(bp), '--registry', str(rp)],
                           capture_output=True, text=True, timeout=30)
        lines = p.stdout.splitlines()
        got = None
        if len(lines) == 1 and lines[0].startswith('H01-GATE '):
            got = json.loads(lines[0][len('H01-GATE '):])
        ok = (p.returncode == want_exit and got is not None
              and got['verdict'] == want_verdict and got['reason'] == want_reason
              and got['admission_granted'] is False and got['gate'] == 'claude_h01_domain_gate')
        rows.append({'case': name, 'ok': ok, 'exit': p.returncode, 'got': got})
        print('H01-CASE %s %s exit=%d reason=%s' % (name, 'PASS' if ok else 'FAIL', p.returncode, got and got['reason']))
        if not ok:
            failures.append(name)
            print('  stdout=%r stderr=%r' % (p.stdout, p.stderr))
    # Unreadable and malformed inputs must also fail closed with the stable line.
    for name, bcontent in (('input-missing-file', None), ('input-invalid-json', '{')):
        bp = td / (name + '.b.json')
        if bcontent is not None:
            bp.write_text(bcontent, encoding='utf-8')
        rp = td / 'ok.r.json'
        rp.write_text(json.dumps(REG), encoding='utf-8')
        p = subprocess.run([sys.executable, '-I', str(GATE), '--binding', str(bp), '--registry', str(rp)],
                           capture_output=True, text=True, timeout=30)
        got = json.loads(p.stdout.splitlines()[0][len('H01-GATE '):]) if p.stdout.startswith('H01-GATE ') else None
        ok = p.returncode == 2 and got and got['verdict'] == 'REFUSED' and got['reason'] == 'input-unreadable'
        rows.append({'case': name, 'ok': bool(ok), 'exit': p.returncode, 'got': got})
        print('H01-CASE %s %s exit=%d' % (name, 'PASS' if ok else 'FAIL', p.returncode))
        if not ok:
            failures.append(name)

gate_sha = hashlib.sha256(GATE.read_bytes()).hexdigest()
out = {'gate_sha256': gate_sha, 'cases': len(rows), 'failed': failures, 'rows': rows}
if len(sys.argv) > 1:
    pathlib.Path(sys.argv[1]).write_text(json.dumps(out, indent=1, sort_keys=True), encoding='utf-8')
print('H01-SUMMARY cases=%d failed=%d gate_sha256=%s' % (len(rows), len(failures), gate_sha))
sys.exit(1 if failures else 0)
