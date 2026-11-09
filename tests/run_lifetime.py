#!/usr/bin/env python3
"""Verify SDK contract deaths are intentional aborts, not memory crashes."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("fixtures", type=Path)
    parser.add_argument("--case", help="Run just one listed case")
    parser.add_argument("--output", type=Path, help="Keep raw per-case logs and summary.json")
    args = parser.parse_args()
    executable = str(args.executable.resolve())
    listing = subprocess.run([executable, "--list"], capture_output=True, check=True,
                             encoding="utf-8", errors="replace")
    cases = [line.split() for line in listing.stdout.splitlines() if line.strip()]
    if args.case:
        cases = [case for case in cases if case[0] == args.case]
        if not cases:
            parser.error(f"Unknown case: {args.case}")
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
    results = []
    # Direct SIGABRT on POSIX; MSVC CRT abort exits with 3 or fail-fast's
    # STATUS_FATAL_APP_EXIT. SIGSEGV and access violations never qualify.
    abort_codes = {3, 0x40000015} if os.name == "nt" else {-signal.SIGABRT}
    for name, expectation in cases:
        try:
            process = subprocess.run([executable, name, str(args.fixtures.resolve())],
                                     capture_output=True, timeout=45)
            stdout = process.stdout.decode("utf-8", errors="replace")
            stderr = process.stderr.decode("utf-8", errors="replace")
            combined = stdout + stderr
            sanitizer_error = any(marker in combined for marker in (
                "ERROR: AddressSanitizer", "ERROR: LeakSanitizer", "runtime error:",
                "AddressSanitizer:DEADLYSIGNAL", "TEST_CHECK_FAILED"))
            if expectation == "abort":
                reasons = {"callback_destroy_active": "重入", "render_callback_free_cache_owner": "重入",
                           "canvas_sink_destroy_active": "重入", "borrowed_page_free": "借用"}
                reason = reasons.get(name, "对象已释放")
                passed = (process.returncode in abort_codes
                          and "EXR_LIFETIME_ASSERT" in stderr
                          and reason in stderr and not sanitizer_error)
            else:
                passed = (process.returncode == 0 and f"PASS {name} (" in stdout
                          and "EXR_LIFETIME_ASSERT" not in stderr and not sanitizer_error)
            result = {"case": name, "expected": expectation, "exit_code": process.returncode,
                      "passed": passed, "stdout": stdout, "stderr": stderr}
        except subprocess.TimeoutExpired as exc:
            result = {"case": name, "expected": expectation, "passed": False,
                      "error": f"Timed out after {exc.timeout} seconds"}
        results.append(result)
        print(f"{'PASS' if result['passed'] else 'FAIL'} {name}: "
              f"{expectation}, exit={result.get('exit_code', 'timeout')}", flush=True)
        if not result["passed"]:
            print(result.get("stdout", "") + result.get("stderr", result.get("error", "")))
        if args.output:
            (args.output / f"{name}.txt").write_text(
                f"case={name}\nexpected={expectation}\nexit={result.get('exit_code')}\n"
                + result.get("stdout", "") + result.get("stderr", result.get("error", "")),
                encoding="utf-8")
    summary = {"total": len(results), "passed": sum(r["passed"] for r in results),
               "intentional_aborts": sum(r["passed"] and r["expected"] == "abort" for r in results),
               "results": results}
    if args.output:
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False)
                                                + "\n", encoding="utf-8")
    print(f"Lifetime contracts: {summary['passed']}/{summary['total']} passed; "
          f"{summary['intentional_aborts']} intentional assertion aborts")
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
