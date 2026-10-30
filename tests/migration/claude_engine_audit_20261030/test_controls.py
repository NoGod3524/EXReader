import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'audit', Path(__file__).resolve().parents[3] / 'scripts/audit/claude_c06_engine_audit_20261030.py')
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)
E = A.EXPECT
h = A.h

SRC_BLOBS = {
    'extras/migration/windows_recovery_engine_20261030/lm_win_engine.h': b'header-a',
    'extras/migration/windows_recovery_engine_20261030/engine.c': b'engine-source',
    'docs/MIGRATION-WINDOWS-ENGINE-20261030.md': b'doc',
}


def blob(sha, path):
    return SRC_BLOBS.get(path) if sha == E['sha'] else None


def make_files():
    exe = bytearray(0x200)
    exe[:2] = b'MZ'
    exe[0x3c:0x40] = (0x80).to_bytes(4, 'little')
    exe[0x80:0x84] = b'PE\0\0'
    exe[0x84:0x86] = (0x8664).to_bytes(2, 'little')
    exe = bytes(exe)
    lib = b'!<arch>\nmember'
    priv = {'target.fixture': b'retained-byte-observation', 'observed.bin': b'obs', 'deadline.bin': b''}
    out = {'passed': True, 'checks': 29, 'failed': 0, 'migration_admission': False, 'full_p0_acceptance': False}
    adm = dict(source=E['sha'], base=E['base'], changed=sorted(SRC_BLOBS), full_p0_acceptance=False,
               files={p: h(b) for p, b in SRC_BLOBS.items()})
    rec = dict(source=E['sha'], run=str(E['run_id']), attempt='1', consumer=out, worker_sha256=h(exe),
               library_sha256=h(lib), files={n: h(b) for n, b in priv.items()}, full_p0_acceptance=False)
    ev = A.EV
    f = {ev + 'receipt.json': json.dumps(rec).encode(), ev + 'admission.json': json.dumps(adm).encode(),
         ev + 'stdout.txt': json.dumps(out).encode(), ev + 'stderr.txt': b'',
         A.EXE: exe, A.LIB: lib,
         'build/migration/windows_recovery_engine_20261030/observer-provider.map': b'map',
         'build/engine-check/consumer-provider.map': b'map',
         A.INC + 'lm_win_engine.h': b'header-a'}
    f.update({ev + 'private/' + n: b for n, b in priv.items()})
    return f


def make_meta():
    run = dict(id=E['run_id'], head_sha=E['sha'], event='push', status='completed', conclusion='success',
               path=E['workflow'], run_attempt=1)
    steps = [dict(name=n, conclusion='success') for n in A.STEPS] + \
            [dict(name='Run actions/upload-artifact@v4', conclusion='success')]
    job = dict(name=E['job'], conclusion='success', head_sha=E['sha'], run_id=E['run_id'], run_attempt=1,
               started_at='2026-10-30T10:00:00Z', completed_at='2026-10-30T10:10:00Z', steps=steps)
    art = dict(id=E['artifact_id'], name='windows-engine-' + E['sha'], expired=False,
               workflow_run=dict(id=E['run_id'], head_sha=E['sha']), created_at='2026-10-30T10:09:00Z',
               digest='sha256:' + 'ab' * 32)
    return run, [job], art


def check_files(files, attempt=1, blob_fn=blob):
    with tempfile.TemporaryDirectory() as d:
        for p, b in files.items():
            t = Path(d) / p
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_bytes(b)
        return A.verify_files(d, attempt, blob_fn)


def edit_json(path, fn):
    def m(f):
        j = json.loads(f[path])
        fn(j)
        f[path] = json.dumps(j).encode()
    return m


class Controls(unittest.TestCase):
    def test_valid_passes(self):
        run, jobs, art = make_meta()
        self.assertEqual(A.verify_meta(run, jobs, art, E, 'ab' * 32), 1)
        checks, _ = check_files(make_files())
        self.assertIn('receipt-binding', checks)

    def test_meta_rejections(self):
        def sub(d, k, v):
            d[k] = v
        cases = [
            ('run id mismatch', lambda r, j, a: sub(r, 'id', 1)),
            ('run head_sha mismatch', lambda r, j, a: sub(r, 'head_sha', '0' * 40)),
            ('not completed successfully', lambda r, j, a: sub(r, 'conclusion', 'failure')),
            ('run event', lambda r, j, a: sub(r, 'event', 'pull_request')),
            ('workflow path', lambda r, j, a: sub(r, 'path', '.github/workflows/other.yml')),
            ('job attempt|run attempt', lambda r, j, a: sub(j[0], 'run_attempt', 2)),
            ('job head_sha', lambda r, j, a: sub(j[0], 'head_sha', '1' * 40)),
            ('job run id', lambda r, j, a: sub(j[0], 'run_id', 7)),
            ('not found exactly once', lambda r, j, a: sub(j[0], 'name', 'other')),
            ('did not succeed', lambda r, j, a: sub(j[0], 'conclusion', 'cancelled')),
            ('step not successful', lambda r, j, a: sub(j[0]['steps'][2], 'conclusion', 'skipped')),
            ('upload step', lambda r, j, a: j[0]['steps'].pop()),
            ('artifact id', lambda r, j, a: sub(a, 'id', 5)),
            ('artifact name', lambda r, j, a: sub(a, 'name', 'windows-engine-' + '2' * 40)),
            ('expired', lambda r, j, a: sub(a, 'expired', True)),
            ('artifact run id', lambda r, j, a: a['workflow_run'].update(id=9)),
            ('artifact head_sha', lambda r, j, a: a['workflow_run'].update(head_sha='3' * 40)),
            ('job window', lambda r, j, a: sub(a, 'created_at', '2026-10-29T10:00:00Z')),
            ('digest', lambda r, j, a: sub(a, 'digest', 'sha256:' + 'cd' * 32)),
        ]
        for rx, mut in cases:
            run, jobs, art = copy.deepcopy(make_meta())
            mut(run, jobs, art)
            with self.subTest(rx), self.assertRaisesRegex(A.AuditError, rx):
                A.verify_meta(run, jobs, art, E, 'ab' * 32)

    def test_attempt_binding(self):
        with self.assertRaisesRegex(A.AuditError, 'receipt attempt'):
            check_files(make_files(), attempt=2)

    def test_missing_evidence_fails(self):
        for p in A.FIXED:
            f = make_files()
            if p not in f:
                continue
            del f[p]
            with self.subTest(p), self.assertRaisesRegex(A.AuditError, 'missing original evidence'):
                check_files(f)
        f = make_files()
        del f[A.INC + 'lm_win_engine.h']
        with self.assertRaisesRegex(A.AuditError, 'missing original evidence'):
            check_files(f)
        with self.assertRaisesRegex(A.AuditError, 'missing original evidence'):
            check_files({})

    def test_tamper_rejections(self):
        ev = A.EV
        cases = [
            ('worker hash', lambda f: f.update({A.EXE: f[A.EXE] + b'x'})),
            ('library hash', lambda f: f.update({A.LIB: f[A.LIB] + b'x'})),
            ('not an x64 PE', lambda f: f.update({A.EXE: b'MZ' + b'\0' * 600})),
            ('ar archive', lambda f: f.update({A.LIB: b'not-archive-bytes'})),
            ('target fixture', lambda f: f.update({ev + 'private/target.fixture': b'other'})),
            ('deadline bytes', lambda f: f.update({ev + 'private/deadline.bin': b'x'})),
            ('observed bytes empty', lambda f: f.update({ev + 'private/observed.bin': b''})),
            ('unexpected files', lambda f: f.update({'extra.txt': b'x'})),
            ('provider map empty', lambda f: f.update({'build/engine-check/consumer-provider.map': b''})),
            ('receipt source', edit_json(ev + 'receipt.json', lambda j: j.update(source='4' * 40))),
            ('receipt run', edit_json(ev + 'receipt.json', lambda j: j.update(run='1'))),
            ('claims full P0', edit_json(ev + 'receipt.json', lambda j: j.update(full_p0_acceptance=True))),
            ('private file hashes', edit_json(ev + 'receipt.json', lambda j: j['files'].update({'observed.bin': '0'}))),
            ('consumer differs', edit_json(ev + 'receipt.json', lambda j: j['consumer'].update(checks=30))),
            ('stdout claims admission', lambda f: (f.update({ev + 'stdout.txt': json.dumps(
                {'passed': True, 'checks': 29, 'failed': 0, 'migration_admission': True,
                 'full_p0_acceptance': False}).encode()}),
                edit_json(ev + 'receipt.json', lambda j: j.update(consumer=json.loads(f[ev + 'stdout.txt'])))(f))),
            ('unparsable', lambda f: f.update({ev + 'stdout.txt': b'{not json'})),
            ('admission source/base', edit_json(ev + 'admission.json', lambda j: j.update(base='5' * 40))),
            ('admission claims full P0', edit_json(ev + 'admission.json', lambda j: j.update(full_p0_acceptance=True))),
            ('outside owned paths', edit_json(ev + 'admission.json', lambda j: (
                j['changed'].append('src/engine.c'), j['files'].update({'src/engine.c': 'x'})))),
            ('differs from git blob', edit_json(ev + 'admission.json', lambda j: j['files'].update(
                {'docs/MIGRATION-WINDOWS-ENGINE-20261030.md': h(b'forged')}))),
            ('installed header differs', lambda f: f.update({A.INC + 'lm_win_engine.h': b'forged'})),
        ]
        for rx, mut in cases:
            f = make_files()
            mut(f)
            with self.subTest(rx), self.assertRaisesRegex(A.AuditError, rx):
                check_files(f)

    def test_git_blob_unavailable_fails(self):
        with self.assertRaisesRegex(A.AuditError, 'git blob unavailable'):
            check_files(make_files(), blob_fn=lambda s, p: None)

    def test_zip_rejections(self):
        for name in ('../escape', '/abs'):
            with tempfile.TemporaryDirectory() as d:
                z = Path(d) / 'a.zip'
                with zipfile.ZipFile(z, 'w') as zf:
                    zf.writestr(name, b'x')
                dest = Path(d) / 'out'
                dest.mkdir()
                with self.subTest(name), self.assertRaisesRegex(A.AuditError, 'unsafe zip member'):
                    A.extract_zip(z, dest)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'x').write_text('x')
            with self.assertRaisesRegex(A.AuditError, 'empty directory'):
                A.extract_zip(Path(d) / 'none.zip', d)

    def test_audit_without_credentials_fails(self):
        import os
        old = os.environ.copy()
        os.environ['PATH'] = ''
        try:
            with tempfile.TemporaryDirectory() as d, self.assertRaises(Exception):
                A.audit(d)
        finally:
            os.environ.clear()
            os.environ.update(old)


if __name__ == '__main__':
    unittest.main()
