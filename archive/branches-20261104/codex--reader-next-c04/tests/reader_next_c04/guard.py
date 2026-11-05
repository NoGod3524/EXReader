#!/usr/bin/env python3
"""C04 source guard: fixed inputs, owned paths and the single-file candidate patch.

Runs only in CI. It never edits anything; it records the identities the
acceptance relies on and fails when any of them differs.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

START = "e67d87cbeabb2457e0852f681ef0b27b2c0da4d8"
SDK = "edddc463c06ed5731195cdb8f06b2df6dff7699e"
F5 = "278d63691a4c73e7aa932d71a40a5938c5427514"
OWNED = ("candidates/reader-next-c04/", "tests/reader_next_c04/", "docs/reader-next-c04/")
OWNED_FILES = (".github/workflows/reader-next-c04.yml", "HANDOFF-RESULT-C04.md")
PINNED = {
    "rtf-crowley-policy": (63797, "de6126e84aed9fa4204f4f7e84b1da6bedf4ef647479caa6a39befd40e9c5656"),
    "rtf-micro-republics": (36814, "6fb4362622c633fff641dcc50935d52b552bdee669eeaba108914d139bd52b84"),
}


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sdk", required=True)
    ap.add_argument("--f5", required=True)
    ap.add_argument("--patch", default="candidates/reader-next-c04/rtf-root-tail-padding.patch")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    problems = []

    sdk_head, f5_head = git(args.sdk, "rev-parse", "HEAD"), git(args.f5, "rev-parse", "HEAD")
    if sdk_head != SDK:
        problems.append("SDK checkout %s != %s" % (sdk_head, SDK))
    if f5_head != F5:
        problems.append("F5 checkout %s != %s" % (f5_head, F5))

    # Owned paths only, relative to the fixed starting point (needs full history).
    changed = git(".", "diff", "--name-only", START, "HEAD").splitlines()
    foreign = [p for p in changed if not (p.startswith(OWNED) or p in OWNED_FILES)]
    if foreign:
        problems.append("paths outside the C04 exclusive set: %s" % foreign)

    # Branch src/include are the approved SDK source, byte for byte.
    trees = {}
    for sub in ("src", "include"):
        mine = git(".", "rev-parse", "HEAD:" + sub)
        theirs = git(args.sdk, "rev-parse", "HEAD:" + sub)
        trees[sub] = {"branch": mine, "sdk": theirs}
        if mine != theirs:
            problems.append("%s tree differs from the approved SDK" % sub)

    patch = Path(args.patch)
    text = patch.read_text(encoding="utf-8")
    touched = sorted(set(re.findall(r"^\+\+\+ b/(\S+)", text, re.M)))
    if touched != ["src/rtf.c"]:
        problems.append("patch must touch exactly src/rtf.c, touches %s" % touched)

    manifest_path = Path(args.f5) / "tests/reader_real_corpus/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rtf = {e["id"]: e for e in manifest["files"] if e["format"] == "RTF"}
    if set(rtf) != set(PINNED):
        problems.append("F5 RTF entries differ: %s" % sorted(rtf))
    for ident, (size, digest) in PINNED.items():
        src = (rtf.get(ident) or {}).get("source", {})
        if (src.get("bytes"), src.get("sha256")) != (size, digest):
            problems.append("%s pin differs from the handoff" % ident)
        if (rtf.get(ident) or {}).get("expect", {}).get("import") != "ok":
            problems.append("%s expectation was changed" % ident)

    report = {
        "schema": 1, "ok": not problems, "problems": problems,
        "start": START, "sdk": SDK, "f5": F5, "branch_head": git(".", "rev-parse", "HEAD"),
        "trees": trees, "changed_paths": changed,
        "patch": {"path": str(patch), "sha256": sha256(patch), "touched": touched},
        "manifest_sha256": sha256(manifest_path),
        "base_rtf_c_sha256": sha256(Path(args.sdk) / "src/rtf.c"),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
