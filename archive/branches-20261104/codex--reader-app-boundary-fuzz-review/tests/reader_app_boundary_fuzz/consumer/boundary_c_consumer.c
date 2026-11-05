/* SPDX-License-Identifier: MIT */
/* Pure C consumer: it proves the installed headers and archives are usable from
   a translation unit that has no C++ runtime, no try/catch and no exceptions.
   It deliberately mirrors only a subset of the C++ consumer so the driver can
   compare statuses across the two language ABI surfaces. */

#include <reader_preferences.h>
#include <reader_revisions.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void print_quoted(const char *value) {
  const unsigned char *p = (const unsigned char *)(value ? value : "");
  putchar('"');
  for (; *p; ++p) {
    if (*p == '"' || *p == '\\') {
      putchar('\\');
      putchar((int)*p);
    } else if (*p < 0x20) {
      printf("\\u%04x", (unsigned)*p);
    } else {
      putchar((int)*p);
    }
  }
  putchar('"');
}

static const char *revision_name(reader_revision_status status) {
  switch (status) {
    case READER_REV_OK: return "OK";
    case READER_REV_ARGUMENT: return "ARGUMENT";
    case READER_REV_MEMORY: return "MEMORY";
    case READER_REV_DATABASE: return "DATABASE";
    case READER_REV_FORMAT: return "FORMAT";
    case READER_REV_LIMIT: return "LIMIT";
    case READER_REV_HASH: return "HASH";
    case READER_REV_COLLISION: return "COLLISION";
    case READER_REV_MISSING_PARENT: return "MISSING_PARENT";
    case READER_REV_CYCLE: return "CYCLE";
    case READER_REV_UNSAFE: return "UNSAFE";
    case READER_REV_OWNER: return "OWNER";
    case READER_REV_NOT_FOUND: return "NOT_FOUND";
    default: return "UNKNOWN";
  }
}

static reader_preferences sentinel(void) {
  reader_preferences value = reader_preferences_defaults();
  value.font_size = 7.25f;
  value.theme = (uint32_t)READER_PREFERENCES_THEME_DARK;
  value.fixed_page_zoom = 250u;
  return value;
}

static unsigned char *read_whole(const char *path, size_t *size) {
  FILE *file = fopen(path, "rb");
  unsigned char *data;
  long length;
  size_t got;
  if (!file) return NULL;
  if (fseek(file, 0, SEEK_END) != 0) { fclose(file); return NULL; }
  length = ftell(file);
  if (length <= 0) { fclose(file); return NULL; }
  if (fseek(file, 0, SEEK_SET) != 0) { fclose(file); return NULL; }
  data = (unsigned char *)malloc((size_t)length);
  if (!data) { fclose(file); return NULL; }
  got = fread(data, 1, (size_t)length, file);
  fclose(file);
  if (got != (size_t)length) { free(data); return NULL; }
  *size = (size_t)length;
  return data;
}

static int command_defaults(void) {
  const reader_preferences value = reader_preferences_defaults();
  printf("{\"abi_version\":%u,\"struct_size\":%u,\"font_size\":%.6g,\"line_spacing\":%.6g,"
         "\"paragraph_spacing\":%.6g,\"margin\":%.6g,\"theme\":%u,\"fixed_page_zoom\":%u}\n",
         (unsigned)reader_preferences_abi_version(), (unsigned)value.struct_size,
         (double)value.font_size, (double)value.line_spacing, (double)value.paragraph_spacing,
         (double)value.margin, (unsigned)value.theme, (unsigned)value.fixed_page_zoom);
  return 0;
}

static int command_status_name(int raw) {
  const char *name = reader_preferences_status_name((reader_preferences_status)raw);
  printf("{\"value\":%d,\"name\":", raw);
  print_quoted(name);
  printf("}\n");
  return 0;
}

static int command_load(const char *path) {
  reader_preferences value = sentinel();
  const reader_preferences before = value;
  reader_preferences_error error;
  reader_preferences_status status;
  int changed;
  reader_preferences_error_clear(&error);
  status = reader_preferences_load(path, &value, NULL, &error);
  changed = memcmp(&before, &value, sizeof value) != 0;
  if (status != READER_PREFERENCES_OK && changed) {
    printf("{\"violation\":\"a failed C load modified the caller record\"}\n");
    return 3;
  }
  printf("{\"status\":%d,\"name\":", (int)status);
  print_quoted(reader_preferences_status_name(status));
  printf(",\"message\":");
  print_quoted(error.message);
  printf(",\"memory_changed\":%d,\"font_size\":%.6g,\"theme\":%u}\n", changed,
         (double)value.font_size, (unsigned)value.theme);
  return 0;
}

static int command_validate_wire(const char *database, const char *wire_path) {
  reader_revisions *store = NULL;
  reader_revision_error error;
  reader_revision_info info;
  unsigned char *wire;
  size_t size = 0;
  reader_revision_status status;
  memset(&error, 0, sizeof error);
  memset(&info, 0, sizeof info);
  wire = read_whole(wire_path, &size);
  if (!wire) {
    printf("{\"error\":\"the wire case is unreadable\"}\n");
    return 2;
  }
  status = reader_revisions_open(database, &store, &error);
  if (status != READER_REV_OK || store == NULL) {
    printf("{\"status\":%d,\"name\":", (int)status);
    print_quoted(revision_name(status));
    printf(",\"message\":");
    print_quoted(error.message);
    printf("}\n");
    free(wire);
    return 0;
  }
  status = reader_revision_validate(store, wire, size, NULL, &info, &error);
  printf("{\"status\":%d,\"name\":", (int)status);
  print_quoted(revision_name(status));
  printf(",\"message\":");
  print_quoted(error.message);
  printf(",\"bytes\":%llu,\"sha256\":", (unsigned long long)info.bytes);
  print_quoted(info.sha256);
  printf("}\n");
  {
    reader_revision_error close_error;
    memset(&close_error, 0, sizeof close_error);
    if (reader_revisions_close(&store, &close_error) != READER_REV_OK) {
      printf("{\"violation\":\"the C consumer could not close the product catalog\"}\n");
      free(wire);
      return 3;
    }
  }
  free(wire);
  return 0;
}

int main(int argc, char **argv) {
  if (argc < 2) {
    printf("{\"usage\":\"boundary-c-consumer <command> ...\"}\n");
    return 2;
  }
  if (strcmp(argv[1], "defaults") == 0) return command_defaults();
  if (strcmp(argv[1], "status-name") == 0 && argc >= 3) return command_status_name(atoi(argv[2]));
  if (strcmp(argv[1], "load") == 0 && argc >= 3) return command_load(argv[2]);
  if (strcmp(argv[1], "validate-wire") == 0 && argc >= 4) {
    return command_validate_wire(argv[2], argv[3]);
  }
  printf("{\"usage\":\"unknown command\"}\n");
  return 2;
}
