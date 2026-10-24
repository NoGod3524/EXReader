/* SPDX-License-Identifier: MIT */
#include "internal.h"

#include <stdio.h>
#include <string.h>

#define AP_HEADER_FORMAT "  \"format\": \"reader-account-profiles\",\n"

typedef struct {
  const unsigned char *data;
  size_t size;
  size_t position;
} ap_cursor;

static int ap_literal(ap_cursor *cursor, const char *text) {
  size_t length = strlen(text);
  if (cursor->position + length > cursor->size) return 0;
  if (memcmp(cursor->data + cursor->position, text, length) != 0) return 0;
  cursor->position += length;
  return 1;
}

static int ap_uint64(ap_cursor *cursor, uint64_t *value) {
  size_t index = cursor->position;
  uint64_t total = 0;
  if (index >= cursor->size) return 0;
  if (cursor->data[index] == '0') {
    index += 1u;
    if (index < cursor->size && cursor->data[index] >= '0' && cursor->data[index] <= '9') return 0;
  } else if (cursor->data[index] >= '1' && cursor->data[index] <= '9') {
    while (index < cursor->size && cursor->data[index] >= '0' && cursor->data[index] <= '9') {
      uint64_t digit = (uint64_t)(cursor->data[index] - '0');
      if (total > (UINT64_MAX - digit) / 10u) return 0;
      total = total * 10u + digit;
      index += 1u;
    }
  } else {
    return 0;
  }
  cursor->position = index;
  *value = total;
  return 1;
}

static int ap_string(ap_cursor *cursor, char *out, size_t capacity) {
  size_t used = 0;
  if (cursor->position >= cursor->size || cursor->data[cursor->position] != '"') return 0;
  cursor->position += 1u;
  for (;;) {
    unsigned char byte;
    if (cursor->position >= cursor->size) return 0;
    byte = cursor->data[cursor->position];
    if (byte == '"') {
      cursor->position += 1u;
      break;
    }
    if (byte == '\\') {
      unsigned char escaped;
      cursor->position += 1u;
      if (cursor->position >= cursor->size) return 0;
      escaped = cursor->data[cursor->position];
      if (escaped != '"' && escaped != '\\') return 0;
      byte = escaped;
      cursor->position += 1u;
    } else {
      if (byte < 0x20u) return 0;
      cursor->position += 1u;
    }
    if (used + 1u >= capacity) return 0;
    out[used++] = (char)byte;
  }
  out[used] = '\0';
  return 1;
}

static int ap_write_string(char *buffer, size_t capacity, size_t *used, const char *value) {
  size_t index;
  if (*used + 1u >= capacity) return 0;
  buffer[(*used)++] = '"';
  for (index = 0; value[index] != '\0'; ++index) {
    char byte = value[index];
    if (byte == '"' || byte == '\\') {
      if (*used + 2u >= capacity) return 0;
      buffer[(*used)++] = '\\';
      buffer[(*used)++] = byte;
    } else {
      if (*used + 1u >= capacity) return 0;
      buffer[(*used)++] = byte;
    }
  }
  if (*used + 1u >= capacity) return 0;
  buffer[(*used)++] = '"';
  return 1;
}

static int ap_write_text(char *buffer, size_t capacity, size_t *used, const char *text) {
  size_t length = strlen(text);
  if (*used + length >= capacity) return 0;
  memcpy(buffer + *used, text, length);
  *used += length;
  return 1;
}

reader_account_profiles_status ap_document_decode(const unsigned char *data, size_t size,
                                                  ap_document *out,
                                                  reader_account_profiles_error *error) {
  ap_cursor cursor;
  uint64_t version = 0;
  uint64_t generation = 0;
  uint32_t count = 0;
  uint32_t index;
  size_t item_offsets[READER_ACCOUNT_PROFILES_MAX_PROFILES];
  size_t field_offsets[READER_ACCOUNT_PROFILES_MAX_PROFILES][4];
  size_t version_offset;

  memset(out, 0, sizeof(*out));
  cursor.data = data;
  cursor.size = size;
  cursor.position = 0;
  if (size == 0) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_FORMAT, 0, 0, "the document is empty");
    return READER_ACCOUNT_PROFILES_FORMAT;
  }
  if (!ap_literal(&cursor, "{\n")) goto format;
  if (!ap_literal(&cursor, AP_HEADER_FORMAT)) goto format;
  if (!ap_literal(&cursor, "  \"version\": ")) goto format;
  version_offset = cursor.position;
  if (!ap_uint64(&cursor, &version)) goto format;
  if (version != (uint64_t)READER_ACCOUNT_PROFILES_FORMAT_VERSION) {
    ap_error_set(error, READER_ACCOUNT_PROFILES_VERSION, 0, version_offset,
                 "document version is not %u", (unsigned)READER_ACCOUNT_PROFILES_FORMAT_VERSION);
    return READER_ACCOUNT_PROFILES_VERSION;
  }
  if (!ap_literal(&cursor, ",\n  \"generation\": ")) goto format;
  if (!ap_uint64(&cursor, &generation)) goto format;
  if (!ap_literal(&cursor, ",\n  \"profiles\": ")) goto format;
  if (ap_literal(&cursor, "[]\n}\n")) {
    if (cursor.position != cursor.size) goto format;
    out->generation = generation;
    out->count = 0;
    return READER_ACCOUNT_PROFILES_OK;
  }
  if (!ap_literal(&cursor, "[\n")) goto format;
  for (;;) {
    if (count >= READER_ACCOUNT_PROFILES_MAX_PROFILES) {
      ap_error_set(error, READER_ACCOUNT_PROFILES_LIMIT, 0, cursor.position,
                   "the document holds more than %u profiles",
                   (unsigned)READER_ACCOUNT_PROFILES_MAX_PROFILES);
      return READER_ACCOUNT_PROFILES_LIMIT;
    }
    item_offsets[count] = cursor.position;
    if (!ap_literal(&cursor, "    {\n      \"profile_id\": ")) goto format;
    field_offsets[count][0] = cursor.position;
    if (!ap_string(&cursor, out->items[count].profile_id,
                   sizeof(out->items[count].profile_id))) goto format;
    if (!ap_literal(&cursor, ",\n      \"account_id\": ")) goto format;
    field_offsets[count][1] = cursor.position;
    if (!ap_string(&cursor, out->items[count].account_id,
                   sizeof(out->items[count].account_id))) goto format;
    if (!ap_literal(&cursor, ",\n      \"root_url\": ")) goto format;
    field_offsets[count][2] = cursor.position;
    if (!ap_string(&cursor, out->items[count].root_url,
                   sizeof(out->items[count].root_url))) goto format;
    if (!ap_literal(&cursor, ",\n      \"display_name\": ")) goto format;
    field_offsets[count][3] = cursor.position;
    if (!ap_string(&cursor, out->items[count].display_name,
                   sizeof(out->items[count].display_name))) goto format;
    if (!ap_literal(&cursor, "\n    }")) goto format;
    out->items[count].struct_size = (uint32_t)sizeof(reader_account_profile);
    count += 1u;
    if (ap_literal(&cursor, ",\n")) continue;
    if (ap_literal(&cursor, "\n  ]\n}\n")) break;
    goto format;
  }
  if (cursor.position != cursor.size) goto format;
  out->generation = generation;
  out->count = count;
  for (index = 0; index < count; ++index) {
    reader_account_profiles_status status;
    status = ap_validate_uuid_field(out->items[index].profile_id, field_offsets[index][0], error);
    if (status != READER_ACCOUNT_PROFILES_OK) return status;
    status = ap_validate_uuid_field(out->items[index].account_id, field_offsets[index][1], error);
    if (status != READER_ACCOUNT_PROFILES_OK) return status;
    status = ap_validate_url_field(out->items[index].root_url, field_offsets[index][2], error);
    if (status != READER_ACCOUNT_PROFILES_OK) return status;
    status = ap_validate_name_field(out->items[index].display_name, field_offsets[index][3], error);
    if (status != READER_ACCOUNT_PROFILES_OK) return status;
    {
      uint32_t previous;
      for (previous = 0; previous < index; ++previous) {
        if (strcmp(out->items[previous].profile_id, out->items[index].profile_id) == 0) {
          ap_error_set(error, READER_ACCOUNT_PROFILES_FORMAT, 0, item_offsets[index],
                       "the document repeats a profile id");
          return READER_ACCOUNT_PROFILES_FORMAT;
        }
        if (strcmp(out->items[previous].account_id, out->items[index].account_id) == 0 &&
            strcmp(out->items[previous].root_url, out->items[index].root_url) == 0) {
          ap_error_set(error, READER_ACCOUNT_PROFILES_FORMAT, 0, item_offsets[index],
                       "the document repeats an account and root URL pair");
          return READER_ACCOUNT_PROFILES_FORMAT;
        }
      }
    }
  }
  return READER_ACCOUNT_PROFILES_OK;

format:
  ap_error_set(error, READER_ACCOUNT_PROFILES_FORMAT, 0, cursor.position,
               "the document is not the canonical shape");
  return READER_ACCOUNT_PROFILES_FORMAT;
}

reader_account_profiles_status ap_document_encode(const ap_document *document, char *buffer,
                                                  size_t capacity, size_t *used,
                                                  reader_account_profiles_error *error) {
  size_t position = 0;
  uint32_t index;
  char number[32];
  if (!ap_write_text(buffer, capacity, &position, "{\n")) goto small;
  if (!ap_write_text(buffer, capacity, &position, AP_HEADER_FORMAT)) goto small;
  if (!ap_write_text(buffer, capacity, &position, "  \"version\": 1,\n")) goto small;
  if (!ap_write_text(buffer, capacity, &position, "  \"generation\": ")) goto small;
  (void)snprintf(number, sizeof(number), "%llu", (unsigned long long)document->generation);
  if (!ap_write_text(buffer, capacity, &position, number)) goto small;
  if (!ap_write_text(buffer, capacity, &position, ",\n  \"profiles\": ")) goto small;
  if (document->count == 0) {
    if (!ap_write_text(buffer, capacity, &position, "[]\n}\n")) goto small;
    *used = position;
    return READER_ACCOUNT_PROFILES_OK;
  }
  if (!ap_write_text(buffer, capacity, &position, "[\n")) goto small;
  for (index = 0; index < document->count; ++index) {
    const reader_account_profile *item = &document->items[index];
    if (!ap_write_text(buffer, capacity, &position, "    {\n      \"profile_id\": ")) goto small;
    if (!ap_write_string(buffer, capacity, &position, item->profile_id)) goto small;
    if (!ap_write_text(buffer, capacity, &position, ",\n      \"account_id\": ")) goto small;
    if (!ap_write_string(buffer, capacity, &position, item->account_id)) goto small;
    if (!ap_write_text(buffer, capacity, &position, ",\n      \"root_url\": ")) goto small;
    if (!ap_write_string(buffer, capacity, &position, item->root_url)) goto small;
    if (!ap_write_text(buffer, capacity, &position, ",\n      \"display_name\": ")) goto small;
    if (!ap_write_string(buffer, capacity, &position, item->display_name)) goto small;
    if (!ap_write_text(buffer, capacity, &position, "\n    }")) goto small;
    if (index + 1u < document->count) {
      if (!ap_write_text(buffer, capacity, &position, ",\n")) goto small;
    }
  }
  if (!ap_write_text(buffer, capacity, &position, "\n  ]\n}\n")) goto small;
  *used = position;
  return READER_ACCOUNT_PROFILES_OK;

small:
  ap_error_set(error, READER_ACCOUNT_PROFILES_LIMIT, 0, position,
               "the encoded document exceeds the file limit");
  return READER_ACCOUNT_PROFILES_LIMIT;
}
