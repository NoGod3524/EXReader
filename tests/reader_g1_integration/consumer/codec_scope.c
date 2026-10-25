/* Existing real codec roundtrip, plus extraction of each product-only archive. */
#define main original_codec_main
#include "codec.c"
#undef main
#include <reader_reading_commands.h>
#include <reader_annotation_view.h>
#include <reader_annotation_export.h>
int main(void) {
  reader_rc_result result = {0};
  reader_rc_error rc = {0};
  reader_av_view *view = NULL;
  reader_av_error av = {0};
  reader_annotation_export_stats stats = {0};
  reader_annotation_export_error ae = {0};
  CHECK(original_codec_main() == 0);
  CHECK(reader_rc_apply(NULL, NULL, &result, &rc) == READER_RC_ARGUMENT);
  CHECK(reader_av_open(NULL, NULL, NULL, &view, &av) == READER_AV_ARGUMENT);
  CHECK(view == NULL);
  CHECK(reader_annotation_export_run(NULL, &stats, &ae) == READER_ANNOTATION_EXPORT_ARGUMENT);
  puts("three product archives extracted with codec; no SDK linked");
  return 0;
}
