#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Cloud guard: the tested commit is this run's commit, descends from the fixed
# implementation start, keeps the protected SDK tree and the product schema
# identical, and only changes this package's own files.
set -euo pipefail
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
git merge-base --is-ancestor "$START_SHA" HEAD
git diff --exit-code "$FROZEN_SDK" HEAD -- src include cmake CMakeLists.txt tests/fixtures bindings \
  .github/workflows/native.yml .github/workflows/reliability.yml
git diff --exit-code "$START_SHA" HEAD -- apps/reader/store
outside=$(git diff --name-only "$START_SHA" HEAD | grep -v -E \
  '^(tests/reader_distribution_inventory/|\.github/workflows/reader-distribution-inventory\.yml$|docs/READER-DISTRIBUTION-INVENTORY\.md$|docs/validation/reader-distribution-inventory\.json$)' || true)
if [ -n "$outside" ]; then
  echo "changes outside the distribution inventory package:"
  echo "$outside"
  exit 1
fi
echo "scope: start $START_SHA, frozen SDK $FROZEN_SDK, product schema unchanged, package-only changes"
