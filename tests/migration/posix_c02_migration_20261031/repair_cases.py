# SPDX-License-Identifier: MIT
"""Actual-process Repair qualification, separate from the original 36 cases."""
import errno, hashlib, json, os, pathlib, signal, struct, subprocess, sys, traceback
class RepairCases:
    def repair_run(self,name,callback):
        try:detail=callback();row=dict(name=name,passed=True,detail=detail)
        except Exception:row=dict(name=name,passed=False,error=traceback.format_exc())
        self.repair_rows.append(row);print(json.dumps(row),flush=True);self.save()
    def repair_save(self):
        value=dict(source=os.environ["GITHUB_SHA"],run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],
                   provider=self.provider,process_uid=os.getuid(),process_euid=os.geteuid(),cases=len(self.repair_rows),
                   failed=sum(not r["passed"] for r in self.repair_rows),results=self.repair_rows)
        (self.a.output/"repair-result.json").write_text(json.dumps(value,indent=2)+"\n")
    def repair_fixture(self,name,kind):
        folder,target,pack,seed=self.fixture(name,area="repair-cases")
        before=dict(database_sha=hashlib.sha256(target.read_bytes()).hexdigest(),database_id=list(self._repair_id(target)),
                    state=(self.route(target)/"state").read_bytes(),binding=(self.route(target)/"binding").read_bytes(),
                    logical=self.logical(target))
        phase=dict(B=1101,C=1201,H=1501)[kind]
        env=dict(os.environ,EXR_PC02_SHORT_PHASE=str(phase))
        failed=self.call(folder,self.a.test_tool,"migrate",target,pack,expected=(2,),env=env)
        route=self.route(target);state=(route/"state").read_bytes();heads=list(route.glob("commit-head-*"))
        assert len(heads)==1
        if kind in ("B","C"):assert len(state)%368==367
        else:assert (heads[0].stat().st_size-464)%272==271
        self.call(folder,self.a.admission,"check",target,expected=(2,))
        self.capture(folder,target,"damaged")
        return folder,target,pack,seed,before,heads[0],failed
    @staticmethod
    def _repair_id(path):
        value=path.stat();return (value.st_dev,value.st_ino)
    def repair_source_hashes(self,folder,target):
        route=self.route(target);paths=[p for p in route.rglob("*") if p.is_file()]
        paths += [p for p in folder.iterdir() if p.is_file() and p.name in ("library.sqlite","library.sqlite.legacy-map.json","input.exrpack")]
        for p in folder.glob("c02-*.journal"):
            paths += [q for q in p.iterdir() if q.is_file()]
        return {str(p):(self._repair_id(p),p.stat().st_size,hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths}
    def repair_sources_equal(self,before):
        for name,want in before.items():
            path=pathlib.Path(name)
            assert path.exists() and (self._repair_id(path),path.stat().st_size,hashlib.sha256(path.read_bytes()).hexdigest())==want,name
    def repair_pause(self,folder,target,phase,label):
        return self.paused(folder,target,None,phase,command=("recover",target),label=label)
    def repair_finish(self,folder,target,pack,seed,before,kind):
        result=self.call(folder,self.a.tool,"recover",target)
        self.call(folder,self.a.admission,"check",target)
        self.call(folder,self.a.guarded,"verify","--pack",seed,"--target",target)
        actual=self.logical(target)
        assert all(row in actual["books"] for row in before["logical"]["books"])
        assert all(row in actual["notes"] for row in before["logical"]["notes"])
        route=self.route(target);assert not (route/"repair.guard").exists()
        if kind=="C":
            self.call(folder,self.a.tool,"verify",target,pack);self.independent(target)
        else:
            assert hashlib.sha256(target.read_bytes()).hexdigest()==before["database_sha"]
            assert self._repair_id(target)==tuple(before["database_id"])
        plans=sorted(route.glob("repair-plan-*"));done=sorted(route.glob("repair-done-*"))
        assert plans and done
        self.capture(folder,target,"final")
        return dict(command_pid=result["pid"],plans=len(plans),done=len(done),same_original_grant=kind=="B",
                    original_source_and_annotations_preserved=True)
    def repair_basic(self,kind):
        name="partial-"+dict(B="begin",C="clean",H="head")[kind]+"-actual"
        folder,target,pack,seed,before,head,_=self.repair_fixture(name,kind)
        damaged=self.repair_source_hashes(folder,target)
        paused=self.repair_pause(folder,target,1702,"repair-plan-1")
        self.repair_sources_equal(damaged)
        result=self.repair_finish(folder,target,pack,seed,before,kind)
        assert result["command_pid"]!=paused["owner_pid"]
        if kind=="B":
            assert (self.route(target)/"binding").read_bytes()==before["binding"]
            assert (self.route(target)/"state").read_bytes()==before["state"]
        return dict(kind=kind,plan_before_source_mutation=True,**result)
    def repair_cut(self,point):
        name="repair-retry-"+str(point);kind="B" if point==1706 else "H"
        folder,target,pack,seed,before,head,_=self.repair_fixture(name,kind)
        if point==1701:
            damaged=self.repair_source_hashes(folder,target)
            self.repair_pause(folder,target,1701,"repair-cut-1701")
            self.repair_sources_equal(damaged)
            assert not list(self.route(target).glob("repair-plan-*"))
        self.repair_pause(folder,target,1702,"repair-plan-1")
        if point not in (1701,1702):self.repair_pause(folder,target,point,"repair-cut-"+str(point))
        result=self.repair_finish(folder,target,pack,seed,before,kind)
        return dict(point=point,actual_sigkill=True,**result)
    def repair_twice(self):
        folder,target,pack,seed,before,head,_=self.repair_fixture("two-sequential-interruptions","H")
        self.repair_pause(folder,target,1702,"repair-plan-1")
        self.repair_pause(folder,target,1705,"repair-cut-1705")
        self.call(folder,self.a.test_tool,"recover",target,expected=(2,),env=dict(os.environ,EXR_PC02_SHORT_PHASE="1201"))
        assert (self.route(target)/"state").stat().st_size%368==367
        self.capture(folder,target,"damaged-2")
        unchanged=self.repair_source_hashes(folder,target)
        self.repair_pause(folder,target,1702,"repair-plan-2")
        self.repair_sources_equal(unchanged)
        assert len(list(self.route(target).glob("repair-plan-*")))==2
        result=self.repair_finish(folder,target,pack,seed,before,"H")
        assert result["plans"]==2 and result["done"]==1
        return result
    def repair_refusal(self,name,make):
        folder,target,pack,seed=self.fixture(name,area="repair-cases")
        make(folder,target,pack)
        self.capture(folder,target,"damaged")
        before=self.repair_source_hashes(folder,target)
        self.call(folder,self.a.admission,"check",target,expected=(2,))
        self.call(folder,self.a.tool,"recover",target,expected=(2,))
        self.repair_sources_equal(before);self.capture(folder,target,"refused")
        return dict(complete_contradiction_refused=True,no_source_modification=True)
    def repair_ambiguous(self):
        def make(folder,target,pack):
            self.paused(folder,target,pack,900,label="orphan-input-1")
            self.call(folder,self.a.test_tool,"migrate",target,pack,expected=(2,),env=dict(os.environ,EXR_PC02_SHORT_PHASE="1101"))
            route=self.route(target);assert len(list(route.glob("input-*")))==2
            state=route/"state";raw=state.read_bytes();assert len(raw)%368==367
            with state.open("r+b",buffering=0) as f: f.truncate(len(raw)-366);os.fsync(f.fileno())
            assert len(state.read_bytes())%368==1
        return self.repair_refusal("ambiguous-orphan-inputs-refused",make)
    def repair_double_partial(self):
        def make(folder,target,pack):
            self.call(folder,self.a.tool,"migrate",target,pack)
            route=self.capture(folder,target,"complete-before-corruption")
            for source in (route/"state",next(route.glob("commit-head-*"))):
                with source.open("r+b",buffering=0) as f: f.truncate(source.stat().st_size-1);os.fsync(f.fileno())
        return self.repair_refusal("incompatible-state-head-partials-refused",make)
    def repair_complete_conflict(self):
        def make(folder,target,pack):
            self.paused(folder,target,pack,901,label="complete-begin")
            path=self.route(target)/"state";raw=bytearray(path.read_bytes())
            struct.pack_into("<Q",raw,len(raw)-368+24,99);raw[-64:]=hashlib.sha256(raw[-368:-64]).hexdigest().encode()
            with path.open("r+b",buffering=0) as f:f.write(raw);os.fsync(f.fileno())
        return self.repair_refusal("complete-state-conflict-refused",make)
    def repair_orphan_applied(self):
        def make(folder,target,pack):
            path=self.route(target)/"repair-applied-000256"
            fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            try:
                st=os.fstat(fd);payload=b"\0"*363
                header=b"PC02R001"+struct.pack("<QQQ",2,256,len(payload))+struct.pack("<QQ",st.st_dev,st.st_ino)+hashlib.sha256(payload).hexdigest().encode()
                raw=header+payload;raw+=hashlib.sha256(raw).hexdigest().encode()
                assert os.write(fd,raw)==len(raw);os.fsync(fd)
            finally:os.close(fd)
        return self.repair_refusal("orphan-applied-refused",make)
    def repair_selected_clean(self):
        folder,target,pack,seed=self.fixture("selected-complete-clean-restored",area="repair-cases")
        before=dict(database_sha=hashlib.sha256(target.read_bytes()).hexdigest(),database_id=list(self._repair_id(target)),
                    logical=self.logical(target))
        self.call(folder,self.a.tool,"migrate",target,pack)
        route=self.capture(folder,target,"selected-complete")
        full=(route/"state").read_bytes();binding=(route/"binding").read_bytes()
        with (route/"state").open("r+b",buffering=0) as f:f.truncate(len(full)-1);os.fsync(f.fileno())
        self.capture(folder,target,"damaged");self.repair_pause(folder,target,1702,"repair-plan-1")
        result=self.repair_finish(folder,target,pack,seed,before,"C")
        assert (route/"state").read_bytes()==full and (route/"binding").read_bytes()==binding
        return dict(complete_clean_never_discarded=True,**result)
    def repair_floor_rollback(self):
        folder,target,pack,seed,before,head,_=self.repair_fixture("protected-applied-floor-rollback-refused","C")
        self.repair_pause(folder,target,1702,"repair-plan-1")
        self.repair_pause(folder,target,1705,"repair-cut-1705")
        with head.open("r+b",buffering=0) as f:f.truncate(head.stat().st_size-272);os.fsync(f.fileno())
        self.capture(folder,target,"rolled-back")
        unchanged=self.repair_source_hashes(folder,target)
        self.call(folder,self.a.tool,"recover",target,expected=(2,))
        self.call(folder,self.a.admission,"check",target,expected=(2,))
        self.repair_sources_equal(unchanged);self.capture(folder,target,"refused")
        return dict(same_head_identity=True,protected_floor_rollback_refused=True,no_source_modification=True)
    def repair_authority_acl(self):
        folder,target,pack,seed=self.fixture("authority-allow-acl-refused",area="repair-cases")
        self.capture(folder,target,"before-acl");before=self.repair_source_hashes(folder,target)
        mode=self.authority.stat().st_mode&0o7777;added=False;original=None
        try:
            if sys.platform=="darwin":
                self.call(folder,pathlib.Path("/bin/ls"),"-lde",self.authority)
                self.call(folder,pathlib.Path("/bin/chmod"),"+a#","0","everyone allow write",self.authority);added=True
                self.call(folder,pathlib.Path("/bin/ls"),"-lde",self.authority)
            else:
                try:original=os.getxattr(self.authority,"system.posix_acl_access")
                except OSError as e:
                    if e.errno!=errno.ENODATA:raise
                raw=struct.pack("<I",2)+b"".join(struct.pack("<HHI",tag,perm,uid) for tag,perm,uid in
                    ((1,7,0xffffffff),(2,7,65534),(4,0,0xffffffff),(16,7,0xffffffff),(32,0,0xffffffff)))
                os.setxattr(self.authority,"system.posix_acl_access",raw);added=True
                actual=os.getxattr(self.authority,"system.posix_acl_access");assert actual==raw
                (folder/"acl-system-call.json").write_text(json.dumps(dict(operation="os.setxattr",path=str(self.authority),
                    name="system.posix_acl_access",value_hex=raw.hex(),readback_hex=actual.hex(),returncode=0),indent=2)+"\n")
            self.capture(folder,target,"allow-acl")
            self.call(folder,self.a.admission,"check",target,expected=(2,))
            self.call(folder,self.a.tool,"recover",target,expected=(2,))
            self.repair_sources_equal(before)
        finally:
            if added:
                if sys.platform=="darwin":self.call(folder,pathlib.Path("/bin/chmod"),"-a#","0",self.authority)
                elif original is None:os.removexattr(self.authority,"system.posix_acl_access")
                else:os.setxattr(self.authority,"system.posix_acl_access",original)
                os.chmod(self.authority,mode)
        self.call(folder,self.a.admission,"check",target);self.capture(folder,target,"restored-acl")
        return dict(authority_allow_acl_refused=True,no_source_modification=True)
    def repair_all(self):
        for kind in ("B","C","H"):self.repair_run("partial-"+dict(B="begin",C="clean",H="head")[kind]+"-actual",lambda kind=kind:self.repair_basic(kind))
        for point in range(1701,1707):self.repair_run("repair-retry-"+str(point),lambda point=point:self.repair_cut(point))
        for name,callback in (("two-sequential-interruptions",self.repair_twice),
            ("ambiguous-orphan-inputs-refused",self.repair_ambiguous),
            ("incompatible-state-head-partials-refused",self.repair_double_partial),
            ("complete-state-conflict-refused",self.repair_complete_conflict),
            ("orphan-applied-refused",self.repair_orphan_applied),
            ("selected-complete-clean-restored",self.repair_selected_clean),
            ("protected-applied-floor-rollback-refused",self.repair_floor_rollback),
            ("authority-allow-acl-refused",self.repair_authority_acl)):
            self.repair_run(name,callback)
        assert len(self.repair_rows)==17
