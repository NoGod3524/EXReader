#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare the same-source G14 Unicode observations across all three hosts.

Every accepted record must be byte-identical on Windows, Linux and macOS.
Records are compared after parsing, so file ordering cannot hide a difference.
"""
import argparse
import hashlib
import json
import os
import sys


def parse_observations(path):
    records = {}
    current = None
    with open(path, "r", encoding="ascii") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if not line:
                continue
            if line[0] == "#":
                current = line[1:]
                records[current] = {}
                continue
            if current is None:
                raise SystemExit("field before any record in " + path)
            key, _, value = line.partition("=")
            records[current][key] = value
    return records


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(65536)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def split_assignment(text):
    name, _, value = text.partition("=")
    if not name or not value:
        raise SystemExit("expected platform=path, got " + text)
    return name, value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--observations", action="append", default=[],
                        help="platform=path to the C++ consumer observations")
    parser.add_argument("--c-observations", action="append", default=[],
                        help="platform=path to the C consumer observations")
    parser.add_argument("--report", action="append", default=[],
                        help="platform=path to the per-platform report.json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--run", default="")
    parser.add_argument("--attempt", default="")
    options = parser.parse_args()

    observations = {}
    for entry in options.observations:
        name, path = split_assignment(entry)
        observations[("consumer", name)] = path
    for entry in options.c_observations:
        name, path = split_assignment(entry)
        observations[("c", name)] = path
    reports = {}
    for entry in options.report:
        name, path = split_assignment(entry)
        reports[name] = path

    problems = []
    digests = {}
    records = {}
    for key, path in observations.items():
        kind, platform = key
        digests.setdefault(platform, {})[kind] = sha256_file(path)
        records[key] = parse_observations(path)

    fixtures = {}
    for platform, path in reports.items():
        with open(path, "r", encoding="utf-8") as handle:
            report = json.load(handle)
        if not report.get("ok"):
            problems.append("%s per-platform report is not passing" % platform)
        if report.get("source") != options.source:
            problems.append("%s report is bound to a different source" % platform)
        digests.setdefault(platform, {})["report.json"] = sha256_file(path)
        fixtures[platform] = report.get("fixture_digests")
    if len(set(json.dumps(value, sort_keys=True) for value in fixtures.values())) != 1:
        problems.append("frozen fixture digests differ between hosts")

    platforms = sorted({platform for _kind, platform in observations})
    for kind in ("consumer", "c"):
        present = [platform for platform in platforms if (kind, platform) in records]
        if len(present) != 3:
            problems.append("%s observations missing for platforms: %s" % (kind, present))
            continue
        base_platform = present[0]
        base = records[(kind, base_platform)]
        for platform in present[1:]:
            current = records[(kind, platform)]
            missing = sorted(set(base) - set(current))
            extra = sorted(set(current) - set(base))
            if missing:
                problems.append("%s %s missing records: %s" % (kind, platform, ",".join(missing[:10])))
            if extra:
                problems.append("%s %s extra records: %s" % (kind, platform, ",".join(extra[:10])))
            for name in sorted(set(base) & set(current)):
                if base[name] != current[name]:
                    keys = sorted(k for k in set(base[name]) | set(current[name])
                                  if base[name].get(k) != current[name].get(k))
                    problems.append("%s %s differs at %s fields %s" % (
                        kind, platform, name, ",".join(keys[:6])))

    report = {
        "source": options.source,
        "run": options.run,
        "attempt": options.attempt,
        "platforms": platforms,
        "observation_digests": digests,
        "record_counts": {kind + "/" + platform: len(records[(kind, platform)])
                          for kind, platform in sorted(records)},
        "problems": problems,
        "ok": not problems and len(platforms) == 3,
    }
    if not os.path.isdir(options.output):
        os.makedirs(options.output)
    with open(os.path.join(options.output, "compare.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=True, sort_keys=True, indent=1)
    print("platforms=%s ok=%s problems=%d" % (",".join(platforms), report["ok"], len(problems)))
    for problem in problems[:20]:
        print("problem " + problem)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
