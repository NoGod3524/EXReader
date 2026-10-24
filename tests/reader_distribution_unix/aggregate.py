#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict same-source collection of the Unix distribution candidate artifacts.

Nothing is trusted because a job said it passed: jobs, run and attempt are read
back from the API, every uploaded ZIP digest is recomputed, every installed file is
re-hashed, the archive is extracted again, the static contract is re-audited from
those extracted bytes, and the recorded consumer and smoke outcomes are re-read.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'reader_distribution_unix'))
import contract

WORKFLOW = '.github/workflows/reader-distribution-unix.yml'
PLATFORMS = ('linux', 'macos')
JOB_NAMES = {'rejection protocol', 'unix (linux)', 'unix (macos)', 'same-source report'}
REPORT_JOB = 'same-source report'
REQUIRED_CHECKS = ('tree_inventory', 'install_layout', 'pkgconfig_contract', 'pkgconfig_directory',
                   'absolute_path_scan',
                   'cmake_relocatable', 'document_bytes', 'licence_materials',
                   'duplicate_material', 'pkgconfig_query', 'installed_consumers',
                   'nine_format_smoke')


class ReportError(RuntimeError):
    pass


def need(value, message):
    if not value:
        raise ReportError(message)
    return value


def api(path):
    done = subprocess.run(['gh', 'api', '-H', 'Accept: application/vnd.github+json', path],
                          capture_output=True, text=True, timeout=180)
    need(done.returncode == 0, 'github api failed: %s %s' % (path, done.stderr.strip()[:200]))
    return json.loads(done.stdout)


def api_bytes(path, destination):
    with Path(destination).open('wb') as stream:
        done = subprocess.run(['gh', 'api', '-H', 'Accept: application/vnd.github+json', path],
                              stdout=stream, stderr=subprocess.PIPE, timeout=600)
    need(done.returncode == 0, 'artifact download failed: ' + done.stderr.decode()[:200])


def payload(folder):
    result = {}
    for path in sorted(Path(folder).rglob('*')):
        if path.is_file():
            result[path.relative_to(folder).as_posix()] = path.read_bytes()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        return summary_main(args)
    except ReportError as error:
        write(args.output, {'schema': 1, 'accepted': False, 'release_ready': False,
                            'source_sha': os.environ.get('GITHUB_SHA'),
                            'run_id': int(os.environ.get('GITHUB_RUN_ID', 0)),
                            'attempt': int(os.environ.get('GITHUB_RUN_ATTEMPT', 0)),
                            'checks': [], 'problems': [str(error)], 'platforms': {},
                            'published': False, 'quality_accepted': False})
        print(json.dumps({'accepted': False, 'problems': [str(error)]}))
        return 1


def summary_main(args):
    need(os.environ.get('GITHUB_ACTIONS') == 'true', 'summary runs in cloud CI only')
    run_id = int(os.environ['GITHUB_RUN_ID'])
    attempt = int(os.environ['GITHUB_RUN_ATTEMPT'])
    sha = os.environ['GITHUB_SHA']
    repo = os.environ['GITHUB_REPOSITORY']
    api_root = '/repos/%s/actions/runs/%d' % (repo, run_id)
    run = api('%s/attempts/%d' % (api_root, attempt))
    jobs = api('%s/attempts/%d/jobs?per_page=100' % (api_root, attempt))['jobs']
    artifacts = api(api_root + '/artifacts?per_page=100')['artifacts']
    problems = []

    def check(name, issues, detail):
        problems.extend('%s: %s' % (name, issue) for issue in issues)
        return {'id': name, 'status': 'pass' if not issues else 'fail', 'detail': detail,
                'problems': list(issues)}

    results = []
    need(run.get('head_sha') == sha, 'run head differs from this checkout')
    need(run.get('path') == WORKFLOW, 'run was produced by another workflow')
    need(run.get('run_attempt') == attempt and run.get('id') == run_id, 'run attempt identity differs')
    names = {job['name'] for job in jobs}
    results.append(check('job_set', [] if names == JOB_NAMES else
                         ['unexpected jobs: %s' % sorted(names)], 'exactly four named jobs'))
    unhealthy = [job['name'] for job in jobs
                 if job['name'] != REPORT_JOB and not (job.get('status') == 'completed'
                                                       and job.get('conclusion') == 'success')]
    results.append(check('job_conclusion', unhealthy, 'protocol and both platform jobs succeeded'))
    if not all(result['status'] == 'pass' for result in results):
        write(args.output, {'schema': 1, 'accepted': False, 'release_ready': False,
                            'source_sha': sha, 'run_id': run_id, 'attempt': attempt,
                            'checks': results, 'problems': problems, 'platforms': {}})
        print(json.dumps({'accepted': False, 'problems': problems}))
        return 1

    wanted = {key: 'reader-distribution-unix-%s-%d-%d' % (key, run_id, attempt) for key in PLATFORMS}
    wanted['protocol'] = 'reader-distribution-protocol-%d-%d' % (run_id, attempt)
    index = {artifact['name']: artifact for artifact in artifacts}
    for name in wanted.values():
        need(name in index, 'missing artifact ' + name)
    now = datetime.now(timezone.utc)
    downloads = args.output / 'downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    downloaded = {}
    artifact_rows = []
    for key, name in wanted.items():
        artifact = index[name]
        need(artifact.get('expired') is False, 'artifact already expired: ' + name)
        expires = artifact.get('expires_at')
        need(isinstance(expires, str) and datetime.fromisoformat(expires.replace('Z', '+00:00')) > now,
             'artifact expiry is not in the future: ' + name)
        need(type(artifact.get('size_in_bytes')) is int and artifact['size_in_bytes'] > 0,
             'artifact is empty: ' + name)
        origin = artifact.get('workflow_run') or {}
        need(str(origin.get('id')) == str(run_id) and origin.get('head_sha') == sha,
             'artifact was produced by another run or source: ' + name)
        target = downloads / (name + '.zip')
        api_bytes('/repos/%s/actions/artifacts/%d/zip' % (repo, artifact['id']), target)
        computed = contract.digest(target)
        recorded = (artifact.get('digest') or '').replace('sha256:', '')
        need(computed == recorded, 'artifact digest differs from the API: ' + name)
        folder = downloads / name
        with zipfile.ZipFile(target) as archive:
            archive.extractall(folder)
        downloaded[key] = payload(folder)
        artifact_rows.append({'key': key, 'name': name, 'id': artifact['id'],
                              'bytes': artifact['size_in_bytes'],
                              'api_digest': artifact.get('digest'),
                              'downloaded_sha256': computed,
                              'expires_at': expires})
    results.append(check('artifact_identity', [], '%d same-run artifacts downloaded and re-hashed'
                         % len(artifact_rows)))

    platforms = {}
    for key in PLATFORMS:
        issues, row = verify_platform(key, downloaded[key], sha, run_id, attempt, args.output)
        platforms[key] = row
        results.append(check('platform_' + key, issues,
                             'relocated, deduplicated and re-extracted %s candidate' % key))

    accepted = not problems and all(result['status'] == 'pass' for result in results)
    summary = {'schema': 1, 'accepted': accepted, 'release_ready': accepted,
               'source_sha': sha, 'run_id': run_id, 'attempt': attempt,
               'workflow': WORKFLOW, 'repository': repo,
               'verified_at': now.isoformat(),
               'scope': 'Linux/x64 and macOS/ARM64 reading-core relocation, pkg-config, '
                        'duplicate-material removal and installed-consumer behaviour; '
                        'the six accepted R6 packages and their hashes are untouched',
               'published': False, 'tag_created': False, 'quality_accepted': False,
               'artifacts': artifact_rows, 'platforms': platforms,
               'checks': results, 'problems': problems,
               'uncovered': ['Windows candidate distribution', 'library and optional profiles',
                             'performance, accessibility, real-device and audio scope',
                             'product host wiring by root']}
    write(args.output, summary)
    print(json.dumps({'accepted': accepted, 'problems': problems,
                      'platforms': {key: platforms[key].get('archive_sha256') for key in platforms}}))
    return 0 if accepted else 1


def write(folder, summary):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')


def require_audit(name, payload_bytes, sha, label):
    issues = []
    report = json.loads(payload_bytes.decode('utf-8'))
    if report.get('schema') != 1:
        issues.append('audit schema is not 1')
    if report.get('source_sha') != sha:
        issues.append('audit was produced for another source')
    if report.get('label') != label:
        issues.append('audit label differs: ' + str(report.get('label')))
    if report.get('release_ready') is not True:
        issues.append('audit is not release ready')
    for problem in report.get('problems') or []:
        issues.append('audit problem: ' + problem)
    statuses = {}
    for entry in report.get('checks') or []:
        statuses[entry.get('id')] = entry.get('status')
        if entry.get('status') not in ('pass', 'reported'):
            issues.append('check %s is %s' % (entry.get('id'), entry.get('status')))
    for name in REQUIRED_CHECKS:
        if statuses.get(name) != 'pass':
            issues.append('required check %s is missing or not passing' % name)
    if label != 'report' and statuses.get('runtime_dependencies') != 'pass':
        issues.append('runtime dependency check did not pass in the build job')
    return issues, report


def verify_platform(key, files, sha, run_id, attempt, output):
    issues = []
    need('stage.json' in files, key + ': stage.json missing')
    stage = json.loads(files['stage.json'].decode('utf-8'))
    for field, expected in (('source_sha', sha), ('platform', key), ('profile', 'reading-core')):
        if stage.get(field) != expected:
            issues.append('stage %s differs: %s' % (field, stage.get(field)))
    ci = stage.get('ci') or {}
    if str(ci.get('GITHUB_RUN_ID')) != str(run_id) or str(ci.get('GITHUB_RUN_ATTEMPT')) != str(attempt):
        issues.append('stage was recorded by another run or attempt')
    if stage.get('release_ready') is not True or stage.get('problems'):
        issues.append('stage did not accept the candidate')
    for entry in stage.get('checks') or []:
        if entry.get('status') != 'pass':
            issues.append('stage check %s is %s' % (entry.get('id'), entry.get('status')))
    pc = (stage.get('pkgconfig') or {}).get('text', '')
    fields, pc_problems = contract.pc_contract(pc, stage.get('sdk_version'), stage.get('link_order'),
                                               stage.get('private_archives'),
                                               stage.get('system_libraries'))
    issues.extend('pkg-config: ' + problem for problem in pc_problems)
    if contract.digest_bytes(pc.encode('utf-8')) != (stage.get('pkgconfig') or {}).get('sha256'):
        issues.append('recorded pkg-config digest does not match its bytes')

    archives = [name for name in files if name.endswith('.tar.gz')]
    if len(archives) != 1:
        issues.append('expected exactly one sealed archive, found %d' % len(archives))
    if 'dist/manifest.json' not in files:
        issues.append('archive manifest missing')
    manifest = json.loads(files.get('dist/manifest.json', b'{}').decode('utf-8'))
    archive_sha = None
    extracted_files = []
    if archives and manifest:
        archive_bytes = files[archives[0]]
        archive_sha = contract.digest_bytes(archive_bytes)
        if archive_sha != (manifest.get('archive') or {}).get('sha256'):
            issues.append('archive digest differs from its manifest')
        if len(archive_bytes) != (manifest.get('archive') or {}).get('bytes'):
            issues.append('archive size differs from its manifest')
        recorded = {member['path']: member for member in manifest.get('files') or []}
        claimed = {entry['path']: entry for entry in stage.get('files') or []}
        if set(recorded) != set(claimed):
            issues.append('archive members differ from the staged inventory')
        else:
            for path, entry in claimed.items():
                if recorded[path]['sha256'] != entry['sha256'] or recorded[path]['bytes'] != entry['bytes']:
                    issues.append('archive member identity differs: ' + path)
        workspace = Path(tempfile.mkdtemp(prefix='j24-report-'))
        try:
            archive_path = workspace / archives[0]
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            archive_path.write_bytes(archive_bytes)
            extracted = workspace / 'extracted'
            report = contract.extract(archive_path, extracted, manifest)
            if not report['accepted']:
                issues.extend('archive extraction: ' + problem for problem in report['problems'])
            extracted_files = report['files']
            claimed = {entry['path']: entry for entry in stage.get('files') or []}
            if {entry['path'] for entry in extracted_files} != set(claimed):
                issues.append('extracted tree differs from the staged inventory')
            for entry in extracted_files:
                other = claimed.get(entry['path'])
                if other is None or other['sha256'] != entry['sha256'] or other['bytes'] != entry['bytes']:
                    issues.append('extracted file differs: ' + entry['path'])
            licence_path = workspace / 'licenses.json'
            if 'licenses.json' not in files:
                issues.append('licence report missing from the artifact')
                licence_path.write_text('{}', encoding='utf-8')
            else:
                licence_path.write_bytes(files['licenses.json'])
            smoke_path = workspace / 'smoke.json'
            smoke_path.write_bytes(files.get('evidence/smoke-before.json', b'{}'))
            report_audit = workspace / 'audit.json'
            tokens = [stage.get('prefixes', {}).get('install', ''), stage.get('prefixes', {}).get('staged', ''),
                      str(extracted), str(workspace)]
            command = [sys.executable, str(ROOT / 'tools/reader_distribution_unix/audit.py'),
                       '--prefix', str(extracted), '--stage', str(workspace / 'stage.json'),
                       '--label', 'report', '--output', str(report_audit), '--platform', key,
                       '--repo', str(ROOT), '--licenses', str(licence_path),
                       '--consumer-report', 'c=' + str(workspace / 'consumer-c.json'),
                       '--consumer-report', 'cxx=' + str(workspace / 'consumer-cxx.json'),
                       '--smoke', str(smoke_path), '--skip-dynamic']
            (workspace / 'stage.json').write_bytes(files['stage.json'])
            for consumer, name in (('c', 'evidence/before-unix-c.json'),
                                   ('cxx', 'evidence/before-unix-cxx.json')):
                if name not in files:
                    issues.append('missing ' + name)
                    continue
                (workspace / ('consumer-' + consumer + '.json')).write_bytes(files[name])
            for token in tokens:
                if token:
                    command.extend(['--token', token])
            if 'evidence/before-unix-c.png' in files:
                png = workspace / 'render.png'
                png.write_bytes(files['evidence/before-unix-c.png'])
                command.extend(['--png', str(png)])
            done = subprocess.run(command, capture_output=True, text=True, timeout=600)
            if done.returncode != 0:
                issues.append('re-audit from uploaded bytes failed: ' + done.stderr.strip()[:300])
            elif report_audit.is_file():
                audit_issues, _ = require_audit('report', report_audit.read_bytes(), sha, 'report')
                issues.extend(audit_issues)
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    for label in ('before', 'after', 'extracted'):
        name = 'evidence/%s-audit.json' % label
        if name not in files:
            issues.append('missing %s audit' % label)
            continue
        audit_issues, _ = require_audit(label, files[name], sha, label)
        issues.extend(audit_issues)
    for name in ('evidence/compare-before-after.json', 'evidence/compare-after-extracted.json'):
        if name not in files:
            issues.append('missing ' + name)
            continue
        comparison = json.loads(files[name].decode('utf-8'))
        if comparison.get('accepted') is not True:
            issues.append(name + ' did not accept relocation')
    dedupe = json.loads(files.get('dedupe.json', b'{}').decode('utf-8'))
    if dedupe.get('accepted') is not True:
        issues.append('dedupe report did not accept the tree')
    if dedupe.get('source_sha') != sha:
        issues.append('dedupe report belongs to another source')
    if not (dedupe.get('bytes_saved') or 0) > 0 or not dedupe.get('groups'):
        issues.append('no duplicate archive material was actually removed')
    relocation = json.loads(files.get('relocation.json', b'{}').decode('utf-8'))
    if relocation.get('accepted') is not True:
        issues.append('relocation report did not accept the copy')
    if relocation.get('source_length') == relocation.get('destination_length'):
        issues.append('relocation did not change the absolute path length')
    extracted_report = json.loads(files.get('extracted.json', b'{}').decode('utf-8'))
    if extracted_report.get('accepted') is not True:
        issues.append('archive extraction report did not accept the bytes')
    for label in ('before', 'after', 'extracted'):
        name = 'evidence/smoke-%s.json' % label
        if name not in files:
            issues.append('missing ' + name)
            continue
        smoke = json.loads(files[name].decode('utf-8'))
        if smoke.get('accepted') is not True or len(smoke.get('results') or []) != 9:
            issues.append('nine-format smoke did not accept %s' % label)
        for entry in smoke.get('results') or []:
            if entry.get('classification') != 'passed':
                issues.append('smoke %s: %s is %s' % (label, entry.get('path'),
                                                      entry.get('classification')))
    for label in ('before', 'after', 'extracted'):
        for consumer in ('c', 'cxx'):
            name = 'evidence/%s-unix-%s.json' % (label, consumer)
            if name not in files:
                issues.append('missing ' + name)
                continue
            report = json.loads(files[name].decode('utf-8'))
            if report.get('version') != stage.get('sdk_version') or report.get('abi') != stage.get('abi'):
                issues.append('%s consumer %s identity differs' % (consumer, label))
            if report.get('failures'):
                issues.append('%s consumer reported %s failures at %s' % (consumer, report['failures'], label))
    row = {'platform': key, 'stage_sha256': contract.digest_bytes(files['stage.json']),
           'pkgconfig_sha256': (stage.get('pkgconfig') or {}).get('sha256'),
           'archive_sha256': archive_sha,
           'files': len(stage.get('files') or []),
           'bytes': (stage.get('totals') or {}).get('bytes'),
           'duplicate_bytes_removed': dedupe.get('bytes_saved'),
           'duplicate_groups': len(dedupe.get('groups') or []),
           'relocated_prefix_length': relocation.get('destination_length'),
           'checks': len((stage.get('checks') or [])),
           'release_ready': not issues}
    return issues, row


if __name__ == '__main__':
    raise SystemExit(main())
