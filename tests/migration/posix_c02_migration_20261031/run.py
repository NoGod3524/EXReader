#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only actual SDK owner, raw native evidence and deterministic cuts."""
import argparse, hashlib, json, os, pathlib, platform, pwd, re, select, shutil, signal, sqlite3, stat, struct, subprocess, sys, traceback
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import legacy_data as L
from repair_cases import RepairCases
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def identity(path):
    s=path.stat();return (s.st_dev,s.st_ino)
def text(raw,offset,size):return raw[offset:offset+size].split(b"\0",1)[0].decode("utf-8")
class Runner(RepairCases):
    def __init__(self,a):
        self.a=a;self.rows=[];self.repair_rows=[];self.serial=0;self.events={};self.sources=[];providers=set()
        self.authority=pathlib.Path(pwd.getpwuid(os.geteuid()).pw_dir).resolve()/".exreader-c02-admission"
        for tool in (a.tool,a.test_tool):
            v=self.call(a.output,tool,"--version")["stdout"].strip()
            m=re.fullmatch(r"exreader-c02-migrate ([0-9a-f]{40}) provider=([0-9a-f]{64}) SDK=3\.42\.0 synchronous-posix",v)
            assert m and m[1]==os.environ["GITHUB_SHA"],v
            providers.add(m[2])
        assert len(providers)==1
        self.provider=m[2]
    def call(self,folder,tool,*args,expected=(0,),env=None):
        self.serial+=1
        p=subprocess.Popen([str(tool),*map(str,args)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        timed_out=False
        try:stdout,stderr=p.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            timed_out=True;p.kill();stdout,stderr=p.communicate(timeout=10)
        row=dict(command=[str(tool),*map(str,args)],pid=p.pid,observer_pid=os.getpid(),observer_uid=os.getuid(),observer_euid=os.geteuid(),
                 exit=p.returncode,timed_out=timed_out,stdout=stdout.decode("utf-8","replace"),stderr=stderr.decode("utf-8","replace"))
        (folder/f"command-{self.serial:04}.json").write_text(json.dumps(row,indent=2)+"\n")
        if expected is not None:assert not timed_out and p.returncode in expected,row
        return row
    def fixture(self,name,seed=True,enroll=True,area="cases"):
        folder=self.a.output/area/name;folder.mkdir(parents=True,mode=0o700)
        target=folder/"library.sqlite";pack=folder/"input.exrpack";seedpack=folder/"seed.exrpack"
        books,notes=L.dataset()
        pack.write_bytes(L.build_pack(books[:1],[n for n in notes if n["bookId"]=="b-txt"]))
        if seed:
            seedpack.write_bytes(L.build_pack([L.entry(L.book_record("unrelated","original.txt",title="Untouched original"),L.TXT_OTHER)],
                 [L.note_record("untouched-note","unrelated","unique sentence about silver tides","original annotation")]))
            self.call(folder,self.a.legacy,"migrate","--pack",seedpack,"--target",target)
            if enroll:self.call(folder,self.a.admission,"enroll",target)
        else:
            assert enroll
            self.call(folder,self.a.admission,"create",target)
        for path in folder.iterdir():
            if path.is_file():os.chmod(path,0o600)
        return folder,target,pack,seedpack
    def route(self,target):
        parent=identity(target.parent);found=[]
        assert self.authority.is_dir()
        for route in self.authority.iterdir():
            if not route.is_dir() or not re.fullmatch("[0-9a-f]{64}",route.name):continue
            p=route/"binding"
            if p.exists():
                raw=p.read_bytes()
                if len(raw)==304 and raw[:8]==b"PC02B001" and struct.unpack_from("<QQ",raw,24)==parent:found.append(route)
        assert len(found)==1,(target,found)
        return found[0]
    def observe(self,path,artifact):
        entry=path.lstat()
        is_dir=stat.S_ISDIR(entry.st_mode)
        assert is_dir or stat.S_ISREG(entry.st_mode),("unexpected native object",path)
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|(os.O_DIRECTORY if is_dir else 0))
        data=b""
        try:
            before=os.fstat(fd)
            assert (before.st_dev,before.st_ino,before.st_mode)==(entry.st_dev,entry.st_ino,entry.st_mode)
            if not is_dir:
                blocks=[]
                while True:
                    chunk=os.read(fd,65536)
                    if not chunk:break
                    blocks.append(chunk)
                data=b"".join(blocks);assert len(data)==before.st_size
            after=os.fstat(fd);named=path.lstat()
            assert (before.st_dev,before.st_ino,before.st_size,before.st_mode,before.st_uid,before.st_nlink)==(after.st_dev,after.st_ino,after.st_size,after.st_mode,after.st_uid,after.st_nlink)
            assert (before.st_dev,before.st_ino)==(named.st_dev,named.st_ino)
        finally:os.close(fd)
        row=dict(source_path=str(path),artifact_path=artifact.relative_to(self.a.output).as_posix(),
             device=before.st_dev,inode=before.st_ino,uid=before.st_uid,gid=before.st_gid,links=before.st_nlink,
             mode=stat.S_IMODE(before.st_mode),raw_mode=before.st_mode,directory=is_dir,bytes=before.st_size,sha256=None)
        if not is_dir:
            row.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
            if artifact!=path:
                artifact.parent.mkdir(parents=True,exist_ok=True,mode=0o700);artifact.write_bytes(data);os.chmod(artifact,0o600)
        else:artifact.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.sources.append(row);return row
    def capture(self,folder,target,label):
        destination=folder/("native-authority-"+label);destination.mkdir(mode=0o700)
        root=dict(path=str(self.authority),device=self.authority.stat().st_dev,inode=self.authority.stat().st_ino,
                  uid=self.authority.stat().st_uid,mode=stat.S_IMODE(self.authority.stat().st_mode))
        (destination/"root-observation.json").write_text(json.dumps(root,indent=2)+"\n")
        self.observe(self.authority/"authority",destination/"authority")
        self.observe(self.authority,destination)
        self.observe(self.authority/"registry.lock",destination/"registry.lock")
        route=self.route(target)
        self.observe(route,destination/route.name)
        for p in sorted(route.rglob("*")):self.observe(p,destination/route.name/p.relative_to(route))
        custody=folder/("native-custody-"+label);custody.mkdir(mode=0o700)
        self.observe(target.parent,custody)
        for p in sorted(folder.iterdir()):
            if p.name.startswith(("native-","command-","process-")):continue
            if p.is_dir():
                self.observe(p,custody/p.name)
                for child in sorted(p.rglob("*")):self.observe(child,custody/p.name/child.relative_to(p))
            elif p.is_file():self.observe(p,custody/p.name)
        (folder/("native-observations-"+label+".json")).write_text(json.dumps(self.sources,indent=2)+"\n")
        return route
    def input(self,target):
        route=self.route(target);state=(route/"state").read_bytes()
        assert len(state)%368==0
        original=state[-368:]
        selected=original[96:160].decode("ascii")
        if original[8]==ord("I"):return None
        generation=struct.unpack_from("<Q",original,24)[0]
        meta=route/f"input-{generation:016x}-{selected}"
        raw=meta.read_bytes();payload=raw[568:-64]
        assert raw[:8]==b"PC02M001" and len(payload)==13844 and payload[:8]==b"PC02IN01"
        assert hashlib.sha256(raw[:-64]).hexdigest().encode()==raw[-64:]
        assert hashlib.sha256(payload).hexdigest()==selected
        begin=state[(generation*2-1)*368:generation*2*368]
        assert len(begin)==368 and begin[8]==ord("B")
        return dict(route=route,metadata_path=meta,raw=raw,payload=payload,selected=selected,generation=generation,
              pending_seal=begin[304:368],manifest=begin[32:96],
              journal=target.parent/text(payload,13222,64),token=text(payload,12917,49),
              original=dict(identity=struct.unpack_from("<QQ",payload,13350),size=struct.unpack_from("<Q",payload,13366)[0],
                            sha=text(payload,13374,65)),
              retained=[target.parent/text(payload,13094+64*k,64) for k in range(2)],
              stages=[target.parent/text(payload,12966+64*k,64) for k in range(2)])
    def ack(self,desc):
        result=[]
        for p in sorted(desc["journal"].glob("ack-*")):
            raw=p.read_bytes()
            assert re.fullmatch("ack-[0-9]{3}",p.name) and raw[:8]==b"PC02ACK1"
            ordinal=struct.unpack_from("<Q",raw,24)[0];n=struct.unpack_from("<Q",raw,224)[0]
            assert len(raw)==296+n+64 and identity(p)==struct.unpack_from("<QQ",raw,8)
            assert raw[96:160].decode()==desc["selected"] and raw[160:224]==desc["pending_seal"] and raw[32:96]==desc["manifest"]
            assert hashlib.sha256(raw[:-64]).hexdigest().encode()==raw[-64:]
            line=raw[296:-64]
            assert hashlib.sha256(line).hexdigest().encode()==raw[232:296]
            m=re.match(rb"EXRWH2 ([0-9]+) ([0-9]+) ",line)
            result.append(dict(path=p,ordinal=ordinal,line=line,event=int(m[2]) if m else 0,sha=sha(p),identity=identity(p)))
        assert [r["ordinal"] for r in result]==list(range(1,len(result)+1))
        return result
    def native_reader_expected(self,route,target):
        raw=(route/"state").read_bytes();binding=(route/"binding").read_bytes()
        if not raw or len(raw)%368:return False
        last=raw[-368:]
        return last[8] in (ord("I"),ord("C")) and last[24:32]==binding[88:96] and last[304:368]==binding[96:160] and target.exists() and identity(target)==struct.unpack_from("<QQ",binding,40)
    def logical(self,target):
        db=sqlite3.connect(target.as_uri()+"?mode=ro&immutable=1",uri=True)
        try:
            books=db.execute("SELECT id,title,source FROM books ORDER BY id").fetchall()
            notes=db.execute("SELECT id,book_id,start,end,text,anchor_exact FROM notes ORDER BY id").fetchall()
            return dict(books=[(r[0],r[1],hashlib.sha256(r[2]).hexdigest()) for r in books],notes=notes)
        finally:db.close()
    def independent(self,target):
        raw=pathlib.Path(str(target)+".legacy-map.json").read_bytes();ledger=json.loads(raw)
        book=next(b for b in ledger["books"] if b["legacy_id"]=="b-txt")
        note=next(n for n in ledger["notes"] if n["legacy_id"]=="n-txt-unique")
        ambiguous=next(n for n in ledger["notes"] if n["legacy_id"]=="n-txt-ambiguous")
        db=sqlite3.connect(target.as_uri()+"?mode=ro&immutable=1",uri=True)
        try:
            internal=db.execute("SELECT id,data FROM exr_migration_ledger").fetchall()
            assert len(internal)==1 and internal[0][0]==1 and bytes(internal[0][1])==raw
            source=db.execute("SELECT source FROM books WHERE id=?",(book["book_id"],)).fetchone()
            assert source and bytes(source[0])==L.TXT
            actual=db.execute("SELECT book_id,start,end,text,anchor_exact FROM notes WHERE id=?",(note["new_id"],)).fetchone()
            assert note["located"] and actual==(book["book_id"],note["start"],note["end"],"keep this","unique sentence about silver tides"),(actual,note)
            assert not ambiguous["located"] and ambiguous["new_id"] is None
            assert db.execute("SELECT count(*) FROM notes WHERE book_id=? AND text='appears twice'",(book["book_id"],)).fetchone()[0]==0
            return dict(ledger_sha=hashlib.sha256(raw).hexdigest(),source_sha=hashlib.sha256(source[0]).hexdigest(),
                        note_id=note["new_id"],start=actual[1],end=actual[2],text=actual[3],anchor=actual[4],ambiguous_absent=True)
        finally:db.close()
    def original_retained(self,desc):
        old=desc["retained"][0]
        assert old.exists() and identity(old)==desc["original"]["identity"] and sha(old)==desc["original"]["sha"]
        assert old.stat().st_size==desc["original"]["size"]
    def journal_bound(self,desc):
        records=self.ack(desc);previous_line=b"0"*64;previous_floor=b"0"*64
        assert records
        assert identity(desc["metadata_path"])==struct.unpack_from("<QQ",desc["raw"],32)
        head=desc["route"]/f"commit-head-{desc['generation']:016x}-{desc['selected']}"
        raw_head=head.read_bytes()
        assert len(raw_head)==464+272*len(records) and raw_head[:8]==b"PC02F001"
        assert identity(head)==struct.unpack_from("<QQ",raw_head,384)==struct.unpack_from("<QQ",desc["raw"],552)
        assert hashlib.sha256(raw_head[:400]).hexdigest().encode()==raw_head[400:464]
        previous_head=raw_head[400:464]
        for k,ack in enumerate(records,1):
            floor=desc["route"]/f"floor-{desc['generation']:016x}-{k:03}"
            raw=floor.read_bytes();data=raw[568:-64]
            assert raw[:8]==b"PC02M001" and len(data)==352 and struct.unpack_from("<Q",raw,8)[0]==3
            assert hashlib.sha256(raw[:-64]).hexdigest().encode()==raw[-64:] and identity(floor)==struct.unpack_from("<QQ",raw,32)
            assert data[208:272]==desc["manifest"] and struct.unpack_from("<Q",data,0)[0]==k-1 and data[8:72]==previous_line and data[72:136]==previous_floor
            assert struct.unpack_from("<Q",data,136)[0]==k and struct.unpack_from("<QQ",data,272)==ack["identity"] and data[288:352].decode()==ack["sha"]
            line=hashlib.sha256(ack["line"]).hexdigest().encode();assert data[144:208]==line
            h=raw_head[464+(k-1)*272:464+k*272]
            assert h[:8]==b"PC02H001" and struct.unpack_from("<Q",h,8)[0]==k and h[16:80]==line and h[80:144].decode()==sha(floor)
            assert h[144:208]==previous_head and hashlib.sha256(h[:208]).hexdigest().encode()==h[208:272]
            previous_head=h[208:272];previous_line=line;previous_floor=sha(floor).encode()
        return dict(ack_count=len(records),floor_bytes=352,ack_header_bytes=296,all_native_ids_and_raw_hashes=True)
    def normal(self,seed=True):
        folder,target,pack,seedpack=self.fixture("actual-full-seed-and-next-generation" if seed else "actual-absent-mirror",seed=seed)
        before=self.logical(target);raw_before=sha(target);id_before=identity(target)
        if seed:
            books,notes=L.dataset();pack.write_bytes(L.build_pack(books,notes))
        result=self.call(folder,self.a.tool,"migrate",target,pack,"--allow-partial")
        assert '"status":"completed"' in result["stdout"],result
        desc=self.input(target);acks=self.ack(desc);self.original_retained(desc)
        assert desc["original"]["identity"]==id_before and desc["original"]["sha"]==raw_before
        for record in acks:
            if seed and record["event"]:self.events[record["event"]]=record["ordinal"]
        self.call(folder,self.a.tool,"verify",target,pack)
        self.call(folder,self.a.admission,"check",target)
        if seed:self.call(folder,self.a.guarded,"verify","--pack",seedpack,"--target",target)
        after=self.logical(target)
        assert all(row in after["books"] for row in before["books"]) and all(row in after["notes"] for row in before["notes"])
        facts=self.independent(target)
        first_generation=desc["generation"];self.journal_bound(desc);self.capture(folder,target,"generation-1")
        self.call(folder,self.a.tool,"migrate",target,pack,"--allow-partial")
        second=self.input(target);self.original_retained(second)
        assert second["generation"]==first_generation+1 and self.logical(target)==after
        self.journal_bound(second)
        self.call(folder,self.a.tool,"verify",target,pack);self.capture(folder,target,"generation-2")
        return dict(actual_sdk=True,synchronous_owner=True,imported=True,generations=2,original_source_and_annotations_preserved=True,
                    input_sha=second["selected"],journal_count=len(self.ack(second)),independent=facts)
    def unregistered(self):
        folder,target,pack,_=self.fixture("unregistered-never-auto-adopted",enroll=False)
        before=sha(target)
        self.call(folder,self.a.tool,"migrate",target,pack,expected=(2,))
        self.call(folder,self.a.guarded,"dump","--target",target,expected=(2,))
        assert sha(target)==before
        self.call(folder,self.a.admission,"enroll",target)
        self.call(folder,self.a.tool,"migrate",target,pack)
        self.call(folder,self.a.tool,"verify",target,pack);self.capture(folder,target,"final")
        return dict(actual_sdk=True,unknown_refused=True,explicit_enroll=True)
    def guard(self):
        folder,target,pack,_=self.fixture("all-old-write-commands-disabled")
        before=sha(target);mirror=sha(pathlib.Path(str(target)+".legacy-map.json"))
        for name in ("exreader-legacy-migrate","exreader-legacy-migrate-tx","exreader-legacy-migrate-recovery"):
            tool=self.a.guarded.parent/name
            for command in ("migrate","recover-mirror","recover-migration"):
                result=self.call(folder,tool,command,"--target",target,"--pack",pack,"--break-lock",expected=(2,))
                assert "c02-owner-required" in result["stdout"],result
            self.call(folder,tool,"dump","--target",target,"--report",target,expected=(2,))
        assert sha(target)==before and sha(pathlib.Path(str(target)+".legacy-map.json"))==mirror
        self.call(folder,self.a.guarded,"dump","--target",target);self.capture(folder,target,"final")
        return dict(actual_sdk=True,legacy_mutation_refused_before_lock=True,all_three_entrypoints=True)
    def paused(self,folder,target,pack,phase,sequence=None,member=None,require_cap=False,command=None,label="paused"):
        ready_r,ready_w=os.pipe();go_r,go_w=os.pipe();env=dict(os.environ)
        env.update(EXR_PC02_PHASE=str(phase),EXR_PC02_READY_FD=str(ready_w),EXR_PC02_GO_FD=str(go_r))
        if sequence is not None:env["EXR_PC02_SEQUENCE"]=str(sequence)
        if member is not None:env["EXR_PC02_MEMBER"]=str(member)
        if require_cap:env["EXR_PC02_REQUIRE_CAP"]="1"
        prefix="process" if label=="paused" else "process-"+label
        out=open(folder/(prefix+".stdout"),"wb");err=open(folder/(prefix+".stderr"),"wb")
        arguments=["migrate",str(target),str(pack)] if command is None else list(map(str,command))
        actual_command=[str(self.a.test_tool),*arguments]
        p=subprocess.Popen(actual_command,stdout=out,stderr=err,env=env,pass_fds=(ready_w,go_r))
        os.close(ready_w);os.close(go_r)
        observation=dict(command=actual_command,owner_pid=p.pid,observer_pid=os.getpid(),observer_uid=os.getuid(),observer_euid=os.geteuid(),phase=phase,sequence=sequence,member=member,require_cap=require_cap,ready_hex="",kill_signal=None)
        try:
            events=select.select([ready_r],[],[],60)[0]
            raw_ready=os.read(ready_r,1) if events else b""
            observation["ready_hex"]=raw_ready.hex()
            assert events and raw_ready==b"r",("barrier not reached",phase,p.poll())
            ps_command=["ps","-axo","pid=,ppid=,uid="]
            children=subprocess.run(ps_command,capture_output=True,text=True,check=True)
            observation.update(ps_command=ps_command,ps_stdout=children.stdout,ps_stderr=children.stderr,ps_exit=children.returncode)
            process_rows=[list(map(int,line.split())) for line in children.stdout.splitlines() if len(line.split())==3]
            owner=[row for row in process_rows if row[0]==p.pid]
            assert len(owner)==1 and owner[0][1]==os.getpid() and owner[0][2]==os.geteuid(),owner
            observation["owner_uid"]=owner[0][2]
            assert not [row for row in process_rows if row[1]==p.pid],"synchronous owner spawned a child"
            self.call(folder,self.a.admission,"check",target,expected=(2,))
            self.capture(folder,target,label)
            observation["kill_signal"]=int(signal.SIGKILL)
            os.kill(p.pid,signal.SIGKILL);observation["wait_returncode"]=p.wait(timeout=10)
            assert observation["wait_returncode"]==-signal.SIGKILL
        finally:
            if p.poll() is None:p.kill();p.wait(timeout=10)
            os.close(ready_r);os.close(go_w);out.close();err.close()
            observation["final_returncode"]=p.returncode
            observation["barrier_stdout"]=(folder/(prefix+".stdout")).read_text(errors="replace")
            (folder/(prefix+"-observation.json")).write_text(json.dumps(observation,indent=2)+"\n")
        return observation
    def cut(self,phase,sequence=None,member=None,require_cap=False):
        name=f"process-kill-{phase}-"+("any" if sequence is None else str(sequence))+("-m"+str(member) if member is not None else "")
        folder,target,pack,seedpack=self.fixture(name)
        before=sha(target);baseline=self.logical(target)
        process=self.paused(folder,target,pack,phase,sequence,member,require_cap)
        route=self.route(target);expected=self.native_reader_expected(route,target)
        self.call(folder,self.a.admission,"check",target,expected=(0,) if expected else (2,))
        desc=self.input(target);acks=self.ack(desc) if desc else []
        committed=any(r["event"]==9 for r in acks)
        fresh=self.call(folder,self.a.tool,"recover",target)
        assert fresh["pid"]!=process["owner_pid"]
        self.call(folder,self.a.admission,"check",target)
        self.call(folder,self.a.guarded,"verify","--pack",seedpack,"--target",target)
        logical=self.logical(target)
        assert all(row in logical["books"] for row in baseline["books"]) and all(row in logical["notes"] for row in baseline["notes"])
        if committed:
            self.call(folder,self.a.tool,"verify",target,pack);facts=self.independent(target);self.original_retained(desc)
            self.journal_bound(self.input(target))
        else:
            assert sha(target)==before
            self.call(folder,self.a.tool,"verify",target,pack,expected=(2,));facts=dict(original_unchanged=True)
        if desc:self.journal_bound(self.input(target))
        self.capture(folder,target,"final")
        return dict(actual_sdk=True,synchronous_owner=True,process_kill=True,phase=phase,sequence=sequence,member=member,
                    original_source_and_annotations_preserved=True,published=committed,full_ack_count=len(acks),independent=facts)
    def bad_ack(self,kind):
        name="actual-ACK-refuse-"+kind;folder,target,pack,_=self.fixture(name)
        ordinal=self.events[9] if kind=="old-valid-tip" else 2
        self.paused(folder,target,pack,1605,ordinal)
        desc=self.input(target);records=self.ack(desc);assert len(records)==ordinal
        selected=records[-1]["path"] if kind in ("old-valid-tip","same-bytes-new-ID") else records[0]["path"]
        old_id=identity(selected);raw=selected.read_bytes()
        retained=folder/("retained-original-"+selected.name);selected.rename(retained)
        if kind=="same-bytes-new-ID":
            selected.write_bytes(raw);os.chmod(selected,0o600);assert identity(selected)!=old_id
        elif kind=="wrong-input-tuple":
            value=bytearray(raw);value[96]=ord("a") if value[96]!=ord("a") else ord("b")
            value[-64:]=hashlib.sha256(value[:-64]).hexdigest().encode();selected.write_bytes(value);os.chmod(selected,0o600)
        elif kind not in ("hole","old-valid-tip"):raise AssertionError(kind)
        before={str(p):sha(p) for p in folder.rglob("*") if p.is_file() and not p.name.startswith(("command-","native-observations-"))}
        self.call(folder,self.a.tool,"recover",target,expected=(2,))
        self.call(folder,self.a.admission,"check",target,expected=(2,))
        assert all(p.is_file() and sha(p)==value for path,value in before.items() for p in [pathlib.Path(path)])
        self.capture(folder,target,"refused")
        return dict(actual_sdk=True,process_kill=True,complete_contradiction_refused=True,no_source_modification=True,kind=kind)
    def run(self,name,callback):
        try:detail=callback();row=dict(name=name,passed=True,detail=detail)
        except Exception:row=dict(name=name,passed=False,error=traceback.format_exc())
        self.rows.append(row);print(json.dumps(row),flush=True);self.save()
    def save(self):
        value=dict(source=os.environ["GITHUB_SHA"],run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],
             provider=self.provider,platform=platform.platform(),process_uid=os.getuid(),process_euid=os.geteuid(),actual_sdk=True,synchronous_owner=True,workers=False,power_loss=False,
             partial_state_head_repair=False,cases=len(self.rows),failed=sum(not r["passed"] for r in self.rows),results=self.rows,
             binaries={role:dict(path=str(getattr(self.a,role)),bytes=getattr(self.a,role).stat().st_size,sha256=sha(getattr(self.a,role)),mode=stat.S_IMODE(getattr(self.a,role).stat().st_mode)) for role in ("tool","test_tool","admission","legacy","guarded")})
        (self.a.output/"migration-result.json").write_text(json.dumps(value,indent=2)+"\n")
        (self.a.output/"native-source-observations.json").write_text(json.dumps(self.sources,indent=2)+"\n")
        self.repair_save()
def main():
    ap=argparse.ArgumentParser()
    for name in ("tool","test-tool","admission","legacy","guarded","output"):ap.add_argument("--"+name,type=pathlib.Path,required=True)
    a=ap.parse_args()
    assert os.environ.get("GITHUB_ACTIONS")=="true" and os.name=="posix","Actions-only actual fixtures"
    for name in ("tool","test_tool","admission","legacy","guarded"):setattr(a,name,getattr(a,name).resolve(strict=True))
    a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True,mode=0o700)
    runner=Runner(a)
    runner.run("actual-full-seed-and-next-generation",lambda:runner.normal(True))
    runner.run("actual-absent-mirror",lambda:runner.normal(False))
    runner.run("unregistered-never-auto-adopted",runner.unregistered)
    runner.run("all-old-write-commands-disabled",runner.guard)
    for phase in (900,901,902,903,904,905,906,907,908,1101,1102,1201,1202,1203,1204,1205,1601,1602,1603,1604):
        runner.run("process-kill-"+str(phase),lambda phase=phase:runner.cut(phase))
    for member in (0,1):
        for phase in (1301,1302):
            runner.run(f"process-kill-{phase}-member-{member}",lambda phase=phase,member=member:runner.cut(phase,member=member))
    runner.run("complete-FLOOR-before-head",lambda:runner.cut(1402,0,require_cap=True))
    runner.run("complete-head-before-fsync",lambda:runner.cut(1501,0))
    if 9 in runner.events:
        n=runner.events[9]
        runner.run("uncommitted-publish-intent-temp-never-promoted",lambda:runner.cut(1602,n-1))
        runner.run("complete-publish-intent-ACK-counted-before-floor",lambda:runner.cut(1603,n-1))
        for kind in ("same-bytes-new-ID","wrong-input-tuple","hole","old-valid-tip"):
            runner.run("actual-ACK-refuse-"+kind,lambda kind=kind:runner.bad_ack(kind))
    else:runner.run("published-event-observed",lambda:(_ for _ in ()).throw(AssertionError("no canonical published history")))
    runner.repair_all()
    inventory=[]
    for p in sorted(a.output.rglob("*")):
        s=p.lstat();row=dict(path=p.relative_to(a.output).as_posix(),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,gid=s.st_gid,
                           links=s.st_nlink,mode=stat.S_IMODE(s.st_mode))
        if stat.S_ISREG(s.st_mode):row.update(bytes=s.st_size,sha256=sha(p))
        inventory.append(row)
    (a.output/"file-hashes.json").write_text(json.dumps(inventory,indent=2)+"\n")
    runner.save();assert len(runner.rows)==36,len(runner.rows)
    assert all(r["passed"] for r in runner.rows),[r["name"] for r in runner.rows if not r["passed"]]
    assert len(runner.repair_rows)==17 and all(r["passed"] for r in runner.repair_rows),[r["name"] for r in runner.repair_rows if not r["passed"]]
    print("POSIX-C02-ACTUAL cases=36 repair_cases=17 failed=0")
    return 0
if __name__=="__main__":sys.exit(main())
