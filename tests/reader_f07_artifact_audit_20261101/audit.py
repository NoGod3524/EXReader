"""Authenticate one fixed F07 producer artifact; never build, relink, or run its payloads."""
import hashlib
import io
import json
import ntpath
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
LOCK = json.loads(Path(__file__).with_name("contract.json").read_text())
OUT = ROOT / "build/f07-artifact-audit"
START = time.monotonic()
REPORT = {"diagnostic_only": True, "F07_accepted": False, "formal_count_changed": False,
          "producer_runtime_observed": False, "artifact_authenticated": False,
          "audit_completed": False, "errors": []}

def need(ok, reason):
    if not ok:
        raise ValueError(reason)

def deadline():
    need(time.monotonic() - START < LOCK["script_deadline_seconds"], "script_deadline")

def sha(data):
    return hashlib.sha256(data).hexdigest()

def put(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

def admission():
    need(os.environ.get("GITHUB_ACTIONS") == "true", "actions_only")
    need(os.environ.get("GITHUB_REPOSITORY") == LOCK["repository"], "repository")
    need(os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "one_attempt")
    need(os.environ.get("GITHUB_REF") == "refs/heads/" + LOCK["branch"], "branch")
    need(git("rev-parse", "HEAD") == os.environ["GITHUB_SHA"], "consumer_source")
    need(LOCK["trigger"] in git("show", "-s", "--format=%B", "HEAD"), "trigger")
    need(set(git("diff", "--name-only", LOCK["base"], "HEAD").splitlines()) == set(LOCK["paths"]), "four_new_paths_only")
    for name in LOCK["paths"]:
        p = subprocess.run(["git", "cat-file", "-e", LOCK["base"] + ":" + name],
                           cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        need(p.returncode != 0, "path_not_new:" + name)
    REPORT["consumer"] = {"source": os.environ["GITHUB_SHA"], "run": os.environ["GITHUB_RUN_ID"],
                          "attempt": os.environ["GITHUB_RUN_ATTEMPT"], "base": LOCK["base"]}

def read_bounded(response, limit):
    buf = bytearray()
    while True:
        deadline()
        chunk = response.read(min(1048576, limit + 1 - len(buf)))
        if not chunk:
            return bytes(buf)
        buf.extend(chunk)
        need(len(buf) <= limit, "http_size_limit")

def api(path):
    deadline()
    req = urllib.request.Request("https://api.github.com/repos/" + LOCK["repository"] + path,
          headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                   "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(read_bounded(r, 2097152))

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def download():
    a = LOCK["artifact"]
    run = api("/actions/runs/" + str(LOCK["producer_run"]))
    need(run["head_sha"] == LOCK["producer_source"] and run["run_attempt"] == 1, "producer_run_identity")
    need(run["status"] == "completed" and run["conclusion"] == "success", "producer_not_success")
    meta = api("/actions/artifacts/" + str(a["id"]))
    need(meta["id"] == a["id"] and meta["name"] == a["name"] and meta["size_in_bytes"] == a["bytes"], "artifact_identity")
    need(meta.get("expired") is False and meta.get("digest") == "sha256:" + a["sha256"], "artifact_digest_or_expired")
    wr = meta["workflow_run"]
    need(wr["id"] == LOCK["producer_run"] and wr["head_sha"] == LOCK["producer_source"], "artifact_source")
    REPORT["producer_api"] = {"run": run["id"], "attempt": run["run_attempt"], "source": run["head_sha"],
                             "artifact_id": meta["id"], "artifact_name": meta["name"], "bytes": meta["size_in_bytes"],
                             "digest": meta["digest"], "created_at": meta["created_at"]}
    req = urllib.request.Request("https://api.github.com/repos/" + LOCK["repository"] +
                                "/actions/artifacts/" + str(a["id"]) + "/zip",
                                headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"]})
    # Never forward the GitHub authorization header to the signed download host.
    try:
        response = urllib.request.build_opener(NoRedirect).open(req, timeout=25)
    except urllib.error.HTTPError as e:
        need(e.code in (301, 302, 303, 307, 308), "artifact_download_http_" + str(e.code))
        location = e.headers.get("Location", "")
        need(location.startswith("https://"), "artifact_redirect_not_https")
        response = urllib.request.urlopen(location, timeout=30)
    with response:
        data = read_bounded(response, a["bytes"])
    need(len(data) == a["bytes"] and sha(data) == a["sha256"], "archive_bytes_digest")
    return data

def archive_members(data):
    output = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        seen = set()
        total = 0
        for info in z.infolist():
            deadline()
            name = info.filename
            p = PurePosixPath(name)
            need(name and not p.is_absolute() and "\\" not in name and ":" not in name
                 and all(x not in ("", ".", "..") for x in name.rstrip("/").split("/")), "unsafe_entry")
            need(name not in seen, "duplicate_entry")
            seen.add(name)
            need(not stat.S_ISLNK(info.external_attr >> 16), "symlink_entry")
            need(not (info.flag_bits & 1), "encrypted_entry")
            if info.is_dir():
                continue
            total += info.file_size
            need(info.file_size <= 134217728 and total <= 536870912, "uncompressed_limit")
            body = z.read(info)
            need(len(body) == info.file_size, "entry_size")
            output[name] = body
    return output

def authenticate(files):
    need("manifest.json" in files, "manifest_missing")
    m = json.loads(files["manifest.json"])
    need(m["schema"] == 1 and m["source"] == LOCK["producer_source"]
         and str(m["run"]) == str(LOCK["producer_run"]) and str(m["attempt"]) == "1", "manifest_identity")
    need(m.get("manifest_excluded_from_own_inventory") is True, "manifest_exclusion")
    inventory = m["files"]
    need(set(inventory) == set(files) - {"manifest.json"}, "inventory_closure")
    for name, item in inventory.items():
        need(len(files[name]) == item["bytes"] and sha(files[name]) == item["sha256"], "entry_integrity:" + name)
    need(m.get("F07_accepted") is False and m.get("formal_count_changed") is False, "historical_flags_changed")
    return m

def canonical(path):
    return ntpath.normcase(ntpath.normpath(path))

def map_rows(text):
    rows = []
    # Parse actual public-symbol rows, not strings merely mentioning sqlite3.
    pattern = re.compile(r"^\s*([0-9A-Fa-f]{4}:[0-9A-Fa-f]+)\s+(\S+)\s+([0-9A-Fa-f]{8,16})\s+(.+?)\s*$")
    for line_no, line in enumerate(text.splitlines(), 1):
        m = pattern.match(line)
        if m and re.match(r"^_?sqlite3_", m[2]):
            tail = m[4].split()
            while tail and tail[0] in ("f", "i"):
                tail.pop(0)
            rows.append({"line": line_no, "section_offset": m[1], "symbol": m[2],
                         "address": m[3], "owner": " ".join(tail), "raw": line})
    return rows

def rsp_libraries(text, cwd):
    # Retain exact spellings; accept only closed quoted or whitespace-separated .lib tokens.
    need(text.count('"') % 2 == 0, "rsp_unbalanced_quotes")
    tokens = re.findall(r'"[^"\r\n]*\.lib"|[^\s"]+\.lib(?=\s|$)', text, flags=re.I)
    records = []
    for token in tokens:
        spelling = token.strip('"')
        if spelling.startswith(("/", "-")) and not ntpath.isabs(spelling):
            continue
        resolved = spelling if ntpath.isabs(spelling) else ntpath.join(cwd, spelling)
        records.append({"spelling": spelling, "resolved": canonical(resolved)})
    return records

def correlate(rows, libraries, known):
    bindings = []
    for row in rows:
        owner = row["owner"]
        item = dict(row, role=None, archive_bound=False, checks={})
        if ":" in owner:
            archive, member = owner.rsplit(":", 1)
            candidates = [x for x in libraries if
                          canonical(ntpath.splitext(ntpath.basename(x["spelling"]))[0]) ==
                          canonical(ntpath.splitext(ntpath.basename(archive))[0])]
            paths = sorted({x["resolved"] for x in candidates})
            roles = [role for role, path in known.items() if paths == [canonical(path)]]
            checks = {"sqlite_member": member.lower() in ("sqlite3.c.obj", "sqlite3.c.o"),
                      "one_rsp_path": len(paths) == 1, "known_archive": len(roles) == 1}
            item.update(member=member, map_archive=archive, rsp_paths=paths, checks=checks)
            if all(checks.values()):
                item.update(role=roles[0], archive_bound=True)
        bindings.append(item)
    return bindings

def controls():
    result = []
    def check(name, fn):
        need(fn(), "control_failed:" + name)
        result.append({"name": name, "passed": True})
    sample = " 0001:00000010 sqlite3_open_v2 0000000140001010 f exr_vendor_exr_sqlite:sqlite3.c.obj"
    known = {"sdk": r"D:\build\sdk\exr_vendor_exr_sqlite.lib"}
    libs = rsp_libraries(r'"D:\build\sdk\exr_vendor_exr_sqlite.lib"', r"D:\build\host")
    row = map_rows(sample)
    check("map_actual_symbol_positive", lambda: len(row) == 1)
    check("map_comment_not_symbol", lambda: map_rows("sqlite3_open_v2 exr_vendor_exr_sqlite") == [])
    check("bound_sdk_positive", lambda: correlate(row, libs, known)[0]["archive_bound"])
    check("missing_library_negative", lambda: not correlate(row, [], known)[0]["archive_bound"])
    check("foreign_archive_negative", lambda: not correlate(row, libs, {"sdk": r"D:\foreign\exr_vendor_exr_sqlite.lib"})[0]["archive_bound"])
    check("duplicate_basename_negative", lambda: not correlate(row, libs + [{"spelling": r"D:\other\exr_vendor_exr_sqlite.lib", "resolved": canonical(r"D:\other\exr_vendor_exr_sqlite.lib")}], known)[0]["archive_bound"])
    check("non_sqlite_member_negative", lambda: not correlate(map_rows(sample.replace("sqlite3.c.obj", "unrelated.obj")), libs, known)[0]["archive_bound"])
    check("bare_object_unbound", lambda: not correlate(map_rows(sample.replace("exr_vendor_exr_sqlite:sqlite3.c.obj", "sqlite3.c.obj")), libs, known)[0]["archive_bound"])
    def badzip(name, duplicate=False):
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            z.writestr(name, b"x")
            if duplicate:
                z.writestr(name, b"y")
        try:
            archive_members(b.getvalue())
            return False
        except ValueError:
            return True
    check("zip_traversal_negative", lambda: badzip("../bad"))
    check("zip_duplicate_negative", lambda: badzip("same", True))
    check("no_loaded_not_automatic_failure", lambda: correlate(row, libs, known)[0]["archive_bound"])
    return result

def observe(files, manifest):
    required = ["summary.json", "commands.json", "host/windows-host.map",
                "host-build/CMakeFiles/EXReaderWave3.rsp", "logs/host-build.log",
                "archives/sdk-build.lib", "archives/sdk-installed.lib", "archives/product-installed.lib",
                "host/EXReaderWave3.exe", "host/EXReader.exe", "logs/host-imports.log"]
    for name in required:
        need(name in files, "required_entry_missing:" + name)
    summary = json.loads(files["summary.json"])
    need(summary["diagnostic_completed"] is True and summary["errors"] == [], "producer_collection_failed")
    need(summary["source"] == LOCK["producer_source"] and str(summary["run"]) == str(LOCK["producer_run"])
         and str(summary["attempt"]) == "1", "summary_identity")
    commands = json.loads(files["commands.json"])
    need(commands and all(x["status"] == "completed" and x["returncode"] == 0 for x in commands), "producer_commands_failed")
    for name in ("sdk-build", "sdk-installed"):
        need(sha(files["archives/" + name + ".lib"]) == LOCK["sdk_sha256"], "sdk_digest")
    need(files["archives/sdk-build.lib"] == files["archives/sdk-installed.lib"], "sdk_bytes_differ")
    need(sha(files["archives/product-installed.lib"]) == LOCK["product_sha256"], "product_digest")
    need(files["host/EXReaderWave3.exe"] == files["host/EXReader.exe"], "host_package_differ")
    need(sha(files["logs/host-build.log"]) == LOCK["host_log_sha256"], "original_log_digest")
    entries = manifest["files"]
    host_dir = ntpath.dirname(entries["host/windows-host.map"]["actual_path"])
    need(ntpath.isabs(host_dir), "host_build_dir_not_absolute")
    known = {"sdk": entries["archives/sdk-installed.lib"]["actual_path"],
             "product": entries["archives/product-installed.lib"]["actual_path"]}
    need(all(ntpath.isabs(p) for p in known.values()), "archive_path_not_absolute")
    map_text = files["host/windows-host.map"].decode("utf-8-sig", errors="strict")
    rsp_text = files["host-build/CMakeFiles/EXReaderWave3.rsp"].decode("utf-8-sig", errors="strict")
    rows = map_rows(map_text)
    libs = rsp_libraries(rsp_text, host_dir)
    binding = correlate(rows, libs, known)
    log = files["logs/host-build.log"].decode("utf-8", errors="strict")
    roles = sorted({r["role"] for r in binding if r["archive_bound"]})
    all_bound = bool(binding) and all(x["archive_bound"] for x in binding)
    classification = ("no_sqlite_public_map_rows" if not rows else
                      "unresolved_or_ambiguous_map_origin" if not all_bound else
                      "multiple_static_archive_roles_observed" if len(roles) != 1 else
                      "single_static_archive_role_observed")
    result = {"classification": classification, "sqlite_public_rows": binding,
              "rsp_libraries": libs, "host_build_directory": host_dir, "known_archives": known,
              "static_archive_roles": roles, "all_observed_map_rows_bound": all_bound,
              "original_loaded_line_count": len(re.findall(r"(?mi)^\s*Loaded\s+", log)),
              "system_sqlite_import_observed": bool(re.search(r"(?i)(?:lib)?sqlite3[^\s/]*\.dll", files["logs/host-imports.log"].decode("utf-8", errors="replace"))),
              "provider_certified": False, "runtime_provider_observed": False,
              "scope": "Existing authenticated static link evidence only; no product execution or full F07 clause acceptance."}
    put("map-rsp-observation.json", result)
    put("entry-inventory.json", [{"name": name, "bytes": len(body), "sha256": sha(body)} for name, body in sorted(files.items())])
    # Small actual text evidence; no binary payload is executed or republished.
    (OUT / "original-map.txt").write_bytes(files["host/windows-host.map"])
    (OUT / "original-link.rsp").write_bytes(files["host-build/CMakeFiles/EXReaderWave3.rsp"])
    REPORT["observation"] = result

def main():
    OUT.mkdir(parents=True, exist_ok=False)
    try:
        admission()
        REPORT["controls"] = controls()
        data = download()
        files = archive_members(data)
        manifest = authenticate(files)
        REPORT["artifact_authenticated"] = True
        REPORT["authenticated_entries"] = len(files)
        observe(files, manifest)
        REPORT["audit_completed"] = True
    except Exception as e:
        # Do not print signed artifact URLs or request headers.
        REPORT["errors"].append(type(e).__name__ + ":" + str(e) if not isinstance(e, urllib.error.URLError)
                                else type(e).__name__ + ":network_request_failed")
    finally:
        REPORT["elapsed_seconds"] = time.monotonic() - START
        put("result.json", REPORT)
        print("F07_ARTIFACT_AUDIT " + json.dumps(REPORT, ensure_ascii=False), flush=True)
    if not REPORT["audit_completed"]:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
