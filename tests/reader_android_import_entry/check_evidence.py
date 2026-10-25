#!/usr/bin/env python3
"""Strict same-source summary: every artifact must come from this run, attempt and commit, every guard and device
check must have passed, and nothing may be skipped. A generated report alone never counts as success."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REQUIRED_SCENARIOS = [
    'setup: native library opened on the sdk-owner thread',
    'thread rule: native commit from the main thread is refused (EXR_ARGUMENT)',
    'VIEW epub: installed SDK import ok, created, original read back byte-equal',
    're-delivery: same content id, SDK exact duplicate keeps the book (created=0)',
    'SEND pdf: staged as PDF, SDK file import ok, read back',
    'SEND_MULTIPLE: unknown-length pipe with 1..37 byte writes staged with the exact bytes',
    'copy buffer: no provider read request exceeded 64 KiB',
    're-post while unreleased: second ticket reports alreadyStaged and the same id',
    'picker result (ClipData of three grants): all imported and read back',
    'provider name is only a hint: no separators in title, no file named after it',
    'failure txt-error -> IO, no file left',
    'failure txt-truncated -> IO, no file left',
    'failure txt-overlong -> IO, no file left',
    'failure txt-33m -> LIMIT, no file left',
    'failure epub-129m -> LIMIT, no file left',
    'failure epub-declared-big -> LIMIT, no file left',
    'failure zip-unknown -> UNSUPPORTED_FORMAT, no file left',
    'failure pdf-lie -> UNSUPPORTED_FORMAT, no file left',
    'failure empty -> EMPTY, no file left',
    'declared 128 MiB + 1: refused before the provider stream was opened',
    'exactly 32 MiB unknown-length text is accepted and staged; the SDK verdict is recorded',
    'grant revoked before the stream opened -> PERMISSION',
    'URI never granted -> PERMISSION',
    'file:// URI refused as ARGUMENT',
    'ticket.cancel() on a stalled provider -> CANCELLED within 3 s',
    'entry.close() mid-copy -> CANCELLED, staging lock released for a new entry',
    'Activity closed mid-copy: copy completes and is delivered once',
    'rotation mid-copy: Activity recreated from saved state, copy delivered exactly once',
    'force-stop mid-copy leaves the partial temporary on disk',
    'restart removes the orphaned temporary and finds nothing ready',
    'force-stop after publish keeps the staged file',
    'restart lists the published file and the host imports it (SDK dedupe keeps the earlier book)',
    'review: 20000 concurrent cancel/commit calls have exactly one winner and no accepted cancel publishes',
    'review: releasing first duplicate lease preserves the second queued ready file',
    'review: last duplicate lease imports through SDK with exact original readback then deletes once',
    'review: stale repeated release cannot delete a restaged same-content file',
    'review: foreign entry leases cannot remove either entry original',
    'review: closed-entry stale lease cannot delete recovered file and new owner imports exact bytes',
    'review: 32 real reliable-pipe provider errors remain IO with no committed request',
    'review: repeated reliable-pipe failure descriptors close within baseline plus four framework FDs',
]


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--guards', type=Path, required=True)
    parser.add_argument('--android', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    problems = []
    identity = {k: os.environ.get(v, '') for k, v in (('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT'))}
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if head != identity['source_sha']:
        problems.append('checked-out HEAD differs from GITHUB_SHA')
    guards = load(args.guards / 'guards.json')
    if guards['head'] != head or guards['violations'] or not guards['protected_tree_unchanged']:
        problems.append('guards: %s' % guards['violations'])
    if not guards['self_tests'] or not all(c['ok'] for c in guards['self_tests']):
        problems.append('guard self-tests failed or missing')
    for name in ('identity.json', 'results.json', 'packages.json', 'stage.json'):
        if not (args.android / name).is_file():
            problems.append('missing android artifact ' + name)
    if not problems:
        ident = load(args.android / 'identity.json')
        for key in identity:
            if ident.get(key) != identity[key]:
                problems.append('identity mismatch for ' + key)
        results = load(args.android / 'results.json')
        for key, value in identity.items():
            if results.get(key) != value:
                problems.append('device report identity mismatch for ' + key)
        names = {c['name']: c for c in results['checks']}
        if len(names) != len(results['checks']) or any(c.get('ok') is not True for c in results['checks']):
            problems.append('duplicate or non-passing device checks')
        for required in REQUIRED_SCENARIOS:
            if required not in names:
                problems.append('required check never ran: ' + required)
            elif not names[required]['ok']:
                problems.append('required check failed: ' + required)
        if results['failed'] or results['device_api'] != '34':
            problems.append('device run: failed=%s api=%s' % (results['failed'], results['device_api']))
        if load(args.android / 'packages.json')['problems']:
            problems.append('package audit problems')
    summary = {'identity': identity, 'problems': problems, 'passed': not problems,
               'required_checks': len(REQUIRED_SCENARIOS)}
    if not problems:
        summary['checks_passed'] = results['passed']
        summary['device'] = {'api': results['device_api'], 'abi': results['device_abi'], 'kind': 'emulator'}
        summary['artifacts'] = {p.name: sha(p) for p in sorted(args.android.glob('*.json'))}
        summary['scope'] = ('API34 x86_64 emulator, real DocumentsProvider and intents; not a physical device, '
                            'not other API levels or ABIs, no audio or speech')
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
