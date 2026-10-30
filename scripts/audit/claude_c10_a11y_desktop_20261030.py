#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""C10 desktop accessibility: owner guard and strict evidence aggregation.

  guard      the checked-out source is the pinned base plus only C10-owned paths
  aggregate  GTK + Windows audit reports + exit probes -> one six-surface report
  selftest   exercise the verdict rules with synthetic reports

Three separate verdicts are kept apart and never merged:
  tree      accessible name/role/state/focus-order checks read from the tree
  operable  a keyboard action was performed and its effect observed
  screen_reader   always "pending": no actual screen reader runs in these jobs
A surface passes only when tree AND operable pass; control existence alone never
makes a surface operable.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/reader_final_a11y_desktop_20261030'))
import surfaces  # noqa: E402

BASE = '343bb94eb6513beaf5b344e7828342f6602a3b7b'
OWNED = (r'^tests/reader_final_a11y_desktop_20261030/', r'^\.github/workflows/claude_c10_a11y_desktop_20261030\.yml$',
         r'^scripts/audit/claude_c10_a11y_desktop_20261030\.py$',
         r'^docs/reader-total-progress/CLAUDE_C10_A11Y_DESKTOP_20261030\.md$')
SCREEN_READER = {'status': 'pending',
                 'reason': 'No actual screen reader (Orca, NVDA, Narrator) was run; the accessibility '
                           'tree is read through AT-SPI / UI Automation, which is not speech output.'}


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def guard(args):
    head = git('rev-parse', 'HEAD').strip()
    if os.environ.get('GITHUB_SHA') and os.environ['GITHUB_SHA'] != head:
        raise SystemExit('checked-out HEAD %s is not GITHUB_SHA' % head)
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, head], cwd=ROOT, check=True)
    changed = [line for line in git('diff', '--name-only', BASE, head).splitlines() if line]
    foreign = [p for p in changed if not any(re.match(rule, p) for rule in OWNED)]
    report = {'base': BASE, 'head': head, 'changed': changed, 'foreign': foreign,
              'run': os.environ.get('GITHUB_RUN_ID'), 'attempt': os.environ.get('GITHUB_RUN_ATTEMPT')}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    if foreign:
        raise SystemExit('paths outside C10 ownership changed: %s' % foreign)


def status_of(entry):
    if entry is None:
        return 'missing'
    if 'status' in entry:
        return entry['status']
    if entry.get('evaluated') is False:
        return 'error'
    return 'pass' if entry.get('pass') else 'fail'


def key_of(entry):
    return entry.get('id') or entry.get('name')


def load_checks(path):
    if not path or not Path(path).is_file():
        return {}
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    return {key_of(item): item for item in data.get('checks', [])}


def judge(platform, checks):
    """checks: id -> raw entry. Returns {surface: verdict} for the six surfaces."""
    table = surfaces.GTK if platform == 'gtk' else surfaces.WINDOWS
    result = {}
    for surface in surfaces.SURFACES:
        rows = [(cid, kind) for cid, (s, kind) in table.items() if s == surface]
        cells = [{'id': cid, 'kind': kind, 'status': status_of(checks.get(cid)),
                  'severity': (checks.get(cid) or {}).get('severity'),
                  'expected': (checks.get(cid) or {}).get('expected'),
                  'actual': (checks.get(cid) or {}).get('actual')} for cid, kind in rows]
        seen = [c for c in cells if c['status'] != 'missing']
        tree = [c for c in seen if c['kind'] != 'operate']
        operate = [c for c in seen if c['kind'] == 'operate']
        if any(c['status'] in ('fail',) for c in tree):
            tree_verdict = 'fail'
        elif not tree or any(c['status'] != 'pass' for c in tree) or len(tree) < len([c for c in cells if c['kind'] != 'operate']):
            tree_verdict = 'incomplete'
        else:
            tree_verdict = 'pass'
        if any(c['status'] == 'fail' for c in operate):
            operable = 'fail'
        elif operate and all(c['status'] == 'pass' for c in operate) and len(operate) == len([c for c in cells if c['kind'] == 'operate']):
            operable = 'pass'
        elif not operate:
            operable = 'unproven'  # controls were observed but no action was performed
        else:
            operable = 'incomplete'
        verdict = 'pass' if tree_verdict == 'pass' and operable == 'pass' else (
            'fail' if 'fail' in (tree_verdict, operable) else 'incomplete')
        result[surface] = {'tree': tree_verdict, 'operable': operable, 'verdict': verdict,
                           'screen_reader': SCREEN_READER['status'], 'checks': cells}
    return result


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def inventory(folder):
    folder = Path(folder)
    files = [p for p in folder.rglob('*') if p.is_file()] if folder.is_dir() else []
    pick = lambda pattern: [p for p in files if re.search(pattern, p.name, re.I)]
    groups = {'screenshots': pick(r'\.png$'), 'key_logs': pick(r'^keys.*\.log$|key-trace.*\.jsonl$'),
              'accessibility_trees': [p for p in files if re.search(r'tree|uia|atspi', str(p.relative_to(folder)), re.I)
                                      and p.suffix in ('.json', '.txt', '.xml')],
              'interaction_logs': pick(r'application\.log$|host-stdout\.log$|audit\.log$')}
    return {name: [{'path': str(p.relative_to(folder)), 'sha256': sha256(p), 'bytes': p.stat().st_size}
                   for p in sorted(items)] for name, items in groups.items()}


def focus_order_gtk(folder):
    order = []
    for path in Path(folder).rglob('keys*.log'):
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            parts = line.split('\t')
            if len(parts) == 4 and parts[2] in ('Tab', 'ISO_Left_Tab', 'shift+Tab') and parts[3] and (not order or order[-1] != parts[3]):
                order.append(parts[3])
    return order


def focus_order_windows(folder):
    order = []
    for path in Path(folder).rglob('*key-trace*.jsonl'):
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            payload = event.get('payload', {})
            if event.get('kind') == 'key' and payload.get('key') in ('tab', 'Tab') and payload.get('focus_after') is not None:
                focus = str(payload['focus_after'])
                if not order or order[-1] != focus:
                    order.append(focus)
    return order


def aggregate(args):
    platforms = {}
    for platform, folder, main in (('gtk', args.gtk, 'result.json'), ('windows', args.windows, 'report.json')):
        folder = Path(folder) if folder else None
        checks = {}
        for source in (main, 'exit-%s.json' % platform):
            hits = list(folder.rglob(source)) if folder and folder.is_dir() else []
            for hit in hits:
                checks.update(load_checks(hit))
        finder = focus_order_gtk if platform == 'gtk' else focus_order_windows
        platforms[platform] = {'artifact_folder': str(folder) if folder else None,
                               'surfaces': judge(platform, checks),
                               'focus_order': finder(folder) if folder and folder.is_dir() else [],
                               'evidence': inventory(folder) if folder else {}}
    cells = [(p, s, v['verdict']) for p, d in platforms.items() for s, v in d['surfaces'].items()]
    accepted = all(v == 'pass' for _, _, v in cells)
    report = {'source_sha': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
              'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
              'tree_and_keyboard_accepted': accepted,
              'screen_reader': SCREEN_READER, 'platforms': platforms,
              'summary': {'%s/%s' % (p, s): v for p, s, v in cells}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    lines = ['## C10 desktop accessibility (GTK + Windows)', '', 'Screen reader: **pending** (not tested, never claimed).', '',
             '| platform | surface | tree | operable | verdict |', '| --- | --- | --- | --- | --- |']
    for p, d in platforms.items():
        for s, v in d['surfaces'].items():
            lines.append('| %s | %s | %s | %s | %s |' % (p, s, v['tree'], v['operable'], v['verdict']))
    lines += ['', 'tree_and_keyboard_accepted: %s' % accepted]
    text = '\n'.join(lines) + '\n'
    print(text)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        Path(os.environ['GITHUB_STEP_SUMMARY']).write_text(text, encoding='utf-8')
    # The aggregate job succeeds when evidence was assembled; acceptance is the report field.
    if args.require_accepted and not accepted:
        raise SystemExit(1)


def selftest(_):
    def gtk_all(status):
        return {cid: {'name': cid, 'pass': status == 'pass'} for cid in surfaces.GTK}
    good = judge('gtk', gtk_all('pass'))
    for surface, v in good.items():
        has_action = any(s == surface and k == 'operate' for s, k in surfaces.GTK.values())
        # GTK reading/annotation have no keyboard-action check: tree-only evidence stays unproven
        assert v['verdict'] == ('pass' if has_action else 'incomplete') and             v['operable'] == ('pass' if has_action else 'unproven'), (surface, v)
    # existence-only evidence: drop every operate check, tree passes yet nothing is operable
    existence = {cid: e for cid, e in gtk_all('pass').items() if surfaces.GTK[cid][1] != 'operate'}
    for surface, v in judge('gtk', existence).items():
        assert v['operable'] == 'unproven' and v['verdict'] != 'pass', (surface, v)
    # one failed operate check fails its surface only
    broken = gtk_all('pass')
    broken['import_books_visible_on_shelf']['pass'] = False
    result = judge('gtk', broken)
    assert result['import']['verdict'] == 'fail' and result['settings']['verdict'] == 'pass'
    # a missing exit probe leaves the exit surface incomplete, never passing
    no_exit = {cid: e for cid, e in gtk_all('pass').items() if surfaces.GTK[cid][0] != 'exit'}
    assert judge('gtk', no_exit)['exit']['verdict'] != 'pass'
    # windows: not_verified is not a pass
    win = {cid: {'id': cid, 'status': 'pass'} for cid in surfaces.WINDOWS}
    win['EXIT-02']['status'] = 'not_verified'
    assert judge('windows', win)['exit']['verdict'] != 'pass'
    assert all(v['screen_reader'] == 'pending' for v in good.values())
    print('selftest ok')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    g = sub.add_parser('guard')
    g.add_argument('--report', type=Path, default=Path('build/c10/source-guard.json'))
    g.set_defaults(run=guard)
    a = sub.add_parser('aggregate')
    a.add_argument('--gtk', type=Path)
    a.add_argument('--windows', type=Path)
    a.add_argument('--output', type=Path, default=Path('build/c10/final-report.json'))
    a.add_argument('--require-accepted', action='store_true')
    a.set_defaults(run=aggregate)
    s = sub.add_parser('selftest')
    s.set_defaults(run=selftest)
    parsed = parser.parse_args()
    parsed.run(parsed)
