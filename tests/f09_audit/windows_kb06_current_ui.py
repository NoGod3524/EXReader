"""Actions-only current-shell KB-06: actual Space, chooser cancel/import and focus."""
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build/f09-windows-kb06"
BASE = "5a57ff3cc0f295327676663236c6214b5736cb6a"
PARENT = "b62ef60e8830f7b515c1fb6234dc4187c429954e"
BRANCH = "audit/f09-windows-kb06-current-ui-20261102"
MARKER = "[F09-WINDOWS-KB06-CURRENT-UI-R2-20261102]"
PATHS = {
    "tests/f09_audit/windows_kb06_current_ui.py",
    ".github/workflows/f09-windows-kb06-current-ui-20261102.yml",
    "docs/reader-total-progress/F09_WINDOWS_KB06_CURRENT_UI_20261102.md",
}
IDENTITY = {key: os.environ.get(env) for key, env in (
    ("source_sha", "GITHUB_SHA"), ("run_id", "GITHUB_RUN_ID"), ("attempt", "GITHUB_RUN_ATTEMPT"))}

def need(value, message):
    if not value:
        raise ValueError(message)

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

def source():
    need(os.environ.get("GITHUB_ACTIONS") == "true" and platform.system() == "Windows", "Windows Actions only")
    need(os.environ.get("GITHUB_EVENT_NAME") == "push" and os.environ.get("GITHUB_REF") == "refs/heads/" + BRANCH,
         "exact approved push branch")
    need(IDENTITY["attempt"] == "1" and all(IDENTITY.values()), "single first attempt identity")
    head = git("rev-parse", "HEAD")
    need(head == IDENTITY["source_sha"] and git("rev-list", "--parents", "-n", "1", head).split() == [head, PARENT],
         "fixed parent/source")
    need(MARKER in git("log", "-1", "--format=%B"), "authorized marker")
    changed = git("diff", "--name-status", BASE, head).splitlines()
    need(len(changed) == 3 and {line[2:] for line in changed} == PATHS
         and all(line.startswith("A\t") for line in changed), "exact three additions; all old bytes preserved")
    current = git("diff", "--name-status", PARENT, head).splitlines()
    need(len(current) == 3 and {line[2:] for line in current} == PATHS
         and all(line.startswith("M\t") for line in current), "exact approved three-file R2 correction")
    need(not git("diff", "--name-only", "HEAD"), "tracked source modified")
    return {**IDENTITY, "product_source_base": BASE, "old_files_unchanged": True}

def command(label, argv, timeout=1800):
    OUT.mkdir(parents=True, exist_ok=True)
    stdout, stderr = OUT / (label + ".log"), OUT / (label + ".stderr")
    timed_out = None
    done = None
    try:
        with stdout.open("wb") as out, stderr.open("wb") as err:
            done = subprocess.run([str(x) for x in argv], cwd=ROOT, stdout=out, stderr=err, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        timed_out = error
        print(json.dumps({"command": label, "timed_out": True, "timeout_seconds": timeout}), flush=True)
    if timed_out is not None or done.returncode:
        for path in (stdout, stderr):
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - 4096))
                text = stream.read().decode("utf-8", "replace")
            text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
            text = re.sub(r"(?i)(authorization|access_token|password|client_secret)([=: ]+)\S+", r"\1\2[REDACTED]", text)
            text = re.sub(r"https?://[^\s]+", "[URL REDACTED]", text)
            text = "".join(c for c in text if c in "\n\t" or ord(c) >= 32)
            print(json.dumps({"failed_log": path.name, "sha256": sha(path), "tail": "\n".join(text.splitlines()[-40:])}), flush=True)
    if timed_out is not None:
        raise timed_out
    need(done.returncode == 0, label + " exit " + str(done.returncode))

def canonical_hash_prefix(prefix):
    # Do not normalize spelling by guessing Windows case, drive or separators.
    # CMake's own REAL_PATH is also the unchanged product's comparison authority.
    prefix = Path(prefix)
    need(prefix.is_absolute() and prefix.is_dir(), "installed hash directory missing")
    for component in (prefix, *prefix.parents):
        need(not component.is_symlink() and not component.is_junction(), "hash prefix path alias")
    need(prefix.resolve(strict=True).is_relative_to(OUT.resolve(strict=True)), "hash prefix outside this run")
    script = OUT / "hash-realpath.cmake"
    canonical_file = OUT / "hash-canonical.txt"
    script.write_text('file(REAL_PATH "${INPUT_PREFIX}" canonical)\nfile(WRITE "${OUTPUT_FILE}" "${canonical}")\n', encoding="utf-8")
    command("hash-canonical", ["cmake", "-DINPUT_PREFIX=" + prefix.as_posix(),
            "-DOUTPUT_FILE=" + canonical_file.as_posix(), "-P", script], 60)
    canonical = canonical_file.read_text(encoding="utf-8")
    need(canonical and canonical == canonical.strip() and not any(c in canonical for c in ("\n", "\r", ";")),
         "invalid canonical path output")
    real = Path(canonical)
    need(real.is_absolute() and real.is_dir() and os.path.samefile(real, prefix),
         "CMake canonical prefix does not identify the installed directory")
    for component in (real, *real.parents):
        need(not component.is_symlink() and not component.is_junction(), "canonical hash path alias")
    need(real.resolve(strict=True).is_relative_to(OUT.resolve(strict=True)), "canonical prefix escaped run")
    os.environ["EXREADER_ORIGINAL_HASH_PREFIX"] = canonical
    probe = OUT / "hash-package-admission"
    probe.mkdir(exist_ok=False)
    cmake = """cmake_minimum_required(VERSION 3.24)
project(F09HashPackageAdmission LANGUAGES C)
if(NOT "${READER_ORIGINAL_HASH_PREFIX}" STREQUAL "$ENV{EXREADER_ORIGINAL_HASH_PREFIX}")
  message(FATAL_ERROR "F09 canonical selector disagreement")
endif()
file(REAL_PATH "${READER_ORIGINAL_HASH_PREFIX}" actual)
if(NOT "${actual}" STREQUAL "${READER_ORIGINAL_HASH_PREFIX}")
  message(FATAL_ERROR "F09 canonical roundtrip mismatch")
endif()
set(expected "${actual}/lib/cmake/EXReaderOPDSHash")
find_package(EXReaderOPDSHash 0.1.0 EXACT CONFIG REQUIRED PATHS "${expected}" NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH)
if(NOT "${EXReaderOPDSHash_DIR}" STREQUAL "${expected}")
  message(FATAL_ERROR "F09 hash package escaped exact prefix")
endif()
exreader_opds_hash_validate("${actual}")
"""
    (probe / "CMakeLists.txt").write_text(cmake, encoding="utf-8")
    command("hash-package-admission", ["cmake", "-S", probe, "-B", OUT / "hash-package-admission-build",
            "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release", "-DREADER_ORIGINAL_HASH_PREFIX=" + canonical], 120)
    inventory = {}
    for item in sorted(real.rglob("*")):
        need(not item.is_symlink() and not item.is_junction(), "installed hash member alias")
        if item.is_file():
            inventory[item.relative_to(real).as_posix()] = {"bytes": item.stat().st_size, "sha256": sha(item)}
    need(inventory and "lib/cmake/EXReaderOPDSHash/EXReaderOPDSHashConfig.cmake" in inventory,
         "hash package inventory missing")
    receipt = {"requested": str(prefix), "requested_posix": prefix.as_posix(), "canonical": canonical,
               "drive": real.drive, "same_directory": True, "cmake_package_admission": True,
               "files": inventory, "source": IDENTITY}
    save("hash-prefix-admission.json", receipt)
    print(json.dumps({"hash_prefix_admission": receipt}), flush=True)
    return receipt

def build():
    report = {**IDENTITY, "build_complete": False, "accepted": False}
    try:
        report.update(source())
        prefix = OUT / "hash"
        command("hash-configure", ["cmake", "-S", ROOT / "extras/opds", "-B", OUT / "hash-build",
                "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release", "-DEXREADER_OPDS_HASH_ONLY=ON",
                "-DCMAKE_INSTALL_PREFIX=" + str(prefix)])
        command("hash-build", ["cmake", "--build", OUT / "hash-build", "--parallel", "4"])
        command("hash-install", ["cmake", "--install", OUT / "hash-build"])
        need(prefix.is_dir() and any(prefix.rglob("*Config.cmake")), "installed OPDSHash package missing")
        hash_receipt = canonical_hash_prefix(prefix)
        report["hash_prefix_admission"] = hash_receipt
        spec = importlib.util.spec_from_file_location("f09_kb06_f06", ROOT / "tests/reader_f06_packages/build.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.OUT = OUT / "f06"
        module.OUT.mkdir(parents=True, exist_ok=False)
        payload = module.windows() / "EXReader"
        need(os.environ.get("EXREADER_ORIGINAL_HASH_PREFIX") == hash_receipt["canonical"],
             "hash prefix changed during original F06 build")
        for relative, identity in hash_receipt["files"].items():
            item = Path(hash_receipt["canonical"]) / relative
            need(item.is_file() and not item.is_symlink() and not item.is_junction()
                 and {"bytes": item.stat().st_size, "sha256": sha(item)} == identity,
                 "installed hash package changed during original build")
        exe = payload / "EXReader.exe"
        need(exe.is_file(), "F06 actual packaged EXReader.exe missing")
        command("fixtures", [sys.executable, ROOT / "tests/windows_host/make_fixtures.py", "--output", OUT / "fixtures"], 120)
        book = OUT / "fixtures/Extra-Book.epub"
        need(book.is_file(), "original generated Extra-Book fixture missing")
        files = {}
        for path in sorted(payload.rglob("*")):
            need(not path.is_symlink(), "package symlink")
            if path.is_file() and path.suffix.lower() in (".exe", ".dll"):
                files[path.relative_to(payload).as_posix()] = {"bytes": path.stat().st_size, "sha256": sha(path)}
        report.update(build_complete=True, payload=str(payload), executable=str(exe), executable_sha256=sha(exe),
                      files=files, fixture=str(book), fixture_sha256=sha(book),
                      build_recipe="tests/reader_f06_packages/build.py:windows",
                      recipe_sha256=sha(ROOT / "tests/reader_f06_packages/build.py"),
                      sdk_version="3.42.0", old_suite_executed=False)
    except Exception as error:
        report["error"] = type(error).__name__ + ": " + str(error)
    save("build-report.json", report)
    print(json.dumps(report), flush=True)
    return 0 if report["build_complete"] else 1

def collect():
    report = {**IDENTITY, "case": "KB-06-current-ui", "status": "not_executed", "accepted": False,
              "formal_acceptance": False, "legacy_report_changed": False, "space_activations": 0,
              "checks": [], "trace": [], "old_suite_executed": False,
              "scope": "one cancel path and one successful import path, current Windows shell"}
    process = None
    package = None
    before = None
    try:
        report.update(source())
        built = json.loads((OUT / "build-report.json").read_text())
        need(built.get("build_complete") is True and all(built.get(k) == v for k, v in IDENTITY.items()),
             "same-run build precondition not executed")
        exe, book = Path(built["executable"]), Path(built["fixture"])
        package = Path(built["payload"])
        need(exe.resolve().is_relative_to(OUT.resolve()) and book.resolve().is_relative_to(OUT.resolve()), "build path escape")
        def inventory():
            result = {}
            for relative in built["files"]:
                path = package / relative
                need(path.is_file() and not path.is_symlink(), "packaged binary missing/aliased")
                result[relative] = {"bytes": path.stat().st_size, "sha256": sha(path)}
            return result
        before = inventory()
        need(before == built["files"] and sha(book) == built["fixture_sha256"], "packaged/fixture identity changed")
        import uiautomation as auto
        U = ctypes.WinDLL("user32", use_last_error=True)
        K = ctypes.WinDLL("kernel32", use_last_error=True)
        U.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        U.GetWindowThreadProcessId.restype = wintypes.DWORD
        U.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.c_void_p]
        U.GetGUIThreadInfo.restype = wintypes.BOOL
        U.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        U.GetAncestor.restype = wintypes.HWND
        U.IsWindowVisible.argtypes = U.IsWindowEnabled.argtypes = [wintypes.HWND]
        U.IsWindowVisible.restype = U.IsWindowEnabled.restype = wintypes.BOOL
        U.GetDlgCtrlID.argtypes = [wintypes.HWND]
        U.GetDlgCtrlID.restype = ctypes.c_int
        U.GetForegroundWindow.restype = wintypes.HWND
        K.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        K.OpenProcess.restype = wintypes.HANDLE
        K.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        K.QueryFullProcessImageNameW.restype = wintypes.BOOL
        K.CloseHandle.argtypes = [wintypes.HANDLE]
        class GUI(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
                        ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                        ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND), ("rcCaret", wintypes.RECT)]
        data = OUT / "host-data"
        data.mkdir(exist_ok=False)
        process = subprocess.Popen([str(exe), "--data", str(data)], cwd=exe.parent)
        def wait(predicate, seconds):
            end = time.monotonic() + seconds
            last = None
            while time.monotonic() < end:
                need(process.poll() is None, "owned application exited")
                try:
                    value = predicate()
                    if value:
                        return value
                except Exception as error:
                    last = str(error)
                time.sleep(.2)
            raise ValueError("state deadline; last=" + str(last))
        def pid(hwnd):
            value = wintypes.DWORD()
            thread = U.GetWindowThreadProcessId(hwnd, ctypes.byref(value))
            return value.value, thread
        window = auto.WindowControl(searchDepth=1, Name="EXReader", ProcessId=process.pid)
        wait(lambda: window.Exists(0), 60)
        hwnd = window.NativeWindowHandle
        need(pid(hwnd)[0] == process.pid, "window belongs to another process")
        handle = K.OpenProcess(0x1000, False, process.pid)
        need(handle, "owned process identity access")
        try:
            buf = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buf))
            need(K.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)), "actual process image unavailable")
            actual_image = Path(buf.value)
        finally:
            K.CloseHandle(handle)
        need(os.path.normcase(str(actual_image.resolve())) == os.path.normcase(str(exe.resolve()))
             and sha(actual_image) == built["executable_sha256"], "actual running binary differs")
        report["running_identity"] = {"pid": process.pid, "path": str(actual_image), "sha256": sha(actual_image)}
        window.SetActive()  # Initial setup only; never used to repair post-command focus.
        time.sleep(1)
        def focus():
            state = GUI()
            state.cbSize = ctypes.sizeof(state)
            need(U.GetGUIThreadInfo(pid(hwnd)[1], ctypes.byref(state)), "GetGUIThreadInfo failed")
            target = int(state.hwndFocus or 0)
            owned = bool(target and pid(target)[0] == process.pid)
            row = {"hwnd": target, "owned": owned, "in_main": bool(owned and U.GetAncestor(target, 2) == hwnd),
                   "visible": bool(owned and U.IsWindowVisible(target)), "enabled": bool(owned and U.IsWindowEnabled(target))}
            row["usable_main_focus"] = row["owned"] and row["in_main"] and row["visible"] and row["enabled"]
            if owned:
                row["control_id"] = U.GetDlgCtrlID(target)
                control = auto.GetFocusedControl()
                if control and control.ProcessId == process.pid:
                    row["uia"] = {"type": control.ControlTypeName, "name": control.Name, "automation_id": control.AutomationId}
            return row
        def keys(text, note):
            need(pid(U.GetForegroundWindow())[0] == process.pid, "refuse keyboard input outside owned application")
            report["trace"].append({"t_monotonic": time.monotonic(), "keys": text, "note": note, "focus": focus()})
            auto.SendKeys(text, interval=.05, waitTime=.4)
        def go_import():
            stops = []
            for index in range(41):
                current = focus()
                stops.append(current)
                if current.get("control_id") == 102 and current["usable_main_focus"]:
                    need(current.get("uia", {}).get("type") == "ButtonControl", "import control is not an accessible button")
                    report["trace"].append({"import_tab_stops": stops})
                    return
                if index < 40:
                    keys("{Tab}", "reach current import button")
            raise ValueError("import button 102 not reachable within 40 Tabs")
        def dialog():
            value = auto.WindowControl(searchDepth=2, ClassName="#32770", ProcessId=process.pid)
            return value if value.Exists(0) and pid(value.NativeWindowHandle)[0] == process.pid else None
        def no_dialog():
            return not dialog()
        def rows():
            listing = window.ListControl(searchDepth=3)
            need(listing.Exists(0), "current shelf list missing")
            return [c.Name for c in listing.GetChildren() if c.ControlTypeName == "ListItemControl"]
        def returned(label):
            first = focus()
            attempts = []
            if not first["usable_main_focus"]:
                for _ in range(2):
                    keys("{Tab}", "original KB-06 bounded focus recovery")
                    attempts.append(focus())
                    if attempts[-1]["usable_main_focus"]:
                        break
            good = first["usable_main_focus"] or bool(attempts and attempts[-1]["usable_main_focus"])
            report["checks"].append({"id": label, "passed": good, "initial": first, "tab_attempts": attempts})
            need(good, label + " undefined/unreachable product focus")
        initial_rows = rows()
        need(not initial_rows, "private initial shelf is not empty")
        go_import()
        keys("{Space}", "activate import for cancel path")
        report["space_activations"] += 1
        report["status"] = "running"
        report["focus_after_first_space"] = focus()
        wait(dialog, 20)
        report["checks"].append({"id": "space-opens-cancel-chooser", "passed": True})
        keys("{Esc}", "cancel chooser once")
        wait(no_dialog, 10)
        returned("focus-after-cancel")
        need(rows() == initial_rows, "cancel changed shelf")
        go_import()
        keys("{Space}", "activate import for successful import path")
        report["space_activations"] += 1
        report["focus_after_second_space"] = focus()
        wait(dialog, 20)
        report["checks"].append({"id": "space-opens-import-chooser", "passed": True})
        auto.SetClipboardText(str(book))
        keys("{Ctrl}v", "paste original deterministic EPUB path")
        keys("{Enter}", "confirm path once")
        wait(no_dialog, 20)
        final_rows = wait(lambda: rows(), 90)
        need(len(final_rows) == 1 and all(name.strip() for name in final_rows), "successful import must create one named shelf row")
        report["shelf"] = {"before": initial_rows, "after": final_rows, "fixture_sha256": sha(book)}
        returned("focus-after-import")
        need(report["space_activations"] == 2 and len(report["checks"]) == 4 and all(c["passed"] for c in report["checks"]),
             "complete two-path KB-06 evidence")
        report["status"] = "pass"
        report["accepted"] = True
    except Exception as error:
        report["error"] = type(error).__name__ + ": " + str(error)
        report["status"] = "fail" if report["space_activations"] else "not_executed"
    finally:
        if process is not None:
            report["process_exit_before_cleanup"] = process.poll()
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
                report["owned_cleanup_complete"] = process.poll() is not None
            except Exception as error:
                report["cleanup_error"] = str(error)
                report["accepted"] = False
                report["status"] = "fail" if report["space_activations"] else "not_executed"
        if package is not None and before is not None:
            try:
                after = inventory()
                report["binary_inventory_before"] = before
                report["binary_inventory_after"] = after
                need(before == after, "binary bytes changed during observation")
            except Exception as error:
                report["accepted"] = False
                report["status"] = "fail"
                report["identity_error"] = str(error)
        report["formal_acceptance"] = False
        save("report.json", report)
        print(json.dumps(report, ensure_ascii=True), flush=True)
    return 0 if report["accepted"] else 1

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    need(len(sys.argv) == 2 and sys.argv[1] in ("build", "collect"), "fixed action")
    sys.exit(build() if sys.argv[1] == "build" else collect())
