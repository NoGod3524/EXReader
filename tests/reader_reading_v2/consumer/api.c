/* SPDX-License-Identifier: MIT */
#include <reader_reading_state.h>
#include <reader_projection.h>
int v2_c_contract(void){
  char *wire=(char *)1;size_t n=1;reader_rs_error error;
  if(READER_REVISION_ANCHOR_MAX_VERSION!=2)return 1;
  if(reader_rs_encode_v2(NULL,NULL,NULL,0,&wire,&n,&error)!=READER_RS_ARGUMENT||wire||n)return 2;
  size_t part=0;if(reader_rs_epub_record_part(NULL,NULL,&part,&error)!=READER_RS_ARGUMENT||part!=SIZE_MAX)return 3;
  if(reader_revision_local_reading(NULL,NULL,0,NULL,0,NULL,NULL,NULL)==READER_REV_OK)return 4;
  return 0;
}
