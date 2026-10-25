#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""S08 platform runner: real red-action acceptance of diagnostics and accounts.

The job generates every secret with the OS CSPRNG, drives the installed public
APIs of the three existing owner modules through normal, failure, cancellation
and reopen paths, and scans the complete transcript, every phase log, the
isolated stores, the temporary home, the installed modules, the consumer binary
and the artifact payload for each secret in raw/hex/base64/percent/UTF-16 form.
Diagnostics must stay useful: status names, numeric statuses, system errors,
document offsets and redacted request lines are all required, and no message may
degenerate to REDACTED or to an empty string.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from scan import judge_diagnostics, scan_paths, selfcheck, text_forms, value_forms

FIXED_BASE = "0889f7d1e9a537c6c1b05456547e016b26e1cd85"
CHECK_DETAIL = re.compile(r"[A-Za-z0-9_=,.:/ -]{0,160}")

OPDS_CHECKS = [
    "opds-normal-downloaded", "opds-normal-log-count", "opds-normal-log-method",
    "opds-normal-log-status", "opds-normal-log-removes-userinfo", "opds-normal-log-redacts-token",
    "opds-normal-log-keeps-source", "opds-normal-log-no-authorization",
    "opds-normal-request-carried-exact-authorization",
    "opds-401-status", "opds-401-http-status", "opds-401-scheme", "opds-401-log-status",
    "opds-401-log-no-secret", "opds-401-message-useful",
    "opds-500-status", "opds-500-http-status", "opds-500-log-status", "opds-500-log-no-secret",
    "opds-cancel-status", "opds-cancel-log-status", "opds-cancel-log-no-secret",
    "opds-cancel-no-file",
    "opds-redirect-status", "opds-redirect-two-lines", "opds-redirect-first-302",
    "opds-redirect-second-200", "opds-redirect-drops-credential", "opds-redirect-stats",
    "opds-redirect-log-no-secret",
    "opds-redact-contract", "opds-redact-truncation", "opds-redact-truncation-no-secret",
    "opds-redact-long-input",
]
CREDENTIAL_CHECKS = [
    "cred-open-rejects-invalid-namespace", "cred-open", "cred-empty-get-not-found",
    "cred-empty-delete-not-found", "cred-put", "cred-get-read-back", "cred-update",
    "cred-update-no-stale", "cred-put-other-account", "cred-account-isolation",
    "cred-open-second-namespace", "cred-namespace-isolation", "cred-put-second-namespace",
    "cred-small-buffer", "cred-small-buffer-untouched", "cred-invalid-account",
    "cred-zero-length", "cred-put-binary", "cred-binary-exact", "cred-put-unicode",
    "cred-unicode-exact", "cred-put-maximum", "cred-maximum-exact", "cred-delete",
    "cred-delete-again", "cred-status-names", "cred-no-message-surface",
]
PROFILE_CHECKS = [
    "profiles-empty-load", "profiles-add-a", "profiles-add-b-same-url",
    "profiles-add-c-same-account", "profiles-load-three", "profiles-order-and-fields",
    "profiles-activation-a", "profiles-activation-plan-fields", "profiles-activation-verify",
    "profiles-account-isolation", "profiles-reject-userinfo", "profiles-userinfo-message-useful",
    "profiles-reject-query", "profiles-reject-bad-uuid", "profiles-reject-control-name",
    "profiles-reject-space-name", "profiles-reject-relative-store",
    "profiles-argument-diagnostic", "profiles-cancel-immediate",
    "profiles-cancel-immediate-unchanged", "profiles-cancel-before-commit",
    "profiles-cancel-before-commit-unchanged", "profiles-cancel-diagnostic-retained",
    "profiles-cancel-no-temp", "profiles-version-diagnostic", "profiles-format-diagnostic",
    "profiles-io-diagnostic", "profiles-limit-fill", "profiles-limit-refused",
    "profiles-rename", "profiles-rename-applied", "profiles-marker-created", "profiles-remove",
    "profiles-remove-absent", "profiles-remove-record-only", "profiles-remove-keeps-directory",
]
WORKER_CHECKS = ["worker-add-profile", "worker-credentials-open", "worker-put", "worker-exit"]
REOPEN_CHECKS = [
    "reopen-profiles-persist", "reopen-profile-generation", "reopen-credentials-open",
    "reopen-worker-credential-exact", "reopen-other-account-exact", "reopen-absent-account",
]
CLEANUP_CHECKS = [
    "cleanup-credentials-removed", "cleanup-remove-a", "cleanup-remove-c", "cleanup-remove-d",
    "cleanup-second-namespace",
]
VERIFY_CHECKS = ["verify-credential-absent", "verify-clean-account-c", "verify-profiles-absent"]
UNAVAILABLE_CHECKS = ["cred-open-rejects-invalid-namespace", "cred-open", "unavailable-put",
                      "unavailable-get-absent", "unavailable-get-existing", "unavailable-delete"]
VERIFY_UNAVAILABLE_CHECKS = ["verify-unavailable-wrote-nothing",
                             "verify-unavailable-second-namespace"]

TRANSCRIPT = None


def say(line: str = "") -> None:
    print(line, flush=True)
    if TRANSCRIPT is not None:
        TRANSCRIPT.write(line + "\n")
        TRANSCRIPT.flush()


def make_material(root: Path) -> dict:
    values = {
        "primary": secrets.token_bytes(64),
        "update": secrets.token_bytes(24),
        "other": secrets.token_bytes(32),
        "binary": b"\x00\x01" + secrets.token_bytes(30) + b"\x00\xfe\xff",
        "unicode": ("pässwörd-密码-🔑-" + secrets.token_hex(8)).encode("utf-8"),
        "max": secrets.token_bytes(2048),
        "reopen": secrets.token_bytes(48),
    }
    texts = {
        "authorization": "Bearer " + secrets.token_hex(20),
        "cookie": "session=" + secrets.token_hex(16),
        "userinfo-user": "u" + secrets.token_hex(6),
        "userinfo-password": secrets.token_hex(10),
        "token": secrets.token_hex(20),
    }
    stores = {}
    for name in ("store", "store-version", "store-format", "store-limit"):
        path = root / name
        path.mkdir(parents=True, exist_ok=True)
        stores[name] = str(path)
    (root / "download").mkdir(parents=True, exist_ok=True)
    stores["download-dir"] = str(root / "download")
    io_parent = root / "io-parent"
    io_parent.write_bytes(b"regular file in the way of a store\n")
    stores["store-io"] = str(io_parent / "store")
    # Bytes only: a text-mode write would turn 
 into 
 on Windows and make
    # the canonical-shape check fail before it can report VERSION/FORMAT.
    (root / "store-version" / "profiles.json").write_bytes(
        b'{\n  "format": "reader-account-profiles",\n  "version": 7,\n  "generation": 0,\n'
        b'  "profiles": []\n}\n')
    (root / "store-format" / "profiles.json").write_bytes(
        b'{\n  "format": "reader-account-profiles",\n  "version": 1,\n  "generation": 0,\n'
        b'  "profiles": [ ]\n}\n')
    identity = {
        "namespace": "test.exr-s08." + secrets.token_hex(8),
        "namespace2": "test.exr-s08." + secrets.token_hex(8),
        "account-a": str(uuid.uuid4()), "account-b": str(uuid.uuid4()),
        "account-c": str(uuid.uuid4()), "account-d": str(uuid.uuid4()),
        "account-u": str(uuid.uuid4()),
        "profile-a": str(uuid.uuid4()), "profile-b": str(uuid.uuid4()),
        "profile-c": str(uuid.uuid4()), "profile-d": str(uuid.uuid4()),
        "profile-cancel": str(uuid.uuid4()),
        "url-1": "https://" + secrets.token_hex(6) + ".example/reader/",
        "url-2": "https://" + secrets.token_hex(6) + ".example/reader/",
        "name-a": secrets.token_hex(6), "name-b": secrets.token_hex(6),
        "name-c": secrets.token_hex(6), "name-d": secrets.token_hex(6),
        "name-renamed": secrets.token_hex(6),
    }
    return {"values": values, "texts": texts, "stores": stores, "identity": identity}


def build_input(material: dict) -> bytes:
    lines = []
    for name, value in material["stores"].items():
        lines.append("text %s %s" % (name, value))
    for name, value in material["identity"].items():
        lines.append("text %s %s" % (name, value))
    for name, value in material["texts"].items():
        lines.append("text %s %s" % (name, value))
    for name, value in material["values"].items():
        lines.append("secret %s %s" % (name, value.hex()))
    return ("\n".join(lines) + "\n").encode("utf-8")


def parse_output(text: str) -> dict:
    checks = []
    phases = []
    diags = []
    other = []
    for line in text.splitlines():
        if line.startswith("check "):
            parts = line.split(" ", 3)
            if len(parts) < 3:
                other.append("malformed check line")
                continue
            identifier = parts[1]
            result = parts[2]
            detail = parts[3] if len(parts) > 3 else ""
            checks.append({"id": identifier, "result": result, "detail": detail})
        elif line.startswith("phase "):
            parts = line.split(" ")
            if len(parts) != 3 or "/" not in parts[2]:
                other.append("malformed phase line")
                continue
            passed, total = parts[2].split("/", 1)
            phases.append({"phase": parts[1], "passed": int(passed), "total": int(total)})
        elif line.startswith("diag "):
            try:
                diags.append(json.loads(line[5:]))
            except json.JSONDecodeError:
                other.append("malformed diag line")
        elif line.strip():
            other.append("unexpected output line")
    return {"checks": checks, "phases": phases, "diags": diags, "other": other}


class Service:
    """Private D-Bus session plus gnome-keyring for the Linux job only."""

    def __init__(self, root: Path):
        self.root = root
        self.env = None
        self.bus_pid = None
        self.keyring_pid = None
        self.collection = None
        self.notes = {}

    def start(self) -> None:
        home = self.root / "home"
        runtime = self.root / "run"
        home.mkdir()
        runtime.mkdir(mode=0o700)
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("DBUS_", "GNOME_KEYRING", "XDG_"))}
        env.update(HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
                   XDG_DATA_HOME=str(home / ".local/share"),
                   XDG_CONFIG_HOME=str(home / ".config"),
                   XDG_CACHE_HOME=str(home / ".cache"))
        bus = subprocess.run(
            ["dbus-daemon", "--session", "--fork", "--print-address=1", "--print-pid=1",
             "--address=unix:path=%s/bus" % runtime],
            capture_output=True, text=True, env=env, timeout=60)
        if bus.returncode != 0:
            raise RuntimeError("dbus-daemon failed: " + bus.stderr.strip()[:200])
        address, pid = (bus.stdout.split("\n") + ["", ""])[:2]
        env["DBUS_SESSION_BUS_ADDRESS"] = address.strip()
        self.bus_pid = pid.strip() or None
        self.password = secrets.token_hex(16)
        self.env = env
        self._start_keyring()
        self.collection = self._default_collection()
        self.notes = {"bus": "private dbus-daemon --session",
                      "service": "gnome-keyring-daemon --components=secrets",
                      "home": "temporary isolated HOME",
                      "default_collection": self.collection}

    def _start_keyring(self) -> None:
        daemon_out = self.root / ("keyring-env-%d.txt" % int(time.time() * 1000))
        with open(daemon_out, "w", encoding="utf-8") as handle:
            subprocess.run(["gnome-keyring-daemon", "--daemonize", "--unlock",
                            "--components=secrets"], input=self.password, stdout=handle,
                           stderr=subprocess.STDOUT, text=True, env=self.env, timeout=90)
        for line in daemon_out.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                if key.startswith(("SSH_", "GNOME_", "SECRET_")):
                    self.env[key] = value
        self._wait_service()
        probe = subprocess.run(["pgrep", "-u", str(os.getuid()), "-n", "gnome-keyring-d"],
                               capture_output=True, text=True)
        self.keyring_pid = probe.stdout.strip() or None

    def restart(self) -> None:
        if self.keyring_pid:
            subprocess.run(["kill", self.keyring_pid], check=False)
            time.sleep(1)
        self._start_keyring()

    def locked(self) -> bool:
        if not self.collection:
            return False
        state = self._gdbus(self.collection, "org.freedesktop.DBus.Properties.Get",
                            "org.freedesktop.Secret.Collection", "Locked")
        return "true" in state

    def _gdbus(self, path: str, method: str, *args: str) -> str:
        done = subprocess.run(["gdbus", "call", "--session", "--dest", "org.freedesktop.secrets",
                               "--object-path", path, "--method", method, *args],
                              capture_output=True, text=True, env=self.env, timeout=60)
        return done.stdout + done.stderr

    def _wait_service(self) -> None:
        for _ in range(60):
            done = subprocess.run(["gdbus", "call", "--session", "--dest", "org.freedesktop.DBus",
                                   "--object-path", "/org/freedesktop/DBus", "--method",
                                   "org.freedesktop.DBus.NameHasOwner",
                                   "org.freedesktop.secrets"],
                                  capture_output=True, text=True, env=self.env, timeout=20)
            if "true" in done.stdout:
                return
            time.sleep(0.5)
        raise RuntimeError("org.freedesktop.secrets never appeared")

    def _default_collection(self) -> str | None:
        alias = self._gdbus("/org/freedesktop/secrets",
                            "org.freedesktop.Secret.Service.ReadAlias", "default")
        if "collection/" not in alias:
            self._gdbus("/org/freedesktop/secrets", "org.freedesktop.Secret.Service.SetAlias",
                        "default", "objectpath '/org/freedesktop/secrets/collection/login'")
            alias = self._gdbus("/org/freedesktop/secrets",
                                "org.freedesktop.Secret.Service.ReadAlias", "default")
        match = re.search(r"'(/org/freedesktop/secrets/collection/[^']+)'", alias)
        return match.group(1) if match else None

    def lock(self) -> dict:
        if not self.collection:
            return {"locked": False, "reason": "no default collection"}
        self._gdbus("/org/freedesktop/secrets", "org.freedesktop.Secret.Service.Lock",
                    "@ao ['%s']" % self.collection)
        state = self._gdbus(self.collection, "org.freedesktop.DBus.Properties.Get",
                            "org.freedesktop.Secret.Collection", "Locked")
        return {"locked": "true" in state, "state": state.strip()[:60]}

    def unlock(self) -> None:
        if self.collection:
            self._gdbus("/org/freedesktop/secrets", "org.freedesktop.Secret.Service.Unlock",
                        "@ao ['%s']" % self.collection)

    def stop(self) -> None:
        for pid in (self.keyring_pid, self.bus_pid):
            if pid:
                subprocess.run(["kill", pid], check=False)
        time.sleep(1)
        shutil.rmtree(self.root, ignore_errors=True)


def run_phase(consumer: str, label: str, phase: str, expected: list, env, payload: bytes,
              output: Path, index: int, timeout: int = 420) -> dict:
    prefix = "%02d-%s" % (index, label)
    started = time.time()
    try:
        done = subprocess.run([consumer, phase], input=payload, capture_output=True, env=env,
                              timeout=timeout)
        stdout = done.stdout.decode("utf-8", "replace")
        stderr = done.stderr.decode("utf-8", "replace")
        code = done.returncode
    except subprocess.TimeoutExpired as error:
        stdout = (error.stdout or b"").decode("utf-8", "replace")
        stderr = (error.stderr or b"").decode("utf-8", "replace") + "\ntimeout\n"
        code = None
    (output / "logs" / (prefix + ".stdout.log")).write_text(stdout, encoding="utf-8")
    (output / "logs" / (prefix + ".stderr.log")).write_text(stderr, encoding="utf-8")
    parsed = parse_output(stdout)
    ids = [item["id"] for item in parsed["checks"]]
    details_ok = all(CHECK_DETAIL.fullmatch(item["detail"] or "") for item in parsed["checks"])
    duplicates = len(ids) != len(set(ids))
    sets_ok = set(ids) == set(expected) and not duplicates
    all_pass = all(item["result"] == "pass" for item in parsed["checks"])
    phases_ok = (len(parsed["phases"]) == 1 and parsed["phases"][0]["phase"] == phase and
                 parsed["phases"][0]["passed"] == parsed["phases"][0]["total"] == len(expected))
    accepted = bool(code == 0 and sets_ok and all_pass and phases_ok and details_ok
                    and not parsed["other"])
    say("[%s] exit=%s checks=%d/%d accepted=%s %.1fs" % (
        label, code, len(ids), len(expected), accepted, time.time() - started))
    if not accepted:
        missing = sorted(set(expected) - set(ids))
        extra = sorted(set(ids) - set(expected))
        failed = [item["id"] for item in parsed["checks"] if item["result"] != "pass"]
        say("[%s] missing=%s extra=%s failed=%s phases=%s other=%s" % (
            label, missing, extra, failed, parsed["phases"], parsed["other"]))
        if stderr.strip():
            say("[%s] stderr tail: %s" % (label, stderr.strip()[-400:]))
    return {"label": label, "phase": phase, "exit": code, "checks": parsed["checks"],
            "expected": expected, "ids": ids, "phases": parsed["phases"], "diags": parsed["diags"],
            "accepted": accepted, "seconds": round(time.time() - started, 2)}


def manifest(output: Path) -> list:
    entries = []
    for path in sorted(output.rglob("*")):
        if not path.is_file() or path.name == "report.json":
            continue
        data = path.read_bytes()
        entries.append({"path": path.relative_to(output).as_posix(), "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest()})
    return entries


def main() -> int:
    global TRANSCRIPT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, choices=["windows", "linux"])
    parser.add_argument("--consumer", required=True)
    parser.add_argument("--credentials-prefix", required=True)
    parser.add_argument("--profiles-prefix", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--scan", action="append", default=[])
    parser.add_argument("--timeout", type=int, default=420)
    args = parser.parse_args()

    output = Path(args.output).resolve()
    (output / "logs").mkdir(parents=True, exist_ok=True)
    TRANSCRIPT = open(output / "transcript.log", "w", encoding="utf-8")
    root = Path(tempfile.mkdtemp(prefix="exr-s08-", dir=os.environ.get("RUNNER_TEMP")))
    material = make_material(root)
    payload = build_input(material)
    forms = value_forms(material["values"]) + text_forms(material["texts"])
    forbid = list(material["texts"].values()) + [material["identity"]["url-1"],
                                                 material["identity"]["url-2"],
                                                 material["identity"]["name-a"],
                                                 material["identity"]["name-b"],
                                                 material["identity"]["name-c"],
                                                 material["identity"]["name-d"],
                                                 material["identity"]["name-renamed"]]
    judge_context = {
        "forbidden": forbid,
        "label": "job input",
        "opds_source": "reader.test:8080",
        "opds_path": "/shelf/reader/",
        "require_unavailable": args.platform == "linux",
        "forbid_credentials_unavailable": args.platform == "windows",
        "minimum_diags": 40,
    }
    say("[s08] platform=%s source=%s run=%s attempt=%s" % (
        args.platform, os.environ.get("GITHUB_SHA", ""), os.environ.get("GITHUB_RUN_ID", ""),
        os.environ.get("GITHUB_RUN_ATTEMPT", "")))
    say("[s08] input bytes=%d secrets=%d text-secrets=%d forms=%d" % (
        len(payload), len(material["values"]), len(material["texts"]), len(forms)))

    service = None
    env = None
    if args.platform == "linux":
        service = Service(root / "service")
        (root / "service").mkdir()
        service.start()
        env = service.env
        say("[s08] private Secret Service ready collection=%s" % (service.collection,))

    plan = [
        ("opds", "opds", OPDS_CHECKS),
        ("credentials", "credentials", CREDENTIAL_CHECKS),
        ("profiles", "profiles", PROFILE_CHECKS),
        ("worker", "worker", WORKER_CHECKS),
        ("reopen", "reopen", REOPEN_CHECKS),
    ]
    if args.platform == "linux":
        plan += [
            ("unavailable-locked", "unavailable", UNAVAILABLE_CHECKS),
            ("unavailable-no-service", "unavailable", UNAVAILABLE_CHECKS),
            ("verify-unavailable-clean", "verify-unavailable-clean", VERIFY_UNAVAILABLE_CHECKS),
        ]
    plan += [("cleanup", "cleanup", CLEANUP_CHECKS), ("verify-clean", "verify-clean", VERIFY_CHECKS)]

    runs = []
    unavailable_observations = {}
    scans = {}
    not_exercised = []
    for index, (label, phase, expected) in enumerate(plan, start=1):
        phase_env = env
        if label == "unavailable-locked" and service is not None:
            unavailable_observations["locked"] = service.lock()
            say("[s08] collection lock: %s" % (unavailable_observations["locked"],))
            if not unavailable_observations["locked"].get("locked"):
                not_exercised.append("Linux locked collection: the default collection did not "
                                     "report Locked=true in this job")
        if label == "unavailable-no-service":
            base = dict(env or {})
            base["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=%s/no-such-bus" % (root / "service")
            phase_env = base
        if label == "verify-unavailable-clean" and service is not None:
            service.unlock()
            unlocked = False
            for _ in range(20):
                if not service.locked():
                    unlocked = True
                    break
                time.sleep(0.5)
            if not unlocked:
                service.restart()
                unlocked = not service.locked()
            unavailable_observations["unlocked_for_verify"] = unlocked
            say("[s08] service unlocked for the no-plaintext check: %s" % (unlocked,))
        entry = run_phase(args.consumer, label, phase, expected, phase_env, payload, output, index,
                          args.timeout)
        runs.append(entry)
        if label == "worker":
            scans["after-worker"] = scan_paths([root, output], forms)
            say("[s08] scan after worker exit: files=%d bytes=%d hits=%d" % (
                scans["after-worker"]["files"], scans["after-worker"]["bytes"],
                scans["after-worker"]["hits"]))
        if label == "profiles":
            scans["after-profiles"] = scan_paths([root], forms)
            say("[s08] scan after profiles: files=%d bytes=%d hits=%d" % (
                scans["after-profiles"]["files"], scans["after-profiles"]["bytes"],
                scans["after-profiles"]["hits"]))

    if args.platform == "windows":
        not_exercised.append(
            "Credential Manager UNAVAILABLE: not induced on this Windows job. The original J21 "
            "evidence showed low integrity, a stopped VaultSvc and an S4U task all remained "
            "available; the mapping from those platform errors is unproven here. pending")

    # Detector and judge red actions with the live secrets of this job.
    detector = selfcheck(material["values"], material["texts"], judge_context)
    say("[s08] detector red actions: passed=%s cases=%d" % (
        detector["passed"], len(detector["cases"])))
    for case in detector["cases"]:
        if not case["passed"]:
            say("[s08] detector case failed: %s" % (case["case"],))

    diags = [diag for run in runs for diag in run["diags"]]
    problems = judge_diagnostics(diags, judge_context)
    for problem in problems:
        say("[s08] judge: " + problem)

    final_scan = scan_paths([root, output] + [Path(path) for path in args.scan], forms)
    scans["final"] = final_scan
    say("[s08] final scan: files=%d bytes=%d hits=%d forms=%d" % (
        final_scan["files"], final_scan["bytes"], final_scan["hits"], final_scan["forms"]))

    flags = {
        "phases": all(run["accepted"] for run in runs),
        "detector": detector["passed"],
        "diagnostics": not problems,
        "scan": final_scan["hits"] == 0 and all(item["hits"] == 0 for item in scans.values()),
        "unavailable_paths": (True if args.platform == "windows" else
                              unavailable_observations.get("locked", {}).get("locked") is True),
    }
    accepted = all(flags.values())

    diag_index = {}
    for diag in diags:
        module = diag.get("module")
        diag_index.setdefault(module, {})
        diag_index[module][diag.get("status")] = diag_index[module].get(diag.get("status"), 0) + 1
    say("[s08] diagnostics modules=%s" % (sorted(diag_index),))
    say("[s08] verdict platform=%s accepted=%s flags=%s" % (
        args.platform, accepted, ",".join("%s=%s" % item for item in flags.items())))

    def installed(prefix: str) -> list:
        entries = []
        base = Path(prefix)
        for path in sorted(base.rglob("*")):
            if path.is_file():
                data = path.read_bytes()
                entries.append({"path": path.relative_to(base).as_posix(), "bytes": len(data),
                                "sha256": hashlib.sha256(data).hexdigest()})
        return entries

    consumer = Path(args.consumer)
    report = {
        "schema": 1,
        "package": "S08",
        "accepted": accepted,
        "complete_product": False,
        "platform": args.platform,
        "fixed_base": FIXED_BASE,
        "source_sha": os.environ.get("GITHUB_SHA", ""),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        "job": os.environ.get("GITHUB_JOB", ""),
        "runner": {"os": os.environ.get("RUNNER_OS", ""),
                   "image": os.environ.get("ImageOS", ""),
                   "image_version": os.environ.get("ImageVersion", ""),
                   "python": sys.version.split()[0]},
        "phases": runs,
        "phase_labels": [run["label"] for run in runs],
        "checks": sum(len(run["checks"]) for run in runs),
        "expected_checks": sum(len(run["expected"]) for run in runs),
        "passed": sum(1 for run in runs for item in run["checks"] if item["result"] == "pass"),
        "diagnostics": diag_index,
        "judge_problems": problems,
        "detector": detector,
        "scans": scans,
        "flags": flags,
        "not_exercised": not_exercised,
        "unavailable_observations": unavailable_observations,
        "secret_scope": {
            "generated": "OS CSPRNG inside this job; never written outside this process tree",
            "scanned": "runner transcript, every phase log, isolated stores and home, installed "
                       "modules, consumer binary and the artifact payload",
            "encodings": "raw, 32-byte window, hex/HEX, base64/base64url (padded and unpadded), "
                         "percent-encoded, UTF-16LE/BE",
            "redacted": "credential bytes, Authorization value, cookie value, URL userinfo, "
                        "secret-named query values, local store/home paths, account URLs and "
                        "display names in exported diagnostics",
            "retained": "module and operation, status name, numeric status, system error, document "
                        "offset, HTTP status, challenge scheme, request method, origin, URL path, "
                        "non-secret query pairs, fixed module message text",
        },
        "installed": {"credentials": installed(args.credentials_prefix),
                      "profiles": installed(args.profiles_prefix)},
        "consumer": {"name": consumer.name, "bytes": consumer.stat().st_size,
                     "sha256": hashlib.sha256(consumer.read_bytes()).hexdigest()}
        if consumer.is_file() else None,
    }
    say("[s08] evidence complete: checks=%d/%d failed_phases=%s" % (
        report["passed"], report["expected_checks"],
        [run["label"] for run in runs if not run["accepted"]]))
    # Last transcript line: the manifest below must describe the final transcript.
    report["manifest"] = manifest(output)
    payload_report = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if any(form in payload_report for form in forms):
        report = {"schema": 1, "package": "S08", "accepted": False, "platform": args.platform,
                  "reason": "the report itself held secret material"}
        payload_report = (json.dumps(report) + "\n").encode("utf-8")
    (output / "report.json").write_bytes(payload_report)

    if service is not None:
        service.stop()
    for path in sorted(root.rglob("*"), reverse=True):
        try:
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        except OSError:
            pass
    shutil.rmtree(root, ignore_errors=True)
    TRANSCRIPT.close()
    TRANSCRIPT = None
    return 0 if report.get("accepted") else 1


if __name__ == "__main__":
    sys.exit(main())
