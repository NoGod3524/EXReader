/* SPDX-License-Identifier: MIT */
/* Installed-package C consumer: one verb per process, machine-readable output. */
#include "reader_account_profiles.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(_WIN32)
#include <windows.h>
#else
#include <pthread.h>
#endif

static void print_status(reader_account_profiles_status status,
                         const reader_account_profiles_error *error) {
  (void)printf("status=%s\n", reader_account_profiles_status_name(status));
  (void)printf("offset=%llu\n", error ? (unsigned long long)error->offset : 0ull);
  (void)printf("system_error=%d\n", error ? error->system_error : 0);
  (void)printf("message=%s\n", error ? error->message : "");
}

static void copy_field(char *out, size_t capacity, const char *value) {
  size_t length = value ? strlen(value) : 0u;
  if (length >= capacity) length = capacity - 1u;
  if (length) memcpy(out, value, length);
  out[length] = '\0';
}

static void make_profile(reader_account_profile *profile, const char *id, const char *account,
                         const char *url, const char *name) {
  memset(profile, 0, sizeof(*profile));
  profile->struct_size = (uint32_t)sizeof(*profile);
  copy_field(profile->profile_id, sizeof(profile->profile_id), id);
  copy_field(profile->account_id, sizeof(profile->account_id), account);
  copy_field(profile->root_url, sizeof(profile->root_url), url);
  copy_field(profile->display_name, sizeof(profile->display_name), name);
}

static reader_account_profiles_status load_store(const char *store,
                                                 reader_account_profiles_list *list,
                                                 reader_account_profiles_options *options,
                                                 reader_account_profiles_error *error) {
  memset(list, 0, sizeof(*list));
  list->struct_size = (uint32_t)sizeof(*list);
  reader_account_profiles_error_clear(error);
  return reader_account_profiles_load(store, list, options, error);
}

static void print_list(const reader_account_profiles_list *list) {
  uint32_t index;
  (void)printf("generation=%llu\n", (unsigned long long)list->generation);
  (void)printf("count=%u\n", (unsigned)list->count);
  for (index = 0; index < list->count; ++index) {
    (void)printf("p%u.id=%s\n", (unsigned)index, list->profiles[index].profile_id);
    (void)printf("p%u.account=%s\n", (unsigned)index, list->profiles[index].account_id);
    (void)printf("p%u.url=%s\n", (unsigned)index, list->profiles[index].root_url);
    (void)printf("p%u.name=%s\n", (unsigned)index, list->profiles[index].display_name);
  }
}

static void print_plan(const reader_account_profiles_activation *plan) {
  (void)printf("plan.generation=%llu\n", (unsigned long long)plan->store_generation);
  (void)printf("plan.id=%s\n", plan->profile.profile_id);
  (void)printf("plan.account=%s\n", plan->profile.account_id);
  (void)printf("plan.url=%s\n", plan->profile.root_url);
  (void)printf("plan.name=%s\n", plan->profile.display_name);
  (void)printf("plan.product=%s\n", plan->product_path);
  (void)printf("plan.private=%s\n", plan->private_directory);
  (void)printf("plan.originals=%s\n", plan->original_directory);
}

static int cancel_now(void *context) {
  (void)context;
  return 1;
}

typedef struct {
  const char *store;
  unsigned index;
  int status;
} thread_args;

#if defined(_WIN32)
static DWORD WINAPI thread_main(LPVOID opaque) {
  thread_args *args = (thread_args *)opaque;
#else
static void *thread_main(void *opaque) {
  thread_args *args = (thread_args *)opaque;
#endif
  char id[40];
  char account[40];
  reader_account_profile profile;
  reader_account_profiles_error error;
  reader_account_profiles_error_clear(&error);
  (void)snprintf(id, sizeof(id), "10000000-0000-4000-8000-%012u", args->index);
  (void)snprintf(account, sizeof(account), "20000000-0000-4000-8000-%012u", args->index);
  make_profile(&profile, id, account, "https://thread.example/reader/", "thread");
  args->status = (int)reader_account_profiles_add(args->store, &profile, NULL, NULL, &error);
#if defined(_WIN32)
  return 0;
#else
  return NULL;
#endif
}

static int run(int argc, char **argv) {
  reader_account_profiles_error error;

  if (argc < 2) {
    (void)printf("usage: probe <verb> ...\n");
    return 2;
  }
  reader_account_profiles_error_clear(&error);

  if (strcmp(argv[1], "info") == 0) {
    (void)printf("abi=%u\n", (unsigned)reader_account_profiles_abi_version());
    (void)printf("version=%s\n", READER_ACCOUNT_PROFILES_VERSION_STRING);
    (void)printf("max_profiles=%u\n", (unsigned)READER_ACCOUNT_PROFILES_MAX_PROFILES);
    (void)printf("max_file_bytes=%u\n", (unsigned)READER_ACCOUNT_PROFILES_MAX_FILE_BYTES);
    (void)printf("status.OK=%s\n", reader_account_profiles_status_name(READER_ACCOUNT_PROFILES_OK));
    (void)printf("status.SECRET=%s\n",
                 reader_account_profiles_status_name(READER_ACCOUNT_PROFILES_SECRET));
    (void)printf("status.UNSAFE_PATH=%s\n",
                 reader_account_profiles_status_name(READER_ACCOUNT_PROFILES_UNSAFE_PATH));
    (void)printf("status.BINDING=%s\n",
                 reader_account_profiles_status_name(READER_ACCOUNT_PROFILES_BINDING));
    (void)printf("status.UNKNOWN=%s\n",
                 reader_account_profiles_status_name((reader_account_profiles_status)999));
    return 0;
  }

  if (strcmp(argv[1], "validate") == 0 && argc == 6) {
    reader_account_profile profile;
    make_profile(&profile, argv[2], argv[3], argv[4], argv[5]);
    print_status(reader_account_profiles_validate(&profile, &error), &error);
    return 0;
  }

  if (strcmp(argv[1], "struct-size") == 0 && argc == 2) {
    reader_account_profiles_list list;
    reader_account_profile profile;
    reader_account_profiles_options options;
    memset(&list, 0, sizeof(list));
    print_status(reader_account_profiles_load("/tmp/never-used", &list, NULL, &error), &error);
    memset(&profile, 0, sizeof(profile));
    profile.struct_size = 0;
    print_status(reader_account_profiles_validate(&profile, &error), &error);
    memset(&options, 0, sizeof(options));
    options.struct_size = 0;
    memset(&list, 0, sizeof(list));
    list.struct_size = (uint32_t)sizeof(list);
    print_status(reader_account_profiles_load("/tmp/never-used", &list, &options, &error), &error);
    return 0;
  }

  if (strcmp(argv[1], "relative") == 0 && argc == 2) {
    reader_account_profiles_list list;
    memset(&list, 0, sizeof(list));
    list.struct_size = (uint32_t)sizeof(list);
    print_status(reader_account_profiles_load("relative-store", &list, NULL, &error), &error);
    return 0;
  }

  if (strcmp(argv[1], "load") == 0 && argc == 3) {
    reader_account_profiles_list list;
    reader_account_profiles_status status = load_store(argv[2], &list, NULL, &error);
    print_status(status, &error);
    if (status == READER_ACCOUNT_PROFILES_OK) print_list(&list);
    return 0;
  }

  if (strcmp(argv[1], "cancel-load") == 0 && argc == 3) {
    reader_account_profiles_list list;
    reader_account_profiles_options options;
    memset(&options, 0, sizeof(options));
    options.struct_size = (uint32_t)sizeof(options);
    options.control.cancelled = cancel_now;
    reader_account_profiles_error_clear(&error);
    memset(&list, 0, sizeof(list));
    list.struct_size = (uint32_t)sizeof(list);
    print_status(reader_account_profiles_load(argv[2], &list, &options, &error), &error);
    return 0;
  }

  if ((strcmp(argv[1], "add") == 0 || strcmp(argv[1], "add-gen") == 0 ||
       strcmp(argv[1], "cancel-add") == 0) && argc >= 7) {
    reader_account_profile profile;
    reader_account_profiles_options options;
    reader_account_profiles_options *pointer = NULL;
    uint64_t generation = 0;
    reader_account_profiles_status status;
    make_profile(&profile, argv[3], argv[4], argv[5], argv[6]);
    if (strcmp(argv[1], "cancel-add") == 0) {
      memset(&options, 0, sizeof(options));
      options.struct_size = (uint32_t)sizeof(options);
      options.control.cancelled = cancel_now;
      pointer = &options;
    } else if (argc >= 8 || strcmp(argv[1], "add-gen") == 0) {
      memset(&options, 0, sizeof(options));
      options.struct_size = (uint32_t)sizeof(options);
      if (strcmp(argv[1], "add-gen") == 0) {
        options.flags = READER_ACCOUNT_PROFILES_CHECK_GENERATION;
        options.expected_generation = argc >= 8 ? strtoull(argv[7], NULL, 10) : 0ull;
      } else {
        options.lock_timeout_ms = (uint32_t)strtoul(argv[7], NULL, 10);
      }
      pointer = &options;
    }
    status = reader_account_profiles_add(argv[2], &profile, pointer, &generation, &error);
    print_status(status, &error);
    (void)printf("new_generation=%llu\n", (unsigned long long)generation);
    return 0;
  }

  if (strcmp(argv[1], "rename") == 0 && argc == 5) {
    uint64_t generation = 0;
    reader_account_profiles_status status =
        reader_account_profiles_rename(argv[2], argv[3], argv[4], NULL, &generation, &error);
    print_status(status, &error);
    (void)printf("new_generation=%llu\n", (unsigned long long)generation);
    return 0;
  }

  if (strcmp(argv[1], "remove") == 0 && argc == 4) {
    uint64_t generation = 0;
    reader_account_profiles_status status =
        reader_account_profiles_remove(argv[2], argv[3], NULL, &generation, &error);
    print_status(status, &error);
    (void)printf("new_generation=%llu\n", (unsigned long long)generation);
    return 0;
  }

  if (strcmp(argv[1], "activation") == 0 && argc == 4) {
    reader_account_profiles_activation plan;
    reader_account_profiles_status status;
    memset(&plan, 0, sizeof(plan));
    plan.struct_size = (uint32_t)sizeof(plan);
    status = reader_account_profiles_prepare_activation(argv[2], argv[3], NULL, &plan, &error);
    print_status(status, &error);
    if (status == READER_ACCOUNT_PROFILES_OK) print_plan(&plan);
    return 0;
  }

  if (strcmp(argv[1], "verify-nonterminated") == 0 && argc == 2) {
    reader_account_profiles_activation *bad = malloc(sizeof(*bad));
    reader_account_profiles_status status;
    if (!bad) return 2;
    memset(bad, 0x7f, sizeof(*bad));
    bad->struct_size = (uint32_t)sizeof(*bad);
    bad->profile.struct_size = (uint32_t)sizeof(bad->profile);
    memcpy(bad->profile.profile_id, "a1000000-0000-4000-8000-000000000001", 36);
    status = reader_account_profiles_verify_activation("unused", bad, NULL, &error);
    free(bad);
    print_status(status, &error);
    return status == READER_ACCOUNT_PROFILES_INVALID ? 0 : 2;
  }

  if (((strcmp(argv[1], "verify") == 0 || strcmp(argv[1], "verify-tampered") == 0) && argc == 4) ||
      (strcmp(argv[1], "verify-held") == 0 && argc == 5)) {
    reader_account_profiles_activation plan;
    reader_account_profiles_status prepare;
    reader_account_profiles_status verify;
    memset(&plan, 0, sizeof(plan));
    plan.struct_size = (uint32_t)sizeof(plan);
    prepare = reader_account_profiles_prepare_activation(argv[2], argv[3], NULL, &plan, &error);
    (void)printf("prepare=%s\n", reader_account_profiles_status_name(prepare));
    if (prepare != READER_ACCOUNT_PROFILES_OK) {
      print_status(prepare, &error);
      return 0;
    }
    if (strcmp(argv[1], "verify-held") == 0) {
      FILE *ready = fopen(argv[4], "wb");
      if (!ready) return 2;
      if (fputs("ready", ready) < 0 || fclose(ready) != 0) return 2;
      if (fgetc(stdin) != '1') return 2;
    }
    if (strcmp(argv[1], "verify-tampered") == 0) {
      size_t used = strlen(plan.product_path);
      if (used + 3u >= sizeof(plan.product_path)) return 2;
      plan.product_path[used] = 'x';
      plan.product_path[used + 1u] = '/';
      plan.product_path[used + 2u] = '\0';
    }
    reader_account_profiles_error_clear(&error);
    verify = reader_account_profiles_verify_activation(argv[2], &plan, NULL, &error);
    (void)printf("verify=%s\n", reader_account_profiles_status_name(verify));
    print_status(verify, &error);
    return 0;
  }

  if (strcmp(argv[1], "load-limit") == 0 && argc == 4) {
    reader_account_profiles_list list;
    reader_account_profiles_options options;
    memset(&options, 0, sizeof(options));
    options.struct_size = (uint32_t)sizeof(options);
    options.max_file_bytes = (size_t)strtoull(argv[3], NULL, 10);
    reader_account_profiles_error_clear(&error);
    memset(&list, 0, sizeof(list));
    list.struct_size = (uint32_t)sizeof(list);
    print_status(reader_account_profiles_load(argv[2], &list, &options, &error), &error);
    return 0;
  }

  if ((strcmp(argv[1], "verify-stale") == 0 && argc == 5) ||
      (strcmp(argv[1], "verify-missing") == 0 && argc == 4)) {
    reader_account_profiles_activation plan;
    reader_account_profiles_status prepare;
    reader_account_profiles_status verify;
    reader_account_profiles_status mutation;
    reader_account_profile replacement;
    uint64_t generation = 0;
    memset(&plan, 0, sizeof(plan));
    plan.struct_size = (uint32_t)sizeof(plan);
    prepare = reader_account_profiles_prepare_activation(argv[2], argv[3], NULL, &plan, &error);
    (void)printf("prepare=%s\n", reader_account_profiles_status_name(prepare));
    if (prepare != READER_ACCOUNT_PROFILES_OK) return 0;
    mutation = reader_account_profiles_remove(argv[2], argv[3], NULL, &generation, &error);
    (void)printf("remove=%s\n", reader_account_profiles_status_name(mutation));
    if (mutation == READER_ACCOUNT_PROFILES_OK && strcmp(argv[1], "verify-stale") == 0) {
      make_profile(&replacement, plan.profile.profile_id, argv[4], plan.profile.root_url,
                   plan.profile.display_name);
      mutation = reader_account_profiles_add(argv[2], &replacement, NULL, &generation, &error);
      (void)printf("readd=%s\n", reader_account_profiles_status_name(mutation));
    }
    reader_account_profiles_error_clear(&error);
    verify = reader_account_profiles_verify_activation(argv[2], &plan, NULL, &error);
    (void)printf("verify=%s\n", reader_account_profiles_status_name(verify));
    print_status(verify, &error);
    return 0;
  }

  if (strcmp(argv[1], "threads") == 0 && argc == 4) {
    unsigned count = (unsigned)strtoul(argv[3], NULL, 10);
    thread_args *args;
    unsigned index;
    int failures = 0;
    if (count == 0u || count > READER_ACCOUNT_PROFILES_MAX_PROFILES) return 2;
    args = (thread_args *)calloc(count, sizeof(thread_args));
    if (!args) return 2;
    for (index = 0; index < count; ++index) {
      args[index].store = argv[2];
      args[index].index = index;
      args[index].status = -1;
    }
#if defined(_WIN32)
    {
      HANDLE *handles = (HANDLE *)calloc(count, sizeof(HANDLE));
      if (!handles) { free(args); return 2; }
      for (index = 0; index < count; ++index)
        handles[index] = CreateThread(NULL, 0, thread_main, &args[index], 0, NULL);
      for (index = 0; index < count; ++index) {
        if (handles[index]) {
          WaitForSingleObject(handles[index], 120000);
          CloseHandle(handles[index]);
        }
      }
      free(handles);
    }
#else
    {
      pthread_t *threads = (pthread_t *)calloc(count, sizeof(pthread_t));
      if (!threads) { free(args); return 2; }
      for (index = 0; index < count; ++index)
        if (pthread_create(&threads[index], NULL, thread_main, &args[index]) != 0)
          args[index].status = -2;
      for (index = 0; index < count; ++index) pthread_join(threads[index], NULL);
      free(threads);
    }
#endif
    for (index = 0; index < count; ++index) {
      (void)printf("thread%u=%s\n", index,
                   reader_account_profiles_status_name((reader_account_profiles_status)args[index].status));
      if (args[index].status != READER_ACCOUNT_PROFILES_OK) failures += 1;
    }
    free(args);
    {
      reader_account_profiles_list list;
      reader_account_profiles_status status = load_store(argv[2], &list, NULL, &error);
      (void)printf("load=%s\n", reader_account_profiles_status_name(status));
      if (status == READER_ACCOUNT_PROFILES_OK) print_list(&list);
    }
    (void)printf("failures=%d\n", failures);
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
