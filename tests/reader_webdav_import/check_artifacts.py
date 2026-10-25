#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify the same-run WebDAV import artifacts through the GitHub API.

Each platform artifact must be present, unexpired, byte-identical to its API
digest and contain a strict result report bound to this exact source, run and
attempt. The verifier first proves it rejects altered reports.
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile

API = 'https://api.github.com'
PLATFORMS = ('Windows', 'Linux', 'macOS')
MIN_CHECKS = 1
REQUIRED = {
    'format_sample.epub', 'format_pdf-public-text.pdf', 'format_comic.cbz', 'format_sample.txt',
    'independent_sdk_readback_nine_originals_and_unicode_titles',
    'same_remote_name_different_content_keeps_both',
    'duplicate_keeps_existing_book_title_and_survives_every_failure_cleanup',
    'corrupted_after_download_flip', 'corrupted_after_download_delete',
    'invalid_book_rejected_by_sdk_without_row_or_leftover',
    'redirect_foreign_origin', 'untrusted_certificate', 'hostname_mismatch', 'http_401_requires_credentials',
    'short_read_removes_partial_file', 'received_length_differs_from_listing',
    'reflow_format_stream_over_32_mib_stopped_and_cleaned',
    'streaming_format_declared_over_128_mib_refused_before_request',
    'cancel_before_network', 'cancel_during_download_removes_temporary',
    'cancel_between_phases_discard_never_opens_library',
    'cancel_sweep_commit_boundary_中文 书名.epub',
    'credentials_stay_at_configured_origin_and_no_foreign_request',
    'independent_c_and_cpp_consumers_from_installed_package',
    'invalid_webdav_argument_allows_null_error_without_network',
    'real_cleanup_refusal_keeps_receipt_and_owned_retry_without_deleting_sdk_book',
    'all_owned_download_allocations_fail_before_network_without_published_orphans',
    'explicit_and_derived_title_oom_never_silently_import_with_other_metadata',
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *unused):
        return None


def call(path, token):
    req = urllib.request.Request(API + path, headers={
        'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'reader-webdav-import-evidence'})
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read()


def download(repo, artifact_id, token):
    req = urllib.request.Request(API + '/repos/%s/actions/artifacts/%s/zip' % (repo, artifact_id), headers={
        'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'reader-webdav-import-evidence'})
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code not in (301, 302, 303, 307, 308) or not exc.headers.get('Location'):
            raise
        with urllib.request.urlopen(exc.headers['Location'], timeout=120) as response:
            return response.read()


def require_report(report, source, run_id, attempt):
    if not isinstance(report, dict) or report.get('accepted') is not True:
        raise ValueError('report not accepted')
    if report.get('source_sha') != source or str(report.get('run_id')) != run_id or str(report.get('attempt')) != attempt:
        raise ValueError('report source or run identity differs')
    checks = report.get('checks')
    if not isinstance(checks, list) or len(checks) < MIN_CHECKS or report.get('count') != len(checks):
        raise ValueError('check count differs')
    if any(not isinstance(c, dict) or c.get('pass') is not True or not isinstance(c.get('id'), str) for c in checks):
        raise ValueError('failed or malformed check')
    ids = [c['id'] for c in checks]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate check ids')
    missing = REQUIRED - set(ids)
    if missing:
        raise ValueError('required checks absent: %s' % sorted(missing))
    if report.get('complete_product') is not False:
        raise ValueError('scope claim must stay bounded')


def negative_selftest():
    good = {'accepted': True, 'source_sha': 's', 'run_id': '1', 'attempt': '1', 'count': len(REQUIRED),
            'complete_product': False, 'checks': [{'id': i, 'pass': True} for i in sorted(REQUIRED)]}
    require_report(good, 's', '1', '1')
    failed_first = [dict(good['checks'][0], **{'pass': False})] + good['checks'][1:]
    altered = [dict(good, accepted='true'), dict(good, source_sha='o'), dict(good, run_id='2'), dict(good, attempt='2'),
               dict(good, count=1), dict(good, checks=good['checks'][1:], count=len(REQUIRED) - 1),
               dict(good, checks=failed_first), dict(good, complete_product=True),
               dict(good, checks=good['checks'] + [good['checks'][0]], count=len(REQUIRED) + 1)]
    for value in altered:
        try:
            require_report(value, 's', '1', '1')
        except ValueError:
            continue
        raise AssertionError('altered report accepted')
    return len(altered)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    token, repo = os.environ.get('GH_TOKEN', ''), os.environ.get('GITHUB_REPOSITORY', '')
    run_id, attempt = os.environ.get('GITHUB_RUN_ID', ''), os.environ.get('GITHUB_RUN_ATTEMPT', '')
    source = os.environ.get('GITHUB_SHA', '')
    if not (token and repo and run_id and attempt and source):
        print('missing GitHub environment')
        return 2
    os.makedirs(args.output, exist_ok=True)
    record = {'run_id': run_id, 'attempt': attempt, 'source': source, 'ok': True, 'failures': [], 'artifacts': [],
              'altered_reports_rejected': negative_selftest(),
              'checked_at': dt.datetime.now(dt.timezone.utc).isoformat()}
    suffix = '-%s-%s' % (run_id, attempt)
    artifacts = []
    for _ in range(12):
        artifacts = json.loads(call('/repos/%s/actions/runs/%s/artifacts?per_page=100' % (repo, run_id), token))['artifacts']
        if all('reader-webdav-import-%s%s' % (p, suffix) in {a['name'] for a in artifacts} for p in PLATFORMS):
            break
        time.sleep(10)
    for platform_name in PLATFORMS:
        name = 'reader-webdav-import-%s%s' % (platform_name, suffix)
        item = {'os': platform_name, 'name': name}
        record['artifacts'].append(item)
        matches = [a for a in artifacts if a['name'] == name]
        artifact = matches[0] if len(matches) == 1 else None
        if not artifact:
            record['failures'].append(name + ': missing')
            continue
        item.update(id=artifact.get('id'), size_in_bytes=artifact.get('size_in_bytes'), digest=artifact.get('digest'),
                    expires_at=artifact.get('expires_at'))
        try:
            run = json.loads(call('/repos/%s/actions/runs/%s' % (repo, run_id), token))
            if run['head_sha'] != source or str(run['run_attempt']) != attempt or run['path'] != '.github/workflows/reader-webdav-import.yml':
                raise ValueError('foreign run/source/workflow')
            jobs = json.loads(call('/repos/%s/actions/runs/%s/attempts/%s/jobs?per_page=100' % (repo, run_id, attempt), token))['jobs']
            runner = {'Linux': 'ubuntu-22.04', 'Windows': 'windows-2022', 'macOS': 'macos-15'}[platform_name]
            producers = [j for j in jobs if j['name'] == 'WebDAV import (%s)' % runner]
            if len(producers) != 1 or producers[0]['head_sha'] != source or producers[0]['status'] != 'completed' or producers[0]['conclusion'] != 'success':
                raise ValueError('real producer did not complete successfully')
            item['job_id'] = producers[0]['id']
            if artifact['workflow_run']['head_sha'] != source or str(artifact['workflow_run']['id']) != run_id:
                raise ValueError('artifact belongs to another source/run')
            if (type(artifact['id']) is not int or type(artifact['size_in_bytes']) is not int or artifact['size_in_bytes'] <= 0
                    or artifact.get('expired') is not False or not re.fullmatch(r'sha256:[0-9a-f]{64}', artifact.get('digest') or '')):
                raise ValueError('strict artifact metadata missing')
            if dt.datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) <= dt.datetime.now(dt.timezone.utc):
                raise ValueError('expired')
            data = download(repo, artifact['id'], token)
            item['sha256'], item['downloaded_bytes'] = hashlib.sha256(data).hexdigest(), len(data)
            if 'sha256:' + item['sha256'] != artifact['digest'] or len(data) != artifact['size_in_bytes']:
                raise ValueError('digest or size differs from the API record')
            bundle = zipfile.ZipFile(io.BytesIO(data))
            result = [n for n in bundle.namelist() if n.endswith('wi-evidence/result.json')]
            guards = [n for n in bundle.namelist() if n.endswith('wi-guards/guards.json')]
            if len(result) != 1 or len(guards) != 1:
                raise ValueError('result or guards report absent')
            report = json.loads(bundle.read(result[0]).decode('utf-8'))
            require_report(report, source, run_id, attempt)
            for stem, key in (('cloud-probe', 'probe_sha256'), ('cloud-review-probe', 'review_probe_sha256')):
                programs = [n for n in bundle.namelist() if n.endswith('wi-consumer/' + stem + ('.exe' if platform_name == 'Windows' else ''))]
                if len(programs) != 1 or hashlib.sha256(bundle.read(programs[0])).hexdigest() != report[key]:
                    raise ValueError('consumer bytes differ from report')
            if json.loads(bundle.read(guards[0]).decode('utf-8')).get('ok') is not True:
                raise ValueError('guards not ok')
            if not any(n.endswith('wi-prefix/include/reader_cloud_import.h') for n in bundle.namelist()):
                raise ValueError('installed package absent from artifact')
            item['checks'] = len(report['checks'])
        except Exception as exc:
            item['error'] = str(exc)
            record['failures'].append('%s: %s' % (name, exc))
    record['ok'] = not record['failures']
    with open(os.path.join(args.output, 'artifacts.json'), 'w', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2, sort_keys=True)
    print('artifact evidence', 'ok' if record['ok'] else 'FAILED: %s' % record['failures'])
    return 0 if record['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
