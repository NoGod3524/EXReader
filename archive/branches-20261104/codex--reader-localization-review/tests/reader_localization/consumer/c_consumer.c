/* SPDX-License-Identifier: MIT */
/* Installed C consumer of EXReaderLocalization. It links only the installed
   package and its public header; nothing here includes the package sources.

   Modes:
     (no argument)      run the full internal check matrix
     --manifest         print the catalog for the out-of-process checker
     --matrix FILE      render the fixture lines in FILE and print one result
                        line per fixture, so the checker compares bytes it
                        fixed before this process started */
#if defined(_WIN32)
#define _CRT_SECURE_NO_WARNINGS 1
#endif
#include "reader_localization.h"

#include <locale.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int failures;

#define CHECK(condition, name) \
  do { if (!(condition)) { (void)printf("FAIL %s\n", name); ++failures; } } while (0)

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

static reader_localization_measurement make_measurement(void) {
  reader_localization_measurement measurement;
  memset(&measurement, 0, sizeof(measurement));
  measurement.struct_size = (uint32_t)sizeof(measurement);
  return measurement;
}

static reader_localization_message make_message(void) {
  reader_localization_message message;
  memset(&message, 0, sizeof(message));
  message.struct_size = (uint32_t)sizeof(message);
  return message;
}

static reader_localization_template make_template(void) {
  reader_localization_template row;
  memset(&row, 0, sizeof(row));
  row.struct_size = (uint32_t)sizeof(row);
  return row;
}

static int bytes_are(const unsigned char *bytes, size_t length, unsigned char value) {
  size_t i;
  for (i = 0; i < length; ++i) {
    if (bytes[i] != value) return 0;
  }
  return 1;
}

/* Local placeholder scanner: proves the shipped template uses exactly the
   indices the declared slot layout promises, without trusting the library. */
static int template_layout_ok(const char *text, uint32_t slots) {
  const char *cursor = text;
  unsigned seen = 0u;
  uint32_t count = 0u;
  while (*cursor != '\0') {
    if (*cursor == '{') {
      uint32_t index = 0u;
      size_t digits = 0u;
      ++cursor;
      while (*cursor >= '0' && *cursor <= '9') {
        index = index * 10u + (uint32_t)(*cursor - '0');
        ++cursor;
        ++digits;
        if (digits > 2u) return 0;
      }
      if (digits == 0u || *cursor != '}') return 0;
      ++cursor;
      if (index >= slots) return 0;
      if ((seen & (1u << index)) != 0u) return 0;
      seen |= 1u << index;
      ++count;
    } else if (*cursor == '}') {
      return 0;
    } else {
      ++cursor;
    }
  }
  if (slots == 0u) return count == 0u;
  return count == slots && seen == ((1u << slots) - 1u);
}

static int template_is_plain(const char *text) {
  const unsigned char *bytes = (const unsigned char *)text;
  size_t i;
  size_t length = strlen(text);
  if (length == 0u || length > 256u) return 0;
  for (i = 0; i < length; ++i) {
    if (bytes[i] == '\t' || bytes[i] == '\n' || bytes[i] == '\r') return 0;
    if (bytes[i] < 0x20u) return 0;
  }
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
    reader_localization_message message = make_message();
    if (reader_localization_message_at(i, &message) != READER_LOCALIZATION_OK) {
      (void)printf("ERROR\tmessage\t%lu\n", (unsigned long)i);
      return 1;
    }
    (void)printf("M\t%s\t%s\t%s\n", message.message_id, message.group, message.kinds);
  }
  for (i = 0; i < templates; ++i) {
    reader_localization_template row = make_template();
    if (reader_localization_template_at(i, &row) != READER_LOCALIZATION_OK) {
      (void)printf("ERROR\ttemplate\t%lu\n", (unsigned long)i);
      return 1;
    }
    (void)printf("T\t%s\t%s\t%s\n", row.message_id, row.locale, row.text);
  }
  return 0;
}

static int hex_value(int character) {
  if (character >= '0' && character <= '9') return character - '0';
  if (character >= 'a' && character <= 'f') return character - 'a' + 10;
  if (character >= 'A' && character <= 'F') return character - 'A' + 10;
  return -1;
}

typedef struct {
  reader_localization_param items[READER_LOCALIZATION_MAX_SLOTS];
  /* One byte past the value limit, so the fixture format can carry an
     over-long value and let the library refuse it instead of the parser. */
  char texts[READER_LOCALIZATION_MAX_SLOTS][READER_LOCALIZATION_MAX_VALUE_BYTES + 2u];
  size_t count;
} staged_params;

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

static int parse_spec(const char *spec, staged_params *staged) {
  const char *cursor = spec;
  staged->count = 0u;
  if (strcmp(spec, "-") == 0) return 1;
  while (*cursor != '\0') {
    char kind = *cursor;
    const char *value;
    size_t length;
    if (staged->count >= (size_t)READER_LOCALIZATION_MAX_SLOTS) return 0;
    if (cursor[1] != ':') return 0;
    value = cursor + 2;
    length = 0u;
    while (value[length] != '\0' && value[length] != '|') ++length;
    if (kind == 's') {
      size_t index = staged->count;
      if (!decode_hex(value, length, staged->texts[index], sizeof(staged->texts[index]))) return 0;
      staged->items[index] = text_param(staged->texts[index]);
    } else if (kind == 'd') {
      char number[32];
      if (length == 0u || length >= sizeof(number)) return 0;
      memcpy(number, value, length);
      number[length] = '\0';
      staged->items[staged->count] = int_param((int64_t)strtoll(number, NULL, 10));
    } else if (kind == 'u') {
      char number[32];
      if (length == 0u || length >= sizeof(number)) return 0;
      memcpy(number, value, length);
      number[length] = '\0';
      staged->items[staged->count] = uint_param((uint64_t)strtoull(number, NULL, 10));
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

static int run_matrix(const char *path) {
  FILE *file = fopen(path, "rb");
  char line[16384];
  if (file == NULL) {
    (void)printf("ERROR\topen\t%s\n", path);
    return 1;
  }
  while (fgets(line, (int)sizeof(line), file) != NULL) {
    char *fields[4];
    char *cursor = line;
    size_t count = 0u;
    size_t length = strlen(line);
    staged_params staged;
    reader_localization_context context;
    reader_localization_measurement measurement;
    reader_localization_status status;
    char buffer[READER_LOCALIZATION_MAX_OUTPUT_BYTES + 1u];
    unsigned char sentinel[READER_LOCALIZATION_MAX_OUTPUT_BYTES + 1u];
    size_t capacity;
    size_t produced;
    int untouched;

    while (length > 0u && (line[length - 1u] == '\n' || line[length - 1u] == '\r')) {
      line[length - 1u] = '\0';
      --length;
    }
    if (length == 0u || line[0] == '#') continue;
    while (count < 4u) {
      fields[count] = cursor;
      ++count;
      while (*cursor != '\0' && *cursor != '\t') ++cursor;
      if (*cursor == '\0') break;
      *cursor = '\0';
      ++cursor;
    }
    if (count < 4u) {
      (void)printf("ERROR\tline\t%s\n", line);
      fclose(file);
      return 1;
    }
    if (!parse_spec(fields[2], &staged)) {
      (void)printf("ERROR\tspec\t%s\n", fields[0]);
      fclose(file);
      return 1;
    }
    {
      uint32_t locale = 0u;
      if (reader_localization_parse_locale(fields[1], &locale) != READER_LOCALIZATION_OK) {
        (void)printf("ERROR\tlocale\t%s\n", fields[1]);
        fclose(file);
        return 1;
      }
      context = make_context(locale);
    }
    memset(buffer, 0, sizeof(buffer));
    memset(sentinel, 0xa5, sizeof(sentinel));
    memcpy(buffer, sentinel, sizeof(buffer));
    measurement = make_measurement();

    if (strcmp(fields[3], "-") == 0) {
      status = reader_localization_measure(&context, fields[0], staged.items, staged.count,
                                           &measurement);
      if (status != READER_LOCALIZATION_OK) {
        (void)printf("R\t%s\t%s\t%s\t%s\t%s\t-\t%s\t%lu\t%lu\n", fields[0], fields[1],
                     fields[2], fields[3], reader_localization_status_name(status), "-",
                     (unsigned long)measurement.bytes, (unsigned long)measurement.fallback);
        continue;
      }
      capacity = measurement.bytes;
    } else {
      capacity = (size_t)strtoul(fields[3], NULL, 10);
      measurement = make_measurement();
    }
    if (capacity > sizeof(buffer)) capacity = sizeof(buffer);
    status = reader_localization_format(&context, fields[0], staged.items, staged.count, buffer,
                                        capacity, &measurement);
    produced = status == READER_LOCALIZATION_OK ? strlen(buffer) : 0u;
    untouched = bytes_are((const unsigned char *)buffer, sizeof(buffer), 0xa5u);
    (void)printf("R\t%s\t%s\t%s\t%s\t%s\t", fields[0], fields[1], fields[2], fields[3],
                 reader_localization_status_name(status));
    print_hex(buffer, produced);
    (void)printf("\t%s\t%lu\t%lu\n", untouched ? "unchanged" : "written",
                 (unsigned long)measurement.bytes, (unsigned long)measurement.fallback);
  }
  fclose(file);
  return 0;
}

static void check_identity(void) {
  int status_value;
  char digest_a[65];
  char digest_b[65];
  CHECK(reader_localization_abi_version() == READER_LOCALIZATION_ABI_VERSION, "abi-version");
  CHECK(reader_localization_catalog_version() == READER_LOCALIZATION_CATALOG_FORMAT_VERSION,
        "catalog-version");
  CHECK(strcmp(reader_localization_locale_tag((uint32_t)READER_LOCALIZATION_LOCALE_ZH_CN),
               "zh-CN") == 0, "locale-tag-zh");
  CHECK(strcmp(reader_localization_locale_tag((uint32_t)READER_LOCALIZATION_LOCALE_EN_US),
               "en-US") == 0, "locale-tag-en");
  CHECK(reader_localization_locale_tag(0u) == NULL, "locale-tag-zero");
  CHECK(reader_localization_locale_tag(3u) == NULL, "locale-tag-three");
  for (status_value = 0; status_value <= (int)READER_LOCALIZATION_CATALOG; ++status_value) {
    const char *name = reader_localization_status_name((reader_localization_status)status_value);
    CHECK(name != NULL && name[0] != '\0', "status-name-present");
    CHECK(strcmp(name, "UNRECOGNIZED") != 0, "status-name-known");
  }
  CHECK(strcmp(reader_localization_status_name((reader_localization_status)99), "UNRECOGNIZED") == 0,
        "status-name-unknown");
  reader_localization_catalog_digest(digest_a);
  reader_localization_catalog_digest(digest_b);
  CHECK(strlen(digest_a) == 64u, "digest-length");
  CHECK(strcmp(digest_a, digest_b) == 0, "digest-stable");
  {
    size_t i;
    for (i = 0; i < 64u; ++i) {
      char character = digest_a[i];
      if (!((character >= '0' && character <= '9') || (character >= 'a' && character <= 'f'))) {
        CHECK(0, "digest-hex-lowercase");
        break;
      }
    }
  }
}

static void check_locales(void) {
  static const char *const accepted[] = {"zh", "zh-CN", "zh_cn", "ZH-Hans", "zh-Hans-CN",
                                         "en", "en-US", "en_us"};
  static const char *const refused[] = {"de-DE", "zh-CN-x-bogus", "en-GB", "", " zh", "zh ",
                                        "zh-Hans-CN-x-private"};
  size_t i;
  for (i = 0; i < sizeof(accepted) / sizeof(accepted[0]); ++i) {
    uint32_t locale = 0u;
    CHECK(reader_localization_parse_locale(accepted[i], &locale) == READER_LOCALIZATION_OK,
          "parse-locale-accepted");
    CHECK(reader_localization_locale_tag(locale) != NULL, "parse-locale-tag");
  }
  for (i = 0; i < sizeof(refused) / sizeof(refused[0]); ++i) {
    uint32_t locale = 12345u;
    CHECK(reader_localization_parse_locale(refused[i], &locale) ==
              READER_LOCALIZATION_UNKNOWN_LOCALE, "parse-locale-refused");
    CHECK(locale == 12345u, "parse-locale-untouched");
  }
  CHECK(reader_localization_parse_locale(NULL, NULL) == READER_LOCALIZATION_ARGUMENT,
        "parse-locale-null");
  {
    reader_localization_context context = make_context(0u);
    CHECK(reader_localization_open("zh-CN", &context) == READER_LOCALIZATION_OK, "open-zh");
    CHECK(context.locale == (uint32_t)READER_LOCALIZATION_LOCALE_ZH_CN, "open-zh-value");
    CHECK(reader_localization_open("fr-FR", &context) == READER_LOCALIZATION_UNKNOWN_LOCALE,
          "open-unknown");
    CHECK(context.locale == (uint32_t)READER_LOCALIZATION_LOCALE_ZH_CN, "open-unknown-untouched");
    context.struct_size = 4u;
    CHECK(reader_localization_open("en-US", &context) == READER_LOCALIZATION_ARGUMENT,
          "open-struct-size");
  }
}

static void check_catalog(void) {
  size_t messages = reader_localization_message_count();
  size_t templates = reader_localization_template_count();
  size_t i;
  CHECK(messages >= 60u, "message-count-floor");
  CHECK(templates == messages * 2u, "template-count-pairs");
  for (i = 0; i < messages; ++i) {
    reader_localization_message message = make_message();
    uint32_t slots;
    size_t locale_index;
    CHECK(reader_localization_message_at(i, &message) == READER_LOCALIZATION_OK, "message-at");
    if (message.message_id == NULL || message.group == NULL || message.kinds == NULL) {
      CHECK(0, "message-fields");
      continue;
    }
    slots = (uint32_t)strlen(message.kinds);
    CHECK(strlen(message.message_id) <= (size_t)READER_LOCALIZATION_MAX_MESSAGE_ID, "message-id-length");
    CHECK(slots <= READER_LOCALIZATION_MAX_SLOTS, "message-slot-limit");
    for (locale_index = 0; locale_index < slots; ++locale_index) {
      char kind = message.kinds[locale_index];
      if (kind != 's' && kind != 'd' && kind != 'u') {
        CHECK(0, "message-kind-character");
        break;
      }
    }
    for (locale_index = 0; locale_index < 2u; ++locale_index) {
      uint32_t locale = locale_index == 0u ? (uint32_t)READER_LOCALIZATION_LOCALE_ZH_CN
                                          : (uint32_t)READER_LOCALIZATION_LOCALE_EN_US;
      reader_localization_context context = make_context(locale);
      reader_localization_template row = make_template();
      CHECK(reader_localization_resolve(&context, message.message_id, &row) ==
                READER_LOCALIZATION_OK, "resolve-row");
      CHECK(row.fallback == 0u, "resolve-shipped-no-fallback");
      CHECK(row.slots == slots, "resolve-slots");
      CHECK(strcmp(row.message_id, message.message_id) == 0, "resolve-id");
      CHECK(row.locale != NULL && strcmp(row.locale, reader_localization_locale_tag(locale)) == 0,
            "resolve-locale");
      if (row.text == NULL) {
        CHECK(0, "resolve-text");
        continue;
      }
      CHECK(template_is_plain(row.text), "template-plain");
      CHECK(template_layout_ok(row.text, slots), "template-layout");
    }
  }
  for (i = 0; i < templates; ++i) {
    reader_localization_template row = make_template();
    CHECK(reader_localization_template_at(i, &row) == READER_LOCALIZATION_OK, "template-at");
    CHECK(row.fallback == 0u, "template-at-no-fallback");
  }
  {
    reader_localization_template row = make_template();
    reader_localization_template before = row;
    CHECK(reader_localization_template_at(templates, &row) == READER_LOCALIZATION_ARGUMENT,
          "template-at-range");
    CHECK(memcmp(&row, &before, sizeof(row)) == 0, "template-at-range-untouched");
    CHECK(reader_localization_template_at(0u, NULL) == READER_LOCALIZATION_ARGUMENT,
          "template-at-null");
    row.struct_size = 4u;
    CHECK(reader_localization_template_at(0u, &row) == READER_LOCALIZATION_ARGUMENT,
          "template-at-struct-size");
    {
      reader_localization_message message = make_message();
      CHECK(reader_localization_message_at(messages, &message) == READER_LOCALIZATION_ARGUMENT,
            "message-at-range");
      CHECK(reader_localization_message_at(0u, NULL) == READER_LOCALIZATION_ARGUMENT,
            "message-at-null");
    }
  }
}

static void check_refusals(void) {
  reader_localization_context en = make_context((uint32_t)READER_LOCALIZATION_LOCALE_EN_US);
  reader_localization_context zh = make_context((uint32_t)READER_LOCALIZATION_LOCALE_ZH_CN);
  reader_localization_param pair[3];
  reader_localization_measurement measurement = make_measurement();
  char buffer[64];
  unsigned char sentinel[64];

  pair[0] = int_param(1);
  pair[1] = int_param(2);
  memset(buffer, 0xa5, sizeof(buffer));
  memcpy(sentinel, buffer, sizeof(sentinel));

  CHECK(reader_localization_format(&en, "reader.reading.page", pair, 0u, buffer, sizeof(buffer),
                                   NULL) == READER_LOCALIZATION_PARAMETER_COUNT, "refuse-arity-zero");
  CHECK(memcmp(buffer, sentinel, sizeof(buffer)) == 0, "refuse-arity-zero-untouched");
  CHECK(reader_localization_format(&en, "reader.reading.page", pair, 3u, buffer, sizeof(buffer),
                                   NULL) == READER_LOCALIZATION_PARAMETER_COUNT, "refuse-arity-three");
  CHECK(reader_localization_format(&en, "reader.shelf.title", pair, 1u, buffer, sizeof(buffer),
                                   NULL) == READER_LOCALIZATION_PARAMETER_COUNT, "refuse-arity-one");
  CHECK(reader_localization_format(&en, "reader.reading.page", NULL, 2u, buffer, sizeof(buffer),
                                   NULL) == READER_LOCALIZATION_ARGUMENT, "refuse-null-params");
  pair[0] = text_param("x");
  pair[1] = int_param(2);
  CHECK(reader_localization_format(&en, "reader.reading.page", pair, 2u, buffer, sizeof(buffer),
                                   NULL) == READER_LOCALIZATION_PARAMETER_TYPE, "refuse-kind-string");
  pair[0] = int_param(1);
  pair[1] = uint_param(2u);
  CHECK(reader_localization_format(&en, "reader.reading.page", pair, 2u, buffer, sizeof(buffer),
                                   NULL) == READER_LOCALIZATION_PARAMETER_TYPE, "refuse-kind-unsigned");
  pair[0] = int_param(1);
  pair[1] = int_param(2);
  pair[0].kind = 7u;
  CHECK(reader_localization_format(&en, "reader.reading.page", pair, 2u, buffer, sizeof(buffer),
                                   NULL) == READER_LOCALIZATION_ARGUMENT, "refuse-kind-enum");
  pair[0] = int_param(1);
  pair[0].struct_size = 4u;
  CHECK(reader_localization_format(&en, "reader.reading.page", pair, 2u, buffer, sizeof(buffer),
                                   NULL) == READER_LOCALIZATION_ARGUMENT, "refuse-param-struct-size");
  pair[0] = text_param(NULL);
  CHECK(reader_localization_format(&en, "reader.shelf.book.missing", pair, 1u, buffer,
                                   sizeof(buffer), NULL) == READER_LOCALIZATION_ARGUMENT,
        "refuse-null-string-value");
  CHECK(reader_localization_format(&en, "reader.shelf.title", pair, 0u, buffer, sizeof(buffer),
                                   NULL) == READER_LOCALIZATION_OK, "zero-slot-ignores-params");
  CHECK(reader_localization_format(&en, "reader.does.not.exist", pair, 0u, buffer, sizeof(buffer),
                                   NULL) == READER_LOCALIZATION_UNKNOWN_MESSAGE, "refuse-unknown-id");
  CHECK(reader_localization_format(&en, NULL, pair, 0u, buffer, sizeof(buffer), NULL) ==
            READER_LOCALIZATION_ARGUMENT, "refuse-null-id");
  CHECK(reader_localization_format(&en, "", pair, 0u, buffer, sizeof(buffer), NULL) ==
            READER_LOCALIZATION_ARGUMENT, "refuse-empty-id");
  {
    char long_id[128];
    memset(long_id, 'a', sizeof(long_id) - 1u);
    long_id[sizeof(long_id) - 1u] = '\0';
    CHECK(reader_localization_format(&en, long_id, pair, 0u, buffer, sizeof(buffer), NULL) ==
              READER_LOCALIZATION_ARGUMENT, "refuse-long-id");
  }
  {
    reader_localization_context bad = en;
    bad.reserved[0] = 1u;
    CHECK(reader_localization_format(&bad, "reader.shelf.title", NULL, 0u, buffer, sizeof(buffer),
                                     NULL) == READER_LOCALIZATION_ARGUMENT, "refuse-reserved");
    bad = en;
    bad.struct_size = 8u;
    CHECK(reader_localization_format(&bad, "reader.shelf.title", NULL, 0u, buffer, sizeof(buffer),
                                     NULL) == READER_LOCALIZATION_ARGUMENT, "refuse-context-struct-size");
    CHECK(reader_localization_format(NULL, "reader.shelf.title", NULL, 0u, buffer, sizeof(buffer),
                                     NULL) == READER_LOCALIZATION_ARGUMENT, "refuse-null-context");
  }
  measurement.struct_size = 8u;
  CHECK(reader_localization_measure(&en, "reader.shelf.title", NULL, 0u, &measurement) ==
            READER_LOCALIZATION_ARGUMENT, "refuse-measurement-struct-size");
  CHECK(reader_localization_measure(&en, "reader.shelf.title", NULL, 0u, NULL) ==
            READER_LOCALIZATION_OK, "measure-null-output");
  /* Rendering never writes into a null buffer, whatever the capacity. */
  CHECK(reader_localization_format(&en, "reader.shelf.title", NULL, 0u, NULL, 0u, NULL) ==
            READER_LOCALIZATION_ARGUMENT, "refuse-null-buffer");
  CHECK(reader_localization_format(&en, "reader.shelf.title", NULL, 0u, NULL, 4096u, NULL) ==
            READER_LOCALIZATION_ARGUMENT, "refuse-null-buffer-large");
  CHECK(reader_localization_format(&zh, "reader.shelf.title", NULL, 0u, buffer, sizeof(buffer),
                                   NULL) == READER_LOCALIZATION_OK, "zh-basic");
}

static void check_values(void) {
  reader_localization_context en = make_context((uint32_t)READER_LOCALIZATION_LOCALE_EN_US);
  reader_localization_param param;
  char buffer[READER_LOCALIZATION_MAX_OUTPUT_BYTES + 1u];
  char big[READER_LOCALIZATION_MAX_VALUE_BYTES + 2u];
  unsigned char sentinel[sizeof(buffer)];
  size_t i;

  /* Malformed UTF-8 is refused, never repaired or copied through. */
  {
    static const char *const malformed[] = {
        "\xc0\xaf",         /* overlong two-byte */
        "\xed\xa0\x80",     /* UTF-16 surrogate */
        "\xf5\x80\x80\x80", /* lead byte above U+10FFFF */
        "\xf4\x90\x80\x80", /* four-byte encoding above U+10FFFF */
        "\xf0\x80\x80\x80", /* overlong four-byte */
        "\xe2\x82",         /* truncated three-byte at the end of the value */
        "\xf0\x9f\x98",     /* truncated four-byte at the end of the value */
        "\x80",             /* lone continuation byte */
        "\xfe"};
    for (i = 0; i < sizeof(malformed) / sizeof(malformed[0]); ++i) {
      param = text_param(malformed[i]);
      memset(buffer, 0xa5, sizeof(buffer));
      memcpy(sentinel, buffer, sizeof(sentinel));
      CHECK(reader_localization_format(&en, "reader.shelf.book.missing", &param, 1u, buffer,
                                       sizeof(buffer), NULL) == READER_LOCALIZATION_VALUE_INVALID,
            "refuse-malformed-utf8");
      CHECK(memcmp(buffer, sentinel, sizeof(buffer)) == 0, "refuse-malformed-utf8-untouched");
    }
  }
  /* Well-formed Unicode, including bidi controls and an emoji ZWJ sequence,
     passes through byte for byte. */
  {
    static const char *const valid[] = {
        "\xe4\xb9\xa6",                                  /* U+4E66 CJK */
        "\xf0\x9f\x93\x9a",                              /* U+1F4DA books */
        "\xf0\x9f\x91\xa8\xe2\x80\x8d\xf0\x9f\x91\xa9\xe2\x80\x8d\xf0\x9f\x91\xa7", /* family ZWJ */
        "\xd7\xa9\xd7\x9c\xd7\x95\xd7\x9d",             /* Hebrew */
        "\xd9\x85\xd8\xb1\xd8\xad\xd8\xa8\xd8\xa7",     /* Arabic */
        "e\xcc\x81",                                      /* e + combining acute */
        "\xe2\x80\xae",                                  /* U+202E right-to-left override */
        "\xf4\x8f\xbf\xbf",                              /* U+10FFFF, the last scalar */
        "\xc2\x80",                                       /* U+0080, the first two-byte scalar */
        "{0} %s %n $1 {{0}}",                            /* formatting-looking data */
        "a\tb\nc",
    };
    for (i = 0; i < sizeof(valid) / sizeof(valid[0]); ++i) {
      reader_localization_measurement measurement = make_measurement();
      size_t length;
      param = text_param(valid[i]);
      CHECK(reader_localization_measure(&en, "reader.shelf.book.missing", &param, 1u,
                                        &measurement) == READER_LOCALIZATION_OK, "measure-unicode");
      if (measurement.bytes > sizeof(buffer)) {
        CHECK(0, "measure-unicode-size");
        continue;
      }
      CHECK(reader_localization_format(&en, "reader.shelf.book.missing", &param, 1u, buffer,
                                       sizeof(buffer), NULL) == READER_LOCALIZATION_OK,
            "format-unicode");
      /* "<value> is unavailable" */
      length = strlen(valid[i]);
      CHECK(strncmp(buffer, valid[i], length) == 0, "unicode-verbatim");
      CHECK(strcmp(buffer + length, " is unavailable") == 0, "unicode-suffix");
    }
  }
  /* A value that itself looks like a template is data, not a second pass. */
  {
    param = text_param("{1}{0}");
    CHECK(reader_localization_format(&en, "reader.shelf.book.missing", &param, 1u, buffer,
                                     sizeof(buffer), NULL) == READER_LOCALIZATION_OK,
          "data-braces-ok");
    CHECK(strcmp(buffer, "{1}{0} is unavailable") == 0, "data-braces-verbatim");
  }
  /* Value limit: exactly the maximum is accepted, one byte more is refused. */
  memset(big, 'x', sizeof(big) - 1u);
  big[sizeof(big) - 1u] = '\0';
  big[READER_LOCALIZATION_MAX_VALUE_BYTES] = '\0';
  param = text_param(big);
  CHECK(reader_localization_measure(&en, "reader.shelf.book.missing", &param, 1u, NULL) ==
            READER_LOCALIZATION_OK, "value-at-limit");
  big[READER_LOCALIZATION_MAX_VALUE_BYTES] = 'x';
  big[READER_LOCALIZATION_MAX_VALUE_BYTES + 1u] = '\0';
  CHECK(reader_localization_measure(&en, "reader.shelf.book.missing", &param, 1u, NULL) ==
            READER_LOCALIZATION_VALUE_TOO_LONG, "value-over-limit");
}

static void check_numbers(void) {
  reader_localization_context en = make_context((uint32_t)READER_LOCALIZATION_LOCALE_EN_US);
  reader_localization_context zh = make_context((uint32_t)READER_LOCALIZATION_LOCALE_ZH_CN);
  reader_localization_param param;
  char buffer[64];
  char before[64];

  param = int_param(1234567);
  CHECK(reader_localization_format(&en, "reader.shelf.count", &param, 1u, buffer, sizeof(buffer),
                                   NULL) == READER_LOCALIZATION_OK, "number-en");
  CHECK(strcmp(buffer, "1234567 books") == 0, "number-no-grouping-en");
  {
    /* The library must not follow the process locale: a German or Japanese
       setlocale() cannot introduce separators, non-ASCII digits or a different
       rendering. */
    (void)setlocale(LC_ALL, "de_DE.UTF-8");
    memcpy(before, buffer, sizeof(before));
    CHECK(reader_localization_format(&en, "reader.shelf.count", &param, 1u, buffer, sizeof(buffer),
                                     NULL) == READER_LOCALIZATION_OK, "number-after-setlocale");
    CHECK(strcmp(buffer, before) == 0, "number-locale-independent");
    (void)setlocale(LC_ALL, "ja_JP.UTF-8");
    CHECK(reader_localization_format(&en, "reader.shelf.count", &param, 1u, buffer, sizeof(buffer),
                                     NULL) == READER_LOCALIZATION_OK, "number-after-setlocale-ja");
    CHECK(strcmp(buffer, before) == 0, "number-locale-independent-ja");
    (void)setlocale(LC_ALL, "C");
  }
  param = int_param(1234567);
  CHECK(reader_localization_format(&zh, "reader.shelf.count", &param, 1u, buffer, sizeof(buffer),
                                   NULL) == READER_LOCALIZATION_OK, "number-zh");
  CHECK(strcmp(buffer, "1234567 本") == 0, "number-no-grouping-zh");
  param = int_param(INT64_MIN);
  CHECK(reader_localization_format(&en, "reader.error.limit", &param, 1u, buffer, sizeof(buffer),
                                   NULL) == READER_LOCALIZATION_OK, "number-int64-min");
  CHECK(strcmp(buffer, "Only -9223372036854775808 books can be added at once") == 0,
        "number-int64-min-text");
  param = int_param(INT64_MAX);
  CHECK(reader_localization_format(&en, "reader.error.limit", &param, 1u, buffer, sizeof(buffer),
                                   NULL) == READER_LOCALIZATION_OK, "number-int64-max");
  CHECK(strncmp(buffer, "Only 9223372036854775807 books", 28u) == 0, "number-int64-max-text");
  {
    /* Unsigned slots exist in the layout even though no shipped message
       declares one; the kind check must still reject a mismatched pair rather
       than silently reinterpreting UINT64_MAX as a negative number. */
    reader_localization_param numeric[2];
    numeric[0] = uint_param(UINT64_MAX);
    numeric[1] = uint_param(0u);
    CHECK(reader_localization_measure(&en, "reader.reading.page", numeric, 2u, NULL) ==
              READER_LOCALIZATION_PARAMETER_TYPE, "unsigned-rejected-for-signed-slot");
  }
}

static void check_capacity(void) {
  reader_localization_context en = make_context((uint32_t)READER_LOCALIZATION_LOCALE_EN_US);
  reader_localization_param params[3];
  reader_localization_measurement measurement = make_measurement();
  char buffer[128];
  unsigned char sentinel[128];
  size_t required;

  params[0] = text_param("Ulysses");
  params[1] = text_param("James Joyce");
  params[2] = int_param(37);
  CHECK(reader_localization_measure(&en, "reader.a11y.shelf.book", params, 3u, &measurement) ==
            READER_LOCALIZATION_OK, "capacity-measure");
  CHECK(measurement.bytes > 1u && measurement.slots == 3u && measurement.fallback == 0u,
        "capacity-measure-fields");
  required = measurement.bytes;
  CHECK(reader_localization_format(&en, "reader.a11y.shelf.book", params, 3u, buffer, required,
                                   NULL) == READER_LOCALIZATION_OK, "capacity-exact");
  CHECK(strlen(buffer) + 1u == required, "capacity-exact-length");
  CHECK(strcmp(buffer, "Ulysses by James Joyce, 37% read") == 0, "capacity-exact-text");

  memset(buffer, 0xa5, sizeof(buffer));
  memcpy(sentinel, buffer, sizeof(sentinel));
  {
    reader_localization_measurement short_measure = make_measurement();
    CHECK(reader_localization_format(&en, "reader.a11y.shelf.book", params, 3u, buffer,
                                     required - 1u, &short_measure) == READER_LOCALIZATION_CAPACITY,
          "capacity-short");
    CHECK(short_measure.bytes == required, "capacity-short-reports");
    CHECK(memcmp(buffer, sentinel, sizeof(buffer)) == 0, "capacity-short-untouched-buffer");
  }
  CHECK(reader_localization_format(&en, "reader.a11y.shelf.book", params, 3u, buffer, 1u, NULL) ==
            READER_LOCALIZATION_CAPACITY, "capacity-one");
  CHECK(memcmp(buffer, sentinel, sizeof(buffer)) == 0, "capacity-one-untouched");
  CHECK(reader_localization_format(&en, "reader.a11y.shelf.book", params, 3u, buffer, 0u, NULL) ==
            READER_LOCALIZATION_CAPACITY, "capacity-zero");

  memset(buffer, 0xa5, sizeof(buffer));
  CHECK(reader_localization_format(&en, "reader.a11y.shelf.book", params, 3u, buffer,
                                   sizeof(buffer), NULL) == READER_LOCALIZATION_OK,
        "capacity-extra");
  CHECK((unsigned char)buffer[required] == 0xa5u, "capacity-tail-untouched");
  CHECK(buffer[required - 1u] == '\0', "capacity-terminator");
}

static void check_output_limit(void) {
  reader_localization_context en = make_context((uint32_t)READER_LOCALIZATION_LOCALE_EN_US);
  reader_localization_param params[2];
  char first[READER_LOCALIZATION_MAX_VALUE_BYTES + 1u];
  char second[READER_LOCALIZATION_MAX_VALUE_BYTES + 1u];
  char buffer[READER_LOCALIZATION_MAX_OUTPUT_BYTES + 1u];
  unsigned char sentinel[sizeof(buffer)];
  reader_localization_measurement measurement = make_measurement();
  reader_localization_status status;
  /* "Move {0} to {1}" is 9 literal bytes, so 1024 + 1015 fills the 2048-byte
     rendered limit exactly and 1024 + 1016 exceeds it. */
  memset(first, 'a', sizeof(first));
  first[sizeof(first) - 1u] = '\0';
  memset(second, 'b', sizeof(second));
  second[sizeof(second) - 1u] = '\0';
  second[1015] = '\0';
  params[0] = text_param(first);
  params[1] = text_param(second);
  status = reader_localization_measure(&en, "reader.organize.move", params, 2u, &measurement);
  CHECK(status == READER_LOCALIZATION_OK, "limit-at-boundary-measure");
  CHECK(measurement.bytes == (size_t)READER_LOCALIZATION_MAX_OUTPUT_BYTES + 1u,
        "limit-at-boundary-bytes");
  CHECK(reader_localization_format(&en, "reader.organize.move", params, 2u, buffer, sizeof(buffer),
                                   NULL) == READER_LOCALIZATION_OK, "limit-at-boundary-format");
  second[1015] = 'b';
  second[1016] = '\0';
  memset(buffer, 0xa5, sizeof(buffer));
  memcpy(sentinel, buffer, sizeof(sentinel));
  measurement = make_measurement();
  CHECK(reader_localization_measure(&en, "reader.organize.move", params, 2u, &measurement) ==
            READER_LOCALIZATION_LIMIT, "limit-over-measure");
  CHECK(measurement.bytes == 0u, "limit-measurement-untouched");
  CHECK(reader_localization_format(&en, "reader.organize.move", params, 2u, buffer, sizeof(buffer),
                                   NULL) == READER_LOCALIZATION_LIMIT, "limit-over-format");
  CHECK(memcmp(buffer, sentinel, sizeof(buffer)) == 0, "limit-over-untouched");
}

int main(int argc, char **argv) {
  if (argc > 1 && strcmp(argv[1], "--manifest") == 0) {
    return print_manifest();
  }
  if (argc > 2 && strcmp(argv[1], "--matrix") == 0) {
    return run_matrix(argv[2]);
  }
  check_identity();
  check_locales();
  check_catalog();
  check_refusals();
  check_values();
  check_numbers();
  check_capacity();
  check_output_limit();
  (void)printf("CONSUMER\tc\t%lu\tfailures\n", (unsigned long)failures);
  return failures == 0 ? 0 : 1;
}
