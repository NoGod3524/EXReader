#include <exr/library.h>
#include <original_import.h>
#include <sqlite3.h>
int main() {
 reader_original_status (*volatile recover)(reader_catalog *, const char *) = &reader_original_recover;
 return exr_version() && sqlite3_libversion_number() > 0 && recover ? 0 : 1;
}
