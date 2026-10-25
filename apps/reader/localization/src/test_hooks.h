/* SPDX-License-Identifier: MIT */
/* Test-hook API, available only in a build with READER_LOCALIZATION_TEST_HOOKS.
   The shipped library and every installed consumer build without that macro, so
   these symbols do not exist in the installed package. */
#ifndef READER_LOCALIZATION_TEST_HOOKS_H
#define READER_LOCALIZATION_TEST_HOOKS_H

#include "reader_localization.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Drop the shipped row for one message/locale so the caller sees the en-US
   fallback. Returns 1 when the row was overridden. */
int reader_localization_test_drop(const char *message_id, uint32_t locale);
/* Substitute a self-inconsistent template (for example "{9}") for one row.
   Returns 1 when the row was overridden. The override is never applied to the
   catalog digest, which always describes the shipped rows. */
int reader_localization_test_corrupt(const char *message_id, uint32_t locale, const char *text);
/* Replace one row's slot layout with a layout of 's', 'd' and 'u' characters, at
   most one character past READER_LOCALIZATION_MAX_SLOTS. Returns 1 when the row
   was overridden. It lets the worker reach the unsigned slot kind and the
   over-long-layout refusal, which no shipped row exercises, and is never
   applied to the catalog digest. */
int reader_localization_test_kinds(const char *message_id, const char *kinds);
/* Remove every template, layout and fallback override. */
void reader_localization_test_reset(void);

#ifdef __cplusplus
}
#endif
#endif
