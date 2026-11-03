#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Actions custom shell: fail on the first failed command, including pipelines.
set -Eeuo pipefail
trap 'rc=$?; printf "expected=command success; actual=exit %s command=%s; candidate=%s:%s\n" "$rc" "$BASH_COMMAND" "${BASH_SOURCE[0]}" "$LINENO" >&2; exit "$rc"' ERR

ci_require_nonempty() {
  local actual="$1" expected="$2"; shift 2
  if [[ -z "$actual" ]]; then
    printf 'expected=%s; actual=<empty>; candidates=%s\n' "$expected" "$*" >&2
    return 1
  fi
}

ci_expect_failure() {
  # Preserve the rejected command's actual stdout/stderr, not just its status.
  local rc
  printf 'expected=nonzero exit; candidate command: %s\n' "$*"
  trap - ERR
  set +e
  "$@"
  rc=$?
  set -e
  trap 'rc=$?; printf "expected=command success; actual=exit %s command=%s; candidate=%s:%s\n" "$rc" "$BASH_COMMAND" "${BASH_SOURCE[0]}" "$LINENO" >&2; exit "$rc"' ERR
  printf 'actual=exit %s; rejected candidate command: %s\n' "$rc" "$*"
  [ "$rc" -ne 0 ] || { echo "control did not fail; expected=nonzero; actual=0; candidate=$*" >&2; exit 1; }
}

source "$1"
