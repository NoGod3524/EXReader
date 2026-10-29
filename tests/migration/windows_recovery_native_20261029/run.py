#!/usr/bin/env python3
"""Actions-only Windows adapter qualification. No product enablement."""
import argparse, contextlib, ctypes, hashlib, importlib.util, json, os, re
import shutil, sqlite3, subprocess, sys, time, traceback, stat
from pathlib import Path
from ctypes import wintypes as W
if os.environ.get('GITHUB_ACTIONS') != 'true' or os.name != 'nt':
    raise SystemExit('Native Windows Actions only; no local execution.')
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('frozen_preflight',HERE.parent/'recovery_preflight_20261029/run.py')
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)
K=ctypes.WinDLL('kernel32',use_last_error=True)
SIZE=ctypes.c_size_t;ULONG_PTR=SIZE;LPVOID=ctypes.c_void_p
class SI(ctypes.Structure):
    _fields_=[('cb',W.DWORD),('lpReserved',W.LPWSTR),('lpDesktop',W.LPWSTR),('lpTitle',W.LPWSTR),('dwX',W.DWORD),('dwY',W.DWORD),('dwXSize',W.DWORD),('dwYSize',W.DWORD),('dwXCountChars',W.DWORD),('dwYCountChars',W.DWORD),('dwFillAttribute',W.DWORD),('dwFlags',W.DWORD),('wShowWindow',W.WORD),('cbReserved2',W.WORD),('lpReserved2',LPVOID),('hStdInput',W.HANDLE),('hStdOutput',W.HANDLE),('hStdError',W.HANDLE)]
class SIX(ctypes.Structure):_fields_=[('s',SI),('attrs',LPVOID)]
class PI(ctypes.Structure):_fields_=[('process',W.HANDLE),('thread',W.HANDLE),('pid',W.DWORD),('tid',W.DWORD)]
class LIMITS(ctypes.Structure):
    _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),('flags',W.DWORD),('min_ws',SIZE),('max_ws',SIZE),('active',W.DWORD),('affinity',ULONG_PTR),('priority',W.DWORD),('scheduling',W.DWORD)]
class IO(ctypes.Structure):_fields_=[(x,ctypes.c_ulonglong) for x in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
class EXT(ctypes.Structure):_fields_=[('basic',LIMITS),('io',IO),('process_mem',SIZE),('job_mem',SIZE),('peak_process',SIZE),('peak_job',SIZE)]
class ACCOUNT(ctypes.Structure):_fields_=[('a',ctypes.c_longlong),('b',ctypes.c_longlong),('c',ctypes.c_longlong),('d',ctypes.c_longlong),('faults',W.DWORD),('total',W.DWORD),('active',W.DWORD),('terminated',W.DWORD)]
def api(name,restype,args):
    f=getattr(K,name);f.restype=restype;f.argtypes=args;return f
create=api('CreateProcessW',W.BOOL,[W.LPCWSTR,W.LPWSTR,LPVOID,LPVOID,W.BOOL,W.DWORD,LPVOID,W.LPCWSTR,ctypes.POINTER(SIX),ctypes.POINTER(PI)])
newjob=api('CreateJobObjectW',W.HANDLE,[LPVOID,W.LPCWSTR]);setjob=api('SetInformationJobObject',W.BOOL,[W.HANDLE,ctypes.c_int,LPVOID,W.DWORD]);assign=api('AssignProcessToJobObject',W.BOOL,[W.HANDLE,W.HANDLE]);injob=api('IsProcessInJob',W.BOOL,[W.HANDLE,W.HANDLE,ctypes.POINTER(W.BOOL)])
wait=api('WaitForSingleObject',W.DWORD,[W.HANDLE,W.DWORD]);close=api('CloseHandle',W.BOOL,[W.HANDLE]);exitcode=api('GetExitCodeProcess',W.BOOL,[W.HANDLE,ctypes.POINTER(W.DWORD)]);kill=api('TerminateProcess',W.BOOL,[W.HANDLE,W.UINT]);killjob=api('TerminateJobObject',W.BOOL,[W.HANDLE,W.UINT]);queryjob=api('QueryInformationJobObject',W.BOOL,[W.HANDLE,ctypes.c_int,LPVOID,W.DWORD,LPVOID]);resume=api('ResumeThread',W.DWORD,[W.HANDLE]);setinherit=api('SetHandleInformation',W.BOOL,[W.HANDLE,W.DWORD,W.DWORD])
attrs_init=api('InitializeProcThreadAttributeList',W.BOOL,[LPVOID,W.DWORD,W.DWORD,ctypes.POINTER(SIZE)]);attrs_set=api('UpdateProcThreadAttribute',W.BOOL,[LPVOID,W.DWORD,SIZE,LPVOID,SIZE,LPVOID,LPVOID]);attrs_delete=api('DeleteProcThreadAttributeList',None,[LPVOID])
openfile=api('CreateFileW',W.HANDLE,[W.LPCWSTR,W.DWORD,W.DWORD,LPVOID,W.DWORD,W.DWORD,W.HANDLE]);move=api('MoveFileExW',W.BOOL,[W.LPCWSTR,W.LPCWSTR,W.DWORD]);getattrs=api('GetFileAttributesW',W.DWORD,[W.LPCWSTR]);hardlink=api('CreateHardLinkW',W.BOOL,[W.LPCWSTR,W.LPCWSTR,LPVOID]);symlink=api('CreateSymbolicLinkW',W.BOOLEAN,[W.LPCWSTR,W.LPCWSTR,W.DWORD]);flush=api('FlushFileBuffers',W.BOOL,[W.HANDLE])
BAD=ctypes.c_void_p(-1).value
FATAL=False
UNCONFIRMED=[]

def check(v,label):
    if not v:raise AssertionError((label,ctypes.get_last_error()))
def bounded_read(path,maximum,after_open=None):
    import msvcrt
    class TAG(ctypes.Structure):_fields_=[('attributes',W.DWORD),('tag',W.DWORD)]
    getinfo=api('GetFileInformationByHandleEx',W.BOOL,[W.HANDLE,ctypes.c_int,LPVOID,W.DWORD])
    handle=openfile(str(path),0x80000000,1|2|4,None,3,0x00200000,None);check(handle!=BAD,'bounded protocol open');transferred=False
    try:
        tag=TAG();check(getinfo(handle,9,ctypes.byref(tag),ctypes.sizeof(tag)),'bounded protocol attributes');assert not tag.attributes&(0x400|0x10)
        fd=msvcrt.open_osfhandle(int(handle),os.O_RDONLY|os.O_BINARY);transferred=True
        with os.fdopen(fd,'rb') as source:
            before=os.fstat(source.fileno());assert 0<=before.st_size<=maximum
            if after_open:after_open()
            raw=source.read(maximum+1);after=os.fstat(source.fileno());assert len(raw)<=maximum and after.st_size<=maximum
            assert (before.st_dev,before.st_ino)==(after.st_dev,after.st_ino)
        return raw
    finally:
        if not transferred:close(handle)
def bounded_json(value,maximum):
    chunks=[];size=0
    for part in json.JSONEncoder(indent=2).iterencode(value):
        raw=part.encode('utf-8');size+=len(raw);assert size+1<=maximum;chunks.append(raw)
    return b''.join(chunks)+b'\n'
def projection_equal(observed,expected):
    assert observed==expected,'ordered original public projection mismatch'
def statfile(path):return P.identity(path),hashlib.sha256(bounded_read(path,64*1024**2)).hexdigest(),path.stat().st_size


def model(path):
    with contextlib.closing(P.connect(path)) as db:
        db.execute('BEGIN');assert db.execute('PRAGMA integrity_check').fetchall()==[('ok',)];assert not db.execute('PRAGMA foreign_key_check').fetchall()
        return dict(version=db.execute('PRAGMA user_version').fetchone()[0],catalog=set(db.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema')),rows={n:db.execute('SELECT _rowid_,* FROM '+P.quote(n)+' ORDER BY _rowid_').fetchall() for n, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")},canonical=P.canonical(db),public=P.public_projection(db))
UPGRADE={('table','epub_bounded_books','epub_bounded_books','CREATE TABLE epub_bounded_books(book_id INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE)'),('table','epub_progress','epub_progress','CREATE TABLE epub_progress(book_id INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,part INTEGER NOT NULL CHECK(part>=0 AND part<10000),path TEXT NOT NULL,position INTEGER NOT NULL CHECK(position>=0),prefix TEXT,suffix TEXT,chapter TEXT)')}
# Exact schema6 upgrade DDL, independently specified as in the frozen oracle.
UPGRADE.add(('table','epub_notes','epub_notes','CREATE TABLE epub_notes(id INTEGER PRIMARY KEY,book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,part INTEGER NOT NULL CHECK(part>=0 AND part<10000),path TEXT NOT NULL,start INTEGER NOT NULL CHECK(start>=0),end INTEGER NOT NULL CHECK(end>start),exact TEXT NOT NULL,prefix TEXT,suffix TEXT,chapter TEXT,text TEXT NOT NULL)'))
UPGRADE.add(('index','epub_notes_book','epub_notes','CREATE INDEX epub_notes_book ON epub_notes(book_id,part,start,id)'))

def parity(before,after,title=None):
    assert after['version']==(7 if title is not None else before['version'])
    assert after['catalog']==before['catalog']|(UPGRADE if before['version']==6 and title is not None else set())
    assert set(after['rows'])==set(before['rows'])|({'epub_bounded_books','epub_progress','epub_notes'} if before['version']==6 and title is not None else set())
    for table,rows in before['rows'].items():
        expected=rows
        if title is not None and table=='books':
            expected=[]
            # rowid,id,format,title,... are frozen schema order, asserted below.
            for row in rows:
                row=list(row)
                if row[1]==1:row[3]=title
                expected.append(tuple(row))
        assert after['rows'][table]==expected,table
    for table in set(after['rows'])-set(before['rows']):assert after['rows'][table]==[]

class Job:
    def __init__(self):
        self.h=newjob(None,None);check(self.h,'job');x=EXT();x.basic.flags=0x2000|0x100|0x200|0x2;x.basic.process_time=60*10_000_000;x.process_mem=512*1024**2;x.job_mem=1024**3;check(setjob(self.h,9,ctypes.byref(x),ctypes.sizeof(x)),'job limits');self.closed=False
    def active(self):
        x=ACCOUNT();check(queryjob(self.h,1,ctypes.byref(x),ctypes.sizeof(x),None),'job query');return x.active
    def finish(self):
        global FATAL
        if self.closed:return
        if self.active():check(killjob(self.h,125),'owned job terminate')
        end=time.monotonic()+10
        while self.active() and time.monotonic()<end:time.sleep(.02)
        if self.active():FATAL=True;raise AssertionError('job cleanup unconfirmed; no further launches')
        for process in list(UNCONFIRMED):
            if wait(process.process,0)==0:
                close(process.thread);close(process.process);UNCONFIRMED.remove(process)
        check(close(self.h),'job close');self.closed=True

class Child:
    def __init__(self,command,folder,job):
        global FATAL
        assert not FATAL
        self.deadline=time.monotonic()+120;self.pi=PI();self.job=job;self.log=folder;self.closed=False
        self.out=openfile(str(folder),0x40000000,1|2,None,1,0x80000000,None);check(self.out!=BAD,'log exclusive')
        self.input=openfile('NUL',0x80000000,1|2,None,3,0,None);check(self.input!=BAD,'stdin NUL')
        handles=(W.HANDLE*3)(self.input,self.out,job.h)
        size=SIZE();attrs_init(None,1,0,ctypes.byref(size));buffer=ctypes.create_string_buffer(size.value);si=SIX();si.s.cb=ctypes.sizeof(si);si.s.dwFlags=0x100;si.s.hStdInput=self.input;si.s.hStdOutput=si.s.hStdError=self.out;si.attrs=ctypes.cast(buffer,LPVOID)
        created=False;initialized=False
        try:
            check(attrs_init(si.attrs,1,0,ctypes.byref(size)),'attributes init');initialized=True
            for h in handles:check(setinherit(h,1,1),'inherit allowlist')
            check(attrs_set(si.attrs,0,0x20002,ctypes.cast(handles,LPVOID),ctypes.sizeof(handles),None,None),'exact handle list')
            cmd=ctypes.create_unicode_buffer(subprocess.list2cmdline([str(x) for x in command]))
            check(create(str(command[0]),cmd,None,None,True,0x4|0x80000|0x08000000,None,None,ctypes.byref(si),ctypes.byref(self.pi)),'create suspended');created=True
            member=W.BOOL();check(injob(self.pi.process,job.h,ctypes.byref(member)),'membership before');
            if not member.value:check(assign(job.h,self.pi.process),'assign before resume')
            check(injob(self.pi.process,job.h,ctypes.byref(member)) and member.value,'membership verified')
            check(resume(self.pi.thread)!=0xffffffff,'resume contained')
        except BaseException:
            if created:
                kill(self.pi.process,125)
                if wait(self.pi.process,10000)!=0:
                    FATAL=True;UNCONFIRMED.append(self.pi)
            if not FATAL:
                if self.pi.thread:close(self.pi.thread)
                if self.pi.process:close(self.pi.process)
            raise
        finally:
            if initialized:attrs_delete(si.attrs)
            for h in handles:setinherit(h,1,0)
            close(self.input);close(self.out)
    def alive(self):return wait(self.pi.process,0)==258
    def phase(self,root,name):
        marker=root/(name+'.ready');value=None
        while self.alive() and time.monotonic()<self.deadline:
            if self.log.exists():assert self.log.stat().st_size<=2*1024**2
            if marker.exists():
                raw=bounded_read(marker,4096)
                try:value=json.loads(raw)
                except json.JSONDecodeError:pass
                else:
                    assert value['phase']==name and value['nonce']==root.parent.name
                    return value
            time.sleep(.02)
        raise AssertionError((name,'missing complete marker',self.read()))
    def finish(self,terminate=False):
        global FATAL
        if terminate and self.alive():check(kill(self.pi.process,125),'terminate exact process')
        while self.alive() and time.monotonic()<self.deadline:
            assert self.log.stat().st_size<=2*1024**2
            time.sleep(.02)
        if self.alive():kill(self.pi.process,125)
        result=wait(self.pi.process,10000 if self.alive() else 0)
        if result!=0:FATAL=True;raise AssertionError(('process cleanup unconfirmed',result,ctypes.get_last_error()))
        code=W.DWORD();check(exitcode(self.pi.process,ctypes.byref(code)),'exitcode')
        close(self.pi.thread);close(self.pi.process);self.closed=True
        assert self.log.stat().st_size<=2*1024**2
        return code.value
    def read(self):
        if not self.log.exists():return ''
        assert self.log.stat().st_size<=2*1024**2
        with self.log.open('rb') as source:raw=source.read(2*1024**2+1)
        assert len(raw)<=2*1024**2
        return raw.decode('utf-8','strict')
    def report(self):return json.loads(self.read().splitlines()[-1])

def workspace_bytes(root):
    pending=[root];total=0;count=0
    while pending:
        parent=pending.pop()
        with os.scandir(parent) as listing:
            for entry in listing:
                count+=1;assert count<=30000
                st=entry.stat(follow_symlinks=False)
                if getattr(st,'st_file_attributes',0)&0x400:continue
                if stat.S_ISDIR(st.st_mode):pending.append(Path(entry.path))
                elif stat.S_ISREG(st.st_mode):total+=st.st_size;assert total<=4*1024**3
                else:raise AssertionError('unexpected workspace node')
    return total

class Driver:
    def __init__(self,a):
        self.a=a;self.work=a.work.resolve();self.work.mkdir(exist_ok=False);self.logs=self.work/'logs';self.logs.mkdir();self.cases=[];self.serial=0;self.job=None
    def child(self,command):
        self.serial+=1;return Child(command,self.logs/('%05d.txt'%self.serial),self.job)
    def native(self,op,root,arg='none',extra=()):return self.child([self.a.probe,op,str(root),root.parent.name,arg,str(self.job.h),*extra])
    def call(self,op,root,arg='none',extra=(),success=True,reason=None):
        child=self.native(op,root,arg,extra);rc=child.finish();r=child.report();assert r['full_p0_acceptance'] is False and r['product_admission'] is False
        assert not r['cleanup_unconfirmed'],r
        assert (rc==0 and r['passed']) if success else (rc!=0 and not r['passed']),r
        if reason:assert r['reason']==reason,r
        return r
    def go(self,root,name):return self.call('token',root,name+'.go')
    def put(self,root,name,data):
        source=root.parent/('input-%05d'%self.serial);source.write_bytes(data);return self.call('copy',root,name,(str(source),))
    def fresh(self,label):
        assert workspace_bytes(self.work)+1024**3+64*1024**2<=4*1024**3
        folder=self.work/hashlib.sha256(label.encode()).hexdigest()[:32];folder.mkdir(exist_ok=False);root=folder/'私有-library';self.call('init',root);return root
    def seed(self,root,schema=7,journal='delete'):
        entries,notes=P.L.dataset();pack=root.parent/'seed.exrpack';pack.write_bytes(P.L.build_pack(entries,notes))
        c=self.child([self.a.old_tool if schema==6 else self.a.tool,'migrate','--target',str(root/'library.sqlite'),'--pack',str(pack),'--allow-partial']);assert c.finish()==0,c.read();r=c.report()
        assert (r['result'], r['code']) == ('success', 'ok'), r
        assert r['pack']['sha256'] == hashlib.sha256(pack.read_bytes()).hexdigest()
        expected_counts = {
            'books_expected': 5, 'books_created': 4, 'books_existing': 0,
            'books_merged': 0, 'books_skipped': 0,
            'books_audio_positions_only': 1, 'books_accounted': 5,
            'notes_expected': 16, 'notes_created': 10, 'notes_existing': 0,
            'notes_unlocated': 6, 'notes_skipped': 0, 'notes_accounted': 16,
        }
        assert {k: r['counts'][k] for k in expected_counts} == expected_counts, r
        assert r['counts']['entries'] == {
            'info': 4, 'warning': 1, 'approximate': 2, 'unlocated': 6,
            'dropped': 1, 'unsupported': 1, 'conflict': 0,
        }, r
        unsupported = [(e['code'], e['scope'], e['legacy_id']) for e in r['entries'] if e['severity'] == 'unsupported']
        assert unsupported == [('audio-original-not-storable', 'book', 'b-audio')], r
        assert not [e for e in r['entries'] if e['severity'] == 'conflict'], r
        expected_unlocated = {
            'n-txt-ambiguous': 'quote-ambiguous',
            'n-txt-missing': 'quote-not-found',
            'n-txt-bookmark': 'bookmark-without-cfi',
            'n-epub-ambiguous': 'quote-ambiguous',
            'n-pdf-missing': 'quote-not-found', 'n-orphan': 'orphan-note',
        }
        assert {n['legacy_id']: n['reason'] for n in r['notes'] if n['status'] == 'unlocated'} == expected_unlocated, r
        assert {b['legacy_id']: b['status'] for b in r['items']} == {
            'b-txt': 'created', 'b-epub': 'created', 'b-pdf': 'created',
            'b-cbz': 'created', 'b-audio': 'audio-positions-only',
        }, r
        ledger = json.loads(Path(str(root/'library.sqlite') + '.legacy-map.json').read_text(encoding='utf-8'))
        assert ledger['format'] == 'exreader-legacy-map' and ledger['version'] == 1
        assert ledger['packs'] == [r['pack']['sha256']]
        assert len(ledger['books']) == 5 and len(ledger['notes']) == 16
        # Frozen producer deliberately stores the cover separately, not in raw
        # book JSON. Its public cover bytes remain covered by clone projection.
        assert {b['legacy_id']: b['retained'] for b in ledger['books']} == {
            b['legacy_id']: {k: v for k, v in b['record'].items() if k != 'cover'} for b in entries
        }
        assert {n['legacy_id']: n['retained'] for n in ledger['notes']} == {n['id']: n for n in notes}
        assert {n['legacy_id']: n['reason'] for n in ledger['notes'] if not n['located']} == expected_unlocated
        with contextlib.closing(P.connect(root/'library.sqlite',True)) as db:
            assert db.execute('PRAGMA user_version').fetchone()[0]==schema;assert db.execute('PRAGMA journal_mode='+journal).fetchone()[0]==journal;db.commit()
        return model(root/'library.sqlite')
    def writer(self,root,busy,change=None):
        with contextlib.closing(P.connect(root/'library.sqlite',True)) as db:
            try:db.execute('BEGIN IMMEDIATE')
            except sqlite3.OperationalError as error:
                assert busy and error.sqlite_errorcode&255==sqlite3.SQLITE_BUSY,(busy,error.sqlite_errorcode);return error.sqlite_errorcode
            assert not busy,'writer unexpectedly acquired'
            if change:db.execute('UPDATE books SET title=? WHERE id=1',(change,));db.commit()
            else:db.rollback()
        return 0
    def owner(self,root,mode='rollback',scan=False,before_finish=None,expected=None):
        c=self.native('owner',root,mode);c.phase(root,'before-sdk');self.go(root,'before-sdk');c.phase(root,'owner-held');self.writer(root,True);self.go(root,'owner-held')
        if scan or mode=='handoff':
            c.phase(root,'child-spawned');self.go(root,'child-spawned');c.phase(root,'child-live');self.writer(root,True);self.go(root,'child-live');c.phase(root,'child-waited');self.writer(root,True);self.projection(root,expected);self.go(root,'child-waited')
        if mode=='handoff':c.phase(root,'compared');self.writer(root,True);self.go(root,'compared')
        c.phase(root,'mutation-held');self.writer(root,True)
        context=before_finish(root) if before_finish else contextlib.nullcontext()
        with context as calibration:
            self.go(root,'mutation-held');c.phase(root,'owner-finished')
            if before_finish:
                assert (root/'library.sqlite-journal').exists()
                self.cases[-1]['fault_at_finish']=dict(calibration=calibration,journal_present=True,journal_size=(root/'library.sqlite-journal').stat().st_size)
            self.go(root,'owner-finished')
        c.phase(root,'owner-closed');self.writer(root,False);self.go(root,'owner-closed');assert c.finish()==0,c.read();return c.report()
    def projection(self,root,expected):
        assert expected is not None,'independent pre-owner expectation required'
        out=root/'worker-output';raw=bounded_read(out/'public-projection.jsonl',64*1024**2)
        projection_equal([json.loads(line) for line in raw.splitlines()],expected['public'])
        assert bounded_read(out/'baseline.bin',64*1024**2)==expected['canonical']
        # The SDK clone may add exactly schema6's documented empty schema7 tables.
        clone=model(out/'clone.sqlite')
        if expected['version']==6:
            assert clone['version']==7 and clone['catalog']==expected['catalog']|UPGRADE
            for name,rows in expected['rows'].items():assert clone['rows'][name]==rows,name
            for name in set(clone['rows'])-set(expected['rows']):assert clone['rows'][name]==[]
        else:parity(expected,clone)
    def launch(self,root,variant='normal',success=True,result_edit=None):
        c=self.native('launch',root,variant)
        if variant=='assign-fail':
            assert c.finish()!=0;cdata=c.report();assert cdata['reason']=='spawn-contained-before-resume' and not cdata['target_sdk_open_attempted'] and not cdata['cleanup_unconfirmed'];return cdata
        c.phase(root,'child-spawned');self.go(root,'child-spawned')
        if variant not in ('spawn-gap','wrong-kind','wrong-nonce','wrong-producer','wrong-output'):
            c.phase(root,'child-live');self.go(root,'child-live');c.phase(root,'child-waited')
            if result_edit:result_edit(root)
            self.go(root,'child-waited')
        rc=c.finish();result=c.report();assert (rc==0 and result['passed']) if success else (rc!=0 and not result['passed']),result
        return result
    def execute(self,name,fn):
        global FATAL
        row=dict(name=name,passed=False);self.cases.append(row);self.job=Job()
        try:
            assert not FATAL,'prior cleanup unconfirmed';fn();row['passed']=True
        except BaseException as error:row['error']=repr(error);row['traceback']=traceback.format_exc()
        finally:
            try:self.job.finish()
            except BaseException as error:FATAL=True;row['passed']=False;row['cleanup_error']=repr(error)
            self.save();print(name,'PASS' if row['passed'] else 'FAIL '+row.get('error',''),flush=True)
    def save(self):
        data=dict(source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],cases=self.cases,passed=len(self.cases)==24 and all(x['passed'] for x in self.cases),product_admission=False,full_p0_acceptance=False,directory_fsync_equivalent=False,physical_power_loss_qualified=False,cleanup_unconfirmed=FATAL)
        raw=bounded_json(data,64*1024**2)
        (self.work/'evidence.json').write_bytes(raw)

def read_child_report(root):
    raw=bounded_read(root/'worker-log.txt',2*1024**2).decode('utf-8','strict')
    return json.loads(raw.splitlines()[-1])

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--probe',type=Path,required=True);parser.add_argument('--tool',type=Path,required=True);parser.add_argument('--old-tool',type=Path,required=True);parser.add_argument('--work',type=Path,required=True);a=parser.parse_args()
    for key in ('probe','tool','old_tool'):setattr(a,key,getattr(a,key).resolve())
    assert sys.version_info[:2]==(3,12)
    d=Driver(a)
    def fixture(label,schema=7,journal='delete'):
        root=d.fresh(label);return root,d.seed(root,schema,journal)
    def stable(before,root):parity(before,model(root/'library.sqlite'))
    def finish_owner(c,root):
        c.phase(root,'mutation-held');d.writer(root,True);d.go(root,'mutation-held');c.phase(root,'owner-finished');d.go(root,'owner-finished');c.phase(root,'owner-closed');d.writer(root,False);d.go(root,'owner-closed');assert c.finish()==0,c.read();return c.report()
    def scan_gate(root,expected):
        c=d.native('owner',root,'handoff');c.phase(root,'before-sdk');d.go(root,'before-sdk');c.phase(root,'owner-held');d.writer(root,True);d.go(root,'owner-held');c.phase(root,'child-spawned');d.go(root,'child-spawned');c.phase(root,'child-live');d.writer(root,True);d.go(root,'child-live');c.phase(root,'child-waited');d.projection(root,expected);d.writer(root,True);d.go(root,'child-waited');return c
    def replace_file(root,name):
        old=root/name;data=old.read_bytes();before=P.identity(old);old.rename(root/(name+'.original'));d.put(root,name,data);assert P.identity(old)!=before and old.read_bytes()==data;return before,data
    def native_share(path,access,share):
        h=openfile(str(path),access,share,None,3,0x00200000,None);check(h!=BAD,'native calibrated handle');return h
    def g01():
        with contextlib.closing(sqlite3.connect(':memory:')) as db:
            try:db.execute('NOT SQL')
            except sqlite3.OperationalError as e:assert e.sqlite_errorcode==sqlite3.SQLITE_ERROR
            else:raise AssertionError('syntax calibration unexpectedly succeeded')
        root=d.fresh('01-native-Unicode');r=d.call('identity',root);assert len(r['root_id'])==48 and re.fullmatch('[0-9a-f]{48}',r['root_id']);assert len(r['source_producer'])==64 and 'D:P' in r['actual_root_sddl'];assert r['outside_ancestors']
        for ancestor in r['outside_ancestors']:assert ancestor['classification']=='outside-pinned-not-private' and ancestor['requested_access']==0x200a0 and ancestor['requested_share']==1 and len(ancestor['identity'])==48 and ancestor['observed_sddl']
        measurement=d.call('directory-flush',root);assert type(measurement['directory_flush_result']) is bool and not measurement['directory_fsync_equivalent']
    def g02():
        root=d.fresh('02-acl');d.call('write',root,'private.txt');before=statfile(root/'private.txt')
        tool=Path(shutil.which('icacls.exe'));c=d.child([tool,str(root/'private.txt'),'/grant','*S-1-1-0:R']);assert c.finish()==0,c.read()
        r=d.call('read',root,'private.txt',success=False,reason='private-acl-shape');assert statfile(root/'private.txt')==before and not r['target_sdk_open_attempted']
        root,before=fixture('02-private-root-acl');root_id=P.identity(root);files={x.name:statfile(x) for x in root.iterdir() if x.is_file()}
        c=d.child([tool,str(root),'/grant','*S-1-1-0:R']);assert c.finish()==0,c.read()
        for op,arg in (('identity','none'),('owner','rollback')):
            r=d.call(op,root,arg,success=False,reason='private-acl-shape');assert not r['target_sdk_open_attempted']
        assert P.identity(root)==root_id and {x.name:statfile(x) for x in root.iterdir() if x.is_file()}==files;stable(before,root)
    def g03():
        root=d.fresh('03-collision');d.call('write',root,'same.bin');old=statfile(root/'same.bin');r=d.call('write',root,'same.bin',success=False,reason='regular-open');assert r['native_error'] in (80,183) and statfile(root/'same.bin')==old
    def g04():
        root=d.fresh('04-write');control=root.parent/'bounded-read-control';control.write_bytes(b'x'*64);assert bounded_read(control,64)==b'x'*64
        control.write_bytes(b'x'*65)
        try:bounded_read(control,64)
        except AssertionError:pass
        else:raise AssertionError('one-over protocol read admitted')
        control.write_bytes(b'x'*64)
        def grow():
            with control.open('ab') as f:f.write(b'x');f.flush();os.fsync(f.fileno())
        try:bounded_read(control,64,grow)
        except AssertionError:pass
        else:raise AssertionError('growing protocol read admitted')
        d.cases[-1]['bounded_reader_controls']=3
        d.call('write-read',root);assert (root/'source.bin').read_bytes()==b'canonical-native-record\n';assert P.identity(root/'source.bin')
    def g05():
        root=d.fresh('05-partial');c=d.native('partial',root);c.phase(root,'partial-written');assert c.finish(terminate=True)==125;old=statfile(root/'partial.json');d.call('partial-check',root,success=False,reason='partial-record-refused');assert statfile(root/'partial.json')==old
    def g06():
        for mode in ('write-denied','flush-denied'):
            root=d.fresh('06-'+mode);old=statfile(root/'anchor.json');r=d.call(mode,root);assert r['native_refusal']==5 and statfile(root/'anchor.json')==old and not (root/'ack.json').exists()
    def g07():
        root=d.fresh('07-flush-before-ack');c=d.native('postflush',root);c.phase(root,'file-flushed');assert c.finish(terminate=True)==125;before=statfile(root/'source.bin');d.call('completion',root,success=False,reason='restart-has-no-actual-wait-proof');assert statfile(root/'source.bin')==before and not (root/'ack.json').exists()
    def g08():
        root=d.fresh('08-complete-not-durable');r=d.call('complete-failed',root,success=False,reason='complete-record-flush-unverified');assert r['native_refusal']==5;assert json.loads((root/'complete.json').read_bytes())=={'looks_complete':True};old=statfile(root/'complete.json');d.call('completion',root,success=False,reason='restart-has-no-actual-wait-proof');assert statfile(root/'complete.json')==old
    def g09():
        root=d.fresh('09-namespace');d.call('write',root,'original.bin');original=(root/'original.bin').read_bytes();outside=root.parent/'outside';outside.mkdir();(outside/'canary').write_bytes(b'outside-unchanged')
        check(hardlink(str(root/'hard.bin'),str(root/'original.bin'),None),'hardlink capability');r=d.call('read',root,'hard.bin',success=False,reason='file-kind-or-alias');assert not r['target_sdk_open_attempted'];(root/'hard.bin').unlink();assert (root/'original.bin').read_bytes()==original
        check(symlink(str(root/'link.bin'),str(root/'original.bin'),2),'symlink capability');d.call('read',root,'link.bin',success=False,reason='file-kind-or-alias');(root/'link.bin').unlink()
        junction=root/'junction';c=d.child([Path(os.environ['COMSPEC']),'/d','/c','mklink','/J',str(junction),str(outside)]);assert c.finish()==0,c.read()
        raw=d.child([a.probe,'identity',str(junction),root.parent.name,'none',str(d.job.h)]);assert raw.finish()!=0;assert raw.report()['reason']=='file-kind-or-alias';junction.rmdir()
        d.call('write',root,'original.bin:stream',success=False,reason='leaf-path')
        c=d.native('parent-pin',root);c.phase(root,'parent-pinned');assert not move(str(root),str(root.parent/'moved-private'),0);error=ctypes.get_last_error();assert error in (5,32),error
        # A pinned parent cannot be replaced with a junction after the check.
        assert not symlink(str(root),str(outside),1|2);assert ctypes.get_last_error() in (5,32,183),ctypes.get_last_error();d.go(root,'parent-pinned');assert c.finish()==0,c.read();assert (root/'confined.bin').read_bytes()==b'canonical-native-record\n' and list(outside.iterdir())==[outside/'canary'] and (outside/'canary').read_bytes()==b'outside-unchanged'
    def g10():
        root,before=fixture('10-baseline');d.put(root,'baseline.bin',before['canonical']);c=scan_gate(root,before);c.phase(root,'compared');replace_file(root,'baseline.bin');d.go(root,'compared');assert c.finish()!=0;cdata=c.report();assert cdata['reason']=='bound-evidence-changed' and not cdata['commit_requested'];stable(before,root)
        for which in ('request','output'):
            root,before=fixture('10-'+which);c=d.native('launch',root,'normal');c.phase(root,'child-spawned')
            if which=='request':replace_file(root,'use-0.json')
            else:
                (root/'worker-output').rename(root/'original-output');d.call('mkdir',root,'worker-output')
            d.go(root,'child-spawned');assert c.finish()!=0 and c.report()['reason']=='child-nonzero';child=read_child_report(root);assert not child['target_sdk_open_attempted'] and child['reason'] in ('anchored-use-replaced','child-output-replaced');stable(before,root)
        root,before=fixture('10-target-request');c=d.native('launch',root,'request-pause');c.phase(root,'request-published');replace_file(root,'library.sqlite');foreign=statfile(root/'library.sqlite');d.go(root,'request-published');c.phase(root,'child-spawned');d.go(root,'child-spawned');assert c.finish()!=0;child=read_child_report(root);assert child['reason']=='child-target-request' and not child['target_sdk_open_attempted'];assert statfile(root/'library.sqlite')==foreign;stable(before,root)
    def g11():
        root=d.fresh('11-rename');c=d.native('rename',root);c.phase(root,'renamed');assert not (root/'source.bin').exists();old=statfile(root/'published.bin');d.go(root,'renamed');assert c.finish()==0;r=c.report();assert r['rename_attempted'] and r['rename_ntstatus']==0 and r['rename_io_status']==0
        r=d.call('rename',root,success=False,reason='rename-no-replace');assert r['native_error'] in (80,183,5) and r['rename_attempted'] and r['rename_ntstatus']<0 and statfile(root/'published.bin')==old and (root/'source.bin').read_bytes()==b'canonical-native-record\n'
        root=d.fresh('11-cwd');outside=root.parent/'different-cwd';outside.mkdir();canary=outside/'published.bin';canary.write_bytes(b'outside-cwd-canary');original=statfile(canary)
        c=d.native('rename-cwd',root,str(outside));c.phase(root,'renamed');assert not (root/'source.bin').exists();published=statfile(root/'published.bin');d.go(root,'renamed');assert c.finish()==0,c.read();r=c.report()
        assert r['different_cwd_observed'] and r['rename_attempted'] and r['rename_ntstatus']==0 and r['rename_io_status']==0 and r['rename_source_id']==r['rename_destination_id'] and len(r['root_id'])==48
        assert statfile(root/'published.bin')==published and statfile(canary)==original and list(outside.iterdir())==[canary]
        for style in ('foreign','sibling-prefix','nested'):
            root=d.fresh('11-membership-'+style)
            if style=='foreign':other=d.fresh('11-other-root');other_nonce=other.parent.name
            else:
                other=root.with_name(root.name+'-sibling') if style=='sibling-prefix' else root/'nested';other_nonce=root.parent.name
                c=d.child([a.probe,'init',str(other),other_nonce,'none',str(d.job.h)]);assert c.finish()==0,c.read()
            c=d.child([a.probe,'write',str(other),other_nonce,'source.bin',str(d.job.h)]);assert c.finish()==0,c.read()
            def snapshot(folder):
                result={};pending=[folder]
                while pending:
                    parent=pending.pop()
                    with os.scandir(parent) as entries:
                        for entry in entries:
                            assert len(result)<128
                            path=Path(entry.path);st=entry.stat(follow_symlinks=False);assert not getattr(st,'st_file_attributes',0)&0x400
                            assert stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)
                            result[str(path.relative_to(folder))]=(st.st_mode,P.identity(path),bounded_read(path,1024**2) if stat.S_ISREG(st.st_mode) else None)
                            if stat.S_ISDIR(st.st_mode):pending.append(path)
                return (P.identity(folder),result)
            before_root=snapshot(root);before_other=snapshot(other)
            r=d.call('rename-foreign',root,str(other),success=False,reason='rename-source-parent')
            assert not r['rename_attempted'] and not r['target_sdk_open_attempted'] and snapshot(root)==before_root and snapshot(other)==before_other and not (root/'published.bin').exists() and not (other/'published.bin').exists()
    def g12():
        root=d.fresh('12-share-refusal');c=d.native('rename-paused',root);c.phase(root,'before-rename');old=statfile(root/'source.bin');h=native_share(root/'source.bin',0x80000000,1|2)
        try:d.go(root,'before-rename');assert c.finish()!=0;assert c.report()['reason']=='regular-open' and c.report()['native_error']==32
        finally:check(close(h),'close refusal handle')
        assert statfile(root/'source.bin')==old and not (root/'published.bin').exists()
    def g13():
        root,before=fixture('13-outer');c=d.native('owner',root,'rollback');c.phase(root,'before-sdk');d.go(root,'before-sdk');c.phase(root,'owner-held');r=d.call('slots',root,success=False,reason='regular-open');assert r['native_error']==32 and not r['target_sdk_open_attempted'];d.writer(root,True);d.go(root,'owner-held');finish_owner(c,root);stable(before,root)
    def g14():
        root,before=fixture('14-inherited');c=d.native('launch',root,'normal');c.phase(root,'child-spawned');d.go(root,'child-spawned');marker=c.phase(root,'child-live');assert marker['sdk_open_attempted'];assert not move(str(root/'worker-output'),str(root/'foreign-output'),0);assert ctypes.get_last_error() in (5,32);h=openfile(str(root/'slot-0.lock'),0xc0000000,0,None,3,0,None);assert h==BAD and ctypes.get_last_error()==32;d.writer(root,True);d.go(root,'child-live');c.phase(root,'child-waited');d.go(root,'child-waited');assert c.finish()==0 and c.report()['worker_waited'];d.call('slots',root);stable(before,root)
    def g15():
        root,before=fixture('15-live-sdk-orphan');c=d.native('launch',root,'normal');c.phase(root,'child-spawned');d.go(root,'child-spawned');c.phase(root,'child-live');assert c.finish(terminate=True)==125
        assert not move(str(root/'worker-output'),str(root/'retained-output'),0);assert ctypes.get_last_error() in (5,32)
        r=d.call('slots',root,success=False,reason='regular-open');assert r['native_error']==32;d.writer(root,True)
        d.job.finish();d.job=Job();d.call('slots',root);stable(before,root)
        # An earlier genuinely live child holds the anchored slot but has not
        # pinned output or opened SDK yet: whole-output disappearance is real.
        root,before=fixture('15-before-output-pin');c=d.native('launch',root,'prepin');c.phase(root,'child-spawned');marker=c.phase(root,'child-before-pin');assert not marker['sdk_open_attempted'];assert c.finish(terminate=True)==125
        (root/'worker-output').rename(root/'retained-output');r=d.call('slots',root,success=False,reason='regular-open');assert r['native_error']==32 and not r['target_sdk_open_attempted'];d.writer(root,False)
        d.job.finish();d.job=Job();d.call('slots',root,success=False,reason='retained-output-missing');stable(before,root)
    def g16():
        for variant in ('spawn-gap','assign-fail'):
            root,before=fixture('16-'+variant);r=d.launch(root,variant,success=False);assert not r['target_sdk_open_attempted']
            if variant=='spawn-gap':assert read_child_report(root)['reason']=='child-owner-go-absent' and not read_child_report(root)['target_sdk_open_attempted']
            else:assert r['native_error']!=0 and r['cleanup_wait_result']==0
            stable(before,root);d.call('slots',root)
    def g17():
        for variant in ('wrong-kind','wrong-nonce','wrong-producer','wrong-output'):
            root,before=fixture('17-'+variant);r=d.launch(root,variant,success=False);assert r['reason']=='child-nonzero';child=read_child_report(root);assert not child['target_sdk_open_attempted'] and child['reason'] in ('child-request-envelope','child-output-replaced');stable(before,root)
        for kind in ('missing','partial'):
            root,before=fixture('17-result-'+kind)
            def edit(root):
                (root/'child-result.json').rename(root/'retained-child-result.json')
                if kind=='partial':d.put(root,'child-result.json',b'{"format":')
            r=d.launch(root,success=False,result_edit=edit);assert r['worker_waited'] and r['reason'] in ('regular-open','child-result-binding');stable(before,root)
    def g18():
        root,before=fixture('18-wait-proof');r=d.launch(root);assert r['worker_waited'] and r['contained'];result=json.loads((root/'child-result.json').read_bytes());assert result['complete'] and result['finish_status']==0 and result['nonce']==root.parent.name;d.call('slots',root);d.call('completion',root,success=False,reason='restart-has-no-actual-wait-proof');stable(before,root)
        root,before=fixture('18-coherent-result-forgery')
        def coherent(root):
            use=root/'use-0.json';result=root/'child-result.json';ids=(P.identity(use),P.identity(result));raw=bounded_read(use,4096);value=json.loads(raw);value['output_id']='0'*48;changed=(json.dumps(value,separators=(',',':'))+'\n').encode();report=json.loads(bounded_read(result,4096));report['request_sha256']=hashlib.sha256(changed).hexdigest()
            for path,payload in ((use,changed),(result,bounded_json(report,4096))):
                with path.open('wb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
            assert ids==(P.identity(use),P.identity(result))
        r=d.launch(root,success=False,result_edit=coherent);assert r['worker_waited'] and r['reason']=='parent-request-changed';stable(before,root)
        root,before=fixture('18-restart-target-binding');d.launch(root);replace_file(root,'library.sqlite');foreign=statfile(root/'library.sqlite');d.call('slots',root,success=False,reason='retained-target-replaced');r=d.call('owner',root,'rollback',success=False,reason='retained-target-replaced');assert not r['target_sdk_open_attempted'] and statfile(root/'library.sqlite')==foreign;stable(before,root)
    def g19():
        root,before=fixture('19-descendant');c=d.native('launch',root,'descendant');c.phase(root,'child-spawned');d.go(root,'child-spawned');c.phase(root,'grandchild-live');c.phase(root,'child-waited');d.go(root,'child-waited');assert c.finish()!=0 and c.report()['native_error']==32
        r=d.call('slots',root,success=False,reason='regular-open');assert r['native_error']==32;assert d.job.active()>=1;d.job.finish();d.job=Job();d.call('slots',root);stable(before,root)
    def g20():
        for schema in (6,7):
            for journal in ('delete','wal'):
                root,before=fixture('20-%s-%s'%(schema,journal),schema,journal)
                with contextlib.closing(P.connect(root/'library.sqlite')) as readonly:
                    try:readonly.execute('UPDATE books SET title=title')
                    except sqlite3.OperationalError as e:assert e.sqlite_errorcode&255==sqlite3.SQLITE_READONLY
                    else:raise AssertionError('read-only calibration unexpectedly wrote')
                r=d.owner(root);assert r['target_sdk_open_attempted'] and r['finish_status']==0 and not r['commit_requested'];stable(before,root)
    def g21():
        for schema in (6,7):
            root,before=fixture('21-scan-%s'%schema,schema,'wal');r=d.owner(root,'scan',scan=True,expected=before);assert r['worker_waited'];stable(before,root)
            projection=root/'worker-output/public-projection.jsonl';rows=[json.loads(line) for line in projection.read_bytes().splitlines()];assert rows==before['public'];bad=list(rows);bad[0]=list(bad[0]);bad[0][3]='changed-projection'
            try:projection_equal(bad,before['public'])
            except AssertionError:pass
            else:raise AssertionError('actual projection comparator admitted mutation')
    def g22():
        root,before=fixture('22-real-delete-IO',7,'delete')
        r=d.owner(root,before_finish=lambda root:P.deny_delete(root/'library.sqlite-journal'))
        expected=str(root/'library.sqlite-journal').replace('\\','/').casefold();events=[]
        for event in r['sqlite_events']:
            m=re.fullmatch(r'os_(win|unix)\.c:\d+: \((\d+)\) ([A-Za-z0-9_]+)\((.*?)\) - [^\r\n]*',event['message'])
            if m and m.group(1)=='win' and int(m.group(2))==32 and m.group(3)=='winDelete' and m.group(4).replace('\\','/').casefold()==expected and event['phase']=='sdk-finish' and event['code']==sqlite3.SQLITE_IOERR_DELETE:events.append(event)
        assert events,r;assert isinstance(r['finish_status'],int) and not r['commit_requested'];assert d.cases[-1]['fault_at_finish']['journal_present'];stable(before,root)
        d.cases[-1]['actual_sdk_finish_status']=r['finish_status'];d.cases[-1]['actual_internal_io']=events
    def g23():
        root,before=fixture('23-later-changed');d.put(root,'baseline.bin',before['canonical']);d.writer(root,False,'later-writer-kept');later=model(root/'library.sqlite');c=scan_gate(root,later);assert c.finish()!=0;cdata=c.report();assert cdata['reason']=='current-baseline-parity-mismatch' and not cdata['commit_requested'];stable(later,root)
        for style in ('noop','aba'):
            root,before=fixture('23-'+style);d.put(root,'baseline.bin',before['canonical']);original=next(row[3] for row in before['rows']['books'] if row[1]==1)
            if style=='aba':d.writer(root,False,'temporary-change')
            d.writer(root,False,original);r=d.owner(root,'handoff',expected=before);assert r['commit_requested'];parity(before,model(root/'library.sqlite'),'windows-native-planned-title')
        d.cases[-1]['guarantee']='current parity only; not historical rollback or COMMIT proof'
    def g24():
        for schema in (6,7):
            root,before=fixture('24-handoff-%s'%schema,schema,'delete');d.put(root,'baseline.bin',before['canonical']);original=statfile(root/'baseline.bin');r=d.owner(root,'handoff',expected=before);assert r['commit_requested'] and r['finish_status']==0 and r['worker_waited'];parity(before,model(root/'library.sqlite'),'windows-native-planned-title');assert statfile(root/'baseline.bin')==original and (root/'anchor.json').exists() and (root/'prepared.json').exists() and (root/'ack.json').exists();d.call('slots',root);d.call('completion',root,success=False,reason='restart-has-no-actual-wait-proof');d.writer(root,False,'ordinary-writer-after-ack');later=model(root/'library.sqlite');d.call('completion',root,success=False,reason='restart-has-no-actual-wait-proof');stable(later,root)
    cases=[g01,g02,g03,g04,g05,g06,g07,g08,g09,g10,g11,g12,g13,g14,g15,g16,g17,g18,g19,g20,g21,g22,g23,g24]
    for index,case in enumerate(cases,1):d.execute('%02d-%s'%(index,case.__name__),case)
    d.save();passed=sum(x['passed'] for x in d.cases);print('native qualification %d/24'%passed,flush=True);return 0 if passed==24 and not FATAL else 1
ARCHIVE_BYTES=1024**3
ARCHIVE_MANIFEST=8*1024**2
ARCHIVE_HEADROOM=16*1024**2

def artifact_path(relative):
    text=relative.as_posix();assert len(text.encode('utf-8'))<=4096 and len(relative.parts)<=32 and all(0<len(p.encode('utf-8'))<=1024 for p in relative.parts)
    return text

def artifact_payload(entries,total,budget=ARCHIVE_BYTES):
    assert len(entries)<=28000
    for item in entries:artifact_path(Path(item['path']))
    raw=bounded_json(dict(complete=True,entries=entries,total_regular_bytes=total,reparse_objects_are_metadata_only=True,terminal_workspace_only=True),ARCHIVE_MANIFEST)
    assert total+len(raw)+4096<=budget
    return raw

def artifact_publish(folder,raw,partial=False):
    assert len(raw)<=ARCHIVE_MANIFEST
    stage=folder/'manifest.stage.json';final=folder/'manifest.json'
    with stage.open('xb') as stream:
        if partial:
            stream.write(raw[:min(7,len(raw))]);stream.flush();os.fsync(stream.fileno());raise RuntimeError('deliberate helper interruption before final publication')
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    assert bounded_read(stage,ARCHIVE_MANIFEST)==raw
    check(move(str(stage),str(final),8),'no-replace manifest publication')
    assert bounded_read(final,ARCHIVE_MANIFEST)==raw

def artifact_controls(folder):
    controls=folder/'helper-controls';controls.mkdir();raw=artifact_payload([dict(path='a',kind='regular')],1)
    try:artifact_payload([dict(path='a',kind='regular')],1,budget=8)
    except AssertionError:pass
    else:raise AssertionError('manifest output budget admitted')
    try:artifact_payload([dict(path='x'*4097,kind='regular')],0)
    except AssertionError:pass
    else:raise AssertionError('overlong manifest path admitted')
    incomplete=controls/'INCOMPLETE.json';incomplete.write_bytes(b'{"complete":false}\n')
    try:artifact_publish(controls,raw,partial=True)
    except RuntimeError:pass
    else:raise AssertionError('partial publication unexpectedly completed')
    assert incomplete.read_bytes()==b'{"complete":false}\n' and not (controls/'manifest.json').exists() and 0<(controls/'manifest.stage.json').stat().st_size<len(raw)
    (controls/'controls.json').write_bytes(b'{"budget":true,"long_path":true,"partial_final_write":true}\n')
    return 3

# Terminal-only archive admission. Every ancestor and active directory stays
# pinned without write/delete sharing while relative children are enumerated.
def archive_evidence(destination):
    import msvcrt
    class ID(ctypes.Structure):_fields_=[('volume',ctypes.c_ulonglong),('file',ctypes.c_ubyte*16)]
    class TAG(ctypes.Structure):_fields_=[('attributes',W.DWORD),('tag',W.DWORD)]
    info=api('GetFileInformationByHandleEx',W.BOOL,[W.HANDLE,ctypes.c_int,LPVOID,W.DWORD])
    started=time.monotonic();entries=[];total=0;destination=destination.resolve();destination.mkdir(exist_ok=False)
    receipt=destination/'INCOMPLETE.json'
    with receipt.open('xb') as initial:initial.write(b'{"complete":false,"reason":"archive-incomplete"}\n');initial.flush();os.fsync(initial.fileno())
    controls=artifact_controls(destination)
    def identity(handle):
        value=ID();tag=TAG();check(info(handle,18,ctypes.byref(value),ctypes.sizeof(value)),'archive full identity');check(info(handle,9,ctypes.byref(tag),ctypes.sizeof(tag)),'archive attributes')
        return '%016x'%value.volume+bytes(value.file).hex(),tag.attributes,tag.tag
    def pin(path):
        handle=openfile(str(path),0x80|0x20000,1,None,3,0x02000000|0x00200000,None);check(handle!=BAD,'archive directory pin');value=identity(handle)
        if value[1]&0x400 or not value[1]&0x10:close(handle);raise AssertionError(('archive directory reparse/type',str(path)))
        return handle,value
    def limit():assert time.monotonic()-started<180 and len(entries)<28000
    def visit(source,relative):
        nonlocal total
        limit();before=source.lstat();record=dict(path=artifact_path(relative),size=before.st_size)
        if getattr(before,'st_file_attributes',0)&0x400:
            # Read metadata from the reparse object itself, never its destination.
            handle=openfile(str(source),0x80,1,None,3,0x02000000|0x00200000,None);check(handle!=BAD,'reparse metadata handle')
            try:value=identity(handle);assert value[1]&0x400;record.update(kind='reparse-metadata-only',identity=value[0],attributes=value[1],reparse_tag=value[2]);entries.append(record)
            finally:close(handle)
        elif stat.S_ISDIR(before.st_mode):
            handle,value=pin(source)
            try:
                record.update(kind='directory',identity=value[0]);entries.append(record)
                with os.scandir(source) as listing:
                    for item in listing:visit(Path(item.path),relative/item.name)
                assert identity(handle)==value
            finally:close(handle)
        elif stat.S_ISREG(before.st_mode):
            assert before.st_size<=64*1024**2 and total+before.st_size<=ARCHIVE_BYTES-ARCHIVE_HEADROOM
            handle=openfile(str(source),0x80000000|0x20000,1,None,3,0x00200000,None);check(handle!=BAD,'archive no-follow file')
            transferred=False
            try:
                value=identity(handle);assert not value[1]&(0x400|0x10)
                fd=msvcrt.open_osfhandle(int(handle),os.O_RDONLY|os.O_BINARY);transferred=True
                target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);digest=hashlib.sha256();read=0
                with os.fdopen(fd,'rb') as src,target.open('xb') as dst:
                    opened=os.fstat(src.fileno());assert (opened.st_dev,opened.st_ino,opened.st_size)==(before.st_dev,before.st_ino,before.st_size)
                    while True:
                        block=src.read(65536)
                        if not block:break
                        read+=len(block);assert read<=before.st_size;limit();digest.update(block);dst.write(block)
                    assert read==before.st_size and identity(handle)==value
                total+=read;record.update(kind='regular',identity=value[0],sha256=digest.hexdigest());entries.append(record)
            finally:
                if not transferred:close(handle)
        else:raise AssertionError(('unsupported node',str(source)))
    roots=[Path('build/evidence'),Path('build/windows-native'),Path('build/windows-frozen-preflight'),Path('build/native/native-provider.map'),Path('build/native/link-closure.txt'),Path('build/native/frozen-preflight/provider.map'),Path('build/native/frozen-preflight/link-closure.txt')]
    for root in roots:
        try:root.lstat()
        except FileNotFoundError:continue
        source=Path(os.path.abspath(root));pins=[]
        try:
            # Every original pathname component is pinned; no resolve()/link traversal.
            for parent in reversed(source.parents):pins.append(pin(parent)[0])
            relative=Path('provider')/source.parent.name/source.name if source.suffix in ('.map','.txt') else Path(source.name)
            visit(source,relative)
        finally:
            for handle in reversed(pins):close(handle)
    raw=artifact_payload(entries,total)
    # Re-inventory the actual destination, including directory nodes, helper
    # controls and the immutable incomplete receipt, before final publication.
    pending=[destination];out_count=0;out_bytes=0
    while pending:
        directory=pending.pop()
        with os.scandir(directory) as listing:
            for entry in listing:
                limit();out_count+=1;assert out_count+2<=30000
                st=entry.stat(follow_symlinks=False);assert not getattr(st,'st_file_attributes',0)&0x400
                artifact_path(Path(entry.path).relative_to(destination))
                if stat.S_ISDIR(st.st_mode):pending.append(Path(entry.path))
                else:
                    assert stat.S_ISREG(st.st_mode) and st.st_size<=64*1024**2
                    out_bytes+=st.st_size;assert out_bytes+len(raw)<=ARCHIVE_BYTES
    artifact_publish(destination,raw)
    # Final exact bytes are included in the accounted total. INCOMPLETE remains
    # immutable; only the exclusive final manifest is a completion receipt.
    assert out_bytes+(destination/'manifest.json').stat().st_size<=ARCHIVE_BYTES
    assert bounded_read(destination/'manifest.json',ARCHIVE_MANIFEST)==raw
    print('artifact helper controls',controls,'final output bytes',out_bytes+len(raw),flush=True)

    print('retained evidence nodes',len(entries),'regular bytes',total,flush=True)

if __name__=='__main__':
    if sys.argv[1:]==['--archive']:archive_evidence(Path('build/retained-evidence'))
    else:raise SystemExit(main())

