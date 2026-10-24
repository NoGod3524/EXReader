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
    viewport = element('list', 0, 0, 200, 400, 'Application>Window>ScrollView[list]', role='ScrollView')
    inside = 'Application>Window>ScrollView[list]>Button[%s]'

    # 1. Two controls inside the same scroll view, both fully visible, 79% overlap.
    elements = {'list': viewport,
                'a': element('a', 0, 0, 100, 100, inside % 'a'),
                'b': element('b', 10, 10, 90, 90, inside % 'b')}
    cases.append({'id': 'same-container-visible-overlap',
                  'description': '同一滚动容器内两个可见控件真实重叠 79%',
                  'expected': 'fail', 'threshold_ratio': 0.79,
                  'outcome': classify_overlap(elements['a'], elements['b'], elements, 0.5)})

    # 2. Same container, 20% overlap: below the unchanged threshold.
    elements = {'list': viewport,
                'a': element('a', 0, 0, 100, 100, inside % 'a'),
                'b': element('b', 80, 0, 100, 100, inside % 'b')}
    cases.append({'id': 'same-container-below-threshold',
                  'description': '同一容器内 20% 重叠低于 50% 阈值',
                  'expected': 'none', 'threshold_ratio': 0.20,
                  'outcome': classify_overlap(elements['a'], elements['b'], elements, 0.5)})

    # 3. Threshold edges stay at 50%.
    elements = {'list': viewport,
                'a': element('a', 0, 0, 100, 100, inside % 'a'),
                'b': element('b', 51, 0, 100, 100, inside % 'b')}
    cases.append({'id': 'threshold-49-percent',
                  'description': '同一容器内 49% 重叠仍判通过',
                  'expected': 'none', 'threshold_ratio': 0.49,
                  'outcome': classify_overlap(elements['a'], elements['b'], elements, 0.5)})
    elements = {'list': viewport,
                'a': element('a', 0, 0, 100, 100, inside % 'a'),
                'b': element('b', 49, 0, 100, 100, inside % 'b')}
    cases.append({'id': 'threshold-51-percent',
                  'description': '同一容器内 51% 重叠判遮挡',
                  'expected': 'fail', 'threshold_ratio': 0.51,
                  'outcome': classify_overlap(elements['a'], elements['b'], elements, 0.5)})

    # 4. Containment is not occlusion.
    elements = {'list': viewport,
                'a': element('a', 0, 0, 100, 100, inside % 'a'),
                'b': element('b', 10, 10, 20, 20, inside % 'b')}
    cases.append({'id': 'same-container-containment',
                  'description': '一方布局框包含另一方，不算遮挡',
                  'expected': 'none', 'threshold_ratio': None,
                  'outcome': classify_overlap(elements['a'], elements['b'], elements, 0.5)})

    # 5. Scroll content outside the viewport overlapping an external button.
    viewport = element('list', -2.5, 165, 380, 15, 'Application>Window>ScrollView[list]', role='ScrollView')
    elements = {'list': viewport,
                'book': element('book', 13.5, 165, 348, 142,
                                'Application>Window>ScrollView[list]>Other>Button[book]'),
                'import': element('import', -1.5, 188, 176, 77.5, 'Application>Window>Button[import]')}
    cases.append({'id': 'scroll-content-outside-viewport',
                  'description': '滚动内容在 15 pt 视口之外，与外部按钮几何重叠但不遮挡',
                  'expected': 'excluded', 'threshold_ratio': None,
                  'outcome': classify_overlap(elements['book'], elements['import'], elements, 0.5)})

    # 6. Scroll content whose visible part does overlap an external button.
    viewport = element('list2', 0, 100, 300, 100, 'Application>Window>ScrollView[list2]', role='ScrollView')
    elements = {'list2': viewport,
                'a': element('a', 0, 150, 100, 40, 'Application>Window>ScrollView[list2]>Button[a]'),
                'b': element('b', 50, 155, 40, 40, 'Application>Window>Button[b]')}
    cases.append({'id': 'scroll-content-visible-overlap',
                  'description': '滚动内容的可见部分与外部按钮重叠 87.5%',
                  'expected': 'fail', 'threshold_ratio': 0.875,
                  'outcome': classify_overlap(elements['a'], elements['b'], elements, 0.5)})

    # 7. Two different scroll containers, both visible: still occlusion.
    elements = {'va': element('va', 0, 0, 300, 300, 'Application>Window>ScrollView[va]', role='ScrollView'),
                'vb': element('vb', 0, 80, 300, 320, 'Application>Window>ScrollView[vb]', role='ScrollView'),
                'a': element('a', 0, 100, 100, 50, 'Application>Window>ScrollView[va]>Button[a]'),
                'b': element('b', 20, 110, 100, 50, 'Application>Window>ScrollView[vb]>Button[b]')}
    cases.append({'id': 'different-scroll-containers-visible',
                  'description': '两个不同滚动容器的可见部分重叠 64%',
                  'expected': 'fail', 'threshold_ratio': 0.64,
                  'outcome': classify_overlap(elements['a'], elements['b'], elements, 0.5)})

    # 8. Different scroll containers where one side is clipped away.
    elements = {'va': element('va', 0, 0, 300, 50, 'Application>Window>ScrollView[va]', role='ScrollView'),
                'a': element('a', 0, 100, 100, 50, 'Application>Window>ScrollView[va]>Button[a]'),
                'b': element('b', 0, 120, 100, 40, 'Application>Window>Button[b]')}
    cases.append({'id': 'different-scroll-containers-clipped',
                  'description': '滚动内容完全在视口外，与外部按钮不构成遮挡',
                  'expected': 'excluded', 'threshold_ratio': None,
                  'outcome': classify_overlap(elements['a'], elements['b'], elements, 0.5)})

    # 9. Scroll ancestor without an identifier: undetermined, never 'clipped'.
    elements = {'a': element('a', 0, 100, 100, 50, 'Application>Window>ScrollView>Button[a]'),
                'b': element('b', 0, 120, 100, 40, 'Application>Window>Button[b]')}
    cases.append({'id': 'bare-scroll-ancestor',
                  'description': '滚动祖先没有标识，无法读取视口 → uncovered',
                  'expected': 'undetermined', 'threshold_ratio': None,
                  'outcome': classify_overlap(elements['a'], elements['b'], elements, 0.5)})

    # 10. Identifier names a viewport that the state never recorded.
    elements = {'a': element('a', 0, 100, 100, 50, 'Application>Window>ScrollView[ghost]>Button[a]'),
                'b': element('b', 0, 120, 100, 40, 'Application>Window>Button[b]')}
    cases.append({'id': 'missing-scroll-viewport',
                  'description': '滚动视口未记录 → uncovered，不声称已被裁剪',
                  'expected': 'undetermined', 'threshold_ratio': None,
                  'outcome': classify_overlap(elements['a'], elements['b'], elements, 0.5)})

    # 11. Nested scroll views: the nearest viewport decides.
    elements = {'outer': element('outer', 0, 0, 300, 400, 'Application>Window>ScrollView[outer]', role='ScrollView'),
                'inner': element('inner', 0, 200, 300, 40,
                                 'Application>Window>ScrollView[outer]>Other>ScrollView[inner]', role='ScrollView'),
                'a': element('a', 0, 210, 100, 40,
                             'Application>Window>ScrollView[outer]>Other>ScrollView[inner]>Button[a]'),
                'b': element('b', 0, 220, 100, 40, 'Application>Window>Button[b]')}
    cases.append({'id': 'nested-scroll-nearest-ancestor',
                  'description': '嵌套滚动按最近视口裁剪（66.7%，不是外层的 75%）',
                  'expected': 'fail', 'threshold_ratio': 0.6667,
                  'outcome': classify_overlap(elements['a'], elements['b'], elements, 0.5)})

    # 12. No scroll involvement behaves exactly as before.
    elements = {'a': element('a', 0, 0, 100, 100, 'Application>Window>Button[a]'),
                'b': element('b', 0, 0, 100, 100, 'Application>Window>Button[b]')}
    cases.append({'id': 'plain-no-scroll-overlap',
                  'description': '无滚动容器时 100% 重叠仍判遮挡',
                  'expected': 'fail', 'threshold_ratio': 1.0,
                  'outcome': classify_overlap(elements['a'], elements['b'], elements, 0.5)})

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
