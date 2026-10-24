/* SPDX-License-Identifier: MIT */
#ifndef READER_PREFERENCES_INTERNAL_H
#define READER_PREFERENCES_INTERNAL_H

#include "reader_preferences.h"

#define RP_DEFAULT_FILE_LIMIT 65536u
#define RP_JSON_CAPACITY 4096u

void rp_error_set(reader_preferences_error *error, reader_preferences_status status,
                  int system_error, size_t offset, const char *format, ...);
int rp_cancel_requested(const reader_preferences_control *control);

reader_preferences_status rp_validate_fields(const reader_preferences *preferences,
                                             reader_preferences_error *error);
reader_preferences_status rp_json_parse(const unsigned char *data, size_t size,
                                        reader_preferences *out,
                                        reader_preferences_error *error);
reader_preferences_status rp_json_write(const reader_preferences *preferences, char *buffer,
                                        size_t capacity, size_t *used,
                                        reader_preferences_error *error);
reader_preferences_status rp_read_file(const char *utf8_path, size_t max_bytes,
                                       const reader_preferences_control *control,
                                       unsigned char **data, size_t *size,
                                       reader_preferences_error *error);
reader_preferences_status rp_write_file_atomic(const char *utf8_path, const void *data,
                                               size_t size,
                                               const reader_preferences_control *control,
                                               reader_preferences_error *error);

#endif
