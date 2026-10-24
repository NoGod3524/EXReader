# SPDX-License-Identifier: MIT
"""Actions-only judgment of the installed annotation export.

The oracle is corpus.json written by make_fixtures.py (original wire bytes and the
state each annotation must report). The JSONL is read back by two readers that
share no code with the implementation: Python's json module and a hand-written
unescaper of the documented string encoding. The Markdown is read by a small
structural parser that also proves nothing outside fenced blocks can render as
markup. Databases are compared before and after every export.
"""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import subprocess
import sys
import time

S_OK, S_ARGUMENT, S_MEMORY, S_REVISION, S_DECODE, S_IO, S_LIMIT, S_CANCELLED = range(8)
OWNER = 11
UNICODE_DIR = 'ünï-目录 🙂'


def hexs(s):
    return '-' if s is None else s.encode('utf-8').hex()


def md_norm(s):
    """Independent statement of the documented Markdown text normalization."""
    s = s.replace('\r\n', '\n').replace('\r', '\n')
    out = []
    for ch in s:
        if ch in '\n\t':
            out.append(ch)
        elif ord(ch) < 0x20:
            out.append(chr(0x2400 + ord(ch)))
        elif ch == '\x7f':
            out.append('\u2421')
        else:
            out.append(ch)
    return ''.join(out)


def unescape_md(s):
    return re.sub(r'\\([!-/:-@\[-`{-~])', r'\1', s)


SIMPLE = {0x22: b'"', 0x5c: b'\\', 0x2f: b'/', 0x62: b'\b', 0x66: b'\f', 0x6e: b'\n', 0x72: b'\r', 0x74: b'\t'}


def manual_wires(line):
    """Second reader: decode every "wire" string of one JSONL line by the documented escaping only."""
    marker = b'"wire":"'
    wires = []
    at = 0
    while True:
        found = line.find(marker, at)
        if found < 0:
            return wires
        i = found + len(marker)
        out = bytearray()
        while True:
            b = line[i]
            if b == 0x22:
                break
            if b == 0x5c:
                i += 1
                e = line[i]
                if e in SIMPLE:
                    out += SIMPLE[e]
                    i += 1
                elif e == 0x75:
                    cp = int(line[i + 1:i + 5], 16)
                    i += 5
                    if 0xD800 <= cp < 0xDC00:
                        assert line[i:i + 2] == b'\\u', 'lone high surrogate'
                        lo = int(line[i + 2:i + 6], 16)
                        cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)
                        i += 6
                    out += chr(cp).encode('utf-8')
                else:
                    raise AssertionError('undefined escape')
            else:
                assert b >= 0x20, 'raw control byte inside a JSONL string'
                out.append(b)
                i += 1
        wires.append(bytes(out))
        at = i + 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--probe', required=True, type=Path)
    p.add_argument('--c-consumer', required=True, type=Path)
    p.add_argument('--fixtures', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud only'
    root = a.output.resolve()
    root.mkdir(parents=True)
    probe = str(a.probe.resolve())
    corpus = json.loads((a.fixtures / 'corpus.json').read_text(encoding='utf-8'))
    wires = {w['revision_id']: bytes.fromhex(w['wire_hex']) for w in corpus['wires']}
    books = corpus['books']
    TXT, EPUB, PDF = 'txt:' + 'a' * 64, 'epub:' + 'b' * 64, 'pdf:' + 'c' * 64
    OTHER, MASS, EMPTY, UNKNOWN = 'txt:' + '9' * 64, 'txt:' + 'e' * 64, 'txt:' + 'f' * 64, 'txt:' + '7' * 64
    checks, skipped, cases = [], [], []
    system = platform.system().lower()

    def record(name):
        assert name not in checks, name
        checks.append(name)
        print('PASS ' + name, flush=True)

    def run(args, expect_rc=0):
        done = subprocess.run([probe] + [str(x) for x in args], capture_output=True, text=True, encoding='utf-8', timeout=600)
        assert done.returncode == expect_rc, (args, done.returncode, done.stderr, done.stdout[:500])
        return json.loads(done.stdout)

    def export(db, book, jsonl=None, md=None, title=None, budget=0, extra=()):
        return run(['export', db, book, hexs(title), hexs(str(jsonl) if jsonl else None), hexs(str(md) if md else None), budget, *extra])

    # ---------- the c11 view and the product store accept the corpus ----------
    c = subprocess.run([str(a.c_consumer.resolve())], capture_output=True, text=True, timeout=60)
    assert c.returncode == 0 and c.stdout.strip() == 'OK', c
    record('c11_consumer_constants_and_argument_contract')
    main_db, small_db = str(root / 'main.sqlite'), str(root / 'small.sqlite')
    for db, batch, total in [(main_db, 'all.batch', corpus['batch_wires']),
                             (small_db, 'small.batch', None)]:
        r = run(['receive-batch', db, a.fixtures / batch])
        assert r['status'] == 0 and r['rejected'] == [], r['rejected'][:5]
        assert total is None or r['accepted'] == total == r['created'], r
        assert r['lines'] == r['accepted']
    record('corpus_wires_incl_ascii_and_reordered_encodings_accepted_by_product_store')

    def dump(db):
        with contextlib.closing(sqlite3.connect(db)) as conn:
            lines = list(conn.iterdump())
            version = conn.execute('PRAGMA user_version').fetchone()[0]
            app = conn.execute('PRAGMA application_id').fetchone()[0]
            progress = conn.execute("SELECT revision_id,entity_key FROM reader_revisions WHERE entity_kind='progress' ORDER BY 1").fetchall()
        return hashlib.sha256('\n'.join(lines).encode('utf-8')).hexdigest(), version, app, progress, len(lines)
    before_main, before_small = dump(main_db), dump(small_db)
    assert before_main[3], 'fixture has a progress revision'

    def leftovers(directory):
        return sorted(n for n in os.listdir(directory) if n.startswith('.exr-export-'))

    def expected_totals(key):
        t = dict(annotations=0, current=0, tombstones=0, pending_parents=0, concurrent=0, blocked_restore=0, head_wires=0)
        for aid, e in books[key]['annotations'].items():
            t['annotations'] += 1
            t['head_wires'] += len(e['heads'])
            if e['selection'] == 'safe':
                t['tombstones' if e['tombstone'] else 'current'] += 1
            else:
                t[e['selection']] += 1
        return t

    def graph_ok(e, observed):
        """Clean histories report no missing/foreign parent; a pending history reports at least the expected
        number of unresolved parents (the revision store alone defines whether a late cross-entity parent is
        counted as missing or foreign, so only the sum is asserted)."""
        if e['selection'] != 'pending_parents':
            return observed == (0, 0)
        return sum(observed) >= e['missing_parents'] + e['foreign_parents'] and (e['label'] != 'missing_parent' or observed[0] == 1)

    # ---------- JSONL reader ----------
    def read_jsonl(path, key, title):
        raw = Path(path).read_bytes()
        assert raw.endswith(b'\n') and b'\r\n' not in raw and b'\x00' not in raw
        raw.decode('utf-8')
        lines = raw.split(b'\n')[:-1]
        header, footer = json.loads(lines[0]), json.loads(lines[-1])
        assert list(header) == ['type', 'format', 'format_version', 'module_version', 'book_key', 'book_title', 'order', 'wire_encoding'], list(header)
        assert (header['type'], header['format'], header['format_version'], header['module_version']) == ('header', 'exreader-annotation-export', 1, '0.1.0')
        assert header['book_key'] == key and header['book_title'] == title
        assert header['order'] == 'annotation_id_ascending' and header['wire_encoding'] == 'json_string_utf8'
        want = books[key]['annotations'] if key in books else {}
        totals = expected_totals(key) if key in books else dict(annotations=0, current=0, tombstones=0, pending_parents=0, concurrent=0, blocked_restore=0, head_wires=0)
        assert list(footer) == ['type', 'annotations', 'current', 'tombstones', 'pending_parents', 'concurrent', 'blocked_restore', 'head_wires', 'complete'], list(footer)
        assert footer == dict(type='footer', complete=True, **totals), (footer, totals)
        body = lines[1:-1]
        assert len(body) == totals['annotations']
        ids = []
        for line in body:
            row = json.loads(line)
            assert list(row) == ['type', 'annotation_id', 'entity_key', 'selection', 'tombstone', 'graph', 'heads'], list(row)
            aid = row['annotation_id']
            ids.append(aid)
            e = want[aid]
            assert row['type'] == 'annotation' and row['entity_key'] == key + ':' + aid
            assert row['selection'] == e['selection'] and row['tombstone'] == e['tombstone'], (aid, row['selection'], e['selection'])
            g = row['graph']
            assert list(g) == ['revisions', 'heads', 'missing_parents', 'foreign_parents', 'projection_safe', 'deleted', 'requires_restore']
            assert g['revisions'] == e['revisions'] and g['heads'] == len(e['heads']) == len(row['heads']), (aid, g, e)
            assert graph_ok(e, (g['missing_parents'], g['foreign_parents'])), (aid, g)
            assert g['projection_safe'] == (e['selection'] == 'safe')
            if e['selection'] == 'safe':
                assert g['deleted'] == e['tombstone'] and not g['requires_restore']
            second = manual_wires(line)
            assert len(second) == len(row['heads'])
            assert [h['revision_id'] for h in row['heads']] == [h['id'] for h in e['heads']], 'heads ascending by revision id'
            for h, expect, again in zip(row['heads'], e['heads'], second):
                assert list(h) == ['revision_id', 'operation', 'sha256', 'bytes', 'wire']
                original = wires[expect['id']]
                assert h['operation'] == expect['operation']
                assert h['wire'].encode('utf-8') == original, ('wire differs', expect['id'])
                assert again == original, ('manual reader differs', expect['id'])
                assert h['bytes'] == len(original) and h['sha256'] == hashlib.sha256(original).hexdigest()
                assert json.loads(original)['id'] == h['revision_id']
        assert ids == sorted(want) and len(set(ids)) == len(ids), 'bytewise ascending, no duplicates, nothing from another book'
        return header, footer, lines

    # ---------- Markdown reader ----------
    def read_markdown(path, key, title):
        text = Path(path).read_bytes().decode('utf-8')
        assert '\r' not in text and text.endswith('\n') and '\x00' not in text
        lines = text.split('\n')[:-1]
        assert lines[0].startswith('# ')
        assert unescape_md(lines[0][2:]) == (title if title is not None else key), lines[0]
        assert lines[2] == '- 书籍标识：`' + key + '`'
        annotations, cur, head, label, i = [], None, None, None, 3
        outside = [lines[0][2:]]
        while i < len(lines):
            line = lines[i]
            m = re.match(r'^(`{3,})text$', line)
            if m:
                fence = m.group(1)
                body = []
                i += 1
                while not re.fullmatch('`{%d,}' % len(fence), lines[i]):
                    assert not lines[i].startswith(fence), 'content line could close the fence'
                    body.append(lines[i])
                    i += 1
                assert lines[i] == fence, 'closing fence differs from opening fence'
                head['blocks'][label] = '\n'.join(body)
                i += 1
                continue
            outside.append(line)
            if line.startswith('## 批注 '):
                cur = {'number': int(line[len('## 批注 '):]), 'heads': []}
                annotations.append(cur)
            elif line.startswith('- 标注标识：`'):
                cur['id'] = line[len('- 标注标识：`'):-1]
            elif line.startswith('- 状态：'):
                cur['status'] = line[len('- 状态：'):]
            elif line.startswith('- 修订图：'):
                cur['graph'] = [int(x) for x in re.fullmatch(r'- 修订图：修订 (\d+)，头 (\d+)，缺失父修订 (\d+)，外来父修订 (\d+)', line).groups()]
            elif line.startswith('### 头 '):
                m2 = re.fullmatch(r'### 头 (\d+)/(\d+)：修订 `([0-9a-f]{32})`（(.*)）', line)
                head = {'index': int(m2.group(1)), 'count': int(m2.group(2)), 'id': m2.group(3), 'op': unescape_md(m2.group(4)), 'blocks': {}, 'fields': {}}
                cur['heads'].append(head)
            elif line == '- 该头是删除记录，没有位置和正文。':
                head['deleted'] = True
            elif line.startswith('- 位置模式：'):
                mm = re.fullmatch(r'- 位置模式：(\w+)；锚点版本：(\d+)', line)
                head['fields']['mode'], head['fields']['version'] = mm.group(1), int(mm.group(2))
            elif line.startswith('- 书内部分路径：'):
                head['fields']['part_path'] = unescape_md(line[len('- 书内部分路径：'):])
            elif line.startswith('- 部分序号：'):
                head['fields']['part'] = int(line[len('- 部分序号：'):])
            elif line.startswith('- 页面标识：'):
                mm = re.fullmatch(r'- 页面标识：(.*)；页索引（从0起）：(\d+)', line)
                head['fields']['page_id'], head['fields']['page'] = unescape_md(mm.group(1)), int(mm.group(2))
            elif line.startswith('- 章节范围：'):
                head['fields']['chapter'] = unescape_md(line[len('- 章节范围：'):])
            elif line.startswith('- 偏移提示（仅供参考，未用于定位）：'):
                mm = re.fullmatch(r'- 偏移提示（仅供参考，未用于定位）：(\d+)–(\d+)', line)
                head['fields']['start'], head['fields']['end'] = int(mm.group(1)), int(mm.group(2))
            elif line in ('引文：', '前文：', '后文：', '批注：'):
                label = line[:-1]
            elif line in ('引文：（无，位置点或书签）', '批注：（空）'):
                head['blocks'][line[:2]] = None
            elif line.startswith('共 ') or line in ('', '---') or line.startswith('- 导出：') or line.startswith('- 说明：'):
                pass
            else:
                raise AssertionError('unrecognized Markdown line: ' + line[:80])
            i += 1
        # nothing outside a fenced block can render as markup, HTML or a link
        scrub = []
        for line in outside:
            line = re.sub(r'^(#+ |- )', '', line)
            line = re.sub(r'`[0-9A-Za-z:._-]+`', '', line)
            line = re.sub(r'\\[!-/:-@\[-`{-~]', '', line)
            scrub.append(line)
        flat = '\n'.join(scrub)
        assert not re.search(r'[<>&\[\]*#!|~`]', flat), 'unescaped markup outside fenced blocks'
        assert 'http' not in flat.lower()
        return annotations, text

    def check_markdown(path, key, title, jsonl_lines=None):
        annotations, text = read_markdown(path, key, title)
        want = books[key]['annotations'] if key in books else {}
        assert [x['id'] for x in annotations] == sorted(want), 'ascending, complete'
        assert [x['number'] for x in annotations] == list(range(1, len(want) + 1))
        for x in annotations:
            e = want[x['id']]
            prefix = {'safe': '已删除（墓碑' if e['tombstone'] else '当前批注（唯一的安全头）',
                      'concurrent': '冲突：存在 %d 个并发头，未选择任何一个' % len(e['heads']),
                      'blocked_restore': '冲突：删除后被隐式恢复',
                      'pending_parents': '未定位：缺少父修订或父修订不属于本批注'}[e['selection']]
            assert x['status'].startswith(prefix), (x['id'], x['status'])
            r, h, mp, fp = x['graph']
            assert (r, h) == (e['revisions'], len(e['heads'])) and graph_ok(e, (mp, fp)), (x['id'], x['graph'])
            assert [h['id'] for h in x['heads']] == [h['id'] for h in e['heads']]
            for got, expect in zip(x['heads'], e['heads']):
                assert (got['index'], got['count']) == (e['heads'].index(expect) + 1, len(e['heads'])) and got['op'] == expect['operation']
                if not expect['has_location']:
                    assert got.get('deleted') and not got['fields'] and not got['blocks']
                    continue
                s = expect['spec']
                f = got['fields']
                assert (f['mode'], f['version']) == (s['mode'], s['version'])
                start = s.get('start', 0)
                exact = s.get('exact', '')
                span = len(exact.encode()) if s['version'] == 2 else s.get('span', len(exact.encode()))
                assert (f['start'], f['end']) == (start, start + span)
                if s['mode'] == 'epub_chapter':
                    assert f['part_path'] == s['part_path'] and f.get('part') == (s['part'] if s['version'] == 2 else None)
                if s['mode'] == 'fixed_page':
                    assert (f['page_id'], f['page']) == (s['page_id'], s['page'])
                if s['mode'] == 'reflow_global' and s['version'] == 2:
                    assert f['chapter'] == (s.get('chapter') or '无')
                for label, value in [('引文', exact), ('前文', s.get('prefix', '')), ('后文', s.get('suffix', '')), ('批注', expect['note'])]:
                    shown = got['blocks'].get(label, 'absent')
                    if value:
                        norm = md_norm(value)
                        norm = norm[:-1] if norm.endswith('\n') else norm
                        assert shown == norm, (x['id'], label, shown, norm)
                    elif label in ('引文', '批注'):
                        assert shown is None, (x['id'], label)
                    else:
                        assert shown == 'absent'
        return text

    # ---------- JSONL + Markdown, all modes, derived and explicit titles ----------
    out = root / 'out'
    out.mkdir()
    state = {}
    for key in (TXT, EPUB, PDF, OTHER):
        j, m = out / (key.split(':')[0] + '-' + key[-4:] + '.jsonl'), out / (key.split(':')[0] + '-' + key[-4:] + '.md')
        r = export(main_db, key, j, m)
        assert r['status'] == S_OK, r
        t = expected_totals(key)
        assert {k: r['stats'][k] for k in t} == t, (r['stats'], t)
        assert r['stats']['jsonl_published'] == r['stats']['markdown_published'] == 1
        assert r['stats']['jsonl_bytes'] == j.stat().st_size and r['stats']['markdown_bytes'] == m.stat().st_size
        read_jsonl(j, key, books[key]['title'])
        check_markdown(m, key, books[key]['title'])
        state[key] = (j, m, r)
        cases.append({'id': 'export-' + key.split(':')[0], 'book': key, 'stats': r['stats'], 'polls': r['polls']})
    assert leftovers(out) == []
    record('txt_unicode_newline_quote_markdown_html_samples_roundtrip_exact_wire_and_visible_text')
    record('epub_and_pdf_modes_with_anchor_v1_and_v2_roundtrip')
    ids_txt = set(books[TXT]['annotations'])
    assert not (ids_txt & set(books[OTHER]['annotations'])) and (out / 'txt-9999.jsonl').read_bytes().count(b'not this book') == 1
    assert b'not this book' not in state[TXT][0].read_bytes() and 'not this book' not in state[TXT][1].read_text(encoding='utf-8')
    record('other_books_annotations_progress_and_book_records_never_leak')
    sel = {e['label']: e['selection'] for e in books[TXT]['annotations'].values()}
    assert sel['concurrent_put_delete'] == sel['concurrent_three'] == 'concurrent' and sel['missing_parent'] == sel['foreign_parent'] == 'pending_parents'
    assert sel['blocked_restore'] == 'blocked_restore' and sel['tombstone'] == 'safe' and sel['explicit_restore'] == 'safe'
    r = state[TXT][2]['stats']
    assert (r['concurrent'], r['pending_parents'], r['blocked_restore'], r['tombstones']) == (2, 2, 1, 1)
    record('conflict_tombstone_missing_and_foreign_parent_states_keep_every_head_without_choosing')
    # an explicit title replaces the derived one and is escaped in Markdown
    jt, mt = out / 'titled.jsonl', out / 'titled.md'
    custom = '手动书名 "q" <b>*x*</b> & [l](u) `t` \\ 🙂'
    r = export(main_db, TXT, jt, mt, title=custom)
    assert r['status'] == S_OK
    read_jsonl(jt, TXT, custom)
    check_markdown(mt, TXT, custom)
    ju, mu = out / 'unknown.jsonl', out / 'unknown.md'
    r = export(main_db, UNKNOWN, ju, mu)
    assert r['status'] == S_OK and r['stats']['annotations'] == 0
    read_jsonl(ju, UNKNOWN, None)
    check_markdown(mu, UNKNOWN, None)
    record('explicit_title_override_and_untitled_book_are_escaped_and_declared')

    # ---------- empty export ----------
    je, me = out / 'empty.jsonl', out / 'empty.md'
    r = export(main_db, EMPTY, je, me)
    assert r['status'] == S_OK and r['stats']['annotations'] == 0 and r['stats']['head_wires'] == 0
    header, footer, lines = read_jsonl(je, EMPTY, books[EMPTY]['title'])
    assert len(lines) == 2
    annotations, text = read_markdown(me, EMPTY, books[EMPTY]['title'])
    assert annotations == [] and '共 0 条标注实体' in text
    record('empty_export_has_header_footer_and_title_only')

    # ---------- 1234 annotations over 13 keyset pages, deterministic ----------
    jm, mm_ = out / 'mass.jsonl', out / 'mass.md'
    r = export(main_db, MASS, jm, mm_)
    assert r['status'] == S_OK and r['stats']['annotations'] == 1234
    header, footer, lines = read_jsonl(jm, MASS, books[MASS]['title'])
    check_markdown(mm_, MASS, books[MASS]['title'])
    first = (jm.read_bytes(), mm_.read_bytes())
    jm2, mm2 = out / 'mass2.jsonl', out / 'mass2.md'
    r2 = export(main_db, MASS, jm2, mm2)
    assert (jm2.read_bytes(), mm2.read_bytes()) == first and r2['polls'] == r['polls']
    assert r['stats']['concurrent'] > 0 and r['stats']['tombstones'] > 0 and r['stats']['annotations'] > 1000
    mass_polls = r['polls']
    cases.append({'id': 'export-mass', 'stats': r['stats'], 'polls': r['polls'], 'jsonl_bytes': len(first[0]), 'markdown_bytes': len(first[1])})
    record('thousand_plus_annotations_stream_across_keyset_pages_in_order_and_repeat_byte_identically')

    # ---------- unicode directory and file names ----------
    ud = out / UNICODE_DIR
    ud.mkdir()
    ju_, mu_ = ud / '导出 🙂.jsonl', ud / '导出 🙂.md'
    r = export(main_db, TXT, ju_, mu_)
    assert r['status'] == S_OK
    assert ju_.read_bytes() == state[TXT][0].read_bytes() and mu_.read_bytes() == state[TXT][1].read_bytes()
    assert leftovers(ud) == []
    record('unicode_output_path_publishes_identical_bytes')

    # ---------- atomic replace and failure retention ----------
    def old_file(path):
        path.write_bytes(('旧的有效导出\n' + path.name + '\n').encode('utf-8'))
        return path.read_bytes()
    work = root / 'atomic'
    work.mkdir()
    jp, mp = work / 'book.jsonl', work / 'book.md'
    old_j, old_m = old_file(jp), old_file(mp)
    r = export(main_db, TXT, jp, mp)
    assert r['status'] == S_OK and jp.read_bytes() == state[TXT][0].read_bytes() and mp.read_bytes() == state[TXT][1].read_bytes()
    assert jp.read_bytes() != old_j and leftovers(work) == []
    size = jp.stat().st_size
    record('successful_export_atomically_replaces_an_existing_file')

    def intact(label, status, only_jsonl=False, **kw):
        good_j, good_m = jp.read_bytes(), mp.read_bytes()
        r = export(main_db, TXT if 'book' not in kw else kw.pop('book'), jp, None if only_jsonl else mp, **kw)
        assert r['status'] == status, (label, r)
        assert jp.read_bytes() == good_j and mp.read_bytes() == good_m, label + ': previous valid export changed'
        assert leftovers(work) == [], label + ': temporary file left behind'
        assert r['stats']['jsonl_published'] == r['stats']['markdown_published'] == 0, label
        cases.append({'id': label, 'status': r['status'], 'os_error': r['os_error'], 'polls': r['polls']})
        return r
    total_polls = state[TXT][2]['polls']
    assert total_polls > 3
    for n in (1, 2, total_polls // 2, total_polls):
        intact('cancel-%d-of-%d' % (n, total_polls), S_CANCELLED, extra=['cancel_after=%d' % n])
    intact('cancel-mid-mass', S_CANCELLED, book=MASS, extra=['cancel_after=%d' % (mass_polls // 2)])
    record('cancellation_before_during_and_at_the_final_flush_keeps_previous_export_and_removes_temp_files')
    r = export(main_db, TXT, jp, None, budget=size)
    assert r['status'] == S_OK and jp.read_bytes() == state[TXT][0].read_bytes()
    jp.write_bytes(old_j)
    intact('budget-one-byte-short', S_LIMIT, only_jsonl=True, budget=size - 1)
    intact('budget-small', S_LIMIT, budget=3000)
    record('output_budget_is_exact_and_breach_keeps_previous_export')
    sub = work / 'dir.md'
    sub.mkdir()
    r = export(main_db, TXT, jp, sub)
    assert r['status'] == S_IO and r['os_error'] != 0 and sub.is_dir() and leftovers(work) == []
    assert r['stats']['jsonl_published'] == 1 and r['stats']['markdown_published'] == 0
    assert jp.read_bytes() == state[TXT][0].read_bytes()
    sub.rmdir()
    r = export(main_db, TXT, work / 'no-such-dir' / 'x.jsonl', None)
    assert r['status'] == S_IO and r['os_error'] != 0 and not (work / 'no-such-dir').exists()
    jp.write_bytes(old_j)
    mp.write_bytes(old_m)
    (work / 'sub.d').mkdir()
    r = export(main_db, TXT, work / 'sub.d', None)
    assert r['status'] == S_IO and (work / 'sub.d').is_dir() and leftovers(work) == []
    record('publish_failures_directory_target_missing_parent_and_partial_two_output_publish_are_reported_exactly')
    if system != 'windows':
        jp.write_bytes(old_j)
        r = intact('posix-fsize-mid-stream-write-failure', S_IO, book=MASS, only_jsonl=True, extra=['fsize=40000'])
        assert r['os_error'] != 0 and 'write' in r['message'].lower()
        record('mid_stream_write_failure_rlimit_fsize_keeps_previous_export')
        skipped.append({'name': 'windows_locked_target_publish_failure', 'reason': 'Windows-only sharing violation case'})
    else:
        jp.write_bytes(old_j)
        r = intact('windows-locked-target-publish-failure', S_IO, only_jsonl=True, extra=['lock=' + hexs(str(jp))])
        assert r['os_error'] != 0 and 'publish' in r['message'].lower()
        record('locked_target_publish_failure_keeps_previous_export')
        skipped.append({'name': 'posix_rlimit_fsize_mid_stream_write_failure', 'reason': 'RLIMIT_FSIZE does not exist on Windows; locked-target publish failure covers this platform'})

    # ---------- argument and ownership refusals ----------
    jp.write_bytes(old_j)
    before_listing = sorted(os.listdir(work))

    def where(name):
        if name == '-':
            return '-'
        return hexs(str(work) + os.sep + name[:-1] + os.sep) if name.endswith('/') else hexs(str(work / name))

    def refuse(label, statuses, jsonl='x.jsonl', md='-', title_hex=None, key=TXT, budget=0, extra=()):
        r = run(['export', main_db, key, title_hex or '-', where(jsonl), where(md), budget, *extra])
        assert r['status'] in statuses, (label, r)
        assert sorted(os.listdir(work)) == before_listing, label + ': filesystem changed'
        assert r['stats']['jsonl_published'] == r['stats']['markdown_published'] == 0
        return r
    refuse('no-output', (S_ARGUMENT,), jsonl='-', md='-')
    refuse('same-path', (S_ARGUMENT,), jsonl='x.jsonl', md='x.jsonl')
    refuse('directory-path', (S_ARGUMENT,), jsonl='x.jsonl/')
    refuse('bad-title-utf8', (S_ARGUMENT,), title_hex='fffe')
    pad = 4096 - len(str(work)) - 1
    long_path = run(['export', main_db, TXT, '-', hexs(str(work) + os.sep + 'x' * (pad + 1)), '-', 0])
    ok_len = run(['export', main_db, TXT, '-', hexs(str(work) + os.sep + 'x' * pad), '-', 0])
    assert long_path['status'] == S_ARGUMENT and ok_len['status'] == S_IO, (long_path, ok_len)
    assert sorted(os.listdir(work)) == before_listing
    refuse('budget-over-hard-maximum', (S_ARGUMENT,), budget=(1 << 30) + 1)
    refuse('bad-book-key', (S_ARGUMENT, S_REVISION), key='txt:bad')
    refuse('book-key-with-markup', (S_ARGUMENT,), key='txt:`x`')
    refuse('short-struct', (S_ARGUMENT,), extra=['short_struct=1'])
    refuse('null-options', (S_ARGUMENT,), extra=['null_options=1'])
    r = refuse('non-owner-thread', (S_REVISION,), extra=['thread=1'])
    assert r['revision_code'] == OWNER, r
    record('invalid_options_paths_budgets_titles_book_keys_and_non_owner_calls_are_refused_without_writing')


    # ---------- one valid public snapshot per entity over a real second process ----------
    # The corpus holds one annotation per window book. The export blocks inside its
    # own cancel callback between the page read and that entity's heads read, a
    # second process commits one advance revision on the same product database, and
    # only then does the export continue. Everything the export publishes for that
    # entity must come from the one later public snapshot.
    def derive_selection(graph):
        if graph['heads'] == 0:
            return 'missing'
        if graph['missing_parents'] or graph['foreign_parents']:
            return 'pending_parents'
        if graph['heads'] > 1:
            return 'concurrent'
        return 'safe' if graph['projection_safe'] else 'blocked_restore'

    def wait_for(path, seconds):
        for _ in range(seconds * 100):
            if Path(path).exists():
                return True
            time.sleep(0.01)
        return False

    window_digests = {}

    def window_case(case):
        wdir = root / 'window'
        wdir.mkdir(exist_ok=True)
        name = case['case']
        jsonl, markdown = wdir / (name + '.jsonl'), wdir / (name + '.md')
        go, done = wdir / (name + '.go'), wdir / (name + '.done')
        args = [probe, 'export', main_db, case['book'], hexs(case['title']), hexs(str(jsonl)), hexs(str(markdown)), '0',
                'advance_at_poll=2', 'go=' + hexs(str(go)), 'done=' + hexs(str(done)), 'advance_wait=240']
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        try:
            assert wait_for(go, 240), ('export never reached the page/entity window', name)
            advance = run(['receive-batch', main_db, a.fixtures / ('advance-' + name + '.batch')])
            assert advance['status'] == 0 and advance['accepted'] == 1 and advance['created'] == 1, (name, advance)
        finally:
            if not done.exists():
                done.write_bytes(b'')
            stdout, stderr = process.communicate(timeout=600)
        assert process.returncode == 0, (name, process.returncode, stderr, stdout[:300])
        result = json.loads(stdout)
        assert result['advanced'] == 1 and result['advance_timeout'] == 0, (name, result)
        assert result['status'] == S_OK, (name, result)
        lines = jsonl.read_bytes().split(b'\n')[:-1]
        footer = json.loads(lines[-1])
        body = [json.loads(x) for x in lines[1:-1]]
        assert len(body) == 1 and body[0]['annotation_id'] == case['annotation'], (name, body)
        row, graph, heads = body[0], body[0]['graph'], body[0]['heads']
        derived = derive_selection(graph)
        assert row['selection'] == derived, ('selection disagrees with the exported graph', name, row['selection'], derived, graph)
        expected_tombstone = derived == 'safe' and len(heads) == 1 and heads[0]['operation'] == 'delete'
        assert row['tombstone'] == expected_tombstone, ('tombstone disagrees with the exported heads', name, row['tombstone'], expected_tombstone, heads)
        assert graph['heads'] == len(heads), ('graph head count differs from the head list', name, graph, len(heads))
        assert row['selection'] == case['expected']['selection'] and row['tombstone'] == case['expected']['tombstone'], (name, row['selection'], case['expected'])
        assert [h['revision_id'] for h in heads] == case['expected']['heads'], (name, [h['revision_id'] for h in heads], case['expected'])
        assert graph['revisions'] == case['expected']['revisions'], (name, graph)
        if derived == 'safe':
            assert graph['projection_safe'] is True and graph['deleted'] == case['expected']['tombstone'] and not graph['requires_restore'], (name, graph)
            assert graph['missing_parents'] == 0 and graph['foreign_parents'] == 0, (name, graph)
        wire = bytes.fromhex(case['advance']['wire_hex'])
        assert heads[0]['wire'].encode('utf-8') == wire and heads[0]['sha256'] == case['advance']['sha256'], ('advanced wire differs', name)
        assert heads[0]['bytes'] == len(wire) and manual_wires(lines[1]) == [wire], ('second reader differs', name)
        want = dict(annotations=1, current=0, tombstones=0, pending_parents=0, concurrent=0, blocked_restore=0, head_wires=len(heads))
        if derived == 'safe':
            want['tombstones' if row['tombstone'] else 'current'] += 1
        else:
            want[derived] += 1
        assert footer == dict(type='footer', complete=True, **want), (name, footer, want)
        stats = result['stats']
        assert {k: stats[k] for k in want} == want, (name, stats, want)
        annotations, _ = read_markdown(markdown, case['book'], case['title'])
        assert len(annotations) == 1 and annotations[0]['id'] == case['annotation'], (name, annotations)
        prefix = {'safe': '已删除（墓碑' if row['tombstone'] else '当前批注（唯一的安全头）',
                  'concurrent': '冲突：存在 1 个并发头', 'blocked_restore': '冲突：删除后被隐式恢复',
                  'pending_parents': '未定位：缺少父修订或父修订不属于本批注',
                  'missing': '未定位：没有可用的修订'}[derived]
        assert annotations[0]['status'].startswith(prefix), ('markdown status disagrees', name, annotations[0]['status'], prefix)
        assert annotations[0]['graph'] == [graph['revisions'], len(heads), graph['missing_parents'], graph['foreign_parents']], (name, annotations[0]['graph'])
        window_digests['window-' + name + '.jsonl'] = hashlib.sha256(jsonl.read_bytes()).hexdigest()
        window_digests['window-' + name + '.md'] = hashlib.sha256(markdown.read_bytes()).hexdigest()
        cases.append({'id': 'window-' + name, 'selection': derived, 'tombstone': row['tombstone'], 'graph': graph})

    window_names = {'parent_arrival': 'window_parent_arrival_is_exported_from_one_consumed_snapshot',
                    'explicit_merge': 'window_explicit_merge_is_exported_from_one_consumed_snapshot',
                    'delete_merge': 'window_delete_merge_keeps_tombstone_and_graph_from_one_snapshot',
                    'explicit_restore': 'window_explicit_restore_unblocks_in_one_snapshot'}

    def window_gap():
        for case in corpus['window']:
            window_case(dict(case, title=corpus['books'][case['book']]['title']))
            record(window_names[case['case']])
        assert leftovers(root / 'window') == []

    # ---------- real output path aliases ----------
    def alias_gap():
        al = root / 'alias'
        al.mkdir()
        keep_jsonl, keep_md = al / 'book.jsonl', al / 'book.md'
        assert export(main_db, TXT, keep_jsonl, keep_md)['status'] == S_OK
        good_jsonl, good_md = keep_jsonl.read_bytes(), keep_md.read_bytes()
        base_path = str(al)
        sep = os.sep
        canonical = base_path + sep + 'x.jsonl'
        aliases = [('dot-segment', canonical, base_path + sep + '.' + sep + 'x.jsonl'),
                   ('duplicate-separator', canonical, base_path + sep + sep + 'x.jsonl')]
        (al / 'sub').mkdir()
        aliases.append(('parent-segment', canonical, base_path + sep + 'sub' + sep + '..' + sep + 'x.jsonl'))
        if system == 'windows':
            aliases.append(('case-folded', canonical, base_path + sep + 'X.JSONL'))
        else:
            (al / 'real').mkdir()
            os.symlink('real', str(al / 'link'))
            aliases.append(('symlinked-directory', base_path + sep + 'real' + sep + 'x.jsonl',
                            base_path + sep + 'link' + sep + 'x.jsonl'))
        for label, canon, alias in aliases:
            r = run(['export', main_db, TXT, '-', hexs(canon), hexs(alias), 0])
            assert r['status'] == S_ARGUMENT, ('alias not refused', label, r)
            assert r['stats']['jsonl_published'] == 0 and r['stats']['markdown_published'] == 0, (label, r['stats'])
            assert not Path(canon).exists() and not Path(alias).exists(), ('alias wrote a file', label)
            assert keep_jsonl.read_bytes() == good_jsonl and keep_md.read_bytes() == good_md, label + ': existing export changed'
            assert leftovers(al) == [], label + ': temporary file left behind'
            cases.append({'id': 'alias-' + label, 'status': r['status'], 'os_error': r['os_error']})
        r = export(main_db, TXT, al / 'a.jsonl', al / 'b.jsonl')
        assert r['status'] == S_OK and (al / 'a.jsonl').exists() and (al / 'b.jsonl').exists(), ('distinct targets refused', r)
        assert leftovers(al) == []
        record('path_aliases_that_resolve_to_one_target_are_refused_before_writing')

    # ---------- reentrant export from the cancel callback ----------
    def reentry_gap():
        re_dir = root / 'reentry'
        re_dir.mkdir()
        keep_jsonl, keep_md = re_dir / 'keep.jsonl', re_dir / 'keep.md'
        assert export(main_db, TXT, keep_jsonl, keep_md)['status'] == S_OK
        good_jsonl, good_md = keep_jsonl.read_bytes(), keep_md.read_bytes()
        nested = re_dir / 'nested.jsonl'

        def attempt(label, extra, expected):
            r = export(main_db, TXT, keep_jsonl, keep_md, extra=extra)
            assert r['status'] == expected, (label, r)
            assert r['reenter']['status'] == S_ARGUMENT and r['reenter']['code'] == S_ARGUMENT, (label, r['reenter'])
            assert not nested.exists(), (label, 'nested export published a file')
            assert leftovers(re_dir) == [], label + ': temporary file left behind'
            assert keep_jsonl.read_bytes() == good_jsonl and keep_md.read_bytes() == good_md, label + ': outer output changed'
            cases.append({'id': 'reentry-' + label, 'status': r['status'], 'nested': r['reenter']['status']})
            return r

        attempt('nested-target', ['reenter=1', 'reenter_path=' + hexs(str(nested))], S_OK)
        r = attempt('shared-stats', ['reenter=1', 'reenter_path=' + hexs(str(nested)), 'reenter_stats=1'], S_OK)
        assert r['stats']['annotations'] == expected_totals(TXT)['annotations'], ('outer stats were cleared', r['stats'])
        attempt('same-target', ['reenter=1', 'reenter_path=' + hexs(str(keep_jsonl))], S_OK)
        attempt('then-cancel', ['reenter=1', 'reenter_path=' + hexs(str(nested)), 'cancel_after=2'], S_CANCELLED)
        record('reentrant_export_from_the_cancel_callback_is_refused_and_the_outer_export_stays_recoverable')

    gaps = []
    def new_gap(label, body):
        try:
            body()
        except AssertionError as error:
            gaps.append({'gap': label, 'error': str(error)[:600]})
            print('VIOLATION ' + label + ': ' + str(error)[:600], flush=True)
    new_gap('single_entity_snapshot', window_gap)
    new_gap('output_path_alias', alias_gap)
    new_gap('reentrant_export', reentry_gap)
    assert not gaps, gaps

    # ---------- no private data ----------
    private = [str(root), str(root).replace('\\', '/'), os.environ.get('RUNNER_TEMP', '\0'), os.environ.get('HOME', '\0'),
               '.exr-export-', 'authorization', 'password', 'rowid', 'queue_id', 'attempts', '.sqlite', 'exr_library']
    for path in list(out.glob('*.jsonl')) + list(out.glob('*.md')):
        body = path.read_text(encoding='utf-8')
        for needle in private:
            if len(needle) > 1:
                assert needle.lower() not in body.lower(), (path.name, needle)
    record('outputs_contain_no_absolute_paths_account_secrets_or_sdk_row_ids')

    # ---------- read-only product ----------
    assert dump(main_db) == before_main and dump(small_db) == before_small
    record('database_and_progress_unchanged_after_every_export')
    # one more complete export on the small database proves independence from the mass book
    r = export(small_db, TXT, out / 'small.jsonl', out / 'small.md')
    assert r['status'] == S_OK and (out / 'small.jsonl').read_bytes() == state[TXT][0].read_bytes()
    assert dump(small_db) == before_small
    record('same_bytes_from_an_independent_database_copy')

    digests = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in
               [('txt.jsonl', state[TXT][0]), ('txt.md', state[TXT][1]), ('epub.jsonl', state[EPUB][0]), ('epub.md', state[EPUB][1]),
                ('pdf.jsonl', state[PDF][0]), ('pdf.md', state[PDF][1]), ('mass.jsonl', jm), ('mass.md', mm_), ('empty.jsonl', je), ('empty.md', me)]}
    digests.update(window_digests)
    report = {'accepted': True, 'digests': digests, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'granted_platform': system, 'checks': checks, 'count': len(checks),
              'skipped': skipped, 'cases': cases, 'wires': len(corpus['wires']), 'mass_annotations': 1234,
              'database_unchanged': True, 'schema_changed': False, 'sdk_changed': False, 'host_ui_accepted': False,
              'import_or_conflict_resolution': False, 'performance_claimed': False}
    (root / 'result.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'cases'}), flush=True)


if __name__ == '__main__':
    main()
