/* SPDX-License-Identifier: MIT */
#include "reader_preferences.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int set_environment(const char *name, const char *value) {
#if defined(_WIN32)
  return _putenv_s(name, value) == 0;
#else
  return setenv(name, value, 1) == 0;
#endif
}

static reader_preferences make_preset(const char *name) {
  reader_preferences p = reader_preferences_defaults();
  if (strcmp(name, "a") == 0) {
    p.font_size = 12.0f;
    p.line_spacing = 1.2f;
    p.paragraph_spacing = 4.0f;
    p.margin = 16.0f;
    p.theme = (uint32_t)READER_PREFERENCES_THEME_LIGHT;
    p.page_turn_direction = (uint32_t)READER_PREFERENCES_TURN_LTR;
    p.page_turn_input = (uint32_t)READER_PREFERENCES_INPUT_TAP;
    p.fixed_page_zoom = 100u;
    p.light_foreground[0] = 0x11u; p.light_foreground[1] = 0x22u;
    p.light_foreground[2] = 0x33u; p.light_foreground[3] = 0xffu;
    p.light_background[0] = 0xeeu; p.light_background[1] = 0xddu;
    p.light_background[2] = 0xccu; p.light_background[3] = 0xffu;
  } else if (strcmp(name, "b") == 0) {
    p.font_size = 48.0f;
    p.line_spacing = 2.5f;
    p.paragraph_spacing = 64.0f;
    p.margin = 96.0f;
    p.theme = (uint32_t)READER_PREFERENCES_THEME_DARK;
    p.page_turn_direction = (uint32_t)READER_PREFERENCES_TURN_RTL;
    p.page_turn_input = (uint32_t)READER_PREFERENCES_INPUT_SWIPE;
    p.fixed_page_zoom = 250u;
    p.light_foreground[0] = 0x44u; p.light_foreground[1] = 0x55u;
    p.light_foreground[2] = 0x66u; p.light_foreground[3] = 0x77u;
    p.light_background[0] = 0x88u; p.light_background[1] = 0x99u;
    p.light_background[2] = 0xaau; p.light_background[3] = 0xbbu;
  } else if (strcmp(name, "custom") == 0) {
    p.font_size = 36.0f;
    p.line_spacing = 2.0f;
    p.paragraph_spacing = 24.0f;
    p.margin = 64.0f;
    p.theme = (uint32_t)READER_PREFERENCES_THEME_SYSTEM;
    p.page_turn_direction = (uint32_t)READER_PREFERENCES_TURN_VERTICAL;
    p.page_turn_input = (uint32_t)READER_PREFERENCES_INPUT_HARDWARE_KEYS;
    p.fixed_page_zoom = 175u;
  }
  return p;
}

static void print_preferences(const reader_preferences *p) {
  (void)printf("font_size=%.7g\n", (double)p->font_size);
  (void)printf("line_spacing=%.7g\n", (double)p->line_spacing);
  (void)printf("paragraph_spacing=%.7g\n", (double)p->paragraph_spacing);
  (void)printf("margin=%.7g\n", (double)p->margin);
  (void)printf("theme=%u\n", (unsigned)p->theme);
  (void)printf("page_turn_direction=%u\n", (unsigned)p->page_turn_direction);
  (void)printf("page_turn_input=%u\n", (unsigned)p->page_turn_input);
  (void)printf("fixed_page_zoom=%u\n", (unsigned)p->fixed_page_zoom);
  (void)printf("light_foreground=#%02X%02X%02X%02X\n", (unsigned)p->light_foreground[0],
               (unsigned)p->light_foreground[1], (unsigned)p->light_foreground[2],
               (unsigned)p->light_foreground[3]);
  (void)printf("light_background=#%02X%02X%02X%02X\n", (unsigned)p->light_background[0],
               (unsigned)p->light_background[1], (unsigned)p->light_background[2],
               (unsigned)p->light_background[3]);
  (void)printf("dark_foreground=#%02X%02X%02X%02X\n", (unsigned)p->dark_foreground[0],
               (unsigned)p->dark_foreground[1], (unsigned)p->dark_foreground[2],
               (unsigned)p->dark_foreground[3]);
  (void)printf("dark_background=#%02X%02X%02X%02X\n", (unsigned)p->dark_background[0],
               (unsigned)p->dark_background[1], (unsigned)p->dark_background[2],
               (unsigned)p->dark_background[3]);
}

static int report_failure(reader_preferences_status status, const reader_preferences_error *error) {
  (void)printf("status=%s\n", reader_preferences_status_name(status));
  if (error) (void)printf("message=%s\n", error->message);
  return status == READER_PREFERENCES_IO ? 20 : 1;
}

static int cancel_now(void *context) {
  (void)context;
  return 1;
}

static int parse_save_flags(int argc, char **argv, int first) {
  int i = first;
  while (i < argc) {
    if (strcmp(argv[i], "--fail-before-rename") == 0) {
      if (!set_environment("EXR_PREFERENCES_TEST_FAIL_BEFORE_RENAME", "1")) return 0;
      i += 1;
    } else if (strcmp(argv[i], "--pause-before-rename") == 0 && i + 1 < argc) {
      if (!set_environment("EXR_PREFERENCES_TEST_PAUSE_BEFORE_RENAME", "30000")) return 0;
      if (!set_environment("EXR_PREFERENCES_TEST_READY_FILE", argv[i + 1])) return 0;
      i += 2;
    } else if (strcmp(argv[i], "--pause-after-rename") == 0 && i + 1 < argc) {
      if (!set_environment("EXR_PREFERENCES_TEST_PAUSE_AFTER_RENAME", "30000")) return 0;
      if (!set_environment("EXR_PREFERENCES_TEST_READY_FILE", argv[i + 1])) return 0;
      i += 2;
    } else {
      return 0;
    }
  }
  return 1;
}

int main(int argc, char **argv) {
  reader_preferences p;
  reader_preferences before;
  reader_preferences_error error;
  reader_preferences_status status;
  reader_preferences_control control;
  int i;

  reader_preferences_error_clear(&error);
  if (argc < 2) {
    (void)printf("usage: worker <save|load|preserve|cancel-save|cancel-load|race|import-legacy|defaults> ...\n");
    return 2;
  }

  if (strcmp(argv[1], "defaults") == 0) {
    p = reader_preferences_defaults();
    print_preferences(&p);
    return 0;
  }

  if (strcmp(argv[1], "load") == 0 && argc >= 3) {
    p = reader_preferences_defaults();
    status = reader_preferences_load(argv[2], &p, NULL, &error);
    if (status != READER_PREFERENCES_OK) return report_failure(status, &error);
    print_preferences(&p);
    return 0;
  }

  if (strcmp(argv[1], "save") == 0 && argc >= 4) {
    p = make_preset(argv[3]);
    if (!parse_save_flags(argc, argv, 4)) return 2;
    status = reader_preferences_save(&p, argv[2], NULL, &error);
    if (status != READER_PREFERENCES_OK) return report_failure(status, &error);
    return 0;
  }

  if (strcmp(argv[1], "preserve") == 0 && argc >= 5) {
    p = make_preset(argv[3]);
    before = p;
    status = reader_preferences_load(argv[4], &p, NULL, &error);
    if (status == READER_PREFERENCES_OK) {
      (void)printf("unexpected success\n");
      return 1;
    }
    if (memcmp(&p, &before, sizeof(p)) != 0) {
      (void)printf("record changed on failed load\n");
      return 1;
    }
    (void)printf("preserved=1 status=%s\n", reader_preferences_status_name(status));
    return 0;
  }

  if (strcmp(argv[1], "cancel-load") == 0 && argc >= 3) {
    p = make_preset("a");
    before = p;
    control.cancelled = cancel_now;
    control.context = NULL;
    {
      reader_preferences_load_options options;
      memset(&options, 0, sizeof(options));
      options.struct_size = sizeof(options);
      options.control = control;
      status = reader_preferences_load(argv[2], &p, &options, &error);
    }
    if (status != READER_PREFERENCES_CANCELLED) return report_failure(status, &error);
    if (memcmp(&p, &before, sizeof(p)) != 0) return 1;
    (void)printf("cancelled=1\n");
    return 10;
  }

  if (strcmp(argv[1], "cancel-save") == 0 && argc >= 3) {
    p = make_preset("b");
    control.cancelled = cancel_now;
    control.context = NULL;
    {
      reader_preferences_save_options options;
      memset(&options, 0, sizeof(options));
      options.struct_size = sizeof(options);
      options.control = control;
      status = reader_preferences_save(&p, argv[2], &options, &error);
    }
    if (status != READER_PREFERENCES_CANCELLED) return report_failure(status, &error);
    (void)printf("cancelled=1\n");
    return 10;
  }

  if (strcmp(argv[1], "race") == 0 && argc >= 5) {
    int iterations = atoi(argv[4]);
    p = make_preset(argv[3]);
    for (i = 0; i < iterations; ++i) {
      status = reader_preferences_save(&p, argv[2], NULL, &error);
      if (status != READER_PREFERENCES_OK) return report_failure(status, &error);
    }
    return 0;
  }

  if (strcmp(argv[1], "import-legacy") == 0 && argc >= 3) {
    reader_preferences_legacy legacy;
    reader_preferences_import_report report;
    p = make_preset("a");
    memset(&legacy, 0, sizeof(legacy));
    legacy.struct_size = sizeof(legacy);
    legacy.present = READER_PREFERENCES_LEGACY_FONT_SIZE | READER_PREFERENCES_LEGACY_THEME;
    legacy.font_size = 30.0f;
    legacy.theme = (uint32_t)READER_PREFERENCES_THEME_DARK;
    memset(&report, 0, sizeof(report));
    report.struct_size = sizeof(report);
    status = reader_preferences_import_legacy(&p, &legacy, &report, &error);
    if (status != READER_PREFERENCES_OK) return report_failure(status, &error);
    (void)printf("applied=%u preserved=%u\n", (unsigned)report.applied,
                 (unsigned)report.preserved);
    print_preferences(&p);
    status = reader_preferences_save(&p, argv[2], NULL, &error);
    if (status != READER_PREFERENCES_OK) return report_failure(status, &error);
    return 0;
  }

  return 2;
}
