/* SPDX-License-Identifier: MIT */
#if defined(_WIN32)
#define _CRT_SECURE_NO_WARNINGS 1
#endif
#include "internal.h"

#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define AP_BINDING_PREFIX "EXReader account v1\n"
#define AP_BINDING_LIMIT 8400u
#define AP_ENCODE_SLACK 4096u

void ap_error_set(reader_account_profiles_error *error, reader_account_profiles_status status,
                  int system_error, size_t offset, const char *format, ...) {
  va_list args;
  if (!error) return;
  error->status = status;
  error->system_error = system_error;
  error->offset = offset;
  va_start(args, format);
  if (format) {
    (void)vsnprintf(error->message, sizeof(error->message), format, args);
  } else {
    error->message[0] = '\0';
  }
  va_end(args);
  error->message[sizeof(error->message) - 1u] = '\0';
}

int ap_cancel_requested(const reader_account_profiles_control *control) {
  return control && control->cancelled && control->cancelled(control->context);
}

reader_account_profiles_status ap_check_string(const char *value, size_t maximum,
                                               reader_account_profiles_error *error,
                                               const char *what) {
  size_t index;
  if (!value) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0, "%s is null", what);
    return READER_ACCOUNT_PROFILES_ARGUMENT;
  }
  for (index = 0; index <= maximum; ++index) {
    if (value[index] == '\0') return READER_ACCOUNT_PROFILES_OK;
  }
  ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0,
               "%s is not terminated within %u bytes", what, (unsigned)maximum);
  return READER_ACCOUNT_PROFILES_ARGUMENT;
}

int ap_uuid_valid(const char *value) {
  size_t index;
  int non_zero = 0;
  if (!value || strlen(value) != READER_ACCOUNT_PROFILES_UUID_BYTES) return 0;
  for (index = 0; index < READER_ACCOUNT_PROFILES_UUID_BYTES; ++index) {
    char byte = value[index];
    if (index == 8u || index == 13u || index == 18u || index == 23u) {
      if (byte != '-') return 0;
    } else if ((byte >= '0' && byte <= '9') || (byte >= 'a' && byte <= 'f')) {
      if (byte != '0') non_zero = 1;
    } else {
      return 0;
    }
  }
  return non_zero;
}

static int ap_utf8_next(const unsigned char *value, size_t *length, uint32_t *code) {
  unsigned char lead = value[0];
  size_t need;
  size_t index;
  uint32_t total;
  if (lead < 0x80u) {
    *length = 1u;
    *code = lead;
    return 1;
  }
  if ((lead & 0xE0u) == 0xC0u) {
    need = 1u;
    total = (uint32_t)(lead & 0x1Fu);
  } else if ((lead & 0xF0u) == 0xE0u) {
    need = 2u;
    total = (uint32_t)(lead & 0x0Fu);
  } else if ((lead & 0xF8u) == 0xF0u) {
    need = 3u;
    total = (uint32_t)(lead & 0x07u);
  } else {
    return 0;
  }
  for (index = 1u; index <= need; ++index) {
    unsigned char byte = value[index];
    if ((byte & 0xC0u) != 0x80u) return 0;
    total = (total << 6) | (uint32_t)(byte & 0x3Fu);
  }
  if (need == 1u && total < 0x80u) return 0;
  if (need == 2u && total < 0x800u) return 0;
  if (need == 3u && total < 0x10000u) return 0;
  if (total > 0x10FFFFu) return 0;
  if (total >= 0xD800u && total <= 0xDFFFu) return 0;
  *length = need + 1u;
  *code = total;
  return 1;
}

static int ap_utf8_valid(const unsigned char *value) {
  while (*value) {
    size_t length = 0;
    uint32_t code = 0;
    if (!ap_utf8_next(value, &length, &code)) return 0;
    value += length;
  }
  return 1;
}

static int ap_control_code(uint32_t code) {
  return code < 0x20u || (code >= 0x80u && code <= 0x9Fu);
}

reader_account_profiles_status ap_validate_uuid_field(const char *value, size_t offset,
                                                     reader_account_profiles_error *error) {
  if (!ap_uuid_valid(value)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, offset,
                 "a profile or account id is not a lowercase UUID");
    return READER_ACCOUNT_PROFILES_INVALID;
  }
  return READER_ACCOUNT_PROFILES_OK;
}

reader_account_profiles_status ap_validate_url_field(const char *value, size_t offset,
                                                     reader_account_profiles_error *error) {
  size_t length;
  size_t index;
  size_t authority_start;
  size_t authority_end;
  size_t colon = 0;
  if (!value) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, offset, "the root URL is null");
    return READER_ACCOUNT_PROFILES_INVALID;
  }
  length = strlen(value);
  if (length < 10u || length > READER_ACCOUNT_PROFILES_MAX_URL_BYTES) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, offset,
                 "the root URL length %u is outside 10..%u", (unsigned)length,
                 (unsigned)READER_ACCOUNT_PROFILES_MAX_URL_BYTES);
    return READER_ACCOUNT_PROFILES_INVALID;
  }
  if (memcmp(value, "https://", 8u) != 0) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, offset,
                 "the root URL must start with https://");
    return READER_ACCOUNT_PROFILES_INVALID;
  }
  authority_start = 8u;
  authority_end = authority_start;
  while (authority_end < length && value[authority_end] != '/') authority_end += 1u;
  if (authority_end == authority_start) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, offset,
                 "the root URL has no host");
    return READER_ACCOUNT_PROFILES_INVALID;
  }
  for (index = 0; index < length; ++index) {
    unsigned char byte = (unsigned char)value[index];
    if (byte < 0x21u || byte > 0x7Eu) {
      ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, offset,
                   "the root URL must be printable ASCII without spaces");
      return READER_ACCOUNT_PROFILES_INVALID;
    }
    if (byte == '"' || byte == '\\') {
      ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, offset,
                   "the root URL must not contain a quote or backslash");
      return READER_ACCOUNT_PROFILES_INVALID;
    }
    if (index >= authority_start && index < authority_end) {
      unsigned char authority = byte;
      if (authority == '@') {
        ap_error_set(error, READER_ACCOUNT_PROFILES_SECRET, 0, offset,
                     "the root URL carries userinfo");
        return READER_ACCOUNT_PROFILES_SECRET;
      }
      if (authority == '?') {
        ap_error_set(error, READER_ACCOUNT_PROFILES_SECRET, 0, offset,
                     "the root URL carries a query");
        return READER_ACCOUNT_PROFILES_SECRET;
      }
      if (!((authority >= 'A' && authority <= 'Z') ||
            (authority >= 'a' && authority <= 'z') ||
            (authority >= '0' && authority <= '9') ||
            authority == '.' || authority == '-' || authority == ':')) {
        ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, offset,
                     "the root URL host is not a plain host or host:port");
        return READER_ACCOUNT_PROFILES_INVALID;
      }
      if (authority == ':') {
        if (colon != 0u) {
          ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, offset,
                       "the root URL host has more than one port separator");
          return READER_ACCOUNT_PROFILES_INVALID;
        }
        colon = index;
      }
    } else if (byte == '?') {
      ap_error_set(error, READER_ACCOUNT_PROFILES_SECRET, 0, offset,
                   "the root URL carries a query");
      return READER_ACCOUNT_PROFILES_SECRET;
    } else if (byte == '#') {
      ap_error_set(error, READER_ACCOUNT_PROFILES_SECRET, 0, offset,
                   "the root URL carries a fragment");
      return READER_ACCOUNT_PROFILES_SECRET;
    }
  }
  if (colon != 0u) {
    if (colon + 1u == authority_end) {
      ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, offset,
                   "the root URL port is empty");
      return READER_ACCOUNT_PROFILES_INVALID;
    }
    for (index = colon + 1u; index < authority_end; ++index) {
      if (value[index] < '0' || value[index] > '9') {
        ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, offset,
                     "the root URL port is not numeric");
        return READER_ACCOUNT_PROFILES_INVALID;
      }
    }
  }
  if (value[length - 1u] != '/') {
    ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, offset,
                 "the root URL must end with a slash");
    return READER_ACCOUNT_PROFILES_INVALID;
  }
  return READER_ACCOUNT_PROFILES_OK;
}

reader_account_profiles_status ap_validate_name_field(const char *value, size_t offset,
                                                      reader_account_profiles_error *error) {
  size_t length;
  const unsigned char *cursor;
  if (!value) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, offset, "the display name is null");
    return READER_ACCOUNT_PROFILES_INVALID;
  }
  length = strlen(value);
  if (length == 0u || length > READER_ACCOUNT_PROFILES_MAX_NAME_BYTES) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, offset,
                 "the display name length %u is outside 1..%u", (unsigned)length,
                 (unsigned)READER_ACCOUNT_PROFILES_MAX_NAME_BYTES);
    return READER_ACCOUNT_PROFILES_INVALID;
  }
  if ((unsigned char)value[0] == 0x20u || (unsigned char)value[length - 1u] == 0x20u) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, offset,
                 "the display name starts or ends with a space");
    return READER_ACCOUNT_PROFILES_INVALID;
  }
  cursor = (const unsigned char *)value;
  while (*cursor) {
    size_t used = 0;
    uint32_t code = 0;
    if (!ap_utf8_next(cursor, &used, &code)) {
      ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, offset,
                   "the display name is not valid UTF-8");
      return READER_ACCOUNT_PROFILES_INVALID;
    }
    if (ap_control_code(code)) {
      ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, offset,
                   "the display name contains a control character");
      return READER_ACCOUNT_PROFILES_INVALID;
    }
    cursor += used;
  }
  return READER_ACCOUNT_PROFILES_OK;
}

reader_account_profiles_status ap_validate_profile_fields(const reader_account_profile *profile,
                                                          reader_account_profiles_error *error) {
  reader_account_profiles_status status;
  if (!profile) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0, "the profile is null");
    return READER_ACCOUNT_PROFILES_ARGUMENT;
  }
  if (profile->struct_size != (uint32_t)sizeof(reader_account_profile)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0,
                 "profile struct_size %u != %u", (unsigned)profile->struct_size,
                 (unsigned)sizeof(reader_account_profile));
    return READER_ACCOUNT_PROFILES_ARGUMENT;
  }
  status = ap_check_string(profile->profile_id, READER_ACCOUNT_PROFILES_UUID_BYTES,
                           error, "profile_id");
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  status = ap_check_string(profile->account_id, READER_ACCOUNT_PROFILES_UUID_BYTES,
                           error, "account_id");
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  status = ap_check_string(profile->root_url, READER_ACCOUNT_PROFILES_MAX_URL_BYTES,
                           error, "root_url");
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  status = ap_check_string(profile->display_name, READER_ACCOUNT_PROFILES_MAX_NAME_BYTES,
                           error, "display_name");
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  if (!ap_utf8_valid((const unsigned char *)profile->display_name)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, 0,
                 "the display name is not valid UTF-8");
    return READER_ACCOUNT_PROFILES_INVALID;
  }
  status = ap_validate_uuid_field(profile->profile_id, 0, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  status = ap_validate_uuid_field(profile->account_id, 0, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  status = ap_validate_url_field(profile->root_url, 0, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  return ap_validate_name_field(profile->display_name, 0, error);
}

static int ap_separator(char byte) { return byte == '/' || byte == '\\'; }

static int ap_store_is_absolute(const char *path) {
#if defined(_WIN32)
  if (path[0] != '\0' && path[1] == ':' && ap_separator(path[2])) return 1;
  if (ap_separator(path[0]) && ap_separator(path[1])) return 1;
  return 0;
#else
  return path[0] == '/';
#endif
}

static reader_account_profiles_status ap_normalize_store(const char *store_dir, char *out,
                                                         size_t capacity,
                                                         reader_account_profiles_error *error) {
  size_t length;
  size_t index;
  size_t root;
  if (!store_dir || store_dir[0] == '\0') {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0,
                 "the store directory is null or empty");
    return READER_ACCOUNT_PROFILES_ARGUMENT;
  }
  length = strlen(store_dir);
  if (length < 2u || !ap_store_is_absolute(store_dir)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0,
                 "the store directory is not absolute");
    return READER_ACCOUNT_PROFILES_ARGUMENT;
  }
  if (length >= capacity) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0,
                 "the store directory exceeds %u bytes",
                 (unsigned)READER_ACCOUNT_PROFILES_MAX_STORE_PATH_BYTES);
    return READER_ACCOUNT_PROFILES_ARGUMENT;
  }
#if defined(_WIN32)
  root = (length >= 3u && store_dir[1] == ':') ? 3u : 2u;
#else
  root = 1u;
#endif
  while (length > root && ap_separator(store_dir[length - 1u])) length -= 1u;
  if (length > READER_ACCOUNT_PROFILES_MAX_STORE_PATH_BYTES) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0,
                 "the store directory exceeds %u bytes",
                 (unsigned)READER_ACCOUNT_PROFILES_MAX_STORE_PATH_BYTES);
    return READER_ACCOUNT_PROFILES_ARGUMENT;
  }
  for (index = root; index < length; ++index) {
    if (ap_separator(store_dir[index]) && index + 2u < length &&
        store_dir[index + 1u] == '.' && store_dir[index + 2u] == '.' &&
        (index + 3u == length || ap_separator(store_dir[index + 3u]))) {
      ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0,
                   "the store directory must not contain ..");
      return READER_ACCOUNT_PROFILES_ARGUMENT;
    }
  }
  memcpy(out, store_dir, length);
  out[length] = '\0';
  return READER_ACCOUNT_PROFILES_OK;
}

reader_account_profiles_status ap_join_path(char *out, size_t capacity, const char *base,
                                            const char *leaf) {
  size_t base_length = strlen(base);
  size_t leaf_length = strlen(leaf);
  int needs_separator = base_length > 0u && !ap_separator(base[base_length - 1u]);
  if (base_length + (size_t)needs_separator + leaf_length + 1u > capacity) {
    return READER_ACCOUNT_PROFILES_LIMIT;
  }
  memcpy(out, base, base_length);
  if (needs_separator) out[base_length++] = '/';
  memcpy(out + base_length, leaf, leaf_length + 1u);
  return READER_ACCOUNT_PROFILES_OK;
}

reader_account_profiles_status ap_directory_path(char *out, size_t capacity, const char *base,
                                                 const char *id, const char *leaf) {
  char root[READER_ACCOUNT_PROFILES_MAX_STORE_PATH_BYTES + 64u];
  char joined[READER_ACCOUNT_PROFILES_MAX_PATH_BYTES + 32u];
  reader_account_profiles_status status = ap_join_path(root, sizeof(root), base, "profiles");
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  status = ap_join_path(joined, sizeof(joined), root, id);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  if (!leaf) {
    if (strlen(joined) + 1u > capacity) return READER_ACCOUNT_PROFILES_LIMIT;
    memcpy(out, joined, strlen(joined) + 1u);
    return READER_ACCOUNT_PROFILES_OK;
  }
  return ap_join_path(out, capacity, joined, leaf);
}

reader_account_profiles_status ap_resolve_options(const reader_account_profiles_options *options,
                                                  ap_options *out,
                                                  reader_account_profiles_error *error) {
  memset(out, 0, sizeof(*out));
  out->lock_timeout_ms = READER_ACCOUNT_PROFILES_DEFAULT_LOCK_TIMEOUT_MS;
  out->max_file_bytes = READER_ACCOUNT_PROFILES_MAX_FILE_BYTES;
  if (!options) return READER_ACCOUNT_PROFILES_OK;
  if (options->struct_size != (uint32_t)sizeof(reader_account_profiles_options)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0,
                 "options struct_size %u != %u", (unsigned)options->struct_size,
                 (unsigned)sizeof(reader_account_profiles_options));
    return READER_ACCOUNT_PROFILES_ARGUMENT;
  }
  if ((options->flags & ~(uint32_t)READER_ACCOUNT_PROFILES_CHECK_GENERATION) != 0u) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0,
                 "options flags %#x are unknown", (unsigned)options->flags);
    return READER_ACCOUNT_PROFILES_ARGUMENT;
  }
  out->control = options->control;
  out->flags = options->flags;
  out->expected_generation = options->expected_generation;
  if (options->lock_timeout_ms != 0u) {
    if (options->lock_timeout_ms > READER_ACCOUNT_PROFILES_MAX_LOCK_TIMEOUT_MS) {
      ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0,
                   "lock_timeout_ms %u exceeds %u", (unsigned)options->lock_timeout_ms,
                   (unsigned)READER_ACCOUNT_PROFILES_MAX_LOCK_TIMEOUT_MS);
      return READER_ACCOUNT_PROFILES_ARGUMENT;
    }
    out->lock_timeout_ms = options->lock_timeout_ms;
  }
  if (options->max_file_bytes != 0u) {
    if (options->max_file_bytes > READER_ACCOUNT_PROFILES_MAX_FILE_BYTES) {
      ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0,
                   "max_file_bytes may only lower the %u-byte ceiling",
                   (unsigned)READER_ACCOUNT_PROFILES_MAX_FILE_BYTES);
      return READER_ACCOUNT_PROFILES_ARGUMENT;
    }
    out->max_file_bytes = options->max_file_bytes;
  }
  return READER_ACCOUNT_PROFILES_OK;
}

static reader_account_profiles_status ap_document_file(const char *store, char *path,
                                                       size_t capacity,
                                                       reader_account_profiles_error *error) {
  reader_account_profiles_status status = ap_join_path(path, capacity, store, "profiles.json");
  if (status != READER_ACCOUNT_PROFILES_OK) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_LIMIT, 0, 0,
                 "the store path is too long for a document path");
  }
  return status;
}

static reader_account_profiles_status ap_load_document(const char *store, const ap_options *options,
                                                       ap_document *document,
                                                       reader_account_profiles_error *error) {
  char path[READER_ACCOUNT_PROFILES_MAX_PATH_BYTES + 32u];
  unsigned char *data = NULL;
  size_t size = 0;
  int found = 0;
  reader_account_profiles_status status = ap_document_file(store, path, sizeof(path), error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  status = ap_read_file(path, options->max_file_bytes, &data, &size, &found,
                        &options->control, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  if (!found) {
    memset(document, 0, sizeof(*document));
    return READER_ACCOUNT_PROFILES_OK;
  }
  status = ap_document_decode(data, size, document, error);
  free(data);
  return status;
}

static reader_account_profiles_status ap_store_document(const char *store,
                                                        const ap_document *document,
                                                        const ap_options *options,
                                                        reader_account_profiles_error *error) {
  char path[READER_ACCOUNT_PROFILES_MAX_PATH_BYTES + 32u];
  char *text;
  size_t used = 0;
  reader_account_profiles_status status = ap_document_file(store, path, sizeof(path), error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  text = (char *)malloc(options->max_file_bytes + AP_ENCODE_SLACK);
  if (!text) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_IO, ENOMEM, 0, "out of memory");
    return READER_ACCOUNT_PROFILES_IO;
  }
  status = ap_document_encode(document, text, options->max_file_bytes + AP_ENCODE_SLACK,
                              &used, error);
  if (status != READER_ACCOUNT_PROFILES_OK) {
    free(text);
    return status;
  }
  if (used > options->max_file_bytes) {
    free(text);
    ap_error_set(error, READER_ACCOUNT_PROFILES_LIMIT, 0, 0,
                 "the document is %llu bytes, limit is %llu",
                 (unsigned long long)used, (unsigned long long)options->max_file_bytes);
    return READER_ACCOUNT_PROFILES_LIMIT;
  }
  status = ap_write_file_atomic(store, path, text, used, &options->control, error);
  free(text);
  return status;
}

static const char *ap_find_profile(const ap_document *document, const char *profile_id,
                                   uint32_t *position) {
  uint32_t index;
  for (index = 0; index < document->count; ++index) {
    if (strcmp(document->items[index].profile_id, profile_id) == 0) {
      if (position) *position = index;
      return document->items[index].profile_id;
    }
  }
  return NULL;
}

void reader_account_profiles_error_clear(reader_account_profiles_error *error) {
  if (!error) return;
  memset(error, 0, sizeof(*error));
  error->struct_size = (uint32_t)sizeof(*error);
}

uint32_t reader_account_profiles_abi_version(void) {
  return READER_ACCOUNT_PROFILES_ABI_VERSION;
}

const char *reader_account_profiles_status_name(reader_account_profiles_status status) {
  switch (status) {
    case READER_ACCOUNT_PROFILES_OK: return "OK";
    case READER_ACCOUNT_PROFILES_ARGUMENT: return "ARGUMENT";
    case READER_ACCOUNT_PROFILES_IO: return "IO";
    case READER_ACCOUNT_PROFILES_FORMAT: return "FORMAT";
    case READER_ACCOUNT_PROFILES_VERSION: return "VERSION";
    case READER_ACCOUNT_PROFILES_INVALID: return "INVALID";
    case READER_ACCOUNT_PROFILES_SECRET: return "SECRET";
    case READER_ACCOUNT_PROFILES_CANCELLED: return "CANCELLED";
    case READER_ACCOUNT_PROFILES_LIMIT: return "LIMIT";
    case READER_ACCOUNT_PROFILES_NOT_FOUND: return "NOT_FOUND";
    case READER_ACCOUNT_PROFILES_EXISTS: return "EXISTS";
    case READER_ACCOUNT_PROFILES_CONFLICT: return "CONFLICT";
    case READER_ACCOUNT_PROFILES_LOCKED: return "LOCKED";
    case READER_ACCOUNT_PROFILES_UNSAFE_PATH: return "UNSAFE_PATH";
    case READER_ACCOUNT_PROFILES_BINDING: return "BINDING";
    default: return "UNKNOWN";
  }
}

reader_account_profiles_status
reader_account_profiles_validate(const reader_account_profile *profile,
                                 reader_account_profiles_error *error) {
  reader_account_profiles_error_clear(error);
  return ap_validate_profile_fields(profile, error);
}

reader_account_profiles_status
reader_account_profiles_load(const char *store_dir, reader_account_profiles_list *out,
                             const reader_account_profiles_options *options,
                             reader_account_profiles_error *error) {
  char store[READER_ACCOUNT_PROFILES_MAX_STORE_PATH_BYTES + 1u];
  ap_options resolved;
  ap_document document;
  reader_account_profiles_list candidate;
  reader_account_profiles_status status;

  reader_account_profiles_error_clear(error);
  if (!out || out->struct_size != (uint32_t)sizeof(reader_account_profiles_list)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0,
                 "list struct_size %u is not %u", (unsigned)(out ? out->struct_size : 0u),
                 (unsigned)sizeof(reader_account_profiles_list));
    return READER_ACCOUNT_PROFILES_ARGUMENT;
  }
  status = ap_normalize_store(store_dir, store, sizeof(store), error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  status = ap_resolve_options(options, &resolved, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  if (ap_cancel_requested(&resolved.control)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_CANCELLED, 0, 0, "load cancelled before reading");
    return READER_ACCOUNT_PROFILES_CANCELLED;
  }
  status = ap_load_document(store, &resolved, &document, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  if (ap_cancel_requested(&resolved.control)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_CANCELLED, 0, 0, "load cancelled before commit");
    return READER_ACCOUNT_PROFILES_CANCELLED;
  }
  memset(&candidate, 0, sizeof(candidate));
  candidate.struct_size = (uint32_t)sizeof(candidate);
  candidate.generation = document.generation;
  candidate.count = document.count;
  memcpy(candidate.profiles, document.items, sizeof(document.items));
  *out = candidate;
  return READER_ACCOUNT_PROFILES_OK;
}

reader_account_profiles_status
reader_account_profiles_add(const char *store_dir, const reader_account_profile *profile,
                            const reader_account_profiles_options *options,
                            uint64_t *new_generation, reader_account_profiles_error *error) {
  char store[READER_ACCOUNT_PROFILES_MAX_STORE_PATH_BYTES + 1u];
  ap_options resolved;
  ap_document document;
  ap_lock lock;
  uint32_t index;
  reader_account_profiles_status status;

  reader_account_profiles_error_clear(error);
  if (new_generation) *new_generation = 0;
  status = ap_validate_profile_fields(profile, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  status = ap_normalize_store(store_dir, store, sizeof(store), error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  status = ap_resolve_options(options, &resolved, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  if (ap_cancel_requested(&resolved.control)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_CANCELLED, 0, 0, "add cancelled before the lock");
    return READER_ACCOUNT_PROFILES_CANCELLED;
  }
  status = ap_lock_acquire(store, resolved.lock_timeout_ms, &resolved.control, &lock, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  status = ap_load_document(store, &resolved, &document, error);
  if (status == READER_ACCOUNT_PROFILES_OK &&
      (resolved.flags & READER_ACCOUNT_PROFILES_CHECK_GENERATION) != 0u &&
      resolved.expected_generation != document.generation) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_CONFLICT, 0, 0,
                 "generation %llu is not the expected %llu",
                 (unsigned long long)document.generation,
                 (unsigned long long)resolved.expected_generation);
    status = READER_ACCOUNT_PROFILES_CONFLICT;
  }
  if (status == READER_ACCOUNT_PROFILES_OK) {
    if (document.count >= READER_ACCOUNT_PROFILES_MAX_PROFILES) {
      ap_error_set(error, READER_ACCOUNT_PROFILES_LIMIT, 0, 0,
                   "the store already holds %u profiles",
                   (unsigned)READER_ACCOUNT_PROFILES_MAX_PROFILES);
      status = READER_ACCOUNT_PROFILES_LIMIT;
    }
  }
  if (status == READER_ACCOUNT_PROFILES_OK) {
    for (index = 0; index < document.count; ++index) {
      if (strcmp(document.items[index].profile_id, profile->profile_id) == 0) {
        ap_error_set(error, READER_ACCOUNT_PROFILES_EXISTS, 0, 0,
                     "a profile with this id already exists");
        status = READER_ACCOUNT_PROFILES_EXISTS;
        break;
      }
      if (strcmp(document.items[index].account_id, profile->account_id) == 0 &&
          strcmp(document.items[index].root_url, profile->root_url) == 0) {
        ap_error_set(error, READER_ACCOUNT_PROFILES_EXISTS, 0, 0,
                     "this account and root URL pair already exists");
        status = READER_ACCOUNT_PROFILES_EXISTS;
        break;
      }
    }
  }
  if (status == READER_ACCOUNT_PROFILES_OK) {
    document.items[document.count] = *profile;
    document.items[document.count].struct_size = (uint32_t)sizeof(reader_account_profile);
    document.count += 1u;
    document.generation += 1u;
    status = ap_store_document(store, &document, &resolved, error);
    if (status == READER_ACCOUNT_PROFILES_OK && new_generation) *new_generation = document.generation;
  }
  ap_lock_release(&lock);
  return status;
}

reader_account_profiles_status
reader_account_profiles_rename(const char *store_dir, const char *profile_id,
                               const char *display_name,
                               const reader_account_profiles_options *options,
                               uint64_t *new_generation, reader_account_profiles_error *error) {
  char store[READER_ACCOUNT_PROFILES_MAX_STORE_PATH_BYTES + 1u];
  ap_options resolved;
  ap_document document;
  ap_lock lock;
  uint32_t position = 0;
  reader_account_profiles_status status;

  reader_account_profiles_error_clear(error);
  if (new_generation) *new_generation = 0;
  if (!ap_uuid_valid(profile_id)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, 0,
                 "the profile id is not a lowercase UUID");
    return READER_ACCOUNT_PROFILES_INVALID;
  }
  status = ap_validate_name_field(display_name, 0, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  status = ap_normalize_store(store_dir, store, sizeof(store), error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  status = ap_resolve_options(options, &resolved, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  if (ap_cancel_requested(&resolved.control)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_CANCELLED, 0, 0, "rename cancelled before the lock");
    return READER_ACCOUNT_PROFILES_CANCELLED;
  }
  status = ap_lock_acquire(store, resolved.lock_timeout_ms, &resolved.control, &lock, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  status = ap_load_document(store, &resolved, &document, error);
  if (status == READER_ACCOUNT_PROFILES_OK &&
      (resolved.flags & READER_ACCOUNT_PROFILES_CHECK_GENERATION) != 0u &&
      resolved.expected_generation != document.generation) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_CONFLICT, 0, 0,
                 "generation %llu is not the expected %llu",
                 (unsigned long long)document.generation,
                 (unsigned long long)resolved.expected_generation);
    status = READER_ACCOUNT_PROFILES_CONFLICT;
  }
  if (status == READER_ACCOUNT_PROFILES_OK && !ap_find_profile(&document, profile_id, &position)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_NOT_FOUND, 0, 0, "no profile with this id exists");
    status = READER_ACCOUNT_PROFILES_NOT_FOUND;
  }
  if (status == READER_ACCOUNT_PROFILES_OK) {
    (void)snprintf(document.items[position].display_name,
                   sizeof(document.items[position].display_name), "%s", display_name);
    document.generation += 1u;
    status = ap_store_document(store, &document, &resolved, error);
    if (status == READER_ACCOUNT_PROFILES_OK && new_generation) *new_generation = document.generation;
  }
  ap_lock_release(&lock);
  return status;
}

reader_account_profiles_status
reader_account_profiles_remove(const char *store_dir, const char *profile_id,
                               const reader_account_profiles_options *options,
                               uint64_t *new_generation, reader_account_profiles_error *error) {
  char store[READER_ACCOUNT_PROFILES_MAX_STORE_PATH_BYTES + 1u];
  ap_options resolved;
  ap_document document;
  ap_lock lock;
  uint32_t position = 0;
  reader_account_profiles_status status;

  reader_account_profiles_error_clear(error);
  if (new_generation) *new_generation = 0;
  if (!ap_uuid_valid(profile_id)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, 0,
                 "the profile id is not a lowercase UUID");
    return READER_ACCOUNT_PROFILES_INVALID;
  }
  status = ap_normalize_store(store_dir, store, sizeof(store), error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  status = ap_resolve_options(options, &resolved, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  if (ap_cancel_requested(&resolved.control)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_CANCELLED, 0, 0, "remove cancelled before the lock");
    return READER_ACCOUNT_PROFILES_CANCELLED;
  }
  status = ap_lock_acquire(store, resolved.lock_timeout_ms, &resolved.control, &lock, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  status = ap_load_document(store, &resolved, &document, error);
  if (status == READER_ACCOUNT_PROFILES_OK &&
      (resolved.flags & READER_ACCOUNT_PROFILES_CHECK_GENERATION) != 0u &&
      resolved.expected_generation != document.generation) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_CONFLICT, 0, 0,
                 "generation %llu is not the expected %llu",
                 (unsigned long long)document.generation,
                 (unsigned long long)resolved.expected_generation);
    status = READER_ACCOUNT_PROFILES_CONFLICT;
  }
  if (status == READER_ACCOUNT_PROFILES_OK && !ap_find_profile(&document, profile_id, &position)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_NOT_FOUND, 0, 0, "no profile with this id exists");
    status = READER_ACCOUNT_PROFILES_NOT_FOUND;
  }
  if (status == READER_ACCOUNT_PROFILES_OK) {
    uint32_t index;
    for (index = position; index + 1u < document.count; ++index)
      document.items[index] = document.items[index + 1u];
    memset(&document.items[document.count - 1u], 0, sizeof(reader_account_profile));
    document.count -= 1u;
    document.generation += 1u;
    status = ap_store_document(store, &document, &resolved, error);
    if (status == READER_ACCOUNT_PROFILES_OK && new_generation) *new_generation = document.generation;
  }
  ap_lock_release(&lock);
  return status;
}

static reader_account_profiles_status
ap_check_library(const char *product, const char *account_id, const char *root_url,
                 reader_account_profiles_error *error) {
  char binding[READER_ACCOUNT_PROFILES_MAX_PATH_BYTES + 64u];
  char expected[READER_ACCOUNT_PROFILES_MAX_URL_BYTES + READER_ACCOUNT_PROFILES_UUID_BYTES +
                 sizeof(AP_BINDING_PREFIX) + 8u];
  ap_entry_kind kind = AP_ENTRY_MISSING;
  ap_entry_kind library_kind = AP_ENTRY_MISSING;
  uint64_t size = 0;
  uint64_t library_size = 0;
  uint32_t links = 0;
  uint32_t library_links = 0;
  size_t expected_length;
  reader_account_profiles_status status;

  status = ap_inspect_entry(product, &library_kind, &library_size, &library_links, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  if (library_kind == AP_ENTRY_LINK || library_kind == AP_ENTRY_DIRECTORY ||
      library_kind == AP_ENTRY_OTHER) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_UNSAFE_PATH, 0, 0,
                 "the product library is not a regular file");
    return READER_ACCOUNT_PROFILES_UNSAFE_PATH;
  }
  if (library_kind == AP_ENTRY_FILE && library_links != 1u) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_UNSAFE_PATH, 0, 0,
                 "the product library has more than one hard link");
    return READER_ACCOUNT_PROFILES_UNSAFE_PATH;
  }
  status = ap_join_path(binding, sizeof(binding), product, ".sync-account");
  if (status != READER_ACCOUNT_PROFILES_OK) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_LIMIT, 0, 0,
                 "the store path is too long for a binding path");
    return status;
  }
  status = ap_inspect_entry(binding, &kind, &size, &links, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  if (kind == AP_ENTRY_MISSING) {
    if (library_kind == AP_ENTRY_FILE && library_size > 0u) {
      ap_error_set(error, READER_ACCOUNT_PROFILES_BINDING, 0, 0,
                   "the product library has no binding and is not empty");
      return READER_ACCOUNT_PROFILES_BINDING;
    }
    return READER_ACCOUNT_PROFILES_OK;
  }
  if (kind != AP_ENTRY_FILE || links != 1u) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_UNSAFE_PATH, 0, 0,
                 "the binding file is not a single-link regular file");
    return READER_ACCOUNT_PROFILES_UNSAFE_PATH;
  }
  if (size > (uint64_t)AP_BINDING_LIMIT) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_BINDING, 0, 0,
                 "the binding file is larger than expected");
    return READER_ACCOUNT_PROFILES_BINDING;
  }
  expected_length = (size_t)snprintf(expected, sizeof(expected), "%s%s\n%s\n", AP_BINDING_PREFIX,
                                     account_id, root_url);
  {
    unsigned char *data = NULL;
    size_t read_size = 0;
    int present = 0;
    reader_account_profiles_control none;
    none.cancelled = NULL;
    none.context = NULL;
    status = ap_read_file(binding, AP_BINDING_LIMIT, &data, &read_size, &present, &none, error);
    if (status != READER_ACCOUNT_PROFILES_OK) return status;
    if (!present || read_size != expected_length || memcmp(data, expected, expected_length) != 0) {
      free(data);
      ap_error_set(error, READER_ACCOUNT_PROFILES_BINDING, 0, 0,
                   "the product library is bound to another account or root URL");
      return READER_ACCOUNT_PROFILES_BINDING;
    }
    free(data);
  }
  return READER_ACCOUNT_PROFILES_OK;
}

reader_account_profiles_status
reader_account_profiles_prepare_activation(const char *store_dir, const char *profile_id,
                                           const reader_account_profiles_options *options,
                                           reader_account_profiles_activation *out,
                                           reader_account_profiles_error *error) {
  char store[READER_ACCOUNT_PROFILES_MAX_STORE_PATH_BYTES + 1u];
  char root[READER_ACCOUNT_PROFILES_MAX_PATH_BYTES + 32u];
  char directory[READER_ACCOUNT_PROFILES_MAX_PATH_BYTES + 32u];
  ap_options resolved;
  ap_document document;
  ap_lock lock;
  reader_account_profiles_activation plan;
  uint32_t position = 0;
  reader_account_profiles_status status;

  reader_account_profiles_error_clear(error);
  if (!out || out->struct_size != (uint32_t)sizeof(reader_account_profiles_activation)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0,
                 "activation struct_size %u is not %u",
                 (unsigned)(out ? out->struct_size : 0u),
                 (unsigned)sizeof(reader_account_profiles_activation));
    return READER_ACCOUNT_PROFILES_ARGUMENT;
  }
  if (!ap_uuid_valid(profile_id)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, 0,
                 "the profile id is not a lowercase UUID");
    return READER_ACCOUNT_PROFILES_INVALID;
  }
  status = ap_normalize_store(store_dir, store, sizeof(store), error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  status = ap_resolve_options(options, &resolved, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  if (ap_cancel_requested(&resolved.control)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_CANCELLED, 0, 0,
                 "activation cancelled before the lock");
    return READER_ACCOUNT_PROFILES_CANCELLED;
  }
  status = ap_lock_acquire(store, resolved.lock_timeout_ms, &resolved.control, &lock, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  status = ap_load_document(store, &resolved, &document, error);
  if (status == READER_ACCOUNT_PROFILES_OK && !ap_find_profile(&document, profile_id, &position)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_NOT_FOUND, 0, 0, "no profile with this id exists");
    status = READER_ACCOUNT_PROFILES_NOT_FOUND;
  }
  if (status == READER_ACCOUNT_PROFILES_OK) {
    status = ap_verify_directory_chain(store, error);
  }
  if (status == READER_ACCOUNT_PROFILES_OK) {
    status = ap_join_path(root, sizeof(root), store, "profiles");
  }
  if (status == READER_ACCOUNT_PROFILES_OK) status = ap_ensure_directory(root, error);
  if (status == READER_ACCOUNT_PROFILES_OK) {
    status = ap_directory_path(directory, sizeof(directory), store, profile_id, NULL);
    if (status == READER_ACCOUNT_PROFILES_OK) status = ap_ensure_directory(directory, error);
  }
  if (status == READER_ACCOUNT_PROFILES_OK) {
    status = ap_directory_path(directory, sizeof(directory), store, profile_id, "private");
    if (status == READER_ACCOUNT_PROFILES_OK) status = ap_ensure_directory(directory, error);
  }
  if (status == READER_ACCOUNT_PROFILES_OK) {
    status = ap_directory_path(directory, sizeof(directory), store, profile_id, "originals");
    if (status == READER_ACCOUNT_PROFILES_OK) status = ap_ensure_directory(directory, error);
  }
  if (status == READER_ACCOUNT_PROFILES_OK) {
    status = ap_directory_path(directory, sizeof(directory), store, profile_id, "private");
    if (status == READER_ACCOUNT_PROFILES_OK) status = ap_verify_directory_chain(directory, error);
  }
  if (status == READER_ACCOUNT_PROFILES_OK) {
    char product[READER_ACCOUNT_PROFILES_MAX_PATH_BYTES + 32u];
    status = ap_directory_path(product, sizeof(product), store, profile_id, "library.sqlite");
    if (status == READER_ACCOUNT_PROFILES_OK) {
      status = ap_check_library(product, document.items[position].account_id,
                                document.items[position].root_url, error);
      if (status == READER_ACCOUNT_PROFILES_OK) {
        memset(&plan, 0, sizeof(plan));
        plan.struct_size = (uint32_t)sizeof(plan);
        plan.store_generation = document.generation;
        plan.profile = document.items[position];
        {
          size_t product_length = strlen(product);
          if (product_length >= sizeof(plan.product_path)) {
            status = READER_ACCOUNT_PROFILES_LIMIT;
            ap_error_set(error, READER_ACCOUNT_PROFILES_LIMIT, 0, 0,
                         "the derived product path exceeds the plan capacity");
          } else {
            memcpy(plan.product_path, product, product_length + 1u);
          }
        }
        status = ap_directory_path(plan.private_directory, sizeof(plan.private_directory), store,
                                   profile_id, "private");
        if (status == READER_ACCOUNT_PROFILES_OK)
          status = ap_directory_path(plan.original_directory, sizeof(plan.original_directory),
                                     store, profile_id, "originals");
        if (status == READER_ACCOUNT_PROFILES_OK) *out = plan;
      }
    }
  }
  ap_lock_release(&lock);
  return status;
}

reader_account_profiles_status
reader_account_profiles_verify_activation(const char *store_dir,
                                          const reader_account_profiles_activation *plan,
                                          const reader_account_profiles_options *options,
                                          reader_account_profiles_error *error) {
  char store[READER_ACCOUNT_PROFILES_MAX_STORE_PATH_BYTES + 1u];
  char derived[READER_ACCOUNT_PROFILES_MAX_PATH_BYTES + 32u];
  ap_options resolved;
  ap_document document;
  uint32_t position = 0;
  reader_account_profiles_status status;

  reader_account_profiles_error_clear(error);
  if (!plan || plan->struct_size != (uint32_t)sizeof(reader_account_profiles_activation)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0,
                 "activation struct_size %u is not %u",
                 (unsigned)(plan ? plan->struct_size : 0u),
                 (unsigned)sizeof(reader_account_profiles_activation));
    return READER_ACCOUNT_PROFILES_ARGUMENT;
  }
  if (plan->profile.struct_size != (uint32_t)sizeof(reader_account_profile)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0,
                 "plan profile struct_size is not %u",
                 (unsigned)sizeof(reader_account_profile));
    return READER_ACCOUNT_PROFILES_ARGUMENT;
  }
  if (!ap_uuid_valid(plan->profile.profile_id)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_INVALID, 0, 0,
                 "the plan profile id is not a lowercase UUID");
    return READER_ACCOUNT_PROFILES_INVALID;
  }
  status = ap_normalize_store(store_dir, store, sizeof(store), error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  status = ap_resolve_options(options, &resolved, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  if (ap_cancel_requested(&resolved.control)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_CANCELLED, 0, 0,
                 "verification cancelled before reading");
    return READER_ACCOUNT_PROFILES_CANCELLED;
  }
  status = ap_load_document(store, &resolved, &document, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  if (!ap_find_profile(&document, plan->profile.profile_id, &position)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_NOT_FOUND, 0, 0,
                 "the plan profile no longer exists");
    return READER_ACCOUNT_PROFILES_NOT_FOUND;
  }
  if (strcmp(document.items[position].account_id, plan->profile.account_id) != 0 ||
      strcmp(document.items[position].root_url, plan->profile.root_url) != 0) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_CONFLICT, 0, 0,
                 "the plan no longer matches its profile");
    return READER_ACCOUNT_PROFILES_CONFLICT;
  }
  status = ap_directory_path(derived, sizeof(derived), store, plan->profile.profile_id,
                             "library.sqlite");
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  if (strcmp(derived, plan->product_path) != 0) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0,
                 "the plan product path is not the derived path");
    return READER_ACCOUNT_PROFILES_ARGUMENT;
  }
  status = ap_directory_path(derived, sizeof(derived), store, plan->profile.profile_id, "private");
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  if (strcmp(derived, plan->private_directory) != 0) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0,
                 "the plan private directory is not the derived path");
    return READER_ACCOUNT_PROFILES_ARGUMENT;
  }
  status = ap_directory_path(derived, sizeof(derived), store, plan->profile.profile_id,
                             "originals");
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  if (strcmp(derived, plan->original_directory) != 0) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_ARGUMENT, 0, 0,
                 "the plan original directory is not the derived path");
    return READER_ACCOUNT_PROFILES_ARGUMENT;
  }
  status = ap_verify_directory_chain(plan->private_directory, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  status = ap_check_library(plan->product_path, plan->profile.account_id,
                            plan->profile.root_url, error);
  if (status != READER_ACCOUNT_PROFILES_OK) return status;
  if (ap_cancel_requested(&resolved.control)) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_CANCELLED, 0, 0, "verification cancelled at the end");
    return READER_ACCOUNT_PROFILES_CANCELLED;
  }
  return READER_ACCOUNT_PROFILES_OK;
}