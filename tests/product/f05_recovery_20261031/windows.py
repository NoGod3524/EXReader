# SPDX-License-Identifier: MIT
"""Real Win32 two-profile producer. Never writes a receiver database.

Preparation driver: subset coverage only, F05_accepted remains false. Runs only
in Actions. Uses the unchanged host control adapter, not its planted-record tests.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests/reader_windows_account"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture import Store

def main():
    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Windows Actions only")
    import check_account_ui as A
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    user, password = "f05", secrets.token_hex(24)
    authorization = "Basic " + base64.b64encode((user + ":" + password).encode()).decode()
    cert, key = out / "fixture.crt", out / "fixture.key"
    openssl = shutil.which("openssl") or r"C:\Program Files\Git\usr\bin\openssl.exe"
    subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                    "-days", "1", "-keyout", str(key), "-out", str(cert),
                    "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"],
                   check=True, capture_output=True)
    subprocess.run(["certutil", "-addstore", "-f", "Root", str(cert)],
                   check=True, capture_output=True)
    fingerprint = subprocess.run([openssl, "x509", "-in", str(cert), "-noout", "-fingerprint", "-sha1"],
                                 check=True, capture_output=True, text=True).stdout.strip().split("=", 1)[1].replace(":", "")
    store = Store(cert, key, authorization)
    devices = []
    report = {"identity": {"source": os.environ["GITHUB_SHA"],
                           "run": os.environ["GITHUB_RUN_ID"],
                           "attempt": os.environ["GITHUB_RUN_ATTEMPT"]},
              "host": "windows", "F05_accepted": False, "cases": [], "errors": [],
              "program_sha256": hashlib.sha256(args.candidate.read_bytes()).hexdigest()}
    def launch(name, existing=False):
        device = A.Device(args.candidate.resolve(), (args.package / "Reader.otf").resolve(),
                          out / name, existing=existing)
        devices.append(device)
        return device
    def rows(name, query):
        db = out / name / "library.sqlite.product.sqlite"
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=20) as connection:
            return connection.execute(query).fetchall()
    def sdk_originals(name):
        db=out/name/"library.sqlite"
        with sqlite3.connect(db.as_uri()+"?mode=ro",uri=True,timeout=20) as connection:
            return [{"id":row[0],"bytes":len(row[1]),"sha256":hashlib.sha256(row[1]).hexdigest()}
                    for row in connection.execute("SELECT id,source FROM books ORDER BY id")]
    def snapshot(name):
        records = [json.loads(body) for body, in rows(name, "SELECT body_json FROM reader_revisions")]
        entity_keys = {r["entity_key"] for r in records if r["entity_kind"] == "book"}
        if len(entity_keys) != 1:
            raise AssertionError("single-book producer cannot combine unrelated entity heads")
        ids = {r["id"] for r in records if r["entity_kind"] == "book"}
        parents = {p for r in records if r["entity_kind"] == "book" for p in r["parents"]}
        return {"entity_key": next(iter(entity_keys)), "heads": sorted(ids - parents), "records": records,
                "outbox": rows(name, "SELECT count(*) FROM reader_outbox")[0][0]}
    def configure(device):
        dialog = device.open_account()
        device.fill(dialog, store.root, user, password, False)
        device.apply(dialog, "仅本次会话")
        device.close_account(dialog)
    def sync(device, conflict=False):
        dialog = device.open_account()
        device.press(dialog, A.SYNC)
        device.wait_note(dialog, "接收尚未完成" if conflict else "同步完成", 240)
        detail = device.detail(dialog)
        A.M.screenshot(dialog, out / ("sync-%s-%d.bmp" % (device.profile.name, len(store.requests))))
        device.close_account(dialog)
        return detail
    def edit(device, title):
        dialog = device.details()
        A.set_text(A.U.GetDlgItem(dialog, A.M.TITLE), title)
        device.press(dialog, A.M.SAVE)
        device.closed(dialog)
    def readable(device):
        device.wait_idle()
        title = rows(device.profile.name, "SELECT title FROM reader_books WHERE deleted=0")[0][0]
        device.open(title)
        device.wait_idle()
        device.click("select")
        device.click("copy")
        if "F05 original remains readable" not in A.clipboard_text(device):
            raise AssertionError("actual host original not readable")
    try:
        original = ("F05 original remains readable. " * 400).encode()
        source = out / "F05 original.txt"
        source.write_bytes(original)
        first = launch("first")
        first.import_file(source)
        first.wait(lambda: A.send(first.control("books"), 0x18B) == 1)
        first.wait_idle()
        configure(first)
        sync(first)
        second = launch("second")
        configure(second)
        before_cancel=sdk_originals("second")
        store.hold_get=True;store.get_blocked.clear();store.release.clear()
        cancel_dialog=second.open_account()
        second.press(cancel_dialog,A.SYNC)
        if not store.get_blocked.wait(60):
            raise AssertionError("actual Windows sync original GET not reached")
        second.press(cancel_dialog,A.CANCEL)
        store.release.set()
        second.wait_note(cancel_dialog,"CANCELLED",120)
        cancelled_originals=sdk_originals("second")
        if cancelled_originals!=before_cancel:
            raise AssertionError("cancelled transport mutated SDK originals")
        second.close_account(cancel_dialog)
        sync(second)
        retry_originals=sdk_originals("second")
        if len(retry_originals)!=1 or retry_originals[0]["sha256"]!=hashlib.sha256(original).hexdigest():
            raise AssertionError("actual cancellation retry original mismatch or duplicate")
        report["cases"].append({"name":"cancel_sync_retry","outcome":"passed",
            "cancel_layer":"transport-original-GET-before-native-auto-receive",
            "actual_native_cancel":True,"before":before_cancel,"cancelled":cancelled_originals,
            "retry":retry_originals,"sdk_import_mid_commit_cancel_tested":False})
        initial = snapshot("first")
        if snapshot("second")["heads"] != initial["heads"]:
            raise AssertionError("second actual host has not received initial head")
        # The actual host edits offline; only UI actions write local history.
        store.offline = True
        edit(first, "Offline edited F05")
        offline = snapshot("first")
        if offline["outbox"] < 1 or offline["heads"] == initial["heads"]:
            raise AssertionError("offline host edit did not persist")
        store.offline = False
        sync(first)
        sync(second)
        if snapshot("second")["heads"] != offline["heads"] or snapshot("first")["outbox"]:
            raise AssertionError("real peer failed to converge after reconnect")
        report["cases"].append({"name": "offline_reconnect", "outcome": "passed",
                                "before": initial, "offline": offline, "peer": snapshot("second")})
        # Withhold the PUT response after the server commits. Kill the real host.
        edit(first, "Uncertain commit F05")
        pending = snapshot("first")
        store.put_committed.clear()
        store.release.clear()
        store.hold_put = True
        dialog = first.open_account()
        first.press(dialog, A.SYNC)
        if not store.put_committed.wait(60):
            raise AssertionError("host revision PUT did not reach committed boundary")
        terminated_pid = first.process.pid
        first.process.kill()
        first.process.wait(timeout=20)
        first.log.close()
        server_before = dict(store.entries)
        store.release.set()
        first = launch("first", existing=True)
        configure(first)
        sync(first)
        sync(second)
        if snapshot("first")["outbox"] or snapshot("second")["heads"] != pending["heads"]:
            raise AssertionError("uncertain commit replay lost durable work")
        if any(store.entries.get(path) != body for path, body in server_before.items()):
            raise AssertionError("retry rewrote immutable server bytes")
        report["cases"].append({"name": "kill_commit_ack_replay", "outcome": "passed",
                                "terminated_pid": terminated_pid, "reopened_pid": first.process.pid,
                                "before": pending, "after": snapshot("first")})
        # Both actual clients edit a shared parent without seeing the other edit.
        common = snapshot("first")
        store.checkpoint(out / "peer-baseline", "windows-native-book-common-parent")
        edit(first, "Concurrent first")
        edit(second, "Concurrent second")
        one, two = snapshot("first"), snapshot("second")
        expected = set(one["heads"]) | set(two["heads"])
        if len(expected) != 2:
            raise AssertionError("two actual hosts did not create distinct heads")
        sync(first)
        second_detail = sync(second, conflict=True)
        first_detail = sync(first, conflict=True)
        if set(snapshot("first")["heads"]) != expected or set(snapshot("second")["heads"]) != expected:
            raise AssertionError("concurrent head discarded")
        if "并发版本" not in first_detail or "并发版本" not in second_detail:
            raise AssertionError("real host did not display conflict")
        store.checkpoint(out / "peer-conflict", "windows-two-native-book-peer-heads")
        (out / "peer-contract.json").write_text(json.dumps({
            "entity_kind":"book", "entity_key":common["entity_key"],
            "common_parent":common["heads"], "competing_heads":sorted(expected),
            "baseline":"peer-baseline", "remote_conflict":"peer-conflict",
            "simultaneous_online_peers":False}, indent=2) + "\n")
        report["cases"].append({"name": "concurrent_heads_preserved", "outcome": "passed",
                                "heads": sorted(expected), "first_ui": first_detail,
                                "second_ui": second_detail})
        # Close and independently reopen the actual host, without network.
        first.close()
        store.offline = True
        first = launch("first", existing=True)
        readable(first)
        if set(snapshot("first")["heads"]) != expected:
            raise AssertionError("offline reopen changed heads")
        report["cases"].append({"name": "restart_offline_read", "outcome": "passed",
                                "heads": sorted(expected)})
    except Exception as error:
        report["errors"].append(str(error))
        raise
    finally:
        for device in devices:
            if device.process.poll() is None:
                try: device.close()
                except Exception:
                    device.process.kill()
                    device.process.wait(timeout=20)
        store.close()
        report["requests"] = store.requests
        report["uncovered"] = ["delete_put_tombstone_preserved", "cancel_receive_retry",
                               "other five hosts", "independent original-artifact authentication"]
        (out / "coverage.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        subprocess.run(["certutil", "-delstore", "Root", fingerprint], capture_output=True)
        key.unlink(missing_ok=True)


def collect_provider(argv):
    """Capture original build inputs/outputs only; never infer runtime binding."""
    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Windows Actions only")
    parser = argparse.ArgumentParser()
    for name in ("host", "package", "build-directory", "sdk-prefix", "product-prefix",
                 "stage-prefix", "sdk-archive", "product-archive", "link-map",
                 "build-log", "build-command-json", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    records, commands = {}, []
    def copy(label, source):
        source = source.resolve(strict=True)
        data = source.read_bytes()
        target = out / label
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        records[label] = {"actual_path": str(source), "bytes": len(data),
                          "sha256": hashlib.sha256(data).hexdigest()}
    def capture(label, command):
        try:
            done = subprocess.run(command, cwd=args.build_directory, capture_output=True,
                                  text=True, errors="replace", timeout=120)
        except subprocess.TimeoutExpired as error:
            def decoded(value):
                return value.decode(errors="replace") if isinstance(value, bytes) else value or ""
            partial = decoded(error.stdout) + decoded(error.stderr)
            (out / label).write_text(partial)
            print(partial, flush=True)
            commands.append({"argv": command, "cwd": str(args.build_directory.resolve()),
                             "returncode": None, "timed_out": True, "output": label})
            (out / "command.json").write_text(json.dumps(commands, indent=2) + "\n")
            raise RuntimeError("provider command timed out: " + label) from error
        data = done.stdout + done.stderr
        (out / label).write_text(data)
        # Preserve diagnostics in ordinary job stdout as well as artifacts.
        print(data, flush=True)
        commands.append({"argv": command, "cwd": str(args.build_directory.resolve()),
                         "returncode": done.returncode, "output": label})
        (out / "command.json").write_text(json.dumps(commands, indent=2) + "\n")
        if done.returncode: raise RuntimeError("provider command failed: " + label)
    copy("host.exe", args.host)
    copy("packaged.exe", args.package)
    copy("sdk-sqlite.lib", args.sdk_archive)
    copy("product-sqlite.lib", args.product_archive)
    copy("host.map", args.link_map)
    copy("host-build.log", args.build_log)
    copy("host-build-command.json", args.build_command_json)
    for name in ("CMakeCache.txt", "build.ninja", "CMakeFiles/rules.ninja"):
        copy(name, args.build_directory / name)
    responses = sorted(args.build_directory.rglob("*.rsp"))
    rules = (args.build_directory / "CMakeFiles/rules.ninja").read_text(errors="replace")
    response_status = "retained" if responses else "missing" if "rspfile" in rules else "not_used"
    for response in responses:
        copy("response/" + response.relative_to(args.build_directory).as_posix(), response)
    capture("cmake-version.log", ["cmake", "--version"])
    capture("host-imports.log", ["dumpbin", "/IMPORTS", str(args.package.resolve())])
    for role, archive in (("sdk", args.sdk_archive), ("product", args.product_archive)):
        capture(role + "-symbols.log", ["dumpbin", "/SYMBOLS", str(archive.resolve())])
        capture(role + "-members.log", ["dumpbin", "/LINKERMEMBER:1", str(archive.resolve())])
    frozen = "8357eafa28423a7ab93ba08b823af80f01ad1505"
    guard = {}
    for item in ("src", "include", "cmake", "CMakeLists.txt", "tests/fixtures"):
        def git_object(ref):
            return subprocess.run(["git", "rev-parse", ref + ":" + item], cwd=ROOT,
                                  check=True, capture_output=True, text=True).stdout.strip()
        current, baseline = git_object(os.environ["GITHUB_SHA"]), git_object(frozen)
        guard[item] = {"actual": current, "frozen": baseline}
        if current != baseline: raise RuntimeError("frozen SDK object mismatch: " + item)
    for diagnostic in sorted(out.rglob("*")):
        if diagnostic.is_file():
            label = diagnostic.relative_to(out).as_posix()
            data = diagnostic.read_bytes()
            records.setdefault(label, {"actual_path": str(diagnostic), "bytes": len(data),
                                       "sha256": hashlib.sha256(data).hexdigest()})
    manifest = {"schema": 1, "source": os.environ["GITHUB_SHA"],
                "run": os.environ["GITHUB_RUN_ID"], "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
                "sdk_freeze": frozen, "sdk_object_guard": guard,
                "sdk_prefix": str(args.sdk_prefix.resolve(strict=True)),
                "product_prefix": str(args.product_prefix.resolve(strict=True)),
                "stage_prefix": str(args.stage_prefix.resolve(strict=True)),
                "files": records, "commands": commands,
                "observations": "static-only", "static_only": True,
                "response_status": response_status,
                "host_runtime_provider_observed": False,
                "F07_accepted": False}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "collect-provider":
        collect_provider(sys.argv[2:])
    else:
        main()
