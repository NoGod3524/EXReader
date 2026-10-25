/* SPDX-License-Identifier: MIT */
#ifndef READER_ACCOUNT_PROFILES_INTERNAL_H
#define READER_ACCOUNT_PROFILES_INTERNAL_H

#include "reader_account_profiles.h"

#include <stddef.h>
#include <stdint.h>

/* Decoded canonical document. Caller-owned. */
typedef struct {
  uint64_t generation;
  uint32_t count;
  reader_account_profile items[READER_ACCOUNT_PROFILES_MAX_PROFILES];
} ap_document;

/* Normalised call options. */
typedef struct {
  reader_account_profiles_control control;
  uint32_t flags;
  uint64_t expected_generation;
  uint32_t lock_timeout_ms;
  size_t max_file_bytes;
} ap_options;

/* One held writer lock. */
typedef struct {
#if defined(_WIN32)
  void *handle;
#else
  int descriptor;
#endif
  int held;
} ap_lock;

typedef enum {
  AP_ENTRY_MISSING = 0,
  AP_ENTRY_FILE,
  AP_ENTRY_DIRECTORY,
  AP_ENTRY_LINK,
  AP_ENTRY_OTHER
} ap_entry_kind;

void ap_error_set(reader_account_profiles_error *error, reader_account_profiles_status status,
                  int system_error, size_t offset, const char *format, ...);
int ap_cancel_requested(const reader_account_profiles_control *control);
void ap_sleep_ms(unsigned milliseconds);

reader_account_profiles_status ap_resolve_options(const reader_account_profiles_options *options,
                                                  ap_options *out,
                                                  reader_account_profiles_error *error);
reader_account_profiles_status ap_check_string(const char *value, size_t maximum,
                                               reader_account_profiles_error *error,
                                               const char *what);
int ap_uuid_valid(const char *value);
reader_account_profiles_status ap_validate_uuid_field(const char *value, size_t offset,
                                                     reader_account_profiles_error *error);
reader_account_profiles_status ap_validate_url_field(const char *value, size_t offset,
                                                     reader_account_profiles_error *error);
reader_account_profiles_status ap_validate_name_field(const char *value, size_t offset,
                                                      reader_account_profiles_error *error);
reader_account_profiles_status ap_validate_profile_fields(const reader_account_profile *profile,
                                                          reader_account_profiles_error *error);

reader_account_profiles_status ap_join_path(char *out, size_t capacity, const char *base,
                                            const char *leaf);
reader_account_profiles_status ap_directory_path(char *out, size_t capacity, const char *base,
                                                 const char *id, const char *leaf);

reader_account_profiles_status ap_document_decode(const unsigned char *data, size_t size,
                                                  ap_document *out,
                                                  reader_account_profiles_error *error);
/* A missing document decodes to generation 0 and no profiles. */
reader_account_profiles_status ap_document_encode(const ap_document *document, char *buffer,
                                                  size_t capacity, size_t *used,
                                                  reader_account_profiles_error *error);

reader_account_profiles_status ap_lock_acquire(const char *store_dir, uint32_t timeout_ms,
                                               const reader_account_profiles_control *control,
                                               ap_lock *lock,
                                               reader_account_profiles_error *error);
void ap_lock_release(ap_lock *lock);

reader_account_profiles_status ap_read_file(const char *path, size_t max_bytes,
                                            unsigned char **data, size_t *size, int *present,
                                            const reader_account_profiles_control *control,
                                            reader_account_profiles_error *error);
reader_account_profiles_status ap_write_file_atomic(const char *directory, const char *path,
                                                    const void *data, size_t size,
                                                    const reader_account_profiles_control *control,
                                                    reader_account_profiles_error *error);
reader_account_profiles_status ap_ensure_directory(const char *path,
                                                   reader_account_profiles_error *error);
reader_account_profiles_status ap_verify_directory_chain(const char *path,
                                                         reader_account_profiles_error *error);
reader_account_profiles_status ap_inspect_entry(const char *path, ap_entry_kind *kind,
                                                uint64_t *size, uint32_t *link_count,
                                                reader_account_profiles_error *error);
#endif
