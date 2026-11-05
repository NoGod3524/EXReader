#!/usr/bin/env bash
set -euo pipefail
test "${GITHUB_ACTIONS:-}" = true
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
start=a826a65c9c66e43620eff61b49cb79f941a3c953
sdk=9854061be331fe603a1822d9b2b36ee357154927
git merge-base --is-ancestor "$start" HEAD
for path in src include cmake CMakeLists.txt tests/fixtures bindings; do
  test "$(git rev-parse "HEAD:$path")" = "$(git rev-parse "$sdk:$path")"
done
while IFS= read -r path; do
  case "$path" in
    extras/apple-reader-display/*|tests/reader_apple_display/*|.github/workflows/reader-apple-display.yml|docs/READER-APPLE-DISPLAY.md|docs/validation/reader-apple-display.json) ;;
    *) echo "Out-of-scope path: $path"; exit 1;;
  esac
done < <(git diff --name-only "$start" HEAD)
test -z "$(git status --porcelain)"
echo "D06 exact source, fixed ancestor, SDK 3.40 and full exclusive-path guard PASS"
