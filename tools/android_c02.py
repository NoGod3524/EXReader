#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Installed Android C02 dependencies shared by the production APK builders."""
import hashlib
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SDK_BASE = "8357eafa28423a7ab93ba08b823af80f01ad1505"
COORDINATOR_BASE = "a8d0b162d8c21617e4c2c837e3eb2b2174bbf69b"
FROZEN_COORDINATOR = [
    "extras/migration/windows_coordinator_hardening_20261030",
    "tests/migration/windows_coordinator_hardening_20261030",
    "extras/migration/windows_coordinator_cas_20261030",
    "tests/migration/windows_coordinator_cas_20261030",
    "extras/migration/windows_admission_lease_20261030",
]
SOURCES = ["examples/android", "apps/reader", "extras/android-import-entry/sample", "extras/opds",
    "tools/android_c02.py", "tools/build_android_host.py",
    "extras/migration/posix_c02_admission_20261031",
    "extras/migration/posix_c02_sdk_admission_20261031", *FROZEN_COORDINATOR]

def run(command):
    print("+", " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=ROOT, check=True)

def provenance():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Android C02 builds run only on Actions")
    source = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    if source != os.environ["GITHUB_SHA"]:
        raise SystemExit("Android C02 build source differs from the Actions source")
    for baseline, paths in [
        (SDK_BASE, ["src", "include", "bindings", "cmake", "CMakeLists.txt"]),
        (COORDINATOR_BASE, FROZEN_COORDINATOR)]:
        if subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", baseline, "HEAD", "--", *paths]).returncode:
            raise SystemExit("Frozen Android C02 source differs: " + baseline)
    files = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "--", *SOURCES], text=True).splitlines()
    return dict(profile="c02", source=source, sdk_base=SDK_BASE, coordinator_base=COORDINATOR_BASE,
                source_files_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files})

def common(ndk):
    return ["-G", "Ninja", "-DCMAKE_TOOLCHAIN_FILE=" + str(Path(ndk) / "build/cmake/android.toolchain.cmake"),
            "-DANDROID_ABI=x86_64", "-DANDROID_PLATFORM=android-26", "-DANDROID_STL=c++_static",
            "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
            "-DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=BOTH"]

def install(sdk, prefix, work, ndk):
    """Append only admission libraries/headers to an installed SDK or own prefix."""
    provenance()
    sdk, prefix, work = Path(sdk).resolve(), Path(prefix).resolve(), Path(work).resolve()
    for name, source, extra in [
        ("abi2", "extras/migration/windows_coordinator_hardening_20261030", []),
        ("native", "extras/migration/posix_c02_admission_20261031", ["-DWH_PREFIX=" + str(prefix)]),
        ("sdk", "extras/migration/posix_c02_sdk_admission_20261031",
         ["-DWH_PREFIX=" + str(prefix), "-DPC02_PREFIX=" + str(prefix), "-DEXR_SDK=" + str(sdk)])]:
        build = work / name
        run(["cmake", "-S", ROOT / source, "-B", build, *common(ndk),
             "-DCMAKE_INSTALL_PREFIX=" + str(prefix), *extra])
        run(["cmake", "--build", build, "--parallel", "4"])
        run(["cmake", "--install", build])
    return prefix

def install_hash(prefix, work, ndk):
    """The current product catalog requires the independent installed hash owner."""
    provenance()
    prefix, work = Path(prefix).resolve(), Path(work).resolve()
    run(["cmake", "-S", ROOT / "extras/opds", "-B", work, *common(ndk),
         "-DEXREADER_OPDS_HASH_ONLY=ON", "-DCMAKE_INSTALL_PREFIX=" + str(prefix)])
    run(["cmake", "--build", work, "--parallel", "4"])
    run(["cmake", "--install", work])
    return prefix
