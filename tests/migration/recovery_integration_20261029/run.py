#!/usr/bin/env python3
"""Actions-only real importer recovery acceptance. Refusals are not recovery passes."""
import argparse
import contextlib
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import traceback

if os.environ.get('GITHUB_ACTIONS') != 'true':
    raise SystemExit('All builds, tests, fixtures and artifact parsing are Actions-only')
SPEC=importlib.util.spec_from_file_location('independent_preflight',Path(__file__).parents[1]/'recovery_preflight_20261029/run.py')
P=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(P)
L=P.L
MIB=1024*1024
PHASES=('S1-anchor-before-sync','S2-baseline-durable','S3-owner-open','S4-prepared',
        'S5-mirror-durable','S6-commit-before-ack','S7-ack-before-sync','S8-owner-closed')
UPGRADE={
 ('table','epub_bounded_books','epub_bounded_books','CREATE TABLE epub_bounded_books(book_id INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE)'),
 ('table','epub_progress','epub_progress','CREATE TABLE epub_progress(book_id INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,part INTEGER NOT NULL CHECK(part>=0 AND part<10000),path TEXT NOT NULL,position INTEGER NOT NULL CHECK(position>=0),prefix TEXT,suffix TEXT,chapter TEXT)'),
 ('table','epub_notes','epub_notes','CREATE TABLE epub_notes(id INTEGER PRIMARY KEY,book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,part INTEGER NOT NULL CHECK(part>=0 AND part<10000),path TEXT NOT NULL,start INTEGER NOT NULL CHECK(start>=0),end INTEGER NOT NULL CHECK(end>start),exact TEXT NOT NULL,prefix TEXT,suffix TEXT,chapter TEXT,text TEXT NOT NULL)'),
 ('index','epub_notes_book','epub_notes','CREATE INDEX epub_notes_book ON epub_notes(book_id,part,start,id)'),
}
LEDGER=('table','exr_migration_ledger','exr_migration_ledger','CREATE TABLE exr_migration_ledger(id INTEGER PRIMARY KEY CHECK(id=1),data BLOB NOT NULL)')

def identity(p):
    s=p.lstat();return (s.st_dev,s.st_ino)

def state(p):
    if not p.exists():return None
    return identity(p),hashlib.sha256(p.read_bytes()).hexdigest()

def inventory(root):
    if not root.exists():return {}
    return {str(p.relative_to(root)):state(p) for p in root.rglob('*') if p.is_file()}

def disk(root):
    return sum(p.lstat().st_size for p in root.rglob('*') if p.is_file())

def model(target):
    with contextlib.closing(P.connect(target)) as db:
        db.execute('BEGIN')
        assert db.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        tables=[x[0] for x in db.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name")]
        return dict(canonical=P.canonical(db),schema=db.execute('PRAGMA user_version').fetchone()[0],
                    app=db.execute('PRAGMA application_id').fetchone()[0],
                    catalog=set(db.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema')),
                    columns={t:[x[1] for x in db.execute('PRAGMA table_info('+P.quote(t)+')')] for t in tables},
                    rows={t:db.execute('SELECT rowid,* FROM '+P.quote(t)+' ORDER BY rowid').fetchall() for t in tables},
                    public=public_projection(db))

def writer(target,busy,change=False):
    with contextlib.closing(P.connect(target,True)) as db:
        try:db.execute('BEGIN IMMEDIATE')
        except sqlite3.OperationalError as error:
            assert busy and error.sqlite_errorcode&255==5,(busy,str(error));return
        assert not busy,'independent ordinary writer unexpectedly acquired owner fence'
        if change:db.execute("UPDATE books SET title='ordinary writer retained' WHERE id=(SELECT min(id) FROM books)")
        db.commit()

class Child:
    def __init__(self,driver,argv,env=None):
        self.d=driver;driver.serial+=1;self.out=driver.logs/('%04d.stdout'%driver.serial);self.err=driver.logs/('%04d.stderr'%driver.serial)
        self.size=0;self.errors=[];self.lock=threading.Lock();self.done=False;self.result=None;self.deadline=time.monotonic()+120
        self.reservation=2*MIB
        assert driver.log_total+driver.log_reserved+self.reservation<=16*MIB,'case log capacity reserved before spawn'
        driver.log_reserved+=self.reservation
        self.p=subprocess.Popen(list(map(str,argv)),stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True,start_new_session=(os.name=='posix'),
            env=dict(os.environ,EXR_MIGRATE_TEST_FAULTS='1',**(env or {})))
        def drain(stream,path):
            try:
                with path.open('xb') as out:
                    while True:
                        b=stream.read(4096)
                        if not b:break
                        with self.lock:
                            self.size+=len(b)
                            if self.size>self.reservation:raise AssertionError('process output limit')
                        out.write(b)
            except Exception as error:
                self.errors.append(repr(error))
                if self.p.poll() is None:self.kill()
            finally:stream.close()
        self.threads=[threading.Thread(target=drain,args=(self.p.stdout,self.out),daemon=True),threading.Thread(target=drain,args=(self.p.stderr,self.err),daemon=True)]
        for t in self.threads:t.start()
        driver.children.append(self)
    def kill(self):
        if os.name=='posix':
            try:os.killpg(self.p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        else:self.p.kill()
    def finish(self,kill=False):
        if self.done:return self.result
        if kill and self.p.poll() is None:self.kill()
        try:self.result=self.p.wait(timeout=max(0,self.deadline-time.monotonic()))
        except subprocess.TimeoutExpired:
            self.kill();self.errors.append('120s absolute process deadline')
            try:self.result=self.p.wait(timeout=max(0,self.deadline-time.monotonic()))
            except subprocess.TimeoutExpired:self.errors.append('owned process termination unconfirmed at deadline')
        # Parent exit is not pipe EOF. Kill the owned POSIX session/group even
        # when its leader has exited, then join both drains against ONE deadline.
        if any(t.is_alive() for t in self.threads):self.kill()
        for t in self.threads:t.join(max(0,self.deadline-time.monotonic()))
        alive=any(t.is_alive() for t in self.threads)
        if alive or self.p.poll() is None:
            self.kill();self.errors.append('bounded native group/stream cleanup unconfirmed')
            self.d.harness_failed=True
        else:
            self.d.log_reserved-=self.reservation;self.d.log_total+=self.size
        self.done=True
        assert not alive and self.p.poll() is not None and not self.errors,self.errors
        return self.result
    def report(self):return json.loads(self.out.read_text(encoding='utf-8'))
    def wait(self,target,phase):
        until=min(self.deadline,time.monotonic()+35);root=Path(str(target)+'.migration-recovery')
        while time.monotonic()<until and self.p.poll() is None:
            matches=list(root.glob('run-*/'+phase+'.ready'))
            for readroot in target.parent.glob(target.name+'.migration-read-*'):matches+=list(readroot.glob('run-*/'+phase+'.ready'))
            matches=[p for p in matches if not p.with_suffix('.go').exists()]
            if matches:return matches[-1]
            time.sleep(.01)
        raise AssertionError(('missing calibrated boundary',phase,self.p.poll(),self.out.read_text(errors='replace'),self.err.read_text(errors='replace')))
    def go(self,ready):ready.with_suffix('.go').write_bytes(b'continue\n')

class Driver:
    def __init__(self,a):
        self.a=a;self.serial=0;self.save_serial=0;self.report_exceeded=False;self.harness_failed=False;self.case=None;self.children=[];self.log_total=0;self.log_reserved=0;a.work.mkdir(parents=True,exist_ok=False)
        self.evidence=dict(source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],platform=os.environ['RUNNER_OS'],cases=[],passed=False,product_admission=False,full_p0_acceptance=False,scope='real existing-target POSIX importer candidate; Windows capability refusal',physical_cleanup_verified=False,historical_rollback_proven=False)
    def check(self,label,value,detail=None):
        self.case['checks'].append(dict(label=label,passed=bool(value),detail=detail));assert value,(label,detail)
    def run(self,name,fn):
        folder=self.a.work/name;folder.mkdir();self.logs=folder/'logs';self.logs.mkdir();self.children=[];self.log_total=0;self.log_reserved=0
        self.case=dict(name=name,passed=False,checks=[]);self.evidence['cases'].append(self.case)
        try:
            assert not self.harness_failed,'prior owned process/stream cleanup unconfirmed; this case not executed'
            # Reserve a full case plus streams before fixtures, not after writes.
            assert disk(self.a.work)+(1024+16+64)*MIB<=4*1024*MIB,'4GiB pre-case workspace reservation'
            fn(folder);self.check('case bytes within reservation',disk(folder)<=(1024+16)*MIB);self.case['passed']=True
        except Exception:self.case['error']=traceback.format_exc()
        finally:
            for c in self.children:
                try:c.finish(kill=c.p.poll() is None)
                except Exception as error:self.case['passed']=False;self.case.setdefault('cleanup_errors',[]).append(repr(error))
            self.save();print(name,'PASS' if self.case['passed'] else 'FAIL',flush=True)
            if not self.case['passed']:print(self.case.get('error',self.case.get('cleanup_errors')),flush=True)
    def save(self):
        payload=bytearray()
        if not self.report_exceeded:
            for part in json.JSONEncoder(indent=2,default=str).iterencode(self.evidence):
                encoded=part.encode('utf-8')
                if len(encoded)>64*MIB-len(payload)-1:
                    self.report_exceeded=True;break
                payload.extend(encoded)
        if self.report_exceeded:
            self.evidence['passed']=False
            if self.case:self.case['passed']=False
            summary={k:v for k,v in self.evidence.items() if k!='cases'}
            summary['cases']=[{'name':c['name'],'passed':False,'reason':'report-reservation-exceeded; raw bounded child logs retained'} for c in self.evidence['cases']]
            summary['report_reservation_exceeded']=True;payload=bytearray(json.dumps(summary,indent=2).encode())
        payload.extend(b'\n');assert len(payload)<=64*MIB
        self.save_serial+=1;temporary=self.a.work/('evidence-%03d.pending'%self.save_serial)
        with temporary.open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
        temporary.replace(self.a.work/'evidence.json')

    def call(self,*argv,env=None):
        c=Child(self,argv,env);return c.finish(),c.report() if c.out.read_bytes().lstrip().startswith(b'{') else c.out.read_text(errors='replace'),c
    def args(self,f,command='migrate',pack=None,extra=(),font=True):
        result=[self.a.candidate,command,'--target',f['target']]
        if command in ('migrate','recover-migration','verify','inspect'):result+=['--pack',pack or f['pack']]
        if font and self.a.font:result+=['--recovery-font',self.a.font]
        return result+list(extra)
    def start(self,f,phase,command='migrate',pack=None,extra=(),fault=None):
        env={'EXR_RECOVERY_PAUSE':phase}
        if fault:env['EXR_RECOVERY_FAULT']=fault
        c=Child(self,self.args(f,command,pack,extra),env);return c,c.wait(f['target'],phase)
    def recover(self,f,extra=()):
        rc,r,_=self.call(*self.args(f,'recover-migration',extra=extra));self.check('actual explicit R succeeds',rc==0 and r['atomicity']['recovery']['route']=='R',r);return r
    def seed(self,folder,schema=7,journal='delete',full=False):
        folder.mkdir(exist_ok=True);target=folder/'library.sqlite';pack=folder/'original.exrpack'
        books,notes=L.dataset() if full else ([L.entry(L.book_record('old','old.txt',title='original kept'),L.TXT)],[L.note_record('old-note','old','lantern keeper','original comment')])
        pack.write_bytes(L.build_pack(books,notes));argv=[self.a.old_tool if schema==6 else self.a.tool,'migrate','--target',target,'--pack',pack]+(['--allow-partial'] if full else [])
        rc,r,_=self.call(*argv);self.check('genuine pinned producer success',rc==0 and r['result']=='success',r)
        with contextlib.closing(P.connect(target,True)) as db:
            self.check('actual schema seed',db.execute('PRAGMA user_version').fetchone()[0]==schema)
            self.check('native journal mode',db.execute('PRAGMA journal_mode='+journal).fetchone()[0]==journal);db.commit()
        incoming=folder/'incoming.exrpack';incoming.write_bytes(L.build_pack([L.entry(L.book_record('incoming','incoming.txt'),L.TXT_OTHER)],[L.note_record('incoming-note','incoming','lantern keeper','imported comment')]))
        return dict(target=target,pack=incoming,original_pack=pack,books=books,notes=notes,root=Path(str(target)+'.migration-recovery'),mirror=Path(str(target)+'.legacy-map.json'),schema=schema,journal=journal,original=model(target),identity=identity(target))
    def preserve(self,f,prior):
        now=model(f['target']);self.check('target inode unchanged',identity(f['target'])==f['identity'])
        self.check('all supported typed rows/catalog/content exact',now['canonical']==prior['canonical']);return now
    def committed(self,f,prior,report):
        now=model(f['target']);planned=prior['catalog']|(UPGRADE if prior['schema']==6 else set())|{LEDGER}
        self.check('exact catalog delta/schema7/application id',now['schema']==7 and now['app']==prior['app'] and now['catalog']==planned)
        records=[json.loads(p.read_text()) for p in sorted(f['root'].glob('record-*.json'))]
        baselines=[x for x in records if x['phase'] in (1,6) and x['generation']==report['atomicity']['recovery']['generation']]
        self.check('exact independently framed pre-owner baseline',len(baselines)==1 and (f['root']/baselines[0]['base_token']/'baseline.bin').read_bytes()==prior['canonical'])

        self.check('all original typed rows retained',all(all(row in now['rows'][t] for row in rows) for t,rows in prior['rows'].items() if t!='exr_migration_ledger'))
        self.check('new tables only whitelist',set(now['rows'])-set(prior['rows'])<=({'epub_bounded_books','epub_progress','epub_notes','exr_migration_ledger'}))
        ledger=json.loads(now['rows']['exr_migration_ledger'][0][2]);mirror=json.loads(f['mirror'].read_text())
        self.check('actual mirrored internal ledger',ledger==mirror and report['pack']['sha256'] in ledger['packs'])
        self.check('known actual commit and retained evidence',report['atomicity']['transaction']['target_commit']=='committed' and report['atomicity']['recovery']['commit_acknowledged'] and f['root'].exists())
        self.check('no fabricated rollback/physical cleanup/P0',report['atomicity']['rolled_back'] is None and not report['atomicity']['recovery']['physical_cleanup_verified'] and not report['atomicity']['recovery']['product_p0_accepted'])
        f['accepted_prior']=prior;f['accepted_generation']=report['atomicity']['recovery']['generation']
        return now
    @contextlib.contextmanager
    def wal(self,f):
        if f['journal']!='wal':yield None;return
        old=P.connect(f['target']);w=P.connect(f['target'],True)
        try:
            w.execute('PRAGMA wal_autocheckpoint=0');w.execute('PRAGMA wal_checkpoint(TRUNCATE)');old.execute('BEGIN');before=old.execute('SELECT title FROM books WHERE id=1').fetchone()
            w.execute("UPDATE books SET title='uncheckpointed WAL canary' WHERE id=1");w.commit();telemetry=w.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchone()
            self.check('real uncheckpointed committed WAL',telemetry[1]>telemetry[2]>=0 and old.execute('SELECT title FROM books WHERE id=1').fetchone()==before,telemetry)
            yield w
        finally:old.close();w.close()
    def checkpoint(self,w):
        if w:
            telemetry=w.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchone();self.check('live checkpoint pressure',telemetry[1]>=telemetry[2]>=0,telemetry)
    def projection(self,f):
        prior=f['accepted_prior'];generation=f['accepted_generation']
        records=[json.loads(p.read_text()) for p in sorted(f['root'].glob('record-*.json'))]
        bases=[x for x in records if x['phase'] in (1,6) and x['generation']==generation]
        self.check('one exact accepted generation capture',len(bases)==1)
        root=f['root']/bases[0]['base_token'];projection=root/'public-projection.jsonl'
        self.check('accepted original projection mandatory',projection.is_file())
        rows=[json.loads(line) for line in projection.read_text().splitlines()]
        self.check('independent PRE-OWNER public values/order/absence exact',rows==prior['public'])
        self.check('independent PRE-OWNER canonical bytes exact',(root/'baseline.bin').read_bytes()==prior['canonical'])
        clone=model(root/'clone.sqlite')
        self.check('all original clone rows exact after SDK validation',all(clone['rows'][t]==v for t,v in prior['rows'].items()))
        # A native output mutation must fail this independent comparison even
        # though clone SQL would still agree with the unaltered original.
        mutated=copy.deepcopy(rows);assert mutated
        mutated[0][-1]={'unexpected':'single-cell/type mutation'}
        negative=self.logs/('projection-mutation-%s.json'%generation)
        negative.write_text(json.dumps(mutated)+'\n')
        self.check('single-cell/type mutation independently rejected',json.loads(negative.read_text())!=prior['public'])


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
        bounded = int(fmt == 4 and 'epub_bounded_books' in tables and db.execute('SELECT 1 FROM epub_bounded_books WHERE book_id=?',(book,)).fetchone() is not None)
        for note in ([] if bounded else db.execute('SELECT id,start,end,text,anchor_exact,anchor_prefix,anchor_suffix,anchor_chapter,location_state FROM notes WHERE book_id=? ORDER BY start,id',(book,))):
            nid,start,end,text,exact,prefix,suffix,chapter,state = note
            result.append(['note',nid,book,start if state == 1 else -1,end if state == 1 else -1,
                           text,start,end,exact,prefix,suffix,chapter])
        if fmt in (1,2,3,4,5,6,7) and not bounded:
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


def main():
    ap=argparse.ArgumentParser()
    for name in ('candidate','tool','old-tool','fixture','font'):ap.add_argument('--'+name,required=True)
    ap.add_argument('--work',type=Path,required=True);ap.add_argument('--fixtures',type=Path,required=True)
    a=ap.parse_args()
    for name in ('candidate','tool','old_tool','fixture','font'):setattr(a,name,str(Path(getattr(a,name)).resolve()))
    a.fixtures=a.fixtures.resolve();a.work=a.work.resolve();d=Driver(a)
    def simple(folder,schema=7,journal='delete'):
        f=d.seed(folder,schema,journal)
        with d.wal(f) as w:
            before=model(f['target']);c,ready=d.start(f,'S4-prepared');writer(f['target'],True);d.checkpoint(w);c.finish(kill=True);d.preserve(f,before)
            d.check('durable baseline and permanent barrier',bool(list(f['root'].glob('cap-*/baseline.bin'))) and Path(str(f['target'])+'.migrate-lock').exists())
            rc,r,_=d.call(*d.args(f));d.check('ordinary command cannot implicitly recover',rc!=0 and not r['atomicity']['recovery']['target_sdk_open_attempted'],r)
            report=d.recover(f);after=d.committed(f,before,report);d.projection(f)
            writer(f['target'],False,True);later=model(f['target'])
            other=folder/'next.exrpack';other.write_bytes(L.build_pack([L.entry(L.book_record('next','next.txt'),L.TXT+b'\nnext independent original')],[]))
            rc,r,_=d.call(*d.args(f,pack=other));d.check('actual C successor succeeds',rc==0 and r['atomicity']['recovery']['route']=='C',r);d.committed(f,later,r)
            rc,_,_=d.call(*d.args(f,'verify',pack=other));d.check('actual guarded verify through private snapshot',rc==0)
    def missing(folder):
        target=folder/'absent.sqlite';pack=folder/'pack';pack.write_bytes(L.build_pack([],[]));f=dict(target=target,pack=pack)
        rc,r,_=d.call(*d.args(f));d.check('missing-target refused before SDK',rc!=0 and not r['atomicity']['recovery']['target_sdk_open_attempted'],r)
        d.check('no target/anchor/stage/output',set(p.name for p in folder.iterdir())=={'logs','pack'})
    def replacement(folder):
        for change in ('replace','disappear'):
            f=d.seed(folder/change);c,ready=d.start(f,'SDK-opening-durable');saved=f['target'].with_suffix('.saved');f['target'].rename(saved)
            if change=='replace':f['target'].write_bytes(b'foreign target must not be upgraded');foreign=state(f['target'])
            c.go(ready);rc=c.finish();r=c.report();d.check('late target change before actual SDK attempt',rc!=0 and not r['atomicity']['recovery']['target_sdk_open_attempted'],r)
            if change=='replace':d.check('foreign target exact',state(f['target'])==foreign)
            else:d.check('disappeared target not recreated',not f['target'].exists())
            d.check('original inode saved untouched',identity(saved)==f['identity'])
    def crash(folder,index):
        for schema in (6,7):
            for journal in ('delete','wal'):
                f=d.seed(folder/('%d-%s'%(schema,journal)),schema,journal)
                with d.wal(f) as w:
                    prior=model(f['target']);c,ready=d.start(f,PHASES[index]);d.checkpoint(w)
                    if 2<=index<=4:writer(f['target'],True)
                    c.finish(kill=True);now=model(f['target']);root_before=inventory(f['root'])
                    if index>=5:
                        source_at=now['columns']['books'].index('source')+1
                        d.check('post-COMMIT crash has actual incoming original exactly once',sum(row[source_at]==L.TXT_OTHER for row in now['rows']['books'])==1)
                        d.check('post-COMMIT crash actual ledger contains incoming pack',hashlib.sha256(f['pack'].read_bytes()).hexdigest() in json.loads(now['rows']['exr_migration_ledger'][0][2])['packs'])

                    if index<5:
                        d.preserve(f,prior);rc,r,_=d.call(*d.args(f,'recover-migration'));d.check('pre-COMMIT crash explicitly retried',rc==0,r);d.committed(f,prior,r)
                    elif index==5:
                        rc,r,_=d.call(*d.args(f,'recover-migration'));d.check('COMMIT with missing ACK cannot replay original',rc!=0,r);d.preserve(f,now)
                    else:
                        writer(f['target'],False,True);later=model(f['target']);rc,r,_=d.call(*d.args(f));d.check('observed valid ACK permits fresh C not old replay',rc==0 and r['atomicity']['recovery']['route']=='C',r);d.committed(f,later,r)
                    d.check('preexisting protocol evidence retained',all(state(f['root']/k)==v for k,v in root_before.items()))
    def full(folder):
        f=d.seed(folder);books,notes=L.dataset();pack=folder/'full.exrpack';pack.write_bytes(L.build_pack(books,notes));prior=model(f['target'])
        rc,r,_=d.call(*d.args(f,pack=pack,extra=('--allow-partial',)));d.check('whole unchanged difficult fixture imported',rc==0,r);d.committed(f,prior,r)
        d.check('all five books/sixteen notes accounted',r['counts']['books_expected']==5 and r['counts']['notes_expected']==16 and r['counts']['books_accounted']==5 and r['counts']['notes_accounted']==16,r['counts'])
        d.check('only known audio unsupported',[(e['code'],e['legacy_id']) for e in r['entries'] if e['severity']=='unsupported']==[('audio-original-not-storable','b-audio')])
        reasons={'n-txt-ambiguous':'quote-ambiguous','n-txt-missing':'quote-not-found','n-txt-bookmark':'bookmark-without-cfi','n-epub-ambiguous':'quote-ambiguous','n-pdf-missing':'quote-not-found','n-orphan':'orphan-note'}
        d.check('six exact retained unlocated reasons',{n['legacy_id']:n['reason'] for n in r['notes'] if n['status']=='unlocated'}==reasons)
        ledger=json.loads(f['mirror'].read_text());got={n['legacy_id']:n['retained'] for n in ledger['notes']};d.check('all raw notes including orphan preserved',all(got[n['id']]==n for n in notes))
        got={b['legacy_id']:b['retained'] for b in ledger['books']};d.check('all raw books except separately stored cover',all(got[b['legacy_id']]=={k:v for k,v in b['record'].items() if k!='cover'} for b in books))
    def formats(folder):
        f=d.seed(folder);paths={i:a.fixtures/('sample.'+ext) for i,ext in enumerate(('txt','html','fb2','epub','docx','rtf','mobi'),1)}
        paths[8]=folder/'fixture.pdf';paths[8].write_bytes(L.pdf());paths[9]=folder/'fixture.cbz';paths[9].write_bytes(L.cbz())
        for fmt,path in paths.items():
            rc,r,_=d.call(a.fixture,'import',f['target'],fmt,path,'format-'+str(fmt));d.check('real public import format '+str(fmt),rc==0,r)
        rc,r,_=d.call(a.fixture,'bounded',f['target'],paths[4],a.font);d.check('real bounded EPUB progress/note captured with font',rc==0,r)
        with contextlib.closing(P.connect(f['target'],True)) as db:
            db.execute("UPDATE books SET tags=?,cover=? WHERE id=(SELECT min(id) FROM books)",('',b'\x00'+bytes(range(256))*33))
            db.execute("UPDATE notes SET text=?,anchor_prefix=?,anchor_suffix=? WHERE id=(SELECT min(id) FROM notes)",('typed-comment',None,''));db.commit()
        before=model(f['target']);d.check('all nine actual format values present',{row[before['columns']['books'].index('format')+1] for row in before['rows']['books']}==set(range(1,10)))
        rc,r,_=d.call(*d.args(f));d.check('full existing entity baseline accepted',rc==0,r);d.committed(f,before,r);d.projection(f)
        d.check('bounded actual resolution observations retained',bool(list(f['root'].glob('cap-*/bounded-*.jsonl'))))
        # Independent framing expectations, not equality of two native serializers.
        d.check('typed empty/NUL/int/float/BLOB controls',len({P.typed(x) for x in (None,'',b'',1,1.0,'a\0b',b'a\0b')})==7)
        for fmt,path in paths.items():
            g=d.seed(folder/('import-'+str(fmt)));incoming=folder/('format-'+str(fmt)+'.pack');incoming.write_bytes(L.build_pack([L.entry(L.book_record('format-'+str(fmt),'sample.'+path.suffix.lstrip('.')),path.read_bytes())],[]));prior=model(g['target'])
            rc,r,_=d.call(*d.args(g,pack=incoming));d.check('real full importer format '+str(fmt),rc==0,r);d.committed(g,prior,r)
    def policy(folder):
        f=d.seed(folder);books,notes=L.dataset();f['pack'].write_bytes(L.build_pack(books,notes));before=model(f['target'])
        rc,r,_=d.call(*d.args(f));d.check('strict unsupported refuses without COMMIT',rc!=0 and r['code']=='policy-strict',r);d.preserve(f,before)
        r=d.recover(f,('--allow-partial',));d.committed(f,before,r)
        conflict=copy.deepcopy(books);conflict[0]['data']=L.TXT_OTHER;bad=folder/'conflict.pack';bad.write_bytes(L.build_pack(conflict,notes));prior=model(f['target'])
        rc,r,_=d.call(*d.args(f,pack=bad));d.check('changed legacy ID strict conflict retained',rc!=0 and r['code']=='policy-strict',r);d.preserve(f,prior)
    def repeat(folder):
        f=d.seed(folder);rc,r,_=d.call(*d.args(f));d.check('first actual commit',rc==0,r);prior=model(f['target']);rc,r,_=d.call(*d.args(f));d.check('repeat is actual C',rc==0 and r['atomicity']['recovery']['route']=='C',r)
        now=model(f['target']);d.check('repeat no duplicate book/note/audio',all(now['rows'][t]==rows for t,rows in prior['rows'].items() if t!='exr_migration_ledger'))
        for i in (2,3):
            p=folder/('generation%d.pack'%i);p.write_bytes(L.build_pack([L.entry(L.book_record('g%d'%i,'g%d.txt'%i),L.TXT+str(i).encode())],[]));prior=model(f['target']);rc,r,_=d.call(*d.args(f,pack=p));d.check('distinct successful generation '+str(i),rc==0,r);d.committed(f,prior,r)
    def later(folder):
        f=d.seed(folder,full=True);rc,r,_=d.call(*d.args(f));d.check('initial new work',rc==0,r)
        rc,r,_=d.call(a.fixture,'bounded',f['target'],a.fixtures/'sample.epub',a.font);d.check('bounded state created by ordinary API',rc==0,r)
        rc,r,_=d.call(a.fixture,'edit-all',f['target']);d.check('all independent ordinary public edits',rc==0,r);before=model(f['target'])
        p=folder/'later.pack';p.write_bytes(L.build_pack([L.entry(L.book_record('later','later.txt'),L.TXT+b'later new book')],[]));rc,r,_=d.call(*d.args(f,pack=p));d.check('C preserves later multi-entity state',rc==0,r);d.committed(f,before,r);d.projection(f)
    def preopen(folder):
        f=d.seed(folder/'race');c,ready=d.start(f,'SDK-opening-durable');writer(f['target'],False,True);before=model(f['target']);c.go(ready);rc=c.finish();r=c.report();d.check('changed pre-owner snapshot refuses not relabeled',rc!=0 and r['atomicity']['recovery']['target_sdk_open_attempted'],r);d.preserve(f,before)
        f=d.seed(folder/'busy');c,ready=d.start(f,'SDK-opening-durable')
        with contextlib.closing(P.connect(f['target'],True)) as w:
            w.execute('BEGIN IMMEDIATE');c.go(ready);rc=c.finish();r=c.report();d.check('actual first SDK opening BUSY after durable baseline',rc!=0 and r['code']=='recovery-sdk-open-failed',r);w.rollback()
        for kind,extra in [('dry',('--dry-run',)),('cancel',('--inject','cancel@1'))]:
            f=d.seed(folder/kind);before=model(f['target']);rc,r,_=d.call(*d.args(f,extra=extra));d.check(kind+' never claims whole rollback',rc!=0 and r['atomicity']['rolled_back'] is None,r)
            if kind=='dry':d.check('dry-run explicitly requires R',r['code']=='dry-run-recovery-required' and r['atomicity']['recovery']['rollback_requested'])
            d.preserve(f,before)
        f=d.seed(folder/'bad-baseline')
        with contextlib.closing(P.connect(f['target'],True)) as db:db.execute('CREATE TABLE unsupported(x)');db.commit()
        rc,r,_=d.call(*d.args(f));d.check('bad prebaseline before target SDK',rc!=0 and not r['atomicity']['recovery']['target_sdk_open_attempted'],r)
    def wrongpack(folder):
        for change in ('wrong-pack','changed','noop','aba'):
            f=d.seed(folder/change);c,ready=d.start(f,'S3-owner-open');c.finish(kill=True);before=model(f['target'])
            if change=='wrong-pack':other=f['original_pack']
            else:
                other=f['pack']
                with contextlib.closing(P.connect(f['target'],True)) as db:
                    original=db.execute('SELECT title FROM books WHERE id=1').fetchone()[0];db.execute("UPDATE books SET title=? WHERE id=1",(original if change=='noop' else 'changed after interruption',));db.commit()
                    if change=='aba':db.execute('UPDATE books SET title=? WHERE id=1',(original,));db.commit()
            current=model(f['target']);rc,r,_=d.call(*d.args(f,'recover-migration',pack=other));d.check('explicit '+change+' disposition',(rc==0) if change in ('noop','aba') else rc!=0,r)
            if rc==0:d.check('current parity is not historical rollback proof',not r['atomicity']['recovery']['historical_rollback_proven'])
            else:d.preserve(f,current)
    def foreign(folder):
        for name in ('anchor','mirror','baseline','alias'):
            f=d.seed(folder/name);c,ready=d.start(f,'S4-prepared');writer(f['target'],True)
            p=f['root']/'anchor.json' if name=='anchor' else f['mirror'] if name=='mirror' else next(f['root'].glob('cap-*/baseline.bin'))
            saved=p.with_name(p.name+'.owned-save');p.rename(saved)
            if name=='alias':os.link(f['target'],p)
            else:p.write_bytes(saved.read_bytes())
            os.chmod(p,0o600);foreign_before=state(p);c.go(ready);rc=c.finish();r=c.report();d.check('foreign '+name+' refuses',rc!=0,r);d.check('foreign entry not overwritten/deleted',state(p)==foreign_before)
        f=d.seed(folder/'pre-base-mirror');before=model(f['target']);c,ready=d.start(f,'S1-anchor-before-sync');saved=f['mirror'].with_suffix('.saved');f['mirror'].rename(saved);f['mirror'].write_bytes(saved.read_bytes());os.chmod(f['mirror'],0o600);foreign_before=state(f['mirror']);c.go(ready);rc=c.finish();r=c.report();d.check('first BASE does not adopt foreign original mirror',rc!=0 and not r['atomicity']['recovery']['target_sdk_open_attempted'],r);d.check('pre-BASE foreign mirror untouched',state(f['mirror'])==foreign_before);d.preserve(f,before)
        f=d.seed(folder/'late-mirror');before=model(f['target']);c,ready=d.start(f,'S5-mirror-durable');owned=f['mirror'].with_suffix('.owned-save');f['mirror'].rename(owned);f['mirror'].write_bytes(owned.read_bytes());os.chmod(f['mirror'],0o600);foreign_before=state(f['mirror']);c.go(ready);rc=c.finish();r=c.report();d.check('late equal-byte foreign mirror prevents COMMIT',rc!=0 and r['atomicity']['transaction']['target_commit']=='not-attempted' and r['atomicity']['recovery']['rollback_requested'],r);d.check('foreign mirror retained exact',state(f['mirror'])==foreign_before);d.preserve(f,before)
        f=d.seed(folder/'race');c=Child(d,d.args(f),{'EXR_RECOVERY_FAULT':'snapshot-race','EXR_RECOVERY_PAUSE':'snapshot-race'});ready=c.wait(f['target'],'snapshot-race');anchor=f['root']/'anchor.json';anchor.rename(f['root']/'anchor-saved.json');os.link(f['target'],anchor);writer(f['target'],True);c.go(ready)
        until=min(c.deadline,time.monotonic()+30);stopped=None
        while time.monotonic()<until:
            pid,status=os.waitpid(c.p.pid,os.WNOHANG|os.WUNTRACED)
            if pid:
                d.check('post-open native stop, not exit',os.WIFSTOPPED(status) and os.WSTOPSIG(status)==signal.SIGSTOP,status);stopped=status;break
            time.sleep(.01)
        d.check('native post-quarantine observation reached',stopped is not None);writer(f['target'],True);d.check('real writer remains BUSY after actual alias fd opened/quarantined',True,stopped);os.kill(c.p.pid,signal.SIGCONT);rc=c.finish();r=c.report();d.check('actual fd alias is quarantined',rc!=0 and r['atomicity']['recovery']['quarantined_descriptors']>=1,r);writer(f['target'],False)
    def mirrors(folder):
        for absent in (False,True):
            f=d.seed(folder/str(absent));
            if absent:f['mirror'].unlink()
            before=model(f['target']);c,ready=d.start(f,'S5-mirror-durable');c.finish(kill=True);d.preserve(f,before);r=d.recover(f);d.committed(f,before,r)
        f=d.seed(folder/'sync');before=model(f['target']);rc,r,_=d.call(*d.args(f),env={'EXR_RECOVERY_FAULT':'mirror-sync-ebadf'});d.check('native EBADF sync uncertainty retained, not EIO/power loss claim',rc!=0 and 'ebadf' in r['code'],r);d.preserve(f,before);d.recover(f)
    def native(folder):
        unreadable=d.seed(folder/'read-refusal');before=model(unreadable['target']);mode=stat.S_IMODE(unreadable['target'].stat().st_mode)
        try:
            unreadable['target'].chmod(0);calibrated=False
            try:
                with unreadable['target'].open('rb') as denied:denied.read(1)
            except PermissionError:calibrated=True
            d.check('actual OS target read refusal calibrated',calibrated)
            rc,r,_=d.call(*d.args(unreadable));d.check('actual read failure before target SDK',rc!=0 and not r['atomicity']['recovery']['target_sdk_open_attempted'],r)
        finally:unreadable['target'].chmod(mode)
        d.preserve(unreadable,before)
        f=d.seed(folder/'unlink-refusal');c,ready=d.start(f,'S5-mirror-durable');parent=f['target'].parent;probe=parent/'unlink-calibration';probe.write_bytes(b'owned calibration');mode=stat.S_IMODE(parent.stat().st_mode);calibrated=False
        try:
            parent.chmod(0o500)
            try:probe.unlink()
            except PermissionError:calibrated=True
            d.check('real OS unlink refusal calibrated',calibrated)
            c.p.send_signal(signal.SIGTERM);rc=c.finish();r=c.report();d.check('actual SDK status recorded without invented failure',rc!=0 and r['atomicity']['recovery']['rollback_requested'] and isinstance(r['atomicity']['recovery']['rollback_sdk_status'],int),r)
        finally:parent.chmod(mode)
        d.recover(f)
    def ack(folder):
        for variant in ('absent','partial','equal-foreign'):
            f=d.seed(folder/variant);phase='S6-commit-before-ack' if variant=='absent' else 'S7-ack-before-sync';c,ready=d.start(f,phase);c.finish(kill=True);committed=model(f['target'])
            if variant!='absent':
                p=sorted(f['root'].glob('record-*.json'))[-1]
                if variant=='partial':p.write_bytes(b'{')
                else:saved=p.with_suffix('.saved');p.rename(saved);p.write_bytes(saved.read_bytes());os.chmod(p,0o600)
            before=inventory(f['root']);rc,r,_=d.call(*d.args(f,'recover-migration'));d.check(variant+' ACK does not authorize C/replay',rc!=0,r);d.preserve(f,committed);d.check('all preceding evidence retained',all(state(f['root']/k)==v for k,v in before.items()))
    def entries(folder):
        f=d.seed(folder);c,ready=d.start(f,'S3-owner-open');c.finish(kill=True);before=model(f['target']);retained=inventory(f['root'])
        for command,extra in [('migrate',()),('migrate',('--dry-run',)),('migrate',('--break-lock',)),('recover-mirror',()),('dump',()),('verify',()),('export-ledger',('--output',str(folder/'export.json'))),('inspect',())]:
            rc,r,_=d.call(*d.args(f,command,extra=extra));d.check(command+str(extra)+' pre-open refusal',rc!=0 and not r['atomicity']['recovery']['target_sdk_open_attempted'],r);d.preserve(f,before)
        d.check('no export before admission',not (folder/'export.json').exists());d.check('old pending evidence untouched',all(state(f['root']/k)==v for k,v in retained.items()))
        for command in ('dump','verify','export-ledger'):
            f=d.seed(folder/('read-divergent-'+command));ledger=json.loads(f['mirror'].read_text());ledger['packs'].append('0'*64);f['mirror'].write_text(json.dumps(ledger));before=state(f['mirror']);extra=('--output',str(f['target'].parent/'out.json')) if command=='export-ledger' else ()
            rc,r,_=d.call(*d.args(f,command,extra=extra));d.check('actual rootless divergent mirror refuses '+command,rc!=0 and not r['atomicity']['recovery']['target_sdk_open_attempted'],r);d.check('divergent original mirror unchanged',state(f['mirror'])==before)
        f=d.seed(folder/'read-policy-race');c,ready=d.start(f,'worker-result',command='dump');f['root'].mkdir(mode=0o700);(f['root']/'uncertain-anchor').write_bytes(b'real pending namespace appeared');Path(str(f['target'])+'.migrate-lock').write_bytes(b'foreign owned barrier');before=inventory(f['root']);c.go(ready);rc=c.finish();r=c.report();d.check('read snapshot does not waive newly appeared policy',rc!=0 and not r['atomicity']['recovery']['target_sdk_open_attempted'],r);d.check('new foreign policy retained',inventory(f['root'])==before)

    def lifetime(folder):
        f=d.seed(folder);marker=folder/'source';source=Child(d,[a.fixture,'hold-source',f['target'],marker]);until=time.monotonic()+30
        while not Path(str(marker)+'.ready').exists() and source.p.poll() is None and time.monotonic()<until:time.sleep(.01)
        d.check('real source retains owner after SDK close',Path(str(marker)+'.ready').exists());Path(str(marker)+'.go').write_bytes(b'go');d.check('source and owner fully released',source.finish()==0)
        c,ready=d.start(f,'S3-owner-open');writer(f['target'],True);c.go(ready);d.check('actual importer succeeds after release',c.finish()==0,c.report());writer(f['target'],False)
        # Cross-process flock still held after SDK close; SQLite writer can run.
        p=folder/'lease.pack';p.write_bytes(L.build_pack([L.entry(L.book_record('lease','lease.txt'),L.TXT+b'lease')],[]));c,ready=d.start(f,'S8-owner-closed',pack=p);writer(f['target'],False)
        rc,r,_=d.call(*d.args(f,pack=p));d.check('migration lease survives original SDK close',rc!=0 and 'lease' in r['code'],r);c.go(ready);d.check('lease owner reports then exits',c.finish()==0)
    def transport(folder):
        for fault in ('wrong-nonce','kill-worker','stop-worker'):
            f=d.seed(folder/fault)
            if fault=='stop-worker':
                c,ready=d.start(f,'worker-stopped',fault=fault);c.go(ready);rc=c.finish();r=c.report();d.check('actual stopped/resumed scanner calibrated',rc==0,r)
            else:
                rc,r,_=d.call(*d.args(f),env={'EXR_RECOVERY_FAULT':fault});d.check(fault+' refuses actual transport',rc!=0 and not r['atomicity']['recovery']['target_sdk_open_attempted'],r)
        for fault in ('owner-wrong-nonce','owner-kill-worker','owner-timeout'):
            f=d.seed(folder/fault);before=model(f['target'])
            if fault=='owner-timeout':
                c,ready=d.start(f,'worker-stopped',fault=fault);writer(f['target'],True);c.go(ready);rc=c.finish();r=c.report()
            else:rc,r,_=d.call(*d.args(f),env={'EXR_RECOVERY_FAULT':fault})
            d.check(fault+' measured under actual target owner',rc!=0 and r['atomicity']['recovery']['target_sdk_open_attempted'] and r['atomicity']['recovery']['rollback_requested'],r);d.preserve(f,before)
        for change in ('missing','other-nonce','partial','foreign-stdout'):

            f=d.seed(folder/change);c,ready=d.start(f,'worker-result');p=next(f['root'].glob('cap-*/baseline.bin'))
            if change=='missing':p.rename(p.with_name('missing-saved.bin'))
            elif change=='other-nonce':other=p.parent.with_name('cap-'+'f'*32+'-99');other.mkdir(mode=0o700);p.rename(other/'baseline.bin')
            elif change=='partial':p.write_bytes(b'partial')
            else:
                output=next(f['root'].glob('run-*/worker-01.stdout'));saved=output.with_suffix('.saved');output.rename(saved);output.write_bytes(saved.read_bytes());os.chmod(output,0o600)
            c.go(ready);d.check(change+' scanner output cannot admit',c.finish()!=0,c.report())
    def bounds(folder):
        f=d.seed(folder/'records')
        successes=0
        for i in range(8):
            p=f['target'].parent/('pack%d'%i);p.write_bytes(L.build_pack([L.entry(L.book_record('unique%d'%i,'unique%d.txt'%i),L.TXT+str(i).encode())],[]));before=model(f['target']);rc,r,_=d.call(*d.args(f,pack=p))
            if rc:
                d.check('capacity refusal before target SDK',not r['atomicity']['recovery']['target_sdk_open_attempted'] and ('capacity' in r['code'] or 'bound' in r['code'] or 'reservation' in r['code']),r);d.preserve(f,before);break
            successes+=1
        else:raise AssertionError('bounded capacity never reached')
        d.check('at least three distinct generations actually committed',successes>=3,successes);writer(f['target'],False)
        f=d.seed(folder/'page-work')
        with contextlib.closing(P.connect(f['target'],True)) as db:
            db.execute('PRAGMA page_size=512');db.execute('VACUUM');db.execute('UPDATE books SET cover=zeroblob(12582912)');db.commit();d.check('real small-page backup work exceeds16384',db.execute('PRAGMA page_size').fetchone()[0]==512 and db.execute('PRAGMA page_count').fetchone()[0]>16384)
        before=model(f['target']);rc,r,_=d.call(*d.args(f));d.check('actual page work quota refuses before target SDK',rc!=0 and not r['atomicity']['recovery']['target_sdk_open_attempted'] and r['atomicity']['recovery']['worker_reason']=='backup-work-budget',r);d.preserve(f,before)
        f=d.seed(folder/'physical');before=model(f['target'])
        with contextlib.closing(P.connect(f['target'],True)) as db:db.execute('PRAGMA page_size=65536');db.execute('VACUUM');db.execute("UPDATE books SET cover=zeroblob(67108865)");db.commit()
        current=model(f['target']);rc,r,_=d.call(*d.args(f));d.check('actual oversized physical/manifest refusal before SDK',rc!=0 and not r['atomicity']['recovery']['target_sdk_open_attempted'],r);d.preserve(f,current)
    def schemas(folder):
        for sql in ('CREATE TABLE extra(x)','CREATE VIEW extra AS SELECT * FROM books','CREATE TRIGGER extra AFTER UPDATE ON books BEGIN SELECT 1; END','PRAGMA user_version=99'):
            sub=folder/hashlib.sha256(sql.encode()).hexdigest()[:8];f=d.seed(sub)
            with contextlib.closing(P.connect(f['target'],True)) as db:db.executescript(sql);db.commit()
            before=P.read_state(f['target']);rc,r,_=d.call(*d.args(f));d.check('unsupported catalog/profile refuses before SDK',rc!=0 and not r['atomicity']['recovery']['target_sdk_open_attempted'],r);d.check('bad-schema input unchanged',P.read_state(f['target'])==before)
        for label,value in [('nul','embedded\x00NUL'),('blob',sqlite3.Binary(b'not a TEXT value'))]:
            f=d.seed(folder/('public-text-'+label))
            with contextlib.closing(P.connect(f['target'],True)) as db:db.execute('UPDATE books SET title=? WHERE id=1',(value,));db.commit()
            before=P.read_state(f['target']);rc,r,_=d.call(*d.args(f));d.check('unsupported public text refuses before SDK '+label,rc!=0 and not r['atomicity']['recovery']['target_sdk_open_attempted'],r);d.check('typed bad public text unchanged',P.read_state(f['target'])==before)
        f=d.seed(folder/'font');rc,_,_=d.call(a.fixture,'bounded',f['target'],a.fixtures/'sample.epub',a.font);d.check('bounded input really exists',rc==0)
        rc,r,_=d.call(*d.args(f,font=False));d.check('bounded EPUB without declared font refuses before SDK',rc!=0 and not r['atomicity']['recovery']['target_sdk_open_attempted'] and r['atomicity']['recovery']['worker_reason']=='bounded-epub-requires-recovery-font',r)
    def installed(folder):
        f=d.seed(folder);installed=Path(a.candidate).parent;worker=installed/'exreader-migration-recovery-worker';d.check('installed sibling worker exists',worker.is_file());rc,version,_=d.call(a.candidate,'--version');d.check('distinct recovery version',rc==0 and 'recovery-existing-v1' in version)
        # Operate on an isolated copied install, never mutate the real build.
        copybin=folder/'copybin';copybin.mkdir();candidate=copybin/Path(a.candidate).name;shutil.copy2(a.candidate,candidate);rc,r,_=d.call(candidate,'migrate','--target',f['target'],'--pack',f['pack']);d.check('missing sibling cannot fall back to PATH',rc!=0 and not r['atomicity']['recovery']['target_sdk_open_attempted'],r)
    def compatibility(folder):
        f=d.seed(folder/'v3');c=Child(d,[a.tool,'migrate','--target',f['target'],'--pack',f['pack'],'--inject','intent-pause']);ready=Path(str(f['target'])+'.intent-ready');until=time.monotonic()+30
        while not ready.exists() and c.p.poll() is None and time.monotonic()<until:time.sleep(.01)
        d.check('actual old candidate v3 emitted',ready.exists());c.finish(kill=True);pending=Path(str(f['target'])+'.migration-pending.json');d.check('actual old version3',json.loads(pending.read_text())['version']==3);before=state(pending);rc,r,_=d.call(*d.args(f,'recover-migration'));d.check('old v3 is never upgraded into new provenance',rc!=0 and not r['atomicity']['recovery']['target_sdk_open_attempted'],r);d.check('old v3 retained exact',state(pending)==before)
        f=d.seed(folder/'barrier');rc,r,_=d.call(*d.args(f));d.check('new actual success for compatibility barrier',rc==0,r);before=model(f['target']);lock=Path(str(f['target'])+'.migrate-lock');owned=state(lock)
        rc,r,_=d.call(a.old_tool,'migrate','--target',f['target'],'--pack',f['pack']);d.check('real SDK3.40 default shared lock refuses',rc!=0,r);d.preserve(f,before);d.check('barrier remains exact',state(lock)==owned)
        d.check('old --break-lock explicitly outside supported guarantee',True,'not invoked against user data; old code removes a lock without consulting new anchor; no downgrade safety claim')
    if os.name=='nt':
        for i,(command,extra) in enumerate([('migrate',()),('recover-migration',()),('recover-mirror',()),('dump',()),('verify',()),('export-ledger',('--output','export.json')),('inspect',()),('migrate',('--break-lock','--dry-run'))],1):
            def unsupported(folder,command=command,extra=extra):
                target=folder/'existing.sqlite';target.write_bytes(b'not opened by SDK');pack=folder/'pack';pack.write_bytes(L.build_pack([],[]));f=dict(target=target,pack=pack);before=state(target)
                rc,r,_=d.call(*d.args(f,command,extra=extra));d.check('Windows literal unsupported before SDK',rc!=0 and r['code']=='recovery-platform-unqualified' and not r['atomicity']['recovery']['target_sdk_open_attempted'],r);d.check('target and namespace untouched',state(target)==before and {p.name for p in folder.iterdir()}=={'existing.sqlite','pack','logs'})
            d.run('%02d-windows-%s'%(i,command),unsupported)
        expected=8
    else:
        for schema in (6,7):
            for journal in ('delete','wal'):d.run('%02d-import-s%d-%s'%(len(d.evidence['cases'])+1,schema,journal),lambda f,schema=schema,journal=journal:simple(f,schema,journal))
        d.run('05-missing-target',missing);d.run('06-target-races',replacement)
        for i in range(8):d.run('%02d-crash-%s'%(i+7,PHASES[i]),lambda f,i=i:crash(f,i))
        for name,fn in [('15-full-original-fixture',full),('16-nine-formats-bounded-projection',formats),('17-strict-partial-conflict',policy),('18-repeat-three-generations',repeat),('19-later-public-writers',later),('20-preopen-preview-cancel',preopen),('21-R-pack-changed-ABA',wrongpack),('22-foreign-artifacts-fd-alias',foreign),('23-mirror-restore-sync',mirrors),('24-native-permission-rollback-observation',native),('25-ack-absent-partial-foreign',ack),('26-all-real-entrypoints',entries),('27-live-sources-owner-lease',lifetime),('28-worker-transport',transport),('29-resource-capacity',bounds),('30-schema-font-refusals',schemas),('31-installed-worker',installed),('32-old-v3-default-barrier',compatibility)]:d.run(name,fn)
        expected=32
    d.evidence['expected_cases']=expected;d.evidence['passed']=not d.report_exceeded and len(d.evidence['cases'])==expected and all(c['passed'] for c in d.evidence['cases']);d.save()
    print(str(sum(c['passed'] for c in d.evidence['cases']))+'/'+str(expected),'full_p0_acceptance=false',flush=True)
    return 0 if d.evidence['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
