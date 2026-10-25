#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify one S12 platform run against the frozen expectation.

Checks, in this order:

1. the frozen fixture digests cover the files actually used;
2. every required record exists with exactly the expected fields (a "$nonzero"
   expectation means "any nonzero integer", used only where the public contract
   promises a refusal without naming one status);
3. hex payloads are lowercase, even-length bytes and every recorded sha256
   covers exactly those bytes;
4. the retained metadata wire matches the published command document with the
   randomly assigned revision ID substituted;
5. the C ABI consumer agrees with the C++ consumer for the shared views;
6. the byte snapshots prove that reopen, re-attach, the second receive and the
   read-only C consumer never moved the product database or the pending intent.
"""
import argparse
import hashlib
import json
import os
import sys

SENTINEL_NONZERO = "$nonzero"
AGREEMENT = [
    ("attach.page.all", "c.page.all"),
    ("attach.page.forward.0", "c.page.forward.0"),
    ("attach.query.ascii", "c.query.ascii"),
    ("attach.query.unicode", "c.query.unicode"),
    ("attach.canonical.nfc", "c.canonical.nfc"),
    ("attach.lookup.id", "c.lookup.id"),
    ("attach.metadata.one", "c.metadata.one"),
    ("attach.metadata.two", "c.metadata.two"),
    ("attach.metadata.empty", "c.metadata.empty"),
]
STABLE_PAIRS = [
    ("main.after_seed", "main.after_reattach"),
    ("main.settled", "main.after_reopen"),
    ("mirror.receive1", "mirror.receive2"),
    ("mirror.receive2", "mirror.after_reopen"),
    ("sidecar.staged", "sidecar.reopened"),
]


def container_texts(path, ids):
    """Read the UTF-16LE text records the fixtures wrote into cases.bin."""
    with open(path, "rb") as handle:
        blob = handle.read()
    if blob[:4] != b"S121" or int.from_bytes(blob[4:8], "little") != 1:
        raise SystemExit("bad request container magic or version")
    count = int.from_bytes(blob[8:12], "little")
    at = 12
    wanted = {}
    for _ in range(count):
        name_length = int.from_bytes(blob[at:at + 4], "little")
        at += 4
        name = blob[at:at + name_length].decode("ascii")
        at += name_length
        kind = int.from_bytes(blob[at:at + 4], "little")
        at += 4
        length = int.from_bytes(blob[at:at + 4], "little")
        at += 4
        payload = blob[at:at + length]
        at += length
        if name in ids and kind in (1, 2):
            wanted[name] = payload.decode("utf-16-le", "surrogatepass")
    return wanted


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path):
    value = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(65536)
            if not block:
                break
            value.update(block)
    return value.hexdigest()


def parse_records(path):
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
                if not current or current in records:
                    raise SystemExit("bad or duplicate record id in " + path)
                records[current] = {}
                order.append(current)
                continue
            if current is None or "=" not in line:
                raise SystemExit("malformed observation line in %s: %s" % (path, line))
            key, _, value = line.partition("=")
            if key in records[current]:
                raise SystemExit("duplicate field %s in record %s" % (key, current))
            records[current][key] = value
    return records, order


def match(want, got):
    if want == SENTINEL_NONZERO:
        try:
            return int(got) != 0
        except ValueError:
            return False
    return want == got


def check_group(label, observations, expected_records, required, derived, problems):
    verdicts = {}
    failures = {}
    for name in sorted(required):
        want = expected_records[name]
        got = observations.get(name)
        if got is None:
            verdicts[name] = "missing"
            continue
        if want == got:
            verdicts[name] = "pass"
            continue
        if set(want) == set(got) and all(match(want[key], got[key]) for key in want):
            verdicts[name] = "pass"
            continue
        verdicts[name] = "fail"
        failures[name] = {key: {"expected": want.get(key), "actual": got.get(key)}
                          for key in sorted(set(want) | set(got)) if want.get(key) != got.get(key)}
    extra = sorted(set(observations) - set(required) - set(derived))
    for name in sorted(derived):
        if name not in observations:
            problems.append("%s: derived record %s is missing" % (label, name))
    missing = sorted(name for name, verdict in verdicts.items() if verdict == "missing")
    failed = sorted(name for name, verdict in verdicts.items() if verdict == "fail")
    if missing:
        problems.append("%s: missing records %s" % (label, ", ".join(missing)))
    if failed:
        problems.append("%s: %d records differ" % (label, len(failed)))
    if extra:
        problems.append("%s: unexpected records %s" % (label, ", ".join(extra)))
    summary = {"required": len(required), "pass": len(required) - len(missing) - len(failed),
               "fail": len(failed), "missing": len(missing)}
    return summary, verdicts, failures


def check_integrity(label, observations, problems):
    checked = 0
    for name, fields in sorted(observations.items()):
        encoded = fields.get("hex")
        if encoded is None:
            continue
        if encoded != encoded.lower() or any(char not in "0123456789abcdef" for char in encoded):
            problems.append("%s: %s carries a non-lowercase hex payload" % (label, name))
            continue
        if len(encoded) % 2:
            problems.append("%s: %s carries an odd-length hex payload" % (label, name))
            continue
        payload = bytes.fromhex(encoded)
        if "bytes" in fields and fields["bytes"] != str(len(payload)):
            problems.append("%s: %s length differs from its payload" % (label, name))
        if "sha" in fields:
            if sha256_bytes(payload) != fields["sha"]:
                problems.append("%s: %s sha256 does not cover its payload" % (label, name))
            checked += 1
    return checked


def check_wire(rule, observations, problems):
    name = "metadata.wire.book1"
    fields = observations.get(name)
    if fields is None:
        problems.append("derived wire record is missing")
        return None
    identity = fields.get(rule["id_field"], "")
    if len(identity) != rule["id_length"] or any(char not in "0123456789abcdef" for char in identity):
        problems.append("derived wire record has no valid assigned revision identity")
        return None
    template = rule["template"].replace("@@ID@@", identity).encode("utf-8")
    payload = bytes.fromhex(fields.get(rule["hex_field"], ""))
    if payload != template:
        problems.append("retained wire document differs from the published command shape")
        return identity
    if sha256_bytes(payload) != fields.get(rule["sha_field"]):
        problems.append("retained wire sha256 does not cover the recorded bytes")
    return identity


def check_agreement(observations, c_observations, problems):
    disagreements = []
    for consumer_name, c_name in AGREEMENT:
        left = observations.get(consumer_name)
        right = c_observations.get(c_name)
        if left is None or right is None:
            problems.append("agreement pair is incomplete: %s / %s" % (consumer_name, c_name))
            continue
        for key in ("status", "error", "rows", "joined"):
            if key in left and key in right and left[key] != right[key]:
                disagreements.append("%s vs %s field %s" % (consumer_name, c_name, key))
    if disagreements:
        problems.append("C ABI disagrees with C++: " + "; ".join(disagreements))
    return len(AGREEMENT)


def check_snapshots(root, database, problems):
    directory = os.path.join(root, "snapshots")
    digests = {}
    if not os.path.isdir(directory):
        problems.append("snapshot directory is missing")
        return digests, {}
    for entry in sorted(os.listdir(directory)):
        path = os.path.join(directory, entry)
        if os.path.isfile(path):
            digests[entry[:-4] if entry.endswith(".bin") else entry] = {
                "sha256": sha256_file(path), "bytes": os.path.getsize(path)}
    for left, right in STABLE_PAIRS:
        if left not in digests or right not in digests:
            problems.append("stability snapshot missing: %s / %s" % (left, right))
        elif digests[left]["sha256"] != digests[right]["sha256"]:
            problems.append("bytes moved between %s and %s" % (left, right))
    if os.path.isfile(database):
        live = sha256_file(database)
        if "main.final" not in digests:
            problems.append("final snapshot is missing")
        elif digests["main.final"]["sha256"] != live:
            problems.append("the read-only C consumer changed the product database")
    else:
        problems.append("product database is missing")
    return digests, {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--root", required=True, help="consumer working root")
    parser.add_argument("--observations", required=True)
    parser.add_argument("--c-observations", required=True)
    parser.add_argument("--local", required=True)
    parser.add_argument("--consumer", required=True)
    parser.add_argument("--c-consumer", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--run", default="")
    parser.add_argument("--attempt", default="")
    parser.add_argument("--output", required=True)
    options = parser.parse_args()

    expected_path = os.path.join(options.fixtures, "expected.json")
    meta_path = os.path.join(options.fixtures, "meta.json")
    case_path = os.path.join(options.fixtures, "cases.bin")
    with open(expected_path, "r", encoding="utf-8") as handle:
        expected = json.load(handle)
    with open(meta_path, "r", encoding="utf-8") as handle:
        meta = json.load(handle)

    problems = []
    if meta["expected_sha256"] != sha256_file(expected_path):
        problems.append("expected.json digest differs from its manifest")
    if meta["case_file_sha256"] != sha256_file(case_path):
        problems.append("cases.bin digest differs from its manifest")

    observations, consumer_order = parse_records(options.observations)
    c_observations, c_order = parse_records(options.c_observations)

    summary, verdicts, failures = check_group("consumer", observations, expected["records"],
                                              expected["required_consumer"], expected["derived"], problems)
    c_summary, c_verdicts, c_failures = check_group("c", c_observations, expected["c_records"],
                                                    expected["required_c"], [], problems)
    wire_identity = check_wire(expected["derived"]["metadata.wire.book1"], observations, problems)
    integrity = check_integrity("consumer", observations, problems)
    c_integrity = check_integrity("c", c_observations, problems)
    agreement = check_agreement(observations, c_observations, problems)

    names = container_texts(case_path, {"dir.workspace", "dir.space", "dir.library", "file.main"})
    database = os.path.join(options.root, names["dir.workspace"], names["dir.space"], names["dir.library"],
                            names["file.main"])
    digests, _ = check_snapshots(options.root, database, problems)

    local = {}
    if os.path.isfile(options.local):
        with open(options.local, "r", encoding="utf-8") as handle:
            for line in handle:
                key, _, value = line.rstrip("\n").partition("=")
                if key:
                    local[key] = value
    else:
        problems.append("platform-local evidence is missing")

    report = {
        "format": "s12-1",
        "platform": options.platform,
        "source": options.source,
        "run": options.run,
        "attempt": options.attempt,
        "fixtures": {"cases.bin": meta["case_file_sha256"], "expected.json": meta["expected_sha256"]},
        "consumers": {
            "s12-consumer": {"name": os.path.basename(options.consumer), "sha256": sha256_file(options.consumer)},
            "s12-c-consumer": {"name": os.path.basename(options.c_consumer),
                               "sha256": sha256_file(options.c_consumer)},
        },
        "observation_files": {
            "consumer": {"name": os.path.basename(options.observations),
                         "sha256": sha256_file(options.observations), "records": len(observations),
                         "order": consumer_order},
            "c": {"name": os.path.basename(options.c_observations),
                  "sha256": sha256_file(options.c_observations), "records": len(c_observations), "order": c_order},
        },
        "groups": {"consumer": summary, "c": c_summary},
        "verdicts": {"consumer": verdicts, "c": c_verdicts},
        "failures": {"consumer": failures, "c": c_failures},
        "integrity": {"consumer_sha_payloads": integrity, "c_sha_payloads": c_integrity,
                      "wire_identity": wire_identity, "agreement_pairs": agreement},
        "snapshots": digests,
        "platform_local": local,
        "problems": problems,
        "ok": not problems,
    }
    if not os.path.isdir(options.output):
        os.makedirs(options.output)
    with open(os.path.join(options.output, "report.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=True, sort_keys=True, indent=1)
        handle.write("\n")

    print("platform=%s consumer=%d/%d c=%d/%d agreement=%d integrity=%d/%d ok=%s" % (
        options.platform, summary["pass"], summary["required"], c_summary["pass"], c_summary["required"],
        agreement, integrity, c_integrity, report["ok"]))
    for name in sorted(failures)[:12]:
        print("fail %s %s" % (name, json.dumps(failures[name], sort_keys=True)[:400]))
    for name in sorted(c_failures)[:12]:
        print("fail-c %s %s" % (name, json.dumps(c_failures[name], sort_keys=True)[:400]))
    for problem in problems:
        print("problem %s" % problem)
    print("observations %s" % report["observation_files"]["consumer"]["sha256"])
    print("c-observations %s" % report["observation_files"]["c"]["sha256"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
