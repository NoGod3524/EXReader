#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Build the eight-arm factorial from real commits. Each change touches exactly one file,
# and no other renderer source, header or CMake input differs between 9a4f3ba0c and the
# test merge of main + perf/dense-vector-439, so each arm is base plus the chosen files.
#   G = #264  src/canvas.c        from f77d6712a
#   I = #263  src/affine_image.c  from 578d942e3
#   V = densevec src/blend.c      from b5ba2f363
# Usage: build.sh <detached worktree at 9a4f3ba0c, configured at build/perf> <output root>
set -euo pipefail
tree=$1; out=$2
cd "$tree"
for arm in base G I V GI GV IV GIV; do
  git checkout -q 9a4f3ba0c -- src/canvas.c src/affine_image.c src/blend.c
  [[ $arm == *G* ]] && git checkout -q f77d6712a -- src/canvas.c
  [[ $arm == *I* ]] && git checkout -q 578d942e3 -- src/affine_image.c
  [[ $arm == *V* ]] && git checkout -q b5ba2f363 -- src/blend.c
  ninja -C build/perf libexreader.dll > "$out/build-$arm.log" 2>&1
  mkdir -p "$out/$arm" && cp build/perf/libexreader.dll "$out/$arm/"
done
git checkout -q 9a4f3ba0c -- src
