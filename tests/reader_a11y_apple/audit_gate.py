#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict assembly of the G16 Apple accessibility audit.

Reads the three per-platform reports produced by audit_collect.py and answers two
separate questions:

  audit_completed       - did the declared three targets actually run and produce
                          parseable, same-source/same-run/same-attempt evidence?
  accessibility_accepted - did that evidence avoid every blocking finding?

The gate never turns a finding into a pass and never accepts a platform whose
evidence is missing, stale or bound to another source. A completed audit that
found blocking defects exits 0 with accessibility_accepted=false; broken evidence
exits 1.
"""
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

PLATFORMS = ('macos', 'iphone', 'ipad')
SDK_BASELINE = '9854061be331fe603a1822d9b2b36ee357154927'


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            sha.update(chunk)
    return sha.hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--artifacts-json', type=Path,
                        help='GitHub Actions artifact list for this run (identity cross-check)')
    args = parser.parse_args()

    contract_path = args.contract.absolute()
    contract = load(contract_path)
    contract_sha = digest(contract_path)
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)

    problems = []
    reports = {}
    for platform in PLATFORMS:
        path = args.audit / platform / 'report.json'
        if not path.is_file():
            problems.append('%s: 缺少 report.json（该目标未产出审计证据）' % platform)
            continue
        reports[platform] = load(path)

    head = ''
    try:
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    except Exception:
        problems.append('无法读取本地 checkout 的 HEAD')
    if head and head != args.source_sha:
        problems.append('checkout HEAD %s 与本次 source %s 不一致' % (head, args.source_sha))

    program_shas = {}
    runtime_ids = {}
    fixtures_shas = {}
    sdk_shas = {}
    platform_summary = {}
    for platform, report in reports.items():
        if report.get('source_sha') != args.source_sha:
            problems.append('%s: source_sha %s 与运行 source %s 不一致'
                            % (platform, report.get('source_sha'), args.source_sha))
        if str(report.get('run_id')) != str(args.run_id) or str(report.get('attempt')) != str(args.attempt):
            problems.append('%s: run/attempt %s/%s 与本次 %s/%s 不一致'
                            % (platform, report.get('run_id'), report.get('attempt'),
                               args.run_id, args.attempt))
        if report.get('contract_sha256') != contract_sha:
            problems.append('%s: 契约摘要 %s 与本次 %s 不一致'
                            % (platform, report.get('contract_sha256'), contract_sha))
        environment = report.get('environment') or {}
        program = environment.get('program') or {}
        sha = program.get('executable_sha256')
        if not isinstance(sha, str) or len(sha) != 64:
            problems.append('%s: 受测程序 SHA-256 缺失' % platform)
        else:
            program_shas[platform] = sha
        if program.get('embedded_source_sha') != args.source_sha:
            problems.append('%s: 受测程序内嵌 EXRSourceSHA %s 与本次 source 不一致'
                            % (platform, program.get('embedded_source_sha')))
        if not environment.get('runtime'):
            problems.append('%s: 模拟器/宿主 runtime 未记录' % platform)
        runtime_ids[platform] = environment.get('runtime')
        fixtures_shas[platform] = environment.get('fixtures_sha256')
        sdk = environment.get('sdk') or {}
        sdk_shas[platform] = sdk.get('library_sha256')
        if platform == 'macos':
            if not str(environment.get('keyboard_ui_mode', '')).strip():
                problems.append('macos: 未记录键盘访问（AppleKeyboardUIMode）设置')
        else:
            content_size = str(environment.get('content_size', '')).strip()
            if not content_size or content_size == 'not-applicable':
                problems.append('%s: 未记录大字体装置（simctl content_size）' % platform)
            elif 'accessibility' not in content_size:
                problems.append('%s: 大字体装置内容尺寸为 %s，不是可访问性类别' % (platform, content_size))
        if environment.get('test_failures'):
            problems.append('%s: 审计用例失败 %s（该平台证据不完整）'
                            % (platform, ', '.join(environment['test_failures'])))
        counts = report.get('counts') or {}
        platform_summary[platform] = {
            'program_sha256': sha,
            'runtime': environment.get('runtime'),
            'device': environment.get('device_name'),
            'xcode': environment.get('xcode'),
            'keyboard_ui_mode': environment.get('keyboard_ui_mode'),
            'items': counts.get('items', 0),
            'pass': counts.get('pass', 0),
            'fail': counts.get('fail', 0),
            'blocked': counts.get('blocked', 0),
            'gap': counts.get('gap', 0),
            'stale': counts.get('stale', 0),
            'uncovered': counts.get('uncovered', 0),
            'states': sorted((report.get('states') or {}).keys()),
            'attachments': (environment.get('attachments') or {}).get('count', 0),
        }

    if len(set(fixtures_shas.values())) > 1:
        problems.append('各目标的夹具清单摘要不一致：%s' % json.dumps(fixtures_shas, sort_keys=True))
    # iPhone and iPad both audit the same iphonesimulator SDK build, so their
    # recorded library identity must agree; divergence means the staged SDK moved.
    if sdk_shas.get('iphone') and sdk_shas.get('ipad') and sdk_shas['iphone'] != sdk_shas['ipad']:
        problems.append('iPhone 与 iPad 记录的 SDK 摘要不一致：%s vs %s'
                        % (sdk_shas['iphone'], sdk_shas['ipad']))

    # Every contract state that applies to a platform must have a record on it.
    states = contract.get('states') or {}
    for platform, report in reports.items():
        recorded = set((report.get('states') or {}).keys())
        expected = {step for step, spec in states.items()
                    if platform in (spec.get('platforms') or [])}
        missing = sorted(expected - recorded)
        if missing:
            problems.append('%s: 契约步骤未被记录 %s' % (platform, ', '.join(missing)))
        extra = sorted(recorded - expected)
        if extra:
            problems.append('%s: 记录了契约外的步骤 %s' % (platform, ', '.join(extra)))

    items = []
    gaps = []
    uncovered = []
    for report in reports.values():
        items.extend(report.get('items') or [])
        gaps.extend(report.get('feature_gaps') or [])
        uncovered.extend(report.get('uncovered') or [])

    blocking_failures = [item for item in items
                         if item.get('verdict') == 'fail' and item.get('blocking')]
    failures = [item for item in items if item.get('verdict') == 'fail']
    blocked = [item for item in items if item.get('verdict') == 'blocked']
    stale = [gap for gap in gaps if gap.get('verdict') != 'gap']
    for gap in stale:
        problems.append('缺口 %s 的源码引用已失效：%s' % (gap.get('id'), gap.get('source_check')))

    def order(entry):
        rank = {'critical': 0, 'major': 1, 'minor': 2}
        return (0 if entry.get('blocking') else 1, rank.get(str(entry.get('severity')), 3),
                str(entry.get('platform')), str(entry.get('state')), str(entry.get('element')))

    findings = []
    for item in sorted(failures, key=order):
        findings.append({
            'platform': item.get('platform'),
            'state': item.get('state'),
            'element': item.get('element'),
            'element_path': item.get('element_path', ''),
            'criterion': item.get('criterion'),
            'expected': item.get('expected'),
            'actual': item.get('actual'),
            'severity': item.get('severity'),
            'blocking': item.get('blocking'),
            'fix': item.get('fix'),
            'screenshot': item.get('screenshot'),
        })

    # Artifact identity: the uploaded evidence must exist for this run and attempt,
    # carry a non-zero size and a digest, and embed the run/attempt in its name.
    artifacts = []
    if args.artifacts_json is not None:
        if not args.artifacts_json.is_file():
            problems.append('缺少工件清单，无法核对上传身份')
        else:
            listing = load(args.artifacts_json)
            entries = listing.get('artifacts') or []
            by_name = {}
            for entry in entries:
                if isinstance(entry, dict) and isinstance(entry.get('name'), str):
                    by_name[entry['name']] = entry
            for platform in PLATFORMS:
                name = 'reader-a11y-apple-audit-%s-%s-%s' % (platform, args.run_id, args.attempt)
                entry = by_name.get(name)
                if entry is None:
                    problems.append('缺少工件 %s（上传步骤未产出或名称不符）' % name)
                    continue
                size = int(entry.get('size_in_bytes') or 0)
                digest_value = entry.get('digest') or ''
                if size <= 0:
                    problems.append('工件 %s 字节数为 0' % name)
                if not str(digest_value).startswith('sha256:'):
                    problems.append('工件 %s 缺少 sha256 摘要' % name)
                if entry.get('expired'):
                    problems.append('工件 %s 已过期' % name)
                artifacts.append({
                    'id': entry.get('id'),
                    'name': name,
                    'size_in_bytes': size,
                    'digest': digest_value,
                    'expires_at': entry.get('expires_at'),
                    'head_sha': entry.get('head_sha'),
                    'workflow_run': entry.get('workflow_run'),
                })

    audit_completed = not problems and not blocked and not stale
    accessibility_accepted = audit_completed and not blocking_failures

    summary = {
        'schema': 1,
        'package': 'G16 Apple accessibility audit',
        'source_sha': args.source_sha,
        'run_id': args.run_id,
        'attempt': args.attempt,
        'contract': 'tests/reader_a11y_apple/a11y_contract.json',
        'contract_sha256': contract_sha,
        'sdk_baseline': SDK_BASELINE,
        'platforms': platform_summary,
        'program_sha256': program_shas,
        'runtime': runtime_ids,
        'audit_completed': audit_completed,
        'accessibility_accepted': accessibility_accepted,
        'blocking_findings': len(blocking_failures),
        'findings': findings,
        'gaps': gaps,
        'uncovered': uncovered,
        'artifacts': artifacts,
        'problems': problems,
        'limits': [
            '自动 XCUI 不等于 VoiceOver 通过；traits、朗读、转子与外观适配保持未覆盖。',
            '未在真机执行；只在 Actions 的 macOS 宿主与模拟器 runtime 上审计。',
            '未接真实 iCloud 账号或用户文件；只审计 -EXRUITestFixtures 夹具路径。',
            'macOS 无系统 Dynamic Type 缩放，大字体只在 iOS 模拟器上取证。',
            'iOS 全键盘访问未在模拟器启用，iOS 键盘路径保持未覆盖。',
        ],
    }
    (output / 'reader-a11y-apple-summary.json').write_text(
        json.dumps(summary, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    print(json.dumps({
        'audit_completed': audit_completed,
        'accessibility_accepted': accessibility_accepted,
        'blocking_findings': len(blocking_failures),
        'findings': len(failures),
        'gaps': len([gap for gap in gaps if gap.get('verdict') == 'gap']),
        'uncovered': len(uncovered),
        'problems': problems,
    }, indent=2, sort_keys=True))
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
