#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only, separately budgeted frozen SDK and C02 Apple product installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
SDK_SHA = "8357eafa28423a7ab93ba08b823af80f01ad1505"
SDK_PATHS = ("src","include","cmake","CMakeLists.txt","bindings")

def run(*command):
    print(json.dumps(list(map(str,command))),flush=True)
    subprocess.run(list(map(str,command)),cwd=ROOT,check=True)

def current():
    source = subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    assert os.environ.get("GITHUB_ACTIONS") == "true" and sys.platform == "darwin"
    assert source == os.environ["GITHUB_SHA"]
    return source

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target",choices=("macos","iphonesimulator"),required=True)
    parser.add_argument("--phase",choices=("sdk","products"),required=True)
    args = parser.parse_args()
    source = current()
    out = ROOT/"build/apple-c02"/args.target
    sdk, products = out/"sdk", out/"products"
    out.mkdir(parents=True,exist_ok=True)
    if args.phase == "sdk":
        run("git","diff","--exit-code",SDK_SHA,source,"--",*SDK_PATHS)
        assert not subprocess.check_output(["git","status","--porcelain","--untracked-files=all","--",*SDK_PATHS],cwd=ROOT)
        options = ["-DCMAKE_BUILD_TYPE=Release","-DEXR_BUILD_TESTS=OFF","-DEXR_BUILD_TOOLS=OFF","-DEXR_ENABLE_AAC=OFF"]
        if args.target == "iphonesimulator":
            options += ["-DCMAKE_SYSTEM_NAME=iOS","-DCMAKE_OSX_SYSROOT=iphonesimulator",
                        "-DCMAKE_OSX_ARCHITECTURES=arm64","-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0",
                        "-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO"]
        else:
            options += ["-DCMAKE_OSX_DEPLOYMENT_TARGET=12.0"]
        run("cmake","-S",ROOT,"-B",out/"sdk-build",*options)
        run("cmake","--build",out/"sdk-build","--parallel","4")
        run("cmake","--install",out/"sdk-build","--prefix",sdk)
        identity = dict(source=source,run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],
                        frozen_sdk=SDK_SHA,target=args.target,sdk_paths=SDK_PATHS,
                        files={p.relative_to(sdk).as_posix():sha(p) for p in sorted(sdk.rglob("*")) if p.is_file()})
        (sdk/"c02-sdk-identity.json").write_text(json.dumps(identity,indent=2)+"\n")
    else:
        identity = json.loads((sdk/"c02-sdk-identity.json").read_text())
        assert identity["source"] == source and identity["frozen_sdk"] == SDK_SHA and identity["target"] == args.target
        assert identity["run"] == os.environ["GITHUB_RUN_ID"] and identity["attempt"] == os.environ["GITHUB_RUN_ATTEMPT"]
        for name,digest in identity["files"].items():
            assert sha(sdk/name) == digest,name
        original_hash = products/"original-hash"
        options = ["-DCMAKE_BUILD_TYPE=Release","-DEXREADER_OPDS_HASH_ONLY=ON",
                   "-DCMAKE_INSTALL_PREFIX="+str(original_hash)]
        if args.target == "iphonesimulator":
            options += ["-DCMAKE_SYSTEM_NAME=iOS","-DCMAKE_OSX_SYSROOT=iphonesimulator",
                        "-DCMAKE_OSX_ARCHITECTURES=arm64","-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0",
                        "-DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO"]
        else:
            options += ["-DCMAKE_OSX_DEPLOYMENT_TARGET=12.0"]
        run("cmake","-S",ROOT/"extras/opds","-B",out/"original-hash-build",*options)
        run("cmake","--build",out/"original-hash-build","--parallel","4")
        run("cmake","--install",out/"original-hash-build")
        os.environ["EXREADER_ORIGINAL_HASH_PREFIX"] = str(original_hash.resolve())
        run(sys.executable,"tools/build_apple_product.py","--sdk",sdk,"--sdk-version","3.42.0",
            "--target",args.target,"--product-prefix",products,"--build",out/"products-build")
        product = json.loads((products/"share/exreader-apple/product.json").read_text())
        assert product["source_sha"] == source and product["c02_admission"] is True
        (products/"c02-product-identity.json").write_text(json.dumps(dict(
            source=source,run=os.environ["GITHUB_RUN_ID"],attempt=os.environ["GITHUB_RUN_ATTEMPT"],target=args.target,
            frozen_sdk=SDK_SHA,files={p.relative_to(products).as_posix():sha(p)
                                    for p in sorted(products.rglob("*")) if p.is_file()}),indent=2)+"\n")

if __name__ == "__main__":
    main()
