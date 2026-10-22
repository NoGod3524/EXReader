#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only H8 acceptance using the normal distributed Win32 binary."""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
import sqlite3
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
SDK_CANDIDATE = '2f26847684b54006ca812c35477ceae43719e7d4'
sys.path.insert(0, str(ROOT / 'tools'))
import check_windows_host as base


def epub(path, missing=False):
    container = ('<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
                 '<rootfiles><rootfile full-path="OPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
    opf = ('<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
           '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">urn:r5:h8</dc:identifier>'
           '<dc:title>'+('H8 Missing Chapter' if missing else 'H8 Bounded')+'</dc:title></metadata>'
           '<manifest><item id="a" href="a.xhtml" media-type="application/xhtml+xml"/>'
           '<item id="b" href="b.xhtml" media-type="application/xhtml+xml"/>'
           '<item id="long" href="long.xhtml" media-type="application/xhtml+xml"/></manifest>'
           '<spine><itemref idref="a"/><itemref idref="b"/><itemref idref="long"/><itemref idref="a"/></spine></package>')
    alpha = '<p>ALPHA chapter zero. Native bounded reading keeps exact UTF-8 positions: 中文 é 😀.</p>'
    beta = '<p>BETA chapter one. A short independent route for a saved annotation and navigation.</p>'
    long = ''.join('<p>Long chapter row %05d. Native pages keep only a bounded window. '
                   'Unicode 中文 é 😀 and unique tail token %05d.</p>' % (i, i) for i in range(6000))
    def body(text):
        return '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>H8</title></head><body>'+text+'</body></html>'
    with zipfile.ZipFile(path, 'w') as archive:
        for name, data in [('mimetype', 'application/epub+zip'), ('META-INF/container.xml', container),
                           ('OPS/package.opf', opf), ('OPS/a.xhtml', body(alpha)),
                           *([] if missing else [('OPS/b.xhtml', body(beta))]), ('OPS/long.xhtml', body(long))]:
            item = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_STORED if name == 'mimetype' else zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, data.encode('utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=Path, required=True)
    args = parser.parse_args()
    package, output = args.package.resolve(), args.output.resolve()
    base.require(not output.exists(), 'use a fresh H8 evidence directory')
    output.mkdir(parents=True)
    exe = package / 'EXReader.exe'
    book, missing = output / 'H8-Bounded.epub', output / 'H8-Missing.epub'
    epub(book); epub(missing, missing=True)
    repeated = output / 'H8-Repeated.epub'; epub(repeated)
    base.require(book.read_bytes() == repeated.read_bytes(), 'fixture generation is not byte-stable')
    repeated.unlink()
    source = base.source_identity()
    files = [exe, package / 'Reader.otf', package / 'Sample.epub', package / 'Sample-positive.epub', args.seed.resolve(), book, missing]
    files += [p for p in package.iterdir() if p.suffix == '.dll']
    identities = {str(p): base.digest(p) for p in files}
    checks, records, sdk_trees = [], {}, {}

    def require(condition, name):
        checks.append({'name': name, 'passed': bool(condition)})
        base.require(condition, name)

    def run(group, phase, actions, data):
        root = output / group; root.mkdir(exist_ok=True)
        plan = [{'index': i + 1, 'action': line.split('|')[0], 'parameters': line.split('|')[1:]}
                for i, line in enumerate(actions)]
        script = root / (phase + '.script'); script.write_text('\n'.join(actions)+'\n', encoding='utf-8')
        script_hash = base.digest(script)
        require(all(base.digest(Path(p)) == sha for p, sha in identities.items()), group+'/'+phase+'/sealed-inputs')
        code, elapsed, pid = base.run_phase(exe, script, root, phase, data, package, 600)
        base.EXPECTED_SHOTS[phase] = {x['parameters'][0] for x in plan if x['action'] == 'snapshot'}
        try:
            parsed = base.parse_log(root / phase / 'drive.log', plan, phase, '3.40.0', pid)
        except ValueError:
            for raw in (root / phase / 'drive.log').read_text(encoding='utf-8', errors='replace').splitlines():
                if '\tFAIL\t' in raw or raw.startswith('STATE\t'):
                    print('H8-REJECTED-DIAGNOSTIC '+group+'/'+phase+' '+raw, flush=True)
            raise
        steps, states, shelf, notes, shots, done, host = parsed
        require(code == 0 and len(steps) == len(plan) and bool(done), group+'/'+phase+'/complete-actions')
        require(base.digest(script) == script_hash, group+'/'+phase+'/sealed-script')
        for name, shot in shots.items():
            shot.update(base.png_identity(root / phase / (name+'.png')))
        result = {'exit_code': code, 'elapsed_seconds': elapsed, 'pid': pid, 'plan': plan, 'steps': steps,
                  'states': states, 'notes': notes, 'shelf': shelf, 'screenshots': shots, 'host': host}
        records[group+'/'+phase] = result
        return result

    error = None
    try:
        ancestry = subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', SDK_CANDIDATE, source], check=False)
        require(ancestry.returncode == 0, 'SDK-candidate-is-source-ancestor')
        for path in ('src', 'include', 'cmake', 'CMakeLists.txt', 'tests/fixtures',
                     '.github/workflows/native.yml', '.github/workflows/reliability.yml', 'bindings'):
            baseline = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', SDK_CANDIDATE+':'+path], text=True).strip()
            current = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', source+':'+path], text=True).strip()
            sdk_trees[path] = {'candidate': baseline, 'host': current}
            require(baseline == current, 'unchanged-SDK-tree/'+path)
        data = output / 'profile'; data.mkdir()
        a = run('pilot', 'A', [
            'import|'+str(book), 'open|H8 Bounded', 'check|bounded|1', 'check|part|0', 'state|alpha',
            'select_all', 'copy', 'check|clipboard|contains|ALPHA', 'next', 'check|part|1', 'check|page|1',
            'prev', 'check|part|0', 'next', 'check|part|1', 'select_all', 'note|Cross-part note', 'add_note',
            'check|notes|1', 'state|beta_note', 'next', 'check|part|2', 'state|long_start',
            'next', 'next', 'next', 'state|long_before_font', 'font_inc', 'font_dec', 'check|part|2',
            'state|long_after_font', 'chapter_end', 'state|long_tail', 'snapshot|h8-long-tail',
            'next', 'check|part|3', 'check|page|1', 'state|duplicate_route',
            'select_all', 'note|Duplicate-route note', 'add_note', 'check|notes|2',
            'jump_note|0', 'check|part|1', 'check|selection|nonempty', 'state|cross_part_jump',
            'jump_note|1', 'check|part|3', 'check|selection|nonempty', 'copy', 'check|clipboard|contains|ALPHA',
            'state|before_restart', 'snapshot|h8-duplicate-route', 'quit'], data)
        rejection_profiles = {}
        for kind in ('missing-note', 'ambiguous-note', 'missing-progress', 'ambiguous-progress'):
            rejected = output / (kind+'-profile'); shutil.copytree(data, rejected)
            with sqlite3.connect(rejected/'library.sqlite') as database:
                book_id = database.execute('SELECT id FROM books').fetchone()[0]
                if kind.endswith('note'):
                    if kind.startswith('missing'):
                        database.execute("UPDATE epub_notes SET start=0,end=11,exact='never-found',prefix='unseen',suffix='unseen' WHERE part=1")
                    else:
                        database.execute("UPDATE epub_notes SET part=2,path='OPS/long.xhtml',chapter='OPS/long.xhtml',"
                                         "start=0,end=12,exact='Native pages',prefix=' ',suffix=' ' WHERE part=1")
                else:
                    prefix, suffix = ('unseen', 'unseen') if kind.startswith('missing') else ('Native ', 'pages')
                    database.execute('UPDATE epub_progress SET part=2,path=?,chapter=?,position=1,prefix=?,suffix=? WHERE book_id=?',
                                     ('OPS/long.xhtml', 'OPS/long.xhtml', prefix, suffix, book_id))
            rejection_profiles[kind] = rejected
        b = run('pilot', 'B', [
            'wait_idle', 'check|bounded|1', 'check|part|3', 'check|notes|2', 'state|restored',
            'note_select|1', 'note|Route updated', 'update_note', 'wait_idle', 'state|updated', 'delete_note', 'check|notes|1',
            'prev', 'check|part|2', 'state|previous_chapter_tail', 'chapter_home', 'check|page|1',
            'next', 'next', 'state|before_long_restart', 'quit'], data)
        c = run('pilot', 'C', [
            'wait_idle', 'check|bounded|1', 'check|part|2', 'check|notes|1', 'state|long_restored',
            'jump_note|0', 'check|part|1', 'check|selection|nonempty', 'delete_note', 'check|notes|0',
            'import|'+str(missing), 'open|H8 Missing Chapter', 'check|part|0', 'state|before_bad_chapter',
            'next', 'check|status|contains|失败', 'check|part|0', 'state|after_bad_chapter', 'quit'], data)
        for result in (a, b, c):
            for name, state in result['states'].items():
                require(state.get('bounded') == '1' and state.get('explicit_snapshot_bytes') == '0' and
                        0 < int(state['owned_frame_text_geometry_bytes']) <= 16 * 1024 * 1024 and
                        int(state['peak_parse_workspace_bytes']) <= 8 * 1024 * 1024,
                        'bounded-owned-frame/'+name)
        alpha, duplicate = a['states']['alpha'], a['states']['duplicate_route']
        require(alpha['part_path'] == duplicate['part_path'] and alpha['part'] != duplicate['part'] and
                alpha['page_text_fnv'] == duplicate['page_text_fnv'], 'duplicate-path-distinct-part-same-content')
        tail = a['states']['long_tail']
        require(int(tail['windows_loaded']) > 1 and int(tail['windows_evicted']) > 0 and
                int(tail['projection_bytes']) > 512 * 1024 and int(tail['page']) > 20, 'long-chapter-window-eviction')
        require(a['states']['before_restart']['part'] == b['states']['restored']['part'] == '3' and
                a['notes']['before_restart'] == b['notes']['restored'], 'route-and-notes-survive-process-restart')
        require(b['notes']['updated'][1]['comment'] == 'Route updated', 'comment-update-preserves-route')
        before, restored = b['states']['before_long_restart'], c['states']['long_restored']
        require(all(before[k] == restored[k] for k in ('book_id', 'part', 'part_path', 'offset', 'page_text_fnv')),
                'long-chapter-point-restores-identical-page')
        bad_before, bad_after = c['states']['before_bad_chapter'], c['states']['after_bad_chapter']
        require(all(bad_before[k] == bad_after[k] for k in ('book_id', 'part', 'part_path', 'offset', 'page_text_fnv')),
                'missing-chapter-is-error-keeps-accepted-frame')
        with sqlite3.connect(data / 'library.sqlite') as database:
            require(database.execute('PRAGMA user_version').fetchone()[0] == 7, 'bounded-schema-seven')
            require(database.execute('SELECT count(*) FROM notes').fetchone()[0] == 0 and
                    database.execute('SELECT count(*) FROM epub_notes').fetchone()[0] == 0,
                    'chapter-notes-crud-never-writes-global-notes')
        for kind, rejected in rejection_profiles.items():
            expected = '未匹配' if kind.startswith('missing') else '歧义'
            with sqlite3.connect(rejected/'library.sqlite') as database:
                before_rows = database.execute('SELECT * FROM '+('epub_notes' if kind.endswith('note') else 'epub_progress')+' ORDER BY 1').fetchall()
            actions = ['wait_idle', 'state|before']
            if kind.endswith('note'):
                actions += ['check|part|3', 'jump_note|0', 'check|status|contains|'+expected, 'check|part|3', 'state|after']
            else:
                actions += ['check|status|contains|'+expected, 'state|after']
            observed = run(kind, 'A', actions+['quit'], rejected)
            before_state, after_state = observed['states']['before'], observed['states']['after']
            if kind.endswith('note'):
                require(all(before_state[k] == after_state[k] for k in ('book_id', 'part', 'page_text_fnv', 'offset')),
                        kind+'/rejected-with-accepted-frame-retained')
            else:
                require(after_state['book_id'] != '0' and after_state['part'] == '2' and
                        after_state.get('progress_record_preserved') == '1' and
                        '回退恢复（未精确锚定）' in after_state['status'], kind+'/explicit-numeric-fallback-without-exact-claim')
            with sqlite3.connect(rejected/'library.sqlite') as database:
                after_rows = database.execute('SELECT * FROM '+('epub_notes' if kind.endswith('note') else 'epub_progress')+' ORDER BY 1').fetchall()
            require(before_rows == after_rows, kind+'/original-records-retained')
        repeat_profile = output / 'repeated-profile'; repeat_profile.mkdir()
        repeated_a = run('original-repeated', 'A', [
            'import|'+str(package/'Sample.epub'), 'open|EXReader benchmark', 'check|bounded|1',
            'next', 'select_all', 'note|Repeated quote negative', 'add_note', 'check|notes|1',
            'prev', 'state|before_ambiguous_note', 'jump_note|0', 'check|status|contains|歧义',
            'state|after_ambiguous_note', 'next', 'next', 'state|before_restart', 'quit'], repeat_profile)
        refused_before = repeated_a['states']['before_ambiguous_note']
        refused_after = repeated_a['states']['after_ambiguous_note']
        require(all(refused_before[k] == refused_after[k] for k in ('book_id', 'part', 'page', 'offset', 'page_text_fnv')) and
                refused_after['selection_active'] == '0', 'original-repeated-quote-rejected-without-navigation')
        with sqlite3.connect(repeat_profile/'library.sqlite') as database:
            repeat_progress = database.execute('SELECT * FROM epub_progress').fetchall()
        repeated_b = run('original-repeated', 'B', [
            'wait_idle', 'check|bounded|1', 'check|notes|1', 'check|status|contains|回退', 'state|fallback_restored', 'quit'], repeat_profile)
        repeated_restored = repeated_b['states']['fallback_restored']
        require(all(repeated_a['states']['before_restart'][k] == repeated_restored[k]
                    for k in ('book_id', 'part', 'page', 'offset', 'page_text_fnv')) and
                repeated_restored['progress_record_preserved'] == '1', 'original-repeated-progress-explicit-fallback')
        with sqlite3.connect(repeat_profile/'library.sqlite') as database:
            require(database.execute('SELECT * FROM epub_progress').fetchall() == repeat_progress and
                    database.execute('SELECT count(*) FROM epub_notes').fetchone()[0] == 1,
                    'original-repeated-selector-records-retained')
        legacy = output / 'legacy-profile'; legacy.mkdir()
        subprocess.run([str(args.seed.resolve()), str(legacy/'library.sqlite'), str(package/'Sample.epub')], check=True, timeout=30)
        la = run('legacy', 'A', ['import|'+str(package/'Sample.epub'), 'check|shelf|count|1',
            'open|Legacy memory import', 'check|bounded|0', 'next', 'select_all', 'note|Legacy note', 'add_note',
            'check|notes|1', 'state|legacy_saved', 'quit'], legacy)
        lb = run('legacy', 'B', ['wait_idle', 'check|bounded|0', 'check|notes|1', 'state|legacy_restored', 'quit'], legacy)
        require(all(la['states']['legacy_saved'][k] == lb['states']['legacy_restored'][k]
                    for k in ('book_id', 'offset', 'page_text_fnv')), 'legacy-progress-notes-remain-global')
        with sqlite3.connect(legacy/'library.sqlite') as database:
            require(database.execute('SELECT count(*) FROM epub_bounded_books').fetchone()[0] == 0 and
                    database.execute('SELECT count(*) FROM notes').fetchone()[0] == 1 and
                    database.execute('SELECT count(*) FROM epub_notes').fetchone()[0] == 0,
                    'dedup-keeps-legacy-storage-mode')
        require(all(base.digest(Path(p)) == sha for p, sha in identities.items()), 'all-sealed-inputs-unchanged')
    except (OSError, ValueError, KeyError, IndexError, sqlite3.Error, subprocess.SubprocessError) as caught:
        error = type(caught).__name__+': '+str(caught)
        for name, result in records.items():
            print('H8-FAILED-CHECK-STATE '+json.dumps({'run': name,
                'states': {key: {field: value for field, value in state.items()
                    if field in ('book_id', 'part', 'page', 'offset', 'notes', 'status', 'progress_record_preserved')}
                    for key, state in result['states'].items()},
                'notes': result['notes']}, ensure_ascii=True), flush=True)
    evidence = {'schema': 1, 'source_sha': source, 'sdk_candidate': SDK_CANDIDATE, 'sdk_trees': sdk_trees,
                'run_id': os.environ.get('GITHUB_RUN_ID'), 'accepted': error is None and bool(checks) and all(x['passed'] for x in checks),
                'checks': checks, 'failures': [] if error is None else [error], 'identities': identities, 'runs': records,
                'scope': 'H8 default bounded EPUB Windows pilot; legacy mode and fixed readers retained',
                'complete_product': False, 'performance_budget_accepted': False}
    (output/'h8-evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'accepted': evidence['accepted'], 'checks': len(checks), 'failures': evidence['failures'],
                      'source_sha': source}, ensure_ascii=True), flush=True)
    return 0 if evidence['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
