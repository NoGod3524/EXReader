"""Authenticate one retained failed Android artifact and report only safe evidence."""
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

REPO = "NoGod3524/EXReader"
BRANCH = "codex/gpt-f02-android-online-evidence-20261031"
BASE = "f47f7c374524d2774e9a61cba44f63a5b7580916"
SOURCE = "fe947bec25a56f40538677ffa9fb2a5e1e351b08"
RUN = 41233481729
ARTIFACT = 13054812884
SIZE = 20160253
DIGEST = "f0370e0f441a6f34b764bb2e3e1be420d0f88106614684dc79525e5ccd1180a4"
PATHS = sorted([
    ".github/workflows/dot-f02-android-online-evidence-20261031.yml",
    "tools/reader_composition/f02_android_online_evidence_20261031.py",
    "docs/reader-total-progress/DOT_F02_ANDROID_ONLINE_EVIDENCE_20261031.md",
])
ONLINE_CHECKS = [
    "strict_sdk342_shared_provider",
    "fresh_activity_empty_sdk_and_mapping",
    "actual_sync_scans_sender_wire_without_import",
    "corrupt_original_rejected",
    "truncated_original_rejected",
    "cancel_blocked_receive_preserves_empty_library",
    "explicit_receive_imports_exact_original",
    "duplicate_receive_keeps_one_sdk_mapping",
    "actual_online_reader",
    "cancelled_copy_has_no_publication",
    "abandoned_copy_has_no_publication",
    "wrong_original_is_refused",
    "closed_host_sdk_original",
]
OUT = Path("build/f02-android-online-evidence")
EXPECTED = {"source": SOURCE, "run": RUN, "attempt": 1}

def need(value, reason):
    if not value:
        raise AssertionError(reason)

def api(path):
    request = urllib.request.Request(
        "https://api.github.com/repos/" + REPO + "/" + path,
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read(4 * 1024 * 1024 + 1)
    need(len(raw) <= 4 * 1024 * 1024, "bounded API response")
    return json.loads(raw)

def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()

def own_identity():
    return {"source": os.environ["GITHUB_SHA"], "run": int(os.environ["GITHUB_RUN_ID"]),
            "attempt": int(os.environ["GITHUB_RUN_ATTEMPT"])}

def guard():
    need(os.environ.get("GITHUB_ACTIONS") == "true", "Actions only")
    need(os.environ.get("GITHUB_REPOSITORY") == REPO, "repository")
    need(os.environ.get("GITHUB_REF_NAME") == BRANCH, "exclusive diagnostic branch")
    need(os.environ.get("GITHUB_EVENT_NAME") == "push", "push only")
    need(own_identity()["attempt"] == 1, "one diagnostic attempt")
    need(git("rev-parse", "HEAD") == own_identity()["source"], "diagnostic source")
    need(git("rev-parse", "HEAD^") == BASE, "fixed diagnostic parent")
    need(git("rev-parse", BASE + "^") == SOURCE, "sealed producer source")
    need(sorted(git("diff", "--name-only", BASE, "HEAD").splitlines()) == PATHS
         and all(line.startswith("A\t") for line in git("diff", "--name-status", BASE, "HEAD").splitlines()),
         "exact three new paths")
    need(all(git("cat-file", "-t", "HEAD:" + p) == "blob" for p in PATHS),
         "three ordinary source blobs")
    query = "actions/runs?branch=" + urllib.parse.quote(BRANCH, safe="") + "&per_page=100"
    runs = api(query)
    need(runs["total_count"] == 1 and runs["workflow_runs"][0]["id"] == own_identity()["run"],
         "sole diagnostic run")

def download():
    run = api("actions/runs/" + str(RUN))
    need(run["head_sha"] == SOURCE and run["run_attempt"] == 1
         and run["status"] == "completed" and run["conclusion"] == "failure",
         "fixed failed producer identity")
    jobs = api("actions/runs/" + str(RUN) + "/attempts/1/jobs?per_page=100")["jobs"]
    need(any(j["id"] == 124632394760 and j["name"] == "android"
             and j["status"] == "completed" and j["conclusion"] == "failure" for j in jobs),
         "fixed failed Android job")
    meta = api("actions/artifacts/" + str(ARTIFACT))
    need(meta["id"] == ARTIFACT and meta["name"] == "f02-android-receiver-41233481729-1"
         and meta["size_in_bytes"] == SIZE and meta["digest"] == "sha256:" + DIGEST
         and not meta["expired"] and meta["workflow_run"]["id"] == RUN
         and meta["workflow_run"]["head_sha"] == SOURCE, "artifact API identity")
    request = urllib.request.Request(
        "https://api.github.com/repos/" + REPO + "/actions/artifacts/" + str(ARTIFACT) + "/zip",
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                 "Accept": "application/vnd.github+json"},
    )
    # A temporary input stays outside the uploaded output directory.
    target = Path("build/f02-original-receiver.zip")
    class SignedArtifactRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            parsed = urllib.parse.urlparse(newurl)
            need(parsed.scheme == "https" and not parsed.username and not parsed.password
                 and parsed.hostname and (parsed.hostname.endswith(".blob.core.windows.net")
                                           or parsed.hostname.endswith(".githubusercontent.com")),
                 "trusted HTTPS artifact redirect")
            redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
            if redirected is not None:
                redirected.remove_header("Authorization")
            return redirected
    opener = urllib.request.build_opener(SignedArtifactRedirect())
    with opener.open(request, timeout=90) as response, target.open("xb") as output:
        total = 0
        digest = hashlib.sha256()
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            need(total <= SIZE, "bounded original ZIP bytes")
            digest.update(block)
            output.write(block)
    need(total == SIZE and digest.hexdigest() == DIGEST, "original ZIP bytes and SHA256")
    return target, {"id": ARTIFACT, "name": meta["name"], "bytes": total,
                    "sha256": digest.hexdigest(), "producer": EXPECTED}

def inspect(target):
    inventory = []
    with zipfile.ZipFile(target) as archive:
        members = archive.infolist()
        need(0 < len(members) <= 256, "bounded ZIP member count")
        seen = set()
        total = 0
        for entry in members:
            name = entry.filename
            path = PurePosixPath(name)
            need(name and len(name) <= 240 and not path.is_absolute()
                 and "\\" not in name and "\x00" not in name and ":" not in name
                 and all(part not in ("", ".", "..") for part in name.rstrip("/").split("/"))
                 and name == path.as_posix() + ("/" if entry.is_dir() else ""),
                 "safe canonical ZIP member path")
            key = name.rstrip("/").casefold()
            need(key not in seen, "no duplicate or case-alias member")
            seen.add(key)
            mode = entry.external_attr >> 16
            kind = stat.S_IFMT(mode)
            need(kind in (0, stat.S_IFREG, stat.S_IFDIR) and not entry.flag_bits & 1,
                 "no symlink, special or encrypted member")
            need(entry.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                 and entry.file_size <= 64 * 1024 * 1024, "bounded ZIP member")
            total += entry.file_size
            need(total <= 128 * 1024 * 1024, "bounded ZIP total")
            digest = hashlib.sha256()
            length = 0
            with archive.open(entry) as stream:
                while True:
                    block = stream.read(1024 * 1024)
                    if not block:
                        break
                    length += len(block)
                    need(length <= entry.file_size, "bounded decompression")
                    digest.update(block)
            need(length == entry.file_size, "ZIP member length and CRC")
            inventory.append({"path": name, "bytes": length, "sha256": digest.hexdigest()})
        names = {entry.filename for entry in members}
        def read(name):
            need(name in names, "required evidence member " + name)
            need(archive.getinfo(name).file_size <= 2 * 1024 * 1024, "bounded text evidence")
            return archive.read(name)
        producer = json.loads(read("report.json"))
        online = json.loads(read("online-report.json"))
        build = json.loads(read("build.json"))
        instrumentation = read("online-instrumentation.txt").decode("utf-8")
        need(producer["identity"] == EXPECTED and online["identity"] == EXPECTED
             and build["identity"] == EXPECTED, "embedded producer identities")
        need(producer["accepted"] is False and online["phase"] == "online"
             and len(producer["phases"]) == 1 and producer["phases"][0] == online,
             "one retained online phase")
        checks = online["checks"]
        need(isinstance(checks, list) and online["count"] == len(checks)
             and all(c["name"] in ONLINE_CHECKS and isinstance(c["passed"], bool) for c in checks),
             "known online check records")
        active = online.get("active_check")
        need(active is None or active in ONLINE_CHECKS, "known failed check")
        failure_type = online.get("failure_type")
        need(failure_type is None or re.fullmatch(r"[A-Za-z0-9_$]{1,96}", failure_type),
             "safe failure class")
        native = {"present": "proc-online.txt" in names}
        if native["present"]:
            raw = read("proc-online.txt")
            pid = re.search(rb"^Pid:\s+([0-9]+)\s*$", raw, re.M)
            uid = re.search(rb"^Uid:\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s*$", raw, re.M)
            need(pid and uid, "native PID and UID records")
            native.update(pid=int(pid[1]), uids=[int(x) for x in uid.groups()],
                          matches_report=int(pid[1]) == online["pid"] and int(uid[1]) == online["uid"],
                          sha256=hashlib.sha256(raw).hexdigest())
        codes = [int(v) for v in re.findall(r"^INSTRUMENTATION_CODE:\s*(-?[0-9]+)\s*$",
                                          instrumentation, re.M)]
        streams = re.findall(r"F02_ANDROID online checks=([0-9]+) passed=(true|false)",
                             instrumentation)
        result = {
            "producer_passed": producer["accepted"], "online_passed": online["passed"],
            "completed_checks": [{"name": c["name"], "passed": c["passed"]} for c in checks],
            "completed_count": len(checks), "active_check": active, "failure_type": failure_type,
            "native_evidence": native,
            "instrumentation_final_codes": codes,
            "instrumentation_summaries": [{"checks": int(n), "passed": b == "true"} for n, b in streams],
            "adb_process_exit_code": None,
            "adb_process_exit_code_evidence": "Not persisted as a separate value; original producer required returncode==0 before this report guard.",
            "inner_assertion_message": None,
            "inner_assertion_evidence": "Original Java report retains failure_type and active_check, not exception message or stack.",
            "offline_reached": False, "independent12_controls_executed": False,
            "root_cause_complete": False,
            "evidence_limitations": [
                "Exact inner exception message and stack were not retained by the original Java report.",
                "The adb process return code was not persisted as its own field.",
            ] + ([] if native["present"] else ["Raw native process evidence is absent."])
              + ([] if codes else ["Final instrumentation result code is absent."]),
            "redacted_reason": "Original online phase stopped in the recorded active_check; exact inner assertion/exception text was not retained. No emulator-startup warning is assigned as root cause.",
            "redaction": "Only fixed identities, known check names, numeric process/result values and a bounded exception class are published; no arbitrary report strings, URLs or credentials.",
        }
    return result, inventory

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {"diagnostic": own_identity(), "producer": EXPECTED, "artifact_verified": False,
               "diagnosis_completed": False, "F02_accepted": False, "formal": "95/108"}
    ok = False
    try:
        guard()
        target, artifact = download()
        summary.update(artifact=artifact, artifact_verified=True)
        result, inventory = inspect(target)
        summary.update(diagnosis_completed=True, result=result)
        (OUT / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")
        ok = True
    except Exception as error:
        # API and arbitrary application error messages are never echoed.
        summary["diagnostic_error"] = type(error).__name__
        if isinstance(error, AssertionError):
            summary["diagnostic_reason"] = str(error)[:180]
    finally:
        (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print("F02_ANDROID_ONLINE_DIAGNOSTIC " + json.dumps(summary), flush=True)
    if not ok:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
