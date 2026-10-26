#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict same-run artifact verification for the GTK performance package.

Runs inside GitHub Actions: it asks the API for this run's jobs and artifacts,
downloads the package ZIP with the authenticated CLI, recomputes SHA-256 over the
ZIP and every member, and refuses missing, expired, cross-source, cross-attempt,
summary-mismatched or under-covered evidence.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

WORKFLOW = '.github/workflows/reader-composition-perf-gtk.yml'
PERF_JOB = 'GTK product performance sampling (ubuntu-22.04)'
VERIFY_JOB = 'artifact identity verification'
REQUIRED_MEMBERS = {'report.json', 'summary.json', 'samples.json', 'samples.csv',
                    'launches.json', 'environment.json', 'plan.json', 'corpus.json',
                    'calibration.json', 'guards.json', 'import-corpus.json', 'bundle.json'}
MIN_LAUNCHES = 30
CORE_METRICS = ('startup_shelf_rows', 'startup_key_response', 'shelf_selection_move',
                'search_title_unique', 'search_author_literal', 'search_empty', 'search_clear',
                'open_book_applied', 'open_book_painted', 'page_turn_forward',
                'page_turn_backward', 'resume_frame_applied', 'resume_frame_painted',
                'import_complete', 'import_input_response', 'import_resize_response')


def require(value, message):
    if not value:
        raise SystemExit('verification refused: ' + message)


def token():
    value = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    require(value, 'GH_TOKEN is required')
    return value


def api(path):
    url = 'https://api.github.com/repos/' + os.environ['GITHUB_REPOSITORY'] + ('/' + path if path else '')
    request = urllib.request.Request(url, headers={
        'Authorization': 'Bearer ' + token(),
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def pages(path, key):
    records, total, page = [], None, 1
    while total is None or len(records) < total:
        response = api(path + '?per_page=100&page=%d' % page)
        total = response['total_count']
        require(isinstance(total, int) and 0 <= total <= 10000, 'unstable pagination count')
        batch = response[key]
        require(isinstance(batch, list) and (batch or len(records) == total), 'incomplete API pagination')
        records.extend(batch)
        require(len(records) <= total, 'pagination exceeds the declared count')
        page += 1
    return records


def download(artifact_id, destination):
    require(isinstance(artifact_id, int) and artifact_id > 0, 'artifact id must be positive')
    command = ['gh', 'api', 'repos/%s/actions/artifacts/%d/zip' % (
        os.environ['GITHUB_REPOSITORY'], artifact_id)]
    with destination.open('wb') as handle:
        subprocess.run(command, stdout=handle, stderr=subprocess.PIPE, check=True, timeout=600)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('run the artifact verifier on a GitHub Actions runner')
    source = os.environ['GITHUB_SHA']
    run_id = int(os.environ['GITHUB_RUN_ID'])
    attempt = int(os.environ['GITHUB_RUN_ATTEMPT'])

    record = api('actions/runs/%d' % run_id)
    require(record['id'] == run_id, 'run id differs')
    require(record['head_sha'] == source, 'run head differs from the verified source')
    require(record['run_attempt'] == attempt, 'run attempt differs')
    workflow_ref = os.environ['GITHUB_WORKFLOW_REF'].split('@', 1)[0]
    prefix = os.environ['GITHUB_REPOSITORY'] + '/'
    require(workflow_ref.startswith(prefix), 'caller workflow repository differs')
    require(record['path'].split('@')[0] == workflow_ref[len(prefix):], 'run workflow path differs')

    jobs = pages('actions/runs/%d/jobs' % run_id, 'jobs')
    # A caller can contain other jobs; reusable job names receive a caller prefix.
    def matching(name):
        return [job for job in jobs if job['name'] == name or job['name'].endswith(' / ' + name)]
    perf = matching(PERF_JOB)
    verifier = matching(VERIFY_JOB)
    require(len(perf) == 1, 'the sampling job must appear exactly once')
    require(len(verifier) == 1, 'the verification job must appear exactly once')
    require(verifier[0]['head_sha'] == source and verifier[0]['run_id'] == run_id
            and verifier[0]['run_attempt'] == attempt, 'verification job source or attempt differs')
    perf = perf[0]
    require(perf['status'] == 'completed' and perf['conclusion'] == 'success',
            'sampling job did not succeed: %s/%s' % (perf['status'], perf['conclusion']))
    require(perf['head_sha'] == source and perf['run_id'] == run_id and perf['run_attempt'] == attempt,
            'sampling job source or attempt differs')

    artifacts = pages('actions/runs/%d/artifacts' % run_id, 'artifacts')
    expected_name = 'reader-composition-perf-gtk-%d-%d' % (run_id, attempt)
    matches = [artifact for artifact in artifacts if artifact['name'] == expected_name]
    require(len(matches) == 1, 'expected exactly one current-attempt artifact, found %d' % len(matches))
    artifact = matches[0]
    require(artifact['expired'] is False, 'artifact is expired')
    require(isinstance(artifact['size_in_bytes'], int) and artifact['size_in_bytes'] > 0,
            'artifact is empty')
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', artifact.get('digest') or '') is not None,
            'artifact digest is missing or malformed')
    require(artifact['workflow_run']['id'] == run_id and artifact['workflow_run']['head_sha'] == source,
            'artifact belongs to another run or source')
    require(isinstance(artifact['id'], int) and artifact['id'] > 0, 'artifact id differs')

    archive_path = output / 'artifact.zip'
    download(int(artifact['id']), archive_path)
    zip_digest = sha256_file(archive_path)
    require(zip_digest == (artifact.get('digest') or '').split(':', 1)[-1],
            'downloaded ZIP digest differs from the API digest')
    require(archive_path.stat().st_size == artifact['size_in_bytes'],
            'downloaded ZIP size differs from the API size')

    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        require(0 < len(infos) <= 10000 and len({info.filename for info in infos}) == len(infos),
                'ZIP member count or uniqueness differs')
        for info in infos:
            path = PurePosixPath(info.filename)
            require(not path.is_absolute() and '..' not in path.parts and '\\' not in info.filename
                    and ':' not in info.filename and '\x00' not in info.filename
                    and stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG, stat.S_IFDIR),
                    'unsafe ZIP member: %s' % info.filename)
        members = {info.filename: info for info in infos if not info.is_dir()}
        missing = REQUIRED_MEMBERS - set(members)
        require(not missing, 'required evidence members are missing: %r' % sorted(missing))
        bundle = json.loads(archive.read(members['bundle.json']))
        listed = bundle['files']
        require(set(listed) | {'bundle.json'} == set(members),
                'ZIP members and the declared bundle differ: %r' % sorted(
                    (set(listed) | {'bundle.json'}) ^ set(members)))
        for name, expected in sorted(listed.items()):
            data = archive.read(members[name])
            require(len(data) == expected['bytes'], 'member size differs: ' + name)
            require(sha256_bytes(data) == expected['sha256'], 'member digest differs: ' + name)
        report = json.loads(archive.read(members['report.json']))
        summary = json.loads(archive.read(members['summary.json']))
        samples = json.loads(archive.read(members['samples.json']))
        launches = json.loads(archive.read(members['launches.json']))['launches']

    require(report['accepted'] is True and not report.get('problems'), 'report refused the run')
    require(report['complete_product'] is False, 'the sampler cannot grant product completion')
    require(report['source_sha'] == source, 'report source differs')
    require(str(report['run_id']) == str(run_id) and str(report['attempt']) == str(attempt),
            'report run or attempt differs')
    require(summary['source_sha'] == source and str(summary['run_id']) == str(run_id)
            and str(summary['attempt']) == str(attempt), 'summary identity differs')
    require(samples['source_sha'] == source, 'samples source differs')
    require(len(launches) >= MIN_LAUNCHES, 'fewer than %d completed launches' % MIN_LAUNCHES)
    require(len(launches) == summary['launches']['completed'] == report['launches'],
            'launch counts differ between evidence files')
    require(all(row.get('process_exit') == 0 for row in launches), 'a launch did not exit cleanly')
    require(all(row.get('vm_hwm_kb') for row in launches), 'a launch has no RSS high-water mark')
    for metric in CORE_METRICS:
        entry = report['metrics'].get(metric)
        require(entry is not None, 'metric missing from the report: ' + metric)
        require(isinstance(entry, dict) and isinstance(entry.get('expected'), int)
                and isinstance(entry.get('ok'), int), 'metric record is malformed: ' + metric)
        require(entry['expected'] > 0 and entry['ok'] >= entry['expected'],
                'metric coverage differs: ' + metric)
        values = summary['metrics'][metric]
        require(values['count'] == entry['ok'] and len(values['samples_ms']) == values['count'],
                'metric samples were filtered: ' + metric)
    require(len(samples['samples']) == len(samples['plan']), 'plan and samples differ')
    require(all(row['outcome'] == 'ok' for row in samples['samples']),
            'a planned sample failed or was missing')
    guards = summary['guards']
    require(guards['head'] == source and guards['github_sha'] == source
            and bool(guards['components']), 'source component identities are missing')

    verified = {
        'schema': 1, 'source_sha': source, 'run_id': run_id, 'attempt': attempt,
        'workflow': WORKFLOW,
        'jobs': [{'name': job['name'], 'status': job['status'], 'conclusion': job['conclusion'],
                  'id': job['id']} for job in jobs],
        'artifact': {
            'name': artifact['name'], 'id': artifact['id'],
            'bytes': artifact['size_in_bytes'], 'digest': artifact['digest'],
            'zip_sha256': zip_digest, 'expires_at': artifact['expires_at'],
            'members': len(members), 'bundle_members': len(listed)},
        'report': {'accepted': report['accepted'], 'launches': report['launches'],
                   'samples': report['samples'], 'checks': len(report['checks']),
                   'metrics': report['metrics']},
        'observations': {metric: {'count': summary['metrics'][metric]['count'],
                                  'min_ms': summary['metrics'][metric]['min_ms'],
                                  'p50_ms': summary['metrics'][metric]['p50_ms'],
                                  'p95_ms': summary['metrics'][metric]['p95_ms'],
                                  'max_ms': summary['metrics'][metric]['max_ms']}
                         for metric in sorted(summary['metrics'])},
        'package': summary['environment']['payload'],
        'archive': summary['environment'].get('package'),
        'corpus': {'books': summary['corpus']['books'],
                   'long_book_bytes': summary['corpus']['long_book_bytes'],
                   'total_original_bytes': summary['corpus']['total_original_bytes'],
                   'corpus_sha256': summary['environment']['seed']['corpus_sha256']},
        'rss_kb': {'per_launch': summary['rss']['per_launch_kb'],
                   'p50': summary['rss']['p50_kb'], 'max': summary['rss']['max_kb']},
        'paint_events': summary['paint']['total'],
        'calibration': summary['calibration'],
        'verified_by': VERIFY_JOB,
    }
    (output / 'verified.json').write_text(json.dumps(verified, indent=2) + '\n')
    print(json.dumps(verified, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
