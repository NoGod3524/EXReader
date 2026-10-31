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

def stage_apple():
    source = retained("tests/apple_android_relay/apple/run.py")
    source = replace_once(source, "ROOT = Path(__file__).resolve().parents[3]", "ROOT = Path(" + repr(str(ROOT)) + ")")
    source = replace_once(source, "sys.path.insert(0, str(ROOT / 'tests/apple_android_relay'))",
                          "sys.path.insert(0, " + repr(str(HERE)) + ")")
    source = replace_once(source, "('position', 'uploaded')",
                          "('position', 'uploaded', 'created-records', 'incoming-bookmark', 'incoming-note')")
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
    return source

def stage_android():
    source = retained("tests/apple_android_relay/android/run.py")
    source = replace_once(source, "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))",
                          "sys.path.insert(0, " + repr(str(HERE)) + ")")
    source = replace_once(source, "package + '.RelayAndroidTest'", "package + '.F04AndroidTest'")
    source = replace_once(source, "'apple_progress_public_parse_real_jump', 'real_forward_pages_and_application_save',",
        "'apple_progress_public_parse_real_jump', 'peer_bookmark_and_annotation_originals_resolve',\n"
        "            'real_forward_pages_and_application_save', 'create_return_bookmark_and_annotation',")
    source = replace_once(source, "        report['checks'] = expected",
        "        report['f04_checks'] = ['peer_bookmark_and_annotation_originals_resolve', 'create_return_bookmark_and_annotation']\n"
        "        report['checks'] = [name for name in expected if name not in report['f04_checks']]\n"
        "        report['f04_stage'] = 'iphone-android-reading-v1'\n"
        "        report['sdk_version'] = '3.42.0'")
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
    print(json.dumps({"prepared": True, "runtime_accepted": False, "F04_accepted": False,
        "android_init": "build/f04-driver/init.gradle",
        "instrumentation": "org.exreader.host.F04AndroidTest"}), flush=True)

def main():
    assert os.environ.get("GITHUB_ACTIONS") == "true", "Actions only"
    assert Path.cwd().resolve() == ROOT
    assert os.environ.get("EXR_APPLE_SDK_VERSION") == "3.42.0"
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "apple", "android"))
    args, rest = parser.parse_known_args()
    prepare()
    if args.action != "prepare":
        completed = subprocess.run([sys.executable, str(OUT / (args.action + ".py")), *rest], cwd=ROOT)
        raise SystemExit(completed.returncode)
if __name__ == "__main__":
    main()
