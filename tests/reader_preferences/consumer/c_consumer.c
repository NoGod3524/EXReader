/* SPDX-License-Identifier: MIT */
#if defined(_WIN32)
#define _CRT_SECURE_NO_WARNINGS 1
#endif
#include "reader_preferences.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

static int failures;

#define CHECK(condition, name) \
  do { if (!(condition)) { (void)printf("FAIL %s\n", name); ++failures; } } while (0)

static int write_text(const char *path, const char *text) {
  FILE *file = fopen(path, "wb");
  size_t length = strlen(text);
  if (!file) return 0;
  if (fwrite(text, 1, length, file) != length) { (void)fclose(file); return 0; }
  return fclose(file) == 0;
}

static size_t read_file(const char *path, unsigned char *buffer, size_t capacity) {
  FILE *file = fopen(path, "rb");
  size_t length;
  if (!file) return 0;
  length = fread(buffer, 1, capacity, file);
  (void)fclose(file);
  return length;
}

static int cancel_immediately(void *context) {
  (void)context;
  return 1;
}

int main(int argc, char **argv) {
  const char *directory = argc > 1 ? argv[1] : ".";
  char path[1024];
  char bad_path[1024];
  reader_preferences p;
  reader_preferences before;
  reader_preferences_error error;
  reader_preferences_legacy legacy;
  reader_preferences_import_report report;
  reader_preferences_control control;
  reader_preferences_load_options load_options;
  reader_preferences_save_options save_options;
  unsigned char bytes_before[4096];
  unsigned char bytes_after[4096];
  size_t size_before;
  size_t size_after;

  (void)snprintf(path, sizeof(path), "%s/preferences-c.json", directory);
  (void)snprintf(bad_path, sizeof(bad_path), "%s/preferences-c-bad.json", directory);

  p = reader_preferences_defaults();
  CHECK(p.struct_size == sizeof(reader_preferences), "defaults struct_size");
  CHECK(p.abi_version == READER_PREFERENCES_ABI_VERSION, "defaults abi");
  CHECK(reader_preferences_abi_version() == READER_PREFERENCES_ABI_VERSION, "abi function");
  CHECK(p.font_size == 24.0f, "default font_size");
  CHECK(p.line_spacing == 1.6f, "default line_spacing");
  CHECK(p.paragraph_spacing == 12.0f, "default paragraph_spacing");
  CHECK(p.margin == 48.0f, "default margin");
  CHECK(p.theme == (uint32_t)READER_PREFERENCES_THEME_LIGHT, "default theme");
  CHECK(p.page_turn_direction == (uint32_t)READER_PREFERENCES_TURN_LTR, "default direction");
  CHECK(p.page_turn_input == (uint32_t)READER_PREFERENCES_INPUT_TAP, "default input");
  CHECK(p.fixed_page_zoom == 100u, "default zoom");
  CHECK(p.light_foreground[0] == 0x1au && p.dark_background[0] == 0x10u, "default colors");

  reader_preferences_error_clear(&error);
  CHECK(reader_preferences_validate(&p, &error) == READER_PREFERENCES_OK, "validate defaults");
  CHECK(error.message[0] == '\0', "success clears message");

  p.font_size = NAN;
  CHECK(reader_preferences_validate(&p, &error) == READER_PREFERENCES_RANGE, "reject NaN");
  CHECK(error.message[0] != '\0', "range message present");
  p = reader_preferences_defaults();
  p.line_spacing = INFINITY;
  CHECK(reader_preferences_validate(&p, &error) == READER_PREFERENCES_RANGE, "reject infinity");
  p = reader_preferences_defaults();
  p.margin = -0.5f;
  CHECK(reader_preferences_validate(&p, &error) == READER_PREFERENCES_RANGE, "reject negative margin");
  p = reader_preferences_defaults();
  p.theme = 0u;
  CHECK(reader_preferences_validate(&p, &error) == READER_PREFERENCES_ARGUMENT, "reject enum zero");
  p = reader_preferences_defaults();
  p.fixed_page_zoom = 24u;
  CHECK(reader_preferences_validate(&p, &error) == READER_PREFERENCES_RANGE, "reject zoom below");
  p = reader_preferences_defaults();
  p.reserved[3] = 1u;
  CHECK(reader_preferences_validate(&p, &error) == READER_PREFERENCES_ARGUMENT, "reject reserved");
  p = reader_preferences_defaults();
  p.struct_size = 1u;
  CHECK(reader_preferences_validate(&p, &error) == READER_PREFERENCES_ARGUMENT, "reject struct size");
  p = reader_preferences_defaults();
  p.abi_version = 9u;
  CHECK(reader_preferences_validate(&p, &error) == READER_PREFERENCES_ARGUMENT, "reject abi");

  p = reader_preferences_defaults();
  p.theme = (uint32_t)READER_PREFERENCES_THEME_SYSTEM;
  CHECK(reader_preferences_effective_theme(&p, READER_PREFERENCES_THEME_DARK) ==
        READER_PREFERENCES_THEME_DARK, "system resolves dark");
  CHECK(reader_preferences_effective_theme(&p, READER_PREFERENCES_THEME_LIGHT) ==
        READER_PREFERENCES_THEME_LIGHT, "system resolves light");
  CHECK(reader_preferences_effective_theme(&p, READER_PREFERENCES_THEME_SYSTEM) ==
        READER_PREFERENCES_THEME_LIGHT, "unknown system falls back light");
  p.theme = (uint32_t)READER_PREFERENCES_THEME_DARK;
  CHECK(reader_preferences_effective_theme(&p, READER_PREFERENCES_THEME_LIGHT) ==
        READER_PREFERENCES_THEME_DARK, "stored dark ignores system");

  p = reader_preferences_defaults();
  p.font_size = 20.0f;
  memset(&legacy, 0, sizeof(legacy));
  legacy.struct_size = sizeof(legacy);
  legacy.present = READER_PREFERENCES_LEGACY_FONT_SIZE | READER_PREFERENCES_LEGACY_THEME;
  legacy.font_size = 30.0f;
  legacy.theme = (uint32_t)READER_PREFERENCES_THEME_DARK;
  memset(&report, 0, sizeof(report));
  report.struct_size = sizeof(report);
  CHECK(reader_preferences_import_legacy(&p, &legacy, &report, &error) == READER_PREFERENCES_OK,
        "legacy import ok");
  CHECK(p.font_size == 30.0f, "legacy font applied");
  CHECK(p.theme == (uint32_t)READER_PREFERENCES_THEME_DARK, "legacy theme applied");
  CHECK(p.line_spacing == 1.6f, "legacy absent field preserved");
  CHECK(report.applied == legacy.present, "legacy applied bits");
  CHECK(report.preserved == (READER_PREFERENCES_LEGACY_ALL & ~legacy.present), "legacy preserved bits");

  before = p;
  legacy.present |= 1u << 20;
  CHECK(reader_preferences_import_legacy(&p, &legacy, &report, &error) == READER_PREFERENCES_ARGUMENT,
        "legacy unknown bits rejected");
  CHECK(memcmp(&p, &before, sizeof(p)) == 0, "legacy unknown leaves record");

  legacy.present = READER_PREFERENCES_LEGACY_FONT_SIZE;
  legacy.font_size = 300.0f;
  CHECK(reader_preferences_import_legacy(&p, &legacy, &report, &error) == READER_PREFERENCES_RANGE,
        "legacy range rejected");
  CHECK(memcmp(&p, &before, sizeof(p)) == 0, "legacy range leaves record");

  p = reader_preferences_defaults();
  CHECK(write_text(bad_path, "not json at all"), "write corrupt fixture");
  p.font_size = 44.0f;
  before = p;
  CHECK(reader_preferences_load(bad_path, &p, NULL, &error) == READER_PREFERENCES_FORMAT,
        "corrupt load rejected");
  CHECK(memcmp(&p, &before, sizeof(p)) == 0, "failed load preserves caller");

  reader_preferences_error_clear(&error);
  CHECK(error.status == READER_PREFERENCES_OK && error.message[0] == '\0', "error clear");

  p = reader_preferences_defaults();
  CHECK(reader_preferences_save(&p, path, NULL, &error) == READER_PREFERENCES_OK, "save defaults");
  p = reader_preferences_defaults();
  p.font_size = 44.0f;
  CHECK(reader_preferences_load(path, &p, NULL, &error) == READER_PREFERENCES_OK, "load saved");
  CHECK(p.font_size == 24.0f, "caller record replaced on success");

  memset(&load_options, 0, sizeof(load_options));
  load_options.struct_size = 1u;
  CHECK(reader_preferences_load(path, &p, &load_options, &error) == READER_PREFERENCES_ARGUMENT,
        "load options size rejected");
  memset(&save_options, 0, sizeof(save_options));
  save_options.struct_size = 1u;
  CHECK(reader_preferences_save(&p, path, &save_options, &error) == READER_PREFERENCES_ARGUMENT,
        "save options size rejected");

  p = reader_preferences_defaults();
  p.font_size = 44.0f;
  before = p;
  control.cancelled = cancel_immediately;
  control.context = NULL;
  CHECK(reader_preferences_load(path, &p, NULL, &error) == READER_PREFERENCES_OK, "reload baseline");
  p = before;
  memset(&load_options, 0, sizeof(load_options));
  load_options.struct_size = sizeof(load_options);
  load_options.control = control;
  CHECK(reader_preferences_load(path, &p, &load_options, &error) == READER_PREFERENCES_CANCELLED,
        "cancelled load");
  CHECK(memcmp(&p, &before, sizeof(p)) == 0, "cancelled load preserves caller");

  size_before = read_file(path, bytes_before, sizeof(bytes_before));
  p = reader_preferences_defaults();
  p.font_size = 33.0f;
  memset(&save_options, 0, sizeof(save_options));
  save_options.struct_size = sizeof(save_options);
  save_options.control = control;
  CHECK(reader_preferences_save(&p, path, &save_options, &error) == READER_PREFERENCES_CANCELLED,
        "cancelled save");
  size_after = read_file(path, bytes_after, sizeof(bytes_after));
  CHECK(size_before == size_after && memcmp(bytes_before, bytes_after, size_before) == 0,
        "cancelled save keeps bytes");

  p = reader_preferences_defaults();
  p.font_size = 3.0f;
  size_before = read_file(path, bytes_before, sizeof(bytes_before));
  CHECK(reader_preferences_save(&p, path, NULL, &error) == READER_PREFERENCES_RANGE, "reject bad save");
  size_after = read_file(path, bytes_after, sizeof(bytes_after));
  CHECK(size_before == size_after && memcmp(bytes_before, bytes_after, size_before) == 0,
        "invalid save keeps bytes");

  CHECK(strcmp(reader_preferences_status_name(READER_PREFERENCES_OK), "OK") == 0, "status OK name");
  CHECK(strcmp(reader_preferences_status_name(READER_PREFERENCES_VERSION), "VERSION") == 0,
        "status VERSION name");
  CHECK(strcmp(reader_preferences_status_name((reader_preferences_status)99), "UNKNOWN") == 0,
        "status unknown name");

  if (failures == 0) {
    (void)printf("c-consumer-ok\n");
    return 0;
  }
  (void)printf("c-consumer-failed %d\n", failures);
  return 1;
}
