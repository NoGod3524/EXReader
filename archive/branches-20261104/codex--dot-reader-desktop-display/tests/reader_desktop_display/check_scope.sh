#!/usr/bin/env bash
set -euo pipefail
test "${GITHUB_ACTIONS:-}" = true
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
git merge-base --is-ancestor a826a65c9c66e43620eff61b49cb79f941a3c953 HEAD
git diff --exit-code 9854061be331fe603a1822d9b2b36ee357154927 HEAD -- src include cmake CMakeLists.txt tests/fixtures bindings .github/workflows/native.yml .github/workflows/reliability.yml
outside=$(git diff --name-only a826a65c9c66e43620eff61b49cb79f941a3c953 HEAD | grep -v -E '^(extras/desktop-reader-display/|tests/reader_desktop_display/|\.github/workflows/reader-desktop-display\.yml$|docs/READER-DESKTOP-DISPLAY\.md$|docs/validation/reader-desktop-display\.json$)' || true)
test -z "$outside" || { printf '%s\n' "$outside"; exit 1; }
# The whitelist freezes every host, product schema, wire/anchor and original workflow.
echo "D07 source $GITHUB_SHA: fixed-start ancestry, SDK 3.40 and all non-owned paths frozen"
