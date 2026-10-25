#!/usr/bin/env bash
set -euo pipefail
[[ "$GITHUB_ACTIONS" == true ]]
# All inputs remain in the pinned isolated target checkout.
cmake --preset reading-library
cmake --build --preset reading-library --parallel 2
cmake --install build/reading-library
prefix="$PWD/build/d09-stage"
sdk="$PWD/build/reading-library/stage"
for module in apps/reader/store/native extras/webdav apps/reader/revisions apps/reader/commands apps/reader/desktop-metadata apps/reader/sync apps/reader/session extras/credentials extras/sideload apps/reader/batch-import apps/reader/reading-state apps/reader/reading-commands apps/reader/annotation-view apps/reader/preferences apps/reader/search apps/reader/navigation extras/desktop-drop; do
  name="${module//\//-}"
  raw=(); case "$module" in apps/reader/revisions|apps/reader/commands|apps/reader/desktop-metadata|apps/reader/sync|apps/reader/session|apps/reader/reading-state|apps/reader/reading-commands|apps/reader/annotation-view) raw=(-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON);; esac
  cmake -S "$module" -B "build/d09-$name" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$prefix" -DCMAKE_PREFIX_PATH="$prefix;$sdk" -DREADER_PRODUCT_PREFIX="$prefix" -DEXR_SDK="$sdk" -DEXR_SDK_VERSION=3.41.0 "${raw[@]}"
  cmake --build "build/d09-$name" --parallel 2
  cmake --install "build/d09-$name"
done
for mode in ON; do
  # Explicit raw3 compact candidate only; old OFF D03 evidence remains separate.
  extra=(); if [[ "$mode" == ON ]]; then extra=(-DEXR_READER_GTK_COMPACT=ON); fi
  cmake -S apps/reader/desktop -B "build/d09-$mode" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_EXPORT_COMPILE_COMMANDS=ON "${extra[@]}" -DEXR_SDK_VERSION=3.41.0 -DEXR_READER_GTK_RAW3=ON -DREADER_GTK_RAW3_PREFIX="$prefix" -DEXR_READER_PAGE_BACKGROUND=ON -DEXR_SDK="$sdk" -DREADER_METADATA_PREFIX="$prefix" -DREADER_ACCOUNT_PREFIX="$prefix" -DEXR_READER_GTK_BATCH_IMPORT=ON -DEXR_READER_GTK_DROP_IMPORT=ON -DREADER_DESKTOP_DROP_PREFIX="$prefix" -DREADER_BATCH_IMPORT_PREFIX="$prefix" -DEXR_READER_GTK_ACCOUNT=ON -DEXR_READER_GTK_PREFERENCES=ON -DREADER_PREFERENCES_PREFIX="$prefix" -DEXR_READER_GTK_SEARCH=ON -DREADER_SEARCH_PREFIX="$prefix" -DEXR_READER_GTK_READING_RECORDS=ON -DREADER_READING_RECORDS_PREFIX="$prefix" -DCMAKE_PREFIX_PATH="$prefix;$sdk" -DEXR_READER_GTK_NAVIGATION=ON -DREADER_NAVIGATION_PREFIX="$prefix" -DEXR_READER_FIXTURES="$PWD/tests/fixtures" -DEXR_READER_BUILD_GTK=ON
  cmake --build "build/d09-$mode" --parallel 2 --target exreader-linux --verbose
  python3 tools/build_linux_host.py --sdk "$sdk" --sdk-version 3.41.0 --binary "build/d09-$mode/gtk-host/exreader-linux" --output "build/d09-package-$mode"
done
