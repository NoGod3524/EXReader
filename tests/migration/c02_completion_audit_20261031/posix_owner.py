# SPDX-License-Identifier: MIT
"""Independent audit of the desktop POSIX owner's original Actions artifact.

Only raw ZIP members and qualified source bytes are inputs. No owner, SDK,
fixture generator or native admission library is imported or executed.
"""
import ast
import posixpath
import re
import sqlite3
import stat
import struct

from protocols import (need, sha, hexadecimal, integer, json_value, ztext,
                       history, legacy_pack, sqlite_content)
from posix_protocols import (ZERO, u64, native_id, digest_field, absolute_path,
                             observed_id, metadata, route, anchor, binding, states)
from posix_migration import (audit_transaction, metadata_envelope, committed_head,
                             final_name, head_name, native_ack)

OWNER = "extras/migration/posix_c02_migration_20261031/"
DRIVER = "tests/migration/posix_c02_migration_20261031/run.py"
HISTORICAL = "tests/migration/run_cases.py"
FIXTURES = "tests/migration/legacy_data.py"
OLD_NAMES = ("exreader-legacy-migrate", "exreader-legacy-migrate-tx",
             "exreader-legacy-migrate-recovery")
POINTS = (900,901,902,903,904,905,906,907,908,1101,1102,
          1201,1202,1203,1204,1205,1601,1602,1603,1604)
GATE_NAMES = ("PC02-native-authority-v1", "PC02-synchronous-two-member-v1",
              "PC02-exact-ack-floor-v1", "PC02-actual-SDK-proof-v1",
              "PC02-no-workers-v1")
BIND_FIELDS = (("source",41),("run",21),("attempt",8),("artifact",65),
               ("platform",32),("sdk",64),("provider",65))
TABLES = ("books","notes","fixed_notes","audio_library","audio_tracks","audio_marks")


def relative(value, prefix=False):
    need(isinstance(value,str) and value and not value.startswith("/") and
         "\0" not in value, "po-explicit-relative-path")
    body = value[:-1] if prefix and value.endswith("/") else value
    need(posixpath.normpath(body) == body and
         all(part not in ("",".","..") for part in body.split("/")),
         "po-canonical-relative-path")
    need(not prefix or value.endswith("/"), "po-explicit-prefix-trailing-slash")
    return value


def padded(raw, offset, count, utf8=False):
    data = raw[offset:offset+count]
    need(len(data) == count and b"\0" in data, "po-bounded-text")
    value, tail = data.split(b"\0",1)
    need(value and not any(tail), "po-canonical-text-padding")
    return value.decode("utf-8" if utf8 else "ascii")


def file_record(raw, offset):
    identity = native_id(raw,offset)
    size = u64(raw,offset+16)
    digest = padded(raw,offset+24,65)
    need(identity[1] > 0 and hexadecimal(digest,64) and digest != ZERO,
         "po-file-record-native-id-and-digest")
    return dict(identity=identity, size=size, sha256=digest)


def _source_text(source, path, git_bytes):
    raw = git_bytes(source,path)
    need(isinstance(raw,bytes), "po-qualified-source-bytes")
    return raw.decode("utf-8")


def qualified_material(files, evidence, source, git_bytes):
    cmake = _source_text(source,OWNER+"CMakeLists.txt",git_bytes)
    matches = re.findall(r"set\(_provider_inputs\s+(.*?)\)",cmake,re.S)
    need(len(matches) == 1, "po-qualified-provider-material-list")
    paths = matches[0].split()
    need(len(paths) == len(set(paths)) and len(paths) >= 21 and
         {"src/pc02_main.c","src/pc02_journal.c","src/pc02_transform.c",
          "../posix_c02_admission_20261031/src/pc02_migration.inc",
          "../posix_c02_admission_20261031/src/pc02_floor_head.inc",
          "../windows_coordinator_hardening_20261030/src/wh_digest.c"} <= set(paths),
         "po-complete-owner-native-transformer-coordinator-material")
    material = b"PC02-synchronous-production-ACK296-FLOOR352-v1\n"
    for path in paths:
        resolved = posixpath.normpath(OWNER+path)
        relative(resolved)
        material += (path+" "+sha(git_bytes(source,resolved))+"\n").encode()
    need(files[evidence+"pc02-provider-inputs.txt"] == material,
         "po-provider-exact-qualified-source-material")
    frozen_runner = git_bytes(source,HISTORICAL)
    frozen_fixtures = git_bytes(source,FIXTURES)
    need(sha(frozen_runner) == "28c1401cdfac08475232a5b234748b379aca2ef8a9bf0760cd32310db83b215a" and
         sha(frozen_fixtures) == "9c6baddebbcce6ac7597eed9c93c39a39ca547af77dca93fc98c9d88bec8e5d4",
         "po-original-65-fixtures-unchanged")
    tree = ast.parse(frozen_fixtures.decode())
    literals = [node.value for node in tree.body if isinstance(node,ast.Assign) and
                any(isinstance(t,ast.Name) and t.id == "TXT" for t in node.targets)]
    need(len(literals) == 1 and isinstance(literals[0],ast.Call) and
         isinstance(literals[0].func,ast.Attribute) and literals[0].func.attr == "encode" and
         not literals[0].keywords, "po-original-txt-static-literal")
    txt = ast.literal_eval(literals[0].func.value)
    need(isinstance(txt,str), "po-original-txt-string")
    cases = {}
    for node in ast.parse(frozen_runner.decode()).body:
        if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            continue
        decorators = [d for d in node.decorator_list if isinstance(d,ast.Call) and
                      isinstance(d.func,ast.Name) and d.func.id == "case"]
        if decorators:
            need(len(decorators) == 1 and len(decorators[0].args) == 1,
                 "po-historical-decorator")
            cases[node.name] = ast.literal_eval(decorators[0].args[0])
    need(len(cases) == 65, "po-all-65-qualified-historical-cases")
    # This adapter describes the synchronous INPUT13844/PREPARED251 producer.
    main = _source_text(source,OWNER+"src/pc02_main.c",git_bytes)
    driver = _source_text(source,DRIVER,git_bytes)
    need("sizeof(p2_input)==13844" in main and "sizeof(p2_prepared)==251" in main and
         "PC02-synchronous" in cmake and "cases=36 failed=0" in driver,
         "po-qualified-production-wire-and-full-driver")
    dataset = [n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name == "dataset"]
    need(len(dataset) == 1, "po-qualified-full-dataset")
    book_ids,note_ids = set(),set()
    for node in ast.walk(dataset[0]):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.args:
            if node.func.id == "book_record":
                book_ids.add(ast.literal_eval(node.args[0]))
            elif node.func.id == "note_record":
                note_ids.add(ast.literal_eval(node.args[0]))
    need(len(book_ids) == 5 and len(note_ids) == 16, "po-complete-five-kinds-sixteen-notes")
    return dict(provider=sha(material),txt=txt.encode("utf-8"),historical=cases,
                book_ids=book_ids,note_ids=note_ids,qualified_material_sha256=sha(material))


def audit_inventory(files, runtime):
    rows = json_value(files[runtime+"file-hashes.json"])
    need(isinstance(rows,list) and rows, "po-runtime-inventory")
    regular = set()
    seen = set()
    for row in rows:
        path = relative(row["path"])
        need(path not in seen and all(integer(row[k]) for k in
             ("device","inode","uid","gid","links","mode")), "po-inventory-native-fields")
        seen.add(path)
        need(0 <= row["mode"] <= 0o7777 and row["inode"] > 0,
             "po-inventory-mode-identity")
        if "sha256" in row:
            raw = files[runtime+path]
            need(integer(row["bytes"]) and len(raw) == row["bytes"] and
                 row["sha256"] == sha(raw), "po-runtime-inventory-exact-bytes")
            regular.add(runtime+path)
        else:
            need("bytes" not in row and runtime+path not in files,
                 "po-inventory-directory-not-raw-file")
    need(regular == {p for p in files if p.startswith(runtime)} -
         {runtime+"file-hashes.json"}, "po-runtime-inventory-full-coverage")
    return len(regular)


def historical_report(files, runtime, evidence, material):
    report = json_value(files[runtime+"legacy-result.json"])
    expected = material["historical"]
    need(report["schema"] == 1 and report["kind"] == "wp12-legacy-migration-scenarios" and
         report["tool"]["path"] == OLD_NAMES[0] and
         report["tool"]["version"] == "exreader-legacy-migrate 0.1.0 (EXReader SDK 3.42.0)" and
         report["tool"]["sha256"] == sha(files[evidence+"preserved-binaries/legacy/"+OLD_NAMES[0]]),
         "po-original-historical-report-and-installed-binary")
    rows = report["cases"]
    need(isinstance(rows,list) and len(rows) == 65 and
         {r["name"] for r in rows} == set(expected), "po-full-historical-named-cases")
    checks = 0
    for row in rows:
        need(row["area"] == expected[row["name"]] and row["passed"] is True and
             row["error"] is None and isinstance(row["checks"],list) and row["checks"] and
             integer(row["tool_invocations"]) and row["tool_invocations"] > 0,
             "po-original-historical-case")
        for check in row["checks"]:
            need(check["ok"] is True and isinstance(check["check"],str) and check["check"],
                 "po-original-historical-check")
            checks += 1
    summary = report["summary"]
    need(summary["cases"] == summary["passed"] == 65 and summary["failed"] == 0 and
         summary["checks"] == summary["checks_passed"] == checks and
         summary["tool_invocations"] == sum(r["tool_invocations"] for r in rows) and
         summary["areas"] == sorted(set(expected.values())), "po-original-historical-summary")
    return dict(cases=65,checks=checks,tool_invocations=summary["tool_invocations"])


class OwnerAudit:
    def __init__(self, files, spec, source, material):
        self.files, self.spec, self.source, self.material = files,spec,source,material
        self.evidence = relative(spec["evidence_prefix"],True)
        self.runtime = relative(spec["runtime_prefix"],True)
        need(self.runtime == f"c02-posix-migration-{spec['run']}-{spec['attempt']}/",
             "po-exact-runtime-run-attempt")
        self.receipt = self.json("migration-result.json")
        r = self.receipt
        need(r["source"] == source and str(r["run"]) == str(spec["run"]) and
             str(r["attempt"]) == str(spec["attempt"]) and r["provider"] == material["provider"],
             "po-producer-qualified-run-provider")
        self.euid = r["process_euid"]
        need(integer(self.euid) and self.euid > 0 and r["process_uid"] == self.euid,
             "po-real-nonroot-native-owner")
        self.observations = self.json("native-source-observations.json")
        need(isinstance(self.observations,list) and self.observations,
             "po-real-fd-observations")
        self.observed = {}
        for row in self.observations:
            path = relative(row["artifact_path"])
            need(path not in self.observed and type(row["directory"]) is bool and
                 integer(row["raw_mode"]) and integer(row["mode"]) and
                 row["mode"] == stat.S_IMODE(row["raw_mode"]) and
                 (stat.S_ISDIR(row["raw_mode"]) if row["directory"] else
                  stat.S_ISREG(row["raw_mode"])), "po-unique-actual-fstat-object-and-mode")
            absolute_path(row["source_path"])
            normalized = dict(row,path=path,mode=row["raw_mode"])
            metadata(normalized,self.euid,directory=row["directory"],
                     private="/native-authority-" in path or row["directory"])
            if not row["directory"]:
                raw = files[self.runtime+path]
                need(row["bytes"] == len(raw) and row["sha256"] == sha(raw),
                     "po-source-fstat-original-raw-size-and-sha")
            self.observed[path] = row
        self.binary_map = {}
        self.binary_hash = {}
        for role,key in (("tool","owner"),("test_tool","controls"),("admission","admission")):
            archive = relative(spec["binaries"][key])
            entry = r["binaries"][role]
            absolute_path(entry["path"])
            raw = files[archive]
            need(entry["bytes"] == len(raw) and entry["sha256"] == sha(raw) and
                 integer(entry["mode"]) and entry["mode"] & 0o111 and
                 not entry["mode"] & 0o22, "po-installed-owner-binary-binding")
            self.binary_map[entry["path"]] = (role,archive)
            self.binary_hash[role] = sha(raw)
        self.home = None
        for role,kind in (("legacy","legacy"),("guarded","guarded")):
            entry = r["binaries"][role]
            path = self.evidence+"preserved-binaries/"+kind+"/"+OLD_NAMES[1]
            raw = files[path]
            need(entry["bytes"] == len(raw) and entry["sha256"] == sha(raw) and
                 not entry["mode"] & 0o22 and entry["mode"] & 0o111,
                 "po-legacy-versus-guarded-installed-role")
            for name in OLD_NAMES:
                archive = self.evidence+"preserved-binaries/"+kind+"/"+name
                need(archive in files and files[archive], "po-all-six-actual-cli-binaries-retained")
                self.binary_map[posixpath.dirname(entry["path"])+"/"+name] = (kind,archive)
        need(self.binary_hash["tool"] != self.binary_hash["test_tool"],
             "po-installed-owner-distinct-from-controls-binary")
        self.commands = {}
        numbers = []
        self.observer = None
        for path,raw in files.items():
            if not path.startswith(self.runtime):
                continue
            match = re.fullmatch(r"(.*)command-([0-9]{4})\.json",path[len(self.runtime):])
            if not match:
                continue
            row = json_value(raw)
            command = row["command"]
            need(isinstance(command,list) and command and command[0] in self.binary_map and
                 all(isinstance(v,str) for v in command) and integer(row["pid"]) and row["pid"] > 0 and
                 integer(row["observer_pid"]) and row["observer_pid"] > 0 and
                 row["observer_uid"] == row["observer_euid"] == self.euid and
                 type(row["exit"]) is int and row["timed_out"] is False and
                 isinstance(row["stdout"],str) and isinstance(row["stderr"],str),
                 "po-actual-command-binary-pid-and-result")
            if self.observer is None:
                self.observer = row["observer_pid"]
            need(row["observer_pid"] == self.observer and row["pid"] != self.observer,
                 "po-single-observer-and-independent-command-process")
            number = int(match[2])
            numbers.append(number)
            self.commands.setdefault(match[1].rstrip("/"),[]).append((number,row))
        need(sorted(numbers) == list(range(1,len(numbers)+1)), "po-complete-command-sequence")
        for rows in self.commands.values():
            rows.sort(key=lambda item:item[0])
        versions = self.commands.get("",[])
        need(len(versions) == 2, "po-both-production-and-control-version-commands")
        for (_,row),role in zip(versions,("tool","test_tool")):
            need(self.binary_map[row["command"][0]][0] == role and row["command"][1:] == ["--version"] and
                 row["exit"] == 0 and row["stdout"].strip() ==
                 f"exreader-c02-migrate {source} provider={material['provider']} SDK=3.42.0 synchronous-posix",
                 "po-actual-version-provenance")
        self.snapshots = {}
        self.used_observations = set()
        self.transactions = 0
        self.case_details = []

    def json(self,path):
        return json_value(self.files[self.runtime+path])

    def raw(self, relative_path):
        return self.files[self.runtime+relative_path]

    def rows(self,folder):
        return [row for _,row in self.commands.get("cases/"+folder,[])]

    def find(self,folder,role,args,exit_code=None):
        found = [r for r in self.rows(folder) if
                 self.binary_map[r["command"][0]][0] == role and r["command"][1:] == args]
        need(found, "po-actual-command-present:"+folder+":"+str(args[:1]))
        if exit_code is not None:
            need(any(r["exit"] == exit_code for r in found), "po-actual-command-exit")
        return found

    def normalize(self,row,path):
        return dict(row,path=path,mode=row["raw_mode"])

    def snapshot(self,folder,label):
        key = folder,label
        if key in self.snapshots:
            return self.snapshots[key]
        base = "cases/"+folder+"/"
        ap = base+"native-authority-"+label
        cp = base+"native-custody-"+label
        captured = [r for r in self.observations if r["artifact_path"] == ap or
                    r["artifact_path"].startswith(ap+"/") or r["artifact_path"] == cp or
                    r["artifact_path"].startswith(cp+"/")]
        need(captured, "po-required-native-phase-snapshot")
        phase_rows = self.json(base+"native-observations-"+label+".json")
        need(isinstance(phase_rows,list), "po-phase-cumulative-fstat-array")
        phase_map = {r["artifact_path"]:r for r in phase_rows}
        need(len(phase_map) == len(phase_rows) and all(phase_map.get(r["artifact_path"]) == r
             for r in captured), "po-independent-phase-cumulative-fstat-binding")
        ar,cr = {},{}
        for row in captured:
            path = row["artifact_path"]
            self.used_observations.add(path)
            root = ap if path == ap or path.startswith(ap+"/") else cp
            rel = path[len(root):].lstrip("/") or "."
            dest = ar if root == ap else cr
            need(rel not in dest, "po-phase-unique-actual-object")
            dest[rel] = self.normalize(row,rel)
        need("." in ar and "." in cr, "po-actual-authority-and-library-parent-directory-fds")
        root = self.json(ap+"/root-observation.json")
        authority_path = absolute_path(ar["."]["source_path"])
        parent_path = absolute_path(cr["."]["source_path"])
        library = parent_path+"/library.sqlite"
        need(root == dict(path=authority_path,device=ar["."]["device"],inode=ar["."]["inode"],
                          uid=self.euid,mode=ar["."]["mode"] & 0o7777),
             "po-path-stat-agrees-with-independent-authority-fstat")
        home = posixpath.dirname(posixpath.dirname(parent_path))
        need(posixpath.basename(home) == self.runtime.rstrip("/") and
             posixpath.basename(posixpath.dirname(parent_path)) == "cases" and
             parent_path.endswith("/cases/"+folder), "po-native-case-physical-runtime-path")
        actual_home = posixpath.dirname(home)
        need(authority_path == actual_home+"/.exreader-c02-admission",
             "po-fixed-passwd-home-authority-independent-of-package")
        if self.home is None:
            self.home = actual_home
        need(self.home == actual_home, "po-same-fixed-runner-user-home")
        for rel,row in ar.items():
            need(row["source_path"] == authority_path+("" if rel=="." else "/"+rel),
                 "po-authority-actual-source-path")
        for rel,row in cr.items():
            need(row["source_path"] == parent_path+("" if rel=="." else "/"+rel),
                 "po-custody-actual-source-path")
        root_id = observed_id(ar["."])
        a = anchor(self.raw(ap+"/authority"))
        need(a["root"] == root_id and a["registry"] == observed_id(ar["registry.lock"]) and
             a["identity"] == observed_id(ar["authority"]) and
             self.raw(ap+"/registry.lock") == b"PC02-REGISTRY\n\0\0",
             "po-actual-authority-registry-self-id")
        rn = route(observed_id(cr["."]),library)
        need(set(p for p in ar if "/" not in p) == {".","authority","registry.lock",rn},
             "po-complete-single-current-route-capture")
        regular_a = {self.runtime+ap+"/"+p for p,r in ar.items() if not r["directory"]}
        need(regular_a == {p for p in self.files if p.startswith(self.runtime+ap+"/")} -
             {self.runtime+ap+"/root-observation.json"}, "po-all-authority-raw-files-have-actual-fstat")
        regular_c = {self.runtime+cp+"/"+p for p,r in cr.items() if not r["directory"]}
        need(regular_c == {p for p in self.files if p.startswith(self.runtime+cp+"/")},
             "po-all-custody-raw-files-have-actual-fstat")
        br = self.raw(ap+"/"+rn+"/binding")
        sr = self.raw(ap+"/"+rn+"/state")
        b,ss = binding(br),states(sr)
        need(b["root"] == root_id and b["parent"] == observed_id(cr["."]) and b["route"] == rn,
             "po-live-binding-native-root-parent-route")
        for name in ("binding","state","lease"):
            need(observed_id(ar[rn+"/"+name]) == b["identity" if name=="binding" else name],
                 "po-live-binding-actual-fstat-"+name)
        granted = [r for r in ss if r["seal"] == b["grant"]]
        need(len(granted) == 1 and granted[0]["kind"] in ("I","C") and
             granted[0]["generation"] == b["generation"] and granted[0]["target"] == b["target"],
             "po-binding-exact-recorded-clean-grant")
        admitted = (ss[-1]["seal"] == b["grant"] and "library.sqlite" in cr and
                    observed_id(cr["library.sqlite"]) == b["target"])
        snap = dict(folder=folder,label=label,ap=ap,cp=cp,authority=ar,custody=cr,
                    authority_path=authority_path,parent_path=parent_path,library=library,
                    route=rn,binding_raw=br,state_raw=sr,binding=b,states=ss,
                    admitted=admitted,parent=self.normalize(cr["."],parent_path))
        self.snapshots[key] = snap
        return snap

    def custody_raw(self,snap,name):
        need(name in snap["custody"] and not snap["custody"][name]["directory"],
             "po-required-actual-custody-file:"+name)
        return self.raw(snap["cp"]+"/"+name)

    def match_file(self,snap,name,expected):
        row = snap["custody"].get(name)
        need(row is not None and not row["directory"] and observed_id(row) == expected["identity"] and
             row["bytes"] == expected["size"] and row["sha256"] == expected["sha256"],
             "po-actual-member-identity-size-digest:"+name)
        raw = self.custody_raw(snap,name)
        need(len(raw) == expected["size"] and sha(raw) == expected["sha256"],
             "po-actual-member-original-bytes")
        return raw

    def decode_input(self,snap,envelope,role):
        raw = envelope["payload"]
        need(len(raw) == 13844 and raw[:8] == b"PC02IN01", "po-production-input-13844")
        fields = {}
        offset = 8
        for name,size in BIND_FIELDS:
            fields[name] = padded(raw,offset,size)
            offset += size
        need(offset == 304 and fields["source"] == self.source and
             fields["run"] == str(self.spec["run"]) and
             fields["attempt"] == str(self.spec["attempt"]) and
             fields["artifact"] == self.binary_hash[role] and
             fields["provider"] == self.material["provider"] and
             fields["sdk"] == "3.42.0-8357eafa" and
             fields["platform"] == ("linux-ext4" if self.spec["role"] == "posix-migration-linux" else "macos-apfs"),
             "po-input-qualified-producer-installed-artifact-sdk-platform")
        gates = [padded(raw,304+65*k,65) for k in range(5)]
        need(gates == [sha(n.encode()) for n in GATE_NAMES], "po-actual-native-gate-contract-identities")
        manifest = "EXRWH2|"+"|".join(k+"="+fields[k] for k,_ in BIND_FIELDS)
        manifest += "|"+"|".join(k+"="+v for k,v in zip(
            ("admission","publisher","recovery","observer","fault"),gates))
        manifest_raw = manifest.encode("ascii")
        library,source_pack,authority_path = [padded(raw,off,4096,True) for off in (629,4725,8821)]
        for value in (library,source_pack,authority_path):
            absolute_path(value)
        need(library == snap["library"] and source_pack == snap["parent_path"]+"/input.exrpack" and
             authority_path == snap["authority_path"], "po-immutable-input-fixed-actual-routes")
        token = padded(raw,12917,49)
        need(hexadecimal(token,48), "po-random-transaction-token")
        stages = [padded(raw,12966+64*k,64) for k in range(2)]
        retained = [padded(raw,13094+64*k,64) for k in range(2)]
        journal,private_pack = padded(raw,13222,64),padded(raw,13286,64)
        need(stages == [f"c02-{token}-{k}.stage" for k in range(2)] and
             retained == [f"c02-{token}-{k}.retained" for k in range(2)] and
             journal == f"c02-{token}.journal" and private_pack == f"c02-{token}.pack",
             "po-fixed-same-parent-original-staging-journal-names")
        original = file_record(raw,13350)
        mirror_present,partial = raw[13842],raw[13843]
        need(mirror_present in (0,1) and partial in (0,1), "po-input-exact-flags")
        mirror = file_record(raw,13439) if mirror_present else None
        need(mirror_present or not any(raw[13439:13528]), "po-absent-mirror-zero-file-record")
        external,private = file_record(raw,13528),file_record(raw,13617)
        need(external["size"] == private["size"] and external["sha256"] == private["sha256"] and
             external["identity"] != private["identity"], "po-exact-independent-private-pack-copy")
        self.match_file(snap,"input.exrpack",external)
        pack_raw = self.match_file(snap,private_pack,private)
        need(pack_raw == self.custody_raw(snap,"input.exrpack"), "po-private-copy-original-pack-bytes")
        pack = legacy_pack(pack_raw)
        need(len({b["legacy_id"] for b in pack["books"]}) == len(pack["books"]) and
             len({n["legacy_id"] for n in pack["notes"]}) == len(pack["notes"]),
             "po-input-pack-unique-original-records")
        books = {b["legacy_id"] for b in pack["books"]}
        notes = {n["legacy_id"] for n in pack["notes"]}
        if snap["folder"] == "actual-full-seed-and-next-generation":
            need(books == self.material["book_ids"] and notes == self.material["note_ids"] and partial == 1,
                 "po-real-full-five-kind-sixteen-note-original-pack")
        else:
            need(books == {"b-txt"} and notes == {n for n in self.material["note_ids"] if n.startswith("n-txt-")} and
                 partial == int(snap["folder"] == "actual-absent-mirror"), "po-real-txt-pack-and-explicit-partial-policy")
        txt = next(b for b in pack["books"] if b["legacy_id"] == "b-txt")["file"]
        need(txt["present"] is True and
             pack_raw[txt["offset"]:txt["offset"]+txt["size"]] == self.material["txt"],
             "po-pack-original-txt-qualified-source-bytes")
        staged = [native_id(raw,13706+16*k) for k in range(2)]
        jid = native_id(raw,13738)
        need(all(value[1] > 0 for value in [*staged,jid]) and len(set([*staged,jid])) == 3,
             "po-reserved-stage-and-journal-native-objects")
        need(journal in snap["custody"] and snap["custody"][journal]["directory"] and
             observed_id(snap["custody"][journal]) == jid, "po-journal-actual-fd-identity")
        grant = dict(generation=u64(raw,13754),seal=digest_field(raw,13762),target=native_id(raw,13826))
        origin = envelope["origin"]
        need(grant["generation"] == origin["generation"] and grant["seal"] == origin["grant"] and
             grant["target"] == origin["target"] == original["identity"] and
             envelope["generation"] == grant["generation"]+1, "po-original-input-exact-prior-native-grant")
        snapshot_rows = [("library.sqlite",original)]
        if mirror is not None:
            snapshot_rows.append(("mirror.json",mirror))
        snapshot_rows.append(("pack.exrpack",external))
        bd = "EXRWC-BIND1\n"+"".join(k+"="+fields[k]+"\n" for k,_ in BIND_FIELDS)
        snapshot_text = f"EXRWC-SNAP1 {sha(bd.encode())} {len(snapshot_rows)}\n"
        content_text = f"EXRWC-CONTENT1 {len(snapshot_rows)}\n"
        for path,file in snapshot_rows:
            line = f"f {file['size']} {file['sha256']} {path}\n"
            snapshot_text += struct.pack("<QQ",*file["identity"]).hex()+"0"*16+" "+line
            content_text += line
        return dict(raw=raw,sha256=sha(raw),binding=fields,gates=gates,manifest=manifest_raw,
                    manifest_sha256=sha(manifest_raw),token=token,stages=stages,retained=retained,
                    journal=journal,private_pack=private_pack,original=original,mirror=mirror,
                    source_pack=external,private=private,staged=staged,journal_identity=jid,
                    original_grant=grant,pack=pack,pack_raw=pack_raw,
                    snapshot_sha256=sha(snapshot_text.encode()),content_sha256=sha(content_text.encode()))

    def prepared(self,record,inp):
        if record is None:
            return None
        raw = record["payload"]
        need(len(raw) == 251 and raw[:8] == b"PC02OUT1" and
             padded(raw,8,65) == inp["sha256"], "po-prepared-251-exact-original-input")
        out = [file_record(raw,73+89*k) for k in range(2)]
        need(all(r["size"] > 0 and r["identity"] == inp["staged"][k] for k,r in enumerate(out)),
             "po-prepared-exact-reserved-native-stage-identities")
        return out

    def members(self,snap,inp,prepared):
        targets = ("library.sqlite","library.sqlite.legacy-map.json")
        statuses = []
        old_raw,new_raw = [],[]
        for k,target in enumerate(targets):
            original = inp["original"] if k == 0 else inp["mirror"]
            stage,retained = inp["stages"][k],inp["retained"][k]
            objects = snap["custody"]
            has_target,has_stage,has_retained = [name in objects for name in (target,stage,retained)]
            if has_stage:
                need(observed_id(objects[stage]) == inp["staged"][k], "po-retained-reservation-stage-native-id")
            if has_target and prepared is not None and observed_id(objects[target]) == prepared[k]["identity"]:
                need(not has_stage and has_retained == (original is not None),
                     "po-published-member-exact-stage-absence-and-original-custody")
                new = self.match_file(snap,target,prepared[k])
                old = self.match_file(snap,retained,original) if original is not None else None
                state = 2
            elif has_retained:
                need(original is not None and not has_target and has_stage and prepared is not None,
                     "po-between-two-native-renames-exact-member-state")
                old = self.match_file(snap,retained,original)
                new = self.match_file(snap,stage,prepared[k])
                state = 1
            else:
                need(has_target == (original is not None) and has_stage,
                     "po-unpublished-member-original-and-stage-no-overwrite")
                old = self.match_file(snap,target,original) if original is not None else None
                new = self.match_file(snap,stage,prepared[k]) if prepared is not None else self.custody_raw(snap,stage)
                state = 0
            statuses.append(state)
            old_raw.append(old)
            new_raw.append(new)
        if prepared is not None:
            proof = sqlite_content(new_raw[0],new_raw[1],inp["pack"],self.material["txt"])
            self.preserved_rows(old_raw[0],new_raw[0])
            if old_raw[1] is not None:
                old_ledger,new_ledger = json_value(old_raw[1]),json_value(new_raw[1])
                for name,key in (("books","legacy_id"),("notes","legacy_id")):
                    mapped = {r[key]:r for r in new_ledger[name]}
                    need(all(mapped.get(r[key]) == r for r in old_ledger[name]),
                         "po-original-ledger-records-preserved:"+name)
            need(sha(inp["pack_raw"]) in json_value(new_raw[1])["packs"],
                 "po-actual-original-pack-accounted-in-new-ledger")
        else:
            proof = None
        seed = snap["custody"].get("seed.exrpack")
        if seed is not None:
            seed_raw = self.custody_raw(snap,"seed.exrpack")
            seed_pack = legacy_pack(seed_raw)
            need({b["legacy_id"] for b in seed_pack["books"]} == {"unrelated"} and
                 {n["legacy_id"] for n in seed_pack["notes"]} == {"untouched-note"},
                 "po-real-independent-original-seed-pack")
            item = seed_pack["books"][0]["file"]
            need(seed_raw[item["offset"]:item["offset"]+item["size"]] ==
                 self.material["txt"].replace(b"Alpha",b"Omega"),
                 "po-original-unrelated-book-qualified-bytes")
            need(old_raw[1] is not None, "po-seeded-original-mirror-retained")
            sqlite_content(old_raw[0],old_raw[1],seed_pack)
            if prepared is not None:
                sqlite_content(new_raw[0],new_raw[1],seed_pack)
        return dict(statuses=statuses,old=old_raw,new=new_raw,content=proof)

    @staticmethod
    def preserved_rows(old,new):
        need(old is not None and new is not None, "po-actual-old-and-new-sqlite-bytes")
        connections = []
        try:
            tables = []
            for raw in (old,new):
                db = sqlite3.connect(":memory:")
                connections.append(db)
                db.deserialize(raw)
                db.execute("PRAGMA trusted_schema=OFF")
                db.execute("PRAGMA query_only=ON")
                need(db.execute("PRAGMA integrity_check").fetchall() == [("ok",)] and
                     db.execute("PRAGMA application_id").fetchone() == (1163416131,) and
                     db.execute("PRAGMA user_version").fetchone() == (7,),
                     "po-old-new-actual-sqlite-integrity-schema")
                names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                result = {}
                for name in TABLES:
                    if name in names:
                        result[name] = db.execute('SELECT * FROM "'+name+'"').fetchall()
                tables.append(result)
            need("books" in tables[0] and "notes" in tables[0], "po-original-book-note-tables")
            for name,rows in tables[0].items():
                need(name in tables[1] and all(r in tables[1][name] for r in rows),
                     "po-original-row-tuples-preserved:"+name)
            return tables[0],tables[1]
        finally:
            for db in connections:
                db.close()

    def acknowledgements(self,snap,inp):
        prefix = snap["cp"]+"/"+inp["journal"]+"/"
        entries = {}
        temporary = []
        for path,row in snap["custody"].items():
            if posixpath.dirname(path) != inp["journal"]:
                continue
            name = posixpath.basename(path)
            if name.startswith("ack-"):
                need(re.fullmatch(r"ack-[0-9]{3}",name) is not None, "po-all-final-ack-names")
                number = int(name[4:])
                need(number not in entries, "po-no-duplicate-actual-ack-ordinal")
                entries[number] = dict(path=self.runtime+snap["cp"]+"/"+path,
                                       observed=self.normalize(row,path))
            else:
                match = re.fullmatch(r"\.pending-([0-9]+)-([0-9]+)",name)
                need(match is not None and 0 < int(match[1]) < 2**31 and
                     0 < int(match[2]) < 2**32, "po-only-bounded-unpromoted-ack-temporaries")
                # A complete temporary still has to identify its own actual inode.
                raw = self.custody_raw(snap,path)
                need(len(raw) >= 360 and raw[:8] == b"PC02ACK1", "po-retained-complete-temp-wire")
                ordinal = u64(raw,24)
                observed = self.normalize(row,f"ack-{ordinal:03d}")
                record = native_ack(raw,f"ack-{ordinal:03d}",observed,self.euid)
                need(record["input"] == inp["sha256"] and record["manifest"] == inp["manifest_sha256"],
                     "po-retained-temp-exact-input-and-manifest")
                temporary.append(dict(name=name,record=record,raw=raw,observed=row))
        return entries,temporary,self.runtime+prefix

    def transaction(self,snap,role,prebegin=False):
        ar,rn = snap["authority"],snap["route"]
        ss = snap["states"]
        if prebegin:
            need(len(ss) == 1 and ss[0]["kind"] == "I" and snap["admitted"],
                 "po-before-pending-original-clean-only")
            names = [p for p in ar if posixpath.dirname(p) == rn and
                     posixpath.basename(p).startswith("input-")]
            need(len(names) == 1, "po-single-prebegin-immutable-input")
            name = names[0]
            envelope = metadata_envelope(self.raw(snap["ap"]+"/"+name),posixpath.basename(name),
                                         ar[name],self.euid)
            need(envelope["origin_raw"] == snap["binding_raw"] and envelope["generation"] == 1,
                 "po-prebegin-input-bound-to-original-grant")
            hname = head_name(envelope["generation"],envelope["input"])
            head = committed_head(self.raw(snap["ap"]+"/"+rn+"/"+hname),hname,ar[rn+"/"+hname],self.euid)
            need(head["count"] == 0 and head["identity"] == envelope["head_identity"] and
                 head["origin_raw"] == envelope["origin_raw"], "po-prebegin-empty-registered-head")
            inp = self.decode_input(snap,envelope,role)
            acks,temporary,prefix = self.acknowledgements(snap,inp)
            need(not acks and not temporary and not any(posixpath.basename(p).startswith(("prepared-","floor-"))
                 for p in ar), "po-prebegin-no-journal-or-prepared-floor-authority")
            members = self.members(snap,inp,None)
            need(members["statuses"] == [0,0] and all(not v for v in members["new"]),
                 "po-before-pending-reserved-stages-empty")
            tx = dict(generation=1,input=envelope["input"],manifest=inp["manifest_sha256"],
                      input_record=envelope,prepared_record=None,floors=[],floor=dict(count=0),
                      head=head,acknowledgements=[],unfloored_ack_count=0,needs_head_confirm=False)
        else:
            last = ss[-1]
            need(last["kind"] in ("B","C"), "po-current-real-transaction-state")
            begin = ss[-1] if last["kind"] == "B" else ss[-2]
            exact = {k:begin[k] for k in ("generation","seal","manifest","input")}
            name = final_name(1,exact["generation"],exact["input"])
            envelope = metadata_envelope(self.raw(snap["ap"]+"/"+rn+"/"+name),name,ar[rn+"/"+name],self.euid)
            inp = self.decode_input(snap,envelope,role)
            acks,temporary,prefix = self.acknowledgements(snap,inp)
            tx = audit_transaction(self.files,ar,current_binding=snap["binding_raw"],
                  raw_state=snap["state_raw"],exact=exact,euid=self.euid,library_path=snap["library"],
                  parent=snap["parent"],authority_prefix=self.runtime+snap["ap"]+"/",
                  profile="production-native-ack",acknowledgements=acks,expected_source=self.source,
                  acknowledgement_prefix=prefix)
            need(inp["manifest_sha256"] == exact["manifest"] and inp["sha256"] == exact["input"],
                 "po-input-actual-manifest-and-pending-seals")
            need(all(t["record"]["pending"] == exact["seal"] for t in temporary),
                 "po-unpromoted-temp-exact-pending-seal")
            prepared = self.prepared(tx["prepared_record"],inp)
            members = self.members(snap,inp,prepared)
        lines = [a["line"] for a in tx["acknowledgements"]]
        journal = history(lines,self.source)
        if lines:
            need(lines[0] == inp["manifest"], "po-actual-ack-manifest-exact-input-binding")
            need(journal["lease"] in ("-",inp["token"]) and journal["stage"] in ("-",inp["token"]),
                 "po-real-owner-journal-lease-and-stage-token")
            if journal["snapshot"] != "-":
                need(journal["snapshot"] == inp["snapshot_sha256"], "po-journal-actual-original-native-snapshot")
            if journal["content"] != "-":
                need(journal["content"] == inp["content_sha256"], "po-journal-actual-original-content-digest")
        if not prebegin and snap["states"][-1]["kind"] == "C":
            need(journal["event"] == 12 and journal["committed"] != journal["aborted"],
                 "po-clean-only-after-exact-journal-terminal")
            need(members["statuses"] == ([2,2] if journal["committed"] else [0,0]),
                 "po-clean-exact-pair-commit-or-original-abort")
            need(snap["states"][-1]["target"] == (self.prepared(tx["prepared_record"],inp)[0]["identity"]
                 if journal["committed"] else inp["original"]["identity"]),
                 "po-clean-native-target-exact-terminal-proof")
        self.transactions += 1
        return dict(native=tx,input=inp,members=members,journal=journal,temporary=temporary,lines=lines)

    def process(self,folder,phase,sequence=None,member=None,require_cap=False):
        row = self.json("cases/"+folder+"/process-observation.json")
        need(row["phase"] == phase and row["sequence"] == sequence and row["member"] == member and
             row["require_cap"] is require_cap and row["ready_hex"] == "72" and
             row["observer_pid"] == self.observer and row["observer_uid"] == row["observer_euid"] == self.euid and
             row["owner_uid"] == self.euid and integer(row["owner_pid"]) and row["owner_pid"] > 0 and
             row["owner_pid"] != self.observer and row["kill_signal"] == 9 and
             row["wait_returncode"] == row["final_returncode"] == -9,
             "po-actual-process-barrier-pipe-and-sigkill")
        need(row["ps_command"] == ["ps","-axo","pid=,ppid=,uid="] and row["ps_exit"] == 0 and
             row["ps_stderr"] == "", "po-raw-process-table-command")
        table = []
        for line in row["ps_stdout"].splitlines():
            values = line.split()
            need(len(values) == 3 and all(re.fullmatch("[0-9]+",v) for v in values),
                 "po-raw-process-table-numeric-rows")
            table.append(tuple(map(int,values)))
        need(len({p[0] for p in table}) == len(table) and
             [p for p in table if p[0] == row["owner_pid"]] ==
             [(row["owner_pid"],self.observer,self.euid)] and
             not any(p[1] == row["owner_pid"] for p in table),
             "po-live-owner-native-uid-and-no-orphan-workers")
        stdout = self.raw("cases/"+folder+"/process.stdout").decode("utf-8")
        need(stdout == row["barrier_stdout"], "po-original-barrier-stdout-bytes")
        events = [json_value(line.encode()) for line in stdout.splitlines() if line]
        barriers = [e for e in events if "barrier" in e]
        need(len(barriers) == 1 and barriers[0]["barrier"] == phase and
             type(barriers[0]["sequence"]) is int and barriers[0]["sequence"] >= 0 and
             type(barriers[0]["member"]) is int and barriers[0]["member"] in (0,1) and
             (sequence is None or barriers[0]["sequence"] == sequence) and
             (member is None or barriers[0]["member"] == member),
             "po-original-deterministic-barrier-exact-phase-sequence-member")
        row["actual_barrier"] = barriers[0]
        return row

    def same_custody(self,before,after):
        need(before["parent"]["device"] == after["parent"]["device"] and
             before["parent"]["inode"] == after["parent"]["inode"] and
             before["authority_path"] == after["authority_path"] and
             before["route"] == after["route"], "po-recovery-same-native-route-parent")
        for path in ("authority","registry.lock",before["route"]+"/lease",before["route"]+"/state"):
            need(observed_id(before["authority"][path]) == observed_id(after["authority"][path]),
                 "po-recovery-preserves-native-lock-state-objects")
        need(after["state_raw"].startswith(before["state_raw"]), "po-state-history-never-rewritten-or-truncated")
        for path,row in before["authority"].items():
            name = posixpath.basename(path)
            if name.startswith(("input-","prepared-","floor-")):
                need(path in after["authority"] and observed_id(row) == observed_id(after["authority"][path]) and
                     self.raw(before["ap"]+"/"+path) == self.raw(after["ap"]+"/"+path),
                     "po-write-once-transaction-original-records-retained")
        for path,row in before["custody"].items():
            if "/ack-" in path or "/.pending-" in path:
                need(path in after["custody"] and observed_id(row) == observed_id(after["custody"][path]) and
                     self.custody_raw(before,path) == self.custody_raw(after,path),
                     "po-original-complete-acks-and-uncommitted-temporaries-retained")

    def cut(self,name,folder,phase,sequence=None,member=None,require_cap=False,special=None):
        process = self.process(folder,phase,sequence,member,require_cap)
        paused = self.snapshot(folder,"paused")
        final = self.snapshot(folder,"final")
        before = self.transaction(paused,"test_tool",phase == 900)
        after = self.transaction(final,"test_tool",phase == 900)
        self.same_custody(paused,final)
        need(before["input"]["raw"] == after["input"]["raw"], "po-fresh-recovery-original-immutable-input")
        target,pack = paused["library"],paused["parent_path"]+"/input.exrpack"
        checks = self.find(folder,"admission",["check",target])
        need([r["exit"] for r in checks] == [2,0 if paused["admitted"] else 2,0],
             "po-live-refusal-postdeath-exact-grant-and-final-reader-admission")
        recoveries = self.find(folder,"tool",["recover",target],0)
        need(len(recoveries) == 1 and recoveries[0]["pid"] != process["owner_pid"],
             "po-fresh-process-recovery-not-original-capability")
        recovery = recoveries[0]
        self.find(folder,"guarded",["verify","--pack",paused["parent_path"]+"/seed.exrpack","--target",target],0)
        publish_intent = before["journal"]["publish_intent"]
        if phase == 900:
            need(final["state_raw"] == paused["state_raw"] and final["binding_raw"] == paused["binding_raw"] and
                 json_value(recovery["stdout"].encode())["status"] == "registered_clean_without_pending",
                 "po-before-begin-orphan-metadata-never-becomes-live-transaction")
        else:
            need(final["admitted"] and final["states"][-1]["kind"] == "C" and
                 after["journal"]["committed"] is publish_intent and
                 after["journal"]["aborted"] is (not publish_intent),
                 "po-fresh-recovery-branch-only-complete-actual-ack-publish-intent")
        if publish_intent:
            self.find(folder,"tool",["verify",target,pack],0)
            need(after["members"]["statuses"] == [2,2] and after["members"]["content"] is not None,
                 "po-recovered-two-member-actual-content")
        else:
            self.find(folder,"tool",["verify",target,pack],2)
            need(self.custody_raw(final,"library.sqlite") == before["members"]["old"][0] and
                 after["members"]["statuses"] == [0,0], "po-no-intent-exact-original-db-bytes")
            if before["members"]["old"][1] is not None:
                need(self.custody_raw(final,"library.sqlite.legacy-map.json") == before["members"]["old"][1],
                     "po-no-intent-exact-original-mirror-bytes")
        n = len(before["lines"])
        f,h = before["native"]["floor"]["count"],before["native"]["head"]["count"]
        if phase in (900,901,1101,1102):
            need(n == f == h == 0 and before["members"]["statuses"] == [0,0] and
                 all(not data for data in before["members"]["new"]), "po-before-import-empty-journal-and-stages")
        expected_count = {902:4,903:6,904:8,905:10,906:10,907:13,908:13,
                          1201:13,1202:13,1203:13,1204:13,1205:13,1301:10,1302:10}
        if phase in expected_count:
            need(n == f == h == expected_count[phase], "po-real-barrier-original-canonical-history-count")
        if phase == 903:
            sqlite_content(before["members"]["new"][0],before["members"]["new"][1],
                           before["input"]["pack"],self.material["txt"])
            self.preserved_rows(before["members"]["old"][0],before["members"]["new"][0])
        if phase == 904:
            need(before["native"]["prepared_record"] is not None and before["members"]["statuses"] == [0,0],
                 "po-prepared-before-publish-intent")
        if phase == 905:
            need(before["members"]["statuses"] == [2,0], "po-only-db-member-published")
        if phase in (906,907,908,1201,1202,1203,1204,1205):
            need(before["members"]["statuses"] == [2,2], "po-both-members-published-before-terminal")
        if phase in (1301,1302):
            expected = ([1,0] if phase == 1301 else [2,0]) if member == 0 else (
                        [2,1] if phase == 1301 else [2,2])
            need(before["members"]["statuses"] == expected, "po-exact-cut-between-native-member-renames")
        if phase in (1101,1102):
            need(paused["states"][-1]["kind"] == "B", "po-durable-pending-before-capability")
        if phase in (1201,1202,1203):
            need(paused["states"][-1]["kind"] == "C" and not paused["admitted"],
                 "po-clean-record-before-binding-still-refuses-reader")
        if phase in (1204,1205,908):
            need(paused["states"][-1]["kind"] == "C" and paused["admitted"],
                 "po-exact-clean-binding-only-postdeath-admission")
        if phase == 1402:
            need(n == f == 1 and h == 0 and before["native"]["needs_head_confirm"] and require_cap,
                 "po-complete-floor-before-head-independent-proof")
        if phase == 1501:
            need(n == f == h == 1 and not before["native"]["needs_head_confirm"],
                 "po-complete-head-record-before-fsync")
        if phase in (1601,1602):
            need(n == f == h == process["actual_barrier"]["sequence"] and len(before["temporary"]) == 1,
                 "po-complete-uncommitted-ack-temp-not-final")
        if phase in (1603,1604):
            need(n == process["actual_barrier"]["sequence"]+1 and f == h == n-1,
                 "po-complete-final-ack-before-floor")
        if special == "temp-intent":
            tmp = before["temporary"][0]["record"]["line"]
            need(tmp.startswith(b"EXRWH2 ") and int(tmp.split(b" ")[2]) == 9 and
                 not publish_intent and after["journal"]["aborted"], "po-temp-event-nine-never-promoted")
            need(all(r["file_sha256"] != before["temporary"][0]["record"]["file_sha256"]
                 for r in after["native"]["acknowledgements"]), "po-temp-not-reused-as-final-ack")
        if special == "ack-intent":
            need(publish_intent and before["lines"][-1].split(b" ")[2] == b"9" and n == f+1 and
                 after["journal"]["committed"], "po-full-final-event-nine-counted-without-floor")
        self.case_details.append(dict(name=name,phase=phase,sequence=sequence,member=member,
             original_owner_pid=process["owner_pid"],fresh_recovery_pid=recovery["pid"],
             uid=self.euid,paused_ack_count=n,paused_floor=f,paused_head=h,
             actual_publish_intent=publish_intent,recovery="commit" if publish_intent else
             ("unstarted" if phase == 900 else "abort"),final_admitted=final["admitted"]))

    def normal(self,folder):
        first = self.snapshot(folder,"generation-1")
        second = self.snapshot(folder,"generation-2")
        a,b = self.transaction(first,"tool"),self.transaction(second,"tool")
        self.same_custody(first,second)
        need(first["admitted"] and second["admitted"] and
             a["journal"]["committed"] and b["journal"]["committed"] and
             a["native"]["generation"] == 1 and b["native"]["generation"] == 2 and
             a["members"]["statuses"] == b["members"]["statuses"] == [2,2] and
             b["members"]["old"] == a["members"]["new"] and
             self.preserved_rows(a["members"]["new"][0],b["members"]["new"][0])[0] ==
             self.preserved_rows(a["members"]["new"][0],b["members"]["new"][0])[1],
             "po-two-real-native-generations-idempotent-content-originals-retained")
        if folder == "actual-absent-mirror":
            need(a["input"]["mirror"] is None and a["members"]["old"][1] is None,
                 "po-explicit-create-absent-mirror-first-publication")
        else:
            need(a["input"]["mirror"] is not None, "po-existing-original-mirror-present")
        target,pack = first["library"],first["parent_path"]+"/input.exrpack"
        self.find(folder,"tool",["migrate",target,pack,"--allow-partial"],0)
        need(len(self.find(folder,"tool",["migrate",target,pack,"--allow-partial"])) == 2,
             "po-two-actual-owner-invocations")
        self.find(folder,"tool",["verify",target,pack],0)
        self.find(folder,"admission",["check",target],0)
        self.case_details.append(dict(name=folder,generations=2,actual_content=a["members"]["content"],
                                      original_rows_preserved=True,final_admitted=True))
        return a

    def unregistered(self):
        folder = "unregistered-never-auto-adopted"
        final = self.snapshot(folder,"final")
        tx = self.transaction(final,"tool")
        target,pack = final["library"],final["parent_path"]+"/input.exrpack"
        rows = self.rows(folder)
        refused = self.find(folder,"tool",["migrate",target,pack],2)
        need(len(refused) == 2 and [r["exit"] for r in refused] == [2,0],
             "po-ordinary-owner-refuses-unknown-before-explicit-enroll")
        self.find(folder,"guarded",["dump","--target",target],2)
        enroll = self.find(folder,"admission",["enroll",target],0)
        need(len(enroll) == 1 and rows.index(refused[0]) < rows.index(enroll[0]) < rows.index(refused[1]) and
             final["admitted"] and tx["journal"]["committed"] and tx["members"]["statuses"] == [2,2],
             "po-explicit-enrollment-precedes-successful-real-owner")
        seed = legacy_pack(self.custody_raw(final,"seed.exrpack"))
        sqlite_content(tx["members"]["old"][0],tx["members"]["old"][1],seed)
        self.case_details.append(dict(name=folder,ordinary_unknown_refusal=True,explicit_enroll=True,
                                      original_rows_preserved=True,final_admitted=True))

    def guard(self):
        folder = "all-old-write-commands-disabled"
        snap = self.snapshot(folder,"final")
        need(snap["admitted"] and len(snap["states"]) == 1 and snap["states"][0]["kind"] == "I",
             "po-old-cli-never-begins-native-migration")
        need(not any(posixpath.basename(p).startswith(("input-","prepared-","floor-","commit-head-"))
             for p in snap["authority"]), "po-old-cli-no-protected-transaction-effects")
        target,pack = snap["library"],snap["parent_path"]+"/input.exrpack"
        rows = self.rows(folder)
        for name in OLD_NAMES:
            for command in ("migrate","recover-mirror","recover-migration"):
                found = [r for r in rows if posixpath.basename(r["command"][0]) == name and
                    self.binary_map[r["command"][0]][0] == "guarded" and r["command"][1:] ==
                    [command,"--target",target,"--pack",pack,"--break-lock"]]
                need(len(found) == 1 and found[0]["exit"] == 2 and
                     "c02-owner-required" in found[0]["stdout"], "po-every-old-write-and-break-lock-refused")
            found = [r for r in rows if posixpath.basename(r["command"][0]) == name and
                self.binary_map[r["command"][0]][0] == "guarded" and
                r["command"][1:] == ["dump","--target",target,"--report",target]]
            need(len(found) == 1 and found[0]["exit"] == 2,
                 "po-all-old-report-target-write-shortcuts-refused")
        self.find(folder,"guarded",["dump","--target",target],0)
        seed = legacy_pack(self.custody_raw(snap,"seed.exrpack"))
        sqlite_content(self.custody_raw(snap,"library.sqlite"),
                       self.custody_raw(snap,"library.sqlite.legacy-map.json"),seed)
        self.case_details.append(dict(name=folder,write_commands_refused=9,report_overwrite_refused=3,
                                      actual_original_content=True,final_admitted=True))

    def bad_ack(self,kind,publish_ordinal):
        folder = "actual-ACK-refuse-"+kind
        ordinal = publish_ordinal if kind == "old-valid-tip" else 2
        process = self.process(folder,1605,ordinal)
        paused = self.snapshot(folder,"paused")
        refused = self.snapshot(folder,"refused")
        tx = self.transaction(paused,"test_tool")
        need(len(tx["lines"]) == tx["native"]["floor"]["count"] == tx["native"]["head"]["count"] == ordinal and
             paused["states"][-1]["kind"] == refused["states"][-1]["kind"] == "B" and
             not paused["admitted"] and not refused["admitted"], "po-contradiction-starts-from-live-exact-protected-prefix")
        need(set(paused["authority"]) == set(refused["authority"]), "po-refusal-no-authority-object-created-or-removed")
        for path,row in paused["authority"].items():
            later = refused["authority"][path]
            for key in ("device","inode","uid","gid","links","mode","raw_mode","directory","bytes","sha256"):
                need(row[key] == later[key], "po-refusal-preserves-all-protected-native-fields")
            if not row["directory"]:
                need(self.raw(paused["ap"]+"/"+path) == self.raw(refused["ap"]+"/"+path),
                     "po-refusal-preserves-all-actual-authority-bytes")
        inp = tx["input"]
        selected = ordinal if kind in ("old-valid-tip","same-bytes-new-ID") else 1
        ack_name = f"ack-{selected:03d}"
        path = inp["journal"]+"/"+ack_name
        retained = "retained-original-"+ack_name
        old = self.custody_raw(paused,path)
        need(self.custody_raw(refused,retained) == old and
             observed_id(refused["custody"][retained]) == observed_id(paused["custody"][path]),
             "po-attack-original-ack-native-object-retained")
        if kind in ("hole","old-valid-tip"):
            need(path not in refused["custody"], "po-attack-removes-exact-complete-ack")
        else:
            new = self.custody_raw(refused,path)
            need(observed_id(refused["custody"][path]) != observed_id(paused["custody"][path]),
                 "po-same-named-replacement-has-actual-different-native-id")
            if kind == "same-bytes-new-ID":
                need(new == old, "po-same-bytes-new-id-control-is-exact-byte-copy")
            else:
                need(len(new) == len(old) and new[:96] == old[:96] and new[97:-64] == old[97:-64] and
                     new[96] in b"ab" and new[96] != old[96] and new[-64:] == sha(new[:-64]).encode(),
                     "po-resealed-wrong-input-tuple-control")
        for path,row in paused["custody"].items():
            if row["directory"] or path == inp["journal"]+"/"+ack_name:
                continue
            need(path in refused["custody"] and
                 observed_id(row) == observed_id(refused["custody"][path]) and
                 self.custody_raw(paused,path) == self.custody_raw(refused,path),
                 "po-failed-recovery-preserves-every-other-source-object")
        # The unchanged floor/head is checked against the actual contradictory
        # ACK namespace. Do not substitute the retained original ACK's fstat.
        failure = None
        try:
            self.transaction(refused,"test_tool")
        except ValueError as error:
            failure = str(error)
        expected = {"same-bytes-new-ID":{"pm-ack-name-size-actual-self-id"},
                    "wrong-input-tuple":{"pm-ack-name-size-actual-self-id",
                                         "pm-every-complete-ack-original-transaction"},
                    "hole":{"pm-complete-actual-ack-inventory"},
                    "old-valid-tip":{"pm-floor-cannot-exceed-real-ack-prefix"}}
        need(failure in expected[kind], "po-independent-exact-ack-contradiction-rejected")
        target = paused["library"]
        recovery = self.find(folder,"tool",["recover",target],2)
        need(len(recovery) == 1 and recovery[0]["pid"] != process["owner_pid"],
             "po-contradiction-refused-by-fresh-independent-owner")
        checks = self.find(folder,"admission",["check",target])
        need([r["exit"] for r in checks] == [2,2], "po-contradiction-remains-reader-pending")
        self.case_details.append(dict(name=folder,original_owner_pid=process["owner_pid"],
             fresh_recovery_pid=recovery[0]["pid"],protected_count=ordinal,
             contradiction=failure,all_original_authority_bytes_retained=True,final_admitted=False))


def audit_posix_owner(files,spec,source,git_bytes):
    evidence = relative(spec["evidence_prefix"],True)
    runtime = relative(spec["runtime_prefix"],True)
    need(spec["role"] in ("posix-migration-linux","posix-migration-macos") and
         hexadecimal(source,40) and source != "0"*40, "po-explicit-qualified-desktop-role")
    material = qualified_material(files,evidence,source,git_bytes)
    inventory_count = audit_inventory(files,runtime)
    historical = historical_report(files,runtime,evidence,material)
    audit = OwnerAudit(files,spec,source,material)
    full = audit.normal("actual-full-seed-and-next-generation")
    audit.normal("actual-absent-mirror")
    audit.unregistered()
    audit.guard()
    publish_ordinal = next((a["count"] for a in full["native"]["acknowledgements"]
                          if a["line"].startswith(b"EXRWH2 ") and a["line"].split(b" ")[2] == b"9"),None)
    need(type(publish_ordinal) is int and publish_ordinal > 2, "po-real-publish-intent-event-ordinal")
    for point in POINTS:
        audit.cut("process-kill-"+str(point),f"process-kill-{point}-any",point)
    for member in (0,1):
        for point in (1301,1302):
            audit.cut(f"process-kill-{point}-member-{member}",
                      f"process-kill-{point}-any-m{member}",point,member=member)
    audit.cut("complete-FLOOR-before-head","process-kill-1402-0",1402,0,require_cap=True)
    audit.cut("complete-head-before-fsync","process-kill-1501-0",1501,0)
    audit.cut("uncommitted-publish-intent-temp-never-promoted",
              f"process-kill-1602-{publish_ordinal-1}",1602,publish_ordinal-1,special="temp-intent")
    audit.cut("complete-publish-intent-ACK-counted-before-floor",
              f"process-kill-1603-{publish_ordinal-1}",1603,publish_ordinal-1,special="ack-intent")
    for kind in ("same-bytes-new-ID","wrong-input-tuple","hole","old-valid-tip"):
        audit.bad_ack(kind,publish_ordinal)
    rows = audit.receipt["results"]
    expected = [r["name"] for r in audit.case_details]
    need(len(expected) == len(set(expected)) == 36 and audit.receipt["cases"] == 36 and
         audit.receipt["failed"] == 0 and isinstance(rows,list) and len(rows) == 36 and
         [r["name"] for r in rows] == expected and all(r["passed"] is True for r in rows),
         "po-all-36-actual-named-scenarios-preserved")
    need(audit.used_observations == set(audit.observed), "po-all-native-source-observations-accounted")
    expected_folders = {p for p,_ in audit.snapshots}
    need({p.removeprefix("cases/") for p in audit.commands if p.startswith("cases/")} == expected_folders,
         "po-all-actual-case-command-folders-accounted")
    need(audit.receipt["partial_state_head_repair"] is False, "po-first-batch-repair-not-yet-qualified")
    return dict(actual_owner=True,actual_migration=True,production_native_ack=True,
        profile="production-native-ack",ack_header_bytes=296,floor_payload_bytes=352,
        input_payload_bytes=13844,prepared_payload_bytes=251,payload_semantics_verified=True,
        journal_bound=True,source=source,provider=material["provider"],euid=audit.euid,
        installed_owner_sha256=audit.binary_hash["tool"],
        controls_sha256=audit.binary_hash["test_tool"],runtime_files=inventory_count,
        native_fstat_objects=len(audit.observations),phase_snapshots=len(audit.snapshots),
        actual_cases=36,historical_cases=historical["cases"],historical_checks=historical["checks"],
        transactions_audited=audit.transactions,power_loss=False,partial_state_head_repair=False,
        missing=["posix-partial-state-and-head-explicit-repair"],
        cases=audit.case_details)


def posix_owner_negative_controls(files,spec,source,git_bytes,output):
    """Write eight restorable, original-ZIP-bound patches and re-audit each.

    Replacements include every affected actual-observation copy and the runtime
    inventory. The patch archive supplies its own CRCs; its manifest binds the
    original artifact API identity and exact ZIP SHA. Each rejection below is
    obtained after reading that patch ZIP back and reconstructing the file set.
    """
    import json
    import pathlib
    import zipfile

    baseline = audit_posix_owner(files,spec,source,git_bytes)
    need(baseline["actual_cases"] == 36 and baseline["historical_cases"] == 65,
         "po-negative-original-positive-baseline")
    root = pathlib.Path(output)
    root.mkdir(parents=True,exist_ok=True)
    evidence,runtime = spec["evidence_prefix"],spec["runtime_prefix"]
    material = qualified_material(files,evidence,source,git_bytes)
    original = OwnerAudit(files,spec,source,material)
    receipt = original.receipt
    observed = original.observations
    results = []
    source_root = None

    def encoded(value):
        return (json.dumps(value,ensure_ascii=False,sort_keys=True,
                           separators=(",",":"))+"\n").encode("utf-8")

    def phase(folder,label):
        nonlocal source_root
        snap = original.snapshot(folder,label)
        source_root = original.home+"/"+runtime.rstrip("/")
        return snap

    def aliases(replacements,source_path,data):
        names = [r["artifact_path"] for r in observed if
                 r["source_path"] == source_path and not r["directory"]]
        need(names, "po-negative-real-source-aliases")
        for name in names:
            replacements[runtime+name] = data
        if source_root is not None and source_path.startswith(source_root+"/"):
            direct = runtime+source_path[len(source_root)+1:]
            if direct in files:
                replacements[direct] = data

    def envelope(raw,payload):
        need(raw[:8] == b"PC02M001" and len(raw) == 632+len(payload),
             "po-negative-exact-envelope-payload")
        value = bytearray(raw)
        value[568:-64] = payload
        value[488:552] = sha(payload).encode()
        value[-64:] = sha(value[:-64]).encode()
        return bytes(value)

    def sqlite_mutation(raw,sql,args):
        db = sqlite3.connect(":memory:")
        try:
            db.deserialize(raw)
            db.execute("PRAGMA trusted_schema=OFF")
            cursor = db.execute(sql,args)
            need(cursor.rowcount == 1, "po-negative-one-actual-sqlite-row")
            db.commit()
            need(db.execute("PRAGMA integrity_check").fetchall() == [("ok",)],
                 "po-negative-preserves-valid-sqlite")
            return db.serialize()
        finally:
            db.close()

    def reseal_outer(replacements,identities):
        # All historical cumulative observation arrays must continue to agree
        # with the final complete fstat inventory after a semantic mutation.
        changed = dict(replacements)
        for path,raw in files.items():
            if not path.startswith(runtime):
                continue
            leaf = posixpath.basename(path)
            if leaf != "native-source-observations.json" and not (
                    leaf.startswith("native-observations-") and leaf.endswith(".json")):
                continue
            rows = json_value(raw)
            touched = False
            for row in rows:
                if row["source_path"] in identities:
                    row.update(identities[row["source_path"]])
                    touched = True
                archive = runtime+row["artifact_path"]
                if not row["directory"] and archive in changed:
                    row["bytes"] = len(changed[archive])
                    row["sha256"] = sha(changed[archive])
                    touched = True
            if touched:
                changed[path] = encoded(rows)
        inventory = json_value(files[runtime+"file-hashes.json"])
        for row in inventory:
            path = runtime+row["path"]
            if path in changed:
                need("sha256" in row, "po-negative-replacement-is-regular-inventory-file")
                row["bytes"] = len(changed[path])
                row["sha256"] = sha(changed[path])
        changed[runtime+"file-hashes.json"] = encoded(inventory)
        return changed

    def check(name,replacements,expected,identities=None):
        changed = reseal_outer(replacements,identities or {})
        need(changed and all(path in files and isinstance(raw,bytes) for path,raw in changed.items()),
             "po-negative-only-original-member-replacements")
        patch_path = root/(name+".patch.zip")
        members = []
        manifest = dict(schema="pc02-owner-resealed-patch-v1",name=name,source=source,
                        role=spec["role"],original_artifact=spec["artifact"],
                        run=spec["run"],attempt=spec["attempt"],job=spec["job"],
                        expected_rejection=expected,removed=[],replacements=members)
        for index,path in enumerate(sorted(changed)):
            raw = changed[path]
            members.append(dict(path=path,member=f"replacement-{index:04d}.bin",
                                bytes=len(raw),sha256=sha(raw)))
        with zipfile.ZipFile(patch_path,"x",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            archive.writestr("patch.json",encoded(manifest))
            for entry in members:
                archive.writestr(entry["member"],changed[entry["path"]])
        # Use only bytes read back through the actual ZIP parser for the attack.
        reconstructed = dict(files)
        with zipfile.ZipFile(patch_path,"r") as archive:
            parsed = json_value(archive.read("patch.json"))
            need(parsed == manifest and parsed["original_artifact"]["sha256"] ==
                 spec["artifact"]["sha256"] and
                 set(archive.namelist()) == {"patch.json"}|{r["member"] for r in members} and
                 len(archive.namelist()) == len(members)+1,
                 "po-negative-patch-original-zip-binding-and-complete-inventory")
            for entry in parsed["replacements"]:
                relative(entry["path"])
                raw = archive.read(entry["member"])
                need(len(raw) == entry["bytes"] and sha(raw) == entry["sha256"],
                     "po-negative-patch-readback-crc-size-sha")
                reconstructed[entry["path"]] = raw
        failure = None
        try:
            audit_posix_owner(reconstructed,spec,source,git_bytes)
        except ValueError as error:
            failure = str(error)
        need(failure in expected, "po-negative-owner-semantic-rejection:"+name+":"+str(failure))
        patch_raw = patch_path.read_bytes()
        result = dict(name=name,rejected=True,rejection=failure,expected_rejection=expected,
                      original_zip_sha256=spec["artifact"]["sha256"],
                      patch=patch_path.name,patch_bytes=len(patch_raw),patch_sha256=sha(patch_raw),
                      replacements=len(changed),runtime_inventory_resealed=True,
                      actual_zip_readback=True,decoder="audit_posix_owner")
        (root/(name+".json")).write_bytes(encoded(result))
        results.append(result)

    # 1. A PID copied from the killed owner is never a fresh recovery process.
    folder = "process-kill-900-any"
    killed = original.json("cases/"+folder+"/process-observation.json")["owner_pid"]
    recovery_rows = [(path,json_value(raw)) for path,raw in files.items()
                     if path.startswith(runtime+"cases/"+folder+"/command-") and path.endswith(".json")]
    selected = [(path,row) for path,row in recovery_rows if row["command"][1:2] == ["recover"]]
    need(len(selected) == 1, "po-negative-single-real-recovery-command")
    path,row = selected[0]
    row["pid"] = killed
    check("fresh-recovery-reuses-killed-owner-pid",{path:encoded(row)},
          ["po-fresh-process-recovery-not-original-capability"])

    # 2. Re-seal the JSON while leaving the observed UID field unchanged: the
    # raw ps row independently contradicts that declaration.
    path = runtime+"cases/"+folder+"/process-observation.json"
    row = original.json("cases/"+folder+"/process-observation.json")
    table = row["ps_stdout"].splitlines()
    matches = [i for i,line in enumerate(table) if line.split() and int(line.split()[0]) == killed]
    need(len(matches) == 1, "po-negative-original-owner-ps-row")
    owner = table[matches[0]].split()
    owner[2] = str(original.euid+1)
    table[matches[0]] = " ".join(owner)
    row["ps_stdout"] = "\n".join(table)+"\n"
    check("raw-native-owner-uid-contradicts-declaration",{path:encoded(row)},
          ["po-live-owner-native-uid-and-no-orphan-workers"])

    # 3. An intact SQLite image with one old annotation deleted is not original
    # content preservation. At 903 there is no PREPARED yet to obscure this.
    snap = phase("process-kill-903-any","paused")
    tx = original.transaction(snap,"test_tool")
    stage = tx["input"]["stages"][0]
    modified = sqlite_mutation(original.custody_raw(snap,stage),
                               "DELETE FROM notes WHERE text=?",("original annotation",))
    replacements = {}
    aliases(replacements,snap["custody"][stage]["source_path"],modified)
    check("valid-sqlite-loses-original-annotation",replacements,
          ["po-original-row-tuples-preserved:notes"])

    # 4. Keep all original SQL rows, but remove the original annotation's ledger
    # record from both private SDK ledger and mirror, updating PREPARED seals.
    snap = phase("process-kill-904-any","paused")
    tx = original.transaction(snap,"test_tool")
    stages = tx["input"]["stages"]
    ledger = json_value(original.custody_raw(snap,stages[1]))
    old_count = len(ledger["notes"])
    ledger["notes"] = [n for n in ledger["notes"] if n["legacy_id"] != "untouched-note"]
    need(len(ledger["notes"])+1 == old_count, "po-negative-original-ledger-note-present")
    mirror = encoded(ledger)
    database = sqlite_mutation(original.custody_raw(snap,stages[0]),
                               "UPDATE exr_migration_ledger SET data=? WHERE id=1",(mirror,))
    replacements = {}
    for k,data in enumerate((database,mirror)):
        aliases(replacements,snap["custody"][stages[k]]["source_path"],data)
    prepared = tx["native"]["prepared_record"]
    pname = final_name(2,tx["native"]["generation"],tx["input"]["sha256"])
    ppath = snap["route"]+"/"+pname
    praw = original.raw(snap["ap"]+"/"+ppath)
    payload = bytearray(prepared["payload"])
    for k,data in enumerate((database,mirror)):
        offset = 73+89*k
        payload[offset+16:offset+24] = struct.pack("<Q",len(data))
        payload[offset+24:offset+89] = sha(data).encode()+b"\0"
    aliases(replacements,snap["authority"][ppath]["source_path"],envelope(praw,bytes(payload)))
    check("re-sealed-prepared-pair-loses-original-ledger-record",replacements,
          ["po-original-ledger-records-preserved:notes"])

    # 5. A package copy with a different actual inode cannot satisfy INPUT's
    # independently registered private-pack identity, even with identical bytes.
    snap = phase("process-kill-900-any","paused")
    tx = original.transaction(snap,"test_tool",True)
    pack_name = tx["input"]["private_pack"]
    row = snap["custody"][pack_name]
    check("input-private-pack-actual-native-id-rebound",{},
          ["po-actual-member-identity-size-digest:"+pack_name],
          {row["source_path"]:dict(inode=row["inode"]+1)})

    # 6. PREPARED's payload and outer envelope remain internally sealed, but its
    # new DB identity no longer equals the real reserved stage.
    snap = phase("process-kill-904-any","paused")
    tx = original.transaction(snap,"test_tool")
    prepared = tx["native"]["prepared_record"]
    pname = final_name(2,tx["native"]["generation"],tx["input"]["sha256"])
    ppath = snap["route"]+"/"+pname
    raw = original.raw(snap["ap"]+"/"+ppath)
    payload = bytearray(prepared["payload"])
    payload[81:89] = struct.pack("<Q",u64(payload,81)+1)
    replacements = {}
    aliases(replacements,snap["authority"][ppath]["source_path"],envelope(raw,bytes(payload)))
    check("re-sealed-prepared-native-object-contradiction",replacements,
          ["po-prepared-exact-reserved-native-stage-identities"])

    # 7. Re-seal all immutable floor-chain hashes and all following head records;
    # the first floor still names the wrong whole raw ACK digest.
    snap = phase("actual-full-seed-and-next-generation","generation-1")
    tx = original.transaction(snap,"tool")
    replacements = {}
    previous_floor = ZERO
    new_floors = []
    for index,floor in enumerate(tx["native"]["floors"]):
        relative_path = snap["route"]+"/"+floor["name"]
        raw = original.raw(snap["ap"]+"/"+relative_path)
        payload = bytearray(raw[568:-64])
        payload[72:136] = previous_floor.encode()
        if not index:
            payload[288] = ord("a") if payload[288] != ord("a") else ord("b")
        new_raw = envelope(raw,bytes(payload))
        previous_floor = sha(new_raw)
        new_floors.append(previous_floor)
        aliases(replacements,snap["authority"][relative_path]["source_path"],new_raw)
    hname = head_name(tx["native"]["generation"],tx["input"]["sha256"])
    hpath = snap["route"]+"/"+hname
    head = bytearray(original.raw(snap["ap"]+"/"+hpath))
    previous_head = head[400:464]
    for index,digest in enumerate(new_floors):
        offset = 464+272*index
        head[offset+80:offset+144] = digest.encode()
        head[offset+144:offset+208] = previous_head
        head[offset+208:offset+272] = sha(head[offset:offset+208]).encode()
        previous_head = head[offset+208:offset+272]
    aliases(replacements,snap["authority"][hpath]["source_path"],bytes(head))
    check("re-sealed-floor-head-chain-wrong-actual-ack-sha",replacements,
          ["pm-floor-actual-ack-fstat-raw-and-line"])

    # 8. Even a complete, internally re-sealed temporary has to contain the
    # claimed event9 fixture. It cannot manufacture a committed publish intent.
    publish = next(a["count"] for a in tx["native"]["acknowledgements"]
                   if a["line"].startswith(b"EXRWH2 ") and a["line"].split(b" ")[2] == b"9")
    snap = phase(f"process-kill-1602-{publish-1}","paused")
    tx = original.transaction(snap,"test_tool")
    need(len(tx["temporary"]) == 1, "po-negative-actual-unpromoted-event-nine-temp")
    temporary = tx["temporary"][0]
    raw = bytearray(temporary["raw"])
    parts = temporary["record"]["line"].split(b" ")
    need(parts[2] == b"9", "po-negative-original-temp-event-nine")
    parts[2] = b"8"
    prefix = b" ".join(parts[:-1])
    line = prefix+b" "+sha(prefix).encode()
    need(len(line) == len(temporary["record"]["line"]), "po-negative-same-size-resealed-temp-line")
    raw[296:-64] = line
    raw[232:296] = sha(line).encode()
    raw[-64:] = sha(raw[:-64]).encode()
    replacements = {}
    source_path = temporary["observed"]["source_path"]
    aliases(replacements,source_path,bytes(raw))
    check("re-sealed-temporary-does-not-prove-publish-intent",replacements,
          ["po-temp-event-nine-never-promoted"])

    need(len(results) == 8, "po-all-eight-owner-specific-resealed-negatives")
    (root/"owner-negative-controls.json").write_bytes(encoded(dict(
        schema="pc02-owner-resealed-negatives-v1",source=source,role=spec["role"],
        original_zip_sha256=spec["artifact"]["sha256"],controls=results)))
    return results
