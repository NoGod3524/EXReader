#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Extract original S20 failures from Actions-downloaded target artifacts."""
import argparse
import json
import os
from pathlib import Path

from delivery import sha256_file
from diagnostics import android_cases, xctest_log

SOURCE = '63d0c8d2f032f5c78c77c9f407b17185412e991f'
RUN = '40248648454'
ATTEMPT = '1'


def unique(root, pattern, parent):
    matches = [path for path in root.rglob(pattern) if path.is_file() and path.parent.name == parent]
    if len(matches) != 1:
        raise ValueError('expected one %s/%s, found %s' % (parent, pattern, len(matches)))
    return matches[0]


def extract(root, target):
    manifest_path = unique(root / target, 'manifest.json', 'delivery')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    provenance = manifest.get('provenance') or {}
    if (manifest.get('source_sha') != SOURCE or manifest.get('target') != target
            or str(provenance.get('run_id')) != RUN or str(provenance.get('attempt')) != ATTEMPT):
        raise ValueError(target + ': original manifest source/run/attempt/target differs')
    archive = manifest['archive']
    if Path(archive['name']).name != archive['name']:
        raise ValueError(target + ': invalid original archive name')
    archive_path = manifest_path.parent / archive['name']
    if (archive_path.stat().st_size != archive['bytes']
            or sha256_file(archive_path) != archive['sha256']):
        raise ValueError(target + ': original ZIP bytes differ from original manifest')
    entry = manifest['entry']
    result = {'target': target, 'source_sha': SOURCE, 'run_id': RUN, 'attempt': ATTEMPT,
              'archive': archive, 'archive_verified_from_bytes': True,
              'entry': entry, 'entry_sha256': manifest['files'][entry]['sha256'],
              'sdk_version': manifest.get('sdk_version'), 'manifest': str(manifest_path),
              'accepted': False}
    if target == 'ipad':
        path = unique(root / target, 'xcodebuild.log', 'ipad-xctest-broad')
        parsed = xctest_log(path.read_text(encoding='utf-8', errors='replace'))
        result.update({key: parsed[key] for key in ('passed', 'failed', 'failed_cases', 'first_assertion')})
        if not result['failed_cases']:
            raise ValueError('original iPad broad log contains no named failed case')
    else:
        path = unique(root / target, 'validation.json', 'device')
        validation = json.loads(path.read_text(encoding='utf-8'))
        if (validation.get('source_sha') != SOURCE or str(validation.get('run_id')) != RUN
                or str(validation.get('attempt')) != ATTEMPT):
            raise ValueError('original Android validation source/run/attempt differs')
        if validation.get('apk_sha256') != result['entry_sha256']:
            raise ValueError('original Android validation APK differs from original ZIP program')
        parsed = android_cases(validation)
        # Keep case identity and detail, without copying screenshots or per-frame data.
        result.update({key: parsed[key] for key in ('passed', 'failed', 'skipped', 'total', 'problems')})
        result['failed_cases'] = [{key: case[key] for key in ('id', 'status', 'detail') if key in case}
                                  for case in parsed['failed_cases']]
        result['first_failure'] = result['failed_cases'][0] if result['failed_cases'] else None
        if not result['failed_cases']:
            raise ValueError('original Android walkthrough contains no named failed case')
    result['evidence'] = str(path)
    result['evidence_sha256'] = sha256_file(path)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Downloaded ipad/ and android/ directories')
    parser.add_argument('--output', type=Path, required=True, help='New JSON file; Markdown uses the same stem')
    args = parser.parse_args(argv)
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('original artifact extraction runs only in GitHub Actions')
    markdown = args.output.with_suffix('.md')
    if args.output.exists() or markdown.exists():
        raise SystemExit('choose new output files to preserve earlier diagnostics')
    report = {'schema': 1, 'kind': 's20-original-failure-diagnostics', 'source_sha': SOURCE,
              'run_id': RUN, 'attempt': ATTEMPT, 'new_acceptance_round': False,
              'accepted': False, 'targets': {}, 'problems': []}
    for target in ('ipad', 'android'):
        try:
            report['targets'][target] = extract(args.root, target)
        except (OSError, ValueError, KeyError, TypeError) as error:
            report['problems'].append(target + ': ' + str(error))
    report['diagnostics_complete'] = not report['problems']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = ['# 原 S20 失败诊断', '', '原源码：`' + SOURCE + '`；run `' + RUN + '`；attempt `1`。',
             '', '此输出只提取原失败，不计为新增验收轮次，两个目标仍为未通过。', '']
    for target, record in report['targets'].items():
        lines += ['## ' + target, '', '- 原 ZIP：`' + record['archive']['name'] + '`',
                  '- 原 ZIP SHA-256：`' + record['archive']['sha256'] + '`',
                  '- 原程序 SHA-256：`' + record['entry_sha256'] + '`',
                  '- 通过/失败：%s/%s' % (record['passed'], record['failed']), '',
                  '```json', json.dumps(record['failed_cases'], ensure_ascii=False, indent=2), '```', '']
    lines.extend('- 提取问题：' + problem for problem in report['problems'])
    markdown.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['diagnostics_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
