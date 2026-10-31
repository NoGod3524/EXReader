#!/usr/bin/env python3
"""Actions-only immutable source admission; no product edits or evidence promotion."""
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
    assert set(changed) == set(contract["authorized_paths"]), (changed, "exact authorized twelve-file ownership")
    sdk_paths = ("src", "include", "cmake", "CMakeLists.txt", "bindings")
    assert not git("diff", "--name-only", contract["sdk_source"], source, "--", *sdk_paths)
    assert not git("status", "--porcelain", "--", *sdk_paths)
    for path in ("tests/apple_android_relay", "tests/reader_android_record_interop",
                 "tests/apple_sdk342_host", "tests/apple_host/reading",
                 "tests/reader_android_reading", "apps", "examples", "extras"):
        assert not git("diff", "--name-only", contract["base_source"], source, "--", path), path
    result = {"source_sha": source, "base_source": contract["base_source"],
              "sdk_source": contract["sdk_source"], "sdk_version": contract["sdk_version"],
              "run_id": os.environ["GITHUB_RUN_ID"], "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
              "admission": True, "runtime_accepted": False, "F04_accepted": False}
    print(json.dumps(result), flush=True)
if __name__ == "__main__":
    main()
