#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Cloud guard: the tested commit is this run's commit, descends from the fixed
# implementation start, keeps the protected SDK tree, the product schema and every
# licence original identical, and only adds this package's own files.
set -euo pipefail
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
git merge-base --is-ancestor "$START_SHA" HEAD
git diff --exit-code "$FROZEN_SDK" HEAD -- src include cmake CMakeLists.txt tests/fixtures bindings \
  .github/workflows/native.yml .github/workflows/reliability.yml
git diff --exit-code "$START_SHA" HEAD -- apps/reader/store
# This package only adds manifests and checks: no licence original may change.
git diff --exit-code "$START_SHA" HEAD -- licenses LICENSE THIRD_PARTY_NOTICES.md tools/check_reading_licenses.py \
  tests/reader_distribution_inventory
outside=$(git diff --name-only "$START_SHA" HEAD | grep -v -E \
  '^(tests/reader_final_s09/|\.github/workflows/reader-final-s09\.yml$|docs/reader-final-s09/|HANDOFF-RESULT\.md$)' || true)
if [ -n "$outside" ]; then
  echo "changes outside the final distribution closure package:"
  echo "$outside"
  exit 1
fi
echo "scope: start $START_SHA, frozen SDK $FROZEN_SDK, licence originals and product schema unchanged"
