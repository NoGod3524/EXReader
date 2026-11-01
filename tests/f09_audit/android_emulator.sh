#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Emulator side of the F09 Android lane: the retained audit unchanged, then the
# F09 annotation-reachability flow on the same installed host. Each keeps its
# own result; neither decides the other.
set -uo pipefail
bash tests/reader_a11y_android/ci/emulator-audit.sh
echo "retained audit exit $?" | tee build/a11y-android/retained-audit-exit.txt
python3 tests/f09_audit/android_flow.py
echo "f09 flow exit $?"
exit 0
