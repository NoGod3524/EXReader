#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual installed migration command, native barriers and fresh-process recovery.
All fixture creation and execution is confined to GitHub Actions.
"""
import argparse, ctypes, hashlib, json, os, pathlib, re, sqlite3, struct, subprocess, sys, traceback, uuid, winreg
from ctypes import wintypes
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import legacy_data as L
K=ctypes.WinDLL("kernel32",use_last_error=True)
K.CreateEventW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.BOOL,wintypes.LPCWSTR]
K.CreateEventW.restype=wintypes.HANDLE
K.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
K.WaitForSingleObject.restype=wintypes.DWORD
K.CloseHandle.argtypes=[wintypes.HANDLE]
K.CloseHandle.restype=wintypes.BOOL

class Runner:
    def __init__(self,args):
        self.a=args;self.rows=[];self.serial=0;self.versions={}
        for tool in (args.tool,args.test_tool):
            result=self.call(args.output,tool,"--version")
            match=re.fullmatch(r"exreader-c02-migrate ([0-9a-f]{40}) provider=([0-9a-f]{64}) SDK=3\.42\.0",result["stdout"].strip())
            assert match and match[1]==os.environ["GITHUB_SHA"],result
            self.versions[tool.name]=dict(source=match[1],provider=match[2])
        assert len({r["provider"] for r in self.versions.values()})==1
    def call(self,folder,tool,*args,success=True,env=None):
        self.serial+=1
        run=subprocess.run([str(tool),*map(str,args)],capture_output=True,timeout=120,env=env)
        record=dict(command=[str(tool),*map(str,args)],exit=run.returncode,
                    stdout=run.stdout.decode("utf-8","replace"),stderr=run.stderr.decode("utf-8","replace"))
        (folder/f"command-{self.serial:03}.json").write_text(json.dumps(record,indent=2)+"\n",encoding="utf-8")
        if success is not None:
            assert (run.returncode==0)==success,record
        if success is False:
            assert run.returncode==2,record
            if pathlib.Path(tool)==self.a.admission:
                assert json.loads(record["stdout"])["admitted"] is False,record
            elif pathlib.Path(tool)==self.a.tool:
                assert "C02 refused or pending;" in record["stderr"],record
        return record
    def fixture(self,name,seed=False,long_root=False):
        folder=self.a.output/"cases"/name;folder.mkdir(parents=True);self.active_folder=folder
        target=folder/"library.sqlite";pack=folder/"input.exrpack";root=folder/"domain"
        if long_root:
            root=folder/("r"*(225-len(str(folder))-1));assert len(str(root))==225
        books,notes=L.dataset()
        pack.write_bytes(L.build_pack(books[:1],[n for n in notes if n["bookId"]=="b-txt"]))
        if seed:
            seedpack=folder/"seed.exrpack"
            seedpack.write_bytes(L.build_pack([L.entry(L.book_record("unrelated","original.txt",title="Untouched original"),L.TXT_OTHER)],[]))
            self.call(folder,self.a.legacy,"migrate","--pack",seedpack,"--target",target)
            self.call(folder,self.a.admission,"enroll",target,root)
        else:self.call(folder,self.a.admission,"create",target,root)
        return folder,target,pack,root
    def run(self,name,fn):
        try:
            detail=fn();detail["evidence_dir"]=self.active_folder.name
            if detail.get("repair_phase") is not None:
                detail["origin_phase"]=detail.get("phase");detail["origin_sequence"]=detail.get("sequence")
            row=dict(name=name,passed=True,detail=detail)
        except Exception:
            row=dict(name=name,passed=False,error=traceback.format_exc())
        self.rows.append(row)
        print(json.dumps(row),flush=True)
        self.save()
    def save(self):
        receipt=dict(source=os.environ["GITHUB_SHA"],run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],
                     actual_importer=True,synchronous_owner=True,power_loss=False,versions=self.versions,cases=len(self.rows),
                     failed=sum(not r["passed"] for r in self.rows),results=self.rows,
                     binaries={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in [self.a.tool,self.a.test_tool,self.a.admission]})
        (self.a.output/"migration-result.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    def contents(self,target):
        connection=sqlite3.connect(target.as_uri()+"?mode=ro",uri=True)
        try:
            rows=connection.execute("SELECT id,title,source FROM books ORDER BY id").fetchall()
            return [dict(id=r[0],title=r[1],sha=hashlib.sha256(r[2]).hexdigest()) for r in rows]
        finally:connection.close()
    def independent_sqlite(self,target):
        raw=pathlib.Path(str(target)+".legacy-map.json").read_bytes();data=json.loads(raw)
        book=next(b for b in data["books"] if b["legacy_id"]=="b-txt")
        note=next(n for n in data["notes"] if n["legacy_id"]=="n-txt-unique")
        ambiguous=next(n for n in data["notes"] if n["legacy_id"]=="n-txt-ambiguous")
        db=sqlite3.connect(target.as_uri()+"?mode=ro",uri=True)
        try:
            internal=db.execute("SELECT id,data FROM exr_migration_ledger").fetchall()
            assert len(internal)==1 and internal[0][0]==1 and bytes(internal[0][1])==raw
            source=db.execute("SELECT source FROM books WHERE id=?",(book["book_id"],)).fetchone()
            assert source and bytes(source[0])==L.TXT
            actual=db.execute("SELECT book_id,start,end,text,anchor_exact FROM notes WHERE id=?",(note["new_id"],)).fetchone()
            assert note["located"] and actual==(book["book_id"],note["start"],note["end"],"keep this","unique sentence about silver tides"),(actual,note)
            assert not ambiguous["located"] and ambiguous["new_id"] is None
            assert db.execute("SELECT count(*) FROM notes WHERE book_id=? AND text='appears twice'",(book["book_id"],)).fetchone()[0]==0
            return dict(ledger_sha=hashlib.sha256(raw).hexdigest(),book_id=book["book_id"],source_sha=hashlib.sha256(source[0]).hexdigest(),note_id=note["new_id"],start=actual[1],end=actual[2],text=actual[3],anchor=actual[4],ambiguous_absent=True)
        finally:db.close()
    def input_binding(self,folder,target,producer):
        matches=[]
        base=winreg.OpenKey(winreg.HKEY_CURRENT_USER,r"Software\EXReaderC02Admission")
        try:
            index=0
            while True:
                try:name=winreg.EnumKey(base,index);index+=1
                except OSError:break
                try:
                    with winreg.OpenKey(base,name) as key:
                        binding,kind=winreg.QueryValueEx(key,"Binding")
                        if kind!=winreg.REG_BINARY or len(binding)!=1352 or binding[:8]!=b"WH3REG01":continue
                        library=binding[248:768].decode("utf-16le").split("\0",1)[0]
                        if library.casefold()!=str(target).casefold():continue
                        domain=binding[8:56].decode("ascii")
                        raw,kind=winreg.QueryValueEx(key,"Transaction-"+domain)
                        assert kind==winreg.REG_BINARY and raw[:8]==b"WH3TXN01"
                        assert hashlib.sha256(raw[:-64]).hexdigest().encode()==raw[-64:]
                        assert struct.unpack_from("<Q",raw,8)[0]==1
                        size=struct.unpack_from("<Q",raw,16)[0];payload=raw[1376:-64]
                        assert size==len(payload)==2577
                        assert payload[:8]==b"C02IN001"
                        text=lambda start,end:payload[start:end].split(b"\0",1)[0].decode("ascii")
                        assert text(8,49)==os.environ["GITHUB_SHA"]
                        assert text(49,70)==os.environ["GITHUB_RUN_ID"]
                        assert text(70,78)==os.environ["GITHUB_RUN_ATTEMPT"]
                        assert text(78,143)==sha(producer)
                        assert text(239,304)==self.versions[producer.name]["provider"]
                        (folder/("native-input-"+domain+".bin")).write_bytes(raw)
                        matches.append(dict(domain=domain,artifact=text(78,143),provider=text(239,304)))
                except FileNotFoundError:continue
        finally:winreg.CloseKey(base)
        assert len(matches)==1,matches
        return matches[0]
    def normal(self):
        folder,target,pack,root=self.fixture("actual-import-and-second-epoch",seed=True)
        baseline=self.contents(target);before=sha(target);old_mirror=sha(pathlib.Path(str(target)+".legacy-map.json"))
        books,notes=L.dataset();pack.write_bytes(L.build_pack(books,notes))
        first=self.call(folder,self.a.tool,"migrate",target,pack,"--allow-partial")
        assert '"status":"completed"' in first["stdout"],first
        self.input_binding(folder,target,self.a.tool)
        self.call(folder,self.a.tool,"verify",target,pack)
        self.call(folder,self.a.admission,"check",target)
        after=self.contents(target);independent_first=self.independent_sqlite(target)
        assert all(row in after for row in baseline)
        assert len(after)==len(baseline)+4,(baseline,after)
        assert any(sha(p)==before for p in folder.glob("*-0.retained"))
        assert any(sha(p)==old_mirror for p in folder.glob("*-1.retained"))
        ledger=pathlib.Path(str(target)+".legacy-map.json").read_bytes()
        data=json.loads(ledger)
        assert any(n["legacy_id"]=="n-txt-unique" and n["located"] for n in data["notes"])
        assert any(n["legacy_id"]=="n-txt-ambiguous" and not n["located"] for n in data["notes"])
        old_native={p.name:sha(p) for p in root.iterdir()}
        self.call(folder,self.a.admission,"next-epoch",target)
        second=self.call(folder,self.a.tool,"migrate",target,pack,"--allow-partial")
        assert '"status":"completed"' in second["stdout"],second
        self.call(folder,self.a.tool,"verify",target,pack)
        assert after==self.contents(target)
        assert ledger==pathlib.Path(str(target)+".legacy-map.json").read_bytes()
        assert old_native=={p.name:sha(p) for p in root.iterdir()}
        return dict(before=before,after=sha(target),baseline=baseline,final=after,old_native=old_native,
                    independent_first=independent_first,independent_second=self.independent_sqlite(target))
    def gate_fault(self,phase):
        folder,target,pack,root=self.fixture(f"gate-short-{phase}")
        before=sha(target)
        failed=self.call(folder,self.a.test_tool,"migrate",target,pack,success=False,
                         env=dict(os.environ,EXR_C02_GATE_SHORT=str(phase)))
        self.input_binding(folder,target,self.a.test_tool)
        raw={p.name:sha(p) for p in root.glob("*.bin")}
        assert (root/"admission.bin").stat().st_size==(687 if phase==201 else 1031)
        self.call(folder,self.a.admission,"check",target,success=False)
        self.call(folder,self.a.tool,"recover",target)
        self.call(folder,self.a.admission,"check",target)
        archives={p.name:sha(p) for p in root.glob("repair-*.raw")}
        for digest in raw.values():assert digest in archives.values()
        if phase==203:
            self.call(folder,self.a.tool,"verify",target,pack)
            independent=self.independent_sqlite(target)
        else:
            assert sha(target)==before
            independent=None
        return dict(gate_fault=phase,exit=failed["exit"],published=phase==203,raw_before=raw,
                    archives=archives,original=before,recovered=sha(target),independent=independent)
    def strict_abort(self):
        folder,target,pack,root=self.fixture("strict-policy-abort")
        before=sha(target);pack.write_bytes(L.build_pack([L.entry(L.book_record("unsupported","data.xyz"),b"unsupported")],[]))
        result=self.call(folder,self.a.tool,"migrate",target,pack,success=None)
        assert result["exit"]==3 and '"status":"rolled_back"' in result["stdout"],result
        assert sha(target)==before and not pathlib.Path(str(target)+".legacy-map.json").exists()
        self.call(folder,self.a.admission,"check",target)
        return dict(original=before,result=result["exit"],retained_private=len(list(folder.glob("*.stage"))))
    def floor_tamper(self):
        folder,target,pack,root=self.fixture("repair-ack-floor")
        owner_exit=self.crash(folder,["migrate",target,pack],7,sequence=9)
        self.input_binding(folder,target,self.a.test_tool)
        repair_exit=self.crash(folder,["recover",target],954,log_name="repair-owner.log")
        paths=[root/"journal.bin",root/"intent.bin"];ids=[p.stat().st_ino for p in paths]
        data=paths[0].read_bytes();at=0
        for _ in range(5):
            size=struct.unpack_from("<I",data,at)[0];assert 0<size<2048;at+=4+size
        assert at<len(data)
        for path,keep in zip(paths,(at,5*848)):
            with path.open("r+b") as stream:stream.truncate(keep)
        assert ids==[p.stat().st_ino for p in paths]
        reverted={p.name:sha(p) for p in root.glob("*.bin")}
        self.call(folder,self.a.tool,"recover",target,success=False)
        self.call(folder,self.a.admission,"check",target,success=False)
        assert reverted=={p.name:sha(p) for p in root.glob("*.bin")}
        return dict(phase=7,sequence=9,member=0,repair_phase=954,tamper="ack-floor",
                    owner_exit=owner_exit,repair_owner_exit=repair_exit,remains_pending=True,
                    reverted=reverted,kept_acks=5,protected_acks=9,native_inodes=ids)
    def archive_tamper(self,kind):
        folder,target,pack,root=self.fixture("repair-archive-"+kind)
        owner_exit=self.crash(folder,["migrate",target,pack],7,sequence=0)
        self.input_binding(folder,target,self.a.test_tool)
        raw={p.name:sha(p) for p in root.glob("*.bin")}
        repair_exit=self.crash(folder,["recover",target],950,log_name="repair-owner.log")
        archive=next(root.glob("repair-*-1.raw"))
        prior=dict(dev=archive.stat().st_dev,ino=archive.stat().st_ino,sha=sha(archive))
        if kind=="bytes":
            with archive.open("ab") as stream:stream.write(b"FOREIGN")
        else:
            data=archive.read_bytes();archive.rename(archive.with_suffix(".foreign-original"));archive.write_bytes(data)
        after=dict(dev=archive.stat().st_dev,ino=archive.stat().st_ino,sha=sha(archive))
        if kind=="identity":assert prior["ino"]!=after["ino"] and prior["sha"]==after["sha"]
        self.call(folder,self.a.tool,"recover",target,success=False)
        self.call(folder,self.a.admission,"check",target,success=False)
        assert raw=={p.name:sha(p) for p in root.glob("*.bin")}
        return dict(phase=7,sequence=0,member=0,repair_phase=950,tamper="archive-"+kind,
                    owner_exit=owner_exit,repair_owner_exit=repair_exit,remains_pending=True,
                    raw_before=raw,prior_stage=prior,after_stage=after)
    def crash(self,folder,command,phase,member=0,sequence=None,log_name="killed-owner.log"):
        ready_name="Local\\c02-ready-"+uuid.uuid4().hex;resume_name="Local\\c02-resume-"+uuid.uuid4().hex
        ready=K.CreateEventW(None,True,False,ready_name);resume=K.CreateEventW(None,True,False,resume_name)
        assert ready and resume
        env=dict(os.environ,EXR_C02_PHASE=str(phase),EXR_C02_MEMBER=str(member),EXR_C02_READY=ready_name,EXR_C02_RESUME=resume_name)
        if sequence is not None:env["EXR_C02_SEQUENCE"]=str(sequence)
        log=folder/log_name
        try:
            with log.open("wb") as out:
                child=subprocess.Popen([str(self.a.test_tool),*map(str,command)],stdout=out,stderr=subprocess.STDOUT,env=env)
                try:
                    wait=258
                    for _ in range(90):
                        wait=K.WaitForSingleObject(ready,1000)
                        if wait!=258 or child.poll() is not None:break
                    assert wait==0,dict(wait=wait,exit=child.poll(),log=log.read_text(errors="replace"))
                    self.call(folder,self.a.admission,"check",command[1],success=False)
                    child.kill();child.wait(timeout=15)
                finally:
                    if child.poll() is None:child.kill();child.wait(timeout=15)
        finally:K.CloseHandle(ready);K.CloseHandle(resume)
        barriers=[json.loads(line) for line in log.read_text(errors="replace").splitlines() if line.startswith('{"barrier":')]
        assert barriers and barriers[-1]["barrier"]==phase and barriers[-1]["member"]==member,barriers
        if sequence is not None:assert barriers[-1]["sequence"]==sequence
        assert child.returncode!=0
        return child.returncode
    def killed(self,phase,member=0,sequence=None,tamper=None,repair_phase=None,long_root=False):
        name=f"kill-{phase}-{member}"+(f"-seq-{sequence}" if sequence is not None else "")+(f"-{tamper}" if tamper else "")+(f"-repair-{repair_phase}" if repair_phase is not None else "")+("-long-root" if long_root else "")
        folder,target,pack,root=self.fixture(name,seed=phase==801 and member==1,long_root=long_root)
        original=sha(target);before=self.contents(target)
        owner_exit=self.crash(folder,["migrate",target,pack],phase,member,sequence)
        self.call(folder,self.a.admission,"check",target,success=phase in (900,908))
        self.input_binding(folder,target,self.a.test_tool)
        if tamper:
            stage=next(folder.glob("*-0.stage"))
            prior_stage=dict(dev=stage.stat().st_dev,ino=stage.stat().st_ino,sha=sha(stage))
            if tamper=="bytes":
                with stage.open("ab") as stream:stream.write(b"UNEXPECTED")
            else:
                data=stage.read_bytes();stage.rename(stage.with_suffix(".foreign-original"));stage.write_bytes(data)
            after_stage=dict(dev=stage.stat().st_dev,ino=stage.stat().st_ino,sha=sha(stage))
            if tamper=="identity":assert (prior_stage["dev"],prior_stage["ino"])!=(after_stage["dev"],after_stage["ino"]) and prior_stage["sha"]==after_stage["sha"]
            self.call(folder,self.a.tool,"recover",target,success=False)
            self.call(folder,self.a.admission,"check",target,success=False)
            return dict(phase=phase,member=member,sequence=sequence,tamper=tamper,remains_pending=True,
                        owner_exit=owner_exit,prior_stage=prior_stage,after_stage=after_stage)
        raw_before={p.name:sha(p) for p in root.glob("*.bin")}
        repair_exit=None
        if repair_phase is not None:
            repair_exit=self.crash(folder,["recover",target],repair_phase,
                                   member=1 if repair_phase==955 and sequence>=10 else 0,log_name="repair-owner.log")
            self.call(folder,self.a.admission,"check",target,success=False)
            if repair_phase==955:self.call(folder,self.a.admission,"next-epoch",target,success=False)
        recovered=self.call(folder,self.a.tool,"recover",target)
        archive_root=pathlib.Path("\\\\?\\"+str(root)) if long_root else root
        archives={p.name:sha(p) for p in archive_root.glob("repair-*.raw")}
        if repair_phase is not None or (phase in (2,3,4,6,7,8,9)):
            for digest in raw_before.values():assert digest in archives.values(),(raw_before,archives)
        self.call(folder,self.a.admission,"check",target)
        published=phase in (800,801,802,803,905,906,907,908,203,204) or (phase in (1,2,3,4,5,6,7,8,9,10) and sequence is not None and (sequence>=10 or (sequence==9 and phase in (5,10))))
        independent=None
        if published:
            self.call(folder,self.a.tool,"verify",target,pack)
            assert len(self.contents(target))==len(before)+1
            independent=self.independent_sqlite(target)
            assert any(sha(p)==original for p in folder.glob("*-0.retained"))
        else:
            assert sha(target)==original and self.contents(target)==before
        if repair_phase==955:
            self.call(folder,self.a.admission,"next-epoch",target)
            self.call(folder,self.a.admission,"check",target)
        return dict(phase=phase,member=member,sequence=sequence,published=published,original=original,
                    recovered=sha(target),owner_exit=owner_exit,recovery=recovered["stdout"],independent=independent,
                    raw_before=raw_before,archives=archives,repair_phase=repair_phase,repair_owner_exit=repair_exit,
                    long_root=long_root,root_characters=len(str(root)))

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser()
    for name in ("tool","test-tool","admission","legacy","output"):ap.add_argument("--"+name,type=pathlib.Path,required=True)
    a=ap.parse_args()
    for key in ("tool","test_tool","admission","legacy","output"):setattr(a,key,getattr(a,key).resolve())
    a.output.mkdir(parents=True,exist_ok=True)
    r=Runner(a);r.run("actual-import-and-second-epoch",r.normal);r.run("strict-policy-abort",r.strict_abort)
    for phase in (900,901,902,903,904,905,906,907,908,201,202,203,204):
        r.run(f"actual-owner-kill-{phase}",lambda phase=phase:r.killed(phase,1 if phase in (906,907,908,203,204) else 0))
    for member in (0,1):
        for phase in (800,802,803):
            r.run(f"native-member-kill-{phase}-{member}",lambda phase=phase,member=member:r.killed(phase,member))
    r.run("native-retained-window",lambda:r.killed(801))
    r.run("actual-old-mirror-retained-window",lambda:r.killed(801,1))
    for tamper in ("bytes","identity"):
        r.run(f"recovery-rejects-prepared-{tamper}",lambda tamper=tamper:r.killed(800,tamper=tamper))
    for sequence in (0,5,9,10):
        for phase in range(1,11):
            r.run(f"actual-native-kill-{phase}-seq-{sequence}",
                  lambda phase=phase,sequence=sequence:r.killed(phase,1 if sequence>=10 else 0,sequence))
    for sequence in (0,10):
        for phase in range(950,956):
            r.run(f"actual-repair-kill-{phase}-seq-{sequence}",
                  lambda phase=phase,sequence=sequence:r.killed(7,1 if sequence>=10 else 0,sequence,repair_phase=phase))
    for phase in (201,203):
        r.run(f"actual-gate-short-{phase}",lambda phase=phase:r.gate_fault(phase))
    for kind in ("bytes","identity"):
        r.run(f"repair-rejects-archive-{kind}",lambda kind=kind:r.archive_tamper(kind))
    r.run("actual-repair-long-registered-root",lambda:r.killed(7,sequence=0,long_root=True))
    r.run("repair-rejects-ack-history-rollback",r.floor_tamper)
    assert len(r.rows)==83
    print(f"C02-ACTUAL-MIGRATION cases={len(r.rows)} failed={sum(not x['passed'] for x in r.rows)}",flush=True)
    return 1 if any(not x["passed"] for x in r.rows) else 0
if __name__=="__main__":sys.exit(main())
