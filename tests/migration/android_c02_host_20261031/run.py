#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions emulator run; preserve original app-UID authority bytes and fstat evidence."""
import hashlib, json, os, pathlib, subprocess, tarfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "evidence/android-c02"
PKG = "org.exreader.host"
def run(command, **kwargs):
    return subprocess.run(command, check=True, timeout=240, **kwargs)
def main():
    if os.environ.get("GITHUB_ACTIONS") != "true": raise SystemExit("Actions execution required")
    run(["adb", "install", "-r", "-t", str(OUT / "app-debug.apk")])
    run(["adb", "install", "-r", "-t", str(OUT / "app-debug-androidTest.apk")])
    result = subprocess.run(["adb", "shell", "am", "instrument", "-w", "-r",
        PKG + ".test/org.exreader.host.C02HostTest"], capture_output=True, timeout=240)
    (OUT / "instrumentation.stdout").write_bytes(result.stdout)
    (OUT / "instrumentation.stderr").write_bytes(result.stderr)
    # run-as performs this archive read under the application UID. These shell
    # tar headers are not used as native object identity proof.
    archive = OUT / "app-raw.tar"
    with archive.open("wb") as stream:
        pulled = subprocess.run(["adb", "exec-out", "run-as", PKG, "tar", "-cf", "-",
            "files/c02-evidence", "c02-native-events.log", "files/c02-pending.bin", "no_backup/c02-admission"],
            stdout=stream, stderr=subprocess.PIPE, timeout=60)
    (OUT / "archive.stderr").write_bytes(pulled.stderr)
    logcat = subprocess.run(["adb", "logcat", "-d", "-v", "threadtime"], capture_output=True, timeout=30)
    (OUT / "logcat.txt").write_bytes(logcat.stdout)
    assert pulled.returncode == 0, pulled.stderr.decode(errors="replace")
    device = OUT / "device"
    device.mkdir()
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            path = pathlib.PurePosixPath(member.name)
            assert not path.is_absolute() and ".." not in path.parts
            assert member.isfile() or member.isdir(), "unexpected app evidence object"
        source.extractall(device, filter="data")
    report = json.loads((device / "files/c02-evidence/device-report.json").read_text())
    assert result.returncode == 0 and b"OK (14 tests)" in result.stdout, result.stdout[-2000:]
    assert report["uid"] == report["euid"] and report["euid"] >= 10000, "root/shell evidence is not app UID evidence"
    assert report["passed"] == 14 and len(report["cases"]) == 14 and report["failure"] is None, report
    assert all(row["passed"] for row in report["cases"])
    assert report["actual_sdk"] and report["actual_android_host"] and not report["actual_migration"]
    phases = ["source-held", "source-released", "pending-owner-live", "pending-owner-dead",
              "pending-fresh-host-refused", "clean-after-independent-proof", "final"]
    for phase in phases:
        base = device / "files/c02-evidence" / phase
        observation = json.loads((base / "observations.json").read_text())
        assert observation["euid"] == report["uid"]
        assert observation["scope_fd"]["uid"] == report["uid"] and observation["scope_fd"]["ino"] > 0
        assert observation["scope_fd"]["dev"] > 0
        assert {p.name for p in (base / "authority").iterdir()} >= {"authority", "registry.lock"}
        for row in observation["objects"]:
            assert row["uid"] == report["uid"] and row["ino"] > 0
            assert all(key in row for key in ("dev", "ino", "mode", "uid", "gid", "nlink", "size"))
            if "raw" in row:
                raw = (device / "files/c02-evidence" / row["raw"]).read_bytes()
                assert len(raw) == row["size"] and hashlib.sha256(raw).hexdigest() == row["sha256"]
    receipt = dict(source=os.environ["GITHUB_SHA"], run=os.environ["GITHUB_RUN_ID"],
        attempt=os.environ["GITHUB_RUN_ATTEMPT"], cases=14, checks=report["checks"],
        uid=report["uid"], raw_archive="app-raw.tar", app_evidence="device/files/c02-evidence",
        authority="device/no_backup/c02-admission", native_events="device/c02-native-events.log",
        actual_sdk=True, actual_android_host=True, actual_migration=False, full_c02_acceptance=False)
    (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))
    (OUT / "file-hashes.json").write_text(json.dumps([dict(path=str(p.relative_to(OUT)), bytes=p.stat().st_size,
        sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(OUT.rglob("*")) if p.is_file()], indent=2) + "\n")
if __name__ == "__main__": main()
