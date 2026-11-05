#!/usr/bin/env python3
"""Join the guard, diagnostic and two platform artifacts of one C04 run.

The result is always `accepted: false`: the patched SDK is an unaccepted
candidate. `candidate_checks_passed` only says that every named check below
held for this run and attempt; final acceptance belongs to the root.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import sys
from pathlib import Path, PurePosixPath
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip


def authenticate(root):
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    run, attempt, source = os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT'], os.environ['GITHUB_SHA']
    metadata = fetch(f'actions/runs/{run}/attempts/{attempt}')
    assert metadata['head_sha'] == source and metadata['path'].split('@')[0] == '.github/workflows/reader-next-c04.yml'
    upstream = {'guard', 'diagnose',
                'acceptance (ubuntu-22.04, python3, /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf)',
                'acceptance (windows-latest, python, C:/Windows/Fonts/arial.ttf, .exe, Release/)'}
    jobs = fetch(f'actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')['jobs']
    selected = [row for row in jobs if row['name'] in upstream]
    assert len(selected) == 4 and {row['name'] for row in selected} == upstream
    assert all(row['head_sha'] == source and row['status'] == 'completed' and row['conclusion'] == 'success' for row in selected)
    names = {f'reader-next-c04-{part}-{run}-{attempt}' for part in ('guard', 'diagnose', 'ubuntu-22.04', 'windows-latest')}
    artifacts = fetch(f'actions/runs/{run}/artifacts?per_page=100')['artifacts']
    assert len(artifacts) == 4 and {row['name'] for row in artifacts} == names
    evidence = {'run_id': int(run), 'attempt': int(attempt), 'source_sha': source,
                'jobs': [{key: row[key] for key in ('id', 'name', 'conclusion', 'head_sha')} for row in selected], 'artifacts': []}
    for artifact in artifacts:
        assert not artifact['expired'] and artifact['workflow_run']['head_sha'] == source and artifact['workflow_run']['id'] == int(run)
        assert datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
        body = download_artifact_zip(artifact['id'])
        assert len(body) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(body).hexdigest() == artifact['digest']
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            entries = archive.namelist()
            assert len(entries) == len(set(entries)) and len(entries) <= 1000
            assert sum(item.file_size for item in archive.infolist()) <= 64 * 1024 * 1024
            for name in entries:
                path = PurePosixPath(name)
                assert not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name
                if not name.endswith('/'):
                    assert (root / artifact['name'] / name).read_bytes() == archive.read(name)
        evidence['artifacts'].append({key: artifact[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
    return evidence


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
    authentication = authenticate(root)
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
        for ident in ('rtf-crowley-policy', 'rtf-micro-republics'):
            for variant in ('base', 'cand'):
                probe = json.loads((d / f'original-{variant}-{ident}.json').read_text(encoding='utf-8'))
                check(f'{key}.{variant}.{ident}.exact_public_status',
                      probe['test'] == 'original-public-open' and probe['status'] == probe['expected'] and
                      probe['document'] == (variant == 'cand') and
                      probe['status'] == (0 if variant == 'cand' else 5), probe)
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
                      "cand_rtf_c_sha256", "base_sdk_tree", "cand_sdk_tree", "base_src_tree", "cand_src_tree", "run_id", "attempt"):
            check("same_" + field, a.get(field) and a.get(field) == b.get(field), [a.get(field), b.get(field)])
        check("same_input_hashes", platforms["windows-latest"]["scan_sha256"] == platforms["ubuntu-22.04"]["scan_sha256"])

    result = {
        "schema": 1, "accepted": False,
        "meaning": "unaccepted SDK candidate; candidate_checks_passed only reports this run's named checks",
        "authentication": authentication,
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
