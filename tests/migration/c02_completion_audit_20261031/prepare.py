#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only explicit qualification manifest selection; no ZIP operations."""
import argparse
import json
import os
import pathlib
import subprocess
import sys

from protocols import need, hexadecimal, json_value, sha

def main():
    need(os.environ.get("GITHUB_ACTIONS")=="true", "actions-only-manifest-selection")
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",required=True)
    parser.add_argument("--scope",choices=("windows-components","complete-c02"),required=True)
    parser.add_argument("--output",type=pathlib.Path,required=True)
    args=parser.parse_args()
    need(hexadecimal(args.source,40), "explicit-full-producer-sha")
    audit_sha=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    need(audit_sha==os.environ["GITHUB_SHA"], "audit-code-exact-candidate-sha")
    source=subprocess.check_output(["git","rev-parse",args.source+"^{commit}"],text=True).strip()
    need(source==args.source, "producer-source-git-object")
    supplied=os.environ.get("QUALIFICATION_JSON","").strip()
    if args.scope=="windows-components":
        preset=pathlib.Path(__file__).with_name("qualification.windows-faae.json")
        raw=preset.read_bytes()
        manifest=json_value(raw)
        need(not supplied and manifest["source"]==source, "fixed-original-windows-components-only")
    else:
        need(supplied, "complete-mode-requires-explicit-qualification-manifest")
        manifest=json_value(supplied)
        need(manifest["source"]==source, "explicit-complete-source-binding")
        roles={item["role"] for item in manifest["packages"]}
        need(roles=={"native-windows","native-linux","persistent-gate","registry-product",
                     "host-android","host-macos","host-gtk"}, "complete-mode-all-platform-packages")
    need(manifest["schema"]==1 and manifest["repository"]=="NoGod3524/EXReader" and
         manifest["repository"]==os.environ["GITHUB_REPOSITORY"], "qualification-repository")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(manifest,indent=2)+"\n")
    receipt=dict(audit_code_sha=audit_sha,producer_source=source,scope=args.scope,
                 full_c02_claim_requested=args.scope=="complete-c02",
                 qualification_sha256=sha(args.output.read_bytes()))
    args.output.with_name("preparation.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps(receipt),flush=True)
    return 0

if __name__=="__main__":
    sys.exit(main())
