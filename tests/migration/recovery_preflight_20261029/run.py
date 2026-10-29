#!/usr/bin/env python3
"""Actions-only independent oracle and native process/permission calibration."""
import argparse
import contextlib
import csv
import ctypes
from ctypes import wintypes
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import struct
import subprocess
import sys
import time
import traceback

if os.environ.get('GITHUB_ACTIONS') != 'true':
    raise SystemExit('Builds, tests, fixtures and artifact parsing are Actions-only.')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import legacy_data as L

CAPTURE_PHASES = ('owner-held', 'reader-held', 'backup-closed', 'reader-closed',
                  'clone-sdk-closed', 'baseline-durable', 'intent-durable',
                  'mirror-published', 'mutation-held', 'owner-finished')
VERIFY_PHASES = ('verify-held', 'compared', 'decision-durable')


def typed(value):
    """Independent specification: type byte + LE u64 length + exact payload."""
    if value is None:
        tag, payload = b'N', b''
    elif isinstance(value, int):
        tag, payload = b'I', struct.pack('<q', value)
    elif isinstance(value, float):
        assert math.isfinite(value)
        tag, payload = b'F', struct.pack('<d', value)
    elif isinstance(value, str):
        tag, payload = b'T', value.encode('utf-8')
    elif isinstance(value, bytes):
        tag, payload = b'B', value
    else:
        raise AssertionError(type(value))
    return tag + struct.pack('<Q', len(payload)) + payload


def query_frame(label, columns, rows):
    label = label.encode('utf-8')
    return (b'Q' + struct.pack('<Q', len(label)) + label + struct.pack('<Q', columns) +
            b''.join(b'R' + b''.join(typed(v) for v in row) for row in rows) + b'E')


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def connect(path, write=False):
    db = sqlite3.connect(path.resolve().as_uri() + ('?mode=rw' if write else '?mode=ro'),
                         uri=True, timeout=0)
    db.execute('PRAGMA read_uncommitted=OFF')
    db.execute('PRAGMA trusted_schema=OFF')
    return db


def catalog_bytes(db):
    rows = db.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type COLLATE BINARY,name COLLATE BINARY').fetchall()
    return query_frame('catalog', 4, rows)


def canonical(db):
    def q(label, sql):
        cur = db.execute(sql)
        return query_frame(label, len(cur.description), cur.fetchall())
    result = b'EXRPF1\n'
    for key in ('application_id', 'user_version', 'encoding'):
        result += q(key, 'PRAGMA ' + key)
    result += catalog_bytes(db)
    tables = [x[0] for x in db.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name COLLATE BINARY")]
    for name in tables:
        result += q('xinfo:' + name, 'PRAGMA table_xinfo(' + quote(name) + ')')
        result += q('indexes:' + name, 'PRAGMA index_list(' + quote(name) + ')')
        result += q('fk:' + name, 'PRAGMA foreign_key_list(' + quote(name) + ')')
        indexes = sorted(x[1] for x in db.execute('PRAGMA index_list(' + quote(name) + ')'))
        for index in indexes:
            result += q('index-xinfo:' + index, 'PRAGMA index_xinfo(' + quote(index) + ')')
        result += q('rows:' + name, 'SELECT _rowid_,* FROM ' + quote(name) + ' ORDER BY _rowid_')
    return result


def read_state(path):
    with contextlib.closing(connect(path)) as db:
        db.execute('BEGIN')
        assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        return canonical(db)


def public_projection(db):
    """Independent expected public values, derived before the SDK owner starts.

    This applies the documented getter projection (including unresolved note
    ranges), not the SDK's getter implementation or a later unbound target read.
    """
    result = []
    tables = {x[0] for x in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
    for row in db.execute('SELECT id,format,title,author,tags,favorite,status,position,source,cover FROM books ORDER BY id DESC'):
        book,fmt,title,author,tags,favorite,status,position,source,cover = row
        result.append(['book',book,fmt,title,author,tags,favorite,status,position])
        for kind,blob in (('source',source),('cover',cover or b'')):
            result.append([kind,book,len(blob),hashlib.sha256(blob).hexdigest()])
        for note in db.execute('SELECT id,start,end,text,anchor_exact,anchor_prefix,anchor_suffix,anchor_chapter,location_state FROM notes WHERE book_id=? ORDER BY start,id',(book,)):
            nid,start,end,text,exact,prefix,suffix,chapter,state = note
            result.append(['note',nid,book,start if state == 1 else -1,end if state == 1 else -1,
                           text,start,end,exact,prefix,suffix,chapter])
        if fmt in (1,4):
            stored = db.execute('SELECT position,state,prefix,suffix,chapter FROM book_progress WHERE book_id=?',(book,)).fetchone()
            if stored:
                pos,state,prefix,suffix,chapter = stored
                result.append(['progress',book,state,pos,pos,None if state == 3 else '',prefix,suffix,chapter])
            else:
                result.append(['progress',book,3,position,position,None,None,None,None])
        if fmt == 4:
            bounded = int('epub_bounded_books' in tables and db.execute('SELECT 1 FROM epub_bounded_books WHERE book_id=?',(book,)).fetchone() is not None)
            result.append(['epub-info',book,bounded,1-bounded])
            stored = db.execute('SELECT part,path,position,prefix,suffix,chapter FROM epub_progress WHERE book_id=?',(book,)).fetchone() if 'epub_progress' in tables else None
            if stored:
                part,path,pos,prefix,suffix,chapter = stored
                result.append(['epub-progress',book,1,part,path,pos,pos,'',prefix,suffix,chapter])
            else:
                result.append(['epub-progress',book,0])
            if 'epub_notes' in tables:
                for note in db.execute('SELECT id,part,path,start,end,exact,prefix,suffix,chapter,text FROM epub_notes WHERE book_id=? ORDER BY part,start,id',(book,)):
                    nid,part,path,start,end,exact,prefix,suffix,chapter,text = note
                    result.append(['epub-note',nid,book,part,path,start,end,exact,prefix,suffix,chapter,text])
        if fmt in (8,9):
            for note in db.execute('SELECT id,page,start,end,text,page_id,exact,prefix,suffix FROM fixed_notes WHERE book_id=? ORDER BY page,start,id',(book,)):
                nid,page,start,end,text,page_id,exact,prefix,suffix = note
                result.append(['fixed-note',nid,book,page,start,end,text,start,end,page_id,exact.hex(),prefix.hex(),suffix.hex()])
    keys = [x[0] for x in db.execute('SELECT audio_id FROM audio_resume UNION SELECT audio_id FROM audio_marks ORDER BY audio_id')]
    for key in keys:
        stored = db.execute('SELECT track_id,offset,rate FROM audio_resume WHERE audio_id=?',(key,)).fetchone()
        result.append(['audio-resume',key,1,stored[0],int.from_bytes(stored[1],'little'),float(stored[2])] if stored else ['audio-resume',key,0])
        for mark in db.execute('SELECT id,label,track_id,offset,rate FROM audio_marks WHERE audio_id=? ORDER BY id',(key,)):
            mid,label,track,offset,rate = mark
            result.append(['audio-mark',key,mid,label,track,int.from_bytes(offset,'little'),float(rate)])
    return result


def identity(path):
    s = path.lstat()
    return s.st_dev, s.st_ino


def file_state(path):
    return identity(path), hashlib.sha256(path.read_bytes()).hexdigest()


class Child:
    def __init__(self, command, logbase):
        self.out_path = Path(str(logbase) + '.stdout.txt')
        self.err_path = Path(str(logbase) + '.stderr.txt')
        self.out = self.out_path.open('w', encoding='utf-8')
        self.err = self.err_path.open('w', encoding='utf-8')
        self.p = subprocess.Popen(command, stdout=self.out, stderr=self.err,
                                  close_fds=True, env=dict(os.environ, EXR_MIGRATE_TEST_FAULTS='1'))

    def wait(self, root, phase):
        marker = root / (phase + '.ready')
        until = time.monotonic() + 35
        while not marker.exists() and self.p.poll() is None and time.monotonic() < until:
            time.sleep(.02)
        assert marker.exists(), ('missing calibrated phase', phase, self.p.poll(), self.err_path)

    def go(self, root, phase):
        (root / (phase + '.go')).write_bytes(b'continue\n')

    def finish(self, kill=False):
        errors = []
        try:
            if kill and self.p.poll() is None:
                self.p.kill()
            self.p.wait(timeout=40)
        except Exception as error:
            errors.append(repr(error))
            try:
                self.p.kill()
                self.p.wait(timeout=10)
            except Exception as cleanup:
                errors.append(repr(cleanup))
        finally:
            for stream in (self.out, self.err):
                try:
                    stream.close()
                except Exception as cleanup:
                    errors.append(repr(cleanup))
        assert not errors, errors
        return self.p.returncode

    def report(self):
        return json.loads(self.out_path.read_text(encoding='utf-8'))


def windows_api():
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    api.CreateFileW.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    return api


@contextlib.contextmanager
def deny_delete(path):
    """Calibrate actual owned-name refusal before SDK finish."""
    release = None
    if os.name == 'nt':
        api = windows_api()
        h = api.CreateFileW(str(path.resolve()), 0x80000000, 1 | 2, None, 3, 0x00200000, None)
        assert h != ctypes.c_void_p(-1).value, ctypes.get_last_error()
        release = lambda: api.CloseHandle(h)
        try:
            probe = api.CreateFileW(str(path.resolve()), 0x00010000, 1 | 2 | 4, None, 3, 0x00200000, None)
            error = ctypes.get_last_error()
            if probe != ctypes.c_void_p(-1).value:
                api.CloseHandle(probe)
                raise AssertionError('DELETE access unexpectedly succeeded')
            assert error == 32, error
            yield {'mechanism': 'journal no-delete-share', 'native_error': error}
        finally:
            assert release(), 'release native journal handle'
    else:
        folder = path.parent
        original = stat.S_IMODE(folder.stat().st_mode)
        marker = folder / 'native-delete-calibration'
        marker.write_bytes(b'owned disposable file')
        try:
            folder.chmod(original & ~0o222)
            try:
                marker.unlink()
                raise AssertionError('unlink denial did not calibrate')
            except PermissionError as error:
                assert error.errno == 13
                yield {'mechanism': 'parent directory write refusal', 'native_error': error.errno}
        finally:
            folder.chmod(original)


@contextlib.contextmanager
def deny_windows_page1(path):
    api = windows_api()
    class OVERLAPPED(ctypes.Structure):
        _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                    ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD), ('hEvent', wintypes.HANDLE)]
    api.LockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(OVERLAPPED)]
    api.LockFileEx.restype = wintypes.BOOL
    api.UnlockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(OVERLAPPED)]
    api.UnlockFileEx.restype = wintypes.BOOL
    api.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    api.ReadFile.restype = wintypes.BOOL
    handle = api.CreateFileW(str(path.resolve()), 0x80000000 | 0x40000000, 1 | 2 | 4, None, 3, 0, None)
    assert handle != ctypes.c_void_p(-1).value
    overlap = OVERLAPPED()
    locked = False
    second = None
    try:
        assert api.LockFileEx(handle, 3, 0, 4096, 0, ctypes.byref(overlap)), ctypes.get_last_error()
        locked = True
        second = api.CreateFileW(str(path.resolve()), 0x80000000, 1 | 2 | 4, None, 3, 0, None)
        assert second != ctypes.c_void_p(-1).value
        buffer = ctypes.create_string_buffer(16)
        count = wintypes.DWORD()
        assert not api.ReadFile(second, buffer, 16, ctypes.byref(count), None)
        error = ctypes.get_last_error()
        assert error == 33, error
        yield {'mechanism': 'main database page1 byte-range read refusal', 'native_error': error,
               'consumer_mmap': 0, 'scope': 'fresh public SQLite verifier, not SDK rollback attribution'}
    finally:
        errors = []
        if second not in (None, ctypes.c_void_p(-1).value) and not api.CloseHandle(second):
            errors.append('close calibration reader')
        if locked and not api.UnlockFileEx(handle, 0, 4096, 0, ctypes.byref(overlap)):
            errors.append('unlock page1')
        if not api.CloseHandle(handle):
            errors.append('close lock owner')
        assert not errors, errors


@contextlib.contextmanager
def deny_evidence_read(path):
    if os.name == 'nt':
        api = windows_api()
        handle = api.CreateFileW(str(path.resolve()), 0x80000000, 2 | 4, None, 3, 0x00200000, None)
        assert handle != ctypes.c_void_p(-1).value
        try:
            try:
                path.read_bytes()
                raise AssertionError('read refusal was not calibrated')
            except PermissionError as error:
                yield {'mechanism': 'evidence no-share-read', 'native_error': error.winerror}
        finally:
            assert api.CloseHandle(handle)
    else:
        permissions = stat.S_IMODE(path.stat().st_mode)
        try:
            path.chmod(0)
            try:
                path.read_bytes()
                raise AssertionError('read refusal was not calibrated')
            except PermissionError as error:
                assert error.errno == 13
                yield {'mechanism': 'evidence read permission', 'native_error': 13}
        finally:
            path.chmod(permissions)


@contextlib.contextmanager
def deny_decision_create(root):
    """Only this new test-owned directory; ready/go already exist beforehand."""
    if os.name == 'nt':
        who = subprocess.run(['whoami','/user','/fo','csv','/nh'], capture_output=True, text=True, check=True)
        sid = next(csv.reader([who.stdout.strip()]))[1]
        applied = False
        try:
            p = subprocess.run(['icacls',str(root),'/deny','*' + sid + ':(WD)'], capture_output=True, text=True)
            applied = True
            assert p.returncode == 0, p.stdout + p.stderr
            try:
                (root / 'calibration-new-file').write_bytes(b'x')
                raise AssertionError('directory create refusal not calibrated')
            except PermissionError as error:
                yield {'mechanism': 'directory FILE_ADD_FILE denial', 'native_error': error.winerror}
        finally:
            if applied:
                restored = subprocess.run(['icacls',str(root),'/remove:d','*' + sid], capture_output=True, text=True)
                assert restored.returncode == 0, restored.stdout + restored.stderr
    else:
        permissions = stat.S_IMODE(root.stat().st_mode)
        try:
            root.chmod(permissions & ~0o222)
            try:
                (root / 'calibration-new-file').write_bytes(b'x')
                raise AssertionError('directory create refusal not calibrated')
            except PermissionError as error:
                assert error.errno == 13
                yield {'mechanism': 'directory create permission', 'native_error': 13}
        finally:
            root.chmod(permissions)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--probe', required=True)
    ap.add_argument('--tool', required=True)
    ap.add_argument('--old-tool', required=True)
    ap.add_argument('--work', type=Path, required=True)
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=False)
    logs = a.work / 'logs'
    logs.mkdir()
    cases = []
    serial = 0
    evidence = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
                'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': os.environ['RUNNER_OS'],
                'cases': cases, 'passed': False, 'product_admission': False, 'full_p0_acceptance': False,
                'scope': 'test-only current supported-baseline parity under calibrated writer fence',
                'limitations': ['trusted directory custody is not cryptographic authentication',
                                'no product evidence retirement', 'no historical COMMIT/rollback proof',
                                'no universal power-loss or hostile-namespace guarantee',
                                'bounded EPUB application traversal refuses, not qualified',
                                'non-Windows WAL physical read fault not covered',
                                'spill control is explicit real SDK ledger write, not a naturally occurring schema upgrade']}

    def command(mode, target, root, cat, fault='none'):
        return [a.probe, mode, str(target), str(root), str(cat), root.parent.name, fault, 'qualification-only']

    def spawn(mode, target, root, cat, fault='none'):
        nonlocal serial
        serial += 1
        return Child(command(mode, target, root, cat, fault), logs / ('%04d-%s-%s' % (serial, root.parent.name, mode)))

    def simple(mode, target, root, cat, fault='none'):
        child = spawn(mode, target, root, cat, fault)
        rc = child.finish()
        return rc, child.report()

    def writer(target, root, cat, busy):
        rc, report = simple('writer', target, root, cat)
        assert (rc == 3 and report['sqlite_extended_code'] & 255 == 5) if busy else rc == 0, report
        mutex = root / 'migration.mutex'
        if mutex.exists():
            before = file_state(mutex)
            try:
                with mutex.open('xb') as f:
                    f.write(b'competing sidecar writer')
                raise AssertionError('cooperative exclusive mutex unexpectedly acquired')
            except FileExistsError:
                pass
            assert file_state(mutex) == before
            report['cooperative_sidecar_exclusive_create_refused'] = True
        return report

    def clear_signals(root):
        for phase in CAPTURE_PHASES + VERIFY_PHASES:
            for suffix in ('.ready', '.go'):
                (root / (phase + suffix)).unlink(missing_ok=True)

    def seed(folder, schema=7, journal='delete'):
        target, pack = folder / 'library.sqlite', folder / 'seed.exrpack'
        entries, notes = L.dataset()
        pack.write_bytes(L.build_pack(entries, notes))
        # The unchanged full legacy fixture deliberately includes an unstorable
        # audio original. Like the original full() producer, opt in explicitly;
        # do not silently remove the audio/orphan or accept arbitrary partials.
        child = Child([a.old_tool if schema == 6 else a.tool, 'migrate', '--target', str(target), '--pack', str(pack), '--allow-partial'], logs / (folder.name + '-seed'))
        assert child.finish() == 0, child.out_path.read_text(encoding='utf-8')
        report = child.report()
        assert (report['result'], report['code']) == ('success', 'ok'), report
        assert report['pack']['sha256'] == hashlib.sha256(pack.read_bytes()).hexdigest()
        expected_counts = {
            'books_expected': 5, 'books_created': 4, 'books_existing': 0,
            'books_merged': 0, 'books_skipped': 0,
            'books_audio_positions_only': 1, 'books_accounted': 5,
            'notes_expected': 16, 'notes_created': 10, 'notes_existing': 0,
            'notes_unlocated': 6, 'notes_skipped': 0, 'notes_accounted': 16,
        }
        assert {k: report['counts'][k] for k in expected_counts} == expected_counts, report
        assert report['counts']['entries'] == {
            'info': 4, 'warning': 1, 'approximate': 2, 'unlocated': 6,
            'dropped': 1, 'unsupported': 1, 'conflict': 0,
        }, report
        unsupported = [(e['code'], e['scope'], e['legacy_id']) for e in report['entries'] if e['severity'] == 'unsupported']
        assert unsupported == [('audio-original-not-storable', 'book', 'b-audio')], report
        assert not [e for e in report['entries'] if e['severity'] == 'conflict'], report
        expected_unlocated = {
            'n-txt-ambiguous': 'quote-ambiguous',
            'n-txt-missing': 'quote-not-found',
            'n-txt-bookmark': 'bookmark-without-cfi',
            'n-epub-ambiguous': 'quote-ambiguous',
            'n-pdf-missing': 'quote-not-found', 'n-orphan': 'orphan-note',
        }
        assert {n['legacy_id']: n['reason'] for n in report['notes'] if n['status'] == 'unlocated'} == expected_unlocated, report
        assert {b['legacy_id']: b['status'] for b in report['items']} == {
            'b-txt': 'created', 'b-epub': 'created', 'b-pdf': 'created',
            'b-cbz': 'created', 'b-audio': 'audio-positions-only',
        }, report
        ledger = json.loads(Path(str(target) + '.legacy-map.json').read_text(encoding='utf-8'))
        assert ledger['format'] == 'exreader-legacy-map' and ledger['version'] == 1
        assert ledger['packs'] == [report['pack']['sha256']]
        assert len(ledger['books']) == 5 and len(ledger['notes']) == 16
        # Frozen producer deliberately stores the cover separately, not in raw
        # book JSON. Its public cover bytes remain covered by clone projection.
        assert {b['legacy_id']: b['retained'] for b in ledger['books']} == {
            b['legacy_id']: {k: v for k, v in b['record'].items() if k != 'cover'} for b in entries
        }
        assert {n['legacy_id']: n['retained'] for n in ledger['notes']} == {n['id']: n for n in notes}
        assert {n['legacy_id']: n['reason'] for n in ledger['notes'] if not n['located']} == expected_unlocated
        (folder / 'seed-admission.json').write_text(json.dumps({
            'explicit_allow_partial': True, 'known_unsupported': unsupported,
            'expected_unlocated': expected_unlocated, 'counts': report['counts'],
            'all_original_records_retained_except_separately_stored_cover': True,
            'pack_sha256': report['pack']['sha256'],
            'recovery_qualification': False,
        }, indent=2) + '\n')
        root = folder / 'protocol'
        root.mkdir()
        cat = folder / 'catalog.bin'
        with contextlib.closing(connect(target, True)) as db:
            assert db.execute('PRAGMA user_version').fetchone()[0] == schema
            assert db.execute('PRAGMA journal_mode=' + journal).fetchone()[0] == journal
            db.execute('PRAGMA wal_autocheckpoint=0')
            db.commit()
            cat.write_bytes(catalog_bytes(db))
        return target, pack, root, cat

    @contextlib.contextmanager
    def wal_pin(target):
        old, writer_db = connect(target), connect(target, True)
        try:
            writer_db.execute('PRAGMA wal_autocheckpoint=0')
            writer_db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            old.execute('BEGIN')
            prior = old.execute('SELECT title FROM books WHERE id=1').fetchone()[0]
            writer_db.execute("UPDATE books SET title='uncheckpointed-committed-canary' WHERE id=1")
            writer_db.commit()
            assert old.execute('SELECT title FROM books WHERE id=1').fetchone()[0] == prior
            telemetry = writer_db.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchone()
            assert telemetry[1] > telemetry[2] >= 0, telemetry
            blocked = writer_db.execute('PRAGMA wal_checkpoint(FULL)').fetchone()
            assert blocked[0] == 1 and blocked[1] > blocked[2], blocked
            with contextlib.closing(connect(target)) as fresh:
                assert fresh.execute('SELECT title FROM books WHERE id=1').fetchone()[0] == 'uncheckpointed-committed-canary'
            yield {'passive': telemetry, 'blocked_full': blocked, 'old_snapshot_title': prior}, writer_db
        finally:
            old.close()
            writer_db.close()

    def clone_validation(target, root, original_rows, original_catalog, schema):
        expected_additions = {
            ('table','epub_bounded_books','epub_bounded_books','CREATE TABLE epub_bounded_books(book_id INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE)'),
            ('table','epub_progress','epub_progress','CREATE TABLE epub_progress(book_id INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,part INTEGER NOT NULL CHECK(part>=0 AND part<10000),path TEXT NOT NULL,position INTEGER NOT NULL CHECK(position>=0),prefix TEXT,suffix TEXT,chapter TEXT)'),
            ('table','epub_notes','epub_notes','CREATE TABLE epub_notes(id INTEGER PRIMARY KEY,book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,part INTEGER NOT NULL CHECK(part>=0 AND part<10000),path TEXT NOT NULL,start INTEGER NOT NULL CHECK(start>=0),end INTEGER NOT NULL CHECK(end>start),exact TEXT NOT NULL,prefix TEXT,suffix TEXT,chapter TEXT,text TEXT NOT NULL)'),
            ('index','epub_notes_book','epub_notes','CREATE INDEX epub_notes_book ON epub_notes(book_id,part,start,id)'),
        }
        with contextlib.closing(connect(root / 'clone.sqlite')) as clone:
            assert clone.execute('PRAGMA user_version').fetchone()[0] == 7
            assert clone.execute('PRAGMA application_id').fetchone()[0] == 1163416131
            actual_catalog = set(clone.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema'))
            assert actual_catalog == original_catalog | (expected_additions if schema == 6 else set())
            names = {x[0] for x in clone.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
            for name, rows in original_rows.items():
                cur = clone.execute('SELECT _rowid_,* FROM ' + quote(name) + ' ORDER BY _rowid_')
                assert query_frame(name, len(cur.description), cur.fetchall()) == query_frame(name, len(cur.description), rows), name
            assert names - set(original_rows) == ({'epub_bounded_books', 'epub_progress', 'epub_notes'} if schema == 6 else set())
            assert clone.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
            assert not clone.execute('PRAGMA foreign_key_check').fetchall()

    def capture(folder, target, root, cat, schema, kill_at=None, native=False, spill=False, checkpoint=None):
        with contextlib.closing(connect(target)) as initial:
            initial.execute('BEGIN')
            expected = canonical(initial)
            rows = {name: initial.execute('SELECT _rowid_,* FROM ' + quote(name) + ' ORDER BY _rowid_').fetchall()
                    for (name,) in initial.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
            original_catalog = set(initial.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema'))
            expected_projection = public_projection(initial)
        (folder / 'expected-public-projection.json').write_text(json.dumps(expected_projection,indent=2)+'\n',encoding='utf-8')
        before_id = identity(target)
        child = spawn('capture', target, root, cat, 'spill' if spill else 'none')
        native_record = None
        try:
            for phase in CAPTURE_PHASES:
                if spill and phase == 'reader-held':
                    rc = child.finish()
                    report = child.report()
                    assert rc == 3 and report['sqlite_extended_code'] & 255 == 5, report
                    assert not (root / 'baseline.bin').exists() and not (root / 'intent.json').exists()
                    return {'real_sdk_spill_reader_busy': True, 'natural_upgrade_spill_claimed': False, 'report': report}
                child.wait(root, phase)
                if checkpoint: checkpoint('capture:' + phase)
                if phase in ('owner-held', 'reader-held', 'backup-closed', 'reader-closed', 'clone-sdk-closed'):
                    writer(target, root, cat, True)
                if phase == 'clone-sdk-closed':
                    clone_validation(target, root, rows, original_catalog, schema)
                    projection = [json.loads(line) for line in (root / 'public-projection.jsonl').read_text(encoding='utf-8').splitlines()]
                    assert projection == expected_projection, 'public value/order projection differs from pre-owner fixture'
                    assert read_state(target) == expected and identity(target) == before_id
                if phase == 'baseline-durable':
                    assert (root / 'baseline.bin').read_bytes() == expected
                if phase == kill_at:
                    child.finish(kill=True)
                    return {'killed_after': phase, 'expected': expected.hex(), 'target_identity': before_id}
                if phase == 'mutation-held' and native:
                    journal = Path(str(target) + '-journal')
                    assert journal.stat().st_size > 0
                    with deny_delete(journal) as calibration:
                        native_record = dict(calibration)
                        child.go(root, phase)
                        child.wait(root, 'owner-finished')
                        native_record['journal_after_finish'] = {'present': journal.exists(), 'size': journal.stat().st_size if journal.exists() else None}
                        child.go(root, 'owner-finished')
                        rc = child.finish()
                    break
                if phase == 'owner-finished':
                    writer(target, root, cat, False)
                child.go(root, phase)
            else:
                rc = child.finish()
            report = child.report()
            assert rc == 0 and report['sdk_status'] == 0, report
            assert read_state(target) == expected and identity(target) == before_id
            return {'captured': True, 'report': report, 'native': native_record,
                    'independent_typed_baseline_match': True, 'snapshot_bound_clone_checked': True}
        finally:
            child.finish(kill=child.p.poll() is None)

    def verify(target, root, cat, expect=True, kill_at=None, before_go=None, fault='none', checkpoint=None):
        clear_signals(root)
        child = spawn('verify', target, root, cat, fault)
        try:
            for phase in VERIFY_PHASES:
                if not expect:
                    # Refusal may occur before acquiring a DB owner or after read.
                    until = time.monotonic() + 35
                    while child.p.poll() is None and not (root / (phase + '.ready')).exists() and time.monotonic() < until:
                        time.sleep(.02)
                    if child.p.poll() is not None:
                        break
                child.wait(root, phase)
                if checkpoint: checkpoint('verify:' + phase)
                writer(target, root, cat, True)
                if before_go:
                    before_go(phase)
                if kill_at == phase:
                    child.finish(kill=True)
                    return {'killed_after': phase}
                child.go(root, phase)
            rc = child.finish()
            report = child.report()
            assert (rc == 0) == expect, report
            assert not report['product_admission'] and not report['historical_outcome_proved']
            return report
        finally:
            child.finish(kill=child.p.poll() is None)

    def main_case(folder, schema, journal):
        target, pack, root, cat = seed(folder, schema, journal)
        if journal == 'wal':
            with wal_pin(target) as (telemetry, checkpointer):
                pressure = []
                def checkpoint(phase):
                    passive = checkpointer.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchone()
                    full = checkpointer.execute('PRAGMA wal_checkpoint(FULL)').fetchone()
                    assert passive[1] > passive[2] >= 0 and full[0] == 1 and full[1] > full[2], (phase,passive,full)
                    with contextlib.closing(connect(target)) as fresh:
                        assert fresh.execute('SELECT title FROM books WHERE id=1').fetchone()[0] == 'uncheckpointed-committed-canary'
                    pressure.append({'phase':phase,'passive':passive,'full':full,'fresh_canary':True})
                result = capture(folder, target, root, cat, schema, checkpoint=checkpoint)
                baseline_state = read_state(target)
                verify(target, root, cat, checkpoint=checkpoint)
                partial = checkpointer.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchone()
                assert partial[1] > partial[2], partial
            with contextlib.closing(connect(target, True)) as db:
                assert db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0] == 0
            assert read_state(target) == baseline_state
            result['wal'] = telemetry
            result['checkpoint_pressure'] = pressure
        else:
            result = capture(folder, target, root, cat, schema)
            verify(target, root, cat)
        # A receipt never authorizes a restart by itself. A no-op/ABA can match
        # current state; a real changed canary must refuse without replacement.
        before = {p.name: file_state(p) for p in (root / 'baseline.bin', root / 'intent.json', root / 'decision.json', root / 'custody.txt', root / 'migration.mutex')}
        with contextlib.closing(connect(target, True)) as db:
            old_title = db.execute('SELECT title FROM books WHERE id=1').fetchone()[0]
            db.execute('UPDATE books SET title=title WHERE id=1');db.commit()
        verify(target, root, cat)
        with contextlib.closing(connect(target, True)) as db:
            db.execute("UPDATE books SET title='ABA intermediate' WHERE id=1");db.commit()
            db.execute('UPDATE books SET title=? WHERE id=1', (old_title,));db.commit()
        verify(target, root, cat)
        verify(target, root, cat, kill_at='decision-durable')
        with contextlib.closing(connect(target, True)) as db:
            db.execute("UPDATE books SET title='changed after verifier death' WHERE id=1");db.commit()
        after_write = read_state(target)
        refusal = verify(target, root, cat, expect=False)
        assert refusal['reason'] == 'baseline-parity-mismatch'
        assert read_state(target) == after_write
        assert {p.name: file_state(p) for p in (root / 'baseline.bin', root / 'intent.json', root / 'decision.json', root / 'custody.txt', root / 'migration.mutex')} == before
        result.update(stale_receipt_rejected=True, no_op_and_ABA_current_parity_only=True, later_write_preserved=True)
        return result

    def native_case(folder, schema):
        target, pack, root, cat = seed(folder, schema)
        result = capture(folder, target, root, cat, schema, native=True)
        result['fresh_verifier'] = verify(target, root, cat)
        return result

    def wal_fault(folder, schema):
        target, pack, root, cat = seed(folder, schema, 'wal')
        with wal_pin(target):
            capture(folder, target, root, cat, schema)
            before = read_state(target)
            with deny_windows_page1(target) as calibration:
                report = verify(target, root, cat, expect=False)
                assert report['sqlite_extended_code'] & 255 == 10, report
                assert not (root / 'decision.json').exists()
            assert read_state(target) == before
            return dict(calibration, actual_verifier=report, recovered=verify(target, root, cat))

    def mutation_case(folder, change):
        target, pack, root, cat = seed(folder)
        capture(folder, target, root, cat, 7)
        protected = {p.name: file_state(p) for p in (root / 'baseline.bin', root / 'intent.json', root / 'custody.txt', root / 'migration.mutex')}
        with contextlib.closing(connect(target, True)) as db:
            db.execute('PRAGMA foreign_keys=OFF')
            db.execute(change)
            db.commit()
        before = identity(target)
        with contextlib.closing(connect(target)) as db:
            changed_state = canonical(db)  # FK-invalid fixture is intentionally not healthy.
        report = verify(target, root, cat, expect=False)
        assert not (root / 'decision.json').exists() and identity(target) == before
        with contextlib.closing(connect(target)) as db:
            assert canonical(db) == changed_state
        assert {p.name: file_state(p) for p in (root / 'baseline.bin', root / 'intent.json', root / 'custody.txt', root / 'migration.mutex')} == protected
        return {'change': change, 'refusal': report}

    def evidence_mutation(folder, which):
        target, pack, root, cat = seed(folder)
        capture(folder, target, root, cat, 7)
        path = root / which
        if which == 'baseline.bin':
            replacement = root / 'foreign-baseline.bin'
            replacement.write_bytes(path.read_bytes())
            os.replace(replacement, path)
        elif which == 'intent.json':
            path.write_bytes(b'{"format":')
        else:
            path.write_bytes(b'foreign mutex')
        changed = file_state(path)
        before = read_state(target)
        report = verify(target, root, cat, expect=False)
        assert file_state(path) == changed and read_state(target) == before
        assert not (root / 'decision.json').exists()
        return {'foreign_evidence_untouched': True, 'refusal': report}

    def boundary_kill(folder, phase):
        target, pack, root, cat = seed(folder)
        result = capture(folder, target, root, cat, 7, kill_at=phase)
        assert read_state(target) == bytes.fromhex(result['expected'])
        protected = {p.name: file_state(p) for p in root.iterdir() if p.is_file() and not p.name.endswith(('.ready', '.go'))}
        # An intent is usable only after its separate custody witness exists.
        expect = (root / 'intent.json').exists() and (root / 'custody.txt').exists()
        report = verify(target, root, cat, expect=expect)
        for name, state in protected.items():
            assert file_state(root / name) == state
        return {'kill_boundary': phase, 'recomputed_parity_after_restart': expect, 'report': report}

    def vectors_case(folder, mutation):
        root = folder / 'protocol';root.mkdir()
        rc, report = simple('vectors', folder / 'unused.sqlite', root, folder / 'unused.catalog', mutation)
        assert rc == 0, report
        large = bytearray(b'\xa5' * 8193);large[4096] = 0
        rows = [(1,None,None),(2,None,''),(3,None,b''),(4,'nul','a\0b'),(5,'blob',b'a\0b'),(6,'number',42),(7,'number',42.0),(8,'large',bytes(large))]
        if mutation == 'rowid':
            rows[0] = (20,None,None);rows.sort(key=lambda row:row[0])
        if mutation == 'type': rows[5] = (6,'number',42.0)
        if mutation == 'cell': rows[4] = (5,'blob',b'a\0c')
        expected = query_frame('vectors', 3, rows)
        assert (root / 'baseline.bin').read_bytes() == expected
        return {'independent_exact_typed_bytes': True, 'mutation': mutation, 'bytes': len(expected)}

    def lifecycle_case(folder):
        target, pack, root, cat = seed(folder)
        rc, report = simple('lifecycle', target, root, cat)
        assert rc == 0 and report['source_retained_control'] and report['close_busy_control'], report
        writer(target, root, cat, False)
        return report

    def alias_case(folder, kind):
        target, pack, root, cat = seed(folder)
        baseline = root / 'baseline.bin'
        if kind == 'hardlink':
            os.link(target, baseline)
        else:
            # Windows symlink privilege may not be available: directory junction
            # is an independently measured reparse-point refusal, not a skip.
            if os.name == 'nt':
                p = subprocess.run(['cmd', '/c', 'mklink', '/J', str(baseline), str(folder)], capture_output=True, text=True)
                assert p.returncode == 0, p.stdout + p.stderr
                assert baseline.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
            else:
                baseline.symlink_to(target.resolve())
        before = read_state(target)
        child = spawn('capture', target, root, cat)
        try:
            assert child.finish() == 3
            report = child.report()
            assert not (root / 'intent.json').exists() and read_state(target) == before
            return {'alias_refused': kind, 'report': report}
        finally:
            child.finish(kill=child.p.poll() is None)
            if os.name == 'nt' and kind == 'symlink': os.rmdir(baseline)
            else: baseline.unlink()

    def capture_refusal(folder, kind):
        target, pack, root, cat = seed(folder)
        with contextlib.closing(connect(target, True)) as db:
            if kind == 'application':
                db.execute("UPDATE books SET source=x'00010203' WHERE format=8")
                # include/exr/base.h pins EXR_PDF=8; assert an actual row changed.
                if not db.execute('SELECT changes()').fetchone()[0]:
                    raise AssertionError('PDF enum fixture must update at least one original')
            else:
                # Python's real FTS5 creates a virtual/shadow schema. The SDK
                # may refuse its module earlier; either way no admission exists.
                db.execute('CREATE VIRTUAL TABLE unqualified USING fts5(body)')
                db.execute("INSERT INTO unqualified VALUES('actual virtual row')")
            db.commit()
        # Clean DELETE fixture, no live owner: raw identity/hash here is only a
        # negative-control preservation check, never the WAL parity oracle.
        before = file_state(target)
        child = spawn('capture', target, root, cat)
        reached = []
        try:
            for phase in CAPTURE_PHASES:
                until = time.monotonic() + 35
                while child.p.poll() is None and not (root / (phase + '.ready')).exists() and time.monotonic() < until:
                    time.sleep(.02)
                if child.p.poll() is not None:
                    break
                child.wait(root, phase);reached.append(phase);child.go(root, phase)
            assert child.finish() == 3
            report = child.report()
            assert not (root / 'intent.json').exists() and not (root / 'decision.json').exists()
            assert file_state(target) == before
            if kind == 'application':
                assert report['reason'].startswith('clone-'), report
            return {'kind': kind, 'actual_refusal': report, 'phases_reached': reached}
        finally:
            child.finish(kill=child.p.poll() is None)

    def target_change(folder, kind):
        target, pack, root, cat = seed(folder)
        capture(folder, target, root, cat, 7)
        saved = folder / 'original-library.sqlite'
        target.rename(saved)
        try:
            if kind == 'foreign':
                shutil.copyfile(saved, target)
                foreign = file_state(target)
            report = verify(target, root, cat, expect=False)
            assert not (root / 'decision.json').exists()
            if kind == 'foreign':
                assert file_state(target) == foreign
            else:
                assert not target.exists()
            return {'target': kind, 'refusal': report}
        finally:
            if target.exists(): target.unlink()
            saved.rename(target)

    def late_evidence(folder, name):
        target, pack, root, cat = seed(folder)
        capture(folder, target, root, cat, 7)
        before = read_state(target)
        replaced = {}
        def replace(phase):
            if phase == 'compared':
                path = root / name
                temp = root / 'foreign-equal-bytes'
                temp.write_bytes(path.read_bytes());os.replace(temp,path)
                replaced['state'] = file_state(path)
        report = verify(target, root, cat, expect=False, before_go=replace)
        assert report['reason'] == 'ownership-changed', report
        assert file_state(root / name) == replaced['state'] and read_state(target) == before
        assert not (root / 'decision.json').exists()
        return {'late_equal_byte_foreign': name, 'refusal': report}

    def read_refusal(folder):
        target, pack, root, cat = seed(folder)
        capture(folder, target, root, cat, 7)
        before = read_state(target), file_state(root / 'baseline.bin')
        with deny_evidence_read(root / 'baseline.bin') as calibration:
            report = verify(target, root, cat, expect=False)
            assert not (root / 'decision.json').exists()
        assert (read_state(target), file_state(root / 'baseline.bin')) == before
        return dict(calibration, refusal=report, recovered=verify(target, root, cat))

    def create_refusal(folder):
        target, pack, root, cat = seed(folder)
        capture(folder, target, root, cat, 7)
        before = read_state(target)
        clear_signals(root)
        child = spawn('verify', target, root, cat)
        try:
            child.wait(root,'verify-held');writer(target,root,cat,True);child.go(root,'verify-held')
            child.wait(root,'compared');writer(target,root,cat,True)
            # Empty precreated token does not release the C rendezvous. Existing
            # file write remains allowed while directory creation is denied.
            (root / 'compared.go').write_bytes(b'')
            with deny_decision_create(root) as calibration:
                child.go(root,'compared')
                assert child.finish() == 3
                report = child.report()
                assert report['reason'] == 'exclusive-file-create', report
                assert not (root / 'decision.json').exists()
            assert read_state(target) == before
            return dict(calibration, refusal=report, recovered=verify(target, root, cat))
        finally:
            child.finish(kill=child.p.poll() is None)

    def decision_rename_refusal(folder):
        target, pack, root, cat = seed(folder)
        capture(folder, target, root, cat, 7);verify(target, root, cat)
        decision = root / 'decision.json'
        before = file_state(decision), read_state(target)
        replacement = root / 'rename-disposable'
        replacement.write_bytes(b'not a valid result')
        # The consumer never renames/deletes decisions. This is a measured OS
        # retention control, not a claim it attempted a forbidden cleanup.
        with deny_delete(decision) as calibration:
            try:
                os.replace(replacement, decision)
                raise AssertionError('decision rename unexpectedly succeeded')
            except PermissionError:
                pass
        assert (file_state(decision), read_state(target)) == before
        return dict(calibration, retained=True, consumer_cleanup_attempted=False)

    def interrupt_case(folder):
        target, pack, root, cat = seed(folder)
        capture(folder, target, root, cat, 7)
        before = read_state(target)
        report = verify(target, root, cat, expect=False, fault='interrupt')
        assert report['sqlite_extended_code'] & 255 == 9 and report['reason'] == 'actual-query-interrupt', report
        assert not (root / 'decision.json').exists() and read_state(target) == before
        return {'actual_interrupt': report, 'fresh_retry': verify(target, root, cat)}

    def product_control(folder, pending):
        target, pack, root, cat = seed(folder)
        delta = folder / 'delta.exrpack'
        delta.write_bytes(L.build_pack([L.entry(L.book_record('additional','additional.txt'),L.TXT_OTHER)],[]))
        args = [a.tool,'migrate','--target',str(target),'--pack',str(delta)]
        if pending: args += ['--inject','precommit-cancel']
        child = Child(args,logs / (folder.name + '-product'))
        rc = child.finish();report = child.report()
        policy = Path(str(target) + '.migration-pending.json')
        if pending:
            assert rc == 4 and report['atomicity']['recovery']['automatic_retirement_blocked'], report
            assert json.loads(policy.read_text())['version'] == 3
            paths = [p for p in folder.iterdir() if p.name.startswith('library.sqlite.')]
            protected = {str(p):file_state(p) for p in paths}
            before = read_state(target)
            capture(folder,target,root,cat,7);verify(target,root,cat)
            assert read_state(target) == before
            assert {str(p):file_state(p) for p in paths} == protected
            retry = Child([a.tool,'recover-mirror','--target',str(target)],logs / (folder.name+'-retry'))
            assert retry.finish() == 5
            assert retry.report()['code'] == 'recovery-unverified'
            assert {str(p):file_state(p) for p in paths} == protected
            return {'v3_still_pending': True, 'provisional_decision_not_product_authority': True}
        assert rc == 0 and report['atomicity']['transaction']['target_commit'] == 'committed', report
        assert not policy.exists() and not Path(str(target)+'.migrate-lock').exists()
        writer(target,root,cat,False)
        with contextlib.closing(connect(target,True)) as db:
            db.execute("UPDATE books SET title='ordinary writer after normal COMMIT' WHERE id=1");db.commit()
        before = read_state(target)
        retry = Child(args,logs / (folder.name+'-idempotent'))
        assert retry.finish() == 0 and read_state(target) == before
        return {'normal_COMMIT_and_later_write_preserved': True}

    def execute(name, function):
        folder = a.work / name;folder.mkdir()
        item = {'name': name, 'passed': False};cases.append(item)
        try:
            item['details'] = function(folder)
            item['passed'] = True
        except Exception:
            item['error'] = traceback.format_exc()
        (a.work / 'result.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(item), flush=True)

    for schema in (6,7):
        for journal in ('delete','wal'):
            execute('baseline-schema%d-%s' % (schema,journal), lambda f,s=schema,j=journal:main_case(f,s,j))
        execute('native-delete-schema%d' % schema, lambda f,s=schema:native_case(f,s))
        execute('real-sdk-spill-schema%d' % schema,
                lambda f,s=schema: (lambda t,p,r,c:capture(f,t,r,c,s,spill=True))(*seed(f,s)))
        if os.name == 'nt':
            execute('native-wal-read-schema%d' % schema, lambda f,s=schema:wal_fault(f,s))
    for mutation in ('none','rowid','type','cell'):
        execute('typed-vector-' + mutation, lambda f,m=mutation:vectors_case(f,m))
    execute('explicit-resource-lifetime', lifecycle_case)
    for kind in ('hardlink','symlink'):
        execute('alias-' + kind, lambda f,k=kind:alias_case(f,k))
    changes = {
        'content': "UPDATE books SET title='different with equal ledger' WHERE id=1",
        'type': "UPDATE books SET cover=42 WHERE id=1",
        'rowid': "UPDATE notes SET id=id+1000 WHERE id=(SELECT min(id) FROM notes)",
        'trigger': 'DROP TRIGGER books_progress_changed',
        'index': 'DROP INDEX notes_book',
        'unknown-table': 'CREATE TABLE unexpected(x)',
        'foreign-key': 'UPDATE notes SET book_id=987654 WHERE id=(SELECT min(id) FROM notes)',
    }
    for name, change in changes.items():
        execute('mutation-' + name, lambda f,c=change:mutation_case(f,c))
    for which in ('baseline.bin','intent.json','migration.mutex'):
        execute('evidence-' + which, lambda f,w=which:evidence_mutation(f,w))
    for phase in ('baseline-durable','intent-durable','mirror-published','mutation-held'):
        execute('kill-' + phase, lambda f,p=phase:boundary_kill(f,p))
    for kind in ('application','virtual'):
        execute('capture-refusal-' + kind, lambda f,k=kind:capture_refusal(f,k))
    for kind in ('absent','foreign'):
        execute('target-' + kind, lambda f,k=kind:target_change(f,k))
    for name in ('intent.json','baseline.bin'):
        execute('late-' + name, lambda f,n=name:late_evidence(f,n))
    execute('evidence-read-refusal',read_refusal)
    execute('decision-create-refusal',create_refusal)
    execute('decision-rename-refusal',decision_rename_refusal)
    execute('actual-query-interrupt',interrupt_case)
    execute('existing-v3-remains-pending',lambda f:product_control(f,True))
    execute('normal-product-COMMIT',lambda f:product_control(f,False))
    evidence['expected_cases'] = 43 if os.name == 'nt' else 41
    evidence['passed'] = len(cases) == evidence['expected_cases'] and all(item['passed'] for item in cases)
    evidence['executables_sha256'] = {key: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                                      for key,path in [('probe',a.probe),('candidate',a.tool),('actual_sdk340',a.old_tool)]}
    evidence['python_sqlite_version'] = sqlite3.sqlite_version
    (a.work / 'result.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(evidence), flush=True)
    raise SystemExit(0 if evidence['passed'] else 1)


if __name__ == '__main__':
    main()
