#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Cloud guard: tested commit descends from the fixed start, the frozen SDK and
# every file outside this package are unchanged, and module sources contain no
# logging or printing call through which a secret could reach a log.
set -euo pipefail
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
git merge-base --is-ancestor "$START_SHA" HEAD
git diff --exit-code "$FROZEN_SDK" HEAD -- src include cmake CMakeLists.txt tests/fixtures bindings \
  .github/workflows/native.yml .github/workflows/reliability.yml
outside=$(git diff --name-only "$START_SHA" HEAD | grep -v -E \
  '^(extras/credentials/|tests/reader_credentials/|\.github/workflows/reader-credentials\.yml$|docs/READER-CREDENTIALS\.md$|docs/validation/reader-credentials\.json$)' || true)
if [ -n "$outside" ]; then
  echo "changes outside the credentials package:"; echo "$outside"; exit 1
fi
if grep -rnE '(^|[^A-Za-z0-9_])(printf|fprintf|puts|perror|syslog|NSLog|OutputDebugString[AW]?|__android_log_[a-z]+)[[:space:]]*\(|(^|[^A-Za-z0-9_])Log\.[a-z]+\(|System\.(out|err)' \
    extras/credentials/src extras/credentials/include extras/credentials/android/credentials/src; then
  echo "module sources must not log or print"; exit 1
fi
if grep -rn 'credentials' CMakeLists.txt cmake; then
  echo "default build must not include the credentials module"; exit 1
fi
echo "scope: fixed start $START_SHA, frozen SDK $FROZEN_SDK, package-only changes, no module logging"
