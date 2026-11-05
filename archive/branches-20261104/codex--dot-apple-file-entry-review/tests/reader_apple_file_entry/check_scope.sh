#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Cloud guard: the tested commit descends from the fixed start; the frozen SDK,
# fixtures, sideload module and product schema are byte-identical to it; only
# this package's paths changed; the module stays out of the default build and
# never reads or writes the SDK's private storage.
set -euo pipefail
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
git merge-base --is-ancestor "$START_SHA" HEAD
git diff --exit-code "$FROZEN_SDK" HEAD -- src include cmake CMakeLists.txt tests/fixtures bindings \
  .github/workflows/native.yml .github/workflows/reliability.yml
git diff --exit-code "$START_SHA" HEAD -- extras/sideload apps/reader/store examples/apple tests/apple_host \
  tests/sideload .github/workflows/reader-modules.yml
outside=$(git diff --name-only "$START_SHA" HEAD | grep -v -E \
  '^(extras/apple-file-entry/|tests/reader_apple_file_entry/|\.github/workflows/reader-apple-file-entry\.yml$|docs/READER-APPLE-FILE-ENTRY\.md$|docs/validation/reader-apple-file-entry\.json$)' || true)
if [ -n "$outside" ]; then
  echo "changes outside the Apple file-entry package:"; echo "$outside"; exit 1
fi
if grep -rn -i 'apple-file-entry\|EXRFileEntry' CMakeLists.txt cmake CMakePresets.json; then
  echo "default build must not include the file-entry module"; exit 1
fi
if grep -rn -E '\bsqlite3_|exr_library_open|NSLog\(|print\(' extras/apple-file-entry/Sources; then
  echo "component must not touch SDK storage or log"; exit 1
fi
echo "scope: start $START_SHA, frozen SDK $FROZEN_SDK, package-only changes, sideload/schema/hosts unchanged"
