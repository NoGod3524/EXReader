#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# The emulator action invokes each script entry separately; run both commands in one shell.
observation=0
python tools/run_reader_shelf_ui.py --output build/perf-android/ui-execution || observation=$?
verification=0
python tests/reader_perf_android/verify_observation.py || verification=$?
test "$observation" -eq 0 && test "$verification" -eq 0
