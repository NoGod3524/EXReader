#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Install the packaged C11 host and both test APKs on the real API34 emulator,
# then execute the unchanged uitest suites and the wave3 instrumentation phases.
set -euo pipefail

BASE="${1:?build/wave3 workspace}"
ARTIFACTS="$BASE/artifacts"
FIXTURES="$BASE/fixtures"
DOWNLOAD="$BASE/download"
EVIDENCE="$BASE/evidence"
mkdir -p "$EVIDENCE"

adb wait-for-device
for _ in $(seq 1 180); do
  if [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; then break; fi
  sleep 3
done
[ "$(adb shell getprop sys.boot_completed | tr -d '\r')" = "1" ] || { echo "emulator did not boot"; exit 1; }

adb shell settings put global window_animation_scale 0
adb shell settings put global transition_animation_scale 0
adb shell settings put global animator_duration_scale 0
adb shell settings put global hide_error_dialogs 1
adb shell setprop debug.checkjni 1
[ "$(adb shell getprop debug.checkjni | tr -d '\r')" = "1" ] || { echo "CheckJNI was not enabled"; exit 1; }
adb shell getprop debug.checkjni > "$EVIDENCE/checkjni.txt"

adb install -r -t "$ARTIFACTS/app-debug.apk"
adb install -r -t "$ARTIFACTS/uitest-debug.apk"
adb install -r -t "$ARTIFACTS/uitest-debug-androidTest.apk"

adb shell mkdir -p /sdcard/Download
for fixture in "$DOWNLOAD"/* "$FIXTURES"/*; do
  case "$fixture" in
    *.epub|*.txt|*.pdf) adb push "$fixture" /sdcard/Download/ ;;
  esac
done
adb shell ls -l /sdcard/Download > "$EVIDENCE/device-downloads.txt" 2>&1 || true

status=0
python3 tests/reader_wave3_c11/walkthrough.py --app "$ARTIFACTS/app-debug.apk" \
  --fixtures "$DOWNLOAD" --output "$EVIDENCE/walkthrough" || status=1

adb install -r -t "$ARTIFACTS/app-debug-androidTest.apk"
mkdir -p "$EVIDENCE/wave3"
python3 tests/reader_wave3_c11/run_ui.py --fixtures "$FIXTURES" \
  --font tests/fixtures/fonts/primary.ttf --app "$ARTIFACTS/app-debug.apk" \
  --output "$EVIDENCE/wave3" || status=1
adb install -r -t "$ARTIFACTS/navigation-debug-androidTest.apk"
python3 tests/reader_android_navigation/run_ui.py --fixtures "$BASE/navigation-fixtures" \
  --output "$EVIDENCE/navigation" || status=1
exit "$status"
