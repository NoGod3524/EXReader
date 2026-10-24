#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Positive and negative cases for the overlap judge (runs only in Actions).

Root review found the first version too broad: it skipped every pair whose path
mentioned a ScrollView, which also hid two controls overlapping *inside* one
scroll view. This harness pins the narrowed contract:

  * same container (including both outside any scroll view) -> compare laid-out
    boxes with the unchanged 50% threshold, so a real overlap fails;
  * different containers -> clip each side by its recorded scroll viewport and
    compare the visible parts, so scroll content below the viewport cannot fake
    an overlap with an external control;
  * an unrecorded ancestor viewport -> undetermined, reported as uncovered,
    never as clipped.

Case 13 replays the exact frames behind the first run's false blocking item so the
gap is demonstrated on the original classification before the fix is trusted.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).absolute().parent))
from audit_collect import classify_overlap, scroll_chain  # noqa: E402

TOLERANCE = 0.01


def element(identifier, x, y, width, height, path, role='Button', enabled=True):
    return {'id': identifier, 'role': role, 'label': identifier, 'value': '',
            'frame': {'x': float(x), 'y': float(y), 'width': float(width), 'height': float(height)},
            'enabled': enabled, 'path': path}


def legacy_v1_verdict(first, second):
    """The first version: any ScrollView in either path skipped the pair entirely."""
    if 'ScrollView' in str(first.get('path', '')) or 'ScrollView' in str(second.get('path', '')):
        return 'skipped'
    return None


def assert_ratio(case, observed, expected):
    return abs(observed - expected) <= TOLERANCE


def build_cases():
    cases = []
    scroll_path = 'Application>Window>ScrollView[list]'
    viewport = element('list', 0, 0, 200, 400, scroll_path, role='ScrollView')
    inside = scroll_path + '>Button[%s]'
    plain = 'Application>Window>Button[%s]'

    def case(identifier, description, expected, elements, first, second, ratio=None):
        return {'id': identifier, 'description': description, 'expected': expected,
                'threshold_ratio': ratio,
                'outcome': classify_overlap(elements[first], elements[second], elements, 0.5)}

    # 1-4. Same container, shared viewport recorded: the unchanged 50% threshold.
    elements = {'list': viewport,
                'a': element('a', 0, 0, 100, 100, inside % 'a'),
                'b': element('b', 20, 10, 100, 100, inside % 'b')}
    cases.append(case('same-container-visible-overlap',
                      '同一滚动容器内两个可见控件真实重叠 72%（互不包含）',
                      'fail', elements, 'a', 'b', 0.72))
    elements = {'list': viewport,
                'a': element('a', 0, 0, 100, 100, inside % 'a'),
                'b': element('b', 80, 0, 100, 100, inside % 'b')}
    cases.append(case('same-container-below-threshold',
                      '同一容器内 20% 重叠低于 50% 阈值',
                      'none', elements, 'a', 'b', 0.20))
    elements = {'list': viewport,
                'a': element('a', 0, 0, 100, 100, inside % 'a'),
                'b': element('b', 51, 0, 100, 100, inside % 'b')}
    cases.append(case('threshold-49-percent', '同一容器内 49% 重叠仍判通过',
                      'none', elements, 'a', 'b', 0.49))
    elements = {'list': viewport,
                'a': element('a', 0, 0, 100, 100, inside % 'a'),
                'b': element('b', 49, 0, 100, 100, inside % 'b')}
    cases.append(case('threshold-51-percent', '同一容器内 51% 重叠判遮挡',
                      'fail', elements, 'a', 'b', 0.51))

    # 5-7. Siblings where one box fully covers the other stay a real occlusion:
    # area alone never proves a parent-child relationship.
    elements = {'list': viewport,
                'a': element('a', 0, 0, 100, 100, inside % 'a'),
                'b': element('b', 0, 0, 100, 100, inside % 'b')}
    cases.append(case('same-container-containment-equal',
                      '同级同尺寸完全重合仍判遮挡', 'fail', elements, 'a', 'b', 1.0))
    elements = {'list': viewport,
                'a': element('a', 0, 0, 100, 100, inside % 'a'),
                'b': element('b', 10, 10, 80, 80, inside % 'b')}
    cases.append(case('same-container-containment-64pct-area',
                      '同级 80x80 完全落在 100x100 内（面积 64%）：可见面积 100% 被覆盖 → fail',
                      'fail', elements, 'a', 'b', 1.0))
    elements = {'list': viewport,
                'a': element('a', 0, 0, 100, 100, inside % 'a'),
                'b': element('b', 27.65, 27.65, 44.7, 44.7, inside % 'b')}
    cases.append(case('same-container-containment-20pct-area',
                      '同级小控件面积约 20% 且完全被覆盖 → 仍 fail',
                      'fail', elements, 'a', 'b', 1.0))

    # 8. The only sanctioned exception: the semantic path proves real ancestry.
    elements = {'outer': element('outer', 0, 0, 100, 100, plain % 'outer'),
                'inner': element('inner', 10, 10, 20, 20, plain % 'outer' + '>Other>Button[inner]')}
    cases.append(case('path-proven-ancestor',
                      '语义路径证明父子关系（路径前缀）才豁免嵌套遮挡',
                      'none', elements, 'outer', 'inner'))

    # 9-11. Different scroll containers.
    elements = {'va': element('va', 0, 0, 300, 300, 'Application>Window>ScrollView[va]', role='ScrollView'),
                'vb': element('vb', 0, 0, 300, 300, 'Application>Window>ScrollView[vb]', role='ScrollView'),
                'a': element('a', 20, 20, 40, 40, 'Application>Window>ScrollView[va]>Button[a]'),
                'b': element('b', 0, 0, 100, 100, 'Application>Window>ScrollView[vb]>Button[b]')}
    cases.append(case('different-scroll-containers-full-containment',
                      '不同滚动容器里小控件被大控件完全覆盖（可见）→ fail',
                      'fail', elements, 'a', 'b', 1.0))
    elements = {'va': element('va', 0, 0, 300, 300, 'Application>Window>ScrollView[va]', role='ScrollView'),
                'vb': element('vb', 0, 80, 300, 320, 'Application>Window>ScrollView[vb]', role='ScrollView'),
                'a': element('a', 0, 100, 100, 50, 'Application>Window>ScrollView[va]>Button[a]'),
                'b': element('b', 20, 110, 100, 50, 'Application>Window>ScrollView[vb]>Button[b]')}
    cases.append(case('different-scroll-containers-visible',
                      '两个不同滚动容器的可见部分重叠 64%',
                      'fail', elements, 'a', 'b', 0.64))
    elements = {'va': element('va', 0, 0, 300, 50, 'Application>Window>ScrollView[va]', role='ScrollView'),
                'a': element('a', 0, 100, 100, 50, 'Application>Window>ScrollView[va]>Button[a]'),
                'b': element('b', 0, 120, 100, 40, plain % 'b')}
    cases.append(case('different-scroll-containers-clipped',
                      '滚动内容完全在视口外，与外部按钮不构成遮挡',
                      'excluded', elements, 'a', 'b'))

    # 12-13. Scroll content against an external control.
    elements = {'list': element('list2', -2.5, 165, 380, 15, 'Application>Window>ScrollView[list2]', role='ScrollView'),
                'book': element('book', 13.5, 165, 348, 142,
                                'Application>Window>ScrollView[list2]>Other>Button[book]'),
                'import': element('import', -1.5, 188, 176, 77.5, plain % 'import')}
    cases.append(case('scroll-content-outside-viewport',
                      '滚动内容在 15 pt 视口之外，与外部按钮几何重叠但不遮挡',
                      'excluded', elements, 'book', 'import'))
    elements = {'list2': element('list2', 0, 100, 300, 100, 'Application>Window>ScrollView[list2]', role='ScrollView'),
                'a': element('a', 0, 150, 100, 40, 'Application>Window>ScrollView[list2]>Button[a]'),
                'b': element('b', 50, 155, 40, 40, plain % 'b')}
    cases.append(case('scroll-content-visible-overlap',
                      '滚动内容的可见部分与外部按钮重叠 87.5%',
                      'fail', elements, 'a', 'b', 0.875))

    # 14. Nested scroll views: the nearest recorded viewport decides.
    elements = {'outer': element('outer', 0, 0, 300, 400, 'Application>Window>ScrollView[outer]', role='ScrollView'),
                'inner': element('inner', 0, 200, 300, 40,
                                 'Application>Window>ScrollView[outer]>Other>ScrollView[inner]', role='ScrollView'),
                'a': element('a', 0, 210, 100, 40,
                             'Application>Window>ScrollView[outer]>Other>ScrollView[inner]>Button[a]'),
                'b': element('b', 0, 220, 100, 40, plain % 'b')}
    cases.append(case('nested-scroll-nearest-ancestor',
                      '嵌套滚动按最近视口裁剪（66.7%，不是外层的 75%）',
                      'fail', elements, 'a', 'b', 0.6667))

    # 15-17. Cannot prove where the visible area is: never claim visible occlusion.
    elements = {'a': element('a', 0, 0, 100, 100, 'Application>Window>ScrollView>Button[a]'),
                'b': element('b', 30, 0, 100, 100, 'Application>Window>ScrollView>Button[b]')}
    cases.append(case('bare-scroll-siblings-unknown-viewport',
                      '无标识滚动容器内的同级控件：视口不可证 → uncovered，不看 raw 几何',
                      'undetermined', elements, 'a', 'b'))
    elements = {'a': element('a', 0, 0, 100, 100, 'Application>Window>ScrollView>Other>Other>Button[a]'),
                'b': element('b', 30, 0, 100, 100, 'Application>Window>ScrollView>Other>Button[b]')}
    cases.append(case('bare-scroll-different-depth',
                      '同一无标识滚动容器但层级不同 → uncovered',
                      'undetermined', elements, 'a', 'b'))
    elements = {'a': element('a', 0, 0, 100, 100, 'Application>Window>ScrollView[ghost]>Button[a]'),
                'b': element('b', 30, 0, 100, 100, plain % 'b')}
    cases.append(case('missing-scroll-viewport',
                      '滚动视口未记录 → uncovered，不声称已被裁剪',
                      'undetermined', elements, 'a', 'b'))

    # 18-19. No scroll container at all: laid-out boxes, unchanged threshold.
    elements = {'a': element('a', 0, 0, 100, 100, plain % 'a'),
                'b': element('b', 0, 0, 100, 100, plain % 'b')}
    cases.append(case('plain-no-scroll-overlap', '无滚动容器时 100% 重叠仍判遮挡',
                      'fail', elements, 'a', 'b', 1.0))
    elements = {'a': element('a', 0, 0, 100, 100, plain % 'a'),
                'b': element('b', 10, 10, 80, 80, plain % 'b')}
    cases.append(case('plain-no-scroll-containment',
                      '无滚动容器时同级完全包含（面积 64%）仍判遮挡',
                      'fail', elements, 'a', 'b', 1.0))

    return cases, elements


def original_run_replay():
    """Frames recorded by run 40085956514 (source 29f03e23), state library.large_type
    on iPhone SE (3rd generation): library.list viewport y=165 h=15, library.book.0
    y=165 h=142, library.import.epub y=188 h=77.5. The first classification called
    this pair a 91% blocking overlap; clipping by the recorded viewport shows the
    visible parts never meet."""
    viewport = element('library.list', -2.5, 165, 380, 15,
                       'Application>Window>Other>ScrollView[library.list]', role='ScrollView')
    elements = {'library.list': viewport,
                'library.book.0': element('library.book.0', 13.5, 165, 348, 142,
                                          'Application>Window>ScrollView[library.list]>Other>Button[library.book.0]'),
                'library.import.epub': element('library.import.epub', -1.5, 188, 176, 77.5,
                                               'Application>Window>Button[library.import.epub]')}
    first = elements['library.book.0']
    second = elements['library.import.epub']
    return {'elements': elements, 'first': first, 'second': second,
            'outcome': classify_overlap(first, second, elements, 0.5),
            'legacy': legacy_v1_verdict(first, second)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--contract', type=Path,
                        default=Path(__file__).absolute().parent/'a11y_contract.json')
    args = parser.parse_args()

    contract = json.loads(args.contract.read_text(encoding='utf-8'))
    policy = contract.get('policy') or {}
    targets = policy.get('minimum_target_pt') or {}
    expected_policy = {
        'minimum_target_pt.blocking': targets.get('blocking'),
        'minimum_target_pt.advisory_ios': targets.get('advisory_ios'),
        'minimum_target_pt.advisory_macos': targets.get('advisory_macos'),
        'overlap_threshold': policy.get('overlap_threshold'),
        'clip_tolerance_pt': policy.get('clip_tolerance_pt'),
        'reading_order_tolerance_pt': policy.get('reading_order_tolerance_pt'),
    }
    required_policy = {'minimum_target_pt.blocking': 24,
                       'minimum_target_pt.advisory_ios': 44,
                       'minimum_target_pt.advisory_macos': 20,
                       'overlap_threshold': 0.5,
                       'clip_tolerance_pt': 2,
                       'reading_order_tolerance_pt': 20}
    policy_ok = all(expected_policy.get(key) == value for key, value in required_policy.items())

    cases, _ = build_cases()
    results = []
    for case in cases:
        outcome = case['outcome']
        passed = outcome['verdict'] == case['expected']
        if passed and case['threshold_ratio'] is not None:
            ratio = outcome['visible_ratio'] if outcome['same_container'] is False else outcome['raw_ratio']
            passed = assert_ratio(case, ratio, case['threshold_ratio'])
        results.append({'id': case['id'], 'description': case['description'],
                        'expected': case['expected'], 'observed': outcome['verdict'],
                        'same_container': outcome['same_container'],
                        'raw_ratio': round(outcome['raw_ratio'], 4),
                        'visible_ratio': round(outcome['visible_ratio'], 4),
                        'detail': outcome['detail'], 'passed': passed})

    replay = original_run_replay()
    replay_passed = (replay['outcome']['verdict'] == 'excluded'
                     and replay['outcome']['raw_ratio'] > 0.5
                     and replay['legacy'] == 'skipped')
    results.append({'id': 'original-run-replay-29f03e23',
                    'description': '原 run 40085956514 的误判对：v1 直接 skip，v2 用已记录视口证明可视部分不相交',
                    'expected': 'excluded', 'observed': replay['outcome']['verdict'],
                    'same_container': replay['outcome']['same_container'],
                    'raw_ratio': round(replay['outcome']['raw_ratio'], 4),
                    'visible_ratio': round(replay['outcome']['visible_ratio'], 4),
                    'legacy_v1': replay['legacy'],
                    'detail': replay['outcome']['detail'], 'passed': replay_passed})

    results.append({'id': 'policy-thresholds-unchanged',
                    'description': '24/44/20 pt、50% 重叠、2 pt 容差、20 pt 顺序容差保持不变',
                    'expected': 'unchanged', 'observed': 'unchanged' if policy_ok else 'changed',
                    'detail': json.dumps(expected_policy, sort_keys=True), 'passed': policy_ok})

    failed = [item['id'] for item in results if not item['passed']]
    report = {'schema': 1, 'judge': 'overlap classifier',
              'source_sha': os.environ.get('GITHUB_SHA', ''),
              'contract': str(args.contract.absolute()),
              'policy': expected_policy,
              'legacy_v1_gap': {'case': 'original-run-replay-29f03e23',
                                'legacy_verdict': replay['legacy'],
                                'current_verdict': replay['outcome']['verdict'],
                                'raw_ratio': round(replay['outcome']['raw_ratio'], 4),
                                'visible_ratio': round(replay['outcome']['visible_ratio'], 4)},
              'cases': results, 'failed': failed, 'passed': not failed}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'cases': len(results), 'failed': failed,
                      'legacy_v1_gap': report['legacy_v1_gap']}, sort_keys=True))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
