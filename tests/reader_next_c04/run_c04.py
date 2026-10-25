#!/usr/bin/env python3
"""Run the unchanged F5 consumer and expectations on the two pinned real RTF files.

The F5 runner, consumer and manifest come from the fixed F5 checkout; nothing
here replaces a file, a query or an expectation. `fetch` downloads and verifies
the original bytes once; `run` executes one SDK's consumer on exactly those
bytes; `compare` joins the unmodified-SDK run with the candidate run.
"""
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

RTF_IDS = ("rtf-crowley-policy", "rtf-micro-republics")


def load_f5(f5):
    path = Path(f5) / "tests/reader_real_corpus/run_acceptance.py"
    spec = importlib.util.spec_from_file_location("f5_run_acceptance", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = module.load_manifest(Path(f5) / "tests/reader_real_corpus/manifest.json")
    entries = [e for e in manifest["files"] if e["id"] in RTF_IDS]
    if [e["id"] for e in entries] != list(RTF_IDS):
        raise SystemExit("F5 manifest does not contain exactly the two RTF entries")
    return module, entries


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cmd_fetch(args):
    module, entries = load_f5(args.f5)
    root = Path(args.out)
    records = module.download_manifest({"files": entries}, root, "collect")
    bad = [r for r in records if r["status"] != "verified"]
    print(json.dumps(records, indent=2))
    return 1 if bad else 0


def cmd_run(args):
    module, entries = load_f5(args.f5)
    corpus, root = Path(args.corpus), Path(args.out)
    root.mkdir(parents=True, exist_ok=True)
    records = []
    for entry in entries:
        source = corpus / entry["path"]
        if not source.is_file() or source.stat().st_size != entry["source"]["bytes"] or \
                sha256_file(source) != entry["source"]["sha256"]:
            raise SystemExit("%s: corpus bytes differ from the pinned original" % entry["id"])
        record = module.run_one(dict(entry, path=str(source)), root, Path(args.consumer),
                                Path(args.font), args.timeout)
        record["input_sha256"] = sha256_file(source)
        records.append(record)
        print("[%s] %s %s" % (args.label, entry["id"], record["status"]), flush=True)
    summary = {
        "schema": 1, "label": args.label, "sdk_stage": args.stage_name,
        "consumer_sha256": sha256_file(args.consumer), "font_sha256": sha256_file(args.font),
        "accepted": all(r["status"] == "accepted" for r in records),
        "files": records,
    }
    Path(args.summary).write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("label", "accepted")}))
    if args.label == "candidate":
        return 0 if summary["accepted"] else 1
    return 0


def brief(record):
    result = record.get("result") or {}
    detail = result.get("detail") or {}
    return {
        "status": record["status"], "exit_code": record["exit_code"], "ops": result.get("ops"),
        "mismatches": record.get("mismatches"), "errors": record.get("errors"),
        "import_error": detail.get("import_error"), "open_error": detail.get("open_error"),
        "pages": detail.get("pages"), "reopen_pages": detail.get("reopen_pages"),
        "title": detail.get("title"), "find": detail.get("find"),
        "anchor_state_same": detail.get("anchor_state_same"),
        "anchor_state_reopen": detail.get("anchor_state_reopen"),
        "readback_verified": record.get("readback_verified"),
        "input_sha256": record.get("input_sha256"),
        "first_render": detail.get("first"), "middle_render": detail.get("middle"),
        "last_render": detail.get("last"), "seconds": record.get("seconds"),
        "timings_ms": result.get("timings_ms"),
    }


def cmd_compare(args):
    base = json.loads(Path(args.base).read_text(encoding="utf-8"))
    cand = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
    rows = {}
    for b in base["files"]:
        rows.setdefault(b["id"], {})["base"] = brief(b)
    for c in cand["files"]:
        rows.setdefault(c["id"], {})["candidate"] = brief(c)
    same_input = all(r.get("base", {}).get("input_sha256") == r.get("candidate", {}).get("input_sha256")
                     for r in rows.values())
    out = {
        "schema": 1, "same_input_bytes": same_input,
        "base_accepted": base["accepted"], "candidate_accepted": cand["accepted"],
        "base_consumer_sha256": base["consumer_sha256"], "candidate_consumer_sha256": cand["consumer_sha256"],
        "files": rows,
        "performance_note": "timings are single observations from one run and are not a budget result",
    }
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("same_input_bytes", "base_accepted", "candidate_accepted")}))
    return 0 if same_input and cand["accepted"] else 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--f5", required=True)
    f.add_argument("--out", required=True)
    f.set_defaults(func=cmd_fetch)
    r = sub.add_parser("run")
    r.add_argument("--f5", required=True)
    r.add_argument("--corpus", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--summary", required=True)
    r.add_argument("--consumer", required=True)
    r.add_argument("--font", required=True)
    r.add_argument("--label", choices=("base", "candidate"), required=True)
    r.add_argument("--stage-name", default="")
    r.add_argument("--timeout", type=int, default=600)
    r.set_defaults(func=cmd_run)
    c = sub.add_parser("compare")
    c.add_argument("--base", required=True)
    c.add_argument("--candidate", required=True)
    c.add_argument("--out", required=True)
    c.set_defaults(func=cmd_compare)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
