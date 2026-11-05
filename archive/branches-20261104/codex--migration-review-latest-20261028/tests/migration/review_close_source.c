#include <exr/library.h>
#include <stdio.h>
#include <string.h>
int main(int argc, char **argv) {
  exr_library *lib = NULL; exr_source source = {0}, spare = {0}; exr_error error = {0};
  void *ledger = NULL; size_t size = 0; int found = 0;
  if (argc != 2 || exr_library_migration_open(argv[1], &lib, &error) != EXR_OK) return 2;
  if (exr_library_source(lib, 1, &source, &error) != EXR_OK) return 3;
  if (exr_library_migration_ledger_set(lib, "probe", 5, &error) != EXR_OK) return 4;
  if (exr_library_source(lib, 1, &spare, &error) != EXR_OK) return 5;
  spare.release(spare.context);
  if (exr_library_migration_ledger_get(lib, &ledger, &size, &found, &error) != EXR_OK ||
      !found || size != 5 || memcmp(ledger, "probe", 5)) return 6;
  exr_free(ledger);
  exr_library_close(lib);
  puts("READY"); fflush(stdout); getchar();
  source.release(source.context);
  return 0;
}
