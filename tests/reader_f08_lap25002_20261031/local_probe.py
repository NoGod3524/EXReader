"""Local native GPU diagnostic. This execution is explicitly not a GitHub Actions run."""
import argparse
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/reader_perf_windows"))
import perf_windows as H

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

P = module("local_pixels", "tests/reader_f08_windows_product_pixels_20261031/run.py")
D = module("local_display", "tests/reader_wave3_c09/desktop.py")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-source", required=True)
    args = parser.parse_args()
    P.need(os.name == "nt" and os.environ.get("COMPUTERNAME", "").upper() == "LAP25002", "named native device")
    P.need(os.environ.get("GITHUB_ACTIONS") != "true", "local provenance")
    head = P.command(["git", "rev-parse", "HEAD"], text=True).strip()
    P.need(head == args.expected_source, "reviewed source")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(os.environ["USERPROFILE"]) / ".codex/f08-device-runs" / stamp
    out.mkdir(parents=True, exist_ok=False)
    cached = ROOT / "build/f08-local-inputs/product/original.zip"
    raw, product = P.F.product(out / "product", cached.read_bytes() if cached.exists() else None)
    observer_pin = {"source_sha": "ede0972d89e73e294a4d6c8fdf72aed067ba2b13", "run_id": "41225360464", "attempt": "1"}
    observer_meta = P.F.api("actions/artifacts/13051612967")
    digest = "4ae8cc3a8f73da8db3781e27f13ea26b0a71250c4570c09f9852de73d8b5398d"
    P.need(observer_meta["digest"] == "sha256:" + digest and observer_meta["size_in_bytes"] == 94508316 and
           observer_meta["workflow_run"]["head_sha"] == observer_pin["source_sha"] and
           str(observer_meta["workflow_run"]["id"]) == observer_pin["run_id"] and not observer_meta["expired"], "observer metadata")
    observer_cache = ROOT / "build/f08-local-inputs/observer.zip"
    data = observer_cache.read_bytes() if observer_cache.exists() else P.command(
        ["gh", "api", "repos/NoGod3524/EXReader/actions/artifacts/13051612967/zip"])
    P.need(len(data) == 94508316 and P.hashlib.sha256(data).hexdigest() == digest, "observer ZIP")
    if not observer_cache.exists():
        observer_cache.parent.mkdir(parents=True, exist_ok=True)
        observer_cache.write_bytes(data)
    observer = out / "observer.exe"
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        list(P.F.PRODUCT.entries(archive))
        manifest = json.loads(archive.read("manifest.json"))
        old = json.loads(archive.read("result.json"))
        P.need(all(manifest[k] == v for k, v in observer_pin.items()), "observer manifest")
        binary = archive.read("observer.exe")
        P.need(P.hashlib.sha256(binary).hexdigest() == old["observer_sha256"] ==
               manifest["files"]["observer.exe"]["sha256"], "observer bytes")
        observer.write_bytes(binary)
    P.save(out / "observer-metadata.json", observer_meta)
    report = {"execution": "local-native", "native_run_id": stamp, "source_sha": head, "machine": "LAP25002",
              "product": product, "observer_sha256": P.sha(observer), "captures": [], "problems": [],
              "f08_accepted": False, "frame_budget_measured": False, "physical_scanout_proven": False,
              "scope": "Two additional device diagnostic launches. Original CI cohorts remain separate."}
    profile = out / "profile"
    report["seed"] = H.seed_corpus(profile, raw / "seed.exe")
    user = C.WinDLL("user32", use_last_error=True)
    user.EnumDisplaySettingsW.argtypes = [W.LPCWSTR, W.DWORD, C.POINTER(D.Settings)]
    user.EnumDisplaySettingsW.restype = W.BOOL
    user.ChangeDisplaySettingsExW.argtypes = [W.LPCWSTR, C.POINTER(D.Settings), W.HWND, W.DWORD, W.LPVOID]
    user.ChangeDisplaySettingsExW.restype = W.LONG
    user.GetForegroundWindow.restype = W.HWND
    user.SetForegroundWindow.argtypes = [W.HWND]
    user.GetDlgCtrlID.argtypes = [W.HWND]
    user.IsWindowEnabled.argtypes = [W.HWND]
    user.ShowWindow.argtypes = [W.HWND, C.c_int]
    user.SetWindowPos.argtypes = [W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT]
    user.SetWindowPos.restype = W.BOOL
    H.K.SetThreadExecutionState.argtypes = [W.DWORD]
    H.K.SetThreadExecutionState.restype = W.DWORD
    before = D.Settings(size=C.sizeof(D.Settings))
    P.need(user.EnumDisplaySettingsW(None, 0xffffffff, C.byref(before)), "current display")
    foreground = user.GetForegroundWindow()
    report["display_before"] = [before.width, before.height, before.frequency]
    frequency = C.c_longlong()
    H.K.QueryPerformanceFrequency(C.byref(frequency))
    def qpc():
        value = C.c_longlong()
        P.need(H.K.QueryPerformanceCounter(C.byref(value)), "native QPC")
        return value.value
    execution_state = H.K.SetThreadExecutionState(0x80000003)
    P.need(execution_state, "temporary display and system awake request")
    report["execution_state_before"] = execution_state
    try:
        requested = D.Settings.from_buffer_copy(before)
        requested.width, requested.height, requested.frequency = 1280, 800, 60
        requested.fields = 0x00080000 | 0x00100000 | 0x00400000
        P.need(user.ChangeDisplaySettingsExW(None, C.byref(requested), None, 2, None) == 0, "supported device mode")
        P.need(user.ChangeDisplaySettingsExW(None, C.byref(requested), None, 0, None) == 0, "device mode")
        for index, kind in enumerate(("shelf", "font")):
            folder = out / ("capture-%02d" % index)
            folder.mkdir()
            entry = {"index": index, "kind": kind, "folder": folder.name, "complete": False}
            report["captures"].append(entry)
            host = H.Host(raw / "program/EXReader.exe", raw / "program/Reader.otf", profile, folder / "application.log")
            entry.update(pid=host.process.pid, frequency=frequency.value, program_sha256=P.sha(host.exe))
            def emit(event):
                with (folder / "driver.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(event) + "\n")
            emit({"kind": "process", "pid": host.process.pid, "qpc": qpc(), "frequency": frequency.value,
                  "exe_sha256": entry["program_sha256"]})
            process = None
            stream = None
            send = host.send
            def traced(hwnd, message, wparam=0, lparam=0, timeout=2000):
                if message not in (0xF5, 0x20A, 0x186, 0x111, 0xC):
                    return send(hwnd, message, wparam, lparam, timeout)
                event = {"kind": "input", "pid": host.process.pid, "hwnd": int(hwnd), "control_id": user.GetDlgCtrlID(hwnd),
                         "message": message, "wparam": wparam, "start_qpc": qpc(), "dispatched": True,
                         "enabled_at_dispatch": bool(user.IsWindowEnabled(hwnd)), "remaining_ms": timeout}
                event["dispatch_qpc"] = qpc()
                try:
                    return send(hwnd, message, wparam, lparam, timeout)
                finally:
                    event["end_qpc"] = qpc()
                    emit(event)
            host.send = traced
            try:
                entry["first_screen"] = H.op_first_screen(host, 60)
                entry["hwnd"] = int(host.window)
                user.ShowWindow(host.window, 9)
                P.need(user.SetWindowPos(host.window, W.HWND(-1), 0, 0, 0, 0, 0x43), "visible owned product window")
                user.SetForegroundWindow(host.window)
                entry["foreground_at_capture"] = user.GetForegroundWindow() == host.window
                stream = (folder / "native.jsonl").open("wb")
                process = subprocess.Popen([str(observer), str(entry["hwnd"]), str(host.process.pid),
                                            str(folder / "stop"), str(folder / "images")],
                                           cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
                entry["observer_pid"] = process.pid
                deadline = time.monotonic() + 10
                while not any('"kind":"ready"' in line for line in (folder / "native.jsonl").read_text().splitlines()):
                    P.need(process.poll() is None and time.monotonic() < deadline, "observer readiness")
                    time.sleep(.01)
                if kind == "shelf":
                    entry["first_scroll"] = H.op_shelf_next_page(host, 20)
                    for _ in range(3):
                        host.wheel(4)
                        time.sleep(.12)
                        host.wheel_up(4)
                        time.sleep(.12)
                else:
                    H.op_reset_top(host)
                    entry["open"] = H.op_open(host, "Shelf 0000", 30)
                    for _ in range(3):
                        for control in ("font_inc", "font_dec"):
                            host.wait_enabled(control, 10)
                            host.click(control)
                            time.sleep(.15)
                time.sleep(.2)
                entry["observed"] = True
            finally:
                if process is not None:
                    (folder / "stop").write_text("native diagnostic finished\n")
                    try:
                        entry["observer_exit"] = process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
                        entry["observer_exit"] = process.returncode
                    stream.close()
                entry["peak"] = host.close()
                emit({"kind": "close", "pid": host.process.pid, "qpc": qpc(), "exit": host.process.poll()})
            P.need(entry.get("observer_exit") == 0 and entry.get("observed"), "completed native capture")
            adapters = [row for row in P.rows(folder / "native.jsonl") if row["kind"] == "adapter"]
            P.need(len(adapters) == 1 and adapters[0]["vendor"] == 0x8086 and not adapters[0]["flags"] & 2, "Intel native GPU")
            entry["adapter"] = adapters[0]
            entry["complete"] = True
    except BaseException as error:
        report["problems"].append(repr(error))
        raise
    finally:
        report["execution_state_restored"] = bool(H.K.SetThreadExecutionState(execution_state))
        restored = user.ChangeDisplaySettingsExW(None, C.byref(before), None, 0, None)
        after = D.Settings(size=C.sizeof(D.Settings))
        report["display_restored"] = restored == 0 and bool(user.EnumDisplaySettingsW(None, 0xffffffff, C.byref(after))) and (
            after.width, after.height, after.frequency) == (before.width, before.height, before.frequency)
        if foreground:
            user.SetForegroundWindow(foreground)
        P.save(out / "result.json", report)
        print("F08_LOCAL_NATIVE_OUTPUT", str(out), flush=True)
        P.need(report["display_restored"], "original display restoration")
    try:
        for entry in report["captures"]:
            entry["analysis"] = P.analyze(out / entry["folder"], entry)
            control = 119 if entry["kind"] == "shelf" else 123
            P.need(entry["analysis"]["distinct_content_frames"][control] >= 3 and
                   entry["analysis"]["native_input_dispatches"] >= 6, "observed product content changes")
        report["collection_complete"] = all(row["complete"] for row in report["captures"]) and len(report["captures"]) == 2
    except BaseException as error:
        report["problems"].append("analysis: " + repr(error))
        raise
    finally:
        P.save(out / "result.json", report)
        P.save(out / "manifest.json", {"execution": "local-native", "source_sha": head,
            "files": {p.relative_to(out).as_posix(): {"sha256": P.sha(p), "bytes": p.stat().st_size}
                      for p in sorted(out.rglob("*")) if p.is_file() and p != out / "manifest.json"}})
    print("F08_LOCAL_NATIVE", json.dumps({k: v for k, v in report.items() if k not in ("product", "captures")}), flush=True)

if __name__ == "__main__":
    main()
