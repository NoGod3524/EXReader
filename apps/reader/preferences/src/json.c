/* SPDX-License-Identifier: MIT */
#include "internal.h"

#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

typedef struct {
  const unsigned char *begin;
  const unsigned char *p;
  const unsigned char *end;
  reader_preferences_error *error;
  reader_preferences_status status;
} rp_parser;

typedef struct {
  char *buffer;
  size_t capacity;
  size_t length;
  int ok;
} rp_writer;

static int rp_parser_fail(rp_parser *s, reader_preferences_status status, const char *message) {
  s->status = status;
  rp_error_set(s->error, status, 0, (size_t)(s->p - s->begin), "%s", message);
  return 0;
}

static reader_preferences_status rp_parser_status(const rp_parser *parser) {
  return parser->status != READER_PREFERENCES_OK ? parser->status : READER_PREFERENCES_FORMAT;
}

static void rp_skip_ws(rp_parser *s) {
  while (s->p < s->end) {
    unsigned char c = *s->p;
    if (c == ' ' || c == '\t' || c == '\r' || c == '\n') {
      ++s->p;
    } else {
      break;
    }
  }
}

static int rp_take(rp_parser *s, unsigned char want) {
  if (s->p < s->end && *s->p == want) {
    ++s->p;
    return 1;
  }
  return 0;
}

static int rp_digit(unsigned char c) { return c >= '0' && c <= '9'; }

static int rp_parse_string(rp_parser *s, const unsigned char **start, size_t *length) {
  const unsigned char *from;
  if (!rp_take(s, '"')) return rp_parser_fail(s, READER_PREFERENCES_FORMAT, "expected string");
  from = s->p;
  while (s->p < s->end) {
    unsigned char c = *s->p;
    if (c == '"') {
      *start = from;
      *length = (size_t)(s->p - from);
      ++s->p;
      return 1;
    }
    if (c == '\\') return rp_parser_fail(s, READER_PREFERENCES_FORMAT, "escapes are not accepted");
    if (c < 0x20u || c >= 0x80u)
      return rp_parser_fail(s, READER_PREFERENCES_FORMAT, "non-ASCII or control byte in string");
    ++s->p;
  }
  return rp_parser_fail(s, READER_PREFERENCES_FORMAT, "unterminated string");
}

static int rp_key_is(const unsigned char *key, size_t length, const char *literal) {
  size_t n = strlen(literal);
  return n == length && memcmp(key, literal, n) == 0;
}

static int rp_parse_number(rp_parser *s, double *out) {
  const unsigned char *p = s->p;
  int negative = 0;
  int significant = 0;
  long exponent = 0;
  double mantissa = 0.0;

  if (p < s->end && *p == '-') { negative = 1; ++p; }
  if (p >= s->end || !rp_digit(*p))
    return rp_parser_fail(s, READER_PREFERENCES_FORMAT, "expected number");
  if (*p == '0' && p + 1 < s->end && rp_digit(p[1]))
    return rp_parser_fail(s, READER_PREFERENCES_FORMAT, "leading zero in number");
  while (p < s->end && rp_digit(*p)) {
    if (significant || *p != '0') {
      if (significant < 17) { mantissa = mantissa * 10.0 + (double)(*p - '0'); ++significant; }
      else { ++exponent; }
    }
    ++p;
  }
  if (p < s->end && *p == '.') {
    ++p;
    if (p >= s->end || !rp_digit(*p))
      return rp_parser_fail(s, READER_PREFERENCES_FORMAT, "fraction requires a digit");
    while (p < s->end && rp_digit(*p)) {
      if (significant < 17) {
        mantissa = mantissa * 10.0 + (double)(*p - '0');
        if (significant || *p != '0') ++significant;
        --exponent;
      }
      ++p;
    }
  }
  if (p < s->end && (*p == 'e' || *p == 'E')) {
    int sign = 1;
    long value = 0;
    int digits = 0;
    ++p;
    if (p < s->end && (*p == '+' || *p == '-')) {
      if (*p == '-') sign = -1;
      ++p;
    }
    while (p < s->end && rp_digit(*p)) {
      if (value < 100000) value = value * 10 + (*p - '0');
      ++digits;
      ++p;
    }
    if (!digits) return rp_parser_fail(s, READER_PREFERENCES_FORMAT, "exponent requires a digit");
    exponent += sign * value;
  }
  if (!isfinite(mantissa))
    return rp_parser_fail(s, READER_PREFERENCES_RANGE, "number is not finite");
  if (mantissa != 0.0) {
    double scaled;
    if (exponent > 400 || exponent < -400)
      return rp_parser_fail(s, READER_PREFERENCES_RANGE, "number exponent outside range");
    scaled = mantissa * pow(10.0, (double)exponent);
    if (!isfinite(scaled))
      return rp_parser_fail(s, READER_PREFERENCES_RANGE, "number is not finite");
    mantissa = scaled;
  }
  if (negative) mantissa = -mantissa;
  s->p = p;
  *out = mantissa;
  return 1;
}

static int rp_parse_uint(rp_parser *s, uint32_t *out) {
  const unsigned char *p = s->p;
  uint64_t value = 0;
  int digits = 0;
  if (p >= s->end || !rp_digit(*p))
    return rp_parser_fail(s, READER_PREFERENCES_FORMAT, "expected unsigned integer");
  if (*p == '0' && p + 1 < s->end && rp_digit(p[1]))
    return rp_parser_fail(s, READER_PREFERENCES_FORMAT, "leading zero in integer");
  while (p < s->end && rp_digit(*p)) {
    value = value * 10u + (uint64_t)(*p - '0');
    if (value > 0xffffffffull)
      return rp_parser_fail(s, READER_PREFERENCES_RANGE, "integer outside 32-bit range");
    ++digits;
    ++p;
  }
  if (p < s->end && (*p == '.' || *p == 'e' || *p == 'E'))
    return rp_parser_fail(s, READER_PREFERENCES_FORMAT, "integer field cannot be fractional");
  (void)digits;
  s->p = p;
  *out = (uint32_t)value;
  return 1;
}

static int rp_hex(unsigned char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

static int rp_parse_color(rp_parser *s, uint8_t out[4]) {
  const unsigned char *text;
  size_t length;
  size_t i;
  if (!rp_parse_string(s, &text, &length)) return 0;
  if (length != 7 && length != 9)
    return rp_parser_fail(s, READER_PREFERENCES_FORMAT, "color must be #RRGGBB or #RRGGBBAA");
  if (text[0] != '#')
    return rp_parser_fail(s, READER_PREFERENCES_FORMAT, "color must start with #");
  for (i = 1; i < length; ++i) {
    if (rp_hex(text[i]) < 0)
      return rp_parser_fail(s, READER_PREFERENCES_FORMAT, "color contains a non-hex digit");
  }
  out[0] = (uint8_t)((rp_hex(text[1]) << 4) | rp_hex(text[2]));
  out[1] = (uint8_t)((rp_hex(text[3]) << 4) | rp_hex(text[4]));
  out[2] = (uint8_t)((rp_hex(text[5]) << 4) | rp_hex(text[6]));
  out[3] = length == 9 ? (uint8_t)((rp_hex(text[7]) << 4) | rp_hex(text[8])) : 255u;
  return 1;
}

static int rp_enum_value(const unsigned char *text, size_t length, const char *const *names,
                         size_t count, uint32_t *out) {
  size_t i;
  for (i = 0; i < count; ++i) {
    if (rp_key_is(text, length, names[i])) { *out = (uint32_t)(i + 1u); return 1; }
  }
  return 0;
}

reader_preferences_status rp_json_parse(const unsigned char *data, size_t size,
                                        reader_preferences *out,
                                        reader_preferences_error *error) {
  static const char *const themes[] = { "light", "dark", "system" };
  static const char *const directions[] = { "ltr", "rtl", "vertical" };
  static const char *const inputs[] = { "tap", "swipe", "tap_and_swipe", "hardware_keys" };
  rp_parser s;
  reader_preferences parsed;
  uint32_t seen = 0;
  uint32_t version = 0;
  size_t version_offset = 0;
  int format_ok = 0;
  double number = 0.0;

  if (error) error->status = READER_PREFERENCES_OK;
  if (!data || size == 0u) {
    rp_error_set(error, READER_PREFERENCES_FORMAT, 0, 0, "empty document");
    return READER_PREFERENCES_FORMAT;
  }
  s.begin = data; s.p = data; s.end = data + size; s.error = error;s.status = READER_PREFERENCES_OK;
  parsed = *out;
  if (size >= 3u && data[0] == 0xefu && data[1] == 0xbbu && data[2] == 0xbfu) s.p += 3;
  rp_skip_ws(&s);
  if (!rp_take(&s, '{')) {
    (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "document must be an object");
    return READER_PREFERENCES_FORMAT;
  }
  rp_skip_ws(&s);
  if (rp_take(&s, '}')) {
    rp_error_set(error, READER_PREFERENCES_FORMAT, 0, (size_t)(s.p - s.begin), "document is empty");
    return READER_PREFERENCES_FORMAT;
  }
  for (;;) {
    const unsigned char *key;
    size_t key_length;
    const uint32_t bit_format = 1u << 0;
    const uint32_t bit_version = 1u << 1;
    const uint32_t bit_font = 1u << 2;
    const uint32_t bit_line = 1u << 3;
    const uint32_t bit_paragraph = 1u << 4;
    const uint32_t bit_margin = 1u << 5;
    const uint32_t bit_theme = 1u << 6;
    const uint32_t bit_direction = 1u << 7;
    const uint32_t bit_input = 1u << 8;
    const uint32_t bit_zoom = 1u << 9;
    const uint32_t bit_lfg = 1u << 10;
    const uint32_t bit_lbg = 1u << 11;
    const uint32_t bit_dfg = 1u << 12;
    const uint32_t bit_dbg = 1u << 13;

    rp_skip_ws(&s);
    if (!rp_parse_string(&s, &key, &key_length)) return READER_PREFERENCES_FORMAT;
    rp_skip_ws(&s);
    if (!rp_take(&s, ':')) {
      (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "expected ':' after key");
      return READER_PREFERENCES_FORMAT;
    }
    rp_skip_ws(&s);

    if (rp_key_is(key, key_length, "format")) {
      const unsigned char *value;
      size_t value_length;
      if (seen & bit_format) { (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "duplicate key"); return READER_PREFERENCES_FORMAT; }
      if (!rp_parse_string(&s, &value, &value_length)) return READER_PREFERENCES_FORMAT;
      format_ok = rp_key_is(value, value_length, "exreader-preferences");
      seen |= bit_format;
    } else if (rp_key_is(key, key_length, "format_version")) {
      if (seen & bit_version) { (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "duplicate key"); return READER_PREFERENCES_FORMAT; }
      version_offset = (size_t)(s.p - s.begin);
      if (!rp_parse_uint(&s, &version)) return rp_parser_status(&s);
      seen |= bit_version;
    } else if (rp_key_is(key, key_length, "font_size")) {
      if (seen & bit_font) { (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "duplicate key"); return READER_PREFERENCES_FORMAT; }
      if (!rp_parse_number(&s, &number)) return rp_parser_status(&s);
      parsed.font_size = (float)number;
      seen |= bit_font;
    } else if (rp_key_is(key, key_length, "line_spacing")) {
      if (seen & bit_line) { (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "duplicate key"); return READER_PREFERENCES_FORMAT; }
      if (!rp_parse_number(&s, &number)) return rp_parser_status(&s);
      parsed.line_spacing = (float)number;
      seen |= bit_line;
    } else if (rp_key_is(key, key_length, "paragraph_spacing")) {
      if (seen & bit_paragraph) { (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "duplicate key"); return READER_PREFERENCES_FORMAT; }
      if (!rp_parse_number(&s, &number)) return rp_parser_status(&s);
      parsed.paragraph_spacing = (float)number;
      seen |= bit_paragraph;
    } else if (rp_key_is(key, key_length, "margin")) {
      if (seen & bit_margin) { (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "duplicate key"); return READER_PREFERENCES_FORMAT; }
      if (!rp_parse_number(&s, &number)) return rp_parser_status(&s);
      parsed.margin = (float)number;
      seen |= bit_margin;
    } else if (rp_key_is(key, key_length, "theme")) {
      const unsigned char *value;
      size_t value_length;
      uint32_t value_number = 0;
      if (seen & bit_theme) { (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "duplicate key"); return READER_PREFERENCES_FORMAT; }
      if (!rp_parse_string(&s, &value, &value_length)) return READER_PREFERENCES_FORMAT;
      if (!rp_enum_value(value, value_length, themes, 3, &value_number)) {
        (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "theme must be light, dark or system");
        return READER_PREFERENCES_FORMAT;
      }
      parsed.theme = value_number;
      seen |= bit_theme;
    } else if (rp_key_is(key, key_length, "page_turn_direction")) {
      const unsigned char *value;
      size_t value_length;
      uint32_t value_number = 0;
      if (seen & bit_direction) { (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "duplicate key"); return READER_PREFERENCES_FORMAT; }
      if (!rp_parse_string(&s, &value, &value_length)) return READER_PREFERENCES_FORMAT;
      if (!rp_enum_value(value, value_length, directions, 3, &value_number)) {
        (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "page_turn_direction must be ltr, rtl or vertical");
        return READER_PREFERENCES_FORMAT;
      }
      parsed.page_turn_direction = value_number;
      seen |= bit_direction;
    } else if (rp_key_is(key, key_length, "page_turn_input")) {
      const unsigned char *value;
      size_t value_length;
      uint32_t value_number = 0;
      if (seen & bit_input) { (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "duplicate key"); return READER_PREFERENCES_FORMAT; }
      if (!rp_parse_string(&s, &value, &value_length)) return READER_PREFERENCES_FORMAT;
      if (!rp_enum_value(value, value_length, inputs, 4, &value_number)) {
        (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "page_turn_input must be tap, swipe, tap_and_swipe or hardware_keys");
        return READER_PREFERENCES_FORMAT;
      }
      parsed.page_turn_input = value_number;
      seen |= bit_input;
    } else if (rp_key_is(key, key_length, "fixed_page_zoom")) {
      if (seen & bit_zoom) { (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "duplicate key"); return READER_PREFERENCES_FORMAT; }
      if (!rp_parse_uint(&s, &parsed.fixed_page_zoom)) return rp_parser_status(&s);
      seen |= bit_zoom;
    } else if (rp_key_is(key, key_length, "light_foreground")) {
      if (seen & bit_lfg) { (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "duplicate key"); return READER_PREFERENCES_FORMAT; }
      if (!rp_parse_color(&s, parsed.light_foreground)) return READER_PREFERENCES_FORMAT;
      seen |= bit_lfg;
    } else if (rp_key_is(key, key_length, "light_background")) {
      if (seen & bit_lbg) { (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "duplicate key"); return READER_PREFERENCES_FORMAT; }
      if (!rp_parse_color(&s, parsed.light_background)) return READER_PREFERENCES_FORMAT;
      seen |= bit_lbg;
    } else if (rp_key_is(key, key_length, "dark_foreground")) {
      if (seen & bit_dfg) { (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "duplicate key"); return READER_PREFERENCES_FORMAT; }
      if (!rp_parse_color(&s, parsed.dark_foreground)) return READER_PREFERENCES_FORMAT;
      seen |= bit_dfg;
    } else if (rp_key_is(key, key_length, "dark_background")) {
      if (seen & bit_dbg) { (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "duplicate key"); return READER_PREFERENCES_FORMAT; }
      if (!rp_parse_color(&s, parsed.dark_background)) return READER_PREFERENCES_FORMAT;
      seen |= bit_dbg;
    } else {
      (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "unknown key");
      return READER_PREFERENCES_FORMAT;
    }

    rp_skip_ws(&s);
    if (rp_take(&s, ',')) continue;
    if (rp_take(&s, '}')) break;
    (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "expected ',' or '}'");
    return READER_PREFERENCES_FORMAT;
  }
  rp_skip_ws(&s);
  if (s.p != s.end) {
    (void)rp_parser_fail(&s, READER_PREFERENCES_FORMAT, "trailing bytes after object");
    return READER_PREFERENCES_FORMAT;
  }
  if (seen != 0x3fffu) {
    rp_error_set(error, READER_PREFERENCES_FORMAT, 0, (size_t)(s.p - s.begin),
                 "document is missing required fields (mask %#x)", (unsigned)seen);
    return READER_PREFERENCES_FORMAT;
  }
  if (!format_ok) {
    rp_error_set(error, READER_PREFERENCES_FORMAT, 0, 0, "format is not exreader-preferences");
    return READER_PREFERENCES_FORMAT;
  }
  if (version != 1u) {
    rp_error_set(error, READER_PREFERENCES_VERSION, 0, version_offset,
                 "unsupported format_version %u", (unsigned)version);
    return READER_PREFERENCES_VERSION;
  }
  {
    reader_preferences_status status = rp_validate_fields(&parsed, error);
    if (status != READER_PREFERENCES_OK) return status;
  }
  *out = parsed;
  return READER_PREFERENCES_OK;
}

static void rp_writer_put(rp_writer *w, const char *text) {
  size_t n;
  if (!w->ok) return;
  n = strlen(text);
  if (w->length + n + 1u > w->capacity) { w->ok = 0; return; }
  memcpy(w->buffer + w->length, text, n);
  w->length += n;
  w->buffer[w->length] = '\0';
}

static void rp_writer_printf(rp_writer *w, const char *format, ...) {
  char temporary[64];
  int written;
  va_list args;
  if (!w->ok) return;
  va_start(args, format);
  written = vsnprintf(temporary, sizeof(temporary), format, args);
  va_end(args);
  if (written < 0 || (size_t)written >= sizeof(temporary)) { w->ok = 0; return; }
  rp_writer_put(w, temporary);
}

static void rp_writer_number(rp_writer *w, double value) {
  char temporary[64];
  int length = 0;
  int negative;
  double magnitude;
  uint64_t scaled;
  uint64_t integer_part;
  uint64_t fraction;
  if (!w->ok) return;
  if (!isfinite(value)) { w->ok = 0; return; }
  negative = value < 0.0;
  magnitude = negative ? -value : value;
  scaled = (uint64_t)(magnitude * 1000000.0 + 0.5);
  integer_part = scaled / 1000000ull;
  fraction = scaled % 1000000ull;
  length = snprintf(temporary, sizeof(temporary), "%s%llu", negative ? "-" : "",
                    (unsigned long long)integer_part);
  if (length < 0 || (size_t)length >= sizeof(temporary)) { w->ok = 0; return; }
  if (fraction != 0u) {
    char digits[10];
    int used = 6;
    (void)snprintf(digits, sizeof(digits), "%06llu", (unsigned long long)fraction);
    while (used > 0 && digits[used - 1] == '0') --used;
    temporary[length++] = '.';
    memcpy(temporary + length, digits, (size_t)used);
    length += used;
    temporary[length] = '\0';
  }
  rp_writer_put(w, temporary);
}

reader_preferences_status rp_json_write(const reader_preferences *p, char *buffer,
                                        size_t capacity, size_t *used,
                                        reader_preferences_error *error) {
  rp_writer w;
  if (used) *used = 0;
  if (!p || !buffer || capacity == 0u) {
    rp_error_set(error, READER_PREFERENCES_ARGUMENT, 0, 0, "null document buffer");
    return READER_PREFERENCES_ARGUMENT;
  }
  w.buffer = buffer; w.capacity = capacity; w.length = 0; w.ok = 1;
  buffer[0] = '\0';
  rp_writer_put(&w, "{\n  \"format\": \"exreader-preferences\",\n  \"format_version\": 1,\n");
  rp_writer_put(&w, "  \"font_size\": ");
  rp_writer_number(&w, (double)p->font_size);
  rp_writer_put(&w, ",\n  \"line_spacing\": ");
  rp_writer_number(&w, (double)p->line_spacing);
  rp_writer_put(&w, ",\n  \"paragraph_spacing\": ");
  rp_writer_number(&w, (double)p->paragraph_spacing);
  rp_writer_put(&w, ",\n  \"margin\": ");
  rp_writer_number(&w, (double)p->margin);
  rp_writer_put(&w, ",\n  \"theme\": ");
  rp_writer_put(&w, p->theme == (uint32_t)READER_PREFERENCES_THEME_DARK ? "\"dark\"" :
                    p->theme == (uint32_t)READER_PREFERENCES_THEME_SYSTEM ? "\"system\"" : "\"light\"");
  rp_writer_put(&w, ",\n  \"page_turn_direction\": ");
  rp_writer_put(&w, p->page_turn_direction == (uint32_t)READER_PREFERENCES_TURN_RTL ? "\"rtl\"" :
                    p->page_turn_direction == (uint32_t)READER_PREFERENCES_TURN_VERTICAL ? "\"vertical\"" : "\"ltr\"");
  rp_writer_put(&w, ",\n  \"page_turn_input\": ");
  rp_writer_put(&w, p->page_turn_input == (uint32_t)READER_PREFERENCES_INPUT_SWIPE ? "\"swipe\"" :
                    p->page_turn_input == (uint32_t)READER_PREFERENCES_INPUT_TAP_AND_SWIPE ? "\"tap_and_swipe\"" :
                    p->page_turn_input == (uint32_t)READER_PREFERENCES_INPUT_HARDWARE_KEYS ? "\"hardware_keys\"" : "\"tap\"");
  rp_writer_put(&w, ",\n  \"fixed_page_zoom\": ");
  rp_writer_printf(&w, "%u", (unsigned)p->fixed_page_zoom);
  rp_writer_put(&w, ",\n  \"light_foreground\": ");
  rp_writer_printf(&w, "\"#%02X%02X%02X%02X\"", (unsigned)p->light_foreground[0],
                   (unsigned)p->light_foreground[1], (unsigned)p->light_foreground[2],
                   (unsigned)p->light_foreground[3]);
  rp_writer_put(&w, ",\n  \"light_background\": ");
  rp_writer_printf(&w, "\"#%02X%02X%02X%02X\"", (unsigned)p->light_background[0],
                   (unsigned)p->light_background[1], (unsigned)p->light_background[2],
                   (unsigned)p->light_background[3]);
  rp_writer_put(&w, ",\n  \"dark_foreground\": ");
  rp_writer_printf(&w, "\"#%02X%02X%02X%02X\"", (unsigned)p->dark_foreground[0],
                   (unsigned)p->dark_foreground[1], (unsigned)p->dark_foreground[2],
                   (unsigned)p->dark_foreground[3]);
  rp_writer_put(&w, ",\n  \"dark_background\": ");
  rp_writer_printf(&w, "\"#%02X%02X%02X%02X\"", (unsigned)p->dark_background[0],
                   (unsigned)p->dark_background[1], (unsigned)p->dark_background[2],
                   (unsigned)p->dark_background[3]);
  rp_writer_put(&w, "\n}\n");
  if (!w.ok) {
    rp_error_set(error, READER_PREFERENCES_RANGE, 0, 0, "document capacity exceeded");
    return READER_PREFERENCES_RANGE;
  }
  if (used) *used = w.length;
  return READER_PREFERENCES_OK;
}
