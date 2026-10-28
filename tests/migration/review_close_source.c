#include <exr/library.h>
#include <stdio.h>
#include <string.h>
int main(int argc, char **argv) {
  exr_library *lib = NULL; exr_source source = {0}; exr_error error = {0};
  if (argc != 2 || exr_library_migration_open(argv[1], &lib, &error) != EXR_OK) return 2;
  if (exr_library_source(lib, 1, &source, &error) != EXR_OK) return 3;
  if (exr_library_migration_ledger_set(lib, "probe", 5, &error) != EXR_OK) return 4;
  exr_library_close(lib);
  puts("READY"); fflush(stdout); getchar();
  source.release(source.context);
  return 0;
}
