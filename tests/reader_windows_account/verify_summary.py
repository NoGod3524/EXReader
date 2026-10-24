# SPDX-License-Identifier: MIT
"""Actions-only strict summary: re-download the uploaded artifact ZIP, recompute its digest and
require every retained and new report to be complete and bound to this exact source/run/attempt."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

RETAINED = {
    'account-product10/product-result.json': 10,
    'account-worker5/worker-result.json': 5,
    'account-shelf-ui/shelf-result.json': 13,
    'account-metadata-ui/metadata-ui.json': 18,
}


def bare(digest):
    """Compare digests by their hex body: the API adds 'sha256:', upload outputs do not."""
    return digest.split(':', 1)[1] if ':' in digest else digest


def gh(*arguments, binary=False):
    done = subprocess.run(['gh', 'api', *arguments], capture_output=True, check=True)
    return done.stdout if binary else done.stdout.decode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifact-id', required=True)
    parser.add_argument('--upload-digest', default='')
    parser.add_argument('--account-checks', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repository, sha = os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_SHA']
    run, attempt = os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT']
    problems = []

    def require(condition, message):
        if not condition:
            problems.append(message)

    args.output.mkdir(parents=True, exist_ok=True)
    meta = json.loads(gh('repos/%s/actions/artifacts/%s' % (repository, args.artifact_id)))
    name = 'reader-windows-account-%s-%s' % (run, attempt)
    require(meta['name'] == name, 'artifact name differs from this run and attempt')
    require(meta['size_in_bytes'] > 0 and not meta['expired'], 'artifact is empty or expired')
    require(meta['workflow_run']['id'] == int(run) and meta['workflow_run']['head_sha'] == sha, 'artifact belongs to another run or source')
    archive = args.output / 'artifact.zip'
    archive.write_bytes(gh('repos/%s/actions/artifacts/%s/zip' % (repository, args.artifact_id), binary=True))
    digest = 'sha256:' + hashlib.sha256(archive.read_bytes()).hexdigest()
    require(archive.stat().st_size > 0, 'downloaded ZIP is empty')
    # The API returns 'sha256:<hex>' and the upload step output is bare hex: compare hex to hex.
    require(not meta.get('digest') or bare(meta['digest']) == bare(digest), 'API digest differs from the recomputed ZIP digest')
    require(not args.upload_digest or bare(args.upload_digest) == bare(digest), 'upload step digest differs from the recomputed ZIP digest')
    root = args.output / 'unzipped'
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(root)

    def load(path):
        file = root / path
        require(file.is_file(), 'missing report ' + path)
        return json.loads(file.read_text(encoding='utf-8')) if file.is_file() else {}

    def bound(report, path):
        require(report.get('accepted') is True and report.get('source_sha') == sha and
                report.get('run_id') == run and report.get('attempt') == attempt, 'report is not bound to this source/run/attempt: ' + path)
        names = report.get('checks', [])
        require(len(names) == len(set(names)) and report.get('count', len(names)) == len(names), 'duplicate or miscounted checks: ' + path)
        return names

    counts = {}
    ui = load('account-ui158/summary.json')
    require(ui.get('passed') is True and ui.get('counts') == {'steps': 158, 'passed': 158, 'failed': 0} and ui.get('errors') == [], 'original UI158 incomplete')
    counts['ui158'] = ui.get('counts', {}).get('passed')
    evidence = load('account-ui158/wp13-windows-evidence.json')
    require(evidence.get('source_sha') == sha and evidence.get('identities_unchanged') is True, 'UI158 evidence is not bound to this source')
    negative = load('account-negative/checks.json')
    require(negative.get('passed') is True and len(negative.get('checks', [])) >= 26, 'original evidence rejection cases incomplete')
    for path, expected in RETAINED.items():
        names = bound(load(path), path)
        require(len(names) == expected, '%s has %d checks, expected %d' % (path, len(names), expected))
        counts[path] = len(names)
    account = load('account-ui/account-ui.json')
    names = bound(account, 'account-ui/account-ui.json')
    require(len(names) == args.account_checks, 'account checks %d differ from %d' % (len(names), args.account_checks))
    counts['account'] = len(names)
    require(account.get('complete_product') is False, 'the report must not claim a complete product')
    result = {'accepted': not problems, 'problems': problems, 'source_sha': sha, 'run_id': run, 'attempt': attempt,
              'artifact': {'id': int(args.artifact_id), 'name': meta['name'], 'bytes': meta['size_in_bytes'],
                           'expires_at': meta['expires_at'], 'sha256': digest},
              'counts': counts, 'account_uncovered': account.get('uncovered', [])}
    (args.output / 'verified.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    if problems:
        raise SystemExit('strict summary rejected: ' + '; '.join(problems))


if __name__ == '__main__':
    main()
