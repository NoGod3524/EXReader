#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Emulator-side host walkthrough. Kept in a file because the emulator action
# runs its inline script line by line.
set -e

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
EVIDENCE="$ROOT/build/android-host/evidence"
mkdir -p "$EVIDENCE"

wait_boot() {
  adb wait-for-device
  for _ in $(seq 1 240); do
    value="$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' || true)"
    [ "$value" = "1" ] && return 0
    sleep 3
  done
  return 1
}

try_storage() {
  adb shell mkdir -p /sdcard/Download >/dev/null 2>&1
}

ensure_storage() {
  for _ in $(seq 1 24); do
    try_storage && return 0
    sleep 5
  done
  echo "shared storage is not ready; collecting diagnostics"
  {
    adb shell sm list-volumes all || true
    adb shell ls -ld /sdcard /storage/emulated/0 /data/media/0 || true
    adb shell mount | grep -E 'fuse|emulated|sdcard' || true
    adb logcat -d -b all | grep -iE 'MediaProvider|FUSE|vold|sdcard' | tail -n 120 || true
  } > "$EVIDENCE/storage-before.txt" 2>&1 || true
  adb root || true
  adb wait-for-device
  sleep 3
  adb shell "sm mount 'emulated;0'" || true
  sleep 5
  for _ in $(seq 1 12); do
    try_storage && return 0
    sleep 5
  done
  echo "rebooting the emulator to recover shared storage"
  adb reboot || true
  wait_boot || true
  sleep 20
  adb shell input keyevent 82 || true
  for _ in $(seq 1 36); do
    try_storage && return 0
    sleep 5
  done
  {
    adb shell sm list-volumes all || true
    adb shell ls -ld /sdcard /storage/emulated/0 /data/media/0 || true
    adb shell mount | grep -E 'fuse|emulated|sdcard' || true
  } > "$EVIDENCE/storage-after.txt" 2>&1 || true
  return 1
}

ensure_storage

adb shell settings put global window_animation_scale 0
adb shell settings put global transition_animation_scale 0
adb shell settings put global animator_duration_scale 0
adb install -r build/android-host/artifacts/app-debug.apk
adb install -r build/android-host/artifacts/uitest-debug.apk
adb install -r build/android-host/artifacts/uitest-debug-androidTest.apk

for file in build/android-host/fixtures/*; do
  case "$file" in
    *.epub|*.pdf|*.txt) adb push "$file" /sdcard/Download/ ;;
  esac
done
adb shell ls -l /sdcard/Download > "$EVIDENCE/device-downloads.txt" 2>&1 || true

adb shell pm clear org.exreader.host
adb shell rm -rf /sdcard/Android/data/org.exreader.host.uitest/files/evidence

set +e
adb shell am instrument -w -e disableAnalytics true \
  org.exreader.host.uitest.test/androidx.test.runner.AndroidJUnitRunner \
  | tee "$EVIDENCE/instrumentation.txt"
instrument_status=$PIPESTATUS
set -e

adb logcat -d > "$EVIDENCE/logcat.txt" || true
adb pull /sdcard/Android/data/org.exreader.host.uitest/files/evidence \
  "$EVIDENCE/device" || true
if [ -d "$EVIDENCE/device/evidence" ]; then
  cp -a "$EVIDENCE/device/evidence/." "$EVIDENCE/device/"
  rm -rf "$EVIDENCE/device/evidence"
fi
adb shell dumpsys package org.exreader.host > "$EVIDENCE/package.txt" 2>&1 || true

exit "$instrument_status"
