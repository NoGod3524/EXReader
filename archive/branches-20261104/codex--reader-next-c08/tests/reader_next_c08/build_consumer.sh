#!/usr/bin/env bash
# Build the independent C ABI consumer against the SDK headers that shipped with
# the producer run. Actions only; the headers are never taken from this checkout.
set -euo pipefail
out="${1:-build/c08-consumer}"
inventory="${2:-build/c08-authenticate/inventory.json}"
producer_source="4a04a9cc74dde67f755c87e87b278d63a254a3ac"
mkdir -p "$out"
stage="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['sdk_stage']['path'])" "$inventory")"
include=""
origin=""
if [ -f "$stage/include/exr/library.h" ]; then
  include="$stage/include"
  origin="sdk-stage of the authenticated producer artifact"
else
  # The staging tree carries the umbrella header only; take the public headers of
  # the sealed producer commit and record that fact.
  rm -rf "$out/headers"
  mkdir -p "$out/headers"
  git archive "$producer_source" include | tar -x -C "$out/headers"
  include="$out/headers/include"
  origin="git archive of sealed producer source $producer_source include/"
fi
if [ ! -f "$include/exr/library.h" ]; then
  echo "no exr/library.h found in $include" >&2
  find "$stage" -maxdepth 3 | head -80 >&2
  exit 1
fi
ndk="${ANDROID_NDK_ROOT:-${ANDROID_NDK_HOME:-}}"
if [ -z "$ndk" ] || [ ! -d "$ndk" ]; then
  ndk="$(ls -d "${ANDROID_HOME:-/usr/local/lib/android/sdk}"/ndk/* | sort | tail -1)"
fi
clang="$ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/x86_64-linux-android26-clang"
"$clang" --version | head -2
"$clang" -std=gnu11 -O2 -Wall -Wextra -fPIE -pie -I"$include" \
  tests/reader_next_c08/consumer/c08_consumer.c -ldl -o "$out/c08_consumer"
sha256sum "$out/c08_consumer" | tee "$out/c08_consumer.sha256"
file "$out/c08_consumer" || true
python3 - "$out" "$include" "$origin" "$ndk" <<'PY'
import hashlib, json, pathlib, sys
out, include, origin, ndk = sys.argv[1:]
headers = {}
for path in sorted(pathlib.Path(include).rglob('*.h')):
    headers[path.relative_to(include).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
binary = pathlib.Path(out, 'c08_consumer')
pathlib.Path(out, 'consumer-build.json').write_text(json.dumps({
    'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'bytes': binary.stat().st_size,
    'headers_origin': origin, 'headers': headers, 'ndk': ndk,
    'source_sha256': hashlib.sha256(pathlib.Path('tests/reader_next_c08/consumer/c08_consumer.c').read_bytes()).hexdigest(),
}, indent=2, sort_keys=True) + '\n')
PY
