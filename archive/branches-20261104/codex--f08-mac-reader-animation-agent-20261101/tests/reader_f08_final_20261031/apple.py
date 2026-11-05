"""Run the unchanged full Apple cohorts from the final admitted source."""
import argparse
import importlib.util
import json
import os
import sys

from source import ROOT, admission, need

LEGACY = ROOT / "tests/reader_f08_apple_20261031"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = load("final_apple_run", LEGACY / "run.py")
R.guard = admission


def sdk(target):
    admitted = admission()
    builder = load("final_apple_sdk", ROOT / "tests/apple_sdk342_host/build.py")
    # Admission has already frozen production and build recipes. The original
    # builder now compiles this HEAD and records it as its SDK content source.
    builder.SDK_SOURCE = admitted["source_sha"]
    previous = sys.argv
    try:
        sys.argv = [str(builder.__file__), "--target", target]
        builder.main()
    finally:
        sys.argv = previous


def audit():
    # The original audit imports helpers from a module literally named "run".
    previous = sys.modules.get("run")
    sys.modules["run"] = R
    try:
        replay = load("final_apple_audit", LEGACY / "audit.py")
    finally:
        if previous is None:
            sys.modules.pop("run", None)
        else:
            sys.modules["run"] = previous
    need(replay.guard is admission, "final Apple audit admission binding")
    replay.main()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("guard", "sdk", "native", "seal", "audit"))
    parser.add_argument("--target", choices=("macos", "iphonesimulator"))
    parser.add_argument("--platform", choices=("macos", "iphone", "ipad", "macos-sdk", "iphonesimulator-sdk"))
    args = parser.parse_args()
    need((args.target is not None) == (args.mode == "sdk"), "SDK target")
    need((args.platform is not None) == (args.mode in ("native", "seal")), "native/seal platform")
    admitted = admission()
    if args.mode == "guard":
        print(json.dumps(admitted))
    elif args.mode == "sdk":
        sdk(args.target)
    elif args.mode == "native":
        need(args.platform in ("macos", "iphone", "ipad"), "native target")
        need(os.environ.get("F08_APPLE_DIAGNOSTIC", "").lower() != "true", "full original Apple cohorts required")
        R.native(args.platform)
    elif args.mode == "seal":
        R.seal(args.platform)
    else:
        audit()


if __name__ == "__main__":
    main()
