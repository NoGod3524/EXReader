/* SPDX-License-Identifier: MIT */
/* Test-hook worker: the only binary built from package sources with
 * READER_ACCOUNT_PROFILES_TEST_HOOKS. The installed library cannot be paused,
 * failed or cancelled through environment variables. */
#include "reader_account_profiles.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(_WIN32)
#include <windows.h>
#endif

static int set_environment(const char *name, const char *value) {
#if defined(_WIN32)
  return _putenv_s(name, value) == 0;
#else
  return setenv(name, value, 1) == 0;
#endif
}

static void make_profile(reader_account_profile *profile, const char *id, const char *account,
                         const char *url, const char *name) {
  memset(profile, 0, sizeof(*profile));
  profile->struct_size = (uint32_t)sizeof(*profile);
  (void)snprintf(profile->profile_id, sizeof(profile->profile_id), "%s", id);
  (void)snprintf(profile->account_id, sizeof(profile->account_id), "%s", account);
  (void)snprintf(profile->root_url, sizeof(profile->root_url), "%s", url);
  (void)snprintf(profile->display_name, sizeof(profile->display_name), "%s", name);
}

static int parse_flags(int argc, char **argv, int first) {
  int index = first;
  while (index < argc) {
    if (strcmp(argv[index], "--fail-before-rename") == 0) {
      if (!set_environment("EXR_ACCOUNT_PROFILES_TEST_FAIL_BEFORE_RENAME", "1")) return 0;
      index += 1;
    } else if (strcmp(argv[index], "--cancel-before-rename") == 0) {
      if (!set_environment("EXR_ACCOUNT_PROFILES_TEST_CANCEL_BEFORE_RENAME", "1")) return 0;
      index += 1;
    } else if (strcmp(argv[index], "--pause-after-lock") == 0 && index + 2 < argc) {
      if (!set_environment("EXR_ACCOUNT_PROFILES_TEST_PAUSE_AFTER_LOCK", argv[index + 2]))
        return 0;
      if (!set_environment("EXR_ACCOUNT_PROFILES_TEST_READY_FILE", argv[index + 1])) return 0;
      index += 3;
    } else if (strcmp(argv[index], "--pause-before-rename") == 0 && index + 2 < argc) {
      if (!set_environment("EXR_ACCOUNT_PROFILES_TEST_PAUSE_BEFORE_RENAME", argv[index + 2]))
        return 0;
      if (!set_environment("EXR_ACCOUNT_PROFILES_TEST_READY_FILE", argv[index + 1])) return 0;
      index += 3;
    } else if (strcmp(argv[index], "--pause-after-rename") == 0 && index + 2 < argc) {
      if (!set_environment("EXR_ACCOUNT_PROFILES_TEST_PAUSE_AFTER_RENAME", argv[index + 2]))
        return 0;
      if (!set_environment("EXR_ACCOUNT_PROFILES_TEST_READY_FILE", argv[index + 1])) return 0;
      index += 3;
    } else {
      return 0;
    }
  }
  return 1;
}

static int run(int argc, char **argv) {
  reader_account_profiles_error error;
  reader_account_profiles_status status;
  uint64_t generation = 0;
  reader_account_profile profile;

  reader_account_profiles_error_clear(&error);
  if (argc < 2) {
    (void)printf("usage: worker <add|race|hold> ...\n");
    return 2;
  }

  if (strcmp(argv[1], "add") == 0 && argc >= 7) {
    make_profile(&profile, argv[3], argv[4], argv[5], argv[6]);
    if (!parse_flags(argc, argv, 7)) return 2;
    status = reader_account_profiles_add(argv[2], &profile, NULL, &generation, &error);
    (void)printf("status=%s\ngeneration=%llu\nmessage=%s\n",
                 reader_account_profiles_status_name(status),
                 (unsigned long long)generation, error.message);
    return 0;
  }

  if (strcmp(argv[1], "hold") == 0 && argc == 6) {
    char id[40];
    char account[40];
    unsigned index = (unsigned)strtoul(argv[5], NULL, 10);
    (void)snprintf(id, sizeof(id), "30000000-0000-4000-8000-%012u", index);
    (void)snprintf(account, sizeof(account), "40000000-0000-4000-8000-%012u", index);
    make_profile(&profile, id, account, "https://hold.example/reader/", "holder");
    if (!set_environment("EXR_ACCOUNT_PROFILES_TEST_PAUSE_AFTER_LOCK", argv[4])) return 2;
    if (!set_environment("EXR_ACCOUNT_PROFILES_TEST_READY_FILE", argv[3])) return 2;
    status = reader_account_profiles_add(argv[2], &profile, NULL, &generation, &error);
    (void)printf("status=%s\ngeneration=%llu\n", reader_account_profiles_status_name(status),
                 (unsigned long long)generation);
    return 0;
  }

  if (strcmp(argv[1], "race") == 0 && argc == 5) {
    unsigned base = (unsigned)strtoul(argv[3], NULL, 10);
    unsigned count = (unsigned)strtoul(argv[4], NULL, 10);
    unsigned index;
    if (count == 0u || count > 32u) return 2;
    for (index = 0; index < count; ++index) {
      char id[40];
      char account[40];
      (void)snprintf(id, sizeof(id), "50000000-0000-4000-8000-%012u", base + index);
      (void)snprintf(account, sizeof(account), "60000000-0000-4000-8000-%012u", base + index);
      make_profile(&profile, id, account, "https://race.example/reader/", "racer");
      status = reader_account_profiles_add(argv[2], &profile, NULL, &generation, &error);
      (void)printf("add%u=%s\n", index, reader_account_profiles_status_name(status));
      if (status != READER_ACCOUNT_PROFILES_OK) return 1;
    }
    (void)printf("generation=%llu\n", (unsigned long long)generation);
    return 0;
  }

  (void)printf("status=ARGUMENT\nmessage=unsupported verb or arity\n");
  return 2;
}

#if defined(_WIN32)
static char *wide_to_utf8(const wchar_t *text) {
  int needed = WideCharToMultiByte(CP_UTF8, 0, text, -1, NULL, 0, NULL, NULL);
  char *utf8;
  if (needed <= 0) return NULL;
  utf8 = (char *)malloc((size_t)needed);
  if (!utf8) return NULL;
  if (WideCharToMultiByte(CP_UTF8, 0, text, -1, utf8, needed, NULL, NULL) != needed) {
    free(utf8);
    return NULL;
  }
  return utf8;
}

int wmain(int argc, wchar_t **argv) {
  char **utf8 = (char **)calloc((size_t)argc + 1u, sizeof(char *));
  int index;
  int result;
  if (!utf8) return 2;
  for (index = 0; index < argc; ++index) {
    utf8[index] = wide_to_utf8(argv[index]);
    if (!utf8[index]) return 2;
  }
  result = run(argc, utf8);
  for (index = 0; index < argc; ++index) free(utf8[index]);
  free(utf8);
  return result;
}
#else
int main(int argc, char **argv) { return run(argc, argv); }
#endif
