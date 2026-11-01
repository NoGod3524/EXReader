#!/usr/bin/env python3
"""Prepare/run F04 test adapters in Actions. Never edit the retained source files.

Existing original drivers remain immutable. The generated copies preserve every
original check and add record exchange probes; all substitutions fail closed.
This module does not dispatch a workflow or spend a CI authorization.
"""
import argparse, json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / "build/f04-driver"
BASE = "94fb236a4a2da87dfbaf4f1dd2a47885d615a230"

def replace_once(source, before, after):
    assert source.count(before) == 1, ("adapter source drift", before)
    return source.replace(before, after, 1)

def retained(path):
    old = subprocess.check_output(["git", "show", BASE + ":" + path], cwd=ROOT)
    actual = (ROOT / path).read_bytes()
    assert old == actual, "retained original driver changed: " + path
    return actual.decode("utf-8")

def stage_apple(target='iphone', generic=False):
    source = retained("tests/apple_android_relay/apple/run.py")
    source = replace_once(source, "ROOT = Path(__file__).resolve().parents[3]", "ROOT = Path(" + repr(str(ROOT)) + ")")
    source = replace_once(source, "sys.path.insert(0, str(ROOT / 'tests/apple_android_relay'))",
                          "sys.path.insert(0, " + repr(str(HERE)) + ")")
    source = replace_once(source, "('position', 'uploaded')",
                          "('position', 'uploaded', 'created-records', 'incoming-bookmark', 'incoming-note', 'edited-records')")
    source = replace_once(source, "from relay import start, save",
                          "from relay import start, save, untrust_desktop, finish_cleanup")
    before = """    finally:
        if controller: controller.shutdown(); controller.server_close()
        if dav:
            (out / 'requests.json').write_text(json.dumps(dav.requests, indent=2))
            dav.server.shutdown(); dav.server.server_close()
        (out / 'result.json').write_text(json.dumps(data, indent=2))"""
    after = """    finally:
        actions = []
        if controller:
            actions.extend([('stop-controller', controller.shutdown), ('close-controller', controller.server_close)])
        if dav:
            actions.extend([
                ('save-requests', lambda: (out / 'requests.json').write_text(json.dumps(dav.requests, indent=2))),
                ('stop-fixture', dav.server.shutdown), ('close-fixture', dav.server.server_close)])
            if getattr(dav, 'fixture_trust', None):
                actions.append(('remove-fixture-trust', lambda: untrust_desktop(dav.fixture_trust)))
        actions.append(('remove-fixture-key', lambda: (out / 'key.pem').unlink(missing_ok=True)))
        finish_cleanup(actions, data, out / 'result.json')"""
    source = replace_once(source, before, after)
    source = replace_once(source, "ROOT / 'tests/apple_android_relay/apple/RelayUITests.swift'",
                          "ROOT / 'tests/dot_f04_reading_sync_20261031/apple_driver.swift'")
    source = replace_once(source, "identity = json.loads((sdk / 'wave3-packages.json').read_text())",
        "identity = json.loads((sdk / 'wave3-packages.json').read_text())\n"
        "        assert identity['sdk_version'] == '3.42.0'\n"
        "        data['sdk_version'] = identity['sdk_version']\n"
        "        data['f04_stage'] = 'iphone-android-reading-v1'")
    source = replace_once(source, "        data['passed'] = True",
        "        (out / 'program.bin').write_bytes(binary.read_bytes())\n"
        "        required = ('created-records',) if args.phase == 'apple-first' else ('incoming-bookmark', 'incoming-note')\n"
        "        assert all(name in checkpoints for name in required)\n"
        "        data['f04_checkpoints'] = {name: checkpoints[name] for name in required}\n"
        "        data['passed'] = True")
    source = replace_once(source, "'__PHASE__': args.phase, '__TOKEN__': token,",
        "'__PHASE__': args.phase, '__TOKEN__': token,\n"
        "                         '__INCOMING_PREFIX__': getattr(args, 'incoming_prefix', 'F04_ANDROID'),\n"
        "                         '__OUTGOING_PREFIX__': 'F04_" + target.upper() + "',")
    if target == "iphone" and not generic:
        source = source.replace("'F04_IPHONE'", "'F04_APPLE'")
        return source
    source = replace_once(source, "choices=['apple-first', 'apple-return']",
                          "choices=['" + target + "-peer']")
    source = replace_once(source, "    args = p.parse_args()",
        "    p.add_argument('--incoming-prefix', default='F04_WINDOWS')\n    args = p.parse_args()")
    source = replace_once(source, "'platform': 'iPhone Simulator'",
        "'platform': " + repr({"iphone": "iphone-simulator", "ipad": "ipad-simulator", "macos": "macos"}[target]))
    source = source.replace("data['f04_stage'] = 'iphone-android-reading-v1'",
                            "data['f04_stage'] = 'six-host-reading-preparation-v2'")
    source = replace_once(source, "from relay import start, save, untrust_desktop, finish_cleanup",
                          "from relay import start, save, untrust_desktop, finish_cleanup, input_metadata, retained_rows")
    source = replace_once(source, "                    checkpoints[name] = payload",
        "                    payload['retained_records'] = retained_rows(root / 'accounts' / matching[0]['id'] / 'reader-catalog.db')\n"
        "                    checkpoints[name] = payload")
    source = replace_once(source, "            previous = json.loads(args.previous.read_text())['data']",
        "            previous = input_metadata(json.loads(args.previous.read_text()))")
    source = replace_once(source, "        data['passed'] = True",
        "        assert 'edited-records' in checkpoints and 'uploaded' in checkpoints\n"
        "        data['f04_checkpoints'].update({k: checkpoints[k] for k in ('edited-records', 'uploaded', 'position')})\n"
        "        data['passed'] = True")
    if target == "ipad":
        source = replace_once(source, "d['name'].startswith('iPhone')", "d['name'].startswith('iPad')")
    if target == "macos":
        source = replace_once(source, "team24-apple-sdk-iphonesimulator-*", "team24-apple-sdk-macos-*")
        begin = source.index("        devices = json.loads(")
        finish = source.index("        checkpoints = {}", begin)
        source = source[:begin] + (
            "        data['device'] = {'name': 'macOS runner', 'physical_device': False}\n"
            "        dav, user, password = start(out, previous=args.previous)\n") + source[finish:]
        begin = source.index("                    container = Path(")
        finish = source.index("                    profiles =", begin)
        source = source[:begin] + (
            "                    root = Path.home() / 'Library/Application Support/EXReader'\n") + source[finish:]
        source = replace_once(source, "CODE_SIGNING_ALLOWED=NO", "CODE_SIGNING_ALLOWED=YES")
        source = replace_once(source, "'-scheme', 'EXReaderHost-iOS'", "'-scheme', 'EXReaderHost-macOS'")
        source = replace_once(source, "'platform=iOS Simulator,id=' + udid", "'platform=macOS'")
        source = replace_once(source, "'derived/Build/Products/Debug-iphonesimulator/EXReaderHost.app'",
                              "'derived/Build/Products/Debug/EXReaderHost.app'")
        source = replace_once(source, "(app / 'Info.plist')", "(app / 'Contents/Info.plist')")
        source = replace_once(source, "binary = app / 'EXReaderHost'", "binary = app / 'Contents/MacOS/EXReaderHost'")
    return source

def stage_android(generic=False):
    source = retained("tests/apple_android_relay/android/run.py")
    source = replace_once(source, "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))",
                          "sys.path.insert(0, " + repr(str(HERE)) + ")")
    source = replace_once(source, "package + '.RelayAndroidTest'", "package + '.F04AndroidTest'")
    # MainActivity is singleTask: install ActivityMonitor before its first
    # launch, otherwise onNewIntent need not deliver an Activity to the monitor.
    # Only the test-input directory is prepared here; no app database is seeded.
    source = replace_once(source,
        "adb('shell', 'am', 'start', '-W', '-n', package + '/.MainActivity')",
        "adb('shell', 'run-as', package, 'mkdir', '-p', 'files')")
    source = replace_once(source, "'apple_progress_public_parse_real_jump', 'real_forward_pages_and_application_save',",
        "'apple_progress_public_parse_real_jump', 'peer_bookmark_and_annotation_originals_resolve',\n"
        "            'real_forward_pages_and_application_save', 'create_return_bookmark_and_annotation',")
    source = replace_once(source, "        report['checks'] = expected",
        "        report['f04_checks'] = ['peer_bookmark_and_annotation_originals_resolve', 'create_return_bookmark_and_annotation']\n"
        "        report['checks'] = [name for name in expected if name not in report['f04_checks']]\n"
        "        report['f04_stage'] = 'iphone-android-reading-v1'\n"
        "        report['sdk_version'] = '3.42.0'")
    source = replace_once(source, "        assert report['passed'] is True, report",
        "        save('program.bin', installed_apk)\n        assert report['passed'] is True, report")
    if generic:
        source = replace_once(source, "relay.load(args.previous, 'apple-first')", "relay.load(args.previous)")
        source = replace_once(source, "    args = parser.parse_args()",
            "    parser.add_argument('--incoming-prefix', default='F04_WINDOWS')\n    args = parser.parse_args()")
        before = "        payload = {key: previous['data'][key] for key in\n            ('original_sha256', 'original_bytes', 'book_identity', 'location', 'remote_title')}"
        source = replace_once(source, before,
            "        payload = relay.input_metadata(previous)\n        payload['incoming_prefix'] = args.incoming_prefix")
        source = source.replace("report['f04_stage'] = 'iphone-android-reading-v1'",
                                "report['f04_stage'] = 'six-host-reading-preparation-v2'\n"
                                "        report['platform'] = 'android-api34-x86_64'")
    return source

def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    generated = OUT / "android/org/exreader/host"
    generated.mkdir(parents=True, exist_ok=True)
    (generated / "F04AndroidTest.java").write_text((HERE / "android_driver.java").read_text())
    init = retained("tests/apple_android_relay/android/init.gradle")
    init = replace_once(init, "../../tests/apple_android_relay/android/java", "../../build/f04-driver/android")
    (OUT / "init.gradle").write_text(init)
    (OUT / "apple.py").write_text(stage_apple())
    (OUT / "android.py").write_text(stage_android())
    (OUT / "android-peer.py").write_text(stage_android(generic=True))
    for target in ("iphone", "ipad", "macos"):
        (OUT / (target + "-peer.py")).write_text(stage_apple(target, generic=True))
    print(json.dumps({"prepared": True, "runtime_accepted": False, "F04_accepted": False,
        "android_init": "build/f04-driver/init.gradle",
        "instrumentation": "org.exreader.host.F04AndroidTest"}), flush=True)

def prepare_hash_owner(platform):
    """Install the mandatory public hash dependency for this exact target."""
    assert platform in ("windows", "gtk", "android")
    retained("extras/opds/CMakeLists.txt")
    prefix = ROOT / ("build/f04-hash-" + platform + "/prefix")
    prefix.mkdir(parents=True, exist_ok=True)
    canonical = prefix.resolve().as_posix()
    previous = os.environ.get("EXREADER_ORIGINAL_HASH_PREFIX")
    assert previous in (None, "", canonical), "foreign original hash owner prefix"
    binary = prefix.parent / "build"
    args = ["cmake", "-S", str(ROOT / "extras/opds"), "-B", str(binary), "-G", "Ninja",
            "-DCMAKE_BUILD_TYPE=Release", "-DEXREADER_OPDS_HASH_ONLY=ON",
            "-DCMAKE_POSITION_INDEPENDENT_CODE=ON", "-DCMAKE_INSTALL_PREFIX=" + canonical]
    if platform == "android":
        sdk = Path(os.environ["ANDROID_HOME"])
        ndk = os.environ.get("C11_NDK", "27.0.12077973")
        toolchain = sdk / "ndk" / ndk / "build/cmake/android.toolchain.cmake"
        assert toolchain.is_file(), "install approved Android NDK before target hash build"
        args += ["-DCMAKE_TOOLCHAIN_FILE=" + toolchain.as_posix(), "-DANDROID_ABI=x86_64",
                 "-DANDROID_PLATFORM=android-26", "-DANDROID_STL=c++_static"]
    subprocess.run(args, cwd=ROOT, check=True)
    subprocess.run(["cmake", "--build", str(binary), "--parallel", "4"], cwd=ROOT, check=True)
    subprocess.run(["cmake", "--install", str(binary)], cwd=ROOT, check=True)
    assert (prefix / "lib/cmake/EXReaderOPDSHash/EXReaderOPDSHashConfig.cmake").is_file()
    # Installed ProductCatalog consumers also need this selector, not just store/native.
    os.environ["EXREADER_ORIGINAL_HASH_PREFIX"] = canonical
    return canonical

def build_producer(platform):
    """Actions-only recipe, still unreachable from the disabled workflow."""
    import hashlib
    # The historical package guards pin unrelated old branch path sets.
    # This package's exact twelve-file + frozen-SDK admission is mandatory;
    # build functions themselves and all their original assertions stay intact.
    subprocess.run([sys.executable, str(HERE / "admission.py")], cwd=ROOT, check=True)
    recipes = {
        "windows": ("tests/windows_sdk342/build.py", []),
        "gtk": ("tests/gtk_sdk342_package/run.py", ["build"]),
        "android": ("tests/android_sdk342_package/run.py", ["build"]),
        "macos": ("tests/apple_sdk342_host/build.py", ["--target", "macos"]),
        "iphonesimulator": ("tests/apple_sdk342_host/build.py", ["--target", "iphonesimulator"]),
    }
    path, arguments = recipes[platform]
    hash_prefix = prepare_hash_owner(platform) if platform in ("windows", "gtk", "android") else None
    original_recipe = retained(path)
    if platform == "android":
        (ROOT / "build/f06").mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(ROOT / path), *arguments], cwd=ROOT, check=True)
    evidence = {"source_sha": os.environ["GITHUB_SHA"],
        "run_id": os.environ["GITHUB_RUN_ID"], "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "platform": platform, "sdk_source": "8357eafa28423a7ab93ba08b823af80f01ad1505",
        "sdk_version": "3.42.0", "recipe": path,
        "recipe_sha256": hashlib.sha256(original_recipe.encode()).hexdigest(),
        "host_runtime_accepted": False, "F04_accepted": False, "original_hash_prefix": hash_prefix}
    if platform == "android":
        import yaml
        workflow = retained(".github/workflows/reader-apple-android-relay.yml")
        steps = yaml.safe_load(workflow)["jobs"]["android"]["steps"]
        selected = [s for s in steps if s.get("name") == "Build real cross-platform relay instrumentation"]
        assert len(selected) == 1
        body = selected[0]["run"]
        body = replace_once(body, "$PWD/tests/apple_android_relay/android/init.gradle",
                            "$PWD/build/f04-driver/init.gradle")
        body = replace_once(body, "org.exreader.host.RelayAndroidTest", "org.exreader.host.F04AndroidTest")
        body = replace_once(body, "-PexrSdk=", "-PexrSdkVersion=3.42.0 -PexrSdk=")
        script = OUT / "android-instrumentation.sh"
        script.write_text(body)
        subprocess.run(["bash", "-e", "-o", "pipefail", str(script)], cwd=ROOT, check=True)
        # An instrumentation-only rebuild must not silently substitute the host APK.
        original_apk = ROOT / "build/wave3/artifacts/app-debug.apk"
        built_apk = ROOT / "examples/android/app/build/outputs/apk/debug/app-debug.apk"
        assert original_apk.read_bytes() == built_apk.read_bytes()
        evidence["instrumentation_recipe_sha256"] = hashlib.sha256(body.encode()).hexdigest()
    candidates = {
        "windows": ROOT / "build/windows-sdk342/package/EXReader/EXReader.exe",
        "gtk": ROOT / "build/gtk-raw-wave3/retained-package/EXReader-Linux/bin/exreader-linux",
        "android": ROOT / "build/wave3/artifacts/app-debug.apk",
    }
    if platform in candidates:
        binary = candidates[platform]
        evidence["program"] = {"path": binary.relative_to(ROOT).as_posix(),
            "bytes": binary.stat().st_size, "sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}
    else:
        identity = ROOT / ("build/raw3-ios-sdk/" + platform + "/sdk342-installed-identity.json")
        installed = json.loads(identity.read_text())
        assert installed["source_sha"] == evidence["source_sha"]
        assert installed["sdk_version"] == "3.42.0"
        evidence["installed_identity_sha256"] = hashlib.sha256(identity.read_bytes()).hexdigest()
        evidence["program"] = None  # Real host is built by the later UI producer, not this SDK step.
    (OUT / ("build-" + platform + ".json")).write_text(json.dumps(evidence, indent=2) + "\n")

def main():
    assert os.environ.get("GITHUB_ACTIONS") == "true", "Actions only"
    assert Path.cwd().resolve() == ROOT
    assert os.environ.get("EXR_APPLE_SDK_VERSION") == "3.42.0"
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "apple", "android", "android-peer", "iphone-peer", "ipad-peer", "macos-peer", "windows", "gtk", "build-windows", "build-gtk", "build-android", "build-macos", "build-iphonesimulator"))
    args, rest = parser.parse_known_args()
    prepare()
    if args.action.startswith("build-"):
        assert not rest, rest
        build_producer(args.action.removeprefix("build-"))
        return
    if args.action != "prepare":
        driver = HERE / (args.action + "_driver.py") if args.action in ("windows", "gtk") else OUT / (args.action + ".py")
        completed = subprocess.run([sys.executable, str(driver), *rest], cwd=ROOT)
        raise SystemExit(completed.returncode)
if __name__ == "__main__":
    main()
