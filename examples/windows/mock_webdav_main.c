/* SPDX-License-Identifier: MIT */
/* Stand-alone mock WebDAV server: mock_webdav.exe PORT USER PASSWORD
   Prints "listening PORT" then serves until stdin closes or it is killed. */
#include <winsock2.h>
#include <windows.h>
#include <process.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../../tools/convert_json.h"
#include "../../tools/convert_json.c"
#include "mock_webdav.inc"
int wmain(int argc, wchar_t **argv) {
  setvbuf(stdout, NULL, _IONBF, 0);
  if (argc < 4) { fprintf(stderr, "usage: mock_webdav PORT USER PASSWORD\n"); return 2; }
  char user[512], password[512];
  if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, argv[2], -1, user, sizeof(user), NULL, NULL) ||
      !WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, argv[3], -1, password, sizeof(password), NULL, NULL)) return 2;
  int port = mock_start(_wtoi(argv[1]), user, password);
  if (!port) { fprintf(stderr, "cannot listen\n"); return 1; }
  printf("listening %d\n", port);
  for (int c = getchar(); c != EOF; c = getchar()) {}
  mock_stop();
  return 0;
}
