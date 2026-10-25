# SPDX-License-Identifier: MIT
"""C06 Actions-only builds, installed-package consumers and independent judges.

Builds the unchanged default family, the original fixed-source baseline and the
explicit raw0.2 family from installed packages only, then drives the installed
probe. JSONL is judged here by Python's own json module, not by the C++ writer.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/c06'
START = 'e67d87cbeabb2457e0852f681ef0b27b2c0da4d8'
IMPORT_SOURCE = '9c7e276f13f42cb61a32507c36d1c22c4489bd01'
SDK_341 = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
PDF_SHA = '5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'
TXT_TEXT = 'A real public SDK text capture has enough context for stable matching.'
TXT_SHA = hashlib.sha256(TXT_TEXT.encode()).hexdigest()
SUFFIX = '.exe' if os.name == 'nt' else ''
ENV = dict(os.environ)
ENV['C06_TXT_SHA'] = TXT_SHA
CHECKS, FAILED = [], []
# probe status codes (see the two public headers)
EX_OK, EX_ARGUMENT, EX_REVISION, EX_LIMIT = 0, 1, 3, 5
AI_OK, AI_ARGUMENT, AI_FORMAT, AI_REVISION, AI_CANCELLED, AI_IDENTITY, AI_UNRESOLVED, AI_UNCONFIRMED = 0, 1, 4, 6, 7, 9, 10, 11
LOC_KEYS = ['mode', 'parser_version', 'anchor_version', 'page_id', 'page', 'part_path', 'part', 'chapter', 'start', 'end',
            'exact', 'prefix', 'suffix']


def run(args, name=None, timeout=1800, check=True, cwd=None):
    args = list(map(str, args))
    print('RUN', ' '.join(args), flush=True)
    p = subprocess.run(args, cwd=cwd or ROOT, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, encoding='utf-8', errors='replace', timeout=timeout)
    if name:
        (OUT / (name + '.log')).write_text(p.stdout, encoding='utf-8')
    print(p.stdout[-6000:], flush=True)
    if check and p.returncode:
        raise RuntimeError((args, p.returncode))
    return p


def expect(condition, name, detail=None):
    if not condition:
        FAILED.append({'name': name, 'detail': repr(detail)})
        raise AssertionError((name, detail))
    CHECKS.append(name)
    print('CHECK', name, flush=True)


def archive(sha, name, *paths):
    target = OUT / name
    target.mkdir()
    raw = subprocess.run(['git', 'archive', sha, *paths], cwd=ROOT, capture_output=True, check=True).stdout
    import io
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        tar.extractall(target, filter='data')
    return target


def build(source, name, prefix, extra=(), install=True, timeout=1800):
    target = OUT / name
    run(['cmake', '-S', source, '-B', target, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
         '-DCMAKE_INSTALL_PREFIX=' + str(prefix), *extra], name + '-configure')
    run(['cmake', '--build', target, '--parallel', '4'], name + '-build', timeout)
    if install:
        run(['cmake', '--install', target], name + '-install')
    return target


def refused_configure(source, name, extra):
    """A mixed install must fail at configure time; the failure text is kept."""
    p = run(['cmake', '-S', source, '-B', OUT / name, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', *extra], name, check=False)
    return p.returncode != 0


def paths(*prefixes):
    return '-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, prefixes))


def core(name, enabled, product, sdk, source=ROOT):
    prefix = OUT / (name + '-stage')
    flag = '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=' + ('ON' if enabled else 'OFF')
    build(source / 'apps/reader/revisions', name + '-revisions', prefix, [flag, '-DREADER_PRODUCT_PREFIX=' + str(product),
          paths(prefix, product)])
    build(source / 'apps/reader/reading-state', name + '-reading-state', prefix,
          [flag, '-DEXR_SDK_VERSION=3.41.0', '-DEXR_SDK=' + str(sdk), paths(prefix, product, sdk)])
    return prefix


def modules(name, enabled, core_prefix, product, sdk, export_source, import_source):
    prefix = OUT / (name + '-stage')
    flag = '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=' + ('ON' if enabled else 'OFF')
    if enabled:
        build(export_source, name + '-export', prefix, [flag, paths(core_prefix, product, sdk)])
        build(import_source, name + '-import', prefix, [flag, '-DREADER_ANNOTATION_IMPORT_BUILD=ON', paths(core_prefix, product, sdk)])
    else:
        build(export_source, name + '-export', prefix, [paths(core_prefix, product, sdk)])
        build(import_source, name + '-import', prefix, ['-DREADER_ANNOTATION_IMPORT_BUILD=ON', paths(core_prefix, product, sdk)])
    return prefix


def consumer(name, raw, *prefixes):
    target = build(ROOT / 'tests/reader_next_c06/consumer', name, OUT / (name + '-stage'),
                   ['-DC06_RAW=' + ('ON' if raw else 'OFF'), paths(*prefixes)], install=False)
    return target / ('c06-probe' + SUFFIX)


class Result:
    def __init__(self, process):
        self.text = process.stdout
        self.exit = process.returncode
        self.lines = process.stdout.splitlines()

    def value(self, prefix):
        for line in self.lines:
            if line.startswith(prefix + ' '):
                return line[len(prefix) + 1:]
        return None

    @property
    def status(self):
        return int(self.value('STATUS'))

    @property
    def message(self):
        return self.value('MESSAGE') or ''

    @property
    def stats(self):
        text = self.value('STATS') or ''
        if '=' in text:
            return {k: int(v) for k, v in (item.split('=') for item in text.split())}
        return [int(x) for x in text.split()]

    @property
    def items(self):
        out = []
        for line in self.lines:
            if line.startswith('ITEM '):
                parts = line.split()
                out.append({'index': int(parts[1]), **{k: int(v) for k, v in (x.split('=') for x in parts[2:])}})
        return out


def probe(exe, *args, label=None):
    p = subprocess.run([str(exe), *map(str, args)], cwd=ROOT, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, encoding='utf-8', errors='replace', timeout=900)
    if label:
        (OUT / 'probe-logs').mkdir(exist_ok=True)
        (OUT / 'probe-logs' / (label + '.log')).write_text(p.stdout, encoding='utf-8')
    print(label or ' '.join(map(str, args)), p.returncode, p.stdout[-1500:], flush=True)
    return Result(p)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(database):
    """Digest of every product table (reader_*) of a closed store, read from a disposable copy."""
    with tempfile.TemporaryDirectory(prefix='c06-dump-') as temporary:
        copy = Path(temporary) / 'db.sqlite'
        shutil.copyfile(database, copy)
        for suffix in ('-wal', '-shm'):
            if Path(str(database) + suffix).exists():
                shutil.copyfile(str(database) + suffix, str(copy) + suffix)
        connection = sqlite3.connect(copy)
        try:
            digest, counts = hashlib.sha256(), {}
            for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'reader%' ORDER BY name"):
                rows = sorted(repr(r) for r in connection.execute('SELECT * FROM "%s"' % name))
                counts[name] = len(rows)
                digest.update(name.encode() + b'\0' + '\n'.join(rows).encode('utf-8', 'surrogatepass') + b'\0')
            return digest.hexdigest(), counts
        finally:
            connection.close()


def revisions(database):
    with tempfile.TemporaryDirectory(prefix='c06-rev-') as temporary:
        copy = Path(temporary) / 'db.sqlite'
        shutil.copyfile(database, copy)
        for suffix in ('-wal', '-shm'):
            if Path(str(database) + suffix).exists():
                shutil.copyfile(str(database) + suffix, str(copy) + suffix)
        connection = sqlite3.connect(copy)
        try:
            return {r[0]: bytes(r[1]) for r in connection.execute('SELECT revision_id,CAST(body_json AS BLOB) FROM reader_revisions')}
        finally:
            connection.close()


def outbox_rows(database):
    with tempfile.TemporaryDirectory(prefix='c06-out-') as temporary:
        copy = Path(temporary) / 'db.sqlite'
        shutil.copyfile(database, copy)
        for suffix in ('-wal', '-shm'):
            if Path(str(database) + suffix).exists():
                shutil.copyfile(str(database) + suffix, str(copy) + suffix)
        connection = sqlite3.connect(copy)
        try:
            names = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%outbox%'")]
            return {n: connection.execute('SELECT COUNT(*) FROM "%s"' % n).fetchone()[0] for n in names}
        finally:
            connection.close()


def b64(data):
    return base64.b64encode(data).decode()


def expected_location(wire):
    value = json.loads(wire)
    payload = value['payload']
    if payload is None:
        return None
    loc, selector = payload['location'], payload['location']['selector']
    version, mode = loc['anchor_version'], loc['mode']

    def field(name):
        item = selector.get(name)
        if version == 3:
            return {'size': item['size'], 'base64': item['base64']}
        data = item.encode('utf-8') if item is not None else None
        return {'size': len(data) if data is not None else 0, 'base64': b64(data) if data is not None else None}
    return {'mode': mode, 'parser_version': loc['parser_version'], 'anchor_version': version,
            'page_id': loc.get('page_id'), 'page': loc.get('page') if mode == 'fixed_page' else None,
            'part_path': loc.get('part_path'), 'part': loc.get('part') if mode == 'epub_chapter' and version >= 2 else None,
            'chapter': selector.get('chapter'), 'start': selector['start'], 'end': selector['end'],
            'exact': field('exact'), 'prefix': field('prefix'), 'suffix': field('suffix')}


def parse_export(path, book, source_bytes, counts):
    """Independent judge of one raw3 JSONL file; returns the list of heads."""
    data = Path(path).read_bytes()
    expect(data.endswith(b'\n') and b'\r' not in data and b'\0' not in data, 'raw3 JSONL is LF-terminated UTF-8 without CR/NUL ' + book[:8])
    lines = [json.loads(line) for line in data.decode('utf-8').split('\n')[:-1]]
    header, footer, annotations = lines[0], lines[-1], lines[1:-1]
    expect(list(header) == ['type', 'format', 'format_version', 'module_version', 'book_key', 'source_bytes', 'book_title', 'order', 'wire_encoding']
           and header['format'] == 'exreader-annotation-export-raw3' and header['format_version'] == 1 and header['module_version'] == '0.2.0'
           and header['book_key'] == book and header['source_bytes'] == source_bytes, 'raw3 header identity ' + book[:8], header)
    ids = [a['annotation_id'] for a in annotations]
    expect(ids == sorted(ids) and len(set(ids)) == len(ids), 'annotations ascending ' + book[:8])
    heads = []
    for a in annotations:
        for h in a['heads']:
            wire = h['wire'].encode('utf-8')
            expect(list(h) == ['revision_id', 'operation', 'sha256', 'bytes', 'location', 'wire'], 'head key order')
            expect(hashlib.sha256(wire).hexdigest() == h['sha256'] and len(wire) == h['bytes'], 'head wire sha/bytes self-check')
            expect(h['location'] == expected_location(h['wire']), 'independent location equals wire', (h['location'], expected_location(h['wire'])))
            if h['location'] is not None:
                expect(list(h['location']) == LOC_KEYS, 'location key order')
            heads.append((a['annotation_id'], h, wire))
    expect(footer['type'] == 'footer' and footer['complete'] is True and footer['annotations'] == len(annotations)
           and footer['head_wires'] == len(heads), 'footer proves completeness ' + book[:8], footer)
    for key, value in counts.items():
        expect(footer[key] == value, f'footer {key}={value} {book[:8]}', footer)
    return heads


def mutate(source, target, edit):
    text = Path(source).read_text(encoding='utf-8')
    changed = edit(text)
    assert changed != text
    Path(target).write_text(changed, encoding='utf-8', newline='')
    return target


def guards():
    expect(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    expect(run(['git', 'rev-parse', 'HEAD']).stdout.strip() == os.environ['GITHUB_SHA'], 'tested source is the pushed SHA')
    run(['git', 'merge-base', '--is-ancestor', START, 'HEAD'])
    run(['git', 'diff', '--exit-code', SDK_341, 'HEAD', '--', 'src', 'include', 'cmake', 'CMakeLists.txt'])
    run(['git', 'diff', '--exit-code', START, 'HEAD', '--', 'apps/reader/store', 'apps/reader/revisions', 'apps/reader/reading-state',
         'apps/reader/reading-commands', 'apps/reader/annotation-view', 'tests/fixtures', 'extras', 'docs/READER-ANNOTATION-EXPORT.md',
         'tests/reader_annotation_export'])
    changed = run(['git', 'diff', '--name-only', START, 'HEAD']).stdout.split()
    allowed = ('apps/reader/annotation-export/', 'apps/reader/annotation-import/', 'tests/reader_next_c06/', 'docs/reader-next-c06/')
    exact = {'.github/workflows/reader-next-c06.yml', 'HANDOFF-RESULT-C06.md'}
    bad = [p for p in changed if not (p.startswith(allowed) or p in exact)]
    expect(not bad, 'only task-owned paths changed', bad)
    # The legacy part of the importer is byte-identical to the fixed source: only an appended #ifdef section is new.
    original = subprocess.run(['git', 'show', IMPORT_SOURCE + ':apps/reader/annotation-import/src/annotation_import.cpp'], cwd=ROOT, capture_output=True, check=True).stdout
    current = (ROOT / 'apps/reader/annotation-import/src/annotation_import.cpp').read_bytes()
    expect(current.startswith(original), 'fixed legacy importer source is a byte prefix of the new file')
    original = subprocess.run(['git', 'show', IMPORT_SOURCE + ':apps/reader/annotation-import/include/reader_annotation_import.h'], cwd=ROOT, capture_output=True, check=True).stdout
    expect((ROOT / 'apps/reader/annotation-import/include/reader_annotation_import.h').read_bytes() == original, 'legacy import header byte-identical')
    expect(subprocess.run(['git', 'diff', '--quiet', START, 'HEAD', '--', 'apps/reader/annotation-export/include/reader_annotation_export.h'], cwd=ROOT).returncode == 0,
           'legacy export header byte-identical')
    pdf = ROOT / 'tests/fixtures/pdf-public-text.pdf'
    expect(len(pdf.read_bytes()) == 8845 and sha(pdf) == PDF_SHA, 'same real PDF fixture')
    return pdf


def legacy_phase(name, exe, work):
    work.mkdir(parents=True)
    seed = probe(exe, 'legacy-seed', work, label=name + '-legacy-seed')
    expect(seed.exit == 0, name + ' legacy seed')
    key = 'txt:' + TXT_SHA
    export = probe(exe, 'old-export', 'legacy', work / 'legacy-sender.sqlite', key, work / 'legacy.jsonl', work / 'legacy.md', label=name + '-legacy-export')
    expect(export.status == EX_OK and export.stats[:2] == [2, 2], name + ' legacy export OK', export.text)
    recv = work / 'legacy-receiver.sqlite'
    expect(probe(exe, 'make-store', 'legacy', recv, work / 'books/legacy-txt.json').exit == 0, name + ' legacy receiver seeded')
    imported = probe(exe, 'old-import', 'legacy', recv, key, work / 'legacy.jsonl', label=name + '-legacy-import')
    expect(imported.status == 0 and imported.stats[:3] == [2, 2, 2], name + ' legacy import OK', imported.text)
    header = json.loads((work / 'legacy.jsonl').read_text(encoding='utf-8').split('\n')[0])
    expect(header['format'] == 'exreader-annotation-export' and header['format_version'] == 1 and header['module_version'] == '0.1.0'
           and 'source_bytes' not in header, name + ' legacy v1 header unchanged', header)
    return {'jsonl': sha(work / 'legacy.jsonl'), 'markdown': sha(work / 'legacy.md')}


def raw_phase(raw, off, pdf, work):
    work.mkdir(parents=True)
    out = work / 'out'
    out.mkdir()
    seed = probe(raw, 'raw-seed', pdf, work, label='raw-seed')
    expect(seed.exit == 0, 'raw seed from the real PDF through the explicit raw encoder')
    keys = dict(zip(['pdf', 'txt', 'ambiguous', 'pdf2'], seed.value('KEYS').split()))
    plan = {'pdf': (8845, {'annotations': 4, 'current': 3, 'tombstones': 1, 'pending_parents': 0, 'concurrent': 0, 'blocked_restore': 0, 'head_wires': 4}),
            'txt': (len(TXT_TEXT), {'annotations': 2, 'current': 2, 'tombstones': 0, 'head_wires': 2}),
            'ambiguous': (800, {'annotations': 1, 'current': 1, 'head_wires': 1}),
            'pdf2': (8845, {'annotations': 1, 'current': 1, 'head_wires': 1})}
    sender = work / 'sender.sqlite'
    before = dump(sender)
    heads = {}
    for name, (source_bytes, counts) in plan.items():
        exported = probe(raw, 'raw-export', 'raw', sender, keys[name], out / (name + '.jsonl'), out / (name + '.md'), 0, label='export-' + name)
        expect(exported.status == EX_OK and exported.stats[2:4] == [1, 1], 'raw3 export ' + name, exported.text)
        heads[name] = parse_export(out / (name + '.jsonl'), keys[name], source_bytes, counts)
    expect(dump(sender) == before, 'export left the sender store unchanged')
    # Normal records: source anchor 1/2/3, NULL / allocated-empty / NUL with byte lengths.
    versions = {h['location']['anchor_version'] for name in heads for _, h, _ in heads[name] if h['location']}
    expect(versions == {1, 2, 3}, 'source anchor versions 1, 2 and 3 are preserved', versions)
    by_annotation = {(n, a): h for n in heads for a, h, _ in heads[n]}
    null_head = by_annotation[('pdf', 'd' * 32)]
    expect(null_head['location']['exact'] == {'size': 0, 'base64': None}, 'typed NULL exact stays NULL')
    empty_head = by_annotation[('pdf2', 'e' * 32)]
    expect(all(empty_head['location'][s] == {'size': 0, 'base64': ''} for s in ('exact', 'prefix', 'suffix')), 'allocated empty stays allocated empty')
    point_head = by_annotation[('pdf', 'b' * 32)]
    suffix = base64.b64decode(point_head['location']['suffix']['base64'])
    expect(b'\0' in suffix and len(suffix) == point_head['location']['suffix']['size'], 'NUL selector bytes keep their byte length')
    expect(by_annotation[('txt', 'a' * 32)]['location']['anchor_version'] == 1 and by_annotation[('txt', 'b' * 32)]['location']['anchor_version'] == 2,
           'anchor1 and anchor2 sources keep their versions')
    expect(by_annotation[('pdf', 'f' * 32)]['operation'] == 'delete' and by_annotation[('pdf', 'f' * 32)]['location'] is None, 'tombstone head has no location')
    markdown = (out / 'pdf.md').read_text(encoding='utf-8') + (out / 'pdf2.md').read_text(encoding='utf-8')
    expect('NULL（无值）' in markdown and '已分配的空值' in markdown and '␀' in markdown and '\0' not in markdown, 'Markdown distinguishes NULL, empty and NUL')

    # Wrong-entry/mixed-store rejection, zero outputs.
    legacy_store = work / 'legacy-store.sqlite'
    expect(probe(off, 'make-store', 'legacy', legacy_store, work / 'books/txt.json').exit == 0, 'legacy store seeded for mixed-entry cases')
    old_on_raw = probe(raw, 'old-export', 'raw', sender, keys['pdf'], out / 'wrong-old.jsonl', out / 'wrong-old.md', label='old-export-on-raw')
    expect(old_on_raw.status == EX_ARGUMENT and old_on_raw.value('REVISION').split()[0] == '1' and not (out / 'wrong-old.jsonl').exists() and not (out / 'wrong-old.md').exists(), 'legacy export refuses a raw store with no output', old_on_raw.text)
    raw_on_old = probe(raw, 'raw-export', 'legacy', legacy_store, 'txt:' + TXT_SHA, out / 'wrong-raw.jsonl', '-', 0, label='raw-export-on-legacy')
    expect(raw_on_old.status == EX_ARGUMENT and raw_on_old.value('REVISION').split()[0] == '1' and not (out / 'wrong-raw.jsonl').exists(), 'raw export refuses a legacy store with no output', raw_on_old.text)
    tiny = probe(raw, 'raw-export', 'raw', sender, keys['pdf'], out / 'tiny.jsonl', '-', 100, label='export-budget')
    expect(tiny.status == EX_LIMIT and not (out / 'tiny.jsonl').exists(), 'output budget breach publishes nothing', tiny.text)
    legacy_file = work / 'legacy-format.jsonl'
    shutil.copyfile(work.parent / 'legacy-off/legacy.jsonl', legacy_file)
    raw_recv_txt = work / 'raw-recv-txt.sqlite'
    expect(probe(raw, 'make-store', 'raw', raw_recv_txt, work / 'books/txt.json').exit == 0, 'raw receiver for the txt book')
    d_txt = dump(raw_recv_txt)
    rejected = probe(raw, 'raw-import', 'raw', raw_recv_txt, 'txt:' + TXT_SHA, legacy_file, 'preview', 'verified', 0, 0, 0, '-', label='raw-import-legacy-file')
    expect(rejected.status == AI_FORMAT and dump(raw_recv_txt) == d_txt, 'raw importer refuses the legacy v1 file with zero writes', rejected.text)
    old_recv = work / 'old-recv.sqlite'
    expect(probe(raw, 'make-store', 'legacy', old_recv, work / 'books/txt.json').exit == 0, 'legacy receiver for the txt book')
    d_old = dump(old_recv)
    rejected = probe(raw, 'old-import', 'legacy', old_recv, 'txt:' + TXT_SHA, out / 'txt.jsonl', label='old-import-raw3-file')
    expect(rejected.status == AI_FORMAT and dump(old_recv) == d_old, 'legacy importer refuses the raw3 file with zero writes', rejected.text)
    rejected = probe(raw, 'old-import', 'raw', raw_recv_txt, 'txt:' + TXT_SHA, out / 'txt.jsonl', label='old-import-on-raw-store')
    expect(rejected.status == AI_REVISION and dump(raw_recv_txt) == d_txt, 'legacy importer refuses a raw store with zero writes', rejected.text)
    rejected = probe(raw, 'raw-import', 'legacy', old_recv, 'txt:' + TXT_SHA, out / 'txt.jsonl', 'preview', 'verified', 0, 0, 0, '-', label='raw-import-on-legacy-store')
    expect(rejected.status == AI_REVISION and dump(old_recv) == d_old, 'raw importer refuses a legacy store with zero writes', rejected.text)

    # Receivers: pdf book, resolved by the real public SDK.
    def receiver(name, book_files):
        path = work / f'recv-{name}.sqlite'
        expect(probe(raw, 'make-store', 'raw', path, *[work / 'books' / f for f in book_files]).exit == 0, 'raw receiver ' + name)
        return path

    pdf_recv = receiver('pdf', ['pdf.json'])
    base_dump = dump(pdf_recv)
    preview = probe(raw, 'raw-import', 'raw', pdf_recv, keys['pdf'], out / 'pdf.jsonl', 'preview', 'required', 0, 0, 0, pdf, label='pdf-preview')
    s = preview.stats
    expect(preview.status == AI_OK and s['validated'] == 1 and s['head_wires'] == 4 and s['found'] == 2 and s['unresolved'] == 0 and s['null_preserved'] == 1
           and s['would_create'] == 4 and s['would_duplicate'] == 0 and s['omitted'] == 4 and s['source_bytes'] == 8845 and s['found_checked'] == 1 and s['accepted'] == 0,
           'preview reports real public FOUND, NULL preserved, omitted history', preview.text)
    expect(dump(pdf_recv) == base_dump, 'preview writes nothing')
    fingerprint = s['fingerprint']
    for label, value in (('missing', 0), ('wrong', fingerprint ^ 1)):
        refused = probe(raw, 'raw-import', 'raw', pdf_recv, keys['pdf'], out / 'pdf.jsonl', 'commit', 'required', value, 0, 0, pdf, label='pdf-commit-' + label)
        expect(refused.status == AI_UNCONFIRMED and dump(pdf_recv) == base_dump, f'commit with {label} preview fingerprint is refused with zero writes', refused.text)
    cancelled = probe(raw, 'raw-import', 'raw', pdf_recv, keys['pdf'], out / 'pdf.jsonl', 'commit', 'required', fingerprint, 0, 2, pdf, label='pdf-commit-cancel')
    expect(cancelled.status == AI_CANCELLED and cancelled.stats['committed'] == 2 and cancelled.stats['next_index'] == 2 and len(cancelled.items) == 2,
           'cancel keeps earlier commits and reports next_index', cancelled.text)
    expect(len(revisions(pdf_recv)) == 3, 'only the two committed heads (plus the book) are stored after cancel')
    resumed = probe(raw, 'raw-import', 'raw', pdf_recv, keys['pdf'], out / 'pdf.jsonl', 'commit', 'required', fingerprint, 2, 0, pdf, label='pdf-commit-resume')
    expect(resumed.status == AI_OK and resumed.stats['committed'] == 2 and resumed.stats['created'] == 2, 'resume from next_index completes the import', resumed.text)
    stored = revisions(pdf_recv)
    expect(len(stored) == 5 and all(stored.get(h['revision_id']) == w for _, h, w in heads['pdf']),
           'receiver holds exactly the exported head bytes plus the book, no forged ancestor')
    expect([i['outcome'] for i in cancelled.items] == [3, 3] and [i['outcome'] for i in resumed.items] == [0, 3],
           'real receiving graph is reported per item (missing parents are not forged)', (cancelled.items, resumed.items))
    after = dump(pdf_recv)
    again = probe(raw, 'raw-import', 'raw', pdf_recv, keys['pdf'], out / 'pdf.jsonl', 'commit', 'required', fingerprint, 0, 0, pdf, label='pdf-commit-repeat')
    expect(again.status == AI_OK and again.stats['committed'] == 4 and again.stats['created'] == 0 and again.stats['duplicates'] == 4 and dump(pdf_recv) == after,
           'repeating the import is an exact duplicate with no history change', again.text)
    expect(all(v == 0 for v in outbox_rows(pdf_recv).values()), 'remote receive creates no outbox rows', outbox_rows(pdf_recv))
    null_wire = [w for a, h, w in heads['pdf'] if a == 'd' * 32][0]
    expect(stored.get(by_annotation[('pdf', 'd' * 32)]['revision_id']) == null_wire, 'typed NULL record stored byte-identical')

    # Negative files against the same receiver kind: every one is rejected with zero writes.
    negatives = work / 'negative'
    negatives.mkdir()
    fresh = receiver('neg', ['pdf.json'])
    clean = dump(fresh)
    text = (out / 'pdf.jsonl').read_text(encoding='utf-8')

    def reject(name, edit, status, source=None):
        path = negatives / (name.replace(' ', '-') + '.jsonl')
        if source:
            path.write_text(edit(Path(source).read_text(encoding='utf-8')), encoding='utf-8', newline='')
        else:
            mutate(out / 'pdf.jsonl', path, edit)
        result = probe(raw, 'raw-import', 'raw', fresh, keys['pdf'], path, 'preview', 'verified', 0, 0, 0, '-', label='negative-' + name.replace(' ', '-'))
        expect(result.status == status and dump(fresh) == clean, 'negative: ' + name + ' rejected with zero writes', result.text)
        commit = probe(raw, 'raw-import', 'raw', fresh, keys['pdf'], path, 'commit', 'verified', 1, 0, 0, '-', label='negative-commit-' + name.replace(' ', '-'))
        expect(commit.status != AI_OK and dump(fresh) == clean, 'negative commit: ' + name + ' writes nothing', commit.text)
    reject('unknown format version', lambda t: t.replace('"format_version":1', '"format_version":2', 1), AI_FORMAT)
    reject('unknown format name', lambda t: t.replace('exreader-annotation-export-raw3', 'exreader-annotation-export-raw4', 1), AI_FORMAT)
    reject('unknown module version', lambda t: t.replace('"module_version":"0.2.0"', '"module_version":"0.3.0"', 1), AI_FORMAT)
    reject('NULL changed to allocated empty', lambda t: t.replace('"exact":{"size":0,"base64":null}', '"exact":{"size":0,"base64":""}', 1), AI_FORMAT)
    reject('size changed', lambda t: t.replace('"suffix":{"size":', '"suffix":{"size":1', 1), AI_FORMAT)
    reject('wire edited keeps sha', lambda t: t.replace('point twice', 'point TWICE', 1), AI_REVISION)
    reject('sha changed', lambda t: t.replace('"sha256":"' + heads['pdf'][0][1]['sha256'][:8], '"sha256":"00000000', 1), AI_REVISION)
    reject('source bytes differ', lambda t: t.replace('"source_bytes":8845', '"source_bytes":8846', 1), AI_IDENTITY)
    reject('source bytes null', lambda t: t.replace('"source_bytes":8845', '"source_bytes":null', 1), AI_IDENTITY)
    reject('other book key', lambda t: t.replace('"book_key":"' + keys['pdf'] + '"', '"book_key":"' + keys['pdf2'] + '"', 1), AI_IDENTITY)
    reject('footer count', lambda t: t.replace('"head_wires":4', '"head_wires":5', 1), AI_FORMAT)
    reject('truncated before footer', lambda t: '\n'.join(t.split('\n')[:-2]) + '\n', AI_FORMAT)
    reject('trailing data after footer', lambda t: t + '{}\n', AI_FORMAT)
    reject('location of another head', lambda t: t.replace('"start":0,"end":0', '"start":1,"end":1', 1), AI_FORMAT)

    def anchor_four(t):
        rows = [json.loads(line) for line in t.split('\n')[:-1]]
        for row in rows:
            if row.get('type') == 'annotation':
                head = row['heads'][0]
                value = json.loads(head['wire'])
                if value['payload'] is None:
                    continue
                value['payload']['location']['anchor_version'] = 4
                wire = json.dumps(value, separators=(',', ':'), ensure_ascii=False)
                head['wire'], head['bytes'], head['sha256'] = wire, len(wire.encode()), hashlib.sha256(wire.encode()).hexdigest()
                break
        return '\n'.join(json.dumps(r, separators=(',', ':'), ensure_ascii=False) for r in rows) + '\n'
    reject('unknown source anchor version 4', anchor_four, AI_REVISION)
    # Existing ID with different bytes is found by whole-file preflight.
    collide = work / 'recv-collide.sqlite'
    first = heads['pdf'][0][1]
    altered = work / 'collide-wire.json'
    altered.write_text(first['wire'].replace('point twice', 'point TWICE'), encoding='utf-8', newline='')
    expect(probe(raw, 'make-store', 'raw', collide, work / 'books/pdf.json', altered).exit == 0, 'collision receiver seeded')
    state = dump(collide)
    collided = probe(raw, 'raw-import', 'raw', collide, keys['pdf'], out / 'pdf.jsonl', 'preview', 'verified', 0, 0, 0, '-', label='collision')
    expect(collided.status == AI_REVISION and dump(collide) == state, 'same ID with different bytes is rejected in preflight', collided.text)
    # Missing callback with the required policy.
    nodoc = probe(raw, 'raw-import', 'raw', fresh, keys['pdf'], out / 'pdf.jsonl', 'preview', 'required', 0, 0, 0, '-', label='required-no-document')
    expect(nodoc.status == AI_OK and nodoc.stats['found'] == 0 and nodoc.stats['unresolved'] == 2 and nodoc.stats['null_preserved'] == 1 and dump(fresh) == clean,
           'without a public document nothing is FOUND', nodoc.text)
    nocb = probe(raw, 'raw-import', 'raw', fresh, keys['pdf'], out / 'pdf.jsonl', 'preview', 'nocallback', 0, 0, 0, '-', label='required-no-callback')
    expect(nocb.status == AI_ARGUMENT and dump(fresh) == clean, 'required policy without a callback is refused', nocb.text)

    # Ambiguity: old offsets must not break it; public resolve says not FOUND, nothing written.
    amb_recv = receiver('ambiguous', ['ambiguous.json'])
    amb_state = dump(amb_recv)
    amb_preview = probe(raw, 'raw-import', 'raw', amb_recv, keys['ambiguous'], out / 'ambiguous.jsonl', 'preview', 'required', 0, 0, 0, pdf, label='ambiguous-preview')
    expect(amb_preview.status == AI_OK and amb_preview.stats['unresolved'] == 1 and amb_preview.stats['found'] == 0,
           'ambiguous reflow selector is not a public FOUND (offsets never break the tie)', amb_preview.text)
    amb_commit = probe(raw, 'raw-import', 'raw', amb_recv, keys['ambiguous'], out / 'ambiguous.jsonl', 'commit', 'required', amb_preview.stats['fingerprint'], 0, 0, pdf, label='ambiguous-commit')
    expect(amb_commit.status == AI_UNRESOLVED and dump(amb_recv) == amb_state, 'unresolved file commits nothing', amb_commit.text)

    # TXT book: source anchor1/anchor2 import with real FOUND.
    txt_recv = receiver('txt', ['txt.json'])
    txt_preview = probe(raw, 'raw-import', 'raw', txt_recv, keys['txt'], out / 'txt.jsonl', 'preview', 'required', 0, 0, 0, pdf, label='txt-preview')
    expect(txt_preview.status == AI_OK and txt_preview.stats['found'] == 2 and txt_preview.stats['unresolved'] == 0, 'anchor1 and anchor2 resolve FOUND through the public SDK', txt_preview.text)
    txt_commit = probe(raw, 'raw-import', 'raw', txt_recv, keys['txt'], out / 'txt.jsonl', 'commit', 'required', txt_preview.stats['fingerprint'], 0, 0, pdf, label='txt-commit')
    stored = revisions(txt_recv)
    expect(txt_commit.status == AI_OK and all(stored.get(h['revision_id']) == w for _, h, w in heads['txt']), 'anchor1/anchor2 heads stored byte-identical', txt_commit.text)

    # Allocated empty selectors: explicit host verification, never claimed as checked.
    empty_recv = receiver('pdf2', ['pdf2.json'])
    empty_preview = probe(raw, 'raw-import', 'raw', empty_recv, keys['pdf2'], out / 'pdf2.jsonl', 'preview', 'verified', 0, 0, 0, '-', label='pdf2-preview')
    expect(empty_preview.status == AI_OK and empty_preview.stats['found_checked'] == 0 and empty_preview.items[0]['found'] == 4, 'ALREADY_VERIFIED is reported as not checked', empty_preview.text)
    empty_commit = probe(raw, 'raw-import', 'raw', empty_recv, keys['pdf2'], out / 'pdf2.jsonl', 'commit', 'verified', empty_preview.stats['fingerprint'], 0, 0, '-', label='pdf2-commit')
    stored = revisions(empty_recv)
    expect(empty_commit.status == AI_OK and all(stored.get(h['revision_id']) == w for _, h, w in heads['pdf2']), 'allocated-empty head stored byte-identical', empty_commit.text)

    digests = {f'{name}.{kind}': sha(out / f'{name}.{kind}') for name in plan for kind in ('jsonl', 'md')}
    return digests, keys


def mac_phase(raw, work):
    sys.path.insert(0, str(ROOT / 'tests/apple_host/raw3/ios/reading'))
    import importlib.util
    spec = importlib.util.spec_from_file_location('c06_peer', ROOT / 'tests/apple_host/raw3/ios/reading/peer.py')
    peer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(peer)
    work.mkdir(parents=True)
    (work / 'peer-resources').mkdir()
    proof, wires, originals = peer.load(work / 'peer', work / 'peer-resources')
    source = work / 'peer/original-mac-operations.db'
    out = work / 'out'
    out.mkdir()
    summary = {'peer': {k: proof[k] for k in ('source_sha', 'run_id', 'attempt', 'artifact_id', 'zip_sha256', 'operations_database_sha256', 'null_revision_ids')}}
    totals = {'heads': 0, 'null_heads': 0, 'versions': set()}
    all_wires = revisions(source)
    null_kinds = sorted({json.loads(all_wires[r])['entity_kind'] for r in proof['null_revision_ids']})
    for index, book in enumerate(proof['book_keys']):
        # The exporter opens a disposable copy of the authenticated retained store.
        copy = work / f'export-{index}.db'
        shutil.copyfile(source, copy)
        for suffix in ('-wal', '-shm'):
            if Path(str(source) + suffix).exists():
                shutil.copyfile(str(source) + suffix, str(copy) + suffix)
        book_wires = {r: b for r, b in all_wires.items() if json.loads(b)['entity_kind'] == 'book' and json.loads(b)['entity_key'] == book}
        files = []
        for revision, body in sorted(book_wires.items()):
            file = work / f'book-{index}-{revision}.json'
            file.write_bytes(body)
            files.append(file)
        sizes = {json.loads(b)['payload']['source_bytes'] for b in book_wires.values() if json.loads(b)['operation'] != 'delete'}
        expect(len(sizes) == 1, 'real Mac book has one original byte length ' + book[:12], sizes)
        exported = probe(raw, 'raw-export', 'raw', copy, book, out / f'{index}.jsonl', out / f'{index}.md', 0, label=f'mac-export-{index}')
        expect(exported.status == EX_OK, f'real Mac records exported ({book[:12]})', exported.text)
        data = (out / f'{index}.jsonl').read_text(encoding='utf-8').split('\n')[:-1]
        rows = [json.loads(line) for line in data]
        heads = [(r['annotation_id'], h, h['wire'].encode()) for r in rows if r['type'] == 'annotation' for h in r['heads']]
        for _, h, wire in heads:
            expect(h['location'] == expected_location(h['wire']) and hashlib.sha256(wire).hexdigest() == h['sha256'], 'Mac record location independently equals its wire')
            if h['location']:
                totals['versions'].add(h['location']['anchor_version'])
                if h['location']['exact'] == {'size': 0, 'base64': None}:
                    totals['null_heads'] += 1
        totals['heads'] += len(heads)
        receiver_db = work / f'receiver-{index}.db'
        expect(probe(raw, 'make-store', 'raw', receiver_db, *files).exit == 0, 'Mac receiver seeded with the original book revisions')
        clean = dump(receiver_db)
        required = probe(raw, 'raw-import', 'raw', receiver_db, book, out / f'{index}.jsonl', 'preview', 'nocallback', 0, 0, 0, '-', label=f'mac-required-{index}')
        expect(required.status == AI_ARGUMENT and dump(receiver_db) == clean, 'required FOUND policy without a resolver is refused', required.text)
        preview = probe(raw, 'raw-import', 'raw', receiver_db, book, out / f'{index}.jsonl', 'preview', 'verified', 0, 0, 0, '-', label=f'mac-preview-{index}')
        expect(preview.status == AI_OK and preview.stats['found_checked'] == 0 and preview.stats['head_wires'] == len(heads), 'Mac preview validates the real records', preview.text)
        if heads:
            nul = mutate(out / f'{index}.jsonl', work / f'null-negative-{index}.jsonl', lambda t: t.replace('"base64":null', '"base64":""', 1)) \
                if any(h['location'] and h['location']['exact']['base64'] is None for _, h, _ in heads) else None
            if nul:
                bad = probe(raw, 'raw-import', 'raw', receiver_db, book, nul, 'preview', 'verified', 0, 0, 0, '-', label=f'mac-null-negative-{index}')
                expect(bad.status == AI_FORMAT and dump(receiver_db) == clean, 'real Mac NULL turned into empty is rejected with zero writes', bad.text)
        commit = probe(raw, 'raw-import', 'raw', receiver_db, book, out / f'{index}.jsonl', 'commit', 'verified', preview.stats['fingerprint'], 0, 0, '-', label=f'mac-commit-{index}')
        expect(commit.status == AI_OK, 'Mac records committed by explicit confirmation', commit.text)
        stored = revisions(receiver_db)
        expect(all(stored.get(h['revision_id']) == w for _, h, w in heads) and len(stored) == len(book_wires) + len(heads),
               'Mac head bytes round-trip exactly with no forged ancestor')
        summary.setdefault('books', []).append({'book': book, 'heads': len(heads), 'jsonl_sha256': sha(out / f'{index}.jsonl')})
    expect(totals['heads'] >= 1, 'real Mac annotation heads were exported', totals)
    if 'annotation' in null_kinds:
        expect(totals['null_heads'] >= 1, 'the real Mac typed NULL annotation is exported as NULL', totals)
    summary['totals'] = {'heads': totals['heads'], 'null_heads': totals['null_heads'], 'versions': sorted(totals['versions']), 'null_entity_kinds': null_kinds}
    return summary


def main():
    OUT.mkdir(parents=True)
    result = {'accepted': False, 'source_sha': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
              'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'platform': sys.platform, 'checks': CHECKS, 'failed': FAILED,
              'scope': 'explicit raw0.2 portable annotation export/import candidate; not adopted', 'adopted': False,
              'host_ui': False, 'physical_device': False, 'sdk_changed': False, 'schema_changed': False, 'legacy_default_kept': False,
              'unverified': ['FOUND of real Mac-origin records (no SDK documents for them: ALREADY_VERIFIED, found_checked=0)',
                             'Windows long paths, Apple/Android builds, performance, host UI']}
    try:
        pdf = guards()
        product = OUT / 'product-stage'
        build(ROOT / 'apps/reader/store/native', 'product', product)
        run(['cmake', '--preset', 'reading-library'], 'sdk-configure')
        run(['cmake', '--build', '--preset', 'reading-library'], 'sdk-build', 2400)
        run(['cmake', '--install', 'build/reading-library'], 'sdk-install')
        sdk = ROOT / 'build/reading-library/stage'
        core_off = core('core-off', False, product, sdk)
        core_raw = core('core-raw', True, product, sdk)
        original = archive(START, 'baseline-source', 'apps/reader/annotation-export')
        fixed_import = archive(IMPORT_SOURCE, 'fixed-import-source', 'apps/reader/annotation-import')
        baseline = modules('baseline', False, core_off, product, sdk, original / 'apps/reader/annotation-export', fixed_import / 'apps/reader/annotation-import')
        off = modules('off', False, core_off, product, sdk, ROOT / 'apps/reader/annotation-export', ROOT / 'apps/reader/annotation-import')
        raw = modules('raw', True, core_raw, product, sdk, ROOT / 'apps/reader/annotation-export', ROOT / 'apps/reader/annotation-import')
        exes = {
            'baseline': consumer('baseline-consumer', False, baseline, core_off, product, sdk),
            'off': consumer('off-consumer', False, off, core_off, product, sdk),
            'raw': consumer('raw-consumer', True, raw, core_raw, product, sdk)}
        consumer_dir = ROOT / 'tests/reader_next_c06/consumer'
        expect(refused_configure(consumer_dir, 'mixed-raw-consumer-on-legacy-install', ['-DC06_RAW=ON', paths(off, core_off, product, sdk)]), 'raw consumer refuses the legacy install at configure time')
        expect(refused_configure(consumer_dir, 'mixed-legacy-consumer-on-raw-install', ['-DC06_RAW=OFF', paths(raw, core_raw, product, sdk)]), 'legacy consumer refuses the raw install at configure time')
        expect(refused_configure(ROOT / 'apps/reader/annotation-export', 'mixed-raw-export-on-legacy-core',
                                 ['-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON', paths(core_off, product, sdk)]), 'raw export refuses legacy revisions/reading-state')
        expect(refused_configure(ROOT / 'apps/reader/annotation-import', 'mixed-legacy-import-on-raw-core',
                                 ['-DREADER_ANNOTATION_IMPORT_BUILD=ON', paths(core_raw, product, sdk)]), 'legacy import refuses raw revisions')
        # Default family: installed headers and library surface unchanged.
        for header in ('reader_annotation_export.h', 'reader_annotation_import.h'):
            expect((baseline / 'include' / header).read_bytes() == (off / 'include' / header).read_bytes(), 'default installed header byte-identical ' + header)
        expect(not (off / 'include/reader_annotation_export_raw3.h').exists() and not (off / 'include/reader_annotation_import_raw3.h').exists(), 'default install has no raw3 header')
        for lib in (off / 'lib').glob('*annotation*'):
            blob = lib.read_bytes()
            hits = {n.decode(): blob.count(n) for n in (b'reader_annotation_export_raw3_run', b'reader_annotation_import_raw3_run', b'reader_revision_get_raw_v3',
                                                        b'reader_rs_decode_raw_v3', b'reader_revision_heads_raw_v3', b'exreader-annotation-export-raw3')}
            loose = {n.decode(): [blob[max(0, i - 40):i + 40] for i in [blob.find(n)]] for n in (b'raw3', b'_raw_v3') if n in blob}
            result.setdefault('default_library_loose_matches', {})[lib.name] = {k: repr(v) for k, v in loose.items()}
            expect(not any(hits.values()), 'default library has no raw symbols ' + lib.name, hits)
        hashes = {name: legacy_phase(name, exe, OUT / (f'legacy-{name}')) for name, exe in exes.items()}
        expect(hashes['baseline'] == hashes['off'] == hashes['raw'], 'legacy export bytes identical in baseline, default and raw-enabled builds', hashes)
        digests, keys = raw_phase(exes['raw'], exes['off'], pdf, OUT / 'raw')
        result.update(legacy_outputs=hashes['off'], raw_outputs=digests, raw_keys=keys, legacy_default_kept=True)
        if os.environ.get('GH_TOKEN'):
            result['mac_records'] = mac_phase(exes['raw'], OUT / 'mac')
        else:
            expect(False, 'GH_TOKEN present for the certified Mac records')
        result['consumers'] = {name: sha(exe) for name, exe in exes.items()}
        result['logs'] = {p.name: sha(p) for p in OUT.glob('*.log')}
        result['accepted'] = not FAILED
    except BaseException:
        result['error'] = traceback.format_exc()
        print(result['error'], flush=True)
        raise
    finally:
        result['count'] = len(CHECKS)
        (OUT / 'result.json').write_text(json.dumps(result, indent=2, default=list) + '\n', encoding='utf-8')
        print(json.dumps({k: v for k, v in result.items() if k != 'checks'}, default=list), flush=True)


if __name__ == '__main__':
    main()
