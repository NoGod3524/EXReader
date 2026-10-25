#!/usr/bin/env bash
set -euo pipefail
test "$GITHUB_ACTIONS" = true
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
start=a826a65c9c66e43620eff61b49cb79f941a3c953
sdk=9854061be331fe603a1822d9b2b36ee357154927
git merge-base --is-ancestor "$start" HEAD
git diff --exit-code "$sdk" HEAD -- src include cmake CMakeLists.txt tests/fixtures bindings .github/workflows/native.yml .github/workflows/reliability.yml
outside=$(git diff --name-only "$start" HEAD | grep -v -E '^(extras/android-reader-display/|tests/reader_android_display/|\.github/workflows/reader-android-display\.yml$|docs/READER-ANDROID-DISPLAY\.md$|docs/validation/reader-android-display\.json$)' || true)
test -z "$outside" || { echo "Out of scope: $outside"; exit 1; }
# This path guard also protects all schema/wire/host files, not just SDK paths.
if grep -R -nE 'android\.provider\.Settings|PowerManager|WakeLock|WRITE_SETTINGS|<service|<uses-permission|startService|startForegroundService|SharedPreferences|SQLite|java\.net' extras/android-reader-display/display/src; then
  echo 'forbidden Android capability'; exit 1
fi
echo "scope passed: fixed start, exact HEAD, frozen SDK and entire non-D05 tree"
