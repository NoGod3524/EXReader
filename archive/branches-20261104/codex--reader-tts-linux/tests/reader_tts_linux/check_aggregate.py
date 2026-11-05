#!/usr/bin/env python3
"""Rejection regressions for the J19 aggregation rules.

Every rule that protects the same-run evidence is exercised twice: once with a
sound fixture (must be accepted) and once with a mutated fixture (must be
rejected). Runs offline inside Actions; no artifact is downloaded here.
"""
import argparse
import copy
import hashlib
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aggregate  # noqa: E402

SOURCE = "0123456789abcdef0123456789abcdef01234567"
RUN_ID = "1234567890"
ATTEMPT = "2"


def make_payload(expected):
    cases = []
    for phase, names in expected.items():
        for name in names:
            cases.append({"name": name, "phase": phase, "status": "pass",
                          "detail": "fixture evidence for %s" % name})
    return {
        "schema": 1,
        "package": "J19-reader-tts-linux",
        "source_sha": SOURCE,
        "run_id": int(RUN_ID),
        "run_attempt": int(ATTEMPT),
        "env": {
            "socket": "/run/user/1001/speech-dispatcher/speechd.sock",
            "binaries": {"reader-tts-consumer": {"sha256": "a" * 64, "bytes": 1234}},
            "libspeechd_header_sha256": "b" * 64,
        },
        "counts": {"pass": len(cases), "fail": 0, "skip": 0, "other": 0},
        "cases": cases,
        "problems": [],
        "accepted": True,
    }


def make_meta(name):
    return {
        "id": 42,
        "name": name,
        "size_in_bytes": 2048,
        "digest": "sha256:" + "c" * 64,
        "expired": False,
        "expires_at": "2026-12-31T00:00:00Z",
        "created_at": "2026-10-24T00:00:00Z",
        "workflow_run": {"id": int(RUN_ID), "head_sha": SOURCE},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--expected", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    with open(args.expected) as f:
        expected = json.load(f)["phases"]
    name = "reader-tts-linux-ubuntu-2204-release-r%s-a%s-%s" % (RUN_ID, ATTEMPT, SOURCE)

    results = []

    def record(label, problems, want_clean):
        clean = not problems
        ok = clean if want_clean else not clean
        results.append({"case": label, "ok": ok, "problems": problems[:4]})
        print("%s %s%s" % ("pass" if ok else "FAIL", label,
                           "" if ok else ": " + "; ".join(problems[:3])))

    def check_payload(label, mutate, want_clean):
        payload = make_payload(expected)
        mutate(payload)
        record(label, aggregate.verify_payload(payload, expected, SOURCE, RUN_ID, ATTEMPT),
               want_clean)

    def check_meta(label, mutate, want_clean):
        meta = make_meta(name)
        mutate(meta)
        record(label, aggregate.verify_artifact_meta(meta, name, SOURCE, RUN_ID, ATTEMPT),
               want_clean)

    record("accept_clean_payload",
           aggregate.verify_payload(make_payload(expected), expected, SOURCE, RUN_ID, ATTEMPT), True)
    record("accept_clean_artifact", aggregate.verify_artifact_meta(make_meta(name), name, SOURCE,
                                                                  RUN_ID, ATTEMPT), True)

    check_payload("reject_not_accepted", lambda p: p.update(accepted=False), False)
    check_payload("reject_declared_problem", lambda p: p["problems"].append("boom"), False)
    check_payload("reject_failing_case",
                  lambda p: p["counts"].__setitem__("fail", 1), False)
    check_payload("reject_skipped_case",
                  lambda p: p["counts"].__setitem__("skip", 1), False)
    check_payload("reject_other_status",
                  lambda p: p["counts"].__setitem__("other", 1), False)
    check_payload("reject_missing_case", lambda p: p["cases"].pop(), False)
    check_payload("reject_duplicate_case", lambda p: p["cases"].append(dict(p["cases"][0])), False)
    check_payload("reject_unexpected_case",
                  lambda p: p["cases"].append({"name": "not_planned", "phase": "live",
                                               "status": "pass", "detail": "x"}), False)
    check_payload("reject_empty_detail",
                  lambda p: p["cases"][0].__setitem__("detail", ""), False)
    check_payload("reject_cross_source",
                  lambda p: p.update(source_sha="f" * 40), False)
    check_payload("reject_cross_run", lambda p: p.update(run_id=int(RUN_ID) + 1), False)
    check_payload("reject_cross_attempt", lambda p: p.update(run_attempt=int(ATTEMPT) + 1), False)
    check_payload("reject_missing_socket", lambda p: p["env"].pop("socket"), False)
    check_payload("reject_missing_binaries", lambda p: p["env"].pop("binaries"), False)
    check_payload("reject_missing_header_digest", lambda p: p["env"].pop("libspeechd_header_sha256"),
                  False)
    check_payload("reject_failing_case_status",
                  lambda p: p["cases"][0].__setitem__("status", "fail"), False)

    check_meta("reject_expired", lambda m: m.update(expired=True), False)
    check_meta("reject_zero_bytes", lambda m: m.update(size_in_bytes=0), False)
    check_meta("reject_malformed_digest", lambda m: m.update(digest="sha256:abc"), False)
    check_meta("reject_missing_digest", lambda m: m.pop("digest"), False)
    check_meta("reject_cross_run_artifact", lambda m: m["workflow_run"].update(id=1), False)
    check_meta("reject_cross_sha_artifact", lambda m: m["workflow_run"].update(head_sha="e" * 40),
               False)
    check_meta("reject_name_without_attempt",
               lambda m: m.update(name="reader-tts-linux-ubuntu-2204-release"), False)
    check_meta("reject_missing_expiry", lambda m: m.pop("expires_at"), False)

    good_zip = b"PK" + b"x" * 100
    good_meta = make_meta(name)
    good_meta["size_in_bytes"] = len(good_zip)
    good_meta["digest"] = "sha256:" + hashlib.sha256(good_zip).hexdigest()
    record("accept_clean_zip", aggregate.verify_zip(good_zip, good_meta), True)
    tampered = bytearray(good_zip)
    tampered[-1] ^= 0xFF
    record("reject_tampered_zip", aggregate.verify_zip(bytes(tampered), good_meta), False)
    record("reject_empty_zip", aggregate.verify_zip(b"", good_meta), False)
    short_meta = copy.deepcopy(good_meta)
    short_meta["size_in_bytes"] = len(good_zip) - 1
    record("reject_zip_size_mismatch", aggregate.verify_zip(good_zip, short_meta), False)

    manifest = ["%s  results.json" % ("d" * 64), "%s  logs/live.log" % ("e" * 64)]
    actual = {"results.json": "d" * 64, "logs/live.log": "e" * 64}
    record("accept_clean_manifest", aggregate.verify_file_manifest(manifest, actual), True)

    # artifacts keep the evidence in a directory of its own, next to the logs and
    # the installed prefix; the manifest is relative to that directory.
    packed = {"evidence/results.json": "d" * 64, "evidence/logs/live.log": "e" * 64,
              "evidence/files.sha256": "f" * 64, "pkg-logs/build.log": "1" * 64,
              "stage/lib/libreader_tts.a": "2" * 64}
    prefix = aggregate.evidence_prefix(list(packed))
    record("accept_evidence_prefix", [] if prefix == "evidence" else ["prefix is %r" % prefix], True)
    scoped = aggregate.scope_entries(packed, prefix)
    record("accept_prefixed_manifest", aggregate.verify_file_manifest(manifest, scoped), True)
    record("reject_prefixed_manifest_tamper", aggregate.verify_file_manifest(
        manifest, dict(scoped, **{"logs/live.log": "0" * 64})), False)
    record("reject_flat_manifest_tamper", aggregate.verify_file_manifest(
        ["%s  results.json" % ("0" * 64), manifest[1]], actual), False)
    record("reject_no_evidence_prefix",
           [] if aggregate.evidence_prefix(["pkg-logs/build.log"]) is None
           else ["a stray results.json was accepted"], True)
    record("reject_manifest_digest", aggregate.verify_file_manifest(
        ["%s  results.json" % ("0" * 64), manifest[1]], actual), False)
    record("reject_manifest_extra_entry", aggregate.verify_file_manifest(
        manifest + ["%s  logs/ghost.log" % ("1" * 64)], actual), False)
    record("reject_uncovered_archive_file", aggregate.verify_file_manifest(
        manifest, dict(actual, **{"logs/extra.log": "2" * 64})), False)

    failures = [r for r in results if not r["ok"]]
    os.makedirs(args.output, exist_ok=True)
    with open(os.path.join(args.output, "rejections.json"), "w") as f:
        json.dump({"total": len(results), "failures": len(failures), "results": results}, f,
                  indent=2)
    print("rejection regressions: %d/%d as expected" % (len(results) - len(failures), len(results)))
    return 0 if not failures else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(3)
