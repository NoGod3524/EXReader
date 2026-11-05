#!/usr/bin/env bash
set -euo pipefail
adb wait-for-device
for _ in $(seq 1 180); do
  if [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; then break; fi
  sleep 3
done
[ "$(adb shell getprop sys.boot_completed | tr -d '\r')" = "1" ]
adb shell settings put global window_animation_scale 0
adb shell settings put global transition_animation_scale 0
adb shell settings put global animator_duration_scale 0
adb shell setprop debug.checkjni 1
adb install -r -t build/wave3/artifacts/app-debug.apk
adb install -r -t build/wave3/artifacts/original-save-debug-androidTest.apk
python3 tests/android_real_original_save/run_ui.py
