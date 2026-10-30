#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""F10 Windows dynamic privacy run: the real Windows Credential Manager through the
installed credentials module, synthetic run-time canaries, no real credentials.

Usage: run_dynamic_windows.py --probe PATH --auditor PATH --module-prefix DIR --out REPORT.json

Gates (fail closed): round-trip put/verify/replace/delete/absent; `cmdkey /list` shows the
F10 target only while it is stored (checked outside the module, F10 target only is kept);
no canary (any encoding) in the sandbox, in probe output, or in credential-store files that
appeared/changed during the run (matched bytes only, nothing else is read or kept); TEMP is
empty after every phase; at least ONE real refusal mechanism (low-integrity process, S4U
scheduled task, VaultSvc stopped) must actually make the store unavailable, otherwise the
gap is reported and the run fails; the store is clean and the sandbox removed at the end.
"""
import argparse, getpass, hashlib, importlib.util, json, os, platform, secrets, shutil, subprocess, sys, tempfile, time
from pathlib import Path

NAMESPACE = "org.exreader.f10.privacy"
ACCOUNT = "3f10c0de-0000-4000-8000-000000000a01"
FIXED = b"f10-synthetic-fixed-canary-0001"


def load_auditor(path):
    spec = importlib.util.spec_from_file_location("f10_auditor", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ps(command: str, timeout=180):
    done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                          capture_output=True, text=True, timeout=timeout)
    return done.returncode, (done.stdout + done.stderr).strip()


class Run:
    def __init__(self, args):
        self.args = args
        self.aud = load_auditor(args.auditor)
        self.probe = Path(args.probe).resolve()
        self.secret1 = secrets.token_hex(12).encode() + b"-pw1"
        self.secret2 = ("pässwörd-" + secrets.token_hex(12)).encode("utf-8")
        self.tables = {"s1": self.aud.variants(self.secret1), "s2": self.aud.variants(self.secret2),
                       "fx": self.aud.variants(FIXED)}
        self.phases = []
        self.root = Path(tempfile.mkdtemp(prefix="f10-win-", dir=os.environ.get("RUNNER_TEMP")))
        self.tmp = self.root / "tmp"
        self.tmp.mkdir()
        self.env = dict(os.environ, TEMP=str(self.tmp), TMP=str(self.tmp))
        self.store_dirs = [Path(p) / sub for var, sub in (("LOCALAPPDATA", r"Microsoft\Credentials"),
                                                          ("APPDATA", r"Microsoft\Credentials"),
                                                          ("LOCALAPPDATA", r"Microsoft\Vault"))
                           if (p := os.environ.get(var))]
        self.store_before = self.snapshot_store()
        self.scanned = {"files": 0, "bytes": 0}
        self.store_changed_total = 0

    # ---- helpers
    def record(self, name, ok, diagnostic=False, **detail):
        self.phases.append({"phase": name, "ok": bool(ok), "diagnostic": diagnostic, **detail})
        print(("PASS " if ok else "FAIL ") + ("(diagnostic) " if diagnostic else "") + name, flush=True)
        if not ok or diagnostic:  # plain-log detail for failures/diagnostics (no secrets are ever in these fields)
            print("  detail " + json.dumps(detail, default=str, sort_keys=True)[:900], flush=True)

    def snapshot_store(self):
        snap = {}
        for d in self.store_dirs:
            if d.is_dir():
                for p in d.rglob("*"):
                    try:
                        if p.is_file():
                            st = p.stat()
                            snap[str(p)] = (st.st_mtime_ns, st.st_size)
                    except OSError:
                        pass
        return snap

    def changed_store_files(self):
        now = self.snapshot_store()
        return [Path(k) for k, v in now.items() if self.store_before.get(k) != v]

    def table(self, tags):
        merged = {}
        for tag in tags:
            merged.update({f"{tag}:{k}": v for k, v in self.tables[tag].items()})
        return merged

    def cmdkey_has_target(self):
        done = subprocess.run(["cmdkey", "/list"], capture_output=True, text=True, timeout=60)
        text = done.stdout + done.stderr
        return NAMESPACE in text and ACCOUNT in text  # only our own target is ever inspected

    def leak_hits(self, tags):
        table = self.table(tags)
        # the fixed canary is compiled into the probe binaries by design: never scan sandbox files for it
        found = self.aud.scan_tree(self.root, self.table([t for t in tags if t != "fx"]))
        self.scanned = {"files": max(self.scanned["files"], found["files"]), "bytes": max(self.scanned["bytes"], found["bytes"])}
        hits = list(found["hits"])
        changed = self.changed_store_files()
        self.store_changed_total = max(self.store_changed_total, len(changed))
        for p in changed:  # only files created/modified during this run; bytes are matched, never stored
            try:
                hits += self.aud.scan_bytes("credential-store-file", p.read_bytes(), table)
            except OSError:
                pass
        return hits

    def run_probe(self, name, mode, secret_tag=None, tags=("s1", "s2"), expect_exit=0, expect_target=None,
                  exe=None, diagnostic=False, extra_env=None):
        penv = dict(self.env, **(extra_env or {}))
        if secret_tag:
            penv["F10_SECRET_HEX"] = {"s1": self.secret1, "s2": self.secret2}[secret_tag].hex()
        done = subprocess.run([str(exe or self.probe), mode], env=penv, capture_output=True, timeout=120)
        table = self.table(tags)
        stream_hits = self.aud.scan_bytes("stdout", done.stdout, table) + self.aud.scan_bytes("stderr", done.stderr, table)
        hits = self.leak_hits(tags)
        tmp_left = sorted(p.name for p in self.tmp.rglob("*"))
        target = self.cmdkey_has_target()
        ok = (done.returncode == expect_exit and not stream_hits and not hits and not tmp_left
              and (expect_target is None or target == expect_target))
        self.record(name, ok, diagnostic=diagnostic, mode=mode, exit=done.returncode, expected_exit=expect_exit,
                    cmdkey_target_present=target, expected_target_present=expect_target,
                    probe_output=None if stream_hits else done.stdout.decode("utf-8", "replace").strip().splitlines()[:12],
                    stream_hits=stream_hits, sandbox_or_store_hits=hits, tmp_left=tmp_left)
        return ok, done.returncode

    # ---- real refusal mechanisms
    def attempt_low_integrity(self):
        low = self.root / "low"
        low.mkdir()
        exe = low / "f10-probe-low.exe"
        shutil.copy2(self.probe, exe)
        subprocess.run(["icacls", str(exe), "/setintegritylevel", "Low"], capture_output=True, timeout=60)
        label = subprocess.run(["icacls", str(exe)], capture_output=True, text=True, timeout=60).stdout
        labelled = "Low Mandatory Level" in label
        ok, _ = self.run_probe("W7a-low-integrity-process", "unavailable", "s2", tags=("s2",), exe=exe, diagnostic=True)
        return ok and labelled, {"low_label_applied": labelled}

    def attempt_s4u(self):
        out = self.root / "s4u-out.txt"
        task = "f10-privacy-" + secrets.token_hex(6)
        arg = f'/c ""{self.probe}" unavailable-fixed > "{out}" 2>&1"'
        script = f"""
$ErrorActionPreference = 'Stop'
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '{arg}'
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType S4U -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 3)
Register-ScheduledTask -TaskName '{task}' -Action $action -Principal $principal -Settings $settings | Out-Null
try {{
  Start-ScheduledTask -TaskName '{task}'
  $deadline = (Get-Date).AddMinutes(3)
  Start-Sleep -Seconds 2
  while ((Get-ScheduledTask -TaskName '{task}').State -eq 'Running' -and (Get-Date) -lt $deadline) {{ Start-Sleep -Milliseconds 500 }}
  $info = Get-ScheduledTaskInfo -TaskName '{task}'
  "last_result=$($info.LastTaskResult)"
}} finally {{
  Unregister-ScheduledTask -TaskName '{task}' -Confirm:$false
}}
"""
        _, text = ps(script, timeout=300)
        code = next((int(l.split("=")[1]) for l in text.splitlines() if l.startswith("last_result=")), None)
        output = out.read_bytes() if out.exists() else b""
        hits = self.aud.scan_bytes("s4u-output", output, self.table(("fx",))) + self.leak_hits(("fx", "s1", "s2"))
        target = self.cmdkey_has_target()
        ok = code == 0 and not hits and not target
        self.record("W7b-s4u-scheduled-task", ok, diagnostic=True, last_task_result=code,
                    output_lines=output.decode("utf-8", "replace").strip().splitlines()[:8] if not hits else None,
                    hits=hits, cmdkey_target_present=target)
        return ok, {"last_task_result": code}

    def attempt_vault_stopped(self):
        _, before = ps("(Get-Service VaultSvc).Status")
        _, stopped = ps("Stop-Service VaultSvc -Force -ErrorAction Continue; (Get-Service VaultSvc).Status")
        try:
            ok, _ = self.run_probe("W7c-vaultsvc-stopped", "unavailable", "s2", tags=("s2",), diagnostic=True)
        finally:
            _, after = ps("Start-Service VaultSvc -ErrorAction Continue; (Get-Service VaultSvc).Status")
        return ok, {"before": before.splitlines()[-1:], "stopped": stopped.splitlines()[-1:], "restored": after.splitlines()[-1:]}

    def attempt_network_logon(self):
        """Loopback WinRM with a throw-away local user: a network logon has no credential-capable session."""
        net = self.root / "net"
        net.mkdir()
        exe = net / "f10-probe-net.exe"
        shutil.copy2(self.probe, exe)
        user, password = "f10u" + secrets.token_hex(4), secrets.token_hex(12) + "Aa1!"
        script = f"""
$ErrorActionPreference = 'Stop'
icacls '{net}' /grant '*S-1-1-0:(OI)(CI)RX' | Out-Null
try {{ Enable-PSRemoting -Force -SkipNetworkProfileCheck | Out-Null }} catch {{ "enable_psremoting_failed" }}
net user {user} '{password}' /add /y | Out-Null
try {{
  net localgroup 'Remote Management Users' {user} /add | Out-Null
  $cred = New-Object System.Management.Automation.PSCredential("$env:COMPUTERNAME\\{user}", (ConvertTo-SecureString '{password}' -AsPlainText -Force))
  Invoke-Command -ComputerName localhost -Credential $cred -Authentication Negotiate -ScriptBlock {{
    param($e) $o = & $e unavailable-fixed 2>&1; "exit=$LASTEXITCODE"; $o }} -ArgumentList '{exe}'
}} finally {{ net user {user} /delete | Out-Null }}
"""
        rc, text = ps(script, timeout=400)
        lines = [l for l in text.splitlines() if l.strip()]
        code = next((int(l.split("=")[1]) for l in lines if l.startswith("exit=") and l[5:].isdigit()), None)
        hits = self.aud.scan_bytes("network-output", text.encode(), self.table(("fx", "s1", "s2"))) + self.leak_hits(("s1", "s2"))
        target = self.cmdkey_has_target()
        refused = code == 0 and any(l.startswith("RESULT put") and l.split()[-1] in ("UNAVAILABLE", "IO") for l in lines)
        # lines are our own RESULT/CHECK output or PowerShell error text; no user name/password is echoed back
        me = getpass.getuser()
        shown = [l[:160].replace(me, "<user>") for l in lines if not (password in l or user in l)][:10]
        self.record("W7d-network-logon-winrm-loopback", refused and not hits and not target, diagnostic=True,
                    powershell_exit=rc, probe_exit=code, output_lines=shown, hits=hits, cmdkey_target_present=target)
        return refused and not hits and not target, {"probe_exit": code, "powershell_exit": rc}

    # ---- sequence
    def sequence(self):
        self.run_probe("W0-argument-validation-leaves-store-untouched", "args", expect_target=False)
        self.run_probe("W1-absent-before-put", "absent", expect_target=False)
        self.run_probe("W2-put-canary-1", "put", "s1", tags=("s1",), expect_target=True)
        self.run_probe("W3-verify-canary-1", "verify", "s1", tags=("s1",), expect_target=True)
        self.run_probe("W4-replace-with-canary-2", "put", "s2", expect_target=True)
        self.run_probe("W5-verify-canary-2-and-old-secret-gone", "verify", "s2", expect_target=True)
        self.run_probe("W6-delete-removes-target", "delete", expect_target=False)
        self.run_probe("W6b-absent-after-delete", "absent", expect_target=False)
        mechanisms, used = {}, None
        for label, fn in (("low-integrity", self.attempt_low_integrity), ("s4u", self.attempt_s4u),
                          ("vaultsvc-stopped", self.attempt_vault_stopped),
                          ("network-logon", self.attempt_network_logon)):
            try:
                ok, info = fn()
            except Exception as exc:  # a mechanism that cannot run is a gap, not a pass
                ok, info = False, {"error": type(exc).__name__ + ": " + str(exc)[:160]}
            mechanisms[label] = {"made_store_unavailable": bool(ok), **info}
            # a mechanism that unexpectedly stored the secret must not leave it behind
            self.run_probe("W7-cleanup-after-" + label, "delete", diagnostic=True)
            if ok:
                used = label
                break
        self.record("W7-real-refusal-mechanism-exercised", used is not None, mechanisms=mechanisms, used=used,
                    gap=None if used else "no supported mechanism made the Credential Manager unavailable on this runner; "
                                          "refusal-without-plaintext-fallback is NOT demonstrated")

    def teardown(self):
        try:
            subprocess.run([str(self.probe), "delete"], env=self.env, capture_output=True, timeout=60)
        except Exception:
            pass
        self.record("Z-store-clean-at-end", not self.cmdkey_has_target())
        shutil.rmtree(self.root, ignore_errors=True)
        self.record("Z-sandbox-removed", not self.root.exists())

    def go(self):
        try:
            self.sequence()
        except Exception as exc:  # report, never hide
            self.record("harness-exception", False, error=type(exc).__name__ + ": " + str(exc)[:200])
        finally:
            self.teardown()
        lib = next(iter(sorted(Path(self.args.module_prefix).rglob("exr_credentials*"))), None)
        report = {
            "gate_passed": bool(self.phases) and all(p["ok"] for p in self.phases if not p["diagnostic"]),
            "identity": self.aud.run_identity(),
            "evidence_class": "dynamic-proof (executed against the real Windows Credential Manager with synthetic canaries)",
            "provider": "Windows Credential Manager (CRED_TYPE_GENERIC) via the installed exr_credentials module",
            "probe_sha256": digest(self.probe), "module_library": lib.name if lib else None,
            "module_library_sha256": digest(lib) if lib and lib.is_file() else None,
            "canary": {"synthetic": True, "generated_at_run_time": True,
                       "sha256": {"s1": hashlib.sha256(self.secret1).hexdigest(), "s2": hashlib.sha256(self.secret2).hexdigest()},
                       "length": {"s1": len(self.secret1), "s2": len(self.secret2)},
                       "fixed_synthetic_canary_for_s4u_only": True,
                       "encodings_scanned": sorted(self.tables["s1"])},
            "store_files_watched": ["%LOCALAPPDATA%/Microsoft/Credentials", "%APPDATA%/Microsoft/Credentials",
                                    "%LOCALAPPDATA%/Microsoft/Vault"],
            "store_files_changed_during_run_max": self.store_changed_total,
            "max_scan": self.scanned, "phases": self.phases}
        text = json.dumps(report, indent=2, sort_keys=True)
        for needle in (getpass.getuser(), str(Path.home())):  # reports must not disclose the runner identity
            if len(needle) >= 4 and needle in text:
                report["gate_passed"] = False
                report["identity_disclosure"] = "report text contained runner identity; removed"
                text = json.dumps(report, indent=2, sort_keys=True).replace(needle, "<redacted>")
        Path(self.args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(self.args.out).write_text(text + "\n")
        return 0 if report["gate_passed"] else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", required=True)
    ap.add_argument("--auditor", required=True)
    ap.add_argument("--module-prefix", required=True)
    ap.add_argument("--out", required=True)
    return Run(ap.parse_args()).go()


if __name__ == "__main__":
    sys.exit(main())
