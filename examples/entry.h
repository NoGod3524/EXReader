/* SPDX-License-Identifier: MIT */
/* Include after static int example_main(int, char **). Windows argv uses the
   process code page, so read the Unicode command line and pass UTF-8 to the SDK. */
#ifdef _WIN32
#include <windows.h>
#include <shellapi.h>
#include <stdlib.h>
int main(void) {
  int argc = 0, i, result = 2;
  wchar_t **wide = CommandLineToArgvW(GetCommandLineW(), &argc);
  char **argv;
  if (!wide)
    return 2;
  argv = calloc((size_t)argc + 1, sizeof(*argv));
  if (!argv) {
    LocalFree(wide);
    return 2;
  }
  for (i = 0; i < argc; i++) {
    int n = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide[i], -1, NULL, 0, NULL, NULL);
    if (!n || !(argv[i] = malloc((size_t)n)))
      goto done;
    if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide[i], -1, argv[i], n, NULL, NULL))
      goto done;
  }
  result = example_main(argc, argv);
done:
  for (i = 0; i < argc; i++)
    free(argv[i]);
  free(argv);
  LocalFree(wide);
  return result;
}
#else
int main(int argc, char **argv) { return example_main(argc, argv); }
#endif
