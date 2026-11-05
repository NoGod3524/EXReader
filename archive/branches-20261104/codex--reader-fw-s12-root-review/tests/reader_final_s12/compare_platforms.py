#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Require the Windows and Linux S12 runs to agree byte for byte.

Only the cross-platform observation files are compared: everything platform
specific (absolute paths, host path limits, file system details) is kept in each
platform's own local evidence file and in its report.
"""
import argparse
import hashlib
import json
import os
import sys


def sha256_file(path):
    value = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(65536)
            if not block:
                break
            value.update(block)
    return value.hexdigest()


def named(values, label, problems):
    result = {}
    for item in values:
        name, _, path = item.partition("=")
        if not name or not path or name in result:
            problems.append("bad --%s argument %s" % (label, item))
            continue
        result[name] = path
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--run", default="")
    parser.add_argument("--attempt", default="")
    parser.add_argument("--observations", action="append", default=[])
    parser.add_argument("--c-observations", action="append", default=[])
    parser.add_argument("--report", action="append", default=[])
    parser.add_argument("--output", required=True)
    options = parser.parse_args()

    problems = []
    observations = named(options.observations, "observations", problems)
    c_observations = named(options.c_observations, "c-observations", problems)
    reports = named(options.report, "report", problems)
    platforms = sorted(observations)
    if platforms != ["Linux", "Windows"] or sorted(c_observations) != platforms or sorted(reports) != platforms:
        problems.append("both Windows and Linux evidence are required")

    digests = {}
    for platform in platforms:
        for kind, mapping in (("observations", observations), ("c-observations", c_observations),
                              ("report", reports)):
            path = mapping.get(platform, "")
            if not path or not os.path.isfile(path):
                problems.append("%s %s is missing" % (platform, kind))
                continue
            digests.setdefault(platform, {})[kind] = sha256_file(path)
            if kind == "report":
                with open(path, "r", encoding="utf-8") as handle:
                    report = json.load(handle)
                if report.get("ok") is not True:
                    problems.append("%s report is not ok" % platform)
                if report.get("source") != options.source:
                    problems.append("%s report source differs" % platform)
                if options.run and str(report.get("run")) != options.run:
                    problems.append("%s report run differs" % platform)
                if options.attempt and str(report.get("attempt")) != options.attempt:
                    problems.append("%s report attempt differs" % platform)
                digests.setdefault(platform, {})["fixtures"] = report.get("fixtures", {})

    equal = {}
    if len(platforms) == 2:
        left, right = platforms
        for kind in ("observations", "c-observations"):
            if digests.get(left, {}).get(kind) and digests.get(right, {}).get(kind):
                equal[kind] = digests[left][kind] == digests[right][kind]
                if not equal[kind]:
                    problems.append("%s differ between %s and %s" % (kind, left, right))
        fixtures_equal = digests.get(left, {}).get("fixtures") == digests.get(right, {}).get("fixtures")
        equal["fixtures"] = fixtures_equal
        if not fixtures_equal:
            problems.append("frozen fixture digests differ between platforms")
        elif not digests.get(left, {}).get("fixtures"):
            problems.append("frozen fixture digests are missing")
        equal["records"] = None
        for platform in platforms:
            path = observations.get(platform, "")
            if path and os.path.isfile(path):
                with open(path, "r", encoding="ascii") as handle:
                    count = sum(1 for line in handle if line.startswith("#"))
                digests[platform]["records"] = count
        counts = {digests.get(platform, {}).get("records") for platform in platforms}
        equal["records"] = len(counts) == 1 and None not in counts
        if not equal["records"]:
            problems.append("observation record counts differ between platforms")

    report = {
        "format": "s12-1",
        "source": options.source,
        "run": options.run,
        "attempt": options.attempt,
        "platforms": platforms,
        "digests": digests,
        "byte_equality": equal,
        "problems": problems,
        "accepted": not problems,
    }
    if not os.path.isdir(options.output):
        os.makedirs(options.output)
    with open(os.path.join(options.output, "compare.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=True, sort_keys=True, indent=1)
        handle.write("\n")
    for platform in platforms:
        print("%s observations=%s c=%s" % (platform, digests.get(platform, {}).get("observations"),
                                           digests.get(platform, {}).get("c-observations")))
    print("byte_equality=%s" % json.dumps(equal, sort_keys=True))
    for problem in problems:
        print("problem %s" % problem)
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
