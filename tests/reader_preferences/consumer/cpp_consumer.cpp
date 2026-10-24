// SPDX-License-Identifier: MIT
#include "reader_preferences.h"

#include <cstdio>
#include <cstring>
#include <type_traits>

static_assert(std::is_standard_layout<reader_preferences>::value, "C ABI struct layout");

int main(int argc, char **argv) {
  const char *path = argc > 1 ? argv[1] : "preferences-cpp.json";
  reader_preferences preferences = reader_preferences_defaults();
  reader_preferences_error error;
  reader_preferences_error_clear(&error);
  if (reader_preferences_validate(&preferences, &error) != READER_PREFERENCES_OK) return 1;
  preferences.theme = static_cast<uint32_t>(READER_PREFERENCES_THEME_SYSTEM);
  if (reader_preferences_effective_theme(&preferences, READER_PREFERENCES_THEME_DARK) !=
      READER_PREFERENCES_THEME_DARK) return 2;
  preferences.theme = static_cast<uint32_t>(READER_PREFERENCES_THEME_LIGHT);
  if (reader_preferences_save(&preferences, path, nullptr, &error) != READER_PREFERENCES_OK) return 3;
  preferences.font_size = 60.0f;
  if (reader_preferences_load(path, &preferences, nullptr, &error) != READER_PREFERENCES_OK) return 4;
  if (preferences.font_size != 24.0f) return 5;
  std::printf("cpp-consumer-ok size=%zu\n", sizeof(reader_preferences));
  return 0;
}
