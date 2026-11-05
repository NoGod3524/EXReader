/* SPDX-License-Identifier: MIT */
/* Test-hook worker for EXReaderLocalization. It is built from the package
   sources with READER_LOCALIZATION_TEST_HOOKS, which the installed consumers
   never see, so the shipped library cannot be paused, dropped or corrupted
   through it. Every mode prints key=value lines; the out-of-process checker
   owns the expectations. */
#if defined(_WIN32)
#define _CRT_SECURE_NO_WARNINGS 1
#endif
#include "reader_localization.h"
#include "test_hooks.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static reader_localization_context make_context(uint32_t locale) {
  reader_localization_context context;
  memset(&context, 0, sizeof(context));
  context.struct_size = (uint32_t)sizeof(context);
  context.locale = locale;
  return context;
}

static reader_localization_param text_param(const char *text) {
  reader_localization_param param;
  memset(&param, 0, sizeof(param));
  param.struct_size = (uint32_t)sizeof(param);
  param.kind = (uint32_t)READER_LOCALIZATION_PARAM_STRING;
  param.string = text;
  return param;
}

static reader_localization_param int_param(int64_t value) {
  reader_localization_param param;
  memset(&param, 0, sizeof(param));
  param.struct_size = (uint32_t)sizeof(param);
  param.kind = (uint32_t)READER_LOCALIZATION_PARAM_INT;
  param.integer = value;
  return param;
}

static reader_localization_param uint_param(uint64_t value) {
  reader_localization_param param;
  memset(&param, 0, sizeof(param));
  param.struct_size = (uint32_t)sizeof(param);
  param.kind = (uint32_t)READER_LOCALIZATION_PARAM_UNSIGNED;
  param.unsigned_integer = value;
  return param;
}

static int hex_value(int character) {
  if (character >= '0' && character <= '9') return character - '0';
  if (character >= 'a' && character <= 'f') return character - 'a' + 10;
  if (character >= 'A' && character <= 'F') return character - 'A' + 10;
  return -1;
}

static int decode_hex(const char *hex, size_t length, char *out, size_t capacity) {
  size_t used = 0u;
  size_t i = 0u;
  if (length % 2u != 0u) return 0;
  while (i < length) {
    int high;
    int low;
    if (i + 1u >= length) return 0;
    high = hex_value((unsigned char)hex[i]);
    low = hex_value((unsigned char)hex[i + 1u]);
    if (high < 0 || low < 0) return 0;
    if (used + 1u >= capacity) return 0;
    out[used] = (char)((high << 4) | low);
    ++used;
    i += 2u;
  }
  out[used] = '\0';
  return 1;
}

typedef struct {
  reader_localization_param items[READER_LOCALIZATION_MAX_SLOTS];
  /* One byte past the value limit, so the fixture format can carry an
     over-long value and let the library refuse it instead of the parser. */
  char texts[READER_LOCALIZATION_MAX_SLOTS][READER_LOCALIZATION_MAX_VALUE_BYTES + 2u];
  size_t count;
} staged_params;

static int parse_spec(const char *spec, staged_params *staged) {
  const char *cursor = spec;
  staged->count = 0u;
  if (strcmp(spec, "-") == 0) return 1;
  while (*cursor != '\0') {
    char kind = *cursor;
    const char *value;
    size_t length = 0u;
    if (staged->count >= (size_t)READER_LOCALIZATION_MAX_SLOTS) return 0;
    if (cursor[1] != ':') return 0;
    value = cursor + 2;
    while (value[length] != '\0' && value[length] != '|') ++length;
    if (kind == 's') {
      size_t index = staged->count;
      if (!decode_hex(value, length, staged->texts[index], sizeof(staged->texts[index]))) return 0;
      staged->items[index] = text_param(staged->texts[index]);
    } else if (kind == 'd' || kind == 'u') {
      char number[32];
      if (length == 0u || length >= sizeof(number)) return 0;
      memcpy(number, value, length);
      number[length] = '\0';
      if (kind == 'd') {
        staged->items[staged->count] = int_param((int64_t)strtoll(number, NULL, 10));
      } else {
        staged->items[staged->count] = uint_param((uint64_t)strtoull(number, NULL, 10));
      }
    } else {
      return 0;
    }
    ++staged->count;
    cursor = value + length;
    if (*cursor == '|') ++cursor;
  }
  return 1;
}

static void print_hex(const char *text, size_t length) {
  static const char digits[] = "0123456789abcdef";
  size_t i;
  if (length == 0u) {
    (void)printf("-");
    return;
  }
  for (i = 0; i < length; ++i) {
    unsigned char byte = (unsigned char)text[i];
    (void)printf("%c%c", digits[byte >> 4], digits[byte & 0x0fu]);
  }
}

static void report(reader_localization_status status, const char *text, size_t length,
                   uint32_t fallback) {
  (void)printf("status=%s\n", reader_localization_status_name(status));
  (void)printf("fallback=%lu\n", (unsigned long)fallback);
  (void)printf("len=%lu\n", (unsigned long)length);
  (void)printf("hex=");
  print_hex(text, length);
  (void)printf("\n");
}

static int render(const char *message_id, uint32_t locale, staged_params *staged, uint32_t *fallback) {
  reader_localization_context context = make_context(locale);
  reader_localization_measurement measurement;
  char buffer[READER_LOCALIZATION_MAX_OUTPUT_BYTES + 1u];
  reader_localization_status status;
  uint32_t used_fallback = 0u;

  memset(&measurement, 0, sizeof(measurement));
  measurement.struct_size = (uint32_t)sizeof(measurement);
  status = reader_localization_measure(&context, message_id, staged->items, staged->count,
                                       &measurement);
  if (status != READER_LOCALIZATION_OK) {
    report(status, "", 0u, 0u);
    return 0;
  }
  used_fallback = measurement.fallback;
  memset(buffer, 0xa5, sizeof(buffer));
  status = reader_localization_format(&context, message_id, staged->items, staged->count, buffer,
                                      sizeof(buffer), &measurement);
  if (status != READER_LOCALIZATION_OK) {
    report(status, "", 0u, 0u);
    return 0;
  }
  if (fallback != NULL) *fallback = used_fallback;
  report(status, buffer, strlen(buffer), used_fallback);
  return 1;
}

static int print_manifest(void) {
  size_t messages = reader_localization_message_count();
  size_t templates = reader_localization_template_count();
  char digest[65];
  size_t i;
  reader_localization_catalog_digest(digest);
  (void)printf("MESSAGES\t%lu\n", (unsigned long)messages);
  (void)printf("TEMPLATES\t%lu\n", (unsigned long)templates);
  (void)printf("DIGEST\t%s\n", digest);
  for (i = 0; i < messages; ++i) {
    reader_localization_message message;
    memset(&message, 0, sizeof(message));
    message.struct_size = (uint32_t)sizeof(message);
    if (reader_localization_message_at(i, &message) != READER_LOCALIZATION_OK) return 1;
    (void)printf("M\t%s\t%s\t%s\n", message.message_id, message.group, message.kinds);
  }
  for (i = 0; i < templates; ++i) {
    reader_localization_template row;
    memset(&row, 0, sizeof(row));
    row.struct_size = (uint32_t)sizeof(row);
    if (reader_localization_template_at(i, &row) != READER_LOCALIZATION_OK) return 1;
    (void)printf("T\t%s\t%s\t%s\n", row.message_id, row.locale, row.text);
  }
  return 0;
}

int main(int argc, char **argv) {
  staged_params staged;
  uint32_t locale = 0u;

  memset(&staged, 0, sizeof(staged));
  if (argc < 2) {
    (void)printf("error=usage\n");
    return 2;
  }
  if (strcmp(argv[1], "manifest") == 0) {
    return print_manifest();
  }
  if (argc < 5) {
    (void)printf("error=usage\n");
    return 2;
  }
  if (reader_localization_parse_locale(argv[3], &locale) != READER_LOCALIZATION_OK) {
    (void)printf("error=locale\n");
    return 2;
  }
  if (!parse_spec(argv[4], &staged)) {
    (void)printf("error=spec\n");
    return 2;
  }

  if (strcmp(argv[1], "plain") == 0) {
    return render(argv[2], locale, &staged, NULL) ? 0 : 1;
  }
  if (strcmp(argv[1], "fallback") == 0) {
    uint32_t fallback = 0u;
    if (!reader_localization_test_drop(argv[2], locale)) {
      (void)printf("error=drop\n");
      return 2;
    }
    if (!render(argv[2], locale, &staged, &fallback)) {
      reader_localization_test_reset();
      return 1;
    }
    {
      char digest[65];
      reader_localization_catalog_digest(digest);
      (void)printf("digest=%s\n", digest);
    }
    reader_localization_test_reset();
    return 0;
  }
  if (strcmp(argv[1], "en-missing") == 0) {
    reader_localization_context context;
    reader_localization_template row;
    if (!reader_localization_test_drop(argv[2], (uint32_t)READER_LOCALIZATION_LOCALE_EN_US)) {
      (void)printf("error=drop\n");
      return 2;
    }
    context = make_context(locale);
    memset(&row, 0, sizeof(row));
    row.struct_size = (uint32_t)sizeof(row);
    (void)printf("resolve=%s\n",
                 reader_localization_status_name(reader_localization_resolve(&context, argv[2], &row)));
    {
      int ok = render(argv[2], locale, &staged, NULL);
      reader_localization_test_reset();
      return ok ? 0 : 1;
    }
  }
  if (strcmp(argv[1], "corrupt") == 0) {
    if (argc < 6) {
      (void)printf("error=usage\n");
      return 2;
    }
    if (!reader_localization_test_corrupt(argv[2], locale, argv[5])) {
      (void)printf("error=corrupt\n");
      return 2;
    }
    {
      int ok = render(argv[2], locale, &staged, NULL);
      reader_localization_test_reset();
      return ok ? 0 : 1;
    }
  }
  if (strcmp(argv[1], "slots") == 0) {
    /* slots <id> <locale> <spec> <kinds> <template>: replace one row's slot
       layout and template, then render it. The shipped catalog declares no
       unsigned slot and never more than three slots with every index bound
       exactly once, so this is the only way the unsigned kind, the 8-slot
       maximum and the over-long-layout refusal can be executed at all. The
       checker owns the expectations; the digest line proves the hook does not
       touch the shipped catalog. */
    char digest[65];
    int ok;
    if (argc < 7) {
      (void)printf("error=usage\n");
      return 2;
    }
    if (!reader_localization_test_kinds(argv[2], argv[5])) {
      (void)printf("error=kinds\n");
      return 2;
    }
    if (!reader_localization_test_corrupt(argv[2], locale, argv[6])) {
      reader_localization_test_reset();
      (void)printf("error=corrupt\n");
      return 2;
    }
    ok = render(argv[2], locale, &staged, NULL);
    reader_localization_catalog_digest(digest);
    (void)printf("digest=%s\n", digest);
    reader_localization_test_reset();
    return ok ? 0 : 1;
  }
  (void)printf("error=mode\n");
  return 2;
}
