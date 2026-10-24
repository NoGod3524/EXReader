/* SPDX-License-Identifier: MIT */
/* Installed-package consumer for EXReaderLinkPolicy. It links the static library
   from the install prefix, feeds the fixed fixture table to the public entry
   point and prints what the library returned. Expected values live in
   link_fixtures.py and are never derived from this probe. */
#include "reader_link_policy.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int failures;

static void verdict(const char *name, int ok) {
  if (!ok) failures++;
  printf("CHK\t%s\t%s\n", name, ok ? "ok" : "bad");
}

static const char *status_name(reader_link_status status) {
  switch (status) {
    case READER_LINK_OK: return "OK";
    case READER_LINK_ARGUMENT: return "ARGUMENT";
    case READER_LINK_MEMORY: return "MEMORY";
    case READER_LINK_CANCELLED: return "CANCELLED";
  }
  return "UNKNOWN";
}

static char *read_file(const char *path, size_t *size) {
  FILE *file = fopen(path, "rb");
  long length;
  char *data;
  if (!file) return NULL;
  if (fseek(file, 0, SEEK_END) != 0) { fclose(file); return NULL; }
  length = ftell(file);
  if (length < 0 || fseek(file, 0, SEEK_SET) != 0) { fclose(file); return NULL; }
  data = (char *)malloc((size_t)length + 1);
  if (!data) { fclose(file); return NULL; }
  if (length && fread(data, 1, (size_t)length, file) != (size_t)length) {
    free(data);
    fclose(file);
    return NULL;
  }
  fclose(file);
  data[length] = 0;
  *size = (size_t)length;
  return data;
}

static int hex_digit(int c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

/* "hex" is an even-length hex string or "." for empty. */
static unsigned char *parse_hex(const char *hex, size_t *size) {
  size_t length, i;
  unsigned char *bytes;
  if (!strcmp(hex, ".")) { *size = 0; return (unsigned char *)malloc(1); }
  length = strlen(hex);
  if (length % 2) return NULL;
  bytes = (unsigned char *)malloc(length / 2 + 1);
  if (!bytes) return NULL;
  for (i = 0; i < length; i += 2) {
    int hi = hex_digit((unsigned char)hex[i]);
    int lo = hex_digit((unsigned char)hex[i + 1]);
    if (hi < 0 || lo < 0) { free(bytes); return NULL; }
    bytes[i / 2] = (unsigned char)(hi * 16 + lo);
  }
  *size = length / 2;
  return bytes;
}

static void print_hex(const char *data, size_t size) {
  size_t i;
  if (!data) { printf("-"); return; }
  for (i = 0; i < size; i++) printf("%02x", (unsigned char)data[i]);
}

static size_t split_fields(char *line, char **fields, size_t limit) {
  size_t count = 1;
  fields[0] = line;
  while (*line && count < limit) {
    if (*line == '\t') { *line = 0; fields[count++] = line + 1; }
    line++;
  }
  return count;
}

static reader_link_status create_default(reader_link_policy **out) {
  return reader_link_policy_create(NULL, out, NULL);
}

static reader_link_status create_with(unsigned max_input, const char *const *schemes,
                                      size_t count, reader_link_policy **out) {
  reader_link_policy_options options;
  memset(&options, 0, sizeof(options));
  options.struct_size = (uint32_t)sizeof(options);
  options.max_input_bytes = max_input;
  options.schemes = schemes;
  options.scheme_count = count;
  return reader_link_policy_create(&options, out, NULL);
}

/* The fixture stores the base path as hex, "." for the empty string and "-" for
   NULL, so the probe decodes it before calling the library. */
static char *decode_base(const char *field) {
  size_t base_size = 0;
  unsigned char *decoded;
  char *base;
  if (!strcmp(field, "-")) return NULL;
  decoded = parse_hex(field, &base_size);
  if (!decoded) return (char *)(uintptr_t)1;
  base = (char *)malloc(base_size + 1);
  if (base) {
    if (base_size) memcpy(base, decoded, base_size);
    base[base_size] = 0;
  }
  free(decoded);
  return base;
}

static int mode_classify(const char *path) {
  size_t size = 0, cases = 0;
  char *data = read_file(path, &size);
  char *line, *next;
  char *schemes[READER_LINK_MAX_SCHEMES];
  size_t scheme_count = 0;
  unsigned max_input = 0;
  reader_link_policy *policy = NULL;
  int created = 0;

  if (!data) { fprintf(stderr, "FATAL\tcannot read %s\n", path); return 2; }
  line = data;
  while (line && *line) {
    char *fields[12];
    size_t count;
    size_t line_length;
    next = strchr(line, '\n');
    if (next) *next++ = 0;
    line_length = strlen(line);
    if (line_length && line[line_length - 1] == '\r') line[line_length - 1] = 0;
    if (line[0] == '#') {
      if (!strncmp(line, "#schemes ", 9)) {
        char *item = line + 9;
        char *comma;
        do {
          comma = strchr(item, ',');
          if (comma) *comma = 0;
          if (scheme_count < READER_LINK_MAX_SCHEMES) schemes[scheme_count++] = item;
          item = comma ? comma + 1 : NULL;
        } while (item);
      } else if (!strncmp(line, "#max ", 5)) {
        max_input = (unsigned)strtoul(line + 5, NULL, 10);
      }
      line = next;
      continue;
    }
    if (!created) {
      if (create_with(max_input, (const char *const *)schemes, scheme_count, &policy) !=
          READER_LINK_OK) {
        fprintf(stderr, "FATAL\tpolicy create failed\n");
        free(data);
        return 2;
      }
      created = 1;
    }
    count = split_fields(line, fields, 12);
    if (count >= 10) {
      const char *name = fields[0];
      char *base = decode_base(fields[1]);
      size_t input_size = 0;
      unsigned char *bytes = parse_hex(fields[2], &input_size);
      reader_link_result result;
      reader_link_error error;
      reader_link_status status;
      unsigned limit = max_input ? max_input : READER_LINK_DEFAULT_INPUT_BYTES;

      if (base == (char *)(uintptr_t)1) {
        fprintf(stderr, "FATAL\tbad base hex in %s\n", name);
        free(data);
        return 2;
      }
      if (!bytes) {
        fprintf(stderr, "FATAL\tbad hex in %s\n", name);
        free(base);
        free(data);
        return 2;
      }
      memset(&result, 0, sizeof(result));
      result.struct_size = (uint32_t)sizeof(result);
      memset(&error, 0, sizeof(error));
      error.struct_size = (uint32_t)sizeof(error);
      status = reader_link_classify(policy, (const char *)bytes, input_size, base, NULL,
                                    &result, &error);
      printf("C\t%s\t%d\t%d\t%d\t%d\t%u\t%s\t%zu\t%zu\t%zu\t%zu\t%zu\t",
             name, (int)status, (int)result.action, (int)result.reason, (int)result.kind,
             (unsigned)result.flags, result.scheme[0] ? result.scheme : "-", result.path_len,
             result.fragment_offset, result.fragment_len, result.input_bytes, result.display_len);
      print_hex(result.display, result.display_len);
      printf("\t%d\t%d\n",
             result.display && result.display[result.display_len] == 0 ? 1 : 0,
             result.display ? (result.display != (char *)bytes) : 1);
      if (status == READER_LINK_OK && input_size <= limit) {
        if (!result.display || result.display_len != input_size ||
            memcmp(result.display, bytes, input_size) != 0) {
          fprintf(stderr, "FATAL\t%s display copy is not independent\n", name);
          failures++;
        }
      }
      if (status == READER_LINK_OK && input_size > limit &&
          (result.display || result.display_len)) {
        fprintf(stderr, "FATAL\t%s kept a display copy past the limit\n", name);
        failures++;
      }
      reader_link_result_free(&result);
      reader_link_result_free(&result);
      if (result.display || result.display_len) {
        fprintf(stderr, "FATAL\t%s free is not idempotent\n", name);
        failures++;
      }
      free(bytes);
      free(base);
      cases++;
    }
    line = next;
  }
  reader_link_policy_destroy(policy);
  free(data);
  printf("T\t%zu\n", cases);
  return failures ? 1 : 0;
}

static int mode_limits(void) {
  reader_link_policy *policy = NULL;
  reader_link_policy_options options;
  reader_link_error error;
  const char *nine[9];
  const char *duplicate[2];
  const char *one[1];
  char long_scheme[18];
  size_t i;
  reader_link_result result;
  reader_link_status status;

  for (i = 0; i < 9; i++) nine[i] = "tel";
  duplicate[0] = "TEL";
  duplicate[1] = "tel";
  memset(long_scheme, 'a', 17);
  long_scheme[17] = 0;

  status = create_default(&policy);
  verdict("limits-default-create", status == READER_LINK_OK && policy != NULL);
  printf("CHK\tlimits-default-status\t%s\n", status_name(status));
  reader_link_policy_destroy(policy);
  policy = NULL;

  status = create_with(READER_LINK_MAX_INPUT_BYTES, NULL, 0, &policy);
  printf("CHK\tlimits-max-ceiling\t%s\n", status_name(status));
  reader_link_policy_destroy(policy);
  policy = NULL;

  status = create_with(READER_LINK_MAX_INPUT_BYTES + 1, NULL, 0, &policy);
  printf("CHK\tlimits-max-over\t%s\t%d\n", status_name(status), policy == NULL ? 1 : 0);
  reader_link_policy_destroy(policy);
  policy = NULL;

  memset(&options, 0, sizeof(options));
  memset(&error, 0, sizeof(error));
  options.struct_size = (uint32_t)sizeof(options) - 1;
  error.struct_size = (uint32_t)sizeof(error);
  status = reader_link_policy_create(&options, &policy, &error);
  printf("CHK\tlimits-options-struct-size\t%s\t%d\n", status_name(status),
         error.status == READER_LINK_ARGUMENT ? 1 : 0);
  reader_link_policy_destroy(policy);
  policy = NULL;

  memset(&options, 0, sizeof(options));
  options.struct_size = (uint32_t)sizeof(options);
  options.scheme_count = 2;
  status = reader_link_policy_create(&options, &policy, NULL);
  printf("CHK\tlimits-schemes-null\t%s\n", status_name(status));
  reader_link_policy_destroy(policy);
  policy = NULL;

  status = create_with(0, nine, 9, &policy);
  printf("CHK\tlimits-schemes-too-many\t%s\n", status_name(status));
  reader_link_policy_destroy(policy);
  policy = NULL;

  one[0] = "javascript";
  status = create_with(0, one, 1, &policy);
  printf("CHK\tlimits-scheme-denied\t%s\n", status_name(status));
  reader_link_policy_destroy(policy);
  policy = NULL;
  one[0] = "MS-Anything";
  status = create_with(0, one, 1, &policy);
  printf("CHK\tlimits-scheme-ms\t%s\n", status_name(status));
  reader_link_policy_destroy(policy);
  policy = NULL;
  one[0] = "te l";
  status = create_with(0, one, 1, &policy);
  printf("CHK\tlimits-scheme-bad-syntax\t%s\n", status_name(status));
  reader_link_policy_destroy(policy);
  policy = NULL;
  one[0] = long_scheme;
  status = create_with(0, one, 1, &policy);
  printf("CHK\tlimits-scheme-too-long\t%s\n", status_name(status));
  reader_link_policy_destroy(policy);
  policy = NULL;
  one[0] = "";
  status = create_with(0, one, 1, &policy);
  printf("CHK\tlimits-scheme-empty\t%s\n", status_name(status));
  reader_link_policy_destroy(policy);
  policy = NULL;

  status = create_with(0, duplicate, 2, &policy);
  printf("CHK\tlimits-duplicate-scheme\t%s\n", status_name(status));
  if (policy) {
    memset(&result, 0, sizeof(result));
    result.struct_size = (uint32_t)sizeof(result);
    if (reader_link_classify(policy, "TeL:+1555", 9, NULL, NULL, &result, NULL) ==
            READER_LINK_OK &&
        result.action == READER_LINK_ACTION_NEEDS_HOST && !strcmp(result.scheme, "tel")) {
      printf("CHK\tlimits-scheme-normalised\ttel\n");
    } else {
      printf("CHK\tlimits-scheme-normalised\tbad\n");
      failures++;
    }
    reader_link_result_free(&result);
  } else {
    printf("CHK\tlimits-scheme-normalised\tbad\n");
    failures++;
  }
  reader_link_policy_destroy(policy);
  policy = NULL;

  printf("CHK\tlimits-null-out\t%s\n",
         status_name(reader_link_policy_create(NULL, NULL, NULL)));
  reader_link_policy_destroy(NULL);
  verdict("limits-destroy-null", 1);
  printf("CHK\tlimits-name-tables\t%s\n",
         !strcmp(reader_link_action_name(READER_LINK_ACTION_NEEDS_HOST), "NEEDS_HOST") &&
                 !strcmp(reader_link_reason_name(READER_LINK_REASON_PATH_ESCAPE), "PATH_ESCAPE") &&
                 !strcmp(reader_link_action_name((reader_link_action)99), "UNKNOWN") &&
                 !strcmp(reader_link_reason_name((reader_link_reason)99), "UNKNOWN")
             ? "ok" : "bad");
  if (strcmp(reader_link_reason_name((reader_link_reason)99), "UNKNOWN")) failures++;
  return failures ? 1 : 0;
}

static int mode_errors(void) {
  reader_link_policy *policy = NULL;
  reader_link_result result;
  char long_base[READER_LINK_INTERNAL_PART_LIMIT + 1];
  reader_link_status status;

  memset(long_base, 'a', sizeof(long_base) - 1);
  long_base[sizeof(long_base) - 1] = 0;
  if (create_default(&policy) != READER_LINK_OK) {
    fprintf(stderr, "FATAL\tpolicy create failed\n");
    return 2;
  }

  status = reader_link_classify(policy, "ch1.xhtml", 9, NULL, NULL, NULL, NULL);
  printf("CHK\terrors-null-result\t%s\n", status_name(status));

  memset(&result, 0, sizeof(result));
  status = reader_link_classify(policy, "ch1.xhtml", 9, NULL, NULL, &result, NULL);
  printf("CHK\terrors-result-struct-size\t%s\n", status_name(status));

  memset(&result, 0, sizeof(result));
  result.struct_size = (uint32_t)sizeof(result);
  status = reader_link_classify(NULL, "ch1.xhtml", 9, NULL, NULL, &result, NULL);
  printf("CHK\terrors-null-policy\t%s\t%d\n", status_name(status),
         status == READER_LINK_ARGUMENT && result.action == READER_LINK_ACTION_REJECT &&
                 !result.display && !result.display_len && !result.input_bytes
             ? 1 : 0);
  if (!(status == READER_LINK_ARGUMENT && !result.display)) failures++;

  memset(&result, 0, sizeof(result));
  result.struct_size = (uint32_t)sizeof(result);
  status = reader_link_classify(policy, NULL, 5, NULL, NULL, &result, NULL);
  printf("CHK\terrors-null-text\t%s\n", status_name(status));

  memset(&result, 0, sizeof(result));
  result.struct_size = (uint32_t)sizeof(result);
  status = reader_link_classify(policy, "ch1.xhtml", 9, "/OEBPS/ch1.xhtml", NULL, &result, NULL);
  printf("CHK\terrors-base-absolute\t%s\n", status_name(status));

  memset(&result, 0, sizeof(result));
  result.struct_size = (uint32_t)sizeof(result);
  status = reader_link_classify(policy, "ch1.xhtml", 9, "OEBPS\\ch1.xhtml", NULL, &result, NULL);
  printf("CHK\terrors-base-backslash\t%s\n", status_name(status));

  memset(&result, 0, sizeof(result));
  result.struct_size = (uint32_t)sizeof(result);
  status = reader_link_classify(policy, "ch1.xhtml", 9, long_base, NULL, &result, NULL);
  printf("CHK\terrors-base-too-long\t%s\n", status_name(status));

  memset(&result, 0, sizeof(result));
  result.struct_size = (uint32_t)sizeof(result);
  status = reader_link_classify(policy, "#frag", 5, NULL, NULL, &result, NULL);
  printf("CHK\terrors-optional-pointers\t%s\t%d\n", status_name(status),
         result.action == READER_LINK_ACTION_INTERNAL &&
                 result.kind == READER_LINK_KIND_FRAGMENT ? 1 : 0);
  reader_link_result_free(&result);

  memset(&result, 0, sizeof(result));
  result.struct_size = (uint32_t)sizeof(result);
  status = reader_link_classify(policy, "javascript:alert(1)", strlen("javascript:alert(1)"),
                                NULL, NULL, &result, NULL);
  printf("CHK\terrors-reject-action\t%s\n",
         status == READER_LINK_OK && result.action == READER_LINK_ACTION_REJECT &&
                 result.reason == READER_LINK_REASON_FORBIDDEN_SCHEME ? "REJECT" : "bad");
  if (result.action != READER_LINK_ACTION_REJECT) failures++;
  reader_link_result_free(&result);

  memset(&result, 0, sizeof(result));
  result.struct_size = (uint32_t)sizeof(result);
  status = reader_link_classify(policy, "", 0, NULL, NULL, &result, NULL);
  printf("CHK\terrors-empty-reason\t%s\n",
         result.reason == READER_LINK_REASON_EMPTY ? reader_link_reason_name(result.reason)
                                                   : "bad");
  if (result.reason != READER_LINK_REASON_EMPTY) failures++;
  reader_link_result_free(&result);

  reader_link_policy_destroy(policy);
  return failures ? 1 : 0;
}

static int mode_lifetime(void) {
  reader_link_policy *policy = NULL;
  reader_link_result first, second;
  char *input = (char *)malloc(32);
  char expected[] = "https://example.com/a";
  size_t length = strlen(expected);

  if (!input || create_default(&policy) != READER_LINK_OK) {
    fprintf(stderr, "FATAL\tsetup failed\n");
    free(input);
    return 2;
  }
  memcpy(input, expected, length + 1);
  memset(&first, 0, sizeof(first));
  first.struct_size = (uint32_t)sizeof(first);
  if (reader_link_classify(policy, input, length, NULL, NULL, &first, NULL) != READER_LINK_OK) {
    fprintf(stderr, "FATAL\tclassify failed\n");
    return 2;
  }
  verdict("lifetime-no-alias", first.display && first.display != input);
  reader_link_policy_destroy(policy);
  policy = NULL;
  memset(input, 0xFF, length);
  verdict("lifetime-survives-policy-and-input",
          first.display && !memcmp(first.display, expected, length) &&
                  first.display[length] == 0 && first.display_len == length &&
                  first.struct_size == sizeof(first));

  memset(&second, 0, sizeof(second));
  second.struct_size = (uint32_t)sizeof(second);
  if (create_default(&policy) != READER_LINK_OK) {
    free(input);
    return 2;
  }
  reader_link_classify(policy, "#note", 5, NULL, NULL, &second, NULL);
  verdict("lifetime-independent-results",
          first.display && second.display && strcmp(first.display, second.display) != 0);
  reader_link_result_free(&first);
  verdict("lifetime-free-clears", !first.display && !first.display_len);
  reader_link_result_free(&first);
  verdict("lifetime-double-free", !first.display);
  reader_link_result_free(&second);
  reader_link_policy_destroy(policy);
  free(input);
  return failures ? 1 : 0;
}

static int mode_interleave(void) {
  reader_link_policy *strict = NULL, *open = NULL;
  reader_link_result result;
  const char *schemes[1];
  unsigned i;
  int stable = 1;

  if (create_default(&strict) != READER_LINK_OK) return 2;
  schemes[0] = "tel";
  if (create_with(0, schemes, 1, &open) != READER_LINK_OK) return 2;

  for (i = 0; i < 100; i++) {
    memset(&result, 0, sizeof(result));
    result.struct_size = (uint32_t)sizeof(result);
    if (reader_link_classify(open, "tel:+15551234", 13, NULL, NULL, &result, NULL) !=
            READER_LINK_OK ||
        result.action != READER_LINK_ACTION_NEEDS_HOST)
      stable = 0;
    reader_link_result_free(&result);
    memset(&result, 0, sizeof(result));
    result.struct_size = (uint32_t)sizeof(result);
    if (reader_link_classify(strict, "tel:+15551234", 13, NULL, NULL, &result, NULL) !=
            READER_LINK_OK ||
        result.action != READER_LINK_ACTION_REJECT ||
        result.reason != READER_LINK_REASON_UNKNOWN_SCHEME)
      stable = 0;
    reader_link_result_free(&result);
  }
  verdict("interleave-policies-independent", stable);
  reader_link_policy_destroy(open);
  memset(&result, 0, sizeof(result));
  result.struct_size = (uint32_t)sizeof(result);
  verdict("interleave-survives-other-destroy",
          reader_link_classify(strict, "ch2.xhtml", 9, "OEBPS/text/ch1.xhtml", NULL, &result,
                               NULL) == READER_LINK_OK &&
                  result.action == READER_LINK_ACTION_INTERNAL);
  reader_link_result_free(&result);
  reader_link_policy_destroy(strict);
  return failures ? 1 : 0;
}

int main(int argc, char **argv) {
  if (argc < 2) {
    fprintf(stderr, "usage: link-probe classify|limits|errors|lifetime|interleave [path]\n");
    return 2;
  }
  if (!strcmp(argv[1], "classify")) {
    if (argc != 3) { fprintf(stderr, "classify needs a fixture path\n"); return 2; }
    if (mode_classify(argv[2]) != 0) return 1;
  } else if (!strcmp(argv[1], "limits")) {
    if (mode_limits() != 0) return 1;
  } else if (!strcmp(argv[1], "errors")) {
    if (mode_errors() != 0) return 1;
  } else if (!strcmp(argv[1], "lifetime")) {
    if (mode_lifetime() != 0) return 1;
  } else if (!strcmp(argv[1], "interleave")) {
    if (mode_interleave() != 0) return 1;
  } else {
    fprintf(stderr, "unknown mode %s\n", argv[1]);
    return 2;
  }
  printf("link-probe-ok\n");
  return 0;
}
