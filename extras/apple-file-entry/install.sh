#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Builds and installs the file-entry component for one Apple SDK:
#   install.sh <prefix> <macos|iphonesimulator>
# Output: <prefix>/lib/libEXRFileEntry.a, <prefix>/lib/swift/EXRFileEntry.swiftmodule,
# <prefix>/share/exreader-apple-file-entry/{LICENSE.txt,examples/*}.
set -euo pipefail
prefix=${1:?prefix}
target=${2:?macos|iphonesimulator}
here=$(cd "$(dirname "$0")" && pwd)
arch=$(uname -m)
case "$target" in
  macos) sdk=macosx; triple="$arch-apple-macos12.0" ;;
  iphonesimulator) sdk=iphonesimulator; triple="arm64-apple-ios15.0-simulator" ;;
  *) echo "unknown target $target" >&2; exit 2 ;;
esac
sdkpath=$(xcrun --sdk "$sdk" --show-sdk-path)
mkdir -p "$prefix/lib/swift" "$prefix/share/exreader-apple-file-entry/examples"
xcrun --sdk "$sdk" swiftc -swift-version 5 -O -parse-as-library \
  -module-name EXRFileEntry -target "$triple" -sdk "$sdkpath" \
  -emit-library -static -emit-module -emit-module-path "$prefix/lib/swift/EXRFileEntry.swiftmodule" \
  -o "$prefix/lib/libEXRFileEntry.a" "$here"/Sources/EXRFileEntry/*.swift
cp "$here"/examples/* "$prefix/share/exreader-apple-file-entry/examples/"
cp "$here/../../LICENSE" "$prefix/share/exreader-apple-file-entry/LICENSE.txt"
echo "installed EXRFileEntry for $target ($triple) into $prefix"
