"""Source-scope guard for the GTK raw Wave 3 package (Actions only).

The package owns the GTK host raw wiring, the Wave 3 owner-worker branches, the
new probe/workflow/docs and the pinned public pure-capture candidate. Everything
else, in particular the original C10 driver, the original C10 workflow, the
module schemas and implementations and the public desktop CMake file, must be
byte identical to the recorded base commit."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

BASE = "36d5deec"
ROOT = Path(__file__).resolve().parents[2]
OWNED = {
    "apps/reader/desktop/gtk_feature_integration.cmake",
    "apps/reader/reading-state/CMakeLists.txt",
    "apps/reader/reading-state/include/reader_reading_state_capture_raw_candidate.h",
    "apps/reader/reading-state/src/reading_state.cpp",
    "examples/linux/reading.c",
    "examples/linux/wave3_backend.inc",
    ".github/workflows/reader-gtk-raw-wave3.yml",
}
OWNED_PREFIXES = ("tests/reader_gtk_raw_wave3/", "docs/reader_gtk_raw_wave3/")
FROZEN = (
    "apps/reader/desktop/CMakeLists.txt",
    "tests/reader_wave3_c10/backend.c",
    "tests/reader_wave3_c10/check_ui.py",
    "tests/reader_wave3_c10/guard.py",
    "tests/reader_wave3_c10/identity.py",
    "tests/reader_wave3_c10/g13_diagnostic.py",
    ".github/workflows/reader-wave3-c10.yml",
    "apps/reader/annotation-import/src/annotation_import.cpp",
    "apps/reader/annotation-import/include/reader_annotation_import.h",
    "apps/reader/annotation-import/include/reader_annotation_import_raw3.h",
    "apps/reader/annotation-import/CMakeLists.txt",
    "apps/reader/annotation-export/src/annotation_export.cpp",
    "apps/reader/annotation-export/include/reader_annotation_export.h",
    "apps/reader/annotation-export/include/reader_annotation_export_raw3.h",
    "apps/reader/annotation-export/CMakeLists.txt",
    "apps/reader/jump-history/src/jump_history.cpp",
    "apps/reader/jump-history/include/reader_jump_history.h",
    "apps/reader/jump-history/CMakeLists.txt",
    "apps/reader/sync-status-view/src/sync_view.cpp",
    "apps/reader/sync-status-view/include/reader_sync_view.h",
    "apps/reader/sync-status-view/CMakeLists.txt",
    "apps/reader/font-library/src/library.cpp",
    "apps/reader/font-library/include/reader_font_library.h",
    "apps/reader/original-export/src/original_export.cpp",
    "apps/reader/original-export/include/reader_original_export.h",
    "apps/reader/reading-state/include/reader_reading_state.h",
    "apps/reader/reading-state/src/reading_resolve.cpp",
    "apps/reader/revisions/include/reader_revisions.h",
    "apps/reader/session/include/reader_session.h",
)


def git(*arguments):
    return subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def blob(relative):
    return subprocess.run(["git", "show", BASE + ":" + relative], cwd=ROOT, capture_output=True, check=True).stdout


def worktree(relative):
    return (ROOT / relative).read_bytes()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="build/reader-gtk-raw-wave3/guard.json")
    options = parser.parse_args()
    results = []

    def check(name, ok, detail=""):
        results.append({"check": name, "passed": bool(ok), "detail": detail})

    changed = [row for row in git("diff", "--name-only", BASE).splitlines() if row]
    changed += [row for row in git("ls-files", "--others", "--exclude-standard").splitlines() if row]
    outside = [row for row in changed
               if row not in OWNED and not row.startswith(OWNED_PREFIXES)]
    check("no-path-outside-the-package", not outside, outside)
    for relative in sorted(OWNED):
        check("owned-path-present-" + relative, (ROOT / relative).is_file())
    for relative in FROZEN:
        check("frozen-" + relative, worktree(relative) == blob(relative))
    # The pinned candidate is exactly the three blobs of the recorded capability
    # commit; the legacy public header and API stay untouched.
    pinned = {
        "apps/reader/reading-state/CMakeLists.txt": "2b513deeb2681eb2e0c674fe447ddfee83cb3994",
        "apps/reader/reading-state/include/reader_reading_state_capture_raw_candidate.h":
            "0cce3515dbcbed3c6b49356e1d6dc137b5a31aaa",
        "apps/reader/reading-state/src/reading_state.cpp": "25de29dd59828371d7c35dc8a6295b9d74bc738d",
    }
    for relative, expected in pinned.items():
        actual = hashlib.sha1(b"blob %d\x00" % len(worktree(relative)) + worktree(relative)).hexdigest()
        check("pinned-blob-" + relative, actual == expected, actual)
    # The raw branches must be gated on the explicit host option, never default.
    wave3 = (ROOT / "examples/linux/wave3_backend.inc").read_text(encoding="utf-8")
    check("raw-branches-are-option-gated", "EXR_READER_GTK_RAW3" in wave3)
    check("no-private-extern", "reader_rs_encode_retained_raw_v3" not in wave3)
    integration = (ROOT / "apps/reader/desktop/gtk_feature_integration.cmake").read_text(encoding="utf-8")
    check("legacy-family-still-default",
          "find_package(EXReaderJumpHistory 0.1.0 EXACT CONFIG REQUIRED)" in integration and
          "find_package(EXReaderAnnotationImport 0.1.0 EXACT CONFIG REQUIRED)" in integration)
    check("raw-family-is-explicit", "find_package(EXReaderJumpHistory 0.2.0 EXACT CONFIG REQUIRED)" in integration)
    check("candidate-is-required-for-raw-history", "EXR_READER_PURE_CAPTURE_CANDIDATE=1" in integration)
    # The raw GUI round reuses the exact DSF-G01 driver source and must keep every
    # one of its ten business records, its reveal-based chooser and its timeouts.
    ui = (ROOT / "tests/reader_gtk_raw_wave3/ui_raw.py").read_text(encoding="utf-8")
    records = [line.strip() for line in ui.splitlines() if line.strip().startswith("record('")]
    check("gui-driver-keeps-ten-records", len(records) == 10, records)
    for token in ("def visible_cell(", "def cell_click(", "def points_into(", "def ancestor(",
                  "seconds=45", "seconds=25", "seconds=20"):
        check("gui-driver-keeps-" + token, token in ui)
    check("gui-driver-declares-its-source-blob", "43bab342c97cde24ae30556e46cebe269312d66e" in ui)
    check("gui-driver-adds-only-the-raw-precondition",
          ui.count("save_identity_record") == 2 and "raw identity record" in ui)

    failed = [row for row in results if not row["passed"]]
    report = {"base": BASE, "changed": changed, "checks": results,
              "check_count": len(results), "failed": len(failed), "accepted": not failed}
    output = Path(options.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"guard_checks": len(results), "failed": len(failed)}))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
