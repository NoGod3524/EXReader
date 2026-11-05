#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Cloud guard: the tested commit is this run's commit, descends from the fixed
# implementation start, changes nothing in the protected SDK tree, the product schema
# or any licence original, and only adds this package's own files.
set -euo pipefail
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
git merge-base --is-ancestor "$START_SHA" HEAD
git merge-base --is-ancestor "$FROZEN_SDK" HEAD
# The frozen 3.40 SDK is an ancestor here, not an equal tree: the shared source moved on
# after it (3.41 candidates and host work by their owners). What this package must prove
# is that it changes none of it and inherits exactly the same delta as its start commit.
git diff --exit-code "$START_SHA" HEAD -- src include cmake CMakeLists.txt tests/fixtures bindings \
  .github/workflows/native.yml .github/workflows/reliability.yml
test "$(git diff --name-only "$FROZEN_SDK" "$START_SHA" -- src include cmake CMakeLists.txt | sort)" = \
     "$(git diff --name-only "$FROZEN_SDK" HEAD -- src include cmake CMakeLists.txt | sort)"
git diff --exit-code "$START_SHA" HEAD -- apps/reader/store
# This package only adds manifests and checks: no licence original or generator may change.
git diff --exit-code "$START_SHA" HEAD -- licenses LICENSE THIRD_PARTY_NOTICES.md \
  tools/check_reading_licenses.py tests/reader_distribution_inventory
outside=$(git diff --name-only "$START_SHA" HEAD | grep -v -E \
  '^(tests/reader_final_s09/|\.github/workflows/reader-final-s09\.yml$|docs/reader-final-s09/|HANDOFF-RESULT\.md$)' || true)
if [ -n "$outside" ]; then
  echo "changes outside the final distribution closure package:"
  echo "$outside"
  exit 1
fi
echo "scope: start $START_SHA, frozen SDK $FROZEN_SDK inherited unchanged, licence originals and product schema unchanged"
