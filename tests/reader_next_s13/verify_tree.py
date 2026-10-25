#!/usr/bin/env python3
"""S13 workspace and patch identity gates. Git and file reads only.

Verifies that this branch carries nothing but the owned candidate files, that the
fixed start equals the approved SDK source for src/include/cmake, that the
original tests and fixtures are byte-identical, and that the patch is exactly the
declared minimal change to one file.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run import Checks, write_json  # noqa: E402

OWNED = ("candidates/reader-next-s13/", "tests/reader_next_s13/", ".github/workflows/reader-next-s13.yml",
         "docs/reader-next-s13/", "HANDOFF-RESULT-S13.md")
FROZEN = ("src", "include", "cmake", "CMakeLists.txt", "bindings", "apps", "extras", "tools")


def git(*arguments, check=False):
    result = subprocess.run(["git"] + list(arguments), capture_output=True, text=True)
    if check and result.returncode != 0:
        raise SystemExit("git %s failed: %s" % (" ".join(arguments), result.stderr))
    return result


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--sdk", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    patch = manifest["patch"]
    checks = Checks("workspace")

    head = git("rev-parse", "HEAD", check=True).stdout.strip()
    checks.require("head_is_github_source", head == os.environ.get("GITHUB_SHA", head),
                   {"head": head, "github_sha": os.environ.get("GITHUB_SHA")})
    checks.require("base_commit_present", git("cat-file", "-e", args.base + "^{commit}").returncode == 0, {"base": args.base})
    checks.require("approved_sdk_commit_present", git("cat-file", "-e", args.sdk + "^{commit}").returncode == 0, {"sdk": args.sdk})
    checks.require("base_equals_approved_sdk_source",
                   git("diff", "--quiet", args.sdk, args.base, "--", *FROZEN).returncode == 0,
                   {"paths": list(FROZEN)})
    checks.require("frozen_sdk_and_owners_untouched",
                   git("diff", "--quiet", args.sdk, head, "--", *FROZEN).returncode == 0,
                   {"paths": list(FROZEN)})
    originals = ("tests/test_cbz.c", "tests/test_cbz_formats.c", "tests/fixtures", "tests/reading_real",
                 "tools/reading_corpus", ".github/workflows/native.yml", "tests/sdk_components")
    checks.require("original_tests_and_fixtures_untouched",
                   git("diff", "--quiet", args.base, head, "--", *originals).returncode == 0,
                   {"paths": list(originals)})
    changed = [line for line in git("diff", "--name-only", args.base, head).stdout.splitlines() if line]
    unexpected = [path for path in changed if not path.startswith(OWNED)]
    checks.require("only_owned_paths_changed", not unexpected, {"changed": len(changed), "unexpected": unexpected})

    blob = git("rev-parse", args.base + ":src/cbz.c", check=True).stdout.strip()
    checks.require("pre_image_is_fixed_start_blob",
                   git("hash-object", "src/cbz.c").stdout.strip() == blob == patch["target_blob"],
                   {"blob": blob, "declared": patch["target_blob"]})
    checks.require("patch_bytes_are_declared", digest(patch["path"]) == patch["sha256"], {"sha256": digest(patch["path"])})
    checks.require("post_image_bytes_are_declared", digest(patch["post_image"]) == patch["post_sha256"],
                   {"sha256": digest(patch["post_image"])})
    stat = git("apply", "--numstat", patch["path"]).stdout.strip()
    checks.require("patch_is_one_file", len(stat.splitlines()) == 1 and stat.split("\t")[2] == "src/cbz.c", {"numstat": stat})
    checks.require("patch_applies_to_fixed_start", git("apply", "--check", patch["path"]).returncode == 0, {"patch": patch["path"]})
    header = [line for line in Path(patch["path"]).read_text(encoding="utf-8").splitlines() if line.startswith("+++ ")]
    checks.require("patch_targets_only_cbz", header == ["+++ b/src/cbz.c"], {"headers": header})
    payload = checks.payload({"source_sha": head, "base": args.base, "sdk": args.sdk,
                              "patch": patch, "changed_paths": changed})
    write_json(args.out, payload)
    print(json.dumps({"accepted": payload["accepted"], "failed": payload["failed"], "changed": len(changed)}))
    return 0 if payload["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
