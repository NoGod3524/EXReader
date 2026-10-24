#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prove the previous local-downloads build fails these regressions and the
current build passes them.

Both binaries are installed-package consumers of the same source, built from
the same probe source: one against the previously tested implementation, one
against this tree. The evidence is therefore "old fails / new passes", not an
assertion about the current code alone.
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_local_downloads import Ctx, same, sha256_file  # noqa: E402


def intent_lines(book):
    return [b"stage=1", b"key=" + book.key.encode("ascii"), b"bytes=%d" % book.size,
            b"mapped=%d" % book.mapped, b"ids=%d" % book.mapped]


def record(book, lines):
    body = b"EXRLD1\n" + b"".join(line + b"\n" for line in lines)
    return body + b"check=" + hashlib.sha256(body).hexdigest().encode("ascii") + b"\n"


def huge_prefix(book):
    lines = intent_lines(book)
    body = b"EXRLD1\n" + b"".join(line + b"\n" for line in lines)
    pad = 2048 - (len(body) + 5 + 71)
    body += b"pad=" + b"A" * pad + b"\n"
    data = body + b"check=" + hashlib.sha256(body).hexdigest().encode("ascii") + b"\n"
    if len(data) != 2048:
        raise RuntimeError("padded record must reach the bound exactly")
    return data + b"TRAILING"


INTENT_CASES = [
    ("stage_suffix", lambda book: record(book, [b"stage=2junk"] + intent_lines(book)[1:])),
    ("bad_number", lambda book: record(book, [b"stage=1", b"key=" + book.key.encode("ascii"),
                                              b"bytes=%dabc" % book.size, b"mapped=%d" % book.mapped,
                                              b"ids=%d" % book.mapped])),
    ("duplicate_field", lambda book: record(book, [b"stage=1", b"key=" + book.key.encode("ascii"),
                                                   b"bytes=%d" % book.size, b"bytes=%d" % book.size,
                                                   b"mapped=%d" % book.mapped, b"ids=%d" % book.mapped])),
    ("unknown_field", lambda book: record(book, intent_lines(book) + [b"extra=1"])),
    # the mapped id is present, so only the overflow element can be rejected
    ("overflow_id", lambda book: record(book, [b"stage=1", b"key=" + book.key.encode("ascii"),
                                               b"bytes=%d" % book.size, b"mapped=%d" % book.mapped,
                                               b"ids=%d,99999999999999999999" % book.mapped])),
    ("oversized_prefix", huge_prefix),
]


def run_swap(ctx, name):
    env = ctx.new(name)
    book = env.add("txt", "Swap", content=b"A" * 4096)
    env.seed_product([book])
    env.run("remove", "--key", book.key)
    substitute = os.path.join(env.work, "files", "substitute.txt")
    with open(substitute, "wb") as f:
        f.write(b"B" * 4096)  # same size, other bytes
    out = env.run("reimport", "--key", book.key, "--file", book.path,
                  "--swap-at", "1", "--swap-from", substitute)
    r = out.result
    stored = None
    if r["status"] == "ok" and int(r["id"]) > 0:
        stored = env.dump_sha(int(r["id"]))
    return {"status": r["status"], "outcome": r["outcome"],
            "stored_matches_identity": stored == book.sha, "stored_sha": stored or ""}


def run_intent(ctx, name, build):
    env = ctx.new(name)
    book = env.add("txt", "Intent " + name)
    env.seed_product([book])
    with open(os.path.join(env.state, "intent.rdi"), "wb") as f:
        f.write(build(book))
    before = sha256_file(os.path.join(env.work, "sdk.db")) + sha256_file(env.catalog_path)
    r = env.run("recover").result
    after = sha256_file(os.path.join(env.work, "sdk.db")) + sha256_file(env.catalog_path)
    return {"status": r["status"], "outcome": r["outcome"],
            "databases_unchanged": before == after}


def collect(ctx, label):
    cases = {"swap": run_swap(ctx, label + "_swap")}
    for name, build in INTENT_CASES:
        cases["intent_" + name] = run_intent(ctx, label + "_" + name, build)
    return cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-probe", required=True)
    parser.add_argument("--new-probe", required=True)
    parser.add_argument("--cpp", required=True)
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--path-extra", action="append", default=[])
    parser.add_argument("--library", action="append", default=[])
    args = parser.parse_args()

    if not os.path.isdir(args.work):
        os.makedirs(args.work)
    old = Ctx(os.path.abspath(args.old_probe), os.path.abspath(args.cpp),
              os.path.abspath(args.fixtures), os.path.join(os.path.abspath(args.work), "old"),
              args.path_extra)
    new = Ctx(os.path.abspath(args.new_probe), os.path.abspath(args.cpp),
              os.path.abspath(args.fixtures), os.path.join(os.path.abspath(args.work), "new"),
              args.path_extra)

    old_cases = collect(old, "old")
    new_cases = collect(new, "new")

    expectations = {
        "swap": (False, True),      # old stored other bytes, new keeps the identity
        "intent_stage_suffix": ("ok", "corrupt_intent"),
        "intent_bad_number": ("ok", "corrupt_intent"),
        "intent_duplicate_field": ("ok", "corrupt_intent"),
        "intent_unknown_field": ("ok", "corrupt_intent"),
        "intent_overflow_id": ("ok", "corrupt_intent"),
        "intent_oversized_prefix": ("ok", "corrupt_intent"),
    }
    failures = []
    detail = {}
    for name, (old_want, new_want) in expectations.items():
        old_case, new_case = old_cases[name], new_cases[name]
        key = "stored_matches_identity" if name == "swap" else "status"
        detail[name] = {"old": old_case, "new": new_case}
        if old_case[key] != old_want:
            failures.append("%s: the previous build did not show the defect (%r != %r)" % (
                name, old_case[key], old_want))
        if new_case[key] != new_want:
            failures.append("%s: the current build is wrong (%r != %r)" % (
                name, new_case[key], new_want))
        if not new_case.get("databases_unchanged", True):
            failures.append("%s: refused record still changed a database" % name)
        if name == "swap" and new_case["status"] != "ok":
            failures.append("swap: the current build refused a valid reimport")

    report = {
        "ok": not failures,
        "source": os.environ.get("GITHUB_SHA", ""),
        "run": os.environ.get("GITHUB_RUN_ID", ""),
        "attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        "os": os.environ.get("RUNNER_OS", sys.platform),
        "old_probe_sha256": sha256_file(args.old_probe),
        "new_probe_sha256": sha256_file(args.new_probe),
        "previous_implementation": "apps/reader/local-downloads at the previously tested source",
        "cases": detail,
        "failures": failures,
    }
    if not os.path.isdir(args.output):
        os.makedirs(args.output)
    with open(os.path.join(args.output, "regressions.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, indent=1, sort_keys=True)
    print("regressions ok=%s old=%s new=%s" % (
        report["ok"], report["old_probe_sha256"][:12], report["new_probe_sha256"][:12]))
    for name in sorted(detail):
        print("case %s old=%s new=%s" % (name,
            detail[name]["old"].get("stored_matches_identity", detail[name]["old"].get("status")),
            detail[name]["new"].get("stored_matches_identity", detail[name]["new"].get("status"))))
    for failure in failures:
        print("FAIL " + failure)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
