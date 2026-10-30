#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""F10 Linux dynamic privacy run: real Secret Service (gnome-keyring on a private
D-Bus, temporary HOME/TMPDIR), synthetic run-time canaries, no real credentials.

Usage: run_dynamic.py --probe PATH --auditor PATH --module-prefix DIR --out REPORT.json

Gates: no canary (raw/hex/base64/percent/UTF-16) in any sandbox file or name or in
probe output after put, replace and delete; TMPDIR empty after every phase; locked
collection and absent service refuse (UNAVAILABLE/IO) without a plaintext fallback.
"""
import argparse, getpass, hashlib, importlib.util, json, os, platform, re, secrets, shutil, subprocess, sys, tempfile, time
from pathlib import Path


def load_auditor(path):
    spec = importlib.util.spec_from_file_location("f10_auditor", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Run:
    def __init__(self, args):
        self.args = args
        self.aud = load_auditor(args.auditor)
        self.probe = Path(args.probe).resolve()
        self.secret1 = secrets.token_hex(12).encode() + b"-pw1"
        self.secret2 = ("pässwörd-" + secrets.token_hex(12)).encode("utf-8")
        self.tables = {"s1": self.aud.variants(self.secret1), "s2": self.aud.variants(self.secret2)}
        self.phases = []
        self.root = Path(tempfile.mkdtemp(prefix="f10-linux-", dir=os.environ.get("RUNNER_TEMP")))
        self.home, self.runtime, self.tmp = self.root / "home", self.root / "run", self.root / "tmp"
        for d in (self.home, self.tmp):
            d.mkdir()
        self.runtime.mkdir(mode=0o700)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("DBUS_", "GNOME_KEYRING", "XDG_"))}
        self.env.update(HOME=str(self.home), TMPDIR=str(self.tmp), XDG_RUNTIME_DIR=str(self.runtime),
                        XDG_DATA_HOME=str(self.home / ".local/share"), XDG_CONFIG_HOME=str(self.home / ".config"),
                        XDG_CACHE_HOME=str(self.home / ".cache"))
        self.scanned = {"files": 0, "bytes": 0}

    def sh(self, cmd, **kw):
        return subprocess.run(cmd, env=kw.pop("env", self.env), capture_output=True, text=True, timeout=60, **kw)

    def gdbus(self, path, method, *a):
        return self.sh(["gdbus", "call", "--session", "--dest", "org.freedesktop.secrets", "--object-path", path,
                        "--method", method, *a]).stdout

    def record(self, name, ok, **detail):
        self.phases.append({"phase": name, "ok": bool(ok), **detail})
        print(("PASS " if ok else "FAIL ") + name, flush=True)

    def sandbox_hits(self, which):
        merged = {}
        for tag in which:
            merged.update({f"{tag}:{k}": v for k, v in self.tables[tag].items()})
        found = self.aud.scan_tree(self.root, merged)
        self.scanned = {"files": max(self.scanned["files"], found["files"]), "bytes": max(self.scanned["bytes"], found["bytes"])}
        return found["hits"]

    def run_probe(self, name, mode, secret_tag=None, expect_exit=0, scan_tags=("s1", "s2"), env=None):
        penv = dict(env or self.env)
        if secret_tag:
            penv["F10_SECRET_HEX"] = {"s1": self.secret1, "s2": self.secret2}[secret_tag].hex()
        done = subprocess.run([str(self.probe), mode], env=penv, capture_output=True, timeout=60)
        merged = {}
        for tag in scan_tags:
            merged.update({f"{tag}:{k}": v for k, v in self.tables[tag].items()})
        stream_hits = self.aud.scan_bytes("stdout", done.stdout, merged) + self.aud.scan_bytes("stderr", done.stderr, merged)
        hits = self.sandbox_hits(scan_tags)
        tmp_left = sorted(p.name for p in self.tmp.rglob("*"))
        ok = done.returncode == expect_exit and not stream_hits and not hits and not tmp_left
        self.record(name, ok, mode=mode, exit=done.returncode, expected_exit=expect_exit,
                    probe_output=None if stream_hits else done.stdout.decode("utf-8", "replace").strip().splitlines()[:12],
                    stream_hits=stream_hits, sandbox_hits=hits, tmp_left=tmp_left)

    def start_service(self):
        bus = self.sh(["dbus-daemon", "--session", "--fork", "--print-address=1", "--print-pid=1",
                       f"--address=unix:path={self.runtime}/bus"])
        address, self.bus_pid = (bus.stdout.split("\n") + ["", ""])[:2]
        self.env["DBUS_SESSION_BUS_ADDRESS"] = address.strip()
        out = self.root / "keyring-env.txt"
        with open(out, "w") as f:
            subprocess.run(["gnome-keyring-daemon", "--daemonize", "--unlock", "--components=secrets"],
                           input=secrets.token_hex(16), stdout=f, stderr=subprocess.STDOUT, text=True, env=self.env,
                           timeout=60)
        for line in out.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                self.env[k] = v
        out.unlink()  # contains daemon socket paths only; keep the sandbox free of anything but store files
        for _ in range(30):
            r = self.sh(["gdbus", "call", "--session", "--dest", "org.freedesktop.DBus", "--object-path",
                         "/org/freedesktop/DBus", "--method", "org.freedesktop.DBus.NameHasOwner", "org.freedesktop.secrets"])
            if "true" in r.stdout:
                break
            time.sleep(1)
        svc = "org.freedesktop.Secret.Service"
        alias = self.gdbus("/org/freedesktop/secrets", svc + ".ReadAlias", "default")
        if "collection/" not in alias:
            self.gdbus("/org/freedesktop/secrets", svc + ".SetAlias", "default",
                       "objectpath '/org/freedesktop/secrets/collection/login'")
            alias = self.gdbus("/org/freedesktop/secrets", svc + ".ReadAlias", "default")
        m = re.search(r"'(/org/freedesktop/secrets/collection/[^']+)'", alias)
        self.collection = m.group(1) if m else None
        ps = self.sh(["pgrep", "-u", str(os.getuid()), "-n", "gnome-keyring-d"])
        self.keyring_pid = ps.stdout.strip() or None
        self.record("secret-service-started", bool(self.collection), default_collection=self.collection)

    def phases_run(self):
        self.run_probe("A0-argument-validation-leaves-store-untouched", "args")
        self.run_probe("A1-absent-before-put", "absent")
        self.run_probe("A2-put-canary-1", "put", "s1", scan_tags=("s1",))
        keyring = self.home / ".local/share/keyrings"
        self.record("A2b-keyring-files-exist", keyring.is_dir() and any(keyring.iterdir()),
                    files=sorted(p.name for p in keyring.iterdir()) if keyring.is_dir() else [])
        self.run_probe("A3-verify-canary-1", "verify", "s1", scan_tags=("s1",))
        self.run_probe("A4-replace-with-canary-2", "put", "s2")
        self.run_probe("A5-verify-canary-2-and-old-secret-gone", "verify", "s2")
        self.run_probe("A6-delete", "delete")
        self.run_probe("A7-absent-after-delete", "absent")
        if self.collection:
            self.gdbus("/org/freedesktop/secrets", "org.freedesktop.Secret.Service.Lock", f"@ao ['{self.collection}']")
            locked = self.gdbus(self.collection, "org.freedesktop.DBus.Properties.Get",
                                "org.freedesktop.Secret.Collection", "Locked")
            self.record("B0-collection-locked", "true" in locked, observed=locked.strip())
        self.run_probe("B1-locked-collection-refuses-without-plaintext-fallback", "unavailable", "s1", scan_tags=("s1",))
        absent = dict(self.env, DBUS_SESSION_BUS_ADDRESS=f"unix:path={self.root}/no-such-bus")
        self.run_probe("C1-no-service-refuses-without-plaintext-fallback", "unavailable", "s2", scan_tags=("s2",), env=absent)

    def teardown(self):
        if getattr(self, "keyring_pid", None):
            subprocess.run(["kill", self.keyring_pid], check=False)
        if getattr(self, "bus_pid", "").strip():
            subprocess.run(["kill", self.bus_pid.strip()], check=False)
        time.sleep(1)
        shutil.rmtree(self.root, ignore_errors=True)
        self.record("Z-sandbox-removed", not self.root.exists())

    def go(self):
        try:
            self.start_service()
            self.phases_run()
        except Exception as exc:  # report, never hide
            self.record("harness-exception", False, error=type(exc).__name__ + ": " + str(exc)[:200])
        finally:
            self.teardown()
        lib = next(iter(sorted(Path(self.args.module_prefix).rglob("libexr_credentials*"))), None)
        user, home = getpass.getuser(), str(Path.home())
        report = {
            "gate_passed": bool(self.phases) and all(p["ok"] for p in self.phases),
            "platform": platform.platform(), "host_os": os.environ.get("RUNNER_OS"),
            "provider": "libsecret -> gnome-keyring-daemon (private dbus-daemon, temporary HOME/TMPDIR)",
            "probe_sha256": digest(self.probe), "module_library": lib.name if lib else None,
            "module_library_sha256": digest(lib) if lib and lib.is_file() else None,
            "canary": {"synthetic": True, "generated_at_run_time": True,
                       "sha256": {"s1": hashlib.sha256(self.secret1).hexdigest(), "s2": hashlib.sha256(self.secret2).hexdigest()},
                       "length": {"s1": len(self.secret1), "s2": len(self.secret2)},
                       "encodings_scanned": sorted(self.tables["s1"])},
            "max_scan": self.scanned, "phases": self.phases}
        text = json.dumps(report, indent=2, sort_keys=True)
        for needle in (user, home):  # reports must not disclose the runner identity
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
