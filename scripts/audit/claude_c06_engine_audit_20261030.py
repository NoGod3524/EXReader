#!/usr/bin/env python3
"""Independent preliminary audit of the original Windows observer producer.

Binds source SHA, run id, run attempt, job and artifact identity of the original
evidence, then re-derives hashes from the downloaded bytes and from Git blobs.
Producer assertions (receipt.json, stdout.txt) are cross-checked, never trusted
as proof. Missing original evidence is a failure.
"""
import argparse
import copy
import datetime
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

EXPECT = dict(  # corrected producer; primary target
    label='corrected',
    repo='NoGod3524/EXReader',
    sha='83b0bd1c1d2d697973ef43272d42b34cc58baa7f',
    base='2743f32a4eccd5823657da19cb4f77f2411424af',
    run_id=41087206035,
    artifact_id=12991588693,
    job='engine',
    job_id=124171372303,
    zip_size=250290,
    zip_sha256='daa5f7b6ab686de1340a73dd80d626e01fd8157487447da651c2cb7ed3c4e913',
    boundary=True,
    workflow='.github/workflows/migration-windows-engine-20261030.yml',
)
LEGACY = dict(  # original b3f34657 producer; retained, never replaced
    EXPECT, label='original-b3f34657', sha='b3f346570df7ca972c67232bb5ec3cfb2f6510d8',
    run_id=41024553069, artifact_id=12962888396, job_id=None, zip_size=None,
    zip_sha256='819b770ce3822145b1cbdcc15dd59772903c88a2e266f4d81bbef5a02e3ea364', boundary=False)
STEPS = ('Exact source admission',
         'Build and install frozen SDK plus opt-in private engine',
         'Actual separately compiled installed consumer')
EV = 'build/engine-evidence/'
EXE = 'engine-stage/bin/exreader-migration-windows-observer.exe'
LIB = 'engine-stage/lib/exreader-migration-windows-engine.lib'
INC = 'engine-stage/include/exreader-migration-windows-engine/'
SRC = 'extras/migration/windows_recovery_engine_20261030/'
FIXED = (EV + 'receipt.json', EV + 'admission.json', EV + 'stdout.txt', EV + 'stderr.txt',
         EV + 'private/target.fixture', EV + 'private/observed.bin', EV + 'private/deadline.bin',
         EXE, LIB,
         'build/migration/windows_recovery_engine_20261030/observer-provider.map',
         'build/engine-check/consumer-provider.map')
BOUNDARY = (EV + 'boundary-stdout.txt', EV + 'boundary-stderr.txt', EV + 'boundary-receipt.json',
            EV + 'boundary-private/wrong-launch.bin')
HEADER_DIRS = (SRC, 'extras/migration/src/', 'src/')
PREFIXES = ('extras/migration/windows_recovery_engine_20261030/',
            'tests/migration/windows_recovery_engine_20261030/')
ALLOWED = {'extras/migration/CMakeLists.txt',
           '.github/workflows/migration-windows-engine-20261030.yml',
           'docs/MIGRATION-WINDOWS-ENGINE-20261030.md'}


class AuditError(Exception):
    pass


def req(cond, msg):
    if not cond:
        raise AuditError(msg)


def h(b):
    return hashlib.sha256(b).hexdigest()


def ts(s):
    return datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))


def verify_meta(run, jobs, art, exp=EXPECT, zip_sha256=None, zip_size=None):
    """Identity binding from the GitHub API. Returns the run attempt."""
    req(run.get('id') == exp['run_id'], 'run id mismatch')
    req(run.get('head_sha') == exp['sha'], 'run head_sha mismatch')
    req(run.get('event') == 'push', 'run event is not push')
    req(run.get('status') == 'completed' and run.get('conclusion') == 'success', 'run not completed successfully')
    req(str(run.get('path', '')).startswith(exp['workflow']), 'run workflow path mismatch')
    attempt = run.get('run_attempt')
    req(isinstance(attempt, int) and attempt >= 1, 'run attempt missing')
    named = [j for j in jobs if j.get('name') == exp['job']]
    req(len(named) == 1, 'job %s not found exactly once' % exp['job'])
    job = named[0]
    req(job.get('conclusion') == 'success', 'job did not succeed')
    if exp.get('job_id') is not None:
        req(job.get('id') == exp['job_id'], 'job id mismatch')
    req(job.get('head_sha') == exp['sha'], 'job head_sha mismatch')
    req(job.get('run_id') == exp['run_id'], 'job run id mismatch')
    req(job.get('run_attempt') == attempt, 'job run attempt mismatch')
    steps = {s.get('name'): s.get('conclusion') for s in job.get('steps', [])}
    for name in STEPS:
        req(steps.get(name) == 'success', 'step not successful: ' + name)
    req(any(n.startswith('Run actions/upload-artifact') and c == 'success' for n, c in steps.items()),
        'upload step not successful')
    req(art.get('id') == exp['artifact_id'], 'artifact id mismatch')
    req(art.get('name') == 'windows-engine-' + exp['sha'], 'artifact name mismatch')
    req(art.get('expired') is False, 'artifact expired')
    wr = art.get('workflow_run') or {}
    req(wr.get('id') == exp['run_id'], 'artifact run id mismatch')
    req(wr.get('head_sha') == exp['sha'], 'artifact head_sha mismatch')
    slack = datetime.timedelta(seconds=60)
    created = ts(art['created_at'])
    req(ts(job['started_at']) - slack <= created <= ts(job['completed_at']) + slack,
        'artifact not created inside job window')
    digest = art.get('digest')
    if digest is not None and zip_sha256 is not None:
        req(digest == 'sha256:' + zip_sha256, 'artifact digest mismatch')
    if exp.get('zip_sha256'):
        req(zip_sha256 == exp['zip_sha256'], 'zip sha256 differs from pinned value')
    if exp.get('zip_size'):
        req(zip_size == exp['zip_size'], 'zip size differs from pinned value')
        req(art.get('size_in_bytes') == exp['zip_size'], 'artifact size_in_bytes differs from pinned value')
    return attempt


def pe_x64(b):
    if len(b) < 0x100 or b[:2] != b'MZ':
        return False
    off = int.from_bytes(b[0x3c:0x40], 'little')
    return b[off:off + 4] == b'PE\0\0' and int.from_bytes(b[off + 4:off + 6], 'little') == 0x8664


def verify_files(root, attempt, git_blob, exp=EXPECT):
    """Content binding of the unpacked artifact. Returns (checks, observations)."""
    root = Path(root)
    sha = exp['sha']
    found = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    fixed = FIXED + (BOUNDARY if exp.get('boundary') else ())
    for p in fixed:
        req(p in found, 'missing original evidence: ' + p)
    extra = sorted(p for p in found - set(fixed)
                   if not p.startswith(INC) and not (exp.get('boundary') and p.startswith(EV + 'boundary-private/')))
    req(not extra, 'unexpected files: %s' % extra)
    headers = sorted(p for p in found if p.startswith(INC))
    req(headers, 'missing original evidence: installed headers')
    rd = lambda p: (root / p).read_bytes()
    checks, obs = [], []
    exe, lib = rd(EXE), rd(LIB)
    req(pe_x64(exe), 'observer is not an x64 PE image')
    req(lib[:8] == b'!<arch>\n', 'engine library is not an ar archive')
    req(rd('build/migration/windows_recovery_engine_20261030/observer-provider.map')
        and rd('build/engine-check/consumer-provider.map'), 'provider map empty')
    checks.append('binary-format')
    priv = {n: rd(EV + 'private/' + n) for n in ('target.fixture', 'observed.bin', 'deadline.bin')}
    req(priv['target.fixture'] == b'retained-byte-observation', 'target fixture bytes differ')
    req(priv['deadline.bin'] == b'', 'deadline bytes not empty')
    req(priv['observed.bin'], 'observed bytes empty')
    checks.append('private-bytes')
    try:
        r = json.loads(rd(EV + 'receipt.json'))
        out = json.loads(rd(EV + 'stdout.txt'))
        adm = json.loads(rd(EV + 'admission.json'))
    except ValueError:
        raise AuditError('evidence json unparsable')
    req(r.get('source') == sha, 'receipt source mismatch')
    req(r.get('run') == str(exp['run_id']), 'receipt run mismatch')
    req(r.get('attempt') == str(attempt), 'receipt attempt mismatch')
    req(r.get('full_p0_acceptance') is False, 'receipt claims full P0')
    req(r.get('worker_sha256') == h(exe), 'receipt worker hash differs from bytes')
    req(r.get('library_sha256') == h(lib), 'receipt library hash differs from bytes')
    req(r.get('files') == {n: h(b) for n, b in priv.items()}, 'receipt private file hashes differ')
    req(r.get('consumer') == out, 'receipt consumer differs from stdout')
    req(out.get('migration_admission') is False and out.get('full_p0_acceptance') is False, 'stdout claims admission')
    checks.append('receipt-binding')
    req(adm.get('source') == sha and adm.get('base') == exp['base'], 'admission source/base mismatch')
    req(adm.get('full_p0_acceptance') is False, 'admission claims full P0')
    changed = adm.get('changed')
    req(isinstance(changed, list) and changed, 'admission change list missing')
    req(all(p.startswith(PREFIXES) or p in ALLOWED for p in changed), 'admission change outside owned paths')
    req(sorted(adm.get('files', {})) == sorted(changed), 'admission file list differs from change list')
    for p in changed:
        blob = git_blob(sha, p)
        req(blob is not None, 'git blob unavailable: ' + p)
        req(adm['files'][p] == h(blob), 'admission hash differs from git blob: ' + p)
    checks.append('admission-git-blobs')
    for p in headers:
        blob = next((b for b in (git_blob(sha, d + p[len(INC):]) for d in HEADER_DIRS) if b is not None), None)
        if blob is None:
            obs.append('header has no same-named source: ' + p)
        else:
            req(h(rd(p)) == h(blob), 'installed header differs from git blob: ' + p)
    checks.append('headers')
    if exp.get('boundary'):
        try:
            bout = json.loads(rd(EV + 'boundary-stdout.txt'))
            brec = json.loads(rd(EV + 'boundary-receipt.json'))
        except ValueError:
            raise AuditError('boundary json unparsable')
        req(brec.get('source') == sha, 'boundary receipt source mismatch')
        req(brec.get('run') == str(exp['run_id']), 'boundary receipt run mismatch')
        req(brec.get('attempt') == str(attempt), 'boundary receipt attempt mismatch')
        req(brec.get('full_p0_acceptance') is False, 'boundary receipt claims full P0')
        req(brec.get('result') == bout, 'boundary receipt differs from boundary stdout')
        req(bout.get('passed') is True and bout.get('failed') == 0 and bout.get('checks') == 21,
            'boundary result not 21 checks / 0 failed')
        req(rd(EV + 'boundary-private/wrong-launch.bin') == b'', 'wrong-launch bytes not empty')
        checks.append('boundary-binding')
        obs.append('boundary suite is test_only_fault_injection=%s, receipt production_test_hooks=%s; '
                   'both producer-asserted, not independent proof' % (
                       bout.get('test_only_fault_injection'), brec.get('production_test_hooks')))
    if exp['sha'].encode() not in exe:
        obs.append('source SHA not embedded in observer binary')
    obs.append('producer-asserted (not independent): consumer checks=%s failed=%s' % (out.get('checks'), out.get('failed')))
    return checks, obs


def extract_zip(zpath, dest):
    dest = Path(dest)
    req(dest.is_dir() and not any(dest.iterdir()), 'destination must be an empty directory')
    total = 0
    with zipfile.ZipFile(zpath) as z:
        for i in z.infolist():
            n = PurePosixPath(i.filename)
            req(not n.is_absolute() and '..' not in n.parts and '\\' not in i.filename, 'unsafe zip member: ' + i.filename)
            req((i.external_attr >> 16) & 0o170000 != 0o120000, 'zip symlink member: ' + i.filename)
            total += i.file_size
            req(total <= 256 * 1024 * 1024, 'zip too large')
        z.extractall(dest)


def git_blob(sha, path):
    p = subprocess.run(['git', 'show', '%s:%s' % (sha, path)], capture_output=True)
    return p.stdout if p.returncode == 0 else None


def gh_json(path):
    p = subprocess.run(['gh', 'api', '-H', 'Accept: application/vnd.github+json', path], capture_output=True, text=True)
    req(p.returncode == 0, 'original evidence unavailable (%s): %s' % (path, p.stderr.strip()[:200]))
    return json.loads(p.stdout)


def audit(out):
    """Corrected producer is primary; the original b3f34657 evidence is retained as a cross-check."""
    out = Path(out)
    reports = [audit_one(out / t['label'], t) for t in (EXPECT, LEGACY)]
    summary = dict(primary=reports[0]['original'], primary_verified=reports[0]['provenance_and_integrity_verified'],
                   retained_original_verified=reports[1]['provenance_and_integrity_verified'],
                   behavior_independently_verified=False, full_p0_acceptance=False,
                   commit_or_sdk_admission=False)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return reports[0]


def audit_one(out, exp):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    repo = os.environ.get('GITHUB_REPOSITORY', exp['repo'])
    report = dict(auditor=dict(source=os.environ.get('GITHUB_SHA'), run=os.environ.get('GITHUB_RUN_ID'),
                               attempt=os.environ.get('GITHUB_RUN_ATTEMPT')),
                  original=dict(label=exp['label'], sha=exp['sha'], run_id=exp['run_id'],
                                artifact_id=exp['artifact_id'], job=exp['job'], job_id=exp['job_id']),
                  provenance_and_integrity_verified=False,
                  behavior_independently_verified=False,
                  native_owner_fix_7b26bf30='unverified: its own run not supplied; 83b0bd1c descends from it and is audited separately',
                  commit_or_sdk_admission=False,
                  old_risks_preserved=True,
                  full_p0_acceptance=False)
    try:
        run = gh_json('repos/%s/actions/runs/%d' % (repo, exp['run_id']))
        attempt = run.get('run_attempt')
        jobs = gh_json('repos/%s/actions/runs/%d/attempts/%s/jobs?per_page=100' % (repo, exp['run_id'], attempt))['jobs']
        art = gh_json('repos/%s/actions/artifacts/%d' % (repo, exp['artifact_id']))
        zpath = out / 'original.zip'
        with open(zpath, 'wb') as f:
            p = subprocess.run(['gh', 'api', 'repos/%s/actions/artifacts/%d/zip' % (repo, exp['artifact_id'])], stdout=f, stderr=subprocess.PIPE)
        req(p.returncode == 0, 'original artifact download failed: ' + p.stderr.decode()[:200])
        zb = zpath.read_bytes()
        report['original']['zip_sha256'] = h(zb)
        report['original']['zip_size'] = len(zb)
        attempt = verify_meta(run, jobs, art, exp, h(zb), len(zb))
        report['original']['attempt'] = attempt
        dest = out / 'original'
        dest.mkdir()
        extract_zip(zpath, dest)
        checks, obs = verify_files(dest, attempt, git_blob, exp)
        report.update(checks=['identity'] + checks, observations=obs, provenance_and_integrity_verified=True)
    except AuditError as e:
        report['failure'] = str(e)
    (out / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    sys.exit(0 if audit(a.out)['provenance_and_integrity_verified'] else 1)
