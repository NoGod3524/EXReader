#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Static agreement check between the frozen expectations and the consumers.

The two installed consumers emit one record per observation and the checker
requires the exact record set. This gate reads the consumer sources and the
frozen expectation file, so a renamed or forgotten record is caught before any
binary is built. It never executes a consumer and never changes a value.
"""
import argparse
import json
import os
import re
import sys

CALLS_CONSUMER = ("record", "page_record", "metadata_of", "query_record", "canonical_record", "stability_record",
                  "competing")
CALLS_C = ("record", "page_record", "row_record", "text_record")

PATTERN = re.compile(r"\b(%s)\(\s*\"([a-zA-Z0-9_.\-]+)\"" % "|".join(CALLS_CONSUMER))
PATTERN_C = re.compile(r"\b(%s)\(\s*\"([a-zA-Z0-9_.\-]+)\"" % "|".join(CALLS_C))
LISTED = re.compile(r"for \(const char \*name : \{([^}]*)\}\)")
NAMED_ARGUMENT = re.compile(r"\bcompeting\([^,]*,\s*\"([a-zA-Z0-9_.\-]+)\"\)")
ASCII_CALL = re.compile(r"\bascii\(\s*\"([a-zA-Z0-9_.\-]+)\"\s*\)")
DECODE_CALL = re.compile(r"\b(?:decode|must_convert|text_record)\([^;]*?\"([a-zA-Z0-9_.\-]+)\"\s*[,)]")
QUOTED = re.compile(r"\"([a-zA-Z0-9_.\-]+)\"")
CONVERSION_ARRAY = re.compile(r"conversions\[\] = \{(.*?)\};", re.S)


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def consumer_names(source):
    names = set(match.group(2) for match in PATTERN.finditer(source))
    for block in LISTED.finditer(source):
        names.update(QUOTED.findall(block.group(1)))
    array = CONVERSION_ARRAY.search(source)
    if not array:
        raise SystemExit("conversion list not found in probe.cpp")
    for item in QUOTED.findall(array.group(1)):
        names.add("utf16." + item)
    names.update(match.group(1) for match in NAMED_ARGUMENT.finditer(source))
    names.update("attach.seed.%d" % index for index in range(1, 7))
    return names


def c_names(source):
    return set(match.group(2) for match in PATTERN_C.finditer(source))


def kind_problems(label, source, kinds, problems):
    """A text item must be decoded, an ASCII identity must be read as ASCII."""
    for match in ASCII_CALL.finditer(source):
        name = match.group(1)
        if name in kinds and kinds[name] != 0:
            problems.append("%s reads %s as ASCII but the container stores kind %d" % (label, name, kinds[name]))
    for match in DECODE_CALL.finditer(source):
        name = match.group(1)
        if name in kinds and kinds[name] == 0:
            problems.append("%s decodes %s as UTF-16 but the container stores ASCII" % (label, name))


def compare(label, produced, required, problems):
    missing = sorted(set(required) - produced)
    unexpected = sorted(produced - set(required))
    if missing:
        problems.append("%s: expectations without a producing call: %s" % (label, ", ".join(missing)))
    if unexpected:
        problems.append("%s: calls without an expectation: %s" % (label, ", ".join(unexpected)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=os.path.dirname(os.path.abspath(__file__)))
    parser.add_argument("--expected", required=True)
    parser.add_argument("--meta", default="")
    options = parser.parse_args()

    with open(options.expected, "r", encoding="utf-8") as handle:
        expected = json.load(handle)
    meta_path = options.meta or os.path.join(os.path.dirname(os.path.abspath(options.expected)), "meta.json")
    kinds = {}
    if os.path.isfile(meta_path):
        with open(meta_path, "r", encoding="utf-8") as handle:
            kinds = json.load(handle).get("kinds", {})

    problems = []
    derived = set(expected.get("derived", {}))
    probe_source = read(os.path.join(options.root, "probe.cpp"))
    api_source = read(os.path.join(options.root, "api.c"))
    probe = consumer_names(probe_source)
    compare("consumer", probe, set(expected["required_consumer"]) | derived, problems)
    api = c_names(api_source)
    compare("c-consumer", api, expected["required_c"], problems)
    if kinds:
        kind_problems("consumer", probe_source, kinds, problems)
        kind_problems("c-consumer", api_source, kinds, problems)

    print("consumer records: %d produced / %d expected" % (len(probe), len(expected["required_consumer"])))
    print("c records: %d produced / %d expected" % (len(api), len(expected["required_c"])))
    for problem in problems:
        print("problem %s" % problem)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
