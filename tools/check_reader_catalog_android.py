#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fail closed on incomplete production-catalog instrumentation reports."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

TESTS = {
    "createsAndReopensCatalog",
    "rejectsForeignDatabasesWithoutChangingData",
    "keepsCompleteShelfTriggers",
    "retainsImmutableRevisionsAndTombstones",
    "rollsBackInterruptedMigrationAndAllowsRetry",
    "rejectsTamperedAssetFieldsAndSource",
    "rejectsOversizedAndMalformedAssets",
    "enforcesWorkerOwnership",
}


def inspect(reports):
    files = sorted(reports.rglob("*.xml"))
    if not files:
        raise ValueError("missing catalog instrumentation XML")
    cases = []
    inventory = []
    for path in files:
        raw = path.read_bytes()
        root = ET.fromstring(raw)
        for suite in root.iter("testsuite"):
            for status in ("failures", "errors", "skipped"):
                if int(suite.get(status, "0")) != 0:
                    raise ValueError("catalog test suite reports failures or skips")
        inventory.append({"path": path.relative_to(reports).as_posix(),
                          "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        for case in root.iter("testcase"):
            if case.get("classname") != "org.exreader.host.CatalogStoreTest":
                raise ValueError("unexpected instrumentation test class")
            if any(case.find(status) is not None for status in ("failure", "error", "skipped")):
                raise ValueError("catalog test failed or was skipped: " + str(case.get("name")))
            cases.append(case.get("name"))
    if len(cases) != len(TESTS) or set(cases) != TESTS:
        raise ValueError("catalog test identities are missing, duplicated or unexpected")
    return {"tests": sorted(cases), "reports": inventory}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {"accepted": False, "problems": [], "scope": "Android catalog adapter only",
              "source_sha": os.environ.get("GITHUB_SHA"),
              "run_id": os.environ.get("GITHUB_RUN_ID"),
              "attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
              "physical_device_execution": False}
    try:
        if os.environ.get("GITHUB_ACTIONS") != "true" or not result["source_sha"]:
            raise ValueError("catalog acceptance must execute in GitHub Actions")
        evidence = args.output.parent
        if (evidence / "device-api.txt").read_text().strip() != "34":
            raise ValueError("unexpected Android API")
        if (evidence / "device-abi.txt").read_text().strip() != "x86_64":
            raise ValueError("unexpected Android architecture")
        if (evidence / "source.txt").read_text().strip() != result["source_sha"]:
            raise ValueError("checked-out source differs from workflow source")
        result.update(inspect(args.reports))
        result.update(accepted=True, passed=len(TESTS), failed=0, skipped=0,
                      device_api=34, device_abi="x86_64")
    except (ValueError, OSError, ET.ParseError) as error:
        result["problems"].append(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    if not result["accepted"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
