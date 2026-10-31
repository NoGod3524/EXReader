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
    source = replace_once(source, "ROOT / 'tests/apple_android_relay/apple/RelayUITests.swift'",
                          "ROOT / 'tests/dot_f04_reading_sync_20261031/apple_driver.swift'")
    source = replace_once(source, "identity = json.loads((sdk / 'wave3-packages.json').read_text())",
        "identity = json.loads((sdk / 'wave3-packages.json').read_text())\n"
        "        assert identity['sdk_version'] == '3.42.0'\n"
        "        data['sdk_version'] = identity['sdk_version']\n"
        "        data['f04_stage'] = 'iphone-android-reading-v1'")
    source = replace_once(source, "        data['passed'] = True",
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
    source = replace_once(source, "from relay import start, save",
                          "from relay import start, save, input_metadata, retained_rows")
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

def main():
    assert os.environ.get("GITHUB_ACTIONS") == "true", "Actions only"
    assert Path.cwd().resolve() == ROOT
    assert os.environ.get("EXR_APPLE_SDK_VERSION") == "3.42.0"
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "apple", "android", "android-peer", "iphone-peer", "ipad-peer", "macos-peer", "windows", "gtk"))
    args, rest = parser.parse_known_args()
    prepare()
    if args.action != "prepare":
        driver = HERE / (args.action + "_driver.py") if args.action in ("windows", "gtk") else OUT / (args.action + ".py")
        completed = subprocess.run([sys.executable, str(driver), *rest], cwd=ROOT)
        raise SystemExit(completed.returncode)
if __name__ == "__main__":
    main()
