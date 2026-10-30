#!/usr/bin/env python3
"""Auditor for package C02 (full49 migration coordinator). Run with python -I.

  audit ... --base SHA            owned-path / forbidden-path / static checks
  audit ... --evidence FILE.json  additionally validate the native check output
Exit status is non-zero on any violation. Passing grants no acceptance count.
"""
import argparse, json, re, subprocess, sys

BASE = "2743f32a4eccd5823657da19cb4f77f2411424af"
OWNED = (
    "extras/migration/windows_coordinator_20261030/",
    "tests/migration/windows_coordinator_20261030/",
    ".github/workflows/claude_dot_coordinator_20261030.yml",
    "scripts/audit/claude_dot_coordinator_20261030.py",
    "docs/reader-total-progress/CLAUDE_DOT_C02_20261030.md",
)
FORBIDDEN_SUBSTR = ("lm_main", "windows_publish_20261030", "windows_recovery_engine_20261030",
                    "windows_migration_host", "reader_f05", "windows_p0_fault")
MIN_CHECKS = 200


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--evidence")
    ap.add_argument("--head", default="HEAD")
    a = ap.parse_args()
    errors = []
    changed = [l for l in git("diff", "--name-only", a.base, a.head).splitlines() if l]
    if not changed:
        errors.append("empty diff against base")
    for path in changed:
        if not path.startswith(OWNED):
            errors.append("path outside owned set: " + path)
    for path in git("ls-tree", "-r", "--name-only", a.head, "--", *OWNED[:2]).splitlines():
        text = git("show", f"{a.head}:{path}")
        for bad in FORBIDDEN_SUBSTR:
            if bad in text and not path.endswith("claude_dot_coordinator_20261030.py"):
                errors.append(f"{path} references forbidden owner '{bad}'")
    hdr = git("show", f"{a.head}:extras/migration/windows_coordinator_20261030/include/exr_wc.h")
    if "EXR_WC_ID_BYTES 49u" not in hdr:
        errors.append("49-byte identity constant missing")
    if a.evidence:
        ev = json.load(open(a.evidence, encoding="utf-8"))
        if ev.get("passed") is not True or ev.get("failures") != 0:
            errors.append("native check did not pass")
        if int(ev.get("checks", 0)) < MIN_CHECKS:
            errors.append(f"too few checks: {ev.get('checks')}")
        if ev.get("scope") != "module-only-not-full-p0":
            errors.append("scope marker missing")
        if not re.fullmatch(r"[0-9a-f]{40}", str(ev.get("source", ""))):
            errors.append("source identity missing")
    print(json.dumps({"changed": changed, "errors": errors, "ok": not errors}, indent=1))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
