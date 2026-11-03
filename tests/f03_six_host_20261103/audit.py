"""Authenticate original artifacts and require actual six-host F03 convergence."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import urllib.parse
import urllib.request
import zipfile

from run import BASE, SDK, HOSTS, PHASES, ROOT, admission, require, setup

IDENTITY = ("source_sha", "run_id", "attempt")
OPERATIONS = {
    "create": ["nested-shelf", "tag", "series"], "delete": ["group-delete"],
    "restore": ["group-restore"], "member-remove": ["membership-remove"],
    "member-restore": ["membership-restore"], "restart": ["restart"],
}

def read(path):
    return json.loads(path.read_bytes())

def same(value, stamp):
    require(all(value.get(k) == stamp[k] for k in IDENTITY), "source/run/attempt mismatch")

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def golden(snapshot, phase, book):
    """Fixed fixture expectations, independent of any host's success flag."""
    shelves, tags, series = (snapshot[t] for t in ("reader_shelves", "reader_tags", "reader_series"))
    require(len(shelves) == 2 and len(tags) == 1 and len(series) == 1, "missing or extra organization")
    roots = [r for r in shelves if r["name"] == "F03 Root"]
    children = [r for r in shelves if r["name"] == "F03 Child"]
    require(len(roots) == 1 and len(children) == 1, "nested shelf names differ")
    root, child = roots[0], children[0]
    require(root["parent_id"] in (None, "") and root["ordinal"] == 1 and root["deleted"] == 0,
            "root shelf differs")
    require(child["parent_id"] == root["shelf_id"] and child["ordinal"] == 2, "nested shelf order differs")
    require(tags[0]["name"] == "F03 Tag" and series[0]["name"] == "F03 Series", "tag or series differs")
    deleted = int(phase == "delete")
    require(all(r["deleted"] == deleted for r in (child, tags[0], series[0])), "group tombstone differs")
    for table, key, group, order in (
        ("reader_book_shelves", "shelf_id", child["shelf_id"], 3),
        ("reader_book_tags", "tag_id", tags[0]["tag_id"], None),
        ("reader_book_series", "series_id", series[0]["series_id"], 7),
    ):
        rows = snapshot[table]
        require(len(rows) == (0 if phase == "member-remove" else 1), "membership count differs")
        if rows:
            require(rows[0][key] == group and rows[0]["book_key"] == book, "membership identity differs")
            require(order is None or rows[0]["ordinal"] == order, "membership order differs")

def verify(data, stamp):
    identity = setup()
    require(set(data["hosts"]) == set(HOSTS) and len(data["hosts"]) == 6, "six hosts required")
    require(data["sdk_source"] == SDK and data["sdk_version"] == "3.42.0", "SDK mismatch")
    for host in HOSTS:
        require(set(data["receipts"].get(host, {})) == set(PHASES), "six phases required: " + host)
        build = data["builds"][host]
        same(build, stamp)
        require(build["operation_completed"] is True and build["sdk_source"] == SDK and
                build["sdk_version"] == "3.42.0", "actual SDK build missing")
        original = data["retained"][host]
        same(original, stamp)
        require(original["accepted"] is True and not original.get("problems") and
                not original.get("failures") and not original.get("skipped", 0), "retained suite failed or skipped")
        field = "executable_sha256" if host in ("macos", "iphone", "ipad") else "program_sha256"
        require(original[field] == data["programs"][host], "retained executable differs")
        if host == "gtk":
            require(original["count"] == 27 and len(set(original["checks"])) == 27, "GTK original coverage missing")
        if host in ("macos", "iphone", "ipad"):
            require(len(original["cases"]) == 6 and "testTagAndSeriesPersist" in original["cases"],
                    "Apple original coverage missing")
        if host == "android":
            require([original.get(k) for k in ("native_checks", "ui_checks", "recovery_checks", "sync_checks")]
                    == [8, 8, 12, 5], "Android synchronization profile coverage missing")
    baseline = data["android_baseline"]
    same(baseline, stamp)
    require(baseline["accepted"] is True and not baseline["problems"] and
            baseline["original_host_checks"] == 66 and baseline["original_owner_cases"] == 18 and
            baseline["original_gate_checks"] == [48, 20] and baseline["recovery_cases"] == 12 and
            baseline["original_organization_ui_cases"] == 8, "Android original all-exits chain missing")
    previous, previous_digest, previous_snapshot = {}, None, None
    for phase in PHASES:
        author = data["receipts"]["gtk"][phase]
        wire = data["wires"][phase]
        same(wire, stamp)
        require(wire["previous_sha256"] == previous_digest, "wire predecessor mismatch")
        require(wire["phase"] == "f03-gtk-" + phase and wire["data"]["events"] == OPERATIONS[phase],
                "actual lifecycle operations missing")
        bodies = {}
        for path, record in wire["entries"].items():
            body = base64.b64decode(record["body"], validate=True)
            require(hashlib.sha256(body).hexdigest() == record["sha256"], "wire digest mismatch")
            bodies[path] = body
        require(all(bodies.get(k) == v for k, v in previous.items()), "immutable wire changed")
        revisions = {json.loads(body)["id"]: json.loads(body) for path, body in bodies.items() if "/revisions/" in path}
        expected_revisions = {r["id"]: r["body"] for r in author["snapshot"]["revisions"]}
        require(expected_revisions and all(revisions.get(k) == v for k, v in expected_revisions.items()),
                "authored revisions missing from actual wire")
        for operation in OPERATIONS[phase]:
            event = data["events"][phase][operation]
            same(event, stamp)
            require(event["operation"] == operation and event["native_ui"] is True and event["passed"] is True and
                    event["program_sha256"] == data["programs"]["gtk"], "native operation evidence missing")
            require(set(event["revision_ids"]) <= set(expected_revisions), "operation revision missing")
            require(bool(event["revision_ids"]) or phase == "restart", "operation authored no revision")
        if phase == "restart":
            require(author["snapshot"] == previous_snapshot, "restart changed organization")
        for host in HOSTS:
            receipt = data["receipts"][host][phase]
            same(receipt, stamp)
            require(receipt["host"] == host and receipt["sdk_version"] == "3.42.0", "receiver host/SDK mismatch")
            require(receipt["program_sha256"] == data["programs"][host], "receiver executable differs")
            require(receipt["native_sync_completed"] is True, "native synchronization missing")
            require(receipt["restart_verified"] is True, "actual process restart missing")
            snapshot = receipt["snapshot"]
            require(hashlib.sha256(canonical(snapshot)).hexdigest() == receipt["snapshot_sha256"], "snapshot digest mismatch")
            golden(snapshot, phase, data["book_key"])
            require(snapshot == data["databases"][host][phase], "retained database differs")
            require(all(snapshot[t] == author["snapshot"][t] for t in identity.TABLES), "cross-host projection differs")
            received = {r["id"]: r["body"] for r in snapshot["revisions"]}
            require(all(received.get(k) == v for k, v in expected_revisions.items()), "received revision differs")
            requests = data["requests"][host][phase]
            require(requests and all(r.get("authenticated") is True for r in requests), "authenticated transport missing")
            method = "PUT" if host == "gtk" else "GET"
            if host != "gtk" or phase != "restart":
                require(any(r["method"] == method and "/revisions/" in r["path"] for r in requests),
                        "native revision transport missing")
        previous, previous_digest = bodies, data["wire_digests"][phase]
        previous_snapshot = author["snapshot"]

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        result = super().redirect_request(req, fp, code, msg, headers, newurl)
        if urllib.parse.urlsplit(newurl).netloc != "api.github.com":
            result.remove_header("Authorization")
        return result

def collect(folder, stamp):
    identity = setup()
    opener = urllib.request.build_opener(Redirect())
    def fetch(endpoint):
        return opener.open(urllib.request.Request("https://api.github.com/repos/NoGod3524/EXReader" + endpoint,
            headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"], "Accept": "application/vnd.github+json"}), timeout=180)
    prefix = "/actions/runs/" + stamp["run_id"]
    with fetch(prefix + "/attempts/" + stamp["attempt"]) as response:
        run = json.load(response)
    require(run["head_sha"] == stamp["source_sha"] and str(run["run_attempt"]) == stamp["attempt"], "API run identity differs")
    with fetch(prefix + "/attempts/" + stamp["attempt"] + "/jobs?per_page=100") as response:
        jobs = json.load(response)["jobs"]
    with fetch(prefix + "/artifacts?per_page=100") as response:
        artifacts = json.load(response)["artifacts"]
    require(len(artifacts) < 100 and len(jobs) < 100, "unexpected API pagination")
    provenance = {}
    for host in [*HOSTS, "android-baseline"]:
        job_name = "apple (" + host + ")" if host in ("macos", "iphone", "ipad") else host
        found = [j for j in jobs if j["name"] == job_name]
        require(len(found) == 1 and found[0]["status"] == "completed" and found[0]["conclusion"] == "success",
                "producer failed/skipped/missing: " + host)
        name = "f03-six-" + host + "-" + stamp["run_id"] + "-" + stamp["attempt"]
        found_artifacts = [a for a in artifacts if a["name"] == name]
        require(len(found_artifacts) == 1, "current-attempt artifact missing: " + host)
        artifact = found_artifacts[0]
        require(not artifact["expired"] and artifact["workflow_run"]["head_sha"] == stamp["source_sha"] and
                str(artifact["workflow_run"]["id"]) == stamp["run_id"], "artifact provenance differs")
        archive = folder / (host + ".zip")
        with fetch("/actions/artifacts/" + str(artifact["id"]) + "/zip") as response, archive.open("wb") as stream:
            import shutil
            shutil.copyfileobj(response, stream)
        require(archive.stat().st_size == artifact["size_in_bytes"] and artifact["digest"] == "sha256:" + sha(archive),
                "original archive identity differs")
        output = folder / host
        with zipfile.ZipFile(archive) as zipped:
            members = zipped.infolist()
            require(len({m.filename for m in members}) == len(members), "duplicate archive members")
            require(sum(m.file_size for m in members) <= 4 * 1024**3, "archive expansion exceeds bound")
            for member in members:
                path = Path(member.filename)
                require(not path.is_absolute() and ":" not in member.filename and "\\" not in member.filename and
                        ".." not in path.parts and not stat.S_ISLNK(member.external_attr >> 16), "unsafe archive member")
            zipped.extractall(output)
        provenance[host] = {"job_id": found[0]["id"], "artifact_id": artifact["id"],
                            "bytes": artifact["size_in_bytes"], "sha256": sha(archive)}
    identity.write_json(folder / "provenance.json", {**stamp, "artifacts": provenance})
    data = {"hosts": HOSTS, "sdk_source": SDK, "sdk_version": "3.42.0", "programs": {}, "builds": {},
            "retained": {}, "receipts": {}, "requests": {}, "databases": {}, "events": {}, "wires": {}, "wire_digests": {}}
    for host in HOSTS:
        root = folder / host
        if host == "gtk":
            program = root / "package/EXReader-Linux/bin/exreader-linux"
            build, report = root / "f03-gtk-build.json", root / "f03-retained-gtk/collections-ui.json"
        elif host == "windows":
            program = root / "c09/package/EXReader/EXReader.exe"
            build, report = root / "f03-windows-build.json", root / "organization-ui/report.json"
            composed = read(root / "c09/report.json")
            same(composed, stamp)
            require(composed["accepted"] is True and not composed["failures"], "Windows retained build chain missing")
        elif host == "android":
            program = root / "wave3/artifacts/app-debug.apk"
            build, report = root / "f03-android-sync/build.json", root / "f03-android-sync/retained/result.json"
        else:
            apple = root / "dot-f03-native" / host
            suffix = "Debug" if host == "macos" else "Debug-iphonesimulator"
            program = apple / "derived/Build/Products" / suffix / "EXReaderHost.app"
            program /= "Contents/MacOS/EXReaderHost" if host == "macos" else "EXReaderHost"
            build, report = root / ("f03-" + host + "-build.json"), apple / "validated/organization-ui.json"
        data["programs"][host], data["builds"][host], data["retained"][host] = sha(program), read(build), read(report)
        for key in ("receipts", "requests", "databases"):
            data[key][host] = {}
        for phase in PHASES:
            receipt = root / "f03-author" / phase if host == "gtk" else root / "f03-receipts" / host / phase
            if host in ("macos", "iphone", "ipad"):
                receipt = receipt.with_name(phase + "-receiver")
                require(read(receipt / "cleanup.json")["passed"] is True, "Apple receiver cleanup failed")
            data["receipts"][host][phase] = read(receipt / "projection.json")
            data["requests"][host][phase] = read(receipt / "wire/requests.json")
            database = [p for p in (receipt / "native-catalog").iterdir() if p.is_file() and not p.name.endswith(("-wal", "-shm"))]
            require(len(database) == 1, "actual retained database missing or ambiguous")
            data["databases"][host][phase] = identity.read_snapshot(database[0])
            if host == "gtk":
                data["wires"][phase] = read(receipt / "wire/state.json")
                data["wire_digests"][phase] = sha(receipt / "wire/state.json")
                data["events"][phase] = {op: read(receipt / (op + ".json")) for op in OPERATIONS[phase]}
    original = folder / "gtk/f03-originals/gtk-organization.txt"
    data["book_key"] = "txt:" + sha(original)
    data["android_baseline"] = read(folder / "android-baseline/f03-production/result.json")
    return data

def controls(data, stamp):
    def snapshot_change(value, host, phase, change):
        receipt = value["receipts"][host][phase]
        change(receipt["snapshot"])
        receipt["snapshot_sha256"] = hashlib.sha256(canonical(receipt["snapshot"])).hexdigest()
    def altered_wire(value):
        record = next(iter(value["wires"]["create"]["entries"].values()))
        record["sha256"] = "0" * 64
    mutations = [
        ("wrong-source", "source/run/attempt mismatch", lambda d: d["receipts"]["ipad"]["create"].update(source_sha="0"*40)),
        ("wrong-sdk", "SDK mismatch", lambda d: d.update(sdk_version="3.41.0")),
        ("missing-host", "six hosts required", lambda d: d["hosts"].pop()),
        ("missing-phase", "six phases required", lambda d: d["receipts"]["windows"].pop("restore")),
        ("skipped-original", "retained suite failed or skipped", lambda d: d["retained"]["iphone"].update(skipped=1)),
        ("wrong-program", "receiver executable differs", lambda d: d["receipts"]["android"]["create"].update(program_sha256="0"*64)),
        ("no-restart", "actual process restart missing", lambda d: d["receipts"]["macos"]["restart"].update(restart_verified=False)),
        ("no-sync", "native synchronization missing", lambda d: d["receipts"]["windows"]["create"].update(native_sync_completed=False)),
        ("no-authentication", "authenticated transport missing", lambda d: d["requests"]["ipad"].update(create=[])),
        ("failed-original-android", "Android original all-exits chain missing", lambda d: d["android_baseline"].update(accepted=False)),
        ("missing-tag", "missing or extra organization", lambda d: snapshot_change(d, "ipad", "create", lambda s: s["reader_tags"].clear())),
        ("wrong-parent", "nested shelf order differs", lambda d: snapshot_change(d, "iphone", "create",
            lambda s: next(r for r in s["reader_shelves"] if r["name"] == "F03 Child").update(parent_id=None))),
        ("wrong-group-tombstone", "group tombstone differs", lambda d: snapshot_change(d, "android", "delete",
            lambda s: s["reader_tags"][0].update(deleted=0))),
        ("wrong-member-order", "membership order differs", lambda d: snapshot_change(d, "windows", "restore",
            lambda s: s["reader_book_series"][0].update(ordinal=99))),
        ("stale-membership", "membership count differs", lambda d: snapshot_change(d, "macos", "member-remove",
            lambda s: s["reader_book_tags"].append({"tag_id": "0"*32, "book_key": d["book_key"]}))),
        ("wire-digest", "wire digest mismatch", altered_wire),
        ("wire-predecessor", "wire predecessor mismatch", lambda d: d["wires"]["restore"].update(previous_sha256=None)),
        ("unobserved-native-operation", "native operation evidence missing", lambda d: d["events"]["create"]["tag"].update(native_ui=False)),
    ]
    results = []
    for name, reason, mutate in mutations:
        altered = copy.deepcopy(data)
        mutate(altered)
        try:
            verify(altered, stamp)
        except AssertionError as error:
            require(reason in str(error), "negative control rejected for unexpected reason: " + name + ": " + str(error))
            results.append({"id": name, "rejected": True, "reason": str(error)})
        else:
            raise AssertionError("negative control accepted: " + name)
    # Preserve the historical verifier's five source-admission counterexamples.
    # They are tested against its unchanged historical scope, never used as the
    # positive admission of this new six-host source.
    identity = setup()
    old = identity.SCOPE
    cases = [
        ("old-sdk-as-product", old["sdk_source"], old["sdk_source"], [], False, "product baseline mismatch"),
        ("old-wrong-sdk", old["baseline"], "0"*40, [], False, "SDK freeze mismatch"),
        ("old-false-owner", old["baseline"], old["sdk_source"], [], True, "historical owner guard"),
        ("old-product-edit", old["baseline"], old["sdk_source"], ["examples/android/app/build.gradle"], False, "outside authorized"),
        ("old-test-edit", old["baseline"], old["sdk_source"], ["tools/check_reader_owner_android.py"], False, "outside authorized"),
    ]
    for name, base, sdk, paths, historical, reason in cases:
        try:
            identity.check_candidate_fields(base, sdk, paths, historical)
        except AssertionError as error:
            require(reason in str(error), "historical negative rejected for wrong reason: " + name)
            results.append({"id": name, "rejected": True, "reason": str(error)})
        else:
            raise AssertionError("historical negative accepted: " + name)
    return results

def main():
    identity = setup()
    stamp = admission()
    folder = ROOT / "build/f03-six-audit"
    folder.mkdir(parents=True, exist_ok=False)
    result = {**stamp, "requirement": "F03", "accepted": False, "complete": False,
              "active_hosts": [], "sdk_source": SDK, "sdk_version": "3.42.0", "problems": []}
    try:
        data = collect(folder, stamp)
        verify(data, stamp)
        negatives = controls(data, stamp)
        identity.write_json(folder / "negative-controls.json", {**stamp, "controls": negatives})
        result.update(accepted=True, complete=True, active_hosts=HOSTS, phases=PHASES,
                      negative_controls=len(negatives), physical_device_execution=False)
    except Exception as error:
        result["problems"].append(type(error).__name__ + ": " + str(error))
    identity.write_json(folder / "six-host-result.json", result)
    print(json.dumps(result))
    raise SystemExit(0 if result["accepted"] else 1)

if __name__ == "__main__":
    main()
