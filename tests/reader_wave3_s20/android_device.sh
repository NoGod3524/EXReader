#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Install the unpacked S20 Android delivery on the emulator and run the two
# existing instrumentation suites through the unchanged evidence runner.
set -euo pipefail

FRESH="${1:?fresh unpacked delivery directory}"
EVIDENCE="${2:?evidence directory}"
mkdir -p "$EVIDENCE"

adb wait-for-device
for _ in $(seq 1 120); do
  value="$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' || true)"
  [ "$value" = "1" ] && break
  sleep 3
done

adb shell settings put global window_animation_scale 0
adb shell settings put global transition_animation_scale 0
adb shell settings put global animator_duration_scale 0
adb shell settings put global hide_error_dialogs 1
adb shell settings put global anr_show_background 0

for _ in $(seq 1 24); do
  adb shell mkdir -p /sdcard/Download >/dev/null 2>&1 && break
  sleep 5
done

adb install -r "$FRESH/artifacts/app-debug.apk"
adb install -r "$FRESH/artifacts/uitest-debug.apk"
adb install -r "$FRESH/artifacts/uitest-debug-androidTest.apk"

for file in "$FRESH"/fixtures/*; do
  case "$file" in
    *.epub|*.pdf|*.txt) adb push "$file" /sdcard/Download/ ;;
  esac
done
adb shell ls -l /sdcard/Download > "$EVIDENCE/device-downloads.txt" 2>&1 || true

adb shell pm clear org.exreader.host
adb shell rm -rf /sdcard/Android/data/org.exreader.host.uitest/files/evidence \
  /sdcard/Android/data/org.exreader.host.uitest/files/review-evidence \
  /sdcard/Android/data/org.exreader.host.uitest/files/bounded-evidence

python3 tools/run_android_host_evidence.py --build "$FRESH/build.json" --evidence "$EVIDENCE"
