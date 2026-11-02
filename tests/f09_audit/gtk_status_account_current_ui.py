"""Actions-only, single GTK status transition and Account Escape observation."""
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
OUT = ROOT / "build/f09-gtk-status-account"
BASE = "77cbbe5e96303306dc22ca9025d9c1d760e87895"
BRANCH = "audit/f09-gtk-status-account-current-ui-20261102"
MARKER = "[F09-GTK-STATUS-ACCOUNT-CURRENT-UI-20261102]"
PATHS = {
    "tests/f09_audit/gtk_status_account_current_ui.py",
    ".github/workflows/f09-gtk-status-account-current-ui-20261102.yml",
    "docs/reader-total-progress/F09_GTK_STATUS_ACCOUNT_20261102.md",
}
PINS = {"examples/linux/reader.c": '9a5863292fbd1b0b0a1d4fc7fce1ee2f30fcfb3513117552e4d46ff7d8b3b7dd', 'tests/f09_audit/baseline.py': 'ce6e33cf2022d95223ba93967b50506080eb3480ceefc06fcac758289dacfc4e', 'tests/reader_gtk_raw_wave3/run.py': 'cf5a87a4beca3952fb00e4d1be27328c068a00e33947523f192a5a13e55f5b58', 'tests/reader_gtk_raw_wave3/check_install.py': 'b8e29ebc03ea12d8b636205504fd97f0dc0de4b4ee3be91542f0b5d34ec64c3f', 'tools/build_linux_host.py': 'd2a5f08d7c5c02794820426ef4f4c32629fb83ed2a97be6c30ae477ff338063a', 'tests/reader_a11y_gtk/driver.py': 'e720933661afe0c89a6113b8f35d43b29774ec4d773ea8daa2181a61f51e2217', 'tests/reader_a11y_gtk/atspi_client.py': '82bc3a2043797bf9275809e81c26ff8bc3d0a315951b455e1e7466c19eb95dee', 'tests/f09_audit/gtk_compact.py': '39759cc8c6d8c2d66c9c8a22f355bbdc8e3a51a102d9f3a63c38cd5b363c4174', 'tests/reader_a11y_gtk/audit_gtk_a11y.py': '5d7e9ded77b419c64a8e9866504c18028a7f793e27eb77fb44762310f0ee9964', 'tests/f09_audit/windows_kb06_current_ui.py': '994b86f32872a96c968f121130a86926559fdad66e7b8031dee667262cf352de', 'extras/opds/EXReaderOPDSHashConfig.cmake.in': '08dc649103e48ddda180382d0b32385ebc341b53e234c6e21f206b0ded040254'}
IDENTITY = {k: os.environ.get(v) for k, v in (
    ("source_sha", "GITHUB_SHA"), ("run_id", "GITHUB_RUN_ID"), ("attempt", "GITHUB_RUN_ATTEMPT"))}

def need(value, message):
    if not value:
        raise ValueError(message)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()

def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

def source():
    need(os.environ.get("GITHUB_ACTIONS") == "true" and platform.system() == "Linux", "Linux Actions only")
    need(os.environ.get("GITHUB_EVENT_NAME") == "push" and os.environ.get("GITHUB_REF") == "refs/heads/" + BRANCH,
         "exact approved push branch")
    need(IDENTITY["attempt"] == "1" and all(IDENTITY.values()), "single first attempt identity")
    head = git("rev-parse", "HEAD")
    need(head == IDENTITY["source_sha"] and git("rev-list", "--parents", "-n", "1", head).split() == [head, BASE],
         "fixed source parent")
    need(MARKER in git("log", "-1", "--format=%B"), "authorized marker")
    changed = git("diff", "--name-status", BASE, head).splitlines()
    need(len(changed) == 3 and {x[2:] for x in changed} == PATHS and all(x.startswith("A\t") for x in changed),
         "exact three additions; old files unchanged")
    need(not git("diff", "--name-only", "HEAD"), "tracked source modified")
    for path, expected in PINS.items():
        need(sha(ROOT / path) == expected, "original source pin: " + path)
    return {**IDENTITY, "product_source_base": BASE, "old_files_unchanged": True}

def command(label, argv, timeout=1800):
    OUT.mkdir(parents=True, exist_ok=True)
    stdout, stderr = OUT / (label + ".log"), OUT / (label + ".stderr")
    error = None
    done = None
    try:
        with stdout.open("wb") as out, stderr.open("wb") as err:
            done = subprocess.run([str(x) for x in argv], cwd=ROOT, stdout=out, stderr=err, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        error = exc
    if error is not None or done.returncode:
        for path in (stdout, stderr):
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - 4096))
                text = stream.read().decode("utf-8", "replace")
            text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
            text = re.sub(r"(?i)(authorization|access_token|password|client_secret)([=: ]+)\S+", r"\1\2[REDACTED]", text)
            text = re.sub(r"https?://[^\s]+", "[URL REDACTED]", text)
            text = "".join(c for c in text if c in "\n\t" or ord(c) >= 32)
            print(json.dumps({"failed_log": path.name, "sha256": sha(path),
                              "tail": "\n".join(text.splitlines()[-40:]), "timed_out": error is not None}), flush=True)
    if error is not None:
        raise error
    need(done.returncode == 0, label + " exit " + str(done.returncode))

def module(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

def canonical_hash_prefix(prefix):
    # Do not normalize spelling by guessing Windows case, drive or separators.
    # CMake's own REAL_PATH is also the unchanged product's comparison authority.
    prefix = Path(prefix)
    need(prefix.is_absolute() and prefix.is_dir(), "installed hash directory missing")
    for component in (prefix, *prefix.parents):
        need(not component.is_symlink() and not getattr(component, "is_junction", lambda: False)(), "hash prefix path alias")
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
        need(not component.is_symlink() and not getattr(component, "is_junction", lambda: False)(), "canonical hash path alias")
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
        need(not item.is_symlink() and not getattr(item, "is_junction", lambda: False)(), "installed hash member alias")
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
    report = {**IDENTITY, "build_complete": False, "formal_acceptance": False, "old_suite_executed": False,
              "observations_executed": False}
    try:
        report.update(source())
        prefix = OUT / "hash"
        command("hash-configure", ["cmake", "-S", ROOT / "extras/opds", "-B", OUT / "hash-build",
                "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release", "-DEXREADER_OPDS_HASH_ONLY=ON",
                "-DCMAKE_INSTALL_PREFIX=" + str(prefix)])
        command("hash-build", ["cmake", "--build", OUT / "hash-build", "--parallel", "4"])
        command("hash-install", ["cmake", "--install", OUT / "hash-build"])
        receipt = canonical_hash_prefix(prefix)
        G = module("tests/reader_gtk_raw_wave3/run.py", "f09_gtk_targeted_build")
        original = G.run
        def run_342(label, args, *rest, **options):
            raised, previous = [], None
            for arg in args:
                text = str(arg)
                if text == "-DEXR_SDK_VERSION=3.41.0":
                    arg = "-DEXR_SDK_VERSION=3.42.0"
                elif text == "3.41.0" and previous == "--sdk-version":
                    arg = "3.42.0"
                raised.append(arg)
                previous = text
            return original(label, raised, *rest, **options)
        G.run = run_342
        G.build_sdk()
        G.install_family("raw", G.PREFIX, True)
        installed = G.installed("raw", G.PREFIX)
        G.cmake("raw-preferences", ROOT / "apps/reader/preferences", G.OUT / "raw-preferences", G.PREFIX, install=True)
        G.HOST_OPTIONS = G.HOST_OPTIONS + ["-DEXR_READER_GTK_PREFERENCES=ON",
                                          "-DREADER_PREFERENCES_PREFIX=" + str(G.PREFIX)]
        package_dir = G.build_compact_host()
        payload = package_dir / "EXReader-Linux"
        metadata_path = package_dir / "build.json"
        metadata = json.loads(metadata_path.read_text())
        need(metadata["source_sha"] == IDENTITY["source_sha"] and metadata["sdk_version"] == "3.42.0"
             and metadata["abi"] == 1, "actual packaged source/SDK/ABI")
        exe = payload / "bin/exreader-linux"
        need(metadata["files"]["bin/exreader-linux"] == sha(exe), "manifest binary identity")
        need(os.environ.get("EXREADER_ORIGINAL_HASH_PREFIX") == receipt["canonical"], "hash selector changed")
        for relative, identity in receipt["files"].items():
            item = Path(receipt["canonical"]) / relative
            need(item.is_file() and not item.is_symlink()
                 and {"bytes": item.stat().st_size, "sha256": sha(item)} == identity, "installed hash changed")
        report.update(build_complete=True, payload=str(payload), executable_sha256=sha(exe),
                      package_manifest=metadata, package_manifest_sha256=sha(metadata_path),
                      raw_installed_report=installed, hash_prefix_admission=receipt,
                      original_baseline_build_lines="77-107; no subsequent audits invoked")
    except Exception as error:
        report["error"] = type(error).__name__ + ": " + str(error)
    save("build-report.json", report)
    print(json.dumps(report), flush=True)
    return 0 if report["build_complete"] else 1

def collect():
    report = {**IDENTITY, "accepted": False, "formal_acceptance": False, "legacy_report_changed": False,
              "screen_reader_verified": False, "old_suite_executed": False,
              "checks": {"status": {"executed": False, "pass": False}, "account": {"executed": False, "pass": False}}}
    host = recorder = None
    try:
        report.update(source())
        built = json.loads((OUT / "build-report.json").read_text())
        need(built["build_complete"] and all(built[k] == IDENTITY[k] for k in IDENTITY), "same run build")
        payload = Path(built["payload"])
        exe = payload / "bin/exreader-linux"
        need(sha(exe) == built["executable_sha256"], "built executable changed")
        sys.path.insert(0, str(ROOT / "tests/reader_a11y_gtk"))
        import atspi_client as A
        import driver as D
        ok, message = A.init()
        need(ok, message)
        session = OUT / "session"
        session.mkdir(exist_ok=False)
        host = D.Host(exe, payload / "Reader.otf", session)
        host.launch()

        def app():
            matches = []
            for value in A.applications():
                try:
                    if int(value.get_process_id()) == host.process.pid:
                        matches.append(value)
                except Exception:
                    pass
            need(len(matches) == 1, "unique AT-SPI application for actual host PID")
            return matches[0]

        def wait(predicate, seconds):
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                value = predicate()
                if value:
                    return value
                time.sleep(0.1)
            return None

        # Only startup registration can be transient. Fail closed after its bounded wait.
        def registered():
            try:
                return app()
            except ValueError:
                return None
        need(wait(registered, 30) is not None, "host accessibility registration")

        def structural(node):
            indices = []
            current = node
            for _ in range(24):
                if current is None:
                    raise ValueError("AX ancestry missing")
                if A.role(current) == "application":
                    need(int(current.get_process_id()) == host.process.pid, "foreign AX application")
                    return list(reversed(indices))
                index = int(current.get_index_in_parent())
                need(index >= 0, "AX sibling index unavailable")
                indices.append(index)
                current = current.get_parent()
            raise ValueError("AX ancestry bound exceeded")

        def snapshot(node):
            return {"indices": structural(node), "role": A.role(node), "name": A.name(node),
                    "states": A.states(node), "path_display": A.path_of(node)}

        def frame():
            nodes = A.find_all(app(), roles={"frame"}, text="EXReader Linux")
            need(len(nodes) == 1, "unique actual host main frame")
            return nodes[0]

        def dialog():
            return A.find_one(app(), roles={"dialog", "frame"}, text="Account and Sync")

        class Recorder(A.Recorder):
            def _callback(self, event):
                source_node = getattr(event, "source", None)
                try:
                    if source_node is None or int(source_node.get_process_id()) != host.process.pid:
                        return
                    entry = {"t": time.monotonic(), "type": str(getattr(event, "type", "")),
                             "detail1": str(getattr(event, "detail1", "")),
                             "detail2": str(getattr(event, "detail2", "")),
                             "source": snapshot(source_node), "source_pid": host.process.pid}
                    with self.lock:
                        if len(self.items) >= 20000:
                            self.error = "event limit exceeded"
                        else:
                            self.items.append(entry)
                except Exception as error:
                    with self.lock:
                        self.error = "callback evidence error"
                        if len(self.items) < 20000:
                            self.items.append({"t": time.monotonic(), "type": "callback-error",
                                               "error": type(error).__name__ + ": " + str(error)})
        recorder = Recorder()
        need(recorder.start() and "object:property-change" in recorder.registered, "property event registration")
        process_exe = Path("/proc") / str(host.process.pid) / "exe"
        need(process_exe.resolve(strict=True) == exe.resolve(strict=True), "running executable path")
        report["program_before"] = {"pid": host.process.pid, "actual_executable": str(process_exe.resolve()),
                                    "sha256": sha(process_exe), "package_sha256": sha(exe)}
        need(report["program_before"]["sha256"] == built["executable_sha256"], "running binary hash")
        def settled(state):
            required = {"busy", "saving", "reader_visible", "shelf_loading", "shelf_restoring", "error", "sequence"}
            need(required <= set(state), "original host observation fields missing")
            return (not state["busy"] and not state["saving"] and
                    (state["reader_visible"] == 1 or (not state["shelf_loading"] and not state["shelf_restoring"])))
        initial_state = host.wait_state(settled, timeout=120)
        need(initial_state["error"] == 0, "startup already failed")
        # status() updates both this label and the STATUS message; the exact
        # initial name comes from that real log, or its source-defined creation
        # value before the first status() call. Never select an arbitrary label.
        expected_initial = host.last_status() or "Import a book to start reading"
        main = frame()
        labels = A.find_all(main, roles={"label"}, text=expected_initial)
        need(len(labels) == 1, "unique exact initial status label")
        status = labels[0]
        parent = status.get_parent()
        main_indices = structural(main)
        before = snapshot(status)
        need(before["indices"][:len(main_indices)] == main_indices
             and len(before["indices"]) == len(main_indices) + 2
             and A.role(parent) in ("panel", "filler"), "source-defined direct root-box status anchor")
        report["status_anchor"] = {"initial_name": expected_initial, "role": "label",
            "parent": snapshot(parent), "main": snapshot(main),
            "source": "examples/linux/reader.c:373-377,1195", "initial_state": initial_state}
        mark = recorder.mark()
        invalid = session / "invalid.epub"
        invalid.write_bytes(b"not an epub document")
        report["checks"]["status"]["executed"] = True
        host.key("F1")
        host.window_named("Import book", True, 20)
        host.key("ctrl+l")
        host.type_text(str(invalid))
        host.key("Return")
        # One import submission; never re-submit on failure.
        host.window_named("Import book", False, 30)
        # First wait for the real refusal to finish; a transient loading name
        # is not a completed error notification. Observations only gate timing.
        final_state = host.wait_state(
            lambda state: settled(state) and state["sequence"] > initial_state["sequence"] and state["error"] != 0,
            timeout=120, description="single invalid import completed with nonzero error")
        final_message = host.last_status()
        need(final_message and final_message != before["name"], "final refusal message missing")
        changed = wait(lambda: A.name(status) == final_message, 10)
        after = snapshot(status)
        report["status_final_observation"] = {"state": final_state, "logged_message": final_message}
        def matching():
            return [e for e in recorder.since(mark) if e.get("source", {}).get("indices") == before["indices"]
                    and e.get("source", {}).get("name") == after["name"]
                    and e.get("type") == "object:property-change:accessible-name"]
        observed = wait(matching, 5) if changed else []
        events = recorder.since(mark)
        old_matches = [e for e in events if e.get("type", "").startswith("object:property-change")
                       and e.get("detail1") == "accessible-name"
                       and e.get("source", {}).get("name") == after["name"]]
        report["checks"]["status"].update(
            pass_=False, before=before, after=after, events=events,
            original_filter_matches=old_matches, actual_type_matches=observed or [],
            recognized_event_schema="object:property-change:accessible-name",
            unknown_property_event_types=sorted({e["type"] for e in events
                if e.get("source", {}).get("indices") == before["indices"]
                and e.get("type", "").startswith("object:property-change")
                and e["type"] != "object:property-change:accessible-name"}))
        report["checks"]["status"].pop("pass_", None)
        report["checks"]["status"]["pass"] = bool(changed and before["indices"] == after["indices"] and observed)
        # Account is an independent observation, not a rerun of status.
        host.key("ctrl+shift+a")
        pane = wait(dialog, 20)
        need(pane is not None, "one Account shortcut failed")
        need(wait(lambda: A.focused_all(pane), 10), "Account focus never entered dialog")
        report["checks"]["account"]["executed"] = True
        report["checks"]["account"]["opened"] = snapshot(pane)
        report["checks"]["account"]["control_names"] = [
            {"role": A.role(n), "name": A.name(n)} for n in A.walk(pane)
            if A.role(n) in ("push button", "button", "entry", "text", "radio button")]
        account_mark = recorder.mark()
        host.key("Escape")
        timeline = []
        end = time.monotonic() + 15
        restored = False
        while time.monotonic() < end:
            pane_now = dialog()
            focused = A.focused_all(app())
            root = frame()
            inside = bool(focused) and all(A.is_ancestor(root, n) or A.same(root, n) for n in focused)
            timeline.append({"t": time.monotonic(), "dialog_present": pane_now is not None,
                             "focused": [snapshot(n) for n in focused], "inside_main": inside})
            if pane_now is None and inside:
                restored = True
                break
            time.sleep(0.1)
        report["checks"]["account"].update({"pass": restored, "timeline": timeline,
            "events": recorder.since(account_mark), "escape_presses": 1, "focus_repair_performed": False})
        need(host.process.poll() is None, "host exited during observations")
        report["program_after"] = {"pid": host.process.pid, "actual_executable": str(process_exe.resolve(strict=True)),
                                   "sha256": sha(process_exe), "package_sha256": sha(exe)}
        need(report["program_after"] == report["program_before"], "program identity changed")
        need(not recorder.error and not any(e.get("type") == "callback-error" for e in recorder.since(0)),
             "event evidence incomplete or overflow")
        report["callback_errors"] = [e for e in recorder.since(0) if e.get("type") == "callback-error"]
        report["accepted"] = all(c["executed"] and c["pass"] for c in report["checks"].values())
    except Exception as error:
        report["error"] = type(error).__name__ + ": " + str(error)
    finally:
        if recorder is not None:
            report["event_registration"] = {"registered": recorder.registered, "rejected": recorder.rejected,
                                            "error": recorder.error}
            save("events.json", recorder.since(0))
            recorder.stop()
        if host is not None:
            try:
                report["cleanup_exit"] = host.close()
                report["cleanup_complete"] = host.process.poll() is not None
            except Exception as error:
                report["cleanup_error"] = str(error)
                report["cleanup_complete"] = False
            if not report.get("cleanup_complete") or report.get("cleanup_exit") != 0:
                report["accepted"] = False
        save("report.json", report)
        # Keep the full event stream in the artifact; the complete bounded verdict
        # and focus timeline remain in stdout without a second ZIP-read request.
        brief = json.loads(json.dumps(report))
        for check in brief["checks"].values():
            if "events" in check:
                check["event_count"] = len(check.pop("events"))
        print(json.dumps(brief), flush=True)
    return 0 if report["accepted"] else 1

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    need(len(sys.argv) == 2 and sys.argv[1] in ("build", "collect"), "exact stage")
    sys.exit(build() if sys.argv[1] == "build" else collect())
