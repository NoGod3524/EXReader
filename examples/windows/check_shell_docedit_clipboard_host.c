/* SPDX-License-Identifier: MIT */
/* Compile-only integration check: the slice sees the actual host declarations.
   gcc -std=c11 -fsyntax-only -DEXR_READER_WINDOWS_SHELL -Iinclude
     examples/windows/check_shell_docedit_clipboard_host.c
   The shipping include belongs immediately before de_key in input.inc. */
#define WinMain clipboard_host_WinMain
#include "../reader.c"
#undef WinMain
#include "shell_docedit_clipboard.inc"
