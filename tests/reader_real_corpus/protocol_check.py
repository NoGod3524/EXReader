#!/usr/bin/env python3
"""Protocol checks for the reader real-corpus package.

These checks exercise manifest validation, expectation comparison, summary
acceptance and cross-platform aggregation with fabricated records only. They do
not download corpus files or invoke the SDK.
"""
import argparse
import copy
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import run_acceptance as rac


def expect_error(manifest, mode="run"):
    try:
        rac.validate_manifest(manifest, mode)
    except rac.CorpusError:
        return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="tests/reader_real_corpus/manifest.json")
    args = parser.parse_args()
    base = rac.load_manifest(args.manifest)
    checks = []

    def check(name, condition):
        checks.append((name, bool(condition)))

    check("manifest accepts the fixed dataset", rac.validate_manifest(base, "pin"))

    bad = copy.deepcopy(base)
    bad["files"][0]["source"]["sha256"] = bad["files"][1]["source"]["sha256"]
    check("duplicate SHA is rejected", expect_error(bad))

    bad = copy.deepcopy(base)
    bad["files"] = [e for e in bad["files"] if e["format"] != "CBZ"]
    check("format below two real files is rejected", expect_error(bad))

    bad = copy.deepcopy(base)
    bad["files"][0]["kind"] = "synthetic"
    check("synthetic file counted as real is rejected", expect_error(bad))

    bad = copy.deepcopy(base)
    bad["files"][0]["source"]["url"] = "http://example.invalid/book.epub"
    check("plain HTTP source is rejected", expect_error(bad))

    bad = copy.deepcopy(base)
    del bad["files"][0]["expect"]["anchor.resolve_reopen"]
    check("missing expectation is rejected", expect_error(bad))

    bad = copy.deepcopy(base)
    bad["files"][0]["source"]["license"]["redistribution"] = False
    check("unconfirmed redistribution is rejected", expect_error(bad))

    bad = copy.deepcopy(base)
    bad["files"][0]["source"]["sha256"] = None
    check("unpinned digest is rejected before execution", expect_error(bad))

    entry = base["files"][0]
    ops = dict(entry["expect"])
    check("matching result passes", not rac.compare_expectations(entry["expect"], {"ops": ops}))
    wrong = dict(ops); wrong["pages.last"] = "failed"
    check("mismatched operation is reported", rac.compare_expectations(entry["expect"], {"ops": wrong}))
    report_expect = {"toc": "report"}
    check("report accepts nonempty", not rac.compare_expectations(report_expect, {"ops": {"toc": "nonempty"}}))
    check("report accepts empty", not rac.compare_expectations(report_expect, {"ops": {"toc": "empty"}}))
    check("report rejects failure", rac.compare_expectations(report_expect, {"ops": {"toc": "failed"}}))

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        consumer = tmp / "consumer"; consumer.write_bytes(b"consumer")
        font = tmp / "font.ttf"; font.write_bytes(b"font")
        fake_args = SimpleNamespace(manifest=args.manifest, consumer=consumer, font=font,
                                    source_commit="0" * 40, run_id="1", attempt="1")
        records = []
        for item in base["files"]:
            records.append({"id": item["id"], "format": item["format"], "status": "accepted",
                            "mismatches": [], "errors": [], "result": {"program": {"sdk_version": "3.40.0", "abi": 1}}})
        summary = rac.summarize(base, records, fake_args)
        check("complete accepted summary passes", summary["accepted"])
        broken = copy.deepcopy(records)
        broken[0]["status"] = "failed"
        check("one failed file rejects the batch", not rac.summarize(base, broken, fake_args)["accepted"])
        pending_manifest = copy.deepcopy(base)
        pending_manifest["pending"] = [{"format": "FB2", "status": "pending", "reason": "no legal source"}]
        check("pending input rejects acceptance", not rac.summarize(pending_manifest, records, fake_args)["accepted"])

        win = copy.deepcopy(summary); win["platform"] = {"system": "Windows"}
        linux = copy.deepcopy(summary); linux["platform"] = {"system": "Linux"}
        win_path, linux_path = tmp / "win.json", tmp / "linux.json"
        win_path.write_text(json.dumps(win)); linux_path.write_text(json.dumps(linux))
        out = tmp / "aggregate.json"
        rc = rac.cmd_aggregate(SimpleNamespace(summaries=[str(win_path), str(linux_path)], out=str(out)))
        check("two-platform aggregate passes", rc == 0 and json.loads(out.read_text())["accepted"])
        only_win = tmp / "only-win.json"
        only_win.write_text(json.dumps(win))
        rc = rac.cmd_aggregate(SimpleNamespace(summaries=[str(win_path), str(only_win)], out=str(out)))
        check("missing Linux summary is rejected", rc != 0)

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(("PASS " if ok else "FAIL ") + name)
    print("%d/%d protocol checks passed" % (len(checks) - len(failed), len(checks)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())