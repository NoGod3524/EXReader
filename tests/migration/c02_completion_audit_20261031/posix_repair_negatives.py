# SPDX-License-Identifier: MIT
"""Original-ZIP-bound Repair attacks, re-read as patch ZIPs before full audit.

Construction and ZIP IO run only in Actions. Production files are untouched.
Every removal/rename is reflected in all cumulative actual-FD observations and
the outer artifact inventory; failures must come from the full semantic decoder.
"""
import json
import pathlib
import posixpath
import re
import struct
import zipfile

from protocols import need, sha, json_value
from posix_protocols import observed_id, u64
from posix_owner import audit_posix_owner, relative


def _encoded(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")


class _Attack:
    def __init__(self,files,runtime,observed):
        self.files,self.runtime,self.observed = files,runtime,observed
        self.changed,self.removed,self.renamed,self.row_changes = {},set(),{},{}
        self.identity_changes = {}

    def raw(self,path):
        need(path not in self.removed,"prn-construction-read-not-removed")
        return self.changed.get(path,self.files.get(path))

    def put(self,path,raw):
        relative(path)
        need(path in self.files and isinstance(raw,bytes),"prn-original-regular-member-replacement")
        self.changed[path] = raw

    def object_aliases(self,identity,raw):
        selected = [r for r in self.observed if not r["directory"] and observed_id(r) == identity and
                    self.files[self.runtime+r["artifact_path"]][:8] == b"PC02R001"]
        need(selected,"prn-immutable-real-object-aliases")
        for row in selected:
            self.put(self.runtime+row["artifact_path"],raw)

    def erase(self,path):
        relative(path)
        need(path in self.files and path not in self.changed,"prn-remove-original-existing-member")
        self.removed.add(path)

    def rename(self,old,new,source_old,source_new):
        relative(new)
        need(old in self.files and new not in self.files and new not in self.changed,"prn-canonical-original-object-rename")
        self.removed.add(old);self.renamed[old] = new;self.changed[new] = self.files[old]
        for row in self.observed:
            if self.runtime+row["artifact_path"] == old:
                self.row_changes[row["artifact_path"]] = dict(artifact_path=new[len(self.runtime):],source_path=source_new)
                need(row["source_path"] == source_old,"prn-rename-actual-source-name")

    def change_identity(self,row,**values):
        self.identity_changes[row["artifact_path"]] = values

    def sealed(self):
        changed = dict(self.changed)
        row_paths = []
        for path,raw in self.files.items():
            if not path.startswith(self.runtime):
                continue
            name = posixpath.basename(path)
            if name == "native-source-observations.json" or (
                    name.startswith("native-observations-") and name.endswith(".json")):
                row_paths.append(path)
                original = json_value(raw);rows = []
                for value in original:
                    row = dict(value);old = self.runtime+row["artifact_path"]
                    if old in self.removed and old not in self.renamed:
                        continue
                    row.update(self.row_changes.get(row["artifact_path"],{}))
                    row.update(self.identity_changes.get(value["artifact_path"],{}))
                    archive = self.runtime+row["artifact_path"]
                    if not row["directory"] and archive in changed:
                        row["bytes"],row["sha256"] = len(changed[archive]),sha(changed[archive])
                    rows.append(row)
                if rows != original:
                    changed[path] = _encoded(rows)
        need(self.runtime+"native-source-observations.json" in row_paths,"prn-original-global-observation-array")
        original_inventory = json_value(self.files[self.runtime+"file-hashes.json"])
        inventory = []
        for value in original_inventory:
            row = dict(value);old = self.runtime+row["path"]
            if old in self.removed and old not in self.renamed:
                continue
            if old in self.renamed:
                row["path"] = self.renamed[old][len(self.runtime):]
            path = self.runtime+row["path"]
            if path in changed:
                need("sha256" in row,"prn-only-regular-content-replacement")
                row["bytes"],row["sha256"] = len(changed[path]),sha(changed[path])
            inventory.append(row)
        inventory.sort(key=lambda row:row["path"])
        need(len({r["path"] for r in inventory}) == len(inventory),"prn-resealed-unique-inventory")
        changed[self.runtime+"file-hashes.json"] = _encoded(inventory)
        return changed


def _wrapper(raw,payload):
    need(raw[:8] == b"PC02R001" and len(raw) == 176+len(payload),"prn-complete-original-wrapper")
    out = bytearray(raw)
    out[112:-64] = payload
    out[48:112] = sha(payload).encode("ascii")
    out[-64:] = sha(out[:-64]).encode("ascii")
    return bytes(out)


def _ref(raw,leaf):
    need(raw[:8] == b"PC02R001" and len(leaf.encode("ascii")) < 96,"prn-canonical-reference-target")
    return raw[32:48]+struct.pack("<Q",len(raw))+sha(raw).encode()+b"\0"+leaf.encode()+bytes(96-len(leaf))


def _tree(files,runtime,observed,folder,label,space):
    base = f"repair-cases/{folder}/native-{space}-{label}"
    rows = {r["artifact_path"][len(base):].lstrip("/") or ".":r for r in observed
            if r["artifact_path"] == base or r["artifact_path"].startswith(base+"/")}
    need("." in rows and rows["."]["directory"],"prn-real-original-phase-directory")
    return base,rows


def _route(rows):
    found = [name for name,row in rows.items() if "/" not in name and
             re.fullmatch("[0-9a-f]{64}",name) and row["directory"]]
    need(len(found) == 1,"prn-real-original-single-route")
    return found[0]


def _object(files,runtime,base,rows,path):
    row = rows[path]
    raw = files[runtime+base+"/"+path]
    need(not row["directory"] and raw[:8] == b"PC02R001" and row["bytes"] == len(raw) and
         row["sha256"] == sha(raw) and raw[32:48] == struct.pack("<QQ",*observed_id(row)),
         "prn-actual-native-repair-object")
    return raw,row


def _rewrite_single_plan(attack,folder,mutate):
    runtime,files,observed = attack.runtime,attack.files,attack.observed
    base,rows = _tree(files,runtime,observed,folder,"final","authority");route = _route(rows)
    plan,row = _object(files,runtime,base,rows,route+"/repair-plan-000001")
    need(not any(re.fullmatch(route+r"/repair-plan-(?!000001)[0-9]{6}",p) for p in rows),
         "prn-selected-single-plan-epoch")
    payload = bytearray(plan[112:-64]);mutate(payload)
    guard_leaf = "repair-guard-000001.retired"
    guard,grow = _object(files,runtime,base,rows,route+"/"+guard_leaf)
    proposal = bytearray(payload);proposal[402:587] = bytes(185)
    guard = _wrapper(guard,bytes(proposal))
    payload[402:587] = _ref(guard,"repair.guard")
    plan = _wrapper(plan,bytes(payload))
    applied,arow = _object(files,runtime,base,rows,route+"/repair-applied-000001")
    ap = bytearray(applied[112:-64]);ap[:185] = _ref(plan,"repair-plan-000001")
    applied = _wrapper(applied,bytes(ap))
    done,drow = _object(files,runtime,base,rows,route+"/repair-done-000001")
    dp = bytearray(done[112:-64])
    dp[32:217] = _ref(guard,"repair.guard")
    dp[217:402] = _ref(plan,"repair-plan-000001")
    dp[402:587] = _ref(applied,"repair-applied-000001")
    done = _wrapper(done,bytes(dp))
    for raw,item in ((guard,grow),(plan,row),(applied,arow),(done,drow)):
        attack.object_aliases(observed_id(item),raw)


def _rewrite_done(attack,folder,mutate):
    base,rows = _tree(attack.files,attack.runtime,attack.observed,folder,"final","authority")
    route = _route(rows)
    raw,row = _object(attack.files,attack.runtime,base,rows,route+"/repair-done-000001")
    payload = bytearray(raw[112:-64]);mutate(payload)
    attack.object_aliases(observed_id(row),_wrapper(raw,bytes(payload)))


def repair_negative_controls(files,spec,source,git_bytes,output):
    baseline = audit_posix_owner(files,spec,source,git_bytes)
    need(baseline["actual_cases"] == 36 and baseline["historical_cases"] == 65 and
         baseline["repair_cases"] == 20 and baseline["partial_state_head_repair"] is True,
         "prn-original-full-positive-owner-and-repair-baseline")
    root = pathlib.Path(output);root.mkdir(parents=True,exist_ok=True)
    runtime = relative(spec["runtime_prefix"],True)
    observed = json_value(files[runtime+"native-source-observations.json"])
    need(isinstance(observed,list) and observed,"prn-actual-original-native-fstat-array")
    results = []

    def check(name,attack,expected):
        changed = attack.sealed()
        need(changed and all(isinstance(raw,bytes) for raw in changed.values()) and
             not (set(changed)&attack.removed),"prn-balanced-replacements-removals")
        manifest = dict(schema="pc02-repair-resealed-patch-v1",name=name,source=source,role=spec["role"],
                        original_artifact=spec["artifact"],run=spec["run"],attempt=spec["attempt"],job=spec["job"],
                        expected_rejection=list(expected),removed=sorted(attack.removed),replacements=[])
        for index,path in enumerate(sorted(changed)):
            relative(path);raw = changed[path]
            manifest["replacements"].append(dict(path=path,member=f"replacement-{index:04d}.bin",bytes=len(raw),sha256=sha(raw)))
        patch_path = root/(name+".patch.zip")
        with zipfile.ZipFile(patch_path,"x",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            archive.writestr("patch.json",_encoded(manifest))
            for entry in manifest["replacements"]:
                archive.writestr(entry["member"],changed[entry["path"]])
        reconstructed = dict(files)
        with zipfile.ZipFile(patch_path,"r") as archive:
            parsed = json_value(archive.read("patch.json"))
            names = {"patch.json"}|{entry["member"] for entry in manifest["replacements"]}
            need(parsed == manifest and parsed["original_artifact"]["sha256"] == spec["artifact"]["sha256"] and
                 len(archive.namelist()) == len(names) and set(archive.namelist()) == names,
                 "prn-patch-readback-original-zip-binding-inventory-crc")
            for path in parsed["removed"]:
                relative(path);need(path in reconstructed,"prn-readback-removal-original-member")
                del reconstructed[path]
            # ZipFile.read verifies each member CRC before size/SHA checks.
            for entry in parsed["replacements"]:
                relative(entry["path"]);raw = archive.read(entry["member"])
                need(len(raw) == entry["bytes"] and sha(raw) == entry["sha256"],"prn-patch-readback-size-and-sha")
                reconstructed[entry["path"]] = raw
        failure = None
        try:
            audit_posix_owner(reconstructed,spec,source,git_bytes)
        except ValueError as error:
            failure = str(error)
        need(failure in expected,"prn-full-owner-semantic-rejection:"+name+":"+str(failure))
        raw_patch = patch_path.read_bytes()
        result = dict(name=name,rejected=True,rejection=failure,expected_rejection=list(expected),
            original_zip_sha256=spec["artifact"]["sha256"],patch=patch_path.name,patch_bytes=len(raw_patch),
            patch_sha256=sha(raw_patch),replacements=len(changed),removals=len(attack.removed),
            runtime_inventory_resealed=True,all_cumulative_observations_resealed=True,
            actual_zip_readback=True,decoder="audit_posix_owner")
        (root/(name+".json")).write_bytes(_encoded(result));results.append(result)

    # 1. All wrapper seals and immutable REF links agree, but the PLAN's
    # original state ID is not any independent actual source FD observation.
    attack = _Attack(files,runtime,observed)
    def source_id(payload):
        at = 5039
        need(payload[at+346] == 1,"prn-first-original-part-is-state")
        struct.pack_into("<Q",payload,at+8,u64(payload,at+8)+1)
    _rewrite_single_plan(attack,"partial-head-actual",source_id)
    check("repair-plan-source-id-not-real-fstat",attack,
          ["pr-original-id-not-inferred-from-plan-or-binding"])

    # 2. The copied image bytes stay valid and unchanged. Only its independently
    # observed actual inode contradicts the SDK proof process's held-FD record.
    attack = _Attack(files,runtime,observed)
    base,rows = _tree(files,runtime,observed,"partial-clean-actual","final","authority")
    selected = [(path,row) for path,row in rows.items() if
                re.fullmatch(r".*/proof-[1-9][0-9]*-0-[0-9]+\.image",path)]
    need(selected,"prn-original-actual-sdk-clone")
    path,row = selected[0]
    for alias in observed:
        if alias["source_path"] == row["source_path"]:
            attack.change_identity(alias,inode=alias["inode"]+1)
    check("repair-sdk-clone-actual-native-id-rebound",attack,
          ["pr-sdk-clone-and-source-real-fd-ids-and-exact-held-bytes"])

    # 3. Keep every ACK/FLOOR raw byte and ID; replace only the current directory
    # FD observation. A real directory is part of the INPUT identity contract.
    attack = _Attack(files,runtime,observed)
    folder = "partial-head-actual"
    abase,arows = _tree(files,runtime,observed,folder,"final","authority");rn = _route(arows)
    plan,_ = _object(files,runtime,abase,arows,rn+"/repair-plan-000001")
    journal = plan[112+1003+2756:112+1003+2820].split(b"\0",1)[0].decode("ascii")
    cbase,crows = _tree(files,runtime,observed,folder,"final","custody")
    jrow = crows[journal];need(jrow["directory"],"prn-original-real-journal-directory")
    attack.change_identity(jrow,inode=jrow["inode"]+1)
    check("repair-current-journal-directory-native-id-rebound",attack,
          ["po-journal-actual-fd-identity","pr-current-journal-actual-private-directory-id",
           "pr-original-journal-directory-real-fstat-in-each-source-phase"])

    # 4. Removing an earlier APPLIED cannot be hidden by a later complete PLAN,
    # APPLIED and DONE, even though all those remaining record seals are intact.
    attack = _Attack(files,runtime,observed)
    base,rows = _tree(files,runtime,observed,"two-sequential-interruptions","final","authority")
    rn = _route(rows)
    attack.erase(runtime+base+"/"+rn+"/repair-applied-000001")
    check("repair-complete-history-loses-middle-applied",attack,
          ["pr-every-complete-prior-plan-has-original-applied"])

    # 5. The initial H repair archived only ACK1. The actual later terminal ACK
    # must still be checked after DONE, with the complete final head retained.
    attack = _Attack(files,runtime,observed)
    folder = "partial-head-actual"
    abase,arows = _tree(files,runtime,observed,folder,"final","authority");rn = _route(arows)
    plan,_ = _object(files,runtime,abase,arows,rn+"/repair-plan-000001")
    payload = plan[112:-64];count = u64(payload,5031)
    need(sum(payload[5039+k*452+346] == 6 for k in range(count)) == 1,
         "prn-original-plan-only-archived-first-ack")
    cbase,crows = _tree(files,runtime,observed,folder,"final","custody")
    acks = sorted(p for p in crows if posixpath.dirname(p) == journal and re.fullmatch(r"ack-[0-9]{3}",posixpath.basename(p)))
    need(len(acks)>1,"prn-original-new-terminal-after-plan")
    last = acks[-1];raw = files[runtime+cbase+"/"+last]
    need(raw[:8] == b"PC02ACK1" and raw[296:-64].split(b" ")[2] == b"12",
         "prn-original-new-complete-terminal-ack")
    source_path = crows[last]["source_path"]
    for row in observed:
        if not row["directory"] and row["source_path"] == source_path:
            attack.erase(runtime+row["artifact_path"])
    root_source = crows["."]["source_path"].rsplit("/repair-cases/",1)[0]
    direct = runtime+source_path[len(root_source)+1:] if source_path.startswith(root_source+"/") else None
    if direct in files:
        attack.erase(direct)
    check("repair-done-loses-new-complete-terminal-ack",attack,
          ["pr-done-complete-ack-inventory"])

    # 6. A later real Binding is fully sealed and has its own actual FD witness.
    # It still cannot replace the historical pre-BEGIN DONE's original grant.
    attack = _Attack(files,runtime,observed)
    folder = "pre-begin-repair-then-new-generation"
    nbase,nrows = _tree(files,runtime,observed,folder,"new-generation","authority");rn = _route(nrows)
    later = files[runtime+nbase+"/"+rn+"/binding"]
    fbase,frows = _tree(files,runtime,observed,folder,"final","authority")
    historical = files[runtime+fbase+"/"+rn+"/binding"]
    need(later[:8] == historical[:8] == b"PC02B001" and
         later[40:56] != historical[40:56] and u64(later,88) == u64(historical,88)+1,
         "prn-later-actual-target-and-grant-distinct-from-historical-done")
    def later_target(payload):
        payload[772:1076] = later
    _rewrite_done(attack,folder,later_target)
    check("repair-historical-done-adopts-later-real-target-grant",attack,
          ["pr-before-begin-restores-only-same-existing-grant"])

    # 7. Preserve the complete embedded Binding format/seal while changing only
    # its native authority root. Historical DONE must enforce the pinned domain.
    attack = _Attack(files,runtime,observed)
    def wrong_domain(payload):
        bound = bytearray(payload[772:1076])
        struct.pack_into("<Q",bound,16,u64(bound,16)+1)
        bound[240:304] = sha(bound[:240]).encode("ascii")
        payload[772:1076] = bound
    _rewrite_done(attack,"pre-begin-repair-then-new-generation",wrong_domain)
    check("repair-historical-done-binding-wrong-native-domain",attack,
          ["pr-done-binding-pinned-domain-root"])

    # 8. Reuse the real last raw object of the retained 1701 orphan archive,
    # preserving its actual ID/content. Rename it as an SDK proof. The remaining
    # orphan raw prefix is still consecutive; proof is forbidden before a plan.
    attack = _Attack(files,runtime,observed)
    folder = "repair-retry-1701"
    base,rows = _tree(files,runtime,observed,folder,"final","authority");rn = _route(rows)
    plan,_ = _object(files,runtime,base,rows,rn+"/repair-plan-000001")
    used = plan[112+603:112+699].split(b"\0",1)[0].decode("ascii")
    orphans = [p for p,row in rows.items() if row["directory"] and
               posixpath.dirname(p) == rn and posixpath.basename(p).startswith("repair-archive-") and
               posixpath.basename(p) != used]
    need(orphans,"prn-real-retained-preplan-archive")
    archive = sorted(orphans)[0]
    raw_paths = sorted(p for p,row in rows.items() if not row["directory"] and
                       posixpath.dirname(p) == archive and re.fullmatch(r"raw-[0-9]{4}",posixpath.basename(p)))
    need(raw_paths,"prn-real-last-orphan-raw-object")
    selected = raw_paths[-1];item = rows[selected]
    control = json_value(files[runtime+f"repair-cases/{folder}/process-repair-cut-1701-observation.json"])
    name = f"proof-{control['owner_pid']}-0-0.image"
    old_source = item["source_path"];new_source = posixpath.dirname(old_source)+"/"+name
    aliases = [r for r in observed if r["source_path"] == old_source and not r["directory"]]
    need(aliases,"prn-all-original-retained-orphan-raw-aliases")
    for row in aliases:
        old = runtime+row["artifact_path"];new = posixpath.dirname(old)+"/"+name
        attack.rename(old,new,old_source,new_source)
    check("repair-orphan-archive-manufactures-sdk-proof",attack,
          ["pr-every-sdk-proof-image-in-protected-archive-and-independently-accounted"])

    need(len(results) == 8,"prn-exactly-eight-repair-specific-resealed-controls")
    (root/"repair-negative-controls.json").write_bytes(_encoded(dict(
        schema="pc02-repair-resealed-negatives-v1",source=source,role=spec["role"],
        original_zip_sha256=spec["artifact"]["sha256"],controls=results)))
    return results
