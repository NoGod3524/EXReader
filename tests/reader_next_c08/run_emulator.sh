#!/usr/bin/env bash
set -euo pipefail
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-/usr/local/lib/android/sdk}}"
export PATH="$PATH:$ANDROID_SDK_ROOT/platform-tools"
mkdir -p build/c08-logs
python3 tests/reader_next_c08/emulator.py 2>&1 | tee build/c08-logs/emulator.log
