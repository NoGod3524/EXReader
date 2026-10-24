#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# J19 package guard: fixed start, frozen SDK and product SQL unchanged, every
# changed path inside this package's whitelist, and the library keeps its hard
# properties (no text formatting, no process spawning, no autospawn).
set -euo pipefail

START=f43baf9182d75907c0cb5d6f77048f27bca8c950
FROZEN_SDK=9854061be331fe603a1822d9b2b36ee357154927
PRODUCT_SQL=apps/reader/store/001_catalog.sql
PROTECTED=(src include cmake CMakeLists.txt tests/fixtures bindings
           .github/workflows/native.yml .github/workflows/reliability.yml)

fails=0
ok()   { printf 'guard: pass: %s\n' "$1"; }
bad()  { printf 'guard: FAIL: %s\n' "$1" >&2; fails=$((fails + 1)); }

head_sha=$(git rev-parse HEAD)
printf 'guard: HEAD=%s GITHUB_SHA=%s\n' "$head_sha" "${GITHUB_SHA:-unset}"
if [ "${GITHUB_SHA:-$head_sha}" = "$head_sha" ]; then
  ok "HEAD equals GITHUB_SHA"
else
  bad "HEAD $head_sha differs from GITHUB_SHA ${GITHUB_SHA:-unset}"
fi

if git cat-file -e "$START^{commit}" 2>/dev/null; then
  if git merge-base --is-ancestor "$START" HEAD; then
    ok "fixed start $START is an ancestor of HEAD"
  else
    bad "fixed start $START is not an ancestor of HEAD"
  fi
else
  bad "fixed start $START is not available in this clone"
fi

if git cat-file -e "$FROZEN_SDK^{commit}" 2>/dev/null; then
  if git diff --quiet "$FROZEN_SDK" "$START" -- "${PROTECTED[@]}"; then
    ok "start matches frozen SDK $FROZEN_SDK on the protected tree"
  else
    bad "start differs from frozen SDK $FROZEN_SDK on the protected tree"
  fi
else
  bad "frozen SDK commit $FROZEN_SDK is missing from this clone"
fi

changed_protected=$(git diff --name-only "$START" HEAD -- "${PROTECTED[@]}" || true)
if [ -z "$changed_protected" ]; then
  ok "protected paths unchanged since the fixed start"
else
  bad "protected paths changed: $(echo "$changed_protected" | tr '\n' ' ')"
fi

if [ -n "$(git diff --name-only "$START" HEAD -- "$PRODUCT_SQL" || true)" ]; then
  bad "product SQL $PRODUCT_SQL changed"
else
  ok "product SQL $PRODUCT_SQL unchanged"
fi
product_sql_before=$(git rev-parse "$START:$PRODUCT_SQL")
product_sql_now=$(git rev-parse "HEAD:$PRODUCT_SQL")
if [ "$product_sql_before" = "$product_sql_now" ]; then
  ok "product SQL blob identical ($product_sql_now)"
else
  bad "product SQL blob differs ($product_sql_before -> $product_sql_now)"
fi

allowed() {
  case "$1" in
    extras/reader-tts-linux/*) return 0 ;;
    tests/reader_tts_linux/*) return 0 ;;
    .github/workflows/reader-tts-linux.yml) return 0 ;;
    docs/READER-TTS-LINUX.md) return 0 ;;
    docs/validation/reader-tts-linux.json) return 0 ;;
    *) return 1 ;;
  esac
}
outside=0
covered=0
while IFS= read -r path; do
  [ -n "$path" ] || continue
  if allowed "$path"; then
    covered=$((covered + 1))
  else
    bad "changed path outside the package whitelist: $path"
    outside=$((outside + 1))
  fi
done < <(git diff --name-only "$START" HEAD)
if [ "$outside" -eq 0 ]; then
  ok "every changed path is inside the J19 whitelist"
fi
printf 'guard: changed paths inside the package: %d\n' "$covered"

# Source-level invariants of the library, checked on the working tree.
LIB=extras/reader-tts-linux/src/reader_tts_linux.c
if [ -f "$LIB" ]; then
  if grep -nE '\b(printf|fprintf|snprintf|sprintf|strcpy|strcat|va_list)\b' "$LIB" >/dev/null 2>&1; then
    bad "the library formats text; the frozen ABI must not carry message text"
  else
    ok "library never formats text (errors carry codes only)"
  fi
  if grep -nE '\b(system|popen|fork|execv|execve|execl|posix_spawn|daemon)[[:space:]]*\(' "$LIB" >/dev/null 2>&1; then
    bad "the library spawns processes; the daemon must stay a system service"
  else
    ok "library never spawns a process"
  fi
  if grep -q 'spd_open2("exreader-reader-tts", "reader", NULL, SPD_MODE_THREADED, NULL, 0, &err)' "$LIB"; then
    ok "spd_open2 uses the default address with autospawn disabled"
  else
    bad "spd_open2 call does not disable autospawn / does not use the default address"
  fi
  for symbol in reader_tts_create reader_tts_voices reader_tts_voice_list_free reader_tts_speak \
                reader_tts_pause reader_tts_resume reader_tts_stop reader_tts_observe \
                reader_tts_poll reader_tts_request_close reader_tts_destroy; do
    if ! grep -qE "^(reader_tts_status|void) $symbol\(" "$LIB"; then
      bad "frozen ABI symbol missing from the library: $symbol"
    fi
  done
  ok "all frozen ABI entry points are implemented"
  if grep -q 'READER_TTS_VERSION "0.1.0"' extras/reader-tts-linux/include/reader_tts.h; then
    ok "READER_TTS_VERSION is 0.1.0"
  else
    bad "READER_TTS_VERSION macro missing or changed"
  fi
else
  bad "library source $LIB is missing"
fi

if [ "$fails" -ne 0 ]; then
  printf 'guard: %d failing check(s)\n' "$fails" >&2
  exit 1
fi
printf 'guard: all checks passed\n'
