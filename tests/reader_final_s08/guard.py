#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""S08 cloud guard: fixed base, owner identity, static log surface, red actions.

Runs only inside GitHub Actions. It proves that this branch changes nothing but
its own new paths, that the three owner modules are byte-identical to the fixed
implementation base, that the credentials module still has no logging surface,
and that the secret detector and diagnostic judge detect planted leaks.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan import selfcheck  # noqa: E402

FIXED_BASE = "0889f7d1e9a537c6c1b05456547e016b26e1cd85"
FROZEN_SDK = "9854061be331fe603a1822d9b2b36ee357154927"
OWNER_PATHS = ["extras/credentials", "apps/reader/account-profiles", "extras/opds"]
ALLOWED = re.compile(r"^(tests/reader_final_s08/|\.github/workflows/reader-final-s08\.yml$|"
                     r"docs/reader-final-s08/|HANDOFF-RESULT\.md$)")
FORBIDDEN_CREDENTIAL = re.compile(
    r"(?<![A-Za-z_])printf\s*\(|(?<![A-Za-z_])fprintf\s*\(|\bfputs\s*\(|(?<![A-Za-z_])puts\s*\(|"
    r"\bfwrite\s*\(|\bstderr\b|\bstdout\b|\bsyslog\b|\bNSLog\b|System\.(out|err)|println|"
    r"\bLog\.[dviwe]\s*\(")
FORBIDDEN_OTHER = re.compile(
    r"(?<![A-Za-z_])printf\s*\(|fprintf\s*\(\s*std(err|out)|\bstd::c(err|out)|System\.(out|err)|"
    r"println|\bsyslog\s*\(")


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    problems = []
    checks = []

    def record(identifier: str, ok: bool, detail: str) -> None:
        checks.append({"id": identifier, "ok": bool(ok), "detail": detail})
        if not ok:
            problems.append(identifier + ": " + detail)

    head = git("rev-parse", "HEAD").stdout.strip()
    record("source-matches-actions", head == os.environ.get("GITHUB_SHA", ""),
           "head=" + head[:12])
    ancestor = git("merge-base", "--is-ancestor", FIXED_BASE, "HEAD").returncode == 0
    record("fixed-base-ancestor", ancestor, "base=" + FIXED_BASE[:12])
    sdk = git("merge-base", "--is-ancestor", FROZEN_SDK, "HEAD").returncode == 0
    record("frozen-sdk-ancestor", sdk, "sdk=" + FROZEN_SDK[:12])
    # This package must not move the protected SDK trees at all. The frozen SDK
    # commit stays an ancestor; mainline history before the fixed base is not
    # this package's change, so the diff is taken from the fixed base.
    sdk_diff = git("diff", "--stat", FIXED_BASE, "HEAD", "--", "src", "include", "cmake",
                   "CMakeLists.txt", "tests/fixtures", "bindings").stdout.strip()
    record("frozen-sdk-trees-unchanged", sdk_diff == "", sdk_diff[:160] or "no change")

    changed = [line for line in git("diff", "--name-only", FIXED_BASE, "HEAD").stdout.splitlines()
               if line.strip()]
    unowned = [path for path in changed if not ALLOWED.match(path)]
    record("owned-paths-only", not unowned, ",".join(unowned)[:200] or "only new paths")

    owner_diff = git("diff", "--stat", FIXED_BASE, "HEAD", "--", *OWNER_PATHS).stdout.strip()
    record("owner-modules-identical", owner_diff == "", owner_diff[:200] or "no change")

    for path in OWNER_PATHS:
        present = Path(path).is_dir()
        record("owner-present:" + path, present, "directory")

    credential_sources = list(Path("extras/credentials/src").glob("*.c")) + \
        list(Path("extras/credentials/src").glob("*.h")) + \
        [Path("extras/credentials/include/exr_credentials.h")] + \
        list(Path("extras/credentials/android/credentials/src/main/java").rglob("*.java"))
    hits = []
    for source in credential_sources:
        text = source.read_text(encoding="utf-8", errors="replace")
        for match in FORBIDDEN_CREDENTIAL.finditer(text):
            hits.append(str(source) + ":" + match.group(0))
    record("credentials-no-log-surface", not hits, ",".join(hits)[:200] or "none")

    other_hits = []
    for base in ("apps/reader/account-profiles/src", "extras/opds/src"):
        for source in Path(base).rglob("*"):
            if source.suffix not in (".c", ".h"):
                continue
            text = source.read_text(encoding="utf-8", errors="replace")
            for match in FORBIDDEN_OTHER.finditer(text):
                other_hits.append(str(source) + ":" + match.group(0))
    record("account-and-opds-no-console-surface", not other_hits, ",".join(other_hits)[:200] or "none")

    header = Path("extras/credentials/include/exr_credentials.h").read_text(encoding="utf-8")
    record("credentials-status-only-surface", "char message" not in header and
           "exr_credentials_status_name" in header, "status names only")
    opds_header = Path("extras/opds/include/opds.h").read_text(encoding="utf-8")
    record("opds-redaction-declared", "opds_redact_url" in opds_header and
           "redacted request lines only" in opds_header, "public helper")

    root_cmake = Path("CMakeLists.txt").read_text(encoding="utf-8")
    record("optional-modules-outside-default-build",
           "credentials" not in root_cmake and "account-profiles" not in root_cmake,
           "root build untouched")

    values = {"primary": secrets.token_bytes(48), "secondary": secrets.token_bytes(32),
              "unicode": ("密钥-" + secrets.token_hex(6)).encode("utf-8")}
    texts = {"authorization": "Bearer " + secrets.token_hex(16),
             "cookie": "session=" + secrets.token_hex(12),
             "userinfo": secrets.token_hex(8)}
    context = {"forbidden": list(texts.values()), "label": "guard input"}
    detector = selfcheck(values, texts, context)
    record("detector-red-actions", detector["passed"],
           "%d cases %d forms" % (len(detector["cases"]), detector["forms"]))
    for case in detector["cases"]:
        record("detector:" + case["case"], case["passed"], "planted case")

    summary = {"schema": 1, "package": "S08", "role": "guard", "accepted": not problems,
               "source_sha": head, "fixed_base": FIXED_BASE, "frozen_sdk": FROZEN_SDK,
               "run_id": os.environ.get("GITHUB_RUN_ID", ""),
               "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
               "job": os.environ.get("GITHUB_JOB", ""),
               "changed_paths": changed, "checks": checks, "problems": problems,
               "detector": detector}
    (output / "guard.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    for item in checks:
        print("%s %s %s" % ("PASS" if item["ok"] else "FAIL", item["id"], item["detail"]))
    print("guard accepted=%s checks=%d problems=%d" % (summary["accepted"], len(checks),
                                                       len(problems)))
    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
