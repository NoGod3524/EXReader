/* SPDX-License-Identifier: MIT */
/* Stand-alone mock WebDAV server: mock_webdav.exe PORT USER PASSWORD
   Prints "listening PORT" then serves until stdin closes or it is killed. */
#include <windows.h>
#include <process.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../../tools/convert_json.h"
#include "../../tools/convert_json.c"
#include "mock_webdav.inc"
int main(int argc, char **argv) {
  setvbuf(stdout, NULL, _IONBF, 0);
  if (argc < 4) { fprintf(stderr, "usage: mock_webdav PORT USER PASSWORD\n"); return 2; }
  int port = mock_start(atoi(argv[1]), argv[2], argv[3]);
  if (!port) { fprintf(stderr, "cannot listen\n"); return 1; }
  printf("listening %d\n", port);
  for (int c = getchar(); c != EOF; c = getchar()) {}
  mock_stop();
  return 0;
}
