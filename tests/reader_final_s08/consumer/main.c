/* SPDX-License-Identifier: MIT */
/* S08 independent red-action consumer.
 *
 * Drives the installed public interfaces of three existing owner modules with
 * job-generated secrets and prints machine-readable evidence:
 *
 *   check <id> pass|fail <safe detail>
 *   phase <name> <passed>/<total>
 *   diag  {"module":...,"op":...,"status":...,"code":...}
 *
 * The consumer itself never writes secret material to stdout, stderr or files:
 * every diagnostic carries status names, numeric statuses, system errors,
 * offsets, fixed module messages and the module's own redacted request line.
 * The runner scans this transcript (and every file this process creates) for
 * the secrets in raw/hex/base64/percent/UTF-16 forms.
 *
 * Input arrives on stdin only (never argv), one directive per line:
 *   text <name> <value>
 *   secret <name> <lowercase hex bytes>
 *
 * Owner module sources are read-only in this package; nothing here reimplements
 * their behaviour or relaxes an original assertion.
 */
#if defined(_WIN32)
#define _CRT_SECURE_NO_WARNINGS 1
#endif

#include "exr_credentials.h"
#include "opds.h"
#include "reader_account_profiles.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(_WIN32)
#include <fcntl.h>
#include <io.h>
#endif

#define TEXT_ENTRIES 48
#define VALUE_ENTRIES 16
#define LOG_LINES 24
#define TEXT_CAPACITY 4096
#define LINE_CAPACITY 6400
#define INPUT_CAPACITY (1u << 20)
#define URL_CAPACITY 2048

typedef struct {
  char name[48];
  char text[TEXT_CAPACITY];
} text_entry;

typedef struct {
  char name[48];
  unsigned char data[EXR_CREDENTIALS_SECRET_MAX];
  size_t length;
} value_entry;

static char g_input[INPUT_CAPACITY];
static text_entry g_text[TEXT_ENTRIES];
static int g_text_count;
static value_entry g_values[VALUE_ENTRIES];
static int g_value_count;
static int g_passed;
static int g_total;

static void check(const char *id, int ok, const char *detail) {
  char safe[160];
  size_t index = 0;
  const char *p = detail ? detail : "";
  for (; *p && index + 1u < sizeof safe; ++p) {
    char c = *p;
    int keep = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') ||
               c == '_' || c == '=' || c == ',' || c == '.' || c == ':' || c == '/' || c == '-' ||
               c == ' ';
    safe[index++] = keep ? c : '_';
  }
  safe[index] = '\0';
  g_total += 1;
  if (ok) g_passed += 1;
  printf("check %s %s %s\n", id, ok ? "pass" : "fail", index ? safe : "ok");
  fflush(stdout);
}

static void phase_end(const char *name) {
  printf("phase %s %d/%d\n", name, g_passed, g_total);
  fflush(stdout);
}

static void json_escape(const char *value, char *out, size_t capacity) {
  size_t used = 0;
  const unsigned char *p = (const unsigned char *)(value ? value : "");
  if (capacity == 0u) return;
  for (; *p && used + 8u < capacity; ++p) {
    unsigned char c = *p;
    if (c == '"' || c == '\\') {
      out[used++] = '\\';
      out[used++] = (char)c;
    } else if (c < 0x20u || c == 0x7fu) {
      used += (size_t)snprintf(out + used, capacity - used, "\\u%04x", (unsigned)c);
    } else {
      out[used++] = (char)c;
    }
  }
  out[used] = '\0';
}

static void diag_line(const char *module, const char *op, const char *status, int code,
                      const char *extra) {
  char line[LINE_CAPACITY];
  int used;
  used = snprintf(line, sizeof line, "diag {\"module\":\"%s\",\"op\":\"%s\",\"status\":\"%s\",\"code\":%d",
                  module, op, status, code);
  if (used < 0 || (size_t)used >= sizeof line) return;
  if (extra && extra[0]) {
    int added = snprintf(line + used, sizeof line - (size_t)used, ",%s", extra);
    if (added < 0 || (size_t)added >= sizeof line - (size_t)used) return;
    used += added;
  }
  snprintf(line + used, sizeof line - (size_t)used, "}");
  printf("%s\n", line);
  fflush(stdout);
}

static void diag_credentials(const char *op, exr_credentials_status status) {
  diag_line("credentials", op, exr_credentials_status_name(status), (int)status, NULL);
}

static void diag_profiles(const char *op, reader_account_profiles_status status,
                          const reader_account_profiles_error *error,
                          const char *extra_field) {
  char message[LINE_CAPACITY];
  char extra[LINE_CAPACITY];
  json_escape(error ? error->message : "", message, sizeof message);
  snprintf(extra, sizeof extra,
           "\"system_error\":%d,\"offset\":%llu,\"message\":\"%s\"%s%s%s",
           error ? error->system_error : 0,
           (unsigned long long)(error ? error->offset : 0ull), message,
           extra_field && extra_field[0] ? "," : "", extra_field ? extra_field : "",
           extra_field && extra_field[0] ? "" : "");
  diag_line("profiles", op, reader_account_profiles_status_name(status), (int)status, extra);
}

/* ---------- input ---------- */

static const char *text_get(const char *name) {
  int index;
  for (index = 0; index < g_text_count; ++index) {
    if (strcmp(g_text[index].name, name) == 0) return g_text[index].text;
  }
  return "";
}

static const value_entry *value_get(const char *name) {
  int index;
  for (index = 0; index < g_value_count; ++index) {
    if (strcmp(g_values[index].name, name) == 0) return &g_values[index];
  }
  return NULL;
}

static int hex_digit(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

static int decode_hex(const char *hex, unsigned char *out, size_t capacity, size_t *length) {
  size_t used = 0;
  while (hex[0] && hex[1]) {
    int high = hex_digit(hex[0]);
    int low = hex_digit(hex[1]);
    if (high < 0 || low < 0 || used >= capacity) return 0;
    out[used++] = (unsigned char)((high << 4) | low);
    hex += 2;
  }
  if (hex[0]) return 0;
  *length = used;
  return 1;
}

static void parse_directive(char *line) {
  char *name;
  char *value;
  char *space = strchr(line, ' ');
  if (!space) return;
  *space = '\0';
  name = space + 1;
  value = strchr(name, ' ');
  if (!value) return;
  *value = '\0';
  value += 1;
  if (strcmp(line, "text") == 0) {
    if (g_text_count >= TEXT_ENTRIES) return;
    snprintf(g_text[g_text_count].name, sizeof g_text[0].name, "%s", name);
    snprintf(g_text[g_text_count].text, sizeof g_text[0].text, "%s", value);
    g_text_count += 1;
  } else if (strcmp(line, "secret") == 0) {
    size_t length = 0;
    if (g_value_count >= VALUE_ENTRIES) return;
    if (!decode_hex(value, g_values[g_value_count].data, EXR_CREDENTIALS_SECRET_MAX, &length)) return;
    snprintf(g_values[g_value_count].name, sizeof g_values[0].name, "%s", name);
    g_values[g_value_count].length = length;
    g_value_count += 1;
  }
}

static void read_input(void) {
  size_t total = 0;
  size_t got;
#if defined(_WIN32)
  (void)_setmode(_fileno(stdin), _O_BINARY);
#endif
  while ((got = fread(g_input + total, 1, sizeof g_input - 1u - total, stdin)) > 0) {
    total += got;
    if (total + 1u >= sizeof g_input) break;
  }
  g_input[total] = '\0';
}

static void parse_input(void) {
  char *p = g_input;
  while (*p) {
    char *end = strchr(p, '\n');
    if (end) *end = '\0';
    if (p[0] && p[0] != '\r') parse_directive(p);
    if (!end) break;
    p = end + 1;
  }
}

/* ---------- OPDS host transport ---------- */

static char g_log[LOG_LINES][URL_CAPACITY];
static int g_log_count;
static int g_requests;
static int g_auth_exact;
static int g_transport_mode; /* 1 normal, 2 unauthorized, 3 server error, 4 redirect, 5 abort */
static const char *g_redirect_target;
static const char *g_expected_authorization;

static void opds_capture(void *context, const char *line) {
  (void)context;
  if (g_log_count >= LOG_LINES) return;
  snprintf(g_log[g_log_count], sizeof g_log[0], "%s", line ? line : "");
  g_log_count += 1;
}

static opds_status host_fetch(void *context, const opds_request *request, unsigned timeout_ms,
                              const opds_control *control, opds_head_fn head, opds_body_fn body,
                              void *user, opds_error *error) {
  unsigned char book[512];
  opds_response response;
  int index;
  (void)context;
  (void)timeout_ms;
  (void)error;
  if (control && control->cancelled && control->cancelled(control->context)) return OPDS_ABORTED;
  index = g_requests;
  g_requests += 1;
  if (request->authorization) {
    if (g_expected_authorization && strcmp(request->authorization, g_expected_authorization) == 0) {
      g_auth_exact += 1;
    }
  }
  memset(&response, 0, sizeof response);
  response.content_length = -1;
  if (g_transport_mode == 2) {
    response.status = 401;
    response.www_authenticate = "Basic realm=\"s08\"";
  } else if (g_transport_mode == 3) {
    response.status = 500;
  } else if (g_transport_mode == 4 && index == 0) {
    response.status = 302;
    response.location = g_redirect_target;
  } else {
    response.status = 200;
    response.content_type = "application/octet-stream";
  }
  if (head(user, &response)) return OPDS_OK;
  if (g_transport_mode == 5 && index == 0) return OPDS_ABORTED;
  memset(book, 0x42, sizeof book);
  book[0] = 0x50;
  book[1] = 0x4b;
  book[2] = 0x03;
  book[3] = 0x04;
  if (body(user, book, sizeof book)) return OPDS_ABORTED;
  return OPDS_OK;
}

static const opds_transport g_host_transport = {host_fetch, NULL};

static int line_status(const char *line) {
  size_t length = strlen(line);
  size_t index = length;
  int value = 0;
  int digits = 0;
  while (index > 0u && line[index - 1u] >= '0' && line[index - 1u] <= '9') {
    index -= 1u;
    digits += 1;
  }
  if (digits == 0 || digits > 3) return -1;
  for (; index < length; ++index) value = value * 10 + (line[index] - '0');
  return value;
}

static void diag_opds_line(const char *op, const char *line) {
  char escaped[LINE_CAPACITY];
  char extra[LINE_CAPACITY];
  int status = line_status(line);
  json_escape(line, escaped, sizeof escaped);
  snprintf(extra, sizeof extra, "\"http_status\":%d,\"log_line\":\"%s\"", status, escaped);
  diag_line("opds", op, "http", status, extra);
}

static void diag_opds_result(const char *op, opds_status status, const opds_error *error) {
  char escaped_message[1024];
  char escaped_scheme[128];
  char escaped_line[LINE_CAPACITY];
  char extra[LINE_CAPACITY];
  const char *line = g_log_count > 0 ? g_log[g_log_count - 1] : "";
  json_escape(error ? error->message : "", escaped_message, sizeof escaped_message);
  json_escape(error ? error->auth_scheme : "", escaped_scheme, sizeof escaped_scheme);
  json_escape(line, escaped_line, sizeof escaped_line);
  snprintf(extra, sizeof extra,
           "\"http_status\":%d,\"auth_scheme\":\"%s\",\"message\":\"%s\",\"log_line\":\"%s\"",
           error ? error->http_status : 0, escaped_scheme, escaped_message, escaped_line);
  diag_line("opds", op, opds_status_name(status), (int)status, extra);
}

static opds_client *opds_open(opds_config *config) {
  opds_config_defaults(config);
  config->transport = &g_host_transport;
  config->credential_origin = "http://reader.test:8080";
  config->authorization = text_get("authorization");
  config->log = opds_capture;
  config->log_context = NULL;
  config->user_agent = "exreader-s08";
  return opds_client_create(config);
}

static void opds_reset(int mode) {
  int index;
  g_log_count = 0;
  g_requests = 0;
  g_auth_exact = 0;
  g_transport_mode = mode;
  for (index = 0; index < LOG_LINES; ++index) g_log[index][0] = '\0';
}

static int contains(const char *haystack, const char *needle) {
  return needle && needle[0] && strstr(haystack, needle) != NULL;
}

static int file_exists(const char *path) {
  FILE *file = fopen(path, "rb");
  if (!file) return 0;
  fclose(file);
  return 1;
}

static void opds_phase(void) {
  opds_config config;
  opds_client *client;
  opds_error error;
  opds_download_result result;
  opds_status status;
  const char *download_dir = text_get("download-dir");
  const char *token = text_get("token");
  const char *userinfo_user = text_get("userinfo-user");
  const char *userinfo_password = text_get("userinfo-password");
  const char *authorization = text_get("authorization");
  const char *cookie = text_get("cookie");
  char url[URL_CAPACITY];
  char destination[URL_CAPACITY];
  char redacted[URL_CAPACITY];
  char expected[URL_CAPACITY];
  int index;

  g_expected_authorization = authorization;
  memset(&error, 0, sizeof error);
  snprintf(url, sizeof url,
           "http://%s:%s@reader.test:8080/shelf/reader/feed.epub?token=%s&page=2",
           userinfo_user, userinfo_password, token);

  /* --- normal download: log line is redacted but keeps method/path/status --- */
  opds_reset(1);
  client = opds_open(&config);
  snprintf(destination, sizeof destination, "%s/book-normal.epub", download_dir);
  status = opds_download_url(client, url, destination, NULL, NULL, &result, &error);
  for (index = 0; index < g_log_count; ++index) diag_opds_line("normal", g_log[index]);
  diag_opds_result("normal-result", status, &error);
  check("opds-normal-downloaded", status == OPDS_OK && result.published && result.bytes > 0u, "status=ok");
  check("opds-normal-log-count", g_log_count == 1, "log=1");
  check("opds-normal-log-method", g_log_count == 1 && strncmp(g_log[0], "GET ", 4) == 0, "method=GET");
  check("opds-normal-log-status", g_log_count == 1 && line_status(g_log[0]) == 200, "status=200");
  check("opds-normal-log-removes-userinfo",
        g_log_count == 1 && !contains(g_log[0], userinfo_user) && !contains(g_log[0], userinfo_password),
        "userinfo=absent");
  check("opds-normal-log-redacts-token",
        g_log_count == 1 && !contains(g_log[0], token) && contains(g_log[0], "token=REDACTED"),
        "token=redacted");
  check("opds-normal-log-keeps-source",
        g_log_count == 1 && contains(g_log[0], "reader.test:8080") &&
            contains(g_log[0], "/shelf/reader/feed.epub") && contains(g_log[0], "page=2"),
        "source=kept");
  check("opds-normal-log-no-authorization",
        g_log_count == 1 && !contains(g_log[0], authorization) && !contains(g_log[0], token) &&
            !contains(g_log[0], cookie),
        "authorization=absent");
  check("opds-normal-request-carried-exact-authorization", g_auth_exact == 1, "auth=exact");
  opds_client_free(client);

  /* --- 401: status, HTTP status and challenge scheme stay visible --- */
  opds_reset(2);
  client = opds_open(&config);
  snprintf(destination, sizeof destination, "%s/book-401.epub", download_dir);
  status = opds_download_url(client, url, destination, NULL, NULL, &result, &error);
  for (index = 0; index < g_log_count; ++index) diag_opds_line("unauthorized", g_log[index]);
  diag_opds_result("unauthorized-result", status, &error);
  check("opds-401-status", status == OPDS_AUTH_REQUIRED, "status=auth_required");
  check("opds-401-http-status", error.http_status == 401, "http=401");
  check("opds-401-scheme", strcmp(error.auth_scheme, "Basic") == 0, "scheme=Basic");
  check("opds-401-log-status", g_log_count == 1 && line_status(g_log[0]) == 401, "log=401");
  check("opds-401-log-no-secret", g_log_count == 1 && !contains(g_log[0], token) &&
                                      !contains(g_log[0], authorization) &&
                                      !contains(g_log[0], userinfo_password),
        "secret=absent");
  check("opds-401-message-useful", error.message[0] != '\0', "message=present");
  opds_client_free(client);

  /* --- 500: generic HTTP failure keeps its code --- */
  opds_reset(3);
  client = opds_open(&config);
  snprintf(destination, sizeof destination, "%s/book-500.epub", download_dir);
  status = opds_download_url(client, url, destination, NULL, NULL, &result, &error);
  for (index = 0; index < g_log_count; ++index) diag_opds_line("server-error", g_log[index]);
  diag_opds_result("server-error-result", status, &error);
  check("opds-500-status", status == OPDS_HTTP, "status=http");
  check("opds-500-http-status", error.http_status == 500, "http=500");
  check("opds-500-log-status", g_log_count == 1 && line_status(g_log[0]) == 500, "log=500");
  check("opds-500-log-no-secret", g_log_count == 1 && !contains(g_log[0], token) &&
                                      !contains(g_log[0], authorization),
        "secret=absent");
  opds_client_free(client);

  /* --- cancelled transfer: status is retained, secret is not --- */
  opds_reset(5);
  client = opds_open(&config);
  snprintf(destination, sizeof destination, "%s/book-abort.epub", download_dir);
  status = opds_download_url(client, url, destination, NULL, NULL, &result, &error);
  for (index = 0; index < g_log_count; ++index) diag_opds_line("cancelled", g_log[index]);
  diag_opds_result("cancelled-result", status, &error);
  check("opds-cancel-status", status == OPDS_ABORTED, "status=aborted");
  check("opds-cancel-log-status", g_log_count == 1 && line_status(g_log[0]) == 200, "log=200");
  check("opds-cancel-log-no-secret", g_log_count == 1 && !contains(g_log[0], token) &&
                                         !contains(g_log[0], authorization),
        "secret=absent");
  check("opds-cancel-no-file", !file_exists(destination), "temp=removed");
  opds_client_free(client);

  /* --- cross-origin redirect drops the credential --- */
  g_redirect_target = "http://other.test:8080/shelf/moved.epub";
  opds_reset(4);
  client = opds_open(&config);
  snprintf(destination, sizeof destination, "%s/book-moved.epub", download_dir);
  status = opds_download_url(client, url, destination, NULL, NULL, &result, &error);
  for (index = 0; index < g_log_count; ++index) diag_opds_line("redirect", g_log[index]);
  diag_opds_result("redirect-result", status, &error);
  check("opds-redirect-status", status == OPDS_OK && result.published, "status=ok");
  check("opds-redirect-two-lines", g_log_count == 2, "log=2");
  check("opds-redirect-first-302", g_log_count == 2 && line_status(g_log[0]) == 302, "first=302");
  check("opds-redirect-second-200", g_log_count == 2 && line_status(g_log[1]) == 200, "second=200");
  check("opds-redirect-drops-credential", g_auth_exact == 1, "auth=first-only");
  {
    unsigned requests = 0, redirects = 0, dropped = 0;
    opds_client_stats(client, &requests, &redirects, &dropped);
    check("opds-redirect-stats", requests == 2u && redirects == 1u && dropped == 1u, "dropped=1");
  }
  check("opds-redirect-log-no-secret",
        g_log_count == 2 && !contains(g_log[0], token) && !contains(g_log[1], token) &&
            !contains(g_log[0], userinfo_password) && !contains(g_log[1], userinfo_password),
        "secret=absent");
  opds_client_free(client);

  /* --- documented redaction contract, content never printed --- */
  opds_redact_url("http://user:pw@reader.test:8080/p?token=secret-value&page=2&Password=zz",
                  redacted, sizeof redacted);
  snprintf(expected, sizeof expected, "%s", "http://reader.test:8080/p?token=REDACTED&page=2&Password=REDACTED");
  check("opds-redact-contract", strcmp(redacted, expected) == 0, "contract=exact");
  {
    char extra[256];
    snprintf(extra, sizeof extra, "\"expected_length\":%llu,\"got_length\":%llu",
             (unsigned long long)strlen(expected), (unsigned long long)strlen(redacted));
    diag_line("opds-redact", "contract", strcmp(redacted, expected) == 0 ? "ok" : "mismatch",
              strcmp(redacted, expected) == 0 ? 0 : 1, extra);
  }
  opds_redact_url(url, redacted, 40u);
  check("opds-redact-truncation", strlen(redacted) < 40u, "terminated");
  check("opds-redact-truncation-no-secret", !contains(redacted, token) &&
                                                !contains(redacted, userinfo_password),
        "secret=absent");
  {
    char extra[256];
    snprintf(extra, sizeof extra, "\"expected_length\":39,\"got_length\":%llu",
             (unsigned long long)strlen(redacted));
    diag_line("opds-redact", "truncation", strlen(redacted) < 40u ? "ok" : "mismatch",
              strlen(redacted) < 40u ? 0 : 1, extra);
  }
  {
    char long_url[5000];
    size_t prefix = strlen("http://reader.test:8080/shelf/");
    memset(long_url, 'a', sizeof long_url);
    memcpy(long_url, "http://reader.test:8080/shelf/", prefix);
    long_url[sizeof long_url - 1u] = '\0';
    opds_redact_url(long_url, redacted, sizeof redacted);
    check("opds-redact-long-input",
          strlen(redacted) > 0u && strlen(redacted) + 1u <= sizeof redacted, "terminated");
  }
  phase_end("opds");
}

/* ---------- credentials ---------- */

static int bytes_equal(const unsigned char *left, size_t left_length, const unsigned char *right,
                       size_t right_length) {
  return left_length == right_length && (left_length == 0u || memcmp(left, right, left_length) == 0);
}

static void credentials_open_and_write(exr_credentials_store *store, const char *account,
                                       const value_entry *value, const char *op, int *ok) {
  exr_credentials_status status;
  status = exr_credentials_put(store, account, value->data, value->length);
  *ok = status == EXR_CRED_OK;
  diag_credentials(op, status);
}

static void credentials_phase(const char *account_a, const char *account_b, const char *account_c,
                              const char *account_u, int unavailable) {
  const char *ns = text_get("namespace");
  const char *ns2 = text_get("namespace2");
  const value_entry *primary = value_get("primary");
  const value_entry *update = value_get("update");
  const value_entry *other = value_get("other");
  const value_entry *binary = value_get("binary");
  const value_entry *maximum = value_get("max");
  const value_entry *unicode = value_get("unicode");
  exr_credentials_store *store = NULL;
  exr_credentials_status status;
  unsigned char buffer[EXR_CREDENTIALS_SECRET_MAX];
  unsigned char small[8];
  size_t length = 0;
  int ok = 0;

  if (!primary || !update || !other || !binary || !maximum || !unicode) {
    check("cred-input-complete", 0, "input=missing");
    phase_end(unavailable ? "unavailable" : "credentials");
    return;
  }

  status = exr_credentials_open("Bad Namespace", &store);
  check("cred-open-rejects-invalid-namespace", status == EXR_CRED_ARGUMENT && store == NULL,
        "status=ARGUMENT");
  diag_credentials("open-invalid-namespace", status);

  status = exr_credentials_open(ns, &store);
  check("cred-open", status == EXR_CRED_OK && store != NULL, "status=OK");
  diag_credentials("open", status);
  if (status != EXR_CRED_OK) {
    check("cred-open-usable", 0, "status=not-ok");
    phase_end(unavailable ? "unavailable" : "credentials");
    return;
  }

  if (unavailable) {
    status = exr_credentials_put(store, account_u, primary->data, primary->length);
    check("unavailable-put", status == EXR_CRED_UNAVAILABLE, "status=UNAVAILABLE");
    diag_credentials("put-unavailable", status);
    length = 0;
    status = exr_credentials_get(store, account_u, buffer, sizeof buffer, &length);
    check("unavailable-get-absent", status == EXR_CRED_UNAVAILABLE && length == 0u,
          "status=UNAVAILABLE");
    diag_credentials("get-unavailable-absent", status);
    length = 0;
    status = exr_credentials_get(store, account_a, buffer, sizeof buffer, &length);
    check("unavailable-get-existing", status == EXR_CRED_UNAVAILABLE && length == 0u,
          "status=UNAVAILABLE");
    diag_credentials("get-unavailable-existing", status);
    status = exr_credentials_delete(store, account_u);
    check("unavailable-delete", status == EXR_CRED_UNAVAILABLE, "status=UNAVAILABLE");
    diag_credentials("delete-unavailable", status);
    exr_credentials_close(store);
    phase_end("unavailable");
    return;
  }

  length = 0;
  status = exr_credentials_get(store, account_a, buffer, sizeof buffer, &length);
  check("cred-empty-get-not-found", status == EXR_CRED_NOT_FOUND && length == 0u,
        "status=NOT_FOUND");
  diag_credentials("get-absent", status);

  status = exr_credentials_delete(store, account_a);
  check("cred-empty-delete-not-found", status == EXR_CRED_NOT_FOUND, "status=NOT_FOUND");
  diag_credentials("delete-absent", status);

  credentials_open_and_write(store, account_a, primary, "put", &ok);
  check("cred-put", ok, "status=OK");
  length = 0;
  status = exr_credentials_get(store, account_a, buffer, sizeof buffer, &length);
  check("cred-get-read-back", status == EXR_CRED_OK &&
                                    bytes_equal(buffer, length, primary->data, primary->length),
        "bytes=exact");
  diag_credentials("get", status);
  exr_credentials_wipe(buffer, sizeof buffer);

  credentials_open_and_write(store, account_a, update, "put-update", &ok);
  check("cred-update", ok, "status=OK");
  memset(buffer, 0xAA, sizeof buffer);
  length = 0;
  status = exr_credentials_get(store, account_a, buffer, sizeof buffer, &length);
  check("cred-update-no-stale", status == EXR_CRED_OK &&
                                     bytes_equal(buffer, length, update->data, update->length),
        "bytes=exact");
  diag_credentials("get-updated", status);
  exr_credentials_wipe(buffer, sizeof buffer);

  credentials_open_and_write(store, account_b, other, "put-other-account", &ok);
  check("cred-put-other-account", ok, "status=OK");
  length = 0;
  status = exr_credentials_get(store, account_b, buffer, sizeof buffer, &length);
  check("cred-account-isolation", status == EXR_CRED_OK &&
                                      bytes_equal(buffer, length, other->data, other->length),
        "other=exact");
  diag_credentials("get-other-account", status);
  exr_credentials_wipe(buffer, sizeof buffer);

  {
    exr_credentials_store *second = NULL;
    status = exr_credentials_open(ns2, &second);
    check("cred-open-second-namespace", status == EXR_CRED_OK && second != NULL, "status=OK");
    diag_credentials("open-second-namespace", status);
    if (second) {
      length = 0;
      status = exr_credentials_get(second, account_a, buffer, sizeof buffer, &length);
      check("cred-namespace-isolation", status == EXR_CRED_NOT_FOUND, "status=NOT_FOUND");
      diag_credentials("get-other-namespace", status);
      status = exr_credentials_put(second, account_c, other->data, other->length);
      check("cred-put-second-namespace", status == EXR_CRED_OK, "status=OK");
      diag_credentials("put-second-namespace", status);
      exr_credentials_close(second);
    }
  }

  memset(small, 0, sizeof small);
  length = 0;
  status = exr_credentials_get(store, account_a, small, sizeof small, &length);
  check("cred-small-buffer", status == EXR_CRED_ARGUMENT && length == update->length,
        "status=ARGUMENT");
  check("cred-small-buffer-untouched", small[0] == 0u && small[1] == 0u, "buffer=untouched");
  diag_credentials("get-small-buffer", status);

  status = exr_credentials_put(store, "NOT-A-UUID", primary->data, primary->length);
  check("cred-invalid-account", status == EXR_CRED_ARGUMENT, "status=ARGUMENT");
  diag_credentials("put-invalid-account", status);

  status = exr_credentials_put(store, account_a, primary->data, 0u);
  check("cred-zero-length", status == EXR_CRED_ARGUMENT, "status=ARGUMENT");
  diag_credentials("put-zero-length", status);

  credentials_open_and_write(store, account_c, binary, "put-binary", &ok);
  check("cred-put-binary", ok, "status=OK");
  length = 0;
  status = exr_credentials_get(store, account_c, buffer, sizeof buffer, &length);
  check("cred-binary-exact", status == EXR_CRED_OK &&
                                 bytes_equal(buffer, length, binary->data, binary->length),
        "bytes=exact");
  diag_credentials("get-binary", status);
  exr_credentials_wipe(buffer, sizeof buffer);

  credentials_open_and_write(store, account_c, unicode, "put-unicode", &ok);
  check("cred-put-unicode", ok, "status=OK");
  length = 0;
  status = exr_credentials_get(store, account_c, buffer, sizeof buffer, &length);
  check("cred-unicode-exact", status == EXR_CRED_OK &&
                                  bytes_equal(buffer, length, unicode->data, unicode->length),
        "bytes=exact");
  diag_credentials("get-unicode", status);
  exr_credentials_wipe(buffer, sizeof buffer);

  credentials_open_and_write(store, account_c, maximum, "put-maximum", &ok);
  check("cred-put-maximum", ok, "status=OK");
  length = 0;
  status = exr_credentials_get(store, account_c, buffer, sizeof buffer, &length);
  check("cred-maximum-exact", status == EXR_CRED_OK &&
                                  bytes_equal(buffer, length, maximum->data, maximum->length),
        "bytes=exact");
  diag_credentials("get-maximum", status);
  exr_credentials_wipe(buffer, sizeof buffer);

  status = exr_credentials_delete(store, account_c);
  check("cred-delete", status == EXR_CRED_OK, "status=OK");
  diag_credentials("delete", status);
  status = exr_credentials_delete(store, account_c);
  check("cred-delete-again", status == EXR_CRED_NOT_FOUND, "status=NOT_FOUND");
  diag_credentials("delete-again", status);

  check("cred-status-names",
        strcmp(exr_credentials_status_name(EXR_CRED_OK), "OK") == 0 &&
            strcmp(exr_credentials_status_name(EXR_CRED_NOT_FOUND), "NOT_FOUND") == 0 &&
            strcmp(exr_credentials_status_name(EXR_CRED_UNAVAILABLE), "UNAVAILABLE") == 0 &&
            strcmp(exr_credentials_status_name(EXR_CRED_ARGUMENT), "ARGUMENT") == 0 &&
            strcmp(exr_credentials_status_name(EXR_CRED_IO), "IO") == 0,
        "names=stable");
  diag_credentials("status-names", EXR_CRED_OK);
  check("cred-no-message-surface", exr_credentials_status_name(EXR_CRED_IO)[0] != '\0',
        "surface=status");

  exr_credentials_close(store);
  phase_end("credentials");
}

/* ---------- account profiles ---------- */

typedef struct {
  int polls;
  int limit;
} cancel_state;

static int cancel_poll(void *context) {
  cancel_state *state = (cancel_state *)context;
  state->polls += 1;
  return state->limit > 0 && state->polls >= state->limit;
}

static void make_profile(reader_account_profile *profile, const char *id, const char *account,
                         const char *url, const char *name) {
  memset(profile, 0, sizeof *profile);
  profile->struct_size = (uint32_t)sizeof *profile;
  snprintf(profile->profile_id, sizeof profile->profile_id, "%s", id);
  snprintf(profile->account_id, sizeof profile->account_id, "%s", account);
  snprintf(profile->root_url, sizeof profile->root_url, "%s", url);
  snprintf(profile->display_name, sizeof profile->display_name, "%s", name);
}

static unsigned long long file_hash(const char *path, int *exists) {
  unsigned long long hash = 1469598103934665603ull;
  FILE *file = fopen(path, "rb");
  int byte;
  if (!file) {
    *exists = 0;
    return 0ull;
  }
  *exists = 1;
  while ((byte = fgetc(file)) != EOF) {
    hash ^= (unsigned char)byte;
    hash *= 1099511628211ull;
  }
  fclose(file);
  return hash;
}

static reader_account_profiles_status profiles_reload(const char *store,
                                                      reader_account_profiles_list *list,
                                                      reader_account_profiles_error *error,
                                                      const char *op) {
  reader_account_profiles_status status;
  memset(list, 0, sizeof *list);
  list->struct_size = (uint32_t)sizeof *list;
  reader_account_profiles_error_clear(error);
  status = reader_account_profiles_load(store, list, NULL, error);
  diag_profiles(op, status, error, NULL);
  return status;
}

static void profiles_phase(void) {
  const char *store = text_get("store");
  const char *store_version = text_get("store-version");
  const char *store_format = text_get("store-format");
  const char *store_io = text_get("store-io");
  const char *store_limit = text_get("store-limit");
  const char *id_a = text_get("profile-a");
  const char *id_b = text_get("profile-b");
  const char *id_c = text_get("profile-c");
  const char *id_cancel = text_get("profile-cancel");
  const char *account_a = text_get("account-a");
  const char *account_b = text_get("account-b");
  const char *account_c = text_get("account-c");
  const char *url_1 = text_get("url-1");
  const char *url_2 = text_get("url-2");
  const char *name_a = text_get("name-a");
  const char *name_b = text_get("name-b");
  const char *name_c = text_get("name-c");
  const char *renamed = text_get("name-renamed");
  reader_account_profiles_list *list = (reader_account_profiles_list *)malloc(sizeof *list);
  reader_account_profiles_activation *plan =
      (reader_account_profiles_activation *)malloc(sizeof *plan);
  reader_account_profiles_error error;
  reader_account_profiles_status status;
  reader_account_profile profile;
  reader_account_profiles_options options;
  cancel_state cancel;
  uint64_t generation = 0;
  char path[2304];
  unsigned long long before = 0ull, after = 0ull;
  int exists = 0;
  FILE *temp = NULL;

  if (!list || !plan) {
    check("profiles-memory", 0, "allocation=failed");
    phase_end("profiles");
    return;
  }

  status = profiles_reload(store, list, &error, "load-empty");
  check("profiles-empty-load", status == READER_ACCOUNT_PROFILES_OK && list->count == 0u &&
                                   list->generation == 0ull,
        "count=0");

  make_profile(&profile, id_a, account_a, url_1, name_a);
  status = reader_account_profiles_add(store, &profile, NULL, &generation, &error);
  diag_profiles("add-a", status, &error, NULL);
  check("profiles-add-a", status == READER_ACCOUNT_PROFILES_OK && generation == 1ull, "gen=1");

  make_profile(&profile, id_b, account_b, url_1, name_b);
  status = reader_account_profiles_add(store, &profile, NULL, &generation, &error);
  diag_profiles("add-b", status, &error, NULL);
  check("profiles-add-b-same-url", status == READER_ACCOUNT_PROFILES_OK && generation == 2ull,
        "gen=2");

  make_profile(&profile, id_c, account_a, url_2, name_c);
  status = reader_account_profiles_add(store, &profile, NULL, &generation, &error);
  diag_profiles("add-c", status, &error, NULL);
  check("profiles-add-c-same-account", status == READER_ACCOUNT_PROFILES_OK && generation == 3ull,
        "gen=3");

  status = profiles_reload(store, list, &error, "load-three");
  check("profiles-load-three", status == READER_ACCOUNT_PROFILES_OK && list->count == 3u &&
                                   list->generation == 3ull,
        "count=3");
  check("profiles-order-and-fields",
        list->count == 3u && strcmp(list->profiles[0].profile_id, id_a) == 0 &&
            strcmp(list->profiles[1].profile_id, id_b) == 0 &&
            strcmp(list->profiles[2].profile_id, id_c) == 0 &&
            strcmp(list->profiles[0].root_url, url_1) == 0 &&
            strcmp(list->profiles[0].display_name, name_a) == 0,
        "fields=exact");

  memset(plan, 0, sizeof *plan);
  plan->struct_size = (uint32_t)sizeof *plan;
  status = reader_account_profiles_prepare_activation(store, id_a, NULL, plan, &error);
  diag_profiles("activation-a", status, &error, NULL);
  check("profiles-activation-a", status == READER_ACCOUNT_PROFILES_OK &&
                                     strstr(plan->product_path, id_a) != NULL &&
                                     strstr(plan->private_directory, id_a) != NULL &&
                                     strstr(plan->original_directory, id_a) != NULL,
        "paths=under-profile");
  check("profiles-activation-plan-fields",
        status == READER_ACCOUNT_PROFILES_OK &&
            plan->store_generation == 3ull &&
            strcmp(plan->profile.root_url, url_1) == 0 &&
            strcmp(plan->profile.account_id, account_a) == 0 &&
            strcmp(plan->product_path, plan->private_directory) != 0,
        "plan=exact");
  status = reader_account_profiles_verify_activation(store, plan, NULL, &error);
  diag_profiles("activation-verify", status, &error, NULL);
  check("profiles-activation-verify", status == READER_ACCOUNT_PROFILES_OK, "status=OK");

  {
    reader_account_profiles_activation *other_plan =
        (reader_account_profiles_activation *)malloc(sizeof *other_plan);
    if (other_plan) {
      memset(other_plan, 0, sizeof *other_plan);
      other_plan->struct_size = (uint32_t)sizeof *other_plan;
      status = reader_account_profiles_prepare_activation(store, id_b, NULL, other_plan, &error);
      diag_profiles("activation-b", status, &error, NULL);
      check("profiles-account-isolation",
            status == READER_ACCOUNT_PROFILES_OK &&
                strcmp(other_plan->product_path, plan->product_path) != 0 &&
                strstr(other_plan->product_path, id_b) != NULL,
            "paths=distinct");
      free(other_plan);
    } else {
      check("profiles-account-isolation", 0, "allocation=failed");
    }
  }

  make_profile(&profile, id_a, account_a, "https://user:pass@reader.test/shelf/", name_a);
  reader_account_profiles_error_clear(&error);
  status = reader_account_profiles_validate(&profile, &error);
  diag_profiles("validate-userinfo", status, &error, NULL);
  check("profiles-reject-userinfo", status == READER_ACCOUNT_PROFILES_SECRET, "status=SECRET");
  check("profiles-userinfo-message-useful",
        error.message[0] != '\0' && !contains(error.message, "reader.test") &&
            !contains(error.message, "user:pass"),
        "message=retained");

  make_profile(&profile, id_a, account_a, "https://reader.test/shelf/?token=abc", name_a);
  reader_account_profiles_error_clear(&error);
  status = reader_account_profiles_validate(&profile, &error);
  diag_profiles("validate-query", status, &error, NULL);
  check("profiles-reject-query", status == READER_ACCOUNT_PROFILES_SECRET, "status=SECRET");

  make_profile(&profile, "not-a-uuid", account_a, url_1, name_a);
  reader_account_profiles_error_clear(&error);
  status = reader_account_profiles_validate(&profile, &error);
  diag_profiles("validate-uuid", status, &error, NULL);
  check("profiles-reject-bad-uuid", status == READER_ACCOUNT_PROFILES_INVALID, "status=INVALID");

  make_profile(&profile, id_a, account_a, url_1, "bad\nname");
  reader_account_profiles_error_clear(&error);
  status = reader_account_profiles_validate(&profile, &error);
  diag_profiles("validate-control-name", status, &error, NULL);
  check("profiles-reject-control-name", status == READER_ACCOUNT_PROFILES_INVALID,
        "status=INVALID");

  make_profile(&profile, id_a, account_a, url_1, " leading");
  reader_account_profiles_error_clear(&error);
  status = reader_account_profiles_validate(&profile, &error);
  diag_profiles("validate-space-name", status, &error, NULL);
  check("profiles-reject-space-name", status == READER_ACCOUNT_PROFILES_INVALID, "status=INVALID");

  make_profile(&profile, id_a, account_a, url_1, name_a);
  status = reader_account_profiles_add("relative/store", &profile, NULL, &generation, &error);
  diag_profiles("add-relative-store", status, &error, NULL);
  check("profiles-reject-relative-store", status == READER_ACCOUNT_PROFILES_ARGUMENT,
        "status=ARGUMENT");

  memset(list, 0, sizeof *list);
  list->struct_size = (uint32_t)sizeof *list;
  reader_account_profiles_error_clear(&error);
  status = reader_account_profiles_load(NULL, list, NULL, &error);
  diag_profiles("load-null", status, &error, NULL);
  check("profiles-argument-diagnostic",
        status == READER_ACCOUNT_PROFILES_ARGUMENT && error.message[0] != '\0' &&
            error.system_error == 0,
        "status=ARGUMENT");

  memset(&options, 0, sizeof options);
  options.struct_size = (uint32_t)sizeof options;
  options.control.cancelled = cancel_poll;
  options.control.context = &cancel;
  snprintf(path, sizeof path, "%s/profiles.json", store);
  before = file_hash(path, &exists);
  cancel.polls = 0;
  cancel.limit = 1;
  make_profile(&profile, id_cancel, account_c, url_1, name_c);
  reader_account_profiles_error_clear(&error);
  status = reader_account_profiles_add(store, &profile, &options, &generation, &error);
  after = file_hash(path, &exists);
  diag_profiles("cancel-immediate", status, &error, NULL);
  check("profiles-cancel-immediate", status == READER_ACCOUNT_PROFILES_CANCELLED,
        "status=CANCELLED");
  check("profiles-cancel-immediate-unchanged", before == after, "hash=same");

  cancel.polls = 0;
  cancel.limit = 2;
  make_profile(&profile, id_cancel, account_c, url_2, name_c);
  reader_account_profiles_error_clear(&error);
  before = file_hash(path, &exists);
  status = reader_account_profiles_add(store, &profile, &options, &generation, &error);
  after = file_hash(path, &exists);
  diag_profiles("cancel-before-commit", status, &error, NULL);
  check("profiles-cancel-before-commit", status == READER_ACCOUNT_PROFILES_CANCELLED,
        "status=CANCELLED");
  check("profiles-cancel-before-commit-unchanged", before == after && before != 0ull,
        "hash=same");
  check("profiles-cancel-diagnostic-retained",
        status == READER_ACCOUNT_PROFILES_CANCELLED && error.message[0] != '\0', "message=retained");
  snprintf(path, sizeof path, "%s/profiles.json.tmp", store);
  temp = fopen(path, "rb");
  check("profiles-cancel-no-temp", temp == NULL, "temp=absent");
  if (temp) fclose(temp);

  status = profiles_reload(store_version, list, &error, "load-version");
  check("profiles-version-diagnostic", status == READER_ACCOUNT_PROFILES_VERSION &&
                                           error.offset > 0ull && error.message[0] != '\0',
        "status=VERSION");
  status = profiles_reload(store_format, list, &error, "load-format");
  check("profiles-format-diagnostic", status == READER_ACCOUNT_PROFILES_FORMAT &&
                                          error.offset > 0ull && error.message[0] != '\0',
        "status=FORMAT");
  make_profile(&profile, id_a, account_a, url_1, name_a);
  generation = 0;
  status = reader_account_profiles_add(store_io, &profile, NULL, &generation, &error);
  diag_profiles("add-io", status, &error, NULL);
  check("profiles-io-diagnostic",
        status == READER_ACCOUNT_PROFILES_IO && error.system_error != 0 && error.message[0] != '\0',
        "status=IO");

  {
    unsigned index = 0;
    int limit_ok = 1;
    reader_account_profile item;
    char account[40];
    for (index = 0; index < READER_ACCOUNT_PROFILES_MAX_PROFILES; ++index) {
      char id[40];
      snprintf(id, sizeof id, "10000000-0000-4000-8000-%012u", index);
      snprintf(account, sizeof account, "20000000-0000-4000-8000-%012u", index);
      make_profile(&item, id, account, url_1, name_a);
      generation = 0;
      status = reader_account_profiles_add(store_limit, &item, NULL, &generation, &error);
      if (status != READER_ACCOUNT_PROFILES_OK) limit_ok = 0;
      if (index == 0u) diag_profiles("limit-first", status, &error, NULL);
    }
    check("profiles-limit-fill", limit_ok, "count=32");
    snprintf(account, sizeof account, "30000000-0000-4000-8000-%012u", 0u);
    make_profile(&item, "30000000-0000-4000-8000-000000000000", account, url_1, name_a);
    generation = 0;
    status = reader_account_profiles_add(store_limit, &item, NULL, &generation, &error);
    diag_profiles("limit-overflow", status, &error, NULL);
    check("profiles-limit-refused", status == READER_ACCOUNT_PROFILES_LIMIT, "status=LIMIT");
  }

  status = reader_account_profiles_rename(store, id_a, renamed, NULL, &generation, &error);
  diag_profiles("rename", status, &error, NULL);
  check("profiles-rename", status == READER_ACCOUNT_PROFILES_OK && generation == 4ull, "gen=4");
  status = profiles_reload(store, list, &error, "load-renamed");
  check("profiles-rename-applied", status == READER_ACCOUNT_PROFILES_OK && list->count == 3u &&
                                       strcmp(list->profiles[0].display_name, renamed) == 0,
        "name=exact");

  snprintf(path, sizeof path, "%s/profiles/%s/s08-marker.txt", store, id_b);
  temp = fopen(path, "wb");
  check("profiles-marker-created", temp != NULL, "marker=created");
  if (temp) {
    fputs("kept", temp);
    fclose(temp);
  }
  status = reader_account_profiles_remove(store, id_b, NULL, &generation, &error);
  diag_profiles("remove", status, &error, NULL);
  check("profiles-remove", status == READER_ACCOUNT_PROFILES_OK && generation == 5ull, "gen=5");
  status = reader_account_profiles_remove(store, id_b, NULL, &generation, &error);
  diag_profiles("remove-absent", status, &error, NULL);
  check("profiles-remove-absent", status == READER_ACCOUNT_PROFILES_NOT_FOUND,
        "status=NOT_FOUND");
  status = profiles_reload(store, list, &error, "load-after-remove");
  check("profiles-remove-record-only", status == READER_ACCOUNT_PROFILES_OK && list->count == 2u,
        "count=2");
  temp = fopen(path, "rb");
  check("profiles-remove-keeps-directory", temp != NULL, "dir=kept");
  if (temp) fclose(temp);

  free(plan);
  free(list);
  phase_end("profiles");
}

/* ---------- reopen / worker / cleanup / verify ---------- */

static void reopen_phase(const char *account_a, const char *account_b, const char *account_c,
                         int expect_profiles) {
  const char *store = text_get("store");
  const char *ns = text_get("namespace");
  const value_entry *reopen = value_get("reopen");
  const value_entry *other = value_get("other");
  reader_account_profiles_list *list = (reader_account_profiles_list *)malloc(sizeof *list);
  reader_account_profiles_error error;
  reader_account_profiles_status status;
  exr_credentials_store *credentials = NULL;
  exr_credentials_status credential_status;
  unsigned char buffer[EXR_CREDENTIALS_SECRET_MAX];
  size_t length = 0;
  int ok = 1;

  if (!list || !reopen || !other) {
    check("reopen-memory", 0, "allocation=failed");
    phase_end("reopen");
    return;
  }
  status = profiles_reload(store, list, &error, "reopen-load");
  check("reopen-profiles-persist", status == READER_ACCOUNT_PROFILES_OK &&
                                       list->count == (uint32_t)expect_profiles,
        "count=persisted");
  check("reopen-profile-generation", status == READER_ACCOUNT_PROFILES_OK && list->generation > 0ull,
        "generation=kept");
  free(list);

  credential_status = exr_credentials_open(ns, &credentials);
  check("reopen-credentials-open", credential_status == EXR_CRED_OK && credentials != NULL,
        "status=OK");
  diag_credentials("reopen-open", credential_status);
  if (credential_status == EXR_CRED_OK && credentials) {
    length = 0;
    credential_status = exr_credentials_get(credentials, account_a, buffer, sizeof buffer, &length);
    if (!(credential_status == EXR_CRED_OK &&
          bytes_equal(buffer, length, reopen->data, reopen->length)))
      ok = 0;
    diag_credentials("reopen-get-worker-value", credential_status);
    exr_credentials_wipe(buffer, sizeof buffer);
    check("reopen-worker-credential-exact", ok, "bytes=exact");
    length = 0;
    credential_status = exr_credentials_get(credentials, account_b, buffer, sizeof buffer, &length);
    check("reopen-other-account-exact",
          credential_status == EXR_CRED_OK &&
              bytes_equal(buffer, length, other->data, other->length),
          "bytes=exact");
    diag_credentials("reopen-get-other", credential_status);
    exr_credentials_wipe(buffer, sizeof buffer);
    length = 0;
    credential_status = exr_credentials_get(credentials, account_c, buffer, sizeof buffer, &length);
    check("reopen-absent-account", credential_status == EXR_CRED_NOT_FOUND, "status=NOT_FOUND");
    diag_credentials("reopen-get-absent", credential_status);
    exr_credentials_close(credentials);
  }
  phase_end("reopen");
}

static void worker_phase(const char *account_a) {
  const char *store = text_get("store");
  const char *id_d = text_get("profile-d");
  const char *account_d = text_get("account-d");
  const char *url_1 = text_get("url-1");
  const char *name_d = text_get("name-d");
  const char *ns = text_get("namespace");
  const value_entry *reopen = value_get("reopen");
  reader_account_profile profile;
  reader_account_profiles_error error;
  reader_account_profiles_status status;
  exr_credentials_store *credentials = NULL;
  exr_credentials_status credential_status;
  uint64_t generation = 0;

  if (!reopen) {
    check("worker-input", 0, "input=missing");
    phase_end("worker");
    return;
  }
  make_profile(&profile, id_d, account_d, url_1, name_d);
  reader_account_profiles_error_clear(&error);
  status = reader_account_profiles_add(store, &profile, NULL, &generation, &error);
  diag_profiles("worker-add-profile", status, &error, NULL);
  check("worker-add-profile", status == READER_ACCOUNT_PROFILES_OK, "status=OK");

  credential_status = exr_credentials_open(ns, &credentials);
  diag_credentials("worker-open", credential_status);
  check("worker-credentials-open", credential_status == EXR_CRED_OK && credentials != NULL,
        "status=OK");
  if (credential_status == EXR_CRED_OK && credentials) {
    credential_status = exr_credentials_put(credentials, account_a, reopen->data, reopen->length);
    diag_credentials("worker-put", credential_status);
    check("worker-put", credential_status == EXR_CRED_OK, "status=OK");
    exr_credentials_close(credentials);
  }
  check("worker-exit", 1, "status=done");
  phase_end("worker");
}

static void cleanup_phase(const char *account_a, const char *account_b, const char *account_c) {
  const char *store = text_get("store");
  const char *ns = text_get("namespace");
  const char *ns2 = text_get("namespace2");
  const char *id_a = text_get("profile-a");
  const char *id_c = text_get("profile-c");
  const char *id_d = text_get("profile-d");
  exr_credentials_store *credentials = NULL;
  exr_credentials_status credential_status;
  reader_account_profiles_status status;
  reader_account_profiles_error error;
  uint64_t generation = 0;
  int ok = 1;

  credential_status = exr_credentials_open(ns, &credentials);
  diag_credentials("cleanup-open", credential_status);
  if (credential_status == EXR_CRED_OK && credentials) {
    credential_status = exr_credentials_delete(credentials, account_a);
    diag_credentials("cleanup-delete-a", credential_status);
    if (credential_status != EXR_CRED_OK) ok = 0;
    credential_status = exr_credentials_delete(credentials, account_b);
    diag_credentials("cleanup-delete-b", credential_status);
    if (credential_status != EXR_CRED_OK && credential_status != EXR_CRED_NOT_FOUND) ok = 0;
    credential_status = exr_credentials_delete(credentials, account_c);
    diag_credentials("cleanup-delete-c", credential_status);
    if (credential_status != EXR_CRED_OK && credential_status != EXR_CRED_NOT_FOUND) ok = 0;
    exr_credentials_close(credentials);
  } else {
    ok = 0;
  }
  check("cleanup-credentials-removed", ok, "status=removed");

  reader_account_profiles_error_clear(&error);
  status = reader_account_profiles_remove(store, id_a, NULL, &generation, &error);
  diag_profiles("cleanup-remove-a", status, &error, NULL);
  check("cleanup-remove-a", status == READER_ACCOUNT_PROFILES_OK, "status=OK");
  reader_account_profiles_error_clear(&error);
  status = reader_account_profiles_remove(store, id_c, NULL, &generation, &error);
  diag_profiles("cleanup-remove-c", status, &error, NULL);
  check("cleanup-remove-c", status == READER_ACCOUNT_PROFILES_OK, "status=OK");
  reader_account_profiles_error_clear(&error);
  status = reader_account_profiles_remove(store, id_d, NULL, &generation, &error);
  diag_profiles("cleanup-remove-d", status, &error, NULL);
  check("cleanup-remove-d", status == READER_ACCOUNT_PROFILES_OK, "status=OK");

  credential_status = exr_credentials_open(ns2, &credentials);
  diag_credentials("cleanup-open-second", credential_status);
  if (credential_status == EXR_CRED_OK && credentials) {
    credential_status = exr_credentials_delete(credentials, account_c);
    diag_credentials("cleanup-delete-second-namespace", credential_status);
    check("cleanup-second-namespace",
          credential_status == EXR_CRED_OK || credential_status == EXR_CRED_NOT_FOUND,
          "status=removed");
    exr_credentials_close(credentials);
  }
  phase_end("cleanup");
}

static void verify_clean_phase(const char *account_a, const char *account_c, const char *account_u,
                              int unavailable_check) {
  const char *store = text_get("store");
  const char *ns = text_get("namespace");
  const char *ns2 = text_get("namespace2");
  reader_account_profiles_list *list = (reader_account_profiles_list *)malloc(sizeof *list);
  reader_account_profiles_error error;
  reader_account_profiles_status status;
  exr_credentials_store *credentials = NULL;
  exr_credentials_status credential_status;
  unsigned char buffer[EXR_CREDENTIALS_SECRET_MAX];
  size_t length = 0;

  if (unavailable_check) {
    credential_status = exr_credentials_open(ns, &credentials);
    diag_credentials("verify-unavailable-open", credential_status);
    if (credential_status == EXR_CRED_OK && credentials) {
      length = 0;
      credential_status = exr_credentials_get(credentials, account_u, buffer, sizeof buffer, &length);
      check("verify-unavailable-wrote-nothing", credential_status == EXR_CRED_NOT_FOUND &&
                                                    length == 0u,
            "status=NOT_FOUND");
      diag_credentials("verify-unavailable-absent", credential_status);
      exr_credentials_wipe(buffer, sizeof buffer);
      exr_credentials_close(credentials);
      credentials = NULL;
    } else {
      check("verify-unavailable-wrote-nothing", 0, "status=open-failed");
    }
    credential_status = exr_credentials_open(ns2, &credentials);
    diag_credentials("verify-unavailable-open-second", credential_status);
    if (credential_status == EXR_CRED_OK && credentials) {
      length = 0;
      credential_status = exr_credentials_get(credentials, account_u, buffer, sizeof buffer, &length);
      check("verify-unavailable-second-namespace", credential_status == EXR_CRED_NOT_FOUND &&
                                                       length == 0u,
            "status=NOT_FOUND");
      diag_credentials("verify-unavailable-absent-second", credential_status);
      exr_credentials_wipe(buffer, sizeof buffer);
      exr_credentials_close(credentials);
      credentials = NULL;
    } else {
      check("verify-unavailable-second-namespace", 0, "status=open-failed");
    }
    free(list);
    phase_end("verify-clean");
    return;
  }

  credential_status = exr_credentials_open(ns, &credentials);
  diag_credentials("verify-open", credential_status);
  if (credential_status == EXR_CRED_OK && credentials) {
    length = 0;
    credential_status = exr_credentials_get(credentials, account_a, buffer, sizeof buffer, &length);
    check("verify-credential-absent", credential_status == EXR_CRED_NOT_FOUND,
          "status=NOT_FOUND");
    diag_credentials("verify-get-absent", credential_status);
    exr_credentials_wipe(buffer, sizeof buffer);
    credential_status = exr_credentials_get(credentials, account_c, buffer, sizeof buffer, &length);
    check("verify-clean-account-c", credential_status == EXR_CRED_NOT_FOUND, "status=NOT_FOUND");
    diag_credentials("verify-clean-absent-c", credential_status);
    exr_credentials_wipe(buffer, sizeof buffer);
    exr_credentials_close(credentials);
  } else {
    check("verify-credential-absent", 0, "status=open-failed");
    check("verify-clean-account-c", 0, "status=open-failed");
  }
  if (list) {
    status = profiles_reload(store, list, &error, "verify-load");
    check("verify-profiles-absent", status == READER_ACCOUNT_PROFILES_OK && list->count == 0u,
          "count=0");
  } else {
    check("verify-profiles-absent", 0, "allocation=failed");
  }
  free(list);
  phase_end("verify-clean");
}

/* ---------- entry ---------- */

int main(int argc, char **argv) {
  const char *phase;
  const char *account_a;
  const char *account_b;
  const char *account_c;
  const char *account_u;

  if (argc < 2) {
    printf("usage: reader-final-s08-consumer <phase>\n");
    return 2;
  }
  phase = argv[1];
  read_input();
  parse_input();
  account_a = text_get("account-a");
  account_b = text_get("account-b");
  account_c = text_get("account-c");
  account_u = text_get("account-u");

  if (strcmp(phase, "opds") == 0) {
    opds_phase();
  } else if (strcmp(phase, "credentials") == 0) {
    g_passed = 0;
    g_total = 0;
    credentials_phase(account_a, account_b, account_c, account_u, 0);
  } else if (strcmp(phase, "profiles") == 0) {
    profiles_phase();
  } else if (strcmp(phase, "worker") == 0) {
    worker_phase(account_a);
  } else if (strcmp(phase, "reopen") == 0) {
    reopen_phase(account_a, account_b, account_c, 3);
  } else if (strcmp(phase, "unavailable") == 0) {
    credentials_phase(account_a, account_b, account_c, account_u, 1);
  } else if (strcmp(phase, "verify-unavailable-clean") == 0) {
    verify_clean_phase(account_a, account_c, account_u, 1);
  } else if (strcmp(phase, "cleanup") == 0) {
    cleanup_phase(account_a, account_b, account_c);
  } else if (strcmp(phase, "verify-clean") == 0) {
    verify_clean_phase(account_a, account_c, account_u, 0);
  } else {
    printf("unknown phase %s\n", phase);
    return 2;
  }
  return g_passed == g_total && g_total > 0 ? 0 : 1;
}
