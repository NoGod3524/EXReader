# SPDX-License-Identifier: MIT
"""Actions-only deterministic corpus for the annotation export.

Writes <out>/corpus.json (the oracle: every wire as hex plus what each
annotation must be) and <out>/all.batch, <out>/small.batch (lines of
"<sha256> <exact wire bytes>\\n" for the probe's receive-batch).
"""
import hashlib
import json
import sys
from pathlib import Path

TXT = 'txt:' + 'a' * 64
EPUB = 'epub:' + 'b' * 64
PDF = 'pdf:' + 'c' * 64
OTHER = 'txt:' + '9' * 64
MASS = 'txt:' + 'e' * 64
EMPTY = 'txt:' + 'f' * 64
TITLES = {
    TXT: '《测试书》 é 🙂 <img src=x onerror=alert(1)> *bold* # [l](javascript:alert(1)) &copy; \\ `tick`',
    EPUB: 'EPUB "quoted" book',
    PDF: 'PDF 书',
    OTHER: 'Other book',
    MASS: '千条标注',
    EMPTY: '空书',
}


def canon(v):
    return json.dumps(v, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def spaced_ascii(v):
    """Default separators and \\uXXXX (surrogate pair) escapes: different bytes, same value."""
    return json.dumps(v, ensure_ascii=True).encode('utf-8')


def reordered(v):
    """Reversed key order, a display_time, and escaped solidus."""
    w = dict(reversed(list(v.items())))
    w['display_time'] = '2026-10-24T00:00:00Z'
    return json.dumps(w, ensure_ascii=False, separators=(',', ':')).replace('/', '\\/').encode('utf-8')


STYLES = {'canon': canon, 'ascii': spaced_ascii, 'reordered': reordered}


def selector(spec):
    exact = spec.get('exact', '')
    start = spec.get('start', 0)
    s = {'exact': exact, 'prefix': spec.get('prefix', ''), 'suffix': spec.get('suffix', ''),
         'start': start, 'end': start + (len(exact.encode('utf-8')) if spec['version'] == 2 else spec.get('span', len(exact.encode('utf-8'))))}
    if spec['version'] == 2 and spec['mode'] == 'reflow_global':
        s['chapter'] = spec.get('chapter')
    return s


def location(spec):
    loc = {'mode': spec['mode'], 'anchor_version': spec['version'], 'parser_version': '3.40.0', 'selector': selector(spec)}
    if spec['mode'] == 'epub_chapter':
        loc['part_path'] = spec['part_path']
        if spec['version'] == 2:
            loc['part'] = spec['part']
    if spec['mode'] == 'fixed_page':
        loc['page_id'] = spec['page_id']
        loc['page'] = spec['page']
    return loc


class Corpus:
    def __init__(self):
        self.wires = []
        self.books = {}
        self.counter = 0

    def rid(self):
        self.counter += 1
        return '%032x' % (0x100000 + self.counter)

    def add(self, value, style='canon'):
        data = STYLES[style](value)
        assert b'\n' not in data
        self.wires.append({'revision_id': value['id'], 'entity_kind': value['entity_kind'], 'entity_key': value['entity_key'],
                           'sha256': hashlib.sha256(data).hexdigest(), 'wire_hex': data.hex()})
        return value['id']

    def book(self, key, title):
        fmt = key.split(':')[0]
        v = {'version': 1, 'id': self.rid(), 'entity_kind': 'book', 'entity_key': key, 'operation': 'put', 'location_kind': 'none',
             'parents': [], 'payload': {'format': fmt, 'source_sha256': key.split(':')[1], 'source_bytes': 1000, 'title': title,
                                        'author': '', 'favorite': False}}
        self.add(v)
        self.books[key] = {'title': title, 'annotations': {}}

    def progress(self, key, spec):
        v = {'version': 1, 'id': self.rid(), 'entity_kind': 'progress', 'entity_key': key, 'operation': 'put',
             'location_kind': spec['mode'], 'parents': [],
             'payload': {'book_key': key, 'location': location(spec)}}
        self.add(v)

    def revision(self, key, aid, op, parents, spec, note, style='canon', revision_id=None):
        v = {'version': 1, 'id': revision_id or self.rid(), 'entity_kind': 'annotation', 'entity_key': key + ':' + aid,
             'operation': op, 'location_kind': spec['mode'], 'parents': parents,
             'payload': None if op == 'delete' else {'book_key': key, 'annotation_id': aid, 'location': location(spec), 'text': note}}
        self.add(v, style)
        return {'id': v['id'], 'operation': op, 'has_location': op != 'delete',
                'spec': None if op == 'delete' else spec, 'note': None if op == 'delete' else note}

    def expect(self, key, aid, selection, heads, revisions, missing=0, foreign=0, tombstone=False, label=''):
        self.books[key]['annotations'][aid] = {
            'selection': selection, 'tombstone': tombstone, 'revisions': revisions, 'missing_parents': missing,
            'foreign_parents': foreign, 'heads': sorted(heads, key=lambda h: h['id']), 'label': label}


def reflow(version=2, **kw):
    return dict(mode='reflow_global', version=version, **kw)


def build():
    c = Corpus()
    for key, title in TITLES.items():
        c.book(key, title)
    n = [0]

    def aid(base=0x5000):
        n[0] += 1
        return '%032x' % (base + n[0])

    # ---------------- TXT book: text, encodings, wire styles ----------------
    long_cn = ('长文本批注。' * 800)
    long_exact = ('引文' * 1500)
    texts = [
        ('chinese', reflow(exact='中文引文，包含逗号。', prefix='前文', suffix='后文', start=100), '批注：这是一条中文批注\n第二行', 'canon'),
        ('emoji_combining', reflow(exact='🙂 👨‍👩‍👧‍👦 é 한 ﬁ', prefix='🙂', suffix='é', start=7), '带表情 🙂 与组合字符 é 的批注', 'canon'),
        ('newlines_quotes', reflow(exact='He said "hi"\r\nline2\\n\t\'single\' `tick`\rlone-cr', prefix='"q"', suffix="'s'", start=3), 'line1\r\nline2\nline3\r"quoted" \\ back\\slash', 'canon'),
        ('markdown_sample', reflow(exact='# Heading\n* list\n[link](javascript:alert(1))\n```\ncode\n```\n````\n    indented\n---\n> quote\n| a | b |', prefix='**', suffix='__', start=9),
         '```\nfence in note\n````\n``````text\n- [ ] task\n1. one\n![img](http://x.invalid/a.png)\n', 'canon'),
        ('html_sample', reflow(exact='<script>alert(1)</script><img src=x onerror=alert(1)> &amp; &lt;b&gt; <!-- c -->', prefix='<b>', suffix='</b>', start=11),
         '<b>bold</b>\n<a href="javascript:alert(1)">x</a>\n<iframe src="http://x.invalid/"></iframe> &#x3c;', 'canon'),
        ('bookmark_v2', reflow(exact='', prefix='前', suffix='后', start=40), '书签', 'canon'),
        ('empty_note_v2', reflow(exact='只有引文', start=50), '', 'canon'),
        ('v1_highlight', reflow(version=1, exact='版本一引文 v1 quote', prefix='前' * 300, suffix='后' * 300, start=60, span=19), 'v1 批注', 'canon'),
        ('v1_point_like', reflow(version=1, exact='x', start=5, span=0), 'v1 零宽度选择', 'canon'),
        ('controls', reflow(exact='tab\there \x01\x07\x1f del\x7f line sep \u0085', start=70), 'note \x01 \x07 \x1f \x7f   end', 'canon'),
        ('long_text', reflow(exact=long_exact, start=1000), long_cn, 'canon'),
        ('style_ascii', reflow(exact='转义🙂引文', prefix='前', suffix='后', start=80), '同值不同字节 🙂 / "q"', 'ascii'),
        ('style_reordered', reflow(exact='乱序/solidus', prefix='/', suffix='\\', start=90), '键序与 display_time', 'reordered'),
        ('v2_chapter', reflow(exact='章节范围引文', start=95, chapter='OPS/chapter-2.xhtml'), '带章节范围', 'canon'),
    ]
    for label, spec, note, style in texts:
        a = aid()
        h = c.revision(TXT, a, 'put', [], spec, note, style)
        c.expect(TXT, a, 'safe', [h], 1, label=label)
    # edit chain
    a = aid(); r1 = c.revision(TXT, a, 'put', [], reflow(exact='初稿', start=1), 'v1')
    r2 = c.revision(TXT, a, 'put', [r1['id']], reflow(exact='二稿', start=1), 'v2')
    r3 = c.revision(TXT, a, 'put', [r2['id']], reflow(exact='三稿', start=1), 'v3')
    c.expect(TXT, a, 'safe', [r3], 3, label='edit_chain')
    # tombstone
    a = aid(); r1 = c.revision(TXT, a, 'put', [], reflow(exact='将被删除', start=2), 'x')
    r2 = c.revision(TXT, a, 'delete', [r1['id']], reflow(), None)
    c.expect(TXT, a, 'safe', [r2], 2, tombstone=True, label='tombstone')
    # explicit restore
    a = aid(); r1 = c.revision(TXT, a, 'put', [], reflow(exact='先删后恢复', start=3), 'x')
    r2 = c.revision(TXT, a, 'delete', [r1['id']], reflow(), None)
    r3 = c.revision(TXT, a, 'restore', [r2['id']], reflow(exact='先删后恢复', start=3), '已恢复')
    c.expect(TXT, a, 'safe', [r3], 3, label='explicit_restore')
    # concurrent: put vs delete
    a = aid(); r1 = c.revision(TXT, a, 'put', [], reflow(exact='并发基线', start=4), 'base')
    r2 = c.revision(TXT, a, 'put', [r1['id']], reflow(exact='并发甲', start=4), '设备甲')
    r3 = c.revision(TXT, a, 'delete', [r1['id']], reflow(), None)
    c.expect(TXT, a, 'concurrent', [r2, r3], 3, label='concurrent_put_delete')
    # three-way concurrent puts
    a = aid(); r1 = c.revision(TXT, a, 'put', [], reflow(exact='三向基线', start=5), 'base')
    heads = [c.revision(TXT, a, 'put', [r1['id']], reflow(exact='分支%d <b>' % i, start=5), '分支 %d' % i) for i in range(3)]
    c.expect(TXT, a, 'concurrent', heads, 4, label='concurrent_three')
    # missing parent
    a = aid(); missing = '%032x' % 0xDEAD0001
    r1 = c.revision(TXT, a, 'put', [missing], reflow(exact='缺父修订', start=6), '父未到达')
    c.expect(TXT, a, 'pending_parents', [r1], 1, missing=1, label='missing_parent')
    # implicit resurrection stays blocked
    a = aid(); r1 = c.revision(TXT, a, 'put', [], reflow(exact='隐式复活', start=7), 'x')
    r2 = c.revision(TXT, a, 'delete', [r1['id']], reflow(), None)
    r3 = c.revision(TXT, a, 'put', [r2['id']], reflow(exact='隐式复活后', start=7), '未经 restore')
    c.expect(TXT, a, 'blocked_restore', [r3], 3, label='blocked_restore')
    # foreign parent: the parent arrives later and belongs to another annotation
    a = aid(); b = aid(); foreign_parent = '%032x' % 0xF0E1
    r1 = c.revision(TXT, a, 'put', [foreign_parent], reflow(exact='外来父', start=8), 'x')
    rg = c.revision(TXT, b, 'put', [], reflow(exact='父属于别的批注', start=9), 'y', revision_id=foreign_parent)
    c.expect(TXT, a, 'pending_parents', [r1], 1, foreign=1, label='foreign_parent')
    c.expect(TXT, b, 'safe', [rg], 1, label='foreign_parent_owner')
    # progress + another book's annotations must never leak
    c.progress(TXT, reflow(exact='', start=123))
    o = aid(0x8000); ho = c.revision(OTHER, o, 'put', [], reflow(exact='别的书', start=1), 'not this book')
    c.expect(OTHER, o, 'safe', [ho], 1, label='other_book')

    # ---------------- EPUB and PDF modes ----------------
    for label, spec, note in [
        ('epub_v1', dict(mode='epub_chapter', version=1, exact='EPUB v1 引文', prefix='p', suffix='s', start=3, part_path='OPS/ch1.xhtml'), 'epub v1'),
        ('epub_v2', dict(mode='epub_chapter', version=2, exact='EPUB v2 引文', prefix='p', suffix='s', start=4, part_path='OPS/ch1.xhtml', part=2), 'epub v2'),
        ('epub_v2_repeated_path', dict(mode='epub_chapter', version=2, exact='', start=0, part_path='OPS/ch1.xhtml', part=5), '重复路径的书签'),
        ('epub_global_chapter', reflow(exact='全局带章节', start=9, chapter='OPS/ch3.xhtml'), 'epub 全局'),
    ]:
        a = aid(0x6000); h = c.revision(EPUB, a, 'put', [], spec, note)
        c.expect(EPUB, a, 'safe', [h], 1, label=label)
    for label, spec, note in [
        ('pdf_v1', dict(mode='fixed_page', version=1, exact='PDF v1 quote', prefix='a', suffix='b', start=2, page_id='page-1', page=0), 'pdf v1'),
        ('pdf_v2', dict(mode='fixed_page', version=2, exact='PDF v2 引文 🙂', prefix='a', suffix='b', start=2, page_id='page-2', page=1), 'pdf v2'),
        ('pdf_textless', dict(mode='fixed_page', version=2, exact='', start=0, page_id='页面-3', page=2), '无文本页'),
    ]:
        a = aid(0x7000); h = c.revision(PDF, a, 'put', [], spec, note)
        c.expect(PDF, a, 'safe', [h], 1, label=label)

    # ---------------- 1234 annotations over 13 pages ----------------
    for i in range(1234):
        a = '%032x' % (0x2000000 + i * 3)
        spec = reflow(version=1 if i % 7 == 0 else 2, exact='第%d条' % i, start=i * 10, prefix='前', suffix='后')
        if i % 7 == 0:
            spec['span'] = len(spec['exact'].encode())
        r1 = c.revision(MASS, a, 'put', [], spec, '批注 %d' % i)
        if i % 50 == 49:
            r2 = c.revision(MASS, a, 'delete', [r1['id']], reflow(), None)
            c.expect(MASS, a, 'safe', [r2], 2, tombstone=True, label='mass_tombstone')
        elif i % 101 == 100:
            r2 = c.revision(MASS, a, 'put', [r1['id']], spec, '分支甲 %d' % i)
            r3 = c.revision(MASS, a, 'delete', [r1['id']], reflow(), None)
            c.expect(MASS, a, 'concurrent', [r2, r3], 3, label='mass_conflict')
        else:
            c.expect(MASS, a, 'safe', [r1], 1, label='mass')
    return c


def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True)
    c = build()
    corpus = {'books': {k: {'title': v['title'], 'annotations': v['annotations']} for k, v in c.books.items()}, 'wires': c.wires}
    (out / 'corpus.json').write_text(json.dumps(corpus, ensure_ascii=False, indent=1), encoding='utf-8')
    with open(out / 'all.batch', 'wb') as f:
        for w in c.wires:
            f.write(w['sha256'].encode() + b' ' + bytes.fromhex(w['wire_hex']) + b'\n')
    small = [w for w in c.wires if w['entity_key'].startswith(MASS) is False and MASS.split(':')[1] not in w['entity_key']]
    with open(out / 'small.batch', 'wb') as f:
        for w in small:
            f.write(w['sha256'].encode() + b' ' + bytes.fromhex(w['wire_hex']) + b'\n')
    print('wires', len(c.wires), 'small', len(small), 'mass annotations', len(c.books[MASS]['annotations']))


if __name__ == '__main__':
    main()
