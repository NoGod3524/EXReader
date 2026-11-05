#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
test "$GITHUB_ACTIONS" = true
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
base=37fdc830d75eee8590120d52d4d881102e0d9dc4
sdk=9854061be331fe603a1822d9b2b36ee357154927
git merge-base --is-ancestor "$base" HEAD
changed=$(git diff --name-only "$base" HEAD)
printf '%s\n' "$changed"
bad=$(printf '%s\n' "$changed" | grep -v -E '^(apps/reader/conflict-actions/|tests/reader_explicit_conflict_actions/|\.github/workflows/reader-explicit-conflict-actions\.yml$|docs/READER-EXPLICIT-CONFLICT-ACTIONS\.md$|docs/validation/reader-explicit-conflict-actions\.json$|$)' || true)
test -z "$bad" || { printf 'path outside allowed set:\n%s\n' "$bad"; exit 1; }
git diff --exit-code "$sdk" HEAD -- src include cmake CMakeLists.txt tests/fixtures bindings .github/workflows/native.yml .github/workflows/reliability.yml
git diff --exit-code "$base" HEAD -- apps/reader/store apps/reader/revisions apps/reader/commands apps/reader/desktop-metadata extras
