#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""J01: locate Android license-material findings from the pinned F12 matrix and
build an immutable candidate package. Execute ONLY in GitHub Actions.

Reuses the F12 auditor (read-only checkout) so judgments are identical to the
audit that produced the findings. Never touches the APK payload bytes.
"""
import hashlib, importlib.util, io, json, os, sys, tarfile, zipfile, urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[3]
F12 = Path(os.environ["F12_CHECKOUT"]).resolve()
SRC = Path(os.environ["SOURCE_CHECKOUT"]).resolve()
OUT = ROOT / "j01-evidence"
CAND = ROOT / "j01-candidate"

F12_RUN, F12_ART, F12_BYTES = 41149079819, 13022451126, 138556827
F12_DIGEST = "941fa87a94f0ca44fcb23ef1f68a9d873c379e9ffbcd564190bd636258f3fc34"
F12_COMMIT = "c03b1d9a3b30b745a903eeab9be2871f18360e33"
APK_SHA = "b6adf2d4208be647573090d77490b63fea9e37e2c89c760b2871fc4aec5f9519"

spec = importlib.util.spec_from_file_location("f12", F12 / "scripts/audit/dot_f12_package_material_audit_20261030.py")
f12 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f12)
sha, need, js, dump = f12.sha, f12.need, f12.js, f12.dump
MIB = f12.MIB


def lic_registry():
    s = importlib.util.spec_from_file_location("lic", F12 / "tools/check_reading_licenses.py")
    m = importlib.util.module_from_spec(s)
    sys.path.insert(0, str(F12 / "tools"))
    s.loader.exec_module(m)
    return m


def read_f12_matrix():
    meta = js(f12.get(f"https://api.github.com/repos/{f12.REPO}/actions/artifacts/{F12_ART}", MIB))
    need(meta["id"] == F12_ART and meta["size_in_bytes"] == F12_BYTES, "f12.identity")
    need(meta["digest"] == "sha256:" + F12_DIGEST and meta["expired"] is False, "f12.digest")
    need(meta["workflow_run"]["id"] == F12_RUN and meta["workflow_run"]["head_sha"] == F12_COMMIT, "f12.run")
    raw = f12.get(f"https://api.github.com/repos/{f12.REPO}/actions/artifacts/{F12_ART}/zip", F12_BYTES)
    need(len(raw) == F12_BYTES and sha(raw) == F12_DIGEST, "f12.download")
    wanted = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = [i.filename for i in z.infolist()]
        dump(OUT / "f12-artifact-listing.json", names)
        for i in z.infolist():
            if i.filename.endswith(("android/materials.json", "summary.json", "controls.json")) and i.file_size < 32 * MIB:
                wanted[i.filename] = json.loads(z.read(i))
    return wanted


def load_android():
    aid, size, digest, inner_digest = f12.PINS["android"]
    meta = js(f12.get(f"https://api.github.com/repos/{f12.REPO}/actions/artifacts/{aid}", MIB))
    f12.meta_check(meta, "android")
    raw = f12.get(f"https://api.github.com/repos/{f12.REPO}/actions/artifacts/{aid}/zip", size)
    need(len(raw) == size and sha(raw) == digest, "download.identity")
    outer_z = zipfile.ZipFile(io.BytesIO(raw))
    outer = f12.scan_zip(raw, [0], "outer")
    mname = [n for n in outer if PurePosixPath(n).name == "manifest.json"]
    need(len(mname) == 1, "outer.manifest_count")
    om = js(outer[mname[0]])
    arch = [n for n in outer if n == om["archive"]["name"] or n.endswith("/" + om["archive"]["name"])]
    need(len(arch) == 1, "outer.archive_count")
    pkg = outer[arch[0]]
    need(sha(pkg) == inner_digest, "manifest.inner_hash")
    return dict(raw=raw, outer_z=outer_z, outer=outer, mname=mname[0], om=om, arch=arch[0], pkg=pkg)


def merged_view(pkg_bytes):
    files = f12.scan_zip(pkg_bytes, [0], "package")
    im = f12.manifest_check(files, "android")
    need(im["entry"] == "artifacts/app-debug.apk", "apk.entry")
    nested = f12.scan_zip(files[im["entry"]], [0], "apk")
    return files, im, f12.merge_apk(files, nested)


def summarize(rows):
    return {r.get("component", "?") + "|" + str(r.get("installed", "")): r["state"] for r in rows}


def fetch_upstream(comp, cache):
    url = comp["source"]
    if url in cache:
        return cache[url]
    need(comp.get("archive_sha256") and url.startswith("https://codeload.github.com/"), "upstream.pin")
    req = urllib.request.Request(url, headers={"User-Agent": "EXReader-J01"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read(256 * MIB)
    need(sha(data) == comp["archive_sha256"], "upstream.hash")
    members = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        for m in t:
            if m.isfile() and m.size < 4 * MIB:
                members[m.name.split("/", 1)[-1]] = t.extractfile(m).read()
    cache[url] = members
    return members


def source_bytes(row, comps, cache):
    """Return (bytes, origin) only if content hash equals the registered expectation."""
    exp = row.get("expected_sha256")
    if not exp:
        return None, "no_expected_hash"
    p = row["source"]
    for base, label in ((SRC, "8f8acf32"), (F12, "f12")):
        f = base / p
        if f.is_file() and sha(f.read_bytes()) == exp:
            return f.read_bytes(), "repository@" + label + ":" + p
    comp = comps.get(row["component"])
    if comp and comp.get("archive_sha256"):
        mem = fetch_upstream(comp, cache)
        if p in mem and sha(mem[p]) == exp:
            return mem[p], "upstream:" + comp["source"] + "!" + p
        return None, "upstream_member_not_matching"
    return None, "source_not_found"


def find_by_hash(h):
    for p in SRC.rglob("*"):
        if p.is_file() and ".git" not in p.parts and p.stat().st_size < 1 * MIB and sha(p.read_bytes()) == h:
            return p.read_bytes(), "repository:" + str(p.relative_to(SRC))
    return None, "not_found"


def build_candidate(a, mats_before, registry, comps):
    files, im, merged = merged_view(a["pkg"])
    additions, skipped = {}, []
    cache = {}
    for r in mats_before["materials"]:
        st = r["state"]
        if st != "missing_required":
            if st not in ("present_verified", "not_applicable"):
                skipped.append({"row": r.get("component"), "installed": r.get("installed"), "state": st,
                                "why": "not added: mismatch/unresolved needs a decision, not a blind overwrite"})
            continue
        comp = r.get("component")
        if comp == "first_party":
            data, org = source_bytes(dict(r, source="LICENSE"), comps, cache)
            dest = "LICENSE"
        elif comp == "notice":
            data, org = source_bytes(dict(r, source="THIRD_PARTY_NOTICES.md"), comps, cache)
            dest = "THIRD_PARTY_NOTICES.md"
        elif comp == "host_noto_font":
            data, org = find_by_hash(f12.OFL)
            dest = "licenses/noto-host-font/OFL.txt"
        else:
            data, org = source_bytes(r, comps, cache)
            dest = r["installed"].removeprefix("share/exreader/")
        if data is None:
            skipped.append({"row": comp, "installed": r.get("installed"), "state": st, "why": org})
            continue
        if dest in files or dest in additions:
            skipped.append({"row": comp, "installed": dest, "state": st, "why": "destination already occupied"})
            continue
        additions[dest] = (data, org)
    # --- rebuild inner package ---
    mtext = files["manifest.json"].decode()
    man = js(files["manifest.json"])
    sample = next(iter(man["files"].values()))
    for dest, (data, org) in additions.items():
        row = {k: v for k, v in sample.items()}
        row["bytes"], row["sha256"] = len(data), sha(data)
        if "mode" in row:
            row["mode"] = 0o644
        man["files"][dest] = row
    man["candidate"] = {"task": "J01", "base_archive_sha256": f12.PINS["android"][3],
                        "added": {d: {"sha256": sha(b), "origin": o} for d, (b, o) in sorted(additions.items())},
                        "apk_sha256": APK_SHA, "note": "materials added only; APK bytes unchanged; not a release"}
    indent = 2 if mtext.startswith("{\n") else None
    new_manifest = (json.dumps(man, ensure_ascii=False, indent=indent) + ("\n" if mtext.endswith("\n") else "")).encode()
    sums = "".join(man["files"][n]["sha256"] + "  " + n + "\n" for n in sorted(man["files"])).encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(a["pkg"])) as zin, zipfile.ZipFile(buf, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info)
            if info.filename == "manifest.json": data = new_manifest
            elif info.filename == "SHA256SUMS": data = sums
            zout.writestr(info, data, compress_type=info.compress_type)
        for dest, (data, _) in sorted(additions.items()):
            zi = zipfile.ZipInfo(dest, date_time=(2026, 10, 31, 0, 0, 0))
            zi.external_attr = (0o100644) << 16
            zout.writestr(zi, data, compress_type=zipfile.ZIP_DEFLATED)
    inner = buf.getvalue()
    # --- rebuild outer ---
    om = json.loads(json.dumps(a["om"]))
    om["archive"]["sha256"], om["archive"]["bytes"] = sha(inner), len(inner)
    om["files"] = js(new_manifest)["files"]
    om["candidate"] = man["candidate"]
    otext = a["outer"][a["mname"]].decode()
    oindent = 2 if otext.startswith("{\n") else None
    new_outer_manifest = (json.dumps(om, ensure_ascii=False, indent=oindent) + ("\n" if otext.endswith("\n") else "")).encode()
    ob = io.BytesIO()
    with zipfile.ZipFile(ob, "w") as zout:
        for info in a["outer_z"].infolist():
            data = a["outer_z"].read(info)
            if info.filename == a["mname"]: data = new_outer_manifest
            elif info.filename == a["arch"]: data = inner
            zout.writestr(info, data, compress_type=info.compress_type)
    return ob.getvalue(), inner, additions, skipped


def main():
    need(os.environ.get("GITHUB_ACTIONS") == "true", "actions_only")
    OUT.mkdir(exist_ok=True); CAND.mkdir(exist_ok=True)
    matrix = read_f12_matrix()
    dump(OUT / "f12-matrix-android-excerpt.json", matrix)
    mod = lic_registry()
    comps = {c["id"]: c for c in mod.COMPONENTS}
    registry = f12.obligations()
    a = load_android()
    files, im, merged = merged_view(a["pkg"])
    before = f12.materials(merged, im, registry)
    dump(OUT / "android-before-rederived.json", before)
    f12_android = next((v for k, v in matrix.items() if k.endswith("android/materials.json")), None)
    consistent = None
    if f12_android:
        consistent = summarize(f12_android["materials"]) == summarize(before["materials"])
    dump(OUT / "rederive-consistency.json", {"matches_f12_matrix": consistent})
    apk_before = sha(files[im["entry"]])
    need(apk_before == APK_SHA, "apk.identity")
    outer_bytes, inner_bytes, additions, skipped = build_candidate(a, before, registry, comps)
    # --- verify candidate with the same F12 logic ---
    outer2 = f12.scan_zip(outer_bytes, [0], "cand.outer")
    need(len(outer2) == len(a["outer"]), "cand.outer_count")
    om2 = js(outer2[a["mname"]])
    need(sha(outer2[a["arch"]]) == om2["archive"]["sha256"] and len(outer2[a["arch"]]) == om2["archive"]["bytes"], "cand.archive_hash")
    files2, im2, merged2 = merged_view(outer2[a["arch"]])
    need(sha(files2[im2["entry"]]) == APK_SHA, "cand.apk_changed")
    changed = [n for n in files if n not in ("manifest.json", "SHA256SUMS") and files[n] != files2.get(n)]
    need(not changed, "cand.payload_changed")
    need(om2["files"] == im2["files"], "cand.outer_inner_identity")
    after = f12.materials(merged2, im2, registry)
    dump(OUT / "android-after.json", after)
    names = [i.filename for i in zipfile.ZipFile(io.BytesIO(outer_bytes)).infolist()]
    inner_names = [i.filename for i in zipfile.ZipFile(io.BytesIO(inner_bytes)).infolist()]
    need(len(names) == len(set(names)) and len(inner_names) == len(set(inner_names)), "cand.duplicate_entry")
    findings = [dict(component=r.get("component"), installed=r.get("installed"), state=r["state"],
                     condition=r.get("condition"), applicability=r.get("applicability"),
                     paths=r.get("paths"), expected_sha256=r.get("expected_sha256"))
                for r in before["materials"] if r["state"] not in ("present_verified", "not_applicable")]
    name = "exreader-android-j01-candidate.zip"
    (CAND / name).write_bytes(outer_bytes)
    ident = {"candidate_outer": {"name": name, "bytes": len(outer_bytes), "sha256": sha(outer_bytes)},
             "candidate_inner": {"bytes": len(inner_bytes), "sha256": sha(inner_bytes)},
             "original_outer_sha256": f12.PINS["android"][2], "original_inner_sha256": f12.PINS["android"][3],
             "apk_sha256_unchanged": APK_SHA}
    dump(OUT / "candidate-identity.json", ident)
    summary = dict(candidate_identity=ident,
        findings_before=findings, added=[{"path": d, "sha256": sha(b), "origin": o} for d, (b, o) in sorted(additions.items())],
        skipped_unresolved=skipped,
        states_before={s: sum(r["state"] == s for r in before["materials"]) for s in {r["state"] for r in before["materials"]}},
        states_after={s: sum(r["state"] == s for r in after["materials"]) for s in {r["state"] for r in after["materials"]}},
        registered_materials_complete_before=before["registered_materials_complete"],
        registered_materials_complete_after=after["registered_materials_complete"],
        rederive_matches_f12_matrix=consistent, production_packaging_changed=False,
        legal_compliance_assessed=False, materials_complete="false: runtime/system dependency closure unresolved (F12 limit)")
    dump(OUT / "j01-summary.json", summary)
    print(json.dumps(summary, indent=2)[:6000])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        OUT.mkdir(exist_ok=True)
        dump(OUT / "fatal.json", {"error": str(e), "type": type(e).__name__})
        raise
