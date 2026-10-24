/* SPDX-License-Identifier: MIT */
/* Strict renderer for the fixed reader catalog.

   Order of work in one call: validate the caller's context, the message id,
   the parameter count, the parameter kinds, the string values, the template
   layout, the rendered length and only then the caller's capacity. Nothing is
   written to a caller buffer before the rendered length is known, so a refused
   call cannot leave a partial string behind. */
#include "internal.h"
#include "test_hooks.h"

#include <string.h>

#if defined(READER_LOCALIZATION_TEST_HOOKS)
/* Test-hook build only: a mutating override table used by the Actions worker to
   prove fallback and self-inconsistent-template refusal. The production build
   has no mutable global state at all. */
#define RL_TEST_OVERRIDES 4
typedef struct {
  size_t message;
  uint32_t locale;
  const char *replacement; /* NULL drops the row */
} rl_override;
static rl_override rl_overrides[RL_TEST_OVERRIDES];
static size_t rl_override_count;

static int rl_override_lookup(size_t message, uint32_t locale, const char **replacement) {
  size_t i;
  for (i = 0; i < rl_override_count; ++i) {
    if (rl_overrides[i].message == message && rl_overrides[i].locale == locale) {
      *replacement = rl_overrides[i].replacement;
      return 1;
    }
  }
  return 0;
}

static int rl_override_set(const char *message_id, uint32_t locale, const char *replacement);
#endif

size_t rl_slot_count(const char *kinds) { return strlen(kinds); }

int rl_strlen_bounded(const char *text, size_t limit, size_t *length) {
  size_t i;
  for (i = 0; i < limit; ++i) {
    if (text[i] == '\0') {
      *length = i;
      return 1;
    }
  }
  return 0;
}

int rl_utf8_valid(const char *text, size_t length) {
  const unsigned char *bytes = (const unsigned char *)text;
  size_t i = 0u;
  while (i < length) {
    unsigned char first = bytes[i];
    if (first < 0x80u) {
      i += 1u;
      continue;
    }
    if (first >= 0xc2u && first <= 0xdfu) {
      if (i + 1u >= length) return 0;
      if ((bytes[i + 1u] & 0xc0u) != 0x80u) return 0;
      i += 2u;
      continue;
    }
    if (first >= 0xe0u && first <= 0xefu) {
      unsigned char second;
      unsigned char third;
      if (i + 2u >= length) return 0;
      second = bytes[i + 1u];
      third = bytes[i + 2u];
      if ((second & 0xc0u) != 0x80u || (third & 0xc0u) != 0x80u) return 0;
      if (first == 0xe0u && second < 0xa0u) return 0; /* overlong */
      if (first == 0xedu && second > 0x9fu) return 0; /* surrogate */
      i += 3u;
      continue;
    }
    if (first >= 0xf0u && first <= 0xf4u) {
      if (i + 3u >= length) return 0;
      if ((bytes[i + 1u] & 0xc0u) != 0x80u || (bytes[i + 2u] & 0xc0u) != 0x80u ||
          (bytes[i + 3u] & 0xc0u) != 0x80u) {
        return 0;
      }
      if (first == 0xf0u && bytes[i + 1u] < 0x90u) return 0; /* overlong */
      if (first == 0xf4u && bytes[i + 1u] > 0x8fu) return 0; /* above U+10FFFF */
      i += 4u;
      continue;
    }
    return 0; /* continuation byte, 0xc0/0xc1 or 0xf5..0xff */
  }
  return 1;
}

static int rl_ascii_lower(int value) {
  if (value >= 'A' && value <= 'Z') return value - 'A' + 'a';
  return value;
}

static int rl_tag_equals(const char *tag, const char *lowercase_literal) {
  while (*tag != '\0' && *lowercase_literal != '\0') {
    if (rl_ascii_lower((unsigned char)*tag) != (unsigned char)*lowercase_literal) return 0;
    ++tag;
    ++lowercase_literal;
  }
  return *tag == '\0' && *lowercase_literal == '\0';
}

reader_localization_status reader_localization_parse_locale(const char *tag, uint32_t *locale) {
  static const char *const zh_tags[] = {"zh", "zh-cn", "zh-hans", "zh-hans-cn"};
  static const char *const en_tags[] = {"en", "en-us"};
  char normalized[16];
  size_t length = 0u;
  size_t i;

  if (tag == NULL || locale == NULL) return READER_LOCALIZATION_ARGUMENT;
  if (!rl_strlen_bounded(tag, sizeof(normalized), &length)) return READER_LOCALIZATION_UNKNOWN_LOCALE;
  for (i = 0u; i < length; ++i) {
    char value = tag[i];
    if (value == '_') {
      value = '-';
    } else if (value >= 'A' && value <= 'Z') {
      value = (char)(value - 'A' + 'a');
    } else if ((value < 'a' || value > 'z') && (value < '0' || value > '9')) {
      return READER_LOCALIZATION_UNKNOWN_LOCALE;
    }
    normalized[i] = value;
  }
  normalized[length] = '\0';

  for (i = 0u; i < sizeof(zh_tags) / sizeof(zh_tags[0]); ++i) {
    if (rl_tag_equals(normalized, zh_tags[i])) {
      *locale = (uint32_t)READER_LOCALIZATION_LOCALE_ZH_CN;
      return READER_LOCALIZATION_OK;
    }
  }
  for (i = 0u; i < sizeof(en_tags) / sizeof(en_tags[0]); ++i) {
    if (rl_tag_equals(normalized, en_tags[i])) {
      *locale = (uint32_t)READER_LOCALIZATION_LOCALE_EN_US;
      return READER_LOCALIZATION_OK;
    }
  }
  return READER_LOCALIZATION_UNKNOWN_LOCALE;
}

uint32_t reader_localization_abi_version(void) { return READER_LOCALIZATION_ABI_VERSION; }

int reader_localization_catalog_version(void) { return READER_LOCALIZATION_CATALOG_FORMAT_VERSION; }

const char *reader_localization_status_name(reader_localization_status status) {
  switch (status) {
    case READER_LOCALIZATION_OK: return "OK";
    case READER_LOCALIZATION_ARGUMENT: return "ARGUMENT";
    case READER_LOCALIZATION_UNKNOWN_MESSAGE: return "UNKNOWN_MESSAGE";
    case READER_LOCALIZATION_UNKNOWN_LOCALE: return "UNKNOWN_LOCALE";
    case READER_LOCALIZATION_PARAMETER_COUNT: return "PARAMETER_COUNT";
    case READER_LOCALIZATION_PARAMETER_TYPE: return "PARAMETER_TYPE";
    case READER_LOCALIZATION_VALUE_INVALID: return "VALUE_INVALID";
    case READER_LOCALIZATION_VALUE_TOO_LONG: return "VALUE_TOO_LONG";
    case READER_LOCALIZATION_CAPACITY: return "CAPACITY";
    case READER_LOCALIZATION_LIMIT: return "LIMIT";
    case READER_LOCALIZATION_CATALOG: return "CATALOG";
    default: return "UNRECOGNIZED";
  }
}

const char *reader_localization_locale_tag(uint32_t locale) {
  if (locale == (uint32_t)READER_LOCALIZATION_LOCALE_ZH_CN) return "zh-CN";
  if (locale == (uint32_t)READER_LOCALIZATION_LOCALE_EN_US) return "en-US";
  return NULL;
}

reader_localization_status reader_localization_open(const char *locale_tag,
                                                    reader_localization_context *out) {
  uint32_t locale = 0u;
  reader_localization_status status;
  if (out == NULL || out->struct_size != (uint32_t)sizeof(reader_localization_context)) {
    return READER_LOCALIZATION_ARGUMENT;
  }
  status = reader_localization_parse_locale(locale_tag, &locale);
  if (status != READER_LOCALIZATION_OK) return status;
  out->locale = locale;
  out->reserved[0] = 0u;
  out->reserved[1] = 0u;
  return READER_LOCALIZATION_OK;
}

static reader_localization_status rl_context_valid(const reader_localization_context *context) {
  if (context == NULL) return READER_LOCALIZATION_ARGUMENT;
  if (context->struct_size != (uint32_t)sizeof(reader_localization_context)) {
    return READER_LOCALIZATION_ARGUMENT;
  }
  if (context->locale != (uint32_t)READER_LOCALIZATION_LOCALE_ZH_CN &&
      context->locale != (uint32_t)READER_LOCALIZATION_LOCALE_EN_US) {
    return READER_LOCALIZATION_ARGUMENT;
  }
  if (context->reserved[0] != 0u || context->reserved[1] != 0u) return READER_LOCALIZATION_ARGUMENT;
  return READER_LOCALIZATION_OK;
}

static reader_localization_status rl_find_message(const char *message_id, size_t *index) {
  size_t length = 0u;
  size_t i;
  if (message_id == NULL) return READER_LOCALIZATION_ARGUMENT;
  if (!rl_strlen_bounded(message_id, (size_t)READER_LOCALIZATION_MAX_MESSAGE_ID + 1u, &length)) {
    return READER_LOCALIZATION_ARGUMENT;
  }
  if (length == 0u) return READER_LOCALIZATION_ARGUMENT;
  for (i = 0u; i < rl_message_count; ++i) {
    if (strcmp(rl_messages[i].id, message_id) == 0) {
      *index = i;
      return READER_LOCALIZATION_OK;
    }
  }
  return READER_LOCALIZATION_UNKNOWN_MESSAGE;
}

static const char *rl_shipped_row(size_t index, uint32_t locale) {
  if (locale == (uint32_t)READER_LOCALIZATION_LOCALE_ZH_CN) return rl_zh_templates[index];
  return rl_en_templates[index];
}

static const char *rl_requested_row(size_t index, uint32_t locale) {
  const char *text = rl_shipped_row(index, locale);
#if defined(READER_LOCALIZATION_TEST_HOOKS)
  {
    const char *replacement = NULL;
    if (rl_override_lookup(index, locale, &replacement)) text = replacement;
  }
#endif
  return text;
}

/* Requested locale first, then en-US with fallback = 1. A missing en-US row is
   a missing message, never an empty string. */
static const char *rl_resolve_text(size_t index, uint32_t locale, uint32_t *fallback) {
  const char *text = rl_requested_row(index, locale);
  if (text != NULL) {
    if (fallback != NULL) *fallback = 0u;
    return text;
  }
  if (locale != (uint32_t)READER_LOCALIZATION_LOCALE_EN_US) {
    text = rl_requested_row(index, (uint32_t)READER_LOCALIZATION_LOCALE_EN_US);
    if (text != NULL) {
      if (fallback != NULL) *fallback = 1u;
      return text;
    }
  }
  return NULL;
}

size_t reader_localization_message_count(void) { return rl_message_count; }

size_t reader_localization_template_count(void) { return rl_message_count * (size_t)RL_LOCALE_COUNT; }

reader_localization_status reader_localization_message_at(size_t index,
                                                          reader_localization_message *out) {
  if (out == NULL || out->struct_size != (uint32_t)sizeof(reader_localization_message)) {
    return READER_LOCALIZATION_ARGUMENT;
  }
  if (index >= rl_message_count) return READER_LOCALIZATION_ARGUMENT;
  out->message_id = rl_messages[index].id;
  out->group = rl_messages[index].group;
  out->kinds = rl_messages[index].kinds;
  out->slots = (uint32_t)rl_slot_count(rl_messages[index].kinds);
  out->reserved = 0u;
  return READER_LOCALIZATION_OK;
}

reader_localization_status reader_localization_template_at(size_t index,
                                                           reader_localization_template *out) {
  size_t message_index;
  size_t locale_index;
  uint32_t locale;
  const char *text;
  if (out == NULL || out->struct_size != (uint32_t)sizeof(reader_localization_template)) {
    return READER_LOCALIZATION_ARGUMENT;
  }
  if (index >= rl_message_count * (size_t)RL_LOCALE_COUNT) return READER_LOCALIZATION_ARGUMENT;
  message_index = index / (size_t)RL_LOCALE_COUNT;
  locale_index = index % (size_t)RL_LOCALE_COUNT;
  locale = locale_index == 0u ? (uint32_t)READER_LOCALIZATION_LOCALE_ZH_CN
                              : (uint32_t)READER_LOCALIZATION_LOCALE_EN_US;
  /* Enumeration reports shipped rows only, so it stays independent of the test
     hooks and of fallback. */
  text = rl_shipped_row(message_index, locale);
  if (text == NULL) return READER_LOCALIZATION_CATALOG;
  out->message_id = rl_messages[message_index].id;
  out->locale = reader_localization_locale_tag(locale);
  out->text = text;
  out->slots = (uint32_t)rl_slot_count(rl_messages[message_index].kinds);
  out->fallback = 0u;
  out->reserved = 0u;
  return READER_LOCALIZATION_OK;
}

reader_localization_status reader_localization_resolve(const reader_localization_context *context,
                                                       const char *message_id,
                                                       reader_localization_template *out) {
  reader_localization_status status;
  size_t index = 0u;
  uint32_t fallback = 0u;
  const char *text;

  status = rl_context_valid(context);
  if (status != READER_LOCALIZATION_OK) return status;
  if (out == NULL || out->struct_size != (uint32_t)sizeof(reader_localization_template)) {
    return READER_LOCALIZATION_ARGUMENT;
  }
  status = rl_find_message(message_id, &index);
  if (status != READER_LOCALIZATION_OK) return status;
  text = rl_resolve_text(index, context->locale, &fallback);
  if (text == NULL) return READER_LOCALIZATION_UNKNOWN_MESSAGE;
  out->message_id = rl_messages[index].id;
  out->locale = reader_localization_locale_tag(context->locale);
  out->text = text;
  out->slots = (uint32_t)rl_slot_count(rl_messages[index].kinds);
  out->fallback = fallback;
  out->reserved = 0u;
  return READER_LOCALIZATION_OK;
}

typedef struct {
  const char *texts[READER_LOCALIZATION_MAX_SLOTS];
  size_t lengths[READER_LOCALIZATION_MAX_SLOTS];
  char numbers[READER_LOCALIZATION_MAX_SLOTS][24];
} rl_slots;

static size_t rl_format_decimal(uint64_t magnitude, int negative, char *out) {
  char digits[20];
  size_t count = 0u;
  size_t written = 0u;
  size_t i;
  do {
    digits[count] = (char)('0' + (int)(magnitude % 10u));
    ++count;
    magnitude /= 10u;
  } while (magnitude != 0u);
  if (negative) {
    out[written] = '-';
    ++written;
  }
  for (i = count; i > 0u; --i) {
    out[written] = digits[i - 1u];
    ++written;
  }
  out[written] = '\0';
  return written;
}

static reader_localization_status rl_prepare(const reader_localization_context *context,
                                             const char *message_id,
                                             const reader_localization_param *params,
                                             size_t param_count, const char **out_text,
                                             uint32_t *out_slots, uint32_t *out_fallback,
                                             rl_slots *values) {
  reader_localization_status status;
  size_t index = 0u;
  uint32_t slot_count;
  uint32_t i;
  const char *text;

  status = rl_context_valid(context);
  if (status != READER_LOCALIZATION_OK) return status;
  status = rl_find_message(message_id, &index);
  if (status != READER_LOCALIZATION_OK) return status;
  text = rl_resolve_text(index, context->locale, out_fallback);
  if (text == NULL) return READER_LOCALIZATION_UNKNOWN_MESSAGE;
  slot_count = (uint32_t)rl_slot_count(rl_messages[index].kinds);
  if (slot_count > READER_LOCALIZATION_MAX_SLOTS) return READER_LOCALIZATION_CATALOG;
  if (param_count != (size_t)slot_count) return READER_LOCALIZATION_PARAMETER_COUNT;
  if (slot_count > 0u && params == NULL) return READER_LOCALIZATION_ARGUMENT;

  for (i = 0u; i < slot_count; ++i) {
    const reader_localization_param *param = &params[i];
    char expected = rl_messages[index].kinds[i];
    if (param->struct_size != (uint32_t)sizeof(reader_localization_param)) {
      return READER_LOCALIZATION_ARGUMENT;
    }
    if (param->kind != (uint32_t)READER_LOCALIZATION_PARAM_STRING &&
        param->kind != (uint32_t)READER_LOCALIZATION_PARAM_INT &&
        param->kind != (uint32_t)READER_LOCALIZATION_PARAM_UNSIGNED) {
      return READER_LOCALIZATION_ARGUMENT;
    }
    if (expected == 's') {
      size_t length = 0u;
      if (param->kind != (uint32_t)READER_LOCALIZATION_PARAM_STRING) {
        return READER_LOCALIZATION_PARAMETER_TYPE;
      }
      if (param->string == NULL) return READER_LOCALIZATION_ARGUMENT;
      if (!rl_strlen_bounded(param->string, (size_t)READER_LOCALIZATION_MAX_VALUE_BYTES + 1u,
                             &length)) {
        return READER_LOCALIZATION_VALUE_TOO_LONG;
      }
      if (!rl_utf8_valid(param->string, length)) return READER_LOCALIZATION_VALUE_INVALID;
      values->texts[i] = param->string;
      values->lengths[i] = length;
    } else if (expected == 'd') {
      uint64_t magnitude;
      int negative;
      if (param->kind != (uint32_t)READER_LOCALIZATION_PARAM_INT) {
        return READER_LOCALIZATION_PARAMETER_TYPE;
      }
      negative = param->integer < 0;
      magnitude = negative ? (uint64_t)(-(param->integer + 1)) + 1u : (uint64_t)param->integer;
      values->lengths[i] = rl_format_decimal(magnitude, negative, values->numbers[i]);
      values->texts[i] = values->numbers[i];
    } else if (expected == 'u') {
      if (param->kind != (uint32_t)READER_LOCALIZATION_PARAM_UNSIGNED) {
        return READER_LOCALIZATION_PARAMETER_TYPE;
      }
      values->lengths[i] = rl_format_decimal(param->unsigned_integer, 0, values->numbers[i]);
      values->texts[i] = values->numbers[i];
    } else {
      return READER_LOCALIZATION_CATALOG;
    }
  }

  *out_text = text;
  *out_slots = slot_count;
  return READER_LOCALIZATION_OK;
}

/* Validates the placeholder layout and copies (or measures) the rendered text.
   Every slot index must appear exactly once and stay below the declared slot
   count; a template that breaks that rule is refused as CATALOG instead of
   rendering a partial or duplicated value. */
static reader_localization_status rl_walk(const char *text, uint32_t slot_count,
                                          const rl_slots *values, char *out, size_t capacity,
                                          size_t *out_length) {
  const char *cursor = text;
  size_t total = 0u;
  uint32_t seen = 0u;

  while (*cursor != '\0') {
    if (*cursor == '{') {
      uint32_t index = 0u;
      size_t digits = 0u;
      ++cursor;
      while (*cursor >= '0' && *cursor <= '9') {
        if (digits >= 2u) return READER_LOCALIZATION_CATALOG;
        index = index * 10u + (uint32_t)(*cursor - '0');
        ++cursor;
        ++digits;
      }
      if (digits == 0u || *cursor != '}') return READER_LOCALIZATION_CATALOG;
      ++cursor;
      if (index >= slot_count) return READER_LOCALIZATION_CATALOG;
      if ((seen & (1u << index)) != 0u) return READER_LOCALIZATION_CATALOG;
      seen |= 1u << index;
      if (out != NULL) {
        if (total > capacity) return READER_LOCALIZATION_CAPACITY;
        if (values->lengths[index] > capacity - total) return READER_LOCALIZATION_CAPACITY;
        if (values->lengths[index] > 0u) {
          memcpy(out + total, values->texts[index], values->lengths[index]);
        }
      }
      total += values->lengths[index];
    } else if (*cursor == '}') {
      return READER_LOCALIZATION_CATALOG;
    } else {
      if (out != NULL) {
        if (total >= capacity) return READER_LOCALIZATION_CAPACITY;
        out[total] = *cursor;
      }
      total += 1u;
      ++cursor;
    }
  }

  if (slot_count == 0u) {
    if (seen != 0u) return READER_LOCALIZATION_CATALOG;
  } else if (seen != ((1u << slot_count) - 1u)) {
    return READER_LOCALIZATION_CATALOG;
  }
  *out_length = total;
  return READER_LOCALIZATION_OK;
}

static reader_localization_status rl_measurement_ready(
    const reader_localization_measurement *measurement) {
  if (measurement == NULL) return READER_LOCALIZATION_OK;
  if (measurement->struct_size != (uint32_t)sizeof(reader_localization_measurement)) {
    return READER_LOCALIZATION_ARGUMENT;
  }
  return READER_LOCALIZATION_OK;
}

static void rl_fill_measurement(reader_localization_measurement *measurement, size_t bytes,
                                uint32_t slots, uint32_t fallback) {
  if (measurement == NULL) return;
  measurement->bytes = bytes;
  measurement->slots = slots;
  measurement->fallback = fallback;
  measurement->reserved = 0u;
}

reader_localization_status reader_localization_measure(const reader_localization_context *context,
                                                       const char *message_id,
                                                       const reader_localization_param *params,
                                                       size_t param_count,
                                                       reader_localization_measurement *out) {
  reader_localization_status status;
  rl_slots values;
  const char *text = NULL;
  uint32_t slot_count = 0u;
  uint32_t fallback = 0u;
  size_t required = 0u;

  memset(&values, 0, sizeof(values));
  status = rl_measurement_ready(out);
  if (status != READER_LOCALIZATION_OK) return status;
  status = rl_prepare(context, message_id, params, param_count, &text, &slot_count, &fallback,
                      &values);
  if (status != READER_LOCALIZATION_OK) return status;
  status = rl_walk(text, slot_count, &values, NULL, 0u, &required);
  if (status != READER_LOCALIZATION_OK) return status;
  if (required > (size_t)READER_LOCALIZATION_MAX_OUTPUT_BYTES) return READER_LOCALIZATION_LIMIT;
  rl_fill_measurement(out, required + 1u, slot_count, fallback);
  return READER_LOCALIZATION_OK;
}

reader_localization_status reader_localization_format(const reader_localization_context *context,
                                                      const char *message_id,
                                                      const reader_localization_param *params,
                                                      size_t param_count, char *out_text,
                                                      size_t out_bytes,
                                                      reader_localization_measurement *out_measurement) {
  reader_localization_status status;
  rl_slots values;
  const char *text = NULL;
  uint32_t slot_count = 0u;
  uint32_t fallback = 0u;
  size_t required = 0u;
  size_t written = 0u;

  memset(&values, 0, sizeof(values));
  status = rl_measurement_ready(out_measurement);
  if (status != READER_LOCALIZATION_OK) return status;
  status = rl_prepare(context, message_id, params, param_count, &text, &slot_count, &fallback,
                      &values);
  if (status != READER_LOCALIZATION_OK) return status;
  status = rl_walk(text, slot_count, &values, NULL, 0u, &required);
  if (status != READER_LOCALIZATION_OK) return status;
  if (required > (size_t)READER_LOCALIZATION_MAX_OUTPUT_BYTES) return READER_LOCALIZATION_LIMIT;
  if (out_text == NULL) return READER_LOCALIZATION_ARGUMENT;
  if (out_bytes < required + 1u) {
    /* The only refusal that reports: the caller learns the size it needs while
       its buffer keeps every previous byte. */
    rl_fill_measurement(out_measurement, required + 1u, slot_count, fallback);
    return READER_LOCALIZATION_CAPACITY;
  }
  status = rl_walk(text, slot_count, &values, out_text, out_bytes, &written);
  if (status != READER_LOCALIZATION_OK) return status;
  out_text[written] = '\0';
  rl_fill_measurement(out_measurement, written + 1u, slot_count, fallback);
  return READER_LOCALIZATION_OK;
}

void reader_localization_catalog_digest(char out_hex[65]) {
  static const char hex[] = "0123456789abcdef";
  rl_sha256 hash;
  unsigned char digest[32];
  size_t order[RL_MESSAGE_COUNT];
  size_t i;
  size_t j;

  for (i = 0u; i < (size_t)RL_MESSAGE_COUNT; ++i) order[i] = i;
  for (i = 1u; i < (size_t)RL_MESSAGE_COUNT; ++i) {
    size_t value = order[i];
    j = i;
    while (j > 0u && strcmp(rl_messages[order[j - 1u]].id, rl_messages[value].id) > 0) {
      order[j] = order[j - 1u];
      --j;
    }
    order[j] = value;
  }

  rl_sha256_init(&hash);
  rl_sha256_update_string(&hash, "reader-localization-catalog\t1\n");
  for (i = 0u; i < (size_t)RL_MESSAGE_COUNT; ++i) {
    const rl_message *message = &rl_messages[order[i]];
    rl_sha256_update_string(&hash, "M\t");
    rl_sha256_update_string(&hash, message->id);
    rl_sha256_update_string(&hash, "\t");
    rl_sha256_update_string(&hash, message->group);
    rl_sha256_update_string(&hash, "\t");
    rl_sha256_update_string(&hash, message->kinds);
    rl_sha256_update_string(&hash, "\n");
  }
  for (i = 0u; i < (size_t)RL_MESSAGE_COUNT; ++i) {
    const rl_message *message = &rl_messages[order[i]];
    size_t locale_index;
    for (locale_index = 0u; locale_index < (size_t)RL_LOCALE_COUNT; ++locale_index) {
      uint32_t locale = locale_index == 0u ? (uint32_t)READER_LOCALIZATION_LOCALE_ZH_CN
                                           : (uint32_t)READER_LOCALIZATION_LOCALE_EN_US;
      const char *text = rl_shipped_row(order[i], locale);
      if (text == NULL) continue;
      rl_sha256_update_string(&hash, "T\t");
      rl_sha256_update_string(&hash, message->id);
      rl_sha256_update_string(&hash, "\t");
      rl_sha256_update_string(&hash, reader_localization_locale_tag(locale));
      rl_sha256_update_string(&hash, "\t");
      rl_sha256_update_string(&hash, text);
      rl_sha256_update_string(&hash, "\n");
    }
  }
  rl_sha256_final(&hash, digest);
  for (i = 0u; i < 32u; ++i) {
    out_hex[i * 2u] = hex[digest[i] >> 4];
    out_hex[i * 2u + 1u] = hex[digest[i] & 0x0fu];
  }
  out_hex[64] = '\0';
}

#if defined(READER_LOCALIZATION_TEST_HOOKS)
static int rl_override_set(const char *message_id, uint32_t locale, const char *replacement) {
  size_t index = 0u;
  size_t i;
  if (reader_localization_locale_tag(locale) == NULL) return 0;
  if (rl_find_message(message_id, &index) != READER_LOCALIZATION_OK) return 0;
  for (i = 0u; i < rl_override_count; ++i) {
    if (rl_overrides[i].message == index && rl_overrides[i].locale == locale) {
      rl_overrides[i].replacement = replacement;
      return 1;
    }
  }
  if (rl_override_count >= (size_t)RL_TEST_OVERRIDES) return 0;
  rl_overrides[rl_override_count].message = index;
  rl_overrides[rl_override_count].locale = locale;
  rl_overrides[rl_override_count].replacement = replacement;
  ++rl_override_count;
  return 1;
}

int reader_localization_test_drop(const char *message_id, uint32_t locale) {
  return rl_override_set(message_id, locale, NULL);
}

int reader_localization_test_corrupt(const char *message_id, uint32_t locale, const char *text) {
  return rl_override_set(message_id, locale, text);
}

void reader_localization_test_reset(void) {
  rl_override_count = 0u;
}
#endif
