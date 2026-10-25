#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Normalise downloaded evidence directories into <target>/ trees.

GitHub artifact upload keeps whatever relative layout the runner produced, so
the matrix compiler must not depend on it. Every directory that contains an
identity.json is a platform evidence root; its identity decides the target name.
"""
import argparse
import json
import os
import shutil
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="downloaded artifact tree")
    parser.add_argument("--output", required=True, help="normalised evidence root")
    args = parser.parse_args()

    found = {}
    for root, _directories, files in os.walk(args.input):
        if "identity.json" not in files:
            continue
        try:
            with open(os.path.join(root, "identity.json"), "r", encoding="utf-8") as handle:
                platform = json.load(handle).get("platform")
        except (OSError, ValueError) as error:
            print("problem: unreadable identity under %s (%s)" % (root, error), file=sys.stderr)
            return 1
        if not platform:
            print("problem: identity under %s names no platform" % root, file=sys.stderr)
            return 1
        if platform in found:
            print("problem: two evidence roots claim platform %s: %s and %s"
                  % (platform, found[platform], root), file=sys.stderr)
            return 1
        found[platform] = root

    if not found:
        print("problem: no identity.json found under %s" % args.input, file=sys.stderr)
        return 1

    if os.path.isdir(args.output):
        shutil.rmtree(args.output)
    os.makedirs(args.output)
    for platform, root in sorted(found.items()):
        shutil.copytree(root, os.path.join(args.output, platform))
        print("evidence %s <- %s" % (platform, root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
