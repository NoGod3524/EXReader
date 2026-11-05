#!/usr/bin/env bash
set -euo pipefail
out=build/final-d05
mkdir -p "$out/legacy" "$out/delta"
adb wait-for-device
adb shell getprop > "$out/getprop.txt"
adb shell wm size > "$out/resolution.txt"
adb shell wm density > "$out/density.txt"
adb shell settings get secure enabled_accessibility_services > "$out/accessibility-services.txt"
adb install -r -t build/android-host/artifacts/app-debug.apk
adb install -r -t tests/reader_final_d05/harness/a11y/build/outputs/apk/debug/a11y-debug.apk
adb install -r -t tests/reader_final_d05/harness/a11y/build/outputs/apk/androidTest/debug/a11y-debug-androidTest.apk
for name in Sample.epub Second.epub Sample.txt Sample.pdf; do adb push "build/android-host/fixtures/$name" /sdcard/Download/; done
apk_path="$(adb shell pm path org.exreader.host | tr -d '\r' | sed -n 's/^package://p' | head -n 1)"
adb exec-out cat "$apk_path" > "$out/installed-host.apk"
cmp "$out/installed-host.apk" build/android-host/artifacts/app-debug.apk
for suite in legacy delta; do
  adb shell pm clear org.exreader.host
  adb shell settings put system font_scale 1.0
  adb shell wm density reset
  if [ "$suite" = legacy ]; then class=A11yAuditTest; folder=a11y-evidence; else class=FinalAuditTest; folder=final-evidence; fi
  set +e
  adb shell am instrument -w -r -e class "org.exreader.a11y.$class" -e exr_source_sha "$GITHUB_SHA" -e exr_run_id "$GITHUB_RUN_ID" -e exr_attempt "$GITHUB_RUN_ATTEMPT" org.exreader.host.a11y.test/androidx.test.runner.AndroidJUnitRunner > "$out/$suite-instrumentation.txt" 2>&1
  code=$?
  set -e
  echo "$code" > "$out/$suite-exit.txt"
  cat "$out/$suite-instrumentation.txt"
  adb pull "/sdcard/Android/data/org.exreader.host.a11y/files/$folder/." "$out/$suite/" || true
  adb logcat -d -v threadtime > "$out/$suite-logcat.txt"
done
python3 tests/reader_final_d05/evidence.py seal "$out"
