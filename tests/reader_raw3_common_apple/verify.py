"""Run unchanged original Apple judges, then authenticate the new guard's own identity."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import zipfile

from guard import BRANCH, KIND, ROOT, SPECS, require, validate_record, workflow_identity

sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch


def read_guard(artifact, member, mode, target, source, run, attempt):
    require(not artifact['expired'] and artifact['workflow_run']['head_sha'] == source and
            artifact['workflow_run']['id'] == int(run), 'Guard artifact source/run differs')
    require(datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc),
            'Guard artifact expired')
    raw = download_artifact_zip(artifact['id'])
    require(len(raw) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == artifact['digest'],
            'Guard artifact ZIP bytes/digest differ')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), 'Duplicate guard ZIP member')
        for name in names:
            path = PurePosixPath(name)
            require(not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name,
                    'Unsafe guard ZIP member')
        info = archive.getinfo(member)
        require(0 < info.file_size <= 64 * 1024, 'Guard report size differs')
        data = archive.read(member)
        value = json.loads(data)
    validate_record(value, mode, target, source, run, attempt)
    return dict(artifact={key: artifact[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')},
                member=member, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), guard=value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', required=True, choices=SPECS)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    require(os.environ.get('GITHUB_REF_NAME') == BRANCH, 'Actual common-source branch required')
    source, run, attempt = (os.environ[name] for name in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    checkout = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    require(checkout == source, 'Checkout/source differs')
    workflow = workflow_identity(args.mode)['workflow']
    metadata = fetch('actions/runs/' + run + '/attempts/' + attempt)
    require(metadata['head_sha'] == source and metadata['head_branch'] == BRANCH and
            metadata['path'] == workflow and metadata['run_attempt'] == int(attempt), 'Run/workflow identity differs')
    # Execute the existing scripts as standalone programs: original imports, judges,
    # producer names, job/artifact counts, cases, budgets and outputs stay unchanged.
    originals = {
        'records': ('tests/apple_host/reading/summarize.py', 'tests/reader_apple_records_ready/verify.py'),
        'macos': ('tests/apple_host/raw3/verify.py',),
        'ios': ('tests/apple_host/raw3/ios/reading/verify.py', 'tests/reader_apple_records_ready/raw3_verify.py'),
    }
    # In records/iOS the preceding original strict step remains explicit in the
    # workflow. Only the final original verification is wrapped here.
    judges = originals[args.mode] if args.mode == 'macos' else originals[args.mode][1:]
    for judge in judges:
        subprocess.run([sys.executable, str(ROOT / judge)], cwd=ROOT, check=True)
    artifacts = fetch('actions/runs/' + run + '/artifacts?per_page=100')['artifacts']
    if args.mode == 'records':
        selections = [('apple-reading-sdk-' + target + '-' + run + '-' + attempt,
                       'build/apple-records-ready/guard.json', target) for target in ('macos', 'iphonesimulator')]
        output = 'build/apple-reading-summary/common-source.json'
    elif args.mode == 'macos':
        selections = [('apple-raw3-native-' + run + '-' + attempt, 'guard.json', 'macos')]
        output = 'build/apple-raw3-summary/common-source.json'
    else:
        selections = [('raw3-ios-sdk-' + target + '-' + run + '-' + attempt,
                       'common-source-guard.json', target) for target in ('macos', 'iphonesimulator')]
        output = 'build/raw3-ios-summary/common-source.json'
    proofs = []
    for name, member, target in selections:
        selected = [row for row in artifacts if row['name'] == name]
        require(len(selected) == 1, 'Missing/repeated common guard artifact: ' + name)
        proofs.append(read_guard(selected[0], member, args.mode, target, source, run, attempt))
    result = dict(accepted=True, guard_kind=KIND, mode=args.mode, source_sha=source,
                  run_id=run, attempt=attempt, workflow=workflow,
                  unchanged_original_judges_passed=True, authenticated_common_guards=proofs,
                  original_guard_executed=False, physical_device_execution=False,
                  performance_accepted=False, complete_product=False,
                  scope='complete unchanged original Apple suite plus authenticated common-source guard only')
    out = ROOT / output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
