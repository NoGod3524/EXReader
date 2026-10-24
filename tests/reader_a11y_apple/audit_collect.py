#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Collect the G16 Apple accessibility audit evidence for one platform.

Runs only in cloud CI. It parses the tagged records the audit test bundle prints,
binds them to this source/run/attempt, hashes the audited program, the installed
SDK and the fixture manifest, then evaluates every declared expectation of
a11y_contract.json against the observed accessibility trees.

The collector never decides whether the product is accessible. It produces
per-criterion items; audit_gate.py turns them into audit_completed and
accessibility_accepted.
"""
import argparse
import hashlib
import json
import os
import platform as host_platform
import plistlib
import re
import subprocess
import sys
from pathlib import Path

TAGS = (('EXR_A11Y_STATE', 'states'), ('EXR_A11Y_ENV', 'environment'),
        ('EXR_A11Y_KEYBOARD', 'keyboard'), ('EXR_A11Y_ERROR', 'errors'))
PLATFORMS = ('macos', 'iphone', 'ipad')
INTERACTIVE_ROLES = ('Button', 'Link', 'TextField', 'TextView', 'Cell',
                     'SegmentedControl', 'Slider', 'Toggle', 'SearchField', 'PickerWheel')


def require(condition, message):
    if not condition:
        raise SystemExit('audit-collect: ' + message)


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            sha.update(chunk)
    return sha.hexdigest()


def cloud_identity(platform):
    require(os.environ.get('GITHUB_ACTIONS') == 'true',
            'audit evidence is collected only in cloud CI')
    return {
        'platform': platform,
        'source_sha': os.environ['GITHUB_SHA'],
        'run_id': os.environ['GITHUB_RUN_ID'],
        'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
        'job': os.environ.get('GITHUB_JOB', ''),
        'runner': host_platform.platform(),
        'run_url': '%s/%s/actions/runs/%s' % (os.environ.get('GITHUB_SERVER_URL', ''),
                                             os.environ.get('GITHUB_REPOSITORY', ''),
                                             os.environ['GITHUB_RUN_ID']),
    }


def parse_records(log_text):
    records = {'states': {}, 'environment': [], 'keyboard': [], 'errors': [], 'order': []}
    for raw in log_text.splitlines():
        line = raw.strip()
        for tag, key in TAGS:
            index = line.find(tag + ' ')
            if index < 0:
                continue
            try:
                payload = json.loads(line[index + len(tag) + 1:])
            except ValueError:
                continue
            if not isinstance(payload, dict):
                continue
            if key == 'states':
                step = payload.get('step')
                if isinstance(step, str) and step:
                    if step not in records['states']:
                        records['order'].append(step)
                    records['states'][step] = payload
            else:
                records[key].append(payload)
            break
    return records


def parse_cases(log_text):
    cases = {}
    pattern = re.compile(r"Test Case '-\[(?P<suite>[^\s]+) (?P<name>[^\]]+)\]' (?P<result>passed|failed)")
    for line in log_text.splitlines():
        match = pattern.search(line)
        if match:
            cases[match.group('name')] = match.group('result')
    return cases


def element_map(state):
    result = {}
    for element in state.get('elements') or []:
        if not isinstance(element, dict):
            continue
        identifier = element.get('id')
        if isinstance(identifier, str) and identifier and identifier not in result:
            result[identifier] = element
    return result


def roles_of(spec):
    role = spec.get('role')
    if isinstance(role, str):
        return [role]
    if isinstance(role, list):
        return [value for value in role if isinstance(value, str)]
    return []


def rect(element):
    frame = element.get('frame') or {}
    return {
        'x': float(frame.get('x') or 0),
        'y': float(frame.get('y') or 0),
        'width': float(frame.get('width') or 0),
        'height': float(frame.get('height') or 0),
    }


def ax_name(element):
    label = element.get('label')
    label = label if isinstance(label, str) else ''
    if label.strip():
        return label
    value = element.get('value')
    return value if isinstance(value, str) else ''


def make_item(platform, state, element, criterion, verdict, expected, actual,
              severity='major', blocking=False, fix='', screenshot=''):
    return {
        'platform': platform,
        'state': state,
        'element': element,
        'criterion': criterion,
        'verdict': verdict,
        'expected': expected,
        'actual': actual,
        'severity': severity,
        'blocking': bool(blocking),
        'fix': fix,
        'screenshot': screenshot,
    }


def evaluate_required(platform, step, spec, elements, items, screenshot):
    for requirement in spec.get('required') or []:
        identifier = requirement.get('id')
        if not isinstance(identifier, str):
            continue
        blocking = requirement.get('blocking', True)
        severity = requirement.get('severity', 'major')
        fix = requirement.get('fix', '')
        element = elements.get(identifier)
        if element is None:
            items.append(make_item(platform, step, identifier, 'element-present', 'fail',
                                   '语义树中存在 ' + identifier, '未出现该标识的元素',
                                   severity, blocking, fix, screenshot))
            continue
        expected_roles = roles_of(requirement)
        role = element.get('role')
        if expected_roles:
            if role in expected_roles:
                items.append(make_item(platform, step, identifier, 'role', 'pass',
                                       '/'.join(expected_roles), str(role), severity, False, fix, screenshot))
            else:
                items.append(make_item(platform, step, identifier, 'role', 'fail',
                                       '/'.join(expected_roles), str(role), severity, blocking, fix, screenshot))
        name = ax_name(element)
        if requirement.get('name_nonempty', True):
            if name.strip():
                items.append(make_item(platform, step, identifier, 'accessible-name', 'pass',
                                       '非空可访问名称', name[:200], severity, False, fix, screenshot))
            else:
                items.append(make_item(platform, step, identifier, 'accessible-name', 'fail',
                                       '非空可访问名称', '名称与值均为空（辅助技术读不到内容）',
                                       severity, blocking, fix, screenshot))
        if 'name_equals' in requirement:
            wanted = requirement['name_equals']
            verdict = 'pass' if name.strip() == wanted.strip() else 'fail'
            items.append(make_item(platform, step, identifier, 'name-equals', verdict,
                                   wanted, name[:200], severity, blocking and verdict == 'fail', fix, screenshot))
        if 'name_contains' in requirement:
            wanted = requirement['name_contains']
            verdict = 'pass' if wanted in name else 'fail'
            items.append(make_item(platform, step, identifier, 'name-contains', verdict,
                                   wanted, name[:200], severity, blocking and verdict == 'fail', fix, screenshot))
        if 'name_not_contains' in requirement:
            unwanted = requirement['name_not_contains']
            verdict = 'fail' if unwanted in name else 'pass'
            items.append(make_item(platform, step, identifier, 'name-changed', verdict,
                                   '名称不再包含 ' + unwanted, name[:200],
                                   severity, blocking and verdict == 'fail', fix, screenshot))
        if 'value_contains' in requirement:
            wanted = requirement['value_contains']
            value = element.get('value')
            value = value if isinstance(value, str) else ''
            verdict = 'pass' if wanted in value else 'fail'
            items.append(make_item(platform, step, identifier, 'value-contains', verdict,
                                   wanted, value[:200], severity, blocking and verdict == 'fail', fix, screenshot))
        if 'expect_enabled' in requirement:
            wanted = bool(requirement['expect_enabled'])
            observed = bool(element.get('enabled'))
            verdict = 'pass' if observed == wanted else 'fail'
            items.append(make_item(platform, step, identifier, 'enabled-state', verdict,
                                   'enabled=' + str(wanted).lower(), 'enabled=' + str(observed).lower(),
                                   severity, blocking and verdict == 'fail', fix, screenshot))


def evaluate_geometry(platform, step, spec, elements, window, policy, items, screenshot):
    tolerance = float(policy.get('clip_tolerance_pt', 2))
    targets = policy.get('minimum_target_pt') or {}
    blocking_min = float(targets.get('blocking', 24))
    blocking_platforms = targets.get('blocking_platforms') or []
    advisory_min = float(targets.get('advisory_ios', 44))
    advisory_macos = float(targets.get('advisory_macos', 20))
    checked = []
    for identifier in spec.get('interactive') or []:
        element = elements.get(identifier)
        if element is None:
            continue
        checked.append((identifier, element))
        box = rect(element)
        if box['width'] <= 0 or box['height'] <= 0:
            items.append(make_item(platform, step, identifier, 'frame-present', 'fail',
                                   '可交互元素有非零布局框', '布局框为空', 'major', True,
                                   spec.get('fix', ''), screenshot))
            continue
        if bool(element.get('enabled')) and element.get('hittable') is False:
            items.append(make_item(platform, step, identifier, 'hittable', 'fail',
                                   '启用中的控件可被命中', 'isHittable=false（可能被遮挡或在窗口外）',
                                   'major', True, '', screenshot))
        else:
            items.append(make_item(platform, step, identifier, 'hittable', 'pass',
                                   '启用中的控件可被命中', 'isHittable=' + str(element.get('hittable')).lower(),
                                   'major', False, '', screenshot))
        outside = (box['x'] < window['x'] - tolerance
                   or box['y'] < window['y'] - tolerance
                   or box['x'] + box['width'] > window['x'] + window['width'] + tolerance
                   or box['y'] + box['height'] > window['y'] + window['height'] + tolerance)
        if outside:
            items.append(make_item(platform, step, identifier, 'clipped', 'fail',
                                   '控件完整落在窗口内',
                                   'frame=%s window=%s' % (json.dumps(box, sort_keys=True),
                                                           json.dumps(window, sort_keys=True)),
                                   'major', True,
                                   '为大字体/小窗口加滚动回退或压缩行距，避免控件溢出窗口', screenshot))
        else:
            items.append(make_item(platform, step, identifier, 'clipped', 'pass',
                                   '控件完整落在窗口内', 'frame 在窗口内', 'major', False, '', screenshot))
        smallest = min(box['width'], box['height'])
        if platform in blocking_platforms and smallest < blocking_min:
            items.append(make_item(platform, step, identifier, 'target-size', 'fail',
                                   '控件不小于 %g pt（WCAG 2.5.8）' % blocking_min,
                                   '最小边 %.1f pt' % smallest, 'major', True,
                                   '扩大点击区域（.contentShape / padding / frame(minWidth:minHeight:)）', screenshot))
        else:
            items.append(make_item(platform, step, identifier, 'target-size', 'pass',
                                   '控件不小于 %g pt（WCAG 2.5.8）' % blocking_min,
                                   '最小边 %.1f pt' % smallest, 'minor', False, '', screenshot))
            if platform in ('iphone', 'ipad') and smallest < advisory_min:
                items.append(make_item(platform, step, identifier, 'target-size-hig', 'advisory',
                                       'iOS HIG 建议不小于 %g pt' % advisory_min,
                                       '最小边 %.1f pt' % smallest, 'minor', False,
                                       '按 HIG 放大到 44 pt 触控区', screenshot))
            elif platform == 'macos' and smallest < advisory_macos:
                items.append(make_item(platform, step, identifier, 'target-size-macos', 'advisory',
                                       'macOS 指针目标建议不小于 %g pt' % advisory_macos,
                                       '最小边 %.1f pt' % smallest, 'minor', False,
                                       '按 macOS 控件惯例放大（padding 或 frame(minWidth:minHeight:)）', screenshot))
    for left in range(len(checked)):
        for right in range(left + 1, len(checked)):
            first_id, first = checked[left]
            second_id, second = checked[right]
            a = rect(first)
            b = rect(second)
            overlap_width = min(a['x'] + a['width'], b['x'] + b['width']) - max(a['x'], b['x'])
            overlap_height = min(a['y'] + a['height'], b['y'] + b['height']) - max(a['y'], b['y'])
            if overlap_width <= 0 or overlap_height <= 0:
                continue
            contains = ((a['x'] <= b['x'] and a['y'] <= b['y']
                         and a['x'] + a['width'] >= b['x'] + b['width']
                         and a['y'] + a['height'] >= b['y'] + b['height'])
                        or (b['x'] <= a['x'] and b['y'] <= a['y']
                            and b['x'] + b['width'] >= a['x'] + a['width']
                            and b['y'] + b['height'] >= a['y'] + a['height']))
            if contains:
                continue
            smaller = min(a['width'] * a['height'], b['width'] * b['height'])
            area = overlap_width * overlap_height
            if smaller > 0 and area / smaller > 0.5:
                items.append(make_item(platform, step, first_id + '|' + second_id, 'overlap', 'fail',
                                       '可交互控件的布局框不互相重叠',
                                       '重叠面积占较小控件 %.0f%%' % (area / smaller * 100),
                                       'major', True, '在压缩布局中重新分配间距，避免控件互相覆盖', screenshot))


def evaluate_book_rows(platform, step, spec, elements, items, screenshot):
    """Shelf order is a product decision, so each audited title must appear in at
    least one row accessible name rather than at a fixed index."""
    observed = sorted(ax_name(element)[:60] for identifier, element in elements.items()
                      if identifier.startswith("library.book."))
    for wanted in spec.get("book_row_names") or []:
        if not isinstance(wanted, str):
            continue
        matched = sorted(identifier for identifier, element in elements.items()
                         if identifier.startswith("library.book.") and wanted in ax_name(element))
        if matched:
            items.append(make_item(platform, step, ",".join(matched), "book-row-visible", "pass",
                                   "书架行名称包含 " + wanted, ", ".join(observed), "major", False,
                                   "", screenshot))
        else:
            items.append(make_item(platform, step, "library.book.*", "book-row-visible", "fail",
                                   "书架行名称包含 " + wanted,
                                   "行名称中没有该书：" + (", ".join(observed) if observed else "<无书架行>"),
                                   "major", True,
                                   "书架行必须把书名与格式/位置暴露为可访问名称", screenshot))

def evaluate_reading_order(platform, step, spec, elements, policy, items, screenshot):
    tolerance = float(policy.get('reading_order_tolerance_pt', 20))
    sequence = [value for value in (spec.get('reading_sequence') or []) if isinstance(value, str)]
    previous = None
    for identifier in sequence:
        element = elements.get(identifier)
        if element is None:
            continue
        box = rect(element)
        if previous is not None and box['y'] < previous[1] - tolerance:
            items.append(make_item(platform, step, identifier, 'reading-order', 'fail',
                                   '辅助技术顺序与视觉顺序一致（自 ' + previous[0] + ' 之后向下）',
                                   'y=%.1f 早于 %s 的 y=%.1f' % (box['y'], previous[0], previous[1]),
                                   'major', False,
                                   '检查容器顺序或补 accessibilitySortPriority', screenshot))
        previous = (identifier, box['y'])


def evaluate_content_rule(platform, rule, elements, items):
    identifier = rule.get('element')
    element = elements.get(identifier)
    state_id = rule.get('state')
    shot = ''
    if element is None:
        return
    field = rule.get('field', 'label')
    # macOS exposes SwiftUI Text as label="" plus value="<string>", so a content
    # rule that asks for the accessible name must use the same fallback the
    # name checks use; otherwise the rule silently passes with an empty string.
    if field == 'label':
        value = ax_name(element)
    else:
        raw_value = element.get(field)
        value = raw_value if isinstance(raw_value, str) else ''
    expected = rule.get('expected', '')
    fix = rule.get('fix', '')
    severity = rule.get('severity', 'minor')
    blocking = bool(rule.get('blocking', False))
    problems = []
    if 'forbid_regex' in rule and re.search(rule['forbid_regex'], value):
        problems.append('匹配禁止模式 ' + rule['forbid_regex'])
    if 'forbid_substring' in rule and rule['forbid_substring'] in value:
        problems.append('包含 ' + rule['forbid_substring'])
    if 'warn_regex' in rule and re.search(rule['warn_regex'], value):
        problems.append('命中需改进模式 ' + rule['warn_regex'])
    if 'max_chars' in rule and len(value) > int(rule['max_chars']):
        problems.append('长度 %d 超过 %s' % (len(value), rule['max_chars']))
    actual = (value[:200] if value else '<empty>')
    if problems:
        items.append(make_item(platform, state_id, identifier, 'content-rule:' + rule['id'], 'fail',
                               expected, '; '.join(problems) + ' | ' + actual, severity, blocking, fix, shot))
    else:
        items.append(make_item(platform, state_id, identifier, 'content-rule:' + rule['id'], 'pass',
                               expected, actual, severity, False, fix, shot))


def verify_source(root, verify):
    path = Path(root) / verify.get('file', '')
    if not path.is_file():
        return False, 'missing source file ' + str(verify.get('file'))
    text = path.read_text(encoding='utf-8', errors='replace')
    lines = text.splitlines()
    for needle in verify.get('contains') or []:
        if needle not in text:
            return False, 'source no longer contains: ' + needle
    absent = verify.get('absent')
    if absent:
        scope = verify.get('absent_in_lines')
        if scope:
            start, end = int(scope[0]), int(scope[1])
            window = '\n'.join(lines[start - 1:end])
            if absent in window:
                return False, 'source lines %d-%d now contain %s' % (start, end, absent)
        elif absent in text:
            return False, 'source now contains: ' + absent
    return True, 'source citation holds'


def evaluate_keyboard(platform, contract, records, items):
    spec = contract.get('keyboard') or {}
    if platform not in (spec.get('platforms') or []):
        return
    entries = [entry for entry in records['keyboard'] if entry.get('platform') == platform]
    if not entries:
        items.append(make_item(platform, 'reader.keyboard', '', 'keyboard-path', 'blocked',
                               spec.get('expected', ''),
                               '没有键盘遍历记录（该目标未执行键盘审计）', 'major', True,
                               spec.get('fix', ''), ''))
        return
    entry = entries[-1]
    candidates = [value for value in (entry.get('candidates') or []) if isinstance(value, str)]
    distinct = [value for value in (entry.get('distinct_states') or []) if isinstance(value, str)]
    changed = bool(entry.get('keyboard_state_changed'))
    if changed:
        actual = '可观察状态出现 %d 种取值：%s' % (len(distinct), ' / '.join(distinct[:6]))
    else:
        actual = ('16 次 Tab（每 4 次追加 Space）后可观察状态无变化，样本=%s，候选控件 %d 个'
                  % (distinct[0] if distinct else '<empty>', len(candidates)))
    items.append(make_item(platform, 'reader.keyboard', '', 'keyboard-operable',
                           'pass' if changed else 'fail',
                           spec.get('expected', ''), actual, 'major',
                           bool(spec.get('blocking', True)) and not changed,
                           spec.get('fix', ''), ''))
    focus = spec.get('focus_order') or {}
    items.append(make_item(platform, 'reader.keyboard', '', 'keyboard-focus-order',
                           focus.get('verdict', 'uncovered'),
                           '逐控件焦点顺序与 Tab 可达集合',
                           focus.get('reason', ''), 'major', False, '', ''))


def evaluate_scaling(platform, contract, records, items):
    for rule in contract.get('scaling') or []:
        if platform not in (rule.get('platforms') or []):
            continue
        source_state = records['states'].get(rule.get('from'))
        target_state = records['states'].get(rule.get('to'))
        if source_state is None or target_state is None:
            continue
        source_elements = element_map(source_state)
        target_elements = element_map(target_state)
        base_metrics = source_state.get('metrics') or {}
        large_metrics = target_state.get('metrics') or {}
        base_pt = float(base_metrics.get('caption1_pt') or 0)
        large_pt = float(large_metrics.get('caption1_pt') or 0)
        if base_pt <= 0 or large_pt <= base_pt:
            items.append(make_item(platform, rule.get('to'), '', 'dynamic-type-fixture', 'blocked',
                                   '设备内容尺寸类别已提升（caption1 点值变大）',
                                   'caption1 默认 %.1fpt 与大字体 %.1fpt 相同或缺失：大字体装置未生效，'
                                   '不能用它评判产品' % (base_pt, large_pt),
                                   'major', True,
                                   'workflow: xcrun simctl ui <udid> content_size '
                                   'accessibility-extra-extra-extra-large 后再跑大字体用例', ''))
            continue
        items.append(make_item(platform, rule.get('to'), '', 'dynamic-type-fixture', 'pass',
                               '设备内容尺寸类别已提升', 'caption1 %.1fpt → %.1fpt' % (base_pt, large_pt),
                               'minor', False, '', ''))
        for identifier in rule.get('ids') or []:
            base = source_elements.get(identifier)
            large = target_elements.get(identifier)
            if base is None or large is None:
                continue
            base_height = rect(base)['height']
            large_height = rect(large)['height']
            growth = large_height - base_height
            verdict = 'pass' if growth >= float(rule.get('min_growth_pt', 0.5)) else 'fail'
            items.append(make_item(platform, rule.get('to'), identifier, 'dynamic-type-scaling', verdict,
                                   rule.get('expected', '默认字号高度 %.1f，可访问字号应更高' % base_height),
                                   '默认 %.1fpt → 大字体 %.1fpt（增长 %.1fpt）' % (base_height, large_height, growth),
                                   rule.get('severity', 'major'),
                                   bool(rule.get('blocking', False)) and verdict == 'fail',
                                   rule.get('fix', ''), large.get('screenshot', '')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=list(PLATFORMS), required=True)
    parser.add_argument('--log', type=Path, action='append', required=True)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--xcresult', type=Path, action='append', required=True)
    parser.add_argument('--content-size', default='')
    parser.add_argument('--attachments', type=Path, action='append')
    parser.add_argument('--destination-file', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--sdk-root', type=Path, required=True)
    parser.add_argument('--keyboard-ui-mode', default='')
    parser.add_argument('--root', type=Path, default=Path('.'))
    args = parser.parse_args()

    identity = cloud_identity(args.platform)
    contract = json.loads(args.contract.read_text(encoding='utf-8'))
    policy = contract.get('policy') or {}
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    log_text = '\n'.join(path.read_text(encoding='utf-8', errors='replace') for path in args.log)
    records = parse_records(log_text)
    cases = parse_cases(log_text)

    destination = [line.strip() for line in args.destination_file.read_text().splitlines()]
    require(len(destination) >= 4 and all(destination[:4]), 'destination identity incomplete')
    executable = args.app / ('Contents/MacOS/EXReaderHost' if args.platform == 'macos' else 'EXReaderHost')
    require(executable.is_file(), 'audited host executable missing: ' + str(executable))
    info_plist = args.app / ('Contents/Info.plist' if args.platform == 'macos' else 'Info.plist')
    require(info_plist.is_file(), 'audited host Info.plist missing')
    with info_plist.open('rb') as stream:
        plist = plistlib.load(stream)
    fixtures = json.loads(args.fixtures.read_text(encoding='utf-8'))
    sdk_target = 'macos' if args.platform == 'macos' else 'iphonesimulator'
    sdk_library = args.sdk_root / 'lib' / 'libexreader.dylib'
    require(sdk_library.is_file(), 'installed SDK library missing: ' + str(sdk_library))

    environment = {
        'platform': args.platform,
        'destination': destination[0],
        'device_udid': destination[1],
        'device_name': destination[2],
        'runtime': destination[3],
        'xcode': subprocess.check_output(['xcodebuild', '-version'], text=True).strip(),
        'swift': subprocess.check_output(['xcrun', 'swiftc', '--version'], text=True).strip(),
        'keyboard_ui_mode': args.keyboard_ui_mode.strip(),
        'content_size': args.content_size.strip(),
        'program': {
            'bundle': str(args.app),
            'executable': executable.name,
            'executable_sha256': digest(executable),
            'executable_bytes': executable.stat().st_size,
            'info_plist_sha256': digest(info_plist),
            'embedded_source_sha': plist.get('EXRSourceSHA', ''),
        },
        'sdk': {'target': sdk_target, 'library': sdk_library.name,
                'library_sha256': digest(sdk_library)},
        'fixtures_sha256': hashlib.sha256(
            json.dumps(fixtures, sort_keys=True).encode('utf-8')).hexdigest(),
        'fixtures': fixtures,
        'xcresult_sha256': {},
        'log_sha256': {path.name: digest(path) for path in args.log},
        'test_cases': cases,
        'test_failures': sorted(name for name, result in cases.items() if result != 'passed'),
    }
    for bundle in args.xcresult:
        if bundle.is_dir():
            info = bundle / 'Info.plist'
            environment['xcresult_sha256'][bundle.name] = digest(info) if info.is_file() else ''
    attachments = {}
    screenshots = []
    for directory in args.attachments or []:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob('*')):
            if path.is_file():
                attachments[path.name] = {'sha256': digest(path), 'bytes': path.stat().st_size}
        manifest = directory / 'manifest.json'
        if not manifest.is_file():
            continue
        try:
            entries = json.loads(manifest.read_text(encoding='utf-8'))
        except ValueError:
            continue
        for entry in entries if isinstance(entries, list) else []:
            for attachment in (entry.get('attachments') or []) if isinstance(entry, dict) else []:
                if not isinstance(attachment, dict):
                    continue
                exported = attachment.get('exportedFileName') or ''
                human = attachment.get('suggestedHumanReadableName') or ''
                if not exported:
                    continue
                # xcresulttool appends "_<index>_<uuid>.<ext>"; keep the authored
                # attachment name so every finding's screenshot is traceable.
                name = re.sub(r'_[0-9]+_[0-9A-Fa-f-]+\.[A-Za-z0-9]+$', '', human)
                path = directory / exported
                screenshots.append({
                    'name': name,
                    'file': exported,
                    'bytes': path.stat().st_size if path.is_file() else 0,
                    'sha256': digest(path) if path.is_file() else '',
                })
    environment['attachments'] = {'count': len(attachments), 'files': attachments}
    environment['screenshots'] = screenshots

    items = []
    states_summary = {}
    states = contract.get('states') or {}
    for step in sorted(states):
        spec = states[step]
        if args.platform not in (spec.get('platforms') or []):
            continue
        state = records['states'].get(step)
        if state is None:
            items.append(make_item(args.platform, step, '', 'state-recorded', 'blocked',
                                   '该步骤产生了可解析的 AX 记录',
                                   '没有记录：审计用例未执行到该步骤或输出被截断', 'major', True,
                                   '', ''))
            continue
        recorded_platform = state.get('platform')
        if recorded_platform != args.platform:
            # UIDevice idiom in the runner process reports iPhone on an iPad, so the
            # family is confirmed against the simctl destination before trusting it.
            device_name = str(environment.get('device_name', ''))
            family = {'iphone': 'iPhone', 'ipad': 'iPad'}.get(args.platform, '')
            if (recorded_platform in ('iphone', 'ipad') and family
                    and family.lower() in device_name.lower()):
                items.append(make_item(args.platform, step, '', 'state-platform', 'pass',
                                       '记录设备族与 simctl 目的地一致',
                                       '记录=%s 目的地=%s' % (recorded_platform, device_name),
                                       'major', False,
                                       '测试进程 idiom 不可靠；平台由 TEST_RUNNER_EXR_A11Y_PLATFORM 与目的地共同固定',
                                       ''))
            else:
                items.append(make_item(args.platform, step, '', 'state-platform', 'blocked',
                                       '记录平台为 ' + args.platform, str(recorded_platform),
                                       'major', True, '', ''))
                continue
        if state.get('app_state') != 'runningForeground':
            items.append(make_item(args.platform, step, '', 'app-foreground', 'blocked',
                                   'runningForeground', str(state.get('app_state')), 'major', True, '', ''))
        elements = element_map(state)
        screenshot = state.get('screenshot') if isinstance(state.get('screenshot'), str) else ''
        window = {key: float((state.get('window') or {}).get(key) or 0)
                  for key in ('x', 'y', 'width', 'height')}
        if window['width'] <= 0 or window['height'] <= 0:
            items.append(make_item(args.platform, step, '', 'window-frame', 'blocked',
                                   '窗口布局框非空', 'window=' + json.dumps(window, sort_keys=True),
                                   'major', True, '', screenshot))
        evaluate_required(args.platform, step, spec, elements, items, screenshot)
        evaluate_book_rows(args.platform, step, spec, elements, items, screenshot)
        evaluate_geometry(args.platform, step, spec, elements, window, policy, items, screenshot)
        evaluate_reading_order(args.platform, step, spec, elements, policy, items, screenshot)
        for share in spec.get('state_exposure') or []:
            for identifier in share.get('ids') or []:
                element = elements.get(identifier)
                if element is None:
                    continue
                wanted = bool(share.get('expect_enabled', False))
                observed = bool(element.get('enabled'))
                verdict = 'pass' if observed == wanted else 'fail'
                items.append(make_item(args.platform, step, identifier, 'state-exposure', verdict,
                                       'enabled=' + str(wanted).lower(),
                                       'enabled=' + str(observed).lower(),
                                       share.get('severity', 'minor'),
                                       bool(share.get('blocking', False)) and verdict == 'fail',
                                       share.get('note', ''), screenshot))
        states_summary[step] = {
            'element_count': int(state.get('element_count') or 0),
            'anonymous_controls': int(state.get('anonymous_controls') or 0),
            'orientation': state.get('orientation'),
            'window': window,
            'metrics': state.get('metrics'),
            'screenshot': screenshot,
            'test': state.get('test'),
            'lanes_observed': sorted(elements)[:40],
        }

    for rule in contract.get('content_rules') or []:
        state = records['states'].get(rule.get('state'))
        if state is None or state.get('platform') != args.platform:
            continue
        evaluate_content_rule(args.platform, rule, element_map(state), items)

    evaluate_scaling(args.platform, contract, records, items)
    evaluate_keyboard(args.platform, contract, records, items)

    gaps = []
    for gap in contract.get('feature_gaps') or []:
        if args.platform not in (gap.get('platforms') or []):
            continue
        ok, detail = verify_source(args.root, gap.get('verify') or {})
        gaps.append({
            'id': gap.get('id'),
            'criterion': gap.get('criterion'),
            'platform': args.platform,
            'verdict': 'gap' if ok else 'stale',
            'expected': gap.get('expected', ''),
            'actual': gap.get('actual', ''),
            'severity': gap.get('severity', 'minor'),
            'blocking': bool(gap.get('blocking', False)),
            'fix': gap.get('fix', ''),
            'source_check': detail,
            'source_file': (gap.get('verify') or {}).get('file', ''),
        })

    uncovered = []
    for entry in contract.get('uncovered') or []:
        if args.platform not in (entry.get('platforms') or []):
            continue
        uncovered.append({
            'id': entry.get('id'),
            'criterion': entry.get('criterion'),
            'platform': args.platform,
            'verdict': 'uncovered',
            'reason': entry.get('reason', ''),
            'owner': entry.get('owner', ''),
        })

    # Bind every item to the accessibility-tree path of the element it audited so
    # the report names a location inside the app, not just an identifier.
    paths = {}
    for step, state in records['states'].items():
        for identifier, element in element_map(state).items():
            path = element.get('path')
            paths[(step, identifier)] = path if isinstance(path, str) else ''
    for item in items:
        item['element_path'] = paths.get((item['state'], item['element']), '')

    counts = {}
    for verdict in ('pass', 'fail', 'blocked', 'uncovered', 'gap', 'stale'):
        counts[verdict] = len([item for item in items if item['verdict'] == verdict]) \
            if verdict in ('pass', 'fail', 'blocked') else 0
    counts['gap'] = len([gap for gap in gaps if gap['verdict'] == 'gap'])
    counts['stale'] = len([gap for gap in gaps if gap['verdict'] == 'stale'])
    counts['uncovered'] = len(uncovered)
    counts['items'] = len(items)

    report = {
        'schema': 1,
        'package': 'G16 Apple accessibility audit',
        'platform': args.platform,
        'source_sha': identity['source_sha'],
        'run_id': identity['run_id'],
        'attempt': identity['attempt'],
        'job': identity['job'],
        'run_url': identity['run_url'],
        'environment': environment,
        'contract_sha256': digest(args.contract),
        'states': states_summary,
        'records': {'states': sorted(records['states']), 'environment': len(records['environment']),
                    'keyboard': len(records['keyboard']), 'errors': records['errors']},
        'items': items,
        'feature_gaps': gaps,
        'uncovered': uncovered,
        'counts': counts,
    }
    (output / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n',
                                       encoding='utf-8')
    blocked = [item for item in items if item['verdict'] == 'blocked']
    blocking = [item for item in items if item['verdict'] == 'fail' and item['blocking']]
    print(json.dumps({
        'platform': args.platform,
        'items': len(items),
        'pass': counts['pass'],
        'fail': counts['fail'],
        'blocked': len(blocked),
        'blocking_failures': len(blocking),
        'gaps': counts['gap'],
        'stale_gaps': counts['stale'],
        'uncovered': counts['uncovered'],
        'program_sha256': environment['program']['executable_sha256'],
        'runtime': environment['runtime'],
    }, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
