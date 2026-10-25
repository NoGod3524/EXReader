#include <string.h>
#include <exr/base.h>
#include <reader_cloud_import.h>
#include <reader_thumbnails.h>
#include <reader_book_information.h>
#include <reader_local_downloads.h>

int main(int argc, char **argv) {
  reader_cloud_request request;
  reader_ld_options options;
  rth_limits limits = rth_limits_defaults();
  reader_cloud_request_init(&request);
  reader_ld_options_init(&options);
  reader_book_information_free(NULL);
  if (argc != 2 || strcmp(exr_version(), argv[1])) return 1;
  return request.struct_size != sizeof(request) || options.struct_size != sizeof(options) ||
         limits.struct_size != sizeof(limits);
}
