#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Authenticate the six same-run delivery artifacts and aggregate their verdicts."""
import argparse
import datetime
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).absolute().parents[2] / 'tools' / 'reader_wave3_package'))
from diagnostics import candidate_identity, matrix_markdown

TARGETS = ('windows', 'linux', 'macos', 'android', 'iphone', 'ipad')
PREFIX = 'reader-wave3-s20-'


def api(url, token):
    request = urllib.request.Request(url, headers={
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'reader-wave3-s20-summary',
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode('utf-8'))


def artifacts(server, repository, run, token):
    values, page = [], 1
    while True:
        url = server + '/repos/' + repository + '/actions/runs/' + run + '/artifacts?per_page=100&page=' + str(page)
        payload = api(url, token)
        values.extend(payload.get('artifacts') or [])
        if len(payload.get('artifacts') or []) < 100:
            return values
        page += 1


def local_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def locate(root, relative):
    """Find exactly one uploaded evidence file without assuming the archive layout."""
    matches = sorted(path for path in Path(root).rglob(relative) if path.is_file())
    if len(matches) != 1:
        return None
    return matches[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--targets', type=Path, required=True, help='Directory holding <artifact-name>/s20-<target>')
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run', default=os.environ.get('GITHUB_RUN_ID', ''))
    parser.add_argument('--attempt', default=os.environ.get('GITHUB_RUN_ATTEMPT', '1'))
    args = parser.parse_args(argv)
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    server = os.environ.get('GITHUB_API_URL', 'https://api.github.com')
    repository = os.environ.get('GITHUB_REPOSITORY', '')
    problems, results = [], {}
    if not token:
        problems.append('missing GH_TOKEN for the artifact API')
    if not args.run or not repository:
        problems.append('missing run id or repository identity')
    listing = []
    if not problems:
        try:
            listing = artifacts(server, repository, args.run, token)
        except urllib.error.HTTPError as error:
            problems.append('artifact API call failed: ' + str(error) + ' (endpoint: /repos/<repo>/actions/runs/<run>/artifacts)')
        except (urllib.error.URLError, OSError, ValueError) as error:
            problems.append('artifact API call failed: ' + str(error))
    names = {item.get('name'): item for item in listing}
    now = datetime.datetime.now(datetime.timezone.utc)
    for target in TARGETS:
        name = PREFIX + target + '-' + args.run + '-' + args.attempt
        entry = {'name': name, 'accepted': False, 'problems': []}
        artifact = names.get(name)
        root = args.targets / name
        if artifact is None:
            entry['problems'].append('this run/attempt did not upload the target artifact')
        else:
            entry['artifact'] = {'id': artifact.get('id'), 'bytes': artifact.get('size_in_bytes'),
                                 'digest': artifact.get('digest'), 'expired': artifact.get('expired'),
                                 'expires_at': artifact.get('expires_at')}
            run_info = artifact.get('workflow_run') or {}
            if run_info.get('id') is not None and str(run_info.get('id')) != args.run:
                entry['problems'].append('artifact belongs to another run')
            if run_info.get('head_sha') and run_info['head_sha'] != args.source_sha:
                entry['problems'].append('artifact was produced from another source')
            if not artifact.get('size_in_bytes'):
                entry['problems'].append('artifact is empty')
            if artifact.get('expired'):
                entry['problems'].append('artifact is expired')
            expires = artifact.get('expires_at')
            if isinstance(expires, str):
                try:
                    when = datetime.datetime.strptime(expires, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc)
                    if when <= now:
                        entry['problems'].append('artifact expiry has passed')
                except ValueError:
                    entry['problems'].append('artifact expiry is not parseable')
        report_path = unpack_path = manifest_path = None
        if not root.is_dir():
            entry['problems'].append('downloaded artifact directory is missing: ' + str(root))
        else:
            report_path = locate(root, 'target.json')
            unpack_path = locate(root, 'unpack.json')
            manifest_path = locate(root, 'manifest.json')
            if manifest_path is not None and manifest_path.parent.name != 'delivery':
                manifest_path = None
            for label, path in (('target.json', report_path), ('unpack.json', unpack_path),
                                ('delivery/manifest.json', manifest_path)):
                if path is None:
                    entry['problems'].append('missing or duplicated evidence: ' + label)
        if not entry['problems']:
            report = local_json(report_path)
            unpack = local_json(unpack_path)
            manifest = local_json(manifest_path)
            entry['problems'].extend(candidate_identity(
                manifest, unpack, report, source_sha=args.source_sha,
                run_id=args.run, attempt=args.attempt, sdk_version='3.41.0'))
            archive = manifest_path.parent / manifest['archive']['name']
            entry.update({
                'source_sha': report.get('source_sha'),
                'entry': report.get('entry'),
                'entry_sha256': report.get('entry_sha256'),
                'run_id': report.get('run_id'), 'attempt': report.get('attempt'),
                'sdk_version': manifest.get('sdk_version'),
                'producer': manifest.get('producer'),
                'operations': sorted(report.get('operations') or {}),
                'missing': report.get('missing'),
                'drivers': [item.get('name') for item in report.get('drivers') or []],
                'archive': {'name': manifest['archive']['name'], 'bytes': manifest['archive']['bytes'],
                            'sha256': manifest['archive']['sha256']},
            })
            if not archive.is_file():
                entry['problems'].append('delivery archive is missing from the artifact')
            else:
                value = hashlib.sha256()
                with archive.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        value.update(chunk)
                if value.hexdigest() != manifest['archive']['sha256']:
                    entry['problems'].append('delivery archive bytes differ from its manifest')
                if manifest['files'].get(report.get('entry') or '', {}).get('sha256') != report.get('entry_sha256'):
                    entry['problems'].append('target report entry bytes differ from the delivery manifest')
                entry['archive_verified_from_bytes'] = True
            if report.get('source_sha') != args.source_sha:
                entry['problems'].append('target report binds another source')
            if report.get('run_id') and report.get('run_id') != args.run:
                entry['problems'].append('target report was produced in another run')
            if report.get('attempt') and report['attempt'] != args.attempt:
                entry['problems'].append('target report was produced in another attempt')
            if not report.get('accepted'):
                entry['problems'].append('target report is not accepted')
            if unpack.get('source_sha') != args.source_sha:
                entry['problems'].append('unpack report binds another source')
            if manifest.get('source_sha') != args.source_sha:
                entry['problems'].append('delivery manifest binds another source')
            entry['accepted'] = not entry['problems']
        results[target] = entry
        problems.extend([target + ': ' + item for item in entry['problems']])
    accepted = not problems and all(results[target]['accepted'] for target in TARGETS)
    delivery = {'schema': 1, 'kind': 'exreader-native-delivery-index', 'source_sha': args.source_sha,
                'run_id': args.run, 'attempt': args.attempt, 'targets': results,
                'accepted': accepted, 'problems': problems,
                'scope': 'six target native delivery archives and their existing UI drivers; no tag, Release or store publication',
                'complete_product': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(delivery, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    args.output.with_suffix('.md').write_text(matrix_markdown(delivery), encoding='utf-8')
    print(matrix_markdown(delivery), flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
            stream.write(matrix_markdown(delivery))
    print(json.dumps({'accepted': accepted, 'problems': problems,
                      'targets': {target: {'accepted': results[target]['accepted'],
                                           'missing': results[target].get('missing')} for target in TARGETS}},
                     ensure_ascii=True))
    return 0 if accepted else 1


if __name__ == '__main__':
    raise SystemExit(main())
