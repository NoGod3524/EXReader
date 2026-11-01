#!/usr/bin/env python3
"""Actions-only immutable source admission; only three approved parser spelling branches; no evidence promotion."""
import json, os, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
def main():
    assert os.environ.get("GITHUB_ACTIONS") == "true", "Actions only"
    contract = json.loads((HERE / "contract.json").read_text())
    source = git("rev-parse", "HEAD")
    assert source == os.environ["GITHUB_SHA"]
    assert git("merge-base", contract["base_source"], source) == contract["base_source"]
    changed = git("diff", "--name-only", contract["base_source"], source).splitlines()
    if os.environ.get("GITHUB_REF") == "refs/heads/" + contract["canonical"]["branch"]:
        assert os.environ.get("F04_SCOPE") in ("f04/windows-android", "f04/six-host"), "approved fixed case"
        assert os.environ.get("F04_CONTROLLER_SHA") == source, "controller/source mismatch"
        assert set(changed) == set(contract["canonical"]["union_paths"]), (changed, "exact approved twenty-six-path union")
    else:
        assert set(changed) == set(contract["authorized_paths"]), (changed, "exact fifteen-file preparation ownership")
        assert os.environ.get("F04_SCOPE") is None, "execution requires canonical branch"
    sdk_paths = ("src", "include", "cmake", "CMakeLists.txt", "bindings")
    assert not git("diff", "--name-only", contract["sdk_source"], source, "--", *sdk_paths)
    assert not git("status", "--porcelain", "--", *sdk_paths)
    for path in ("tests/apple_android_relay", "tests/reader_android_record_interop",
                 "tests/apple_sdk342_host", "tests/apple_host/reading",
                 "tests/reader_android_reading", "tests/windows_sdk342", "tests/gtk_sdk342_package",
                 "tests/android_sdk342_package", "tests/reader_windows_records", "tests/reader_windows_account",
                 "tests/reader_gtk_reading_records", "tests/linux_host", "tools",
                 "extras", "tests/apple_host/record_compatibility"):
        assert not git("diff", "--name-only", contract["base_source"], source, "--", path), path
    production = {
        "examples/android/app/src/main/java/org/exreader/host/ReadingParserPolicy.java": (
            '        if (recorded.equals("exreader-sdk-" + actual)) return true;',
            '        if (actual.equals("3.42.0") && recorded.equals("3.42.0")) return true;'),
        "apps/reader/desktop/windows_records_owner.cpp": (
            ' if(!std::strcmp(recorded,exr_version()))return true;',
            ' if(!std::strcmp(exr_version(),"3.42.0")&&!std::strcmp(recorded,"exreader-sdk-3.42.0"))return true;')}
    production["examples/apple/HostReadingRecords.swift"] = (
        '        if recorded == actual { return true }',
        '        if actual == "3.42.0" && recorded == "exreader-sdk-3.42.0" { return true }')
    assert set(git("diff", "--name-only", contract["base_source"], source, "--", "apps", "examples").splitlines()) == set(production)
    for path, (anchor, added) in production.items():
        original = subprocess.check_output(["git", "show", contract["base_source"] + ":" + path], cwd=ROOT)
        assert original.count(anchor.encode()) == 1
        expected = original.replace(anchor.encode(), (anchor + "\n" + added).encode(), 1)
        assert (ROOT / path).read_bytes() == expected, "production delta exceeds parser function: " + path
    result = {"source_sha": source, "base_source": contract["base_source"],
              "sdk_source": contract["sdk_source"], "sdk_version": contract["sdk_version"],
              "run_id": os.environ["GITHUB_RUN_ID"], "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
              "admission": True, "runtime_accepted": False, "F04_accepted": False}
    print(json.dumps(result), flush=True)
if __name__ == "__main__":
    main()
