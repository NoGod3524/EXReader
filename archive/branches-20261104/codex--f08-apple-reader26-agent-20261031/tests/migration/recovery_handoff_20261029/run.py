#!/usr/bin/env python3
"""Actions-only isolated handoff qualification. Expected refusals are cases.

No production receipt is consumed or retired. The C helper, not this driver,
owns the live SDK transaction, scanner launch, byte comparison and COMMIT ACK.
"""
import argparse
import contextlib
import errno
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import traceback

if os.environ.get('GITHUB_ACTIONS') != 'true':
    raise SystemExit('Builds/tests/fixtures/artifact parsing are Actions-only')
if os.name != 'posix':
    raise SystemExit('POSIX qualification only; Windows remains unqualified')
SPEC = importlib.util.spec_from_file_location('frozen_preflight', Path(__file__).parents[1] / 'recovery_preflight_20261029/run.py')
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)
TOKEN_SPEC = importlib.util.spec_from_file_location('complete_private_token', Path(__file__).parents[1] / 'recovery_integration_20261029/run.py')
T = importlib.util.module_from_spec(TOKEN_SPEC)
TOKEN_SPEC.loader.exec_module(T)

MIB = 1024 * 1024
PHASES = ('lease-snapshot', 'S1', 'S2', 'S3', 'snapshot-race', 'scanner-request', 'scanner-live', 'scanner-result',
          'scanner-complete', 'scanner-refused', 'compared', 'restore-prepared', 'restore-published',
          'S4', 'mirror-published', 'S5', 'identity-refused', 'rollback-finished', 'close-only', 'S6', 'S7', 'S8', 'lease-held')
FENCED = {'S3', 'scanner-request', 'scanner-live', 'scanner-result', 'scanner-complete',
          'scanner-refused', 'compared', 'restore-prepared', 'restore-published', 'S4', 'mirror-published', 'S5', 'snapshot-race', 'identity-refused'}
UPGRADE = {
    ('table','epub_bounded_books','epub_bounded_books','CREATE TABLE epub_bounded_books(book_id INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE)'),
    ('table','epub_progress','epub_progress','CREATE TABLE epub_progress(book_id INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,part INTEGER NOT NULL CHECK(part>=0 AND part<10000),path TEXT NOT NULL,position INTEGER NOT NULL CHECK(position>=0),prefix TEXT,suffix TEXT,chapter TEXT)'),
    ('table','epub_notes','epub_notes','CREATE TABLE epub_notes(id INTEGER PRIMARY KEY,book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,part INTEGER NOT NULL CHECK(part>=0 AND part<10000),path TEXT NOT NULL,start INTEGER NOT NULL CHECK(start>=0),end INTEGER NOT NULL CHECK(end>start),exact TEXT NOT NULL,prefix TEXT,suffix TEXT,chapter TEXT,text TEXT NOT NULL)'),
    ('index','epub_notes_book','epub_notes','CREATE INDEX epub_notes_book ON epub_notes(book_id,part,start,id)'),
}
LEDGER_DDL = 'CREATE TABLE exr_migration_ledger(id INTEGER PRIMARY KEY CHECK(id=1),data BLOB NOT NULL)'
LEDGER_OBJECT = ('table','exr_migration_ledger','exr_migration_ledger',LEDGER_DDL)


class BoundedChild:
    """Drain native pipes into bounded evidence; never poll an unbounded file.

    Reserve 256KiB before launch (128KiB parent streams +64KiB C-owned scanner
    streams + slack), release unused reservation only after wait/join/readback.
    """
    def __init__(self, command, logbase, driver):
        self.driver=driver;self.done=False;self.total=0;self.errors=[];self.lock=threading.Lock()
        self.reservation=256*1024
        with driver.log_lock:
            assert driver.log_used+driver.log_reserved+self.reservation<=16*MIB,'case log reservation'
            driver.log_reserved+=self.reservation
        self.extra=Path(command[4]) if command[0]==driver.a.handoff else None
        self.out_path=Path(str(logbase)+'.stdout.txt');self.err_path=Path(str(logbase)+'.stderr.txt')
        self.p=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True,
                                env=dict(os.environ,EXR_MIGRATE_TEST_FAULTS='1'))
        def drain(pipe,path):
            try:
                with path.open('xb') as stream:
                    while True:
                        data=pipe.read(4096)
                        if not data:break
                        with self.lock:
                            if self.total+len(data)>128*1024:
                                self.errors.append('hard native stdout/stderr bound')
                                self.p.kill();break
                            self.total+=len(data)
                        stream.write(data)
            except Exception as error:
                self.errors.append(repr(error))
                try:self.p.kill()
                except ProcessLookupError:pass
            finally:pipe.close()
        self.threads=[threading.Thread(target=drain,args=(self.p.stdout,self.out_path)),
                      threading.Thread(target=drain,args=(self.p.stderr,self.err_path))]
        for thread in self.threads:thread.start()

    def wait(self,root,phase):
        until=time.monotonic()+30
        while not (root/(phase+'.ready')).exists() and self.p.poll() is None and time.monotonic()<until:time.sleep(.01)
        assert (root/(phase+'.ready')).exists(),('missing native phase',phase,self.p.poll())

    def go(self,root,phase):T.private_token(root/(phase+'.go'))

    def finish(self,kill=False):
        if not self.done:
            try:
                if kill and self.p.poll() is None:self.p.kill()
                self.p.wait(timeout=35)
            except subprocess.TimeoutExpired:
                self.p.kill();self.p.wait(timeout=5);self.errors.append('native child deadline')
            finally:
                for thread in self.threads:
                    thread.join(timeout=5)
                    if thread.is_alive():self.errors.append('pipe drain deadline')
                extra=sum(p.stat().st_size for p in (self.extra.glob('scanner.*.txt') if self.extra else ()))
                if extra>65536:self.errors.append('C scanner hard log bound')
                with self.driver.log_lock:
                    self.driver.log_reserved-=self.reservation
                    self.driver.log_used+=self.total+extra
                    if self.driver.log_used+self.driver.log_reserved>16*MIB:self.errors.append('case cumulative log bound')
                self.done=True
        assert not self.errors,self.errors
        return self.p.returncode

    def report(self):return json.loads(self.out_path.read_text())


def inventory(root):
    result = []
    for p in sorted(root.rglob('*')):
        s = p.lstat()
        result.append({'path': str(p.relative_to(root)), 'bytes': s.st_size,
                       'allocated': s.st_blocks * 512, 'mode': oct(stat.S_IMODE(s.st_mode)),
                       'dev': s.st_dev, 'ino': s.st_ino, 'links': s.st_nlink})
    return result


def model(target):
    with contextlib.closing(P.connect(target)) as db:
        db.execute('BEGIN')
        assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        tables = [x[0] for x in db.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name")]
        return {'schema': db.execute('PRAGMA user_version').fetchone()[0],
                'app': db.execute('PRAGMA application_id').fetchone()[0],
                'catalog': set(db.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema')),
                'rows': {t: db.execute('SELECT _rowid_,* FROM ' + P.quote(t) + ' ORDER BY _rowid_').fetchall() for t in tables},
                'columns': {t: [x[1] for x in db.execute('PRAGMA table_info(' + P.quote(t) + ')')] for t in tables},
                'public': P.public_projection(db), 'canonical': P.canonical(db)}


class Driver:
    def __init__(self, args):
        self.a = args
        self.serial = 0
        self.current = None
        self.logs = args.work / 'logs'
        self.logs.mkdir()
        self.cases = []
        self.children = []
        self.log_lock=threading.Lock();self.log_used=0;self.log_reserved=0

    def reserve(self,amount):
        # The whole case's 1GiB is reserved against the 4GiB workspace BEFORE
        # starting it; fixed-size fixture writes reserve their own worst case.
        paths=inventory(self.case_folder) if self.case_folder.exists() else []
        used=max(sum(p['bytes'] for p in paths),sum(p['allocated'] for p in paths))
        self.check('pre-write case byte reservation',used+amount<=1024*MIB,{'used':used,'reserve':amount})

    def check(self, name, condition, observed=None):
        self.current['checks'].append({'name': name, 'passed': bool(condition), 'observed': observed})
        assert condition, (name, observed)

    def stamp(self):
        self.serial += 1
        return '%032x' % self.serial

    def child(self, command, name):
        # Each real native child self-enforces CPU/file limits; driver additionally
        # bounds logs and deadlines. No child is launched with a live SDK handle.
        c = BoundedChild(command, self.logs / (self.stamp() + '-' + name),self)
        self.children.append(c)
        return c

    def simple_probe(self, mode, target, root, cat):
        c = self.child([self.a.probe, mode, str(target), str(root), str(cat), self.stamp(), 'none', 'qualification-only'], mode)
        rc = c.finish()
        return rc, c.report()

    def writer(self, target, root, cat, busy):
        rc, r = self.simple_probe('writer', target, root, cat)
        self.check('native writer ' + ('BUSY' if busy else 'available'),
                   (rc == 3 and r['sqlite_extended_code'] & 255 == 5) if busy else rc == 0, r)

    def lease(self, root, busy):
        path = root / 'lease'
        with path.open('rb') as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError as e:
                self.check('native flock refusal errno', e.errno in (errno.EWOULDBLOCK, errno.EAGAIN), e.errno)
                acquired = False
            self.check('lease held until original process exit' if busy else 'lease released by process exit', acquired != busy)

    def run(self, fixture, mode='admit', fault='none', entry='protocol-admit', kill_at=None,
            action=None, expect=True, checkpoint=None):
        target, root, cat = fixture['target'], fixture['root'], fixture['cat']
        token = self.stamp()
        ctl = fixture['folder'] / ('control-' + token)
        ctl.mkdir(mode=0o700)
        c = self.child([self.a.handoff, mode, str(target), str(root), str(ctl), self.a.probe,
                        token, fault, entry, 'qualification-only'], 'handoff-' + mode)
        handled = set()
        deadline = time.monotonic() + 120
        try:
            while c.p.poll() is None:
                assert time.monotonic() < deadline, 'case process deadline'
                for phase in PHASES:
                    if phase in handled or not (ctl / (phase + '.ready')).exists():
                        continue
                    handled.add(phase)
                    if phase in FENCED:
                        self.writer(target, root, cat, True)
                    if phase not in ('S1','lease-snapshot') and (root / 'lease').exists():
                        self.lease(root, True)
                    if checkpoint:
                        checkpoint(phase)
                    if action:
                        action(phase, c, ctl)
                    if phase == kill_at:
                        c.finish(kill=True)
                        self.check('actual child killed at ' + phase, c.p.returncode < 0, c.p.returncode)
                        if (root / 'lease').exists():
                            self.lease(root, False)
                        return {'killed': phase, 'phases': sorted(handled), 'control': str(ctl)}
                    if c.p.poll() is None:
                        c.go(ctl,phase)
                for log in (c.out_path, c.err_path):
                    self.check_log_size(log)
                time.sleep(.01)
            rc = c.finish()
            r = c.report()
            for line in c.err_path.read_text().splitlines():
                if line.startswith('quarantined target/unknown descriptors until process exit: '):
                    r['quarantined_descriptors']=int(line.rsplit(': ',1)[1])
            if (ctl/'scanner.stdout.txt').exists():
                raw=(ctl/'scanner.stdout.txt').read_text()
                try:r['scanner_report']=json.loads(raw)
                except json.JSONDecodeError:r['scanner_report_unparseable']=True
            self.check('expected process outcome', (rc == 0) == expect, {'rc': rc, 'report': r})
            self.check('no inflated admission', not any(r[k] for k in ('physical_cleanup_verified','historical_rollback_proved','product_admission','full_p0_acceptance')), r)
            self.check('no invented I/O observation', r['io_observation'] == 'not-installed')
            r['phases_observed'] = sorted(handled)
            return r
        finally:
            c.finish(kill=c.p.poll() is None)

    @staticmethod
    def check_log_size(path):
        if path.exists():assert path.stat().st_size <= 16*MIB, ('log budget', path)

    def seed(self, folder, schema=7, journal='delete', absent=False):
        self.reserve(64*MIB)
        folder.mkdir(mode=0o700)
        target, pack = folder/'library.sqlite', folder/'seed.exrpack'
        entries, notes = P.L.dataset()
        pack.write_bytes(P.L.build_pack(entries, notes))
        c = self.child([self.a.old_tool if schema == 6 else self.a.tool, 'migrate', '--target', str(target), '--pack', str(pack), '--allow-partial'], 'seed')
        self.check('real original fixture producer succeeds', c.finish() == 0)
        r = c.report()
        counts = {'books_expected':5,'books_created':4,'books_accounted':5,
                  'books_audio_positions_only':1,'notes_expected':16,'notes_created':10,
                  'notes_unlocated':6,'notes_accounted':16}
        self.check('whole legacy fixture retained', (r['result'],r['code']) == ('success','ok') and all(r['counts'][k] == v for k,v in counts.items()), r['counts'])
        self.check('only known unsupported audio', [(e['code'],e['legacy_id']) for e in r['entries'] if e['severity']=='unsupported'] == [('audio-original-not-storable','b-audio')])
        ledger = json.loads(Path(str(target)+'.legacy-map.json').read_bytes())
        self.check('all five book and sixteen note originals retained', len(ledger['books']) == 5 and len(ledger['notes']) == 16 and
                   {b['legacy_id']:b['retained'] for b in ledger['books']} == {b['legacy_id']:{k:v for k,v in b['record'].items() if k!='cover'} for b in entries} and
                   {n['legacy_id']:n['retained'] for n in ledger['notes']} == {n['id']:n for n in notes})
        with contextlib.closing(P.connect(target, True)) as db:
            self.check('actual schema/journal', db.execute('PRAGMA user_version').fetchone()[0] == schema and db.execute('PRAGMA journal_mode='+journal).fetchone()[0] == journal)
            db.execute('PRAGMA wal_autocheckpoint=0')
        root = folder/'protocol';root.mkdir(mode=0o700)
        capture = folder/'preflight';capture.mkdir(mode=0o700)
        cat = root/'catalog.bin'
        with contextlib.closing(P.connect(target)) as db:
            cat.write_bytes(P.catalog_bytes(db))
        return {'folder':folder,'target':target,'root':root,'capture':capture,'cat':cat,
                'schema':schema,'journal':journal,'pack':pack,'absent':absent}

    def capture(self, f):
        self.reserve(256*MIB)
        target, root, cat = f['target'], f['capture'], f['cat']
        original = model(target)
        c = self.child([self.a.probe,'capture',str(target),str(root),str(cat),self.stamp(),'none','qualification-only'], 'capture')
        try:
            for phase in P.CAPTURE_PHASES:
                c.wait(root,phase)
                if phase != 'owner-finished':
                    self.writer(target, root, cat, True)
                if phase == 'clone-sdk-closed':
                    clone = model(root/'clone.sqlite')
                    self.check('pinned upgrade only', clone['schema']==7 and clone['catalog']==original['catalog'] | (UPGRADE if f['schema']==6 else set()))
                    self.check('all original clone rows unchanged', all(clone['rows'][t]==rows for t,rows in original['rows'].items()))
                    projection=[json.loads(line) for line in (root/'public-projection.jsonl').read_text().splitlines()]
                    self.check('independent public projection exact',projection==original['public'])
                c.go(root,phase)
            self.check('unchanged preflight capture',c.finish()==0,c.report())
        finally:
            c.finish(kill=c.p.poll() is None)
        self.check('baseline bytes and target exact', (root/'baseline.bin').read_bytes()==original['canonical'] and P.read_state(target)==original['canonical'])
        proto=f['root']
        (proto/'baseline.bin').write_bytes((root/'baseline.bin').read_bytes())
        (proto/'pending.original').write_bytes((root/'intent.json').read_bytes())
        with contextlib.closing(P.connect(root/'clone.sqlite')) as db:
            rows=set(db.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema'))
            # SDK3.40/schema6 has no internal ledger; the planned public ledger
            # call creates precisely this current-SDK DDL, not arbitrary schema.
            if not any(row[1]=='exr_migration_ledger' for row in rows):rows.add(LEDGER_OBJECT)
            (proto/'catalog7.bin').write_bytes(P.query_frame('catalog',4,sorted(rows,key=lambda row:(row[0],row[1]))))
        before=Path(str(target)+'.legacy-map.json').read_bytes()
        (proto/'mirror.preimage').write_bytes(before)
        if not f['absent']:
            (proto/'mirror.json').write_bytes(before)
        (proto/'pack.original').write_bytes(f['pack'].read_bytes())
        ledger=json.loads(before)
        for n in (1,2):
            ledger['packs'].append(hashlib.sha256(('bounded-handoff-work-'+str(n)).encode()).hexdigest())
            (proto/('plan%d.json'%n)).write_text(json.dumps(ledger,separators=(',',':'))+'\n')
        f['original']=original
        f['target_id']=P.identity(target)
        f['retained']={n:P.file_state(proto/n) for n in ('baseline.bin','catalog.bin','catalog7.bin','pending.original','mirror.preimage','plan1.json','plan2.json','pack.original')}
        return f

    def prepared(self, folder, schema=7, journal='delete', absent=False):
        return self.capture(self.seed(folder,schema,journal,absent))

    def retained(self,f):
        self.check('all original evidence identities and bytes retained', {n:P.file_state(f['root']/n) for n in f['retained']}==f['retained'])
        self.check('target identity preserved',P.identity(f['target'])==f['target_id'])

    def committed(self,f,prior,work):
        now=model(f['target'])
        expected={t:[tuple(row) for row in rows] for t,rows in prior['rows'].items()}
        title_index=prior['columns']['books'].index('title')+1
        id_index=prior['columns']['books'].index('id')+1
        expected['books']=[tuple('handoff-work-'+('one' if work==1 else 'two') if i==title_index and row[id_index]==1 else value for i,value in enumerate(row)) for row in expected['books']]
        expected['exr_migration_ledger']=[(1,1,(f['root']/('plan%d.json'%work)).read_bytes())]
        planned_catalog=prior['catalog'] | (UPGRADE if prior['schema']==6 else set())
        if 'exr_migration_ledger' not in prior['rows']:planned_catalog.add(LEDGER_OBJECT)
        self.check('exact post-COMMIT catalog and schema',now['schema']==7 and now['app']==1163416131 and now['catalog']==planned_catalog)
        self.check('only planned title/ledger changed',all(now['rows'][t]==rows for t,rows in expected.items()),list(expected))
        self.check('only whitelisted empty schema additions',set(now['rows'])-set(expected)==({'epub_bounded_books','epub_progress','epub_notes'} if prior['schema']==6 else set()) and all(not rows for t,rows in now['rows'].items() if t not in expected))
        self.check('published mirror planned bytes',(f['root']/'mirror.json').read_bytes()==(f['root']/('plan%d.json'%work)).read_bytes())
        self.retained(f)
        return now

    @contextlib.contextmanager
    def pin(self,f):
        if f['journal']!='wal':
            yield None
            return
        reader, checkpointer=P.connect(f['target']),P.connect(f['target'],True)
        try:
            checkpointer.execute('PRAGMA wal_autocheckpoint=0')
            checkpointer.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            reader.execute('BEGIN');old=reader.execute('SELECT tags FROM books WHERE id=1').fetchone()[0]
            checkpointer.execute("UPDATE books SET tags='noncheckpointed-handoff-canary' WHERE id=1");checkpointer.commit()
            def pressure(phase):
                passive=checkpointer.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchone()
                full=checkpointer.execute('PRAGMA wal_checkpoint(FULL)').fetchone()
                self.check('live WAL checkpoint pressure '+phase,passive[1]>passive[2]>=0 and full[0]==1 and full[1]>full[2],{'passive':passive,'full':full})
                self.check('pinned old snapshot',reader.execute('SELECT tags FROM books WHERE id=1').fetchone()[0]==old)
                with contextlib.closing(P.connect(f['target'])) as db:
                    self.check('committed WAL canary remains visible',db.execute('SELECT tags FROM books WHERE id=1').fetchone()[0]=='noncheckpointed-handoff-canary')
            pressure('initial')
            yield pressure
        finally:
            reader.close();checkpointer.close()

    def end_to_end(self,folder,schema,journal):
        f=self.seed(folder,schema,journal)
        with self.pin(f) as checkpoint:
            self.capture(f)
            killed=self.run(f,'init',kill_at='S5',checkpoint=checkpoint)
            self.check('interrupted transaction recovered to baseline',P.read_state(f['target'])==f['original']['canonical'])
            r=self.run(f,checkpoint=checkpoint)
            self.check('R actual SDK COMMIT',r['route']=='R' and r['commit_status']==0,r)
            self.committed(f,f['original'],1)
            with contextlib.closing(P.connect(f['target'],True)) as db:
                db.execute("UPDATE books SET author='later ordinary writer preserved',favorite=1 WHERE id=2");db.commit()
            later=model(f['target'])
            successor=self.run(f,checkpoint=checkpoint)
            self.check('C new work actual SDK COMMIT',successor['route']=='C' and successor['commit_status']==0,successor)
            self.committed(f,later,2)
        self.writer(f['target'],f['root'],f['cat'],False)
        self.lease(f['root'],False)
        return {'interrupted':killed,'retry':r,'successor':successor}

    def crash(self,folder,phase):
        folder.mkdir(mode=0o700);results=[]
        for schema in (6,7):
            for journal in ('delete','wal'):
                f=self.seed(folder/('%s-%s'%(schema,journal)),schema,journal)
                with self.pin(f) as checkpoint:
                    self.capture(f);self.run(f,'init',kill_at=phase,checkpoint=checkpoint)
                    prior=model(f['target'])
                    if phase=='S1':
                        r=self.run(f,expect=False)
                        self.check('pre-durable baseline refuses pre-open',r['sdk_open_attempts']==0 and r['reason']=='baseline-not-durable',r)
                        self.check('pre-baseline target unchanged',P.read_state(f['target'])==f['original']['canonical'])
                    elif phase=='S6':
                        self.committed(f,f['original'],1)
                        r=self.run(f,expect=False,checkpoint=checkpoint)
                        refused=(r['reason']=='scanner-status' and r.get('scanner_report',{}).get('reason')=='schema-catalog-mismatch') if schema==6 else r['reason']=='full-baseline-parity-mismatch'
                        self.check('COMMIT without ACK never blindly replays',refused,r)
                        self.check('ack-missing committed data preserved',P.read_state(f['target'])==prior['canonical'])
                    elif phase in ('S7','S8'):
                        r=self.run(f,checkpoint=checkpoint)
                        self.check('visible literal ACK chooses C not replay',r['route']=='C' and r['commit_status']==0,r)
                        self.committed(f,prior,2)
                    else:
                        self.check('uncommitted crash retains baseline',prior['canonical']==f['original']['canonical'])
                        r=self.run(f,checkpoint=checkpoint)
                        self.check('fresh R only after full comparison',r['route']=='R' and r['commit_status']==0,r)
                        self.committed(f,f['original'],1)
                    self.retained(f);results.append({'schema':schema,'journal':journal,'restart':r})
        return results

    def gates(self,folder):
        f=self.prepared(folder);self.run(f,'init',kill_at='S2');before=P.read_state(f['target'])
        protected=P.file_state(f['root']/'anchor.bin')
        for entry in ('migrate','migrate-flag','migrate-dry-run','migrate-break-lock','recover-mirror','dump','verify','export-ledger','inspect-target'):
            r=self.run(f,'gate',entry=entry,expect=False)
            self.check('all entrypoints refuse before DB/output '+entry,r['sdk_open_attempts']==r['sqlite_gate_opens']==r['output_gate_attempts']==0)
        for entry in ('help','version','inspect-no-target'):
            self.run(f,'gate',entry=entry)
        for entry in ('migrate','migrate-break-lock'):
            r=self.run(f,entry=entry,expect=False)
            self.check('no implicit R route '+entry,r['reason']=='explicit-protocol-entry-required' and r['sdk_open_attempts']==0,r)
        self.check('gate leaves data and anchor exact',P.read_state(f['target'])==before and P.file_state(f['root']/'anchor.bin')==protected)
        self.retained(f)
        # Actual unmodified old3.40 sees its shared default lock; no break-lock.
        c=self.child([self.a.old_tool,'migrate','--target',str(f['target']),'--pack',str(f['pack']),'--allow-partial'],'old-default-lock')
        self.check('real old3.40 default blocked',c.finish()!=0,c.report())
        self.check('old default did not mutate',P.read_state(f['target'])==before)
        for variation in ('partial','foreign-equal-bytes'):
            anchor=f['root']/'anchor.bin'
            if variation=='partial':anchor.write_bytes(b'EXRHANDOFF')
            else:
                replacement=f['folder']/'new-anchor';replacement.write_bytes(anchor.read_bytes());os.replace(replacement,anchor)
            for entry in ('migrate','migrate-flag','migrate-dry-run','migrate-break-lock','recover-mirror','dump','verify','export-ledger','inspect-target'):
                r=self.run(f,'gate',entry=entry,expect=False)
                self.check(variation+' gate before any opens '+entry,r['sdk_open_attempts']==r['sqlite_gate_opens']==r['output_gate_attempts']==0)
            self.check(variation+' leaves current data exact',P.read_state(f['target'])==before)
        return {'entrypoints':12,'legacy_break_lock_supported':False,'guard_is_test_model':True}

    def lifetime(self,folder):
        f=self.prepared(folder);self.run(f,'init',kill_at='S2')
        self.run(f,'lease')
        self.lease(f['root'],False)
        # Real isolated exec child can remain stopped after owner death; its
        # continued existence must not keep either the flock or SQLite writer.
        pid=[]
        def action(phase,c,ctl):
            if phase=='scanner-live':
                pid.append(int((ctl/'scanner.pid').read_text()))
        try:
            self.run(f,fault='scanner-paused',kill_at='scanner-live',action=action)
            self.check('scanner PID recorded',len(pid)==1)
            self.lease(f['root'],False)
            self.writer(f['target'],f['root'],f['cat'],False)
        finally:
            for childpid in pid:
                try:os.kill(childpid,signal.SIGKILL)
                except ProcessLookupError:pass
        f2=self.prepared(f['folder']/'replacement-control');self.run(f2,'init',kill_at='S2')
        def replace(phase,c,ctl):
            if phase=='lease-snapshot':
                lease=f2['root']/'lease';other=f2['folder']/'foreign-lease';other.write_bytes(lease.read_bytes());os.replace(other,lease)
        r=self.run(f2,fault='lease-replace',action=replace,expect=False)
        self.check('opened lease fd must equal exact snapshotted inode',r['reason']=='lease-open-fd-identity' and r['sdk_open_attempts']==0,r)
        return {'independent_descriptor_close_and_exec_lifetimes':True}

    def later(self,folder):
        f=self.prepared(folder);self.run(f,'init',kill_at='S2')
        with contextlib.closing(P.connect(f['target'],True)) as db:
            prior=db.execute('SELECT author FROM books WHERE id=2').fetchone()[0]
            db.execute('UPDATE books SET author=author WHERE id=2');db.commit()
            db.execute("UPDATE books SET author='ABA temporary' WHERE id=2");db.commit()
            db.execute('UPDATE books SET author=? WHERE id=2',(prior,));db.commit()
        self.run(f,kill_at='compared')
        self.check('no-op ABA are current parity only',P.read_state(f['target'])==f['original']['canonical'])
        with contextlib.closing(P.connect(f['target'],True)) as db:
            db.execute("UPDATE books SET author='changed after decision death' WHERE id=2");db.commit()
        changed=P.read_state(f['target']);r=self.run(f,expect=False)
        self.check('stale parity never admission',r['reason']=='full-baseline-parity-mismatch' and P.read_state(f['target'])==changed,r)
        self.retained(f);return r

    def foreign(self,folder):
        folder.mkdir(mode=0o700);reports=[]
        for name in ('mirror.json','pending.original','mirror.preimage','anchor.bin','record-00.bin'):
            f=self.prepared(folder/name.replace('.','-'));self.run(f,'init',kill_at='S2')
            path=f['root']/name;old=P.file_state(path);replacement=f['folder']/'replacement';replacement.write_bytes(path.read_bytes());os.replace(replacement,path)
            foreign=P.file_state(path);self.check('equal bytes foreign inode calibrated',foreign[0]!=old[0] and foreign[1]==old[1])
            before=P.read_state(f['target']);r=self.run(f,expect=False)
            self.check('foreign exact bytes refused and retained',P.file_state(path)==foreign and P.read_state(f['target'])==before,r)
            reports.append({'artifact':name,'report':r})
        return reports

    def publication_refusal(self,folder):
        f=self.prepared(folder);permissions=stat.S_IMODE(f['root'].stat().st_mode);calibration=[]
        def action(phase,c,ctl):
            if phase=='S4':
                marker=f['root']/'permission-calibration';marker.write_bytes(b'owned')
                f['root'].chmod(permissions & ~0o222)
                try:
                    marker.rename(f['root']/'permission-destination')
                    raise AssertionError('native rename refusal not calibrated')
                except PermissionError as e:
                    calibration.append(e.errno);self.check('native mirror rename EACCES',e.errno==13,e.errno)
        try:r=self.run(f,'init',action=action,expect=False)
        finally:f['root'].chmod(permissions)
        self.check('real mirror rename fails',r['reason']=='actual-mirror-rename-refusal' and r['native_errno']==13 and calibration==[13],r)
        self.check('failed publication preserves baseline',P.read_state(f['target'])==f['original']['canonical'])
        self.run(f);self.committed(f,f['original'],1);return r

    def sync_failure(self,folder):
        f=self.prepared(folder);r=self.run(f,'init',fault='mirror-sync',expect=False)
        self.check('actual fsync EBADF observed',r['reason']=='actual-sync-descriptor-ebadf' and r['native_errno']==errno.EBADF,r)
        self.check('anchor remains after rename/sync uncertainty',(f['root']/'anchor.bin').exists())
        r2=self.run(f,'sync-control',expect=False)
        self.check('unsafe active name vanished but real anchor remains',not (f['root']/'disposable-active').exists() and (f['root']/'anchor.bin').exists() and r2['native_errno']==errno.EBADF,r2)
        gate=self.run(f,'gate',entry='migrate-break-lock',expect=False)
        self.check('permanent anchor prevents absence bypass',gate['reason']=='pre-open-policy-refusal' and gate['sdk_open_attempts']==0)
        self.run(f);self.committed(f,f['original'],1)
        restorations=[]
        for absent in (False,True):
            sub=f['folder']/('restore-absent' if absent else 'restore-present')
            restored=self.prepared(sub,absent=absent)
            self.run(restored,'init',kill_at='S5')
            restore_report=self.run(restored,fault='restore-sync',expect=False)
            self.check('restoration actual parent-sync refusal',restore_report['native_errno']==errno.EBADF,restore_report)
            destination=restored['root']/'mirror.json'
            self.check('exact original absence or bytes restored',not destination.exists() if absent else destination.read_bytes()==(restored['root']/'mirror.preimage').read_bytes())
            self.check('sole planned evidence archived before removal',len(list(restored['root'].glob('archive-*')))==1)
            self.run(restored);self.committed(restored,restored['original'],1)
            restorations.append(restore_report)
        return {'publish_sync':r,'unsafe_unlink_control':r2,'restoration_sync':restorations}

    def acknowledgment(self,folder):
        folder.mkdir(mode=0o700);reports=[]
        for fault in ('ack-sync','ack-fifo','close-only','wrong-nonce','kill-scanner','partial-report','missing-output','other-nonce-output','partial-output','foreign-output','target-hardlink-input','snapshot-race','foreign-intent-late'):
            f=self.prepared(folder/fault)
            fifo=[]
            def action(phase,c,ctl):
                if phase=='scanner-request' and fault=='wrong-nonce':
                    envelope=next(f['root'].glob('scan-*/envelope.json'))
                    value=json.loads(envelope.read_bytes());value['nonce']='f'*32
                    envelope.write_text(json.dumps(value))
                if phase=='scanner-result' and fault=='partial-report':
                    (ctl/'scanner.stdout.txt').write_text('{"mode":"scan"')
                if phase=='scanner-result' and fault in ('missing-output','other-nonce-output'):
                    output=next(f['root'].glob('scan-*/baseline.bin'))
                    if fault=='missing-output':output.unlink()
                    else:
                        wrong=f['root']/('scan-'+'f'*32);wrong.mkdir(mode=0o700);output.rename(wrong/'baseline.bin')
                if phase=='scanner-complete' and fault in ('partial-output','foreign-output'):
                    output=next(f['root'].glob('scan-*/baseline.bin'))
                    if fault=='partial-output':output.write_bytes(output.read_bytes()[:7])
                    else:
                        other=f['folder']/'foreign';other.write_bytes(output.read_bytes());os.replace(other,output)
                if phase=='S7' and fault=='foreign-intent-late':
                    p=f['root']/'pending.original';other=f['folder']/'foreign';other.write_bytes(p.read_bytes());os.replace(other,p)
                if phase=='S7' and fault=='ack-fifo':
                    p=sorted(f['root'].glob('record-*.bin'))[-1]
                    p.rename(f['folder']/'original-ack-retained.bin');os.mkfifo(p,0o600);fifo.append((p,P.identity(p)))
                if phase=='scanner-complete' and fault=='target-hardlink-input':
                    p=f['root']/'baseline.bin';p.unlink();os.link(f['target'],p)
                if phase=='snapshot-race':
                    p=f['root']/'pending.original';p.unlink();os.link(f['target'],p)
                if phase=='close-only':self.writer(f['target'],f['root'],f['cat'],False)
            try:r=self.run(f,'init',fault=fault if fault in ('ack-sync','close-only','kill-scanner','snapshot-race') else 'none',action=action,expect=False)
            finally:
                for p,owned_id in fifo:
                    self.current['checks'].append({'name':'owned FIFO transport cleanup','passed':P.identity(p)==owned_id,'observed':{'mode':p.lstat().st_mode,'identity':owned_id}})
                    assert P.identity(p)==owned_id
                    p.unlink()  # Only exact test-created FIFO; original ACK remains saved.
            if fault=='ack-sync':
                self.check('literal committed but sync uncertain',r['commit_status']==0 and r['native_errno']==errno.EBADF,r)
                prior=self.committed(f,f['original'],1);self.run(f);self.committed(f,prior,2)
            elif fault=='ack-fifo':
                self.check('special sync target refuses without blocking',r['commit_status']==0 and r['reason']=='sync-file-custody',r)
                self.committed(f,f['original'],1)
            elif fault=='foreign-intent-late':
                self.check('late foreign intent never success',r['commit_status']==0 and r['reason']=='owned-identity-or-bytes-changed',r)
            elif fault=='close-only':
                self.check('void close is not a rollback acknowledgment',r['commit_status']==r['rollback_status']==-1 and r['reason']=='void-close-only-still-pending',r)
                self.check('fresh baseline after implicit close',P.read_state(f['target'])==f['original']['canonical'])
                self.run(f);self.committed(f,f['original'],1)
            elif fault=='snapshot-race':
                self.check('actual opened target alias quarantined without fd close',r['reason']=='opened-target-alias-quarantined' and r['quarantined_descriptors']==1 and 'identity-refused' in r['phases_observed'],r)
                self.check('race refusal left DB content unchanged',P.read_state(f['target'])==f['original']['canonical'])
            else:
                self.check('scanner failure never COMMIT',r['commit_status']==-1 and P.read_state(f['target'])==f['original']['canonical'],r)
                self.check('scanner refusal retains live writer until observed','scanner-refused' in r['phases_observed'])
                if fault in ('missing-output','other-nonce-output'):
                    self.check('missing expected output explicitly refuses',r['reason']=='scanner-baseline-output-missing',r)
            reports.append({'fault':fault,'report':r})
        return reports

    def native_rollback(self,folder):
        folder.mkdir(mode=0o700);reports=[]
        for schema in (6,7):
            f=self.prepared(folder/str(schema),schema)
            manager=None;observed=[]
            def action(phase,c,ctl):
                nonlocal manager
                if phase=='S5':
                    journal=Path(str(f['target'])+'-journal')
                    self.check('actual dirty DELETE journal',journal.stat().st_size>0)
                    manager=P.deny_delete(journal);observed.append(manager.__enter__())
                if phase=='rollback-finished':
                    journal=Path(str(f['target'])+'-journal')
                    observed.append({'retained_journal_bytes':journal.stat().st_size})
            try:r=self.run(f,'init',fault='rollback',action=action,expect=False)
            finally:
                if manager:manager.__exit__(None,None,None)
            self.check('literal SDK status measured not forced error',r['rollback_status']>=0,r)
            self.check('independent fresh recovery baseline exact',P.read_state(f['target'])==f['original']['canonical'])
            self.run(f);self.committed(f,f['original'],1)
            reports.append({'schema':schema,'calibration':observed,'sdk_result':r})
        return reports

    def resources(self,folder):
        folder.mkdir(mode=0o700);reports=[]
        for fault in ('none','cancel','deadline','oversized','work-cap','file-cap'):
            self.reserve(3*67*MIB)
            sub=folder/fault;sub.mkdir(mode=0o700);root=sub/'protocol';root.mkdir(mode=0o700);target=sub/'resource.sqlite'
            with sqlite3.connect(target) as db:
                db.execute('CREATE TABLE payload(x)');db.execute('INSERT INTO payload VALUES(zeroblob(?))',((65 if fault=='oversized' else 2)*MIB,));db.commit()
            f={'folder':sub,'root':root,'target':target,'cat':root/'unused'}
            r=self.run(f,'resource',fault=fault,expect=fault=='none')
            if fault=='none':self.check('real chunked backup progressed',r['backup_steps']>1 and r['backup_pages']>64,r)
            elif fault=='cancel':self.check('cancel after actual progress',r['cancel_observed'] and r['backup_steps']>=1,r)
            elif fault=='deadline':self.check('monotonic deadline refuses after real progress',r['reason']=='backup-monotonic-deadline' and r['backup_steps']>=1,r)
            elif fault=='work-cap':self.check('cumulative reserved page-work cap',r['reason']=='backup-cumulative-work-bound' and r['backup_reserved_pages']==64 and r['backup_pages']>0,r)
            elif fault=='file-cap':self.check('actual inherited RLIMIT_FSIZE refuses growth',r['reason']=='actual-native-file-size-refusal' and r['native_errno']==errno.EFBIG,r)
            else:self.check('physical page size budget refuses',r['reason']=='backup-page-byte-bound',r)
            reports.append(r)
        return reports

    def namespace(self,folder):
        folder.mkdir(mode=0o700);reports=[]
        for attack in ('symlink','hardlink','directory-mode','cumulative','unknown-chain','old-v3'):
            f=self.prepared(folder/attack);self.run(f,'init',kill_at='S2');path=f['root']/'pending.original'
            if attack=='symlink':
                saved=f['folder']/'saved';path.rename(saved);path.symlink_to(saved)
            elif attack=='hardlink':os.link(path,f['root']/'alias')
            elif attack=='directory-mode':f['root'].chmod(0o755)
            elif attack=='cumulative':
                self.reserve(540*MIB)
                for n in range(9):
                    with (f['root']/('sparse-%d'%n)).open('xb') as stream:stream.truncate(60*MIB)
            elif attack=='unknown-chain':(f['root']/'record-03.bin').write_bytes(b'unknown gap record')
            elif attack=='old-v3':
                (f['root']/'anchor.bin').write_text('{"version":3,"retirement_policy":"unverified"}')
            before=P.read_state(f['target'])
            try:r=self.run(f,expect=False)
            finally:
                f['root'].chmod(0o700)
                if attack=='cumulative':
                    measured=inventory(f['root'])
                    self.current['inventories'].append({'attack':attack,'files':measured})
                    for p in f['root'].glob('sparse-*'):p.unlink()
            self.check('namespace/provenance refuses before SDK',r['sdk_open_attempts']==0 and P.read_state(f['target'])==before,r)
            reports.append({'attack':attack,'report':r})
        # Actual current-product v3 is not the test helper's synthetic anchor.
        # No existing pending data can manufacture a trusted baseline/ACK.
        f=self.seed(folder/'actual-product-v3')
        delta=f['folder']/'delta.exrpack'
        delta.write_bytes(P.L.build_pack([P.L.entry(P.L.book_record('additional','additional.txt'),P.L.TXT_OTHER)],[]))
        c=self.child([self.a.tool,'migrate','--target',str(f['target']),'--pack',str(delta),'--inject','precommit-cancel'],'actual-product-v3')
        self.check('real product cancellation produces v3',c.finish()==4,c.report())
        policy=Path(str(f['target'])+'.migration-pending.json')
        self.check('actual pending version three',json.loads(policy.read_bytes())['version']==3)
        protected={str(p):P.file_state(p) for p in f['folder'].iterdir() if p.is_file() and p.name.startswith('library.sqlite.')}
        before=P.read_state(f['target']);r=self.run(f,expect=False)
        self.check('real v3 cannot acquire synthetic provenance',r['sdk_open_attempts']==0 and r['reason']=='anchor-provenance-missing-or-invalid',r)
        c=self.child([self.a.tool,'recover-mirror','--target',str(f['target'])],'actual-product-v3-retry')
        self.check('unchanged product still refuses',c.finish()==5 and c.report()['code']=='recovery-unverified')
        self.check('real pending evidence and data retained',P.read_state(f['target'])==before and {p:P.file_state(Path(p)) for p in protected}==protected)
        reports.append({'attack':'actual-product-v3','report':r})
        return reports

    def execute(self,name,fn):
        item={'name':name,'passed':False,'checks':[],'inventories':[]};self.cases.append(item);self.current=item
        folder=self.a.work/name
        self.case_folder=folder;self.log_used=0;self.log_reserved=0
        before=inventory(self.a.work)
        occupied=max(sum(x['bytes'] for x in before),sum(x['allocated'] for x in before))
        capacity=(1024+16+64)*MIB
        if occupied+capacity>4*1024*MIB:
            item['error']='4GiB workspace cannot reserve next 1GiB case; no new fixture created';self.seal()
            raise SystemExit(item['error'])
        item['workspace_reservation_before_fixture']=capacity
        start=time.monotonic()
        def expired(signum,frame):raise TimeoutError('120-second top-level case deadline')
        old=signal.signal(signal.SIGALRM,expired);signal.alarm(120)
        try:
            item['result']=fn(folder)
            item['passed']=True
        except Exception as error:
            item['error']=repr(error);item['traceback']=traceback.format_exc()
        finally:
            signal.alarm(0);signal.signal(signal.SIGALRM,old)
            for c in self.children:
                if c.p.poll() is None:
                    try:c.finish(kill=True)
                    except Exception as error:item.setdefault('cleanup_errors',[]).append(repr(error));item['passed']=False
            self.children=[]
            item['seconds']=time.monotonic()-start
            if folder.exists():item['inventory']=inventory(folder)
            # Finite workspace budget. Do not erase failed evidence to continue.
            all_files=inventory(self.a.work)
            total=sum(x['bytes'] for x in all_files)
            allocated=sum(x['allocated'] for x in all_files)
            item['workspace_bytes']=total;item['workspace_allocated']=allocated
            if max(total,allocated)>4*1024*MIB:
                item['passed']=False;item['workspace_budget_exceeded']=True
            self.seal()
            print(json.dumps({'case':name,'passed':item['passed'],'checks':len(item['checks']),'error':item.get('error'),'seconds':item['seconds']}),flush=True)
            if item.get('workspace_budget_exceeded'):raise SystemExit('workspace cap; retained evidence, no further fixtures')

    def seal(self):
        evidence={'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],
                  'platform':os.environ['RUNNER_OS'],'cases':self.cases,'passed':len(self.cases)==22 and all(c['passed'] for c in self.cases),
                  'new_top_level_expected':22,'physical_cleanup_verified':False,'historical_rollback_proved':False,
                  'product_admission':False,'full_p0_acceptance':False,
                  'scope':'isolated POSIX guard-aware logical succession, title/ledger proxy only',
                  'limits':{'job_minutes':30,'case_seconds':120,'child_seconds':30,'evidence_bytes':512*MIB,'workspace_bytes':4*1024*MIB},
                  'remaining':['Windows protocol not qualified','no real product dispatch/importer integration','old v3 cannot acquire provenance',
                               'no power-loss or physical cleanup proof','trusted namespace custody, not hostile same-user CAS',
                               'old preflight capture backup_step(-1) unchanged; new resource mode bounds are separate']}
        serialized=(json.dumps(evidence,indent=2)+'\n').encode()
        assert len(serialized)<=64*MIB,'bounded aggregate evidence receipt'
        (self.a.work/'evidence.json').write_bytes(serialized)


def main():
    ap=argparse.ArgumentParser()
    for key in ('handoff','probe','tool','old-tool'):ap.add_argument('--'+key,required=True)
    ap.add_argument('--work',type=Path,required=True)
    a=ap.parse_args()
    for key in ('handoff','probe','tool','old_tool'):setattr(a,key,str(Path(getattr(a,key)).resolve()))
    os.umask(0o077);a.work=a.work.resolve();a.work.mkdir(mode=0o700,parents=True,exist_ok=False)
    d=Driver(a)
    for schema in (6,7):
        for journal in ('delete','wal'):
            d.execute('R-C-schema%d-%s'%(schema,journal),lambda f,s=schema,j=journal:d.end_to_end(f,s,j))
    for phase in ('S1','S2','S3','S4','S5','S6','S7','S8'):
        d.execute('crash-'+phase,lambda f,p=phase:d.crash(f,p))
    for name,fn in (
        ('entrypoint-guard',d.gates),('lifetime-lease',d.lifetime),('later-writer-ABA',d.later),
        ('foreign-artifacts',d.foreign),('native-mirror-refusal',d.publication_refusal),
        ('sync-uncertainty',d.sync_failure),('ack-scanner-uncertainty',d.acknowledgment),
        ('literal-DELETE-rollback',d.native_rollback),('bounded-backup',d.resources),
        ('privacy-namespace-bytes',d.namespace)):
        d.execute(name,fn)
    d.seal()
    passed=sum(c['passed'] for c in d.cases)
    print('HANDOFF TOTAL %d/22; protocol-only; product_admission=false; full_p0_acceptance=false'%passed,flush=True)
    raise SystemExit(0 if len(d.cases)==22 and passed==22 else 1)


if __name__=='__main__':main()
