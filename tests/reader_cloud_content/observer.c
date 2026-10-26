/* Ordinary installed-package HTTPS consumer: observed bytes, collision retry,
   redirect and cancellation. No concurrent path changes. */
#include <exr_webdav.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { unsigned char *data; size_t size; int failed; } observed;
static void collect(void *context, const void *bytes, size_t size) {
  observed *o = context;
  unsigned char *next = realloc(o->data, o->size + size);
  if (!next) { o->failed = 1; return; }
  o->data = next; memcpy(o->data + o->size, bytes, size); o->size += size;
}
static int stop(void *context) { return ((observed *)context)->size != 0; }
static int equal_file(const char *path, const observed *o) {
  FILE *f = fopen(path, "rb");
  size_t i;
  if (!f || o->failed) { if (f) fclose(f); return 0; }
  for (i = 0; i < o->size; i++) if (fgetc(f) != o->data[i]) { fclose(f); return 0; }
  i = (size_t)(fgetc(f) == EOF && !ferror(f)); fclose(f); return (int)i;
}
int main(int argc, char **argv) {
  exr_webdav_config config = {0}; exr_webdav_client *client = NULL;
  exr_webdav_error error = {0}; exr_webdav_download result = {0};
  exr_webdav_control control = {0}; observed o = {0}; char path[4096];
  exr_webdav_status status;
  if (argc != 4) return 1;
  config.root_url = argv[1]; config.authorization = argv[2];
  if (exr_webdav_create(&config, &client, &error) != EXR_DAV_OK) return 2;
  status = exr_webdav_download_observed(client, "err/redirect-same.epub", argv[3], "first.epub", NULL,
      collect, &o, &result, &error);
  snprintf(path, sizeof(path), "%s/first.epub", argv[3]);
  if (status != EXR_DAV_OK || !result.published || result.bytes != o.size || !equal_file(path, &o)) return 3;
  free(o.data); memset(&o, 0, sizeof(o));
  status = exr_webdav_download_observed(client, "err/redirect-same.epub", argv[3], "first.epub", NULL,
      collect, &o, &result, &error);
  if (status != EXR_DAV_EXISTS || !o.size || o.failed) return 4;
  free(o.data); memset(&o, 0, sizeof(o));
  status = exr_webdav_download_observed(client, "err/redirect-same.epub", argv[3], "second.epub", NULL,
      collect, &o, &result, &error);
  snprintf(path, sizeof(path), "%s/second.epub", argv[3]);
  if (status != EXR_DAV_OK || !result.published || result.bytes != o.size || !equal_file(path, &o)) return 5;
  free(o.data); memset(&o, 0, sizeof(o));
  control.cancelled = stop; control.context = &o;
  status = exr_webdav_download_observed(client, "err/redirect-same.epub", argv[3], "cancel.epub", &control,
      collect, &o, &result, &error);
  if (status != EXR_DAV_CANCELLED || result.published || o.failed) return 6;
  free(o.data); exr_webdav_free(client); return 0;
}
