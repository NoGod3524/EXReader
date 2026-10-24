#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Emulator-side accessibility audit. Kept in a file because the emulator action
# runs its inline script line by line.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
EVIDENCE="$ROOT/build/a11y-android"
DEVICE="$EVIDENCE/device"
HOST_APK="$ROOT/build/android-host/artifacts/app-debug.apk"
mkdir -p "$DEVICE"

adb wait-for-device
for _ in $(seq 1 180); do
  if [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' || true)" = "1" ]; then
    break
  fi
  sleep 2
done

adb shell getprop ro.build.version.sdk | tr -d '\r' > "$EVIDENCE/device-api.txt"
adb shell getprop ro.product.cpu.abi | tr -d '\r' > "$EVIDENCE/device-abi.txt"
adb shell getprop ro.build.fingerprint | tr -d '\r' > "$EVIDENCE/device-fingerprint.txt"

adb shell settings put global window_animation_scale 0
adb shell settings put global transition_animation_scale 0
adb shell settings put global animator_duration_scale 0
adb shell settings put global hide_error_dialogs 1

adb install -r -t "$HOST_APK"
adb install -r -t "$EVIDENCE/apks/a11y-debug.apk"
adb install -r -t "$EVIDENCE/apks/a11y-debug-androidTest.apk"

for file in "$ROOT"/build/android-host/fixtures/*; do
  case "$file" in
    *.epub|*.pdf|*.txt) adb push "$file" /sdcard/Download/ >/dev/null ;;
  esac
done
adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE \
  -d file:///sdcard/Download/Sample.epub >/dev/null 2>&1 || true
adb shell ls -l /sdcard/Download > "$EVIDENCE/device-downloads.txt" 2>&1 || true

# The audited application keeps its identity: read the installed APK back and
# compare it with the owner build record instead of trusting the install step.
apk_path="$(adb shell pm path org.exreader.host | tr -d '\r' | sed -n 's/^package://p' | head -n 1)"
test -n "$apk_path"
adb exec-out cat "$apk_path" > "$EVIDENCE/installed-host.apk"
sha="$(sha256sum "$EVIDENCE/installed-host.apk" | cut -d' ' -f1)"
size="$(stat -c %s "$EVIDENCE/installed-host.apk")"
printf '%s %s\n' "$sha" "$size" > "$EVIDENCE/installed-host-apk.txt"

adb shell pm clear org.exreader.host >/dev/null
adb shell am force-stop org.exreader.host || true
adb shell rm -rf /sdcard/Android/data/org.exreader.host.a11y/files/a11y-evidence

set +e
adb shell am instrument -w -r \
  -e exr_source_sha "${GITHUB_SHA}" \
  -e exr_run_id "${GITHUB_RUN_ID}" \
  -e exr_attempt "${GITHUB_RUN_ATTEMPT}" \
  org.exreader.host.a11y.test/androidx.test.runner.AndroidJUnitRunner \
  > "$EVIDENCE/instrumentation.txt" 2>&1
status=$?
set -e
echo "$status" > "$EVIDENCE/audit-exit.txt"
cat "$EVIDENCE/instrumentation.txt"

adb pull /sdcard/Android/data/org.exreader.host.a11y/files/a11y-evidence/. "$DEVICE/" || true
test -s "$DEVICE/validation.json"
adb logcat -d -v threadtime > "$EVIDENCE/logcat.txt" || true
