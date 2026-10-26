"""Installed-family identity checks for the raw Wave 3 prefix (Actions only).

Every check reads the actual installed tree: package configs, version files,
installed headers and imported-target properties written by the modules
themselves. Nothing is inferred from the source tree."""
import argparse
import json
from pathlib import Path


def read(path):
    return Path(path).read_text(encoding="utf-8", errors="replace")


def config(prefix, package):
    """The installed package config file of one module."""
    return Path(prefix) / "lib" / "cmake" / package / (package + "Config.cmake")


def version(prefix, package):
    return Path(prefix) / "lib" / "cmake" / package / (package + "ConfigVersion.cmake")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--family", choices=("raw", "legacy"), required=True)
    parser.add_argument("--output", required=True)
    options = parser.parse_args()
    prefix = Path(options.prefix).resolve()
    headers = prefix / "include"
    results = []

    def check(name, ok, detail=""):
        results.append({"check": name, "passed": bool(ok), "detail": detail})

    def installed(package, expected):
        path = version(prefix, package)
        check(package + "-version-file", path.is_file(), str(path))
        if not path.is_file():
            return
        text = read(path)
        check(package + "-version-" + expected, 'PACKAGE_VERSION "' + expected + '"' in text,
              [line.strip() for line in text.splitlines() if "PACKAGE_VERSION" in line][:2])

    raw = options.family == "raw"
    # The four family-specific tools.
    installed("EXReaderAnnotationImport", "0.2.0" if raw else "0.1.0")
    installed("EXReaderJumpHistory", "0.2.0" if raw else "0.1.0")
    installed("EXReaderSyncView", "0.2.0" if raw else "0.1.0")
    installed("EXReaderAnnotationExport", "0.2.0" if raw else "0.1.0")
    # The two single-family tools never change family.
    installed("EXReaderFontLibrary", "0.1.0")
    installed("EXReaderOriginalExport", "0.1.0")
    installed("EXReaderReadingState", "0.2.0" if raw else "0.1.0")
    installed("EXReaderSession", "0.2.0" if raw else "0.1.0")

    candidate = headers / "reader_reading_state_capture_raw_candidate.h"
    check("pure-capture-candidate-header", candidate.is_file() == raw, str(candidate))
    import_raw = headers / "reader_annotation_import_raw3.h"
    export_raw = headers / "reader_annotation_export_raw3.h"
    check("raw-import-header", import_raw.is_file() == raw, str(import_raw))
    check("raw-export-header", export_raw.is_file() == raw, str(export_raw))
    if raw:
        text = read(import_raw)
        check("raw-import-macro", '#define READER_ANNOTATION_IMPORT_RAW3_VERSION "0.2.0"' in text)
        text = read(export_raw)
        check("raw-export-macro", '#define READER_ANNOTATION_EXPORT_RAW3_VERSION "0.2.0"' in text)
        text = read(candidate)
        check("candidate-declares-public-encoder", "reader_rs_encode_capture_raw_candidate(" in text)
        check("candidate-requires-both-definitions",
              "EXR_READER_SELECTOR_BYTES_CANDIDATE" in text and "EXR_READER_PURE_CAPTURE_CANDIDATE" in text)
    # The two headers are one file with family #ifdef branches, so the installed
    # family is read from the exported target properties, not from header text.
    for package, target in (("EXReaderJumpHistory", "reader_jump_history"),
                            ("EXReaderSyncView", "reader_sync_view")):
        exported = prefix / "lib" / "cmake" / package / (package + "Targets.cmake")
        text = read(exported) if exported.is_file() else ""
        check(package + "-target-capability",
              ("EXR_READER_SELECTOR_BYTES_CANDIDATE=1" in text) == raw, str(exported))
    # The package configs carry the family they were configured for.
    for package in ("EXReaderAnnotationImport", "EXReaderJumpHistory", "EXReaderSyncView", "EXReaderAnnotationExport"):
        path = config(prefix, package)
        text = read(path) if path.is_file() else ""
        check(package + "-config-guard", ("_exr_raw_guard_target" in text) == raw, str(path))
    for package in ("EXReaderFontLibrary", "EXReaderOriginalExport"):
        path = config(prefix, package)
        text = read(path) if path.is_file() else ""
        check(package + "-single-family", "_exr_raw_guard_target" not in text, str(path))
    # The capability is a public compile definition of the installed codec, so a
    # consumer cannot silently build the history encoder without it.
    codec = config(prefix, "EXReaderReadingState")
    text = read(codec) if codec.is_file() else ""
    check("reading-state-family-guard", ("_exr_raw_guard_target" in text) == raw, str(codec))
    exported = (prefix / "lib" / "cmake" / "EXReaderReadingState" / "EXReaderReadingStateTargets.cmake")
    text = read(exported) if exported.is_file() else ""
    check("codec-target-carries-selector-capability",
          ("EXR_READER_SELECTOR_BYTES_CANDIDATE=1" in text) == raw, str(exported))
    check("codec-target-carries-pure-capture-capability",
          ("EXR_READER_PURE_CAPTURE_CANDIDATE=1" in text) == raw, str(exported))

    failed = [row for row in results if not row["passed"]]
    report = {"prefix": str(prefix), "family": options.family, "checks": results,
              "check_count": len(results), "failed": len(failed), "accepted": not failed}
    output = Path(options.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"family": options.family, "checks": len(results), "failed": len(failed)}))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
