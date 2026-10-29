#!/usr/bin/env python3
"""Actions-only same-source SDK 3.42 installation for original Team24 native gates."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SDK_SOURCE = "8357eafa28423a7ab93ba08b823af80f01ad1505"
SDK_PATHS = ("src", "include", "cmake", "CMakeLists.txt", "bindings")
VERSION = "3.42.0"
MODULES = ("annotation-export", "annotation-import", "font-library", "original-export",
           "jump-history", "sync-status-view")

def run(*args):
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True)

def files(root):
    return {p.relative_to(root).as_posix(): {
        "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()
    } for p in root.rglob("*") if p.is_file()}

def main():
    assert os.environ.get("GITHUB_ACTIONS") == "true" and sys.platform == "darwin"
    assert os.environ.get("EXR_APPLE_SDK_VERSION") == VERSION
    p = argparse.ArgumentParser()
    p.add_argument("--target", choices=("macos", "iphonesimulator"), required=True)
    target = p.parse_args().target
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert source == os.environ["GITHUB_SHA"]
    if subprocess.run(["git", "cat-file", "-e", SDK_SOURCE + "^{commit}"], cwd=ROOT,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        run("git", "fetch", "--no-tags", "origin", SDK_SOURCE)
    run("git", "diff", "--exit-code", SDK_SOURCE, source, "--", *SDK_PATHS)
    assert not subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all",
                                       "--", *SDK_PATHS], cwd=ROOT, text=True)
    out = ROOT / "build/raw3-ios-sdk" / target
    sdk, raw = out / "sdk", out / "raw-products"
    options = ["-DCMAKE_BUILD_TYPE=Release", "-DEXR_BUILD_TESTS=OFF",
               "-DEXR_BUILD_TOOLS=OFF", "-DEXR_ENABLE_AAC=OFF"]
    if target == "iphonesimulator":
        options += ["-DCMAKE_SYSTEM_NAME=iOS", "-DCMAKE_OSX_SYSROOT=iphonesimulator",
                    "-DCMAKE_OSX_ARCHITECTURES=arm64", "-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0",
                    "-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO"]
    run("cmake", "-S", ROOT, "-B", out / "sdk-build", *options)
    run("cmake", "--build", out / "sdk-build", "--parallel", "4")
    run("cmake", "--install", out / "sdk-build", "--prefix", sdk)
    header = (sdk / "include/exr/base.h").read_text()
    assert re.search(r'#define EXR_VERSION "([^"]+)"', header)[1] == VERSION
    run(sys.executable, "tools/build_apple_product.py", "--sdk", sdk, "--sdk-version", VERSION,
        "--target", target, "--build", out / "legacy-build")
    run(sys.executable, "tools/build_apple_product.py", "--sdk", sdk, "--sdk-version", VERSION,
        "--target", target, "--product-prefix", raw, "--selector-bytes-candidate",
        "--wave3", "--build", out / "raw-build")
    for root, candidate in ((sdk, False), (raw, True)):
        product = json.loads((root / "share/exreader-apple/product.json").read_text())
        assert product["source_sha"] == source and product["target"] == target
        assert product["sdk_version"] == VERSION
        assert product["selector_bytes_candidate"] is candidate
        assert product["wave3_enabled"] is candidate
        if candidate:
            assert set(MODULES).issubset(product["installed_modules"])
            assert product["sqlite_provider"] == "libreader_catalog_sqlite.a"
            assert product["system_sqlite_fallback"] is False
            assert product["reading_resolver_linked"] is False
    run(sys.executable, "tests/apple_host/evidence_contract.py", "sdk", "--root", sdk,
        "--platform", target, "--output", out / "sdk-identity.json")
    cloud = {"source_sha": source, "run_id": os.environ["GITHUB_RUN_ID"],
             "attempt": os.environ["GITHUB_RUN_ATTEMPT"], "target": target}
    identity = {**cloud, "sdk_version": VERSION, "sdk_content_candidate": SDK_SOURCE,
                "sdk_content_paths": SDK_PATHS, "sdk_files": files(sdk), "raw_files": files(raw)}
    (out / "sdk342-installed-identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    (out / "raw-identity.json").write_text(json.dumps(
        {**cloud, "raw_files": identity["raw_files"]}, indent=2) + "\n")
    (out / "wave3-packages.json").write_text(json.dumps({
        **cloud, "modules": MODULES, "sdk_version": VERSION, "sdk_frozen_source": SDK_SOURCE
    }, indent=2) + "\n")
    print(json.dumps({**cloud, "sdk_version": VERSION, "sdk_content_candidate": SDK_SOURCE,
                      "modules": MODULES}), flush=True)

if __name__ == "__main__":
    main()
