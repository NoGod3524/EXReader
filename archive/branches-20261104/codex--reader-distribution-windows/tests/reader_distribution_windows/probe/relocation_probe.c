/* SPDX-License-Identifier: MIT */
/* Native Windows relocation probe.
 *
 * Compiled only against an extracted distribution prefix: the prefix is given
 * as a run-time argument, the module actually loaded is reported with its full
 * path, every loaded module is classified, and a real publication is opened
 * through the installed public ABI. A module outside the prefix, the Windows
 * directory or an explicit allowance fails the probe, so a silently relocated
 * DLL or a leaked build-machine dependency cannot pass. */
#define _CRT_SECURE_NO_WARNINGS
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <exreader.h>

#define MAX_MODULES 256
#define MAX_EXTERNAL 32

typedef struct {
  char module_path[4096];
  char prefix[4096];
  char version[64];
  unsigned abi;
  size_t parts;
  unsigned loaded;
  unsigned external_count;
  char external[MAX_EXTERNAL][1024];
  int failures;
} probe_state;

static void narrow(const wchar_t *wide, char *output, size_t capacity) {
  if (!WideCharToMultiByte(CP_UTF8, 0, wide, -1, output, (int)capacity, NULL, NULL)) {
    output[0] = '\0';
  }
}

static void escape(const char *value, char *output, size_t capacity) {
  size_t used = 0;
  for (const char *cursor = value; *cursor && used + 3 < capacity; cursor++) {
    unsigned char byte = (unsigned char)*cursor;
    if (byte == '\\' || byte == '"') {
      output[used++] = '\\';
      output[used++] = (char)byte;
    } else if (byte < 0x20) {
      used += (size_t)snprintf(output + used, capacity - used, "\\u%04x", byte);
    } else {
      output[used++] = (char)byte;
    }
  }
  output[used] = '\0';
}

static void normalise(char *value) {
  for (char *cursor = value; *cursor; cursor++) {
    if (*cursor == '/') {
      *cursor = '\\';
    } else if (*cursor >= 'A' && *cursor <= 'Z') {
      *cursor = (char)(*cursor - 'A' + 'a');
    }
  }
}

static int starts_with(const char *value, const char *prefix) {
  size_t length = strlen(prefix);
  return length > 0 && strncmp(value, prefix, length) == 0;
}

static int self_path(char *output, size_t capacity) {
  wchar_t wide[4096];
  DWORD written = GetModuleFileNameW(NULL, wide, (DWORD)(sizeof(wide) / sizeof(wide[0])));
  if (written == 0 || written >= sizeof(wide) / sizeof(wide[0])) {
    return 0;
  }
  narrow(wide, output, capacity);
  return 1;
}

static void classify_modules(probe_state *state) {
  HMODULE modules[MAX_MODULES];
  DWORD needed = 0;
  wchar_t windows_dir[4096];
  char windows_root[4096];
  if (!GetWindowsDirectoryW(windows_dir, (DWORD)(sizeof(windows_dir) / sizeof(windows_dir[0])))) {
    state->failures++;
    return;
  }
  narrow(windows_dir, windows_root, sizeof(windows_root));
  normalise(windows_root);
  if (!EnumProcessModules(GetCurrentProcess(), modules, (DWORD)sizeof(modules), &needed)) {
    state->failures++;
    return;
  }
  DWORD count = needed / (DWORD)sizeof(HMODULE);
  if (count > MAX_MODULES) {
    count = MAX_MODULES;
  }
  for (DWORD index = 0; index < count; index++) {
    wchar_t wide[4096];
    char path[4096];
    DWORD written = GetModuleFileNameExW(GetCurrentProcess(), modules[index], wide,
                                         (DWORD)(sizeof(wide) / sizeof(wide[0])));
    if (written == 0) {
      continue;
    }
    narrow(wide, path, sizeof(path));
    normalise(path);
    state->loaded++;
    if (!strcmp(path, state->module_path)) {
      continue;  /* the probe itself is recorded separately, not as a dependency */
    }
    if (starts_with(path, state->prefix) || starts_with(path, windows_root)) {
      continue;
    }
    if (state->external_count < MAX_EXTERNAL) {
      snprintf(state->external[state->external_count], sizeof(state->external[0]), "%s", path);
      state->external_count++;
    }
    state->failures++;
  }
}

static int open_publication(probe_state *state, const char *font_path, const char *book_path) {
  exr_font *font = NULL;
  exr_publication *publication = NULL;
  exr_error error = {0};
  size_t parts = 0;
  const exr_part *declared = NULL;
  exr_status status = exr_font_open(font_path, &font, &error);
  if (status != EXR_OK) {
    fprintf(stderr, "font open failed: %d\n", (int)status);
    return 0;
  }
  status = exr_publication_open(book_path, &publication, &error);
  if (status != EXR_OK) {
    fprintf(stderr, "publication open failed: %d\n", (int)status);
    exr_font_free(font);
    return 0;
  }
  declared = exr_publication_parts(publication, &parts);
  if (!declared || parts == 0) {
    exr_publication_free(publication);
    exr_font_free(font);
    return 0;
  }
  state->parts = parts;
  exr_publication_free(publication);
  exr_font_free(font);
  return 1;
}

static void write_report(const probe_state *state, const char *path) {
  FILE *stream = fopen(path, "wb");
  char module[8192], prefix[8192], version[256];
  if (!stream) {
    return;
  }
  escape(state->module_path, module, sizeof(module));
  escape(state->prefix, prefix, sizeof(prefix));
  escape(state->version, version, sizeof(version));
  fprintf(stream,
          "{\"schema\":\"reader-distribution-windows-probe-v1\","
          "\"module_path\":\"%s\",\"prefix\":\"%s\",\"sdk_version\":\"%s\",\"abi\":%u,"
          "\"self_module\":true,"
          "\"document_parts\":%u,\"loaded_modules\":%u,\"external_modules\":[",
          module, prefix, version, state->abi, (unsigned)state->parts, state->loaded);
  for (unsigned index = 0; index < state->external_count; index++) {
    char escaped[4096];
    escape(state->external[index], escaped, sizeof(escaped));
    fprintf(stream, "%s\"%s\"", index ? "," : "", escaped);
  }
  fprintf(stream, "],\"passed\":%s}\n", state->failures == 0 ? "true" : "false");
  if (state->failures) {
    fprintf(stderr, "relocation probe failed: module=%s prefix=%s external=%u\n",
            state->module_path, state->prefix, state->external_count);
    for (unsigned index = 0; index < state->external_count; index++) {
      fprintf(stderr, "  external module: %s\n", state->external[index]);
    }
  }
  fclose(stream);
}

int main(int argc, char **argv) {
  probe_state state;
  const char *font_path = NULL;
  const char *book_path = NULL;
  const char *output = NULL;
  const char *prefix = NULL;
  memset(&state, 0, sizeof(state));
  for (int index = 1; index + 1 < argc; index += 2) {
    if (!strcmp(argv[index], "--prefix")) {
      prefix = argv[index + 1];
    } else if (!strcmp(argv[index], "--font")) {
      font_path = argv[index + 1];
    } else if (!strcmp(argv[index], "--book")) {
      book_path = argv[index + 1];
    } else if (!strcmp(argv[index], "--output")) {
      output = argv[index + 1];
    }
  }
  if (!prefix || !font_path || !book_path || !output) {
    fprintf(stderr, "usage: relocation-probe --prefix <dir> --font <ttf> --book <epub> --output <json>\n");
    return 2;
  }
  if (!self_path(state.module_path, sizeof(state.module_path))) {
    return 3;
  }
  snprintf(state.prefix, sizeof(state.prefix), "%s", prefix);
  normalise(state.module_path);
  normalise(state.prefix);
  snprintf(state.version, sizeof(state.version), "%s", exr_version());
  state.abi = (unsigned)exr_abi_version();
  if (!starts_with(state.module_path, state.prefix)) {
    state.failures++;
  }
  classify_modules(&state);
  if (!open_publication(&state, font_path, book_path)) {
    state.failures++;
  }
  write_report(&state, output);
  return state.failures == 0 ? 0 : 1;
}
