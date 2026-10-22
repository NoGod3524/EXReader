#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Revalidate real cloud artifacts, then reject independent incomplete/altered copies."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile

from assemble_validation import assemble
from evidence_contract import (cloud_identity, digest, load, require, validate_identity,
    validate_package, validate_platform, validate_review_reports, validate_sdk)


def copy_file(source, target):
    try:
        os.link(source, target, follow_symlinks=True)
    except OSError:
        shutil.copy2(source, target, follow_symlinks=True)
    return target


def replace(path, contents):
    temporary = path.with_name(path.name + '.gate-review')
    temporary.write_bytes(contents)
    temporary.replace(path)


def edit(path, change):
    data = json.loads(path.read_text())
    change(data)
    replace(path, (json.dumps(data, sort_keys=True) + '\n').encode())


def attachment(root, kind):
    directory = root/'wp13-apple-macos/evidence/macos'
    records = json.loads((directory/'evidence.json').read_text())['attachments']['records']
    record = next(item for item in records if
        (kind == 'steps' and item['role'].startswith('steps-')) or
        (kind == 'tree' and 'tree' in item['role']) or
        (kind == 'screenshot' and not item['role'].startswith('steps-') and 'tree' not in item['role']))
    return directory/'attachments'/record['file']


def alter_export_name(root, prefix):
    path = root/'wp13-apple-macos/evidence/macos/attachments/manifest.json'
    def change(groups):
        item = next(item for group in groups for item in group['attachments']
                    if item['suggestedHumanReadableName'].endswith('.png'))
        item['suggestedHumanReadableName'] = prefix + '_0_00000000-0000-0000-0000-000000000000.png'
    edit(path, change)


def accepted(args):
    try:
        return assemble(args)[0]['accepted'] is True
    except Exception:
        return False


def affected_accepted(args, name):
    """Revalidate the changed component; unchanged files are never substituted for changed ones."""
    root = args.artifacts
    try:
        sdks = {target: load(root/('wp13-apple-sdk-' + target)/'build/sdk-identity.json')
                for target in ('macos', 'iphonesimulator', 'iphoneos')}
        if name in ('missing platform', 'missing fixture manifest'):
            return accepted(args)
        if name in ('wrong SDK source', 'missing SDK', 'changed SDK bytes'):
            target = 'iphoneos' if name == 'missing SDK' else 'macos'
            validate_sdk(root/('wp13-apple-sdk-' + target)/'stage'/target, sdks[target],
                         args.source_sha, args.run_id, args.attempt, target)
        elif name in ('missing model review', 'failed model review', 'incomplete model review checks',
                      'changed model executable', 'missing SDK review', 'failed SDK review',
                      'incomplete SDK review checks', 'changed SDK review executable'):
            fixtures = load(root/'wp13-apple-macos/apple-resources/manifest.json')
            validate_review_reports(root/'wp13-apple-package', args.source_sha, args.run_id,
                                    args.attempt, sdks['macos'], fixtures)
        elif name in ('missing package', 'wrong package run', 'wrong package attempt',
                      'missing legacy report', 'wrong legacy source', 'incomplete legacy checks',
                      'duplicate legacy check', 'failed legacy result', 'string legacy result',
                      'wrong package source', 'missing device archive', 'changed device archive',
                      'device signing policy mismatch'):
            validate_package(root/'wp13-apple-package', args.source_sha, args.run_id, args.attempt, sdks)
        else:
            validate_platform(root/'wp13-apple-macos/evidence/macos', 'macos', args.source_sha,
                args.run_id, args.attempt, sdks['macos'], root/'wp13-apple-macos/results')
        return True
    except Exception:
        return False


def mutations():
    ui = Path('wp13-apple-macos/evidence/macos')
    report = ui/'evidence.json'
    legacy = Path('wp13-apple-package/evidence-iphone/report.json')
    changes = [
        ('missing platform', lambda r: shutil.rmtree(r/'wp13-apple-ipad')),
        ('missing evidence report', lambda r: (r/report).unlink()),
        ('empty evidence report', lambda r: edit(r/report, lambda d: d.clear())),
        ('wrong evidence source', lambda r: edit(r/report, lambda d: d.update(source_sha='0'*40))),
        ('wrong environment source', lambda r: edit(r/report, lambda d: d['environment'].update(source_sha='0'*40))),
        ('wrong run', lambda r: edit(r/report, lambda d: d['environment'].update(run_id='0'))),
        ('wrong attempt', lambda r: edit(r/report, lambda d: d['environment'].update(attempt='0'))),
        ('wrong platform', lambda r: edit(r/report, lambda d: d['environment'].update(platform='ipad'))),
        ('wrong job', lambda r: edit(r/report, lambda d: d['environment'].update(job='package'))),
        ('collector failure', lambda r: edit(r/report, lambda d: d.update(collector_status=1))),
        ('string accepted result', lambda r: edit(r/report, lambda d: d.update(accepted='true'))),
        ('missing original case', lambda r: edit(r/report, lambda d: d['tests'].pop(0))),
        ('missing new regression case', lambda r: edit(r/report, lambda d: d['tests'].pop())),
        ('duplicate case', lambda r: edit(r/report, lambda d: d['tests'].__setitem__(1, d['tests'][0]))),
        ('unknown case identity', lambda r: edit(r/report, lambda d: d['tests'][0].update(name='test00Unknown()'))),
        ('failed case', lambda r: edit(r/report, lambda d: d['tests'][0].update(result='Failed'))),
        ('skipped case', lambda r: edit(r/report, lambda d: d['tests'][0].update(result='Skipped'))),
        ('missing step', lambda r: edit(r/report, lambda d: d['tests'][0]['steps'].pop())),
        ('duplicate step', lambda r: edit(r/report, lambda d: d['tests'][0]['steps'].__setitem__(1, d['tests'][0]['steps'][0]))),
        ('inconsistent totals', lambda r: edit(r/report, lambda d: d['totals'].update(passed=0))),
        ('missing attachment directory', lambda r: shutil.rmtree(r/ui/'attachments')),
        ('missing screenshot bytes', lambda r: attachment(r, 'screenshot').unlink()),
        ('changed screenshot bytes', lambda r: replace(attachment(r, 'screenshot'), b'not a screenshot')),
        ('missing element tree bytes', lambda r: attachment(r, 'tree').unlink()),
        ('empty element tree', lambda r: replace(attachment(r, 'tree'), b'')),
        ('missing step attachment', lambda r: attachment(r, 'steps').unlink()),
        ('step attachment identity mismatch', lambda r: edit(attachment(r, 'steps'), lambda d: d.update(test='test00Unknown'))),
        ('step attachment incomplete', lambda r: edit(attachment(r, 'steps'), lambda d: d['steps'].pop())),
        ('attachment export failure', lambda r: edit(r/report, lambda d: d['attachments'].update(status=1))),
        ('attachment name prefix is not identity', lambda r: alter_export_name(r, '01-empty-library-extra')),
        ('attachment owner mismatch', lambda r: alter_export_name(r, '34-nondefault-font-restored')),
        ('missing program', lambda r: shutil.rmtree(r/ui/'program')),
        ('changed executable bytes', lambda r: replace(r/ui/'program/EXReaderHost.app/Contents/MacOS/EXReaderHost', b'changed executable')),
        ('wrong program hash', lambda r: edit(r/report, lambda d: d['environment']['app'].update(executable_sha256='0'*64))),
        ('missing fixture manifest', lambda r: (r/'wp13-apple-macos/apple-resources/manifest.json').unlink()),
        ('wrong fixture identity', lambda r: edit(r/report, lambda d: d['environment']['fixtures'].update(**{'Sample.epub': '0'*64}))),
        ('changed fixture bytes', lambda r: replace(r/ui/'program/EXReaderHost.app/Contents/Resources/Sample.epub', b'changed fixture')),
        ('wrong SDK source', lambda r: edit(r/'wp13-apple-sdk-macos/build/sdk-identity.json', lambda d: d.update(source_sha='0'*40))),
        ('missing SDK', lambda r: shutil.rmtree(r/'wp13-apple-sdk-iphoneos')),
        ('changed SDK bytes', lambda r: replace(r/'wp13-apple-sdk-macos/stage/macos/include/exr/base.h', b'changed SDK header')),
        ('missing persisted database', lambda r: (r/ui/'library.sqlite').unlink()),
        ('changed persisted database', lambda r: replace(r/ui/'library.sqlite', b'invalid database')),
        ('missing host state', lambda r: (r/ui/'host-state.json').unlink()),
        ('changed host state', lambda r: edit(r/ui/'host-state.json', lambda d: d.update(state_hash='00000000'))),
        ('missing host log', lambda r: (r/ui/'host-log.txt').unlink()),
        ('missing raw result', lambda r: shutil.rmtree(r/'wp13-apple-macos/results/macos.xcresult')),
        ('missing raw log', lambda r: (r/'wp13-apple-macos/results/macos-xcodebuild.log').unlink()),
        ('missing package', lambda r: shutil.rmtree(r/'wp13-apple-package')),
        ('wrong package run', lambda r: edit(r/'wp13-apple-package/package-identity.json', lambda d: d.update(run_id='0'))),
        ('wrong package attempt', lambda r: edit(r/'wp13-apple-package/package-identity.json', lambda d: d.update(attempt='0'))),
        ('missing legacy report', lambda r: (r/legacy).unlink()),
        ('wrong legacy source', lambda r: edit(r/legacy, lambda d: d.update(source_sha='0'*40))),
        ('incomplete legacy checks', lambda r: edit(r/legacy, lambda d: d['checks'].pop())),
        ('duplicate legacy check', lambda r: edit(r/legacy, lambda d: d['checks'].__setitem__(1, d['checks'][0]))),
        ('failed legacy result', lambda r: edit(r/legacy, lambda d: d.update(passed=False))),
        ('string legacy result', lambda r: edit(r/legacy, lambda d: d.update(passed='true'))),
        ('wrong package source', lambda r: edit(r/'wp13-apple-package/device/build.json', lambda d: d.update(source_sha='0'*40))),
        ('missing device archive', lambda r: (r/'wp13-apple-package/device/EXReader-iOS-unsigned.ipa').unlink()),
        ('changed device archive', lambda r: replace(r/'wp13-apple-package/device/EXReader-iOS-unsigned.ipa', b'invalid archive')),
        ('device signing policy mismatch', lambda r: edit(r/'wp13-apple-package/device/build.json', lambda d: d.update(signing='unknown'))),
        ('missing model review', lambda r: (r/'wp13-apple-package/model-review/model-review.json').unlink()),
        ('failed model review', lambda r: edit(r/'wp13-apple-package/model-review/model-review.json', lambda d: d.update(accepted=False))),
        ('incomplete model review checks', lambda r: edit(r/'wp13-apple-package/model-review/model-review.json', lambda d: d['checks'].pop())),
        ('changed model executable', lambda r: replace(r/'wp13-apple-package/model-review/model-review', b'changed program')),
        ('missing SDK review', lambda r: (r/'wp13-apple-package/sdk-review/sdk-review-identity.json').unlink()),
        ('failed SDK review', lambda r: edit(r/'wp13-apple-package/sdk-review/sdk-review-identity.json', lambda d: d.update(passed=False))),
        ('incomplete SDK review checks', lambda r: edit(r/'wp13-apple-package/sdk-review/consumer/sdk-review.json', lambda d: d['cases'].pop())),
        ('changed SDK review executable', lambda r: replace(r/'wp13-apple-package/sdk-review/sdk-review', b'changed program')),
    ]
    return changes


def review_names():
    names = ['complete real same-run evidence accepted']
    names.extend(name + ' refused' for name, change in mutations())
    names.extend(job + ' ' + (status or 'missing result') + ' refused'
                 for job in ('sdk', 'uitest', 'package')
                 for status in ('failure', 'cancelled', 'skipped', ''))
    return names


def validate_review_result(path):
    result = load(path)
    expected = cloud_identity('summary')
    validate_identity(result, expected['source_sha'], expected['run_id'], expected['attempt'], 'summary', 'summary')
    checks = result.get('checks', [])
    require(result.get('schema') == 1 and result.get('accepted') is True and
            result.get('check_count') == len(review_names()) and
            [item.get('name') for item in checks] == review_names() and
            all(item.get('passed') is True for item in checks) and
            result.get('review_script_sha256') == digest(__file__), 'gate regression evidence incomplete')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'evidence regression runs only in cloud CI')
    expected = cloud_identity('summary')
    gate_args = argparse.Namespace(artifacts=args.artifacts, package=None,
        source_sha=expected['source_sha'], run_id=expected['run_id'], attempt=expected['attempt'],
        date='', upstream_results=os.environ['WP13_APPLE_UPSTREAM_RESULTS'])
    require(accepted(gate_args), 'real cloud evidence must pass before negative checks')
    checks = [{'name': 'complete real same-run evidence accepted', 'passed': True}]
    changes = mutations()
    for name, change in changes:
        with tempfile.TemporaryDirectory(prefix='apple-gate-review-') as temporary:
            root = Path(temporary)/'artifacts'
            shutil.copytree(args.artifacts, root, copy_function=copy_file)
            change(root)
            gate_args.artifacts = root
            require(not affected_accepted(gate_args, name), 'gate accepted altered evidence: ' + name)
            checks.append({'name': name + ' refused', 'passed': True})
    gate_args.artifacts = args.artifacts
    upstream = json.loads(gate_args.upstream_results)
    for job in ('sdk', 'uitest', 'package'):
        for status in ('failure', 'cancelled', 'skipped', ''):
            changed = json.loads(json.dumps(upstream))
            changed[job]['result'] = status
            gate_args.upstream_results = json.dumps(changed)
            require(not accepted(gate_args), 'upstream result not refused')
            checks.append({'name': job + ' ' + (status or 'missing result') + ' refused', 'passed': True})
    result = {**expected, 'schema': 1, 'accepted': True, 'checks': checks,
              'check_count': len(checks), 'review_script_sha256': digest(__file__)}
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'accepted': True, 'gate_review_checks': len(checks)}))


if __name__ == '__main__':
    main()
