#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only actual Android host build with installed native C02 admission."""
import hashlib, json, os, pathlib, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "evidence/android-c02"
def run(command):
    print("+", " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=ROOT, check=True)
def main():
    if os.environ.get("GITHUB_ACTIONS") != "true": raise SystemExit("Actions execution required")
    OUT.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / "tools"))
    import build_android_host as host
    sdk = ROOT / "stage/android-c02-sdk"
    host.build_sdk(sdk, ROOT / "build/android-c02-sdk")
    product = ROOT / "stage/android-product"
    host.build_product(product, ROOT / "build/android-c02-product")
    host.patch_android_libraries(sdk)
    toolchain = host.ndk_home() / "build/cmake/android.toolchain.cmake"
    common = ["-G", "Ninja", "-DCMAKE_TOOLCHAIN_FILE=" + str(toolchain), "-DANDROID_ABI=x86_64",
              "-DANDROID_PLATFORM=android-26", "-DANDROID_STL=c++_static", "-DCMAKE_BUILD_TYPE=Release",
              "-DCMAKE_POSITION_INDEPENDENT_CODE=ON", "-DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=BOTH"]
    abi = ROOT / "stage/android-c02-abi2"
    native = ROOT / "stage/android-c02-native"
    admission = ROOT / "stage/android-c02"
    for name, source, prefix, extra in [
        ("abi2", "extras/migration/windows_coordinator_hardening_20261030", abi, []),
        ("native", "extras/migration/posix_c02_admission_20261031", native, ["-DWH_PREFIX=" + str(abi)]),
        ("sdk-admission", "extras/migration/posix_c02_sdk_admission_20261031", admission,
         ["-DWH_PREFIX=" + str(abi), "-DPC02_PREFIX=" + str(native), "-DEXR_SDK=" + str(sdk)])]:
        build = ROOT / ("build/android-c02-" + name)
        run(["cmake", "-S", source, "-B", build, *common, "-DCMAKE_INSTALL_PREFIX=" + str(prefix), *extra])
        run(["cmake", "--build", build, "--parallel", "4"])
        run(["cmake", "--install", build])
    assets = ROOT / "examples/android/app/src/main/assets"
    assets.mkdir(parents=True, exist_ok=True)
    run([sys.executable, "tools/reader_catalog_assets.py", "--output", assets / "reader-catalog-v1.json"])
    from host_font import fetch
    font = fetch(ROOT / "build/c02-host-font")
    shutil.copyfile(font / "Reader.otf", assets / "Reader.otf")
    shutil.copyfile(font / "OFL.txt", assets / "OFL.txt")
    android = ROOT / "examples/android"
    (android / "local.properties").write_text("sdk.dir=" + str(host.android_home()) + "\n")
    run(["gradle", "-p", android, "--no-daemon", "--stacktrace", ":app:assembleDebug", ":app:assembleDebugAndroidTest",
         "-PexrSdk=" + str(sdk), "-PexrSdkVersion=3.42.0", "-PexrC02Prefix=" + str(admission),
         "-PexrProduct=" + str(product), "-PexrC02Test=true", "-PexrTestRunner=org.exreader.host.C02HostTest"])
    app = android / "app/build/outputs/apk/debug/app-debug.apk"
    test = android / "app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
    for source in (app, test): shutil.copyfile(source, OUT / source.name)
    # ELF/provider inspection remains on Actions. Native host must call the same
    # shared SDK; the installed admission archives must not define SDK symbols.
    ndkbin = host.ndk_home() / "toolchains/llvm/prebuilt/linux-x86_64/bin"
    native_hosts = list((android / "app/build/intermediates/cxx/Debug").rglob("libexreader_host.so"))
    assert len(native_hosts) == 1, native_hosts
    shutil.copyfile(native_hosts[0], OUT / "libexreader_host.so")
    symbols = subprocess.check_output([str(ndkbin / "llvm-nm"), "--defined-only", str(native_hosts[0])])
    dynamic = subprocess.check_output([str(ndkbin / "llvm-readelf"), "-d", str(native_hosts[0])])
    (OUT / "host-defined-symbols.txt").write_bytes(symbols)
    (OUT / "host-dynamic.txt").write_bytes(dynamic)
    assert not any(line.split()[-1:] == [b"exr_library_open"] for line in symbols.splitlines()), "duplicate static SDK provider"
    assert b"libexreader.so" in dynamic, "actual JNI does not use shared SDK"
    for prefix, tag in ((sdk, "sdk"), (native, "admission-native"), (admission, "admission-sdk")):
        rows = [dict(path=str(p.relative_to(prefix)), bytes=p.stat().st_size,
                     sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(prefix.rglob("*")) if p.is_file()]
        (OUT / (tag + "-installed.json")).write_text(json.dumps(rows, indent=2) + "\n")
    (OUT / "build-receipt.json").write_text(json.dumps(dict(source=os.environ["GITHUB_SHA"],
        run=os.environ["GITHUB_RUN_ID"], attempt=os.environ["GITHUB_RUN_ATTEMPT"], frozen_sdk="8357eafa28423a7ab93ba08b823af80f01ad1505",
        sdk_version="3.42.0", actual_android_host=True, actual_migration=False), indent=2) + "\n")
if __name__ == "__main__": main()
