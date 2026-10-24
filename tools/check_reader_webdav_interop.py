#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only summary of this run's real WebDAV service interop artifacts.

Binds every service report to this run/attempt/source and its authenticated
artifact digest, then re-derives the HTTP facts from the server's own raw access
log instead of trusting the harness summary. Failures are kept and reported."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import ssl
import stat
import tempfile
import zipfile

from check_parallel_integration import download_artifact_zip, fetch, pages, require

WORKFLOW = '.github/workflows/reader-webdav-interop.yml'
HARNESS = Path(__file__).resolve().parent.parent / 'tests' / 'reader_webdav_interop' / 'run_interop.py'
SUMMARY_JOB = 'interop summary'


def harness():
    spec = importlib.util.spec_from_file_location('reader_webdav_interop', HARNESS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_archive(archive):
    names = archive.namelist()
    require(0 < len(names) <= 20000 and len(names) == len(set(names)), 'ZIP member count/uniqueness differs')
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        require(not path.is_absolute() and '..' not in path.parts and '\\' not in info.filename and
                ':' not in info.filename and '\x00' not in info.filename and
                stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG, stat.S_IFDIR), 'unsafe ZIP member')
        require(not info.filename.endswith('.key'), 'private key member present')


def access_lines(data, agent):
    lines = []
    for line in data.decode('utf-8', 'replace').splitlines():
        parts = line.split('\t')
        require(len(parts) == 8, 'malformed server access log line')
        _, _, status, depth, condition, ua, _, request = parts
        if ua == agent:
            continue
        words = request.split(' ')
        lines.append({'status': status, 'depth': depth, 'if_none_match': condition, 'method': words[0],
                      'target': words[1] if len(words) > 1 else '', 'line': line})
    return lines


def verify_service(service, archive, source, run_id, attempt, module):
    # upload-artifact roots members at the evidence folder's common ancestor.
    prefix = 'interop-evidence/' + service + '/'
    report_bytes = archive.read(prefix + 'result.json')
    require(0 < len(report_bytes) <= 32 * 1024 * 1024, 'report size differs')
    report = json.loads(report_bytes)
    require(report.get('schema') == 'reader-webdav-interop-service-v1' and report.get('service') == service,
            'report schema/service differs')
    require(report.get('source_sha') == source and str(report.get('run_id')) == str(run_id) and
            str(report.get('attempt')) == str(attempt), 'report source/run/attempt differs')
    for flag in ('real_user_cloud', 'public_writable_server', 'six_platform_client_accepted',
                 'inherits_tls_fixture_conclusions', 'complete_product'):
        require(report.get(flag) is False, 'report overclaims ' + flag)
    checks = report.get('checks', [])
    ids = [c.get('id') for c in checks]
    summary = {'service': service, 'title': report.get('service_title'), 'report_sha256': hashlib.sha256(report_bytes).hexdigest(),
               'harness_accepted': report.get('accepted') is True, 'count': len(checks),
               'passed': sum(1 for c in checks if c.get('pass') is True),
               'failed': [{'id': c.get('id'), 'error': c.get('error')} for c in checks if c.get('pass') is not True],
               'problems': report.get('problems', []), 'findings': report.get('findings', []),
               'image': report.get('image'), 'versions': report.get('versions'), 'tls': report.get('tls'),
               'client_backend': report.get('client_backend')}
    pinned = module.SERVICES[service]['image']
    image = report.get('image') or {}
    require(image.get('reference') == pinned and image.get('pinned_index_digest') == pinned.split('@', 1)[1] and
            any(d.endswith('@' + image['pinned_index_digest']) for d in image.get('repo_digests', [])) and
            image.get('image_id') == image.get('container_image_id'), 'service image is not the pinned digest')
    require(ids == module.EXPECTED, 'check identity/order differs')
    tls = report.get('tls') or {}
    der_text = archive.read(prefix + 'tls/trusted.crt').decode('ascii')
    require(tls.get('certificate_sha256') == hashlib.sha256(ssl.PEM_cert_to_DER_cert(der_text)).hexdigest() and
            tls.get('host') == module.SERVICES[service]['host'], 'TLS identity differs from the preserved certificate')
    # Independent of the harness: the server's own record of module requests.
    lines = access_lines(archive.read(prefix + 'http/access.log'), module.HARNESS_UA)
    counts = {}
    for line in lines:
        key = '%s %s' % (line['method'], line['status'])
        counts[key] = counts.get(key, 0) + 1
    require(lines and {l['method'] for l in lines} <= {'PROPFIND', 'GET', 'PUT', 'MKCOL'}, 'module method set differs')
    require(all(l['if_none_match'] == '*' for l in lines if l['method'] == 'PUT'), 'unconditional module PUT in server log')
    require(all(l['depth'] == '1' for l in lines if l['method'] == 'PROPFIND'), 'non Depth-one PROPFIND in server log')
    require(counts.get('PUT 412', 0) >= 1 and counts.get('MKCOL 405', 0) >= 1 and counts.get('MKCOL 409', 0) >= 1,
            'server log lacks real 412/405/409 answers')
    require(report.get('http_summary') in (None, counts), 'harness HTTP summary differs from the server log')
    recorded = {l['line'] for l in lines}
    for check in checks:
        for raw in (check.get('http') or {}).get('lines', []):
            require(raw in recorded, 'check cites a request absent from the server log')
    for info in archive.infolist():
        if info.is_dir():
            continue
        data = archive.read(info)
        require(not re.search(rb'Authorization:\s*Basic\s+[A-Za-z0-9+/=]{8,}', data) and
                b'NEXTCLOUD_ADMIN_PASSWORD=' not in data, 'credential-shaped content in ' + info.filename)
    summary['server_log'] = {'module_requests': len(lines), 'by_method_status': counts}
    summary['verified'] = True
    summary['accepted'] = summary['harness_accepted'] and not summary['failed'] and not summary['problems']
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'verify only in GitHub Actions')
    source = os.environ['GITHUB_SHA']
    run_id, attempt = int(os.environ['GITHUB_RUN_ID']), int(os.environ['GITHUB_RUN_ATTEMPT'])
    args.output.mkdir(parents=True, exist_ok=False)
    module = harness()
    jobs_expected = {'real WebDAV interop (%s)' % s: s for s in module.SERVICES}
    result = {'schema': 'reader-webdav-interop-summary-v1', 'accepted': False, 'source_sha': source, 'run_id': run_id,
              'attempt': attempt, 'workflow': WORKFLOW, 'start_point': module.START,
              'scope': 'Job-local pinned real WebDAV services against installed EXReaderWebDAV/Revisions/Sync on Linux',
              'real_user_cloud': False, 'six_platform_client_accepted': False, 'windows_winhttp_covered': False,
              'inherits_tls_fixture_conclusions': False, 'complete_product': False,
              'jobs': [], 'services': [], 'problems': []}
    try:
        run = fetch(f'actions/runs/{run_id}')
        require(run.get('id') == run_id and run.get('head_sha') == source and run.get('run_attempt') == attempt and
                run.get('path') == WORKFLOW and run.get('event') in ('push', 'workflow_dispatch'), 'caller identity differs')
        jobs = pages(f'actions/runs/{run_id}/attempts/{attempt}/jobs', 'jobs')
        require({job['name'] for job in jobs} == set(jobs_expected) | {SUMMARY_JOB}, 'job set differs')
        for job in jobs:
            require(job.get('head_sha') == source and job.get('run_attempt') == attempt, 'job source/attempt differs')
            if job['name'] in jobs_expected:
                result['jobs'].append({k: job.get(k) for k in ('id', 'name', 'status', 'conclusion', 'started_at',
                                                                'completed_at', 'html_url')})
        artifacts = pages(f'actions/runs/{run_id}/artifacts', 'artifacts')
        for service in sorted(module.SERVICES):
            name = f'reader-webdav-interop-{service}-{run_id}-{attempt}'
            found = [a for a in artifacts if a['name'] == name]
            if len(found) != 1:
                result['problems'].append(service + ': artifact missing or duplicated')
                continue
            artifact = found[0]
            entry = {k: artifact[k] for k in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')}
            try:
                require(artifact.get('expired') is False and artifact['workflow_run'].get('head_sha') == source and
                        re.fullmatch(r'sha256:[0-9a-f]{64}', artifact.get('digest') or '') is not None,
                        'artifact expired or identity/digest differs')
                with tempfile.TemporaryFile() as stream:
                    download_artifact_zip(artifact['id'], stream)
                    size = stream.tell()
                    stream.seek(0)
                    digest = hashlib.sha256()
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(block)
                    require(size == artifact['size_in_bytes'] and 'sha256:' + digest.hexdigest() == artifact['digest'],
                            'downloaded ZIP size/digest differs')
                    stream.seek(0)
                    with zipfile.ZipFile(stream) as archive:
                        validate_archive(archive)
                        entry.update(verify_service(service, archive, source, run_id, attempt, module))
            except Exception as error:
                entry.update(verified=False, accepted=False, error=str(error))
                result['problems'].append('%s: %s' % (service, error))
            job = next((j for j in result['jobs'] if jobs_expected.get(j['name']) == service), None)
            entry['job'] = job
            if not job or job.get('conclusion') != 'success':
                entry['accepted'] = False
            result['services'].append(entry)
        result['accepted'] = (not result['problems'] and len(result['services']) == len(module.SERVICES) and
                              all(s.get('accepted') is True for s in result['services']))
    except Exception as error:
        result['problems'].append(str(error))
    finally:
        (args.output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'accepted': result['accepted'], 'problems': result['problems'],
                          'services': [{k: s.get(k) for k in ('service', 'accepted', 'passed', 'count', 'failed',
                                                              'findings', 'server_log')}
                                       for s in result['services']]}, ensure_ascii=False, indent=1))
    raise SystemExit(0 if result['accepted'] else 1)


if __name__ == '__main__':
    main()
