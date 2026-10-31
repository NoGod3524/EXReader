#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only actual Android host build with installed native C02 admission."""
import hashlib, json, os, pathlib, re, shutil, subprocess, sys, zipfile

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
    formal = ROOT / "build/android-c02-formal-package"
    # Exercise the ordinary product entry point before enabling process actors.
    run([sys.executable, "tools/build_android_host.py", "--stage", sdk,
         "--sdk-build", ROOT / "build/android-c02-sdk", "--build-dir", formal, "--gradle", "gradle"])
    product = ROOT / "stage/android-product"
    admission = sdk
    native = sdk
    os.environ["EXREADER_ORIGINAL_HASH_PREFIX"] = str(product / "original-hash")
    formal_evidence = OUT / "formal-package"
    formal_evidence.mkdir()
    shutil.copyfile(formal / "build.json", formal_evidence / "build.json")
    shutil.copyfile(formal / "artifacts/app-debug.apk", formal_evidence / "app-debug.apk")
    metadata = json.loads((formal / "build.json").read_text())
    assert metadata["sdk_version"] == "3.42.0" and metadata["c02_admission"]["profile"] == "c02"
    assert metadata["c02_admission"]["source"] == os.environ["GITHUB_SHA"]
    android = ROOT / "examples/android"
    run(["gradle", "-p", android, "--no-daemon", "--stacktrace", ":app:assembleRelease",
         "-PexrSdk=" + str(sdk), "-PexrSdkVersion=3.42.0", "-PexrProduct=" + str(product),
         "-PexrC02Prefix=" + str(admission)])
    shutil.copyfile(android / "app/build/outputs/apk/release/app-release-unsigned.apk",
                    formal_evidence / "app-release-unsigned.apk")
    run(["gradle", "-p", android, "--no-daemon", "--stacktrace", ":app:assembleDebug", ":app:assembleDebugAndroidTest",
         "-PexrSdk=" + str(sdk), "-PexrSdkVersion=3.42.0", "-PexrC02Prefix=" + str(admission),
         "-PexrProduct=" + str(product), "-PexrC02Test=true", "-PexrTestRunner=org.exreader.host.C02HostTest"])
    app = android / "app/build/outputs/apk/debug/app-debug.apk"
    test = android / "app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
    for source in (app, test): shutil.copyfile(source, OUT / source.name)
    # ELF/provider inspection remains on Actions. Native host must call the same
    # shared SDK; the installed admission archives must not define SDK symbols.
    ndkbin = host.ndk_home() / "toolchains/llvm/prebuilt/linux-x86_64/bin"
    packaged = OUT / "libexreader_host.packaged.so"
    sdk_installed = OUT / "sdk-libexreader.installed.so"
    sdk_packaged = OUT / "sdk-libexreader.packaged.so"
    shutil.copyfile(sdk / "lib/libexreader.so", sdk_installed)
    with zipfile.ZipFile(app) as archive:
        packaged.write_bytes(archive.read("lib/x86_64/libexreader_host.so"))
        sdk_packaged.write_bytes(archive.read("lib/x86_64/libexreader.so"))
    strip_matches = []
    if sdk_installed.read_bytes() == sdk_packaged.read_bytes():
        strip_matches.append("identical")
    for flag, label in [("--strip-unneeded", "unneeded"), ("--strip-debug", "debug")]:
        predicted = OUT / ("sdk-libexreader.strip-" + label + ".so")
        run([ndkbin / "llvm-strip", flag, "-o", predicted, sdk_installed])
        if predicted.read_bytes() == sdk_packaged.read_bytes(): strip_matches.append(flag)
    (OUT / "sdk-byte-binding.json").write_text(json.dumps(dict(installed="sdk-libexreader.installed.so",
        packaged="sdk-libexreader.packaged.so", apk="app-debug.apk", apk_entry="lib/x86_64/libexreader.so",
        installed_sha256=hashlib.sha256(sdk_installed.read_bytes()).hexdigest(),
        packaged_sha256=hashlib.sha256(sdk_packaged.read_bytes()).hexdigest(),
        ndk="27.0.12077973", matching_official_strip=strip_matches), indent=2) + "\n")
    assert strip_matches, "Packaged SDK differs from installed SDK and the official NDK strip transforms"
    def build_id(path):
        notes = subprocess.check_output([str(ndkbin / "llvm-readelf"), "-n", str(path)], text=True)
        match = re.search(r"Build ID:\s*([0-9a-f]+)", notes)
        assert match, path
        return match.group(1)
    actual_build_id = build_id(packaged)
    native_hosts = [path for path in (android / "app/build/intermediates/cxx/Debug").rglob("libexreader_host.so")
                    if build_id(path) == actual_build_id]
    assert len(native_hosts) == 1, native_hosts
    shutil.copyfile(native_hosts[0], OUT / "libexreader_host.so")
    symbols = subprocess.check_output([str(ndkbin / "llvm-nm"), "--defined-only", str(native_hosts[0])])
    dynamic = subprocess.check_output([str(ndkbin / "llvm-readelf"), "-d", str(packaged)])
    (OUT / "native-provider.json").write_text(json.dumps(dict(build_id=actual_build_id,
        packaged_sha256=hashlib.sha256(packaged.read_bytes()).hexdigest(),
        unstripped_sha256=hashlib.sha256(native_hosts[0].read_bytes()).hexdigest()), indent=2) + "\n")
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
