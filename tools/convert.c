/* SPDX-License-Identifier: MIT */
#if !defined(_WIN32) && !defined(_POSIX_C_SOURCE)
#define _POSIX_C_SOURCE 200809L
#endif
/* exreader-convert: small, installable single-file/batch conversion driver.
   All decoding, conversion and structure-preserving export happens through the
   EXReader SDK; this file only owns arguments, file protection and reporting. */
#include "convert_io.h"
#include "convert_json.h"
#include "convert_report.h"
#include "exreader.h"
#include <miniz.h>
#include <ctype.h>
#include <errno.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#endif

#define CV_SIZE_LIMIT ((uint64_t)512u * 1024u * 1024u)
#define CV_MANIFEST_LIMIT ((size_t)16u * 1024u * 1024u)
#define CV_ITEMS_LIMIT 100000u

static volatile sig_atomic_t g_cancelled;
static int cancelled_callback(void *context) {
  (void)context;
  return g_cancelled != 0;
}
#ifdef _WIN32
static BOOL WINAPI console_handler(DWORD type) {
  if (type == CTRL_C_EVENT || type == CTRL_BREAK_EVENT || type == CTRL_CLOSE_EVENT) {
    g_cancelled = 1;
    return TRUE;
  }
  return FALSE;
}
static void install_cancel_handlers(void) { SetConsoleCtrlHandler(console_handler, TRUE); }
#else
static void signal_handler(int signal_number) {
  (void)signal_number;
  g_cancelled = 1;
}
static void install_cancel_handlers(void) {
  struct sigaction action;
  memset(&action, 0, sizeof(action));
  action.sa_handler = signal_handler;
  sigemptyset(&action.sa_mask);
  sigaction(SIGINT, &action, NULL);
  sigaction(SIGTERM, &action, NULL);
}
#endif

typedef struct {
  const char *name;
  exr_format format;
  const char *variant;
  int text_input, text_output, preserve_input, preserve_output;
} cv_format;
static const cv_format cv_formats[] = {
    {"txt", EXR_TXT, "none", 1, 1, 0, 0},
    {"html", EXR_HTML, "none", 1, 1, 1, 1},
    {"fb2", EXR_FB2, "none", 1, 1, 0, 0},
    {"epub", EXR_EPUB, "none", 1, 1, 1, 1},
    {"docx", EXR_DOCX, "none", 1, 1, 0, 0},
    {"rtf", EXR_RTF, "none", 1, 1, 0, 0},
    {"mobi", EXR_MOBI, "mobi", 1, 0, 0, 0},
    {"kf8", EXR_MOBI, "kf8", 1, 0, 0, 0},
    {"pdf", EXR_PDF, "none", 0, 0, 0, 0},
    {"cbz", EXR_CBZ, "none", 0, 0, 0, 0},
    {NULL, EXR_CUSTOM, NULL, 0, 0, 0, 0}};
static int equal_ci(const char *a, const char *b) {
  while (*a && *b) {
    if (tolower((unsigned char)*a) != tolower((unsigned char)*b)) return 0;
    a++; b++;
  }
  return *a == 0 && *b == 0;
}
static const cv_format *parse_format(const char *name) {
  size_t i;
  if (!name) return NULL;
  if (equal_ci(name, "text")) name = "txt";
  if (equal_ci(name, "xhtml") || equal_ci(name, "htm")) name = "html";
  if (equal_ci(name, "azw3") || equal_ci(name, "azw")) name = "kf8";
  if (equal_ci(name, "prc")) name = "mobi";
  if (equal_ci(name, "audio")) return NULL;
  for (i = 0; cv_formats[i].name; i++)
    if (equal_ci(name, cv_formats[i].name)) return &cv_formats[i];
  return NULL;
}
static const cv_format *format_from_extension(const char *path) {
  const char *ext = cv_extension(path);
  char lower[16];
  size_t i;
  for (i = 0; ext[i] && i + 1 < sizeof(lower); i++) lower[i] = (char)tolower((unsigned char)ext[i]);
  lower[i] = 0;
  if (!strcmp(lower, "azw3")) return parse_format("kf8");
  if (!strcmp(lower, "mobi") || !strcmp(lower, "prc") || !strcmp(lower, "azw"))
    return parse_format("mobi");
  return parse_format(lower);
}
static const char *output_extension(const cv_format *format, cv_profile profile) {
  if (profile == CV_PROFILE_PRESERVE && format->format == EXR_HTML) return "zip";
  return format->name;
}
static unsigned be16(const unsigned char *p) { return ((unsigned)p[0] << 8) | p[1]; }
static unsigned be32(const unsigned char *p) {
  return ((unsigned)p[0] << 24) | ((unsigned)p[1] << 16) | ((unsigned)p[2] << 8) | p[3];
}
/* Mirrors the loader's MOBI/KF8 split without trusting an extension. A legacy
   header (<8) with an EXTH boundary and a version-8 KF8 header is hybrid KF8. */
static const char *mobi_variant_bytes(const unsigned char *data, size_t size) {
  size_t count, first, end, offset, header, length, items, at, i;
  unsigned version;
  if (size < 94 || memcmp(data + 60, "BOOKMOBI", 8)) return "unknown";
  count = be16(data + 76);
  if (count < 2 || count > (size - 78) / 8) return "unknown";
  first = be32(data + 78);
  end = count > 1 ? be32(data + 86) : (unsigned)size;
  if (first < 78 + count * 8 || first > end || end > size || end - first < 132) return "unknown";
  if (memcmp(data + first + 16, "MOBI", 4)) return "unknown";
  version = be32(data + first + 36);
  if (version == 8) return "kf8";
  if (version > 8) return "unknown";
  header = be32(data + first + 20);
  if (header < 116 || header > end - first - 16) return "unknown";
  offset = first + 16 + header;
  if (!(be32(data + first + 128) & 64)) return "mobi";
  if (offset + 12 > end || memcmp(data + offset, "EXTH", 4)) return "mobi";
  length = be32(data + offset + 4);
  items = be32(data + offset + 8);
  if (length < 12 || length > end - offset || items > (length - 12) / 8) return "mobi";
  at = 12;
  for (i = 0; i < items; i++) {
    unsigned type, item;
    if (length - at < 8) break;
    type = be32(data + offset + at);
    item = be32(data + offset + at + 4);
    if (item < 8 || item > length - at) break;
    if (type == 121 && item == 12) {
      size_t boundary = be32(data + offset + at + 8);
      if (boundary < count) {
        size_t start = be32(data + 78 + boundary * 8);
        size_t stop = boundary + 1 < count ? be32(data + 78 + (boundary + 1) * 8) : size;
        if (start < stop && stop <= size && stop - start >= 132 &&
            !memcmp(data + start + 16, "MOBI", 4) &&
            be32(data + start + 36) == 8)
          return "kf8";
      }
      break;
    }
    at += item;
  }
  return "mobi";
}

/* ---------- text comparison ---------- */
static int utf8_decode(const unsigned char *p, size_t n, size_t *used, unsigned *cp) {
  if (!n) return 0;
  if (p[0] < 0x80) { *cp = p[0]; *used = 1; return 1; }
  if ((p[0] & 0xe0) == 0xc0 && n >= 2 && (p[1] & 0xc0) == 0x80) {
    *cp = ((unsigned)(p[0] & 0x1f) << 6) | (p[1] & 0x3f);
    *used = 2; return *cp >= 0x80;
  }
  if ((p[0] & 0xf0) == 0xe0 && n >= 3 && (p[1] & 0xc0) == 0x80 && (p[2] & 0xc0) == 0x80) {
    *cp = ((unsigned)(p[0] & 0xf) << 12) | ((unsigned)(p[1] & 0x3f) << 6) | (p[2] & 0x3f);
    *used = 3; return *cp >= 0x800 && (*cp < 0xd800 || *cp > 0xdfff);
  }
  if ((p[0] & 0xf8) == 0xf0 && n >= 4 && (p[1] & 0xc0) == 0x80 &&
      (p[2] & 0xc0) == 0x80 && (p[3] & 0xc0) == 0x80) {
    *cp = ((unsigned)(p[0] & 7) << 18) | ((unsigned)(p[1] & 0x3f) << 12) |
          ((unsigned)(p[2] & 0x3f) << 6) | (p[3] & 0x3f);
    *used = 4; return *cp >= 0x10000 && *cp <= 0x10ffff;
  }
  return 0;
}
static void append_scalar(cv_text *out, unsigned cp) {
  char bytes[4];
  size_t n;
  if (cp < 0x80) { bytes[0] = (char)cp; n = 1; }
  else if (cp < 0x800) {
    bytes[0] = (char)(0xc0 | (cp >> 6)); bytes[1] = (char)(0x80 | (cp & 63)); n = 2;
  } else if (cp < 0x10000) {
    bytes[0] = (char)(0xe0 | (cp >> 12)); bytes[1] = (char)(0x80 | ((cp >> 6) & 63));
    bytes[2] = (char)(0x80 | (cp & 63)); n = 3;
  } else {
    bytes[0] = (char)(0xf0 | (cp >> 18)); bytes[1] = (char)(0x80 | ((cp >> 12) & 63));
    bytes[2] = (char)(0x80 | ((cp >> 6) & 63)); bytes[3] = (char)(0x80 | (cp & 63)); n = 4;
  }
  cv_text_append(out, bytes, n);
}
static int normalize_text(const char *text, size_t size, cv_text *out, char **error) {
  size_t at = 0;
  int pending_space = 0, any = 0;
  while (at < size) {
    unsigned cp; size_t used;
    if (!utf8_decode((const unsigned char *)text + at, size - at, &used, &cp)) {
      if (error && !*error) *error = strdup("Document text is not valid UTF-8");
      return 0;
    }
    at += used;
    if (cp == ' ' || cp == '\t' || cp == '\n' || cp == '\r' || cp == '\f' || cp == '\v') {
      if (any) pending_space = 1;
      continue;
    }
    if (pending_space) { cv_text_append(out, " ", 1); pending_space = 0; }
    append_scalar(out, cp);
    any = 1;
  }
  return 1;
}
static int text_equal_normalized(const exr_document *a, const exr_document *b, char **error) {
  size_t an = 0, bn = 0;
  const char *at = exr_document_text(a, &an), *bt = exr_document_text(b, &bn);
  cv_text na, nb;
  int same;
  cv_text_init(&na); cv_text_init(&nb);
  if (!normalize_text(at ? at : "", an, &na, error) ||
      !normalize_text(bt ? bt : "", bn, &nb, error)) {
    cv_text_free(&na); cv_text_free(&nb); return 0;
  }
  same = na.size == nb.size && !memcmp(na.data ? na.data : "", nb.data ? nb.data : "", na.size);
  cv_text_free(&na); cv_text_free(&nb);
  return same;
}
static char *duplicate_string(const char *s) {
  size_t n;
  char *out;
  if (!s) return NULL;
  n = strlen(s);
  out = malloc(n + 1);
  if (out) memcpy(out, s, n + 1);
  return out;
}
static void set_message(char **target, const char *format, ...) {
  va_list args, copy;
  int n;
  free(*target);
  *target = NULL;
  va_start(args, format);
  va_copy(copy, args);
  n = vsnprintf(NULL, 0, format, copy);
  va_end(copy);
  if (n >= 0) {
    *target = malloc((size_t)n + 1);
    if (*target) vsnprintf(*target, (size_t)n + 1, format, args);
  }
  va_end(args);
}
static void take_error(char **target, char **error, const char *fallback) {
  if (*error) { *target = *error; *error = NULL; }
  else if (fallback) *target = duplicate_string(fallback);
}
static void set_cancelled_error(cv_result *r) {
  free(r->error_message);
  r->error_message = duplicate_string("cancelled");
  r->error_code = EXR_CANCELLED;
  r->stage = "convert";
  r->status = "cancelled";
}

/* ---------- manifest ---------- */
typedef struct {
  char *id, *input, *output, *from, *to;
  int profile_set, overwrite_set;
  cv_profile profile;
  int overwrite;
} cv_item_spec;
typedef struct {
  char *root, *output_root;
  int profile_set, overwrite;
  cv_profile profile;
  cv_item_spec *items;
  size_t count;
} cv_manifest;
static void manifest_free(cv_manifest *m) {
  size_t i;
  free(m->root); free(m->output_root);
  for (i = 0; i < m->count; i++) {
    free(m->items[i].id); free(m->items[i].input); free(m->items[i].output);
    free(m->items[i].from); free(m->items[i].to);
  }
  free(m->items);
  memset(m, 0, sizeof(*m));
}
static int profile_parse(const char *s, cv_profile *profile) {
  if (equal_ci(s, "text")) { *profile = CV_PROFILE_TEXT; return 1; }
  if (equal_ci(s, "preserve")) { *profile = CV_PROFILE_PRESERVE; return 1; }
  return 0;
}
static const char *string_field(const cv_json *object, const char *key, char **error) {
  const cv_json *v = cv_json_get(object, key);
  if (!v) return NULL;
  if (v->type != CV_JSON_STRING) {
    set_message(error, "Manifest field '%s' must be a string", key);
    return NULL;
  }
  return v->string;
}
static int bool_field(const cv_json *object, const char *key, int *value, char **error) {
  const cv_json *v = cv_json_get(object, key);
  if (!v) return 1;
  if (v->type != CV_JSON_BOOL) {
    set_message(error, "Manifest field '%s' must be a boolean", key);
    return 0;
  }
  *value = v->boolean;
  return 1;
}
static int reject_unknown(const cv_json *object, const char *where, const char *const *allowed,
                          size_t allowed_count, char **error) {
  size_t i, j;
  for (i = 0; i < object->count; i++) {
    for (j = 0; j < allowed_count; j++) if (!strcmp(object->keys[i], allowed[j])) break;
    if (j == allowed_count) {
      set_message(error, "Unknown %s field '%s'", where, object->keys[i]);
      return 0;
    }
  }
  return 1;
}
static int parse_manifest(const char *path, cv_manifest *m, char **error) {
  static const char *top_allowed[] = {"schema", "profile", "overwrite", "root", "output_root", "items"};
  static const char *item_allowed[] = {"id", "input", "to", "output", "profile", "format", "overwrite"};
  unsigned char *bytes = NULL;
  size_t size = 0;
  char *read_error = NULL;
  cv_json *root = NULL;
  const cv_json *schema, *items, *v;
  uint64_t file_size = 0;
  size_t i;
  memset(m, 0, sizeof(*m));
  if (!cv_file_size(path, &file_size, &read_error)) {
    set_message(error, "Cannot read manifest: %s", read_error ? read_error : "I/O error");
    free(read_error);
    return 0;
  }
  if (file_size > CV_MANIFEST_LIMIT) {
    set_message(error, "Manifest exceeds 16 MiB");
    return 0;
  }
  if (!cv_read_file(path, &bytes, &size, &read_error)) {
    set_message(error, "Cannot read manifest: %s", read_error ? read_error : "I/O error");
    free(read_error);
    return 0;
  }
  if (size > CV_MANIFEST_LIMIT) {
    free(bytes); set_message(error, "Manifest exceeds 16 MiB"); return 0;
  }
  root = cv_json_parse((const char *)bytes, size, error);
  free(bytes);
  if (!root) return 0;
  if (root->type != CV_JSON_OBJECT) { set_message(error, "Manifest root must be an object"); goto failed; }
  if (!reject_unknown(root, "manifest", top_allowed, sizeof(top_allowed) / sizeof(top_allowed[0]), error)) goto failed;
  schema = cv_json_get(root, "schema");
  if (!schema || schema->type != CV_JSON_NUMBER || !schema->integral || schema->integer != 1) {
    set_message(error, "Manifest schema must be the integer 1"); goto failed;
  }
  v = cv_json_get(root, "profile");
  if (v && !(v->type == CV_JSON_STRING && profile_parse(v->string, &m->profile))) {
    set_message(error, "Manifest profile must be text or preserve"); goto failed;
  }
  m->profile_set = v != NULL;
  if (!bool_field(root, "overwrite", &m->overwrite, error)) goto failed;
  v = cv_json_get(root, "root");
  if (v) {
    if (v->type != CV_JSON_STRING) { set_message(error, "Manifest root must be a string"); goto failed; }
    m->root = duplicate_string(v->string);
  }
  v = cv_json_get(root, "output_root");
  if (v) {
    if (v->type != CV_JSON_STRING) { set_message(error, "Manifest output_root must be a string"); goto failed; }
    m->output_root = duplicate_string(v->string);
  }
  items = cv_json_get(root, "items");
  if (!items || items->type != CV_JSON_ARRAY || !items->count) {
    set_message(error, "Manifest items must be a non-empty array"); goto failed;
  }
  if (items->count > CV_ITEMS_LIMIT) { set_message(error, "Manifest exceeds 100000 items"); goto failed; }
  m->items = calloc(items->count, sizeof(*m->items));
  if (!m->items) { set_message(error, "Out of memory"); goto failed; }
  m->count = items->count;
  for (i = 0; i < items->count; i++) {
    const cv_json *entry = items->items[i];
    cv_item_spec *item = &m->items[i];
    const char *s;
    if (entry->type != CV_JSON_OBJECT) { set_message(error, "Item %zu must be an object", i); goto failed; }
    if (!reject_unknown(entry, "item", item_allowed, sizeof(item_allowed) / sizeof(item_allowed[0]), error)) goto failed;
    s = string_field(entry, "input", error);
    if (!s || !*s) { if (!*error) set_message(error, "Item %zu needs a non-empty input", i); goto failed; }
    item->input = duplicate_string(s);
    s = string_field(entry, "to", error);
    if (!s || !*s) { if (!*error) set_message(error, "Item %zu needs a non-empty to", i); goto failed; }
    item->to = duplicate_string(s);
    s = string_field(entry, "id", error);
    if (*error) goto failed;
    if (s) item->id = duplicate_string(s);
    s = string_field(entry, "output", error);
    if (*error) goto failed;
    if (s) item->output = duplicate_string(s);
    s = string_field(entry, "format", error);
    if (*error) goto failed;
    if (s) item->from = duplicate_string(s);
    v = cv_json_get(entry, "profile");
    if (v) {
      if (v->type != CV_JSON_STRING || !profile_parse(v->string, &item->profile)) {
        set_message(error, "Item %zu profile must be text or preserve", i); goto failed;
      }
      item->profile_set = 1;
    }
    v = cv_json_get(entry, "overwrite");
    if (v) {
      if (v->type != CV_JSON_BOOL) { set_message(error, "Item %zu overwrite must be boolean", i); goto failed; }
      item->overwrite = v->boolean;
      item->overwrite_set = 1;
    }
  }
  for (i = 0; i < m->count; i++) {
    size_t k;
    if (!m->items[i].id) continue;
    for (k = i + 1; k < m->count; k++)
      if (m->items[k].id && !strcmp(m->items[i].id, m->items[k].id)) {
        set_message(error, "Duplicate item id '%s'", m->items[i].id);
        goto failed;
      }
  }
  cv_json_free(root);
  return 1;
failed:
  cv_json_free(root);
  manifest_free(m);
  return 0;
}

/* ---------- jobs ---------- */
typedef struct {
  cv_result result;
  cv_profile profile;
  int overwrite;
  const cv_format *declared, *target;
  int explicit_format;
  int preflight_ok;
} cv_job;
static void job_free(cv_job *job) { cv_result_free(&job->result); }
static void reject_job(cv_job *job, exr_status code, const char *message) {
  job->preflight_ok = 0;
  job->result.status = "rejected";
  job->result.stage = "preflight";
  job->result.error_code = (int)code;
  set_message(&job->result.error_message, "%s", message);
}
static void fail_job(cv_job *job, const char *stage, exr_status code, char *message) {
  job->result.status = (code == EXR_CANCELLED) ? "cancelled" : "failed";
  job->result.stage = stage;
  job->result.error_code = (int)code;
  free(job->result.error_message);
  job->result.error_message = message;
}
static void cancel_job(cv_job *job, const char *stage) {
  job->result.status = "cancelled";
  job->result.stage = stage;
  job->result.error_code = EXR_CANCELLED;
  free(job->result.error_message);
  job->result.error_message = duplicate_string("cancelled");
}
static char *derive_output(const char *input, const cv_format *target, cv_profile profile,
                           const char *output_root, char **error) {
  char *dir = output_root ? duplicate_string(output_root) : cv_dirname(input);
  char *base, *stem, *out, *ext = NULL;
  const char *dot;
  size_t n;
  (void)error;
  if (!dir) return NULL;
  base = cv_basename(input);
  if (!base) { free(dir); return NULL; }
  dot = strrchr(base, '.');
  n = dot && dot != base ? (size_t)(dot - base) : strlen(base);
  stem = malloc(n + 1);
  if (!stem) { free(base); free(dir); return NULL; }
  memcpy(stem, base, n); stem[n] = 0;
  free(base);
  if (profile == CV_PROFILE_PRESERVE && target->format == EXR_HTML) {
    out = malloc(strlen(dir) + strlen(stem) + 16);
    if (out) sprintf(out, "%s/%s-html.zip", dir, stem);
  } else {
    const char *extension = output_extension(target, profile);
    out = malloc(strlen(dir) + strlen(stem) + strlen(extension) + 24);
    if (out) {
      sprintf(out, "%s/%s.%s", dir, stem, extension);
      if (!strcmp(extension, target->name)) {
        /* Avoid source==target for same-format text/preserve requests. */
        char *probe = cv_absolute(out, NULL);
        char *src = cv_absolute(input, NULL);
        if (probe && src && cv_path_equal(probe, src)) {
          ext = duplicate_string(profile == CV_PROFILE_PRESERVE ? "-preserved" : "-converted");
          if (ext) sprintf(out, "%s/%s%s.%s", dir, stem, ext, extension);
        }
        free(probe); free(src); free(ext);
      }
    }
  }
  free(stem); free(dir);
  return out;
}
static int build_jobs(const cv_item_spec *specs, size_t count, const char *root,
                      const char *output_root, int cli_profile_set, cv_profile cli_profile,
                      int cli_overwrite, const char *manifest,
                      cv_job **out_jobs, size_t *out_count, char **error) {
  cv_job *jobs;
  size_t i, j;
  *out_jobs = NULL; *out_count = 0;
  jobs = calloc(count, sizeof(*jobs));
  if (!jobs) { set_message(error, "Out of memory"); return 0; }
  for (i = 0; i < count; i++) {
    const cv_item_spec *spec = &specs[i];
    cv_job *job = &jobs[i];
    char *resolved = NULL, *input_abs = NULL, *output_abs = NULL, *local_error = NULL;
    cv_file_id input_id, output_id;
    int same = 0;
    cv_result_init(&job->result);
    job->profile = cli_profile_set ? cli_profile : spec->profile_set ? spec->profile : CV_PROFILE_TEXT;
    job->result.profile = job->profile;
    job->overwrite = cli_overwrite || spec->overwrite;
    job->result.id = duplicate_string(spec->id ? spec->id : "");
    if (!job->result.id) { set_message(error, "Out of memory"); goto failed; }
    if (!spec->id) {
      free(job->result.id);
      job->result.id = malloc(32);
      if (!job->result.id) { set_message(error, "Out of memory"); goto failed; }
      sprintf(job->result.id, "item-%zu", i);
    }
    resolved = cv_join(root, spec->input);
    if (!resolved || !(input_abs = cv_absolute(resolved, &local_error))) {
      reject_job(job, EXR_ARGUMENT, local_error ? local_error : "Cannot resolve input path");
      free(local_error); local_error = NULL;
      free(resolved);
      continue;
    }
    free(resolved);
    job->result.input = input_abs;
    if (!cv_identity(input_abs, &input_id, &local_error)) {
      reject_job(job, EXR_IO, local_error ? local_error : "Cannot inspect input");
      free(local_error); local_error = NULL;
      continue;
    }
    if (!input_id.exists || !input_id.is_file) {
      reject_job(job, EXR_IO, "Input does not exist or is not a regular file");
      continue;
    }
    if (spec->from) {
      job->declared = parse_format(spec->from);
      job->explicit_format = 1;
      job->result.format_source = "explicit";
      if (!job->declared) {
        reject_job(job, EXR_UNSUPPORTED, "Unknown explicit input format");
        continue;
      }
    } else {
      job->declared = format_from_extension(input_abs);
      job->explicit_format = 0;
      job->result.format_source = "extension";
      if (!job->declared) {
        reject_job(job, EXR_UNSUPPORTED, "Unsupported input extension; pass --from/format explicitly");
        continue;
      }
    }
    job->target = parse_format(spec->to);
    if (!job->target) {
      reject_job(job, EXR_UNSUPPORTED, "Unknown or unsupported target format");
      continue;
    }
    if (job->profile == CV_PROFILE_PRESERVE) {
      if (!job->declared->preserve_input) {
        reject_job(job, EXR_UNSUPPORTED,
                   "Preserve profile accepts only EPUB/HTML/XHTML inputs; no text fallback is performed");
        continue;
      }
      if (!job->target->preserve_output) {
        reject_job(job, EXR_UNSUPPORTED,
                   "Preserve profile accepts only EPUB/HTML outputs; no text fallback is performed");
        continue;
      }
    } else {
      if (!job->declared->text_input) {
        reject_job(job, EXR_UNSUPPORTED, "Input format is outside the text profile");
        continue;
      }
      if (!job->target->text_output) {
        reject_job(job, EXR_UNSUPPORTED,
                   "Target format is outside the text profile (MOBI/KF8/PDF/CBZ write-back is unsupported)");
        continue;
      }
    }
    if (spec->output && *spec->output) {
      if (cv_is_absolute(spec->output))
        output_abs = cv_absolute(spec->output, &local_error);
      else {
        char *base = output_root ? duplicate_string(output_root) : cv_dirname(input_abs);
        char *joined = base ? cv_join(base, spec->output) : NULL;
        free(base);
        output_abs = joined ? cv_absolute(joined, &local_error) : NULL;
        free(joined);
      }
    } else {
      output_abs = derive_output(input_abs, job->target, job->profile, output_root, &local_error);
    }
    if (!output_abs) {
      reject_job(job, EXR_MEMORY, local_error ? local_error : "Cannot derive output path");
      free(local_error); local_error = NULL;
      continue;
    }
    {
      char *normalized = cv_absolute(output_abs, NULL);
      if (normalized) { free(output_abs); output_abs = normalized; }
    }
    free(local_error); local_error = NULL;
    job->result.output = output_abs;
    if (!cv_same_file(input_abs, output_abs, &same, &local_error)) {
      reject_job(job, EXR_IO, local_error ? local_error : "Cannot compare input and output");
      free(local_error); local_error = NULL;
      continue;
    }
    if (same) {
      reject_job(job, EXR_ARGUMENT, "Source and output denote the same file");
      continue;
    }
    if (!cv_identity(output_abs, &output_id, &local_error)) {
      reject_job(job, EXR_IO, local_error ? local_error : "Cannot inspect output");
      free(local_error); local_error = NULL;
      continue;
    }
    if (output_id.exists && !output_id.is_dir && !job->overwrite) {
      reject_job(job, EXR_IO, "Output already exists and --overwrite was not given");
      continue;
    }
    job->preflight_ok = 1;
  }
  /* Protect the batch manifest before any conversion. */
  for (i = 0; i < count; i++) {
    if (jobs[i].preflight_ok && manifest) {
      char *local_error = NULL;
      int same = 0;
      if (!cv_same_file(jobs[i].result.output, manifest, &same, &local_error))
        reject_job(&jobs[i], EXR_IO, local_error ? local_error : "Cannot compare output and batch manifest");
      else if (same)
        reject_job(&jobs[i], EXR_ARGUMENT, "Output denotes the batch manifest");
      free(local_error);
    }
  }
  /* Duplicate outputs are rejected before any conversion. */
  for (i = 0; i < count; i++) {
    if (!jobs[i].result.output) continue;
    for (j = i + 1; j < count; j++) {
      int same = 0;
      if (!jobs[j].result.output) continue;
      if (cv_path_equal(jobs[i].result.output, jobs[j].result.output)) same = 1;
      else {
        char *local_error = NULL;
        if (!cv_same_file(jobs[i].result.output, jobs[j].result.output, &same, &local_error)) {
          same = 0;
        }
        free(local_error);
      }
      if (same) {
        if (jobs[i].preflight_ok) reject_job(&jobs[i], EXR_ARGUMENT, "Duplicate output path in batch");
        if (jobs[j].preflight_ok) reject_job(&jobs[j], EXR_ARGUMENT, "Duplicate output path in batch");
      }
    }
  }
  *out_jobs = jobs;
  *out_count = count;
  return 1;
failed:
  for (i = 0; i < count; i++) job_free(&jobs[i]);
  free(jobs);
  return 0;
}

/* ---------- conversion ---------- */
static int verify_text_output(cv_job *job, exr_document *source, const void *data,
                              size_t size, char **error) {
  exr_document *output = NULL;
  exr_error exr_error_value = {0};
  exr_status status = exr_document_open_memory(job->target->format, data, size, &output,
                                               &exr_error_value);
  int ok = 0;
  if (status != EXR_OK) {
    set_message(error, "Published output did not reopen: %s", exr_error_value.message);
    return 0;
  }
  if (job->target->format == EXR_TXT) {
    size_t a = 0, b = 0;
    const char *at = exr_document_text(source, &a), *bt = exr_document_text(output, &b);
    ok = a == b && (!a || !memcmp(at ? at : "", bt ? bt : "", a));
  } else {
    ok = text_equal_normalized(source, output, error);
  }
  exr_document_free(output);
  return ok;
}
static int verify_preserve_epub(cv_job *job, exr_document *source, const void *data,
                                size_t size, char **error) {
  exr_document *output = NULL;
  exr_error exr_error_value = {0};
  exr_status status = exr_document_open_memory(EXR_EPUB, data, size, &output, &exr_error_value);
  const exr_chapter *sa, *sb;
  const exr_resource *ra, *rb;
  size_t sc, oc, sr, orr, i, j;
  int ok = 0;
  if (status != EXR_OK) {
    set_message(error, "Published EPUB did not reopen: %s", exr_error_value.message);
    return 0;
  }
  if (!text_equal_normalized(source, output, error)) {
    set_message(error, "Reopened EPUB normalized text differs from the source");
    goto done;
  }
  sa = exr_document_chapters(source, &sc);
  sb = exr_document_chapters(output, &oc);
  {
    size_t sn = 0, on = 0, si = 0, oi = 0, k;
    for (i = 0; i < sc; i++) if (sa[i].in_spine) sn++;
    for (i = 0; i < oc; i++) if (sb[i].in_spine) on++;
    if (sn != on) {
      set_message(error, "Reopened EPUB spine length differs from the source");
      goto done;
    }
    for (k = 0; k < sn; k++) {
      while (si < sc && !sa[si].in_spine) si++;
      while (oi < oc && !sb[oi].in_spine) oi++;
      if (si >= sc || oi >= oc || sa[si].linear != sb[oi].linear) {
        set_message(error, "Reopened EPUB reading order differs from the source");
        goto done;
      }
      /* Standalone HTML/XHTML input has no authored package path; the exporter
         generates a collision-free chapter path. EPUB input keeps exact paths. */
      if (strcmp(job->result.input_format, "epub") == 0 &&
          (!sa[si].path || !sb[oi].path || strcmp(sa[si].path, sb[oi].path))) {
        set_message(error, "Reopened EPUB chapter paths differ from the source");
        goto done;
      }
      si++; oi++;
    }
  }
  ra = exr_document_resources(source, &sr);
  rb = exr_document_resources(output, &orr);
  for (i = 0; i < sr; i++) {
    for (j = 0; j < orr; j++)
      if (ra[i].path && rb[j].path && !strcmp(ra[i].path, rb[j].path)) break;
    if (j == orr) {
      set_message(error, "Reopened EPUB is missing resource '%s'", ra[i].path ? ra[i].path : "");
      goto done;
    }
    if ((ra[i].media_type ? ra[i].media_type : "")[0] &&
        strcmp(ra[i].media_type ? ra[i].media_type : "", rb[j].media_type ? rb[j].media_type : "")) {
      set_message(error, "Reopened EPUB media type differs for '%s'", ra[i].path);
      goto done;
    }
    if (strcmp(ra[i].properties ? ra[i].properties : "", rb[j].properties ? rb[j].properties : "")) {
      set_message(error, "Reopened EPUB resource properties differ for '%s'", ra[i].path);
      goto done;
    }
    /* Chapter XHTML is reserialized from the model; the text/spine checks above
       cover it, while non-XHTML resources must be byte-identical. */
    if (ra[i].media_type && !strcmp(ra[i].media_type, "application/xhtml+xml")) continue;
    {
      void *a = NULL, *b = NULL;
      size_t an = 0, bn = 0;
      exr_error ae = {0};
      if (exr_document_resource(source, i, &a, &an, &ae) != EXR_OK ||
          exr_document_resource(output, j, &b, &bn, &ae) != EXR_OK ||
          an != bn || (an && memcmp(a, b, an))) {
        exr_free(a); exr_free(b);
        set_message(error, "Reopened EPUB resource bytes differ for '%s'", ra[i].path);
        goto done;
      }
      exr_free(a); exr_free(b);
    }
  }
  ok = 1;
done:
  exr_document_free(output);
  return ok;
}
static int verify_html_bundle(cv_job *job, exr_document *source, const void *data, size_t size,
                              const char *entry, char **error) {
  mz_zip_archive zip;
  const exr_chapter *chapters;
  const exr_resource *resources;
  size_t chapters_count, resources_count, i;
  int ok = 0;
  memset(&zip, 0, sizeof(zip));
  if (!entry || !*entry) { set_message(error, "HTML bundle has no entry path"); return 0; }
  if (!mz_zip_reader_init_mem(&zip, data, size, 0)) {
    set_message(error, "Published HTML bundle is not a readable ZIP");
    return 0;
  }
  {
    size_t body_size = 0;
    void *body = mz_zip_reader_extract_file_to_heap(&zip, entry, &body_size, 0);
    exr_document *entry_document = NULL;
    exr_error entry_error = {0};
    if (!body) {
      set_message(error, "HTML bundle entry '%s' is missing", entry);
      goto done;
    }
    if (exr_document_open_memory(EXR_HTML, body, body_size, &entry_document, &entry_error) != EXR_OK) {
      mz_free(body);
      set_message(error, "HTML entry did not reopen: %s", entry_error.message);
      goto done;
    }
    exr_document_free(entry_document);
    mz_free(body);
  }
  chapters = exr_document_chapters(source, &chapters_count);
  for (i = 0; i < chapters_count; i++) {
    if (chapters[i].path && *chapters[i].path &&
        mz_zip_reader_locate_file(&zip, chapters[i].path, NULL, 0) < 0) {
      set_message(error, "HTML bundle is missing chapter '%s'", chapters[i].path);
      goto done;
    }
  }
  resources = exr_document_resources(source, &resources_count);
  for (i = 0; i < resources_count; i++) {
    if (resources[i].path && *resources[i].path &&
        mz_zip_reader_locate_file(&zip, resources[i].path, NULL, 0) < 0) {
      set_message(error, "HTML bundle is missing resource '%s'", resources[i].path);
      goto done;
    }
  }
  ok = 1;
done:
  mz_zip_reader_end(&zip);
  return ok;
}
static void notes_begin(cv_text *notes, int *first) {
  cv_text_string(notes, "[");
  *first = 1;
}
static void notes_add(cv_text *notes, int *first, const char *key, const char *value) {
  if (!*first) cv_text_string(notes, ",");
  *first = 0;
  cv_text_string(notes, "{\"key\":");
  cv_text_json(notes, key);
  cv_text_string(notes, ",\"value\":");
  cv_text_json(notes, value);
  cv_text_string(notes, "}");
}
static void notes_end(cv_text *notes) { cv_text_string(notes, "]"); }
static void run_job(cv_job *job, const exr_control *control) {
  exr_error exr_error_value = {0};
  exr_status status;
  exr_document *document = NULL;
  void *data = NULL;
  char *entry_owned = NULL;
  size_t size = 0;
  const char *entry = NULL;
  char *error = NULL;
  uint64_t input_size = 0;
  uint64_t started = cv_now_ms();
  char variant_buffer[64] = {0};
  int notes_first = 0;
  if (!job->preflight_ok) return;
  job->result.status = "failed";
  job->result.stage = "read";
  if (g_cancelled) { cancel_job(job, "read"); return; }
  {
    char hash[65];
    if (!cv_file_size(job->result.input, &input_size, &error)) {
      fail_job(job, "read", EXR_IO, error ? error : duplicate_string("Cannot size input"));
      return;
    }
    job->result.input_bytes = input_size;
    if (input_size > CV_SIZE_LIMIT) {
      fail_job(job, "read", EXR_LIMIT, duplicate_string("Input exceeds the 512 MiB tool limit"));
      return;
    }
    if (!cv_sha256_file(job->result.input, hash, &error)) {
      fail_job(job, "read", EXR_IO, error ? error : duplicate_string("Cannot hash input"));
      return;
    }
    memcpy(job->result.input_sha, hash, sizeof(hash));
  }
  if (job->declared->format == EXR_MOBI) {
    unsigned char *prefix = malloc(1u << 20);
    size_t got = 0;
    if (!prefix) {
      fail_job(job, "read", EXR_MEMORY, duplicate_string("Cannot allocate MOBI header buffer"));
      return;
    }
    if (!cv_read_prefix(job->result.input, prefix, 1u << 20, &got, &error)) {
      free(prefix);
      fail_job(job, "read", EXR_IO, error ? error : duplicate_string("Cannot read MOBI header"));
      return;
    }
    snprintf(variant_buffer, sizeof(variant_buffer), "%s", mobi_variant_bytes(prefix, got));
    free(prefix);
    if (!strcmp(variant_buffer, "unknown")) {
      fail_job(job, "read", EXR_FORMAT, duplicate_string("Not a recognized MOBI/KF8 container"));
      return;
    }
    {
      const cv_format *actual = parse_format(variant_buffer);
      job->result.input_variant = actual ? actual->name : "unknown";
      job->result.input_format = actual ? actual->name : "unknown";
    }
    if (strcmp(variant_buffer, job->declared->variant)) {
      fail_job(job, "read", EXR_FORMAT,
               duplicate_string(job->explicit_format
                                    ? "Declared MOBI/KF8 variant does not match the input bytes"
                                    : "File extension MOBI/KF8 variant does not match the input bytes; "
                                      "rename or pass --from explicitly"));
      return;
    }
  } else {
    job->result.input_variant = "none";
    job->result.input_format = job->declared->name;
  }
  job->result.target_format = job->target->name;
  job->result.stage = "open";
  if (job->explicit_format) {
    unsigned char *bytes = NULL;
    size_t bytes_size = 0;
    if (!cv_read_file(job->result.input, &bytes, &bytes_size, &error)) {
      fail_job(job, "open", EXR_IO, error ? error : duplicate_string("Cannot read input"));
      return;
    }
    status = exr_document_open_memory(job->declared->format, bytes, bytes_size, &document,
                                      &exr_error_value);
    free(bytes);
  } else {
    status = exr_document_open(job->result.input, &document, &exr_error_value);
  }
  if (status != EXR_OK) {
    fail_job(job, "open", status, duplicate_string(exr_error_value.message));
    return;
  }
  if (exr_document_format(document) != job->declared->format) {
    set_message(&error, "Declared input format '%s' does not match loaded document",
                job->declared->name);
    exr_document_free(document);
    fail_job(job, "open", EXR_FORMAT, error);
    return;
  }
  if (g_cancelled) { exr_document_free(document); cancel_job(job, "open"); return; }
  {
    size_t chapters = 0, resources = 0;
    (void)exr_document_chapters(document, &chapters);
    (void)exr_document_resources(document, &resources);
    job->result.chapters = chapters;
    job->result.resources = resources;
    cv_degradations(&job->result.degradations, job->profile, job->target->name,
                    job->result.input_format ? job->result.input_format : job->declared->name,
                    chapters, resources);
  }
  notes_begin(&job->result.notes, &notes_first);
  if (job->declared->format == EXR_MOBI)
    notes_add(&job->result.notes, &notes_first, "mobi_variant_source",
              job->explicit_format ? "explicit-format-validated-against-bytes"
                                   : "extension-expectation-validated-against-bytes");
  notes_add(&job->result.notes, &notes_first, "profile_semantics",
            job->profile == CV_PROFILE_PRESERVE
                ? "structure/resource preservation; target rendering fidelity is not asserted"
                : "declared body text only; not lossless or high-fidelity");
  job->result.stage = "convert";
  if (job->profile == CV_PROFILE_PRESERVE && job->target->format == EXR_EPUB) {
    status = exr_document_export_epub(document, control, &data, &size, &exr_error_value);
  } else if (job->profile == CV_PROFILE_PRESERVE && job->target->format == EXR_HTML) {
    status = exr_document_export_html_bundle(document, control, &data, &size,
                                             (char **)&entry_owned, &exr_error_value);
    entry = (const char *)entry_owned;
    if (status == EXR_OK && entry) {
      job->result.entry_path = duplicate_string(entry);
      notes_add(&job->result.notes, &notes_first, "html_bundle_entry", entry);
      notes_add(&job->result.notes, &notes_first, "html_bundle_usage",
                "extract the whole ZIP before opening entry_path; the ZIP is not a single HTML file");
    }
  } else {
    status = exr_document_export_control(document, job->target->format, control, &data, &size,
                                         &exr_error_value);
  }
  if (status != EXR_OK) {
    exr_free(data); exr_free(entry_owned);
    exr_document_free(document);
    if (status == EXR_CANCELLED) cancel_job(job, "convert");
    else fail_job(job, "convert", status, duplicate_string(exr_error_value.message));
    return;
  }
  if (!data || !size) {
    exr_free(data); exr_free(entry_owned);
    exr_document_free(document);
    fail_job(job, "convert", EXR_LIMIT, duplicate_string("Converter returned an empty payload"));
    return;
  }
  if (g_cancelled) {
    exr_free(data); exr_free(entry_owned);
    exr_document_free(document);
    cancel_job(job, "convert");
    return;
  }
  {
    char *temp = NULL;
    char *publish_error = NULL;
    int same = 0;
    job->result.stage = "write";
    if (!cv_write_temp(job->result.output, data, size, &temp, &publish_error)) {
      exr_free(data); exr_free(entry_owned); exr_document_free(document);
      fail_job(job, "write", EXR_IO, publish_error ? publish_error : duplicate_string("Cannot write output"));
      return;
    }
    if (g_cancelled) {
      cv_remove(temp); free(temp);
      exr_free(data); exr_free(entry_owned); exr_document_free(document);
      cancel_job(job, "publish");
      return;
    }
    if (!cv_same_file(job->result.input, job->result.output, &same, &publish_error)) {
      cv_remove(temp); free(temp);
      exr_free(data); exr_free(entry_owned); exr_document_free(document);
      fail_job(job, "publish", EXR_IO, publish_error ? publish_error : duplicate_string("Cannot compare paths"));
      return;
    }
    if (same) {
      cv_remove(temp); free(temp);
      exr_free(data); exr_free(entry_owned); exr_document_free(document);
      fail_job(job, "publish", EXR_ARGUMENT, duplicate_string("Source and output denote the same file"));
      return;
    }
    job->result.stage = "publish";
    if (!cv_publish(temp, job->result.output, job->overwrite, &publish_error)) {
      cv_remove(temp); free(temp);
      exr_free(data); exr_free(entry_owned); exr_document_free(document);
      fail_job(job, "publish", EXR_IO, publish_error ? publish_error : duplicate_string("Cannot publish output"));
      return;
    }
    free(temp);
    job->result.published = 1;
    notes_add(&job->result.notes, &notes_first, "publication", "same-directory temporary file, flushed, atomically published");
  }
  {
    char hash[65];
    if (cv_sha256_file(job->result.output, hash, &error)) {
      memcpy(job->result.output_sha, hash, sizeof(hash));
    }
    if (!cv_file_size(job->result.output, &job->result.output_bytes, &error)) {
      job->result.output_bytes = size;
    }
  }
  job->result.stage = "verify";
  {
    int verified = 0;
    if (job->profile == CV_PROFILE_PRESERVE && job->target->format == EXR_EPUB) {
      verified = verify_preserve_epub(job, document, data, size, &error);
      if (verified) notes_add(&job->result.notes, &notes_first, "verify_rule",
                              "reopened EPUB: normalized text, spine order and resource bytes");
    } else if (job->profile == CV_PROFILE_PRESERVE && job->target->format == EXR_HTML) {
      verified = verify_html_bundle(job, document, data, size, entry, &error);
      if (verified) notes_add(&job->result.notes, &notes_first, "verify_rule",
                              "ZIP entry opens and every chapter/resource path is present");
    } else {
      verified = verify_text_output(job, document, data, size, &error);
      if (verified) {
        notes_add(&job->result.notes, &notes_first, "verify_rule",
                  job->target->format == EXR_TXT
                      ? "reopened TXT text is byte-identical to the source document text"
                      : "reopened text equals the source after ASCII-whitespace collapse");
      }
    }
    job->result.reopen_verified = verified;
    if (!verified) {
      exr_free(data); exr_free(entry_owned); exr_document_free(document);
      fail_job(job, "verify", EXR_FORMAT,
               error ? error : duplicate_string("Reopened output did not verify"));
      return;
    }
  }
  notes_end(&job->result.notes);
  exr_free(data); exr_free(entry_owned);
  exr_document_free(document);
  job->result.status = "ok";
  job->result.stage = "complete";
  job->result.error_code = EXR_OK;
  free(job->result.error_message);
  job->result.error_message = duplicate_string("");
  job->result.elapsed_ms = cv_now_ms() - started;
}


/* ---------- reporting and driver ---------- */
static int publish_report(const char *path, const cv_text *json, char **error) {
  char *temp = NULL;
  if (!path) return 1;
  if (!cv_write_temp(path, json->data, json->size, &temp, error)) return 0;
  if (!cv_publish(temp, path, 1, error)) {
    cv_remove(temp); free(temp);
    return 0;
  }
  free(temp);
  return 1;
}
static int report_collides(const char *report, const cv_job *jobs, size_t count,
                           const char *manifest, char **error) {
  size_t i;
  int same = 0;
  if (!report) return 0;
  if (manifest && (!cv_same_file(report, manifest, &same, error) || same)) return 1;
  for (i = 0; i < count; i++) {
    int same = 0;
    if (jobs[i].result.input && cv_path_equal(report, jobs[i].result.input)) return 1;
    if (jobs[i].result.output && cv_path_equal(report, jobs[i].result.output)) return 1;
    if (jobs[i].result.input && cv_same_file(report, jobs[i].result.input, &same, error) && same)
      return 1;
    if (jobs[i].result.output && cv_same_file(report, jobs[i].result.output, &same, error) && same)
      return 1;
  }
  return 0;
}
static void build_report(cv_text *json, const char *mode, const char *manifest,
                         const char *report, int overwrite, int defaulted, int cancelled,
                         int complete, int written, const cv_job *jobs, size_t count,
                         const char *started, const char *finished, size_t peak,
                         unsigned long long elapsed) {
  size_t i;
  cv_result *results = count ? calloc(count, sizeof(*results)) : NULL;
  if (count && !results) { cv_text_string(json, "{}\n"); return; }
  for (i = 0; i < count; i++) results[i] = jobs[i].result;
  cv_report_json(json, mode, manifest, report, overwrite, defaulted, cancelled, complete,
                 written, results, count, started, finished, peak, elapsed);
  free(results);
}
static void usage(FILE *out) {
  fprintf(out,
          "exreader-convert %s (ABI %u)\n"
          "Usage:\n"
          "  exreader-convert --capabilities\n"
          "  exreader-convert --input PATH --to FORMAT [--from FORMAT] [--profile text|preserve]\n"
          "                   [--output PATH] [--output-root DIR] [--report PATH] [--overwrite]\n"
          "  exreader-convert --batch MANIFEST [--root DIR] [--output-root DIR] [--profile PROFILE]\n"
          "                   [--report PATH] [--overwrite]\n"
          "\n"
          "Profiles: text (default) converts declared body text; preserve copies structure and\n"
          "resources for EPUB/HTML inputs to EPUB or a single ZIP HTML bundle. Unsupported\n"
          "pairs are rejected; preserve never falls back to text. Relative manifest inputs\n"
          "resolve against --root (default: manifest directory). Relative outputs resolve\n"
          "against --output-root when set, otherwise the input directory. Reports are JSON\n"
          "and always include per-item stage/status/degradation/publication/reopen state.\n",
          exr_version(), exr_abi_version());
}
static int invocation_error(const char *message) {
  fprintf(stderr, "exreader-convert: %s\n", message);
  return 2;
}
static char *manifest_directory(const char *manifest) {
  char *absolute = cv_absolute(manifest, NULL);
  char *dir;
  if (!absolute) return NULL;
  dir = cv_dirname(absolute);
  free(absolute);
  return dir;
}
static int parse_cli(int argc, char **argv, cv_item_spec *single, int *single_used,
                     const char **manifest_arg, const char **root_arg, const char **output_root_arg,
                     const char **report_arg, int *overwrite, int *profile_set,
                     cv_profile *profile, char **parse_error) {
  int i;
  const char *input = NULL, *to = NULL, *from = NULL, *output = NULL;
  memset(single, 0, sizeof(*single));
  *manifest_arg = NULL; *root_arg = NULL; *output_root_arg = NULL; *report_arg = NULL;
  *overwrite = 0; *profile_set = 0; *single_used = 0; *parse_error = NULL;
  for (i = 1; i < argc; i++) {
    const char *arg = argv[i];
    const char *value = NULL;
    if (!strcmp(arg, "--overwrite")) { *overwrite = 1; continue; }
    if (!strcmp(arg, "--help") || !strcmp(arg, "-h")) { usage(stdout); return 1; }
    if (!strcmp(arg, "--version")) { printf("%s %u\n", exr_version(), exr_abi_version()); return 1; }
    if (!strcmp(arg, "--capabilities")) {
      if (i + 1 != argc) { *parse_error = duplicate_string("--capabilities must be used alone"); return -1; }
      return 2;
    }
    if (!strncmp(arg, "--", 2)) {
      size_t n = strlen(arg);
      if (n > 2 && arg[n - 1] == '=') {
        *parse_error = duplicate_string("Options use a separate value argument");
        return -1;
      }
      if (i + 1 >= argc) {
        *parse_error = malloc(strlen(arg) + 32);
        if (*parse_error) sprintf(*parse_error, "Option %s needs a value", arg);
        return -1;
      }
      value = argv[++i];
      if (!strcmp(arg, "--input")) { if (input) goto duplicate; input = value; }
      else if (!strcmp(arg, "--to")) { if (to) goto duplicate; to = value; }
      else if (!strcmp(arg, "--from") || !strcmp(arg, "--format")) { if (from) goto duplicate; from = value; }
      else if (!strcmp(arg, "--output")) { if (output) goto duplicate; output = value; }
      else if (!strcmp(arg, "--batch")) { if (*manifest_arg) goto duplicate; *manifest_arg = value; }
      else if (!strcmp(arg, "--root")) { if (*root_arg) goto duplicate; *root_arg = value; }
      else if (!strcmp(arg, "--output-root")) { if (*output_root_arg) goto duplicate; *output_root_arg = value; }
      else if (!strcmp(arg, "--report")) { if (*report_arg) goto duplicate; *report_arg = value; }
      else if (!strcmp(arg, "--profile")) {
        if (*profile_set) goto duplicate;
        if (!profile_parse(value, profile)) { *parse_error = duplicate_string("Unknown profile"); return -1; }
        *profile_set = 1;
      } else {
        *parse_error = malloc(strlen(arg) + 32);
        if (*parse_error) sprintf(*parse_error, "Unknown option %s", arg);
        return -1;
      }
      continue;
    }
    *parse_error = malloc(strlen(arg) + 48);
    if (*parse_error) sprintf(*parse_error, "Unexpected positional argument: %s", arg);
    return -1;
duplicate:
    *parse_error = malloc(strlen(arg) + 32);
    if (*parse_error) sprintf(*parse_error, "Duplicate option %s", arg);
    return -1;
  }
  if (*manifest_arg && (input || to || output || from)) {
    *parse_error = duplicate_string("--batch cannot be combined with --input/--to/--from/--output");
    return -1;
  }
  if (*manifest_arg) return 0;
  if (!input || !to) {
    *parse_error = duplicate_string("Single conversion requires --input and --to");
    return -1;
  }
  single->input = duplicate_string(input);
  single->to = duplicate_string(to);
  single->from = duplicate_string(from);
  single->output = duplicate_string(output);
  single->id = duplicate_string("single");
  *single_used = 1;
  return 0;
}
static int convert_main(int argc, char **argv) {
  cv_item_spec single;
  cv_item_spec *specs = NULL;
  cv_manifest manifest;
  cv_job *jobs = NULL;
  size_t job_count = 0, i;
  int single_used = 0, overwrite = 0, profile_set = 0, status = 0;
  int manifest_profile_set = 0, defaulted = 1, all_ok = 1, report_ok = 1;
  cv_profile profile = CV_PROFILE_TEXT;
  const char *manifest_arg = NULL, *root_arg = NULL, *output_root_arg = NULL, *report_arg = NULL;
  char *parse_error = NULL, *manifest_dir = NULL, *root = NULL, *output_root = NULL;
  char *report = NULL, *report_error = NULL;
  char started[32], finished[32];
  uint64_t start_ms;
  cv_text json;
  cv_apply_allocator_policy(argv);
  memset(&manifest, 0, sizeof(manifest));
  memset(&single, 0, sizeof(single));
  install_cancel_handlers();
  {
    int parsed = parse_cli(argc, argv, &single, &single_used, &manifest_arg, &root_arg,
                           &output_root_arg, &report_arg, &overwrite, &profile_set, &profile,
                           &parse_error);
    if (parsed == 2) {
      cv_text_init(&json);
      cv_capabilities_json(&json);
      fwrite(json.data ? json.data : "", 1, json.size, stdout);
      cv_text_free(&json);
      return 0;
    }
    if (parsed == 1) return 0;
    if (parsed < 0) {
      status = invocation_error(parse_error ? parse_error : "Invalid arguments");
      free(parse_error);
      return status;
    }
  }
  start_ms = cv_now_ms();
  cv_timestamp_now(started);
  cv_text_init(&json);
  if (single_used) {
    specs = &single;
    job_count = 1;
    root = cv_absolute(".", NULL);
    if (output_root_arg && !(output_root = cv_absolute(output_root_arg, NULL))) {
      status = invocation_error("Cannot resolve --output-root");
      goto done;
    }
  } else {
    if (!manifest_arg) { status = invocation_error("No input or manifest"); goto done; }
    if (!parse_manifest(manifest_arg, &manifest, &parse_error)) {
      status = invocation_error(parse_error ? parse_error : "Invalid manifest");
      free(parse_error); parse_error = NULL;
      goto done;
    }
    manifest_profile_set = manifest.profile_set;
    {
      int base_overwrite = overwrite || manifest.overwrite;
      overwrite = base_overwrite;
    }
    for (i = 0; i < manifest.count; i++) {
      if (!manifest.items[i].profile_set && manifest.profile_set) {
        manifest.items[i].profile = manifest.profile;
        manifest.items[i].profile_set = 1;
      }
      if (!manifest.items[i].overwrite_set && manifest.overwrite)
        manifest.items[i].overwrite = 1;
    }
    manifest_dir = manifest_directory(manifest_arg);
    if (!manifest_dir) { status = invocation_error("Cannot resolve manifest directory"); goto done; }
    if (root_arg) {
      root = cv_absolute(root_arg, NULL);
    } else if (manifest.root) {
      char *joined = cv_join(manifest_dir, manifest.root);
      root = joined ? cv_absolute(joined, NULL) : NULL;
      free(joined);
    } else {
      root = duplicate_string(manifest_dir);
    }
    if (!root) { status = invocation_error("Cannot resolve input root"); goto done; }
    if (output_root_arg) output_root = cv_absolute(output_root_arg, NULL);
    else if (manifest.output_root) {
      char *joined = cv_join(manifest_dir, manifest.output_root);
      output_root = joined ? cv_absolute(joined, NULL) : NULL;
      free(joined);
    }
    if (output_root_arg && !output_root) {
      status = invocation_error("Cannot resolve --output-root");
      goto done;
    }
    specs = manifest.items;
    job_count = manifest.count;
  }
  if (report_arg) {
    report = cv_absolute(report_arg, NULL);
    if (!report) { status = invocation_error("Cannot resolve report path"); goto done; }
  }
  defaulted = !profile_set && !manifest_profile_set;
  if (job_count) {
    size_t built = 0;
    if (!build_jobs(specs, job_count, root, output_root, profile_set, profile,
                    overwrite, manifest_arg, &jobs, &built, &parse_error)) {
      status = invocation_error(parse_error ? parse_error : "Cannot prepare jobs");
      free(parse_error); parse_error = NULL;
      goto done;
    }
    job_count = built;
  }
  if (report && report_collides(report, jobs, job_count, manifest_arg, &report_error)) {
    status = invocation_error(report_error ? report_error : "Report path collides with an input, output or batch manifest");
    free(report_error); report_error = NULL;
    goto done;
  }
  free(report_error); report_error = NULL;
  for (i = 0; i < job_count; i++) {
    if (g_cancelled) {
      jobs[i].result.status = "unfinished";
      jobs[i].result.stage = "queued";
      jobs[i].result.error_code = EXR_CANCELLED;
      free(jobs[i].result.error_message);
      jobs[i].result.error_message = duplicate_string("cancelled before this item started");
      jobs[i].result.cancel_requested = 1;
    } else {
      exr_control control;
      memset(&control, 0, sizeof(control));
      control.cancelled = cancelled_callback;
      if (i == 0) cv_memory_diag("before", i);
      run_job(&jobs[i], &control);
      if (i < 3 || i % 10 == 9) cv_memory_diag("after-job", i);
      if (i < 3 || i % 10 == 9) cv_memory_diag("after-release", i);
      if (g_cancelled) jobs[i].result.cancel_requested = 1;
    }
    if (report) {
      cv_text attempt;
      char now[32];
      cv_text_init(&attempt);
      cv_timestamp_now(now);
      build_report(&attempt, single_used ? "single" : "batch", manifest_arg, report, overwrite,
                   defaulted, g_cancelled != 0, 0, 1, jobs, job_count, started, now,
                   cv_peak_rss(), cv_now_ms() - start_ms);
      if (!publish_report(report, &attempt, &report_error)) report_ok = 0;
      cv_text_free(&attempt);
    }
  }
  for (i = 0; i < job_count; i++) {
    if (strcmp(jobs[i].result.status, "ok")) all_ok = 0;
    if (!jobs[i].result.reopen_verified && !strcmp(jobs[i].result.status, "ok")) all_ok = 0;
  }
  cv_timestamp_now(finished);
  if (report) {
    cv_text final_json;
    cv_text_init(&final_json);
    build_report(&final_json, single_used ? "single" : "batch", manifest_arg, report, overwrite,
                 defaulted, g_cancelled != 0, all_ok && !g_cancelled, report_ok, jobs, job_count,
                 started, finished, cv_peak_rss(), cv_now_ms() - start_ms);
    report_ok = publish_report(report, &final_json, &report_error);
    cv_text_free(&final_json);
  }
  if (!report_ok) {
    fprintf(stderr, "exreader-convert: report could not be written: %s\n",
            report_error ? report_error : "unknown error");
    fprintf(stderr, "published outputs (not rolled back):\n");
    for (i = 0; i < job_count; i++)
      if (jobs[i].result.published && jobs[i].result.output)
        fprintf(stderr, "  %s\n", jobs[i].result.output);
  }
  build_report(&json, single_used ? "single" : "batch", manifest_arg, report, overwrite, defaulted,
               g_cancelled != 0, all_ok && !g_cancelled, report_ok, jobs, job_count, started,
               finished, cv_peak_rss(), cv_now_ms() - start_ms);
  fwrite(json.data ? json.data : "", 1, json.size, stdout);
  if (!report_ok) status = 4;
  else if (!all_ok || g_cancelled) status = 3;
  else status = 0;
done:
  if (jobs) {
    for (i = 0; i < job_count; i++) job_free(&jobs[i]);
    free(jobs);
  }
  manifest_free(&manifest);
  free(single.input); free(single.to); free(single.from); free(single.output); free(single.id);
  free(manifest_dir); free(root); free(output_root); free(report);
  free(report_error); free(parse_error);
  cv_text_free(&json);
  return status;
}
#define example_main convert_main
#include "../examples/entry.h"

