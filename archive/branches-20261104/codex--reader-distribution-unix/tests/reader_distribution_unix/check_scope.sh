#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Cloud guard: the tested commit is this run's commit, descends from the fixed
# implementation start f43baf9, keeps the protected SDK tree and the product
# schema identical, and only changes this package's own files.
set -euo pipefail
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
git merge-base --is-ancestor "$START_SHA" HEAD
git diff --exit-code "$FROZEN_SDK" HEAD -- src include cmake CMakeLists.txt tests/fixtures bindings \
  .github/workflows/native.yml .github/workflows/reliability.yml
git diff --exit-code "$START_SHA" HEAD -- apps/reader/store
outside=$(git diff --name-only "$START_SHA" HEAD | grep -v -E \
  '^(tools/reader_distribution_unix/|tests/reader_distribution_unix/|\.github/workflows/reader-distribution-unix\.yml$|docs/READER-DISTRIBUTION-UNIX\.md$|docs/validation/reader-distribution-unix\.json$)' || true)
if [ -n "$outside" ]; then
  echo "changes outside the distribution-unix package:"
  echo "$outside"
  exit 1
fi
python3 -m py_compile tools/reader_distribution_unix/contract.py tools/reader_distribution_unix/stage.py \
  tools/reader_distribution_unix/transform.py tools/reader_distribution_unix/audit.py \
  tools/reader_distribution_unix/seal.py tests/reader_distribution_unix/compare.py \
  tests/reader_distribution_unix/selfcheck.py
echo "scope: start $START_SHA, frozen SDK $FROZEN_SDK, product schema unchanged, package-only changes"
