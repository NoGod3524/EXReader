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
PARENT = "8047eef0cfeda7c765c5f2970f2cccc7cc9ed8d7"
BRANCH = "audit/f09-gtk-status-account-current-ui-20261102"
MARKER = "[F09-GTK-STATUS-ACCOUNT-CURRENT-UI-R2-20261102]"
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
    need(head == IDENTITY["source_sha"] and git("rev-list", "--parents", "-n", "1", head).split() == [head, PARENT],
         "fixed source parent")
    need(MARKER in git("log", "-1", "--format=%B"), "authorized marker")
    changed = git("diff", "--name-status", BASE, head).splitlines()
    need(len(changed) == 3 and {x[2:] for x in changed} == PATHS and all(x.startswith("A\t") for x in changed),
         "exact three additions; old files unchanged")
    current = git("diff", "--name-status", PARENT, head).splitlines()
    need(len(current) == 3 and {x[2:] for x in current} == PATHS and all(x.startswith("M\t") for x in current),
         "exact three-file R2 diagnostic correction")
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

        # Each requested case gets one fresh host/profile and its own cleanup.
        # This is not a retry: neither case is ever invoked a second time.
        for case in ("status", "account"):
            result = report["checks"][case]
            host = recorder = None
            query_errors = []
            try:
                session = OUT / ("session-" + case)
                session.mkdir(exist_ok=False)
                host = D.Host(exe, payload / "Reader.otf", session)
                host.launch()
                process_exe = Path("/proc") / str(host.process.pid) / "exe"

                def program():
                    need(host.process.poll() is None, "owned host exited")
                    actual = process_exe.resolve(strict=True)
                    need(actual == exe.resolve(strict=True), "running executable path")
                    value = {"pid": host.process.pid, "actual_executable": str(actual),
                             "sha256": sha(process_exe), "package_sha256": sha(exe)}
                    need(value["sha256"] == built["executable_sha256"] == value["package_sha256"],
                         "same built/running binary identity")
                    return value

                result["program_before"] = program()

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

                def wait(predicate, seconds, label):
                    end = time.monotonic() + seconds
                    while time.monotonic() < end:
                        try:
                            value = predicate()
                            if value:
                                return value
                        except Exception as error:
                            if len(query_errors) < 100:
                                query_errors.append({"t": time.monotonic(), "query": label,
                                    "error": type(error).__name__ + ": " + str(error)})
                        time.sleep(0.1)
                    return None

                need(wait(app, 30, "owned accessibility application") is not None, "host accessibility registration")

                def structural(node):
                    indices = []
                    current = node
                    for _ in range(24):
                        need(current is not None, "AX ancestry missing")
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

                def named_dialog(title, roles):
                    nodes = A.find_all(app(), roles=roles, text=title)
                    need(len(nodes) <= 1, "ambiguous owned dialog")
                    return nodes[0] if nodes else None

                class Recorder(A.Recorder):
                    def __init__(self, target=None):
                        super().__init__()
                        self.target = target
                        self.owner_pid = host.process.pid
                        self.target_errors = []
                    def _callback(self, event):
                        # Raw primitives are retained before any optional source query.
                        # Do not walk every transient GTK/chooser node's parent/index tree.
                        entry = {"t": time.monotonic()}
                        target_match = None
                        raw_ready = False
                        try:
                            entry.update({"type": str(getattr(event, "type", "")),
                                          "detail1": str(getattr(event, "detail1", "")),
                                          "detail2": str(getattr(event, "detail2", ""))})
                            need(bool(entry["type"]), "raw event type missing")
                            raw_ready = True
                            source_node = getattr(event, "source", None)
                            need(source_node is not None, "event source missing")
                            # GObject reference equality, not role/name/extents similarity.
                            target_match = self.target is not None and source_node == self.target
                            entry["source_reference_is_target"] = bool(target_match)
                            entry["source_pid"] = int(source_node.get_process_id())
                            entry["source_role"] = str(source_node.get_role_name())
                            entry["source_name"] = str(source_node.get_name())
                            entry["owned_source"] = entry["source_pid"] == self.owner_pid
                            if target_match:
                                need(entry["owned_source"] and entry["source_role"].lower() == "label",
                                     "target event identity mismatch")
                        except Exception as error:
                            entry["source_query_error"] = type(error).__name__ + ": " + str(error)
                            entry["source_reference_is_target"] = target_match
                            if not raw_ready:
                                entry["type"] = "callback-error"
                                entry["raw_field_error"] = True
                        with self.lock:
                            if len(self.items) >= 20000:
                                self.error = "event limit exceeded"
                                return
                            self.items.append(entry)
                            if entry.get("raw_field_error"):
                                self.error = "raw event field capture failed"
                            # A known target error or an unidentifiable name-change
                            # cannot be silently treated as an unrelated transient node.
                            if "source_query_error" in entry and self.target is not None and (
                                target_match is True or (target_match is None and
                                    entry["type"].startswith("object:property-change:accessible-name"))):
                                self.target_errors.append(entry)
                    def start_required(self):
                        need(self.start() and "object:property-change" in self.registered,
                             "property event registration")

                def settled(state):
                    required = {"busy", "saving", "reader_visible", "shelf_loading",
                                "shelf_restoring", "error", "sequence"}
                    need(required <= set(state), "original host observation fields missing")
                    return (not state["busy"] and not state["saving"] and
                            (state["reader_visible"] == 1 or
                             (not state["shelf_loading"] and not state["shelf_restoring"])))

                initial_state = host.wait_state(settled, timeout=120)
                need(initial_state["error"] == 0, "startup already failed")

                if case == "status":
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
                         and A.role(parent) in ("panel", "filler"), "direct root-box status anchor")
                    result["status_anchor"] = {"initial_name": expected_initial, "before": before,
                        "parent": snapshot(parent), "main": snapshot(main), "initial_state": initial_state}
                    recorder = Recorder(status)
                    recorder.start_required()
                    mark = recorder.mark()
                    invalid = session / "invalid.epub"
                    invalid.write_bytes(b"not an epub document")
                    result["executed"] = True
                    result["import_operations"] = 1
                    host.key("F1")

                    def chooser_ready():
                        pane = named_dialog("Import book", {"file chooser"})
                        return pane if pane is not None and A.states(pane).get("active") and A.focused_all(pane) else None

                    pane = wait(chooser_ready, 20, "owned chooser active and focused")
                    need(pane is not None, "chooser never became ready")
                    result["chooser_ready"] = snapshot(pane)
                    host.key("ctrl+l")

                    def location():
                        pane = named_dialog("Import book", {"file chooser"})
                        if pane is None:
                            return None
                        nodes = [n for n in A.focused_all(pane)
                                 if A.role(n) in ("text", "entry") and A.states(n).get("editable")
                                 and "Location Layer" in A.path_of(n)]
                        return nodes[0] if len(nodes) == 1 else None

                    entry = wait(location, 15, "focused editable chooser Location Layer")
                    need(entry is not None, "location entry not ready")
                    result["location_ready"] = snapshot(entry)
                    host.key("ctrl+a")
                    host.type_text(str(invalid))

                    def complete_path():
                        entry = location()
                        text = A.accessible_text(entry) if entry is not None else None
                        return {"entry": snapshot(entry), "text": text} if text and text["text"] == str(invalid) else None

                    path_proof = wait(complete_path, 15, "exact typed path readback")
                    need(path_proof is not None, "full invalid EPUB path not entered")
                    result["path_readback"] = path_proof
                    result["confirmations"] = []
                    # Original compact flow: initial Return plus at most three
                    # confirmation Returns, only while the SAME chooser stays open.
                    # Never reopen F1, retype a path, or start a second import.
                    for attempt in range(4):
                        current = named_dialog("Import book", {"file chooser"})
                        if current is None:
                            break
                        need(structural(current) == result["chooser_ready"]["indices"], "chooser identity changed")
                        # After Return focus may move to the file list/Open button;
                        # re-read the original Location Layer without setting focus.
                        entries = [n for n in A.walk(current)
                                   if A.role(n) in ("text", "entry") and A.states(n).get("editable")
                                   and "Location Layer" in A.path_of(n)]
                        proofs = [A.accessible_text(n) for n in entries]
                        need(any(v and v["text"] == str(invalid) for v in proofs),
                             "path changed before bounded confirmation")
                        result["confirmations"].append({"index": attempt, "t": time.monotonic(),
                                                         "chooser": snapshot(current), "path_exact": True})
                        host.key("Return")
                        closed = wait(lambda: named_dialog("Import book", {"file chooser"}) is None,
                                      3, "chooser dismissal")
                        if closed:
                            break
                    need(named_dialog("Import book", {"file chooser"}) is None,
                         "chooser stayed open after original bounded confirmations")
                    final_state = host.wait_state(
                        lambda state: settled(state) and state["sequence"] > initial_state["sequence"] and state["error"] != 0,
                        timeout=120, description="single invalid import completed with nonzero error")
                    final_message = host.last_status()
                    need(final_message and final_message != before["name"], "final refusal message missing")
                    changed = wait(lambda: A.name(status) == final_message, 10, "final status AX name")
                    after = snapshot(status)
                    result["final_observation"] = {"state": final_state, "logged_message": final_message, "after": after}
                    def matching():
                        return [e for e in recorder.since(mark) if e.get("source_reference_is_target") is True
                                and e.get("owned_source") is True and e.get("source_name") == after["name"]
                                and e.get("type") == "object:property-change:accessible-name"
                                and "source_query_error" not in e]
                    observed = wait(matching, 5, "bound target name-change event") if changed else []
                    events = recorder.since(mark)
                    old_matches = [e for e in events if e.get("type", "").startswith("object:property-change")
                                   and e.get("detail1") == "accessible-name" and e.get("source_name") == after["name"]]
                    result.update(original_filter_matches=old_matches, target_event_matches=observed or [],
                                  target_errors=recorder.target_errors,
                                  raw_event_count=len(events), recognized_event_schema="object:property-change:accessible-name")
                    need(not recorder.error and not recorder.target_errors, "target event evidence incomplete")
                    result["pass"] = bool(changed and before["indices"] == after["indices"] and observed)
                else:
                    recorder = Recorder()
                    recorder.start_required()
                    result["executed"] = True
                    host.key("ctrl+shift+a")
                    pane = wait(lambda: named_dialog("Account and Sync", {"dialog", "frame"}), 20, "Account opening")
                    need(pane is not None, "one Account shortcut failed")
                    need(wait(lambda: A.focused_all(pane), 10, "Account inside focus"), "Account focus never entered")
                    result["opened"] = snapshot(pane)
                    result["control_names"] = [{"role": A.role(n), "name": A.name(n)} for n in A.walk(pane)
                        if A.role(n) in ("push button", "button", "entry", "text", "radio button")]
                    host.key("Escape")
                    result["escape_presses"] = 1
                    timeline = []
                    def restored():
                        pane_now = named_dialog("Account and Sync", {"dialog", "frame"})
                        focused = A.focused_all(app())
                        main = frame()
                        inside = bool(focused) and all(A.is_ancestor(main, n) or A.same(main, n) for n in focused)
                        timeline.append({"t": time.monotonic(), "dialog_present": pane_now is not None,
                                         "focused": [snapshot(n) for n in focused], "inside_main": inside})
                        return pane_now is None and inside
                    back = wait(restored, 15, "Account closed and main focus restored")
                    result.update({"pass": bool(back), "timeline": timeline, "focus_repair_performed": False})
                    need(not recorder.error, "event stream overflow")
                result["program_after"] = program()
                need(result["program_after"] == result["program_before"], "program identity changed")
            except Exception as error:
                result["pass"] = False
                result["error"] = type(error).__name__ + ": " + str(error)
            finally:
                result["query_errors"] = query_errors
                event_shutdown_safe = True
                try:
                    if recorder is not None:
                        recorder.stop()
                        if recorder.thread is not None:
                            recorder.thread.join(timeout=5)
                            need(not recorder.thread.is_alive(), "event thread did not stop within five seconds")
                        # Thread is stopped. Take one locked final snapshot before
                        # judging late errors or allowing a second host to start.
                        with recorder.lock:
                            events = list(recorder.items)
                            final_error = recorder.error
                            target_errors = list(recorder.target_errors)
                        save(case + "-events.json", events)
                        result["event_registration"] = {"registered": recorder.registered,
                            "rejected": recorder.rejected, "error": final_error, "thread_stopped": True}
                        errors = [e for e in events if "source_query_error" in e]
                        result["event_source_errors"] = {"count": len(errors), "first": errors[:5],
                            "non_target_errors_are_not_full_stream_acceptance": True}
                        result["final_target_errors"] = target_errors
                        if final_error or target_errors:
                            result["pass"] = False
                except Exception as error:
                    event_shutdown_safe = False
                    result["pass"] = False
                    result["event_shutdown_error"] = type(error).__name__ + ": " + str(error)
                finally:
                    # Event shutdown or evidence-save errors must never bypass
                    # cleanup of the exact host process this case created.
                    if host is not None:
                        try:
                            result["cleanup_exit"] = host.close()
                            result["cleanup_complete"] = host.process.poll() is not None
                        except Exception as error:
                            result["cleanup_error"] = str(error)
                            result["cleanup_complete"] = False
                        if not result.get("cleanup_complete") or result.get("cleanup_exit") != 0:
                            result["pass"] = False
                        if not result.get("cleanup_complete"):
                            event_shutdown_safe = False
                result["safe_to_start_next_case"] = event_shutdown_safe
                save(case + "-report.json", {**IDENTITY, **result})
                print(json.dumps({"case": case, **IDENTITY, **result}), flush=True)
            if not event_shutdown_safe:
                report["infrastructure_error"] = "previous case event/host shutdown incomplete; no next host started"
                break
        report["accepted"] = all(c["executed"] and c["pass"] for c in report["checks"].values())
    except Exception as error:
        report["error"] = type(error).__name__ + ": " + str(error)
    save("report.json", report)
    print(json.dumps(report), flush=True)
    return 0 if report["accepted"] else 1

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    need(len(sys.argv) == 2 and sys.argv[1] in ("build", "collect"), "exact stage")
    sys.exit(build() if sys.argv[1] == "build" else collect())
