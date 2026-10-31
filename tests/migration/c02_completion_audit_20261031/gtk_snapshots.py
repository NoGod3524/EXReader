# SPDX-License-Identifier: MIT
"""Independent raw GTK authority snapshots, including resealed semantic negatives."""
import argparse
import copy
import io
import json
import os
from pathlib import Path
import struct
import zipfile
from protocols import need, sha, json_value
from posix_protocols import audit_snapshot

PHASES = ("clean", "borrowed", "released", "pending")

def audit_gtk_snapshots(files, prefix=""):
    results = {}
    for phase in PHASES:
        base = prefix + "snapshots/" + phase + "/"
        manifest = json_value(files[base + "native-identities.json"])
        value = audit_snapshot(files, manifest, base)
        need(len(value["libraries"]) == 2 and
             [item["status"] for item in value["libraries"]] ==
             (["pending", "clean"] if phase == "pending" else ["clean", "clean"]),
             "gtk-exact-native-phase:" + phase)
        for index, library in enumerate(value["libraries"]):
            need(len(library["history"]) == (2 if phase == "pending" and index == 0 else 1),
                 "gtk-exact-state-record-count")
        results[phase] = value
    first = results["clean"]
    for phase, value in results.items():
        need(value["euid"] == first["euid"] and value["root"] == first["root"],
             "gtk-retained-native-authority")
        for index, library in enumerate(value["libraries"]):
            prior = first["libraries"][index]
            need(library["route"] == prior["route"] and library["binding"] == prior["binding"] and
                 library["path"] == prior["path"] and library["observed_target"] == prior["observed_target"],
                 "gtk-original-native-route-custody")
    for phase in ("released", "pending"):
        for index in (0, 1):
            name = "library-%d.sqlite" % index
            need(files[prefix + "snapshots/" + phase + "/" + name] ==
                 files[prefix + "snapshots/borrowed/" + name], "gtk-no-post-borrow-library-write")
    report = json_value(files[prefix + "report.json"])
    pending = next(row for row in report["cases"] if row["name"] ==
                   "durable-pending-blocks-actual-host-before-any-catalog-write")["descriptor"]
    observed = results["pending"]["libraries"][0]["history"][-1]
    need(pending == dict(pending=True, generation=observed["generation"], seal=observed["seal"],
                         manifest=observed["manifest"], input=observed["input"]), "gtk-native-pending-descriptor")
    held = [json_value(line) for line in files[prefix + "held.stdout"].splitlines() if line]
    need(len(held) == 2 and held[0]["holding"] is True and held[0]["search_complete"] is False and
         held[0]["search_results"] > 0 and held[1] == dict(closed=True), "gtk-actual-live-search-and-final-close")
    for name, code in (("exclusive-while-borrowed", 2), ("exclusive-after-close", 0),
                       ("pending-actual-host", 2), ("pending-command", 2), ("pending-duplicate-enroll", 2),
                       ("unknown-host", 2), ("second-created", 0)):
        need(files[prefix + name + ".exit"].strip() == str(code).encode(), "gtk-raw-process-exit:" + name)
    return dict(phases=results, actual_search_results=held[0]["search_results"])

def pending_negative_controls(files, prefix, output):
    base = prefix + "snapshots/pending/"
    original = {path[len(base):]:data for path, data in files.items() if path.startswith(base)}
    source_manifest = json_value(original["native-identities.json"])
    verified = audit_snapshot(original, source_manifest)
    route = verified["libraries"][0]["route"]
    controls = []
    def replace(raw, manifest, name, mutation, seal_offset=None):
        key = "authority/" + name
        data = bytearray(raw[key])
        mutation(data)
        if seal_offset is not None:
            data[seal_offset:seal_offset + 64] = sha(data[:seal_offset]).encode()
        raw[key] = bytes(data)
        row = next(item for item in manifest["objects"] if item["path"] == name)
        row.update(bytes=len(data), sha256=sha(data))
    def state(raw, manifest, mutation):
        def change(data):
            mutation(data)
            if len(data) == 736:
                data[672:736] = sha(data[368:672]).encode()
        replace(raw, manifest, route + "/state", change)
    mutations = [
        ("resealed-posix-reserved", lambda r,m:state(r,m,lambda b:b.__setitem__(377,1))),
        ("resealed-posix-sequence-gap", lambda r,m:state(r,m,lambda b:struct.pack_into("<Q",b,384,3))),
        ("resealed-posix-pending-as-grant", lambda r,m:replace(r,m,route+"/binding",
            lambda b:b.__setitem__(slice(96,160),r["authority/"+route+"/state"][672:736]),240)),
        ("resealed-posix-authority-identity", lambda r,m:replace(r,m,"authority",
            lambda b:struct.pack_into("<Q",b,48,struct.unpack_from("<Q",b,48)[0]+1),56)),
        ("posix-same-bytes-replaced-state", lambda r,m:next(x for x in m["objects"] if x["path"]==route+"/state")
            .update(inode=next(x for x in m["objects"] if x["path"]==route+"/state")["inode"]+1)),
        ("posix-authority-permissions", lambda r,m:next(x for x in m["objects"] if x["path"]==".")
            .update(mode=0o40777)),
        ("rehashed-posix-torn-state", lambda r,m:state(r,m,lambda b:b.__delitem__(slice(735,None)))),
        ("rehashed-posix-pending-prefix-rollback", lambda r,m:state(r,m,lambda b:b.__delitem__(slice(368,None)))),
    ]
    output.mkdir(parents=True, exist_ok=True)
    for name, mutation in mutations:
        raw = dict(original)
        manifest = copy.deepcopy(source_manifest)
        mutation(raw, manifest)
        raw["native-identities.json"] = (json.dumps(manifest, indent=2)+"\n").encode()
        raw["file-hashes.json"] = (json.dumps([dict(path=path,bytes=len(data),sha256=sha(data))
            for path,data in sorted(raw.items())],indent=2)+"\n").encode()
        try:
            value = audit_snapshot(raw, manifest)
            need(value["libraries"][0]["status"] == "pending", "gtk-negative-native-pending-lost")
        except ValueError as error:
            reason = str(error)
        else:
            raise ValueError("accepted-resealed-posix-negative:" + name)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path,data in sorted(raw.items()):
                archive.writestr(path,data)
        packet = buffer.getvalue()
        (output / (name + ".zip")).write_bytes(packet)
        controls.append(dict(name=name,rejected=True,reason=reason,bytes=len(packet),sha256=sha(packet)))
    return controls

def main():
    need(os.environ.get("GITHUB_ACTIONS") == "true", "Actions-only")
    parser = argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    files = {path.relative_to(args.root).as_posix():path.read_bytes()
             for path in args.root.rglob("*") if path.is_file() and not path.is_symlink()}
    result = audit_gtk_snapshots(files)
    result["negative_controls"] = pending_negative_controls(files,"",args.output / "negative-controls")
    result["passed"] = True
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output / "result.json").write_text(json.dumps(result,indent=2)+"\n")
    print("C02-GTK-INDEPENDENT phases=4 resealed_negatives=8 passed=true",flush=True)

if __name__ == "__main__":
    main()
