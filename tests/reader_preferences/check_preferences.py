#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only acceptance checker for the installed EXReaderPreferences package."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from preferences_fixtures import DEFAULTS, document

COMMON_START = "c3511a011eefbf1fba1d20908f000cef22b1ced2"
MAX_FILE = 65536
cases = []


class CheckFailure(RuntimeError):
    pass


def record(name, function):
    try:
        function()
        cases.append({"name": name, "ok": True, "detail": ""})
        print("PASS", name, flush=True)
    except Exception as error:  # noqa: BLE001 - every failure is evidence
        cases.append({"name": name, "ok": False, "detail": str(error)[:800]})
        print("FAIL", name, str(error)[:800], flush=True)


def run(command, code=0, timeout=180):
    process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=timeout)
    if code is not None and process.returncode != code:
        raise CheckFailure("rc=%d expected %d: %s %s" % (
            process.returncode, code, process.stdout[-400:], process.stderr[-400:]))
    return process


def kv(process):
    values = {}
    for line in process.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def load_ok(path):
    return kv(run([WORKER, "load", str(path)], 0))


def load_refusal(path, expected):
    process = run([WORKER, "load", str(path)], None)
    status = kv(process).get("status", "")
    if process.returncode == 0 or status != expected:
        raise CheckFailure("expected %s, got rc=%d status=%r" % (expected, process.returncode, status))
    return process


def hash_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def temp_files(directory):
    return sorted(p.name for p in Path(directory).iterdir()
                  if ".tmp-" in p.name or ".reader-preferences.tmp-" in p.name)


def start_paused(path, preset, flag, ready, directory):
    ready_path = Path(directory) / ready
    if ready_path.exists():
        ready_path.unlink()
    process = subprocess.Popen([WORKER, "save", str(path), preset, flag, str(ready_path)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               encoding="utf-8", errors="replace")
    deadline = time.time() + 30
    while not ready_path.exists():
        if process.poll() is not None:
            out, err = process.communicate()
            raise CheckFailure("paused save exited early rc=%d %s %s" % (process.returncode, out, err))
        if time.time() > deadline:
            process.kill()
            process.wait()
            raise CheckFailure("ready marker did not appear")
        time.sleep(0.05)
    time.sleep(0.25)
    process.kill()
    process.wait(timeout=30)
    return ready_path


def main():
    global WORKER
    parser = argparse.ArgumentParser()
    parser.add_argument("--consumer", required=True)
    parser.add_argument("--cpp", required=True)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--installed", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--platform", default="")
    arguments = parser.parse_args()
    WORKER = str(Path(arguments.worker).resolve())
    fixtures = Path(arguments.fixtures).resolve()
    installed = Path(arguments.installed).resolve()
    output = Path(arguments.output).resolve()
    work = output / "work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    platform = arguments.platform or ("Windows" if os.name == "nt" else sys.platform)

    def defaults_check():
        values = kv(run([WORKER, "defaults"], 0))
        expected = {
            "font_size": "24", "line_spacing": "1.6", "paragraph_spacing": "12",
            "margin": "48", "theme": "1", "page_turn_direction": "1",
            "page_turn_input": "1", "fixed_page_zoom": "100",
            "light_foreground": "#1A1A1AFF", "light_background": "#FFFFFFFF",
            "dark_foreground": "#E6E6E6FF", "dark_background": "#101010FF",
        }
        for key, value in expected.items():
            if values.get(key) != value:
                raise CheckFailure("%s=%r expected %r" % (key, values.get(key), value))

    def c_consumer():
        process = run([arguments.consumer, str(work)], 0)
        if "c-consumer-ok" not in process.stdout:
            raise CheckFailure(process.stdout + process.stderr)

    def cpp_consumer():
        process = run([arguments.cpp, str(work / "cpp.json")], 0)
        if "cpp-consumer-ok" not in process.stdout:
            raise CheckFailure(process.stdout + process.stderr)

    def unicode_roundtrip():
        directory = work / "偏好设置-📚"
        directory.mkdir()
        path = directory / "阅读 设置.json"
        run([WORKER, "save", str(path), "custom"], 0)
        first = load_ok(path)
        run([WORKER, "save", str(path), "custom"], 0)
        second = load_ok(path)
        if first != second or first.get("theme") != "3" or first.get("fixed_page_zoom") != "175":
            raise CheckFailure("unicode roundtrip differs: %r %r" % (first, second))

    def boundaries():
        fields = [
            ("font_size", 4, 256, "3.999", "256.001"),
            ("line_spacing", 1, 5, "0.999", "5.001"),
            ("paragraph_spacing", 0, 1024, "-0.001", "1024.001"),
            ("margin", 0, 1024, "-0.001", "1024.001"),
            ("fixed_page_zoom", 25, 400, "24", "401"),
        ]
        for field, minimum, maximum, low, high in fields:
            for value in (minimum, maximum):
                path = work / ("boundary-%s-%s.json" % (field, value))
                path.write_text(document(**{field: value}), encoding="utf-8")
                values = load_ok(path)
                if values.get(field) != (str(value) if field == "fixed_page_zoom" else format(float(value), ".9g")):
                    raise CheckFailure("%s=%s not read back: %r" % (field, value, values.get(field)))
            for value in (low, high):
                path = work / ("boundary-bad-%s-%s.json" % (field, value.replace("-", "m").replace(".", "_")))
                numeric = int(value) if field == "fixed_page_zoom" else float(value)
                path.write_text(document(**{field: numeric}), encoding="utf-8")
                load_refusal(path, "RANGE")

    def refusals():
        expected = {
            "unknown-version.json": "VERSION",
            "nan.json": "FORMAT",
            "infinity.json": "FORMAT",
            "huge-exponent.json": "RANGE",
            "bad-enum.json": "FORMAT",
            "bad-direction.json": "FORMAT",
            "bad-input.json": "FORMAT",
            "bad-color.json": "FORMAT",
            "bad-format.json": "FORMAT",
            "zoom-fraction.json": "FORMAT",
            "wrong-type.json": "FORMAT",
            "missing.json": "FORMAT",
            "trailing.json": "FORMAT",
            "empty.json": "FORMAT",
            "format_only.json": "FORMAT",
            "truncated.json": "FORMAT",
            "duplicate.json": "FORMAT",
            "unknown-key.json": "FORMAT",
            "nul.json": "FORMAT",
            "bad-utf8.bin": "FORMAT",
            "oversize.json": "LIMIT",
        }
        for name, status in expected.items():
            try:
                load_refusal(fixtures / name, status)
            except CheckFailure as error:
                raise CheckFailure("%s: %s" % (name, error)) from error

    def unknown_version_keeps_bytes():
        path = work / "unknown-version-copy.json"
        shutil.copyfile(fixtures / "unknown-version.json", path)
        before = path.read_bytes()
        load_refusal(path, "VERSION")
        if path.read_bytes() != before:
            raise CheckFailure("unknown version file changed")

    def failed_load_preserves():
        process = run([WORKER, "preserve", str(work / "unused.json"), "b",
                       str(fixtures / "bad-enum.json")], 0)
        if "preserved=1" not in process.stdout:
            raise CheckFailure(process.stdout + process.stderr)

    def cancelled_load():
        path = work / "cancel-load.json"
        run([WORKER, "save", str(path), "a"], 0)
        process = run([WORKER, "cancel-load", str(path)], 10)
        if "cancelled=1" not in process.stdout:
            raise CheckFailure(process.stdout + process.stderr)

    def cancelled_save():
        path = work / "cancel-save.json"
        run([WORKER, "save", str(path), "a"], 0)
        before = path.read_bytes()
        run([WORKER, "cancel-save", str(path)], 10)
        if path.read_bytes() != before:
            raise CheckFailure("cancelled save changed the file")
        if temp_files(work):
            raise CheckFailure("cancelled save left temporary files: %r" % temp_files(work))

    def atomic_failure():
        path = work / "atomic-failure.json"
        run([WORKER, "save", str(path), "a"], 0)
        before = path.read_bytes()
        run([WORKER, "save", str(path), "b", "--fail-before-rename"], 20)
        if path.read_bytes() != before:
            raise CheckFailure("failed replacement changed the file")
        if load_ok(path).get("font_size") != "12":
            raise CheckFailure("failed replacement did not keep the old value")
        if temp_files(work):
            raise CheckFailure("failed replacement left temporary files: %r" % temp_files(work))

    def kill_before_rename():
        path = work / "kill-before.json"
        run([WORKER, "save", str(path), "a"], 0)
        before = path.read_bytes()
        start_paused(path, "b", "--pause-before-rename", "ready-before.txt", work)
        if path.read_bytes() != before:
            raise CheckFailure("target changed before rename")
        if load_ok(path).get("font_size") != "12":
            raise CheckFailure("old value not readable after kill")
        for name in temp_files(work):
            (work / name).unlink()

    def kill_after_rename():
        path = work / "kill-after.json"
        run([WORKER, "save", str(path), "a"], 0)
        start_paused(path, "b", "--pause-after-rename", "ready-after.txt", work)
        values = load_ok(path)
        if values.get("font_size") != "48" or values.get("theme") != "2":
            raise CheckFailure("new value incomplete after kill: %r" % values)

    def concurrent_callers():
        path = work / "race.json"
        first = subprocess.Popen([WORKER, "race", str(path), "a", "120"], stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        second = subprocess.Popen([WORKER, "race", str(path), "b", "120"], stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        out_a, err_a = first.communicate(timeout=180)
        out_b, err_b = second.communicate(timeout=180)
        if first.returncode != 0 or second.returncode != 0:
            raise CheckFailure("race failed a=%d b=%d %s %s" % (first.returncode, second.returncode, err_a, err_b))
        values = load_ok(path)
        if values.get("font_size") not in ("12", "48"):
            raise CheckFailure("race produced a partial value: %r" % values)
        if temp_files(work):
            raise CheckFailure("race left temporary files: %r" % temp_files(work))

    def legacy_import():
        path = work / "legacy.json"
        process = run([WORKER, "import-legacy", str(path)], 0)
        values = kv(process)
        if values.get("applied") != "17" or values.get("preserved") != "4078":
            raise CheckFailure("legacy report differs: %r" % values)
        loaded = load_ok(path)
        if loaded.get("font_size") != "30" or loaded.get("theme") != "2" or loaded.get("line_spacing") != "1.2":
            raise CheckFailure("legacy values not applied: %r" % loaded)

    def installed_header():
        header = installed / "include" / "reader_preferences.h"
        if not header.is_file():
            raise CheckFailure("installed header is missing")
        if header.read_bytes() != (Path(__file__).resolve().parents[2] / "apps" / "reader" /
                                   "preferences" / "include" / "reader_preferences.h").read_bytes():
            raise CheckFailure("installed header differs from source")

    record("defaults", defaults_check)
    record("c-consumer", c_consumer)
    record("cpp-consumer", cpp_consumer)
    record("unicode-roundtrip", unicode_roundtrip)
    record("field-boundaries", boundaries)
    record("refusal-documents", refusals)
    record("unknown-version-bytes", unknown_version_keeps_bytes)
    record("failed-load-preserves", failed_load_preserves)
    record("cancelled-load", cancelled_load)
    record("cancelled-save", cancelled_save)
    record("atomic-replace-failure", atomic_failure)
    record("kill-before-rename", kill_before_rename)
    record("kill-after-rename", kill_after_rename)
    record("concurrent-callers", concurrent_callers)
    record("legacy-import", legacy_import)
    record("installed-header", installed_header)

    passed = sum(1 for case in cases if case["ok"])
    failed = len(cases) - passed
    artifacts = {}
    for relative in ("include/reader_preferences.h",):
        path = installed / relative
        if path.is_file():
            artifacts[relative] = {"bytes": path.stat().st_size, "sha256": hash_file(path)}
    result = {
        "accepted": failed == 0,
        "package": "EXReaderPreferences 0.1.0",
        "common_start": COMMON_START,
        "source_sha": os.environ.get("GITHUB_SHA", ""),
        "run_id": int(os.environ.get("GITHUB_RUN_ID", "0") or 0),
        "attempt": int(os.environ.get("GITHUB_RUN_ATTEMPT", "0") or 0),
        "platform": platform,
        "granted_platform": platform.lower(),
        "macos_accepted": platform == "macOS" and failed == 0,
        "performance_claimed": False,
        "host_ui_accepted": False,
        "six_platform_accepted": False,
        "complete_product": False,
        "sdk_changed": False,
        "schema_changed": False,
        "max_file_bytes": MAX_FILE,
        "checks": len(cases),
        "passed": passed,
        "failed": failed,
        "installed": artifacts,
        "cases": cases,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"accepted": result["accepted"], "platform": platform, "cases": len(cases)}), flush=True)
    raise SystemExit(0 if result["accepted"] else 1)


if __name__ == "__main__":
    main()
