#include <reader_reading_commands.h>
#include <reader_annotation_view.h>
#include <reader_projection.h>
#include <string.h>
int selector_bytes_c_api(void){
  if(READER_REVISION_ANCHOR_MAX_VERSION!=2)return 1;
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if(!reader_revisions_open_raw_v3||!reader_rs_encode_fixed_v3||!reader_av_page_get_raw_v3)return 2;
  if(strcmp(READER_REVISIONS_VERSION,"0.4.0")||strcmp(READER_READING_STATE_VERSION,"0.2.0")||strcmp(READER_READING_COMMANDS_VERSION,"0.2.0")||strcmp(READER_ANNOTATION_VIEW_VERSION,"0.2.0"))return 3;
#else
  if(strcmp(READER_REVISIONS_VERSION,"0.3.0")||strcmp(READER_READING_STATE_VERSION,"0.1.0")||strcmp(READER_READING_COMMANDS_VERSION,"0.1.0")||strcmp(READER_ANNOTATION_VIEW_VERSION,"0.1.0"))return 4;
#endif
  return 0;
}
