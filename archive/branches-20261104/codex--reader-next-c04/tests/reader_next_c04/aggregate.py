#!/usr/bin/env python3
"""Join the guard, diagnostic and two platform artifacts of one C04 run.

The result is always `accepted: false`: the patched SDK is an unaccepted
candidate. `candidate_checks_passed` only says that every named check below
held for this run and attempt; final acceptance belongs to the root.
"""
import argparse
import json
import sys
from pathlib import Path


def read_kv(path):
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


def first(root, name):
    found = sorted(root.rglob(name))
    return found[0] if found else None


def int_file(path):
    return int(Path(path).read_text().strip()) if path else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    root = Path(args.dir)
    checks, platforms = [], {}

    def check(name, ok, detail=None):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    guard_file = first(root, "guard.json")
    guard = json.loads(guard_file.read_text(encoding="utf-8")) if guard_file else None
    check("guard.present_and_ok", guard and guard.get("ok"), guard and guard.get("problems"))
    diag = sorted(root.glob("*diagnose*"))
    check("diagnose.artifact_present", len(diag) == 1 and first(diag[0], "scan.json") is not None)

    for key in ("windows-latest", "ubuntu-22.04"):
        dirs = [d for d in root.iterdir() if d.is_dir() and key in d.name]
        if len(dirs) != 1:
            check("%s.artifact_unique" % key, False, [d.name for d in dirs])
            continue
        d = dirs[0]
        identity = read_kv(d / "identity.txt") if (d / "identity.txt").exists() else {}
        compare_file = d / "compare.json"
        compare = json.loads(compare_file.read_text(encoding="utf-8")) if compare_file.exists() else {}
        scan = json.loads((d / "scan.json").read_text(encoding="utf-8")) if (d / "scan.json").exists() else {}
        platforms[key] = {"artifact": d.name, "identity": identity, "compare_present": bool(compare),
                          "scan_sha256": {n: v.get("sha256") for n, v in scan.get("files", {}).items()}}
        check(key + ".same_input_bytes", compare.get("same_input_bytes") is True)
        check(key + ".candidate_real_files_accepted", compare.get("candidate_accepted") is True)
        check(key + ".ctest_exit_0", int_file(first(d, "ctest.exit")) == 0)
        check(key + ".boundary_candidate_exit_0", int_file(first(d, "boundary-cand.exit")) == 0)
        files = compare.get("files", {})
        check(key + ".both_real_files_present", sorted(files) == ["rtf-crowley-policy", "rtf-micro-republics"])
        platforms[key]["base_status"] = {i: (r.get("base") or {}).get("status") for i, r in files.items()}
        platforms[key]["candidate_status"] = {i: (r.get("candidate") or {}).get("status") for i, r in files.items()}
        platforms[key]["unmodified_boundary_exit"] = int_file(first(d, "boundary-base.exit"))
        platforms[key]["candidate_diff_files"] = identity.get("cand_diff_files", "").split()
        check(key + ".candidate_touches_only_rtf_c", identity.get("cand_diff_files", "").split() == ["src/rtf.c"])

    if len(platforms) == 2:
        a, b = platforms["windows-latest"]["identity"], platforms["ubuntu-22.04"]["identity"]
        for field in ("branch_sha", "sdk_sha", "f5_sha", "patch_sha256", "base_rtf_c_sha256",
                      "cand_rtf_c_sha256", "base_src_tree", "cand_src_tree", "run_id", "attempt"):
            check("same_" + field, a.get(field) and a.get(field) == b.get(field), [a.get(field), b.get(field)])
        check("same_input_hashes", platforms["windows-latest"]["scan_sha256"] == platforms["ubuntu-22.04"]["scan_sha256"])

    result = {
        "schema": 1, "accepted": False,
        "meaning": "unaccepted SDK candidate; candidate_checks_passed only reports this run's named checks",
        "candidate_checks_passed": all(c["ok"] for c in checks),
        "checks": checks, "platforms": platforms, "guard": guard,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"candidate_checks_passed": result["candidate_checks_passed"],
                      "failed": [c["name"] for c in checks if not c["ok"]]}, indent=2))
    return 0 if result["candidate_checks_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
