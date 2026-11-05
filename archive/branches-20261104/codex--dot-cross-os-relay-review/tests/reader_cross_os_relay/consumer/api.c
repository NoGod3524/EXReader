/* SPDX-License-Identifier: MIT */
/* Pure C compile and link check of the installed public header. */
#include <exr_relay.h>
#include <string.h>
int main(void) {
  exr_relay_error error;
  char *json = (char *)1;
  size_t bytes = 1;
  char hex[65];
  uint64_t count = 1;
  if (exr_relay_inventory(NULL, NULL, NULL, &json, &bytes, &error) != EXR_RELAY_ARGUMENT || json || bytes) return 1;
  if (exr_relay_verify("x", NULL, 0, NULL, NULL, &error) != EXR_RELAY_ARGUMENT) return 2;
  if (exr_relay_sha256_file(NULL, 0, NULL, hex, &count, &error) != EXR_RELAY_ARGUMENT || count) return 3;
  exr_relay_free(NULL);
  return strcmp(EXR_RELAY_VERSION, "0.1.0") ? 4 : 0;
}
