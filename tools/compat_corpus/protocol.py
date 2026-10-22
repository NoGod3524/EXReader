#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Frozen, rights-reviewed corpus protocol around the existing document checker."""
import argparse
from collections import Counter
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_corpus import digest, valid_report
from triage_corpus import verified_result

# Public exr_format values, not extensions. XHTML shares EXR_HTML; KF8 shares EXR_MOBI.
TARGETS = dict(pdf=1000, epub=500, txt=30, html=30, fb2=30, docx=30,
               rtf=30, mobi=30, cbz=30)
EXTENSIONS = {'pdf': {'pdf'}, 'epub': {'epub'}, 'txt': {'txt'},
              'html': {'html', 'htm', 'xhtml'}, 'fb2': {'fb2'}, 'docx': {'docx'},
              'rtf': {'rtf'}, 'mobi': {'mobi', 'azw3', 'azw', 'prc', 'kf8'}, 'cbz': {'cbz'}}
HASH = re.compile(r'[0-9a-f]{64}\Z')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def relative(value):
    require(isinstance(value, str) and value and '\\' not in value and ':' not in value,
            'Require a portable relative path')
    path = PurePosixPath(value)
    require(not path.is_absolute() and '..' not in path.parts and str(path) == value,
            'Path must be normalized and remain within the corpus root')
    return value


def inside(root, name):
    path = root / relative(name)
    require(path.resolve().is_relative_to(root.resolve()), 'Path escapes corpus root')
    return path


def https(value):
    require(isinstance(value, str), 'Require an HTTPS source URL')
    url = urlsplit(value)
    require(url.scheme == 'https' and url.hostname and not url.username and not url.password,
            'Require an HTTPS source URL without credentials')
    return url.hostname


def validate(manifest):
    require(isinstance(manifest, dict) and type(manifest.get('schema')) is int and manifest['schema'] == 1,
            'Unknown manifest schema')
    require(re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', manifest.get('dataset_id', '')) is not None,
            'Require a stable dataset_id')
    require(manifest.get('targets') == TARGETS and all(type(x) is int for x in manifest['targets'].values()),
            'Targets must match the frozen public format policy')
    require(type(manifest.get('complete')) is bool, 'Require an explicit complete flag')
    selection = manifest.get('selection', {})
    require(isinstance(selection, dict), 'Invalid source selection declaration')
    require(isinstance(selection.get('method'), str) and selection['method'].strip(), 'Missing source selection method')
    require(selection.get('engine_results_used') is False, 'Selection must precede engine observations')
    candidates, excluded = selection.get('candidate_ids'), selection.get('excluded')
    require(isinstance(candidates, list) and all(text(x) for x in candidates)
            and len(candidates) == len(set(candidates)), 'Missing or duplicate candidate roster')
    require(isinstance(excluded, list), 'Require an explicit exclusion ledger')
    excluded_ids = []
    for item in excluded:
        require(isinstance(item, dict) and item.get('reason') in
                ('permission_unconfirmed', 'not_declared_format') and text(item.get('evidence')),
                'Failures cannot be excluded from the candidate roster')
        excluded_ids.append(item.get('id'))
    files = manifest.get('files')
    require(isinstance(files, list), 'Require a file inventory')
    ids, paths, hashes, evidence_paths = set(), set(), set(), {}
    counts, synthetic, variants = Counter(), Counter(), Counter()
    for item in files:
        require(isinstance(item, dict), 'Invalid inventory entry')
        identity = item.get('id')
        require(text(identity) and identity not in ids, 'Missing or duplicate input identity')
        ids.add(identity)
        path = relative(item.get('path'))
        require(path.casefold() not in paths, 'Duplicate input path or case alias')
        paths.add(path.casefold())
        sha = item.get('sha256', '')
        require(isinstance(sha, str) and HASH.fullmatch(sha), 'Missing input SHA-256')
        require(sha not in hashes, 'Duplicate content cannot satisfy separate format or alias targets')
        hashes.add(sha)
        require(type(item.get('bytes')) is int and 0 < item['bytes'] <= 128 * 1024 * 1024,
                'Require positive bounded byte size')
        fmt = item.get('format')
        require(fmt in TARGETS and PurePosixPath(path).suffix.lower()[1:] in EXTENSIONS[fmt],
                'Unknown canonical format or extension mapping')
        variant = item.get('variant')
        allowed = {'html': {'html', 'xhtml'}, 'mobi': {'mobi', 'kf8'}}.get(fmt, {fmt})
        require(variant in allowed, 'Require an explicit content variant, not an extension alias')
        require(item.get('kind') in ('real', 'synthetic'), 'Real and synthetic must be declared separately')
        require(item.get('scope') in ('supported', 'boundary'), 'Require supported or boundary scope')
        source = item.get('source', {})
        require(isinstance(source, dict), 'Invalid source declaration')
        https(source.get('url'))
        require(text(source.get('creator')) and text(source.get('license')), 'Missing source creator or license')
        permission = source.get('permission', {})
        require(isinstance(permission, dict), 'Invalid redistribution declaration')
        require(permission.get('redistribution') is True and text(permission.get('scope')) and
                text(permission.get('reviewed_by')), 'Per-file redistribution review is required')
        https(permission.get('evidence_url'))
        proof = relative(permission.get('evidence_path'))
        require(isinstance(permission.get('evidence_sha256'), str) and HASH.fullmatch(permission['evidence_sha256']),
                'Missing permission evidence SHA-256')
        require(proof not in ('collection-registration.json', 'collection-attempts.jsonl') and
                (proof.casefold() not in evidence_paths or evidence_paths[proof.casefold()] == permission['evidence_sha256']),
                'Permission proofs conflict with a collection ledger or one another')
        evidence_paths[proof.casefold()] = permission['evidence_sha256']
        require(source.get('origin') in ('published_document', 'original_test_fixture'),
                'Require the original publication or fixture origin')
        require(item['kind'] != 'real' or source['origin'] == 'published_document',
                'Original synthetic fixtures cannot be relabeled as real publications')
        expected, capabilities = item.get('expected'), item.get('capabilities')
        require(isinstance(expected, dict) and set(expected) == {'status', 'complete'} and
                type(expected['status']) is int and expected['status'] >= 0 and
                type(expected['complete']) is bool, 'Missing predeclared pipeline expectation')
        require(isinstance(capabilities, dict) and set(capabilities) == {'open', 'render', 'extract', 'save'},
                'Declare every capability before observation')
        require(capabilities['save'] == 'not_evaluated' and text(item.get('save_reason')),
                'This checker cannot grant saving acceptance')
        if item['scope'] == 'supported':
            require(expected == {'status': 0, 'complete': True} and
                    all(capabilities[k] == 'complete' for k in ('open', 'render', 'extract')),
                    'Supported inputs require whole-document completion')
        else:
            require(expected['status'] > 0 and expected['complete'] is False and text(item.get('expectation_reason')) and
                    all(capabilities[k] == 'not_evaluated' for k in ('open', 'render', 'extract')),
                    'Boundary rejections need a prior reason and cannot claim completion')
        if item['kind'] == 'synthetic':
            synthetic[fmt] += 1
        elif item['scope'] == 'supported':
            counts[fmt] += 1
        variants[fmt + '/' + variant] += 1
    require(not paths.intersection(evidence_paths), 'Permission proof cannot overwrite an input')
    require(len(excluded_ids) == len(set(excluded_ids)) and not ids.intersection(excluded_ids) and
            set(candidates) == ids.union(excluded_ids), 'Every frozen candidate must be retained or explained')
    return {'real_supported': {fmt: counts[fmt] for fmt in TARGETS},
            'synthetic': dict(synthetic), 'variants': dict(variants),
            'shortfall': {fmt: max(0, count - counts[fmt]) for fmt, count in TARGETS.items()},
            'entries': len(files), 'excluded': len(excluded_ids)}


def git(*arguments):
    process = subprocess.run(['git', '-C', str(ROOT), *arguments], capture_output=True, check=True)
    return process.stdout


def registered(manifest_path, commit):
    require(re.fullmatch('[0-9a-f]{40}', commit) is not None, 'Require the full registration commit')
    name = manifest_path.resolve().relative_to(ROOT).as_posix()
    git('merge-base', '--is-ancestor', commit, 'HEAD')
    frozen = git('show', commit + ':' + name)
    require(sha_bytes(frozen) == digest(manifest_path), 'Registered expectations or source inventory changed')
    # The first addition anchors this dataset path; later runs cannot choose a newer registration.
    additions = git('log', '--reverse', '--diff-filter=A', '--format=%H', 'HEAD', '--', name).decode().splitlines()
    require(additions and additions[0] == commit, 'Use the original registration, not a post-observation replacement')
    require(not git('status', '--porcelain', '--untracked-files=no').strip(), 'Require clean committed source')
    return {'commit': commit, 'path': name, 'sha256': sha_bytes(frozen)}


def verify_assets(manifest, root):
    for item in manifest['files']:
        path = inside(root, item['path'])
        require(path.is_file() and path.stat().st_size == item['bytes'] and digest(path) == item['sha256'],
                'Missing or changed input: ' + item['id'])
        proof = item['source']['permission']
        require(digest(inside(root, proof['evidence_path'])) == proof['evidence_sha256'],
                'Missing or changed redistribution evidence: ' + item['id'])


def verify_summary(manifest, summary, source_sha):
    require(summary.get('source_sha') == source_sha and summary.get('source_dirty') is False and
            summary.get('identities_unchanged') is True, 'Run source or identity mismatch')
    files, results = manifest['files'], summary.get('results', [])
    require(summary.get('manifest_entries') == len(files) and summary.get('checked_entries') == len(files) and
            len(results) == len(files) and summary.get('page_limit') == 0,
            'Partial or filtered results cannot be accepted')
    counts = Counter()
    for index, (item, record) in enumerate(zip(files, results)):
        result = verified_result(record)
        require(record.get('index') == index and record.get('path') == item['path'] and
                result.get('index') == index and result.get('input') == item and
                result.get('observed_sha256') == item['sha256'], 'Result is not from the frozen input')
        kind = result.get('classification')
        require(kind == record.get('classification'), 'Summary classification changed')
        require({'stdout.json', 'stderr.log'} <= result.get('evidence', {}).keys(),
                'Missing raw process attachments')
        if kind in ('passed', 'expected_rejection'):
            report = result.get('report')
            require(valid_report(report), 'Invalid observed pipeline report')
            raw = json.loads((Path(record['result']).parent / 'stdout.json').read_text(encoding='utf-8'))
            require(raw == report and all(report[k] == v for k, v in item['expected'].items()) and
                    result.get('exit_code') == (0 if report['complete'] else 1) and
                    kind == ('passed' if report['complete'] else 'expected_rejection'),
                    'Observed report, exit or predeclared expectation mismatch')
        counts[kind] += 1
    require(dict(counts) == summary.get('counts'), 'Summary counts omit retained outcomes')
    return dict(counts)


def acceptance(manifest, inventory, counts):
    enough = not any(inventory['shortfall'].values())
    all_observed = sum(counts.values()) == inventory['entries'] and inventory['entries'] > 0
    pipeline = bool(manifest['complete'] and enough and all_observed and
                    all(kind in ('passed', 'expected_rejection') for kind in counts))
    return {'pipeline_accepted': pipeline, 'accepted': False,
            'pending': ['pixel/semantic fidelity and saving require independent capability evidence'] +
                       ([] if pipeline else ['real corpus target, full collection or pipeline outcomes incomplete']),
            'scope': 'open, all-page render, text access; no fidelity, saving, audio or image codec acceptance'}


def cloud_only():
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_RUN_ID'),
            'Collection and execution are restricted to GitHub Actions')


class HttpsRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        https(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def fetch(url, destination, expected_hash, size):
    https(url)
    if destination.exists():
        require(destination.is_file() and digest(destination) == expected_hash and
                (size is None or destination.stat().st_size == size), 'Existing collected asset changed')
        return 'verified_existing'
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.partial')
    require(not temporary.exists(), 'Interrupted partial asset retained; review it before resuming')
    limit = size if size is not None else 4 * 1024 * 1024
    opener = urllib.request.build_opener(HttpsRedirect())
    with opener.open(urllib.request.Request(url, headers={'User-Agent': 'EXReader-licensed-corpus/1'}), timeout=60) as response:
        with temporary.open('xb') as output:
            length = 0
            while block := response.read(min(65536, limit - length + 1)):
                length += len(block)
                require(length <= limit, 'Download exceeds frozen byte bound')
                output.write(block)
    require((size is None or length == size) and digest(temporary) == expected_hash,
            'Downloaded content differs from the registered source')
    temporary.rename(destination)
    return 'downloaded'


def collect(manifest, manifest_path, root, registration):
    cloud_only()
    root.mkdir(parents=True, exist_ok=True)
    seal = root / 'collection-registration.json'
    if seal.exists():
        require(json.loads(seal.read_text()) == registration, 'Cannot resume a different registered dataset')
    else:
        require(not any(root.iterdir()), 'New collection directory must be empty')
        write_json(seal, registration)
    failures = 0
    for item in manifest['files']:
        attempt = {'id': item['id'], 'manifest_sha256': digest(manifest_path),
                   'run_id': os.environ['GITHUB_RUN_ID'], 'started_unix': time.time()}
        try:
            source, proof = item['source'], item['source']['permission']
            time.sleep(0.5)
            attempt['permission'] = fetch(proof['evidence_url'], inside(root, proof['evidence_path']),
                                          proof['evidence_sha256'], None)
            time.sleep(0.5)
            attempt['input'] = fetch(source['url'], inside(root, item['path']), item['sha256'], item['bytes'])
            attempt['status'] = 'collected'
        except (OSError, ValueError, http.client.HTTPException) as error:
            failures += 1
            attempt.update(status='collection_failed', error=str(error))
        with (root / 'collection-attempts.jsonl').open('a', encoding='utf-8') as ledger:
            ledger.write(json.dumps(attempt, ensure_ascii=False) + '\n')
    return failures


def run(manifest, manifest_path, root, output, binary, font, registration, timeout, workers):
    cloud_only()
    require(not output.exists(), 'Choose a fresh output directory for this exact run/source')
    output.mkdir(parents=True)
    source_sha = git('rev-parse', 'HEAD').decode().strip()
    report = {'schema': 1, 'dataset_id': manifest['dataset_id'], 'source_sha': source_sha,
              'run_id': os.environ['GITHUB_RUN_ID'], 'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
              'registration': registration, 'inventory': validate(manifest), 'accepted': False,
              'pipeline_accepted': False}
    # Seal before collection/probe output exists, and preserve a refusal even on setup failure.
    write_json(output / 'registration.json', report)
    try:
        verify_assets(manifest, root)
        require(manifest['files'], 'No registered real corpus assets available')
        projection = output / 'checker-manifest.json'
        write_json(projection, {'complete': manifest['complete'], 'target': len(manifest['files']), 'files': manifest['files']})
        command = [sys.executable, str(ROOT / 'tools/check_corpus.py'), str(binary.resolve()),
                   str(font.resolve()), str(projection), str(output / 'probe'), '--root', str(root),
                   '--timeout', str(timeout), '--workers', str(workers)]
        with (output / 'driver.stdout').open('wb') as stdout, (output / 'driver.stderr').open('wb') as stderr:
            process = subprocess.run(command, stdout=stdout, stderr=stderr)
        summary_path = output / 'probe/summary.json'
        summary = json.loads(summary_path.read_text(encoding='utf-8'))
        counts = verify_summary(manifest, summary, source_sha)
        require(process.returncode == (0 if summary['accepted'] else 1), 'Document driver exit/report mismatch')
        verify_assets(manifest, root)
        require(registered(manifest_path, registration['commit']) == registration, 'Registration changed during run')
        report.update(counts=counts, checker_summary={'path': str(summary_path), 'sha256': digest(summary_path)})
        report.update(acceptance(manifest, report['inventory'], counts))
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        report['refusal'] = str(error)
    write_json(output / 'acceptance.json', report)
    return 0 if report['pipeline_accepted'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('inventory', 'collect', 'run'))
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--registered-at')
    parser.add_argument('--root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--font', type=Path)
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    try:
        cloud_only()
        manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
        inventory = validate(manifest)
        if args.action == 'inventory':
            require(not args.output.exists(), 'Preserve previous inventory reports')
            args.output.parent.mkdir(parents=True, exist_ok=True)
            write_json(args.output, {'schema': 1, 'manifest_sha256': digest(args.manifest),
                                    'inventory': inventory, **acceptance(manifest, inventory, {})})
            return 0
        require(args.registered_at and args.root, 'Require registration commit and corpus root')
        registration = registered(args.manifest, args.registered_at)
        if args.action == 'collect':
            require(not args.output.exists(), 'Preserve previous collection reports')
            args.output.parent.mkdir(parents=True, exist_ok=True)
            failures = collect(manifest, args.manifest, args.root, registration)
            write_json(args.output, {'registration': registration, 'failed': failures, 'accepted': False})
            return 1 if failures else 0
        require(args.binary and args.font and 1 <= args.workers <= 8 and 0 < args.timeout <= 3600,
                'Require checker, font, 1..8 workers and timeout in (0,3600]')
        return run(manifest, args.manifest, args.root, args.output, args.binary, args.font,
                   registration, args.timeout, args.workers)
    except (OSError, ValueError, TypeError, KeyError, subprocess.CalledProcessError) as error:
        if os.environ.get('GITHUB_ACTIONS') == 'true' and not args.output.exists():
            refusal = {'schema': 1, 'accepted': False, 'pipeline_accepted': False,
                       'run_id': os.environ.get('GITHUB_RUN_ID'), 'refusal': str(error)}
            if args.action == 'run':
                args.output.mkdir(parents=True)
                write_json(args.output / 'acceptance.json', refusal)
            else:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                write_json(args.output, refusal)
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
