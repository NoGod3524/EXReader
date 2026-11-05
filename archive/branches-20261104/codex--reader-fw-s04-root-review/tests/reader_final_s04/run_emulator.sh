#!/usr/bin/env bash
set -euo pipefail
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-/usr/local/lib/android/sdk}}"
export PATH="$PATH:$ANDROID_SDK_ROOT/platform-tools"
mkdir -p build/s04-logs
python3 tests/reader_final_s04/emulator.py --contract docs/reader-final-s04/apk-contract.json --inventory build/s04-authenticate/inventory.json --output build/s04-emulator 2>&1 | tee build/s04-logs/emulator.log
