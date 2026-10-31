# SPDX-License-Identifier: MIT
"""Actions-only GTK two-real-host wire recovery; preparation subset, not F05 pass."""
import argparse
import base64
import configparser
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import time
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_linux_host import Session, command
from fixture import Store

def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Actions only")
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    cert, key = out / "fixture.crt", out / "fixture.key"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                    "-keyout", str(key), "-out", str(cert), "-subj", "/CN=127.0.0.1",
                    "-addext", "subjectAltName=IP:127.0.0.1"], check=True, capture_output=True)
    trust = Path("/usr/local/share/ca-certificates") / ("f05-" + secrets.token_hex(12) + ".crt")
    subprocess.run(["sudo", "cp", str(cert), str(trust)], check=True, capture_output=True)
    subprocess.run(["sudo", "update-ca-certificates"], check=True, capture_output=True)
    user, password = "f05", secrets.token_hex(24)
    auth = "Basic " + base64.b64encode((user + ":" + password).encode()).decode()
    store = Store(cert, key, auth)
    devices, checks = [], []
    binary = (args.payload / "bin/exreader-linux").resolve()
    report = {"host": "linux", "F05_accepted": False, "cases": checks, "errors": [],
              "identity": {"source": os.environ["GITHUB_SHA"], "run": os.environ["GITHUB_RUN_ID"],
                           "attempt": os.environ["GITHUB_RUN_ATTEMPT"]},
              "program_sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}
    def launch(name):
        folder = out / name
        folder.mkdir(exist_ok=True)
        host = Session(binary, (args.payload / "Reader.otf").resolve(), folder)
        devices.append(host)
        host.launch()
        return host
    def wait(host, predicate, timeout=120):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if host.process.poll() is not None: raise AssertionError("host exited")
            value = predicate()
            if value: return value
            time.sleep(.1)
        raise TimeoutError("GTK boundary not reached")
    def window(host, title, present=True):
        def find():
            result = subprocess.run(["xdotool", "search", "--onlyvisible", "--all",
                    "--pid", str(host.process.pid), "--name", "^" + title + "$"],
                    capture_output=True, text=True, timeout=5)
            if not present: return not result.stdout.strip()
            return result.stdout.splitlines()[-1] if result.stdout.strip() else None
        target = wait(host, find, 30)
        if present: command("xdotool", "windowactivate", "--sync", target)
        return target
    def account(host):
        state = configparser.ConfigParser(interpolation=None)
        state.read(host.observe)
        return dict(state["account"]) if state.has_section("account") else {}
    def open_account(host):
        command("xdotool", "windowactivate", "--sync", host.window)
        host.key("F2", "ctrl+shift+a")
        window(host, "Account and Sync")
        wait(host, lambda: account(host).get("visible") == "1")
    def close_account(host):
        window(host, "Account and Sync")
        host.key("alt+F4")
        window(host, "Account and Sync", False)
        wait(host, lambda: account(host).get("session_present") == "0")
    def configure(host):
        open_account(host)
        for shortcut, value in (("w", store.root), ("u", user), ("p", password)):
            host.key("alt+" + shortcut, "ctrl+a")
            host.paste(value)
        host.key("alt+h", "alt+a")
        wait(host, lambda: account(host).get("bound") == "1")
        close_account(host)
    def snapshot(host):
        db = host.folder / "profile/library.sqlite.product.sqlite"
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=20) as connection:
            records = [json.loads(r[0]) for r in connection.execute("SELECT body_json FROM reader_revisions")]
            pending = connection.execute("SELECT count(*) FROM reader_outbox").fetchone()[0]
        entity_keys = {r["entity_key"] for r in records if r["entity_kind"] == "book"}
        if len(entity_keys) != 1:
            raise AssertionError("single-book producer cannot combine unrelated entity heads")
        ids = {r["id"] for r in records if r["entity_kind"] == "book"}
        parents = {p for r in records if r["entity_kind"] == "book" for p in r["parents"]}
        return {"entity_key": next(iter(entity_keys)), "heads": sorted(ids - parents), "records": records, "outbox": pending}
    def sync(host, heads=None):
        open_account(host)
        host.key("alt+s")
        wait(host, lambda: account(host).get("session_state") == "4", 240)
        if heads is not None:
            wait(host, lambda: set(snapshot(host)["heads"]) == set(heads))
        state = account(host)
        command("import", "-window", window(host, "Account and Sync"),
                out / ("sync-" + host.folder.name + "-" + str(len(store.requests)) + ".png"))
        close_account(host)
        return state
    def edit(host, title):
        command("xdotool", "windowactivate", "--sync", host.window)
        host.key("F2", "ctrl+e")
        window(host, "Book details")
        host.key("alt+t", "ctrl+a")
        host.paste(title)
        host.key("Return")
        window(host, "Book details", False)
        host.wait(lambda s: not s["error"] and not s.get("busy"), timeout=60)
    try:
        first = launch("first")
        original = out / "F05.txt"
        original.write_text("F05 GTK original. " * 400)
        first.dialog(original)
        first.wait(lambda s: s["book"] > 0 and not s["error"], timeout=60)
        configure(first)
        sync(first)
        second = launch("second")
        configure(second)
        sync(second, snapshot(first)["heads"])
        baseline = snapshot(first)
        store.offline = True
        edit(first, "Offline GTK edit")
        offline = snapshot(first)
        if not offline["outbox"]: raise AssertionError("offline outbox absent")
        store.offline = False
        sync(first)
        sync(second, offline["heads"])
        if snapshot(first)["outbox"]: raise AssertionError("outbox not acknowledged")
        checks.append({"name": "offline_reconnect", "outcome": "passed",
                       "baseline": baseline, "offline": offline, "peer": snapshot(second)})
        edit(first, "Uncertain GTK commit")
        pending = snapshot(first)
        store.hold_put = True
        store.put_committed.clear()
        store.release.clear()
        open_account(first)
        first.key("alt+s")
        if not store.put_committed.wait(60): raise AssertionError("no committed PUT boundary")
        pid = first.process.pid
        first.process.kill()
        first.process.wait(timeout=20)
        first.log.close()
        before = dict(store.entries)
        store.release.set()
        first = launch("first")
        configure(first)
        sync(first)
        sync(second, pending["heads"])
        if snapshot(first)["outbox"] or any(store.entries.get(k) != v for k, v in before.items()):
            raise AssertionError("uncertain replay mismatch")
        checks.append({"name": "kill_commit_ack_replay", "outcome": "passed",
                       "terminated_pid": pid, "reopened_pid": first.process.pid,
                       "pending": pending, "after": snapshot(first)})
        edit(first, "Concurrent GTK first")
        edit(second, "Concurrent GTK second")
        heads = set(snapshot(first)["heads"]) | set(snapshot(second)["heads"])
        if len(heads) != 2: raise AssertionError("two true peer heads required")
        sync(first)
        right = sync(second, heads)
        left = sync(first, heads)
        # A visual screenshot alone is insufficient: inspect native observer
        # fields only after the exact actual conflict display contract is bound.
        checks.append({"name": "concurrent_heads_preserved", "outcome": "needs-ui-audit",
                       "heads": sorted(heads), "first_native_state": left,
                       "second_native_state": right})
    except Exception as error:
        report["errors"].append(str(error))
        raise
    finally:
        for host in devices:
            if host.process.poll() is None:
                try: host.close()
                except Exception:
                    host.process.kill()
                    host.process.wait(timeout=20)
        store.close()
        report["requests"] = store.requests
        report["uncovered"] = ["conflict UI independent readback", "delete-put tombstone",
                               "receive cancellation", "offline reopened actual read",
                               "independent original-artifact authentication"]
        (out / "coverage.json").write_text(json.dumps(report, indent=2) + "\n")
        subprocess.run(["sudo", "rm", "--", str(trust)], check=True, capture_output=True)
        subprocess.run(["sudo", "update-ca-certificates"], check=True, capture_output=True)
        key.unlink(missing_ok=True)

if __name__ == "__main__":
    main()
