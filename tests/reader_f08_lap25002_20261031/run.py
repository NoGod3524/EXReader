"""Run the authenticated Windows observer on the named physical device, then audit in hosted CI."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = "ede0972d89e73e294a4d6c8fdf72aed067ba2b13"
RUNNER = "f08-lap25002-20261031-1"
FILES = {"tests/reader_f08_lap25002_20261031/run.py", ".github/workflows/f08-lap25002-native-20261031.yml"}

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

P = module("device_pixels", "tests/reader_f08_windows_product_pixels_20261031/run.py")

def guard():
    P.need(os.environ.get("GITHUB_ACTIONS") == "true" and os.name == "nt", "Windows Actions")
    P.need(P.command(["git", "rev-parse", "HEAD"], text=True).strip() == P.identity()["source_sha"], "source")
    P.command(["git", "merge-base", "--is-ancestor", BASE, "HEAD"])
    P.need(set(P.command(["git", "diff", "--name-only", BASE, "HEAD"], text=True).splitlines()) == FILES, "device-only changes")

P.guard = guard

def seal_device(device):
    P.save(P.OUT / "device.json", device)
    manifest_path = P.OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"] = {p.relative_to(P.OUT).as_posix(): {"sha256": P.sha(p), "bytes": p.stat().st_size}
                         for p in sorted(P.OUT.rglob("*")) if p.is_file() and p != manifest_path}
    P.save(manifest_path, manifest)

def capture():
    guard()
    P.need(os.environ.get("COMPUTERNAME", "").upper() == "LAP25002" and os.environ["RUNNER_NAME"] == RUNNER, "named physical device")
    target = ROOT / "build/f08-device-observer"
    target.mkdir(parents=True, exist_ok=False)
    pin = {"source_sha": BASE, "run_id": "41225360464", "attempt": "1"}
    meta = P.F.api("actions/artifacts/13051612967")
    P.need(meta["name"] == "f08-windows-product-pixels-41225360464-1" and not meta["expired"] and
           meta["workflow_run"]["head_sha"] == BASE and str(meta["workflow_run"]["id"]) == pin["run_id"], "observer producer")
    data = P.command(["gh", "api", "repos/NoGod3524/EXReader/actions/artifacts/13051612967/zip"])
    expected = "4ae8cc3a8f73da8db3781e27f13ea26b0a71250c4570c09f9852de73d8b5398d"
    P.need(len(data) == meta["size_in_bytes"] == 94508316 and P.hashlib.sha256(data).hexdigest() == expected and
           meta["digest"] == "sha256:" + expected, "observer ZIP")
    raw = target / "raw"
    P.F.extract(data, raw, "manifest.json", pin)
    old = json.loads((raw / "result.json").read_text())
    P.need(P.sha(raw / "observer.exe") == old["observer_sha256"], "compiled observer")
    binary = ROOT / "build/f08-product-pixels-build/Release/f08_product_pixels.exe"
    binary.parent.mkdir(parents=True)
    shutil.copyfile(raw / "observer.exe", binary)
    D = module("device_display", "tests/reader_wave3_c09/desktop.py")
    user = C.WinDLL("user32", use_last_error=True)
    user.EnumDisplaySettingsW.argtypes = [W.LPCWSTR, W.DWORD, C.POINTER(D.Settings)]
    user.EnumDisplaySettingsW.restype = W.BOOL
    user.ChangeDisplaySettingsExW.argtypes = [W.LPCWSTR, C.POINTER(D.Settings), W.HWND, W.DWORD, W.LPVOID]
    user.ChangeDisplaySettingsExW.restype = W.LONG
    user.GetForegroundWindow.restype = W.HWND
    user.SetForegroundWindow.argtypes = [W.HWND]
    before = D.Settings(size=C.sizeof(D.Settings))
    P.need(user.EnumDisplaySettingsW(None, 0xffffffff, C.byref(before)), "current desktop")
    foreground = user.GetForegroundWindow()
    hardware = json.loads(P.command(["powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,AdapterRAM,CurrentRefreshRate | ConvertTo-Json -Compress"], text=True))
    device = {**P.identity(), "machine": "LAP25002", "runner": RUNNER, "hardware": hardware,
              "before": [before.width, before.height, before.frequency], "requested": [1280, 800, 60],
              "observer_artifact_id": meta["id"], "observer_artifact_sha256": expected,
              "collection_complete": False, "display_restored": False, "f08_accepted": False,
              "scope": "Physical-device desktop capture capability; producer budgets remain tied to their original hosted run.",
              "frame_budget_measured": False, "physical_scanout_proven": False}
    try:
        requested = D.Settings.from_buffer_copy(before)
        requested.width, requested.height, requested.frequency = 1280, 800, 60
        requested.fields = 0x00080000 | 0x00100000 | 0x00400000
        P.need(user.ChangeDisplaySettingsExW(None, C.byref(requested), None, 2, None) == 0, "supported fixed device mode")
        P.need(user.ChangeDisplaySettingsExW(None, C.byref(requested), None, 0, None) == 0, "fixed device mode")
        P.capture()
        result = json.loads((P.OUT / "result.json").read_text())
        adapters = []
        for entry in result["captures"]:
            adapters.extend(row for row in P.rows(P.OUT / entry["folder"] / "native.jsonl") if row["kind"] == "adapter")
        P.need(len(adapters) == len(result["captures"]) == 12 and
               all(row["vendor"] == 0x8086 and not row["flags"] & 2 for row in adapters), "Intel hardware adapter per capture")
        device.update(collection_complete=result["collection_complete"], adapters=adapters)
    finally:
        restored = user.ChangeDisplaySettingsExW(None, C.byref(before), None, 0, None)
        after = D.Settings(size=C.sizeof(D.Settings))
        device["display_restored"] = restored == 0 and bool(user.EnumDisplaySettingsW(None, 0xffffffff, C.byref(after))) and (
            after.width, after.height, after.frequency) == (before.width, before.height, before.frequency)
        if foreground:
            user.SetForegroundWindow(foreground)
        if (P.OUT / "manifest.json").exists():
            seal_device(device)
        P.save(target / "device.json", device)
        P.need(device["display_restored"], "original desktop restoration")
    print("F08_NATIVE_DEVICE", json.dumps(device), flush=True)

def audit():
    guard()
    P.audit()
    root = ROOT / "build/f08-windows-product-pixels-audit"
    device = json.loads((root / "raw/device.json").read_text())
    P.need(all(device.get(k) == v for k, v in P.identity().items()) and device["machine"] == "LAP25002" and
           device["runner"] == RUNNER and device["collection_complete"] and device["display_restored"], "physical device receipt")
    jobs = P.F.api("actions/runs/" + os.environ["GITHUB_RUN_ID"] + "/attempts/" + os.environ["GITHUB_RUN_ATTEMPT"] + "/jobs")
    capture_jobs = [j for j in jobs["jobs"] if j["name"] == "capture"]
    P.need(len(capture_jobs) == 1 and capture_jobs[0]["runner_name"] == RUNNER and
           capture_jobs[0]["conclusion"] == "success", "physical runner job")
    report = json.loads((root / "audit.json").read_text())
    report["device"] = device
    report["device_job_id"] = capture_jobs[0]["id"]
    P.save(root / "audit.json", report)
    print("F08_NATIVE_DEVICE_AUDIT", json.dumps({"authenticated": True, "device_job_id": report["device_job_id"],
          "captures": len(report["captures"]), "machine": "LAP25002", "f08_accepted": False}), flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("capture", "audit"))
    globals()[parser.parse_args().mode]()
