"""Actions-only review of retained Windows/recovery current-package evidence."""
import hashlib, io, json, os, sys, tarfile, zipfile
from pathlib import Path, PurePosixPath
assert os.environ.get("GITHUB_ACTIONS") == "true"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_parallel_integration import fetch, download_artifact_zip
OUT = Path("build/windows-closure-independent")
OUT.mkdir(parents=True, exist_ok=True)
STAGE = "be3f9f5610125d1ff969add1169028111b398a22"
RECORD = "2743f32a4eccd5823657da19cb4f77f2411424af"
PINS = [
 ("linux", STAGE, 40949223801, 123712573306, 12930499541, 19503796, "c42772e380ddf4b84a75fe406ee7c687b6e15bf40013ff7a080a0390dfe0b62f"),
 ("macos", STAGE, 40949223801, 123712572899, 12932484375, 19520617, "c2a42eb5ba3e399a4dd5a0050be00131362b594e17450cf591a7ad630b0f58e0"),
 ("windows", STAGE, 40949223801, 123712573269, 12930546852, 32135, "f762cf6bcc533c69260c4a02097ca0e72d75fd642aaee6432d5a1daa6f1f2357"),
 ("record", RECORD, 40950523121, 123717117262, 12931496665, 131650, "fe9906afd12bf2644cf584f627b525cd17d9e2f007615b2297a5d423f67611ec"),
]
def sha(data): return hashlib.sha256(data).hexdigest()
def read_zip(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = [i.filename for i in z.infolist()]
        assert len(names) == len(set(names))
        assert all(not PurePosixPath(n).is_absolute() and ".." not in n.split("/") and "\\" not in n and ":" not in n for n in names)
        return {i.filename:z.read(i) for i in z.infolist() if not i.is_dir()}
def one(items, suffix):
    found = [n for n in items if n == suffix or n.endswith("/"+suffix)]
    assert len(found) == 1, (suffix, found)
    return items[found[0]]
def cases(data, expected):
    assert data["passed"] is True and data["full_p0_acceptance"] is False
    assert len(data["cases"]) == expected and all(c["passed"] is True for c in data["cases"])
    return expected
result = dict(accepted=False, records=[], catalog_changed=False, complete_product=False,
              common_source_acceptance=False, recovery_admission=False)
try:
    for label, source, runid, jobid, aid, size, digest in PINS:
        run = fetch(f"actions/runs/{runid}/attempts/1")
        job = fetch(f"actions/jobs/{jobid}")
        assert (run["head_sha"],run["run_attempt"],run["status"],run["conclusion"]) == (source,1,"completed","success")
        assert (job["run_id"],job["head_sha"],job["status"],job["conclusion"]) == (runid,source,"completed","success")
        pin = fetch(f"actions/artifacts/{aid}")
        assert not pin["expired"] and pin["size_in_bytes"] == size and pin["digest"] == "sha256:"+digest
        assert (pin["workflow_run"]["id"],pin["workflow_run"]["head_sha"]) == (runid,source)
        raw = download_artifact_zip(aid)
        assert len(raw) == size and sha(raw) == digest
        files = read_zip(raw)
        row = dict(label=label,source=source,run=runid,attempt=1,job=jobid,artifact=aid,bytes=size,sha256=digest)
        row["recovery_cases"] = cases(json.loads(one(files,"recovery-integration/evidence.json")),8 if label in ("record","windows") else 32)
        if label in ("linux","macos"):
            row["preflight_cases"] = cases(json.loads(one(files,"recovery-preflight/result.json")),41)
            row["handoff_cases"] = cases(json.loads(one(files,"recovery-handoff/evidence.json")),22)
            receipt = json.loads(one(files,"evidence/new-target-archive-receipt.json"))
            manifest_raw = one(files,"evidence/new-target-node-manifest.json")
            manifest = json.loads(manifest_raw)
            archive = one(files,"evidence/new-target-evidence.tar.gz")
            assert receipt["source_sha"] == manifest["source_sha"] == source
            assert receipt["typed_replay_passed"] is True
            assert len(archive) == receipt["archive_bytes"] and sha(archive) == receipt["archive_sha256"]
            assert all(receipt["helper_controls"].values())
            seen = set()
            targets = {}
            with tarfile.open(fileobj=io.BytesIO(archive),mode="r:gz") as tar:
                for member in tar:
                    assert member.name not in seen and len(seen) <= 30000
                    seen.add(member.name)
                    assert not PurePosixPath(member.name).is_absolute() and ".." not in member.name.split("/")
                    if member.name == "node-manifest.json":
                        assert member.isfile() and tar.extractfile(member).read() == manifest_raw
                    elif member.isfile():
                        item = manifest["entries"][member.name]
                        assert item["kind"] == "file" and member.size == item["identity"][4] and member.size <= 1024**3
                        data = tar.extractfile(member).read()
                        assert sha(data) == item["sha256"]
                        if member.name.endswith("/evidence.json"): targets[member.name] = data
                    elif member.islnk():
                        assert member.linkname in manifest["entries"]
                        assert manifest["entries"][member.name]["sha256"] == manifest["entries"][member.linkname]["sha256"]
                    else:
                        assert member.isdir() or member.issym() or member.isfifo()
            assert seen == set(manifest["entries"]) | {"node-manifest.json"}
            row["new_target_cases"] = cases(json.loads(one(targets,"new-target-recovery/evidence.json")),36)
        if label == "record":
            receipt = json.loads(one(files,"record-evidence/receipt.json"))
            native = json.loads(one(files,"record-evidence/native.json"))
            assert receipt["source"] == native["source"] == source and str(receipt["run"]) == str(runid)
            assert receipt["checks"] == native and receipt["full_p0_acceptance"] is False
            assert native["passed"] is True and native["checks"] == native["expected"] == 27
            assert native["identity_bytes"] == 49 and native["sdk_open_attempts"] == 0 and native["recovery_admission"] is False
            record_raw = one(files,"record-evidence/private-state/record-00.json")
            record = json.loads(record_raw)
            assert len(record) == 13 and record["magic"] == "EXRWINRECOVERY1" and record["version"] == 1
            assert record["source"] == source and record["target"] == native["target"]
            assert all(len(record[n]) == 48 and set(record[n]) <= set("0123456789abcdef") for n in ("root","parent","target"))
            body = {k:v for k,v in record.items() if k != "seal"}
            canonical = json.dumps(body,separators=(",",":"))+"\n"
            assert sha(canonical.encode()) == record["seal"]
            assert (json.dumps(record,separators=(",",":"))+"\n").encode() == record_raw
            assert set(receipt["files"]) == {"target.fixture","record-00.json"}
            for name,meta in receipt["files"].items():
                data = one(files,"record-evidence/private-state/"+name)
                assert len(data) == meta["bytes"] and sha(data) == meta["sha256"]
            lib = one(files,"migration-stage/lib/exreader-migration-windows-record.lib")
            assert sha(lib) == receipt["installed_library_sha256"]
            row.update(installed_consumer_checks=27,canonical_record_seal_recomputed=True,
                       retained_installed_library_sha256=sha(lib))
        result["records"].append(row)
    result.update(accepted=True,scope="exact retained producer ZIP identities, original case counts/results, typed archive file hashes and retained Windows canonical record; no replay or recovery admission")
except Exception as error:
    result["error"] = repr(error)
finally:
    (OUT/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result),flush=True)
assert result["accepted"], result.get("error")
