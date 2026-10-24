/* SPDX-License-Identifier: MIT */
#include "internal.h"

#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void rp_error_set(reader_preferences_error *error, reader_preferences_status status,
                  int system_error, size_t offset, const char *format, ...) {
  va_list args;
  if (!error) return;
  error->status = status;
  error->system_error = system_error;
  error->offset = offset;
  va_start(args, format);
  if (format) {
    (void)vsnprintf(error->message, sizeof(error->message), format, args);
  } else {
    error->message[0] = '\0';
  }
  va_end(args);
  error->message[sizeof(error->message) - 1u] = '\0';
}

int rp_cancel_requested(const reader_preferences_control *control) {
  return control && control->cancelled && control->cancelled(control->context);
}

reader_preferences_status rp_validate_fields(const reader_preferences *p,
                                             reader_preferences_error *error) {
  size_t i;
  if (!p) {
    rp_error_set(error, READER_PREFERENCES_ARGUMENT, 0, 0, "preferences is null");
    return READER_PREFERENCES_ARGUMENT;
  }
  if (p->struct_size != sizeof(reader_preferences)) {
    rp_error_set(error, READER_PREFERENCES_ARGUMENT, 0, 0,
                 "struct_size %u != %u", (unsigned)p->struct_size,
                 (unsigned)sizeof(reader_preferences));
    return READER_PREFERENCES_ARGUMENT;
  }
  if (p->abi_version != READER_PREFERENCES_ABI_VERSION) {
    rp_error_set(error, READER_PREFERENCES_ARGUMENT, 0, 0,
                 "abi_version %u != %u", (unsigned)p->abi_version,
                 READER_PREFERENCES_ABI_VERSION);
    return READER_PREFERENCES_ARGUMENT;
  }
  for (i = 0; i < sizeof(p->reserved) / sizeof(p->reserved[0]); ++i) {
    if (p->reserved[i] != 0u) {
      rp_error_set(error, READER_PREFERENCES_ARGUMENT, 0, 0,
                   "reserved[%u] must be zero", (unsigned)i);
      return READER_PREFERENCES_ARGUMENT;
    }
  }
  if (!isfinite(p->font_size)) {
    rp_error_set(error, READER_PREFERENCES_RANGE, 0, 0, "font_size must be finite");
    return READER_PREFERENCES_RANGE;
  }
  if (!isfinite(p->line_spacing)) {
    rp_error_set(error, READER_PREFERENCES_RANGE, 0, 0, "line_spacing must be finite");
    return READER_PREFERENCES_RANGE;
  }
  if (!isfinite(p->paragraph_spacing)) {
    rp_error_set(error, READER_PREFERENCES_RANGE, 0, 0, "paragraph_spacing must be finite");
    return READER_PREFERENCES_RANGE;
  }
  if (!isfinite(p->margin)) {
    rp_error_set(error, READER_PREFERENCES_RANGE, 0, 0, "margin must be finite");
    return READER_PREFERENCES_RANGE;
  }
  if (p->font_size < 4.0f || p->font_size > 256.0f) {
    rp_error_set(error, READER_PREFERENCES_RANGE, 0, 0,
                 "font_size %g outside 4..256 pt", (double)p->font_size);
    return READER_PREFERENCES_RANGE;
  }
  if (p->line_spacing < 1.0f || p->line_spacing > 5.0f) {
    rp_error_set(error, READER_PREFERENCES_RANGE, 0, 0,
                 "line_spacing %g outside 1..5", (double)p->line_spacing);
    return READER_PREFERENCES_RANGE;
  }
  if (p->paragraph_spacing < 0.0f || p->paragraph_spacing > 1024.0f) {
    rp_error_set(error, READER_PREFERENCES_RANGE, 0, 0,
                 "paragraph_spacing %g outside 0..1024 pt", (double)p->paragraph_spacing);
    return READER_PREFERENCES_RANGE;
  }
  if (p->margin < 0.0f || p->margin > 1024.0f) {
    rp_error_set(error, READER_PREFERENCES_RANGE, 0, 0,
                 "margin %g outside 0..1024 pt", (double)p->margin);
    return READER_PREFERENCES_RANGE;
  }
  if (p->theme < (uint32_t)READER_PREFERENCES_THEME_LIGHT ||
      p->theme > (uint32_t)READER_PREFERENCES_THEME_SYSTEM) {
    rp_error_set(error, READER_PREFERENCES_ARGUMENT, 0, 0,
                 "theme %u is not light, dark or system", (unsigned)p->theme);
    return READER_PREFERENCES_ARGUMENT;
  }
  if (p->page_turn_direction < (uint32_t)READER_PREFERENCES_TURN_LTR ||
      p->page_turn_direction > (uint32_t)READER_PREFERENCES_TURN_VERTICAL) {
    rp_error_set(error, READER_PREFERENCES_ARGUMENT, 0, 0,
                 "page_turn_direction %u is not ltr, rtl or vertical",
                 (unsigned)p->page_turn_direction);
    return READER_PREFERENCES_ARGUMENT;
  }
  if (p->page_turn_input < (uint32_t)READER_PREFERENCES_INPUT_TAP ||
      p->page_turn_input > (uint32_t)READER_PREFERENCES_INPUT_HARDWARE_KEYS) {
    rp_error_set(error, READER_PREFERENCES_ARGUMENT, 0, 0,
                 "page_turn_input %u is not a supported operation",
                 (unsigned)p->page_turn_input);
    return READER_PREFERENCES_ARGUMENT;
  }
  if (p->fixed_page_zoom < 25u || p->fixed_page_zoom > 400u) {
    rp_error_set(error, READER_PREFERENCES_RANGE, 0, 0,
                 "fixed_page_zoom %u outside 25..400 percent", (unsigned)p->fixed_page_zoom);
    return READER_PREFERENCES_RANGE;
  }
  return READER_PREFERENCES_OK;
}

uint32_t reader_preferences_abi_version(void) {
  return READER_PREFERENCES_ABI_VERSION;
}

reader_preferences reader_preferences_defaults(void) {
  reader_preferences p;
  memset(&p, 0, sizeof(p));
  p.struct_size = (uint32_t)sizeof(p);
  p.abi_version = READER_PREFERENCES_ABI_VERSION;
  p.font_size = 24.0f;
  p.line_spacing = 1.6f;
  p.paragraph_spacing = 12.0f;
  p.margin = 48.0f;
  p.theme = (uint32_t)READER_PREFERENCES_THEME_LIGHT;
  p.page_turn_direction = (uint32_t)READER_PREFERENCES_TURN_LTR;
  p.page_turn_input = (uint32_t)READER_PREFERENCES_INPUT_TAP;
  p.fixed_page_zoom = 100u;
  p.light_foreground[0] = 0x1au; p.light_foreground[1] = 0x1au;
  p.light_foreground[2] = 0x1au; p.light_foreground[3] = 0xffu;
  p.light_background[0] = 0xffu; p.light_background[1] = 0xffu;
  p.light_background[2] = 0xffu; p.light_background[3] = 0xffu;
  p.dark_foreground[0] = 0xe6u; p.dark_foreground[1] = 0xe6u;
  p.dark_foreground[2] = 0xe6u; p.dark_foreground[3] = 0xffu;
  p.dark_background[0] = 0x10u; p.dark_background[1] = 0x10u;
  p.dark_background[2] = 0x10u; p.dark_background[3] = 0xffu;
  return p;
}

const char *reader_preferences_status_name(reader_preferences_status status) {
  switch (status) {
    case READER_PREFERENCES_OK: return "OK";
    case READER_PREFERENCES_ARGUMENT: return "ARGUMENT";
    case READER_PREFERENCES_IO: return "IO";
    case READER_PREFERENCES_FORMAT: return "FORMAT";
    case READER_PREFERENCES_VERSION: return "VERSION";
    case READER_PREFERENCES_RANGE: return "RANGE";
    case READER_PREFERENCES_CANCELLED: return "CANCELLED";
    case READER_PREFERENCES_LIMIT: return "LIMIT";
    default: return "UNKNOWN";
  }
}

void reader_preferences_error_clear(reader_preferences_error *error) {
  if (!error) return;
  memset(error, 0, sizeof(*error));
  error->struct_size = (uint32_t)sizeof(*error);
}

reader_preferences_status reader_preferences_validate(const reader_preferences *preferences,
                                                      reader_preferences_error *error) {
  reader_preferences_error_clear(error);
  return rp_validate_fields(preferences, error);
}

reader_preferences_status reader_preferences_load(const char *utf8_path,
                                                  reader_preferences *inout,
                                                  const reader_preferences_load_options *options,
                                                  reader_preferences_error *error) {
  reader_preferences_status status;
  reader_preferences candidate;
  unsigned char *data = NULL;
  size_t size = 0;
  size_t limit = RP_DEFAULT_FILE_LIMIT;
  reader_preferences_control control;

  reader_preferences_error_clear(error);
  if (!inout || !utf8_path || utf8_path[0] == '\0') {
    rp_error_set(error, READER_PREFERENCES_ARGUMENT, 0, 0, "null or empty path/record");
    return READER_PREFERENCES_ARGUMENT;
  }
  if (options) {
    if (options->struct_size != sizeof(reader_preferences_load_options)) {
      rp_error_set(error, READER_PREFERENCES_ARGUMENT, 0, 0,
                   "load options struct_size differs");
      return READER_PREFERENCES_ARGUMENT;
    }
    if (options->max_file_bytes != 0u) limit = options->max_file_bytes;
    if (limit > RP_DEFAULT_FILE_LIMIT) {
      rp_error_set(error, READER_PREFERENCES_ARGUMENT, 0, 0,
                   "load limit may only lower the 65536-byte ceiling");
      return READER_PREFERENCES_ARGUMENT;
    }
    control = options->control;
  } else {
    control.cancelled = NULL;
    control.context = NULL;
  }
  if (rp_cancel_requested(&control)) {
    rp_error_set(error, READER_PREFERENCES_CANCELLED, 0, 0, "load cancelled before open");
    return READER_PREFERENCES_CANCELLED;
  }
  status = rp_read_file(utf8_path, limit, &control, &data, &size, error);
  if (status != READER_PREFERENCES_OK) return status;
  candidate = reader_preferences_defaults();
  status = rp_json_parse(data, size, &candidate, error);
  free(data);
  if (status != READER_PREFERENCES_OK) return status;
  if (rp_cancel_requested(&control)) {
    rp_error_set(error, READER_PREFERENCES_CANCELLED, 0, 0, "load cancelled before commit");
    return READER_PREFERENCES_CANCELLED;
  }
  *inout = candidate;
  return READER_PREFERENCES_OK;
}

reader_preferences_status reader_preferences_save(const reader_preferences *preferences,
                                                  const char *utf8_path,
                                                  const reader_preferences_save_options *options,
                                                  reader_preferences_error *error) {
  reader_preferences_status status;
  reader_preferences_control control;
  char document[RP_JSON_CAPACITY];
  size_t used = 0;

  reader_preferences_error_clear(error);
  status = rp_validate_fields(preferences, error);
  if (status != READER_PREFERENCES_OK) return status;
  if (!utf8_path || utf8_path[0] == '\0') {
    rp_error_set(error, READER_PREFERENCES_ARGUMENT, 0, 0, "null or empty path");
    return READER_PREFERENCES_ARGUMENT;
  }
  if (options) {
    if (options->struct_size != sizeof(reader_preferences_save_options)) {
      rp_error_set(error, READER_PREFERENCES_ARGUMENT, 0, 0,
                   "save options struct_size differs");
      return READER_PREFERENCES_ARGUMENT;
    }
    control = options->control;
  } else {
    control.cancelled = NULL;
    control.context = NULL;
  }
  if (rp_cancel_requested(&control)) {
    rp_error_set(error, READER_PREFERENCES_CANCELLED, 0, 0, "save cancelled before write");
    return READER_PREFERENCES_CANCELLED;
  }
  status = rp_json_write(preferences, document, sizeof(document), &used, error);
  if (status != READER_PREFERENCES_OK) return status;
  return rp_write_file_atomic(utf8_path, document, used, &control, error);
}

reader_preferences_status reader_preferences_import_legacy(
    reader_preferences *preferences, const reader_preferences_legacy *legacy,
    reader_preferences_import_report *report, reader_preferences_error *error) {
  reader_preferences merged;
  reader_preferences_status status;
  uint32_t applied;
  uint32_t ignored;

  reader_preferences_error_clear(error);
  if (!preferences || !legacy) {
    rp_error_set(error, READER_PREFERENCES_ARGUMENT, 0, 0, "null preferences or legacy record");
    return READER_PREFERENCES_ARGUMENT;
  }
  if (legacy->struct_size != sizeof(reader_preferences_legacy)) {
    rp_error_set(error, READER_PREFERENCES_ARGUMENT, 0, 0, "legacy struct_size differs");
    return READER_PREFERENCES_ARGUMENT;
  }
  if (report && report->struct_size != sizeof(reader_preferences_import_report)) {
    rp_error_set(error, READER_PREFERENCES_ARGUMENT, 0, 0, "report struct_size differs");
    return READER_PREFERENCES_ARGUMENT;
  }
  if ((legacy->present & ~(uint32_t)READER_PREFERENCES_LEGACY_ALL) != 0u) {
    rp_error_set(error, READER_PREFERENCES_ARGUMENT, 0, 0,
                 "legacy present bits %#x are unknown; nothing imported",
                 (unsigned)(legacy->present & ~(uint32_t)READER_PREFERENCES_LEGACY_ALL));
    return READER_PREFERENCES_ARGUMENT;
  }
  status = rp_validate_fields(preferences, error);
  if (status != READER_PREFERENCES_OK) return status;

  merged = *preferences;
  applied = legacy->present;
  if (applied & READER_PREFERENCES_LEGACY_FONT_SIZE) merged.font_size = legacy->font_size;
  if (applied & READER_PREFERENCES_LEGACY_LINE_SPACING) merged.line_spacing = legacy->line_spacing;
  if (applied & READER_PREFERENCES_LEGACY_PARAGRAPH_SPACING)
    merged.paragraph_spacing = legacy->paragraph_spacing;
  if (applied & READER_PREFERENCES_LEGACY_MARGIN) merged.margin = legacy->margin;
  if (applied & READER_PREFERENCES_LEGACY_THEME) merged.theme = legacy->theme;
  if (applied & READER_PREFERENCES_LEGACY_TURN_DIRECTION)
    merged.page_turn_direction = legacy->page_turn_direction;
  if (applied & READER_PREFERENCES_LEGACY_TURN_INPUT)
    merged.page_turn_input = legacy->page_turn_input;
  if (applied & READER_PREFERENCES_LEGACY_FIXED_ZOOM)
    merged.fixed_page_zoom = legacy->fixed_page_zoom;
  if (applied & READER_PREFERENCES_LEGACY_LIGHT_FOREGROUND)
    memcpy(merged.light_foreground, legacy->light_foreground, 4);
  if (applied & READER_PREFERENCES_LEGACY_LIGHT_BACKGROUND)
    memcpy(merged.light_background, legacy->light_background, 4);
  if (applied & READER_PREFERENCES_LEGACY_DARK_FOREGROUND)
    memcpy(merged.dark_foreground, legacy->dark_foreground, 4);
  if (applied & READER_PREFERENCES_LEGACY_DARK_BACKGROUND)
    memcpy(merged.dark_background, legacy->dark_background, 4);

  status = rp_validate_fields(&merged, error);
  if (status != READER_PREFERENCES_OK) return status;

  ignored = (uint32_t)READER_PREFERENCES_LEGACY_ALL & ~applied;
  *preferences = merged;
  if (report) {
    report->applied = applied;
    report->preserved = ignored;
  }
  return READER_PREFERENCES_OK;
}

reader_preferences_theme reader_preferences_effective_theme(
    const reader_preferences *preferences, reader_preferences_theme system_theme) {
  if (!preferences || preferences->struct_size != sizeof(reader_preferences) ||
      preferences->abi_version != READER_PREFERENCES_ABI_VERSION) {
    return READER_PREFERENCES_THEME_LIGHT;
  }
  if (preferences->theme == (uint32_t)READER_PREFERENCES_THEME_LIGHT)
    return READER_PREFERENCES_THEME_LIGHT;
  if (preferences->theme == (uint32_t)READER_PREFERENCES_THEME_DARK)
    return READER_PREFERENCES_THEME_DARK;
  if (preferences->theme != (uint32_t)READER_PREFERENCES_THEME_SYSTEM)
    return READER_PREFERENCES_THEME_LIGHT;
  if (system_theme == READER_PREFERENCES_THEME_LIGHT ||
      system_theme == READER_PREFERENCES_THEME_DARK)
    return system_theme;
  return READER_PREFERENCES_THEME_LIGHT;
}
