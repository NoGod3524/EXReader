#!/usr/bin/env python3
"""Fail closed unless the five manifests, binary exports and runtime smoke agree."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from symbols import PLATFORMS, ROOT, public_symbols
from manifest import source_files


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def features(manifest):
    options = manifest["compile_options"]["exr_options"]
    return {key: value for key, value in options.items() if key.startswith("EXR_ENABLE_") or
            key in ("EXR_BUILD_TEXT_INDEX", "EXR_BUILD_SHARED_COMPAT", "EXR_SANITIZE")}


def macros(manifest):
    return {key: sorted(value for value in definitions.split(";") if value.startswith("EXR_"))
            for key, definitions in manifest["compile_options"]["object_targets"].items()
            if key.endswith(".COMPILE_DEFINITIONS")}


def validate(manifests, symbols, smoke, public, android_runtime=None):
    require(set(manifests) == PLATFORMS, "require all five platform manifests")
    require(len(public) == 427, "S5 full SDK public header contract must contain 427 exports")
    reference = manifests["windows"]
    commit = reference["source"]["commit"]
    require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit), "missing actual source commit")
    sdk_hash = reference["source"]["sdk_input_sha256"]
    require(digest(sdk_hash), "invalid SDK input SHA256")
    require(bool(features(reference)) and bool(macros(reference)), "missing feature or macro evidence")
    cohort = list(manifests.items()) + ([("android-runtime", android_runtime)] if android_runtime else [])
    for name, manifest in cohort:
        require(manifest["platform"] == ("android" if name == "android-runtime" else name), f"{name}: platform mismatch")
        source = manifest["source"]
        require(source["commit"] == commit and source["sdk_input_sha256"] == sdk_hash, f"{name}: source identity mismatch")
        require(source["tracked_changes"] == "", f"{name}: SDK source was dirty")
        require(source["files"] == reference["source"]["files"] and bool(source["files"]), f"{name}: SDK input files differ")
        require(hashlib.sha256(json.dumps(source["files"], sort_keys=True).encode()).hexdigest() == sdk_hash,
                f"{name}: SDK input digest does not match file inventory")
        require(manifest["compiler"]["id"] and manifest["compiler"]["version"] and manifest["cmake"]["version"],
                f"{name}: missing compiler/CMake identity")
        require(manifest["configuration"] == "Release", f"{name}: not Release")
        require(manifest["compile_options"]["position_independent_code"] == "ON", f"{name}: PIC disabled")
        require(features(manifest) == features(reference), f"{name}: EXR features differ")
        require(macros(manifest) == macros(reference), f"{name}: compiled EXR macros differ")
        for dependency in ("expat", "freetype", "miniz", "zlib"):
            item, baseline = manifest["dependencies"][dependency], reference["dependencies"][dependency]
            require(item["enabled"] and item["version"] and digest(item["source_tree_sha256"]), f"{name}: missing {dependency} version/source")
            for key in ("version", "archive_sha256", "version_file_sha256"):
                require(item[key] == baseline[key], f"{name}: {dependency} {key} differs")
        artifact = manifest["artifact"]
        require(digest(artifact["sha256"]) and artifact["size_bytes"] > 0, f"{name}: invalid artifact identity")
        require(artifact["exported_symbol_count"] == len(public) and artifact["slices"], f"{name}: wrong export count")
        for part in artifact["slices"]:
            require(part["format"] in ("PE", "ELF", "Mach-O"), f"{name}: static definitions used as exports")
            require(len(part["symbols"]) == len(public) and set(part["symbols"]) == public, f"{name}: public export names differ")
    observed = {row["platform"]: row for row in symbols["platforms"]}
    require(len(symbols["platforms"]) == 5 and set(observed) == PLATFORMS, "incomplete binary symbol comparison")
    for name, row in observed.items():
        artifact = manifests[name]["artifact"]
        require(row["sha256"] == artifact["sha256"] and row["size_bytes"] == artifact["size_bytes"], f"{name}: symbols inspected a different binary")
        require(row["source_commit"] == commit and set(row["symbols"]) == public, f"{name}: binary symbols/source differ")
    require(symbols["common_count"] == 427 and symbols["differences"] == [] and
            symbols["desktop_sets_equal"] and symbols["all_sets_equal"], "inconsistent symbol aggregate")
    rows = smoke["platforms"]
    require(set(rows) == {"windows", "linux", "android"}, "incomplete runtime platform set")
    for name, row in rows.items():
        manifest = android_runtime if name == "android" and android_runtime else manifests[name]
        require(row["source_commit"] == commit and row["library_sha256"] == manifest["artifact"]["sha256"],
                f"{name}: runtime did not use the manifested binary/source")
        require(row["pages"] > 0 and row["search_hits"] == 1000 and row["width"] == 360 and row["height"] == 480,
                f"{name}: invalid smoke output")
        require(row["pixel_bytes"] == 360 * 480 * 4 and 0 < row["ink_pixels"] < 360 * 480, f"{name}: invalid pixel extent")
        for key in ("book_sha256", "font_sha256", "pixel_sha256", "raw_log_sha256"):
            require(digest(row[key]), f"{name}: missing {key}")
    for key in ("source_commit", "book_sha256", "font_sha256", "pages", "search_hits"):
        require(len({row[key] for row in rows.values()}) == 1 and smoke["equal"][key], f"runtime {key} mismatch")
    pixel_equal = len({row["pixel_sha256"] for row in rows.values()}) == 1
    require(pixel_equal == smoke["equal"]["pixel_sha256"], "pixel equality claim differs from observed hashes")
    require(pixel_equal or bool(smoke.get("pixel_difference_reason")), "unequal pixels need an evidenced cause")
    require(smoke["probe_source_sha256"] == hashlib.sha256((ROOT / "tools/platforms/probe.c").read_bytes()).hexdigest(),
            "runtime summary uses another probe source")
    return {"passed": True, "source_commit": commit, "sdk_input_sha256": sdk_hash,
            "platform_count": 5, "common_exports": len(public), "symbol_differences": 0,
            "pages_equal": True, "search_hits_equal": True, "pixels_equal": pixel_equal}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifests", type=Path, default=ROOT / "docs/validation")
    parser.add_argument("--symbols", type=Path, required=True)
    parser.add_argument("--smoke", type=Path, required=True)
    parser.add_argument("--android-runtime-manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    try:
        manifests = {name: read(args.manifests / f"build-manifest-{name}.json") for name in PLATFORMS}
        require(source_files(ROOT) == manifests["windows"]["source"]["files"],
                "current checkout SDK files differ from the manifested inputs")
        result = validate(manifests, read(args.symbols), read(args.smoke), public_symbols(ROOT / "include/exr"),
                          read(args.android_runtime_manifest) if args.android_runtime_manifest else None)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {"passed": False, "error": str(error)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return int(not result["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
