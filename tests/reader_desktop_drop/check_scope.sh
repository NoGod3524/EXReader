#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Cloud guard for the desktop drop package: the tested commit descends from the
# fixed start, the frozen SDK and every shared path are byte-identical to it,
# only this package's whitelist changed, the module is SDK-free and stays out
# of the default build, and only test/probe programs print.
set -euo pipefail
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
git merge-base --is-ancestor "$START_SHA" HEAD
git diff --exit-code "$FROZEN_SDK" HEAD -- src include cmake CMakeLists.txt tests/fixtures bindings \
  .github/workflows/native.yml .github/workflows/reliability.yml
outside=$(git diff --name-only "$START_SHA" HEAD | grep -v -E \
  '^(extras/desktop-drop/|tests/reader_desktop_drop/|\.github/workflows/reader-desktop-drop\.yml$|docs/READER-DESKTOP-DROP\.md$|docs/validation/reader-desktop-drop\.json$)' || true)
if [ -n "$outside" ]; then
  echo "changes outside the desktop drop package:"
  echo "$outside"
  exit 1
fi
if grep -rn 'desktop[-_]drop' CMakeLists.txt cmake; then
  echo "the default build must not include the desktop drop module"
  exit 1
fi
if grep -rnE '#include[[:space:]]*[<"](exr|EXReader)/' extras/desktop-drop; then
  echo "the adapter must stay SDK-free and use only its own public header"
  exit 1
fi
# The installed module (src + public headers) must stay silent; the host
# example under examples/ is a normal program and prints its own result.
if grep -rnE '(^|[^A-Za-z0-9_])(printf|fprintf|puts|perror|syslog|NSLog|OutputDebugString[AW]?|g_print|g_warning)[[:space:]]*\(' \
    extras/desktop-drop/src extras/desktop-drop/include; then
  echo "installed module sources must not print or log"
  exit 1
fi
echo "scope: start $START_SHA, frozen SDK $FROZEN_SDK, whitelist-only changes, SDK-free module"
