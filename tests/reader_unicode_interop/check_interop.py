#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare raw G14 Unicode consumer observations with the frozen expectations.

The consumer only records what the installed public API returned. This script
holds no product knowledge beyond the frozen expectation file, so a passing
run means the observed bytes, orderings, statuses and hashes match the values
frozen before the run.
"""
import argparse
import hashlib
import json
import os
import sys


def parse_observations(path):
    records = {}
    order = []
    current = None
    with open(path, "r", encoding="ascii") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if not line:
                continue
            if line[0] == "#":
                current = line[1:]
                if not current:
                    raise SystemExit("empty record id in " + path)
                if current in records:
                    raise SystemExit("duplicate record " + current + " in " + path)
                records[current] = {}
                order.append(current)
                continue
            if current is None:
                raise SystemExit("field before any record in " + path)
            if "=" not in line:
                raise SystemExit("malformed field line in " + path + ": " + line)
            key, _, value = line.partition("=")
            if key in records[current]:
                raise SystemExit("duplicate field " + key + " in record " + current)
            records[current][key] = value
    return records, order


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(65536)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def check_group(observations, expected, required, aliases):
    records = expected["records"]
    missing = [name for name in required if name not in observations]
    unexpected = [name for name in observations
                  if name not in required and name not in aliases]
    missing_alias = [name for name in aliases if name not in observations]
    failed = {}
    verdicts = {}

    for name in required:
        if name not in observations:
            verdicts[name] = "missing"
            continue
        want = records[name]
        got = observations[name]
        if want == got:
            verdicts[name] = "pass"
            continue
        difference = {}
        for key in sorted(set(want) | set(got)):
            if want.get(key) != got.get(key):
                difference[key] = {"expected": want.get(key), "actual": got.get(key)}
        verdicts[name] = "fail"
        failed[name] = difference

    alias_ok = 0
    for name, target in aliases.items():
        if name not in observations:
            verdicts[name] = "missing"
            continue
        if observations[name] != records[target]:
            verdicts[name] = "fail"
            failed[name] = {"alias": {"expected": target, "actual": "differs from expectation"}}
            continue
        if target in observations and observations[name] != observations[target]:
            verdicts[name] = "fail"
            failed[name] = {"alias": {"expected": target, "actual": "differs from canonical run"}}
            continue
        verdicts[name] = "pass"
        alias_ok += 1

    integrity = []
    for name in required:
        got = observations.get(name)
        if got is None:
            continue
        if "hex" in got:
            encoded = got["hex"]
            if encoded.lower() != encoded or any(c not in "0123456789abcdef" for c in encoded):
                integrity.append({"record": name, "issue": "hex payload is not lowercase hex"})
                continue
            if len(encoded) % 2:
                integrity.append({"record": name, "issue": "hex payload has an odd length"})
                continue
            data = bytes.fromhex(encoded)
            if "bytes" in got and got["bytes"] != str(len(data)):
                integrity.append({"record": name, "issue": "recorded length differs from payload"})
            if "sha256" in got:
                digest = hashlib.sha256(data).hexdigest()
                if digest != got["sha256"]:
                    integrity.append({"record": name, "issue": "sha256 does not cover the payload"})
        if "rows" in got:
            try:
                claimed = int(got["rows"])
            except ValueError:
                integrity.append({"record": name, "issue": "row count is not an integer"})
                continue
            present = set()
            for key in got:
                head, _, tail = key.partition(".")
                if head.startswith("row") and head[3:].isdigit() and tail:
                    present.add(head)
            if len(present) != claimed:
                integrity.append({"record": name, "issue": "row count differs from row fields"})

    areas = {}
    for name in required:
        area = name.split(".")[0]
        entry = areas.setdefault(area, {"required": 0, "pass": 0, "fail": 0, "missing": 0})
        entry["required"] += 1
        verdict = verdicts.get(name, "missing")
        if verdict == "pass":
            entry["pass"] += 1
        elif verdict == "fail":
            entry["fail"] += 1
        else:
            entry["missing"] += 1

    ok = (not missing and not unexpected and not missing_alias and not failed
          and not integrity)
    summary = {
        "required_records": len(required),
        "record_pass": sum(1 for name in required if verdicts.get(name) == "pass"),
        "record_fail": sum(1 for name in required if verdicts.get(name) == "fail"),
        "record_missing": len(missing),
        "alias_checks": len(aliases),
        "alias_pass": alias_ok,
        "alias_fail": sum(1 for name in aliases if verdicts.get(name) == "fail"),
        "unexpected_records": unexpected,
        "integrity_issues": integrity,
        "areas": areas,
        "ok": ok,
    }
    return summary, verdicts, failed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", required=True, help="fixture directory")
    parser.add_argument("--observations", required=True, help="consumer observation file")
    parser.add_argument("--c-observations", required=True, help="C ABI consumer observation file")
    parser.add_argument("--consumer", required=True, help="C++ consumer binary")
    parser.add_argument("--c-consumer", required=True, help="C consumer binary")
    parser.add_argument("--platform", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--run", default="")
    parser.add_argument("--attempt", default="")
    parser.add_argument("--output", required=True, help="evidence directory")
    options = parser.parse_args()

    expected_path = os.path.join(options.fixtures, "expected.json")
    meta_path = os.path.join(options.fixtures, "meta.json")
    with open(expected_path, "r", encoding="utf-8") as handle:
        expected = json.load(handle)
    with open(meta_path, "r", encoding="utf-8") as handle:
        fixture_meta = json.load(handle)

    problems = []
    if fixture_meta["expected_sha256"] != sha256_file(expected_path):
        problems.append("expected.json digest differs from its own manifest")
    case_path = os.path.join(options.fixtures, "cases.bin")
    if fixture_meta["case_file_sha256"] != sha256_file(case_path):
        problems.append("cases.bin digest differs from its own manifest")

    consumer_records, consumer_order = parse_observations(options.observations)
    c_records, c_order = parse_observations(options.c_observations)

    consumer_summary, consumer_verdicts, consumer_failed = check_group(
        consumer_records, expected, expected["required_consumer"], expected["aliases"])
    c_summary, c_verdicts, c_failed = check_group(
        c_records, expected, expected["required_c"], {})

    report = {
        "fixture": expected["format"],
        "fixture_digests": {
            "cases.bin": fixture_meta["case_file_sha256"],
            "expected.json": fixture_meta["expected_sha256"],
        },
        "platform": options.platform,
        "source": options.source,
        "run": options.run,
        "attempt": options.attempt,
        "consumers": {
            "unicode-consumer": {"sha256": sha256_file(options.consumer),
                                 "name": os.path.basename(options.consumer)},
            "unicode-c-consumer": {"sha256": sha256_file(options.c_consumer),
                                   "name": os.path.basename(options.c_consumer)},
        },
        "observation_files": {
            "consumer": {"name": os.path.basename(options.observations),
                         "sha256": sha256_file(options.observations),
                         "records": len(consumer_records),
                         "order": consumer_order},
            "c": {"name": os.path.basename(options.c_observations),
                  "sha256": sha256_file(options.c_observations),
                  "records": len(c_records),
                  "order": c_order},
        },
        "groups": {"consumer": consumer_summary, "c": c_summary},
        "records": {"consumer": consumer_verdicts, "c": c_verdicts},
        "failures": {"consumer": consumer_failed, "c": c_failed},
        "problems": problems,
        "ok": consumer_summary["ok"] and c_summary["ok"] and not problems,
    }
    if not os.path.isdir(options.output):
        os.makedirs(options.output)
    with open(os.path.join(options.output, "report.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=True, sort_keys=True, indent=1)

    print("platform=%s consumer=%d/%d c=%d/%d ok=%s" % (
        options.platform, consumer_summary["record_pass"], consumer_summary["required_records"],
        c_summary["record_pass"], c_summary["required_records"], report["ok"]))
    for area in sorted(consumer_summary["areas"]):
        entry = consumer_summary["areas"][area]
        print("area %s %d/%d" % (area, entry["pass"], entry["required"]))
    print("consumer-sha256 %s" % report["consumers"]["unicode-consumer"]["sha256"])
    print("c-consumer-sha256 %s" % report["consumers"]["unicode-c-consumer"]["sha256"])
    print("fixtures cases=%s expected=%s" % (
        report["fixture_digests"]["cases.bin"], report["fixture_digests"]["expected.json"]))
    print("observations %s c=%s" % (
        report["observation_files"]["consumer"]["sha256"],
        report["observation_files"]["c"]["sha256"]))
    if consumer_summary["unexpected_records"]:
        print("unexpected: %s" % ",".join(sorted(consumer_summary["unexpected_records"])[:20]))
    for name in sorted(consumer_failed)[:10]:
        print("fail %s %s" % (name, json.dumps(consumer_failed[name], sort_keys=True)[:400]))
    for name in sorted(c_failed)[:10]:
        print("fail-c %s %s" % (name, json.dumps(c_failed[name], sort_keys=True)[:400]))
    for issue in consumer_summary["integrity_issues"][:10]:
        print("integrity %s %s" % (issue["record"], issue["issue"]))
    for problem in problems:
        print("problem %s" % problem)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
