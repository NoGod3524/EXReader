"""Reject mixed commits, feature/dependency drift, renamed exports and reused smoke."""
import copy
import hashlib
import json

from check_evidence import validate, PLATFORMS, ROOT, public_symbols


def main():
    public = public_symbols(ROOT / "include/exr")
    files = {"src/fixture.c": "a" * 64}
    source = {"commit": "b" * 40, "sdk_input_sha256": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
              "tracked_changes": "", "files": files}
    artifact = {"sha256": "c" * 64, "size_bytes": 123, "exported_symbol_count": 427,
                "slices": [{"format": "ELF", "symbols": sorted(public)}]}
    base = {"source": source, "artifact": artifact, "compiler": {"id": "fixture", "version": "1"}, "cmake": {"version": "3.24"},
            "configuration": "Release", "compile_options": {"position_independent_code": "ON",
            "exr_options": {"EXR_ENABLE_PDF": "ON"}, "object_targets": {"base.COMPILE_DEFINITIONS": "EXR_STATIC"}},
            "dependencies": {name: {"enabled": True, "version": "1", "archive_sha256": "d" * 64,
            "version_file_sha256": "e" * 64, "source_tree_sha256": "f" * 64} for name in ("expat", "freetype", "miniz", "zlib")}}
    manifests = {name: {**copy.deepcopy(base), "platform": name} for name in PLATFORMS}
    symbols = {"platforms": [{"platform": name, "sha256": artifact["sha256"], "size_bytes": 123,
                              "source_commit": source["commit"], "symbols": sorted(public)} for name in PLATFORMS],
               "common_count": 427, "differences": [], "desktop_sets_equal": True, "all_sets_equal": True}
    row = {"source_commit": source["commit"], "library_sha256": artifact["sha256"], "pages": 215,
           "search_hits": 1000, "width": 360, "height": 480, "pixel_bytes": 691200, "ink_pixels": 20543,
           **{key: "e" * 64 for key in ("book_sha256", "font_sha256", "pixel_sha256", "raw_log_sha256")}}
    smoke = {"platforms": {name: dict(row) for name in ("windows", "linux", "android")},
             "equal": {key: True for key in ("source_commit", "book_sha256", "font_sha256", "pages", "search_hits", "pixel_sha256")},
             "probe_source_sha256": hashlib.sha256((ROOT / "tools/platforms/probe.c").read_bytes()).hexdigest()}
    assert validate(manifests, symbols, smoke, public)["passed"]
    mutations = [
        lambda m, s, r: m["ios"]["source"].update(commit="0" * 40),
        lambda m, s, r: m["linux"]["compile_options"]["exr_options"].update(EXR_ENABLE_PDF="OFF"),
        lambda m, s, r: m["android"]["dependencies"]["miniz"].update(version="2"),
        lambda m, s, r: m["macos"]["artifact"]["slices"][0]["symbols"].__setitem__(0, "vendor_leak"),
        lambda m, s, r: s["platforms"][0].update(sha256="0" * 64),
        lambda m, s, r: r["platforms"]["windows"].update(library_sha256="0" * 64),
        lambda m, s, r: r["platforms"]["linux"].update(search_hits=1),
        lambda m, s, r: r["platforms"]["android"].update(pixel_sha256="0" * 64),
    ]
    for mutate in mutations:
        m, s, r = copy.deepcopy((manifests, symbols, smoke))
        mutate(m, s, r)
        try:
            validate(m, s, r, public)
        except ValueError:
            continue
        raise AssertionError("invalid cross-platform evidence passed")
    # Agreement between five labels is insufficient: corrupt every recorded
    # SDK digest identically while keeping the actual file inventory unchanged.
    corrupted = copy.deepcopy(manifests)
    for manifest in corrupted.values():
        manifest["source"]["sdk_input_sha256"] = "0" * 64
    try:
        validate(corrupted, symbols, smoke, public)
    except ValueError as error:
        assert "digest does not match file inventory" in str(error)
    else:
        raise AssertionError("identically corrupted source identities accepted")
    print("PASS complete cohort and nine source/features/dependencies/exports/smoke rejection cases")


if __name__ == "__main__":
    main()
