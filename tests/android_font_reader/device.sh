#!/usr/bin/env bash
# Retain every original device suite and collect new checks even on old failure.
set -euo pipefail
BASE="${1:?workspace}"
status=0
bash tests/reader_wave3_c11/device.sh "$BASE" || status=1
adb install -r -t "$BASE/artifacts/font-reader-debug-androidTest.apk" || status=1
python3 tests/android_font_reader/run_ui.py --fixtures "$BASE/fixtures" \
  --font tests/fixtures/fonts/primary.ttf --app "$BASE/artifacts/app-debug.apk" \
  --output "$BASE/evidence/font-reader" || status=1
exit "$status"
