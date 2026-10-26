"""Actions-only driver for the GTK raw0.2 Wave 3 package.

It installs two real prefixes (the explicit raw0.2 family and the original
legacy 0.1 family), builds the actual GTK host and the raw owner probe from the
installed packages only, runs the raw business probe on real SDK books, and
proves the legacy configuration still configures and links with RAW3 OFF. Every
build, fixture and program run happens here in Actions; nothing runs locally."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build/gtk-raw-wave3"
SDK = ROOT / "build/reading-library/stage"
PREFIX = OUT / "raw-stage"
LEGACY = OUT / "legacy-stage"
RAW_MODULES = {"revisions", "commands", "desktop-metadata", "sync", "session", "reading-state",
               "reading-commands", "annotation-view", "jump-history", "sync-status-view",
               "annotation-import", "annotation-export"}
COMMON = [("product", "apps/reader/store/native"), ("webdav", "extras/webdav"),
          ("revisions", "apps/reader/revisions"), ("commands", "apps/reader/commands"),
          ("desktop-metadata", "apps/reader/desktop-metadata"), ("sync", "apps/reader/sync"),
          ("session", "apps/reader/session"), ("credentials", "extras/credentials"),
          ("sideload", "extras/sideload"), ("reading-state", "apps/reader/reading-state"),
          ("reading-commands", "apps/reader/reading-commands"), ("annotation-view", "apps/reader/annotation-view")]
HOST_MODULES = [("search", "apps/reader/search"), ("navigation", "apps/reader/navigation"),
                ("font-library", "apps/reader/font-library"), ("original-export", "apps/reader/original-export"),
                ("jump-history", "apps/reader/jump-history"), ("sync-status-view", "apps/reader/sync-status-view"),
                ("annotation-import", "apps/reader/annotation-import"), ("annotation-export", "apps/reader/annotation-export")]


def run(label, args, timeout=1800, env=None, expect=0):
    print("RUN " + label, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    done = subprocess.run([str(a) for a in args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout, env=env)
    (OUT / (label + ".log")).write_text(done.stdout + "\n" + done.stderr, encoding="utf-8")
    print(done.stdout[-4000:], flush=True)
    if done.returncode != expect:
        raise RuntimeError(label + ": " + str(done.returncode) + "\n" + done.stderr[-4000:])
    return done


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_epub(path):
    """Two chapters with unique markers, so a search landing can never coincide
    with the page caret the page turn produced. Same container shape as the
    repository's sample.epub; nothing outside this attempt's work dir is read."""
    lines = "".join("<p>line %d keeps ordinary reading words moving through the page so that "
                    "several pages exist.</p>" % index for index in range(60))
    chapter = ('<?xml version="1.0" encoding="utf-8"?>'
               '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>%s</title></head><body>%s'
               '<p>%s appears only here.</p>%s</body></html>')
    container = ('<?xml version="1.0" encoding="utf-8"?>'
                 '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="OEBPS/book.opf" '
                 'media-type="application/oebps-package+xml"/></rootfiles></container>')
    package = ('<?xml version="1.0" encoding="utf-8"?>'
               '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">'
               '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
               '<dc:identifier id="id">urn:uuid:11111111-2222-4333-8444-555555555555</dc:identifier>'
               '<dc:title>Marker book</dc:title><dc:language>en</dc:language></metadata>'
               '<manifest><item id="one" href="Text/first.xhtml" media-type="application/xhtml+xml"/>'
               '<item id="two" href="Text/second.xhtml" media-type="application/xhtml+xml"/></manifest>'
               '<spine><itemref idref="one"/><itemref idref="two"/></spine></package>')
    path = Path(path)
    with zipfile.ZipFile(path, "w") as archive:
        info = zipfile.ZipInfo("mimetype")
        archive.writestr(info, "application/epub+zip", zipfile.ZIP_STORED)
        for name, text in (("META-INF/container.xml", container),
                           ("OEBPS/book.opf", package),
                           ("OEBPS/Text/first.xhtml", chapter % ("One", lines, "NEEDLEONE", lines)),
                           ("OEBPS/Text/second.xhtml", chapter % ("Two", lines, "NEEDLETWO", lines))):
            archive.writestr(name, text, zipfile.ZIP_DEFLATED)
    return path


def cmake(label, source, binary, prefix, extra=(), targets=(), install=False):
    options = ["-DCMAKE_PREFIX_PATH=" + str(prefix) + ";" + str(SDK), "-DCMAKE_INSTALL_PREFIX=" + str(prefix),
               "-DREADER_PRODUCT_PREFIX=" + str(prefix), "-DEXR_SDK=" + str(SDK), "-DEXR_SDK_VERSION=3.41.0"]
    run(label + "-configure", ["cmake", "-S", source, "-B", binary, "-G", "Ninja",
                               "-DCMAKE_BUILD_TYPE=Release", *options, *extra])
    run(label + "-build", ["cmake", "--build", binary, "--parallel", "4",
                           *(["--target", *targets] if targets else [])])
    if install:
        run(label + "-install", ["cmake", "--install", binary])


def build_sdk():
    run("sdk-configure", ["cmake", "--preset", "reading-library"])
    run("sdk-build", ["cmake", "--build", "--preset", "reading-library", "--parallel", "4"])
    run("sdk-install", ["cmake", "--install", "build/reading-library"])


def install_family(profile, prefix, raw):
    modules = COMMON + HOST_MODULES
    for module, source in modules:
        extra = []
        if raw and module in RAW_MODULES:
            extra.append("-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON")
        if raw and module == "reading-state":
            extra.append("-DEXR_READER_PURE_CAPTURE_CANDIDATE=ON")
        if module == "font-library":
            extra.append("-DREADER_FONT_LIBRARY_BUILD=ON")
        if module == "annotation-import":
            extra.append("-DREADER_ANNOTATION_IMPORT_BUILD=ON")
        # search and navigation need the SDK 3.41 candidate explicitly.
        cmake(profile + "-" + module, ROOT / source, OUT / (profile + "-" + module), prefix,
              extra=extra, install=True)


def installed(profile, prefix):
    report = OUT / (profile + "-install.json")
    run(profile + "-install-check", [sys.executable, "tests/reader_gtk_raw_wave3/check_install.py",
                                     "--prefix", prefix, "--family", "raw" if profile == "raw" else "legacy",
                                     "--output", report])
    return json.loads(report.read_text())


HOST_OPTIONS = ["-DEXR_READER_BUILD_GTK=ON", "-DEXR_LINUX_REVIEW_TESTS=ON", "-DEXR_LINUX_FIXED_TESTS=ON",
                "-DEXR_READER_PAGE_BACKGROUND=ON", "-DEXR_READER_GTK_ACCOUNT=ON",
                "-DEXR_READER_GTK_READING_RECORDS=ON", "-DEXR_READER_GTK_SEARCH=ON",
                "-DEXR_READER_GTK_NAVIGATION=ON", "-DEXR_READER_GTK_WAVE3=ON"]


def host_options(prefix):
    return HOST_OPTIONS + ["-DREADER_METADATA_PREFIX=" + str(prefix), "-DREADER_ACCOUNT_PREFIX=" + str(prefix),
                           "-DREADER_READING_RECORDS_PREFIX=" + str(prefix), "-DREADER_SEARCH_PREFIX=" + str(prefix),
                           "-DREADER_NAVIGATION_PREFIX=" + str(prefix), "-DREADER_WAVE3_PREFIX=" + str(prefix)]


def build_raw_host():
    binary = OUT / "raw-host"
    cmake("raw-host", ROOT / "apps/reader/desktop", binary, PREFIX,
          extra=host_options(PREFIX) + ["-DEXR_READER_GTK_RAW3=ON",
                                        "-DREADER_GTK_RAW3_PREFIX=" + str(PREFIX)],
          targets=("exreader-linux", "reader-gtk-wave3-raw-backend"))
    payload = OUT / "package"
    run("raw-package", [sys.executable, "tools/build_linux_host.py", "--sdk", "build/reading-library/stage",
                        "--sdk-version", "3.41.0", "--binary", binary / "gtk-host/exreader-linux",
                        "--output", payload])
    return binary, payload


def build_legacy_host():
    """Configure and link the unchanged OFF configuration; no legacy suite rerun."""
    binary = OUT / "legacy-host"
    cmake("legacy-host", ROOT / "apps/reader/desktop", binary, LEGACY,
          extra=host_options(LEGACY) + ["-DEXR_READER_GTK_RAW3=OFF"],
          targets=("exreader-linux-reading", "reader-gtk-wave3-backend"))
    return binary


def backend(font):
    work = OUT / "work"
    for path in (work / "a", work / "b", work / "logs"):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
        path.chmod(0o700)
    make_epub(work / "logs/markers.epub")
    binary = OUT / "raw-host/reader-gtk-wave3-raw-backend"
    done = run("raw-backend", [binary, work / "a/library.sqlite", work / "b/library.sqlite",
                               ROOT / font, ROOT / "tests/fixtures", work / "logs"], timeout=900)
    checks = [json.loads(line) for line in done.stdout.splitlines() if line.startswith("{\"check\"")]
    summary = json.loads([line for line in done.stdout.splitlines() if line.startswith("{\"backend_checks\"")][-1])
    failed = [row for row in checks if not row.get("pass")]
    report = {"binary": str(binary), "binary_sha256": sha(binary), "checks": checks,
              "check_count": len(checks), "requirement_count": summary["backend_checks"],
              "failed": len(failed), "accepted": not failed and len(checks) > 0}
    (OUT / "raw-backend.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def host_identity(binary):
    wanted = ("reader_annotation_import_raw3_run", "reader_annotation_export_raw3_run",
              "reader_jh_commit_wire_raw_v3", "reader_jh_commit_fixed_v3",
              "reader_rs_encode_capture_raw_candidate", "reader_sync_view_capture",
              "rfl_import_file", "roe_run")
    names = set()
    for line in run("raw-host-symbols", ["nm", "--defined-only",
                                         binary / "gtk-host/exreader-linux"]).stdout.splitlines():
        parts = line.split()
        if parts:
            names.add(parts[-1])
    symbols = "\n".join(name for name in wanted if name in names)
    text = (binary / "CMakeCache.txt").read_text(encoding="utf-8", errors="replace")
    checks = [
        ("raw-prefix-selected", "READER_GTK_RAW3_PREFIX:PATH=" + str(PREFIX) in text),
        ("wave3-prefix-is-the-raw-prefix", "READER_WAVE3_PREFIX:PATH=" + str(PREFIX) in text),
        ("wave3-enabled", "EXR_READER_GTK_WAVE3:BOOL=ON" in text),
        ("raw3-enabled", "EXR_READER_GTK_RAW3:BOOL=ON" in text),
        ("raw-import-symbol", "reader_annotation_import_raw3_run" in symbols),
        ("raw-export-symbol", "reader_annotation_export_raw3_run" in symbols),
        ("raw-jump-history-symbol", "reader_jh_commit_wire_raw_v3" in symbols),
        ("pure-capture-symbol", "reader_rs_encode_capture_raw_candidate" in symbols),
        ("raw-sync-view-symbol", "reader_sync_view_capture" in symbols),
        ("font-library-symbol", "rfl_import_file" in symbols),
        ("original-export-symbol", "roe_run" in symbols),
    ]
    report = {"binary": str(binary / "gtk-host/exreader-linux"),
              "binary_sha256": sha(binary / "gtk-host/exreader-linux"),
              "checks": [{"check": name, "passed": ok} for name, ok in checks],
              "accepted": all(ok for _, ok in checks)}
    (OUT / "raw-host-identity.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def build_compact_host():
    """The compact payload the five tools live in, on the raw0.2 family."""
    binary = OUT / "compact-host"
    cmake("compact-host", ROOT / "apps/reader/desktop", binary, PREFIX,
          extra=host_options(PREFIX) + ["-DEXR_READER_GTK_RAW3=ON",
                                        "-DREADER_GTK_RAW3_PREFIX=" + str(PREFIX),
                                        "-DEXR_READER_GTK_COMPACT=ON"],
          targets=("exreader-linux",))
    payload = OUT / "compact-package"
    run("compact-package", [sys.executable, "tools/build_linux_host.py", "--sdk", "build/reading-library/stage",
                            "--sdk-version", "3.41.0", "--binary", binary / "gtk-host/exreader-linux",
                            "--output", payload])
    return payload


def gui(enabled):
    """One full raw five-tool GUI round: the exact DSF-G01 driver source plus its
    documented raw identity precondition, on the compact raw0.2 host."""
    if not enabled:
        return {"executed": False,
                "reason": "the full raw GUI round is only requested explicitly, never by a push run"}
    fixtures = OUT / "gui-fixtures"
    seed = OUT / "seed"
    for path in (fixtures, seed):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
    seed.chmod(0o700)
    payload = build_compact_host()
    book = fixtures / "history.txt"
    probe = OUT / "raw-host/reader-gtk-wave3-raw-backend"
    run("gui-seed", [probe, seed / "library.sqlite", seed / "unused.sqlite",
                     ROOT / "tests/fixtures/fonts/primary.ttf", ROOT / "tests/fixtures", fixtures,
                     "seed", book], timeout=600)
    annotations = fixtures / "annotations.jsonl"
    if not annotations.is_file() or not annotations.stat().st_size:
        raise RuntimeError("seed produced no raw annotation file")
    output = OUT / "gui"
    if output.exists():
        shutil.rmtree(output)
    script = ("openbox >/dev/null 2>&1 & "
              "gsettings set org.gnome.desktop.interface toolkit-accessibility true; "
              "gsettings set org.gnome.desktop.a11y.applications screen-reader-enabled true; "
              + sys.executable + " tests/reader_gtk_raw_wave3/ui_raw.py"
              + " --payload " + str(payload)
              + " --book " + str(book)
              + " --annotations " + str(annotations)
              + " --font tests/fixtures/fonts/primary.ttf"
              + " --output " + str(output))
    environment = dict(os.environ, PYTHONPATH=str(OUT / "gtk-atspi-client"))
    run("raw-gui", ["xvfb-run", "-a", "-s", "-screen 0 1440x3600x24", "dbus-run-session", "--",
                    "bash", "-c", script], timeout=2400, env=environment)
    report = json.loads((output / "result.json").read_text(encoding="utf-8"))
    return {"executed": True, "driver": "tests/reader_gtk_raw_wave3/ui_raw.py",
            "driver_source_blob": "43bab342c97cde24ae30556e46cebe269312d66e",
            "program_sha256": report.get("program_sha256"),
            "checks": report.get("checks", []), "accepted": bool(report.get("accepted")),
            "output": str(output),
            "navigation_and_batch_import": "not executed in this round and not counted as passed"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gui", action="store_true",
                        help="run the one full raw five-tool GUI round after every other scope passes")
    parser.add_argument("--skip-legacy", action="store_true")
    options = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    result = {"source": run("source", ["git", "rev-parse", "HEAD"]).stdout.strip()}
    build_sdk()
    install_family("raw", PREFIX, True)
    result["raw_install"] = installed("raw", PREFIX)
    binary, payload = build_raw_host()
    result["raw_host"] = host_identity(binary)
    try:
        result["raw_backend"] = backend("tests/fixtures/fonts/primary.ttf")
    except Exception as error:
        # Keep the remaining scopes honest inside the same attempt: a failed probe
        # is recorded as failed and the legacy OFF check still runs.
        result["raw_backend"] = {"accepted": False, "check_count": 0,
                                 "error": str(error)[-3000:]}
    if not options.skip_legacy:
        install_family("legacy", LEGACY, False)
        result["legacy_install"] = installed("legacy", LEGACY)
        legacy = build_legacy_host()
        result["legacy_host"] = {"binary": str(legacy / "gtk-host/exreader-linux"),
                                 "binary_sha256": sha(legacy / "gtk-host/exreader-linux"),
                                 "configured_and_linked": True,
                                 "suite_rerun": False,
                                 "note": "RAW3 OFF keeps the original 0.1 modules; only configure and link ran"}
    base = (result["raw_install"]["accepted"] and result["raw_host"]["accepted"]
            and result["raw_backend"]["accepted"]
            and result.get("legacy_install", {}).get("accepted", True)
            and (options.skip_legacy or result.get("legacy_host", {}).get("configured_and_linked", False)))
    # One full GUI round, only on an explicit request and only after every
    # non-GUI scope of this same attempt already passed.
    result["gui"] = gui(options.gui and base)
    accepted = base and (not options.gui or result["gui"].get("accepted", False))
    result["accepted"] = bool(accepted)
    (OUT / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"accepted": result["accepted"],
                      "raw_checks": result["raw_backend"].get("check_count", 0),
                      "gui_executed": result["gui"]["executed"],
                      "gui_accepted": result["gui"].get("accepted", False)}))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
