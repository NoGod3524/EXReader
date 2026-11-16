/* SPDX-License-Identifier: MIT */
/* F10 TLS beyond the loopback test CA: drive the installed product WebDAV
   client (WinHTTP on Windows, libcurl on Linux) against real public origins
   with the platform trust store. Positive origins must complete the TLS
   handshake and return an HTTP status; badssl.com origins with an expired,
   wrong-host, self-signed or untrusted-root certificate must be refused as
   EXR_DAV_TLS before any HTTP status exists. No credential is configured.
   With arguments the cases come from the command line instead, as
   accept=URL / refuse=URL; tests/ledger_f8910/private_tls uses that to drive
   the same client against a private-CA origin on a non-loopback address.
   Output: one JSON object on stdout; exit 0 only when every case matches. */
#include <stdio.h>
#include <string.h>
#include "exr_webdav.h"

typedef struct { const char *url; int expect_tls_refusal; const char *why; } tls_case;

static const char *status_name(exr_webdav_status s) {
  static const char *names[] = {"OK","ARGUMENT","MEMORY","IO","TLS","HTTP","AUTH","CANCELLED",
                                "LIMIT","FORMAT","REDIRECT","EXISTS"};
  return (unsigned)s < sizeof(names) / sizeof(names[0]) ? names[s] : "UNKNOWN";
}

static void json_string(const char *s) {
  putchar('"');
  for (; *s; s++) {
    unsigned char c = (unsigned char)*s;
    if (c == '"' || c == '\\') printf("\\%c", c);
    else if (c < 0x20) printf("\\u%04x", c);
    else putchar(c);
  }
  putchar('"');
}

int main(int argc, char **argv) {
  static const tls_case public_cases[] = {
    {"https://www.github.com/", 0, "public CA chain, valid host"},
    {"https://example.com/", 0, "public CA chain, valid host"},
    {"https://badssl.com/", 0, "public CA chain on the negative-test origin itself"},
    {"https://expired.badssl.com/", 1, "certificate expired"},
    {"https://wrong.host.badssl.com/", 1, "certificate name does not match host"},
    {"https://self-signed.badssl.com/", 1, "self-signed certificate"},
    {"https://untrusted-root.badssl.com/", 1, "chain to a root absent from the platform store"},
  };
  tls_case argument_cases[16];
  const tls_case *cases = public_cases;
  size_t count = sizeof(public_cases) / sizeof(public_cases[0]), passed = 0;
  if (argc > 1) {
    if (argc - 1 > (int)(sizeof(argument_cases) / sizeof(argument_cases[0]))) return 2;
    for (int i = 1; i < argc; i++) {
      int refuse = !strncmp(argv[i], "refuse=", 7);
      if (!refuse && strncmp(argv[i], "accept=", 7)) { fputs("usage: public-tls-probe [accept=URL|refuse=URL]...\n", stderr); return 2; }
      argument_cases[i - 1].url = argv[i] + 7;
      argument_cases[i - 1].expect_tls_refusal = refuse;
      argument_cases[i - 1].why = "command line";
    }
    cases = argument_cases;
    count = (size_t)argc - 1;
  }
  printf("{\"probe\":\"%s\",", argc > 1 ? "argument-tls" : "public-tls");
  printf("\"client\":\"EXReaderWebDAV %s\",\"cases\":[", EXR_WEBDAV_VERSION);
  for (size_t i = 0; i < count; i++) {
    exr_webdav_config config;
    exr_webdav_client *client = NULL;
    exr_webdav_listing listing;
    exr_webdav_error error;
    memset(&config, 0, sizeof config);
    memset(&listing, 0, sizeof listing);
    memset(&error, 0, sizeof error);
    config.root_url = cases[i].url;
    config.timeout_ms = 20000;
    config.max_listing_bytes = 1u << 20;
    exr_webdav_status created = exr_webdav_create(&config, &client, &error);
    exr_webdav_status listed = created;
    if (created == EXR_DAV_OK) {
      memset(&error, 0, sizeof error);
      listed = exr_webdav_list(client, "", NULL, &listing, &error);
      exr_webdav_listing_free(&listing);
      exr_webdav_free(client);
    }
    /* A refused certificate yields TLS with no HTTP status. Every status
       below is only produced from a response received over a completed
       handshake: a listing, an HTTP error, an authentication challenge, a
       body the client rejected, or a redirect it refused to follow (the
       client never follows redirects, e.g. www.github.com -> github.com). */
    int handshake_completed = created == EXR_DAV_OK &&
                              (listed == EXR_DAV_OK || listed == EXR_DAV_REDIRECT || listed == EXR_DAV_FORMAT ||
                               ((listed == EXR_DAV_HTTP || listed == EXR_DAV_AUTH) && error.http_status > 0));
    int refused = created == EXR_DAV_OK && listed == EXR_DAV_TLS && error.http_status == 0;
    int pass = cases[i].expect_tls_refusal ? refused : handshake_completed;
    passed += pass != 0;
    printf("%s{\"url\":", i ? "," : "");
    json_string(cases[i].url);
    printf(",\"expect\":\"%s\",\"why\":", cases[i].expect_tls_refusal ? "tls_refused" : "handshake_completed");
    json_string(cases[i].why);
    printf(",\"create\":\"%s\",\"list\":\"%s\",\"http_status\":%d,\"message\":",
           status_name(created), status_name(listed), error.http_status);
    json_string(error.message);
    printf(",\"pass\":%s}", pass ? "true" : "false");
    fflush(stdout);
  }
  printf("],\"passed\":%u,\"total\":%u,\"accepted\":%s}\n", (unsigned)passed, (unsigned)count,
         passed == count ? "true" : "false");
  return passed == count ? 0 : 1;
}
