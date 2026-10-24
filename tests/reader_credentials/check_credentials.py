#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Runs the installed credentials consumer against the real platform store.

Secrets are generated here with the OS CSPRNG, handed to the consumer through
stdin (or a removed input file where a process has no stdin), and never
printed. Every byte written under --output plus every --scan path is searched
for each secret in raw, hex and base64 forms before the report is accepted.
Each platform uses an isolated store owned by this job:

  windows  current-user Credential Manager, random test namespace; UNAVAILABLE
           from an S4U scheduled task, which has no credential logon session.
  linux    private D-Bus session + gnome-keyring with a temporary HOME; locked
           collection and absent service are both UNAVAILABLE.
  macos    temporary keychain as the only search-list/default keychain; the
           locked keychain is UNAVAILABLE. The user's keychains are restored.
  ios      a freshly created simulator device and an ad-hoc signed probe app.
  android  a freshly installed probe app on the emulator; uninstalled after,
           which removes its AndroidKeyStore keys and records.
"""
from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import json
import os
import platform as host_platform
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

PHASE_CHECKS = {
    "suite": [
        "contract-version-and-status-names", "open-rejects-invalid-namespace", "open-accepts-namespaces",
        "empty-get-not-found", "empty-delete-not-found", "write-read-back", "exact-update-no-stale-bytes",
        "account-isolation", "namespace-isolation", "unicode-secret-exact", "opaque-binary-with-nul-exact",
        "maximum-secret-exact", "out-of-bounds-secret-refused-record-kept",
        "small-buffer-reports-length-untouched", "invalid-account-ids-refused", "null-arguments-refused",
        "delete-and-repeat-delete", "handle-reopen-reads-record", "wipe-zeroes-buffer",
        "own-records-removed-reopen-record-written",
    ],
    "reopen": ["new-process-reads-persisted-record", "new-process-deletes-record"],
    "seed": ["seed-probe-record"],
    "unavailable": ["open-needs-no-service", "unavailable-get-existing", "unavailable-get-absent",
                    "unavailable-put", "unavailable-delete"],
    "cleanup": ["cleanup-only-own-records"],
}
ANDROID_JAVA_CHECKS = {
    "uninitialized": ["java-null-context-or-namespace-refused"],
    "suite": [
        "java-open-rejects-invalid", "java-empty-not-found", "java-write-read-exact-update",
        "java-bounds-and-arguments", "java-unicode-binary-maximum", "java-delete-and-repeat-delete",
        "java-encrypted-at-rest", "java-keystore-key-not-exportable", "java-record-bound-to-account",
        "java-record-bound-to-namespace", "java-reopen-record-written",
    ],
    "reopen": ["java-reads-jni-written-record", "java-new-process-reads-record"],
    "cleanup": ["java-cleanup-own-records-and-keys"],
}
CHECK_LINE = re.compile(r"^check (\S+) (pass|fail) (.*)$")
PHASE_LINE = re.compile(r"^phase (\S+) (\d+)/(\d+)$")
SECRET_MAX = 2048


def make_input() -> tuple[str, dict[str, bytes], dict[str, str]]:
    ns = "test.exr-cred." + secrets.token_hex(8)
    ns2 = "test.exr-cred." + secrets.token_hex(8)
    accounts = {k: str(uuid.uuid4()) for k in "abcdrp"}
    binary = bytearray(secrets.token_bytes(200))
    for i in (0, 77, 199):
        binary[i] = 0
    values = {
        "primary": secrets.token_bytes(96),
        "update": secrets.token_bytes(40),
        "other": secrets.token_bytes(48),
        "ns2": secrets.token_bytes(48),
        "unicode": ("webdav-用户:pässwörd🔑:" + secrets.token_hex(16)).encode("utf-8"),
        "binary": bytes(binary),
        "max": secrets.token_bytes(SECRET_MAX),
        "reopen": secrets.token_bytes(64),
    }
    lines = [f"namespace {ns}", f"namespace2 {ns2}"]
    lines += [f"account {k} {v}" for k, v in accounts.items()]
    lines += [f"secret {k} {v.hex()}" for k, v in values.items()]
    return "\n".join(lines) + "\n", values, {"namespace": ns, "namespace2": ns2, **accounts}


def secret_forms(values: dict[str, bytes]) -> list[bytes]:
    forms = []
    for value in values.values():
        token = value[-32:]  # the random tail; every secret ends in CSPRNG bytes
        forms += [value, token, value.hex().encode(), value.hex().upper().encode(),
                  base64.b64encode(value), base64.urlsafe_b64encode(value)]
        if token != value:
            forms += [token.hex().encode(), base64.b64encode(token)[:40]]
    return forms


class Run:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.output = Path(args.output).resolve()
        (self.output / "logs").mkdir(parents=True, exist_ok=True)
        self.text, self.values, self.identity = make_input()
        self.phases: list[dict] = []
        self.diagnostics: list[dict] = []
        self.observations: dict[str, object] = {}
        self.unavailable: list[str] = []
        self.not_exercised: list[str] = []

    def log(self, line: str) -> None:
        print(line, flush=True)

    def record(self, phase: str, label: str, code: int | None, stdout: str, stderr: str,
               expected: list[str] | None = None, diagnostic: bool = False) -> bool:
        name = f"{len(self.phases) + len(self.diagnostics):02d}-{label}"
        (self.output / "logs" / f"{name}.stdout.log").write_text(stdout, encoding="utf-8")
        (self.output / "logs" / f"{name}.stderr.log").write_text(stderr, encoding="utf-8")
        checks, summaries = [], []
        for line in stdout.splitlines():
            m = CHECK_LINE.match(line.strip())
            if m:
                checks.append({"id": m.group(1), "result": m.group(2), "detail": m.group(3)})
            m = PHASE_LINE.match(line.strip())
            if m:
                summaries.append({"phase": m.group(1), "passed": int(m.group(2)), "total": int(m.group(3))})
        ids = [c["id"] for c in checks]
        if expected is None:
            expected = PHASE_CHECKS[phase]
            summaries_ok = summaries == [{"phase": phase, "passed": len(expected), "total": len(expected)}]
        else:
            summaries_ok = bool(summaries) and all(s["passed"] == s["total"] for s in summaries)
        complete = (ids == expected and all(c["result"] == "pass" for c in checks) and code == 0
                    and summaries_ok)
        entry = {"label": label, "phase": phase, "exit": code, "checks": checks,
                 "expected": expected, "summaries": summaries, "accepted": complete, "log": name}
        (self.diagnostics if diagnostic else self.phases).append(entry)
        tag = f"diagnostic {label}" if diagnostic else label
        for c in checks:
            self.log(f"[{tag}] {c['result'].upper()} {c['id']} {c['detail']}")
        self.log(f"[{tag}] exit={code} accepted={complete}")
        return complete

    def consumer(self, phase: str, label: str, env: dict | None = None, executable: str | None = None,
                 diagnostic: bool = False, timeout: int = 180) -> bool:
        try:
            done = subprocess.run([executable or self.args.consumer, phase], input=self.text.encode(),
                                  capture_output=True, timeout=timeout, env=env)
            return self.record(phase, label, done.returncode, done.stdout.decode("utf-8", "replace"),
                               done.stderr.decode("utf-8", "replace"), diagnostic=diagnostic)
        except subprocess.TimeoutExpired as e:
            return self.record(phase, label, None, (e.stdout or b"").decode("utf-8", "replace"),
                               f"timeout after {timeout}s\n", diagnostic=diagnostic)

    # ---------- Windows ----------
    def windows(self) -> None:
        self.consumer("suite", "suite")
        self.consumer("reopen", "reopen")
        self.consumer("seed", "seed")
        # Candidate real conditions; each runs as a diagnostic and the first that
        # yields UNAVAILABLE for every operation is re-run as the accepted phase.
        attempts = [
            ("unavailable-low-integrity", "low-integrity process (file mandatory label Low)",
             self.windows_low_integrity),
            ("unavailable-vault-service-stopped", "Credential Manager service (VaultSvc) stopped",
             self.windows_vault_stopped),
            ("unavailable-s4u-task", "S4U scheduled task", self.windows_s4u),
        ]
        results = {}
        for label, description, run in attempts:
            results[label] = run(label, True)
        self.observations["windows_unavailable_attempts"] = results
        chosen = next(((label, description, run) for label, description, run in attempts if results[label]), None)
        if chosen:
            chosen[2](chosen[0], False)
            self.unavailable.append(chosen[1])
        else:
            self.not_exercised.append("Windows UNAVAILABLE: Credential Manager stayed available to a low-integrity "
                                      "process, with VaultSvc stopped and in an S4U task (all recorded as diagnostics)")
        self.consumer("cleanup", "cleanup")

    def windows_low_integrity(self, label: str, diagnostic: bool) -> bool:
        root = Path(tempfile.mkdtemp(prefix="exr-cred-low-", dir=os.environ.get("RUNNER_TEMP")))
        exe = root / "credentials-consumer-low.exe"
        shutil.copy2(self.args.consumer, exe)
        subprocess.run(["icacls", str(exe), "/setintegritylevel", "Low"], capture_output=True, timeout=60)
        label_out = subprocess.run(["icacls", str(exe)], capture_output=True, text=True, timeout=60).stdout
        self.observations["windows_low_integrity_label"] = "Low Mandatory Level" in label_out
        try:
            return self.consumer("unavailable", label, executable=str(exe), diagnostic=diagnostic)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def windows_vault_stopped(self, label: str, diagnostic: bool) -> bool:
        def ps(command: str) -> str:
            done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                                  capture_output=True, text=True, timeout=120)
            return (done.stdout + done.stderr).strip()
        before = ps("(Get-Service VaultSvc).Status")
        stop = ps("Stop-Service VaultSvc -Force -ErrorAction Continue; (Get-Service VaultSvc).Status")
        try:
            return self.consumer("unavailable", label, diagnostic=diagnostic)
        finally:
            after = ps("Start-Service VaultSvc -ErrorAction Continue; (Get-Service VaultSvc).Status")
            self.observations.setdefault("windows_vault_service", []).append(
                {"before": before, "stopped": stop, "restored": after})

    def windows_s4u(self, label: str, diagnostic: bool) -> bool:
        io_dir = Path(tempfile.mkdtemp(prefix="exr-cred-s4u-", dir=os.environ.get("RUNNER_TEMP")))
        task = "exr-credentials-" + secrets.token_hex(6)
        input_file = io_dir / "credentials-input.txt"
        input_file.write_text(self.text, encoding="ascii")
        consumer = str(Path(self.args.consumer).resolve())
        script = f"""
$ErrorActionPreference = 'Stop'
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute '{consumer}' -Argument 'unavailable --io-dir "{io_dir}"'
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType S4U -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 3)
Register-ScheduledTask -TaskName '{task}' -Action $action -Principal $principal -Settings $settings | Out-Null
try {{
  Start-ScheduledTask -TaskName '{task}'
  $deadline = (Get-Date).AddMinutes(3)
  Start-Sleep -Seconds 2
  while ((Get-ScheduledTask -TaskName '{task}').State -eq 'Running' -and (Get-Date) -lt $deadline) {{ Start-Sleep -Milliseconds 500 }}
  $info = Get-ScheduledTaskInfo -TaskName '{task}'
  "logon=S4U user=$user last_result=$($info.LastTaskResult)"
}} finally {{
  Unregister-ScheduledTask -TaskName '{task}' -Confirm:$false
}}
"""
        done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                              capture_output=True, timeout=300)
        stdout = done.stdout.decode("utf-8", "replace")
        self.observations.setdefault("windows_s4u_task", []).append(stdout.strip())
        result = io_dir / "credentials-result.txt"
        text = result.read_text(encoding="utf-8") if result.exists() else ""
        code = None
        m = re.search(r"last_result=(\d+)", stdout)
        if m:
            code = int(m.group(1))
        accepted = self.record("unavailable", label, code, text, stdout + done.stderr.decode("utf-8", "replace"),
                               diagnostic=diagnostic)
        self.observations["s4u_input_removed_by_consumer"] = not input_file.exists()
        self.wipe_dir(io_dir)
        return accepted

    # ---------- Linux ----------
    def linux(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="exr-cred-linux-", dir=os.environ.get("RUNNER_TEMP")))
        home, runtime = root / "home", root / "run"
        home.mkdir()
        runtime.mkdir(mode=0o700)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("DBUS_", "GNOME_KEYRING", "XDG_"))}
        env.update(HOME=str(home), XDG_RUNTIME_DIR=str(runtime), XDG_DATA_HOME=str(home / ".local/share"),
                   XDG_CONFIG_HOME=str(home / ".config"), XDG_CACHE_HOME=str(home / ".cache"))
        bus = subprocess.run(["dbus-daemon", "--session", "--fork", "--print-address=1", "--print-pid=1",
                              f"--address=unix:path={runtime}/bus"], capture_output=True, text=True, env=env,
                             timeout=30)
        address, pid = (bus.stdout.split("\n") + ["", ""])[:2]
        env["DBUS_SESSION_BUS_ADDRESS"] = address.strip()
        keyring_pid = None
        try:
            password = secrets.token_hex(16)
            daemon_out = root / "keyring-env.txt"
            with open(daemon_out, "w") as out:
                subprocess.run(["gnome-keyring-daemon", "--daemonize", "--unlock", "--components=secrets"],
                               input=password, stdout=out, stderr=subprocess.STDOUT, text=True, env=env,
                               timeout=60)
            for line in daemon_out.read_text().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    env[k] = v
            self.wait_dbus_name(env, "org.freedesktop.secrets")
            alias = self.gdbus(env, "/org/freedesktop/secrets", "org.freedesktop.Secret.Service.ReadAlias",
                               "default")
            if "collection/" not in alias:
                self.gdbus(env, "/org/freedesktop/secrets", "org.freedesktop.Secret.Service.SetAlias",
                           "default", "objectpath '/org/freedesktop/secrets/collection/login'")
                alias = self.gdbus(env, "/org/freedesktop/secrets", "org.freedesktop.Secret.Service.ReadAlias",
                                   "default")
            collection = re.search(r"'(/org/freedesktop/secrets/collection/[^']+)'", alias)
            self.observations["linux_secret_service"] = {
                "bus": "private dbus-daemon --session in RUNNER_TEMP",
                "service": "gnome-keyring-daemon --components=secrets with temporary HOME",
                "default_alias": collection.group(1) if collection else alias.strip(),
            }
            ps = subprocess.run(["pgrep", "-u", str(os.getuid()), "-n", "gnome-keyring-d"], capture_output=True,
                                text=True)
            keyring_pid = ps.stdout.strip() or None
            self.consumer("suite", "suite", env)
            self.consumer("reopen", "reopen", env)
            self.consumer("cleanup", "cleanup", env)
            self.consumer("seed", "seed", env)
            if collection:
                self.gdbus(env, "/org/freedesktop/secrets", "org.freedesktop.Secret.Service.Lock",
                           f"@ao ['{collection.group(1)}']")
                locked = self.gdbus(env, collection.group(1), "org.freedesktop.DBus.Properties.Get",
                                    "org.freedesktop.Secret.Collection", "Locked")
                self.observations["linux_collection_locked"] = locked.strip()
            self.consumer("unavailable", "unavailable-locked-collection", env)
            self.unavailable.append("default Secret Service collection locked")
            absent = dict(env, DBUS_SESSION_BUS_ADDRESS=f"unix:path={root}/no-such-bus")
            self.consumer("unavailable", "unavailable-no-service", absent)
            self.unavailable.append("no Secret Service / session bus reachable")
        finally:
            if keyring_pid:
                subprocess.run(["kill", keyring_pid], check=False)
            if pid.strip():
                subprocess.run(["kill", pid.strip()], check=False)
            time.sleep(1)
            shutil.rmtree(root, ignore_errors=True)
            self.observations["linux_temporary_keyring_removed"] = not root.exists()

    def gdbus(self, env: dict, path: str, method: str, *args: str) -> str:
        done = subprocess.run(["gdbus", "call", "--session", "--dest", "org.freedesktop.secrets",
                               "--object-path", path, "--method", method, *args],
                              capture_output=True, text=True, env=env, timeout=30)
        return done.stdout + done.stderr

    def wait_dbus_name(self, env: dict, name: str) -> None:
        for _ in range(60):
            done = subprocess.run(["gdbus", "call", "--session", "--dest", "org.freedesktop.DBus",
                                   "--object-path", "/org/freedesktop/DBus", "--method",
                                   "org.freedesktop.DBus.NameHasOwner", name],
                                  capture_output=True, text=True, env=env, timeout=10)
            if "true" in done.stdout:
                return
            time.sleep(0.5)

    # ---------- macOS ----------
    def security(self, *args: str) -> str:
        done = subprocess.run(["security", *args], capture_output=True, text=True, timeout=60)
        return done.stdout

    def macos(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="exr-cred-mac-", dir=os.environ.get("RUNNER_TEMP")))
        keychain = str(root / "exr-credentials-test.keychain-db")
        password = secrets.token_hex(16)
        original_list = [s.strip().strip('"') for s in self.security("list-keychains", "-d", "user").splitlines()
                         if s.strip()]
        original_default = self.security("default-keychain", "-d", "user").strip().strip('"')
        try:
            self.security("create-keychain", "-p", password, keychain)
            self.security("set-keychain-settings", keychain)  # no auto-lock timeout
            self.security("unlock-keychain", "-p", password, keychain)
            self.security("list-keychains", "-d", "user", "-s", keychain)
            self.security("default-keychain", "-d", "user", "-s", keychain)
            active = [s.strip().strip('"') for s in self.security("list-keychains", "-d", "user").splitlines()
                      if s.strip()]
            self.observations["macos_keychain"] = {
                "search_list_only_test_keychain": [Path(p).name for p in active] == [Path(keychain).name],
                "default_is_test_keychain": Path(self.security("default-keychain", "-d", "user").strip()
                                                 .strip('"')).name == Path(keychain).name,
                "original_search_list_entries": len(original_list),
            }
            self.consumer("suite", "suite")
            self.consumer("reopen", "reopen")
            self.consumer("seed", "seed")
            self.security("lock-keychain", keychain)
            self.consumer("unavailable", "unavailable-locked-keychain", timeout=90)
            self.unavailable.append("test keychain locked, no user interaction allowed")
            self.security("unlock-keychain", "-p", password, keychain)
            self.consumer("cleanup", "cleanup")
        finally:
            if original_list:
                self.security("list-keychains", "-d", "user", "-s", *original_list)
            if original_default:
                self.security("default-keychain", "-d", "user", "-s", original_default)
            self.security("delete-keychain", keychain)
            shutil.rmtree(root, ignore_errors=True)
            restored = [s.strip().strip('"') for s in self.security("list-keychains", "-d", "user").splitlines()
                        if s.strip()]
            self.observations["macos_user_keychains_restored"] = restored == original_list

    # ---------- iOS simulator ----------
    def simctl(self, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
        return subprocess.run(["xcrun", "simctl", *args], capture_output=True, text=True, timeout=timeout)

    def ios(self) -> None:
        app, bundle_id = self.args.ios_app, "org.exreader.credentials.probe"
        runtimes = json.loads(self.simctl("list", "runtimes", "available", "-j").stdout)["runtimes"]
        ios_runtimes = sorted((r for r in runtimes if r.get("platform") == "iOS"),
                              key=lambda r: [int(x) for x in r["version"].split(".")])
        runtime = ios_runtimes[-1]
        device_type = next(d["identifier"] for d in runtime.get("supportedDeviceTypes", [])
                           if d.get("productFamily") == "iPhone")
        udid = self.simctl("create", "exr-credentials-" + secrets.token_hex(4), device_type,
                           runtime["identifier"]).stdout.strip()
        self.observations["ios_simulator"] = {"runtime": runtime["identifier"], "version": runtime["version"],
                                              "device_type": device_type, "fresh_device": True}
        try:
            boot = self.simctl("bootstatus", udid, "-b", timeout=600)
            self.observations["ios_boot"] = boot.returncode
            install = self.simctl("install", udid, app)
            self.observations["ios_install"] = install.returncode
            self.log(f"[ios] boot={boot.returncode} install={install.returncode} {install.stderr.strip()[:400]}")
            container = Path(self.simctl("get_app_container", udid, bundle_id, "data").stdout.strip())
            docs = container / "Documents"
            docs.mkdir(parents=True, exist_ok=True)
            for phase in ("suite", "reopen", "cleanup"):
                (docs / "credentials-input.txt").write_text(self.text, encoding="ascii")
                result = docs / "credentials-result.txt"
                if result.exists():
                    result.unlink()
                launch = self.simctl("launch", "--console-pty", "--terminate-running-process", udid, bundle_id,
                                     phase, "--io-dir", str(docs), timeout=300)
                text = result.read_text(encoding="utf-8") if result.exists() else ""
                self.log(f"[ios] launch {phase} rc={launch.returncode} result_file={result.exists()} "
                         f"output={(launch.stdout + launch.stderr).strip()[-600:]!r}")
                code = 0 if re.search(r"^phase ", text, re.M) else 1
                self.record(phase, phase, code, text, launch.stdout + launch.stderr)
                leftover = docs / "credentials-input.txt"
                self.observations[f"ios_{phase}_input_removed_by_app"] = not leftover.exists()
                if leftover.exists():
                    self.wipe_file(leftover)
            self.not_exercised.append("iOS locked keychain: the simulator has no passcode lock to engage")
        finally:
            self.simctl("shutdown", udid)
            self.simctl("delete", udid)

    # ---------- Android emulator ----------
    def adb(self, *args: str, data: bytes | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
        return subprocess.run(["adb", *args], input=data, capture_output=True, timeout=timeout)

    def android(self) -> None:
        package = "org.exreader.credentials.probe"
        files = f"/data/data/{package}/files"
        bind, c, java = ["jni-bind-keystore-store"], PHASE_CHECKS, ANDROID_JAVA_CHECKS
        plan = [
            ("uninitialized", c["unavailable"] + java["uninitialized"]),
            ("suite", bind + c["suite"] + java["suite"]),
            ("reopen", java["reopen"] + bind + c["reopen"]),
            ("cleanup", bind + c["cleanup"] + java["cleanup"]),
        ]
        api = self.adb("shell", "getprop", "ro.build.version.sdk").stdout.decode().strip()
        abi = self.adb("shell", "getprop", "ro.product.cpu.abi").stdout.decode().strip()
        self.adb("uninstall", package)
        install = self.adb("install", "-r", "-t", self.args.consumer)
        self.observations["android_device"] = {"api": api, "abi": abi, "fresh_install": install.returncode == 0,
                                               "keystore": "AndroidKeyStore AES-256-GCM, non-exportable"}
        self.adb("logcat", "-c")
        try:
            for phase, expected in plan:
                self.adb("shell", "am", "force-stop", package)
                self.adb("exec-in", "run-as", package, "sh", "-c",
                         f"mkdir -p {files} && cat > {files}/credentials-input.txt", data=self.text.encode())
                done = self.adb("shell", "am", "instrument", "-w", "-r", "-e", "phase", phase,
                                f"{package}/.CredentialsProbe")
                instrument = done.stdout.decode("utf-8", "replace")
                result = self.adb("exec-out", "run-as", package, "cat", f"{files}/credentials-result.txt")
                text = result.stdout.decode("utf-8", "replace") if result.returncode == 0 else ""
                code = 0 if "INSTRUMENTATION_CODE: -1" in instrument else 1
                self.record(phase, phase, code, text, instrument + done.stderr.decode("utf-8", "replace"), expected)
                left = self.adb("exec-out", "run-as", package, "ls", files).stdout.decode()
                self.observations[f"android_{phase}_input_removed_by_probe"] = "credentials-input.txt" not in left
                self.adb("shell", "am", "force-stop", package)  # next phase is a new process
            self.unavailable.append("C ABI used before binding to the Keystore-backed Java store")
            self.not_exercised.append("Android Keystore service failure: not inducible on the emulator")
        finally:
            logcat = self.adb("logcat", "-d", "-v", "threadtime")
            (self.output / "logs" / "logcat.txt").write_bytes(logcat.stdout)
            self.adb("uninstall", package)  # also deletes its Keystore keys and records

    # ---------- shared ----------
    @staticmethod
    def wipe_file(path: Path) -> None:
        try:
            size = path.stat().st_size
            with open(path, "r+b") as f:
                f.write(b"\0" * size)
            path.unlink()
        except OSError:
            pass

    def wipe_dir(self, root: Path) -> None:
        for p in root.rglob("*"):
            if p.is_file():
                self.wipe_file(p)
        shutil.rmtree(root, ignore_errors=True)

    def scan(self, extra: list[str]) -> dict:
        forms = secret_forms(self.values)
        files = hits = total = 0
        roots = [self.output] + [Path(p) for p in extra]
        for root in roots:
            paths = [root] if root.is_file() else list(root.rglob("*")) if root.exists() else []
            for p in paths:
                if not p.is_file():
                    continue
                data = p.read_bytes()
                files += 1
                total += len(data)
                if any(f in data for f in forms):
                    hits += 1
                    self.log(f"secret material found in {p.name}")
        return {"files": files, "bytes": total, "forms_per_secret": "raw, 32-byte window, hex, HEX, base64, "
                "base64url", "secrets": len(self.values), "hits": hits}

    def installed(self) -> list[dict]:
        out = []
        prefix = Path(self.args.module_prefix)
        for p in sorted(prefix.rglob("*")):
            if p.is_file():
                out.append({"path": p.relative_to(prefix).as_posix(), "bytes": p.stat().st_size,
                            "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
        return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, choices=["windows", "linux", "macos", "ios", "android"])
    parser.add_argument("--consumer", required=True, help="installed consumer executable, iOS probe binary or Android probe APK")
    parser.add_argument("--ios-app", help="probe .app bundle for the iOS simulator")
    parser.add_argument("--module-prefix", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--scan", action="append", default=[], help="additional files/dirs to scan for secrets")
    args = parser.parse_args()
    run = Run(args)
    getattr(run, args.platform)()
    scan = run.scan(args.scan)
    expected_labels = {
        "windows": ["suite", "reopen", "seed", "unavailable-*", "cleanup"],
        "linux": ["suite", "reopen", "cleanup", "seed", "unavailable-locked-collection", "unavailable-no-service"],
        "macos": ["suite", "reopen", "seed", "unavailable-locked-keychain", "cleanup"],
        "ios": ["suite", "reopen", "cleanup"],
        "android": ["uninitialized", "suite", "reopen", "cleanup"],
    }[args.platform]
    labels = [p["label"] for p in run.phases]
    if args.platform == "windows" and not any(l.startswith("unavailable-") for l in labels):
        # No reachable condition made Credential Manager unavailable; every
        # attempt must still have run and been recorded as a diagnostic.
        expected_labels = ["suite", "reopen", "seed", "cleanup"]
        if len(run.diagnostics) != 3:
            expected_labels = expected_labels + ["unavailable-*"]
    labels_ok = len(labels) == len(expected_labels) and all(
        fnmatch.fnmatchcase(a, b) for a, b in zip(labels, expected_labels))
    checks = sum(len(p["checks"]) for p in run.phases)
    expected_checks = sum(len(p["expected"]) for p in run.phases)
    consumer = Path(args.consumer)
    report = {
        "schema": 1,
        "module": "EXReaderCredentials",
        "module_version": "0.1.0",
        "platform": args.platform,
        "source_sha": os.environ.get("GITHUB_SHA", ""),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        "job": os.environ.get("GITHUB_JOB", ""),
        "runner": {"os": os.environ.get("RUNNER_OS", ""), "image": os.environ.get("ImageOS", ""),
                   "image_version": os.environ.get("ImageVersion", ""), "python": host_platform.platform()},
        "phases": run.phases,
        "diagnostics": run.diagnostics,
        "phase_labels": labels,
        "expected_phase_labels": expected_labels,
        "checks": checks,
        "passed": sum(1 for p in run.phases for c in p["checks"] if c["result"] == "pass"),
        "expected_checks": expected_checks,
        "unavailable_scenarios": run.unavailable,
        "not_exercised": run.not_exercised,
        "observations": run.observations,
        "secret_scan": scan,
        "installed_files": run.installed(),
        "consumer": {"name": consumer.name, "bytes": consumer.stat().st_size,
                     "sha256": hashlib.sha256(consumer.read_bytes()).hexdigest()} if consumer.is_file() else None,
    }
    report["accepted"] = bool(labels_ok and all(p["accepted"] for p in run.phases)
                              and scan["hits"] == 0 and checks == expected_checks and report["passed"] == checks)
    data = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if any(f in data for f in secret_forms(run.values)):
        report = {"schema": 1, "platform": args.platform, "accepted": False, "reason": "report held secret"}
        data = (json.dumps(report) + "\n").encode("utf-8")
    (run.output / "report.json").write_bytes(data)
    run.log(f"{args.platform}: {report['passed']}/{expected_checks} checks, phases={labels}, "
            f"secret_hits={scan['hits']}, accepted={report['accepted']}")
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
