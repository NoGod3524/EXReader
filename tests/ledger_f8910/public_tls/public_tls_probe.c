/* SPDX-License-Identifier: MIT */
/* F10 TLS beyond the loopback test CA: drive the installed product WebDAV
   client (WinHTTP on Windows, libcurl on Linux) against real public origins
   with the platform trust store. Positive origins must complete the TLS
   handshake and return an HTTP status; badssl.com origins with an expired,
   wrong-host, self-signed or untrusted-root certificate must be refused as
   EXR_DAV_TLS before any HTTP status exists. No credential is configured.
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
    if (c == '"' || c == '\') printf("\%c", c);
    else if (c < 0x20) printf("\u%04x", c);
    else putchar(c);
  }
  putchar('"');
}

int main(void) {
  static const tls_case cases[] = {
    {"https://www.github.com/", 0, "public CA chain, valid host"},
    {"https://example.com/", 0, "public CA chain, valid host"},
    {"https://badssl.com/", 0, "public CA chain on the negative-test origin itself"},
    {"https://expired.badssl.com/", 1, "certificate expired"},
    {"https://wrong.host.badssl.com/", 1, "certificate name does not match host"},
    {"https://self-signed.badssl.com/", 1, "self-signed certificate"},
    {"https://untrusted-root.badssl.com/", 1, "chain to a root absent from the platform store"},
  };
  size_t count = sizeof(cases) / sizeof(cases[0]), passed = 0;
  printf("{\"probe\":\"public-tls\",\"client\":\"EXReaderWebDAV %s\",\"cases\":[", EXR_WEBDAV_VERSION);
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
    /* A handshake that completed yields an HTTP status (or a WebDAV listing);
       a refused certificate yields TLS with no status. */
    int handshake_completed = created == EXR_DAV_OK && listed != EXR_DAV_TLS && listed != EXR_DAV_IO &&
                              (listed == EXR_DAV_OK || error.http_status > 0);
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
