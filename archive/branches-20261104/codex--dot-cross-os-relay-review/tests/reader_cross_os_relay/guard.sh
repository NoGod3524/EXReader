#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Per-job source guard: exact checkout, fixed start ancestor, protected SDK/schema trees equal,
# product SQL equal to the start, and every changed path inside this package's allowlist.
set -euo pipefail
START=9ff063dcc6b898fb0c776edabadf743919045a7d
SDK=9854061be331fe603a1822d9b2b36ee357154927
SCHEMA=f32bb8aa18ed3de286900f19ce4230fd93435dd0
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
git merge-base --is-ancestor "$START" HEAD
git diff --exit-code "$SDK" HEAD -- src include cmake CMakeLists.txt tests/fixtures bindings .github/workflows/native.yml .github/workflows/reliability.yml
git diff --exit-code "$SCHEMA" HEAD -- apps/reader/store/001_catalog.sql
git diff --exit-code "$START" HEAD -- apps/reader/store/001_catalog.sql
bad=$(git diff --name-only "$START" HEAD | grep -Ev '^(tests/reader_cross_os_relay/|\.github/workflows/reader-cross-os-relay\.yml$|docs/READER-CROSS-OS-RELAY\.md$|docs/validation/reader-cross-os-relay\.json$)' || true)
if [ -n "$bad" ]; then echo "paths outside the package allowlist:"; echo "$bad"; exit 1; fi
echo "guard ok: $(git rev-parse HEAD)"
