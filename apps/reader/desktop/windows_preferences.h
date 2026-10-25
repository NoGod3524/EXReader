/* SPDX-License-Identifier: MIT */
/* Installed F3 reading preferences for the real Windows host.
 *
 * This header owns only the control identifiers, the accepted preference
 * record and the small amount of UI-owner state. The SDK is never called from
 * here: layout and rendering stay on the existing single worker, and the
 * stored file is written with the installed EXReaderPreferences atomic API. */
#ifndef READER_WINDOWS_PREFERENCES_H
#define READER_WINDOWS_PREFERENCES_H

#ifdef EXR_READER_WINDOWS_PREFERENCES

#ifndef HOST_PATH
#define HOST_PATH 4096
#endif

#include <reader_preferences.h>

/* Ids 260..289 are unused by the original host and by every other optional
   Windows module (150..255), so no existing control id moves. */
enum {
  IDC_PREFERENCES = 260, IDC_PREF_FONT, IDC_PREF_LINE, IDC_PREF_PARAGRAPH, IDC_PREF_MARGIN,
  IDC_PREF_THEME, IDC_PREF_DIRECTION, IDC_PREF_INPUT, IDC_PREF_ZOOM,
  IDC_PREF_LIGHT_FG, IDC_PREF_LIGHT_BG, IDC_PREF_DARK_FG, IDC_PREF_DARK_BG,
  IDC_PREF_APPLY, IDC_PREF_DEFAULTS, IDC_PREF_IMPORT, IDC_PREF_REBUILD, IDC_PREF_CLOSE,
  IDC_PREF_MESSAGE, IDC_PREF_TOGGLE, IDC_PREF_NOTE,
  IDC_PREF_FONT_LABEL, IDC_PREF_LINE_LABEL, IDC_PREF_PARAGRAPH_LABEL, IDC_PREF_MARGIN_LABEL,
  IDC_PREF_THEME_LABEL, IDC_PREF_DIRECTION_LABEL, IDC_PREF_INPUT_LABEL, IDC_PREF_ZOOM_LABEL,
  IDC_PREF_LIGHT_FG_LABEL, IDC_PREF_LIGHT_BG_LABEL, IDC_PREF_DARK_FG_LABEL, IDC_PREF_DARK_BG_LABEL
};

/* The single accepted record plus the plain-owner facts that must never be
   read from the worker. active is 0 until the reader explicitly chooses a
   value, which is what keeps the original out-of-box rendering byte-identical. */
typedef struct {
  reader_preferences value;
  wchar_t path[HOST_PATH];
  int active;
  int file_present;
  int corrupt;
  int load_status;
  int system_theme;      /* sampled on the UI owner only */
  int system_events;
  int theme_pending;
  int last_ok;
  unsigned long applied;
} host_preferences;

#endif
#endif
