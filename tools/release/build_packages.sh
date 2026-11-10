#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu
if [ "$#" -lt 1 ] || [ "$#" -gt 3 ]; then
    echo "Usage: $0 BUILD_DIR [OUTPUT_DIR [CONFIGURATION]]" >&2
    exit 2
fi
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "${PYTHON:-python3}" "$script_dir/build_packages.py" --build-dir "$1" \
    --output-dir "${2:-$script_dir/../../dist}" --config "${3:-Release}"
