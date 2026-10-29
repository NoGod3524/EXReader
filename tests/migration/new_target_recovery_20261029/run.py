#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only real new-target importer, publication and same-root C acceptance."""
import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sqlite3
import stat
import sys
import time

if os.environ.get('GITHUB_ACTIONS')!='true':
    raise SystemExit('Builds, fixtures, tests and artifact parsing are Actions-only')
SPEC=importlib.util.spec_from_file_location('unchanged_integration',Path(__file__).parents[1]/'recovery_integration_20261029/run.py')
I=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(I)
L=I.L;P=I.P;MIB=1024*1024

class Child(I.Child):
    def wait(self,target,phase):
        until=min(self.deadline,time.monotonic()+35);root=Path(str(target)+'.migration-recovery')
        while time.monotonic()<until and self.p.poll() is None:
            matches=[p for p in root.glob('*/'+phase+'.ready') if not p.with_suffix('.go').exists()]
            if matches:return matches[-1]
            time.sleep(.01)
        raise AssertionError(('actual creation boundary unavailable',phase,self.p.poll(),self.out.read_text(errors='replace'),self.err.read_text(errors='replace')))

class Driver(I.Driver):
    def __init__(self,a):
        super().__init__(a);self.evidence['scope']='real POSIX private DELETE creation, no-replace public adoption and fresh C; no Windows recovery';self.orphans=[]
    def args(self,f,command='migrate',pack=None,extra=(),create=True):
        result=[self.a.candidate,command,'--target',f['target']]
        if command in ('migrate','recover-migration','verify','inspect'):result+=['--pack',pack or f['pack']]
        if self.a.font:result+=['--recovery-font',self.a.font]
        if create:result+=['--create-target']
        return result+list(extra)
    def call(self,*argv,env=None):
        c=Child(self,argv,env);return c.finish(),c.report() if c.out.read_bytes().lstrip().startswith(b'{') else c.out.read_text(errors='replace'),c
    def start(self,f,phase,command='migrate',extra=(),pack=None):
        c=Child(self,self.args(f,command,pack,extra),{'EXR_CREATE_PAUSE':phase});return c,c.wait(f['target'],phase)
    def fixture(self,folder,books=None,notes=None):
        folder.mkdir(mode=0o700,parents=True,exist_ok=True);target=folder/'library.sqlite';pack=folder/'source.exrpack'
        if books is None:books=[L.entry(L.book_record('first','first.txt',title='new standalone original'),L.TXT)]
        if notes is None:notes=[L.note_record('first-note','first','lantern keeper','new comment')]
        pack.write_bytes(L.build_pack(books,notes));return dict(target=target,pack=pack,root=Path(str(target)+'.migration-recovery'),mirror=Path(str(target)+'.legacy-map.json'),books=books,notes=notes)
    def records(self,f):return [json.loads(p.read_text()) for p in sorted(f['root'].glob('record-*.json'))]
    def image(self,f):
        records=self.records(f);return f['root']/('image-'+next(r['producer'] for r in reversed(records) if r['magic']=='EXRCREATE1')+'.sqlite')
    def pending(self,f,rc,r,reasons=None):
        self.check('actual nonzero retained refusal',rc!=0 and r['creation']['explicit_recovery_required'],r)
        if reasons:self.check('exact original refusal cause',r['code'] in reasons,(r['code'],reasons))
        self.check('permanent creation anchor and shared barrier retained',(f['root']/'anchor.json').is_file() and Path(str(f['target'])+'.migrate-lock').is_file())
    def created(self,f,rc,r):
        self.check('literal creation acknowledged',rc==0 and r['creation']['creation_acknowledged'],r)
        self.check('coordinator does not invent import counts',r['counts'] is None and r['creation']['private_import_report']['parent_successful_wait_recorded'] is True)
        before=I.model(f['target']);self.check('standalone schema7 full integrity',before['schema']==7 and before['app']==1163416131)
        records=self.records(f);sealed=next(x for x in records if x['magic']=='EXRCREATE1' and x['phase']==4)
        self.check('no live private pathname after publication',not self.image(f).exists())
        self.check('exact planned inode installed',('%016x%016x'%I.identity(f['target']))==sealed['image'][1])
        self.check('full independent canonical oracle matches sealed prepublication snapshot',(f['root']/sealed['verify_token']/'baseline.bin').read_bytes()==before['canonical'])
        public=[json.loads(line) for line in (f['root']/sealed['verify_token']/'public-projection.jsonl').read_text().splitlines()]
        self.check('independent public projection of actual resulting library',public==before['public'])
        ledger=json.loads(before['rows']['exr_migration_ledger'][0][2]);self.check('internal ledger is exact planned mirror',ledger==json.loads(f['mirror'].read_text()) and hashlib.sha256(f['pack'].read_bytes()).hexdigest() in ledger['packs'])
        self.check('raw note records retained',{n['legacy_id']:n['retained'] for n in ledger['notes']}=={n['id']:n for n in f['notes']})
        self.check('raw book records retained except cover',{b['legacy_id']:b['retained'] for b in ledger['books']}=={b['legacy_id']:{k:v for k,v in b['record'].items() if k!='cover'} for b in f['books']})
        for ending in ('-wal','-shm','-journal'):self.check('standalone publication lacks '+ending,not Path(str(f['target'])+ending).exists())
        self.check('not full P0 or physical power-loss proof',r['creation']['full_p0_acceptance'] is False and r['creation']['physical_power_loss_qualified'] is False)
        return before
    def slot_transition(self,f,before):
        # Only the two preallocated empty use inodes consumed by this actual
        # capture+owner scan may change. All other retained evidence is exact.
        root=f['root'];manifest=json.loads((root/'worker-slots.json').read_text());empty=hashlib.sha256(b'').hexdigest()
        slots=[i for i in range(8) if before['worker-slot-%02d.use'%i][1]==empty][:2]
        self.check('exact two previously unused slots available',len(slots)==2)
        changed={name for name,old in before.items() if I.state(root/name)!=old}
        expected={'worker-slot-%02d.use'%i for i in slots}
        self.check('only exact two single-use records change',changed==expected,sorted(changed))
        records=self.records(f);suffix=[x for x in records if x['magic']=='EXRCREATE1-C'];generation=max(x['generation'] for x in suffix)
        base=next(x for x in suffix if x['generation']==generation and x['phase'] in (1,6));opening=next(x for x in suffix if x['generation']==generation and x['phase']==2)
        nonce=base['run'];heads=[base['previous'],hashlib.sha256((root/('record-%02d.json'%opening['ordinal'])).read_bytes()).hexdigest()]
        for serial,(i,kind,head) in enumerate(zip(slots,('create-capture','create-scan'),heads),1):
            name='worker-slot-%02d.use'%i;p=root/name;raw=p.read_bytes();u=json.loads(raw);lock,initial=manifest['slots'][i]
            token=('cap' if serial==1 else 'scan')+'-'+nonce+'-%02d'%serial;output=root/token;request_path=output/'request.json';request_raw=request_path.read_bytes();request=json.loads(request_raw)
            descriptor=[1,'%016x%016x'%I.identity(request_path),hashlib.sha256(request_raw).hexdigest(),len(request_raw)]
            expected_use=dict(magic='EXRCREATE1-WORKER',slot=i,nonce=nonce,token=token,output_identity='%016x%016x'%I.identity(output),predecessor=head,request=descriptor)
            self.check('same anchored use inode empty to one canonical complete request',I.identity(p)==before[name][0] and initial==[1,'%016x%016x'%I.identity(p),empty,0] and raw==(json.dumps(expected_use,separators=(',',':'))+'\n').encode(),u)
            self.check('request binds actual phase producer output target and lease',request['nonce']==nonce and request['kind']==kind and request['output']==str(output) and request['output_identity']==expected_use['output_identity'] and request['target']==str(f['target']) and request['live']==str(root/('worker-slot-%02d.lock'%i)) and request['live_file']==lock and request['image_file'][0:3]==[1,'%016x%016x'%I.identity(f['target']),'0'*64] and request['pack']=='-' and request['pack_file']==[0,'','',0] and request['font']==self.a.font and request['font_file']==json.loads((root/'anchor.json').read_text())['font'],request)
            self.check('all required use file and lease ownership preserved',p.lstat().st_nlink==1 and stat.S_IMODE(p.lstat().st_mode)==0o600 and I.state(root/('worker-slot-%02d.lock'%i))==before['worker-slot-%02d.lock'%i])
        self.check('all other prior immutable evidence preserved',all(I.state(root/name)==old for name,old in before.items() if name not in expected))
    def recover(self,f,extra=()):return self.call(*self.args(f,'recover-migration',extra=extra))
    def lock_busy(self,p,busy=True):
        fd=os.open(p,os.O_RDWR|os.O_NOFOLLOW)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:self.check('actual inherited OFD exclusion busy',busy);return
            self.check('actual liveness available only after exit',not busy)
        finally:os.close(fd)
    def finish_orphan(self,pid,live,ready):
        self.lock_busy(live,True);I.private_token(ready.with_suffix('.go'))
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            fd=os.open(live,os.O_RDWR|os.O_NOFOLLOW)
            try:
                try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);return
                except BlockingIOError:pass
            finally:os.close(fd)
            time.sleep(.02)
        # Only the exact fresh child PID returned by this invocation's owned
        # record is considered; a held liveness lock proves this attempt persists.
        os.kill(pid,signal.SIGKILL)
        raise AssertionError('owned orphan did not release its bound liveness lease after GO')

def main():
    ap=argparse.ArgumentParser()
    for k in ('candidate','tool','old-tool','fixture','font'):ap.add_argument('--'+k,required=True)
    ap.add_argument('--work',type=Path,required=True);ap.add_argument('--fixtures',type=Path,required=True);ap.add_argument('--harness-admission',type=Path,required=True)
    a=ap.parse_args()
    for k in ('candidate','tool','old_tool','fixture','font'):setattr(a,k,str(Path(getattr(a,k)).resolve()))
    a.work=a.work.resolve();a.fixtures=a.fixtures.resolve();d=Driver(a)
    def simple(folder,full=False):
        books,notes=L.dataset() if full else (None,None);f=d.fixture(folder,books,notes);rc,r,_=d.call(*d.args(f,extra=('--allow-partial',) if full else ()));d.created(f,rc,r)
        if full:
            child=json.loads(next(f['root'].glob('import-*/stdout.json')).read_text());d.check('whole original five-book sixteen-note fixture',child['counts']['books_expected']==5 and child['counts']['notes_expected']==16 and child['counts']['books_accounted']==5 and child['counts']['notes_accounted']==16,child)
            d.check('only known audio unsupported',[(e['code'],e['legacy_id']) for e in child['entries'] if e['severity']=='unsupported']==[('audio-original-not-storable','b-audio')])
    def strict(folder):
        books,notes=L.dataset();f=d.fixture(folder,books,notes);rc,r,_=d.call(*d.args(f));d.pending(f,rc,r,['create-child-exit-refused']);d.check('strict original policy never publishes',not f['target'].exists())
        child=json.loads(next(f['root'].glob('import-*/stdout.json')).read_text());d.check('exact child original strict policy',child['code']=='policy-strict' and child['atomicity']['transaction']['target_commit']!='committed',child)
        retained=I.inventory(f['root']);rc,r,_=d.recover(f,('--allow-partial',));d.created(f,rc,r);d.check('unknown/failed first attempt preserved',all(I.state(f['root']/p)==v for p,v in retained.items()))
    def formats(folder):
        paths={ext:a.fixtures/('sample.'+ext) for ext in ('txt','html','fb2','epub','docx','rtf','mobi')}
        paths['pdf']=folder/'sample.pdf';paths['pdf'].write_bytes(L.pdf());paths['cbz']=folder/'sample.cbz';paths['cbz'].write_bytes(L.cbz())
        for ext,p in paths.items():
            f=d.fixture(folder/ext,[L.entry(L.book_record('format-'+ext,'sample.'+ext),p.read_bytes())],[])
            rc,r,_=d.call(*d.args(f));d.created(f,rc,r)
    def later(folder):
        f=d.fixture(folder);rc,r,_=d.call(*d.args(f));d.created(f,rc,r);I.writer(f['target'],False,True);prior=I.model(f['target']);identity=I.identity(f['target']);original=I.inventory(f['root'])
        pack=folder/'next.pack';pack.write_bytes(L.build_pack([L.entry(L.book_record('second','second.txt'),L.TXT_OTHER)],[]))
        rc,r,_=d.call(*d.args(f,pack=pack,create=False));d.check('actual fresh C same-root handoff succeeds',rc==0 and r['atomicity']['recovery']['route']=='creation-C' and r['atomicity']['recovery']['same_owner_comparison'],r)
        now=I.model(f['target']);d.check('all later writer rows and target identity retained',I.identity(f['target'])==identity and all(all(row in now['rows'][t] for row in rows) for t,rows in prior['rows'].items() if t!='exr_migration_ledger'))
        records=d.records(f);d.check('one canonical ordered profile and suffix',all(r['ordinal']==i for i,r in enumerate(records)) and any(r['magic']=='EXRCREATE1-C' for r in records))
        d.slot_transition(f,original)
        before_second=I.inventory(f['root']);I.writer(f['target'],False)
        with contextlib.closing(sqlite3.connect(f['target'],timeout=0)) as writer_db:writer_db.execute("UPDATE books SET title='second later writer retained' WHERE id=(SELECT min(id) FROM books)");writer_db.commit()
        prior2=I.model(f['target']);pack2=folder/'third.pack';pack2.write_bytes(L.build_pack([L.entry(L.book_record('third','third.txt'),L.TXT+b' third pack payload')],[]))
        rc,r,_=d.call(*d.args(f,pack=pack2,create=False));d.check('second fresh C means three distinct real packs',rc==0 and r['atomicity']['recovery']['route']=='C',r)
        d.slot_transition(f,before_second)
        now2=I.model(f['target']);d.check('second C preserves first C plus later writer state',all(all(row in now2['rows'][t] for row in rows) for t,rows in prior2['rows'].items() if t!='exr_migration_ledger'))
        ledger=json.loads(now2['rows']['exr_migration_ledger'][0][2]);d.check('exact three distinct pack hashes retained',all(hashlib.sha256(p.read_bytes()).hexdigest() in ledger['packs'] for p in (f['pack'],pack,pack2)))
        rc,_,_=d.call(*d.args(f,'verify',pack=pack2,create=False));d.check('guarded read after two actual C generations works',rc==0)
        retained=I.inventory(f['root']);before_capacity=I.model(f['target']);rc,r,_=d.call(*d.args(f,pack=pack2,create=False));d.check('finite record reservation refuses further import before SDK',rc!=0 and not r['atomicity']['recovery']['target_sdk_open_attempted'] and r['code']=='recovery-record-capacity-before-open',r)
        d.check('capacity refusal preserves all evidence and public state',all(I.state(f['root']/p)==v for p,v in retained.items()) and I.model(f['target'])['canonical']==before_capacity['canonical'])
    def preview(folder):
        for extra in (('--dry-run',),('--inject','cancel@0')):
            f=d.fixture(folder/str(len(list(folder.iterdir()))));rc,r,_=d.call(*d.args(f,extra=extra));d.check('preview/cancel never public',rc!=0 and not f['target'].exists(),r)
            if f['root'].exists():d.pending(f,rc,r)
    def crash(folder,phase):
        f=d.fixture(folder);c,ready=d.start(f,phase);image=d.image(f) if list(f['root'].glob('record-*.json')) else None
        child_info=None
        if phase in ('private-owner-open','private-commit-before-exit'):
            request=json.loads((ready.parent/'request.json').read_text());child_info=(int((ready.parent/'child.pid').read_text()),Path(request['live']),ready)
        c.finish(kill=True)
        if child_info:d.finish_orphan(*child_info)
        before=I.model(f['target']) if f['target'].exists() else None;ident=I.identity(f['target']) if before else None
        rc,r,_=d.recover(f)
        d.check('explicit restart converges without silent evidence deletion',rc==0,r)
        if before:d.check('visible original content retained',I.identity(f['target'])==ident and I.model(f['target'])['canonical']==before['canonical'])
        else:d.created(f,rc,r)
        if image and phase in ('private-attempt-durable','private-owner-open','private-commit-before-exit'):d.check('unacknowledged original image preserved',image.exists())
    def foreign_target(folder):
        f=d.fixture(folder);c,ready=d.start(f,'before-public-rename');f['target'].write_bytes(b'foreign target must not be replaced');before=I.state(f['target']);c.go(ready);rc=c.finish();d.pending(f,rc,c.report());d.check('foreign target exact',I.state(f['target'])==before and d.image(f).exists())
    def aliases(folder,hard=False):
        for ending in ('','-wal','-shm','-journal'):
            f=d.fixture(folder/(ending or 'db'));foreign=f['target'].parent/'foreign';foreign.write_bytes(b'foreign untouched');p=Path(str(f['target'])+ending)
            if hard:os.link(foreign,p)
            else:p.symlink_to(foreign)
            before=foreign.read_bytes();rc,r,_=d.call(*d.args(f));d.check('pre-open alias refused without root',rc!=0 and not f['root'].exists(),r);d.check('foreign bytes exact',foreign.read_bytes()==before)
        if hard:
            f=d.fixture(folder/'fifo');os.mkfifo(f['target']);rc,r,_=d.call(*d.args(f));d.check('FIFO refused without blocking',rc!=0 and not f['root'].exists(),r)
    def replace_image(folder):
        for phase in ('private-before-sdk-open','sealed-before-publish'):
            f=d.fixture(folder/phase);c,ready=d.start(f,phase);image=d.image(f);raw=image.read_bytes();old=image.with_suffix('.original');image.rename(old);image.write_bytes(raw);image.chmod(0o600);foreign=I.state(image);c.go(ready);rc=c.finish();d.pending(f,rc,c.report());d.check('same bytes never waive private identity',I.state(image)==foreign and not f['target'].exists())
    def foreign_evidence(folder):
        for kind in ('request','pack','plan','record'):
            f=d.fixture(folder/kind);phase='private-before-sdk-open' if kind in ('request','pack') else 'sealed-before-publish';c,ready=d.start(f,phase)
            p=next(f['root'].glob({'request':'import-*/request.json','pack':'pack-*.bin','plan':'import-*/planned-ledger.bin','record':'record-01.json'}[kind]));saved=p.with_name(p.name+'.original');p.rename(saved);p.write_bytes(saved.read_bytes());p.chmod(0o600);before=I.state(p);c.go(ready);rc=c.finish();d.pending(f,rc,c.report());d.check('equal-byte foreign evidence retained/refused',I.state(p)==before and not f['target'].exists())
        # A fresh public observation is different evidence from the original
        # sealed image. Neither equal bytes nor a missing observation may be
        # accepted after the final observation rendezvous.
        for name,remove in [('stdout.json',False),('baseline.bin',False),('clone.sqlite',False),('public-projection.jsonl',False),('baseline.bin',True)]:
            sub=folder/('observe-'+name+('-missing' if remove else ''));f=d.fixture(sub);c,ready=d.start(f,'public-before-sync');c.finish(kill=True)
            c,ready=d.start(f,'public-observation-before-adopt',command='recover-migration');prior=I.model(f['target']);ident=I.identity(f['target']);p=next(f['root'].glob('observe-*/'+name));saved=p.with_name(p.name+'.original');p.rename(saved)
            if not remove:p.write_bytes(saved.read_bytes());p.chmod(0o600)
            c.go(ready);rc=c.finish();d.pending(f,rc,c.report());d.check('fresh observation evidence cannot be replaced/missing',I.identity(f['target'])==ident and I.model(f['target'])['canonical']==prior['canonical'])

    def foreign_lock(folder):
        f=d.fixture(folder/'lock');lock=Path(str(f['target'])+'.migrate-lock');lock.write_bytes(b'foreign');before=I.state(lock);rc,r,_=d.call(*d.args(f));d.check('foreign shared lock exact',rc!=0 and I.state(lock)==before and not f['root'].exists(),r)
        positive=d.fixture(folder/'parent-positive');c,ready=d.start(positive,'sealed-before-publish');c.go(ready);rc=c.finish();d.created(positive,rc,c.report())
        f=d.fixture(folder/'parent');c,ready=d.start(f,'sealed-before-publish');original=f['target'].parent;original_id=I.identity(original);renamed=original.with_name(original.name+'-moved');relative=ready.relative_to(original)
        retained=I.inventory(f['root']);image_relative=d.image(f).relative_to(original);image_before=I.state(d.image(f));first=d.records(f)[0];live_relative=f['root'].relative_to(original)/('live-'+first['run']+'.lock')
        original.rename(renamed);original.mkdir(mode=0o700);replacement_ready=original/relative;replacement_ready.parent.mkdir(mode=0o700,parents=True);replacement_ready.write_bytes((renamed/relative).read_bytes());replacement_ready.chmod(0o600)
        d.check('exact predecessor liveness path moved with original parent',not (original/live_relative).exists() and '%016x%016x'%I.identity(renamed/live_relative)==first['live'][1] and I.identity(renamed)==original_id and I.identity(original)!=original_id)
        c.go(replacement_ready);rc=c.finish();r=c.report();d.check('exact retained parent-replacement refusal',rc!=0 and r['code']=='create-artifact-changed' and r['creation']['explicit_recovery_required'],r)
        d.check('earlier exact liveness lookup refuses after matched usable token',r['creation']['phase']=='sealed-before-publish' and r['creation']['records']==4 and not r['creation']['creation_acknowledged'] and not r['creation']['public_name_observed'] and not f['target'].exists() and not f['mirror'].exists(),r)
        d.check('entire moved original tree and private image preserved',all(I.state(renamed/f['root'].relative_to(original)/name)==old for name,old in retained.items()) and I.state(renamed/image_relative)==image_before and not (renamed/f['target'].name).exists())
        expected_namespace={relative.as_posix():stat.S_IFREG,relative.with_suffix('.go').as_posix():stat.S_IFREG}
        expected_namespace.update({p.as_posix():stat.S_IFDIR for p in relative.parents if p!=Path('.')})
        actual_namespace={};pending=[original]
        while pending:
            with os.scandir(pending.pop()) as listing:
                for entry in listing:
                    p=Path(entry.path);kind=stat.S_IFMT(entry.stat(follow_symlinks=False).st_mode);actual_namespace[p.relative_to(original).as_posix()]=kind
                    if kind==stat.S_IFDIR:pending.append(p)
        d.check('replacement parent has exact no-follow control namespace only',actual_namespace==expected_namespace,actual_namespace)
        d.check('replacement control bytes exact',replacement_ready.read_bytes()==(renamed/relative).read_bytes() and replacement_ready.with_suffix('.go').read_bytes()==b'continue\n')
        for kind in ('mirror','record','registry','suffix'):
            f=d.fixture(folder/('post-ack-'+kind));c,ready=d.start(f,'create-ack-durable');prior=I.model(f['target']);ident=I.identity(f['target'])
            p=f['mirror'] if kind=='mirror' else sorted(f['root'].glob('record-*.json'))[-1] if kind=='record' else f['root']/'worker-slots.json' if kind=='registry' else f['root']/('record-%02d.json'%len(d.records(f)))
            if kind=='suffix':p.write_bytes(b'foreign premature suffix')
            else:
                original=p.with_name(p.name+'.original');p.rename(original);p.write_bytes(original.read_bytes())
            p.chmod(0o600);foreign=I.state(p);c.go(ready);rc=c.finish();d.pending(f,rc,c.report());d.check('post-ACK foreign inode cannot produce success',I.state(p)==foreign and I.identity(f['target'])==ident and I.model(f['target'])['canonical']==prior['canonical'])

    def wal(folder):
        f=d.fixture(folder);c,ready=d.start(f,'private-finished-durable');image=d.image(f)
        with contextlib.closing(sqlite3.connect(image,timeout=0)) as db:
            d.check('actual private WAL control',db.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal');db.execute('PRAGMA wal_autocheckpoint=0');db.execute("UPDATE books SET title='uncheckpointed private canary'");db.commit();d.check('real nonempty WAL exists',Path(str(image)+'-wal').stat().st_size>32)
            c.go(ready);rc=c.finish();d.pending(f,rc,c.report());d.check('WAL state not converted or published',not f['target'].exists() and db.execute('SELECT title FROM books').fetchone()[0]=='uncheckpointed private canary')
    def reader(folder):
        f=d.fixture(folder);c,ready=d.start(f,'private-finished-durable');image=d.image(f)
        with contextlib.closing(sqlite3.connect(image,timeout=0)) as db:
            db.execute('BEGIN');db.execute('SELECT * FROM books').fetchall();c.go(ready);rc=c.finish();d.pending(f,rc,c.report());d.check('live private reader blocks seal rather than moving open image',not f['target'].exists())
        rc,r,_=d.recover(f);d.created(f,rc,r)
        # Matched successful seal: both outside reader and writer must be
        # excluded after actual DELETE/exclusive readback, not only before it.
        f=d.fixture(folder/'exclusive-positive');c,ready=d.start(f,'seal-read-fence');image=d.image(f)
        I.writer(image,True)
        with contextlib.closing(sqlite3.connect(image,timeout=0)) as db:
            try:db.execute('SELECT * FROM books').fetchall();raise AssertionError('reader crossed retained seal EXCLUSIVE fence')
            except sqlite3.OperationalError as error:d.check('actual seal reader numeric BUSY',I.error_code(error)&255==sqlite3.SQLITE_BUSY)
        c.go(ready);rc=c.finish();d.created(f,rc,c.report());I.writer(f['target'],False)
    def orphan(folder,sealing=False):
        f=d.fixture(folder);phase='seal-worker-alive' if sealing else 'private-owner-open';c,ready=d.start(f,phase);output=ready.parent;pid=int((output/'child.pid').read_text());request=json.loads((output/'request.json').read_text());live=Path(request['live']);d.lock_busy(live)
        os.kill(c.p.pid,signal.SIGKILL);c.finish();rc,r,_=d.recover(f);d.pending(f,rc,r,['create-child-or-coordinator-alive']);d.check('no seal or rename while orphan live',not f['target'].exists())
        d.finish_orphan(pid,live,ready);d.lock_busy(live,False);rc,r,_=d.recover(f);d.check('after child lifetime ended explicit retry is bounded',rc==0,r)
    def spawn_gap(folder):
        f=d.fixture(folder);c,ready=d.start(f,'spawn-gap');rec=d.records(f)[-1];live=f['root']/('live-'+rec['run']+'.lock');d.lock_busy(live);c.finish(kill=True);d.lock_busy(live,False);rc,r,_=d.recover(f);d.created(f,rc,r)
    def descriptor(folder):
        p=folder/'ofd';p.write_bytes(b'nonce');fd=os.open(p,os.O_RDWR);dup=os.dup(fd);other=os.open(p,os.O_RDWR)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);os.close(fd);fd=None
            try:fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB);raise AssertionError('duplicate close released lock')
            except BlockingIOError:pass
            fcntl.flock(dup,fcntl.LOCK_UN);fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB);d.check('native duplicate close vs explicit unlock calibrated',True)
        finally:
            for x in (fd,dup,other):
                if x is not None:os.close(x)
        f=d.fixture(folder/'invalid');rc,r,_=d.call(*d.args(f,extra=('--private-create-request',str(folder/'missing')),create=False));d.check('no unbound inherited FD may open SDK',rc!=0 and not f['target'].exists(),r)
        # Calibrate the actual typed internal channel with a real inherited
        # OFD, not a parent-side rejection before the child is launched.
        for mutation in ('valid','unknown-kind','mismatched-kind','missing-pack-binding','public-target'):
            f=d.fixture(folder/mutation);c,ready=d.start(f,'private-attempt-durable');c.finish(kill=True)
            request_path=next(f['root'].glob('import-*/request.json'));request=json.loads(request_path.read_text());target=Path(request['target'])
            if mutation=='unknown-kind':request['kind']='unknown'
            elif mutation=='mismatched-kind':request['kind']='observe'
            elif mutation=='missing-pack-binding':request['pack_file']=[0,'','',0]
            elif mutation=='public-target':
                f['target'].write_bytes(b'public foreign file not opened');target=f['target'];request['target']=str(target)
                request['image_file']=[1,'%016x%016x'%I.identity(target),hashlib.sha256(target.read_bytes()).hexdigest(),target.stat().st_size]
            request_path.write_text(json.dumps(request));request_path.chmod(0o600)
            before=I.state(target);original_fd=os.open(request['live'],os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(original_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            # Never depend on platform DUP2(3,3) clearing close-on-exec.
            # Keep only a distinct high CLOEXEC source; duplicate close is not unlock.
            try:live_fd=fcntl.fcntl(original_fd,fcntl.F_DUPFD,10);os.set_inheritable(live_fd,False)
            finally:os.close(original_fd)
            d.check('test spawn uses distinct inherited OFD source',live_fd>=10 and not os.get_inheritable(live_fd) and (os.fstat(live_fd).st_dev,os.fstat(live_fd).st_ino)==I.identity(Path(request['live'])))
            d.lock_busy(Path(request['live']))
            d.serial+=1;out=d.logs/('typed-%04d.stdout'%d.serial);err=d.logs/('typed-%04d.stderr'%d.serial);out_fd=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);err_fd=os.open(err,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            argv=[a.candidate,'migrate','--private-create-request',str(request_path),'--target',str(target),'--pack',request['pack'],'--recovery-font',a.font]
            pid=None;status=None;deadline=time.monotonic()+30
            d.check('bounded direct typed-channel log reservation',d.log_total+d.log_reserved+2*MIB<=16*MIB);d.log_reserved+=2*MIB
            try:
                actions=[(os.POSIX_SPAWN_OPEN,0,'/dev/null',os.O_RDONLY,0),(os.POSIX_SPAWN_DUP2,out_fd,1),(os.POSIX_SPAWN_DUP2,err_fd,2),(os.POSIX_SPAWN_DUP2,live_fd,3)]
                pid=os.posix_spawn(a.candidate,argv,dict(os.environ,EXR_MIGRATE_TEST_FAULTS='1'),file_actions=actions,setpgroup=0)
                os.close(live_fd);live_fd=None
                while time.monotonic()<deadline:
                    got,status_raw=os.waitpid(pid,os.WNOHANG)
                    if got:status=status_raw;break
                    assert out.stat().st_size+err.stat().st_size<=2*MIB
                    time.sleep(.01)
                assert status is not None,'typed internal child deadline'
            finally:
                if pid is not None and status is None:
                    os.killpg(pid,signal.SIGKILL);os.waitpid(pid,0)
                if live_fd is not None:os.close(live_fd)
                os.close(out_fd);os.close(err_fd);d.log_reserved-=2*MIB;d.log_total+=out.stat().st_size+err.stat().st_size
            report=json.loads(out.read_text());success=os.WIFEXITED(status) and os.WEXITSTATUS(status)==0
            if mutation=='valid':d.check('matched valid inherited import reaches actual SDK COMMIT',success and report['atomicity']['transaction']['target_commit']=='committed',report)
            else:d.check('mismatched typed envelope refuses before SDK and preserves bytes',not success and report['atomicity']['transaction']['target_commit']=='not-attempted' and I.state(target)==before,report)

    def transport(folder):
        for mutation in ('nonce','partial','deadline'):
            f=d.fixture(folder/mutation);phase='private-before-sdk-open' if mutation=='nonce' else 'child-exited-before-finished' if mutation=='partial' else 'private-before-commit';c,ready=d.start(f,phase)
            if mutation=='nonce':
                q=next(f['root'].glob('import-*/request.json'));data=json.loads(q.read_text());data['nonce']='f'*32;q.write_text(json.dumps(data));c.go(ready)
            elif mutation=='partial':next(f['root'].glob('import-*/stdout.json')).write_bytes(b'{');c.go(ready)
            rc=c.finish();d.pending(f,rc,c.report());d.check('transport ambiguity never admits public image',not f['target'].exists())
    def suffix_orphan(folder):
        orphan(folder/'seal',True)
        f=d.fixture(folder/'suffix');rc,r,_=d.call(*d.args(f));d.created(f,rc,r)
        # Real creation-context capture remains alive after parent death. Its
        # bound slot must block all candidate entrypoints even if output vanishes.
        c=Child(d,d.args(f,create=False),{'EXR_CREATE_PAUSE':'suffix-worker-alive'});ready=c.wait(f['target'],'suffix-worker-alive');request=json.loads((ready.parent/'request.json').read_text());live=Path(request['live'])
        pidfile=next(p for p in f['root'].glob('run-*/worker-01.pid'));pid=int(pidfile.read_text());d.lock_busy(live)
        os.kill(c.p.pid,signal.SIGKILL);c.finish();prior=I.model(f['target']);identity=I.identity(f['target']);original=ready.parent;renamed=original.with_name(original.name+'-removed');original.rename(renamed)
        rc,r,_=d.call(*d.args(f,create=False));d.pending(f,rc,r,['create-child-or-coordinator-alive']);d.check('whole output disappearance cannot hide live orphan or alter public state',not original.exists() and I.identity(f['target'])==identity and I.model(f['target'])['canonical']==prior['canonical'])
        # Restore the exact directory only to deliver the already-bound GO;
        # child still performs its envelope checks. It is not a new recovery.
        renamed.rename(original);d.finish_orphan(pid,live,ready);d.lock_busy(live,False);original.rename(renamed)
        rc,r,_=d.call(*d.args(f,create=False));d.pending(f,rc,r);d.check('missing anchored used output never silently regains capacity',not original.exists() and renamed.exists())
        manifest=json.loads((f['root']/'worker-slots.json').read_text());d.check('all eight slot pairs anchored from creation',len(manifest['slots'])==8)

    def writer_after_visibility(folder,phase):
        f=d.fixture(folder);c,ready=d.start(f,phase);I.writer(f['target'],False,True);prior=I.model(f['target']);identity=I.identity(f['target']);c.finish(kill=True);rc,r,_=d.recover(f);d.check('current-state public adoption succeeds',rc==0,r);d.check('later ordinary metadata never overwritten',I.identity(f['target'])==identity and I.model(f['target'])['canonical']==prior['canonical'])
    def aba(folder):
        for changed in (False,True):
            f=d.fixture(folder/str(changed));c,ready=d.start(f,'public-before-sync');prior=I.model(f['target'])
            with contextlib.closing(sqlite3.connect(f['target'],timeout=0)) as db:
                if changed:db.execute("UPDATE exr_migration_ledger SET data=x'7b7d' WHERE id=1")
                else:
                    title=db.execute('SELECT title FROM books LIMIT 1').fetchone()[0];db.execute("UPDATE books SET title='ABA intermediate'");db.commit();db.execute('UPDATE books SET title=?',(title,))
                db.commit()
            c.finish(kill=True);rc,r,_=d.recover(f)
            if changed:d.pending(f,rc,r);d.check('foreign ledger preserved',I.model(f['target'])['rows']['exr_migration_ledger'][0][2]==b'{}')
            else:d.check('ABA current parity accepted without historical inference',rc==0 and I.model(f['target'])['canonical']==prior['canonical'],r)
    def bounds(folder):
        f=d.fixture(folder/'large');f['pack'].write_bytes(b'x'*(64*MIB+1));rc,r,_=d.call(*d.args(f));d.check('64MiB stream cap before public mutation',rc!=0 and not f['target'].exists() and not f['root'].exists(),r)
        f=d.fixture(folder/'staging');c,ready=d.start(f,'private-finished-durable');image=d.image(f)
        with image.open('ab') as out:out.truncate(64*MIB+1)
        c.go(ready);rc=c.finish();d.pending(f,rc,c.report());d.check('oversized physical private image retained',not f['target'].exists())
    def capacity(folder):
        for mode in ('names','bytes'):
            f=d.fixture(folder/mode);c,ready=d.start(f,'sealed-before-publish')
            if mode=='names':
                for i in range(100):(f['root']/('reserved-%03d'%i)).write_bytes(b'');(f['root']/('reserved-%03d'%i)).chmod(0o600)
            else:
                p=f['root']/'reserved.bin'
                with p.open('wb') as out:out.truncate(130*MIB)
                p.chmod(0o600)
            c.go(ready);rc=c.finish();d.pending(f,rc,c.report());d.check('future actual C capacity is required before public rename',not f['target'].exists())
    def entries(folder):
        f=d.fixture(folder);c,ready=d.start(f,'sealed-before-publish');c.finish(kill=True);original=I.inventory(f['root'])
        for command,extra in [('migrate',()),('migrate',('--break-lock',)),('recover-mirror',()),('dump',()),('verify',()),('export-ledger',('--output',str(folder/'output'))),('inspect',())]:
            rc,r,_=d.call(*d.args(f,command,extra=extra,create=False));d.check('pending creation guarded before SDK '+command,rc!=0 and not r['atomicity']['recovery']['target_sdk_open_attempted'],r)
        d.check('no alternate entrypoint consumes evidence',all(I.state(f['root']/p)==v for p,v in original.items()) and not f['target'].exists())
        rc,r,_=d.recover(f);d.created(f,rc,r)
    def standalone(folder):
        f=d.fixture(folder);rc,r,_=d.call(*d.args(f));before=d.created(f,rc,r)
        for command in ('dump','verify','export-ledger'):
            extra=('--output',str(folder/'export.bin')) if command=='export-ledger' else ()
            rc,r,_=d.call(*d.args(f,command,extra=extra,create=False));d.check('installed guarded '+command+' works',rc==0,r)
        f=d.fixture(folder/'mutated');c,ready=d.start(f,'private-finished-durable');image=d.image(f)
        with contextlib.closing(sqlite3.connect(image)) as db:db.execute("UPDATE books SET title='independent altered image'");db.commit()
        c.go(ready);rc=c.finish();d.pending(f,rc,c.report());d.check('independent image mutation rejected, not equal-bug serializer accepted',not f['target'].exists())
    tasks=[('01-minimal',simple),('02-full-known-partial',lambda f:simple(f,True)),('03-strict-partial',strict),('04-nine-formats-projection',formats),('05-fresh-C-later-writer',later),('06-preview-cancel',preview)]
    for name,phase in [('07-anchor','creation-anchor-durable'),('08-attempt','private-attempt-durable'),('09-private-interruption','private-owner-open'),('10-private-COMMIT','private-commit-before-exit'),('11-reaped-before-seal','private-finished-durable'),('12-sealed','sealed-before-publish'),('13-rename-before-sync','public-before-sync'),('14-sync-before-adopt','public-synced-before-adopt'),('15-mirror-before-sync','mirror-before-sync'),('16-ACK-final-return','create-ack-durable')]:tasks.append((name,lambda f,phase=phase:crash(f,phase)))
    tasks += [('17-foreign-no-overwrite',foreign_target),('18-symlink-sidecars',aliases),('19-hardlink-special',lambda f:aliases(f,True)),('20-foreign-image-inode',replace_image),('21-foreign-provenance',foreign_evidence),('22-parent-foreign-lock',foreign_lock),('23-real-private-WAL-refusal',wal),('24-live-private-reader',reader),('25-parent-kill-live-SDK-child',orphan),('26-spawn-gap',spawn_gap),('27-liveness-descriptor',descriptor),('28-transport-deadlines',transport),('29-orphan-seal-and-suffix-worker',suffix_orphan),('30-writer-before-parent-sync',lambda f:writer_after_visibility(f,'public-before-sync')),('31-writer-after-adopt',lambda f:writer_after_visibility(f,'mirror-before-sync')),('32-ABA-changed-ledger',aba),('33-stream-physical-bounds',bounds),('34-shared-capacity',capacity),('35-preSDK-entrypoints',entries),('36-installed-independent-oracle',standalone)]
    assert len(tasks)==36
    for name,fn in tasks:d.run(name,fn)
    d.evidence['expected_cases']=36;d.evidence['passed']=not d.report_exceeded and len(d.evidence['cases'])==36 and all(c['passed'] for c in d.evidence['cases']);d.save()
    print(str(sum(c['passed'] for c in d.evidence['cases']))+'/36 full_p0_acceptance=false',flush=True);return 0 if d.evidence['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
