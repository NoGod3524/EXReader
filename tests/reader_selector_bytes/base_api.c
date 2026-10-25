/* Standalone installed base header: no projection/command header supplies declarations. */
#include <reader_revisions.h>
int selector_bytes_base_api(void){
  if(READER_REVISION_ANCHOR_MAX_VERSION!=2)return 1;
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if(!reader_revisions_open_raw_v3||!reader_revision_get_raw_v3||!reader_revision_outbox_raw_v3)return 2;
#endif
  return 0;
}
