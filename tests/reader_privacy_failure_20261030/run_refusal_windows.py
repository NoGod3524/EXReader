#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""C08: try to make the real Windows Credential Manager refuse a store, then look for plaintext.

Usage: run_refusal_windows.py --probe PATH --auditor PATH --out REPORT.json

Runs only on a disposable GitHub Actions runner. A throw-away local user with a run-time random
password is created; the probe logs it on with each logon type in turn, impersonates it and drives
the installed credential module with a run-time synthetic secret. Nothing real is read, no system
security setting is changed. `refusal_proven` is true only if the real module returned
UNAVAILABLE/IO for put (and a failing get) under a real logon; otherwise it stays false and the
per-type results say why. The sandbox, probe streams and credential-store files that changed during
the run are searched for the secret in every encoding; any hit fails the harness gate.
"""
import argparse
import importlib.util
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LOGON_TYPES = ("network", "network-cleartext", "batch", "service", "interactive")
TARGET_PREFIX = "EXReaderCredentials/org.exreader.c08.privacy"


def load_auditor(path):
    spec = importlib.util.spec_from_file_location("c08_auditor", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Run:
    def __init__(self, args):
        self.args = args
        self.audit = load_auditor(args.auditor)
        self.probe = Path(args.probe).resolve()
        self.root = Path(tempfile.mkdtemp(prefix="c08-win-", dir=os.environ.get("RUNNER_TEMP")))
        self.tmp = self.root / "tmp"
        self.tmp.mkdir()
        self.secret = "c08-canary-" + secrets.token_hex(16)
        self.user = "c08t" + secrets.token_hex(4)
        self.password = "Zz9!" + secrets.token_hex(5)  # 14 chars: no legacy-password prompt
        print("::add-mask::" + self.password, flush=True)
        self.canaries = {"secret": self.secret, "password": self.password}
        self.env = dict(os.environ, TEMP=str(self.tmp), TMP=str(self.tmp), C08_SECRET_HEX=self.secret.encode().hex(),
                        C08_USER=self.user, C08_PASS=self.password)
        self.store_dirs = [Path(p) / sub for var, sub in (("LOCALAPPDATA", r"Microsoft\Credentials"),
                                                          ("APPDATA", r"Microsoft\Credentials"),
                                                          ("LOCALAPPDATA", r"Microsoft\Vault"))
                           if (p := os.environ.get(var))]
        self.before = self.snapshot()
        self.phases, self.attempts, self.user_created = [], [], False

    def snapshot(self):
        snap = {}
        for base in self.store_dirs:
            for path in base.rglob("*") if base.exists() else ():
                if path.is_file():
                    try:
                        st = path.stat()
                    except OSError:
                        continue
                    snap[str(path)] = (st.st_size, st.st_mtime_ns)
        return snap

    def changed_store_hits(self):
        now, hits = self.snapshot(), []
        for name, stamp in now.items():
            if self.before.get(name) != stamp:
                try:
                    data = Path(name).read_bytes()
                except OSError:
                    continue
                hits += [{"where": "credential-store-file", "hit": h} for h in self.audit.scan_bytes(data, self.canaries)]
        return hits

    def cmdkey_has_target(self):
        done = subprocess.run(["cmdkey", "/list"], capture_output=True, text=True, timeout=60)
        return TARGET_PREFIX.lower() in done.stdout.lower()

    def record(self, name, ok, **detail):
        self.phases.append(dict(name=name, ok=bool(ok), **detail))
        print("%s %s" % ("PASS" if ok else "FAIL", name), flush=True)

    def sweep(self, label, streams):
        hits = self.audit.scan_tree(self.root, self.canaries) + self.changed_store_hits()
        for text in streams:
            hits += [{"where": "probe-stream", "hit": h} for h in self.audit.scan_bytes(text.encode(), self.canaries)]
        left = sorted(p.name for p in self.tmp.iterdir())
        self.record("sweep-" + label, not hits and not left and not self.cmdkey_has_target(),
                    hits=hits, tmp_left=left, runner_cmdkey_target_present=self.cmdkey_has_target())
        return not hits

    def run_cmd(self, argv, timeout=120):
        done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, input="Y\n")
        return done.returncode, (done.stdout + done.stderr).replace(self.password, "<pw>")

    def create_user(self):
        code, out = self.run_cmd(["net", "user", self.user, self.password, "/add", "/expires:never"])
        self.user_created = code == 0
        self.record("A-create-synthetic-user", code == 0, exit=code, output=out.strip()[:300])
        return code == 0

    def remove_user(self):
        if self.user_created:
            self.run_cmd(["net", "user", self.user, "/delete"])
        code, _ = self.run_cmd(["net", "user", self.user])
        profile = Path(os.environ.get("SystemDrive", "C:") + "\\Users") / self.user
        if profile.exists():
            shutil.rmtree(profile, ignore_errors=True)
        self.record("Z-synthetic-user-removed", code != 0 and not profile.exists(), user_exists_exit=code,
                    profile_left=profile.exists())

    def attempt(self, logon):
        try:
            done = subprocess.run([str(self.probe), logon], capture_output=True, text=True, env=self.env, timeout=120)
            code, out, err = done.returncode, done.stdout, done.stderr
        except subprocess.TimeoutExpired:
            code, out, err = -1, "", "timeout"
        lines = [ln for ln in out.splitlines() if ln.split(" ", 1)[0] in
                 ("LOGON", "IMPERSONATE", "IDENTITY", "RESULT", "DIRECT", "OUTCOME")]
        outcome = next((ln.split(" ", 1)[1] for ln in lines if ln.startswith("OUTCOME")), "none")
        put = next((ln.split()[2] for ln in lines if ln.startswith("RESULT put")), None)
        item = {"logon": logon, "exit": code, "outcome": outcome, "put": put, "lines": lines, "stderr": err.strip()[:200]}
        self.attempts.append(item)
        clean = self.sweep("after-" + logon, [out, err])
        refused = outcome.startswith("refused") and put in ("UNAVAILABLE", "IO") and code == 0
        stored_ok = outcome.startswith("stored") and "match=1" in outcome and "cleaned=1" in outcome
        item["refused"] = refused
        if outcome.startswith("stored") and not stored_ok:
            self.record("leftover-after-" + logon, False, outcome=outcome)
        return clean

    def go(self):
        ok = self.create_user()
        if ok:
            for logon in LOGON_TYPES:
                ok &= self.attempt(logon)
        self.remove_user()
        harness_ok = all(p["ok"] for p in self.phases)
        proven = next((a for a in self.attempts if a["refused"]), None)
        report = {
            "harness_ok": harness_ok, "refusal_proven": bool(proven and harness_ok),
            "refusal_mechanism": ("%s logon impersonated, put=%s" % (proven["logon"], proven["put"])) if proven else None,
            "attempts": self.attempts, "phases": self.phases,
            "gap": None if proven else "no tried logon type made Credential Manager refuse; refusal unproven",
            "probe_sha256": self.audit.digest(self.probe),
            "store_files_watched": ["%LOCALAPPDATA%/Microsoft/Credentials", "%APPDATA%/Microsoft/Credentials",
                                    "%LOCALAPPDATA%/Microsoft/Vault"],
            "note": "synthetic user and secret generated at run time; matching only, no store bytes retained",
        }
        self.audit.write_json(self.args.out, report)
        shutil.rmtree(self.root, ignore_errors=True)
        print("refusal_proven=%s harness_ok=%s" % (report["refusal_proven"], harness_ok), flush=True)
        return 0 if harness_ok else 1


def main():
    parser = argparse.ArgumentParser()
    for name in ("probe", "auditor", "out"):
        parser.add_argument("--" + name, required=True)
    return Run(parser.parse_args()).go()


if __name__ == "__main__":
    sys.exit(main())
