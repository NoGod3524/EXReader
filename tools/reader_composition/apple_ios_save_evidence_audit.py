#!/usr/bin/env python3
"""Inspect original Apple evidence in Actions; do not change catalog acceptance."""
import hashlib, json, os, plistlib, subprocess, tempfile, zipfile
from pathlib import Path, PurePosixPath

assert os.environ.get("GITHUB_ACTIONS") == "true"
REPO = "NoGod3524/EXReader"
FONT_RUN, FONT_SOURCE = 40627627614, "d23fc1de44d94a80ea8cfc5aa8d74fb24d63400a"
SAVE_RUN, SAVE_SOURCE = 40905868673, "127cdb7c62772fd293c10cc032547c28904bd1c2"
FONT_HASH = "ce360aed7a09322e2c815ed9c06ce9e3304cdfb886b19493e9e59216d622bfed"
BOOK_HASH = "0c54c6c969cb720875557d8f877d0733cc65dd1e80d74d098fb18ba65bf42bdb"
PINS = [
 ("original", "iphone", 12912596737, 1091079, "842f2802eef90df0816a930af60b5be987ab2c9500190ef644c9fee19cff9fd1", 123560322008),
 ("original", "ipad", 12912122792, 1395222, "8352574f57110bfa9bbe031e88140f19bf1cbfdacb2deda85cdc999333255849", 123560322186),
]
def api(path, binary=False):
    p = subprocess.run(["gh", "api", "repos/" + REPO + "/" + path], check=True, stdout=subprocess.PIPE)
    return p.stdout if binary else json.loads(p.stdout)
def digest(data): return hashlib.sha256(data).hexdigest()
def safe_extract(archive, target):
    names = archive.namelist()
    assert len(names) == len(set(names)), "duplicate ZIP members"
    for name in names:
        p = PurePosixPath(name)
        assert not p.is_absolute() and ".." not in p.parts and "\\" not in name, name
    archive.extractall(target)
def one(root, pattern):
    found = list(root.rglob(pattern))
    assert len(found) == 1, (pattern, [str(x) for x in found])
    return found[0]
def test_cases(bundle):
    out = subprocess.check_output(["xcrun", "xcresulttool", "get", "test-results", "tests", "--path", str(bundle), "--format", "json"])
    cases = []
    def walk(node):
        if node.get("nodeType") == "Test Case": cases.append((node.get("name"), node.get("result")))
        for child in node.get("children", []): walk(child)
    for node in json.loads(out)["testNodes"]: walk(node)
    return cases
def audit(kind, platform, artifact, size, expected, job_id, root):
    run, source = (FONT_RUN, FONT_SOURCE) if kind == "font" else (SAVE_RUN, SAVE_SOURCE)
    run_data = api("actions/runs/%s/attempts/1" % run)
    assert run_data["head_sha"] == source and run_data["run_attempt"] == 1
    assert run_data["status"] == "completed" and run_data["conclusion"] == "success"
    job = api("actions/jobs/%s" % job_id)
    assert job["run_id"] == run and job["head_sha"] == source and job["conclusion"] == "success"
    meta = api("actions/artifacts/%s" % artifact)
    assert not meta["expired"] and meta["workflow_run"]["id"] == run
    assert meta["workflow_run"]["head_sha"] == source
    assert meta["size_in_bytes"] == size and meta["digest"] == "sha256:" + expected
    raw = api("actions/artifacts/%s/zip" % artifact, True)
    assert len(raw) == size and digest(raw) == expected
    dst = root / (kind + "-" + platform); dst.mkdir()
    with zipfile.ZipFile(__import__("io").BytesIO(raw)) as z: safe_extract(z, dst)
    report = json.loads(one(dst, "result.json").read_text())
    assert (report["source_sha"], str(report["run_id"]), str(report["attempt"]), report["platform"]) == (source, str(run), "1", platform)
    assert report["accepted"] is True and report["physical_device"] is False
    if kind == "font":
        assert report["fixture"]["font_sha256"] == FONT_HASH
        manifest = json.loads(one(dst, "resource-manifest.json").read_text())
        assert manifest["FontReview.ttf"] == FONT_HASH and manifest["Reader.otf"] != FONT_HASH
        assert test_cases(one(dst, "font.xcresult")) == [("testDistinctFontInvalidRollbackLeaseAndReopen()", "Passed")]
        package = one(dst, "EXReaderHost.zip")
        with zipfile.ZipFile(package) as z:
            files = z.namelist()
            suffix = "Contents/MacOS/EXReaderHost" if platform == "macos" else "EXReaderHost.app/EXReaderHost"
            binary = [n for n in files if n.endswith(suffix)]
            plists = [n for n in files if n.endswith("Contents/Info.plist" if platform == "macos" else "EXReaderHost.app/Info.plist")]
            fonts = [n for n in files if n.endswith("/FontReview.ttf")]
            assert len(binary) == len(plists) == len(fonts) == 1
            assert digest(z.read(binary[0])) == report["program"]["sha256"]
            assert digest(z.read(fonts[0])) == FONT_HASH
            info = plistlib.loads(z.read(plists[0]))
            assert info["EXRSourceSHA"] == source and info["CFBundleIdentifier"] == "org.exreader.host"
        detail = {"test": "testDistinctFontInvalidRollbackLeaseAndReopen()", "program_sha256": report["program"]["sha256"]}
    else:
        assert test_cases(one(dst, "native.xcresult")) == [("testSystemFolderSave()", "Passed")]
        source_bytes = one(dst, "source.epub").read_bytes()
        saved_bytes = one(dst, "saved.epub").read_bytes()
        assert source_bytes == saved_bytes and len(source_bytes) == 7724 and digest(source_bytes) == BOOK_HASH
        assert report["readback"]["byte_equal"] is True
        assert report["readback"]["source_sha256"] == report["readback"]["saved_sha256"] == BOOK_HASH
        detail = {"test": "testSystemFolderSave()", "source_saved_sha256": BOOK_HASH, "bytes": len(source_bytes),
                  "program_sha256_reported": report["program"]["sha256"], "program_binary_retained": False}
    return {"kind": kind, "platform": platform, "run": run, "source": source, "job": job_id,
            "artifact": artifact, "archive_sha256": expected, "original_run_conclusion": "success",
            "scoped_evidence_passed": True, "physical_device": False, **detail}
results=[]
try:
    with tempfile.TemporaryDirectory() as work:
        for pin in PINS:
            try:
                result = audit(*pin, Path(work))
            except Exception as exc:
                result = {"kind":pin[0], "platform":pin[1], "artifact":pin[2],
                          "scoped_evidence_passed":False, "error":repr(exc)}
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
finally:
    out=Path("build/apple-ios-save-evidence-audit")
    out.mkdir(parents=True, exist_ok=True)
    (out/"results.json").write_text(json.dumps({"results":results, "catalog_changed":False}, indent=2)+"\n")
assert len(results) == len(PINS) and all(x["scoped_evidence_passed"] for x in results)
