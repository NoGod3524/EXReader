#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Cloud guard: the tested commit is this run's commit, it descends from the fixed
# start, the frozen SDK and every path outside this package are unchanged, the
# component does not log or print, and the default build never adds it.
set -euo pipefail
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
git merge-base --is-ancestor "$START_SHA" HEAD
git diff --exit-code "$FROZEN_SDK" HEAD -- src include cmake CMakeLists.txt tests/fixtures bindings \
  .github/workflows/native.yml .github/workflows/reliability.yml
outside=$(git diff --name-only "$START_SHA" HEAD | grep -v -E \
  '^(extras/reader-tts-windows/|tests/reader_tts_windows/|\.github/workflows/reader-tts-windows\.yml$|docs/READER-TTS-WINDOWS\.md$|docs/validation/reader-tts-windows\.json$)' || true)
if [ -n "$outside" ]; then
  echo "changes outside the Windows TTS package:"; echo "$outside"; exit 1
fi
if grep -rnE '(^|[^A-Za-z0-9_])(printf|fprintf|puts|perror|OutputDebugString[AW]?)[[:space:]]*\(' \
    extras/reader-tts-windows/src extras/reader-tts-windows/include; then
  echo "module sources must not print or log"; exit 1
fi
if grep -rn 'reader_tts\|reader-tts' CMakeLists.txt cmake; then
  echo "default build must not include the Windows TTS component"; exit 1
fi
echo "scope: fixed start $START_SHA, frozen SDK $FROZEN_SDK, package-only changes, no module output"
