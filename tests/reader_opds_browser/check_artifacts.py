#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only strict same-source evidence for the three OPDS consumer jobs.

Every artifact and job must belong to this run, attempt and source; the ZIP digest is
recomputed from the authenticated download; the embedded report must name the same source
and must not over-grant scope; the named case outcomes must agree on all three platforms.
"""
import hashlib
import io
import json
import os
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch, pages, require  # noqa: E402

PLATFORMS = [('linux', 'ubuntu-22.04'), ('windows', 'windows-2022'), ('macos', 'macos-15')]
REQUIRED_CASES = frozenset(['browser_create', 'opds1_open', 'opds1_display_fields', 'opds1_identity', 'opds1_cursor_format', 'opds1_snapshot_links', 'opds1_link_classes', 'opds1_free_link', 'opds1_facets', 'opds1_search_advertised', 'opds1_feed_links', 'opds1_next_page', 'opds1_next_third_page', 'opds1_loop_refused', 'cursor_stale_after_advance', 'cursor_wrong_value', 'cursor_other_feed_refused', 'search_opensearch_utf8', 'search_terms_refused', 'opds2_snapshot', 'opds2_navigation', 'opds2_facet_counts', 'opds2_search_template', 'acquire_free_epub', 'acquire_duplicate', 'staged_discard', 'discard_foreign_name', 'acquire_buy_refused', 'acquire_borrow_refused', 'acquire_protected_refused', 'acquire_priced_refused', 'acquire_indirect_refused', 'acquire_sample_refused', 'acquire_fake_extension_mismatch', 'acquire_broken_published', 'acquire_cancel', 'browser_usable_after_cancel', 'busy_reentry', 'limits_max_pages', 'limits_lowered_entries', 'staging_required', 'auth_origin_accepted', 'cross_origin_redirect', 'cross_origin_credentials_dropped', 'auth_required', 'tls_available', 'tls_open', 'tls_acquire', 'import_acquire', 'import_ok', 'import_duplicate_reuses_book', 'import_descriptor_size_mismatch', 'import_media_type_refused', 'import_descriptor_required', 'import_digest_mismatch', 'import_broken_acquire', 'import_broken_rejected_by_sdk', 'import_cancelled_before_commit', 'import_library_usable_after_failure', 'import_library_open', 'discard_denied_preserves_receipt'])


def validate_job(job, source, run_id, attempt):
    require(job.get('head_sha') == source and job.get('run_id') == run_id and
            job.get('run_attempt') == attempt, 'job identity differs')
    require(job.get('status') == 'completed' and job.get('conclusion') == 'success',
            'job not completed successfully')


def validate_artifact(artifact, data, source, run_id):
    require(type(artifact.get('id')) is int and artifact['id'] > 0, 'invalid artifact ID')
    require(artifact.get('expired') is False and artifact.get('size_in_bytes', 0) > 0,
            'artifact expired or empty')
    require(datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) >
            datetime.now(timezone.utc), 'artifact expiry elapsed')
    require(artifact['workflow_run']['id'] == run_id and
            artifact['workflow_run']['head_sha'] == source, 'artifact run/source differs')
    require(len(data) == artifact['size_in_bytes'], 'ZIP size differs')
    require('sha256:' + hashlib.sha256(data).hexdigest() == artifact['digest'],
            'ZIP digest differs')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def validate_members(names):
    require(len(names) == len(set(names)), 'duplicate ZIP member')
    for name in names:
        path = PurePosixPath(name)
        require(not path.is_absolute() and '..' not in path.parts and
                '\\' not in name and ':' not in name and str(path) == name.rstrip('/'),
                'unsafe or ambiguous ZIP member')
    reports = [n for n in names if PurePosixPath(n).name == 'result.json']
    require(reports == ['opds-evidence/result.json'], 'missing or duplicate report')


def validate_cases(report):
    cases = report.get('cases', [])
    ids = [c.get('id') for c in cases]
    require(len(cases) >= len(REQUIRED_CASES) and report.get('checks') == len(cases), 'case count differs')
    require(all(isinstance(i, str) and i for i in ids) and len(set(ids)) == len(ids),
            'invalid or duplicate case ID')
    require(REQUIRED_CASES <= set(ids), 'required original/review case missing')
    require(all(c.get('ok') is True for c in cases), 'failed or malformed case')
    return [[c['id'], c['ok']] for c in cases]


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud only')
    run_id = int(os.environ['GITHUB_RUN_ID'])
    attempt = int(os.environ['GITHUB_RUN_ATTEMPT'])
    source = os.environ['GITHUB_SHA']
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    summary = {'accepted': False, 'package': 'EXReaderOpdsBrowser 0.1.0', 'source_sha': source,
               'run_id': run_id, 'attempt': attempt, 'artifacts': [], 'jobs': [], 'problems': [],
               'granted_platforms': [], 'macos_accepted': False, 'performance_claimed': False,
               'host_ui_accepted': False, 'sdk_changed': False, 'schema_changed': False}
    try:
        run = fetch('actions/runs/%d' % run_id)
        require(run['head_sha'] == source, 'run source differs')
        require(int(run['run_attempt']) == attempt, 'run attempt differs')
        require(run['path'] == '.github/workflows/reader-opds-browser.yml', 'caller workflow differs')
        jobs = pages('actions/runs/%d/attempts/%d/jobs' % (run_id, attempt), 'jobs')
        artifacts = pages('actions/runs/%d/artifacts' % run_id, 'artifacts')
        outcomes = {}
        for platform, runner in PLATFORMS:
            name = 'reader-opds-browser-%s-%d-%d' % (platform, run_id, attempt)
            job_name = 'opds consumers (%s)' % runner
            matches = [a for a in artifacts if a['name'] == name]
            require(len(matches) == 1, 'missing/duplicate artifact ' + name)
            artifact = matches[0]
            matches = [j for j in jobs if j['name'] == job_name]
            require(len(matches) == 1, 'missing/duplicate job ' + job_name)
            job = matches[0]
            validate_job(job, source, run_id, attempt)
            require(not artifact['expired'] and artifact['size_in_bytes'] > 0,
                    'artifact expired or empty: ' + name)
            require(artifact['workflow_run']['head_sha'] == source, 'artifact source differs: ' + name)
            require(artifact['workflow_run']['id'] == run_id, 'artifact run differs: ' + name)
            with tempfile.TemporaryFile() as stream:
                download_artifact_zip(artifact['id'], stream)
                stream.seek(0)
                data = stream.read()
            validate_artifact(artifact, data, source, run_id)
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                validate_members(archive.namelist())
                report = json.loads(archive.read('opds-evidence/result.json'), object_pairs_hook=unique_object)
                names = [n for n in archive.namelist()
                         if n.startswith('opds-consumer/') and not n.endswith('/') and
                         Path(n).name in ('opds-consumer', 'opds-consumer.exe',
                                          'opds-import-consumer', 'opds-import-consumer.exe')]
                require(len(names) == 2, 'consumer binaries missing from ' + name)
                embedded = {}
                for entry in names:
                    payload = archive.read(entry)
                    embedded[Path(entry).name] = (len(payload), hashlib.sha256(payload).hexdigest())
                reported = {c['name']: (int(c['bytes']), c['sha256']) for c in report['consumers']}
                require(len(report['consumers']) == len(reported) == 2,
                        'duplicate consumer identity')
                expected = {'opds-consumer', 'opds-import-consumer'}
                if platform == 'windows':
                    expected = {n + '.exe' for n in expected}
                require(set(embedded) == expected and all(v[0] > 0 for v in embedded.values()),
                        'wrong or empty consumer binaries')
                require(embedded == reported, 'consumer binaries differ from the report: ' + name)
            require(report.get('accepted') is True, 'report refused: ' + name)
            require(report.get('package') == 'EXReaderOpdsBrowser 0.1.0', 'wrong package')
            require(report['source_sha'] == source, 'report source differs: ' + name)
            require(int(report['run_id']) == run_id and int(report['attempt']) == attempt,
                    'report run identity differs: ' + name)
            require(report['platform'] == platform, 'report platform differs: ' + name)
            require(report['sdk_changed'] is False and report['schema_changed'] is False,
                    'report claims frozen tree changes')
            require(int(report['checks']) > 0 and report['cases'], 'report has no cases: ' + name)
            require(report['origin_isolation']['plain_requests_with_authorization'] == 0,
                    'credentials reached the plain origin: ' + name)
            require(report['origin_isolation']['tls_requests'] > 0, 'no TLS request served: ' + name)
            outcomes[platform] = validate_cases(report)
            summary['artifacts'].append({k: artifact[k] for k in
                                         ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
            summary['jobs'].append({k: job[k] for k in ('id', 'name', 'conclusion')})
            summary.setdefault('consumers', {})[platform] = sorted(
                [n, size, digest] for n, (size, digest) in embedded.items())
            summary['granted_platforms'].append(platform)
        require(len(outcomes) == 3, 'missing platform outcomes')
        require(len({a['id'] for a in summary['artifacts']}) == 3, 'reused artifact ID')
        reference = outcomes['linux']
        for platform in ('windows', 'macos'):
            require(outcomes[platform] == reference, 'case outcomes differ on ' + platform)
        require(len(reference) >= 30, 'too few named cases: %d' % len(reference))
        summary['macos_accepted'] = True
        summary['accepted'] = True
        summary['case_count'] = len(reference)
        summary['case_ids'] = [entry[0] for entry in reference]
    except Exception as error:  # noqa: BLE001 - every failure becomes retained evidence
        summary['problems'].append(str(error))
    (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'accepted': summary['accepted'], 'problems': summary['problems']}, ensure_ascii=False))
    raise SystemExit(0 if summary['accepted'] else 1)


if __name__ == '__main__':
    main()
