import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

BASE = "0f07b97837356ee225fda87e932496208d22b869"
PATHS = [
    ".github/workflows/f09-simulator-environment-20261102.yml",
    "docs/reader-total-progress/F09_SIMULATOR_ENVIRONMENT_20261102.md",
    "tools/f09_review/inspect_simulator_environment.py",
]
OUT = Path("build/f09-simulator-environment")
OUT.mkdir(parents=True, exist_ok=True)
DEADLINE = time.monotonic() + 240
REPORT = {
    "schema": 1, "acceptance_eligible": False,
    "source": os.environ.get("GITHUB_SHA"), "run": os.environ.get("GITHUB_RUN_ID"),
    "attempt": os.environ.get("GITHUB_RUN_ATTEMPT"), "base": BASE,
    "commands": [], "enumeration_invocations": 0,
    "observation_difference": "stdout/stderr regular files instead of original stdout PIPE; no causal claim",
    "service_health_inferred": False, "product_tests_executed": 0,
}
ACTIVE = None

def clean(s):
    s = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", s)
    s = "".join(c for c in s if c in "\n\t" or (ord(c) >= 32 and not 127 <= ord(c) <= 159))
    s = re.sub(r"(?i)(authorization\s*[:=]\s*)[^\r\n]+", r"\1[REDACTED]", s)
    s = re.sub(r"(?i)((?:password|access_token|client_secret|cookie)\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", s)
    s = re.sub(r"(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)", "[REDACTED]", s)
    s = re.sub(r"https?://[^\s]+", "[URL REDACTED]", s)
    return s

def budget(n):
    left = int(DEADLINE-time.monotonic())
    if left <= 0:
        raise TimeoutError("240 second orchestration ceiling")
    return min(n, left)

def digest(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()

def detail(p):
    with p.open("rb") as f:
        size = p.stat().st_size
        f.seek(max(0, size-4096))
        tail = f.read(4096).decode("utf-8", "replace")
    return {"file": p.name, "bytes": size, "sha256": digest(p),
            "redacted_tail": "\n".join(clean(tail).splitlines()[-40:])}

def own_group_cleanup(proc, record):
    # Only this Popen's new session/process group, never a discovered service PID.
    try:
        os.killpg(proc.pid, signal.SIGKILL)
        record["own_process_group_kill_sent"] = True
    except ProcessLookupError:
        record["own_process_group_already_gone"] = True
    proc.wait(timeout=5)

def command(args, name, seconds):
    global ACTIVE
    stdout, stderr = OUT/(name+".stdout"), OUT/(name+".stderr")
    record = {"name": name, "command": args, "limit_seconds": seconds,
              "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    REPORT["commands"].append(record)
    started = time.monotonic()
    record["started_monotonic"] = started
    proc = None
    try:
        with stdout.open("wb") as out, stderr.open("wb") as err:
            proc = subprocess.Popen(args, stdout=out, stderr=err, start_new_session=True)
            ACTIVE = proc
            record["pid"] = proc.pid
            try:
                proc.wait(timeout=budget(seconds))
            except subprocess.TimeoutExpired:
                record["timed_out"] = True
                record["poll_at_timeout"] = proc.poll()
                own_group_cleanup(proc, record)
            record["returncode"] = proc.returncode
    finally:
        if proc is not None and proc.poll() is None:
            own_group_cleanup(proc, record)
        ACTIVE = None
        record["ended_monotonic"] = time.monotonic()
        record["elapsed_seconds"] = round(record["ended_monotonic"]-started, 3)
        for label, p in [("stdout", stdout), ("stderr", stderr)]:
            if p.exists():
                record[label] = detail(p)
    return record

def process_snapshot(name):
    record = {"name": name, "command": ["ps", "-axo", "pid,ppid,stat,etime,comm"],
              "limit_seconds": 10}
    REPORT["commands"].append(record)
    started = time.monotonic()
    record["started_monotonic"] = started
    # No argv or environment; retain only relevant comm records.
    try:
        p = subprocess.run(record["command"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=budget(10), text=True)
        lines = [line for line in p.stdout.splitlines()
                 if "CoreSimulator" in line or re.search(r"(?:^|/)simctl\s*$", line)]
        record.update(returncode=p.returncode, relevant_processes=[clean(x) for x in lines[:80]],
                      relevant_count=len(lines), truncated=len(lines)>80,
                      stderr=clean(p.stderr[-1024:]))
    except subprocess.TimeoutExpired:
        record["timed_out"] = True
    record["ended_monotonic"] = time.monotonic()
    record["elapsed_seconds"] = round(record["ended_monotonic"]-started, 3)
    return record

code = 1
try:
    if os.environ.get("GITHUB_ACTIONS") != "true" or REPORT["attempt"] != "1":
        raise RuntimeError("Actions attempt 1 only")
    changed = subprocess.check_output(["git", "diff", "--name-only", BASE, "HEAD"],
                                      text=True, timeout=budget(10)).splitlines()
    added = subprocess.check_output(["git", "diff", "--diff-filter=A", "--name-only", BASE, "HEAD"],
                                    text=True, timeout=budget(10)).splitlines()
    if sorted(changed) != PATHS or sorted(added) != PATHS:
        raise RuntimeError("exact three new diagnostic paths required")
    REPORT["changed_paths"] = changed
    for args, name, seconds in [
        (["sw_vers"], "os-version", 10),
        (["uname", "-m"], "architecture", 10),
        (["xcode-select", "-p"], "developer-directory", 15),
        (["xcodebuild", "-version"], "xcode-version", 30),
        (["xcrun", "--find", "simctl"], "simctl-path", 15),
    ]:
        r = command(args, name, seconds)
        if r.get("timed_out") or r.get("returncode") != 0:
            raise RuntimeError("environment prerequisite failed: "+name)
    pre = process_snapshot("processes-before")
    if pre.get("timed_out") or pre.get("returncode") != 0:
        raise RuntimeError("process observation failed before enumeration")
    REPORT["enumeration_invocations"] = 1
    result = command(["xcrun", "simctl", "list", "devices", "available", "--json"],
                     "enumeration", 60)
    post = process_snapshot("processes-after")
    if result.get("timed_out") or result.get("returncode") != 0:
        raise RuntimeError("single enumeration did not complete successfully within 60 seconds")
    p = OUT/"enumeration.stdout"
    if p.stat().st_size > 4*1024*1024:
        raise RuntimeError("enumeration JSON exceeds 4 MiB inspection limit")
    data = json.loads(p.read_text())
    if not isinstance(data, dict) or not isinstance(data.get("devices"), dict):
        raise RuntimeError("unexpected enumeration schema")
    devices = []
    for runtime, rows in data["devices"].items():
        if not isinstance(runtime, str) or not isinstance(rows, list):
            raise RuntimeError("unexpected runtime rows")
        for row in rows:
            if not isinstance(row, dict):
                raise RuntimeError("unexpected device record")
            devices.append({k: row.get(k) for k in ("name", "udid", "state", "isAvailable")} |
                           {"runtime": runtime})
    if len(devices) > 200:
        raise RuntimeError("device summary exceeds 200 records")
    REPORT["devices"] = devices
    if post.get("timed_out") or post.get("returncode") != 0:
        raise RuntimeError("process observation failed after enumeration")
    REPORT["stop_reason"] = "one environment observation completed; no app or causal conclusion"
    code = 0
except Exception as exc:
    REPORT["stop_reason"] = clean(type(exc).__name__+": "+str(exc))
finally:
    if ACTIVE is not None and ACTIVE.poll() is None:
        own_group_cleanup(ACTIVE, REPORT)
    REPORT["exit_code"] = code
    (OUT/"report.json").write_text(json.dumps(REPORT, ensure_ascii=False, indent=2))
    print("F09_SIMULATOR_ENVIRONMENT_BEGIN")
    print(json.dumps(REPORT, ensure_ascii=False, indent=2))
    print("F09_SIMULATOR_ENVIRONMENT_END")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
        f.write("# F09 environment-only observation\n\n~~~json\n"+
                json.dumps(REPORT, ensure_ascii=False, indent=2)+"\n~~~\n")
sys.exit(code)
